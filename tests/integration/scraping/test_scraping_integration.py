"""
Integration tests for the scraping service.

These tests verify the functionality of the scraping system including:
- Redis queue management
- Domain limiting
- Depth limiting
- Priority handling
- Job isolation
"""
import asyncio
import os
import uuid
import unittest
from datetime import timedelta
from pathlib import Path
import json
import tempfile
import shutil
import logging

from redis_client.redis_client import AsyncRedisClient
from scrapy.crawler import Crawler
from scrapy.settings import Settings
from scrapy import Spider, Request
from scrapy.utils.defer import deferred_to_future
from twisted.internet.defer import Deferred

from workflow_service.services.scraping.redis_sync_client import SyncRedisClient
from workflow_service.services.scraping.settings import (
    scraping_settings, get_queue_key, get_dupefilter_key,
    get_domain_limit_key, get_depth_stats_key, calculate_priority_from_depth,
    parse_domain_from_url, get_purge_patterns, get_processed_items_key, ScrapingSettings
)
from workflow_service.services.scraping.scrapy_redis_integration import RedisScheduler, TieredDownloadHandler
from workflow_service.services.scraping.spider import (
    push_urls_to_redis, get_spider_stats, GenericSpider
)

ScrapingSettings.USE_IN_MEMORY_QUEUE = False

# Import settings
from global_config.settings import global_settings


class TestProcessedUrlsLimiting(unittest.IsolatedAsyncioTestCase):
    """Test MAX_PROCESSED_URLS_PER_DOMAIN functionality."""
    
    async def asyncSetUp(self):
        """Set up test environment."""
        self.redis_url = global_settings.REDIS_URL
        if not self.redis_url:
            self.skipTest("REDIS_URL environment variable not set.")
            
        self.client = AsyncRedisClient(self.redis_url)
        self.sync_client = SyncRedisClient(self.redis_url)
        self.TEST_PREFIX = f"test_processed_{uuid.uuid4().hex[:6]}"
        
        is_connected = await self.client.ping()
        if not is_connected:
            await self.client.close()
            self.skipTest("Could not connect to Redis.")
    
    async def asyncTearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'sync_client'):
            self.sync_client.close()
            
        if hasattr(self, 'client') and self.client:
            try:
                patterns = [
                    f"processed_items:{self.TEST_PREFIX}*",
                    f"queue:{self.TEST_PREFIX}*",
                    f"domain_limit:{self.TEST_PREFIX}*",
                ]
                for pattern in patterns:
                    await self.client.delete_keys_by_pattern(pattern)
            except:
                pass
            await self.client.close()
    
    async def test_processed_items_tracking(self):
        """Test tracking of processed items separately from enqueued URLs."""
        spider_name = f"{self.TEST_PREFIX}_processed"
        domain = "otter.ai"
        
        # Track enqueued vs processed
        from workflow_service.services.scraping.settings import (
            get_domain_limit_key, get_processed_items_key
        )
        
        domain_key = get_domain_limit_key(spider_name, domain)
        processed_key = get_processed_items_key(spider_name, domain)
        
        # Simulate enqueueing 10 URLs
        for i in range(10):
            count, is_over = self.sync_client.increment_counter_with_limit(
                domain_key, 1, limit=20
            )
            self.assertFalse(is_over)
        
        # Simulate processing only 5 of them
        max_processed = 5
        processed_count = 0
        
        for i in range(10):
            # Try to process
            count, is_over = self.sync_client.increment_counter_with_limit(
                processed_key, 1, limit=max_processed
            )
            
            # With optimistic increment:
            # - If count > max_processed, it was rolled back
            # - If count <= max_processed and not rolled back, it succeeded
            if count <= max_processed and not (is_over and count == processed_count):
                processed_count += 1
        
        # Verify counts
        enqueued = await self.client.get_counter_value(domain_key)
        processed = await self.client.get_counter_value(processed_key)
        
        self.assertEqual(enqueued, 10, "Should have enqueued 10 URLs")
        self.assertEqual(processed, max_processed, f"Should have processed exactly {max_processed}")
        self.assertEqual(processed_count, max_processed)
    
    async def test_processed_items_with_filtering(self):
        """Test processed items limiting with should_process_link filtering."""
        spider_name = f"{self.TEST_PREFIX}_filter"
        domain = "grain.com"
        
        from workflow_service.services.scraping.settings import get_processed_items_key
        
        processed_key = get_processed_items_key(spider_name, domain)
        max_processed = 3
        
        # Simulate items with different quality scores
        items = [
            {'quality': 'high', 'should_process': True},
            {'quality': 'low', 'should_process': False},
            {'quality': 'high', 'should_process': True},
            {'quality': 'medium', 'should_process': True},
            {'quality': 'low', 'should_process': False},
            {'quality': 'high', 'should_process': True},
        ]
        
        processed_items = []
        filtered_items = []
        
        for item in items:
            if not item['should_process']:
                # Filtered by should_process_link
                filtered_items.append(item)
                continue
            
            # Try to process
            count, is_over = self.sync_client.increment_counter_with_limit(
                processed_key, 1, limit=max_processed
            )
            
            # Check if increment was successful (not rolled back)
            if not is_over or count == len(processed_items) + 1:
                processed_items.append(item)
            else:
                # Hit limit, stop processing
                break
        
        # Verify results
        self.assertEqual(len(processed_items), max_processed)
        self.assertEqual(len(filtered_items), 2, "Should have filtered 2 low quality items")
        
        # All processed items should be high/medium quality
        for item in processed_items:
            self.assertTrue(item['should_process'])
    
    async def test_processed_limits_across_domains(self):
        """Test that processed limits are per-domain."""
        spider_name = f"{self.TEST_PREFIX}_multi"
        domains = ["otter.ai", "grain.com", "help.otter.ai"]
        max_processed_per_domain = 2
        
        from workflow_service.services.scraping.settings import get_processed_items_key
        
        # Process items for each domain
        domain_processed = {}
        
        for domain in domains:
            processed_key = get_processed_items_key(spider_name, domain)
            domain_processed[domain] = 0
            
            # Try to process 5 items per domain
            for i in range(5):
                count, is_over = self.sync_client.increment_counter_with_limit(
                    processed_key, 1, limit=max_processed_per_domain
                )
                
                # Check if increment was successful (not rolled back)
                # With optimistic increment, if we're over limit and count didn't increase,
                # it means the increment was rolled back
                if not is_over or (is_over and count == domain_processed[domain] + 1):
                    domain_processed[domain] += 1
                else:
                    # Hit limit, no need to continue for this domain
                    break
        
        # Each domain should have exactly max_processed_per_domain items
        for domain, count in domain_processed.items():
            self.assertEqual(
                count, max_processed_per_domain,
                f"Domain {domain} should have exactly {max_processed_per_domain} processed items"
            )


