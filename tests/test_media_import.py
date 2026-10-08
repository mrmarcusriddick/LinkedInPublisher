import copy
import json
import unittest
from app.media import media_bytes, same_media_content

class MediaImportTests(unittest.TestCase):
    def setUp(self):
        sha = 'a' * 64
        self.item = {'date': '2026-10-08', 'images': {'personal': {
            'path': f'assets/{sha}.png', 'sha256': sha, 'alt': 'Official logo'}}}
        self.name = 'media/2026-10-08.json'
        self.canonical = media_bytes(self.item)

    def test_operator_formatted_manifest_matches_without_replacement(self):
        formatted = (json.dumps(self.item, indent=2) + '\n').encode()
        self.assertNotEqual(formatted, self.canonical)
        self.assertTrue(same_media_content(self.name, formatted, self.canonical))

    def test_actual_attachment_changes_remain_immutable(self):
        for key, value in [('alt', 'Changed'), ('sha256', 'b' * 64),
                           ('path', 'assets/' + 'b' * 64 + '.png')]:
            changed = copy.deepcopy(self.item)
            changed['images']['personal'][key] = value
            self.assertFalse(same_media_content(self.name, json.dumps(changed), self.canonical))
        changed = copy.deepcopy(self.item)
        changed['images']['company'] = changed['images'].pop('personal')
        self.assertFalse(same_media_content(self.name, json.dumps(changed), self.canonical))

    def test_wrong_date_binary_post_and_malformed_data_are_rejected(self):
        for name in ['media/2026-10-09.json', '2026-10-08.json', 'assets/test.png']:
            self.assertFalse(same_media_content(name, self.canonical, self.canonical))
        for data in [b'not json', b'\xff', b'{}', b'[]',
                     self.canonical.replace(b'"date":', b'"date":"2026-10-09","date":', 1)]:
            self.assertFalse(same_media_content(self.name, data, self.canonical))
