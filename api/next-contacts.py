"""POST /api/next-contacts
Body: {account_number, count?, focus_area?}
Finds N additional target contacts, dedupes vs existing (skipping empty emails)."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo
from _lib.claude import run_claude_json, ClaudeError
from _lib.prompts import build_next_contacts_prompt


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        body = self._body()
        acc_num = (body.get('account_number') or '').strip()
        try:
            count = int(body.get('count') or 5)
        except (TypeError, ValueError):
            raise HttpError(400, 'count must be an integer')
        focus_area = (body.get('focus_area') or '').strip() or None

        if not acc_num:
            raise HttpError(400, 'account_number is required')
        if count < 1 or count > 20:
            raise HttpError(400, 'count must be between 1 and 20')

        cfg = repo.load_prompt_context(user_id)
        target = repo.get_account_by_number(user_id, acc_num)
        if not target:
            raise HttpError(404, f'Account {acc_num} not found')

        job_id = repo.start_job(user_id, 'next_contacts')

        try:
            prompt = build_next_contacts_prompt(cfg, target['data'], count=count, focus_area=focus_area)
            result = run_claude_json(prompt)
        except ClaudeError as e:
            repo.fail_job(job_id, str(e))
            raise HttpError(502, str(e))

        new_contacts = result.get('contacts') or [] if isinstance(result, dict) else []
        if not isinstance(new_contacts, list):
            new_contacts = []

        # Dedupe by email (case-insensitive). When a contact has no email,
        # also dedupe by name against other email-less contacts so a user-
        # added contact without an email isn't rediscovered by the AI.
        data = dict(target['data'])
        existing = list(data.get('contacts') or [])
        existing_emails = {
            (c.get('email') or '').lower().strip()
            for c in existing
            if (c.get('email') or '').strip()
        }
        existing_emailless_names = {
            (c.get('name') or '').strip().lower()
            for c in existing
            if not (c.get('email') or '').strip() and (c.get('name') or '').strip()
        }
        added: list[dict] = []
        for c in new_contacts:
            if not isinstance(c, dict):
                continue
            email = (c.get('email') or '').lower().strip()
            name  = (c.get('name')  or '').strip().lower()
            if email and email in existing_emails:
                continue
            if not email and name and name in existing_emailless_names:
                continue
            if email:
                existing_emails.add(email)
            elif name:
                existing_emailless_names.add(name)
            added.append(c)

        data['contacts'] = existing + added
        if not repo.upsert_account_data(target['id'], user_id, data, target['updated_at']):
            repo.fail_job(job_id, 'concurrent modification')
            raise HttpError(409, 'Account was modified by another request. Please retry.')

        result_out = {'contacts': added, 'added_count': len(added)}
        repo.finish_job(job_id, result_out)
        self._ok({'job_id': job_id, 'status': 'done', 'result': result_out})
