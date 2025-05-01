"""
Node for merging multiple JSON objects or lists of objects based on specified strategies.

This node allows combining data from different parts of the input payload
according to configurable selection, mapping, and reduction rules.

Key Features:
- Selects objects/lists from multiple input paths.
- Merges objects sequentially based on priority (left-to-right).
- Supports explicit key mapping (renaming/selecting specific source keys).
- Handles unspecified keys via AUTO_MERGE or IGNORE strategies.
- Provides various reducers for handling key collisions:
    - REPLACE_LEFT, REPLACE_RIGHT
    - APPEND, EXTEND (for lists)
    - COMBINE_IN_LIST
    - SUM, MIN, MAX (for numerical aggregation)
    - SIMPLE_MERGE_REPLACE, SIMPLE_MERGE_AGGREGATE (merge top-level dict keys)
    - NESTED_MERGE_REPLACE, NESTED_MERGE_AGGREGATE (recursively merge dict keys)
- Supports nested destination keys (e.g., "output.user.id").
- Optional Single Field Transformations (post-merge operations like AVERAGE, MULTIPLY, DIVIDE, ADD, SUBTRACT).
- Configurable error handling during reduction and transformation.
- Modular design for reducers and transformations, making it easy to extend.
"""

import copy
import traceback
from enum import Enum
from typing import Any, Dict, List, Optional, Union, ClassVar, Literal, Tuple, Set, Type, Callable
import numbers # Import numbers module for checking numeric types
from global_config.logger import get_prefect_or_regular_python_logger

from pydantic import Field, model_validator, field_validator, BaseModel, ValidationError, validator

from kiwi_app.workflow_app.constants import LaunchStatus
from workflow_service.registry.schemas.base import BaseSchema
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema, BaseDynamicNode
# Reuse helpers from transform_node - assuming they are accessible
# If not, they need to be copied or imported properly.
# For now, let's assume they are defined within this file or imported.

# ==============================================
# --- HELPER FUNCTIONS (Assume these exist) ---
# ==============================================

def _get_nested_obj(data: Union[Dict[str, Any], List[Any]], path: str) -> Tuple[Any, bool]:
    """
    Retrieves a value from a nested dictionary or list using dot-notation path.

    Handles paths containing integer indices for lists. e.g., "data.items.0.name".

    Args:
        data (Union[Dict[str, Any], List[Any]]): The dictionary or list to search within.
        path (str): Dot-notation path (e.g., "user.profile.email", "items.0.id").

    Returns:
        Tuple[Any, bool]: A tuple containing the retrieved value and a boolean indicating
                          if the path was found. Returns (None, False) if not found.
    """
    if not path:
        return None, False

    parts = path.split('.')
    current_level: Any = data
    for i, part in enumerate(parts):
        if isinstance(current_level, dict):
            if part in current_level:
                current_level = current_level[part]
            else:
                return None, False
        elif isinstance(current_level, list):
            try:
                index = int(part)
                if 0 <= index < len(current_level):
                    current_level = current_level[index]
                else:
                    # Index out of bounds
                    return None, False
            except (ValueError, TypeError):
                # Part is not a valid integer index for the list
                return None, False
        else:
            # Current level is not a dict or list, cannot traverse further
            return None, False
    return current_level, True


def _set_nested_obj(data: Dict[str, Any], path: str, value: Any, create_missing: bool = True) -> bool:
    """
    Sets a value at a specified path within a nested dictionary structure.
    Handles creation of intermediate dictionaries.

    Args:
        data (Dict[str, Any]): The dictionary to modify.
        path (str): Dot-notation path where the value should be set (e.g., "user.profile.email").
        value (Any): The value to set at the specified path.
        create_missing (bool): If True, create intermediate dictionaries if they don't exist. Defaults to True.

    Returns:
        bool: True if the value was successfully set, False otherwise.

    Raises:
        TypeError: If trying to set a key on a non-dictionary intermediate path element.
    """
    logger = get_prefect_or_regular_python_logger(f"{__name__}")
    if not path:
        logger.warning("Warning: Attempted to set value with an empty path. This is not supported.")
        return False

    parts = path.split('.')
    current_level = data
    final_key = parts[-1]

    for i, part in enumerate(parts[:-1]):
        # If the part exists and is a dictionary, move to the next level
        if part in current_level and isinstance(current_level[part], dict):
            current_level = current_level[part]
        # If the part exists but is NOT a dictionary
        elif part in current_level and not isinstance(current_level[part], dict):
             if create_missing:
                 # Overwrite the existing non-dict value if create_missing is true
                 logger.warning(f"Warning: Overwriting non-dictionary element at path part '{part}' in path '{path}'.")
                 current_level[part] = {}
                 current_level = current_level[part]
             else:
                 # Cannot proceed if not creating missing and structure conflicts
                 raise TypeError(f"Cannot create nested structure. Element at path "
                                 f"{'.'.join(parts[:i+1])} is not a dictionary (found type: {type(current_level[part]).__name__}) "
                                 f"and create_missing is False.")
        # If the part does NOT exist
        elif part not in current_level:
            if create_missing:
                current_level[part] = {}
                current_level = current_level[part]
            else:
                # Path does not exist, and we're not creating it
                logger.warning(f"Warning: Path part '{part}' not found in path '{path}' and create_missing is False.")
                return False

    # Ensure the final part can be set (i.e., current_level is a dict)
    if not isinstance(current_level, dict):
         raise TypeError(f"Cannot set key '{final_key}'. Parent path '{'.'.join(parts[:-1])}' "
                         f"does not point to a dictionary (found type: {type(current_level).__name__}).")

    current_level[final_key] = value
    return True

# ==============================================
# --- ENUMS, TRANSFORMATION, REDUCER FUNCTIONS ---
# ==============================================

class ErrorHandlingStrategy(str, Enum):
    """Strategy for handling errors during reduction or transformation."""
    COALESCE_KEEP_LEFT = "coalesce_keep_left" # Keep the existing left value if reduction fails
    COALESCE_KEEP_NON_EMPTY = "coalesce_keep_non_empty" # Keep the existing left value if reduction fails
    SKIP_OPERATION = "skip_operation"       # Skip the reduction/transformation if it fails
    SET_NONE = "set_none"                   # Set the destination field to None if it fails
    FAIL_NODE = "fail_node"                 # Raise exception, causing the node to fail

class UnspecifiedKeysStrategy(str, Enum):
    """Strategy for handling keys not explicitly defined in mappings."""
    AUTO_MERGE = "auto_merge" # Merge keys with the same name using the default reducer
    IGNORE = "ignore"         # Ignore keys not explicitly mapped

class DictMergeMode(str, Enum):
    """Mode for merging dictionaries in reducers."""
    REPLACE = "replace"     # Right value replaces left if not None
    AGGREGATE = "aggregate" # Combine non-None values into a list

class ReducerType(str, Enum):
    """Defines how to combine values when keys collide during merging."""
    REPLACE_RIGHT = "replace_right" # Default: Rightmost value overwrites leftmost
    REPLACE_LEFT = "replace_left"   # Leftmost value is kept, rightmost ignored
    APPEND = "append"               # Append right value to left list (expects lists)
    EXTEND = "extend"               # Extend left list with right list (expects lists)
    COMBINE_IN_LIST = "combine_in_list" # Create a list [left_value, right_value]
    SUM = "sum"                     # Add right value to left value (expects numbers)
    MIN = "min"                     # Take the minimum of left and right values (expects numbers)
    MAX = "max"                     # Take the maximum of left and right values (expects numbers)
    SIMPLE_MERGE_REPLACE = "simple_merge_replace"     # Merge top-level dict keys, replacing non-None values
    SIMPLE_MERGE_AGGREGATE = "simple_merge_aggregate" # Merge top-level dict keys, aggregating non-None values in lists
    NESTED_MERGE_REPLACE = "nested_merge_replace"     # Recursively merge dict keys, replacing non-None values
    NESTED_MERGE_AGGREGATE = "nested_merge_aggregate" # Recursively merge dict keys, aggregating non-None values in lists
    # Add CONCATENATE later if needed

