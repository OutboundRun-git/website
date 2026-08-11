"""POST /api/refresh-research
Body: {account_number}
Runs only the web-research prompt. Returns updated research HTML."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, user_or_401
from _lib.db import get_db
from _lib.claude import run_claude_html
from _lib.prompts import build_research_prompt


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
        if not acc_num:
            return self._err(400, 'account_number is required')

        db = get_db()
        cfg_row = db.table('configs').select('data').eq('user_id', user_id).maybe_single().execute()
        cfg = (cfg_row.data or {}).get('data', {}) if cfg_row and cfg_row.data else {}

        target = _find_account(db, user_id, acc_num)
        if not target:
            return self._err(404, f'Account {acc_num} not found')

        job = db.table('jobs').insert({
            'user_id': user_id, 'kind': 'research', 'status': 'running',
        }).execute()
        job_id = job.data[0]['id'] if job.data else None

        try:
            prompt = build_research_prompt(cfg, target['data'])
            html = run_claude_html(prompt)
        except Exception as e:
            if job_id:
                db.table('jobs').update({'status': 'error', 'error': str(e)}).eq('id', job_id).execute()
            return self._err(500, f'Claude failed: {e}')

        if not html or not html.strip():
            if job_id:
                db.table('jobs').update({'status': 'error', 'error': 'empty result'}).eq('id', job_id).execute()
            return self._err(500, 'Claude returned empty research')

        data = target['data']
        data['research'] = html
        db.table('accounts').update({'data': data}).eq('id', target['id']).execute()

        if job_id:
            db.table('jobs').update({'status': 'done', 'result': {'research': html}}).eq('id', job_id).execute()

        self._ok({'job_id': job_id, 'status': 'done', 'result': {'research': html}})
