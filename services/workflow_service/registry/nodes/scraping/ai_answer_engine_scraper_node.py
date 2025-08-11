"""
🤖 AI Answer Engine Scraper Node for querying AI providers and storing results.

This node provides a workflow interface to query multiple AI answer engines
(Google, OpenAI, Perplexity) and automatically store the results in MongoDB
using the customer data service.

Key Features:
🌐 Multi-provider AI querying with configurable providers
📝 Template-based query construction with variable substitution
💾 Automatic MongoDB storage via customer data service
🔍 Result caching to avoid redundant queries
🚀 Configurable browser pool for parallel queries
🔄 Per-provider configuration with retry logic

The node integrates with the multi-provider query engine infrastructure and stores
all query results in MongoDB with proper user/org isolation.
"""

import json
import asyncio
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union, ClassVar, Type, Tuple, Set
from dataclasses import dataclass
from urllib.parse import urlparse

from kiwi_app.workflow_app.schemas import WorkflowRunJobCreate
from pydantic import Field, model_validator

# Node framework imports - matching crawler_scraper_node.py pattern
from kiwi_app.workflow_app.service_customer_data import CustomerDataService
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema, BaseDynamicNode, BaseNode
from workflow_service.registry.schemas.base import BaseNodeConfig, BaseSchema
from kiwi_app.workflow_app.constants import LaunchStatus
from workflow_service.config.constants import APPLICATION_CONTEXT_KEY, EXTERNAL_CONTEXT_MANAGER_KEY

# Billing imports
from kiwi_app.billing.exceptions import InsufficientCreditsException

from kiwi_app.billing.models import CreditType

from db.session import get_async_db_as_manager

# Scraping and customer data imports
from workflow_service.services.scraping.settings import scraping_settings
from kiwi_app.workflow_app import schemas as customer_data_schemas
from global_config.logger import get_prefect_or_regular_python_logger
from workflow_service.services.scraping.browsers.multi_provider_query_engine import (
    MultiProviderQueryEngine, 
    ProviderConfig
)
from workflow_service.services.scraping.browsers.config import (
    MAX_CONCURRENT_SCRAPELESS_BROWSERS, 
    ACQUISITION_TIMEOUT, 
    BROWSER_TTL
)

logger = get_prefect_or_regular_python_logger(
    name="workflow_service.registry.nodes.scraping.ai_answer_engine_scraper_node",
    return_non_prefect_logger=False
)


# ============================================================================
# Helper Classes for Modular Design
# ============================================================================

@dataclass
class CacheResult:
    """Results from cache checking operation."""
    found: bool = False
    results: List[Dict[str, Any]] = None
    categorized_results: Dict[str, List[Dict[str, Any]]] = None
    namespace: Optional[str] = None
    cached_count: int = 0
    remaining_queries: Dict[str, List[str]] = None
    found_query_providers: Set[Tuple[str, str]] = None
    
    def __post_init__(self):
        if self.results is None:
            self.results = []
        if self.categorized_results is None:
            self.categorized_results = {}
        if self.remaining_queries is None:
            self.remaining_queries = {}
        if self.found_query_providers is None:
            self.found_query_providers = set()


class QueryBuilder:
    """Handles query construction and naming operations."""
    
    @staticmethod
    def construct_queries(
        template_vars: Dict[str, str], 
        query_templates: Dict[str, List[str]]
    ) -> Dict[str, List[str]]:
        """
        Construct actual queries from templates by substituting variables.
        
        Args:
            template_vars: Dictionary of variables to substitute
            query_templates: Categorized query templates
            
        Returns:
            Dictionary of category -> list of constructed queries
        """
        categorized_queries = {}
        
        for category, category_templates in query_templates.items():
            queries = []
            for template in category_templates:
                query = template
                # Replace all variables found in the template
                for var_name, var_value in template_vars.items():
                    var_placeholder = f"{{{var_name}}}"
                    if var_placeholder in query:
                        query = query.replace(var_placeholder, var_value)
                
                queries.append(query)
            
            # Remove duplicates while preserving order within category
            seen = set()
            unique_queries = []
            for query in queries:
                if query not in seen:
                    seen.add(query)
                    unique_queries.append(query)
            
            if unique_queries:  # Only add category if it has queries
                categorized_queries[category] = unique_queries
                
        return categorized_queries
    
    @staticmethod
    def generate_namespace(entity_name: str, date_str: str) -> str:
        """Generate namespace for the AI query results."""
        # Clean entity name for use in namespace
        clean_entity = entity_name.lower().replace(' ', '_').replace('-', '_')
        # Remove any non-alphanumeric characters except underscore
        clean_entity = ''.join(c for c in clean_entity if c.isalnum() or c == '_')
        
        namespace = f"scraping_ai_answers_results_{clean_entity}_{date_str}"
        return namespace
    
    @staticmethod
    def generate_docname(query: str, provider: str, model: str = "default") -> str:
        """Generate document name for the query result."""
        # Generate deterministic UUID from query
        query_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, query)
        docname = f"scraped_query_result_{query_uuid}_{provider}_{model}"
        return docname


