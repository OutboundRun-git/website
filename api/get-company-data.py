"""GET /api/get-company-data?company_id=<uuid>
Returns the company's shared config bag (credible_external_sources, etc.).
Gate: platform admin OR member of that company."""
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo
from urllib.parse import urlparse, parse_qs


_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)


class handler(BaseHandler):
    @endpoint
    def do_GET(self, user_id: str):
        qs = parse_qs(urlparse(self.path).query)
        company_id = (qs.get('company_id') or [''])[0].strip()
        if not _UUID_RE.match(company_id):
            raise HttpError(400, 'company_id must be a UUID')

        profile = repo.get_user_profile_full(user_id)
        if not profile:
            raise HttpError(403, 'Profile not found')
        is_admin = bool(profile.get('is_admin'))
        same_company = profile.get('company_id') == company_id
        if not (is_admin or same_company):
            raise HttpError(403, 'Not a member of that company')

        self._ok({'data': repo.get_company_data(company_id)})
