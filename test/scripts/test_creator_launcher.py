import os
import stat
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


class TestCreatorLauncher(unittest.TestCase):
    def test_creator_launcher_exists_and_is_executable(self):
        launcher = ROOT_DIR / "creator.sh"

        self.assertTrue(launcher.exists())
        self.assertTrue(os.access(launcher, os.X_OK))

    def test_creator_launcher_starts_creator_console_with_defaults(self):
        launcher = ROOT_DIR / "creator.sh"
        content = launcher.read_text(encoding="utf-8")

        self.assertIn("uvicorn app.asgi:app", content)
        self.assertIn("PORT=\"${PORT:-8080}\"", content)
        self.assertIn("http://${HOST}:${PORT}/", content)
        self.assertIn(".venv/bin/python", content)
        self.assertIn("set +u", content)
        self.assertIn("source \"$ROOT_DIR/setup_cuda_env.sh\"", content)


if __name__ == "__main__":
    unittest.main()
