import asyncio
import base64
import hashlib
import json
import re
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlparse, urljoin

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
from .redis_sync_client import SyncRedisClient
from .settings import (
    scraping_settings, get_queue_key, get_dupefilter_key, 
    get_domain_limit_key, get_processed_items_key, get_depth_stats_key, 
    calculate_priority_from_depth, parse_domain_from_url, get_purge_patterns
)


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
        self.redis_client = AsyncRedisClient(redis_url)  # For async methods
        self.sync_redis = SyncRedisClient(redis_url)    # For sync methods
        
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
        
    def _get_job_id(self):
        """Get job ID from settings or generate one."""
        if self.job_id:
            return self.job_id
            
        # Try to get from spider
        if hasattr(self, 'spider') and hasattr(self.spider, 'job_id'):
            return self.spider.job_id
            
        # Generate a default job ID
        import uuid
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
        
        # Log queue configuration
        spider.logger.info(
            f"Using queue key: {self.queue_key} (strategy: {self.queue_key_strategy})"
        )
        spider.logger.info(
            f"Domain limit: {self.max_urls_per_domain}, Max depth: {self.max_crawl_depth}"
        )
        
        # Return a Deferred for async initialization
        return deferred_from_coro(self._async_open())
        
    async def _async_open(self):
        """Async initialization of the scheduler."""
        # Check Redis connection
        if not await self.redis_client.ping():
            raise ConnectionError("Cannot connect to Redis")
            
        # Clear queue if requested
        if self.flush_on_start:
            cleared, dupes_cleared = await self.redis_client.clear_queue(
                self.queue_key, clear_dupefilter=True
            )
            # Also clear domain/depth tracking
            patterns = [
                get_domain_limit_key(self.spider.name, '*', self.job_id, self.queue_key_strategy),
                get_depth_stats_key(self.spider.name, self.job_id, self.queue_key_strategy)
            ]
            await self.redis_client.delete_multiple_patterns(patterns)
            self.spider.logger.info(f"Cleared {cleared} requests, {dupes_cleared} duplicates")
            
        # Check for existing requests
        queue_len = await self.redis_client.get_queue_length(self.queue_key)
        if queue_len:
            self.spider.logger.info(f"Resuming crawl ({queue_len} requests scheduled)")

            
    def close(self, reason):
        """Clean up on spider close. Returns a Deferred."""
        return deferred_from_coro(self._async_close(reason))
        
    async def _async_close(self, reason):
        """Async cleanup on spider close."""
        # Get final stats before any cleanup
        stats = await self.redis_client.get_queue_stats(self.queue_key)
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
        
        # Clear queue if not persisting
        if not self.persist:
            cleared, dupes_cleared = await self.redis_client.clear_queue(
                self.queue_key, clear_dupefilter=True
            )
            self.spider.logger.info(f"Spider closed: cleared {cleared} requests")
            
        # Purge all spider data if configured
        if self.purge_on_close:
            # Use centralized purge patterns
            patterns = get_purge_patterns(
                self.spider.name, 
                self.job_id if self.queue_key_strategy == 'job' else None
            )
            deleted_counts = await self.redis_client.delete_multiple_patterns(patterns)
            total_deleted = sum(deleted_counts.values())
            self.spider.logger.info(
                f"Purged all Redis data for spider: {total_deleted} keys removed"
            )
            if self.stats:
                self.stats.set_value('redis_keys_purged', total_deleted)
                
        # Close Redis clients
        await self.redis_client.close()
        # Close sync wrapper (this will handle its own thread cleanup)
        self.sync_redis.close()
        
        # Remove references from crawler
        if hasattr(self.crawler, '_redis_clients'):
            del self.crawler._redis_clients
            
        self.spider.logger.info("Redis clients closed and cleaned up")
            
    async def _get_domain_stats(self) -> Dict[str, int]:
        """Get statistics about domains crawled."""
        # Get all domain limit keys
        pattern = get_domain_limit_key(
            self.spider.name, '*', self.job_id, self.queue_key_strategy
        )
        
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
            self.spider.logger.debug(
                f"Domain {domain} has reached processed limit: "
                f"{current_count}/{self.max_processed_urls_per_domain}"
            )
            
        return (current_count, is_over)
    
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
        self.spider.logger.info(
            f"Domain {domain} reached limit - consider implementing queue purge optimization"
        )
        return 0
    
    async def _get_processed_items_stats(self) -> Dict[str, int]:
        """Get statistics about items actually processed per domain."""
        # Get all processed items keys
        pattern = get_processed_items_key(
            self.spider.name, '*', self.job_id, self.queue_key_strategy
        )
        
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
            
    def enqueue_request(self, request):
        """Add request to Redis queue with domain/depth checking."""
        # Check depth limit
        depth = request.meta.get('depth', 0)
        if self.max_crawl_depth > 0 and depth > self.max_crawl_depth:
            if self.stats:
                self.stats.inc_value('scheduler/filtered/max_depth', spider=self.spider)
            self.spider.logger.debug(f"Request filtered by max depth ({depth}): {request.url}")
            return False
        
        # NEW: Check if spider wants to follow this URL BEFORE counting it
        if hasattr(self.spider, 'processor') and hasattr(self.spider.processor, 'should_follow_link'):
            # For follow requests, check if we should actually follow
            if not request.meta.get('is_start_url', False):  # Don't filter start URLs
                dummy_response = Response(url=request.url)
                if not self.spider.processor.should_follow_link(request.url, dummy_response, self.spider):
                    if self.stats:
                        self.stats.inc_value('scheduler/filtered/should_follow', spider=self.spider)
                    self.spider.logger.debug(f"Request filtered by should_follow_link: {request.url}")
                    return False
        
        # Extract domain for limit checking
        domain = parse_domain_from_url(request.url)
        
        # NEW: Check if domain has already reached its PROCESSED limit
        # This prevents enqueueing URLs that won't be processed anyway
        processed_count, is_over_processed = self._is_domain_over_processed_limit(domain)
        if is_over_processed:
            if self.stats:
                self.stats.inc_value('scheduler/filtered/processed_limit', spider=self.spider)
            self.spider.logger.debug(
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
                self.spider.logger.debug(
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
                self.spider.logger.debug(
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
            self.spider.logger.warning(
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
        import gzip
        
        # Check Redis memory usage periodically
        if hasattr(self, '_enqueue_count'):
            self._enqueue_count = getattr(self, '_enqueue_count', 0) + 1
            if self._enqueue_count % 100 == 0:  # Check every 100 requests
                try:
                    memory_usage = self.sync_redis.check_memory_usage()
                    if memory_usage > 80:  # 80% threshold
                        self.spider.logger.warning(
                            f"Redis memory usage high: {memory_usage:.1f}%. "
                            f"Consider reducing queue size or increasing Redis memory limit."
                        )
                except Exception as e:
                    self.spider.logger.debug(f"Could not check Redis memory: {e}")
        
        # Handle request body
        body = ''
        body_compressed = False
        original_body_size = len(request.body) if request.body else 0
        
        if request.body:
            # Skip body for GET requests if configured
            if request.method == 'GET' and self.skip_body_for_get:
                body = ''
                if original_body_size > 0:
                    self.spider.logger.debug(
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
                            self.spider.logger.debug(
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
                        self.spider.logger.warning(f"Failed to compress body: {e}")
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
            self.spider.logger.warning(
                f"Large request body ({original_body_size/1024:.1f}KB) for {request.url}. "
                f"Consider reducing body size or using external storage."
            )
            
        return {
            'url': request.url,
            'method': request.method,
            'headers': {k.decode(): [v.decode() for v in vals]
                       for k, vals in request.headers.items()},
            'body': body,
            'cookies': request.cookies,
            'meta': self._serialize_meta(request.meta),
            'priority': request.priority,
            'dont_filter': request.dont_filter,
            'callback': request.callback.__name__ if request.callback else None,
            'errback': request.errback.__name__ if request.errback else None,
            'cb_kwargs': request.cb_kwargs if hasattr(request, 'cb_kwargs') else {},
            'flags': list(request.flags) if hasattr(request, 'flags') else [],
            '_body_compressed': body_compressed,
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
                    import gzip
                    compressed_data = base64.b64decode(body[5:])  # Skip 'gzip:' prefix
                    body = gzip.decompress(compressed_data)
                except Exception as e:
                    self.spider.logger.error(f"Failed to decompress body: {e}")
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
            'headers': data.get('headers', {}),
            'body': body,
            'cookies': data.get('cookies', {}),
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
        
        # Browser pool for tier 2
        self.browser_pool = None
        
    @property 
    def redis_client(self):
        """Get async Redis client from crawler (job-specific)."""
        if hasattr(self.crawler, '_redis_clients'):
            return self.crawler._redis_clients.get('async')
        return None
        
    def download_request(self, request: Request, spider: Spider) -> Deferred[Response]:
        """
        Download request with tier escalation.
        Returns a Deferred as required by Scrapy.
        """
        async def _download():
            # Determine tier based on URL patterns
            tier = self._get_tier_for_url(request.url)
            
            # Log tier selection
            spider.logger.debug(f"Using tier '{tier}' for {request.url}")
            
            # Track tier usage
            if self.stats:
                self.stats.inc_value(f'downloader/tier_{tier}/requests', spider=spider)
            
            # Execute download based on tier
            try:
                if tier == 'basic':
                    response = await self._download_basic(request, spider)
                elif tier == 'playwright':
                    response = await self._download_playwright(request, spider)
                elif tier == 'managed':
                    response = await self._download_managed(request, spider)
                else:
                    response = await self._download_basic(request, spider)
                    
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
        
    async def _download_basic(self, request: Request, spider: Spider) -> HtmlResponse:
        """Basic HTTP download."""
        import httpx
        
        # Prepare headers
        headers = {}
        for key, values in request.headers.items():
            if isinstance(key, bytes):
                key = key.decode('utf-8')
            if isinstance(values, list):
                headers[key] = b', '.join(values).decode('utf-8')
            else:
                headers[key] = values.decode('utf-8') if isinstance(values, bytes) else values
                
        async with httpx.AsyncClient(verify=False, timeout=30.0, follow_redirects=True) as client:
            resp = await client.request(
                method=request.method,
                url=request.url,
                headers=headers,
                content=request.body,
                cookies=request.cookies,
            )
            
        # httpx automatically handles Content-Encoding (gzip, deflate, br)
        # resp.content is already decompressed
        
        # Check if URL indicates a gzipped file (e.g., file.json.gz)
        import gzip
        content = resp.content
        if request.url.endswith(('.gz', '.gzip')):
            try:
                # Try to decompress as gzip
                content = gzip.decompress(content)
                spider.logger.debug(f"Decompressed gzipped file: {request.url}")
            except Exception as e:
                spider.logger.warning(f"Failed to decompress {request.url}: {e}")
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
            spider.logger.warning("Playwright not installed, falling back to basic download")
            return await self._download_basic(request, spider)
        
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
                    encoding='utf-8'
                )
                
                # Add metadata
                response.meta['discovered_urls_count'] = len(discovered_urls)
                response.meta['render_tier'] = 'playwright'
                
                return response
                
            finally:
                await browser.close()
                
        except Exception as e:
            # Handle Playwright errors (e.g., browser not installed)
            spider.logger.error(f"Playwright error: {e}, falling back to basic download")
            return await self._download_basic(request, spider)
                
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
                
        spider.logger.debug(f"Discovered {len(discovered_urls)} URLs from {page.url}")
        return list(discovered_urls)
        
    async def _queue_discovered_urls(self, urls, parent_request, spider):
        """Queue discovered URLs directly to Redis with domain/depth checking."""
        # Check if discovery is enabled
        if not parent_request.meta.get('discover_urls', True):
            return
            
        # Get Redis client
        redis_client = self.redis_client
        if not redis_client:
            spider.logger.warning("No Redis client available for URL discovery")
            return
            
        # Get scheduler for configuration
        scheduler = None
        if hasattr(self.crawler, 'engine') and hasattr(self.crawler.engine, 'slot'):
            scheduler = self.crawler.engine.slot.scheduler
        else:
            scheduler = self.crawler.engine._slot.scheduler
        
        if scheduler is None:
            spider.logger.warning("No scheduler available for URL discovery")
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
            spider.logger.debug(
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
                    spider.logger.debug(f"Playwright discovered URL filtered by should_follow_link: {url}")
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
                    spider.logger.debug(
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
            spider.logger.debug("All discovered URLs filtered by processed limits")
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
            
        # Batch queue to Redis
        queued_count = await redis_client.push_requests_batch(
            scheduler.queue_key,
            new_requests,
            check_duplicates=True
        )
        
        spider.logger.info(
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
                
        spider.logger.debug(f"Executed {len(actions)} actions on {page.url}")
        
    async def _download_managed(self, request, spider):
        """Managed browser download - placeholder."""
        # Implement your managed browser service integration here
        spider.logger.warning(f"Managed browser not implemented, falling back to basic")
        return await self._download_basic(request, spider)
        
    def close(self):
        """Clean up resources."""
        # Close browser pool if needed
        return None
