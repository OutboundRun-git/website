"""Env var loading with whitespace stripping, prefix validation, fail-fast.

Every env access goes through here. Prevents the "newline in the API key" class
of bug that took production down (Anthropic API key had an embedded \\n from
paste corruption; httpx rejected the header; whole app broke).
"""
import os


class ConfigError(RuntimeError):
    pass


def _get(name: str, expect_prefix: str | None = None, min_len: int = 20) -> str:
    raw = os.environ.get(name)
    if raw is None:
        raise ConfigError(f'Missing env var: {name}')
    value = raw.strip()
    if len(value) < min_len:
        raise ConfigError(f'{name} is suspiciously short ({len(value)} chars)')
    if expect_prefix and not value.startswith(expect_prefix):
        raise ConfigError(f'{name} does not start with expected prefix {expect_prefix!r}')
    if any(c in value for c in ('\n', '\r', '\t', ' ')):
        raise ConfigError(f'{name} contains whitespace characters; likely paste corruption')
    return value


SUPABASE_URL              = _get('SUPABASE_URL',              expect_prefix='https://')
SUPABASE_ANON_KEY         = _get('SUPABASE_ANON_KEY',         expect_prefix='sb_')
SUPABASE_SERVICE_ROLE_KEY = _get('SUPABASE_SERVICE_ROLE_KEY')
ANTHROPIC_API_KEY         = _get('ANTHROPIC_API_KEY',         expect_prefix='sk-ant-')
