"""
Defines a workflow node for loading Prompt Templates from the database.
"""

import logging
from typing import Any, Dict, Optional, Type, ClassVar, Union, List, Tuple

from pydantic import Field, model_validator

# Internal dependencies
from kiwi_app.workflow_app.constants import LaunchStatus
from kiwi_app.workflow_app import crud as wf_crud
from kiwi_app.workflow_app.schemas import WorkflowRunJobCreate # For application context typing
from kiwi_app.auth.models import User
from db.session import get_async_db_as_manager # For database access
# Import helper from customer_data for nested object retrieval
from workflow_service.registry.nodes.db.customer_data import _get_nested_obj 

# Base node/schema types
from workflow_service.registry.schemas.base import BaseSchema, BaseNodeConfig
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema, BaseDynamicNode
from workflow_service.services.external_context_manager import ExternalContextManager
from workflow_service.config.constants import (
    APPLICATION_CONTEXT_KEY,
    EXTERNAL_CONTEXT_MANAGER_KEY
)

# Setup logger
log = logging.getLogger(__name__)

# --- Helper Function for Path Resolution ---

def _resolve_template_path(
    static_name: Optional[str],
    static_version: Optional[str],
    input_name_field_path: Optional[str],
    input_version_field_path: Optional[str],
    input_data: Dict[str, Any]
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Resolves the template name and version based on static config and input data.

    Priority:
    1. Value from input_field_path (if path provided and found in input_data).
    2. Static value (if provided).
    3. None if neither is available or input path not found.

    Args:
        static_name: Statically configured template name.
        static_version: Statically configured template version.
        input_name_field_path: Dot-notation path to find name in input_data.
        input_version_field_path: Dot-notation path to find version in input_data.
        input_data: The node's input data dictionary.

    Returns:
        Tuple (resolved_name, resolved_version, error_message).
        Returns (None, None, error_message) if resolution fails for either.
    """
    resolved_name: Optional[str] = None
    resolved_version: Optional[str] = None
    error_message: Optional[str] = None

    # Resolve Name
    if input_name_field_path:
        name_val, found = _get_nested_obj(input_data, input_name_field_path)
        if found and isinstance(name_val, str):
            resolved_name = name_val
            log.debug(f"Resolved template name '{resolved_name}' from input path '{input_name_field_path}'.")
        elif found:
            error_message = f"Input field '{input_name_field_path}' for template name found but is not a string (type: {type(name_val)})."
            log.warning(error_message)
            # Continue to static fallback if defined
            if static_name:
                resolved_name = static_name
                log.debug(f"Using static template name '{resolved_name}' as fallback.")
                error_message = None # Clear error as we have a fallback
            else:
                 return None, None, error_message # Fatal if no static fallback
        else: # Not found
            log.debug(f"Input field '{input_name_field_path}' for template name not found.")
            if static_name:
                resolved_name = static_name
                log.debug(f"Using static template name '{resolved_name}' as fallback.")
            else:
                error_message = f"Template name resolution failed: Input field '{input_name_field_path}' not found and no static_name provided."
                log.warning(error_message)
                return None, None, error_message
    elif static_name:
        resolved_name = static_name
        log.debug(f"Using static template name '{resolved_name}'.")
    else:
        error_message = "Template name resolution failed: Neither input_name_field_path nor static_name provided."
        log.error(error_message)
        return None, None, error_message

    # Resolve Version
    if input_version_field_path:
        version_val, found = _get_nested_obj(input_data, input_version_field_path)
        if found and isinstance(version_val, str):
            resolved_version = version_val
            log.debug(f"Resolved template version '{resolved_version}' from input path '{input_version_field_path}'.")
        elif found:
            # If found but wrong type, still try static fallback if version IS required implicitly by static_version being set
            error_message = f"Input field '{input_version_field_path}' for template version found but is not a string (type: {type(version_val)})."
            log.warning(error_message)
            if static_version:
                resolved_version = static_version
                log.debug(f"Using static template version '{resolved_version}' as fallback.")
                error_message = None
            else:
                 # If no static fallback, and input was provided but invalid, it IS an error.
                 return resolved_name, None, error_message 
        else: # Not found via input path
            log.debug(f"Input field '{input_version_field_path}' for template version not found.")
            if static_version:
                resolved_version = static_version
                log.debug(f"Using static template version '{resolved_version}' as fallback.")
            # If input path was specified but not found, AND no static version exists, treat as resolvable to None (version optional)
            # else: # No static version, input path specified but not found -> version is None
            #    resolved_version = None 
            #    log.debug("No static version and input path not found, resolving version to None.")
    elif static_version:
        resolved_version = static_version
        log.debug(f"Using static template version '{resolved_version}'.")
    # If neither input path nor static version was provided, version resolves to None cleanly.
    else:
        resolved_version = None 
        log.debug("Neither static_version nor input_version_field_path provided, resolving version to None.")
        error_message = None # Not an error if version is optional

    # Final check: Name must always be resolved. Version is optional.
    if resolved_name:
        return resolved_name, resolved_version, None # Return None for error if successful
    else:
        # This case should be covered by name resolution logic, but safeguard.
        final_error = error_message or "Name resolution failed for unknown reason."
        log.error(f"Final resolution check failed for name: {final_error}")
        return None, None, final_error


# --- Configuration Schemas ---

class PromptTemplatePathConfig(BaseNodeConfig):
    """
    Configuration for resolving a prompt template's name and version.
    Supports static values or dynamic retrieval from input fields.
    """
    # Static Definition
    static_name: Optional[str] = Field(None, description="A fixed template name.")
    static_version: Optional[str] = Field(None, description="A fixed template version.")

    # Dynamic Retrieval from Input Data
    input_name_field_path: Optional[str] = Field(
        None, description="Dot-notation path in the input data to retrieve the template name."
    )
    input_version_field_path: Optional[str] = Field(
        None, description="Dot-notation path in the input data to retrieve the template version."
    )

    @model_validator(mode='after')
    def validate_config(self) -> 'PromptTemplatePathConfig':
        """Ensures that either static or input path is provided for the name."""
        if not self.static_name and not self.input_name_field_path:
            raise ValueError("Either static_name or input_name_field_path must be provided for the template name.")
        # Version is now optional, so no validation needed for version sources.
        # if not self.static_version and not self.input_version_field_path:
        #     raise ValueError("Either static_version or input_version_field_path must be provided.")
        return self

class PromptTemplateLoadEntry(BaseNodeConfig):
    """
    Defines a single prompt template loading operation within the node's config.
    """
    path_config: PromptTemplatePathConfig = Field(
        ..., description="Configuration for resolving the template name and version."
    )
    output_key_name: Optional[str] = Field(
        None,
        description="Optional key name for the loaded template in the output dictionary. Defaults to the resolved template name."
    )

class LoadPromptTemplatesConfig(BaseNodeConfig):
    """
    Configuration schema for the enhanced LoadPromptTemplatesNode.
    Allows loading multiple prompt templates based on static or dynamic paths.
    """
    load_entries: List[PromptTemplateLoadEntry] = Field(
        ...,
        min_length=1,
        description="List of configurations, each defining a prompt template to load."
    )

# --- Input Schema ---
# Now dynamic, as name/version come from config + input data paths
# class PromptTemplateLoaderInput(DynamicSchema):
#     """
#     Input schema for the PromptTemplateLoaderNode.
#     Specifies the name and version of the prompt template to load.
#     """
#     template_name: str = Field(
#         ...,
#         description="The name of the Prompt Template to load."
#     )
#     template_version: str = Field(
#         ...,
#         description="The version of the Prompt Template to load."
#     )

# --- Output Schema ---

class LoadedPromptTemplateData(BaseSchema):
    """
    Represents the data loaded for a single prompt template.
    """
    template: Optional[str] = Field(None, description="The template content string.")
    input_variables: Optional[Dict[str, Any]] = Field(None, description="Dictionary of input variable names and optional default values.")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Associated metadata.")
    id: Optional[str] = Field(None, description="The UUID of the template.")

class LoadPromptTemplatesOutput(DynamicSchema):
    """
    Output schema for the LoadPromptTemplatesNode.
    Contains a dictionary of successfully loaded templates and a list of errors.
    """
    loaded_templates: Dict[str, LoadedPromptTemplateData] = Field(
        default_factory=dict,
        description="Dictionary where keys are output_key_names (or template names) and values are the loaded template data."
    )
    load_errors: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of errors encountered during loading attempts. Each entry contains details about the failure."
    )


