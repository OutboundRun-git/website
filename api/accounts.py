"""GET /api/accounts
Returns the current user's full list of accounts, ordered by account_number."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, endpoint
from _lib import repo


class handler(BaseHandler):
    @endpoint
    def do_GET(self, user_id: str):
        self._ok({'accounts': repo.list_accounts(user_id)})
