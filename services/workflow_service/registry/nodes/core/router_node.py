"""
Router node for conditional branching in workflows.

This module defines the RouterNode, which allows dynamic routing of workflow execution
based on simple equality conditions evaluated against the input data.
"""
import copy
from typing import Any, Dict, List, Optional, Type, ClassVar, Union, Tuple
from pydantic import Field, model_validator, BaseModel

from kiwi_app.workflow_app.constants import LaunchStatus
from workflow_service.registry.schemas.base import BaseSchema
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema, BaseDynamicNode, RouterSchema as BaseRouterSchema, DynamicRouterNode
from workflow_service.config.constants import TEMP_STATE_UPDATE_KEY, ROUTER_CHOICE_KEY, OBJECT_PATH_REFERENCE_DELIMITER


class RouterChoiceCondition(BaseSchema):
    """
    Defines a single condition for a routing choice.

    Specifies the target node ID, the path to the input field to check,
    and the value to compare against for equality.

    Attributes:
        choice_id (str): The ID of the node to route to if the condition matches.
                         This ID must be present in the parent RouterConfigSchema's `choices` list.
        input_path (str): The path to the field within the input data to evaluate.
                          Uses OBJECT_PATH_REFERENCE_DELIMITER for nesting (e.g., "field_a::nested_field").
        target_value (Any): The value to compare the input field's value against.
                            Equality comparison is performed.
    """
    choice_id: str = Field(
        ...,
        description="ID of the node to route to if this condition is met."
    )
    input_path: str = Field(
        ...,
        description=f"Path to the input field using '{OBJECT_PATH_REFERENCE_DELIMITER}' as delimiter (e.g., 'data::user::id')."
    )
    target_value: Any = Field(
        ...,
        description="The value to compare the input field against for equality."
    )

class RouterConfigSchema(BaseRouterSchema):
    """
    Configuration schema for the RouterNode.

    Inherits `choices` (list of all possible node IDs) and `allow_multiple`
    from BaseRouterSchema. Adds specific conditions for each choice.

    Attributes:
        choices (List[str]): Inherited. List of all possible destination node IDs.
        allow_multiple (bool): Inherited. If True, routes to all matching choices.
                               If False, routes only to the first matching choice.
        choices_with_conditions (List[RouterChoiceCondition]):
            List of conditions defining the routing logic. Each condition maps an
            input path and target value to a specific `choice_id`. Conditions are
            evaluated in the order they appear in this list.
    """
    choices_with_conditions: List[RouterChoiceCondition] = Field(
        ...,
        min_length=1,
        description="List of conditions evaluated in order to determine routing."
    )

    @model_validator(mode='after')
    def validate_choice_ids_exist(self) -> 'RouterConfigSchema':
        """
        Validates that all choice_ids in choices_with_conditions
        are present in the main 'choices' list.
        """
        available_choices = set(self.choices)
        for condition in self.choices_with_conditions:
            if condition.choice_id not in available_choices:
                raise ValueError(
                    f"Choice ID '{condition.choice_id}' in conditions is not present "
                    f"in the main 'choices' list: {self.choices}"
                )
        return self


def _get_nested_value(data: Dict[str, Any], path: str) -> Tuple[Any, bool]:
    """
    Retrieves a value from a nested dictionary using a path string.

    Args:
        data (Dict[str, Any]): The dictionary to navigate.
        path (str): The path string, using OBJECT_PATH_REFERENCE_DELIMITER as delimiter.

    Returns:
        Tuple[Any, bool]: A tuple containing the retrieved value and a boolean
                          indicating whether the path was successfully resolved.
                          If the path is invalid, returns (None, False).
    """
    keys = path.split(OBJECT_PATH_REFERENCE_DELIMITER)
    current_value = data
    try:
        for key in keys:
            if isinstance(current_value, dict):
                current_value = current_value[key]
            # TODO: Consider adding list index access if needed, e.g., "data::list_field::0"
            else:
                # Cannot navigate further if not a dictionary
                return None, False
        return current_value, True
    except (KeyError, TypeError, IndexError):
        # Path does not exist or is invalid for the structure
        return None, False


