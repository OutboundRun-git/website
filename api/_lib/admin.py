"""Admin gate. Extends require_user() by also verifying is_admin=true on
the caller's profile row. Used by every /api/ endpoint that admins call."""
from _lib.db import get_db
from _lib.http import HttpError


def require_admin(user_id: str) -> None:
    """Raises HttpError(403) if the caller is not flagged is_admin=true."""
    resp = (get_db().table('profiles')
        .select('is_admin')
        .eq('id', user_id)
        .limit(1)
        .execute())
    rows = resp.data or []
    if not rows or not rows[0].get('is_admin'):
        raise HttpError(403, 'Admin access required')
