"""Tests for delete-all-accounts + delete-all-products endpoints."""
from unittest.mock import MagicMock

import pytest

from tests.api.conftest import load_endpoint


def _chain(final_data=None):
    m = MagicMock()
    m.execute.return_value.data = final_data if final_data is not None else []
    for method in ('select', 'eq', 'order', 'limit', 'update', 'insert', 'delete', 'upsert'):
        getattr(m, method).return_value = m
    return m


class TestDeleteAllAccountsEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('delete-all-accounts')

    def test_deletes_all_and_returns_count(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[
            {'id': 'row-1', 'data': {'account_number': 'A-1', 'account_name': 'One'}},
            {'id': 'row-2', 'data': {'account_number': 'A-2', 'account_name': 'Two'}},
            {'id': 'row-3', 'data': {'account_number': 'A-3', 'account_name': 'Three'}},
        ])
        h = make_handler(self.mod.handler, body={})
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json == {'deleted': 3}
        # delete() should have been invoked on the table chain
        assert mock_db.table.return_value.delete.called

    def test_deletes_zero_when_empty(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[])
        h = make_handler(self.mod.handler, body={})
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json == {'deleted': 0}

    def test_requires_auth(self, make_handler, mock_db):
        h = make_handler(self.mod.handler, body={}, authed=False)
        h.do_POST()
        assert h.response_status == 401


class TestDeleteAccountsBatchEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('delete-accounts')

    def test_deletes_each_found(self, mocker, make_handler, mock_db, authed_user_id):
        # Patch delete_account_by_number to simulate 2 found, 1 missing
        results = {'A-1': True, 'A-2': True, 'MISSING': False}
        mocker.patch(
            '_lib.repo.delete_account_by_number',
            side_effect=lambda uid, n: results.get(n, False),
        )
        h = make_handler(self.mod.handler, body={'account_numbers': ['A-1', 'A-2', 'MISSING']})
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json == {'deleted': 2, 'not_found': ['MISSING']}

    def test_empty_array_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'account_numbers': []})
        h.do_POST()
        assert h.response_status == 400

    def test_not_an_array_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'account_numbers': 'A-1'})
        h.do_POST()
        assert h.response_status == 400

    def test_oversize_returns_413(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={
            'account_numbers': [f'A-{i}' for i in range(501)]
        })
        h.do_POST()
        assert h.response_status == 413

    def test_requires_auth(self, make_handler, mock_db):
        h = make_handler(self.mod.handler, body={'account_numbers': ['A-1']}, authed=False)
        h.do_POST()
        assert h.response_status == 401


class TestDeleteAllProductsEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('delete-all-products')

    def test_clears_products_returns_count(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[{
            'data': {'company': {'products': [
                {'name': 'A', 'short_desc': ''},
                {'name': 'B', 'short_desc': ''},
            ]}}
        }])
        h = make_handler(self.mod.handler, body={})
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json == {'deleted': 2}

    def test_zero_when_no_products(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[{'data': {}}])
        h = make_handler(self.mod.handler, body={})
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json == {'deleted': 0}

    def test_requires_auth(self, make_handler, mock_db):
        h = make_handler(self.mod.handler, body={}, authed=False)
        h.do_POST()
        assert h.response_status == 401