class SingleFieldOperationType(str, Enum):
    """Defines operations that can be applied to a field after merging."""
    AVERAGE = "average"             # Calculate average (expects final value to be sum, uses tracked count)
    MULTIPLY = "multiply"           # Multiply the final value by an operand
    DIVIDE = "divide"               # Divide the final value by an operand
    ADD = "add"                     # Add an operand to the final value
    SUBTRACT = "subtract"           # Subtract an operand from the final value
    RECURSIVE_FLATTEN_LIST = "recursive_flatten_list"   # Flatten nested lists into a single-level list
    LIMIT_LIST = "limit_list"       # Limit the final value to a specified number of items
    SORT_LIST = "sort_list"         # Sort a list based on key(s) and order

# --- Configuration Schemas (Forward declaration for type hints) ---
class SingleFieldTransformationSchema(BaseModel):
    pass

# --- Type Aliases for Callables ---
ReducerFunc = Callable[[Any, Any], Any]
TransformationFunc = Callable[[Any, SingleFieldTransformationSchema, Optional[int]], Any]

# --- Dictionary Merge Helpers ---

def _simple_merge(left_dict: Dict[str, Any], right_dict: Dict[str, Any], mode: DictMergeMode) -> Dict[str, Any]:
    """
    Merges top-level keys from right_dict into left_dict based on mode.
    Modifies left_dict in place and returns it.
    """
    if not isinstance(left_dict, dict) or not isinstance(right_dict, dict):
        raise TypeError(f"Simple merge requires dictionary inputs. Got {type(left_dict)}, {type(right_dict)}")

    for key, right_val in right_dict.items():
        if right_val is None:
            continue # Skip None values from the right side

        if key not in left_dict:
            # Key only exists in right_dict, add it
            if mode == DictMergeMode.AGGREGATE:
                left_dict[key] = [right_val] # Start a list
            else: # REPLACE mode
                left_dict[key] = right_val
        else:
            # Key exists in both
            left_val = left_dict[key]
            if mode == DictMergeMode.AGGREGATE:
                if isinstance(left_val, list):
                    # if right_val not in left_val: # Avoid duplicates? User might want them... append for now.
                    left_val.append(right_val)
                else:
                    # Convert left to list if it wasn't already
                    left_dict[key] = [left_val, right_val]
            else: # REPLACE mode
                left_dict[key] = right_val # Replace with non-None right value
    return left_dict

def _nested_merge(left_data: Any, right_data: Any, mode: DictMergeMode) -> Any:
    """
    Recursively merges right_data into left_data based on the specified mode.

    Handles nested dictionaries and lists. Returns the merged result.
    - In 'REPLACE' mode, values from right_data overwrite corresponding values
      in left_data. If keys are dictionaries, they are merged recursively.
      None values in right_data do not overwrite existing values.
    - In 'AGGREGATE' mode:
        - Dictionaries are merged recursively (keys combined).
        - Lists are extended (right list appended to left list, non-None items).
        - If types differ or are primitives, values are combined into a list
          (e.g., merging 1 and 2 results in [1, 2]; merging 1 and {'a': 1} results in [1, {'a': 1}]).
        - None values from right_data are ignored during aggregation.

    Args:
        left_data (Any): The base data structure (often a dictionary or list).
        right_data (Any): The data structure to merge into left_data.
        mode (DictMergeMode): The merge mode ('replace' or 'aggregate').

    Returns:
        Any: The merged data structure. Note that for mutable inputs like dictionaries
             passed in the 'left_data' argument during recursive calls, modifications
             might occur partially in-place, although the function generally returns
             new objects (especially via deepcopy at the start of dict merges).
    """
    logger = get_prefect_or_regular_python_logger(f"{__name__}._nested_merge") # Add logger

    # --- AGGREGATE Mode Logic ---
    if mode == DictMergeMode.AGGREGATE:
        # 1. Both are dictionaries: Recursively merge keys
        if isinstance(left_data, dict) and isinstance(right_data, dict):
            # Start with a deep copy of the left dictionary to avoid modifying the original
            # during the merge process, especially important for nested structures.
            merged_dict = copy.deepcopy(left_data)
            for key, right_val in right_data.items():
                 # Retrieve the corresponding value from the merged dictionary (initially left_data's copy).
                 left_val = merged_dict.get(key)

                 if left_val is not None:
                      # Key exists in both left and right: merge their values recursively.
                      merged_dict[key] = _nested_merge(left_val, right_val, mode)
                 elif right_val is not None: # Key only exists in right (and right value is not None)
                      # Add the new key-value pair from right_data.
                      # A deepcopy is used here to ensure independence if right_val is mutable.
                      merged_dict[key] = copy.deepcopy(right_val)
                 # If right_val is None and the key wasn't in left, it's simply skipped.
            return merged_dict

        # 2. Both are lists: Extend left with non-None items from right
        elif isinstance(left_data, list) and isinstance(right_data, list):
            # Create a copy of the left list.
            new_list = copy.copy(left_data)
            # Extend the new list with items from the right list, filtering out None values.
            new_list.extend(item for item in right_data if item is not None)
            return new_list

        # 3. Aggregating disparate types or primitives into a list
        elif right_data is not None: # Only aggregate if right_data has a value
             final_right_data = copy.deepcopy(right_data) if isinstance(right_data, (dict, list)) else right_data
             if isinstance(left_data, list):
                 # Left is already a list: Create a copy and append the right value.
                 new_list = copy.copy(left_data)
                 # Deepcopy right_data if it's mutable to avoid shared references in the list.
                 new_list.append(final_right_data)
                 return new_list
             else:
                 # Left is not a list: Create a new list containing both left and right values.
                 # Deepcopy right_data if mutable. Left_data is assumed to be handled correctly
                 # as it came from a previous state or initial input.
                 
                 ret_data = []
                 if left_data is not None:
                     ret_data.append(left_data)
                 if final_right_data is not None:
                     ret_data.append(final_right_data)
                 return ret_data
        else:
             # Right_data is None: Aggregation results in keeping the left_data unchanged.
             return left_data

    # --- REPLACE Mode Logic ---
    elif mode == DictMergeMode.REPLACE:
        # 1. Both are dictionaries: Recursively merge keys, replacing values
        if isinstance(left_data, dict) and isinstance(right_data, dict):
            # Start with a deep copy of the left dictionary.
            merged_dict = copy.deepcopy(left_data)
            for key, right_val in right_data.items():
                # In REPLACE mode, skip merging if the right value is None.
                if right_val is None:
                    continue

                if key not in merged_dict:
                    # Key only in right: Add it to the merged dictionary. Deepcopy if mutable.
                    merged_dict[key] = copy.deepcopy(right_val) if isinstance(right_val, (dict, list)) else right_val
                else:
                    # Key exists in both: Recursively merge the values using REPLACE mode.
                    left_val = merged_dict[key]
                    merged_dict[key] = _nested_merge(left_val, right_val, mode)
            return merged_dict

        # 2. Base case: Right replaces Left if right is not None
        elif right_data is not None:
            # Return a deep copy if the right data is mutable to prevent aliasing issues later.
            return copy.deepcopy(right_data) if isinstance(right_data, (dict, list)) else right_data

        # 3. Right is None, keep Left
        else:
            # Return the left data as is. If it was mutable, the caller should be aware.
            return left_data

    # --- Fallback ---
    # This part should ideally not be reached if 'mode' is always a valid DictMergeMode enum.
    # However, as a safeguard, return left_data.
    else:
        logger.warning(f"Warning: Unhandled merge mode '{mode}'. Returning left_data.")
        return left_data


