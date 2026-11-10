import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.server import access_token


class AccessTokenTests(unittest.TestCase):
    def test_six_digits_preserve_leading_zero_and_survive_restart(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.dict(os.environ, {"CS211_ACCESS_TOKEN": ""}), \
                patch("backend.server.secrets.randbelow", return_value=42) as random:
            root = Path(folder) / "runs"
            self.assertEqual(access_token(root), "000042")
            self.assertEqual(access_token(root), "000042")
            random.assert_called_once_with(1_000_000)

    def test_custom_token_overrides_without_replacing_saved_code(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".access-token").write_text("123456\n")
            with patch.dict(os.environ, {"CS211_ACCESS_TOKEN": "custom-secret"}):
                self.assertEqual(access_token(root), "custom-secret")
            self.assertEqual((root / ".access-token").read_text(), "123456\n")

    def test_corrupt_saved_code_is_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.dict(os.environ, {"CS211_ACCESS_TOKEN": ""}):
            root = Path(folder)
            (root / ".access-token").write_text("invalid")
            with self.assertRaises(ValueError):
                access_token(root)
