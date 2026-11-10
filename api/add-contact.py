"""POST /api/add-contact
Body: {account_number, contact: {name, title?, email?, mobile?, hook?, subject?, body?}}
Adds a single manually-entered contact to the account. Refuses to add a
duplicate: same email (case-insensitive) or, when both have empty email,
same name (case-insensitive)."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo


MAX_FIELDS = {
    'name': 200,
    'title': 200,
    'email': 320,
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
        raw = body.get('contact') or {}
        if not acc_num:
            raise HttpError(400, 'account_number is required')
        if not isinstance(raw, dict):
            raise HttpError(400, 'contact must be an object')

        name = (raw.get('name') or '').strip()
        title = (raw.get('title') or '').strip()
        email = (raw.get('email') or '').strip()
        if not name:
            raise HttpError(400, 'contact.name is required')
        if not title:
            raise HttpError(400, 'contact.title is required so OutboundRun can draft a persona-specific email')
        if not email:
            raise HttpError(400, 'contact.email is required so OutboundRun can draft an email for them')

        contact: dict = {}
        for field, max_len in MAX_FIELDS.items():
            val = raw.get(field)
            if val is None:
                contact[field] = ''
                continue
            contact[field] = str(val).strip()[:max_len]
        # Manually-added contacts default to neutral flags so they do not
        # pollute the Green/Yellow/Red filters used by bulk send.
        contact.setdefault('flag', 'YELLOW')
        contact.setdefault('flag_reason', 'Manually added by user; not AI-verified.')
        contact.setdefault('flag_categories', ['Manually added'])
        contact.setdefault('human_flag', 'GREEN')
        contact.setdefault('human_reason', 'Manually entered, not AI-generated.')
        contact.setdefault('exec_flag', 'YELLOW')
        contact.setdefault('exec_reason', 'Manually added; exec appropriateness not assessed.')

        target = repo.get_account_by_number(user_id, acc_num)
        if not target:
            raise HttpError(404, f'Account {acc_num} not found')
        data = dict(target['data'])
        existing = list(data.get('contacts') or [])

        new_email = (contact['email'] or '').lower().strip()
        new_name_key = name.lower()
        for c in existing:
            c_email = (c.get('email') or '').lower().strip()
            c_name = (c.get('name') or '').strip().lower()
            if new_email and c_email == new_email:
                raise HttpError(409, f'A contact with email {new_email} is already on this account')
            if not new_email and not c_email and c_name == new_name_key:
                raise HttpError(409, f'A contact named "{name}" is already on this account')

        existing.append(contact)
        data['contacts'] = existing
        if not repo.upsert_account_data(target['id'], user_id, data, target['updated_at']):
            raise HttpError(409, 'Account was modified by another request. Please retry.')
        self._ok({'saved': True, 'contact': contact})
