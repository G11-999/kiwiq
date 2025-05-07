import asyncio
import copy
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union, TypeVar, Generic, cast

import jsonpatch
import jsonschema
from jsonschema import Draft7Validator, validators, Draft202012Validator
from jsonschema.exceptions import ValidationError

# Import the AsyncMongoDBClient
from mongo_client.mongo_client_v2_secure import AsyncMongoDBClient

from global_config.logger import get_logger
from global_utils.utils import datetime_now_utc

# Configure logging
logger = get_logger(__name__)

T = TypeVar('T')

def extend_with_default(validator_class):
    """
    Extends a validator class to fill in default values from the schema.
    This is used for validation during partial updates.
    
    Args:
        validator_class: The validator class to extend (Draft202012Validator)
        
    Returns:
        An extended validator class with default value handling
    """
    validate_properties = validator_class.VALIDATORS["properties"]

    def set_defaults(validator, properties, instance, schema):
        for property, subschema in properties.items():
            if "default" in subschema and property not in instance:
                instance[property] = subschema["default"]

        for error in validate_properties(validator, properties, instance, schema):
            yield error

    return validators.extend(validator_class, {"properties": set_defaults})


# Use Draft202012Validator as the base validator class with format checking support
DefaultValidatingDraft202012Validator = extend_with_default(Draft202012Validator)
# Access format_checker via Draft202012Validator.FORMAT_CHECKER when needed for validation
# validate(instance=run_submit.inputs, schema=hitl_job.response_schema, format_checker=Draft202012Validator.FORMAT_CHECKER)

