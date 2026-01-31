"""Tests for ACP protocol module."""

from vibes import acp_protocol


class TestFrameClassification:
    """Test JSON-RPC frame classification."""

    def test_notification_no_id_with_method(self):
        msg = {"jsonrpc": "2.0", "method": "session/update", "params": {}}
        assert acp_protocol.classify_frame(msg) == "notification"
        assert acp_protocol.is_notification(msg) is True
        assert acp_protocol.is_request(msg) is False
        assert acp_protocol.is_response(msg) is False

    def test_request_has_id_and_method(self):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "session/request_permission", "params": {}}
        assert acp_protocol.classify_frame(msg) == "request"
        assert acp_protocol.is_request(msg) is True
        assert acp_protocol.is_notification(msg) is False
        assert acp_protocol.is_response(msg) is False

    def test_response_has_id_and_result(self):
        msg = {"jsonrpc": "2.0", "id": 1, "result": {"sessionId": "abc"}}
        assert acp_protocol.classify_frame(msg) == "response"
        assert acp_protocol.is_response(msg) is True
        assert acp_protocol.is_request(msg) is False
        assert acp_protocol.is_notification(msg) is False

    def test_response_has_id_and_error(self):
        msg = {"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "fail"}}
        assert acp_protocol.classify_frame(msg) == "response"
        assert acp_protocol.is_response(msg) is True

    def test_invalid_no_method_no_result(self):
        msg = {"jsonrpc": "2.0", "id": 1}
        assert acp_protocol.classify_frame(msg) == "invalid"

    def test_invalid_non_dict(self):
        assert acp_protocol.classify_frame("not a dict") == "invalid"
        assert acp_protocol.classify_frame(123) == "invalid"
        assert acp_protocol.classify_frame(None) == "invalid"


class TestParseFrame:
    """Test line-to-messages parsing."""

    def test_blank_line_returns_empty(self):
        assert acp_protocol.parse_frame(b"") == []
        assert acp_protocol.parse_frame(b"   ") == []
        assert acp_protocol.parse_frame(b"\n") == []

    def test_single_object_returns_list(self):
        line = b'{"jsonrpc":"2.0","method":"test"}\n'
        result = acp_protocol.parse_frame(line)
        assert len(result) == 1
        assert result[0]["method"] == "test"

    def test_batch_array_returns_all_dicts(self):
        line = b'[{"id":1,"result":{}},{"method":"notify"}]\n'
        result = acp_protocol.parse_frame(line)
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["method"] == "notify"

    def test_batch_with_non_dicts_filters_them(self):
        line = b'[{"id":1},123,"string",{"id":2}]\n'
        result = acp_protocol.parse_frame(line)
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    def test_invalid_json_returns_empty(self):
        line = b'not valid json\n'
        result = acp_protocol.parse_frame(line)
        assert result == []

    def test_non_utf8_returns_empty(self):
        line = b'\x80\x81\x82\n'
        result = acp_protocol.parse_frame(line)
        assert result == []


class TestToolCallState:
    """Test tool call state management."""

    def test_from_tool_call_extracts_fields(self):
        data = {
            "toolCallId": "tc-1",
            "title": "Run command",
            "status": "pending",
            "kind": "execute",
            "rawInput": {"cmd": "ls"},
        }
        tc = acp_protocol.ToolCallState.from_tool_call(data)
        assert tc.tool_call_id == "tc-1"
        assert tc.title == "Run command"
        assert tc.status == "pending"
        assert tc.kind == "execute"
        assert tc.raw_input == {"cmd": "ls"}

    def test_merge_update_does_not_clobber_with_none(self):
        tc = acp_protocol.ToolCallState(
            tool_call_id="tc-1",
            title="Original",
            status="pending",
        )
        tc.merge_update({"title": None, "status": "completed"})
        assert tc.title == "Original"  # Not clobbered
        assert tc.status == "completed"  # Updated

    def test_merge_update_updates_non_none_fields(self):
        tc = acp_protocol.ToolCallState(tool_call_id="tc-1")
        tc.merge_update({
            "title": "New Title",
            "kind": "read",
            "rawOutput": {"result": "ok"},
        })
        assert tc.title == "New Title"
        assert tc.kind == "read"
        assert tc.raw_output == {"result": "ok"}


class TestTurnState:
    """Test per-turn aggregation state."""

    def test_get_or_create_tool_call_creates_placeholder(self):
        turn = acp_protocol.TurnState(turn_id=1)
        tc = turn.get_or_create_tool_call("tc-1")
        assert tc.tool_call_id == "tc-1"
        assert "tc-1" in turn.tool_calls

    def test_record_tool_call_sets_saw_flag_and_clears_pre(self):
        turn = acp_protocol.TurnState(turn_id=1)
        turn.pre_tool_blocks.append({"type": "text", "text": "before"})

        tc = turn.record_tool_call({"toolCallId": "tc-1", "title": "Test"})

        assert turn.saw_any_tool_call is True
        assert turn.pre_tool_blocks == []
        assert tc.title == "Test"

    def test_record_tool_call_update_before_tool_call(self):
        """Update arriving before tool_call should not crash."""
        turn = acp_protocol.TurnState(turn_id=1)
        turn.pre_tool_blocks.append({"type": "text", "text": "before"})

        tc = turn.record_tool_call_update({"toolCallId": "tc-1", "status": "in_progress"})

        assert turn.saw_any_tool_call is True
        assert turn.pre_tool_blocks == []
        assert tc.status == "in_progress"

    def test_add_content_block_routes_to_correct_list(self):
        turn = acp_protocol.TurnState(turn_id=1)

        turn.add_content_block({"type": "text", "text": "pre"})
        assert len(turn.pre_tool_blocks) == 1
        assert len(turn.post_tool_blocks) == 0

        turn.saw_any_tool_call = True
        turn.add_content_block({"type": "text", "text": "post"})
        assert len(turn.pre_tool_blocks) == 1
        assert len(turn.post_tool_blocks) == 1

    def test_get_final_blocks_returns_post_if_tool_seen(self):
        turn = acp_protocol.TurnState(turn_id=1)
        turn.pre_tool_blocks.append({"type": "text", "text": "pre"})
        turn.saw_any_tool_call = True
        turn.post_tool_blocks.append({"type": "text", "text": "post"})

        final = turn.get_final_blocks()
        assert len(final) == 1
        assert final[0]["text"] == "post"

    def test_get_final_blocks_returns_pre_if_no_tool(self):
        turn = acp_protocol.TurnState(turn_id=1)
        turn.pre_tool_blocks.append({"type": "text", "text": "pre"})

        final = turn.get_final_blocks()
        assert len(final) == 1
        assert final[0]["text"] == "pre"


class TestSegmentKindClassification:
    """Test metadata-based content classification."""

    def test_segment_kind_from_annotations_dict(self):
        ann = {"type": "segment", "kind": "thinking"}
        assert acp_protocol.segment_kind_from_annotations(ann) == "thinking"

    def test_segment_kind_from_annotations_list(self):
        ann = [{"type": "other"}, {"kind": "thought"}]
        assert acp_protocol.segment_kind_from_annotations(ann) == "thought"

    def test_segment_kind_from_annotations_none(self):
        assert acp_protocol.segment_kind_from_annotations(None) is None
        assert acp_protocol.segment_kind_from_annotations([]) is None

    def test_is_thinking_content_with_update_hint(self):
        update = {"segment": "thinking"}
        assert acp_protocol.is_thinking_content(update) is True

    def test_is_thinking_content_with_block_annotations(self):
        update = {}
        block = {"annotations": {"kind": "thought"}}
        assert acp_protocol.is_thinking_content(update, block) is True

    def test_is_thinking_content_false_for_normal_content(self):
        update = {}
        block = {"type": "text", "text": "Hello"}
        assert acp_protocol.is_thinking_content(update, block) is False
