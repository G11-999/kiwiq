"""
RAG Service routers for KiwiQ system.

This module defines the FastAPI routers for RAG (Retrieval Augmented Generation) endpoints,
including document search, ingestion, deletion, and management. It follows KiwiQ's established
patterns for API design, authentication, error handling, and logging.
"""

import uuid
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Body, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_async_db_dependency
from kiwi_app.utils import get_kiwi_logger
from kiwi_app.auth.dependencies import (
    get_current_active_verified_user, 
    get_current_active_superuser
)
from kiwi_app.auth.models import User
from kiwi_app.workflow_app.dependencies import get_active_org_id

from kiwi_app.rag_service import schemas, services, dependencies
from kiwi_app.rag_service.exceptions import (
    RAGServiceException,
    RAGPermissionException,
    RAGDocumentNotFoundException,
    RAGSearchException,
    RAGIngestionException,
    RAGWeaviateException
)

# Get logger for RAG operations
rag_logger = get_kiwi_logger(name="kiwi_app.rag_service.routers")

# Create router instances
rag_router = APIRouter(prefix="/rag", tags=["rag"])
# rag_admin_router = APIRouter(prefix="/rag/admin", tags=["rag-admin"])

# --- Document Search Endpoints --- #

@rag_router.post("/search", response_model=schemas.RAGSearchResponse, tags=["rag-search"])
async def search_documents(
    search_request: schemas.RAGSearchRequest,
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(dependencies.RequireRAGReadActiveOrg),
    rag_service: services.RAGService = Depends(dependencies.get_rag_service)
):
    """
    Search documents using vector, keyword, or hybrid search.
    
    This endpoint provides comprehensive document search capabilities with:
    - **Vector Search**: Semantic similarity search using embeddings
    - **Keyword Search**: Traditional text-based search
    - **Hybrid Search**: Combination of vector and keyword search
    
    **Permission Rules:**
    - Regular users can only search their own organization's documents
    - Users can optionally filter by their own user_id
    - Superusers can specify any org_id/user_id or perform global search
    
    **Search Features:**
    - Configurable search types (vector/keyword/hybrid)
    - Advanced filtering by namespace, document name, version, dates
    - Chunk-level content and metadata filtering
    - Relevance scoring and ranking
    - Optional vector embeddings in results
    - Pagination support with limit and offset parameters
    
    **Performance Notes:**
    - Results are limited to 100 documents maximum per request
    - Use offset parameter for pagination through large result sets
    - Execution time is tracked and returned in response
    - Filters are optimized for Weaviate performance
    
    Returns search results with relevance scores, document metadata,
    and optional vector embeddings based on request parameters.
    """
    try:
        # For regular users, force active org. For superusers, allow override
        if current_user.is_superuser and search_request.org_id:
            effective_org_id = search_request.org_id
        else:
            effective_org_id = active_org_id
        
        # For regular users, only allow their own user_id if specified
        if current_user.is_superuser:
            effective_user_id = search_request.user_id
        else:
            # Regular users can optionally filter by their own user_id
            if search_request.user_id and search_request.user_id != current_user.id:
                raise RAGPermissionException(
                    # status_code=status.HTTP_403_FORBIDDEN,
                    message="Regular users can only filter by their own user ID"
                )
            effective_user_id = current_user.id
        
        # Update request with effective IDs
        validated_request = search_request.model_copy()
        validated_request.org_id = effective_org_id
        validated_request.user_id = effective_user_id

        if validated_request.search_only_system_entities and (not current_user.is_superuser):
            raise RAGPermissionException(
                message="Regular users cannot search only system entities"
            )
        
        response = await rag_service.search_documents(
            search_request=validated_request,
            user=current_user
        )
        
        rag_logger.info(
            f"Document search completed: user={current_user.id}, "
            f"query='{search_request.query[:50]}...', "
            f"type={search_request.search_type.value}, "
            f"results={response.total_results}"
        )
        
        return response
        
    except RAGPermissionException as e:
        rag_logger.warning(f"Permission denied for user {current_user.id}: {e.message}")
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message
        )
    except ValueError as e:
        rag_logger.warning(f"Invalid search parameters for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        rag_logger.error(f"Error in document search: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search documents"
        )

# --- Document Management Endpoints --- #

