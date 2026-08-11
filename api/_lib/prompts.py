"""Prompt templates and builders. Ported from Significant_Revenue/app.py lines 187-524.

Every builder takes a config dict directly (no file I/O) since the hosted version
loads config from Supabase per user, not from a local file.

Em-dashes have been replaced with periods or colons throughout to enforce the
OutboundRun no-em-dashes rule (Claude tends to carry template punctuation into
output, which becomes buyer-facing).
"""


# ============================================================================
# TEMPLATES (verbatim from app.py 189-400 with em-dashes stripped)
# ============================================================================

REFRESH_PROMPT_TEMPLATE = """You are a sales research agent helping a {user_role} at {company_name} build targeted outreach for a {industry_descriptor} account.

ACCOUNT: {account_name}
ACCOUNT NUMBER: {account_number}
{crm_id_line}

YOUR TASKS. Complete ALL of them:

## TASK 1: INTERNAL TEAM
{team_task}

## TASK 2: TARGET CONTACTS
{contacts_task}

From contacts found (plus any publicly known executives you can identify from web research on {account_name}), select the 4-5 BEST targets for outreach. Prioritize:
{target_roles}

For mobile numbers: use CRM data if available, otherwise return "Not found".

## TASK 3: WEB RESEARCH
Search publicly available information about {account_name}, prioritizing these credible sources the user trusts:
{credible_sources_list}

Also incorporate anything relevant from these internal data sources the user has access to: {internal_sources_list}

REQUIRED SEARCHES (run all of them):
1. Recent news, acquisitions, funding, or leadership changes (last 12-18 months)
2. Technology stack: CRM, ERP, marketing tools, data platforms (job postings are a good signal)
3. Business challenges relevant to {company_name}'s product area
4. Industry context ({industry_descriptor}: scale, products/services)
5. Digital transformation or strategic initiatives mentioned publicly
6. If any of the credible sources above are financial-filing systems (SEC EDGAR, Companies House, etc.) and {account_name} is publicly traded there, pull the most recent annual filing. Extract: annual revenue and YoY growth, key risk factors relevant to {company_name}'s product area, strategic priorities that intersect with {company_name}'s value prop, explicit mentions of challenges {company_name}'s products address. If not public or no filing found, state that explicitly.

Return the research as HTML using ONLY these tags (no markdown):
- <h3> for section headers (e.g. "Company Overview", "10-K / Financial Highlights", "Technology Stack", "Recent News & Initiatives")
- <p> for paragraphs
- <ul><li> for bullet lists
- <sup class="cite">[N]</sup> inline after each specific fact that has a verifiable source
- A <div class="footnotes"> at the very end with one <p> per citation: [N] Source title: URL or brief description

Be specific. Do not write generic statements that apply to any {industry_descriptor} company. If a fact cannot be sourced, omit it.

## TASK 4: GTM VALUE HYPOTHESIS
Based on everything you've found, write a GTM value hypothesis for {company_name}'s products at {account_name}.

Structure it as HTML using these tags (no markdown):
- <h3> for product section headers
- <p> for paragraphs
- <ul><li> for bullet lists
- <span class="product-tag"> for product names

Cover whichever of these products genuinely fit (skip ones that don't):
{products_with_desc}

For each relevant product: what's the specific business problem at this account, what evidence supports it, and what's the hook.

Also return gtm_products as a short array of product names that fit.

## TASK 5: GHOST EMAILS
For EACH of the 4-5 target contacts, write a personalized first-touch cold email from {user_full_name} ({user_role} at {company_name}).

USER-DEFINED PERSONAS (use pain points and drivers to tailor each email per role):
{personas_detail}

Rules:
- Subject line: specific, not generic, max 8 words
- Body: 4-6 sentences max, no fluff
- Opens with a specific hook relevant to THAT persona's role and pain
- References something real about {account_name} (news, product, challenge)
- Connects to a specific product value prop from the list above
- Closes with a single low-friction CTA ({cta_minutes}-minute call)
- Do NOT mention "{company_name}" generically. Reference specific products or capabilities.
- Sign off: [Your name] (the sender will personalize)
- NO subject prefixes like "Re:" or "Fwd:"
- Do NOT use em-dashes anywhere in the output. Use periods, commas, or colons instead.

Return a JSON object with these fields:
- team: array of {{role, name, email}}
- contacts: array of {{name, title, email, mobile, hook, subject, body}}
- gtm_products: array of strings
- hypothesis: HTML string
- research: HTML string (structured per Task 3 above, with inline citation superscripts and a footnotes div)
"""


