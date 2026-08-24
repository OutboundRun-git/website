"""POST /api/update-company
Admin-only. Body: { id: uuid, name?: string, slug?: string }
Renames or reslugs an existing company."""
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib.admin import require_admin
from _lib.db import get_db


_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)
_SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,62}$')


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        require_admin(user_id)
        body = self._body()

        company_id = (body.get('id') or '').strip()
        if not _UUID_RE.match(company_id):
            raise HttpError(400, 'Invalid company id')

        patch = {}
        if 'name' in body:
            name = (body.get('name') or '').strip()
            if not name or len(name) > 200:
                raise HttpError(400, 'Company name must be 1-200 characters')
            patch['name'] = name
        if 'slug' in body:
            slug = (body.get('slug') or '').strip().lower()
            if slug and not _SLUG_RE.match(slug):
                raise HttpError(400, 'Slug must be lowercase letters, digits, and hyphens')
            patch['slug'] = slug or None

        if not patch:
            raise HttpError(400, 'Nothing to update')

        resp = (get_db().table('companies')
            .update(patch)
            .eq('id', company_id)
            .execute())
        rows = resp.data or []
        if not rows:
            raise HttpError(404, 'Company not found')
        self._ok({'company': rows[0]})
