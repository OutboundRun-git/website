"""Supabase service-role client. ONLY use after require_user() has verified the caller.

Thread-safe singleton (Fluid Compute can share a Python process across
concurrent invocations).
"""
import threading

from supabase import create_client, Client

from _lib import env


_client: Client | None = None
_lock = threading.Lock()


def get_db() -> Client:
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = create_client(env.SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY)
    return _client
