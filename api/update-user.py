"""POST /api/update-user
Admin-only. Body: { id: uuid, company_id?: uuid|null, role?: 'member'|'manager', is_admin?: bool }
Updates a target user's profile fields. Admins may promote/demote other admins,
but the last admin cannot demote themselves (safety guard)."""
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib.admin import require_admin
from _lib.db import get_db


_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        require_admin(user_id)
        body = self._body()

        target_id = (body.get('id') or '').strip()
        if not _UUID_RE.match(target_id):
            raise HttpError(400, 'Invalid user id')

        patch = {}

        if 'company_id' in body:
            cid = body.get('company_id')
            if cid is None or cid == '':
                patch['company_id'] = None
            else:
                cid = str(cid).strip()
                if not _UUID_RE.match(cid):
                    raise HttpError(400, 'Invalid company id')
                patch['company_id'] = cid

        if 'role' in body:
            role = (body.get('role') or '').strip().lower()
            if role not in ('member', 'manager'):
                raise HttpError(400, 'Role must be member or manager')
            patch['role'] = role

        if 'is_admin' in body:
            new_admin = bool(body.get('is_admin'))
            patch['is_admin'] = new_admin

            if not new_admin and target_id == user_id:
                # Prevent self-demotion if you'd be the last admin.
                db = get_db()
                admins = (db.table('profiles')
                    .select('id')
                    .eq('is_admin', True)
                    .execute()).data or []
                if len(admins) <= 1:
                    raise HttpError(
                        400,
                        'You are the last admin and cannot demote yourself.',
                    )

        if not patch:
            raise HttpError(400, 'Nothing to update')

        # Enforce the DB check constraint client-side too, so we return a
        # friendlier error than a 500 with a Postgres constraint name.
        if patch.get('is_admin') is False and patch.get('company_id') is None:
            # If only one of these was in the patch, we still need to fetch
            # the current row to know the effective post-update state.
            current = (get_db().table('profiles')
                .select('is_admin, company_id')
                .eq('id', target_id)
                .limit(1)
                .execute()).data or []
            if not current:
                raise HttpError(404, 'User not found')
            merged = {**current[0], **patch}
            if not merged.get('is_admin') and not merged.get('company_id'):
                raise HttpError(
                    400,
                    'Non-admin users must belong to a company. Set a company or keep is_admin=true.',
                )

        resp = (get_db().table('profiles')
            .update(patch)
            .eq('id', target_id)
            .execute())
        rows = resp.data or []
        if not rows:
            raise HttpError(404, 'User not found')
        self._ok({'user': rows[0]})
