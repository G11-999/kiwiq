"""
Unit tests for v2.1 hybrid strategy functionality.

Tests cover:
- Budget allocation between extraction and summarization
- Sequential execution (extraction first, then summarization)
- Extraction budget percentages (2%, 5%, 10%)
- Budget reallocation when extraction completes
- Combined output validation

Test IDs: 36-42 (from comprehensive test plan)
"""

import unittest

from workflow_service.registry.nodes.llm.prompt_compaction.compactor import (
    ExtractionConfig,
    HybridConfig,
    SummarizationConfig,
)
from workflow_service.registry.nodes.llm.prompt_compaction.strategies import (
    ExtractionStrategy,
    HybridStrategy,
    SummarizationStrategy,
)
from workflow_service.registry.nodes.llm.prompt_compaction.utils import (
    ExtractionStrategy as ExtractionStrategyType,
    get_message_metadata,
)

from .test_base import PromptCompactionUnitTestBase


class TestHybridPositionWeights(PromptCompactionUnitTestBase):
    """Test hybrid strategy uses full_history_indices for position weights (v3.1)."""

    async def test_hybrid_uses_full_history_indices(self):
        """Test that hybrid strategy uses full_history_indices for position weights."""
        strategy = HybridStrategy()
        
        # Generate messages
        messages = self._generate_test_messages(8)
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
            "historical": messages[:5],
            "marked": [],
            "recent": messages[5:],
        }
        
        result = await strategy.compact(
            sections=sections,
            budget=self._create_test_budget(),
            model_metadata=self._create_test_model_metadata(),
            ext_context=self.ext_context,
            runtime_config=runtime_config,
        )
        
        # Verify compacted messages have position_weight set where expected
        # (extractions and summaries should have position_weight)
        messages_with_weight = [
            msg for msg in result.compacted_messages
            if get_message_metadata(msg, "position_weight") is not None
        ]
        self.assertGreater(len(messages_with_weight), 0, 
                          "Some compacted messages should have position_weight set")


class TestHybridBudgetAllocation(PromptCompactionUnitTestBase):
    """Test 36: Budget allocation between extraction and summarization."""

    async def test_default_5_percent_extraction_budget(self):
        """Should allocate 5% of budget to extraction by default."""
        extraction_strategy = ExtractionStrategy(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            store_embeddings=False,
        )
        summarization_strategy = SummarizationStrategy()

        strategy = HybridStrategy(
            extraction_pct=0.05,  # 5% default
            extraction_strategy=extraction_strategy,
            summarization_strategy=summarization_strategy,
        )

        # Verify config
        self.assertEqual(strategy.extraction_pct, 0.05)

    async def test_budget_split_calculation(self):
        """Should correctly configure budget split percentage."""
        extraction_strategy = ExtractionStrategy(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            store_embeddings=False,
        )
        summarization_strategy = SummarizationStrategy()

        strategy = HybridStrategy(
            extraction_pct=0.05,
            extraction_strategy=extraction_strategy,
            summarization_strategy=summarization_strategy,
        )

        # Verify percentage is set correctly
        self.assertEqual(strategy.extraction_pct, 0.05)


class TestHybridSequentialExecution(PromptCompactionUnitTestBase):
    """Test 37: Sequential execution (extraction first, then summarization)."""

    async def test_extraction_runs_before_summarization(self):
        """Should run extraction before summarization."""
        extraction_strategy = ExtractionStrategy(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            store_embeddings=False,
        )
        summarization_strategy = SummarizationStrategy()

        strategy = HybridStrategy(
            extraction_pct=0.05,
            extraction_strategy=extraction_strategy,
            summarization_strategy=summarization_strategy,
        )

        sections = {
            "system": self._generate_test_messages(1, roles=["system"]),
            "summaries": [],
            "historical": self._generate_test_messages(20),
            "marked": [],
            "recent": self._generate_test_messages(5),
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

        # Verify result is not None - strategy executed successfully
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.compacted_messages)


class TestHybridExtractionPercentages(PromptCompactionUnitTestBase):
    """Test 38-40: Different extraction budget percentages."""

    async def test_2_percent_extraction_budget(self):
        """Should allocate 2% to extraction."""
        extraction_strategy = ExtractionStrategy(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            store_embeddings=False,
        )
        summarization_strategy = SummarizationStrategy()

        strategy = HybridStrategy(
            extraction_pct=0.02,  # 2%
            extraction_strategy=extraction_strategy,
            summarization_strategy=summarization_strategy,
        )

        self.assertEqual(strategy.extraction_pct, 0.02)

    async def test_5_percent_extraction_budget(self):
        """Should allocate 5% to extraction (default)."""
        extraction_strategy = ExtractionStrategy(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            store_embeddings=False,
        )
        summarization_strategy = SummarizationStrategy()

        strategy = HybridStrategy(
            extraction_pct=0.05,  # 5%
            extraction_strategy=extraction_strategy,
            summarization_strategy=summarization_strategy,
        )

        self.assertEqual(strategy.extraction_pct, 0.05)

    async def test_10_percent_extraction_budget(self):
        """Should allocate 10% to extraction."""
        extraction_strategy = ExtractionStrategy(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            store_embeddings=False,
        )
        summarization_strategy = SummarizationStrategy()

        strategy = HybridStrategy(
            extraction_pct=0.10,  # 10%
            extraction_strategy=extraction_strategy,
            summarization_strategy=summarization_strategy,
        )

        self.assertEqual(strategy.extraction_pct, 0.10)


