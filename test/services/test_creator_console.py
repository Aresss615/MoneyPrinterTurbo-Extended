import json
import random
import sys
import tempfile
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
            }
        )

        story = creator_console.parse_chatgpt_story_json(raw_json)

        self.assertEqual(story.source_url, "https://www.reddit.com/r/AmItheAsshole/example")
        self.assertEqual(story.subreddit, "AmItheAsshole")
        self.assertEqual(story.comment_card_username, "u/example")
        self.assertEqual(story.comment_card_title, "AITA for keeping the window seat?")
        self.assertEqual(story.caption_keywords_to_highlight, ["window seat", "paid extra"])
        self.assertEqual(story.suggested_hashtags, ["#aita", "#drama", "#travel"])

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

    def test_build_video_params_rotates_source_and_voice_from_pool(self):
        from app.services import creator_console

        story = creator_console.CreatorStory(
            narration_script="AITA for refusing to switch seats? " * 30,
        )

        params = creator_console.build_video_params(story, rng=random.Random(7))

        discovered = {str(p) for p in creator_console.list_background_sources()}
        self.assertIn(params.video_materials[0].url, discovered)
        self.assertIn(params.voice_name, creator_console.VOICE_POOL)


if __name__ == "__main__":
    unittest.main()
