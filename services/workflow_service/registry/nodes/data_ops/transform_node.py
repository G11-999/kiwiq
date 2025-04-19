"""
Data transformation and mapping nodes for workflow processing.

This module provides nodes for:
- Rearranging object structures (TransformerNode)
- Joining data from different parts of the input based on keys (MapperNode)

These nodes facilitate complex data manipulation within workflows.
"""

import copy
import traceback
from enum import Enum
from typing import Any, Dict, List, Optional, Union, ClassVar, Literal, Tuple, Set, Type

# Use real imports
from pydantic import Field, model_validator, field_validator, BaseModel, ValidationError, validator

from kiwi_app.workflow_app.constants import LaunchStatus
from workflow_service.registry.schemas.base import BaseSchema
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema, BaseDynamicNode
from workflow_service.registry.nodes.core.flow_nodes import _get_nested_obj # Reuse helper

# ==============================================
# --- HELPER FUNCTIONS ---
# ==============================================

def _set_nested_obj(data: Dict[str, Any], path: str, value: Any, create_missing: bool = True) -> bool:
    """
    Sets a value at a specified path within a nested dictionary structure.

    Args:
        data (Dict[str, Any]): The dictionary to modify.
        path (str): Dot-notation path where the value should be set (e.g., "user.profile.email").
        value (Any): The value to set at the specified path.
        create_missing (bool): If True, create intermediate dictionaries if they don't exist. Defaults to True.

    Returns:
        bool: True if the value was successfully set, False otherwise.

    Raises:
        TypeError: If trying to set a key on a non-dictionary intermediate path element
                   when create_missing is False or if the path structure conflicts.
    """
    if not path:
        # Cannot set a value at the root level directly with this function's logic
        # It might overwrite the entire dictionary, which is likely unintended.
        print("Warning: Attempted to set value with an empty path. This is not supported.")
        return False

    parts = path.split('.')
    current_level = data
    final_key = parts[-1]

    # Traverse the path to the second-to-last element
    for i, part in enumerate(parts[:-1]):
        if part not in current_level:
            if create_missing:
                # Create a new dictionary if the key is missing
                current_level[part] = {}
                current_level = current_level[part]
            else:
                # Path does not exist, and we're not creating it
                print(f"Warning: Path part '{part}' not found in path '{path}' and create_missing is False.")
                return False
        elif isinstance(current_level[part], dict):
            # Move to the next level if it's a dictionary
            current_level = current_level[part]
        else:
            # Conflict: An intermediate element exists but is not a dictionary
            raise TypeError(f"Cannot create nested structure. Element at path "
                            f"{'.'.join(parts[:i+1])} is not a dictionary (found type: {type(current_level[part]).__name__}).")

    # Set the value at the final key
    current_level[final_key] = value
    return True

# ==============================================
# --- TRANSFORMER NODE ---
# ==============================================

class TransformMappingSchema(BaseSchema):
    """
    Defines a single mapping from a source path to a destination path.

    Attributes:
        source_path (str): Dot-notation path to the data to be copied from the input.
        destination_path (str): Dot-notation path where the data should be placed in the output.
                                Intermediate dictionaries will be created if they don't exist.
    """
    source_path: str = Field(..., description="Dot-notation path to the source field in the input data.")
    destination_path: str = Field(..., description="Dot-notation path for the field in the output data.")

    @validator('source_path', 'destination_path')
    def path_must_not_be_empty(cls, v: str) -> str:
        """Ensures paths are not empty strings."""
        if not v or not v.strip():
            raise ValueError("Path cannot be empty.")
        return v.strip()

class TransformerConfigSchema(BaseSchema):
    """
    Configuration for the TransformerNode.

    Attributes:
        mappings (List[TransformMappingSchema]): A list of source-to-destination path mappings.
                                                 Mappings are processed in the order they appear.
                                                 Later mappings can overwrite values set by earlier ones
                                                 if destination paths collide.
    """
    mappings: List[TransformMappingSchema] = Field(
        ...,
        min_length=1,
        description="List of source-to-destination path mappings."
    )

class TransformerOutputSchema(BaseSchema):
    """
    Output schema for the TransformerNode.

    Attributes:
        transformed_data (Dict[str, Any]): The resulting data structure after applying the transformations.
                                          Returns an empty dict if the input was invalid or processing failed.
    """
    transformed_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="The data structure after applying transformations."
    )

