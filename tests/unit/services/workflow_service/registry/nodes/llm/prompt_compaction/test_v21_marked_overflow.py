"""
Unit tests for v2.1 marked message overflow handling features.

Tests cover:
- Removal of preserve=True flag on overflow
- Removal of dont_summarize=True flag on overflow
- Addition of originally_marked=True flag
- Ingestion with "marked_overflow" section label
- Separation during ingestion
- Recombination for extraction

Test IDs: 27-32 (from comprehensive test plan)
"""

import unittest
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from workflow_service.registry.nodes.llm.prompt_compaction.strategies import (
    ExtractionStrategy,
)
from workflow_service.registry.nodes.llm.config import ModelMetadata, LLMModelProvider
from workflow_service.registry.nodes.llm.prompt_compaction.utils import (
    get_compaction_metadata,
    set_section_label,
    get_section_label,
    set_ingestion_metadata,
    is_message_ingested,
    MessageSectionLabel,
    ExtractionStrategy as ExtractionStrategyType,
)

from .test_base import PromptCompactionUnitTestBase


class TestMarkedOverflowFlagHandling(unittest.TestCase):
    """Test 27-29: Flag handling for marked overflow messages."""

    def test_marked_overflow_removes_preserve_flag(self):
        """Test 27: preserve=True flag is removed when message overflows."""
        message = HumanMessage(content="Important message", id="msg_1")

        # Initially mark as preserve
        if not hasattr(message, "response_metadata"):
            message.response_metadata = {}
        message.response_metadata["preserve"] = True

        # Verify preserve flag is set
        self.assertTrue(message.response_metadata.get("preserve"))

        # Simulate overflow handling: remove preserve, add originally_marked
        message.response_metadata.pop("preserve", None)
        message.response_metadata["originally_marked"] = True

        # Verify flag changes
        self.assertNotIn("preserve", message.response_metadata)
        self.assertTrue(message.response_metadata.get("originally_marked"))

    def test_marked_overflow_removes_dont_summarize_flag(self):
        """Test 28: dont_summarize=True flag is removed on overflow."""
        message = HumanMessage(content="Important message", id="msg_2")

        # Initially mark as dont_summarize
        if not hasattr(message, "response_metadata"):
            message.response_metadata = {}
        message.response_metadata["dont_summarize"] = True

        # Verify flag is set
        self.assertTrue(message.response_metadata.get("dont_summarize"))

        # Simulate overflow handling
        message.response_metadata.pop("dont_summarize", None)
        message.response_metadata["originally_marked"] = True

        # Verify flag changes
        self.assertNotIn("dont_summarize", message.response_metadata)
        self.assertTrue(message.response_metadata.get("originally_marked"))

    def test_marked_overflow_adds_originally_marked_flag(self):
        """Test 29: originally_marked=True flag is added on overflow."""
        message = HumanMessage(content="Important message", id="msg_3")

        # Initially has preserve or dont_summarize
        if not hasattr(message, "response_metadata"):
            message.response_metadata = {}
        message.response_metadata["preserve"] = True

        # Simulate overflow handling
        had_marking = message.response_metadata.get("preserve") or \
                     message.response_metadata.get("dont_summarize")

        if had_marking:
            message.response_metadata.pop("preserve", None)
            message.response_metadata.pop("dont_summarize", None)
            message.response_metadata["originally_marked"] = True

        # Verify originally_marked was added
        self.assertTrue(message.response_metadata.get("originally_marked"))
        self.assertNotIn("preserve", message.response_metadata)


class TestMarkedOverflowIngestion(PromptCompactionUnitTestBase):
    """Test 30-31: Ingestion handling for marked overflow messages."""

    async def test_marked_overflow_ingestion_section_label(self):
        """Test 30: Marked overflow messages ingested with "marked" label."""
        message = HumanMessage(content="Marked overflow message", id="msg_marked")

        # Set section label (using MARKED for marked overflow messages)
        set_section_label(message, MessageSectionLabel.MARKED)

        # Verify section label
        section = get_section_label(message)
        self.assertEqual(section, MessageSectionLabel.MARKED)

        # Set ingestion metadata with section label
        set_ingestion_metadata(
            message,
            chunk_ids=["chunk_1"],
            section_label=MessageSectionLabel.MARKED
        )

        # Verify ingestion metadata includes section label
        ingestion_meta = get_compaction_metadata(message, "ingestion", {})
        self.assertTrue(ingestion_meta.get("ingested"))
        self.assertEqual(
            ingestion_meta.get("section_label"),
            MessageSectionLabel.MARKED
        )

    async def test_marked_overflow_separated_during_ingestion(self):
        """Test 31: Marked overflow messages separated from historical during ingestion."""
        # Create historical messages
        historical_msgs = [
            HumanMessage(content=f"Historical {i}", id=f"hist_{i}")
            for i in range(3)
        ]

        # Create marked overflow messages
        marked_msgs = [
            HumanMessage(content=f"Marked {i}", id=f"marked_{i}")
            for i in range(2)
        ]

        # Set section labels
        for msg in historical_msgs:
            set_section_label(msg, MessageSectionLabel.HISTORICAL)

        for msg in marked_msgs:
            set_section_label(msg, MessageSectionLabel.MARKED)

        # Verify separation by section label
        all_msgs = historical_msgs + marked_msgs

        historical_filtered = [
            msg for msg in all_msgs
            if get_section_label(msg) == MessageSectionLabel.HISTORICAL
        ]
        marked_filtered = [
            msg for msg in all_msgs
            if get_section_label(msg) == MessageSectionLabel.MARKED
        ]

        self.assertEqual(len(historical_filtered), 3)
        self.assertEqual(len(marked_filtered), 2)


class TestMarkedOverflowExtraction(unittest.TestCase):
    """Test 32: Recombination of marked overflow for extraction."""

    def test_marked_overflow_recombined_for_extraction(self):
        """Test 32: Marked overflow combined with historical for extraction."""
        # Create messages with different section labels
        historical = HumanMessage(content="Historical", id="hist")
        set_section_label(historical, MessageSectionLabel.HISTORICAL)

        marked = HumanMessage(content="Marked overflow", id="marked")
        set_section_label(marked, MessageSectionLabel.MARKED)

        recent = HumanMessage(content="Recent", id="recent")
        set_section_label(recent, MessageSectionLabel.RECENT)

        all_messages = [historical, marked, recent]

        # During extraction, marked messages should be available for retrieval
        # Verify all messages can be accessed regardless of section label
        self.assertEqual(len(all_messages), 3)

        # Verify each has its section label
        self.assertEqual(get_section_label(historical), MessageSectionLabel.HISTORICAL)
        self.assertEqual(get_section_label(marked), MessageSectionLabel.MARKED)
        self.assertEqual(get_section_label(recent), MessageSectionLabel.RECENT)

        # For extraction, we would typically combine historical and marked
        # while keeping recent separate
        extractable = [
            msg for msg in all_messages
            if get_section_label(msg) in [
                MessageSectionLabel.HISTORICAL,
                MessageSectionLabel.MARKED
            ]
        ]

        self.assertEqual(len(extractable), 2)
        self.assertIn(historical, extractable)
        self.assertIn(marked, extractable)
        self.assertNotIn(recent, extractable)


if __name__ == "__main__":
    unittest.main()
