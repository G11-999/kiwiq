"""
Node for loading multiple customer data documents based on listing criteria.
"""

import uuid
from typing import Any, Dict, List, Optional, Type, ClassVar, Union

from pydantic import Field, model_validator, ValidationError

# Internal dependencies
from global_config.logger import get_prefect_or_regular_python_logger
from kiwi_app.workflow_app.constants import LaunchStatus
from kiwi_app.auth.models import User
from kiwi_app.workflow_app.schemas import (
    WorkflowRunJobCreate,
    CustomerDataSortBy,
    SortOrder,
    CustomerDocumentMetadata,
)
from kiwi_app.workflow_app.service_customer_data import CustomerDataService
from db.session import get_async_db_as_manager
from workflow_service.config.constants import (
    APPLICATION_CONTEXT_KEY,
    EXTERNAL_CONTEXT_MANAGER_KEY,
)

# Base node/schema types and sibling node components
from workflow_service.registry.schemas.base import BaseSchema, BaseNodeConfig
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema, BaseDynamicNode
from workflow_service.registry.nodes.db.customer_data import (
    VersionConfig,
    SchemaOptions,
    _get_nested_obj, # Re-use helper if needed, but less likely here
)


# --- Configuration Schemas ---

class LoadMultipleCustomerDataConfig(BaseNodeConfig):
    """
    Configuration schema for the LoadMultipleCustomerDataNode.

    Defines criteria for listing documents and options for loading them.
    """
    # Dynamic Configuration Loading
    config_input_path: Optional[str] = Field(
        None,
        description="Dot-notation path within the node's input data to find the listing configuration. "
                   "This can be a JSON object matching this schema structure. "
                   "If provided, values from this dynamic configuration override the static configuration fields."
    )
    
    # Listing Criteria
    namespace_filter: Optional[str] = Field(
        None,
        description="Optional namespace to filter documents by. If None or '*', lists across all accessible namespaces."
    )
    # Namespace Pattern Support (similar to customer_data.py)
    namespace_pattern: Optional[str] = Field(
        None,
        description="f-string like template to generate the namespace (e.g., 'user_{item}'). "
                   "Used to dynamically create namespace filters."
    )
    namespace_pattern_input_path: Optional[str] = Field(
        None,
        description="Dot-notation path within the input data to find the value(s) to use in the namespace_pattern. "
                   "The object found at this path will be available as 'item' in the pattern context."
    )
    
    include_shared: bool = Field(
        True, description="Include shared documents in the listing."
    )
    include_user_specific: bool = Field(
        True, description="Include user-specific documents in the listing."
    )
    include_system_entities: bool = Field(
        False, description="Include system entities (requires superuser privileges)."
    )
    on_behalf_of_user_id: Optional[str] = Field(
        None, description="User ID (as string) to list/load documents on behalf of (requires superuser privileges)."
    )

    # Pagination and Sorting
    skip: Optional[int] = Field(
        0, ge=0, description="Number of documents to skip (for pagination)."
    )
    limit: Optional[int] = Field(
        100, ge=1, le=200, description="Maximum number of documents to return (for pagination)."
    )
    sort_by: Optional[CustomerDataSortBy] = Field(
        None, description="Field to sort by ('created_at', 'updated_at')."
    )
    sort_order: Optional[SortOrder] = Field(
        SortOrder.DESC, description="Sort order ('asc' or 'desc')."
    )

    # Loading Options (Applied to each document found by listing)
    global_version_config: Optional[VersionConfig] = Field(
        default=None, # <<< Change this back to None
        description="Default version configuration to apply when loading versioned documents. If None, loads the active version."
    )
    global_schema_options: Optional[SchemaOptions] = Field(
        default_factory=SchemaOptions,
        description="Default schema handling options to apply when loading documents."
    )

    # Output Configuration
    output_field_name: str = Field(
        ...,
        description="The field name in the output data where the list of loaded documents will be placed. "
                    "Must not start with underscore (_)."
    )

    @model_validator(mode='after')
    def validate_output_field_name(self) -> 'LoadMultipleCustomerDataConfig':
        """Ensure output_field_name doesn't start with underscore."""
        if self.output_field_name.startswith('_'):
            raise ValueError(f"output_field_name '{self.output_field_name}' cannot start with underscore (_).")
        return self

    @model_validator(mode='after')
    def check_inclusion_flags(self) -> 'LoadMultipleCustomerDataConfig':
        """Ensure at least one inclusion flag is True if not including system entities."""
        if not self.include_system_entities and not self.include_shared and not self.include_user_specific:
             raise ValueError("At least one of 'include_shared', 'include_user_specific', or 'include_system_entities' must be True.")
        return self
        
    @model_validator(mode='after')
    def validate_namespace_pattern(self) -> 'LoadMultipleCustomerDataConfig':
        """Validate namespace pattern configuration."""
        if self.namespace_pattern and not self.namespace_pattern_input_path:
            raise ValueError("When using 'namespace_pattern', 'namespace_pattern_input_path' must also be provided.")
            
        if self.namespace_pattern_input_path and not self.namespace_pattern:
            raise ValueError("When using 'namespace_pattern_input_path', 'namespace_pattern' must also be provided.")
            
        # Basic pattern validation (simple check)
        if self.namespace_pattern and ('{' not in self.namespace_pattern or '}' not in self.namespace_pattern):
            logger = get_prefect_or_regular_python_logger(f"{__name__}")
            logger.warning(f"namespace_pattern '{self.namespace_pattern}' doesn't look like a valid f-string pattern.")
            
        # Prevent conflicting namespace specifications
        if self.namespace_pattern and self.namespace_filter:
            raise ValueError("Provide either 'namespace_filter' or 'namespace_pattern', not both.")
            
        return self


