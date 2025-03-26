"""
Dynamic input and output nodes for workflows.

This module contains the implementation of dynamic input and output nodes,
which serve as the entry and exit points for workflows. Their schemas are
dynamically created based on the graph connections.
"""
from typing import Any, Dict, List, Optional, Type, ClassVar, cast, Callable, Union, get_origin, get_args
from pydantic import Field, create_model, field_validator
from datetime import datetime, date
from enum import Enum

from workflow_service.registry.schemas.base import BaseSchema
from workflow_service.registry.nodes.core.base import BaseNode
from workflow_service.config.constants import INPUT_NODE_NAME, OUTPUT_NODE_NAME, HITL_NODE_NAME_PREFIX, TEMP_STATE_UPDATE_KEY, ROUTER_CHOICE_KEY
from global_config.constants import EnvFlag
from abc import ABC, abstractmethod


class DynamicSchema(BaseSchema, ABC):
    """
    A dynamic schema that can be created at runtime.
    
    This is a placeholder class that will be replaced with dynamically
    created schemas based on the graph connections.
    """
    IS_DYNAMIC_SCHEMA: ClassVar[bool] = True


ALLOWED_FIELD_TYPES: Dict[str, Type] = {
        "str": str,
        "int": int, 
        "float": float,
        "bool": bool,
        "bytes": bytes,
        "datetime": datetime,
        "date": date
}

DEFAULT_NOT_SPECIFIED_VALUE = "@@@NOT_SPECIFIED_VALUE@@@"

class DynamicSchemaFieldConfig(BaseSchema):
    """
    A configuration for a field in a dynamic schema.
    """
    TYPE_MAPPING: ClassVar[Dict[str, Type]] = ALLOWED_FIELD_TYPES

    type: str = Field(..., description="The type of the field")
    required: Optional[bool] = Field(None, description="Whether the field is required")
    default: Optional[Union[str, int, float, bool, bytes, datetime, date]] = Field(DEFAULT_NOT_SPECIFIED_VALUE, description="The default value of the field, only specified if type is primitive, not list / dict.")
    description: Optional[str] = Field(None, description="The description of the field")
    items_type: Optional[str] = Field(None, description="The type of the items in a list field")
    keys_type: Optional[str] = Field(None, description="The type of the keys in a dict field")
    values_type: Optional[str] = Field(None, description="The type of the values in a dict field")
    values_items_type: Optional[str] = Field(None, description="The type of the items in a list field")
    # Enum support
    enum_values: Optional[List[Union[str, int, float, bool, bytes, datetime, date]]] = Field(None, description="List of allowed values for an enum field")
    multi_select: Optional[bool] = Field(False, description="Whether multiple values can be selected from the enum (creates a List[Enum] type)")


