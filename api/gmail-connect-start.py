"""GET /api/gmail-connect-start
Returns {url: <Google OAuth URL>}. Frontend redirects the browser to that URL."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib.gmail import build_oauth_url, GmailError
from _lib import env


class handler(BaseHandler):
    @endpoint
    def do_GET(self, user_id: str):
        if not env.gmail_configured():
            raise HttpError(503, 'Gmail sending is not configured on this deployment')
        try:
            url = build_oauth_url(user_id)
        except GmailError as e:
            raise HttpError(500, str(e))
        self._ok({'url': url})
