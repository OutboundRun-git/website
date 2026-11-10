"""GET /api/list-companies
Scope:
  - Platform admin (is_admin=true): returns every company with member_count.
  - Company manager:               returns ONLY their own company (for
                                   populating the Company Config picker).
  - Everyone else:                 empty list."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, endpoint
from _lib import repo
from _lib.db import get_db


class handler(BaseHandler):
    @endpoint
    def do_GET(self, user_id: str):
        profile = repo.get_user_profile_full(user_id)
        if not profile:
            self._ok({'companies': []})
            return

        db = get_db()
        is_admin = bool(profile.get('is_admin'))
        cid = profile.get('company_id')

        if is_admin:
            companies = (db.table('companies')
                .select('id, name, slug, created_at')
                .order('created_at', desc=True)
                .execute()).data or []
            profiles = (db.table('profiles')
                .select('company_id')
                .not_.is_('company_id', 'null')
                .execute()).data or []
            counts = {}
            for p in profiles:
                counts[p.get('company_id')] = counts.get(p.get('company_id'), 0) + 1
            for c in companies:
                c['member_count'] = counts.get(c['id'], 0)
            self._ok({'companies': companies})
            return

        if profile.get('role') == 'manager' and cid:
            rows = (db.table('companies')
                .select('id, name, slug, created_at')
                .eq('id', cid)
                .limit(1)
                .execute()).data or []
            for c in rows:
                c['member_count'] = 1
            self._ok({'companies': rows})
            return

        self._ok({'companies': []})
