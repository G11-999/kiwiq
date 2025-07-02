"""
Ingestion pipeline for customer documents into Weaviate vector database.

This module provides functionality to:
1. Parse document type from metadata using patterns from app_artifacts.py
2. Chunk documents using JSONSplitter with cluster-aware processing
3. Process chunks to add cluster information and create flat JSON structures
4. Extract nested keys for enhanced searchability
5. Ingest processed chunks into Weaviate for RAG applications

Key Features:
- Intelligent document type detection based on namespace and docname patterns
- Cluster-aware chunking for improved semantic organization  
- Automatic key extraction from nested JSON structures
- Batch processing support for high-volume ingestion
- Configurable chunking parameters for different document types
"""

import json
import logging
from datetime import datetime, timezone
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Union, Tuple
from uuid import UUID, uuid4

from kiwi_app.workflow_app.schemas import CustomerDocumentSearchResult, CustomerDocumentSearchResultMetadata
from kiwi_app.data_jobs.ingestion.chunking import JSONSplitter
from weaviate_client.weaviate_client import WeaviateChunkClient, ChunkSchema

# Configure logging
logger = logging.getLogger(__name__)


def parse_doc_type_from_metadata(metadata: CustomerDocumentSearchResultMetadata) -> str:
    """
    Parse document type from metadata object using pattern matching against app_artifacts.py keys.
    
    This function matches document patterns based on the document configurations defined in
    app_artifacts.py to determine the appropriate chunking strategy. The mapping follows
    the document keys used in the UserDocumentsConfig.
    
    Args:
        metadata: CustomerDocumentSearchResultMetadata object
        
    Returns:
        str: Parsed document type corresponding to app_artifacts.py keys
        
    Document Type Mapping:
    - user_dna_doc: User DNA and profile documents
    - content_strategy_doc: Content strategy and pillar documents  
    - linkedin_scraped_profile_doc/linkedin_scraped_posts_doc: LinkedIn data
    - content_analysis_doc: Analysis and insight documents
    - brief/concept/draft/idea: Content creation documents
    - uploaded_files: User-uploaded file documents
    - Default fallback for unmapped documents
    """
    namespace = metadata.namespace.lower() if metadata.namespace else ''
    docname = metadata.docname.lower() if metadata.docname else ''
    
    # Direct docname matches from app_artifacts.py keys
    if 'user_dna_doc' in docname:
        return "user_dna_doc"
    elif 'content_strategy_doc' in docname:
        return "content_strategy_doc"
    elif 'core_beliefs_perspectives_doc' in docname:
        return "core_beliefs_perspectives_doc" 
    elif 'content_pillars_doc' in docname:
        return "content_pillars_doc"
    elif 'user_preferences_doc' in docname:
        return "user_preferences_doc"
    elif 'content_analysis_doc' in docname:
        return "content_analysis_doc"
    elif 'linkedin_scraped_profile_doc' in docname:
        return "linkedin_scraped_profile_doc"
    elif 'linkedin_scraped_posts_doc' in docname:
        return "linkedin_scraped_posts_doc"
    elif 'user_source_analysis' in docname:
        return "user_source_analysis"
    elif 'knowledge_base_analysis' in docname:
        return "knowledge_base_analysis"
    elif 'writing_style' in docname:
        return "writing_style"
    
    # Brief, concept, draft, idea pattern matching
    elif docname.startswith('brief_'):
        return "brief"
    elif docname.startswith('concept_'):
        return "concept" 
    elif docname.startswith('draft_'):
        return "draft"
    elif docname.startswith('idea_'):
        return "idea"
    
    # System documents
    elif 'methodology_implementation_ai_copilot' in docname:
        return "methodology_implementation_ai_copilot"
    elif 'building_blocks_content_methodology' in docname:
        return "building_blocks_content_methodology"
    elif 'linkedin_post_evaluation_framework' in docname:
        return "linkedin_post_evaluation_framework"
    elif 'linkedin_post_scoring_framework' in docname:
        return "linkedin_post_scoring_framework"
    elif 'linkedin_content_optimization_guide' in docname:
        return "linkedin_content_optimization_guide"
    
    # Namespace-based pattern matching
    elif 'user_strategy' in namespace:
        return "content_strategy_doc"  # Default for strategy namespace
    elif 'user_analysis' in namespace:
        return "content_analysis_doc"  # Default for analysis namespace
    elif 'user_insights' in namespace or 'user_inputs' in namespace:
        return "user_preferences_doc"  # Default for insights/inputs namespace
    elif 'user_identity' in namespace or 'scraping_results' in namespace:
        return "linkedin_scraped_profile_doc"  # Default for identity/scraping namespace
    elif 'content_briefs' in namespace:
        return "brief"
    elif 'content_concepts' in namespace:
        return "concept"
    elif 'post_drafts' in namespace:
        return "draft"
    elif 'content_ideas' in namespace:
        return "idea"
    elif 'uploaded_files' in namespace:
        return "uploaded_files"
    elif 'knowledge_base' in namespace:
        return "knowledge_base_analysis"
    elif 'system_strategy_docs_namespace' in namespace:
        return "methodology_implementation_ai_copilot"  # Default system doc type
    
    # Content-related fallbacks
    elif 'dna' in docname or 'profile' in docname:
        return "user_dna_doc"
    elif 'strategy' in docname or 'pillar' in docname:
        return "content_strategy_doc"
    elif 'linkedin' in docname or 'social' in docname:
        return "linkedin_scraped_profile_doc"
    elif 'analysis' in docname or 'insight' in docname:
        return "content_analysis_doc"
    elif 'content' in docname or 'post' in docname:
        return "content_analysis_doc"
    
    # Default fallback - use content_strategy_doc as reasonable default for chunking
    logger.debug(f"No specific doc_type match found for namespace='{namespace}', docname='{docname}'. Using default.")
    return "content_strategy_doc"


