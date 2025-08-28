# services/workflow_service/registry/nodes/db/customer_data.py
"""
Nodes for interacting with customer data stored in MongoDB via CustomerDataService.

Provides nodes for loading and storing both versioned and unversioned documents,
respecting organization, user, shared, and system data access patterns.
"""

import copy
from datetime import datetime, timezone
import json
import traceback
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Type, ClassVar, Tuple, Set, get_origin

from pydantic import Field, model_validator, BaseModel, ValidationError

# Internal dependencies
from global_config.logger import get_prefect_or_regular_python_logger

from kiwi_app.workflow_app.constants import LaunchStatus
from kiwi_app.auth.models import User
from kiwi_app.workflow_app.schemas import WorkflowRunJobCreate # For application context typing
from kiwi_app.workflow_app.service_customer_data import CustomerDataService
# This causes circular imports!
# from workflow_service.services.external_context_manager import ExternalContextManager
from sqlmodel.ext.asyncio.session import AsyncSession
from workflow_service.config.constants import (
    APPLICATION_CONTEXT_KEY,
    EXTERNAL_CONTEXT_MANAGER_KEY,
)
from db.session import get_async_db_as_manager

from global_utils.utils import datetime_now_utc

# Base node/schema types
from workflow_service.registry.schemas.base import BaseSchema, BaseNodeConfig
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema, BaseDynamicNode


# --- Helper Functions ---

def _get_nested_obj(data: Any, field_path: str) -> Tuple[Any, bool]:
    """
    Retrieves a nested object or value at the specified path.

    Handles navigation through dictionaries and lists using dot notation.

    Args:
        data: The data structure (dict or list) to navigate.
        field_path: Dot-notation path (e.g., 'a.b.0.c').

    Returns:
        Tuple[Any, bool]: The retrieved object/value and a boolean indicating if the path was found.
                         Returns (None, False) if the path is invalid or not found.
    """
    current = data
    parts = field_path.split('.') if field_path else []

    if not field_path:
        return data, True # Return the whole data if path is empty

    for part in parts:
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                return None, False # Key not found in dict
        elif isinstance(current, list):
            try:
                idx = int(part)
                # Check bounds for list index
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None, False # Index out of bounds
            except (ValueError, TypeError):
                # Invalid index format for list
                return None, False
        else:
            # Cannot navigate further (e.g., encountered a primitive type)
            return None, False

    return current, True

def _set_nested_obj(data: Dict[str, Any], field_path: str, value: Any, logger: Optional[BaseDynamicNode] = None) -> bool:
    """
    Sets a value in a nested dictionary or list structure.

    Creates necessary dictionaries if intermediate path segments for dictionaries do not exist.
    Assumes lists and their indices exist up to the point of setting the value for list elements.

    Args:
        data: The dictionary to modify.
        field_path: Dot-notation path (e.g., 'a.b.0.c') where the value should be set.
        value: The value to set at the specified path.

    Returns:
        bool: True if the value was successfully set, False otherwise (e.g., path is invalid).
    """
    logger = logger or get_prefect_or_regular_python_logger(f"{__name__}._set_nested_obj")
    parts = field_path.split('.')
    current_obj = data
    
    # Navigate to the parent object of the target key/index
    for i, part in enumerate(parts[:-1]):
        if isinstance(current_obj, dict):
            if part not in current_obj or not isinstance(current_obj[part], (dict, list)):
                # If the next part is supposed to be a dict key (because it's not the last part of a list index path)
                # or if the structure needs to be created.
                # Check if the next part in the path is an integer, suggesting it's a list index.
                # This check is a bit heuristic; ideally, schema information would guide this.
                # For now, if we need to create, we default to creating a dict.
                is_next_part_list_index = False
                if i + 1 < len(parts) -1 : # Check if there's a part after the current `part`
                    try:
                        int(parts[i+1]) # If the part *after* current `part` is an int, then `current_obj[part]` should be a list.
                                        # This logic is imperfect for _set_ as we might be setting into a non-existent list.
                                        # For simplicity, we assume dict creation if path not found.
                                        # Proper list creation would require knowing the type.
                        pass # Not creating list structure here, assuming dicts primarily.
                    except ValueError:
                        pass # Not an int, so likely a dict key.

                current_obj[part] = {} # Default to creating a dictionary
            current_obj = current_obj[part]
        elif isinstance(current_obj, list):
            try:
                idx = int(part)
                if 0 <= idx < len(current_obj):
                    current_obj = current_obj[idx]
                else:
                    logger.error(f"Index {idx} out of bounds for path segment '{part}' in path '{field_path}'. Current list length: {len(current_obj)}.")
                    return False # Index out of bounds
            except (ValueError, TypeError):
                logger.error(f"Invalid list index '{part}' in path '{field_path}'.")
                return False # Invalid index format for list
        else:
            logger.error(f"Cannot traverse path '{field_path}': segment '{part}' leads to a non-container type ({type(current_obj)}).")
            return False # Path leads to a non-container type

    # Set the value at the final key/index
    last_part = parts[-1]
    if isinstance(current_obj, dict):
        current_obj[last_part] = value
        return True
    elif isinstance(current_obj, list):
        try:
            idx = int(last_part)
            if 0 <= idx < len(current_obj):
                current_obj[idx] = value
                return True
            # elif idx == len(current_obj): # Append behavior not implemented as per "update" requirement
            #     current_obj.append(value)
            #     return True
            else:
                logger.error(f"Final index {idx} out of bounds for list at path '{'.'.join(parts[:-1])}' in path '{field_path}'. List length: {len(current_obj)}.")
                return False # Index out of bounds for setting
        except (ValueError, TypeError):
            logger.error(f"Final path segment '{last_part}' is not a valid list index for path '{field_path}'.")
            return False # last_part is not a valid index for a list
    else:
        logger.error(f"Cannot set value: parent for '{last_part}' in path '{field_path}' is not a dict or list, but {type(current_obj)}.")
        return False

# --- New Filename Configuration Schema and Helper ---

class FilenameConfig(BaseNodeConfig):
    """
    Configuration for determining the namespace and docname for a customer data operation.

    Supports static values, dynamic retrieval from input fields, pattern-based generation
    using the current item context, or pattern-based generation using data from a
    specific input field.

    Context for patterns:
    - `namespace_pattern`/`docname_pattern`: Use `{'item': current_item_data, 'index': item_index}`.
    - `input_namespace_field_pattern`/`input_docname_field_pattern`: Use `{'item': retrieved_data_from_input_field}`.
    """
    # Static Definition
    static_namespace: Optional[str] = Field(
        None, description="A fixed namespace value."
    )
    static_docname: Optional[str] = Field(
        None, description="A fixed document name value."
    )

    # Dynamic Retrieval from Input Data (direct value)
    input_namespace_field: Optional[str] = Field(
        None, description="Dot-notation path in the input data to retrieve the namespace value OR the object for pattern evaluation."
    )
    input_docname_field: Optional[str] = Field(
        None, description="Dot-notation path in the input data to retrieve the docname value OR the object for pattern evaluation."
    )

    # Pattern-Based Generation (using current item context)
    namespace_pattern: Optional[str] = Field(
        None, description="f-string like template to generate the namespace (e.g., 'user_{item[user_id]}'). Uses 'item' and 'index' context from the currently processed item."
    )
    docname_pattern: Optional[str] = Field(
        None, description="f-string like template to generate the docname (e.g., 'order_{item[order_id]}_{index}'). Uses 'item' and 'index' context from the currently processed item."
    )

    # Pattern-Based Generation (using data from specific input field)
    input_namespace_field_pattern: Optional[str] = Field(
        None, description="f-string like template to generate the namespace using data found at 'input_namespace_field'. Uses {'item': retrieved_data} context."
    )
    input_docname_field_pattern: Optional[str] = Field(
        None, description="f-string like template to generate the docname using data found at 'input_docname_field'. Uses {'item': retrieved_data} context."
    )

    @model_validator(mode='after')
    def validate_config(self) -> 'FilenameConfig':
        """Ensures a valid and unique combination of fields is provided for namespace and docname."""
        # Namespace validation
        logger = get_prefect_or_regular_python_logger(f"{__name__}")
        ns_sources = [
            self.static_namespace,
            self.input_namespace_field and not self.input_namespace_field_pattern, # Field used directly
            self.namespace_pattern,
            self.input_namespace_field_pattern
        ]
        num_ns_sources = sum(1 for source in ns_sources if source) # Count how many are not None/False
        
        if num_ns_sources > 1:
            logger.error("Multiple namespace sources configured in FilenameConfig")
            raise ValueError("Provide only one source for namespace: static_namespace, input_namespace_field (direct), namespace_pattern, or input_namespace_field_pattern.")
        if num_ns_sources == 0:
            logger.error("No namespace source configured in FilenameConfig")
            raise ValueError("One source for namespace must be provided: static_namespace, input_namespace_field, namespace_pattern, or input_namespace_field_pattern.")
        
        # If using input_namespace_field_pattern, input_namespace_field must be set
        if self.input_namespace_field_pattern and not self.input_namespace_field:
            logger.error("input_namespace_field_pattern used without input_namespace_field")
            raise ValueError("'input_namespace_field' must be provided when using 'input_namespace_field_pattern'.")
        
        # Docname validation
        dn_sources = [
            self.static_docname,
            self.input_docname_field and not self.input_docname_field_pattern, # Field used directly
            self.docname_pattern,
            self.input_docname_field_pattern
        ]
        num_dn_sources = sum(1 for source in dn_sources if source) # Count how many are not None/False
        
        if num_dn_sources > 1:
            logger.error("Multiple docname sources configured in FilenameConfig")
            raise ValueError("Provide only one source for docname: static_docname, input_docname_field (direct), docname_pattern, or input_docname_field_pattern.")
        if num_dn_sources == 0:
            logger.error("No docname source configured in FilenameConfig")
            raise ValueError("One source for docname must be provided: static_docname, input_docname_field, docname_pattern, or input_docname_field_pattern.")
        
        # If using input_docname_field_pattern, input_docname_field must be set
        if self.input_docname_field_pattern and not self.input_docname_field:
            logger.error("input_docname_field_pattern used without input_docname_field")
            raise ValueError("'input_docname_field' must be provided when using 'input_docname_field_pattern'.")
        
        # Original pattern validation (basic checks)
        if self.namespace_pattern and ('{' not in self.namespace_pattern or '}' not in self.namespace_pattern):
            logger.warning(f"namespace_pattern '{self.namespace_pattern}' doesn't look like a valid f-string pattern.")
        if self.docname_pattern and ('{' not in self.docname_pattern or '}' not in self.docname_pattern):
            logger.warning(f"docname_pattern '{self.docname_pattern}' doesn't look like a valid f-string pattern.")
        # New pattern validation (basic checks)
        if self.input_namespace_field_pattern and ('{' not in self.input_namespace_field_pattern or '}' not in self.input_namespace_field_pattern):
            logger.warning(f"input_namespace_field_pattern '{self.input_namespace_field_pattern}' doesn't look like a valid f-string pattern.")
        if self.input_docname_field_pattern and ('{' not in self.input_docname_field_pattern or '}' not in self.input_docname_field_pattern):
            logger.warning(f"input_docname_field_pattern '{self.input_docname_field_pattern}' doesn't look like a valid f-string pattern.")
        
        return self

