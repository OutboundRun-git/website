"""POST /api/delete-all-accounts
Deletes every account owned by the caller. No body required.
Returns {deleted: count_before}."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, endpoint
from _lib import repo


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        before = len(repo.list_accounts(user_id))
        repo.delete_all_accounts(user_id)
        self._ok({'deleted': before})
