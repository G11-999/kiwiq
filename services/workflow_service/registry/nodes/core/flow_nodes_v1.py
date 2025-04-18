# workflow_service/registry/nodes/core/flow_nodes_gemini.py

# --- Existing Imports ---
import copy
from enum import Enum
import json
import traceback
from typing import Any, Dict, List, Optional, Union, ClassVar, Literal, Tuple, Set, Type

# Use real imports
from pydantic import Field, model_validator, field_validator, BaseModel, ValidationError
from workflow_service.registry.schemas.base import BaseSchema
# from workflow_service.registry.nodes.core.base import BaseNode # Not used directly
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema, BaseDynamicNode

from global_config.constants import EnvFlag

# --- Enums (Unchanged) ---
class LogicalOperator(str, Enum): AND = "and"; OR = "or"
class FilterOperator(str, Enum):
    DENY = "deny"; EQUALS = "equals"; EQUALS_ANY_OF = "equals_any_of"; NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"; LESS_THAN = "less_than"; GREATER_THAN_OR_EQUALS = "greater_than_or_equals"
    LESS_THAN_OR_EQUALS = "less_than_or_equals"; CONTAINS = "contains"; NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"; ENDS_WITH = "ends_with"; IS_EMPTY = "is_empty"; IS_NOT_EMPTY = "is_not_empty"

