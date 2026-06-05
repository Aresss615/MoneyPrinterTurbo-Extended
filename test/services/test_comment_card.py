import os
import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from app.services import video
from app.utils import utils


FONT_PATH = os.path.join(utils.font_dir(), "STHeitiMedium.ttc")


class TestCommentCardImage(unittest.TestCase):
    def test_returns_rgba_image_of_requested_width(self):
        img = video.create_comment_card_image(
            width=900,
            username="u/throwaway",
            title="AITA for refusing to give up the window seat I paid extra for?",
            font_path=FONT_PATH,
        )
        self.assertEqual(img.mode, "RGBA")
        self.assertEqual(img.width, 900)
        self.assertGreater(img.height, 0)

    def test_longer_title_produces_taller_card(self):
        short = video.create_comment_card_image(
            width=900, username="u/x", title="Short title?", font_path=FONT_PATH
        )
        long = video.create_comment_card_image(
            width=900,
            username="u/x",
            title=(
                "AITA for refusing to give up the window seat I paid extra for "
                "even though a mom insisted her child wanted to watch the clouds "
                "for the entire six hour flight to the other side of the country?"
            ),
            font_path=FONT_PATH,
        )
        self.assertGreater(long.height, short.height)

    def test_falls_back_when_font_missing(self):
        # Should not raise even if the font path is invalid.
        img = video.create_comment_card_image(
            width=600,
            username="u/x",
            title="Hello world",
            font_path="/nonexistent/font.ttf",
        )
        self.assertEqual(img.width, 600)


if __name__ == "__main__":
    unittest.main()
