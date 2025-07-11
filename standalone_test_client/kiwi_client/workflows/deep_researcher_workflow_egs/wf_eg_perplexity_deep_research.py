import asyncio
import logging
from typing import Dict, Any, Optional, List, Union, ClassVar, Type
import json
from enum import Enum

# Using Pydantic for easier schema generation
from pydantic import BaseModel, Field

# Internal dependencies
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

# --- Workflow Configuration Constants ---

# LLM Configuration for Deep Research Model
LLM_PROVIDER = "perplexity"  # openai
LLM_MODEL = "sonar-deep-research"  # Deep research model  # o4-mini-deep-research
LLM_TEMPERATURE = 0.7
LLM_MAX_TOKENS = 16384  # 100000  # 16384
# LLM_MAX_TOOL_CALLS = 15  # Cost control for deep research models

# Default prompts
DEFAULT_SYSTEM_PROMPT = """You are an expert researcher with access to web search and code execution capabilities. 
Your task is to thoroughly research the given topic and provide comprehensive, well-sourced information.

Please:
1. Search for current and relevant information
2. Analyze multiple sources and perspectives
3. Provide clear, structured insights
4. Include specific examples and data when available
5. Cite your sources appropriately

Use your tools effectively to conduct thorough research."""

DEFAULT_USER_PROMPT = "Research the latest developments in artificial intelligence and machine learning in 2024. Focus on breakthrough technologies, major industry trends, and potential future implications."

### INPUTS ###

INPUT_FIELDS = {
    "system_prompt": {
        "type": "str", 
        "required": False, 
        "description": "System prompt for the researcher. If not provided, a default research prompt will be used."
    },
    "user_prompt": { 
        "type": "str", 
        "required": True, 
        "description": "The research question or topic to investigate."
    },
}

##############

### EDGES CONFIG ###

field_mappings_from_input_to_llm = [
    { "src_field": "system_prompt", "dst_field": "system_prompt" },
    { "src_field": "user_prompt", "dst_field": "user_prompt" },
]

field_mappings_from_llm_to_output = [
    { "src_field": "current_messages", "dst_field": "current_messages"},
    { "src_field": "content", "dst_field": "content"},
    { "src_field": "text_content", "dst_field": "text_content"},
    { "src_field": "metadata", "dst_field": "metadata"},
    { "src_field": "tool_calls", "dst_field": "tool_calls"},
    { "src_field": "web_search_result", "dst_field": "web_search_result"},
]

#############

workflow_graph_schema = {
    "nodes": {
        # --- 1. Input Node ---
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": INPUT_FIELDS
            }
        },

        # --- 2. Deep Research LLM Node ---
        "deep_researcher": {
            "node_id": "deep_researcher",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER, 
                        "model": LLM_MODEL
                    },
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS,
                    # "max_tool_calls": LLM_MAX_TOOL_CALLS  # Cost control for deep research models
                },
                "default_system_prompt": DEFAULT_SYSTEM_PROMPT,
                "tool_calling_config": {
                    "enable_tool_calling": True,
                    "parallel_tool_calls": True
                },
                # "tools": [
                #     # Web search tool (required for deep research models)
                #     {
                #         "tool_name": "web_search_preview",
                #         "is_provider_inbuilt_tool": True,
                #         # "provider_inbuilt_user_config": {
                #         #     "search_context_size": "high",
                #         #     "user_location": {
                #         #         "type": "approximate",
                #         #         "approximate": {
                #         #             "country": "US",
                #         #             "city": "San Francisco",
                #         #             "region": "CA"
                #         #         }
                #         #     }
                #         # }
                #     },
                #     # Code interpreter tool (optional but recommended)
                #     {
                #         "tool_name": "code_interpreter",
                #         "is_provider_inbuilt_tool": True,
                #     }
                # ]
            }
        },

        # --- 3. Output Node ---
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {},
        },
    },

    # --- Edges Defining Data Flow ---
    "edges": [
        # Input -> State: Store initial inputs globally
        { 
            "src_node_id": "input_node", 
            "dst_node_id": "deep_researcher", 
            "mappings": field_mappings_from_input_to_llm
        },
        
        # LLM -> Output: Pass all LLM outputs to the output node
        { 
            "src_node_id": "deep_researcher", 
            "dst_node_id": "output_node", 
            "mappings": field_mappings_from_llm_to_output
        },
    ],

    # --- Define Start and End ---
    "input_node_id": "input_node",
    "output_node_id": "output_node",
}

