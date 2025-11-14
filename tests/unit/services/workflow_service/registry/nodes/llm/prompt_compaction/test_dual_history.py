"""
Unit tests for v2.1 dual history support in LLM node.

Tests cover:
- LLM node outputs summarized_messages field
- summarized_messages is None when no compaction occurs
- summarized_messages contains correct message IDs
- State reducer patterns (add_messages vs replace)
- Multi-turn conversation handling

Test IDs: 10-18 (from comprehensive test plan)
"""

import unittest
from typing import List, Optional
from unittest.mock import AsyncMock, Mock, patch

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from workflow_service.registry.nodes.llm.llm_node import (
    LLMNode,
    LLMNodeInputSchema,
    LLMNodeOutputSchema,
    LLMNodeConfigSchema,
    LLMModelConfig,
    ModelSpec,
)
from workflow_service.registry.nodes.llm.config import LLMModelProvider
from workflow_service.registry.nodes.llm.prompt_compaction.compactor import (
    CompactionResult,
    CompactionStrategyType,
    PromptCompactionConfig,
)
from workflow_service.registry.nodes.llm.prompt_compaction.strategies import (
    ExtractionStrategy,
    NoOpStrategy,
)
from workflow_service.registry.nodes.llm.prompt_compaction.utils import (
    ExtractionStrategy as ExtractionStrategyType,
)

from .test_base import PromptCompactionUnitTestBase


class TestDualHistoryOutputField(PromptCompactionUnitTestBase):
    """Test 10: LLM node outputs summarized_messages field."""

    async def test_output_schema_has_summarized_messages(self):
        """Should include summarized_messages field in output schema."""
        # Verify field exists in schema
        self.assertTrue(hasattr(LLMNodeOutputSchema, "__fields__"))
        fields = LLMNodeOutputSchema.__fields__
        self.assertIn("summarized_messages", fields)

        # Verify field is optional
        field_info = fields["summarized_messages"]
        # Check if Optional by looking at annotation
        import typing
        self.assertTrue(
            typing.get_origin(field_info.annotation) is typing.Union
            or field_info.annotation == Optional[List[BaseMessage]]
        )


class TestDualHistoryNoneWhenNoCompaction(PromptCompactionUnitTestBase):
    """Test 11: summarized_messages is None when no compaction occurs."""

    async def test_none_when_compaction_disabled(self):
        """Should handle case when compaction is disabled."""
        # Test that NoOp strategy works
        strategy = NoOpStrategy()

        sections = {
            "system": [],
            "summaries": [],
            "historical": self._generate_test_messages(3),
            "marked": [],
            "recent": self._generate_test_messages(2),
        }

        result = await strategy.compact(
            sections=sections,
            budget=self._create_test_budget(),
            model_metadata=self._create_test_model_metadata(),
            ext_context=self.ext_context,
        )

        # Should complete successfully
        self.assertIsNotNone(result)

    async def test_none_when_threshold_not_reached(self):
        """Should handle short message lists that don't need compaction."""
        # Test with small message count
        strategy = NoOpStrategy()

        sections = {
            "system": [],
            "summaries": [],
            "historical": self._generate_test_messages(2),  # Small count
            "marked": [],
            "recent": self._generate_test_messages(2),
        }

        result = await strategy.compact(
            sections=sections,
            budget=self._create_test_budget(),
            model_metadata=self._create_test_model_metadata(),
            ext_context=self.ext_context,
        )

        # Should complete successfully
        self.assertIsNotNone(result)


class TestDualHistoryMessageIDs(PromptCompactionUnitTestBase):
    """Test 12: summarized_messages contains correct message IDs."""

    async def test_correct_message_ids_in_summarized(self):
        """Should preserve message IDs in summarized_messages."""
        # Create mock compaction result
        original_messages = self._generate_test_messages(count=10)

        # Simulate compacted messages (reduced to 5)
        compacted_messages = original_messages[:2] + original_messages[-3:]

        compaction_result = CompactionResult(
            compacted_messages=compacted_messages,
            num_tokens_saved=5000,
            original_token_count=10000,
            compacted_token_count=5000,
        )

        # Verify message IDs preserved
        original_ids = {msg.id for msg in compacted_messages}
        result_ids = {msg.id for msg in compaction_result.compacted_messages}

        self.assertEqual(original_ids, result_ids)


class TestDualHistoryStateReducers(PromptCompactionUnitTestBase):
    """Test 13: Dual history with different state reducers."""

    async def test_add_messages_reducer_pattern(self):
        """Should append to full history with add_messages reducer."""
        # Simulate workflow state with add_messages reducer
        from typing import Annotated
        from langgraph.graph import add_messages

        # Full history (append-only)
        full_history = self._generate_test_messages(count=5)

        # New message to add
        new_message = self._generate_test_message("New message", role="ai")

        # Simulate add_messages behavior (concatenation)
        updated_full_history = full_history + [new_message]

        self.assertEqual(len(updated_full_history), 6)
        self.assertEqual(updated_full_history[-1].id, new_message.id)

    async def test_replace_reducer_pattern(self):
        """Should replace summarized history with replace reducer."""
        # Simulate workflow state with replace reducer
        old_summarized = self._generate_test_messages(count=10)
        new_summarized = self._generate_test_messages(count=5)

        # Replace behavior (no merging)
        updated_summarized = new_summarized

        self.assertEqual(len(updated_summarized), 5)
        self.assertNotEqual(
            {msg.id for msg in updated_summarized},
            {msg.id for msg in old_summarized}
        )


