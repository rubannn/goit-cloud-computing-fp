"""HTTP smoke tests using a temporary SQLite database, without AWS resources."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.env = dict(os.environ, DATABASE_URL=f"sqlite:///{Path(cls.temp.name) / 'quotes.db'}")
        subprocess.run([sys.executable, "-m", "app.init_db"], cwd=ROOT, env=cls.env, check=True)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.start_server()
        cls.addClassCleanup(cls.stop_server)

    @classmethod
    def start_server(cls):
        cls.server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory",
             "--host", "127.0.0.1", "--port", str(cls.port), "--log-level", "warning"],
            cwd=ROOT, env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            if cls.server.poll() is not None:
                raise RuntimeError("Test server exited before becoming ready")
            try:
                with urlopen(cls.base + "/health", timeout=.5) as response:
                    if response.status == 200:
                        return
            except OSError:
                time.sleep(.1)
        cls.stop_server()
        raise RuntimeError("Test server did not start")

    @classmethod
    def stop_server(cls):
        cls.server.terminate()
        try:
            cls.server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.server.kill()
            cls.server.wait()

    def request(self, path, method="GET", payload=None):
        request = Request(
            self.base + path, method=method,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            data = response.read()
            return response.status, json.loads(data) if data else None

    def setUp(self):
        for quote in self.request("/api/quotes?limit=100")[1]:
            self.request(f"/api/quotes/{quote['id']}", "DELETE")

    def test_crud_and_persistence(self):
        status, quote = self.request("/api/quotes", "POST", {
            "text": "  Мысль для коллекции  ", "author": "Автор", "category": "Жизнь",
        })
        self.assertEqual(status, 201)
        self.assertEqual(quote["text"], "Мысль для коллекции")
        self.assertTrue(quote["created_at"])
        path = f"/api/quotes/{quote['id']}"
        self.stop_server()
        self.start_server()
        self.assertEqual(self.request(path)[1]["author"], "Автор")
        status, updated = self.request(path, "PUT", {"text": "Новая мысль"})
        self.assertEqual(status, 200)
        self.assertEqual(updated["text"], "Новая мысль")
        self.assertEqual(updated["created_at"], self.request(path)[1]["created_at"])
        self.assertEqual(self.request(path, "DELETE")[0], 204)
        self.assertEqual(self.request(path)[0], 404)
        self.assertEqual(self.request("/api/quotes")[1], [])

    def test_filters_random_and_pagination(self):
        for payload in [
            {"text": "Keep moving", "author": "Alice", "category": "Life"},
            {"text": "100% focus", "author": "Bob", "category": "Work"},
            {"text": "Small steps", "author": "Alice", "category": "Work"},
        ]:
            self.assertEqual(self.request("/api/quotes", "POST", payload)[0], 201)
        self.assertEqual(len(self.request("/api/quotes?q=alice")[1]), 2)
        self.assertEqual(len(self.request("/api/quotes?category=Work")[1]), 2)
        self.assertEqual(len(self.request("/api/quotes?q=alice&category=Work")[1]), 1)
        self.assertEqual(len(self.request("/api/quotes?q=%25")[1]), 1)
        self.assertEqual(self.request("/api/categories")[1], ["Life", "Work"])
        self.assertEqual(len(self.request("/api/quotes?offset=1&limit=1")[1]), 1)
        status, quote = self.request("/api/quotes/random?category=Life")
        self.assertEqual(status, 200)
        self.assertEqual(quote["text"], "Keep moving")
        self.assertEqual(self.request("/api/quotes/random?category=Missing")[0], 404)

    def test_validation_and_missing_records(self):
        for payload in [{"text": "   "}, {"text": "x" * 5001}, {"text": "x", "author": "x" * 201}]:
            self.assertEqual(self.request("/api/quotes", "POST", payload)[0], 422)
        self.assertEqual(self.request("/api/quotes?limit=101")[0], 422)
        self.assertEqual(self.request("/api/quotes?offset=-1")[0], 422)
        self.assertEqual(self.request("/api/quotes/random")[0], 404)
        self.assertEqual(self.request("/api/quotes/999999", "PUT", {"text": "x"})[0], 404)
        self.assertEqual(self.request("/api/quotes/999999", "DELETE")[0], 404)
        self.assertEqual(self.request("/health"), (200, {"status": "ok"}))
        with urlopen(self.base) as response:
            self.assertIn(b"Quote Collection", response.read())
        with urlopen(self.base + "/static/app.js") as response:
            self.assertEqual(response.status, 200)


if __name__ == "__main__":
    unittest.main()
