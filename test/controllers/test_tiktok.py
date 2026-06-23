import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.asgi import app
from app.services import creator_console, tiktok
from app.utils import utils


class TestTikTokApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_status_reports_configured_and_connection(self):
        with patch.object(tiktok, "is_configured", return_value=True), patch.object(
            tiktok, "load_token_cache", return_value={}
        ):
            response = self.client.get("/api/v1/tiktok/status")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertTrue(data["configured"])
        self.assertFalse(data["connected"])

    def test_auth_url_returns_authorize_link_when_configured(self):
        with patch.object(
            tiktok.config,
            "tiktok",
            {"client_key": "abc", "redirect_uri": "https://dev.example.com/cb"},
        ), patch.object(
            tiktok, "save_oauth_state", create=True
        ) as save_state, patch(
            "app.controllers.v1.tiktok.utils.get_uuid", return_value="state-1"
        ):
            response = self.client.get("/api/v1/tiktok/auth-url")

        self.assertEqual(response.status_code, 200)
        self.assertIn("client_key=abc", response.json()["data"]["auth_url"])
        self.assertIn("state=state-1", response.json()["data"]["auth_url"])
        save_state.assert_called_once_with("state-1")

    def test_auth_url_returns_400_when_not_configured(self):
        with patch.object(tiktok.config, "tiktok", {}):
            response = self.client.get("/api/v1/tiktok/auth-url")

        self.assertEqual(response.status_code, 400)

    def test_publish_returns_404_when_video_missing(self):
        response = self.client.post(
            "/api/v1/tiktok/publish", json={"task_id": "no-such-task-xyz"}
        )

        self.assertEqual(response.status_code, 404)

    def test_publish_uses_story_metadata_fallback_for_caption(self):
        task_id = "tiktok-publish-test"
        task_path = Path(utils.task_dir(task_id))
        (task_path / "final-1.mp4").write_bytes(b"fake-video")
        with open(task_path / "story.json", "w", encoding="utf-8") as fp:
            json.dump(
                {
                    "narration_script": "AITA story",
                    "suggested_description": "Window seat drama",
                    "suggested_hashtags": ["#aita", "#redditstories"],
                },
                fp,
            )

        try:
            with patch.object(
                tiktok,
                "publish_video",
                return_value={"status": "PUBLISH_COMPLETE", "publish_id": "p1"},
            ) as publish:
                response = self.client.post(
                    "/api/v1/tiktok/publish", json={"task_id": task_id}
                )
                marker = creator_console.load_publish_marker(task_id)
        finally:
            for name in ("final-1.mp4", "story.json", "publish.json"):
                try:
                    os.remove(task_path / name)
                except OSError:
                    pass

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"], "PUBLISH_COMPLETE")
        publish.assert_called_once()
        self.assertEqual(publish.call_args.kwargs["description"], "Window seat drama")
        self.assertEqual(
            publish.call_args.kwargs["hashtags"], ["#aita", "#redditstories"]
        )
        self.assertEqual(marker["method"], "direct")
        self.assertEqual(marker["status"], "PUBLISH_COMPLETE")
        self.assertEqual(marker["publish_id"], "p1")

    def test_status_surfaces_user_info_display_name(self):
        with patch.object(tiktok, "is_configured", return_value=True), patch.object(
            tiktok, "load_token_cache", return_value={"access_token": "tok"}
        ), patch.object(
            tiktok, "query_user_info", return_value={"display_name": "Jules"}
        ), patch.object(
            tiktok, "query_creator_info", return_value={}
        ):
            response = self.client.get("/api/v1/tiktok/status")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertTrue(data["connected"])
        self.assertEqual(data["nickname"], "Jules")
        self.assertEqual(data["user_info"]["display_name"], "Jules")

    def test_status_hides_connected_account_without_creator_access_key(self):
        with patch.object(tiktok.config, "app", {"creator_access_key": "owner"}), patch.object(
            tiktok, "is_configured", return_value=True
        ), patch.object(
            tiktok, "load_token_cache", return_value={"access_token": "tok"}
        ), patch.object(tiktok, "query_user_info") as query_user_info, patch.object(
            tiktok, "query_creator_info"
        ) as query_creator_info:
            response = self.client.get("/api/v1/tiktok/status")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertTrue(data["configured"])
        self.assertTrue(data["locked"])
        self.assertFalse(data["connected"])
        self.assertEqual(data["nickname"], "")
        query_user_info.assert_not_called()
        query_creator_info.assert_not_called()

    def test_auth_url_requires_creator_access_key_when_configured(self):
        with patch.object(tiktok.config, "app", {"creator_access_key": "owner"}), patch.object(
            tiktok.config,
            "tiktok",
            {"client_key": "abc", "redirect_uri": "https://dev.example.com/cb"},
        ), patch.object(tiktok, "save_oauth_state", create=True) as save_state:
            response = self.client.get("/api/v1/tiktok/auth-url")

        self.assertEqual(response.status_code, 401)
        save_state.assert_not_called()

    def test_publish_requires_creator_access_key_when_configured(self):
        task_id = "tiktok-publish-locked"
        task_path = Path(utils.task_dir(task_id))
        (task_path / "final-1.mp4").write_bytes(b"fake-video")

        try:
            with patch.object(
                tiktok.config, "app", {"creator_access_key": "owner"}
            ), patch.object(
                tiktok,
                "publish_video",
                return_value={"status": "PUBLISH_COMPLETE", "publish_id": "p1"},
            ) as publish:
                response = self.client.post(
                    "/api/v1/tiktok/publish", json={"task_id": task_id}
                )
        finally:
            try:
                os.remove(task_path / "final-1.mp4")
            except OSError:
                pass

        self.assertEqual(response.status_code, 401)
        publish.assert_not_called()

    def test_upload_inbox_returns_404_when_video_missing(self):
        response = self.client.post(
            "/api/v1/tiktok/upload-inbox", json={"task_id": "no-such-task-xyz"}
        )

        self.assertEqual(response.status_code, 404)

    def test_upload_inbox_sends_finished_video(self):
        task_id = "tiktok-inbox-test"
        task_path = Path(utils.task_dir(task_id))
        (task_path / "final-1.mp4").write_bytes(b"fake-video")
        try:
            with patch.object(
                tiktok,
                "upload_video_to_inbox",
                return_value={"status": "PUBLISH_COMPLETE", "publish_id": "inbox-1"},
            ) as upload:
                response = self.client.post(
                    "/api/v1/tiktok/upload-inbox", json={"task_id": task_id}
                )
                marker = creator_console.load_publish_marker(task_id)
        finally:
            try:
                os.remove(task_path / "final-1.mp4")
            except OSError:
                pass
            try:
                os.remove(task_path / "publish.json")
            except OSError:
                pass

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"], "PUBLISH_COMPLETE")
        upload.assert_called_once()
        self.assertTrue(upload.call_args.args[0].endswith("final-1.mp4"))
        self.assertEqual(marker["method"], "inbox")
        self.assertEqual(marker["status"], "PUBLISH_COMPLETE")
        self.assertEqual(marker["publish_id"], "inbox-1")

    def test_upload_inbox_requires_creator_access_key_when_configured(self):
        task_id = "tiktok-inbox-locked"
        task_path = Path(utils.task_dir(task_id))
        (task_path / "final-1.mp4").write_bytes(b"fake-video")
        try:
            with patch.object(
                tiktok.config, "app", {"creator_access_key": "owner"}
            ), patch.object(
                tiktok,
                "upload_video_to_inbox",
                return_value={"status": "PUBLISH_COMPLETE", "publish_id": "inbox-1"},
            ) as upload:
                response = self.client.post(
                    "/api/v1/tiktok/upload-inbox", json={"task_id": task_id}
                )
        finally:
            try:
                os.remove(task_path / "final-1.mp4")
            except OSError:
                pass

        self.assertEqual(response.status_code, 401)
        upload.assert_not_called()

    def test_callback_rejects_invalid_oauth_state(self):
        with patch.object(
            tiktok, "consume_oauth_state", return_value=False, create=True
        ), patch.object(tiktok, "exchange_code_for_token") as exchange:
            response = self.client.get(
                "/api/v1/tiktok/callback?code=abc&state=invalid-state"
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("invalid OAuth state", response.text)
        exchange.assert_not_called()

    def test_callback_exchanges_code_when_oauth_state_is_valid(self):
        with patch.object(
            tiktok, "consume_oauth_state", return_value=True, create=True
        ), patch.object(
            tiktok, "exchange_code_for_token", return_value={"open_id": "open-1"}
        ) as exchange:
            response = self.client.get(
                "/api/v1/tiktok/callback?code=abc&state=valid-state"
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("TikTok connected", response.text)
        exchange.assert_called_once_with("abc")

    def test_serves_tiktok_site_verification_file_under_callback_path(self):
        response = self.client.get(
            "/api/v1/tiktok/callback/"
            "tiktokWLly7x9cmPv0wlZyHy99pbIPzg458GTc.txt"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.text.strip(),
            "tiktok-developers-site-verification=WLly7x9cmPv0wlZyHy99pbIPzg458GTc",
        )
        self.assertIn("text/plain", response.headers["content-type"])

    def test_serves_tiktok_privacy_page(self):
        response = self.client.get("/api/v1/tiktok/privacy")

        self.assertEqual(response.status_code, 200)
        self.assertIn("JC Video Factory Privacy Policy", response.text)

    def test_serves_tiktok_site_verification_file_under_privacy_path(self):
        response = self.client.get(
            "/api/v1/tiktok/privacy/"
            "tiktoklxPM3j6HLE0ELdYGQtKiUBRk3zcaNktU.txt"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.text.strip(),
            "tiktok-developers-site-verification=lxPM3j6HLE0ELdYGQtKiUBRk3zcaNktU",
        )
        self.assertIn("text/plain", response.headers["content-type"])

    def test_serves_tiktok_site_verification_file_under_terms_path(self):
        response = self.client.get(
            "/api/v1/tiktok/terms/"
            "tiktokmrsQ4Koe9viUCunfDTI0E7veX4Ls1i8H.txt"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.text.strip(),
            "tiktok-developers-site-verification=mrsQ4Koe9viUCunfDTI0E7veX4Ls1i8H",
        )
        self.assertIn("text/plain", response.headers["content-type"])

    def test_publish_passes_tiktok_publish_controls(self):
        task_id = "tiktok-publish-controls"
        task_path = Path(utils.task_dir(task_id))
        (task_path / "final-1.mp4").write_bytes(b"fake-video")

        try:
            with patch.object(
                tiktok,
                "publish_video",
                return_value={"status": "PROCESSING_UPLOAD", "publish_id": "p2"},
            ) as publish:
                response = self.client.post(
                    "/api/v1/tiktok/publish",
                    json={
                        "task_id": task_id,
                        "privacy": "SELF_ONLY",
                        "disable_comment": True,
                        "disable_duet": True,
                        "disable_stitch": False,
                        "brand_content_toggle": False,
                        "brand_organic_toggle": False,
                        "is_aigc": True,
                    },
                )
        finally:
            try:
                os.remove(task_path / "final-1.mp4")
            except OSError:
                pass

        self.assertEqual(response.status_code, 200)
        self.assertTrue(publish.call_args.kwargs["disable_comment"])
        self.assertTrue(publish.call_args.kwargs["disable_duet"])
        self.assertFalse(publish.call_args.kwargs["disable_stitch"])
        self.assertFalse(publish.call_args.kwargs["brand_content_toggle"])
        self.assertFalse(publish.call_args.kwargs["brand_organic_toggle"])
        self.assertTrue(publish.call_args.kwargs["is_aigc"])


if __name__ == "__main__":
    unittest.main()
