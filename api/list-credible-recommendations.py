"""GET /api/list-credible-recommendations
Returns every row in credible_source_recommendations ordered by category +
display_order. Any authenticated user can read."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, endpoint
from _lib.db import get_db


class handler(BaseHandler):
    @endpoint
    def do_GET(self, user_id: str):
        resp = (get_db().table('credible_source_recommendations')
            .select('id, name, url, description, category, display_order')
            .order('category')
            .order('display_order')
            .execute())
        self._ok({'recommendations': resp.data or []})
