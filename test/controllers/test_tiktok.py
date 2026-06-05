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
from app.services import tiktok
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
            {"client_key": "abc", "redirect_uri": "http://cb"},
        ):
            response = self.client.get("/api/v1/tiktok/auth-url")

        self.assertEqual(response.status_code, 200)
        self.assertIn("client_key=abc", response.json()["data"]["auth_url"])

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
        finally:
            for name in ("final-1.mp4", "story.json"):
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


if __name__ == "__main__":
    unittest.main()
