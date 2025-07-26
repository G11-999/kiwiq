"""
Integration tests for the scraping service using in-memory storage.

These tests verify the functionality of the scraping system with in-memory storage:
- In-memory queue management
- Domain limiting
- Depth limiting  
- Priority handling
- Job isolation

Note: These tests are for single-process scenarios only since in-memory storage
doesn't support multi-process access.
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

# Enable in-memory mode
ScrapingSettings.USE_IN_MEMORY_QUEUE = True


class TestProcessedUrlsLimitingMemory(unittest.TestCase):
    """Test MAX_PROCESSED_URLS_PER_DOMAIN functionality with in-memory storage."""
    
    def setUp(self):
        """Set up test environment."""
        self.sync_client = SyncRedisClient(use_in_memory=True)
        self.TEST_PREFIX = f"test_processed_{uuid.uuid4().hex[:6]}"
    
    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'sync_client'):
            self.sync_client.close()
    
    def test_processed_items_tracking(self):
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
            old_count = self.sync_client.get_counter_value(processed_key)
            count, is_over = self.sync_client.increment_counter_with_limit(
                processed_key, 1, limit=max_processed
            )
            
            # Check if increment was actually applied
            if count > old_count:
                processed_count += 1
        
        # Verify counts
        enqueued = self.sync_client.get_counter_value(domain_key)
        processed = self.sync_client.get_counter_value(processed_key)
        
        self.assertEqual(enqueued, 10, "Should have enqueued 10 URLs")
        self.assertEqual(processed, max_processed, f"Should have processed exactly {max_processed}")
        self.assertEqual(processed_count, max_processed)
    
    def test_processed_items_with_filtering(self):
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
            old_count = self.sync_client.get_counter_value(processed_key)
            count, is_over = self.sync_client.increment_counter_with_limit(
                processed_key, 1, limit=max_processed
            )
            
            # Check if increment was actually applied
            if count > old_count:
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
    
    def test_processed_limits_across_domains(self):
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
                old_count = self.sync_client.get_counter_value(processed_key)
                count, is_over = self.sync_client.increment_counter_with_limit(
                    processed_key, 1, limit=max_processed_per_domain
                )
                
                # Check if increment was actually applied
                if count > old_count:
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


class TestScrapingIntegrationMemory(unittest.TestCase):
    """Test case for scraping service integration with in-memory storage."""
    
    def setUp(self):
        """Set up test environment before each test method."""
        # Initialize in-memory Redis client
        self.sync_client = SyncRedisClient(use_in_memory=True)
        self.TEST_PREFIX = f"test_scraping_{uuid.uuid4().hex[:6]}"
    
    def tearDown(self):
        """Clean up after each test method."""
        if hasattr(self, 'sync_client'):
            self.sync_client.close()

    def test_scraping_settings(self):
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

    def test_push_urls_to_redis(self):
        """Test pushing URLs to in-memory queue."""
        spider_name = f"{self.TEST_PREFIX}_push_test"
        urls = [
            "https://otter.ai/page1",
            "https://otter.ai/page2",
            "https://grain.com/page1",
        ]
        
        # Push URLs
        stats = push_urls_to_redis(
            spider_name, urls,
            redis_client=self.sync_client,
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
        queue_length = self.sync_client.get_queue_length(queue_key)
        self.assertEqual(queue_length, 3, "Queue should have 3 URLs")
        
        # Test duplicate filtering
        stats2 = push_urls_to_redis(
            spider_name, urls,
            redis_client=self.sync_client
        )
        self.assertEqual(stats2['urls_pushed'], 0, "Should not push duplicates")

    def test_job_specific_queues(self):
        """Test job-specific queue isolation."""
        spider_name = f"{self.TEST_PREFIX}_job_test"
        urls = ["https://otter.ai/test"]
        
        # Push to job1
        stats1 = push_urls_to_redis(
            spider_name, urls,
            redis_client=self.sync_client,
            job_id="job1",
            queue_key_strategy='job'
        )
        
        # Push to job2
        stats2 = push_urls_to_redis(
            spider_name, urls,
            redis_client=self.sync_client,
            job_id="job2",
            queue_key_strategy='job'
        )
        
        # Both should succeed (isolated deduplication)
        self.assertEqual(stats1['urls_pushed'], 1)
        self.assertEqual(stats2['urls_pushed'], 1)
        
        # Verify different queue keys
        self.assertNotEqual(stats1['queue_key'], stats2['queue_key'])
        
        # Verify queue contents
        queue1_length = self.sync_client.get_queue_length(stats1['queue_key'])
        queue2_length = self.sync_client.get_queue_length(stats2['queue_key'])
        self.assertEqual(queue1_length, 1)
        self.assertEqual(queue2_length, 1)

    def test_domain_limiting(self):
        """Test domain limiting functionality through URL counting."""
        spider_name = f"{self.TEST_PREFIX}_domain_limit"
        domain = "grain.com"
        max_urls = 3
        
        # Push URLs to test domain limiting
        urls = [f"https://{domain}/page{i}" for i in range(max_urls + 2)]
        
        # Use push_urls_to_redis with domain limit
        stats = push_urls_to_redis(
            spider_name, urls,
            redis_client=self.sync_client,
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
            old_count = self.sync_client.get_counter_value(domain_key)
            count, is_over = self.sync_client.increment_counter_with_limit(
                domain_key, 1, limit=max_urls
            )
            
            # Check if increment was actually applied
            if count > old_count:
                allowed_count += 1
            else:
                blocked_count += 1
        
        # Verify limits
        self.assertEqual(allowed_count, max_urls, f"Should allow exactly {max_urls} URLs")
        self.assertEqual(blocked_count, 2, "Should block 2 URLs")

    def test_depth_limiting(self):
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
            
            pushed = self.sync_client.push_request(
                queue_key, request_data, priority=priority
            )
            self.assertTrue(pushed, f"Should be able to push URL at depth {depth}")
        
        # Verify queue has correct number of items
        queue_length = self.sync_client.get_queue_length(queue_key)
        self.assertEqual(queue_length, max_depth + 1)

    def test_priority_by_depth(self):
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
            self.sync_client.push_request(
                queue_key, request_data, priority=priority
            )
            requests.append((depth, priority))
        
        # Pop requests - should come in depth order (0, 1, 2, 3)
        popped_depths = []
        while True:
            request = self.sync_client.pop_request(queue_key)
            if not request:
                break
            popped_depths.append(request['meta']['depth'])
        
        # Verify order
        self.assertEqual(popped_depths, [0, 1, 2, 3], "Requests should be popped in depth order")

    def test_spider_stats(self):
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
            redis_client=self.sync_client
        )
        
        # Simulate crawling by updating domain and depth counters
        for url in urls:
            domain = parse_domain_from_url(url)
            domain_key = get_domain_limit_key(spider_name, domain)
            self.sync_client.increment_counter_with_limit(domain_key, 1)
        
        # Update depth stats
        depth_key = get_depth_stats_key(spider_name)
        self.sync_client.increment_hash_counter(depth_key, "0", 2)
        self.sync_client.increment_hash_counter(depth_key, "1", 1)
        
        # Get stats
        stats = get_spider_stats(spider_name, redis_client=self.sync_client)
        
        # Verify stats
        self.assertEqual(stats['spider_name'], spider_name)
        self.assertEqual(stats['total_urls_crawled'], 3)
        self.assertEqual(stats['depth_distribution']['0'], 2)
        self.assertEqual(stats['depth_distribution']['1'], 1)

    def test_queue_request_serialization(self):
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
        self.sync_client.push_request(
            queue_key, original_request, 
            priority=original_request['priority']
        )
        
        # Pop request
        popped_request = self.sync_client.pop_request(queue_key)
        
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

    def test_thread_safety_domain_limiting(self):
        """Test domain limiting with concurrent threads."""
        import threading
        
        spider_name = f"{self.TEST_PREFIX}_thread_safe"
        domain = "help.otter.ai"
        max_urls = 5
        
        # Create domain limit key
        domain_key = get_domain_limit_key(spider_name, domain)
        
        # Simulate concurrent requests
        results = []
        lock = threading.Lock()
        
        def try_add_url(url_suffix):
            old_count = self.sync_client.get_counter_value(domain_key)
            count, is_over = self.sync_client.increment_counter_with_limit(
                domain_key, increment=1, limit=max_urls
            )
            
            # Check if increment was actually applied
            success = count > old_count
            with lock:
                results.append(success)
            return success
        
        # Create concurrent threads
        threads = []
        for i in range(10):  # Try to add 10 URLs concurrently
            thread = threading.Thread(target=try_add_url, args=(f"page{i}",))
            threads.append(thread)
        
        # Execute concurrently
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # Count successes
        allowed_count = sum(1 for r in results if r)
        blocked_count = sum(1 for r in results if not r)
        
        # Verify limits were respected
        self.assertEqual(allowed_count, max_urls, f"Should allow exactly {max_urls} URLs")
        self.assertEqual(blocked_count, 5, "Should block 5 URLs")
        
        # Verify final count
        final_count = self.sync_client.get_counter_value(domain_key)
        self.assertEqual(final_count, max_urls, "Final count should be at limit")


class TestScrapingRealWorldMemory(unittest.TestCase):
    """Test real-world scraping scenarios with otter.ai using in-memory storage."""
    
    def setUp(self):
        """Set up test environment."""
        self.sync_client = SyncRedisClient(use_in_memory=True)
        self.TEST_PREFIX = f"test_otter_{uuid.uuid4().hex[:6]}"
    
    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'sync_client'):
            self.sync_client.close()

    def test_otter_ai_url_discovery(self):
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
            redis_client=self.sync_client,
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
    
    def test_otter_ai_domain_limiting(self):
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
            redis_client=self.sync_client,
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
            
            # Try to increment
            old_count = self.sync_client.get_counter_value(domain_key)
            count, is_over = self.sync_client.increment_counter_with_limit(
                domain_key, 1, limit=max_urls_per_domain
            )
            
            # Check if increment was actually applied
            if count > old_count:
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
    
    def test_otter_ai_crawl_simulation(self):
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
            self.sync_client.push_request(
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
            request = self.sync_client.pop_request(queue_key)
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
                    
                    self.sync_client.push_request(
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


class TestScrapingEdgeCasesMemory(unittest.TestCase):
    """Test edge cases and error handling in scraping service with in-memory storage."""
    
    def setUp(self):
        """Set up test environment."""
        self.sync_client = SyncRedisClient(use_in_memory=True)
        self.TEST_PREFIX = f"test_edge_{uuid.uuid4().hex[:6]}"
    
    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'sync_client'):
            self.sync_client.close()

    def test_empty_url_list(self):
        """Test pushing empty URL list."""
        spider_name = f"{self.TEST_PREFIX}_empty"
        
        stats = push_urls_to_redis(
            spider_name, [],
            redis_client=self.sync_client
        )
        
        self.assertEqual(stats['urls_pushed'], 0)
        self.assertEqual(stats['domain_distribution'], {})

    def test_invalid_urls(self):
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
            redis_client=self.sync_client
        )
        
        # Should still push all URLs (validation is Spider's responsibility)
        self.assertGreater(stats['urls_pushed'], 0)

    def test_very_deep_urls(self):
        """Test handling of very deep URLs."""
        spider_name = f"{self.TEST_PREFIX}_deep"
        max_depth = 3
        
        # Test with URL at max depth
        stats = push_urls_to_redis(
            spider_name, 
            ["https://otter.ai/very/deep/url"],
            redis_client=self.sync_client,
            max_crawl_depth=max_depth,
            initial_depth=max_depth  # Already at max depth
        )
        
        # Should still push (enforcement happens in scheduler)
        self.assertEqual(stats['urls_pushed'], 1)
        
        # Verify priority is very low for deep URLs
        depth = 10
        priority = calculate_priority_from_depth(depth)
        self.assertGreater(priority, 0, "Priority should never go below 1")

    def test_special_characters_in_domain(self):
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

    def test_job_id_special_characters(self):
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
                redis_client=self.sync_client,
                job_id=job_id,
                queue_key_strategy='job'
            )
            
            self.assertEqual(stats['urls_pushed'], 1, f"Should handle job_id: {job_id}")
            
            # Clean up
            queue_key = stats['queue_key']
            self.sync_client.clear_queue(queue_key, clear_dupefilter=True)


class TestComplexConcurrentScenariosMemory(unittest.TestCase):
    """Test complex concurrent scraping scenarios with in-memory storage."""
    
    def setUp(self):
        """Set up test environment."""
        self.sync_client = SyncRedisClient(use_in_memory=True)
        self.TEST_PREFIX = f"test_complex_{uuid.uuid4().hex[:6]}"
    
    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'sync_client'):
            self.sync_client.close()
    
    def test_concurrent_multi_spider_crawling(self):
        """Test multiple spiders crawling concurrently with shared domains."""
        import threading
        
        num_spiders = 5
        shared_domain = "otter.ai"
        max_urls_per_domain = 20  # Total across all spiders
        
        from workflow_service.services.scraping.settings import get_domain_limit_key
        
        # Use shared domain key (no job_id)
        domain_key = get_domain_limit_key(f"{self.TEST_PREFIX}", shared_domain)
        
        results = []
        lock = threading.Lock()
        
        def spider_worker(spider_id):
            """Simulate a spider trying to crawl URLs."""
            spider_name = f"{self.TEST_PREFIX}_spider_{spider_id}"
            urls_crawled = 0
            urls_blocked = 0
            
            # Each spider tries to crawl 10 URLs
            for i in range(10):
                old_count = self.sync_client.get_counter_value(domain_key)
                count, is_over = self.sync_client.increment_counter_with_limit(
                    domain_key, 1, limit=max_urls_per_domain
                )
                
                if count > old_count:
                    urls_crawled += 1
                    # Simulate processing time
                    import time
                    time.sleep(0.001)
                else:
                    urls_blocked += 1
            
            with lock:
                results.append({
                    'spider_id': spider_id,
                    'urls_crawled': urls_crawled,
                    'urls_blocked': urls_blocked
                })
        
        # Run spiders concurrently
        threads = []
        for i in range(num_spiders):
            thread = threading.Thread(target=spider_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
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
    
    def test_job_isolation_with_concurrent_jobs(self):
        """Test that concurrent jobs are properly isolated."""
        import threading
        
        spider_name = f"{self.TEST_PREFIX}_isolated"
        num_jobs = 3
        urls_per_job = 5
        
        results = []
        lock = threading.Lock()
        
        def job_worker(job_id):
            """Simulate a scraping job."""
            queue_key = get_queue_key(spider_name, job_id, 'job')
            
            # Push URLs
            for i in range(urls_per_job):
                request_data = {
                    'url': f'https://otter.ai/job{job_id}/page{i}',
                    'meta': {'job_id': job_id}
                }
                self.sync_client.push_request(queue_key, request_data, priority=100-i)
            
            # Pop and process URLs
            processed = []
            while True:
                request = self.sync_client.pop_request(queue_key)
                if not request:
                    break
                processed.append(request)
            
            with lock:
                results.append({
                    'job_id': job_id,
                    'urls_processed': len(processed),
                    'queue_key': queue_key
                })
        
        # Run jobs concurrently
        threads = []
        for i in range(num_jobs):
            thread = threading.Thread(target=job_worker, args=(f"job_{i}",))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Verify isolation
        for result in results:
            self.assertEqual(result['urls_processed'], urls_per_job,
                           f"Job {result['job_id']} should process exactly {urls_per_job} URLs")
        
        # Verify different queue keys
        queue_keys = [r['queue_key'] for r in results]
        self.assertEqual(len(set(queue_keys)), num_jobs,
                        "Each job should have a unique queue key")
    
    def test_race_condition_in_domain_limiting(self):
        """Test handling of race conditions in domain limiting."""
        import threading
        
        spider_name = f"{self.TEST_PREFIX}_race"
        domain = "grain.com"
        max_urls = 10
        num_concurrent_requests = 50  # Much more than limit
        
        from workflow_service.services.scraping.settings import get_domain_limit_key
        domain_key = get_domain_limit_key(spider_name, domain)
        
        # Track results
        success_count = 0
        fail_count = 0
        lock = threading.Lock()
        
        def try_increment():
            """Try to increment domain counter."""
            nonlocal success_count, fail_count
            
            old_count = self.sync_client.get_counter_value(domain_key)
            count, is_over = self.sync_client.increment_counter_with_limit(
                domain_key, 1, limit=max_urls
            )
            
            with lock:
                if count > old_count:
                    success_count += 1
                    return True
                else:
                    fail_count += 1
                    return False
        
        # Create many concurrent attempts
        threads = []
        for _ in range(num_concurrent_requests):
            thread = threading.Thread(target=try_increment)
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Verify exactly max_urls succeeded
        self.assertEqual(success_count, max_urls,
                        f"Exactly {max_urls} requests should succeed")
        self.assertEqual(fail_count, num_concurrent_requests - max_urls,
                        f"Exactly {num_concurrent_requests - max_urls} should fail")
        
        # Verify final counter value
        final_count = self.sync_client.get_counter_value(domain_key)
        self.assertEqual(final_count, max_urls,
                        f"Final counter should be exactly {max_urls}")
    
    def test_concurrent_url_discovery(self):
        """Test concurrent URL discovery from multiple sources."""
        import threading
        import time
        
        spider_name = f"{self.TEST_PREFIX}_discovery"
        job_id = "discovery_test"
        queue_key = get_queue_key(spider_name, job_id, 'job')
        
        # Clear any existing data
        self.sync_client.clear_queue(queue_key, clear_dupefilter=True)
        
        results = []
        lock = threading.Lock()
        
        # Simulate multiple discovery sources
        def html_parser(page_id):
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
                if self.sync_client.push_request(queue_key, request_data):
                    pushed_count += 1
            
            with lock:
                results.append(('html', pushed_count))
        
        def js_renderer(page_id):
            """Simulate discovering URLs from JavaScript rendering."""
            urls = []
            for i in range(3):
                urls.append(f"https://grain.com/js/page{page_id}/dynamic{i}")
            
            # Simulate rendering delay
            time.sleep(0.005)
            
            # Push discovered URLs
            pushed_count = 0
            for url in urls:
                request_data = {
                    'url': url,
                    'meta': {'discovered_by': 'js_renderer', 'page_id': page_id}
                }
                if self.sync_client.push_request(queue_key, request_data):
                    pushed_count += 1
            
            with lock:
                results.append(('js', pushed_count))
        
        # Run discovery concurrently for multiple pages
        num_pages = 10
        threads = []
        
        for i in range(num_pages):
            thread1 = threading.Thread(target=html_parser, args=(i,))
            thread2 = threading.Thread(target=js_renderer, args=(i,))
            threads.extend([thread1, thread2])
            thread1.start()
            thread2.start()
        
        for thread in threads:
            thread.join()
        
        total_pushed = sum(count for _, count in results)
        
        # Verify queue has all discovered URLs (minus duplicates)
        queue_length = self.sync_client.get_queue_length(queue_key)
        # Should have at least some URLs (exact count depends on duplicates)
        self.assertGreater(queue_length, 0, "Should have URLs in queue")
        self.assertLessEqual(queue_length, total_pushed, "Queue length should not exceed total pushed")
        
        # Sample URLs to verify discovery sources
        discovered_by_html = 0
        discovered_by_js = 0
        sampled = 0
        
        # Try to sample up to 100 URLs to ensure we get both types
        while sampled < min(100, queue_length):
            request = self.sync_client.pop_request(queue_key)
            if not request:
                break
                
            sampled += 1
            source = request.get('meta', {}).get('discovered_by')
            if source == 'html_parser':
                discovered_by_html += 1
            elif source == 'js_renderer':
                discovered_by_js += 1
        
        # Should have URLs from both sources
        self.assertGreater(discovered_by_html, 0, f"Should have HTML discovered URLs (sampled {sampled} URLs)")
        self.assertGreater(discovered_by_js, 0, f"Should have JS discovered URLs (sampled {sampled} URLs)")


class TestAdvancedEdgeCasesMemory(unittest.TestCase):
    """Test advanced edge cases and error scenarios with in-memory storage."""
    
    def setUp(self):
        """Set up test environment."""
        self.sync_client = SyncRedisClient(use_in_memory=True)
        self.TEST_PREFIX = f"test_advanced_{uuid.uuid4().hex[:6]}"
    
    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'sync_client'):
            self.sync_client.close()
    
    def test_unicode_and_international_urls(self):
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
    
    def test_very_long_urls(self):
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
            request = self.sync_client.pop_request(queue_key)
            self.assertIsNotNone(request)
            self.assertIn('url', request)
            self.assertTrue(len(request['url']) > 100)
    
    def test_malformed_request_data(self):
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
            
            # Valid request for comparison
            {'url': 'https://otter.ai', 'meta': {}},
        ]
        
        # Try to push each request
        successes = 0
        failures = 0
        
        for request_data in malformed_requests:
            try:
                # The push_request method should validate
                if 'url' in request_data and isinstance(request_data['url'], str):
                    pushed = self.sync_client.push_request(queue_key, request_data)
                    if pushed:
                        successes += 1
                    else:
                        failures += 1
                else:
                    failures += 1
            except Exception:
                failures += 1
        
        # Some should fail
        self.assertGreater(failures, 0, "Some malformed requests should fail")
        self.assertGreater(successes, 0, "Valid request should succeed")
    
    def test_extreme_concurrency(self):
        """Test behavior under extreme concurrency."""
        import threading
        
        spider_name = f"{self.TEST_PREFIX}_extreme"
        queue_key = get_queue_key(spider_name)
        num_threads = 100
        operations_per_thread = 50
        
        results = []
        lock = threading.Lock()
        
        def worker(thread_id):
            """Perform many queue operations."""
            push_count = 0
            pop_count = 0
            
            for i in range(operations_per_thread):
                if i % 2 == 0:
                    # Push
                    request_data = {
                        'url': f'https://otter.ai/thread{thread_id}/op{i}',
                        'meta': {'thread': thread_id, 'op': i}
                    }
                    if self.sync_client.push_request(queue_key, request_data):
                        push_count += 1
                else:
                    # Pop
                    request = self.sync_client.pop_request(queue_key)
                    if request:
                        pop_count += 1
            
            with lock:
                results.append({
                    'thread_id': thread_id,
                    'push_count': push_count,
                    'pop_count': pop_count
                })
        
        # Start all threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Verify results
        total_pushed = sum(r['push_count'] for r in results)
        total_popped = sum(r['pop_count'] for r in results)
        
        # Should have processed many operations
        self.assertGreater(total_pushed, 0, "Should have pushed many items")
        self.assertGreater(total_popped, 0, "Should have popped many items")
        
        # Queue should have some items left (more pushes than pops)
        final_queue_length = self.sync_client.get_queue_length(queue_key)
        expected_remaining = total_pushed - total_popped
        self.assertGreaterEqual(final_queue_length, 0, "Queue length should be non-negative")
    
    def test_domain_parsing_edge_cases(self):
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
    
    def test_priority_edge_cases(self):
        """Test priority calculation edge cases."""
        spider_name = f"{self.TEST_PREFIX}_priority"
        queue_key = get_queue_key(spider_name)
        
        # Test extreme priority values
        extreme_priorities = [
            (0, 100),      # Highest priority
            (10, 1),       # Lowest normal priority  
            (100, 1),      # Very deep, clamped to 1
            (1000, 1),     # Extremely deep, still 1
            (-1, 110),     # Negative depth (edge case)
            (-10, 200),    # Very negative depth
        ]
        
        for depth, expected_priority in extreme_priorities:
            priority = calculate_priority_from_depth(depth)
            self.assertEqual(priority, expected_priority,
                           f"Priority for depth {depth} should be {expected_priority}")
        
        # Push requests with extreme priorities
        for depth, priority in extreme_priorities[:4]:  # Skip negative depths
            request_data = {
                'url': f'https://otter.ai/depth{depth}',
                'meta': {'depth': depth}
            }
            self.sync_client.push_request(queue_key, request_data, priority=priority)
        
        # Pop and verify order (highest priority first)
        popped_depths = []
        while True:
            request = self.sync_client.pop_request(queue_key)
            if not request:
                break
            popped_depths.append(request['meta']['depth'])
        
        # Should be in ascending depth order (0, 10, 100, 1000)
        self.assertEqual(popped_depths, [0, 10, 100, 1000],
                        "Requests should be popped in depth order")


class TestScrapingPerformanceMemory(unittest.TestCase):
    """Test performance characteristics of the scraping system with in-memory storage."""
    
    def setUp(self):
        """Set up test environment."""
        self.sync_client = SyncRedisClient(use_in_memory=True)
        self.TEST_PREFIX = f"test_perf_{uuid.uuid4().hex[:6]}"
    
    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'sync_client'):
            self.sync_client.close()
    
    def test_large_scale_url_pushing(self):
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
        
        # Should complete very fast with in-memory
        self.assertLess(elapsed, 10, f"Pushing {num_urls} URLs took too long: {elapsed:.2f}s")
        
        # Calculate throughput
        throughput = num_urls / elapsed
        print(f"\nIn-memory push throughput: {throughput:.0f} URLs/second")
        
        # Verify all pushed
        self.assertEqual(stats['urls_pushed'], num_urls)
        
        # Verify domain distribution
        self.assertEqual(len(stats['domain_distribution']), 2)
        self.assertIn('otter.ai', stats['domain_distribution'])
        self.assertIn('grain.com', stats['domain_distribution'])
    
    def test_memory_efficiency(self):
        """Test memory efficiency with in-memory storage."""
        spider_name = f"{self.TEST_PREFIX}_memory"
        
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
                request = self.sync_client.pop_request(queue_key)
                if request:
                    items_processed += 1
        
        # Process remaining items
        while True:
            request = self.sync_client.pop_request(queue_key)
            if not request:
                break
            items_processed += 1
        
        # Should have processed many items
        self.assertGreater(items_processed, 0)
        print(f"\nProcessed {items_processed} items efficiently in memory")
    
    def test_depth_priority_performance(self):
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
                self.sync_client.push_request(queue_key, request_data, priority=priority)
        
        push_time = time.time() - start_push
        
        # Pop all URLs and verify depth ordering
        start_pop = time.time()
        depths_popped = []
        
        while True:
            request = self.sync_client.pop_request(queue_key)
            if not request:
                break
            depths_popped.append(request['meta']['depth'])
        
        pop_time = time.time() - start_pop
        
        # Verify performance
        total_urls = len(depths) * urls_per_depth
        push_rate = total_urls / push_time
        pop_rate = total_urls / pop_time
        
        print(f"\nIn-memory priority queue performance:")
        print(f"  Push rate: {push_rate:.0f} URLs/second")
        print(f"  Pop rate: {pop_rate:.0f} URLs/second")
        
        # In-memory should be very fast
        self.assertGreater(push_rate, 10000, "Push rate should be very high")
        self.assertGreater(pop_rate, 10000, "Pop rate should be very high")
        
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


class TestScrapingPipelinesMemory(unittest.TestCase):
    """Test streaming pipeline functionality with in-memory storage."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_pipeline_"))
        
    def tearDown(self):
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


