import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.asgi import app
from app.utils import utils


class TestCreatorConsoleApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _storage_dir_factory(self, root: Path):
        def storage_dir(sub_dir="", create=False):
            path = root
            if sub_dir:
                path = path / sub_dir
            if create:
                path.mkdir(parents=True, exist_ok=True)
            return str(path)

        return storage_dir

    def test_get_idea_prompt_returns_reddit_workflow_prompt(self):
        response = self.client.get("/api/v1/creator/idea-prompt")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertIn("Reddit", data["prompt"])
        # Retention-first markers: niche territories, length lanes, verdict CTA.
        self.assertIn("length_lane", data["prompt"])
        self.assertIn("comment_prompt", data["prompt"])
        self.assertIn("NTA or YTA?", data["prompt"])
        self.assertIn("170-260 words", data["prompt"])

    def test_get_idea_prompt_injects_recent_story_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.object(
                utils, "storage_dir", side_effect=self._storage_dir_factory(temp_root)
            ):
                task_path = Path(utils.task_dir("used-story"))
                (task_path / "story.json").write_text(
                    json.dumps(
                        {
                            "source_url": "https://www.reddit.com/r/AITA/comments/used/story",
                            "comment_card_title": "AITA for refusing the family loan?",
                            "narration_script": "I refused the family loan after my brother lied. " * 12,
                        }
                    ),
                    encoding="utf-8",
                )

                response = self.client.get("/api/v1/creator/idea-prompt")

        self.assertEqual(response.status_code, 200)
        prompt = response.json()["data"]["prompt"]
        self.assertIn("Do not reuse these stories/topics/sources", prompt)
        self.assertIn("Every new ChatGPT chat is stateless", prompt)
        self.assertIn("AITA for refusing the family loan?", prompt)
        self.assertIn("https://www.reddit.com/r/AITA/comments/used/story", prompt)

    def test_get_status_reports_webserver_and_bot_connection(self):
        response = self.client.get("/api/v1/creator/status")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertTrue(data["webserver_connected"])
        self.assertTrue(data["bot_connected"])
        self.assertEqual(data["bot_status"], "ready")
        self.assertIn("gameplay_ready", data["checks"])

    def test_validate_story_returns_duration_and_guardrail_status(self):
        response = self.client.post(
            "/api/v1/creator/validate",
            json={
                "narration_script": " ".join(["word"] * 187),
                "comment_card_title": "AITA for refusing to switch seats?",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["estimated_seconds"], 68)
        self.assertEqual(data["word_count"], 187)
        self.assertTrue(data["meets_minimum_duration"])
        self.assertEqual(data["story"]["comment_card_title"], "AITA for refusing to switch seats?")

    def test_import_chatgpt_accepts_smart_quote_fenced_json(self):
        response = self.client.post(
            "/api/v1/creator/import-chatgpt",
            json={
                "raw_json": """
````
{
“source_url”: “https://www.reddit.com/r/AmItheAsshole/comments/example/”,
“subreddit”: “r/AmItheAsshole”,
“comment_card_username”: “u/throwaway_aita”,
“comment_card_title”: “AITA for refusing to hand over wedding photos?”,
“comment_card_likes”: “99+”,
“video_subject”: “Wedding photographer drama”,
“narration_script”: “I deleted an entire wedding album over one meal. The groom told me I was there to work, not eat.”,
“caption_keywords_to_highlight”: [“wedding”, “photographer”, “deleted photos”],
“suggested_hashtags”: [“#AITA”, “RedditStories”],
“content_notes”: “Paraphrased and anonymized.”
}
````
""",
            },
        )

        self.assertEqual(response.status_code, 200)
        story = response.json()["data"]["story"]
        self.assertEqual(story["comment_card_title"], "AITA for refusing to hand over wedding photos?")
        self.assertEqual(story["suggested_hashtags"], ["#AITA", "#RedditStories"])

    def test_import_chatgpt_warns_on_duplicate_title_source_and_script(self):
        script = "I refused the family loan after my brother lied. " * 12
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.object(
                utils, "storage_dir", side_effect=self._storage_dir_factory(temp_root)
            ):
                task_path = Path(utils.task_dir("used-story"))
                (task_path / "story.json").write_text(
                    json.dumps(
                        {
                            "source_url": "https://www.reddit.com/r/AITA/comments/used/story",
                            "comment_card_title": "AITA for refusing the family loan?",
                            "narration_script": script,
                        }
                    ),
                    encoding="utf-8",
                )

                response = self.client.post(
                    "/api/v1/creator/import-chatgpt",
                    json={
                        "raw_json": json.dumps(
                            {
                                "source_url": "https://www.reddit.com/r/AITA/comments/used/story",
                                "comment_card_title": "AITA for refusing the family loan?",
                                "narration_script": script,
                            }
                        )
                    },
                )

        self.assertEqual(response.status_code, 200)
        warnings = response.json()["data"]["warnings"]
        self.assertTrue(any("source" in warning.lower() for warning in warnings))
        self.assertTrue(any("title" in warning.lower() for warning in warnings))
        self.assertTrue(any("script" in warning.lower() for warning in warnings))

    def test_validate_story_warns_on_duplicate_title_from_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.object(
                utils, "storage_dir", side_effect=self._storage_dir_factory(temp_root)
            ):
                queue_root = Path(utils.storage_dir("creator_queue", create=True))
                (queue_root / "queued.json").write_text(
                    json.dumps(
                        {
                            "queue_id": "queued",
                            "story": {
                                "comment_card_title": "AITA for canceling dinner?",
                                "narration_script": "I canceled dinner after everyone ignored me. " * 12,
                            },
                            "caption_text": "",
                            "status": "queued",
                            "position": 1,
                            "created_at": 1,
                            "updated_at": 1,
                        }
                    ),
                    encoding="utf-8",
                )

                response = self.client.post(
                    "/api/v1/creator/validate",
                    json={
                        "comment_card_title": "AITA for canceling dinner?",
                        "narration_script": "A different script about dinner. " * 40,
                    },
                )

        self.assertEqual(response.status_code, 200)
        warnings = response.json()["data"]["warnings"]
        self.assertTrue(any("title" in warning.lower() for warning in warnings))

    def test_import_chatgpt_invalid_json_returns_400(self):
        response = self.client.post(
            "/api/v1/creator/import-chatgpt",
            json={"raw_json": "{not json"},
        )

        self.assertEqual(response.status_code, 400)

    def test_create_creator_video_submits_task_with_creator_defaults(self):
        with patch("app.controllers.v1.creator.tm.start") as start:
            with patch("app.controllers.v1.creator.task_manager.add_task") as add_task:
                response = self.client.post(
                    "/api/v1/creator/videos",
                    json={
                        "narration_script": "AITA for refusing to switch seats? " * 30,
                        "comment_card_title": "AITA for refusing to switch seats?",
                        "comment_card_username": "u/throwaway_plane",
                    },
                )

        self.assertEqual(response.status_code, 200)
        task = response.json()["data"]
        self.assertIn("task_id", task)
        add_task.assert_called_once()
        self.assertIs(add_task.call_args.args[0], start)
        params = add_task.call_args.kwargs["params"]
        self.assertEqual(params.min_video_duration, 60)
        self.assertEqual(params.comment_card_username, "u/throwaway_plane")


if __name__ == "__main__":
    unittest.main()
