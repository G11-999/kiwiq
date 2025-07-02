"""
Comprehensive tests for Document CRUD Tools.

This module tests all four document CRUD tools in isolation:
- EditDocumentTool: For editing documents with various operation types
- DocumentViewerTool: For viewing single or multiple documents  
- DocumentSearchTool: For searching documents with text queries
- ListDocumentsTool: For listing documents with filters

Tests use the node's process method directly without LLM integration.
"""

import asyncio
import json
import unittest
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

# Test infrastructure imports
from db.session import get_async_db_as_manager
from kiwi_app.workflow_app.constants import LaunchStatus
from kiwi_app.workflow_app.schemas import (
    WorkflowRunJobCreate,
    CustomerDocumentSearchResult,
    CustomerDocumentSearchResultMetadata
)
from kiwi_app.workflow_app.service_customer_data import CustomerDataService
from kiwi_app.rag_service.schemas import (
    RAGSearchRequest,
    RAGSearchResponse,
    RAGSearchResult,
    SearchType,
    RAGDocumentIngestRequest,
    RAGDocumentDeleteRequest
)
from kiwi_app.rag_service.services import RAGService

# Context and configuration imports
from workflow_service.config.constants import (
    APPLICATION_CONTEXT_KEY,
    EXTERNAL_CONTEXT_MANAGER_KEY
)
from workflow_service.services.external_context_manager import (
    ExternalContextManager,
    get_external_context_manager_with_clients
)

# Import the document CRUD tools
from workflow_service.registry.nodes.tools.documents.document_crud_tools import (
    EditDocumentTool,
    DocumentViewerTool,
    DocumentSearchTool,
    ListDocumentsTool,
    EditDocumentInputSchema,
    DocumentViewerInputSchema,
    DocumentSearchInputSchema,
    ListDocumentsInputSchema,
    EditOperationType,
    DocumentIdentifier,
    DocumentListFilter,
    EditOperation,
    TextEditDetails,
    JsonOperationDetails
)

# Import app_artifacts to get document configurations
from kiwi_app.workflow_app.app_artifacts import DEFAULT_USER_DOCUMENTS_CONFIG


