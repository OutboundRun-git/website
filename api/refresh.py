"""POST /api/refresh
Body: {account_number}
Full refresh: team + contacts + research + GTM + emails. Runs synchronously
on Fluid Compute (maxDuration=300s)."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo
from _lib.claude import run_claude_json, ClaudeError
from _lib.prompts import build_refresh_prompt


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        body = self._body()
        acc_num = (body.get('account_number') or '').strip()
        if not acc_num:
            raise HttpError(400, 'account_number is required')

        cfg = repo.get_config(user_id)
        target = repo.get_account_by_number(user_id, acc_num)
        if not target:
            raise HttpError(404, f'Account {acc_num} not found')

        job_id = repo.start_job(user_id, 'refresh')

        try:
            prompt = build_refresh_prompt(cfg, target['data'])
            result = run_claude_json(prompt)
        except ClaudeError as e:
            repo.fail_job(job_id, str(e))
            raise HttpError(502, str(e))

        if not isinstance(result, dict):
            repo.fail_job(job_id, 'malformed AI output')
            raise HttpError(502, 'AI returned malformed output')

        data = dict(target['data'])
        for key in ('team', 'contacts', 'gtm_products', 'hypothesis', 'research'):
            if key in result:
                data[key] = result[key]

        if not repo.upsert_account_data(target['id'], user_id, data, target['updated_at']):
            repo.fail_job(job_id, 'concurrent modification')
            raise HttpError(409, 'Account was modified by another request. Please retry.')

        repo.finish_job(job_id, result)
        self._ok({'job_id': job_id, 'status': 'done', 'result': result})