class ConstructDynamicSchema(BaseSchema):
    """
    A schema for constructing a dynamic schema from a JSON configuration.
    
    This class allows building dynamic schemas with fields of primitive types,
    as well as non-nested List and Dict types. The field configurations are specified
    using DynamicSchemaFieldConfig objects, which define properties like type, default values,
    and whether fields are required or optional.
    
    Example:
    ```python
    schema_config = ConstructDynamicSchema(fields={
        "name": DynamicSchemaFieldConfig(type="str", required=True),
        "age": DynamicSchemaFieldConfig(type="int", default=0),
        "tags": DynamicSchemaFieldConfig(type="list", items_type="str"),
        "metadata": DynamicSchemaFieldConfig(type="dict", keys_type="str", values_type="int"),
        "user_lists": DynamicSchemaFieldConfig(
            type="dict", 
            keys_type="str", 
            values_type="list", 
            values_items_type="str"
        )
    })
    ```
    """
    fields: Dict[str, DynamicSchemaFieldConfig] = Field(
        ...,
        description="Dictionary of field definitions. Keys are field names, values are field configurations."
    )
    
    # Type mapping from string representation to actual Python types
    
    
    @field_validator('fields')
    def validate_fields(cls, field_defs: Dict[str, DynamicSchemaFieldConfig]) -> Dict[str, DynamicSchemaFieldConfig]:
        """
        Validate that the field definitions are properly structured.
        
        Args:
            field_defs: Dictionary of field definitions
            
        Returns:
            The validated field definitions
            
        Raises:
            ValueError: If field definitions are invalid
        """
        for field_name, field_def in field_defs.items():
            # Every field must have a type
            field_type = field_def.type
            
            # Validate enum type
            if field_type == "enum":
                if not field_def.enum_values:
                    raise ValueError(f"Enum field '{field_name}' is missing 'enum_values' property")
                
                if not all(isinstance(val, tuple(DynamicSchemaFieldConfig.TYPE_MAPPING.values())) for val in field_def.enum_values):
                    raise ValueError(f"Enum values in field '{field_name}' must be of primitive types: {list(DynamicSchemaFieldConfig.TYPE_MAPPING.keys())}")
                
                # Check for duplicate values
                if len(field_def.enum_values) != len(set(str(val) for val in field_def.enum_values)):
                    raise ValueError(f"Enum field '{field_name}' contains duplicate values")
                
                continue
                
            # Validate primitive types
            elif field_type in DynamicSchemaFieldConfig.TYPE_MAPPING:
                continue
                
            # Validate list type
            elif field_type == "list":
                if not field_def.items_type:
                    raise ValueError(f"List field '{field_name}' is missing 'items_type' property")
                    
                items_type = field_def.items_type
                if items_type not in DynamicSchemaFieldConfig.TYPE_MAPPING:
                    raise ValueError(f"Invalid items_type '{items_type}' for list field '{field_name}'. Must be a primitive type.")
                
            # Validate dict type
            elif field_type == "dict":
                if not field_def.keys_type:
                    raise ValueError(f"Dict field '{field_name}' is missing 'keys_type' property")
                if not field_def.values_type:
                    raise ValueError(f"Dict field '{field_name}' is missing 'values_type' property")
                    
                keys_type = field_def.keys_type
                if keys_type not in DynamicSchemaFieldConfig.TYPE_MAPPING:
                    raise ValueError(f"Invalid keys_type '{keys_type}' for dict field '{field_name}'. Must be a primitive type.")
                    
                values_type = field_def.values_type
                
                # Values can be primitive types
                if values_type in DynamicSchemaFieldConfig.TYPE_MAPPING:
                    continue
                    
                # Or values can be lists of primitives
                elif values_type == "list":
                    if not field_def.values_items_type:
                        raise ValueError(f"Dict field '{field_name}' with values_type 'list' is missing 'values_items_type' property")
                        
                    values_items_type = field_def.values_items_type
                    if values_items_type not in DynamicSchemaFieldConfig.TYPE_MAPPING:
                        raise ValueError(f"Invalid values_items_type '{values_items_type}' for dict field '{field_name}'. Must be a primitive type.")
                else:
                    raise ValueError(f"Invalid values_type '{values_type}' for dict field '{field_name}'. Must be a primitive type or 'list'.")
            else:
                raise ValueError(f"Invalid field type '{field_type}' for field '{field_name}'. Must be one of {list(DynamicSchemaFieldConfig.TYPE_MAPPING.keys()) + ['list', 'dict', 'enum']}")
                
        return field_defs
    
    def build_schema(self, schema_name: str = "DynamicSchema") -> Type[BaseSchema]:
        """
        Build a dynamic schema from the configuration.
        
        Args:
            schema_name: Name for the created schema class
            
        Returns:
            Type[BaseSchema]: A new BaseSchema subclass with the defined fields
        """
        field_definitions = {}
        created_enums = {}
        
        for field_name, field_def in self.fields.items():
            field_type = field_def.type
            required = field_def.required if field_def.required is not None else True
            default = field_def.default
            if not required:
                if default == DEFAULT_NOT_SPECIFIED_VALUE:
                    default = None
            description = field_def.description or f"Field {field_name}"
            
            # Create the appropriate field type
            if field_type == "enum":
                # Create a dynamic enum type if not already created
                enum_name = f"{schema_name}_{field_name}_Enum"
                if enum_name not in created_enums:
                    # Create an enum with string keys and the actual values
                    enum_dict = {f"VALUE_{i}": val for i, val in enumerate(field_def.enum_values)}
                    
                    # Create the enum class
                    created_enums[enum_name] = Enum(enum_name, enum_dict)
                
                enum_class = created_enums[enum_name]
                
                # Check if this is a multi-select enum
                multi_select = field_def.multi_select or False
                
                if multi_select:
                    # Multi-select enum - creates a List[Enum] type
                    python_type = List[enum_class]
                    
                else:
                    # Single-select enum
                    python_type = enum_class
                # Convert default values to enum members if provided
                kwargs = {"default": default} if not required else {}
                if default != DEFAULT_NOT_SPECIFIED_VALUE and default is not None:
                    kwargs["default"] = default
                else:
                    if multi_select:
                        kwargs["default"] = []
                
                field_definitions[field_name] = (
                    Optional[python_type] if not required else python_type,
                    Field(description=description, **kwargs)
                )
                
            elif field_type in DynamicSchemaFieldConfig.TYPE_MAPPING:
                # Primitive type
                python_type = DynamicSchemaFieldConfig.TYPE_MAPPING[field_type]
                kwargs = {}
                if default != DEFAULT_NOT_SPECIFIED_VALUE:
                    kwargs["default"] = default
                field_definitions[field_name] = (
                    Optional[python_type] if not required else python_type,
                    Field(description=description, **kwargs)
                )
                
            elif field_type == "list":
                # List type
                items_type = field_def.items_type
                python_type = List[DynamicSchemaFieldConfig.TYPE_MAPPING[items_type]]
                kwargs = {}
                if default != DEFAULT_NOT_SPECIFIED_VALUE:
                    kwargs["default"] = default or []
                field_definitions[field_name] = (
                    Optional[python_type] if not required else python_type,
                    Field( description=description, **kwargs)
                )
                
            elif field_type == "dict":
                # Dict type
                keys_type = field_def.keys_type
                values_type = field_def.values_type
                
                if values_type in DynamicSchemaFieldConfig.TYPE_MAPPING:
                    # Dict with primitive values
                    python_type = Dict[DynamicSchemaFieldConfig.TYPE_MAPPING[keys_type], DynamicSchemaFieldConfig.TYPE_MAPPING[values_type]]
                elif values_type == "list":
                    # Dict with list values
                    values_items_type = field_def.values_items_type
                    python_type = Dict[
                        DynamicSchemaFieldConfig.TYPE_MAPPING[keys_type], 
                        List[DynamicSchemaFieldConfig.TYPE_MAPPING[values_items_type]]
                    ]
                kwargs = {}
                if default != DEFAULT_NOT_SPECIFIED_VALUE:
                    kwargs["default"] = default or {}
                field_definitions[field_name] = (
                    Optional[python_type] if not required else python_type,
                    Field(description=description, **kwargs)
                )
        
        # Create and return the dynamic schema class
        return create_model(
            schema_name,
            __base__=DynamicSchema,
            **field_definitions
        )


