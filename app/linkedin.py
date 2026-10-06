"""Never log tokens, signed upload URLs or LinkedIn response bodies."""
import re
from urllib.parse import urlsplit, quote

class LinkedInError(Exception):
    def __init__(self, operation, status, response=None):
        self.operation, self.status = operation, status
        self.details = {}
        # Only machine codes are exposed, never response text or signed URLs.
        if response is not None:
            try:
                body = response.json()
                code = body.get('code')
                if isinstance(code, str) and re.fullmatch(r'[A-Z][A-Z_]{0,79}', code):
                    self.details['code'] = code
                service_code = body.get('serviceErrorCode')
                if type(service_code) is int:
                    self.details['service_error_code'] = service_code
            except (ValueError, AttributeError, TypeError):
                pass
        super().__init__(f'{operation}: HTTP {status}')

class LinkedIn:
    def __init__(self, token, version, owner, session=None):
        if session is None:
            import requests
            session = requests.Session()
        self.session, self.owner = session, owner
        self.headers = {'Authorization': 'Bearer ' + token, 'Linkedin-Version': version,
                        'X-Restli-Protocol-Version': '2.0.0', 'Content-Type': 'application/json'}

    def initialize(self):
        r = self.session.post('https://api.linkedin.com/rest/images?action=initializeUpload',
            headers=self.headers, json={'initializeUploadRequest': {'owner': self.owner}},
            timeout=(5, 15), allow_redirects=False)
        if r.status_code != 200:
            raise LinkedInError('image_initialize', r.status_code)
        value = r.json()['value']
        if not re.fullmatch(r'urn:li:image:[A-Za-z0-9_-]+', value['image']):
            raise ValueError('Invalid image URN')
        return value

    def upload(self, url, data):
        p = urlsplit(url)
        if (p.scheme != 'https' or p.hostname not in {'www.linkedin.com', 'api.linkedin.com'}
                or p.port not in {None, 443} or p.username or p.password
                or not p.path.startswith('/dms-uploads/')):
            raise ValueError('Unexpected LinkedIn upload destination')
        r = self.session.put(url, headers={'Authorization': self.headers['Authorization'],
            'Content-Type': 'image/png'}, data=data, timeout=(5, 15), allow_redirects=False)
        if r.status_code not in (200, 201, 202):
            raise LinkedInError('image_upload', r.status_code)

    def image_status(self, urn):
        headers = dict(self.headers)
        base = 'https://api.linkedin.com/rest/images/'
        if self.owner.startswith('urn:li:person:'):
            # Legacy reads use the v2 gateway. /rest requires a version header.
            # w_member_social cannot use the versioned image GET permission path.
            base = 'https://api.linkedin.com/v2/images/'
            headers.pop('Linkedin-Version')
        r = self.session.get(base + quote(urn, safe=''),
            headers=headers, timeout=(5, 15), allow_redirects=False)
        if r.status_code != 200:
            raise LinkedInError('image_status', r.status_code, r)
        return r.json()['status']

    def publish(self, text, media=None):
        body = {'author': self.owner, 'commentary': text, 'visibility': 'PUBLIC',
            'distribution': {'feedDistribution': 'MAIN_FEED', 'targetEntities': [], 'thirdPartyDistributionChannels': []},
            'lifecycleState': 'PUBLISHED', 'isReshareDisabledByAuthor': False}
        if media is not None:
            body['content'] = {'media': media}
        r = self.session.post('https://api.linkedin.com/rest/posts', headers=self.headers, json=body,
            timeout=(5, 20), allow_redirects=False)
        retry = r.headers.get('Retry-After', '300')
        try:
            retry = int(retry)
        except ValueError:
            from datetime import datetime, timezone
            from email.utils import parsedate_to_datetime
            try:
                retry = max(300, int((parsedate_to_datetime(retry) - datetime.now(timezone.utc)).total_seconds()))
            except Exception:
                retry = 3600
        return {'status': r.status_code, 'post_id': r.headers.get('x-restli-id'), 'retry_after': retry}

def prepare_image(store, target, attachment, client):
    """Upload before claiming a post. Retry uploads safely; never guess readiness."""
    from app.media import validate_png
    from hashlib import sha256
    owner_hash = sha256(client.owner.encode()).hexdigest()[:16]
    key = 'image-' + target + '-' + owner_hash + '-' + attachment['sha256']
    with store.locked_state(key) as (state, save):
        if state.get('status') == 'available':
            return {'id': state['image'], 'altText': attachment['alt']}
        if state.get('status') == 'failed':
            raise ValueError('Image processing failed; operator review required')
        if state.get('status') != 'uploaded':
            data = validate_png(store.get_asset(attachment['path']), attachment['sha256'])
            value = client.initialize()
            # An interrupted upload can leave an unused asset, never a public post.
            client.upload(value['uploadUrl'], data)
            state.update(status='uploaded', image=value['image'])
            save(state)
            return None
        status = client.image_status(state['image'])
        if status == 'AVAILABLE':
            state['status'] = 'available'
            save(state)
            return {'id': state['image'], 'altText': attachment['alt']}
        if status == 'PROCESSING_FAILED':
            state['status'] = 'failed'
            save(state)
            raise ValueError('Image processing failed')
        return None