RESEARCH_PROMPT_TEMPLATE = """You are a sales research assistant helping a {user_role} at {company_name} refresh the research summary for a {industry_descriptor} account.

ACCOUNT: {account_name}
ACCOUNT NUMBER: {account_number}

EXISTING INTERNAL RESEARCH (do not re-cite this, it comes from the user's internal data):
{existing_research}

USER-TRUSTED CREDIBLE SOURCES (prioritize these when fetching, in this order):
{credible_sources_list}

INTERNAL SOURCES THE USER HAS ACCESS TO: {internal_sources_list}

YOUR TASK: Perform these three fetches in order, one at a time, waiting for each result before proceeding:

FETCH 1: Company website
Fetch the homepage of {account_name} (search for their official website URL first if needed). Extract: what the company does, key products/services, any stated strategic priorities or recent announcements.

FETCH 2: Financial filings (if applicable)
If any of the credible sources above is a financial-filing system (SEC EDGAR, Companies House, ASX, etc.) and {account_name} is publicly traded there, retrieve the most recent annual filing (10-K, annual report). Extract: annual revenue and YoY growth, key risk factors relevant to {company_name}'s product area, strategic priorities intersecting with {company_name}'s value prop, and explicit mentions of the challenges {company_name}'s products address. If the account is not public or no filing is found, note that explicitly.

FETCH 3: Business-news search across the user's trusted news outlets
From the credible sources above, identify which are news outlets (Bloomberg, Reuters, AP, industry trade press, etc.). Search each for "{account_name}" from the last 18 months. Extract any acquisitions, funding, leadership changes, or strategic announcements. Note which outlet each fact came from.

SYNTHESIS INSTRUCTIONS:
- Start with the existing CRM-based research as your foundation. Keep all of it verbatim.
- Add a new section <h3>Web Research Updates</h3> containing only what you found in the 3 fetches above.
- Only include a fact if it came directly from one of the fetches. Do not invent or infer.
- Add inline citations ONLY for facts from the web fetches: <sup class="cite">[N]</sup> immediately after the fact.
- At the very end include a <div class="footnotes"> with one <p> per citation: [N] Source name: URL
- Do not add citations to the existing CRM-based content.
- Use only these HTML tags: <h3>, <p>, <ul>, <li>, <sup class="cite">, <div class="footnotes">. No markdown.
- Do NOT use em-dashes anywhere in the output. Use periods, commas, or colons instead.

Return ONLY the raw HTML. No JSON wrapper, no markdown fences, no preamble. Your entire response should start with <p> or <h3> and end with </div>.
"""


GTM_PROMPT_TEMPLATE = """You are a sales strategist helping a {user_role} at {company_name} write a GTM value hypothesis for a {industry_descriptor} account.

ACCOUNT: {account_name}
ACCOUNT NUMBER: {account_number}

RESEARCH (use this as your sole grounding. Do not invent facts not present here):
{research_html}

YOUR TASK: Write a GTM value hypothesis for {company_name}'s products at {account_name}.

Rules:
- Every claim you make must be grounded in a specific fact from the research above.
- After each grounded claim, add an inline citation superscript referencing the research footnote number it came from: <sup class="cite">[N]</sup>
- If a point cannot be tied back to the research, omit it.
- Structure the output as HTML using ONLY these tags:
  - <h3> for product section headers
  - <p> for paragraphs
  - <ul><li> for bullet lists
  - <span class="product-tag"> for product names
  - <sup class="cite">[N]</sup> for inline citations
  - A <div class="footnotes"> at the very end listing only the citations actually used, one <p> per line: [N]: copied verbatim from the research footnote
- Do NOT use em-dashes anywhere in the output. Use periods, commas, or colons instead.

Cover whichever of these products genuinely fit given the research (skip ones that don't):
{products_with_desc}

For each relevant product: what is the specific business problem at this account (citing evidence), and what is the hook.

Return a JSON object with these fields:
- hypothesis: HTML string (structured per above, with inline citations and a footnotes div)
- gtm_products: array of short product name strings that are covered
"""


