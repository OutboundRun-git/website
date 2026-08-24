-- Phase 1: admin allowlist + is_admin on profiles.
-- Every user currently in auth.users becomes an admin (per Kim 2026-08-24).
-- Going forward, new users get is_admin=true iff their email is in admin_allowlist.

-- ---------- profiles.is_admin ----------
alter table public.profiles
  add column if not exists is_admin boolean not null default false;

-- ---------- admin_allowlist ----------
create table if not exists public.admin_allowlist (
  email      text primary key,
  added_by   uuid references auth.users(id) on delete set null,
  added_at   timestamptz not null default now()
);

alter table public.admin_allowlist enable row level security;
-- No policies: only service_role can read/write. Client code should never
-- touch this table directly; admin membership is decided by the trigger.

-- ---------- seed: every existing auth.users email + dcarew1 ----------
insert into public.admin_allowlist(email)
  select lower(email) from auth.users where email is not null
union
  select lower('dcarew1@gmail.com')
on conflict (email) do nothing;

-- ---------- backfill: every existing profile becomes admin ----------
update public.profiles
  set is_admin = true
  where id in (select id from auth.users where email is not null);

-- ---------- handle_new_user(): consult allowlist on signup ----------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_is_admin boolean;
begin
  select exists(
    select 1 from public.admin_allowlist
    where lower(email) = lower(new.email)
  ) into v_is_admin;

  insert into public.profiles(id, email, is_admin)
    values (new.id, new.email, coalesce(v_is_admin, false))
    on conflict (id) do update set is_admin = excluded.is_admin;

  insert into public.configs(user_id, data)
    values (new.id, '{"email":{"sender":"clipboard","cta_length_minutes":20}}'::jsonb)
    on conflict (user_id) do nothing;

  return new;
end;
$$;
