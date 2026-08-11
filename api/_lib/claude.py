"""Anthropic SDK wrapper. Replaces the local Claude Code CLI subprocess calls.

The four prompt patterns in this app return either raw HTML (research) or JSON
(everything else). Both helpers strip markdown fences that Claude sometimes wraps
around outputs even when told not to.
"""
import json
import os
from anthropic import Anthropic


_client: Anthropic | None = None
MODEL = 'claude-sonnet-4-6'
MAX_TOKENS = 8192


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic()  # reads ANTHROPIC_API_KEY from env
    return _client


def _strip_fences(text: str) -> str:
    """Strip surrounding ```json ... ``` or ``` ... ``` fences if present."""
    text = text.strip()
    if not text.startswith('```'):
        return text
    parts = text.split('```', 2)
    if len(parts) < 3:
        return text
    inner = parts[1]
    for prefix in ('json\n', 'html\n', 'json', 'html'):
        if inner.startswith(prefix):
            inner = inner[len(prefix):]
            break
    return inner.lstrip('\n').rstrip()


def run_claude_text(prompt: str) -> str:
    """Send a prompt, return the raw text response."""
    client = _get_client()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return msg.content[0].text


def run_claude_json(prompt: str) -> dict:
    """Send a prompt, expect JSON. Retry once with a JSON-only prefix if parse fails."""
    raw = run_claude_text(prompt)
    stripped = _strip_fences(raw)
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        retry_prefix = 'Return ONLY valid JSON, no prose, no code fences.\n\n'
        raw = run_claude_text(retry_prefix + prompt)
        stripped = _strip_fences(raw)
        return json.loads(stripped)


def run_claude_html(prompt: str) -> str:
    """Send a prompt, expect raw HTML (research prompt). Strip fences if present."""
    raw = run_claude_text(prompt)
    return _strip_fences(raw)
