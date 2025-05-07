"""
Prompt Constructor Node.

This module provides a flexible prompt construction node that can fill templates
with variables from input data and configuration. It can use statically defined
templates or load them dynamically from the database.
"""
from collections import defaultdict
import json
from typing import Any, ClassVar, Dict, List, Optional, Type, Union
import re
from pydantic import Field, model_validator, BaseModel
# Internal dependencies
from kiwi_app.workflow_app.constants import LaunchStatus
from kiwi_app.workflow_app import crud as wf_crud
from db.session import get_async_db_as_manager # For database access

from global_utils.utils import datetime_now_utc

# Base node/schema types and helpers
from workflow_service.config.constants import (
    OBJECT_PATH_REFERENCE_DELIMITER,
    APPLICATION_CONTEXT_KEY,
    EXTERNAL_CONTEXT_MANAGER_KEY
)
from workflow_service.registry.nodes.core.base import BaseSchema
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema, BaseDynamicNode

from typing import Any, Dict, Optional, Type, ClassVar, Union, List, Tuple

from pydantic import Field, model_validator

# Internal dependencies
from kiwi_app.workflow_app.constants import LaunchStatus
from kiwi_app.workflow_app import crud as wf_crud
from db.session import get_async_db_as_manager # For database access
from global_config.logger import get_prefect_or_regular_python_logger
# Import helper from customer_data for nested object retrieval
# from workflow_service.registry.nodes.db.customer_data import _get_nested_obj 

# Base node/schema types
from workflow_service.registry.schemas.base import BaseSchema
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema, BaseDynamicNode
from workflow_service.config.constants import (
    APPLICATION_CONTEXT_KEY,
    EXTERNAL_CONTEXT_MANAGER_KEY
)

# --- Type Aliases ---
PromptConstructOptions = Dict[str, str] # Type alias for clarity: maps variable_name -> input_data_path


# --- Helper Function for Path Resolution ---

SPECIAL_VAR_MAPPING = {
    "$current_date": lambda: datetime_now_utc().strftime("%Y-%m-%d"),
    "$current_datetime": lambda: datetime_now_utc().strftime("%Y-%m-%d %H:%M:%S"),
}


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
    logger = get_prefect_or_regular_python_logger(__name__)
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
    logger = get_prefect_or_regular_python_logger(__name__)
    resolved_name: Optional[str] = None
    resolved_version: Optional[str] = None
    error_message: Optional[str] = None

    # Resolve Name
    if input_name_field_path:
        name_val, found = _get_nested_obj(input_data, input_name_field_path)
        if found and isinstance(name_val, str):
            resolved_name = name_val
            logger.debug(f"Resolved template name '{resolved_name}' from input path '{input_name_field_path}'.")
        elif found:
            error_message = f"Input field '{input_name_field_path}' for template name found but is not a string (type: {type(name_val)})."
            logger.warning(error_message)
            # Continue to static fallback if defined
            if static_name:
                resolved_name = static_name
                logger.debug(f"Using static template name '{resolved_name}' as fallback.")
                error_message = None # Clear error as we have a fallback
            else:
                 return None, None, error_message # Fatal if no static fallback
        else: # Not found
            logger.debug(f"Input field '{input_name_field_path}' for template name not found.")
            if static_name:
                resolved_name = static_name
                logger.debug(f"Using static template name '{resolved_name}' as fallback.")
            else:
                error_message = f"Template name resolution failed: Input field '{input_name_field_path}' not found and no static_name provided."
                logger.warning(error_message)
                return None, None, error_message
    elif static_name:
        resolved_name = static_name
        logger.debug(f"Using static template name '{resolved_name}'.")
    else:
        error_message = "Template name resolution failed: Neither input_name_field_path nor static_name provided."
        logger.error(error_message)
        return None, None, error_message

    # Resolve Version
    if input_version_field_path:
        version_val, found = _get_nested_obj(input_data, input_version_field_path)
        if found and isinstance(version_val, str):
            resolved_version = version_val
            logger.debug(f"Resolved template version '{resolved_version}' from input path '{input_version_field_path}'.")
        elif found:
            # If found but wrong type, still try static fallback if version IS required implicitly by static_version being set
            error_message = f"Input field '{input_version_field_path}' for template version found but is not a string (type: {type(version_val)})."
            logger.warning(error_message)
            if static_version:
                resolved_version = static_version
                logger.debug(f"Using static template version '{resolved_version}' as fallback.")
                error_message = None
            else:
                 # If no static fallback, and input was provided but invalid, it IS an error.
                 return resolved_name, None, error_message 
        else: # Not found via input path
            logger.debug(f"Input field '{input_version_field_path}' for template version not found.")
            if static_version:
                resolved_version = static_version
                logger.debug(f"Using static template version '{resolved_version}' as fallback.")
            # If input path was specified but not found, AND no static version exists, treat as resolvable to None (version optional)
            # else: # No static version, input path specified but not found -> version is None
            #    resolved_version = None 
            #    logger.debug("No static version and input path not found, resolving version to None.")
    elif static_version:
        resolved_version = static_version
        logger.debug(f"Using static template version '{resolved_version}'.")
    # If neither input path nor static version was provided, version resolves to None cleanly.
    else:
        resolved_version = None 
        logger.debug("Neither static_version nor input_version_field_path provided, resolving version to None.")
        error_message = None # Not an error if version is optional

    # Final check: Name must always be resolved. Version is optional.
    if resolved_name:
        return resolved_name, resolved_version, None # Return None for error if successful
    else:
        # This case should be covered by name resolution logic, but safeguard.
        final_error = error_message or "Name resolution failed for unknown reason."
        logger.error(f"Final resolution check failed for name: {final_error}")
        return None, None, final_error


