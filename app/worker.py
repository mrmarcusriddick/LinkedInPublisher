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
    from app.tokens import load_target_token
    auths = {}
    credential_failures = False
    for target in TARGETS:
        pattern = r'urn:li:person:[A-Za-z0-9_-]+' if target == 'personal' else r'urn:li:organization:[0-9]+'
        if not re.fullmatch(pattern, authors[target]):
            print(json.dumps({'target': target, 'status': 'author_not_configured'}))
            credential_failures = True
            continue
        try:
            auths[target] = load_target_token(client, target, now)
            if datetime.fromisoformat(auths[target]['expires_at']) < now + timedelta(days=7):
                print(json.dumps({'target': target, 'warning': 'linkedin_token_expires_within_7_days'}))
        except Exception as error:
            print(json.dumps({'target': target, 'status': 'credential_unavailable', 'type': type(error).__name__}))
            credential_failures = True
    session = requests.Session()  # Default: no automatic retries of POSTs.
    def send(target, text):
        response = session.post('https://api.linkedin.com/rest/posts', headers={
            'Authorization': 'Bearer ' + auths[target]['access_token'],
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
    failed = credential_failures
    for target in TARGETS:
        if target not in auths:
            continue
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
