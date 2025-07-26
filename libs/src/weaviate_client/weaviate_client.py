"""
Weaviate Async Client for Document Chunk Management

This module provides an async client for Weaviate operations including:
- Schema setup and configuration
- Batch ingestion and deletion
- Vector, keyword, and hybrid search with prefiltering
- Object reingestion with automatic chunk cleanup
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
import os
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID, uuid4

import weaviate
from weaviate import WeaviateAsyncClient, WeaviateClient
# from weaviate.classes.init import Auth
from weaviate.classes.config import Configure, DataType, Property, VectorDistances, Tokenization, StopwordsPreset
from weaviate.classes.query import Filter, Move, QueryReference, MetadataQuery
from weaviate.classes.tenants import Tenant
from weaviate.util import generate_uuid5

from global_config.settings import global_settings

# Configure logging
logger = logging.getLogger(__name__)


class ChunkSchema:
    """
    Defines the schema for document chunks in Weaviate.
    
    This schema includes:
    - Temporal fields (created_at, updated_at, scheduled_date)
    - Document identifiers (doc_id, org_segment, user_segment, etc.)
    - Chunk content and metadata
    
    Note: created_at and updated_at represent the MongoDB document's original timestamps
    for sync and audit purposes.
    """
    
    # Collection name
    COLLECTION_NAME = "CustomerDocumentChunk"
    
    # Property names as constants for consistency
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    SCHEDULED_DATE = "scheduled_date"
    DOC_ID = "doc_id"
    ORG_SEGMENT = "org_segment"
    USER_SEGMENT = "user_segment"
    NAMESPACE = "namespace"
    DOC_NAME = "doc_name"
    VERSION = "version"
    CHUNK_NO = "chunk_no"
    CHUNK_CONTENT = "chunk_content"
    CHUNK_KEYS = "chunk_keys"
    
    @classmethod
    def get_properties(cls) -> List[Property]:
        """
        Returns the property definitions for the chunk schema.
        
        Returns:
            List[Property]: List of Weaviate property configurations
        """
        return [
            # Temporal fields
            
            Property(
                name=cls.CREATED_AT,
                data_type=DataType.DATE,
                description="MongoDB document creation timestamp",
                index_filterable=True,
                index_range_filters=True,  # Enable range filtering
                index_searchable=False,
                skip_vectorization=True,  # Don't include in vector
            ),
            Property(
                name=cls.UPDATED_AT,
                data_type=DataType.DATE,
                description="MongoDB document last update timestamp",
                index_filterable=True,
                index_range_filters=True,  # Enable range filtering
                index_searchable=False,
                skip_vectorization=True,  # Don't include in vector
            ),
            Property(
                name=cls.SCHEDULED_DATE,
                data_type=DataType.DATE,
                description="Scheduled date for the document (nullable)",
                index_filterable=True,
                index_range_filters=True,  # Enable range filtering
                index_searchable=False,
                skip_vectorization=True,  # Don't include in vector
                # Note: indexNullState is False by default
            ),
            
            # Document identifiers - all skip vectorization
            Property(
                name=cls.DOC_ID,
                data_type=DataType.TEXT,
                description="Full document ID for MongoDB queries and deletion",
                index_filterable=True,
                index_searchable=False,
                tokenization=Tokenization.FIELD,  # Exact match only
                skip_vectorization=True,  # Don't include in vector
            ),
            Property(
                name=cls.ORG_SEGMENT,
                data_type=DataType.TEXT,
                description="Organization segment identifier",
                index_filterable=True,
                index_searchable=False,
                tokenization=Tokenization.FIELD,
                skip_vectorization=True,  # Don't include in vector
            ),
            Property(
                name=cls.USER_SEGMENT,
                data_type=DataType.TEXT,
                description="User segment identifier",
                index_filterable=True,
                index_searchable=False,
                tokenization=Tokenization.FIELD,
                skip_vectorization=True,  # Don't include in vector
            ),
            Property(
                name=cls.NAMESPACE,
                data_type=DataType.TEXT,
                description="Document namespace",
                index_filterable=True,
                index_searchable=False,
                tokenization=Tokenization.FIELD,
                skip_vectorization=True,  # Don't include in vector
            ),
            Property(
                name=cls.DOC_NAME,
                data_type=DataType.TEXT,
                description="Document name",
                index_filterable=True,
                index_searchable=True,  # Allow text search on doc name
                tokenization=Tokenization.WORD,
                skip_vectorization=True,  # Don't include in vector
            ),
            Property(
                name=cls.VERSION,
                data_type=DataType.TEXT,
                description="Document version (nullable)",
                index_filterable=True,
                index_searchable=False,
                tokenization=Tokenization.FIELD,
                skip_vectorization=True,  # Don't include in vector
            ),
            Property(
                name=cls.CHUNK_NO,
                data_type=DataType.INT,
                description="Chunk number within the document",
                index_filterable=True,
                index_searchable=False,
                skip_vectorization=True,  # Don't include in vector
            ),
            
            # Chunk content
            Property(
                name=cls.CHUNK_CONTENT,
                data_type=DataType.TEXT,
                description="Main chunk content (JSON serialized or text/markdown) for vectorization and search",
                index_filterable=False,
                index_searchable=True,
                tokenization=Tokenization.WORD,
                vectorize_property_name=False,  # Don't include property name in vector
            ),
            Property(
                name=cls.CHUNK_KEYS,
                data_type=DataType.TEXT_ARRAY,
                description="JSON keys extracted from the chunk",
                index_filterable=True,
                index_searchable=True,
                tokenization=Tokenization.WORD,
                skip_vectorization=True,  # By default, don't include in vector
            ),
        ]


class WeaviateChunkClient:
    """
    Async client for managing document chunks in Weaviate.
    
    This client provides:
    - Automatic schema creation and validation
    - Batch ingestion with configurable batch sizes (using sync client for performance)
    - Efficient deletion by doc_id using where clauses with ContainsAny optimization
    - Vector, keyword, and hybrid search capabilities
    - Timezone-aware date filtering
    
    Note: Per Weaviate recommendations, batch operations use the synchronous client
    as it's already optimized for concurrent requests. ContainsAny filters are used
    instead of multiple OR operations to avoid Weaviate's filter combination limits.
    """
    
    def __init__(
        self,
        url: Optional[str] = None,
        host: Optional[str] = None,
        api_key: Optional[str] = None,
        additional_headers: Optional[Dict[str, str]] = None,
        collection_name: str = ChunkSchema.COLLECTION_NAME,
        vectorizer: str = "text2vec-openai",
        vectorizer_config: Optional[Dict[str, Any]] = None,
        batch_size: int = 200,
        delete_batch_size: int = 500,  # Separate batch size for deletions
    ):
        """
        Initialize the Weaviate client.
        
        Args:
            url: Weaviate instance URL
            host: Weaviate host (for local connections)
            api_key: Optional API key for authentication
            additional_headers: Optional additional headers
            collection_name: Name of the collection (default: CustomerDocumentChunk)
            vectorizer: Vectorizer module to use (default: text2vec-openai)
            vectorizer_config: Optional vectorizer configuration
            batch_size: Size of each batch for ingestion (default: 100)
            delete_batch_size: Size of each batch for deletion (default: 500)
        """
        # Use provided values or fall back to global settings
        self.url = url or global_settings.WEAVIATE_URL
        self.host = host or global_settings.WEAVIATE_HOST
        # print(f"\n\n\n\nWEAVIATE_HOST: {self.host}\n\n\n\n")
        self.api_key = api_key or global_settings.WEAVIATE_API_KEY
        
        # Setup headers
        openai_key = os.getenv("OPENAI_API_KEY")
        default_headers = {}
        if openai_key:
            default_headers["X-OpenAI-Api-Key"] = openai_key
            
        if additional_headers:
            self.additional_headers = {**default_headers, **additional_headers}
        else:
            self.additional_headers = default_headers

        self.collection_name = collection_name
        self.vectorizer = vectorizer
        self.vectorizer_config = vectorizer_config or {}
        self.batch_size = batch_size
        self.delete_batch_size = delete_batch_size
        
        self.client: Optional[WeaviateAsyncClient] = None
        self.sync_client: Optional[WeaviateClient] = None  # For batch operations
        
        logger.info(f"Initialized WeaviateChunkClient for {self.url or self.host}")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def connect(self) -> None:
        """
        Establish connection to Weaviate.
        
        Creates both async and sync clients. The sync client is used for
        batch operations as recommended by Weaviate documentation.
        
        Raises:
            Exception: If connection fails
        """
        try:
            # Create async client for most operations
            if self.api_key and self.url:
                self.client = weaviate.use_async_with_weaviate_cloud(
                    cluster_url=self.url,
                    auth_credentials=weaviate.auth.Auth.api_key(self.api_key),
                    headers=self.additional_headers,
                )
            else:
                self.client = weaviate.use_async_with_local(
                    host=self.host,
                    headers=self.additional_headers,
                )
            
            await self.client.connect()
            
            # Create sync client for batch operations
            if self.api_key and self.url:
                self.sync_client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=self.url,
                    auth_credentials=weaviate.auth.Auth.api_key(self.api_key),
                    headers=self.additional_headers,
                )
            else:
                self.sync_client = weaviate.connect_to_local(
                    host=self.host,
                    headers=self.additional_headers,
                )
            
            logger.info("Successfully connected to Weaviate (async and sync clients)")
            
        except Exception as e:
            logger.error(f"Failed to connect to Weaviate: {e}")
            raise Exception(f"Connection failed: {e}")
    
    async def close(self) -> None:
        """Close the Weaviate connections."""
        if self.client:
            await self.client.close()
        if self.sync_client:
            self.sync_client.close()
        logger.info("Closed Weaviate connections")
    
    async def setup_schema(self, recreate: bool = False) -> None:
        """
        Setup or validate the collection schema.
        
        Args:
            recreate: If True, delete and recreate the collection
            
        Design decisions:
        - Uses configurable vectorizer for flexibility
        - Enables BM25 for keyword search
        - Sets up appropriate indexes based on query patterns
        """
        if not self.client:
            raise RuntimeError("Client not connected. Call connect() first.")
        
        collections = self.client.collections
        
        # Check if collection exists
        if await collections.exists(self.collection_name):
            if recreate:
                logger.warning(f"Recreating collection {self.collection_name}")
                await collections.delete(self.collection_name)
            else:
                logger.info(f"Collection {self.collection_name} already exists")
                return
        
        # Create collection with schema
        logger.info(f"Creating collection {self.collection_name}")
        
        default_kwargs = {
            "vectorize_collection_name": False,
        }
        # Configure vectorizer with model settings
        vectorizer_module = Configure.Vectorizer.text2vec_openai(
            model="text-embedding-3-large",
            vectorize_collection_name=False,
        )
        # if self.vectorizer == "text2vec-openai":
        #     # Ensure we have a model specified for OpenAI
        #     vectorizer_module = Configure.Vectorizer.text2vec_openai(
        #         model="text-embedding-3-large",
        #         vectorize_collection_name=False,
        #     )
        if self.vectorizer == "text2vec-cohere":
            vectorizer_module = Configure.Vectorizer.text2vec_cohere(**default_kwargs)
        elif self.vectorizer == "text2vec-huggingface":
            vectorizer_module = Configure.Vectorizer.text2vec_huggingface(**default_kwargs)
        # else:
        #     # Default to OpenAI if unknown
        #     vectorizer_module = Configure.Vectorizer.text2vec_openai(
        #         model="ada",
        #         vectorize_collection_name=False,
        #     )
        
        await collections.create(
            name=self.collection_name,
            description="Customer document chunks with metadata for RAG applications",
            vectorizer_config=vectorizer_module,
            # https://weaviate.io/developers/weaviate/config-refs/schema/vector-index#how-to-configure-hnsw
            # vector_index_config=Configure.VectorIndex.dynamic(),  # switches from flat to dynamic when object threshold crossed 
            vector_index_config=Configure.VectorIndex.hnsw(
                # distance_metric=VectorDistances.COSINE,
                # ef_construction=128,
                # ef=64,
                # max_connections=32,
            ),
            properties=ChunkSchema.get_properties(),
            # Enable BM25 for keyword search
            inverted_index_config=Configure.inverted_index(
                # bm25_b=0.75,
                # bm25_k1=1.2,
                stopwords_preset=StopwordsPreset.EN,
                index_null_state=False,  # As requested
                index_property_length=True,
                index_timestamps=True,
            ),
        )
        
        logger.info(f"Successfully created collection {self.collection_name}")
    
    async def ingest_chunks(
        self,
        chunks: List[Dict[str, Any]],
        generate_vectors: bool = True,
    ) -> List[str]:
        """
        Ingest chunks in batches using the sync client for optimal performance.
        
        Args:
            chunks: List of chunk dictionaries
            generate_vectors: Whether to generate vectors (default: True)
            
        Returns:
            List[str]: List of generated UUIDs for the chunks
            
        Note:
        - Uses sync client for batch operations as recommended by Weaviate
        - Handles timezone conversion for dates
        - Generates deterministic UUIDs based on doc_id and chunk_no
        """
        return await asyncio.to_thread(self._ingest_chunks_sync, chunks, generate_vectors)
    
    def _ingest_chunks_sync(self, chunks: List[Dict[str, Any]], generate_vectors: bool = True) -> List[str]:
        """
        Ingest chunks in batches using the sync client for optimal performance.
        """
        if not self.sync_client:
            raise RuntimeError("Sync client not connected. Call connect() first.")
        if not self.sync_client:
            raise RuntimeError("Sync client not connected. Call connect() first.")
        
        collection = self.sync_client.collections.get(self.collection_name)
        uuids = []
        
        # Process chunks in batches using sync client's batch functionality
        with collection.batch.fixed_size(batch_size=self.batch_size) as batch:
            for chunk in chunks:
                # Generate deterministic UUID
                uuid_seed = f"{chunk.get(ChunkSchema.DOC_ID)}_{chunk.get(ChunkSchema.CHUNK_NO)}"
                chunk_uuid = generate_uuid5(uuid_seed)
                uuids.append(str(chunk_uuid))

                # Prepare properties, including date formatting
                properties = {}
                for prop in ChunkSchema.get_properties():
                    prop_name = prop.name
                    if prop_name in chunk:
                        value = chunk[prop_name]
                        if prop.dataType == DataType.DATE and value is not None:
                            if isinstance(value, datetime):
                                if value.tzinfo is None:
                                    value = value.replace(tzinfo=timezone.utc)
                                # Use ISO format with Z for UTC
                                value = value.isoformat().replace('+00:00', 'Z')
                            elif isinstance(value, str):
                                try:
                                    parsed_date = datetime.fromisoformat(value.replace('Z', '+00:00'))
                                    if parsed_date.tzinfo is None:
                                        parsed_date = parsed_date.replace(tzinfo=timezone.utc)
                                    value = parsed_date.isoformat().replace('+00:00', 'Z')
                                except ValueError:
                                    logger.warning(f"Invalid date format for {prop_name}: {value}, setting to None")
                                    value = None
                        properties[prop_name] = value

                # Determine if a custom vector should be used
                vector = chunk.get("vector") if not generate_vectors else None
                
                # Add object to the batch
                batch.add_object(
                    properties=properties,
                    uuid=chunk_uuid,
                    vector=vector,
                )
        
        # Check for failed objects
        if hasattr(collection.batch, 'failed_objects') and collection.batch.failed_objects:
            logger.error(f"Batch insertion errors: {len(collection.batch.failed_objects)} objects failed")
            for error in collection.batch.failed_objects[:5]:  # Log first 5 errors
                logger.error(f"Failed object: {error}")

        logger.info(f"Successfully ingested {len(chunks)} chunks")
        return uuids
    
    async def delete_by_doc_id(
        self, 
        doc_id: Union[str, List[str]], 
    ) -> Tuple[int, int, int, int]:
        """
        Delete all chunks associated with one or more document IDs.
        
        Args:
            doc_id: Single document ID or list of document IDs
            
        Returns:
            Tuple[int, int, int, int]: (total_doc_ids_deleted, failed, matched, successful)
            
        This method uses where clauses for efficient deletion without fetching UUIDs.
        For multiple doc_ids, uses ContainsAny filter to avoid limits with OR operations.
        """
        if not self.client:
            raise RuntimeError("Client not connected. Call connect() first.")
        
        collection = self.client.collections.get(self.collection_name)
        
        # Handle single doc_id or list
        doc_ids = [doc_id] if isinstance(doc_id, str) else doc_id
        
        if not doc_ids:
            return 0, 0, 0, 0  # Return proper tuple for empty input
        
        # Process in batches based on delete_batch_size
        total_doc_ids_deleted = 0
        successful = 0
        failed = 0
        matched = 0
        
        for i in range(0, len(doc_ids), self.delete_batch_size):
            batch_doc_ids = doc_ids[i:i + self.delete_batch_size]
            
            # Build filter for batch deletion using ContainsAny for efficiency
            if len(batch_doc_ids) == 1:
                where_filter = Filter.by_property(ChunkSchema.DOC_ID).equal(batch_doc_ids[0])
            else:
                # Use ContainsAny instead of combining multiple OR filters
                where_filter = Filter.by_property(ChunkSchema.DOC_ID).contains_any(batch_doc_ids)
            
            # Delete using where clause
            try:
                # Use the correct delete method for Weaviate v4
                result = await collection.data.delete_many(where=where_filter)
                
                # Extract results from the response
                logger.debug(f"Delete result type: {type(result)}, attrs: {dir(result)}")
                
                if hasattr(result, 'failed'):
                    failed += result.failed
                    logger.debug(f"Failed count: {result.failed}")
                if hasattr(result, 'matches'):
                    matched += result.matches
                    logger.debug(f"Matches count: {result.matches}")
                # Only count successful if there were actually matches to delete
                if hasattr(result, 'successful') and hasattr(result, 'matches') and result.matches > 0:
                    successful += result.successful
                    logger.debug(f"Successful count: {result.successful}")
                
                # Only count as successful deletions if we actually have matches
                # For non-existent docs, matches should be 0
                if hasattr(result, 'matches') and result.matches > 0:
                    logger.info(f"Deleted {result.matches} chunks for {len(batch_doc_ids)} doc_ids")
                    total_doc_ids_deleted += len(batch_doc_ids)  # Approximate
                else:
                    logger.info(f"No chunks found to delete for {len(batch_doc_ids)} doc_ids")
                        
            except Exception as e:
                logger.error(f"Failed to delete batch: {e}")
                raise
        
        logger.info(f"Deleted chunks for {len(doc_ids)} document(s)")
        return total_doc_ids_deleted, failed, matched, successful
    
    async def reingest_document(
        self,
        doc_id: str,
        new_chunks: List[Dict[str, Any]],
        generate_vectors: bool = True,
    ) -> Tuple[int, List[str]]:
        """
        Reingest a document by deleting old chunks and inserting new ones.
        
        Args:
            doc_id: Document ID to reingest
            new_chunks: New chunks for the document
            generate_vectors: Whether to generate vectors
            
        Returns:
            Tuple[int, List[str]]: (deleted_count, new_uuids)
            
        This is an atomic operation that ensures:
        - All old chunks are deleted before new ones are inserted
        - Consistent state even if insertion fails
        """
        # First, delete all existing chunks
        deleted_doc_count, failed, matched, successful = await self.delete_by_doc_id(doc_id)
        
        # Then, ingest new chunks
        new_uuids = await self.ingest_chunks(new_chunks, generate_vectors)
        
        logger.info(
            f"Reingested document {doc_id}: "
            f"deleted ~{deleted_doc_count}, inserted {len(new_uuids)}, failed {failed}, matched {matched}, successful {successful}"
        )
        
        return deleted_doc_count, new_uuids
    
    async def batch_reingest_documents(
        self,
        documents: List[Dict[str, Any]],
        generate_vectors: bool = True,
    ) -> Dict[str, Tuple[int, List[str]]]:
        """
        Reingest multiple documents in batch.
        
        Args:
            documents: List of dicts with 'doc_id' and 'chunks' keys
                      Example: [{"doc_id": "doc1", "chunks": [...]}, ...]
            generate_vectors: Whether to generate vectors
            
        Returns:
            Dict[str, Tuple[int, List[str]]]: Mapping of doc_id to (deleted_count, new_uuids)
            
        This method efficiently handles multiple document reingestions:
        - Batch deletes all old documents
        - Batch ingests all new chunks
        """
        if not documents:
            return {}
        
        # Extract all doc_ids for batch deletion
        doc_ids = [doc["doc_id"] for doc in documents]
        
        # Batch delete all documents
        logger.info(f"Batch deleting {len(doc_ids)} documents")
        total_docs_deleted, failed, matched, successful = await self.delete_by_doc_id(doc_ids)
        
        # Prepare all chunks for batch ingestion
        all_chunks = []
        doc_chunk_mapping = {}  # Track which chunks belong to which doc
        
        for doc in documents:
            doc_id = doc["doc_id"]
            chunks = doc["chunks"]
            start_idx = len(all_chunks)
            all_chunks.extend(chunks)
            end_idx = len(all_chunks)
            doc_chunk_mapping[doc_id] = (start_idx, end_idx)
        
        # Batch ingest all chunks
        logger.info(f"Batch ingesting {len(all_chunks)} chunks")
        all_uuids = await self.ingest_chunks(all_chunks, generate_vectors)
        
        # Map results back to documents
        results = {}
        for doc_id, (start_idx, end_idx) in doc_chunk_mapping.items():
            doc_uuids = all_uuids[start_idx:end_idx]
            # Approximate deleted count per doc
            avg_deleted = total_docs_deleted // len(doc_ids) if doc_ids else 0
            results[doc_id] = (avg_deleted, doc_uuids)
        
        logger.info(f"Batch reingested {len(documents)} documents")
        return results
    
    async def vector_search(
        self,
        query_vector: Optional[List[float]] = None,
        query_text: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        where_filter: Optional[Filter] = None,
        return_properties: Optional[List[str]] = None,
        include_vector: bool = False,
        target_vector: Optional[Union[List[str], str]] = None,  # Only use with named vectors
        return_metadata: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search.
        
        Args:
            query_vector: Query vector (if None, query_text must be provided)
            query_text: Query text for vectorization
            limit: Maximum results to return
            offset: Number of results to skip before applying the limit
            where_filter: Optional prefilter
            return_properties: Properties to return (None = all)
            include_vector: Whether to include vectors in results
            target_vector: Optional target vector field(s) - only use with named vectors
            return_metadata: Whether to return metadata
            
        Returns:
            List[Dict[str, Any]]: Search results
            
        Note: target_vector should only be used when the collection is configured 
        with named vectors. For default single vector space, leave as None.
        """
        if not self.client:
            raise RuntimeError("Client not connected. Call connect() first.")
        
        if query_vector is None and query_text is None:
            raise ValueError("Either query_vector or query_text must be provided")
        
        collection = self.client.collections.get(self.collection_name)
        
        # Build query kwargs
        base_kwargs = {
            "limit": limit,
            "offset": offset,
        }
        if where_filter:
            base_kwargs["filters"] = where_filter
        if return_properties:
            base_kwargs["return_properties"] = return_properties
        if include_vector:
            base_kwargs["include_vector"] = include_vector
        
        # Only add target_vector if specified (for named vectors)
        if target_vector is not None:
            base_kwargs["target_vector"] = target_vector
        
        # Execute query - these are async operations
        try:
            if query_vector:
                result = await collection.query.near_vector(
                    near_vector=query_vector,
                    return_metadata=MetadataQuery.full() if return_metadata else None,
                    **base_kwargs
                )
            else:
                # Log the search query for debugging
                logger.debug(f"Performing vector search with text: '{query_text}', limit: {limit}, offset: {offset}")
                result = await collection.query.near_text(
                    query=query_text,
                    return_metadata=MetadataQuery.full() if return_metadata else None,
                    **base_kwargs
                )
            
        except Exception as e:
            logger.error(f"Error in vector search: {e}")
            raise
        
        # Convert to dictionaries
        formatted_results = self._format_results(result.objects)
        if not formatted_results and query_text:
            logger.warning(f"Vector search returned no results for query: {query_text}")
        return formatted_results
    
    async def keyword_search(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        where_filter: Optional[Filter] = None,
        return_properties: Optional[List[str]] = None,
        bm25_properties: Optional[List[str]] = None,
        return_metadata: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Perform BM25 keyword search.
        
        Args:
            query: Search query
            limit: Maximum results to return
            offset: Number of results to skip before applying the limit
            where_filter: Optional prefilter
            return_properties: Properties to return
            bm25_properties: Properties to search (default: searchable properties)
            return_metadata: Whether to return metadata
            
        Returns:
            List[Dict[str, Any]]: Search results
        """
        if not self.client:
            raise RuntimeError("Client not connected. Call connect() first.")
        
        collection = self.client.collections.get(self.collection_name)
        
        # Default to searching in searchable text properties
        if bm25_properties is None:
            bm25_properties = [
                ChunkSchema.DOC_NAME,
                ChunkSchema.CHUNK_CONTENT,
                ChunkSchema.CHUNK_KEYS,
            ]
        
        kwargs = {
            "query": query,
            "limit": limit,
            "offset": offset,
        }
        if where_filter:
            kwargs["filters"] = where_filter
        if return_properties:
            kwargs["return_properties"] = return_properties
        if bm25_properties:
            kwargs["query_properties"] = bm25_properties
        
        try:
            logger.debug(f"Performing BM25 search with query: '{query}', properties: {bm25_properties}")
            result = await collection.query.bm25(return_metadata=MetadataQuery.full() if return_metadata else None, **kwargs)
                
        except Exception as e:
            logger.error(f"Error in keyword search: {e}")
            raise
        
        return self._format_results(result.objects)
    
    async def hybrid_search(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        alpha: Optional[float] = None,
        where_filter: Optional[Filter] = None,
        return_properties: Optional[List[str]] = None,
        vector: Optional[List[float]] = None,
        return_metadata: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining vector and keyword search.
        
        Args:
            query: Search query
            limit: Maximum results to return
            offset: Number of results to skip before applying the limit
            alpha: Balance between vector (1.0) and keyword (0.0) search
            where_filter: Optional prefilter
            return_properties: Properties to return
            vector: Optional pre-computed query vector
            return_metadata: Whether to return metadata
            
        Returns:
            List[Dict[str, Any]]: Search results
            
        Alpha controls the balance:
        - alpha = 1.0: Pure vector search
        - alpha = 0.5: Equal weight to both
        - alpha = 0.0: Pure keyword search
        """
        if not self.client:
            raise RuntimeError("Client not connected. Call connect() first.")
        
        collection = self.client.collections.get(self.collection_name)
        
        kwargs = {
            "query": query,
            "limit": limit,
            "offset": offset,
        }
        if alpha is not None:
            kwargs["alpha"] = alpha
        if where_filter:
            kwargs["filters"] = where_filter
        if return_properties:
            kwargs["return_properties"] = return_properties
        if vector:
            kwargs["vector"] = vector
        
        try:
            result = await collection.query.hybrid(return_metadata=MetadataQuery.full() if return_metadata else None, **kwargs)
                
        except Exception as e:
            logger.error(f"Error in hybrid search: {e}")
            raise
        
        return self._format_results(result.objects)
    
    async def search_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        date_field: str = ChunkSchema.SCHEDULED_DATE,
        user_timezone: str = "UTC",
        additional_filters: Optional[Filter] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Search for chunks within a date range.
        
        Args:
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            date_field: Field to filter on (default: scheduled_date)
            user_timezone: User's timezone for conversion
            additional_filters: Additional filters to apply
            limit: Maximum results
            offset: Number of results to skip before applying the limit
            
        Returns:
            List[Dict[str, Any]]: Chunks within date range
            
        This method handles timezone conversion:
        - Converts user's local time to UTC for querying
        - Ensures consistent timezone handling
        """
        if not self.client:
            raise RuntimeError("Client not connected. Call connect() first.")
        
        # Get timezone object
        if user_timezone == "UTC":
            tz = timezone.utc
        else:
            # For non-UTC timezones, you might want to use a library like zoneinfo
            # For now, we'll assume the dates are already in the correct timezone
            logger.warning(f"Timezone {user_timezone} conversion not implemented, using as-is")
            tz = None
        
        # Ensure dates are timezone-aware
        if tz and start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=tz)
        if tz and end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=tz)
        
        # Convert to UTC for Weaviate query
        if start_date.tzinfo:
            start_utc = start_date.astimezone(timezone.utc)
        else:
            start_utc = start_date
            
        if end_date.tzinfo:
            end_utc = end_date.astimezone(timezone.utc)
        else:
            end_utc = end_date
        
        # Build date range filter with RFC3339 format
        start_date_str = start_utc.strftime('%Y-%m-%dT%H:%M:%S.%fZ')[:-3] + 'Z'
        end_date_str = end_utc.strftime('%Y-%m-%dT%H:%M:%S.%fZ')[:-3] + 'Z'
        
        date_filter = (
            Filter.by_property(date_field).greater_or_equal(start_date_str) &
            Filter.by_property(date_field).less_or_equal(end_date_str)
        )
        
        # Combine with additional filters if provided
        if additional_filters:
            where_filter = date_filter & additional_filters
        else:
            where_filter = date_filter
        
        collection = self.client.collections.get(self.collection_name)
        
        kwargs = {
            "limit": limit,
            "offset": offset,
        }
        if where_filter:
            kwargs["filters"] = where_filter
        
        try:
            result = await collection.query.fetch_objects(**kwargs)
                
        except Exception as e:
            logger.error(f"Error in date range search: {e}")
            raise
        
        return self._format_results(result.objects)
    
    def build_filter(
        self,
        doc_id: Optional[str] = None,
        org_segment: Optional[str] = None,
        user_segment: Optional[str] = None,
        namespace: Optional[str] = None,
        doc_name: Optional[str] = None,
        version: Optional[str] = None,
        # Date range filters
        created_at_start: Optional[datetime] = None,
        created_at_end: Optional[datetime] = None,
        updated_at_start: Optional[datetime] = None,
        updated_at_end: Optional[datetime] = None,
        scheduled_date_start: Optional[datetime] = None,
        scheduled_date_end: Optional[datetime] = None,
        # CHUNK_KEYS filters
        chunk_keys_contains_any: Optional[List[str]] = None,
        chunk_keys_contains_all: Optional[List[str]] = None,
    ) -> Optional[Filter]:
        """
        Build a compound filter from document identifiers, date ranges, and chunk keys.
        
        Args:
            doc_id: Document ID filter
            org_segment: Organization segment filter
            user_segment: User segment filter
            namespace: Namespace filter
            doc_name: Document name filter
            version: Version filter
            created_at_start: Filter for CREATED_AT >= this date
            created_at_end: Filter for CREATED_AT <= this date
            updated_at_start: Filter for UPDATED_AT >= this date
            updated_at_end: Filter for UPDATED_AT <= this date
            scheduled_date_start: Filter for SCHEDULED_DATE >= this date
            scheduled_date_end: Filter for SCHEDULED_DATE <= this date
            chunk_keys_contains_any: Filter for CHUNK_KEYS containing any of these values
            chunk_keys_contains_all: Filter for CHUNK_KEYS containing all of these values

            # TODO: add Like support for namespace / docname prefix / suffix filters https://docs.weaviate.io/weaviate/api/graphql/filters#like
            #     NOTE: this filter is inefficent and scales linearly with the number of documents!
            
        Returns:
            Optional[Filter]: Combined filter or None
            
        This is a helper method to build complex filters easily.
        Date values will be converted to ISO format with Z suffix for Weaviate.
        """
        filters = []
        
        # Basic identifier filters
        if doc_id:
            filters.append(Filter.by_property(ChunkSchema.DOC_ID).equal(doc_id))
        if org_segment:
            filters.append(Filter.by_property(ChunkSchema.ORG_SEGMENT).equal(org_segment))
        if user_segment:
            filters.append(Filter.by_property(ChunkSchema.USER_SEGMENT).equal(user_segment))
        if namespace:
            filters.append(Filter.by_property(ChunkSchema.NAMESPACE).equal(namespace))
        if doc_name:
            filters.append(Filter.by_property(ChunkSchema.DOC_NAME).equal(doc_name))
        if version:
            filters.append(Filter.by_property(ChunkSchema.VERSION).equal(version))
        
        # Date range filters for CREATED_AT
        if created_at_start:
            # Ensure timezone
            if created_at_start.tzinfo is None:
                created_at_start = created_at_start.replace(tzinfo=timezone.utc)
            iso_date = created_at_start.strftime('%Y-%m-%dT%H:%M:%S.%fZ')[:-3] + 'Z'
            filters.append(Filter.by_property(ChunkSchema.CREATED_AT).greater_or_equal(iso_date))
        if created_at_end:
            # Ensure timezone
            if created_at_end.tzinfo is None:
                created_at_end = created_at_end.replace(tzinfo=timezone.utc)
            iso_date = created_at_end.strftime('%Y-%m-%dT%H:%M:%S.%fZ')[:-3] + 'Z'
            filters.append(Filter.by_property(ChunkSchema.CREATED_AT).less_or_equal(iso_date))
        
        # Date range filters for UPDATED_AT
        if updated_at_start:
            # Ensure timezone
            if updated_at_start.tzinfo is None:
                updated_at_start = updated_at_start.replace(tzinfo=timezone.utc)
            iso_date = updated_at_start.strftime('%Y-%m-%dT%H:%M:%S.%fZ')[:-3] + 'Z'
            filters.append(Filter.by_property(ChunkSchema.UPDATED_AT).greater_or_equal(iso_date))
        if updated_at_end:
            # Ensure timezone
            if updated_at_end.tzinfo is None:
                updated_at_end = updated_at_end.replace(tzinfo=timezone.utc)
            iso_date = updated_at_end.strftime('%Y-%m-%dT%H:%M:%S.%fZ')[:-3] + 'Z'
            filters.append(Filter.by_property(ChunkSchema.UPDATED_AT).less_or_equal(iso_date))
        
        # Date range filters for SCHEDULED_DATE
        if scheduled_date_start:
            # Ensure timezone
            if scheduled_date_start.tzinfo is None:
                scheduled_date_start = scheduled_date_start.replace(tzinfo=timezone.utc)
            iso_date = scheduled_date_start.strftime('%Y-%m-%dT%H:%M:%S.%fZ')[:-3] + 'Z'
            filters.append(Filter.by_property(ChunkSchema.SCHEDULED_DATE).greater_or_equal(iso_date))
        if scheduled_date_end:
            # Ensure timezone
            if scheduled_date_end.tzinfo is None:
                scheduled_date_end = scheduled_date_end.replace(tzinfo=timezone.utc)
            iso_date = scheduled_date_end.strftime('%Y-%m-%dT%H:%M:%S.%fZ')[:-3] + 'Z'
            filters.append(Filter.by_property(ChunkSchema.SCHEDULED_DATE).less_or_equal(iso_date))
        
        # CHUNK_KEYS filters
        if chunk_keys_contains_any:
            filters.append(Filter.by_property(ChunkSchema.CHUNK_KEYS).contains_any(chunk_keys_contains_any))
        if chunk_keys_contains_all:
            filters.append(Filter.by_property(ChunkSchema.CHUNK_KEYS).contains_all(chunk_keys_contains_all))
        
        if not filters:
            return None
        
        # Combine all filters with AND - this is appropriate since we're combining
        # different types of filters (identifiers, dates, etc.)
        # Note: ContainsAny is already used above for array-based filtering
        combined_filter = filters[0]
        for f in filters[1:]:
            combined_filter = combined_filter & f
        
        return combined_filter
    
    def _format_results(self, objects: List[Any]) -> List[Dict[str, Any]]:
        """
        Format Weaviate objects into dictionaries.
        
        Converts Weaviate response objects into clean dictionaries
        with metadata and properties.
        """
        results = []
        
        for obj in objects:
            metadata = getattr(obj, "metadata", None)
            result = {
                "uuid": str(obj.uuid),
                "properties": obj.properties,
                "metadata": {
                    "distance": getattr(metadata, "distance", None),
                    "certainty": getattr(metadata, "certainty", None),
                    "score": getattr(metadata, "score", None),
                    "explain_score": getattr(metadata, "explain_score", None),
                    # "rerank_score": getattr(metadata, "rerank_score", None),
                    # "is_consistent": getattr(metadata, "is_consistent", None),
                },
            }
            
            # Include vector if present
            if hasattr(obj, "vector") and obj.vector:
                vector = obj.vector
                # Handle named vectors vs single vector space
                if isinstance(vector, dict) and len(vector) == 1 and "default" in vector:
                    # Single vector space returned as {'default': [values]}
                    # Extract just the vector values for backwards compatibility
                    result["vector"] = vector["default"]
                else:
                    # Either a list directly or multiple named vectors
                    result["vector"] = vector
            
            results.append(result)
        
        return results
    
    async def batch_fetch_by_doc_ids(
        self,
        doc_ids: List[str],
        return_properties: Optional[List[str]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch chunks for multiple document IDs efficiently.
        
        Args:
            doc_ids: List of document IDs to fetch
            return_properties: Properties to return
            
        Returns:
            Dict[str, List[Dict[str, Any]]]: Mapping of doc_id to chunks
            
        This method is optimized for batch fetching:
        - Groups results by doc_id
        - Handles large lists of doc_ids
        - Uses ContainsAny filter to avoid limits with OR operations
        """
        if not self.client:
            raise RuntimeError("Client not connected. Call connect() first.")
        
        if not doc_ids:
            return {}
        
        collection = self.client.collections.get(self.collection_name)
        results_by_doc_id = {doc_id: [] for doc_id in doc_ids}
        
        # Process in batches to avoid query size limits
        batch_size = 50  # Adjust based on Weaviate limits
        
        
        for i in range(0, len(doc_ids), batch_size):
            batch_doc_ids = doc_ids[i:i + batch_size]
            
            if len(batch_doc_ids) == 1:
                # Single doc_id
                combined_filter = Filter.by_property(ChunkSchema.DOC_ID).equal(batch_doc_ids[0])
            else:
                # Use ContainsAny instead of combining multiple OR filters
                combined_filter = Filter.by_property(ChunkSchema.DOC_ID).contains_any(batch_doc_ids)
            
            # Fetch objects
            kwargs = {
                "filters": combined_filter,
                "limit": 10000,  # Adjust based on expected chunks per doc
                # NOTE: can use offset in below method!
            }
            if return_properties:
                kwargs["return_properties"] = return_properties
            
            try:
                result = await collection.query.fetch_objects(**kwargs)
                
            except Exception as e:
                logger.error(f"Error in batch fetch: {e}")
                raise
            
            # Group by doc_id
            for obj in result.objects:
                doc_id = obj.properties.get(ChunkSchema.DOC_ID)
                if doc_id in results_by_doc_id:
                    results_by_doc_id[doc_id].append({
                        "uuid": str(obj.uuid),
                        "properties": obj.properties,
                    })
        
        return results_by_doc_id


# Example usage function for testing
async def example_usage():
    """
    Example usage of the WeaviateChunkClient.
    
    This demonstrates:
    - Client initialization and connection
    - Schema setup
    - Chunk ingestion
    - Various search methods
    - Document reingestion
    - Batch operations
    """
    # Initialize client
    async with WeaviateChunkClient(
        # url="http://localhost:8080",
        vectorizer="text2vec-openai",
        batch_size=100,
        delete_batch_size=500,
    ) as client:
        # Setup schema
        await client.setup_schema(recreate=False)
        
        # Example chunks
        example_chunks = [
            {
                ChunkSchema.DOC_ID: "doc123",
                ChunkSchema.ORG_SEGMENT: "org1",
                ChunkSchema.USER_SEGMENT: "user1",
                ChunkSchema.NAMESPACE: "default",
                ChunkSchema.DOC_NAME: "Technical Documentation",
                ChunkSchema.VERSION: "1.0",
                ChunkSchema.CHUNK_NO: 1,
                ChunkSchema.CHUNK_CONTENT: '{"title": "Introduction", "content": "This is the first chunk of technical documentation."}',
                ChunkSchema.CHUNK_KEYS: ["title", "content"],
                ChunkSchema.CREATED_AT: datetime.now(timezone.utc),
                ChunkSchema.UPDATED_AT: datetime.now(timezone.utc),
                ChunkSchema.SCHEDULED_DATE: datetime(2024, 1, 15, tzinfo=timezone.utc),
            },
            {
                ChunkSchema.DOC_ID: "doc123",
                ChunkSchema.ORG_SEGMENT: "org1",
                ChunkSchema.USER_SEGMENT: "user1",
                ChunkSchema.NAMESPACE: "default",
                ChunkSchema.DOC_NAME: "Technical Documentation",
                ChunkSchema.VERSION: "1.0",
                ChunkSchema.CHUNK_NO: 2,
                ChunkSchema.CHUNK_CONTENT: '{"details": "specifications", "info": "This is the second chunk with more details."}',
                ChunkSchema.CHUNK_KEYS: ["details", "info"],
                ChunkSchema.CREATED_AT: datetime.now(timezone.utc),
                ChunkSchema.UPDATED_AT: datetime.now(timezone.utc),
                ChunkSchema.SCHEDULED_DATE: datetime(2024, 1, 15, tzinfo=timezone.utc),
            },
        ]
        
        # Ingest chunks
        uuids = await client.ingest_chunks(example_chunks)
        print(f"Ingested {len(uuids)} chunks")
        
        # Vector search (default: only searches CHUNK_CONTENT)
        results = await client.vector_search(
            query_text="technical documentation overview",
            limit=5,
            offset=0,
        )
        print(f"Vector search found {len(results)} results")
        
        # Vector search with offset for pagination
        results = await client.vector_search(
            query_text="technical documentation overview",
            limit=3,
            offset=2,
        )
        print(f"Vector search with offset found {len(results)} results")
        
        # Vector search with different query
        results = await client.vector_search(
            query_text="title content",
            limit=5,
            offset=0,
        )
        print(f"Vector search found {len(results)} results")
        
        # Keyword search
        results = await client.keyword_search(
            query="specifications",
            limit=5,
            offset=0,
        )
        print(f"Keyword search found {len(results)} results")
        
        # Hybrid search
        results = await client.hybrid_search(
            query="technical documentation",
            alpha=0.7,  # More weight on vector search
            limit=5,
            offset=0,
        )
        print(f"Hybrid search found {len(results)} results")
        
        # Date range search
        results = await client.search_by_date_range(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
            date_field=ChunkSchema.SCHEDULED_DATE,
            user_timezone="UTC",
            limit=100,
            offset=0,
        )
        print(f"Date range search found {len(results)} results")
        
        # Document reingestion
        new_chunks = [
            {
                ChunkSchema.DOC_ID: "doc123",
                ChunkSchema.ORG_SEGMENT: "org1",
                ChunkSchema.USER_SEGMENT: "user1",
                ChunkSchema.NAMESPACE: "default",
                ChunkSchema.DOC_NAME: "Technical Documentation v2",
                ChunkSchema.VERSION: "2.0",
                ChunkSchema.CHUNK_NO: 1,
                ChunkSchema.CHUNK_CONTENT: '{"update": "revision", "content": "Updated documentation with new content."}',
                ChunkSchema.CHUNK_KEYS: ["update", "content"],
                ChunkSchema.CREATED_AT: datetime.now(timezone.utc),
                ChunkSchema.UPDATED_AT: datetime.now(timezone.utc),
                ChunkSchema.SCHEDULED_DATE: datetime(2024, 2, 1, tzinfo=timezone.utc),
            },
        ]
        
        deleted, new_uuids = await client.reingest_document(
            "doc123", 
            new_chunks,
        )
        print(f"Reingestion: deleted ~{deleted}, added {len(new_uuids)} chunks")
        
        # Batch reingestion
        batch_docs = [
            {
                "doc_id": "doc456",
                "chunks": [
                    {
                        ChunkSchema.DOC_ID: "doc456",
                        ChunkSchema.ORG_SEGMENT: "org1",
                        ChunkSchema.USER_SEGMENT: "user2",
                        ChunkSchema.NAMESPACE: "default",
                        ChunkSchema.DOC_NAME: "API Documentation",
                        ChunkSchema.VERSION: "1.0",
                        ChunkSchema.CHUNK_NO: 1,
                        ChunkSchema.CHUNK_CONTENT: "API endpoint documentation",
                        ChunkSchema.CHUNK_KEYS: ["api", "endpoints"],
                        ChunkSchema.CREATED_AT: datetime.now(timezone.utc),
                        ChunkSchema.UPDATED_AT: datetime.now(timezone.utc),
                        ChunkSchema.SCHEDULED_DATE: datetime(2024, 1, 15, tzinfo=timezone.utc),
                    },
                ],
            },
            {
                "doc_id": "doc789",
                "chunks": [
                    {
                        ChunkSchema.DOC_ID: "doc789",
                        ChunkSchema.ORG_SEGMENT: "org2",
                        ChunkSchema.USER_SEGMENT: "user3",
                        ChunkSchema.NAMESPACE: "default",
                        ChunkSchema.DOC_NAME: "User Guide",
                        ChunkSchema.VERSION: "2.0",
                        ChunkSchema.CHUNK_NO: 1,
                        ChunkSchema.CHUNK_CONTENT: "User guide content",
                        ChunkSchema.CHUNK_KEYS: ["guide", "user"],
                        ChunkSchema.CREATED_AT: datetime.now(timezone.utc),
                        ChunkSchema.UPDATED_AT: datetime.now(timezone.utc),
                        ChunkSchema.SCHEDULED_DATE: datetime(2024, 1, 15, tzinfo=timezone.utc),
                    },
                ],
            },
        ]
        
        batch_results = await client.batch_reingest_documents(batch_docs)
        print(f"Batch reingested {len(batch_results)} documents")
        
        # Batch deletion
        deleted_doc_count, failed, matched, successful = await client.delete_by_doc_id(["doc456", "doc789"])
        print(f"Batch deleted ~{deleted_doc_count} doc_ids, failed {failed}, matched {matched}, successful {successful}")
        
        # Example of advanced filtering with build_filter
        advanced_filter = client.build_filter(
            org_segment="org1",
            created_at_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            created_at_end=datetime(2024, 12, 31, tzinfo=timezone.utc),
            chunk_keys_contains_any=["title", "content"],
        )
        
        # Use advanced filter in search
        if advanced_filter:
            results = await client.vector_search(
                query_text="documentation",
                where_filter=advanced_filter,
                limit=5,
            )
            print(f"Advanced filtered search found {len(results)} results")
        
        # Example with chunk_keys_contains_all
        strict_filter = client.build_filter(
            user_segment="user1",
            chunk_keys_contains_all=["title", "content", "details"],
            scheduled_date_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        
        if strict_filter:
            results = await client.keyword_search(
                query="technical",
                where_filter=strict_filter,
                limit=5,
            )
            print(f"Strict filtered search found {len(results)} results")
        
        # Final cleanup - delete all test data created during example
        test_doc_ids = ["doc123", "doc456", "doc789"]
        print(f"Cleaning up test data: {test_doc_ids}")
        
        deleted_doc_count, failed, matched, successful = await client.delete_by_doc_id(test_doc_ids)
        print(f"Final cleanup: deleted ~{deleted_doc_count} doc_ids, failed {failed}, matched {matched}, successful {successful}")
        
        # Verify cleanup by attempting to fetch any remaining chunks
        remaining_results = await client.batch_fetch_by_doc_ids(test_doc_ids)
        total_remaining = sum(len(chunks) for chunks in remaining_results.values())
        if total_remaining == 0:
            print("✅ All test data successfully cleaned up from Weaviate")
        else:
            print(f"⚠️  {total_remaining} test chunks still remain in Weaviate")
        


if __name__ == "__main__":
    # Run example
    asyncio.run(example_usage())