def extract_nested_keys(obj: Any, parent_key: str = "", max_depth: int = 10, current_depth: int = 0) -> List[str]:
    """
    Recursively extract all nested keys from a JSON object into a flat list.
    
    This function traverses nested JSON structures and creates a comprehensive
    list of all possible key paths for enhanced searchability in Weaviate.
    
    Args:
        obj: JSON object to extract keys from
        parent_key: Parent key path for nested objects
        max_depth: Maximum recursion depth to prevent infinite loops
        current_depth: Current recursion depth
        
    Returns:
        List[str]: Flat list of all nested key paths
        
    Example:
        Input: {"user": {"profile": {"name": "John"}}, "age": 30}
        Output: ["user", "user.profile", "user.profile.name", "age"]
        
    Design Decisions:
    - Uses dot notation for nested objects: "parent.child.grandchild"
    - Uses bracket notation for array indices: "parent[0].child"
    - Limits recursion depth to prevent performance issues
    - Filters out empty keys and very long key paths
    """
    if current_depth > max_depth:
        return []
    
    keys = []
    
    if isinstance(obj, dict):
        for key, value in obj.items():
            if not key or len(str(key)) > 100:  # Skip empty or very long keys
                continue
                
            # Add the current key
            current_key = f"{parent_key}.{key}" if parent_key else key
            keys.append(current_key)
            
            # Recursively extract nested keys
            nested_keys = extract_nested_keys(value, current_key, max_depth, current_depth + 1)
            keys.extend(nested_keys)
            
    elif isinstance(obj, list):
        # For lists, extract keys from each item with index (limit to reasonable size)
        for i, item in enumerate(obj[:10]):  # Limit to first 10 items to avoid explosion
            indexed_key = f"{parent_key}[{i}]" if parent_key else f"[{i}]"
            nested_keys = extract_nested_keys(item, indexed_key, max_depth, current_depth + 1)
            keys.extend(nested_keys)
    
    return keys


