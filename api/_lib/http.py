"""Base HTTP handler and endpoint decorator.

Contract:
- Every endpoint uses @endpoint (which handles auth, exception catching, and
  request-body draining before responding to prevent ConnectionReset).
- _body() raises HttpError(400) on malformed JSON (not swallowed).
- Public error messages only. Server-side logging captures detail.
"""
import json
import logging
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from _lib.auth import require_user, AuthError


log = logging.getLogger(__name__)

MAX_BODY_BYTES = 5 * 1024 * 1024  # 5MB hard cap on any request body


class HttpError(Exception):
    def __init__(self, status: int, public_message: str):
        super().__init__(public_message)
        self.status = status
        self.public_message = public_message


class BaseHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Silence Vercel per-request access log noise; use logging in handlers.
        pass

    # ---------- response helpers ----------
    def _json(self, data, status: int = 200) -> None:
        body = json.dumps(data, separators=(',', ':')).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            log.exception('failed to write response body')

    def _ok(self, data) -> None:
        self._json(data, 200)

    def _err(self, status: int, message: str) -> None:
        # Drain body first so POST callers do not see ConnectionReset.
        self._drain_body()
        self._json({'error': message}, status)

    # ---------- request helpers ----------
    def _drain_body(self) -> None:
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except (TypeError, ValueError):
            return
        remaining = min(length, MAX_BODY_BYTES)
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 65536))
            if not chunk:
                break
            remaining -= len(chunk)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except (TypeError, ValueError):
            raise HttpError(400, 'Invalid Content-Length')
        if length == 0:
            return {}
        if length > MAX_BODY_BYTES:
            self._drain_body()
            raise HttpError(413, 'Request body too large')
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise HttpError(400, f'Malformed JSON body: {e.msg}')
        if not isinstance(data, dict):
            raise HttpError(400, 'Request body must be a JSON object')
        return data

    def _query(self, key: str) -> str | None:
        qs = parse_qs(urlparse(self.path).query)
        vals = qs.get(key)
        return vals[0] if vals else None

    def _user(self) -> str:
        return require_user(self)


def endpoint(fn):
    """Decorator for do_GET / do_POST: auth-gate, catch expected errors, catch
    unexpected exceptions, always drain body before responding."""
    def wrapper(self):
        try:
            user_id = self._user()
            fn(self, user_id)
        except AuthError as e:
            self._err(e.status, e.message)
        except HttpError as e:
            self._err(e.status, e.public_message)
        except Exception:
            log.exception('unhandled exception in endpoint')
            self._err(500, 'Internal server error')
    return wrapper
