"""GET /api/health
Diagnostic endpoint (no auth) that verifies the deployment: env vars set,
Supabase client can connect, tables exist. Returns detailed error info on
failure so we can debug from curl without needing a JWT.

Safe to expose because it only reports on the deployment's own state; it does
not expose user data.
"""
import os
import sys
import traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler


class handler(BaseHandler):
    def do_GET(self):
        info = {
            'env': {
                'SUPABASE_URL_set':              bool(os.environ.get('SUPABASE_URL')),
                'SUPABASE_URL_prefix':           (os.environ.get('SUPABASE_URL') or '')[:30],
                'SUPABASE_ANON_KEY_set':         bool(os.environ.get('SUPABASE_ANON_KEY')),
                'SUPABASE_ANON_KEY_prefix':      (os.environ.get('SUPABASE_ANON_KEY') or '')[:15],
                'SUPABASE_SERVICE_ROLE_KEY_set': bool(os.environ.get('SUPABASE_SERVICE_ROLE_KEY')),
                'SUPABASE_SERVICE_ROLE_KEY_prefix': (os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or '')[:15],
                'ANTHROPIC_API_KEY_set':         bool(os.environ.get('ANTHROPIC_API_KEY')),
                'ANTHROPIC_API_KEY_prefix':      (os.environ.get('ANTHROPIC_API_KEY') or '')[:12],
            },
            'python_version': sys.version,
        }

        try:
            from _lib.db import get_db
            db = get_db()
            info['db_client_created'] = True
        except Exception as e:
            info['db_client_created'] = False
            info['db_client_error'] = f'{type(e).__name__}: {e}'
            info['db_client_traceback'] = traceback.format_exc()
            self._ok(info)
            return

        for table in ('profiles', 'configs', 'accounts', 'jobs'):
            try:
                res = db.table(table).select('*').limit(1).execute()
                info[f'{table}_query'] = 'ok'
                info[f'{table}_sample_rows'] = len(res.data or [])
            except Exception as e:
                info[f'{table}_query'] = 'error'
                info[f'{table}_error'] = f'{type(e).__name__}: {e}'
                info[f'{table}_traceback'] = traceback.format_exc()

        try:
            from anthropic import Anthropic
            _ = Anthropic()
            info['anthropic_client_created'] = True
        except Exception as e:
            info['anthropic_client_created'] = False
            info['anthropic_client_error'] = f'{type(e).__name__}: {e}'

        self._ok(info)
