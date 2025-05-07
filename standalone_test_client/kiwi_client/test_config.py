import os
import uuid
import logging
from pydantic import BaseModel
from typing import List, Optional

from kiwi_client.schemas.graph_schema import GraphSchema

from dotenv import load_dotenv

# NOTE: set the below vars in your .env to load automatically: TEST_ENV, TEST_USER_EMAIL, TEST_USER_PASSWORD, TEST_ORG_ID
load_dotenv()

# --- Configuration ---
# Replace with your actual API base URL
BASE_HOST = "http://127.0.0.1:8000" if os.getenv("TEST_ENV") == "local" else "https://api.prod.kiwiq.ai"
API_BASE_URL = f"{BASE_HOST}/api/v1" # Example: http://localhost:8000

# Replace with your test user credentials
TEST_USER_EMAIL = os.getenv("TEST_USER_EMAIL", "admin@example.com")
TEST_USER_PASSWORD = os.getenv("TEST_USER_PASSWORD", "testpass")

# NOTE: Important to also test with regular non-superuser User after registration!
# TEST_USER_EMAIL = "admin@example.com"
# TEST_USER_PASSWORD = "testpass"

# Replace with a valid organization UUID accessible by the test user
# This will be used for the X-Active-Org header
# You might need to register the test user and create/find an org ID first.
TEST_ORG_ID = uuid.UUID(os.getenv("TEST_ORG_ID", "a7e22f23-1829-4f65-b21c-fecab74ef948"))

# --- Standard Headers ---
BASE_HEADERS = {
    "accept": "application/json",
    "Content-Type": "application/json",
}

CLIENT_LOG_LEVEL = logging.INFO

# --- API Endpoints ---
# Define constants for endpoint paths for easier maintenance

# Auth
REGISTER_URL = f"{API_BASE_URL}/auth/register"
LOGIN_URL = f"{API_BASE_URL}/auth/login/token"
REFRESH_URL = f"{API_BASE_URL}/auth/refresh"
REQUEST_VERIFY_EMAIL_URL = f"{API_BASE_URL}/auth/request-verify-email"
VERIFY_EMAIL_URL = f"{API_BASE_URL}/auth/verify-email"
CHANGE_PASSWORD_URL = f"{API_BASE_URL}/auth/users/me/change-password"
REQUEST_PASSWORD_RESET_URL = f"{API_BASE_URL}/auth/request-password-reset"
VERIFY_PASSWORD_RESET_URL = f"{API_BASE_URL}/auth/verify-password-reset-token"
RESET_PASSWORD_URL = f"{API_BASE_URL}/auth/reset-password"
LINKEDIN_LOGIN_URL = f"{API_BASE_URL}/auth/linkedin/login" # Note: Testing OAuth might be complex
LINKEDIN_CALLBACK_URL = f"{API_BASE_URL}/auth/linkedin/callback"
ADMIN_REGISTER_URL = f"{API_BASE_URL}/auth/admin/users/register"

# Users
USERS_ME_URL = f"{API_BASE_URL}/auth/users/me"
USERS_ME_ORGS_URL = f"{API_BASE_URL}/auth/users/me/organizations"

# Orgs
ORGANIZATIONS_URL = f"{API_BASE_URL}/auth/organizations"
ORG_USERS_URL = lambda org_id: f"{ORGANIZATIONS_URL}/{org_id}/users"
ORG_DETAIL_URL = lambda org_id: f"{ORGANIZATIONS_URL}/{org_id}"

# Roles (Admin)
ROLES_URL = f"{API_BASE_URL}/auth/roles"

# Templates
# --- API Endpoint URLs ---
# Construct absolute URLs using the base URL from config
NODE_TEMPLATES_URL = f"{API_BASE_URL}/templates/nodes"
NODE_TEMPLATE_DETAIL_URL = lambda template_id: f"{NODE_TEMPLATES_URL}/{template_id}"

