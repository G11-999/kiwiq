from pymongo import AsyncMongoClient

import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple, Union, Set, Iterable, TypeVar, Generic, Callable
from bson import ObjectId
import uuid

from global_config.logger import get_logger

# Configure logging
logger = get_logger(__name__)

# Type variables for generic return types
T = TypeVar('T')
U = TypeVar('U')

class AsyncMongoDBClient:
    """
    An asynchronous MongoDB client designed to manage documents using a structured path-based approach.
    
    Features:
    - Fully asynchronous operations using motor_asyncio
    - Supports variable segment counts in path keys (not fixed to 4 segments)
    - Full CRUD operations with permissions
    - Wildcard pattern searching, listing and deletion
    - Text search capabilities
    - Permission validation for operations
    - Index management
    - Batch operation support for improved performance
    - Document path is used as ID for efficient lookups and uniqueness
    
    Documents are stored with segments as individual fields for efficient querying.
    """
    
    # Secure delimiter that's unlikely to appear in path segments
    PATH_DELIMITER = ":::"
    DOC_TYPE_KEY = "__doc_type__"
    DOC_TYPE_UNVERSIONED = "unversioned"
    DOC_TYPE_VERSIONED = "versioned"

    def __init__(
        self, 
        uri: str,
        database: str,
        collection: str,
        segment_names: Optional[List[str]] = None,
        text_search_fields: Optional[List[str]] = None,
        value_filter_fields: Optional[List[str]] = None,  # fields within document such as `xyz` which will be stored under `data.xyz`; only specify xyz!
        version_mode: Optional[str] = DOC_TYPE_UNVERSIONED,
        **kwargs
    ):
        """
        Initialize MongoDB client with connection to specified database and collection.
        
        Args:
            uri: MongoDB connection URI
            database: Database name
            collection: Collection name
            segment_names: Optional list of segment field names. If not provided,
                          segments will be named "segment_0", "segment_1", etc.
            text_search_fields: Fields within 'data' to include in text index
            **kwargs: Additional motor client options
        """
        self.uri = uri
        self.database = database
        self.collection_name = collection
        self.segment_names = segment_names or []
        self.text_search_fields = text_search_fields or []
        self.value_filter_fields = value_filter_fields or []
        self.connection_params = kwargs
        self.version_mode = version_mode
        
        # Connection objects (initialized lazily)
        self._client = None
        self._db = None
        self._collection = None
        
        logger.info(f"AsyncMongoDB client configured for: {uri}, DB: {database}, Collection: {collection}")
    
    # =========================================================================
    # CONNECTION MANAGEMENT
    # =========================================================================
    
    async def _connect(self):
        """Establishes MongoDB connection and gets DB/collection objects.
        # TODO: Add exponential backoff and retry logic!
        """
        try:
            logger.info("Connecting to MongoDB asynchronously...")
            # Create async client with serverSelectionTimeoutMS for faster timeout
            self._client = AsyncMongoClient(
                self.uri, 
                serverSelectionTimeoutMS=5000,
                **self.connection_params
            )
            
            # Verify connection is working
            await self._client.admin.command('ping')
            
            self._db = self._client[self.database]
            self._collection = self._db[self.collection_name]
            logger.info("Successfully connected to MongoDB.")
        except Exception as e:
            logger.error(f"MongoDB connection error: {e}")
            self._client = None
            self._db = None
            self._collection = None
            raise
    
    async def _get_collection(self):  #  -> motor.motor_asyncio.AsyncIOMotorCollection:
        """Ensures connection exists and returns the collection object."""
        if self._client is None or self._collection is None:
            logger.debug("MongoDB connection not established. Connecting...")
            await self._connect()
        
        # Verify connection is still alive
        try:
            if self._client:
                await self._client.admin.command('ping')
            else:
                raise ConnectionError("Client object is None after connect attempt.")
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            # Try to reconnect once
            await self._connect()
        
        if self._collection is None:
            raise ConnectionError("Collection object is None after connection check.")
        
        return self._collection
    
    async def ping(self) -> bool:
        """
        Checks if MongoDB connection is active.
        
        Returns:
            True if connection is active
        """
        try:
            if not self._client:
                await self._connect()
            
            result = await self._client.admin.command('ping')
            return result.get('ok', 0) == 1
        except Exception as e:
            logger.error(f"MongoDB ping failed: {e}")
            return False
    
    async def close(self):
        """Closes the MongoDB connection."""
        if self._client:
            logger.info("Closing MongoDB connection...")
            await self._client.close()
            self._client = None
            self._db = None
            self._collection = None
            logger.info("MongoDB connection closed.")
    
    # =========================================================================
    # PATH AND ID UTILITIES
    # =========================================================================
    
    def _path_to_id(self, path: List[str]) -> str:
        """
        Converts a path list to a document ID.
        This is a one-way operation - we never parse IDs back into paths.
        
        Args:
            path: Path as list of segments
            
        Returns:
            String ID created from path
        """
        # Security note: We never split this ID to get path components
        # Path components are always stored in separate fields for querying
        return self.PATH_DELIMITER.join(path)
    
    def _validate_document_path(self, path: List[str]) -> None:
        """
        Validates a document path (not a pattern).
        
        Args:
            path: Path as list of segments
            
        Raises:
            ValueError: If path contains wildcard characters or empty segments
        """
        if not isinstance(path, list):
            raise ValueError(f"Path must be a list of strings, not {type(path)}")
            
        # # Check for empty segments
        if any(not segment for segment in path):
            raise ValueError(f"Path {path} contains empty segments, which is not allowed")
        
        # Check for wildcard characters in actual document paths
        for i, segment in enumerate(path):
            if not isinstance(segment, str):
                raise ValueError(f"Path segment {i} is not a string: {segment}")
                
            if '*' in segment:
                raise ValueError(f"Path segment {i} '{segment}' contains wildcard character '*', which is not allowed in document paths")
            
            # Check for path delimiter in segments, which would break our ID scheme
            if self.PATH_DELIMITER in segment:
                raise ValueError(f"Path segment {i} '{segment}' contains the reserved delimiter '{self.PATH_DELIMITER}', which is not allowed")
    
    def _validate_pattern(self, pattern: List[str]) -> None:
        """
        Validates a pattern (can contain wildcards).
        
        Args:
            pattern: Pattern as list of segments
            
        Raises:
            ValueError: If pattern format is invalid
        """
        if not isinstance(pattern, list):
            raise ValueError(f"Pattern must be a list of strings, not {type(pattern)}")
            
        # NOTE: this behaviour has changed so that patterns can have None for a segment to only fetch docs without that segment!
        # # Check for empty segments
        # if any(not isinstance(segment, str) or not segment for segment in pattern):
        #     raise ValueError(f"Pattern {pattern} contains empty segments, which is not allowed")
        
        # Check for path delimiter in segments
        for i, segment in enumerate(pattern):
            if segment and self.PATH_DELIMITER in segment:
                raise ValueError(f"Pattern segment {i} '{segment}' contains the reserved delimiter '{self.PATH_DELIMITER}', which is not allowed")
    
    def _validate_allowed_prefixes(self, allowed_prefixes: List[List[str]]) -> None:
        """
        Validates allowed prefixes format.
        
        Args:
            allowed_prefixes: List of prefix patterns as lists
            
        Raises:
            ValueError: If format is invalid
        """
        if not isinstance(allowed_prefixes, list):
            raise ValueError(f"allowed_prefixes must be a list of lists, not {type(allowed_prefixes)}")
            
        for i, prefix in enumerate(allowed_prefixes):
            if not isinstance(prefix, list):
                raise ValueError(f"Each prefix must be a list of strings, not {type(prefix)}. Error at prefix {i}: {prefix}")
                
            # Check for empty segments
            if any(not isinstance(segment, str) or not segment for segment in prefix):
                raise ValueError(f"Prefix {i} {prefix} contains empty segments, which is not allowed")
            
            # Check for path delimiter in segments
            for j, segment in enumerate(prefix):
                if self.PATH_DELIMITER in segment:
                    raise ValueError(f"Prefix {i} segment {j} '{segment}' contains the reserved delimiter '{self.PATH_DELIMITER}', which is not allowed")
    
    def _path_to_segments(self, path: List[str]) -> Dict[str, str]:
        """
        Converts a path list to a dictionary of segment fields.
        
        Args:
            path: Path as list of segments
            
        Returns:
            Dictionary mapping segment names to values
        
        Raises:
            ValueError: If path doesn't have enough segments
        """
        # Ensure we have enough segment names
        if len(self.segment_names) < len(path):
            raise ValueError(f"Path {path} contains more segments than the segment names defined: {self.segment_names}")
        
        # Create mapping of segment names to values
        return {self.segment_names[i]: segment for i, segment in enumerate(path)}
    
    def _segments_to_path(self, segments: Dict[str, str]) -> List[str]:
        """
        Converts segment dictionary back to a path list.
        
        Args:
            segments: Dictionary of segment names to values
            
        Returns:
            Path as list of segments
        """
        # Sort segments by their position in segment_names to ensure correct order
        path = []
        for name in self.segment_names:
            if name in segments:
                path.append(segments[name])
            else:
                break
        
        return path
    
    # =========================================================================
    # PERMISSION VALIDATION
    # =========================================================================
    
    def _validate_path_permission(
        self, 
        path: List[str], 
        allowed_prefixes: List[List[str]]
    ) -> bool:
        """
        Validates if a path is allowed based on the allowed prefixes.
        
        Args:
            path: Path as list of segments
            allowed_prefixes: List of allowed prefix patterns as lists
            
        Returns:
            True if path is allowed, False otherwise
            
        NOTE: CRITICAL security consideration: the User ID / Name, Org ID / Name, project ID / Name, namespace etc
        can never be a wildcard character i.e. `*`!
        """
        if not allowed_prefixes:
            return True  # No restrictions
        
        # Check if any prefix gives "allow all" access
        if any(prefix == ["*"] for prefix in allowed_prefixes):
            return True
            
        for prefix in allowed_prefixes:
            # # Skip if prefix has more segments than path
            # if len(prefix) > len(path):
            #     continue
                
            # Check if each segment matches (accounting for wildcards)
            matches = True
            for i, prefix_segment in enumerate(prefix):
                if prefix_segment == '*':
                    # Wildcard matches any segment
                    continue
                elif i >= len(path) or prefix_segment != path[i]:
                    matches = False
                    break
            
            if matches:
                return True
        
        return False
    
    # =========================================================================
    # QUERY BUILDING
    # =========================================================================
    
    def _build_exact_path_query(self, path: List[str]) -> Dict[str, Any]:
        """
        Builds a query to match a document by exact path.
        For exact path queries, we use the document ID for efficiency.
        
        Args:
            path: Path as list of segments
            
        Returns:
            MongoDB query dictionary for exact path match
        """
        return {"_id": self._path_to_id(path)}
    
    def _build_segment_query(self, pattern: List[str]) -> Dict[str, Any]:
        """
        Builds a MongoDB query dictionary based on path segments from a pattern.
        Handles '*' as a wildcard for a segment.
        
        Args:
            pattern: Pattern with wildcards as list
            
        Returns:
            MongoDB query dictionary
        
        NOTE: TODO: query if segments unset!
        # all docs where “myField” is not present
        cursor = collection.find({ "myField": { "$exists": False } })

        # matches docs where myField == null OR myField is missing
        cursor = collection.find({ "myField": None })
        """
        # Validate pattern
        self._validate_pattern(pattern)
        
        # Ensure we have enough segment names
        if len(self.segment_names) < len(pattern):
            raise ValueError(f"Pattern has {len(pattern)} segments, but only {len(self.segment_names)} segment names defined")
        
        query = {}
        for i, part in enumerate(pattern):
            if i >= len(self.segment_names):
                break
                
            if part == '*':
                continue  # Skip wildcard segments
            else:
                segment_name = self.segment_names[i]
                
                # Handle embedded wildcards within a segment (e.g., "ab*cd")
                if part and '*' in part:
                    # Escape special regex characters except *
                    escaped_part = part
                    for char in '.^$+?()[]{}|\\':
                        escaped_part = escaped_part.replace(char, '\\' + char)
                    regex_pattern = '^' + escaped_part.replace('*', '.*') + '$'
                    query[segment_name] = {'$regex': regex_pattern}
                else:
                    query[segment_name] = part
        
        return query
    
    def _build_permission_query(self, allowed_prefixes: List[List[str]]) -> Dict[str, Any]:
        """
        Builds a MongoDB query component for checking allowed prefixes.
        
        Args:
            allowed_prefixes: List of allowed prefix patterns as lists
            
        Returns:
            MongoDB query for permission filtering
        
        NOTE: CRITICAL security consideration: the User ID / Name, Org ID / Name, project ID / Name, namespace etc
        can never be a wildcard character i.e. `*`!
        """
        if not allowed_prefixes:
            return {}  # No permission restrictions
        
        # Validate allowed prefixes
        self._validate_allowed_prefixes(allowed_prefixes)
        
        # Check for allow all access
        if any(prefix == ["*"] for prefix in allowed_prefixes):
            return {}  # Allow all access
        
        or_clauses = []
        for prefix in allowed_prefixes:
            if not prefix:
                continue  # Skip empty prefixes
            
            # Ensure no empty segments within the prefix
            if any(not part for part in prefix):
                logger.warning(f"Skipping prefix with empty segments: {prefix}")
                continue
            
            # Ensure we have enough segment names
            if len(self.segment_names) < len(prefix):
                logger.warning(f"Prefix has more segments than defined segment names: {prefix}")
                continue
            
            clause = {}
            all_wildcards = True
            for i, part in enumerate(prefix):
                if i >= len(self.segment_names):
                    break
                    
                if part != '*':  # Skip wildcard segments in prefix
                    all_wildcards = False
                    segment_name = self.segment_names[i]
                    clause[segment_name] = part
            
            # Skip prefixes that are all wildcards beyond ["*"]
            if all_wildcards and len(prefix) > 1:
                logger.warning(f"Skipping prefix with all wildcards beyond ['*']: {prefix}")
                continue
                
            if clause:  # Only add non-empty clauses
                or_clauses.append(clause)
        
        if not or_clauses:
            logger.warning("No valid permission prefixes provided, effectively denying all access.")
            return {"_id": {"$exists": False}}  # Query that matches nothing
        
        return {"$or": or_clauses}
    
    def _combine_queries(self, *queries: Dict[str, Any]) -> Dict[str, Any]:
        """
        Combines multiple query dictionaries using $and.
        
        Args:
            *queries: Query dictionaries to combine
            
        Returns:
            Combined MongoDB query
        """
        # Filter out empty queries and impossible queries
        valid_queries = []
        for q in queries:
            if not q:
                continue  # Skip empty queries
                
            if q == {"_id": {"$exists": False}}:
                return {"_id": {"$exists": False}}  # Short-circuit with impossible query
                
            valid_queries.append(q)
        
        if not valid_queries:
            return {}
            
        if len(valid_queries) == 1:
            return valid_queries[0]
        
        # Flatten nested $and clauses
        final_clauses = []
        for q in valid_queries:
            if "$and" in q:
                final_clauses.extend(q["$and"])
            else:
                final_clauses.append(q)
        
        return {"$and": final_clauses}
    
    # =========================================================================
    # DOCUMENT PROCESSING UTILITIES
    # =========================================================================
    
    def _prepare_document(self, path: List[str], data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        Prepares a document for insertion/update.
        
        Args:
            path: Path as list of segments
            data: Document data
            
        Returns:
            Prepared document
        """
        segments = self._path_to_segments(path)
        
        return {
            "_id": self._path_to_id(path),
            **segments,
            "data": data,
            AsyncMongoDBClient.DOC_TYPE_KEY: self.version_mode,
        }
    
    async def _process_operation_with_retry(
        self, 
        operation: Callable[..., T], 
        *args: Any, 
        **kwargs: Any
    ) -> T:
        """
        Processes a MongoDB operation with retry logic.
        
        Args:
            operation: Async function to call
            *args: Positional arguments for the operation
            **kwargs: Keyword arguments for the operation
            
        Returns:
            Result of the operation
            
        Raises:
            Exception: If operation fails after retry
        """
        try:
            return await operation(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Operation failed: {e}. Retrying once...")
            try:
                # Try reconnecting
                await self._connect()
                # Retry operation
                return await operation(*args, **kwargs)
            except Exception as retry_e:
                logger.error(f"Operation failed after retry: {retry_e}")
                raise
    
    async def _process_batch(
        self, 
        items: List[T], 
        process_func: Callable[[List[T]], U], 
        chunk_size: int = 100
    ) -> U:
        """
        Processes a batch of items in chunks.
        
        Args:
            items: List of items to process
            process_func: Function to process each chunk
            chunk_size: Size of each chunk
            
        Returns:
            Combined results from all chunks
        """
        results = []
        for i in range(0, len(items), chunk_size):
            chunk = items[i:i+chunk_size]
            chunk_result = await process_func(chunk)
            results.append(chunk_result)
        return results
    
    # =========================================================================
    # SETUP & MANAGEMENT
    # =========================================================================
    
    async def setup(self) -> bool:
        """
        Sets up necessary indexes for the collection.
        
        Database round trips:
        1. One round trip to get current indexes
        2. One round trip to create segment compound index (if needed)
        3. One round trip to get current indexes again (if text index needed)
        4. One round trip to create text index (if needed)
        
        Returns:
            True if setup completes successfully
        """
        logger.info("Setting up MongoDB indexes...")
        try:
            collection = await self._get_collection()
            
            # Create compound index on all segment fields
            if self.segment_names:
                compound_index_name = f"segment_compound_idx_{'__'.join(self.segment_names)}"
                compound_index_key = [(field, 1) for field in self.segment_names]  # 1 = ASCENDING
                
                # Get current indexes
                indexes = await collection.index_information()
                
                if compound_index_name not in indexes:
                    logger.info(f"Creating compound index on segment fields: {self.segment_names}")
                    await collection.create_index(
                        compound_index_key,
                        name=compound_index_name,
                        background=True
                    )
                    logger.info("Compound index created.")
                else:
                    logger.info(f"Compound index '{compound_index_name}' already exists.")
            
            # Create text index if text search fields are configured
            if self.text_search_fields:
                text_index_name = "data_text_idx"
                text_index_keys = [(f"data.{field}", "text") for field in self.text_search_fields]
                
                # Get current indexes
                indexes = await collection.index_information()
                
                if text_index_name not in indexes:
                    logger.info(f"Creating text index on fields: {self.text_search_fields}")
                    await collection.create_index(
                        text_index_keys,
                        name=text_index_name,
                        default_language='english',
                        background=True
                    )
                    logger.info("Text index created.")
                else:
                    logger.info(f"Text index '{text_index_name}' already exists.")
            
            # Create indexes on value filter fields if configured
            if self.value_filter_fields:
                for field in self.value_filter_fields:
                    value_index_name = f"data_{field}_idx"
                    
                    # Get current indexes if we haven't already
                    indexes = await collection.index_information()
                    
                    if value_index_name not in indexes:
                        logger.info(f"Creating index on value filter field: data.{field}")
                        await collection.create_index(
                            [(f"data.{field}", 1)],
                            name=value_index_name,
                            background=True
                        )
                        logger.info(f"Value filter index '{value_index_name}' created.")
                    else:
                        logger.info(f"Value filter index '{value_index_name}' already exists.")
            
            # Make sure _id field is indexed (should be by default)
            await collection.create_index([("_id", 1)])
            
            logger.info("MongoDB setup complete.")
            return True
            
        except Exception as e:
            logger.error(f"Error during MongoDB setup: {e}")
            return False
    
    async def reset_collection(self, confirm: bool = False) -> Optional[Dict[str, Any]]:
        """
        !! DANGER !! Deletes ALL documents in the collection.
        
        Database round trips:
        1. One round trip to delete all documents
        
        Args:
            confirm: Must be True to proceed with deletion
            
        Returns:
            Result dictionary with deletion count
            
        Raises:
            ValueError: If confirm is not True
        """
        if not confirm:
            raise ValueError("Confirmation required to reset the collection.")
        
        collection = await self._get_collection()
        logger.warning(f"!!! DELETING ALL DOCUMENTS in collection '{self.database}.{self.collection_name}' !!!")
        
        try:
            result = await collection.delete_many({})
            deleted_count = result.deleted_count
            logger.info(f"Deleted {deleted_count} documents from collection.")
            return {"deleted_count": deleted_count}
        except Exception as e:
            logger.error(f"Error deleting documents: {e}")
            raise
    
    async def drop_collection(self, confirm: bool = False) -> bool:
        """
        !! DANGER !! Drops the entire collection including indexes.
        
        Database round trips:
        1. One round trip to list collections
        2. One round trip to drop the collection (if it exists)
        
        Args:
            confirm: Must be True to proceed with dropping
            
        Returns:
            True if collection was dropped successfully
            
        Raises:
            ValueError: If confirm is not True
        """
        if not confirm:
            raise ValueError("Confirmation required to drop the collection.")
        
        if not self._db:
            await self._connect()
        
        # Check if collection exists
        collections = await self._db.list_collection_names()
        if self.collection_name in collections:
            logger.warning(f"!!! DROPPING COLLECTION '{self.database}.{self.collection_name}' !!!")
            
            try:
                await self._db.drop_collection(self.collection_name)
                logger.info(f"Collection '{self.database}.{self.collection_name}' dropped successfully.")
                self._collection = None
                return True
            except Exception as e:
                logger.error(f"Error dropping collection: {e}")
                raise
        else:
            logger.info(f"Collection '{self.database}.{self.collection_name}' does not exist.")
            return True
    
    # =========================================================================
    # SINGLE DOCUMENT OPERATIONS
    # =========================================================================
    
    async def create_object(
        self, 
        path: List[str], 
        data: Dict[str, Any],
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> str:
        """
        Creates a new document using segmented path structure.
        
        Database round trips:
        1. One round trip to insert the document
        
        Args:
            path: Path as list of segments (e.g., ["org", "user", "namespace", "object_name"])
            data: JSON data to store
            allowed_prefixes: Optional list of allowed path prefixes as lists
            
        Returns:
            ID (based on path) of the created document
            
        Raises:
            ValueError: If path format is invalid or access is denied
        """
        # Validate document path
        self._validate_document_path(path)
        
        # Check permissions
        if allowed_prefixes and not self._validate_path_permission(path, allowed_prefixes):
            error_msg = f"Access denied for path '{path}' based on allowed prefixes"
            logger.warning(error_msg)
            raise ValueError(error_msg)
        
        # Prepare document
        document = self._prepare_document(path, data)
        doc_id = document["_id"]
        
        # Insert document
        collection = await self._get_collection()
        try:
            # We use replace_one with upsert instead of insert_one to handle the case
            # where a document with this ID already exists (ensuring uniqueness at path)
            result = await collection.replace_one(
                {"_id": doc_id},
                document,
                upsert=True
            )
            logger.info(f"Created document with path '{path}', ID: {doc_id}")
            return doc_id
        except Exception as e:
            logger.error(f"Error creating document for path '{path}': {e}")
            raise

    async def update_object(
        self, 
        path: List[str], 
        data: Any,
        allowed_prefixes: Optional[List[List[str]]] = None,
        update_subfields: bool = False
    ) -> Optional[str]:
        """
        Updates an existing document identified by its path.
        
        Database round trips:
        1. One round trip to update the document
        
        Args:
            path: Path as list of segments
            data: New data to store
            allowed_prefixes: Optional list of allowed path prefixes as lists
            update_subfields: If True, updates only specified subfields within data
                              using dot notation (data.field_name) instead of replacing
                              the entire data object
            
        Returns:
            ID of the updated document, or None if not found
            
        Raises:
            ValueError: If path format is invalid or access is denied
        """
        # Validate document path
        self._validate_document_path(path)
        
        # Check permissions
        if allowed_prefixes and not self._validate_path_permission(path, allowed_prefixes):
            error_msg = f"Access denied for path '{path}' based on allowed prefixes"
            logger.warning(error_msg)
            raise ValueError(error_msg)
        
        # Build query for exact path
        query = self._build_exact_path_query(path)
        doc_id = self._path_to_id(path)
        
        # Update document
        collection = await self._get_collection()
        try:
            # Construct update operation based on update_subfields flag
            if update_subfields:
                # Create update with individual field updates using dot notation
                update_fields = {}
                if isinstance(data, dict):
                    for key, value in data.items():
                        update_fields[f"data.{key}"] = value
                else:
                    update_fields["data"] = data
                
                update_operation = {"$set": update_fields}
                logger.debug(f"Updating specific subfields: {list(update_fields.keys())}")
            else:
                # Replace entire data object
                update_operation = {"$set": {"data": data}}
            
            result = await collection.update_one(query, update_operation)
            
            if result.matched_count == 0:
                logger.info(f"No document found with path '{path}' to update.")
                return None
            
            if result.modified_count > 0:
                if update_subfields:
                    logger.info(f"Updated {len(data) if isinstance(data, dict) else 1} subfields for document at path '{path}'.")
                else:
                    logger.info(f"Updated entire data object for path '{path}'.")
            else:
                logger.info(f"Document found for path '{path}' but data was identical.")
                
            return doc_id
        except Exception as e:
            logger.error(f"Error updating document for path '{path}': {e}")
            raise
    
    async def create_or_update_object(
        self, 
        path: List[str], 
        data: Dict[str, Any],
        allowed_prefixes: Optional[List[List[str]]] = None,
        update_subfields: bool = False
    ) -> Tuple[str, bool]:
        """
        Creates a document if it doesn't exist, or updates existing document.
        
        Database round trips:
        1. TODO: FIXME: One round trip to perform the upsert operation
        Current implementation performs 2 round trips:
        - First to check if document exists
        - Second to perform the upsert (create or update) operation
        
        Args:
            path: Path as list of segments
            data: Data to store
            allowed_prefixes: Optional list of allowed path prefixes as lists
            
        Returns:
            Tuple of (document ID, was_created)
            
        Raises:
            ValueError: If path format is invalid or access is denied
        """
        # Validate document path
        self._validate_document_path(path)
        
        # Check permissions
        if allowed_prefixes and not self._validate_path_permission(path, allowed_prefixes):
            error_msg = f"Access denied for path '{path}' based on allowed prefixes"
            logger.warning(error_msg)
            raise ValueError(error_msg)
        
        # Prepare document (including all segment fields)
        document = self._prepare_document(path, data)
        doc_id = document["_id"]
        
        # Perform upsert
        collection = await self._get_collection()
        try:
            # Check if document exists
            existing = await collection.find_one({"_id": doc_id}, {"_id": 1})
            was_created = existing is None
            
            if was_created:
                # Insert new document
                await collection.insert_one(document)
                logger.info(f"Created document for path '{path}', ID: {doc_id}")
            else:
                # Update existing document
                doc_id = await self.update_object(
                    path=path, 
                    data=data,
                    allowed_prefixes=allowed_prefixes,
                    update_subfields=update_subfields
                )
                logger.info(f"Updated document for path '{path}', ID: {doc_id}")
            
            return doc_id, was_created
        except Exception as e:
            logger.error(f"Error during create_or_update for path '{path}': {e}")
            raise
    
    async def fetch_object(
        self, 
        path: List[str], 
        allowed_prefixes: Optional[List[List[str]]] = None,
        include_fields: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetches a document by exact path, with optional permission check.
        
        Database round trips:
        1. One round trip to fetch the document
        
        Args:
            path: Path as list of segments
            allowed_prefixes: Optional list of allowed path prefixes as lists
            include_fields: Optional list of fields to include in the results

        Returns:
            Document if found and allowed, None otherwise
            
        Raises:
            ValueError: If path format is invalid
        """
        try:
            # Validate document path
            self._validate_document_path(path)
            
            # Quick client-side permission check
            if allowed_prefixes and not self._validate_path_permission(path, allowed_prefixes):
                logger.info(f"Access denied for path '{path}' based on allowed prefixes.")
                return None
            
            # Build query for exact path
            query = self._build_exact_path_query(path)
            
            # Fetch document
            collection = await self._get_collection()

            kwargs = {}
            if include_fields:
                kwargs["projection"] = {field: 1 for field in include_fields}
                # Always include _id field
                if "_id" not in kwargs["projection"]:
                    kwargs["projection"]["_id"] = 1

            document = await collection.find_one(query, **kwargs)
            
            if document:
                logger.debug(f"Fetched document for path '{path}'")
                return document
            else:
                logger.debug(f"No document found for path '{path}'")
                return None
        except ValueError as e:
            logger.error(f"Invalid path format for '{path}': {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching document for path '{path}': {e}")
            raise
    
    async def delete_object(
        self,
        path: List[str],
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> bool:
        """
        Deletes a specific document by its path.
        
        Database round trips:
        1. One round trip to delete the document
        
        Args:
            path: Path as list of segments
            allowed_prefixes: Optional list of allowed path prefixes as lists
            
        Returns:
            True if document was deleted, False if not found
            
        Raises:
            ValueError: If path format is invalid or access is denied
        """
        # Validate document path
        self._validate_document_path(path)
        
        # Check permissions
        if allowed_prefixes and not self._validate_path_permission(path, allowed_prefixes):
            error_msg = f"Access denied for path '{path}' based on allowed prefixes"
            logger.warning(error_msg)
            raise ValueError(error_msg)
        
        # Build query for exact path
        query = self._build_exact_path_query(path)
        
        # Delete document
        collection = await self._get_collection()
        try:
            result = await collection.delete_one(query)
            if result.deleted_count > 0:
                logger.info(f"Deleted document with path '{path}'")
                return True
            else:
                logger.info(f"No document found with path '{path}' to delete")
                return False
        except Exception as e:
            logger.error(f"Error deleting document for path '{path}': {e}")
            raise
    
    # =========================================================================
    # QUERY OPERATIONS
    # =========================================================================
    
    async def list_objects(
        self,
        pattern: List[str] = ["*", "*"],
        allowed_prefixes: Optional[List[List[str]]] = None,
        include_data: bool = False
    ) -> List[Union[List[str], Dict[str, Any]]]:
        """
        Lists objects matching a pattern, filtered by permissions.
        
        Database round trips:
        1. One round trip to fetch matching documents
        
        Args:
            pattern: Path pattern with wildcards as list
            allowed_prefixes: Optional list of allowed path prefixes as lists
            include_data: Whether to include document data or just paths
            
        Returns:
            List of paths (as lists) or complete documents
            
        Raises:
            ValueError: If pattern format is invalid
        """
        # Validate pattern
        self._validate_pattern(pattern)
        
        collection = await self._get_collection()
        
        try:
            # Build queries
            pattern_query = self._build_segment_query(pattern)
            permission_query = self._build_permission_query(allowed_prefixes or [])
            final_query = self._combine_queries(pattern_query, permission_query)
            
            if final_query == {"_id": {"$exists": False}}:  # Deny-all case
                logger.info("Listing objects denied due to permissions.")
                return []
            
            logger.debug(f"Listing objects with query: {final_query}")
            
            # Determine what fields to return
            projection = None if include_data else {field: 1 for field in self.segment_names}
            
            results = []
            async for doc in collection.find(final_query, projection=projection):
                if include_data:
                    results.append(doc)
                else:
                    # Reconstruct path from segments
                    path_segments = {}
                    for field in self.segment_names:
                        if field in doc:
                            path_segments[field] = doc[field]
                    
                    # Skip documents that don't have expected segments
                    # if len(path_segments) < len(pattern):
                    #     continue
                    
                    # Return paths as lists
                    path_list = self._segments_to_path(path_segments)
                    results.append(path_list)
            
            logger.info(f"Found {len(results)} objects matching pattern '{pattern}'")
            return results
        except ValueError as e:
            logger.error(f"Invalid pattern format for '{pattern}': {e}")
            raise
        except Exception as e:
            logger.error(f"Error listing objects with pattern '{pattern}': {e}")
            raise
    
    async def search_objects(
        self,
        key_pattern: List[str] = ["*", "*"],
        text_search_query: Optional[str] = None,
        value_filter: Optional[Dict[str, Any]] = None,
        allowed_prefixes: Optional[List[List[str]]] = None,
        value_sort_by: Optional[List[Tuple[str, int]]] = None,
        include_fields: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Searches objects by pattern, text search, and value filters.
        
        Database round trips:
        1. One round trip to search for documents
        
        Args:
            key_pattern: Path pattern with wildcards as list
            text_search_query: Optional text search query
            value_filter: Optional data field filters
            allowed_prefixes: Optional list of allowed path prefixes as lists
            value_sort_by: Optional list of sort fields and directions
            include_fields: Optional list of fields to include in the results
            
        Returns:
            List of matching documents
            
        Raises:
            ValueError: If pattern format is invalid
        """
        # Validate pattern
        self._validate_pattern(key_pattern)
        
        collection = await self._get_collection()
        
        try:
            # Build pattern query
            pattern_query = self._build_segment_query(key_pattern)
            
            # Build text search query if provided
            text_query = {}
            if text_search_query:
                if not self.text_search_fields:
                    logger.warning("Text search query provided, but no text search fields configured.")
                else:
                    text_query = {"$text": {"$search": text_search_query}}
            
            # Build value filter query if provided
            filter_query = {}
            if value_filter:
                filter_query = {f"data.{k}": v for k, v in value_filter.items()}
            
            # Build permission query
            permission_query = self._build_permission_query(allowed_prefixes or [])
            
            # Combine all queries
            final_query = self._combine_queries(pattern_query, text_query, filter_query, permission_query)
            
            if final_query == {"_id": {"$exists": False}}:  # Deny-all case
                logger.info("Search denied due to permissions.")
                return []
            
            logger.debug(f"Searching objects with query: {final_query}")
            
            # Prepare projection if include_fields is specified
            projection = None
            if include_fields:
                projection = {field: 1 for field in include_fields}
                # Always include _id field
                if "_id" not in projection:
                    projection["_id"] = 1
            
            # Execute search
            find_kwargs = {}
            if projection:
                find_kwargs["projection"] = projection
            
            cursor = collection.find(final_query, **find_kwargs)
            
            # Add sort for text search relevance if needed
            value_sort_by = value_sort_by or []
            value_sort_by = [(f"data.{field}", _order) for field, _order in value_sort_by]
            if text_query:
                value_sort_by.append(("score", {"$meta": "textScore"}))
            
            if value_sort_by:
                cursor = cursor.sort(value_sort_by)
            
            results = []
            async for doc in cursor:
                results.append(doc)
                
            logger.info(f"Found {len(results)} objects matching search criteria with pattern '{key_pattern}'")
            return results
        except Exception as e:
            if text_search_query and "text index required" in str(e).lower():
                fields_str = ', '.join([f"data.{f}" for f in self.text_search_fields])
                logger.error(f"Text search failed: Text index missing on fields [{fields_str}]")
                raise ValueError(f"Text search requires a text index. Run setup() first.") from e
            else:
                logger.error(f"Error searching objects with pattern '{key_pattern}': {e}")
                raise
    
    async def delete_objects(
        self,
        pattern: List[str],
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> int:
        """
        Deletes objects matching a pattern, filtered by permissions.
        
        Database round trips:
        1. One round trip to delete matching documents
        
        Args:
            pattern: Path pattern with wildcards as list
            allowed_prefixes: Optional list of allowed path prefixes as lists
            
        Returns:
            Number of documents deleted
            
        Raises:
            ValueError: If pattern format is invalid
        """
        # Validate pattern
        self._validate_pattern(pattern)
        
        collection = await self._get_collection()
        
        try:
            # Build queries
            pattern_query = self._build_segment_query(pattern)
            permission_query = self._build_permission_query(allowed_prefixes or [])
            final_query = self._combine_queries(pattern_query, permission_query)
            
            if final_query == {"_id": {"$exists": False}}:  # Deny-all case
                logger.info("Deletion denied due to permissions.")
                return 0
            
            # Safety check for empty query
            if not final_query:
                if pattern.count('*') != len(pattern):
                    # This isn't a "match all" pattern (e.g., ["*", "*"] for 2 segments)
                    logger.warning(f"Empty delete query for pattern '{pattern}'. No documents will be deleted.")
                    return 0
                elif allowed_prefixes:
                    # Permissions were provided but resulted in an empty query
                    logger.warning(f"Empty delete query for pattern '{pattern}' due to permissions.")
                    return 0
                
                logger.warning("Attempting to delete all documents! Ensure this is intended.")
            
            logger.debug(f"Deleting objects with query: {final_query}")
            
            result = await collection.delete_many(final_query)
            deleted_count = result.deleted_count
            logger.info(f"Deleted {deleted_count} documents matching pattern '{pattern}'")
            return deleted_count
        except ValueError as e:
            logger.error(f"Invalid pattern format for '{pattern}': {e}")
            raise
        except Exception as e:
            logger.error(f"Error deleting objects with pattern '{pattern}': {e}")
            raise
    
    async def count_objects(
        self,
        pattern: List[str] = ["*", "*"],
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> int:
        """
        Counts objects matching a pattern, filtered by permissions.
        
        Database round trips:
        1. One round trip to count matching documents
        
        Args:
            pattern: Path pattern with wildcards as list
            allowed_prefixes: Optional list of allowed path prefixes as lists
            
        Returns:
            Number of matching documents
        """
        # Validate pattern
        self._validate_pattern(pattern)
        
        collection = await self._get_collection()
        
        try:
            # Build queries
            pattern_query = self._build_segment_query(pattern)
            permission_query = self._build_permission_query(allowed_prefixes or [])
            final_query = self._combine_queries(pattern_query, permission_query)
            
            if final_query == {"_id": {"$exists": False}}:  # Deny-all case
                return 0
            
            count = await collection.count_documents(final_query)
            logger.info(f"Counted {count} objects matching pattern '{pattern}'")
            return count
        except ValueError as e:
            logger.error(f"Invalid pattern format for '{pattern}': {e}")
            return 0
        except Exception as e:
            logger.error(f"Error counting objects with pattern '{pattern}': {e}")
            return 0
    
    # =========================================================================
    # BATCH OPERATIONS
    # =========================================================================
    
    async def batch_fetch_objects(
        self,
        paths: List[List[str]],
        allowed_prefixes: Optional[List[List[str]]] = None,
        include_fields: Optional[List[str]] = None
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Fetches multiple documents by their paths in a batch operation.
        
        Database round trips:
        1. One round trip to fetch all documents
        
        Args:
            paths: List of paths as lists of segments
            allowed_prefixes: Optional list of allowed path prefixes as lists
            include_fields: Optional list of fields to include in the projection
        Returns:
            Dictionary mapping stringified paths to document objects (or None if not found/denied)
            
        Raises:
            ValueError: If any path format is invalid
        """
        if not paths:
            return {}
        
        # Process each path
        allowed_paths = []
        results = {}  # Initialize with empty results
        
        for path in paths:
            # Validate path
            try:
                self._validate_document_path(path)
            except ValueError as e:
                logger.error(f"Invalid path format for '{path}': {e}")
                results[str(path)] = None
                continue
                
            # Check permissions
            if allowed_prefixes and not self._validate_path_permission(path, allowed_prefixes):
                logger.info(f"Access denied for path '{path}' based on allowed prefixes.")
                results[str(path)] = None
                continue
            
            # Add to allowed paths for fetch
            allowed_paths.append(path)
            
            # Initialize result to None (will be updated if found)
            results[str(path)] = None
        
        # Build query for batch fetch
        if allowed_paths:
            collection = await self._get_collection()
            
            # Build $or query with multiple ID conditions for more efficient lookup
            ids = [self._path_to_id(path) for path in allowed_paths]
            id_query = {"_id": {"$in": ids}}
            
            try:
                # Create a mapping from document ID to path for O(1) lookups
                id_to_path_set = {self._path_to_id(path): str(path) for path in allowed_paths}
                kwargs = {}
                if include_fields:
                    kwargs["projection"] = {field: 1 for field in include_fields}
                
                # Fetch all matching documents in one query
                async for doc in collection.find(id_query, **kwargs):
                    # Get the document ID
                    doc_id = doc["_id"]
                    
                    # Use the mapping for O(1) lookup instead of iterating through paths
                    allowed_path_str = id_to_path_set.get(doc_id, None)
                    if allowed_path_str is not None:
                        results[allowed_path_str] = doc
            except Exception as e:
                logger.error(f"Error in batch fetch operation: {e}")
        
        logger.info(f"Fetched documents for {len(paths)} paths in batch operation")
        return results
    
    async def batch_delete_objects(
        self,
        paths: List[List[str]],
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> Dict[str, bool]:
        """
        Deletes multiple documents by their exact paths in a batch operation.
        
        Database round trips:
        1. One round trip to delete the documents
        
        Args:
            paths: List of paths as lists of segments
            allowed_prefixes: Optional list of allowed path prefixes as lists
            
        Returns:
            Dictionary mapping stringified paths to deletion success (True if deleted)
            
        Raises:
            ValueError: If any path format is invalid
        """
        if not paths:
            return {}
        
        # Process each path
        allowed_paths = []
        results = {}  # Initialize with all False results
        path_to_id = {}
        
        for path in paths:
            try:
                # Validate path
                self._validate_document_path(path)
                
                # Check permissions
                if allowed_prefixes and not self._validate_path_permission(path, allowed_prefixes):
                    logger.info(f"Access denied for path '{path}' based on allowed prefixes.")
                    results[str(path)] = False
                    continue
                
                # Add to allowed paths for deletion
                allowed_paths.append(path)
                
                # Map path to ID
                path_str = str(path)
                path_to_id[path_str] = self._path_to_id(path)
                
                # Initialize result to False (will be updated if delete succeeded)
                results[path_str] = False
            except ValueError as e:
                logger.error(f"Invalid path format for '{path}': {e}")
                results[str(path)] = False
        
        # Build query for batch delete
        if allowed_paths:
            collection = await self._get_collection()
            
            # Get all IDs to delete
            ids = list(path_to_id.values())
            
            try:
                # Delete all documents with matching IDs
                delete_result = await collection.delete_many({"_id": {"$in": ids}})
                # if any('nonexistent' in path for path in paths):
                #     import ipdb; ipdb.set_trace()
                
                # TODO: return results count too!
                # Mark all paths as deleted (we assume all allowed paths were deleted)
                for path_str in path_to_id:
                    results[path_str] = True
                
                logger.info(f"Deleted {delete_result.deleted_count} documents in batch operation")
            except Exception as e:
                logger.error(f"Error in batch delete operation: {e}")
        
        return results
    
    async def batch_create_objects(
        self, 
        path_data_pairs: List[Tuple[List[str], Dict[str, Any]]],
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> List[str]:
        """
        Creates multiple documents in a single batch operation.
        
        Database round trips:
        1. One round trip to insert all documents
        
        Args:
            path_data_pairs: List of (path, data) tuples where path is a list of segments
            allowed_prefixes: Optional list of allowed path prefixes as lists
            
        Returns:
            List of IDs for created documents
            
        Raises:
            ValueError: If any path format is invalid or access is denied
        """
        if not path_data_pairs:
            return []
        
        # Validate paths and check permissions
        documents = []
        doc_ids = []
        
        for path, data in path_data_pairs:
            # Validate document path
            self._validate_document_path(path)
            
            # Check permissions
            if allowed_prefixes and not self._validate_path_permission(path, allowed_prefixes):
                error_msg = f"Access denied for path '{path}' based on allowed prefixes"
                logger.warning(error_msg)
                raise ValueError(error_msg)
            
            # Prepare document
            document = self._prepare_document(path, data)
            documents.append(document)
            doc_ids.append(document["_id"])
        
        # Insert documents
        collection = await self._get_collection()
        try:
            # Use bulk write for better performance
            from pymongo import InsertOne, ReplaceOne
            
            # Prepare bulk operations (using replace to handle existing documents)
            bulk_ops = [
                ReplaceOne({"_id": doc["_id"]}, doc, upsert=True) 
                for doc in documents
            ]
            
            await collection.bulk_write(bulk_ops)
            logger.info(f"Created {len(documents)} documents in batch operation")
            return doc_ids
        except Exception as e:
            logger.error(f"Error in batch create operation: {e}")
            raise
    
    async def batch_update_objects(
        self,
        path_data_pairs: List[Tuple[List[str], Dict[str, Any]]],
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> List[Optional[str]]:
        """
        Updates multiple documents in a batch operation.
        
        Database round trips:
        1. One round trip to update all documents
        
        Args:
            path_data_pairs: List of (path, data) tuples where path is a list of segments
            allowed_prefixes: Optional list of allowed path prefixes as lists
            
        Returns:
            List of IDs of updated documents (None for any not found or denied)
            
        Raises:
            ValueError: If any path format is invalid
        """
        if not path_data_pairs:
            return []
        
        # Process paths, check permissions, and prepare update operations
        from pymongo import UpdateOne
        bulk_operations = []
        doc_ids = []
        
        for path, data in path_data_pairs:
            try:
                # Validate document path
                self._validate_document_path(path)
                
                # Skip if permission denied
                if allowed_prefixes and not self._validate_path_permission(path, allowed_prefixes):
                    logger.info(f"Access denied for path '{path}' in batch update")
                    doc_ids.append(None)
                    continue
                
                # Get ID for query
                doc_id = self._path_to_id(path)
                
                # Add update operation
                bulk_operations.append(
                    UpdateOne(
                        {"_id": doc_id},
                        {"$set": {"data": data}}
                    )
                )
                
                # Add ID to results
                doc_ids.append(doc_id)
            except ValueError as e:
                logger.error(f"Invalid path format for '{path}': {e}")
                doc_ids.append(None)
        
        # Execute updates if any
        if bulk_operations:
            collection = await self._get_collection()
            try:
                result = await collection.bulk_write(bulk_operations)
                # if any({"name": "Nonexistent"} == data for path, data in path_data_pairs):
                #     import ipdb; ipdb.set_trace()

                # TODO: return results count too!
                # Update results for documents that weren't found
                if result.matched_count < len(bulk_operations):
                    # We don't know which specific operations failed
                    # In a real implementation, we could query to verify each update
                    logger.warning(f"Only {result.matched_count} of {len(bulk_operations)} updates matched documents")
            except Exception as e:
                logger.error(f"Error in batch update operation: {e}")
                # Don't raise, continue with partial results
        
        logger.info(f"Processed {len(path_data_pairs)} updates in batch operation")
        return doc_ids
    
    async def batch_create_or_update_objects(
        self,
        path_data_pairs: List[Tuple[List[str], Dict[str, Any]]],
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> List[Tuple[str, bool]]:
        """
        Creates or updates multiple documents in a batch operation.
        
        Database round trips:
        1. One round trip to check which documents exist
        2. One round trip to perform all upserts
        
        Args:
            path_data_pairs: List of (path, data) tuples where path is a list of segments
            allowed_prefixes: Optional list of allowed path prefixes as lists
            
        Returns:
            List of (document ID, was_created) tuples
            
        Raises:
            ValueError: If any path format is invalid or access is denied
        """
        if not path_data_pairs:
            return []
        
        # Validate paths and check permissions
        from pymongo import ReplaceOne
        
        documents = []
        doc_ids = []
        path_to_index = {}
        
        for i, (path, data) in enumerate(path_data_pairs):
            # Validate document path
            self._validate_document_path(path)
            
            # Check permissions
            if allowed_prefixes and not self._validate_path_permission(path, allowed_prefixes):
                error_msg = f"Access denied for path '{path}' based on allowed prefixes"
                logger.warning(error_msg)
                raise ValueError(error_msg)
            
            # Prepare document
            document = self._prepare_document(path, data)
            documents.append(document)
            doc_id = document["_id"]
            doc_ids.append(doc_id)
            
            # Map ID to index for tracking
            path_to_index[doc_id] = i
        
        # First, check which documents already exist
        collection = await self._get_collection()
        existing_docs = await collection.find(
            {"_id": {"$in": doc_ids}},
            {"_id": 1}
        ).to_list(length=None)
        
        existing_ids = {doc["_id"] for doc in existing_docs}
        
        # Prepare bulk operations
        bulk_ops = [
            ReplaceOne(
                {"_id": doc["_id"]},
                doc,
                upsert=True
            )
            for doc in documents
        ]
        
        # Execute bulk operations
        try:
            await collection.bulk_write(bulk_ops)
            
            # Prepare results
            results = []
            for doc_id in doc_ids:
                was_created = doc_id not in existing_ids
                results.append((doc_id, was_created))
            
            logger.info(f"Processed {len(path_data_pairs)} upserts in batch operation")
            return results
        except Exception as e:
            logger.error(f"Error during batch upsert: {e}")
            raise
