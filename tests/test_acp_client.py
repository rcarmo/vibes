"""Tests for ACP client."""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from vibes import acp_client


class TestAcpClient:
    """Test ACP client functions."""

    def setup_method(self):
        """Reset global state before each test."""
        acp_client.reset_state()

    def test_next_request_id(self):
        """Test request ID generation."""
        id1 = acp_client._next_request_id()
        id2 = acp_client._next_request_id()
        id3 = acp_client._next_request_id()
        
        assert id1 == 1
        assert id2 == 2
        assert id3 == 3

    def test_is_agent_running_false(self):
        """Test is_agent_running when no agent."""
        assert acp_client.is_agent_running() is False

    def test_is_agent_running_with_terminated_proc(self):
        """Test is_agent_running with terminated process."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0  # Terminated
        acp_client.get_state().agent_proc = mock_proc
        
        assert acp_client.is_agent_running() is False

    def test_is_agent_running_with_active_proc(self):
        """Test is_agent_running with active process."""
        mock_proc = MagicMock()
        mock_proc.returncode = None  # Still running
        acp_client.get_state().agent_proc = mock_proc
        
        assert acp_client.is_agent_running() is True

    @pytest.mark.asyncio
    async def test_read_response_success(self):
        """Test reading a valid JSON response."""
        mock_reader = AsyncMock()
        response_data = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
        mock_reader.readline = AsyncMock(return_value=json.dumps(response_data).encode() + b'\n')
        
        result = await acp_client._read_response(mock_reader)
        assert result == response_data

    @pytest.mark.asyncio
    async def test_read_response_empty_closes(self):
        """Test that empty response raises error."""
        mock_reader = AsyncMock()
        mock_reader.readline = AsyncMock(return_value=b'')
        
        with pytest.raises(RuntimeError, match="connection closed"):
            await acp_client._read_response(mock_reader)

    @pytest.mark.asyncio
    async def test_read_response_invalid_json(self):
        """Test that invalid JSON raises error."""
        mock_reader = AsyncMock()
        mock_reader.readline = AsyncMock(return_value=b'not json\n')
        
        with pytest.raises(RuntimeError, match="Invalid JSON"):
            await acp_client._read_response(mock_reader)

    @pytest.mark.asyncio
    async def test_send_request_not_connected(self):
        """Test send_request when not connected."""
        with pytest.raises(RuntimeError, match="not connected"):
            await acp_client._send_request("test", {})

    @pytest.mark.asyncio
    async def test_send_request_success(self):
        """Test successful request/response."""
        mock_writer = AsyncMock()
        mock_reader = AsyncMock()
        
        # Setup writer
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        
        # Setup reader to return matching response
        response = {"jsonrpc": "2.0", "id": 1, "result": {"message": "ok"}}
        mock_reader.readline = AsyncMock(return_value=json.dumps(response).encode() + b'\n')
        
        state = acp_client.get_state()
        state.agent_writer = mock_writer
        state.agent_reader = mock_reader
        state.request_id = 0
        
        result = await acp_client._send_request("test/method", {"arg": "value"})
        
        assert result == {"message": "ok"}
        mock_writer.write.assert_called_once()
        
        # Verify request format
        written_data = mock_writer.write.call_args[0][0].decode()
        request = json.loads(written_data)
        assert request["method"] == "test/method"
        assert request["params"] == {"arg": "value"}

    @pytest.mark.asyncio
    async def test_send_request_with_error(self):
        """Test request that returns error."""
        mock_writer = AsyncMock()
        mock_reader = AsyncMock()
        
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        
        response = {"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "Failed"}}
        mock_reader.readline = AsyncMock(return_value=json.dumps(response).encode() + b'\n')
        
        state = acp_client.get_state()
        state.agent_writer = mock_writer
        state.agent_reader = mock_reader
        state.request_id = 0
        
        with pytest.raises(RuntimeError, match="Agent error"):
            await acp_client._send_request("test", {})

    @pytest.mark.asyncio
    async def test_send_request_collects_updates(self):
        """Test that session updates are collected."""
        mock_writer = AsyncMock()
        mock_reader = AsyncMock()
        
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        
        # Return notification, then response
        notification = {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "Hello "}
                }
            }
        }
        tool_call = {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "title": "Reading file"
                }
            }
        }
        post_tool_notification = {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "World"}
                }
            }
        }
        response = {"jsonrpc": "2.0", "id": 1, "result": {}}
        
        responses = [
            json.dumps(notification).encode() + b'\n',
            json.dumps(tool_call).encode() + b'\n',
            json.dumps(post_tool_notification).encode() + b'\n',
            json.dumps(response).encode() + b'\n'
        ]
        mock_reader.readline = AsyncMock(side_effect=responses)
        
        state = acp_client.get_state()
        state.agent_writer = mock_writer
        state.agent_reader = mock_reader
        state.request_id = 0
        
        result = await acp_client._send_request("test", {}, collect_updates=True)
        
        # Only post-tool content is kept in the final response
        assert result["_collected_text"] == "World"

    @pytest.mark.asyncio
    async def test_send_request_with_status_callback(self):
        """Test that status callback is called for tool_call updates."""
        mock_writer = AsyncMock()
        mock_reader = AsyncMock()
        mock_callback = AsyncMock()
        
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        
        notification = {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "title": "Running tests..."
                }
            }
        }
        response = {"jsonrpc": "2.0", "id": 1, "result": {}}
        
        responses = [
            json.dumps(notification).encode() + b'\n',
            json.dumps(response).encode() + b'\n'
        ]
        mock_reader.readline = AsyncMock(side_effect=responses)
        
        state = acp_client.get_state()
        state.agent_writer = mock_writer
        state.agent_reader = mock_reader
        state.request_id = 0
        
        await acp_client._send_request("test", {}, collect_updates=True, status_callback=mock_callback)
        
        mock_callback.assert_called_once_with({"type": "tool_call", "title": "Running tests..."})

    @pytest.mark.asyncio
    async def test_stop_agent(self):
        """Test stopping the agent."""
        mock_proc = AsyncMock()
        mock_proc.terminate = MagicMock()
        mock_proc.wait = AsyncMock()
        mock_proc.returncode = None
        
        state = acp_client.get_state()
        state.agent_proc = mock_proc
        state.agent_reader = MagicMock()
        state.agent_writer = MagicMock()
        state.session_id = "test-session"
        
        await acp_client.stop_agent()
        
        mock_proc.terminate.assert_called_once()
        state = acp_client.get_state()
        assert state.agent_proc is None
        assert state.session_id is None

    @pytest.mark.asyncio
    async def test_send_message_simple_no_session(self):
        """Test send_message_simple when session fails."""
        with patch.object(acp_client, '_ensure_agent', new_callable=AsyncMock) as mock_ensure:
            mock_ensure.return_value = None
            acp_client.get_state().session_id = None
            
            result = await acp_client.send_message_simple("Hello")
            
            assert "[Error: No active session]" in result

    @pytest.mark.asyncio
    async def test_send_message_simple_timeout(self):
        """Test send_message_simple on timeout."""
        with patch.object(acp_client, '_ensure_agent', new_callable=AsyncMock):
            with patch.object(acp_client, '_send_request', new_callable=AsyncMock) as mock_send:
                mock_send.side_effect = asyncio.TimeoutError()
                acp_client.get_state().session_id = "test-session"
                
                result = await acp_client.send_message_simple("Hello")
                
                assert "timed out" in result.lower()

    @pytest.mark.asyncio
    async def test_send_message_simple_success(self):
        """Test successful send_message_simple."""
        with patch.object(acp_client, '_ensure_agent', new_callable=AsyncMock):
            with patch.object(acp_client, '_send_request', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = {"_collected_text": "Hello from agent!"}
                acp_client.get_state().session_id = "test-session"
                
                result = await acp_client.send_message_simple("Hello")
                
                assert result == "Hello from agent!"

    @pytest.mark.asyncio
    async def test_send_message_yields_response(self):
        """Test send_message async iterator."""
        with patch.object(acp_client, 'send_message_simple', new_callable=AsyncMock) as mock_simple:
            mock_simple.return_value = "Response text"
            
            responses = []
            async for chunk in acp_client.send_message("Hello"):
                responses.append(chunk)
            
            assert responses == ["Response text"]

    @pytest.mark.asyncio
    async def test_start_agent_success(self):
        """Test start_agent returns True on success."""
        with patch.object(acp_client, '_ensure_agent', new_callable=AsyncMock):
            result = await acp_client.start_agent()
            assert result is True

    @pytest.mark.asyncio
    async def test_start_agent_failure(self):
        """Test start_agent returns False on failure."""
        with patch.object(acp_client, '_ensure_agent', new_callable=AsyncMock) as mock_ensure:
            mock_ensure.side_effect = RuntimeError("Agent not found")
            
            result = await acp_client.start_agent()
            assert result is False

    @pytest.mark.asyncio
    async def test_send_message_simple_concurrent_error_restarts_agent(self):
        """Test that concurrent prompt error triggers agent restart."""
        with patch.object(acp_client, '_ensure_agent', new_callable=AsyncMock):
            with patch.object(acp_client, '_send_request', new_callable=AsyncMock) as mock_send:
                with patch.object(acp_client, 'stop_agent', new_callable=AsyncMock) as mock_stop:
                    mock_send.side_effect = RuntimeError("Concurrent prompts are not supported")
                    acp_client.get_state().session_id = "test-session"
                    
                    result = await acp_client.send_message_simple("Hello")
                    
                    assert "busy" in result.lower() or "try again" in result.lower()
                    mock_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_simple_lock_check(self):
        """Test that busy check works when lock is held."""
        # Acquire the lock
        await acp_client.get_state().request_lock.acquire()
        
        try:
            result = await acp_client.send_message_simple("Hello")
            assert "busy" in result.lower()
        finally:
            acp_client.get_state().request_lock.release()


class TestContentParsing:
    """Test content block parsing functions."""

    def test_parse_text_block(self):
        """Test parsing text content block."""
        block = {"type": "text", "text": "Hello world"}
        result = acp_client._parse_content_block(block)
        assert result == {"type": "text", "text": "Hello world"}

    def test_parse_image_block_base64(self):
        """Test parsing image block with base64 data."""
        block = {
            "type": "image",
            "content": "iVBORw0KGgo=",
            "content_encoding": "base64",
            "content_type": "image/png"
        }
        result = acp_client._parse_content_block(block)
        assert result["type"] == "image"
        assert result["data"] == "iVBORw0KGgo="
        assert result["encoding"] == "base64"
        assert result["mime_type"] == "image/png"

    def test_parse_image_block_url(self):
        """Test parsing image block with URL."""
        block = {
            "type": "image",
            "content_url": "https://example.com/image.png",
            "content_type": "image/png"
        }
        result = acp_client._parse_content_block(block)
        assert result["type"] == "image"
        assert result["url"] == "https://example.com/image.png"
        assert result["mime_type"] == "image/png"

    def test_parse_file_block(self):
        """Test parsing file/artifact block."""
        block = {
            "type": "file",
            "name": "data.json",
            "content": "eyJrZXkiOiAidmFsdWUifQ==",
            "content_encoding": "base64",
            "content_type": "application/json"
        }
        result = acp_client._parse_content_block(block)
        assert result["type"] == "file"
        assert result["name"] == "data.json"
        assert result["mime_type"] == "application/json"

    def test_parse_unknown_block(self):
        """Test parsing unknown block type preserves it."""
        block = {"type": "custom", "data": "something"}
        result = acp_client._parse_content_block(block)
        assert result == block

    def test_parse_empty_block(self):
        """Test parsing block without type returns None."""
        block = {"data": "no type"}
        result = acp_client._parse_content_block(block)
        assert result is None

    def test_collect_content_blocks_dict(self):
        """Test collecting content from dict."""
        content = {"type": "text", "text": "Hello"}
        collected = []
        acp_client._collect_content_blocks(content, collected)
        assert len(collected) == 1
        assert collected[0]["type"] == "text"

    def test_collect_content_blocks_list(self):
        """Test collecting content from list."""
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "image", "content_url": "https://example.com/img.png"}
        ]
        collected = []
        acp_client._collect_content_blocks(content, collected)
        assert len(collected) == 2
        assert collected[0]["type"] == "text"
        assert collected[1]["type"] == "image"

    @pytest.mark.asyncio
    async def test_send_message_multimodal_success(self):
        """Test send_message_multimodal returns structured response."""
        with patch.object(acp_client, '_ensure_agent', new_callable=AsyncMock):
            with patch.object(acp_client, '_send_request', new_callable=AsyncMock) as mock_send:
                mock_send.return_value = {
                    "_collected_text": "Here is an image",
                    "_collected_content": [
                        {"type": "text", "text": "Here is an image"},
                        {"type": "image", "url": "https://example.com/img.png", "mime_type": "image/png"}
                    ]
                }
                acp_client.get_state().session_id = "test-session"
                
                result = await acp_client.send_message_multimodal("Generate an image")
                
                assert result["text"] == "Here is an image"
                assert len(result["content"]) == 2
                assert result["content"][1]["type"] == "image"

    @pytest.mark.asyncio
    async def test_send_message_multimodal_busy(self):
        """Test send_message_multimodal when agent is busy."""
        await acp_client.get_state().request_lock.acquire()
        
        try:
            result = await acp_client.send_message_multimodal("Hello")
            assert "busy" in result["text"].lower()
            assert len(result["content"]) == 1
        finally:
            acp_client.get_state().request_lock.release()