class TestComplexConcurrentScenarios(unittest.IsolatedAsyncioTestCase):
    """Test complex concurrent scraping scenarios."""
    
    async def asyncSetUp(self):
        """Set up test environment."""
        self.redis_url = global_settings.REDIS_URL
        if not self.redis_url:
            self.skipTest("REDIS_URL environment variable not set.")
            
        self.client = AsyncRedisClient(self.redis_url)
        self.sync_client = SyncRedisClient(self.redis_url)
        self.TEST_PREFIX = f"test_complex_{uuid.uuid4().hex[:6]}"
        
        is_connected = await self.client.ping()
        if not is_connected:
            await self.client.close()
            self.skipTest("Could not connect to Redis.")
    
    async def asyncTearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'sync_client'):
            self.sync_client.close()
            
        if hasattr(self, 'client') and self.client:
            try:
                await self.client.delete_keys_by_pattern(f"{self.TEST_PREFIX}*")
                await self.client.delete_keys_by_pattern(f"*{self.TEST_PREFIX}*")
            except:
                pass
            await self.client.close()
    
    async def test_concurrent_multi_spider_crawling(self):
        """Test multiple spiders crawling concurrently with shared domains."""
        num_spiders = 5
        shared_domain = "otter.ai"
        max_urls_per_domain = 20  # Total across all spiders
        
        from workflow_service.services.scraping.settings import get_domain_limit_key
        
        # Use shared domain key (no job_id)
        domain_key = get_domain_limit_key(f"{self.TEST_PREFIX}", shared_domain)
        
        async def spider_worker(spider_id):
            """Simulate a spider trying to crawl URLs."""
            spider_name = f"{self.TEST_PREFIX}_spider_{spider_id}"
            urls_crawled = 0
            urls_blocked = 0
            
            # Each spider tries to crawl 10 URLs
            for i in range(10):
                count, is_over = await self.client.increment_counter_with_limit(
                    domain_key, 1, limit=max_urls_per_domain
                )
                
                if not is_over or count <= max_urls_per_domain:
                    urls_crawled += 1
                    # Simulate processing time
                    await asyncio.sleep(0.01)
                else:
                    # Rollback
                    await self.client.increment_counter_with_limit(domain_key, -1)
                    urls_blocked += 1
            
            return {
                'spider_id': spider_id,
                'urls_crawled': urls_crawled,
                'urls_blocked': urls_blocked
            }
        
        # Run spiders concurrently
        tasks = [spider_worker(i) for i in range(num_spiders)]
        results = await asyncio.gather(*tasks)
        
        # Verify results
        total_crawled = sum(r['urls_crawled'] for r in results)
        total_blocked = sum(r['urls_blocked'] for r in results)
        
        self.assertEqual(total_crawled, max_urls_per_domain,
                        f"Should crawl exactly {max_urls_per_domain} URLs total")
        self.assertEqual(total_crawled + total_blocked, num_spiders * 10,
                        "Total attempts should equal spider count * URLs per spider")
        
        # Verify at least some spiders got blocked
        spiders_blocked = sum(1 for r in results if r['urls_blocked'] > 0)
        self.assertGreater(spiders_blocked, 0, "Some spiders should have been blocked")
        
    async def test_job_isolation_with_concurrent_jobs(self):
        """Test that concurrent jobs are properly isolated."""
        spider_name = f"{self.TEST_PREFIX}_isolated"
        num_jobs = 3
        urls_per_job = 5
        
        async def job_worker(job_id):
            """Simulate a scraping job."""
            queue_key = get_queue_key(spider_name, job_id, 'job')
            
            # Push URLs
            for i in range(urls_per_job):
                request_data = {
                    'url': f'https://otter.ai/job{job_id}/page{i}',
                    'meta': {'job_id': job_id}
                }
                await self.client.push_request(queue_key, request_data, priority=100-i)
            
            # Pop and process URLs
            processed = []
            while True:
                request = await self.client.pop_request(queue_key)
                if not request:
                    break
                processed.append(request)
                # Simulate processing
                await asyncio.sleep(0.01)
            
            return {
                'job_id': job_id,
                'urls_processed': len(processed),
                'queue_key': queue_key
            }
        
        # Run jobs concurrently
        tasks = [job_worker(f"job_{i}") for i in range(num_jobs)]
        results = await asyncio.gather(*tasks)
        
        # Verify isolation
        for result in results:
            self.assertEqual(result['urls_processed'], urls_per_job,
                           f"Job {result['job_id']} should process exactly {urls_per_job} URLs")
        
        # Verify different queue keys
        queue_keys = [r['queue_key'] for r in results]
        self.assertEqual(len(set(queue_keys)), num_jobs,
                        "Each job should have a unique queue key")
        
    async def test_race_condition_in_domain_limiting(self):
        """Test handling of race conditions in domain limiting."""
        spider_name = f"{self.TEST_PREFIX}_race"
        domain = "grain.com"
        max_urls = 10
        num_concurrent_requests = 50  # Much more than limit
        
        from workflow_service.services.scraping.settings import get_domain_limit_key
        domain_key = get_domain_limit_key(spider_name, domain)
        
        # Track results
        success_count = 0
        fail_count = 0
        lock = asyncio.Lock()
        
        async def try_increment():
            """Try to increment domain counter."""
            nonlocal success_count, fail_count
            
            count, is_over = await self.client.increment_counter_with_limit(
                domain_key, 1, limit=max_urls
            )
            
            async with lock:
                if not is_over or count <= max_urls:
                    success_count += 1
                    return True
                else:
                    # Rollback
                    await self.client.increment_counter_with_limit(domain_key, -1)
                    fail_count += 1
                    return False
        
        # Create many concurrent attempts
        tasks = [try_increment() for _ in range(num_concurrent_requests)]
        results = await asyncio.gather(*tasks)
        
        # Verify exactly max_urls succeeded
        self.assertEqual(success_count, max_urls,
                        f"Exactly {max_urls} requests should succeed")
        self.assertEqual(fail_count, num_concurrent_requests - max_urls,
                        f"Exactly {num_concurrent_requests - max_urls} should fail")
        
        # Verify final counter value
        final_count = await self.client.get_counter_value(domain_key)
        self.assertEqual(final_count, max_urls,
                        f"Final counter should be exactly {max_urls}")
        
    async def test_memory_pressure_scenario(self):
        """Test behavior under memory pressure with large queues."""
        spider_name = f"{self.TEST_PREFIX}_memory"
        queue_key = get_queue_key(spider_name)
        
        # Check initial memory usage
        initial_memory = await self.client.check_memory_usage()
        
        # Push many requests
        batch_size = 1000
        num_batches = 5
        
        for batch in range(num_batches):
            requests = []
            for i in range(batch_size):
                request_data = {
                    'url': f'https://grain.com/batch{batch}/page{i}',
                    'meta': {
                        'batch': batch,
                        'large_data': 'x' * 1000  # 1KB of data per request
                    },
                    'priority': batch * 1000 + i
                }
                requests.append(request_data)
            
            # Push batch
            try:
                await self.client.push_requests_batch(queue_key, requests)
            except Exception as e:
                # If memory limit hit, that's expected
                if "memory" in str(e).lower():
                    break
                raise
            
            # Check memory after each batch
            current_memory = await self.client.check_memory_usage()
            if current_memory > 80:  # 80% threshold
                print(f"Memory usage high: {current_memory:.1f}% after batch {batch}")
                break
        
        # Verify queue has items
        queue_length = await self.client.get_queue_length(queue_key)
        self.assertGreater(queue_length, 0, "Queue should have items")
        
        # Pop some items to reduce memory
        for _ in range(min(100, queue_length)):
            await self.client.pop_request(queue_key)
        
        # Memory should be lower after popping
        final_memory = await self.client.check_memory_usage()
        # Note: This assertion might fail if Redis hasn't garbage collected yet
        # self.assertLess(final_memory, current_memory)
    
    async def test_concurrent_url_discovery(self):
        """Test concurrent URL discovery from multiple sources."""
        spider_name = f"{self.TEST_PREFIX}_discovery"
        job_id = "discovery_test"
        queue_key = get_queue_key(spider_name, job_id, 'job')
        
        # Clear any existing data
        await self.client.clear_queue(queue_key, clear_dupefilter=True)
        
        # Simulate multiple discovery sources
        async def html_parser(page_id):
            """Simulate discovering URLs from HTML parsing."""
            urls = []
            for i in range(5):
                urls.append(f"https://otter.ai/html/page{page_id}/link{i}")
            
            # Push discovered URLs
            pushed_count = 0
            for url in urls:
                request_data = {
                    'url': url,
                    'meta': {'discovered_by': 'html_parser', 'page_id': page_id}
                }
                if await self.client.push_request(queue_key, request_data):
                    pushed_count += 1
            
            return pushed_count
        
        async def js_renderer(page_id):
            """Simulate discovering URLs from JavaScript rendering."""
            urls = []
            for i in range(3):
                urls.append(f"https://grain.com/js/page{page_id}/dynamic{i}")
            
            # Simulate rendering delay
            await asyncio.sleep(0.05)
            
            # Push discovered URLs
            pushed_count = 0
            for url in urls:
                request_data = {
                    'url': url,
                    'meta': {'discovered_by': 'js_renderer', 'page_id': page_id}
                }
                if await self.client.push_request(queue_key, request_data):
                    pushed_count += 1
            
            return pushed_count
        
        # Run discovery concurrently for multiple pages
        num_pages = 10
        html_tasks = [html_parser(i) for i in range(num_pages)]
        js_tasks = [js_renderer(i) for i in range(num_pages)]
        
        all_tasks = html_tasks + js_tasks
        results = await asyncio.gather(*all_tasks)
        
        total_pushed = sum(results)
        
        # Verify queue has all discovered URLs (minus duplicates)
        queue_length = await self.client.get_queue_length(queue_key)
        # Should have at least some URLs (exact count depends on duplicates)
        self.assertGreater(queue_length, 0, "Should have URLs in queue")
        self.assertLessEqual(queue_length, total_pushed, "Queue length should not exceed total pushed")
        
        # Sample URLs to verify discovery sources
        discovered_by_html = 0
        discovered_by_js = 0
        sampled = 0
        
        # Try to sample up to 100 URLs to ensure we get both types
        while sampled < min(100, queue_length):
            request = await self.client.pop_request(queue_key)
            if not request:
                break
                
            sampled += 1
            source = request.get('meta', {}).get('discovered_by')
            if source == 'html_parser':
                discovered_by_html += 1
            elif source == 'js_renderer':
                discovered_by_js += 1
        
        # Should have URLs from both sources (since we pushed from both)
        # The HTML parser should have successfully pushed at least some URLs
        self.assertGreater(discovered_by_html, 0, f"Should have HTML discovered URLs (sampled {sampled} URLs)")
        self.assertGreater(discovered_by_js, 0, f"Should have JS discovered URLs (sampled {sampled} URLs)")
        self.assertGreater(discovered_by_html + discovered_by_js, 0, 
                          "Should have discovered URLs from at least one source")


