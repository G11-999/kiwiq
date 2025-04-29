import json
from logging import Logger
import re
from typing import Any, Callable, ClassVar, Dict, Generic, Optional, Type, TypeVar, Union, get_type_hints
import inspect
from abc import ABC, abstractmethod

# FIXME: DEBUG: Prefect test!
from prefect import flow, task
from prefect.cache_policies import NO_CACHE

from langgraph.types import Command, Send, Interrupt

from workflow_service.config.constants import NODE_EXECUTION_ORDER_KEY
from workflow_service.registry.schemas.base import BaseSchema
from workflow_service.utils.utils import get_central_state_field_key, is_dynamic_schema_node

from kiwi_app.workflow_app.constants import LaunchStatus

# Define type variables for input, output, and config schemas
InputSchemaT = TypeVar('InputSchemaT', bound=BaseSchema)
OutputSchemaT = TypeVar('OutputSchemaT', bound=BaseSchema)
ConfigSchemaT = TypeVar('ConfigSchemaT', bound=BaseSchema)
StateT = TypeVar('StateT')  # For langgraph state type

from pydantic import BaseModel

from workflow_service.utils.utils import get_node_output_state_key
# from workflow_service.config.constants import GRAPH_STATE_SPECIAL_NODE_NAME, STATE_KEY_DELIMITER

from typing import TYPE_CHECKING # Import ClassVar

# TYPE_CHECKING helps avoid runtime circular dependencies if Task hints itself
if TYPE_CHECKING:
    from prefect.tasks import Task


from global_config.logger import get_prefect_or_regular_python_logger


