"""
RAG Service for KiwiQ system.

This module provides the service layer for RAG (Retrieval Augmented Generation) operations.
It wraps existing services including WeaviateChunkClient, DocumentIngestionPipeline,
and CustomerDataService to provide comprehensive document search, ingestion, and deletion.
"""

import uuid
import time
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime, timezone
import asyncio
from functools import partial

from sqlalchemy.ext.asyncio import AsyncSession

from kiwi_app.auth.models import User
from kiwi_app.utils import get_kiwi_logger
from kiwi_app.workflow_app.service_customer_data import CustomerDataService
from kiwi_app.data_jobs.ingestion.ingestion_pipeline import (
    DocumentIngestionPipeline,
    ingest_single_document,
    ingest_multiple_documents
)
from weaviate_client.weaviate_client import WeaviateChunkClient, ChunkSchema
from kiwi_app.rag_service.schemas import (
    RAGSearchRequest, RAGSearchResponse, RAGSearchResult,
    RAGDocumentDeleteRequest, RAGDocumentDeleteResponse,
    RAGDocumentIngestRequest, RAGDocumentIngestResponse, RAGDocumentIngestResult,
    RAGStatusResponse, RAGDocumentInfo, RAGDocumentListRequest, RAGDocumentListResponse,
    RAGBulkDeleteRequest, RAGBulkIngestRequest, RAGBulkOperationResponse,
    RAGAdvancedSearchRequest, RAGAdvancedSearchResponse, RAGGroupedSearchResult,
    SearchType
)
from kiwi_app.workflow_app.constants import CustomerDataServiceConstants
from kiwi_app.rag_service.exceptions import RAGPermissionException
from global_config.logger import get_prefect_or_regular_python_logger

# Get logger for RAG operations
rag_logger = get_kiwi_logger(name="kiwi_app.rag_service")