# --- Node Definition ---

class PromptTemplateLoaderNode(BaseDynamicNode):
    """
    A workflow node that loads one or more Prompt Templates from the database.

    The specific templates to load, how to find their names/versions (statically
    or dynamically from input data), and how they are keyed in the output are
    defined in the node's configuration (`LoadPromptTemplatesConfig`).
    """
    node_name: ClassVar[str] = "load_prompt_templates" # Renamed for clarity
    node_version: ClassVar[str] = "0.2.0" # Version bump for major refactor
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.PRODUCTION
    # Ineriting input / output dynamic schemas from base class!
    # input_schema_cls: Type[DynamicSchema] = DynamicSchema # Input is now generic
    output_schema_cls: ClassVar[Type[LoadPromptTemplatesOutput]] = LoadPromptTemplatesOutput
    config_schema_cls: ClassVar[Type[LoadPromptTemplatesConfig]] = LoadPromptTemplatesConfig
    config: LoadPromptTemplatesConfig # Instance of the config

    async def process(
        self,
        input_data: DynamicSchema, # Input is now dynamic
        runtime_config: Optional[Dict[str, Any]] = None,
        *args: Any,
        **kwargs: Any
    ) -> LoadPromptTemplatesOutput:
        """
        Loads multiple prompt templates based on the node's configuration.

        Args:
            input_data: The dynamic input data potentially containing values for
                        template name/version resolution.
            runtime_config: The runtime configuration dictionary.
            *args: Additional positional arguments (unused).
            **kwargs: Additional keyword arguments (unused).

        Returns:
            An instance of LoadPromptTemplatesOutput containing loaded templates
            and any errors encountered.
        """
        self.logger.debug(f"Executing {self.node_name} v{self.node_version}")

        # --- 1. Extract Context & Input Dict ---
        if not runtime_config:
            self.logger.error("Missing runtime_config.")
            return self.output_schema_cls(load_errors=[{"error": "Missing runtime_config"}])

        configurable_config = runtime_config.get("configurable", runtime_config)
        app_context: Optional[Dict[str, Any]] = configurable_config.get(APPLICATION_CONTEXT_KEY)
        ext_context: Optional[ExternalContextManager] = configurable_config.get(EXTERNAL_CONTEXT_MANAGER_KEY)

        if not app_context or not ext_context:
            missing_keys = [k for k, v in [(APPLICATION_CONTEXT_KEY, app_context), (EXTERNAL_CONTEXT_MANAGER_KEY, ext_context)] if not v]
            error_msg = f"Missing required keys in runtime_config: {', '.join(missing_keys)}"
            self.logger.error(error_msg)
            return self.output_schema_cls(load_errors=[{"error": error_msg}])

        user: Optional[User] = app_context.get("user")
        run_job: Optional[WorkflowRunJobCreate] = app_context.get("workflow_run_job")

        if not user or not run_job:
            missing_ctx = [k for k, v in [("user", user), ("workflow_run_job", run_job)] if not v]
            error_msg = f"Missing required data in application_context: {', '.join(missing_ctx)}"
            self.logger.error(error_msg)
            return self.output_schema_cls(load_errors=[{"error": error_msg}])

        org_id = run_job.owner_org_id
        input_dict = input_data.model_dump(mode='json') if isinstance(input_data, DynamicSchema) else input_data
        prompt_template_dao: wf_crud.PromptTemplateDAO = ext_context.daos.prompt_template

        # --- 2. Process Load Entries ---
        loaded_templates_dict: Dict[str, LoadedPromptTemplateData] = {}
        errors_list: List[Dict[str, Any]] = []

        async with get_async_db_as_manager() as db:
            for i, entry in enumerate(self.config.load_entries):
                entry_id = f"entry_{i}" # For logging/error context
                resolved_name: Optional[str] = None
                resolved_version: Optional[str] = None
                output_key: Optional[str] = entry.output_key_name

                try:
                    # --- 2a. Resolve Name and Version ---
                    resolved_name, resolved_version, resolution_error = _resolve_template_path(
                        static_name=entry.path_config.static_name,
                        static_version=entry.path_config.static_version,
                        input_name_field_path=entry.path_config.input_name_field_path,
                        input_version_field_path=entry.path_config.input_version_field_path,
                        input_data=input_dict
                    )
                    # print(f"Resolved name: {resolved_name}, version: {resolved_version}, error: {resolution_error}")
                    # import ipdb; ipdb.set_trace()

                    if resolution_error:
                        self.logger.warning(f"[{entry_id}] Path resolution failed: {resolution_error}")
                        errors_list.append({
                            "entry_index": i,
                            "config": entry.model_dump(),
                            "error": f"Path resolution failed: {resolution_error}",
                            "output_key": output_key,
                        })
                        continue # Skip to next entry

                    # This check should be redundant if _resolve_template_path is correct, but safety first
                    if not resolved_name:
                        unknown_error = "Unknown error during path resolution."
                        self.logger.error(f"[{entry_id}] Resolved name is None despite no error from _resolve_template_path.")
                        errors_list.append({
                            "entry_index": i,
                            "config": entry.model_dump(),
                            "error": unknown_error,
                            "output_key": output_key,
                        })
                        continue
                        
                    # --- 2b. Determine Output Key ---
                    output_key = output_key or resolved_name
                    self.logger.info(f"[{entry_id}] Attempting to load template '{resolved_name}' v'{resolved_version}' for org '{org_id}' into output key '{output_key}'.")

                    # --- 2c. Load from DB ---
                    # Search for templates matching name/version with appropriate visibility settings
                    # This allows finding org-specific templates as well as public/system templates
                    templates = await prompt_template_dao.search_by_name_version(
                        db=db,
                        name=resolved_name,
                        version=resolved_version,
                        owner_org_id=org_id,
                        include_public=True,  # Include public templates
                        include_system_entities=False,  # Include system templates
                        include_public_system_entities=True,  # Include public system templates
                        is_superuser=user.is_superuser  # Default to non-superuser access
                    )
                    # print(f"Found {len(templates)} templates matching '{resolved_name}' v'{resolved_version}'")
                    # print(f"name ; version: {resolved_name} ; {resolved_version}")
                    # import ipdb; ipdb.set_trace()
                    
                    # Use the first matching template if any were found
                    prompt_template = templates[0] if templates else None

                    if prompt_template:
                        # --- 2d. Populate Output Dict --- 
                        loaded_data = LoadedPromptTemplateData(
                            template=prompt_template.template_content,
                            input_variables=prompt_template.input_variables,
                            metadata={
                                "is_system_entity": prompt_template.is_system_entity,
                                "name": prompt_template.name,
                                "version": prompt_template.version,
                                "description": prompt_template.description,
                                "owner_org_id": str(prompt_template.owner_org_id) if prompt_template.owner_org_id else None,
                            },
                            id=str(prompt_template.id)
                        )
                        loaded_templates_dict[output_key] = loaded_data
                        self.logger.info(f"[{entry_id}] Successfully loaded template '{resolved_name}' v'{resolved_version}' (ID: {prompt_template.id}) into key '{output_key}'.")
                    else:
                        not_found_error = f"Template '{resolved_name}' version '{resolved_version}' not found for org '{org_id}' or as a system template."
                        self.logger.warning(f"[{entry_id}] {not_found_error}")
                        errors_list.append({
                            "entry_index": i,
                            "config": entry.model_dump(),
                            "resolved_name": resolved_name,
                            "resolved_version": resolved_version,
                            "output_key": output_key,
                            "error": not_found_error
                        })

                except Exception as e:
                    self.logger.error(f"[{entry_id}] Unexpected error processing entry: {e}", exc_info=True)
                    errors_list.append({
                        "entry_index": i,
                        "config": entry.model_dump(),
                        "resolved_name": resolved_name, # May be None if error happened early
                        "resolved_version": resolved_version,
                        "output_key": output_key,
                        "error": f"Unexpected error: {str(e)}"
                    })

        # --- 3. Construct Final Output ---
        output = self.output_schema_cls(
            loaded_templates=loaded_templates_dict,
            load_errors=errors_list
        )
        return output
