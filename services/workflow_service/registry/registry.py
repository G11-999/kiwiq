"""
Registry for workflow nodes.

This module provides a registry for all available node types in the workflow system.
The registry allows nodes to be looked up by name and version, and provides
functionality for registering new nodes.
"""
from typing import Any, Dict, List, Optional, Type
import uuid

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

# from kiwi_app.workflow_app.schemas import NodeTemplateUpdate
from workflow_service.config.constants import GRAPH_STATE_SPECIAL_NODE_NAME, HITL_NODE_NAME_PREFIX
from workflow_service.registry.nodes.core.base import BaseNode
from workflow_service.registry.nodes.core.dynamic_nodes import InputNode, OutputNode, DynamicRouterNode, HITLNode
# from workflow_service.registry.nodes.core.hitl_node import HITLNode
# from workflow_service.registry.nodes.core.flow_nodes import FilterNode, IfElseNode
# from workflow_service.registry.nodes.core.join_node import JoinNode
# from workflow_service.registry.nodes.ai.openai_node import OpenAINode

from workflow_service.registry.schemas.base import BaseSchema
from workflow_service.utils.utils import is_central_state_special_node

# Import DAOs and schemas from kiwi_app
# Assuming DAOs are initialized elsewhere or passed in

# from kiwi_app.workflow_app.schemas import GraphSchema # Import GraphSchema


class BaseRegistry:
    """
    Base class for all registries.
    """
    pass
    
    
    


