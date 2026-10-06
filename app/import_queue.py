import argparse
import json
import os
from pathlib import Path
from app.core import canonical, validate
from app.media import validate_media, media_bytes, validate_png, local_asset

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('directory', nargs='?', default='posts')
    args = parser.parse_args()
    items = []
    for path in sorted(Path(args.directory).glob('*.json')):
        item = validate(json.loads(path.read_text()))
        if path.name != item['date'] + '.json':
            raise ValueError('Filename must match item date')
        items.append((item, canonical(item)))
    attachments = []
    assets = {}
    root = Path(args.directory).resolve().parent
    dates = {item['date'] for item, _ in items}
    for path in sorted((root / 'media').glob('*.json')):
        media = validate_media(json.loads(path.read_text()))
        if path.name != media['date'] + '.json' or media['date'] not in dates:
            raise ValueError('Media must match an existing post date')
        for image in media['images'].values():
            data = local_asset(root, image)
            assets[image['path']] = data
        attachments.append((path.name, media_bytes(media)))
    if not args.validate_only:
        from app.storage import Store
        store = Store(os.environ['STORAGE_ACCOUNT'])
        for name, data in assets.items():
            print(name, store.import_blob(name, data, 'image/png'))
        for name, data in attachments:
            print('media/' + name, store.import_blob('media/' + name, data, 'application/json'))
        for item, data in items:
            print(item['date'], store.import_day(item['date'], data))
    print(f'Validated {len(items)} daily pairs, {len(attachments)} image attachments, {len(assets)} assets')

if __name__ == '__main__':
    main()