def _resolve_single_doc_path(
    config: FilenameConfig,
    full_input_data: Dict[str, Any],
    current_item_data: Optional[Dict[str, Any]] = None,
    item_index: Optional[int] = None,
    generated_uuid: Optional[str] = None,  # NEW PARAMETER: Pass generated UUID if available
    logger: Optional[BaseDynamicNode] = None,
) -> Optional[Tuple[str, str]]:
    """
    Resolves the namespace and docname for a single document operation.

    Handles static, dynamic (retrieved from fields inside/outside the item),
    and pattern-based resolution.

    Args:
        config: The FilenameConfig instructing how to resolve the path.
        full_input_data: The complete input dict given to the node's process method.
                         Used for resolving input fields pointing outside the current item.
        current_item_data: The specific dictionary representing the document being processed
                           (e.g., an item from a list being stored). Required for
                           resolving input fields within the item and for patterns.
                           If None, dynamic fields must point to full_input_data.
        item_index: The index if current_item_data is from a list. Used for pattern context.
        generated_uuid: If provided, this UUID will be used for _uuid_ placeholders in docname patterns
                        instead of generating a new one.

    Returns:
        A tuple (namespace, docname) or None if resolution fails.
    """
    logger = logger or get_prefect_or_regular_python_logger(f"{__name__}")
    resolved_namespace: Optional[str] = None
    resolved_docname: Optional[str] = None
    context_data = current_item_data if current_item_data is not None else full_input_data

    # --- Resolve Namespace ---
    if config.static_namespace is not None:
        resolved_namespace = config.static_namespace
    elif config.input_namespace_field and not config.input_namespace_field_pattern:
        # Direct retrieval using input_namespace_field
        # Try finding the field within the current item first, fallback to full input
        # Note: This prioritizes current_item if available, might need adjustment based on exact desired behavior.
        # Let's prioritize full_input_data for fields meant to be *outside* the item.
        ns_val, found = _get_nested_obj(full_input_data, config.input_namespace_field)
        if not found and current_item_data is not None: # Fallback only if not found in full input
             ns_val, found = _get_nested_obj(current_item_data, config.input_namespace_field)

        if found and isinstance(ns_val, str):
            resolved_namespace = ns_val
        else:
            logger.warning(f"Direct namespace field '{config.input_namespace_field}' not found in full input or item, or not a string.")
            return None
    elif config.input_namespace_field_pattern:
        # Pattern evaluation using data from input_namespace_field
        if not config.input_namespace_field: # Should be caught by validator, but double-check
             logger.error("Config Error: input_namespace_field_pattern specified without input_namespace_field.")
             return None
        # Retrieve the object to use in the pattern context
        pattern_source_data, found = _get_nested_obj(full_input_data, config.input_namespace_field)
        if not found:
             logger.warning(f"Data for namespace pattern not found at '{config.input_namespace_field}' in full input data.")
             return None
        try:
            # Use the retrieved object as 'item' in the pattern context
            resolved_namespace = config.input_namespace_field_pattern.format(item=pattern_source_data)
        except KeyError as e:
            logger.error(f"Error formatting input_namespace_field_pattern '{config.input_namespace_field_pattern}': Key {e} not found in data at '{config.input_namespace_field}'.")
            return None
        except Exception as e:
            logger.error(f"Error formatting input_namespace_field_pattern '{config.input_namespace_field_pattern}': {e}")
            return None
    elif config.namespace_pattern:
        # Original pattern evaluation using current_item_data and item_index
        if current_item_data is None:
            logger.error("Cannot evaluate namespace_pattern: 'current_item_data' is missing (required for this pattern type).")
            return None
        try:
            # Provide 'item' (current item) and 'index' context for formatting
            pattern_context = {'item': current_item_data, 'index': item_index}
            resolved_namespace = config.namespace_pattern.format(**pattern_context)
        except KeyError as e:
            logger.error(f"Error formatting namespace_pattern '{config.namespace_pattern}': Key {e} not found in current item data.")
            return None
        except Exception as e:
            logger.error(f"Error formatting namespace_pattern '{config.namespace_pattern}': {e}")
            return None
    else:
         # Should be caught by validator
         logger.error("Invalid FilenameConfig state for namespace.")
         return None

    DOCNAME_SPECIAL_PLACEHOLDERS = {
        "_uuid_": lambda: generated_uuid if generated_uuid else str(uuid.uuid4()),  # Use the provided UUID if available
        "_timestamp_": lambda: datetime_now_utc().isoformat() 
    }

    # --- Resolve Docname ---
    if config.static_docname is not None:
        resolved_docname = config.static_docname
        kwargs = {}
        for placeholder, func in DOCNAME_SPECIAL_PLACEHOLDERS.items():
            if f"{{{placeholder}}}" in resolved_docname:
                kwargs[placeholder] = func()
        if kwargs:
            resolved_docname = resolved_docname.format(**kwargs)
    elif config.input_docname_field and not config.input_docname_field_pattern:
        # Direct retrieval using input_docname_field
        dn_val, found = _get_nested_obj(full_input_data, config.input_docname_field)
        if not found and current_item_data is not None: # Fallback
             dn_val, found = _get_nested_obj(current_item_data, config.input_docname_field)

        if found and isinstance(dn_val, str):
            resolved_docname = dn_val
        else:
            logger.warning(f"Direct docname field '{config.input_docname_field}' not found in full input or item, or not a string.")
            return None
    elif config.input_docname_field_pattern:
         # Pattern evaluation using data from input_docname_field
        if not config.input_docname_field: # Should be caught by validator
             logger.error("Config Error: input_docname_field_pattern specified without input_docname_field.")
             return None
        # Retrieve the object to use in the pattern context
        pattern_source_data, found = _get_nested_obj(full_input_data, config.input_docname_field)
        if not found:
             logger.warning(f"Data for docname pattern not found at '{config.input_docname_field}' in full input data.")
             return None
        try:
            kwargs = {
                'item': pattern_source_data,
            }
            for placeholder, func in DOCNAME_SPECIAL_PLACEHOLDERS.items():
                if f"{{{placeholder}}}" in config.input_docname_field_pattern:
                    kwargs[placeholder] = func()
            # Use the retrieved object as 'item' in the pattern context
            resolved_docname = config.input_docname_field_pattern.format(**kwargs)
        except KeyError as e:
            logger.error(f"Error formatting input_docname_field_pattern '{config.input_docname_field_pattern}': Key {e} not found in data at '{config.input_docname_field}'.")
            return None
        except Exception as e:
            logger.error(f"Error formatting input_docname_field_pattern '{config.input_docname_field_pattern}': {e}")
            return None
    elif config.docname_pattern:
        # Original pattern evaluation using current_item_data and item_index
        if current_item_data is None:
            logger.error("Cannot evaluate docname_pattern: 'current_item_data' is missing (required for this pattern type).")
            return None
        try:
            # Provide 'item' (current item) and 'index' context for formatting
            pattern_context = {'item': current_item_data, 'index': item_index}
            for placeholder, func in DOCNAME_SPECIAL_PLACEHOLDERS.items():
                if f"{{{placeholder}}}" in config.docname_pattern:
                    pattern_context[placeholder] = func()
            resolved_docname = config.docname_pattern.format(**pattern_context)
        except KeyError as e:
            logger.error(f"Error formatting docname_pattern '{config.docname_pattern}': Key {e} not found in current item data.")
            return None
        except Exception as e:
            logger.error(f"Error formatting docname_pattern '{config.docname_pattern}': {e}")
            return None
    else:
         # Should be caught by validator
         logger.error("Invalid FilenameConfig state for docname.")
         return None

    # Final check
    if resolved_namespace is not None and resolved_docname is not None:
        return resolved_namespace, resolved_docname
    else:
        logger.error("Failed to resolve namespace or docname.")
        return None

# --- Enums ---

