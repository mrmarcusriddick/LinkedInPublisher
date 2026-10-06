import copy
import hashlib
import struct
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from app.core import process
from app.media import validate_media, validate_png, attachment_hash
from app.linkedin import LinkedIn, prepare_image, LinkedInError

DATA = b'\x89PNG\r\n\x1a\n' + b'\0\0\0\rIHDR' + struct.pack('>II', 20, 20)
SHA = hashlib.sha256(DATA).hexdigest()
IMAGE = {'path': 'assets/' + SHA + '.png', 'sha256': SHA, 'alt': 'Office illustration'}

class Store:
    def __init__(self): self.states = {}; self.keys = []
    @contextmanager
    def locked_state(self, key):
        self.keys.append(key)
        state = copy.deepcopy(self.states.get(key, {}))
        def save(s): self.states[key] = copy.deepcopy(s)
        yield state, save
    def get_asset(self, path): return DATA

class API:
    owner = 'urn:li:person:test'
    def __init__(self): self.uploads = 0; self.status = 'PROCESSING'
    def initialize(self): return {'image': 'urn:li:image:1', 'uploadUrl': 'unused'}
    def upload(self, url, data): self.uploads += 1
    def image_status(self, urn): return self.status

class Session:
    def __init__(self): self.calls = []
    def post(self, url, **kw):
        self.calls.append((url, kw))
        return type('Response', (), {'status_code': 201, 'headers': {'x-restli-id': 'urn:li:share:1'}})()
    def get(self, url, **kw):
        self.calls.append((url, kw))
        return type('Response', (), {'status_code': 200, 'json': lambda self: {'status': 'AVAILABLE'}})()

class ImageTests(unittest.TestCase):
    def test_path_and_hash_validation(self):
        validate_media({'date': '2026-10-06', 'images': {'personal': IMAGE}})
        validate_png(DATA, SHA)
        bad = dict(IMAGE, path='../../token')
        with self.assertRaises(ValueError): validate_media({'date': '2026-10-06', 'images': {'personal': bad}})
        with self.assertRaises(ValueError): validate_png(DATA + b'changed', SHA)
        with self.assertRaises(ValueError): validate_png(b'not png', SHA)
        oversized = DATA[:16] + struct.pack('>II', 99999, 99999)
        with self.assertRaises(ValueError): validate_png(oversized, hashlib.sha256(oversized).hexdigest())

    def test_ready_only_after_processing_and_no_duplicate_upload(self):
        store, api = Store(), API()
        self.assertIsNone(prepare_image(store, 'personal', IMAGE, api))
        self.assertIsNone(prepare_image(store, 'personal', IMAGE, api))
        api.status = 'AVAILABLE'
        self.assertEqual(prepare_image(store, 'personal', IMAGE, api)['id'], 'urn:li:image:1')
        prepare_image(store, 'personal', IMAGE, api)
        self.assertEqual(api.uploads, 1)
        prepare_image(store, 'company', IMAGE, api)
        self.assertEqual(api.uploads, 2)

    def test_processing_failure_blocks(self):
        store, api = Store(), API()
        prepare_image(store, 'personal', IMAGE, api)
        api.status = 'PROCESSING_FAILED'
        with self.assertRaises(ValueError): prepare_image(store, 'personal', IMAGE, api)
        with self.assertRaises(ValueError): prepare_image(store, 'personal', IMAGE, api)
        self.assertEqual(api.uploads, 1)

    def test_payload_and_personal_legacy_get(self):
        session = Session(); api = LinkedIn('test', '202609', 'urn:li:person:test', session)
        api.publish('text', {'id': 'urn:li:image:1', 'altText': 'alt'})
        body = session.calls[-1][1]['json']
        self.assertEqual(body['content']['media']['altText'], 'alt')
        self.assertEqual(body['author'], api.owner)
        api.image_status('urn:li:image:1')
        self.assertNotIn('Linkedin-Version', session.calls[-1][1]['headers'])
        api.owner = 'urn:li:organization:1'
        api.image_status('urn:li:image:1')
        self.assertEqual(session.calls[-1][1]['headers']['Linkedin-Version'], '202609')
        api.publish('text')
        self.assertNotIn('content', session.calls[-1][1]['json'])

    def test_token_never_sent_to_arbitrary_upload_host(self):
        api = LinkedIn('test', '202609', 'urn:li:person:test', Session())
        for url in ['https://evil.test/dms-uploads/a', 'https://www.linkedin.com.evil.test/dms-uploads/a',
                    'http://www.linkedin.com/dms-uploads/a', 'https://www.linkedin.com/redirect']:
            with self.assertRaises(ValueError): api.upload(url, DATA)

    def test_changed_image_and_ambiguous_post_cannot_repost(self):
        item = {'date':'2026-10-06','posts':{'personal':'A','company':'B'},'sources':['https://www.cloud2e.com/']}
        state, calls = {}, []
        now = datetime(2026,10,6,13,tzinfo=timezone.utc)
        def send(*args):
            calls.append(args)
            raise TimeoutError()
        self.assertEqual(process(item,'personal',state,lambda s: None,send,now,attachment=IMAGE),'unknown')
        self.assertEqual(process(item,'personal',state,lambda s: None,send,now,attachment=IMAGE),'unknown')
        self.assertEqual(process(item,'personal',state,lambda s: None,send,now,attachment=dict(IMAGE,alt='Changed')),'content_conflict')
        self.assertEqual(len(calls),1)
        self.assertEqual(attachment_hash('text'), hashlib.sha256(b'text').hexdigest())

class PartTests(unittest.TestCase):
    def test_reassembly_and_missing_part_failure(self):
        import tempfile
        from pathlib import Path
        from app.media import local_asset
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root/'image-parts'/SHA
            folder.mkdir(parents=True)
            (folder/'000.part').write_bytes(DATA[:12])
            (folder/'001.part').write_bytes(DATA[12:])
            self.assertEqual(local_asset(root, IMAGE), DATA)
            (folder/'000.part').unlink()
            with self.assertRaises(ValueError): local_asset(root, IMAGE)
