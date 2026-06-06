import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.asgi import app
from app.utils import utils


class TestCreatorQueueApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_root = Path(self.temp_dir.name)
        self.storage_patch = patch.object(
            utils, "storage_dir", side_effect=self._storage_dir
        )
        self.storage_patch.start()
        self.addCleanup(self.storage_patch.stop)
        self.addCleanup(self.temp_dir.cleanup)

    def _storage_dir(self, sub_dir="", create=False):
        path = self.temp_root
        if sub_dir:
            path = path / sub_dir
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _story_payload(self, title="AITA for leaving?", description="Caption"):
        return {
            "comment_card_title": title,
            "narration_script": "AITA story " * 40,
            "suggested_description": description,
            "suggested_hashtags": ["#aita", "#storytime"],
        }

    def _seed_video(self, task_id="rendered-task"):
        task_path = Path(utils.task_dir(task_id))
        (task_path / "final-1.mp4").write_bytes(b"video")
        (task_path / "story.json").write_text(
            json.dumps(self._story_payload("Rendered story", "Rendered caption")),
            encoding="utf-8",
        )
        return task_path

    def test_import_list_update_and_delete_queue_item(self):
        response = self.client.post(
            "/api/v1/creator/queue/import",
            json={"raw_json": json.dumps([self._story_payload("One"), self._story_payload("Two")])},
        )

        self.assertEqual(response.status_code, 200)
        created = response.json()["data"]["items"]
        self.assertEqual(len(created), 2)

        listed = self.client.get("/api/v1/creator/queue")
        self.assertEqual(listed.status_code, 200)
        items = listed.json()["data"]["items"]
        self.assertEqual([item["position"] for item in items], [1, 2])

        queue_id = items[0]["queue_id"]
        updated = self.client.patch(
            f"/api/v1/creator/queue/{queue_id}",
            json={"caption_text": "Custom caption"},
        )

        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["data"]["item"]["caption_text"], "Custom caption")

        deleted = self.client.delete(f"/api/v1/creator/queue/{queue_id}")

        self.assertEqual(deleted.status_code, 200)
        remaining = self.client.get("/api/v1/creator/queue").json()["data"]["items"]
        self.assertEqual(len(remaining), 1)

    def test_process_endpoint_starts_next_queued_item(self):
        self.client.post(
            "/api/v1/creator/queue/import",
            json={"raw_json": json.dumps(self._story_payload("Queued render"))},
        )

        with patch(
            "app.controllers.v1.creator.utils.get_uuid", return_value="queue-task"
        ), patch("app.controllers.v1.creator.tm.start") as start, patch(
            "app.controllers.v1.creator.task_manager.add_task"
        ) as add_task:
            response = self.client.post("/api/v1/creator/queue/process")

        self.assertEqual(response.status_code, 200)
        item = response.json()["data"]["started"]
        self.assertEqual(item["task_id"], "queue-task")
        self.assertEqual(item["status"], "rendering")
        self.assertIs(add_task.call_args.args[0], start)

    def test_direct_schedule_rejects_missing_consent_and_privacy(self):
        self.client.post(
            "/api/v1/creator/queue/import",
            json={"raw_json": json.dumps(self._story_payload())},
        )
        item = self.client.get("/api/v1/creator/queue").json()["data"]["items"][0]

        response = self.client.patch(
            f"/api/v1/creator/queue/{item['queue_id']}",
            json={
                "schedule": {
                    "run_at_epoch": time.time() + 60,
                    "action": "direct",
                    "timezone_label": "UTC",
                }
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_queue_direct_schedule_requires_tiktok_connection(self):
        self.client.post(
            "/api/v1/creator/queue/import",
            json={"raw_json": json.dumps(self._story_payload())},
        )
        item = self.client.get("/api/v1/creator/queue").json()["data"]["items"][0]

        with patch("app.controllers.v1.creator.tiktok.is_configured", return_value=True), patch(
            "app.controllers.v1.creator.tiktok.load_token_cache", return_value={}
        ):
            response = self.client.patch(
                f"/api/v1/creator/queue/{item['queue_id']}",
                json={
                    "schedule": {
                        "run_at_epoch": time.time() + 60,
                        "action": "direct",
                        "timezone_label": "UTC",
                        "privacy": "SELF_ONLY",
                        "consent_confirmed": True,
                    }
                },
            )

        self.assertEqual(response.status_code, 400)

    def test_library_video_can_be_scheduled_as_draft(self):
        self._seed_video("library-task")

        response = self.client.post(
            "/api/v1/creator/library/library-task/schedule",
            json={
                "caption_text": "Draft caption",
                "schedule": {
                    "run_at_epoch": time.time() + 60,
                    "action": "draft",
                    "timezone_label": "Asia/Manila",
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        item = response.json()["data"]["item"]
        self.assertEqual(item["task_id"], "library-task")
        self.assertEqual(item["status"], "scheduled")
        self.assertEqual(item["caption_text"], "Draft caption")
        self.assertEqual(item["schedule"]["action"], "draft")

    def test_library_direct_schedule_accepts_consent_privacy_and_connection(self):
        self._seed_video("library-direct")

        with patch("app.controllers.v1.creator.tiktok.is_configured", return_value=True), patch(
            "app.controllers.v1.creator.tiktok.load_token_cache",
            return_value={"access_token": "token"},
        ):
            response = self.client.post(
                "/api/v1/creator/library/library-direct/schedule",
                json={
                    "schedule": {
                        "run_at_epoch": time.time() + 60,
                        "action": "direct",
                        "timezone_label": "UTC",
                        "privacy": "SELF_ONLY",
                        "consent_confirmed": True,
                        "disable_comment": True,
                        "disable_duet": False,
                        "disable_stitch": True,
                        "is_aigc": True,
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        item = response.json()["data"]["item"]
        self.assertEqual(item["status"], "scheduled")
        self.assertEqual(item["schedule"]["action"], "direct")
        self.assertEqual(item["schedule"]["privacy"], "SELF_ONLY")


    def test_cancel_video_endpoint_requests_task_cancel(self):
        from app.services import task_control

        self.addCleanup(task_control.clear, "editor-task")
        response = self.client.post("/api/v1/creator/videos/editor-task/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["canceled"], "editor-task")
        self.assertTrue(task_control.is_canceled("editor-task"))

    def test_cancel_queue_item_endpoint_marks_canceled(self):
        self.client.post(
            "/api/v1/creator/queue/import",
            json={"raw_json": json.dumps(self._story_payload("Cancel me"))},
        )
        item = self.client.get("/api/v1/creator/queue").json()["data"]["items"][0]

        response = self.client.post(
            f"/api/v1/creator/queue/{item['queue_id']}/cancel"
        )

        self.assertEqual(response.status_code, 200)
        listed = self.client.get("/api/v1/creator/queue").json()["data"]["items"]
        self.assertEqual(listed[0]["status"], "canceled")

    def test_cancel_unknown_queue_item_returns_404(self):
        response = self.client.post("/api/v1/creator/queue/does-not-exist/cancel")

        self.assertEqual(response.status_code, 404)

    def test_cancel_dispatching_queue_item_returns_400(self):
        from app.services import creator_queue

        self.client.post(
            "/api/v1/creator/queue/import",
            json={"raw_json": json.dumps(self._story_payload("Dispatching"))},
        )
        item = creator_queue.list_queue_items()[0]
        item.status = "dispatching"
        creator_queue.save_queue_item(item)

        response = self.client.post(
            f"/api/v1/creator/queue/{item.queue_id}/cancel"
        )

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
