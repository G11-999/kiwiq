"""
Unit tests for v2.1 metadata propagation features.

Tests that compaction strategies properly add metadata (section labels, graph edges) 
to messages in the compacted output.

NOTE: The v2.1 metadata snapshotting and messages_with_updated_metadata tracking
has been removed. Metadata is now only applied to the final compacted messages,
not to full_history messages.
"""

import pytest
from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
)

from workflow_service.registry.nodes.llm.prompt_compaction.strategies import (
    NoOpStrategy,
    SummarizationStrategy,
    ExtractionStrategy,
    HybridStrategy,
    CompactionResult,
)
from workflow_service.registry.nodes.llm.prompt_compaction.compactor import (
    PromptCompactionConfig,
    SummarizationConfig,
    ExtractionConfig as ExtractionCompactionConfig,
    HybridConfig,
)
from workflow_service.registry.nodes.llm.prompt_compaction.utils import (
    set_compaction_metadata,
    get_compaction_metadata,
)

from .test_base import PromptCompactionUnitTestBase


# ============================================================================
# Test Strategy Integration: Metadata Application
# ============================================================================


class TestNoOpStrategyMetadataPropagation(PromptCompactionUnitTestBase):
    """Test NoOpStrategy adds metadata to compacted messages."""

    async def test_noop_all_messages_get_metadata(self):
        """Test NoOp strategy adds section labels and graph edges to all messages."""
        strategy = NoOpStrategy()

        sections = {
            "system": [],
            "summaries": [],
            "historical": [],
            "marked": [],
            "recent": self._generate_test_messages(2),
        }

        result = await strategy.compact(
            sections=sections,
            budget=self._create_test_budget(),
            model_metadata=self._create_test_model_metadata(),
            ext_context=self.ext_context,
        )

        # All messages should have section labels
        for msg in result.compacted_messages:
            assert get_compaction_metadata(msg, "section_label") is not None


class TestSummarizationStrategyMetadataPropagation(PromptCompactionUnitTestBase):
    """Test SummarizationStrategy adds metadata to compacted messages."""

    async def test_summarization_messages_get_metadata(self):
        """Test summarization strategy adds section labels to messages."""
        strategy = SummarizationStrategy()

        sections = {
            "system": [],
            "summaries": [],
            "historical": [],
            "marked": [],
            "recent": self._generate_test_messages(2),
        }

        result = await strategy.compact(
            sections=sections,
            budget=self._create_test_budget(),
            model_metadata=self._create_test_model_metadata(),
            ext_context=self.ext_context,
        )

        # All messages should have section labels
        for msg in result.compacted_messages:
            assert get_compaction_metadata(msg, "section_label") is not None


class TestExtractionStrategyMetadataPropagation(PromptCompactionUnitTestBase):
    """Test ExtractionStrategy adds metadata to compacted messages."""

    async def test_extraction_messages_get_metadata(self):
        """Test extraction strategy adds section labels to messages."""
        from workflow_service.registry.nodes.llm.prompt_compaction.utils import ExtractionStrategy as ExtractionStrategyType

        strategy = ExtractionStrategy(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            store_embeddings=False,
        )

        sections = {
            "system": [],
            "summaries": [],
            "historical": [],
            "marked": [],
            "recent": self._generate_test_messages(2),
        }

        result = await strategy.compact(
            sections=sections,
            budget=self._create_test_budget(),
            model_metadata=self._create_test_model_metadata(),
            ext_context=self.ext_context,
        )

        # All messages should have section labels
        for msg in result.compacted_messages:
            assert get_compaction_metadata(msg, "section_label") is not None
        
        # v3.1: Verify extraction metadata on extracted messages
        if result.extracted_messages:
            for msg in result.extracted_messages:
                # Check new v3.1 metadata fields
                assert get_compaction_metadata(msg, "extraction_performed") == True
                assert get_compaction_metadata(msg, "embedding_model") is not None
                assert get_compaction_metadata(msg, "construction_strategy") is not None


class TestHybridStrategyMetadataPropagation(PromptCompactionUnitTestBase):
    """Test HybridStrategy adds metadata to compacted messages."""

    async def test_hybrid_messages_get_metadata(self):
        """Test hybrid strategy adds section labels to messages."""
        strategy = HybridStrategy()

        sections = {
            "system": [],
            "summaries": [],
            "historical": [],
            "marked": [],
            "recent": self._generate_test_messages(2),
        }

        result = await strategy.compact(
            sections=sections,
            budget=self._create_test_budget(),
            model_metadata=self._create_test_model_metadata(),
            ext_context=self.ext_context,
        )

        # All messages should have section labels
        for msg in result.compacted_messages:
            assert get_compaction_metadata(msg, "section_label") is not None