# --- Reducer Implementations ---

def _reduce_replace_right(left_val: Any, right_val: Any, is_init: bool=False) -> Any:
    return right_val

def _reduce_replace_left(left_val: Any, right_val: Any, is_init: bool=False) -> Any:
    if is_init: return right_val
    return left_val

def _reduce_append(left_val: Any, right_val: Any, is_init: bool=False) -> Any:
    logger = get_prefect_or_regular_python_logger(f"{__name__}")
    if is_init: return right_val
    if isinstance(left_val, list):
        new_list = copy.copy(left_val)
        new_list.append(right_val)
        return new_list
    else:
        logger.warning(f"Warning: APPEND reducer called with non-list left value ({type(left_val).__name__}). Creating new list.")
        return [left_val, right_val]

def _reduce_extend(left_val: Any, right_val: Any, is_init: bool=False) -> Any:
    if is_init: return right_val
    if isinstance(left_val, list) and isinstance(right_val, list):
        new_list = copy.copy(left_val)
        new_list.extend(right_val)
        return new_list
    else:
        raise TypeError(f"EXTEND reducer requires both values to be lists. Got {type(left_val).__name__} and {type(right_val).__name__}.")

def _reduce_combine_in_list(left_val: Any, right_val: Any, is_init: bool=False) -> Any:
    # print(f"\n\ncombine_in_list: left_val={left_val}, right_val={right_val}, is_init={is_init}\n\n")
    if is_init: return [right_val]
    if (not left_val) or (not right_val):
        ret_val = left_val or right_val
        return [ret_val] if right_val else ret_val
    
    if isinstance(left_val, list):
        new_list = copy.copy(left_val)
        new_list.append(right_val)
        return new_list
    else:
        return [left_val, right_val]

def _reduce_sum(left_val: Any, right_val: Any, is_init: bool=False) -> Any:
    if is_init: return right_val
    if isinstance(left_val, numbers.Number) and isinstance(right_val, numbers.Number):
        return left_val + right_val
    else:
        raise TypeError(f"SUM reducer requires both values to be numeric. Got {type(left_val).__name__} and {type(right_val).__name__}.")

def _reduce_min(left_val: Any, right_val: Any, is_init: bool=False) -> Any:
    if is_init: return right_val
    try: return min(left_val, right_val)
    except TypeError: raise TypeError(f"MIN reducer requires comparable types. Got {type(left_val).__name__} and {type(right_val).__name__}.")

def _reduce_max(left_val: Any, right_val: Any, is_init: bool=False) -> Any:
    if is_init: return right_val
    try: return max(left_val, right_val)
    except TypeError: raise TypeError(f"MAX reducer requires comparable types. Got {type(left_val).__name__} and {type(right_val).__name__}.")

def _reduce_simple_merge_replace(left_val: Any, right_val: Any, is_init: bool=False) -> Any:
    if is_init: return right_val
    if not isinstance(left_val, dict) or not isinstance(right_val, dict):
        raise TypeError(f"SIMPLE_MERGE_REPLACE requires dict inputs. Got {type(left_val)}, {type(right_val)}")
    # Deep copy left to avoid modifying it if it came from a previous step within the *same* merge sequence
    merged = _simple_merge(copy.deepcopy(left_val), right_val, mode=DictMergeMode.REPLACE)
    return merged

def _reduce_simple_merge_aggregate(left_val: Any, right_val: Any, is_init: bool=False) -> Any:
    if is_init: return right_val
    if not isinstance(left_val, dict) or not isinstance(right_val, dict):
        raise TypeError(f"SIMPLE_MERGE_AGGREGATE requires dict inputs. Got {type(left_val)}, {type(right_val)}")
    merged = _simple_merge(copy.deepcopy(left_val), right_val, mode=DictMergeMode.AGGREGATE)
    return merged

def _reduce_nested_merge_replace(left_val: Any, right_val: Any, is_init: bool=False) -> Any:
    if is_init: return right_val
    # Nested merge handles non-dict types gracefully in its logic
    merged = _nested_merge(left_val, right_val, mode=DictMergeMode.REPLACE)
    return merged

def _reduce_nested_merge_aggregate(left_val: Any, right_val: Any, is_init: bool=False) -> Any:
    if is_init: return right_val
    merged = _nested_merge(left_val, right_val, mode=DictMergeMode.AGGREGATE)
    return merged

# Map enum values to functions
REDUCER_FUNCTIONS: Dict[ReducerType, ReducerFunc] = {
    ReducerType.REPLACE_RIGHT: _reduce_replace_right,
    ReducerType.REPLACE_LEFT: _reduce_replace_left,
    ReducerType.APPEND: _reduce_append,
    ReducerType.EXTEND: _reduce_extend,
    ReducerType.COMBINE_IN_LIST: _reduce_combine_in_list,
    ReducerType.SUM: _reduce_sum,
    ReducerType.MIN: _reduce_min,
    ReducerType.MAX: _reduce_max,
    ReducerType.SIMPLE_MERGE_REPLACE: _reduce_simple_merge_replace,
    ReducerType.SIMPLE_MERGE_AGGREGATE: _reduce_simple_merge_aggregate,
    ReducerType.NESTED_MERGE_REPLACE: _reduce_nested_merge_replace,
    ReducerType.NESTED_MERGE_AGGREGATE: _reduce_nested_merge_aggregate,
}

# --- Transformation Implementations ---

def _transform_average(current_value: Any, config: SingleFieldTransformationSchema, count: Optional[int]) -> Any:
    """Transformation: Calculate average."""
    if count is None or count <= 0:
        raise ZeroDivisionError("Cannot calculate average, count is zero or undefined.")
    if not isinstance(current_value, numbers.Number):
        raise TypeError(f"Cannot calculate average. Value is not numeric ({type(current_value).__name__}).")
    return current_value / count

def _transform_recursive_flatten_list(current_value: Any, config: SingleFieldTransformationSchema, count: Optional[int]) -> Any:
    """
    Transformation: Flatten nested lists into a single-level list.
    
    This transformation recursively flattens nested lists while preserving non-list elements.
    For example:
    - [1, [2, 3], [[4, 5], 6]] becomes [1, 2, 3, 4, 5, 6]
    - [1, {'a': [2, 3]}, [4, 5]] becomes [1, {'a': [2, 3]}, 4, 5]
    
    Args:
        current_value: The value to flatten, expected to be a list
        config: Configuration parameters for the transformation
        count: Optional count of items (not used in this transformation)
        
    Returns:
        A flattened list containing all non-list elements from the original structure
        
    Raises:
        TypeError: If the input value is not a list
    """
    if not isinstance(current_value, list):
        raise TypeError(f"FLATTEN_LIST requires a list input. Got {type(current_value).__name__}.")
    
    result = []
    
    def _flatten(items):
        for item in items:
            if isinstance(item, list):
                # Recursively flatten nested lists
                _flatten(item)
            else:
                # Append non-list items directly
                result.append(item)
    
    _flatten(current_value)
    return result