class StoreOperation(str, Enum):
    """Defines the operation to perform when storing data."""
    INITIALIZE = "initialize" # Initialize a new versioned document (fails if exists)
    UPDATE = "update"         # Update an existing document (versioned or unversioned, fails if not exists)
    UPSERT = "upsert"         # Create or update an unversioned document
    CREATE_VERSION = "create_version" # Create a new version for an existing versioned document
    UPSERT_VERSIONED = "upsert_versioned" # Update a versioned document, or initialize if it doesn't exist

# --- Common Schemas ---

class VersionConfig(BaseNodeConfig):
    """Configuration for specifying a document version."""
    version: Optional[str] = Field(
        None,
        description="The specific version name to load or store (e.g., 'default', 'v1.2')."
    )

class SchemaOptions(BaseNodeConfig):
    """Options for handling document schemas during load/store."""
    load_schema: bool = Field(
        False,
        description="If true, attempts to load the schema associated with the document (only applicable for versioned documents)."
    )
    # Below are primarily for specifying schema during store or for validating unversioned docs on load/store
    schema_template_name: Optional[str] = Field(
        None,
        description="Name of a Schema Template to use for validation or association."
    )
    schema_template_version: Optional[str] = Field(
        None,
        description="Version of the Schema Template (optional, defaults to latest accessible)."
    )
    # Allows providing a schema directly in the config
    schema_definition: Optional[Dict[str, Any]] = Field(
        None,
        description="A direct JSON schema definition to use for validation or association."
    )

    @model_validator(mode='after')
    def check_schema_source(self) -> 'SchemaOptions':
        """Ensure only one schema source (template or definition) is provided."""
        if self.schema_template_name and self.schema_definition:
            raise ValueError("Provide either 'schema_template_name' or 'schema_definition', not both.")
        return self

# --- Extra Field Configuration for Store Customer Data ---

class ExtraFieldConfig(BaseNodeConfig):
    """
    Configuration for adding extra fields to objects before storing.
    
    Extra fields are retrieved from the input data and added to the object(s) being stored.
    """
    src_path: str = Field(
        ...,
        description="Dot-notation path within the full input data to find the value to add."
    )
    dst_path: Optional[str] = Field(
        None,
        description="Dot-notation path within the object being stored where the value should be placed. "
                   "If not provided, defaults to the last segment of src_path."
    )

    @model_validator(mode='after')
    def set_default_dst_path(self) -> 'ExtraFieldConfig':
        """Set default dst_path if not provided."""
        if self.dst_path is None:
            # Use the last segment of src_path as the default dst_path
            path_segments = self.src_path.split('.')
            if path_segments:
                self.dst_path = path_segments[-1]
            else:
                raise ValueError("Invalid src_path: must contain at least one segment")
        return self

# Helper function to add extra fields to an object
def _add_extra_fields(
    target_obj: Any, 
    full_input_data: Dict[str, Any], 
    extra_fields: List[ExtraFieldConfig],
    logger: BaseDynamicNode
) -> Any:
    """
    Adds extra fields to the target object based on the provided configuration.
    
    Args:
        target_obj: The object to add fields to (modified in-place if dict)
        full_input_data: The complete input data to retrieve values from
        extra_fields: List of ExtraFieldConfig objects defining fields to add
        logger: Logger instance for error reporting
        
    Returns:
        The modified object (same object if dict, or wrapper object if non-dict)
    """
    if not isinstance(target_obj, dict):
        logger.warning(f"Target object is not a dictionary, extra fields will be skipped: {type(target_obj)}")
        return target_obj
    
    # Create a mutable copy if needed
    target_dict = target_obj
    
    for field_config in extra_fields:
        # Retrieve value from source path
        value, found = _get_nested_obj(full_input_data, field_config.src_path)
        
        if not found:
            logger.warning(f"Source path '{field_config.src_path}' not found in input data, skipping extra field")
            continue
            
        # Skip if value is a list (as per requirements)
        if isinstance(value, list):
            logger.warning(f"Source path '{field_config.src_path}' resolves to a list, skipping as per requirements")
            continue
            
        # Set value at destination path (handle nested paths)
        dst_parts = field_config.dst_path.split('.')
        current = target_dict
        
        # Navigate to the final object that will contain the field
        for i, part in enumerate(dst_parts[:-1]):
            if part not in current:
                current[part] = {}
            elif not isinstance(current[part], dict):
                logger.warning(f"Cannot add field at '{field_config.dst_path}': path segment '{part}' exists but is not a dictionary")
                break
            current = current[part]
        else:
            # Set the value in the final object
            current[dst_parts[-1]] = value
            logger.debug(f"Added extra field '{field_config.dst_path}' with value from '{field_config.src_path}'")
    
    return target_dict

# --- Load Customer Data Node ---

class LoadPathConfig(BaseNodeConfig):
    """Configuration for loading a single document or pattern."""
    filename_config: FilenameConfig = Field(
        ...,
        description="Configuration defining how to determine the document's namespace and docname."
    )
    # Output Field
    output_field_name: str = Field(
        ...,
        description="The field name in the output data where the loaded document(s) will be placed. "
                    "Must not start with underscore (_) as it may conflict with Pydantic reserved fields."
    )
    # Path Modifiers (use global defaults if None)
    is_shared: Optional[bool] = Field(
        None, description="Override global default: Access shared data instead of user-specific."
    )
    is_system_entity: Optional[bool] = Field(
        None, description="Override global default: Access system data (requires superuser)."
    )
    # Versioning (use global defaults if None)
    version_config: Optional[VersionConfig] = Field(
        None, description="Override global default: Specify version to load."
    )
    # Schema Handling (use global defaults if None)
    schema_options: Optional[SchemaOptions] = Field(
        None, description="Override global default: Schema loading/validation options."
    )
    # NEW FIELD: Optional user ID to act on behalf of
    on_behalf_of_user_id: Optional[str] = Field(
        None, description="User ID (as string) to act on behalf of (requires superuser privileges). Overrides global default."
    )

    @model_validator(mode='after')
    def validate_output_field_name(self) -> 'LoadPathConfig':
        """Ensure output_field_name doesn't start with underscore to avoid conflicts with Pydantic reserved fields."""
        if self.output_field_name.startswith('_'):
            raise ValueError(f"output_field_name '{self.output_field_name}' cannot start with underscore (_) as it may conflict with Pydantic reserved fields.")
        return self

class LoadCustomerDataConfig(BaseNodeConfig):
    """
    Configuration schema for the LoadCustomerDataNode.

    Defines document loading either via a static list of configurations (`load_paths`)
    or dynamically by specifying a path (`load_configs_input_path`) within the input
    data that contains the configuration(s).
    """
    # Static list of load configurations
    load_paths: Optional[List[LoadPathConfig]] = Field(
        None, # Changed from ... to None, making it optional
        min_length=1, # Keep min_length constraint if provided directly
        description="List of configurations, each defining a document or pattern to load. Used if 'load_configs_input_path' is not provided."
    )
    # Dynamic loading from input data
    load_configs_input_path: Optional[str] = Field(
        None,
        description="Dot-notation path within the node's input data to find the load configuration(s). "
                    "This can be a single JSON object matching LoadPathConfig structure, or a list of such objects. "
                    "If provided, this overrides 'load_paths'."
    )

    # Global defaults (applied if not overridden in LoadPathConfig)
    global_is_shared: bool = Field(False, description="Default value for 'is_shared'.")
    global_is_system_entity: bool = Field(False, description="Default value for 'is_system_entity'.")
    global_version_config: VersionConfig = Field(
        default_factory=VersionConfig, description="Default version configuration."
    )
    global_schema_options: SchemaOptions = Field(
        default_factory=SchemaOptions, description="Default schema handling options."
    )
    # NEW FIELD: Global default for on behalf of user ID
    global_on_behalf_of_user_id: Optional[str] = Field(
        None, description="Default User ID (as string) to act on behalf of (requires superuser privileges)."
    )

    @model_validator(mode='after')
    def check_config_source(self) -> 'LoadCustomerDataConfig':
        """Ensure either load_paths or load_configs_input_path is provided, but not both."""
        if self.load_paths is None and self.load_configs_input_path is None:
            raise ValueError("Either 'load_paths' or 'load_configs_input_path' must be provided.")
        if self.load_paths is not None and self.load_configs_input_path is not None:
            raise ValueError("Provide either 'load_paths' or 'load_configs_input_path', not both.")
        # Ensure load_paths has at least one item if it's the chosen source
        if self.load_paths is not None and not self.load_paths:
             raise ValueError("'load_paths' must contain at least one configuration if provided.")
        return self

class LoadCustomerDataOutput(DynamicSchema):
    """
    Output schema for the LoadCustomerDataNode.

    Inherits from DynamicSchema, allowing loaded data to be added dynamically.
    Includes a dedicated field for metadata like loaded schemas.
    """
    loaded_fields: List[str] = Field(default_factory=list) # Internal tracking
    output_metadata: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Metadata associated with loaded documents, keyed by 'output_field_name'. E.g., {'my_doc': {'schema': {...}}}"
    )

