"""
Graph runtime adapter module.

This module contains base class and implementations for runtime adapters that handle the
actual execution of workflow graphs using different underlying frameworks.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Type, Union, AsyncIterator, cast, Literal, Callable
from pathlib import Path
import os
import json
import asyncio
from pydantic import create_model
from typing_extensions import TypedDict

from workflow_service.config.constants import ROUTER_CHOICE_KEY, TEMP_STATE_UPDATE_KEY, HITL_USER_PROMPT_KEY, HITL_USER_SCHEMA_KEY, GRAPH_STATE_SPECIAL_NODE_NAME
from workflow_service.graph.builder import GraphEntities
from workflow_service.graph.graph import GraphSchema
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema
from langgraph.graph import START
from langgraph.types import Command, interrupt
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.runnables.config import RunnableConfig

from workflow_service.registry.schemas.base import BaseSchema
from workflow_service.utils.utils import get_central_state_field_key

from workflow_service.registry.nodes.core.base import BaseNode
from workflow_service.registry.registry import MockRegistry
from workflow_service.utils.utils import get_node_output_state_key


class GraphRuntimeAdapter(ABC):
    """
    Abstract base class for graph runtime adapters.
    
    This class defines the interface that all runtime adapters must implement.
    Runtime adapters are responsible for building and executing graphs using
    an underlying graph execution framework (e.g., LangGraph).
    
    Attributes:
        None
    """
    
    @abstractmethod
    def build_graph(
        self, 
        graph_entities: GraphEntities,
        runtime_config: Optional[Dict[str, Any]] = None
    ) -> Tuple[Any, Dict[str, Any]]:
        """
        Build a graph from a graph schema.
        
        Args:
            graph_entities (GraphEntities): Graph entities containing node instances and schemas.
            runtime_config (Optional[Dict[str, Any]]): Runtime configuration for the graph.
            
        Returns:
            Tuple[Any, Dict[str, Any]]: The built graph and the initial graph state.
        """
        pass
    
    @abstractmethod
    def execute_graph(
        self,
        graph: Any,
        input_data: Dict[str, Any],
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a graph with input data.
        
        Args:
            graph (Any): The graph to execute.
            input_data (Dict[str, Any]): Input data for the graph.
            config (Dict[str, Any]): Runtime configuration for execution.
            
        Returns:
            Dict[str, Any]: Output data from the graph.
        """
        pass
    
    @abstractmethod
    async def aexecute_graph_stream(
        self,
        graph: Any,
        input_data: Dict[str, Any],
        config: Dict[str, Any]
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute a graph with input data and stream results.
        
        Args:
            graph (Any): The graph to execute.
            input_data (Dict[str, Any]): Input data for the graph.
            config (Dict[str, Any]): Runtime configuration for execution.
            
        Yields:
            Dict[str, Any]: Streaming outputs from the graph.
        """
        pass

    @staticmethod
    @abstractmethod
    def routing_node_post_processor(
        node_outputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Post-process the outputs of a routing node.
        """
        pass


class LangGraphRuntimeAdapter(GraphRuntimeAdapter):
    """
    Runtime adapter for LangGraph.
    
    This adapter uses LangGraph to build and execute workflow graphs based on
    graph entities created by the GraphBuilder.
    
    Attributes:
        checkpoint_dir (Optional[str]): Directory to store checkpoints.
    """
    
    def __init__(self, checkpoint_dir: Optional[str] = None):
        """
        Initialize the LangGraph runtime adapter.
        
        Args:
            checkpoint_dir (Optional[str]): Directory to store checkpoints.
                If None, checkpointing is disabled.
        """
        self.checkpoint_dir = checkpoint_dir
        
        # Create checkpoint directory if it doesn't exist
        if self.checkpoint_dir:
            os.makedirs(self.checkpoint_dir, exist_ok=True)
    
    def build_graph(
        self, 
        graph_entities: GraphEntities,
        # runtime_config: Optional[Dict[str, Any]] = None
    ) -> Tuple[Any, Dict[str, Any]]:
        """
        Build a LangGraph StateGraph from a graph schema and entities.
        
        Args:
            graph_entities (GraphEntities): Graph entities containing node instances and schemas.
            runtime_config (Optional[Dict[str, Any]]): Runtime configuration for the graph.
            
        Returns:
            Tuple[Any, Dict[str, Any]]: The built StateGraph and initial state.
        """
        from langgraph.graph import StateGraph, END
        from typing import get_origin, get_args, get_type_hints
        
        # if runtime_config is None:
        #     runtime_config = {}
            
        # Extract entities
        node_instances = graph_entities["node_instances"]
        graph_state_cls = graph_entities["graph_state"]
        entity_runtime_config = graph_entities["runtime_config"]
        runtime_config = entity_runtime_config
        
        # Store input and output node IDs in runtime config for easier access
        # entity_runtime_config["input_node_id"] = graph_entities["input_node_id"]
        # entity_runtime_config["output_node_id"] = graph_entities["output_node_id"]
        
        # Merge runtime configs if provided
        # if runtime_config:
        #     for key, value in runtime_config.items():
        #         if key in entity_runtime_config:
        #             entity_runtime_config[key].update(value)
        #         else:
        #             entity_runtime_config[key] = value
        
        # Create the StateGraph with the graph state class
        kwargs = {}
        input_schema = graph_entities["node_instances"][graph_entities["input_node_id"]].input_schema_cls
        output_schema = graph_entities["node_instances"][graph_entities["output_node_id"]].output_schema_cls
        if input_schema is not None:
            # Create a new input schema model with renamed fields using get_central_state_field_key
            # This ensures field names in the graph input match the central state field naming convention
            input_fields = {}
            for field_name, field_info in input_schema.model_fields.items():
                central_state_field_name = get_central_state_field_key(field_name)
                input_fields[central_state_field_name] = (field_info.annotation, field_info)
            
            # Dynamically create a new Pydantic model with the renamed fields
            renamed_input_schema = create_model(
                f"{input_schema.__name__}CentralState",
                __base__=DynamicSchema,
                __module__=input_schema.__module__,
                **input_fields
            )
            
            kwargs["input"] = renamed_input_schema
            input_schema = renamed_input_schema
        if output_schema:
            kwargs["output"] = output_schema
        print(f"kwargs GRAPH STATE INPUT SCHEMA!: {kwargs["input"].model_fields}")
        # import ipdb; ipdb.set_trace()
        state_graph = StateGraph(graph_state_cls, **kwargs)
        
        
        router_instances = {}

        # Add nodes to the graph
        for node_id, node_instance in node_instances.items():
            # Define a node function that captures the node instance and runtime config
            # def create_node_function(node_id, node, config):
            #     # This is a closure to capture node and config
            #     def node_function(state):
            #         # Process node's inputs based on runtime config
            #         node_inputs = self._prepare_node_inputs(state, node_id, config)
                    
            #         # Execute the node with prepared inputs
            #         node_outputs = node.process(**node_inputs)
                    
            #         # Map outputs to state updates
            #         state_updates = self._prepare_state_updates(node_outputs, node_id, config)
                    
            #         return state_updates
                
            #     return node_function

            # Set run annotations to provide proper type hints to LangGraph
            node_instance.set_run_annotations(
                state_type=graph_state_cls,
                config_type=RunnableConfig
            )
            # if node_id == graph_entities["input_node_id"]:
            #     if input_schema:
            #         node_instance.run.__func__.__annotations__.update({
            #             'input': input_schema
            #         })
            if MockRegistry.is_node_instance_hitl(node_instance) or MockRegistry.is_node_instance_router(node_instance):
                if MockRegistry.is_node_instance_hitl(node_instance):
                    node_instance.__class__.runtime_preprocessor = LangGraphRuntimeAdapter.interrupt_node_pre_processor
                elif MockRegistry.is_node_instance_router(node_instance):
                    router_instances[node_id] = node_instance
                    # NOTE: routing node config will be part of regular node configs! choices will be in dict from graph schema
                    node_instance.__class__.runtime_postprocessor = LangGraphRuntimeAdapter.routing_node_post_processor
                    # This annotation is for langgraph graph visualization!
                    node_instance.run.__func__.__annotations__.update({
                        'return': Command[Literal.__getitem__(tuple(node_instance.config.choices))]
                    })

            # Add the node to the graph with its function
            state_graph.add_node(node_id, 
                node_instance.run,
                # create_node_function(node_id, node_instance, entity_runtime_config)
            )
            
        
        # Add edges to the graph - from the schema
        # Collect edges by destination node ID to handle fan-in
        edges_by_dst = {}
        for edge in graph_entities["edges"]:
            if edge.src_node_id in router_instances or edge.src_node_id == GRAPH_STATE_SPECIAL_NODE_NAME or edge.dst_node_id == GRAPH_STATE_SPECIAL_NODE_NAME:
                    # NOTE: routing edges are dynamic and not added to the graph directly!
                    #     https://langchain-ai.github.io/langgraph/how-tos/command/#basic-usage
                    continue
            if edge.dst_node_id not in edges_by_dst:
                edges_by_dst[edge.dst_node_id] = []
            edges_by_dst[edge.dst_node_id].append(edge.src_node_id)
        
        # Process edges based on whether fan-in is enabled for the destination node
        for dst_node_id, src_node_ids in edges_by_dst.items():
            
            # Check if fan-in is enabled for this destination node
            enable_fan_in = False
            if dst_node_id in graph_entities["graph_schema"].nodes:
                enable_fan_in = graph_entities["graph_schema"].nodes[dst_node_id].enable_node_fan_in
            
            if enable_fan_in:
                state_graph.add_edge(src_node_ids, dst_node_id)
            else:
                for src_node_id in src_node_ids:
                    state_graph.add_edge(src_node_id, dst_node_id)
            
        
        
        # for edge in graph_entities["edges"]:
        #     # if edge.condition:
        #     #     # Add conditional edge
        #     #     state_graph.add_conditional_edges(
        #     #         edge.src_node_id,
        #     #         self._create_condition_function(edge.condition),
        #     #         {
        #     #             True: edge.dst_node_id,
        #     #             False: None  # No destination if condition fails
        #     #         }
        #     #     )
        #     # else:
        #         # Add standard edge
        #         if edge.src_node_id in router_instances or edge.src_node_id == GRAPH_STATE_SPECIAL_NODE_NAME or edge.dst_node_id == GRAPH_STATE_SPECIAL_NODE_NAME:
        #             # NOTE: routing edges are dynamic and not added to the graph directly!
        #             #     https://langchain-ai.github.io/langgraph/how-tos/command/#basic-usage
        #             continue
        #         # enable_node_fan_in
        #         state_graph.add_edge(edge.src_node_id, edge.dst_node_id)
        
        # Add END edge from output node if specified
        if graph_entities["output_node_id"]:
            state_graph.add_edge(graph_entities["output_node_id"], END)
        
        # Set the entry point - this is the input node
        if graph_entities["input_node_id"]:
            state_graph.set_entry_point(graph_entities["input_node_id"])
            
            # For the input node, we need to set the input schema state annotations
            if graph_entities["input_node_id"] in node_instances:
                input_node = node_instances[graph_entities["input_node_id"]]
                if input_node.input_schema_cls is not None:
                    # Ensure the input node's run method has appropriate type annotations
                    input_node.set_run_annotations(
                        state_type=input_schema,
                        config_type=RunnableConfig
                    )
        
        # Get checkpointing config
        use_checkpointing = runtime_config.get("use_checkpointing", False)
        checkpointer_type = runtime_config.get("checkpointer_type", "memory")
        thread_id = runtime_config.get("thread_id", None)
        
        # Compile the graph with appropriate settings
        compiled_kwargs = {}
        
        if use_checkpointing and thread_id:  #  and self.checkpoint_dir
            # from langgraph.checkpoint import JsonCheckpoint
            # checkpoint_path = Path(self.checkpoint_dir) / f"{checkpoint_id}.json"
            # JsonCheckpoint(checkpoint_path)
            if checkpointer_type == "memory":
                checkpointer = MemorySaver()
            else:
                raise NotImplementedError(f"Checkpointer type {checkpointer_type} not implemented")
            compiled_kwargs["checkpointer"] = checkpointer
        
        # TODO: debug streaming!
        # Add debug option if specified
        # if runtime_config.get("debug", False):
        #     compiled_kwargs["debug"] = True
        print("\n\n\n\n#### compiled_kwargs", compiled_kwargs, "\n\n\n\n")
        # Compile the graph
        # print(f"compiled_kwargs: {compiled_kwargs}")
        compiled_graph = state_graph.compile(**compiled_kwargs)
        
        # # Create initial state based on graph_state_cls
        # # If graph_state_cls is a TypedDict-like class, we need to create a dictionary with the correct structure
        # initial_state = {}
        
        # # If graph_state_cls is a normal class (with __init__), create an instance
        # if hasattr(graph_state_cls, "__annotations__"):
        #     # It's a TypedDict-like class, find required fields with default values
        #     type_hints = get_type_hints(graph_state_cls)
            
        #     for field_name, field_type in type_hints.items():
        #         # Check if the field has a default value in graph_state_cls
        #         if hasattr(graph_state_cls, field_name):
        #             default_value = getattr(graph_state_cls, field_name)
        #             initial_state[field_name] = default_value
        #         else:
        #             # Handle Optional fields
        #             origin = get_origin(field_type)
        #             args = get_args(field_type)
                    
        #             if origin is Union and type(None) in args:
        #                 # It's an Optional field, set to None
        #                 initial_state[field_name] = None
        
        # # Initialize node states in the initial state
        # for node_id in node_instances:
        #     # Only initialize if not already set
        #     if node_id not in initial_state:
        #         initial_state[node_id] = {}
                
        return compiled_graph

    @staticmethod
    def interrupt_node_pre_processor(
        node_instance: BaseNode,
        input_data: Dict[str, Any],
        config: Dict[str, Any],
        *args: Any,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        https://github.com/langchain-ai/langgraph/issues/1222
        https://github.com/langchain-ai/langgraph/discussions/929
        https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/wait-user-input/
        """
        # """
        # Post-process the outputs of an interrupt node.
        # """
        # TODO: ascertain if input_data can be BaseModel!
        output_schema = node_instance.output_schema_cls.model_json_schema()
        interrupt_data = {
            HITL_USER_PROMPT_KEY: input_data,
            HITL_USER_SCHEMA_KEY: output_schema,
        }
        print("\n\n\n\n#### interrupt_data", interrupt_data, "\n\n\n\n")
        hitl_data = interrupt(interrupt_data)
        # if RESUME_KEY not in config:
        #     config[RESUME_KEY] = {}
        # config[RESUME_KEY][node_instance.node_id] = hitl_data
        return hitl_data

    @staticmethod
    def routing_node_post_processor(
        node_instance: BaseNode,
        state_update: Dict[str, Any],
        config: Dict[str, Any],
        *args: Any,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Post-process the outputs of a routing node.
        """
        update = state_update.get(TEMP_STATE_UPDATE_KEY, {})
        update={get_node_output_state_key(node_instance.node_id): update} if update else {}
        
        # Dump any other update keys directly to final update without any modifications!
        update.update({k:v for k,v in state_update.items() if k not in [TEMP_STATE_UPDATE_KEY, ROUTER_CHOICE_KEY]})
        # import ipdb; ipdb.set_trace()
        return Command(
            # state update
            update=update,
            # control flow
            goto=state_update.get(ROUTER_CHOICE_KEY, None)
        )
    
    # def _prepare_node_inputs(self, state: Dict[str, Any], node_id: str, runtime_config: Dict[str, Any]) -> Dict[str, Any]:
    #     """
    #     Prepare inputs for a node based on the current state and runtime config.
        
    #     Args:
    #         state (Dict[str, Any]): Current graph state.
    #         node_id (str): ID of the node being executed.
    #         runtime_config (Dict[str, Any]): Runtime configuration.
            
    #     Returns:
    #         Dict[str, Any]: Prepared inputs for the node.
    #     """
    #     node_inputs = {}
    #     input_mappings = runtime_config.get("inputs", {}).get(node_id, {})
        
    #     # Handle the special case for input nodes that might use the initial input directly
    #     is_input_node = runtime_config.get("input_node_id") == node_id
    #     if is_input_node and "input" in state:
    #         # For input nodes, we can also extract values from the initial input
    #         initial_input = state.get("input", {})
    #         for field_name, field_value in initial_input.items():
    #             if field_name not in node_inputs:
    #                 node_inputs[field_name] = field_value
        
    #     # Process regular input mappings
    #     for input_field, source in input_mappings.items():
    #         if isinstance(source, list):
    #             # Source is [node_id, field_name]
    #             source_node_id, source_field = source
    #             if source_node_id in state:
    #                 node_state = state.get(source_node_id, {})
    #                 if hasattr(node_state, source_field):
    #                     # Access attribute if it's an object
    #                     node_inputs[input_field] = getattr(node_state, source_field)
    #                 elif isinstance(node_state, dict) and source_field in node_state:
    #                     # Access dictionary key if it's a dict
    #                     node_inputs[input_field] = node_state[source_field]
    #         elif isinstance(source, dict) and "path" in source:
    #             # Source is a path specification for deep accessing
    #             path = source["path"]
    #             current = state
    #             valid_path = True
                
    #             for path_part in path:
    #                 if isinstance(current, dict) and path_part in current:
    #                     current = current[path_part]
    #                 elif hasattr(current, path_part):
    #                     current = getattr(current, path_part)
    #                 else:
    #                     valid_path = False
    #                     break
                
    #             if valid_path:
    #                 node_inputs[input_field] = current
    #         else:
    #             # Source is a central state field
    #             if source in state:
    #                 node_inputs[input_field] = state[source]
        
    #     return node_inputs
    
    # def _prepare_state_updates(self, node_outputs: Dict[str, Any], node_id: str, runtime_config: Dict[str, Any]) -> Dict[str, Any]:
    #     """
    #     Prepare state updates based on node outputs and runtime config.
        
    #     Args:
    #         node_outputs (Dict[str, Any]): Outputs from the node execution.
    #         node_id (str): ID of the node that was executed.
    #         runtime_config (Dict[str, Any]): Runtime configuration.
            
    #     Returns:
    #         Dict[str, Any]: State updates to apply.
    #     """
    #     state_updates = {}
    #     output_mappings = runtime_config.get("outputs", {}).get(node_id, {})
        
    #     # Handle output node specially
    #     is_output_node = runtime_config.get("output_node_id") == node_id
        
    #     # Add node output to state under the node's ID
    #     # For objects with a model_dump method (like BaseSchema instances), use it
    #     if hasattr(node_outputs, "model_dump"):
    #         state_updates[node_id] = node_outputs.model_dump()
    #     else:
    #         state_updates[node_id] = node_outputs
        
    #     # For output nodes, also update the final output state
    #     if is_output_node:
    #         if hasattr(node_outputs, "model_dump"):
    #             state_updates["output"] = node_outputs.model_dump()
    #         else:
    #             state_updates["output"] = node_outputs
        
    #     # Map specific output fields to central state fields
    #     for output_field, central_field in output_mappings.items():
    #         # Handle nested path updates with dot notation (e.g., "messages.system")
    #         if isinstance(central_field, str) and "." in central_field:
    #             parts = central_field.split(".")
                
    #             # Create nested dictionaries for the path
    #             current_dict = state_updates
    #             for i, part in enumerate(parts[:-1]):
    #                 if part not in current_dict:
    #                     current_dict[part] = {}
    #                 current_dict = current_dict[part]
                
    #             # Set the value at the final path location
    #             if hasattr(node_outputs, output_field):
    #                 # If node_outputs is an object with attributes
    #                 value = getattr(node_outputs, output_field)
    #                 # Convert to dict if it's a schema object
    #                 if hasattr(value, "model_dump"):
    #                     value = value.model_dump()
    #                 current_dict[parts[-1]] = value
    #             elif isinstance(node_outputs, dict) and output_field in node_outputs:
    #                 # If node_outputs is a dictionary
    #                 value = node_outputs[output_field]
    #                 # Convert to dict if it's a schema object
    #                 if hasattr(value, "model_dump"):
    #                     value = value.model_dump()
    #                 current_dict[parts[-1]] = value
    #         else:
    #             # Direct field mapping
    #             if hasattr(node_outputs, output_field):
    #                 # If node_outputs is an object with attributes
    #                 value = getattr(node_outputs, output_field)
    #                 # Convert to dict if it's a schema object
    #                 if hasattr(value, "model_dump"):
    #                     value = value.model_dump()
    #                 state_updates[central_field] = value
    #             elif isinstance(node_outputs, dict) and output_field in node_outputs:
    #                 # If node_outputs is a dictionary
    #                 value = node_outputs[output_field]
    #                 # Convert to dict if it's a schema object
    #                 if hasattr(value, "model_dump"):
    #                     value = value.model_dump()
    #                 state_updates[central_field] = value
        
    #     return state_updates
    
    # def _create_condition_function(self, condition_config: Dict[str, Any]):
    #     """
    #     Create a condition function from a condition configuration.
        
    #     Args:
    #         condition_config (Dict[str, Any]): Condition configuration.
            
    #     Returns:
    #         Callable: A function that evaluates the condition.
    #     """
    #     def condition_function(state):
    #         # Implement condition evaluation based on condition_config
    #         # This is a placeholder for actual condition evaluation logic
    #         return True
        
    #     return condition_function
    @staticmethod
    def get_value_from_human(
        interrupt_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get a value from a human.
        """
        user_prompt = interrupt_data[HITL_USER_PROMPT_KEY]
        user_schema = interrupt_data[HITL_USER_SCHEMA_KEY]
        print("\n\n\n\n#### user prompt for interrupt", json.dumps(user_prompt, indent=4), "\n\n\n\n")
        print("\n\n\n\n#### user input required schema", json.dumps(user_schema, indent=4), "\n\n\n\n")
        response = input()
        return response

    def execute_graph(
        self,
        graph: Any,
        input_data: Dict[str, Any],
        config: Dict[str, Any],
        output_node_id: str = None,
        interrupt_handler: Callable = None
    ) -> Dict[str, Any]:
        """
        Execute a LangGraph with input data.
        
        Args:
            graph (Any): The LangGraph to execute.
            input_data (Dict[str, Any]): Input data for the graph.
            config (Dict[str, Any]): Runtime configuration for execution.
            
        Returns:
            Dict[str, Any]: Output data from the graph.
        """
        # TODO: FIXME: MUST TEST NESTED INPUT FIELDS AND DATA!
        input_data = {get_central_state_field_key(k): v for k, v in input_data.items()}
        
        if interrupt_handler is None:
            interrupt_handler = LangGraphRuntimeAdapter.get_value_from_human
        
        # Create a LangGraph config dict
        lg_config = {
            "configurable": config,  # config may have thread_id
            # "metadata": {
            #     "workflow_id": config.get("workflow_id", ""),
            #     "run_id": config.get("run_id", ""),
            #     "user_id": config.get("user_id"),
            #     "configurable": config.get("configurable", {})
            # }
        }
        
        # Add callbacks if provided
        # if "callbacks" in config:
        #     lg_config["callbacks"] = config["callbacks"]
        
        # Execute the graph
        # input_data can be None
        has_interrupts = True
        interrupt_data = None

        print("\n\n\n\n#### INPUT DATA SENT TO GRAPH INVOKE", input_data, "\n\n\n\n")

        while has_interrupts:
            # https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/#interrupt
            if interrupt_data:
                value_from_human = interrupt_handler(interrupt_data)
                result = graph.invoke(Command(resume=value_from_human), config=lg_config)
            else:
                result = graph.invoke(input_data, config=lg_config)
            print("\n\n\n\n#### GRAPH RUN PHASE FINISHED (Interrupted or Final Finished)! result", result, "\n\n\n\n")
            last_state = graph.get_state(lg_config)
            has_interrupts = False
            # final_state.tasks[0].interrupts  # check for keys as set in interrupt pre-processor below!
            interrupt_data = None
            if last_state.tasks:
                for task in last_state.tasks:
                    if task.interrupts:
                        has_interrupts = True
                        interrupt_data = task.interrupts[0].value
                        break
        
        # central states
        # looped over node outputs and fields were replaced
        # final output
        
        # result = graph.invoke(input_data, config=lg_config)
        final_state = graph.get_state(lg_config)
        # final_state.tasks[0].interrupts  # check for keys as set in interrupt pre-processor below!

        graph_output = None
        if output_node_id:
            graph_output = final_state.values.get(get_node_output_state_key(output_node_id), {})
        
        
        # final_state.values.get(get_node_output_state_key(output_node_id), {})
        central_state_keys = [k for k in final_state.values.keys() if k.startswith(GRAPH_STATE_SPECIAL_NODE_NAME)]
        central_state = {k: final_state.values[k] for k in central_state_keys}

        from langchain_core.load import dumpd, dumps, load, loads

        print("\n\n\n\n#### final_state", dumps(final_state, pretty=True), "\n\n\n\n")

        print("\n\n\n\n#### central_state", dumps(central_state, pretty=True), "\n\n\n\n")

        # print("\n\n\n\n#### graph_output", json.dumps(graph_output, indent=4), "\n\n\n\n")

        # node_id = "human_review"
        # print(dumps(final_state.values.get(get_node_output_state_key(node_id), {}), pretty=True))
        # Since this BaseModel / BaseSchema, it dumps well!
        # print(final_state.values.get(get_node_output_state_key(node_id), {}).model_dump_json(indent=4))

        
        # print(result)
        # print(final_state)
        print("\n\n\n\n#### graph_output")
        # print(dumps(graph_output, pretty=True))
        if isinstance(graph_output, BaseSchema):
            print(graph_output.model_dump_json(indent=4))
        else:
            print(json.dumps(graph_output, indent=4))
        print("\n\n\n\n")
        # import ipdb; ipdb.set_trace()
        
        return graph_output

    def execute_graph_stream(
        self,
        graph: Any,
        input_data: Dict[str, Any],
        config: Dict[str, Any],
        output_node_id: str = None,
        interrupt_handler: Callable = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute a LangGraph with input data and stream results.
        
        Args:
            graph (Any): The LangGraph to execute.
            input_data (Dict[str, Any]): Input data for the graph.
            config (Dict[str, Any]): Runtime configuration for execution.
            
        Yields:
            Dict[str, Any]: Streaming outputs from the graph.

        https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/#interrupt
        """
        # TODO: FIXME: MUST TEST NESTED INPUT FIELDS AND DATA!
        input_data = {get_central_state_field_key(k): v for k, v in input_data.items()}
        
        if interrupt_handler is None:
            interrupt_handler = LangGraphRuntimeAdapter.get_value_from_human
        
        # Create a LangGraph config dict
        lg_config = {
            "configurable": config,  # config may have thread_id
            # "metadata": {
            #     "workflow_id": config.get("workflow_id", ""),
            #     "run_id": config.get("run_id", ""),
            #     "user_id": config.get("user_id"),
            #     "configurable": config.get("configurable", {})
            # }
        }
        
        # Add callbacks if provided
        # if "callbacks" in config:
        #     lg_config["callbacks"] = config["callbacks"]
        
        # Execute the graph
        # input_data can be None
        has_interrupts = True
        interrupt_data = None

        print("\n\n\n\n#### INPUT DATA SENT TO GRAPH INVOKE", input_data, "\n\n\n\n")

        # while has_interrupts:
        #     # https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/#interrupt
        #     if interrupt_data:
        #         value_from_human = interrupt_handler(interrupt_data)
        #         result = graph.invoke(Command(resume=value_from_human), config=lg_config)
        #     else:
        #         result = graph.invoke(input_data, config=lg_config)
        #     print("\n\n\n\n#### GRAPH RUN PHASE FINISHED (Interrupted or Final Finished)! result", result, "\n\n\n\n")
        #     last_state = graph.get_state(lg_config)
        #     has_interrupts = False
        #     # final_state.tasks[0].interrupts  # check for keys as set in interrupt pre-processor below!
        #     interrupt_data = None
        #     if last_state.tasks:
        #         for task in last_state.tasks:
        #             if task.interrupts:
        #                 has_interrupts = True
        #                 interrupt_data = task.interrupts[0].value
        #                 break
        
        # Execute the graph with streaming
        while has_interrupts:
            if interrupt_data:
                value_from_human = interrupt_handler(interrupt_data)
                stream = graph.stream(Command(resume=value_from_human), config=lg_config, stream_mode=["updates", "messages"])
            else:
                stream = graph.stream(input_data, config=lg_config, stream_mode=["updates", "messages"])
            has_interrupts = False
            for chunk in stream:
                print("\n\n\n\n", "-"*100, "##### chunk\n", chunk, "\n", "-"*100, "\n\n\n\n")
                update_type, update_data = chunk
                if update_type == "updates" and "__interrupt__" in update_data:
                    interrupt_data = update_data["__interrupt__"][0].value
                    has_interrupts = True
                    print("\n\n\n\n#### INTERRUPT DATA", interrupt_data, "\n\n\n\n")
                    # TODO: FIXME: MUST HANDLE INTERRUPT!
                elif update_type == "messages":
                    print("\n\n\n\n#### MESSAGE DATA", update_data, "\n\n\n\n")
                # import ipdb; ipdb.set_trace()
            # print(chunk)
            # yield chunk
        final_state = graph.get_state(lg_config)
        # final_state.tasks[0].interrupts  # check for keys as set in interrupt pre-processor below!

        graph_output = None
        if output_node_id:
            graph_output = final_state.values.get(get_node_output_state_key(output_node_id), {})
        return graph_output

    async def aexecute_graph_stream(
        self,
        graph: Any,
        input_data: Dict[str, Any],
        config: Dict[str, Any]
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute a LangGraph with input data and stream results.
        
        Args:
            graph (Any): The LangGraph to execute.
            input_data (Dict[str, Any]): Input data for the graph.
            config (Dict[str, Any]): Runtime configuration for execution.
            
        Yields:
            Dict[str, Any]: Streaming outputs from the graph.
        
        https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/#interrupt
        """
        from langchain_core.runnables import RunnableConfig
        
        # Create a LangGraph config dict
        lg_config = {
            "configurable": config,  # config may have thread_id
            # "metadata": {
            #     "workflow_id": config.get("workflow_id", ""),
            #     "run_id": config.get("run_id", ""),
            #     "user_id": config.get("user_id"),
            #     "configurable": config.get("configurable", {})
            # }
        }
        
        # Add callbacks if provided
        # if "callbacks" in config:
        #     lg_config["callbacks"] = config["callbacks"]
        
        # Set up streaming config
        stream_config = dict(lg_config)
        
        # Execute the graph with streaming
        async for chunk in graph.astream(input_data, config=stream_config, stream_mode=["updates", "messages"]):

            import ipdb; ipdb.set_trace()
            print(chunk)
            # yield chunk
