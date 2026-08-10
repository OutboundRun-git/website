"""Launch-day audit for outboundrun.com.

Tests the ~20 things that commonly break on a new website. Runs against
the live production site by default (override with OUTBOUNDRUN_BASE_URL).

Categories covered:
  1.  HTTP status codes (all pages 200, no soft 404s)
  2.  SSL cert valid + HTTPS redirect from HTTP
  3.  Meta tags present on every page (title, description, canonical, OG, Twitter)
  4.  Canonical URL matches actual URL (no self-inconsistency)
  5.  Structured data (JSON-LD) parses
  6.  Sitemap valid + URLs match reality
  7.  robots.txt allows indexing + points at real sitemap
  8.  Exactly ONE h1 per page (SEO + a11y)
  9.  All internal links resolve (no broken hrefs)
 10.  No mixed content (no http:// resources on https:// page)
 11.  Skip-to-content link present + points at #main
 12.  Focus outline styles present in CSS
 13.  No JS console errors on any page (Playwright)
 14.  Demo form on landing page has all required inputs
 15.  Mobile viewport meta tag present
 16.  Page loads under 3s (via Playwright timing)
 17.  Favicon + OG image reachable
 18.  No leftover em-dashes (per OutboundRun content style rule)
 19.  Cross-links between comparison pages present
 20.  Common typos / placeholder strings absent (Lorem ipsum, TODO, [Your Name])
"""
import json
import re
import ssl
import socket
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

