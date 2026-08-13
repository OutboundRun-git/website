"""POST /api/edit-account
Body: {account_number, updates: {account_name?, industry?, website?, notes?}}
Updates top-level account fields. Leaves contacts/research/hypothesis alone."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo


EDITABLE_STRING_FIELDS = {
    'account_name': 200,
    'industry': 200,
    'website': 400,
    'notes': 2000,
    'status': 40,
}
ALLOWED_STATUSES = {'new', 'in_progress', 'opportunity', 'won', 'lost', 'cold', 'disqualified'}


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
        for field, max_len in EDITABLE_STRING_FIELDS.items():
            if field in updates:
                value = ('' if updates[field] is None else str(updates[field])).strip()[:max_len]
                if field == 'account_name' and not value:
                    raise HttpError(400, 'account_name cannot be blank')
                if field == 'status' and value and value not in ALLOWED_STATUSES:
                    raise HttpError(400, f'status must be one of: {", ".join(sorted(ALLOWED_STATUSES))}')
                data[field] = value
        if 'starred' in updates:
            data['starred'] = bool(updates['starred'])

        if not repo.upsert_account_data(target['id'], user_id, data, target['updated_at']):
            raise HttpError(409, 'Account was modified by another request. Please retry.')
        self._ok({'saved': True, 'account': data})
