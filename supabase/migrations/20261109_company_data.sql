-- Phase 1 (partial): company-scoped config sources.
--
-- Adds companies.data jsonb — a free-form bag of settings owned by the company,
-- edited by company admins (role='manager') or platform admins (is_admin=true).
--
-- Expected keys today:
--   credible_external_sources     text[]  (SEC EDGAR, Bloomberg, etc.)
--   internal_sources              text[]  (CRM, deal notes, analytics)
--   contact_discovery_sources     text[]  (Apollo, LinkedIn SN, ZoomInfo)
--
-- Prompts.py prefers these when non-empty, else falls back to the caller's
-- per-user config so existing single-user setups keep working while we migrate.

alter table public.companies
  add column if not exists data jsonb not null default '{}'::jsonb;

-- RLS: company members may read their company's data; admins + managers may write.
drop policy if exists companies_data_read on public.companies;
create policy companies_data_read on public.companies
  for select
  using (id = public.current_user_company_id() or public.current_user_is_admin());

drop policy if exists companies_data_update on public.companies;
create policy companies_data_update on public.companies
  for update
  using (
    public.current_user_is_admin()
    or (id = public.current_user_company_id() and public.current_user_role() = 'manager')
  )
  with check (
    public.current_user_is_admin()
    or (id = public.current_user_company_id() and public.current_user_role() = 'manager')
  );
