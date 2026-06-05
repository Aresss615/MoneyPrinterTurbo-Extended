import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from app.services import video


class TestSequentialSubclipsNeeded(unittest.TestCase):
    def test_collects_enough_clips_to_cover_longer_audio(self):
        # 43.12s of narration with 5s clips needs ceil(43.12/5) = 9 subclips,
        # otherwise the gameplay runs out and the video goes black.
        self.assertEqual(video.sequential_subclips_needed(43.12, 5), 9)

    def test_exact_multiple_is_not_over_collected(self):
        self.assertEqual(video.sequential_subclips_needed(10.0, 5), 2)

    def test_audio_shorter_than_one_clip_still_needs_one(self):
        self.assertEqual(video.sequential_subclips_needed(4.0, 5), 1)

    def test_zero_audio_needs_at_least_one(self):
        self.assertEqual(video.sequential_subclips_needed(0, 5), 1)

    def test_non_positive_clip_duration_is_guarded(self):
        self.assertEqual(video.sequential_subclips_needed(43.0, 0), 1)


if __name__ == "__main__":
    unittest.main()
