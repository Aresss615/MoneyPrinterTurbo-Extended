import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from app.services import llm


class TestCleanGeneratedText(unittest.TestCase):
    def test_removes_think_block(self):
        out = llm.clean_generated_text("<think>reasoning here</think>The real story.")
        self.assertEqual(out, "The real story.")

    def test_removes_trailing_slash_think_token(self):
        out = llm.clean_generated_text("Am I the asshole? /think")
        self.assertEqual(out, "Am I the asshole?")

    def test_keeps_the_word_think(self):
        out = llm.clean_generated_text("I think she was wrong.")
        self.assertEqual(out, "I think she was wrong.")

    def test_strips_markdown_and_wrapping_quotes(self):
        out = llm.clean_generated_text('"**Hello** ## world"')
        self.assertEqual(out, "Hello world")

    def test_collapses_whitespace(self):
        out = llm.clean_generated_text("a\n\n  b   c")
        self.assertEqual(out, "a b c")


if __name__ == "__main__":
    unittest.main()