class CacheManager:
    """Manages cache checking and deduplication operations."""
    
    def __init__(self, customer_data_service: CustomerDataService):
        self.customer_data_service = customer_data_service
        self.logger = logger
    
    async def check_cache(
        self,
        categorized_queries: Dict[str, List[str]],
        entity_name: str,
        enable_cache: bool,
        lookback_days: int,
        enabled_providers: List[str]
    ) -> CacheResult:
        """
        Check MongoDB for cached query results within the lookback period.
        
        Returns CacheResult with found results and remaining queries to execute.
        """
        result = CacheResult()
        
        if not enable_cache:
            result.remaining_queries = categorized_queries.copy()
            return result
        
        # Debug logging
        total_queries = sum(len(queries) for queries in categorized_queries.values())
        self.logger.debug(f"🔍 Checking cache for {total_queries} queries for entity '{entity_name}', " +
                         f"enabled providers: {enabled_providers}, lookback: {lookback_days} days")
        
        try:
            # Phase 1: Broad search
            phase1_results = await self._phase1_broad_search(
                entity_name, lookback_days, enabled_providers
            )
            
            # Process Phase 1 results - only include queries that match current configuration
            filtered_out_count = 0
            for (query, provider), doc in phase1_results.items():
                # Check if this query is part of current configuration
                query_in_current_config = False
                query_category = None
                
                for category, queries in categorized_queries.items():
                    if query in queries:
                        query_in_current_config = True
                        query_category = category
                        break
                
                # Only process if query is in current configuration
                if query_in_current_config:
                    result.found_query_providers.add((query, provider))
                    
                    # Categorize result
                    if query_category not in result.categorized_results:
                        result.categorized_results[query_category] = []
                    result.categorized_results[query_category].append(doc.document_contents)
                    
                    result.results.append(doc.document_contents)
                    if not result.namespace:
                        result.namespace = doc.metadata.namespace
                else:
                    filtered_out_count += 1
                    self.logger.debug(f"  - Filtered out cached result not in current config: query='{query[:40]}...', provider={provider}")
            
            result.cached_count = len(result.results)  # Count only results matching current config
            result.found = result.cached_count > 0
            
            if filtered_out_count > 0:
                self.logger.info(f"🔍 Filtered out {filtered_out_count} cached results that don't match current query configuration")
            
            # Determine remaining queries
            found_queries = {qp[0] for qp in result.found_query_providers}
            for category, queries in categorized_queries.items():
                remaining = [q for q in queries if q not in found_queries]
                if remaining:
                    result.remaining_queries[category] = remaining
            
            # Phase 2: Exact search for remaining queries
            if result.remaining_queries:
                phase2_count = await self._phase2_exact_search(
                    result, entity_name, lookback_days, enabled_providers
                )
                result.cached_count += phase2_count
            
            # Final logging
            self.logger.debug(f"📊 Cache check complete: total_cached={result.cached_count}, " +
                            f"unique_query_providers={len(result.found_query_providers)}")
            
        except Exception as e:
            self.logger.error(f"⚠️ Error checking for cached results: {e}", exc_info=True)
            result.remaining_queries = categorized_queries.copy()
        
        return result
    
    async def _phase1_broad_search(
        self,
        entity_name: str,
        lookback_days: int,
        enabled_providers: List[str]
    ) -> Dict[Tuple[str, str], Any]:
        """
        Phase 1: Broad search for all documents with namespace prefix.
        Returns deduplicated results as {(query, provider): document}.
        """
        # Clean entity name
        clean_entity = entity_name.lower().replace(' ', '_').replace('-', '_')
        clean_entity = ''.join(c for c in clean_entity if c.isalnum() or c == '_')
        
        namespace_prefix = f"scraping_ai_answers_results_{clean_entity}_"
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        
        # Search for documents
        search_results = await self.customer_data_service.system_search_documents(
            namespace_pattern=f"{namespace_prefix}*",
            docname_pattern="*",
            skip=0,
            limit=1000,
            sort_by=customer_data_schemas.CustomerDataSortBy.CREATED_AT,
            sort_order=customer_data_schemas.SortOrder.DESC
        )
        
        self.logger.debug(f"🔍 Phase 1 search found {len(search_results) if search_results else 0} total documents")
        
        # Deduplicate and filter results
        query_provider_results = {}
        processed_count = 0
        skipped_disabled = 0
        skipped_old = 0
        
        if search_results:
            for doc in search_results:
                namespace = doc.metadata.namespace
                if namespace.startswith(namespace_prefix):
                    date_str = namespace.split("_")[-1]
                    if len(date_str) == 8 and date_str.isdigit():
                        try:
                            namespace_date = datetime.strptime(date_str, '%Y%m%d')
                            if namespace_date >= cutoff_date:
                                if (doc.document_contents and 
                                    'query' in doc.document_contents and 
                                    doc.document_contents.get('success', False)):
                                    
                                    query = doc.document_contents['query']
                                    provider = doc.document_contents.get('provider', 'unknown')
                                    processed_count += 1
                                    
                                    # Filter by enabled providers
                                    if enabled_providers and provider not in enabled_providers:
                                        skipped_disabled += 1
                                        continue
                                    
                                    key = (query, provider)
                                    # Keep only most recent for each (query, provider)
                                    if (key not in query_provider_results or 
                                        namespace_date > query_provider_results[key][1]):
                                        query_provider_results[key] = (doc, namespace_date)
                            else:
                                skipped_old += 1
                        except ValueError:
                            pass
        
        self.logger.debug(f"📊 Phase 1 statistics: processed={processed_count}, " +
                         f"skipped_disabled={skipped_disabled}, skipped_old={skipped_old}, " +
                         f"unique_results={len(query_provider_results)}")
        
        # Return only the documents (without dates)
        return {k: v[0] for k, v in query_provider_results.items()}
    
    async def _phase2_exact_search(
        self,
        result: CacheResult,
        entity_name: str,
        lookback_days: int,
        enabled_providers: List[str]
    ) -> int:
        """
        Phase 2: Exact search for specific remaining queries.
        Returns count of new results found.
        """
        self.logger.debug(f"🔍 Phase 2: Running exact searches for " +
                         f"{sum(len(queries) for queries in result.remaining_queries.values())} remaining queries")
        
        # Clean entity name
        clean_entity = entity_name.lower().replace(' ', '_').replace('-', '_')
        clean_entity = ''.join(c for c in clean_entity if c.isalnum() or c == '_')
        
        phase2_tasks = []
        phase2_metadata = []
        
        # Build search tasks
        for category, queries in result.remaining_queries.items():
            for query in queries:
                providers_to_check = enabled_providers if enabled_providers else ["openai", "google", "perplexity"]
                for provider in providers_to_check:
                    docname = QueryBuilder.generate_docname(query, provider)
                    
                    for days_ago in range(lookback_days):
                        check_date = datetime.now() - timedelta(days=days_ago)
                        date_str = check_date.strftime('%Y%m%d')
                        namespace = f"scraping_ai_answers_results_{clean_entity}_{date_str}"
                        
                        task = self.customer_data_service.system_search_documents(
                            namespace_pattern=namespace,
                            docname_pattern=docname,
                            skip=0,
                            limit=1,
                            sort_by=customer_data_schemas.CustomerDataSortBy.CREATED_AT,
                            sort_order=customer_data_schemas.SortOrder.DESC
                        )
                        phase2_tasks.append(task)
                        phase2_metadata.append({
                            'query': query,
                            'category': category,
                            'provider': provider,
                            'namespace': namespace
                        })
        
        # Execute searches
        phase2_found = 0
        phase2_skipped = 0
        
        if phase2_tasks:
            phase2_results = await asyncio.gather(*phase2_tasks, return_exceptions=True)
            
            for search_result, metadata in zip(phase2_results, phase2_metadata):
                if not isinstance(search_result, Exception) and search_result:
                    doc = search_result[0]
                    if doc.document_contents and doc.document_contents.get('success', False):
                        result_provider = doc.document_contents.get('provider', 'unknown')
                        
                        if enabled_providers and result_provider not in enabled_providers:
                            continue
                        
                        # Check for duplicates
                        query_provider_key = (metadata['query'], result_provider)
                        if query_provider_key in result.found_query_providers:
                            self.logger.debug(f"  - Skipping duplicate from Phase 2: {query_provider_key}")
                            phase2_skipped += 1
                            continue
                        
                        # Add new result (already filtered by query being in remaining_queries)
                        result.results.append(doc.document_contents)
                        result.found = True
                        phase2_found += 1
                        result.found_query_providers.add(query_provider_key)
                        
                        # Categorize
                        category = metadata['category']
                        if category not in result.categorized_results:
                            result.categorized_results[category] = []
                        result.categorized_results[category].append(doc.document_contents)
                        
                        # Remove from remaining
                        query = metadata['query']
                        if category in result.remaining_queries and query in result.remaining_queries[category]:
                            result.remaining_queries[category].remove(query)
                            if not result.remaining_queries[category]:
                                del result.remaining_queries[category]
        
        self.logger.debug(f"📊 Phase 2 statistics: found={phase2_found}, skipped_duplicates={phase2_skipped}")
        return phase2_found


