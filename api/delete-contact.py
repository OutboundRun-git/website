"""POST /api/delete-contact
Body: {account_number, contact_email (or contact_name)}
Removes a contact from the account's contacts array."""
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
        contact_email = (body.get('contact_email') or '').strip().lower()
        contact_name = (body.get('contact_name') or '').strip()

        if not acc_num:
            raise HttpError(400, 'account_number is required')
        if not (contact_email or contact_name):
            raise HttpError(400, 'contact_email or contact_name is required')

        target = repo.get_account_by_number(user_id, acc_num)
        if not target:
            raise HttpError(404, f'Account {acc_num} not found')

        data = dict(target['data'])
        contacts = list(data.get('contacts') or [])
        before = len(contacts)
        contacts = [
            c for c in contacts
            if not (
                (contact_email and (c.get('email') or '').lower() == contact_email)
                or (contact_name and (c.get('name') or '') == contact_name)
            )
        ]
        removed = before - len(contacts)
        if removed == 0:
            raise HttpError(404, 'Contact not found on this account')

        data['contacts'] = contacts
        if not repo.upsert_account_data(target['id'], user_id, data, target['updated_at']):
            raise HttpError(409, 'Account was modified by another request. Please retry.')
        self._ok({'deleted': True, 'removed': removed})
