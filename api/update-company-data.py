"""POST /api/update-company-data
Body: {company_id, data: {...}}
Gate: platform admin OR manager of that company."""
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo


_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)

ALLOWED_STRING_LIST_KEYS = {
    'credible_external_sources',
    'internal_sources',
    'contact_discovery_sources',
}
ALLOWED_UUID_LIST_KEYS = {
    'credible_source_opt_outs',
    'internal_source_opt_outs',
    'contact_discovery_opt_outs',
}
ALLOWED_PRODUCT_LIST_KEYS = {
    'products',
}
MAX_LIST = 200
MAX_ITEM_LEN = 400
MAX_PRODUCTS = 50
MAX_PRODUCT_NAME_LEN = 200
MAX_PRODUCT_DESC_LEN = 500


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        body = self._body()
        company_id = (body.get('company_id') or '').strip()
        if not _UUID_RE.match(company_id):
            raise HttpError(400, 'company_id must be a UUID')

        raw = body.get('data')
        if not isinstance(raw, dict):
            raise HttpError(400, 'data must be an object')

        profile = repo.get_user_profile_full(user_id)
        if not profile:
            raise HttpError(403, 'Profile not found')
        is_admin = bool(profile.get('is_admin'))
        is_mgr = (
            profile.get('company_id') == company_id
            and profile.get('role') == 'manager'
        )
        if not (is_admin or is_mgr):
            raise HttpError(403, 'Only platform admins or company managers can edit')

        cleaned: dict = {}
        for key, val in raw.items():
            if key in ALLOWED_STRING_LIST_KEYS:
                if not isinstance(val, list):
                    raise HttpError(400, f'{key} must be an array of strings')
                if len(val) > MAX_LIST:
                    raise HttpError(413, f'{key} exceeds {MAX_LIST} items')
                items = []
                for v in val:
                    if not isinstance(v, str):
                        continue
                    s = v.strip()[:MAX_ITEM_LEN]
                    if s:
                        items.append(s)
                cleaned[key] = items
            elif key in ALLOWED_UUID_LIST_KEYS:
                if not isinstance(val, list):
                    raise HttpError(400, f'{key} must be an array of uuids')
                if len(val) > MAX_LIST:
                    raise HttpError(413, f'{key} exceeds {MAX_LIST} items')
                ids = []
                for v in val:
                    if isinstance(v, str) and _UUID_RE.match(v):
                        ids.append(v)
                cleaned[key] = ids
            elif key in ALLOWED_PRODUCT_LIST_KEYS:
                if not isinstance(val, list):
                    raise HttpError(400, f'{key} must be an array of {{name, short_desc}} objects')
                if len(val) > MAX_PRODUCTS:
                    raise HttpError(413, f'{key} exceeds {MAX_PRODUCTS} items')
                products = []
                for p in val:
                    if not isinstance(p, dict):
                        continue
                    name = (p.get('name') or '').strip()[:MAX_PRODUCT_NAME_LEN] if isinstance(p.get('name'), str) else ''
                    if not name:
                        continue
                    desc = (p.get('short_desc') or '').strip()[:MAX_PRODUCT_DESC_LEN] if isinstance(p.get('short_desc'), str) else ''
                    products.append({'name': name, 'short_desc': desc})
                cleaned[key] = products

        # Merge with existing so unspecified keys are preserved.
        existing = repo.get_company_data(company_id)
        merged = {**existing, **cleaned}
        repo.update_company_data(company_id, merged)
        self._ok({'data': merged})
