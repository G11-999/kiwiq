# services/workflow_service/registry/nodes/db/customer_data.py
"""
Nodes for interacting with customer data stored in MongoDB via CustomerDataService.

Provides nodes for loading and storing both versioned and unversioned documents,
respecting organization, user, shared, and system data access patterns.
"""

import copy
import traceback
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Type, ClassVar, Tuple, Set
import logging # Added logging

from pydantic import Field, model_validator, BaseModel, ValidationError

# Internal dependencies
from kiwi_app.workflow_app.constants import LaunchStatus
from kiwi_app.auth.models import User
from kiwi_app.workflow_app.schemas import WorkflowRunJobCreate # For application context typing
from kiwi_app.workflow_app.service_customer_data import CustomerDataService
# This causes circular imports!
# from workflow_service.services.external_context_manager import ExternalContextManager
from db.session import get_async_db_as_manager # For database access within nodes if needed directly (unlikely)
from workflow_service.config.constants import (
    APPLICATION_CONTEXT_KEY,
    EXTERNAL_CONTEXT_MANAGER_KEY
)

# Base node/schema types
from workflow_service.registry.schemas.base import BaseSchema
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema, BaseDynamicNode

# Setup logger
log = logging.getLogger(__name__)

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

# --- New Filename Configuration Schema and Helper ---

class FilenameConfig(BaseSchema):
    """
    Configuration for determining the namespace and docname for a customer data operation.

    Supports static values, dynamic retrieval from input fields, or pattern-based generation.
    """
    # Static Definition
    static_namespace: Optional[str] = Field(
        None, description="A fixed namespace value."
    )
    static_docname: Optional[str] = Field(
        None, description="A fixed document name value."
    )

    # Dynamic Retrieval from Input Data
    input_namespace_field: Optional[str] = Field(
        None, description="Dot-notation path in the input data to retrieve the namespace value."
    )
    input_docname_field: Optional[str] = Field(
        None, description="Dot-notation path in the input data to retrieve the docname value."
    )

    # Pattern-Based Generation (using fields from the item being processed)
    namespace_pattern: Optional[str] = Field(
        None, description="f-string like template to generate the namespace (e.g., 'user_{item[user_id]}'). Uses 'item' and 'index' context."
    )
    docname_pattern: Optional[str] = Field(
        None, description="f-string like template to generate the docname (e.g., 'order_{item[order_id]}_{index}'). Uses 'item' and 'index' context."
    )

    @model_validator(mode='after')
    def validate_config(self) -> 'FilenameConfig':
        """Ensures a valid combination of static, input, or pattern fields is provided for namespace and docname."""
        # Namespace validation
        ns_sources = sum(1 for source in [self.static_namespace, self.input_namespace_field, self.namespace_pattern] if source is not None)
        if ns_sources > 1:
            raise ValueError("Provide only one of static_namespace, input_namespace_field, or namespace_pattern.")
        if ns_sources == 0:
            raise ValueError("One of static_namespace, input_namespace_field, or namespace_pattern must be provided.")
        if self.namespace_pattern and not self.input_namespace_field:
             log.debug("namespace_pattern is set, but input_namespace_field is not. Pattern will use the 'item' context directly.")
             # This is allowed, pattern will use the whole item.

        # Docname validation
        dn_sources = sum(1 for source in [self.static_docname, self.input_docname_field, self.docname_pattern] if source is not None)
        if dn_sources > 1:
            raise ValueError("Provide only one of static_docname, input_docname_field, or docname_pattern.")
        if dn_sources == 0:
            raise ValueError("One of static_docname, input_docname_field, or docname_pattern must be provided.")
        if self.docname_pattern and not self.input_docname_field:
             log.debug("docname_pattern is set, but input_docname_field is not. Pattern will use the 'item' context directly.")
             # This is allowed.

        # Pattern validation (basic check for now)
        # TODO: Add more robust pattern validation if needed (e.g., check for valid keys)
        if self.namespace_pattern and ('{' not in self.namespace_pattern or '}' not in self.namespace_pattern):
             log.warning(f"namespace_pattern '{self.namespace_pattern}' doesn't look like a valid pattern.")
        if self.docname_pattern and ('{' not in self.docname_pattern or '}' not in self.docname_pattern):
             log.warning(f"docname_pattern '{self.docname_pattern}' doesn't look like a valid pattern.")

        return self

