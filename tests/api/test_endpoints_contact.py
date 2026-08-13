"""Tests for save-action, save-dnc, edit-contact, delete-contact endpoints."""
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
    'data': {
        'account_number': 'ACC-1',
        'account_name': 'TestCo',
        'contacts': [
            {'name': 'Alice', 'title': 'CFO', 'email': 'alice@testco.com'},
            {'name': 'Bob',   'title': 'VP',  'email': 'bob@testco.com'},
        ],
    },
}


def _make_db_returning_account(mock_db):
    """Configure mock_db so both get_account_by_number and upsert succeed."""
    chain = _chain(final_data=[ACC_ROW])
    # Update returns updated row so optimistic lock passes
    update_chain = MagicMock()
    update_chain.execute.return_value.data = [{'id': 'row-1'}]
    for method in ('eq', 'update'):
        setattr(update_chain, method, MagicMock(return_value=update_chain))
    # Reuse the same chain object for both select and update flow
    chain.update.return_value = chain  # update returns chain
    chain.execute.return_value.data = [ACC_ROW]  # default: return the account row
    mock_db.table.return_value = chain
    return chain


class TestSaveActionEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('save-action')

    def test_saves_action_by_email(self, make_handler, mock_db, authed_user_id):
        _make_db_returning_account(mock_db)
        h = make_handler(self.mod.handler, body={
            'account_number': 'ACC-1',
            'contact_email': 'alice@testco.com',
            'action': 'emailed',
            'date': '2026-08-01',
        })
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['updated'] == 1

    def test_missing_account_number_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'contact_email': 'x', 'action': 'emailed'})
        h.do_POST()
        assert h.response_status == 400

    def test_missing_action_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'account_number': 'ACC-1', 'contact_email': 'x'})
        h.do_POST()
        assert h.response_status == 400

    def test_missing_contact_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'account_number': 'ACC-1', 'action': 'emailed'})
        h.do_POST()
        assert h.response_status == 400

    def test_unknown_account_returns_404(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[])
        h = make_handler(self.mod.handler, body={
            'account_number': 'ACC-999', 'contact_email': 'a@b.com', 'action': 'emailed'
        })
        h.do_POST()
        assert h.response_status == 404

    def test_unknown_contact_returns_404(self, make_handler, mock_db, authed_user_id):
        _make_db_returning_account(mock_db)
        h = make_handler(self.mod.handler, body={
            'account_number': 'ACC-1', 'contact_email': 'ghost@nowhere.com', 'action': 'emailed'
        })
        h.do_POST()
        assert h.response_status == 404


class TestSaveDncEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('save-dnc')

    def test_toggles_dnc(self, make_handler, mock_db, authed_user_id):
        _make_db_returning_account(mock_db)
        h = make_handler(self.mod.handler, body={
            'account_number': 'ACC-1', 'contact_email': 'alice@testco.com', 'do_not_contact': True,
        })
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['do_not_contact'] is True

    def test_missing_account_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'contact_email': 'x', 'do_not_contact': True})
        h.do_POST()
        assert h.response_status == 400


class TestEditContactEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('edit-contact')

    def test_updates_fields(self, make_handler, mock_db, authed_user_id):
        _make_db_returning_account(mock_db)
        h = make_handler(self.mod.handler, body={
            'account_number': 'ACC-1',
            'contact_email': 'alice@testco.com',
            'updates': {'title': 'CEO'},
        })
        h.do_POST()
        assert h.response_status == 200

    def test_missing_updates_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={
            'account_number': 'ACC-1', 'contact_email': 'a@b.com'
        })
        h.do_POST()
        assert h.response_status == 400


class TestDeleteContactEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('delete-contact')

    def test_deletes_contact(self, make_handler, mock_db, authed_user_id):
        _make_db_returning_account(mock_db)
        h = make_handler(self.mod.handler, body={
            'account_number': 'ACC-1', 'contact_email': 'alice@testco.com',
        })
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['deleted'] is True
        assert h.response_json['removed'] == 1

    def test_unknown_contact_returns_404(self, make_handler, mock_db, authed_user_id):
        _make_db_returning_account(mock_db)
        h = make_handler(self.mod.handler, body={
            'account_number': 'ACC-1', 'contact_email': 'ghost@nowhere.com'
        })
        h.do_POST()
        assert h.response_status == 404
