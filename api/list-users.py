"""GET /api/list-users
Admin-only. Returns every user (auth + profile + company)."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, endpoint
from _lib.admin import require_admin
from _lib.db import get_db


class handler(BaseHandler):
    @endpoint
    def do_GET(self, user_id: str):
        require_admin(user_id)
        db = get_db()

        # auth.users has last_sign_in_at + confirmed_at; not exposed via
        # PostgREST by default, but supabase-py's auth.admin.list_users hits
        # the admin API for us.
        try:
            auth_page = db.auth.admin.list_users()
            auth_users = auth_page if isinstance(auth_page, list) else (
                getattr(auth_page, 'users', None) or []
            )
        except Exception:
            auth_users = []

        auth_map = {}
        for u in auth_users:
            uid = getattr(u, 'id', None) or (u.get('id') if isinstance(u, dict) else None)
            if not uid:
                continue
            auth_map[str(uid)] = {
                'last_sign_in_at': (
                    getattr(u, 'last_sign_in_at', None)
                    if not isinstance(u, dict) else u.get('last_sign_in_at')
                ),
                'confirmed_at': (
                    getattr(u, 'confirmed_at', None)
                    if not isinstance(u, dict) else u.get('confirmed_at')
                ),
            }

        profiles = (db.table('profiles')
            .select('id, email, is_admin, company_id, role, created_at')
            .order('created_at', desc=True)
            .execute()).data or []

        pending = (db.table('pending_invites')
            .select('email, company_id, role, invited_at')
            .execute()).data or []

        companies = (db.table('companies')
            .select('id, name, slug')
            .execute()).data or []
        company_map = {c['id']: c for c in companies}

        for p in profiles:
            aux = auth_map.get(p['id'], {})
            p['last_sign_in_at'] = aux.get('last_sign_in_at')
            p['confirmed_at'] = aux.get('confirmed_at')
            p['company'] = company_map.get(p.get('company_id')) if p.get('company_id') else None

        for inv in pending:
            inv['company'] = company_map.get(inv.get('company_id'))

        self._ok({
            'users': profiles,
            'pending_invites': pending,
        })
