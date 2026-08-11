-- OutboundRun app tables for the hosted (multi-tenant) version.
-- Each authenticated user gets one config row and many account rows.
-- Row-level security: every user can only read/write their own rows.

-- ---------- profiles ----------
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy own_profile on public.profiles
  for all using (auth.uid() = id) with check (auth.uid() = id);

-- ---------- configs (one row per user) ----------
create table if not exists public.configs (
  user_id uuid primary key references auth.users(id) on delete cascade,
  data jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.configs enable row level security;

create policy own_config on public.configs
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------- accounts (many rows per user) ----------
create table if not exists public.accounts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  data jsonb not null,
  updated_at timestamptz not null default now()
);

create index if not exists accounts_user_idx on public.accounts(user_id);

alter table public.accounts enable row level security;

create policy own_accounts on public.accounts
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------- jobs (background job status; for reconnect recovery) ----------
create table if not exists public.jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  kind text not null,
  status text not null default 'running',
  result jsonb,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists jobs_user_idx on public.jobs(user_id);

alter table public.jobs enable row level security;

create policy own_jobs on public.jobs
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------- signup trigger ----------
-- When a new user signs up via magic link, auto-create their profile
-- and an empty config with clipboard-only email defaults.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles(id, email)
    values (new.id, new.email)
    on conflict (id) do nothing;

  insert into public.configs(user_id, data)
    values (new.id, '{"email":{"sender":"clipboard","cta_length_minutes":20}}'::jsonb)
    on conflict (user_id) do nothing;

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