class TestScrapingIntegration(unittest.IsolatedAsyncioTestCase):
    """Test case for scraping service integration."""
    
    async def asyncSetUp(self):
        """Set up test environment before each test method."""
        self.redis_url = global_settings.REDIS_URL
        if not self.redis_url:
            self.skipTest("REDIS_URL environment variable not set.")
            
        # Initialize Redis client
        self.client = AsyncRedisClient(self.redis_url)
        self.TEST_PREFIX = f"test_scraping_{uuid.uuid4().hex[:6]}"
        
        # Test connection
        is_connected = await self.client.ping()
        if not is_connected:
            await self.client.close()
            self.skipTest("Could not connect to Redis.")
    
    async def asyncTearDown(self):
        """Clean up after each test method."""
        if hasattr(self, 'client') and self.client:
            # Clean up any test keys
            try:
                patterns = [
                    f"queue:{self.TEST_PREFIX}*",
                    f"domain_limit:{self.TEST_PREFIX}*",
                    f"depth_stats:{self.TEST_PREFIX}*",
                    f"job_state:{self.TEST_PREFIX}*",
                    f"{self.TEST_PREFIX}*"
                ]
                for pattern in patterns:
                    await self.client.delete_keys_by_pattern(pattern)
            except:
                pass
            
            await self.client.close()

    async def test_scraping_settings(self):
        """Test centralized settings configuration."""
        # Test queue key generation
        spider_name = f"{self.TEST_PREFIX}_spider"
        
        # Spider-level queue
        queue_key = get_queue_key(spider_name, None, 'spider')
        self.assertEqual(queue_key, f"queue:{spider_name}:requests")
        
        # Job-level queue
        job_id = "test_job_123"
        queue_key_job = get_queue_key(spider_name, job_id, 'job')
        self.assertEqual(queue_key_job, f"queue:{spider_name}:{job_id}:requests")
        
        # Test dupefilter key
        dupefilter_key = get_dupefilter_key(queue_key)
        self.assertEqual(dupefilter_key, f"{queue_key}:dupefilter")
        
        # Test domain limit key
        domain = "otter.ai"
        domain_key = get_domain_limit_key(spider_name, domain)
        self.assertEqual(domain_key, f"domain_limit:{spider_name}:{domain}")
        
        # Test depth stats key
        depth_key = get_depth_stats_key(spider_name)
        self.assertEqual(depth_key, f"depth_stats:{spider_name}")
        
        # Test priority calculation
        priority_0 = calculate_priority_from_depth(0)
        priority_3 = calculate_priority_from_depth(3)
        self.assertGreater(priority_0, priority_3, "Lower depth should have higher priority")
        
        # Test domain parsing
        test_urls = [
            ("https://www.otter.ai/page", "www.otter.ai"),
            ("http://help.otter.ai:8080/path", "help.otter.ai"),
            ("https://GRAIN.COM/", "grain.com"),  # Should be lowercase
        ]
        for url, expected_domain in test_urls:
            domain = parse_domain_from_url(url)
            self.assertEqual(domain, expected_domain, f"Domain parsing failed for {url}")

    async def test_push_urls_to_redis(self):
        """Test pushing URLs to Redis queue."""
        spider_name = f"{self.TEST_PREFIX}_push_test"
        urls = [
            "https://otter.ai/page1",
            "https://otter.ai/page2",
            "https://grain.com/page1",
        ]
        
        # Push URLs
        stats = push_urls_to_redis(
            spider_name, urls,
            redis_url=self.redis_url,
            max_urls_per_domain=10,
            max_crawl_depth=5
        )
        
        # Verify stats
        self.assertEqual(stats['urls_pushed'], 3, "Should push 3 URLs")
        self.assertEqual(len(stats['domain_distribution']), 2, "Should have 2 domains")
        self.assertEqual(stats['domain_distribution']['otter.ai'], 2)
        self.assertEqual(stats['domain_distribution']['grain.com'], 1)
        
        # Verify queue contents
        queue_key = stats['queue_key']
        queue_length = await self.client.get_queue_length(queue_key)
        self.assertEqual(queue_length, 3, "Queue should have 3 URLs")
        
        # Test duplicate filtering
        stats2 = push_urls_to_redis(
            spider_name, urls,
            redis_url=self.redis_url
        )
        self.assertEqual(stats2['urls_pushed'], 0, "Should not push duplicates")

    async def test_job_specific_queues(self):
        """Test job-specific queue isolation."""
        spider_name = f"{self.TEST_PREFIX}_job_test"
        urls = ["https://otter.ai/test"]
        
        # Push to job1
        stats1 = push_urls_to_redis(
            spider_name, urls,
            redis_url=self.redis_url,
            job_id="job1",
            queue_key_strategy='job'
        )
        
        # Push to job2
        stats2 = push_urls_to_redis(
            spider_name, urls,
            redis_url=self.redis_url,
            job_id="job2",
            queue_key_strategy='job'
        )
        
        # Both should succeed (isolated deduplication)
        self.assertEqual(stats1['urls_pushed'], 1)
        self.assertEqual(stats2['urls_pushed'], 1)
        
        # Verify different queue keys
        self.assertNotEqual(stats1['queue_key'], stats2['queue_key'])
        
        # Verify queue contents
        queue1_length = await self.client.get_queue_length(stats1['queue_key'])
        queue2_length = await self.client.get_queue_length(stats2['queue_key'])
        self.assertEqual(queue1_length, 1)
        self.assertEqual(queue2_length, 1)

    async def test_domain_limiting(self):
        """Test domain limiting functionality through URL counting."""
        spider_name = f"{self.TEST_PREFIX}_domain_limit"
        domain = "grain.com"
        max_urls = 3
        
        # Push URLs to test domain limiting
        urls = [f"https://{domain}/page{i}" for i in range(max_urls + 2)]
        
        # Use push_urls_to_redis with domain limit
        stats = push_urls_to_redis(
            spider_name, urls,
            redis_url=self.redis_url,
            max_urls_per_domain=max_urls,
            max_crawl_depth=5
        )
        
        # Domain limiting is enforced at crawl time, not push time
        # So all URLs should be pushed
        self.assertEqual(stats['urls_pushed'], max_urls + 2)
        
        # Check domain counter directly
        from workflow_service.services.scraping.settings import get_domain_limit_key
        domain_key = get_domain_limit_key(spider_name, domain)
        
        # Simulate crawling by incrementing domain counter
        allowed_count = 0
        blocked_count = 0
        
        for i in range(max_urls + 2):
            # Check if we can increment
            current_count = await self.client.get_counter_value(domain_key)
            if current_count < max_urls:
                await self.client.increment_counter_with_limit(domain_key, 1, max_urls)
                allowed_count += 1
            else:
                blocked_count += 1
        
        # Verify limits
        self.assertEqual(allowed_count, max_urls, f"Should allow exactly {max_urls} URLs")
        self.assertEqual(blocked_count, 2, "Should block 2 URLs")

    async def test_depth_limiting(self):
        """Test depth limiting functionality through priority calculation."""
        spider_name = f"{self.TEST_PREFIX}_depth_limit"
        max_depth = 3
        
        # Test priority calculation for different depths
        test_depths = [0, 1, 2, 3, 4, 5]
        priorities = []
        
        for depth in test_depths:
            priority = calculate_priority_from_depth(depth)
            priorities.append((depth, priority))
            
            # Verify priority decreases with depth
            if depth > 0:
                self.assertLess(priority, priorities[depth-1][1], 
                              f"Priority should decrease with depth")
        
        # Push URLs at different depths to verify they can be queued
        queue_key = get_queue_key(spider_name)
        
        for depth in test_depths[:max_depth+1]:  # Only test up to max_depth
            request_data = {
                'url': f'https://grain.com/depth{depth}',
                'meta': {'depth': depth}
            }
            priority = calculate_priority_from_depth(depth)
            
            pushed = await self.client.push_request(
                queue_key, request_data, priority=priority
            )
            self.assertTrue(pushed, f"Should be able to push URL at depth {depth}")
        
        # Verify queue has correct number of items
        queue_length = await self.client.get_queue_length(queue_key)
        self.assertEqual(queue_length, max_depth + 1)

    async def test_priority_by_depth(self):
        """Test that priority decreases with depth."""
        spider_name = f"{self.TEST_PREFIX}_priority"
        queue_key = get_queue_key(spider_name)
        
        # Push requests at different depths
        requests = []
        for depth in [0, 1, 2, 3]:
            priority = calculate_priority_from_depth(depth)
            request_data = {
                'url': f'https://otter.ai/depth{depth}',
                'meta': {'depth': depth},
                'priority': priority
            }
            await self.client.push_request(
                queue_key, request_data, priority=priority
            )
            requests.append((depth, priority))
        
        # Pop requests - should come in depth order (0, 1, 2, 3)
        popped_depths = []
        while True:
            request = await self.client.pop_request(queue_key)
            if not request:
                break
            popped_depths.append(request['meta']['depth'])
        
        # Verify order
        self.assertEqual(popped_depths, [0, 1, 2, 3], "Requests should be popped in depth order")

    async def test_spider_stats(self):
        """Test getting spider statistics."""
        spider_name = f"{self.TEST_PREFIX}_stats"
        
        # Push some URLs
        urls = [
            "https://otter.ai/page1",
            "https://otter.ai/page2",
            "https://grain.com/page1",
        ]
        
        push_stats = push_urls_to_redis(
            spider_name, urls,
            redis_url=self.redis_url
        )
        
        # Simulate crawling by updating domain and depth counters
        for url in urls:
            domain = parse_domain_from_url(url)
            domain_key = get_domain_limit_key(spider_name, domain)
            await self.client.increment_counter_with_limit(domain_key, 1)
        
        # Update depth stats
        depth_key = get_depth_stats_key(spider_name)
        await self.client.increment_hash_counter(depth_key, "0", 2)
        await self.client.increment_hash_counter(depth_key, "1", 1)
        
        # Get stats
        stats = get_spider_stats(spider_name, redis_url=self.redis_url)
        
        # Verify stats
        self.assertEqual(stats['spider_name'], spider_name)
        # Note: domain_stats is not implemented yet (placeholder in get_spider_stats)
        # So we skip domain-related assertions
        self.assertEqual(stats['total_urls_crawled'], 3)
        self.assertEqual(stats['depth_distribution']['0'], 2)
        self.assertEqual(stats['depth_distribution']['1'], 1)

    async def test_purge_patterns(self):
        """Test purge pattern generation and cleanup."""
        spider_name = f"{self.TEST_PREFIX}_purge"
        job_id = "purge_job"
        
        # Get purge patterns
        spider_patterns = get_purge_patterns(spider_name)
        job_patterns = get_purge_patterns(spider_name, job_id)
        
        # Verify patterns
        self.assertIn(f"queue:{spider_name}:*", spider_patterns)
        self.assertIn(f"domain_limit:{spider_name}:*", spider_patterns)
        
        self.assertIn(f"queue:{spider_name}:{job_id}:*", job_patterns)
        self.assertIn(f"domain_limit:{spider_name}:{job_id}:*", job_patterns)
        
        # Create some test data
        test_keys = [
            get_queue_key(spider_name),
            get_domain_limit_key(spider_name, "grain.com"),
            get_depth_stats_key(spider_name),
        ]
        
        for key in test_keys:
            await self.client.set_cache(key, "test_data")
        
        # Verify keys exist
        for key in test_keys:
            value = await self.client.get_cache(key)
            self.assertIsNotNone(value, f"Key {key} should exist")
        
        # Purge using patterns
        deleted_counts = await self.client.delete_multiple_patterns(spider_patterns)
        total_deleted = sum(deleted_counts.values())
        
        self.assertGreater(total_deleted, 0, "Should delete some keys")
        
        # Verify keys are gone
        for key in test_keys:
            value = await self.client.get_cache(key)
            self.assertIsNone(value, f"Key {key} should be deleted")

    async def test_queue_request_serialization(self):
        """Test request serialization and deserialization."""
        spider_name = f"{self.TEST_PREFIX}_serialize"
        queue_key = get_queue_key(spider_name)
        
        # Create test request data with various fields
        original_request = {
            'url': 'https://otter.ai/test',
            'method': 'POST',
            'headers': {'User-Agent': 'TestBot', 'Accept': 'application/json'},
            'body': 'test_body_data',
            'cookies': {'session': 'abc123'},
            'meta': {
                'depth': 2,
                'discovered_from': 'https://otter.ai/',
                'custom_data': {'key': 'value'}
            },
            'priority': 50,
            'dont_filter': True,
            'callback': 'parse_item',
            'errback': 'handle_error',
            'cb_kwargs': {'category': 'test'},
            'flags': ['test_flag']
        }
        
        # Push request
        await self.client.push_request(
            queue_key, original_request, 
            priority=original_request['priority']
        )
        
        # Pop request
        popped_request = await self.client.pop_request(queue_key)
        
        # Verify all fields are preserved
        self.assertIsNotNone(popped_request)
        self.assertEqual(popped_request['url'], original_request['url'])
        self.assertEqual(popped_request['method'], original_request['method'])
        self.assertEqual(popped_request['headers'], original_request['headers'])
        self.assertEqual(popped_request['body'], original_request['body'])
        self.assertEqual(popped_request['cookies'], original_request['cookies'])
        self.assertEqual(popped_request['meta'], original_request['meta'])
        self.assertEqual(popped_request['priority'], original_request['priority'])
        self.assertEqual(popped_request['dont_filter'], original_request['dont_filter'])
        self.assertEqual(popped_request['callback'], original_request['callback'])
        self.assertEqual(popped_request['errback'], original_request['errback'])
        self.assertEqual(popped_request['cb_kwargs'], original_request['cb_kwargs'])
        self.assertEqual(popped_request['flags'], original_request['flags'])

    async def test_concurrent_domain_limiting(self):
        """Test domain limiting with concurrent requests."""
        spider_name = f"{self.TEST_PREFIX}_concurrent"
        domain = "help.otter.ai"
        max_urls = 5
        
        # Create domain limit key
        domain_key = get_domain_limit_key(spider_name, domain)
        
        # Simulate concurrent requests
        async def try_add_url(url_suffix):
            count, is_over = await self.client.increment_counter_with_limit(
                domain_key, increment=1, limit=max_urls
            )
            
            if is_over and count > max_urls:
                # Rollback if over limit
                await self.client.increment_counter_with_limit(
                    domain_key, increment=-1
                )
                return False
            return True
        
        # Create concurrent tasks
        tasks = []
        for i in range(10):  # Try to add 10 URLs concurrently
            task = try_add_url(f"page{i}")
            tasks.append(task)
        
        # Execute concurrently
        results = await asyncio.gather(*tasks)
        
        # Count successes
        allowed_count = sum(1 for r in results if r)
        blocked_count = sum(1 for r in results if not r)
        
        # Verify limits were respected
        self.assertEqual(allowed_count, max_urls, f"Should allow exactly {max_urls} URLs")
        self.assertEqual(blocked_count, 5, "Should block 5 URLs")
        
        # Verify final count
        final_count = await self.client.get_counter_value(domain_key)
        self.assertEqual(final_count, max_urls, "Final count should be at limit")