class LoadCustomerDataNode(BaseDynamicNode):
    """
    Node to load customer data documents (versioned or unversioned) from MongoDB.

    Retrieves documents based on specified paths (static or derived from input)
    and places them into the output data stream under configured field names.
    Supports loading specific versions and associated schemas.
    Handles shared, user-specific, and system-level documents based on user permissions.

    # TODO: Add support for loading multiple documents at once using patterns
    """
    node_name: ClassVar[str] = "load_customer_data"
    node_version: ClassVar[str] = "0.1.4" # Added on_behalf_of_user_id support
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.PRODUCTION
    # Ineriting input / output dynamic schemas from base class!
    # input_schema_cls: Type[DynamicSchema] = DynamicSchema
    output_schema_cls: ClassVar[Type[LoadCustomerDataOutput]] = LoadCustomerDataOutput
    config_schema_cls: ClassVar[Type[LoadCustomerDataConfig]] = LoadCustomerDataConfig
    config: LoadCustomerDataConfig

    async def process(
        self,
        input_data: Union[DynamicSchema, Dict[str, Any]],
        runtime_config: Optional[Dict[str, Any]] = None,
        *args: Any,
        **kwargs: Any
    ) -> LoadCustomerDataOutput:
        """
        Loads customer data based on the node's configuration.

        Can load configurations statically defined in `load_paths` or dynamically
        from `load_configs_input_path` pointing to data within `input_data`.

        Args:
            input_data: The input data potentially containing path information.
            runtime_config: The runtime configuration containing execution context
                            (MUST include APPLICATION_CONTEXT_KEY and EXTERNAL_CONTEXT_MANAGER_KEY).
            *args: Additional positional arguments (unused).
            **kwargs: Additional keyword arguments (unused).

        Returns:
            LoadCustomerDataOutput: An object containing the loaded data and metadata.
                                    Fields are dynamically added based on 'output_field_name'.
        """
        
        if not runtime_config:
            self.error("Missing runtime_config.")
            return self.__class__.output_schema_cls(__root__={}, output_metadata={})
        
        runtime_config = runtime_config.get("configurable")
        app_context: Optional[Dict[str, Any]] = runtime_config.get(APPLICATION_CONTEXT_KEY)
        ext_context = runtime_config.get(EXTERNAL_CONTEXT_MANAGER_KEY)  # : Optional[ExternalContextManager]
        if not app_context or not ext_context:
            self.error(f"Missing required keys in runtime_config: {APPLICATION_CONTEXT_KEY} or {EXTERNAL_CONTEXT_MANAGER_KEY}")
            return self.__class__.output_schema_cls(__root__={}, output_metadata={})
        user: Optional[User] = app_context.get("user")
        run_job: Optional[WorkflowRunJobCreate] = app_context.get("workflow_run_job")
        if not user or not run_job:
            self.error("Missing 'user' or 'workflow_run_job' in application_context.")
            return self.__class__.output_schema_cls(__root__={}, output_metadata={})
        org_id = run_job.owner_org_id
        customer_data_service: CustomerDataService = ext_context.customer_data_service
        input_dict = input_data if isinstance(input_data, dict) else input_data.model_dump(mode='json')

        # self.info(f"Starting LoadCustomerDataNode processing, runtime_config: {runtime_config}")
        # self.info(f"\n\nStarting LoadCustomerDataNode processing, runtime_config OUTGOING EDGES: {runtime_config.get('outgoing_edges', {})}\n\n")

        output_data: Dict[str, Any] = {}
        output_meta: Dict[str, Dict[str, Any]] = {}

        effective_load_configs: List[LoadPathConfig] = []

        # --- Determine effective load configurations ---
        if self.config.load_configs_input_path:
            self.info(f"Attempting to load configurations dynamically from input path: {self.config.load_configs_input_path}")
            config_data, found = _get_nested_obj(input_dict, self.config.load_configs_input_path)
            if not found:
                self.error(f"Input path '{self.config.load_configs_input_path}' for load configs not found in input data. Cannot load any documents.")
                # Return empty output, respecting the schema
                return self.__class__.output_schema_cls(**{"output_metadata": output_meta})
            try:
                if isinstance(config_data, list):
                    # Parse list of configs
                    effective_load_configs = [LoadPathConfig.model_validate(item) for item in config_data]
                    self.info(f"Successfully parsed {len(effective_load_configs)} load configurations from list at '{self.config.load_configs_input_path}'.")
                elif isinstance(config_data, dict):
                    # Parse single config
                    effective_load_configs = [LoadPathConfig.model_validate(config_data)]
                    self.info(f"Successfully parsed 1 load configuration from object at '{self.config.load_configs_input_path}'.")
                else:
                    self.error(f"Data found at '{self.config.load_configs_input_path}' is not a valid list or object for load configurations. Type: {type(config_data)}. Cannot load documents.")
                    return self.__class__.output_schema_cls(**{"output_metadata": output_meta}) # Return empty output
            except ValidationError as e:
                 self.error(f"Validation error parsing load configuration(s) from input path '{self.config.load_configs_input_path}': {e}", exc_info=True)
                 return self.__class__.output_schema_cls(**{"output_metadata": output_meta}) # Return empty on parse error
            except Exception as e:
                 self.error(f"Unexpected error parsing load configuration(s) from input path '{self.config.load_configs_input_path}': {e}", exc_info=True)
                 return self.__class__.output_schema_cls(**{"output_metadata": output_meta}) # Return empty on unexpected error

        elif self.config.load_paths:
            self.info(f"Using statically defined load configurations from 'load_paths' ({len(self.config.load_paths)} configs).")
            effective_load_configs = self.config.load_paths
        else:
            # This case should be prevented by the validator, but good practice to handle
            self.error("Configuration error: No load paths or dynamic input path specified.")
            return self.__class__.output_schema_cls(**{"output_metadata": output_meta})

        # --- Process effective load configurations ---
        if not effective_load_configs:
             self.warning("No effective load configurations found after processing static/dynamic options. No documents will be loaded.")

        # async with get_async_db_as_manager() as db:
        output_fields_overlapping_count = {}
        for path_config in effective_load_configs:
            output_fields_overlapping_count[path_config.output_field_name] = output_fields_overlapping_count.get(path_config.output_field_name, 0) + 1
        
        for path_config in effective_load_configs:
            try:
                # --- Validation Check ---
                if not isinstance(path_config, LoadPathConfig):
                        self.error(f"Internal Error: Encountered non-LoadPathConfig object during processing: {type(path_config)}. Skipping.")
                        continue
                # --- End Validation Check ---

                resolved_path = _resolve_single_doc_path(
                    config=path_config.filename_config,
                    full_input_data=input_dict,
                    current_item_data=None,
                    item_index=None,
                    logger=self,
                )
                if not resolved_path:
                    self.error(f"Could not resolve document path for output field '{path_config.output_field_name}'. Skipping.")
                    continue
                namespace, docname = resolved_path

                is_shared = path_config.is_shared if path_config.is_shared is not None else self.config.global_is_shared
                is_system_entity = path_config.is_system_entity if path_config.is_system_entity is not None else self.config.global_is_system_entity
                version_cfg = path_config.version_config or self.config.global_version_config
                schema_opts = path_config.schema_options or self.config.global_schema_options

                doc_metadata = None
                try:
                    # Determine the on_behalf_of_user_id
                    on_behalf_id_str = path_config.on_behalf_of_user_id if path_config.on_behalf_of_user_id is not None else self.config.global_on_behalf_of_user_id
                    on_behalf_of_user_id_uuid: Optional[uuid.UUID] = None
                    if on_behalf_id_str:
                        try:
                            on_behalf_of_user_id_uuid = uuid.UUID(on_behalf_id_str)
                        except ValueError:
                            self.error(f"Invalid UUID format for on_behalf_of_user_id: '{on_behalf_id_str}'. Skipping document load.")
                            continue # Skip this path_config

                    # --- Superuser Check --- #
                    if on_behalf_of_user_id_uuid and not user.is_superuser:
                        self.error(f"User '{user.id}' is not a superuser and cannot use 'on_behalf_of_user_id'='{on_behalf_id_str}'. Skipping load for output field '{path_config.output_field_name}'.")
                        continue # Skip this path_config
                    # --- End Superuser Check --- #

                    doc_metadata = await customer_data_service.get_document_metadata(
                        org_id=org_id, namespace=namespace, docname=docname,
                        is_shared=is_shared, user=user, is_system_entity=is_system_entity,
                        on_behalf_of_user_id=on_behalf_of_user_id_uuid, # Pass the UUID
                        is_called_from_workflow=True
                    )
                except Exception as meta_err:
                    # Check if it's a 403 Forbidden, often due to superuser required for on_behalf_of
                    if hasattr(meta_err, 'status_code') and meta_err.status_code == 403:
                        self.error(f"Permission denied fetching metadata for '{namespace}/{docname}'. Check if superuser is required for 'on_behalf_of_user_id': {meta_err}")
                    else:
                        self.warning(f"Could not fetch metadata for '{namespace}/{docname}': {meta_err}. Assuming unversioned.")

                is_versioned_doc = doc_metadata.is_versioned if doc_metadata else False

                document_data = None
                loaded_schema = None
                # Determine on_behalf_of again for subsequent calls (could be refactored)
                on_behalf_id_str = path_config.on_behalf_of_user_id if path_config.on_behalf_of_user_id is not None else self.config.global_on_behalf_of_user_id
                on_behalf_of_user_id_uuid: Optional[uuid.UUID] = None
                if on_behalf_id_str:
                    try:
                        on_behalf_of_user_id_uuid = uuid.UUID(on_behalf_id_str)
                    except ValueError:
                        # Error already logged during metadata fetch
                        continue

                if is_versioned_doc:
                    try:
                        document_data = await customer_data_service.get_versioned_document(
                            org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                            user=user, version=version_cfg.version, is_system_entity=is_system_entity,
                            on_behalf_of_user_id=on_behalf_of_user_id_uuid, # Pass the UUID
                            is_called_from_workflow=True
                        )
                        if schema_opts.load_schema:
                            loaded_schema = await customer_data_service.get_versioned_document_schema(
                                org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                                user=user, is_system_entity=is_system_entity,
                                on_behalf_of_user_id=on_behalf_of_user_id_uuid, # Pass the UUID
                                is_called_from_workflow=True
                            )
                    except Exception as load_err:
                            self.error(f"Failed to load versioned document '{namespace}/{docname}': {load_err}", exc_info=True)
                            continue # Skip this document
                else:
                    try:
                        document_data = await customer_data_service.get_unversioned_document(
                            org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                            user=user, is_system_entity=is_system_entity,
                            on_behalf_of_user_id=on_behalf_of_user_id_uuid, # Pass the UUID
                            is_called_from_workflow=True
                        )
                        # Schema loading for unversioned (logic remains the same, user context passed)
                        if schema_opts.load_schema and (schema_opts.schema_template_name or schema_opts.schema_definition):
                            if schema_opts.schema_template_name:
                                try:
                                    # _get_schema_from_template doesn't directly take on_behalf_of,
                                    # but the `user` object context is important.
                                    async with get_async_db_as_manager() as db_session:
                                        loaded_schema = await customer_data_service._get_schema_from_template(
                                            db=db_session, template_name=schema_opts.schema_template_name,
                                            template_version=schema_opts.schema_template_version,
                                            org_id=org_id, user=user
                                        )
                                except Exception as schema_err:
                                        self.error(f"Failed to load schema template '{schema_opts.schema_template_name}' for '{namespace}/{docname}': {schema_err}")
                            elif schema_opts.schema_definition:
                                loaded_schema = schema_opts.schema_definition
                    except Exception as load_err:
                            self.error(f"Failed to load unversioned document '{namespace}/{docname}': {load_err}", exc_info=True)
                            continue # Skip this document

                if document_data is not None:
                    if output_fields_overlapping_count[path_config.output_field_name] == 1:
                        output_data[path_config.output_field_name] = document_data
                    else:
                        if path_config.output_field_name not in output_data:
                            output_data[path_config.output_field_name] = [document_data]
                        else:
                            output_data[path_config.output_field_name].append(document_data)
                    if loaded_schema:
                            # NOTE: while loading multiple objects to same output field name, its assumed that all schemas should be same!
                            # TODO: FIXME: validate this!
                            output_meta.setdefault(path_config.output_field_name, {})['schema'] = loaded_schema
                else:
                        self.warning(f"Document not found or access denied for '{namespace}/{docname}' (Output field: {path_config.output_field_name}).")

            except Exception as e:
                self.error(f"Failed to load document for output field '{path_config.output_field_name}': {e}", exc_info=True)

        # Create output instance using the class reference
        output_cls = self.__class__.output_schema_cls

        # Prepare data for instantiation: include explicitly defined fields and dynamic data fields
        # Combine explicitly defined fields (like metadata) with the dynamic data fields
        init_data = {
            "output_metadata": output_meta,
            **output_data  # Add the dynamically loaded data fields
        }

        # Hack for converting output data into correct list types from non-list if output schema is expecting list type
        for field_name, field_info in output_cls.model_fields.items():
            if field_name in init_data:
                if get_origin(field_info.annotation) is list:
                    if not isinstance(init_data[field_name], list):
                        init_data[field_name] = [init_data[field_name]]

        try:
            # Filter out any potential Pydantic keywords from dynamically added keys
            safe_init_data = {k: v for k, v in init_data.items() 
                              if not k.startswith('_')
                              }

            # Instantiate directly, relying on extra='ignore' (assumed on BaseSchema/DynamicSchema)
            output_instance = output_cls(**safe_init_data)

            # Track loaded fields (optional)
            if hasattr(output_instance, '_loaded_fields'):
                 output_instance.loaded_fields = list(output_data.keys())

        except ValidationError as ve:
            self.error(f"Output validation error: {ve}. Initializing with: {safe_init_data.keys()}")
            # Fallback to empty output, ensuring output_metadata is included if possible
            fallback_data = {"output_metadata": output_meta}
            return output_cls(**fallback_data) # Attempt instantiation with just metadata
        except Exception as e:
             self.error(f"Unexpected error during output instantiation: {e}", exc_info=True)
             fallback_data = {"output_metadata": output_meta}
             return output_cls(**fallback_data)

        self.info(f"Completed LoadCustomerDataNode processing, loaded {len(output_meta)} documents")
        return output_instance