class BaseNode(BaseModel, Generic[InputSchemaT, OutputSchemaT, ConfigSchemaT], ABC):
    """
    Abstract base class for workflow nodes.
    
    This class provides the foundation for all nodes in a workflow. It defines the interface
    and common functionality that all nodes must implement. Nodes process input data according
    to their configuration and produce output data that can be passed to downstream nodes.
    
    Key Features:
    - Input/Output/Config schema validation
    - Error code registration and handling
    - Custom event emission
    - Environment flagging (staging/experimental/prod)
    - Subnode composition support
    - Version tracking
    
    Attributes:
        input_schema_cls (ClassVar[Type[InputSchemaT]]): Class reference for input schema validation.
        output_schema_cls (ClassVar[Type[OutputSchemaT]]): Class reference for output schema validation.
        config_schema_cls (ClassVar[Type[ConfigSchemaT]]): Class reference for configuration schema validation.
        config (ConfigSchemaT): Configuration parameters for the node.
        node_name (str): Unique identifier for the node type
        node_version (str): Version identifier for this node implementation
        env_flag (str): Environment flag - one of: staging, experimental, production
        error_codes (Dict[str, str]): Mapping of error codes to descriptions
        custom_events (Dict[str, str]): Mapping of custom event types to descriptions
        has_subnodes (bool): Whether this node contains subnodes
    """
    # Node metadata
    node_name: ClassVar[str]  # Required unique identifier
    # node_description: # Comes from the docstring available via `__doc__`!
    node_version: ClassVar[str]  # Required version
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.EXPERIMENTAL  # Default to experimental
    # error_codes: ClassVar[Dict[str, str]] = {}  # Error code registry
    # custom_events: ClassVar[Dict[str, str]] = {}  # Custom event registry
    has_subnodes: ClassVar[bool] = False  # Subnode flag
    
    dynamic_schemas: ClassVar[bool] = False
    node_is_tool: ClassVar[bool] = False
    # Schema class references to be overridden by subclasses
    input_schema_cls: ClassVar[Optional[Type[InputSchemaT]]] = None
    output_schema_cls: ClassVar[Optional[Type[OutputSchemaT]]] = None
    config_schema_cls: ClassVar[Optional[Type[ConfigSchemaT]]] = None

    runtime_postprocessor: ClassVar[Optional[Callable[[Dict[str, Any]], Dict[str, Any]]]] = None
    runtime_preprocessor: ClassVar[Optional[Callable[[Dict[str, Any]], Dict[str, Any]]]] = None
    logger: Optional[Logger] = None

    # FIXME: DEBUG: Prefect test!
    # --- The Fix ---
    # Annotate the task method attribute as ClassVar
    # Optionally, provide a more specific type hint for the Task object itself
    # run: ClassVar['Task[..., str]']

    # Instance configuration
    node_id: str  # Required unique identifier in the context of a graph run
    config: Optional[Union[ConfigSchemaT, Dict[str, Any]]] = None
    # Whether to run the node in Prefect mode for logging and tracking flow/tasks
    prefect_mode: bool = True
    
    # Whether to run the node in private input mode (directly accepting previous node's output)
    #   Useful for map/reduce or branching patterns or maintaining private states
    private_input_mode: bool = False
    private_output_mode: bool = False

    class Config:
        arbitrary_types_allowed = True # Allow non-pydantic types like clients, etc!

    @classmethod
    def __pydantic_init_subclass__(cls, *args, **kwargs):
        """
        Validates schema field definitions during class creation.
        """
        super().__pydantic_init_subclass__(*args, **kwargs)
        # Check if class is abstract by looking for abstract methods
        if cls == BaseNode:
            return  # Skip validation for the base class itself
            
        # Check if class is abstract by looking for abstract methods
        if inspect.isabstract(cls):
            return  # Skip validation for abstract classes
        
        assert cls.node_name is not None and re.match(r"^[a-zA-Z0-9_\. \(\),]+$", cls.node_name), f"Valid characters for node_name are: a-z, A-Z, 0-9, _, ., (, ), , and space!"
        
        # cls.logger = get_prefect_or_regular_python_logger(f"{__name__}.{cls.__name__}")

        if cls.input_schema_cls is None:
            cls.input_schema_cls = None
        if cls.output_schema_cls is None:
            cls.output_schema_cls = None
        if cls.config_schema_cls is None:
            cls.config_schema_cls = None
        if not cls.node_name:
            raise TypeError(f"node_name must be set for {cls.__name__}!")
        if not cls.node_version:
            raise TypeError(f"node_version must be set for {cls.__name__}!")
    
    def __init__(self, allow_non_user_editable_fields_in_config: bool = True, **kwargs):
        super().__init__(**kwargs)
        # classes instantiated with configs during flow run!
        self.logger = get_prefect_or_regular_python_logger(f"{__name__}.{self.node_name}.{self.node_id}")
        if (not allow_non_user_editable_fields_in_config) and (self.__class__.config_schema_cls is not None) and (not inspect.isabstract(self.__class__.config_schema_cls)):
            is_valid, error_field = self.__class__.config_schema_cls.validate_only_user_editable_fields_provided_in_input(kwargs.get("config", {}))
            if not is_valid:
                raise ValueError(f"Invalid non-editable fields in {self.__class__.node_id} --> {self.__class__.node_name} node config: `{error_field}`!")
    
    @abstractmethod
    async def process(self, input_data: InputSchemaT, config: Dict[str, Any], *args: Any, **kwargs: Any) -> OutputSchemaT:
        """
        Process input data and produce output data.
        
        This is the primary execution method that subclasses must implement.
        
        Args:
            input_data (InputSchemaT): Input data conforming to the input schema.
            
        Returns:
            OutputSchemaT: Output data conforming to the output schema.
            
        Raises:
            Exception: If an unregistered error code is encountered
        """
        pass

    # def emit_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
    #     """
    #     Emit a custom event during node execution.
        
    #     Args:
    #         event_type (str): Type of event - must be registered in custom_events
    #         event_data (Dict[str, Any]): Event payload
            
    #     Raises:
    #         ValueError: If event_type is not registered
    #     """
    #     if event_type not in self.custom_events:
    #         raise ValueError(f"Unregistered event type: {event_type}")
    #     # TODO: Implement event emission logic
    #     pass

    def build_input_state(self, state: StateT, config: Dict[str, Any], only_fetch_central_state: bool = False, build_input_schema_obj: bool = True) -> Dict[str, Any]:
        """
        Build the input state for the node.
        """
        # print(f"\n\n\n\n#### build_input_state --  > #############################  {self.node_id} --> {self.node_name}  ###############################\n\n\n\n")
        # print("\n\n\n\n#### build_input_state")
        # print("\n\n\n\n#### state (in build input state)", state, "\n\n\n\n")
        
        # import ipdb; ipdb.set_trace()
        configurable = config.get("configurable", {})
        # print("\n\n\n\n#### configurable (in build input state)", configurable, "\n\n\n\n")  # json.dumps(configurable, indent=4))
        if configurable is None:
            # TODO: raise exceptions in standard ways while maintaining debugability! 
            raise ValueError("No config provided to node!")
        if self.input_schema_cls is None or (not self.input_schema_cls.model_fields):
            return {}
        input_dict = {}
        if self.input_schema_cls.get_required_fields() and (("inputs" not in configurable) or (self.node_id not in configurable["inputs"])):
            raise ValueError("No inputs provided in config for building input state!")
        field_mappings = configurable["inputs"][self.node_id]
        # print("\n\n\n\n#### field_mappings", field_mappings, "\n\n\n\n")
        parents_run_status = {}
        
        node_execution_order = {}
        for idx, node_id in enumerate(state.get(get_central_state_field_key(NODE_EXECUTION_ORDER_KEY), [])):
            node_execution_order[node_id] = max(node_execution_order.get(node_id, 0), idx)

        ordered_field_mappings = {}
        for input_field, state_key in field_mappings.items():
            node_state_keys = []
            central_state_keys = []
            for state_key_instance in state_key:
                if isinstance(state_key_instance, list):
                    node_id = state_key_instance[0]
                    node_state_keys.append((node_execution_order.get(node_id, -1), state_key_instance))
                else:
                    central_state_keys.append(state_key_instance)
            # sort node state keys by execution order (latest executed is first!)
            node_state_keys = sorted(node_state_keys, key = lambda x: x[0], reverse=True)
            # remove idx
            node_state_keys = [x[1] for x in node_state_keys]
            ordered_field_mappings[input_field] = central_state_keys + node_state_keys

        for input_field, state_key in ordered_field_mappings.items():  # field_mappings.items()
            # Get value from state using the mapped state key
            for state_key_instance in state_key:
                if isinstance(state_key_instance, list):
                    if only_fetch_central_state:
                        continue
                
                    # Get value from state using the mapped state key
                    # NOTE: this handles the case when a router node creates multiple fan outs and a subsequent node receives multiple fan ins from router nodes at runtime!
                    state_key_0 = get_node_output_state_key(state_key_instance[0])
                    # TODO: FIXME: BUG: sometimes this is not an object but a dict! probably due to the way langgraph handles state updates!
                    dict_has_key = (isinstance(state.get(state_key_0, None), dict)) and (state_key_instance[1] in state.get(state_key_0, {}))
                    if state_key_0 not in state or ((not hasattr(state[state_key_0], state_key_instance[1])) and (not dict_has_key)):
                        # This could mean the the parent node outputs are uninitialized and this node could be part of a loop!
                        #     This means that the input must be marked as optional!
                        parents_run_status[state_key_instance[0]] = False
                        continue
                        # raise ValueError(f"State key {state_key[0]} not found in state!")
                    
                    # NOTE: the node 2 node key never overrides a previously filled state since it may be filled by a previous node or central state!
                    if dict_has_key:
                        input_received_value = state[state_key_0][state_key_instance[1]]
                    else:
                        input_received_value = getattr(state[state_key_0], state_key_instance[1])
                    parents_run_status[state_key_instance[0]] = True
                    
                    if input_field not in input_dict:
                        input_dict[input_field] = input_received_value
                    # break
                else:
                    # Get value from CENTRAL state using the mapped state key!
                    central_state_key_instance = get_central_state_field_key(state_key_instance)
                    if central_state_key_instance not in state:
                        # This could mean the the parent node outputs are uninitialized and this node could be part of a loop!
                        #     This means that the input must be marked as optional!
                        continue
                        # raise ValueError(f"State key {state_key} not found in state!")
                    input_dict[input_field] = state[central_state_key_instance]
                # break
        # if self.node_id == "review":
        #     import ipdb; ipdb.set_trace()
        # print("\n\n\n\n#### input_dict (in build input state)", input_dict, "\n\n\n\n")
        
        # This generates a weird error in Langgraph!
        # Best to block multiple incoming edges on frontend -> use central state for data passing from multiple edges, use edges as part of a loop or explicitly handled FAN IN!
        # # TODO: FIXME: hack for multiple fan Ins and Loops!
        # for fname, field_info in self.input_schema_cls.model_fields.items():
        #     if fname not in input_dict:
        #         if field_info.is_required() and any(p == False for p in parents_run_status.values()):
        #             print(f"fname: {fname} is required but not found in input_dict: {input_dict}")
        #             return None
        if not build_input_schema_obj:
            return input_dict

        input_obj = self.input_schema_cls(**input_dict)
        # print("\n\n\n\n#### input_dict (in build input state)", input_obj.model_dump_json(indent=4), "\n\n\n\n")
        return input_obj

    def build_output_state_update(self, output_data: OutputSchemaT, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build the state update for the node.
        """
        configurable = config.get("configurable", {})
        state_update = {}
        output_schema = self.__class__.output_schema_cls
        if output_schema and isinstance(output_data, output_schema):
            # We will let node outputs be outputed even in private input mode for debugging purpsoes by adding collect values reducer for node output keys!
            if not self.private_input_mode:
                state_update = {get_node_output_state_key(self.node_id): output_data}
        
            # Ensure that this node is configured to send outputs to the global central state
            #     And it has a set output schema and the generated output is actually an instance of the schema object
            #     The latter helps avoiding issues like when output is actually interrupts in HITL node, etc!
            if isinstance(state_update, dict) and configurable.get("outputs", None) and configurable["outputs"].get(self.node_id, None):
                # This pushes output to global central state if configured to do so!
                # TODO: check if output field name is valid!
                central_state_output_field_mapping = configurable["outputs"].get(self.node_id, {})
                central_state_output = {}
                for output_field_name, central_state_field_name in central_state_output_field_mapping.items():
                    central_state_output_field_name = get_central_state_field_key(central_state_field_name)
                    central_state_output[central_state_output_field_name] = getattr(output_data, output_field_name)
                state_update.update(central_state_output)
        else:
            # NOTE: may wanna copy this potentially!
            state_update = output_data if output_data else state_update

        # Add node execution order to state update
        state_update[get_central_state_field_key(NODE_EXECUTION_ORDER_KEY)] = [self.node_id]

        return state_update
    
    # def _prepare_input_data(self, input_data: Union[InputSchemaT, Dict[str, Any]], config: Dict[str, Any]) -> InputSchemaT:
    #     """
    #     Prepare the input data for the node.
    #     """
    #     return self.input_schema_cls(**input_data) if isinstance(input_data, dict) else input_data

    # FIXME: DEBUG: Prefect test!
    # @task
    async def run(self, state: StateT, config: Dict[str, Any], *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """
        LangGraph-compatible execution method.
        
        This method adapts the node's processing logic to be compatible with LangGraph's
        execution model. It extracts input data from the state, processes it, and returns
        the updated state.
        
        Args:
            state (StateT): The current state of the workflow graph. This is a TypedDict.
            config (Dict[str, Any]): Runtime configuration overrides.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.
            
        Returns:
            Dict[str, Any]: The updated state after processing.
            
        Raises:
            Exception: For any unregistered error codes encountered during processing
        """
        
        try:
            # print("\n\n\n\n NODE ENTRY: ", "="*100, "\n\n\n\n")
            # print("\n\n\n\n#### RUN ", self.node_id, " --> ", self.node_name, "\n\n\n\n")
            # print("\n\n\n\n#### state (in run) START!", state, "\n\n\n\n")
            # Extract input data from state based on runtime config mapping
            # config format: - {"inputs": node_id: {<input_field_key> : ["source_node", "field_key_in_source_node"] | OR | graph_state_key_source_of_input }}
            if self.private_input_mode:
                # fetch central state inputs!
                input_data_dict = self.build_input_state(state, config, only_fetch_central_state=True, build_input_schema_obj=False)
                # assume the received input is entire input!
                #   for conflicting keys, overwrite central state values with private values!
                input_data_dict.update(state)
                # TODO: Potentially use model_validate(...)?
                input_data = input_data_dict
                # NOTE: TODO: FIXME: We don't initialize the input schema in private input mode! Be careful and handle this behaviour more gracefully!
                #     This is mainly the case due to dynamic schemas and missing field types leading to empty input schema cls!
                # input_data = self.input_schema_cls(**input_data_dict)
            else:
                input_data = self.build_input_state(state, config)
            if input_data is None:
                # print("\n\n\n\n NODE EARLY EXIT -> REQUIRED NOT FULFILLED!!!!!: ", "="*100, "\n\n\n\n")
                # TODO: FIXME:
                # This is exceptional case when not all required fields were found in input!
                #     It could either be a bug or the node is prematurely called due to FAN IN bug!
                # We will exit the node without running the node since required field is missing 
                #     and hope this node is re-executed when all parents are run and requried field is found in input!
                return {}
            # print("\n\n\n\n#### self.node_id", self.node_id)
            # print("input_data", input_data)
            
            # # Apply runtime config overrides if provided
            # effective_config = self.config
            # if config:
            #     config_dict = self.config.model_dump()
            #     config_dict.update(config)
            #     effective_config = self.config_schema_cls.model_validate(config_dict)

            # print("\n\n\n\n#### input_data (in run)", input_data, "\n\n\n\n")
            if self.__class__.runtime_preprocessor:
                # Generally used for interupts to get HITL!
                # print("\n\n\n\n#### self.__class__.runtime_preprocessor (in run)", "\n\n\n\n")
                preprocessed_input_data = self.__class__.runtime_preprocessor(self, input_data, config, *args, **kwargs)
                input_data = preprocessed_input_data
            
            ###### Test SENDING COMPLEX OBJECTS inputs to prefect!
            # from workflow_service.registry.registry import DBRegistry
            # from kiwi_app.workflow_app.crud import NodeTemplateDAO, SchemaTemplateDAO, PromptTemplateDAO, WorkflowDAO
            # node_template_dao = NodeTemplateDAO()
            # schema_template_dao = SchemaTemplateDAO()
            # prompt_template_dao = PromptTemplateDAO()
            # workflow_dao = WorkflowDAO()
            # db_registry = DBRegistry(node_template_dao, schema_template_dao, prompt_template_dao, workflow_dao)
            # from db.session import get_async_session
            # async_session = get_async_session()

            # obj = {
            #     "db_registry": db_registry,
            #     "async_session": async_session,
            # }
            # , db_obj=obj
            ######

            # Process the input data
            if self.prefect_mode:
                output_data = await task(name=f"Node Name: `{self.node_name}` - Node ID: `{self.node_id}`", cache_policy=NO_CACHE)(self.process)(input_data, config, *args, **kwargs)
            else:
                output_data = await self.process(input_data, config, *args, **kwargs)
            # print("\n\n\n\n#### output_data (in run)", output_data, "\n\n\n\n")
            
            # Convert output to dict and return as state update
            # NOTE: in case a Command / Send is generated in the process(...) method, this method to build state update should be called from there directly since otehrwise
            #       the Command / Send will not make it to langgraph and state will be built with atleast the node order update!
            #       Also if the Command / Send don't include the central state update, the node order won't be captured!
            if isinstance(output_data, (Command, Send, Interrupt)):
                state_update = output_data
            else:
                state_update = self.build_output_state_update(output_data, config)
            # print(f"\n\n\n\n#### state_update (in run) --> {state_update.__class__}", state_update, "\n\n\n\n")
            # if self.node_id == "join":
            #     import ipdb; ipdb.set_trace()
            # import ipdb; ipdb.set_trace()

            state_update = state_update if state_update else output_data   # state_update could be None if no output schema defined but output_data may be a runtime command / interupt!

            if self.__class__.runtime_postprocessor and (not isinstance(state_update, (Command, Send, Interrupt))) and (not isinstance(output_data, (Command, Send, Interrupt))):
                state_update = self.__class__.runtime_postprocessor(self, state_update, config, *args, **kwargs)
            
            if (isinstance(output_data, dict) or isinstance(output_data, BaseSchema)) and (not isinstance(state_update, (Command, Send, Interrupt))) and (not isinstance(output_data, (Command, Send, Interrupt))):
                # assume this is standard state_update and not Command / Send / Interrupts for eg
                configurable = config.get("configurable", {})
                if self.private_output_mode:
                    # update central state with private output!
                    output_to_nodes = {}
                    for out_node_id, out_node_edge in configurable.get("outgoing_edges", {}).get(self.node_id, {}).items():
                        output_to_node = {}
                        for mapping in out_node_edge.mappings:
                            # Get source field value from state_update, handling both dict and BaseSchema objects
                            if isinstance(output_data, dict):
                                src_value = output_data.get(mapping.src_field, None)
                            else:  # BaseSchema
                                src_value = getattr(output_data, mapping.src_field, None)
                            
                            # Set the destination field in output_data
                            if src_value is not None:
                                output_to_node[mapping.dst_field] = src_value
                        output_to_nodes[out_node_id] = output_to_node
                    # Ignore any other state update apart from a dictionary, potentialy ignore Command / Send / Interrupt!
                    state_update = state_update if isinstance(state_update, dict) else None
                    # TODO: langgraph dependency!
                    response = Command(goto=[Send(node_id, node_input) for node_id, node_input in output_to_nodes.items()], update=state_update, )
                    return response

            # print("\n\n\n\n#### state_update (in run)", state_update, "\n\n\n\n")
            # print("\n\n\n\n NODE EXIT: ", "="*100, "\n\n\n\n")
            return state_update
        except Exception as e:
            # TODO: raise custom error codes which are registered!
            raise e
        # except Exception as e:
        #     # Check if error code is registered
        #     error_code = getattr(e, 'code', str(type(e).__name__))
        #     if error_code not in self.error_codes:
        #         # Unregistered errors should trigger alerts
        #         # TODO: Implement alert mechanism
        #         raise
        #     raise  # Re-raise the original error
        # pass
    def set_run_annotations(
        self,
        state_type: Type[Any],
        config_type: Optional[Type[Any]] = None,
        return_type: Optional[Type[Any]] = None
    ) -> None:
        """
        Updates the run method's type annotations directly on the instance.

        This method modifies the run method's type hints to use specific types for state and config parameters.
        This is useful when integrating with systems that rely on type annotations for validation.

        Args:
            state_type (Type[Any]): The type to use for the state parameter.
            config_type (Optional[Type[Any]]): The type to use for the config parameter.
                Defaults to Dict[str, Any] if not provided.

        Note:
            This modifies the instance's run method annotations directly, rather than creating a new method.
            The actual implementation remains unchanged - only the type hints are updated.
        """
        if config_type is None:
            config_type = Dict[str, Any]
        if return_type is None:
            return_type = Dict[str, Any]

        # Update the run method's annotations directly
        self.run.__func__.__annotations__ = {
            'state': state_type,
            'config': Optional[config_type],
            'return': return_type
        }
    
    @classmethod
    def with_typed_signature(
        cls, 
        state_type: Type[Any], 
        config_type: Optional[Type[Any]] = None
    ) -> Callable[[StateT, Optional[Dict[str, Any]], Any, Any], Dict[str, Any]]:
        """
        Create a version of the run method with specific type annotations.

        This helper method allows for more precise type hints when integrating with
        LangGraph or other systems that rely on type annotations for validation.

        Args:
            state_type (Type[Any]): The type to use for the state parameter.
            config_type (Optional[Type[Any]]): The type to use for the config parameter.
                
        Returns:
            Callable: A function with the same behavior as run but with updated type annotations.
        """
        if config_type is None:
            config_type = Dict[str, Any]
        
        # Create a new function with the same implementation but different annotations
        def typed_run(
            self, 
            state: state_type, 
            config: Optional[config_type] = None, 
            *args: Any, 
            **kwargs: Any
        ) -> Dict[str, Any]:
            return cls.run(self, state, config, *args, **kwargs)
        
        # Update the function's signature to reflect the new types
        typed_run.__annotations__ = {
            'state': state_type,
            'config': Optional[config_type],
            'return': Dict[str, Any]
        }
        
        return typed_run
    
    @classmethod
    def dump_node_signature(cls) -> Dict[str, Any]:
        """
        Dumps the node's signature including name, version and schemas.

        Returns:
            Dict[str, Any]: Dictionary containing:
                - node_name: Name of the node class
                - version: Version of the node (if defined)
                - input_schema: Schema for input (None if not defined) 
                - output_schema: Schema for output (None if not defined)
                - config_schema: Schema for config (None if not defined)
        """
        # Get generic type args for input/output/config schemas
        
        # Extract schemas, defaulting to None if not specified

        signature = {
            "node_name": cls.node_name,
            "version": cls.node_version,
            "input_schema": cls.input_schema_cls.get_schema_for_db() if cls.input_schema_cls else None,
            "output_schema": cls.output_schema_cls.get_schema_for_db() if cls.output_schema_cls else None,
            "config_schema": cls.config_schema_cls.get_schema_for_db() if cls.config_schema_cls else None,
            "input_schema_is_dynamic": is_dynamic_schema_node(cls.input_schema_cls),
            "output_schema_is_dynamic": is_dynamic_schema_node(cls.output_schema_cls),
            "config_schema_is_dynamic": is_dynamic_schema_node(cls.config_schema_cls),
        }
        
        return signature

    @classmethod
    def diff_from_provided_signature(cls, provided_signature: Dict[str, Any], self_is_base_for_diff:bool = False) -> Dict[str, Any]:
        """
        Compare current node signature against a provided signature and return differences.
        Uses BaseSchema diff for schema comparisons.

        Args:
            provided_signature (Dict[str, Any]): Node signature to compare against

        Returns:
            Dict[str, Any]: Dictionary containing:
                - version_changed: True if version differs
                - schema_diffs: Dict containing diffs for each schema type:
                    - input_schema: Diff results if input schema changed
                    - output_schema: Diff results if output schema changed  
                    - config_schema: Diff results if config schema changed
        """
        # current_sig = cls.dump_node_signature()
        
        # Name changed
        # NOTE: This should not happen!
        name_changed = cls.node_name != provided_signature.get("node_name")

        # Compare versions
        version_changed = cls.node_version != provided_signature.get("version")
        
        # Compare schemas
        signature_schema_types = ["input_schema", "output_schema", "config_schema"]
        current_schema_types = [cls.input_schema_cls, cls.output_schema_cls, cls.config_schema_cls]

        diff = {
            "name_changed": name_changed,
            "version_changed": version_changed,
            "schema_added": [],
            "schema_removed": [],
            "schema_diffs": {},
            "dynamic_schema_changes": {},
        }
        if self_is_base_for_diff:
            current_added_key = "schema_removed"
            provided_added_key = "schema_added"
            provided_dynamic_change_key = "changed_to_dynamic"
            current_dynamic_change_key = "changed_to_static"
        else:
            current_added_key = "schema_added"
            provided_added_key = "schema_removed"
            provided_dynamic_change_key = "changed_to_static"
            current_dynamic_change_key = "changed_to_dynamic"
        for schema_type, current_schema_cls in zip(signature_schema_types, current_schema_types):
            provided_schema = provided_signature.get(schema_type)
            
            # Skip if both schemas are None
            if current_schema_cls is None and provided_schema is None:
                continue
                
            # Record change if one schema is None and other isn't
            if current_schema_cls is None or provided_schema is None:
                if current_schema_cls is not None:
                    diff[current_added_key].append(schema_type)
                else:
                    diff[provided_added_key].append(schema_type)
                continue
            
            # Check for dynamic schema changes
            dynamic_schema_key = f"{schema_type}_is_dynamic"
            current_is_dynamic = is_dynamic_schema_node(current_schema_cls)
            provided_is_dynamic = provided_signature.get(dynamic_schema_key, False)
            
            if current_is_dynamic != provided_is_dynamic:
                diff["dynamic_schema_changes"][schema_type] = {
                    provided_dynamic_change_key: provided_is_dynamic,
                    current_dynamic_change_key: current_is_dynamic
                }
            
            if current_schema_cls is not None:
                # Use BaseSchema diff to compare schemas
                diff["schema_diffs"][schema_type] = current_schema_cls.diff_from_provided_schema(provided_schema, self_is_base_for_diff=self_is_base_for_diff)
        return diff

    # Logger convenience methods
    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """
        Log a debug message through the node's logger.
        
        Args:
            msg: The message to log
            *args: Additional positional arguments for the logger
            **kwargs: Additional keyword arguments for the logger
        """
        if self.logger:
            self.logger.debug(msg, *args, **kwargs)
    
    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """
        Log an info message through the node's logger.
        
        Args:
            msg: The message to log
            *args: Additional positional arguments for the logger
            **kwargs: Additional keyword arguments for the logger
        """
        if self.logger:
            self.logger.info(msg, *args, **kwargs)
    
    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """
        Log a warning message through the node's logger.
        
        Args:
            msg: The message to log
            *args: Additional positional arguments for the logger
            **kwargs: Additional keyword arguments for the logger
        """
        if self.logger:
            self.logger.warning(msg, *args, **kwargs)
    
    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """
        Log an error message through the node's logger.
        
        Args:
            msg: The message to log
            *args: Additional positional arguments for the logger
            **kwargs: Additional keyword arguments for the logger
        """
        if self.logger:
            self.logger.error(msg, *args, **kwargs)
    
    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """
        Log a critical message through the node's logger.
        
        Args:
            msg: The message to log
            *args: Additional positional arguments for the logger
            **kwargs: Additional keyword arguments for the logger
        """
        if self.logger:
            self.logger.critical(msg, *args, **kwargs)
