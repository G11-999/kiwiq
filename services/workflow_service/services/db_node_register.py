import asyncio
from db.session import get_async_db_as_manager

from workflow_service.registry.registry import DBRegistry
from workflow_service.registry.nodes.llm.llm_node import LLMNode
from workflow_service.registry.nodes.llm.prompt import PromptConstructorNode
from workflow_service.registry.nodes.core.dynamic_nodes import InputNode, OutputNode, HITLNode  # , DynamicRouterNode
from workflow_service.registry.nodes.core.flow_nodes import (  # flow_nodes_gemini_CURRENT_GOOD  flow_nodes
    FilterNode,
    IfElseConditionNode
)
from workflow_service.registry.nodes.data_ops.transform_node import (
    TransformerNode,
    DataJoinNode,
)
from workflow_service.registry.nodes.core.mapper_node import (
    MapListRouterNode
)
from services.workflow_service.registry.nodes.db.customer_data import (
    LoadCustomerDataNode,
    StoreCustomerDataNode,
)
from workflow_service.registry.nodes.core.router_node import RouterNode

async def register_node_templates(db_registry: DBRegistry):
    async with get_async_db_as_manager() as db:
        # Core Nodes
        await db_registry.register_node_template(db, InputNode)
        await db_registry.register_node_template(db, OutputNode)

        # HITL
        await db_registry.register_node_template(db, HITLNode)
        
        # Flow Nodes
        await db_registry.register_node_template(db, FilterNode)
        await db_registry.register_node_template(db, IfElseConditionNode)
        
        # Routing
        await db_registry.register_node_template(db, RouterNode)
        await db_registry.register_node_template(db, MapListRouterNode)
        
        # Data Ops
        await db_registry.register_node_template(db, TransformerNode)
        await db_registry.register_node_template(db, DataJoinNode)
        
        # Customer / System Data
        await db_registry.register_node_template(db, LoadCustomerDataNode)
        await db_registry.register_node_template(db, StoreCustomerDataNode)
        
        # LLM
        await db_registry.register_node_template(db, LLMNode)
        await db_registry.register_node_template(db, PromptConstructorNode)
        # print("metadata keys:: ", db_registry._metadata.keys())

# if __name__ == "__main__":
#     from kiwi_app.workflow_app import crud as wf_crud
    
#     node_template_dao =  wf_crud.NodeTemplateDAO()
#     workflow_dao = wf_crud.WorkflowDAO()
#     workflow_run_dao = wf_crud.WorkflowRunDAO()
#     prompt_template_dao = wf_crud.PromptTemplateDAO()
#     schema_template_dao = wf_crud.SchemaTemplateDAO()
#     user_notification_dao = wf_crud.UserNotificationDAO()
#     hitl_job_dao = wf_crud.HITLJobDAO()

#     db_registry = DBRegistry(
#         node_template_dao = node_template_dao,
#         schema_template_dao = schema_template_dao,
#         prompt_template_dao = prompt_template_dao,
#         workflow_dao = workflow_dao,
#     )
#     asyncio.run(register_node_templates(db_registry))