# --- Store Customer Data Node ---

class TargetPathConfig(BaseNodeConfig):
    """Configuration for the target path where data will be stored."""
    filename_config: FilenameConfig = Field(
        ...,
        description="Configuration defining how to determine the document's namespace and docname."
    )

class VersioningInfo(BaseNodeConfig):
    """Configuration for how to handle versioning during storage."""
    is_versioned: bool = Field(
        True, description="Whether the target document path uses versioning."
    )
    operation: StoreOperation = Field(
        ..., description="The storage operation to perform (initialize, update, upsert, create_version, upsert_versioned)."
    )
    version: Optional[str] = Field(
        None, description="Version name to use for the operation (e.g., for updates, initialization, or new version creation)."
    )
    # Specific to CREATE_VERSION
    from_version: Optional[str] = Field(
         None, description="For 'create_version' operation, specify the version to branch from (defaults to active version)."
    )
    # Specific to UPDATE/UPSERT
    is_complete: Optional[bool] = Field(
         None, description="For 'update'/'upsert' on versioned docs, mark if the document state is complete after update."
    )


    @model_validator(mode='after')
    def check_operation_consistency(self) -> 'VersioningInfo':
        """Validate versioning settings based on operation type."""
        # --- Validations for Unversioned ---
        if not self.is_versioned:
            if self.operation not in [StoreOperation.UPSERT, StoreOperation.UPDATE]:
                raise ValueError(f"Operation '{self.operation.value}' is only valid for versioned documents when is_versioned=False. Use 'upsert' or 'update'.")
            # Force version to 'default' for unversioned updates/upserts for clarity
            if self.operation == StoreOperation.UPDATE and self.version is not None and self.version != "default":
                 self.version = "default"
            if self.operation == StoreOperation.UPSERT and self.version is not None and self.version != "default":
                 self.version = "default" # Although UPSERT doesn't use version in service, align config
            # Disallow versioned-specific fields
            if self.from_version is not None:
                 raise ValueError("'from_version' cannot be used when is_versioned=False.")
            # is_complete could potentially be used for unversioned if service supports, but keep it simple for now.
            # if self.is_complete is not None:
            #      raise ValueError("'is_complete' cannot be used when is_versioned=False.")

        # --- Validations for Versioned ---
        if self.is_versioned:
            if self.operation == StoreOperation.UPSERT:
                raise ValueError("Operation 'upsert' is only valid for unversioned documents (is_versioned=False). Use 'initialize', 'update', 'create_version', or 'upsert_versioned'.")
        if self.operation != StoreOperation.CREATE_VERSION and self.from_version is not None:
            raise ValueError("'from_version' is only applicable for 'create_version' operation.")
            # Allow is_complete for update, initialize, and upsert_versioned
            if self.operation not in [StoreOperation.UPDATE, StoreOperation.INITIALIZE, StoreOperation.UPSERT_VERSIONED] and self.is_complete is not None:
                 raise ValueError("'is_complete' is only applicable for 'update', 'initialize', or 'upsert_versioned' operations on versioned documents.")

        # General: Ensure a version is specified if needed by the operation (though None often implies 'active' for updates)
        # if self.is_versioned and self.operation in [StoreOperation.INITIALIZE, StoreOperation.UPDATE, StoreOperation.UPSERT_VERSIONED] and self.version is None:
        #     # Allow None for UPDATE/UPSERT_VERSIONED (means active), but maybe require for INITIALIZE?
        #     # Service defaults INITIALIZE to 'default' if None, so this is likely okay.
        #     pass

        return self


class StoreConfig(BaseNodeConfig):
    """Configuration for storing a single document or a list of documents."""
    input_field_path: str = Field(
        ...,
        description="Dot-notation path within the node's input data to find the document(s) (dict or list of dicts) to store."
    )
    target_path: TargetPathConfig = Field(
        ...,
        description="Configuration defining the target namespace and docname."
    )
    # Modifiers (use global defaults if None)
    is_shared: Optional[bool] = Field(None, description="Override global: Store as shared data.")
    is_system_entity: Optional[bool] = Field(None, description="Override global: Store as system data (superuser only).")
    # Versioning (use global defaults if None)
    versioning: Optional[VersioningInfo] = Field(None, description="Override global: Versioning behavior.")
    # Schema (use global defaults if None)
    schema_options: Optional[SchemaOptions] = Field(None, description="Override global: Schema association/validation.")
    # NEW FIELD: Optional user ID to act on behalf of
    on_behalf_of_user_id: Optional[str] = Field(
        None, description="User ID (as string) to act on behalf of (requires superuser privileges). Overrides global default."
    )
    # NEW FIELD: Control list processing
    process_list_items_separately: Optional[bool] = Field(
        None,
        description="If True and input data is a list, process each item separately using the target path config. If False, store the entire list as a single document."
    )
    # NEW FIELDS: Extra field configurations and UUID generation
    extra_fields: Optional[List[ExtraFieldConfig]] = Field(
        None,
        description="List of extra field configurations to add to the object(s) being stored. "
                   "Same fields are added to all objects when processing list items separately."
    )
    generate_uuid: Optional[bool] = Field(
        None,
        description="If True, generates and adds a UUID to each object being stored. "
                   "For dictionary objects, adds a 'uuid' key directly. "
                   "For non-dictionary objects, wraps them in a dict with 'uuid' and 'data' keys. "
                   "If _uuid_ is used in filename patterns, this generated UUID will be used."
    )
    create_only_fields: Optional[List[str]] = Field(
        None,
        description="List of fields in data which should be removed if the operation is an update rather than creation"
    )
    keep_create_fields_if_missing: Optional[bool] = Field(
        None,
        description="If True, keep create_only_fields in data if they don't exist in `existing object` during update. NOTE: this also effects any generated uuids and they are discarded if this is False and the operation is an update."
    )

