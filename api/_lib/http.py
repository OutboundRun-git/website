"""Base HTTP handler that every /api/* endpoint inherits from.

Handles: JSON body parsing, JSON response formatting, and delegating auth
to require_user() with clean 401 handling.
"""
import json
from http.server import BaseHTTPRequestHandler

from _lib.auth import require_user, AuthError


class BaseHandler(BaseHTTPRequestHandler):
    def _json(self, data, status: int = 200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _ok(self, data):
        self._json(data, 200)

    def _err(self, status: int, message: str):
        self._json({'error': message}, status)

    def _body(self) -> dict:
        length = int(self.headers.get('Content-Length') or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _query(self, key: str) -> str | None:
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        vals = qs.get(key)
        return vals[0] if vals else None

    def _user(self) -> str:
        return require_user(self)

    def log_message(self, fmt, *args):
        # Silence Vercel's per-request access log noise; use print() in handlers.
        pass


def user_or_401(fn):
    """Decorator: verify auth, pass user_id as first arg, return 401 on AuthError."""
    def wrapper(self):
        try:
            user_id = self._user()
        except AuthError as e:
            return self._err(e.status, str(e))
        return fn(self, user_id)
    return wrapper