class BaseDynamicNode(BaseNode[DynamicSchema, DynamicSchema, DynamicSchema], ABC):
    """
    Base class for dynamic nodes.
    """
    # TODO: test if langgraph allows these nodes to not generate any output or have empty schemas, in case where
    #    there's no input / output data but still need these nodes for dependency edges to starter nodes!
    
    dynamic_schemas: ClassVar[bool] = True
    # Schema classes will be dynamically created at runtime
    input_schema_cls: ClassVar[Type[DynamicSchema]] = DynamicSchema
    output_schema_cls: ClassVar[Type[DynamicSchema]] = DynamicSchema
    config_schema_cls: ClassVar[Type[DynamicSchema]] = DynamicSchema

    @classmethod
    def create_node_with_input_output_schemas(
        cls, 
        input_fields: Optional[Dict[str, Any]] = None,
        output_fields: Optional[Dict[str, Any]] = None,
        config_fields: Optional[Dict[str, Any]] = None
    ) -> Type['BaseDynamicNode']:
        """
        Create a new BaseDynamicNode with dynamically created schemas.
        
        Args:
            input_fields (Optional[Dict[str, Any]]): Optional mapping of field names to field definitions
                                          for the input schema.
            output_fields (Optional[Dict[str, Any]]): Optional mapping of field names 
                                                     to field definitions for the output schema.
                                                     If None, uses same schema as input.
            config_fields (Optional[Dict[str, Any]]): Optional mapping of field names 
                                                     to field definitions for the config schema.
            NOTE: atleaset one of them should be provided!

        Returns:
            Type[BaseDynamicNode]: A new BaseDynamicNode class with dynamic schemas.
        """
        assert (input_fields is not None) or (output_fields is not None), "Atleast one of input_fields or output_fields should be provided!"
        
        # if input_fields is None:
        #     input_fields = output_fields
        #     output_fields = None

        class_name = f"Dynamic{cls.__name__}"
        node_kwargs = {}

        # Create dynamic output schema (same as input if not specified)
        if output_fields is None and input_fields is not None:
            output_fields = input_fields
            # node_kwargs['output_schema_cls'] = node_kwargs['input_schema_cls']
        elif output_fields is not None and input_fields is None:
            input_fields = output_fields
            # node_kwargs['input_schema_cls'] = node_kwargs['output_schema_cls']
        
        if input_fields:
            # Create dynamic input schema
            dynamic_input_schema = create_model(
                class_name + "InputSchema",
                # NOTE: this allows field inheritance from set DynamicSchema subclasses!
                __base__=cls.input_schema_cls if cls.input_schema_cls is not None else DynamicSchema,
                **input_fields
            )
            node_kwargs['input_schema_cls'] = dynamic_input_schema
        
        if output_fields:
            # Create dynamic input schema
            dynamic_output_schema = create_model(
                class_name + "OutputSchema",
                __base__=cls.output_schema_cls if cls.output_schema_cls is not None else DynamicSchema,
                **output_fields
            )
            node_kwargs['output_schema_cls'] = dynamic_output_schema
        
        # Create dynamic config schema
        if config_fields:
            dynamic_config_schema = create_model(
                class_name + "ConfigSchema",
                __base__=cls.config_schema_cls if cls.config_schema_cls is not None else DynamicSchema,
                **config_fields
            )
            node_kwargs['config_schema_cls'] = dynamic_config_schema
        
        # check which schemas are marked dyanamic and only overwrite those schemas!
        if not (hasattr(cls.input_schema_cls, 'IS_DYNAMIC_SCHEMA') and 
            getattr(cls.input_schema_cls, 'IS_DYNAMIC_SCHEMA', False)):
            if 'input_schema_cls' in node_kwargs:
                del node_kwargs['input_schema_cls']
        if not (hasattr(cls.output_schema_cls, 'IS_DYNAMIC_SCHEMA') and 
            getattr(cls.output_schema_cls, 'IS_DYNAMIC_SCHEMA', False)):
            if 'output_schema_cls' in node_kwargs:
                del node_kwargs['output_schema_cls']
        if not (hasattr(cls.config_schema_cls, 'IS_DYNAMIC_SCHEMA') and 
            getattr(cls.config_schema_cls, 'IS_DYNAMIC_SCHEMA', False)):
            if 'config_schema_cls' in node_kwargs:
                del node_kwargs['config_schema_cls']

        # Create a new class with these schemas
        new_node_class = create_model(
            class_name,
            __base__=cls,
            __module__=cls.__module__,
            **node_kwargs
        )
        
        return new_node_class


