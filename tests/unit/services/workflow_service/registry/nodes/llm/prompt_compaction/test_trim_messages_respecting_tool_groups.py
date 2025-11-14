"""
Unit tests for MessageClassifier.trim_messages_respecting_tool_groups (v2.6).

Tests verify that keep_count is NEVER exceeded, even when tool groups are present.
v2.6 fix: Function now excludes tool groups that would cause exceeding keep_count.

Author: AI Assistant
Date: 2025-11-14
"""

import pytest
from typing import List
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
    SystemMessage,
)

from workflow_service.registry.nodes.llm.prompt_compaction.context_manager import (
    MessageClassifier,
)


class TestTrimMessagesRespectingToolGroups:
    """Test suite for trim_messages_respecting_tool_groups with v2.6 behavior."""

    # ==================== Fixtures ====================

    @pytest.fixture
    def simple_messages(self) -> List[BaseMessage]:
        """
        Simple message list without tool calls.
        
        Returns:
            List of 5 simple messages [H0, AI0, H1, AI1, H2]
        """
        return [
            HumanMessage(content="Human 0"),
            AIMessage(content="AI 0"),
            HumanMessage(content="Human 1"),
            AIMessage(content="AI 1"),
            HumanMessage(content="Human 2"),
        ]

    @pytest.fixture
    def messages_with_tool_group_at_end(self) -> List[BaseMessage]:
        """
        Messages with tool call group at the end.
        
        Structure:
            [M0, M1, M2, TC_AI, TC_Tool1, TC_Tool2, M6, M7]
            Tool group: indices 3-5 (TC_AI with 2 tool calls + 2 tool responses)
        
        Returns:
            List of 8 messages with tool group at indices 3-5
        """
        return [
            HumanMessage(content="Message 0"),
            AIMessage(content="Message 1"),
            HumanMessage(content="Message 2"),
            # Tool group starts here (indices 3-5)
            AIMessage(
                content="Using tools",
                tool_calls=[
                    {"id": "tc1", "name": "tool1", "args": {}},
                    {"id": "tc2", "name": "tool2", "args": {}},
                ],
            ),
            ToolMessage(content="Tool 1 result", tool_call_id="tc1"),
            ToolMessage(content="Tool 2 result", tool_call_id="tc2"),
            # Tool group ends here
            HumanMessage(content="Message 6"),
            AIMessage(content="Message 7"),
        ]

    @pytest.fixture
    def messages_with_tool_group_at_start(self) -> List[BaseMessage]:
        """
        Messages with tool call group at the start.
        
        Structure:
            [TC_AI, TC_Tool1, TC_Tool2, M3, M4, M5, M6, M7]
            Tool group: indices 0-2 (TC_AI with 2 tool calls + 2 tool responses)
        
        Returns:
            List of 8 messages with tool group at indices 0-2
        """
        return [
            # Tool group starts here (indices 0-2)
            AIMessage(
                content="Using tools",
                tool_calls=[
                    {"id": "tc1", "name": "tool1", "args": {}},
                    {"id": "tc2", "name": "tool2", "args": {}},
                ],
            ),
            ToolMessage(content="Tool 1 result", tool_call_id="tc1"),
            ToolMessage(content="Tool 2 result", tool_call_id="tc2"),
            # Tool group ends here
            HumanMessage(content="Message 3"),
            AIMessage(content="Message 4"),
            HumanMessage(content="Message 5"),
            AIMessage(content="Message 6"),
            HumanMessage(content="Message 7"),
        ]

    @pytest.fixture
    def messages_with_multiple_tool_groups(self) -> List[BaseMessage]:
        """
        Messages with multiple tool call groups.
        
        Structure:
            [M0, TC1_AI, TC1_Tool, M3, TC2_AI, TC2_Tool, M6, M7, M8, M9]
            Tool group 1: indices 1-2
            Tool group 2: indices 4-5
        
        Returns:
            List of 10 messages with tool groups at indices 1-2 and 4-5
        """
        return [
            HumanMessage(content="Message 0"),
            # Tool group 1 (indices 1-2)
            AIMessage(
                content="Tool call 1",
                tool_calls=[{"id": "tc1", "name": "tool1", "args": {}}],
            ),
            ToolMessage(content="Tool 1 result", tool_call_id="tc1"),
            HumanMessage(content="Message 3"),
            # Tool group 2 (indices 4-5)
            AIMessage(
                content="Tool call 2",
                tool_calls=[{"id": "tc2", "name": "tool2", "args": {}}],
            ),
            ToolMessage(content="Tool 2 result", tool_call_id="tc2"),
            HumanMessage(content="Message 6"),
            AIMessage(content="Message 7"),
            HumanMessage(content="Message 8"),
            AIMessage(content="Message 9"),
        ]

    # ==================== Test Cases: from_end=True ====================

    def test_from_end_no_tool_groups(self, simple_messages):
        """
        Test trim from end with no tool groups (baseline).
        
        Scenario:
            - Messages: [H0, AI0, H1, AI1, H2] (5 messages)
            - keep_count: 3
            - Expected: Keep last 3 messages [H1, AI1, H2]
        """
        kept, overflow = MessageClassifier.trim_messages_respecting_tool_groups(
            messages=simple_messages,
            keep_count=3,
            from_end=True,
        )

        # Verify keep_count is respected
        assert len(kept) == 3, f"Expected 3 messages, got {len(kept)}"
        assert len(overflow) == 2, f"Expected 2 overflow, got {len(overflow)}"

        # Verify correct messages kept
        assert kept[0].content == "Human 1"
        assert kept[1].content == "AI 1"
        assert kept[2].content == "Human 2"

    def test_from_end_trim_point_hits_tool_group(self, messages_with_tool_group_at_end):
        """
        Test v2.6 behavior: keep_count NEVER exceeded (exclude tool group).
        
        Scenario:
            - Messages: [M0, M1, M2, TC_AI, TC_Tool1, TC_Tool2, M6, M7] (8 messages)
            - Tool group: indices 3-6 (MAX SPAN includes trailing HumanMessage M6)
            - keep_count: 3
            - Naive trim_point: 8 - 3 = 5 (would start at index 5, splitting tool group)
            
        OLD v2.5 behavior (BUG):
            - Moved trim_point to group_start (3) → kept [3, 4, 5, 6, 7] = 5 messages ❌ EXCEEDS
            
        NEW v2.6 behavior (FIXED):
            - Move trim_point to group_end + 1 (7) → keeps [7] = 1 message ✓ RESPECTS
        """
        kept, overflow = MessageClassifier.trim_messages_respecting_tool_groups(
            messages=messages_with_tool_group_at_end,
            keep_count=3,
            from_end=True,
        )

        # CRITICAL: Verify keep_count is never exceeded
        assert len(kept) <= 3, f"keep_count EXCEEDED: {len(kept)} > 3"
        
        # Verify correct behavior: tool group excluded (MAX SPAN includes M6, so only M7 kept)
        assert len(kept) == 1, f"Expected 1 message (tool group with MAX SPAN excluded), got {len(kept)}"
        assert len(overflow) == 7, f"Expected 7 overflow (including tool group), got {len(overflow)}"

        # Verify correct messages kept (after tool group)
        assert kept[0].content == "Message 7"

        # Verify tool group in overflow
        assert overflow[3].content == "Using tools"
        assert isinstance(overflow[3], AIMessage)
        assert len(overflow[3].tool_calls) == 2

    def test_from_end_keep_count_larger_than_tool_group(self, messages_with_tool_group_at_end):
        """
        Test when keep_count is large enough to include tool group safely.
        
        Scenario:
            - Messages: [M0, M1, M2, TC_AI, TC_Tool1, TC_Tool2, M6, M7] (8 messages)
            - Tool group: indices 3-5
            - keep_count: 6
            - Naive trim_point: 8 - 6 = 2 (would start at index 2, no conflict)
            
        Expected: Keep last 6 messages including tool group [M2, TC_AI, TC_Tool1, TC_Tool2, M6, M7]
        """
        kept, overflow = MessageClassifier.trim_messages_respecting_tool_groups(
            messages=messages_with_tool_group_at_end,
            keep_count=6,
            from_end=True,
        )

        # Verify keep_count is respected
        assert len(kept) == 6, f"Expected 6 messages, got {len(kept)}"
        assert len(overflow) == 2, f"Expected 2 overflow, got {len(overflow)}"

        # Verify tool group is included and intact
        assert kept[1].content == "Using tools"
        assert isinstance(kept[1], AIMessage)
        assert len(kept[1].tool_calls) == 2
        assert isinstance(kept[2], ToolMessage)
        assert isinstance(kept[3], ToolMessage)

    def test_from_end_multiple_tool_groups(self, messages_with_multiple_tool_groups):
        """
        Test trimming with multiple tool groups.
        
        Scenario:
            - Messages: [M0, TC1_AI, TC1_Tool, M3, TC2_AI, TC2_Tool, M6, M7, M8, M9] (10 messages)
            - Tool group 1: indices 1-3 (MAX SPAN includes M3)
            - Tool group 2: indices 4-6 (MAX SPAN includes M6)
            - keep_count: 4
            - Naive trim_point: 10 - 4 = 6 (would start at index 6, splits tool group 2)
            
        Expected: Keep last 3 messages [M7, M8, M9] (tool group 2 excluded to respect keep_count)
        """
        kept, overflow = MessageClassifier.trim_messages_respecting_tool_groups(
            messages=messages_with_multiple_tool_groups,
            keep_count=4,
            from_end=True,
        )

        # Verify keep_count is never exceeded
        assert len(kept) <= 4, f"keep_count EXCEEDED: {len(kept)} > 4"
        
        # Verify correct behavior: tool group 2 excluded (MAX SPAN includes M6)
        assert len(kept) == 3, f"Expected 3 messages (tool group 2 excluded), got {len(kept)}"
        assert len(overflow) == 7, f"Expected 7 overflow (including tool group 2), got {len(overflow)}"

        # Verify correct messages kept (after tool group 2)
        assert kept[0].content == "Message 7"
        assert kept[1].content == "Message 8"
        assert kept[2].content == "Message 9"

    # ==================== Test Cases: from_end=False ====================

    def test_from_start_no_tool_groups(self, simple_messages):
        """
        Test trim from start with no tool groups (baseline).
        
        Scenario:
            - Messages: [H0, AI0, H1, AI1, H2] (5 messages)
            - keep_count: 3
            - Expected: Keep first 3 messages [H0, AI0, H1]
        """
        kept, overflow = MessageClassifier.trim_messages_respecting_tool_groups(
            messages=simple_messages,
            keep_count=3,
            from_end=False,
        )

        # Verify keep_count is respected
        assert len(kept) == 3, f"Expected 3 messages, got {len(kept)}"
        assert len(overflow) == 2, f"Expected 2 overflow, got {len(overflow)}"

        # Verify correct messages kept
        assert kept[0].content == "Human 0"
        assert kept[1].content == "AI 0"
        assert kept[2].content == "Human 1"

    def test_from_start_trim_point_hits_tool_group(self, messages_with_tool_group_at_start):
        """
        Test v2.6 behavior: keep_count NEVER exceeded (exclude tool group).
        
        Scenario:
            - Messages: [TC_AI, TC_Tool1, TC_Tool2, M3, M4, M5, M6, M7] (8 messages)
            - Tool group: indices 0-2
            - keep_count: 4
            - Naive trim_point: 4 (would keep [0, 1, 2, 3], includes incomplete tool group)
            - Last message index: trim_point - 1 = 3 (not in tool group, but let's test index 2)
            
        Let's test with keep_count=2, which would hit the tool group:
            - trim_point: 2 (would keep [0, 1], last message at index 1 is in tool group)
            
        OLD v2.5 behavior (BUG):
            - Moved trim_point to group_end + 1 (3) → kept [0, 1, 2] = 3 messages ❌ EXCEEDS
            
        NEW v2.6 behavior (FIXED):
            - Move trim_point to group_start (0) → keeps [] = 0 messages ✓ RESPECTS
        """
        kept, overflow = MessageClassifier.trim_messages_respecting_tool_groups(
            messages=messages_with_tool_group_at_start,
            keep_count=2,
            from_end=False,
        )

        # CRITICAL: Verify keep_count is never exceeded
        assert len(kept) <= 2, f"keep_count EXCEEDED: {len(kept)} > 2"
        
        # Verify correct behavior: tool group excluded
        assert len(kept) == 0, f"Expected 0 messages (tool group excluded), got {len(kept)}"
        assert len(overflow) == 8, f"Expected 8 overflow (all messages), got {len(overflow)}"

    def test_from_start_keep_count_larger_than_tool_group(self, messages_with_tool_group_at_start):
        """
        Test when keep_count is large enough to include tool group safely.
        
        Scenario:
            - Messages: [TC_AI, TC_Tool1, TC_Tool2, M3, M4, M5, M6, M7] (8 messages)
            - Tool group: indices 0-2
            - keep_count: 5
            - Naive trim_point: 5 (would keep [0, 1, 2, 3, 4], last at index 4, not in tool group)
            
        Expected: Keep first 5 messages including tool group [TC_AI, TC_Tool1, TC_Tool2, M3, M4]
        """
        kept, overflow = MessageClassifier.trim_messages_respecting_tool_groups(
            messages=messages_with_tool_group_at_start,
            keep_count=5,
            from_end=False,
        )

        # Verify keep_count is respected
        assert len(kept) == 5, f"Expected 5 messages, got {len(kept)}"
        assert len(overflow) == 3, f"Expected 3 overflow, got {len(overflow)}"

        # Verify tool group is included and intact
        assert kept[0].content == "Using tools"
        assert isinstance(kept[0], AIMessage)
        assert len(kept[0].tool_calls) == 2
        assert isinstance(kept[1], ToolMessage)
        assert isinstance(kept[2], ToolMessage)

    # ==================== Edge Cases ====================

    def test_keep_count_zero(self, simple_messages):
        """Test with keep_count=0 (should return empty list)."""
        kept, overflow = MessageClassifier.trim_messages_respecting_tool_groups(
            messages=simple_messages,
            keep_count=0,
            from_end=True,
        )

        assert len(kept) == 0, f"Expected 0 messages, got {len(kept)}"
        assert len(overflow) == len(simple_messages), "All messages should be overflow"

    def test_keep_count_exceeds_message_count(self, simple_messages):
        """Test with keep_count > len(messages) (should return all messages)."""
        kept, overflow = MessageClassifier.trim_messages_respecting_tool_groups(
            messages=simple_messages,
            keep_count=100,
            from_end=True,
        )

        assert len(kept) == len(simple_messages), "All messages should be kept"
        assert len(overflow) == 0, "No messages should overflow"

    def test_keep_count_equals_message_count(self, simple_messages):
        """Test with keep_count == len(messages) (should return all messages)."""
        kept, overflow = MessageClassifier.trim_messages_respecting_tool_groups(
            messages=simple_messages,
            keep_count=len(simple_messages),
            from_end=True,
        )

        assert len(kept) == len(simple_messages), "All messages should be kept"
        assert len(overflow) == 0, "No messages should overflow"

    def test_empty_message_list(self):
        """Test with empty message list."""
        kept, overflow = MessageClassifier.trim_messages_respecting_tool_groups(
            messages=[],
            keep_count=5,
            from_end=True,
        )

        assert len(kept) == 0, "Should return empty list"
        assert len(overflow) == 0, "Should return empty list"

    # ==================== Pre-computed Boundaries ====================

    def test_with_precomputed_boundaries(self, messages_with_tool_group_at_end):
        """
        Test that pre-computed boundaries work correctly (v2.5 feature).
        
        Scenario:
            - Messages: [M0, M1, M2, TC_AI, TC_Tool1, TC_Tool2, M6, M7] (8 messages)
            - Tool group: indices 3-5 (INCLUSIVE end)
            - keep_count: 3
            - Pre-computed boundaries: [(3, 5)]  # INCLUSIVE end indices
            
        Expected: Same result as without pre-computed boundaries
        """
        # Pre-compute boundaries (INCLUSIVE end indices as per docstring)
        pre_computed_boundaries = [(3, 5)]  # Tool group at indices 3-5 (inclusive)

        kept, overflow = MessageClassifier.trim_messages_respecting_tool_groups(
            messages=messages_with_tool_group_at_end,
            keep_count=3,
            from_end=True,
            pre_computed_boundaries=pre_computed_boundaries,
        )

        # CRITICAL: Verify keep_count is never exceeded
        assert len(kept) <= 3, f"keep_count EXCEEDED: {len(kept)} > 3"
        
        # Verify correct behavior: tool group excluded
        assert len(kept) == 2, f"Expected 2 messages (tool group excluded), got {len(kept)}"
        assert len(overflow) == 6, f"Expected 6 overflow (including tool group), got {len(overflow)}"

        # Verify correct messages kept (after tool group)
        assert kept[0].content == "Message 6"
        assert kept[1].content == "Message 7"

    # ==================== Verification Tests ====================

    def test_never_exceeds_keep_count_comprehensive(self, messages_with_multiple_tool_groups):
        """
        Comprehensive test to verify keep_count is NEVER exceeded for various values.
        
        Tests all keep_count values from 1 to len(messages) to ensure the guarantee holds.
        """
        messages = messages_with_multiple_tool_groups
        
        for keep_count in range(1, len(messages) + 1):
            # Test from_end=True
            kept_end, _ = MessageClassifier.trim_messages_respecting_tool_groups(
                messages=messages,
                keep_count=keep_count,
                from_end=True,
            )
            assert len(kept_end) <= keep_count, (
                f"from_end=True: keep_count EXCEEDED for keep_count={keep_count}: "
                f"{len(kept_end)} > {keep_count}"
            )

            # Test from_end=False
            kept_start, _ = MessageClassifier.trim_messages_respecting_tool_groups(
                messages=messages,
                keep_count=keep_count,
                from_end=False,
            )
            assert len(kept_start) <= keep_count, (
                f"from_end=False: keep_count EXCEEDED for keep_count={keep_count}: "
                f"{len(kept_start)} > {keep_count}"
            )

    def test_tool_groups_never_split(self, messages_with_tool_group_at_end):
        """
        Verify that tool groups are never split (atomic guarantee).
        
        A tool group is split if:
        - AI message with tool_calls is kept but corresponding ToolMessages are in overflow
        - ToolMessages are kept but corresponding AI message is in overflow
        """
        messages = messages_with_tool_group_at_end
        
        for keep_count in range(1, len(messages) + 1):
            kept, overflow = MessageClassifier.trim_messages_respecting_tool_groups(
                messages=messages,
                keep_count=keep_count,
                from_end=True,
            )

            # Check that no AI message with tool_calls is split from its responses
            for msg in kept:
                if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                    # All tool_call_ids should have corresponding ToolMessages in kept
                    tool_call_ids = {tc["id"] for tc in msg.tool_calls}
                    found_tool_responses = {
                        tm.tool_call_id for tm in kept if isinstance(tm, ToolMessage)
                    }
                    assert tool_call_ids.issubset(found_tool_responses), (
                        f"Tool group SPLIT: AI message has tool calls {tool_call_ids} "
                        f"but only found responses {found_tool_responses}"
                    )

            # Check overflow doesn't have orphaned ToolMessages
            for msg in overflow:
                if isinstance(msg, ToolMessage):
                    # There should be a corresponding AI message with this tool_call_id in overflow
                    ai_with_tool_call = any(
                        isinstance(m, AIMessage)
                        and hasattr(m, "tool_calls")
                        and m.tool_calls
                        and any(tc["id"] == msg.tool_call_id for tc in m.tool_calls)
                        for m in overflow
                    )
                    assert ai_with_tool_call, (
                        f"Orphaned ToolMessage in overflow: {msg.tool_call_id}"
                    )

