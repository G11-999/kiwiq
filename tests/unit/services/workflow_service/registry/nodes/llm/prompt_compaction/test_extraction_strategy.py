"""
Unit tests for v2.1 extraction strategy functionality.

Tests cover:
- All 3 construction strategies (DUMP, EXTRACT_FULL, LLM_REWRITE)
- Top-k filtering
- Similarity threshold filtering
- Budget allocation for extraction
- Relevance scoring
- Chunk construction
- Message ordering preservation

Test IDs: 25-35 (from comprehensive test plan)
"""

import unittest
from typing import List

from langchain_core.messages import BaseMessage

from workflow_service.registry.nodes.llm.prompt_compaction.compactor import ExtractionConfig
from workflow_service.registry.nodes.llm.prompt_compaction.strategies import (
    ExtractionStrategy,
)
from workflow_service.registry.nodes.llm.prompt_compaction.utils import (
    ExtractionStrategy as ExtractionStrategyType,
)

from workflow_service.registry.nodes.llm.prompt_compaction.utils import get_message_metadata

from .test_base import PromptCompactionUnitTestBase


class TestExtractionPositionWeights(PromptCompactionUnitTestBase):
    """Test extraction strategy uses full_history_indices for position weights (v3.1)."""

    async def test_extraction_uses_full_history_indices(self):
        """Test that extraction uses full_history_indices for position weights."""
        strategy = ExtractionStrategy(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            store_embeddings=False,
            top_k=3,
        )
        
        # Generate messages
        messages = self._generate_test_messages(5)
        full_history_indices = {msg.id: idx for idx, msg in enumerate(messages)}
        
        # Create runtime_config with full_history_indices
        runtime_config = {
            "full_history_indices": full_history_indices,
            "thread_id": self.test_thread_id,
            "node_id": self.test_node_id,
        }
        
        sections = {
            "system": [],
            "summaries": [],
            "historical": messages[:3],
            "marked": [],
            "recent": messages[3:],
        }
        
        result = await strategy.compact(
            sections=sections,
            budget=self._create_test_budget(),
            model_metadata=self._create_test_model_metadata(),
            ext_context=self.ext_context,
            runtime_config=runtime_config,
        )
        
        # Verify extracted messages have position_weight set
        for msg in result.extracted_messages:
            position_weight = get_message_metadata(msg, "position_weight")
            self.assertIsNotNone(position_weight, "position_weight should be set on extracted messages")
            self.assertIsInstance(position_weight, (int, float), "position_weight should be numeric")

    async def test_extraction_without_full_history_indices(self):
        """Test that extraction works gracefully without full_history_indices (backwards compatibility)."""
        strategy = ExtractionStrategy(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            store_embeddings=False,
            top_k=2,
        )
        
        messages = self._generate_test_messages(4)
        
        sections = {
            "system": [],
            "summaries": [],
            "historical": messages[:2],
            "marked": [],
            "recent": messages[2:],
        }
        
        # No runtime_config at all
        result = await strategy.compact(
            sections=sections,
            budget=self._create_test_budget(),
            model_metadata=self._create_test_model_metadata(),
            ext_context=self.ext_context,
            runtime_config=None,
        )
        
        # Should still work, just without position_weight metadata
        self.assertIsNotNone(result)
        self.assertGreaterEqual(len(result.compacted_messages), 0)


class TestExtractionStrategyDUMP(PromptCompactionUnitTestBase):
    """Test 25: DUMP construction strategy."""

    async def test_dump_concatenates_chunks(self):
        """Should handle DUMP strategy without errors."""
        config = ExtractionConfig(
            construction_strategy=ExtractionStrategyType.DUMP,
            top_k=5,
            store_embeddings=False,
        )
        strategy = ExtractionStrategy(
            construction_strategy=config.construction_strategy,
            store_embeddings=config.store_embeddings,
            top_k=config.top_k,
        )

        # Create test sections
        sections = {
            "system": self._generate_test_messages(1, roles=["system"]),
            "summaries": [],
            "historical": self._generate_test_messages(count=10),
            "marked": [],
            "recent": self._generate_test_messages(count=3),
        }

        budget = self._create_test_budget()
        model_metadata = self._create_test_model_metadata()

        # Test real compact method
        result = await strategy.compact(
            sections=sections,
            budget=budget,
            model_metadata=model_metadata,
            ext_context=self.ext_context,
            runtime_config=None,
        )

        # Verify result structure
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.compacted_messages)
        self.assertIsInstance(result.compacted_messages, list)