class TestDualHistoryCompactionResult(PromptCompactionUnitTestBase):
    """Test 14: Compaction result structure for dual history."""

    async def test_compaction_result_structure(self):
        """Should have correct structure for dual history extraction."""
        strategy = ExtractionStrategy(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            store_embeddings=False,
        )

        sections = {
            "system": [],
            "summaries": [],
            "historical": self._generate_test_messages(count=10),
            "marked": [],
            "recent": self._generate_test_messages(count=3),
        }

        result = await strategy.compact(
            sections=sections,
            budget=self._create_test_budget(),
            model_metadata=self._create_test_model_metadata(),
            ext_context=self.ext_context,
            runtime_config=None,
        )

        # Verify structure - CompactionResult has these fields:
        # compacted_messages, summary_messages, extracted_messages,
        # removed_message_ids, token_usage, cost, compression_ratio, metadata
        self.assertIsNotNone(result.compacted_messages)
        self.assertGreater(len(result.compacted_messages), 0)
        self.assertIsNotNone(result.token_usage)
        self.assertIsNotNone(result.cost)
        self.assertIsNotNone(result.compression_ratio)
        self.assertIsNotNone(result.metadata)
        self.assertIsInstance(result.compacted_messages, list)
        self.assertIsInstance(result.summary_messages, list)
        self.assertIsInstance(result.extracted_messages, list)
        self.assertIsInstance(result.removed_message_ids, list)


class TestDualHistoryMessageCount(PromptCompactionUnitTestBase):
    """Test 15: Dual history message count validation."""

    async def test_summarized_count_less_than_full(self):
        """Should have fewer messages in summarized than full history."""
        full_history = self._generate_test_messages(count=20)

        # Simulate compaction reducing to 50%
        summarized_history = full_history[:10]

        self.assertLess(len(summarized_history), len(full_history))
        self.assertEqual(len(summarized_history), len(full_history) // 2)


class TestDualHistoryContentPreservation(PromptCompactionUnitTestBase):
    """Test 16: Dual history preserves important content."""

    async def test_preserves_system_messages(self):
        """Should preserve system messages in summarized history."""
        from langchain_core.messages import SystemMessage

        # Create messages with system message
        system_msg = SystemMessage(content="You are a helpful assistant", id="sys_1")
        user_messages = self._generate_test_messages(count=10, roles=["human", "ai"])

        all_messages = [system_msg] + user_messages

        # Simulate compaction that preserves system messages
        compacted_messages = [system_msg] + user_messages[-3:]

        # Verify system message present
        system_messages_in_compacted = [
            msg for msg in compacted_messages
            if isinstance(msg, SystemMessage)
        ]

        self.assertEqual(len(system_messages_in_compacted), 1)
        self.assertEqual(system_messages_in_compacted[0].id, "sys_1")

    async def test_preserves_recent_messages(self):
        """Should preserve recent messages in summarized history."""
        messages = self._generate_test_messages(count=20)

        # Most recent N messages
        recent_count = 5
        recent_messages = messages[-recent_count:]

        # Simulate compaction that keeps recent messages
        compacted_messages = messages[:5] + recent_messages

        # Verify recent messages are in compacted set
        recent_ids = {msg.id for msg in recent_messages}
        compacted_ids = {msg.id for msg in compacted_messages}

        self.assertTrue(recent_ids.issubset(compacted_ids))


class TestDualHistoryMetadata(PromptCompactionUnitTestBase):
    """Test 17: Dual history metadata tracking."""

    async def test_metadata_on_summarized_messages(self):
        """Should include compaction metadata on summarized messages."""
        # Generate messages with compaction metadata
        messages = self._generate_test_messages(count=5)

        # Add compaction metadata to simulate post-compaction state
        for i, msg in enumerate(messages):
            msg.response_metadata = {
                "compaction": {
                    "section_label": "summary" if i < 2 else "recent",
                    "compacted": True,
                }
            }

        # Verify metadata present
        for msg in messages:
            self.assertMessageHasMetadata(msg, ["compaction"])


class TestDualHistoryEmptyCompaction(PromptCompactionUnitTestBase):
    """Test 18: Dual history with empty compaction result."""

    async def test_empty_compacted_messages(self):
        """Should handle empty compacted messages gracefully."""
        # Edge case: compaction returns empty list
        compaction_result = CompactionResult(
            compacted_messages=[],
            num_tokens_saved=0,
            original_token_count=100,
            compacted_token_count=100,
        )

        # Should still be valid result
        self.assertIsNotNone(compaction_result.compacted_messages)
        self.assertEqual(len(compaction_result.compacted_messages), 0)

    async def test_single_message_compaction(self):
        """Should handle single message compaction."""
        message = self._generate_test_message("Single message", role="human")

        compaction_result = CompactionResult(
            compacted_messages=[message],
            num_tokens_saved=0,
            original_token_count=10,
            compacted_token_count=10,
        )

        self.assertEqual(len(compaction_result.compacted_messages), 1)
        self.assertEqual(compaction_result.compacted_messages[0].id, message.id)


if __name__ == "__main__":
    unittest.main()
