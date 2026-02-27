"""Tests for the Pi RPC stream parser."""

import json

import pytest

from vibes.pi_client import (
    _read_event,
    _try_parse,
)


class FakeReader:
    """Simulate asyncio.StreamReader.readline() with controlled lines."""

    def __init__(self, lines: list[bytes]):
        self._lines = list(lines)

    async def readline(self) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)


class ErrorReader:
    """Reader that raises ValueError to simulate buffer overflow."""

    async def readline(self) -> bytes:
        raise ValueError("Separator is found, but chunk is too long")


# ---------- _try_parse ----------


def test_try_parse_simple():
    assert _try_parse(b'{"type":"agent_end"}') == {"type": "agent_end"}


def test_try_parse_invalid():
    assert _try_parse(b"{broken}") is None


def test_try_parse_not_dict():
    assert _try_parse(b"[1,2,3]") is None


def test_try_parse_tab_in_string():
    """strict=False tolerates raw tab inside string values."""
    result = _try_parse(b'{"text":"hello\tworld"}')
    assert result == {"text": "hello\tworld"}


def test_try_parse_with_raw_newline():
    """strict=False tolerates raw newline inside string values."""
    result = _try_parse(b'{"text":"line1\nline2"}')
    assert result == {"text": "line1\nline2"}


def test_try_parse_null_byte():
    result = _try_parse(b'{"text":"a\x00b"}')
    assert result is not None
    assert result["text"] == "a\x00b"


# ---------- _read_event ----------


@pytest.mark.asyncio
async def test_read_event_single_line():
    reader = FakeReader([b'{"type":"agent_end"}\n'])
    event = await _read_event(reader)
    assert event == {"type": "agent_end"}


@pytest.mark.asyncio
async def test_read_event_skips_blank_lines():
    reader = FakeReader([b"\n", b"\n", b'{"type":"ok"}\n'])
    event = await _read_event(reader)
    assert event == {"type": "ok"}


@pytest.mark.asyncio
async def test_read_event_skips_non_json():
    reader = FakeReader([b"some noise\n", b'{"type":"ok"}\n'])
    event = await _read_event(reader)
    assert event == {"type": "ok"}


@pytest.mark.asyncio
async def test_read_event_eof_raises():
    reader = FakeReader([])
    with pytest.raises(RuntimeError, match="connection closed"):
        await _read_event(reader)


@pytest.mark.asyncio
async def test_read_event_eof_with_partial():
    """Partial line at EOF — unparseable, so raises."""
    reader = FakeReader([b'{"type":"trun'])
    with pytest.raises(RuntimeError, match="connection closed"):
        await _read_event(reader)


@pytest.mark.asyncio
async def test_read_event_eof_with_complete():
    """Complete JSON at EOF (no trailing newline) — should parse."""
    reader = FakeReader([b'{"type":"agent_end"}'])
    event = await _read_event(reader)
    assert event == {"type": "agent_end"}


@pytest.mark.asyncio
async def test_read_event_readline_overflow():
    """ValueError from readline is handled gracefully and retried."""
    class OverflowThenOk:
        def __init__(self):
            self.call = 0
        async def readline(self):
            self.call += 1
            if self.call == 1:
                raise ValueError("line too long")
            if self.call == 2:
                return b'{"type":"ok"}\n'
            return b""

    event = await _read_event(OverflowThenOk())
    assert event == {"type": "ok"}


@pytest.mark.asyncio
async def test_read_event_stitches_embedded_newline():
    """Event with raw \\n in a string value gets split by readline.
    The parser should stitch lines back together."""
    # Original event: {"text":"hello\nworld"}
    # readline() returns two pieces because of the raw 0x0a byte.
    reader = FakeReader([
        b'{"text":"hello\n',
        b'world"}\n',
    ])
    event = await _read_event(reader)
    assert event is not None
    assert event["text"] == "hello\nworld"


@pytest.mark.asyncio
async def test_read_event_stitches_multiple_newlines():
    """Event with multiple raw \\n bytes — needs multiple stitches."""
    reader = FakeReader([
        b'{"text":"a\n',
        b'b\n',
        b'c"}\n',
    ])
    event = await _read_event(reader)
    assert event is not None
    assert event["text"] == "a\nb\nc"


@pytest.mark.asyncio
async def test_read_event_two_events():
    reader = FakeReader([
        b'{"type":"a"}\n',
        b'{"type":"b"}\n',
    ])
    e1 = await _read_event(reader)
    e2 = await _read_event(reader)
    assert e1 == {"type": "a"}
    assert e2 == {"type": "b"}


@pytest.mark.asyncio
async def test_read_event_control_chars_in_thinking():
    """Real-world scenario: thinking content with raw tabs and CRs."""
    # These don't cause line splits (only \n does), so single readline.
    raw = b'{"type":"msg","delta":"plan\tthe\rscript"}\n'
    reader = FakeReader([raw])
    event = await _read_event(reader)
    assert event is not None
    assert "plan" in event["delta"]
    assert "script" in event["delta"]


@pytest.mark.asyncio
async def test_read_event_large_payload():
    """Large tool call IDs (seen in production) are handled."""
    long_id = "call_xyz|" + "A" * 60000
    event_dict = {"type": "turn_end", "toolCallId": long_id}
    raw = json.dumps(event_dict).encode() + b"\n"
    reader = FakeReader([raw])
    event = await _read_event(reader)
    assert event is not None
    assert event["type"] == "turn_end"
    assert len(event["toolCallId"]) == len(long_id)


@pytest.mark.asyncio
async def test_read_event_nested_json():
    event_dict = {
        "type": "message_update",
        "assistantMessageEvent": {
            "type": "text_delta",
            "delta": "hello",
        },
    }
    raw = json.dumps(event_dict).encode() + b"\n"
    reader = FakeReader([raw])
    event = await _read_event(reader)
    assert event == event_dict


@pytest.mark.asyncio
async def test_read_event_braces_in_string():
    """Braces inside string values must not affect parsing."""
    event_dict = {"type": "update", "text": "function() { return {}; }"}
    raw = json.dumps(event_dict).encode() + b"\n"
    reader = FakeReader([raw])
    event = await _read_event(reader)
    assert event == event_dict


@pytest.mark.asyncio
async def test_read_event_escaped_quotes():
    event_dict = {"type": "update", "text": 'say "hello" world'}
    raw = json.dumps(event_dict).encode() + b"\n"
    reader = FakeReader([raw])
    event = await _read_event(reader)
    assert event == event_dict


@pytest.mark.asyncio
async def test_read_event_backslash_path():
    event_dict = {"type": "update", "path": "C:\\Users\\"}
    raw = json.dumps(event_dict).encode() + b"\n"
    reader = FakeReader([raw])
    event = await _read_event(reader)
    assert event == event_dict
