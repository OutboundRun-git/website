-- Phase 1b: platform-curated credible-source recommendations.
--
-- Seed table with international, non-political business sources. Admins (you,
-- future platform staff) can CRUD; every authenticated user can read.
--
-- Companies opt OUT of specific recommendations by storing their IDs in
-- companies.data.credible_source_opt_outs (array of uuid). Default behavior
-- is "all checked"; empty opt-outs = every recommendation used.
--
-- Companies can also ADD custom sources via
-- companies.data.credible_external_sources (array of free-form strings).
--
-- The final list fed to the prompt is:
--   (recommendations ∖ opt_outs) ∪ custom strings

create table if not exists public.credible_source_recommendations (
  id            uuid primary key default gen_random_uuid(),
  name          text not null,
  url           text,
  description   text,
  category      text not null,
  display_order int  not null default 0,
  created_at    timestamptz not null default now()
);

alter table public.credible_source_recommendations enable row level security;

-- Any authenticated user may read the catalog.
drop policy if exists csr_read on public.credible_source_recommendations;
create policy csr_read on public.credible_source_recommendations
  for select
  using (auth.uid() is not null);

-- Only platform admins may write.
drop policy if exists csr_admin_write on public.credible_source_recommendations;
create policy csr_admin_write on public.credible_source_recommendations
  for all
  using (public.current_user_is_admin())
  with check (public.current_user_is_admin());

-- ---------- Seed: 22 curated sources (idempotent on name) ----------
insert into public.credible_source_recommendations (name, url, description, category, display_order) values
  ('SEC EDGAR',                 'https://www.sec.gov/edgar',           '10-K, 10-Q, 8-K and other filings for US public companies.',           'filings', 10),
  ('Companies House (UK)',      'https://find-and-update.company-information.service.gov.uk', 'Statutory filings for UK registered companies.',                                                           'filings', 20),
  ('SEDAR+ (Canada)',           'https://www.sedarplus.ca',            'Canadian securities filings and continuous disclosure.',               'filings', 30),
  ('ASX Market Announcements',  'https://www.asx.com.au/markets/trade-our-cash-market/announcements', 'ASX-listed company continuous disclosures.',                                          'filings', 40),
  ('Reuters',                   'https://www.reuters.com/business',    'International business news wire; neutral editorial standard.',        'news',    100),
  ('Bloomberg',                 'https://www.bloomberg.com',           'Markets, companies, macroeconomic data.',                              'news',    110),
  ('Financial Times',           'https://www.ft.com',                  'Global business journalism and sector analysis.',                      'news',    120),
  ('Wall Street Journal',       'https://www.wsj.com/news/business',   'US-centric business reporting.',                                       'news',    130),
  ('The Economist',             'https://www.economist.com',           'Weekly analysis of business, finance, and economics.',                 'news',    140),
  ('Nikkei Asia',               'https://asia.nikkei.com',             'Asia-Pacific business coverage; strong on Japanese + Korean markets.', 'news',    150),
  ('Crunchbase',                'https://www.crunchbase.com',          'Funding, team, and news for private companies and startups.',          'research',200),
  ('PitchBook',                 'https://pitchbook.com',               'Private-market data, funding rounds, M&A, cap tables.',                'research',210),
  ('CB Insights',               'https://www.cbinsights.com',          'Startup and VC market intelligence + industry research reports.',      'research',220),
  ('Harvard Business Review',   'https://hbr.org',                     'Management and strategy articles backed by research.',                 'research',230),
  ('McKinsey Insights',         'https://www.mckinsey.com/insights',   'Industry and functional research reports.',                            'research',240),
  ('Gartner',                   'https://www.gartner.com/en/research', 'Technology market research, Magic Quadrants, hype cycles.',            'research',250),
  ('Forrester',                 'https://www.forrester.com',           'Customer-experience and technology research.',                         'research',260),
  ('IDC',                       'https://www.idc.com',                 'IT market share, forecasts, vendor assessments.',                      'research',270),
  ('Company press releases',    null,                                  'Official announcements from the target company.',                      'company', 300),
  ('Company investor relations','null',                                'IR deck, annual report, quarterly materials.',                         'company', 310),
  ('Company earnings-call transcripts', null,                          'Transcripts of Q&A with analysts; strategic priorities + tone.',      'company', 320),
  ('Company LinkedIn page',     null,                                  'Headcount trends, hiring signals, leadership changes.',                'company', 330)
on conflict do nothing;
