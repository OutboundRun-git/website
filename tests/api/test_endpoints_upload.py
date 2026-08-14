"""Tests for upload-accounts + upload-products endpoints."""
from unittest.mock import MagicMock

import pytest

from tests.api.conftest import load_endpoint


def _chain(final_data=None):
    m = MagicMock()
    m.execute.return_value.data = final_data if final_data is not None else []
    for method in ('select', 'eq', 'order', 'limit', 'update', 'insert', 'delete', 'upsert'):
        getattr(m, method).return_value = m
    return m


class TestUploadAccountsEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('upload-accounts')

    def test_uploads_new_accounts(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[])
        csv = 'account_name,industry\nSnowflake,Data Cloud\nDatadog,Observability\n'
        h = make_handler(self.mod.handler, body={'csv': csv, 'mode': 'merge'})
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['added'] == 2

    def test_replace_mode_wipes_existing(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[])
        csv = 'account_name\nSnowflake\n'
        h = make_handler(self.mod.handler, body={'csv': csv, 'mode': 'replace'})
        h.do_POST()
        assert h.response_status == 200
        # delete should have been called
        assert mock_db.table.return_value.delete.called

    def test_missing_csv_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'mode': 'merge'})
        h.do_POST()
        assert h.response_status == 400

    def test_invalid_mode_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'csv': 'x', 'mode': 'invalid'})
        h.do_POST()
        assert h.response_status == 400

    def test_empty_csv_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'csv': 'account_name\n', 'mode': 'merge'})
        h.do_POST()
        assert h.response_status == 400

    def test_oversized_csv_returns_413(self, make_handler, mock_db, authed_user_id):
        big = 'account_name\n' + ('x' * (3 * 1024 * 1024)) + '\n'
        h = make_handler(self.mod.handler, body={'csv': big, 'mode': 'merge'})
        h.do_POST()
        assert h.response_status == 413

    def test_missing_auth_returns_401(self, make_handler, mock_db):
        h = make_handler(self.mod.handler, body={'csv': 'x', 'mode': 'merge'}, authed=False)
        h.do_POST()
        assert h.response_status == 401

    def test_missing_name_column_returns_422_with_helpful_message(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[])
        # CSV has rows but NO account_name / name / company column
        csv = 'foo,bar,baz\nx,y,z\na,b,c\n'
        h = make_handler(self.mod.handler, body={'csv': csv, 'mode': 'merge'})
        h.do_POST()
        assert h.response_status == 422
        assert 'account_name' in h.response_json['error']
        assert 'foo' in h.response_json['error']  # detected columns should be echoed

    def test_bom_prefixed_csv_is_accepted(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[])
        # Excel adds UTF-8 BOM to CSV exports; must not corrupt the first column
        csv = '﻿account_name,industry\nSnowflake,Data\n'
        h = make_handler(self.mod.handler, body={'csv': csv, 'mode': 'merge'})
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['added'] == 1

    def test_name_alias_case_insensitive(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[])
        csv = 'Company,Industry\nSnowflake,Data\n'
        h = make_handler(self.mod.handler, body={'csv': csv, 'mode': 'merge'})
        h.do_POST()
        assert h.response_status == 200
        assert h.response_json['added'] == 1


class TestUploadProductsEndpoint:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('upload-products')

    def test_saves_products(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[{'data': {}}])
        h = make_handler(self.mod.handler, body={'products': [
            {'name': 'Product A', 'short_desc': 'desc A'},
            {'name': 'Product B', 'short_desc': 'desc B'},
        ]})
        h.do_POST()
        assert h.response_status == 200
        assert len(h.response_json['products']) == 2

    def test_filters_out_nameless_products(self, make_handler, mock_db, authed_user_id):
        mock_db.table.return_value = _chain(final_data=[{'data': {}}])
        h = make_handler(self.mod.handler, body={'products': [
            {'name': 'Real', 'short_desc': 'ok'},
            {'name': '', 'short_desc': 'no name'},
        ]})
        h.do_POST()
        assert h.response_status == 200
        assert len(h.response_json['products']) == 1

    def test_no_valid_products_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'products': [{'name': ''}]})
        h.do_POST()
        assert h.response_status == 400

    def test_products_not_array_returns_400(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'products': 'not an array'})
        h.do_POST()
        assert h.response_status == 400

    def test_over_50_products_returns_413(self, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, body={'products': [
            {'name': f'P{i}', 'short_desc': 'x'} for i in range(51)
        ]})
        h.do_POST()
        assert h.response_status == 413
