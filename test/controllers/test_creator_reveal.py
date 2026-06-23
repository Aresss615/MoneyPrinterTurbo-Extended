import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.asgi import app
from app.utils import utils


class TestCreatorRevealApi(unittest.TestCase):
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

    def test_reveal_finished_video_opens_file_manager_location(self):
        task_id = "ready-video"
        video_path = Path(utils.task_dir(task_id)) / "final-1.mp4"
        video_path.write_bytes(b"fake-video")

        with patch(
            "app.controllers.v1.creator.creator_console.reveal_path_in_file_manager"
        ) as reveal:
            response = self.client.post(f"/api/v1/creator/library/{task_id}/reveal")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["task_id"], task_id)
        self.assertEqual(data["path"], os.path.realpath(video_path))
        reveal.assert_called_once_with(os.path.realpath(video_path))

    def test_reveal_missing_finished_video_returns_404(self):
        task_id = "no-video"
        os.makedirs(utils.task_dir(task_id), exist_ok=True)

        response = self.client.post(f"/api/v1/creator/library/{task_id}/reveal")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
