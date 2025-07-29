import uuid
import asyncio
import base64
import hashlib
import json
import re
import fnmatch
import threading
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlparse, urljoin, unquote_plus

import httpx
import gzip

from scrapy import Request, Spider
from scrapy.crawler import Crawler
from scrapy.settings import Settings
from scrapy.http import Response, HtmlResponse
from scrapy.core.scheduler import Scheduler
from scrapy.utils.defer import deferred_from_coro, maybe_deferred_to_future
from scrapy.utils.reactor import is_asyncio_reactor_installed
from scrapy.utils.misc import load_object
from scrapy.exceptions import IgnoreRequest

from twisted.internet.defer import Deferred, inlineCallbacks

from scrapy.utils.reactor import install_reactor
install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")

from redis_client.redis_client import AsyncRedisClient  # Import your Redis client
from workflow_service.services.scraping.redis_sync_client import SyncRedisClient
from workflow_service.services.scraping.settings import (
    scraping_settings, get_queue_key, get_dupefilter_key, 
    get_domain_limit_key, get_processed_items_key, get_depth_stats_key, 
    calculate_priority_from_depth, parse_domain_from_url, get_purge_patterns
)

# Import the browser pool components
from workflow_service.services.scraping.browsers.scrapeless.scrapeless_browser import (
    ScrapelessBrowserPool,
    ScrapelessBrowserContextManager
)

# Import customer data service dependency
from services.workflow_service.services.external_context_manager import get_customer_data_service_no_dependency, clean_customer_data_service_no_dependency