# --- Output Schema ---

class LoadMultipleCustomerDataOutput(DynamicSchema):
    """
    Output schema for the LoadMultipleCustomerDataNode.

    Contains the list of loaded documents under the dynamically configured field name.
    Includes metadata about the loading operation.
    """
    # This field will be populated dynamically based on config.output_field_name
    # Example: loaded_docs: List[Dict[str, Any]] = Field(...)

    # Metadata fields
    load_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about the loading operation, e.g., number requested, number loaded."
    )


# --- Node Implementation ---

class LoadMultipleCustomerDataNode(BaseDynamicNode):
    """
    Node to list and load multiple customer data documents based on specified criteria.

    Uses `CustomerDataService.list_documents` to find document metadata matching
    the configuration (namespace, shared/user/system scope, pagination, sorting)
    and then loads each document individually using the appropriate versioned or
    unversioned getter from the service.
    """
    node_name: ClassVar[str] = "load_multiple_customer_data"
    node_version: ClassVar[str] = "0.1.2" # Updated version for namespace pattern support
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.DEVELOPMENT # Start as development

    # Input schema can be dynamic, accepting various inputs potentially used by other nodes
    # input_schema_cls: Type[DynamicSchema] = DynamicSchema
    output_schema_cls: ClassVar[Type[LoadMultipleCustomerDataOutput]] = LoadMultipleCustomerDataOutput
    config_schema_cls: ClassVar[Type[LoadMultipleCustomerDataConfig]] = LoadMultipleCustomerDataConfig
    config: LoadMultipleCustomerDataConfig
    
    def _resolve_namespace_pattern(
        self, 
        pattern: str,
        pattern_input_path: str,
        input_dict: Dict[str, Any],
        logger
    ) -> Optional[str]:
        """
        Resolve a namespace pattern using values from the input data.
        
        Args:
            pattern: The pattern template with placeholders (e.g., 'user_{item}').
            pattern_input_path: Path in the input data to find values for the pattern.
            input_dict: The complete input dictionary.
            logger: Logger instance for error reporting.
            
        Returns:
            The resolved namespace string or None if resolution fails.
        """
        try:
            # Get the object to use in pattern substitution
            pattern_data, found = _get_nested_obj(input_dict, pattern_input_path)
            
            if not found:
                logger.error(f"Data for namespace pattern not found at '{pattern_input_path}' in input data.")
                return None
                
            # Format the pattern using the retrieved data as the 'item' context
            resolved_namespace = pattern.format(item=pattern_data)
            logger.info(f"Resolved namespace pattern '{pattern}' to '{resolved_namespace}'")
            return resolved_namespace
            
        except KeyError as e:
            logger.error(f"Error formatting namespace_pattern '{pattern}': Key {e} not found in data at '{pattern_input_path}'.")
            return None
        except Exception as e:
            logger.error(f"Error formatting namespace_pattern '{pattern}': {e}")
            return None

    async def process(
        self,
        input_data: Union[DynamicSchema, Dict[str, Any]],
        runtime_config: Optional[Dict[str, Any]] = None,
        *args: Any,
        **kwargs: Any
    ) -> LoadMultipleCustomerDataOutput:
        """
        Lists and loads multiple customer documents based on node configuration.

        Args:
            input_data: Input data (can contain dynamic configuration if config_input_path is set).
            runtime_config: Runtime configuration containing execution context
                            (MUST include APPLICATION_CONTEXT_KEY and EXTERNAL_CONTEXT_MANAGER_KEY).
            *args: Additional positional arguments (unused).
            **kwargs: Additional keyword arguments (unused).

        Returns:
            LoadMultipleCustomerDataOutput: An object containing the list of loaded documents
                                            under the configured field name, plus metadata.
        """
        logger = get_prefect_or_regular_python_logger(f"{__name__}.{self.__class__.__name__}")

        # --- 1. Extract Context ---
        if not runtime_config:
            logger.error("Missing runtime_config.")
            # Return empty output, respecting the schema structure
            return self.__class__.output_schema_cls(load_metadata={"error": "Missing runtime_config"})

        # Ensure 'configurable' key exists
        runtime_config = runtime_config.get("configurable", {})
        app_context: Optional[Dict[str, Any]] = runtime_config.get(APPLICATION_CONTEXT_KEY)
        ext_context = runtime_config.get(EXTERNAL_CONTEXT_MANAGER_KEY) # : Optional[ExternalContextManager]

        if not app_context or not ext_context:
            logger.error(f"Missing required keys in runtime_config: {APPLICATION_CONTEXT_KEY} or {EXTERNAL_CONTEXT_MANAGER_KEY}")
            return self.__class__.output_schema_cls(load_metadata={"error": "Missing context in runtime_config"})

        user: Optional[User] = app_context.get("user")
        run_job: Optional[WorkflowRunJobCreate] = app_context.get("workflow_run_job")

        if not user or not run_job:
            logger.error("Missing 'user' or 'workflow_run_job' in application_context.")
            return self.__class__.output_schema_cls(load_metadata={"error": "Missing user or run_job in context"})

        org_id = run_job.owner_org_id
        customer_data_service: CustomerDataService = ext_context.customer_data_service
        input_dict = input_data if isinstance(input_data, dict) else input_data.model_dump(mode='json')

        logger.info(f"Starting {self.node_name} processing for org {org_id}, user {user.id}.")

        # --- 1.5 Handle Dynamic Configuration if specified ---
        effective_config = self.config
        
        if self.config.config_input_path:
            logger.info(f"Attempting to load configuration from input path: {self.config.config_input_path}")
            dynamic_config_data, found = _get_nested_obj(input_dict, self.config.config_input_path)
            
            if not found:
                logger.warning(f"Input path '{self.config.config_input_path}' for dynamic configuration not found in input data. Using static configuration.")
            else:
                try:
                    if isinstance(dynamic_config_data, dict):
                        # Create a merged configuration with static config as base and dynamic config as override
                        # First, create a copy of current config values
                        static_config_dict = self.config.model_dump()
                        
                        # Remove the config_input_path to prevent circular reference issues
                        dynamic_config_dict = {
                            k: v for k, v in dynamic_config_data.items() 
                            if k != "config_input_path"
                        }
                        
                        # Merge: start with static config and override with dynamic values
                        merged_config_dict = {**static_config_dict, **dynamic_config_dict}
                        
                        # Validate the merged configuration
                        effective_config = LoadMultipleCustomerDataConfig.model_validate(merged_config_dict)
                        logger.info(f"Successfully loaded and merged dynamic configuration from '{self.config.config_input_path}'.")
                    else:
                        logger.warning(f"Data found at '{self.config.config_input_path}' is not a valid object for configuration. Type: {type(dynamic_config_data)}. Using static configuration.")
                except ValidationError as e:
                    logger.error(f"Validation error parsing dynamic configuration from input path '{self.config.config_input_path}': {e}. Using static configuration.")
                except Exception as e:
                    logger.error(f"Unexpected error parsing dynamic configuration from input path '{self.config.config_input_path}': {e}. Using static configuration.")

        # --- 1.75 Resolve Namespace Pattern if specified ---
        effective_namespace_filter = effective_config.namespace_filter
        
        if effective_config.namespace_pattern and effective_config.namespace_pattern_input_path:
            logger.info(f"Attempting to resolve namespace pattern: {effective_config.namespace_pattern}")
            resolved_namespace = self._resolve_namespace_pattern(
                pattern=effective_config.namespace_pattern,
                pattern_input_path=effective_config.namespace_pattern_input_path,
                input_dict=input_dict,
                logger=logger
            )
            
            if resolved_namespace:
                effective_namespace_filter = resolved_namespace
                logger.info(f"Using resolved namespace filter: {effective_namespace_filter}")
            else:
                logger.error("Failed to resolve namespace pattern. Defaulting to static namespace_filter.")
                # Depending on requirements, you might want to terminate here instead:
                # return self.__class__.output_schema_cls(load_metadata={"error": "Failed to resolve namespace pattern"})

        # --- 2. Prepare Listing Parameters ---
        on_behalf_id_str = effective_config.on_behalf_of_user_id
        on_behalf_of_user_id_uuid: Optional[uuid.UUID] = None
        if on_behalf_id_str:
            try:
                on_behalf_of_user_id_uuid = uuid.UUID(on_behalf_id_str)
                # Superuser check for 'on behalf of'
                if not user.is_superuser:
                    logger.error(f"User '{user.id}' is not a superuser and cannot use 'on_behalf_of_user_id'='{on_behalf_id_str}'.")
                    return self.__class__.output_schema_cls(load_metadata={"error": "Permission denied for on_behalf_of_user_id"})
            except ValueError:
                logger.error(f"Invalid UUID format for on_behalf_of_user_id: '{on_behalf_id_str}'.")
                return self.__class__.output_schema_cls(load_metadata={"error": "Invalid on_behalf_of_user_id format"})

        # Superuser check for including system entities
        if effective_config.include_system_entities and not user.is_superuser:
             logger.error(f"User '{user.id}' is not a superuser and cannot use 'include_system_entities=True'.")
             return self.__class__.output_schema_cls(load_metadata={"error": "Permission denied for include_system_entities"})


        # --- 3. List Documents ---
        listed_docs_metadata: List[CustomerDocumentMetadata] = []
        try:
            logger.info(f"Listing documents with config: {effective_config.model_dump(exclude_none=True)}")
            listed_docs_metadata = await customer_data_service.list_documents(
                org_id=org_id,
                user=user,
                namespace_filter=effective_namespace_filter,
                include_shared=effective_config.include_shared,
                include_user_specific=effective_config.include_user_specific,
                skip=effective_config.skip or 0,
                limit=effective_config.limit or 100,
                on_behalf_of_user_id=on_behalf_of_user_id_uuid,
                include_system_entities=effective_config.include_system_entities,
                sort_by=effective_config.sort_by,
                sort_order=effective_config.sort_order,
            )
            logger.info(f"Found {len(listed_docs_metadata)} document(s) matching criteria.")

        except Exception as list_err:
            logger.error(f"Failed to list documents: {list_err}", exc_info=True)
            return self.__class__.output_schema_cls(load_metadata={"error": f"Failed to list documents: {list_err}"})

        # --- 4. Load Each Document ---
        loaded_documents_list: List[Dict[str, Any]] = []
        load_errors: List[str] = []
        schemas_loaded: Dict[str, Any] = {} # Track loaded schemas if needed

        # Get global loading options once
        version_cfg = effective_config.global_version_config # Keep it Optional
        schema_opts = effective_config.global_schema_options or SchemaOptions()

        async with get_async_db_as_manager() as db: # Needed for schema template loading
            for metadata in listed_docs_metadata:
                doc_identifier = f"{metadata.namespace}/{metadata.docname}"
                doc_org_id = metadata.org_id # May be None for system entities
                # Reconstruct effective user_id for logging/debugging if needed
                effective_user_id = metadata.user_id_or_shared_placeholder

                logger.debug(f"Processing document: {doc_identifier} (shared: {metadata.is_shared}, system: {metadata.is_system_entity}, versioned: {metadata.is_versioned})")

                try:
                    document_data = None
                    loaded_schema = None # Schema for this specific document

                    if metadata.is_versioned:
                        # Determine the version to load: Use config if provided, else None (for active version)
                        version_to_load: Optional[str] = version_cfg.version if version_cfg else None
                        logger.debug(f"Attempting to load version: {version_to_load if version_to_load is not None else 'active (None)'}")

                        # Load versioned document
                        document_data = await customer_data_service.get_versioned_document(
                            # Use the org_id from the metadata if available, else the run's org_id (fallback, less precise for system docs)
                            org_id=doc_org_id or org_id,
                            namespace=metadata.namespace,
                            docname=metadata.docname,
                            is_shared=metadata.is_shared,
                            user=user, # The user performing the action
                            version=version_to_load, # Pass the determined version (or None)
                            on_behalf_of_user_id=on_behalf_of_user_id_uuid, # Use the overall on_behalf_of
                            is_system_entity=metadata.is_system_entity,
                        )
                        if schema_opts.load_schema:
                             try:
                                 loaded_schema = await customer_data_service.get_versioned_document_schema(
                                     org_id=doc_org_id or org_id,
                                     namespace=metadata.namespace,
                                     docname=metadata.docname,
                                     is_shared=metadata.is_shared,
                                     user=user,
                                     on_behalf_of_user_id=on_behalf_of_user_id_uuid,
                                     is_system_entity=metadata.is_system_entity,
                                 )
                             except Exception as schema_err:
                                 logger.warning(f"Failed to load schema for versioned doc '{doc_identifier}': {schema_err}")

                    else:
                        # Load unversioned document
                        document_data = await customer_data_service.get_unversioned_document(
                            org_id=doc_org_id or org_id,
                            namespace=metadata.namespace,
                            docname=metadata.docname,
                            is_shared=metadata.is_shared,
                            user=user,
                            on_behalf_of_user_id=on_behalf_of_user_id_uuid,
                            is_system_entity=metadata.is_system_entity,
                        )
                        # Schema loading for unversioned (requires template name or definition)
                        if schema_opts.load_schema and (schema_opts.schema_template_name or schema_opts.schema_definition):
                             if schema_opts.schema_template_name:
                                 try:
                                     # Use the db session acquired earlier
                                     loaded_schema = await customer_data_service._get_schema_from_template(
                                         db=db,
                                         template_name=schema_opts.schema_template_name,
                                         template_version=schema_opts.schema_template_version,
                                         # Use the org_id context for schema lookup
                                         org_id=org_id, # Or doc_org_id? Needs clarification which context is right for schema lookup
                                         user=user # User context for permission check
                                     )
                                 except Exception as schema_err:
                                     logger.warning(f"Failed to load schema template '{schema_opts.schema_template_name}' for unversioned doc '{doc_identifier}': {schema_err}")
                             elif schema_opts.schema_definition:
                                 loaded_schema = schema_opts.schema_definition

                    if document_data is not None:
                        # Optionally attach schema to document data or store separately
                        # For simplicity, just append the data for now.
                        loaded_documents_list.append(document_data)
                        if loaded_schema:
                             # Decide how to store/return schema info. Maybe in metadata?
                             schemas_loaded[doc_identifier] = loaded_schema # Store per doc for now
                    else:
                        # This case might happen if doc deleted between list and get, or permission issue surfaced during get
                        logger.warning(f"Document '{doc_identifier}' found in list but could not be loaded (None returned). Skipping.")
                        load_errors.append(f"Could not load '{doc_identifier}'")

                except Exception as load_err:
                    logger.error(f"Failed to load document '{doc_identifier}': {load_err}", exc_info=True)
                    load_errors.append(f"Error loading '{doc_identifier}': {load_err}")

        # --- 5. Prepare and Return Output ---
        print("\n\n\n\neffective_namespace_filter\n\n\n\n")
        print(effective_namespace_filter, effective_config.namespace_pattern)
        print("\n\n\n\n")
        output_metadata = {
            "documents_listed": len(listed_docs_metadata),
            "documents_loaded": len(loaded_documents_list),
            "load_errors": load_errors,
            "schemas_loaded_count": len(schemas_loaded), # Basic schema metadata for now
            # Add more metadata like pagination info if needed
            "config_skip": effective_config.skip,
            "config_limit": effective_config.limit,
            "used_dynamic_config": self.config.config_input_path is not None and effective_config != self.config,
            "resolved_namespace": effective_namespace_filter  #  if effective_config.namespace_pattern else None
        }

        # Create output instance dynamically
        output_cls = self.__class__.output_schema_cls
        try:
            # Prepare data for instantiation: include fixed fields and the dynamic data field
            init_data = {
                "load_metadata": output_metadata,
                # Add the list of documents under the dynamic field name
                effective_config.output_field_name: loaded_documents_list,
            }

            # Instantiate, relying on DynamicSchema's handling of extra fields
            output_instance = output_cls(**init_data)

            logger.info(f"Completed {self.node_name} processing. Loaded {len(loaded_documents_list)} documents into field '{effective_config.output_field_name}'.")
            return output_instance

        except ValidationError as ve:
             logger.error(f"Output validation error for {self.node_name}: {ve}. Data: {list(init_data.keys())}", exc_info=True)
             # Fallback to default output with error metadata
             return output_cls(load_metadata={
                 **output_metadata,
                 "error": f"Output validation failed: {ve}"
             })
        except Exception as e:
             logger.error(f"Unexpected error during {self.node_name} output instantiation: {e}", exc_info=True)
             # Fallback to default output with error metadata
             return output_cls(load_metadata={
                 **output_metadata,
                 "error": f"Unexpected error during output creation: {e}"
             })


# Example Usage (for testing or documentation)
if __name__ == "__main__":
    # Example config - list user-specific docs in 'reports' namespace
    config_dict = {
        "namespace_filter": "reports",
        "include_shared": False,
        "include_user_specific": True,
        "limit": 10,
        "sort_by": "updated_at",
        "sort_order": "desc",
        "output_field_name": "loaded_reports",
        "global_version_config": {"version": "latest"} # Example: try to load 'latest' version if docs are versioned
    }
    try:
        test_config = LoadMultipleCustomerDataConfig(**config_dict)
        print("Example Config Validation Successful:")
        print(test_config.model_dump_json(indent=2))

        # Dummy node instance (cannot run process directly without runtime context)
        node_instance = LoadMultipleCustomerDataNode(config=test_config, node_id="test_multi_load")
        print(f"\nNode instance created: {node_instance.node_name} v{node_instance.node_version}")

    except ValidationError as e:
        print(f"Example Config Validation Failed:\n{e}")