class StoreCustomerDataConfig(BaseNodeConfig):
    """Configuration schema for the StoreCustomerDataNode."""
    store_configs: List[StoreConfig] = Field(
        None, # Changed from ... to None, making it optional
        min_length=1,
        description="List of configurations, each defining data to store and its target. Used if 'store_configs_input_path' is not provided."
    )
    # Dynamic loading from input data
    store_configs_input_path: Optional[str] = Field(
        None,
        description="Dot-notation path within the node\'s input data to find the store configuration(s). "\
                    "This can be a single JSON object matching StoreConfig structure, or a list of such objects. "\
                    "If provided, this overrides \'store_configs\'."
    )

    # Global defaults
    global_is_shared: bool = Field(False, description="Default value for \'is_shared\'.")
    global_is_system_entity: bool = Field(False, description="Default value for \'is_system_entity\'.")
    global_versioning: VersioningInfo = Field(
        default_factory=lambda: VersioningInfo(operation=StoreOperation.UPSERT, is_versioned=False), # Sensible default: upsert unversioned
        description="Default versioning configuration."
    )
    global_schema_options: SchemaOptions = Field(
        default_factory=SchemaOptions, description="Default schema handling options."
    )

    # NEW FIELD: Global default for on behalf of user ID
    global_on_behalf_of_user_id: Optional[str] = Field(
        None, description="Default User ID (as string) to act on behalf of (requires superuser privileges)."
    )
    # NEW FIELD: Global default for list processing
    global_process_list_items_separately: bool = Field(
        False,
        description="Default value for 'process_list_items_separately'."
    )
    # NEW FIELD: Global default for UUID generation
    global_generate_uuid: bool = Field(
        False,
        description="Default value for 'generate_uuid'."
    )
    # NEW FIELD: Global default for extra fields
    global_extra_fields: Optional[List[ExtraFieldConfig]] = Field(
        None,
        description="Default extra fields to add to all objects being stored."
    )
    # NEW FIELD: Global default for create_only_fields
    global_create_only_fields: Optional[List[str]] = Field(
        None,
        description="List of fields in data which should be removed if the operation is an update rather than creation"
    )
    # NEW FIELD: Global default for keep_create_fields_if_missing
    global_keep_create_fields_if_missing: Optional[bool] = Field(
        None,
        description="If True, keep create_only_fields in data if they don't exist in `existing object` during update. NOTE: this also effects any generated uuids and they are discarded if this is False and the operation is an update."
    )

    @model_validator(mode='after')
    def check_config_source(self) -> 'StoreCustomerDataConfig':
        """Ensure either store_configs or store_configs_input_path is provided, but not both."""
        if self.store_configs is None and self.store_configs_input_path is None:
            raise ValueError("Either \'store_configs\' or \'store_configs_input_path\' must be provided.")
        if self.store_configs is not None and self.store_configs_input_path is not None:
            raise ValueError("Provide either \'store_configs\' or \'store_configs_input_path\', not both.")
        # Ensure store_configs has at least one item if it\'s the chosen source
        if self.store_configs is not None and not self.store_configs:
             raise ValueError("\'store_configs\' must contain at least one configuration if provided.")
        return self

class StoreCustomerDataOutput(DynamicSchema):
    """
    Output schema for the StoreCustomerDataNode.

    Can include status or IDs of stored/updated documents, potentially
    organized by the input field path or target path used.
    (Currently returns the input data passthrough).
    """
    # TODO: Define a more structured output? E.g., results per store_config?
    # For now, just pass through input for simplicity, similar to IfElse.
    paths_processed: Union[List[List[Union[str, Dict[str, Any]]]], List[str]] = Field(default_factory=list, description="List of paths processed successfully.")
    passthrough_data: Dict[str, Any] = Field(..., description="The original input data passed through.")


