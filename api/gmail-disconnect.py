"""POST /api/gmail-disconnect
Removes the stored Gmail refresh token for the current user."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, endpoint
from _lib import repo


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        repo.delete_gmail_connection(user_id)
        self._ok({'disconnected': True})
