"""POST /api/upload-accounts
Body: {csv: str, mode: "merge" | "replace"}"""
import csv
import io
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, HttpError, endpoint
from _lib import repo


MAX_CSV_BYTES = 2 * 1024 * 1024   # 2MB
MAX_ROWS = 5_000
NAME_ALIASES = ('account_name', 'name', 'account', 'company', 'company_name')
NUMBER_ALIASES = ('account_number', 'number', 'id')


def _first(row: dict, keys: tuple) -> str:
    for k in keys:
        for candidate in (k, k.lower(), k.upper(), k.title()):
            v = row.get(candidate)
            if v and str(v).strip():
                return str(v).strip()
    return ''


class handler(BaseHandler):
    @endpoint
    def do_POST(self, user_id: str):
        body = self._body()
        csv_text = (body.get('csv') or '').strip()
        mode = body.get('mode', 'merge')
        if mode not in ('merge', 'replace'):
            raise HttpError(400, 'mode must be "merge" or "replace"')
        if not csv_text:
            raise HttpError(400, 'csv field is required')
        if len(csv_text.encode('utf-8')) > MAX_CSV_BYTES:
            raise HttpError(413, f'CSV exceeds {MAX_CSV_BYTES // 1024}KB limit')

        # Strip UTF-8 BOM if present (Excel exports include it and it corrupts
        # the first column name).
        if csv_text.startswith('﻿'):
            csv_text = csv_text.lstrip('﻿')

        try:
            reader = csv.DictReader(io.StringIO(csv_text))
        except csv.Error as e:
            raise HttpError(400, f'CSV parse error: {e}')

        rows_in = list(reader)
        if not rows_in:
            raise HttpError(400, 'CSV had no data rows')
        if len(rows_in) > MAX_ROWS:
            raise HttpError(413, f'CSV exceeds {MAX_ROWS} rows')

        # Pre-check: does any accepted name column exist? If not, bail
        # LOUDLY with a helpful message instead of silently importing 0 rows.
        detected_cols = [c for c in (rows_in[0].keys() if rows_in else []) if c]
        detected_lower = {c.strip().lower() for c in detected_cols}
        if not any(alias in detected_lower for alias in NAME_ALIASES):
            raise HttpError(
                422,
                f'CSV is missing the account_name column. Accepted: '
                f'{", ".join(NAME_ALIASES)}. Detected: '
                f'{", ".join(detected_cols) if detected_cols else "(no columns parsed; check delimiter — must be comma)"}.'
            )

        existing_numbers: set[str] = set()
        if mode == 'replace':
            repo.delete_all_accounts(user_id)
        else:
            for acc in repo.list_accounts(user_id):
                num = (acc.get('account_number') or '').strip().upper()
                if num:
                    existing_numbers.add(num)

        max_seq = 0
        for n in existing_numbers:
            if n.startswith('ACC-'):
                try:
                    max_seq = max(max_seq, int(n.split('-', 1)[1]))
                except ValueError:
                    pass

        added: list[dict] = []
        skipped = 0
        seq = max_seq
        for r in rows_in:
            r = {k: (v or '') for k, v in r.items() if k is not None}
            name = _first(r, NAME_ALIASES)
            if not name or len(name) > 200:
                continue
            number = _first(r, NUMBER_ALIASES)
            if not number:
                seq += 1
                number = f'ACC-{seq:05d}'
            elif len(number) > 60:
                continue
            key = number.upper()
            if key in existing_numbers:
                skipped += 1
                continue
            added.append({
                'user_id': user_id,
                'data': {
                    'account_number': number,
                    'account_name': name,
                    'industry': (r.get('industry') or r.get('Industry') or '').strip()[:200],
                    'website': (r.get('website') or r.get('Website') or '').strip()[:400],
                    'crm_id': (r.get('crm_id') or r.get('CRM_ID') or '').strip()[:200],
                    'notes': (r.get('notes') or r.get('Notes') or '').strip()[:2000],
                    'team': [], 'contacts': [], 'gtm_products': [],
                    'hypothesis': '', 'research': '',
                },
            })
            existing_numbers.add(key)

        repo.insert_accounts(added)
        self._ok({
            'added': len(added),
            'skipped_duplicates': skipped,
            'total': len(existing_numbers),
        })
