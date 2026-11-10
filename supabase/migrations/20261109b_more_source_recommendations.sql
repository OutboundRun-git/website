-- Phase 1c: curated catalogs for internal sources + contact-discovery tools.
-- Mirrors the pattern established in 20261109_credible_source_recommendations.sql:
--   - Table of recommendations, all default-checked for new companies
--   - Companies opt-out by storing uuid arrays in companies.data:
--       internal_source_opt_outs       (uuid[])
--       contact_discovery_opt_outs     (uuid[])
--   - Free-text additions still live in companies.data under
--       internal_sources               (text[])
--       contact_discovery_sources      (text[])

-- ============================================================================
-- INTERNAL SOURCE RECOMMENDATIONS
-- ============================================================================
create table if not exists public.internal_source_recommendations (
  id            uuid primary key default gen_random_uuid(),
  name          text not null,
  url           text,
  description   text,
  category      text not null,
  display_order int  not null default 0,
  created_at    timestamptz not null default now()
);

alter table public.internal_source_recommendations enable row level security;

drop policy if exists isr_read on public.internal_source_recommendations;
create policy isr_read on public.internal_source_recommendations
  for select using (auth.uid() is not null);

drop policy if exists isr_admin_write on public.internal_source_recommendations;
create policy isr_admin_write on public.internal_source_recommendations
  for all
  using (public.current_user_is_admin())
  with check (public.current_user_is_admin());

insert into public.internal_source_recommendations (name, url, description, category, display_order) values
  ('Salesforce',                   'https://salesforce.com',       'CRM opportunities, accounts, activity.',                        'crm',       10),
  ('HubSpot',                      'https://hubspot.com',          'CRM + marketing automation.',                                   'crm',       20),
  ('Microsoft Dynamics 365',       'https://dynamics.microsoft.com','Enterprise CRM.',                                              'crm',       30),
  ('Pipedrive',                    'https://pipedrive.com',        'Pipeline-centric CRM.',                                         'crm',       40),
  ('Attio',                        'https://attio.com',            'Modern relational CRM.',                                        'crm',       50),
  ('Gong',                         'https://gong.io',              'Sales-call recordings + conversation intelligence.',            'conv_intel',100),
  ('Chorus (ZoomInfo)',            'https://www.zoominfo.com/chorus','Sales-call recordings + analytics.',                          'conv_intel',110),
  ('Clari',                        'https://clari.com',            'Revenue forecasting + deal health.',                            'revenue',   200),
  ('Internal win/loss notes',      null,                            'Your library of past deal retrospectives.',                   'revenue',   210),
  ('Clay',                         'https://clay.com',             'Data enrichment + automation workflows.',                       'enrichment',300),
  ('Apollo.io',                    'https://apollo.io',            'Account + contact data + outbound tooling.',                    'enrichment',310),
  ('ZoomInfo',                     'https://zoominfo.com',         'B2B contact + company intelligence.',                           'enrichment',320),
  ('Snowflake / BigQuery warehouse', null,                         'Your analytics warehouse (usage, product events, deals).',      'analytics', 400),
  ('Segment customer data',        'https://segment.com',          'Unified customer event stream.',                                'analytics', 410)
on conflict do nothing;

-- ============================================================================
-- CONTACT-DISCOVERY RECOMMENDATIONS
-- ============================================================================
create table if not exists public.contact_discovery_recommendations (
  id            uuid primary key default gen_random_uuid(),
  name          text not null,
  url           text,
  description   text,
  category      text not null,
  display_order int  not null default 0,
  created_at    timestamptz not null default now()
);

alter table public.contact_discovery_recommendations enable row level security;

drop policy if exists cdr_read on public.contact_discovery_recommendations;
create policy cdr_read on public.contact_discovery_recommendations
  for select using (auth.uid() is not null);

drop policy if exists cdr_admin_write on public.contact_discovery_recommendations;
create policy cdr_admin_write on public.contact_discovery_recommendations
  for all
  using (public.current_user_is_admin())
  with check (public.current_user_is_admin());

insert into public.contact_discovery_recommendations (name, url, description, category, display_order) values
  ('LinkedIn Sales Navigator', 'https://business.linkedin.com/sales-solutions/sales-navigator', 'LinkedIn''s premium prospecting + filtering tool.',    'social',  10),
  ('ZoomInfo',                 'https://zoominfo.com',       'B2B contact database + intent signals.',                       'database', 100),
  ('Apollo.io',                'https://apollo.io',          'Database + email finder + outreach platform.',                 'database', 110),
  ('Clearbit (HubSpot Breeze)','https://clearbit.com',       'Company + person enrichment from any email or domain.',        'database', 120),
  ('Lusha',                    'https://lusha.com',          'Contact discovery with mobile numbers + direct emails.',       'database', 130),
  ('Cognism',                  'https://cognism.com',        'International B2B database with GDPR-cleaned data.',           'database', 140),
  ('Hunter.io',                'https://hunter.io',          'Email-pattern finder for any domain.',                         'email',    200),
  ('RocketReach',              'https://rocketreach.co',     'Personal + work contact details lookup.',                      'email',    210),
  ('Crunchbase (people search)','https://crunchbase.com',    'Founders, execs, team members at tracked companies.',          'web',      300),
  ('Clay (contact enrichment)','https://clay.com',           'Enrichment waterfall across 100+ data providers.',             'web',      310),
  ('Public web search',        null,                          'Google + general web for any contact mention.',               'web',      400),
  ('Company website team page',null,                          'Target''s own About / Leadership / Team pages.',              'web',      410)
on conflict do nothing;
