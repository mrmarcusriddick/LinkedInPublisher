import argparse, json, time
from pathlib import Path
from datetime import datetime, timezone
from azure.identity import AzureCliCredential
from azure.keyvault.secrets import SecretClient
from app.tokens import load_target_token
from app.storage import Store
from app.linkedin import LinkedIn, prepare_image
from app.media import validate_media, local_asset
from app.core import process
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--publish',action='store_true')
    args=p.parse_args()
    item=json.loads((Path(__file__).resolve().parents[1]/'manual/2026-10-13-tracker/post.json').read_text())
    if not args.publish:
        print(item['posts']['personal'])
        return
    credential=AzureCliCredential()
    vault=SecretClient(vault_url='https://c2ea2e23015.vault.azure.net',credential=credential)
    auth=load_target_token(vault,'personal',datetime.now(timezone.utc))
    api=LinkedIn(auth['access_token'],'202609','urn:li:person:ntXyHnLoeu')
    store=Store('c2ea2e23015',credential=credential)
    root=Path(__file__).resolve().parents[1]
    media=validate_media(json.loads((root/'manual/2026-10-13-tracker/media.json').read_text()))
    attachment=media['images']['personal']
    store.get_asset=lambda path:local_asset(root,attachment)
    image=None
    for attempt in range(6):
        image=prepare_image(store,'personal',attachment,api)
        if image: break
        if attempt<5: time.sleep(3)
    if not image:
        print(json.dumps({'status':'image_processing','action':'Run again shortly; no post sent'}))
        raise SystemExit(1)
    with store.locked_state('manual-personal-tracker-2026-10-13-v1') as (state,save):
        status=process(item,'personal',state,save,lambda target,text:api.publish(text,image),datetime.now(timezone.utc),manual=True,attachment=attachment)
        result={'status':status}
        if state.get('post_id'):
            result['url']='https://www.linkedin.com/feed/update/'+state['post_id']+'/'
        if state.get('reason'): result['reason']=state['reason']
        print(json.dumps(result))
        if status!='published': raise SystemExit(1)
if __name__=='__main__':
    try: main()
    except Exception as error:
        print(json.dumps({'status':'publish_failed','type':type(error).__name__}))
        raise SystemExit(1)
