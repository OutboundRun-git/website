"""POST /api/send-email
Body: {to, subject, body}
Hosted version is CLIPBOARD-ONLY. Returns the payload for the UI to copy.
No SMTP, no Gmail, no external send."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, user_or_401
from _lib.db import get_db

from _lib.prompts import prompt_context  # only for signature purposes if needed


def _signature(cfg: dict) -> str:
    u = cfg.get('user', {})
    override = (u.get('signature_override') or '').strip()
    if override:
        return override
    lines = ['--', u.get('full_name', '')]
    role = u.get('role_title', '')
    company = cfg.get('company', {}).get('name', '')
    if role and company:
        lines.append(f'{role}, {company}')
    elif role:
        lines.append(role)
    elif company:
        lines.append(company)
    for addr in u.get('address_lines') or []:
        if addr:
            lines.append(addr)
    if u.get('phone'):
        lines.append(f'Mobile: {u["phone"]}')
    if u.get('email'):
        lines.append(f'Email: {u["email"]}')
    return '\n'.join(l for l in lines if l is not None)


class handler(BaseHandler):
    @user_or_401
    def do_POST(self, user_id):
        body = self._body()
        to = (body.get('to') or '').strip()
        subject = (body.get('subject') or '').strip()
        email_body = body.get('body') or ''

        if not to:
            return self._err(400, 'to is required')
        if not subject:
            return self._err(400, 'subject is required')
        if not email_body:
            return self._err(400, 'body is required')

        db = get_db()
        row = db.table('configs').select('data').eq('user_id', user_id).maybe_single().execute()
        cfg = (row.data or {}).get('data', {}) if row and row.data else {}

        # Append signature if not already present in the body
        sig = _signature(cfg)
        if sig and sig not in email_body:
            full_body = f'{email_body.rstrip()}\n\n{sig}'
        else:
            full_body = email_body

        self._ok({
            'sent': False,
            'via': 'clipboard',
            'to': to,
            'subject': subject,
            'body': full_body,
        })
