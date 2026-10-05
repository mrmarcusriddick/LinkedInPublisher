import unittest
from datetime import datetime, timezone
from app.core import process

class ManualTests(unittest.TestCase):
    def test_explicit_manual_run_retains_duplicate_protection(self):
        item = {'date': '2026-10-05', 'posts': {'personal': 'Test', 'company': 'Unused'},
                'sources': ['https://www.cloud2e.com/']}
        now = datetime(2026, 10, 5, 19, tzinfo=timezone.utc)
        state, sent = {}, []
        def send(target, text):
            sent.append(text)
            return {'status': 201, 'post_id': 'urn:li:share:123'}
        save = lambda value: None
        self.assertEqual(process(item, 'personal', state, save, send, now), 'outside_window')
        self.assertEqual(sent, [])
        self.assertEqual(process(item, 'personal', state, save, send, now, manual=True), 'published')
        self.assertEqual(process(item, 'personal', state, save, send, now, manual=True), 'published')
        self.assertEqual(len(sent), 1)
        state['status'] = 'sending'
        self.assertEqual(process(item, 'personal', state, save, send, now, manual=True), 'unknown')
        self.assertEqual(len(sent), 1)
