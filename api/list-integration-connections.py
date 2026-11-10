"""GET /api/list-integration-connections?company_id=<uuid>
Returns the connection metadata for every integration the company has configured.
NEVER returns the plaintext api_key — only has_api_key (bool) and the other
non-secret fields."""
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo
from _lib.db import get_db
from urllib.parse import urlparse, parse_qs


_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)


class handler(BaseHandler):
    @endpoint
    def do_GET(self, user_id: str):
        qs = parse_qs(urlparse(self.path).query)
        company_id = (qs.get('company_id') or [''])[0].strip()
        if not _UUID_RE.match(company_id):
            raise HttpError(400, 'company_id must be a UUID')

        profile = repo.get_user_profile_full(user_id)
        if not profile:
            raise HttpError(403, 'Profile not found')
        if not (bool(profile.get('is_admin')) or profile.get('company_id') == company_id):
            raise HttpError(403, 'Not a member of that company')

        rows = (get_db().table('integration_connections')
            .select('id, integration_kind, integration_rec_id, api_url, notes, updated_at, api_key_plaintext_todo_encrypt')
            .eq('company_id', company_id)
            .execute()).data or []

        out = []
        for r in rows:
            out.append({
                'id': r['id'],
                'integration_kind': r['integration_kind'],
                'integration_rec_id': r['integration_rec_id'],
                'api_url': r.get('api_url') or '',
                'notes': r.get('notes') or '',
                'updated_at': r.get('updated_at'),
                'has_api_key': bool((r.get('api_key_plaintext_todo_encrypt') or '').strip()),
            })
        self._ok({'connections': out})
