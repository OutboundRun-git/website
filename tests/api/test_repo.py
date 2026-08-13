"""Tests for _lib/repo.py — data access layer with mocked Supabase."""
from unittest.mock import MagicMock

import pytest

from _lib import repo


USER_ID = '11111111-2222-3333-4444-555555555555'


def _chain(final_data=None):
    """Build a MagicMock where any .method() call returns self, until .execute()
    which returns a mock with .data set."""
    m = MagicMock()
    m.execute.return_value.data = final_data if final_data is not None else []
    # Every attribute access + call returns m for chaining
    m.select.return_value = m
    m.eq.return_value = m
    m.order.return_value = m
    m.limit.return_value = m
    m.update.return_value = m
    m.insert.return_value = m
    m.delete.return_value = m
    m.upsert.return_value = m
    return m


class TestGetConfig:
    def test_returns_empty_when_no_row(self, mock_db):
        chain = _chain(final_data=[])
        mock_db.table.return_value = chain
        assert repo.get_config(USER_ID) == {}

    def test_returns_data_field_from_row(self, mock_db):
        chain = _chain(final_data=[{'data': {'user': {'full_name': 'Alex'}}}])
        mock_db.table.return_value = chain
        assert repo.get_config(USER_ID) == {'user': {'full_name': 'Alex'}}

    def test_data_null_returns_empty(self, mock_db):
        chain = _chain(final_data=[{'data': None}])
        mock_db.table.return_value = chain
        assert repo.get_config(USER_ID) == {}


class TestSaveConfig:
    def test_upserts_with_user_id(self, mock_db):
        chain = _chain()
        mock_db.table.return_value = chain
        repo.save_config(USER_ID, {'brand': 'foo'})
        mock_db.table.assert_called_with('configs')
        chain.upsert.assert_called_once()
        args, kwargs = chain.upsert.call_args
        assert args[0]['user_id'] == USER_ID
        assert args[0]['data'] == {'brand': 'foo'}
        assert kwargs.get('on_conflict') == 'user_id'


class TestListAccounts:
    def test_empty(self, mock_db):
        mock_db.table.return_value = _chain(final_data=[])
        assert repo.list_accounts(USER_ID) == []

    def test_flattens_data_and_adds_id(self, mock_db):
        mock_db.table.return_value = _chain(final_data=[
            {'id': 'r1', 'updated_at': '2026-01-01', 'data': {'account_number': 'ACC-1', 'account_name': 'A'}},
            {'id': 'r2', 'updated_at': '2026-01-02', 'data': {'account_number': 'ACC-2', 'account_name': 'B'}},
        ])
        out = repo.list_accounts(USER_ID)
        assert len(out) == 2
        assert out[0]['id'] == 'r1'
        assert out[0]['account_name'] == 'A'
        assert out[0]['account_number'] == 'ACC-1'
        # Sorted by account_number
        assert out[0]['account_number'] < out[1]['account_number']


class TestGetAccountByNumber:
    def test_found(self, mock_db):
        row = {'id': 'r1', 'updated_at': 't', 'data': {'account_number': 'ACC-1'}}
        mock_db.table.return_value = _chain(final_data=[row])
        assert repo.get_account_by_number(USER_ID, 'ACC-1') == row

    def test_not_found(self, mock_db):
        mock_db.table.return_value = _chain(final_data=[])
        assert repo.get_account_by_number(USER_ID, 'ACC-999') is None

    def test_uses_jsonb_filter(self, mock_db):
        chain = _chain(final_data=[])
        mock_db.table.return_value = chain
        repo.get_account_by_number(USER_ID, 'ACC-1')
        # eq should be called with the JSONB path filter
        assert any(call.args[0] == 'data->>account_number' for call in chain.eq.call_args_list)


class TestUpsertAccountData:
    def test_returns_true_on_update(self, mock_db):
        chain = _chain(final_data=[{'id': 'r1'}])
        mock_db.table.return_value = chain
        assert repo.upsert_account_data('r1', USER_ID, {'x': 1}, '2026-01-01') is True

    def test_returns_false_on_stale(self, mock_db):
        chain = _chain(final_data=[])  # no rows updated -> stale
        mock_db.table.return_value = chain
        assert repo.upsert_account_data('r1', USER_ID, {'x': 1}, '2026-01-01') is False

    def test_includes_updated_at_check(self, mock_db):
        chain = _chain(final_data=[{'id': 'r1'}])
        mock_db.table.return_value = chain
        repo.upsert_account_data('r1', USER_ID, {'x': 1}, '2026-01-01T00:00:00Z')
        # Should have eq calls for id, user_id, AND updated_at
        eq_columns = [call.args[0] for call in chain.eq.call_args_list]
        assert 'updated_at' in eq_columns
        assert 'user_id' in eq_columns
        assert 'id' in eq_columns


class TestJobs:
    def test_start_job_returns_id(self, mock_db):
        chain = _chain(final_data=[{'id': 'job-abc'}])
        mock_db.table.return_value = chain
        assert repo.start_job(USER_ID, 'refresh') == 'job-abc'

    def test_finish_job_updates_status(self, mock_db):
        chain = _chain()
        mock_db.table.return_value = chain
        repo.finish_job('job-abc', {'result': 42})
        chain.update.assert_called()
        args, _ = chain.update.call_args
        assert args[0]['status'] == 'done'

    def test_fail_job_updates_error(self, mock_db):
        chain = _chain()
        mock_db.table.return_value = chain
        repo.fail_job('job-abc', 'boom')
        args, _ = chain.update.call_args
        assert args[0]['status'] == 'error'
        assert args[0]['error'] == 'boom'

    def test_no_job_id_is_noop(self, mock_db):
        # None job_id should silently no-op (no DB call)
        repo.finish_job(None, {})
        repo.fail_job(None, 'x')
        mock_db.table.assert_not_called()

    def test_get_job(self, mock_db):
        mock_db.table.return_value = _chain(final_data=[{'id': 'j', 'status': 'done'}])
        assert repo.get_job(USER_ID, 'j') == {'id': 'j', 'status': 'done'}


class TestAccountDeletion:
    def test_delete_by_number_returns_true(self, mock_db):
        chain = _chain(final_data=[{'id': 'r1'}])
        mock_db.table.return_value = chain
        assert repo.delete_account_by_number(USER_ID, 'ACC-1') is True

    def test_delete_by_number_returns_false_when_missing(self, mock_db):
        chain = _chain(final_data=[])
        mock_db.table.return_value = chain
        assert repo.delete_account_by_number(USER_ID, 'ACC-999') is False


class TestUserDeletion:
    def test_delete_user_calls_admin(self, mock_db):
        repo.delete_user(USER_ID)
        mock_db.auth.admin.delete_user.assert_called_once_with(USER_ID)