def _transform_multiply(current_value: Any, config: SingleFieldTransformationSchema, count: Optional[int]) -> Any:
    """Transformation: Multiply value by operand."""
    operand = config.operand # Already validated to be numeric
    if not isinstance(current_value, numbers.Number):
        raise TypeError(f"MULTIPLY requires a numeric value. Got {type(current_value).__name__}.")
    return current_value * operand

def _transform_divide(current_value: Any, config: SingleFieldTransformationSchema, count: Optional[int]) -> Any:
    """Transformation: Divide value by operand."""
    operand = config.operand # Already validated to be numeric
    if operand == 0:
        raise ZeroDivisionError("Division by zero in transformation.")
    if not isinstance(current_value, numbers.Number):
        raise TypeError(f"DIVIDE requires a numeric value. Got {type(current_value).__name__}.")
    return current_value / operand

def _transform_add(current_value: Any, config: SingleFieldTransformationSchema, count: Optional[int]) -> Any:
    """Transformation: Add operand to value."""
    operand = config.operand # Already validated to be numeric
    if not isinstance(current_value, numbers.Number):
        raise TypeError(f"ADD requires a numeric value. Got {type(current_value).__name__}.")
    return current_value + operand

def _transform_subtract(current_value: Any, config: SingleFieldTransformationSchema, count: Optional[int]) -> Any:
    """Transformation: Subtract operand from value."""
    operand = config.operand # Already validated to be numeric
    if not isinstance(current_value, numbers.Number):
        raise TypeError(f"SUBTRACT requires a numeric value. Got {type(current_value).__name__}.")
    return current_value - operand

def _transform_limit_list(current_value: Any, config: SingleFieldTransformationSchema, count: Optional[int]) -> Any:
    """
    Transformation: Limit a list to a specified number of items.
    
    Args:
        current_value: The list to limit
        config: Configuration containing the operand (max items to keep)
        count: Not used for this transformation
        
    Returns:
        List limited to the specified number of items
        
    Raises:
        TypeError: If the input value is not a list
    """
    if not isinstance(current_value, list):
        raise TypeError(f"LIMIT_LIST requires a list input. Got {type(current_value).__name__}.")
    
    limit = int(config.operand)  # Already validated to be numeric
    return current_value[:limit]

def _transform_sort_list(current_value: Any, config: SingleFieldTransformationSchema, count: Optional[int]) -> Any:
    """
    Transformation: Sorts a list based on specified keys and order, placing None values last.

    The operand for this operation is an optional dictionary:
    {
        "key": Optional[Union[str, List[str]]],  # Dot-notation path(s) within list elements. If None, sort elements directly.
        "order": Optional[Union[str, int]]      # 'ascending', 1 (default) or 'descending', -1.
    }
    If operand is None or empty, defaults to direct element sorting in ascending order.

    Args:
        current_value: The list to sort.
        config: Configuration containing the optional operand dictionary.
        count: Not used for this transformation.

    Returns:
        A new list containing the sorted elements with None values placed at the end.

    Raises:
        TypeError: If the input value is not a list, if the provided operand is not a dictionary,
                   or if elements are not comparable for the given key(s).
        ValueError: If the operand format is invalid (e.g., invalid 'key' or 'order').
    """
    logger = get_prefect_or_regular_python_logger(f"{__name__}._transform_sort_list")

    if not isinstance(current_value, list):
        raise TypeError(f"SORT_LIST requires a list input. Got {type(current_value).__name__}.")

    operand = config.operand
    # Default values if operand is None or empty dict
    key_spec = None
    order_spec: Union[str, int] = "ascending" # Default sort order

    # Parse operand if it's provided and valid
    if operand is not None:
        if not isinstance(operand, dict):
             raise TypeError(f"SORT_LIST operand must be a dictionary or None. Got {type(operand).__name__}.")
        key_spec = operand.get("key")
        # Only override default order if 'order' is explicitly present in the operand
        if "order" in operand:
            order_spec = operand["order"]

    # --- Normalize Key Paths ---
    key_paths: Optional[List[str]] = None
    if isinstance(key_spec, str) and key_spec.strip():
        key_paths = [key_spec.strip()]
    elif isinstance(key_spec, list):
        key_paths = [p.strip() for p in key_spec if isinstance(p, str) and p.strip()]
        if not key_paths: # Handle list of empty strings or non-strings
            key_paths = None
    elif key_spec is not None: # If key_spec is provided but invalid type
        raise ValueError(f"Invalid 'key' format in SORT_LIST operand: must be string, list of strings, or None. Got {type(key_spec).__name__}")

    # --- Normalize Sort Order ---
    sort_reverse = False
    if isinstance(order_spec, str):
        order_lower = order_spec.lower()
        if order_lower == "descending":
            sort_reverse = True
        elif order_lower != "ascending":
            raise ValueError(f"Invalid 'order' string in SORT_LIST operand: must be 'ascending' or 'descending'. Got '{order_spec}'")
    elif isinstance(order_spec, int):
        if order_spec == -1:
            sort_reverse = True
        elif order_spec != 1:
            raise ValueError(f"Invalid 'order' integer in SORT_LIST operand: must be 1 (ascending) or -1 (descending). Got {order_spec}")
    elif order_spec is not None: # Should only be None if operand was missing 'order' or None itself
         raise ValueError(f"Invalid 'order' type in SORT_LIST operand: must be string or integer. Got {type(order_spec).__name__}")

    # --- Define Sort Key Function (Handles None Last) ---
    def get_sort_key(item: Any) -> Any:
        """
        Generates the actual key used for sorting, ensuring Nones are handled last.
        Returns a tuple where the first element indicates if the primary value is None.
        """
        def none_sort_value(item):
            return item is not None if sort_reverse else item is None
        
        if not key_paths:
            # Sort elements directly
            return (none_sort_value(item), none_sort_value(item), item)
        elif len(key_paths) == 1:
            # Sort by a single nested key
            value, _ = _get_nested_obj(item, key_paths[0])
            return (none_sort_value(value), none_sort_value(item), value)
        else:
            # Sort by multiple nested keys
            # Create a tuple of (is_none, value) for each key path
            # This ensures multi-key sort stability with Nones pushed last at each level
            key_values = tuple(_get_nested_obj(item, p)[0] for p in key_paths)
            item_none_sort_value = none_sort_value(item)
            comparison_tuple = tuple((none_sort_value(v), item_none_sort_value, v) for v in key_values)
            return comparison_tuple

    # --- Perform Sort ---
    try:
        # Use the generated key function
        sorted_list = sorted(current_value, key=get_sort_key, reverse=sort_reverse)
        logger.info(f"Successfully sorted list (None last). Original count: {len(current_value)}, Sorted count: {len(sorted_list)}")
        return sorted_list
    except TypeError as e:
        logger.error(f"TypeError during sorting (None last): {e}. Check element types and key paths.")
        raise TypeError(f"Cannot sort list: Elements are not comparable for the specified key(s) even with None handling. Original error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during sorting (None last): {e}")
        raise

# Map enum values to transformation functions
TRANSFORMATION_FUNCTIONS: Dict[SingleFieldOperationType, TransformationFunc] = {
    SingleFieldOperationType.RECURSIVE_FLATTEN_LIST: _transform_recursive_flatten_list,
    SingleFieldOperationType.AVERAGE: _transform_average,
    SingleFieldOperationType.MULTIPLY: _transform_multiply,
    SingleFieldOperationType.DIVIDE: _transform_divide,
    SingleFieldOperationType.ADD: _transform_add,
    SingleFieldOperationType.SUBTRACT: _transform_subtract,
    SingleFieldOperationType.LIMIT_LIST: _transform_limit_list,
    SingleFieldOperationType.SORT_LIST: _transform_sort_list,
}


# ==============================================
# --- CONFIGURATION SCHEMAS ---
# ==============================================

