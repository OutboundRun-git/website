-- Per-user Gmail OAuth connection. Kept in its own table (not configs.data)
-- because configs.data is round-tripped through the browser via GET /api/config
-- and POST /api/config, which would leak the refresh_token to the client and
-- also risk the user accidentally overwriting/deleting it.
--
-- This table is server-side only. Frontend gets connection *status* (connected +
-- email) via /api/config, never the refresh_token itself.

create table if not exists public.gmail_connections (
  user_id       uuid        primary key references auth.users(id) on delete cascade,
  refresh_token text        not null,
  email         text        not null,
  connected_at  timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

alter table public.gmail_connections enable row level security;

-- Users can see their own row (defense in depth; server always uses service_role
-- but we don't want a leak via the anon client to be catastrophic).
create policy own_gmail_connection on public.gmail_connections
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Auto-bump updated_at via the trigger we defined in 20260813
drop trigger if exists gmail_connections_touch_updated_at on public.gmail_connections;
create trigger gmail_connections_touch_updated_at
  before update on public.gmail_connections
  for each row execute function public.touch_updated_at();