# --- Test Execution Logic ---
async def main_test_deep_researcher_workflow():
    """
    Test for OpenAI Deep Research Workflow.
    """
    test_name = "OpenAI Deep Research Workflow Test"
    print(f"--- Starting {test_name} ---")

    # Test inputs
    test_inputs = {
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "user_prompt": "Research the current state of autonomous vehicles in 2024. What are the major technological breakthroughs, key players, regulatory developments, and market predictions for the next 3-5 years?"
    }

    # No setup documents needed for this simple workflow
    setup_docs: List[SetupDocInfo] = []
    
    # No cleanup documents needed for this simple workflow
    cleanup_docs: List[CleanupDocInfo] = []

    # No predefined HITL inputs needed for this simple workflow
    predefined_hitl_inputs = []

    # Output validation function
    async def validate_deep_research_output(outputs) -> bool:
        """
        Validates the output from the deep research workflow.
        
        Args:
            outputs: The workflow output dictionary to validate
            
        Returns:
            bool: True if validation passes, raises AssertionError otherwise
        """
        assert outputs is not None, "Validation Failed: Workflow returned no outputs."
        
        # Check that we have the expected LLM output fields
        expected_fields = ['current_messages', 'content', 'text_content', 'metadata']
        for field in expected_fields:
            assert field in outputs, f"Validation Failed: '{field}' missing from outputs."
        
        # Validate metadata structure
        metadata = outputs.get('metadata', {})
        assert 'model_name' in metadata, "Metadata missing 'model_name' field"
        assert 'token_usage' in metadata, "Metadata missing 'token_usage' field"
        assert 'latency' in metadata, "Metadata missing 'latency' field"
        
        # Validate token usage
        token_usage = metadata.get('token_usage', {})
        assert 'total_tokens' in token_usage, "Token usage missing 'total_tokens' field"
        assert token_usage['total_tokens'] > 0, "Total tokens should be greater than 0"
        
        # Validate content
        content = outputs.get('content')
        assert content is not None, "Content should not be None"
        assert len(str(content)) > 0, "Content should not be empty"
        
        # Validate text content
        text_content = outputs.get('text_content')
        if text_content:
            assert len(text_content) > 0, "Text content should not be empty if present"
        
        # Check if web search was used (optional)
        web_search_result = outputs.get('web_search_result')
        if web_search_result:
            print(f"✓ Web search was used - found search results")
            if 'citations' in web_search_result and web_search_result['citations']:
                print(f"✓ Citations found: {len(web_search_result['citations'])} sources")
        
        # Check if tools were called (optional)
        tool_calls = outputs.get('tool_calls')
        if tool_calls:
            print(f"✓ Tool calls made: {len(tool_calls)} calls")
        
        # Check tool call count in metadata
        tool_call_count = metadata.get('tool_call_count', 0)
        if tool_call_count > 0:
            print(f"✓ Tool calls in metadata: {tool_call_count}")
        
        # Log success message
        print(f"✓ Deep research workflow validated successfully")
        print(f"✓ Model used: {metadata.get('model_name', 'unknown')}")
        print(f"✓ Total tokens: {token_usage.get('total_tokens', 0)}")
        print(f"✓ Latency: {metadata.get('latency', 0):.2f}s")
        print(f"✓ Content length: {len(str(content))} characters")
        
        return True

    # Execute the test
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=test_inputs,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=predefined_hitl_inputs,
        setup_docs=setup_docs,
        cleanup_docs_created_by_setup=False,
        cleanup_docs=cleanup_docs,
        validate_output_func=validate_deep_research_output,
        stream_intermediate_results=True,
        poll_interval_sec=5,
        timeout_sec=1800  # 10 minutes timeout for research tasks
    )

    print(f"--- {test_name} Finished ---")
    
    if final_run_outputs:
        # Display key results
        metadata = final_run_outputs.get('metadata', {})
        content = final_run_outputs.get('content', '')
        
        print(f"\n=== RESEARCH RESULTS ===")
        print(f"Model: {metadata.get('model_name', 'unknown')}")
        print(f"Total Tokens: {metadata.get('token_usage', {}).get('total_tokens', 0)}")
        print(f"Tool Calls: {metadata.get('tool_call_count', 0)}")
        print(f"Latency: {metadata.get('latency', 0):.2f}s")
        
        # Show web search results if available
        web_search_result = final_run_outputs.get('web_search_result')
        if web_search_result and web_search_result.get('citations'):
            print(f"\n=== SOURCES USED ===")
            for i, citation in enumerate(web_search_result['citations'][:5], 1):  # Show first 5 sources
                print(f"{i}. {citation.get('title', 'No title')}")
                print(f"   URL: {citation.get('url', 'No URL')}")
                if citation.get('snippet'):
                    print(f"   Snippet: {citation['snippet'][:100]}...")
                print()
        
        # Show a preview of the research content
        print(f"\n=== RESEARCH PREVIEW ===")
        text_content = final_run_outputs.get('text_content', str(content))
        if text_content:
            # Show first 500 characters
            preview = text_content[:500]
            print(f"{preview}...")
            print(f"\n(Total content length: {len(text_content)} characters)")
        
        print(f"\n=== END RESULTS ===")

if __name__ == "__main__":
    try:
        asyncio.run(main_test_deep_researcher_workflow())
    except KeyboardInterrupt:
        print("\nExecution interrupted.")
    except Exception as e:
        print(f"\nError running test: {e}")
        import traceback
        traceback.print_exc()
