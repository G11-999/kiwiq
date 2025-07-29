"""
Example Workflow: Web Crawler Scraper with MongoDB Storage

This workflow demonstrates how to use the crawler_scraper node to:
1. Crawl websites starting from specified URLs
2. Automatically store scraped content in MongoDB
3. Return both statistics and sample scraped data

The workflow is useful for:
- Content aggregation from multiple websites
- Documentation crawling and indexing
- Blog/news content extraction
- General web data collection
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
            # "dynamic_output_schema": {
            #     "fields": {
            #         # Required fields
            #         "start_urls": {
            #             "type": "list[str]",
            #             "required": True,
            #             "description": "List of URLs to start crawling from"
            #         },
            #         "allowed_domains": {
            #             "type": "list[str]",
            #             "required": True,
            #             "description": "List of domains allowed for crawling"
            #         },
                    
            #         # Optional crawling limits
            #         "max_urls_per_domain": {
            #             "type": "int",
            #             "required": False,
            #             "default": 20000,
            #             "description": "Maximum URLs to discover per domain"
            #         },
            #         "max_processed_urls_per_domain": {
            #             "type": "int",
            #             "required": False,
            #             "default": 200,
            #             "description": "Maximum URLs to actually scrape per domain"
            #         },
            #         "max_crawl_depth": {
            #             "type": "int",
            #             "required": False,
            #             "default": 4,
            #             "description": "Maximum depth to crawl from start URLs"
            #         },
                    
            #         # Caching options
            #         "use_cached_scraping_results": {
            #             "type": "bool",
            #             "required": False,
            #             "default": True,
            #             "description": "Whether to use cached results if available"
            #         },
            #         "cache_lookback_period_days": {
            #             "type": "int",
            #             "required": False,
            #             "default": 7,
            #             "description": "How many days back to look for cached results"
            #         },
                    
            #         # Storage settings
            #         "is_shared": {
            #             "type": "bool",
            #             "required": False,
            #             "default": False,
            #             "description": "Store data as organization-shared (vs user-specific)"
            #         }
            #     }
            # }
        },
        
        # --- 2. Crawler Scraper Node ---
        "web_crawler": {
            "node_id": "web_crawler",
            "node_name": "crawler_scraper",
            "node_config": {
                # # Processor settings
                # "processor": "default",  # Use default HTML extraction
                
                # # Crawling behavior
                # "respect_robots_txt": True,
                # "crawl_sitemaps": True,
                # "enable_blog_url_pattern_priority_boost": True,
                
                # # Performance settings (conservative defaults)
                # "concurrent_requests_per_domain": 50,
                # "download_delay": 0.5,  # Be respectful to target servers
                
                # # Browser pool for JavaScript sites
                # "browser_pool_enabled": True,
                # "browser_pool_size": 3,
                # "browser_pool_timeout": 30,
                
                # Debug settings
                # "debug_mode": False,
                # "log_level": "INFO"
            }
            # Input fields are mapped from input_node
            # Output includes: job_id, status, stats, mongodb_namespaces, scraped_data, etc.
        },
        
        # --- 3. Output Node ---
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {},
            # Will receive all data from the crawler node
        }
    },
    
    # --- Edges Defining Data Flow ---
    "edges": [
        # Input -> Crawler: Pass all crawling parameters
        {
            "src_node_id": "input_node",
            "dst_node_id": "web_crawler",
            "mappings": [
                {"src_field": "start_urls", "dst_field": "start_urls"},
                # {"src_field": "allowed_domains", "dst_field": "allowed_domains"},
                {"src_field": "max_urls_per_domain", "dst_field": "max_urls_per_domain"},
                {"src_field": "max_processed_urls_per_domain", "dst_field": "max_processed_urls_per_domain"},
                {"src_field": "max_crawl_depth", "dst_field": "max_crawl_depth"},
                {"src_field": "use_cached_scraping_results", "dst_field": "use_cached_scraping_results"},
                {"src_field": "cache_lookback_period_days", "dst_field": "cache_lookback_period_days"},
                {"src_field": "is_shared", "dst_field": "is_shared"}
            ]
        },
        
        # Crawler -> Output: Pass all scraping results
        {
            "src_node_id": "web_crawler",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "job_id", "dst_field": "job_id"},
                {"src_field": "status", "dst_field": "status"},
                {"src_field": "stats", "dst_field": "scraping_stats"},
                {"src_field": "completed_at", "dst_field": "completed_at"},
                {"src_field": "mongodb_namespaces", "dst_field": "mongodb_namespaces"},
                {"src_field": "documents_stored", "dst_field": "documents_stored"},
                {"src_field": "scraped_data", "dst_field": "scraped_data"},
                {"src_field": "total_scraped_count", "dst_field": "total_scraped_count"},
                {"src_field": "used_cached_results", "dst_field": "used_cached_results"},
                {"src_field": "cached_results_age_hours", "dst_field": "cached_results_age_hours"}
            ]
        },
    ],
    
    # --- Define Start and End ---
    "input_node_id": "input_node",
    "output_node_id": "output_node"
}


# --- Test Execution Logic ---

async def validate_crawler_output(
    outputs: Optional[Dict[str, Any]], 
    crawler_inputs: Dict[str, Any]
) -> bool:
    """
    Custom validation function for the web crawler workflow outputs.
    
    Args:
        outputs: The dictionary of final outputs from the workflow run
        crawler_inputs: The original inputs for comparison
        
    Returns:
        True if outputs are valid, False otherwise
        
    Raises:
        AssertionError: If validation fails
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating web crawler workflow outputs...")
    
    # Check for all expected output fields
    required_fields = [
        'job_id', 'status', 'scraping_stats', 'completed_at',
        'mongodb_namespaces', 'documents_stored', 'scraped_data',
        'total_scraped_count', 'used_cached_results',
    ]
    
    for field in required_fields:
        assert field in outputs, f"Validation Failed: '{field}' key missing in outputs."
    
    # Check status
    assert outputs['status'] in ['completed', 'completed_from_cache'], \
        f"Validation Failed: Unexpected status '{outputs['status']}'"
    
    # Log validation results
    logger.info(f"   Job ID: {outputs.get('job_id')}")
    logger.info(f"   Status: {outputs.get('status')}")
    logger.info(f"   Documents stored: {outputs.get('documents_stored')}")
    logger.info(f"   Total scraped count: {outputs.get('total_scraped_count')}")
    logger.info(f"   Used cached results: {outputs.get('used_cached_results')}")
    
    if outputs.get('scraped_data'):
        logger.info(f"   Sample data available: {len(outputs['scraped_data'])} documents")
        # Log first document's keys as example
        if outputs['scraped_data']:
            first_doc_keys = list(outputs['scraped_data'][0].keys())
            logger.info(f"   First document keys: {first_doc_keys[:5]}...")  # Show first 5 keys
    
    if outputs.get('used_cached_results'):
        logger.info(f"   Cache age: {outputs.get('cached_results_age_hours', 0):.1f} hours")
    
    logger.info("✓ Output structure and content validation passed.")
    return True


