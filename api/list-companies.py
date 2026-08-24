"""GET /api/list-companies
Admin-only. Returns all companies with a member_count join."""
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

        companies = (db.table('companies')
            .select('id, name, slug, created_at')
            .order('created_at', desc=True)
            .execute()).data or []

        # Member count per company (cheap: single query, count in Python)
        profiles = (db.table('profiles')
            .select('company_id')
            .not_.is_('company_id', 'null')
            .execute()).data or []
        counts = {}
        for p in profiles:
            cid = p.get('company_id')
            counts[cid] = counts.get(cid, 0) + 1

        for c in companies:
            c['member_count'] = counts.get(c['id'], 0)

        self._ok({'companies': companies})
