"""
Crawler Scraper Node for Web Scraping with MongoDB Storage.

This node provides a workflow interface to the scraping infrastructure,
allowing users to crawl websites and automatically store the results in MongoDB
using the customer data service.

Key Features:
- Multi-domain web crawling with configurable depth and limits
- Automatic robots.txt and sitemap handling
- Browser pool support for JavaScript-heavy sites
- MongoDB storage via customer data service
- Result caching to avoid redundant scraping
- Configurable processors for domain-specific extraction

The node integrates with the generic spider infrastructure and stores all
scraped data in MongoDB with proper user/org isolation.
"""

import json
import asyncio
from collections import defaultdict
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union, ClassVar, Type
from urllib.parse import urlparse

from kiwi_app.workflow_app.schemas import WorkflowRunJobCreate
from pydantic import Field, model_validator

# Node framework imports - matching linkedin_scraping.py pattern
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
from workflow_service.services.scraping.pipelines import MongoCustomerDataPipeline

logger = get_prefect_or_regular_python_logger(
    name="workflow_service.registry.nodes.scraping.crawler_scraper_node",
    return_non_prefect_logger=False
)


class CrawlerScraperConfig(BaseNodeConfig):
    """
    Configuration for the crawler scraper node.
    
    Controls scraping behavior, performance settings, and storage options.
    These settings apply to all scraping jobs triggered by the node.
    """
    
    # Processor settings
    processor: str = Field(
        default="default",
        description="Processor name for domain-specific extraction logic. "
                   "Available processors: 'default' (generic HTML extraction), "
                   "or custom processors registered in the processor registry."
    )
    processor_init_params: Dict[str, Any] = Field(
        default={},
        description="Additional parameters passed to processor initialization. "
                   "These are processor-specific and merged with standard params."
    )
    
    # Crawling behavior
    respect_robots_txt: bool = Field(
        default=scraping_settings.RESPECT_ROBOTS_TXT,
        description="Whether to respect robots.txt rules. Disable only for sites you own "
                   "or have explicit permission to crawl without restrictions."
    )
    crawl_sitemaps: bool = Field(
        default=scraping_settings.CRAWL_SITEMAPS,
        description="Whether to discover and crawl URLs from sitemaps. "
                   "Helps find all pages on well-structured sites."
    )
    enable_blog_url_pattern_priority_boost: bool = Field(
        default=scraping_settings.DEFAULT_ENABLE_BLOG_URL_PATTERN_PRIORITY_BOOST,
        description="Boost priority for blog-like URLs (containing 'blog', 'news', 'article'). "
                   "Useful for content-focused crawling."
    )
    
    # Performance settings
    concurrent_requests_per_domain: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Number of concurrent requests allowed per domain. "
                   "Higher values speed up crawling but may overwhelm target servers."
    )
    download_delay: float = Field(
        default=0.005,
        ge=0.0,
        le=10.0,
        description="Minimum delay (in seconds) between requests to the same domain. "
                   "Increase for respectful crawling of rate-limited sites."
    )
    
    # Browser pool settings
    browser_pool_enabled: bool = Field(
        default=scraping_settings.BROWSER_POOL_ENABLED,
        description="Enable browser pool for JavaScript rendering. "
                   "Required for sites that load content dynamically."
    )
    browser_pool_size: Optional[int] = Field(
        default=scraping_settings.BROWSER_POOL_SIZE,   # 5
        ge=1,
        le=20,
        description="Number of browser instances in the pool. "
                   "More browsers allow more parallel JavaScript rendering."
    )
    browser_pool_timeout: Optional[int] = Field(
        default=scraping_settings.BROWSER_POOL_TIMEOUT,   # 5
        ge=5,
        le=300,
        description="Timeout (in seconds) for browser operations. "
                   "Increase for slow-loading pages."
    )
    
    # Debug settings
    debug_mode: bool = Field(
        default=False,
        description="Enable debug mode for verbose logging and diagnostic information. "
                   "Useful for troubleshooting crawling issues."
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level for the scraping job. "
                   "Options: DEBUG, INFO, WARNING, ERROR, CRITICAL."
    )


