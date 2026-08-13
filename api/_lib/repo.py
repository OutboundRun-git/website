"""Data-access layer. All Supabase table shape lives here. Endpoints call
typed methods and never touch column names directly.

Fixes the N+1 pattern (fetch-all-then-filter-in-Python) by using the JSONB
->>path filter, which hits an index (see 20260813 migration).

Fixes read-modify-write races on accounts.data via optimistic locking on
updated_at.
"""
from typing import Any

from _lib.db import get_db


# ============================================================================
# configs (one row per user)
# ============================================================================

def get_config(user_id: str) -> dict:
    resp = (get_db().table('configs')
        .select('data')
        .eq('user_id', user_id)
        .limit(1)
        .execute())
    rows = resp.data or []
    if not rows:
        return {}
    return rows[0].get('data') or {}


def save_config(user_id: str, cfg: dict) -> None:
    get_db().table('configs').upsert(
        {'user_id': user_id, 'data': cfg},
        on_conflict='user_id',
    ).execute()


# ============================================================================
# accounts (many rows per user)
# ============================================================================

def list_accounts(user_id: str) -> list[dict]:
    resp = (get_db().table('accounts')
        .select('id, data, updated_at')
        .eq('user_id', user_id)
        .execute())
    out = []
    for r in (resp.data or []):
        data = r.get('data') or {}
        out.append({
            'id': r['id'],
            'updated_at': r.get('updated_at'),
            **data,
        })
    out.sort(key=lambda a: a.get('account_number') or '')
    return out


def get_account_by_number(user_id: str, account_number: str) -> dict | None:
    """Direct JSONB lookup. Uses the (user_id, data->>account_number) index."""
    resp = (get_db().table('accounts')
        .select('id, data, updated_at')
        .eq('user_id', user_id)
        .eq('data->>account_number', account_number)
        .limit(1)
        .execute())
    rows = resp.data or []
    return rows[0] if rows else None


def upsert_account_data(row_id: str, user_id: str, data: dict, expected_updated_at: str) -> bool:
    """Optimistic write. Returns True if the row was updated, False on stale
    (someone else wrote in between our read and our write)."""
    resp = (get_db().table('accounts')
        .update({'data': data})
        .eq('id', row_id)
        .eq('user_id', user_id)
        .eq('updated_at', expected_updated_at)
        .execute())
    return bool(resp.data)


def insert_accounts(rows: list[dict]) -> None:
    if rows:
        get_db().table('accounts').insert(rows).execute()


def delete_all_accounts(user_id: str) -> None:
    get_db().table('accounts').delete().eq('user_id', user_id).execute()


# ============================================================================
# jobs (background job status)
# ============================================================================

def start_job(user_id: str, kind: str) -> str | None:
    resp = get_db().table('jobs').insert({
        'user_id': user_id, 'kind': kind, 'status': 'running',
    }).execute()
    return resp.data[0]['id'] if resp.data else None


def finish_job(job_id: str | None, result: Any) -> None:
    if job_id:
        get_db().table('jobs').update(
            {'status': 'done', 'result': result}
        ).eq('id', job_id).execute()


def fail_job(job_id: str | None, error: str) -> None:
    if job_id:
        get_db().table('jobs').update(
            {'status': 'error', 'error': error}
        ).eq('id', job_id).execute()


def get_job(user_id: str, job_id: str) -> dict | None:
    resp = (get_db().table('jobs')
        .select('id, kind, status, result, error, updated_at')
        .eq('id', job_id)
        .eq('user_id', user_id)
        .limit(1)
        .execute())
    rows = resp.data or []
    return rows[0] if rows else None