class RedisScheduler(Scheduler):
    """
    Custom Scrapy scheduler using async Redis client with proper sync/async handling.
    Now includes domain limiting and depth control.
    """
    
    @classmethod
    def from_crawler(cls, crawler):
        """Create scheduler from crawler (Scrapy standard initialization)."""
        return cls(crawler)
    
    def __init__(self, crawler: Crawler, **kwargs):
        # Ignore extra kwargs that Scrapy might pass
        super().__init__(crawler)
        self.crawler = crawler
        self.settings = crawler.settings
        
        # Initialize Redis clients - These are job-specific and will be shared
        redis_url = self.settings.get('REDIS_URL', scraping_settings.REDIS_URL)
        use_in_memory = self.settings.getbool('USE_IN_MEMORY_QUEUE', scraping_settings.USE_IN_MEMORY_QUEUE)
        # self.browser_pool_enabled = self.settings.getbool('BROWSER_POOL_ENABLED', scraping_settings.BROWSER_POOL_ENABLED)
        
        # Only create async client if not using in-memory mode
        if use_in_memory:
            self.redis_client = None  # No async client in in-memory mode
        else:
            self.redis_client = AsyncRedisClient(redis_url)  # For async methods
            
        self.sync_redis = SyncRedisClient(
            redis_url,
            use_in_memory=use_in_memory
        )    # For sync methods
        
        # Store clients in crawler for other components to access
        crawler._redis_clients = {
            'async': self.redis_client,
            'sync': self.sync_redis
        }
        
        # Queue configuration
        self.queue_key_strategy = self.settings.get('REDIS_QUEUE_KEY_STRATEGY', 'spider')  # 'spider' or 'job'
        self.job_id = self.settings.get('SCRAPY_JOB_ID', None)
        
        # Domain and depth limits
        self.max_urls_per_domain = self.settings.getint(
            'MAX_URLS_PER_DOMAIN', 
            scraping_settings.DEFAULT_MAX_URLS_PER_DOMAIN
        )
        self.max_processed_urls_per_domain = self.settings.getint(
            'MAX_PROCESSED_URLS_PER_DOMAIN',
            scraping_settings.DEFAULT_MAX_PROCESSED_URLS_PER_DOMAIN
        )
        self.max_crawl_depth = self.settings.getint(
            'MAX_CRAWL_DEPTH',
            scraping_settings.DEFAULT_MAX_CRAWL_DEPTH
        )
        
        # Per-job limits override global limits
        if self.job_id:
            job_max_urls = self.settings.getint(f'JOB_{self.job_id}_MAX_URLS_PER_DOMAIN', 0)
            if job_max_urls > 0:
                self.max_urls_per_domain = job_max_urls
                
            job_max_depth = self.settings.getint(f'JOB_{self.job_id}_MAX_CRAWL_DEPTH', 0)
            if job_max_depth > 0:
                self.max_crawl_depth = job_max_depth
        
        # Generate actual queue key
        self.queue_key = None  # Will be set in open()
        
        # Initialize stats
        self.stats = crawler.stats if crawler else None
        
        # Blocked triggers tracking (not stored in stats until the end)
        self._blocked_trigger_counts = {}
        self._blocked_url_examples = {}
        self._blocked_triggers_lock = threading.Lock()
        
        # Persistence settings
        self.persist = self.settings.getbool('SCHEDULER_PERSIST', False)
        self.flush_on_start = self.settings.getbool('SCHEDULER_FLUSH_ON_START', False)
        self.purge_on_close = self.settings.getbool('SCHEDULER_PURGE_ON_CLOSE', False)
        
        # Request counter for periodic checks
        self._enqueue_count = 0
        
        # Body handling settings
        self.skip_body_for_get = self.settings.getbool(
            'SCHEDULER_SKIP_BODY_FOR_GET',
            scraping_settings.DEFAULT_SKIP_BODY_FOR_GET
        )
        self.compress_body_threshold = self.settings.getint(
            'SCHEDULER_COMPRESS_BODY_THRESHOLD',
            scraping_settings.DEFAULT_COMPRESS_BODY_THRESHOLD
        )
        
        # Browser pool will be initialized in _async_open
        self.browser_pool = None
        
        # Customer data service will be initialized in _async_open
        self.customer_data_service = None
            
    def _get_job_id(self):
        """Get job ID from settings or generate one."""
        if self.job_id:
            return self.job_id
            
        # Try to get from spider
        if hasattr(self, 'spider') and hasattr(self.spider, 'job_id'):
            return self.spider.job_id
            
        # Generate a default job ID
        return str(uuid.uuid4())[:8]
        
    def open(self, spider: Spider):
        """Initialize scheduler for spider. Returns a Deferred."""
        self.spider = spider
        
        # Update job_id if available from spider
        if hasattr(spider, 'job_id') and spider.job_id:
            self.job_id = spider.job_id
            
        # Generate queue key with spider name
        self.queue_key = get_queue_key(
            spider.name, 
            self.job_id, 
            self.queue_key_strategy
        )
        
        # Browser pool will be initialized in _async_open
        self.browser_pool = None
            
        # Log queue configuration
        spider.prefect_logger.debug(
            f"Using queue key: {self.queue_key} (strategy: {self.queue_key_strategy})"
        )
        spider.prefect_logger.debug(
            f"Domain limit: {self.max_urls_per_domain}, Max depth: {self.max_crawl_depth}"
        )
        
        # Return a Deferred for async initialization
        return deferred_from_coro(self._async_open())
        
    async def _async_open(self):
        """Async initialization of the scheduler."""
        redis_client = self.redis_client
        is_coroutine = True
        if self.sync_redis.use_in_memory:
            redis_client = self.sync_redis
            is_coroutine = False
            
        if is_coroutine and (not await redis_client.ping()):
            raise ConnectionError("Cannot connect to Redis")
        
        # Initialize browser pool if enabled
        if self.settings.getbool('BROWSER_POOL_ENABLED', scraping_settings.BROWSER_POOL_ENABLED):
            try:
                # Browser pool configuration
                pool_config = {
                    'max_concurrent_local': self.settings.getint('BROWSER_POOL_SIZE', scraping_settings.BROWSER_POOL_SIZE),
                    'acquisition_timeout': self.settings.getint('BROWSER_POOL_TIMEOUT', scraping_settings.BROWSER_POOL_TIMEOUT),
                    'browser_ttl': self.settings.getint('BROWSER_POOL_SESSION_TTL', scraping_settings.BROWSER_POOL_SESSION_TTL),
                    'enable_keep_alive': True,  # Keep browsers alive for reuse during job
                    'use_profiles': True,  # Disable profiles for scraping
                    # 'intercept_media': self.settings.getbool('BROWSER_POOL_INTERCEPT_MEDIA', scraping_settings.BROWSER_POOL_INTERCEPT_MEDIA),
                    # 'intercept_images': self.settings.getbool('BROWSER_POOL_INTERCEPT_IMAGES', scraping_settings.BROWSER_POOL_INTERCEPT_IMAGES),
                }
                
                # Create async browser pool
                self.browser_pool = ScrapelessBrowserPool(**pool_config)
                
                # Enter the context manager
                await self.browser_pool.__aenter__()
                
                # Store in crawler for other components to access
                self.crawler._browser_pool = self.browser_pool
                
                self.spider.prefect_logger.info(f"Browser pool initialized and entered context with {pool_config['max_concurrent_local']} max browsers for job {self.job_id}")
            except Exception as e:
                self.spider.prefect_logger.error(f"Failed to initialize browser pool: {e}")
                self.browser_pool = None
                self.crawler._browser_pool = None
            
        # # Initialize customer data service if enabled
        # if self.settings.getbool('MONGO_PIPELINE_ENABLED', True):
        #     try:
        #         # Initialize customer data service without versioning support for better performance
        #         self.customer_data_service = await get_customer_data_service_no_dependency(
        #             include_versioned=False
        #         )
                
        #         # Store in crawler for other components to access
        #         self.crawler._customer_data_service = self.customer_data_service
                
        #         self.spider.prefect_logger.info(f"Customer data service initialized for job {self.job_id}")
        #     except Exception as e:
        #         self.spider.prefect_logger.error(f"Failed to initialize customer data service: {e}")
        #         self.customer_data_service = None
        #         self.crawler._customer_data_service = None
        #         raise e
            
        # Clear queue if requested
        if self.flush_on_start:
            if is_coroutine:
                cleared, dupes_cleared = await redis_client.clear_queue(
                    self.queue_key, clear_dupefilter=True
                )
            else:
                cleared, dupes_cleared = redis_client.clear_queue(
                    self.queue_key, clear_dupefilter=True
                )
            # Also clear domain/depth tracking
            patterns = [
                get_domain_limit_key(self.spider.name, '*', self.job_id, self.queue_key_strategy),
                get_depth_stats_key(self.spider.name, self.job_id, self.queue_key_strategy)
            ]
            # Also clear fallback counters
            if self.job_id:
                patterns.extend([
                    scraping_settings.BROWSER_POOL_FALLBACK_COUNTER_KEY_PATTERN.format(
                        spider=self.spider.name, job=self.job_id
                    ),
                    scraping_settings.PROXY_TIER_FALLBACK_COUNTER_KEY_PATTERN.format(
                        spider=self.spider.name, job=self.job_id
                    )
                ])
            if is_coroutine:
                await redis_client.delete_multiple_patterns(patterns)
            else:
                redis_client.delete_multiple_patterns(patterns)
            self.spider.prefect_logger.info(f"Cleared {cleared} requests, {dupes_cleared} duplicates")
            
        # Check for existing requests
        if is_coroutine:
            queue_len = await redis_client.get_queue_length(self.queue_key)
        else:
            queue_len = redis_client.get_queue_length(self.queue_key)
        if queue_len:
            self.spider.prefect_logger.info(f"Resuming crawl ({queue_len} requests scheduled)")

            
    def close(self, reason):
        """Clean up on spider close. Returns a Deferred."""
        return deferred_from_coro(self._async_close(reason))
        
    async def _async_close(self, reason):
        """Async cleanup on spider close."""
        redis_client = self.redis_client
        is_coroutine = True
        if self.sync_redis.use_in_memory:
            redis_client = self.sync_redis
            is_coroutine = False
            
        # Get final stats before any cleanup
        if is_coroutine:
            stats = await redis_client.get_queue_stats(self.queue_key)
        else:
            stats = redis_client.get_queue_stats(self.queue_key)
            
        if self.stats:
            self.stats.set_value('final_queue_size', stats['queue_size'])
            self.stats.set_value('final_dupefilter_size', stats['dupefilter_size'])
            
            # Get domain stats
            domain_stats = await self._get_domain_stats()
            self.stats.set_value('domains_crawled', len(domain_stats))
            self.stats.set_value('domain_url_counts', domain_stats)
            
            # Get processed items stats
            processed_stats = await self._get_processed_items_stats()
            self.stats.set_value('domain_processed_counts', processed_stats)
            
            # Set blocked trigger stats from internal tracking
            if self._blocked_trigger_counts:
                self.stats.set_value('blocked_trigger_counts', dict(self._blocked_trigger_counts))
            if self._blocked_url_examples:
                self.stats.set_value('blocked_url_examples', dict(self._blocked_url_examples))
            
            # Get browser and proxy tier fallback stats
            handler: TieredDownloadHandler = self.crawler.engine.downloader.handlers._get_handler('https')
            
            if handler:
                # Browser pool stats
                if hasattr(handler, 'browser_pool_enabled') and handler.browser_pool_enabled:
                    browser_fallback_count = await self._get_browser_fallback_count()
                    if browser_fallback_count is not None:
                        self.stats.set_value('browser_pool_fallbacks_used', browser_fallback_count)
                        if hasattr(handler, 'browser_pool_max_fallbacks'):
                            self.stats.set_value('browser_pool_fallbacks_limit', handler.browser_pool_max_fallbacks)
                            self.stats.set_value('browser_pool_fallbacks_percentage', 
                                                (browser_fallback_count / handler.browser_pool_max_fallbacks * 100) 
                                                if handler.browser_pool_max_fallbacks > 0 else 0)
                
                # Proxy tier stats
                proxy_fallback_count = await self._get_proxy_fallback_count()
                if proxy_fallback_count is not None:
                    self.stats.set_value('proxy_tier_fallbacks_used', proxy_fallback_count)
                    if hasattr(handler, 'proxy_tier_max_fallbacks'):
                        self.stats.set_value('proxy_tier_fallbacks_limit', handler.proxy_tier_max_fallbacks)
                        self.stats.set_value('proxy_tier_fallbacks_percentage', 
                                            (proxy_fallback_count / handler.proxy_tier_max_fallbacks * 100) 
                                            if handler.proxy_tier_max_fallbacks > 0 else 0)
        
        # Clear queue if not persisting
        if not self.persist:
            if is_coroutine:
                cleared, dupes_cleared = await redis_client.clear_queue(
                    self.queue_key, clear_dupefilter=True
                )
            else:
                cleared, dupes_cleared = redis_client.clear_queue(
                    self.queue_key, clear_dupefilter=True
                )
            self.spider.prefect_logger.info(f"Spider closed: cleared {cleared} requests")
            
        # Purge all spider data if configured
        if self.purge_on_close:
            # Use centralized purge patterns
            patterns = get_purge_patterns(
                self.spider.name, 
                self.job_id if self.queue_key_strategy == 'job' else None
            )
            if is_coroutine:
                deleted_counts = await redis_client.delete_multiple_patterns(patterns)
            else:
                deleted_counts = redis_client.delete_multiple_patterns(patterns)
                
            total_deleted = sum(deleted_counts.values())
            storage_type = "in-memory" if self.sync_redis.use_in_memory else "Redis"
            self.spider.prefect_logger.info(
                f"Purged all {storage_type} data for spider: {total_deleted} keys removed"
            )
            if self.stats:
                stat_key = 'memory_keys_purged' if self.sync_redis.use_in_memory else 'redis_keys_purged'
                self.stats.set_value(stat_key, total_deleted)
                
        # Close clients
        if is_coroutine:
            await redis_client.close()
        
        if hasattr(self, 'redis_client') and self.redis_client:
            await self.redis_client.close()
        # Always close sync client (it's always created)
        self.sync_redis.close()
        
        # Clean up browser pool if it exists
        if hasattr(self, 'browser_pool') and self.browser_pool:
            try:
                # Exit the context manager properly
                await self.browser_pool.__aexit__(None, None, None)
                self.spider.prefect_logger.info(f"Browser pool context exited and cleaned up")
            except Exception as e:
                self.spider.prefect_logger.error(f"Error exiting browser pool context: {e}")
                # Force cleanup on error
                try:
                    cleaned = await self.browser_pool.cleanup_all_browsers()
                    self.spider.prefect_logger.info(f"Force cleaned {cleaned} browsers after context exit error")
                except Exception as cleanup_error:
                    self.spider.prefect_logger.error(f"Error during force cleanup: {cleanup_error}")
            finally:
                self.browser_pool = None
        
        # Clean up customer data service if it exists
        
        if hasattr(self.crawler, 'customer_data_service') and self.crawler.customer_data_service:
            try:
                await clean_customer_data_service_no_dependency(self.crawler.customer_data_service)
                self.spider.prefect_logger.info("Customer data service cleaned up")
            except Exception as e:
                self.spider.prefect_logger.error(f"Error cleaning up customer data service: {e}")
            finally:
                self.crawler.customer_data_service = None
        
        # Remove references from crawler
        if hasattr(self.crawler, '_redis_clients'):
            del self.crawler._redis_clients
        if hasattr(self.crawler, '_browser_pool'):
            del self.crawler._browser_pool
        if hasattr(self.crawler, '_customer_data_service'):
            del self.crawler._customer_data_service
            
        self.spider.prefect_logger.info("Storage clients, browser pool, and customer data service closed and cleaned up")
            
    async def _get_domain_stats(self) -> Dict[str, int]:
        """Get statistics about domains crawled."""
        # Get all domain limit keys
        pattern = get_domain_limit_key(
            self.spider.name, '*', self.job_id, self.queue_key_strategy
        )
        
        if self.sync_redis.use_in_memory:
            # In-memory mode - use sync client with pattern matching
            # Get all matching keys from counters
            domain_stats = {}
            with self.sync_redis._memory_lock:
                for key in self.sync_redis._memory_counters:
                    if fnmatch.fnmatch(key, pattern):
                        # Extract domain from key
                        parts = key.split(':')
                        domain = parts[-1]
                        count = self.sync_redis.get_counter_value(key)
                        domain_stats[domain] = count
            return domain_stats
        else:
            # Redis mode
            client = await self.redis_client.get_client()
            keys = await client.keys(pattern)
            
            domain_stats = {}
            for key in keys:
                # Extract domain from key
                parts = key.split(':')
                domain = parts[-1]
                count = await self.redis_client.get_counter_value(key)
                domain_stats[domain] = count
                
            return domain_stats
    
    def _is_domain_over_processed_limit(self, domain: str) -> tuple[int, bool]:
        """
        Check if a domain has reached its processed items limit.
        
        This is used for early stopping - no point in crawling URLs from domains
        that have already reached their processed item quota.
        
        Args:
            domain: Domain to check
            
        Returns:
            Tuple of (current_count, is_over_limit)
        """
        # If no processed limit is set, never over limit
        if self.max_processed_urls_per_domain <= 0:
            return (0, False)
            
        # Get the processed items key
        processed_key = get_processed_items_key(
            self.spider.name, domain, self.job_id, self.queue_key_strategy
        )
        
        # Get current count (don't increment, just check)
        current_count = self.sync_redis.get_counter_value(processed_key)
        
        # Check if over limit
        is_over = current_count >= self.max_processed_urls_per_domain
        
        if is_over and self.spider:
            self.spider.prefect_logger.debug(
                f"Domain {domain} has reached processed limit: "
                f"{current_count}/{self.max_processed_urls_per_domain}"
            )
            
        return (current_count, is_over)
    
    def _track_blocked_trigger(self, spider: Spider, trigger_reason: str, url: str) -> None:
        """
        Track blocked URL trigger reasons and store example URLs.
        This data is kept internally and only added to stats at spider close.
        
        Args:
            spider: The spider instance
            trigger_reason: The reason for the block (e.g., "status_403", "pattern_cloudflare")
            url: The URL that was blocked
        """
        # Thread-safe update of blocked triggers
        with self._blocked_triggers_lock:
            # Increment count
            self._blocked_trigger_counts[trigger_reason] = self._blocked_trigger_counts.get(trigger_reason, 0) + 1
            
            # Add example URL
            if trigger_reason not in self._blocked_url_examples:
                self._blocked_url_examples[trigger_reason] = []
            
            examples = self._blocked_url_examples[trigger_reason]
            if url not in examples:
                examples.append(url)
                
                # Limit to max examples
                max_examples = self.settings.getint(
                    'MAX_BLOCKED_URL_EXAMPLES',
                    scraping_settings.MAX_BLOCKED_URL_EXAMPLES
                )
                if len(examples) > max_examples:
                    self._blocked_url_examples[trigger_reason] = examples[-max_examples:]  # Keep most recent
    
    def _purge_domain_urls_from_queue(self, domain: str) -> int:
        """
        Purge remaining URLs from a specific domain from the queue.
        
        This is an optional optimization that can be called when a domain
        reaches its processed limit to avoid wasting time popping and 
        discarding URLs in next_request.
        
        Note: This is a potentially expensive operation as it requires
        scanning the entire queue. Use judiciously.
        
        Args:
            domain: Domain to purge URLs for
            
        Returns:
            Number of URLs purged
        """
        # This would require implementing a Redis Lua script to efficiently
        # scan and remove URLs from a specific domain from the priority queue.
        # For now, we'll leave this as a placeholder for future optimization.
        self.spider.prefect_logger.info(
            f"Domain {domain} reached limit - consider implementing queue purge optimization"
        )
        return 0
    
    async def _get_processed_items_stats(self) -> Dict[str, int]:
        """Get statistics about items actually processed per domain."""
        # Get all processed items keys
        pattern = get_processed_items_key(
            self.spider.name, '*', self.job_id, self.queue_key_strategy
        )
        
        if self.sync_redis.use_in_memory:
            # In-memory mode - use sync client with pattern matching
            processed_stats = {}
            with self.sync_redis._memory_lock:
                for key in self.sync_redis._memory_counters:
                    if fnmatch.fnmatch(key, pattern):
                        # Extract domain from key
                        parts = key.split(':')
                        domain = parts[-1]
                        count = self.sync_redis.get_counter_value(key)
                        processed_stats[domain] = count
            return processed_stats
        else:
            # Redis mode
            client = await self.redis_client.get_client()
            keys = await client.keys(pattern)
            
            processed_stats = {}
            for key in keys:
                # Extract domain from key
                parts = key.split(':')
                domain = parts[-1]
                count = await self.redis_client.get_counter_value(key)
                processed_stats[domain] = count
                
            return processed_stats
    
    async def _get_proxy_fallback_count(self) -> Optional[int]:
        """
        Get the current proxy tier fallback count for this job.
        
        Returns:
            Current proxy tier fallback count or None if not available
        """
        # Get job ID
        job_id = self.job_id or 'default'
        
        # Generate counter key
        counter_key = scraping_settings.PROXY_TIER_FALLBACK_COUNTER_KEY_PATTERN.format(
            spider=self.spider.name,
            job=job_id
        )
        
        if self.sync_redis.use_in_memory:
            # In-memory mode - use sync client
            return self.sync_redis.get_counter_value(counter_key)
        else:
            # Redis mode - use async client
            return await self.redis_client.get_counter_value(counter_key)
            
    async def _get_browser_fallback_count(self) -> Optional[int]:
        """
        Get the current browser fallback count for this job.
        
        Returns:
            Current browser fallback count or None if not available
        """
        # Get job ID
        job_id = self.job_id or 'default'
        
        # Generate counter key
        counter_key = scraping_settings.BROWSER_POOL_FALLBACK_COUNTER_KEY_PATTERN.format(
            spider=self.spider.name,
            job=job_id
        )
        
        if self.sync_redis.use_in_memory:
            # In-memory mode - use sync client
            return self.sync_redis.get_counter_value(counter_key)
        else:
            # Redis mode - use async client
            return await self.redis_client.get_counter_value(counter_key)
            
    def enqueue_request(self, request):
        """Add request to Redis queue with domain/depth checking."""
        # Check depth limit
        depth = request.meta.get('depth', 0)
        if self.max_crawl_depth > 0 and depth > self.max_crawl_depth:
            if self.stats:
                self.stats.inc_value('scheduler/filtered/max_depth', spider=self.spider)
            self.spider.prefect_logger.debug(f"Request filtered by max depth ({depth}): {request.url}")
            return False
        
        # NEW: Check if spider wants to follow this URL BEFORE counting it
        if hasattr(self.spider, 'processor') and hasattr(self.spider.processor, 'should_follow_link'):
            # For follow requests, check if we should actually follow
            if not request.meta.get('is_start_url', False):  # Don't filter start URLs
                dummy_response = Response(url=request.url)
                if not self.spider.processor.should_follow_link(request.url, dummy_response, self.spider):
                    if self.stats:
                        self.stats.inc_value('scheduler/filtered/should_follow', spider=self.spider)
                    self.spider.prefect_logger.debug(f"Request filtered by should_follow_link: {request.url}")
                    return False
        
        # Extract domain for limit checking
        domain = parse_domain_from_url(request.url)
        
        # NEW: Check if domain has already reached its PROCESSED limit
        # This prevents enqueueing URLs that won't be processed anyway
        processed_count, is_over_processed = self._is_domain_over_processed_limit(domain)
        if is_over_processed:
            if self.stats:
                self.stats.inc_value('scheduler/filtered/processed_limit', spider=self.spider)
            self.spider.prefect_logger.debug(
                f"Request filtered by processed limit ({domain}: {processed_count}/"
                f"{self.max_processed_urls_per_domain}): {request.url}"
            )
            return False
            
        # Check domain limit using sync wrapper
        if self.max_urls_per_domain > 0:
            domain_key = get_domain_limit_key(
                self.spider.name, domain, self.job_id, self.queue_key_strategy
            )
            
            # Try to increment - will be rolled back if exceeds limit
            count, is_over = self.sync_redis.increment_counter_with_limit(
                domain_key,
                increment=1,
                limit=self.max_urls_per_domain,
                ttl=scraping_settings.DEFAULT_DUPEFILTER_TTL
            )
            
            if is_over:
                # Either at limit or increment was rolled back
                if self.stats:
                    self.stats.inc_value('scheduler/filtered/domain_limit', spider=self.spider)
                self.spider.prefect_logger.debug(
                    f"Request filtered by domain limit ({domain}: {count}/{self.max_urls_per_domain}): {request.url}"
                )
                return False
        
        # Track depth statistics
        depth_key = get_depth_stats_key(
            self.spider.name, self.job_id, self.queue_key_strategy
        )
        self.sync_redis.increment_hash_counter(
            depth_key, str(depth), 1,
            ttl=scraping_settings.DEFAULT_DUPEFILTER_TTL
        )
        
        # Calculate priority based on depth
        original_priority = request.priority
        depth_priority = calculate_priority_from_depth(depth, original_priority)
        
        # Serialize request with adjusted priority
        request_data = self._serialize_request(request)
        
        # Use safe push with memory check
        queued = self.sync_redis.push_request_safe(
            self.queue_key,
            request_data,
            priority=depth_priority,  # Use depth-based priority
            dedupe_key=request.url
        )
        
        if queued and self.stats:
            self.stats.inc_value('scheduler/enqueued/redis', spider=self.spider)
            self.stats.inc_value(f'scheduler/enqueued/depth_{depth}', spider=self.spider)
            
        return queued
        
    def next_request(self):
        """Get next request from Redis queue, skipping domains that have reached their processed limit."""
        # Use a reasonable max attempts to prevent infinite loop
        # If we have a domain limit, use 10x that; otherwise use 100
        max_attempts = max(100, self.max_urls_per_domain * 10) if self.max_urls_per_domain > 0 else 100
        attempts = 0
        
        while attempts < max_attempts:
            attempts += 1
            
            # Pop from Redis using sync wrapper
            request_data = self.sync_redis.pop_request(self.queue_key)
            
            if not request_data:
                return None
                
            # Deserialize request
            request = self._deserialize_request(request_data)
            
            # Check if this domain has reached its processed limit
            domain = parse_domain_from_url(request.url)
            processed_count, is_over_processed = self._is_domain_over_processed_limit(domain)
            
            if is_over_processed:
                # Skip this URL - domain has reached its limit
                if self.stats:
                    self.stats.inc_value('scheduler/skipped/processed_limit', spider=self.spider)
                self.spider.prefect_logger.debug(
                    f"Skipping URL from over-limit domain ({domain}: {processed_count}/"
                    f"{self.max_processed_urls_per_domain}): {request.url}"
                )
                # Continue to next URL
                continue
            
            # Valid request - track stats and return
            if self.stats:
                self.stats.inc_value('scheduler/dequeued/redis', spider=self.spider)
                depth = request.meta.get('depth', 0)
                self.stats.inc_value(f'scheduler/dequeued/depth_{depth}', spider=self.spider)
                
            return request
        
        # If we've tried too many times, log warning
        if self.spider:
            self.spider.prefect_logger.warning(
                f"Tried {max_attempts} URLs but all were from domains over their processed limit"
            )
        
        return None
        
    def has_pending_requests(self):
        """Check if there are pending requests."""
        length = self.sync_redis.get_queue_length(self.queue_key)
        return length > 0
    
    def __len__(self):
        """Return the number of pending requests in the queue.
        
        This is required for truthiness checks (e.g., 'if scheduler:').
        """
        if not self.queue_key:
            return 0
        return self.sync_redis.get_queue_length(self.queue_key)
        
    def _serialize_request(self, request: Request) -> dict:
        """Serialize Scrapy Request to dict with body optimization."""
        
        # Check Redis memory usage periodically
        if hasattr(self, '_enqueue_count'):
            self._enqueue_count = getattr(self, '_enqueue_count', 0) + 1
            if self._enqueue_count % 100 == 0:  # Check every 100 requests
                try:
                    memory_usage = self.sync_redis.check_memory_usage()
                    if memory_usage > 80:  # 80% threshold
                        self.spider.prefect_logger.warning(
                            f"Redis memory usage high: {memory_usage:.1f}%. "
                            f"Consider reducing queue size or increasing Redis memory limit."
                        )
                except Exception as e:
                    self.spider.prefect_logger.debug(f"Could not check Redis memory: {e}")
        
        # Handle request body
        body = ''
        body_compressed = False
        original_body_size = len(request.body) if request.body else 0
        
        if request.body:
            # Skip body for GET requests if configured
            if request.method == 'GET' and self.skip_body_for_get:
                body = ''
                if original_body_size > 0:
                    self.spider.prefect_logger.debug(
                        f"Skipping {original_body_size} byte body for GET request: {request.url}"
                    )
            else:
                # Compress large bodies
                if original_body_size > self.compress_body_threshold:
                    try:
                        body_bytes = request.body if isinstance(request.body, bytes) else request.body.encode('utf-8')
                        compressed = gzip.compress(body_bytes, compresslevel=6)
                        
                        # Only use compression if it saves at least 20% space
                        if len(compressed) < original_body_size * 0.8:
                            body = f"gzip:{base64.b64encode(compressed).decode('utf-8')}"
                            body_compressed = True
                            self.spider.prefect_logger.debug(
                                f"Compressed body from {original_body_size} to {len(compressed)} bytes "
                                f"({100*(1-len(compressed)/original_body_size):.1f}% reduction) for {request.url}"
                            )
                        else:
                            # Compression didn't help much, use normal encoding
                            if isinstance(request.body, bytes):
                                body = base64.b64encode(request.body).decode('utf-8')
                            else:
                                body = request.body
                    except Exception as e:
                        self.spider.prefect_logger.warning(f"Failed to compress body: {e}")
                        # Fallback to normal encoding
                        if isinstance(request.body, bytes):
                            body = base64.b64encode(request.body).decode('utf-8')
                        else:
                            body = request.body
                else:
                    # Small body, normal handling
                    if isinstance(request.body, bytes):
                        body = base64.b64encode(request.body).decode('utf-8')
                    else:
                        body = request.body
        
        # Log warning for large bodies
        if original_body_size > 10 * 1024:  # 10KB
            self.spider.prefect_logger.warning(
                f"Large request body ({original_body_size/1024:.1f}KB) for {request.url}. "
                f"Consider reducing body size or using external storage."
            )
            
        return {
            'url': request.url,
            'method': request.method,
            # 'headers': {k.decode(): [v.decode() for v in vals]
            #            for k, vals in request.headers.items()},
            # 'body': body,
            # 'cookies': request.cookies,
            'meta': self._serialize_meta(request.meta),
            'priority': request.priority,
            'dont_filter': request.dont_filter,
            'callback': request.callback.__name__ if request.callback else None,
            'errback': request.errback.__name__ if request.errback else None,
            'cb_kwargs': request.cb_kwargs if hasattr(request, 'cb_kwargs') else {},
            'flags': list(request.flags) if hasattr(request, 'flags') else [],
            # '_body_compressed': body_compressed,
        }
        
    def _serialize_meta(self, meta: Dict[str, Any]) -> Dict[str, Any]:
        """Serialize request meta, handling non-JSON types."""
        serialized = {}
        for key, value in meta.items():
            try:
                # Test if JSON serializable
                json.dumps(value)
                serialized[key] = value
            except (TypeError, ValueError):
                # Convert to string representation
                serialized[key] = str(value)
        return serialized
        
    def _deserialize_request(self, data: Dict[str, Any]) -> Request:
        """Deserialize dict to Scrapy Request."""
        # Get callback/errback from spider
        callback = None
        errback = None
        
        if data.get('callback') and hasattr(self.spider, data['callback']):
            callback = getattr(self.spider, data['callback'])
        if data.get('errback') and hasattr(self.spider, data['errback']):
            errback = getattr(self.spider, data['errback'])
            
        # Decode body if base64 encoded or compressed
        body = data.get('body', '')
        if body and len(body) > 0:
            if body.startswith('gzip:'):
                # Decompress gzipped body
                try:
                    compressed_data = base64.b64decode(body[5:])  # Skip 'gzip:' prefix
                    body = gzip.decompress(compressed_data)
                except Exception as e:
                    self.spider.prefect_logger.error(f"Failed to decompress body: {e}")
                    body = b''  # Fallback to empty body
            else:
                try:
                    body = base64.b64decode(body)
                except:
                    body = body.encode('utf-8')
                
        # Create request with all parameters
        request_params = {
            'url': data['url'],
            'method': data.get('method', 'GET'),
            # 'headers': data.get('headers', {}),
            'body': body,
            # 'cookies': data.get('cookies', {}),
            'meta': data.get('meta', {}),
            'priority': data.get('priority', 0),
            'dont_filter': data.get('dont_filter', False),
            'callback': callback,
            'errback': errback,
        }
        
        # Add cb_kwargs if present
        if 'cb_kwargs' in data:
            request_params['cb_kwargs'] = data['cb_kwargs']
            
        request = Request(**request_params)
        
        # Set flags if present (flags can be set after creation)
        if 'flags' in data:
            for flag in data['flags']:
                request.flags.append(flag)
            
        return request