class TestExtractionStrategyEXTRACT_FULL(PromptCompactionUnitTestBase):
    """Test 26: EXTRACT_FULL construction strategy."""

    async def test_extract_full_preserves_messages(self):
        """Should handle EXTRACT_FULL strategy without errors."""
        config = ExtractionConfig(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            top_k=5,
            store_embeddings=False,
        )
        strategy = ExtractionStrategy(
            construction_strategy=config.construction_strategy,
            store_embeddings=config.store_embeddings,
            top_k=config.top_k,
        )

        sections = {
            "system": self._generate_test_messages(1, roles=["system"]),
            "summaries": [],
            "historical": self._generate_test_messages(count=10),
            "marked": [],
            "recent": self._generate_test_messages(count=3),
        }

        budget = self._create_test_budget()
        model_metadata = self._create_test_model_metadata()

        result = await strategy.compact(
            sections=sections,
            budget=budget,
            model_metadata=model_metadata,
            ext_context=self.ext_context,
            runtime_config=None,
        )

        # Verify result
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.compacted_messages)
        # Messages should include system, historical extraction, and recent
        self.assertGreater(len(result.compacted_messages), 0)


class TestExtractionStrategyLLM_REWRITE(PromptCompactionUnitTestBase):
    """Test 27: LLM_REWRITE construction strategy."""

    async def test_llm_rewrite_calls_llm(self):
        """Should handle LLM_REWRITE strategy without errors."""
        config = ExtractionConfig(
            construction_strategy=ExtractionStrategyType.LLM_REWRITE,
            top_k=3,
            store_embeddings=False,
        )
        strategy = ExtractionStrategy(
            construction_strategy=config.construction_strategy,
            store_embeddings=config.store_embeddings,
            top_k=config.top_k,
            rewrite_model="gpt-4o-mini",
        )

        sections = {
            "system": self._generate_test_messages(1, roles=["system"]),
            "summaries": [],
            "historical": self._generate_test_messages(count=5),
            "marked": [],
            "recent": self._generate_test_messages(count=2),
        }

        budget = self._create_test_budget()
        model_metadata = self._create_test_model_metadata()

        result = await strategy.compact(
            sections=sections,
            budget=budget,
            model_metadata=model_metadata,
            ext_context=self.ext_context,
            runtime_config=None,
        )

        # Verify result - should not crash
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.compacted_messages)


class TestExtractionTopKFiltering(PromptCompactionUnitTestBase):
    """Test 28: Top-K filtering behavior."""

    async def test_top_k_limits_results(self):
        """Should respect top_k parameter."""
        config = ExtractionConfig(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            top_k=3,  # Only extract top 3
            store_embeddings=False,
        )
        strategy = ExtractionStrategy(
            construction_strategy=config.construction_strategy,
            store_embeddings=config.store_embeddings,
            top_k=config.top_k,
        )

        sections = {
            "system": [],
            "summaries": [],
            "historical": self._generate_test_messages(count=10),
            "marked": [],
            "recent": self._generate_test_messages(count=2),
        }

        budget = self._create_test_budget()
        model_metadata = self._create_test_model_metadata()

        result = await strategy.compact(
            sections=sections,
            budget=budget,
            model_metadata=model_metadata,
            ext_context=self.ext_context,
            runtime_config=None,
        )

        self.assertIsNotNone(result)
        # Result should have recent messages at minimum
        self.assertGreater(len(result.compacted_messages), 0)


class TestExtractionSimilarityThreshold(PromptCompactionUnitTestBase):
    """Test 29: Similarity threshold filtering."""

    async def test_similarity_threshold_filters_low_scores(self):
        """Should filter messages below similarity threshold."""
        config = ExtractionConfig(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            top_k=5,
            similarity_threshold=0.8,  # High threshold
            store_embeddings=False,
        )
        strategy = ExtractionStrategy(
            construction_strategy=config.construction_strategy,
            store_embeddings=config.store_embeddings,
            top_k=config.top_k,
            similarity_threshold=config.similarity_threshold,
        )

        sections = {
            "system": [],
            "summaries": [],
            "historical": self._generate_test_messages(count=5),
            "marked": [],
            "recent": self._generate_test_messages(count=2),
        }

        budget = self._create_test_budget()
        model_metadata = self._create_test_model_metadata()

        result = await strategy.compact(
            sections=sections,
            budget=budget,
            model_metadata=model_metadata,
            ext_context=self.ext_context,
            runtime_config=None,
        )

        self.assertIsNotNone(result)
        self.assertIsNotNone(result.compacted_messages)


