"""POST /api/delete-my-account
Body: {confirm: "DELETE"}
Deletes the caller's auth user + all their data (cascades to profiles,
configs, accounts, jobs)."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        body = self._body()
        confirm = body.get('confirm')
        if confirm != 'DELETE':
            raise HttpError(400, 'confirm must equal "DELETE" to proceed')

        repo.delete_user(user_id)
        self._ok({'deleted': True})