def process_chunks_for_ingestion(
    clustered_chunks: Dict[str, List[Dict[str, Any]]],
    base_metadata: CustomerDocumentSearchResultMetadata,
    doc_id: str,
    preserve_temporal_fields: bool = True
) -> List[Dict[str, Any]]:
    """
    Process clustered chunks into a flat list ready for Weaviate ingestion.
    
    This function takes the output from JSONSplitter.process_json_document and
    transforms it into Weaviate-compatible chunks with proper metadata mapping.
    
    Args:
        clustered_chunks: Output from JSONSplitter.process_json_document
        base_metadata: CustomerDocumentSearchResultMetadata object
        doc_id: Document ID for tracking and deletion
        preserve_temporal_fields: Whether to preserve created_at/updated_at from original doc
        
    Returns:
        List[Dict[str, Any]]: Flat list of chunks ready for Weaviate ingestion
        
    Processing Steps:
    1. Flattens all clusters into a single list of chunks
    2. Adds cluster information to each chunk (unless cluster is "default")
    3. Serializes chunk content to JSON string for vector embedding
    4. Extracts nested keys for keyword search capabilities
    5. Assigns sequential chunk numbers for ordering
    6. Maps metadata fields to Weaviate schema requirements
    7. Handles temporal fields and version information
    """
    final_chunks = []
    chunk_counter = 0
    
    # Extract temporal information from metadata object
    created_at = None
    updated_at = None
    scheduled_date = None
    
    if preserve_temporal_fields:
        # Try to extract temporal fields from metadata object attributes
        # Note: These might not exist in the current schema, but we check for future extensibility
        for attr_name in ['created_at', 'createdAt', 'created']:
            if hasattr(base_metadata, attr_name):
                attr_value = getattr(base_metadata, attr_name)
                if attr_value:
                    try:
                        if isinstance(attr_value, str):
                            created_at = datetime.fromisoformat(attr_value.replace('Z', '+00:00'))
                        elif isinstance(attr_value, datetime):
                            created_at = attr_value
                        break
                    except (ValueError, TypeError):
                        continue
        
        for attr_name in ['updated_at', 'updatedAt', 'updated', 'modified_at']:
            if hasattr(base_metadata, attr_name):
                attr_value = getattr(base_metadata, attr_name)
                if attr_value:
                    try:
                        if isinstance(attr_value, str):
                            updated_at = datetime.fromisoformat(attr_value.replace('Z', '+00:00'))
                        elif isinstance(attr_value, datetime):
                            updated_at = attr_value
                        break
                    except (ValueError, TypeError):
                        continue
        
        # Check for scheduled date in metadata
        for attr_name in ['scheduled_date', 'scheduledDate', 'schedule', 'publish_date']:
            if hasattr(base_metadata, attr_name):
                attr_value = getattr(base_metadata, attr_name)
                if attr_value:
                    try:
                        if isinstance(attr_value, str):
                            scheduled_date = datetime.fromisoformat(attr_value.replace('Z', '+00:00'))
                        elif isinstance(attr_value, datetime):
                            scheduled_date = attr_value
                        break
                    except (ValueError, TypeError):
                        continue
    
    # Default to current time if no temporal info found
    current_time = datetime.now(timezone.utc)
    created_at = created_at or current_time
    updated_at = updated_at or current_time
    
    # Ensure timezone awareness
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    if scheduled_date and scheduled_date.tzinfo is None:
        scheduled_date = scheduled_date.replace(tzinfo=timezone.utc)
    
    for cluster_name, cluster_chunks in clustered_chunks.items():
        logger.debug(f"Processing cluster '{cluster_name}' with {len(cluster_chunks)} chunks")
        
        for chunk_data in cluster_chunks:
            chunk_counter += 1
            
            # Create a copy to avoid modifying original data
            processed_chunk = chunk_data.copy() if isinstance(chunk_data, dict) else {"content": chunk_data}
            
            # Add cluster information unless it's "default"
            if cluster_name != "default":
                processed_chunk["cluster"] = cluster_name
            
            # Serialize chunk content to JSON string for embedding
            try:
                chunk_content = json.dumps(processed_chunk, ensure_ascii=False, default=str)
            except (TypeError, ValueError) as e:
                logger.warning(f"Failed to serialize chunk {chunk_counter}: {e}")
                # Fallback to string representation
                chunk_content = str(processed_chunk)
            
            # Extract nested keys for enhanced searchability
            try:
                chunk_keys = extract_nested_keys(processed_chunk)
                # Remove duplicates and limit to reasonable number
                chunk_keys = list(dict.fromkeys(chunk_keys))  # Preserve order while removing dupes
                chunk_keys = chunk_keys[:50]  # Limit to prevent too many keys
            except Exception as e:
                logger.warning(f"Failed to extract keys from chunk {chunk_counter}: {e}")
                chunk_keys = []
            
            # Build org and user segments from metadata object
            org_segment = str(base_metadata.org_id)
            
            user_segment = str(base_metadata.user_id_or_shared_placeholder)
            
            # Create Weaviate-compatible chunk with all required fields
            weaviate_chunk = {
                ChunkSchema.DOC_ID: doc_id,
                ChunkSchema.ORG_SEGMENT: org_segment,
                ChunkSchema.USER_SEGMENT: user_segment,
                ChunkSchema.NAMESPACE: base_metadata.namespace or 'default',
                ChunkSchema.DOC_NAME: base_metadata.docname or 'unknown',
                ChunkSchema.VERSION: base_metadata.version,  # Can be None
                ChunkSchema.CHUNK_NO: chunk_counter,
                ChunkSchema.CHUNK_CONTENT: chunk_content,
                ChunkSchema.CHUNK_KEYS: chunk_keys,
                ChunkSchema.CREATED_AT: created_at,
                ChunkSchema.UPDATED_AT: updated_at,
                ChunkSchema.SCHEDULED_DATE: scheduled_date,  # Can be None
            }
            
            final_chunks.append(weaviate_chunk)
    
    logger.info(f"Created {len(final_chunks)} total chunks from {len(clustered_chunks)} clusters")
    return final_chunks


