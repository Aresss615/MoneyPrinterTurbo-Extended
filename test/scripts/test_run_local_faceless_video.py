import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class TestRunLocalFacelessVideo(unittest.TestCase):
    def test_build_video_params_uses_local_chatterbox_defaults(self):
        from scripts import run_local_faceless_video as runner

        params = runner.build_video_params("  AITA for labeling my leftovers?  ")

        self.assertEqual(params.video_script, "AITA for labeling my leftovers?")
        self.assertEqual(params.voice_name, "chatterbox:default:Default Voice-Neutral")
        self.assertEqual(params.video_source, "local")
        self.assertEqual(params.video_aspect, "9:16")
        self.assertEqual(params.video_concat_mode, "sequential")
        self.assertEqual(params.bgm_type, "")
        self.assertTrue(params.subtitle_enabled)
        self.assertTrue(params.enable_word_highlighting)
        self.assertEqual(len(params.video_materials), 1)
        self.assertEqual(params.video_materials[0].provider, "local")
        self.assertTrue(params.video_materials[0].url.endswith("gameplay/minecraft-parkour-1.mp4"))

    def test_build_video_params_enables_reddit_card_and_center_captions(self):
        from scripts import run_local_faceless_video as runner

        params = runner.build_video_params(
            "AITA for labeling my leftovers? My roommate kept eating them."
        )

        self.assertEqual(params.subtitle_position, "center")
        self.assertTrue(params.comment_card_enabled)
        self.assertEqual(params.comment_card_username, runner.DEFAULT_CARD_USERNAME)
        # Card title is the opening question only, not the whole story.
        self.assertEqual(params.comment_card_title, "AITA for labeling my leftovers?")

    def test_derive_card_title_takes_first_sentence(self):
        from scripts import run_local_faceless_video as runner

        self.assertEqual(
            runner.derive_card_title("AITA for X? Then more text here."),
            "AITA for X?",
        )
        self.assertEqual(
            runner.derive_card_title("My neighbor parked in my spot. I was mad."),
            "My neighbor parked in my spot.",
        )

    def test_main_calls_existing_task_pipeline_and_prints_json_result(self):
        from scripts import run_local_faceless_video as runner

        fake_result = {
            "videos": [str(ROOT_DIR / "storage/tasks/unit-task/final-1.mp4")],
            "subtitle_path": str(ROOT_DIR / "storage/tasks/unit-task/subtitle.srt"),
        }

        with patch.object(runner.task_service, "start", return_value=fake_result) as start:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = runner.main(
                    [
                        "--story",
                        "AITA for telling my roommate to stop eating my food?",
                        "--task-id",
                        "unit-task",
                    ]
                )

        self.assertEqual(exit_code, 0)
        start.assert_called_once()
        self.assertEqual(start.call_args.kwargs["task_id"], "unit-task")
        self.assertEqual(start.call_args.kwargs["stop_at"], "video")
        self.assertEqual(
            start.call_args.kwargs["params"].video_materials[0].url,
            str(ROOT_DIR / "gameplay/minecraft-parkour-1.mp4"),
        )

        output = json.loads(stdout.getvalue())
        self.assertEqual(output["task_id"], "unit-task")
        self.assertEqual(output["task_dir"], str(ROOT_DIR / "storage/tasks/unit-task"))
        self.assertEqual(output["videos"], fake_result["videos"])
        self.assertEqual(output["subtitle_path"], fake_result["subtitle_path"])


if __name__ == "__main__":
    unittest.main()
