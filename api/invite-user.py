"""POST /api/invite-user
Admin-only. Body: { email: string, company_id: uuid, role?: 'member'|'manager' }
Inserts a pending_invites row and sends a Supabase magic-link invite.
When the invited user signs in, handle_new_user() consumes the row and
assigns company_id + role."""
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib.admin import require_admin
from _lib.db import get_db


_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        require_admin(user_id)
        body = self._body()

        email = (body.get('email') or '').strip().lower()
        if not _EMAIL_RE.match(email):
            raise HttpError(400, 'Invalid email address')

        company_id = (body.get('company_id') or '').strip()
        if not _UUID_RE.match(company_id):
            raise HttpError(400, 'Invalid company id')

        role = (body.get('role') or 'member').strip().lower()
        if role not in ('member', 'manager'):
            raise HttpError(400, 'Role must be member or manager')

        db = get_db()

        # Confirm the company exists (RLS is service_role so this always sees it).
        company = (db.table('companies')
            .select('id, name')
            .eq('id', company_id)
            .limit(1)
            .execute()).data or []
        if not company:
            raise HttpError(404, 'Company not found')

        # Insert / update the pending invite (upsert on email pk).
        db.table('pending_invites').upsert({
            'email': email,
            'company_id': company_id,
            'role': role,
            'invited_by': user_id,
        }, on_conflict='email').execute()

        # Send the magic-link email. If the user already exists in auth.users,
        # this errors — surface a clear message instead of a 500.
        try:
            db.auth.admin.invite_user_by_email(email, {
                'data': {'invited_by_admin_id': user_id, 'company_id': company_id, 'role': role}
            })
        except Exception as e:
            msg = str(e).lower()
            if 'already been registered' in msg or 'already exists' in msg:
                # User exists — invite path is for NEW users. Roll back the
                # pending_invites row and tell the admin to edit instead.
                db.table('pending_invites').delete().eq('email', email).execute()
                raise HttpError(
                    409,
                    'That email already has an account. Use "Edit user" to change '
                    'their company or role.',
                )
            raise HttpError(500, 'Failed to send invite email')

        self._ok({'email': email, 'company_id': company_id, 'role': role})
