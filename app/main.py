"""Minimal HTTP service used to demonstrate the delivery workflow.

Standard library only, so the image has no third-party dependencies to patch.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = os.environ.get("APP_VERSION", "dev")
PORT = int(os.environ.get("PORT", "8080"))


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":  # liveness: process is up
            self._send(200, {"status": "alive"})
        elif self.path == "/readyz":  # readiness: ready to take traffic
            self._send(200, {"status": "ready"})
        elif self.path == "/":
            self._send(200, {"service": "api", "version": VERSION})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):  # log to stdout, one line per request
        print(f"{self.address_string()} {fmt % args}", flush=True)


def make_server(port=PORT):
    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


if __name__ == "__main__":
    make_server().serve_forever()
