import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _ok(payload: dict) -> MagicMock:
    """Build a successful Graph API response."""
    resp = MagicMock()
    resp.json.return_value = payload
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    return resp


def _err(code: int, message: str) -> MagicMock:
    """Build a failed Graph API response."""
    resp = MagicMock()
    resp.json.return_value = {
        "error": {
            "code": code,
            "message": message,
            "type": "OAuthException",
            "fbtrace_id": "test-trace-id",
        }
    }
    resp.status_code = 400
    resp.raise_for_status.return_value = None
    return resp


class TestFacebookTokenCache(unittest.TestCase):
    def test_save_and_load_round_trip(self):
        from app.services import facebook

        with tempfile.TemporaryDirectory() as tmp:
            token_path = os.path.join(tmp, "facebook_token.json")
            with patch.object(facebook, "_token_path", return_value=token_path):
                saved = facebook.save_token_cache("12345", "EAAtest_token_abc")
                loaded = facebook.load_token_cache()

        self.assertEqual(saved["page_id"], "12345")
        self.assertEqual(saved["page_access_token"], "EAAtest_token_abc")
        self.assertEqual(loaded["page_id"], "12345")
        self.assertEqual(loaded["page_access_token"], "EAAtest_token_abc")

    def test_load_returns_empty_when_no_file_and_no_config(self):
        from app.services import facebook

        with tempfile.TemporaryDirectory() as tmp:
            token_path = os.path.join(tmp, "missing.json")
            with (
                patch.object(facebook, "_token_path", return_value=token_path),
                patch.object(facebook, "_cfg_page_id", return_value=""),
                patch.object(facebook, "_cfg_page_access_token", return_value=""),
            ):
                result = facebook.load_token_cache()

        self.assertEqual(result, {})

    def test_load_falls_back_to_config_when_no_file(self):
        from app.services import facebook

        with tempfile.TemporaryDirectory() as tmp:
            token_path = os.path.join(tmp, "missing.json")
            with (
                patch.object(facebook, "_token_path", return_value=token_path),
                patch.object(facebook, "_cfg_page_id", return_value="99999"),
                patch.object(
                    facebook,
                    "_cfg_page_access_token",
                    return_value="EAAfromconfig",
                ),
            ):
                result = facebook.load_token_cache()

        self.assertEqual(result["page_id"], "99999")
        self.assertEqual(result["page_access_token"], "EAAfromconfig")

    def test_get_valid_access_token_raises_when_not_configured(self):
        from app.services import facebook

        with tempfile.TemporaryDirectory() as tmp:
            token_path = os.path.join(tmp, "missing.json")
            with (
                patch.object(facebook, "_token_path", return_value=token_path),
                patch.object(facebook, "_cfg_page_id", return_value=""),
                patch.object(facebook, "_cfg_page_access_token", return_value=""),
            ):
                with self.assertRaises(facebook.FacebookError):
                    facebook.get_valid_access_token()

    def test_get_valid_access_token_returns_values_from_cache(self):
        from app.services import facebook

        with tempfile.TemporaryDirectory() as tmp:
            token_path = os.path.join(tmp, "facebook_token.json")
            with open(token_path, "w") as fp:
                json.dump(
                    {"page_id": "777", "page_access_token": "EAAvalid", "saved_at": 0},
                    fp,
                )
            with patch.object(facebook, "_token_path", return_value=token_path):
                pid, tok = facebook.get_valid_access_token()

        self.assertEqual(pid, "777")
        self.assertEqual(tok, "EAAvalid")


class TestFacebookCheckResponse(unittest.TestCase):
    def test_raises_on_error_payload(self):
        from app.services import facebook

        resp = _err(190, "Invalid OAuth access token.")
        with self.assertRaises(facebook.FacebookError) as ctx:
            facebook._check_response(resp)
        self.assertIn("190", str(ctx.exception))

    def test_returns_payload_on_success(self):
        from app.services import facebook

        resp = _ok({"id": "12345678901234567"})
        result = facebook._check_response(resp)
        self.assertEqual(result["id"], "12345678901234567")


class TestFacebookGetPageInfo(unittest.TestCase):
    def test_calls_graph_api_with_correct_params(self):
        from app.services import facebook

        with patch("app.services.facebook.requests.get", return_value=_ok({"id": "111", "name": "My Page"})) as mock_get:
            info = facebook.get_page_info(page_id="111", access_token="EAAabc")

        self.assertEqual(info["name"], "My Page")
        call_kwargs = mock_get.call_args
        self.assertIn("111", call_kwargs.args[0])
        self.assertEqual(call_kwargs.kwargs["params"]["access_token"], "EAAabc")


class TestFacebookPostVideo(unittest.TestCase):
    def test_raises_when_file_missing(self):
        from app.services import facebook

        with self.assertRaises(facebook.FacebookError):
            facebook.post_video(
                "/nonexistent/video.mp4",
                page_id="111",
                access_token="EAA",
            )

    def test_posts_multipart_with_correct_fields(self):
        from app.services import facebook

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 100)
            tmp_path = f.name

        try:
            mock_resp = _ok({"id": "video-id-123"})
            with patch(
                "app.services.facebook.requests.post", return_value=mock_resp
            ) as mock_post:
                result = facebook.post_video(
                    tmp_path,
                    description="Test caption",
                    title="My Video",
                    published=True,
                    page_id="1251924241531028",
                    access_token="EAAtest",
                )
        finally:
            os.unlink(tmp_path)

        self.assertEqual(result["id"], "video-id-123")
        call_kwargs = mock_post.call_args
        posted_data = call_kwargs.kwargs["data"]
        self.assertEqual(posted_data["access_token"], "EAAtest")
        self.assertEqual(posted_data["published"], "true")
        self.assertEqual(posted_data["description"], "Test caption")
        self.assertEqual(posted_data["title"], "My Video")
        self.assertIn("source", call_kwargs.kwargs["files"])

    def test_published_false_sends_false_string(self):
        from app.services import facebook

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 50)
            tmp_path = f.name

        try:
            with patch(
                "app.services.facebook.requests.post",
                return_value=_ok({"id": "draft-id"}),
            ) as mock_post:
                facebook.post_video(
                    tmp_path,
                    published=False,
                    page_id="111",
                    access_token="EAA",
                )
        finally:
            os.unlink(tmp_path)

        data = mock_post.call_args.kwargs["data"]
        self.assertEqual(data["published"], "false")

    def test_raises_on_api_error(self):
        from app.services import facebook

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 50)
            tmp_path = f.name

        try:
            with patch(
                "app.services.facebook.requests.post",
                return_value=_err(200, "Permissions error"),
            ):
                with self.assertRaises(facebook.FacebookError):
                    facebook.post_video(tmp_path, page_id="111", access_token="EAA")
        finally:
            os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()
