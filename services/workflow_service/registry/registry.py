"""
Registry for workflow nodes.

This module provides a registry for all available node types in the workflow system.
The registry allows nodes to be looked up by name and version, and provides
functionality for registering new nodes.
"""
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel

from workflow_service.config.constants import GRAPH_STATE_SPECIAL_NODE_NAME, HITL_NODE_NAME_PREFIX
from workflow_service.registry.nodes.core.base import BaseNode
from workflow_service.registry.nodes.core.dynamic_nodes import InputNode, OutputNode, DynamicRouterNode, HITLNode
# from workflow_service.registry.nodes.core.hitl_node import HITLNode
# from workflow_service.registry.nodes.core.flow_nodes import FilterNode, IfElseNode
# from workflow_service.registry.nodes.core.join_node import JoinNode
# from workflow_service.registry.nodes.ai.openai_node import OpenAINode


def is_central_state_special_node(node_name_or_id: str) -> bool:
    """
    Check if a node is the central state special node.
    
    Args:
        node_name_or_id (str): Name or ID of the node to check
        
    Returns:
        bool: True if the node is the central state special node, False otherwise
    """
    return node_name_or_id == GRAPH_STATE_SPECIAL_NODE_NAME

def is_dynamic_schema_node(schema_cls: Type[BaseModel]) -> bool:
    """
    Check if a node is a dynamic schema node.
    """
    return (hasattr(schema_cls, 'IS_DYNAMIC_SCHEMA') and 
            getattr(schema_cls, 'IS_DYNAMIC_SCHEMA', False))


class MockRegistry:
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
            "is_dynamic": MockRegistry.is_node_instance_dynamic(node_class),
            "is_router": MockRegistry.is_node_instance_router(node_class), 
            "is_hitl": MockRegistry.is_node_instance_hitl(node_class),
            "is_input": MockRegistry.is_node_instance_input(node_class),
            "is_output": MockRegistry.is_node_instance_output(node_class),
            # NOTE: has subnodes can be different across version to version!
            # "has_subnodes": node_class.has_subnodes
        }
        if not self._metadata[node_name]:
            self._metadata[node_name] = metadata_dict
        else:
            assert self._metadata[node_name] == metadata_dict, "Metadata for node must be the same for all versions!"
        
    def get_node(self, node_name: str, version: Optional[str] = None) -> Type[BaseNode]:
        """
        Get a node class from the registry.
        
        Args:
            node_name (str): Name of node to get
            version (Optional[str]): Version of node to get. If None, returns latest version.
            
        Returns:
            Type[BaseNode]: The requested node class
            
        Raises:
            ValueError: If node name or version not found
        """
        # Check node exists
        if node_name not in self._nodes:
            raise ValueError(f"Node {node_name} not found in registry")
            
        # Get latest version if none specified
        if version is None:
            version = max(self._nodes[node_name].keys())
        # Check version exists    
        elif version not in self._nodes[node_name]:
            raise ValueError(f"Version {version} not found for node {node_name}")
            
        return self._nodes[node_name][version]
    
    
    
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
            raise ValueError(f"Node {node_name} not found in registry")
        
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
        return self._metadata[node_name].get("is_hitl", False)
    
    def is_input_node(self, node_name: str) -> bool:
        """
        Check if a node is an input node.
        """
        return self._metadata[node_name].get("is_input", False)
    
    def is_output_node(self, node_name: str) -> bool:
        """
        Check if a node is an output node.
        """
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
        return getattr(node_class, "dynamic_schemas", False)
    
    
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


class NodeRegistry:
    """
    Registry for workflow nodes.
    
    This class maintains a registry of all available node types in the workflow system.
    It provides methods for registering new nodes and looking up nodes by name and version.
    
    Attributes:
        _nodes (Dict[str, Dict[str, Type[BaseNode]]]): Mapping of node names and versions to node classes.
    """
    
    def __init__(self):
        """Initialize the node registry."""
        self._nodes: Dict[str, Dict[str, Type[BaseNode]]] = {}
        
        # Register all built-in nodes
        self._register_builtin_nodes()
    
    def _register_builtin_nodes(self):
        """Register all built-in node types."""
        # Register core nodes
        self.register_node(FilterNode)
        self.register_node(IfElseNode)
        self.register_node(JoinNode)
        
        # Register AI nodes
        self.register_node(OpenAINode)
        
        # Note: InputNode, OutputNode, and HITLNode are handled specially
        # during graph building, so they don't need to be in the main registry
    
    def register_node(self, node_class: Type[BaseNode]) -> None:
        """
        Register a node class in the registry.
        
        Args:
            node_class (Type[BaseNode]): The node class to register.
            
        Raises:
            ValueError: If a node with the same name and version is already registered.
        """
        node_name = node_class.node_name
        node_version = node_class.node_version
        
        # Initialize version dict if this is the first version of this node
        if node_name not in self._nodes:
            self._nodes[node_name] = {}
        
        # Check if this version is already registered
        if node_version in self._nodes[node_name]:
            raise ValueError(f"Node {node_name} version {node_version} already registered")
        
        # Register the node
        self._nodes[node_name][node_version] = node_class
    
    def get_node(self, node_name: str, version: Optional[str] = None) -> Type[BaseNode]:
        """
        Get a node class from the registry.
        
        Args:
            node_name (str): The name of the node to get.
            version (Optional[str]): The version of the node to get.
                If not provided, the latest version will be returned.
                
        Returns:
            Type[BaseNode]: The requested node class.
            
        Raises:
            ValueError: If the node or version is not found.
        """
        # Check if the node exists
        if node_name not in self._nodes:
            raise ValueError(f"Node {node_name} not found in registry")
        
        # If no version is provided, get the latest version
        if version is None:
            # Get the latest version (assuming semantic versioning)
            versions = sorted(self._nodes[node_name].keys())
            if not versions:
                raise ValueError(f"No versions found for node {node_name}")
            version = versions[-1]
        
        # Check if the version exists
        if version not in self._nodes[node_name]:
            raise ValueError(f"Version {version} of node {node_name} not found in registry")
        
        # Return the node class
        return self._nodes[node_name][version]
    
    def list_nodes(self) -> List[Dict[str, Any]]:
        """
        List all registered nodes.
        
        Returns:
            List[Dict[str, Any]]: List of registered nodes, each with name and versions.
        """
        result = []
        for node_name, versions in self._nodes.items():
            node_info = {
                "name": node_name,
                "versions": list(versions.keys())
            }
            result.append(node_info)
        return result
    
    def get_registry_dict(self) -> Dict[str, Type[BaseNode]]:
        """
        Get a flattened dictionary of all registered nodes.
        
        Returns:
            Dict[str, Type[BaseNode]]: Mapping of node names to the latest version of each node class.
        """
        result = {}
        for node_name, versions in self._nodes.items():
            # Get the latest version
            latest_version = sorted(versions.keys())[-1]
            result[node_name] = versions[latest_version]
        return result


# Create a global instance of the registry
# node_registry = NodeRegistry()
