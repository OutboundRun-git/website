"""Tests for _lib/env.py — env var loading + validation."""
import pytest

from _lib.env import _get, ConfigError


class TestGetHappyPath:
    def test_reads_env_var(self, monkeypatch):
        monkeypatch.setenv('TEST_VAR_HAPPY', 'a_reasonable_length_value_string')
        assert _get('TEST_VAR_HAPPY') == 'a_reasonable_length_value_string'

    def test_strips_whitespace(self, monkeypatch):
        monkeypatch.setenv('TEST_VAR_STRIP', '   value_with_padding_yay!!   ')
        assert _get('TEST_VAR_STRIP') == 'value_with_padding_yay!!'

    def test_prefix_ok(self, monkeypatch):
        monkeypatch.setenv('TEST_VAR_PREFIX', 'sk-ant-abc123456789012345')
        assert _get('TEST_VAR_PREFIX', expect_prefix='sk-ant-').startswith('sk-ant-')

    def test_default_min_len_ok(self, monkeypatch):
        monkeypatch.setenv('TEST_VAR_MIN', 'x' * 20)
        assert _get('TEST_VAR_MIN') == 'x' * 20


class TestGetRejection:
    def test_missing_raises(self, monkeypatch):
        monkeypatch.delenv('TEST_VAR_MISSING', raising=False)
        with pytest.raises(ConfigError, match='Missing env var'):
            _get('TEST_VAR_MISSING')

    def test_too_short_raises(self, monkeypatch):
        monkeypatch.setenv('TEST_VAR_SHORT', 'nope')
        with pytest.raises(ConfigError, match='suspiciously short'):
            _get('TEST_VAR_SHORT')

    def test_wrong_prefix_raises(self, monkeypatch):
        monkeypatch.setenv('TEST_VAR_PREFIX_WRONG', 'not_https_url_valid_placeholder')
        with pytest.raises(ConfigError, match='does not start with expected prefix'):
            _get('TEST_VAR_PREFIX_WRONG', expect_prefix='https://')

    @pytest.mark.parametrize('bad_char', ['\n', '\r', '\t', ' '])
    def test_whitespace_inside_rejected(self, monkeypatch, bad_char):
        # Long enough to pass length check but with internal whitespace
        val = 'sk-ant-abc123' + bad_char + '456789012345'
        monkeypatch.setenv('TEST_VAR_WS', val)
        with pytest.raises(ConfigError, match='whitespace characters'):
            _get('TEST_VAR_WS', expect_prefix='sk-ant-')

    def test_newline_at_end_stripped_but_leading_ok(self, monkeypatch):
        # Trailing whitespace should be stripped, no error
        monkeypatch.setenv('TEST_VAR_TRAILING', 'sk-ant-1234567890123456789\n')
        assert _get('TEST_VAR_TRAILING', expect_prefix='sk-ant-') == 'sk-ant-1234567890123456789'


class TestModuleConstants:
    """Sanity: the fake env vars we set in conftest.py were validated at import."""

    def test_supabase_url_loaded(self):
        from _lib import env
        assert env.SUPABASE_URL.startswith('https://')

    def test_anthropic_key_loaded(self):
        from _lib import env
        assert env.ANTHROPIC_API_KEY.startswith('sk-ant-')

    def test_supabase_anon_key_loaded(self):
        from _lib import env
        assert env.SUPABASE_ANON_KEY.startswith('sb_')
