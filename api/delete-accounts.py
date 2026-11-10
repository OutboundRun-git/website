"""POST /api/delete-accounts
Body: {account_numbers: [str, ...]}
Deletes each named account; skips ones not found. Returns {deleted, not_found}."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo


MAX_BATCH = 500


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        body = self._body()
        nums = body.get('account_numbers')
        if not isinstance(nums, list) or not nums:
            raise HttpError(400, 'account_numbers must be a non-empty array')
        if len(nums) > MAX_BATCH:
            raise HttpError(413, f'account_numbers exceeds {MAX_BATCH}')

        deleted = 0
        not_found: list[str] = []
        for raw in nums:
            n = (raw or '').strip() if isinstance(raw, str) else ''
            if not n:
                continue
            if repo.delete_account_by_number(user_id, n):
                deleted += 1
            else:
                not_found.append(n)
        self._ok({'deleted': deleted, 'not_found': not_found})
