"""GET /api/gmail-callback?code=...&state=...
Google redirects here after the user consents. We exchange the code for a
refresh token, store it, then redirect the user back to /app/."""
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.gmail import exchange_code_for_tokens, decode_state, GmailError
from _lib import repo


def _redirect(handler, path: str) -> None:
    handler.send_response(302)
    handler.send_header('Location', path)
    handler.send_header('Content-Length', '0')
    handler.end_headers()


class handler(BaseHTTPRequestHandler):
    """This endpoint is NOT auth-gated: Google redirects the browser here with
    a plain GET, no bearer token. Security relies on the HMAC-signed `state`
    param that only we can generate."""

    def log_message(self, fmt, *args):
        pass  # silence Vercel access log noise

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        # Google may return ?error=access_denied if user clicks Cancel
        if qs.get('error'):
            _redirect(self, '/app/?gmail_error=' + qs['error'][0])
            return
        code  = (qs.get('code')  or [''])[0]
        state = (qs.get('state') or [''])[0]
        if not code or not state:
            _redirect(self, '/app/?gmail_error=missing_params')
            return
        try:
            user_id = decode_state(state)
            tokens = exchange_code_for_tokens(code)
            repo.save_gmail_connection(user_id, tokens['refresh_token'], tokens['email'])
        except GmailError as e:
            _redirect(self, '/app/?gmail_error=' + str(e).replace(' ', '_'))
            return
        except Exception:
            import logging, traceback
            logging.getLogger(__name__).exception('gmail-callback failed')
            _redirect(self, '/app/?gmail_error=unexpected')
            return
        _redirect(self, '/app/?gmail_connected=1')