NEXT_CONTACTS_PROMPT_TEMPLATE = """You are a sales research agent helping a {user_role} at {company_name} find additional target contacts at a {industry_descriptor} account.

ACCOUNT: {account_name}
ACCOUNT NUMBER: {account_number}
{crm_id_line}

EXISTING CONTACTS (DO NOT return any of these. They are already in the outreach list):
{existing_contacts}

YOUR TASK: Identify the next {count} best target contacts for outreach at {account_name} who are NOT in the existing contacts list above.
{focus_instruction}
## STEP 1: QUERY CRM
{contacts_task}
Exclude anyone whose name or email appears in the EXISTING CONTACTS list above.

## STEP 2: CONTACT-DISCOVERY RESEARCH
The user has access to these contact-discovery tools. Prioritize suggesting which one to use for each contact you identify, so the user can look them up in the tool that has the best coverage:
{contact_discovery_list}

Use the company website, press releases, LinkedIn, and any of the tools above to find additional contacts at {account_name} not already covered.{role_guidance}

## STEP 3: SELECT & GENERATE
From all contacts found across CRM and web research, select the {count} BEST targets not already in the existing list. For each one generate:
- name, title, email (best guess from company domain if not found; format as firstname.lastname@domain.com), mobile ("Not found" if unavailable)
- hook: 2-3 sentence explanation of why THIS person at THIS account, what their pain likely is, and why they are a good target for {company_name}
- subject: specific cold email subject line, max 8 words, no generic phrasing
- body: 4-6 sentence personalized cold email body from {user_full_name} ({user_role} at {company_name}). Opens with a role-specific pain hook. References something real about {account_name}. Connects to a specific product capability. Closes with a {cta_minutes}-minute call CTA. Sign off: [Your name]. No subject prefixes. Do NOT use em-dashes; use periods, commas, or colons instead.
- flag: "GREEN", "YELLOW", or "RED"
  - GREEN: email looks deliverable and contact is verifiable
  - YELLOW: contact or email is partially unverifiable but plausible
  - RED: email is a guess, contact is unverifiable, or there is a data quality concern
- flag_reason: one sentence explaining the flag rating
- flag_categories: array of zero or more category strings from this list that apply: ["Verified accurate", "Title / role unverifiable from public sources", "Personal email domain (not corporate)", "Wrong / mismatched email domain", "No email address", "Former employee", "Generic / shared inbox or role placeholder contact"]
- human_flag: "GREEN", "YELLOW", or "RED". Does the email read as written by a human, not AI?
- human_reason: one sentence
- exec_flag: "GREEN", "YELLOW", or "RED". Is the email exec-appropriate (concise, outcome-led, peer tone, single CTA)?
- exec_reason: one sentence

Return a JSON object with one field:
- contacts: array of exactly up to {count} contact objects with all fields above
"""


FOCUS_INSTRUCTION = """
FOCUS AREA: All {count} contacts must be specifically relevant to the product area "{focus_area}". Prioritize roles that own, influence, or are impacted by that capability.
"""


BREADTH_ROLE_GUIDANCE = """
Prioritize roles NOT already well-represented in the existing contact list. Look one level deeper or broader than what's already covered:
1. If IT leadership is already covered, go to data/analytics roles
2. If C-suite is covered, go to VP/Director level
3. If commercial is covered, go to operations and enablement roles
4. Any role relevant to {company_name}'s product area
"""


GENERAL_ROLE_GUIDANCE_TEMPLATE = """
Focus on the ICP target roles:
{target_roles}
"""


# ============================================================================
# CONFIG-DERIVED HELPERS (ported from app.py 82-154)
# ============================================================================