class CrawlerScraperInput(BaseSchema):
    """
    Input schema for the crawler scraper node.
    
    Defines the URLs to crawl, allowed domains, crawling limits,
    and caching behavior for each scraping job.
    """
    
    start_urls: List[str] = Field(
        ...,
        min_length=1,
        description="List of URLs to start crawling from. "
                   "Must be valid HTTP/HTTPS URLs. "
                   "Example: ['https://example.com/blog', 'https://example.com/news']"
    )
    allowed_domains: Optional[List[str]] = Field(
        default=None,
        min_length=1,
        max_length=5,
        description="List of domains allowed for crawling. "
                   "Only URLs from these domains will be followed and scraped. "
                   "Example: ['example.com', 'subdomain.example.com']"
    )
    
    # Crawling limits
    max_urls_per_domain: int = Field(
        default=250,
        ge=1,
        le=100000,
        description="Maximum number of URLs to discover and queue per domain. "
                   "This is the upper bound on URLs found, not necessarily scraped."
    )
    max_processed_urls_per_domain: int = Field(
        default=200,
        ge=1,
        le=10000,
        description="Maximum number of URLs to actually process (scrape content from) per domain. "
                   "Should be less than or equal to max_urls_per_domain."
    )
    max_crawl_depth: int = Field(
        default=4,
        ge=0,
        le=10,
        description="Maximum crawl depth from start URLs. "
                   "0 = only start URLs, 1 = start URLs + directly linked pages, etc."
    )
    
    # Caching options
    use_cached_scraping_results: bool = Field(
        default=True,
        description="Check for and use cached results from previous scraping jobs. "
                   "Avoids redundant scraping if recent results exist."
    )
    cache_lookback_period_days: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Number of days to look back for cached results. "
                   "Results older than this are considered stale and ignored."
    )

    # Storage settings
    is_shared: bool = Field(
        default=False,
        description="Store scraped data as organization-shared (accessible to all org users). "
                   "If False, data is only accessible to the user who triggered the job."
    )

    @model_validator(mode='after')
    def validate_limits(self) -> 'CrawlerScraperInput':
        """Ensure max_processed_urls_per_domain doesn't exceed max_urls_per_domain."""
        if self.max_processed_urls_per_domain > self.max_urls_per_domain:
            raise ValueError(
                f"max_processed_urls_per_domain ({self.max_processed_urls_per_domain}) "
                f"cannot exceed max_urls_per_domain ({self.max_urls_per_domain})"
            )
        return self


class CrawlerScraperOutput(BaseSchema):
    """
    Output schema for the crawler scraper node.
    
    Contains job execution results, statistics, sample data,
    and metadata about the scraping operation.
    """
    
    # Job identification
    job_id: str = Field(
        ...,
        description="Unique identifier for the scraping job. "
                   "Format: crawler_YYYYMMDD_HHMMSS_<uuid>"
    )
    status: str = Field(
        ...,
        description="Final status of the scraping job. "
                   "Values: 'completed', 'completed_from_cache', 'failed'"
    )
    
    # Execution statistics
    stats: Dict[str, Any] = Field(
        default_factory=dict,
        description="Detailed statistics from the scraping job including: "
                   "pages crawled, items scraped, errors encountered, "
                   "robots/sitemap handling stats, timing information."
    )
    completed_at: str = Field(
        ...,
        description="ISO 8601 timestamp when the job completed. "
                   "Example: '2024-01-15T10:30:00'"
    )
    
    # MongoDB storage information
    mongodb_namespaces: Union[str, List[str]] = Field(
        ...,
        description="MongoDB namespace pattern where data is stored. "
                   "Format: crawler_scraper_results_{uuid}_{YYYYMMDD}_{domain}. "
                   "Use this pattern to query stored results."
    )
    documents_stored: int = Field(
        default=0,
        ge=0,
        description="Number of documents successfully stored in MongoDB. "
                   "Each scraped page typically generates one document."
    )
    
    # Scraped data sample
    scraped_data: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Sample of scraped documents (up to 5 items). "
                   "Each item contains the extracted data from a scraped page. "
                   "Full results are stored in MongoDB - query using the namespace pattern."
    )
    total_scraped_count: int = Field(
        default=0,
        ge=0,
        description="Total number of documents available in MongoDB for this job. "
                   "May be larger than documents_stored if using cached results."
    )
    
    # Cache information
    used_cached_results: bool = Field(
        default=False,
        description="Whether cached results were used instead of running a new scraping job."
    )
    cached_results_age_hours: Optional[float] = Field(
        default=None,
        description="Age of cached results in hours (if cached results were used). "
                   "None if fresh scraping was performed."
    )


