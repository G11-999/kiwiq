"""
Node for performing LinkedIn scraping tasks using the scraper_service client.

This node allows configuring various LinkedIn scraping jobs (like fetching profiles,
posts, comments, reactions, etc.) defined by the scraper_service. It interacts
with the scraper_service clients (RapidAPIClient, LinkedinPostFetcher) and
calculates the estimated credit cost before execution.
"""

import asyncio
import traceback
from typing import Any, Dict, List, Optional, Union, Type, ClassVar, Tuple, Set

from global_config.logger import get_prefect_or_regular_python_logger
from pydantic import Field, model_validator, BaseModel, ValidationError

# Node framework imports
from kiwi_app.workflow_app.constants import LaunchStatus
from kiwi_app.workflow_app.schemas import WorkflowRunJobCreate
from workflow_service.config.constants import APPLICATION_CONTEXT_KEY, EXTERNAL_CONTEXT_MANAGER_KEY
from workflow_service.registry.schemas.base import BaseSchema, BaseNodeConfig
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema, BaseDynamicNode

# Scraping service imports
from services.scraper_service.client.schemas.job_config_schema import (
    ScrapingRequest,
    JobTypeEnum,
    EntityTypeEnum,
    YesNoEnum,
)
from services.scraper_service.scraper_entrypoint import execute_scraper_job
from services.scraper_service.settings import rapid_api_settings # For defaults maybe


# --- Helper Function (adapted from customer_data.py) ---

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
    logger = get_prefect_or_regular_python_logger(f"{__name__}")
    current = data
    parts = field_path.split('.') if field_path else []

    if not field_path:
        # If the path is empty, return the whole data structure
        return data, True

    for part in parts:
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                logger.debug(f"Key '{part}' not found in dict during path traversal: {field_path}")
                return None, False # Key not found in dict
        elif isinstance(current, list):
            try:
                idx = int(part)
                # Check bounds for list index
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    logger.debug(f"Index '{idx}' out of bounds for list during path traversal: {field_path}")
                    return None, False # Index out of bounds
            except (ValueError, TypeError):
                # Invalid index format for list
                logger.debug(f"Invalid index '{part}' for list during path traversal: {field_path}")
                return None, False
        else:
            # Cannot navigate further (e.g., encountered a primitive type)
            logger.debug(f"Cannot navigate further at part '{part}' (value is {type(current)}) during path traversal: {field_path}")
            return None, False

    return current, True

# --- Configuration Schemas ---

class InputSource(BaseSchema):
    """
    Specifies the source for a parameter value, either static or dynamic from input.
    """
    static_value: Optional[Any] = Field(
        None, description="A fixed, static value for the parameter."
    )
    input_field_path: Optional[str] = Field(
        None, description="Dot-notation path in the node's input data to retrieve the parameter value."
    )
    expand_list: bool = Field(
        False,
        description="If input_field_path points to a list, generate one job per item in the list. "
                    "Only one InputSource per JobDefinition can have this set to True."
    )

    @model_validator(mode='after')
    def check_source(self) -> 'InputSource':
        """Ensures exactly one source (static or dynamic) is provided."""
        if self.static_value is not None and self.input_field_path is not None:
            raise ValueError("Provide only one of static_value or input_field_path.")
        if self.static_value is None and self.input_field_path is None:
            raise ValueError("One of static_value or input_field_path must be provided.")
        if self.expand_list and self.static_value is not None:
            raise ValueError("expand_list can only be True when using input_field_path.")
        # Ensure static_value is serializable or a known type if needed downstream
        # (Pydantic handles basic types, but enums might need use_enum_values=True elsewhere)
        return self