class InputNode(BaseDynamicNode):
    """
    Dynamic input node for workflows.
    
    The input node serves as the entry point for a workflow, collecting initial data
    from the user or system. Its schema is dynamically created based on the fields
    required by downstream nodes connected to it.
    
    Features:
    - Dynamic schema creation based on graph connections
    - Input validation according to the dynamic schema
    - Pass-through of validated input data to the workflow
    """
    # TODO: test if langgraph allows these nodes to not generate any output or have empty schemas, in case where
    #    there's no input / output data but still need these nodes for dependency edges to starter nodes!
    node_name: ClassVar[str] = INPUT_NODE_NAME
    node_version: ClassVar[str] = "0.1.0"
    env_flag: ClassVar[str] = EnvFlag.PROD
    
    # Schema classes will be dynamically created at runtime
    # input_schema_cls = DynamicSchema
    # output_schema_cls = DynamicSchema
    config_schema_cls = None
    
    def process(self, input_data: DynamicSchema, config: Dict[str, Any], *args: Any, **kwargs: Any) -> DynamicSchema:
        """
        Process the input data.
        
        For the input node, this simply passes through the validated input data.
        
        Args:
            input_data (DynamicSchema): The input data from the user or system.
            
        Returns:
            DynamicSchema: The same input data, now validated.
        
        # TODO: check if it accepts raw dict as input, basically serialized inputs or pydantic instantiated model fields??
        """
        # Simply pass through the validated input data
        if input_data:
            return self.__class__.output_schema_cls(**input_data.model_dump()) if self.__class__.output_schema_cls is not None else input_data
        return self.__class__.output_schema_cls() if self.__class__.output_schema_cls is not None else input_data

    # NOTE: input node can just have input configs with source input keys as flat and not list!
    # def run(self, input_data: DynamicSchema) -> DynamicSchema:
    #     """
    #     LangGraph-compatible execution method.
    #     """
    #     # Simply pass through the validated input data
    #     return self.process(input_data)

    # def set_run_annotations(
    #     self, 
    #     input_state: Type[Any]
    # ) -> None:
    #     """
    #     Set the run method's type annotations.
    #     """
    #     self.run.__annotations__ = {
    #         'input_state': input_state,
    #         'return': Dict[str, Any]
    #     }
        
    # def with_typed_signature(
    #     self, 
    #     input_state: Type[Any]
    # ) -> Callable[[Dict[str, Any]], Dict[str, DynamicSchema]]:
    #     """
    #     Create a version of the run method with specific type annotations.

    #     This helper method allows for more precise type hints when integrating with
    #     LangGraph or other systems that rely on type annotations for validation.

    #     Args:
    #         input_state (Type[Any]): The type to use for the input state parameter.
                
    #     Returns:
    #         Callable: A function with the same behavior as run but with updated type annotations.
        
    #     # TODO: can't the input state just be input_schema_cls? diff btw supplying pydantic model vs dict as input in langgraph?

    #     """
        
    #     # Create a new function with the same implementation but different annotations
    #     def typed_run(
    #         state: input_state, 
    #     ) -> Dict[str, DynamicSchema]:
    #         return self.run(state)
        
    #     # Update the function's signature to reflect the new types
    #     # typed_run.__annotations__ = {
    #     #     'state': input_state,
    #     #     'return': Dict[str, Any]
    #     # }
        
    #     return typed_run
    
    # @classmethod
    # def create_node(cls, output_fields: Dict[str, Any]) -> Type['InputNode']:
    #     """
    #     Create a new InputNode with dynamically created schemas.
        
    #     Args:
    #         output_fields (Dict[str, Any]): Mapping of field names to field definitions
    #                                        for the output schema.
                                           
    #     Returns:
    #         Type[InputNode]: A new InputNode class with dynamic schemas.
    #     """
    #     # Create dynamic schemas
    #     dynamic_input_schema = create_model(
    #         'DynamicInputSchema',
    #         __base__=BaseSchema,
    #         **output_fields
    #     )
        
    #     # Output schema is the same as input for the input node
    #     dynamic_output_schema = dynamic_input_schema
        
    #     # Create empty config schema
    #     dynamic_config_schema = create_model(
    #         'DynamicConfigSchema',
    #         __base__=BaseSchema
    #     )
        
    #     # Create a new class with these schemas
    #     new_node_class = create_model(
    #         f"Dynamic{cls.__name__}",
    #         __base__=cls,
    #         __module__=cls.__module__,
    #         input_schema_cls=dynamic_input_schema,
    #         output_schema_cls=dynamic_output_schema,
    #         # config_schema_cls=dynamic_config_schema
    #     )
    #     # new_node_class = cast(Type[InputNode], ModelMetaclass(
    #     #     'DynamicInputNode',
    #     #     (InputNode,),
    #     #     {
    #     #         'input_schema_cls': dynamic_input_schema,
    #     #         'output_schema_cls': dynamic_output_schema,
    #     #         'config_schema_cls': dynamic_config_schema,
    #     #     }
    #     # ))
        
    #     return new_node_class