class CrawlerScraperNode(BaseNode[CrawlerScraperInput, CrawlerScraperOutput, CrawlerScraperConfig]):
    """
    Web Crawler Scraper Node with MongoDB Storage.
    
    This node provides a high-level interface for web scraping operations,
    integrating with the generic spider infrastructure and storing results
    in MongoDB via the customer data service.
    
    Features:
    - **Multi-domain crawling**: Crawl multiple domains in a single job
    - **Smart caching**: Reuse recent results to avoid redundant scraping
    - **Configurable processors**: Use domain-specific extraction logic
    - **Respectful crawling**: Honors robots.txt and implements rate limiting
    - **JavaScript support**: Browser pool for dynamic content rendering
    - **MongoDB storage**: Automatic storage with proper user/org isolation
    
    Usage:
    1. Configure the node with desired settings (processor, performance, etc.)
    2. Provide start URLs and allowed domains as input
    3. The node will crawl, extract, and store data automatically
    4. Results include both execution stats and sample data
    
    Example Input:
    ```json
    {
        "start_urls": ["https://example.com/blog"],
        "allowed_domains": ["example.com"],
        "max_processed_urls_per_domain": 50,
        "use_cached_scraping_results": true
    }
    ```
    """
    
    node_name: ClassVar[str] = "crawler_scraper"
    node_version: ClassVar[str] = "0.2.0"
    env_flag: ClassVar[LaunchStatus] = LaunchStatus.PRODUCTION
    
    input_schema_cls: ClassVar[Type[CrawlerScraperInput]] = CrawlerScraperInput
    output_schema_cls: ClassVar[Type[CrawlerScraperOutput]] = CrawlerScraperOutput
    config_schema_cls: ClassVar[Type[CrawlerScraperConfig]] = CrawlerScraperConfig
    
    
    config: CrawlerScraperConfig

    async def _check_and_search_for_cached_results(
        self,
        input_data: CrawlerScraperInput,
        customer_data_service: CustomerDataService,
        limit: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """
        Check for cached scraping results within the lookback period.
        
        Searches MongoDB for previous scraping results with the same start URLs.
        Results are considered valid if they're within the cache lookback period.
        
        Args:
            input_data: Input containing start URLs and cache settings
            customer_data_service: Customer data service instance
            
        Returns:
            Dictionary with cache info if valid results found, None otherwise.
            Contains: namespace, age_hours, document, metadata
        """
        try:
            # Generate the start_urls_uuid to match the namespace pattern
            start_urls_uuid = MongoCustomerDataPipeline._generate_start_urls_uuid(input_data.start_urls)
            
            # Search pattern - only use start_urls_uuid, not netloc
            namespace_pattern = f"crawler_scraper_results_{start_urls_uuid}_*"
            
            self.info(f"Searching for cached results with pattern: {namespace_pattern}")
            
            # Get the single latest document
            search_results = await customer_data_service.system_search_documents(
                namespace_pattern=namespace_pattern,
                docname_pattern="*",
                skip=0,
                limit=1,
                sort_by=customer_data_schemas.CustomerDataSortBy.UPDATED_AT,
                sort_order=customer_data_schemas.SortOrder.DESC
            )
            
            if not search_results:
                return None
            
            # Check if the result is within the lookback period
            latest_result = search_results[0]
            namespace = latest_result.metadata.namespace
            
            # Extract date from namespace: crawler_scraper_results_{uuid}_{YYYYMMDD}_{netloc}
            try:
                date_str = namespace.split('_')[-2]  # Get YYYYMMDD
                namespace_date = datetime.strptime(date_str, '%Y%m%d')
                
                # Check if within lookback period
                cutoff_date = datetime.now() - timedelta(days=input_data.cache_lookback_period_days)
                cutoff_date = cutoff_date.replace(hour=0, minute=0, second=0, microsecond=0)
                
                if namespace_date < cutoff_date:
                    self.info(f"Cached results too old: {date_str} < {cutoff_date.strftime('%Y%m%d')}")
                    return None
                
                # Calculate age in hours
                age_hours = (datetime.now() - namespace_date).total_seconds() / 3600

                namespace_segments = namespace.split('_')[:-1]
                namespace_pattern = '_'.join(namespace_segments) + "*"

                search_results = await customer_data_service.system_search_documents(
                    namespace_pattern=namespace_pattern,
                    docname_pattern="*",
                    skip=0,
                    limit=limit,
                    sort_by=customer_data_schemas.CustomerDataSortBy.CREATED_AT,
                    sort_order=customer_data_schemas.SortOrder.DESC
                )

                namespaces = defaultdict(int)
                for doc in search_results:
                    namespaces[doc.metadata.namespace] += 1
                
                return {
                    'namespaces': namespaces,
                    "namespace_pattern": namespace_pattern,
                    'age_hours': age_hours,
                    'metadata': latest_result.metadata,
                    'documents': [result.document_contents for result in search_results],
                }
                
            except (IndexError, ValueError) as e:
                self.warning(f"Could not parse date from namespace '{namespace}': {e}")
                return None
                
        except Exception as e:
            self.error(f"Error searching for cached results: {e}", exc_info=True)
            return None

    async def _fetch_sample_scraped_data(
        self,
        customer_data_service: CustomerDataService,
        namespace_pattern: str,
        user,
        org_id,
        is_shared = False,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Fetch a sample of scraped data from MongoDB.
        
        Retrieves a limited number of documents to include in the output
        as a preview of the scraped content.
        
        Args:
            customer_data_service: Customer data service instance
            namespace_pattern: MongoDB namespace pattern to search
            limit: Maximum number of documents to fetch
            
        Returns:
            List of document contents (may be empty if fetch fails)
        """
        try:
            search_results = await customer_data_service.system_search_documents(
                namespace_pattern=namespace_pattern,
                docname_pattern="*",
                skip=0,
                limit=limit,
                sort_by=customer_data_schemas.CustomerDataSortBy.CREATED_AT,
                sort_order=customer_data_schemas.SortOrder.DESC
            )
            
            return [result.document_contents for result in search_results]
            
        except Exception as e:
            self.error(f"Error fetching scraped data sample: {e}")
            return []

    async def process(
        self,
        input_data: Union[CrawlerScraperInput, Dict[str, Any]],
        runtime_config: Optional[Dict[str, Any]] = None,
        *args: Any,
        **kwargs: Any
    ) -> CrawlerScraperOutput:
        """
        Execute the web scraping job and return results.
        
        This method orchestrates the entire scraping workflow:
        1. Validates input and extracts user/org context
        2. Checks for cached results if caching is enabled
        3. Builds job configuration with all settings
        4. Executes the scraping job via the spider infrastructure
        5. Fetches sample data from MongoDB
        6. Returns comprehensive results
        
        Args:
            input_data: Input containing URLs, domains, and limits
            runtime_config: Runtime configuration with context
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments
            
        Returns:
            CrawlerScraperOutput with job results, statistics, and sample data
            
        Raises:
            ValueError: If required context (user, org_id) is missing
        """
        
        # Convert input to proper schema if needed
        if isinstance(input_data, dict):
            input_data = CrawlerScraperInput(**input_data)
        
        # Get app context and external context manager - following customer_data.py pattern
        # Get app context and external context manager - following customer_data.py pattern
        runtime_config = runtime_config.get("configurable")
        app_context: Optional[Dict[str, Any]] = runtime_config.get(APPLICATION_CONTEXT_KEY)
        ext_context= runtime_config.get(EXTERNAL_CONTEXT_MANAGER_KEY)  # : ExternalContextManager 
        customer_data_service: CustomerDataService = ext_context.customer_data_service
        
        # Extract user and org info from app context
        user = app_context.get("user")
        run_job: Optional[WorkflowRunJobCreate] = app_context.get("workflow_run_job")
        org_id = run_job.owner_org_id
        
        if not user or not org_id:
            raise ValueError("User and org_id are required for crawler scraper node")
        
        self.info(
            f"Starting crawler scraper for domains: {input_data.allowed_domains}, "
            f"use_cache: {input_data.use_cached_scraping_results}"
        )
        
        # Check for cached results if enabled
        if input_data.use_cached_scraping_results:
            cached_info = await self._check_and_search_for_cached_results(input_data, customer_data_service, limit=10)  # 1000
            
            if cached_info:
                self.info(f"Using cached results ({cached_info['age_hours']:.1f}h old)")
                
                # Fetch sample of cached data
                scraped_sample = cached_info['documents']
                
                # Extract job_id from cached document if available
                job_id = 'cached_unknown'
                if scraped_sample:
                    job_id = scraped_sample[0].get('_job_id', 'cached_unknown')
                
                return CrawlerScraperOutput(
                    job_id=job_id,
                    status='completed_from_cache',
                    stats={'cached': True, 'namespaces': cached_info['namespaces']},
                    completed_at=datetime.now().isoformat(),
                    mongodb_namespaces=cached_info['namespace_pattern'],
                    documents_stored=len(scraped_sample),  # At least one document exists
                    scraped_data=scraped_sample,  # Return first 5 items
                    total_scraped_count=len(scraped_sample),
                    used_cached_results=True,
                    cached_results_age_hours=cached_info['age_hours']
                )
        
        # Build job configuration
        job_id = f"crawler_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        
        job_config = {
            'job_id': job_id,
            'start_urls': input_data.start_urls,
            
            # Processor config
            'processor': self.config.processor,
            'processor_init_params': self.config.processor_init_params or {},
            
            # Crawling limits
            'max_urls_per_domain': input_data.max_urls_per_domain,
            'max_processed_urls_per_domain': input_data.max_processed_urls_per_domain,
            'max_crawl_depth': input_data.max_crawl_depth,
            
            # Crawling behavior
            'respect_robots_txt': self.config.respect_robots_txt,
            'crawl_sitemaps': self.config.crawl_sitemaps,
            'enable_blog_url_pattern_priority_boost': self.config.enable_blog_url_pattern_priority_boost,
            
            # Performance
            'concurrent_requests_per_domain': self.config.concurrent_requests_per_domain,
            'download_delay': self.config.download_delay,
            
            # Browser pool
            'browser_pool_enabled': self.config.browser_pool_enabled,
            'browser_pool_size': self.config.browser_pool_size,
            'browser_pool_timeout': self.config.browser_pool_timeout,
            
            # MongoDB pipeline - CRITICAL: Set these for the pipeline to work
            'mongo_pipeline_enabled': True,
            'org_id': str(org_id),
            'user': str(user.id),
            'is_shared': input_data.is_shared,
            'start_urls': input_data.start_urls,  # Required for pipeline
            
            # Debug
            'debug_mode': self.config.debug_mode,
            'log_level': self.config.log_level,
            
            # Redis
            'redis_url': scraping_settings.REDIS_URL,
            'use_in_memory': scraping_settings.USE_IN_MEMORY_QUEUE,
            
            # Custom settings for Scrapy
            'custom_settings': {
                'ITEM_PIPELINES': {
                    'workflow_service.services.scraping.pipelines.MongoCustomerDataPipeline': 300,
                },
                'CONCURRENT_REQUESTS_PER_DOMAIN': self.config.concurrent_requests_per_domain,
                'DOWNLOAD_DELAY': self.config.download_delay,
                'LOG_LEVEL': self.config.log_level,
            }
        }

        if input_data.allowed_domains:
            job_config['allowed_domains'] = input_data.allowed_domains
        
        # Billing: Calculate and allocate credits for crawling
        allocated_credits = 0.0
        estimated_urls = input_data.max_processed_urls_per_domain
        if input_data.allowed_domains:
            estimated_urls *= len(input_data.allowed_domains)
        else:
            # If no allowed domains, estimate based on start URLs
            estimated_urls *= len(input_data.start_urls)
        
        if self.billing_mode:
            try:
                # Calculate estimated cost: 0.2 cents per URL (5 URLs per cent)
                estimated_cost = estimated_urls * scraping_settings.CRAWLER_SCRAPER_PRICE_PER_URL
                
                # Allocate credits
                # from kiwi_app.billing.models import CreditType
                
                async with get_async_db_as_manager() as db_session:
                    allocation_result = await ext_context.billing_service.allocate_credits_for_operation(
                        db=db_session,
                        org_id=org_id,
                        user_id=user.id,
                        credit_type=CreditType.DOLLAR_CREDITS,
                        estimated_credits=estimated_cost,
                        operation_id=run_job.run_id,
                        metadata={
                            "node_type": "crawler_scraper",
                            "estimated_urls": estimated_urls,
                            "price_per_url": scraping_settings.CRAWLER_SCRAPER_PRICE_PER_URL,
                            # "start_urls": input_data.start_urls,
                            # "allowed_domains": input_data.allowed_domains,
                        }
                    )
                    allocated_credits = estimated_cost  # allocation_result.allocated_credits
                
                self.info(f"💳 Allocated ${allocated_credits:.4f} for estimated {estimated_urls} URLs")
                
            except InsufficientCreditsException as e:
                self.error(f"❌ Insufficient credits: {str(e)}")
                raise ValueError(f"Insufficient credits to execute crawling job. Estimated cost: ${estimated_cost:.4f} for {estimated_urls} URLs")
            except Exception as e:
                self.warning(f"⚠️ Billing allocation error (proceeding anyway): {str(e)}")
                # Continue execution even if billing fails in non-critical cases
        
        try:
            
            # Run scraping job via spider server client - async approach
            self.info(f"Running scraping job {job_id} via spider server")
            
            from workflow_service.services.worker import web_crawler_scraper_flow

            self.info(f"SCRAPER NODE Job config: {json.dumps(job_config, indent=4)}")
            
            result = await web_crawler_scraper_flow(job_config=job_config)

            self.info(f"Scraping flow completed with status: {json.dumps(result, indent=4)}")
            
            namespaces = result.get('result_namespaces', {})
            documents_stored = sum(namespaces.values())
            
            scraped_sample = []
            for namespace, count in namespaces.items():
                results = await self._fetch_sample_scraped_data(
                    customer_data_service,
                    namespace,
                    user=user,
                    org_id=org_id,
                    limit=10,
                    is_shared=input_data.is_shared,
                )
                scraped_sample.extend(results)
            
            # Billing: Adjust allocated credits with actual usage
            if allocated_credits > 0 and self.billing_mode:
                try:
                    # Calculate actual cost based on documents stored
                    actual_urls_count = documents_stored
                    actual_cost = actual_urls_count * scraping_settings.CRAWLER_SCRAPER_PRICE_PER_URL
                    
                    # Adjust credits
                    # from kiwi_app.billing.models import CreditType
                    
                    async with get_async_db_as_manager() as db_session:
                        adjustment_result = await ext_context.billing_service.adjust_allocated_credits(
                            db=db_session,
                            org_id=org_id,
                            user_id=user.id,
                            credit_type=CreditType.DOLLAR_CREDITS,
                            operation_id=run_job.run_id,
                            actual_credits=actual_cost,
                            allocated_credits=allocated_credits,
                            metadata={
                                "node_type": "crawler_scraper",
                                "actual_urls": actual_urls_count,
                                "estimated_urls": estimated_urls,
                                "price_per_url": scraping_settings.CRAWLER_SCRAPER_PRICE_PER_URL,
                                # "namespaces": list(namespaces.keys()),
                            }
                        )
                    
                    self.info(f"💳 Adjusted credits: allocated=${allocated_credits:.4f}, actual=${actual_cost:.4f} for {actual_urls_count} URLs")
                    
                except Exception as e:
                    self.warning(f"⚠️ Failed to adjust allocated credits: {str(e)}")
            
            return CrawlerScraperOutput(
                job_id=result['job_id'],
                status=result['status'],
                stats=result['stats'],
                completed_at=result['completed_at'],
                mongodb_namespaces=list(namespaces.keys()),
                documents_stored=documents_stored,
                scraped_data=scraped_sample,
                total_scraped_count=len(scraped_sample),
                used_cached_results=False
            )
            
        except Exception as e:
            # self.error(f"Scraping job failed: {str(e)}", exc_info=True)
            raise e
            
            return CrawlerScraperOutput(
                job_id=job_config.get('job_id', 'unknown'),
                status='failed',
                stats={'error': str(e)},
                completed_at=datetime.now().isoformat(),
                mongodb_namespaces="error_no_data_stored",
                documents_stored=0,
                used_cached_results=False
            )