class JobDefinition(BaseNodeConfig):
    """
    Defines how to construct the parameters for one or more ScrapingRequest jobs.
    Allows specifying static values or retrieving values dynamically from the node's input data.
    Can trigger multiple jobs if one input source points to a list and has 'expand_list' set to True.
    """
    output_field_name: str = Field(
        ...,
        description="The field name in the output data where the result(s) for this job definition will be placed."
    )

    # --- Core Job Definition (Mimicking ScrapingRequest) ---
    job_type: InputSource = Field(
        ..., description="Source for the main job type (e.g., 'profile_info'). Must resolve to a JobTypeEnum value."
    )
    type: Optional[InputSource] = Field(
        None, description="Source for the entity type ('company' or 'person'). Required for profile/entity jobs. Must resolve to an EntityTypeEnum value."
    )

    # --- Job Flags (must align with job_type) ---
    # These flags are primarily used by the ScrapingRequest validator.
    # The node ensures the corresponding flag matches the resolved job_type.
    # Defaults are set to NO, override if this definition corresponds to that job type.
    profile_info: InputSource = Field(default_factory=lambda: InputSource(static_value=YesNoEnum.NO.value))
    entity_posts: InputSource = Field(default_factory=lambda: InputSource(static_value=YesNoEnum.NO.value))
    activity_comments: InputSource = Field(default_factory=lambda: InputSource(static_value=YesNoEnum.NO.value))
    activity_reactions: InputSource = Field(default_factory=lambda: InputSource(static_value=YesNoEnum.NO.value))
    search_post_by_keyword: InputSource = Field(default_factory=lambda: InputSource(static_value=YesNoEnum.NO.value))
    search_post_by_hashtag: InputSource = Field(default_factory=lambda: InputSource(static_value=YesNoEnum.NO.value))

    # --- Input Identifiers (Required based on job_type) ---
    url: Optional[InputSource] = Field(
        None, description="Source for the LinkedIn profile/entity URL. Overrides username/type if provided."
    )
    username: Optional[InputSource] = Field(
        None, description="Source for the LinkedIn username/profile ID."
    )
    keyword: Optional[InputSource] = Field(
        None, description="Source for the search keyword."
    )
    hashtag: Optional[InputSource] = Field(
        None, description="Source for the search hashtag (without '#')."
    )

    # --- Limits ---
    post_limit: Optional[InputSource] = Field(
        None, description=f"Source for the max posts limit. API default if not specified."
    )
    post_comments: InputSource = Field(
        default_factory=lambda: InputSource(static_value=YesNoEnum.NO.value),
        description="Source for whether to fetch comments."
    )
    comment_limit: Optional[InputSource] = Field(
        None, description=f"Source for max comments per post. Defaults to API setting ({rapid_api_settings.DEFAULT_COMMENT_LIMIT})."
    )
    post_reactions: InputSource = Field(
        default_factory=lambda: InputSource(static_value=YesNoEnum.NO.value),
        description="Source for whether to fetch reactions."
    )
    reaction_limit: Optional[InputSource] = Field(
        None, description=f"Source for max reactions per post. Defaults to API setting ({rapid_api_settings.DEFAULT_REACTION_LIMIT})."
    )

    @model_validator(mode='after')
    def check_expansion_and_output_field(self) -> 'JobDefinition':
        """
        Validates that at most one field uses 'expand_list' and output_field_name is valid.
        """
        expansion_count = 0
        # Iterate through fields checking for InputSource with expand_list=True
        for field_name, value in self:
            # Check if the field value is an InputSource instance (handling potential None values)
            if isinstance(value, InputSource) and value.expand_list:
                expansion_count += 1

        if expansion_count > 1:
            raise ValueError(f"JobDefinition for '{self.output_field_name}': Only one input field can have expand_list=True.")

        # Validate output_field_name (similar to LoadPathConfig)
        if self.output_field_name.startswith('_'):
            raise ValueError(f"output_field_name '{self.output_field_name}' cannot start with underscore (_) as it may conflict with Pydantic reserved fields.")

        return self

class LinkedInScrapingConfig(BaseNodeConfig):
    """Configuration schema for the LinkedInScrapingNode."""
    jobs: List[JobDefinition] = Field(
        ...,
        min_length=1,
        description="List of job definitions, each specifying how to configure and run one or more scraping tasks."
    )
    test_mode: bool = Field(
        False,
        description="If True, the node resolves and validates job configurations but does not execute them. "
                    "Instead, it outputs the validated ScrapingRequest configurations (as dicts) "
                    "in the corresponding output fields."
    )

