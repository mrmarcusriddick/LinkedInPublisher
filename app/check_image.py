"""Prepare an image with the personal token; no public post unless --publish is given."""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from azure.identity import AzureCliCredential
from azure.keyvault.secrets import SecretClient
from app.tokens import load_target_token
from app.storage import Store
from app.media import validate_media, local_asset
from app.linkedin import LinkedIn, LinkedInError, prepare_image
from app.core import process

OWNER = 'urn:li:person:ntXyHnLoeu'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', default='2026-10-06')
    parser.add_argument('--publish', action='store_true', help='Publish a separate one-time image test now')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    media = validate_media(json.loads((root/'media'/f'{args.date}.json').read_text()))
    attachment = media['images']['personal']
    credential = AzureCliCredential()
    vault = SecretClient(vault_url='https://c2ea2e23015.vault.azure.net', credential=credential)
    auth = load_target_token(vault, 'personal', datetime.now(timezone.utc))
    api = LinkedIn(auth['access_token'], '202609', OWNER)
    store = Store('c2ea2e23015', credential=credential)
    # Local asset is checksum verified by prepare_image; only state access is needed.
    store.get_asset = lambda path: local_asset(root, attachment)
    image = None
    for attempt in range(6):
        image = prepare_image(store, 'personal', attachment, api)
        if image:
            break
        if attempt < 5:
            time.sleep(3)
    if not image:
        print(json.dumps({'status': 'image_processing', 'action': 'Run this command again shortly'}))
        return 1
    if not args.publish:
        print(json.dumps({'status': 'image_ready', 'image_id': image['id'], 'published': False}))
        return 0
    item = {'date': args.date, 'posts': {
        'personal': 'Clear ownership helps IT teams coordinate support. Knowing who resolves an issue, who approves a change, and who communicates progress gives everyone a clearer next step.\n\nCloud2e provides managed IT support to help businesses handle their everyday technology needs.\n\n#ManagedIT #Cloud2e',
        'company': 'Not published by this command'}, 'sources': ['https://www.cloud2e.com/']}
    with store.locked_state('manual-personal-image-test-v1') as (state, save):
        status = process(item, 'personal', state, save, lambda target, text: api.publish(text, image),
            datetime.now(timezone.utc), manual=True, attachment=attachment)
        result = {'status': status}
        if state.get('post_id'):
            result['url'] = 'https://www.linkedin.com/feed/update/' + state['post_id'] + '/'
        if state.get('reason'):
            result['reason'] = state['reason']
        print(json.dumps(result, indent=2))
        return 0 if status == 'published' else 1

if __name__ == '__main__':
    try:
        sys.exit(main())
    except LinkedInError as error:
        print(json.dumps({'status': 'linkedin_error', 'operation': error.operation,
                          'http_status': error.status, **error.details}))
        sys.exit(1)
    except Exception as error:
        print(json.dumps({'status': 'check_failed', 'type': type(error).__name__,
                          'http_status': getattr(error, 'status_code', None)}))
        sys.exit(1)
