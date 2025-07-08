
from typing import Tuple, Type
import uuid
import random

from pydantic import BaseModel
from workflow_service.config.constants import HITL_NODE_NAME_PREFIX, STATE_KEY_DELIMITER, INPUT_NODE_NAME, OUTPUT_NODE_NAME, GRAPH_STATE_SPECIAL_NODE_NAME

from global_config.logger import get_logger
from global_config.settings import global_settings
from global_utils.utils import datetime_now_utc

prefect_logger = None

def init_prefect_logger():
    global prefect_logger
    if prefect_logger is None:
        # prefect_logger = 
        return get_logger(
            name="workflow_service",
            # log_level=global_settings.LOG_LEVEL,
            # log_filename=global_settings.LOG_PREFECT_FILE_NAME,  #  + f".{datetime_now_utc()}.{random.randint(0, 100)}",
            # log_to_file=True,
        )
    return prefect_logger

def get_prefect_logger():
    global prefect_logger
    if prefect_logger is None:
        init_prefect_logger()
    return prefect_logger


# def is_non_dynamic_normal_node(node_name: str) -> bool:
#     return not (is_central_state_special_node(node_name) or is_dynamic_node(node_name))

# def is_hitl_node(node_name: str) -> bool:
#     return node_name.startswith(HITL_NODE_NAME_PREFIX)

# def is_dynamic_node(node_name: str) -> bool:
#     return (node_name in [INPUT_NODE_NAME, OUTPUT_NODE_NAME]) or is_hitl_node(node_name)

# def is_central_state_special_node(node_name_or_id: str) -> bool:
#     return node_name_or_id == GRAPH_STATE_SPECIAL_NODE_NAME

# def get_node_name_and_snno_from_id(node_name: str) -> Tuple[str, str]:
#     return node_name.split(STATE_KEY_DELIMITER)

def get_central_state_field_key(field_name: str) -> str:
    return STATE_KEY_DELIMITER.join([GRAPH_STATE_SPECIAL_NODE_NAME, field_name])

def get_node_output_state_key(node_id: str) -> str:
    return STATE_KEY_DELIMITER.join([node_id, "output"])

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
