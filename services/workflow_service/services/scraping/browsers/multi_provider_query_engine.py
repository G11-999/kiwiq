import asyncio
import uuid
import json
import os
import time
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass

from workflow_service.services.scraping.browsers.scrapeless.scrapeless_browser import (
    ScrapelessBrowser, 
    ScrapelessBrowserPool,
    ScrapelessBrowserContextManager,
    cleanup_scrapeless_redis_pool
)
from workflow_service.services.scraping.browsers.actors.google_ai_mode_logged_out import GoogleAIModeBrowserActor
from workflow_service.services.scraping.browsers.actors.perplexity_logged_out import PerplexityBrowserActor
from workflow_service.services.scraping.browsers.actors.openai_logged_out import OpenAIBrowserActor
from workflow_service.services.scraping.settings import scraping_settings
from workflow_service.services.scraping.browsers.config import MAX_CONCURRENT_SCRAPELESS_BROWSERS, ACQUISITION_TIMEOUT, BROWSER_TTL

from global_config.logger import get_prefect_or_regular_python_logger




@dataclass
class ProviderConfig:
    """Configuration for each provider"""
    enabled: bool = True
    max_retries: int = 3
    retry_delay: float = 2.0  # Base delay between retries (exponential backoff)
    timeout: int = ACQUISITION_TIMEOUT  # Timeout per query in seconds