@rag_router.delete("/documents", response_model=schemas.RAGDocumentDeleteResponse, tags=["rag-documents"])
async def delete_documents(
    delete_request: schemas.RAGDocumentDeleteRequest,
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(dependencies.RequireRAGWriteActiveOrg),
    rag_service: services.RAGService = Depends(dependencies.get_rag_service)
):
    """
    Delete documents from the vector database by document IDs.
    
    This endpoint removes documents and all their associated chunks from the vector database.
    
    **Permission Rules:**
    - Regular users can only delete documents from their own organization
    - Document access is validated using MongoDB path segments
    - Superusers can delete documents from any organization
    
    **Operation Details:**
    - Validates document access permissions before deletion
    - Removes all chunks associated with each document
    - Provides detailed results including success/failure counts
    - Returns error messages for failed deletions
    
    **Safety Features:**
    - Validates up to 100 document IDs per request
    - Performs permission checks on each document individually
    - Continues processing even if some documents fail
    - Provides detailed error reporting
    
    **Use Cases:**
    - Content cleanup and maintenance
    - Document lifecycle management
    - Data privacy and compliance (GDPR, data deletion requests)
    - Storage optimization
    
    Returns detailed results including successful deletions, failures, and total chunks removed.
    """
    try:
        # For regular users, force active org. For superusers, allow override
        if current_user.is_superuser:  #  and delete_request.org_id
            effective_org_id = delete_request.org_id
        else:
            effective_org_id = active_org_id
        
        # For regular users, only allow their own user_id if specified
        if current_user.is_superuser:
            effective_user_id = delete_request.user_id
        else:
            # Regular users can optionally filter by their own user_id
            if delete_request.user_id and delete_request.user_id != current_user.id:
                raise RAGPermissionException(
                    # status_code=status.HTTP_403_FORBIDDEN,
                    message="Regular users can only filter by their own user ID"
                )
            effective_user_id = current_user.id
        # Update request with effective IDs
        validated_request = delete_request.model_copy()
        validated_request.org_id = effective_org_id
        validated_request.user_id = effective_user_id
        
        response = await rag_service.delete_documents(
            delete_request=validated_request,
            user=current_user
        )
        
        rag_logger.info(
            f"Document deletion completed: user={current_user.id}, "
            f"requested={len(delete_request.doc_ids)}, "
            f"deleted={len(response.deleted_doc_ids)}, "
            f"failed={len(response.failed_doc_ids)}, "
            f"chunks_deleted={response.total_chunks_deleted}"
        )
        
        return response
        
    except RAGPermissionException as e:
        rag_logger.warning(f"Permission denied for document deletion: user={current_user.id}, error={e.message}")
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message
        )
    except ValueError as e:
        rag_logger.warning(f"Invalid deletion parameters: user={current_user.id}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        rag_logger.error(f"Error in document deletion: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete documents"
        )

@rag_router.post("/documents/ingest", response_model=schemas.RAGDocumentIngestResponse, tags=["rag-documents"])
async def ingest_documents(
    ingest_request: schemas.RAGDocumentIngestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db_dependency),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(dependencies.RequireRAGWriteActiveOrg),
    rag_service: services.RAGService = Depends(dependencies.get_rag_service)
):
    """
    Ingest or reingest documents into the vector database.
    
    This endpoint processes documents from MongoDB and creates or updates their
    vector representations in the Weaviate database.
    
    **Permission Rules:**
    - Regular users can only ingest documents from their own organization
    - Document access is validated using MongoDB path segments
    - Superusers can ingest documents from any organization
    
    **Ingestion Process:**
    1. Validates document access permissions
    2. Fetches documents from MongoDB using CustomerDataService
    3. Processes documents through the ingestion pipeline
    4. Generates vector embeddings (if requested)
    5. Stores chunks in Weaviate with proper metadata
    
    **Features:**
    - Supports up to 50 document IDs per request
    - Optional vector embedding generation
    - Force reingest option to update existing documents
    - Detailed per-document results and error reporting
    - Integration with existing ingestion pipeline
    
    **Performance Notes:**
    - Large documents are processed in chunks
    - Vector generation can be disabled for faster processing
    - Background processing for large batches
    - Progress tracking per document
    
    **Use Cases:**
    - Initial document indexing
    - Content updates and versioning
    - Document migration and reprocessing
    - Vector embedding regeneration
    
    Returns detailed results including chunks created, processing status, and any errors.
    """
    try:
        # For regular users, force active org. For superusers, allow override
        if current_user.is_superuser:  #  and ingest_request.org_id
            effective_org_id = ingest_request.org_id or active_org_id
        else:
            effective_org_id = active_org_id
        
        # For regular users, only allow their own user_id if specified
        if current_user.is_superuser:
            effective_user_id = ingest_request.user_id
        else:
            # Regular users can optionally filter by their own user_id
            if ingest_request.user_id and ingest_request.user_id != current_user.id:
                raise RAGPermissionException(
                    # status_code=status.HTTP_403_FORBIDDEN,
                    message="Regular users can only filter by their own user ID"
                )
            effective_user_id = current_user.id
        
        # Update request with effective IDs
        validated_request = ingest_request.model_copy()
        validated_request.org_id = effective_org_id
        validated_request.user_id = effective_user_id
        
        response = await rag_service.ingest_documents(
            db=db,
            ingest_request=validated_request,
            user=current_user,
        )
        
        rag_logger.info(
            f"Document ingestion completed: user={current_user.id}, "
            f"requested={len(ingest_request.doc_ids)}, "
            f"processed={response.total_documents_processed}, "
            f"chunks_created={response.total_chunks_created}, "
            f"chunks_deleted={response.total_chunks_deleted}"
        )
        
        return response
        
    except RAGPermissionException as e:
        rag_logger.warning(f"Permission denied for document ingestion: user={current_user.id}, error={e.message}")
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message
        )
    except ValueError as e:
        rag_logger.warning(f"Invalid ingestion parameters: user={current_user.id}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        rag_logger.error(f"Error in document ingestion: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to ingest documents"
        )

