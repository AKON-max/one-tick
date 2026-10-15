import unittest

from app.core.security import hash_password, verify_password


class SecurityHelpersTest(unittest.TestCase):
    def test_password_round_trip(self):
        stored = hash_password("correct horse battery staple")
        self.assertTrue(verify_password("correct horse battery staple", stored))
        self.assertFalse(verify_password("wrong password", stored))

    def test_invalid_stored_format_is_rejected(self):
        self.assertFalse(verify_password("anything", "not-a-valid-hash"))


if __name__ == "__main__":
    unittest.main()