class KeyMappingSchema(BaseSchema):
    """
    Defines how a specific key in the merged output should be populated.
    """
    destination_key: Optional[str] = Field(
        None,
        description="Optional dot-notation path for the key in the merged object (e.g., 'user.id', 'final_score'). "
                    "If not provided, the first element of `source_keys` will be used."
    )
    source_keys: List[str] = Field(
        ...,
        min_length=1,
        description="List of dot-notation paths (relative to object root) to search for the value. "
                    "The first path yielding a non-None value is used. "
                    "The first element is used as `destination_key` if it's not explicitly provided."
    )

    @field_validator('source_keys')
    def source_keys_must_be_valid(cls, v: List[str]) -> List[str]:
        """Ensures source keys list is not empty and paths are not empty."""
        if not v:
            raise ValueError("Source keys list cannot be empty.")
        stripped_keys = [key.strip() for key in v if key and key.strip()]
        if not stripped_keys or len(stripped_keys) != len(v):
             raise ValueError("Source keys cannot contain empty paths.")
        return stripped_keys

    @model_validator(mode='after')
    def set_destination_key_if_none(self) -> 'KeyMappingSchema':
        """Sets the destination_key from the first source_key if it's None."""
        if self.destination_key is None:
            if self.source_keys:
                self.destination_key = self.source_keys[0]
            else:
                raise ValueError("Cannot determine destination_key: source_keys is empty.")
        if not self.destination_key or not self.destination_key.strip():
             raise ValueError("Destination key cannot be empty after defaulting.")
        self.destination_key = self.destination_key.strip()
        return self


class MapPhaseConfigSchema(BaseSchema):
    """Configuration for the mapping phase of a merge operation."""
    key_mappings: List[KeyMappingSchema] = Field(
        default_factory=list,
        description="Explicit mappings for specific destination keys (using dot-notation)."
    )
    unspecified_keys_strategy: UnspecifiedKeysStrategy = Field(
        default=UnspecifiedKeysStrategy.AUTO_MERGE,
        description="Strategy for handling keys not covered by explicit mappings."
    )

class ReducePhaseConfigSchema(BaseSchema):
    """Configuration for the reduction phase of a merge operation."""
    reducers: Dict[str, ReducerType] = Field(
        default_factory=dict,
        description="Specific reducer types for destination keys (dot-notation paths override default)."
    )
    default_reducer: ReducerType = Field(
        default=ReducerType.REPLACE_RIGHT,
        description="Default reducer type to use when keys collide or for auto-merged keys."
    )
    error_strategy: ErrorHandlingStrategy = Field(
        default=ErrorHandlingStrategy.COALESCE_KEEP_NON_EMPTY,
        description="How to handle errors (e.g., TypeError, ZeroDivisionError) during reduction."
    )

# Moved definition earlier for type hints
class SingleFieldTransformationSchema(BaseSchema):
    """Configuration for a single post-merge transformation."""
    operation_type: SingleFieldOperationType = Field(..., description="The type of operation to perform.")
    operand: Optional[Any] = Field(
        None,
        description="Operand for the operation. Type depends on 'operation_type'. "
                    "Required for MULTIPLY, DIVIDE, ADD, SUBTRACT, LIMIT_LIST (numeric operand); "
                    "Optional for SORT_LIST (dict operand: {'key': Optional[str|List[str]], 'order': Optional[str|int]}); "
                    "Not used for AVERAGE, RECURSIVE_FLATTEN_LIST."
    )

    @model_validator(mode='after')
    def check_operand_requirements(self) -> 'SingleFieldTransformationSchema':
        """Validates that operand is provided and has the correct type if required by the operation type."""
        op_type = self.operation_type
        operand = self.operand # Use self.operand for checks

        # Numeric operand operations
        if op_type in [
            SingleFieldOperationType.MULTIPLY,
            SingleFieldOperationType.DIVIDE,
            SingleFieldOperationType.ADD,
            SingleFieldOperationType.SUBTRACT,
            SingleFieldOperationType.LIMIT_LIST
        ]:
            if operand is None:
                 raise ValueError(f"Operand must be provided for operation type '{op_type}'.")
            if not isinstance(operand, numbers.Number):
                 raise TypeError(f"Operand must be numeric for operation type '{op_type}'. Got {type(operand).__name__}.")
            # Specific check for DIVIDE
            if op_type == SingleFieldOperationType.DIVIDE and operand == 0:
                 raise ValueError("Operand cannot be zero for DIVIDE operation.")
            # Specific check for LIMIT_LIST
            if op_type == SingleFieldOperationType.LIMIT_LIST and (not isinstance(operand, int) or operand < 0):
                 raise ValueError("Operand must be a non-negative integer for LIMIT_LIST operation.")

        # Sort list operation (optional dict operand)
        elif op_type == SingleFieldOperationType.SORT_LIST:
            # Operand is optional (can be None). If provided, it MUST be a dictionary.
            if operand is not None and not isinstance(operand, dict):
                 raise TypeError(f"Operand for operation type '{op_type}' must be a dictionary or None. Got {type(operand).__name__}.")
            # Further validation of the dict structure (key, order) happens within _transform_sort_list

        # Operations that do not require an operand
        elif op_type in [
             SingleFieldOperationType.AVERAGE,
             SingleFieldOperationType.RECURSIVE_FLATTEN_LIST
        ]:
            if operand is not None:
                # Optional: Warn or raise if operand is provided but not used? Let's allow it silently.
                pass

        return self

class MergeStrategySchema(BaseSchema):
    """Defines the mapping, reduction, and transformation strategy for a merge operation."""
    map_phase: MapPhaseConfigSchema = Field(default_factory=MapPhaseConfigSchema)
    reduce_phase: ReducePhaseConfigSchema = Field(default_factory=ReducePhaseConfigSchema)
    post_merge_transformations: Optional[Dict[str, SingleFieldTransformationSchema]] = Field(
        None,
        description="Optional transformations applied to specific destination keys (dot-notation) after merging is complete. "
                    "Example: {'final_score.avg': {'operation_type': 'average'}}"
    )
    transformation_error_strategy: ErrorHandlingStrategy = Field(
        default=ErrorHandlingStrategy.SKIP_OPERATION,
        description="How to handle errors during post-merge transformations."
    )


class MergeOperationConfigSchema(BaseSchema):
    """Configuration for a single merge operation within the node."""
    output_field_name: str = Field(
        ...,
        description="The key in the final node output where the result of this merge operation will be stored."
    )
    select_paths: List[str] = Field(
        ...,
        min_length=1, # Must select at least one path
        description="List of dot-notation paths in the input data pointing to objects or lists of objects to merge. "
                    "Order defines priority (left-to-right)."
    )
    merge_strategy: MergeStrategySchema = Field(default_factory=MergeStrategySchema)
    merge_each_object_in_selected_list: bool = Field(
        default=True,
        description="If True (default), lists found at select_paths will be iterated, and each dictionary element within them will be treated as a separate object to merge. "
                    "If False, lists found at select_paths will be treated as single, atomic values to be merged using the default reducer, along with any other non-dictionary values found. "
                    "When False, all selected items for this operation *must* be non-dictionary types (an error will be raised otherwise)."
    )

    @field_validator('output_field_name')
    def output_field_must_not_be_empty(cls, v: str) -> str:
        """Ensures output field name is not empty."""
        if not v or not v.strip():
            raise ValueError("Output field name cannot be empty.")
        return v.strip()

    @field_validator('select_paths')
    def select_paths_must_be_valid(cls, v: List[str]) -> List[str]:
        """Ensures select paths list is not empty and paths are not empty."""
        if not v:
            raise ValueError("Select paths list cannot be empty.")
        stripped_paths = [p.strip() for p in v if p and p.strip()]
        if not stripped_paths or len(stripped_paths) != len(v):
             raise ValueError("Select paths cannot contain empty strings.")
        return stripped_paths


