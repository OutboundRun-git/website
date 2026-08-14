"""Tests for gmail-connect-start, gmail-disconnect, and the updated
send-email + config endpoints (Gmail send path)."""
import json
from unittest.mock import MagicMock

import pytest

from tests.api.conftest import load_endpoint


def _chain(final_data=None):
    m = MagicMock()
    m.execute.return_value.data = final_data if final_data is not None else []
    for method in ('select', 'eq', 'order', 'limit', 'update', 'insert', 'delete', 'upsert'):
        getattr(m, method).return_value = m
    return m


class TestConnectStartEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('gmail-connect-start')

    def test_returns_oauth_url(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler)
        h.do_GET()
        assert h.response_status == 200
        assert h.response_json['url'].startswith('https://accounts.google.com/o/oauth2/v2/auth?')
        assert 'client_id=' in h.response_json['url']
        assert 'gmail.send' in h.response_json['url']
        assert 'state=' in h.response_json['url']

    def test_missing_auth_returns_401(self, make_handler, mock_db):
        h = make_handler(self.mod.handler, authed=False)
        h.do_GET()
        assert h.response_status == 401

    def test_503_when_not_configured(self, make_handler, mock_db, authed_user_id, mocker):
        mocker.patch.object(self.mod.env, 'gmail_configured', return_value=False)
        h = make_handler(self.mod.handler)
        h.do_GET()
        assert h.response_status == 503


class TestDisconnectEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('gmail-disconnect')

    def test_deletes_and_returns_ok(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain()
        h = make_handler(self.mod.handler, body={})
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['disconnected'] is True


class TestConfigReturnsGmailStatus:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('config')

    def test_get_includes_gmail_status_disconnected(self, make_handler, mock_db, authed_user_id):
        # config row exists, but no gmail_connections row
        calls = iter([_chain(final_data=[]), _chain(final_data=[])])
        mock_db.table.side_effect = lambda *a, **kw: next(calls)
        h = make_handler(self.mod.handler)
        h.do_GET()
        assert h.response_status == 200
        assert h.response_json['gmail'] == {'connected': False, 'email': None}
        assert h.response_json['gmail_available'] is True

    def test_get_includes_gmail_status_connected(self, make_handler, mock_db, authed_user_id):
        calls = iter([
            _chain(final_data=[{'data': {}}]),
            _chain(final_data=[{
                'user_id': authed_user_id,
                'refresh_token': 'rt', 'email': 'kim@gmail.com', 'connected_at': 't'
            }]),
        ])
        mock_db.table.side_effect = lambda *a, **kw: next(calls)
        h = make_handler(self.mod.handler)
        h.do_GET()
        assert h.response_status == 200
        assert h.response_json['gmail'] == {'connected': True, 'email': 'kim@gmail.com'}


class TestSendEmailWithGmail:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('send-email')

    def test_falls_back_to_clipboard_when_not_connected(self, make_handler, mock_db, authed_user_id):
        # config row + gmail_connections empty
        calls = iter([_chain(final_data=[{'data': {}}]), _chain(final_data=[])])
        mock_db.table.side_effect = lambda *a, **kw: next(calls)
        h = make_handler(self.mod.handler, body={
            'to': 'x@y.com', 'subject': 'Hi', 'body': 'Hello.'
        })
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['sent'] is False
        assert h.response_json['via'] == 'clipboard'

    def test_real_send_when_connected(self, make_handler, mock_db, authed_user_id, mocker):
        calls = iter([
            _chain(final_data=[{'data': {}}]),                                      # get_config
            _chain(final_data=[{'user_id': authed_user_id, 'refresh_token': 'rt',   # get_gmail_connection
                                'email': 'kim@gmail.com', 'connected_at': 't'}]),
        ])
        mock_db.table.side_effect = lambda *a, **kw: next(calls)
        mocker.patch.object(self.mod, 'refresh_access_token', return_value='at_1')
        mocker.patch.object(self.mod, 'gmail_send', return_value='msg-id-abc')
        h = make_handler(self.mod.handler, body={
            'to': 'buyer@company.com', 'subject': 'Hi', 'body': 'Hello.'
        })
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['sent'] is True
        assert h.response_json['via'] == 'gmail'
        assert h.response_json['message_id'] == 'msg-id-abc'
        assert h.response_json['from'] == 'kim@gmail.com'

    def test_falls_back_when_gmail_send_fails(self, make_handler, mock_db, authed_user_id, mocker):
        from _lib.gmail import GmailError
        calls = iter([
            _chain(final_data=[{'data': {}}]),
            _chain(final_data=[{'user_id': authed_user_id, 'refresh_token': 'rt',
                                'email': 'kim@gmail.com', 'connected_at': 't'}]),
        ])
        mock_db.table.side_effect = lambda *a, **kw: next(calls)
        mocker.patch.object(self.mod, 'refresh_access_token', side_effect=GmailError('token dead'))
        h = make_handler(self.mod.handler, body={
            'to': 'buyer@company.com', 'subject': 'Hi', 'body': 'Hello.'
        })
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['sent'] is False
        assert h.response_json['via'] == 'clipboard'
        assert h.response_json['gmail_error'] == 'token dead'

    def test_missing_to_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'subject': 'Hi', 'body': 'x'})
        h.do_POST()
        assert h.response_status == 400
