"""Package an original PNG into small lossless GitHub-transfer parts."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.media import validate_png
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('image', type=Path)
parser.add_argument('--alt', required=True)
args = parser.parse_args()
data = args.image.read_bytes()
sha = hashlib.sha256(data).hexdigest()
validate_png(data, sha)
if not 1 <= len(args.alt.strip()) <= 1000:
    parser.error('Provide alt text of 1-1000 characters')
folder = ROOT/'image-parts'/sha
folder.mkdir(parents=True, exist_ok=True)
parts = []
for i, offset in enumerate(range(0, len(data), 196608)):
    part = folder/f'{i:03}.part'
    chunk = data[offset:offset+196608]
    if part.exists() and part.read_bytes() != chunk:
        raise ValueError('Existing image part differs')
    part.write_bytes(chunk)
    parts.append(str(part.relative_to(ROOT)))
print(json.dumps({'image': {'path': f'assets/{sha}.png', 'sha256': sha, 'alt': args.alt},
                  'parts': parts}, indent=2))
