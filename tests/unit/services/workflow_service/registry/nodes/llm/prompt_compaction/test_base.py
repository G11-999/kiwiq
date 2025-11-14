"""
Base test classes and utilities for v2.1 prompt compaction testing.

This module provides:
- Base test classes for unit and integration tests
- Helper methods for test data generation
- Mock utilities for external dependencies
- Common fixtures and setup/teardown patterns

Following patterns from:
- tests/integration/clients/weaviate/test_weaviate_client.py
- services/workflow_service/registry/nodes/llm/tests/test_basic_llm_workflow.py
"""

import time
import unittest
import uuid
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from workflow_service.registry.nodes.llm.prompt_compaction.compactor import (
    CompactionStrategyType,
    CompactionLLMConfig,
    ContextBudget,
    ExtractionConfig,
    HybridConfig,
    ModelMetadata,
    PromptCompactionConfig,
)
from workflow_service.registry.nodes.llm.prompt_compaction.context_manager import (
    ContextBudgetConfig,
)
from workflow_service.registry.nodes.llm.prompt_compaction.utils import (
    ExtractionStrategy,
    GraphEdgeType,
    MessageSectionLabel,
)

if TYPE_CHECKING:
    from workflow_service.registry.nodes.llm.prompt_compaction.strategies import SummarizationMode


