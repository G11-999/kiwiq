"""
Reducer functions for state management in workflow graphs.

This module provides a collection of reducer functions that define how state updates are 
processed in workflow graphs. Reducers determine how new values are combined with 
existing values when a node updates a state field.

Inspired by LangGraph state reducers: 
https://langchain-ai.github.io/langgraph/how-tos/state-reducers/
"""
import copy
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union, Set, Mapping
import operator
from collections.abc import Mapping as MappingABC
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage

# Type variables for generics
T = TypeVar('T')
K = TypeVar('K')
V = TypeVar('V')

class DefaultReducers:
    """
    Collection of default reducer functions for common data types.
    
    These reducers define how values are combined when a state field is updated.
    Each reducer takes a left value (existing) and a right value (update) and
    returns the combined result.
    """
    
    @staticmethod
    def replace(left: T, right: T) -> T:
        """
        Replace the existing value with the new value.
        
        This is the default reducer for most types.
        
        Args:
            left: Existing value
            right: New value to replace with
            
        Returns:
            The new value (right)
        """
        return right
    
    @staticmethod
    def add(left: Union[int, float], right: Union[int, float]) -> Union[int, float]:
        """
        Add the new value to the existing value.
        
        Useful for numeric types like int and float.
        
        Args:
            left: Existing value
            right: Value to add
            
        Returns:
            Sum of left and right
        """
        if left is None:
            return right
        return operator.add(left, right)
    
    @staticmethod
    def append_list(left: List[T], right: List[T]) -> List[T]:
        """
        Append items from the new list to the existing list.
        
        Args:
            left: Existing list
            right: List with items to append
            
        Returns:
            Combined list with items from right appended to left
        """
        if left is None:
            return right
        return left + right
    
    @staticmethod
    def union_sets(left: Set[T], right: Set[T]) -> Set[T]:
        """
        Create a union of two sets.
        
        Args:
            left: Existing set
            right: Set to union with
            
        Returns:
            Union of left and right sets
        """
        return left.union(right)
    
    @staticmethod
    def merge_dicts(left: Dict[K, V], right: Dict[K, V]) -> Dict[K, V]:
        """
        Merge the new dictionary into the existing dictionary.
        
        This performs a shallow merge - only top-level keys are merged.
        
        Args:
            left: Existing dictionary
            right: Dictionary to merge in
            
        Returns:
            Merged dictionary
        """
        if left is None:
            return copy.deepcopy(right)
        
        result = left.copy()
        result.update(right)
        return result
    
    @staticmethod
    def deep_merge_dicts(left: Dict[K, Any], right: Dict[K, Any]) -> Dict[K, Any]:
        """
        Recursively merge dictionaries.
        
        For nested dictionaries, this will merge at each level rather than replacing.
        
        Args:
            left: Existing dictionary
            right: Dictionary to merge in
            
        Returns:
            Deeply merged dictionary
        """
        if left is None:
            return copy.deepcopy(right)
        
        result = left.copy()
        
        for key, value in right.items():
            if (
                key in result and 
                isinstance(result[key], dict) and 
                isinstance(value, MappingABC)
            ):
                result[key] = DefaultReducers.deep_merge_dicts(result[key], value)
            else:
                result[key] = value
                
        return result
    
    @staticmethod
    def max_value(left: Union[int, float], right: Union[int, float]) -> Union[int, float]:
        """
        Return the maximum of the two values.
        
        Args:
            left: Existing value
            right: New value
            
        Returns:
            Maximum of left and right
        """
        if left is None:
            return right
        return max(left, right)
    
    @staticmethod
    def min_value(left: Union[int, float], right: Union[int, float]) -> Union[int, float]:
        """
        Return the minimum of the two values.
        
        Args:
            left: Existing value
            right: New value
            
        Returns:
            Minimum of left and right
        """
        if left is None:
            return right
        return min(left, right)
    
    @staticmethod
    def concatenate_strings(left: str, right: str) -> str:
        """
        Concatenate the new string to the existing string.
        
        Args:
            left: Existing string
            right: String to append
            
        Returns:
            Concatenated string
        """
        if left is None:
            return right
        return left + right
    
    @staticmethod
    def collect_values(left: Optional[List[T]], right: T) -> List[T]:
        """
        Collect values into a list, initializing if needed.
        
        If left is None, creates a new list containing right.
        If left is not a list, converts it to a single-element list before appending.
        This is useful for accumulating values when the initial state might be None or a single value.
        
        Args:
            left: Existing list, single value, or None
            right: Value to append to the list
            
        Returns:
            List with the new value appended
        """
        if not isinstance(left, list):
            if left is None:
                return [right]
            else:
                left = [left]
        return left + [right]
    
    @staticmethod
    def conditional_update(
        left: T, 
        right: T, 
        condition: Callable[[T, T], bool]
    ) -> T:
        """
        Update value only if a condition is met.
        
        Args:
            left: Existing value
            right: New value
            condition: Function that takes left and right values and returns a boolean
                indicating whether to update
                
        Returns:
            Either left or right, depending on condition
        """
        return right if condition(left, right) else left