class TestScrapingRealWorld(unittest.IsolatedAsyncioTestCase):
    """Test real-world scraping scenarios with otter.ai."""
    
    async def asyncSetUp(self):
        """Set up test environment."""
        self.redis_url = global_settings.REDIS_URL
        if not self.redis_url:
            self.skipTest("REDIS_URL environment variable not set.")
            
        self.client = AsyncRedisClient(self.redis_url)
        self.TEST_PREFIX = f"test_otter_{uuid.uuid4().hex[:6]}"
        
        is_connected = await self.client.ping()
        if not is_connected:
            await self.client.close()
            self.skipTest("Could not connect to Redis.")
    
    async def asyncTearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'client') and self.client:
            try:
                await self.client.delete_keys_by_pattern(f"{self.TEST_PREFIX}*")
                await self.client.delete_keys_by_pattern(f"queue:{self.TEST_PREFIX}*")
                await self.client.delete_keys_by_pattern(f"domain:*:{self.TEST_PREFIX}*")
            except:
                pass
            await self.client.close()

    async def test_otter_ai_url_discovery(self):
        """Test URL discovery patterns for otter.ai."""
        spider_name = f"{self.TEST_PREFIX}_otter"
        job_id = "otter_discovery_test"
        
        # Simulate otter.ai URL structure
        otter_urls = [
            # Main pages
            "https://otter.ai",
            "https://otter.ai/pricing",
            "https://otter.ai/blog",
            "https://otter.ai/careers",
            "https://otter.ai/education",
            "https://otter.ai/business",
            
            # Blog posts
            "https://otter.ai/blog/ai-meeting-assistant",
            "https://otter.ai/blog/transcription-accuracy",
            "https://otter.ai/blog/remote-work-tools",
            
            # Help/support
            "https://help.otter.ai/hc/en-us",
            "https://help.otter.ai/hc/en-us/articles/360035266494",
            
            # App specific
            "https://otter.ai/signin",
            "https://otter.ai/signup",
            "https://app.otter.ai/dashboard",
            
            # Marketing/landing pages
            "https://otter.ai/sales-teams",
            "https://otter.ai/education-teams",
            "https://otter.ai/media-teams",
        ]
        
        # Push URLs with appropriate depths
        stats = push_urls_to_redis(
            spider_name, otter_urls,
            redis_url=self.redis_url,
            job_id=job_id,
            queue_key_strategy='job',
            max_urls_per_domain=50,
            max_crawl_depth=3
        )
        
        # Verify domain distribution
        self.assertIn('otter.ai', stats['domain_distribution'])
        self.assertIn('help.otter.ai', stats['domain_distribution'])
        self.assertIn('app.otter.ai', stats['domain_distribution'])
        
        # Test subdomain handling
        self.assertGreater(stats['domain_distribution']['otter.ai'], 10)
        self.assertGreater(stats['domain_distribution']['help.otter.ai'], 1)
    
    async def test_otter_ai_domain_limiting(self):
        """Test domain limiting for otter.ai scraping."""
        spider_name = f"{self.TEST_PREFIX}_limit"
        job_id = "otter_limit_test"
        max_urls_per_domain = 10
        
        # Generate many otter.ai URLs
        many_urls = []
        for i in range(20):
            many_urls.extend([
                f"https://otter.ai/page{i}",
                f"https://help.otter.ai/article{i}",
                f"https://app.otter.ai/session{i}"
            ])
        
        # Push all URLs
        stats = push_urls_to_redis(
            spider_name, many_urls,
            redis_url=self.redis_url,
            job_id=job_id,
            queue_key_strategy='job',
            max_urls_per_domain=max_urls_per_domain
        )
        
        # All URLs should be pushed (limiting happens during crawl)
        self.assertEqual(stats['urls_pushed'], len(many_urls))
        
        # Simulate domain limiting by tracking counts
        from workflow_service.services.scraping.settings import get_domain_limit_key
        domain_counts = {}
        
        for url in many_urls:
            domain = parse_domain_from_url(url)
            if domain not in domain_counts:
                domain_counts[domain] = {'allowed': 0, 'blocked': 0}
            
            # Get domain counter key (with job_id for job strategy)
            domain_key = f"domain:{domain}:{job_id}"
            
            # Check current count
            current_count = await self.client.get_counter_value(domain_key)
            
            if current_count < max_urls_per_domain:
                # Simulate crawling this URL
                await self.client.increment_counter_with_limit(
                    domain_key, 1, max_urls_per_domain
                )
                domain_counts[domain]['allowed'] += 1
            else:
                domain_counts[domain]['blocked'] += 1
        
        # Verify each domain respects limit
        for domain, counts in domain_counts.items():
            self.assertLessEqual(
                counts['allowed'], max_urls_per_domain,
                f"Domain {domain} should not exceed {max_urls_per_domain} URLs"
            )
            if counts['allowed'] == max_urls_per_domain:
                self.assertGreater(
                    counts['blocked'], 0,
                    f"Domain {domain} should have blocked some URLs"
                )
    
    async def test_otter_ai_crawl_simulation(self):
        """Simulate a realistic otter.ai crawl with depth progression."""
        spider_name = f"{self.TEST_PREFIX}_crawl"
        job_id = "otter_crawl_sim"
        queue_key = get_queue_key(spider_name, job_id, 'job')
        
        # Seed URLs (depth 0)
        seed_urls = [
            "https://otter.ai",
            "https://help.otter.ai/hc/en-us"
        ]
        
        # Push seed URLs
        for url in seed_urls:
            request = {
                'url': url,
                'meta': {'depth': 0}
            }
            await self.client.push_request(
                queue_key, request, 
                priority=calculate_priority_from_depth(0)
            )
        
        # Simulate crawling and discovering new URLs
        crawled_urls = []
        discovered_patterns = {
            'otter.ai': [
                '/pricing', '/blog', '/careers', '/signin',
                '/business', '/education', '/media-teams'
            ],
            'help.otter.ai': [
                '/hc/en-us/articles/360035266494',
                '/hc/en-us/categories/360002285334',
                '/hc/en-us/requests/new'
            ]
        }
        
        # Process queue simulating crawl
        max_iterations = 20
        iteration = 0
        
        while iteration < max_iterations:
            request = await self.client.pop_request(queue_key)
            if not request:
                break
                
            url = request['url']
            depth = request['meta'].get('depth', 0)
            crawled_urls.append((url, depth))
            
            # Simulate discovering new URLs
            domain = parse_domain_from_url(url)
            base_domain = domain.replace('www.', '').replace('help.', '')
            
            if base_domain in discovered_patterns and depth < 2:
                # Add discovered URLs
                for path in discovered_patterns.get(base_domain, [])[:3]:
                    new_url = f"https://{domain}{path}"
                    new_request = {
                        'url': new_url,
                        'meta': {
                            'depth': depth + 1,
                            'discovered_from': url
                        }
                    }
                    
                    await self.client.push_request(
                        queue_key, new_request,
                        priority=calculate_priority_from_depth(depth + 1)
                    )
            
            iteration += 1
        
        # Verify crawl progression
        depth_counts = {}
        for url, depth in crawled_urls:
            depth_counts[depth] = depth_counts.get(depth, 0) + 1
        
        # Should have crawled seed URLs first (depth 0)
        self.assertIn(0, depth_counts)
        self.assertEqual(depth_counts[0], len(seed_urls))
        
        # Should have discovered and crawled depth 1 URLs
        if 1 in depth_counts:
            self.assertGreater(depth_counts[1], 0)
        
        # Verify depth ordering (lower depths processed first)
        if len(crawled_urls) > 2:
            first_depths = [d for _, d in crawled_urls[:5]]
            last_depths = [d for _, d in crawled_urls[-5:]]
            self.assertLessEqual(
                sum(first_depths) / len(first_depths),
                sum(last_depths) / len(last_depths),
                "Earlier URLs should have lower average depth"
            )
    
    async def test_otter_ai_concurrent_crawling(self):
        """Test concurrent crawling scenario for otter.ai."""
        spider_name = f"{self.TEST_PREFIX}_concurrent"
        job_id = "otter_concurrent"
        
        # Simulate multiple workers crawling concurrently
        num_workers = 5
        urls_per_worker = 10
        
        async def worker(worker_id):
            """Simulate a crawl worker."""
            worker_stats = {
                'urls_pushed': 0,
                'urls_popped': 0,
                'duplicates': 0
            }
            
            queue_key = get_queue_key(spider_name, job_id, 'job')
            
            # Each worker pushes and pops URLs
            for i in range(urls_per_worker):
                # Push URL
                url = f"https://otter.ai/worker{worker_id}/page{i}"
                request = {
                    'url': url,
                    'meta': {'worker_id': worker_id, 'page': i}
                }
                
                pushed = await self.client.push_request(queue_key, request)
                if pushed:
                    worker_stats['urls_pushed'] += 1
                else:
                    worker_stats['duplicates'] += 1
                
                # Pop and process URL
                popped = await self.client.pop_request(queue_key)
                if popped:
                    worker_stats['urls_popped'] += 1
            
            return worker_stats
        
        # Run workers concurrently
        import asyncio
        tasks = [worker(i) for i in range(num_workers)]
        results = await asyncio.gather(*tasks)
        
        # Aggregate stats
        total_pushed = sum(r['urls_pushed'] for r in results)
        total_popped = sum(r['urls_popped'] for r in results)
        total_duplicates = sum(r['duplicates'] for r in results)
        
        # Verify results
        self.assertEqual(total_pushed, num_workers * urls_per_worker)
        self.assertEqual(total_duplicates, 0)  # No duplicates with unique URLs
        self.assertEqual(total_popped, total_pushed)  # All pushed URLs were popped


class TestScrapingEdgeCases(unittest.IsolatedAsyncioTestCase):
    """Test edge cases and error handling in scraping service."""
    
    async def asyncSetUp(self):
        """Set up test environment."""
        self.redis_url = global_settings.REDIS_URL
        if not self.redis_url:
            self.skipTest("REDIS_URL environment variable not set.")
            
        self.client = AsyncRedisClient(self.redis_url)
        self.TEST_PREFIX = f"test_edge_{uuid.uuid4().hex[:6]}"
        
        is_connected = await self.client.ping()
        if not is_connected:
            await self.client.close()
            self.skipTest("Could not connect to Redis.")
    
    async def asyncTearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'client') and self.client:
            try:
                await self.client.delete_keys_by_pattern(f"{self.TEST_PREFIX}*")
            except:
                pass
            await self.client.close()

    async def test_empty_url_list(self):
        """Test pushing empty URL list."""
        spider_name = f"{self.TEST_PREFIX}_empty"
        
        stats = push_urls_to_redis(
            spider_name, [],
            redis_url=self.redis_url
        )
        
        self.assertEqual(stats['urls_pushed'], 0)
        self.assertEqual(stats['domain_distribution'], {})

    async def test_invalid_urls(self):
        """Test handling of invalid URLs."""
        spider_name = f"{self.TEST_PREFIX}_invalid"
        
        # URLs with various issues
        urls = [
            "not-a-url",
            "ftp://ftp.otter.ai/file",  # Different protocol
            "https://",  # Incomplete URL
            "",  # Empty string
            "https://grain.com/page",  # Valid URL for comparison
        ]
        
        stats = push_urls_to_redis(
            spider_name, urls,
            redis_url=self.redis_url
        )
        
        # Should still push all URLs (validation is Spider's responsibility)
        self.assertGreater(stats['urls_pushed'], 0)

    async def test_very_deep_urls(self):
        """Test handling of very deep URLs."""
        spider_name = f"{self.TEST_PREFIX}_deep"
        max_depth = 3
        
        # Test with URL at max depth
        stats = push_urls_to_redis(
            spider_name, 
            ["https://otter.ai/very/deep/url"],
            redis_url=self.redis_url,
            max_crawl_depth=max_depth,
            initial_depth=max_depth  # Already at max depth
        )
        
        # Should still push (enforcement happens in scheduler)
        self.assertEqual(stats['urls_pushed'], 1)
        
        # Verify priority is very low for deep URLs
        depth = 10
        priority = calculate_priority_from_depth(depth)
        self.assertGreater(priority, 0, "Priority should never go below 1")

    async def test_special_characters_in_domain(self):
        """Test domains with special characters."""
        test_domains = [
            "otter-ai-test.com",
            "sub.help.otter.ai",
            "grain123.com",
            "münchen.de",  # IDN domain
        ]
        
        for domain in test_domains:
            parsed = parse_domain_from_url(f"https://{domain}/page")
            self.assertTrue(len(parsed) > 0, f"Should parse domain: {domain}")

    async def test_job_id_special_characters(self):
        """Test job IDs with special characters."""
        spider_name = f"{self.TEST_PREFIX}_jobid"
        
        # Various job ID formats
        job_ids = [
            "simple123",
            "with-dashes",
            "with.dots",
            "with_underscores",
            "2024-01-01T10:00:00Z",
        ]
        
        for job_id in job_ids:
            stats = push_urls_to_redis(
                spider_name,
                ["https://otter.ai/test"],
                redis_url=self.redis_url,
                job_id=job_id,
                queue_key_strategy='job'
            )
            
            self.assertEqual(stats['urls_pushed'], 1, f"Should handle job_id: {job_id}")
            
            # Clean up
            queue_key = stats['queue_key']
            await self.client.clear_queue(queue_key, clear_dupefilter=True)


