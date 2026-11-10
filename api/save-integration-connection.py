"""POST /api/save-integration-connection
Body: {
  company_id, integration_kind ('credible'|'internal'|'contact_discovery'),
  integration_rec_id, api_key?, api_url?, notes?
}
Upserts a connection row keyed by (company_id, integration_kind, integration_rec_id).
Platform admin OR company manager required. api_key stored as plaintext for
the demo stub — see migration comment."""
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo
from _lib.db import get_db


_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)
ALLOWED_KINDS = {'credible', 'internal', 'contact_discovery'}

MAX_KEY_LEN = 2000
MAX_URL_LEN = 2000
MAX_NOTES_LEN = 4000


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        body = self._body()
        company_id = (body.get('company_id') or '').strip()
        kind = (body.get('integration_kind') or '').strip()
        rec_id = (body.get('integration_rec_id') or '').strip()
        if not _UUID_RE.match(company_id):
            raise HttpError(400, 'company_id must be a UUID')
        if kind not in ALLOWED_KINDS:
            raise HttpError(400, f'integration_kind must be one of {sorted(ALLOWED_KINDS)}')
        if not _UUID_RE.match(rec_id):
            raise HttpError(400, 'integration_rec_id must be a UUID')

        profile = repo.get_user_profile_full(user_id)
        if not profile:
            raise HttpError(403, 'Profile not found')
        is_admin = bool(profile.get('is_admin'))
        is_mgr = (profile.get('company_id') == company_id and profile.get('role') == 'manager')
        if not (is_admin or is_mgr):
            raise HttpError(403, 'Only platform admins or company managers can edit')

        def _str(key, max_len):
            v = body.get(key)
            if v is None:
                return None
            if not isinstance(v, str):
                raise HttpError(400, f'{key} must be a string')
            return v.strip()[:max_len]

        api_key = _str('api_key', MAX_KEY_LEN)
        api_url = _str('api_url', MAX_URL_LEN)
        notes   = _str('notes',   MAX_NOTES_LEN)

        db = get_db()
        existing = (db.table('integration_connections')
            .select('id, api_key_plaintext_todo_encrypt')
            .eq('company_id', company_id)
            .eq('integration_kind', kind)
            .eq('integration_rec_id', rec_id)
            .limit(1)
            .execute()).data or []

        # Preserve the existing stored key if the client didn't send one.
        # (The list endpoint never returns the raw key, so the UI typically
        # submits blank to indicate "leave alone"; explicit empty string means
        # "clear it.")
        payload = {
            'company_id': company_id,
            'integration_kind': kind,
            'integration_rec_id': rec_id,
            'api_url': api_url or '',
            'notes': notes or '',
        }
        if api_key is not None:
            # Treat whitespace-only as "clear"
            payload['api_key_plaintext_todo_encrypt'] = api_key

        if existing:
            db.table('integration_connections').update(payload).eq('id', existing[0]['id']).execute()
            self._ok({'saved': True, 'id': existing[0]['id']})
        else:
            if 'api_key_plaintext_todo_encrypt' not in payload:
                payload['api_key_plaintext_todo_encrypt'] = ''
            resp = db.table('integration_connections').insert(payload).execute()
            new_id = (resp.data or [{}])[0].get('id')
            self._ok({'saved': True, 'id': new_id})
