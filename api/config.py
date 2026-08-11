"""GET  /api/config  -> {"config": <cfg>, "complete": bool}
POST /api/config  -> save cfg for the current user"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, user_or_401
from _lib.db import get_db


def _is_complete(cfg: dict) -> bool:
    u = cfg.get('user', {})
    c = cfg.get('company', {})
    products = [p for p in (c.get('products') or []) if p.get('name')]
    return bool(u.get('full_name') and u.get('email') and c.get('name') and products)


class handler(BaseHandler):
    @user_or_401
    def do_GET(self, user_id):
        db = get_db()
        row = db.table('configs').select('data').eq('user_id', user_id).maybe_single().execute()
        cfg = (row.data or {}).get('data', {}) if row and row.data else {}
        self._ok({'config': cfg, 'complete': _is_complete(cfg)})

    @user_or_401
    def do_POST(self, user_id):
        cfg = self._body()
        if not isinstance(cfg, dict):
            return self._err(400, 'Config body must be a JSON object')
        db = get_db()
        db.table('configs').upsert(
            {'user_id': user_id, 'data': cfg},
            on_conflict='user_id',
        ).execute()
        self._ok({'saved': True, 'complete': _is_complete(cfg)})
