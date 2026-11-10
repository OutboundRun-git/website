"""POST /api/test-integration-connection
Body: {connection_id}
Stub — returns a 'not yet implemented' response for the demo. Per-vendor
validation (Salesforce OAuth check, HubSpot /oauth/v1/access-tokens/{token},
Snowflake SHOW WAREHOUSES, etc.) is Phase 2 work."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        body = self._body()
        conn_id = (body.get('connection_id') or '').strip()
        if not conn_id:
            raise HttpError(400, 'connection_id is required')
        self._ok({
            'status': 'not_implemented',
            'message': 'Connection test not yet implemented. Per-vendor validation ships in Phase 2.',
        })