class BillingHandler:
    """Handles billing operations for scraping."""
    
    def __init__(self, billing_service, logger):
        self.billing_service = billing_service
        self.logger = logger
    
    async def allocate_credits(
        self,
        org_id: str,
        user_id: str,
        run_id: str,
        total_api_calls: int,
        query_count: int,
        enabled_providers_count: int
    ) -> float:
        """Allocate credits for the operation."""
        if total_api_calls == 0:
            return 0.0
        
        estimated_cost = total_api_calls * scraping_settings.AI_ANSWER_ENGINE_PRICE_PER_QUERY
        
        try:
            async with get_async_db_as_manager() as db_session:
                await self.billing_service.allocate_credits_for_operation(
                    db=db_session,
                    org_id=org_id,
                    user_id=user_id,
                    credit_type=CreditType.DOLLAR_CREDITS,
                    estimated_credits=estimated_cost,
                    operation_id=run_id,
                    metadata={
                        "node_type": "ai_answer_engine_scraper",
                        "query_count": query_count,
                        "enabled_providers": enabled_providers_count,
                        "total_api_calls": total_api_calls,
                        "price_per_query": scraping_settings.AI_ANSWER_ENGINE_PRICE_PER_QUERY,
                    }
                )
            
            self.logger.info(f"💳 Allocated ${estimated_cost:.4f} for {total_api_calls} API calls")
            return estimated_cost
            
        except InsufficientCreditsException as e:
            self.logger.error(f"❌ Insufficient credits: {str(e)}")
            raise ValueError(f"Insufficient credits to execute queries. Cost: ${estimated_cost:.4f}")
        except Exception as e:
            self.logger.warning(f"⚠️ Billing allocation error (proceeding anyway): {str(e)}")
            return 0.0
    
    async def adjust_credits(
        self,
        org_id: str,
        user_id: str,
        run_id: str,
        allocated_credits: float,
        successful_queries: int,
        failed_queries: int,
        cached_queries: int
    ) -> None:
        """Adjust credits based on actual usage."""
        if allocated_credits <= 0:
            return
        
        actual_cost = successful_queries * scraping_settings.AI_ANSWER_ENGINE_PRICE_PER_QUERY
        
        try:
            async with get_async_db_as_manager() as db_session:
                await self.billing_service.adjust_allocated_credits(
                    db=db_session,
                    org_id=org_id,
                    user_id=user_id,
                    credit_type=CreditType.DOLLAR_CREDITS,
                    operation_id=run_id,
                    actual_credits=actual_cost,
                    allocated_credits=allocated_credits,
                    metadata={
                        "node_type": "ai_answer_engine_scraper",
                        "successful_queries": successful_queries,
                        "failed_queries": failed_queries,
                        "cached_queries": cached_queries,
                        "price_per_query": scraping_settings.AI_ANSWER_ENGINE_PRICE_PER_QUERY,
                    }
                )
            
            self.logger.info(f"💳 Adjusted credits: allocated=${allocated_credits:.4f}, actual=${actual_cost:.4f}")
            
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to adjust allocated credits: {str(e)}")


class AIAnswerEngineScraperConfig(BaseNodeConfig):
    """
    Configuration for the AI answer engine scraper node.
    
    Controls querying behavior, performance settings, provider configuration,
    and storage options. These settings apply to all queries triggered by the node.
    """
    
    # Query templates
    query_templates: Dict[str, List[str]] = Field(
        default={
            "basic_info": [
                "What is {entity_name}?",
                "Tell me about {entity_name}",
                "What does {entity_name} do?"
            ],
            "leadership": [
                "Who is the founder of {entity_name}?",
                "Who are the key executives at {entity_name}?"
            ],
            "business": [
                "What products or services does {entity_name} offer?",
                "What is the business model of {entity_name}?"
            ],
            "market": [
                "Who are the competitors of {entity_name}?",
                "What is the market position of {entity_name}?"
            ],
            "recent": [
                "What is the latest news about {entity_name}?",
                "What are the key achievements of {entity_name}?"
            ]
        },
        description="Categorized query templates with variables in {var_name} format. "
                   "Variables will be replaced with values from input template_vars."
    )
    query_templates_path: Optional[str] = Field(
        default=None,
        description=(
            "Dot-separated path inside dynamic inputs where 'query_templates' can be found. "
            "Priority order for determining templates: "
            "1) direct 'query_templates' in dynamic input, "
            "2) value at this configured path, "
            "3) this config's default 'query_templates'. "
            "If a path is provided but not found, an error is raised."
        ),
    )
    list_template_vars_path: Optional[str] = Field(
        default=None,
        description=(
            "Dot-separated path inside dynamic inputs where 'list_template_vars' can be found. "
            "Priority order: 1) direct 'list_template_vars' in inputs, 2) value at this path. "
            "If neither is provided, templates are used as-is without substitution."
        ),
    )
    entity_name_path: Optional[str] = Field(
        default=None,
        description=(
            "Dot-separated path inside dynamic inputs to resolve a single 'entity_name'. "
            "When provided (or when 'entity_name' is given directly in inputs), the node runs in single-entity mode: "
            "all queries are executed once for this entity, and 'list_template_vars' must be a dict if provided."
        ),
    )

    return_nested_entity_results: bool = Field(
        default=False,
        description="Whether to return nested entity results. "
                   "If True, the node will return a dictionary of entity results, "
                   "where each entity has a 'results' key containing a list of query results."
    )
    
    # Provider configurations
    default_providers_config: Dict[str, Dict[str, Any]] = Field(
        default={
            "google": {"enabled": True, "max_retries": 2, "retry_delay": 2.0, "timeout": ACQUISITION_TIMEOUT},
            "openai": {"enabled": True, "max_retries": 3, "retry_delay": 2.0, "timeout": ACQUISITION_TIMEOUT},
            "perplexity": {"enabled": True, "max_retries": 2, "retry_delay": 2.0, "timeout": ACQUISITION_TIMEOUT}
        },
        description="Default configuration for each AI provider. Can be overridden by input."
    )
    
    # Browser pool settings
    max_concurrent_browsers: int = Field(
        default=35,
        ge=1,
        le=MAX_CONCURRENT_SCRAPELESS_BROWSERS,
        description="Maximum number of concurrent browser instances. "
                   "More browsers allow more parallel queries."
    )
    browser_ttl: int = Field(
        default=BROWSER_TTL,
        ge=60,
        le=900,
        description="Browser time-to-live in seconds. Browsers are reused within this time."
    )
    acquisition_timeout: int = Field(
        default=ACQUISITION_TIMEOUT,
        ge=10,
        le=300,
        description="Timeout for acquiring a browser from the pool."
    )
    use_browser_profiles: bool = Field(
        default=True,
        description="Whether to use browser profiles for better anti-detection."
    )
    persist_browser_profile: bool = Field(
        default=False,
        description="Whether to persist browser profiles between sessions."
    )


