"""POST /api/next-contacts
Body: {account_number, count?, focus_area?}
Finds N additional target contacts at the account, dedupes vs existing."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, user_or_401
from _lib.db import get_db
from _lib.claude import run_claude_json
from _lib.prompts import build_next_contacts_prompt


def _find_account(db, user_id: str, acc_num: str):
    rows = db.table('accounts').select('id, data').eq('user_id', user_id).execute()
    for r in (rows.data or []):
        if (r['data'].get('account_number') or '').strip().upper() == acc_num.upper():
            return r
    return None


class handler(BaseHandler):
    @user_or_401
    def do_POST(self, user_id):
        body = self._body()
        acc_num = (body.get('account_number') or '').strip()
        count = int(body.get('count') or 5)
        focus_area = (body.get('focus_area') or '').strip() or None
        if not acc_num:
            return self._err(400, 'account_number is required')
        if count < 1 or count > 20:
            return self._err(400, 'count must be between 1 and 20')

        db = get_db()
        cfg_row = db.table('configs').select('data').eq('user_id', user_id).maybe_single().execute()
        cfg = (cfg_row.data or {}).get('data', {}) if cfg_row and cfg_row.data else {}

        target = _find_account(db, user_id, acc_num)
        if not target:
            return self._err(404, f'Account {acc_num} not found')

        job = db.table('jobs').insert({
            'user_id': user_id, 'kind': 'next_contacts', 'status': 'running',
        }).execute()
        job_id = job.data[0]['id'] if job.data else None

        try:
            prompt = build_next_contacts_prompt(cfg, target['data'], count=count, focus_area=focus_area)
            result = run_claude_json(prompt)
        except Exception as e:
            if job_id:
                db.table('jobs').update({'status': 'error', 'error': str(e)}).eq('id', job_id).execute()
            return self._err(500, f'Claude failed: {e}')

        new_contacts = result.get('contacts') or []
        if not isinstance(new_contacts, list):
            new_contacts = []

        # Dedupe against existing contacts by email (case-insensitive)
        data = target['data']
        existing = data.get('contacts') or []
        existing_emails = {(c.get('email') or '').lower().strip() for c in existing}
        added = []
        for c in new_contacts:
            email = (c.get('email') or '').lower().strip()
            if email and email in existing_emails:
                continue
            existing_emails.add(email)
            added.append(c)

        data['contacts'] = existing + added
        db.table('accounts').update({'data': data}).eq('id', target['id']).execute()

        result_out = {'contacts': added, 'added_count': len(added)}
        if job_id:
            db.table('jobs').update({'status': 'done', 'result': result_out}).eq('id', job_id).execute()

        self._ok({'job_id': job_id, 'status': 'done', 'result': result_out})
