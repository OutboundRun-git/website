"""POST /api/delete-all-products
Clears config.company.products for the caller. No body required.
Returns {deleted: count_before}."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, endpoint
from _lib import repo


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        cfg = repo.get_config(user_id)
        company = cfg.setdefault('company', {})
        before = len(company.get('products') or [])
        company['products'] = []
        repo.save_config(user_id, cfg)
        self._ok({'deleted': before})
