from openai import AsyncOpenAI
"""
Natural Language Document Editing Prompts and Schemas

This module contains all prompts and schemas used in the natural language document editing workflow.
It supports document operations through natural language commands with human-in-the-loop approval.
"""
import json
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, create_model
from pydantic.fields import FieldInfo
from typing import List, Optional, Dict, Any


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



client = AsyncOpenAI()


from workflow_service.registry.nodes.tools.documents.document_crud_tools import ListDocumentsInputSchema, DocumentSearchInputSchema, EditDocumentInputSchema, DocumentViewerInputSchema
from workflow_service.registry.nodes.llm.llm_node import LLMStructuredOutputSchema
from standalone_test_client.kiwi_client.workflows.llm_inputs.natural_language_editing import DOCUMENT_EDITING_SYSTEM_PROMPT, DOCUMENT_EDITING_USER_PROMPT_TEMPLATE, WORKFLOW_CONTROL_SCHEMA, DOCUMENTS_KEY_TO_DOCUMENT_CONFIG_MAPPING
from standalone_test_client.kiwi_client.workflows.llm_inputs.natural_language_editing_all_schemas import ALL_DOCUMENT_SCHEMAS
from workflow_service.registry.schemas.base import BaseSchema, BaseNodeConfig



def create_tool_for_binding(input_schema, tool_name):
    field_definitions = {}
    for k,v in input_schema.model_fields.items():
        if BaseSchema._is_field_for_llm_tool_call(v):
            # Create a new FieldInfo with default removed and is_required set to True
            # This ensures LLM tools see all fields as required for proper tool calling
            modified_field = v
            # NOTE: hack for openai schemas since they don't support default, etc
                # modified_field = copy(v)
                # modified_field.default = PydanticUndefined  # Remove any default value
                # modified_field.default_factory = PydanticUndefined  # Mark as required for LLM tool calls

            annotation = v.annotation
            # origin = get_origin(v.annotation)
            # if origin is Union and any(arg is None for arg in get_args(v.annotation)):
            #     annotation = [arg for arg in get_args(v.annotation) if arg is not None][0]
            
            # modified_field = FieldInfo(
            #     # Don't pass any default value - this makes the field required
            #     annotation=annotation,
            #     description=v.description,
            #     title=v.title,
            #     examples=v.examples,
            #     json_schema_extra=v.json_schema_extra,
            #     metadata=v.metadata,
            #     # Explicitly exclude default and default_factory to make field required
            #     # All other field properties are preserved
            # )
            

            field_definitions[k] = (v.annotation, modified_field)

    tool_for_binding = create_model(
        tool_name,
        __base__=(BaseNodeConfig),
        __doc__=input_schema.__doc__,
        __module__=input_schema.__module__,  # module_name or 
        # Only bind user editable fields, hide other fields!
        **field_definitions
    )
    return tool_for_binding






