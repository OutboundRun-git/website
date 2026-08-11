"""POST /api/refresh-gtm
Body: {account_number}
Runs only the GTM-hypothesis prompt. Requires existing research on the account."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, user_or_401
from _lib.db import get_db
from _lib.claude import run_claude_json
from _lib.prompts import build_gtm_prompt


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
        if not target['data'].get('research'):
            return self._err(400, 'No research available. Refresh Research Summary first.')

        job = db.table('jobs').insert({
            'user_id': user_id, 'kind': 'gtm', 'status': 'running',
        }).execute()
        job_id = job.data[0]['id'] if job.data else None

        try:
            prompt = build_gtm_prompt(cfg, target['data'])
            result = run_claude_json(prompt)
        except Exception as e:
            if job_id:
                db.table('jobs').update({'status': 'error', 'error': str(e)}).eq('id', job_id).execute()
            return self._err(500, f'Claude failed: {e}')

        data = target['data']
        if 'hypothesis' in result:
            data['hypothesis'] = result['hypothesis']
        if 'gtm_products' in result:
            data['gtm_products'] = result['gtm_products']
        db.table('accounts').update({'data': data}).eq('id', target['id']).execute()

        if job_id:
            db.table('jobs').update({'status': 'done', 'result': result}).eq('id', job_id).execute()

        self._ok({'job_id': job_id, 'status': 'done', 'result': result})
