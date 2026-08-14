"""GET  /api/config  -> {"config": <cfg>, "complete": bool, "gmail": {connected, email}}
POST /api/config  -> save cfg for the current user"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, endpoint
from _lib import repo
from _lib import env


def _is_complete(cfg: dict) -> bool:
    u = cfg.get('user') or {}
    c = cfg.get('company') or {}
    products = [
        p for p in (c.get('products') or [])
        if isinstance(p, dict) and (p.get('name') or '').strip()
    ]
    return bool(
        (u.get('full_name') or '').strip()
        and (u.get('email') or '').strip()
        and (c.get('name') or '').strip()
        and products
    )


class handler(BaseHandler):
    @endpoint
    def do_GET(self, user_id: str):
        cfg = repo.get_config(user_id)
        gmail_status = repo.get_gmail_status(user_id) if env.gmail_configured() else {'connected': False, 'email': None}
        self._ok({
            'config': cfg,
            'complete': _is_complete(cfg),
            'gmail': gmail_status,
            'gmail_available': env.gmail_configured(),
        })

    @endpoint
    def do_POST(self, user_id: str):
        cfg = self._body()
        repo.save_config(user_id, cfg)
        self._ok({'saved': True, 'complete': _is_complete(cfg)})
