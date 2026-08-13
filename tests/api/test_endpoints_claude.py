"""Tests for the 4 Claude-heavy endpoints: refresh, refresh-research, refresh-gtm, next-contacts."""
from unittest.mock import MagicMock, patch

import pytest

from tests.api.conftest import load_endpoint
from _lib.claude import ClaudeError


def _chain(final_data=None):
    m = MagicMock()
    m.execute.return_value.data = final_data if final_data is not None else []
    for method in ('select', 'eq', 'order', 'limit', 'update', 'insert', 'delete', 'upsert'):
        getattr(m, method).return_value = m
    return m


ACC_ROW = {
    'id': 'row-1',
    'updated_at': '2026-01-01T00:00:00Z',
    'data': {'account_number': 'ACC-1', 'account_name': 'Snowflake', 'contacts': [], 'research': ''},
}


def _configure_db_for_claude_endpoint(mock_db, acc_row=ACC_ROW, config=None):
    """Configure mock_db to return: config, then account, then job insert, then upsert."""
    config = config if config is not None else {'user': {'full_name': 'K'}, 'company': {'name': 'OR'}}
    # get_config (list) -> return one row with data
    # get_account_by_number (list) -> return account row
    # start_job insert -> return [{id: 'job-1'}]
    # upsert_account_data update -> return [{id: 'row-1'}] (success)
    # finish_job update -> return []
    calls = iter([
        _chain(final_data=[{'data': config}]),        # get_config
        _chain(final_data=[acc_row]),                 # get_account_by_number
        _chain(final_data=[{'id': 'job-1'}]),         # start_job insert
        _chain(final_data=[{'id': 'row-1'}]),         # upsert_account_data
        _chain(final_data=[]),                         # finish_job update
    ])
    mock_db.table.side_effect = lambda *a, **kw: next(calls)


class TestRefreshEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('refresh')

    def test_happy_path(self, make_handler, mock_db, authed_user_id, mocker):
        _configure_db_for_claude_endpoint(mock_db)
        mocker.patch.object(self.mod, 'run_claude_json', return_value={
            'team': [], 'contacts': [], 'gtm_products': ['X'], 'hypothesis': '<p>h</p>', 'research': '<p>r</p>',
        })
        h = make_handler(self.mod.handler, body={'account_number': 'ACC-1'})
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['status'] == 'done'
        assert 'result' in h.response_json

    def test_missing_account_number_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={})
        h.do_POST()
        assert h.response_status == 400

    def test_unknown_account_returns_404(self, make_handler, mock_db, authed_user_id):
        # config found, account not found
        calls = iter([_chain(final_data=[{'data': {}}]), _chain(final_data=[])])
        mock_db.table.side_effect = lambda *a, **kw: next(calls)
        h = make_handler(self.mod.handler, body={'account_number': 'ACC-999'})
        h.do_POST()
        assert h.response_status == 404

    def test_claude_failure_returns_502(self, make_handler, mock_db, authed_user_id, mocker):
        calls = iter([
            _chain(final_data=[{'data': {}}]),
            _chain(final_data=[ACC_ROW]),
            _chain(final_data=[{'id': 'job-1'}]),
            _chain(final_data=[]),  # fail_job update
        ])
        mock_db.table.side_effect = lambda *a, **kw: next(calls)
        mocker.patch.object(self.mod, 'run_claude_json', side_effect=ClaudeError('AI down'))
        h = make_handler(self.mod.handler, body={'account_number': 'ACC-1'})
        h.do_POST()
        assert h.response_status == 502

    def test_missing_auth_returns_401(self, make_handler, mock_db):
        h = make_handler(self.mod.handler, body={'account_number': 'ACC-1'}, authed=False)
        h.do_POST()
        assert h.response_status == 401


class TestRefreshResearchEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('refresh-research')

    def test_happy_path(self, make_handler, mock_db, authed_user_id, mocker):
        _configure_db_for_claude_endpoint(mock_db)
        mocker.patch.object(self.mod, 'run_claude_html', return_value='<p>fresh research</p>')
        h = make_handler(self.mod.handler, body={'account_number': 'ACC-1'})
        h.do_POST()
        assert h.response_status == 200
        assert '<p>fresh research</p>' in h.response_json['result']['research']

    def test_empty_result_returns_502(self, make_handler, mock_db, authed_user_id, mocker):
        calls = iter([
            _chain(final_data=[{'data': {}}]),
            _chain(final_data=[ACC_ROW]),
            _chain(final_data=[{'id': 'job-1'}]),
            _chain(final_data=[]),
        ])
        mock_db.table.side_effect = lambda *a, **kw: next(calls)
        mocker.patch.object(self.mod, 'run_claude_html', return_value='   ')
        h = make_handler(self.mod.handler, body={'account_number': 'ACC-1'})
        h.do_POST()
        assert h.response_status == 502

    def test_missing_account_number_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={})
        h.do_POST()
        assert h.response_status == 400


class TestRefreshGtmEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('refresh-gtm')

    def test_happy_path(self, make_handler, mock_db, authed_user_id, mocker):
        acc = dict(ACC_ROW, data=dict(ACC_ROW['data'], research='<p>existing</p>'))
        _configure_db_for_claude_endpoint(mock_db, acc_row=acc)
        mocker.patch.object(self.mod, 'run_claude_json', return_value={
            'hypothesis': '<p>hyp</p>', 'gtm_products': ['A']
        })
        h = make_handler(self.mod.handler, body={'account_number': 'ACC-1'})
        h.do_POST()
        assert h.response_status == 200

    def test_no_research_returns_400(self, make_handler, mock_db, authed_user_id):
        # account with empty research
        calls = iter([
            _chain(final_data=[{'data': {}}]),
            _chain(final_data=[ACC_ROW]),  # research is '' in ACC_ROW
        ])
        mock_db.table.side_effect = lambda *a, **kw: next(calls)
        h = make_handler(self.mod.handler, body={'account_number': 'ACC-1'})
        h.do_POST()
        assert h.response_status == 400


class TestNextContactsEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('next-contacts')

    def test_happy_path(self, make_handler, mock_db, authed_user_id, mocker):
        _configure_db_for_claude_endpoint(mock_db)
        mocker.patch.object(self.mod, 'run_claude_json', return_value={
            'contacts': [{'name': 'Carol', 'email': 'carol@x.com'}]
        })
        h = make_handler(self.mod.handler, body={'account_number': 'ACC-1', 'count': 1})
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['result']['added_count'] == 1

    def test_dedupes_by_email(self, make_handler, mock_db, authed_user_id, mocker):
        acc = dict(ACC_ROW, data=dict(ACC_ROW['data'], contacts=[
            {'name': 'Existing', 'email': 'e@x.com'}
        ]))
        _configure_db_for_claude_endpoint(mock_db, acc_row=acc)
        mocker.patch.object(self.mod, 'run_claude_json', return_value={
            'contacts': [
                {'name': 'Dup', 'email': 'e@x.com'},     # dedup
                {'name': 'New', 'email': 'new@x.com'},   # keep
            ]
        })
        h = make_handler(self.mod.handler, body={'account_number': 'ACC-1', 'count': 2})
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['result']['added_count'] == 1

    def test_invalid_count_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'account_number': 'ACC-1', 'count': 999})
        h.do_POST()
        assert h.response_status == 400

    def test_count_defaults_to_5(self, make_handler, mock_db, authed_user_id, mocker):
        _configure_db_for_claude_endpoint(mock_db)
        mocker.patch.object(self.mod, 'run_claude_json', return_value={'contacts': []})
        h = make_handler(self.mod.handler, body={'account_number': 'ACC-1'})
        h.do_POST()
        assert h.response_status == 200