class ReducerType(str, Enum):
    """
    Enumeration of available reducer types.
    
    Using string values for serializability.
    """
    # Basic reducers
    REPLACE = "replace"
    ADD = "add"
    
    # Collection reducers
    APPEND_LIST = "append_list"
    UNION_SETS = "union_sets"
    MERGE_DICTS = "merge_dicts"
    DEEP_MERGE_DICTS = "deep_merge_dicts"
    COLLECT_VALUES = "collect_values"
    
    # Comparison reducers
    MAX = "max"
    MIN = "min"
    
    # String reducers
    CONCATENATE = "concatenate"
    
    # Special reducers
    ADD_MESSAGES = "add_messages"


# Mapping from ReducerType to actual reducer functions
REDUCER_FUNCTION_MAP: Dict[str, Callable[[Any, Any], Any]] = {
    ReducerType.REPLACE: DefaultReducers.replace,
    ReducerType.ADD: DefaultReducers.add,
    ReducerType.APPEND_LIST: DefaultReducers.append_list,
    ReducerType.UNION_SETS: DefaultReducers.union_sets,
    ReducerType.MERGE_DICTS: DefaultReducers.merge_dicts,
    ReducerType.DEEP_MERGE_DICTS: DefaultReducers.deep_merge_dicts,
    ReducerType.COLLECT_VALUES: DefaultReducers.collect_values,
    ReducerType.MAX: DefaultReducers.max_value,
    ReducerType.MIN: DefaultReducers.min_value,
    ReducerType.CONCATENATE: DefaultReducers.concatenate_strings,
    ReducerType.ADD_MESSAGES: add_messages,
}


class ReducerRegistry:
    """
    Registry for managing reducer functions.
    
    Provides methods to get reducer functions by name or type.

    # IMP NOTE: reduced and arguments to reducer must be same type! eg: reduced list and list to be reduced!
    # Check: https://langchain-ai.github.io/langgraph/how-tos/state-reducers/#messagesstate
    """
    
    @staticmethod
    def get_reducer(name: str) -> Optional[Callable[[Any, Any], Any]]:
        """
        Get a reducer function by name.
        
        Args:
            name: Name of the reducer to retrieve (case insensitive)
            
        Returns:
            The reducer function if found, None otherwise
        """
        try:
            # Try to get from enum first
            reducer_type = ReducerType(name.lower())
            return REDUCER_FUNCTION_MAP[reducer_type]
        except (ValueError, KeyError):
            # If not a valid enum value, try matching directly against keys in the map
            for key, func in REDUCER_FUNCTION_MAP.items():
                if key.lower() == name.lower():
                    return func
            return None
    
    @staticmethod
    def get_reducer_for_type(value_type: type) -> Callable[[Any, Any], Any]:
        """
        Get an appropriate default reducer for the given type.
        
        Args:
            value_type: Type to get a reducer for
            
        Returns:
            A reducer function appropriate for the type
        """
        # Try to determine if this is a message type
        is_message_type = False
        if value_type is list[AnyMessage]:
            is_message_type = True

        if is_message_type:
            return REDUCER_FUNCTION_MAP[ReducerType.ADD_MESSAGES]
        elif value_type in (int, float):
            return REDUCER_FUNCTION_MAP[ReducerType.REPLACE]
        elif value_type == str:
            return REDUCER_FUNCTION_MAP[ReducerType.REPLACE]
        elif value_type == list:
            return REDUCER_FUNCTION_MAP[ReducerType.APPEND_LIST]
        elif value_type == dict:
            return REDUCER_FUNCTION_MAP[ReducerType.MERGE_DICTS]
        elif value_type == set:
            return REDUCER_FUNCTION_MAP[ReducerType.UNION_SETS]
        else:
            # Default for other types
            return REDUCER_FUNCTION_MAP[ReducerType.REPLACE]
    
    @staticmethod
    def register_custom_reducer(name: str, reducer_function: Callable[[Any, Any], Any]) -> None:
        """
        Register a custom reducer function.
        
        Args:
            name: Name to register the reducer under
            reducer_function: The reducer function to register
        """
        REDUCER_FUNCTION_MAP[name] = reducer_function


# Common reducer functions that can be used as annotations
replace = DefaultReducers.replace
add = DefaultReducers.add
append_list = DefaultReducers.append_list
union_sets = DefaultReducers.union_sets
merge_dicts = DefaultReducers.merge_dicts
deep_merge_dicts = DefaultReducers.deep_merge_dicts
collect_values = DefaultReducers.collect_values
max_value = DefaultReducers.max_value
min_value = DefaultReducers.min_value
concatenate = DefaultReducers.concatenate_strings
# Export the imported add_messages function
# add_messages is already imported from langgraph.graph.message

# Example of how to use with Annotated:
# from typing_extensions import Annotated
# from langchain_core.messages import AnyMessage
# 
# class State(TypedDict):
#     messages: Annotated[list[AnyMessage], add_messages]
#     counter: Annotated[int, add]
#     settings: Annotated[dict, merge_dicts]