class TransformerNode(BaseDynamicNode):
    """
    Node that rearranges the structure of input data based on defined mappings.

    This node takes an input dictionary and creates a new dictionary where data
    is copied from specified source paths in the input to destination paths
    in the output. Intermediate dictionary structures in the destination path
    are created automatically if they don't exist.
    """
    node_name: ClassVar[str] = "transform_data"
    node_version: ClassVar[str] = "0.1.0"
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.PRODUCTION
    input_schema_cls: Type[DynamicSchema] = DynamicSchema
    output_schema_cls: Type[TransformerOutputSchema] = TransformerOutputSchema
    config_schema_cls: Type[TransformerConfigSchema] = TransformerConfigSchema
    config: TransformerConfigSchema

    def _prepare_input_data(self, input_data: Union[DynamicSchema, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Prepares input data for processing by converting to a dictionary.
        Uses deepcopy to ensure the original input is not mutated during processing,
        although the transformer primarily reads from it.

        Args:
            input_data: The input data to prepare.

        Returns:
            Dict[str, Any]: A dictionary copy of the input data.
        """
        if isinstance(input_data, dict):
            # Even though we primarily read, copying ensures consistency if
            # underlying structures are unexpectedly mutable or shared.
            return copy.deepcopy(input_data)
        elif hasattr(input_data, 'model_dump'):
            return input_data.model_dump(mode='json')
        else:
            # Fallback for other potential input types, though DynamicSchema is expected.
            try:
                return copy.deepcopy(dict(input_data))
            except Exception:
                 print(f"Warning: Could not reliably convert input data of type {type(input_data)} to dict.")
                 return {}


    def process(self, input_data: Union[DynamicSchema, Dict[str, Any]], config: Optional[Dict[str, Any]] = None, *args: Any, **kwargs: Any) -> TransformerOutputSchema:
        """
        Processes input data by applying source-to-destination mappings.

        Iterates through each mapping defined in the configuration:
        1. Retrieves the value from the `source_path` in the input data.
        2. Sets a *copy* of this value at the `destination_path` in a *new* output dictionary.
        3. Creates intermediate dictionaries in the output structure as needed.

        Args:
            input_data: The data to transform, either as a DynamicSchema or dictionary.
            config: Optional configuration override (not typically used as config is instance member).
            *args: Additional positional arguments (unused).
            **kwargs: Additional keyword arguments (unused).

        Returns:
            TransformerOutputSchema: Contains the newly constructed transformed data.
                                     Returns an empty `transformed_data` dict if errors occur.
        """
        # Prepare the input data (ensures it's a dictionary)
        input_dict = self._prepare_input_data(input_data)
        # Initialize an empty dictionary for the output. This avoids mutating the input.
        output_data: Dict[str, Any] = {}

        try:
            # Use the node's validated config
            active_config = self.config

            # Process each mapping in the defined order
            for mapping in active_config.mappings:
                source_path = mapping.source_path
                destination_path = mapping.destination_path

                # Retrieve the value from the source path in the input dictionary
                value_to_copy, found = _get_nested_obj(input_dict, source_path)

                if found:
                    # Use deepcopy to prevent unintended modifications if the value is mutable (like lists or dicts)
                    copied_value = copy.deepcopy(value_to_copy)
                    # Set the copied value at the destination path in the output dictionary
                    try:
                         success = _set_nested_obj(output_data, destination_path, copied_value, create_missing=True)
                         if not success:
                             print(f"Warning: Failed to set value for destination path '{destination_path}' from source '{source_path}'.")
                    except TypeError as e:
                         # This can happen if _set_nested_obj encounters a non-dict where it expects one
                         print(f"Error setting destination path '{destination_path}': {e}. Skipping this mapping.")
                         traceback.print_exc() # Log the error for debugging
                else:
                    # Optional: Log or handle cases where the source path doesn't exist
                    print(f"Warning: Source path '{source_path}' not found in input data. Skipping mapping to '{destination_path}'.")

            # Return the constructed output data
            return TransformerOutputSchema(transformed_data=output_data)

        except ValidationError as e:
             # Handle configuration validation errors
             print(f"Error: Config validation failed for TransformerNode: {e}")
             return TransformerOutputSchema(transformed_data={}) # Return empty on config error
        except Exception as e:
             # Handle any other unexpected errors during processing
             print(f"Error processing TransformerNode: {e}")
             traceback.print_exc()
             return TransformerOutputSchema(transformed_data={}) # Return empty on general error

# ==============================================
# --- MAPPER/JOINER NODE ---
# ==============================================

class JoinType(str, Enum):
    """
    Defines how matching items from the secondary list are nested.

    Attributes:
        ONE_TO_ONE: Nests the first matching item from the secondary list. If multiple match, only the first is used.
                    The nested value will be the object itself (or None if no match).
        ONE_TO_MANY: Nests all matching items from the secondary list as a list.
                     The nested value will be a list of objects (or an empty list if no match).
    """
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"


class MapperJoinConfigSchema(BaseSchema):
    """
    Configuration for a single join operation within the MapperNode.

    Attributes:
        primary_list_path (str): Dot-notation path to the primary list of objects (e.g., "users")
                                 or a single object. The output structure will be based on this.
        secondary_list_path (str): Dot-notation path to the secondary list of objects (e.g., "orders")
                                   or a single object to join.
        primary_join_key (str): Dot-notation path to the key within objects of the primary list/object
                                used for joining (e.g., "user_id" or "details.id").
        secondary_join_key (str): Dot-notation path to the key within objects of the secondary list/object
                                  used for joining (e.g., "customer_id" or "info.user_ref").
        output_nesting_field (str): Dot-notation path under which the joined secondary object(s) will be nested
                                    within each primary object (e.g., "orders_data" or "customer.orders").
                                    Intermediate dictionaries will be created if the path doesn't exist.
        join_type (JoinType): Determines if the join is one-to-one or one-to-many. Defaults to ONE_TO_MANY.

    *Path Handling Caveat*: When traversing paths (e.g., `primary_list_path`, `primary_join_key`), if a list
    is encountered before the end of the path, the subsequent path part *must* be a valid integer index
    (e.g., "data.items.0.id"). Using a non-integer key on a list mid-path will result in the path
    not being found.
    """
    primary_list_path: str = Field(..., description="Dot-notation path to the primary list or object.")
    secondary_list_path: str = Field(..., description="Dot-notation path to the secondary list or object.")
    primary_join_key: str = Field(..., description="Dot-notation join key within the primary list/object's items.")
    secondary_join_key: str = Field(..., description="Dot-notation join key within the secondary list/object's items.")
    output_nesting_field: str = Field(..., description="Dot-notation field name in primary items to nest joined data.")
    join_type: JoinType = Field(default=JoinType.ONE_TO_MANY, description="Type of join (one-to-one or one-to-many).")

    @validator('primary_list_path', 'secondary_list_path', 'primary_join_key', 'secondary_join_key', 'output_nesting_field')
    def field_must_not_be_empty(cls, v: str) -> str:
        """Ensures required string fields are not empty."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty.")
        return v.strip()


class MapperConfigSchema(BaseSchema):
    """
    Configuration for the MapperNode, containing one or more join operations.

    Attributes:
        joins (List[MapperJoinConfigSchema]): A list of join configurations to execute sequentially.
                                              Later joins operate on the result of previous joins within the node.
    """
    joins: List[MapperJoinConfigSchema] = Field(
        ...,
        min_length=1,
        description="List of join operations to perform sequentially."
    )

class MapperOutputSchema(BaseSchema):
    """
    Output schema for the MapperNode.

    Attributes:
        mapped_data (Dict[str, Any]): The resulting data structure after applying all join operations.
                                      Contains the modified data based on the primary lists specified in the joins.
                                      Returns None if a critical error occurred during processing.
    """
    mapped_data: Optional[Dict[str, Any]] = Field(
        None,
        description="The data structure after applying join operations."
    )

class DataJoinNode(BaseDynamicNode):
    """
    Node that joins data from different lists within the input based on specified keys.

    This node performs relational-like join operations on lists of objects found
    at specified paths within the input data. It modifies a copy of the input data
    by nesting matching objects from a secondary list into objects of a primary list.
    Multiple join operations can be configured and are executed sequentially.
    """
    node_name: ClassVar[str] = "data_join_data"
    node_version: ClassVar[str] = "0.1.0"
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.PRODUCTION
    input_schema_cls: Type[DynamicSchema] = DynamicSchema
    output_schema_cls: Type[MapperOutputSchema] = MapperOutputSchema
    config_schema_cls: Type[MapperConfigSchema] = MapperConfigSchema
    config: MapperConfigSchema

    def _prepare_input_data(self, input_data: Union[DynamicSchema, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Prepares input data for processing by converting to a deep dictionary copy.
        Ensures that join operations do not mutate the original input data structure.

        Args:
            input_data: The input data to prepare.

        Returns:
            Dict[str, Any]: A deep dictionary copy of the input data.
        """
        if isinstance(input_data, dict):
            return copy.deepcopy(input_data)
        elif hasattr(input_data, 'model_dump'):
             # Use Pydantic's serialization if available, then deepcopy for safety
             return copy.deepcopy(input_data.model_dump(mode='json'))
        else:
            try:
                 # Fallback, attempt dict conversion then deepcopy
                 return copy.deepcopy(dict(input_data))
            except Exception:
                  print(f"Warning: Could not reliably convert input data of type {type(input_data)} to dict for MapperNode.")
                  return {} # Return empty dict if conversion fails

    def _build_lookup(self, data_list: List[Any], join_key: str) -> Dict[Any, List[Dict[str, Any]]]:
        """
        Builds a lookup dictionary (hash map) for efficient joining.

        Maps join key values (potentially retrieved via a nested path) to a list of
        *copies* of objects having that key value.
        Handles potential errors like missing keys or non-dictionary items gracefully.

        Args:
            data_list (List[Any]): The list of objects to index.
            join_key (str): The dot-notation path within each object to use for indexing.

        Returns:
            Dict[Any, List[Dict[str, Any]]]: A dictionary where keys are join key values
                                            and values are lists of *copied* objects matching that key.
        """
        lookup: Dict[Any, List[Dict[str, Any]]] = {}
        for item in data_list:
            if isinstance(item, dict):
                # Use _get_nested_obj to retrieve the key value using dot-notation path
                key_value, found = _get_nested_obj(item, join_key)

                # Check if the key was found and is not None (consider hashability if None is allowed)
                if found and key_value is not None:
                    # Important: Store a deep copy to avoid modifying original objects when nesting
                    item_copy = copy.deepcopy(item)
                    if key_value not in lookup:
                        lookup[key_value] = []
                    lookup[key_value].append(item_copy)
                elif not found:
                    print(f"Warning: Join key path '{join_key}' not found in secondary item: {item}. Skipping item for lookup.")
                # else: key_value is None, potentially skip or handle if None keys are meaningful

            else:
                # Log or handle items in the list that are not dictionaries
                print(f"Warning: Item found in list for key path '{join_key}' is not a dictionary: {type(item)}. Skipping item for lookup.")
        return lookup

    def process(self, input_data: Union[DynamicSchema, Dict[str, Any]], config: Optional[Dict[str, Any]] = None, *args: Any, **kwargs: Any) -> MapperOutputSchema:
        """
        Processes input data by performing sequential join operations as configured.

        For each configured join:
        1. Retrieves the primary and secondary lists/objects from the current state of the data using dot-notation paths.
        2. Normalizes single objects to lists for consistent processing.
        3. Builds an efficient lookup map for the secondary list based on its dot-notation join key.
        4. Iterates through the primary list.
        5. For each primary item, retrieves its join key value using a dot-notation path and finds matching secondary items using the lookup map.
        6. Nests *copies* of the matching secondary items into the primary item under the specified dot-notation field path,
           according to the configured join type (one-to-one or one-to-many).

        Args:
            input_data: The data containing lists/objects to be joined.
            config: Optional configuration override.
            *args: Additional positional arguments (unused).
            **kwargs: Additional keyword arguments (unused).

        Returns:
            MapperOutputSchema: Contains the data structure after all joins have been applied.
                                Returns `mapped_data=None` if a critical error occurs (e.g., path not found or invalid type).
        """
        # Prepare a deep copy of the input data to modify
        working_data = self._prepare_input_data(input_data)

        try:
            # Use the node's validated config
            active_config = self.config

            # Execute each join configuration sequentially
            for join_config in active_config.joins:
                primary_path = join_config.primary_list_path
                secondary_path = join_config.secondary_list_path
                primary_key = join_config.primary_join_key
                secondary_key = join_config.secondary_join_key
                nesting_field = join_config.output_nesting_field
                join_type = join_config.join_type

                # --- Retrieve Lists/Objects ---
                # Retrieve potentially list or single object from the *current* state of working_data
                primary_obj, p_found = _get_nested_obj(working_data, primary_path)
                secondary_obj, s_found = _get_nested_obj(working_data, secondary_path)

                # --- Validate and Normalize to List ---
                if not p_found:
                    print(f"Error: Primary path '{primary_path}' not found in MapperNode. Aborting join.")
                    return MapperOutputSchema(mapped_data=None)
                if not s_found:
                    print(f"Error: Secondary path '{secondary_path}' not found in MapperNode. Aborting join.")
                    return MapperOutputSchema(mapped_data=None)

                # Normalize primary object to list if it's a single dictionary
                if isinstance(primary_obj, dict):
                    primary_list_obj = [primary_obj] # Treat as a single-item list
                elif isinstance(primary_obj, list):
                    primary_list_obj = primary_obj   # It's already a list
                else:
                    print(f"Error: Primary path '{primary_path}' does not point to a list or a dictionary object. Found type: {type(primary_obj).__name__}. Aborting join.")
                    return MapperOutputSchema(mapped_data=None)

                # Normalize secondary object to list if it's a single dictionary
                if isinstance(secondary_obj, dict):
                    secondary_list_obj = [secondary_obj] # Treat as a single-item list
                elif isinstance(secondary_obj, list):
                    secondary_list_obj = secondary_obj   # It's already a list
                else:
                    print(f"Error: Secondary path '{secondary_path}' does not point to a list or a dictionary object. Found type: {type(secondary_obj).__name__}. Aborting join.")
                    return MapperOutputSchema(mapped_data=None)

                # --- Build Secondary Lookup ---
                # Build lookup from the (potentially normalized) secondary list (using copies)
                secondary_lookup = self._build_lookup(secondary_list_obj, secondary_key)

                # --- Perform Join ---
                # Iterate through the primary list (which is part of working_data and can be modified directly)
                for primary_item in primary_list_obj:
                    if isinstance(primary_item, dict):
                        # Retrieve primary key value using dot-notation path
                        primary_key_value, key_found = _get_nested_obj(primary_item, primary_key)

                        nested_value: Any = None # Default value to nest
                        found_match = False

                        if key_found and primary_key_value is not None:
                            # Find matching secondary items (these are already copies)
                            matching_secondaries = secondary_lookup.get(primary_key_value, [])

                            # Determine value to nest based on join type
                            if join_type == JoinType.ONE_TO_MANY:
                                nested_value = matching_secondaries
                                found_match = True # Even an empty list is a successful join operation result
                            elif join_type == JoinType.ONE_TO_ONE:
                                nested_value = matching_secondaries[0] if matching_secondaries else None
                                found_match = True # None is a valid result for one-to-one

                        elif not key_found:
                            print(f"Warning: Primary join key path '{primary_key}' not found in primary item: {primary_item}. Setting '{nesting_field}' to default.")
                            # Set default value based on join type even if key not found
                            nested_value = [] if join_type == JoinType.ONE_TO_MANY else None
                            found_match = True # Treat missing key as needing default value set
                        # else: primary_key_value is None, handle similarly to key not found
                        else:
                            print(f"Warning: Primary join key path '{primary_key}' value is None in primary item: {primary_item}. Setting '{nesting_field}' to default.")
                            nested_value = [] if join_type == JoinType.ONE_TO_MANY else None
                            found_match = True

                        # Nest the result using dot-notation path
                        if found_match:
                            try:
                                # Use _set_nested_obj to handle nested output path
                                success = _set_nested_obj(primary_item, nesting_field, nested_value, create_missing=True)
                                if not success:
                                    print(f"Warning: Failed to set nested value for path '{nesting_field}' in primary item.")
                            except TypeError as e:
                                 print(f"Error setting nesting path '{nesting_field}': {e}. Skipping nesting for this item.")
                                 # Potentially log traceback: traceback.print_exc()

                    else:
                        print(f"Warning: Item found in primary list/object '{primary_path}' is not a dictionary: {type(primary_item)}. Skipping join for this item.")

            # After all joins are processed, return the modified working_data
            # Note: If primary_path pointed to a single object, working_data at that path
            # will contain the modified single object, not a list.
            return MapperOutputSchema(mapped_data=working_data)

        except ValidationError as e:
             # Handle configuration validation errors
             print(f"Error: Config validation failed for MapperNode: {e}")
             return MapperOutputSchema(mapped_data=None) # Return None on config error
        except Exception as e:
             # Handle any other unexpected errors during processing
             print(f"Error processing MapperNode: {e}")
             traceback.print_exc()
             return MapperOutputSchema(mapped_data=None) # Return None on general error
