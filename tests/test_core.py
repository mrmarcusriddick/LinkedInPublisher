import copy
import unittest
from datetime import datetime, timezone
from app.core import due_at, process, validate

class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.item = {'date':'2026-10-03','posts':{'personal':'A personal perspective.','company':'Cloud2e service guidance.'},'sources':['https://www.cloud2e.com/']}
        self.state = {}; self.saved = []; self.calls = []
        self.now = datetime(2026,10,3,13,0,tzinfo=timezone.utc)
    def save(self, state): self.saved.append(copy.deepcopy(state))
    def send(self, target, text):
        self.assertEqual(self.saved[-1]['status'], 'sending')
        self.calls.append(target)
        return {'status':201,'post_id':'urn:li:share:1'}
    def go(self, **kw):
        return process(self.item, kw.get('target','personal'), self.state, self.save, kw.get('send',self.send), kw.get('now',self.now))
    def test_dst(self):
        self.assertEqual(due_at('2026-10-03').hour,13)
        self.assertEqual(due_at('2026-11-02').hour,14)
        self.assertEqual(due_at('2027-03-15').hour,13)
    def test_due_and_once(self):
        self.assertEqual(self.go(), 'published'); self.go()
        self.assertEqual(len(self.calls),1)
    def test_before_due(self):
        self.assertEqual(self.go(now=self.now.replace(hour=12)), 'not_due'); self.assertFalse(self.calls)
    def test_late_window(self):
        self.assertEqual(self.go(now=self.now.replace(hour=14)), 'outside_window'); self.assertFalse(self.calls)
    def test_crash_does_not_retry(self):
        self.state['status']='sending'
        self.assertEqual(self.go(),'unknown'); self.assertFalse(self.calls)
    def test_timeout_does_not_retry(self):
        def fail(*args): raise TimeoutError()
        self.assertEqual(self.go(send=fail),'unknown'); self.go(); self.assertFalse(self.calls)
    def test_5xx_unknown(self): self.assertEqual(self.go(send=lambda *_:{'status':503}),'unknown')
    def test_missing_id_unknown(self): self.assertEqual(self.go(send=lambda *_:{'status':201}),'unknown')
    def test_401_blocks(self): self.assertEqual(self.go(send=lambda *_:{'status':401}),'blocked')
    def test_rate_limit_backoff(self):
        self.assertEqual(self.go(send=lambda *_:{'status':429,'retry_after':600}),'queued')
        self.assertEqual(self.go(),'waiting_retry')
        self.assertEqual(self.go(now=self.now.replace(minute=10)),'published')
    def test_changed_content_cannot_repost(self):
        self.go(); self.item['posts']['personal']='Changed text'
        self.assertEqual(self.go(),'content_conflict'); self.assertEqual(len(self.calls),1)
    def test_separate_target_records(self):
        self.go(); self.state={}; self.go(target='company')
        self.assertEqual(self.calls,['personal','company'])
    def test_invalid_posts(self):
        self.item['posts']['company']='x'*3001
        with self.assertRaises(ValueError): validate(self.item)

if __name__=='__main__': unittest.main()