class OutputNode(BaseDynamicNode):
    """
    Dynamic output node for workflows.
    
    The output node serves as the exit point for a workflow, collecting and organizing
    the final data produced by the workflow. Its schema is dynamically created based
    on the fields produced by upstream nodes connected to it.
    
    Features:
    - Dynamic schema creation based on graph connections
    - Final data validation according to the dynamic schema
    - Organization of workflow outputs for external consumption
    """
    node_name: ClassVar[str] = OUTPUT_NODE_NAME
    node_version: ClassVar[str] = "0.1.0"
    env_flag: ClassVar[str] = EnvFlag.PROD
    
    # Schema classes will be dynamically created at runtime
    # input_schema_cls = DynamicSchema
    # output_schema_cls = DynamicSchema
    config_schema_cls = None
    
    def process(self, input_data: DynamicSchema, config: Dict[str, Any], *args: Any, **kwargs: Any) -> DynamicSchema:
        """
        Process the input data.
        
        For the output node, this simply validates and passes through the final data.
        
        Args:
            input_data (DynamicSchema): The final data from upstream nodes.
            
        Returns:
            DynamicSchema: The validated final data.
        """
        # Simply pass through the validated final data
        if input_data:
            return self.__class__.output_schema_cls(**input_data.model_dump()) if self.__class__.output_schema_cls is not None else input_data
        return self.__class__.output_schema_cls() if self.__class__.output_schema_cls is not None else input_data

    # @classmethod
    # def create_node(cls, input_fields: Dict[str, Any]) -> Type['OutputNode']:
    #     """
    #     Create a new OutputNode with dynamically created schemas.
        
    #     Args:
    #         input_fields (Dict[str, Any]): Mapping of field names to field definitions
    #                                       for the input schema.
                                          
    #     Returns:
    #         Type[OutputNode]: A new OutputNode class with dynamic schemas.
    #     """
    #     # Create dynamic schemas
    #     dynamic_input_schema = create_model(
    #         'DynamicOutputNodeInputSchema',
    #         __base__=BaseSchema,
    #         **input_fields
    #     )
        
    #     # Output schema is the same as input for the output node
    #     # dynamic_output_schema = dynamic_input_schema
        
    #     # Create empty config schema
    #     # dynamic_config_schema = create_model(
    #     #     'DynamicOutputNodeConfigSchema',
    #     #     __base__=BaseSchema
    #     # )
        
    #     # Create a new class with these schemas
    #     new_node_class = create_model(
    #         f"Dynamic{cls.__name__}",
    #         __base__=cls,
    #         __module__=cls.__module__,
    #         input_schema_cls=dynamic_input_schema,
    #         output_schema_cls=dynamic_input_schema,
    #         # config_schema_cls=dynamic_config_schema
    #     )
        
    #     return new_node_class



