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
from workflow_service.registry.schemas.base import BaseSchema
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema, DynamicRouterNode, RouterSchema as BaseRouterSchema
from workflow_service.config.constants import TEMP_STATE_UPDATE_KEY, ROUTER_CHOICE_KEY, OBJECT_PATH_REFERENCE_DELIMITER, NODE_EXECUTION_ORDER_KEY
from workflow_service.utils.utils import get_central_state_field_key


# --- Configuration Schemas ---

# Removed MapperMapping as mappings are now defined on edges

class MapTargetConfig(BaseSchema):
    """
    Configuration for mapping items from a specific source path to destinations.
    Transformations are now defined by the mappings on the outgoing edges in the graph schema.

    Attributes:
        source_path (str): Path within the input data pointing to the list or dictionary to iterate over.
                           Uses OBJECT_PATH_REFERENCE_DELIMITER.
        destinations (List[str]): List of target node IDs to send each processed item to.
                                  These IDs must exist in the parent config's `choices` list
                                  and have a corresponding edge defined in the graph schema.
    """
    source_path: str = Field(..., description=f"Path to the source list or dictionary in input data, using '{OBJECT_PATH_REFERENCE_DELIMITER}'.")
    destinations: List[str] = Field(..., min_length=1, description="List of target node IDs.")
    # Mappings are now defined on the edges in GraphSchema, not here.


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
    and sends them to specified target nodes using LangGraph's Command/Send mechanism.

    This node is useful for processing collections and distributing tasks
    or data points to subsequent nodes in the workflow.

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
            return input_data.model_dump(mode='json')
        else:
            try:
                return copy.deepcopy(dict(input_data))
            except Exception:
                self.warning(f"Could not convert input data of type {type(input_data)} to dict in MapListRouterNode. Proceeding with empty data.")
                return {}

    async def process(self, input_data: Union[DynamicSchema, Dict[str, Any]], config: Optional[Dict[str, Any]] = None, *args: Any, **kwargs: Any) -> Command:
        """
        Processes input data, iterates over specified collections, maps items based on edge configs,
        and generates a LangGraph Command to send items to target nodes.

        Args:
            input_data: The dynamic input data for the node.
            config: Runtime configuration passed by LangGraph, expected to contain
                    `outgoing_edges` mapping this node's ID to its outgoing edges.
            *args: Additional positional arguments (unused).
            **kwargs: Additional keyword arguments (unused).

        Returns:
            Command: A LangGraph Command object containing Send actions for each item
                     and a state update including node execution order.

        Raises:
            KeyError: If the runtime config is missing expected structure (`outgoing_edges`).
            ValueError: If an edge specified in the node config's destinations is missing
                        from the runtime config's outgoing_edges.
        """
        input_dict = self._prepare_input_data(input_data)
        node_config: MapperConfigSchema = self.config # Use the node's validated instance config
        runtime_config = config if config else {}
        runtime_config = runtime_config.get("configurable")

        # Ensure runtime_config has the necessary structure
        if "outgoing_edges" not in runtime_config or self.node_id not in runtime_config["outgoing_edges"]:
             # If there are no outgoing edges defined in the runtime config for this node, but the
             # node config expects destinations, it's an inconsistency. However, if the node config
             # also has no map_targets, then it's okay (a mapper node with nothing to map).
             if node_config.map_targets:
                 self.warning(f"MapListRouterNode '{self.node_id}' has map_targets defined, but no outgoing edges found in runtime config. No items will be sent.")
             # Return an empty command with just the state update for node order
             state_update_dict = self.build_output_state_update(None, runtime_config)
             state_update_dict.pop(get_central_state_field_key(self.node_id), None)
             state_update_dict.pop(self.node_id, None)
             if get_central_state_field_key(NODE_EXECUTION_ORDER_KEY) not in state_update_dict:
                 state_update_dict[get_central_state_field_key(NODE_EXECUTION_ORDER_KEY)] = [self.node_id]
             return Command(goto=[], update=state_update_dict)

        outgoing_edges_for_node = runtime_config["outgoing_edges"][self.node_id]

        sends: List[Send] = []

        # Iterate through each mapping configuration target defined in the node config
        for target_config in node_config.map_targets:
            # 1. Get the source collection (list or dict) from input data
            source_collection, found = _get_nested_value(input_dict, target_config.source_path)

            if not found:
                self.warning(f"Source path '{target_config.source_path}' not found in input data for MapListRouterNode {self.node_id}.")
                continue

            # Determine items to iterate over
            items_to_process: Iterable[Any]
            if isinstance(source_collection, list):
                items_to_process = source_collection
            elif isinstance(source_collection, dict):
                items_to_process = source_collection.values() # Iterate over dictionary values
            else:
                self.warning(f"Source path '{target_config.source_path}' does not point to a list or dict in MapListRouterNode {self.node_id}. Found type: {type(source_collection)}. Skipping this target.")
                continue

            # 2. Process each item in the collection
            for item_index, item in enumerate(items_to_process):

                # 3. Create Send actions for each destination specified in this target_config
                for destination_node_id in target_config.destinations:
                    # Retrieve the specific edge definition from runtime_config
                    edge_to_destination = outgoing_edges_for_node.get(destination_node_id)
                    if edge_to_destination is None:
                        # This should ideally be caught during graph validation, but double-check here.
                        raise ValueError(f"Configuration error in MapListRouterNode '{self.node_id}': Destination '{destination_node_id}' specified in map_targets, but no corresponding outgoing edge found in runtime config.")

                    edge_mappings: Optional[List[EdgeMapping]] = edge_to_destination.mappings
                    data_to_send: Any

                    # 4. Apply mappings defined on the edge, if any
                    if edge_mappings:
                        mapped_item = {}
                        for mapping in edge_mappings:
                            # Use '.' as src_field to map the entire item
                            src_value, src_found = _get_nested_value(item, mapping.src_field)
                            if src_found:
                                mapped_item[mapping.dst_field] = src_value
                            else:
                                self.warning(f"Source field '{mapping.src_field}' specified in edge mapping to '{destination_node_id}' not found in item at index {item_index} from path '{target_config.source_path}' in MapListRouterNode {self.node_id}.")
                        data_to_send = mapped_item
                    else:
                        # No mappings on the edge: Send item as-is.
                        if isinstance(item, BaseModel):
                            try:
                                data_to_send = item.model_dump(mode='json')
                            except Exception as e:
                                self.warning(f"Could not serialize item {item} to dict in MapListRouterNode {self.node_id}. Sending as is. Error: {e}")
                                data_to_send = item
                        elif isinstance(item, (dict, list, str, int, float, bool, type(None))):
                            data_to_send = item # Already serializable
                        else:
                            self.warning(f"Sending non-standard type {type(item)} as-is from MapListRouterNode {self.node_id} to {destination_node_id}. Ensure target node can handle it.")
                            data_to_send = item

                    # Create the Send action with a deep copy of the data
                    send_data_copy = copy.deepcopy(data_to_send)
                    self.info(f"Sending data to {destination_node_id}: {send_data_copy}")
                    sends.append(Send(destination_node_id, send_data_copy))

        # 5. Build the standard state update (primarily for node execution order)
        state_update_dict = self.build_output_state_update(None, runtime_config) # Pass None as output_data
        # state_update_dict.pop(get_central_state_field_key(self.node_id), None) # Clean up potential None key
        # state_update_dict.pop(self.node_id, None) # Clean up potential node_id key
        # if get_central_state_field_key(NODE_EXECUTION_ORDER_KEY) not in state_update_dict:
        #      state_update_dict[get_central_state_field_key(NODE_EXECUTION_ORDER_KEY)] = [self.node_id]

        # 6. Return the Command
        return Command(goto=sends, update=state_update_dict)


