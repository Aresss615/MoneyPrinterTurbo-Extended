import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.asgi import app


class TestHealthApi(unittest.TestCase):
    """Lightweight liveness check used by the always-on website's bot badge.

    The static site at johnchrisley.dev/legal pings this endpoint to show
    'bot online' / 'bot offline'. It must be cheap (no upstream calls) and
    reachable cross-origin (CORS) at a clean path without /api/v1 or 'tiktok'.
    """

    def setUp(self):
        self.client = TestClient(app)

    def test_health_returns_ok(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_health_allows_cross_origin(self):
        # The site origin differs from the bot origin; CORS must permit it.
        response = self.client.get(
            "/health", headers={"Origin": "https://johnchrisley.dev"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"), "*"
        )


if __name__ == "__main__":
    unittest.main()
