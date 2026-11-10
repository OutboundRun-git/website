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
    data = rows[0].get('data') or {}
    # Unwrap legacy double-nested shape caused by a pre-v2.9.2 POST bug
    # where the entire {"config": <cfg>} wrapper was saved as the config.
    while (
        isinstance(data, dict)
        and set(data.keys()) == {'config'}
        and isinstance(data.get('config'), dict)
    ):
        data = data['config']
    return data if isinstance(data, dict) else {}


def save_config(user_id: str, cfg: dict) -> None:
    # Never persist the ephemeral `_company_data` back onto the user row.
    clean = {k: v for k, v in cfg.items() if k != '_company_data'}
    get_db().table('configs').upsert(
        {'user_id': user_id, 'data': clean},
        on_conflict='user_id',
    ).execute()


def load_prompt_context(user_id: str) -> dict:
    """Returns the user's config MERGED with their company's shared sources
    and the platform-curated credible-source recommendations.

    Soft-fails on the company lookup: if the profile or companies query errors
    (bad test mocks, RLS edge, deleted company), returns the plain user cfg
    rather than taking down the research path."""
    cfg = get_config(user_id)
    try:
        cid = _get_user_company_id(user_id)
        if cid:
            cfg['_company_data'] = get_company_data(cid)
    except Exception:
        pass
    try:
        cd = cfg.setdefault('_company_data', {})
        cd['_recommendations'] = list_credible_recommendations()
        cd['_internal_recommendations'] = list_internal_recommendations()
        cd['_contact_discovery_recommendations'] = list_contact_discovery_recommendations()
    except Exception:
        pass
    return cfg


def _list_recs(table: str) -> list[dict]:
    resp = (get_db().table(table)
        .select('id, name, url, category, display_order')
        .order('category')
        .order('display_order')
        .execute())
    return resp.data or []


def list_credible_recommendations() -> list[dict]:
    return _list_recs('credible_source_recommendations')


def list_internal_recommendations() -> list[dict]:
    return _list_recs('internal_source_recommendations')


def list_contact_discovery_recommendations() -> list[dict]:
    return _list_recs('contact_discovery_recommendations')


def _get_user_company_id(user_id: str) -> str | None:
    resp = (get_db().table('profiles')
        .select('company_id')
        .eq('id', user_id)
        .limit(1)
        .execute())
    rows = resp.data or []
    return rows[0].get('company_id') if rows else None


def get_company_data(company_id: str) -> dict:
    resp = (get_db().table('companies')
        .select('data')
        .eq('id', company_id)
        .limit(1)
        .execute())
    rows = resp.data or []
    return (rows[0].get('data') or {}) if rows else {}


def update_company_data(company_id: str, data: dict) -> None:
    get_db().table('companies').update({'data': data}).eq('id', company_id).execute()


def get_user_profile_full(user_id: str) -> dict | None:
    """is_admin, company_id, role — used to gate company-data endpoints."""
    resp = (get_db().table('profiles')
        .select('is_admin, company_id, role')
        .eq('id', user_id)
        .limit(1)
        .execute())
    rows = resp.data or []
    return rows[0] if rows else None


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


def delete_account_by_number(user_id: str, account_number: str) -> bool:
    """Delete a single account by account_number. Returns True if a row was deleted."""
    resp = (get_db().table('accounts')
        .delete()
        .eq('user_id', user_id)
        .eq('data->>account_number', account_number)
        .execute())
    return bool(resp.data)


def delete_user(user_id: str) -> None:
    """Delete the user's auth row. ON DELETE CASCADE removes profiles, configs,
    accounts, and jobs."""
    get_db().auth.admin.delete_user(user_id)


# ============================================================================
# gmail_connections (one row per user; refresh_token never leaves the server)
# ============================================================================

def save_gmail_connection(user_id: str, refresh_token: str, email_addr: str) -> None:
    get_db().table('gmail_connections').upsert(
        {'user_id': user_id, 'refresh_token': refresh_token, 'email': email_addr},
        on_conflict='user_id',
    ).execute()


def get_gmail_connection(user_id: str) -> dict | None:
    """Server-side only. Returns full row including refresh_token, or None."""
    resp = (get_db().table('gmail_connections')
        .select('user_id, refresh_token, email, connected_at')
        .eq('user_id', user_id)
        .limit(1)
        .execute())
    rows = resp.data or []
    return rows[0] if rows else None


def get_gmail_status(user_id: str) -> dict:
    """Browser-safe. Returns {connected: bool, email: str|None} — never
    exposes the refresh_token."""
    row = get_gmail_connection(user_id)
    if not row:
        return {'connected': False, 'email': None}
    return {'connected': True, 'email': row.get('email')}


def delete_gmail_connection(user_id: str) -> None:
    get_db().table('gmail_connections').delete().eq('user_id', user_id).execute()


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