class PromptCompactionUnitTestBase(unittest.IsolatedAsyncioTestCase):
    """
    Base class for prompt compaction unit tests.

    Provides:
    - Mock external context setup
    - Test data generators
    - Common assertions
    - Helper methods for message creation
    """

    def setUp(self):
        """Setup test fixtures."""
        self.test_user_id = uuid4()
        self.test_org_id = uuid4()
        self.test_run_id = uuid4()
        self.test_thread_id = f"test_thread_{int(time.time())}"
        self.test_node_id = f"test_node_{int(time.time())}"

        # Track created test data for cleanup
        self.test_message_ids: List[str] = []
        self.test_chunk_ids: List[str] = []

    async def asyncSetUp(self):
        """Async setup for test fixtures."""
        await super().asyncSetUp()
        self.ext_context = self._create_mock_ext_context()

    async def asyncTearDown(self):
        """Async cleanup after each test."""
        await super().asyncTearDown()
        # Clear tracked test data
        self.test_message_ids.clear()
        self.test_chunk_ids.clear()

    def _create_mock_ext_context(self) -> Mock:
        """Create mock external context manager."""
        ext_context = Mock()
        ext_context.org_id = self.test_org_id
        ext_context.user_id = self.test_user_id
        return ext_context

    def _generate_test_message(
        self,
        content: str,
        role: str = "human",
        message_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BaseMessage:
        """Generate a test message with tracking."""
        if message_id is None:
            message_id = f"msg_{uuid4().hex[:8]}"

        self.test_message_ids.append(message_id)

        msg_metadata = metadata or {}

        if role == "human":
            return HumanMessage(
                content=content,
                id=message_id,
                response_metadata=msg_metadata
            )
        elif role == "ai":
            return AIMessage(
                content=content,
                id=message_id,
                response_metadata=msg_metadata
            )
        elif role == "system":
            return SystemMessage(
                content=content,
                id=message_id,
                response_metadata=msg_metadata
            )
        elif role == "tool":
            return ToolMessage(
                content=content,
                tool_call_id=f"tool_{uuid4().hex[:8]}",
                id=message_id,
                response_metadata=msg_metadata
            )
        else:
            raise ValueError(f"Unknown role: {role}")

    def _generate_test_messages(
        self,
        count: int,
        content_prefix: str = "Test message",
        roles: Optional[List[str]] = None,
    ) -> List[BaseMessage]:
        """Generate multiple test messages."""
        if roles is None:
            roles = ["human", "ai"] * (count // 2 + 1)

        messages = []
        for i in range(count):
            role = roles[i % len(roles)]
            content = f"{content_prefix} {i+1}"
            messages.append(self._generate_test_message(content, role=role))

        return messages

    def _create_test_config(
        self,
        strategy: CompactionStrategyType = CompactionStrategyType.HYBRID,
        extraction_config: Optional[ExtractionConfig] = None,
        hybrid_config: Optional[HybridConfig] = None,
        llm_config: Optional[CompactionLLMConfig] = None,
    ) -> PromptCompactionConfig:
        """Create test compaction config."""
        if extraction_config is None:
            extraction_config = ExtractionConfig(
                construction_strategy=ExtractionStrategy.EXTRACT_FULL,
                top_k=5,
                similarity_threshold=0.7,
                store_embeddings=True,
            )

        if hybrid_config is None:
            hybrid_config = HybridConfig(
                extraction_pct=0.05,
                extraction_first=True,
            )

        if llm_config is None:
            llm_config = CompactionLLMConfig(
                default_provider="openai",
                default_model="gpt-4o-mini",
            )

        return PromptCompactionConfig(
            enabled=True,
            strategy=strategy,
            context_trigger_threshold=0.75,
            target_context_pct=0.50,
            extraction=extraction_config,
            hybrid=hybrid_config,
            llm_config=llm_config,
        )

    def _create_test_budget(
        self,
        total_context: int = 128000,
        max_output_tokens: int = 16384,
    ) -> ContextBudget:
        """Create test context budget."""
        config = ContextBudgetConfig()
        return ContextBudget.calculate(
            total_context=total_context,
            max_output_tokens=max_output_tokens,
            config=config,
        )

    def _create_test_model_metadata(
        self,
        model_name: str = "gpt-4o",
        provider: str = "openai",
        context_limit: int = 128000,
        output_token_limit: int = 16384,
    ) -> ModelMetadata:
        """Create test model metadata."""
        return ModelMetadata(
            model_name=model_name,
            provider=provider,
            context_limit=context_limit,
            output_token_limit=output_token_limit,
        )

    def _create_test_runtime_config(
        self,
        thread_id: Optional[str] = None,
        node_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create test runtime config."""
        return {
            "thread_id": thread_id or self.test_thread_id,
            "node_id": node_id or self.test_node_id,
        }

    # Assertion helpers

    def assertMessageHasMetadata(
        self,
        message: BaseMessage,
        metadata_keys: List[str],
    ):
        """Assert message has required metadata keys."""
        self.assertIsNotNone(message.response_metadata)
        for key in metadata_keys:
            self.assertIn(key, message.response_metadata)

    def assertMessageHasCompactionMetadata(
        self,
        message: BaseMessage,
        section_label: Optional[MessageSectionLabel] = None,
        has_graph_edges: bool = False,
    ):
        """Assert message has v2.1 compaction metadata."""
        self.assertIn("compaction", message.response_metadata)
        compaction_meta = message.response_metadata["compaction"]

        # Check section label
        self.assertIn("section_label", compaction_meta)
        if section_label:
            self.assertEqual(compaction_meta["section_label"], section_label.value)

        # Check graph edges if required
        if has_graph_edges:
            self.assertIn("graph_edges", compaction_meta)

    def assertMessageIngested(
        self,
        message: BaseMessage,
        expected_chunk_ids: Optional[List[str]] = None,
    ):
        """Assert message has ingestion metadata."""
        self.assertIn("compaction", message.response_metadata)
        compaction_meta = message.response_metadata["compaction"]
        self.assertIn("ingestion", compaction_meta)

        ingestion_meta = compaction_meta["ingestion"]
        self.assertIn("ingested", ingestion_meta)
        self.assertTrue(ingestion_meta["ingested"])
        self.assertIn("chunk_ids", ingestion_meta)

        if expected_chunk_ids:
            self.assertEqual(
                set(ingestion_meta["chunk_ids"]),
                set(expected_chunk_ids)
            )

    def assertMessageNotIngested(self, message: BaseMessage):
        """Assert message does not have ingestion metadata."""
        if "compaction" not in message.response_metadata:
            return  # No compaction metadata at all - not ingested

        compaction_meta = message.response_metadata["compaction"]
        if "ingestion" not in compaction_meta:
            return  # No ingestion metadata - not ingested

        ingestion_meta = compaction_meta["ingestion"]
        self.assertFalse(ingestion_meta.get("ingested", False))


class PromptCompactionIntegrationTestBase(unittest.IsolatedAsyncioTestCase):
    """
    Base class for prompt compaction integration tests.

    Provides:
    - Real external context setup
    - Database connection management
    - Weaviate client setup
    - Cleanup utilities
    """

    def setUp(self):
        """Setup test fixtures."""
        self.test_user_id = uuid4()
        self.test_org_id = uuid4()
        self.test_run_id = uuid4()
        self.test_thread_id = f"test_thread_{int(time.time())}_{uuid4().hex[:6]}"
        self.test_node_id = f"test_node_{int(time.time())}_{uuid4().hex[:6]}"

        # Track created resources for cleanup
        self.test_thread_ids: List[str] = []
        self.test_collection_names: List[str] = []

    async def asyncSetUp(self):
        """Async setup for integration tests."""
        await super().asyncSetUp()
        # Integration tests will override this to setup real clients
        self.ext_context = None

    async def asyncTearDown(self):
        """Async cleanup after each test."""
        await super().asyncTearDown()

        # Cleanup Weaviate collections
        if self.test_collection_names:
            await self._cleanup_weaviate_collections()

        # Clear tracked resources
        self.test_thread_ids.clear()
        self.test_collection_names.clear()

    async def _cleanup_weaviate_collections(self):
        """Cleanup test Weaviate collections."""
        # Integration tests will override this
        pass

    def _generate_unique_thread_id(self) -> str:
        """Generate unique thread ID for test isolation."""
        thread_id = f"test_thread_{int(time.time())}_{uuid4().hex[:6]}"
        self.test_thread_ids.append(thread_id)
        return thread_id

    def _generate_unique_collection_name(self, prefix: str = "TestCompaction") -> str:
        """Generate unique collection name for test isolation."""
        collection_name = f"{prefix}_{int(time.time())}_{uuid4().hex[:6]}"
        self.test_collection_names.append(collection_name)
        return collection_name

    def _create_test_model_metadata(
        self,
        model_name: str = "gpt-4o",
        provider: str = "openai",
        context_limit: int = 128000,
        output_token_limit: int = 16384,
    ) -> ModelMetadata:
        """Create test model metadata."""
        return ModelMetadata(
            model_name=model_name,
            provider=provider,
            context_limit=context_limit,
            output_token_limit=output_token_limit,
        )

    def _generate_test_messages(
        self,
        count: int,
        content_prefix: str = "Test message",
        roles: Optional[List[str]] = None,
    ) -> List[BaseMessage]:
        """Generate multiple test messages."""
        if roles is None:
            roles = ["human", "ai"] * (count // 2 + 1)

        messages = []
        for i in range(count):
            role = roles[i % len(roles)]
            content = f"{content_prefix} {i+1}"
            messages.append(self._generate_test_message(content, role=role))

        return messages

    def _generate_test_message(
        self,
        content: str,
        role: str = "human",
        message_id: Optional[str] = None,
    ) -> BaseMessage:
        """Generate a test message."""
        if message_id is None:
            message_id = f"msg_{uuid4().hex[:8]}"

        if role == "human":
            return HumanMessage(content=content, id=message_id)
        elif role == "ai":
            return AIMessage(content=content, id=message_id)
        elif role == "system":
            return SystemMessage(content=content, id=message_id)
        elif role == "tool":
            return ToolMessage(
                content=content,
                tool_call_id=f"tool_{uuid4().hex[:8]}",
                id=message_id,
            )
        else:
            raise ValueError(f"Unknown role: {role}")

    def _create_config_impl(
        self,
        mode: "SummarizationMode" = None,
        strategy: "CompactionStrategyType" = None,
        max_tokens: int = 4000,
        target_tokens: int = 2000,
    ) -> "PromptCompactionConfig":
        """
        Create test compaction config for integration tests.

        Simplified config creation for Phase 1 tests.
        
        Args:
            mode: Summarization mode (goes into config.summarization.mode)
            strategy: Compaction strategy type
            max_tokens: Context limit for model metadata
            target_tokens: Target context usage after compaction
        """
        from workflow_service.registry.nodes.llm.prompt_compaction.compactor import (
            PromptCompactionConfig,
            SummarizationConfig,
            ContextBudgetConfig,
        )
        from workflow_service.registry.nodes.llm.prompt_compaction.strategies import SummarizationMode, CompactionStrategyType

        if strategy is None:
            strategy = CompactionStrategyType.SUMMARIZATION
        if mode is None:
            mode = SummarizationMode.FROM_SCRATCH

        # Create nested config structure
        summarization_config = SummarizationConfig(mode=mode)
        
        # Calculate trigger threshold based on max_tokens and target_tokens
        # trigger_threshold_pct = what % of context triggers compaction
        # We want to trigger when total > target_tokens
        trigger_pct = target_tokens / max_tokens if max_tokens > 0 else 0.5
        
        config = PromptCompactionConfig(
            enabled=True,
            enable_billing=False,  # Disable billing for tests
            strategy=strategy,
            context_budget=ContextBudgetConfig(trigger_threshold_pct=trigger_pct),
            summarization=summarization_config,
        )
        
        # Store max_tokens for use by _run_compaction to create matching model_metadata
        # This is a test-only hack to pass max_tokens through the config
        config._test_max_tokens = max_tokens
        config._test_output_tokens = max(512, max_tokens // 4)  # 25% for output
        
        return config

    def _create_test_config(
        self,
        mode: "SummarizationMode" = None,
        strategy: "CompactionStrategyType" = None,
        max_tokens: int = 4000,
        target_tokens: int = 2000,
    ) -> "PromptCompactionConfig":
        """Create test config."""
        return self._create_config_impl(mode, strategy, max_tokens, target_tokens)

    def _create_test_compaction_config(
        self,
        mode: "SummarizationMode" = None,
        strategy: "CompactionStrategyType" = None,
        max_tokens: int = 4000,
        target_tokens: int = 2000,
    ) -> "PromptCompactionConfig":
        """Alias for _create_test_config for compatibility."""
        return self._create_config_impl(mode, strategy, max_tokens, target_tokens)

    async def _run_compaction(
        self,
        messages: List["BaseMessage"],
        config: "PromptCompactionConfig",
        thread_id: str,
    ) -> Dict[str, Any]:
        """
        Run compaction on messages and return result.

        Wrapper for integration tests to run compaction.
        """
        from uuid import uuid4
        from workflow_service.registry.nodes.llm.prompt_compaction.compactor import PromptCompactor

        # Create model metadata
        # Use test-specific max_tokens if available (set by _create_config_impl)
        context_limit = getattr(config, '_test_max_tokens', 128000)
        output_limit = getattr(config, '_test_output_tokens', 16384)
        
        model_metadata = self._create_test_model_metadata(
            context_limit=context_limit,
            output_token_limit=output_limit,
        )

        # Create compactor with all required arguments
        compactor = PromptCompactor(
            config=config,
            model_metadata=model_metadata,
            node_id="test_node",
            node_name="test_compaction_node",
        )

        # Create app_context matching production expectations
        class MockUser:
            def __init__(self):
                self.id = self.test_user_id if hasattr(self, 'test_user_id') else uuid4()

        class MockRunJob:
            def __init__(self):
                self.owner_org_id = self.test_org_id if hasattr(self, 'test_org_id') else uuid4()
                self.run_id = self.test_run_id if hasattr(self, 'test_run_id') else uuid4()
                self.id = uuid4()

        app_context = {
            "user": MockUser(),
            "workflow_run_job": MockRunJob(),
        }

        # Run compaction
        result = await compactor.compact(
            messages=messages,
            ext_context=self.ext_context,
            app_context=app_context,
        )

        return {
            "summarized_messages": result.compacted_messages,
            "metadata": result.metadata,
        }

    async def _run_compaction_with_provider(
        self,
        messages: List["BaseMessage"],
        config: "PromptCompactionConfig",
        thread_id: str,
        provider: str = "openai",
        model_name: str = "gpt-4o",
    ) -> Dict[str, Any]:
        """
        Run compaction with specific provider and model.

        This variant allows testing fallback behavior by specifying the main model's provider.
        For example, provider="perplexity" will trigger Perplexity fallback logic.
        """
        from uuid import uuid4
        from workflow_service.registry.nodes.llm.prompt_compaction.compactor import PromptCompactor

        # Create model metadata with specified provider
        context_limit = getattr(config, '_test_max_tokens', 128000)
        output_limit = getattr(config, '_test_output_tokens', 16384)
        
        model_metadata = self._create_test_model_metadata(
            model_name=model_name,
            provider=provider,
            context_limit=context_limit,
            output_token_limit=output_limit,
        )

        # Create compactor with all required arguments
        compactor = PromptCompactor(
            config=config,
            model_metadata=model_metadata,
            node_id="test_node",
            node_name="test_compaction_node",
        )

        # Create app_context matching production expectations
        class MockUser:
            def __init__(self):
                self.id = self.test_user_id if hasattr(self, 'test_user_id') else uuid4()

        class MockRunJob:
            def __init__(self):
                self.owner_org_id = self.test_org_id if hasattr(self, 'test_org_id') else uuid4()
                self.run_id = self.test_run_id if hasattr(self, 'test_run_id') else uuid4()
                self.id = uuid4()

        app_context = {
            "user": MockUser(),
            "workflow_run_job": MockRunJob(),
        }

        # Run compaction
        result = await compactor.compact(
            messages=messages,
            ext_context=self.ext_context,
            app_context=app_context,
        )

        return {
            "summarized_messages": result.compacted_messages,
            "metadata": result.metadata,
        }


class TestMessageClassifier(unittest.TestCase):
    def setUp(self):
        from workflow_service.registry.nodes.llm.prompt_compaction.context_manager import MessageClassifier
        self.classifier = MessageClassifier()

    def test_anthropic_tool_pairing(self):
        """Test that Anthropic tool call and result are grouped as a tool sequence."""
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, BaseMessage, SystemMessage
        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="User input"),
            AIMessage(
                content=[{"type": "text", "text": "Thinking..."}, {"type": "tool_use", "id": "tool1", "name": "get_info", "input": {}}],
                tool_calls=[{"id": "tool1", "name": "get_info", "args": {}}],
                id="ai_msg"
            ),
            HumanMessage(
                content=[{"type": "tool_result", "tool_use_id": "tool1", "content": "Tool result"}],
                id="human_tool_response"
            ),
            HumanMessage(content="Another user input", id="last_human"),
        ]
        
        sections = self.classifier.classify(messages, recent_message_count=2)
        
        # v2.5: Tool sequences merged into recent/historical (no separate latest_tools/old_tools)
        # Tool sequence uses MAX SPAN: AIMessage + HumanMessage(tool_result) + HumanMessage(user input)
        # With recent_message_count=2, we'd take last 2 messages, but tool sequence (indices 2-4)
        # causes split to move earlier to keep sequence intact, so recent gets all 3 messages
        self.assertEqual(len(sections["recent"]), 3)  # Tool sequence in recent (last tool sequence)
        self.assertEqual(len(sections["historical"]), 1)  # Initial user input goes to historical

        # Check content of recent (includes the complete tool sequence)
        self.assertIsInstance(sections["recent"][0], AIMessage)
        self.assertIsInstance(sections["recent"][1], HumanMessage)
        self.assertIsInstance(sections["recent"][2], HumanMessage)
        self.assertEqual(sections["recent"][0].id, "ai_msg")
        self.assertEqual(sections["recent"][1].id, "human_tool_response")
        self.assertEqual(sections["recent"][2].id, "last_human")

        # Check content of historical (initial user input before tool sequence)
        self.assertEqual(len(sections["historical"]), 1)
        self.assertIsNone(sections["historical"][0].id)  # Initial user input


# Mock utilities

def create_mock_embeddings_response(
    count: int,
    dimension: int = 1536,
    ) -> List[List[float]]:
    """Create mock embeddings for testing."""
    import random
    embeddings = []
    for _ in range(count):
            # Generate random normalized vector
            vec = [random.random() for _ in range(dimension)]
            # Normalize
            magnitude = sum(x**2 for x in vec) ** 0.5
            vec = [x / magnitude for x in vec]
            embeddings.append(vec)
    return embeddings


def create_mock_weaviate_client() -> Mock:
    """Create mock Weaviate client for testing."""
    client = Mock()
    client.connect = AsyncMock()
    client.close = AsyncMock()
    client.setup_schema = AsyncMock()
    client.store_thread_message_chunk = AsyncMock()
    client.query_thread_messages = AsyncMock(return_value=[])
    return client


def create_mock_openai_client() -> Mock:
    """Create mock OpenAI client for testing."""
    client = Mock()

    # Mock embeddings
    embeddings_response = Mock()
    embeddings_response.data = []

    client.embeddings = Mock()
    client.embeddings.create = AsyncMock(return_value=embeddings_response)

    return client