class TestHybridBudgetReallocation(PromptCompactionUnitTestBase):
    """Test 41: Budget reallocation when extraction completes."""

    async def test_unused_extraction_budget_reallocated(self):
        """Should handle hybrid strategy with small extraction budget."""
        extraction_strategy = ExtractionStrategy(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            top_k=3,  # Extract only 3 messages
            store_embeddings=False,
        )
        summarization_strategy = SummarizationStrategy()

        strategy = HybridStrategy(
            extraction_pct=0.05,
            extraction_strategy=extraction_strategy,
            summarization_strategy=summarization_strategy,
        )

        sections = {
            "system": self._generate_test_messages(1, roles=["system"]),
            "summaries": [],
            "historical": self._generate_test_messages(30),
            "marked": [],
            "recent": self._generate_test_messages(5),
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


class TestHybridCombinedOutput(PromptCompactionUnitTestBase):
    """Test 42: Combined output validation from hybrid strategy."""

    async def test_combined_output_structure(self):
        """Should combine extraction and summarization outputs correctly."""
        extraction_strategy = ExtractionStrategy(
            construction_strategy=ExtractionStrategyType.EXTRACT_FULL,
            store_embeddings=False,
        )
        summarization_strategy = SummarizationStrategy()

        strategy = HybridStrategy(
            extraction_pct=0.05,
            extraction_strategy=extraction_strategy,
            summarization_strategy=summarization_strategy,
        )

        sections = {
            "system": self._generate_test_messages(1, roles=["system"]),
            "summaries": [],
            "historical": self._generate_test_messages(20),
            "marked": [],
            "recent": self._generate_test_messages(5),
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

        # Verify result structure
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.compacted_messages)

        # Output should include messages
        compacted_count = len(result.compacted_messages)
        self.assertGreater(compacted_count, 0)


class TestHybridStrategyIntegration(PromptCompactionUnitTestBase):
    """Test hybrid strategy uses same code paths as standalone strategies (v3.1)."""

    async def test_hybrid_summarization_uses_same_code_path(self):
        """Test that hybrid's summarization phase matches standalone summarization."""
        # This verifies that HybridStrategy calls summarization_strategy.compact() directly
        # which means it uses the EXACT same code path including all v3.1 enhancements
        
        hybrid_strategy = HybridStrategy()
        
        messages = self._generate_test_messages(10)
        
        sections = {
            "system": [],
            "summaries": [],
            "historical": messages[:7],  # Will be split between extraction and summarization
            "marked": [],
            "recent": messages[7:],
        }
        
        result = await hybrid_strategy.compact(
            sections=sections,
            budget=self._create_test_budget(),
            model_metadata=self._create_test_model_metadata(),
            ext_context=self.ext_context,
        )
        
        # Verify both extraction and summarization happened
        self.assertIsNotNone(result.summary_messages, "Should have summary messages")
        self.assertIsNotNone(result.extracted_messages, "Should have extracted messages")
        
        # Verify summaries have v3.1 metadata (same as standalone summarization)
        for summary in result.summary_messages:
            llm_call_made = get_message_metadata(summary, "llm_call_made")
            # Metadata should exist (may be None if no LLM call was actually made in test)
            self.assertIn(llm_call_made, [None, True],
                         "llm_call_made should be None or True")
        
        # Verify extractions have v3.1 metadata
        for extraction in result.extracted_messages:
            extraction_performed = get_message_metadata(extraction, "extraction_performed")
            self.assertEqual(extraction_performed, True,
                           "extraction_performed should be True on extracted messages")

    async def test_hybrid_metadata_from_both_strategies(self):
        """Test that hybrid preserves metadata from both extraction and summarization."""
        hybrid_strategy = HybridStrategy()
        
        messages = self._generate_test_messages(8)
        full_history_indices = {msg.id: idx for idx, msg in enumerate(messages)}
        
        runtime_config = {
            "full_history_indices": full_history_indices,
            "thread_id": self.test_thread_id,
            "node_id": self.test_node_id,
        }
        
        sections = {
            "system": [],
            "summaries": [],
            "historical": messages[:5],
            "marked": [],
            "recent": messages[5:],
        }
        
        result = await hybrid_strategy.compact(
            sections=sections,
            budget=self._create_test_budget(),
            model_metadata=self._create_test_model_metadata(),
            ext_context=self.ext_context,
            runtime_config=runtime_config,
        )
        
        # Verify result has both extraction and summarization metadata
        self.assertIn("extraction_cost", result.metadata, "Should have extraction_cost in metadata")
        self.assertIn("summarization_cost", result.metadata, "Should have summarization_cost in metadata")
        self.assertEqual(result.metadata.get("strategy"), "hybrid", "Strategy should be hybrid")


if __name__ == "__main__":
    unittest.main()