class AIAnswerEngineScraperInput(DynamicSchema):
    """
    Dynamic input schema for the AI answer engine scraper node with typed fields.
    
    Accepts both fixed, typed fields and arbitrary extra dynamic fields. When the
    typed fields are omitted, the node can optionally resolve them from dot-paths
    configured in the node config. If `list_template_vars` is not provided anywhere,
    templates are used as-is (no variable substitution).
    """

    # Optional by design. If not provided, templates are used as-is.
    # Can be a list[dict] in multi-entity mode, or a dict in single-entity mode (when entity_name is provided).
    list_template_vars: Optional[Union[List[Dict[str, str]], Dict[str, str]]] = Field(
        default=None,
        description=(
            "List of template variables for multiple entities. "
            "Each dict must include 'entity_name' key. "
            "Example: [{'entity_name': 'OpenAI', 'location': 'San Francisco'}, "
            "{'entity_name': 'Tesla', 'industry': 'Automotive'}]"
        ),
    )

    entity_name: Optional[str] = Field(
        default="generic",
        description=(
            "Explicit single 'entity_name'. When set (or resolved via config path), the node switches to single-entity mode: "
            "all queries are run once for this entity. In this mode, 'list_template_vars' (if provided) must be a dict; "
            "it need not include 'entity_name', but if present it must equal this field."
        ),
    )

    query_templates: Optional[Dict[str, List[str]]] = Field(
        default=None,
        description=(
            "Optional categorized query templates to override config defaults. "
            "Templates use {var_name} format for variable substitution."
        ),
    )

    providers_config: Optional[Dict[str, Dict[str, Any]]] = Field(
        default=None,
        description=(
            "Optional provider configuration to override defaults. "
            "Example: {'openai': {'enabled': False}, 'google': {'max_retries': 5}}"
        ),
    )

    # MongoDB caching settings
    enable_mongodb_cache: bool = Field(
        default=True,
        description=(
            "Enable checking MongoDB for cached query results before running new queries."
        ),
    )
    cache_lookback_days: int = Field(
        default=14,
        ge=1,
        le=90,
        description=(
            "Number of days to look back for cached results. Results older than this are considered stale."
        ),
    )

    # Storage settings
    is_shared: bool = Field(
        default=False,
        description=(
            "Store query results as organization-shared (accessible to all org users). "
            "If False, data is only accessible to the user who triggered the job."
        ),
    )

    @model_validator(mode="after")
    def validate_entity_names(self) -> "AIAnswerEngineScraperInput":
        """Validate entity and template vars consistency for single-/multi-entity modes."""
        # Single-entity mode
        if self.entity_name:
            if self.list_template_vars is not None and not isinstance(self.list_template_vars, dict):
                raise ValueError(
                    "When 'entity_name' is provided, 'list_template_vars' must be a dict if provided"
                )
            if isinstance(self.list_template_vars, dict):
                if "entity_name" in self.list_template_vars and self.list_template_vars["entity_name"] != self.entity_name:
                    raise ValueError(
                        "When 'entity_name' is provided, 'list_template_vars.entity_name' (if present) must equal 'entity_name'"
                    )
            return self

        # Multi-entity mode
        if self.list_template_vars is not None:
            if not isinstance(self.list_template_vars, list):
                raise ValueError("'list_template_vars' must be a list of dicts when provided in multi-entity mode")
            for i, template_vars in enumerate(self.list_template_vars):
                if not isinstance(template_vars, dict):
                    raise ValueError(f"list_template_vars[{i}] must be a dict")
                if "entity_name" not in template_vars:
                    raise ValueError(f"list_template_vars[{i}] must include 'entity_name' key")
        return self


class AIAnswerEngineScraperOutput(BaseSchema):
    """
    Output schema for the AI answer engine scraper node.
    
    Contains job execution results, statistics, sample data,
    and metadata about the querying operation.
    """
    
    # Job identification
    job_id: str = Field(
        ...,
        description="Unique identifier for the query job. "
                   "Format: ai_query_YYYYMMDD_HHMMSS_<uuid>"
    )
    status: str = Field(
        ...,
        description="Final status of the query job. "
                   "Values: 'completed', 'completed_from_cache', 'failed'"
    )
    
    # Execution statistics
    total_queries_executed: int = Field(
        default=0,
        description="Total number of queries executed across all providers."
    )
    successful_queries: int = Field(
        default=0,
        description="Number of queries that completed successfully."
    )
    failed_queries: int = Field(
        default=0,
        description="Number of queries that failed."
    )
    cached_results_used: int = Field(
        default=0,
        description="Number of queries served from cache."
    )
    
    provider_stats: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-provider statistics including success rate, duration, average attempts per query, etc. "
                   "Each provider entry contains: total_queries, successful_queries, failed_queries, "
                   "success_rate, total_duration_seconds, average_duration_seconds, "
                   "average_attempts_per_query, and total_attempts."
    )
    
    completed_at: str = Field(
        ...,
        description="ISO 8601 timestamp when the job completed."
    )
    
    # MongoDB storage information
    mongodb_namespaces: List[str] = Field(
        default_factory=list,
        description="MongoDB namespaces where data is stored. "
                   "Format: scraping_ai_answers_results_{entity_name}_{YYYYMMDD}"
    )
    documents_stored: int = Field(
        default=0,
        description="Number of documents successfully stored in MongoDB."
    )
    
    # Query results sample
    query_results: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description=(
            "Sample of flattened query results (up to 10 items). "
            "Each item has: {query, markdown, provider, category}. "
            "Full results are stored in MongoDB under their respective namespaces."
        )
    )
    
    # Per-entity results
    entity_results: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Results grouped by entity name. "
                   "Each entity has its own namespace, query count, sample results, "
                   "and results categorized by query categories."
    )
    
    # Constructed queries
    executed_queries: List[str] = Field(
        default_factory=list,
        description="List of actual queries executed after template substitution."
    )
    
    # Cache information
    used_cached_results: bool = Field(
        default=False,
        description="Whether any cached results were used instead of running new queries."
    )


