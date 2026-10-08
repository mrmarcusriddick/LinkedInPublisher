import unittest
from app.replace_logo_images import assert_unattempted, check_manifest, failure_details

class LogoReplacementTests(unittest.TestCase):
    def test_diagnostics_exclude_response_body_and_credentials(self):
        class AzureError(Exception):
            status_code = 403
            error_code = 'AuthorizationPermissionMismatch'
        details = failure_details(AzureError('secret signed URL'))
        self.assertEqual(details['http_status'], 403)
        self.assertEqual(details['azure_code'], 'AuthorizationPermissionMismatch')
        self.assertNotIn('secret', str(details))

    def test_attempted_delivery_is_never_reset(self):
        for state in ({'status': 'published'}, {'status': 'sending'},
                      {'status': 'unknown'}, {'status': 'blocked'},
                      {'status': 'queued', 'content_hash': 'a'}, {'attempted_at': 'now'}):
            with self.assertRaises(ValueError):
                assert_unattempted(state, '2026-10-07', 'personal')
        assert_unattempted({}, '2026-10-07', 'personal')

    def test_only_known_attachment_can_be_replaced(self):
        old, new = {'image': 'old'}, {'image': 'new'}
        self.assertTrue(check_manifest(old, old, new))
        self.assertFalse(check_manifest(new, old, new))
        with self.assertRaises(ValueError):
            check_manifest({'image': 'unexpected'}, old, new)