# --- Condition Schemas (Unchanged) ---
class FilterCondition(BaseSchema):
    field: str = Field(...)
    operator: FilterOperator = Field(...)
    value: Optional[Any] = Field(None)
    @model_validator(mode='before')
    @classmethod
    def validate_value_presence(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        op = values.get('operator'); val = values.get('value')
        unary = {FilterOperator.IS_EMPTY, FilterOperator.IS_NOT_EMPTY, FilterOperator.DENY}
        if op and op not in unary and val is None: raise ValueError(f"Value required for operator '{op}'")
        return values
    @model_validator(mode='after')
    def validate_operator_value_types(self) -> 'FilterCondition':
        if self.operator == FilterOperator.EQUALS_ANY_OF:
             if self.value is None: raise ValueError(f"Value for '{self.operator}' cannot be None.")
             if not isinstance(self.value, (list, tuple, set)): raise ValueError(f"Value for '{self.operator}' must be list/tuple/set, got {type(self.value).__name__}")
        return self

class FilterConditionGroup(BaseSchema):
    conditions: List[FilterCondition] = Field(..., min_length=1)
    logical_operator: LogicalOperator = Field(default=LogicalOperator.AND)

# --- FilterNode Schemas (Unchanged) ---
class FilterConfigSchema(BaseSchema):
    condition_groups: List[FilterConditionGroup] = Field(..., min_length=1)
    group_logical_operator: LogicalOperator = Field(default=LogicalOperator.AND)
    nested_list_logical_operator: LogicalOperator = Field(default=LogicalOperator.AND)
    filter_target: Optional[str] = Field(default=None)

class FilterTargets(BaseSchema):
    targets: List[FilterConfigSchema] = Field(..., min_length=1)
    @model_validator(mode='after')
    def check_targets(self) -> 'FilterTargets':
        none_targets = 0; target_paths: Set[str] = set()
        for target_config in self.targets:
            target_path = target_config.filter_target
            if target_path is None: none_targets += 1
            else:
                if not isinstance(target_path, str) or not target_path.strip(): raise ValueError(f"filter_target path must be a non-empty string or None, got: '{target_path}'")
                target_path = target_path.strip()
                if target_path in target_paths: raise ValueError(f"Duplicate filter_target path found: '{target_path}'")
                target_paths.add(target_path); target_config.filter_target = target_path
        if none_targets > 1: raise ValueError("Only one FilterConfigSchema can have filter_target=None")
        if none_targets == 1 and len(self.targets) > 1: print("Warning: Object-level filter present...")
        return self

class FilterOutputSchema(BaseSchema):
    filtered_data: Optional[Dict[str, Any]] = Field(None)

# --- IfElseNode Schemas (Unchanged) ---
class IfElseConditionConfig(BaseSchema):
    tag: str = Field(...)
    condition_groups: List[FilterConditionGroup] = Field(..., min_length=1)
    group_logical_operator: LogicalOperator = Field(default=LogicalOperator.AND)
    nested_list_logical_operator: LogicalOperator = Field(default=LogicalOperator.AND)

class IfElseConfigSchema(BaseSchema):
    tagged_conditions: List[IfElseConditionConfig] = Field(..., min_length=1)
    branch_logic_operator: LogicalOperator = Field(default=LogicalOperator.AND)
    @model_validator(mode='after')
    def check_unique_tags(self) -> 'IfElseConfigSchema':
        tags = set()
        for config in self.tagged_conditions:
            if config.tag in tags: raise ValueError(f"Duplicate tag found: '{config.tag}'")
            tags.add(config.tag)
        return self

class BranchPath(str, Enum): TRUE_BRANCH = "true_branch"; FALSE_BRANCH = "false_branch"

class IfElseOutputSchema(BaseSchema):
    data: Dict[str, Any] = Field(...); tag_results: Dict[str, bool] = Field(...)
    condition_result: bool = Field(...); branch: BranchPath = Field(...)

# ==============================================
# --- CORE EVALUATION LOGIC - V9 REVISION ---
# ==============================================

class ConditionEvaluationError(Exception): pass

def _evaluate_single_condition_on_value(
    field_value: Any, operator: FilterOperator, condition_value: Any
) -> bool:
    # --- (Implementation Unchanged - Assumed Correct) ---
    if operator == FilterOperator.DENY: return False
    if operator == FilterOperator.IS_EMPTY: return field_value is None or field_value in ('', [], {})
    if operator == FilterOperator.IS_NOT_EMPTY: return not (field_value is None or field_value in ('', [], {}))
    if operator == FilterOperator.EQUALS: return field_value == condition_value
    if operator == FilterOperator.NOT_EQUALS: return field_value != condition_value
    if field_value is None:
        if operator == FilterOperator.EQUALS_ANY_OF:
             try: return field_value in condition_value
             except TypeError: return False
        if operator == FilterOperator.NOT_CONTAINS: return True
        return False
    if operator == FilterOperator.EQUALS_ANY_OF:
         try: return field_value in condition_value
         except TypeError: return False
    try: # Comparison
        if operator == FilterOperator.GREATER_THAN: return field_value > condition_value
        if operator == FilterOperator.LESS_THAN: return field_value < condition_value
        if operator == FilterOperator.GREATER_THAN_OR_EQUALS: return field_value >= condition_value
        if operator == FilterOperator.LESS_THAN_OR_EQUALS: return field_value <= condition_value
    except TypeError: return False
    except Exception as e: raise ConditionEvaluationError(f"Comparison error: {e}") from e
    if operator == FilterOperator.CONTAINS: # Container
        if isinstance(field_value, (str, list, tuple, set, dict)):
            try: return condition_value in field_value
            except TypeError: return False
            except Exception as e: raise ConditionEvaluationError(f"Containment error: {e}") from e
        return False
    if operator == FilterOperator.NOT_CONTAINS:
        if isinstance(field_value, (str, list, tuple, set, dict)):
             try: return condition_value not in field_value
             except TypeError: return True
             except Exception as e: raise ConditionEvaluationError(f"Containment error: {e}") from e
        return True
    if operator == FilterOperator.STARTS_WITH: # String
        if isinstance(field_value, str): return field_value.startswith(str(condition_value))
        return False
    if operator == FilterOperator.ENDS_WITH:
        if isinstance(field_value, str): return field_value.endswith(str(condition_value))
        return False
    print(f"Warning: Reached end of _evaluate_single_condition_on_value unexpectedly for operator {operator}")
    return False

# **** REVISED evaluate_condition_recursive (V9) ****
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
    Evaluates a condition recursively. Paths always start from data_context.
    Handles generic list expansion.
    If target_list_instance is provided, it switches context to the specified
    item when that specific list instance is encountered during traversal.
    """
    path_parts = condition.field.split('.')
    if not condition.field: path_parts = []

    current_data_segment = data_context
    path_existed = True

    for i, part in enumerate(path_parts):
        current_part = part # For clarity in logic below

        # --- Is current_data_segment the specific target list we need to select an item from? ---
        if target_list_instance is not None and \
           target_item_index is not None and \
           isinstance(current_data_segment, list) and \
           current_data_segment is target_list_instance:

            # YES: Select the item at target_item_index to continue the path from.
            if 0 <= target_item_index < len(current_data_segment):
                current_data_segment = current_data_segment[target_item_index] # Context switch to item
                # Now apply the *current part* to this item context
                if isinstance(current_data_segment, dict):
                    if current_part in current_data_segment:
                        current_data_segment = current_data_segment[current_part] # Traverse within item
                    else:
                        path_existed = False; break # Part not in item dict
                elif isinstance(current_data_segment, list):
                    # Path continues into a list *within* the selected target item.
                    # Treat this as generic list expansion from this point.
                     # The path from here is current_part + remaining_parts
                    sub_path_parts = path_parts[i:]
                    sub_path = '.'.join(sub_path_parts)
                    sub_condition = condition.model_copy(update={"field": sub_path})
                    item_results = []
                    if not current_data_segment: path_existed = False; break
                    for item_in_sublist in current_data_segment:
                         # Pass None for target list context now, as we are expanding generically
                         item_result = evaluate_condition_recursive(
                              item_in_sublist, full_data, sub_condition, list_op, None, None
                         )
                         item_results.append(item_result)
                    return all(item_results) if list_op == LogicalOperator.AND else any(item_results)
                else: # Selected item is not navigable with the current path part
                    path_existed = False; break
            else: # Index out of bounds for target item
                path_existed = False; break
        # --- END TARGET LIST HANDLING ---

        # --- Normal Traversal (Not the target list OR target context inactive) ---
        elif isinstance(current_data_segment, dict):
            if current_part in current_data_segment:
                current_data_segment = current_data_segment[current_part]
            else:
                path_existed = False; break
        elif isinstance(current_data_segment, list):
            # --- Generic List Expansion ---
            current_list = current_data_segment
            # Path from current part onwards needs evaluation against each item
            sub_path_parts = path_parts[i:]
            sub_path = '.'.join(sub_path_parts)
            sub_condition = condition.model_copy(update={"field": sub_path})

            item_results = []
            if not current_list: path_existed = False; break

            for item_in_list in current_list:
                # Evaluate the sub_condition starting from the list item
                item_result = evaluate_condition_recursive(
                    item_in_list, full_data, sub_condition, list_op,
                    target_list_instance, target_item_index # Pass context down
                )
                item_results.append(item_result)
            # This was a branching point, return combined result
            return all(item_results) if list_op == LogicalOperator.AND else any(item_results)
        else: # Scalar or None
            path_existed = False; break

    # --- Loop finished or path broken ---
    final_value = current_data_segment if path_existed else None
    # No special handling needed here for path ending at list,
    # the recursive expansion logic in the loop handles it.
    try:
        return _evaluate_single_condition_on_value(
            final_value, condition.operator, condition.value
        )
    except ConditionEvaluationError as e:
        last_part = path_parts[-1] if path_parts else "final_value"
        print(f"Warning: Condition eval failed for field '{condition.field}' near '{last_part}': {e}. Treating as False.")
        return False
    except Exception as e:
        last_part = path_parts[-1] if path_parts else "final_value"
        print(f"Error: Unexpected error eval condition for field '{condition.field}' near '{last_part}': {e}. Treating as False.")
        return False


# **** Reintroduce evaluate_filter_config_for_list_item ****
def evaluate_filter_config_for_list_item(
    full_data: Dict[str, Any],
    config: FilterConfigSchema,
    target_list_instance: List[Any], # The actual list object instance
    item_index: int # The specific index to focus on
) -> bool:
    """
    Evaluates a FilterConfigSchema specifically for a given item within a target list.
    Condition paths are resolved from full_data, but context switches to the item
    when the target list is encountered during traversal.
    """
    group_results: List[bool] = []
    for group in config.condition_groups:
        condition_results: List[bool] = []
        for condition in group.conditions:
            # Always start evaluation context from full_data, but pass target context info
            result = evaluate_condition_recursive(
                full_data, # Start context from root
                full_data,
                condition,
                config.nested_list_logical_operator,
                target_list_instance=target_list_instance, # Identify target list
                target_item_index=item_index         # Specify which item index
            )
            condition_results.append(result)
        group_results.append(all(condition_results) if group.logical_operator == LogicalOperator.AND else any(condition_results))
    # Combine group results
    return all(group_results) if config.group_logical_operator == LogicalOperator.AND else any(group_results)

# **** Keep evaluate_filter_config_generic for non-list-item evaluation ****
def evaluate_filter_config_generic(
    initial_context: Any, # Usually the full data dict
    config: Union[FilterConfigSchema, IfElseConditionConfig]
) -> bool:
    """
    Evaluates a config block against a given context using the simplified recursive evaluator.
    Used for object-level filtering and IfElse node tags.
    """
    group_results: List[bool] = []
    for group in config.condition_groups:
        condition_results: List[bool] = []
        for condition in group.conditions:
            # Call recursive func without target list context
            result = evaluate_condition_recursive(
                initial_context, # Start relative to this context
                initial_context if isinstance(initial_context, dict) else {}, # Pass context as full_data ref
                condition,
                config.nested_list_logical_operator
                # No target_list_instance or target_item_index
            )
            condition_results.append(result)
        group_results.append(all(condition_results) if group.logical_operator == LogicalOperator.AND else any(condition_results))
    # Combine group results
    return all(group_results) if config.group_logical_operator == LogicalOperator.AND else any(group_results)


# --- Helper functions _remove_nested_path, _get_nested_obj (Unchanged) ---
def _remove_nested_path(data: Any, field_path: str) -> bool:
    parts = field_path.split('.');
    if not parts or not field_path: return False
    target_obj = data; final_key_or_index = parts[-1]
    for part in parts[:-1]:
        if isinstance(target_obj, dict):
            if part in target_obj: target_obj = target_obj[part]
            else: return False
        elif isinstance(target_obj, list):
            try:
                idx = int(part);
                if 0 <= idx < len(target_obj): target_obj = target_obj[idx]
                else: return False
            except (ValueError, TypeError): return False
        else: return False
    if isinstance(target_obj, dict):
        if final_key_or_index in target_obj:
            try: del target_obj[final_key_or_index]; return True
            except Exception: return False
    elif isinstance(target_obj, list):
        try:
            idx = int(final_key_or_index)
            if 0 <= idx < len(target_obj):
                try: del target_obj[idx]; return True
                except Exception: return False
        except (ValueError, TypeError): pass
    return False

def _get_nested_obj(data: Any, field_path: str) -> Tuple[Any, bool]:
    current = data; parts = field_path.split('.');
    if not field_path: return data, True
    for part in parts:
        if isinstance(current, dict):
            if part in current: current = current[part]
            else: return None, False
        elif isinstance(current, list):
            try:
                idx = int(part);
                if 0 <= idx < len(current): current = current[idx]
                else: return None, False
            except (ValueError, TypeError): return None, False
        else: return None, False
    return current, True

# ==============================================
# --- NODE IMPLEMENTATIONS - V9 REVISION ---
# ==============================================

class FilterNode(BaseDynamicNode):
    node_name: ClassVar[str] = "filter_node"
    node_version: ClassVar[str] = "0.3.5" # Version bump
    env_flag: ClassVar[str] = EnvFlag.PROD
    input_schema_cls: Type[DynamicSchema] = DynamicSchema
    output_schema_cls: Type[FilterOutputSchema] = FilterOutputSchema
    config_schema_cls: Type[FilterTargets] = FilterTargets
    config: FilterTargets

    def _prepare_input_data(self, input_data: Union[DynamicSchema, Dict[str, Any]]) -> Dict[str, Any]:
         if isinstance(input_data, dict): return copy.deepcopy(input_data)
         return input_data.model_dump() if hasattr(input_data, "model_dump") else dict(input_data)

    def _get_config(self, config_override: Optional[Union[Dict[str, Any], FilterTargets]]) -> FilterTargets:
        # ... (implementation unchanged) ...
        config_to_use = config_override or self.config
        if isinstance(config_to_use, FilterTargets): return config_to_use
        if isinstance(config_to_use, dict):
             try: return self.config_schema_cls(**config_to_use)
             except Exception as e: raise ValueError(f"Invalid config override: {e}") from e
        if isinstance(self.config, dict) and config_override is None:
             try: return self.config_schema_cls(**self.config)
             except Exception as e: raise ValueError(f"Invalid instance config: {e}") from e
        raise TypeError(f"Config must be dict or FilterTargets, got {type(config_to_use).__name__}")


    def process(self, input_data: Union[DynamicSchema, Dict[str, Any]], config: Optional[Union[Dict[str, Any], FilterTargets]] = None, *args: Any, **kwargs: Any) -> FilterOutputSchema:
        input_dict = self._prepare_input_data(input_data)
        try:
            active_config = self._get_config(config)
            result_data = copy.deepcopy(input_dict) # Operate on a copy

            targets_for_removal: List[str] = []
            # Store tuple: (config, original_list_instance, target_list_path_str)
            list_filter_targets: List[Tuple[FilterConfigSchema, List[Any], str]] = []
            processed_list_instances = set()

            # --- Pass 1: Evaluate all targets against ORIGINAL data ---
            for target_config in active_config.targets:
                current_filter_target = target_config.filter_target
                if isinstance(current_filter_target, str): current_filter_target = current_filter_target.strip()

                # Use generic evaluator (no list target context) for initial check
                passed = evaluate_filter_config_generic(input_dict, target_config)

                if current_filter_target is None: # Object-level
                    if not passed: return FilterOutputSchema(filtered_data=None)
                elif not passed: # Target condition failed
                    target_obj, found = _get_nested_obj(input_dict, current_filter_target)
                    if found and isinstance(target_obj, list):
                         list_id = id(target_obj)
                         if list_id not in processed_list_instances:
                             list_filter_targets.append((target_config, target_obj, current_filter_target))
                             processed_list_instances.add(list_id)
                    elif found: # Exists but not list
                         is_list_target = any(lt[2] == current_filter_target for lt in list_filter_targets)
                         if not is_list_target: targets_for_removal.append(current_filter_target)

            # Reset for Pass 2
            processed_list_instances = set()

            # --- Pass 2: Apply Targeted List Filtering ---
            for list_config, original_list_instance, target_list_path in list_filter_targets:
                list_id = id(original_list_instance)
                if list_id in processed_list_instances: continue

                target_list_in_result, found_in_result = _get_nested_obj(result_data, target_list_path)
                if not (found_in_result and isinstance(target_list_in_result, list)): continue

                indices_to_remove = []
                # Store original length before modification
                original_length = len(target_list_in_result)
                for i in range(original_length - 1, -1, -1):
                    # Ensure index is still valid for the *original* list instance check
                    # Although we modify target_list_in_result, the evaluation logic needs
                    # the original list instance to be passed for identity check during recursion.
                    if i >= len(original_list_instance): continue # Should not happen if lists are same initially

                    # **** Use the dedicated helper for list item evaluation ****
                    item_passed = evaluate_filter_config_for_list_item(
                        input_dict, # Always pass full original data
                        list_config,
                        original_list_instance, # Pass list instance for ID check
                        i                       # Pass index
                    )
                    if not item_passed:
                        indices_to_remove.append(i)

                # Remove items by index, highest index first
                for index in sorted(indices_to_remove, reverse=True):
                    try: del target_list_in_result[index]
                    except IndexError: print(f"Warning: Index {index} out of bounds on removal for {target_list_path}.")

                processed_list_instances.add(list_id)

            # --- Pass 3: Apply Simple Path Removals ---
            for target_path in sorted(list(set(targets_for_removal)), key=len, reverse=True):
                _remove_nested_path(result_data, target_path)

            return FilterOutputSchema(filtered_data=result_data)
        except Exception as e:
             print(f"Error processing FilterNode: {e}"); traceback.print_exc()
             return FilterOutputSchema(filtered_data=None)


class IfElseNode(BaseDynamicNode):
    node_name: ClassVar[str] = "if_else_node"
    node_version: ClassVar[str] = "0.3.5"
    env_flag: ClassVar[str] = EnvFlag.PROD
    input_schema_cls: Type[DynamicSchema] = DynamicSchema
    output_schema_cls: Type[IfElseOutputSchema] = IfElseOutputSchema
    config_schema_cls: Type[IfElseConfigSchema] = IfElseConfigSchema
    config: IfElseConfigSchema

    def _prepare_input_data(self, input_data: Union[DynamicSchema, Dict[str, Any]]) -> Dict[str, Any]:
         if isinstance(input_data, dict): return copy.deepcopy(input_data)
         return input_data.model_dump() if hasattr(input_data, "model_dump") else dict(input_data)

    def _get_config(self, config_override: Optional[Union[Dict[str, Any], IfElseConfigSchema]]) -> IfElseConfigSchema:
        # ... (implementation unchanged) ...
        config_to_use = config_override or self.config
        if isinstance(config_to_use, IfElseConfigSchema): return config_to_use
        if isinstance(config_to_use, dict):
             try: return self.config_schema_cls(**config_to_use)
             except Exception as e: raise ValueError(f"Invalid config override: {e}") from e
        if isinstance(self.config, dict) and config_override is None:
             try: return self.config_schema_cls(**self.config)
             except Exception as e: raise ValueError(f"Invalid instance config: {e}") from e
        raise TypeError(f"Config must be dict or IfElseConfigSchema, got {type(config_to_use).__name__}")


    # Uses simplified evaluate_filter_config_generic
    def process(self, input_data: Union[DynamicSchema, Dict[str, Any]], config: Optional[Union[Dict[str, Any], IfElseConfigSchema]] = None, *args: Any, **kwargs: Any) -> IfElseOutputSchema:
        input_dict = self._prepare_input_data(input_data)
        try:
            active_config = self._get_config(config)
            tag_results: Dict[str, bool] = {}
            for tagged_conf in active_config.tagged_conditions:
                # Use generic evaluator, context starts from input_dict
                result = evaluate_filter_config_generic(input_dict, tagged_conf)
                tag_results[tagged_conf.tag] = result

            final_result = False
            if tag_results:
                op = active_config.branch_logic_operator
                final_result = all(tag_results.values()) if op == LogicalOperator.AND else any(tag_results.values())
            branch = BranchPath.TRUE_BRANCH if final_result else BranchPath.FALSE_BRANCH
            return IfElseOutputSchema(data=input_dict, tag_results=tag_results, condition_result=final_result, branch=branch)
        except Exception as e:
             print(f"Error processing IfElseNode: {e}"); traceback.print_exc()
             return IfElseOutputSchema(data=input_dict, tag_results={}, condition_result=False, branch=BranchPath.FALSE_BRANCH)

# --- Example Usage Block (Optional) ---
if __name__ == '__main__':
    pass
