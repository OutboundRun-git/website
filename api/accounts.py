"""GET /api/accounts
Returns the current user's full list of accounts, ordered by account_number.
Replaces the old static-file fetch of data/generated.json."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, user_or_401
from _lib.db import get_db


class handler(BaseHandler):
    @user_or_401
    def do_GET(self, user_id):
        db = get_db()
        rows = db.table('accounts').select('id, data, updated_at').eq('user_id', user_id).order('updated_at', desc=False).execute()
        out = []
        for r in (rows.data or []):
            d = dict(r['data'])
            d['_id'] = r['id']
            d['_updated_at'] = r['updated_at']
            out.append(d)
        out.sort(key=lambda a: (a.get('account_number') or ''))
        self._ok({'accounts': out})