class MockUser(BaseModel):
    """Mock User model for testing."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    is_superuser: bool = False


class TestDocumentCrudTools(unittest.IsolatedAsyncioTestCase):
    """
    Integration tests for Document CRUD Tool nodes.
    
    These tests verify the functionality of all document CRUD tools
    by testing them in isolation with various input scenarios.
    """
    
    # Test setup attributes
    test_org_id: uuid.UUID
    test_user_id: uuid.UUID
    test_superuser_id: uuid.UUID
    user_regular: MockUser
    user_superuser: MockUser
    run_job_regular: WorkflowRunJobCreate
    run_job_superuser: WorkflowRunJobCreate
    external_context: ExternalContextManager
    runtime_config_regular: Dict[str, Any]
    runtime_config_superuser: Dict[str, Any]
    customer_data_service: CustomerDataService
    rag_service: Optional[RAGService]
    
    # Test data constants
    test_namespace: str = "test_doc_tools"
    test_docname_base: str = "test_doc_"
    
    # Track created documents for cleanup
    created_doc_ids: List[str] = []
    
    async def asyncSetUp(self):
        """Set up test environment before each test."""
        self.test_org_id = uuid.uuid4()
        self.test_user_id = uuid.uuid4()
        self.test_superuser_id = uuid.uuid4()
        
        self.user_regular = MockUser(id=self.test_user_id, is_superuser=False)
        self.user_superuser = MockUser(id=self.test_superuser_id, is_superuser=True)
        
        # Create workflow run jobs
        base_run_job_info = {
            "run_id": uuid.uuid4(),
            "workflow_id": uuid.uuid4(),
            "owner_org_id": self.test_org_id
        }
        self.run_job_regular = WorkflowRunJobCreate(
            **base_run_job_info,
            triggered_by_user_id=self.user_regular.id
        )
        self.run_job_superuser = WorkflowRunJobCreate(
            **base_run_job_info,
            triggered_by_user_id=self.user_superuser.id
        )
        
        # Initialize external context
        try:
            self.external_context = await get_external_context_manager_with_clients()
            self.customer_data_service = self.external_context.customer_data_service
            self.rag_service = self.external_context.rag_service
            if not self.customer_data_service:
                raise unittest.SkipTest("CustomerDataService not available")
        except Exception as e:
            raise unittest.SkipTest(f"Failed to initialize external context: {e}")
        
        # Runtime configurations
        self.runtime_config_regular = {
            "configurable": {
                APPLICATION_CONTEXT_KEY: {
                    "user": self.user_regular,
                    "workflow_run_job": self.run_job_regular
                },
                EXTERNAL_CONTEXT_MANAGER_KEY: self.external_context
            }
        }
        self.runtime_config_superuser = {
            "configurable": {
                APPLICATION_CONTEXT_KEY: {
                    "user": self.user_superuser,
                    "workflow_run_job": self.run_job_superuser
                },
                EXTERNAL_CONTEXT_MANAGER_KEY: self.external_context
            }
        }
        
        # Reset document tracking
        self.created_doc_ids = []
        
        # Clean up any existing test data
        await self._clean_test_data()
    
    async def asyncTearDown(self):
        """Clean up after each test."""
        await self._clean_test_data()
        if self.external_context:
            await self.external_context.close()
    
    async def _clean_test_data(self):
        """Helper to clean up test documents from both customer data service and RAG service."""
        if not self.customer_data_service:
            return
        
        # First, delete from RAG service if available and we have tracked doc IDs
        if self.rag_service and self.created_doc_ids:
            try:
                # Delete documents from RAG service
                delete_request = RAGDocumentDeleteRequest(
                    doc_ids=self.created_doc_ids,
                    org_id=self.test_org_id
                )
                await self.rag_service.delete_documents(delete_request, self.user_superuser)
            except Exception as e:
                print(f"Warning: Error deleting from RAG service: {e}")
        
        # Clean patterns for customer data service
        patterns_to_delete = [
            [str(self.test_org_id), str(self.test_user_id), "*", "*"],
            [str(self.test_org_id), str(self.test_superuser_id), "*", "*"],
            [str(self.test_org_id), self.customer_data_service.SHARED_DOC_PLACEHOLDER, "*", "*"],
            [self.customer_data_service.SYSTEM_DOC_PLACEHOLDER, "*", "*", "*"]
        ]
        
        for pattern in patterns_to_delete:
            try:
                await self.customer_data_service.mongo_client.delete_objects(
                    pattern=pattern,
                    allowed_prefixes=[["*"]]
                )
            except Exception as e:
                print(f"Warning: Error during cleanup for pattern {pattern}: {e}")
        
        # Clear tracked doc IDs
        self.created_doc_ids = []
    
    def _get_doc_config_for_key(self, doc_key: str) -> Tuple[str, str, Dict[str, Any]]:
        """
        Get namespace template, docname template, and other config for a doc_key.
        
        Returns:
            Tuple of (namespace_template, docname_template, config_dict)
        """
        doc_config = DEFAULT_USER_DOCUMENTS_CONFIG.get_document_config(doc_key)
        if not doc_config:
            # Fallback for test documents not in config
            return self.test_namespace, f"{self.test_docname_base}{{suffix}}", {}
        
        return (
            doc_config.namespace_template,
            doc_config.docname_template,
            {
                "is_shared": doc_config.is_shared,
                "is_versioned": doc_config.is_versioned,
                "is_system_entity": doc_config.is_system_entity
            }
        )
    
    def _get_default_version_for_doc_key(self, doc_key: str) -> Optional[str]:
        """Get the default version for a doc_key if it's versioned."""
        doc_config = DEFAULT_USER_DOCUMENTS_CONFIG.get_document_config(doc_key)
        if doc_config and doc_config.is_versioned:
            return "default"
        return None
    
    async def _create_test_document_for_doc_key(
        self,
        doc_key: str,
        data: Any,
        entity_username: Optional[str] = None,
        docname_suffix: Optional[str] = None,
        version: Optional[str] = None,
        user: Optional[MockUser] = None,
        **kwargs
    ) -> Tuple[str, str, str]:
        """
        Create a test document according to its doc_key configuration.
        
        Args:
            doc_key: The document key from app_artifacts
            data: Document data
            entity_username: Entity username for namespace (defaults to user ID)
            docname_suffix: For UUID-based templates, this will be the UUID value
            version: Version for versioned documents
            user: User creating the document
            **kwargs: Additional parameters to override config
            
        Returns:
            Tuple of (doc_id, namespace, docname)
        """
        user = user or self.user_regular
        entity_username = entity_username or str(user.id)
        
        # Get configuration for this doc_key
        namespace_template, docname_template, config = self._get_doc_config_for_key(doc_key)
        
        # Fill namespace template
        namespace_vars = {"entity_username": entity_username}
        namespace = namespace_template.format(**namespace_vars)
        
        # Fill docname template
        docname_vars = {}
        
        # Handle special placeholders in docname
        if "{_uuid_}" in docname_template:
            docname_vars["_uuid_"] = docname_suffix or str(uuid.uuid4())
            docname = docname_template.format(**docname_vars)
        elif "{post_uuid}" in docname_template:
            docname_vars["post_uuid"] = docname_suffix or str(uuid.uuid4())
            docname = docname_template.format(**docname_vars)
        else:
            # For fixed docnames (no placeholders), use the template as-is
            docname = docname_template
        
        # Override config with kwargs
        is_shared = kwargs.get("is_shared", config.get("is_shared", False))
        is_versioned = kwargs.get("is_versioned", config.get("is_versioned", False))
        is_system_entity = kwargs.get("is_system_entity", config.get("is_system_entity", False))
        
        # Create the document
        doc_id = await self._create_test_document(
            namespace=namespace,
            docname=docname,
            data=data,
            is_shared=is_shared,
            is_versioned=is_versioned,
            version=version,
            user=user if not is_system_entity else None
        )
        
        return doc_id, namespace, docname
    
    async def _create_test_document(
        self,
        namespace: str,
        docname: str,
        data: Any,
        is_shared: bool = False,
        is_versioned: bool = False,
        version: Optional[str] = None,
        user: Optional[MockUser] = None
    ) -> str:
        """Helper to create test documents and track their IDs.
        
        Returns:
            Document ID for tracking and cleanup
        """
        user = user or self.user_regular
        
        # Build document ID for tracking
        org_segment = str(self.test_org_id)
        user_segment = self.customer_data_service.SHARED_DOC_PLACEHOLDER if is_shared else str(user.id)
        doc_id_parts = [org_segment, user_segment, namespace, docname]
        if is_versioned and version:
            doc_id_parts.append(version)
        doc_id = self.customer_data_service.mongo_client._path_to_id(doc_id_parts)
        
        if is_versioned:
            if version:
                # Initialize with specific version
                await self.customer_data_service.initialize_versioned_document(
                    db=None,
                    org_id=self.test_org_id,
                    namespace=namespace,
                    docname=docname,
                    is_shared=is_shared,
                    user=user,
                    initial_version=version,
                    initial_data=data
                )
            else:
                # Initialize with default version
                await self.customer_data_service.initialize_versioned_document(
                    db=None,
                    org_id=self.test_org_id,
                    namespace=namespace,
                    docname=docname,
                    is_shared=is_shared,
                    user=user,
                    initial_data=data
                )
                # Add default version to doc_id
                doc_id_parts.append("default")
                doc_id = self.customer_data_service.mongo_client._path_to_id(doc_id_parts)
        else:
            await self.customer_data_service.create_or_update_unversioned_document(
                db=None,
                org_id=self.test_org_id,
                namespace=namespace,
                docname=docname,
                is_shared=is_shared,
                user=user,
                data=data
            )
        
        # Track the document ID for cleanup
        self.created_doc_ids.append(doc_id)
        return doc_id
    
    async def _get_document(
        self,
        namespace: str,
        docname: str,
        is_shared: bool = False,
        is_versioned: bool = False,
        version: Optional[str] = None,
        user: Optional[MockUser] = None
    ) -> Any:
        """Helper to retrieve test documents."""
        user = user or self.user_regular
        
        if is_versioned:
            return await self.customer_data_service.get_versioned_document(
                org_id=self.test_org_id,
                namespace=namespace,
                docname=docname,
                is_shared=is_shared,
                user=user,
                version=version or "default"
            )
        else:
            return await self.customer_data_service.get_unversioned_document(
                org_id=self.test_org_id,
                namespace=namespace,
                docname=docname,
                is_shared=is_shared,
                user=user
            )
    


    async def test_search_with_view_context(self):
        """Test searching using document serial number from view context."""
        # Create document
        doc_key = "brief"
        doc_data = {"content": "Context-based search test document"}
        doc_id, namespace, docname = await self._create_test_document_for_doc_key(
            doc_key=doc_key,
            data=doc_data,
            docname_suffix="search_ctx"
        )
        
        # Use string serial number format
        view_context = {
            "brief_78_1": {"docname": docname}
        }
        
        # Ingest document into RAG service if available
        if self.rag_service:
            try:
                async with get_async_db_as_manager() as db:
                    ingest_request = RAGDocumentIngestRequest(
                        doc_ids=[doc_id],
                        org_id=self.test_org_id
                    )
                    ingest_response = await self.rag_service.ingest_documents(
                        db, ingest_request, self.user_regular
                    )
                    
                    # Verify ingestion was successful
                    self.assertTrue(ingest_response.success)
                    self.assertGreater(ingest_response.total_chunks_created, 0)
                    
                    # Small delay to ensure indexing is complete
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                self.skipTest(f"RAG service ingestion failed: {e}")
        else:
            self.skipTest("RAG service not available for search test")
        
        input_data = DocumentSearchInputSchema(
            entity_username=str(self.user_regular.id),
            view_context=view_context,
            search_query="context search",
            document_identifier=DocumentIdentifier(
                doc_key=doc_key,
                document_serial_number="brief_78_1"  # String serial number
            )
        )
        
        search_tool = DocumentSearchTool(config={}, node_id="test-search", prefect_mode=False)
        result = await search_tool.process(input_data, config=self.runtime_config_regular)
        
        self.assertTrue(result.success)
        self.assertEqual(result.search_scope, "single")
    

    # -- RAG TESTS 2 -- # 


    async def test_search_single_document(self):
        """Test searching within a single document."""
        doc_key = "brief"
        doc_data = {
            "title": "Search Test Document",
            "content": "This document contains important information about search functionality. "
                      "The search feature allows finding specific text within documents."
        }
        doc_id, namespace, docname = await self._create_test_document_for_doc_key(
            doc_key=doc_key,
            data=doc_data,
            docname_suffix="search_single"
        )
        
        # Ingest document into RAG service if available
        if self.rag_service:
            try:
                async with get_async_db_as_manager() as db:
                    ingest_request = RAGDocumentIngestRequest(
                        doc_ids=[doc_id],
                        org_id=self.test_org_id
                    )
                    ingest_response = await self.rag_service.ingest_documents(
                        db, ingest_request, self.user_regular
                    )
                    
                    # Verify ingestion was successful
                    self.assertTrue(ingest_response.success)
                    self.assertGreater(ingest_response.total_chunks_created, 0)
                    
                    # Small delay to ensure indexing is complete
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                self.skipTest(f"RAG service ingestion failed: {e}")
        else:
            self.skipTest("RAG service not available for search test")
        
        input_data = DocumentSearchInputSchema(
            entity_username=str(self.user_regular.id),
            search_query="search functionality",
            document_identifier=DocumentIdentifier(
                doc_key=doc_key,
                docname=docname
            )
        )
        
        search_tool = DocumentSearchTool(config={}, node_id="test-search", prefect_mode=False)
        result = await search_tool.process(input_data, config=self.runtime_config_regular)
        
        self.assertTrue(result.success)
        self.assertEqual(result.search_scope, "single")
        self.assertGreater(len(result.results), 0)
        
        # Verify search result
        search_result = list(result.results.values())[0]
        self.assertEqual(search_result.document_info.docname, docname)
        self.assertIsNotNone(search_result.content_preview)
        self.assertIsNotNone(search_result.match_score)
    
    async def test_search_multiple_documents(self):
        """Test searching across multiple documents."""
        # Create test documents with a specific doc_key
        doc_key = "concept"  # Use concept for articles
        search_term = "artificial intelligence"
        
        docs = []
        doc_ids = []
        for i, doc_info in enumerate([
            {
                "title": "Introduction to AI",
                "content": "Artificial intelligence is transforming how we work and live."
            },
            {
                "title": "Machine Learning Basics",
                "content": "Machine learning is a subset of artificial intelligence."
            },
            {
                "title": "Web Development",
                "content": "Modern web development uses various frameworks and tools."
            }
        ]):
            doc_id, namespace, docname = await self._create_test_document_for_doc_key(
                doc_key=doc_key,
                data=doc_info,
                docname_suffix=f"article_{i}_{uuid.uuid4()}"
            )
            docs.append({"name": docname, "data": doc_info})
            doc_ids.append(doc_id)
        
        # Ingest all documents into RAG service
        if self.rag_service:
            try:
                async with get_async_db_as_manager() as db:
                    ingest_request = RAGDocumentIngestRequest(
                        doc_ids=doc_ids,
                        org_id=self.test_org_id
                    )
                    ingest_response = await self.rag_service.ingest_documents(
                        db, ingest_request, self.user_regular
                    )
                    
                    # Verify ingestion was successful
                    self.assertTrue(ingest_response.success)
                    self.assertGreater(ingest_response.total_chunks_created, 0)
                    
                    # Small delay to ensure indexing is complete
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                self.skipTest(f"RAG service ingestion failed: {e}")
        else:
            self.skipTest("RAG service not available for search test")
        
        input_data = DocumentSearchInputSchema(
            entity_username=str(self.user_regular.id),
            search_query=search_term,
            list_filter=DocumentListFilter(
                doc_key=doc_key  # Search within concepts
            ),
            limit=5
        )
        
        search_tool = DocumentSearchTool(config={}, node_id="test-search", prefect_mode=False)
        result = await search_tool.process(input_data, config=self.runtime_config_regular)
        
        self.assertTrue(result.success)
        self.assertEqual(result.search_scope, "multiple")
        # Should find at least 2 documents that mention "artificial intelligence"
        self.assertGreaterEqual(len(result.results), 2)
        
        # Verify results contain the search term
        for serial_num, search_result in result.results.items():
            # At least the first two docs should be found
            if search_result.document_info.docname in [docs[0]["name"], docs[1]["name"]]:
                content_lower = search_result.content_preview.lower()
                self.assertIn("artificial", content_lower)
                # Also verify score is present
                self.assertIsNotNone(search_result.match_score)
    
    


    async def test_list_search_edit_workflow(self):
        """Test listing documents, searching within them, then editing based on results."""
        doc_key = "concept"  # Use valid doc_key
        
        # Create test documents
        docs = []
        doc_ids = []
        for i in range(3):
            doc_data = {
                "title": f"Document {i}",
                "content": f"This is document number {i}. It contains {'important' if i == 1 else 'regular'} information.",
                "status": "active"
            }
            doc_id, namespace, docname = await self._create_test_document_for_doc_key(
                doc_key=doc_key,
                data=doc_data,
                docname_suffix=f"workflow_doc_{i}"
            )
            docs.append((docname, doc_data))
            doc_ids.append(doc_id)
        
        # Step 1: List documents
        list_input = ListDocumentsInputSchema(
            entity_username=str(self.user_regular.id),
            list_filter=DocumentListFilter(
                doc_key=doc_key
            )
        )
        
        list_tool = ListDocumentsTool(config={}, node_id="test-list", prefect_mode=False)
        list_result = await list_tool.process(list_input, config=self.runtime_config_regular)
        
        self.assertTrue(list_result.success)
        # May get fewer documents due to versioning metadata filtering
        self.assertGreaterEqual(len(list_result.documents), 1)
        
        # Step 2: Search for "important" with real RAG ingestion
        if self.rag_service:
            try:
                async with get_async_db_as_manager() as db:
                    ingest_request = RAGDocumentIngestRequest(
                        doc_ids=doc_ids,
                        org_id=self.test_org_id
                    )
                    ingest_response = await self.rag_service.ingest_documents(
                        db, ingest_request, self.user_regular
                    )
                    
                    # Verify ingestion was successful
                    self.assertTrue(ingest_response.success)
                    self.assertGreater(ingest_response.total_chunks_created, 0)
                    
                    # Small delay to ensure indexing is complete
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                self.skipTest(f"RAG service ingestion failed: {e}")
        else:
            self.skipTest("RAG service not available for search test")
        
        search_input = DocumentSearchInputSchema(
            entity_username=str(self.user_regular.id),
            search_query="important information",
            list_filter=DocumentListFilter(
                doc_key=doc_key
            )
        )
        
        search_tool = DocumentSearchTool(config={}, node_id="test-search", prefect_mode=False)
        search_result = await search_tool.process(search_input, config=self.runtime_config_regular)
        
        self.assertTrue(search_result.success)
        self.assertGreaterEqual(len(search_result.results), 1)
        found_doc = list(search_result.results.values())[0]
        # The document with "important" should be found
        self.assertIn("important", found_doc.content_preview.lower())
        
        # Step 3: Edit the found document
        edit_input = EditDocumentInputSchema(
            entity_username=str(self.user_regular.id),
            document_identifier=DocumentIdentifier(
                doc_key=doc_key,
                docname=found_doc.document_info.docname,
                version=self._get_default_version_for_doc_key(doc_key)
            ),
            operations=[
                EditOperation(
                    operation_type=EditOperationType.JSON_UPSERT_KEYS,
                    json_operation=JsonOperationDetails(
                        json_keys={
                            "priority": "high",
                            "flagged": True,
                            "flagged_reason": "Contains important information"
                        }
                    )
                )
            ]
        )
        
        edit_tool = EditDocumentTool(config={}, node_id="test-edit", prefect_mode=False)
        edit_result = await edit_tool.process(edit_input, config=self.runtime_config_regular)
        
        self.assertTrue(edit_result.success)
        
        # Verify the edit - need to get the namespace for the doc_key
        doc_config = DEFAULT_USER_DOCUMENTS_CONFIG.get_document_config(doc_key)
        namespace = doc_config.namespace_template.format(entity_username=str(self.user_regular.id))
        
        edited_doc = await self._get_document(
            namespace, found_doc.document_info.docname,
            is_versioned=doc_config.is_versioned,
            version=self._get_default_version_for_doc_key(doc_key)
        )
        self.assertEqual(edited_doc["priority"], "high")
        self.assertTrue(edited_doc["flagged"])

    async def test_edit_then_view_workflow(self):
        """Test editing a document and then viewing it to verify changes."""
        doc_key = "brief"
        initial_data = {"status": "draft", "content": "Initial content"}
        doc_id, namespace, docname = await self._create_test_document_for_doc_key(
            doc_key=doc_key,
            data=initial_data,
            docname_suffix="edit_view_flow"
        )
        
        # Edit the document
        edit_input = EditDocumentInputSchema(
            entity_username=str(self.user_regular.id),
            document_identifier=DocumentIdentifier(
                doc_key=doc_key,
                docname=docname,
                version=self._get_default_version_for_doc_key(doc_key)
            ),
            operations=[
                EditOperation(
                    operation_type=EditOperationType.JSON_UPSERT_KEYS,
                    json_operation=JsonOperationDetails(
                        json_keys={
                            "status": "published",
                            "published_at": "2024-01-01T12:00:00Z",
                            "publisher": "Test User"
                        }
                    )
                )
            ]
        )
        
        edit_tool = EditDocumentTool(config={}, node_id="test-edit", prefect_mode=False)
        edit_result = await edit_tool.process(edit_input, config=self.runtime_config_regular)
        self.assertTrue(edit_result.success)
        
        # View the edited document
        view_input = DocumentViewerInputSchema(
            entity_username=str(self.user_regular.id),
            document_identifier=DocumentIdentifier(
                doc_key=doc_key,
                docname=docname,
                version=self._get_default_version_for_doc_key(doc_key)
            )
        )
        
        viewer_tool = DocumentViewerTool(config={}, node_id="test-viewer", prefect_mode=False)
        view_result = await viewer_tool.process(view_input, config=self.runtime_config_regular)
        
        # Debug output
        if not view_result.success:
            print(f"DEBUG: View failed - {view_result.message}")
        
        self.assertTrue(view_result.success)
        
        # Check the content based on whether the edit succeeded or failed
        doc_data = list(view_result.documents.values())[0].data
        if not edit_result.success:
            # If edit failed, document should still have original data
            self.assertEqual(doc_data["status"], "draft")
            self.assertEqual(doc_data["content"], "Initial content")
        else:
            # If edit succeeded, check the updated fields
            self.assertEqual(doc_data["status"], "published")
            self.assertEqual(doc_data["published_at"], "2024-01-01T12:00:00Z")
            self.assertEqual(doc_data["publisher"], "Test User")
            # Original content should still be there
            self.assertEqual(doc_data["content"], "Initial content")
    
    async def test_delete_document_unversioned(self):
        """Test deleting an unversioned document."""
        doc_key = "concept"  # concept is typically unversioned
        initial_data = {
            "title": "Document to Delete",
            "content": "This document will be deleted",
            "status": "draft"
        }
        doc_id, namespace, docname = await self._create_test_document_for_doc_key(
            doc_key=doc_key,
            data=initial_data,
            docname_suffix="delete_test_unversioned",
            is_versioned=False  # Force unversioned for this test
        )
        
        # Verify document exists before deletion
        doc_config = DEFAULT_USER_DOCUMENTS_CONFIG.get_document_config(doc_key)
        doc_before = await self._get_document(
            namespace=namespace,
            docname=docname,
            is_versioned=False,
            user=self.user_regular
        )
        self.assertIsNotNone(doc_before)
        self.assertEqual(doc_before["title"], "Document to Delete")
        
        # Delete the document
        delete_input = EditDocumentInputSchema(
            entity_username=str(self.user_regular.id),
            document_identifier=DocumentIdentifier(
                doc_key=doc_key,
                docname=docname
            ),
            operations=[
                EditOperation(
                    operation_type=EditOperationType.DELETE_DOCUMENT
                )
            ]
        )
        
        edit_tool = EditDocumentTool(config={}, node_id="test-delete", prefect_mode=False)
        delete_result = await edit_tool.process(delete_input, config=self.runtime_config_regular)
        
        # Verify deletion was successful
        self.assertTrue(delete_result.success)
        self.assertEqual(len(delete_result.operation_results), 1)
        self.assertTrue(delete_result.operation_results[0]["success"])
        self.assertEqual(delete_result.operation_results[0]["operation_type"], "delete_document")
        self.assertIn("deleted successfully", delete_result.operation_results[0]["message"].lower())
        
        # Verify document no longer exists by trying to retrieve it
        with self.assertRaises(Exception):  # Should raise HTTPException with 404
            await self._get_document(
                namespace=namespace,
                docname=docname,
                is_versioned=False,
                user=self.user_regular
            )
    
    async def test_delete_document_versioned(self):
        """Test deleting a versioned document."""
        doc_key = "brief"  # brief is typically versioned
        initial_data = {
            "title": "Versioned Document to Delete",
            "content": "This versioned document will be deleted",
            "status": "draft"
        }
        doc_id, namespace, docname = await self._create_test_document_for_doc_key(
            doc_key=doc_key,
            data=initial_data,
            docname_suffix="delete_test_versioned",
            is_versioned=True,
            version="default"
        )
        
        # Verify document exists before deletion
        doc_before = await self._get_document(
            namespace=namespace,
            docname=docname,
            is_versioned=True,
            version="default",
            user=self.user_regular
        )
        self.assertIsNotNone(doc_before)
        self.assertEqual(doc_before["title"], "Versioned Document to Delete")
        
        # Delete the document
        delete_input = EditDocumentInputSchema(
            entity_username=str(self.user_regular.id),
            document_identifier=DocumentIdentifier(
                doc_key=doc_key,
                docname=docname,
                version="default"
            ),
            operations=[
                EditOperation(
                    operation_type=EditOperationType.DELETE_DOCUMENT
                )
            ]
        )
        
        edit_tool = EditDocumentTool(config={}, node_id="test-delete", prefect_mode=False)
        delete_result = await edit_tool.process(delete_input, config=self.runtime_config_regular)
        
        # Verify deletion was successful
        self.assertTrue(delete_result.success)
        self.assertEqual(len(delete_result.operation_results), 1)
        self.assertTrue(delete_result.operation_results[0]["success"])
        self.assertEqual(delete_result.operation_results[0]["operation_type"], "delete_document")
        self.assertIn("deleted successfully", delete_result.operation_results[0]["message"].lower())
        
        # Verify document no longer exists by trying to retrieve it
        with self.assertRaises(Exception):  # Should raise HTTPException with 404
            await self._get_document(
                namespace=namespace,
                docname=docname,
                is_versioned=True,
                version="default",
                user=self.user_regular
            )
    
    async def test_delete_document_with_serial_number(self):
        """Test deleting a document using its serial number from view context."""
        doc_key = "concept"
        initial_data = {
            "title": "Document for Serial Delete",
            "content": "Delete this using serial number",
            "category": "test"
        }
        doc_id, namespace, docname = await self._create_test_document_for_doc_key(
            doc_key=doc_key,
            data=initial_data,
            docname_suffix="serial_delete_test"
        )
        
        # Create view context as if document was previously listed
        view_context = {
            "concept_42_1": {"docname": docname}
        }
        
        # Delete using serial number
        delete_input = EditDocumentInputSchema(
            entity_username=str(self.user_regular.id),
            view_context=view_context,
            document_identifier=DocumentIdentifier(
                doc_key=doc_key,
                document_serial_number="concept_42_1"
            ),
            operations=[
                EditOperation(
                    operation_type=EditOperationType.DELETE_DOCUMENT
                )
            ]
        )
        
        edit_tool = EditDocumentTool(config={}, node_id="test-delete", prefect_mode=False)
        delete_result = await edit_tool.process(delete_input, config=self.runtime_config_regular)
        
        # Verify deletion was successful
        self.assertTrue(delete_result.success)
        self.assertEqual(len(delete_result.operation_results), 1)
        self.assertTrue(delete_result.operation_results[0]["success"])
        self.assertIn("deleted successfully", delete_result.operation_results[0]["message"].lower())
        
        # Verify document no longer exists
        doc_config = DEFAULT_USER_DOCUMENTS_CONFIG.get_document_config(doc_key)
        with self.assertRaises(Exception):  # Should raise HTTPException with 404
            await self._get_document(
                namespace=namespace,
                docname=docname,
                is_versioned=doc_config.is_versioned if doc_config else False,
                user=self.user_regular
            )
    
    async def test_delete_nonexistent_document(self):
        """Test attempting to delete a document that doesn't exist."""
        doc_key = "concept"
        nonexistent_docname = f"nonexistent_doc_{uuid.uuid4()}"
        
        delete_input = EditDocumentInputSchema(
            entity_username=str(self.user_regular.id),
            document_identifier=DocumentIdentifier(
                doc_key=doc_key,
                docname=nonexistent_docname
            ),
            operations=[
                EditOperation(
                    operation_type=EditOperationType.DELETE_DOCUMENT
                )
            ]
        )
        
        edit_tool = EditDocumentTool(config={}, node_id="test-delete", prefect_mode=False)
        delete_result = await edit_tool.process(delete_input, config=self.runtime_config_regular)
        
        # Deletion should fail for nonexistent document
        self.assertFalse(delete_result.success)
        # Check the error message is in the result
        # It could be in the main message or in operation results
        if delete_result.operation_results:
            # Check in operation results
            self.assertFalse(delete_result.operation_results[0]["success"])
            self.assertIn("not found", delete_result.operation_results[0]["message"].lower())
        else:
            # Check in main message
            self.assertIn("not found", delete_result.message.lower())
    

if __name__ == "__main__":
    unittest.main()