# class InputOutputNode(BaseDynamicNode, ABC):
#     """
#     Dynamic Input/Output node for workflows.
    
#     The Input/Output node enables dynamic input and output schemas based on the fields that need 
#     input and output.
    
#     Its input and output schemas are dynamically created based on the fields that need 
#     input and output.
    
#     Features:
#     - Dynamic schema creation for input and output based on fields requiring input and output
#     - Pass-through of validated data after input and output
#     """

#     # Schema classes will be dynamically created at runtime
#     # input_schema_cls = DynamicSchema
#     # output_schema_cls = DynamicSchema
#     config_schema_cls = None

#     @abstractmethod
#     def process(self, input_data: DynamicSchema, config: Dict[str, Any], *args: Any, **kwargs: Any) -> DynamicSchema:
#         """
#         Process the input data through human review.
        
#         For the HITL node, this validates the input, presents it for human review,
#         and validates the human modifications before output.
        
#         Args:
#             input_data (DynamicSchema): The data from upstream nodes for human review.
            
#         Returns:
#             DynamicSchema: The human reviewed/modified data.
#         """
#         # TODO: Implement actual HITL review logic here
#         # For now, simply pass through the data
#         return {self.node_name: input_data}

#     @classmethod
#     def create_node(
#         cls, 
#         input_fields: Dict[str, Any],
#         output_fields: Optional[Dict[str, Any]] = None
#     ) -> Type['InputOutputNode']:
#         """
#         Create a new InputOutputNode with dynamically created schemas.
        
#         Args:
#             input_fields (Dict[str, Any]): Mapping of field names to field definitions
#                                           for the input schema.
#             output_fields (Optional[Dict[str, Any]]): Optional mapping of field names 
#                                                      to field definitions for the output schema.
#                                                      If None, uses same schema as input.

#         Returns:
#             Type[InputOutputNode]: A new InputOutputNode class with dynamic schemas.
#         """
#         class_name = f"Dynamic{cls.__name__}"
#         # Create dynamic input schema
#         dynamic_input_schema = create_model(
#             class_name + "InputSchema",
#             __base__=BaseSchema,
#             **input_fields
#         )
        
#         # Create dynamic output schema (same as input if not specified)
#         if output_fields is None:
#             output_fields = input_fields
            
#         dynamic_output_schema = create_model(
#             class_name + "OutputSchema",
#             __base__=BaseSchema,
#             **output_fields
#         )
        
