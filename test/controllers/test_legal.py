import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.asgi import app


class TestLegalApi(unittest.TestCase):
    """Legal pages served at clean URLs that do not contain 'tiktok'.

    TikTok app review rejected the Terms/Privacy links for containing
    'tiktok'. These routes expose the same documents under /legal/* so the
    URLs entered in the dev portal pass review.
    """

    def setUp(self):
        self.client = TestClient(app)

    def test_landing_page_describes_app_and_links_legal_docs(self):
        response = self.client.get("/legal")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("JC Video Factory", response.text)
        self.assertIn("/legal/terms", response.text)
        self.assertIn("/legal/privacy", response.text)

    def test_serves_terms_page(self):
        response = self.client.get("/legal/terms")

        self.assertEqual(response.status_code, 200)
        self.assertIn("JC Video Factory Terms of Service", response.text)

    def test_serves_privacy_page(self):
        response = self.client.get("/legal/privacy")

        self.assertEqual(response.status_code, 200)
        self.assertIn("JC Video Factory Privacy Policy", response.text)

    def test_clean_urls_do_not_contain_tiktok(self):
        for path in ("/legal", "/legal/terms", "/legal/privacy"):
            self.assertNotIn("tiktok", path.lower())

    def test_serves_site_verification_file_under_legal_path(self):
        response = self.client.get(
            "/legal/tiktokWLly7x9cmPv0wlZyHy99pbIPzg458GTc.txt"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.text.strip(),
            "tiktok-developers-site-verification=WLly7x9cmPv0wlZyHy99pbIPzg458GTc",
        )
        self.assertIn("text/plain", response.headers["content-type"])

    def test_serves_site_verification_file_under_legal_terms_path(self):
        response = self.client.get(
            "/legal/terms/tiktokmrsQ4Koe9viUCunfDTI0E7veX4Ls1i8H.txt"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.text.strip(),
            "tiktok-developers-site-verification=mrsQ4Koe9viUCunfDTI0E7veX4Ls1i8H",
        )

    def test_serves_site_verification_file_under_legal_privacy_path(self):
        response = self.client.get(
            "/legal/privacy/tiktoklxPM3j6HLE0ELdYGQtKiUBRk3zcaNktU.txt"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.text.strip(),
            "tiktok-developers-site-verification=lxPM3j6HLE0ELdYGQtKiUBRk3zcaNktU",
        )

    def test_unknown_verification_file_returns_404(self):
        response = self.client.get("/legal/tiktokNOPE.txt")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
