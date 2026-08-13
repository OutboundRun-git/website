"""JWT verification. Errors are logged server-side, never leaked to the client.

Prior version returned f'Token verification failed: {e}' to the browser, which
could echo the token itself if Supabase ever included it in an error message.
"""
import logging
import re
import threading

from supabase import create_client, Client

from _lib import env


log = logging.getLogger(__name__)

_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)

_auth_client: Client | None = None
_lock = threading.Lock()


def _get_auth_client() -> Client:
    global _auth_client
    if _auth_client is None:
        with _lock:
            if _auth_client is None:
                _auth_client = create_client(env.SUPABASE_URL, env.SUPABASE_ANON_KEY)
    return _auth_client


class AuthError(Exception):
    def __init__(self, message: str = 'Unauthorized', status: int = 401):
        super().__init__(message)
        self.status = status
        self.message = message


def require_user(handler) -> str:
    """Extract user_id from Authorization: Bearer <jwt>. Returns UUID string.
    Raises AuthError with a generic public message on any failure."""
    auth = handler.headers.get('Authorization') or handler.headers.get('authorization') or ''
    if not auth.startswith('Bearer '):
        raise AuthError('Missing bearer token')
    token = auth[len('Bearer '):].strip()
    if not token:
        raise AuthError('Empty bearer token')

    try:
        resp = _get_auth_client().auth.get_user(token)
    except Exception:
        log.exception('supabase.auth.get_user failed')
        raise AuthError('Invalid or expired session')

    user = getattr(resp, 'user', None)
    if user is None and isinstance(resp, dict):
        user = resp.get('user')
    if not user:
        raise AuthError('Invalid or expired session')

    user_id = getattr(user, 'id', None) or (user.get('id') if isinstance(user, dict) else None)
    if not user_id or not _UUID_RE.match(str(user_id)):
        raise AuthError('Invalid session')
    return str(user_id)