class RouterNode(DynamicRouterNode):
    """
    A dynamic router node that directs workflow execution based on input data conditions.

    This node evaluates simple equality conditions defined in its configuration
    against the dynamic input data. It can route to a single destination node
    (the first match) or multiple destination nodes (all matches) depending on
    the `allow_multiple` configuration setting.

    Input Schema: Dynamic (defined at runtime based on graph connections)
    Output Schema: Passes through the input data, adding routing information.
                   The output dictionary structure is dictated by the requirements
                   of the workflow execution engine (e.g., LangGraph), typically
                   containing keys like TEMP_STATE_UPDATE_KEY and ROUTER_CHOICE_KEY.
    Config Schema: RouterConfigSchema, defining possible choices, routing mode,
                   and specific conditions for each choice.
    """
    node_name: ClassVar[str] = "router_node"
    node_version: ClassVar[str] = "0.1.0"
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.PRODUCTION

    # Input schema is dynamic
    input_schema_cls: Type[DynamicSchema] = DynamicSchema
    # Output schema is also dynamic, effectively passing through input + routing info
    output_schema_cls: Type[DynamicSchema] = DynamicSchema
    config_schema_cls: Type[RouterConfigSchema] = RouterConfigSchema

    # Instance config, validated against config_schema_cls
    config: RouterConfigSchema

    def _prepare_input_data(self, input_data: Union[DynamicSchema, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Ensures the input data is represented as a dictionary for processing.

        Args:
            input_data: The input data, potentially a Pydantic model instance or a dict.

        Returns:
            A dictionary representation of the input data.
        """
        if isinstance(input_data, dict):
            # Return a copy to avoid modifying the original state
            return copy.deepcopy(input_data)
        elif hasattr(input_data, 'model_dump'):
            # Use model_dump if available (Pydantic V2)
            return input_data.model_dump(mode='json')
        else:
            # Fallback for other potential BaseSchema types or dict-like objects
            try:
                # Attempt a deepcopy for safety
                return copy.deepcopy(dict(input_data))
            except Exception:
                 # If conversion fails, return an empty dict or raise an error
                 # For robustness, returning empty might be safer in production
                 print(f"Warning: Could not convert input data of type {type(input_data)} to dict. Proceeding with empty data.")
                 return {}

    def process(self, input_data: Union[DynamicSchema, Dict[str, Any]], config: Optional[Dict[str, Any]] = None, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """
        Processes input data to determine the routing destination(s).

        Evaluates conditions defined in the configuration against the input data.
        Based on the `allow_multiple` setting, it selects either the first matching
        choice or all matching choices.

        Args:
            input_data: The dynamic input data for the node.
            config: Optional configuration override.
            *args: Additional positional arguments (unused).
            **kwargs: Additional keyword arguments (unused).

        Returns:
            Dict[str, Any]: A dictionary containing:
                - TEMP_STATE_UPDATE_KEY: The original input data (passed through).
                - ROUTER_CHOICE_KEY: A list of matched node IDs (choice_id).
                                      If allow_multiple is False, this list contains
                                      at most one element. If no conditions match,
                                      this list will be empty.
        """
        # Prepare input data and configuration
        input_dict = self._prepare_input_data(input_data)
        active_config = self.config

        matched_choices: List[str] = []

        # Iterate through conditions in the specified order
        for condition in active_config.choices_with_conditions:
            # Retrieve the value from the input data using the specified path
            input_value, found = _get_nested_value(input_dict, condition.input_path)

            # Only proceed if the path was valid
            if found:
                # Perform equality check
                if input_value == condition.target_value:
                    # Add the choice ID to the list of matches
                    matched_choices.append(condition.choice_id)

                    # If only single choice is allowed, break after the first match
                    if not active_config.allow_multiple:
                        break
            else:
                 # Optionally log a warning if a path doesn't exist
                 print(f"Warning: Input path '{condition.input_path}' not found in data for RouterNode.")


        # Prepare the output data structure expected by the execution engine
        # Pass through the original input data under the state update key
        output_data_passthrough = input_dict # Use the prepared dict

        # NOTE: LangGraph expects the routing choice key to contain the node ID(s)
        #       to route to next. If allow_multiple is false, it expects a single string.
        #       If allow_multiple is true, it *might* expect a list (needs verification
        #       with LangGraph's ConditionalEdges documentation).
        #       For now, we'll return a list, and handle the single-choice case
        #       by potentially returning the first element or an empty list.
        #       If no matches, return empty list.

        # Let's strictly adhere to the type hint of BaseRouterSchema.choices which is List[str]
        # The downstream graph runner (like LangGraph conditional edges) needs to handle
        # an empty list (no route match) or a list with multiple items if allow_multiple=True.

        return {
            TEMP_STATE_UPDATE_KEY: output_data_passthrough,
            ROUTER_CHOICE_KEY: matched_choices
        }
