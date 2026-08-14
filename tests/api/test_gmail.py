"""Tests for _lib/gmail.py — state HMAC + OAuth flow + send via Gmail API."""
import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest

from _lib import gmail
from _lib.gmail import encode_state, decode_state, GmailError


USER_ID = '11111111-2222-3333-4444-555555555555'


class TestStateHmac:
    def test_roundtrip(self):
        state = encode_state(USER_ID)
        assert decode_state(state) == USER_ID

    def test_tampered_signature_rejected(self):
        state = encode_state(USER_ID)
        payload_b64, sig = state.split('.', 1)
        tampered = payload_b64 + '.' + ('0' * len(sig))
        with pytest.raises(GmailError, match='signature'):
            decode_state(tampered)

    def test_tampered_payload_rejected(self):
        state = encode_state(USER_ID)
        payload_b64, sig = state.split('.', 1)
        # Change the payload — signature no longer matches
        bad_payload = base64.urlsafe_b64encode(b'{"uid":"attacker","ts":9999999999,"nonce":"x"}').decode().rstrip('=')
        tampered = bad_payload + '.' + sig
        with pytest.raises(GmailError, match='signature'):
            decode_state(tampered)

    def test_malformed_state_rejected(self):
        with pytest.raises(GmailError, match='Invalid'):
            decode_state('not-a-state')

    def test_empty_state_rejected(self):
        with pytest.raises(GmailError, match='Invalid'):
            decode_state('')

    def test_expired_state_rejected(self, mocker):
        # Encode with a timestamp older than STATE_TTL_SECONDS
        old_time = int(time.time()) - gmail.STATE_TTL_SECONDS - 100
        payload = {'uid': USER_ID, 'ts': old_time, 'nonce': 'a1b2c3d4'}
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        import hmac, hashlib
        sig = hmac.new(gmail._state_secret(), payload_b64.encode(), hashlib.sha256).hexdigest()
        expired = f'{payload_b64}.{sig}'
        with pytest.raises(GmailError, match='expired'):
            decode_state(expired)


class TestBuildOauthUrl:
    def test_includes_required_params(self):
        url = gmail.build_oauth_url(USER_ID)
        assert 'client_id=' in url
        assert 'redirect_uri=' in url
        assert 'response_type=code' in url
        assert 'scope=' in url
        assert 'gmail.send' in url
        assert 'access_type=offline' in url
        assert 'prompt=consent' in url
        assert 'state=' in url

    def test_state_decodes_back_to_user(self):
        url = gmail.build_oauth_url(USER_ID)
        # extract state param
        state = url.split('state=')[1].split('&')[0]
        # URL-decoded state (urlencode escapes . but not always; safe path is
        # to just try both)
        import urllib.parse
        state = urllib.parse.unquote(state)
        assert decode_state(state) == USER_ID


class TestGmailNotConfigured:
    def test_build_oauth_url_raises_when_missing(self, mocker):
        mocker.patch('_lib.gmail.env.gmail_configured', return_value=False)
        with pytest.raises(GmailError, match='not configured'):
            gmail.build_oauth_url(USER_ID)


class TestExchangeCodeForTokens:
    def _mock_urlopen(self, mocker, responses):
        """Configure urllib.request.urlopen to return the given sequence of
        JSON responses."""
        contexts = []
        for r in responses:
            cm = MagicMock()
            cm.__enter__.return_value.read.return_value = json.dumps(r).encode()
            cm.__exit__.return_value = None
            contexts.append(cm)
        mocker.patch('urllib.request.urlopen', side_effect=contexts)

    def test_happy_path(self, mocker):
        self._mock_urlopen(mocker, [
            {'refresh_token': 'rt_1', 'access_token': 'at_1', 'token_type': 'Bearer'},
            {'email': 'user@gmail.com', 'sub': '123'},
        ])
        result = gmail.exchange_code_for_tokens('auth_code_here')
        assert result['refresh_token'] == 'rt_1'
        assert result['access_token'] == 'at_1'
        assert result['email'] == 'user@gmail.com'

    def test_missing_refresh_token_raises(self, mocker):
        self._mock_urlopen(mocker, [
            {'access_token': 'at_1'},  # no refresh_token
        ])
        with pytest.raises(GmailError, match='refresh token'):
            gmail.exchange_code_for_tokens('code')


class TestRefreshAccessToken:
    def test_returns_access_token(self, mocker):
        cm = MagicMock()
        cm.__enter__.return_value.read.return_value = json.dumps({
            'access_token': 'fresh_access', 'expires_in': 3600
        }).encode()
        mocker.patch('urllib.request.urlopen', return_value=cm)
        assert gmail.refresh_access_token('rt_stored') == 'fresh_access'

    def test_missing_access_token_raises(self, mocker):
        cm = MagicMock()
        cm.__enter__.return_value.read.return_value = json.dumps({}).encode()
        mocker.patch('urllib.request.urlopen', return_value=cm)
        with pytest.raises(GmailError, match='refresh returned no access token'):
            gmail.refresh_access_token('rt_stored')


class TestGmailSend:
    def test_sends_and_returns_message_id(self, mocker):
        cm = MagicMock()
        cm.__enter__.return_value.read.return_value = json.dumps({
            'id': '18abc123def456', 'threadId': 'x'
        }).encode()
        mocker.patch('urllib.request.urlopen', return_value=cm)
        msg_id = gmail.send('at_1', 'from@x.com', 'to@y.com', 'Hi', 'Hello.')
        assert msg_id == '18abc123def456'

    def test_wraps_http_error(self, mocker):
        import urllib.error
        mocker.patch(
            'urllib.request.urlopen',
            side_effect=urllib.error.HTTPError('u', 403, 'forbidden', {}, None),
        )
        with pytest.raises(GmailError):
            gmail.send('at_1', 'from@x.com', 'to@y.com', 'Hi', 'Hello.')
