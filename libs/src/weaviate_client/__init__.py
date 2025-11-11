"""
Weaviate Client Module

This module provides async client functionality for Weaviate operations.

The module is structured as follows:
- base_client: Generic WeaviateBaseClient that can be extended for different use cases
- docchunk_client: Specialized WeaviateChunkClient for document chunk management
- thread_message_client: Specialized ThreadMessageWeaviateClient for prompt compaction

For backward compatibility, the most commonly used classes are exported at the module level.
"""

# Base client for generic Weaviate operations
from .base_client import WeaviateBaseClient

# DocChunk-specific client and schema
from .docchunk_client import (
    ChunkSchema,
    WeaviateChunkClient,
)

# ThreadMessage client for prompt compaction
from .thread_message_client import ThreadMessageWeaviateClient

__all__ = [
    # Base client
    "WeaviateBaseClient",
    # DocChunk client (backward compatibility)
    "ChunkSchema",
    "WeaviateChunkClient",
    # ThreadMessage client
    "ThreadMessageWeaviateClient",
]

# Version of the weaviate_client module
__version__ = "0.2.0"
