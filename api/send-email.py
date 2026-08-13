"""POST /api/send-email
Body: {to, subject, body}
Hosted version is CLIPBOARD-ONLY. Returns the payload for the UI to copy.
No SMTP, no Gmail, no external send path."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo


def _signature(cfg: dict) -> str:
    u = cfg.get('user') or {}
    override = (u.get('signature_override') or '').strip()
    if override:
        return override
    lines = ['--', u.get('full_name', '')]
    role = u.get('role_title', '')
    company = (cfg.get('company') or {}).get('name', '')
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
    @endpoint
    def do_POST(self, user_id: str):
        body = self._body()
        to = (body.get('to') or '').strip()
        subject = (body.get('subject') or '').strip()
        email_body = body.get('body') or ''

        if not to:
            raise HttpError(400, 'to is required')
        if not subject:
            raise HttpError(400, 'subject is required')
        if not email_body:
            raise HttpError(400, 'body is required')

        cfg = repo.get_config(user_id)
        sig = _signature(cfg)
        full_body = f'{email_body.rstrip()}\n\n{sig}' if sig and sig not in email_body else email_body

        self._ok({
            'sent': False,
            'via': 'clipboard',
            'to': to,
            'subject': subject,
            'body': full_body,
        })
