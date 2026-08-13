"""POST /api/delete-account
Body: {account_number}
Deletes a single account."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        body = self._body()
        acc_num = (body.get('account_number') or '').strip()
        if not acc_num:
            raise HttpError(400, 'account_number is required')

        if not repo.delete_account_by_number(user_id, acc_num):
            raise HttpError(404, f'Account {acc_num} not found')
        self._ok({'deleted': True, 'account_number': acc_num})