def _products_list(cfg: dict) -> str:
    products = cfg.get('company', {}).get('products') or []
    return ', '.join(p['name'] for p in products if p.get('name'))


def _products_with_desc(cfg: dict) -> str:
    products = cfg.get('company', {}).get('products') or []
    out = []
    for p in products:
        name = (p.get('name') or '').strip()
        if not name:
            continue
        desc = (p.get('short_desc') or '').strip()
        out.append(f'- {name}: {desc}' if desc else f'- {name}')
    return '\n'.join(out) or '(no products configured)'


def _target_roles(cfg: dict) -> str:
    personas = cfg.get('personas') or []
    role_names = []
    for p in personas:
        title = (p.get('title') or '').strip()
        name = (p.get('name') or '').strip()
        if title:
            role_names.append(title)
        elif name:
            role_names.append(name)
    if not role_names:
        role_names = cfg.get('icp', {}).get('target_roles') or []
    if not role_names:
        return '(no target roles or personas configured)'
    return '\n'.join(f'{i+1}. {r}' for i, r in enumerate(role_names))


def _personas_detail(cfg: dict) -> str:
    personas = cfg.get('personas') or []
    out = []
    for p in personas:
        name = (p.get('name') or '').strip()
        title = (p.get('title') or '').strip()
        pain = (p.get('pain_points') or '').strip()
        cares = (p.get('cares_about') or '').strip()
        if not (name or title):
            continue
        label = f'{name} ({title})' if name and title else (name or title)
        block = [f'- {label}']
        if pain:
            block.append(f'    Pain points: {pain}')
        if cares:
            block.append(f'    Cares about: {cares}')
        out.append('\n'.join(block))
    return '\n'.join(out) or '(no personas configured; use general role-based inference)'


def _credible_sources_list(cfg: dict) -> str:
    sources = [s.strip() for s in (cfg.get('credible_external_sources') or []) if s and s.strip()]
    if not sources:
        return '- Public web search (no specific credible sources configured)'
    return '\n'.join(f'- {s}' for s in sources)


def _internal_sources_list(cfg: dict) -> str:
    sources = [s.strip() for s in (cfg.get('internal_sources') or []) if s and s.strip()]
    return ', '.join(sources) if sources else 'none configured'


def _contact_discovery_list(cfg: dict) -> str:
    sources = [s.strip() for s in (cfg.get('contact_discovery_sources') or []) if s and s.strip()]
    if not sources:
        return '- Public web research (no contact-discovery tools configured)'
    return '\n'.join(f'- {s}' for s in sources)


# ============================================================================
# CRM HELPERS (ported from app.py 402-437)
# ============================================================================


def _crm_team_task(cfg: dict, acc: dict) -> str:
    crm = cfg.get('crm', {})
    crm_type = crm.get('type', 'none')
    crm_id = acc.get('crm_id') or acc.get('org62_id')
    if crm_type == 'salesforce_org62' and crm_id:
        roles = crm.get('team_roles') or []
        role_filter = ', '.join(roles) if roles else '(any role)'
        return (
            f"Query Org62 AccountTeamMember for account {crm_id}:\n"
            f"SELECT TeamMemberRole, User.Name, User.Email FROM AccountTeamMember WHERE AccountId = '{crm_id}'\n"
            f"Return ONLY members whose TeamMemberRole is one of: {role_filter}\n"
            f"For each matching member return: role, name, email"
        )
    return 'No CRM integration configured. Return an empty team array.'


def _crm_contacts_task(cfg: dict, acc: dict, limit: int = 50) -> str:
    crm = cfg.get('crm', {})
    crm_type = crm.get('type', 'none')
    crm_id = acc.get('crm_id') or acc.get('org62_id')
    if crm_type == 'salesforce_org62' and crm_id:
        return (
            f"Query Org62 Contacts for this account:\n"
            f"SELECT FirstName, LastName, Title, Email, Phone, MobilePhone, LastActivityDate FROM Contact WHERE AccountId = '{crm_id}' ORDER BY LastActivityDate DESC NULLS LAST LIMIT {limit}\n\n"
            f"Also query open/recent Opportunities:\n"
            f"SELECT Name, StageName, Amount, CloseDate, Description FROM Opportunity WHERE AccountId = '{crm_id}' ORDER BY LastActivityDate DESC NULLS LAST LIMIT 15"
        )
    return 'No CRM integration configured. Skip to web research.'


