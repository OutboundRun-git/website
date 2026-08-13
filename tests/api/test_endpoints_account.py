"""Tests for edit-account, delete-account, delete-my-account endpoints."""
from unittest.mock import MagicMock

import pytest

from tests.api.conftest import load_endpoint


def _chain(final_data=None):
    m = MagicMock()
    m.execute.return_value.data = final_data if final_data is not None else []
    for method in ('select', 'eq', 'order', 'limit', 'update', 'insert', 'delete', 'upsert'):
        getattr(m, method).return_value = m
    return m


ACC_ROW = {
    'id': 'row-1',
    'updated_at': '2026-01-01T00:00:00Z',
    'data': {'account_number': 'ACC-1', 'account_name': 'TestCo', 'industry': 'B2B SaaS'},
}


class TestEditAccountEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('edit-account')

    def test_edits_name(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[ACC_ROW])
        h = make_handler(self.mod.handler, body={
            'account_number': 'ACC-1',
            'updates': {'account_name': 'NewName'},
        })
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['account']['account_name'] == 'NewName'

    def test_rejects_blank_name(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[ACC_ROW])
        h = make_handler(self.mod.handler, body={
            'account_number': 'ACC-1', 'updates': {'account_name': ''}
        })
        h.do_POST()
        assert h.response_status == 400

    def test_sets_valid_status(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[ACC_ROW])
        h = make_handler(self.mod.handler, body={
            'account_number': 'ACC-1', 'updates': {'status': 'opportunity'}
        })
        h.do_POST()
        assert h.response_status == 200

    def test_rejects_invalid_status(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[ACC_ROW])
        h = make_handler(self.mod.handler, body={
            'account_number': 'ACC-1', 'updates': {'status': 'nonsense'}
        })
        h.do_POST()
        assert h.response_status == 400

    def test_toggles_starred(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[ACC_ROW])
        h = make_handler(self.mod.handler, body={
            'account_number': 'ACC-1', 'updates': {'starred': True}
        })
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['account']['starred'] is True

    def test_unknown_account_returns_404(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[])
        h = make_handler(self.mod.handler, body={
            'account_number': 'ACC-999', 'updates': {'account_name': 'X'}
        })
        h.do_POST()
        assert h.response_status == 404

    def test_stale_returns_409(self, make_handler, mock_db, authed_user_id, mocker):
        # get_account_by_number returns the row; upsert returns [] (stale)
        select_chain = _chain(final_data=[ACC_ROW])
        update_chain = _chain(final_data=[])
        # Alternate between two tables/chains — simplest way: two side_effects
        mock_db.table.side_effect = [select_chain, update_chain]
        h = make_handler(self.mod.handler, body={
            'account_number': 'ACC-1', 'updates': {'account_name': 'X'}
        })
        h.do_POST()
        assert h.response_status == 409


class TestDeleteAccountEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('delete-account')

    def test_deletes(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[{'id': 'row-1'}])
        h = make_handler(self.mod.handler, body={'account_number': 'ACC-1'})
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['deleted'] is True

    def test_missing_account_number_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={})
        h.do_POST()
        assert h.response_status == 400

    def test_unknown_account_returns_404(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[])
        h = make_handler(self.mod.handler, body={'account_number': 'ACC-999'})
        h.do_POST()
        assert h.response_status == 404


class TestDeleteMyAccountEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('delete-my-account')

    def test_deletes_user(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'confirm': 'DELETE'})
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['deleted'] is True
        mock_db.auth.admin.delete_user.assert_called_once_with(authed_user_id)

    def test_wrong_confirm_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'confirm': 'delete'})  # lowercase
        h.do_POST()
        assert h.response_status == 400
        mock_db.auth.admin.delete_user.assert_not_called()

    def test_missing_confirm_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={})
        h.do_POST()
        assert h.response_status == 400

    def test_missing_auth_returns_401(self, make_handler, mock_db):
        h = make_handler(self.mod.handler, body={'confirm': 'DELETE'}, authed=False)
        h.do_POST()
        assert h.response_status == 401
