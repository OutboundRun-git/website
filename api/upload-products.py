"""POST /api/upload-products
Two body shapes:
  (a) {products: [{name, short_desc}, ...]}         — legacy, replaces all
  (b) {csv: str, mode: 'merge' | 'replace'}         — CSV upload
      merge  = skip products whose name already exists (case-insensitive)
      replace = wipe and set from the CSV rows

CSV columns: name (required; aliases: product, product_name).
             short_desc (optional; aliases: description, desc)."""
import csv
import io
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo


MAX_PRODUCTS = 50
MAX_CSV_BYTES = 512 * 1024   # 512KB
NAME_ALIASES = ('name', 'product_name', 'product')
DESC_ALIASES = ('short_desc', 'description', 'desc')


def _first(row: dict, keys: tuple) -> str:
    for k in keys:
        for cand in (k, k.lower(), k.upper(), k.title()):
            v = row.get(cand)
            if v and str(v).strip():
                return str(v).strip()
    return ''


def _handle_csv(user_id: str, csv_text: str, mode: str):
    if mode not in ('merge', 'replace'):
        raise HttpError(400, 'mode must be "merge" or "replace"')
    if not csv_text:
        raise HttpError(400, 'csv field is required')
    if len(csv_text.encode('utf-8')) > MAX_CSV_BYTES:
        raise HttpError(413, f'CSV exceeds {MAX_CSV_BYTES // 1024}KB limit')

    if csv_text.startswith('﻿'):
        csv_text = csv_text.lstrip('﻿')

    try:
        reader = csv.DictReader(io.StringIO(csv_text))
    except csv.Error as e:
        raise HttpError(400, f'CSV parse error: {e}')

    rows_in = list(reader)
    if not rows_in:
        raise HttpError(400, 'CSV had no data rows')

    detected = [c for c in (rows_in[0].keys() if rows_in else []) if c]
    detected_lower = {c.strip().lower() for c in detected}
    if not any(a in detected_lower for a in NAME_ALIASES):
        raise HttpError(
            422,
            f'CSV is missing the name column. Accepted: '
            f'{", ".join(NAME_ALIASES)}. Detected: '
            f'{", ".join(detected) if detected else "(no columns parsed; check delimiter — must be comma)"}.'
        )

    cfg = repo.get_config(user_id)
    company = cfg.setdefault('company', {})
    existing = list(company.get('products') or [])

    if mode == 'replace':
        existing_by_key: dict[str, dict] = {}
        existing = []
    else:
        existing_by_key = {(p.get('name') or '').strip().lower(): p for p in existing}

    added: list[dict] = []
    skipped = 0
    for r in rows_in:
        r = {k: (v or '') for k, v in r.items() if k is not None}
        name = _first(r, NAME_ALIASES)
        if not name:
            continue
        name = name[:200]
        key = name.lower()
        if key in existing_by_key:
            skipped += 1
            continue
        short_desc = _first(r, DESC_ALIASES)[:500]
        product = {'name': name, 'short_desc': short_desc}
        existing_by_key[key] = product
        added.append(product)

    final = existing + added
    if len(final) > MAX_PRODUCTS:
        raise HttpError(413, f'Total products would exceed {MAX_PRODUCTS}')

    company['products'] = final
    repo.save_config(user_id, cfg)
    return {
        'added': len(added),
        'skipped_duplicates': skipped,
        'total': len(final),
        'products': final,
    }


def _handle_json(user_id: str, products) -> dict:
    if not isinstance(products, list):
        raise HttpError(400, 'products must be an array of {name, short_desc}')
    if len(products) > MAX_PRODUCTS:
        raise HttpError(413, f'products exceeds {MAX_PRODUCTS} items')

    cleaned = [
        {
            'name': (p.get('name') or '').strip()[:200],
            'short_desc': (p.get('short_desc') or '').strip()[:500],
        }
        for p in products
        if isinstance(p, dict) and (p.get('name') or '').strip()
    ]
    if not cleaned:
        raise HttpError(400, 'At least one product with a name is required')

    cfg = repo.get_config(user_id)
    cfg.setdefault('company', {})['products'] = cleaned
    repo.save_config(user_id, cfg)
    return {'saved': True, 'products': cleaned}


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        body = self._body()
        if 'csv' in body:
            result = _handle_csv(
                user_id,
                (body.get('csv') or '').strip(),
                body.get('mode', 'merge'),
            )
        else:
            result = _handle_json(user_id, body.get('products'))
        self._ok(result)
