"""Apply Marcus's approved logo replacements without resetting post delivery state."""
import argparse
import json
import subprocess
import sys
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path

DATES = ('2026-10-07', '2026-10-08', '2026-10-09')
ACCOUNT = 'c2ea2e23015'
GROUP = 'rg-cloud2e-publisher'
SUBSCRIPTION = 'a2e23015-1a59-4109-9126-cd464798993f'

def az(*args):
    result = subprocess.run(['az', *args, '--subscription', SUBSCRIPTION,
                             '--only-show-errors', '--output', 'json'],
                            capture_output=True, text=True)
    if result.returncode:
        # Azure output may contain credentials. Never print captured output.
        raise RuntimeError('Azure CLI operation failed: ' + ' '.join(args[:3]))
    return json.loads(result.stdout) if result.stdout.strip() else None

def assert_unattempted(state, day, target):
    if state:
        raise ValueError(f'{day} {target}: delivery state exists; refusing replacement')

def check_manifest(current, old, new):
    if current == new:
        return False
    if current != old:
        raise ValueError('Azure attachment differs from both approved versions')
    return True

def read_state(service, day, target, lease=None):
    from azure.core.exceptions import ResourceNotFoundError
    blob = service.get_blob_client('state', f'{day}-{target}.json')
    try:
        return json.loads(blob.download_blob(lease=lease).readall())
    except ResourceNotFoundError:
        return {}

@contextmanager
def hold_state(service, day, target):
    from azure.core.exceptions import ResourceExistsError
    blob = service.get_blob_client('state', f'{day}-{target}.json')
    try:
        blob.upload_blob(b'{}', overwrite=False)
    except ResourceExistsError:
        pass
    lease = blob.acquire_lease(lease_duration=60)
    try:
        yield lease
    finally:
        lease.release()

def set_enabled(value):
    az('containerapp', 'job', 'update', '--resource-group', GROUP, '--name', ACCOUNT,
       '--set-env-vars', 'PUBLISH_ENABLED=' + value)

def main():
    from azure.storage.blob import BlobServiceClient, ContentSettings
    from azure.core import MatchConditions
    from azure.core.exceptions import ResourceExistsError
    from app.media import validate_media, local_asset, validate_png
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    plans = []
    assets = {}
    for day in DATES:
        old = validate_media(json.loads((root/'operator'/'logo-original-media'/f'{day}.json').read_text()))
        payload = (root/'media'/f'{day}.json').read_bytes()
        new = validate_media(json.loads(payload))
        for attachment in new['images'].values():
            assets[attachment['path']] = (local_asset(root, attachment), attachment['sha256'])
        plans.append((day, old, new, payload))
    # The existing Azure administrator's account-key permission provides queue
    # access. The key stays in memory; it is never printed or written to disk.
    keys = az('storage', 'account', 'keys', 'list', '--resource-group', GROUP,
              '--account-name', ACCOUNT)
    service = BlobServiceClient(f'https://{ACCOUNT}.blob.core.windows.net', credential=keys[0]['value'])
    del keys
    pending = []
    for day, old, new, payload in plans:
        blob = service.get_blob_client('queue', f'media/{day}.json')
        current = json.loads(blob.download_blob().readall())
        if check_manifest(current, old, new):
            for target in ('personal', 'company'):
                assert_unattempted(read_state(service, day, target), day, target)
            pending.append((day, old, new, payload, blob))
    if not args.apply:
        print(json.dumps({'status': 'replacement_preflight_passed', 'dates': [p[0] for p in pending],
                          'action': 'Run with --apply to replace attachments'}))
        return 0
    if not pending:
        for path, (_, sha) in assets.items():
            validate_png(service.get_blob_client('queue', path).download_blob().readall(), sha)
        print(json.dumps({'status': 'already_updated', 'dates': list(DATES)}))
        return 0
    job = az('containerapp', 'job', 'show', '--resource-group', GROUP, '--name', ACCOUNT)
    env = job['properties']['template']['containers'][0]['env']
    previous = next((e['value'] for e in env if e['name'] == 'PUBLISH_ENABLED'), 'false')
    changed = False
    paused = False
    completed = False
    try:
        set_enabled('false')
        paused = True
        for attempt in range(12):
            executions = az('containerapp', 'job', 'execution', 'list',
                            '--resource-group', GROUP, '--name', ACCOUNT)
            active = [e for e in executions if e.get('properties', {}).get('status')
                      not in ('Succeeded', 'Failed', 'Stopped', 'Canceled', 'Cancelled')]
            if not active:
                break
            if attempt == 11:
                raise ValueError('Active publisher execution; retry after it finishes')
            time.sleep(3)
        for path, (data, sha) in assets.items():
            blob = service.get_blob_client('queue', path)
            try:
                blob.upload_blob(data, overwrite=False, content_settings=ContentSettings(content_type='image/png'))
            except ResourceExistsError:
                pass
            validate_png(blob.download_blob().readall(), sha)
        with ExitStack() as stack:
            locks = {}
            for day, _, _, _, _ in pending:
                for target in ('personal', 'company'):
                    locks[(day, target)] = stack.enter_context(hold_state(service, day, target))
                    assert_unattempted(read_state(service, day, target, locks[(day, target)]), day, target)
            # Check every attachment before any replacement.
            ready = []
            for day, old, new, payload, blob in pending:
                props = blob.get_blob_properties()
                current = json.loads(blob.download_blob().readall())
                if check_manifest(current, old, new):
                    ready.append((day, payload, blob, props.etag))
            for day, payload, blob, etag in ready:
                for lease in locks.values():
                    lease.renew()
                changed = True
                blob.upload_blob(payload, overwrite=True, etag=etag,
                                 match_condition=MatchConditions.IfNotModified,
                                 content_settings=ContentSettings(content_type='application/json'))
                if blob.download_blob().readall() != payload:
                    raise ValueError('Replacement verification failed')
                print(json.dumps({'date': day, 'status': 'logo_attachment_updated_and_verified'}))
        completed = True
    finally:
        if paused and (completed or not changed):
            set_enabled(previous)
        elif paused:
            print(json.dumps({'status': 'publisher_left_paused',
                              'action': 'Resolve partial replacement before restoring publishing'}))
    print(json.dumps({'status': 'logo_replacements_complete', 'dates': list(DATES),
                      'publishing_setting_restored': previous}))
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({'status': 'replacement_failed', 'type': type(error).__name__,
                          'message': str(error) if isinstance(error, (ValueError, RuntimeError)) else 'Check Azure access and retry'}))
        sys.exit(1)
