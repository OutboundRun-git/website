"""GET /api/job-status?job_id=<uuid>
Returns the current state of a background job. Used for reconnect recovery
when the user closes the tab during a long Claude call."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, user_or_401
from _lib.db import get_db


class handler(BaseHandler):
    @user_or_401
    def do_GET(self, user_id):
        job_id = self._query('job_id')
        if not job_id:
            return self._err(400, 'job_id query param is required')
        db = get_db()
        row = db.table('jobs').select('id, kind, status, result, error, updated_at').eq('id', job_id).eq('user_id', user_id).maybe_single().execute()
        if not row or not row.data:
            return self._err(404, 'job not found')
        self._ok(row.data)