async def main_test_web_crawler(
    start_urls: Optional[List[str]] = None,
    # allowed_domains: Optional[List[str]] = None,
    max_processed_urls: int = 10,
    use_cache: bool = True
):
    """
    Test the Web Crawler Workflow using the run_workflow_test helper.
    
    Args:
        start_urls: URLs to start crawling from (defaults to example blog)
        max_processed_urls: Maximum URLs to process per domain
        use_cache: Whether to use cached results if available
    """
    # Default to a safe example site if not provided
    if not start_urls:
        start_urls = ["https://www.prefect.io/blog"]
    
    # if not allowed_domains:
    #     # Extract domains from start_urls
    #     from urllib.parse import urlparse
    #     allowed_domains = list(set(urlparse(url).netloc for url in start_urls))
    
    # Prepare workflow inputs
    CRAWLER_WORKFLOW_INPUTS = {
        "start_urls": start_urls,
        # "allowed_domains": allowed_domains,
        "max_urls_per_domain": max_processed_urls * 10,  # Discover more than we process
        "max_processed_urls_per_domain": max_processed_urls,
        "max_crawl_depth": 3,  # Reasonable depth for testing
        "use_cached_scraping_results": use_cache,
        "cache_lookback_period_days": 7,
        "is_shared": False  # User-specific data for testing
    }
    
    test_name = "Web Crawler Scraper Test"
    print(f"\n--- Starting {test_name} ---")
    print(f"Target URLs: {start_urls}")
    # print(f"Allowed domains: {allowed_domains}")
    print(f"Max pages to scrape: {max_processed_urls}")
    print(f"Use cache: {use_cache}")
    
    # Note: MongoDB documents are automatically managed by the crawler_scraper node
    # No manual cleanup needed as documents have unique namespaces per job
    
    # Execute the test
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=CRAWLER_WORKFLOW_INPUTS,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=None,  # No human-in-the-loop needed
        setup_docs=[],  # No prerequisite documents
        cleanup_docs=[],  # Crawler manages its own MongoDB storage
        validate_output_func=partial(
            validate_crawler_output, 
            crawler_inputs=CRAWLER_WORKFLOW_INPUTS
        ),
        stream_intermediate_results=True,
        poll_interval_sec=3,
        timeout_sec=300  # 5 minutes for crawling
    )
    
    # Display sample scraped data if available
    if final_run_outputs and final_run_outputs.get('scraped_data'):
        print(f"\n--- Sample Scraped Data ({len(final_run_outputs['scraped_data'])} documents) ---")
        for i, doc in enumerate(final_run_outputs['scraped_data'][:3]):  # Show first 3
            print(f"\nDocument {i+1}:")
            print(f"  URL: {doc.get('url', 'N/A')}")
            print(f"  Title: {doc.get('title', 'N/A')[:100]}...")
            if 'text' in doc:
                print(f"  Text preview: {doc['text'][:200]}...")
            print(f"  Fields: {list(doc.keys())}")
    
    print(f"\n--- {test_name} Finished ---")
    
    return final_run_status_obj, final_run_outputs


