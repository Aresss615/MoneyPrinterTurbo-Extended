import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SITE_DIR = ROOT_DIR / "site" / "legal"


class TestTikTokReviewPages(unittest.TestCase):
    def test_readme_lists_always_on_review_urls(self):
        readme = (SITE_DIR / "README.md").read_text(encoding="utf-8")

        self.assertIn(
            "| Website URL / Web/Desktop URL | `https://johnchrisley.dev/legal` |",
            readme,
        )
        self.assertIn(
            "| Terms of Service URL | `https://johnchrisley.dev/legal/terms` |",
            readme,
        )
        self.assertIn(
            "| Privacy Policy URL | `https://johnchrisley.dev/legal/privacy` |",
            readme,
        )
        self.assertIn(
            "| Login Kit redirect URI | `https://app.johnchrisley.dev/api/v1/callback` |",
            readme,
        )

    def test_static_pages_include_tiktok_url_verification_files(self):
        expected_files = {
            "tiktokWLly7x9cmPv0wlZyHy99pbIPzg458GTc.txt": (
                "tiktok-developers-site-verification=WLly7x9cmPv0wlZyHy99pbIPzg458GTc"
            ),
            "terms/tiktokmrsQ4Koe9viUCunfDTI0E7veX4Ls1i8H.txt": (
                "tiktok-developers-site-verification=mrsQ4Koe9viUCunfDTI0E7veX4Ls1i8H"
            ),
            "privacy/tiktoklxPM3j6HLE0ELdYGQtKiUBRk3zcaNktU.txt": (
                "tiktok-developers-site-verification=lxPM3j6HLE0ELdYGQtKiUBRk3zcaNktU"
            ),
        }

        for relative_path, expected_content in expected_files.items():
            with self.subTest(relative_path=relative_path):
                path = SITE_DIR / relative_path
                self.assertTrue(path.is_file(), f"{relative_path} is missing")
                self.assertEqual(path.read_text(encoding="utf-8").strip(), expected_content)

    def test_setup_notes_point_to_published_review_urls(self):
        setup_notes = (ROOT_DIR / "SETUP_NOTES.md").read_text(encoding="utf-8")

        self.assertIn("https://johnchrisley.dev/legal", setup_notes)
        self.assertIn("https://johnchrisley.dev/legal/terms", setup_notes)
        self.assertIn("https://johnchrisley.dev/legal/privacy", setup_notes)
        self.assertIn("https://app.johnchrisley.dev/api/v1/callback", setup_notes)


if __name__ == "__main__":
    unittest.main()