def _resolve_single_doc_path(
    config: FilenameConfig,
    full_input_data: Dict[str, Any],
    current_item_data: Optional[Dict[str, Any]] = None,
    item_index: Optional[int] = None
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

    Returns:
        A tuple (namespace, docname) or None if resolution fails.
    """
    resolved_namespace: Optional[str] = None
    resolved_docname: Optional[str] = None
    context_data = current_item_data if current_item_data is not None else full_input_data

    # --- Resolve Namespace ---
    if config.static_namespace is not None:
        resolved_namespace = config.static_namespace
    elif config.input_namespace_field:
        # Try finding the field within the current item first, fallback to full input
        ns_val, found = _get_nested_obj(context_data, config.input_namespace_field)
        if not found and current_item_data is not None: # Fallback to full input if item exists
            ns_val, found = _get_nested_obj(full_input_data, config.input_namespace_field)

        if found and isinstance(ns_val, str):
            resolved_namespace = ns_val
        else:
            log.warning(f"Namespace field '{config.input_namespace_field}' not found or not a string.")
            return None
    elif config.namespace_pattern:
        if current_item_data is None:
            log.error("Cannot evaluate namespace_pattern: 'current_item_data' is missing.")
            return None
        try:
            # Provide 'item' and 'index' context for formatting
            pattern_context = {'item': current_item_data, 'index': item_index}
            resolved_namespace = config.namespace_pattern.format(**pattern_context)
        except KeyError as e:
            log.error(f"Error formatting namespace_pattern '{config.namespace_pattern}': Key {e} not found in item data.")
            return None
        except Exception as e:
            log.error(f"Error formatting namespace_pattern '{config.namespace_pattern}': {e}")
            return None
    else:
         # Should be caught by validator
         log.error("Invalid FilenameConfig state for namespace.")
         return None

    # --- Resolve Docname ---
    if config.static_docname is not None:
        resolved_docname = config.static_docname
    elif config.input_docname_field:
        # Try finding the field within the current item first, fallback to full input
        dn_val, found = _get_nested_obj(context_data, config.input_docname_field)
        if not found and current_item_data is not None: # Fallback to full input if item exists
             dn_val, found = _get_nested_obj(full_input_data, config.input_docname_field)

        if found and isinstance(dn_val, str):
            resolved_docname = dn_val
        else:
            log.warning(f"Docname field '{config.input_docname_field}' not found or not a string.")
            return None
    elif config.docname_pattern:
        if current_item_data is None:
            log.error("Cannot evaluate docname_pattern: 'current_item_data' is missing.")
            return None
        try:
            # Provide 'item' and 'index' context for formatting
            pattern_context = {'item': current_item_data, 'index': item_index}
            resolved_docname = config.docname_pattern.format(**pattern_context)
        except KeyError as e:
            log.error(f"Error formatting docname_pattern '{config.docname_pattern}': Key {e} not found in item data.")
            return None
        except Exception as e:
            log.error(f"Error formatting docname_pattern '{config.docname_pattern}': {e}")
            return None
    else:
         # Should be caught by validator
         log.error("Invalid FilenameConfig state for docname.")
         return None

    # Final check
    if resolved_namespace is not None and resolved_docname is not None:
        return resolved_namespace, resolved_docname
    else:
        log.error("Failed to resolve namespace or docname.")
        return None

# --- Enums ---

class StoreOperation(str, Enum):
    """Defines the operation to perform when storing data."""
    INITIALIZE = "initialize" # Initialize a new versioned document (fails if exists)
    UPDATE = "update"         # Update an existing document (versioned or unversioned, fails if not exists)
    UPSERT = "upsert"         # Create or update an unversioned document
    CREATE_VERSION = "create_version" # Create a new version for an existing versioned document

# --- Common Schemas ---

class VersionConfig(BaseSchema):
    """Configuration for specifying a document version."""
    version: str = Field(
        "default",
        description="The specific version name to load or store (e.g., 'default', 'v1.2')."
    )

class SchemaOptions(BaseSchema):
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

# --- Load Customer Data Node ---

class LoadPathConfig(BaseSchema):
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

    @model_validator(mode='after')
    def validate_output_field_name(self) -> 'LoadPathConfig':
        """Ensure output_field_name doesn't start with underscore to avoid conflicts with Pydantic reserved fields."""
        if self.output_field_name.startswith('_'):
            raise ValueError(f"output_field_name '{self.output_field_name}' cannot start with underscore (_) as it may conflict with Pydantic reserved fields.")
        return self

class LoadCustomerDataConfig(BaseSchema):
    """Configuration schema for the LoadCustomerDataNode."""
    load_paths: List[LoadPathConfig] = Field(
        ...,
        min_length=1,
        description="List of configurations, each defining a document or pattern to load."
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
    node_version: ClassVar[str] = "0.1.3" # Version bump for output instantiation change
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.PRODUCTION
    input_schema_cls: Type[DynamicSchema] = DynamicSchema
    output_schema_cls: Type[LoadCustomerDataOutput] = LoadCustomerDataOutput
    config_schema_cls: Type[LoadCustomerDataConfig] = LoadCustomerDataConfig
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
            self.logger.error("Missing runtime_config.")
            return self.__class__.output_schema_cls(__root__={}, output_metadata={})
        app_context: Optional[Dict[str, Any]] = runtime_config.get(APPLICATION_CONTEXT_KEY)
        ext_context = runtime_config.get(EXTERNAL_CONTEXT_MANAGER_KEY)  # : Optional[ExternalContextManager]
        if not app_context or not ext_context:
            self.logger.error(f"Missing required keys in runtime_config: {APPLICATION_CONTEXT_KEY} or {EXTERNAL_CONTEXT_MANAGER_KEY}")
            return self.__class__.output_schema_cls(__root__={}, output_metadata={})
        user: Optional[User] = app_context.get("user")
        run_job: Optional[WorkflowRunJobCreate] = app_context.get("workflow_run_job")
        if not user or not run_job:
            self.logger.error("Missing 'user' or 'workflow_run_job' in application_context.")
            return self.__class__.output_schema_cls(__root__={}, output_metadata={})
        org_id = run_job.owner_org_id
        customer_data_service: CustomerDataService = ext_context.customer_data_service
        input_dict = input_data if isinstance(input_data, dict) else input_data.model_dump(mode='json')

        output_data: Dict[str, Any] = {}
        output_meta: Dict[str, Dict[str, Any]] = {}

        async with get_async_db_as_manager() as db:
            for path_config in self.config.load_paths:
                try:
                    resolved_path = _resolve_single_doc_path(
                        config=path_config.filename_config,
                        full_input_data=input_dict,
                        current_item_data=None,
                        item_index=None
                    )
                    if not resolved_path:
                        self.logger.error(f"Could not resolve document path for output field '{path_config.output_field_name}'. Skipping.")
                        continue
                    namespace, docname = resolved_path

                    is_shared = path_config.is_shared if path_config.is_shared is not None else self.config.global_is_shared
                    is_system_entity = path_config.is_system_entity if path_config.is_system_entity is not None else self.config.global_is_system_entity
                    version_cfg = path_config.version_config or self.config.global_version_config
                    schema_opts = path_config.schema_options or self.config.global_schema_options

                    doc_metadata = None
                    try:
                        doc_metadata = await customer_data_service.get_document_metadata(
                            org_id=org_id, namespace=namespace, docname=docname,
                            is_shared=is_shared, user=user, is_system_entity=is_system_entity
                        )
                    except Exception as meta_err:
                         self.logger.warning(f"Could not fetch metadata for '{namespace}/{docname}': {meta_err}. Assuming unversioned.")
                    is_versioned_doc = doc_metadata.is_versioned if doc_metadata else False

                    document_data = None
                    loaded_schema = None
                    if is_versioned_doc:
                        document_data = await customer_data_service.get_versioned_document(
                            org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                            user=user, version=version_cfg.version, is_system_entity=is_system_entity
                        )
                        if schema_opts.load_schema:
                             loaded_schema = await customer_data_service.get_versioned_document_schema(
                                 org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                                 user=user, is_system_entity=is_system_entity
                             )
                    else:
                        document_data = await customer_data_service.get_unversioned_document(
                            org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                            user=user, is_system_entity=is_system_entity
                        )
                        if schema_opts.load_schema and (schema_opts.schema_template_name or schema_opts.schema_definition):
                             if schema_opts.schema_template_name:
                                 loaded_schema = await customer_data_service._get_schema_from_template(
                                     db=db, template_name=schema_opts.schema_template_name,
                                     template_version=schema_opts.schema_template_version,
                                     org_id=org_id, user=user
                                 )
                             elif schema_opts.schema_definition:
                                 loaded_schema = schema_opts.schema_definition

                    if document_data is not None:
                        output_data[path_config.output_field_name] = document_data
                        if loaded_schema:
                             output_meta.setdefault(path_config.output_field_name, {})['schema'] = loaded_schema
                    else:
                         self.logger.warning(f"Document not found or access denied for '{namespace}/{docname}' (Output field: {path_config.output_field_name}).")

                except Exception as e:
                    self.logger.error(f"Failed to load document for output field '{path_config.output_field_name}': {e}", exc_info=True)

        # Create output instance using the class reference
        output_cls = self.__class__.output_schema_cls

        # Prepare data for instantiation: include explicitly defined fields and dynamic data fields
        # Combine explicitly defined fields (like metadata) with the dynamic data fields
        init_data = {
            "output_metadata": output_meta,
            **output_data  # Add the dynamically loaded data fields
        }

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
            self.logger.error(f"Output validation error: {ve}. Initializing with: {safe_init_data.keys()}")
            # Fallback to empty output, ensuring output_metadata is included if possible
            fallback_data = {"output_metadata": output_meta}
            return output_cls(**fallback_data) # Attempt instantiation with just metadata
        except Exception as e:
             self.logger.error(f"Unexpected error during output instantiation: {e}", exc_info=True)
             fallback_data = {"output_metadata": output_meta}
             return output_cls(**fallback_data)

        return output_instance

# --- Store Customer Data Node ---

class TargetPathConfig(BaseSchema):
    """Configuration for the target path where data will be stored."""
    filename_config: FilenameConfig = Field(
        ...,
        description="Configuration defining how to determine the document's namespace and docname."
    )

class VersioningInfo(BaseSchema):
    """Configuration for how to handle versioning during storage."""
    is_versioned: bool = Field(
        True, description="Whether the target document path uses versioning."
    )
    operation: StoreOperation = Field(
        ..., description="The storage operation to perform (initialize, update, upsert, create_version)."
    )
    version: Optional[str] = Field(
        "default", description="Version name to use for the operation (e.g., for updates, initialization, or new version creation)."
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
        if not self.is_versioned and self.operation not in [StoreOperation.UPSERT, StoreOperation.UPDATE]:
            raise ValueError(f"Operation '{self.operation.value}' is only valid for versioned documents. Use 'upsert' or 'update' for unversioned.")
        if self.is_versioned and self.operation == StoreOperation.UPSERT:
            raise ValueError("Operation 'upsert' is only valid for unversioned documents. Use 'initialize' or 'update'.")
        if self.operation != StoreOperation.CREATE_VERSION and self.from_version is not None:
            raise ValueError("'from_version' is only applicable for 'create_version' operation.")
        if self.operation not in [StoreOperation.UPDATE, StoreOperation.UPSERT] and self.is_complete is not None:
            raise ValueError("'is_complete' is only applicable for 'update'/'upsert' operations on versioned documents.")
        if not self.is_versioned and self.operation == StoreOperation.UPDATE and self.version is not None and self.version != "default":
             # Technically CustomerDataService might allow this, but conceptually weird for unversioned
             self.version = "default" # Force default for unversioned updates? Or just warn? Let's force for clarity.
             # print("Warning: 'version' field ignored for 'update' operation on unversioned documents.")
        return self


class StoreConfig(BaseSchema):
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

class StoreCustomerDataConfig(BaseSchema):
    """Configuration schema for the StoreCustomerDataNode."""
    store_configs: List[StoreConfig] = Field(
        ...,
        min_length=1,
        description="List of configurations, each defining data to store and its target."
    )
    # Global defaults
    global_is_shared: bool = Field(False, description="Default value for 'is_shared'.")
    global_is_system_entity: bool = Field(False, description="Default value for 'is_system_entity'.")
    global_versioning: VersioningInfo = Field(
        default_factory=lambda: VersioningInfo(operation=StoreOperation.UPSERT, is_versioned=False), # Sensible default: upsert unversioned
        description="Default versioning configuration."
    )
    global_schema_options: SchemaOptions = Field(
        default_factory=SchemaOptions, description="Default schema handling options."
    )

class StoreCustomerDataOutput(DynamicSchema):
    """
    Output schema for the StoreCustomerDataNode.

    Can include status or IDs of stored/updated documents, potentially
    organized by the input field path or target path used.
    (Currently returns the input data passthrough).
    """
    # TODO: Define a more structured output? E.g., results per store_config?
    # For now, just pass through input for simplicity, similar to IfElse.
    paths_processed: List[List[str]] = Field(default_factory=list, description="List of paths processed successfully.")
    passthrough_data: Dict[str, Any] = Field(..., description="The original input data passed through.")


class StoreCustomerDataNode(BaseDynamicNode):
    """
    Node to store or update customer data documents (versioned or unversioned) in MongoDB.

    Takes data from the input stream (specified by a path) and writes it to MongoDB
    based on target path configurations (static or derived).
    Supports different storage operations (initialize, update, upsert, create_version)
    and handles schema association/validation.
    Manages shared, user-specific, and system-level documents based on user permissions.
    """
    node_name: ClassVar[str] = "store_customer_data"
    node_version: ClassVar[str] = "0.1.3" # Version bump for paths_processed change
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.PRODUCTION
    input_schema_cls: Type[DynamicSchema] = DynamicSchema
    output_schema_cls: Type[StoreCustomerDataOutput] = StoreCustomerDataOutput
    config_schema_cls: Type[StoreCustomerDataConfig] = StoreCustomerDataConfig
    config: StoreCustomerDataConfig

    async def _store_single_document(
        self,
        doc_data: Dict[str, Any],
        store_cfg: StoreConfig,
        app_context: Dict[str, Any],
        ext_context,  # : ExternalContextManager
        full_input_dict: Dict[str, Any],
        item_index: Optional[int] = None
    ) -> Tuple[bool, Optional[Tuple[str, str, str]]]:
        """
        Helper to store a single document based on configuration.
        
        Returns:
            Tuple containing:
                - success flag (bool)
                - Optional tuple of (namespace, docname, operation) for successful operations
        """
        user: User = app_context["user"]
        run_job: WorkflowRunJobCreate = app_context["workflow_run_job"]
        org_id = run_job.owner_org_id
        customer_data_service: CustomerDataService = ext_context.customer_data_service

        resolved_path = _resolve_single_doc_path(
            config=store_cfg.target_path.filename_config,
            full_input_data=full_input_dict,
            current_item_data=doc_data,
            item_index=item_index
        )
        if not resolved_path:
            self.logger.error(f"Could not resolve target path for item from input '{store_cfg.input_field_path}' (index: {item_index}). Skipping store.")
            return False, None
        namespace, docname = resolved_path

        is_shared = store_cfg.is_shared if store_cfg.is_shared is not None else self.config.global_is_shared
        is_system_entity = store_cfg.is_system_entity if store_cfg.is_system_entity is not None else self.config.global_is_system_entity
        versioning = store_cfg.versioning or self.config.global_versioning
        schema_opts = store_cfg.schema_options or self.config.global_schema_options

        async with get_async_db_as_manager() as db:
            try:
                operation_str = ""
                if not versioning.is_versioned:
                    # --- Handle Unversioned ---
                    if versioning.operation == StoreOperation.UPSERT:
                        _id, created = await customer_data_service.create_or_update_unversioned_document(
                            db=db, org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                            user=user, data=doc_data, schema_template_name=schema_opts.schema_template_name,
                            schema_template_version=schema_opts.schema_template_version,
                            schema_definition=schema_opts.schema_definition,
                            is_system_entity=is_system_entity
                        )
                        operation_str = "upsert_unversioned"
                        self.logger.info(f"Upserted unversioned doc '{namespace}/{docname}'. Created: {created}")
                    elif versioning.operation == StoreOperation.UPDATE:
                         _id, created = await customer_data_service.create_or_update_unversioned_document(
                            db=db, org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                            user=user, data=doc_data, schema_template_name=schema_opts.schema_template_name,
                            schema_template_version=schema_opts.schema_template_version,
                            schema_definition=schema_opts.schema_definition,
                            is_system_entity=is_system_entity
                         )
                         operation_str = "update_unversioned"
                         if created:
                             self.logger.warning(f"Performed 'update' on unversioned doc '{namespace}/{docname}', but it was created instead of updated.")
                         else:
                             self.logger.info(f"Updated unversioned doc '{namespace}/{docname}'.")
                    else:
                        self.logger.error(f"Invalid operation '{versioning.operation.value}' for unversioned document '{namespace}/{docname}'.")
                        return False, None

                else:
                    # --- Handle Versioned ---
                    if versioning.operation == StoreOperation.INITIALIZE:
                        success = await customer_data_service.initialize_versioned_document(
                            db=db, org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                            user=user, initial_version=versioning.version or "default",
                            schema_template_name=schema_opts.schema_template_name,
                            schema_template_version=schema_opts.schema_template_version,
                            schema_definition=schema_opts.schema_definition,
                            initial_data=doc_data, is_complete=versioning.is_complete or False,
                            is_system_entity=is_system_entity
                        )
                        if success:
                            operation_str = f"initialize_versioned_{versioning.version or 'default'}"
                            self.logger.info(f"Initialized versioned doc '{namespace}/{docname}' with version '{versioning.version or 'default'}'.")
                        else:
                            self.logger.error(f"Failed to initialize versioned doc '{namespace}/{docname}': Already exists or other error.")
                            return False, None

                    elif versioning.operation == StoreOperation.UPDATE:
                        success = await customer_data_service.update_versioned_document(
                            db=db, org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                            user=user, data=doc_data, version=versioning.version,
                            is_complete=versioning.is_complete, 
                            schema_template_name=schema_opts.schema_template_name,
                            schema_template_version=schema_opts.schema_template_version,
                            schema_definition=schema_opts.schema_definition,
                            is_system_entity=is_system_entity
                        )
                        if success:
                            operation_str = f"update_versioned_{versioning.version or 'active'}"
                            self.logger.info(f"Updated versioned doc '{namespace}/{docname}' (version: {versioning.version or 'active'}).")
                        else:
                            self.logger.error(f"Failed to update versioned doc '{namespace}/{docname}': Not found or other error.")
                            return False, None

                    elif versioning.operation == StoreOperation.CREATE_VERSION:
                        new_version_name = versioning.version
                        if not new_version_name:
                            new_version_name = f"version_{uuid.uuid4().hex[:8]}"
                            self.logger.info(f"Generated new version name: {new_version_name}")

                        success = await customer_data_service.create_versioned_document_version(
                            org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                            user=user, new_version=new_version_name, from_version=versioning.from_version,
                            is_system_entity=is_system_entity
                        )
                        if success:
                            update_success = await customer_data_service.update_versioned_document(
                                db=db, org_id=org_id, namespace=namespace, docname=docname, is_shared=is_shared,
                                user=user, data=doc_data, version=new_version_name,
                                is_complete=versioning.is_complete,
                                schema_template_name=schema_opts.schema_template_name,
                                schema_template_version=schema_opts.schema_template_version,
                                schema_definition=schema_opts.schema_definition,
                                is_system_entity=is_system_entity
                            )
                            if update_success:
                                operation_str = f"create_version_{new_version_name}"
                                self.logger.info(f"Created and updated new version '{new_version_name}' for doc '{namespace}/{docname}'.")
                            else:
                                self.logger.error(f"Created new version '{new_version_name}' for doc '{namespace}/{docname}', but failed to update it with data.")
                                return False, None
                        else:
                            self.logger.error(f"Failed to create new version '{new_version_name}' for doc '{namespace}/{docname}'.")
                            return False, None
                    else:
                        self.logger.error(f"Unsupported operation '{versioning.operation.value}' for versioned document.")
                        return False, None
                
                # Return success and path info for tracking
                return True, (namespace, docname, operation_str)

            except Exception as e:
                self.logger.error(f"Error storing document '{namespace}/{docname}': {e}", exc_info=True)
                return False, None

    async def process(
        self,
        input_data: Union[DynamicSchema, Dict[str, Any]],
        runtime_config: Optional[Dict[str, Any]] = None, # Renamed config
        *args: Any,
        **kwargs: Any
    ) -> StoreCustomerDataOutput:
        """
        Stores or updates customer data based on the node's configuration.

        Args:
            input_data: The input data containing the document(s) to store.
            runtime_config: The runtime configuration containing execution context.
            *args: Additional positional arguments (unused).
            **kwargs: Additional keyword arguments (unused).

        Returns:
            StoreCustomerDataOutput: Passes through the original input data and includes
            a list of successfully processed paths with their operations.
        """
        # Retrieve context from runtime_config
        if not runtime_config:
            self.logger.error("Missing runtime_config.")
            passthrough_dict = input_data if isinstance(input_data, dict) else input_data.model_dump(mode='json')
            # Instantiate output using class reference, even on failure
            return self.__class__.output_schema_cls(passthrough_data=passthrough_dict, paths_processed=[])

        app_context: Optional[Dict[str, Any]] = runtime_config.get(APPLICATION_CONTEXT_KEY)
        ext_context = runtime_config.get(EXTERNAL_CONTEXT_MANAGER_KEY)  # : Optional[ExternalContextManager]

        if not app_context or not ext_context:
            self.logger.error(f"Missing required keys in runtime_config: {APPLICATION_CONTEXT_KEY} or {EXTERNAL_CONTEXT_MANAGER_KEY}")
            passthrough_dict = input_data if isinstance(input_data, dict) else input_data.model_dump(mode='json')
            return self.__class__.output_schema_cls(passthrough_data=passthrough_dict, paths_processed=[])

        input_dict = input_data if isinstance(input_data, dict) else input_data.model_dump(mode='json')
        passthrough_input = input_dict  # copy.deepcopy(input_dict) # Keep original for output

        all_success = True
        paths_processed: List[Tuple[str, str, str]] = []  # List of (namespace, docname, operation) tuples
        
        for store_cfg in self.config.store_configs:
            data_to_store, found = _get_nested_obj(input_dict, store_cfg.input_field_path)

            if not found:
                self.logger.warning(f"Input field '{store_cfg.input_field_path}' not found. Skipping store configuration.")
                all_success = False
                continue

            if isinstance(data_to_store, list):
                item_success = True
                for item_index, item_data in enumerate(data_to_store):
                    if isinstance(item_data, dict):
                        # Pass contexts to helper
                        success, path_info = await self._store_single_document(
                            item_data, store_cfg, app_context, ext_context, input_dict, item_index
                        )
                        item_success &= success
                        if success and path_info:
                            paths_processed.append(list(path_info))
                    else:
                        self.logger.warning(f"Item at index {item_index} in '{store_cfg.input_field_path}' is not a dictionary. Skipping.")
                        item_success = False
                all_success &= item_success
            elif isinstance(data_to_store, dict):
                # Pass contexts to helper
                success, path_info = await self._store_single_document(
                    data_to_store, store_cfg, app_context, ext_context, input_dict, item_index=None
                )
                all_success &= success
                if success and path_info:
                    paths_processed.append(list(path_info))
            else:
                self.logger.warning(f"Data at '{store_cfg.input_field_path}' is not a dictionary or list of dictionaries. Skipping.")
                all_success = False

        if not all_success:
             self.logger.warning("One or more documents failed to store.")

        # Instantiate output using class reference
        output_cls = self.__class__.output_schema_cls
        # Populate the defined fields (passthrough_data and paths_processed)
        output_instance = output_cls(
            passthrough_data=passthrough_input,
            paths_processed=paths_processed
        )

        return output_instance


