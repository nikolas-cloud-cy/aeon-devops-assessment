import json
import threading
import unittest
import urllib.error
import urllib.request

from main import make_server


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)  # port 0 = random free port
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        try:
            with urllib.request.urlopen(url) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_liveness(self):
        self.assertEqual(self.get("/healthz"), (200, {"status": "alive"}))

    def test_readiness(self):
        self.assertEqual(self.get("/readyz"), (200, {"status": "ready"}))

    def test_root_reports_service(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertEqual(body["service"], "api")

    def test_unknown_path_is_404(self):
        self.assertEqual(self.get("/nope")[0], 404)


if __name__ == "__main__":
    unittest.main()