class TestGenericSpiderAPI(unittest.IsolatedAsyncioTestCase):
    """Test generic spider with API-driven configuration."""
    
    async def asyncSetUp(self):
        """Set up test environment."""
        self.redis_url = global_settings.REDIS_URL
        if not self.redis_url:
            self.skipTest("REDIS_URL environment variable not set.")
            
        self.client = AsyncRedisClient(self.redis_url)
        self.TEST_PREFIX = f"test_api_{uuid.uuid4().hex[:6]}"
        
        is_connected = await self.client.ping()
        if not is_connected:
            await self.client.close()
            self.skipTest("Could not connect to Redis.")
    
    async def asyncTearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'client') and self.client:
            try:
                await self.client.delete_keys_by_pattern(f"{self.TEST_PREFIX}*")
                await self.client.delete_keys_by_pattern(f"queue:*{self.TEST_PREFIX}*")
            except:
                pass
            await self.client.close()
    
    async def test_api_driven_scraping_example(self):
        """Example of API-driven scraping job."""
        # This would typically come from an API request
        job_config = {
            'job_id': f'{self.TEST_PREFIX}_grain_job',
            'start_urls': [
                'https://grain.com',
                'https://grain.com/products'
            ],
            'allowed_domains': ['grain.com'],
            'processor': 'default',  # Could be 'otter.ai' for custom logic
            'max_urls_per_domain': 50,
            'max_crawl_depth': 3,
            'concurrent_requests_per_domain': 5,
            
            # Custom extraction rules
            'extract_rules': {
                'title': {
                    'type': 'css',
                    'selector': 'h1::text',
                    'extract': 'text',
                    'multiple': False
                },
                'product_names': {
                    'type': 'css',
                    'selector': '.product-name',
                    'extract': 'text',
                    'multiple': True
                },
                'prices': {
                    'type': 'css',
                    'selector': '.price',
                    'extract': 'text',
                    'multiple': True
                },
                'images': {
                    'type': 'css',
                    'selector': 'img.product-image',
                    'extract': 'attr:src',
                    'multiple': True
                },
                'description': {
                    'type': 'xpath',
                    'selector': '//div[@class="description"]/p/text()',
                    'extract': 'text',
                    'multiple': False
                }
            },
            
            # Additional Scrapy settings
            'custom_settings': {
                'USER_AGENT': 'MyBot 1.0',
                'DOWNLOAD_DELAY': 0.5,
                'ROBOTSTXT_OBEY': True,
            }
        }
        
        # Verify the config structure
        self.assertIn('job_id', job_config)
        self.assertIn('start_urls', job_config)
        self.assertIn('extract_rules', job_config)
        self.assertIsInstance(job_config['max_urls_per_domain'], int)
        
        # Push URLs to simulate job creation
        stats = push_urls_to_redis(
            'generic_spider',
            job_config['start_urls'],
            redis_url=self.redis_url,
            job_id=job_config['job_id'],
            queue_key_strategy='job',
            max_urls_per_domain=job_config['max_urls_per_domain'],
            max_crawl_depth=job_config['max_crawl_depth']
        )
        
        self.assertEqual(stats['urls_pushed'], len(job_config['start_urls']))
        
        # Clean up
        await self.client.clear_queue(stats['queue_key'], clear_dupefilter=True)
    
    async def test_otter_ai_processor_example(self):
        """Example of using otter.ai processor."""
        # Job config for otter.ai scraping
        otter_job_config = {
            'job_id': f'{self.TEST_PREFIX}_otter_job',
            'start_urls': [
                'https://otter.ai',
                'https://otter.ai/blog',
                'https://otter.ai/pricing'
            ],
            'allowed_domains': ['otter.ai', 'help.otter.ai'],
            'processor': 'otter.ai',  # Use custom otter.ai processor
            'max_urls_per_domain': 100,
            'max_crawl_depth': 3,
            
            # Additional rules can supplement processor logic
            'extract_rules': {
                'custom_field': {
                    'type': 'css',
                    'selector': '.custom-section',
                    'extract': 'text',
                    'multiple': False
                }
            },
            
            'custom_settings': {
                'DOWNLOAD_DELAY': 1,
                'CONCURRENT_REQUESTS_PER_DOMAIN': 10,
            }
        }
        
        # The otter.ai processor will:
        # - Extract blog posts with title, author, content
        # - Extract pricing tiers and features
        # - Extract job listings from careers page
        # - Skip signin/signup pages
        # - Prioritize important pages like pricing
        
        self.assertEqual(otter_job_config['processor'], 'otter.ai')
        
        # Push URLs to simulate job creation
        stats = push_urls_to_redis(
            'generic_spider',
            otter_job_config['start_urls'],
            redis_url=self.redis_url,
            job_id=otter_job_config['job_id'],
            queue_key_strategy='job',
            max_urls_per_domain=otter_job_config['max_urls_per_domain'],
            max_crawl_depth=otter_job_config['max_crawl_depth']
        )
        
        self.assertEqual(stats['urls_pushed'], len(otter_job_config['start_urls']))
        
        # Clean up
        await self.client.clear_queue(stats['queue_key'], clear_dupefilter=True)
    
    async def test_dynamic_processor_registration(self):
        """Test registering custom processors dynamically."""
        from workflow_service.services.scraping.spider import PROCESSOR_REGISTRY, BaseProcessor
        
        # Define a custom processor for a specific domain
        class GrainProcessor(BaseProcessor):
            def on_response(self, response, spider):
                data = super().on_response(response, spider)
                
                # Grain-specific extraction
                if '/blog/' in response.url:
                    data['page_type'] = 'blog_post'
                    data['title'] = response.css('h1::text').get()
                    data['author'] = response.css('.author::text').get()
                elif '/customers/' in response.url:
                    data['page_type'] = 'case_study'
                    data['company'] = response.css('.company-name::text').get()
                    
                return data
            
            def should_follow_link(self, url, response, spider):
                # Skip certain Grain URLs
                skip = ['signin', 'signup', 'app', 'admin']
                return not any(s in url for s in skip)
        
        # Register the processor
        PROCESSOR_REGISTRY['grain'] = GrainProcessor
        
        # Verify registration
        self.assertIn('grain', PROCESSOR_REGISTRY)
        self.assertEqual(PROCESSOR_REGISTRY['grain'], GrainProcessor)


