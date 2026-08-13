"""Anthropic SDK wrapper. Errors are logged server-side; only a generic message
returns to the browser. Robust fence extraction handles multi-block content.
"""
import json
import logging
import re
import threading

from anthropic import Anthropic, APIError

from _lib import env


log = logging.getLogger(__name__)

MODEL = 'claude-sonnet-4-6'
MAX_TOKENS = 8192

_client: Anthropic | None = None
_lock = threading.Lock()


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = Anthropic(api_key=env.ANTHROPIC_API_KEY)
    return _client


class ClaudeError(Exception):
    """Safe-to-return-to-client error. The public message is the exception str."""
    def __init__(self, public_message: str = 'AI service is temporarily unavailable'):
        super().__init__(public_message)


def _call(prompt: str, *, max_tokens: int = MAX_TOKENS) -> str:
    try:
        msg = _get_client().messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            messages=[{'role': 'user', 'content': prompt}],
        )
    except APIError:
        log.exception('anthropic.messages.create failed')
        raise ClaudeError()
    except Exception:
        log.exception('anthropic call raised non-APIError')
        raise ClaudeError()
    if not msg.content:
        raise ClaudeError('AI returned empty response')
    return msg.content[0].text


_FENCE_RE = re.compile(r'```(?:json|html)?\s*\n?(.*?)```', re.DOTALL)


def _extract_body(text: str) -> str:
    text = (text or '').strip()
    if not text:
        return text
    fences = _FENCE_RE.findall(text)
    if fences:
        return max(fences, key=len).strip()
    return text


def run_claude_text(prompt: str) -> str:
    return _call(prompt)


def run_claude_html(prompt: str) -> str:
    return _extract_body(_call(prompt))


def run_claude_json(prompt: str, *, max_retries: int = 1) -> dict:
    attempt = 0
    last_raw = ''
    while attempt <= max_retries:
        raw = _call(prompt if attempt == 0
                    else 'Return ONLY valid JSON. No prose. No code fences.\n\n' + prompt)
        last_raw = raw
        try:
            return json.loads(_extract_body(raw))
        except (json.JSONDecodeError, ValueError):
            attempt += 1
    log.error('claude returned non-JSON after retries: %r', last_raw[:500])
    raise ClaudeError('AI returned malformed JSON')
