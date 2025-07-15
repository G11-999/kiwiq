"""
Generic Spider with Custom Processing Hooks.

This module provides a flexible spider that can be configured via API
with custom processing hooks for domain-specific logic.

## Key Features:

### Processor Configuration
Processors can now be initialized with custom parameters through job configuration:
- `processor_init_params`: Dictionary of parameters passed to processor __init__
- `allowed_domains` is automatically passed from spider configuration
- Useful for domain-specific configuration, API keys, custom behavior, etc.

Example:
```python
job_config = {
    'processor': 'multi_site',
    'allowed_domains': ['example.com', 'another.com'],
    'processor_init_params': {
        # allowed_domains is automatically added from above
        'api_key': 'your_key',
        'custom_param': 'value'
    }
}
```

### Subdomain Support
Enable subdomain crawling with global setting:

```python
'custom_settings': {
    'ALLOW_ALL_SUBDOMAINS_BY_DEFAULT': True
}
```

When enabled, if 'example.com' is in allowed_domains, the spider will also crawl:
- sub.example.com
- deep.sub.example.com
- any.subdomain.example.com

This is particularly useful for crawling sites that use multiple subdomains for
different content types (blog.site.com, support.site.com, docs.site.com, etc).
"""
import re
import json
import logging
from typing import Dict, Any, List, Optional, Callable, Type
from datetime import datetime
from urllib.parse import urlparse, urljoin

from scrapy import Spider, Request
from scrapy.http import Response
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from .settings import scraping_settings, get_queue_key, calculate_priority_from_depth, parse_domain_from_url, get_processed_items_key, get_depth_stats_key
from .redis_sync_client import SyncRedisClient

from global_config.logger import get_prefect_or_regular_python_logger

# Registry for custom processors
PROCESSOR_REGISTRY: Dict[str, Type['BaseProcessor']] = {}



# class PrefectScrapyLogHandler(logging.Handler):
#     """
#     Custom logging handler that redirects Scrapy logs to Prefect's logger.
    
#     This handler intercepts all Scrapy log messages and forwards them to
#     Prefect's run logger, ensuring all logs are captured in the Prefect UI.
#     """
    
#     def __init__(self, prefect_logger=None):
#         super().__init__()
#         self.prefect_logger = prefect_logger
        
#     def emit(self, record):
#         """Forward log records to Prefect logger."""
#         if self.prefect_logger is None:
#             self.prefect_logger = get_prefect_or_regular_python_logger("scrapy")
        
#         # Map Scrapy log levels to Prefect logger methods
#         level_mapping = {
#             logging.DEBUG: self.prefect_logger.debug,
#             logging.INFO: self.prefect_logger.info,
#             logging.WARNING: self.prefect_logger.warning,
#             logging.ERROR: self.prefect_logger.error,
#             logging.CRITICAL: self.prefect_logger.critical,
#         }
        
#         log_func = level_mapping.get(record.levelno, self.prefect_logger.info)
        
#         # Format the message with Scrapy context
#         msg = self.format(record)
#         if record.name.startswith('scrapy'):
#             msg = f"[SCRAPY] {msg}"
            
#         log_func(msg)


