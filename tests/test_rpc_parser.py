"""Tests for the Pi RPC stream parser."""

import json

import pytest

from vibes import pi_client
from vibes.pi_client import _read_event


class FakeReader:
    """Simulate asyncio.StreamReader.read() with controlled chunks."""

    def __init__(self, chunks: list[bytes]):
        self._chunks = list(chunks)

    async def read(self, n: int) -> bytes:
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


class ErrorReader:
    """Reader that raises ValueError to simulate buffer overflow."""

    async def read(self, n: int) -> bytes:
        raise ValueError("Separator is found, but chunk is too long")


@pytest.fixture(autouse=True)
def _reset_buffer():
    """Clear the RPC buffer before each test."""
    pi_client._state.rpc_buffer = ""
    yield
    pi_client._state.rpc_buffer = ""


# ---------- _read_event ----------


@pytest.mark.asyncio
async def test_read_event_single_line():
    reader = FakeReader([b'{"type":"agent_end"}\n'])
    event = await _read_event(reader)
    assert event == {"type": "agent_end"}


@pytest.mark.asyncio
async def test_read_event_skips_blank_lines():
    reader = FakeReader([b'\n\n{"type":"ok"}\n'])
    event = await _read_event(reader)
    assert event == {"type": "ok"}


@pytest.mark.asyncio
async def test_read_event_skips_non_json():
    reader = FakeReader([b'some noise\n{"type":"ok"}\n'])
    event = await _read_event(reader)
    assert event == {"type": "ok"}


@pytest.mark.asyncio
async def test_read_event_eof_raises():
    reader = FakeReader([])
    with pytest.raises(RuntimeError, match="connection closed"):
        await _read_event(reader)


@pytest.mark.asyncio
async def test_read_event_eof_with_partial():
    """Partial JSON at EOF — unparseable, so raises."""
    reader = FakeReader([b'{"type":"trun'])
    with pytest.raises(RuntimeError, match="connection closed"):
        await _read_event(reader)


@pytest.mark.asyncio
async def test_read_event_read_overflow():
    """ValueError from read() is handled gracefully and retried."""

    class OverflowThenOk:
        def __init__(self):
            self.call = 0

        async def read(self, n):
            self.call += 1
            if self.call == 1:
                raise ValueError("line too long")
            if self.call == 2:
                return b'{"type":"ok"}\n'
            return b""

    event = await _read_event(OverflowThenOk())
    assert event == {"type": "ok"}


@pytest.mark.asyncio
async def test_read_event_embedded_newline():
    """Event with raw \\n in a string value — raw_decode handles it."""
    # raw_decode(strict=False) parses control chars inside strings.
    event_dict = {"text": "hello\nworld"}
    raw = json.dumps(event_dict).encode()
    # Replace the escaped \\n with a real newline byte.
    raw = raw.replace(b"\\n", b"\n")
    reader = FakeReader([raw + b"\n"])
    event = await _read_event(reader)
    assert event is not None
    assert event["text"] == "hello\nworld"


@pytest.mark.asyncio
async def test_read_event_many_embedded_newlines():
    """Event with hundreds of embedded \\n — must not be dropped."""
    # This is the key case: thinking_delta with large partial.thinking
    thinking = "\n".join(f"line {i}" for i in range(600))
    event_dict = {"type": "thinking_delta", "partial": {"thinking": thinking}}
    raw = json.dumps(event_dict).encode()
    # Replace escaped newlines with raw bytes.
    raw = raw.replace(b"\\n", b"\n")
    reader = FakeReader([raw + b"\n"])
    event = await _read_event(reader)
    assert event is not None
    assert event["type"] == "thinking_delta"
    assert "line 599" in event["partial"]["thinking"]


@pytest.mark.asyncio
async def test_read_event_fragmented():
    """Event split across two read() chunks."""
    raw = b'{"type":"agent_end"}'
    mid = len(raw) // 2
    reader = FakeReader([raw[:mid], raw[mid:] + b"\n"])
    event = await _read_event(reader)
    assert event == {"type": "agent_end"}


