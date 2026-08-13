"""POST /api/edit-contact
Body: {account_number, contact_email (or contact_name), updates: {name?, title?, email?, mobile?, hook?, subject?, body?}}
Updates one contact within an account."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo


EDITABLE_FIELDS = {
    'name': 200,
    'title': 200,
    'email': 320,       # RFC max email length
    'mobile': 40,
    'hook': 1000,
    'subject': 200,
    'body': 5000,
}


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        body = self._body()
        acc_num = (body.get('account_number') or '').strip()
        contact_email = (body.get('contact_email') or '').strip().lower()
        contact_name = (body.get('contact_name') or '').strip()
        updates = body.get('updates') or {}

        if not acc_num:
            raise HttpError(400, 'account_number is required')
        if not (contact_email or contact_name):
            raise HttpError(400, 'contact_email or contact_name is required')
        if not isinstance(updates, dict) or not updates:
            raise HttpError(400, 'updates must be a non-empty object')

        target = repo.get_account_by_number(user_id, acc_num)
        if not target:
            raise HttpError(404, f'Account {acc_num} not found')

        data = dict(target['data'])
        contacts = list(data.get('contacts') or [])
        updated = 0
        for c in contacts:
            hit = (contact_email and (c.get('email') or '').lower() == contact_email) \
               or (contact_name and (c.get('name') or '') == contact_name)
            if not hit:
                continue
            for field, max_len in EDITABLE_FIELDS.items():
                if field in updates:
                    value = ('' if updates[field] is None else str(updates[field])).strip()[:max_len]
                    c[field] = value
            updated += 1
        if updated == 0:
            raise HttpError(404, 'Contact not found on this account')

        data['contacts'] = contacts
        if not repo.upsert_account_data(target['id'], user_id, data, target['updated_at']):
            raise HttpError(409, 'Account was modified by another request. Please retry.')
        self._ok({'saved': True, 'updated': updated})