PROMPT_TEMPLATES_URL = f"{API_BASE_URL}/templates/prompts"
PROMPT_TEMPLATE_DETAIL_URL = lambda template_id: f"{PROMPT_TEMPLATES_URL}/{template_id}"
PROMPT_TEMPLATES_SEARCH_URL = f"{PROMPT_TEMPLATES_URL}/search"

SCHEMA_TEMPLATES_URL = f"{API_BASE_URL}/templates/schemas"
SCHEMA_TEMPLATE_DETAIL_URL = lambda template_id: f"{SCHEMA_TEMPLATES_URL}/{template_id}"
SCHEMA_TEMPLATES_SEARCH_URL = f"{SCHEMA_TEMPLATES_URL}/search"


# Workflows
WORKFLOWS_URL = f"{API_BASE_URL}/workflows"
WORKFLOW_DETAIL_URL = lambda workflow_id: f"{WORKFLOWS_URL}/{workflow_id}"
VALIDATE_GRAPH_URL = f"{WORKFLOWS_URL}/validate"

# Runs
RUNS_URL = f"{API_BASE_URL}/runs"
RUN_DETAIL_URL = lambda run_id: f"{RUNS_URL}/{run_id}"
RUN_DETAILS_URL = lambda run_id: f"{RUNS_URL}/{run_id}/details"
RUN_STREAM_URL = lambda run_id: f"{RUNS_URL}/{run_id}/stream"
# RUN_CANCEL_URL = lambda run_id: f"{RUNS_URL}{run_id}/cancel" # If implemented

# Notifications
NOTIFICATIONS_URL = f"{API_BASE_URL}/notifications"
NOTIFICATION_READ_URL = lambda notification_id: f"{NOTIFICATIONS_URL}/{notification_id}/read"
NOTIFICATIONS_READ_ALL_URL = f"{NOTIFICATIONS_URL}/read-all"
NOTIFICATIONS_UNREAD_COUNT_URL = f"{NOTIFICATIONS_URL}/unread-count"

# HITL
HITL_JOBS_URL = f"{API_BASE_URL}/hitl"
HITL_JOB_DETAIL_URL = lambda job_id: f"{HITL_JOBS_URL}/{job_id}"
# HITL_JOB_RESPOND_URL = lambda job_id: f"{HITL_JOBS_URL}{job_id}/respond" # Respond is handled via submitting a run with resume_run_id
HITL_JOB_CANCEL_URL = lambda job_id: f"{HITL_JOBS_URL}/{job_id}/cancel"

# Customer Data
CUSTOMER_DATA_BASE_URL = f"{API_BASE_URL}/customer-data"
VERSIONED_DOC_URL = lambda namespace, docname: f"{CUSTOMER_DATA_BASE_URL}/versioned/{namespace}/{docname}"
VERSIONED_DOC_VERSIONS_URL = lambda namespace, docname: f"{CUSTOMER_DATA_BASE_URL}/versioned/{namespace}/{docname}/versions"
VERSIONED_DOC_ACTIVE_VERSION_URL = lambda namespace, docname: f"{CUSTOMER_DATA_BASE_URL}/versioned/{namespace}/{docname}/active-version"
VERSIONED_DOC_HISTORY_URL = lambda namespace, docname: f"{CUSTOMER_DATA_BASE_URL}/versioned/{namespace}/{docname}/history"
VERSIONED_DOC_PREVIEW_RESTORE_URL = lambda namespace, docname, sequence: f"{CUSTOMER_DATA_BASE_URL}/versioned/{namespace}/{docname}/preview-restore/{sequence}"
VERSIONED_DOC_RESTORE_URL = lambda namespace, docname: f"{CUSTOMER_DATA_BASE_URL}/versioned/{namespace}/{docname}/restore"
VERSIONED_DOC_SCHEMA_URL = lambda namespace, docname: f"{CUSTOMER_DATA_BASE_URL}/versioned/{namespace}/{docname}/schema"
UNVERSIONED_DOC_URL = lambda namespace, docname: f"{CUSTOMER_DATA_BASE_URL}/unversioned/{namespace}/{docname}"
LIST_DOCUMENTS_URL = f"{CUSTOMER_DATA_BASE_URL}/list"
SEARCH_DOCUMENTS_URL = f"{CUSTOMER_DATA_BASE_URL}/search"
DOCUMENT_METADATA_URL = lambda namespace, docname: f"{CUSTOMER_DATA_BASE_URL}/metadata/{namespace}/{docname}"
VERSIONED_DOC_UPSERT_URL = lambda namespace, docname: f"{CUSTOMER_DATA_BASE_URL}/versioned/{namespace}/{docname}/upsert"

