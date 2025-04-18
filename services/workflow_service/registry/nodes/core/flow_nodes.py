# workflow_service/registry/nodes/core/flow_nodes.py
"""
Flow control nodes for workflow processing.

This module provides nodes for conditional data filtering and branching logic in workflows.
Key components:
- FilterNode: Selectively filters data based on configurable conditions
- IfElseConditionNode: Implements conditional branching based on data evaluation

The module uses a declarative approach with Pydantic models for configuration and validation.
"""

import copy
from enum import Enum
import json
import traceback
from typing import Any, Dict, List, Optional, Union, ClassVar, Literal, Tuple, Set, Type

# Use real imports
from pydantic import Field, model_validator, field_validator, BaseModel, ValidationError

from kiwi_app.workflow_app.constants import LaunchStatus
from workflow_service.registry.schemas.base import BaseSchema
# from workflow_service.registry.nodes.core.base import BaseNode # Not used directly
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema, BaseDynamicNode

# --- Enums (REVISED) ---
class LogicalOperator(str, Enum):
    """
    Logical operators for combining multiple conditions.
    
    Attributes:
        AND: All conditions must be true
        OR: At least one condition must be true
    """
    AND = "and"
    OR = "or"

class FilterOperator(str, Enum):
    """
    Operators for filter conditions that define how field values are compared.
    
    Attributes:
        EQUALS: Field value equals the condition value
        EQUALS_ANY_OF: Field value equals any value in a list of condition values
        NOT_EQUALS: Field value does not equal the condition value
        GREATER_THAN: Field value is greater than the condition value
        LESS_THAN: Field value is less than the condition value
        GREATER_THAN_OR_EQUALS: Field value is greater than or equal to the condition value
        LESS_THAN_OR_EQUALS: Field value is less than or equal to the condition value
        CONTAINS: Field value contains the condition value (for strings, lists, etc.)
        NOT_CONTAINS: Field value does not contain the condition value
        STARTS_WITH: Field value (string) starts with the condition value
        ENDS_WITH: Field value (string) ends with the condition value
        IS_EMPTY: Field value is None, empty string, empty list, or empty dict
        IS_NOT_EMPTY: Field value is not empty
    """
    EQUALS = "equals"
    EQUALS_ANY_OF = "equals_any_of"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_THAN_OR_EQUALS = "greater_than_or_equals"
    LESS_THAN_OR_EQUALS = "less_than_or_equals"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"

class FilterMode(str, Enum):
    """
    Modes that determine how filter conditions are applied.
    
    Attributes:
        ALLOW: Keep target if condition passes, remove if it fails (default)
        DENY: Remove target if condition passes, keep if it fails
    """
    ALLOW = "allow"  # Keep target if condition passes (remove if fails) - Default
    DENY = "deny"    # Remove target if condition passes (keep if fails)