@pytest.mark.asyncio
async def test_read_event_two_events_one_chunk():
    reader = FakeReader([b'{"type":"a"}\n{"type":"b"}\n'])
    e1 = await _read_event(reader)
    e2 = await _read_event(reader)
    assert e1 == {"type": "a"}
    assert e2 == {"type": "b"}


@pytest.mark.asyncio
async def test_read_event_control_chars_in_thinking():
    """Real-world: thinking content with raw tabs and CRs."""
    raw = b'{"type":"msg","delta":"plan\tthe\rscript"}\n'
    reader = FakeReader([raw])
    event = await _read_event(reader)
    assert event is not None
    assert "plan" in event["delta"]
    assert "script" in event["delta"]


@pytest.mark.asyncio
async def test_read_event_large_payload():
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
        "assistantMessageEvent": {"type": "text_delta", "delta": "hello"},
    }
    raw = json.dumps(event_dict).encode() + b"\n"
    reader = FakeReader([raw])
    event = await _read_event(reader)
    assert event == event_dict


@pytest.mark.asyncio
async def test_read_event_braces_in_string():
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


@pytest.mark.asyncio
async def test_read_event_malformed_then_valid():
    """Garbage line before a valid event — parser skips it."""
    reader = FakeReader([b"not json\n", b'{"type":"good"}\n'])
    event = await _read_event(reader)
    assert event == {"type": "good"}


@pytest.mark.asyncio
async def test_read_event_buffer_overflow_protection():
    """Buffer overflow triggers truncation, not crash."""
    original_max = pi_client._MAX_RPC_BUFFER
    pi_client._MAX_RPC_BUFFER = 1000  # Low limit for testing.
    try:
        reader = FakeReader([b"x" * 600, b"x" * 600, b'{"type":"ok"}\n'])
        event = await _read_event(reader)
        assert event == {"type": "ok"}
    finally:
        pi_client._MAX_RPC_BUFFER = original_max


@pytest.mark.asyncio
async def test_read_event_buffered_remainder():
    """After parsing, leftover data stays in buffer for next call."""
    pi_client._state.rpc_buffer = '{"type":"a"}{"type":"b"}'
    reader = FakeReader([])
    e1 = await _read_event(reader)
    e2 = await _read_event(reader)
    assert e1 == {"type": "a"}
    assert e2 == {"type": "b"}


@pytest.mark.asyncio
async def test_read_event_malformed_prefix_skipped():
    """A malformed JSON prefix must be skipped, not block forever."""
    # Simulate: broken event sitting in buffer, then valid event arrives.
    pi_client._state.rpc_buffer = '{malformed garbage'
    reader = FakeReader([b'\n{"type":"agent_end"}\n'])
    event = await _read_event(reader)
    assert event == {"type": "agent_end"}


@pytest.mark.asyncio
async def test_read_event_malformed_between_valid():
    """Malformed event sandwiched between valid ones doesn't hang."""
    data = b'{"type":"a"}\n{broken\n{"type":"b"}\n'
    reader = FakeReader([data])
    e1 = await _read_event(reader)
    e2 = await _read_event(reader)
    assert e1 == {"type": "a"}
    assert e2 == {"type": "b"}


@pytest.mark.asyncio
async def test_read_event_stuck_buffer_recovery():
    """After many reads without an event, parser skips stuck prefix."""
    # Simulate a permanently broken event followed by many data chunks,
    # then finally a valid event.  The safety valve should skip the stuck
    # prefix after 20 reads.
    chunks = []
    # Broken event prefix that raw_decode sees as "Unterminated"
    chunks.append(b'{"type":"broken","text":"no closing quote')
    # 25 small chunks of additional noise (no valid JSON)
    for _ in range(25):
        chunks.append(b" more data")
    # Then a valid event after another '{'
    chunks.append(b'\n{"type":"recovered"}\n')
    reader = FakeReader(chunks)
    event = await _read_event(reader)
    assert event == {"type": "recovered"}