# --- Configuration Schemas ---

class PromptTemplatePathConfig(BaseSchema):
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


# --- Configuration Schemas ---

class PromptTemplateLoadEntryConfig(BaseSchema):
    """
    Configuration for dynamically loading a single prompt template.
    Mirroring PromptTemplateLoadEntry from the loader node, but just the config part.
    """
    path_config: PromptTemplatePathConfig = Field(
        ..., description="Configuration for resolving the template name and version."
    )
    # output_key_name is not needed here, the key is the template ID in the main config dict

class PromptTemplateDefinition(BaseSchema):
    """
    Defines a single prompt template, either statically or via dynamic loading.
    Allows specifying custom paths within the input data to source variable values.
    """
    id: str = Field(..., description="Unique identifier for this prompt definition within the node's config. Used as the output field name for the constructed prompt.")

    # Option 1: Define template statically
    template: Optional[str] = Field(None, description="Static template string. Provide this OR template_load_config.")
    variables: Dict[str, Optional[Any]] = Field(
        default_factory=dict,
        description="Static definition of variables and their default values/overrides for this template. These can supplement or override variables loaded dynamically."
    )
    construct_options: Optional[PromptConstructOptions] = Field(
        None,
        description="Optional mapping of variable names to specific dot-notation paths in the input data. Overrides global construct options."
    )

    # Option 2: Load template dynamically
    template_load_config: Optional[PromptTemplateLoadEntryConfig] = Field(
        None,
        description="Configuration to load the template from DB. Provide this OR static template content."
    )

    # Internal fields to store loaded data (not part of config schema)
    _loaded_template: Optional[str] = None
    _loaded_variables: Optional[Dict[str, Any]] = None
    _load_error: Optional[Dict[str, Any]] = None

    @model_validator(mode='after')
    def check_template_source(self) -> 'PromptTemplateDefinition':
        """Ensures that either a static template or load config is provided."""
        if self.template is None and self.template_load_config is None:
            raise ValueError(f"PromptTemplateDefinition '{self.id}': Must provide either 'template' or 'template_load_config'.")
        if self.template is not None and self.template_load_config is not None:
            raise ValueError(f"PromptTemplateDefinition '{self.id}': Cannot provide both 'template' and 'template_load_config'.")
        return self