# --- Document Listing and Status Endpoints --- #

@rag_router.post("/documents/list", response_model=schemas.RAGDocumentListResponse, tags=["rag-documents"])
async def list_documents(
    list_request: schemas.RAGDocumentListRequest,
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(dependencies.RequireRAGReadActiveOrg),
    rag_service: services.RAGService = Depends(dependencies.get_rag_service)
):
    """
    List documents in the vector database with filtering and pagination.
    
    This endpoint provides a comprehensive view of documents stored in the vector database
    with flexible filtering and pagination options.
    
    **Permission Rules:**
    - Regular users can only list documents from their own organization
    - Superusers can list documents from any organization or globally
    
    **Filtering Options:**
    - Namespace filtering with pattern matching
    - Document name filtering with wildcard support
    - Organization and user segment filtering
    - Pagination with skip/limit controls
    - Sorting by various fields (created_at, updated_at, doc_name, etc.)
    
    **Document Information:**
    - Document metadata (ID, name, namespace, version)
    - Chunk counts per document
    - Temporal information (created, updated, scheduled dates)
    - Organization and user context
    
    **Use Cases:**
    - Content inventory and management
    - Document discovery and browsing
    - Storage usage analysis
    - Content audit and compliance
    
    Returns paginated list of documents with metadata and filtering summary.
    """
    try:
        # For regular users, force active org. For superusers, allow override
        if current_user.is_superuser:  #  and list_request.org_id
            effective_org_id = list_request.org_id
        else:
            effective_org_id = active_org_id
        
        # For regular users, only allow their own user_id if specified
        if current_user.is_superuser:
            effective_user_id = list_request.user_id
        else:
            # Regular users can optionally filter by their own user_id
            if list_request.user_id and list_request.user_id != current_user.id:
                raise RAGPermissionException(
                    # status_code=status.HTTP_403_FORBIDDEN,
                    message="Regular users can only filter by their own user ID"
                )
            effective_user_id = current_user.id
        
        # Update request with effective IDs
        validated_request = list_request.model_copy()
        validated_request.org_id = effective_org_id
        validated_request.user_id = effective_user_id
        
        response = await rag_service.list_documents(
            list_request=validated_request,
            user=current_user
        )
        
        rag_logger.info(
            f"Document listing completed: user={current_user.id}, "
            f"total={response.total_count}, "
            f"returned={len(response.documents)}, "
            f"filters={response.filters_applied}"
        )
        
        return response
        
    except RAGPermissionException as e:
        rag_logger.warning(f"Permission denied for document listing: user={current_user.id}, error={e.message}")
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message
        )
    except ValueError as e:
        rag_logger.warning(f"Invalid listing parameters: user={current_user.id}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        rag_logger.error(f"Error in document listing: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list documents"
        )

@rag_router.get("/status", response_model=schemas.RAGStatusResponse, tags=["rag-status"])
async def get_rag_status(
    # current_user: User = Depends(get_current_active_verified_user),
    current_superuser: User = Depends(get_current_active_superuser),
    rag_service: services.RAGService = Depends(dependencies.get_rag_service)
):
    """
    Get RAG service status and statistics.
    
    This endpoint provides comprehensive status information about the RAG service
    and vector database health.
    
    **Status Information:**
    - Weaviate connection health
    - Total document and chunk counts
    - Collection schema information
    - Last update timestamps
    - System health metrics
    
    **Use Cases:**
    - Service health monitoring
    - Storage usage tracking
    - System diagnostics
    - Performance monitoring
    
    Available to superusers only. Returns current service status and metrics.
    """
    try:
        response = await rag_service.get_status()
        
        rag_logger.info(
            f"Status check completed: user={current_superuser.id}, "
            f"weaviate_connected={response.weaviate_connected}, "
            f"total_chunks={response.total_chunks}, "
            f"total_documents={response.total_documents}"
        )
        
        return response
        
    except Exception as e:
        rag_logger.error(f"Error getting RAG status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get RAG service status"
        )

# --- Admin Endpoints --- #
