-- OutboundRun: demo_requests table
-- Captures buyer demo-request form submissions from outboundrun.com
-- Public form uses the publishable (anon) key, so the RLS policy allows
-- INSERT from anon but DENIES all reads/updates/deletes from the browser.
-- Kim reads leads via the Supabase Table Editor (which uses service_role).

create table if not exists public.demo_requests (
  id           uuid primary key default gen_random_uuid(),
  email        text not null,
  company      text not null,
  message      text,
  source       text default 'website',
  user_agent   text,
  referrer     text,
  created_at   timestamptz not null default now()
);

create index if not exists demo_requests_created_at_idx
  on public.demo_requests (created_at desc);

create index if not exists demo_requests_email_idx
  on public.demo_requests (lower(email));

alter table public.demo_requests enable row level security;

-- Anon + authenticated can INSERT (with lightweight validation)
create policy "Allow public demo-request submissions"
  on public.demo_requests
  for insert
  to anon, authenticated
  with check (
    email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'
    and char_length(company) between 1 and 200
    and (message is null or char_length(message) < 5000)
  );

-- No SELECT / UPDATE / DELETE policies for anon =>
-- all read/write access from the browser is denied by default.
-- Kim views submissions via the Supabase dashboard (service_role internal).

comment on table public.demo_requests is
  'Buyer demo-request form submissions from outboundrun.com. Anon inserts allowed with RLS validation; reads only via service_role.';
