"""Shared fixtures for API tests.

CRITICAL: this file sets env vars BEFORE any test module imports _lib.env
(which validates env at import time and would otherwise crash).
"""
import io
import json
import os
import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Env vars — set here so `_lib.env` validation passes at import time.
# These are fake values shaped correctly for _lib/env.py's prefix + length rules.
# ---------------------------------------------------------------------------
os.environ.setdefault('SUPABASE_URL', 'https://test-project.supabase.co')
os.environ.setdefault('SUPABASE_ANON_KEY', 'sb_publishable_test_key_placeholder_XYZ12345')
os.environ.setdefault('SUPABASE_SERVICE_ROLE_KEY', 'eyJtest_service_role_key_placeholder_ABCDE1234567890')
os.environ.setdefault('ANTHROPIC_API_KEY', 'sk-ant-test_api_key_placeholder_abcdefgh1234567890')
os.environ.setdefault('GOOGLE_CLIENT_ID', '1234567890-testclientidplaceholder.apps.googleusercontent.com')
os.environ.setdefault('GOOGLE_CLIENT_SECRET', 'GOCSPX-test_client_secret_placeholder_1234')

# ---------------------------------------------------------------------------
# Ensure /api is on sys.path so `from _lib.foo import ...` resolves.
# ---------------------------------------------------------------------------
_API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'api'))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)


# ---------------------------------------------------------------------------
# pytest fixtures
# ---------------------------------------------------------------------------
import pytest  # noqa: E402


@pytest.fixture
def mock_supabase_response():
    """Factory returning a MagicMock shaped like a Supabase execute() response."""
    def _make(data=None):
        resp = MagicMock()
        resp.data = data if data is not None else []
        return resp
    return _make


@pytest.fixture
def mock_db(mocker, mock_supabase_response):
    """Patch every `get_db` reference so tests never hit real Supabase.

    Modules that do `from _lib.db import get_db` create their own local reference;
    we must patch at each import site, not just the source.
    """
    db = MagicMock()
    # Source location:
    mocker.patch('_lib.db.get_db', return_value=db)
    # Modules that pull it in via `from _lib.db import get_db`:
    for target in ('_lib.repo.get_db',):
        try:
            mocker.patch(target, return_value=db)
        except (AttributeError, ModuleNotFoundError):
            pass
    return db


@pytest.fixture
def mock_auth_get_user(mocker):
    """Patch supabase auth.get_user to return a user with a valid UUID."""
    def _configure(user_id='11111111-2222-3333-4444-555555555555', email='test@example.com'):
        auth_client = MagicMock()
        resp = MagicMock()
        resp.user = MagicMock()
        resp.user.id = user_id
        resp.user.email = email
        auth_client.auth.get_user.return_value = resp
        mocker.patch('_lib.auth._get_auth_client', return_value=auth_client)
        return user_id
    return _configure


@pytest.fixture
def authed_user_id(mock_auth_get_user):
    """Convenience: configures auth mock and returns the test user_id."""
    return mock_auth_get_user()


@pytest.fixture
def anthropic_mock(mocker):
    """Patch the Anthropic client so no real API calls happen."""
    client = MagicMock()
    mocker.patch('_lib.claude._get_client', return_value=client)
    return client


# ---------------------------------------------------------------------------
# Fake HTTP handler helpers — lets tests instantiate endpoint handler classes
# without a live BaseHTTPServer.
# ---------------------------------------------------------------------------
class FakeHandlerMixin:
    """Overrides BaseHTTPRequestHandler wire methods with in-memory buffers.

    Test usage:
        from api.config import handler as ConfigHandler
        h = make_handler(ConfigHandler, headers={'Authorization': 'Bearer t'})
        h.do_GET()
        assert h.response_status == 200
        assert h.response_json == {'config': {}, 'complete': False}
    """
    def __init__(self, headers=None, body=b'', path='/'):
        self.headers = dict(headers or {})
        self.path = path
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.command = 'POST'
        self.response_status = None
        self._sent_headers = []
        self._headers_ended = False

    def send_response(self, status):
        self.response_status = status

    def send_header(self, key, value):
        self._sent_headers.append((key, value))

    def end_headers(self):
        self._headers_ended = True

    @property
    def response_headers(self):
        return dict(self._sent_headers)

    @property
    def response_body(self):
        return self.wfile.getvalue()

    @property
    def response_json(self):
        return json.loads(self.response_body.decode('utf-8'))


def load_endpoint(name):
    """Import an endpoint module by its file basename (e.g. 'edit-account' or 'config').

    Endpoint filenames contain hyphens, which aren't valid Python identifiers,
    so a normal `import` won't work. We load via importlib.util.
    """
    import importlib.util
    path = os.path.join(_API_DIR, f'{name}.py')
    spec = importlib.util.spec_from_file_location(f'api_endpoint_{name.replace("-", "_")}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def endpoint_module():
    """Fixture form of load_endpoint (usable in tests)."""
    return load_endpoint


@pytest.fixture
def make_handler():
    """Factory that returns an instance of the given endpoint handler class,
    mixed with FakeHandlerMixin to bypass real socket I/O."""
    def _make(handler_cls, headers=None, body=None, path='/', authed=True):
        hdrs = dict(headers or {})
        if authed and 'Authorization' not in hdrs:
            hdrs['Authorization'] = 'Bearer test-jwt-token'
        raw_body = b''
        if body is not None:
            if isinstance(body, (bytes, bytearray)):
                raw_body = bytes(body)
            else:
                raw_body = json.dumps(body).encode('utf-8')
                hdrs.setdefault('Content-Type', 'application/json')
                hdrs.setdefault('Content-Length', str(len(raw_body)))

        # Build a subclass that inherits from FakeHandlerMixin FIRST, then the
        # real handler class. The mixin overrides __init__ + wire methods.
        Fake = type('Fake' + handler_cls.__name__, (FakeHandlerMixin, handler_cls), {})
        instance = Fake(headers=hdrs, body=raw_body, path=path)
        return instance
    return _make
