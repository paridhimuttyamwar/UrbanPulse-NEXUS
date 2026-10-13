"""
Regression tests for Streamlit Cloud st.secrets fallback and os.environ precedence.
Verifies:
1. os.environ takes precedence over st.secrets when both are present.
2. st.secrets flat keys fallback when os.environ is absent.
3. st.secrets nested [tidb] section fallback when os.environ is absent.
4. Graceful handling when Streamlit or st.secrets is unavailable.
5. Strict cloud mode enforcement.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from config.settings import Settings, _get_config_value


class TestStreamlitSecretsRegression(unittest.TestCase):
    def setUp(self):
        # Save original environment
        self._orig_env = os.environ.copy()
        # Clean test keys from environ
        for k in ["URBANPULSE_ENV", "TIDB_HOST", "TIDB_PORT", "TIDB_USER", "TIDB_PASSWORD", "TIDB_DATABASE"]:
            os.environ.pop(k, None)

    def tearDown(self):
        # Restore original environment
        os.environ.clear()
        os.environ.update(self._orig_env)

    def test_os_environ_precedence_over_streamlit_secrets(self):
        """When both os.environ and st.secrets are present, os.environ must win."""
        os.environ["URBANPULSE_ENV"] = "cloud"
        os.environ["TIDB_HOST"] = "gateway.env-host.tidbcloud.com"
        os.environ["TIDB_PORT"] = "4000"

        mock_st = MagicMock()
        mock_st.secrets = {
            "URBANPULSE_ENV": "local",
            "TIDB_HOST": "gateway.secrets-host.tidbcloud.com",
            "TIDB_PORT": 5000,
        }

        with patch.dict(sys.modules, {"streamlit": mock_st}):
            s = Settings()
            self.assertEqual(s.URBANPULSE_ENV, "cloud")
            self.assertEqual(s.TIDB_HOST, "gateway.env-host.tidbcloud.com")
            self.assertEqual(s.TIDB_PORT, 4000)

    def test_streamlit_secrets_flat_keys_fallback(self):
        """When os.environ is empty, values should resolve from flat st.secrets."""
        mock_st = MagicMock()
        mock_st.secrets = {
            "URBANPULSE_ENV": "cloud",
            "TIDB_HOST": "gateway01.us-east-1.prod.aws.tidbcloud.com",
            "TIDB_PORT": 4000,
            "TIDB_USER": "testuser.root",
            "TIDB_PASSWORD": "secretpassword",
            "TIDB_DATABASE": "urbanpulse_cloud",
        }

        with patch.dict(sys.modules, {"streamlit": mock_st}):
            s = Settings()
            self.assertEqual(s.URBANPULSE_ENV, "cloud")
            self.assertTrue(s.is_cloud)
            self.assertEqual(s.TIDB_HOST, "gateway01.us-east-1.prod.aws.tidbcloud.com")
            self.assertEqual(s.TIDB_PORT, 4000)
            self.assertEqual(s.TIDB_USER, "testuser.root")
            self.assertEqual(s.TIDB_PASSWORD, "secretpassword")
            self.assertEqual(s.TIDB_DATABASE, "urbanpulse_cloud")

    def test_streamlit_secrets_nested_tidb_fallback(self):
        """When secrets use nested [tidb] section in TOML, resolve subkeys."""
        mock_st = MagicMock()
        mock_st.secrets = {
            "URBANPULSE_ENV": "cloud",
            "tidb": {
                "host": "gateway-nested.tidbcloud.com",
                "port": 4000,
                "user": "nested_user",
                "password": "nested_password",
                "database": "nested_db",
            },
        }

        with patch.dict(sys.modules, {"streamlit": mock_st}):
            s = Settings()
            self.assertEqual(s.URBANPULSE_ENV, "cloud")
            self.assertEqual(s.TIDB_HOST, "gateway-nested.tidbcloud.com")
            self.assertEqual(s.TIDB_PORT, 4000)
            self.assertEqual(s.TIDB_USER, "nested_user")
            self.assertEqual(s.TIDB_PASSWORD, "nested_password")
            self.assertEqual(s.TIDB_DATABASE, "nested_db")

    def test_graceful_handling_without_streamlit(self):
        """When streamlit is not installed or raises ImportError, defaults apply."""
        with patch.dict(sys.modules, {"streamlit": None}):
            s = Settings()
            self.assertEqual(s.URBANPULSE_ENV, "local")
            self.assertFalse(s.is_cloud)
            self.assertEqual(s.TIDB_HOST, "")
            self.assertEqual(s.TIDB_PORT, 4000)
            self.assertEqual(s.TIDB_DATABASE, "urbanpulse")

    def test_strict_cloud_mode_prohibits_localhost(self):
        """Cloud mode must never permit localhost."""
        mock_st = MagicMock()
        mock_st.secrets = {
            "URBANPULSE_ENV": "cloud",
            "TIDB_HOST": "localhost",
            "TIDB_USER": "testuser",
            "TIDB_PASSWORD": "secretpassword",
        }

        with patch.dict(sys.modules, {"streamlit": mock_st}):
            s = Settings()
            self.assertTrue(s.is_cloud)
            self.assertIn(s.TIDB_HOST.lower(), ["localhost", "127.0.0.1"])
            # Verification: our database connection layer rejects localhost in cloud mode
            from database.connection import get_db_connection
            with patch("database.connection.settings", s):
                with self.assertRaises(ValueError) as ctx:
                    with get_db_connection():
                        pass
                self.assertIn("prohibits connecting to localhost", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
