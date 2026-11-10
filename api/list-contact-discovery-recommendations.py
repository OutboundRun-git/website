"""GET /api/list-contact-discovery-recommendations"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, endpoint
from _lib import repo


class handler(BaseHandler):
    @endpoint
    def do_GET(self, user_id: str):
        self._ok({'recommendations': repo.list_contact_discovery_recommendations()})
