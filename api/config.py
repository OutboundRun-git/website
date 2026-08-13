"""GET  /api/config  -> {"config": <cfg>, "complete": bool}
POST /api/config  -> save cfg for the current user"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, endpoint
from _lib import repo


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
        self._ok({'config': cfg, 'complete': _is_complete(cfg)})

    @endpoint
    def do_POST(self, user_id: str):
        cfg = self._body()
        repo.save_config(user_id, cfg)
        self._ok({'saved': True, 'complete': _is_complete(cfg)})
