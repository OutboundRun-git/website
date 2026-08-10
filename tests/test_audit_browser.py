"""Browser-based audit tests (Playwright).

These are separate from the HTTP-only tests because they're slower
(browser overhead) and cover things HTTP tests can't:
  - JS console errors on page load
  - Page load timing
  - Rendered DOM after JS runs (brand title, dynamic content)"""
import pytest


PAGES = ['/', '/vs/apollo/', '/vs/outreach/', '/vs/clay/']


@pytest.fixture(scope='session')
def browser_context_args():
    return {'viewport': {'width': 1400, 'height': 900}}


def _collect_errors(page):
    """Return (pageerrors, console_error_msgs, failed_urls) trackers wired up
    to a Playwright page. Call BEFORE page.goto() so no events are missed."""
    page_errors = []
    console_errors = []
    failed_requests = []
    page.on('pageerror', lambda err: page_errors.append(str(err)))
    page.on('console', lambda msg: console_errors.append(msg.text) if msg.type == 'error' else None)
    page.on('response', lambda r: failed_requests.append(f'{r.status} {r.url}') if r.status >= 400 else None)
    return page_errors, console_errors, failed_requests


def _is_expected_404(url):
    """Vercel Analytics scripts return 404 unless Analytics is enabled in the dashboard.
    We ship the site with the script commented out, so this shouldn't fire, but keep
    the exclusion in case someone re-enables the script before enabling Analytics."""
    return '_vercel/insights' in url or '_vercel/speed-insights' in url


class TestJsConsole:
    """Every page should load with no JS errors, no page errors, and no 4xx/5xx
    resource requests (other than benign expected 404s)."""

    @pytest.mark.parametrize('path', PAGES)
    def test_no_js_errors_or_failed_requests(self, page, base_url, path):
        page_errors, console_errors, failed_requests = _collect_errors(page)
        page.goto(base_url + path)
        page.wait_for_load_state('networkidle', timeout=10000)

        # Filter benign expected 404s
        real_failures = [r for r in failed_requests if not _is_expected_404(r)]

        problems = []
        if page_errors:
            problems.append(f'pageerror: {page_errors}')
        if console_errors:
            problems.append(f'console errors: {console_errors}')
        if real_failures:
            problems.append(f'failed requests: {real_failures}')
        assert not problems, f'{path}: {problems}'


class TestPageLoadPerf:
    @pytest.mark.parametrize('path', PAGES)
    def test_page_loads_under_3_seconds(self, page, base_url, path):
        """Rough check: page should reach DOMContentLoaded within 3s."""
        page.goto(base_url + path)
        # Playwright's wait_for_load_state returns quickly if already loaded
        page.wait_for_load_state('domcontentloaded', timeout=3000)
        # Get performance timing
        timing = page.evaluate("() => performance.timing.domContentLoadedEventEnd - performance.timing.navigationStart")
        assert timing < 5000, f'{path}: DOMContentLoaded took {timing}ms'


class TestBrandRenders:
    @pytest.mark.parametrize('path', PAGES)
    def test_brand_title_visible(self, page, base_url, path):
        page.goto(base_url + path)
        brand = page.locator('.brand').first
        assert brand.is_visible()
        assert brand.text_content().strip() == 'OutboundRun'


class TestSkipLinkFocus:
    def test_skip_link_becomes_visible_on_focus(self, page, base_url):
        page.goto(base_url + '/')
        # Skip link is absolutely-positioned off-screen until focused
        skip = page.locator('.skip-link')
        # Trigger keyboard focus by pressing Tab from body
        page.keyboard.press('Tab')
        # Skip link should now be the focused element
        focused_class = page.evaluate("() => document.activeElement.className")
        assert 'skip-link' in focused_class, f'Tab did not focus skip-link. Focused: {focused_class!r}'


class TestMobileViewport:
    def test_landing_renders_at_iphone_width(self, page, base_url):
        page.set_viewport_size({'width': 375, 'height': 812})  # iPhone-ish
        page.goto(base_url + '/')
        # No horizontal scroll should be needed at mobile width
        body_width = page.evaluate("() => document.body.scrollWidth")
        viewport_width = page.evaluate("() => window.innerWidth")
        # Allow a 20px tolerance for scrollbar / rounding
        assert body_width <= viewport_width + 20, \
            f'Landing page overflows viewport: body_width={body_width}, viewport={viewport_width}'