class TieredDownloadHandler:
    """
    Download handler with tiered approach and URL discovery during rendering.
    """
    
    @classmethod
    def from_crawler(cls, crawler):
        """Create handler from crawler (Scrapy standard initialization)."""
        return cls(crawler.settings, crawler)
    
    def __init__(self, settings: Settings, crawler: Crawler):
        self.crawler = crawler
        self.settings = settings
        self.stats = crawler.stats
        
        # Tier configuration
        self.tier_rules = settings.getdict('TIER_RULES', {})
        
        # Browser pool configuration
        self.browser_pool_enabled = settings.getbool('BROWSER_POOL_ENABLED', scraping_settings.BROWSER_POOL_ENABLED)
        self.browser_pool_size = settings.getint('BROWSER_POOL_SIZE', scraping_settings.BROWSER_POOL_SIZE)
        self.browser_pool_timeout = settings.getint('BROWSER_POOL_TIMEOUT', scraping_settings.BROWSER_POOL_TIMEOUT)
        self.browser_pool_trigger_codes = settings.getlist('BROWSER_POOL_TRIGGER_CODES', scraping_settings.BROWSER_POOL_TRIGGER_CODES)
        self.browser_pool_trigger_patterns = settings.getlist('BROWSER_POOL_TRIGGER_PATTERNS', scraping_settings.BROWSER_POOL_TRIGGER_PATTERNS)
        self.browser_pool_max_fallbacks = settings.getint('BROWSER_POOL_MAX_FALLBACKS_PER_JOB', scraping_settings.BROWSER_POOL_MAX_FALLBACKS_PER_JOB)
        
        # Proxy tier configuration
        self.proxy_tier_enabled = settings.getbool('PROXY_TIER_ENABLED', scraping_settings.PROXY_TIER_ENABLED)
        self.proxy_tier_max_fallbacks = settings.getint('PROXY_TIER_MAX_FALLBACKS_PER_JOB', scraping_settings.PROXY_TIER_MAX_FALLBACKS_PER_JOB)
        
        # Browser pool will be accessed from crawler when needed
        # It's created by RedisScheduler and stored as crawler._browser_pool
        
    @property 
    def redis_client(self):
        """Get async Redis client from crawler (job-specific)."""
        if hasattr(self.crawler, '_redis_clients'):
            return self.crawler._redis_clients.get('async')
        return None
    
    @property
    def sync_redis_client(self) -> Optional[SyncRedisClient]:
        """Get sync Redis client from crawler (job-specific)."""
        if hasattr(self.crawler, '_redis_clients'):
            return self.crawler._redis_clients.get('sync')
        return None
    
    @property
    def browser_pool(self) -> Optional[ScrapelessBrowserPool]:
        """Get browser pool from crawler (job-specific)."""
        if hasattr(self.crawler, '_browser_pool'):
            return self.crawler._browser_pool
        return None
    
    @property
    def customer_data_service(self):
        """Get customer data service from crawler (job-specific)."""
        if hasattr(self.crawler, '_customer_data_service'):
            return self.crawler._customer_data_service
        return None
    
    def _check_and_increment_proxy_fallback_count(self, spider: Spider) -> bool:
        """
        Check if we can use proxy fallback and increment counter if allowed.
        
        This method tracks proxy tier fallback usage per job to prevent excessive
        usage of proxy operations.
        
        Args:
            spider: The spider instance
            
        Returns:
            True if proxy fallback is allowed (under limit), False otherwise
        """
        # If no limit set, always allow
        if self.proxy_tier_max_fallbacks <= 0:
            return True
            
        # Get sync Redis client
        redis_client = self.sync_redis_client
        if not redis_client:
            # No Redis client, can't track - allow by default
            spider.prefect_logger.warning("No Redis client available for proxy fallback tracking")
            return True
            
        # Get job ID from spider or settings
        job_id = getattr(spider, 'job_id', None) or self.settings.get('SCRAPY_JOB_ID', 'default')
        
        # Generate counter key
        counter_key = scraping_settings.PROXY_TIER_FALLBACK_COUNTER_KEY_PATTERN.format(
            spider=spider.name,
            job=job_id
        )
        
        # Try to increment counter with limit check
        try:
            current_count, is_over_limit = redis_client.increment_counter_with_limit(
                counter_key,
                increment=1,
                limit=self.proxy_tier_max_fallbacks,
                ttl=86400  # 24 hours TTL
            )
            
            if is_over_limit:
                spider.prefect_logger.warning(
                    f"Proxy tier fallback limit reached for job {job_id}: "
                    f"{current_count}/{self.proxy_tier_max_fallbacks}"
                )
                if self.stats:
                    self.stats.inc_value('downloader/proxy_tier/limit_exceeded', spider=spider)
                return False
                
            spider.prefect_logger.debug(
                f"Proxy tier fallback count for job {job_id}: "
                f"{current_count}/{self.proxy_tier_max_fallbacks}"
            )
            return True
            
        except Exception as e:
            spider.prefect_logger.error(f"Error tracking proxy tier fallback count: {e}")
            # On error, allow fallback to avoid blocking
            return True
    
    def _check_and_increment_browser_fallback_count(self, spider: Spider) -> bool:
        """
        Check if we can use browser fallback and increment counter if allowed.
        
        This method tracks browser fallback usage per job to prevent excessive
        usage of expensive browser operations.
        
        Args:
            spider: The spider instance
            
        Returns:
            True if browser fallback is allowed (under limit), False otherwise
        """
        # If no limit set, always allow
        if self.browser_pool_max_fallbacks <= 0:
            return True
            
        # Get sync Redis client
        redis_client = self.sync_redis_client
        if not redis_client:
            # No Redis client, can't track - allow by default
            spider.prefect_logger.warning("No Redis client available for browser fallback tracking")
            return True
            
        # Get job ID from spider or settings
        job_id = getattr(spider, 'job_id', None) or self.settings.get('SCRAPY_JOB_ID', 'default')
        
        # Generate counter key
        counter_key = scraping_settings.BROWSER_POOL_FALLBACK_COUNTER_KEY_PATTERN.format(
            spider=spider.name,
            job=job_id
        )
        
        # Try to increment counter with limit check
        try:
            current_count, is_over_limit = redis_client.increment_counter_with_limit(
                counter_key,
                increment=1,
                limit=self.browser_pool_max_fallbacks,
                ttl=86400  # 24 hours TTL
            )
            
            if is_over_limit:
                spider.prefect_logger.warning(
                    f"Browser fallback limit reached for job {job_id}: "
                    f"{current_count}/{self.browser_pool_max_fallbacks}"
                )
                if self.stats:
                    self.stats.inc_value('downloader/browser_pool/limit_exceeded', spider=spider)
                return False
                
            spider.prefect_logger.debug(
                f"Browser fallback count for job {job_id}: "
                f"{current_count}/{self.browser_pool_max_fallbacks}"
            )
            return True
            
        except Exception as e:
            spider.prefect_logger.error(f"Error tracking browser fallback count: {e}")
            # On error, allow fallback to avoid blocking
            return True
        
    def download_request(self, request: Request, spider: Spider) -> Deferred[Response]:
        """
        Download request with tier escalation and browser pool fallback.
        Returns a Deferred as required by Scrapy.
        """
        async def _download():
            # Determine tier based on URL patterns
            tier = self._get_tier_for_url(request.url)
            
            # Log tier selection
            spider.prefect_logger.debug(f"Using tier '{tier}' for {request.url}")
            
            # Track tier usage
            if self.stats:
                self.stats.inc_value(f'downloader/tier_{tier}/requests', spider=spider)
            
            # Execute download based on tier
            try:
                if tier == 'basic':
                    response = await self._download_basic(request, spider)
                elif tier == 'playwright':
                    response = await self._download_playwright(request, spider)
                else:
                    response = await self._download_basic(request, spider)
                
                # Check if response requires fallback (proxy tier first, then browser pool)
                should_fallback, trigger_reason = self._should_use_browser_pool(response)
                if should_fallback:
                    spider.prefect_logger.info(f"Response indicates bot detection for {request.url} (status: {response.status}, trigger: {trigger_reason})")
                    
                    # Track the trigger reason
                    # Note: The scheduler will track this, not the handler
                    scheduler = self.crawler.engine.slot.scheduler if hasattr(self.crawler.engine, 'slot') else self.crawler.engine._slot.scheduler
                    if scheduler and hasattr(scheduler, '_track_blocked_trigger'):
                        scheduler._track_blocked_trigger(spider, trigger_reason, request.url)
                    
                    # First try proxy tier if not already used
                    if self.proxy_tier_enabled and (not request.meta.get('proxy_tier_used', False)):
                        # Check if we're under the proxy tier fallback limit
                        if self._check_and_increment_proxy_fallback_count(spider):
                            spider.prefect_logger.info(f"Trying proxy tier fallback for {request.url}")
                            if self.stats:
                                self.stats.inc_value('downloader/proxy_tier/triggered', spider=spider)
                                self.stats.inc_value(f'downloader/proxy_tier/trigger_status_{response.status}', spider=spider)
                            
                            try:
                                # Mark that we're using proxy tier to avoid infinite loop
                                request.meta['proxy_tier_used'] = True
                                proxy_response = await self._download_basic(request, spider, use_proxy=True)
                                
                                # Check if proxy tier was successful
                                proxy_should_fallback, proxy_trigger_reason = self._should_use_browser_pool(proxy_response, retry_on_failed_sitemap_or_robots=False)
                                if not proxy_should_fallback:
                                    # Proxy tier succeeded
                                    if self.stats:
                                        self.stats.inc_value('downloader/proxy_tier/success', spider=spider)
                                    spider.prefect_logger.info(f"Proxy tier succeeded for {request.url}")
                                    return proxy_response
                                else:
                                    # Proxy tier also hit bot detection
                                    spider.prefect_logger.info(f"Proxy tier also detected as bot for {request.url} (status: {proxy_response.status}, trigger: {proxy_trigger_reason})")
                                    if self.stats:
                                        self.stats.inc_value('downloader/proxy_tier/still_detected_blocked', spider=spider)
                                    # Track the proxy tier trigger
                                    scheduler = self.crawler.engine.slot.scheduler if hasattr(self.crawler.engine, 'slot') else self.crawler.engine._slot.scheduler
                                    if scheduler and hasattr(scheduler, '_track_blocked_trigger'):
                                        scheduler._track_blocked_trigger(spider, f"proxy_{proxy_trigger_reason}", request.url)
                                    # Continue to browser pool below
                                    response = proxy_response  # Update response for browser pool check
                                    
                            except Exception as e:
                                spider.prefect_logger.error(f"Proxy tier failed: {e}")
                                if self.stats:
                                    self.stats.inc_value('downloader/proxy_tier/failed', spider=spider)
                                # Continue to browser pool below
                        else:
                            # Proxy tier limit reached
                            spider.prefect_logger.info(
                                f"Proxy tier fallback skipped due to limit for {request.url} "
                                f"(continuing to browser pool if available)"
                            )
                    
                    # Now try browser pool if enabled
                    if self.browser_pool_enabled and self.browser_pool:
                        spider.prefect_logger.info(f"Triggering browser pool fallback for {request.url} (status: {response.status})")
                        
                        # Check if we're under the browser fallback limit
                        if self._check_and_increment_browser_fallback_count(spider):
                            # Track browser pool usage
                            if self.stats:
                                self.stats.inc_value('downloader/browser_pool/triggered', spider=spider)
                                self.stats.inc_value(f'downloader/browser_pool/trigger_status_{response.status}', spider=spider)
                            
                            # Try browser pool fallback
                            try:
                                browser_response = await self._download_with_browser_pool(request, spider)
                                
                                # Check if browser pool actually succeeded
                                browser_should_fallback, _ = self._should_use_browser_pool(browser_response, retry_on_failed_sitemap_or_robots=False)
                                if not browser_should_fallback:
                                    # Browser pool succeeded in bypassing bot detection
                                    if self.stats:
                                        self.stats.inc_value('downloader/browser_pool/success', spider=spider)
                                        # Track which trigger type was successfully bypassed
                                        self.stats.inc_value(f'downloader/browser_pool/bypassed/{trigger_reason}', spider=spider)
                                    response = browser_response
                                else:
                                    # Even browser pool couldn't bypass detection
                                    spider.prefect_logger.warning(f"Browser pool also detected as bot for {request.url}")
                                    if self.stats:
                                        self.stats.inc_value('downloader/browser_pool/still_blocked', spider=spider)
                                        self.stats.inc_value(f'downloader/browser_pool/failed_bypass/{trigger_reason}', spider=spider)
                                    response = browser_response  # Return browser response anyway
                                    
                            except Exception as e:
                                spider.prefect_logger.error(f"Browser pool fallback failed: {e}")
                                if self.stats:
                                    self.stats.inc_value('downloader/browser_pool/failed', spider=spider)
                                # Return the last response we have
                        else:
                            # Fallback limit reached, return current response
                            spider.prefect_logger.info(
                                f"Browser pool fallback skipped due to limit for {request.url} "
                                f"(returning response with status {response.status})"
                            )
                else:
                    # Track success
                    if self.stats:
                        self.stats.inc_value(f'downloader/tier_{tier}/success', spider=spider)
                    
                return response
                
            except Exception as e:
                # Track failure
                if self.stats:
                    self.stats.inc_value(f'downloader/tier_{tier}/failed', spider=spider)
                raise
                
        return deferred_from_coro(_download())
        
    def _get_tier_for_url(self, url: str) -> str:
        """Determine tier based on URL patterns."""
        for pattern, tier in self.tier_rules.items():
            if re.match(pattern, url):
                return tier
        return 'basic'
    
    def _should_use_browser_pool(self, response: Response, retry_on_failed_sitemap_or_robots: bool = True) -> tuple[bool, Optional[str]]:
        """
        Check if response indicates need for browser pool fallback.
        
        This method checks multiple indicators:
        1. HTTP status codes known to indicate bot detection
        2. Response headers that indicate protection services
        3. Content patterns in the response body
        
        Args:
            response: The response to check
            retry_on_failed_sitemap_or_robots: Whether to retry on failed sitemap/robots.txt
            
        Returns:
            Tuple of (should_use_browser_pool, trigger_reason)
        """
        # Check status codes
        if response.status in self.browser_pool_trigger_codes:
            return (True, f"status_{response.status}")
        
        # if response.status == 404:
        #     return False
        is_url_xml = response.url.endswith("xml") or response.url.endswith("xml.gz")
        ends_in_sitemap = response.url.endswith("sitemap")
        contains_sitemap = "sitemap" in response.url
        is_robots_txt = response.url.endswith("robots.txt")
            
        if ((is_url_xml and contains_sitemap) or ends_in_sitemap or is_robots_txt): 
            if response.status == 404 or (not retry_on_failed_sitemap_or_robots):
                return (False, None)
        
        # Check response headers for protection services
        headers_lower = {k.lower(): v for k, v in response.headers.items()}
        
        # Cloudflare headers
        if any(header in headers_lower for header in ['cf-ray', 'cf-request-id', 'cf-cache-status']):
            # Check if it's a Cloudflare challenge (not just CDN)
            if b'cf-mitigated' in headers_lower.get('cf-cache-status', b''):
                return (True, "header_cloudflare_mitigated")
            # Check server header
            if b'cloudflare' in headers_lower.get('server', b'').lower():
                # If Cloudflare server AND error status, likely a challenge
                if response.status >= 400:
                    return (True, f"header_cloudflare_status_{response.status}")
        
        # Other protection service headers
        protection_headers = [
            ('x-sucuri-id', 'header_sucuri_waf'),  # Sucuri WAF
            ('x-denied-reason', 'header_generic_waf'),  # Generic WAF
            ('x-firewall', 'header_firewall'),  # Generic firewall
            ('x-security', 'header_security'),  # Generic security
        ]
        for header, trigger_name in protection_headers:
            if header in headers_lower:
                return (True, trigger_name)
        
        # Check content patterns (case-insensitive)
        if hasattr(response, 'text'):
            content_lower = response.text.lower()
            
            # # Quick check for very short responses that might be redirects
            # if len(response.text) < 500 and response.status == 200:
            #     # Check for meta refresh or JavaScript redirects
            #     if any(pattern in content_lower for pattern in ['meta http-equiv="refresh"', 'window.location', 'document.location']):
            #         return True
            
            # Check for trigger patterns
            for pattern in self.browser_pool_trigger_patterns:  # TODO: FIXME: add min text size of body check too!  and response.body.decode('utf-8') --> convert ot markdown / text
                if pattern.lower() in content_lower:
                    # Create a clean trigger name from the pattern
                    trigger_name = f"pattern_{pattern.replace(' ', '_').replace("'", '')[:30]}"
                    return (True, trigger_name)
        
        return (False, None)
    

        
    async def _download_with_browser_pool(self, request: Request, spider: Spider) -> HtmlResponse:
        """
        Download using browser pool as fallback strategy.
        
        This is now a proper async method using the async browser pool.
        
        Args:
            request: The request to download
            spider: The spider instance
            
        Returns:
            HtmlResponse with the downloaded content
        """
        browser_instance = None
        try:
            # Use async browser pool with async context manager
            async with ScrapelessBrowserContextManager(
                self.browser_pool,
                timeout=self.browser_pool_timeout,
                force_close_on_error=True,
                intercept_media=self.settings.getbool('BROWSER_POOL_INTERCEPT_MEDIA', scraping_settings.BROWSER_POOL_INTERCEPT_MEDIA),
                intercept_images=self.settings.getbool('BROWSER_POOL_INTERCEPT_IMAGES', scraping_settings.BROWSER_POOL_INTERCEPT_IMAGES),
            ) as browser:
                
                browser_instance = browser
                spider.prefect_logger.debug(f"Browser acquired from pool for {request.url}")
                
                # Navigate to the URL
                timeout_ms = self.settings.getint('BROWSER_POOL_TIMEOUT', scraping_settings.BROWSER_POOL_TIMEOUT) * 1000
                await browser.page.goto(request.url, timeout=timeout_ms, wait_until='load')
                
                # Get the page content
                html = await browser.page.content()
                final_url = browser.page.url
                
                spider.prefect_logger.info(f"Successfully scraped {request.url} using browser pool")
                
                # Create response
                response = HtmlResponse(
                    url=final_url,
                    status=200,  # Browser navigation successful
                    body=html.encode('utf-8'),
                    request=request,
                    encoding='utf-8'
                )
                
                # Add metadata
                response.meta['browser_pool_used'] = True
                response.meta['render_tier'] = 'browser_pool'
                
                # Track success
                if self.stats:
                    self.stats.inc_value('downloader/browser_pool/render_success', spider=spider)
                
                return response
                
        except asyncio.TimeoutError:
            spider.prefect_logger.error(f"Browser pool timeout for {request.url}")
            if self.stats:
                self.stats.inc_value('downloader/browser_pool/timeout', spider=spider)
            raise
        except Exception as e:
            spider.prefect_logger.error(f"Browser pool download failed for {request.url}: {e}")
            if self.stats:
                self.stats.inc_value('downloader/browser_pool/render_failed', spider=spider)
                # Track specific error types
                error_type = type(e).__name__
                self.stats.inc_value(f'downloader/browser_pool/error/{error_type}', spider=spider)
            raise
        
    async def _download_basic(self, request: Request, spider: Spider, use_proxy: bool = False) -> HtmlResponse:
        """Basic HTTP download."""
        
        # Prepare headers
        headers = {}
        for key, values in request.headers.items():
            if isinstance(key, bytes):
                key = key.decode('utf-8')
            if isinstance(values, list):
                headers[key] = b', '.join(values).decode('utf-8')
            else:
                headers[key] = values.decode('utf-8') if isinstance(values, bytes) else values
                
        kwargs = {}
        if use_proxy:
            kwargs['proxy'] = scraping_settings.PROXY_URL_EVOMI_ROTATING
            
        async with httpx.AsyncClient(verify=False, timeout=30.0, follow_redirects=True, **kwargs) as client:
            resp = await client.request(
                method=request.method,
                url=request.url,
                headers=headers,
                content=request.body,
                # cookies=request.cookies,
            )
            
        # httpx automatically handles Content-Encoding (gzip, deflate, br)
        # resp.content is already decompressed
        
        # Check if URL indicates a gzipped file (e.g., file.json.gz)
        
        is_compressed = False
        uri = urlparse(request.url)
        url_path = unquote_plus(uri.path)
        content_type = resp.headers.get("content-type") or ""

        if url_path.lower().endswith(".gz") or "gzip" in content_type.lower():
            is_compressed = True
        
        content = resp.content
        if is_compressed and len(content) > 0:
            try:
                # Try to decompress as gzip
                content = gzip.decompress(content)
                spider.prefect_logger.debug(f"Decompressed gzipped file: {request.url}")
            except Exception as e:
                spider.prefect_logger.warning(f"Failed to decompress {request.url}: {e}")
                # Use original content if decompression fails
            
        return HtmlResponse(
            url=str(resp.url),
            status=resp.status_code,
            headers=dict(resp.headers),  # Keep all headers
            body=content,
            request=request,
            encoding='utf-8'
        )
        
    async def _download_playwright(self, request: Request, spider: Spider) -> HtmlResponse:
        """Playwright download with URL discovery."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            spider.prefect_logger.warning("Playwright not installed, falling back to basic download")
            return await self._download_basic(request, spider, use_proxy=True)
        
        # Initialize browser pool if needed
        if self.browser_pool is None:
            self.browser_pool = []  # Simple list for now
            
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.settings.getbool('PLAYWRIGHT_HEADLESS', True),
                    args=['--disable-blink-features=AutomationControlled']
                )
            
            try:
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                
                page = await context.new_page()
                
                # Apply stealth
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)
                
                # Navigate
                await page.goto(request.url, wait_until='networkidle', timeout=30000)
                
                # Discover URLs if enabled
                discovered_urls = []
                if request.meta.get('discover_urls', True):
                    discovered_urls = await self._discover_urls(page, spider)
                    
                    # Queue discovered URLs immediately
                    if discovered_urls:
                        await self._queue_discovered_urls(
                            discovered_urls, request, spider
                        )
                        
                # Perform any custom actions
                if 'playwright_actions' in request.meta:
                    await self._execute_actions(
                        page, request.meta['playwright_actions'], spider
                    )
                    
                # Get final content
                content = await page.content()
                final_url = page.url
                
                # Create response
                response = HtmlResponse(
                    url=final_url,
                    body=content.encode('utf-8'),
                    request=request,
                    encoding='utf-8',
                )
                
                # Add metadata
                response.meta['discovered_urls_count'] = len(discovered_urls)
                response.meta['render_tier'] = 'playwright'
                
                return response
                
            finally:
                await browser.close()
                
        except Exception as e:
            # Handle Playwright errors (e.g., browser not installed)
            spider.prefect_logger.error(f"Playwright error: {e}, falling back to basic download")
            return await self._download_basic(request, spider, use_proxy=True)
                
    async def _discover_urls(self, page, spider: Spider) -> List[str]:
        """Discover URLs from page during rendering."""
        discovered_urls = set()
        
        # Get initial URLs
        urls = await page.evaluate('''
            Array.from(document.querySelectorAll('a[href]'))
                .map(a => a.href)
                .filter(url => url && url.startsWith('http'))
        ''')
        discovered_urls.update(urls)
        
        # Scroll to discover more
        prev_height = 0
        for i in range(3):  # Max 3 scrolls
            # Scroll down
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(1000)
            
            # Check if new content loaded
            current_height = await page.evaluate('document.body.scrollHeight')
            if current_height == prev_height:
                break
            prev_height = current_height
            
            # Get new URLs
            new_urls = await page.evaluate('''
                Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.href)
                    .filter(url => url && url.startsWith('http'))
            ''')
            discovered_urls.update(new_urls)
            
        # Check for pagination
        next_button = await page.query_selector('a.next, a[rel="next"], button.next-page')
        if next_button:
            next_url = await next_button.get_attribute('href')
            if next_url:
                discovered_urls.add(urljoin(page.url, next_url))
                
        spider.prefect_logger.debug(f"Discovered {len(discovered_urls)} URLs from {page.url}")
        return list(discovered_urls)
        
    async def _queue_discovered_urls(self, urls, parent_request, spider):
        """Queue discovered URLs directly to Redis with domain/depth checking."""
        # Check if discovery is enabled
        if not parent_request.meta.get('discover_urls', True):
            return
            
        # Get Redis client (async or sync)
        redis_client = self.redis_client
        sync_redis = None
        if hasattr(self.crawler, '_redis_clients'):
            sync_redis = self.crawler._redis_clients.get('sync')
            
        if not redis_client and not sync_redis:
            spider.prefect_logger.warning("No storage client available for URL discovery")
            return
            
        # Check if we're in in-memory mode
        use_in_memory = sync_redis and sync_redis.use_in_memory
            
        # Get scheduler for configuration
        scheduler = None
        if hasattr(self.crawler, 'engine') and hasattr(self.crawler.engine, 'slot'):
            scheduler = self.crawler.engine.slot.scheduler
        else:
            scheduler = self.crawler.engine._slot.scheduler
        
        if scheduler is None:
            spider.prefect_logger.warning("No scheduler available for URL discovery")
            return
            
        # Filter URLs based on allowed domains
        allowed_domains = getattr(spider, 'allowed_domains', [])
        if allowed_domains:
            filtered_urls = []
            for url in urls:
                domain = urlparse(url).netloc
                if any(allowed in domain for allowed in allowed_domains):
                    filtered_urls.append(url)
            urls = filtered_urls
            
        if not urls:
            return
            
        # Prepare request data
        new_requests = []
        parent_depth = parent_request.meta.get('depth', 0)
        new_depth = parent_depth + 1
        
        # Check if new depth exceeds limit
        if scheduler.max_crawl_depth > 0 and new_depth > scheduler.max_crawl_depth:
            spider.prefect_logger.debug(
                f"Not queueing {len(urls)} discovered URLs - depth {new_depth} exceeds limit"
            )
            if self.stats:
                self.stats.inc_value('urls_discovered_depth_filtered', len(urls), spider=spider)
            return
        
        # Filter URLs by spider's should_follow_link AND domain processed limits
        urls_to_queue = []
        domains_over_limit = set()
        urls_filtered_by_spider = 0
        urls_filtered_by_limit = 0
        
        # Create dummy response for should_follow_link check
        dummy_response = HtmlResponse(url=parent_request.url, body=b'')
        
        for url in urls:
            # First check spider's should_follow_link
            if hasattr(spider, 'processor') and hasattr(spider.processor, 'should_follow_link'):
                if not spider.processor.should_follow_link(url, dummy_response, spider):
                    spider.prefect_logger.debug(f"Playwright discovered URL filtered by should_follow_link: {url}")
                    urls_filtered_by_spider += 1
                    continue
            
            # Then check domain processed limit
            domain = parse_domain_from_url(url)
            
            # Check if we've already determined this domain is over limit
            if domain in domains_over_limit:
                urls_filtered_by_limit += 1
                continue
                
            # Check if domain has reached processed limit
            # Note: We check the scheduler's limit, not spider's processor
            if hasattr(scheduler, '_is_domain_over_processed_limit'):
                _, is_over = scheduler._is_domain_over_processed_limit(domain)
                if is_over:
                    domains_over_limit.add(domain)
                    spider.prefect_logger.debug(
                        f"Playwright discovered URL filtered by processed limit: {url}"
                    )
                    urls_filtered_by_limit += 1
                    continue
                    
            urls_to_queue.append(url)
        
        # Update stats for filtered URLs
        if self.stats:
            if urls_filtered_by_spider > 0:
                self.stats.inc_value(
                    'playwright/urls_filtered_by_spider', 
                    urls_filtered_by_spider, 
                    spider=spider
                )
            if urls_filtered_by_limit > 0:
                self.stats.inc_value(
                    'playwright/urls_filtered_by_processed_limit', 
                    urls_filtered_by_limit, 
                    spider=spider
                )
            
        if not urls_to_queue:
            spider.prefect_logger.debug("All discovered URLs filtered by processed limits")
            return
            
        # Continue with filtered URLs
        for url in urls_to_queue:
            # Calculate priority based on depth
            priority = calculate_priority_from_depth(new_depth)
            
            req_data = {
                'url': url,
                'method': 'GET',
                'headers': {},
                'body': '',
                'meta': {
                    'discovered_from': parent_request.url,
                    'depth': new_depth,
                    'discover_urls': parent_request.meta.get('discover_urls', True),  # Inherit discovery setting
                },
                'priority': priority,  # Use depth-based priority
                'callback': 'parse',  # Default callback
                'dont_filter': False,
            }
            new_requests.append(req_data)
            
        # Batch queue to storage
        if use_in_memory:
            # In-memory mode - use sync client
            queued_count = 0
            for req_data in new_requests:
                # Extract priority and dedupe key
                priority = req_data.get('priority', 0)
                dedupe_key = req_data.get('url', '')
                
                # Push using sync client
                if sync_redis.push_request(scheduler.queue_key, req_data, priority=priority, dedupe_key=dedupe_key):
                    queued_count += 1
        else:
            # Redis mode - use async batch
            queued_count = await redis_client.push_requests_batch(
                scheduler.queue_key,
                new_requests,
                check_duplicates=True
            )
        
        spider.prefect_logger.info(
            f"Queued {queued_count}/{len(urls)} URLs discovered from {parent_request.url}"
        )
        
        # Update stats
        if self.stats:
            self.stats.inc_value('urls_discovered', len(urls), spider=spider)
            self.stats.inc_value('urls_queued', queued_count, spider=spider)
            self.stats.inc_value('urls_filtered_by_spider', len(urls) - len(urls_to_queue) if 'urls_to_follow' in locals() else 0, spider=spider)
            
    async def _execute_actions(self, page, actions, spider):
        """Execute custom page actions."""
        for action in actions:
            action_type = action.get('type')
            
            if action_type == 'wait':
                wait_time = action.get('time', 1000)
                await page.wait_for_timeout(wait_time)
                
            elif action_type == 'click':
                selector = action.get('selector')
                if selector:
                    element = await page.query_selector(selector)
                    if element:
                        await element.click()
                        await page.wait_for_load_state('networkidle')
                        
            elif action_type == 'scroll_to_bottom':
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(1000)
                
            elif action_type == 'screenshot':
                path = action.get('path', 'screenshot.png')
                await page.screenshot(path=path)
                
        spider.prefect_logger.debug(f"Executed {len(actions)} actions on {page.url}")
        
    def close(self):
        """Clean up resources."""
        # Browser pool is managed by RedisScheduler, no cleanup needed here
        return None
