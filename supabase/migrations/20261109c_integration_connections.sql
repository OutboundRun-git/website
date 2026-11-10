-- Phase 1d (DEMO STUB): per-company technical connection config for each
-- recommended source (credible + internal + contact_discovery).
--
-- SECURITY NOTE — api_key is stored PLAINTEXT as api_key_plaintext_todo_encrypt.
-- This is labeled loudly so the Phase 2 migration can swap it for a Fernet-
-- encrypted bytea column + decryption RPC without ambiguity. Do NOT treat
-- the current state as production-ready for customer-owned secrets.
--
-- Rows are keyed by (company_id, integration_kind, integration_rec_id) so a
-- given company has at most one connection per recommendation.

create table if not exists public.integration_connections (
  id                                 uuid primary key default gen_random_uuid(),
  company_id                         uuid not null references public.companies(id) on delete cascade,
  integration_kind                   text not null check (integration_kind in ('credible', 'internal', 'contact_discovery')),
  integration_rec_id                 uuid not null,
  api_key_plaintext_todo_encrypt     text,
  api_url                            text,
  notes                              text,
  created_at                         timestamptz not null default now(),
  updated_at                         timestamptz not null default now(),
  unique (company_id, integration_kind, integration_rec_id)
);

create index if not exists idx_integration_connections_company
  on public.integration_connections (company_id);

alter table public.integration_connections enable row level security;

-- SELECT: platform admins + any user whose profile.company_id matches.
drop policy if exists ic_read on public.integration_connections;
create policy ic_read on public.integration_connections
  for select
  using (
    public.current_user_is_admin()
    or company_id = public.current_user_company_id()
  );

-- INSERT / UPDATE / DELETE: platform admins + company managers of the row's company.
drop policy if exists ic_write on public.integration_connections;
create policy ic_write on public.integration_connections
  for all
  using (
    public.current_user_is_admin()
    or (company_id = public.current_user_company_id() and public.current_user_role() = 'manager')
  )
  with check (
    public.current_user_is_admin()
    or (company_id = public.current_user_company_id() and public.current_user_role() = 'manager')
  );

-- Simple updated_at trigger so the API can display when a connection was last touched.
create or replace function public._bump_integration_connection_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists trg_ic_updated_at on public.integration_connections;
create trigger trg_ic_updated_at
  before update on public.integration_connections
  for each row execute function public._bump_integration_connection_updated_at();
