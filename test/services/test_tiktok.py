import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _ok(data):
    """Build a TikTok API response envelope with a success error block."""
    resp = MagicMock()
    resp.json.return_value = {"data": data, "error": {"code": "ok", "message": ""}}
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    return resp


class TestTikTokService(unittest.TestCase):
    def test_assemble_title_appends_inline_hashtags(self):
        from app.services import tiktok

        title = tiktok.assemble_title(
            "Window seat drama", ["aita", "#redditstories", "story time"]
        )

        self.assertEqual(
            title, "Window seat drama #aita #redditstories #storytime"
        )

    def test_assemble_title_handles_missing_pieces(self):
        from app.services import tiktok

        self.assertEqual(tiktok.assemble_title("", []), "")
        self.assertEqual(tiktok.assemble_title("Just a caption", None), "Just a caption")

    def test_build_authorize_url_includes_scopes_and_state(self):
        from app.services import tiktok

        with patch.object(
            tiktok.config,
            "tiktok",
            {"client_key": "abc", "redirect_uri": "https://dev.example.com/cb"},
        ):
            url = tiktok.build_authorize_url("xyz-state")

        self.assertIn("client_key=abc", url)
        self.assertIn("scope=video.publish", url)
        self.assertIn("state=xyz-state", url)
        self.assertIn("response_type=code", url)
        self.assertIn("redirect_uri=https%3A%2F%2Fdev.example.com%2Fcb", url)

    def test_build_upload_plan_splits_current_89mb_outputs(self):
        from app.services import tiktok

        plan = tiktok.build_upload_plan(89 * 1024 * 1024)

        self.assertEqual(plan["total_chunk_count"], 2)
        self.assertGreaterEqual(plan["chunk_size"], tiktok.MIN_CHUNK_SIZE)
        self.assertLessEqual(plan["chunk_size"], tiktok.MAX_CHUNK_SIZE)

    def test_build_upload_plan_uses_single_chunk_at_64mb_boundary(self):
        from app.services import tiktok

        plan = tiktok.build_upload_plan(tiktok.MAX_CHUNK_SIZE)

        self.assertEqual(
            plan,
            {
                "video_size": tiktok.MAX_CHUNK_SIZE,
                "chunk_size": tiktok.MAX_CHUNK_SIZE,
                "total_chunk_count": 1,
            },
        )

    def test_get_valid_access_token_refreshes_when_expired(self):
        from app.services import tiktok

        cache = {
            "access_token": "old",
            "refresh_token": "refresh-1",
            "expires_at": time.time() - 10,  # expired
            "open_id": "open-1",
        }
        refreshed = _ok(None)
        refreshed.json.return_value = {
            "access_token": "new",
            "refresh_token": "refresh-2",
            "expires_in": 86400,
            "refresh_expires_in": 8640000,
            "open_id": "open-1",
        }

        saved = {}
        with patch.object(tiktok, "load_token_cache", return_value=cache), patch.object(
            tiktok, "save_token_cache", side_effect=lambda d: saved.update(d)
        ), patch.object(
            tiktok.config,
            "tiktok",
            {"client_key": "k", "client_secret": "s"},
        ), patch.object(
            tiktok.requests, "post", return_value=refreshed
        ) as post:
            token = tiktok.get_valid_access_token()

        self.assertEqual(token, "new")
        self.assertEqual(post.call_args.args[0], tiktok.OAUTH_TOKEN_URL)
        self.assertEqual(saved["access_token"], "new")
        self.assertEqual(saved["refresh_token"], "refresh-2")

    def test_get_valid_access_token_uses_cached_when_fresh(self):
        from app.services import tiktok

        cache = {
            "access_token": "still-good",
            "refresh_token": "r",
            "expires_at": time.time() + 9999,
        }
        with patch.object(tiktok, "load_token_cache", return_value=cache), patch.object(
            tiktok.requests, "post"
        ) as post:
            token = tiktok.get_valid_access_token()

        self.assertEqual(token, "still-good")
        post.assert_not_called()

    def test_publish_video_runs_init_upload_status_sequence(self):
        from app.services import tiktok

        init_resp = _ok({"publish_id": "pub-1", "upload_url": "https://upload"})
        status_resp = _ok({"status": "PUBLISH_COMPLETE", "publish_id": "pub-1"})
        put_resp = MagicMock(status_code=201)
        put_resp.raise_for_status.return_value = None

        with patch.object(tiktok.os.path, "isfile", return_value=True), patch.object(
            tiktok.os.path, "getsize", return_value=2048
        ), patch.object(
            tiktok, "_iter_video_chunks", return_value=[(0, 2047, b"x" * 2048)]
        ), patch.object(
            tiktok.config,
            "tiktok",
            {"privacy_level": "SELF_ONLY", "cover_timestamp_ms": 1000},
        ), patch.object(
            tiktok.requests, "post", side_effect=[init_resp, status_resp]
        ) as post, patch.object(
            tiktok.requests, "put", return_value=put_resp
        ) as put:
            result = tiktok.publish_video(
                "/tmp/final.mp4",
                title="My caption #aita",
                access_token="tok",
                poll_interval=0,
            )

        # init then status
        self.assertEqual(post.call_args_list[0].args[0], tiktok.PUBLISH_INIT_URL)
        self.assertEqual(post.call_args_list[1].args[0], tiktok.PUBLISH_STATUS_URL)
        # init body carries caption + privacy + FILE_UPLOAD source
        init_body = post.call_args_list[0].kwargs["json"]
        self.assertEqual(init_body["post_info"]["title"], "My caption #aita")
        self.assertEqual(init_body["post_info"]["privacy_level"], "SELF_ONLY")
        self.assertEqual(init_body["source_info"]["source"], "FILE_UPLOAD")
        self.assertEqual(init_body["source_info"]["video_size"], 2048)
        self.assertEqual(init_body["source_info"]["total_chunk_count"], 1)
        # bytes uploaded to the returned url
        put.assert_called_once()
        self.assertEqual(put.call_args.args[0], "https://upload")
        # terminal result surfaced
        self.assertEqual(result["status"], "PUBLISH_COMPLETE")
        self.assertEqual(result["publish_id"], "pub-1")

    def test_publish_video_uploads_large_video_in_sequential_chunks(self):
        from app.services import tiktok

        video_size = 89 * 1024 * 1024
        plan = tiktok.build_upload_plan(video_size)
        init_resp = _ok({"publish_id": "pub-2", "upload_url": "https://upload"})
        put_resp = MagicMock(status_code=206)
        put_resp.raise_for_status.return_value = None
        chunks = [
            (0, plan["chunk_size"] - 1, b"first"),
            (plan["chunk_size"], video_size - 1, b"second"),
        ]

        with patch.object(tiktok.os.path, "isfile", return_value=True), patch.object(
            tiktok.os.path, "getsize", return_value=video_size
        ), patch.object(
            tiktok, "_iter_video_chunks", return_value=chunks
        ), patch.object(
            tiktok.config, "tiktok", {"privacy_level": "SELF_ONLY"}
        ), patch.object(
            tiktok.requests, "post", return_value=init_resp
        ) as post, patch.object(
            tiktok.requests, "put", return_value=put_resp
        ) as put:
            result = tiktok.publish_video(
                "/tmp/final.mp4", title="t", access_token="tok", poll=False
            )

        init_body = post.call_args.kwargs["json"]
        self.assertEqual(init_body["source_info"]["video_size"], video_size)
        self.assertEqual(init_body["source_info"]["chunk_size"], plan["chunk_size"])
        self.assertEqual(init_body["source_info"]["total_chunk_count"], 2)
        self.assertEqual(put.call_count, 2)
        self.assertEqual(
            put.call_args_list[0].kwargs["headers"]["Content-Range"],
            f"bytes 0-{plan['chunk_size'] - 1}/{video_size}",
        )
        self.assertEqual(
            put.call_args_list[1].kwargs["headers"]["Content-Range"],
            f"bytes {plan['chunk_size']}-{video_size - 1}/{video_size}",
        )
        self.assertEqual(result["status"], "PROCESSING_UPLOAD")

    def test_publish_video_raises_on_api_error(self):
        from app.services import tiktok

        err = MagicMock()
        err.json.return_value = {
            "data": {},
            "error": {"code": "invalid_params", "message": "bad request"},
        }
        err.status_code = 400
        err.raise_for_status.return_value = None

        with patch.object(tiktok.os.path, "isfile", return_value=True), patch.object(
            tiktok.os.path, "getsize", return_value=1
        ), patch.object(
            tiktok, "_iter_video_chunks", return_value=[(0, 0, b"x")]
        ), patch.object(tiktok.config, "tiktok", {}), patch.object(
            tiktok.requests, "post", return_value=err
        ):
            with self.assertRaises(tiktok.TikTokError):
                tiktok.publish_video("/tmp/final.mp4", title="t", access_token="tok")


if __name__ == "__main__":
    unittest.main()