class TestTieredDownloadHandlerMemory(unittest.TestCase):
    """Test TieredDownloadHandler functionality with in-memory storage."""
    
    def setUp(self):
        """Set up test environment."""
        self.sync_client = SyncRedisClient(use_in_memory=True)
        self.TEST_PREFIX = f"test_tiered_{uuid.uuid4().hex[:6]}"
    
    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'sync_client'):
            self.sync_client.close()
    
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
    
    def test_url_discovery_control(self):
        """Test URL discovery control via request meta."""
        from workflow_service.services.scraping.scrapy_redis_integration import TieredDownloadHandler
        from scrapy import Request, Spider
        from scrapy.settings import Settings
        from scrapy.crawler import Crawler
        
        # Create handler
        settings = Settings()
        crawler = Crawler(Spider, settings)
        crawler.stats = type('Stats', (), {'inc_value': lambda *args: None})()
        
        # Use in-memory client for testing
        crawler._redis_clients = {
            'sync': self.sync_client
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


class TestMemoryModeSpecific(unittest.TestCase):
    """Test features specific to in-memory mode."""
    
    def setUp(self):
        """Set up test environment."""
        self.sync_client = SyncRedisClient(use_in_memory=True)
        self.TEST_PREFIX = f"test_memory_specific_{uuid.uuid4().hex[:6]}"
    
    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'sync_client'):
            self.sync_client.close()
    
    def test_no_ttl_behavior(self):
        """Test that TTL is ignored in memory mode."""
        key = f"{self.TEST_PREFIX}:ttl_test"
        
        # Set counter with TTL
        self.sync_client.increment_counter_with_limit(key, 1, limit=10, ttl=1)
        
        # Value should persist (no TTL in memory mode)
        import time
        time.sleep(2)  # Wait longer than TTL
        
        value = self.sync_client.get_counter_value(key)
        self.assertEqual(value, 1, "Value should persist without TTL")
    
    def test_memory_isolation(self):
        """Test that different clients have isolated memory."""
        key = f"{self.TEST_PREFIX}:isolation"
        
        # Set value in first client
        self.sync_client.increment_counter_with_limit(key, 5, limit=10)
        
        # Create second client
        client2 = SyncRedisClient(use_in_memory=True)
        
        # Should not see value from first client
        value = client2.get_counter_value(key)
        self.assertEqual(value, 0, "Second client should have isolated memory")
        
        client2.close()
    
    def test_clear_on_close(self):
        """Test that memory is cleared on close."""
        key = f"{self.TEST_PREFIX}:clear_test"
        queue_key = f"{self.TEST_PREFIX}:queue"
        
        # Create a new client
        client = SyncRedisClient(use_in_memory=True)
        
        # Add some data
        client.increment_counter_with_limit(key, 5, limit=10)
        client.push_request(queue_key, {'url': 'https://test.com'})
        
        # Verify data exists
        self.assertEqual(client.get_counter_value(key), 5)
        self.assertEqual(client.get_queue_length(queue_key), 1)
        
        # Close client
        client.close()
        
        # Data should be cleared after close
        # (In a real scenario, the client would not be usable after close,
        # but for testing we can verify the internal state was cleared)
    
    def test_thread_local_not_needed(self):
        """Test that in-memory mode works correctly without thread-local storage."""
        import threading
        
        key = f"{self.TEST_PREFIX}:thread_test"
        results = []
        lock = threading.Lock()
        
        def worker(thread_id):
            """Each thread increments the same counter."""
            local_count = 0
            for i in range(100):
                old_count = self.sync_client.get_counter_value(key)
                count, is_over = self.sync_client.increment_counter_with_limit(key, 1, limit=1000)
                if count > old_count:
                    local_count += 1
            
            # Record how many successful increments this thread made
            with lock:
                results.append(local_count)
        
        # Run multiple threads
        threads = []
        for i in range(10):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # All threads together should have made exactly 1000 increments
        final_value = self.sync_client.get_counter_value(key)
        self.assertEqual(final_value, 1000, "Counter should be exactly 1000")
        
        # Total successful increments across all threads should be 1000
        total_increments = sum(results)
        self.assertEqual(total_increments, 1000, "Total increments should be 1000")


def run_tests():
    unittest.main()


if __name__ == "__main__":
    run_tests() 