# WebSockets (Base URLs - specific paths depend on run_id etc.)
# Note: httpx doesn't handle cookies automatically for websockets in the same way
#       as HTTP requests. Token needs to be passed manually if required by endpoint.
WS_RUN_BASE_URL = API_BASE_URL.replace("http", "ws") + "/ws/runs"
WS_NOTIFICATIONS_URL = API_BASE_URL.replace("http", "ws") + "/ws/notifications"

# --- URL Definitions ---
# These should ideally come from test_config.py or a shared configuration module.
# For demonstration, they are constructed here.
# Ensure BASE_API_URL is correctly defined in your kiwi_client.test_config
_USER_STATE_API_ROOT = f"{API_BASE_URL}/app-state"
USER_STATE_INITIALIZE_URL = _USER_STATE_API_ROOT
USER_STATE_LIST_DOCUMENTS_URL = f"{_USER_STATE_API_ROOT}/list"
USER_STATE_ACTIVE_DOCNAMES_URL = f"{_USER_STATE_API_ROOT}/active-docnames"
USER_STATE_DETAIL_URL = lambda docname: f"{_USER_STATE_API_ROOT}/{docname}"


# App Artifacts (Workflow App)
_APP_ARTIFACT_API_ROOT = f"{API_BASE_URL}/app-artifacts"
APP_ARTIFACT_GET_WORKFLOW_URL = f"{_APP_ARTIFACT_API_ROOT}/get-workflow"
APP_ARTIFACT_DOC_CONFIGS_URL = f"{_APP_ARTIFACT_API_ROOT}/doc-configs"


# # Example Graph Schema (from test_worker_job.py's basic LLM graph)
# # You might want to define more complex examples or load from files
# class LLMConfig(BaseModel):
#     """Configuration specific to an LLM node."""
#     model_provider: str = "anthropic"
#     model_name: str = "claude-3-5-sonnet-20240620" # Use a valid model enum if available
#     temperature: float = 0.7
#     max_tokens: int = 100
#     output_type: str = "text" # or "json"
#     system_prompt: Optional[str] = None

# class NodeConfig(BaseModel):
#     """Represents configuration for a single node in the graph."""
#     node_type: str # Matches the registered node template name
#     node_name: str # Unique identifier within this graph
#     node_config: LLMConfig # Specific config depends on node_type
#     # Example: node_config: Union[LLMConfig, OtherNodeConfig]

# class EdgeConfig(BaseModel):
#     """Represents a connection between two nodes."""
#     source_node: str # node_name of the source
#     target_node: str # node_name of the target
#     # Optional: specify source/target handles if nodes have multiple outputs/inputs
#     # source_handle: Optional[str] = None
#     # target_handle: Optional[str] = None
#     # Optional: Condition for conditional edges
#     # condition: Optional[str] = None

# class GraphSchema(BaseModel):
#     """Represents the structure and configuration of a workflow graph."""
#     nodes: List[NodeConfig]
#     edges: List[EdgeConfig]
#     start_node: str # node_name of the entry point node
#     # Optional: Global graph configuration (e.g., timeouts, retry strategies)
#     # config: Optional[Dict[str, Any]] = None



