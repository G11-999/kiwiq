"""
Example Workflow: AI Answer Engine Scraper with MongoDB Storage

This workflow demonstrates how to use the ai_answer_engine_scraper node to:
1. Query multiple AI providers (Google, OpenAI, Perplexity) about entities
2. Use template-based query construction with categorization
3. Automatically store results in MongoDB with caching
4. Return categorized results and statistics

The workflow is useful for:
- Entity research and information gathering
- Competitive intelligence
- Market research
- Company/person profiling
- Automated knowledge base building
"""

import asyncio
import json
from typing import Dict, Any, Optional, List
from functools import partial
from datetime import datetime

# Import necessary components for workflow testing
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    CleanupDocInfo
)
from kiwi_client.test_config import CLIENT_LOG_LEVEL
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

# Setup logger
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)


# --- Workflow Graph Definition ---
workflow_graph_schema = {
    "nodes": {
        # --- 1. Input Node ---
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
        },
        
        # --- 2. AI Answer Engine Scraper Node ---
        "ai_scraper": {
            "node_id": "ai_scraper",
            "node_name": "ai_answer_engine_scraper",
            "node_config": {
                # Query templates (can be overridden by input)
                # NOTE: All entities in list_template_vars must have the same keys
                # to ensure all template variables can be replaced
                "query_templates": {
                    "basic_info": [
                        # "What is {entity_name}?",
                        "Tell me about {entity_name}",
                        # "What does {entity_name} do?"
                    ],
                    "business": [
                        # "What products or services does {entity_name} offer?",
                        "What is the business model of {entity_name}?"
                    ],
                    "market": [
                        # "Who are the competitors of {entity_name}?",
                        "What is the market position of {entity_name}?"
                    ],
                    # "recent": [
                    #     "What is the latest news about {entity_name}?",
                    #     "What are the key achievements of {entity_name}?"
                    # ]
                },
                
                # # Provider configuration
                "default_providers_config": {
                    "google": {
                        "enabled": True,
                        "max_retries": 2,
                    },
                    "openai": {
                        "enabled": True,
                        "max_retries": 3,
                    },
                    "perplexity": {
                        "enabled": True,
                        "max_retries": 2,
                    }
                },
                
                # # Browser pool configuration
                # "max_concurrent_browsers": 30,
                # "browser_ttl": 900,  # 15 minutes
                # "acquisition_timeout": 60,
                # "use_browser_profiles": True,
                # "persist_browser_profile": False
            }
        },
        
        # --- 3. Output Node ---
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {},
        }
    },
    
    # --- Edges Defining Data Flow ---
    "edges": [
        # Input -> AI Scraper: Pass all query parameters
        {
            "src_node_id": "input_node",
            "dst_node_id": "ai_scraper",
            "mappings": [
                {"src_field": "list_template_vars", "dst_field": "list_template_vars"},
                {"src_field": "query_templates", "dst_field": "query_templates"},
                {"src_field": "providers_config", "dst_field": "providers_config"},
                {"src_field": "enable_mongodb_cache", "dst_field": "enable_mongodb_cache"},
                {"src_field": "cache_lookback_days", "dst_field": "cache_lookback_days"},
                {"src_field": "is_shared", "dst_field": "is_shared"}
            ]
        },
        
        # AI Scraper -> Output: Pass all results
        {
            "src_node_id": "ai_scraper",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "job_id", "dst_field": "job_id"},
                {"src_field": "status", "dst_field": "status"},
                {"src_field": "total_queries_executed", "dst_field": "total_queries_executed"},
                {"src_field": "successful_queries", "dst_field": "successful_queries"},
                {"src_field": "failed_queries", "dst_field": "failed_queries"},
                {"src_field": "cached_results_used", "dst_field": "cached_results_used"},
                {"src_field": "provider_stats", "dst_field": "provider_stats"},
                {"src_field": "completed_at", "dst_field": "completed_at"},
                {"src_field": "mongodb_namespaces", "dst_field": "mongodb_namespaces"},
                {"src_field": "documents_stored", "dst_field": "documents_stored"},
                {"src_field": "query_results", "dst_field": "query_results"},
                {"src_field": "entity_results", "dst_field": "entity_results"},
                {"src_field": "executed_queries", "dst_field": "executed_queries"},
                {"src_field": "used_cached_results", "dst_field": "used_cached_results"}
            ]
        },
    ],
    
    # --- Define Start and End ---
    "input_node_id": "input_node",
    "output_node_id": "output_node"
}

