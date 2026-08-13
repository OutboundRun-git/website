"""GET /api/job-status?job_id=<uuid>
Returns background job state. Used for reconnect recovery."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo


class handler(BaseHandler):
    @endpoint
    def do_GET(self, user_id: str):
        job_id = self._query('job_id')
        if not job_id:
            raise HttpError(400, 'job_id query param is required')
        job = repo.get_job(user_id, job_id)
        if not job:
            raise HttpError(404, 'job not found')
        self._ok(job)