class PromptConstructorConfig(BaseSchema):
    """
    Configuration schema for the enhanced PromptConstructorNode.
    Allows defining multiple prompt templates, either statically or by loading them.
    Supports global and template-specific variable sourcing from input data paths.
    """
    prompt_templates: Dict[str, PromptTemplateDefinition] = Field(
        ...,
        min_length=1,
        description="Dictionary of prompt templates definitions, keyed by a unique identifier used internally and potentially for output."
    )
    global_construct_options: Optional[PromptConstructOptions] = Field(
        None,
        description="Optional global mapping of variable names to dot-notation paths in the input data. Used as a fallback if template-specific options are not defined or don't contain the variable."
    )

class PromptConstructorOutput(DynamicSchema):
    """
    Output schema for the PromptConstructorNode.
    """
    prompt_template_errors: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="List of dictionaries containing template IDs and their corresponding load errors."
    )

class PromptConstructorNode(BaseDynamicNode):
    """
    Prompt Constructor Node that fills templates with variables.
    
    This node takes input data and configuration to construct prompts based on templates.
    Templates can be defined statically within the configuration or loaded dynamically
    from the Prompt Template database.

    It supports global variable replacement across all templates or template-specific
    variable replacement using the '::' delimiter in the variable name (e.g., `template_id::variable_name`).
    
    The node can construct multiple prompts simultaneously based on the `prompt_templates`
    configuration. The constructed prompts are output as fields matching the `id`
    defined in each `PromptTemplateDefinition`. Potential loading errors can also be included
    in the output if configured in the `dynamic_output_schema`.
    """
    node_name: ClassVar[str] = "prompt_constructor"
    node_version: ClassVar[str] = "0.2.0" # Version bump for merged functionality
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.PRODUCTION # Promoted from DEV
    
    # Ineriting input / output dynamic schemas from base class!
    # input_schema_cls: ClassVar[Type[DynamicSchema]] = DynamicSchema
    # output_schema_cls: ClassVar[Type[DynamicSchema]] = DynamicSchema
    config_schema_cls: ClassVar[Type[PromptConstructorConfig]] = PromptConstructorConfig
    
    # Default delimiter for template-specific variable names
    DELIMITER: ClassVar[str] = OBJECT_PATH_REFERENCE_DELIMITER

    # Instance params
    config: PromptConstructorConfig

    async def _load_dynamic_templates(
        self,
        input_dict: Dict[str, Any],
        runtime_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Loads templates configured with `template_load_config`.

        Mutates the `self.config.prompt_templates` items by populating
        `_loaded_template`, `_loaded_variables`, and `_load_error`.

        Args:
            input_dict: The node's input data dictionary.
            runtime_config: The runtime configuration dictionary.

        Returns:
            A list of error dictionaries encountered during loading.
        """
        load_errors: List[Dict[str, Any]] = []

        # --- 1. Extract Context ---
        # Similar context extraction as in PromptTemplateLoaderNode
        configurable_config = runtime_config.get("configurable", runtime_config)
        app_context: Optional[Dict[str, Any]] = configurable_config.get(APPLICATION_CONTEXT_KEY)
        ext_context = configurable_config.get(EXTERNAL_CONTEXT_MANAGER_KEY)

        if not app_context or not ext_context:
            missing_keys = [k for k, v in [(APPLICATION_CONTEXT_KEY, app_context), (EXTERNAL_CONTEXT_MANAGER_KEY, ext_context)] if not v]
            error_msg = f"Missing required keys in runtime_config for dynamic loading: {', '.join(missing_keys)}"
            self.error(error_msg)
            # Store a general error? This affects ALL dynamic loads.
            # For now, just log and dynamic loads will fail individually below.
            # Alternatively, append one error and return early. Let's return early.
            load_errors.append({"error": error_msg, "scope": "global_context"})
            return load_errors

        user = app_context.get("user")
        run_job = app_context.get("workflow_run_job")

        if not user or not run_job:
            missing_ctx = [k for k, v in [("user", user), ("workflow_run_job", run_job)] if not v]
            error_msg = f"Missing required data in application_context for dynamic loading: {', '.join(missing_ctx)}"
            self.error(error_msg)
            load_errors.append({"error": error_msg, "scope": "application_context"})
            return load_errors

        org_id = run_job.owner_org_id
        prompt_template_dao: wf_crud.PromptTemplateDAO = ext_context.daos.prompt_template

        # --- 2. Iterate and Load ---
        async with get_async_db_as_manager() as db:
            for template_id, template_def in self.config.prompt_templates.items():
                if not template_def.template_load_config:
                    continue # Skip statically defined templates

                entry_config = template_def.template_load_config
                resolved_name: Optional[str] = None
                resolved_version: Optional[str] = None

                try:
                    # --- 2a. Resolve Name and Version ---
                    resolved_name, resolved_version, resolution_error = _resolve_template_path(
                        static_name=entry_config.path_config.static_name,
                        static_version=entry_config.path_config.static_version,
                        input_name_field_path=entry_config.path_config.input_name_field_path,
                        input_version_field_path=entry_config.path_config.input_version_field_path,
                        input_data=input_dict
                    )

                    if resolution_error:
                        self.warning(f"Template '{template_id}': Path resolution failed: {resolution_error}")
                        err_details = {
                            "template_id": template_id,
                            "config": entry_config.model_dump(),
                            "error": f"Path resolution failed: {resolution_error}",
                        }
                        load_errors.append(err_details)
                        template_def._load_error = err_details # Store error on the object
                        continue # Skip to next template

                    if not resolved_name: # Should be caught by resolution_error, but safety first
                        unknown_error = "Unknown error during path resolution (name is None)."
                        self.error(f"Template '{template_id}': {unknown_error}")
                        err_details = {
                            "template_id": template_id, "config": entry_config.model_dump(), "error": unknown_error,
                        }
                        load_errors.append(err_details)
                        template_def._load_error = err_details
                        continue

                    self.info(f"Template '{template_id}': Attempting to load '{resolved_name}' v'{resolved_version}' for org '{org_id}'.")

                    # --- 2b. Load from DB ---
                    templates_found = await prompt_template_dao.search_by_name_version(
                        db=db, name=resolved_name, version=resolved_version, owner_org_id=org_id,
                        include_public=True, include_system_entities=False, include_public_system_entities=True,
                        is_superuser=user.is_superuser
                    )
                    db_template = None
                    if not resolved_version:
                        try:
                            from packaging.version import parse as parse_version
                            sorted_versions = sorted(templates_found, key=lambda x: parse_version(x.version), reverse=True)
                            db_template = sorted_versions[0]
                        except Exception as e:
                            pass
                    
                    if not db_template:
                        db_template = templates_found[0] if templates_found else None

                    if db_template:
                        # --- 2c. Populate Internal Fields ---
                        template_def._loaded_template = db_template.template_content
                        template_def._loaded_variables = db_template.input_variables or {}
                        self.info(f"Template '{template_id}': Successfully loaded '{resolved_name}' v'{resolved_version}' (ID: {db_template.id}).")
                    else:
                        not_found_error = f"Template '{resolved_name}' version '{resolved_version}' not found for org '{org_id}' or as accessible system template."
                        self.warning(f"Template '{template_id}': {not_found_error}")
                        err_details = {
                            "template_id": template_id, "config": entry_config.model_dump(),
                            "resolved_name": resolved_name, "resolved_version": resolved_version,
                            "error": not_found_error
                        }
                        load_errors.append(err_details)
                        template_def._load_error = err_details

                except Exception as e:
                    self.error(f"Template '{template_id}': Unexpected error during loading: {e}", exc_info=True)
                    err_details = {
                        "template_id": template_id, "config": entry_config.model_dump(),
                        "resolved_name": resolved_name, "resolved_version": resolved_version,
                        "error": f"Unexpected error: {str(e)}"
                    }
                    load_errors.append(err_details)
                    template_def._load_error = err_details # Store error

        return load_errors


    async def process(
        self,
        input_data: DynamicSchema,
        runtime_config: Optional[Dict[str, Any]] = None,
        *args: Any,
        **kwargs: Any
        ) -> BaseModel: # Return the validated Pydantic model instance
        """
        Process input data, load dynamic templates if needed, resolve variable values
        using construct options and input data, and construct prompts.

        Variable Resolution Priority:
        1. Template-specific input key (e.g., `template_id::variable_name` in input_data).
        2. Template-specific `construct_options` path lookup in `input_data`.
        3. Global `construct_options` path lookup in `input_data`.
        4. Global input key (e.g., `variable_name` in `input_data`).
        5. Default value from the template definition (static or loaded).

        Args:
            input_data: Dynamic schema containing input variables based on node's dynamic_input_schema.
            runtime_config: The runtime configuration dictionary (required for dynamic loading).
            *args: Additional positional arguments (unused).
            **kwargs: Additional keyword arguments (unused).

        Returns:
            A validated Pydantic model instance based on the node's dynamic_output_schema,
            containing constructed prompts and potentially loading errors.
        """
        # Convert validated input_data (based on dynamic_input_schema) to dictionary for lookups.
        # This contains data mapped via edges or defined in the schema.
        input_dict = input_data if isinstance(input_data, dict) else input_data.model_dump(mode='json')

        # --- 1. Load Dynamic Templates ---
        needs_dynamic_loading = any(
            tpl.template_load_config for tpl in self.config.prompt_templates.values()
        )
        load_errors: List[Dict[str, Any]] = []
        if needs_dynamic_loading:
            if not runtime_config:
                 self.error("Runtime config is required for dynamic template loading but was not provided.")
                 load_errors.append({"error": "Missing runtime_config for dynamic loading", "scope": "global"})
                 for tpl_id, tpl_def in self.config.prompt_templates.items():
                      if tpl_def.template_load_config and not tpl_def._load_error:
                          tpl_def._load_error = {"template_id": tpl_id, "error": "Missing runtime_config"}
            else:
                # Pass the input_dict here for resolving template load paths
                load_errors = await self._load_dynamic_templates(input_dict, runtime_config)
        else:
             self.debug("No dynamic template loading configured for this node instance.")


        # --- 2. Prepare Final Templates and Variables ---
        final_templates: Dict[str, str] = {}
        initial_variables: Dict[str, Dict[str, Optional[Any]]] = {}

        for template_id, template_def in self.config.prompt_templates.items():
            if template_def._load_error:
                self.warning(f"Skipping template '{template_id}' due to load error: {template_def._load_error.get('error')}")
                continue

            current_template_content: Optional[str] = None
            current_variables_defaults: Dict[str, Optional[Any]] = {}

            if template_def.template_load_config:
                current_template_content = template_def._loaded_template
                current_variables_defaults = template_def._loaded_variables or {}
                current_variables_defaults.update(template_def.variables)
            else:
                current_template_content = template_def.template
                current_variables_defaults = template_def.variables.copy()

            if current_template_content is None:
                 self.error(f"Template content for '{template_id}' is None after processing static/dynamic paths. Skipping.")
                 load_errors.append({"template_id": template_id, "error": "Template content missing after load/static check."})
                 continue

            final_templates[template_id] = current_template_content
            initial_variables[template_id] = current_variables_defaults
            self.debug(f"Prepared template '{template_id}' with initial variables: {current_variables_defaults}")

        # --- 3. Resolve Variables and Construct Prompts ---
        constructed_prompts: Dict[str, str] = {}
        construction_errors: List[Dict[str, Any]] = []
        global_construct_options = self.config.global_construct_options or {}

        for template_id, template_str in final_templates.items():
            resolved_vars_for_template: Dict[str, Any] = {}
            template_def = self.config.prompt_templates[template_id]
            template_construct_options = template_def.construct_options or {}
            template_defaults = initial_variables.get(template_id, {})
            placeholders = set(re.findall(r'\{([^{}]+)\}', template_str))
            self.debug(f"Template '{template_id}' requires placeholders: {placeholders}")

            for var_name in placeholders:
                resolved_value: Any = None
                found_value: bool = False
                specific_input_key = f"{template_id}{self.DELIMITER}{var_name}"

                # Priority 1: Template-specific construct_options path
                # Lookup within the validated input_dict
                if var_name in template_construct_options:
                    path = template_construct_options[var_name]
                    value, found = _get_nested_obj(input_dict, path) # Search within the node's received input_dict
                    if found:
                        resolved_value = value
                        found_value = True
                        self.debug(f"Var '{var_name}' for template '{template_id}': Found via template construct_options path '{path}' in node input.")
                    else:
                        self.debug(f"Var '{var_name}' for template '{template_id}': Template construct_options path '{path}' not found in node input.")
 
                # Priority 2: Global construct_options path
                # Lookup within the validated input_dict
                if not found_value and var_name in global_construct_options:
                    path = global_construct_options[var_name]
                    value, found = _get_nested_obj(input_dict, path) # Search within the node's received input_dict
                    if found:
                        resolved_value = value
                        found_value = True
                        self.debug(f"Var '{var_name}' for template '{template_id}': Found via global construct_options path '{path}' in node input.")
                    else:
                        self.debug(f"Var '{var_name}' for template '{template_id}': Global construct_options path '{path}' not found in node input.")

                # Priority 3: Template-specific input key (template_id::var_name)
                # Check directly in the input_dict (which contains validated/mapped inputs)
                if not found_value and specific_input_key in input_dict and input_dict[specific_input_key] is not None:
                    resolved_value = input_dict[specific_input_key]
                    found_value = True
                    self.debug(f"Var '{var_name}' for template '{template_id}': Found via specific input key '{specific_input_key}' in node input.")
                
                # Priority 4: Global input key (var_name)
                # Check directly in the input_dict
                if not found_value and var_name in input_dict and input_dict[var_name] is not None:
                    resolved_value = input_dict[var_name]
                    found_value = True
                    self.debug(f"Var '{var_name}' for template '{template_id}': Found via global input key '{var_name}' in node input.")

                # Priority 5: Default value from template definition
                if not found_value and var_name in template_defaults:
                    resolved_value = template_defaults[var_name]
                    if resolved_value is not None:
                        found_value = True
                        self.debug(f"Var '{var_name}' for template '{template_id}': Using default value.")
                    else:
                        self.debug(f"Var '{var_name}' for template '{template_id}': Default value is None.")

                if found_value:
                    resolved_vars_for_template[var_name] = resolved_value

            # --- 4. Construct Single Prompt ---
            try:
                self.debug(f"Attempting construction for template ID '{template_id}' with resolved variables: {resolved_vars_for_template}")
                # IMPORTANT: Only add to constructed_prompts if successful
                constructed_prompts[template_id] = self._build_prompt_string(template_str, resolved_vars_for_template)
                self.debug(f"Successfully constructed prompt '{template_id}': {constructed_prompts[template_id]}")
            except ValueError as e:
                self.error(f"Error constructing prompt for template ID '{template_id}': {e}")
                missing_in_build = placeholders - set(resolved_vars_for_template.keys())
                err_detail = {
                    "template_id": template_id, "error": f"Prompt construction failed: {e}",
                    "resolved_variables": list(resolved_vars_for_template.keys()),
                    "missing_variables": list(missing_in_build),
                    "required_placeholders": list(placeholders)
                }
                construction_errors.append(err_detail)
                # Do NOT add to constructed_prompts if construction fails

        # --- 5. Prepare Output Dictionary for Validation ---
        output_data_for_validation: Dict[str, Any] = {}

        # Add successfully constructed prompts
        output_data_for_validation.update(constructed_prompts)

        # Combine load and construction errors
        all_errors = load_errors + construction_errors
        if all_errors:
            # Check if the output schema expects errors before adding
            if 'prompt_template_errors' in self.__class__.output_schema_cls.model_fields:
                output_data_for_validation['prompt_template_errors'] = all_errors
                self.info(f"Completed processing with {len(all_errors)} errors.")
            else:
                self.warning(f"Processing completed with {len(all_errors)} errors, but 'prompt_template_errors' field not in output schema. Errors: {all_errors}")

        elif 'prompt_template_errors' in self.__class__.output_schema_cls.model_fields:
             # Add empty list if the field exists and there are no errors
            output_data_for_validation['prompt_template_errors'] = []
            self.info("Completed processing successfully with no errors.")
        else:
            self.info("Completed processing successfully.")

        # Validate and return the Pydantic model instance.
        # Pydantic will raise ValidationError if required fields (defined in dynamic_output_schema)
        # are missing from output_data_for_validation (because they failed construction).
        # This is the desired behavior - the node run should fail if required outputs aren't produced.
        try:
            # NOTE: this works because BaseSchema ignores additional provided fields!
            validated_output = self.__class__.output_schema_cls.model_validate(output_data_for_validation)
            return validated_output
        except Exception as e:
            self.error(f"Output validation failed: {e}. Data: {output_data_for_validation}", exc_info=True)
            raise # Re-raise the validation error to fail the node execution

    def _build_prompt_string(self, template: str, variables: Dict[str, Any]) -> str:
        """
        Build a prompt string by filling a template with variables.
        Handles missing required variables.

        Args:
            template: The prompt template string with placeholders like {variable}.
            variables: Dictionary of variables to fill the template.

        Returns:
            The constructed prompt string.

        Raises:
            ValueError: If a placeholder in the template is not found in the variables dictionary
                        (and the variable value is not None, as None might be acceptable in some templates).
                        Or if the variable value is None when the template expects a value.
        """
        # Find all placeholders in the template (e.g., {var1}, {user_name})
        placeholders = set(re.findall(r'\{([^{}]+)\}', template))

        # Check if all placeholders have corresponding variables provided
        # Allow None values explicitly passed in `variables` dict. format() handles None correctly by default (prints 'None').
        # If a placeholder variable is completely missing from the dict, that's an error.
        missing_vars = placeholders - set(variables.keys())
        if missing_vars:
            # Raise an error indicating which variables are missing
            raise ValueError(f"Missing required variables for template: {missing_vars}. Provided variables: {list(variables.keys())}")

        # Check for placeholders where the resolved value is None, which might be invalid depending on the template usage downstream.
        # For now, we allow None and let format() handle it. Stricter checking could be added here if needed.
        # vars_with_none = {k for k, v in variables.items() if k in placeholders and v is None}
        # if vars_with_none:
        #     self.warning(f"Variables resolved to None for template placeholders: {vars_with_none}")


        # Use string formatting to replace placeholders with variable values
        try:
            # NOTE: this assumes that no complex / nested access is required for dict/list variables within the prompt!
            resolved_variables = {}
            for k, v in variables.items():
                resolved_var = (json.dumps(v) if isinstance(v, (dict, list)) else v)
                if isinstance(v, str) and v in SPECIAL_VAR_MAPPING:
                    resolved_var = SPECIAL_VAR_MAPPING[v]()
                resolved_variables[k] = resolved_var
            return template.format(**resolved_variables)
        except KeyError as e:
            # This should theoretically be caught by the missing_vars check above, but keep as a safeguard.
             raise ValueError(f"Template formatting failed. Missing key: {e}. Placeholders: {placeholders}, Provided: {list(variables.keys())}") from e
        except Exception as e:
             # Catch other potential formatting errors
             raise ValueError(f"Template formatting failed unexpectedly: {e}") from e
