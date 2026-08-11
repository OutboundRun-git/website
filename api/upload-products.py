"""POST /api/upload-products
Body: {products: [{name, short_desc}, ...]}
Merges the products list into the user's config."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, user_or_401
from _lib.db import get_db


class handler(BaseHandler):
    @user_or_401
    def do_POST(self, user_id):
        body = self._body()
        products = body.get('products')
        if not isinstance(products, list):
            return self._err(400, 'products must be an array of {name, short_desc}')
        cleaned = [
            {
                'name': (p.get('name') or '').strip(),
                'short_desc': (p.get('short_desc') or '').strip(),
            }
            for p in products
            if isinstance(p, dict) and (p.get('name') or '').strip()
        ]
        if not cleaned:
            return self._err(400, 'At least one product with a name is required')

        db = get_db()
        row = db.table('configs').select('data').eq('user_id', user_id).maybe_single().execute()
        cfg = (row.data or {}).get('data', {}) if row and row.data else {}
        cfg.setdefault('company', {})['products'] = cleaned
        db.table('configs').upsert(
            {'user_id': user_id, 'data': cfg},
            on_conflict='user_id',
        ).execute()
        self._ok({'saved': True, 'products': cleaned})
