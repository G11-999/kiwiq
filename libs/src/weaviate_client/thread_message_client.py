"""
Weaviate client for ThreadMessageChunks collection.

Stores message embeddings for per-workflow, per-node prompt compaction.
Each LLM node in a workflow maintains its own isolated message history and embeddings.

Collection Schema:
- thread_id: Workflow thread identifier (unique per workflow run)
- node_id: LLM node identifier
- sequence_no: Message sequence number in node's history
- message_id: Unique message identifier
- content: Message content (for reference)
- created_at: Timestamp
- embedding: Vector embedding
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from weaviate.classes.query import Filter
from weaviate.classes.config import Configure, Property, DataType
from weaviate_client.base_client import WeaviateBaseClient


class ThreadMessageWeaviateClient(WeaviateBaseClient):
    """
    Client for ThreadMessageChunks collection operations.

    Handles storage and retrieval of message embeddings for prompt compaction.
    """

    COLLECTION_NAME = "ThreadMessageChunks"

    def __init__(self, *args, **kwargs):
        """Initialize client with ThreadMessageChunks collection."""
        super().__init__(
            collection_name=self.COLLECTION_NAME,
            *args,
            **kwargs
        )

    async def setup_schema(self, recreate: bool = False) -> None:
        """
        Ensure ThreadMessageChunks collection exists with proper schema.

        Args:
            recreate: If True, delete and recreate the collection
        """
        # Define properties using Weaviate v4 API
        properties = [
            Property(
                name="thread_id",
                data_type=DataType.TEXT,
                description="Workflow thread identifier (unique per workflow run)",
                index_filterable=True,
                index_searchable=False,
                skip_vectorization=True,
            ),
            Property(
                name="node_id",
                data_type=DataType.TEXT,
                description="Node identifier (which LLM node this message belongs to)",
                index_filterable=True,
                index_searchable=False,
                skip_vectorization=True,
            ),
            Property(
                name="sequence_no",
                data_type=DataType.INT,
                description="Message sequence number within the node's message history",
                index_filterable=True,
                index_searchable=False,
                skip_vectorization=True,
            ),
            Property(
                name="message_id",
                data_type=DataType.TEXT,
                description="Unique message identifier",
                index_filterable=True,
                index_searchable=False,
                skip_vectorization=True,
            ),
            Property(
                name="content",
                data_type=DataType.TEXT,
                description="Message content (for reference and debugging)",
                index_searchable=True,
            ),
            Property(
                name="created_at",
                data_type=DataType.DATE,
                description="Timestamp when embedding was created",
                index_filterable=True,
                index_searchable=False,
                skip_vectorization=True,
            ),
            # v2.1: Chunk support for oversized messages
            Property(
                name="chunk_id",
                data_type=DataType.TEXT,
                description="Unique chunk identifier (format: chunk_{message_id}_{index}_{timestamp})",
                index_filterable=True,
                index_searchable=False,
                skip_vectorization=True,
            ),
            Property(
                name="chunk_index",
                data_type=DataType.INT,
                description="Chunk index within the message (0-based, None if not chunked)",
                index_filterable=True,
                index_searchable=False,
                skip_vectorization=True,
            ),
            Property(
                name="total_chunks",
                data_type=DataType.INT,
                description="Total number of chunks for this message (1 if not chunked)",
                index_filterable=True,
                index_searchable=False,
                skip_vectorization=True,
            ),
            Property(
                name="overlaps_next",
                data_type=DataType.BOOL,
                description="Whether this chunk overlaps with the next chunk (for context preservation)",
                index_filterable=True,
                index_searchable=False,
                skip_vectorization=True,
            ),
        ]

        # Use base client's setup_schema method with vectorizer none (we provide embeddings)
        vectorizer_config = Configure.Vectorizer.none()

        await super().setup_schema(
            properties=properties,
            vectorizer_config=vectorizer_config,
            description="Message embeddings for per-workflow, per-node prompt compaction",
            recreate=recreate,
        )

    async def get_thread_message_embedding(
        self,
        thread_id: str,
        node_id: str,
        message_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a message embedding by thread_id, node_id, and message_id.

        Args:
            thread_id: Workflow thread identifier
            node_id: LLM node identifier
            message_id: Unique message identifier

        Returns:
            {
                "embedding": List[float],
                "content": str,
                "sequence_no": int,
                "created_at": str,
            }
            or None if not found
        """
        where_filter = (
            Filter.by_property("thread_id").equal(thread_id) &
            Filter.by_property("node_id").equal(node_id) &
            Filter.by_property("message_id").equal(message_id)
        )

        result = await self.fetch_objects(
            where_filter=where_filter,
            limit=1,
            include_vector=True,  # Request vector in response
        )

        if result:
            obj = result[0]
            props = obj.get("properties", {})
            return {
                "embedding": obj.get("vector"),
                "content": props.get("content"),
                "sequence_no": props.get("sequence_no"),
                "created_at": props.get("created_at"),
            }

        return None

    async def store_thread_message_chunk(
        self,
        thread_id: str,
        node_id: str,
        sequence_no: int,
        message_id: str,
        embedding: List[float],
        content: str,
        chunk_id: Optional[str] = None,
        chunk_index: Optional[int] = None,
        total_chunks: Optional[int] = None,
        overlaps_next: Optional[bool] = None,
    ) -> str:
        """
        Store a message chunk with embedding in Weaviate (v2.1: supports chunking).

        Args:
            thread_id: Workflow thread identifier
            node_id: LLM node identifier
            sequence_no: Message sequence number within node's history
            message_id: Unique message identifier (base ID, not including chunk suffix)
            embedding: Vector embedding
            content: Message content (full message or chunk content)
            chunk_id: (v2.1) Unique chunk identifier (e.g., chunk_msg_123_0_170533)
            chunk_index: (v2.1) Chunk index (0-based) if message was chunked
            total_chunks: (v2.1) Total chunks for this message (1 if not chunked)
            overlaps_next: (v2.1) Whether chunk overlaps with next chunk

        Returns: UUID of created object
        """
        collection = self.client.collections.get(self.collection_name)

        properties = {
            "thread_id": thread_id,
            "node_id": node_id,
            "sequence_no": sequence_no,
            "message_id": message_id,
            "content": content,
            "created_at": datetime.now(timezone.utc).isoformat(),  # RFC3339 format with timezone
        }

        # Add chunk fields if provided (v2.1)
        if chunk_id is not None:
            properties["chunk_id"] = chunk_id
        if chunk_index is not None:
            properties["chunk_index"] = chunk_index
        if total_chunks is not None:
            properties["total_chunks"] = total_chunks
        if overlaps_next is not None:
            properties["overlaps_next"] = overlaps_next

        # Insert object with vector (async operation)
        result = await collection.data.insert(
            properties=properties,
            vector=embedding,
        )

        return str(result)

    async def query_thread_messages(
        self,
        thread_id: str,
        node_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query all messages for a specific thread and node.

        Args:
            thread_id: Workflow thread identifier
            node_id: LLM node identifier
            limit: Maximum number of results

        Returns list of messages:
        [
            {
                "message_id": str,
                "sequence_no": int,
                "content": str,
                "thread_id": str,
                "node_id": str,
                "embedding": List[float],
                "created_at": str,
            },
            ...
        ]
        """
        where_filter = (
            Filter.by_property("thread_id").equal(thread_id) &
            Filter.by_property("node_id").equal(node_id)
        )

        result = await self.fetch_objects(
            where_filter=where_filter,
            limit=limit,
            include_vector=True,  # Request vectors in response
        )

        # Convert to output format
        # Note: fetch_objects returns {uuid, properties, vector, metadata}
        # where properties contains the actual data
        messages = []
        for obj in result:
            props = obj.get("properties", {})
            messages.append({
                "message_id": props.get("message_id"),
                "sequence_no": props.get("sequence_no"),
                "content": props.get("content"),
                "thread_id": props.get("thread_id"),
                "node_id": props.get("node_id"),
                "embedding": obj.get("vector"),
                "created_at": props.get("created_at"),
            })

        return messages

    async def query_thread_messages_by_similarity(
        self,
        thread_id: str,
        node_id: str,
        query_embedding: List[float],
        limit: int = 10,
        min_similarity: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """
        Query messages within a specific node by vector similarity.

        Args:
            thread_id: Workflow thread identifier
            node_id: LLM node identifier
            query_embedding: Query vector
            limit: Maximum number of results
            min_similarity: Minimum similarity score

        Returns list of messages sorted by similarity score:
        [
            {
                "message_id": str,
                "sequence_no": int,
                "content": str,
                "similarity": float,
                "embedding": List[float],
            },
            ...
        ]
        """
        collection = self.client.collections.get(self.collection_name)

        # Vector search with filters (async operation)
        result = await collection.query.near_vector(
            near_vector=query_embedding,
            limit=limit,
            filters=(
                Filter.by_property("thread_id").equal(thread_id) &
                Filter.by_property("node_id").equal(node_id)
            ),
            return_metadata=["distance"],
        )

        # Convert to output format
        messages = []
        for obj in result.objects:
            # Convert distance to similarity (cosine distance: 0=identical, 2=opposite)
            # Similarity = 1 - (distance / 2)
            distance = obj.metadata.distance if obj.metadata else 1.0
            similarity = 1.0 - (distance / 2.0)

            if similarity >= min_similarity:
                messages.append({
                    "message_id": obj.properties.get("message_id"),
                    "sequence_no": obj.properties.get("sequence_no"),
                    "content": obj.properties.get("content"),
                    "similarity": similarity,
                    "embedding": obj.vector,
                })

        return messages

    async def delete_thread_messages(
        self,
        thread_id: str,
        node_id: Optional[str] = None,
        older_than_days: Optional[int] = None,
    ) -> int:
        """
        Delete messages for a thread (optionally filtered by node and age).

        Args:
            thread_id: Workflow thread identifier
            node_id: Optional node filter (None = all nodes in thread)
            older_than_days: Optional age filter (None = all messages)

        Returns: Number of objects deleted
        """
        collection = self.client.collections.get(self.collection_name)

        # Build filters
        where_filter = Filter.by_property("thread_id").equal(thread_id)

        if node_id:
            where_filter = where_filter & Filter.by_property("node_id").equal(node_id)

        if older_than_days:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)
            where_filter = where_filter & Filter.by_property("created_at").less_than(cutoff_date.isoformat())

        # Delete objects (async operation)
        result = await collection.data.delete_many(
            where=where_filter
        )

        return result.successful if result else 0

    async def cleanup_old_threads(self, days: int) -> int:
        """
        Cleanup threads older than specified days.

        Args:
            days: Delete threads older than this many days

        Returns: Number of objects deleted
        """
        collection = self.client.collections.get(self.collection_name)

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Delete all messages older than cutoff (async operation)
        result = await collection.data.delete_many(
            where=Filter.by_property("created_at").less_than(cutoff_date.isoformat())
        )

        return result.successful if result else 0