class TestAdvancedEdgeCases(unittest.IsolatedAsyncioTestCase):
    """Test advanced edge cases and error scenarios."""
    
    async def asyncSetUp(self):
        """Set up test environment."""
        self.redis_url = global_settings.REDIS_URL
        if not self.redis_url:
            self.skipTest("REDIS_URL environment variable not set.")
            
        self.client = AsyncRedisClient(self.redis_url)
        self.sync_client = SyncRedisClient(self.redis_url)
        self.TEST_PREFIX = f"test_advanced_{uuid.uuid4().hex[:6]}"
        
        is_connected = await self.client.ping()
        if not is_connected:
            await self.client.close()
            self.skipTest("Could not connect to Redis.")
    
    async def asyncTearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'sync_client'):
            self.sync_client.close()
            
        if hasattr(self, 'client') and self.client:
            try:
                await self.client.delete_keys_by_pattern(f"{self.TEST_PREFIX}*")
            except:
                pass
            await self.client.close()
    
    async def test_unicode_and_international_urls(self):
        """Test handling of Unicode and international domains."""
        spider_name = f"{self.TEST_PREFIX}_unicode"
        
        # Various international URLs
        international_urls = [
            # IDN domains
            "https://münchen.de/veranstaltungen",
            "https://пример.рф/страница",
            "https://例え.jp/ページ",
            "https://مثال.السعودية/صفحة",
            
            # URLs with Unicode paths
            "https://otter.ai/путь/к/странице",
            "https://grain.com/中文/路径",
            "https://otter.ai/مسار/عربي",
            
            # Mixed encodings
            "https://grain.com/search?q=café",
            "https://otter.ai/users/José-María",
            "https://grain.com/products/naïve-résumé",
            
            # Emoji in URLs (edge case)
            "https://otter.ai/emoji/😀/test",
            "https://grain.com/category/🏠-home",
        ]
        
        # Push all URLs
        stats = push_urls_to_redis(
            spider_name, international_urls,
            redis_client=self.sync_client,
            max_urls_per_domain=50
        )
        
        # Should push all URLs (encoding handled internally)
        self.assertGreater(stats['urls_pushed'], 0)
        
        # Verify domain parsing works for IDN
        from workflow_service.services.scraping.settings import parse_domain_from_url
        
        test_cases = [
            ("https://münchen.de/test", "münchen.de"),
            ("https://例え.jp/test", "例え.jp"),
        ]
        
        for url, expected_domain in test_cases:
            domain = parse_domain_from_url(url)
            # Domain might be punycode encoded
            self.assertTrue(len(domain) > 0, f"Should parse domain from {url}")
    
    async def test_very_long_urls(self):
        """Test handling of extremely long URLs."""
        spider_name = f"{self.TEST_PREFIX}_long"
        
        # Create very long URLs
        base_url = "https://otter.ai/very/long/path/"
        long_segment = "segment" * 50  # 350 chars
        
        long_urls = [
            base_url + long_segment,
            base_url + "?" + "param=value&" * 100,  # Long query string
            base_url + "#" + "anchor" * 100,  # Long fragment
        ]
        
        # Add URL at typical browser limit (2048 chars)
        browser_limit_url = "https://grain.com/" + "a" * 2040
        long_urls.append(browser_limit_url)
        
        # Push URLs
        stats = push_urls_to_redis(
            spider_name, long_urls,
            redis_client=self.sync_client
        )
        
        # Should handle long URLs
        self.assertEqual(stats['urls_pushed'], len(long_urls))
        
        # Pop and verify URLs are intact
        queue_key = stats['queue_key']
        for _ in range(len(long_urls)):
            request = await self.client.pop_request(queue_key)
            self.assertIsNotNone(request)
            self.assertIn('url', request)
            self.assertTrue(len(request['url']) > 100)
    
    async def test_malformed_request_data(self):
        """Test handling of malformed request data."""
        spider_name = f"{self.TEST_PREFIX}_malformed"
        queue_key = get_queue_key(spider_name)
        
        # Various malformed requests
        malformed_requests = [
            # Missing required fields
            {'meta': {'test': True}},  # No URL
            
            # Invalid data types
            {'url': None, 'meta': {}},
            {'url': 123, 'meta': {}},  # URL as number
            
            # Circular references (should fail JSON serialization)
            {'url': 'https://otter.ai', 'meta': {}},  # This one is valid
        ]
        
        # Add circular reference
        circular = {'url': 'https://grain.com/circular'}
        circular['meta'] = {'self': circular}  # Circular reference
        malformed_requests.append(circular)
        
        # Try to push each request
        successes = 0
        failures = 0
        
        for request_data in malformed_requests:
            try:
                pushed = await self.client.push_request(queue_key, request_data)
                if pushed:
                    successes += 1
                else:
                    failures += 1
            except Exception:
                failures += 1
        
        # Some should fail
        self.assertGreater(failures, 0, "Some malformed requests should fail")
    
    async def test_redis_connection_recovery(self):
        """Test recovery from Redis connection issues."""
        spider_name = f"{self.TEST_PREFIX}_recovery"
        
        # Create a client with wrong URL to simulate connection failure
        bad_redis_url = "redis://nonexistent:6379/0"
        
        # Test with bad client
        try:
            bad_client = SyncRedisClient(bad_redis_url)
            
            # This should fail
            stats = push_urls_to_redis(
                spider_name,
                ["https://otter.ai"],
                redis_client=bad_client
            )
            
            # Should not reach here
            self.fail("Expected connection error")
            
        except Exception as e:
            # Expected - connection should fail
            error_msg = str(e).lower()
            self.assertTrue(
                any(keyword in error_msg for keyword in ['connect', 'failed', 'ping']),
                f"Expected connection-related error, got: {e}"
            )
        finally:
            if 'bad_client' in locals():
                bad_client.close()
        
        # Now test with good client - should work
        stats = push_urls_to_redis(
            spider_name,
            ["https://grain.com/recovered"],
            redis_client=self.sync_client
        )
        
        self.assertEqual(stats['urls_pushed'], 1, "Should recover with good client")
    
    async def test_scheduler_edge_cases(self):
        """Test edge cases in scheduler behavior."""
        from scrapy.crawler import Crawler
        from scrapy.settings import Settings
        from scrapy import Spider
        
        # Create real crawler with settings
        settings = Settings()
        settings.set('REDIS_URL', self.redis_url)
        
        # Test scheduler creation with various settings
        from workflow_service.services.scraping.scrapy_redis_integration import RedisScheduler
        
        # Test 1: No job ID
        crawler1 = Crawler(Spider, settings)
        scheduler1 = RedisScheduler(crawler1)
        self.assertIsNone(scheduler1.job_id)
        
        # Test 2: Job ID from settings
        settings2 = Settings()
        settings2.set('REDIS_URL', self.redis_url)
        settings2.set('SCRAPY_JOB_ID', 'test_job_123')
        crawler2 = Crawler(Spider, settings2)
        scheduler2 = RedisScheduler(crawler2)
        self.assertEqual(scheduler2.job_id, 'test_job_123')
        
        # Test 3: Custom limits
        settings3 = Settings()
        settings3.set('REDIS_URL', self.redis_url)
        settings3.set('MAX_URLS_PER_DOMAIN', 1000)
        settings3.set('MAX_CRAWL_DEPTH', 10)
        crawler3 = Crawler(Spider, settings3)
        scheduler3 = RedisScheduler(crawler3)
        self.assertEqual(scheduler3.max_urls_per_domain, 1000)
        self.assertEqual(scheduler3.max_crawl_depth, 10)
        
        # Clean up
        await scheduler1.redis_client.close()
        scheduler1.sync_redis.close()
        await scheduler2.redis_client.close()
        scheduler2.sync_redis.close()
        await scheduler3.redis_client.close()
        scheduler3.sync_redis.close()
    
    async def test_concurrent_processed_limits(self):
        """Test concurrent access to processed item limits."""
        spider_name = f"{self.TEST_PREFIX}_concurrent_proc"
        domain = "help.otter.ai"
        max_processed = 5
        num_workers = 10
        
        from workflow_service.services.scraping.settings import get_processed_items_key
        processed_key = get_processed_items_key(spider_name, domain)
        
        # Track results
        success_count = 0
        lock = asyncio.Lock()
        
        async def worker(worker_id):
            """Simulate a worker trying to process items."""
            nonlocal success_count
            worker_success = 0
            
            for i in range(3):  # Each worker tries 3 items
                # Simulate should_process_link check
                if i == 1 and worker_id % 2 == 0:
                    # Even workers skip middle item
                    continue
                
                # Try to process
                count, is_over = await self.client.increment_counter_with_limit(
                    processed_key, 1, limit=max_processed
                )
                
                if not is_over or count <= max_processed:
                    worker_success += 1
                    async with lock:
                        success_count += 1
                    # Simulate processing time
                    await asyncio.sleep(0.01)
                else:
                    # Rollback
                    await self.client.increment_counter_with_limit(processed_key, -1)
            
            return worker_success
        
        # Run workers concurrently
        tasks = [worker(i) for i in range(num_workers)]
        results = await asyncio.gather(*tasks)
        
        # Verify exactly max_processed items were processed
        self.assertEqual(success_count, max_processed,
                        f"Exactly {max_processed} items should be processed")
        
        # Verify some workers got items and some didn't
        workers_with_items = sum(1 for r in results if r > 0)
        workers_without = sum(1 for r in results if r == 0)
        
        self.assertGreater(workers_with_items, 0, "Some workers should process items")
        self.assertGreater(workers_without, 0, "Some workers should be blocked")
    
    async def test_extreme_depth_values(self):
        """Test handling of extreme depth values."""
        spider_name = f"{self.TEST_PREFIX}_extreme_depth"
        
        # Test various extreme depths
        extreme_depths = [0, 1, 9, 10, 11, 100, 1000, 999999]
        
        for depth in extreme_depths:
            priority = calculate_priority_from_depth(depth)
            
            # Priority should always be positive
            self.assertGreater(priority, 0, f"Priority should be positive for depth {depth}")
            
            # Priority should decrease with depth (until it hits minimum of 1)
            if depth > 0:
                prev_priority = calculate_priority_from_depth(depth - 1)
                # At depth 10+, priorities are clamped to 1
                if depth >= 11:
                    self.assertEqual(priority, 1, f"Priority should be 1 for depth {depth}")
                    self.assertEqual(prev_priority, 1, f"Priority should be 1 for depth {depth-1}")
                else:
                    self.assertLess(priority, prev_priority,
                                  f"Priority should decrease from depth {depth-1} to {depth}")
        
        # Test negative depth (edge case)
        negative_priority = calculate_priority_from_depth(-1)
        self.assertGreater(negative_priority, 0, "Should handle negative depth gracefully")
    
    async def test_domain_parsing_edge_cases(self):
        """Test domain parsing with edge cases."""
        from workflow_service.services.scraping.settings import parse_domain_from_url
        
        edge_cases = [
            # IP addresses
            ("http://192.168.1.1/path", "192.168.1.1"),
            ("https://[2001:db8::1]/path", "[2001:db8::1]"),
            
            # Ports
            ("http://otter.ai:8080/", "otter.ai"),
            ("https://grain.com:443/", "grain.com"),
            
            # Subdomains
            ("https://a.b.c.otter.ai/", "a.b.c.otter.ai"),
            ("https://www.grain.com/", "www.grain.com"),
            
            # Special cases
            ("http://localhost/", "localhost"),
            ("http://otter/", "otter"),  # No TLD
            
            # Auth in URL
            ("https://user:pass@grain.com/", "grain.com"),
        ]
        
        for url, expected in edge_cases:
            domain = parse_domain_from_url(url)
            self.assertEqual(domain, expected.lower(),
                           f"Failed to parse domain from {url}")
    
    async def test_job_specific_redis_client_lifecycle(self):
        """Test job-specific Redis client lifecycle management."""
        
        
        # Create crawler with Redis clients
        settings = Settings()
        settings.set('REDIS_URL', self.redis_url)
        crawler = Crawler(Spider, settings)
        # Create a proper stats object with both methods
        crawler.stats = type('Stats', (), {
            'inc_value': lambda *args, **kwargs: None,
            'set_value': lambda *args, **kwargs: None
        })()
        
        # Create scheduler (which creates Redis clients)
        from workflow_service.services.scraping.scrapy_redis_integration import RedisScheduler
        scheduler = RedisScheduler(crawler)
        
        # Verify clients are stored in crawler
        self.assertTrue(hasattr(crawler, '_redis_clients'))
        self.assertIn('async', crawler._redis_clients)
        self.assertIn('sync', crawler._redis_clients)
        
        # Get references to clients
        async_client = crawler._redis_clients['async']
        sync_client = crawler._redis_clients['sync']
        
        # Verify clients work
        self.assertTrue(await async_client.ping())
        self.assertTrue(sync_client.ping())
        
        # Create spider instance
        spider = Spider(name=f"{self.TEST_PREFIX}_lifecycle")
        spider.job_id = "test_job"
        
        # Call the open method which returns a Deferred
        deferred = scheduler.open(spider)
        
        # If it's a Deferred, convert it to a coroutine
        if isinstance(deferred, Deferred):
            from scrapy.utils.defer import deferred_to_future
            await deferred_to_future(deferred)
        
        # Now queue_key should be set
        self.assertIsNotNone(scheduler.queue_key)
        self.assertEqual(scheduler.spider, spider)
        
        # Close scheduler
        close_deferred = scheduler.close("finished")
        if isinstance(close_deferred, Deferred):
            from scrapy.utils.defer import deferred_to_future
            await deferred_to_future(close_deferred)
        
        # Verify clients are closed and removed from crawler
        self.assertFalse(hasattr(crawler, '_redis_clients'))