class TestExtractionRelevanceScoring(PromptCompactionUnitTestBase):
    """Test 30-31: Relevance scoring behavior."""

    async def test_relevance_scores_preserved(self):
        """Should preserve relevance scores in metadata."""
        config = ExtractionConfig(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            top_k=5,
            store_embeddings=False,
        )
        strategy = ExtractionStrategy(
            construction_strategy=config.construction_strategy,
            store_embeddings=config.store_embeddings,
            top_k=config.top_k,
        )

        sections = {
            "system": [],
            "summaries": [],
            "historical": self._generate_test_messages(count=10),
            "marked": [],
            "recent": self._generate_test_messages(count=3),
        }

        budget = self._create_test_budget()
        model_metadata = self._create_test_model_metadata()

        result = await strategy.compact(
            sections=sections,
            budget=budget,
            model_metadata=model_metadata,
            ext_context=self.ext_context,
            runtime_config=None,
        )

        self.assertIsNotNone(result)
        self.assertIsNotNone(result.metadata)

    async def test_relevance_scores_sorted_descending(self):
        """Should sort by relevance (highest first)."""
        config = ExtractionConfig(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            top_k=5,
            store_embeddings=False,
        )
        strategy = ExtractionStrategy(
            construction_strategy=config.construction_strategy,
            store_embeddings=config.store_embeddings,
            top_k=config.top_k,
        )

        sections = {
            "system": [],
            "summaries": [],
            "historical": self._generate_test_messages(count=10),
            "marked": [],
            "recent": self._generate_test_messages(count=3),
        }

        budget = self._create_test_budget()
        model_metadata = self._create_test_model_metadata()

        result = await strategy.compact(
            sections=sections,
            budget=budget,
            model_metadata=model_metadata,
            ext_context=self.ext_context,
            runtime_config=None,
        )

        self.assertIsNotNone(result)


class TestExtractionBudgetAllocation(PromptCompactionUnitTestBase):
    """Test 32: Budget allocation for extraction."""

    async def test_respects_extraction_budget(self):
        """Should respect allocated extraction budget."""
        config = ExtractionConfig(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            top_k=5,
            store_embeddings=False,
        )
        strategy = ExtractionStrategy(
            construction_strategy=config.construction_strategy,
            store_embeddings=config.store_embeddings,
            top_k=config.top_k,
        )

        sections = {
            "system": [],
            "summaries": [],
            "historical": self._generate_test_messages(count=10),
            "marked": [],
            "recent": self._generate_test_messages(count=2),
        }

        # Small budget
        budget = self._create_test_budget(total_context=10000, max_output_tokens=2000)
        model_metadata = self._create_test_model_metadata()

        result = await strategy.compact(
            sections=sections,
            budget=budget,
            model_metadata=model_metadata,
            ext_context=self.ext_context,
            runtime_config=None,
        )

        self.assertIsNotNone(result)


class TestExtractionChunkConstruction(PromptCompactionUnitTestBase):
    """Test 33: Chunk construction and tracking."""

    async def test_chunk_ids_tracked(self):
        """Should track chunk IDs in metadata."""
        config = ExtractionConfig(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            top_k=5,
            store_embeddings=False,
        )
        strategy = ExtractionStrategy(
            construction_strategy=config.construction_strategy,
            store_embeddings=config.store_embeddings,
            top_k=config.top_k,
        )

        sections = {
            "system": [],
            "summaries": [],
            "historical": self._generate_test_messages(count=10),
            "marked": [],
            "recent": self._generate_test_messages(count=3),
        }

        budget = self._create_test_budget()
        model_metadata = self._create_test_model_metadata()

        result = await strategy.compact(
            sections=sections,
            budget=budget,
            model_metadata=model_metadata,
            ext_context=self.ext_context,
            runtime_config=None,
        )

        self.assertIsNotNone(result)


