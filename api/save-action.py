"""POST /api/save-action
Body: {account_number, contact_email (or contact_name), action, date}
Marks a contact's outreach action + date."""
import os
import sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, user_or_401
from _lib.db import get_db


class handler(BaseHandler):
    @user_or_401
    def do_POST(self, user_id):
        body = self._body()
        acc_num = (body.get('account_number') or '').strip()
        contact_email = (body.get('contact_email') or '').strip().lower()
        contact_name = (body.get('contact_name') or '').strip()
        action = (body.get('action') or '').strip()
        date = body.get('date') or datetime.now(timezone.utc).date().isoformat()

        if not acc_num:
            return self._err(400, 'account_number is required')
        if not action:
            return self._err(400, 'action is required')
        if not (contact_email or contact_name):
            return self._err(400, 'contact_email or contact_name is required')

        db = get_db()
        rows = db.table('accounts').select('id, data').eq('user_id', user_id).execute()
        target = None
        for r in (rows.data or []):
            if (r['data'].get('account_number') or '').strip().upper() == acc_num.upper():
                target = r
                break
        if not target:
            return self._err(404, f'Account {acc_num} not found')

        data = target['data']
        contacts = data.get('contacts') or []
        updated = 0
        for c in contacts:
            match = False
            if contact_email and (c.get('email') or '').lower() == contact_email:
                match = True
            elif contact_name and (c.get('name') or '') == contact_name:
                match = True
            if match:
                c['action'] = action
                c['action_date'] = date
                updated += 1
        if updated == 0:
            return self._err(404, 'Contact not found on this account')

        data['contacts'] = contacts
        db.table('accounts').update({'data': data}).eq('id', target['id']).execute()
        self._ok({'saved': True, 'updated': updated})
