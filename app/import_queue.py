import argparse
import json
import os
from pathlib import Path
from app.core import canonical, validate

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
    if not args.validate_only:
        from app.storage import Store
        store = Store(os.environ['STORAGE_ACCOUNT'])
        for item, data in items:
            print(item['date'], store.import_day(item['date'], data))
    print(f'Validated {len(items)} daily pairs')

if __name__ == '__main__':
    main()