class MultiProviderQueryEngine:
    """
    Reusable querying class for orchestrating queries across multiple AI providers.
    
    Features:
    - Configurable providers (OpenAI, Google, Perplexity)
    - Browser pool with keep-alive for efficiency  
    - Configurable retries per query with exponential backoff
    - Collects all responses and saves to JSON
    - Comprehensive error handling and logging
    """
    
    def __init__(
        self,
        queries: List[str],
        providers_config: Optional[Dict[str, ProviderConfig]] = None,
        query_provider_mapping: Optional[Dict[str, List[str]]] = None,
        max_concurrent_browsers: int = 3,
        browser_pool_config: Optional[Dict] = None,
        output_file: Optional[str] = None,
        data_dir: Optional[str] = None
    ):
        """
        Initialize the MultiProviderQueryEngine.
        
        Args:
            queries: List of query strings to execute
            providers_config: Configuration for each provider (openai, google, perplexity)
            query_provider_mapping: Optional mapping of query -> list of providers to use.
                                   If not provided, all enabled providers will be used for all queries.
                                   Example: {"What is AI?": ["openai", "google"], "Tell me about ML": ["perplexity"]}
            max_concurrent_browsers: Maximum concurrent browsers in the pool
            browser_pool_config: Additional browser pool configuration
            output_file: JSON output file name (defaults to timestamped file)
            data_dir: Output directory (defaults to data subdir relative to this file)
        """
        self.logger = get_prefect_or_regular_python_logger(self.__class__.__name__)
        self.queries = queries
        
        # Set up default provider configurations
        default_config = ProviderConfig()
        self.providers_config = providers_config or {
            "openai": default_config,
            "google": default_config, 
            "perplexity": default_config
        }
        
        # Query-specific provider mapping
        self.query_provider_mapping = query_provider_mapping or {}
        
        # Browser pool configuration
        self.max_concurrent_browsers = max_concurrent_browsers
        self.browser_pool_config = browser_pool_config or {}
        
        # Output configuration
        if not data_dir:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            self.data_dir = os.path.join(current_dir, "data")
        else:
            self.data_dir = data_dir
            
        os.makedirs(self.data_dir, exist_ok=True)
        
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.output_file = os.path.join(self.data_dir, f"query_results_{timestamp}.json")
        else:
            self.output_file = os.path.join(self.data_dir, output_file)
        
        # Provider actor mapping
        self.provider_actors = {
            "openai": OpenAIBrowserActor,
            "google": GoogleAIModeBrowserActor,
            "perplexity": PerplexityBrowserActor,
        }
        
        # Calculate total tasks based on query-provider mapping
        total_tasks = 0
        for query in queries:
            if query in self.query_provider_mapping:
                # Use specific providers for this query
                providers_for_query = [p for p in self.query_provider_mapping[query] 
                                     if p in self.providers_config and self.providers_config[p].enabled]
                total_tasks += len(providers_for_query)
            else:
                # Use all enabled providers
                total_tasks += len([p for p, cfg in self.providers_config.items() if cfg.enabled])
        
        self.logger.info(f"MultiProviderQueryEngine initialized:")
        self.logger.info(f"  📋 Queries: {len(queries)}")
        self.logger.info(f"  🌐 Enabled providers: {[p for p, cfg in self.providers_config.items() if cfg.enabled]}")
        if self.query_provider_mapping:
            self.logger.info(f"  🎯 Query-specific provider mapping: {len(self.query_provider_mapping)} custom mappings")
        self.logger.info(f"  📊 Total tasks: {total_tasks}")
        self.logger.info(f"  🔄 Max concurrent browsers: {max_concurrent_browsers}")
        self.logger.info(f"  💾 Output file: {self.output_file}")
    
    async def process_all_queries(self) -> Dict[str, Any]:
        """
        Main method to process all queries across all enabled providers.
        
        Returns:
            Dictionary containing all results and metadata
        """
        start_time = datetime.now()
        self.logger.info(f"🚀 Starting query processing at {start_time.isoformat()}")
        
        all_results = {
            "metadata": {
                "start_time": start_time.isoformat(),
                "queries": self.queries,
                "total_queries": len(self.queries),
                "enabled_providers": [p for p, cfg in self.providers_config.items() if cfg.enabled],
                "browser_pool_config": {
                    "max_concurrent_browsers": self.max_concurrent_browsers,
                    **self.browser_pool_config
                }
            },
            "results": {},
            "errors": {},
            "statistics": {}
        }
        
        # Get enabled providers for parallel processing and optimization calculation
        enabled_providers = [(name, config) for name, config in self.providers_config.items() if config.enabled]
        
        # Calculate total queries based on query-provider mapping
        total_queries_to_execute = 0
        for query in self.queries:
            if query in self.query_provider_mapping:
                # Count only enabled providers for this query
                providers_for_query = [p for p in self.query_provider_mapping[query] 
                                     if p in self.providers_config and self.providers_config[p].enabled]
                total_queries_to_execute += len(providers_for_query)
            else:
                # Use all enabled providers
                total_queries_to_execute += len(enabled_providers)
        
        # Optimization: disable keep-alive if we have enough browsers for all queries
        # This saves resources by not keeping browsers alive unnecessarily
        enable_keep_alive = total_queries_to_execute > self.max_concurrent_browsers
        
        self.logger.info(f"🔧 Keep-alive optimization: {'ENABLED' if enable_keep_alive else 'DISABLED'} "
                   f"(queries: {total_queries_to_execute}, browsers: {self.max_concurrent_browsers})")
        
        # Create and configure browser pool
        pool_config = {
            "max_concurrent_local": self.max_concurrent_browsers,
            "acquisition_timeout": ACQUISITION_TIMEOUT,
            "browser_ttl": BROWSER_TTL,  # 15 minutes
            "enable_keep_alive": enable_keep_alive,  # Dynamic keep-alive optimization
            **self.browser_pool_config
        }
        
        # Process queries with browser pool keep-alive
        async with ScrapelessBrowserPool(**pool_config) as browser_pool:
            self.logger.info(f"🔄 Browser pool activated with keep-alive {'ENABLED' if enable_keep_alive else 'DISABLED'}")
            disabled_providers = [name for name, config in self.providers_config.items() if not config.enabled]
            
            if disabled_providers:
                self.logger.info(f"⏸️ Disabled providers: {', '.join(disabled_providers)}")
            
            if not enabled_providers:
                self.logger.warning("⚠️ No providers enabled! Nothing to process.")
                return all_results
            
            # Calculate actual total tasks based on query-provider mapping
            total_tasks = 0
            query_provider_details = []
            
            for i, query in enumerate(self.queries):
                if query in self.query_provider_mapping:
                    # Use specific providers for this query
                    providers_for_query = [
                        (name, self.providers_config[name]) 
                        for name in self.query_provider_mapping[query]
                        if name in self.providers_config and self.providers_config[name].enabled
                    ]
                    query_provider_details.append((query, i, providers_for_query))
                    total_tasks += len(providers_for_query)
                else:
                    # Use all enabled providers
                    query_provider_details.append((query, i, enabled_providers))
                    total_tasks += len(enabled_providers)
            
            self.logger.info(f"🚀 Processing {len(self.queries)} queries with custom provider mappings")
            self.logger.info(f"📊 Total tasks: {total_tasks} (varies by query)")
            self.logger.info(f"🔄 Browser pool capacity: {browser_pool.effective_max_concurrent} concurrent browsers")
            
            # Create tasks based on query-provider mapping
            all_tasks = []
            task_metadata = []
            
            for query, query_index, providers_for_query in query_provider_details:
                for provider_name, provider_config in providers_for_query:
                    actor_class = self.provider_actors[provider_name]
                    
                    task = asyncio.create_task(
                        self._execute_single_query_with_retry(
                            actor_class=actor_class,
                            query=query,
                            provider_name=provider_name,
                            provider_config=provider_config,
                            browser_pool=browser_pool,
                            query_index=query_index
                        ),
                        name=f"{provider_name}_query_{query_index}"
                    )
                    all_tasks.append(task)
                    task_metadata.append({
                        "provider": provider_name,
                        "query_index": query_index,
                        "query": query
                    })
            
            self.logger.info(f"⏳ Executing {len(all_tasks)} tasks across ALL providers in parallel...")
            
            try:
                # Execute ALL tasks across ALL providers simultaneously
                all_task_results = await asyncio.gather(*all_tasks, return_exceptions=True)
                
                # Organize results by provider
                for task_idx, (result, metadata) in enumerate(zip(all_task_results, task_metadata)):
                    provider_name = metadata["provider"]
                    
                    # Initialize provider results if not exists
                    if provider_name not in all_results["results"]:
                        all_results["results"][provider_name] = []
                    
                    # Handle exceptions that occurred during parallel execution
                    if isinstance(result, Exception):
                        self.logger.error(f"❌ {provider_name.upper()} Query {metadata['query_index']+1} "
                                   f"failed with exception: {result}")
                        # Create a failure result for this query
                        failure_result = {
                            "query": metadata["query"],
                            "query_index": metadata["query_index"],
                            "provider": provider_name,
                            "success": False,
                            "attempts": 1,
                            "start_time": datetime.now().isoformat(),
                            "end_time": datetime.now().isoformat(),
                            "response": None,
                            "error": {
                                "message": str(result),
                                "type": type(result).__name__,
                                "attempt": 1
                            },
                            "duration_seconds": 0
                        }
                        all_results["results"][provider_name].append(failure_result)
                    else:
                        all_results["results"][provider_name].append(result)  # ["results"][provider_name]LIST["response"][raw response for single query...]
                
                # Calculate statistics for each provider
                for provider_name in all_results["results"]:
                    provider_results = all_results["results"][provider_name]
                    
                    # Calculate how many queries were actually sent to this provider
                    actual_queries_for_provider = len(provider_results)
                    
                    successful_queries = sum(1 for r in provider_results if r.get("success", False))
                    total_duration = sum(r.get("duration_seconds", 0) for r in provider_results)
                    avg_duration = total_duration / len(provider_results) if provider_results else 0
                    
                    # Calculate average attempts
                    total_attempts = sum(r.get("attempts", 1) for r in provider_results)
                    avg_attempts = total_attempts / len(provider_results) if provider_results else 0
                    
                    all_results["statistics"][provider_name] = {
                        "total_queries": actual_queries_for_provider,
                        "successful_queries": successful_queries,
                        "failed_queries": actual_queries_for_provider - successful_queries,
                        "success_rate": successful_queries / actual_queries_for_provider if actual_queries_for_provider else 0,
                        "total_duration_seconds": total_duration,
                        "average_duration_seconds": avg_duration,
                        "total_attempts": total_attempts,
                        "average_attempts": avg_attempts
                    }
                    
                    self.logger.info(f"✅ {provider_name.upper()}: {successful_queries}/{actual_queries_for_provider} queries "
                              f"({successful_queries/actual_queries_for_provider*100:.1f}%) in {total_duration:.1f}s "
                              f"(avg: {avg_duration:.1f}s/query, {avg_attempts:.1f} attempts/query)")
                
            except Exception as e:
                self.logger.error(f"❌ Fatal error during cross-provider parallel processing: {e}", exc_info=True)
                # Record the global error
                all_results["errors"]["global_parallel_processing"] = {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "timestamp": datetime.now().isoformat()
                }
        
        # Finalize metadata
        end_time = datetime.now()
        all_results["metadata"]["end_time"] = end_time.isoformat()
        all_results["metadata"]["total_duration_seconds"] = (end_time - start_time).total_seconds()
        
        # # Save results to JSON
        # self._save_results_to_json(all_results)
        
        self.logger.info(f"🎉 Query processing completed in {all_results['metadata']['total_duration_seconds']:.2f}s")
        
        return all_results
    
    async def _execute_single_query_with_retry(
        self,
        actor_class,
        query: str,
        provider_name: str,
        provider_config: ProviderConfig,
        browser_pool: ScrapelessBrowserPool,
        query_index: int
    ) -> Dict[str, Any]:
        """
        Execute a single query with configurable retry logic.
        
        Args:
            actor_class: The actor class to instantiate
            query: Query string to execute
            provider_name: Name of the provider
            provider_config: Configuration for retry behavior
            browser_pool: Browser pool to acquire browsers from
            query_index: Index of this query in the overall list
            
        Returns:
            Dictionary with query result and metadata
        """
        result = {
            "query": query,
            "query_index": query_index,
            "provider": provider_name,
            "success": False,
            "attempts": 0,
            "start_time": datetime.now().isoformat(),
            "response": None,
            "error": None,
            "duration_seconds": 0
        }
        
        start_time = time.time()
        
        for attempt in range(provider_config.max_retries + 1):  # +1 for initial attempt
            result["attempts"] = attempt + 1
            
            try:
                self.logger.debug(f"  🔄 Attempt {attempt + 1}/{provider_config.max_retries + 1}")
                
                # Acquire browser with context manager and retry support
                async with ScrapelessBrowserContextManager(
                    browser_pool,
                    timeout=ACQUISITION_TIMEOUT,  # Browser acquisition timeout
                    force_close_on_error=True  # Force close on errors
                ) as browser:
                    
                    # Create actor instance with the browser
                    actor = actor_class(
                        browser=browser.browser,
                        context=browser.context, 
                        page=browser.page
                    )
                    
                    # Execute the query with timeout
                    try:
                        response = await asyncio.wait_for(
                            actor.single_query(query),
                            timeout=provider_config.timeout
                        )
                        
                        # Normalize response format across providers
                        normalized_response = self._normalize_response(response, provider_name)
                        
                        result["response"] = normalized_response
                        result["success"] = True
                        result["duration_seconds"] = time.time() - start_time
                        result["end_time"] = datetime.now().isoformat()
                        
                        self.logger.info(f"  ✅ Success on attempt {attempt + 1}")
                        return result
                        
                    except asyncio.TimeoutError:
                        raise Exception(f"Query timed out after {provider_config.timeout}s")
                        
            except Exception as e:
                error_msg = str(e)
                self.logger.warning(f"  ❌ Attempt {attempt + 1} failed: {error_msg}")
                
                result["error"] = {
                    "message": error_msg,
                    "type": type(e).__name__,
                    "attempt": attempt + 1
                }
                
                # If this is not the last attempt, wait before retrying
                if attempt < provider_config.max_retries:
                    retry_delay = provider_config.retry_delay * (2 ** attempt)  # Exponential backoff
                    self.logger.debug(f"  ⏳ Retrying in {retry_delay:.1f}s...")
                    await asyncio.sleep(retry_delay)
                else:
                    self.logger.error(f"  ❌ All {provider_config.max_retries + 1} attempts failed", exc_info=True)
        
        result["duration_seconds"] = time.time() - start_time
        result["end_time"] = datetime.now().isoformat()
        return result
    
    def _normalize_response(self, response: Union[Dict, List], provider_name: str) -> Dict[str, Any]:
        """
        Normalize response format across different providers.
        
        Args:
            response: Raw response from the provider
            provider_name: Name of the provider
            
        Returns:
            Normalized response format
        """
        raw_response = response
        if isinstance(raw_response, list):
            raw_response = [({k:v for k,v in r.items() if k not in ["html"]} if isinstance(r, dict) else r) for r in raw_response]
        
        response = raw_response  # remove HTML in futher processing!

        normalized = {
            "provider": provider_name,
            # "raw_response": raw_response,
            "processed_data": None,
            "links": [],
            "citations": [],
            "markdown": "",
            "query": "",
        }
        
        # if provider_name == "google":
        #     # Google returns: {"results": results, "links": links}
        #     if isinstance(response, dict):
        #         normalized["processed_data"] = response.get("results", [])
        #         normalized["links"] = response.get("links", [])
                
        #         # Extract citations from results
        #         for result in normalized["processed_data"]:
        #             if isinstance(result, dict) and "citations" in result:
        #                 normalized["citations"].extend(result["citations"])
        
        if provider_name in ["openai", "perplexity", "google"]:
            # OpenAI and Perplexity return lists directly
            if isinstance(response, list):
                normalized["processed_data"] = response[0] if len(response) == 1 else response
                
                # Extract links and citations from each item
                for item in response:
                    if isinstance(item, dict):
                        if "links" in item:
                            normalized["links"].extend(item["links"])
                        if "citations" in item:
                            normalized["citations"].extend(item["citations"])
                        if "all_links" in item:
                            normalized["links"].extend(item["all_links"])
                        if "markdown" in item:
                            if normalized["markdown"]:
                                normalized["markdown"] += "\n\n"
                            normalized["markdown"] += item["markdown"]
                        if "query" in item:
                            if normalized["query"]:
                                normalized["query"] += "\n\n"
                            normalized["query"] += item["query"]
        
        # Remove duplicates from links and citations
        normalized["links"] = self._deduplicate_list_of_dicts(normalized["links"], "url")
        normalized["citations"] = list(set(normalized["citations"]))

        del normalized["processed_data"]
        
        return normalized
    
    def _deduplicate_list_of_dicts(self, items: List[Dict], key: str) -> List[Dict]:
        """Remove duplicates from list of dictionaries based on a key."""
        seen = set()
        unique_items = []
        for item in items:
            if isinstance(item, dict) and key in item:
                if item[key] not in seen:
                    seen.add(item[key])
                    unique_items.append(item)
        return unique_items
    
    def _save_results_to_json(self, results: Dict[str, Any]) -> None:
        """
        Save results to JSON file with structure similar to profiles cache.
        
        Args:
            results: Complete results dictionary to save
        """
        try:
            # Create backup if file exists
            if os.path.exists(self.output_file):
                backup_file = f"{self.output_file}.backup"
                try:
                    os.rename(self.output_file, backup_file)
                    self.logger.debug(f"📋 Created backup: {backup_file}")
                except OSError as e:
                    self.logger.warning(f"Could not create backup: {e}")
            
            # Add save metadata similar to profiles cache
            save_data = {
                "created_at": datetime.now().isoformat(),
                "operation": "multi_provider_query",
                "version": "1.0",
                "data": results
            }
            
            # Save to JSON with pretty formatting
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False)
            
            file_size = os.path.getsize(self.output_file)
            self.logger.info(f"💾 Results saved to: {self.output_file} ({file_size:,} bytes)")
            
        except Exception as e:
            self.logger.error(f"❌ Error saving results to JSON: {e}")
            raise
    
    def get_summary_statistics(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate summary statistics from the results.
        
        Args:
            results: Results dictionary from process_all_queries
            
        Returns:
            Summary statistics dictionary
        """
        summary = {
            "total_queries": results["metadata"]["total_queries"],
            "total_duration": results["metadata"]["total_duration_seconds"],
            "providers": {}
        }
        
        for provider_name, provider_stats in results.get("statistics", {}).items():
            summary["providers"][provider_name] = {
                "success_rate": provider_stats["success_rate"],
                "successful_queries": provider_stats["successful_queries"],
                "failed_queries": provider_stats["failed_queries"],
                "average_attempts": provider_stats.get("average_attempts", 0)
            }
        
        # Overall statistics
        total_successful = sum(stats["successful_queries"] for stats in results.get("statistics", {}).values())
        total_possible = len(results.get("statistics", {})) * results["metadata"]["total_queries"]
        
        # Calculate overall average attempts
        total_attempts_all_providers = sum(stats["total_attempts"] for stats in results.get("statistics", {}).values())
        total_queries_all_providers = sum(stats["total_queries"] for stats in results.get("statistics", {}).values())
        overall_avg_attempts = total_attempts_all_providers / total_queries_all_providers if total_queries_all_providers > 0 else 0
        
        summary["overall"] = {
            "total_possible_queries": total_possible,
            "total_successful_queries": total_successful,
            "overall_success_rate": total_successful / total_possible if total_possible > 0 else 0,
            "overall_average_attempts": overall_avg_attempts
        }
        
        return summary
