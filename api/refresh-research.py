"""POST /api/refresh-research
Body: {account_number}
Runs the web-research prompt only. Returns updated research HTML."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo
from _lib.claude import run_claude_html, ClaudeError
from _lib.prompts import build_research_prompt


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

        job_id = repo.start_job(user_id, 'research')

        try:
            prompt = build_research_prompt(cfg, target['data'])
            html = run_claude_html(prompt)
        except ClaudeError as e:
            repo.fail_job(job_id, str(e))
            raise HttpError(502, str(e))

        if not html or not html.strip():
            repo.fail_job(job_id, 'empty result')
            raise HttpError(502, 'AI returned empty research')

        data = dict(target['data'])
        data['research'] = html
        if not repo.upsert_account_data(target['id'], user_id, data, target['updated_at']):
            repo.fail_job(job_id, 'concurrent modification')
            raise HttpError(409, 'Account was modified by another request. Please retry.')

        result = {'research': html}
        repo.finish_job(job_id, result)
        self._ok({'job_id': job_id, 'status': 'done', 'result': result})