# TODO: FIXME: store the relaxed schema somewhere for caching!
def create_relaxed_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Creates a relaxed version of the JSON schema by removing required fields.
    This allows validation of partial objects.
    
    Args:
        schema: The original JSON schema
        
    Returns:
        A modified schema with no required fields
    """
    relaxed_schema = copy.deepcopy(schema)
    
    # Remove required fields at the top level
    if "required" in relaxed_schema:
        del relaxed_schema["required"]
    
    # Remove required fields in nested properties
    def remove_required(obj):
        if isinstance(obj, dict):
            if "required" in obj:
                del obj["required"]
            for key, value in obj.items():
                if key == "properties" and isinstance(value, dict):
                    for prop in value.values():
                        remove_required(prop)
                elif isinstance(value, (dict, list)):
                    remove_required(value)
        elif isinstance(obj, list):
            for item in obj:
                remove_required(item)
    
    remove_required(relaxed_schema)
    return relaxed_schema


class AsyncMongoVersionedClient:
    """
    A versioned MongoDB client that wraps the AsyncMongoDBClient.
    
    This client maintains different versions of documents and their edit history.
    It supports both primitive types and JSON objects, storing JSON updates as patches
    for the edit history and storing primitive types as whole values.
    
    Features:
    - Multiple document versions with separate edit histories
    - Branching from any version to create new versions
    - Preview and restore to previous versions
    - JSON schema validation for documents
    - Fixed-length revision history
    
    The document path structure is:
    - base_path: Original path segments (e.g., [org, shared, namespace, docname])
    - metadata_path: base_path (stores metadata such as active version, JSON schema)
    - version_path: base_path + [version] (stores current version data)
    - history_path: base_path + [version, sequence_no] (stores edit history)
    """

    # Maximum number of versions allowed per document
    MAX_VERSIONS = 20
    
    # Maximum number of edits to keep in history
    MAX_HISTORY_LENGTH = 100

    VERSION_SEGMENT_NAME = "version"
    SEQUENCE_SEGMENT_NAME = "sequence_no"

    VERSION_SEGMENT_NAMES = [VERSION_SEGMENT_NAME, SEQUENCE_SEGMENT_NAME]

    CREATED_AT_KEY = "created_at"  # created_at
    UPDATED_AT_KEY = "updated_at"  # updated_at
    MIN_SEQUENCE_KEY = "_min_sequence"  # min_sequence
    MAX_SEQUENCE_KEY = "_max_sequence"  # max_sequence
    IS_COMPLETE_KEY = "_is_complete"  # is_complete
    
    # NOTE: this is only used as key in saved document when object is not a dict!
    DOCUMENT_KEY = "_document"  # document
    INTERNAL_KEYS = [MIN_SEQUENCE_KEY, MAX_SEQUENCE_KEY, IS_COMPLETE_KEY]
    RESERVED_KEYS = [DOCUMENT_KEY] + INTERNAL_KEYS
    ALL_KEYS = [CREATED_AT_KEY, UPDATED_AT_KEY] + INTERNAL_KEYS

    def __init__(
        self,
        client: AsyncMongoDBClient,
        segment_names: List[str],
        return_timestamp_metadata: bool = True,
        # metadata_segment_name: str = "metadata",
        # version_segment_name: str = "version",
        # sequence_segment_name: str = "sequence"
    ):
        """
        Initialize the versioned MongoDB client.
        
        Args:
            client: The underlying AsyncMongoDBClient instance
            segment_names: List of segment names for the base path
            metadata_segment_name: Segment name for the metadata path
            version_segment_name: Segment name for the version path
            sequence_segment_name: Segment name for the sequence number
        """
        assert client.version_mode == AsyncMongoDBClient.DOC_TYPE_VERSIONED, "Client must be versioned"
        self.client = client
        self.segment_names = segment_names
        self.return_timestamp_metadata = return_timestamp_metadata
        # self.metadata_segment_name = metadata_segment_name
        # self.version_segment_name = version_segment_name
        # self.sequence_segment_name = sequence_segment_name
        
        # IMPORTANT ASSUMPTION:
        # The underlying self.client (AsyncMongoDBClient) must be initialized
        # with segment_names that accommodate the version and sequence segments.
        # For example, if self.segment_names (base) is ["org", "user", "doc"],
        # the underlying client might need segment_names like 
        # ["org", "user", "doc", "version", "sequence"]
        # where "version" and "sequence" are the names the underlying client 
        # uses for those segments.
        logger.info(f"AsyncMongoVersionedClient initialized with segment names: {segment_names}")
    
    # =========================================================================
    # Path Construction Helpers
    # =========================================================================

    def _build_metadata_path(self, base_path: List[str]) -> List[str]:
        """
        Build the path for the document metadata.
        Path: base_path
        """
        # Metadata is stored at the base path itself
        return base_path

    def _build_version_path(self, base_path: List[str], version: str) -> List[str]:
        """
        Build the path for a specific document version's data.
        Path: base_path + [version]
        """
        return base_path + [version]

    def _build_history_path(self, base_path: List[str], version: str, sequence: int) -> List[str]:
        """
        Build the path for a specific history item.
        Path: base_path + [version, str(sequence)]
        """
        return base_path + [version, str(sequence)]

    def _build_history_pattern(self, base_path: List[str], version: str) -> List[str]:
        """
        Build the path pattern to match all history items for a version.
        Pattern: base_path + [version, "*"]
        """
        return base_path + [version, "*"]

    # =========================================================================
    # Internal Data Access Helpers (using new path builders)
    # =========================================================================

    async def _get_document_metadata(self, base_path: List[str], allowed_prefixes: Optional[List[List[str]]] = None) -> Optional[Dict[str, Any]]:
        """
        Get the metadata for a document.
        
        Args:
            base_path: The base path for the document
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            The document metadata or None if it doesn't exist
        """
        metadata_path = self._build_metadata_path(base_path)
        metadata = await self.client.fetch_object(metadata_path, allowed_prefixes)
        if metadata:
            return metadata["data"]
        return None
    
    async def _create_or_update_metadata(
        self, 
        base_path: List[str], 
        metadata: Dict[str, Any],
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> str:
        """
        Create or update the metadata for a document.
        
        Args:
            base_path: The base path for the document
            metadata: The metadata to store
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            The document ID
        """
        metadata_path = self._build_metadata_path(base_path)
        doc_id, _ = await self.client.create_or_update_object(metadata_path, metadata, allowed_prefixes)
        return doc_id
    
    async def _get_version_data(
        self, 
        base_path: List[str], 
        version: str,
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get the data for a specific document version.
        
        Args:
            base_path: The base path for the document
            version: The version identifier
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            The version data or None if it doesn't exist
        """
        version_path = self._build_version_path(base_path, version)
        version_obj = await self.client.fetch_object(version_path, allowed_prefixes)
        if version_obj:
            return version_obj["data"]
        return None
    
    async def _create_or_update_version_data(
        self, 
        base_path: List[str], 
        version: str, 
        data: Dict[str, Any],
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> str:
        """
        Create or update the data for a specific document version.
        
        Args:
            base_path: The base path for the document
            version: The version identifier
            data: The version data to store
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            The document ID
        """
        version_path = self._build_version_path(base_path, version)
        doc_id, _ = await self.client.create_or_update_object(version_path, data, allowed_prefixes)
        return doc_id
    
    async def _get_history_item(
        self, 
        base_path: List[str], 
        version: str, 
        sequence: int,
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific history item.
        
        Args:
            base_path: The base path for the document
            version: The version identifier
            sequence: The sequence number
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            The history item or None if it doesn't exist
        """
        history_path = self._build_history_path(base_path, version, sequence)
        history_obj = await self.client.fetch_object(history_path, allowed_prefixes)
        if history_obj:
            return history_obj["data"]
        return None
    
    async def _create_history_item(
        self, 
        base_path: List[str], 
        version: str, 
        sequence: int, 
        data: Dict[str, Any],
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> str:
        """
        Create a history item.
        
        Args:
            base_path: The base path for the document
            version: The version identifier
            sequence: The sequence number
            data: The history item data to store
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            The document ID
        """
        history_path = self._build_history_path(base_path, version, sequence)
        doc_id = await self.client.create_object(history_path, data, allowed_prefixes)
        return doc_id
    
    async def _prune_history(
        self, 
        base_path: List[str], 
        version: str, 
        max_items: int,
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> None:
        """
        Prune the history for a specific version to keep only a maximum number of items.
        This method directly updates the min_sequence in the version data document.
        
        Args:
            base_path: The base path for the document
            version: The version identifier
            max_items: The maximum number of history items to keep
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
        """
        # Get current version data to check sequence numbers
        version_data = await self._get_version_data(base_path, version, allowed_prefixes)
        if not version_data or AsyncMongoVersionedClient.MIN_SEQUENCE_KEY not in version_data or AsyncMongoVersionedClient.MAX_SEQUENCE_KEY not in version_data:
            logger.warning(f"Cannot prune history for version {version}: version data missing or incomplete.")
            return
        
        min_sequence = version_data[AsyncMongoVersionedClient.MIN_SEQUENCE_KEY]
        max_sequence = version_data[AsyncMongoVersionedClient.MAX_SEQUENCE_KEY]
        
        # Calculate how many items to prune
        items_count = max_sequence - min_sequence + 1
        items_to_prune = items_count - max_items
        
        if items_to_prune <= 0:
            return
        
        # Prune oldest items
        new_min_sequence = min_sequence + items_to_prune
        
        delete_paths = []
        for sequence in range(min_sequence, new_min_sequence):
            history_path = self._build_history_path(base_path, version, sequence)
            delete_paths.append(history_path)
        # Use batch delete for efficiency
        await self.client.batch_delete_objects(delete_paths, allowed_prefixes)

        # Update the min_sequence field directly in the version data document
        version_path = self._build_version_path(base_path, version)
        await self.client.update_object(
            path=version_path,
            data={AsyncMongoVersionedClient.MIN_SEQUENCE_KEY: new_min_sequence},
            update_subfields=True, # Ensure only min_sequence is updated
            allowed_prefixes=allowed_prefixes
        )
        logger.info(f"Pruned history for version {version}. New min_sequence: {new_min_sequence}")

        # Prune history if necessary and get updated version_data
        # updated_version_data = await self._prune_history(base_path, version, version_data, self.MAX_HISTORY_LENGTH, allowed_prefixes)
        
        # Save the final version data (including pruned min_sequence)
        # await self._create_or_update_version_data(base_path, version, updated_version_data, allowed_prefixes)

    async def _validate_object(
        self, 
        obj: Dict[str, Any], 
        schema: Dict[str, Any], 
        is_partial: bool = False
    ) -> bool:
        """
        Validate an object against a JSON schema.
        
        Args:
            obj: The object to validate
            schema: The JSON schema
            is_partial: Whether to use relaxed validation for partial objects
            
        Returns:
            True if the object is valid, raises an exception otherwise
        """
        if not schema:
            # No schema to validate against
            return True
        
        try:
            if is_partial:
                # Use relaxed schema for partial validation
                validation_schema = create_relaxed_schema(schema)
                DefaultValidatingDraft202012Validator(validation_schema).validate(obj)
            else:
                # Use strict schema for complete validation first
                jsonschema.validate(obj, schema)
                # Then, apply defaults using the extending validator
                # This modifies the obj in place IF defaults are missing
                DefaultValidatingDraft202012Validator(schema).validate(obj)
        except ValidationError as e:
            # Construct a clear error message with the path
            error_path = "/".join(str(part) for part in e.path)
            error_msg = f"{error_path}: {e.message}" if error_path else e.message
            validation_type = "partial " if is_partial else ""
            raise ValidationError(f"{validation_type}Object validation failed: {error_msg}")
        
        return True
    
    async def _compute_diff(self, old_value: Any, new_value: Any) -> Union[jsonpatch.JsonPatch, None]:
        """
        Compute the difference between two JSON objects.
        
        Args:
            old_value: The old value
            new_value: The new value
            
        Returns:
            A JsonPatch object representing the diff, or None if the values are identical
        """
        if old_value == new_value:
            return None
        
        if isinstance(old_value, dict) and isinstance(new_value, dict):
            # For JSON objects, compute a JSON patch
            patch = jsonpatch.make_patch(old_value, new_value)
            if not patch:
                return None
            return patch
        else:
            # For primitive types, just return a flag indicating there's a diff
            return jsonpatch.JsonPatch([{"op": "replace", "path": "", "value": new_value}])
    
    async def _apply_patches(
        self, 
        base_value: Dict[str, Any], 
        patches: List[jsonpatch.JsonPatch]
    ) -> Dict[str, Any]:
        """
        Apply a series of JSON patches to a base value.
        
        Args:
            base_value: The base value
            patches: List of JSON patches to apply
            
        Returns:
            The result of applying all patches
        """
        result = copy.deepcopy(base_value)
        for patch in patches:
            result = patch.apply(result)
        return result
    
    async def initialize_document(
        self, 
        base_path: List[str], 
        initial_version: str = "v1",
        schema: Optional[Dict[str, Any]] = None,
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> bool:
        """
        Initialize a new versioned document.
        
        Args:
            base_path: The base path for the document
            initial_version: The initial version identifier
            schema: Optional JSON schema for document validation
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            True if the document was initialized successfully
        """
        # Check if document already exists
        existing_metadata = await self._get_document_metadata(base_path, allowed_prefixes)
        if existing_metadata:
            logger.info(f"Document at path {base_path} already exists, initialization skipped")
            return False
        
        # Create initial metadata
        timestamp = datetime_now_utc()
        metadata = {
            # AsyncMongoDBClient.DOC_TYPE_KEY: AsyncMongoDBClient.DOC_TYPE_VERSIONED,
            AsyncMongoVersionedClient.CREATED_AT_KEY: timestamp,
            AsyncMongoVersionedClient.UPDATED_AT_KEY: timestamp,
            "active_version": initial_version,
            "versions": [initial_version],
            "schema": schema
        }
        
        await self._create_or_update_metadata(base_path, metadata, allowed_prefixes)
        
        # Create initial version data
        version_data = {
            AsyncMongoVersionedClient.CREATED_AT_KEY: timestamp,
            AsyncMongoVersionedClient.UPDATED_AT_KEY: timestamp,
            AsyncMongoVersionedClient.MIN_SEQUENCE_KEY: 0,
            AsyncMongoVersionedClient.MAX_SEQUENCE_KEY: -1,
            AsyncMongoVersionedClient.IS_COMPLETE_KEY: False,
            # AsyncMongoVersionedClient.DOCUMENT_KEY: {}
        }
        
        await self._create_or_update_version_data(base_path, initial_version, version_data, allowed_prefixes)
        logger.info(f"Initialized new document at path {base_path} with version {initial_version}")
        
        return True
    
    async def create_version(
        self, 
        base_path: List[str], 
        new_version: str,
        from_version: Optional[str] = None,
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> bool:
        """
        Create a new version of a document, optionally branching from an existing version.
        
        Args:
            base_path: The base path for the document
            new_version: The new version identifier
            from_version: The version to branch from, or None to use the active version
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            True if the version was created successfully
        """
        # Get document metadata
        metadata = await self._get_document_metadata(base_path, allowed_prefixes)
        if not metadata:
            logger.error(f"Cannot create version {new_version}: document at path {base_path} does not exist")
            return False
        
        # Check if we've reached the maximum number of versions
        if len(metadata.get("versions", [])) >= self.MAX_VERSIONS:
            error_msg = f"Maximum number of versions reached ({self.MAX_VERSIONS})"
            logger.error(f"Cannot create version {new_version}: {error_msg}")
            raise ValueError(error_msg)
        
        # Check if version already exists
        if new_version in metadata.get("versions", []):
            error_msg = f"Version '{new_version}' already exists"
            logger.error(f"Cannot create version {new_version}: {error_msg}")
            raise ValueError(error_msg)
        
        # Determine source version
        source_version = from_version or metadata.get("active_version")
        if not source_version or source_version not in metadata.get("versions", []):
            error_msg = f"Source version '{source_version}' does not exist"
            logger.error(f"Cannot create version {new_version}: {error_msg}")
            raise ValueError(error_msg)
        
        # Get source version data
        source_data = await self._get_version_data(base_path, source_version, allowed_prefixes)
        if not source_data:
            logger.error(f"Cannot create version {new_version}: source version {source_version} data not found")
            return False
        
        # Create new version data (copy from source)
        timestamp = datetime_now_utc()
        new_version_data = {
            AsyncMongoVersionedClient.CREATED_AT_KEY: timestamp,
            AsyncMongoVersionedClient.UPDATED_AT_KEY: timestamp,
            AsyncMongoVersionedClient.MIN_SEQUENCE_KEY: 0,
            AsyncMongoVersionedClient.MAX_SEQUENCE_KEY: -1,
            AsyncMongoVersionedClient.IS_COMPLETE_KEY: source_data.get(AsyncMongoVersionedClient.IS_COMPLETE_KEY, False),
            # AsyncMongoVersionedClient.DOCUMENT_KEY: copy.deepcopy(source_data.get(AsyncMongoVersionedClient.DOCUMENT_KEY, {}))
            **copy.deepcopy({k:v for k,v in source_data.items() if k not in AsyncMongoVersionedClient.ALL_KEYS})
        }
        
        await self._create_or_update_version_data(base_path, new_version, new_version_data, allowed_prefixes)
        
        # Update metadata
        metadata["versions"].append(new_version)
        metadata[AsyncMongoVersionedClient.UPDATED_AT_KEY] = timestamp
        await self._create_or_update_metadata(base_path, metadata, allowed_prefixes)
        
        logger.info(f"Created new version {new_version} from {source_version} for document at path {base_path}")
        return True
    
    async def set_active_version(
        self, 
        base_path: List[str], 
        version: str,
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> bool:
        """
        Set the active version of a document.
        
        Args:
            base_path: The base path for the document
            version: The version identifier to set as active
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            True if the active version was set successfully
        """
        # Get document metadata
        metadata = await self._get_document_metadata(base_path, allowed_prefixes)
        if not metadata:
            logger.error(f"Cannot set active version: document at path {base_path} does not exist")
            return False
        
        # Check if version exists
        if version not in metadata.get("versions", []):
            error_msg = f"Version '{version}' does not exist"
            logger.error(f"Cannot set active version: {error_msg}")
            raise ValueError(error_msg)
        
        # Update metadata
        metadata["active_version"] = version
        metadata[AsyncMongoVersionedClient.UPDATED_AT_KEY] = datetime_now_utc()
        await self._create_or_update_metadata(base_path, metadata, allowed_prefixes)
        
        logger.info(f"Set active version to {version} for document at path {base_path}")
        return True
    
    async def get_document(
        self, 
        base_path: List[str], 
        version: Optional[str] = None,
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get a document at a specific version.
        
        Args:
            base_path: The base path for the document
            version: The version identifier, or None to use the active version
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            The document data, or None if it doesn't exist
        """
        # Get document metadata
        metadata = await self._get_document_metadata(base_path, allowed_prefixes)
        if not metadata:
            logger.debug(f"Document at path {base_path} does not exist")
            return None
        
        # Determine which version to use
        target_version = version or metadata.get("active_version")
        if not target_version or target_version not in metadata.get("versions", []):
            error_msg = f"Version '{target_version}' does not exist"
            logger.error(f"Cannot get document: {error_msg}")
            raise ValueError(error_msg)
        
        # Get version data
        version_data = await self._get_version_data(base_path, target_version, allowed_prefixes)
        if not version_data:
            logger.error(f"Version data for {target_version} not found at path {base_path}")
            return None
        
        # logger.warning(f"Retrieved document at path {base_path}, version {target_version}")
        # logger.warning(f"-------Retrieved document at path {base_path}, version {target_version}\n\n\n\n{json.dumps(version_data, indent=4)}\n\n\n\n")

        keys_to_exclude = (AsyncMongoVersionedClient.INTERNAL_KEYS if self.return_timestamp_metadata else AsyncMongoVersionedClient.ALL_KEYS)
        return_obj = {k:v for k,v in version_data.items() if k not in keys_to_exclude}

        # NOTE: DOCUMENT_KEY is used when object is a non-dict type!
        return return_obj.get(AsyncMongoVersionedClient.DOCUMENT_KEY, return_obj)
    
    async def update_document(
        self, 
        base_path: List[str], 
        data: Any,
        version: Optional[str] = None,
        is_complete: Optional[bool] = None,
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> bool:
        """
        Update a document at a specific version.
        
        Args:
            base_path: The base path for the document
            data: The new document data (can be a complete document or a partial update)
            version: The version identifier, or None to use the active version
            is_complete: Whether the document is now complete (for validation purposes)
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            True if the document was updated successfully
        """
        # Get document metadata
        metadata = await self._get_document_metadata(base_path, allowed_prefixes)
        if not metadata:
            logger.error(f"Cannot update document: document at path {base_path} does not exist")
            return False
        
        # Determine which version to use
        target_version = version or metadata.get("active_version")
        if not target_version or target_version not in metadata.get("versions", []):
            error_msg = f"Version '{target_version}' does not exist"
            logger.error(f"Cannot update document: {error_msg}")
            raise ValueError(error_msg)

        if isinstance(data, dict) and any(k in data for k in AsyncMongoVersionedClient.RESERVED_KEYS):
            raise ValueError("Cannot update document: data contains reserved keys")

        # Get version data
        version_data = await self._get_version_data(base_path, target_version, allowed_prefixes)
        if not version_data:
            logger.error(f"Version data for {target_version} not found at path {base_path}")
            return False
        
        current_document = {k:v for k,v in version_data.items() if k not in AsyncMongoVersionedClient.ALL_KEYS}

        # NOTE: DOCUMENT_KEY is used when object is a non-dict type!
        current_document = current_document.get(AsyncMongoVersionedClient.DOCUMENT_KEY, current_document)
        current_is_complete = version_data.get(AsyncMongoVersionedClient.IS_COMPLETE_KEY, False)
        
        # Handle different data types
        if isinstance(data, dict) and isinstance(current_document, dict):
            # For dictionaries, merge the update with the current document
            new_document = copy.deepcopy(current_document)
            new_document.update(data)
        else:
            # For other types, replace the entire document
            new_document = data
        
        # Validate against schema if provided
        schema = metadata.get("schema")
        if schema:
            is_partial = not (is_complete or False)
            try:
                await self._validate_object(new_document, schema, is_partial)
                logger.debug(f"Document validation successful for path {base_path}, version {target_version}")
            except ValidationError as e:
                logger.error(f"Document validation failed: {str(e)}")
                raise
        
        # Compute diff
        diff = await self._compute_diff(current_document, new_document)
        if not diff:
            # No changes
            logger.debug(f"No changes detected for document at path {base_path}, version {target_version}")
            return True
            
        # Determine if the update represents a primitive type replacement
        # This occurs when the diff is a single 'replace' operation at the root path ('')
        is_primitive_update = False
        if isinstance(diff.patch, list) and len(diff.patch) == 1:
            op = diff.patch[0]
            if op.get('op') == 'replace' and op.get('path') == '':
                is_primitive_update = True
        
        # Update is_complete flag if provided
        new_is_complete = is_complete if is_complete is not None else current_is_complete
        
        # Save the update
        timestamp = datetime_now_utc()
        new_sequence = version_data.get(AsyncMongoVersionedClient.MAX_SEQUENCE_KEY, -1) + 1
        
        # Create history item
        history_data = {
            "timestamp": timestamp,
            "sequence": new_sequence,
            # Store the full patch regardless, the flag indicates how it was applied
            "patch": diff.to_string(), 
            "is_primitive": is_primitive_update # Use the calculated flag based on the diff
        }
        
        await self._create_history_item(base_path, target_version, new_sequence, history_data, allowed_prefixes)
        
        # Update version data object in DB first
        version_data = {k:v for k,v in version_data.items() if k in AsyncMongoVersionedClient.ALL_KEYS}
        version_data[AsyncMongoVersionedClient.UPDATED_AT_KEY] = timestamp
        if not isinstance(new_document, dict):
            version_data[AsyncMongoVersionedClient.DOCUMENT_KEY] = new_document
        else:
            if any(k in new_document for k in AsyncMongoVersionedClient.ALL_KEYS):
                logger.warning(f"Skipping reserved / shadowing keys in document update: {', '.join(k for k in new_document if k in AsyncMongoVersionedClient.ALL_KEYS)}")
            version_data.update({k:v for k,v in new_document.items() if k not in AsyncMongoVersionedClient.ALL_KEYS})

        version_data[AsyncMongoVersionedClient.MAX_SEQUENCE_KEY] = new_sequence
        
        if version_data.get(AsyncMongoVersionedClient.MIN_SEQUENCE_KEY) is None:
            version_data[AsyncMongoVersionedClient.MIN_SEQUENCE_KEY] = 0
            
        # if new_is_complete != current_is_complete:
        version_data[AsyncMongoVersionedClient.IS_COMPLETE_KEY] = new_is_complete

        updated_version_store = version_data

        # Save the updated version data *before* pruning
        await self._create_or_update_version_data(base_path, target_version, updated_version_store, allowed_prefixes)

        # Update metadata timestamp
        metadata[AsyncMongoVersionedClient.UPDATED_AT_KEY] = timestamp
        await self._create_or_update_metadata(base_path, metadata, allowed_prefixes)

        logger.info(f"Updated document at path {base_path}, version {target_version}, sequence {new_sequence}")

        # Prune history if necessary
        # Pass only necessary info, _prune_history fetches fresh version data if needed
        await self._prune_history(base_path, target_version, self.MAX_HISTORY_LENGTH, allowed_prefixes)

        return True
    
    async def get_version_history(
        self, 
        base_path: List[str], 
        version: Optional[str] = None,
        limit: Optional[int] = None,
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get the edit history for a specific version of a document.
        
        Args:
            base_path: The base path for the document
            version: The version identifier, or None to use the active version
            limit: Maximum number of history items to return, or None for all
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            List of history items, from newest to oldest
        """
        # Get document metadata
        metadata = await self._get_document_metadata(base_path, allowed_prefixes)
        if not metadata:
            logger.info(f"No metadata found for document at path {base_path}")
            return []
        
        # Determine which version to use
        target_version = version or metadata.get("active_version")
        if not target_version or target_version not in metadata.get("versions", []):
            logger.error(f"Version '{target_version}' does not exist for document at path {base_path}")
            raise ValueError(f"Version '{target_version}' does not exist")
        
        # Get version data
        version_data = await self._get_version_data(base_path, target_version, allowed_prefixes)
        if not version_data:
            logger.info(f"No version data found for document at path {base_path}, version {target_version}")
            return []
        
        min_sequence = version_data.get(AsyncMongoVersionedClient.MIN_SEQUENCE_KEY, 0)
        max_sequence = version_data.get(AsyncMongoVersionedClient.MAX_SEQUENCE_KEY, -1)
        
        if max_sequence < min_sequence:
            logger.info(f"No history items found for document at path {base_path}, version {target_version}")
            return []

        # Determine sequence range to fetch
        start_sequence = min_sequence
        if limit is not None and limit < (max_sequence - min_sequence + 1):
            start_sequence = max_sequence - limit + 1
        
        # Generate paths for batch fetch
        paths_to_fetch = [
            self._build_history_path(base_path, target_version, seq)
            for seq in range(start_sequence, max_sequence + 1)
        ]
        
        logger.info(f"Fetching {len(paths_to_fetch)} history items for document at path {base_path}, version {target_version}")
        
        # Fetch history items in batch
        batch_results = await self.client.batch_fetch_objects(paths_to_fetch, allowed_prefixes)
        
        # Process results and sort by sequence descending
        history_items = []
        for path_str, doc in batch_results.items():
            if doc:
                history_items.append(doc['data'])
                
        # Sort by sequence number descending
        history_items.sort(key=lambda x: x.get('sequence', -1), reverse=True)

        logger.info(f"Retrieved {len(history_items)} history items for document at path {base_path}, version {target_version}")
        return history_items
    
    async def preview_restore(
        self, 
        base_path: List[str], 
        sequence: int,
        version: Optional[str] = None,
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> Optional[Any]:
        """
        Preview document state at a specific point in history.
        
        Args:
            base_path: The base path for the document
            sequence: The sequence number to restore to
            version: The version identifier, or None to use the active version
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            The document state at the specified point in history, or None if it cannot be restored
        """
        # Get document metadata
        metadata = await self._get_document_metadata(base_path, allowed_prefixes)
        if not metadata:
            logger.info(f"No metadata found for document at path {base_path}")
            return None
        
        # Determine which version to use
        target_version = version or metadata.get("active_version")
        if not target_version or target_version not in metadata.get("versions", []):
            logger.error(f"Version '{target_version}' does not exist for document at path {base_path}")
            raise ValueError(f"Version '{target_version}' does not exist")
        
        # Get version data
        version_data = await self._get_version_data(base_path, target_version, allowed_prefixes)
        if not version_data:
            logger.info(f"No version data found for document at path {base_path}, version {target_version}")
            return None
        
        min_sequence = version_data.get(AsyncMongoVersionedClient.MIN_SEQUENCE_KEY, 0)
        max_sequence = version_data.get(AsyncMongoVersionedClient.MAX_SEQUENCE_KEY, -1)
        
        if sequence < min_sequence or sequence > max_sequence:
            logger.error(f"Sequence number {sequence} is out of range ({min_sequence}-{max_sequence}) for document at path {base_path}, version {target_version}")
            raise ValueError(f"Sequence number {sequence} is out of range ({min_sequence}-{max_sequence})")

        logger.info(f"Previewing document state at path {base_path}, version {target_version}, sequence {sequence}")

        # Generate paths for batch fetch
        paths_to_fetch = [
            self._build_history_path(base_path, target_version, seq)
            for seq in range(min_sequence, sequence + 1)
        ]
        
        # Fetch history items in batch
        batch_results = await self.client.batch_fetch_objects(paths_to_fetch, allowed_prefixes)

        # Process results sequentially to reconstruct the document
        fetched_items = {}
        for path_str, doc in batch_results.items():
            if doc and 'data' in doc and 'sequence' in doc['data']:
                fetched_items[doc['data']['sequence']] = doc['data']

        # Start with an empty document or appropriate base
        # TODO: Consider fetching the *actual* base document if min_sequence > 0 and history is pruned
        document = {}

        # Apply patches up to the specified sequence
        for seq in range(min_sequence, sequence + 1):
            history_item = fetched_items.get(seq)
            if not history_item:
                # This might happen if history items are missing, log a warning
                logger.warning(f"Missing history item for sequence {seq} in version {target_version} at path {base_path}")
                continue

            patch_str = history_item.get("patch", "")
            if not patch_str:
                continue
                
            try:
                patch = jsonpatch.JsonPatch.from_string(patch_str)
                
                # If this is the first patch after pruning, handle potential 'replace' on non-existent path
                if seq == min_sequence and min_sequence > 0:
                    for op in patch.patch: 
                        # If the first operation tries to replace/copy/move on a path that might
                        # not exist in the base {}, try changing it to 'add'.
                        # This is a heuristic based on pruning.
                        if op['op'] in ['replace', 'copy', 'move']: 
                            op['op'] = 'add'

                # Check if it's a primitive replace operation (single operation, replace op, root path '')
                is_primitive_replace = (
                    len(patch.patch) == 1 and 
                    patch.patch[0]['op'] == 'replace' and 
                    patch.patch[0]['path'] == '' # NOTE: jsonpatch uses empty string for root, not '/'
                )
                
                if is_primitive_replace:
                    document = patch.patch[0]['value'] # Replace the whole document
                elif isinstance(document, dict): # Only apply patches if current doc is a dict
                    document = patch.apply(document)
                else:
                    # Handle cases where a patch tries to operate on a non-dict document
                    logger.warning(f"Cannot apply patch to non-dict document at sequence {seq} for path {base_path}")
                    # For simplicity, we might just replace it if the patch is a simple replace
                    if len(patch.patch) == 1 and patch.patch[0]['op'] == 'replace':
                         document = patch.patch[0]['value']
                    # Otherwise, the state might become inconsistent
            except (jsonpatch.JsonPatchConflict, jsonpatch.JsonPointerException) as e:
                # Handle patch application errors
                logger.error(f"Error applying patch at sequence {seq} for path {base_path}: {e}")
                # Decide how to proceed: raise error, return None, or try to continue?
                raise ValueError(f"Failed to apply history patch at sequence {seq}") from e
            except Exception as e:
                 # Catch potential errors from JsonPatch.from_string or apply
                logger.error(f"Unexpected error processing patch at sequence {seq} for path {base_path}: {e}")
                raise ValueError(f"Unexpected error processing history patch at sequence {seq}") from e

        logger.info(f"Successfully previewed document state at path {base_path}, version {target_version}, sequence {sequence}")
        return document
    
    async def restore(
        self, 
        base_path: List[str], 
        sequence: int,
        version: Optional[str] = None,
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> bool:
        """
        Restore document to a specific point in history.
        
        Args:
            base_path: The base path for the document
            sequence: The sequence number to restore to
            version: The version identifier, or None to use the active version
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            True if the document was restored successfully
        """
        # Get document metadata
        metadata = await self._get_document_metadata(base_path, allowed_prefixes)
        if not metadata:
            logger.info(f"No metadata found for document at path {base_path}")
            return False
        
        # Determine which version to use
        target_version = version or metadata.get("active_version")
        if not target_version or target_version not in metadata.get("versions", []):
            logger.error(f"Version '{target_version}' does not exist for document at path {base_path}")
            raise ValueError(f"Version '{target_version}' does not exist")
        
        # Get version data
        version_data = await self._get_version_data(base_path, target_version, allowed_prefixes)
        if not version_data:
            logger.warning(f"No version data found for document at path {base_path}, version {target_version}")
            return False
        
        min_sequence = version_data.get(AsyncMongoVersionedClient.MIN_SEQUENCE_KEY, 0)
        max_sequence = version_data.get(AsyncMongoVersionedClient.MAX_SEQUENCE_KEY, -1)
        
        if sequence < min_sequence or sequence > max_sequence:
            logger.error(f"Sequence number {sequence} is out of range ({min_sequence}-{max_sequence}) for path {base_path}")
            raise ValueError(f"Sequence number {sequence} is out of range ({min_sequence}-{max_sequence})")
        
        # Preview the document at the specified sequence
        restored_document = await self.preview_restore(base_path, sequence, target_version, allowed_prefixes)
        if restored_document is None:
            logger.warning(f"Failed to preview document for restoration at path {base_path}, sequence {sequence}")
            return False
        
        # Delete history items after the specified sequence using batch delete
        paths_to_delete = [
            self._build_history_path(base_path, target_version, seq)
            for seq in range(sequence + 1, max_sequence + 1)
        ]
        if paths_to_delete:
            logger.info(f"Deleting {len(paths_to_delete)} history items after sequence {sequence} for path {base_path}")
            await self.client.batch_delete_objects(paths_to_delete, allowed_prefixes)

        # Update version data
        timestamp = datetime_now_utc()
        # version_data[AsyncMongoVersionedClient.UPDATED_AT_KEY] = timestamp
        # if not isinstance(restored_document, dict):
        #     version_data[AsyncMongoVersionedClient.DOCUMENT_KEY] = restored_document
        # else:
        #     if any(k in restored_document for k in AsyncMongoVersionedClient.ALL_KEYS):
        #         logger.warning(f"Skipping reserved / shadowing keys in document update: {', '.join(k for k in restored_document if k in AsyncMongoVersionedClient.ALL_KEYS)}")
        #     version_data.update({k:v for k,v in restored_document.items() if k not in AsyncMongoVersionedClient.ALL_KEYS})
        # version_data[AsyncMongoVersionedClient.MAX_SEQUENCE_KEY] = sequence
        
        # Prepare the new version_data to be saved after restore
        # Start with essential internal keys from the current version_data, but update relevant ones
        new_version_store_after_restore = { 
            k: v for k, v in version_data.items() 
            if k in AsyncMongoVersionedClient.INTERNAL_KEYS # Keep existing internal keys like IS_COMPLETE, MIN_SEQUENCE
        }
        new_version_store_after_restore[AsyncMongoVersionedClient.CREATED_AT_KEY] = version_data.get(AsyncMongoVersionedClient.CREATED_AT_KEY, timestamp) # Preserve original creation time
        new_version_store_after_restore[AsyncMongoVersionedClient.UPDATED_AT_KEY] = timestamp
        new_version_store_after_restore[AsyncMongoVersionedClient.MAX_SEQUENCE_KEY] = sequence # This is the sequence we are restoring to
        # MIN_SEQUENCE_KEY should already be correct in version_data from _get_version_data
        # IS_COMPLETE_KEY should reflect the state of the restored_document. We need to re-validate or infer it.
        # For now, let's assume preview_restore gives the complete document state, so infer IS_COMPLETE based on schema if available.
        # This part is tricky without re-validation. Let's keep the existing IS_COMPLETE_KEY or default it.
        if AsyncMongoVersionedClient.IS_COMPLETE_KEY not in new_version_store_after_restore:
             new_version_store_after_restore[AsyncMongoVersionedClient.IS_COMPLETE_KEY] = False # Default if somehow missing

        # Add restored user document data
        if not isinstance(restored_document, dict):
            # Primitive type: clear old user keys (if any) and set DOCUMENT_KEY
            keys_to_delete = [
                k for k in new_version_store_after_restore 
                if k not in AsyncMongoVersionedClient.ALL_KEYS and k != AsyncMongoVersionedClient.DOCUMENT_KEY
            ]
            for k_del in keys_to_delete:
                del new_version_store_after_restore[k_del]
            new_version_store_after_restore[AsyncMongoVersionedClient.DOCUMENT_KEY] = restored_document
        else:
            # Dict type: clear old DOCUMENT_KEY (if any) and merge restored_document keys
            if AsyncMongoVersionedClient.DOCUMENT_KEY in new_version_store_after_restore:
                del new_version_store_after_restore[AsyncMongoVersionedClient.DOCUMENT_KEY]
            
            if any(k in restored_document for k in AsyncMongoVersionedClient.RESERVED_KEYS):
                 logger.warning(f"Restored document contains reserved keys: {', '.join(k for k in restored_document if k in AsyncMongoVersionedClient.RESERVED_KEYS)}")
            new_version_store_after_restore.update({ 
                k: v for k, v in restored_document.items() 
                if k not in AsyncMongoVersionedClient.RESERVED_KEYS 
            })

        logger.info(f"Updating version data for path {base_path}, version {target_version} to sequence {sequence}")
        await self._create_or_update_version_data(base_path, target_version, new_version_store_after_restore, allowed_prefixes)
        
        # Update metadata timestamp
        metadata[AsyncMongoVersionedClient.UPDATED_AT_KEY] = timestamp
        await self._create_or_update_metadata(base_path, metadata, allowed_prefixes)
        
        logger.info(f"Successfully restored document at path {base_path} to sequence {sequence}")
        return True
    
    async def list_versions(
        self, 
        base_path: List[str],
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> List[Dict[str, Any]]:
        """
        List all versions of a document with their metadata.
        
        Args:
            base_path: The base path for the document
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            List of version information
        """
        # Get document metadata
        metadata = await self._get_document_metadata(base_path, allowed_prefixes)
        if not metadata:
            logger.info(f"No metadata found for document at path {base_path}")
            return []
        
        versions = metadata.get("versions", [])
        active_version = metadata.get("active_version")
        
        logger.debug(f"Found {len(versions)} versions for document at path {base_path}")
        
        # Collect version paths for batch fetch
        version_paths = [
            self._build_version_path(base_path, version)
            for version in versions
        ]
        
        # Fetch version data in batch
        batch_results = await self.client.batch_fetch_objects(version_paths, allowed_prefixes)
        
        # Map path strings back to version names for easier lookup
        path_to_version = {str(self._build_version_path(base_path, v)): v for v in versions}
        
        # Process results
        result = []
        for path_str, doc in batch_results.items():
            version_name = path_to_version.get(path_str)
            if doc and version_name:
                version_data = doc['data']
                min_seq = version_data.get(AsyncMongoVersionedClient.MIN_SEQUENCE_KEY, 0)
                max_seq = version_data.get(AsyncMongoVersionedClient.MAX_SEQUENCE_KEY, -1)
                edit_count = (max_seq - min_seq + 1) if max_seq >= min_seq else 0
                
                result.append({
                    "version": version_name,
                    "is_active": version_name == active_version,
                    AsyncMongoVersionedClient.CREATED_AT_KEY: version_data.get(AsyncMongoVersionedClient.CREATED_AT_KEY),
                    AsyncMongoVersionedClient.UPDATED_AT_KEY: version_data.get(AsyncMongoVersionedClient.UPDATED_AT_KEY),
                    AsyncMongoVersionedClient.IS_COMPLETE_KEY: version_data.get(AsyncMongoVersionedClient.IS_COMPLETE_KEY, False),
                    "edit_count": edit_count
                })

        logger.info(f"Retrieved {len(result)} version details for document at path {base_path}")
        return result
    
    async def delete_version(
        self, 
        base_path: List[str],
        version: str,
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> bool:
        """
        Delete a specific version of a document.
        
        Args:
            base_path: The base path for the document
            version: The version identifier to delete
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            True if the version was deleted successfully
        """
        # Get document metadata
        metadata = await self._get_document_metadata(base_path, allowed_prefixes)
        if not metadata:
            logger.info(f"No metadata found for document at path {base_path}")
            return False
        
        versions = metadata.get("versions", [])
        active_version = metadata.get("active_version")
        
        # Check if version exists
        if version not in versions:
            logger.warning(f"Version '{version}' does not exist for document at path {base_path}")
            return False
        
        # Can't delete active version
        if version == active_version:
            logger.error(f"Cannot delete active version '{version}' for document at path {base_path}")
            raise ValueError("Cannot delete the active version")
        
        # Delete version data
        version_path = self._build_version_path(base_path, version)
        logger.info(f"Deleting version data for path {base_path}, version {version}")
        version_deleted = await self.client.delete_object(version_path, allowed_prefixes)
        
        # Delete all history items using pattern matching (efficient enough)
        history_pattern = self._build_history_pattern(base_path, version)
        logger.info(f"Deleting history items for path {base_path}, version {version}")
        await self.client.delete_objects(history_pattern, allowed_prefixes)
        
        # Update metadata
        if version_deleted:
            metadata["versions"] = [v for v in versions if v != version]
            metadata[AsyncMongoVersionedClient.UPDATED_AT_KEY] = datetime_now_utc()
            await self._create_or_update_metadata(base_path, metadata, allowed_prefixes)
            logger.info(f"Successfully deleted version '{version}' for document at path {base_path}")
        else:
            logger.warning(f"Failed to delete version data for path {base_path}, version {version}")
        
        return version_deleted
    
    async def delete_document(
        self, 
        base_path: List[str],
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> bool:
        """
        Delete a document and all its versions and history.
        
        Args:
            base_path: The base path for the document
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            True if the document was deleted successfully
        """
        # Get document metadata
        metadata = await self._get_document_metadata(base_path, allowed_prefixes)
        if not metadata:
            logger.info(f"No metadata found for document at path {base_path}")
            return False
        
        # Delete all versions using batch delete for version data
        versions = metadata.get("versions", [])
        version_paths_to_delete = []
        history_patterns_to_delete = []

        for version in versions:
            version_paths_to_delete.append(self._build_version_path(base_path, version))
            # Collect history patterns for individual deletion (batch pattern deletion isn't directly supported)
            history_patterns_to_delete.append(self._build_history_pattern(base_path, version))

        # Batch delete version documents
        if version_paths_to_delete:
            logger.info(f"Deleting {len(version_paths_to_delete)} version documents for path {base_path}")
            await self.client.batch_delete_objects(version_paths_to_delete, allowed_prefixes)
            
        # Delete history for each version using pattern delete
        for pattern in history_patterns_to_delete:
            logger.info(f"Deleting history items matching pattern {pattern} for path {base_path}")
            await self.client.delete_objects(pattern, allowed_prefixes)

        # Delete metadata
        metadata_path = self._build_metadata_path(base_path)
        logger.info(f"Deleting metadata for document at path {base_path}")
        result = await self.client.delete_object(metadata_path, allowed_prefixes)
        
        if result:
            logger.info(f"Successfully deleted document and all versions at path {base_path}")
        else:
            logger.warning(f"Failed to delete metadata for document at path {base_path}")
            
        return result
    
    async def get_schema(
        self, 
        base_path: List[str],
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get the JSON schema for a document.
        
        Args:
            base_path: The base path for the document
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            The JSON schema, or None if it doesn't exist
        """
        metadata = await self._get_document_metadata(base_path, allowed_prefixes)
        if not metadata:
            logger.info(f"No metadata found for document at path {base_path}")
            return None
        
        schema = metadata.get("schema")
        if schema:
            logger.debug(f"Retrieved schema for document at path {base_path}")
        else:
            logger.info(f"No schema defined for document at path {base_path}")
            
        return schema
    
    async def update_schema(
        self, 
        base_path: List[str],
        schema: Dict[str, Any],
        allowed_prefixes: Optional[List[List[str]]] = None
    ) -> bool:
        """
        Update the JSON schema for a document.
        
        Args:
            base_path: The base path for the document
            schema: The new JSON schema
            allowed_prefixes: Optional list of allowed path prefixes for permission checking
            
        Returns:
            True if the schema was updated successfully
        """
        metadata = await self._get_document_metadata(base_path, allowed_prefixes)
        if not metadata:
            logger.warning(f"No metadata found for document at path {base_path}, cannot update schema")
            return False
        
        # Update schema
        metadata["schema"] = schema
        metadata[AsyncMongoVersionedClient.UPDATED_AT_KEY] = datetime_now_utc()
        
        logger.info(f"Updating schema for document at path {base_path}")
        await self._create_or_update_metadata(base_path, metadata, allowed_prefixes)
        return True
