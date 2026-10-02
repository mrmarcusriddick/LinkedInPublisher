import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
import requests
from azure.keyvault.secrets import SecretClient
from app.core import ZONE, TARGETS, due_at, process, validate
from app.storage import Store, Busy

def run():
    if os.getenv('PUBLISH_ENABLED', 'false').lower() != 'true':
        print(json.dumps({'status': 'paused'}))
        return 0
    now = datetime.now(timezone.utc)
    due = due_at(now.astimezone(ZONE).date().isoformat())
    if now < due or now >= due + timedelta(hours=1):
        return 0
    authors = {'personal': os.environ['LINKEDIN_PERSON_URN'], 'company': os.environ['LINKEDIN_ORG_URN']}
    if not re.fullmatch(r'urn:li:person:[A-Za-z0-9_-]+', authors['personal']):
        raise ValueError('Configure a verified personal URN')
    if not re.fullmatch(r'urn:li:organization:[0-9]+', authors['company']):
        raise ValueError('Configure a verified company URN')
    version = os.environ['LINKEDIN_API_VERSION']
    if not re.fullmatch(r'20[0-9]{2}(0[1-9]|1[0-2])', version):
        raise ValueError('Configure a supported LinkedIn API version YYYYMM')
    store = Store(os.environ['STORAGE_ACCOUNT'])
    item = store.get_day(now.astimezone(ZONE).date().isoformat())
    if item is None:
        print(json.dumps({'status': 'missing_content'}))
        return 1
    validate(item)
    client = SecretClient(vault_url=os.environ['KEY_VAULT_URL'], credential=store.credential)
    auth = json.loads(client.get_secret('linkedin-token').value)
    expiry = datetime.fromisoformat(auth['expires_at'])
    if expiry.tzinfo is None or expiry <= now + timedelta(minutes=5):
        print(json.dumps({'status': 'reauthorization_required'}))
        return 1
    if expiry < now + timedelta(days=7):
        print(json.dumps({'warning': 'linkedin_token_expires_within_7_days'}))
    session = requests.Session()  # Default: no automatic retries of POSTs.
    def send(target, text):
        response = session.post('https://api.linkedin.com/rest/posts', headers={
            'Authorization': 'Bearer ' + auth['access_token'],
            'Linkedin-Version': version,
            'X-Restli-Protocol-Version': '2.0.0',
            'Content-Type': 'application/json',
        }, json={'author': authors[target], 'commentary': text, 'visibility': 'PUBLIC',
            'distribution': {'feedDistribution': 'MAIN_FEED', 'targetEntities': [], 'thirdPartyDistributionChannels': []},
            'lifecycleState': 'PUBLISHED', 'isReshareDisabledByAuthor': False}, timeout=(5, 20), allow_redirects=False)
        retry_after = response.headers.get('Retry-After', '300')
        try:
            retry_after = int(retry_after)
        except ValueError:
            try:
                from email.utils import parsedate_to_datetime
                retry_after = max(300, int((parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds()))
            except Exception:
                retry_after = 3600
        return {'status': response.status_code, 'post_id': response.headers.get('x-restli-id'), 'retry_after': retry_after}
    failed = False
    for target in TARGETS:
        try:
            with store.locked_state(item['date'] + '-' + target) as (state, save):
                status = process(item, target, state, save, send, datetime.now(timezone.utc))
            failed |= status != 'published'
            print(json.dumps({'date': item['date'], 'target': target, 'status': status}))
        except Busy:
            print(json.dumps({'target': target, 'status': 'another_worker_active'}))
    return int(failed)

if __name__ == '__main__':
    try:
        sys.exit(run())
    except Exception as e:
        # Do not dump exception bodies/headers that may contain tokens.
        print(json.dumps({'status': 'configuration_or_storage_failure', 'type': type(e).__name__}))
        sys.exit(1)