#         # Create a new class with these schemas
#         new_node_class = create_model(
#             class_name,
#             __base__=cls,
#             __module__=cls.__module__,
#             input_schema_cls=dynamic_input_schema,
#             output_schema_cls=dynamic_output_schema
#         )
        
#         return new_node_class



# TODO: FIXME
# Either change HITL node structure and add hooks like process_user_prompt, interrupt, process_user_input etc or leave this!
# pre-pre processor, lol!
# potentially override run method!
# Is is kinda natural for devs to define all this HITL logic right in the node rather than completely relying on dynamic edges!
class HITLNode(BaseDynamicNode):
    """
    Dynamic Human-In-The-Loop (HITL) node for workflows.
    
    The HITL node enables human review and intervention in workflows by:
    1. Receiving input data from upstream nodes
    2. Presenting it to a human reviewer
    3. Collecting their feedback/modifications
    4. Passing the reviewed/modified data to downstream nodes
    
    Its input and output schemas are dynamically created based on the fields that need 
    human review/modification.
    
    Features:
    - Dynamic schema creation for input and output based on fields requiring review
    - Input validation according to the dynamic schema
    - Output validation of human modifications
    - Pass-through of validated data after human review

    # TODO: implement various HITL configs for different review modes!

    NOTE: if the node is interrupted during receiving input from human, the config will have `_resume` data and provided human input and the node can resume in the process method!
    """
    node_name: ClassVar[str] = f"{HITL_NODE_NAME_PREFIX}default"
    node_version: ClassVar[str] = "0.1.0"
    env_flag: ClassVar[str] = EnvFlag.PROD

    # input_key: ClassVar[str] = "input"
    # hitl_key: ClassVar[str] = "hitl"
    # NOTE: how will loops be constructed! test loops!
    #     Loop: Node --> HITL --> IF/ELSE + ROUTING --> conditional loop back to Node!
    #     Node -> dumps output to global state to retrieve previously processed outputs in each loop iteration!

    # Schema classes will be dynamically created at runtime
    # input_schema_cls = DynamicSchema
    # output_schema_cls = DynamicSchema
    # config_schema_cls = None

    def process(self, input_data: DynamicSchema, config: Dict[str, Any], *args: Any, **kwargs: Any) -> DynamicSchema:
        """
        Process the input data through human review.
        
        For the HITL node, this validates the input, presents it for human review,
        and validates the human modifications before output.
        
        Args:
            input_data (DynamicSchema): The data from upstream nodes for human review.
            
        Returns:
            DynamicSchema: The human reviewed/modified data.
        """
        # TODO: Implement actual HITL review logic here
        # For now, simply pass through the data
        return self.output_schema_cls(**input_data)

    # @classmethod
    # def create_node(
    #     cls, 
    #     input_fields: Dict[str, Any],
    #     output_fields: Optional[Dict[str, Any]] = None
    # ) -> Type['HITLNode']:
    #     """
    #     Create a new HITLNode with dynamically created schemas.
        
    #     Args:
    #         input_fields (Dict[str, Any]): Mapping of field names to field definitions
    #                                       for the input schema.
    #         output_fields (Optional[Dict[str, Any]]): Optional mapping of field names 
    #                                                  to field definitions for the output schema.
    #                                                  If None, uses same schema as input.
                                          
    #     Returns:
    #         Type[HITLNode]: A new HITLNode class with dynamic schemas.
    #     """
    #     # Create dynamic input schema
    #     dynamic_input_schema = create_model(
    #         'DynamicHITLNodeInputSchema',
    #         __base__=BaseSchema,
    #         **input_fields
    #     )
        
    #     # Create dynamic output schema (same as input if not specified)
    #     if output_fields is None:
    #         output_fields = input_fields
            
    #     dynamic_output_schema = create_model(
    #         'DynamicHITLNodeOutputSchema',
    #         __base__=BaseSchema,
    #         **output_fields
    #     )
        
    #     # Create a new class with these schemas
    #     new_node_class = create_model(
    #         f"Dynamic{cls.__name__}",
    #         __base__=cls,
    #         __module__=cls.__module__,
    #         input_schema_cls=dynamic_input_schema,
    #         output_schema_cls=dynamic_output_schema
    #     )
        
    #     return new_node_class

from typing import List, Optional, Dict, Any, Type, ClassVar
from pydantic import Field, create_model

