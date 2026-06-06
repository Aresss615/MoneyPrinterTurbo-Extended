import json
import os
import random
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class TestCreatorConsole(unittest.TestCase):
    def test_estimate_read_seconds_uses_short_form_tts_pace(self):
        from app.services import creator_console

        script = " ".join(["word"] * 187)

        self.assertEqual(creator_console.estimate_read_seconds(script), 68)

    def test_parse_chatgpt_story_json_normalizes_fields(self):
        from app.services import creator_console

        raw_json = json.dumps(
            {
                "source_url": "https://www.reddit.com/r/AmItheAsshole/example",
                "subreddit": "AmItheAsshole",
                "comment_card_username": "u/example",
                "comment_card_title": "AITA for keeping the window seat?",
                "narration_script": "AITA for keeping the seat I paid for? " * 20,
                "caption_keywords_to_highlight": ["window seat", "paid extra", 42],
                "suggested_description": "Window seat drama",
                "suggested_hashtags": ["#aita", "drama", "travel"],
                "content_notes": "Anonymized.",
                "narrator_gender": "female",
            }
        )

        story = creator_console.parse_chatgpt_story_json(raw_json)

        self.assertEqual(story.source_url, "https://www.reddit.com/r/AmItheAsshole/example")
        self.assertEqual(story.subreddit, "AmItheAsshole")
        self.assertEqual(story.comment_card_username, "u/example")
        self.assertEqual(story.comment_card_title, "AITA for keeping the window seat?")
        self.assertEqual(story.caption_keywords_to_highlight, ["window seat", "paid extra"])
        self.assertEqual(story.suggested_hashtags, ["#aita", "#drama", "#travel"])
        self.assertEqual(story.narrator_gender, "female")

    def test_parse_chatgpt_story_json_accepts_smart_quotes_and_code_fence(self):
        from app.services import creator_console

        raw_json = """
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
"""

        story = creator_console.parse_chatgpt_story_json(raw_json)

        self.assertEqual(
            story.source_url,
            "https://www.reddit.com/r/AmItheAsshole/comments/example/",
        )
        self.assertEqual(
            story.comment_card_title,
            "AITA for refusing to hand over wedding photos?",
        )
        self.assertEqual(story.caption_keywords_to_highlight, ["wedding", "photographer", "deleted photos"])
        self.assertEqual(story.suggested_hashtags, ["#AITA", "#RedditStories"])

    def test_parse_chatgpt_story_json_repairs_unescaped_dialogue_quotes(self):
        from app.services import creator_console

        # Unescaped inner double quotes (dialogue) are exactly what breaks
        # strict json.loads with "Expecting ',' delimiter".
        raw_json = (
            '{\n'
            '  "subreddit": "AmItheAsshole",\n'
            '  "comment_card_title": "AITA for leaving?",\n'
            '  "narration_script": "He looked at me and said "you are wrong", '
            'then he said "leave now" and walked off.",\n'
            '  "caption_keywords_to_highlight": ["wrong", "leave"]\n'
            '}'
        )

        story = creator_console.parse_chatgpt_story_json(raw_json)

        self.assertIn('"you are wrong"', story.narration_script)
        self.assertIn('"leave now"', story.narration_script)
        self.assertEqual(story.subreddit, "AmItheAsshole")
        self.assertEqual(story.caption_keywords_to_highlight, ["wrong", "leave"])

    def test_parse_chatgpt_story_json_repairs_raw_newlines_and_trailing_commas(self):
        from app.services import creator_console

        raw_json = (
            '{\n'
            '  "comment_card_title": "AITA?",\n'
            '  "narration_script": "First line.\nSecond line.\nThird line.",\n'
            '  "suggested_hashtags": ["#aita", "#reddit",],\n'
            '}'
        )

        story = creator_console.parse_chatgpt_story_json(raw_json)

        self.assertEqual(story.narration_script, "First line. Second line. Third line.")
        self.assertEqual(story.suggested_hashtags, ["#aita", "#reddit"])

    def test_parse_chatgpt_story_json_raises_friendly_error_on_garbage(self):
        from app.services import creator_console

        with self.assertRaises(ValueError) as ctx:
            creator_console.parse_chatgpt_story_json("this is not json at all {")

        self.assertIn("Could not parse the pasted JSON", str(ctx.exception))

    def test_build_video_params_enforces_personal_faceless_defaults(self):
        from app.services import creator_console

        story = creator_console.CreatorStory(
            narration_script="AITA for refusing to switch seats? " * 30,
            comment_card_title="AITA for refusing to switch seats?",
            comment_card_username="u/throwaway_plane",
            comment_card_likes="12.4k",
        )

        params = creator_console.build_video_params(story)

        self.assertEqual(params.video_source, "local")
        self.assertEqual(params.video_aspect, "9:16")
        self.assertEqual(params.video_concat_mode, "sequential")
        self.assertEqual(params.video_clip_duration, 5)
        self.assertEqual(params.min_video_duration, 60)
        self.assertEqual(params.subtitle_position, "center")
        self.assertFalse(params.text_background_color)
        self.assertEqual(params.font_name, "Montserrat-ExtraBold.ttf")
        self.assertEqual(params.font_size, 64)
        self.assertEqual(params.stroke_width, 3)
        self.assertTrue(params.comment_card_enabled)
        self.assertEqual(params.comment_card_title, "AITA for refusing to switch seats?")
        self.assertEqual(params.comment_card_username, "u/throwaway_plane")
        self.assertEqual(params.comment_card_likes, "12.4k")
        self.assertEqual(len(params.video_materials), 1)
        discovered = {str(p) for p in creator_console.list_background_sources()}
        self.assertIn(params.video_materials[0].url, discovered)

    def test_list_background_sources_filters_videos_and_hidden_files(self):
        from app.services import creator_console

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            (tmp_dir / "parkour.mp4").write_bytes(b"x")
            (tmp_dir / "subway.MOV").write_bytes(b"x")
            (tmp_dir / ".hidden.mp4").write_bytes(b"x")
            (tmp_dir / "notes.txt").write_bytes(b"x")
            (tmp_dir / "nested").mkdir()

            with patch.object(creator_console, "GAMEPLAY_DIR", tmp_dir):
                sources = creator_console.list_background_sources()

        self.assertEqual([p.name for p in sources], ["parkour.mp4", "subway.MOV"])

    def test_list_background_sources_returns_empty_when_dir_missing(self):
        from app.services import creator_console

        missing = Path(tempfile.gettempdir()) / "definitely-not-a-gameplay-dir-xyz"
        with patch.object(creator_console, "GAMEPLAY_DIR", missing):
            self.assertEqual(creator_console.list_background_sources(), [])

    def test_pick_background_material_uses_rng_choice(self):
        from app.services import creator_console

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            (tmp_dir / "a.mp4").write_bytes(b"x")
            (tmp_dir / "b.mp4").write_bytes(b"x")

            with patch.object(creator_console, "GAMEPLAY_DIR", tmp_dir):
                material = creator_console.pick_background_material(rng=random.Random(0))

        self.assertEqual(material.provider, "local")
        self.assertIn(Path(material.url).name, {"a.mp4", "b.mp4"})

    def test_pick_background_material_raises_when_empty(self):
        from app.services import creator_console

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(creator_console, "GAMEPLAY_DIR", Path(tmp)):
                with self.assertRaises(FileNotFoundError):
                    creator_console.pick_background_material()

    def test_pick_voice_returns_pool_member(self):
        from app.services import creator_console

        self.assertIn(creator_console.pick_voice(rng=random.Random(3)), creator_console.VOICE_POOL)

    def test_pick_voice_filters_by_narrator_gender(self):
        from app.services import creator_console

        self.assertTrue(
            creator_console.pick_voice(rng=random.Random(0), gender="female").endswith(
                "-Female"
            )
        )
        self.assertTrue(
            creator_console.pick_voice(rng=random.Random(0), gender="male").endswith(
                "-Male"
            )
        )
        self.assertIn(
            creator_console.pick_voice(rng=random.Random(0), gender=""),
            creator_console.VOICE_POOL,
        )

    def test_pick_voice_falls_back_to_full_pool_without_matching_gender(self):
        from app.services import creator_console

        with patch.object(creator_console, "VOICE_POOL", ["en-US-AvaNeural-Female"]):
            self.assertEqual(
                creator_console.pick_voice(rng=random.Random(0), gender="male"),
                "en-US-AvaNeural-Female",
            )

    def test_slugify_builds_safe_download_name(self):
        from app.services import creator_console

        self.assertEqual(
            creator_console.slugify("AITA for leaving my sister's wedding?"),
            "aita-for-leaving-my-sister-s-wedding",
        )
        self.assertEqual(creator_console.slugify("!!!"), "video")
        self.assertLessEqual(len(creator_console.slugify("word " * 40)), 60)

    def test_build_video_params_rotates_source_and_voice_from_pool(self):
        from app.services import creator_console

        story = creator_console.CreatorStory(
            narration_script="AITA for refusing to switch seats? " * 30,
        )

        params = creator_console.build_video_params(story, rng=random.Random(7))

        discovered = {str(p) for p in creator_console.list_background_sources()}
        self.assertIn(params.video_materials[0].url, discovered)
        self.assertIn(params.voice_name, creator_console.VOICE_POOL)

    def test_build_video_params_uses_story_narrator_gender_for_voice(self):
        from app.services import creator_console

        story = creator_console.CreatorStory(
            narration_script="AITA for refusing to switch seats? " * 30,
            narrator_gender="female",
        )

        params = creator_console.build_video_params(story, rng=random.Random(7))

        self.assertTrue(params.voice_name.endswith("-Female"))

    def test_resolve_narrator_gender_prefers_explicit_field(self):
        from app.services import creator_console

        story = creator_console.CreatorStory(
            narration_script="My wife and I argued about the dishes. " * 20,
            narrator_gender="female",
        )

        self.assertEqual(creator_console.resolve_narrator_gender(story), "female")

    def test_resolve_narrator_gender_reads_reddit_self_tags(self):
        from app.services import creator_console

        female = creator_console.CreatorStory(
            narration_script="I (28F) finally told my sister the truth. " * 10,
        )
        male = creator_console.CreatorStory(
            narration_script="So I (30m) got kicked off the flight. " * 10,
        )
        spaced = creator_console.CreatorStory(
            narration_script="My brother M 41 refused to apologize. " * 10,
        )
        prefix = creator_console.CreatorStory(
            narration_script="As the oldest, F23 here, I had enough. " * 10,
        )

        self.assertEqual(creator_console.resolve_narrator_gender(female), "female")
        self.assertEqual(creator_console.resolve_narrator_gender(male), "male")
        self.assertEqual(creator_console.resolve_narrator_gender(spaced), "male")
        self.assertEqual(creator_console.resolve_narrator_gender(prefix), "female")

    def test_resolve_narrator_gender_uses_self_id_keywords(self):
        from app.services import creator_console

        woman = creator_console.CreatorStory(
            narration_script="As a woman, I never expected this betrayal. " * 10,
        )
        man = creator_console.CreatorStory(
            narration_script="I'm a guy who just wanted a quiet weekend. " * 10,
        )

        self.assertEqual(creator_console.resolve_narrator_gender(woman), "female")
        self.assertEqual(creator_console.resolve_narrator_gender(man), "male")

    def test_resolve_narrator_gender_uses_partner_cue_fallback(self):
        from app.services import creator_console

        female = creator_console.CreatorStory(
            narration_script="My husband forgot our anniversary again. " * 10,
        )
        male = creator_console.CreatorStory(
            narration_script="My wife wants to repaint the whole house. " * 10,
        )

        self.assertEqual(creator_console.resolve_narrator_gender(female), "female")
        self.assertEqual(creator_console.resolve_narrator_gender(male), "male")

    def test_resolve_narrator_gender_returns_blank_when_ambiguous(self):
        from app.services import creator_console

        story = creator_console.CreatorStory(
            narration_script="Someone parked in my spot and I was furious. " * 10,
        )

        self.assertEqual(creator_console.resolve_narrator_gender(story), "")

    def test_build_video_params_infers_gender_when_field_blank(self):
        from app.services import creator_console

        story = creator_console.CreatorStory(
            narration_script="As a woman, I refused to give up my seat. " * 20,
        )

        params = creator_console.build_video_params(story, rng=random.Random(7))

        self.assertTrue(params.voice_name.endswith("-Female"))
        self.assertEqual(story.narrator_gender, "female")

    def test_publish_marker_round_trips_and_absent_marker_returns_empty(self):
        from app.services import creator_console
        from app.utils import utils

        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)

            def storage_dir(sub_dir="", create=False):
                path = temp_root
                if sub_dir:
                    path = path / sub_dir
                if create:
                    path.mkdir(parents=True, exist_ok=True)
                return str(path)

            with patch.object(utils, "storage_dir", side_effect=storage_dir):
                self.assertEqual(creator_console.load_publish_marker("task-a"), {})

                creator_console.record_publish(
                    "task-a",
                    "direct",
                    {"status": "PUBLISH_COMPLETE", "publish_id": "pub-1"},
                )
                marker = creator_console.load_publish_marker("task-a")

        self.assertEqual(marker["method"], "direct")
        self.assertEqual(marker["status"], "PUBLISH_COMPLETE")
        self.assertEqual(marker["publish_id"], "pub-1")
        self.assertIsInstance(marker["posted_at"], float)

    def test_list_library_videos_scans_finished_videos_newest_first(self):
        from app.services import creator_console
        from app.utils import utils

        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)

            def storage_dir(sub_dir="", create=False):
                path = temp_root
                if sub_dir:
                    path = path / sub_dir
                if create:
                    path.mkdir(parents=True, exist_ok=True)
                return str(path)

            with patch.object(utils, "storage_dir", side_effect=storage_dir):
                first = Path(utils.task_dir("first"))
                second = Path(utils.task_dir("second"))
                (first / "final-1.mp4").write_bytes(b"first-video")
                (second / "final-1.mp4").write_bytes(b"second-video")
                (first / "story.json").write_text(
                    json.dumps(
                        {
                            "comment_card_title": "AITA for leaving?",
                            "suggested_description": "Caption one",
                            "suggested_hashtags": ["#aita", "#story"],
                        }
                    ),
                    encoding="utf-8",
                )
                (second / "story.json").write_text(
                    json.dumps({"video_subject": "Roommate drama"}),
                    encoding="utf-8",
                )
                creator_console.record_publish(
                    "second",
                    "inbox",
                    {"status": "PROCESSING_UPLOAD", "publish_id": "inbox-1"},
                )
                old = time.time() - 100
                new = time.time()
                os.utime(first / "final-1.mp4", (old, old))
                os.utime(second / "final-1.mp4", (new, new))

                videos = creator_console.list_library_videos()

        self.assertEqual([video["task_id"] for video in videos], ["second", "first"])
        self.assertEqual(videos[0]["display_name"], "Roommate drama")
        self.assertEqual(videos[0]["posted"]["method"], "inbox")
        self.assertEqual(videos[1]["display_name"], "AITA for leaving?")
        self.assertEqual(videos[1]["slug"], "aita-for-leaving")
        self.assertEqual(videos[1]["video_url"], "/tasks/first/final-1.mp4")
        self.assertEqual(videos[1]["suggested_hashtags"], ["#aita", "#story"])


if __name__ == "__main__":
    unittest.main()
