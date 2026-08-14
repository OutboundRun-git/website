"""Tests for config, accounts, send-email, job-status endpoints."""
from unittest.mock import MagicMock

import pytest

from tests.api.conftest import load_endpoint


def _chain(final_data=None):
    m = MagicMock()
    m.execute.return_value.data = final_data if final_data is not None else []
    for method in ('select', 'eq', 'order', 'limit', 'update', 'insert', 'delete', 'upsert'):
        getattr(m, method).return_value = m
    return m


class TestConfigEndpoint:
    mod = None

    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('config')

    def test_get_returns_empty_config_when_no_row(self, make_handler, mock_db, authed_user_id):
        # Endpoint calls two tables now (configs + gmail_connections); both return empty
        calls = iter([_chain(final_data=[]), _chain(final_data=[])])
        mock_db.table.side_effect = lambda *a, **kw: next(calls)
        h = make_handler(self.mod.handler)
        h.do_GET()
        assert h.response_status == 200
        assert h.response_json['config'] == {}
        assert h.response_json['complete'] is False

    def test_get_returns_saved_config(self, make_handler, mock_db, authed_user_id):
        cfg = {
            'user': {'full_name': 'Kim', 'email': 'k@x.com'},
            'company': {'name': 'OutboundRun', 'products': [{'name': 'OutboundRun'}]},
        }
        # configs -> [cfg row], gmail_connections -> []
        calls = iter([_chain(final_data=[{'data': cfg}]), _chain(final_data=[])])
        mock_db.table.side_effect = lambda *a, **kw: next(calls)
        h = make_handler(self.mod.handler)
        h.do_GET()
        assert h.response_status == 200
        assert h.response_json['config'] == cfg
        assert h.response_json['complete'] is True

    def test_get_missing_auth_returns_401(self, make_handler, mock_db):
        h = make_handler(self.mod.handler, authed=False)
        h.do_GET()
        assert h.response_status == 401

    def test_post_saves_config(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain()
        h = make_handler(self.mod.handler, body={'brand': {'product_name': 'X'}})
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['saved'] is True

    def test_post_rejects_non_object_body(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body=b'"just a string"',
                         headers={'Authorization': 'Bearer t', 'Content-Length': '15', 'Content-Type': 'application/json'})
        h.do_POST()
        assert h.response_status == 400


class TestAccountsEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('accounts')

    def test_returns_empty_list(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[])
        h = make_handler(self.mod.handler)
        h.do_GET()
        assert h.response_status == 200
        assert h.response_json == {'accounts': []}

    def test_returns_flattened_accounts_sorted(self, make_handler, mock_db, authed_user_id):
        rows = [
            {'id': 'r1', 'updated_at': 't1', 'data': {'account_number': 'ACC-2', 'account_name': 'Beta'}},
            {'id': 'r2', 'updated_at': 't2', 'data': {'account_number': 'ACC-1', 'account_name': 'Alpha'}},
        ]
        mock_db.table.return_value = _chain(final_data=rows)
        h = make_handler(self.mod.handler)
        h.do_GET()
        accs = h.response_json['accounts']
        assert len(accs) == 2
        assert accs[0]['account_number'] == 'ACC-1'  # sorted
        assert accs[1]['account_number'] == 'ACC-2'

    def test_missing_auth_returns_401(self, make_handler, mock_db):
        h = make_handler(self.mod.handler, authed=False)
        h.do_GET()
        assert h.response_status == 401


class TestSendEmailEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('send-email')

    def test_clipboard_mode_returns_payload(self, make_handler, mock_db, authed_user_id):
        # configs -> one row, gmail_connections -> empty (no Gmail connected)
        calls = iter([
            _chain(final_data=[{'data': {'user': {'full_name': 'Kim'}, 'company': {'name': 'OR'}}}]),
            _chain(final_data=[]),
        ])
        mock_db.table.side_effect = lambda *a, **kw: next(calls)
        h = make_handler(self.mod.handler, body={
            'to': 'x@y.com', 'subject': 'Hi', 'body': 'Hello.'
        })
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['sent'] is False
        assert h.response_json['via'] == 'clipboard'
        assert h.response_json['to'] == 'x@y.com'
        assert 'Hello.' in h.response_json['body']

    def test_appends_signature_if_missing(self, make_handler, mock_db, authed_user_id):
        calls = iter([
            _chain(final_data=[{'data': {'user': {'full_name': 'Kim', 'email': 'k@x.com'}}}]),
            _chain(final_data=[]),
        ])
        mock_db.table.side_effect = lambda *a, **kw: next(calls)
        h = make_handler(self.mod.handler, body={
            'to': 'x@y.com', 'subject': 'Hi', 'body': 'Hello.'
        })
        h.do_POST()
        assert 'Kim' in h.response_json['body']

    def test_missing_to_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'subject': 'Hi', 'body': 'x'})
        h.do_POST()
        assert h.response_status == 400

    def test_missing_subject_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'to': 'x@y.com', 'body': 'x'})
        h.do_POST()
        assert h.response_status == 400

    def test_missing_body_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'to': 'x@y.com', 'subject': 'Hi'})
        h.do_POST()
        assert h.response_status == 400


class TestJobStatusEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('job-status')

    def test_returns_job(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[
            {'id': 'j1', 'kind': 'refresh', 'status': 'done', 'result': {'x': 1}, 'error': None, 'updated_at': 't'}
        ])
        h = make_handler(self.mod.handler, path='/api/job-status?job_id=j1')
        h.do_GET()
        assert h.response_status == 200
        assert h.response_json['status'] == 'done'

    def test_missing_job_id_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, path='/api/job-status')
        h.do_GET()
        assert h.response_status == 400

    def test_unknown_job_returns_404(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[])
        h = make_handler(self.mod.handler, path='/api/job-status?job_id=missing')
        h.do_GET()
        assert h.response_status == 404
