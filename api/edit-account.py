"""POST /api/edit-account
Body: {account_number, updates: {account_name?, industry?, website?, notes?}}
Updates top-level account fields. Leaves contacts/research/hypothesis alone."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo


EDITABLE_FIELDS = {
    'account_name': 200,
    'industry': 200,
    'website': 400,
    'notes': 2000,
}


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        body = self._body()
        acc_num = (body.get('account_number') or '').strip()
        updates = body.get('updates') or {}

        if not acc_num:
            raise HttpError(400, 'account_number is required')
        if not isinstance(updates, dict) or not updates:
            raise HttpError(400, 'updates must be a non-empty object')

        target = repo.get_account_by_number(user_id, acc_num)
        if not target:
            raise HttpError(404, f'Account {acc_num} not found')

        data = dict(target['data'])
        for field, max_len in EDITABLE_FIELDS.items():
            if field in updates:
                value = (updates[field] or '').strip()[:max_len]
                # account_name must not be blank
                if field == 'account_name' and not value:
                    raise HttpError(400, 'account_name cannot be blank')
                data[field] = value

        if not repo.upsert_account_data(target['id'], user_id, data, target['updated_at']):
            raise HttpError(409, 'Account was modified by another request. Please retry.')
        self._ok({'saved': True, 'account': data})