class BaseProcessor:
    """
    Base class for domain-specific processors.
    
    Implement custom logic by subclassing and registering.
    
    Processors can accept initialization parameters via job config:
        - allowed_domains: List of allowed domains (automatically passed)
        - Any other custom parameters needed by the processor
    """
    
    def __init__(self, *args, **kwargs):
        """
        Initialize processor with optional parameters.
        
        Args:
            *args: Positional arguments (for compatibility)
            **kwargs: Keyword arguments passed from job config
        """
        # Store any initialization parameters
        self.allowed_domains = kwargs.get('allowed_domains', [])
        # Store all kwargs for subclasses to use
        self.init_params = kwargs
    
    def on_response(self, response: Response, spider: Spider) -> Dict[str, Any]:
        """
        Process response and extract data.
        
        Args:
            response: Scrapy Response object
            spider: Spider instance
            
        Returns:
            Extracted data dictionary
        """
        return {
            'url': response.url,
            'status': response.status,
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def should_follow_link(self, url: str, response: Response, spider: Spider) -> bool:
        """
        Determine if a link should be followed.
        
        Args:
            url: URL to potentially follow
            response: Current response
            spider: Spider instance
            
        Returns:
            True if link should be followed
        """
        return True
    
    def should_process_link(self, response: Response, data: Dict[str, Any], spider: Spider) -> bool:
        """
        Determine if a response should be processed and yielded.
        
        This is called AFTER data extraction but BEFORE yielding.
        Use this to filter out low-quality or unwanted content.
        
        Args:
            response: Response object
            data: Extracted data
            spider: Spider instance
            
        Returns:
            True if item should be yielded
        """
        # Check response status
        if response.status >= 400:
            return False
            
        # Check if we have meaningful content
        # Override in subclasses for domain-specific checks
        return True
    
    def transform_data(self, data: Dict[str, Any], response: Response, spider: Spider) -> Dict[str, Any]:
        """
        Transform extracted data before yielding.
        
        Args:
            data: Extracted data
            response: Response object
            spider: Spider instance
            
        Returns:
            Transformed data
        """
        return data
    
    def get_link_priority(self, url: str, depth: int, response: Response, spider: Spider) -> int:
        """
        Calculate priority for a discovered link.
        
        Args:
            url: Discovered URL
            depth: Current depth
            response: Current response
            spider: Spider instance
            
        Returns:
            Priority value (higher = processed sooner)
        """
        return calculate_priority_from_depth(depth)


class OtterAIProcessor(BaseProcessor):
    """Example processor for otter.ai with custom logic."""
    
    def __init__(self, *args, **kwargs):
        """Initialize with optional parameters."""
        super().__init__(*args, **kwargs)
    
    def on_response(self, response: Response, spider: Spider) -> Dict[str, Any]:
        """Extract otter.ai specific data."""
        data = super().on_response(response, spider)
        
        # Extract page type
        url = response.url
        if '/blog' in url:
            data['page_type'] = 'blog'
            # Extract blog-specific data
            data['title'] = response.css('h1::text').get()
            data['author'] = response.css('.author-name::text').get()
            data['publish_date'] = response.css('time::attr(datetime)').get()
            data['content'] = ' '.join(response.css('article p::text').getall())
            
        elif '/pricing' in url:
            data['page_type'] = 'pricing'
            # Extract pricing tiers
            data['pricing_tiers'] = []
            for tier in response.css('.pricing-tier'):
                data['pricing_tiers'].append({
                    'name': tier.css('.tier-name::text').get(),
                    'price': tier.css('.price::text').get(),
                    'features': tier.css('.feature::text').getall()
                })
                
        elif '/careers' in url:
            data['page_type'] = 'careers'
            # Extract job listings
            data['jobs'] = []
            for job in response.css('.job-listing'):
                data['jobs'].append({
                    'title': job.css('.job-title::text').get(),
                    'department': job.css('.department::text').get(),
                    'location': job.css('.location::text').get(),
                    'url': response.urljoin(job.css('a::attr(href)').get())
                })
        else:
            data['page_type'] = 'general'
            
        # Extract metadata
        data['meta_description'] = response.css('meta[name="description"]::attr(content)').get()
        data['og_image'] = response.css('meta[property="og:image"]::attr(content)').get()
        
        return data
    
    def should_follow_link(self, url: str, response: Response, spider: Spider) -> bool:
        """Determine if otter.ai link should be followed."""
        # Skip certain URLs
        skip_patterns = [
            'mailto:', 'javascript:', '#',
            '/signin', '/signup', '/logout',
            '.pdf', '.doc', '.xlsx'
        ]
        
        for pattern in skip_patterns:
            if pattern in url.lower():
                return False
                
        # Only follow otter.ai domains
        try:
            parsed = urlparse(url)
            if parsed.netloc and 'otter.ai' not in parsed.netloc:
                return False
        except:
            return False
            
        return True
    
    def get_link_priority(self, url: str, depth: int, response: Response, spider: Spider) -> int:
        """Prioritize certain otter.ai pages."""
        base_priority = calculate_priority_from_depth(depth)
        
        # Boost priority for important pages
        priority_boost = {
            '/pricing': 20,
            '/blog': 15,
            '/features': 15,
            '/business': 10,
            '/education': 10,
        }
        
        for pattern, boost in priority_boost.items():
            if pattern in url:
                return base_priority + boost
                
        return base_priority


# Register processors
PROCESSOR_REGISTRY['otter.ai'] = OtterAIProcessor
PROCESSOR_REGISTRY['default'] = BaseProcessor


class GenericSpider(Spider):
    """
    Generic configurable spider for API-driven scraping.
    
    Can be customized via:
    - Custom processors for domain-specific logic
    - Configuration passed at runtime
    - Hooks and callbacks
    """
    
    name = 'generic_spider'
    
    def __init__(self, job_config: Dict[str, Any] = None, *args, **kwargs):
        """
        Initialize spider with job configuration.
        
        Args:
            job_config: Job configuration dict containing:
                - job_id: Unique job identifier
                - start_urls: List of URLs to start crawling
                - allowed_domains: List of allowed domains
                - processor: Processor name or 'default'
                - processor_init_params: Dict of parameters for processor initialization
                - max_urls_per_domain: Domain limit
                - max_crawl_depth: Depth limit
                - custom_settings: Additional Scrapy settings
                - extract_rules: CSS/XPath extraction rules
        """
        super().__init__(*args, **kwargs)
        
        self.job_config = job_config or {}
        self.job_id = self.job_config.get('job_id', f'job_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        
        # Configure spider
        self.start_urls = self.job_config.get('start_urls', [])
        self.allowed_domains = self.job_config.get('allowed_domains', [])
        
        # Get processor with optional initialization parameters
        processor_name = self.job_config.get('processor', 'default')
        processor_class = PROCESSOR_REGISTRY.get(processor_name, BaseProcessor)
        
        # Get processor init params from job config
        processor_init_params = self.job_config.get('processor_init_params', {})
        
        # Always pass allowed_domains to processor
        processor_init_params['allowed_domains'] = self.allowed_domains
        
        # Initialize processor with parameters
        self.processor = processor_class(**processor_init_params)
        
        # Extraction rules
        self.extract_rules = self.job_config.get('extract_rules', {})
        
        # Stats
        self.pages_crawled = 0
        self.items_extracted = 0
        
    @property
    def redis_client(self):
        """
        Get the Redis sync client from the crawler.
        
        The scheduler creates job-specific Redis clients and stores them
        in the crawler for all components to share.
        
        Returns None if clients not available.
        """
        if hasattr(self, 'crawler') and hasattr(self.crawler, '_redis_clients'):
            return self.crawler._redis_clients.get('sync')
        return None
        
    def start_requests(self):
        """Generate start requests with special flag."""
        for url in self.start_urls:
            yield Request(
                url,
                callback=self.parse,
                meta={'is_start_url': True, 'depth': 0}
            )
    
    def _check_processed_limit(self, response: Response, domain: str) -> bool:
        """
        Check if we've reached the processed items limit for this domain.
        
        Args:
            response: The response being processed
            domain: The domain of the URL
            
        Returns:
            True if we can process this item, False if limit reached
        """
        max_processed = self.settings.getint('MAX_PROCESSED_URLS_PER_DOMAIN', 0)
        
        # No limit set, always allow
        if max_processed <= 0:
            return True
            
        # Get Redis client from scheduler
        redis_client = self.redis_client
                
        if not redis_client:
            # Fallback: create temporary client (should rarely happen)
            # This only happens when spider is run outside of Scrapy framework
            
            raise Exception("Redis client not found in crawler within generic spider!")
        
            # redis_url = self.settings.get('REDIS_URL')
            # if not redis_url:
            #     return True  # No Redis, can't track limits
                
            # from .redis_sync_client import SyncRedisClient
            # temp_client = SyncRedisClient(redis_url)
            # try:
            #     return self._do_processed_limit_check(temp_client, domain, max_processed)
            # finally:
            #     # Important: close temporary client to avoid connection leaks
            #     temp_client.close()
        else:
            return self._do_processed_limit_check(redis_client, domain, max_processed)
            
    def _do_processed_limit_check(self, redis_client: SyncRedisClient, domain: str, max_processed: int) -> bool:
        """
        Perform the actual processed limit check using the provided Redis client.
        
        This method uses the thread-safe increment_counter_with_limit which performs
        optimistic increments and rolls back if the limit would be exceeded.
        
        Args:
            redis_client: The Redis client to use
            domain: The domain to check
            max_processed: The maximum allowed processed items
            
        Returns:
            True if we can process, False if over limit
        """
        # Get the key based on strategy
        queue_strategy = self.settings.get('REDIS_QUEUE_KEY_STRATEGY', 'spider')
        processed_key = get_processed_items_key(
            self.name, domain, self.job_id, queue_strategy
        )
        
        # Try to increment - will be rolled back if exceeds limit
        count, is_over = redis_client.increment_counter_with_limit(
            processed_key,
            increment=1,
            limit=max_processed,
            ttl=7 * 86400  # 7 days
        )
        
        if is_over:
            # Either at limit or increment was rolled back
            self.logger.debug(
                f"Item filtered by processed limit ({domain}: {count}/{max_processed})"
            )
            
            if hasattr(self, 'crawler') and self.crawler.stats:
                self.crawler.stats.inc_value('items/filtered/processed_limit')
                
            return False
            
        return True
    
    def parse(self, response: Response):
        """Main parsing method."""
        self.pages_crawled += 1
        depth = response.meta.get('depth', 0)
        
        self.logger.info(
            f"[JOB {self.job_id}] Crawled {self.pages_crawled}: {response.url} "
            f"(depth: {depth})"
        )
        
        # Process response with custom processor
        try:
            data = self.processor.on_response(response, self)
            
            # Apply custom extraction rules
            if self.extract_rules:
                data.update(self._apply_extraction_rules(response))
            
            # Transform data
            data = self.processor.transform_data(data, response, self)
            
            # Check if we should process this item
            if self.processor.should_process_link(response, data, self):
                # Check processed items limit
                domain = parse_domain_from_url(response.url)
                if self._check_processed_limit(response, domain):
                    # Add metadata
                    data['_job_id'] = self.job_id
                    data['_spider'] = self.name
                    data['_crawled_at'] = datetime.utcnow().isoformat()
                    data['_depth'] = depth
                    
                    # Yield item
                    self.items_extracted += 1
                    yield data
            else:
                self.logger.debug(f"Item filtered by should_process_link: {response.url}")
                if hasattr(self, 'crawler') and self.crawler.stats:
                    self.crawler.stats.inc_value('items/filtered/should_process')
                
        except Exception as e:
            self.logger.error(f"Error processing {response.url}: {e}")
            yield {
                'url': response.url,
                'error': str(e),
                '_job_id': self.job_id,
                '_spider': self.name,
                '_crawled_at': datetime.utcnow().isoformat()
            }
        
        # Discover and follow links
        if depth < self.settings.getint('MAX_CRAWL_DEPTH', 5):
            for url in self._discover_urls(response):
                if self.processor.should_follow_link(url, response, self):
                    priority = self.processor.get_link_priority(url, depth + 1, response, self)
                    
                    yield response.follow(
                        url,
                        callback=self.parse,
                        priority=priority,
                        meta={'depth': depth + 1}
                    )
    
    def _discover_urls(self, response: Response) -> List[str]:
        """Discover URLs from response.
        TODO: FIXME: remove URLS like: mailto:hello@grain.com (leads to value error in scrapy from response lib!)
        """
        urls = set()
        
        # Extract all links
        for link in response.css('a::attr(href)').getall():
            if link:
                absolute_url = response.urljoin(link)
                urls.add(absolute_url)
        
        # Also check for URLs in JavaScript (common in SPAs)
        js_url_patterns = [
            r'["\']/([\w\-/]+)["\']',  # Relative paths
            r'https?://[^\s"\')]+',     # Absolute URLs
        ]
        
        for script in response.css('script::text').getall():
            for pattern in js_url_patterns:
                
                for match in re.finditer(pattern, script):
                    url = match.group(0).strip('"\'')
                    if url.startswith('/'):
                        url = response.urljoin(url)
                    if url.startswith('http'):
                        urls.add(url)
        
        return list(urls)
    
    def _apply_extraction_rules(self, response: Response) -> Dict[str, Any]:
        """Apply custom extraction rules."""
        extracted = {}
        
        for field, rule in self.extract_rules.items():
            try:
                if isinstance(rule, dict):
                    selector_type = rule.get('type', 'css')
                    selector = rule.get('selector')
                    extract = rule.get('extract', 'text')
                    
                    if selector_type == 'css':
                        elements = response.css(selector)
                    elif selector_type == 'xpath':
                        elements = response.xpath(selector)
                    else:
                        continue
                    
                    if extract == 'text':
                        values = elements.getall()
                    elif extract == 'href':
                        values = elements.css('::attr(href)').getall()
                    elif extract.startswith('attr:'):
                        attr_name = extract.split(':', 1)[1]
                        values = elements.css(f'::attr({attr_name})').getall()
                    else:
                        values = elements.getall()
                    
                    # Single value or list
                    if rule.get('multiple', False):
                        extracted[field] = values
                    else:
                        extracted[field] = values[0] if values else None
                        
            except Exception as e:
                self.logger.warning(f"Failed to extract {field}: {e}")
        
        return extracted
    
    def closed(self, reason):
        """Called when spider closes."""
        self.logger.info(
            f"Spider closed: {reason}. "
            f"Pages: {self.pages_crawled}, Items: {self.items_extracted}"
        )


def run_scraping_job(job_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run a scraping job with the given configuration.
    
    Args:
        job_config: Job configuration dictionary
        
    Returns:
        Job execution results
    """
    # # Configure Scrapy logging
    # if use_prefect_logging:
    #     # Disable default Scrapy logging configuration
    #     configure_logging(install_root_handler=False)
    #     settings.set('LOG_ENABLED', True)
    #     settings.set('LOG_LEVEL', job_config.get('log_level', 'INFO'))
        
    #     # Add our custom Prefect handler to root logger
    #     root_logger = logging.getLogger()
    #     scrapy_logger = logging.getLogger('scrapy')
        
    #     # Remove existing handlers to avoid duplicate logs
    #     for handler in scrapy_logger.handlers[:]:
    #         scrapy_logger.removeHandler(handler)
        
    #     # Add Prefect handler
    #     prefect_handler = PrefectScrapyLogHandler(logger)
    #     prefect_handler.setFormatter(
    #         logging.Formatter('%(name)s - %(levelname)s - %(message)s')
    #     )
    #     scrapy_logger.addHandler(prefect_handler)
    #     scrapy_logger.setLevel(getattr(logging, job_config.get('log_level', 'INFO')))
        
    #     # Also add to specific Scrapy component loggers
    #     for component in ['scrapy.core.engine', 'scrapy.downloadermiddlewares', 
    #                     'scrapy.spidermiddlewares', 'scrapy.extensions']:
    #         component_logger = logging.getLogger(component)
    #         component_logger.addHandler(prefect_handler)
    #         component_logger.setLevel(getattr(logging, job_config.get('log_level', 'INFO')))
        
    #     logger.info("Scrapy logging redirected to Prefect")
    # else:
    #     # Use default Scrapy logging
    #     settings.set('LOG_LEVEL', job_config.get('log_level', 'INFO'))
    #     logger.info("Using default Scrapy logging")



    # Prepare settings
    settings = get_project_settings()
    
    # Apply Redis configuration
    settings.set('SCHEDULER', 'services.workflow_service.services.scraping.scrapy_redis_integration.RedisScheduler')
    settings.set('REDIS_URL', job_config.get('redis_url', scraping_settings.REDIS_URL))
    settings.set('REDIS_QUEUE_KEY_STRATEGY', 'job')
    settings.set('SCRAPY_JOB_ID', job_config['job_id'])
    
    # Apply job-specific settings
    settings.set('MAX_URLS_PER_DOMAIN', job_config.get('max_urls_per_domain', 100))
    settings.set('MAX_PROCESSED_URLS_PER_DOMAIN', job_config.get('max_processed_urls_per_domain', 0))
    settings.set('MAX_CRAWL_DEPTH', job_config.get('max_crawl_depth', 5))
    settings.set('CONCURRENT_REQUESTS_PER_DOMAIN', job_config.get('concurrent_requests_per_domain', 10))
    
    # Apply custom settings
    custom_settings = job_config.get('custom_settings', {})
    for key, value in custom_settings.items():
        settings.set(key, value)
    
    # Don't persist queue after job
    settings.set('SCHEDULER_PERSIST', False)
    settings.set('SCHEDULER_PURGE_ON_CLOSE', True)
    
    # Create process
    process = CrawlerProcess(settings)
    
    # Run spider
    process.crawl(GenericSpider, job_config=job_config)
    process.start()

    # Return job stats
    return {
        'job_id': job_config['job_id'],
        'status': 'completed',
        'completed_at': datetime.utcnow().isoformat()
    }

def push_urls_to_redis(
    spider_name: str,
    urls: List[str],
    redis_client: SyncRedisClient = None,
    redis_url: str = None,
    job_id: str = None,
    queue_key_strategy: str = 'spider',
    max_urls_per_domain: int = 0,
    max_crawl_depth: int = 5,
    initial_depth: int = 0
) -> Dict[str, Any]:
    """
    Push URLs to Redis queue for processing.
    
    Args:
        spider_name: Name of the spider
        urls: List of URLs to push
        redis_client: Optional Redis client to use (job-specific)
        redis_url: Redis connection URL (only used if client not provided)
        job_id: Optional job ID for queue isolation
        queue_key_strategy: 'spider' or 'job' strategy
        max_urls_per_domain: Max URLs per domain (0 = no limit)
        max_crawl_depth: Maximum crawl depth
        initial_depth: Initial depth for URLs
        
    Returns:
        Statistics about the push operation
    """
    # Use provided client or create temporary one
    own_client = False
    if not redis_client:
        redis_url = redis_url or scraping_settings.REDIS_URL
        redis_client = SyncRedisClient(redis_url)
        own_client = True
    
    # Get queue key
    queue_key = get_queue_key(spider_name, job_id, queue_key_strategy)
    
    stats = {
        'spider_name': spider_name,
        'job_id': job_id,
        'queue_key': queue_key,
        'urls_provided': len(urls),
        'urls_pushed': 0,
        'duplicates': 0,
        'domain_distribution': {}
    }
    
    try:
        for url in urls:
            # Create request data
            request_data = {
                'url': url,
                'method': 'GET',
                'meta': {'depth': initial_depth},
                'priority': calculate_priority_from_depth(initial_depth),
                'dont_filter': False
            }
            
            # Push to queue
            if redis_client.push_request(queue_key, request_data, priority=request_data['priority']):
                stats['urls_pushed'] += 1
                
                # Track domain distribution
                
                domain = urlparse(url).netloc.lower()
                stats['domain_distribution'][domain] = stats['domain_distribution'].get(domain, 0) + 1
            else:
                stats['duplicates'] += 1
                
    except Exception as e:
        logging.error(f"Error pushing URLs to Redis: {e}")
        raise
    finally:
        # Only close if we created the client
        if own_client:
            redis_client.close()
    
    return stats


def get_spider_stats(
    spider_name: str, 
    job_id: str = None, 
    redis_client: SyncRedisClient = None,
    redis_url: str = None
) -> Dict[str, Any]:
    """
    Get statistics for a spider/job.
    
    Args:
        spider_name: Spider name
        job_id: Optional job ID
        redis_client: Optional Redis client to use (job-specific)
        redis_url: Redis URL (only used if client not provided)
        
    Returns:
        Spider/job statistics
    """
    # Use provided client or create temporary one
    own_client = False
    if not redis_client:
        redis_url = redis_url or scraping_settings.REDIS_URL
        redis_client = SyncRedisClient(redis_url)
        own_client = True
    
    stats = {
        'spider_name': spider_name,
        'job_id': job_id,
        'queue_stats': {},
        'domain_stats': {},
        'depth_distribution': {},
        'total_urls_crawled': 0,
        'domains_crawled': 0
    }
    
    try:
        # Get queue stats
        queue_key = get_queue_key(spider_name, job_id, 'job' if job_id else 'spider')
        stats['queue_stats'] = redis_client.get_queue_stats(queue_key)
        
        # Get domain stats (simplified - would need to track keys properly)
        depth_key = get_depth_stats_key(spider_name)
        stats['depth_distribution'] = redis_client.get_hash_counter_values(depth_key)
        
        # Calculate totals
        stats['total_urls_crawled'] = sum(stats['depth_distribution'].values())
        stats['domains_crawled'] = len(stats['domain_stats'])
        
    except Exception as e:
        
        logging.error(f"Error getting spider stats: {e}")
        # Return partial stats on error
        pass
    finally:
        # Only close if we created the client
        if own_client:
            redis_client.close()
    
    return stats


