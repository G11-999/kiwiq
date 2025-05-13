"""
Mapper node for iterating over collections and dispatching items to other nodes.

This module defines the MapListRouterNode, which iterates over items in a list or
values in a dictionary found at a specified path within the input data.
Each item is then potentially transformed based on outgoing edge mappings
and sent to one or more target nodes using LangGraph's Command/Send mechanism.
"""
import copy
from typing import Any, Dict, List, Optional, Type, ClassVar, Union, Tuple, Iterable

from pydantic import Field, model_validator, BaseModel
from langgraph.types import Command, Send

from kiwi_app.workflow_app.constants import LaunchStatus
from workflow_service.graph.graph import EdgeMapping # Import EdgeMapping for type hint
from workflow_service.registry.schemas.base import BaseSchema, BaseNodeConfig
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema, DynamicRouterNode, RouterSchema as BaseRouterSchema
from workflow_service.config.constants import TEMP_STATE_UPDATE_KEY, ROUTER_CHOICE_KEY, OBJECT_PATH_REFERENCE_DELIMITER, NODE_EXECUTION_ORDER_KEY
from workflow_service.utils.utils import get_central_state_field_key

from workflow_service.config.constants import GRAPH_STATE_SPECIAL_NODE_NAME, STATE_KEY_DELIMITER

# --- Configuration Schemas ---

# Removed MapperMapping as mappings are now defined on edges

class MapTargetConfig(BaseNodeConfig):
    """
    Configuration for mapping items from a specific source path to destinations.
    Transformations are now defined by the mappings on the outgoing edges in the graph schema.
    Items can be batched before sending.

    Attributes:
        source_path (str): Path within the input data pointing to the list or dictionary to iterate over.
                           Uses OBJECT_PATH_REFERENCE_DELIMITER.
        destinations (List[str]): List of target node IDs to send each processed item/batch to.
                                  These IDs must exist in the parent config's `choices` list
                                  and have a corresponding edge defined in the graph schema.
        batch_size (int): Number of items to group into a batch before sending.
                          Defaults to 1 (no batching). Must be 1 or greater.
        batch_field_name (Optional[str]): If provided, the sent data (single item or batch list)
                                         will be wrapped in a dictionary with this string as the key.
                                         Example: {batch_field_name: item} or {batch_field_name: [item1, item2]}.
                                         Defaults to None (data sent as-is).
    """
    source_path: str = Field(..., description=f"Path to the source list or dictionary in input data, using '{OBJECT_PATH_REFERENCE_DELIMITER}'.")
    destinations: List[str] = Field(..., min_length=1, description="List of target node IDs.")
    map_dict_values_if_object_is_dict: bool = Field(
        False,
        description="If True, the values of a dictionary found at the source path will be mapped to the destinations instead of the entire dictionary as a single item."
    )
    # Mappings are now defined on the edges in GraphSchema, not here.
    batch_size: int = Field(
        1,
        ge=1, # Greater than or equal to 1
        description="Number of items to group into a batch. Defaults to 1 (no batching)."
    )
    batch_field_name: Optional[str] = Field(
        None,
        description="Optional field name to wrap the sent item or batch list under. Defaults to None."
    )


class MapperConfigSchema(BaseRouterSchema):
    """
    Configuration schema for the MapListRouterNode.

    Inherits `choices` from BaseRouterSchema to declare potential target nodes for graph visualization
    and validation. `allow_multiple` is inherited but not directly used by the mapper's logic.

    Attributes:
        choices (List[str]): Inherited. Declares all possible nodes that items can be sent to.
        allow_multiple (bool): Inherited. Not directly used by mapper logic.
        map_targets (List[MapTargetConfig]): List of mapping configurations defining source paths and destinations.
                                             Transformations are determined by edge mappings.
    """
    # Inherits 'choices' and 'allow_multiple' from BaseRouterSchema
    map_targets: List[MapTargetConfig] = Field(
        ...,
        min_length=1,
        description="List of configurations defining source paths and destinations. Mappings are defined on edges."
    )

    @model_validator(mode='after')
    def validate_destinations_exist_in_choices(self) -> 'MapperConfigSchema':
        """
        Validates that all destination node IDs specified in map_targets
        are present in the main 'choices' list.
        """
        available_choices = set(self.choices)
        for i, target_config in enumerate(self.map_targets):
            for destination_id in target_config.destinations:
                if destination_id not in available_choices:
                    raise ValueError(
                        f"Destination ID '{destination_id}' in map_targets[{i}] is not present "
                        f"in the main 'choices' list: {self.choices}"
                    )
        return self


