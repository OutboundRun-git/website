"""Tests for _lib/claude.py — fence extraction, JSON retry, error wrapping."""
import json
from unittest.mock import MagicMock

import pytest

from _lib import claude
from _lib.claude import _extract_body, run_claude_html, run_claude_json, ClaudeError


class TestExtractBody:
    def test_no_fence_returns_input(self):
        assert _extract_body('just text') == 'just text'

    def test_strips_json_fence(self):
        assert _extract_body('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_strips_html_fence(self):
        assert _extract_body('```html\n<p>hi</p>\n```') == '<p>hi</p>'

    def test_strips_bare_fence(self):
        assert _extract_body('```\nsomething\n```') == 'something'

    def test_picks_longest_of_multiple_fences(self):
        text = '```json\n{}\n``` intro then ```json\n{"real": "content", "with": "more"}\n```'
        assert '"real"' in _extract_body(text)

    def test_empty_string_ok(self):
        assert _extract_body('') == ''

    def test_none_ok(self):
        assert _extract_body(None) == ''


class TestRunClaudeJson:
    def _mock_reply(self, anthropic_mock, text):
        content_block = MagicMock()
        content_block.text = text
        msg = MagicMock()
        msg.content = [content_block]
        anthropic_mock.messages.create.return_value = msg

    def test_parses_plain_json(self, anthropic_mock):
        self._mock_reply(anthropic_mock, '{"hello": "world"}')
        assert run_claude_json('do a thing') == {'hello': 'world'}

    def test_parses_fenced_json(self, anthropic_mock):
        self._mock_reply(anthropic_mock, '```json\n{"a": 1}\n```')
        assert run_claude_json('do a thing') == {'a': 1}

    def test_retries_on_malformed_json_then_succeeds(self, anthropic_mock):
        content_block1 = MagicMock(); content_block1.text = 'not json at all'
        msg1 = MagicMock(); msg1.content = [content_block1]
        content_block2 = MagicMock(); content_block2.text = '{"retry": true}'
        msg2 = MagicMock(); msg2.content = [content_block2]
        anthropic_mock.messages.create.side_effect = [msg1, msg2]
        assert run_claude_json('do a thing') == {'retry': True}
        assert anthropic_mock.messages.create.call_count == 2

    def test_raises_claude_error_after_retries_exhausted(self, anthropic_mock):
        content_block = MagicMock(); content_block.text = 'still not json'
        msg = MagicMock(); msg.content = [content_block]
        anthropic_mock.messages.create.return_value = msg
        with pytest.raises(ClaudeError, match='malformed JSON'):
            run_claude_json('do a thing')

    def test_wraps_anthropic_apierror_as_claude_error(self, anthropic_mock):
        from anthropic import APIError
        anthropic_mock.messages.create.side_effect = APIError('boom', request=MagicMock(), body=None)
        with pytest.raises(ClaudeError):
            run_claude_json('do a thing')

    def test_empty_content_raises_claude_error(self, anthropic_mock):
        msg = MagicMock(); msg.content = []
        anthropic_mock.messages.create.return_value = msg
        with pytest.raises(ClaudeError, match='empty'):
            run_claude_json('do a thing')


class TestRunClaudeHtml:
    def test_returns_stripped_body(self, anthropic_mock):
        content_block = MagicMock(); content_block.text = '```html\n<h3>Company</h3>\n```'
        msg = MagicMock(); msg.content = [content_block]
        anthropic_mock.messages.create.return_value = msg
        assert run_claude_html('research prompt') == '<h3>Company</h3>'


class TestSanitizedErrors:
    """Public ClaudeError message must never contain the API key or the raw
    exception text (which could echo the key)."""

    def test_apierror_public_message_is_generic(self, anthropic_mock):
        from anthropic import APIError
        anthropic_mock.messages.create.side_effect = APIError(
            'auth failed: key=sk-ant-SECRETVALUE', request=MagicMock(), body=None
        )
        try:
            run_claude_json('anything')
        except ClaudeError as e:
            assert 'SECRETVALUE' not in str(e)
            assert 'sk-ant' not in str(e)
