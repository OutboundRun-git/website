"""POST /api/delete-integration-connection
Body: {connection_id}
Removes the connection row. Platform admin OR company manager required."""
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo
from _lib.db import get_db


_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        body = self._body()
        conn_id = (body.get('connection_id') or '').strip()
        if not _UUID_RE.match(conn_id):
            raise HttpError(400, 'connection_id must be a UUID')

        db = get_db()
        row = (db.table('integration_connections')
            .select('id, company_id')
            .eq('id', conn_id)
            .limit(1)
            .execute()).data or []
        if not row:
            raise HttpError(404, 'Connection not found')

        profile = repo.get_user_profile_full(user_id)
        if not profile:
            raise HttpError(403, 'Profile not found')
        is_admin = bool(profile.get('is_admin'))
        is_mgr = (profile.get('company_id') == row[0]['company_id'] and profile.get('role') == 'manager')
        if not (is_admin or is_mgr):
            raise HttpError(403, 'Only platform admins or company managers can delete')

        db.table('integration_connections').delete().eq('id', conn_id).execute()
        self._ok({'deleted': True})