class RouterSchema(BaseSchema):
    """
    Schema for router node configuration.
    
    This schema defines the configuration options for a router node, including
    the available destination nodes and whether multiple nodes can be selected
    for routing.
    
    Attributes:
        choices (List[str]): List of node IDs that can be selected as routing destinations.
        allow_multiple (bool): Whether multiple nodes can be selected for routing simultaneously.
            When True, the router can direct flow to multiple nodes. When False, only one node
            can be selected at a time.
    """
    choices: List[str] = Field(
        ..., 
        description="List of node IDs that can be selected as routing destinations",
        min_length=1
    )
    allow_multiple: bool = Field(
        False, 
        description="Whether multiple nodes can be selected for routing simultaneously"
    )


class DynamicRouterNode(BaseDynamicNode, ABC):
    """
    Dynamic router node for conditional branching in workflows.
    
    This node allows for dynamic routing of workflow execution based on conditions
    or selections. It can route to one or multiple destination nodes based on its
    configuration and input data.
    
    The router node is configured with a list of possible destination nodes and
    whether multiple destinations can be selected simultaneously.
    """
    node_name: ClassVar[str] = "dynamic_router"
    node_version: ClassVar[str] = "0.1.0"
    config_schema_cls: ClassVar[Type[RouterSchema]] = RouterSchema

    # instance config
    config: RouterSchema

    @abstractmethod
    def process(self, input_data: DynamicSchema, config: Dict[str, Any], *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """
        Process input data and determine routing destination(s).
        
        This method should be implemented by subclasses to define the routing logic.
        The base implementation simply returns the input data with the node name.
        
        Args:
            input_data (Optional[BaseSchema]): Input data to process
            
        Returns:
            Dict[str, Any]: Dictionary containing routing information and processed data
        """
        # Base implementation - should be overridden by subclasses
        # with specific routing logic
        if input_data is not None:
            output_data = self.__class__.output_schema_cls(**input_data.model_dump()) if self.__class__.output_schema_cls is not None else input_data
        else:
            output_data =  self.__class__.output_schema_cls() if self.__class__.output_schema_cls is not None else input_data

        return {TEMP_STATE_UPDATE_KEY: output_data, ROUTER_CHOICE_KEY: "routed_node_id"}
    
    # @classmethod
    # def create_router_node(
    #     cls,
    #     input_fields: Dict[str, Any],
    #     output_fields: Optional[Dict[str, Any]] = None,
    #     choices: List[str] = None,
    #     allow_multiple: bool = False
    # ) -> Type['DynamicRouterNode']:
    #     """
    #     Create a new router node with dynamically created schemas.
        
    #     Args:
    #         input_fields (Dict[str, Any]): Mapping of field names to field definitions
    #                                      for the input schema.
    #         output_fields (Optional[Dict[str, Any]]): Optional mapping of field names 
    #                                                 to field definitions for the output schema.
    #                                                 If None, uses same schema as input.
    #         choices (List[str]): List of node IDs that can be selected as routing destinations.
    #         allow_multiple (bool): Whether multiple nodes can be selected for routing.
                                
    #     Returns:
    #         Type[DynamicRouterNode]: A new DynamicRouterNode class with dynamic schemas.
    #     """
    #     # Create dynamic input schema
    #     dynamic_input_schema = create_model(
    #         'DynamicRouterNodeInputSchema',
    #         __base__=BaseSchema,
    #         **input_fields
    #     )
        
    #     # Create dynamic output schema (same as input if not specified)
    #     if output_fields is None:
    #         output_fields = input_fields
            
    #     dynamic_output_schema = create_model(
    #         'DynamicRouterNodeOutputSchema',
    #         __base__=BaseSchema,
    #         **output_fields
    #     )
        
    #     # Create router config with provided choices
    #     router_config = RouterSchema(
    #         choices=choices or [],
    #         allow_multiple=allow_multiple
    #     )
        
    #     # Create a new class with these schemas
    #     new_node_class = create_model(
    #         f"Dynamic{cls.__name__}",
    #         __base__=cls,
    #         __module__=cls.__module__,
    #         input_schema_cls=(ClassVar[Type[BaseSchema]], dynamic_input_schema),
    #         output_schema_cls=(ClassVar[Type[BaseSchema]], dynamic_output_schema),
    #         config=(Optional[RouterSchema], router_config)
    #     )
        
    #     return new_node_class