async def main():
    tools = [ListDocumentsInputSchema  
             
             , DocumentSearchInputSchema, EditDocumentInputSchema, DocumentViewerInputSchema
             ]
    openai_tools = []
    for tool in tools:
        tool_for_binding = create_tool_for_binding(tool, tool.__name__)
        json_schema = LLMStructuredOutputSchema._recursive_set_json_schema_to_openai_format(tool_for_binding.model_json_schema())
        # print(json.dumps(json_schema, indent=4))
        # import ipdb; ipdb.set_trace()
        json_schema["additionalProperties"] = False
        openai_tools.append({
            "name": tool_for_binding.__name__,
            "parameters": json_schema,
            "strict": True,
            "type": "function",
            "description": tool_for_binding.__doc__,
        })
    buffer = None
    final_tool_calls = {}
    async with client.responses.stream(
        model="o4-mini",  # o4-mini   gpt-4.1
        # developer  system
        input=[ {"role": "developer", "content": DOCUMENT_EDITING_SYSTEM_PROMPT.format(all_document_schemas=ALL_DOCUMENT_SCHEMAS, document_config_mapping=DOCUMENTS_KEY_TO_DOCUMENT_CONFIG_MAPPING, workflow_control_schema=WORKFLOW_CONTROL_SCHEMA)}, 
               {"role": "user", "content": DOCUMENT_EDITING_USER_PROMPT_TEMPLATE.format(user_request="Help me edit content strategy doc and add marketing related sections")}],
        tools=openai_tools,
        text_format=WorkflowControlSchema,
        # stream=True
    ) as stream:
        async for event in stream:
            print(event)
            if event.type == 'response.output_item.added':
                final_tool_calls[event.output_index] = event.item
            elif event.type == 'response.function_call_arguments.delta':
                index = event.output_index

                if final_tool_calls[index]:
                    final_tool_calls[index].arguments += event.delta
            
            # if event.type == "response.refusal.delta":
            #     print(event.delta, end="")
            # elif event.type == "response.output_text.delta":
            #     print(event.delta, end="")
            # elif event.type == "response.error":
            #     print(event.error, end="")
            # elif event.type == "response.completed":
            #     print("Completed")
            #     # print(event.response.output)
    
    final_response = await stream.get_final_response()
    print(final_response)
    print(final_tool_calls)
    import ipdb; ipdb.set_trace()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())


