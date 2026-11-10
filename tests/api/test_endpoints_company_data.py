"""Tests for get-company-data + update-company-data endpoints."""
from unittest.mock import MagicMock

import pytest

from tests.api.conftest import load_endpoint


COMPANY_ID = '11111111-1111-1111-1111-111111111111'
OTHER_COMPANY = '22222222-2222-2222-2222-222222222222'


def _chain(final_data=None):
    m = MagicMock()
    m.execute.return_value.data = final_data if final_data is not None else []
    for method in ('select', 'eq', 'order', 'limit', 'update', 'insert', 'delete', 'upsert'):
        getattr(m, method).return_value = m
    return m


class TestGetCompanyData:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('get-company-data')

    def test_admin_can_read_any_company(self, mocker, make_handler, mock_db, authed_user_id):
        mocker.patch('_lib.repo.get_user_profile_full', return_value={
            'is_admin': True, 'company_id': OTHER_COMPANY, 'role': 'member',
        })
        mocker.patch('_lib.repo.get_company_data', return_value={
            'credible_external_sources': ['SEC EDGAR'],
        })
        h = make_handler(self.mod.handler, path=f'/api/get-company-data?company_id={COMPANY_ID}')
        h.command = 'GET'
        h.do_GET()
        assert h.response_status == 200
        assert h.response_json['data']['credible_external_sources'] == ['SEC EDGAR']

    def test_member_can_read_own_company(self, mocker, make_handler, mock_db, authed_user_id):
        mocker.patch('_lib.repo.get_user_profile_full', return_value={
            'is_admin': False, 'company_id': COMPANY_ID, 'role': 'member',
        })
        mocker.patch('_lib.repo.get_company_data', return_value={})
        h = make_handler(self.mod.handler, path=f'/api/get-company-data?company_id={COMPANY_ID}')
        h.command = 'GET'
        h.do_GET()
        assert h.response_status == 200

    def test_non_member_non_admin_is_forbidden(self, mocker, make_handler, mock_db, authed_user_id):
        mocker.patch('_lib.repo.get_user_profile_full', return_value={
            'is_admin': False, 'company_id': OTHER_COMPANY, 'role': 'member',
        })
        h = make_handler(self.mod.handler, path=f'/api/get-company-data?company_id={COMPANY_ID}')
        h.command = 'GET'
        h.do_GET()
        assert h.response_status == 403

    def test_bad_uuid_returns_400(self, mocker, make_handler, mock_db, authed_user_id):
        h = make_handler(self.mod.handler, path='/api/get-company-data?company_id=not-a-uuid')
        h.command = 'GET'
        h.do_GET()
        assert h.response_status == 400


class TestUpdateCompanyData:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.mod = load_endpoint('update-company-data')

    def test_admin_can_update_any_company(self, mocker, make_handler, mock_db, authed_user_id):
        mocker.patch('_lib.repo.get_user_profile_full', return_value={
            'is_admin': True, 'company_id': OTHER_COMPANY, 'role': 'member',
        })
        mocker.patch('_lib.repo.get_company_data', return_value={})
        upd = mocker.patch('_lib.repo.update_company_data')
        h = make_handler(self.mod.handler, body={
            'company_id': COMPANY_ID,
            'data': {'credible_external_sources': ['SEC EDGAR', 'Bloomberg']},
        })
        h.do_POST()
        assert h.response_status == 200
        upd.assert_called_once()

    def test_manager_can_update_own_company(self, mocker, make_handler, mock_db, authed_user_id):
        mocker.patch('_lib.repo.get_user_profile_full', return_value={
            'is_admin': False, 'company_id': COMPANY_ID, 'role': 'manager',
        })
        mocker.patch('_lib.repo.get_company_data', return_value={})
        mocker.patch('_lib.repo.update_company_data')
        h = make_handler(self.mod.handler, body={
            'company_id': COMPANY_ID,
            'data': {'internal_sources': ['CRM']},
        })
        h.do_POST()
        assert h.response_status == 200

    def test_member_cannot_update(self, mocker, make_handler, mock_db, authed_user_id):
        mocker.patch('_lib.repo.get_user_profile_full', return_value={
            'is_admin': False, 'company_id': COMPANY_ID, 'role': 'member',
        })
        h = make_handler(self.mod.handler, body={
            'company_id': COMPANY_ID,
            'data': {'credible_external_sources': ['x']},
        })
        h.do_POST()
        assert h.response_status == 403

    def test_unknown_keys_dropped(self, mocker, make_handler, mock_db, authed_user_id):
        mocker.patch('_lib.repo.get_user_profile_full', return_value={
            'is_admin': True, 'company_id': COMPANY_ID, 'role': 'manager',
        })
        mocker.patch('_lib.repo.get_company_data', return_value={})
        upd = mocker.patch('_lib.repo.update_company_data')
        h = make_handler(self.mod.handler, body={
            'company_id': COMPANY_ID,
            'data': {
                'credible_external_sources': ['SEC'],
                'arbitrary_hack_key': 'malicious',
            },
        })
        h.do_POST()
        assert h.response_status == 200
        saved = upd.call_args[0][1]
        assert 'credible_external_sources' in saved
        assert 'arbitrary_hack_key' not in saved

    def test_non_array_value_returns_400(self, mocker, make_handler, mock_db, authed_user_id):
        mocker.patch('_lib.repo.get_user_profile_full', return_value={
            'is_admin': True, 'company_id': COMPANY_ID, 'role': 'manager',
        })
        h = make_handler(self.mod.handler, body={
            'company_id': COMPANY_ID,
            'data': {'credible_external_sources': 'not an array'},
        })
        h.do_POST()
        assert h.response_status == 400
