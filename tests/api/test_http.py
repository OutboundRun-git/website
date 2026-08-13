"""Tests for _lib/http.py — BaseHandler + endpoint decorator."""
import io
import json
from unittest.mock import MagicMock

import pytest

from _lib.http import BaseHandler, HttpError, endpoint, MAX_BODY_BYTES
from _lib.auth import AuthError

from tests.api.conftest import FakeHandlerMixin


def _make_bare(headers=None, body=b'', path='/'):
    """Build a raw BaseHandler mixed with FakeHandlerMixin (no endpoint auth)."""
    Fake = type('FakeBare', (FakeHandlerMixin, BaseHandler), {})
    return Fake(headers=headers, body=body, path=path)


class TestBody:
    def test_empty_body_returns_empty_dict(self):
        h = _make_bare(headers={'Content-Length': '0'})
        assert h._body() == {}

    def test_valid_json_body(self):
        raw = json.dumps({'a': 1}).encode()
        h = _make_bare(headers={'Content-Length': str(len(raw))}, body=raw)
        assert h._body() == {'a': 1}

    def test_malformed_json_raises_http_400(self):
        raw = b'not valid json'
        h = _make_bare(headers={'Content-Length': str(len(raw))}, body=raw)
        with pytest.raises(HttpError) as exc:
            h._body()
        assert exc.value.status == 400

    def test_non_object_body_raises_400(self):
        raw = b'"just a string"'
        h = _make_bare(headers={'Content-Length': str(len(raw))}, body=raw)
        with pytest.raises(HttpError) as exc:
            h._body()
        assert exc.value.status == 400

    def test_oversized_body_raises_413(self):
        h = _make_bare(headers={'Content-Length': str(MAX_BODY_BYTES + 1)}, body=b'x')
        with pytest.raises(HttpError) as exc:
            h._body()
        assert exc.value.status == 413

    def test_invalid_content_length_raises_400(self):
        h = _make_bare(headers={'Content-Length': 'not-a-number'})
        with pytest.raises(HttpError) as exc:
            h._body()
        assert exc.value.status == 400


class TestDrainBody:
    def test_drains_full_body_on_err(self):
        raw = b'x' * 1000
        h = _make_bare(headers={'Content-Length': '1000'}, body=raw)
        h._err(401, 'nope')
        # After _err, the rfile should be fully read (drained)
        assert h.rfile.read() == b''

    def test_zero_length_drain_noop(self):
        h = _make_bare(headers={'Content-Length': '0'})
        h._drain_body()  # should not raise


class TestJsonResponse:
    def test_ok_shape(self):
        h = _make_bare()
        h._ok({'hello': 'world'})
        assert h.response_status == 200
        assert h.response_json == {'hello': 'world'}
        assert h.response_headers['Content-Type'].startswith('application/json')
        assert h.response_headers['Cache-Control'] == 'no-store'

    def test_err_shape(self):
        h = _make_bare()
        h._err(404, 'not found')
        assert h.response_status == 404
        assert h.response_json == {'error': 'not found'}


class TestQuery:
    def test_extracts_query_param(self):
        h = _make_bare(path='/api/foo?job_id=abc123&kind=research')
        assert h._query('job_id') == 'abc123'
        assert h._query('kind') == 'research'

    def test_missing_returns_none(self):
        h = _make_bare(path='/api/foo')
        assert h._query('job_id') is None


class TestEndpointDecorator:
    """@endpoint should: verify auth, catch AuthError->401, catch HttpError,
    catch unknown Exception->500, always drain body first."""

    def _make(self, decorated_fn, headers=None, body=b'', authed_user_id_str='11111111-2222-3333-4444-555555555555'):
        """Create a fake handler with the decorated method mounted as do_POST."""
        Fake = type('Fake', (FakeHandlerMixin, BaseHandler), {'do_POST': decorated_fn})
        h = Fake(headers=headers or {'Authorization': 'Bearer x', 'Content-Length': str(len(body))}, body=body)
        return h

    def test_success_flows_through(self, authed_user_id):
        @endpoint
        def handler(self, user_id):
            self._ok({'user': user_id})
        h = self._make(handler)
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json == {'user': authed_user_id}

    def test_auth_error_becomes_401(self):
        @endpoint
        def handler(self, user_id):
            self._ok({})  # should never run
        # No auth header
        h = self._make(handler, headers={'Content-Length': '0'})
        h.do_POST()
        assert h.response_status == 401
        assert 'error' in h.response_json

    def test_http_error_returned_with_status(self, authed_user_id):
        @endpoint
        def handler(self, user_id):
            raise HttpError(422, 'validation failed')
        h = self._make(handler)
        h.do_POST()
        assert h.response_status == 422
        assert h.response_json == {'error': 'validation failed'}

    def test_uncaught_exception_becomes_generic_500(self, authed_user_id):
        @endpoint
        def handler(self, user_id):
            raise ValueError('secret internal detail: sk-ant-LEAK')
        h = self._make(handler)
        h.do_POST()
        assert h.response_status == 500
        assert 'sk-ant' not in json.dumps(h.response_json)
        assert 'secret internal' not in json.dumps(h.response_json)
        assert h.response_json == {'error': 'Internal server error'}