# from tests.unit.services.workflow_service.graph.runtime.tests.test_AI_loop import create_ai_loop_graph, human_review_handler, HumanReviewNode, AIGeneratorNode, ApprovalRouterNode, FinalProcessorNode
# from workflow_service.registry.nodes.llm.tests.test_basic_llm_workflow import create_basic_llm_graph
# test_graph_schema: GraphSchema = create_ai_loop_graph()
# test_graph_schema: GraphSchema = create_basic_llm_graph(
#     model_provider=LLMModelProvider.ANTHROPIC,
#     model_name=AnthropicModels.CLAUDE_3_7_SONNET.value,
#     output_type="text"
# )

# print(test_graph_schema.model_dump_json(indent=4))


EXAMPLE_BASIC_LLM_GRAPH_CONFIG = {
    "nodes": {
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_version": None,
            "node_config": {},
            "dynamic_input_schema": None,
            "dynamic_output_schema": None,
            "dynamic_config_schema": None,
            "enable_dynamic_fields_from_edges": True,
            "enable_node_fan_in": False
        },
        "llm_node": {
            "node_id": "llm_node",
            "node_name": "llm",
            "node_version": None,
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": "anthropic",
                        "model": "claude-3-7-sonnet-20250219"
                    },
                    "max_tokens": 100,
                    "temperature": 0.0,
                    "force_temperature_setting_when_thinking": False,
                    "reasoning_effort_class": None,
                    "reasoning_effort_number": None,
                    "reasoning_tokens_budget": None,
                    "kwargs": None
                },
                "default_system_prompt": None,
                "thinking_tokens_in_prompt": "all",
                "api_key_override": None,
                "cache_responses": True,
                "output_schema": {
                    "schema_from_registry": None,
                    "dynamic_schema_spec": None
                },
                "stream": True,
                "tool_calling_config": {
                    "enable_tool_calling": False,
                    "tool_choice": None,
                    "parallel_tool_calls": True
                },
                "tools": None,
                "web_search_options": None
            },
            "dynamic_input_schema": None,
            "dynamic_output_schema": None,
            "dynamic_config_schema": None,
            "enable_dynamic_fields_from_edges": True,
            "enable_node_fan_in": False
        },
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_version": None,
            "node_config": {},
            "dynamic_input_schema": None,
            "dynamic_output_schema": None,
            "dynamic_config_schema": None,
            "enable_dynamic_fields_from_edges": True,
            "enable_node_fan_in": False
        }
    },
    "edges": [
        {
            "src_node_id": "input_node",
            "dst_node_id": "llm_node",
            "mappings": [
                {
                    "src_field": "user_prompt",
                    "dst_field": "user_prompt",
                    "override_type_validation": False
                },
                {
                    "src_field": "messages_history",
                    "dst_field": "messages_history",
                    "override_type_validation": False
                },
                {
                    "src_field": "system_prompt",
                    "dst_field": "system_prompt",
                    "override_type_validation": False
                }
            ]
        },
        {
            "src_node_id": "llm_node",
            "dst_node_id": "output_node",
            "mappings": [
                {
                    "src_field": "structured_output",
                    "dst_field": "structured_output",
                    "override_type_validation": False
                },
                {
                    "src_field": "metadata",
                    "dst_field": "metadata",
                    "override_type_validation": False
                },
                {
                    "src_field": "current_messages",
                    "dst_field": "current_messages",
                    "override_type_validation": False
                },
                {
                    "src_field": "content",
                    "dst_field": "content",
                    "override_type_validation": False
                },
                {
                    "src_field": "web_search_result",
                    "dst_field": "web_search_result",
                    "override_type_validation": False
                }
            ]
        }
    ],
    "input_node_id": "input_node",
    "output_node_id": "output_node",
    "metadata": {}
}

EXAMPLE_BASIC_LLM_RUN_INPUTS = {
    "user_prompt": "Write a very short poem about a cloud."
} 