"""
{
    "$defs": {
        "DocumentListFilter": {
            "description": "Combined schema for listing and filtering documents.\nMust provide either doc_key OR namespace_of_doc_key (not both).",
            "properties": {
                "doc_key": {
                    "description": "Filter by specific doc key",
                    "title": "Doc Key",
                    "type": "string"
                },
                "namespace_of_doc_key": {
                    "anyOf": [
                        {
                            "type": "string"
                        },
                        {
                            "type": "null"
                        }
                    ],
                    "default": null,
                    "description": "Mention the doc key whose namespace will be used for filtering. This will automatically resolve the correct namespace including template vars, given the correct doc key.",
                    "title": "Namespace Of Doc Key"
                },
                "scheduled_date_range_start": {
                    "anyOf": [
                        {
                            "format": "date-time",
                            "type": "string"
                        },
                        {
                            "type": "null"
                        }
                    ],
                    "default": null,
                    "description": "Filter docs scheduled after this date (YYYY-MM-DDTHH:MM:SSZ UTC format)",
                    "title": "Scheduled Date Range Start"
                },
                "scheduled_date_range_end": {
                    "anyOf": [
                        {
                            "format": "date-time",
                            "type": "string"
                        },
                        {
                            "type": "null"
                        }
                    ],
                    "default": null,
                    "description": "Filter docs scheduled before this date (YYYY-MM-DDTHH:MM:SSZ UTC format)",
                    "title": "Scheduled Date Range End"
                },
                "created_at_range_start": {
                    "anyOf": [
                        {
                            "format": "date-time",
                            "type": "string"
                        },
                        {
                            "type": "null"
                        }
                    ],
                    "default": null,
                    "description": "Filter docs created after this date (YYYY-MM-DDTHH:MM:SSZ UTC format)",
                    "title": "Created At Range Start"
                },
                "created_at_range_end": {
                    "anyOf": [
                        {
                            "format": "date-time",
                            "type": "string"
                        },
                        {
                            "type": "null"
                        }
                    ],
                    "default": null,
                    "description": "Filter docs created before this date (YYYY-MM-DDTHH:MM:SSZ UTC format)",
                    "title": "Created At Range End"
                }
            },
            "required": [
                "doc_key",
                "namespace_of_doc_key",
                "scheduled_date_range_start",
                "scheduled_date_range_end",
                "created_at_range_start",
                "created_at_range_end"
            ],
            "title": "DocumentListFilter",
            "type": "object",
            "additionalProperties": false
        }
    },
    "additionalProperties": false,
    "description": "Input schema for the ListDocumentsTool.\n\nThis tool lists documents based on filter criteria, returning metadata only (not full content).\nIt's designed for browsing and discovering documents when you don't know exact names.\n\nRequired Field:\n- 'list_filter': Defines what documents to list\n\nFilter Options:\nThe 'list_filter' must include one of these:\n- 'doc_key': List all documents of a specific type (e.g., 'brief', 'concept', 'idea')\n- 'namespace_of_doc_key': List all documents in a namespace (e.g., all docs in the 'concept' namespace)\n\nOptional Filters:\n- Date ranges: Filter by scheduled dates or creation dates\n  * scheduled_date_range_start/end: For time-sensitive docs like briefs\n  * created_at_range_start/end: Filter by when documents were created\n\nPagination:\n- 'limit': Number of documents to return (1-10, default 10)\n- 'offset': Skip documents for pagination\n\nCommon Use Cases:\n1. List all briefs:\n   list_filter: {doc_key: \"brief\"}\n\n2. List recent concepts:\n   list_filter: {doc_key: \"concept\", created_at_range_start: \"2024-01-01T00:00:00Z\"}\n\n3. List concepts with pagination:\n   list_filter: {doc_key: \"concept\"}\n   limit: 5\n   offset: 10\n\n4. List all documents in concept namespace (includes shared docs):\n   list_filter: {namespace_of_doc_key: \"concept\"}\n\n5. List scheduled briefs for next week:\n   list_filter: {\n     doc_key: \"brief\",\n     scheduled_date_range_start: \"2024-01-15T00:00:00Z\",\n     scheduled_date_range_end: \"2024-01-22T00:00:00Z\"\n   }\n\nNotes:\n- Returns document metadata only, not full content (use view_documents for full content)\n- Results include both user-specific and shared documents\n- Pagination may not be 100% accurate due to versioning metadata documents being filtered out\n- Dates should be in ISO format: YYYY-MM-DDTHH:MM:SSZ",
    "properties": {
        "list_filter": {
            "$ref": "#/$defs/DocumentListFilter"
        },
        "limit": {
            "description": "Maximum number of documents to list (1-10, default 10). Use smaller values for quick browsing, larger for comprehensive lists.",
            "title": "Limit",
            "type": "integer"
        },
        "offset": {
            "description": "Number of documents to skip for pagination. Use 0 for first page, then increment by 'limit' for subsequent pages.",
            "title": "Offset",
            "type": "integer"
        }
    },
    "required": [
        "list_filter",
        "limit",
        "offset"
    ],
    "title": "ListDocumentsInputSchema",
    "type": "object"
}
    


{
    "$defs": {
        "DocumentListFilter": {
            "description": "Combined schema for listing and filtering documents.\nMust provide either doc_key OR namespace_of_doc_key (not both).",
            "properties": {
                "doc_key": {
                    "anyOf": [
                        {
                            "type": "string"
                        },
                        {
                            "type": "null"
                        }
                    ],
                    "default": null,
                    "description": "Filter by specific doc key",
                    "title": "Doc Key"
                },
                "namespace_of_doc_key": {
                    "anyOf": [
                        {
                            "type": "string"
                        },
                        {
                            "type": "null"
                        }
                    ],
                    "default": null,
                    "description": "Mention the doc key whose namespace will be used for filtering. This will automatically resolve the correct namespace including template vars, given the correct doc key.",
                    "title": "Namespace Of Doc Key"
                },
                "scheduled_date_range_start": {
                    "anyOf": [
                        {
                            "format": "date-time",
                            "type": "string"
                        },
                        {
                            "type": "null"
                        }
                    ],
                    "default": null,
                    "description": "Filter docs scheduled after this date (YYYY-MM-DDTHH:MM:SSZ UTC format)",
                    "title": "Scheduled Date Range Start"
                },
                "scheduled_date_range_end": {
                    "anyOf": [
                        {
                            "format": "date-time",
                            "type": "string"
                        },
                        {
                            "type": "null"
                        }
                    ],
                    "default": null,
                    "description": "Filter docs scheduled before this date (YYYY-MM-DDTHH:MM:SSZ UTC format)",
                    "title": "Scheduled Date Range End"
                },
                "created_at_range_start": {
                    "anyOf": [
                        {
                            "format": "date-time",
                            "type": "string"
                        },
                        {
                            "type": "null"
                        }
                    ],
                    "default": null,
                    "description": "Filter docs created after this date (YYYY-MM-DDTHH:MM:SSZ UTC format)",
                    "title": "Created At Range Start"
                },
                "created_at_range_end": {
                    "anyOf": [
                        {
                            "format": "date-time",
                            "type": "string"
                        },
                        {
                            "type": "null"
                        }
                    ],
                    "default": null,
                    "description": "Filter docs created before this date (YYYY-MM-DDTHH:MM:SSZ UTC format)",
                    "title": "Created At Range End"
                }
            },
            "title": "DocumentListFilter",
            "type": "object",
            "required": [
                "doc_key",
                "namespace_of_doc_key",
                "scheduled_date_range_start",
                "scheduled_date_range_end",
                "created_at_range_start",
                "created_at_range_end"
            ]
        }
    },
    "additionalProperties": false,
    "description": "Input schema for the ListDocumentsTool.\n\nThis tool lists documents based on filter criteria, returning metadata only (not full content).\nIt's designed for browsing and discovering documents when you don't know exact names.\n\nRequired Field:\n- 'list_filter': Defines what documents to list\n\nFilter Options:\nThe 'list_filter' must include one of these:\n- 'doc_key': List all documents of a specific type (e.g., 'brief', 'concept', 'idea')\n- 'namespace_of_doc_key': List all documents in a namespace (e.g., all docs in the 'concept' namespace)\n\nOptional Filters:\n- Date ranges: Filter by scheduled dates or creation dates\n  * scheduled_date_range_start/end: For time-sensitive docs like briefs\n  * created_at_range_start/end: Filter by when documents were created\n\nPagination:\n- 'limit': Number of documents to return (1-10, default 10)\n- 'offset': Skip documents for pagination\n\nCommon Use Cases:\n1. List all briefs:\n   list_filter: {doc_key: \"brief\"}\n\n2. List recent concepts:\n   list_filter: {doc_key: \"concept\", created_at_range_start: \"2024-01-01T00:00:00Z\"}\n\n3. List concepts with pagination:\n   list_filter: {doc_key: \"concept\"}\n   limit: 5\n   offset: 10\n\n4. List all documents in concept namespace (includes shared docs):\n   list_filter: {namespace_of_doc_key: \"concept\"}\n\n5. List scheduled briefs for next week:\n   list_filter: {\n     doc_key: \"brief\",\n     scheduled_date_range_start: \"2024-01-15T00:00:00Z\",\n     scheduled_date_range_end: \"2024-01-22T00:00:00Z\"\n   }\n\nNotes:\n- Returns document metadata only, not full content (use view_documents for full content)\n- Results include both user-specific and shared documents\n- Pagination may not be 100% accurate due to versioning metadata documents being filtered out\n- Dates should be in ISO format: YYYY-MM-DDTHH:MM:SSZ",
    "properties": {
        "list_filter": {
            "$ref": "#/$defs/DocumentListFilter"
        },
        "limit": {
            "description": "Maximum number of documents to list (1-10, default 10). Use smaller values for quick browsing, larger for comprehensive lists.",
            "title": "Limit",
            "type": "integer"
        },
        "offset": {
            "description": "Number of documents to skip for pagination. Use 0 for first page, then increment by 'limit' for subsequent pages.",
            "title": "Offset",
            "type": "integer"
        }
    },
    "required": [
        "list_filter",
        "limit",
        "offset"
    ],
    "title": "ListDocumentsInputSchema",
    "type": "object"
}
"""