# --- Example Usage Functions ---

async def example_crawl_documentation_site():
    """Example: Crawl a documentation website"""
    print("\n" + "="*60)
    print("EXAMPLE 1: Crawling Documentation Website")
    print("="*60)
    
    await main_test_web_crawler(
        start_urls=["https://docs.prefect.io/latest/"],
        # allowed_domains=["docs.prefect.io"],
        max_processed_urls=20,  # Crawl up to 20 pages
        use_cache=True
    )


async def example_crawl_blog():
    """Example: Crawl a blog for content aggregation"""
    print("\n" + "="*60)
    print("EXAMPLE 2: Crawling Blog Content")
    print("="*60)
    
    await main_test_web_crawler(
        start_urls=["https://blog.prefect.io/"],
        # allowed_domains=["blog.prefect.io"],
        max_processed_urls=15,  # Get latest 15 blog posts
        use_cache=False  # Force fresh crawl
    )


async def example_crawl_multiple_sites():
    """Example: Crawl multiple related sites"""
    print("\n" + "="*60)
    print("EXAMPLE 3: Multi-Site Crawling")
    print("="*60)
    
    # Note: This is just an example structure
    # In practice, you'd use real related sites
    await main_test_web_crawler(
        start_urls=[
            "https://example.com/blog",
            "https://docs.example.com/"
        ],
        # allowed_domains=["example.com", "docs.example.com"],
        max_processed_urls=50,  # Total across all domains
        use_cache=True
    )


if __name__ == "__main__":
    print("="*60)
    print("Web Crawler Scraper Workflow Examples")
    print("="*60)
    print("\nThis workflow demonstrates web crawling with automatic MongoDB storage.")
    print("Choose an example to run:")
    print("1. Crawl documentation site")
    print("2. Crawl blog content")
    print("3. Run basic test with defaults")
    
    # For automated testing, just run the basic test
    # In interactive mode, you could add user input to select examples

    kwargs = {
        "start_urls": ["https://otter.ai"],  # , 'https://grain.com/blog'
        # "allowed_domains": ["otter.ai", "grain.com"],
        "max_processed_urls": 200,
        "use_cache": True,
    }
    
    # Handle async execution
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        print("\nAsync event loop already running. Adding task...")
        task = loop.create_task(main_test_web_crawler(**kwargs))
    else:
        print("\nStarting new async event loop...")
        asyncio.run(main_test_web_crawler(**kwargs))
    
    print("\n" + "-"*60)
    print("Run this script from the project root directory using:")
    print("PYTHONPATH=. python standalone_test_client/kiwi_client/workflows/examples/wf_crawler_scraper_eg.py")
    print("-"*60)