# --- Helper Function ---

def _get_nested_value(data: Union[Dict[str, Any], Any], path: str) -> Tuple[Any, bool]:
    """
    Retrieves a value from a nested structure (dict or object) using a path string.

    Args:
        data: The dictionary or object to navigate.
        path: The path string, using OBJECT_PATH_REFERENCE_DELIMITER. If empty or '.', returns the data itself.

    Returns:
        Tuple[Any, bool]: (value, success_flag). (None, False) if path is invalid.
    """
    # Treat empty path or '.' as referring to the object itself
    if not path or path == '.':
        return data, True

    keys = path.split(OBJECT_PATH_REFERENCE_DELIMITER)
    current_value = data
    try:
        for key in keys:
            if isinstance(current_value, dict):
                current_value = current_value[key]
            elif hasattr(current_value, key): # Check for attribute access
                 current_value = getattr(current_value, key)
            # TODO: Add list index access if required?
            else:
                return None, False # Cannot navigate further
        return current_value, True
    except (KeyError, TypeError, IndexError, AttributeError):
        return None, False # Path invalid or structure mismatch


# --- Mapper Node Implementation ---

class MapListRouterNode(DynamicRouterNode):
    """
    Iterates over items in a list or dictionary from the input data,
    optionally maps/transforms each item based on outgoing edge definitions,
    optionally batches them, wraps them in a dictionary, and sends them to
    specified target nodes using LangGraph's Command/Send mechanism.

    This node is useful for processing collections, batching data for efficiency,
    and distributing tasks or data points to subsequent nodes in the workflow.

    Inherits from DynamicRouterNode primarily to utilize the `choices`
    configuration for graph validation and visualization.
    """
    node_name: ClassVar[str] = "map_list_router_node"
    node_version: ClassVar[str] = "0.1.1" # Version bump due to config change
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.PRODUCTION

    # Input schema is dynamic
    # Ineriting input / output dynamic schemas from base class!
    # input_schema_cls: ClassVar[Type[DynamicSchema]] = DynamicSchema
    # Output schema is dynamic (effectively passes through state + commands)
    # output_schema_cls: ClassVar[Type[DynamicSchema]] = DynamicSchema
    config_schema_cls: ClassVar[Type[MapperConfigSchema]] = MapperConfigSchema

    # Instance config
    config: MapperConfigSchema

    def _prepare_input_data(self, input_data: Union[DynamicSchema, Dict[str, Any]]) -> Dict[str, Any]:
        """Ensures input data is a dictionary."""
        if isinstance(input_data, dict):
            return copy.deepcopy(input_data)
        elif hasattr(input_data, 'model_dump'):
            # Ensure nested Pydantic models are also serialized
            return input_data.model_dump(mode='json')
        else:
            try:
                # Attempt a deep copy dictionary conversion
                return copy.deepcopy(dict(input_data))
            except Exception:
                self.warning(f"Could not convert input data of type {type(input_data)} to dict in MapListRouterNode. Proceeding with empty data.")
                return {}

    def _create_batches(self, items: List[Any], batch_size: int) -> List[Union[Any, List[Any]]]:
        """
        Creates batches from a list of items.

        If batch_size is 1, returns a list where each element is a single original item.
        If batch_size > 1, returns a list of lists, where each inner list is a batch.
        The last batch may contain fewer items than batch_size.

        Args:
            items (List[Any]): The list of items to batch.
            batch_size (int): The desired size of each batch. Must be >= 1.

        Returns:
            List[Union[Any, List[Any]]]: A list of batches (or single items if batch_size is 1).
        """
        if not items:
            return []
        if batch_size <= 0:
            # Should be caught by Pydantic validation, but good practice to handle
            self.warning("Batch size must be 1 or greater. Defaulting to 1.")
            batch_size = 1

        if batch_size == 1:
            # No batching needed, return items individually
            return items
        else:
            # Create batches of size batch_size
            return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]

    async def process(self, input_data: Union[DynamicSchema, Dict[str, Any]], config: Optional[Dict[str, Any]] = None, *args: Any, **kwargs: Any) -> Command:
        """
        Processes input data, iterates over specified collections, maps items based on edge configs,
        batches them according to node config, optionally wraps them, and generates a LangGraph
        Command to send items/batches to target nodes.

        Args:
            input_data: The dynamic input data for the node.
            config: Runtime configuration passed by LangGraph, expected to contain
                    `outgoing_edges` mapping this node's ID to its outgoing edges.
            *args: Additional positional arguments (unused).
            **kwargs: Additional keyword arguments (unused).

        Returns:
            Command: A LangGraph Command object containing Send actions for each item/batch
                     and a state update including node execution order.

        Raises:
            KeyError: If the runtime config is missing expected structure (`outgoing_edges`).
            ValueError: If an edge specified in the node config's destinations is missing
                        from the runtime config's outgoing_edges, or if batch_size is invalid (though Pydantic should catch this).
        """
        input_dict = self._prepare_input_data(input_data)
        node_config: MapperConfigSchema = self.config # Use the node's validated instance config
        runtime_config = config if config else {}
        runtime_config_configurable = runtime_config.get("configurable", {}) # Use .get for safety

        # Ensure runtime_config has the necessary structure
        # Using .get for safer access
        outgoing_edges = runtime_config_configurable.get("outgoing_edges", {})
        outgoing_edges_for_node = outgoing_edges.get(self.node_id, {})

        if not outgoing_edges_for_node and node_config.map_targets:
             self.warning(f"MapListRouterNode '{self.node_id}' has map_targets defined, but no outgoing edges found in runtime config. No items will be sent.")
             state_update_dict = self.build_output_state_update(None, runtime_config)
             return Command(goto=[], update=state_update_dict)
        elif not node_config.map_targets:
            # No mapping defined, just update state and return
            self.info(f"MapListRouterNode '{self.node_id}' has no map_targets defined. Only updating state.")
            state_update_dict = self.build_output_state_update(None, runtime_config)
            return Command(goto=[], update=state_update_dict)


        sends: List[Send] = []
        # Dictionary to hold items collected before batching.
        # Key: Tuple(destination_node_id: str, target_config_index: int)
        # Value: List[processed_item]
        collected_items_per_rule: Dict[Tuple[str, int], List[Any]] = {}

        # --- Step 1: Iterate through map targets, process items, and collect them per destination rule ---
        for target_config_index, target_config in enumerate(node_config.map_targets):
            # Get the source collection (list or dict) from input data
            source_collection, found = _get_nested_value(input_dict, target_config.source_path)

            if not found:
                self.warning(f"Source path '{target_config.source_path}' not found in input data for MapListRouterNode {self.node_id}. Skipping target config index {target_config_index}.")
                continue # Skip this target_config

            # Determine items to iterate over
            items_to_process: Iterable[Any]
            if isinstance(source_collection, list):
                items_to_process = source_collection
            elif isinstance(source_collection, dict):
                if target_config.map_dict_values_if_object_is_dict:
                    items_to_process = source_collection.values() # Iterate over dictionary values
                else:
                    items_to_process = [source_collection] # Iterate over the entire dictionary as a single item
            # NOTE: this node doesn't map primitive types i.e. non-list/non-dict!
            else:
                self.warning(f"Source path '{target_config.source_path}' does not point to a list or dict in MapListRouterNode {self.node_id}. Found type: {type(source_collection)}. Skipping target config index {target_config_index}.")
                continue # Skip this target_config

            # Process each item in the collection
            for item_index, item in enumerate(items_to_process):
                # Process for each destination specified in this target_config
                for destination_node_id in target_config.destinations:
                    # Define the unique key for this rule (destination + target config index)
                    rule_key = (destination_node_id, target_config_index)

                    # Initialize list for this rule if it's the first time seeing it
                    if rule_key not in collected_items_per_rule:
                        collected_items_per_rule[rule_key] = []

                    # Retrieve the specific edge definition from runtime_config
                    edge_to_destination = outgoing_edges_for_node.get(destination_node_id)
                    if edge_to_destination is None:
                        # This should ideally be caught during graph validation, but double-check here.
                        raise ValueError(f"Configuration error in MapListRouterNode '{self.node_id}': Destination '{destination_node_id}' specified in map_targets index {target_config_index} (source: '{target_config.source_path}'), but no corresponding outgoing edge found in runtime config.")

                    edge_mappings: Optional[List[EdgeMapping]] = edge_to_destination.mappings
                    processed_item: Any # The item after applying edge mappings (or the original item)

                    # Apply mappings defined on the edge, if any
                    if edge_mappings:
                        mapped_item = {}
                        for mapping in edge_mappings:
                            # Use '.' as src_field to map the entire item if needed
                            src_value, src_found = _get_nested_value(item, mapping.src_field)
                            if src_found:
                                mapped_item[mapping.dst_field] = src_value
                            else:
                                self.warning(f"Source field '{mapping.src_field}' specified in edge mapping to '{destination_node_id}' not found in item at index {item_index} from path '{target_config.source_path}' (target_config index {target_config_index}) in MapListRouterNode {self.node_id}.")
                        processed_item = mapped_item
                    else:
                        # No mappings on the edge: Use item as-is (but ensure serializability if possible)
                        if isinstance(item, BaseModel):
                            try:
                                processed_item = item.model_dump(mode='json')
                            except Exception as e:
                                self.warning(f"Could not serialize Pydantic item (index {item_index}, source: '{target_config.source_path}', target_config index {target_config_index}) to dict in MapListRouterNode {self.node_id}. Using original object. Error: {e}")
                                processed_item = item # Keep original if dump fails
                        elif isinstance(item, (dict, list, str, int, float, bool, type(None))):
                            processed_item = item # Already serializable
                        else:
                            self.warning(f"Using non-standard type {type(item)} (index {item_index}, source: '{target_config.source_path}', target_config index {target_config_index}) as-is from MapListRouterNode {self.node_id} to {destination_node_id}. Ensure target node can handle it.")
                            processed_item = item

                    # Add the processed item to the collection for its specific rule (dest + target_config index)
                    # Using deepcopy for safety as before.
                    collected_items_per_rule[rule_key].append(copy.deepcopy(processed_item))

        # --- Step 2: Iterate through collected items per rule, batch, wrap, and create Send commands ---
        for (destination_node_id, target_config_index), items_for_rule in collected_items_per_rule.items():
            # Retrieve the corresponding target_config to get batching/wrapping rules
            if target_config_index >= len(node_config.map_targets):
                 # This should not happen if logic is correct, but safety check
                 self.error(f"Internal error: target_config_index {target_config_index} out of bounds.")
                 continue
            target_config = node_config.map_targets[target_config_index]

            # Ensure the destination from the key matches the destinations in the config
            # This is another safety check
            if destination_node_id not in target_config.destinations:
                self.error(f"Internal error: Mismatch between rule key destination '{destination_node_id}' and target_config destinations {target_config.destinations} at index {target_config_index}.")
                continue

            batch_size = target_config.batch_size
            batch_field_name = target_config.batch_field_name

            if not items_for_rule:
                # No items were successfully processed for this specific rule
                self.debug(f"No items collected for destination '{destination_node_id}' from target_config index {target_config_index}. Skipping Send command generation for this rule.")
                continue

            # Create batches based on the configuration for this target_config
            batches_or_items = self._create_batches(items_for_rule, batch_size)

            # Process each batch (or individual item if batch_size=1)
            for data_payload in batches_or_items:
                # data_payload is either a single processed item (if batch_size=1)
                # or a list of processed items (if batch_size > 1)

                final_payload_to_send: Any # This will be sent in the Command

                # Wrap the payload if batch_field_name is provided
                if batch_field_name:
                    final_payload_to_send = {batch_field_name: data_payload}
                    self.debug(f"Wrapping payload for {destination_node_id} (from target_config index {target_config_index}) under key '{batch_field_name}'.")
                else:
                    # Send the batch/item as-is
                    final_payload_to_send = data_payload

                # Create the Send action with a deep copy of the final payload
                send_data_copy = copy.deepcopy(final_payload_to_send)
                # self.info(f"Prepared data for {destination_node_id} (from target_config index {target_config_index}, batch_size={batch_size}, wrapped={bool(batch_field_name)}): {send_data_copy}")
                
                # Central state hack!
                # TODO: FIXME
                # Add central state keys to data copy!
                central_state_data = kwargs.get("central_state_data", {})
                if (not isinstance(send_data_copy, dict)) and central_state_data:
                    self.warning(f"Send data copy is not a dict in MapListRouterNode {self.node_id}. Creating a dict with 'data' key to wrap object and adding central state data directly.")
                    send_data_copy = {"data": send_data_copy}
                send_data_copy.update(central_state_data)

                sends.append(Send(destination_node_id, send_data_copy))

            # No need to clear items here, as we are iterating through the collected_items_per_rule dictionary directly.
            # Each rule's items are processed exactly once.


        # --- Step 3: Build the standard state update ---
        # Pass None as output_data, as the primary output is via Sends
        state_update_dict = self.build_output_state_update(None, runtime_config)


        # --- Step 4: Return the Command ---
        self.info(f"MapListRouterNode '{self.node_id}' generated {len(sends)} Send commands based on {len(collected_items_per_rule)} processing rules.")
        return Command(goto=sends, update=state_update_dict)