def _crm_id_line(cfg: dict, acc: dict) -> str:
    crm_id = acc.get('crm_id') or acc.get('org62_id')
    if crm_id and cfg.get('crm', {}).get('type', 'none') != 'none':
        return f"CRM ID: {crm_id}"
    return ''


# ============================================================================
# PROMPT CONTEXT + BUILDERS (ported from app.py 441-524)
# ============================================================================


def prompt_context(cfg: dict) -> dict:
    """Shared config-derived template variables."""
    return {
        'company_name': cfg.get('company', {}).get('name') or '(company)',
        'user_full_name': cfg.get('user', {}).get('full_name') or '(user)',
        'user_role': cfg.get('user', {}).get('role_title') or 'Account Executive',
        'industry_descriptor': (
            cfg.get('icp', {}).get('industry_descriptor')
            or cfg.get('icp', {}).get('industry')
            or 'target'
        ),
        'products_with_desc': _products_with_desc(cfg),
        'products_list': _products_list(cfg),
        'target_roles': _target_roles(cfg),
        'personas_detail': _personas_detail(cfg),
        'credible_sources_list': _credible_sources_list(cfg),
        'internal_sources_list': _internal_sources_list(cfg),
        'contact_discovery_list': _contact_discovery_list(cfg),
        'cta_minutes': cfg.get('email', {}).get('cta_length_minutes', 20),
    }


def build_refresh_prompt(cfg: dict, acc: dict) -> str:
    ctx = prompt_context(cfg)
    return REFRESH_PROMPT_TEMPLATE.format(
        account_name=acc['account_name'],
        account_number=acc['account_number'],
        crm_id_line=_crm_id_line(cfg, acc),
        team_task=_crm_team_task(cfg, acc),
        contacts_task=_crm_contacts_task(cfg, acc, limit=50),
        **ctx,
    )


def build_research_prompt(cfg: dict, acc: dict) -> str:
    ctx = prompt_context(cfg)
    return RESEARCH_PROMPT_TEMPLATE.format(
        account_name=acc['account_name'],
        account_number=acc['account_number'],
        existing_research=acc.get('research') or '(none yet)',
        **ctx,
    )


def build_gtm_prompt(cfg: dict, acc: dict) -> str:
    ctx = prompt_context(cfg)
    return GTM_PROMPT_TEMPLATE.format(
        account_name=acc['account_name'],
        account_number=acc['account_number'],
        research_html=acc.get('research', ''),
        **ctx,
    )


def build_next_contacts_prompt(cfg: dict, acc: dict, count: int = 5, focus_area: str | None = None) -> str:
    ctx = prompt_context(cfg)
    existing = acc.get('contacts', [])
    existing_lines = '\n'.join(
        f"  - {c.get('name', '')} | {c.get('email', '')} | {c.get('title', '')}"
        for c in existing
    ) or '  (none yet)'

    if focus_area:
        focus_instruction = FOCUS_INSTRUCTION.format(count=count, focus_area=focus_area)
        role_guidance = f'\nAll contacts must be relevant to the "{focus_area}" product area.'
    else:
        focus_instruction = ''
        role_guidance = (
            BREADTH_ROLE_GUIDANCE.format(company_name=ctx['company_name'])
            if existing
            else GENERAL_ROLE_GUIDANCE_TEMPLATE.format(target_roles=ctx['target_roles'])
        )

    return NEXT_CONTACTS_PROMPT_TEMPLATE.format(
        account_name=acc['account_name'],
        account_number=acc['account_number'],
        crm_id_line=_crm_id_line(cfg, acc),
        existing_contacts=existing_lines,
        contacts_task=_crm_contacts_task(cfg, acc, limit=100),
        count=count,
        focus_instruction=focus_instruction,
        role_guidance=role_guidance,
        **ctx,
    )
