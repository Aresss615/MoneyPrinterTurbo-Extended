import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from app.services import video


class TestAlignSpokenWords(unittest.TestCase):
    def test_repeated_word_highlights_correct_occurrence(self):
        text_words = ["i", "paid", "for", "the", "window", "seat", "i", "need", "it"]
        spoken = ["i", "paid", "for", "the", "i", "need"]
        # The second spoken "i" must map to index 6, not back to 0.
        self.assertEqual(video.align_spoken_words(text_words, spoken), [0, 1, 2, 3, 6, 7])

    def test_punctuation_is_ignored_when_matching(self):
        text_words = ["A.I.T.A.", "for", "don't", "you"]
        spoken = ["aita", "for", "dont", "you"]
        self.assertEqual(video.align_spoken_words(text_words, spoken), [0, 1, 2, 3])

    def test_unmatched_spoken_word_returns_minus_one(self):
        text_words = ["hello", "world"]
        spoken = ["hello", "there", "world"]
        self.assertEqual(video.align_spoken_words(text_words, spoken), [0, -1, 1])

    def test_pointer_does_not_consume_when_no_forward_match(self):
        # "the" appears once; a later spoken "the" with no forward match falls
        # back to the existing occurrence rather than going to -1.
        text_words = ["the", "cat", "sat"]
        spoken = ["the", "cat", "the"]
        self.assertEqual(video.align_spoken_words(text_words, spoken), [0, 1, 0])


if __name__ == "__main__":
    unittest.main()
