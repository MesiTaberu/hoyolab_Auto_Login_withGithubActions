import os
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import redeem_codes  # noqa: E402


class FakeResponse:
    def __init__(self, payload=None, *, status_code=200, text=""):
        self.payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class RedeemCodeTests(unittest.TestCase):
    def test_redeem_login_required_is_fatal(self):
        profile = redeem_codes.RedeemProfile(
            "Genshin Impact",
            "https://example.invalid/redeem",
            "hk4e_global",
            "123456789",
            "os_asia",
            ["TESTCODE1"],
        )
        response = FakeResponse({"retcode": -1071, "message": "先にアカウントへログインしてください"})

        with patch.dict(os.environ, {"HOYOVERSE_COOKIE": "cookie_token_v2=x"}, clear=True):
            with patch("redeem_codes.requests.get", return_value=response):
                result = redeem_codes.redeem_code(profile, "TESTCODE1")

        self.assertFalse(result["ok"])
        self.assertTrue(result["fatal"])

    def test_already_used_japanese_messages_are_ok(self):
        self.assertTrue(redeem_codes.is_already_used_message("キャンペーンコードは既に使用されました"))
        self.assertTrue(redeem_codes.is_already_used_message("既に当該シリアルコードは使用されています"))

    def test_hoyolab_search_non_json_returns_empty(self):
        response = FakeResponse(ValueError("not json"), text="<html>limited</html>")

        with patch.dict(os.environ, {"REDEEM_HOYOLAB_ENABLED": "true"}, clear=True):
            with patch("redeem_codes.requests.get", return_value=response):
                with redirect_stdout(StringIO()):
                    codes = redeem_codes.fetch_codes_from_hoyolab(redeem_codes.SUPPORTED_GAMES["genshin"])

        self.assertEqual(codes, [])

    def test_missing_auth_fails_before_profile_resolution(self):
        with patch.dict(os.environ, {}, clear=True):
            with redirect_stdout(StringIO()):
                self.assertFalse(redeem_codes.validate_environment())

    def test_explicit_profile_with_hoyoverse_cookie_passes_without_hoyolab_cookie(self):
        env = {
            "HOYOVERSE_COOKIE": "cookie_token_v2=x; account_id_v2=1",
            "GENSHIN_UID": "123456789",
            "GENSHIN_REGION": "os_asia",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertTrue(redeem_codes.validate_environment())


if __name__ == "__main__":
    unittest.main()
