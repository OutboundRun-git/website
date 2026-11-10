"""POST /api/draft-contact-email
Body: {account_number, contact_email (or contact_name)}
Generates a persona-tailored subject + body + hook for a single contact
using the account's Research Summary + GTM Hypothesis as grounding.
Updates the contact in place."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo
from _lib.claude import run_claude_json, ClaudeError
from _lib.prompts import build_single_contact_email_prompt


_EMAIL_FIELDS = ('subject', 'body', 'hook',
                 'flag', 'flag_reason', 'flag_categories',
                 'human_flag', 'human_reason',
                 'exec_flag', 'exec_reason')


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
        if not (data.get('research') or '').strip():
            raise HttpError(400, 'No research available. Run Execute/Refresh Research Summary first.')
        if not (data.get('hypothesis') or '').strip():
            raise HttpError(400, 'No GTM hypothesis available. Run Execute/Refresh GTM first.')

        contacts = list(data.get('contacts') or [])
        idx = -1
        for i, c in enumerate(contacts):
            hit = (contact_email and (c.get('email') or '').lower() == contact_email) \
               or (contact_name and (c.get('name') or '') == contact_name)
            if hit:
                idx = i
                break
        if idx < 0:
            raise HttpError(404, 'Contact not found on this account')
        contact = contacts[idx]
        if not (contact.get('title') or '').strip():
            raise HttpError(400, 'Contact is missing a title; add one via Edit before drafting')

        cfg = repo.load_prompt_context(user_id)
        prompt = build_single_contact_email_prompt(cfg, data, contact)
        try:
            result = run_claude_json(prompt)
        except ClaudeError as e:
            raise HttpError(502, str(e))
        if not isinstance(result, dict):
            raise HttpError(502, 'AI returned malformed output')

        for k in _EMAIL_FIELDS:
            if k in result:
                contact[k] = result[k]
        contacts[idx] = contact
        data['contacts'] = contacts
        if not repo.upsert_account_data(target['id'], user_id, data, target['updated_at']):
            raise HttpError(409, 'Account was modified by another request. Please retry.')
        self._ok({'drafted': True, 'contact': contact})
