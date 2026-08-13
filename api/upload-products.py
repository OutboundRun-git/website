"""POST /api/upload-products
Body: {products: [{name, short_desc}, ...]}
Merges the products list into the user's config."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo


MAX_PRODUCTS = 50


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        body = self._body()
        products = body.get('products')
        if not isinstance(products, list):
            raise HttpError(400, 'products must be an array of {name, short_desc}')
        if len(products) > MAX_PRODUCTS:
            raise HttpError(413, f'products exceeds {MAX_PRODUCTS} items')

        cleaned = [
            {
                'name': (p.get('name') or '').strip()[:200],
                'short_desc': (p.get('short_desc') or '').strip()[:500],
            }
            for p in products
            if isinstance(p, dict) and (p.get('name') or '').strip()
        ]
        if not cleaned:
            raise HttpError(400, 'At least one product with a name is required')

        cfg = repo.get_config(user_id)
        cfg.setdefault('company', {})['products'] = cleaned
        repo.save_config(user_id, cfg)
        self._ok({'saved': True, 'products': cleaned})
