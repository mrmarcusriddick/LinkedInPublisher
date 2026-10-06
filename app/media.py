"""Immutable content-addressed PNG attachments."""
import hashlib
import json
import re
import struct
from datetime import date
MAX_BYTES = 8 * 1024 * 1024

def validate_media(item):
    if set(item) != {'date', 'images'} or date.fromisoformat(item['date']).isoformat() != item['date']:
        raise ValueError('Expected date and images')
    if not item['images'] or not set(item['images']) <= {'personal', 'company'}:
        raise ValueError('Unknown image target')
    for image in item['images'].values():
        if set(image) != {'path', 'sha256', 'alt'}:
            raise ValueError('Expected path, sha256 and alt')
        if not re.fullmatch('[0-9a-f]{64}', image['sha256']):
            raise ValueError('Invalid image hash')
        if image['path'] != 'assets/' + image['sha256'] + '.png':
            raise ValueError('Image path must be content addressed')
        if not isinstance(image['alt'], str) or not 1 <= len(image['alt'].strip()) <= 1000:
            raise ValueError('Image requires alt text')
    return item

def media_bytes(item):
    return json.dumps(validate_media(item), sort_keys=True, ensure_ascii=False).encode()

def validate_png(data, expected_hash):
    if not 24 <= len(data) <= MAX_BYTES or data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
        raise ValueError('Expected PNG under 8 MiB')
    width, height = struct.unpack('>II', data[16:24])
    if not width or not height or width * height >= 36152320:
        raise ValueError('Invalid image dimensions')
    if hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError('Image checksum mismatch')
    return data

def attachment_hash(text, attachment=None):
    value = text if attachment is None else json.dumps({'text': text, 'image': attachment}, sort_keys=True)
    return hashlib.sha256(value.encode()).hexdigest()

def local_asset(root, image):
    """Load a PNG directly or reassemble small binary GitHub transfer parts."""
    from pathlib import Path
    root = Path(root).resolve()
    path = (root / image['path']).resolve()
    if not path.is_relative_to(root / 'assets'):
        raise ValueError('Asset path escapes repository')
    if path.exists():
        if path.stat().st_size > MAX_BYTES:
            raise ValueError('Image too large')
        return validate_png(path.read_bytes(), image['sha256'])
    folder = root / 'image-parts' / image['sha256']
    parts = sorted(folder.glob('*.part'))
    if not parts or len(parts) > 64:
        raise ValueError('Image parts missing or excessive')
    if [p.name for p in parts] != [f'{i:03}.part' for i in range(len(parts))]:
        raise ValueError('Image parts must be contiguous')
    total = 0
    data = []
    for part in parts:
        if not part.resolve().is_relative_to(root / 'image-parts'):
            raise ValueError('Image part escapes repository')
        total += part.stat().st_size
        if total > MAX_BYTES:
            raise ValueError('Image too large')
        data.append(part.read_bytes())
    return validate_png(b''.join(data), image['sha256'])