# --- Test Execution Logic ---

async def validate_ai_scraper_output(
    outputs: Optional[Dict[str, Any]], 
    ai_inputs: Dict[str, Any]
) -> bool:
    """
    Custom validation function for the AI answer engine scraper workflow outputs.
    
    Args:
        outputs: The dictionary of final outputs from the workflow run
        ai_inputs: The original inputs for comparison
        
    Returns:
        True if outputs are valid, False otherwise
        
    Raises:
        AssertionError: If validation fails
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating AI answer engine scraper workflow outputs...")
    
    # Check for all expected output fields
    required_fields = [
        'job_id', 'status', 'total_queries_executed', 'successful_queries',
        'failed_queries', 'cached_results_used', 'provider_stats',
        'completed_at', 'mongodb_namespaces', 'documents_stored',
        'query_results', 'entity_results', 'executed_queries',
        'used_cached_results'
    ]
    
    for field in required_fields:
        assert field in outputs, f"Validation Failed: '{field}' key missing in outputs."
    
    # Check status
    assert outputs['status'] in ['completed', 'completed_from_cache', 'completed_with_cache'], \
        f"Validation Failed: Unexpected status '{outputs['status']}'"
    
    # Log validation results
    logger.info(f"   Job ID: {outputs.get('job_id')}")
    logger.info(f"   Status: {outputs.get('status')}")
    logger.info(f"   Total queries executed: {outputs.get('total_queries_executed')}")
    logger.info(f"   Successful queries: {outputs.get('successful_queries')}")
    logger.info(f"   Failed queries: {outputs.get('failed_queries')}")
    logger.info(f"   Cached results used: {outputs.get('cached_results_used')}")
    logger.info(f"   Documents stored: {outputs.get('documents_stored')}")
    
    # Check entity results
    entity_results = outputs.get('entity_results', {})
    if entity_results:
        logger.info(f"   Entities processed: {len(entity_results)}")
        for entity_name, data in entity_results.items():
            logger.info(f"   - {entity_name}: {data.get('cached_count', 0)} cached, {data.get('new_count', 0)} new")
            
            # Check categorized results
            categorized = data.get('categorized_results', {})
            if categorized:
                logger.info(f"     Categories: {list(categorized.keys())}")
    
    # Check provider stats
    provider_stats = outputs.get('provider_stats', {})
    if provider_stats:
        logger.info(f"   Provider stats:")
        for provider, stats in provider_stats.items():
            success_rate = stats.get('success_rate', 0) * 100
            avg_attempts = stats.get('average_attempts_per_query', 1)
            avg_duration = stats.get('average_duration_seconds', 0)
            logger.info(
                f"   - {provider}: {success_rate:.1f}% success rate, "
                f"avg {avg_attempts:.1f} attempts/query, "
                f"avg {avg_duration:.1f}s/query"
            )
    
    if outputs.get('query_results'):
        logger.info(f"   Sample data available: {len(outputs['query_results'])} results")
    
    logger.info("✅ Output structure and content validation passed.")
    return True


async def main_test_ai_scraper(
    entities: Optional[List[Dict[str, str]]] = None,
    use_cache: bool = True,
    cache_lookback_days: int = 7,
    custom_query_templates: Optional[Dict[str, List[str]]] = None
):
    """
    Test the AI Answer Engine Scraper Workflow using the run_workflow_test helper.
    
    Args:
        entities: List of entities to research with template variables.
                 IMPORTANT: All entities must have the same keys (e.g., if one has 'location',
                 all must have 'location') to ensure query templates work for all entities.
        use_cache: Whether to use cached results if available
        cache_lookback_days: Number of days to look back for cached results
        custom_query_templates: Optional custom categorized query templates
    
    Example entities with consistent keys:
        [
            {"entity_name": "OpenAI", "location": "San Francisco", "industry": "AI"},
            {"entity_name": "Tesla", "location": "Palo Alto", "industry": "Automotive"}
        ]
    """
    # Default to example entities if not provided
    if not entities:
        # Note: All entities must have the same template variable keys
        entities = [
            {"entity_name": "OpenAI", "location": "San Francisco", "industry": "Artificial Intelligence"},
            {"entity_name": "Tesla", "location": "Palo Alto", "industry": "Automotive"}
        ]
    
    # Prepare workflow inputs
    AI_SCRAPER_WORKFLOW_INPUTS = {
        "list_template_vars": entities,
        "enable_mongodb_cache": use_cache,
        "cache_lookback_days": cache_lookback_days,
        "is_shared": False  # User-specific data for testing
    }
    
    # Add custom query templates if provided
    if custom_query_templates:
        AI_SCRAPER_WORKFLOW_INPUTS["query_templates"] = custom_query_templates
    
    # You can also override provider config
    # AI_SCRAPER_WORKFLOW_INPUTS["providers_config"] = {
    #     "perplexity": {"enabled": False}  # Example: disable a provider
    # }
    
    test_name = "AI Answer Engine Scraper Test"
    entity_names = [e.get('entity_name', 'Unknown') for e in entities]
    
    print(f"\n🚀 --- Starting {test_name} ---")
    print(f"🏢 Entities to research: {', '.join(entity_names)}")
    print(f"💾 Use cache: {use_cache}")
    print(f"📅 Cache lookback days: {cache_lookback_days}")
    if custom_query_templates:
        print(f"📝 Using custom query templates with categories: {list(custom_query_templates.keys())}")
    
    # Execute the test
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=AI_SCRAPER_WORKFLOW_INPUTS,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=None,  # No human-in-the-loop needed
        setup_docs=[],  # No prerequisite documents
        cleanup_docs=[],  # AI scraper manages its own MongoDB storage
        validate_output_func=partial(
            validate_ai_scraper_output, 
            ai_inputs=AI_SCRAPER_WORKFLOW_INPUTS
        ),
        stream_intermediate_results=True,
        poll_interval_sec=3,
        timeout_sec=600  # 5 minutes for AI queries
    )
    
    # Display sample results if available
    if final_run_outputs:
        # Display completion time if available
        completed_at = final_run_outputs.get('completed_at')
        if completed_at:
            print(f"\n⏱️ Completed at: {completed_at}")
        
        # Show entity results
        entity_results = final_run_outputs.get('entity_results', {})
        if entity_results:
            print(f"\n📊 --- Entity Results Summary ---")
            for entity_name, data in entity_results.items():
                print(f"\n🏢 {entity_name}:")
                unique_queries = sum(len(queries) for queries in data.get('categorized_queries', {}).values())
                results = data.get('results', [])
                unique_query_provider_combos = len(set((r.get('query', ''), r.get('provider', '')) for r in results if r))
                print(f"  📋 Unique queries: {unique_queries}")
                print(f"  📊 Total results: {unique_query_provider_combos} unique (query, provider) combinations")
                print(f"  💾 Cached results used: {data.get('cached_count', 0)}")
                print(f"  🆕 New results generated: {data.get('new_count', 0)}")
                
                # Show categorized results
                categorized = data.get('categorized_results', {})
                if categorized:
                    print(f"  Results by category:")
                    for category, results in categorized.items():
                        print(f"    - {category}: {len(results)} results")
        
        # Show sample query results
        query_results = final_run_outputs.get('query_results', [])
        if query_results:
            print(f"\n📄 --- Sample Query Results ({len(query_results)} total) ---")
            for i, result in enumerate(query_results[:7]):  # Show first 3
                print(f"\nResult {i+1}:")
                print(f"  Query: {result.get('query', 'N/A')}")
                print(f"  Provider: {result.get('provider', 'N/A')}")
                success = result.get('success', False)
                print(f"  Success: {'✅' if success else '❌'} {success}")
                print(f"  Attempts: {result.get('attempts', 1)}")
                print(f"  Duration: {result.get('duration_seconds', 0):.1f}s")
                if result.get('response'):
                    response = result['response']
                    if isinstance(response, dict) and 'processed_data' in response:
                        print(f"  Response preview: {str(response['processed_data'])[:200]}...")
        
        # Show provider statistics summary
        provider_stats = final_run_outputs.get('provider_stats', {})
        if provider_stats:
            print(f"\n📈 --- Provider Statistics ---")
            for provider, stats in provider_stats.items():
                print(f"\n{provider.upper()}:")
                print(f"  Success rate: {stats.get('success_rate', 0) * 100:.1f}%")
                print(f"  Avg attempts per query: {stats.get('average_attempts_per_query', 1):.2f}")
                print(f"  Avg duration: {stats.get('average_duration_seconds', 0):.1f}s")
                print(f"  Total queries: {stats.get('total_queries', 0)}")
                print(f"  Successful: {stats.get('successful_queries', 0)}")
                print(f"  Failed: {stats.get('failed_queries', 0)}")
        
        # Show overall execution summary
        print(f"\n⏱️ --- Execution Summary ---")
        print(f"Total queries executed: {final_run_outputs.get('total_queries_executed', 0)}")
        print(f"Successful: {final_run_outputs.get('successful_queries', 0)}")
        print(f"Failed: {final_run_outputs.get('failed_queries', 0)}")
        print(f"Cached results used: {final_run_outputs.get('cached_results_used', 0)}")
        print(f"Documents stored: {final_run_outputs.get('documents_stored', 0)}")
    
    print(f"\n🎉 --- {test_name} Finished ---")
    
    return final_run_status_obj, final_run_outputs


if __name__ == "__main__":
    print("="*60)
    print("AI Answer Engine Scraper Workflow Examples")
    print("="*60)
    print("\nThis workflow demonstrates AI-powered entity research with caching.")
    print("Choose an example to run:")
    print("1. Research tech companies")
    print("2. Research with custom query templates")
    print("3. Test caching behavior")
    
    # Example 1: Basic entity research
    # IMPORTANT: All entities in a batch must have the same template variable keys
    # to ensure all queries can be properly constructed for each entity
    example1_entities = [
        {"entity_name": "OpenAI", "location": "San Francisco", "industry": "AI"},
        # {"entity_name": "Anthropic", "location": "San Francisco", "industry": "AI"},
        # {"entity_name": "Tesla", "location": "Palo Alto", "industry": "Automotive"}  # Added location
    ]
    
    # Example 2: Custom query templates
    # All entities must have both 'entity_name' and 'product' keys for these templates
    example2_entities = [
        {"entity_name": "Microsoft", "product": "cloud services"},
        {"entity_name": "Amazon", "product": "cloud services"},
        {"entity_name": "Google", "product": "cloud services"}
    ]
    example2_templates = {
        "financial": [
            "What is the current stock price of {entity_name}?",
            "What is the market cap of {entity_name}?"
        ],
        "products": [
            "What are the main {product} offerings from {entity_name}?",
            "How does {entity_name} compare to AWS in {product}?"
        ]
    }
    
    # For automated testing, run example 1
    kwargs = {
        "entities": example1_entities,
        "use_cache": True,
        "cache_lookback_days": 7
    }
    
    # Uncomment to test example 2 with custom templates
    # kwargs = {
    #     "entities": example2_entities,
    #     "use_cache": False,
    #     "custom_query_templates": example2_templates
    # }
    
    # Handle async execution
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        print("\nAsync event loop already running. Adding task...")
        task = loop.create_task(main_test_ai_scraper(**kwargs))
    else:
        print("\nStarting new async event loop...")
        asyncio.run(main_test_ai_scraper(**kwargs))
    
    print("\n" + "-"*60)
    print("Run this script from the project root directory using:")
    print("PYTHONPATH=. python standalone_test_client/kiwi_client/workflows/examples/wf_ai_answer_engine_scraper_eg.py")
    print("-"*60) 