class MergeObjectsConfigSchema(BaseSchema):
    """Top-level configuration for the MergeObjectsNode."""
    operations: List[MergeOperationConfigSchema] = Field(
        ...,
        min_length=1,
        description="List of merge operations to perform sequentially."
    )

    @model_validator(mode='after')
    def check_unique_output_field_names(self) -> 'MergeObjectsConfigSchema':
        """Validates that all output_field_names across operations are unique."""
        output_names = [op.output_field_name for op in self.operations]
        if len(output_names) != len(set(output_names)):
            raise ValueError("Each merge operation must have a unique 'output_field_name'.")
        return self

# ==============================================
# --- OUTPUT SCHEMA ---
# ==============================================

class MergeObjectsOutputSchema(BaseSchema):
    """
    Output schema for the MergeObjectsNode.
    Contains the results of each merge operation under the specified field names.
    """
    merged_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary containing the results of each merge operation. "
                    "Keys are the 'output_field_name' from the configuration."
    )

# ==============================================
# --- MERGE AGGREGATE NODE ---
# ==============================================

class MergeAggregateNode(BaseDynamicNode):
    """
    Node that merges multiple JSON objects or lists of objects based on configuration.

    It selects data from specified input paths, potentially flattens lists,
    and merges the objects sequentially using defined mapping and reduction strategies.
    Multiple independent merge operations can be configured, each producing an output
    field in the final result. Supports math aggregations (SUM, MIN, MAX, AVERAGE),
    dictionary merging (simple/nested, replace/aggregate), list operations,
    and other post-merge transformations (MULTIPLY, DIVIDE, ADD, SUBTRACT).
    Handles nested destination keys and provides error handling strategies.

    # TODO: FIXME: handle nested paths / destination keys gracefully, currently the behaviour is undefined and sometimes works and sometimes fails
    """
    node_name: ClassVar[str] = "merge_aggregate"
    node_version: ClassVar[str] = "0.3.1"
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.PRODUCTION
    output_schema_cls: ClassVar[Type[MergeObjectsOutputSchema]] = MergeObjectsOutputSchema
    config_schema_cls: ClassVar[Type[MergeObjectsConfigSchema]] = MergeObjectsConfigSchema
    config: MergeObjectsConfigSchema

    def _prepare_input_data(self, input_data: Union[DynamicSchema, Dict[str, Any]]) -> Dict[str, Any]:
        """Prepares input data by converting to a deep dictionary copy."""
        try:
            if isinstance(input_data, dict): return copy.deepcopy(input_data)
            if hasattr(input_data, 'model_dump'): return copy.deepcopy(input_data.model_dump(mode='json'))
            return copy.deepcopy(dict(input_data))
        except Exception as e:
            self.warning(f"Could not reliably convert input data of type {type(input_data)} to dict for {self.node_name}. Error: {e}")
            return {}

    def _get_value_via_source_keys(self, obj: Dict[str, Any], source_keys: List[str]) -> Tuple[Any, bool]:
        """Attempts to retrieve a value using a list of relative source key paths."""
        for key_path in source_keys:
            value, found = _get_nested_obj(obj, key_path)
            if found and value is not None: return value, True
        return None, False

    def _handle_reduction_error(self, error: Exception, strategy: ErrorHandlingStrategy, dest_key: str, left_val: Any, right_val: Any) -> Tuple[Optional[Any], bool]:
        """Handles errors during the reduction phase based on the configured strategy."""
        self.error(f"Error reducing key '{dest_key}': {error} (Left: {type(left_val).__name__}, Right: {type(right_val).__name__}). Strategy: {strategy.value}")
        # Raise immediately if FAIL_NODE is the strategy
        if strategy == ErrorHandlingStrategy.FAIL_NODE: raise error
        # Otherwise, return value based on strategy (no longer need boolean flag)
        if strategy == ErrorHandlingStrategy.SET_NONE: return None
        if strategy == ErrorHandlingStrategy.SKIP_OPERATION: return left_val # Keep left if exists
        if strategy == ErrorHandlingStrategy.COALESCE_KEEP_LEFT: return left_val # Explicitly keep left
        if strategy == ErrorHandlingStrategy.COALESCE_KEEP_NON_EMPTY: return left_val if left_val else right_val # Keep left if non-empty, otherwise right
        self.warning(f"Unknown error handling strategy '{strategy}'. Defaulting to COALESCE_KEEP_LEFT.")
        return left_val # Default safety

    def _handle_transformation_error(self, error: Exception, strategy: ErrorHandlingStrategy, dest_key: str, current_val: Any) -> Tuple[Optional[Any], bool]:
        """Handles errors during the post-merge transformation phase."""
        self.error(f"Error transforming key '{dest_key}': {error} (Value: {type(current_val).__name__}). Strategy: {strategy.value}")
        # Raise immediately if FAIL_NODE is the strategy
        if strategy == ErrorHandlingStrategy.FAIL_NODE: raise error
        # Otherwise, return value based on strategy (no longer need boolean flag)
        if strategy == ErrorHandlingStrategy.SET_NONE: return None
        if strategy == ErrorHandlingStrategy.SKIP_OPERATION: return current_val # Keep original
        if strategy in [ErrorHandlingStrategy.COALESCE_KEEP_LEFT, ErrorHandlingStrategy.COALESCE_KEEP_NON_EMPTY]: return current_val # Treat as SKIP
        self.warning(f"Unknown error handling strategy '{strategy}'. Defaulting to SKIP_OPERATION.")
        return current_val # Default safety


    def _merge_two_objects(self, left_obj: Dict[str, Any], right_obj: Dict[str, Any], strategy: MergeStrategySchema, merged_counts: Dict[str, int]) -> Dict[str, Any]:
        """Merges two objects according to the given merge strategy."""
        # Both inputs must be dictionaries
        if not isinstance(left_obj, dict) or not isinstance(right_obj, dict):
            self.warning(f"_merge_two_objects requires dictionary inputs. Got {type(left_obj)}, {type(right_obj)}. Skipping.")
            return left_obj if isinstance(left_obj, dict) else {}

        map_config = strategy.map_phase
        reduce_config = strategy.reduce_phase
        dest_key_to_source_map: Dict[str, List[str]] = {m.destination_key: m.source_keys for m in map_config.key_mappings}
        explicitly_handled_dest_keys: Set[str] = set(dest_key_to_source_map.keys())

        # Process explicit key mappings
        for dest_key, source_keys in dest_key_to_source_map.items():
            right_val, found_right = self._get_value_via_source_keys(right_obj, source_keys)
            if found_right:
                left_val, found_left = _get_nested_obj(left_obj, dest_key)
                reducer_type = reduce_config.reducers.get(dest_key, reduce_config.default_reducer)
                reducer_func = REDUCER_FUNCTIONS.get(reducer_type)
                if reducer_func:
                    final_value, should_fail_node = None, False
                    try:
                        if found_left:
                            final_value = reducer_func(left_val, right_val)
                            merged_counts[dest_key] = merged_counts.get(dest_key, 1) + 1 # Start count at 1 for left, add 1 for right
                        else:
                            # If left doesn't exist, the 'reduction' is just taking the right value.
                            # Make a deepcopy only if necessary (replace ops, dict/list merges)
                            needs_copy = reducer_type in [
                                ReducerType.REPLACE_RIGHT, ReducerType.SIMPLE_MERGE_REPLACE,
                                ReducerType.SIMPLE_MERGE_AGGREGATE, ReducerType.NESTED_MERGE_REPLACE,
                                ReducerType.NESTED_MERGE_AGGREGATE
                            ] or isinstance(right_val, (dict, list))
                            final_value = copy.deepcopy(right_val) if needs_copy else right_val
                            merged_counts[dest_key] = 1 # First value added
                    except Exception as e:
                        # If FAIL_NODE is strategy, _handle_reduction_error will raise, exiting this function.
                        # Otherwise, it returns the value to use.
                        final_value = self._handle_reduction_error(e, reduce_config.error_strategy, dest_key, left_val, right_val)

                    try: _set_nested_obj(left_obj, dest_key, final_value, create_missing=True)
                    except TypeError as e_set: print(f"Error setting nested key '{dest_key}': {e_set}.")
                else: # Fallback for unknown reducer
                     self.warning(f"Unknown reducer '{reducer_type}' for key '{dest_key}'. Using REPLACE_RIGHT.")
                     try:
                        _set_nested_obj(left_obj, dest_key, copy.deepcopy(right_val), create_missing=True)
                        merged_counts[dest_key] = merged_counts.get(dest_key, 0) + 1
                     except TypeError as e_set:
                        self.warning(f"Error setting nested key '{dest_key}' in fallback: {e_set}.")

        # Process unspecified keys
        if map_config.unspecified_keys_strategy == UnspecifiedKeysStrategy.AUTO_MERGE:
            for key, right_val in right_obj.items():
                 dest_key = key # Destination key is same as source key in auto-merge

                 # --- Auto-merge Guards ---
                 # 1. Skip if this key is an explicitly defined destination key
                 if dest_key in explicitly_handled_dest_keys:
                     continue

                 # 2. Skip if this key is a parent/prefix of an explicitly defined destination key
                 #    (e.g., right has 'user', explicit mapping has 'user.id')
                 #    This prevents auto-merging the whole 'user' dict when only a sub-key was mapped.
                 is_explicit_prefix = any(dk.startswith(key + '.') for dk in explicitly_handled_dest_keys)
                 if is_explicit_prefix:
                     continue
                 # --- End Guards ---

                 # If guards passed, proceed with auto-merge reduction for this key
                 left_val, found_left = _get_nested_obj(left_obj, dest_key)
                 reducer_type = reduce_config.reducers.get(dest_key, reduce_config.default_reducer)
                 reducer_func = REDUCER_FUNCTIONS.get(reducer_type)
                 if reducer_func:
                     final_value, should_fail_node = None, False
                     try:
                         if found_left:
                             final_value = reducer_func(left_val, right_val)
                             merged_counts[dest_key] = merged_counts.get(dest_key, 1) + 1
                         else:
                             needs_copy = reducer_type in [ReducerType.REPLACE_RIGHT, ReducerType.SIMPLE_MERGE_REPLACE, ReducerType.SIMPLE_MERGE_AGGREGATE, ReducerType.NESTED_MERGE_REPLACE, ReducerType.NESTED_MERGE_AGGREGATE] or isinstance(right_val, (dict, list))
                             final_value = copy.deepcopy(right_val) if needs_copy else right_val
                             merged_counts[dest_key] = 1
                     except Exception as e:
                         # If FAIL_NODE is strategy, _handle_reduction_error will raise, exiting this function.
                         # Otherwise, it returns the value to use.
                         final_value = self._handle_reduction_error(e, reduce_config.error_strategy, dest_key, left_val, right_val)

                     try: _set_nested_obj(left_obj, dest_key, final_value, create_missing=True)
                     except TypeError as e_set: 
                         self.warning(f"Error setting auto-merged key '{dest_key}': {e_set}.")
                 else: # Fallback for unknown reducer during auto-merge
                     self.warning(f"Unknown reducer '{reducer_type}' for auto-merged key '{dest_key}'. Using REPLACE_RIGHT.")
                     try:
                         _set_nested_obj(left_obj, dest_key, copy.deepcopy(right_val), create_missing=True)
                         merged_counts[dest_key] = merged_counts.get(dest_key, 0) + 1
                     except TypeError as e_set:
                        self.warning(f"Error setting auto-merged key '{dest_key}' in fallback: {e_set}.")
        return left_obj


    async def process(self, input_data: Union[DynamicSchema, Dict[str, Any]], config: Optional[Dict[str, Any]] = None, *args: Any, **kwargs: Any) -> MergeObjectsOutputSchema:
        """
        Processes input data by performing sequential merge operations.

        Handles both merging dictionaries (with optional flattening of lists based on config) 
        and merging non-dictionary values using a specified default reducer.
        """
        prepared_input = self._prepare_input_data(input_data)
        final_output_data: Dict[str, Any] = {}
        if not prepared_input: return MergeObjectsOutputSchema(merged_data={})

        try:
            active_config = self.config
            for operation_index, operation in enumerate(active_config.operations):
                output_field = operation.output_field_name
                select_paths = operation.select_paths
                strategy = operation.merge_strategy
                merge_each_item = operation.merge_each_object_in_selected_list
                merged_counts_for_op: Dict[str, int] = {} # Tracks contributions per destination key

                self.info(f"Processing merge operation #{operation_index + 1} for output field: '{output_field}'")
                self.info(f"  - merge_each_object_in_selected_list: {merge_each_item}")

                # --- 1. Select Data --- 
                # Collect raw selected items first, handling list flattening based on the flag.
                selected_items: List[Any] = [] 
                for path in select_paths:
                    selected_data, found = _get_nested_obj(prepared_input, path)
                    items_added = 0
                    if found:
                        if merge_each_item:
                            # Flatten lists if flag is True, only taking dicts
                            if isinstance(selected_data, list):
                                for item in selected_data:
                                    if isinstance(item, dict):
                                        selected_items.append(copy.deepcopy(item))
                                        items_added += 1
                                    else:
                                        self.warning(f"  Warning: Item in list from path '{path}' is not a dict (found {type(item).__name__}). Skipping item.")
                            elif isinstance(selected_data, dict):
                                selected_items.append(copy.deepcopy(selected_data))
                                items_added = 1
                            else:
                                self.warning(f"  Warning: Path '{path}' yielded a non-dict/non-list type ({type(selected_data).__name__}) when merge_each_object_in_selected_list is True. Skipping path.")
                        else:
                            # Take the item as is if flag is False
                            selected_items.append(copy.deepcopy(selected_data))
                            items_added = 1 # Treat the whole list/item as one selected item

                        if items_added > 0:
                            self.info(f"  - Selected {items_added} item(s) from path: '{path}'")
                    else:
                        self.warning(f"  Warning: Select path '{path}' not found. Skipping.")

                # --- 2. Determine Merge Type and Perform Merge --- 
                merged_result: Any = None
                is_merging_dicts = False

                if not selected_items:
                    self.warning(f"Warning: No items selected for merge operation '{output_field}'. Setting output to None.")
                    final_output_data[output_field] = None
                    continue # Skip to the next operation

                # Decide if merging dictionaries or non-dictionaries
                if not merge_each_item:
                    # If flag is False, all items *must* be non-dict
                    contains_dict = any(isinstance(item, dict) for item in selected_items)
                    if contains_dict:
                        raise TypeError(f"Configuration error for operation '{output_field}': 'merge_each_object_in_selected_list' is False, but a dictionary was found in the selected items. Cannot mix dictionary and non-dictionary types in this mode.")
                    is_merging_dicts = False
                else:
                    # If flag is True, we expect dictionaries (due to filtering during selection)
                    # Even if somehow a non-dict slipped through, we treat it as a dictionary merge path, 
                    # where _merge_two_objects might handle it or raise errors.
                    is_merging_dicts = True

                # --- 2.a Merge Non-Dictionary Items --- 
                if not is_merging_dicts:
                    self.info(f"  - Performing non-dictionary merge using default reducer: {strategy.reduce_phase.default_reducer.value}")
                    merged_result = selected_items[0]
                    # Keep track of how many items were successfully reduced for potential AVERAGE transform
                    items_successfully_reduced = 1 if merged_result is not None else 0
                    
                    # Get the default reducer function
                    reducer_type = strategy.reduce_phase.default_reducer
                    reducer_func = REDUCER_FUNCTIONS.get(reducer_type)
                    # init:
                    merged_result = reducer_func(None, merged_result, is_init=True)
                    if not reducer_func:
                        raise ValueError(f"Default reducer '{reducer_type.value}' not found.")

                    for i, item in enumerate(selected_items[1:], start=1):
                        self.info(f"  - Reducing item {i+1}...")
                        try:
                            # Apply the default reducer sequentially
                            merged_result = reducer_func(merged_result, item)
                            items_successfully_reduced += 1
                        except Exception as e:
                            # Use reduction error handling. Note: dest_key is less relevant here.
                            merged_result = self._handle_reduction_error(e, strategy.reduce_phase.error_strategy, f"{output_field} (non-dict reduction)", merged_result, item)
                            if strategy.reduce_phase.error_strategy == ErrorHandlingStrategy.FAIL_NODE: 
                                raise # Re-raise if FAIL_NODE strategy caused _handle_reduction_error to raise
                    
                    # Set a generic count for potential AVERAGE transformation
                    # Use the number of successfully reduced items.
                    # If the final result is not numeric, AVERAGE will fail later anyway.
                    if items_successfully_reduced > 0:
                        merged_counts_for_op[output_field] = items_successfully_reduced

                # --- 2.b Merge Dictionary Items --- 
                else: # is_merging_dicts is True
                    self.info(f"  - Performing dictionary merge...")
                    merged_result = {} # Start with an empty dict
                    
                    # Ensure all items are dictionaries before proceeding
                    # This should be guaranteed by the selection logic when merge_each_item is True
                    dict_items_to_merge = [item for item in selected_items if isinstance(item, dict)]
                    if len(dict_items_to_merge) != len(selected_items):
                        self.warning(f"  Warning: Found non-dictionary items during dictionary merge phase for '{output_field}'. These items will be skipped.")
                        # Note: This case should ideally not happen if selection logic is correct
                    
                    if not dict_items_to_merge:
                        self.warning(f"Warning: No valid dictionary objects to merge for '{output_field}'. Setting output to empty dict.")
                        final_output_data[output_field] = {}
                        continue
                        
                    # Merge ALL dictionary objects sequentially into the initially empty merged_result
                    for i, obj_to_merge in enumerate(dict_items_to_merge):
                        self.info(f"  - Merging object {i+1}...")
                        # The first object is merged into the empty dict, applying mapping rules.
                        # Subsequent objects are merged into the result of the previous merge.
                        # merged_counts_for_op is updated within _merge_two_objects
                        merged_result = self._merge_two_objects(merged_result, obj_to_merge, strategy, merged_counts_for_op)

                # --- 3. Apply Post-Merge Transformations --- 
                if strategy.post_merge_transformations:
                    self.info(f"  - Applying post-merge transformations for '{output_field}'...")
                    
                    if is_merging_dicts:
                        # Apply transforms to specific keys within the merged dictionary
                        for dest_key, transform_config in strategy.post_merge_transformations.items():
                            current_value, found_val = _get_nested_obj(merged_result, dest_key)
                            if not found_val:
                                self.warning(f"    Warning: Cannot transform '{dest_key}'. Key not found in merged dictionary.")
                                continue
                            
                            transform_func = TRANSFORMATION_FUNCTIONS.get(transform_config.operation_type)
                            if transform_func:
                                final_value = None
                                try:
                                    # Get count for AVERAGE if needed, based on dictionary merge counts
                                    count_for_avg = merged_counts_for_op.get(dest_key) if transform_config.operation_type == SingleFieldOperationType.AVERAGE else None
                                    final_value = transform_func(current_value, transform_config, count_for_avg)
                                    self.info(f"    - Applied {transform_config.operation_type.value} to '{dest_key}' -> {final_value}")
                                except Exception as e:
                                    final_value = self._handle_transformation_error(e, strategy.transformation_error_strategy, dest_key, current_value)
                                    if strategy.transformation_error_strategy == ErrorHandlingStrategy.FAIL_NODE:
                                        raise # Re-raise if handler raised
                                
                                try: 
                                    _set_nested_obj(merged_result, dest_key, final_value, create_missing=False) # Don't create missing during transform
                                except TypeError as e_set: 
                                    self.warning(f"    Error setting key '{dest_key}' after transform: {e_set}.")
                            else:
                                self.warning(f"    Warning: Unknown transformation type '{transform_config.operation_type}'. Skipping for key '{dest_key}'.")
                                
                    else: # Apply transforms directly to the non-dictionary merged_result
                        # Apply all transformations in sequence to the single output value
                        if strategy.post_merge_transformations:
                            current_value = merged_result
                            self.info(f"  Applying {len(strategy.post_merge_transformations)} transformations to non-dictionary output '{output_field}'")
                            
                            # Iterate through all transformations and apply them in sequence
                            for transform_key, transform_config in strategy.post_merge_transformations.items():
                                transform_func = TRANSFORMATION_FUNCTIONS.get(transform_config.operation_type)
                                
                                if transform_func:
                                    try:
                                        # Get count for AVERAGE if needed, using the count from the non-dict reduction
                                        count_for_avg = merged_counts_for_op.get(output_field) if transform_config.operation_type == SingleFieldOperationType.AVERAGE else None
                                        current_value = transform_func(current_value, transform_config, count_for_avg)
                                        self.info(f"    - Applied {transform_config.operation_type.value} transformation -> {current_value}")
                                    except Exception as e:
                                        current_value = self._handle_transformation_error(e, strategy.transformation_error_strategy, output_field, current_value)
                                        if strategy.transformation_error_strategy == ErrorHandlingStrategy.FAIL_NODE:
                                            raise  # Re-raise if handler raised
                                else:
                                    self.warning(f"    Warning: Unknown transformation type '{transform_config.operation_type}' for output '{output_field}'. Skipping this transformation.")
                            
                            # Update the final merged result after all transformations
                            merged_result = current_value

                # Store final result for this operation
                final_output_data[output_field] = merged_result
                self.info(f"  - Finished processing for '{output_field}'.")

            return MergeObjectsOutputSchema(merged_data=final_output_data)

        except ValidationError as e:
            self.error(f"Error: Config validation failed: {e}"); 
            return MergeObjectsOutputSchema(merged_data={})
        except TypeError as e: # Catch specific type errors like mixing dicts/non-dicts
            self.error(f"Error processing node: {e}"); 
            traceback.print_exc(); 
            # TODO: FIXME: Log error and potentially fail node and not silently pass through error??
            return MergeObjectsOutputSchema(merged_data={})
        # Specific exceptions raised by FAIL_NODE strategy should now propagate up
        # Keep the generic Exception catch for truly unexpected errors
        except Exception as e:
            self.error(f"Error processing node: {e}"); 
            traceback.print_exc(); 
            # TODO: FIXME: Log error and potentially fail node and not silently pass through error??
            return MergeObjectsOutputSchema(merged_data={})
