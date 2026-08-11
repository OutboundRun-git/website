"""JWT verification helper. Every endpoint calls require_user(handler) first."""
import os
from supabase import create_client, Client


_auth_client: Client | None = None


def _get_auth_client() -> Client:
    global _auth_client
    if _auth_client is None:
        url = os.environ['SUPABASE_URL']
        key = os.environ['SUPABASE_ANON_KEY']
        _auth_client = create_client(url, key)
    return _auth_client


class AuthError(Exception):
    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.status = status


def require_user(handler) -> str:
    """Extract user_id from Authorization: Bearer <jwt> header on a BaseHTTPRequestHandler.
    Returns user_id (str). Raises AuthError(401) on any failure."""
    auth = handler.headers.get('Authorization') or handler.headers.get('authorization') or ''
    if not auth.startswith('Bearer '):
        raise AuthError('Missing bearer token')
    token = auth[len('Bearer '):].strip()
    if not token:
        raise AuthError('Empty bearer token')
    client = _get_auth_client()
    try:
        resp = client.auth.get_user(token)
    except Exception as e:
        raise AuthError(f'Token verification failed: {e}')
    user = getattr(resp, 'user', None)
    if user is None and isinstance(resp, dict):
        user = resp.get('user')
    if not user:
        raise AuthError('Token did not resolve to a user')
    user_id = getattr(user, 'id', None) or (user.get('id') if isinstance(user, dict) else None)
    if not user_id:
        raise AuthError('User has no id')
    return user_id
