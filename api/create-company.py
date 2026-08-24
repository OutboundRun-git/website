"""POST /api/create-company
Admin-only. Body: { name: string, slug?: string }
Returns the created company."""
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib.admin import require_admin
from _lib.db import get_db


_SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,62}$')


def _slugify(s: str) -> str:
    s = re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
    return s[:63] or 'company'


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        require_admin(user_id)
        body = self._body()

        name = (body.get('name') or '').strip()
        if not name or len(name) > 200:
            raise HttpError(400, 'Company name must be 1-200 characters')

        slug = (body.get('slug') or '').strip().lower()
        if slug:
            if not _SLUG_RE.match(slug):
                raise HttpError(400, 'Slug must be lowercase letters, digits, and hyphens')
        else:
            slug = _slugify(name)

        resp = (get_db().table('companies')
            .insert({'name': name, 'slug': slug, 'created_by': user_id})
            .execute())
        rows = resp.data or []
        if not rows:
            raise HttpError(500, 'Failed to create company')
        self._ok({'company': rows[0]})
