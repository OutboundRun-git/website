"""Fixtures for the outboundrun.com audit suite.

Tests hit the live production site by default (BASE_URL env var overrides).
Playwright is used for JS-console + rendered-DOM checks; urllib for
structural/HTTP checks (fast, no browser overhead)."""
import os
import pytest

BASE_URL = os.environ.get('OUTBOUNDRUN_BASE_URL', 'https://outboundrun.com').rstrip('/')

# All primary pages that must always work
PAGES = [
    '/',
    '/vs/apollo/',
    '/vs/outreach/',
    '/vs/clay/',
]

# Static assets that must always be reachable
ASSETS = [
    '/styles.css',
    '/favicon.svg',
    '/og-image.png',
    '/sitemap.xml',
    '/robots.txt',
]


@pytest.fixture(scope='session')
def base_url():
    return BASE_URL


@pytest.fixture(scope='session')
def pages():
    return PAGES


@pytest.fixture(scope='session')
def assets():
    return ASSETS


@pytest.fixture(scope='session')
def all_urls(base_url, pages, assets):
    return [base_url + p for p in pages] + [base_url + a for a in assets]