class DocumentIngestionPipeline:
    """
    Comprehensive pipeline for ingesting customer documents into Weaviate vector database.
    
    This pipeline orchestrates the complete flow from document input to vector storage:
    1. Document type detection using app_artifacts.py patterns
    2. Intelligent chunking based on document structure and type
    3. Cluster-aware processing for semantic organization
    4. Metadata extraction and mapping to Weaviate schema
    5. Vector embedding and storage with optimized batch operations
    
    Key Features:
    - Automatic doc_type detection from 20+ document patterns
    - Configurable chunking parameters per document type
    - Cluster-based semantic organization (metadata, content_goals, etc.)
    - Comprehensive key extraction for enhanced search capabilities
    - Unified batch processing for both single and multiple documents
    - Support for both new ingestion and document reingestion
    
    Design Principles:
    - Extensible architecture for new document types
    - Robust error handling with detailed logging
    - Memory-efficient processing for large document sets
    - Optimized for RAG application requirements
    """
    
    def __init__(
        self,
        weaviate_client: WeaviateChunkClient,
        max_json_chunk_size: int = 700,
        max_text_char_limit: int = 700,
        max_json_char_limit: int = 700,
        text_overlap_percent: float = 20.0,
        preserve_temporal_fields: bool = True
    ):
        """
        Initialize the document ingestion pipeline.
        
        Args:
            weaviate_client: Connected WeaviateChunkClient instance
            max_json_chunk_size: Maximum size for JSON chunks in RecursiveJsonSplitter
            max_text_char_limit: Maximum character limit for individual text splits
            max_json_char_limit: Maximum character limit for complete JSON objects
            text_overlap_percent: Percentage (0-100) of text to overlap between chunks for context preservation
            preserve_temporal_fields: Whether to preserve original document timestamps
        """
        self.weaviate_client = weaviate_client
        self.preserve_temporal_fields = preserve_temporal_fields
        
        # Initialize JSON splitter with chunking configuration
        self.json_splitter = JSONSplitter(
            max_json_chunk_size=max_json_chunk_size,
            max_text_char_limit=max_text_char_limit,
            max_json_char_limit=max_json_char_limit,
            text_overlap_percent=text_overlap_percent
        )
        
        logger.info(
            f"Initialized DocumentIngestionPipeline with chunking limits: "
            f"json={max_json_chunk_size}, text={max_text_char_limit}, "
            f"json_char={max_json_char_limit}, overlap={text_overlap_percent}%, "
            f"preserve_temporal={preserve_temporal_fields}"
        )
    
    def _convert_datetimes_to_str(self, obj: Any) -> Any:
        """Recursively convert datetime objects to ISO format strings."""
        
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: self._convert_datetimes_to_str(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_datetimes_to_str(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(self._convert_datetimes_to_str(item) for item in obj)
        else:
            return obj

    def _prepare_document_data(self, doc_data: Any) -> Tuple[Dict[str, Any], bool]:
        """
        Convert document data to appropriate format for processing and determine if it's JSON-like.
        
        Args:
            doc_data: Document data in various formats
            
        Returns:
            Tuple[Dict[str, Any], bool]: (normalized_data, is_json_like)
                - normalized_data: Data ready for processing
                - is_json_like: True if data is JSON-like and can use JSON processing, False if should use text splitting
        """
        # First, try to normalize to dict/JSON format
        if isinstance(doc_data, dict):
            ret_value = doc_data, True
        elif hasattr(doc_data, 'model_dump'):
            ret_value = doc_data.model_dump(), True
        elif hasattr(doc_data, 'dict'):
            ret_value = doc_data.dict(), True
        elif hasattr(doc_data, '__dict__'):
            ret_value = doc_data.__dict__, True
        elif isinstance(doc_data, str):
            # Try to parse as JSON
            try:
                parsed = json.loads(doc_data)
                if isinstance(parsed, dict):
                    ret_value = parsed, True
                else:
                    # JSON but not a dict (e.g., list, primitive) - treat as text
                    ret_value = {"content": doc_data}, False
            except json.JSONDecodeError:
                # Not valid JSON - treat as text
                ret_value = {"content": doc_data}, False
        elif isinstance(doc_data, (list, tuple)):
            # Collections that aren't dicts - treat as text
            text_content = str(doc_data)
            ret_value = {"content": text_content}, False
        else:
            # Any other type - convert to text
            text_content = str(doc_data)
            ret_value = {"content": text_content}, False

        if ret_value[1]:
            ret_value = self._convert_datetimes_to_str(ret_value[0]), ret_value[1]
        return ret_value
    
    def _generate_doc_id(self, metadata: CustomerDocumentSearchResultMetadata) -> str:
        """
        Generate a consistent document ID from metadata object.
        
        Args:
            metadata: CustomerDocumentSearchResultMetadata object
            
        Returns:
            str: Generated document ID for tracking
        """
        # Use existing ID if available
        if metadata.id:
            return str(metadata.id)
        
        # Build ID from components
        org_id = metadata.org_id or 'unknown'
        namespace = metadata.namespace or 'default'
        docname = metadata.docname or 'unknown'
        version = metadata.version or ''
        
        # Include version in ID if available
        if version:
            return f"{org_id}_{namespace}_{docname}_v{version}"
        else:
            return f"{org_id}_{namespace}_{docname}"
    
    async def ingest_documents(
        self,
        documents: Union[CustomerDocumentSearchResult, List[CustomerDocumentSearchResult]],
        generate_vectors: bool = True
    ) -> Dict[str, Tuple[int, List[str]]]:
        """
        Ingest customer documents into Weaviate using batch processing.
        
        This unified method handles both single documents and document lists efficiently
        using the batch reingest functionality for optimal performance.
        
        Args:
            documents: Single CustomerDocumentSearchResult or list of documents to ingest
            generate_vectors: Whether to generate embeddings during ingestion
            
        Returns:
            Dict[str, Tuple[int, List[str]]]: Mapping of doc_id to (chunks_created, chunk_uuids)
            
        Process Flow:
        1. Normalize input to list format
        2. Extract and validate metadata and document data
        3. Parse document types using app_artifacts.py patterns
        4. Prepare document data (JSON vs text processing)
        5. Apply appropriate chunking strategy (JSON splitter or text recursive)
        6. Process chunks for Weaviate compatibility
        7. Batch ingest using weaviate_client.batch_reingest_documents
        
        Error Handling:
        - Skips versioning metadata documents
        - Handles various document data formats gracefully
        - Provides detailed logging for debugging
        - Continues processing even if individual documents have issues
        """
        # Normalize input to list
        if isinstance(documents, CustomerDocumentSearchResult):
            document_list = [documents]
        else:
            document_list = documents
        
        if not document_list:
            return {}
        
        logger.info(f"Starting batch ingestion of {len(document_list)} documents")
        
        results = {}
        weaviate_batch_docs = []
        
        try:
            # Process each document for chunking and preparation
            for idx, doc in enumerate(document_list):
                try:
                    metadata = doc.metadata
                    doc_data = doc.data
                    
                    # Generate consistent document ID
                    doc_id = self._generate_doc_id(metadata)
                    
                    logger.debug(f"Processing document {idx + 1}/{len(document_list)}: {doc_id}")
                    logger.debug(f"Document metadata: namespace='{metadata.namespace}', "
                                f"docname='{metadata.docname}', version='{metadata.version}'")
                    
                    # Skip versioning metadata documents as they don't contain actual content
                    if metadata.is_versioning_metadata:
                        logger.info(f"Skipping versioning metadata document: {doc_id}")
                        results[doc_id] = (0, [])
                        continue
                    
                    # Parse document type for appropriate chunking strategy
                    doc_type = parse_doc_type_from_metadata(metadata)
                    logger.debug(f"Parsed document type: '{doc_type}' for document: {doc_id}")
                    
                    # Prepare document data and determine processing strategy
                    prepared_data, is_json_like = self._prepare_document_data(doc_data)
                    
                    if not prepared_data:
                        logger.warning(f"No content to process for document: {doc_id}")
                        results[doc_id] = (0, [])
                        continue
                    
                    # Apply appropriate chunking strategy
                    logger.debug(f"Chunking document with type: {doc_type}, is_json_like: {is_json_like}")
                    try:
                        if is_json_like:
                            # Use JSON-aware chunking with cluster processing
                            clustered_chunks = self.json_splitter.process_json_document(prepared_data, doc_type)
                        else:
                            # Use text recursive splitting for non-JSON content
                            # Extract text content and apply recursive text splitting
                            text_content = prepared_data.get('content', str(prepared_data))
                            text_chunks = self.json_splitter.split_text_recursively(text_content, self.json_splitter.max_text_char_limit)
                            
                            # Convert text chunks to dict format for consistent processing
                            chunk_dicts = [{"content": chunk} for chunk in text_chunks]
                            clustered_chunks = {"default": chunk_dicts}
                            
                    except Exception as e:
                        logger.error(f"Chunking failed for document {doc_id}: {e}")
                        # Fallback to simple chunking
                        clustered_chunks = {"default": [prepared_data]}
                    
                    # Process chunks for Weaviate ingestion
                    final_chunks = process_chunks_for_ingestion(
                        clustered_chunks, 
                        metadata, 
                        doc_id,
                        self.preserve_temporal_fields
                    )
                    
                    if not final_chunks:
                        logger.warning(f"No processable chunks created for document: {doc_id}")
                        results[doc_id] = (0, [])
                        continue
                    
                    # Prepare for batch ingestion using weaviate batch format
                    weaviate_batch_docs.append({
                        "doc_id": doc_id,
                        "chunks": final_chunks
                    })
                    
                    logger.info(f"Prepared {len(final_chunks)} chunks from {len(clustered_chunks)} clusters for document: {doc_id}")
                
                except Exception as e:
                    try:
                        doc_id = self._generate_doc_id(doc.metadata)
                    except:
                        doc_id = f'unknown_doc_{idx}'
                    
                    logger.error(f"Failed to process document {doc_id} for batch ingestion: {e}")
                    results[doc_id] = (0, [])
            
            # Perform batch ingestion using weaviate client's batch reingest method
            if weaviate_batch_docs:
                logger.info(f"Batch ingesting {len(weaviate_batch_docs)} documents using batch_reingest_documents")
                
                try:
                    batch_results = await self.weaviate_client.batch_reingest_documents(
                        weaviate_batch_docs, generate_vectors
                    )
                    
                    # Map results back from weaviate batch response
                    for doc_id, (deleted_count, new_uuids) in batch_results.items():
                        chunk_count = len(new_uuids)
                        results[doc_id] = (chunk_count, new_uuids)
                        logger.debug(f"Batch ingested document {doc_id}: deleted ~{deleted_count}, created {chunk_count} chunks")
                
                except Exception as e:
                    logger.error(f"Batch ingestion failed: {e}")
                    # Mark all documents as failed
                    for batch_doc in weaviate_batch_docs:
                        results[batch_doc["doc_id"]] = (0, [])
                    raise
            
            # Summary logging
            successful_docs = sum(1 for chunks, _ in results.values() if chunks > 0)
            total_chunks = sum(chunks for chunks, _ in results.values())
            
            logger.info(f"Completed batch ingestion: {successful_docs}/{len(document_list)} documents successful, "
                       f"{total_chunks} total chunks created")
            
            return results
            
        except Exception as e:
            logger.error(f"Failed batch ingestion: {e}", exc_info=True)
            raise


# Convenience functions for direct usage

async def ingest_single_document(
    document: CustomerDocumentSearchResult,
    weaviate_client: WeaviateChunkClient,
    generate_vectors: bool = True,
    chunking_config: Optional[Dict[str, Any]] = None
) -> Tuple[int, List[str]]:
    """
    Convenience function to ingest a single document with minimal setup.
    
    Args:
        document: CustomerDocumentSearchResult to ingest
        weaviate_client: Connected WeaviateChunkClient instance
        generate_vectors: Whether to generate embeddings
        chunking_config: Optional chunking configuration override
        
    Returns:
        Tuple[int, List[str]]: (chunks_created, chunk_uuids)
        
    Example:
        ```python
        async with WeaviateChunkClient() as client:
            chunks_created, uuids = await ingest_single_document(
                document=my_document,
                weaviate_client=client,
                generate_vectors=True,
                chunking_config={
                    "max_json_chunk_size": 500,
                    "text_overlap_percent": 15.0
                }
            )
        ```
    """
    config = chunking_config or {}
    pipeline = DocumentIngestionPipeline(weaviate_client, **config)
    results = await pipeline.ingest_documents(document, generate_vectors)
    
    # Extract result for single document
    if results:
        doc_id = list(results.keys())[0]
        return results[doc_id]
    return 0, []


async def ingest_multiple_documents(
    documents: List[CustomerDocumentSearchResult],
    weaviate_client: WeaviateChunkClient,
    generate_vectors: bool = True,
    chunking_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Tuple[int, List[str]]]:
    """
    Convenience function to ingest multiple documents with batch optimization.
    
    Args:
        documents: List of CustomerDocumentSearchResult to ingest
        weaviate_client: Connected WeaviateChunkClient instance
        generate_vectors: Whether to generate embeddings
        chunking_config: Optional chunking configuration override
        
    Returns:
        Dict[str, Tuple[int, List[str]]]: Mapping of doc_id to (chunks_created, chunk_uuids)
        
    Example:
        ```python
        async with WeaviateChunkClient() as client:
            results = await ingest_multiple_documents(
                documents=document_list,
                weaviate_client=client,
                chunking_config={
                    "max_text_char_limit": 800,
                    "preserve_temporal_fields": True
                }
            )
            
            for doc_id, (chunk_count, uuids) in results.items():
                print(f"Document {doc_id}: {chunk_count} chunks created")
        ```
    """
    config = chunking_config or {}
    pipeline = DocumentIngestionPipeline(weaviate_client, **config)
    return await pipeline.ingest_documents(documents, generate_vectors)


# Example usage and testing
async def example_usage():
    """
    Example demonstrating the document ingestion pipeline with various document types.
    
    This function shows how to:
    1. Set up the Weaviate client and ingestion pipeline
    2. Process different document types with appropriate chunking
    3. Handle both single document and batch ingestion scenarios
    4. Configure chunking parameters for different use cases
    5. Process both JSON and non-JSON document data
    6. Clean up test data after testing
    """
    
    # Sample JSON document metadata and data for testing
    json_metadata = CustomerDocumentSearchResultMetadata(
        namespace="user_strategy",
        docname="content_strategy_doc_john_doe",
        org_id=uuid4(),
        user_id_or_shared_placeholder="user_123",
        is_versioned=True,
        version="v1.0",
        is_shared=False,
        is_system_entity=False,
        is_versioning_metadata=False
    )
    
    json_data = {
        "title": "Content Strategy Document",
        "content_pillars": [
            {
                "name": "Technical Expertise",
                "pillar": "Authority Building",
                "sub_topic": "Advanced development techniques and best practices"
            },
            {
                "name": "Industry Insights", 
                "pillar": "Thought Leadership",
                "sub_topic": "Analysis of emerging technology trends"
            }
        ],
        "target_audience": {
            "primary": "Software engineers and technical leads",
            "secondary": "Engineering managers and CTOs"
        },
        "implementation": {
            "thirty_day_targets": {
                "goal": "Establish technical authority",
                "method": "Weekly technical deep-dive posts",
                "targets": ["2 technical tutorials", "1 architecture analysis"]
            }
        }
    }
    
    json_document = CustomerDocumentSearchResult(
        metadata=json_metadata,
        data=json_data
    )
    
    # Sample text document for testing non-JSON processing
    text_metadata = CustomerDocumentSearchResultMetadata(
        namespace="uploaded_files",
        docname="user_notes.txt",
        org_id=uuid4(),
        user_id_or_shared_placeholder="user_456",
        is_versioned=False,
        is_shared=False,
        is_system_entity=False,
        is_versioning_metadata=False
    )
    
    text_data = """
    This is a long text document that contains multiple paragraphs and sections.
    
    The first section talks about the importance of content strategy in modern business.
    Companies need to understand their audience and create content that resonates with them.
    
    The second section discusses technical implementation details. When building content systems,
    it's important to consider scalability, maintainability, and user experience. The architecture
    should support various content types and enable efficient content management workflows.
    
    The third section covers measurement and analytics. Content performance should be tracked
    using relevant metrics such as engagement rates, conversion rates, and audience growth.
    Regular analysis helps optimize content strategy and improve business outcomes.
    """
    
    text_document = CustomerDocumentSearchResult(
        metadata=text_metadata,
        data=text_data
    )
    
    # Keep track of test document IDs for cleanup
    test_doc_ids = []
    
    # Example of using the ingestion pipeline
    try:
        # Initialize Weaviate client (in real usage, this would be properly configured)
        async with WeaviateChunkClient() as client:
            await client.setup_schema()  # Ensure schema exists
            
            # Create pipeline instance to access doc_id generation
            pipeline = DocumentIngestionPipeline(client)
            
            # Generate doc_ids that will be created (for cleanup tracking)
            json_doc_id = pipeline._generate_doc_id(json_metadata)
            text_doc_id = pipeline._generate_doc_id(text_metadata)
            test_doc_ids.extend([json_doc_id, text_doc_id])
            
            print(f"Test documents to be created: {test_doc_ids}")
            
            # Single JSON document ingestion
            print("=== Single JSON Document Ingestion ===")
            chunks_created, chunk_uuids = await ingest_single_document(
                document=json_document,
                weaviate_client=client,
                generate_vectors=True,
                chunking_config={
                    "max_json_chunk_size": 500,
                    "max_text_char_limit": 600,
                    "text_overlap_percent": 25.0
                }
            )
            print(f"JSON Document: Created {chunks_created} chunks with UUIDs: {chunk_uuids[:3]}...")
            
            # Single text document ingestion
            print("\n=== Single Text Document Ingestion ===")
            chunks_created, chunk_uuids = await ingest_single_document(
                document=text_document,
                weaviate_client=client,
                generate_vectors=True,
                chunking_config={
                    "max_text_char_limit": 400,
                    "text_overlap_percent": 20.0
                }
            )
            print(f"Text Document: Created {chunks_created} chunks with UUIDs: {chunk_uuids[:3]}...")
            
            # Batch document ingestion with mixed document types
            print("\n=== Batch Mixed Document Ingestion ===")
            document_list = [json_document, text_document]
            batch_results = await ingest_multiple_documents(
                documents=document_list,
                weaviate_client=client,
                chunking_config={
                    "max_json_chunk_size": 400,
                    "max_text_char_limit": 350,
                    "preserve_temporal_fields": True
                }
            )
            
            for doc_id, (chunk_count, uuids) in batch_results.items():
                print(f"Document {doc_id}: {chunk_count} chunks created")
            
            # Verify documents were created by fetching them
            print("\n=== Verifying Test Documents Before Cleanup ===")
            before_cleanup = await client.batch_fetch_by_doc_ids(test_doc_ids)
            total_chunks_before = sum(len(chunks) for chunks in before_cleanup.values())
            print(f"Found {total_chunks_before} total chunks across {len([doc_id for doc_id, chunks in before_cleanup.items() if chunks])} documents")
            
            # Clean up test data using Weaviate client deletion methods
            print("\n=== Cleaning Up Test Data ===")
            deleted_doc_count, failed, matched, successful = await client.delete_by_doc_id(test_doc_ids)
            print(f"Cleanup results: ~{deleted_doc_count} doc_ids processed, {matched} chunks matched, {successful} successful deletions, {failed} failed")
            
            # Verify cleanup was successful
            print("\n=== Verifying Cleanup Completion ===")
            after_cleanup = await client.batch_fetch_by_doc_ids(test_doc_ids)
            total_chunks_after = sum(len(chunks) for chunks in after_cleanup.values())
            
            if total_chunks_after == 0:
                print("✅ All test data successfully cleaned up from Weaviate")
            else:
                print(f"⚠️  {total_chunks_after} test chunks still remain in Weaviate")
                for doc_id, chunks in after_cleanup.items():
                    if chunks:
                        print(f"  - Document {doc_id}: {len(chunks)} chunks remaining")
        
        print("\nIngestion pipeline example completed successfully with cleanup!")
        
    except Exception as e:
        print(f"Example failed: {e}")
        # If we're here and have a client connection, attempt cleanup anyway
        try:
            if test_doc_ids:
                print(f"\nAttempting emergency cleanup of test data: {test_doc_ids}")
                async with WeaviateChunkClient() as cleanup_client:
                    deleted_doc_count, failed, matched, successful = await cleanup_client.delete_by_doc_id(test_doc_ids)
                    print(f"Emergency cleanup: ~{deleted_doc_count} doc_ids processed, {matched} matched, {successful} successful, {failed} failed")
        except Exception as cleanup_error:
            print(f"Emergency cleanup also failed: {cleanup_error}")
        raise


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())
