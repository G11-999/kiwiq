"""
Natural Language Document Editing Prompts and Schemas

This module contains all prompts and schemas used in the natural language document editing workflow.
It supports document operations through natural language commands with human-in-the-loop approval.
"""

from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


DOCUMENTS_KEY_TO_DOCUMENT_CONFIG_MAPPING = """{
  "documents": {
    "user_dna_doc": {
      "docname_template": "user_dna_doc",
      "namespace_template": "user_strategy_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "content_strategy_doc": {
      "docname_template": "content_strategy_doc",
      "namespace_template": "user_strategy_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "user_source_analysis": {
      "docname_template": "user_source_analysis",
      "namespace_template": "user_analysis_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "knowledge_base_analysis": {
      "docname_template": "knowledge_base_analysis",
      "namespace_template": "knowledge_base_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "uploaded_files": {
      "docname_template": "",
      "namespace_template": "uploaded_files_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "core_beliefs_perspectives_doc": {
      "docname_template": "core_beliefs_perspectives_doc",
      "namespace_template": "user_inputs_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "content_pillars_doc": {
      "docname_template": "content_pillars_doc",
      "namespace_template": "user_inputs_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "user_preferences_doc": {
      "docname_template": "user_preferences_doc",
      "namespace_template": "user_inputs_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "content_analysis_doc": {
      "docname_template": "content_analysis_doc",
      "namespace_template": "user_analysis_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "linkedin_scraped_profile_doc": {
      "docname_template": "linkedin_scraped_profile_doc",
      "namespace_template": "scraping_results_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "linkedin_scraped_posts_doc": {
      "docname_template": "linkedin_scraped_posts_doc",
      "namespace_template": "scraping_results_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "brief": {
      "docname_template": "brief_{_uuid_}",
      "namespace_template": "content_briefs_{entity_username}",
      "docname_template_vars": {"_uuid_": null},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "concept": {
      "docname_template": "concept_{_uuid_}",
      "namespace_template": "content_concepts_{entity_username}",
      "docname_template_vars": {"_uuid_": null},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "draft": {
      "docname_template": "draft_{post_uuid}",
      "namespace_template": "post_drafts_{entity_username}",
      "docname_template_vars": {"post_uuid": null},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "idea": {
        "docname_template": "idea_{_uuid_}",
        "namespace_template": "content_ideas_{entity_username}",
        "docname_template_vars": {"_uuid_": null},
        "namespace_template_vars": {"entity_username": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
	},
	"writing_style": {
        "docname_template": "writing_style_posts_doc",
        "namespace_template": "user_inputs_{entity_username}",
        "docname_template_vars": {},
        "namespace_template_vars": {"entity_username": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
	},
}
"""

# System prompts for different stages of the workflow
DOCUMENT_EDITING_SYSTEM_PROMPT = """You are an expert document management assistant. You help users answer questions (about their documents or with context from their documents), manage and edit their documents through natural language commands.
Only use the tools to address the user's relevant request about their documents or QA which could be answered with context from their documents.

You have access to the following document tools:
1. view_documents - View content of specific documents
2. search_documents - Search for documents by text queries via hybrid (keyword + vector) search with metadata prefiltering
3. list_documents - List available documents, filtered by metadata e.g. documents in a namespace
4. edit_document - Edit document content (requires user approval - the request will be routed to the user for approval)

## IMPORTANT GUIDELINES:
- Be specific about which documents you're accessing or modifying
- If the user's request is unclear or ambiguous, ask for clarification using the structured output schema.
- You can chain / parallelize multiple tool calls to complete complex requests
- Keep track of the context from previous operations
- When referencing documents from tool call outputs, use the document serial numbers (e.g., 'brief_78_1', 'concept_23_2')

When you need to:
- End the workflow: Set workflow_control.action to "end_workflow". If the user's request is irrelevant, you may instead inform the user and ask for clarification.
- Ask for clarification: Set workflow_control.action to "ask_clarification" and provide the question in workflow_control.clarification_prompt

Current view context and state will be provided to help you understand what documents are currently being viewed or edited.

## Guidelines:
- If user denied tools: Understand why and adjust your approach
- If user provided clarification: Use the new information to better fulfill their request

## Tool Call Output -- aka View Context Format:
The view context contains a mapping of document serial numbers to document information. For example:
- 'brief_78_1': indicates the first brief document in the current view
- 'concept_23_2': indicates the second concept document in the current view

When referencing documents from the tool call outputs, you may use the document serial numbers in your tool calls to reference the documents.

## Structured Output Schema:
{workflow_control_schema}

## Document Config Mapping:

- NOTE: documents can be either high cardinality or unitary, i.e. single document per documet class / key or multiple documents per class / key. Any document in config which has uuid or post_uuid placeholder in docname template is high cardinality.
- keys are doc keys and values are document configs
{document_config_mapping}

## All Document Schemas for reference while editing / fetching information from documents:
{all_document_schemas}
"""


DOCUMENT_EDITING_USER_PROMPT_TEMPLATE = """User Request: {user_request}
"""


class SelectionDecision(str, Enum):
    """Enum representing possible decisions after concept evaluation."""
    END_WORKFLOW = "end_workflow"      # Select the highest scoring concept
    ASK_CLARIFICATION = "ask_clarification"  # All concepts below threshold, need new ones


# Schemas for structured outputs
class WorkflowControlSchema(BaseModel):
    """Schema for LLM workflow control decisions."""
    reason: str = Field(
        ...,
        description="Reason for the chosen action"
    )
    action: SelectionDecision = Field(
        ..., 
        description="Action to take: 'end_workflow', 'ask_clarification'"
    )
    clarification_prompt: Optional[str] = Field(
        None,
        description="Question to ask the user if action is 'ask_clarification'"
    )

WORKFLOW_CONTROL_SCHEMA = WorkflowControlSchema.model_json_schema()