# --- Condition Schemas (REVISED VALIDATOR) ---
class FilterCondition(BaseSchema):
    """
    Defines a single filter condition with a field path, operator, and optional value.
    
    Attributes:
        field: Dot-notation path to the field to evaluate (e.g., "user.profile.name")
        operator: The comparison operator to apply
        value: The value to compare against (optional for some operators like IS_EMPTY)
    """
    field: str = Field(
        ..., 
        description="Dot-notation path to the field to evaluate (e.g., 'user.profile.name')"
    )
    operator: FilterOperator = Field(
        ...,
        description="The comparison operator to apply"
    )
    value: Optional[Any] = Field(
        None,
        description="The value to compare against (optional for some operators like IS_EMPTY)"
    )
    apply_to_each_value_in_list_field: bool = Field(
        False,
        description="Whether to apply the condition to each value in a list field (only applies when the field is a list)"
    )
    list_field_logical_operator: LogicalOperator = Field(
        default=LogicalOperator.AND,
        description="How to combine results when evaluating conditions on each value in a list field."
    )

    @model_validator(mode='before')
    @classmethod
    def validate_value_presence(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates that a value is provided for operators that require one.
        
        Args:
            values: The raw input values
            
        Returns:
            The validated values dictionary
            
        Raises:
            ValueError: If a required value is missing
        """
        op = values.get('operator')
        val = values.get('value')
        unary = {FilterOperator.IS_EMPTY, FilterOperator.IS_NOT_EMPTY}
        if op and op not in unary and val is None:
            if op != FilterOperator.EQUALS_ANY_OF:
                 raise ValueError(f"Value required for operator '{op}'")
        return values

    @model_validator(mode='after')
    def validate_operator_value_types(self) -> 'FilterCondition':
        """
        Validates that the value type is compatible with the operator.
        
        Returns:
            The validated FilterCondition instance
            
        Raises:
            ValueError: If the value type is incompatible with the operator
        """
        if self.operator == FilterOperator.EQUALS_ANY_OF:
             if self.value is None:
                 raise ValueError(f"Value for '{self.operator}' cannot be None.")
             if not isinstance(self.value, (list, tuple, set)):
                 raise ValueError(f"Value for '{self.operator}' must be list/tuple/set, got {type(self.value).__name__}")
        
        numeric_ops = {
            FilterOperator.GREATER_THAN, 
            FilterOperator.LESS_THAN, 
            FilterOperator.GREATER_THAN_OR_EQUALS, 
            FilterOperator.LESS_THAN_OR_EQUALS
        }
        if self.operator in numeric_ops and self.value is None:
             raise ValueError(f"Cannot compare with None using operator '{self.operator}'")
        
        string_ops = {FilterOperator.STARTS_WITH, FilterOperator.ENDS_WITH}
        if self.operator in string_ops and self.value is None:
             raise ValueError(f"Cannot perform string operation '{self.operator}' with None value")
        return self

class FilterConditionGroup(BaseSchema):
    """
    Groups multiple filter conditions with a logical operator.
    
    Attributes:
        conditions: List of filter conditions to evaluate
        logical_operator: How to combine the conditions (AND/OR)
    """
    conditions: List[FilterCondition] = Field(
        ..., 
        min_length=1,
        description="List of filter conditions to evaluate"
    )
    logical_operator: LogicalOperator = Field(
        default=LogicalOperator.AND,
        description="How to combine the conditions (AND/OR)"
    )

# --- FilterNode Schemas (REVISED: Added filter_mode) ---
class FilterConfigSchema(BaseSchema):
    """
    Configuration for a single filter operation.
    
    Attributes:
        condition_groups: Groups of conditions to evaluate
        group_logical_operator: How to combine the condition groups (AND/OR)
        nested_list_logical_operator: How to combine results when evaluating conditions on nested lists
        filter_target: Path to the target field/object to filter (None means filter the entire object)
        filter_mode: Whether to ALLOW (keep) or DENY (remove) items that match the conditions
    """
    condition_groups: List[FilterConditionGroup] = Field(
        ..., 
        min_length=1,
        description="Groups of conditions to evaluate"
    )
    group_logical_operator: LogicalOperator = Field(
        default=LogicalOperator.AND,
        description="How to combine the condition groups (AND/OR)"
    )
    nested_list_logical_operator: LogicalOperator = Field(
        default=LogicalOperator.AND,
        description="How to combine results when evaluating conditions on nested lists when the field points to subfields of objects within a list (doesn't apply when field itself is a list)."
    )
    filter_target: Optional[str] = Field(
        default=None,
        description="Path to the target field/object to filter (None means filter the entire object)"
    )
    filter_mode: FilterMode = Field(
        default=FilterMode.ALLOW,
        description="Whether to ALLOW (keep) or DENY (remove) items that match the conditions"
    )

class FilterTargets(BaseSchema):
    """
    Container for multiple filter configurations.
    
    Attributes:
        targets: List of filter configurations to apply
    """
    targets: List[FilterConfigSchema] = Field(
        ..., 
        min_length=1,
        description="List of filter configurations to apply"
    )
    
    @model_validator(mode='after')
    def check_targets(self) -> 'FilterTargets':
        """
        Validates that filter targets are unique and properly formatted.
        
        Returns:
            The validated FilterTargets instance
            
        Raises:
            ValueError: If there are duplicate targets or more than one None target
        """
        none_targets = 0
        target_paths: Set[str] = set()
        for target_config in self.targets:
            target_path = target_config.filter_target
            if target_path is None:
                none_targets += 1
            else:
                if not isinstance(target_path, str) or not target_path.strip():
                    raise ValueError(f"filter_target path must be a non-empty string or None, got: '{target_path}'")
                target_path = target_path.strip()
                # Allow duplicate paths if they have different modes or conditions, but warn?
                # For now, strict check remains:
                if target_path in target_paths:
                    raise ValueError(f"Duplicate filter_target path found: '{target_path}'")
                target_paths.add(target_path)
                target_config.filter_target = target_path
        if none_targets > 1:
            raise ValueError("Only one FilterConfigSchema can have filter_target=None")
        return self

class FilterOutputSchema(BaseSchema):
    """
    Output schema for the FilterNode.
    
    Attributes:
        filtered_data: The filtered data result (None if filtering failed)
    """
    filtered_data: Optional[Dict[str, Any]] = Field(
        None,
        description="The filtered data result (None if filtering failed)"
    )

# --- IfElseNode Schemas ---
class IfElseConditionConfig(BaseSchema):
    """
    Configuration for a tagged condition in the IfElseNode.
    
    Attributes:
        tag: Unique identifier for this condition
        condition_groups: Groups of conditions to evaluate
        group_logical_operator: How to combine the condition groups (AND/OR)
        nested_list_logical_operator: How to combine results when evaluating conditions on nested lists
    """
    tag: str = Field(
        ...,
        description="Unique identifier for this condition"
    )
    condition_groups: List[FilterConditionGroup] = Field(
        ..., 
        min_length=1,
        description="Groups of conditions to evaluate"
    )
    group_logical_operator: LogicalOperator = Field(
        default=LogicalOperator.AND,
        description="How to combine the condition groups (AND/OR)"
    )
    nested_list_logical_operator: LogicalOperator = Field(
        default=LogicalOperator.AND,
        description="How to combine results when evaluating conditions on nested lists when the field points to subfields of objects within a list (doesn't apply when field itself is a list)."
    )

class IfElseConfigSchema(BaseSchema):
    """
    Configuration for the IfElseConditionNode.
    
    Attributes:
        tagged_conditions: List of tagged conditions to evaluate
        branch_logic_operator: How to combine the tagged condition results (AND/OR)
    """
    tagged_conditions: List[IfElseConditionConfig] = Field(
        ..., 
        min_length=1,
        description="List of tagged conditions to evaluate"
    )
    branch_logic_operator: LogicalOperator = Field(
        default=LogicalOperator.AND,
        description="How to combine the tagged condition results (AND/OR)"
    )
    
    @model_validator(mode='after')
    def check_unique_tags(self) -> 'IfElseConfigSchema':
        """
        Validates that all condition tags are unique.
        
        Returns:
            The validated IfElseConfigSchema instance
            
        Raises:
            ValueError: If there are duplicate tags
        """
        tags = set()
        for config in self.tagged_conditions:
            if config.tag in tags:
                raise ValueError(f"Duplicate tag found: '{config.tag}'")
            tags.add(config.tag)
        return self

class BranchPath(str, Enum):
    """
    Possible branch paths for the IfElseConditionNode.
    
    Attributes:
        TRUE_BRANCH: The path to take when conditions evaluate to true
        FALSE_BRANCH: The path to take when conditions evaluate to false
    """
    TRUE_BRANCH = "true_branch"
    FALSE_BRANCH = "false_branch"

class IfElseOutputSchema(BaseSchema):
    """
    Output schema for the IfElseConditionNode.
    
    Attributes:
        data: The original input data (passed through)
        tag_results: Results of each tagged condition evaluation
        condition_result: The final combined result of all conditions
        branch: Which branch path to take (true_branch or false_branch)
    """
    data: Dict[str, Any] = Field(
        ...,
        description="The original input data (passed through)"
    )
    tag_results: Dict[str, bool] = Field(
        ...,
        description="Results of each tagged condition evaluation"
    )
    condition_result: bool = Field(
        ...,
        description="The final combined result of all conditions"
    )
    branch: BranchPath = Field(
        ...,
        description="Which branch path to take (true_branch or false_branch)"
    )

# ==============================================
# --- CORE EVALUATION LOGIC - V11 REVISION ---
# ==============================================

class ConditionEvaluationError(Exception):
    """Exception raised when a condition evaluation fails."""
    pass

def _evaluate_single_condition_on_value(
    field_value: Any, condition: FilterCondition = None, operator: FilterOperator = None, condition_value: Any = None
) -> bool:
    """
    Evaluates a single condition against a field value.
    
    Args:
        field_value: The value extracted from the data
        condition: The condition to evaluate
        
    Returns:
        bool: True if the condition passes, False otherwise
        
    Raises:
        ConditionEvaluationError: If an error occurs during evaluation
    """
    if condition is not None:
        operator = condition.operator
        condition_value = condition.value
    
    # Handle list field special processing
    if condition is not None and isinstance(field_value, list) and condition.apply_to_each_value_in_list_field:
        # Apply the operator to each value in the list and combine results
        if not field_value:  # Empty list
            return operator == FilterOperator.IS_EMPTY
        
        # Evaluate condition on each item in the list
        item_results = []
        for item in field_value:
            # Recursively apply the same evaluation function to each item
            #     Pass None condition to avoid infinite recursion!
            result = _evaluate_single_condition_on_value(item, None, operator, condition_value)
            item_results.append(result)
        
        # Combine results based on the logical operator
        if condition.list_field_logical_operator == LogicalOperator.AND:
            return all(item_results)
        else:  # LogicalOperator.OR
            return any(item_results)
    
    # Handle empty checks first
    if operator == FilterOperator.IS_EMPTY:
        return field_value is None or field_value in ('', [], {})
    if operator == FilterOperator.IS_NOT_EMPTY:
        return not (field_value is None or field_value in ('', [], {}))
    
    # Handle None field values
    if field_value is None:
        if operator == FilterOperator.EQUALS:
            return field_value == condition_value
        if operator == FilterOperator.NOT_EQUALS:
            return field_value != condition_value
        if operator == FilterOperator.EQUALS_ANY_OF:
             try:
                 return field_value in condition_value
             except TypeError:
                 return False
        if operator == FilterOperator.NOT_CONTAINS:
            return True
        return False
    
    # Handle equality operators
    if operator == FilterOperator.EQUALS:
        return field_value == condition_value
    if operator == FilterOperator.NOT_EQUALS:
        return field_value != condition_value
    if operator == FilterOperator.EQUALS_ANY_OF:
         try:
             return field_value in condition_value
         except TypeError:
             return False
    
    # Handle numeric comparison operators
    try:
        if operator == FilterOperator.GREATER_THAN:
            return field_value > condition_value
        if operator == FilterOperator.LESS_THAN:
            return field_value < condition_value
        if operator == FilterOperator.GREATER_THAN_OR_EQUALS:
            return field_value >= condition_value
        if operator == FilterOperator.LESS_THAN_OR_EQUALS:
            return field_value <= condition_value
    except TypeError:
        return False
    except Exception as e:
        raise ConditionEvaluationError(f"Comparison error: {e}") from e
    
    # Handle containment operators
    if operator == FilterOperator.CONTAINS:
        if isinstance(field_value, (str, list, tuple, set, dict)):
            try:
                return condition_value in field_value
            except TypeError:
                return False
            except Exception as e:
                raise ConditionEvaluationError(f"Containment error: {e}") from e
        return False
    if operator == FilterOperator.NOT_CONTAINS:
        if isinstance(field_value, (str, list, tuple, set, dict)):
             try:
                 return condition_value not in field_value
             except TypeError:
                 return True
             except Exception as e:
                 raise ConditionEvaluationError(f"Containment error: {e}") from e
        return True
    
    # Handle string operators
    if operator == FilterOperator.STARTS_WITH:
        if isinstance(field_value, str):
            return field_value.startswith(str(condition_value))
        return False
    if operator == FilterOperator.ENDS_WITH:
        if isinstance(field_value, str):
            return field_value.endswith(str(condition_value))
        return False
    
    print(f"Warning: Reached end of _evaluate_single_condition_on_value unexpectedly for operator {operator}")
    return False


def evaluate_condition_recursive(
    data_context: Any, # Current position in traversal
    full_data: Dict[str, Any], # Always the root
    condition: FilterCondition,
    list_op: LogicalOperator,
    # -- Context for targeted list item evaluation --
    target_list_instance: Optional[List[Any]] = None, # Specific list instance being filtered
    target_item_index: Optional[int] = None # Index of the item to select from target_list_instance
) -> bool:
    """
    Recursively evaluates a condition by traversing the data structure.
    
    This function handles complex nested data structures and list traversal.
    
    Args:
        data_context: The current data context being evaluated
        full_data: The complete data dictionary (root)
        condition: The filter condition to evaluate
        list_op: The logical operator to use when evaluating lists
        target_list_instance: Optional specific list to target
        target_item_index: Optional index in the target list
        
    Returns:
        bool: True if the condition passes, False otherwise
    """
    path_parts = condition.field.split('.')
    if not condition.field:
        path_parts = []
    
    current_data_segment = data_context
    path_existed = True
    
    for i, part in enumerate(path_parts):
        current_part = part
        remaining_path_parts = path_parts[i+1:]
        remaining_path = '.'.join(remaining_path_parts)
        
        # Check if we've reached the target list instance
        is_target_list = (
            target_list_instance is not None and
            target_item_index is not None and
            isinstance(current_data_segment, list) and
            current_data_segment is target_list_instance # Check identity
        )
        
        if is_target_list:
            # We found the target list, now evaluate on the specific item
            if 0 <= target_item_index < len(current_data_segment):
                item_context = current_data_segment[target_item_index]
                sub_path_parts = path_parts[i:]
                sub_path = '.'.join(sub_path_parts)
                sub_condition = condition.model_copy(update={"field": sub_path})
                return evaluate_condition_recursive(
                    item_context, full_data, sub_condition, list_op, None, None
                )
            else:
                path_existed = False
                break
        elif isinstance(current_data_segment, dict):
            # Navigate through dictionary
            if current_part in current_data_segment:
                current_data_segment = current_data_segment[current_part]
            else:
                path_existed = False
                break
        elif isinstance(current_data_segment, list):
            # Handle list traversal by evaluating condition on each item
            current_list = current_data_segment
            sub_path_parts = path_parts[i:]
            sub_path = '.'.join(sub_path_parts)
            sub_condition = condition.model_copy(update={"field": sub_path})
            item_results = []
            
            if not current_list:
                 path_existed = False
                 break
                 
            for item_in_list in current_list:
                item_result = evaluate_condition_recursive(
                    item_in_list, full_data, sub_condition, list_op,
                    target_list_instance, target_item_index
                )
                item_results.append(item_result)
                # print(f"Item {idx} result: {item_result}")
                
            if not item_results:
                return False
                
            # Combine results based on logical operator
            return all(item_results) if list_op == LogicalOperator.AND else any(item_results)
        else:
            # Not a navigable type
            path_existed = False
            break
    
    # Evaluate the condition on the final value
    final_value = current_data_segment if path_existed else None
    try:
        return _evaluate_single_condition_on_value(
            final_value, condition
        )
    except ConditionEvaluationError as e:
        last_part = path_parts[-1] if path_parts else "root"
        print(f"Warning: Condition eval failed for field '{condition.field}' near '{last_part}': {e}. Treating as False.")
        return False
    except Exception as e:
        last_part = path_parts[-1] if path_parts else "root"
        print(f"Error: Unexpected error eval condition for field '{condition.field}' near '{last_part}': {e}. Treating as False.")
        traceback.print_exc()
        return False


def evaluate_filter_config_for_list_item(
    full_data: Dict[str, Any],
    config: FilterConfigSchema, # The config for the list filtering action
    target_list_instance: List[Any], # The actual list object instance from original data
    item_index: int # The specific index to focus on
) -> bool:
    """
    Evaluates filter conditions for a specific item in a list.
    
    Args:
        full_data: The complete data dictionary
        config: The filter configuration to apply
        target_list_instance: The list being filtered
        item_index: The index of the item to evaluate
        
    Returns:
        bool: True if the item passes the filter conditions, False otherwise
    """
    group_results: List[bool] = []
    
    # Evaluate each condition group
    for group in config.condition_groups:
        condition_results: List[bool] = []
        
        # Evaluate each condition in the group
        for condition in group.conditions:
            result = evaluate_condition_recursive(
                full_data, # Start context from root
                full_data,
                condition,
                config.nested_list_logical_operator,
                target_list_instance=target_list_instance,
                target_item_index=item_index
            )
            condition_results.append(result)
            
        # Combine condition results based on group's logical operator
        group_passed = all(condition_results) if group.logical_operator == LogicalOperator.AND else any(condition_results)
        group_results.append(group_passed)
    
    # Combine group results based on config's logical operator
    config_passed = all(group_results) if config.group_logical_operator == LogicalOperator.AND else any(group_results)
    return config_passed


def evaluate_filter_config_generic(
    initial_context: Any, # Usually the full data dict, or a sub-dict/list
    config: Union[FilterConfigSchema, IfElseConditionConfig]
) -> bool:
    """
    Evaluates filter conditions on any data context (not specific to list items).
    
    Args:
        initial_context: The data to evaluate against
        config: The filter configuration to apply
        
    Returns:
        bool: True if the data passes the filter conditions, False otherwise
    """
    group_results: List[bool] = []
    full_data_ref = initial_context if isinstance(initial_context, dict) else {}
    
    # Evaluate each condition group
    for group in config.condition_groups:
        condition_results: List[bool] = []
        
        # Evaluate each condition in the group
        for condition in group.conditions:
            result = evaluate_condition_recursive(
                initial_context,
                full_data_ref,
                condition,
                config.nested_list_logical_operator
            )
            # print(f"Condition result: {result} -- > {condition.model_dump_json(indent=4)}")
            condition_results.append(result)
            
        # Combine condition results based on group's logical operator
        group_passed = all(condition_results) if group.logical_operator == LogicalOperator.AND else any(condition_results)
        # print(f"Group result: {group_passed} -- > {group.model_dump_json(indent=4)}")
        group_results.append(group_passed)
    
    # print(f"Group results: {group_results} -- > {config.group_logical_operator}")
    # Combine group results based on config's logical operator
    config_passed = all(group_results) if config.group_logical_operator == LogicalOperator.AND else any(group_results)
    # print(f"Config result: {config_passed} -- > {config.model_dump_json(indent=4)}")
    return config_passed


# --- Helper functions ---
def _remove_nested_path(data: Any, field_path: str) -> bool:
    """
    Removes a field at the specified path from a nested data structure.
    
    Args:
        data: The data structure to modify
        field_path: Dot-notation path to the field to remove
        
    Returns:
        bool: True if the field was successfully removed, False otherwise
    """
    parts = field_path.split('.')
    if not parts or not field_path:
        return False
    
    target_obj = data
    final_key_or_index = parts[-1]
    
    # Navigate to the parent object containing the field to remove
    for part in parts[:-1]:
        if isinstance(target_obj, dict):
            if part in target_obj:
                target_obj = target_obj[part]
            else:
                return False
        elif isinstance(target_obj, list):
            try:
                idx = int(part)
                if 0 <= idx < len(target_obj):
                    target_obj = target_obj[idx]
                else:
                    return False
            except (ValueError, TypeError):
                return False
        else:
            return False
    
    # Remove the field from the parent object
    if isinstance(target_obj, dict):
        if final_key_or_index in target_obj:
            try:
                del target_obj[final_key_or_index]
                return True
            except Exception:
                return False
    elif isinstance(target_obj, list):
        try:
            idx = int(final_key_or_index)
            if 0 <= idx < len(target_obj):
                try:
                    del target_obj[idx]
                    return True
                except Exception:
                    return False
        except (ValueError, TypeError):
            pass
    return False

def _get_nested_obj(data: Any, field_path: str) -> Tuple[Any, bool]:
    """
    Retrieves a nested object at the specified path.
    
    Args:
        data: The data structure to navigate
        field_path: Dot-notation path to the field to retrieve
        
    Returns:
        Tuple[Any, bool]: The retrieved object and a boolean indicating success
    """
    current = data
    parts = field_path.split('.')
    
    if not field_path:
        return data, True
    
    # Navigate through the path
    for part in parts:
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                return None, False
        elif isinstance(current, list):
            try:
                idx = int(part)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None, False
            except (ValueError, TypeError):
                return None, False
        else:
            return None, False
    
    return current, True

# --- NEW HELPER ---
def _get_relative_path(full_path: str, base_path: str) -> Optional[str]:
    """
    Extracts a relative path from a full path based on a base path.
    
    If full_path starts with base_path + '.', returns the remainder.
    Otherwise, returns None. Handles empty base_path.
    
    Args:
        full_path: The complete path
        base_path: The base path to remove
        
    Returns:
        Optional[str]: The relative path or None if not relative
    """
    if not base_path:  # Cannot be relative to an empty base path conceptually
        return None
    
    prefix = base_path + '.'
    if full_path.startswith(prefix):
        relative = full_path[len(prefix):]
        return relative if relative else None  # Avoid returning empty string if paths are identical
    return None

# ==============================================
# --- NODE IMPLEMENTATIONS - V11 REVISION ---
# ==============================================

class FilterNode(BaseDynamicNode):
    """
    Node that filters data based on configurable conditions.
    
    This node can:
    1. Filter entire objects based on conditions
    2. Filter specific fields based on conditions
    3. Filter items in lists based on conditions
    4. Filter fields within list items based on conditions
    
    The node supports both ALLOW mode (keep if condition passes) and 
    DENY mode (remove if condition passes).
    """
    node_name: ClassVar[str] = "filter_data"
    node_version: ClassVar[str] = "0.1.0"  # Version bump for index fix
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.PRODUCTION
    input_schema_cls: Type[DynamicSchema] = DynamicSchema
    output_schema_cls: Type[FilterOutputSchema] = FilterOutputSchema
    config_schema_cls: Type[FilterTargets] = FilterTargets
    config: FilterTargets

    def _prepare_input_data(self, input_data: Union[DynamicSchema, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Prepares input data for processing by converting to a dictionary.
        
        Args:
            input_data: The input data to prepare
            
        Returns:
            Dict[str, Any]: A dictionary copy of the input data
        """
        if isinstance(input_data, dict):
            return copy.deepcopy(input_data)
        return input_data.model_dump(mode='json')
    def _get_config(self, config_override: Optional[Union[Dict[str, Any], FilterTargets]]) -> FilterTargets:
        """
        Resolves and validates the configuration to use for processing.
        
        This method handles different ways configuration can be provided:
        1. As a pre-validated FilterTargets object
        2. As a dictionary that needs validation
        3. From the node's existing configuration
        
        Args:
            config_override: Optional configuration to override the node's default config
            
        Returns:
            FilterTargets: A validated configuration object
            
        Raises:
            ValueError: If the provided configuration is invalid
            TypeError: If the configuration is of an unsupported type
        """
        config_to_use = config_override or self.config
        if isinstance(config_to_use, FilterTargets): 
            return config_to_use
        if isinstance(config_to_use, dict):
             try: 
                 return self.config_schema_cls(**config_to_use)
             except Exception as e: 
                 raise ValueError(f"Invalid config override for FilterNode: {e}") from e
        if isinstance(self.config, dict) and config_override is None:
             try: 
                 return self.config_schema_cls(**self.config)
             except Exception as e: 
                 raise ValueError(f"Invalid instance config for FilterNode: {e}") from e
        raise TypeError(f"Config must be dict or FilterTargets for FilterNode, got {type(config_to_use).__name__}")

    def process(self, input_data: Union[DynamicSchema, Dict[str, Any]], config: Optional[Union[Dict[str, Any], FilterTargets]] = None, *args: Any, **kwargs: Any) -> FilterOutputSchema:
        """
        Processes input data by applying filter conditions according to the configuration.
        
        This method implements a multi-pass filtering approach:
        1. Object-level filtering (entire data can be filtered out)
        2. List-based filtering (items in lists can be filtered)
        3. Field-level filtering (specific fields can be removed)
        
        The filtering logic respects both ALLOW and DENY modes:
        - ALLOW: Keep data only if conditions pass
        - DENY: Remove data if conditions pass
        
        Args:
            input_data: The data to filter, either as a DynamicSchema or dictionary
            config: Optional configuration override
            *args: Additional positional arguments (unused)
            **kwargs: Additional keyword arguments (unused)
            
        Returns:
            FilterOutputSchema: Contains the filtered data or None if filtering failed
        """
        # Create a deep copy of input data to avoid modifying the original
        original_input_dict = self._prepare_input_data(input_data) 
        try:
            # Resolve and validate the configuration
            active_config = self._get_config(config)
            # Create a separate copy to modify during filtering
            result_data = copy.deepcopy(original_input_dict) 

            # --- Pass 0: Object-Level Filtering ---
            # Check if the entire object should be filtered out based on top-level conditions
            for target_config in active_config.targets:
                if target_config.filter_target is None:
                    # This config applies to the entire object
                    passed = evaluate_filter_config_generic(original_input_dict, target_config)
                    if (target_config.filter_mode == FilterMode.ALLOW and not passed) or \
                       (target_config.filter_mode == FilterMode.DENY and passed):
                        # Return None if the entire object should be filtered out
                        return FilterOutputSchema(filtered_data=None)

            # --- Pass 1: Categorize Configs and Identify Target List Paths ---
            # Organize filter configurations by the lists they target
            configs_by_list_path: Dict[str, List[FilterConfigSchema]] = {} # {list_path: [configs targeting list OR fields within]}
            non_list_field_configs: List[FilterConfigSchema] = []         # Configs targeting non-list paths
            all_target_list_paths: Set[str] = set()                       # All list paths that need processing

            # Categorize each filter configuration
            for cfg in active_config.targets:
                target_path = cfg.filter_target
                if target_path is None: 
                    continue  # Already handled in Pass 0

                # Determine if this config targets a list or a field within a list
                base_list_path: Optional[str] = None
                parts = target_path.split('.')
                # Check each segment of the path to find if any part is a list
                for i in range(1, len(parts) + 1): 
                    current_sub_path = '.'.join(parts[:i])
                    obj, found = _get_nested_obj(original_input_dict, current_sub_path)
                    if found and isinstance(obj, list):
                        base_list_path = current_sub_path
                        break # Found the innermost list containing/matching the target

                if base_list_path:
                    # This config targets a list or a field within a list
                    all_target_list_paths.add(base_list_path)
                    configs_by_list_path.setdefault(base_list_path, []).append(cfg)
                else:
                    # This config targets a non-list field
                    non_list_field_configs.append(cfg)

            # --- Pass 2: Process Each Target List ---
            # Track which list paths have been processed to avoid duplicates
            processed_list_paths = set() 

            # Sort paths by length to process outer lists first (helps with nested structures)
            for list_path in sorted(list(all_target_list_paths), key=len):
                if list_path in processed_list_paths: 
                    continue  # Skip if already processed

                # Get the original list and the corresponding list in our result copy
                original_list_instance, list_found = _get_nested_obj(original_input_dict, list_path)
                target_list_in_result, result_list_found = _get_nested_obj(result_data, list_path)

                # Verify both lists exist and are actually lists
                if not (list_found and isinstance(original_list_instance, list) and
                        result_list_found and isinstance(target_list_in_result, list)):
                     # Skip if list not found or not a list type
                     continue

                # Get configurations relevant to this list
                relevant_configs = configs_by_list_path.get(list_path, [])
                if not relevant_configs: 
                    continue  # No rules for this list

                # Track which items and fields to remove
                indices_to_remove: Set[int] = set()  # Indices of items to remove completely
                field_removals_per_index: Dict[int, Set[str]] = {}  # Fields to remove from specific items

                # --- Step 2a: Determine actions for each item ---
                original_length = len(original_list_instance)
                for i in range(original_length):
                    keep_item = True  # Assume we keep the item unless a condition says otherwise
                    
                    for config in relevant_configs:
                        # Evaluate the filter condition for this list item
                        item_passed = evaluate_filter_config_for_list_item(
                            original_input_dict, config, original_list_instance, i
                        )

                        # Determine action based on whether config targets the item or a field within
                        if config.filter_target == list_path:  # Targets the entire item
                            if (config.filter_mode == FilterMode.ALLOW and not item_passed) or \
                               (config.filter_mode == FilterMode.DENY and item_passed):
                                keep_item = False
                                break  # Item removal takes precedence over field removals
                        else:  # Targets a field within the item
                            # Get the path relative to the list item
                            relative_field_path = _get_relative_path(config.filter_target, list_path)
                            if relative_field_path:
                                if (config.filter_mode == FilterMode.ALLOW and not item_passed) or \
                                   (config.filter_mode == FilterMode.DENY and item_passed):
                                    # Mark this field for removal in this item
                                    field_removals_per_index.setdefault(i, set()).add(relative_field_path)

                    # If we decided not to keep the item, add its index to removal list
                    if not keep_item:
                        indices_to_remove.add(i)

                # --- Step 2b: Apply removals to the list in result_data ---
                # Process removals in reverse order to maintain correct indices
                for i_orig in range(original_length - 1, -1, -1):
                    if i_orig in indices_to_remove:
                        # Calculate the current index in the result list that corresponds to this original index
                        # This accounts for items that were already removed
                        num_kept_before = sum(1 for i in range(i_orig) if i not in indices_to_remove)
                        current_idx_to_remove = num_kept_before

                        # Remove the item if the calculated index is valid
                        if 0 <= current_idx_to_remove < len(target_list_in_result):
                            del target_list_in_result[current_idx_to_remove]
                        else:
                            # This might happen if the list was modified by other operations
                            print(f"Warning: Calculated index {current_idx_to_remove} for removal (original {i_orig}) out of bounds for list {list_path} (len={len(target_list_in_result)}). Item might have been removed by other means.")

                # --- Step 2c: Apply field removals within the remaining items ---
                current_result_idx = 0  # Track position in the modified result list
                for i_orig in range(original_length):
                    if i_orig not in indices_to_remove:
                        # This item was kept, so apply any field removals
                        if current_result_idx < len(target_list_in_result):
                             item_in_result = target_list_in_result[current_result_idx]
                             if i_orig in field_removals_per_index:
                                 # Process field removals in reverse length order (deeper paths first)
                                 paths_to_remove = sorted(list(field_removals_per_index[i_orig]), key=len, reverse=True)
                                 for rel_path in paths_to_remove:
                                     _remove_nested_path(item_in_result, rel_path)
                             current_result_idx += 1
                        else:
                             print(f"Warning: Result list '{list_path}' length mismatch during field removal (original index {i_orig}).")

                # Mark this list as processed
                processed_list_paths.add(list_path)

            # --- Pass 3: Process Non-List Field Filters ---
            # Handle fields that aren't within lists
            # Sort by path length in reverse to process deeper paths first
            sorted_non_list_paths = sorted([cfg for cfg in non_list_field_configs if cfg.filter_target], 
                                          key=lambda c: len(c.filter_target), reverse=True)

            for config in sorted_non_list_paths:
                 target_path = config.filter_target  # Known to be non-None here
                 # Evaluate the condition using the original data for consistency
                 passed = evaluate_filter_config_generic(original_input_dict, config)
                 # Determine if the field should be removed based on filter mode
                 should_remove = (config.filter_mode == FilterMode.ALLOW and not passed) or \
                                 (config.filter_mode == FilterMode.DENY and passed)
                 if should_remove:
                      # Remove the field from the result data
                      _remove_nested_path(result_data, target_path)

            # Return the filtered data
            return FilterOutputSchema(filtered_data=result_data)

        except ValidationError as e:
             # Handle configuration validation errors
             print(f"Error: Config validation failed for FilterNode: {e}")
             return FilterOutputSchema(filtered_data=None)
        except Exception as e:
             # Handle any other errors during processing
             print(f"Error processing FilterNode: {e}")
             traceback.print_exc()
             return FilterOutputSchema(filtered_data=None)


class IfElseConditionNode(BaseDynamicNode):
    """
    Node that implements conditional branching based on data evaluation.
    
    This node evaluates a set of conditions against input data and determines
    which branch (TRUE or FALSE) the workflow should follow. It supports:
    
    1. Multiple tagged conditions that can be combined with logical operators
    2. Complex condition groups with nested evaluation
    3. Detailed result reporting showing which conditions passed/failed
    
    The node is useful for creating decision points in workflows where different
    processing paths should be taken based on data characteristics.
    """
    node_name: ClassVar[str] = "if_else_condition"
    node_version: ClassVar[str] = "0.1.0" # Version bump for consistency
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.PRODUCTION
    input_schema_cls: Type[DynamicSchema] = DynamicSchema
    output_schema_cls: Type[IfElseOutputSchema] = IfElseOutputSchema
    config_schema_cls: Type[IfElseConfigSchema] = IfElseConfigSchema
    config: IfElseConfigSchema

    def _prepare_input_data(self, input_data: Union[DynamicSchema, Dict[str, Any]]) -> Dict[str, Any]:
         """
         Prepares input data for processing by converting to a dictionary.
         
         Args:
             input_data: The input data to prepare
             
         Returns:
             Dict[str, Any]: A dictionary copy of the input data
         """
         if isinstance(input_data, dict): return copy.deepcopy(input_data)
         return input_data.model_dump(mode='json')  #  if hasattr(input_data, "model_dump") else dict(input_data)

    def _get_config(self, config_override: Optional[Union[Dict[str, Any], IfElseConfigSchema]]) -> IfElseConfigSchema:
        """
        Resolves and validates the configuration to use for processing.
        
        This method handles different ways configuration can be provided:
        1. As a pre-validated IfElseConfigSchema object
        2. As a dictionary that needs validation
        3. From the node's existing configuration
        
        Args:
            config_override: Optional configuration to override the node's default config
            
        Returns:
            IfElseConfigSchema: A validated configuration object
            
        Raises:
            ValueError: If the provided configuration is invalid
            TypeError: If the configuration is of an unsupported type
        """
        config_to_use = config_override or self.config
        if isinstance(config_to_use, IfElseConfigSchema): return config_to_use
        if isinstance(config_to_use, dict):
             try: return self.config_schema_cls(**config_to_use)
             except Exception as e: raise ValueError(f"Invalid config override: {e}") from e
        if isinstance(self.config, dict) and config_override is None:
             try: return self.config_schema_cls(**self.config)
             except Exception as e: raise ValueError(f"Invalid instance config: {e}") from e
        raise TypeError(f"Config must be dict or IfElseConfigSchema, got {type(config_to_use).__name__}")

    def process(self, input_data: Union[DynamicSchema, Dict[str, Any]], config: Optional[Union[Dict[str, Any], IfElseConfigSchema]] = None, *args: Any, **kwargs: Any) -> IfElseOutputSchema:
        """
        Evaluates conditions against input data and determines the branch path.
        
        This method:
        1. Evaluates each tagged condition against the input data
        2. Combines the results according to the configured logical operator
        3. Determines which branch (TRUE or FALSE) should be followed
        4. Returns the original data along with evaluation results
        
        Args:
            input_data: The data to evaluate conditions against
            config: Optional configuration override
            *args: Additional positional arguments (unused)
            **kwargs: Additional keyword arguments (unused)
            
        Returns:
            IfElseOutputSchema: Contains the original data, condition results, and branch path
        """
        # Create a copy of input data to avoid modifying the original
        input_dict_copy = self._prepare_input_data(input_data)
        original_input_passthrough = input_dict_copy.copy()
        try:
            # Resolve and validate the configuration
            active_config = self._get_config(config)
            # Track results for each tagged condition
            tag_results: Dict[str, bool] = {}
            
            # Evaluate each tagged condition
            for tagged_conf in active_config.tagged_conditions:
                # Evaluate the condition against the input data
                result = evaluate_filter_config_generic(input_dict_copy, tagged_conf)
                tag_results[tagged_conf.tag] = result
                
            # Determine the final result by combining individual results
            final_result = False
            if tag_results:
                op = active_config.branch_logic_operator
                # Combine results based on the configured operator
                final_result = all(tag_results.values()) if op == LogicalOperator.AND else any(tag_results.values())
                
            # Determine which branch to follow based on the final result
            branch = BranchPath.TRUE_BRANCH if final_result else BranchPath.FALSE_BRANCH
            
            # Return the original data along with evaluation results
            return IfElseOutputSchema(
                data=original_input_passthrough, 
                tag_results=tag_results, 
                condition_result=final_result, 
                branch=branch
            )
        except ValidationError as e:
             # Handle configuration validation errors
             print(f"Error: Config validation failed for IfElseNode: {e}")
        except Exception as e:
             # Handle any other errors during processing
             print(f"Error processing IfElseNode: {e}")
             traceback.print_exc()
             
        # Return default result in case of errors
        return IfElseOutputSchema(
            data=original_input_passthrough, 
            tag_results={}, 
            condition_result=False, 
            branch=BranchPath.FALSE_BRANCH
        )

# --- Example Usage Block (Optional) ---
if __name__ == '__main__':
     # Example demonstrating FilterMode.DENY
    deny_node = FilterNode(
        node_id="deny_example",
        config={
            "targets": [
                # Deny (remove) orders list item if its status is 'pending'
                {
                    "filter_target": "orders",
                    "filter_mode": "deny", # Use DENY mode
                    "condition_groups": [{
                        "conditions": [{"field": "orders.status", "operator": "equals", "value": "pending"}]
                    }]
                },
                 # Deny (remove) the metadata field if its source is 'test'
                {
                    "filter_target": "metadata.source",
                    "filter_mode": "deny", # Use DENY mode
                    "condition_groups": [{
                        "conditions": [{"field": "metadata.source", "operator": "equals", "value": "test"}]
                    }]
                }
            ]
        }
    )

    test_data = {
            "user": {"name": "Alice", "age": 35, "status": "active"},
            "orders": [
                {"id": 1, "status": "completed", "value": 150.0},
                {"id": 2, "status": "pending", "value": 75.5}, # This should be removed
                {"id": 3, "status": "shipped", "value": 210.0}
            ],
            "metadata": {"source": "prod", "timestamp": 1234567890},
            "global_flag": True
        }

    result = deny_node.process(test_data)
    print("--- DENY Example ---")
    print("Original Data:")
    print(json.dumps(test_data, indent=2))
    print("\nFiltered Data (DENY pending orders, DENY metadata.source if 'test'):")
    print(json.dumps(result.model_dump(), indent=2))

    test_data_deny_source = test_data.copy()
    test_data_deny_source["metadata"] = {"source": "test", "timestamp": 987}
    result_deny_source = deny_node.process(test_data_deny_source)
    print("\nFiltered Data (DENY pending orders, DENY metadata.source if 'test' - source IS test):")
    print(json.dumps(result_deny_source.model_dump(), indent=2))