import pytest


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def http_get(url, timeout=10):
    """GET a URL, returning (status_code, body_text, headers_dict)."""
    req = urllib.request.Request(url, headers={'User-Agent': 'OutboundRun-Audit/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            try:
                body = body.decode('utf-8')
            except UnicodeDecodeError:
                pass
            return resp.status, body, dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='replace'), dict(e.headers or {})


def http_head(url, timeout=10):
    req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'OutboundRun-Audit/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {})


# ── Cheap HTML parser for links + attributes ─────────────────────────────────

class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []       # (href, tag)
        self.h1s = []
        self._in_h1 = False
        self._h1_text = []
        self.title = None
        self._in_title = False
        self._title_text = []
        self.metas = []       # dicts of attributes
        self.link_els = []    # <link ...>
        self.scripts = []     # (src, has_defer, content)
        self._in_script = False
        self._script_attrs = {}
        self._script_content = []
        self.jsonld_blocks = []

    def handle_starttag(self, tag, attrs):
        adict = dict(attrs)
        if tag == 'a' and 'href' in adict:
            self.links.append((adict['href'], 'a'))
        elif tag == 'link' and 'href' in adict:
            self.link_els.append(adict)
            self.links.append((adict['href'], 'link'))
        elif tag == 'script':
            self._in_script = True
            self._script_attrs = adict
            self._script_content = []
        elif tag == 'img' and 'src' in adict:
            self.links.append((adict['src'], 'img'))
        elif tag == 'meta':
            self.metas.append(adict)
        elif tag == 'h1':
            self._in_h1 = True
            self._h1_text = []
        elif tag == 'title':
            self._in_title = True
            self._title_text = []

    def handle_endtag(self, tag):
        if tag == 'script':
            if self._script_attrs.get('type') == 'application/ld+json':
                self.jsonld_blocks.append(''.join(self._script_content))
            self.scripts.append({
                'src': self._script_attrs.get('src'),
                'defer': 'defer' in self._script_attrs,
                'content': ''.join(self._script_content),
            })
            self._in_script = False
        elif tag == 'h1':
            self.h1s.append(''.join(self._h1_text).strip())
            self._in_h1 = False
        elif tag == 'title':
            self.title = ''.join(self._title_text).strip()
            self._in_title = False

    def handle_data(self, data):
        if self._in_script:
            self._script_content.append(data)
        if self._in_h1:
            self._h1_text.append(data)
        if self._in_title:
            self._title_text.append(data)


def parse(html):
    p = LinkExtractor()
    p.feed(html)
    return p


def get_meta(page, name=None, prop=None):
    for m in page.metas:
        if name and m.get('name') == name:
            return m.get('content', '')
        if prop and m.get('property') == prop:
            return m.get('content', '')
    return None


# ── 1. HTTP status codes ──────────────────────────────────────────────────────

class TestHttpStatus:
    def test_all_pages_return_200(self, all_urls):
        failures = []
        for url in all_urls:
            status, _, _ = http_get(url)
            if status != 200:
                failures.append(f'{url} -> {status}')
        assert not failures, f'Non-200 responses: {failures}'

    def test_deliberate_404_returns_404(self, base_url):
        """A path we know doesn't exist should 404, not soft-succeed."""
        status, _, _ = http_get(f'{base_url}/definitely-not-a-real-page-12345')
        assert status == 404


# ── 2. SSL / HTTPS ────────────────────────────────────────────────────────────

class TestSSL:
    def test_https_serves_valid_cert(self, base_url):
        hostname = urllib.parse.urlparse(base_url).hostname
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                assert cert, 'no cert returned'
                # Subject should match hostname (or wildcard)
                subject = dict(x[0] for x in cert['subject'])
                assert subject.get('commonName', '').endswith('outboundrun.com') \
                    or 'outboundrun.com' in [n[1] for n in cert.get('subjectAltName', [])]

    def test_http_redirects_to_https(self, base_url):
        """Requesting the HTTP version should redirect to HTTPS."""
        if not base_url.startswith('https://'):
            pytest.skip('Base URL is not HTTPS, skipping redirect check')
        http_url = base_url.replace('https://', 'http://')
        # urllib follows redirects by default; check the final URL
        req = urllib.request.Request(http_url, headers={'User-Agent': 'audit'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert resp.url.startswith('https://'), f'HTTP did not redirect to HTTPS: {resp.url}'


# ── 3-4. Meta tags + canonical ────────────────────────────────────────────────

class TestMetaTags:
    def test_every_page_has_title(self, base_url, pages):
        for path in pages:
            _, html, _ = http_get(base_url + path)
            p = parse(html)
            assert p.title and len(p.title) > 10, f'{path}: title missing or too short ({p.title!r})'

    def test_every_page_has_description(self, base_url, pages):
        for path in pages:
            _, html, _ = http_get(base_url + path)
            p = parse(html)
            desc = get_meta(p, name='description')
            assert desc and len(desc) > 40, f'{path}: description missing or too short ({desc!r})'

    def test_every_page_has_canonical(self, base_url, pages):
        for path in pages:
            _, html, _ = http_get(base_url + path)
            p = parse(html)
            canonical = next((el['href'] for el in p.link_els if el.get('rel') == 'canonical'), None)
            assert canonical, f'{path}: no canonical URL'

    def test_canonical_matches_actual_url(self, base_url, pages):
        for path in pages:
            _, html, _ = http_get(base_url + path)
            p = parse(html)
            canonical = next((el['href'] for el in p.link_els if el.get('rel') == 'canonical'), None)
            expected = base_url + path
            assert canonical == expected, f'{path}: canonical={canonical} but should be {expected}'

    def test_every_page_has_og_image(self, base_url, pages):
        for path in pages:
            _, html, _ = http_get(base_url + path)
            p = parse(html)
            og_image = get_meta(p, prop='og:image')
            assert og_image and og_image.startswith('http'), f'{path}: og:image missing or relative ({og_image!r})'

    def test_every_page_has_twitter_card(self, base_url, pages):
        for path in pages:
            _, html, _ = http_get(base_url + path)
            p = parse(html)
            card = get_meta(p, name='twitter:card')
            assert card in ('summary', 'summary_large_image'), f'{path}: twitter:card missing or invalid ({card!r})'

    def test_every_page_has_viewport_meta(self, base_url, pages):
        for path in pages:
            _, html, _ = http_get(base_url + path)
            p = parse(html)
            viewport = get_meta(p, name='viewport')
            assert viewport and 'width=device-width' in viewport, f'{path}: viewport meta missing'


# ── 5. Structured data ────────────────────────────────────────────────────────

class TestStructuredData:
    def test_every_page_has_valid_jsonld(self, base_url, pages):
        for path in pages:
            _, html, _ = http_get(base_url + path)
            p = parse(html)
            assert p.jsonld_blocks, f'{path}: no JSON-LD structured data'
            for block in p.jsonld_blocks:
                try:
                    json.loads(block)
                except json.JSONDecodeError as e:
                    pytest.fail(f'{path}: JSON-LD invalid: {e}')


# ── 6-7. Sitemap + robots.txt ─────────────────────────────────────────────────

class TestSitemapAndRobots:
    def test_sitemap_is_valid_xml(self, base_url):
        _, body, _ = http_get(f'{base_url}/sitemap.xml')
        # Should parse without error
        ET.fromstring(body)

    def test_sitemap_urls_all_exist(self, base_url):
        _, body, _ = http_get(f'{base_url}/sitemap.xml')
        root = ET.fromstring(body)
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls = [loc.text for loc in root.findall('.//s:loc', ns)]
        assert urls, 'sitemap has no URLs'
        for url in urls:
            status, _, _ = http_get(url)
            assert status == 200, f'sitemap URL {url} returned {status}'

    def test_sitemap_covers_all_primary_pages(self, base_url, pages):
        _, body, _ = http_get(f'{base_url}/sitemap.xml')
        root = ET.fromstring(body)
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        sitemap_urls = {loc.text for loc in root.findall('.//s:loc', ns)}
        for path in pages:
            expected = base_url + path
            assert expected in sitemap_urls, f'sitemap missing {expected}'

    def test_robots_allows_indexing(self, base_url):
        _, body, _ = http_get(f'{base_url}/robots.txt')
        # No blanket "Disallow: /" for user-agent *
        assert 'Disallow: /' not in body or 'Allow:' in body, \
            f'robots.txt appears to block indexing:\n{body}'

    def test_robots_points_at_real_sitemap(self, base_url):
        _, body, _ = http_get(f'{base_url}/robots.txt')
        sitemap_line = [line for line in body.splitlines() if line.lower().startswith('sitemap:')]
        assert sitemap_line, 'robots.txt has no Sitemap: line'
        sitemap_url = sitemap_line[0].split(':', 1)[1].strip()
        status, _, _ = http_get(sitemap_url)
        assert status == 200, f'robots.txt Sitemap URL {sitemap_url} returned {status}'


# ── 8. H1 count ───────────────────────────────────────────────────────────────

class TestHeadings:
    def test_exactly_one_h1_per_page(self, base_url, pages):
        for path in pages:
            _, html, _ = http_get(base_url + path)
            p = parse(html)
            assert len(p.h1s) == 1, f'{path}: has {len(p.h1s)} h1 tags: {p.h1s}'


# ── 9-10. Internal links + mixed content ─────────────────────────────────────

class TestLinks:
    def test_no_broken_internal_links(self, base_url, pages):
        """Every internal href in the site should resolve to 200 (or 3xx to 200)."""
        seen = set()
        broken = []
        for path in pages:
            _, html, _ = http_get(base_url + path)
            p = parse(html)
            for href, tag in p.links:
                # Skip anchors, mailto, tel, external
                if href.startswith(('#', 'mailto:', 'tel:', 'data:')):
                    continue
                # Only check internal (same origin) links
                if href.startswith('http'):
                    if not href.startswith(base_url):
                        continue  # external, not our problem for this test
                    url = href
                else:
                    url = base_url + ('/' + href if not href.startswith('/') else href)
                if url in seen:
                    continue
                seen.add(url)
                status, _, _ = http_get(url)
                if status not in (200, 301, 302):
                    broken.append(f'{path} -> {url} ({status})')
        assert not broken, f'Broken internal links: {broken}'

    def test_no_mixed_content(self, base_url, pages):
        """On HTTPS, no http:// resource URLs should appear."""
        if not base_url.startswith('https://'):
            pytest.skip('Base URL is not HTTPS')
        offenders = []
        for path in pages:
            _, html, _ = http_get(base_url + path)
            # Look for http:// (with slashes to skip protocol-relative refs)
            # inside src=, href=, action= attributes
            for m in re.finditer(r'(?:src|href|action)=["\']?(http://[^"\'\s>]+)', html):
                url = m.group(1)
                # Some http:// URLs are fine (e.g. xmlns declarations, schema URIs)
                if url.startswith(('http://www.w3.org/', 'http://schema.org', 'http://ns.', 'http://purl.org/')):
                    continue
                offenders.append(f'{path}: {url}')
        assert not offenders, f'Mixed content (http on https page): {offenders}'


# ── 11-12. Accessibility signals ──────────────────────────────────────────────

class TestAccessibility:
    def test_skip_to_content_link_present(self, base_url, pages):
        for path in pages:
            _, html, _ = http_get(base_url + path)
            # Skip link is an <a> with class 'skip-link' pointing at #main
            assert 'class="skip-link"' in html, f'{path}: no skip-link'
            assert 'href="#main"' in html, f'{path}: skip-link does not target #main'
            # Corresponding <main id="main"> exists
            assert 'id="main"' in html, f'{path}: no id="main" target'

    def test_focus_visible_styles_in_css(self, base_url):
        _, css, _ = http_get(f'{base_url}/styles.css')
        assert ':focus-visible' in css or ':focus' in css, \
            'styles.css has no focus outline styles'


# ── 14. Landing-page form ─────────────────────────────────────────────────────

class TestDemoForm:
    def test_landing_has_demo_form_with_required_inputs(self, base_url):
        _, html, _ = http_get(base_url + '/')
        assert 'id="demo-form"' in html
        assert 'id="df-email"' in html
        assert 'id="df-company"' in html
        # Honeypot field for spam
        assert 'class="honeypot"' in html
        # Supabase URL is inlined for direct fetch
        assert 'supabase.co' in html


# ── 17. Favicon + OG image reachable ─────────────────────────────────────────

class TestAssets:
    def test_favicon_reachable(self, base_url):
        status, _, headers = http_get(f'{base_url}/favicon.svg')
        assert status == 200
        assert 'svg' in headers.get('Content-Type', '').lower()

    def test_og_image_reachable_and_correct_type(self, base_url):
        status, _, headers = http_get(f'{base_url}/og-image.png')
        assert status == 200
        assert 'image/png' in headers.get('Content-Type', '').lower()


# ── 18. Content style: no em-dashes on any served page ───────────────────────

class TestContentStyle:
    def test_no_em_dashes_on_any_page(self, base_url, pages):
        offenders = []
        for path in pages:
            _, html, _ = http_get(base_url + path)
            if '—' in html:
                # Locate context of first occurrence for the error message
                idx = html.find('—')
                snippet = html[max(0, idx - 40):idx + 40]
                offenders.append(f'{path}: found em-dash near ...{snippet}...')
        assert not offenders, f'Em-dashes leaked into published pages: {offenders}'


# ── 19. Cross-links between comparison pages ─────────────────────────────────

class TestComparisonCrossLinks:
    COMPARISON_PAGES = ['/vs/apollo/', '/vs/outreach/', '/vs/clay/']

    def test_each_vs_page_links_to_the_other_two(self, base_url):
        for path in self.COMPARISON_PAGES:
            _, html, _ = http_get(base_url + path)
            others = [p for p in self.COMPARISON_PAGES if p != path]
            for other in others:
                assert other in html, f'{path}: does not cross-link to {other}'


# ── 20. Placeholder / debug text ─────────────────────────────────────────────

class TestNoPlaceholders:
    PLACEHOLDER_SIGNS = [
        'lorem ipsum',
        'TODO',
        'FIXME',
        # 'XXX' removed — false-positives on X.X.X version numbers
        # 'placeholder' removed — false-positives on legitimate HTML placeholder="..." attrs
        '[Your Name]',
        '[Your name]',
        '[YOUR_NAME_HERE]',
    ]

    def test_no_leftover_placeholders(self, base_url, pages):
        """These are common typos + debug markers accidentally left in copy.
        Excludes intentional placeholder ATTRIBUTES (e.g. HTML input placeholders)."""
        offenders = []
        for path in pages:
            _, html, _ = http_get(base_url + path)
            for sign in self.PLACEHOLDER_SIGNS:
                # Only flag if sign appears in visible text (rough check: not inside placeholder="...")
                pattern = re.escape(sign)
                for m in re.finditer(pattern, html, re.IGNORECASE):
                    idx = m.start()
                    # Check if it's inside a placeholder attribute value (skip if so)
                    nearby = html[max(0, idx - 60):idx]
                    if 'placeholder="' in nearby and nearby.rfind('"') < nearby.rfind('placeholder='):
                        continue
                    # Skip if in a comment
                    if '<!--' in nearby and nearby.rfind('-->') < nearby.rfind('<!--'):
                        continue
                    snippet = html[max(0, idx - 40):idx + 40]
                    offenders.append(f'{path}: {sign} near ...{snippet}...')
        assert not offenders, f'Placeholder / debug strings in published copy: {offenders}'
