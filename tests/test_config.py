"""Test suite verifying application configuration and security constraints."""

import unittest
from pydantic import SecretStr
from backend.app.core.config import Settings, DEFAULT_DEV_ORIGINS


class TestConfigSettings(unittest.TestCase):
    """Unit tests for configuration parsing, CORS origin policies, and secret handling."""

    def test_default_cors_origins(self):
        """Test default CORS origins use localhost development addresses."""
        settings = Settings()
        self.assertEqual(settings.ALLOWED_ORIGINS, DEFAULT_DEV_ORIGINS)
        self.assertIn("http://localhost:3000", settings.ALLOWED_ORIGINS)
        self.assertIn("http://127.0.0.1:3000", settings.ALLOWED_ORIGINS)
        self.assertTrue(settings.cors_allow_credentials)

    def test_cors_fallback_on_invalid_or_empty_input(self):
        """Test that malformed or empty origin values safely fallback to localhost origins."""
        # Test empty string fallback
        s_empty = Settings(ALLOWED_ORIGINS="")
        self.assertEqual(s_empty.ALLOWED_ORIGINS, DEFAULT_DEV_ORIGINS)

        # Test empty JSON list fallback
        s_empty_json = Settings(ALLOWED_ORIGINS="[]")
        self.assertEqual(s_empty_json.ALLOWED_ORIGINS, DEFAULT_DEV_ORIGINS)

        # Test malformed string fallback
        s_malformed = Settings(ALLOWED_ORIGINS="   ,  ")
        self.assertEqual(s_malformed.ALLOWED_ORIGINS, DEFAULT_DEV_ORIGINS)

    def test_cors_wildcard_disables_credentials(self):
        """Ensure wildcard origins automatically disable credential-enabled CORS."""
        # Explicit wildcard in list
        s_wildcard_list = Settings(ALLOWED_ORIGINS=["*"])
        self.assertFalse(s_wildcard_list.cors_allow_credentials)

        # Explicit wildcard in comma-delimited string
        s_wildcard_str = Settings(ALLOWED_ORIGINS="*")
        self.assertFalse(s_wildcard_str.cors_allow_credentials)

        # Explicit wildcard mixed with other origins
        s_wildcard_mixed = Settings(ALLOWED_ORIGINS=["http://localhost:3000", "*"])
        self.assertFalse(s_wildcard_mixed.cors_allow_credentials)

    def test_cors_custom_origins_enable_credentials(self):
        """Test that valid explicit origins keep credential-enabled CORS active."""
        s_custom = Settings(ALLOWED_ORIGINS=["https://unimind.campus.edu"])
        self.assertTrue(s_custom.cors_allow_credentials)
        self.assertEqual(s_custom.ALLOWED_ORIGINS, ["https://unimind.campus.edu"])

    def test_gemini_api_key_secret_masking(self):
        """Verify GEMINI_API_KEY is masked and never exposed in repr or str."""
        test_key = "AIzaSyDummyTestKey12345"
        settings = Settings(GEMINI_API_KEY=test_key)

        # Must be an instance of SecretStr
        self.assertIsInstance(settings.GEMINI_API_KEY, SecretStr)

        # Must NOT expose raw key in str or repr
        self.assertNotIn(test_key, str(settings.GEMINI_API_KEY))
        self.assertNotIn(test_key, repr(settings.GEMINI_API_KEY))
        self.assertIn("**********", str(settings.GEMINI_API_KEY))

        # Raw key is ONLY revealed upon explicit invocation
        self.assertEqual(settings.get_gemini_api_key(), test_key)
        self.assertEqual(settings.GEMINI_API_KEY.get_secret_value(), test_key)


if __name__ == "__main__":
    unittest.main()

