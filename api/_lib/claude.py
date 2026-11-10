"""Anthropic SDK wrapper. Errors are logged server-side; only a generic message
returns to the browser. Robust fence extraction handles multi-block content.

Server-side web_search tool can be opted into per call with use_web_search=True.
The tool is billed at $10/1000 searches by Anthropic in addition to token cost.
Enable only on endpoints that need live web access (research, next-contacts).
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
WEB_SEARCH_TOOL_TYPE = 'web_search_20250305'
MAX_PAUSE_TURN_ITERATIONS = 6

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


def _collect_text(blocks) -> str:
    """Concatenate all text-type blocks. Skips server_tool_use and
    web_search_tool_result blocks that interleave when the model searches."""
    parts: list[str] = []
    for b in blocks or []:
        t = getattr(b, 'type', None)
        if t == 'text':
            parts.append(getattr(b, 'text', '') or '')
    return ''.join(parts)


def _serialize_assistant_content(blocks):
    """Round-trip the assistant's content blocks so the next request can resume
    a paused turn. Anthropic requires that search-result blocks be sent back
    exactly as received, including their encrypted_content."""
    out = []
    for b in blocks or []:
        if hasattr(b, 'model_dump'):
            out.append(b.model_dump(exclude_none=True))
        elif isinstance(b, dict):
            out.append(b)
    return out


def _call(prompt: str, *, max_tokens: int = MAX_TOKENS,
          use_web_search: bool = False, max_searches: int = 5) -> str:
    kwargs_base: dict = {'model': MODEL, 'max_tokens': max_tokens}
    if use_web_search:
        kwargs_base['tools'] = [{
            'type': WEB_SEARCH_TOOL_TYPE,
            'name': 'web_search',
            'max_uses': max_searches,
        }]
    messages: list[dict] = [{'role': 'user', 'content': prompt}]
    for _ in range(MAX_PAUSE_TURN_ITERATIONS):
        try:
            msg = _get_client().messages.create(messages=messages, **kwargs_base)
        except APIError:
            log.exception('anthropic.messages.create failed')
            raise ClaudeError()
        except Exception:
            log.exception('anthropic call raised non-APIError')
            raise ClaudeError()
        if getattr(msg, 'stop_reason', None) == 'pause_turn':
            messages.append({'role': 'assistant', 'content': _serialize_assistant_content(msg.content)})
            continue
        text = _collect_text(msg.content)
        if not text:
            raise ClaudeError('AI returned empty response')
        return text
    log.error('web_search turn did not complete within pause_turn limit')
    raise ClaudeError('AI search exceeded turn limit')


_FENCE_RE = re.compile(r'```(?:json|html)?\s*\n?(.*?)```', re.DOTALL)


def _extract_body(text: str) -> str:
    text = (text or '').strip()
    if not text:
        return text
    fences = _FENCE_RE.findall(text)
    if fences:
        return max(fences, key=len).strip()
    return text


def run_claude_text(prompt: str, *, use_web_search: bool = False, max_searches: int = 5) -> str:
    return _call(prompt, use_web_search=use_web_search, max_searches=max_searches)


def run_claude_html(prompt: str, *, use_web_search: bool = False, max_searches: int = 5) -> str:
    return _extract_body(_call(prompt, use_web_search=use_web_search, max_searches=max_searches))


def run_claude_json(prompt: str, *, max_retries: int = 1,
                    use_web_search: bool = False, max_searches: int = 5) -> dict:
    attempt = 0
    last_raw = ''
    while attempt <= max_retries:
        raw = _call(
            prompt if attempt == 0
            else 'Return ONLY valid JSON. No prose. No code fences.\n\n' + prompt,
            use_web_search=use_web_search,
            max_searches=max_searches,
        )
        last_raw = raw
        try:
            return json.loads(_extract_body(raw))
        except (json.JSONDecodeError, ValueError):
            attempt += 1
    log.error('claude returned non-JSON after retries: %r', last_raw[:500])
    raise ClaudeError('AI returned malformed JSON')