class StoreCustomerDataNode(BaseDynamicNode):
    """
    Node to store or update customer data documents (versioned or unversioned) in MongoDB.

    Takes data from the input stream (specified by a path) and writes it to MongoDB
    based on target path configurations (static or derived).
    Supports different storage operations (initialize, update, upsert, create_version, upsert_versioned)
    and handles schema association/validation.
    Manages shared, user-specific, and system-level documents based on user permissions.
    """
    node_name: ClassVar[str] = "store_customer_data"
    node_version: ClassVar[str] = "0.1.6" # Updated passthrough_data behavior
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.PRODUCTION
    # Ineriting input / output dynamic schemas from base class!
    # input_schema_cls: Type[DynamicSchema] = DynamicSchema
    output_schema_cls: ClassVar[Type[StoreCustomerDataOutput]] = StoreCustomerDataOutput
    config_schema_cls: ClassVar[Type[StoreCustomerDataConfig]] = StoreCustomerDataConfig
    config: StoreCustomerDataConfig

    async def _store_single_document(
        self,
        doc_data: Any, # Can be dict or primitive
        store_cfg: StoreConfig,
        app_context: Dict[str, Any],
        ext_context,  # : ExternalContextManager
        full_input_dict: Dict[str, Any],
        item_index: Optional[int] = None
    ) -> Tuple[bool, Optional[Tuple[str, str, str]], Optional[Any]]:
        """
        Helper to store a single document based on configuration.

        Handles various storage operations including initialization, updates,
        upserts (for unversioned), version creation, and versioned upserts.
        Modifies `doc_data` by adding UUIDs or extra fields if configured.
        
        Returns:
            Tuple containing:
                - success flag (bool)
                - Optional tuple of (namespace, docname, operation_details) for successful operations
                - Optional modified document data that was stored (Any)
        """
        user: User = app_context["user"]
        run_job: WorkflowRunJobCreate = app_context["workflow_run_job"]
        org_id = run_job.owner_org_id
        customer_data_service: CustomerDataService = ext_context.customer_data_service
        
        # Potentially modified document data that will be stored
        processed_doc_data = doc_data 

        # Generate UUID if configured
        generated_uuid = None
        should_generate_uuid = store_cfg.generate_uuid if store_cfg.generate_uuid is not None else self.config.global_generate_uuid
        create_only_fields = store_cfg.create_only_fields if store_cfg.create_only_fields is not None else self.config.global_create_only_fields
        keep_create_fields_if_missing = store_cfg.keep_create_fields_if_missing if store_cfg.keep_create_fields_if_missing is not None else self.config.global_keep_create_fields_if_missing
        create_only_fields = create_only_fields or []
        keep_create_fields_if_missing = True if keep_create_fields_if_missing is None else keep_create_fields_if_missing
        
        if should_generate_uuid:
            generated_uuid = str(uuid.uuid4())
            if "uuid" not in create_only_fields:
                create_only_fields.append("uuid")
            
            # Apply UUID to document data
            if isinstance(processed_doc_data, dict):
                # Create a copy before modification to avoid altering original item_data if it's a dict from input
                processed_doc_data = dict(processed_doc_data) 
                processed_doc_data["uuid"] = generated_uuid
            else:
                # Wrap non-dict objects, creating a new dict
                processed_doc_data = {
                    "uuid": generated_uuid,
                    "data": processed_doc_data # Original primitive data is nested
                }
                
        # Apply extra fields if configured
        # This will modify processed_doc_data if it's a dictionary
        effective_extra_fields = store_cfg.extra_fields or self.config.global_extra_fields
        if effective_extra_fields:
            # _add_extra_fields modifies dicts in-place or returns non-dicts as is.
            # If processed_doc_data is a dict (either original or wrapper), it's modified.
            processed_doc_data = _add_extra_fields(processed_doc_data, full_input_dict, effective_extra_fields, self)

        resolved_path = _resolve_single_doc_path(
            config=store_cfg.target_path.filename_config,
            full_input_data=full_input_dict,
            current_item_data=processed_doc_data, # Use the (potentially modified) data for path resolution
            item_index=item_index,
            generated_uuid=generated_uuid,  # Pass the generated UUID to use in filename pattern
            logger=self,
        )
        if not resolved_path:
            self.error(f"Could not resolve target path for item from input '{store_cfg.input_field_path}' (index: {item_index}). Skipping store.")
            return False, None, None # Return None for modified_doc_data on failure
        namespace, docname = resolved_path

        is_shared = store_cfg.is_shared if store_cfg.is_shared is not None else self.config.global_is_shared
        is_system_entity = store_cfg.is_system_entity if store_cfg.is_system_entity is not None else self.config.global_is_system_entity
        versioning = store_cfg.versioning or self.config.global_versioning
        schema_opts = store_cfg.schema_options or self.config.global_schema_options

        # --- Determine and Validate on_behalf_of_user_id --- #
        on_behalf_id_str = store_cfg.on_behalf_of_user_id if store_cfg.on_behalf_of_user_id is not None else self.config.global_on_behalf_of_user_id
        on_behalf_of_user_id_uuid: Optional[uuid.UUID] = None
        if on_behalf_id_str:
            try:
                on_behalf_of_user_id_uuid = uuid.UUID(on_behalf_id_str)
            except ValueError:
                self.error(f"Invalid UUID format for on_behalf_of_user_id: '{on_behalf_id_str}' for doc '{namespace}/{docname}'. Skipping store.")
                return False, None, None 
        # --- --- ---

        # --- Superuser Check --- #
        if on_behalf_of_user_id_uuid and not user.is_superuser:
            self.error(f"User '{user.id}' is not a superuser and cannot use 'on_behalf_of_user_id'='{on_behalf_id_str}'. Skipping store for output field '{namespace}/{docname}'.")
            return False, None, None 
        # --- End Superuser Check --- #

        # async with get_async_db_as_manager() as db:
        try:
            operation_str = "" # Detailed string describing the successful operation
            success_flag = False # Flag indicating overall success of the chosen operation

            if not versioning.is_versioned:
                # --- Handle Unversioned ---
                if versioning.operation == StoreOperation.UPSERT:
                    async with get_async_db_as_manager() as db_session:
                        _id, created = await customer_data_service.create_or_update_unversioned_document(
                            db=db_session, org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                            user=user, data=processed_doc_data, schema_template_name=schema_opts.schema_template_name,
                            schema_template_version=schema_opts.schema_template_version,
                            schema_definition=schema_opts.schema_definition,
                            is_system_entity=is_system_entity,
                            on_behalf_of_user_id=on_behalf_of_user_id_uuid, # Pass UUID
                            is_called_from_workflow=True,
                            create_only_fields=create_only_fields,
                            keep_create_fields_if_missing=keep_create_fields_if_missing,
                        )
                    success_flag = True 
                    operation_str = f"upsert_unversioned (created: {created})"
                    self.info(f"Upserted unversioned doc '{namespace}/{docname}'. Created: {created}")
                elif versioning.operation == StoreOperation.UPDATE:
                    # NOTE: create_or_update_unversioned_document currently behaves like UPSERT.
                    # To enforce UPDATE (fail if not exists), the service method would need modification.
                    # For now, we call it and log a warning if it creates the document.
                    async with get_async_db_as_manager() as db_session:
                        _id, created = await customer_data_service.create_or_update_unversioned_document(
                            db=db_session, org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                            user=user, data=processed_doc_data, schema_template_name=schema_opts.schema_template_name,
                            schema_template_version=schema_opts.schema_template_version,
                            schema_definition=schema_opts.schema_definition,
                            is_system_entity=is_system_entity,
                            on_behalf_of_user_id=on_behalf_of_user_id_uuid, # Pass UUID
                            is_called_from_workflow=True,
                            create_only_fields=create_only_fields,
                            keep_create_fields_if_missing=keep_create_fields_if_missing,
                        )
                    success_flag = True 
                    operation_str = f"update_unversioned (created: {created})"
                    if created:
                        self.warning(f"Performed 'update' on unversioned doc '{namespace}/{docname}', but it resulted in creation (upsert behavior). Document did not previously exist.")
                    else:
                        self.info(f"Updated unversioned doc '{namespace}/{docname}'.")
                else:
                    self.error(f"Invalid operation '{versioning.operation.value}' for unversioned document '{namespace}/{docname}'.")
                    return False, None, None

            else:
                # --- Handle Versioned ---
                if versioning.operation == StoreOperation.INITIALIZE:
                    async with get_async_db_as_manager() as db_session:
                        success = await customer_data_service.initialize_versioned_document(
                            db=db_session, org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                            user=user, initial_version=versioning.version or "default", 
                            schema_template_name=schema_opts.schema_template_name,
                            schema_template_version=schema_opts.schema_template_version,
                            schema_definition=schema_opts.schema_definition,
                            initial_data=processed_doc_data, is_complete=versioning.is_complete or False,
                            is_system_entity=is_system_entity,
                            on_behalf_of_user_id=on_behalf_of_user_id_uuid, 
                            is_called_from_workflow=True
                        )
                    if success:
                        success_flag = True
                        operation_str = f"initialize_versioned_{versioning.version or 'default'}"
                        self.info(f"Initialized versioned doc '{namespace}/{docname}' with version '{versioning.version or 'default'}'.")
                    else:
                        self.error(f"Failed to initialize versioned doc '{namespace}/{docname}'. Check permissions (e.g., superuser for on_behalf_of) or if it already exists.")
                        return False, None, None 

                elif versioning.operation == StoreOperation.UPDATE:
                    # Use None for version if not specified, service interprets as 'active'
                    target_version = versioning.version
                    async with get_async_db_as_manager() as db_session:
                        success = await customer_data_service.update_versioned_document(
                            db=db_session, org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                            user=user, data=processed_doc_data, version=target_version,
                            is_complete=versioning.is_complete,
                            schema_template_name=schema_opts.schema_template_name,
                            schema_template_version=schema_opts.schema_template_version,
                            schema_definition=schema_opts.schema_definition,
                            is_system_entity=is_system_entity,
                            on_behalf_of_user_id=on_behalf_of_user_id_uuid, 
                            is_called_from_workflow=True,
                            create_only_fields=create_only_fields,
                            keep_create_fields_if_missing=keep_create_fields_if_missing,
                        )
                    if success:
                        success_flag = True
                        operation_str = f"update_versioned_{target_version or 'active'}"
                        self.info(f"Updated versioned doc '{namespace}/{docname}' (version: {target_version or 'active'}).")
                    else:
                        self.error(f"Failed to update versioned doc '{namespace}/{docname}' (version: {target_version or 'active'}). Check permissions, if doc/version exists, or if superuser is required for on_behalf_of.")
                        return False, None, None 

                elif versioning.operation == StoreOperation.UPSERT_VERSIONED:
                    self.info(f"Attempting upsert_versioned for doc '{namespace}/{docname}' (target version: {versioning.version or 'active/default'}).")
                    try:
                        async with get_async_db_as_manager() as db_session:
                            op_performed, doc_identifier_dict = await customer_data_service.upsert_versioned_document(
                                db=db_session,
                                org_id=org_id,
                                namespace=namespace,
                                docname=docname,
                                is_shared=is_shared,
                                user=user,
                                data=processed_doc_data,
                                version=versioning.version, 
                                from_version=versioning.from_version, 
                                is_complete=versioning.is_complete,
                                schema_template_name=schema_opts.schema_template_name,
                                schema_template_version=schema_opts.schema_template_version,
                                schema_definition=schema_opts.schema_definition,
                                on_behalf_of_user_id=on_behalf_of_user_id_uuid, 
                                is_system_entity=is_system_entity,
                                is_called_from_workflow=True,
                                create_only_fields=create_only_fields,
                                keep_create_fields_if_missing=keep_create_fields_if_missing,
                            )
                        success_flag = True
                        operation_str = op_performed 
                        self.info(f"Upsert_versioned operation successful for doc '{namespace}/{docname}'. Action: {operation_str}")
                    except Exception as upsert_err:
                        self.error(f"Upsert_versioned operation failed for doc '{namespace}/{docname}': {upsert_err}", exc_info=True)
                        return False, None, None 

                elif versioning.operation == StoreOperation.CREATE_VERSION:
                    new_version_name = versioning.version
                    if not new_version_name:
                        new_version_name = f"version_{uuid.uuid4().hex[:8]}"
                        self.info(f"Generated new version name for CREATE_VERSION: {new_version_name}")

                    create_success = await customer_data_service.create_versioned_document_version(
                        org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                        user=user, new_version=new_version_name, from_version=versioning.from_version,
                        is_system_entity=is_system_entity,
                        on_behalf_of_user_id=on_behalf_of_user_id_uuid, 
                        is_called_from_workflow=True
                    )
                    if create_success:
                        async with get_async_db_as_manager() as db_session:
                            update_success = await customer_data_service.update_versioned_document(
                                db=db_session, org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                                user=user, data=processed_doc_data, version=new_version_name, 
                                is_complete=versioning.is_complete, 
                                schema_template_name=schema_opts.schema_template_name,
                                schema_template_version=schema_opts.schema_template_version,
                                schema_definition=schema_opts.schema_definition,
                                is_system_entity=is_system_entity,
                                on_behalf_of_user_id=on_behalf_of_user_id_uuid, 
                                is_called_from_workflow=True,
                                create_only_fields=create_only_fields,
                                keep_create_fields_if_missing=keep_create_fields_if_missing,
                            )
                        if update_success:
                            success_flag = True
                            operation_str = f"create_version_{new_version_name}"
                            self.info(f"Created and updated new version '{new_version_name}' for doc '{namespace}/{docname}'.")
                        else:
                            self.error(f"Created new version '{new_version_name}' for doc '{namespace}/{docname}', but failed to update it with data. The version entry exists but is empty/incomplete. Check permissions.")
                            return False, None, None 
                    else:
                        self.error(f"Failed to create new version entry '{new_version_name}' for doc '{namespace}/{docname}'. Does the document exist? Does the 'from_version' exist? Check permissions (e.g., superuser for on_behalf_of).")
                        return False, None, None 
                else:
                    self.error(f"Unsupported operation '{versioning.operation.value}' for versioned document.")
                    return False, None, None
            
            if success_flag:
                operation_params = {
                    "org_id": org_id,
                    "is_shared": is_shared,
                    "on_behalf_of_user_id": on_behalf_of_user_id_uuid,
                    "is_system_entity": is_system_entity,
                    "namespace": namespace,
                    "docname": docname,
                    "version_info": {
                        "is_versioned": versioning.is_versioned,
                        "version": versioning.version,
                        "is_active_version": versioning.operation in [StoreOperation.UPSERT, StoreOperation.INITIALIZE],
                        "is_complete": versioning.is_complete,
                    },
                    # "schema_opts": {
                    #     "schema_template_name": schema_opts.schema_template_name,
                    #     "schema_template_version": schema_opts.schema_template_version,
                    #     "schema_definition": schema_opts.schema_definition,
                    # },
                }
                return True, (namespace, docname, operation_str, operation_params), processed_doc_data
            else:
                # This path should ideally not be reached if specific failures return (False, None, None)
                self.error(f"Reached end of storage logic without success for '{namespace}/{docname}' operation '{versioning.operation.value if versioning else 'unknown'}': {e}"
                                    f" (Permission denied - check superuser privileges if using on_behalf_of_user_id)"
                                    if hasattr(e, 'status_code') and e.status_code == 403 else
                                    f"This indicates an unexpected control flow issue or prior logged failure.")
                return False, None, None

        except Exception as e:
            error_msg = f"Error storing document '{namespace}/{docname}' during operation '{versioning.operation.value if versioning else 'unknown'}': {e}"
            if hasattr(e, 'status_code') and e.status_code == 403:
                error_msg += " (Permission denied - check superuser privileges if using on_behalf_of_user_id)"
            self.error(error_msg, exc_info=True)
            return False, None, None

    async def process(
        self,
        input_data: Union[DynamicSchema, Dict[str, Any]],
        runtime_config: Optional[Dict[str, Any]] = None, 
        *args: Any,
        **kwargs: Any
    ) -> StoreCustomerDataOutput:
        """
        Stores or updates customer data based on the node's configuration.
        The `passthrough_data` in the output will reflect the input data after
        modifications (like UUID generation, extra fields) have been applied to
        the items that were stored.

        Args:
            input_data: The input data containing the document(s) to store.
            runtime_config: The runtime configuration containing execution context.
            *args: Additional positional arguments (unused).
            **kwargs: Additional keyword arguments (unused).

        Returns:
            StoreCustomerDataOutput: Includes the potentially modified input data in `passthrough_data`
            and a list of successfully processed paths with their operations.
        """
        # Retrieve context from runtime_config
        input_dict = input_data if isinstance(input_data, dict) else input_data.model_dump(mode='json')
        passthrough_input = input_dict
        input_dict = copy.deepcopy(input_dict)
        
        if not runtime_config:
            self.error("Missing runtime_config.")
            # Instantiate output using class reference, even on failure
            return self.__class__.output_schema_cls(passthrough_data=passthrough_input, paths_processed=[])

        runtime_config = runtime_config.get("configurable")
        app_context: Optional[Dict[str, Any]] = runtime_config.get(APPLICATION_CONTEXT_KEY)
        ext_context = runtime_config.get(EXTERNAL_CONTEXT_MANAGER_KEY)  # : Optional[ExternalContextManager]

        if not app_context or not ext_context:
            self.error(f"Missing required keys in runtime_config: {APPLICATION_CONTEXT_KEY} or {EXTERNAL_CONTEXT_MANAGER_KEY}")
            return self.__class__.output_schema_cls(passthrough_data=passthrough_input, paths_processed=[])

        # passthrough_input = input_dict  # copy.deepcopy(input_dict) # Keep original for output

        # Use List[List[str]] to match existing output schema more easily
        paths_processed: List[List[Union[str, Dict[str, Any]]]] = [] # List of [namespace, docname, operation_details] lists
        any_failures = False # Track if any individual store operation failed
        
        effective_store_configs: List[StoreConfig] = []

        # --- Determine effective store configurations ---
        if self.config.store_configs_input_path:
            self.info(f"Attempting to load store configurations dynamically from input path: {self.config.store_configs_input_path}")
            config_data, found = _get_nested_obj(input_dict, self.config.store_configs_input_path)
            if not found:
                self.error(f"Input path '{self.config.store_configs_input_path}' for store configs not found in input data. Cannot store any documents.")
                any_failures = True # Mark failure but continue (maybe other static configs exist? No, validator prevents this)
                # Need to decide whether to completely fail or just skip this dynamic part.
                # For consistency with Load, let's return early.
                return self.__class__.output_schema_cls(passthrough_data=passthrough_input, paths_processed=[])
            try:
                if isinstance(config_data, list):
                    # Parse list of configs
                    effective_store_configs = [StoreConfig.model_validate(item) for item in config_data]
                    self.info(f"Successfully parsed {len(effective_store_configs)} store configurations from list at '{self.config.store_configs_input_path}'.")
                elif isinstance(config_data, dict):
                    # Parse single config
                    effective_store_configs = [StoreConfig.model_validate(config_data)]
                    self.info(f"Successfully parsed 1 store configuration from object at '{self.config.store_configs_input_path}'.")
                else:
                    self.error(f"Data found at '{self.config.store_configs_input_path}' is not a valid list or object for store configurations. Type: {type(config_data)}. Cannot store documents.")
                    return self.__class__.output_schema_cls(passthrough_data=passthrough_input, paths_processed=[])
            except ValidationError as e:
                 self.error(f"Validation error parsing store configuration(s) from input path '{self.config.store_configs_input_path}': {e}", exc_info=True)
                 return self.__class__.output_schema_cls(passthrough_data=passthrough_input, paths_processed=[])
            except Exception as e:
                 self.error(f"Unexpected error parsing store configuration(s) from input path '{self.config.store_configs_input_path}': {e}", exc_info=True)
                 return self.__class__.output_schema_cls(passthrough_data=passthrough_input, paths_processed=[])

        elif self.config.store_configs:
            self.info(f"Using statically defined store configurations from 'store_configs' ({len(self.config.store_configs)} configs).")
            effective_store_configs = self.config.store_configs
        else:
            # This case should be prevented by the validator
            self.error("Configuration error: No store configs or dynamic input path specified.")
            return self.__class__.output_schema_cls(passthrough_data=passthrough_input, paths_processed=[])

        # --- Process effective store configurations ---
        if not effective_store_configs:
             self.warning("No effective store configurations found after processing static/dynamic options. No documents will be stored.")

        # Iterate over the determined configurations
        for store_cfg in effective_store_configs:
            # --- Validation Check ---
            if not isinstance(store_cfg, StoreConfig):
                self.error(f"Internal Error: Encountered non-StoreConfig object during processing: {type(store_cfg)}. Skipping.")
                continue
            # --- End Validation Check ---

            data_to_store, found = _get_nested_obj(input_dict, store_cfg.input_field_path)

            if not found:
                self.warning(f"Input field '{store_cfg.input_field_path}' not found. Skipping store configuration.")
                any_failures = True
                continue

            items_to_process: List[Tuple[Optional[int], Dict[str, Any]]] = []

            process_list_items_separately = store_cfg.process_list_items_separately if store_cfg.process_list_items_separately is not None else self.config.global_process_list_items_separately

            if isinstance(data_to_store, list) and process_list_items_separately:
                for item_index, item_data in enumerate(data_to_store):
                    # if isinstance(item_data, dict):
                    items_to_process.append((item_index, item_data))
                    # else:
                    #     self.warning(f"Item at index {item_index} in '{store_cfg.input_field_path}' is not a dictionary. Skipping.")
                    #     any_failures = True
            else:  # if isinstance(data_to_store, dict):
                items_to_process.append((None, data_to_store))
            # else:
            #     self.warning(f"Data at '{store_cfg.input_field_path}' is not a dictionary or list of dictionaries. Skipping.")
            #     any_failures = True
            #     continue # Skip to next store_cfg

            # Process the identified items
            for item_index, item_data in items_to_process:
                # Pass contexts to helper
                success, path_info, final_doc_data_stored = await self._store_single_document(
                    item_data, store_cfg, app_context, ext_context, input_dict, item_index
                )
                if success and path_info:
                    # path_info is (namespace, docname, operation_details)
                    paths_processed.append(list(path_info))
                    if final_doc_data_stored is not None:
                        # Determine the path in passthrough_input to update
                        path_to_update_in_passthrough: str
                        if item_index is not None: # Item was part of a list processed separately
                            path_to_update_in_passthrough = f"{store_cfg.input_field_path}.{item_index}"
                        else: # Single item or a list stored as a whole document
                            path_to_update_in_passthrough = store_cfg.input_field_path
                        
                        # Update the passthrough_input with the (potentially) modified document data
                        if not _set_nested_obj(passthrough_input, path_to_update_in_passthrough, final_doc_data_stored, logger=self):
                            self.warning(f"Failed to update passthrough_data at path '{path_to_update_in_passthrough}'. "
                                         f"This might occur if the input structure changed unexpectedly or path was invalid.")
                elif not success:
                    # Log implicitly handled by _store_single_document
                    any_failures = True # Mark that at least one operation failed


        if any_failures:
            #  self.error("One or more documents failed to store or were skipped.")
             raise Exception("One or more documents failed to store or were skipped.")

        # Instantiate output using class reference
        output_cls = self.__class__.output_schema_cls
        # Populate the defined fields (passthrough_data and paths_processed)
        output_instance = output_cls(
            passthrough_data=passthrough_input,
            paths_processed=paths_processed # Pass the list of [ns, dn, op] lists
        )

        return output_instance


if __name__ == "__main__":
    workflow_inputs: Dict[str, Any] = {
        "documents_to_process": [
            {
                "filename_config": {
                    "static_namespace": "test",
                    "static_docname": "test",
                },
                "output_field": "loaded_documents",
            },
            {
                "filename_config": {
                    "static_namespace": "test",
                    "static_docname": "test",
                },
                "output_field": "loaded_documents",
            }
        ]
    }
    load_path_configs = [LoadPathConfig(**w) for w in workflow_inputs["documents_to_process"]]
    node = LoadCustomerDataNode(config=LoadCustomerDataConfig(load_paths=load_path_configs), node_id="test_node")
    # node.run(input_data=None, runtime_config=None)
