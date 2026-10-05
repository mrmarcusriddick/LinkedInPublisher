"""Explicit, one-time personal test. Does not change the scheduled publisher."""
import argparse
import json
import sys
from datetime import datetime, timezone
import requests
from azure.identity import AzureCliCredential
from azure.keyvault.secrets import SecretClient
from app.core import process
from app.storage import Store
from app.tokens import load_target_token

AUTHOR = 'urn:li:person:ntXyHnLoeu'
TEXT = ('I am setting up a space to share practical thoughts on managed IT, '
        'cybersecurity operations, and CMMC preparation.\n\n'
        'My focus will be on questions business owners and IT teams can use '
        'to have clearer conversations about their technology and security needs.\n\n'
        'What topic would you find most useful: everyday IT support, access '
        'management, recovery planning, or assessment preparation?\n\n'
        '#ManagedIT #Cybersecurity #CMMCPreparation')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if not args.publish:
        print(TEXT)
        return 0
    now = datetime.now(timezone.utc)
    credential = AzureCliCredential()
    client = SecretClient(vault_url='https://c2ea2e23015.vault.azure.net', credential=credential)
    auth = load_target_token(client, 'personal', now)
    session = requests.Session()
    profile = session.get('https://api.linkedin.com/v2/userinfo',
        headers={'Authorization': 'Bearer ' + auth['access_token']},
        timeout=(5, 20), allow_redirects=False)
    if profile.status_code != 200 or 'urn:li:person:' + str(profile.json().get('sub')) != AUTHOR:
        raise ValueError('Personal token does not match the intended author')
    item = {'date': '2026-10-05', 'posts': {'personal': TEXT, 'company': 'Not sent by this command'},
            'sources': ['https://www.cloud2e.com/']}
    def send(target, text):
        response = session.post('https://api.linkedin.com/rest/posts', headers={
            'Authorization': 'Bearer ' + auth['access_token'], 'Linkedin-Version': '202609',
            'X-Restli-Protocol-Version': '2.0.0', 'Content-Type': 'application/json',
        }, json={'author': AUTHOR, 'commentary': text, 'visibility': 'PUBLIC',
            'distribution': {'feedDistribution': 'MAIN_FEED', 'targetEntities': [], 'thirdPartyDistributionChannels': []},
            'lifecycleState': 'PUBLISHED', 'isReshareDisabledByAuthor': False},
            timeout=(5, 20), allow_redirects=False)
        return {'status': response.status_code, 'post_id': response.headers.get('x-restli-id')}
    store = Store('c2ea2e23015', credential=credential)
    # Fixed key survives reruns and is separate from all scheduled post states.
    with store.locked_state('manual-personal-test-2026-10-05') as (state, save):
        status = process(item, 'personal', state, save, send, datetime.now(timezone.utc), manual=True)
        result = {k: state[k] for k in ('post_id', 'reason') if k in state}
        result['status'] = status
        if state.get('post_id'):
            result['url'] = 'https://www.linkedin.com/feed/update/' + state['post_id'] + '/'
        print(json.dumps(result, indent=2))
        return 0 if status == 'published' else 1

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({'status': 'test_failed', 'type': type(error).__name__}))
        sys.exit(1)
