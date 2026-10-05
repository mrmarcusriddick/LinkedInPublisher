import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from app.tokens import load_target_token

class TokenTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 5, tzinfo=timezone.utc)
        self.names = []
        def get_secret(name):
            self.names.append(name)
            return SimpleNamespace(value=json.dumps({'access_token':name, 'expires_at':'2026-11-01T00:00:00+00:00'}))
        self.client = SimpleNamespace(get_secret=get_secret)
    def test_personal_uses_only_personal_token(self):
        token = load_target_token(self.client, 'personal', self.now)
        self.assertEqual(token['access_token'], 'linkedin-token-personal')
        self.assertEqual(self.names, ['linkedin-token-personal'])
    def test_company_uses_only_company_token(self):
        load_target_token(self.client, 'company', self.now)
        self.assertEqual(self.names, ['linkedin-token-company'])
    def test_missing_token_has_no_fallback(self):
        def missing(name):
            self.names.append(name)
            raise LookupError('missing')
        self.client.get_secret = missing
        with self.assertRaises(LookupError):
            load_target_token(self.client, 'company', self.now)
        self.assertEqual(self.names, ['linkedin-token-company'])
    def test_expired_token_rejected(self):
        self.now = datetime(2026, 12, 1, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            load_target_token(self.client, 'personal', self.now)

if __name__ == '__main__':
    unittest.main()
