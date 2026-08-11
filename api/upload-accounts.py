"""POST /api/upload-accounts
Body: {csv: str, mode: "merge" | "replace"}
Parses a CSV, inserts/upserts one accounts row per line."""
import csv
import io
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.http import BaseHandler, user_or_401
from _lib.db import get_db


NAME_ALIASES = ('account_name', 'name', 'account', 'company', 'company_name')
NUMBER_ALIASES = ('account_number', 'number', 'id')


def _first(row: dict, keys: tuple) -> str:
    for k in keys:
        for candidate in (k, k.lower(), k.upper(), k.title()):
            if candidate in row and (row[candidate] or '').strip():
                return row[candidate].strip()
    return ''


class handler(BaseHandler):
    @user_or_401
    def do_POST(self, user_id):
        body = self._body()
        csv_text = (body.get('csv') or '').strip()
        mode = body.get('mode', 'merge')
        if not csv_text:
            return self._err(400, 'Missing csv field')

        try:
            reader = csv.DictReader(io.StringIO(csv_text))
        except Exception as e:
            return self._err(400, f'CSV parse error: {e}')

        rows_in = list(reader)
        if not rows_in:
            return self._err(400, 'CSV had no data rows')

        db = get_db()

        if mode == 'replace':
            db.table('accounts').delete().eq('user_id', user_id).execute()
            existing_numbers = set()
        else:
            existing = db.table('accounts').select('data').eq('user_id', user_id).execute()
            existing_numbers = {
                (r['data'].get('account_number') or '').strip().upper()
                for r in (existing.data or [])
            }

        # Compute next auto-number starting after the max existing ACC-NNNNN
        max_seq = 0
        for n in existing_numbers:
            if n.startswith('ACC-'):
                try:
                    max_seq = max(max_seq, int(n.split('-', 1)[1]))
                except ValueError:
                    pass

        added = []
        skipped = 0
        seq = max_seq
        for r in rows_in:
            r = {k: (v or '') for k, v in r.items()}
            name = _first(r, NAME_ALIASES)
            if not name:
                continue
            number = _first(r, NUMBER_ALIASES)
            if not number:
                seq += 1
                number = f'ACC-{seq:05d}'
            if number.upper() in existing_numbers:
                skipped += 1
                continue
            acc_data = {
                'account_number': number,
                'account_name': name,
                'industry': (r.get('industry') or r.get('Industry') or '').strip(),
                'website': (r.get('website') or r.get('Website') or '').strip(),
                'crm_id': (r.get('crm_id') or r.get('CRM_ID') or '').strip(),
                'notes': (r.get('notes') or r.get('Notes') or '').strip(),
                'team': [],
                'contacts': [],
                'gtm_products': [],
                'hypothesis': '',
                'research': '',
            }
            added.append({'user_id': user_id, 'data': acc_data})
            existing_numbers.add(number.upper())

        if added:
            db.table('accounts').insert(added).execute()

        self._ok({
            'added': len(added),
            'skipped_duplicates': skipped,
            'total': len(existing_numbers),
        })
