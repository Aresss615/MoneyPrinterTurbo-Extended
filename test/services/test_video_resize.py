import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from app.services import video


class TestVideoResize(unittest.TestCase):
    def test_cover_resize_scales_landscape_video_to_fill_portrait_frame(self):
        scaled_size, crop_box = video.calculate_cover_resize_and_crop(
            source_size=(1920, 1080),
            target_size=(1080, 1920),
        )

        self.assertEqual(scaled_size, (3413, 1920))
        self.assertEqual(crop_box, (1166, 0, 2246, 1920))

    def test_cover_resize_scales_portrait_video_to_fill_landscape_frame(self):
        scaled_size, crop_box = video.calculate_cover_resize_and_crop(
            source_size=(1080, 1920),
            target_size=(1920, 1080),
        )

        self.assertEqual(scaled_size, (1920, 3413))
        self.assertEqual(crop_box, (0, 1166, 1920, 2246))


if __name__ == "__main__":
    unittest.main()