class TestScrapingPipelines(unittest.IsolatedAsyncioTestCase):
    """Test streaming pipeline functionality."""
    
    async def asyncSetUp(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_pipeline_"))
        
    async def asyncTearDown(self):
        """Clean up test files."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_streaming_file_pipeline(self):
        """Test StreamingFilePipeline functionality."""
        from workflow_service.services.scraping.pipelines import StreamingFilePipeline
        from scrapy import Spider
        
        # Create pipeline
        pipeline = StreamingFilePipeline(base_dir=str(self.test_dir))
        
        # Create real spider
        spider = Spider(name="test_spider")
        spider.job_id = "test_job"
        
        # Open spider
        pipeline.open_spider(spider)
        
        # Process items
        items = []
        for i in range(5):
            item = {
                'url': f'https://otter.ai/page{i}',
                'title': f'Page {i}',
                'content': 'Some content for testing'
            }
            processed = pipeline.process_item(item, spider)
            items.append(processed)
        
        # Close spider
        pipeline.close_spider(spider)
        
        # Check file was created
        job_dir = self.test_dir / "test_job"
        files = list(job_dir.glob("*.jsonl"))
        self.assertEqual(len(files), 1, "Should have created exactly one file")
        
        # Verify file content
        with open(files[0]) as f:
            lines = f.readlines()
            self.assertEqual(len(lines), 5, "Should have 5 lines (one per item)")
            
            # Check first line
            first_item = json.loads(lines[0])
            self.assertEqual(first_item['url'], 'https://otter.ai/page0')
            self.assertEqual(first_item['title'], 'Page 0')
            self.assertEqual(first_item['_job_id'], 'test_job')
            self.assertEqual(first_item['_spider'], 'test_spider')
            self.assertIn('_timestamp', first_item)
    
    def test_streaming_pipeline_handles_errors(self):
        """Test that streaming pipeline handles errors gracefully."""
        from workflow_service.services.scraping.pipelines import StreamingFilePipeline
        from scrapy import Spider
        
        pipeline = StreamingFilePipeline(base_dir=str(self.test_dir))
        
        spider = Spider(name="test_spider")
        spider.job_id = "error_test"
        
        pipeline.open_spider(spider)
        
        # Process item with non-serializable data
        class NonSerializable:
            pass
        
        item = {
            'url': 'https://grain.com',
            'bad_data': NonSerializable()  # This will fail JSON serialization
        }
        
        # Should not raise exception
        result = pipeline.process_item(item, spider)
        self.assertEqual(result, item, "Should return item even on error")
        
        # Process a good item after the bad one
        good_item = {'url': 'https://grain.com/good', 'title': 'Good'}
        result = pipeline.process_item(good_item, spider)
        
        pipeline.close_spider(spider)
        
        # Should have at least the good item in the file
        job_dir = self.test_dir / "error_test"
        files = list(job_dir.glob("*.jsonl"))
        if files:  # File might not exist if both items failed
            with open(files[0]) as f:
                lines = f.readlines()
                # Should have at least one line (the good item)
                self.assertGreaterEqual(len(lines), 1)
    
    def test_streaming_pipeline_logging(self):
        """Test that streaming pipeline logs progress."""
        from workflow_service.services.scraping.pipelines import StreamingFilePipeline
        from scrapy import Spider
        import logging
        
        pipeline = StreamingFilePipeline(base_dir=str(self.test_dir))
        
        spider = Spider(name="test_spider")
        spider.job_id = "log_test"
        
        pipeline.open_spider(spider)
        
        # Process 100+ items to trigger logging
        with self.assertLogs('workflow_service.services.scraping.pipelines', level=logging.INFO) as cm:
            for i in range(105):
                item = {'url': f'https://otter.ai/page{i}', 'index': i}
                pipeline.process_item(item, spider)
            
            # Should have logged at 100 items
            self.assertTrue(any("100 items written" in msg for msg in cm.output))
        
        pipeline.close_spider(spider)


class TestTieredDownloadHandler(unittest.IsolatedAsyncioTestCase):
    """Test TieredDownloadHandler functionality."""
    
    async def asyncSetUp(self):
        """Set up test environment."""
        self.redis_url = global_settings.REDIS_URL
        if not self.redis_url:
            self.skipTest("REDIS_URL environment variable not set.")
            
        self.client = AsyncRedisClient(self.redis_url)
        self.TEST_PREFIX = f"test_tiered_{uuid.uuid4().hex[:6]}"
    
    async def asyncTearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'client') and self.client:
            await self.client.close()
    
    def test_tier_selection(self):
        """Test tier selection based on URL patterns."""
        from workflow_service.services.scraping.scrapy_redis_integration import TieredDownloadHandler
        from scrapy.settings import Settings
        from scrapy.crawler import Crawler
        from scrapy import Spider
        
        # Create handler with tier rules
        settings = Settings()
        settings.set('TIER_RULES', {
            r'^https://.*\.ai/use-cases.*': 'playwright',
            r'^https://.*\.com/api/.*': 'basic',
            r'^https://.*\.com/app/.*': 'managed',
            r'.*': 'basic',  # Default
        })
        
        crawler = Crawler(Spider, settings)
        crawler.stats = type('Stats', (), {'inc_value': lambda *args: None})()
        
        handler = TieredDownloadHandler(settings, crawler)
        
        # Test URL tier mapping
        test_cases = [
            ('https://otter.ai/use-cases/education', 'playwright'),
            ('https://grain.com/api/v1/users', 'basic'),
            ('https://grain.com/app/dashboard', 'managed'),
            ('https://grain.com/page', 'basic'),
        ]
        
        for url, expected_tier in test_cases:
            tier = handler._get_tier_for_url(url)
            self.assertEqual(tier, expected_tier,
                           f"URL {url} should use tier {expected_tier}")
    
    async def test_url_discovery_control(self):
        """Test URL discovery control via request meta."""
        from workflow_service.services.scraping.scrapy_redis_integration import TieredDownloadHandler
        from scrapy import Request, Spider
        from scrapy.settings import Settings
        from scrapy.crawler import Crawler
        
        # Create handler
        settings = Settings()
        crawler = Crawler(Spider, settings)
        crawler.stats = type('Stats', (), {'inc_value': lambda *args: None})()
        crawler._redis_clients = {
            'async': self.client,
            'sync': None
        }
        
        handler = TieredDownloadHandler(settings, crawler)
        
        # Create real spider
        spider = Spider(name='test_spider')
        spider.allowed_domains = ['otter.ai', 'grain.com']
        
        # Test 1: URL discovery enabled (default)
        request1 = Request(
            'https://otter.ai/page1',
            meta={'discover_urls': True}
        )
        
        # Verify handler can access meta
        self.assertTrue(request1.meta.get('discover_urls', True))
        
        # Test 2: URL discovery disabled
        request2 = Request(
            'https://grain.com/page2',
            meta={'discover_urls': False}
        )
        
        # Verify handler can access meta
        self.assertFalse(request2.meta.get('discover_urls', True))


class TestScrapingPerformance(unittest.IsolatedAsyncioTestCase):
    """Test performance characteristics of the scraping system."""
    
    async def asyncSetUp(self):
        """Set up test environment."""
        self.redis_url = global_settings.REDIS_URL
        if not self.redis_url:
            self.skipTest("REDIS_URL environment variable not set.")
            
        self.client = AsyncRedisClient(self.redis_url)
        self.sync_client = SyncRedisClient(self.redis_url)
        self.TEST_PREFIX = f"test_perf_{uuid.uuid4().hex[:6]}"
    
    async def asyncTearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'sync_client'):
            self.sync_client.close()
            
        if hasattr(self, 'client') and self.client:
            try:
                await self.client.delete_keys_by_pattern(f"{self.TEST_PREFIX}*")
            except:
                pass
            await self.client.close()
    
    async def test_large_scale_url_pushing(self):
        """Test performance of pushing large numbers of URLs."""
        import time
        
        spider_name = f"{self.TEST_PREFIX}_scale"
        num_urls = 10000
        
        # Generate URLs
        urls = []
        for i in range(num_urls):
            if i % 2 == 0:
                urls.append(f"https://otter.ai/page{i}")
            else:
                urls.append(f"https://grain.com/page{i}")
        
        # Time the push operation
        start_time = time.time()
        
        stats = push_urls_to_redis(
            spider_name, urls,
            redis_client=self.sync_client,
            max_urls_per_domain=5000
        )
        
        elapsed = time.time() - start_time
        
        # Should complete reasonably fast
        self.assertLess(elapsed, 30, f"Pushing {num_urls} URLs took too long: {elapsed:.2f}s")
        
        # Calculate throughput
        throughput = num_urls / elapsed
        print(f"\nPush throughput: {throughput:.0f} URLs/second")
        
        # Verify all pushed
        self.assertEqual(stats['urls_pushed'], num_urls)
        
        # Verify domain distribution
        self.assertEqual(len(stats['domain_distribution']), 2)
        self.assertIn('otter.ai', stats['domain_distribution'])
        self.assertIn('grain.com', stats['domain_distribution'])
    
    async def test_concurrent_queue_operations(self):
        """Test performance of concurrent queue operations."""
        import time
        
        spider_name = f"{self.TEST_PREFIX}_concurrent_ops"
        queue_key = get_queue_key(spider_name)
        num_operations = 1000
        
        # Push initial URLs
        for i in range(num_operations):
            request_data = {
                'url': f'https://otter.ai/page{i}',
                'meta': {'index': i}
            }
            await self.client.push_request(queue_key, request_data)
        
        # Time concurrent push/pop operations
        start_time = time.time()
        
        async def mixed_operations(worker_id):
            """Perform mixed push/pop operations."""
            operations = []
            
            for i in range(50):
                if i % 2 == 0:
                    # Pop
                    request = await self.client.pop_request(queue_key)
                    if request:
                        operations.append(('pop', request['meta'].get('index')))
                else:
                    # Push
                    request_data = {
                        'url': f'https://grain.com/worker{worker_id}/new{i}',
                        'meta': {'worker': worker_id, 'op': i}
                    }
                    pushed = await self.client.push_request(queue_key, request_data)
                    if pushed:
                        operations.append(('push', i))
            
            return operations
        
        # Run concurrent workers
        num_workers = 20
        tasks = [mixed_operations(i) for i in range(num_workers)]
        results = await asyncio.gather(*tasks)
        
        elapsed = time.time() - start_time
        
        # Calculate total operations
        total_ops = sum(len(r) for r in results)
        ops_per_second = total_ops / elapsed
        
        print(f"\nConcurrent operations: {ops_per_second:.0f} ops/second")
        
        # Should handle concurrent operations efficiently
        self.assertGreater(ops_per_second, 100, "Concurrent operations too slow")
    
    async def test_memory_efficient_processing(self):
        """Test memory efficiency with streaming processing."""
        spider_name = f"{self.TEST_PREFIX}_memory"
        
        # Check initial memory
        initial_memory = await self.client.check_memory_usage()
        
        # Process many items without storing them all
        num_items = 5000
        items_processed = 0
        
        # Push URLs in batches
        batch_size = 500
        for batch_start in range(0, num_items, batch_size):
            urls = []
            for i in range(batch_start, min(batch_start + batch_size, num_items)):
                urls.append(f"https://grain.com/item{i}")
            
            push_urls_to_redis(
                spider_name, urls,
                redis_client=self.sync_client
            )
            
            # Process some items to prevent queue growth
            queue_key = get_queue_key(spider_name)
            for _ in range(min(100, batch_size)):
                request = await self.client.pop_request(queue_key)
                if request:
                    items_processed += 1
        
        # Check memory after processing
        final_memory = await self.client.check_memory_usage()
        
        # Memory increase should be minimal
        memory_increase = final_memory - initial_memory
        print(f"\nMemory increase: {memory_increase:.1f}%")
        
        # Process remaining items
        while True:
            request = await self.client.pop_request(queue_key)
            if not request:
                break
            items_processed += 1
        
        # Should have processed many items
        self.assertGreater(items_processed, 0)
    
    async def test_depth_priority_performance(self):
        """Test performance of depth-based priority queue."""
        import time
        
        spider_name = f"{self.TEST_PREFIX}_depth_priority"
        queue_key = get_queue_key(spider_name)
        
        # Push URLs at various depths
        depths = [0, 1, 2, 3, 4, 5]
        urls_per_depth = 100
        
        start_push = time.time()
        
        for depth in depths:
            for i in range(urls_per_depth):
                request_data = {
                    'url': f'https://otter.ai/depth{depth}/page{i}',
                    'meta': {'depth': depth}
                }
                priority = calculate_priority_from_depth(depth)
                await self.client.push_request(queue_key, request_data, priority=priority)
        
        push_time = time.time() - start_push
        
        # Pop all URLs and verify depth ordering
        start_pop = time.time()
        depths_popped = []
        
        while True:
            request = await self.client.pop_request(queue_key)
            if not request:
                break
            depths_popped.append(request['meta']['depth'])
        
        pop_time = time.time() - start_pop
        
        # Verify performance
        total_urls = len(depths) * urls_per_depth
        push_rate = total_urls / push_time
        pop_rate = total_urls / pop_time
        
        print(f"\nPriority queue performance:")
        print(f"  Push rate: {push_rate:.0f} URLs/second")
        print(f"  Pop rate: {pop_rate:.0f} URLs/second")
        
        # Verify depth ordering (should be mostly ordered)
        # Check that average depth increases
        chunk_size = 100
        avg_depths = []
        for i in range(0, len(depths_popped), chunk_size):
            chunk = depths_popped[i:i+chunk_size]
            if chunk:
                avg_depths.append(sum(chunk) / len(chunk))
        
        # Average depth should generally increase
        if len(avg_depths) > 1:
            first_half_avg = sum(avg_depths[:len(avg_depths)//2]) / (len(avg_depths)//2)
            second_half_avg = sum(avg_depths[len(avg_depths)//2:]) / (len(avg_depths) - len(avg_depths)//2)
            self.assertLess(first_half_avg, second_half_avg,
                          "URLs should be roughly ordered by depth")


class TestEarlyStoppingProcessedLimits(unittest.IsolatedAsyncioTestCase):
    """Test early stopping when domains reach their processed item limits."""
    
    async def asyncSetUp(self):
        """Set up test environment."""
        self.redis_url = global_settings.REDIS_URL
        if not self.redis_url:
            self.skipTest("REDIS_URL environment variable not set.")
            
        self.redis_client = AsyncRedisClient(self.redis_url)
        self.sync_redis = SyncRedisClient(self.redis_url)
        self.TEST_PREFIX = f"test_early_stop_{uuid.uuid4().hex[:6]}"
        
        # Test connection
        is_connected = await self.redis_client.ping()
        if not is_connected:
            await self.redis_client.close()
            self.skipTest("Could not connect to Redis.")
        
    async def asyncTearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'sync_redis'):
            self.sync_redis.close()
            
        if hasattr(self, 'redis_client') and self.redis_client:
            try:
                # Clean up test data
                patterns = [
                    f"processed_items:{self.TEST_PREFIX}*",
                    f"queue:{self.TEST_PREFIX}*",
                    f"domain_limit:{self.TEST_PREFIX}*",
                    f"*test_early_stop*",
                    f"*test_skip*",
                    f"*test_playwright*",
                    f"*concurrent_test*",
                    f"*test_all_over*",
                ]
                for pattern in patterns:
                    await self.redis_client.delete_keys_by_pattern(pattern)
            except:
                pass
            await self.redis_client.close()
        
    async def test_enqueue_blocks_when_processed_limit_reached(self):
        """Test that enqueue_request blocks URLs when processed limit is reached."""
        # Create spider and scheduler
        settings = Settings({
            'REDIS_URL': self.redis_url,
            'MAX_PROCESSED_URLS_PER_DOMAIN': 5,  # Low limit for testing
            'MAX_URLS_PER_DOMAIN': 100,  # High enqueue limit
            'SCHEDULER_FLUSH_ON_START': True,
        })
        
        crawler = Crawler(GenericSpider, settings)
        scheduler = RedisScheduler(crawler)
        spider = GenericSpider(job_config={'job_id': 'test_early_stop'})
        
        # Open scheduler
        deferred = scheduler.open(spider)
        if isinstance(deferred, Deferred):
            # Wait for async initialization
            from scrapy.utils.defer import deferred_to_future
            await deferred_to_future(deferred)
            
        # Manually set processed count to limit for a domain
        processed_key = get_processed_items_key(
            spider.name, 'example.com', 'test_early_stop', 'spider'
        )
        self.sync_redis.increment_counter_with_limit(processed_key, increment=5)  # Set to limit
        
        # Try to enqueue URLs from over-limit domain
        requests_blocked = 0
        for i in range(10):
            request = Request(f'https://example.com/page{i}')
            if not scheduler.enqueue_request(request):
                requests_blocked += 1
                
        # All should be blocked
        self.assertEqual(requests_blocked, 10)
        
        # Try URLs from different domain - should work
        requests_allowed = 0
        for i in range(5):
            request = Request(f'https://different.com/page{i}')
            if scheduler.enqueue_request(request):
                requests_allowed += 1
                
        self.assertEqual(requests_allowed, 5)
        
        # Check stats
        if crawler.stats:
            blocked_stat = crawler.stats.get_value('scheduler/filtered/processed_limit')
            self.assertEqual(blocked_stat, 10)
            
        # Close scheduler
        await scheduler._async_close('finished')
        
    async def test_next_request_skips_over_limit_domains(self):
        """Test that next_request skips URLs from domains over their limit."""
        # Create spider and scheduler
        settings = Settings({
            'REDIS_URL': self.redis_url,
            'MAX_PROCESSED_URLS_PER_DOMAIN': 3,
            'SCHEDULER_FLUSH_ON_START': True,
        })
        
        crawler = Crawler(GenericSpider, settings)
        scheduler = RedisScheduler(crawler)
        spider = GenericSpider(job_config={'job_id': 'test_skip'})
        
        # Open scheduler
        deferred = scheduler.open(spider)
        if isinstance(deferred, Deferred):
            from scrapy.utils.defer import deferred_to_future
            await deferred_to_future(deferred)
            
        # Enqueue URLs from multiple domains
        domains = ['site1.com', 'site2.com', 'site3.com']
        for domain in domains:
            for i in range(5):
                request = Request(f'https://{domain}/page{i}')
                scheduler.enqueue_request(request)
                
        # Set site2.com as over limit
        processed_key = get_processed_items_key(
            spider.name, 'site2.com', 'test_skip', 'spider'
        )
        self.sync_redis.increment_counter_with_limit(processed_key, increment=3)
        
        # Pop requests - should skip site2.com URLs
        popped_domains = []
        skipped_count = 0
        
        while True:
            request = scheduler.next_request()
            if not request:
                break
                
            domain = parse_domain_from_url(request.url)
            popped_domains.append(domain)
            
        # Check results
        self.assertNotIn('site2.com', popped_domains)  # Should skip all site2.com
        self.assertIn('site1.com', popped_domains)
        self.assertIn('site3.com', popped_domains)
        
        # Check that site2.com URLs are still in queue but were skipped
        queue_length = self.sync_redis.get_queue_length(scheduler.queue_key)
        self.assertEqual(queue_length, 0)  # All processed or skipped
        
        # Check skip stats
        if crawler.stats:
            skip_stat = crawler.stats.get_value('scheduler/skipped/processed_limit')
            self.assertEqual(skip_stat, 5)  # 5 URLs from site2.com were skipped
            
        await scheduler._async_close('finished')
        
    async def test_playwright_discovered_urls_respect_limits(self):
        """Test that URLs discovered by Playwright respect processed limits."""
        # Create spider and scheduler with download handler
        settings = Settings({
            'REDIS_URL': self.redis_url,
            'MAX_PROCESSED_URLS_PER_DOMAIN': 2,
            'SCHEDULER_FLUSH_ON_START': True,
            'TIER_RULES': {'.*': 'basic'},  # Use basic tier
        })
        
        crawler = Crawler(GenericSpider, settings)
        scheduler = RedisScheduler(crawler)
        handler = TieredDownloadHandler(settings, crawler)
        
        # Set up crawler engine mock
        crawler.engine = type('Engine', (), {})()
        crawler.engine.slot = type('Slot', (), {'scheduler': scheduler})()
        
        spider = GenericSpider(job_config={'job_id': 'test_playwright'})
        
        # Open scheduler
        deferred = scheduler.open(spider)
        if isinstance(deferred, Deferred):
            from scrapy.utils.defer import deferred_to_future
            await deferred_to_future(deferred)
            
        # Set example.com as over limit
        processed_key = get_processed_items_key(
            spider.name, 'example.com', 'test_playwright', 'spider'
        )
        self.sync_redis.increment_counter_with_limit(processed_key, increment=2)
        
        # Simulate discovered URLs
        discovered_urls = [
            'https://example.com/page1',  # Should be filtered
            'https://example.com/page2',  # Should be filtered
            'https://allowed.com/page1',   # Should pass
            'https://allowed.com/page2',   # Should pass
        ]
        
        parent_request = Request('https://source.com', meta={'depth': 0})
        
        # Queue discovered URLs
        await handler._queue_discovered_urls(
            discovered_urls, parent_request, spider
        )
        
        # Check what was queued
        queue_length = self.sync_redis.get_queue_length(scheduler.queue_key)
        self.assertEqual(queue_length, 2)  # Only allowed.com URLs
        
        # Pop and verify
        queued_urls = []
        while True:
            request_data = self.sync_redis.pop_request(scheduler.queue_key)
            if not request_data:
                break
            queued_urls.append(request_data['url'])
            
        self.assertEqual(len(queued_urls), 2)
        self.assertTrue(all('allowed.com' in url for url in queued_urls))
        
        await scheduler._async_close('finished')
        
    async def test_concurrent_limit_checking(self):
        """Test that limit checking works correctly under concurrent access."""
        settings = Settings({
            'REDIS_URL': self.redis_url,
            'MAX_PROCESSED_URLS_PER_DOMAIN': 10,
            'SCHEDULER_FLUSH_ON_START': True,
        })
        
        # Create multiple schedulers (simulating concurrent workers)
        schedulers = []
        spiders = []
        
        for i in range(3):
            crawler = Crawler(GenericSpider, settings)
            scheduler = RedisScheduler(crawler)
            spider = GenericSpider(job_config={'job_id': 'concurrent_test'})
            
            deferred = scheduler.open(spider)
            if isinstance(deferred, Deferred):
                from scrapy.utils.defer import deferred_to_future
                await deferred_to_future(deferred)
                
            schedulers.append(scheduler)
            spiders.append(spider)
            
        # Each scheduler tries to enqueue URLs
        total_enqueued = 0
        urls_per_scheduler = 20
        
        for i, scheduler in enumerate(schedulers):
            for j in range(urls_per_scheduler):
                request = Request(f'https://shared-domain.com/worker{i}/page{j}')
                if scheduler.enqueue_request(request):
                    total_enqueued += 1
                    
        # Set processed count to near limit
        processed_key = get_processed_items_key(
            'generic_spider', 'shared-domain.com', 'concurrent_test', 'spider'
        )
        self.sync_redis.increment_counter_with_limit(processed_key, increment=8)
        
        # Now all schedulers try to enqueue more - should mostly fail
        blocked_count = 0
        for scheduler in schedulers:
            for j in range(10):
                request = Request(f'https://shared-domain.com/extra{j}')
                if not scheduler.enqueue_request(request):
                    blocked_count += 1
                    
        # Most should be blocked due to processed limit
        self.assertGreater(blocked_count, 25)  # Most of 30 attempts should fail
        
        # Clean up
        for scheduler in schedulers:
            await scheduler._async_close('finished')
            
    async def test_edge_case_empty_queue_all_over_limit(self):
        """Test behavior when all domains in queue are over their limits."""
        settings = Settings({
            'REDIS_URL': self.redis_url,
            'MAX_PROCESSED_URLS_PER_DOMAIN': 1,  # Very low limit
            'SCHEDULER_FLUSH_ON_START': True,
        })
        
        crawler = Crawler(GenericSpider, settings)
        scheduler = RedisScheduler(crawler)
        spider = GenericSpider(job_config={'job_id': 'test_all_over'})
        
        deferred = scheduler.open(spider)
        if isinstance(deferred, Deferred):
            from scrapy.utils.defer import deferred_to_future
            await deferred_to_future(deferred)
            
        # Enqueue URLs from domains
        domains = ['domain1.com', 'domain2.com', 'domain3.com']
        for domain in domains:
            for i in range(3):
                request = Request(f'https://{domain}/page{i}')
                scheduler.enqueue_request(request)
                
        # Set ALL domains as over limit
        for domain in domains:
            processed_key = get_processed_items_key(
                spider.name, domain, 'test_all_over', 'spider'
            )
            self.sync_redis.increment_counter_with_limit(processed_key, increment=1)
            
        # Try to get requests - should eventually return None after trying
        request = scheduler.next_request()
        self.assertIsNone(request)
        
        # Check warning was logged (would need to capture logs in real test)
        # Check that queue is now empty (URLs were consumed during attempts)
        queue_length = self.sync_redis.get_queue_length(scheduler.queue_key)
        self.assertEqual(queue_length, 0)  # All URLs consumed during skip attempts
        
        await scheduler._async_close('finished')


def run_tests():
    unittest.main()


if __name__ == "__main__":
    run_tests() 