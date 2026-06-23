import json
import os
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


class TestCreatorLibraryApi(unittest.TestCase):
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

    def _seed_video(
        self,
        task_id,
        title="AITA for leaving?",
        age_days=0,
        posted=False,
        size=10,
    ):
        task_path = Path(utils.task_dir(task_id))
        video_path = task_path / "final-1.mp4"
        video_path.write_bytes(b"x" * size)
        (task_path / "story.json").write_text(
            json.dumps(
                {
                    "comment_card_title": title,
                    "narration_script": "AITA story " * 20,
                    "suggested_description": "Caption text",
                    "suggested_hashtags": ["#aita", "#storytime"],
                    "narrator_gender": "female",
                }
            ),
            encoding="utf-8",
        )
        if posted:
            (task_path / "publish.json").write_text(
                json.dumps(
                    {
                        "method": "direct",
                        "status": "PUBLISH_COMPLETE",
                        "publish_id": "pub-1",
                        "posted_at": time.time(),
                    }
                ),
                encoding="utf-8",
            )
        created_at = time.time() - age_days * 86400
        os.utime(video_path, (created_at, created_at))
        return task_path

    def test_get_library_returns_seeded_videos(self):
        self._seed_video("older", title="Older story", age_days=2, size=11)
        self._seed_video("newer", title="Newer story", age_days=0, posted=True, size=13)

        response = self.client.get("/api/v1/creator/library")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["total_size_bytes"], 24)
        self.assertEqual([video["task_id"] for video in data["videos"]], ["newer", "older"])
        self.assertEqual(data["videos"][0]["display_name"], "Newer story")
        self.assertEqual(data["videos"][0]["posted"]["method"], "direct")
        self.assertEqual(
            data["videos"][0]["publish_status"]["tiktok"]["method"], "direct"
        )
        self.assertEqual(data["videos"][0]["publish_status"]["facebook"], {})
        self.assertEqual(data["videos"][0]["publish_status"]["instagram"], {})
        self.assertEqual(data["videos"][0]["publish_status"]["youtube"], {})
        self.assertEqual(data["videos"][1]["video_url"], "/tasks/older/final-1.mp4")

    def test_delete_library_video_removes_dir_and_rejects_invalid_paths(self):
        task_path = self._seed_video("delete-me")

        response = self.client.delete("/api/v1/creator/library/delete-me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["deleted"], "delete-me")
        self.assertFalse(task_path.exists())

        missing = self.client.delete("/api/v1/creator/library/no-such-task")
        traversal = self.client.delete("/api/v1/creator/library/%2E%2E")

        self.assertEqual(missing.status_code, 404)
        self.assertEqual(traversal.status_code, 404)

    def test_cleanup_deletes_only_old_unposted_videos_and_supports_dry_run(self):
        self._seed_video("old-unposted", age_days=10, size=5)
        self._seed_video("old-posted", age_days=10, posted=True, size=7)
        self._seed_video("new-unposted", age_days=1, size=9)

        dry_run = self.client.post(
            "/api/v1/creator/library/cleanup",
            json={"older_than_days": 7, "dry_run": True},
        )

        self.assertEqual(dry_run.status_code, 200)
        self.assertEqual(dry_run.json()["data"]["deleted"], ["old-unposted"])
        self.assertTrue(Path(utils.task_dir("old-unposted")).exists())

        response = self.client.post(
            "/api/v1/creator/library/cleanup",
            json={"older_than_days": 7, "dry_run": False},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["deleted"], ["old-unposted"])
        self.assertEqual(data["freed_bytes"], 5)
        self.assertFalse((self.temp_root / "tasks" / "old-unposted").exists())
        self.assertTrue((self.temp_root / "tasks" / "old-posted").exists())
        self.assertTrue((self.temp_root / "tasks" / "new-unposted").exists())

    def test_regenerate_starts_new_task_from_stored_story_with_voice_override(self):
        self._seed_video("source-task", title="Regenerate me")

        with patch(
            "app.controllers.v1.creator.utils.get_uuid", return_value="new-task"
        ), patch("app.controllers.v1.creator.tm.start") as start, patch(
            "app.controllers.v1.creator.task_manager.add_task"
        ) as add_task:
            response = self.client.post(
                "/api/v1/creator/library/source-task/regenerate",
                json={"narrator_gender": "male"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["task_id"], "new-task")
        add_task.assert_called_once()
        self.assertIs(add_task.call_args.args[0], start)
        self.assertTrue(
            Path(utils.task_dir("new-task"), "story.json").is_file()
        )
        story = json.loads(Path(utils.task_dir("new-task"), "story.json").read_text())
        self.assertEqual(story["comment_card_title"], "Regenerate me")
        self.assertEqual(story["narrator_gender"], "female")
        self.assertEqual(story["narrator_gender_override"], "male")
        self.assertTrue(add_task.call_args.kwargs["params"].voice_name.endswith("-Male"))


if __name__ == "__main__":
    unittest.main()