class MockRegistry(BaseRegistry):
    """
    Mock registry for workflow nodes.
    
    A simple registry implementation that stores node classes by name and version.
    Provides lookup by name (returning latest version) or by name and version.
    
    Attributes:
        _nodes (Dict[str, Dict[str, Type[BaseNode]]]): Mapping of node names and versions to node classes.
    """
    
    def __init__(self):
        """Initialize empty registry."""
        self._nodes = {}
        self._schemas = {}
        self._metadata = {}
        
    def register_node(self, node_class: Type[BaseNode]) -> None:
        """
        Register a node class in the registry.
        
        Args:
            node_class (Type[BaseNode]): The node class to register.
            
        Raises:
            ValueError: If node with same name and version already exists.
        """
        node_name = node_class.node_name
        node_version = node_class.node_version

        assert node_version is not None, "Node version must be defined"
        
        # Initialize version dict if first version of this node
        if node_name not in self._nodes:
            self._nodes[node_name] = {}
            self._metadata[node_name] = {}
        # Check if version already registered
        if node_version in self._nodes[node_name]:
            raise ValueError(f"Node {node_name} version {node_version} already registered")
            
        # Register the node
        self._nodes[node_name][node_version] = node_class
        metadata_dict = {
            "is_dynamic": self.is_node_instance_dynamic(node_class),
            "is_router": self.is_node_instance_router(node_class), 
            "is_hitl": self.is_node_instance_hitl(node_class),
            "is_input": self.is_node_instance_input(node_class),
            "is_output": self.is_node_instance_output(node_class),
            "is_tool": self.is_node_instance_tool(node_class),
            # NOTE: has subnodes can be different across version to version!
            # "has_subnodes": node_class.has_subnodes
        }
        if not self._metadata[node_name]:
            self._metadata[node_name] = metadata_dict
        else:
            # Verify consistency across versions (should be identical)
            existing_meta = self._metadata[node_name]
            if existing_meta != metadata_dict:
                 # Log a warning or raise an error if metadata differs between versions
                 print(f"Warning: Metadata mismatch for node '{node_name}'. Existing: {existing_meta}, New: {metadata_dict}")
                 # Optionally raise: raise ValueError(f"Metadata mismatch for node '{node_name}' across versions.")
                 # For now, let's overwrite with the latest version's metadata, assuming it's correct
                 raise ValueError(f"Metadata mismatch for node '{node_name}' across versions.")
                 self._metadata[node_name] = metadata_dict
        
    
    def get_node(self, node_name: str, version: Optional[str] = None, return_if_tool: bool = False) -> Type[BaseNode]:
        """
        Get a node class from the registry.
        
        Args:
            node_name (str): Name of node to get
            version (Optional[str]): Version of node to get. If None, returns latest version.
            return_if_tool (bool): If True, return the node even if it's marked as a tool. Defaults to False.
            
        Returns:
            Type[BaseNode]: The requested node class
            
        Raises:
            ValueError: If node name or version not found, or if trying to get a tool node without return_if_tool=True.
        """
        # Check node exists
        if node_name not in self._nodes:
            raise ValueError(f"Node {node_name} not found in registry")
            
        # Get latest version if none specified
        if version is None:
            # Sort versions properly (e.g., handle '1.10.0' vs '1.9.0')
            try:
                # Attempt semantic version sorting if possible
                from packaging.version import parse as parse_version
                sorted_versions = sorted(self._nodes[node_name].keys(), key=parse_version, reverse=True)
                version = sorted_versions[0]
            except ImportError:
                # Fallback to simple string sort (might be inaccurate for complex versions)
                version = max(self._nodes[node_name].keys())

        # Check version exists    
        elif version not in self._nodes[node_name]:
            raise ValueError(f"Version {version} not found for node {node_name}")
            
        node_class = self._nodes[node_name][version]

        # Check if the node is a tool and if it should be returned
        if not return_if_tool and self.is_node_instance_tool(node_class):
             raise ValueError(f"Node {node_name} (version {version}) is a tool node and cannot be directly retrieved without `return_if_tool=True`.")

        return node_class

    def register_schema(self, schema_class: Type[BaseModel]) -> None:
        """
        Register a schema class in the registry. 
        For now, only supports schema BaseModel with a defined `schema_name` classvar field. (i.e. statically defined schema in code)
        
        Args:
            schema_class (Type[BaseSchema]): The schema class to register.
            
        Raises:
            ValueError: If schema with same name already exists.
        """
        if not hasattr(schema_class, "schema_name"):
            raise ValueError(f"Schema class {schema_class.__name__} must have a defined `schema_name` classvar field")
        schema_name = schema_class.schema_name

        schema_version = getattr(schema_class, "schema_version", None)
        # Initialize version dict if first version of this schema
        if schema_name not in self._schemas:
            self._schemas[schema_name] = {}
            
        # Check if version already registered
        if schema_version in self._schemas[schema_name]:
            raise ValueError(f"Schema {schema_name} version {schema_version} already registered")
            
        # Register the schema
        self._schemas[schema_name][schema_version] = schema_class
        
    def get_schema(self, schema_name: str, schema_version: Optional[str] = None) -> Type[BaseModel]:
        """
        Get a schema class from the registry.
        
        Args:
            schema_name (str): Name of schema to get
            schema_version (Optional[str]): Version of schema to get. If None, returns latest version.
            
        Returns:
            Type[BaseSchema]: The requested schema class
            
        Raises:
            ValueError: If schema name or version not found
        """
        # Check schema exists
        if schema_name not in self._schemas:
            raise ValueError(f"Schema {schema_name} not found in registry")
            
        # Get latest version if none specified
        if schema_version is None:
            schema_versions = list(self._schemas[schema_name].keys())
            if None in schema_versions:
                # If an unversioned schema exists, prioritize it when no version is specified
                schema_version = None
            elif schema_versions:
                 # Sort versions properly
                try:
                    from packaging.version import parse as parse_version
                    # Filter out None before sorting
                    valid_versions = [v for v in schema_versions if v is not None]
                    if valid_versions:
                        sorted_versions = sorted(valid_versions, key=parse_version, reverse=True)
                        schema_version = sorted_versions[0]
                    else: # Should only happen if only None was present, handled above
                         raise ValueError(f"No valid versions found for schema {schema_name}")
                except ImportError:
                    # Fallback sort
                    schema_version = max(v for v in schema_versions if v is not None) # Ensure we don't max(None)
            else:
                raise ValueError(f"No versions found for schema {schema_name}") # Should not happen if schema_name exists

        # Check version exists    
        elif schema_version not in self._schemas[schema_name]:
            raise ValueError(f"Version {schema_version} not found for schema {schema_name}")
            
        return self._schemas[schema_name][schema_version]
    
    def get_all_schema_names(self) -> List[str]:
        """
        Get all registered schema names.
        
        Returns:
            List[str]: List of all registered schema names
        """
        return list(self._schemas.keys())
    
    
    # def has_subnodes(self, node_name: str) -> bool:
    #     """
    #     Check if a node has subnodes.
        
    #     Args:
    #         node_name (str): Name of the node to check
            
    #     Returns:
    #         bool: True if the node has subnodes, False otherwise
            
    #     Raises:
    #         ValueError: If node name not found in registry
    #     """
    #     if node_name not in self._metadata:
    #         raise ValueError(f"Node {node_name} not found in registry")
        
    #     return self._metadata[node_name].get("has_subnodes", False)
    
    # def get_all_node_names(self) -> List[str]:
    #     """
    #     Get all registered node names.
        
    #     Returns:
    #         List[str]: List of all registered node names
    #     """
    #     return list(self._nodes.keys())
    
    # def get_node_versions(self, node_name: str) -> List[str]:
    #     """
    #     Get all available versions for a node.
        
    #     Args:
    #         node_name (str): Name of the node
            
    #     Returns:
    #         List[str]: List of all available versions for the node
            
    #     Raises:
    #         ValueError: If node name not found in registry
    #     """
    #     if node_name not in self._nodes:
    #         raise ValueError(f"Node {node_name} not found in registry")
        
    #     return list(self._nodes[node_name].keys())
    
    # def get_latest_version(self, node_name: str) -> str:
    #     """
    #     Get the latest version of a node.
        
    #     Args:
    #         node_name (str): Name of the node
            
    #     Returns:
    #         str: Latest version of the node
            
    #     Raises:
    #         ValueError: If node name not found in registry
    #     """
    #     if node_name not in self._nodes:
    #         raise ValueError(f"Node {node_name} not found in registry")
        
    #     return max(self._nodes[node_name].keys())
    def is_router_node(self, node_name: str) -> bool:
        """
        Check if a node is a router node.
        """
        if node_name not in self._metadata:
             raise ValueError(f"Node {node_name} not found in registry metadata.")
        return self._metadata[node_name].get("is_router", False)
    
    def is_dynamic_node(self, node_name: str) -> bool:
        """
        Check if a node has dynamic schemas.
        
        Args:
            node_name (str): Name of the node to check
            
        Returns:
            bool: True if the node has dynamic schemas, False otherwise
            
        Raises:
            ValueError: If node name not found in registry
        """
        if node_name not in self._metadata:
            raise ValueError(f"Node {node_name} not found in registry metadata.")
        
        return self._metadata[node_name].get("is_dynamic", False)
    
    def is_non_dynamic_normal_node(self, node_name: str) -> bool:
        """
        Check if a node is a non-dynamic normal node.
        
        Args:
            node_name (str): Name of the node to check
            
        Returns:
            bool: True if the node is a non-dynamic normal node, False otherwise
        """
        return not (is_central_state_special_node(node_name) or self.is_dynamic_node(node_name))
    
    def is_hitl_node(self, node_name: str) -> bool:
        """
        Check if a node is a HITL (Human-In-The-Loop) node.
        
        Args:
            node_name (str): Name of the node to check
            
        Returns:
            bool: True if the node is a HITL node, False otherwise
        """
        # node_name.startswith(HITL_NODE_NAME_PREFIX) and self.is_dynamic_node(node_name)
        if node_name not in self._metadata:
             raise ValueError(f"Node {node_name} not found in registry metadata.")
        return self._metadata[node_name].get("is_hitl", False)
    
    def is_input_node(self, node_name: str) -> bool:
        """
        Check if a node is an input node.
        """
        if node_name not in self._metadata:
             raise ValueError(f"Node {node_name} not found in registry metadata.")
        return self._metadata[node_name].get("is_input", False)
    
    def is_output_node(self, node_name: str) -> bool:
        """
        Check if a node is an output node.
        """
        if node_name not in self._metadata:
             raise ValueError(f"Node {node_name} not found in registry metadata.")
        return self._metadata[node_name].get("is_output", False)

    @staticmethod
    def get_node_instance_class(node_instance: Any) -> Type[BaseNode]:
        """
        Get the class of a node instance.
        """
        if isinstance(node_instance, type):
            return node_instance
        else:
            return node_instance.__class__

    @staticmethod
    def is_node_instance_router(node_instance: Any) -> bool:
        """
        Check if a node instance is a router node.
        
        Args:
            node_instance (Any): The node instance to check
            
        Returns:
            bool: True if the node instance is a router node, False otherwise
        """
        node_class = MockRegistry.get_node_instance_class(node_instance)
        return issubclass(node_class, DynamicRouterNode)
    
    @staticmethod
    def is_node_instance_dynamic(node_instance: Any) -> bool:
        """
        Check if a node instance has dynamic schemas.
        
        Args:
            node_instance (Any): The node instance to check
            
        Returns:
            bool: True if the node instance has dynamic schemas, False otherwise
        """
        # Check if node_instance is a type (class) or an instance
        node_class = MockRegistry.get_node_instance_class(node_instance)
        # Check if the class itself has the attribute set to True
        has_dynamic_schemas_attr = getattr(node_class, "dynamic_schemas", False)
        return has_dynamic_schemas_attr
        # Additionally, check if it's a subclass of known dynamic node types
        # is_dynamic_subclass = issubclass(node_class, (InputNode, OutputNode, HITLNode, DynamicRouterNode))
        # return has_dynamic_schemas_attr or is_dynamic_subclass
    
    
    @staticmethod
    def is_node_instance_non_dynamic_normal(node_instance: Any) -> bool:
        """
        Check if a node instance is a non-dynamic normal node.
        
        Args:
            node_instance (Any): The node instance to check
            
        Returns:
            bool: True if the node instance is a non-dynamic normal node, False otherwise
        """
        # Not central state and not dynamic
        # NOTE: ideally the central state special node will never be an instance!
        return not MockRegistry.is_node_instance_dynamic(node_instance)
    
    @staticmethod
    def is_node_instance_hitl(node_instance: Any) -> bool:
        """
        Check if a node instance is a HITL (Human-In-The-Loop) node.
        
        Args:
            node_instance (Any): The node instance to check
            
        Returns:
            bool: True if the node instance is a HITL node, False otherwise
        """
        node_class = MockRegistry.get_node_instance_class(node_instance)
        return issubclass(node_class, HITLNode)
    
    @staticmethod
    def is_node_instance_input(node_instance: Any) -> bool:
        """
        Check if a node instance is an input node.
        
        Args:
            node_instance (Any): The node instance to check
            
        Returns:
            bool: True if the node instance is an input node, False otherwise
        """
        node_class = MockRegistry.get_node_instance_class(node_instance)
        return issubclass(node_class, InputNode)
    
    @staticmethod
    def is_node_instance_output(node_instance: Any) -> bool:
        """
        Check if a node instance is an output node.
        
        Args:
            node_instance (Any): The node instance to check
            
        Returns:
            bool: True if the node instance is an output node, False otherwise
        """
        node_class = MockRegistry.get_node_instance_class(node_instance)
        return issubclass(node_class, OutputNode)

    @staticmethod
    def is_node_instance_tool(node_instance: Any) -> bool:
        """
        Check if a node instance is a tool node.
        """
        node_class = MockRegistry.get_node_instance_class(node_instance)
        return getattr(node_class, "node_is_tool", False)




