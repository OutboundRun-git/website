-- Performance + safety migration to support the audit rewrite.
--
-- 1. GIN-friendly btree index on (user_id, data->>'account_number') so
--    per-account lookups stop doing "SELECT all accounts, filter in Python".
-- 2. auto-updated_at trigger so optimistic concurrency on the accounts table
--    catches concurrent writes.

-- ---------- index for direct JSONB account_number lookups ----------
create index if not exists accounts_user_number_idx
  on public.accounts (user_id, ((data->>'account_number')));

-- ---------- auto-bump updated_at on any row modification ----------
create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists accounts_touch_updated_at on public.accounts;
create trigger accounts_touch_updated_at
  before update on public.accounts
  for each row execute function public.touch_updated_at();

drop trigger if exists configs_touch_updated_at on public.configs;
create trigger configs_touch_updated_at
  before update on public.configs
  for each row execute function public.touch_updated_at();

drop trigger if exists jobs_touch_updated_at on public.jobs;
create trigger jobs_touch_updated_at
  before update on public.jobs
  for each row execute function public.touch_updated_at();