class RAGService:
    """
    Service layer for RAG (Retrieval Augmented Generation) operations.
    
    This service provides a comprehensive interface for:
    - Searching documents using vector, keyword, and hybrid search
    - Managing document ingestion and reingestion
    - Deleting documents from the vector database
    - Enforcing proper permissions based on organization and user context
    
    Key Features:
    - Permission-aware operations respecting org/user boundaries
    - Document path conversion between MongoDB and Weaviate formats
    - Comprehensive error handling and logging
    - Support for both individual and bulk operations
    - Integration with existing ingestion pipeline and customer data services
    """
    
    def __init__(
        self,
        weaviate_client: WeaviateChunkClient,
        customer_data_service: CustomerDataService,
        ingestion_pipeline: Optional[DocumentIngestionPipeline] = None
    ):
        """
        Initialize the RAG service with required dependencies.
        
        Args:
            weaviate_client: Connected WeaviateChunkClient instance
            customer_data_service: CustomerDataService for document access
            ingestion_pipeline: Optional DocumentIngestionPipeline instance
        """
        self.logger = get_prefect_or_regular_python_logger(name="kiwi_app.rag_service", return_non_prefect_logger=False) or rag_logger
        self.weaviate_client = weaviate_client
        self.customer_data_service = customer_data_service
        self.ingestion_pipeline = ingestion_pipeline
        
        self.logger.info("RAG service initialized successfully")
    
    def _validate_user_permissions(
        self,
        user: User,
        org_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Basic permission validation - most validation is now handled by routers.
        
        Args:
            user: User making the request
            org_id: Optional organization ID filter (already validated by routers)
            user_id: Optional user ID filter (already validated by routers)
            
        Returns:
            Always returns (True, None) since routers handle validation
        """
        # Permission validation is now handled by the routers using existing permission checkers
        return True, None
    
    def _build_weaviate_filter(
        self,
        user: User,
        org_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        namespace_filter: Optional[str] = None,
        doc_name_filter: Optional[str] = None,
        version_filter: Optional[str] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        updated_after: Optional[datetime] = None,
        updated_before: Optional[datetime] = None,
        scheduled_after: Optional[datetime] = None,
        scheduled_before: Optional[datetime] = None,
        chunk_keys_contain: Optional[List[str]] = None,
        search_only_system_entities: bool = False,
        **kwargs
    ) -> Optional[Any]:
        """
        Build Weaviate filter based on user permissions and request parameters.
        
        Args:
            user: User making the request
            org_id: Optional organization ID filter
            user_id: Optional user ID filter
            namespace_filter: Optional namespace filter
            doc_name_filter: Optional document name filter
            version_filter: Optional version filter
            created_after: Optional created after date filter
            created_before: Optional created before date filter
            updated_after: Optional updated after date filter
            updated_before: Optional updated before date filter
            scheduled_after: Optional scheduled after date filter
            scheduled_before: Optional scheduled before date filter
            chunk_keys_contain: Optional chunk keys filter
            search_only_system_entities: Optional search only system entities filter
            **kwargs: Additional filter parameters
            
        Returns:
            Weaviate filter object or None
        """
        # Use the org_id and user_id as provided - validation is handled by routers
        effective_org_id = org_id
        effective_user_id = user_id
        
        # Build org_segment filter
        org_segment = None
        if effective_org_id:
            org_segment = str(effective_org_id)
        
        # Build user_segment filter
        user_segment = None
        if effective_user_id:
            user_segment = str(effective_user_id)
        
        if search_only_system_entities:
            org_segment = CustomerDataServiceConstants.SYSTEM_DOC_PLACEHOLDER
            user_segment = CustomerDataServiceConstants.SHARED_DOC_PLACEHOLDER
            if user.is_superuser:
                user_segment = None
        
        # Use the weaviate client's build_filter method
        kwargs = {
            "org_segment": org_segment,
            "user_segment": user_segment,
            "namespace": namespace_filter,
            "doc_name": doc_name_filter,
            "version": version_filter,
            "created_at_start": created_after,
            "created_at_end": created_before,
            "updated_at_start": updated_after,
            "updated_at_end": updated_before,
            "scheduled_date_start": scheduled_after,
            "scheduled_date_end": scheduled_before,
            "chunk_keys_contains_any": chunk_keys_contain
        }
        weaviate_filter = self.weaviate_client.build_filter(**kwargs)
        
        if user_segment and (not search_only_system_entities):
            kwargs["user_segment"] = CustomerDataServiceConstants.SHARED_DOC_PLACEHOLDER
            weaviate_filter = weaviate_filter | self.weaviate_client.build_filter(
                **kwargs
            )
        
        return weaviate_filter
    
    def _convert_weaviate_results(
        self,
        weaviate_results: List[Dict[str, Any]],
        include_vector: bool = False,
        include_chunk_keys: bool = True
    ) -> List[RAGSearchResult]:
        """
        Convert Weaviate search results to RAGSearchResult objects.
        
        Args:
            weaviate_results: Raw results from Weaviate
            include_vector: Whether to include vector embeddings
            include_chunk_keys: Whether to include chunk keys
            
        Returns:
            List of RAGSearchResult objects
        """
        results = []
        
        for result in weaviate_results:
            properties = result.get("properties", {})
            metadata = result.get("metadata", {})
            
            # Extract search relevance scores
            score = metadata.get("score")
            distance = metadata.get("distance")
            certainty = metadata.get("certainty")
            
            # Build RAGSearchResult
            search_result = RAGSearchResult(
                uuid=result.get("uuid", ""),
                doc_id=properties.get(ChunkSchema.DOC_ID, ""),
                org_segment=properties.get(ChunkSchema.ORG_SEGMENT, ""),
                user_segment=properties.get(ChunkSchema.USER_SEGMENT, ""),
                namespace=properties.get(ChunkSchema.NAMESPACE, ""),
                doc_name=properties.get(ChunkSchema.DOC_NAME, ""),
                version=properties.get(ChunkSchema.VERSION),
                chunk_no=properties.get(ChunkSchema.CHUNK_NO, 0),
                chunk_content=properties.get(ChunkSchema.CHUNK_CONTENT, ""),
                chunk_keys=properties.get(ChunkSchema.CHUNK_KEYS) if include_chunk_keys else None,
                created_at=self._parse_datetime(properties.get(ChunkSchema.CREATED_AT)),
                updated_at=self._parse_datetime(properties.get(ChunkSchema.UPDATED_AT)),
                scheduled_date=self._parse_datetime(properties.get(ChunkSchema.SCHEDULED_DATE)),
                score=score,
                distance=distance,
                certainty=certainty,
                vector=result.get("vector") if include_vector else None
            )
            
            results.append(search_result)
        
        return results
    
    def _parse_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse datetime string from Weaviate."""
        if not date_str:
            return None
        if isinstance(date_str, datetime):
            return date_str
        try:
            # Handle ISO format with Z suffix
            if date_str.endswith('Z'):
                date_str = date_str[:-1] + '+00:00'
            return datetime.fromisoformat(date_str)
        except (ValueError, TypeError):
            return None
    
    async def search_documents(
        self,
        search_request: RAGSearchRequest,
        user: User,
    ) -> RAGSearchResponse:
        """
        Search documents using vector, keyword, or hybrid search.
        
        Args:
            search_request: Search request parameters
            user: User making the request
            
        Returns:
            RAGSearchResponse with search results
            
        Raises:
            RAGPermissionException: If user lacks required permissions
            ValueError: If search parameters are invalid
        """
        start_time = time.time()
        
        # Validate permissions
        is_valid, error_msg = self._validate_user_permissions(
            user, search_request.org_id, search_request.user_id
        )
        if not is_valid:
            raise RAGPermissionException(error_msg)
        
        # Build Weaviate filter
        weaviate_filter = self._build_weaviate_filter(
            user=user,
            org_id=search_request.org_id,
            user_id=search_request.user_id,
            namespace_filter=search_request.namespace_filter,
            doc_name_filter=search_request.doc_name_filter,
            version_filter=search_request.version_filter,
            created_after=search_request.created_after,
            created_before=search_request.created_before,
            updated_after=search_request.updated_after,
            updated_before=search_request.updated_before,
            scheduled_after=search_request.scheduled_after,
            scheduled_before=search_request.scheduled_before,
            chunk_keys_contain=search_request.chunk_keys_contain,
            search_only_system_entities=search_request.search_only_system_entities,
        )
        
        try:
            # Execute search based on type
            if search_request.search_type == SearchType.VECTOR:
                weaviate_results = await self.weaviate_client.vector_search(
                    query_text=search_request.query,
                    limit=search_request.limit,
                    offset=search_request.offset,
                    where_filter=weaviate_filter,
                    include_vector=search_request.include_vector
                )
            elif search_request.search_type == SearchType.KEYWORD:
                weaviate_results = await self.weaviate_client.keyword_search(
                    query=search_request.query,
                    limit=search_request.limit,
                    offset=search_request.offset,
                    where_filter=weaviate_filter
                )
            else:  # HYBRID
                weaviate_results = await self.weaviate_client.hybrid_search(
                    query=search_request.query,
                    limit=search_request.limit,
                    offset=search_request.offset,
                    alpha=search_request.alpha,
                    where_filter=weaviate_filter
                )
            
            # Convert results
            results = self._convert_weaviate_results(
                weaviate_results,
                include_vector=search_request.include_vector,
                include_chunk_keys=search_request.include_chunk_keys
            )
            
            # Calculate execution time
            execution_time_ms = (time.time() - start_time) * 1000
            
            # Build search parameters for response
            search_params = {
                "query": search_request.query,
                "search_type": search_request.search_type.value,
                "limit": search_request.limit,
                "offset": search_request.offset,
                "alpha": search_request.alpha,
                "filters_applied": bool(weaviate_filter)
            }
            
            response = RAGSearchResponse(
                results=results,
                total_results=len(results),
                search_params=search_params,
                execution_time_ms=execution_time_ms
            )
            
            self.logger.info(
                f"User {user.id} performed {search_request.search_type.value} search: "
                f"'{search_request.query}' -> {len(results)} results"
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error in document search: {e}", exc_info=True)
            raise
    
    async def delete_documents(
        self,
        delete_request: RAGDocumentDeleteRequest,
        user: User
    ) -> RAGDocumentDeleteResponse:
        """
        Delete documents from the vector database by document IDs.
        
        Args:
            delete_request: Delete request parameters
            user: User making the request
            
        Returns:
            RAGDocumentDeleteResponse with deletion results
            
        Raises:
            RAGPermissionException: If user lacks required permissions
        """
        # Validate permissions
        is_valid, error_msg = self._validate_user_permissions(
            user, delete_request.org_id, delete_request.user_id
        )
        if not is_valid:
            raise RAGPermissionException(error_msg)
        
        deleted_doc_ids = []
        failed_doc_ids = []
        total_chunks_deleted = 0
        errors = []
        
        try:
            # Validate document access permissions for each doc_id
            valid_doc_ids = []
            
            for doc_id in delete_request.doc_ids:
                try:
                    # Convert doc_id to path and validate permissions
                    if await self._validate_document_access(doc_id, user, delete_request.org_id, delete_request.user_id):
                        valid_doc_ids.append(doc_id)
                    else:
                        failed_doc_ids.append(doc_id)
                        errors.append(f"Access denied for document {doc_id}")
                except Exception as e:
                    failed_doc_ids.append(doc_id)
                    errors.append(f"Error validating access for document {doc_id}: {str(e)}")
            
            # Delete valid documents from Weaviate
            if valid_doc_ids:
                try:
                    deleted_count, failed, matched, successful = await self.weaviate_client.delete_by_doc_id(valid_doc_ids)
                    total_chunks_deleted = matched
                    deleted_doc_ids = valid_doc_ids  # Assume all valid docs were processed
                    
                    if failed > 0:
                        errors.append(f"Weaviate deletion had {failed} failures")
                        
                except Exception as e:
                    errors.append(f"Weaviate deletion error: {str(e)}")
                    failed_doc_ids.extend(valid_doc_ids)
            
            response = RAGDocumentDeleteResponse(
                success=len(deleted_doc_ids) > 0 and len(errors) == 0,
                deleted_doc_ids=deleted_doc_ids,
                failed_doc_ids=failed_doc_ids,
                total_chunks_deleted=total_chunks_deleted,
                errors=errors
            )
            
            self.logger.info(
                f"User {user.id} deleted documents: {len(deleted_doc_ids)} successful, "
                f"{len(failed_doc_ids)} failed, {total_chunks_deleted} chunks deleted"
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error in document deletion: {e}", exc_info=True)
            raise
    
    async def ingest_documents(
        self,
        db: AsyncSession,
        ingest_request: RAGDocumentIngestRequest,
        user: User
    ) -> RAGDocumentIngestResponse:
        """
        Reingest documents into the vector database.
        
        Args:
            db: Database session
            ingest_request: Ingest request parameters
            user: User making the request
            
        Returns:
            RAGDocumentIngestResponse with ingestion results
            
        Raises:
            RAGPermissionException: If user lacks required permissions
        """
        # Validate permissions
        is_valid, error_msg = self._validate_user_permissions(
            user, ingest_request.org_id, ingest_request.user_id
        )
        if not is_valid:
            raise RAGPermissionException(error_msg)
        
        results = []
        total_chunks_created = 0
        total_chunks_deleted = 0
        errors = []
        
        try:
            # First, validate access and fetch all documents
            valid_documents = []
            doc_id_to_document = {}
            
            for doc_id in ingest_request.doc_ids:
                try:
                    # Validate document access
                    if not await self._validate_document_access(doc_id, user, ingest_request.org_id, ingest_request.user_id):
                        results.append(RAGDocumentIngestResult(
                            doc_id=doc_id,
                            success=False,
                            chunks_created=0,
                            chunks_deleted=0,
                            error_message="Access denied"
                        ))
                        continue
                    
                    # Fetch document from MongoDB
                    document = await self._fetch_document_by_id(db, doc_id, user, ingest_request.org_id)
                    if not document:
                        results.append(RAGDocumentIngestResult(
                            doc_id=doc_id,
                            success=False,
                            chunks_created=0,
                            chunks_deleted=0,
                            error_message="Document not found in MongoDB"
                        ))
                        continue
                    
                    # Add to valid documents for batch processing
                    valid_documents.append(document)
                    doc_id_to_document[doc_id] = document
                    
                except Exception as e:
                    error_msg = f"Error preparing document {doc_id}: {str(e)}"
                    errors.append(error_msg)
                    results.append(RAGDocumentIngestResult(
                        doc_id=doc_id,
                        success=False,
                        chunks_created=0,
                        chunks_deleted=0,
                        error_message=str(e)
                    ))
            
            # Process all valid documents at once using the pipeline
            if valid_documents:
                try:
                    ingestion_result = await self.ingestion_pipeline.ingest_documents(
                        documents=valid_documents,
                        generate_vectors=ingest_request.generate_vectors
                    )
                    
                    # Process results for each document
                    for doc_id, document in doc_id_to_document.items():
                        if doc_id in ingestion_result:
                            chunks_created, chunk_uuids = ingestion_result[doc_id]
                            results.append(RAGDocumentIngestResult(
                                doc_id=doc_id,
                                success=chunks_created > 0,
                                chunks_created=chunks_created,
                                chunks_deleted=0,  # Pipeline handles reingest automatically
                                error_message=None if chunks_created > 0 else "No chunks created"
                            ))
                            total_chunks_created += chunks_created
                        else:
                            results.append(RAGDocumentIngestResult(
                                doc_id=doc_id,
                                success=False,
                                chunks_created=0,
                                chunks_deleted=0,
                                error_message="Document not processed by ingestion pipeline"
                            ))
                            
                except Exception as e:
                    error_msg = f"Error in batch ingestion: {str(e)}"
                    errors.append(error_msg)
                    self.logger.error(f"Batch ingestion failed: {e}", exc_info=True)
                    
                    # Mark all valid documents as failed
                    for doc_id in doc_id_to_document.keys():
                        # Skip if already processed in results
                        if not any(r.doc_id == doc_id for r in results):
                            results.append(RAGDocumentIngestResult(
                                doc_id=doc_id,
                                success=False,
                                chunks_created=0,
                                chunks_deleted=0,
                                error_message=f"Batch ingestion failed: {str(e)}"
                            ))
            
            successful_results = [r for r in results if r.success]
            
            response = RAGDocumentIngestResponse(
                success=len(successful_results) > 0,
                results=results,
                total_documents_processed=len(ingest_request.doc_ids),
                total_chunks_created=total_chunks_created,
                total_chunks_deleted=total_chunks_deleted,
                errors=errors
            )
            
            self.logger.info(
                f"User {user.id} ingested documents: {len(successful_results)}/{len(ingest_request.doc_ids)} successful, "
                f"{total_chunks_created} chunks created"
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error in document ingestion: {e}", exc_info=True)
            raise
    
    async def get_status(self) -> RAGStatusResponse:
        """
        Get RAG service status and statistics.
        
        Returns:
            RAGStatusResponse with service status
        """
        try:
            # Check Weaviate connection
            weaviate_connected = await self.weaviate_client.client.is_ready() if self.weaviate_client.client else False
            
            # Get collection statistics
            collection_info = {}
            total_chunks = 0
            total_documents = 0
            
            if weaviate_connected:
                try:
                    # Get collection info
                    collection = self.weaviate_client.client.collections.get(self.weaviate_client.collection_name)
                    aggregate_result = await collection.aggregate.over_all()
                    
                    if hasattr(aggregate_result, 'total_count'):
                        total_chunks = aggregate_result.total_count
                    
                    # Estimate unique documents by aggregating unique doc_ids
                    # This is an approximation since Weaviate doesn't have exact count distinct
                    total_documents = max(1, total_chunks // 5)  # Rough estimate
                    
                    collection_info = {
                        "name": self.weaviate_client.collection_name,
                        "vectorizer": self.weaviate_client.vectorizer,
                        "total_objects": total_chunks
                    }
                    
                except Exception as e:
                    self.logger.warning(f"Error getting collection statistics: {e}")
                    collection_info = {"error": str(e)}
            
            response = RAGStatusResponse(
                weaviate_connected=weaviate_connected,
                total_chunks=total_chunks,
                total_documents=total_documents,
                collection_info=collection_info,
                last_updated=datetime.now(timezone.utc)
            )
            
            self.logger.info("RAG service status retrieved successfully")
            return response
            
        except Exception as e:
            self.logger.error(f"Error getting RAG service status: {e}", exc_info=True)
            raise
    
    async def _validate_document_access(
        self,
        doc_id: str,
        user: User,
        org_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None
    ) -> bool:
        """
        Validate that user has access to a specific document.
        
        Args:
            doc_id: Document ID to validate
            user: User making the request
            org_id: Optional organization ID filter
            user_id: Optional user ID filter
            
        Returns:
            True if user has access, False otherwise
        """
        try:
            if user.is_superuser:
                return True

            # Convert doc_id to path segments
            path_segments = self.customer_data_service.mongo_client._id_to_path(doc_id)
            
            if len(path_segments) < 2:
                return False
            
            # Extract org and user segments from path
            doc_org_segment = path_segments[0]
            doc_user_segment = path_segments[1]

            if doc_org_segment == self.customer_data_service.SYSTEM_DOC_PLACEHOLDER:
                # if not user.is_superuser:
                return False
            
            # Parse org_id from org segment
            doc_org_id = uuid.UUID(doc_org_segment)

            if doc_org_id != org_id:
                return False
            
            # Parse user_id from user segment
            if doc_user_segment == self.customer_data_service.SHARED_DOC_PLACEHOLDER:
                return True
            
            doc_user_id = uuid.UUID(doc_user_segment)
            
            return doc_user_id == user.id
            
        except Exception as e:
            self.logger.error(f"Error validating document access for {doc_id}: {e}")
            return False
    
    async def _fetch_document_by_id(
        self,
        db: AsyncSession,
        doc_id: str,
        user: User,
        org_id: Optional[uuid.UUID] = None
    ) -> Optional[Any]:
        """
        Fetch document from MongoDB by document ID.
        
        Args:
            db: Database session
            doc_id: Document ID to fetch
            user: User making the request
            org_id: Optional organization ID for permissions

        Returns:
            CustomerDocumentSearchResult object or None
        """
        try:
            # Convert doc_id to path
            path_segments = self.customer_data_service.mongo_client._id_to_path(doc_id)
            
            if len(path_segments) < 4:
                return None
            
            # Extract path components
            org_segment, user_segment, namespace, docname = path_segments[:4]
            version = path_segments[4] if len(path_segments) > 4 else None
            
            # Determine if shared and system
            is_shared = user_segment == self.customer_data_service.SHARED_DOC_PLACEHOLDER
            is_system_entity = org_segment == self.customer_data_service.SYSTEM_DOC_PLACEHOLDER
            
            # Parse org_id
            if not is_system_entity:
                org_id = uuid.UUID(org_segment)
            
            # Parse user_id for on_behalf_of_user_id
            on_behalf_of_user_id = None
            if not is_shared and user.is_superuser:
                on_behalf_of_user_id = uuid.UUID(user_segment)
            
            # Fetch document using customer data service
            # org_id is already validated at router level, use as-is
            document = await self.customer_data_service.get_document(
                org_id=org_id,
                namespace=namespace,
                docname=docname,
                is_shared=is_shared,
                user=user,
                version=version,
                on_behalf_of_user_id=on_behalf_of_user_id,
                is_system_entity=is_system_entity,
                is_called_from_workflow=True  # Allow system access
            )

            if isinstance(document.document_contents, dict) and "raw_content" in document.document_contents and "source_filename" in document.document_contents:
                # "File uploaded as raw content. Use `/download` endpoint to download it."
                # this is a raw content document, skip!
                return

            return document
            # document_data = document.document_contents
            
            # if version:
            #     # Versioned document
            #     document_data = await self.customer_data_service.get_versioned_document(
            #         org_id=org_id,
            #         namespace=namespace,
            #         docname=docname,
            #         is_shared=is_shared,
            #         user=user,
            #         version=version,
            #         on_behalf_of_user_id=on_behalf_of_user_id,
            #         is_system_entity=is_system_entity,
            #         is_called_from_workflow=True  # Allow system access
            #     )
            # else:
            #     # Unversioned document
            #     document_data = await self.customer_data_service.get_unversioned_document(
            #         org_id=org_id,
            #         namespace=namespace,
            #         docname=docname,
            #         is_shared=is_shared,
            #         user=user,
            #         on_behalf_of_user_id=on_behalf_of_user_id,
            #         is_system_entity=is_system_entity,
            #         is_called_from_workflow=True  # Allow system access
            #     )
            
            # if document_data:
            #     # Create a mock CustomerDocumentSearchResult for ingestion
            #     from kiwi_app.workflow_app.schemas import (
            #         CustomerDocumentSearchResult,
            #         CustomerDocumentSearchResultMetadata
            #     )
                
            #     metadata = CustomerDocumentSearchResultMetadata(
            #         id=doc_id,
            #         org_id=org_id,
            #         user_id_or_shared_placeholder=user_segment,
            #         namespace=namespace,
            #         docname=docname,
            #         version=version,
            #         is_versioned=version is not None,
            #         is_shared=is_shared,
            #         is_system_entity=is_system_entity,
            #         is_versioning_metadata=False
            #     )
                
            #     return CustomerDocumentSearchResult(
            #         metadata=metadata,
            #         document_contents=document_data
            #     )
            
            # return None
            
        except Exception as e:
            self.logger.error(f"Error fetching document {doc_id}: {e}", exc_info=True)
            return None
    
    async def list_documents(
        self,
        list_request: RAGDocumentListRequest,
        user: User
    ) -> RAGDocumentListResponse:
        """
        List documents in the vector database with filtering and pagination.
        
        Args:
            list_request: Document list request parameters
            user: User making the request
            
        Returns:
            RAGDocumentListResponse with document list
        """
        # Validate permissions
        is_valid, error_msg = self._validate_user_permissions(
            user, list_request.org_id, list_request.user_id
        )
        if not is_valid:
            raise RAGPermissionException(error_msg)
        
        # Build Weaviate filter
        weaviate_filter = self._build_weaviate_filter(
            user=user,
            org_id=list_request.org_id,
            user_id=list_request.user_id,
            namespace_filter=list_request.namespace_filter,
            doc_name_filter=list_request.doc_name_filter
        )
        
        try:
            # Query Weaviate for documents
            # This is a simplified implementation - in practice you'd want proper aggregation
            search_results = await self.weaviate_client.vector_search(
                query_text="*",  # Wildcard search
                limit=list_request.limit + list_request.skip,
                offset=0,  # Apply offset at the aggregation level instead
                where_filter=weaviate_filter
            )
            
            # Group by document ID
            docs_by_id = {}
            for result in search_results:
                properties = result.get("properties", {})
                doc_id = properties.get("doc_id", "")
                
                if doc_id not in docs_by_id:
                    docs_by_id[doc_id] = RAGDocumentInfo(
                        doc_id=doc_id,
                        org_segment=properties.get("org_segment", ""),
                        user_segment=properties.get("user_segment", ""),
                        namespace=properties.get("namespace", ""),
                        doc_name=properties.get("doc_name", ""),
                        version=properties.get("version"),
                        chunk_count=0,
                        created_at=self._parse_datetime(properties.get("created_at")),
                        updated_at=self._parse_datetime(properties.get("updated_at"))
                    )
                
                docs_by_id[doc_id].chunk_count += 1
            
            # Apply pagination
            documents = list(docs_by_id.values())[list_request.skip:list_request.skip + list_request.limit]
            
            response = RAGDocumentListResponse(
                documents=documents,
                total_count=len(docs_by_id),
                filters_applied={
                    "namespace_filter": list_request.namespace_filter,
                    "doc_name_filter": list_request.doc_name_filter,
                    "org_id": str(list_request.org_id) if list_request.org_id else None,
                    "user_id": str(list_request.user_id) if list_request.user_id else None
                }
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error listing documents: {e}", exc_info=True)
            raise