class AIAnswerEngineScraperNode(BaseDynamicNode):  # [AIAnswerEngineScraperInput, AIAnswerEngineScraperOutput, AIAnswerEngineScraperConfig]
    """
    🤖 AI Answer Engine Scraper Node with MongoDB Storage.
    
    This node provides a high-level interface for querying AI answer engines,
    integrating with the multi-provider query engine and storing results
    in MongoDB via the customer data service.
    
    Features:
    - 📝 **Template-based queries**: Construct queries from templates with variable substitution
    - 🌐 **Multi-provider support**: Query Google, OpenAI, and Perplexity in parallel
    - 💾 **Smart caching**: Check MongoDB for recent results before querying
    - 🔄 **Configurable retry logic**: Per-provider retry configuration
    - 🚀 **Browser pool optimization**: Efficient browser reuse for parallel queries
    - 🗄️ **MongoDB storage**: Automatic storage with proper user/org isolation
    
    Usage:
    1. ⚙️ Configure the node with query templates and provider settings
    2. 📋 Provide template variables (must include entity_name) as input
    3. 🔄 The node will construct queries, check cache, execute, and store results
    4. 📊 Results include execution stats and sample data
    
    Example Input:
    ```json
    {
        "template_vars": {
            "entity_name": "OpenAI",
            "industry": "AI"
        },
        "providers_config": {
            "openai": {"enabled": true, "max_retries": 5}
        }
    }
    ```
    """
    
    node_name: ClassVar[str] = "ai_answer_engine_scraper"
    node_version: ClassVar[str] = "0.2.0"
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.PRODUCTION
    
    input_schema_cls: ClassVar[Type[AIAnswerEngineScraperInput]] = AIAnswerEngineScraperInput
    output_schema_cls: ClassVar[Type[AIAnswerEngineScraperOutput]] = AIAnswerEngineScraperOutput
    config_schema_cls: ClassVar[Type[AIAnswerEngineScraperConfig]] = AIAnswerEngineScraperConfig
    
    config: AIAnswerEngineScraperConfig

    def _build_providers_config(
        self,
        input_providers_config: Optional[Dict[str, Dict[str, Any]]]
    ) -> Dict[str, ProviderConfig]:
        """Build provider configurations with overrides."""
        providers_config = {}
        for provider, default_config in self.config.default_providers_config.items():
            provider_config = ProviderConfig(**default_config)
            
            # Override with input config if provided
            if input_providers_config and provider in input_providers_config:
                input_config = input_providers_config[provider]
                for key in ['enabled', 'max_retries', 'retry_delay', 'timeout']:
                    if key in input_config:
                        setattr(provider_config, key, input_config[key])
            
            providers_config[provider] = provider_config
        
        return providers_config


    def _resolve_path(self, data: Dict[str, Any], path: str) -> Any:
        """
        Resolve a dot-notation path in nested dynamic inputs, similar to
        workflow_runner_node._resolve_path.
        
        Args:
            data: Source dynamic inputs
            path: Dot path (e.g., 'payload.inputs.vars')
        Returns:
            The value at the path, or None if not found
        """
        if not path:
            return None
        parts = path.split('.')
        current: Any = data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list):
                try:
                    index = int(part)
                    if 0 <= index < len(current):
                        current = current[index]
                    else:
                        return None
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return current


    async def _store_query_result(
        self,
        query: str,
        provider: str,
        result: Dict[str, Any],
        namespace: str,
        customer_data_service: CustomerDataService,
        user,
        org_id,
        is_shared: bool
    ) -> bool:
        """
        Store a single query result in MongoDB.
        
        Args:
            query: The query that was executed
            provider: The provider that executed the query
            result: The query result data
            namespace: MongoDB namespace
            customer_data_service: Customer data service instance
            user: User object
            org_id: Organization ID
            is_shared: Whether to share with organization
            
        Returns:
            Boolean indicating success
        """
        try:
            docname = QueryBuilder.generate_docname(query, provider)
            
            # Store the full result from MultiProviderQueryEngine
            # The result contains: query, query_index, provider, success, attempts, 
            # start_time, end_time, response (normalized), error, duration_seconds
            document_data = result
            
            # Store in MongoDB
            
            async with get_async_db_as_manager() as db_session:
                is_created = await customer_data_service._create_or_update_unversioned_document_no_lock(
                    db=db_session,
                    org_id=org_id,
                    namespace=namespace,
                    docname=docname,
                    is_shared=is_shared,
                    user=user,
                    data=document_data,
                    is_called_from_workflow=True,
                )
                
                self.debug(f"💾 Stored query result: namespace={namespace}, docname={docname}, created={is_created}")
                return True
                
        except Exception as e:
            self.error(f"⚠️ Failed to store query result: {e}", exc_info=True)
            return False

    def _flatten_query_results(self, entity_results: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Flatten categorized results across all entities into a uniform list.

        Output item keys:
        - query: str
        - markdown: str
        - provider: str
        - category: str

        We rely on `entity_results[entity]['categorized_results']` which already groups
        result objects (new or cached) by category. Each result object is expected to be the
        full result dictionary produced by `MultiProviderQueryEngine`, i.e., it contains
        top-level `query`, `provider`, and a `response` with `processed_data`.
        """
        flattened: List[Dict[str, Any]] = []
        for _entity_name, data in entity_results.items():  # [entity_name]['categorized_results'][category]List["response"][raw response for single query...]
            categorized = data.get("categorized_results", {}) or {}
            for category, results in categorized.items():
                for res in results or []:
                    response = res.get("response", {})
                    if not isinstance(response, dict):
                        continue
                    query_val = response.get("query", "")
                    provider_val = response.get("provider", "unknown")
                    markdown_val = response.get("markdown", "")
                    links_val = response.get("links", [])
                    citations_val = response.get("citations", [])
                    flattened.append({
                        "query": query_val,
                        "markdown": markdown_val,
                        "provider": provider_val,
                        "category": category,
                        "links": links_val,
                        # "citations": citations_val,
                    })
        return flattened

    async def process(
        self,
        input_data: Union[AIAnswerEngineScraperInput, Dict[str, Any]],
        runtime_config: Optional[Dict[str, Any]] = None,
        *args: Any,
        **kwargs: Any
    ) -> AIAnswerEngineScraperOutput:
        """
        Execute the AI query job and return results.
        
        This method orchestrates the entire querying workflow:
        1. Validates input and extracts user/org context
        2. Constructs queries from templates
        3. Checks for cached results if caching is enabled
        4. Executes queries via multi-provider engine
        5. Stores results in MongoDB
        6. Returns comprehensive results
        
        Args:
            input_data: Input containing template vars and optional provider config
            runtime_config: Runtime configuration with context
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments
            
        Returns:
            AIAnswerEngineScraperOutput with job results and statistics
            
        Raises:
            ValueError: If required context (user, org_id) is missing
        """
        
        # Normalize to both a parsed typed model and a raw dict to support
        # dynamic dot-path resolution and typed defaults/validation.
        if isinstance(input_data, dict):
            input_parsed = AIAnswerEngineScraperInput(**input_data)
            raw_inputs = input_data
        else:
            input_parsed = input_data  # Already a model
            raw_inputs = input_data.model_dump() if hasattr(input_data, "model_dump") else dict(input_data)
        
        # Get app context and external context manager
        runtime_config = runtime_config.get("configurable")
        app_context: Optional[Dict[str, Any]] = runtime_config.get(APPLICATION_CONTEXT_KEY)
        ext_context = runtime_config.get(EXTERNAL_CONTEXT_MANAGER_KEY)
        customer_data_service: CustomerDataService = ext_context.customer_data_service
        
        # Extract user and org info from app context
        user = app_context.get("user")
        run_job: Optional[WorkflowRunJobCreate] = app_context.get("workflow_run_job")
        org_id = run_job.owner_org_id
        
        if not user or not org_id:
            raise ValueError("User and org_id are required for AI answer engine scraper node")
        
        # Initialize helper classes
        cache_manager = CacheManager(customer_data_service)
        billing_handler = BillingHandler(ext_context.billing_service, self)
        
        # Process multiple entities
        start_time = datetime.now()
        # Resolve dynamic inputs following the priority order:
        # 1) Direct top-level inputs
        # 2) Configured dot paths into dynamic inputs
        # 3) Defaults (only for query_templates). list_template_vars must be provided (directly or via path)

        # Resolve list_template_vars
        resolved_list_template_vars: Optional[Union[List[Dict[str, Any]], Dict[str, Any]]] = None
        if input_parsed.list_template_vars is not None:
            resolved_list_template_vars = input_parsed.list_template_vars
        elif self.config.list_template_vars_path:
            resolved_list_template_vars = self._resolve_path(
                raw_inputs, self.config.list_template_vars_path
            )
            if resolved_list_template_vars is None:
                raise ValueError(
                    f"list_template_vars_path='{self.config.list_template_vars_path}' provided but no data found at that path"
                )
        # If provided as a list, validate list semantics here; dict is allowed for single-entity mode
        if isinstance(resolved_list_template_vars, list):
            for i, template_vars in enumerate(resolved_list_template_vars):
                if not isinstance(template_vars, dict):
                    raise ValueError(f"list_template_vars[{i}] must be a dict")
                if 'entity_name' not in template_vars:
                    raise ValueError(f"list_template_vars[{i}] must include 'entity_name' key")

        # Resolve query_templates
        resolved_query_templates: Optional[Dict[str, List[str]]] = None
        if input_parsed.query_templates is not None:
            resolved_query_templates = input_parsed.query_templates
        elif self.config.query_templates_path:
            resolved_query_templates = self._resolve_path(raw_inputs, self.config.query_templates_path)
            if resolved_query_templates is None:
                raise ValueError(
                    f"query_templates_path='{self.config.query_templates_path}' provided but no data found at that path"
                )
        else:
            resolved_query_templates = self.config.query_templates

        if not isinstance(resolved_query_templates, dict):
            raise ValueError("'query_templates' must be a dict of {category: [templates]} when provided")

        # Resolve single-entity name if provided directly or via path
        resolved_entity_name: Optional[str] = None
        if input_parsed.entity_name:
            resolved_entity_name = input_parsed.entity_name
        elif self.config.entity_name_path:
            resolved_entity_name = self._resolve_path(raw_inputs, self.config.entity_name_path)  # type: ignore[arg-type]

        # Determine mode and entities to process
        no_template_vars = resolved_list_template_vars in (None, [], {})
        single_entity_mode = resolved_entity_name is not None

        if single_entity_mode:
            # list_template_vars must be a dict if provided
            if isinstance(resolved_list_template_vars, list):
                raise ValueError(
                    "In single-entity mode, 'list_template_vars' must be a dict when provided"
                )
            # Build single entity template vars
            if isinstance(resolved_list_template_vars, dict):
                tv = dict(resolved_list_template_vars)
                if 'entity_name' in tv and tv['entity_name'] != resolved_entity_name:
                    raise ValueError(
                        "In single-entity mode, 'list_template_vars.entity_name' (if present) must equal 'entity_name'"
                    )
                tv['entity_name'] = resolved_entity_name  # enforce
                entities_to_process: List[Dict[str, Any]] = [tv]
            else:
                # No substitution
                entities_to_process = [{"entity_name": resolved_entity_name}]
        else:
            # Multi-entity mode
            if resolved_list_template_vars is None or resolved_list_template_vars == []:
                entities_to_process = [{"entity_name": "generic"}]
            else:
                if not isinstance(resolved_list_template_vars, list):
                    raise ValueError(
                        "In multi-entity mode, 'list_template_vars' must be a list of dicts when provided"
                    )
                entities_to_process = resolved_list_template_vars

        self.info(f"🚀 Starting AI answer engine scraper for {len(entities_to_process)} entities")
        
        # Generate single date_str for consistency
        date_str = datetime.now().strftime('%Y%m%d')
        
        # Build provider configurations first (needed for cache checking)
        providers_config = self._build_providers_config(input_parsed.providers_config)
        enabled_providers = [p for p, config in providers_config.items() if config.enabled]
        
        # Collect all queries for all entities
        all_queries = []
        entity_query_map = {}  # Map queries back to entities and categories
        entity_namespaces = {}  # Store namespaces per entity
        entity_results = {}  # Store results per entity
        total_cached_results = 0
        used_any_cache = False
        query_provider_mapping = {}  # Map query -> list of providers that need to be queried
        
        # Process each entity
        for template_vars in entities_to_process:
            entity_name = template_vars.get('entity_name', 'generic') if template_vars else 'generic'
            
            # Construct categorized queries for this entity
            query_templates = resolved_query_templates or self.config.query_templates
            tv_for_queries = {} if no_template_vars else template_vars
            entity_queries = QueryBuilder.construct_queries(tv_for_queries, query_templates)
            
            # Generate namespace for this entity
            namespace = QueryBuilder.generate_namespace(entity_name, date_str)
            entity_namespaces[entity_name] = namespace
            
            # Map queries to entity and category (but don't add to all_queries yet)
            for category, queries in entity_queries.items():
                for query in queries:
                    entity_query_map[query] = {'entity': entity_name, 'category': category}
            
            # Initialize entity results
            entity_results[entity_name] = {
                'namespace': namespace,
                'categorized_queries': entity_queries,
                'cached_count': 0,
                'new_count': 0,
                'results': [],
                'categorized_results': {}
            }
            
            # Check for cached results if enabled
            cache_result = await cache_manager.check_cache(
                entity_queries, 
                entity_name,
                input_data.enable_mongodb_cache,
                input_data.cache_lookback_days,
                enabled_providers
            )
            
            if cache_result.found and cache_result.cached_count > 0:
                num_unique_queries = len(set(qp[0] for qp in cache_result.found_query_providers))
                # Fix: Show actual unique count instead of total cached count
                self.info(f"📋 Found {len(cache_result.found_query_providers)} cached results for {entity_name}: " +
                         f"{num_unique_queries} unique queries × {len(enabled_providers)} providers " +
                         f"(providers: {', '.join(enabled_providers)})")
                entity_results[entity_name]['cached_count'] = cache_result.cached_count
                entity_results[entity_name]['results'].extend(cache_result.results)
                entity_results[entity_name]['categorized_results'] = cache_result.categorized_results
                total_cached_results += cache_result.cached_count
                used_any_cache = True
                
                # Build query-provider mapping based on cache results
                cached_query_provider_map = defaultdict(set)
                for query, provider in cache_result.found_query_providers:
                    cached_query_provider_map[query].add(provider)
                
                # For each query in this entity, determine which providers need to be queried
                for category, queries in entity_queries.items():
                    for query in queries:
                        cached_providers = cached_query_provider_map.get(query, set())
                        # Only query providers that don't have cached results
                        providers_to_query = [p for p in enabled_providers if p not in cached_providers]
                        
                        if providers_to_query:
                            # This query needs to be executed for some providers
                            if query not in query_provider_mapping:
                                query_provider_mapping[query] = []
                            query_provider_mapping[query].extend(providers_to_query)
                            
                            # Add to all_queries for execution
                            if query not in all_queries:
                                all_queries.append(query)
                        else:
                            # All providers have cached results
                            self.debug(f"✅ Query fully cached for all providers: {query[:50]}...")
                
                # Count queries that are fully cached (all providers)
                fully_cached_count = sum(1 for q in cached_query_provider_map 
                                       if all(p in cached_query_provider_map[q] for p in enabled_providers))
                if fully_cached_count > 0:
                    self.info(f"📝 {fully_cached_count} queries fully cached for all {len(enabled_providers)} providers")
                    
                    # Update entity queries to only include remaining queries
                entity_results[entity_name]['remaining_queries'] = cache_result.remaining_queries
            else:
                # No cache or no results found - need to query all
                for category, queries in entity_queries.items():
                    for query in queries:
                        if query not in all_queries:
                            all_queries.append(query)
                        if query not in query_provider_mapping:
                            query_provider_mapping[query] = enabled_providers.copy()
        
        cache_check_elapsed = (datetime.now() - start_time).total_seconds()
        self.info(f"📊 Total queries to execute: {len(all_queries)} (after removing {total_cached_results} cached) - Cache check took {cache_check_elapsed:.1f}s")
        
        # Debug: Show query-provider mapping
        if query_provider_mapping:
            total_api_calls = sum(len(providers) for providers in query_provider_mapping.values())
            self.debug(f"🔍 Query-provider mapping: {len(query_provider_mapping)} unique queries → {total_api_calls} total API calls")
        
        # If all results are cached, return early
        if len(all_queries) == 0 and used_any_cache:
            # Aggregate all cached results
            flat_cached_results = self._flatten_query_results(entity_results)
            
            total_elapsed = (datetime.now() - start_time).total_seconds()
            self.info(f"✨ All results served from cache! Completed in ⏱️ {total_elapsed:.1f}s")
            
            return AIAnswerEngineScraperOutput(
                job_id=f"ai_query_cached_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                status='completed_from_cache',
                total_queries_executed=0,
                successful_queries=0,
                failed_queries=0,
                cached_results_used=total_cached_results,
                provider_stats={},
                completed_at=datetime.now().isoformat(),
                mongodb_namespaces=list(entity_namespaces.values()),
                documents_stored=total_cached_results,
                query_results=flat_cached_results,  # Sample of flattened items
                entity_results=entity_results if self.config.return_nested_entity_results else None,
                executed_queries=[],
                used_cached_results=True
            )
        
        # Build job configuration
        job_id = f"ai_query_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        
        # Browser pool configuration
        browser_pool_config = {
            "browser_ttl": self.config.browser_ttl,
            "use_profiles": self.config.use_browser_profiles,
            "acquisition_timeout": self.config.acquisition_timeout,
            "persist_profile": self.config.persist_browser_profile,
        }
        
        # Billing: Calculate and allocate credits for queries
        allocated_credits = 0.0
        enabled_providers_count = sum(1 for p in providers_config.values() if p.enabled)
        
        if len(all_queries) > 0 and self.billing_mode:
            # Calculate total API calls needed
            total_api_calls = sum(
                len(query_provider_mapping.get(query, enabled_providers))
                for query in all_queries
            )
            
            # Allocate credits
            allocated_credits = await billing_handler.allocate_credits(
                org_id=org_id,
                user_id=user.id,
                run_id=run_job.run_id,
                total_api_calls=total_api_calls,
                query_count=len(all_queries),
                enabled_providers_count=enabled_providers_count
            )
            
            # Log cache optimization
            cache_savings = (len(all_queries) * enabled_providers_count) - total_api_calls
            if cache_savings > 0:
                self.info(f"💸 Cache optimization saved {cache_savings} API calls")
        
        # Execute queries only if there are any non-cached queries
        if len(all_queries) > 0:
            try:
                # Create and run the multi-provider query engine
                engine = MultiProviderQueryEngine(
                    queries=all_queries,
                    providers_config=providers_config,
                    query_provider_mapping=query_provider_mapping,  # Pass the optimized mapping
                    max_concurrent_browsers=self.config.max_concurrent_browsers,
                    browser_pool_config=browser_pool_config,
                    output_file=None,  # We don't need file output
                )
                
                # Log optimization details
                actual_tasks = sum(len(query_provider_mapping.get(q, [])) if q in query_provider_mapping 
                                 else enabled_providers_count for q in all_queries)
                self.info(f"🔄 Executing {len(all_queries)} queries with provider-specific optimization ({actual_tasks} total API calls)")
                
                # Execute all queries
                query_start_time = datetime.now()
                results = await engine.process_all_queries()
                query_execution_time = (datetime.now() - query_start_time).total_seconds()
                self.info(f"⏱️ Query execution completed in {query_execution_time:.1f}s")
                
                # Process and store results
                documents_stored = 0
                all_query_results = []
                
                # Prepare storage tasks for concurrent execution
                storage_tasks = []
                storage_metadata = []
                
                for provider_name, provider_results in results.get('results', {}).items():  # ["results"][provider_name]List["response"][raw response for single query...]
                    for result in provider_results:
                        if result.get('success', False) and result.get('response'):
                            query = result['query']
                            query_info = entity_query_map.get(query, {'entity': 'unknown', 'category': 'unknown'})
                            entity_name = query_info['entity']
                            category = query_info['category']
                            namespace = entity_namespaces.get(entity_name, 'unknown')
                            
                            # Create storage task
                            task = self._store_query_result(
                                query=query,
                                provider=provider_name,
                                result=result,
                                namespace=namespace,
                                customer_data_service=customer_data_service,
                                user=user,
                                org_id=org_id,
                                is_shared=input_data.is_shared
                            )
                            storage_tasks.append(task)
                            
                            # Store metadata for processing results
                            storage_metadata.append({
                                'query': query,
                                'provider': provider_name,
                                'entity_name': entity_name,
                                'category': category,
                                'result': result  # result ==> ["response"][raw response for single query...]
                            })
                
                # Execute all storage tasks concurrently
                if storage_tasks:
                    storage_results = await asyncio.gather(*storage_tasks, return_exceptions=True)
                    
                    for stored, metadata in zip(storage_results, storage_metadata):
                        if not isinstance(stored, Exception) and stored:
                            documents_stored += 1
                            entity_name = metadata['entity_name']
                            category = metadata['category']
                            entity_results[entity_name]['new_count'] += 1
                        
                        # Add to results regardless of storage success
                        # Use the full result object from metadata
                        result_obj = metadata['result']
                        all_query_results.append(result_obj)
                        
                        # Add to entity results
                        entity_results[entity_name]['results'].append(result_obj)
                        
                        # Add to categorized results
                        if category not in entity_results[entity_name]['categorized_results']:
                            entity_results[entity_name]['categorized_results'][category] = []
                        entity_results[entity_name]['categorized_results'][category].append(result_obj)  # [entity_name]['categorized_results'][category]List["response"][raw response for single query...]
                
                # Get statistics and calculate additional metrics
                stats = results.get('statistics', {})
                total_executed = sum(s.get('total_queries', 0) for s in stats.values())
                total_successful = sum(s.get('successful_queries', 0) for s in stats.values())
                total_failed = sum(s.get('failed_queries', 0) for s in stats.values())
                
                # Calculate average attempts per provider
                provider_detailed_stats = {}
                for provider_name, provider_results in results.get('results', {}).items():
                    if provider_results:
                        total_attempts = sum(r.get('attempts', 1) for r in provider_results)
                        avg_attempts = total_attempts / len(provider_results)
                        success_count = sum(1 for r in provider_results if r.get('success', False))
                        
                        provider_detailed_stats[provider_name] = {
                            **stats.get(provider_name, {}),
                            'average_attempts_per_query': avg_attempts,
                            'total_attempts': total_attempts
                        }
                        
                        # Log provider-specific stats
                        self.info(
                            f"📈 Provider {provider_name.upper()} stats: "
                            f"Success rate: {success_count}/{len(provider_results)} ({success_count/len(provider_results)*100:.1f}%), "
                            f"Avg attempts: {avg_attempts:.2f}, "
                            f"Avg duration: {stats.get(provider_name, {}).get('average_duration_seconds', 0):.1f}s"
                        )
                
                # Log overall summary stats
                overall_success_rate = total_successful / total_executed if total_executed > 0 else 0
                query_elapsed = (datetime.now() - start_time).total_seconds()
                self.info(
                    f"🎯 Overall query execution summary: "
                    f"Total executed: {total_executed}, "
                    f"Successful: ✅ {total_successful} ({overall_success_rate*100:.1f}%), "
                    f"Failed: ❌ {total_failed}, "
                    f"Cached used: 💾 {total_cached_results} - "
                    f"⏱️ Total time: {query_elapsed:.1f}s"
                )
                
            except Exception as e:
                self.error(f"❌ AI query job failed: {str(e)}", exc_info=True)
                
                return AIAnswerEngineScraperOutput(
                    job_id=job_id,
                    status='failed',
                    total_queries_executed=0,
                    successful_queries=0,
                    failed_queries=len(all_queries),
                    cached_results_used=total_cached_results,
                    provider_stats={'error': str(e)},
                    completed_at=datetime.now().isoformat(),
                    mongodb_namespaces=list(entity_namespaces.values()),
                    documents_stored=0,
                    entity_results=entity_results if self.config.return_nested_entity_results else None,
                    executed_queries=all_queries,
                    used_cached_results=used_any_cache
                )
        else:
            # No new queries to execute
            stats = {}
            provider_detailed_stats = {}
            total_executed = 0
            total_successful = 0
            total_failed = 0
            all_query_results = []
            documents_stored = 0
        
        # Aggregate all results (cached + new) and log per-entity stats
        final_all_results = []
        for entity_name, entity_data in entity_results.items():
            final_all_results.extend(entity_data['results'])
            
            # Log per-entity summary
            unique_queries_count = sum(len(queries) for queries in entity_data.get('categorized_queries', {}).values())
            
            self.info(
                f"🏢 Entity '{entity_name}' summary: "
                f"Unique queries: {unique_queries_count}, "
                f"Total results: {len(entity_data['results'])} "
                f"(Cached: 💾 {entity_data['cached_count']}, New: 🆕 {entity_data['new_count']}), "
                f"Categories: 📁 {list(entity_data['categorized_results'].keys())}"
            )
        
        # Billing: Adjust allocated credits with actual usage
        if allocated_credits > 0 and self.billing_mode:
            await billing_handler.adjust_credits(
                org_id=org_id,
                user_id=user.id,
                run_id=run_job.run_id,
                allocated_credits=allocated_credits,
                successful_queries=total_successful,
                failed_queries=total_failed,
                cached_queries=total_cached_results
            )
        
        # Log final completion time
        total_elapsed = (datetime.now() - start_time).total_seconds()
        self.info(f"✨ Completed AI answer engine scraper in ⏱️ {total_elapsed:.1f}s total")
        
        # Build flattened query_results structure for output
        flat_query_results = self._flatten_query_results(entity_results)

        return AIAnswerEngineScraperOutput(
            job_id=job_id,
            status='completed' if not used_any_cache else 'completed_with_cache',
            total_queries_executed=total_executed,
            successful_queries=total_successful,
            failed_queries=total_failed,
            cached_results_used=total_cached_results,
            provider_stats=provider_detailed_stats,
            completed_at=datetime.now().isoformat(),
            mongodb_namespaces=list(entity_namespaces.values()),
            documents_stored=documents_stored + total_cached_results,
            query_results=flat_query_results,  # Sample of 10 flattened items
            entity_results=entity_results if self.config.return_nested_entity_results else None,
            executed_queries=all_queries,
            used_cached_results=used_any_cache
        )