class DBRegistry(MockRegistry):
    """
    Database-backed registry for workflow components (nodes, schemas, prompts, workflows).

    This registry maintains both database records (via DAOs) for templates and workflows,
    and local in-memory caches for the actual Python classes of registered nodes and schemas.
    This allows for efficient retrieval of classes during runtime without DB access,
    while ensuring definitions are persisted.

    This registry interacts with the database via DAO objects to persist and retrieve
    workflow component definitions. It handles registration by checking if an entity
    already exists before creating it.

    Attributes:
        node_template_dao (kiwi_crud.NodeTemplateDAO): DAO for NodeTemplate model.
        schema_template_dao (kiwi_crud.SchemaTemplateDAO): DAO for SchemaTemplate model.
        prompt_template_dao (kiwi_crud.PromptTemplateDAO): DAO for PromptTemplate model.
        workflow_dao (kiwi_crud.WorkflowDAO): DAO for Workflow model.

        _nodes (Dict[str, Dict[str, Type[BaseNode]]]): Local cache mapping node name/version to node class.
        _schemas (Dict[str, Dict[str, Type[BaseSchema]]]): Local cache mapping schema name/version to schema class.
        _metadata_cache (Dict[str, Dict[str, Any]]): Local cache for node metadata flags.
    
    # TODO: Add migration methods and version control for node templates, maybe delete older version of nodes if not registered during startup and DB version mismatch?
    """

    def __init__(
        self,
        node_template_dao = None,  # : kiwi_crud.NodeTemplateDAO,
        schema_template_dao = None,  # : kiwi_crud.SchemaTemplateDAO,
        prompt_template_dao = None,  # : kiwi_crud.PromptTemplateDAO,
        workflow_dao = None,  # : kiwi_crud.WorkflowDAO,
    ) -> None:
        """Initialize the DBRegistry with DAO instances and empty local caches.

        Args:
            node_template_dao: DAO for NodeTemplate operations.
            schema_template_dao: DAO for SchemaTemplate operations.
            prompt_template_dao: DAO for PromptTemplate operations.
            workflow_dao: DAO for Workflow operations.
        """
        self.node_template_dao = node_template_dao
        self.schema_template_dao = schema_template_dao
        self.prompt_template_dao = prompt_template_dao
        self.workflow_dao = workflow_dao
        # Cache node metadata similar to MockRegistry, fetched on first access or init
        # TODO: Implement fetching/caching metadata from DB if needed for performance
        self._metadata: Dict[str, Dict[str, Any]] = {}

        # Local caches for direct class access (like MockRegistry)
        self._nodes: Dict[str, Dict[str, Type[BaseNode]]] = {}
        self._schemas: Dict[str, Dict[str, Type[BaseSchema]]] = {}

    async def register_node_template(self, db: AsyncSession, node_class: Type[BaseNode]):  #  -> kiwi_models.NodeTemplate:
        """
        Registers a node class as a NodeTemplate in the database.

        Checks if a template with the same name and version already exists.
        If not, extracts the signature and creates a new NodeTemplate record.

        Args:
            db: The AsyncSession instance.
            node_class: The BaseNode subclass to register.

        Returns:
            The existing or newly created NodeTemplate database object.

        Raises:
            ValueError: If node_version is missing.
        """
        from kiwi_app.workflow_app import schemas as kiwi_schemas
        node_name = node_class.node_name
        node_version = node_class.node_version

        if node_version is None:
            raise ValueError(f"Node {node_name} must have a node_version defined.")

        # Check if node template already exists
        existing_template = await self.node_template_dao.get_by_name_version(db, name=node_name, version=node_version)

        # Extract signature and create schema
        input_schema = node_class.input_schema_cls
        if input_schema is not None:
            input_schema = input_schema.model_json_schema()
        output_schema = node_class.output_schema_cls
        if output_schema is not None:
            output_schema = output_schema.model_json_schema()
        config_schema = node_class.config_schema_cls
        if config_schema is not None:
            config_schema = config_schema.model_json_schema()
        
        node_is_tool = getattr(node_class, "node_is_tool", False)
        
        # TODO: Add logic to update if definition changed?
        if existing_template:
            diff = {}
            if existing_template.description != node_class.__doc__:
                diff["description"] = node_class.__doc__
            if existing_template.input_schema != input_schema:
                diff["input_schema"] = input_schema
            if existing_template.output_schema != output_schema:
                diff["output_schema"] = output_schema
            if existing_template.config_schema != config_schema:
                diff["config_schema"] = config_schema
            if existing_template.launch_status != node_class.env_flag:
                diff["launch_status"] = node_class.env_flag
            if existing_template.node_is_tool != node_is_tool:
                diff["node_is_tool"] = node_is_tool
            
            if not diff:
                self._update_metadata_cache(node_class)
                self._register_node_local(node_class)
                return existing_template

        create_schema = kiwi_schemas.NodeTemplateCreate(
            name=node_name,
            version=node_version,
            node_is_tool=node_is_tool,
            description=node_class.__doc__ or "", # Use class docstring
            input_schema=input_schema,
            output_schema=output_schema,
            config_schema=config_schema,
            launch_status=node_class.env_flag, # Map env_flag to launch_status
            # Add other fields if NodeTemplateCreate requires them
        )

        # Create the node template in the DB
        # Assuming NodeTemplateDAO.create is for admin/system use and doesn't require org_id
        if existing_template:
            update_data = kiwi_schemas.NodeTemplateUpdate(
                node_is_tool=node_is_tool,
                description=create_schema.description,
                input_schema=create_schema.input_schema,
                output_schema=create_schema.output_schema,
                config_schema=create_schema.config_schema,
                launch_status=create_schema.launch_status,
            )
            new_template = await self.node_template_dao.update(db, db_obj=existing_template, obj_in=update_data)
        else:
            new_template = await self.node_template_dao.create(db, obj_in=create_schema)

        # Update metadata cache (simplified)
        self._update_metadata_cache(node_class)

        self._register_node_local(node_class)

        return new_template
    
    async def deregister_node_template(self, db: AsyncSession, node_class: Type[BaseNode]):
        """Remove a node template from the database."""
        node_name = node_class.node_name
        node_version = node_class.node_version

        if node_version is None:
            raise ValueError(f"Node {node_name} must have a node_version defined.")

        # Check if node template already exists
        existing_template = await self.node_template_dao.get_by_name_version(db, name=node_name, version=node_version)
        if existing_template:
            await self.node_template_dao.remove_obj(db, obj=existing_template)

    async def register_schema_template(
        self,
        db: AsyncSession,
        schema_class: Type[BaseSchema],
        is_system_entity: bool = True,
        owner_org_id: Optional[str] = None,
        # TODO: Add creator_user_id?
    ):  #  -> kiwi_models.SchemaTemplate:
        """
        Registers a schema class as a SchemaTemplate in the database.

        Also registers the schema class in the local `_schemas` cache.

        Args:
            db: The AsyncSession instance.
            schema_class: The BaseSchema subclass to register.
            is_system_entity: Flag indicating if it's a system template.
            owner_org_id: The organization ID if it's not a system template.

        Returns:
            The existing or newly created SchemaTemplate database object.

        Raises:
            ValueError: If schema_name is missing or if org template lacks owner_org_id.
        """
        from kiwi_app.workflow_app import schemas as kiwi_schemas, models as kiwi_models
        if not hasattr(schema_class, "schema_name") or not schema_class.schema_name:
            raise ValueError(f"Schema class {schema_class.__name__} must have a defined `schema_name` classvar field.")
        schema_name = schema_class.schema_name
        schema_version = getattr(schema_class, "schema_version", "latest") # Use 'latest' if no version

        if not is_system_entity and owner_org_id is None:
            raise ValueError("owner_org_id must be provided for non-system schema templates.")

        # Check if schema template already exists
        existing_template = await self.schema_template_dao.get_by_name_version(
            db, name=schema_name, version=schema_version, owner_org_id=owner_org_id if not is_system_entity else None
        )
        if existing_template:
            self._register_schema_local(schema_class)
            return existing_template

        # Prepare creation schema
        create_schema = kiwi_schemas.SchemaTemplateCreate(
            name=schema_name,
            version=schema_version,
            description=schema_class.__doc__ or "",
            schema_definition=schema_class.model_json_schema(), # Get JSON schema def
            schema_type=kiwi_models.SchemaType.JSON_SCHEMA, # Assuming JSON schema for now
        )

        # Create in DB
        try:
            if is_system_entity:
                # TODO: Need a separate DAO method for system templates or adjust create
                # Example: Assuming BaseTemplateDAO.create handles is_system_entity=True when owner_org_id=None
                new_template = await self.schema_template_dao.create_system(db, obj_in=create_schema) # Requires create_system method in DAO
                # raise NotImplementedError("System schema template creation via DAO needs implementation.")
            else:
                new_template = await self.schema_template_dao.create(
                    db, obj_in=create_schema, owner_org_id=owner_org_id
                )
        except NotImplementedError as e:
            # Log or handle the case where system template creation isn't ready
            print(f"DAO method for system schema template creation not implemented: {e}")
            raise

        # Register in local cache upon successful DB registration
        self._register_schema_local(schema_class)
        return new_template

    async def register_prompt_template(
        self,
        db: AsyncSession,
        prompt_template_schema,  # : kiwi_schemas.PromptTemplateCreate, # Use schema for input
        is_system_entity: bool = True, # Changed default to True
        owner_org_id: Optional[str] = None, # Kept Optional
    ):  #  -> kiwi_models.PromptTemplate:
        """
        Registers a prompt template in the database.

        Args:
            db: The AsyncSession instance.
            prompt_template_schema: Schema containing prompt template details.
            is_system_entity: Flag indicating if it's a system template.
            owner_org_id: The organization ID if it's not a system template.

        Returns:
            The existing or newly created PromptTemplate database object.

        Raises:
            ValueError: If org template lacks owner_org_id.
        """
        if not is_system_entity and owner_org_id is None:
            raise ValueError("owner_org_id must be provided for non-system prompt templates.")

        # Check if prompt template already exists
        existing_template = await self.prompt_template_dao.get_by_name_version(
            db, name=prompt_template_schema.name,
            version=prompt_template_schema.version,
            owner_org_id=owner_org_id if not is_system_entity else None
        )
        if existing_template:
            return existing_template

        # Create in DB
        try:
            if is_system_entity:
                # TODO: Similar to schema template, need system creation logic
                # Example: Assuming BaseTemplateDAO.create handles is_system_entity=True when owner_org_id=None
                new_template = await self.prompt_template_dao.create_system(db, obj_in=prompt_template_schema) # Requires create_system
                # raise NotImplementedError("System prompt template creation via DAO needs implementation.")
            else:
                new_template = await self.prompt_template_dao.create(
                    db, obj_in=prompt_template_schema, owner_org_id=owner_org_id
                )
        except NotImplementedError as e:
            print(f"DAO method for system prompt template creation not implemented: {e}")
            raise

        # Note: Prompt templates don't have a direct class cache like nodes/schemas
        return new_template

    async def register_workflow(
        self,
        db: AsyncSession,
        workflow_schema,  # : kiwi_schemas.WorkflowCreate, # Use schema for input
        owner_org_id: str,
        creator_user_id: Optional[str] = None,
    ):  #  -> kiwi_models.Workflow:
        """
        Registers a workflow configuration in the database.

        Args:
            db: The AsyncSession instance.
            workflow_schema: Schema containing workflow details, including graph_config.
            owner_org_id: The ID of the owning organization.
            creator_user_id: The ID of the user creating the workflow.

        Returns:
            The newly created Workflow database object.
            (Workflows are typically unique per creation, not checked like templates)
        """
        # TODO: Add check if a workflow with the same name/version_tag already exists for the org?
        # Maybe enforce unique (name, owner_org_id, version_tag) constraint in DB?

        new_workflow = await self.workflow_dao.create(
            db,
            obj_in=workflow_schema,
            owner_org_id=owner_org_id,
            user_id=creator_user_id # Pass user_id to DAO
        )
        return new_workflow

    # NOTE: use get_node same as MockRegistry method to get from local cache!
    async def get_node_template(self, db: AsyncSession, node_name: str, version: Optional[str] = None):  #  -> Optional[kiwi_models.NodeTemplate]:
        """
        Get a node template from the database.

        Args:
            db: The AsyncSession instance.
            node_name (str): Name of node template to get.
            version (Optional[str]): Version of node template. If None, gets latest prod version.

        Returns:
            The requested NodeTemplate object or None if not found.
        """
        if version:
            return await self.node_template_dao.get_by_name_version(db, name=node_name, version=version)
        else:
            # Get latest production version if no specific version requested
            return await self.node_template_dao.get_latest_prod_version(db, name=node_name)

    # NOTE: use get_schema same as MockRegistry method to get from local cache!
    async def get_schema_template(self, db: AsyncSession, schema_name: str, version: Optional[str] = None, owner_org_id: Optional[str] = None):  #  -> Optional[kiwi_models.SchemaTemplate]:
        """
        Get a schema template from the database.

        Searches org-specific first (if owner_org_id provided), then system templates.

        Args:
            db: The AsyncSession instance.
            schema_name (str): Name of schema template.
            version (Optional[str]): Version string. Defaults to 'latest'.
            owner_org_id (Optional[str]): Org ID for org-specific lookup.

        Returns:
            The requested SchemaTemplate object or None.
        """
        # Version defaults to 'latest' if None
        effective_version = version if version is not None else "latest"
        return await self.schema_template_dao.get_by_name_version(db, name=schema_name, version=effective_version, owner_org_id=owner_org_id)

    async def get_prompt_template(self, db: AsyncSession, prompt_name: str, version: Optional[str] = None, owner_org_id: Optional[str] = None):  #  -> Optional[kiwi_models.PromptTemplate]:
        """
        Get a prompt template from the database.

        Searches org-specific first, then system templates.

        Args:
            db: The AsyncSession instance.
            prompt_name (str): Name of prompt template.
            version (Optional[str]): Version string. Defaults to 'latest'.
            owner_org_id (Optional[str]): Org ID for org-specific lookup.

        Returns:
            The requested PromptTemplate object or None.
        """
        effective_version = version if version is not None else "latest"
        return await self.prompt_template_dao.get_by_name_version(db, name=prompt_name, version=effective_version, owner_org_id=owner_org_id)

    async def get_workflow(self, db: AsyncSession, workflow_id: str, owner_org_id: str):  #  -> Optional[kiwi_models.Workflow]:
        """
        Get a specific workflow by its ID and owning organization ID.

        Args:
            db: The AsyncSession instance.
            workflow_id (str): The ID of the workflow.
            owner_org_id (str): The ID of the owning organization.

        Returns:
            The requested Workflow object or None if not found or not owned by the org.
        """
        return await self.workflow_dao.get_by_id_and_org(db, workflow_id=workflow_id, org_id=owner_org_id)

    # --- Metadata Methods (Similar to MockRegistry, potentially cached) --- #

    def _update_metadata_cache(self, node_class: Type[BaseNode]) -> None:
        """Internal helper to update the local metadata cache for a node type."""
        node_name = node_class.node_name
        # Always update or add the metadata when a node is registered
        self._metadata[node_name] = {
            "is_dynamic": DBRegistry.is_node_instance_dynamic(node_class),
            "is_router": DBRegistry.is_node_instance_router(node_class),
            "is_hitl": DBRegistry.is_node_instance_hitl(node_class),
            "is_input": DBRegistry.is_node_instance_input(node_class),
            "is_output": DBRegistry.is_node_instance_output(node_class),
            "is_tool": DBRegistry.is_node_instance_tool(node_class),
        }

    # TODO: Implement fetching metadata from DB if needed, or rely on initial registration
    async def _get_metadata(self, db: AsyncSession, node_name: str) -> Dict[str, Any]:
        """Retrieves metadata for a node, potentially from cache or DB."""
        # Always check cache first
        if node_name in self._metadata:
            return self._metadata[node_name]
        else:
            # Attempt to fetch from DB if not in cache
            # This assumes get_node_template fetches the latest version if available
            template = await self.get_node_template(db, node_name=node_name)
            if template:
                # Derive metadata from the template. This requires mapping DB fields back to node properties.
                # Example (needs refinement based on how NodeTemplate maps to BaseNode properties):
                # Assuming NodeTemplate stores enough info or we load the class dynamically.
                # This part is complex as we don't have the BaseNode class itself easily.
                # A simpler approach might be to store metadata flags directly in NodeTemplate DB model.
                # For now, we'll raise an error, implying registration should populate the cache.
                 raise ValueError(f"Metadata for node {node_name} not found in cache and DB fetching not fully implemented.")
                 # Placeholder for fetching/deriving from DB:
                 # self._metadata[node_name] = self._derive_metadata_from_template(template)

            else:
                raise ValueError(f"Node template {node_name} not found in DB, cannot determine metadata.")

        return self._metadata[node_name]

    # # Metadata methods now operate sync on the cache, mirroring MockRegistry
    # # No db session needed for these checks after initial registration/loading

    # def is_router_node(self, node_name: str) -> bool:
    #     """Check if a node is a router node based on cached/DB metadata."""
    #     # Use cached metadata directly
    #     if node_name not in self._metadata:
    #          raise ValueError(f"Metadata for node {node_name} not found in cache. Ensure node was registered.")
    #     metadata = self._metadata[node_name]
    #     return metadata.get("is_router", False)

    # def is_dynamic_node(self, node_name: str) -> bool:
    #     """Check if a node has dynamic schemas based on cached/DB metadata."""
    #     if node_name not in self._metadata:
    #          raise ValueError(f"Metadata for node {node_name} not found in cache. Ensure node was registered.")
    #     metadata = self._metadata[node_name]
    #     return metadata.get("is_dynamic", False)

    # def is_hitl_node(self, node_name: str) -> bool:
    #     """Check if a node is a HITL node based on cached/DB metadata."""
    #     if node_name not in self._metadata:
    #          raise ValueError(f"Metadata for node {node_name} not found in cache. Ensure node was registered.")
    #     metadata = self._metadata[node_name]
    #     return metadata.get("is_hitl", False)

    # def is_input_node(self, node_name: str) -> bool:
    #     """Check if a node is an input node based on cached/DB metadata."""
    #     if node_name not in self._metadata:
    #          raise ValueError(f"Metadata for node {node_name} not found in cache. Ensure node was registered.")
    #     metadata = self._metadata[node_name]
    #     return metadata.get("is_input", False)

    # def is_output_node(self, node_name: str) -> bool:
    #     """Check if a node is an output node based on cached/DB metadata."""
    #     if node_name not in self._metadata:
    #          raise ValueError(f"Metadata for node {node_name} not found in cache. Ensure node was registered.")
    #     metadata = self._metadata[node_name]
    #     return metadata.get("is_output", False)

    # def is_tool_node(self, node_name: str) -> bool:
    #     """Check if a node is a tool node based on cached/DB metadata."""
    #     if node_name not in self._metadata:
    #          raise ValueError(f"Metadata for node {node_name} not found in cache. Ensure node was registered.")
    #     metadata = self._metadata[node_name]
    #     return metadata.get("is_tool", False)

    # def is_non_dynamic_normal_node(self, node_name: str) -> bool:
    #     """Check if a node is a non-dynamic normal node."""
    #     # Same logic as MockRegistry, using potentially cached metadata
    #     is_dynamic = self.is_dynamic_node(node_name)
    #     return not (is_central_state_special_node(node_name) or is_dynamic)

    # # --- Static Methods (Can remain the same as MockRegistry) --- #
    # # These operate on class types or instances directly, not DB state.
    # get_node_instance_class = MockRegistry.get_node_instance_class
    # is_node_instance_router = MockRegistry.is_node_instance_router
    # is_node_instance_dynamic = MockRegistry.is_node_instance_dynamic
    # is_node_instance_non_dynamic_normal = MockRegistry.is_node_instance_non_dynamic_normal
    # is_node_instance_hitl = MockRegistry.is_node_instance_hitl
    # is_node_instance_input = MockRegistry.is_node_instance_input
    # is_node_instance_output = MockRegistry.is_node_instance_output
    # is_node_instance_tool = MockRegistry.is_node_instance_tool

    # --- Internal Cache Helpers --- #

    def _register_node_local(self, node_class: Type[BaseNode]) -> None:
        """Registers a node class in the local _nodes cache."""
        node_name = node_class.node_name
        node_version = node_class.node_version
        if node_name not in self._nodes:
            self._nodes[node_name] = {}
        if node_version in self._nodes[node_name]:
            # This might happen if register_node_template was called multiple times
            # Or if loading from DB overwrites. For now, just overwrite.
            pass
        self._nodes[node_name][node_version] = node_class

    def _register_schema_local(self, schema_class: Type[BaseSchema]) -> None:
        """Registers a schema class in the local _schemas cache."""
        schema_name = getattr(schema_class, "schema_name", None)
        schema_version = getattr(schema_class, "schema_version", None)
        if not schema_name:
            return # Cannot register schema without a name

        if schema_name not in self._schemas:
            self._schemas[schema_name] = {}
        if schema_version in self._schemas[schema_name]:
            pass # Overwrite if already exists
        self._schemas[schema_name][schema_version] = schema_class