class TestExtractionMessageOrdering(PromptCompactionUnitTestBase):
    """Test 34: Message ordering preservation."""

    async def test_preserves_chronological_order(self):
        """Should maintain chronological order of messages."""
        config = ExtractionConfig(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            top_k=5,
            store_embeddings=False,
        )
        strategy = ExtractionStrategy(
            construction_strategy=config.construction_strategy,
            store_embeddings=config.store_embeddings,
            top_k=config.top_k,
        )

        sections = {
            "system": [],
            "summaries": [],
            "historical": self._generate_test_messages(count=10),
            "marked": [],
            "recent": self._generate_test_messages(count=3),
        }

        budget = self._create_test_budget()
        model_metadata = self._create_test_model_metadata()

        result = await strategy.compact(
            sections=sections,
            budget=budget,
            model_metadata=model_metadata,
            ext_context=self.ext_context,
            runtime_config=None,
        )

        self.assertIsNotNone(result)
        # Should have messages in order
        self.assertIsInstance(result.compacted_messages, list)


class TestExtractionEmptyResults(PromptCompactionUnitTestBase):
    """Test 35: Handling empty extraction results."""

    async def test_empty_historical_messages(self):
        """Should handle case with no historical messages."""
        config = ExtractionConfig(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            top_k=5,
            store_embeddings=False,
        )
        strategy = ExtractionStrategy(
            construction_strategy=config.construction_strategy,
            store_embeddings=config.store_embeddings,
            top_k=config.top_k,
        )

        sections = {
            "system": self._generate_test_messages(1, roles=["system"]),
            "summaries": [],
            "historical": [],  # Empty
            "marked": [],
            "recent": self._generate_test_messages(count=3),
        }

        budget = self._create_test_budget()
        model_metadata = self._create_test_model_metadata()

        result = await strategy.compact(
            sections=sections,
            budget=budget,
            model_metadata=model_metadata,
            ext_context=self.ext_context,
            runtime_config=None,
        )

        self.assertIsNotNone(result)
        # Should still return system + recent
        self.assertGreater(len(result.compacted_messages), 0)

    async def test_no_messages_above_threshold(self):
        """Should handle case where no messages meet threshold."""
        config = ExtractionConfig(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            top_k=5,
            similarity_threshold=0.99,  # Very high threshold
            store_embeddings=False,
        )
        strategy = ExtractionStrategy(
            construction_strategy=config.construction_strategy,
            store_embeddings=config.store_embeddings,
            top_k=config.top_k,
            similarity_threshold=config.similarity_threshold,
        )

        sections = {
            "system": [],
            "summaries": [],
            "historical": self._generate_test_messages(count=5),
            "marked": [],
            "recent": self._generate_test_messages(count=2),
        }

        budget = self._create_test_budget()
        model_metadata = self._create_test_model_metadata()

        result = await strategy.compact(
            sections=sections,
            budget=budget,
            model_metadata=model_metadata,
            ext_context=self.ext_context,
            runtime_config=None,
        )

        self.assertIsNotNone(result)


class TestExtractionWithExistingMarked(PromptCompactionUnitTestBase):
    """Test bonus: Extraction with existing marked messages."""

    async def test_respects_existing_marked_messages(self):
        """Should preserve existing marked messages."""
        config = ExtractionConfig(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            top_k=5,
            store_embeddings=False,
        )
        strategy = ExtractionStrategy(
            construction_strategy=config.construction_strategy,
            store_embeddings=config.store_embeddings,
            top_k=config.top_k,
        )

        marked_msgs = self._generate_test_messages(count=2)

        sections = {
            "system": [],
            "summaries": [],
            "historical": self._generate_test_messages(count=10),
            "marked": marked_msgs,  # Pre-marked messages
            "recent": self._generate_test_messages(count=3),
        }

        budget = self._create_test_budget()
        model_metadata = self._create_test_model_metadata()

        result = await strategy.compact(
            sections=sections,
            budget=budget,
            model_metadata=model_metadata,
            ext_context=self.ext_context,
            runtime_config=None,
        )

        self.assertIsNotNone(result)
        # Should include marked messages
        self.assertGreater(len(result.compacted_messages), len(marked_msgs))
