-- Phase 2: company tenant model.
--
-- Adds companies, profiles.company_id, profiles.role, pending_invites.
-- RLS on accounts/configs/jobs/gmail_connections is INTENTIONALLY UNCHANGED
-- in this migration — Kim will land the RLS rewrite in Phase 2.5 once the
-- first non-admin user is imminent. Today everyone is admin, so per-user
-- RLS is functionally correct (admins hit prod data via the same API paths
-- their own JWT authenticates, and each admin has their own accounts).

-- ---------- companies ----------
create table if not exists public.companies (
  id           uuid primary key default gen_random_uuid(),
  name         text not null,
  slug         text unique,
  created_at   timestamptz not null default now(),
  created_by   uuid references auth.users(id) on delete set null
);

alter table public.companies enable row level security;

-- ---------- profiles: add company_id + role ----------
alter table public.profiles
  add column if not exists company_id uuid references public.companies(id) on delete set null,
  add column if not exists role       text  not null default 'member';

alter table public.profiles
  drop constraint if exists profiles_role_check;
alter table public.profiles
  add constraint profiles_role_check check (role in ('member', 'manager'));

-- Non-admins must belong to a company. Admins may have null company_id.
alter table public.profiles
  drop constraint if exists profiles_company_required_for_non_admin;
alter table public.profiles
  add constraint profiles_company_required_for_non_admin
  check (is_admin = true or company_id is not null);

-- ---------- pending_invites ----------
-- Populated by admin UI. When the invited user signs in, the trigger
-- consumes the row and assigns company_id + role, then deletes it.
create table if not exists public.pending_invites (
  email        text primary key,
  company_id   uuid not null references public.companies(id) on delete cascade,
  role         text not null default 'member' check (role in ('member', 'manager')),
  invited_by   uuid references auth.users(id) on delete set null,
  invited_at   timestamptz not null default now()
);

alter table public.pending_invites enable row level security;
-- No policies: only service_role touches this table (admin API endpoint).

-- ---------- helper functions (SECURITY DEFINER, bypass RLS on profiles) ----------
-- These are the single source of truth for admin/company/role checks.
-- Used by the app-side gate today; Phase 2.5 RLS policies will use them too.

create or replace function public.current_user_is_admin()
returns boolean
language sql
security definer
stable
set search_path = public
as $$
  select coalesce((select is_admin from public.profiles where id = auth.uid()), false);
$$;

create or replace function public.current_user_company_id()
returns uuid
language sql
security definer
stable
set search_path = public
as $$
  select company_id from public.profiles where id = auth.uid();
$$;

create or replace function public.current_user_role()
returns text
language sql
security definer
stable
set search_path = public
as $$
  select coalesce(role, 'member') from public.profiles where id = auth.uid();
$$;

create or replace function public.company_id_of_user(u uuid)
returns uuid
language sql
security definer
stable
set search_path = public
as $$
  select company_id from public.profiles where id = u;
$$;

-- ---------- companies RLS ----------
-- Admins: full CRUD. Members/managers: read their own company only.
drop policy if exists companies_admin_all on public.companies;
create policy companies_admin_all on public.companies
  for all
  using (public.current_user_is_admin())
  with check (public.current_user_is_admin());

drop policy if exists companies_read_own on public.companies;
create policy companies_read_own on public.companies
  for select
  using (id = public.current_user_company_id());

-- ---------- handle_new_user(): consume pending_invites + allowlist ----------
-- Precedence: pending_invites first (so an admin's per-user assignment wins),
-- then admin_allowlist (Kim/staff auto-admin), else default member with null
-- company (which will fail the check constraint UNLESS a company was set —
-- i.e., someone signing in via magic link without an invite AND not on the
-- allowlist can't complete signup, which is exactly the desired gate).
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_is_admin   boolean;
  v_invite     public.pending_invites;
  v_company_id uuid;
  v_role       text;
begin
  -- 1. Check for a pending invite
  select * into v_invite
    from public.pending_invites
    where lower(email) = lower(new.email);

  if v_invite.email is not null then
    v_company_id := v_invite.company_id;
    v_role       := v_invite.role;
  end if;

  -- 2. Check admin allowlist
  select exists(
    select 1 from public.admin_allowlist
    where lower(email) = lower(new.email)
  ) into v_is_admin;

  -- 3. Insert profile. If neither invite nor admin, this will fail the
  --    profiles_company_required_for_non_admin check and roll back the
  --    auth.users insert too (magic-link user rejected). That's the gate.
  insert into public.profiles(id, email, is_admin, company_id, role)
    values (
      new.id,
      new.email,
      coalesce(v_is_admin, false),
      v_company_id,
      coalesce(v_role, 'member')
    )
    on conflict (id) do update set
      is_admin   = excluded.is_admin,
      company_id = coalesce(excluded.company_id, public.profiles.company_id),
      role       = excluded.role;

  -- 4. Default config
  insert into public.configs(user_id, data)
    values (new.id, '{"email":{"sender":"clipboard","cta_length_minutes":20}}'::jsonb)
    on conflict (user_id) do nothing;

  -- 5. Consume the invite so it can't be reused
  if v_invite.email is not null then
    delete from public.pending_invites where lower(email) = lower(v_invite.email);
  end if;

  return new;
end;
$$;
