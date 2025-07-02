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
from workflow_service.registry.nodes.data_ops.merge_aggregate_node import (
    MergeAggregateNode
)
from workflow_service.registry.nodes.core.map_list_router_node import (
    MapListRouterNode
)
from services.workflow_service.registry.nodes.db.customer_data import (
    LoadCustomerDataNode,
    StoreCustomerDataNode,
)
from services.workflow_service.registry.nodes.db.load_multiple_customer_node import (
    LoadMultipleCustomerDataNode,
)
from workflow_service.registry.nodes.core.router_node import RouterNode
from workflow_service.registry.nodes.scraping.linkedin_scraping import LinkedInScrapingNode
from workflow_service.registry.nodes.tools.tool_executor_node import ToolExecutorNode

from services.workflow_service.registry.nodes.tools.documents.document_crud_tools import (
    DocumentViewerTool,
    EditDocumentTool,
    DocumentSearchTool,
    ListDocumentsTool,
)

async def register_node_templates(db_registry: DBRegistry):
    node_classes = [
        # Core Nodes
        InputNode,
        OutputNode,
        # HITL
        HITLNode,
        # Flow Nodes
        FilterNode,
        IfElseConditionNode,
        # Routing
        RouterNode,
        MapListRouterNode,
        # Data Ops
        TransformerNode,
        DataJoinNode,
        MergeAggregateNode,
        # Customer / System Data
        LoadCustomerDataNode,
        StoreCustomerDataNode,
        LoadMultipleCustomerDataNode,
        # LLM
        LLMNode,
        PromptConstructorNode,
        # Tools
        ToolExecutorNode,
        # Scraping
        LinkedInScrapingNode,
        # Document CRUD Tools
        DocumentViewerTool,
        EditDocumentTool,
        DocumentSearchTool,
        ListDocumentsTool,
    ]
    # assert None of the classes have duplicate node_names i.e. node types!
    assert len(set(node.node_name for node in node_classes)) == len(node_classes)
    async with get_async_db_as_manager() as db:
        for node in node_classes:
            await db_registry.register_node_template(db, node)
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