class LinkedInScrapingOutput(BaseSchema):
    """
    Output schema for the LinkedInScrapingNode.
    Contains the scraping results (or list of results if expanded).
    Includes metadata about the execution.
    """
    # Internal tracking or metadata fields can be added here
    execution_summary: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Summary of jobs executed, keyed by output_field_name. Contains info like 'jobs_triggered', 'successful', 'failed'."
    )
    scraping_results: Dict[str, Any] = Field(
        default_factory=dict,
        description="Results from the scraping jobs, keyed by output_field_name. Contains info like 'jobs_triggered', 'successful', 'failed'."
    )


# --- LinkedIn Scraping Node ---

class LinkedInScrapingNode(BaseDynamicNode):
    """
    Node for executing LinkedIn scraping tasks via the scraper_service.

    Configures and triggers various scraping jobs (profile info, posts, search, etc.)
    based on static values or data dynamically retrieved from the node's input.
    Supports triggering multiple jobs from a single definition if an input field
    contains a list (e.g., scraping profiles for a list of usernames).
    Returns results from the scraping service as JSON data.

    In test_mode=True, it only generates and validates the job configurations without execution,
    outputting the configurations themselves.
    """
    node_name: ClassVar[str] = "linkedin_scraping"
    node_version: ClassVar[str] = "0.1.1" # Version bump for test_mode
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.PRODUCTION # Or appropriate status
    # BaseDynamicNode provides dynamic input/output schemas by default
    output_schema_cls: ClassVar[Type[LinkedInScrapingOutput]] = LinkedInScrapingOutput
    config_schema_cls: ClassVar[Type[LinkedInScrapingConfig]] = LinkedInScrapingConfig

    # --- Instance Variables ---
    config: LinkedInScrapingConfig # Instance of LinkedInScrapingConfig

    def _resolve_input_source(
        self,
        source: Optional[InputSource],
        input_dict: Dict[str, Any],
        field_name: str,
        iteration_item: Optional[Any] = None,
        is_expanding_field: bool = False
    ) -> Tuple[Any, bool, bool]:
        """
        Resolves the value from an InputSource configuration.

        Args:
            source: The InputSource object for the field.
            input_dict: The full input data dictionary for the node.
            field_name: The name of the field being resolved (for logging).
            iteration_item: The specific item from the list if this field is expanding.
            is_expanding_field: Flag indicating if this is the field triggering expansion.

        Returns:
            Tuple: (resolved_value, found_or_static, is_list_for_expansion)
                   - resolved_value: The final value (can be None).
                   - found_or_static: True if value came from static or found in input, False otherwise.
                   - is_list_for_expansion: True if the source uses expand_list and resolved to a list.
        """
        if source is None:
            return None, False, False # No source configured for this optional field

        if source.static_value is not None:
            return source.static_value, True, False # Static value provided

        if source.input_field_path:
            is_list_for_expansion = False
            if is_expanding_field:
                # If this is the field driving expansion, use the pre-resolved item for this iteration
                resolved_value = iteration_item
                found = True # Assumed true since we are iterating over it
            else:
                # Resolve from the main input_dict
                resolved_value, found = _get_nested_obj(input_dict, source.input_field_path)

            if found and source.expand_list:
                # Check if the *original* source path pointed to a list
                original_list_value, list_found = _get_nested_obj(input_dict, source.input_field_path)
                if list_found and isinstance(original_list_value, list):
                     is_list_for_expansion = True
                else:
                     # Log a warning if expand_list=True but the input wasn't a list
                     self.warning(f"Field '{field_name}' ({source.input_field_path}) has expand_list=True, but did not resolve to a list in input data.")


            if not found:
                self.warning(f"Input field path '{source.input_field_path}' for '{field_name}' not found in input data.")
                return None, False, False # Field path not found

            return resolved_value, True, is_list_for_expansion

        # Should be unreachable due to InputSource validation
        self.error(f"Invalid InputSource state for field '{field_name}'.")
        return None, False, False


    async def process(
        self,
        input_data: Union[DynamicSchema, Dict[str, Any]],
        runtime_config: Optional[Dict[str, Any]] = None,
        *args: Any,
        **kwargs: Any
    ) -> LinkedInScrapingOutput:
        """
        Generates ScrapingRequest configurations and executes them via execute_scraper_job.
        If test_mode is True, it validates configurations and outputs them instead of executing.

        Args:
            input_data: The input data potentially containing values for dynamic parameters.
            runtime_config: Runtime configuration (optional, currently unused by scraper).
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.

        Returns:
            LinkedInScrapingOutput: An object containing the results (or validated configs in test_mode)
                                   from the scraping jobs, organized by the 'output_field_name'
                                   from the config, along with execution metadata.
        """
        input_dict = input_data if isinstance(input_data, dict) else input_data.model_dump(mode='json')
        test_mode = self.config.test_mode

        all_tasks = []
        # Stores tasks in normal mode, validated configs or errors in test mode
        job_output_map: Dict[str, List[Union[asyncio.Task, Dict[str, Any]]]] = {}
        execution_summary: Dict[str, Dict[str, Any]] = {}

        self.info(f"LinkedIn Scraping Node processing. Test Mode: {test_mode}")

        for job_def in self.config.jobs:
            output_field = job_def.output_field_name
            job_output_map[output_field] = [] # Initialize list for results/configs/errors
            execution_summary[output_field] = {"jobs_triggered": 0, "successful": 0, "failed": 0, "errors": []}
            self.debug(f"Processing job definition for output field: {output_field}")

            expanding_field_name: Optional[str] = None
            expansion_list: List[Any] = [None] # Default: run once even if no expansion
            num_iterations = 1

            # 1. Identify the expanding field (if any) and get its list value
            for field_name, source in job_def:
                if isinstance(source, InputSource) and source.expand_list:
                    if source.input_field_path:
                        list_value, found = _get_nested_obj(input_dict, source.input_field_path)
                        if found and isinstance(list_value, list):
                            expanding_field_name = field_name
                            expansion_list = list_value
                            num_iterations = len(expansion_list)
                            if num_iterations == 0:
                                 self.warning(f"Expansion field '{field_name}' ({source.input_field_path}) resolved to an empty list for output '{output_field}'. No jobs will be triggered for this definition.")
                            break # Found the single expander
                        elif found:
                            self.warning(f"Expansion field '{field_name}' ({source.input_field_path}) has expand_list=True but did not resolve to a list for output '{output_field}'. Treating as single item.")
                            expanding_field_name = field_name
                            expansion_list = [list_value]
                            num_iterations = 1
                            break
                        else:
                            self.warning(f"Expansion field '{field_name}' ({source.input_field_path}) not found for output '{output_field}'. expand_list=True ignored. Will attempt single execution if possible.")
                            break
                    # No need to check static_value here, as expand_list=True requires input_field_path

            if expanding_field_name:
                self.debug(f"Found expanding field: {expanding_field_name} with {num_iterations} item(s)")
            
            # 2. Iterate and construct/validate parameters for each job
            for i in range(num_iterations):
                request_params: Dict[str, Any] = {}
                iteration_item = expansion_list[i] if expanding_field_name is not None else None
                is_valid_iteration = True

                # Resolve all fields
                for field_name, source_config in job_def:
                    if field_name == "output_field_name": continue
                    if isinstance(source_config, InputSource):
                        is_expanding = (field_name == expanding_field_name)
                        resolved_value, found_or_static, _ = self._resolve_input_source(
                            source_config, input_dict, field_name, iteration_item, is_expanding
                        )
                        if found_or_static:
                             request_params[field_name] = resolved_value
                        elif field_name in ["job_type"]: # Check strictly required fields
                             self.error(f"Required field '{field_name}' could not be resolved for job definition '{output_field}', iteration {i}. Skipping this job.")
                             is_valid_iteration = False
                             execution_summary[output_field]["errors"].append(f"Iteration {i}: Required field '{field_name}' could not be resolved.")
                             break

                if not is_valid_iteration:
                    job_output_map[output_field].append({"error": f"Failed to resolve required parameters for iteration {i}"})
                    execution_summary[output_field]["failed"] += 1
                    continue

                # Align job flags
                resolved_job_type = request_params.get("job_type")
                if resolved_job_type:
                    try:
                        job_type_enum = JobTypeEnum(resolved_job_type)
                        flag_name = job_type_enum.value
                        request_params[flag_name] = YesNoEnum.YES.value # Ensure correct flag is YES
                        # Ensure others are NO
                        for jt_enum in JobTypeEnum:
                             other_flag_name = jt_enum.value
                             if other_flag_name != flag_name:
                                  request_params[other_flag_name] = YesNoEnum.NO.value
                    except ValueError:
                         self.error(f"Resolved job_type '{resolved_job_type}' is not a valid JobTypeEnum value for output '{output_field}', iteration {i}. Skipping.")
                         is_valid_iteration = False
                         execution_summary[output_field]["errors"].append(f"Iteration {i}: Invalid job_type '{resolved_job_type}'.")

                if not is_valid_iteration:
                    job_output_map[output_field].append({"error": f"Invalid job_type '{resolved_job_type}' for iteration {i}"})
                    execution_summary[output_field]["failed"] += 1
                    continue

                # 3. Validate (and maybe create task or store config)
                try:
                    final_params = {k: v for k, v in request_params.items() if v is not None}
                    validated_request = ScrapingRequest.model_validate(final_params)
                    execution_summary[output_field]["jobs_triggered"] += 1 # Count potential job

                    if test_mode:
                        # Store the validated config dictionary
                        self.debug(f"[Test Mode] Validated config for '{output_field}_{i}': {validated_request.model_dump()}")
                        job_output_map[output_field].append(validated_request.model_dump(mode='json'))
                        execution_summary[output_field]["successful"] += 1 # Mark as successful validation
                    else:
                        # Create the async task for actual execution
                        task = asyncio.create_task(
                            execute_scraper_job(validated_request),
                            name=f"{output_field}_{i}"
                        )
                        all_tasks.append(task)
                        job_output_map[output_field].append(task) # Store task
                        # Success/failure counted after gather

                except ValidationError as e:
                    self.error(f"Validation failed for ScrapingRequest (output: {output_field}, iteration: {i}): {e}")
                    self.error(f"Parameters: {final_params}")
                    error_details = e.errors()
                    error_msg = f"Validation failed: {e}"
                    job_output_map[output_field].append({"error": error_msg, "details": error_details})
                    execution_summary[output_field]["failed"] += 1
                    # Add detailed validation errors if helpful
                    execution_summary[output_field]["errors"].append(f"Iteration {i}: Error {error_msg} Details: {error_details}")

                except Exception as e:
                    self.error(f"Unexpected error preparing job for {output_field}, iteration {i}: {e}", exc_info=True)
                    error_msg = f"Unexpected error preparing job: {e}"
                    job_output_map[output_field].append({"error": error_msg})
                    execution_summary[output_field]["failed"] += 1
                    execution_summary[output_field]["errors"].append(f"Iteration {i}: {error_msg}")


        # 4. Run tasks concurrently (only if not in test_mode)
        results = []
        if not test_mode and all_tasks:
            self.info(f"Executing {len(all_tasks)} scraping jobs concurrently...")
            results = await asyncio.gather(*all_tasks, return_exceptions=True)
            self.info("Scraping jobs execution finished.")
        elif test_mode:
             self.info("Test mode enabled. Skipping actual job execution.")

        # 5. Process results (or stored configs in test_mode) and map back to output fields
        output_data: Dict[str, Any] = {}
        task_index = 0 # Index into the 'results' list from asyncio.gather
        for job_def in self.config.jobs:
             output_field = job_def.output_field_name
             # This list contains Tasks in normal mode, dicts (configs/errors) in test mode
             placeholder_items = job_output_map[output_field]
             final_outputs_for_field = []

             for item in placeholder_items:
                 if test_mode:
                     # Item is either a validated config dict or an error dict
                     if isinstance(item, dict):
                         final_outputs_for_field.append(item)
                     else:
                         # Should not happen in test_mode
                         self.error(f"[Test Mode] Unexpected item type '{type(item)}' found for output '{output_field}'.")
                         final_outputs_for_field.append({"error": "Internal test mode error: Unexpected item type."})
                 else:
                     # Normal mode: Item is either a Task or an error dict (from pre-validation failure)
                     if isinstance(item, asyncio.Task):
                         if task_index < len(results):
                             result_or_exception = results[task_index]
                             if isinstance(result_or_exception, Exception):
                                 self.error(f"Scraping job '{item.get_name()}' failed: {result_or_exception}", exc_info=result_or_exception)
                                 error_detail = str(result_or_exception)
                                 # Attempt to get cleaner error if available
                                 if hasattr(result_or_exception, '__cause__') and isinstance(getattr(result_or_exception, '__cause__'), dict):
                                     error_detail = getattr(result_or_exception, '__cause__').get('error', error_detail)
                                 final_outputs_for_field.append({"error": f"Job execution failed: {error_detail}"})
                                 # We count triggered jobs earlier, now mark failure post-execution
                                 execution_summary[output_field]["failed"] += 1
                             elif isinstance(result_or_exception, dict) and "error" in result_or_exception:
                                 self.warning(f"Scraping job '{item.get_name()}' returned an error: {result_or_exception['error']}")
                                 final_outputs_for_field.append(result_or_exception)
                                 execution_summary[output_field]["failed"] += 1
                             else:
                                 # Successful result
                                 final_outputs_for_field.append(self._serialize_result(result_or_exception))
                                 execution_summary[output_field]["successful"] += 1 # Count success post-execution
                             task_index += 1
                         else:
                             self.error(f"Mismatch between tasks and results for '{output_field}'.")
                             final_outputs_for_field.append({"error": "Internal error processing results."})
                             execution_summary[output_field]["failed"] += 1 # Count as failed if result missing
                     elif isinstance(item, dict) and "error" in item:
                         # Error occurred before task creation (e.g., validation)
                         final_outputs_for_field.append(item)
                         # Failure already counted
                     else:
                         self.error(f"Unexpected item type in normal mode for '{output_field}': {type(item)}")
                         final_outputs_for_field.append({"error": "Internal error: Unexpected result item type."})

             # Assign results/configs to the output field.
             # Determine if the original intention was expansion
             expansion_intended = any(isinstance(s, InputSource) and s.expand_list for _, s in job_def)

             # Store as list if expansion was intended OR if more than one item exists (e.g., due to pre-run errors)
             # Store single item directly otherwise
             if expansion_intended or len(final_outputs_for_field) > 1:
                 output_data[output_field] = final_outputs_for_field
             elif len(final_outputs_for_field) == 1:
                 output_data[output_field] = final_outputs_for_field[0]
             else: # No jobs triggered (e.g., empty expansion list)
                 output_data[output_field] = [] # Represent no results as empty list

        # 6. Create output instance
        output_cls = self.__class__.output_schema_cls
        init_data = {
            "execution_summary": execution_summary,
            "scraping_results": output_data
        }

        try:
            output_instance = output_cls(**init_data)
        except ValidationError as ve:
             self.error(f"Output validation error for LinkedInScrapingNode: {ve}. Summary: {execution_summary}")
             fallback_data = {"execution_summary": execution_summary}
             for key, val in output_data.items():
                 if key not in fallback_data:
                     fallback_data[key] = {"error": f"Failed to serialize results/configs: {ve}"}
             return output_cls(**fallback_data)
        except Exception as e:
            self.error(f"Unexpected error during output instantiation: {e}", exc_info=True)
            fallback_data = {"execution_summary": execution_summary}
            return output_cls(**fallback_data)

        # Final summary logging
        for field_name, summary in execution_summary.items():
            self.info(f"Output field {field_name}: triggered={summary['jobs_triggered']}, successful={summary['successful']}, failed={summary['failed']}")
            if summary['errors']:
                self.warning(f"Errors for {field_name}: {summary['errors'][:5]}" + ("..." if len(summary['errors']) > 5 else ""))

        return output_instance

    def _serialize_result(self, result: Any) -> Any:
        """Converts potential Pydantic models in results to JSON-serializable dicts."""
        try:
            if isinstance(result, BaseModel):
                return result.model_dump(mode="json")
            elif isinstance(result, list):
                return [self._serialize_result(item) for item in result]
            # Assume other types (dict, str, int, etc.) are already serializable
            return result
        except Exception as e:
            self.error(f"Error serializing scraping result item: {e}")
            return {"error": f"Failed to serialize result item: {e}"}

