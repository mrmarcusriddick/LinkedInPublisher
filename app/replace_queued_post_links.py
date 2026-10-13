"""Replace approved future post text; never reset delivery state."""
import argparse
import json
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from azure.identity import AzureCliCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.core import MatchConditions
from app.core import validate, canonical
from app.replace_logo_images import (
    ACCOUNT, GROUP, az, set_enabled, hold_state, read_state, assert_unattempted
)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    plans = []
    service = BlobServiceClient(
        f'https://{ACCOUNT}.blob.core.windows.net', credential=AzureCliCredential())
    for day in ('2026-10-14', '2026-10-15'):
        old = validate(json.loads((root/'operator'/'link-original-posts'/f'{day}.json').read_text()))
        new = validate(json.loads((root/'operator'/'link-replacement-posts'/f'{day}.json').read_text()))
        if old['date'] != day or new['date'] != day:
            raise ValueError('Replacement date mismatch')
        for text in new['posts'].values():
            if not 100 <= len(text.split()) <= 180:
                raise ValueError('Post word count invalid')
        local = validate(json.loads((root/'posts'/f'{day}.json').read_text()))
        if local not in (old, new):
            raise ValueError(f'{day}: unexpected repository version')
        blob = service.get_blob_client('queue', day+'.json')
        current = json.loads(blob.download_blob().readall())
        if current not in (old, new):
            raise ValueError(f'{day}: unexpected Azure version')
        if current != new:
            if day <= datetime.now(ZoneInfo('America/New_York')).date().isoformat():
                raise ValueError(f'{day}: date is no longer in the future')
            for target in ('personal', 'company'):
                assert_unattempted(read_state(service, day, target), day, target)
        plans.append((day, old, new, blob))
    if not args.apply:
        print(json.dumps({'status':'preflight_passed','dates':[p[0] for p in plans]}))
        return
    job = az('containerapp','job','show','--resource-group',GROUP,'--name',ACCOUNT)
    env = job['properties']['template']['containers'][0]['env']
    previous = next((e.get('value') for e in env if e['name']=='PUBLISH_ENABLED'),None)
    if previous not in ('true','false'):
        raise ValueError('Cannot safely restore publishing setting')
    paused = changed = completed = False
    try:
        set_enabled('false')
        paused = True
        for attempt in range(12):
            executions = az('containerapp','job','execution','list','--resource-group',GROUP,'--name',ACCOUNT)
            active = [e for e in executions if e.get('properties',{}).get('status')
                      not in ('Succeeded','Failed','Stopped','Canceled','Cancelled')]
            if not active:
                break
            if attempt == 11:
                raise ValueError('Active publisher execution; retry later')
            time.sleep(3)
        with ExitStack() as stack:
            locks = []
            ready = []
            for day, old, new, blob in plans:
                current = json.loads(blob.download_blob().readall())
                if current == new:
                    continue
                for target in ('personal','company'):
                    lease = stack.enter_context(hold_state(service,day,target))
                    locks.append(lease)
                    assert_unattempted(read_state(service,day,target,lease),day,target)
                props = blob.get_blob_properties()
                current = json.loads(blob.download_blob().readall())
                if current != old:
                    raise ValueError(f'{day}: queue changed during preflight')
                ready.append((day,new,blob,props.etag))
            for day,new,blob,etag in ready:
                for lease in locks:
                    lease.renew()
                changed = True
                blob.upload_blob(canonical(new),overwrite=True,etag=etag,
                    match_condition=MatchConditions.IfNotModified,
                    content_settings=ContentSettings(content_type='application/json'))
                if blob.download_blob().readall() != canonical(new):
                    raise ValueError(f'{day}: verification failed')
                print(json.dumps({'date':day,'status':'post_links_updated_and_verified'}))
            for day,old,new,blob in plans:
                if blob.download_blob().readall() != canonical(new):
                    raise ValueError(f'{day}: final verification failed')
                (root/'posts'/f'{day}.json').write_text(json.dumps(new,indent=2)+'\n')
        completed = True
    finally:
        if paused and (completed or not changed):
            set_enabled(previous)
        elif paused:
            print(json.dumps({'status':'publisher_left_paused','message':'Resolve partial replacement before restoring publishing'}))
    print(json.dumps({'status':'queue_links_replaced','publishing_setting_restored':previous,
        'next_step':'Commit and push the two modified posts files to synchronize GitHub'}))

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status':'replacement_failed','type':type(error).__name__,
            'message':str(error) if isinstance(error,ValueError) else 'Azure operation failed; check access and retry'}))
        sys.exit(1)
