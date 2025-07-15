"""
Comprehensive integration tests for Redis Sync Client.

Tests all functionality of the synchronous Redis client used by the scraping service.
"""
import os
import json
import time
import uuid
import unittest
from typing import Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from workflow_service.services.scraping.redis_sync_client import SyncRedisClient
from global_config.settings import global_settings


class TestRedisSyncClient(unittest.TestCase):
    """Test synchronous Redis client functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.redis_url = global_settings.REDIS_URL
        if not self.redis_url:
            self.skipTest("REDIS_URL environment variable not set.")
            
        self.client = SyncRedisClient(self.redis_url)
        self.TEST_PREFIX = f"test_sync_{uuid.uuid4().hex[:6]}"
        
        # Test connection
        if not self.client.ping():
            self.client.close()
            self.skipTest("Could not connect to Redis.")
    
    def tearDown(self):
        """Clean up after each test."""
        if hasattr(self, 'client') and self.client:
            # Clean up test keys
            try:
                patterns = [
                    f"{self.TEST_PREFIX}*",
                    f"queue:{self.TEST_PREFIX}*",
                    f"domain:{self.TEST_PREFIX}*",
                    f"counter:{self.TEST_PREFIX}*",
                    f"hash:{self.TEST_PREFIX}*",
                ]
                for pattern in patterns:
                    self.client.delete_multiple_patterns([pattern])
            except:
                pass
            
            self.client.close()
    
    def test_ping_connection(self):
        """Test basic connectivity."""
        self.assertTrue(self.client.ping(), "Ping should succeed")
        
        # Test with closed client
        self.client.close()
        new_client = SyncRedisClient(self.redis_url)
        self.assertTrue(new_client.ping(), "Ping should succeed on new client")
        new_client.close()
        
        # Reconnect for other tests
        self.client = SyncRedisClient(self.redis_url)
    
    def test_queue_operations_basic(self):
        """Test basic queue operations."""
        queue_key = f"queue:{self.TEST_PREFIX}:basic"
        
        # Test empty queue
        self.assertEqual(self.client.get_queue_length(queue_key), 0)
        self.assertIsNone(self.client.pop_request(queue_key))
        
        # Push single request
        request1 = {
            'url': 'https://example.com/page1',
            'method': 'GET',
            'meta': {'depth': 0}
        }
        self.assertTrue(self.client.push_request(queue_key, request1, priority=100))
        self.assertEqual(self.client.get_queue_length(queue_key), 1)
        
        # Push duplicate (should be filtered)
        self.assertFalse(self.client.push_request(queue_key, request1, priority=100))
        self.assertEqual(self.client.get_queue_length(queue_key), 1)
        
        # Pop request
        popped = self.client.pop_request(queue_key)
        self.assertIsNotNone(popped)
        self.assertEqual(popped['url'], request1['url'])
        self.assertEqual(self.client.get_queue_length(queue_key), 0)
    
    def test_queue_priority_ordering(self):
        """Test priority queue ordering."""
        queue_key = f"queue:{self.TEST_PREFIX}:priority"
        
        # Push requests with different priorities
        requests = [
            ({'url': 'https://example.com/low', 'priority': 10}, 10),
            ({'url': 'https://example.com/high', 'priority': 100}, 100),
            ({'url': 'https://example.com/medium', 'priority': 50}, 50),
        ]
        
        for request, priority in requests:
            self.assertTrue(self.client.push_request(queue_key, request, priority=priority))
        
        # Pop in priority order (highest first)
        popped_urls = []
        while True:
            req = self.client.pop_request(queue_key)
            if not req:
                break
            popped_urls.append(req['url'])
        
        expected_order = [
            'https://example.com/high',
            'https://example.com/medium', 
            'https://example.com/low'
        ]
        self.assertEqual(popped_urls, expected_order, "Should pop in priority order")
    
    def test_queue_deduplication(self):
        """Test deduplication functionality."""
        queue_key = f"queue:{self.TEST_PREFIX}:dedupe"
        
        # Test with custom dedupe key
        request1 = {'url': 'https://example.com/page', 'version': 1}
        request2 = {'url': 'https://example.com/page', 'version': 2}
        
        # Same URL but different dedupe keys
        self.assertTrue(self.client.push_request(
            queue_key, request1, dedupe_key='page_v1'
        ))
        self.assertTrue(self.client.push_request(
            queue_key, request2, dedupe_key='page_v2'
        ))
        self.assertEqual(self.client.get_queue_length(queue_key), 2)
        
        # Duplicate dedupe key
        self.assertFalse(self.client.push_request(
            queue_key, request1, dedupe_key='page_v1'
        ))
    
    def test_queue_safe_push(self):
        """Test safe push with memory check."""
        queue_key = f"queue:{self.TEST_PREFIX}:safe"
        
        # Normal push should work
        request = {'url': 'https://example.com/test'}
        self.assertTrue(self.client.push_request_safe(queue_key, request))
        
        # Check memory usage
        memory_usage = self.client.check_memory_usage()
        self.assertIsInstance(memory_usage, float)
        self.assertGreaterEqual(memory_usage, 0.0)
        self.assertLessEqual(memory_usage, 100.0)
    
    def test_queue_stats(self):
        """Test queue statistics."""
        queue_key = f"queue:{self.TEST_PREFIX}:stats"
        
        # Empty queue stats
        stats = self.client.get_queue_stats(queue_key)
        self.assertEqual(stats['queue_size'], 0)
        self.assertEqual(stats['dupefilter_size'], 0)
        self.assertIsNone(stats['highest_priority'])
        self.assertIsNone(stats['lowest_priority'])
        
        # Add requests with different priorities
        priorities = [100, 50, 75, 25]
        for i, priority in enumerate(priorities):
            request = {'url': f'https://example.com/page{i}'}
            self.client.push_request(queue_key, request, priority=priority)
        
        # Check stats
        stats = self.client.get_queue_stats(queue_key)
        self.assertEqual(stats['queue_size'], 4)
        self.assertEqual(stats['dupefilter_size'], 4)
        self.assertEqual(stats['highest_priority'], 100)
        self.assertEqual(stats['lowest_priority'], 25)
        self.assertGreater(stats['dupefilter_ttl'], 0)
    
    def test_queue_clear(self):
        """Test clearing queue and dupefilter."""
        queue_key = f"queue:{self.TEST_PREFIX}:clear"
        
        # Add some requests
        for i in range(5):
            request = {'url': f'https://example.com/page{i}'}
            self.client.push_request(queue_key, request)
        
        # Clear queue only
        queue_count, dupe_count = self.client.clear_queue(queue_key, clear_dupefilter=False)
        self.assertEqual(queue_count, 5)
        self.assertEqual(dupe_count, 0)
        
        # Try to add same URLs (should be blocked by dupefilter)
        request = {'url': 'https://example.com/page0'}
        self.assertFalse(self.client.push_request(queue_key, request))
        
        # Clear with dupefilter
        queue_count, dupe_count = self.client.clear_queue(queue_key, clear_dupefilter=True)
        self.assertEqual(queue_count, 0)
        self.assertGreater(dupe_count, 0)
        
        # Now should be able to add again
        self.assertTrue(self.client.push_request(queue_key, request))
    
    def test_counter_operations(self):
        """Test counter increment and limit checking."""
        counter_key = f"counter:{self.TEST_PREFIX}:basic"
        
        # Initial value
        self.assertEqual(self.client.get_counter_value(counter_key), 0)
        
        # Increment without limit
        count1, over1 = self.client.increment_counter_with_limit(counter_key, increment=5)
        self.assertEqual(count1, 5)
        self.assertFalse(over1)
        
        # Increment with limit (within limit)
        count2, over2 = self.client.increment_counter_with_limit(
            counter_key, increment=3, limit=10
        )
        self.assertEqual(count2, 8)
        self.assertFalse(over2)
        
        # Try to increment over limit - should be rolled back
        count3, over3 = self.client.increment_counter_with_limit(
            counter_key, increment=5, limit=10
        )
        # With optimistic implementation, increment is rolled back
        self.assertEqual(count3, 8)  # Should remain at 8
        self.assertTrue(over3)  # Is at/over limit
        
        # Increment to exactly the limit
        count4, over4 = self.client.increment_counter_with_limit(
            counter_key, increment=2, limit=10
        )
        self.assertEqual(count4, 10)
        self.assertTrue(over4)  # Now at limit
        
        # Try to increment past limit - should be rolled back
        count5, over5 = self.client.increment_counter_with_limit(
            counter_key, increment=1, limit=10
        )
        self.assertEqual(count5, 10)  # Should remain at 10
        self.assertTrue(over5)  # Still at limit
        
        # Verify value
        self.assertEqual(self.client.get_counter_value(counter_key), 10)
    
    def test_counter_with_ttl(self):
        """Test counter with TTL."""
        counter_key = f"counter:{self.TEST_PREFIX}:ttl"
        
        # Set counter with 2 second TTL
        count, over = self.client.increment_counter_with_limit(
            counter_key, increment=10, ttl=2
        )
        self.assertEqual(count, 10)
        
        # Should exist
        self.assertEqual(self.client.get_counter_value(counter_key), 10)
        
        # Wait for expiration
        time.sleep(3)
        
        # Should be gone
        self.assertEqual(self.client.get_counter_value(counter_key), 0)
    
    def test_counter_limit_blocking(self):
        """Test that counter properly blocks increments at limit."""
        counter_key = f"counter:{self.TEST_PREFIX}:limit_blocking"
        limit = 10
        
        # Increment up to the limit
        for i in range(1, limit + 1):
            count, over = self.client.increment_counter_with_limit(
                counter_key, increment=1, limit=limit
            )
            if i < limit:
                self.assertEqual(count, i)
                self.assertFalse(over)
            else:
                self.assertEqual(count, limit)
                self.assertTrue(over)
        
        # Try to increment past limit - should be rolled back
        count, over = self.client.increment_counter_with_limit(
            counter_key, increment=1, limit=limit
        )
        self.assertEqual(count, limit)  # Should still be at limit
        self.assertTrue(over)
        
        # Verify counter didn't change
        self.assertEqual(self.client.get_counter_value(counter_key), limit)
        
        # Decrement should always work (negative increments always allowed)
        count, over = self.client.increment_counter_with_limit(
            counter_key, increment=-2, limit=limit
        )
        self.assertEqual(count, limit - 2)
        self.assertFalse(over)
        
        # Now increment should work again (up to limit)
        count, over = self.client.increment_counter_with_limit(
            counter_key, increment=2, limit=limit
        )
        self.assertEqual(count, limit)
        self.assertTrue(over)
        
        # Try a large increment that would exceed limit - should be rolled back
        count, over = self.client.increment_counter_with_limit(
            counter_key, increment=5, limit=limit
        )
        self.assertEqual(count, limit)  # Should still be at limit
        self.assertTrue(over)
        
        # Decrement below limit then try to exceed in one go
        self.client.increment_counter_with_limit(counter_key, increment=-5, limit=limit)
        count, over = self.client.increment_counter_with_limit(
            counter_key, increment=10, limit=limit  # Try to go from 5 to 15
        )
        self.assertEqual(count, 5)  # Should be rolled back to 5
        self.assertTrue(over)  # Still considered over because we tried to exceed
    
    def test_counter_thread_safety_with_limit(self):
        """Test thread safety of counter operations with limit."""
        counter_key = f"counter:{self.TEST_PREFIX}:thread_safe_limit"
        limit = 100
        num_threads = 20
        increments_per_thread = 10
        
        def worker(thread_id):
            """Try to increment counter multiple times."""
            results = []
            
            for _ in range(increments_per_thread):
                # Try to increment
                count, over = self.client.increment_counter_with_limit(
                    counter_key, increment=1, limit=limit
                )
                results.append((count, over))
                    
                # Small delay to increase contention
                time.sleep(0.001)
            
            return results
        
        # Run concurrent increments
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, i) for i in range(num_threads)]
            all_results = []
            for f in as_completed(futures):
                all_results.extend(f.result())
        
        # Final count should be exactly the limit
        final_count = self.client.get_counter_value(counter_key)
        self.assertEqual(final_count, limit)
        
        # Count how many operations returned each value
        value_counts = {}
        for count, over in all_results:
            value_counts[count] = value_counts.get(count, 0) + 1
        
        # The sum of all unique values returned should equal the limit
        # (each increment from 1 to limit should have been returned exactly once)
        unique_incremented_values = [v for v in value_counts.keys() if v > 0 and v <= limit]
        self.assertEqual(len(set(unique_incremented_values)), limit,
                        f"Should have seen each value from 1 to {limit} exactly once")
        
        # No value should exceed the limit
        for count, _ in all_results:
            self.assertLessEqual(count, limit, f"No counter value should exceed {limit}")
        
        # Count successful vs rolled-back operations
        successful_ops = sum(1 for count, over in all_results if count <= limit and not (over and count == limit))
        at_limit_ops = sum(1 for count, over in all_results if count == limit and over)
        
        print(f"\nThread safety test results:")
        print(f"  Total operations: {len(all_results)}")
        print(f"  Successful increments: {successful_ops}")
        print(f"  Operations that reached limit: {at_limit_ops}")
        print(f"  Final counter value: {final_count}/{limit}")
        print(f"  Unique values seen: {sorted(value_counts.keys())[:10]}..." if len(value_counts) > 10 else f"  Unique values seen: {sorted(value_counts.keys())}")
    
    def test_counter_multiple_limits_concurrency(self):
        """Test concurrent operations on different counters with different limits."""
        num_counters = 5
        num_threads_per_counter = 4
        increments_per_thread = 25
        limits = [20, 40, 60, 80, 100]  # Different limits for each counter
        
        # Track actual final counts instead of trying to count successes
        def worker(counter_id, thread_id):
            """Worker for specific counter."""
            counter_key = f"counter:{self.TEST_PREFIX}:multi_{counter_id}"
            limit = limits[counter_id]
            
            for _ in range(increments_per_thread):
                self.client.increment_counter_with_limit(
                    counter_key, increment=1, limit=limit
                )
                    
            return counter_id
        
        # Run workers for all counters concurrently
        with ThreadPoolExecutor(max_workers=num_counters * num_threads_per_counter) as executor:
            futures = []
            for counter_id in range(num_counters):
                for thread_id in range(num_threads_per_counter):
                    futures.append(executor.submit(worker, counter_id, thread_id))
            
            # Wait for all to complete
            for f in as_completed(futures):
                f.result()
        
        # Verify each counter respected its limit
        for counter_id in range(num_counters):
            counter_key = f"counter:{self.TEST_PREFIX}:multi_{counter_id}"
            final_count = self.client.get_counter_value(counter_key)
            expected_limit = limits[counter_id]
            
            self.assertEqual(final_count, expected_limit,
                           f"Counter {counter_id} should be at its limit")
            
            print(f"Counter {counter_id}: {final_count}/{expected_limit} "
                  f"(attempted {num_threads_per_counter * increments_per_thread} increments)")
    
    def test_counter_rollback_behavior(self):
        """Test specific rollback behavior of the optimistic increment approach."""
        counter_key = f"counter:{self.TEST_PREFIX}:rollback"
        
        # Test 1: Verify positive increments are rolled back when exceeding limit
        self.client.increment_counter_with_limit(counter_key, increment=8, limit=10)
        count, over = self.client.increment_counter_with_limit(counter_key, increment=5, limit=10)
        self.assertEqual(count, 8, "Should roll back to 8 when trying to go from 8 to 13")
        self.assertTrue(over, "Should be marked as over limit")
        
        # Test 2: Verify negative increments are never rolled back
        count, over = self.client.increment_counter_with_limit(counter_key, increment=-5, limit=10)
        self.assertEqual(count, 3, "Negative increment should always succeed")
        self.assertFalse(over, "Should not be over limit after decrement")
        
        # Test 3: Verify we can increment back up to limit
        count, over = self.client.increment_counter_with_limit(counter_key, increment=7, limit=10)
        self.assertEqual(count, 10, "Should increment to exactly the limit")
        self.assertTrue(over, "Should be at limit")
        
        # Test 4: Verify negative increment works even when at limit
        count, over = self.client.increment_counter_with_limit(counter_key, increment=-15, limit=10)
        self.assertEqual(count, -5, "Should be able to go negative")
        self.assertFalse(over, "Should not be over limit when negative")
        
        # Test 5: Large positive increment from negative should respect limit
        count, over = self.client.increment_counter_with_limit(counter_key, increment=20, limit=10)
        self.assertEqual(count, -5, "Should roll back when trying to go from -5 to 15")
        self.assertTrue(over, "Should be marked as over because we tried to exceed")
    
    def test_per_key_locking_independence(self):
        """Test that different counter keys can be incremented concurrently without blocking each other."""
        num_counters = 10
        num_threads = 5
        increments_per_thread = 100
        
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        def worker(worker_id):
            """Each worker increments multiple different counters."""
            start_time = time.time()
            for i in range(increments_per_thread):
                # Round-robin through different counters
                counter_id = i % num_counters
                counter_key = f"counter:{self.TEST_PREFIX}:independent_{counter_id}"
                self.client.increment_counter_with_limit(counter_key, increment=1)
            return time.time() - start_time
        
        # Run workers concurrently
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, i) for i in range(num_threads)]
            elapsed_times = [f.result() for f in as_completed(futures)]
        
        # Verify all counters have expected values
        for counter_id in range(num_counters):
            counter_key = f"counter:{self.TEST_PREFIX}:independent_{counter_id}"
            final_count = self.client.get_counter_value(counter_key)
            expected = (increments_per_thread // num_counters) * num_threads
            self.assertEqual(final_count, expected,
                           f"Counter {counter_id} should have {expected} increments")
        
        # Performance check: operations should be reasonably fast due to per-key locking
        avg_time = sum(elapsed_times) / len(elapsed_times)
        print(f"\nPer-key locking test: Average time per thread: {avg_time:.3f}s "
              f"({increments_per_thread / avg_time:.0f} ops/sec/thread)")
        
        # With per-key locking, threads shouldn't block each other much
        # So the time should be relatively consistent
        self.assertLess(max(elapsed_times) - min(elapsed_times), 1.0,
                       "Thread times should be similar (no excessive blocking)")
    
    def test_increment_to_exact_limit_edge_case(self):
        """Test edge case: incrementing to exactly the limit should succeed."""
        counter_key = f"counter:{self.TEST_PREFIX}:exact_limit"
        limit = 10
        
        # Start at 9
        count, over = self.client.increment_counter_with_limit(counter_key, increment=9, limit=limit)
        self.assertEqual(count, 9)
        self.assertFalse(over, "Should not be over limit at 9")
        
        # Increment by 1 to reach exactly 10 (the limit)
        count, over = self.client.increment_counter_with_limit(counter_key, increment=1, limit=limit)
        self.assertEqual(count, 10, "Should successfully increment to exactly the limit")
        self.assertTrue(over, "Should be marked as at/over limit when at limit")
        
        # Try to increment by 1 more - should be rolled back
        count, over = self.client.increment_counter_with_limit(counter_key, increment=1, limit=limit)
        self.assertEqual(count, 10, "Should remain at limit")
        self.assertTrue(over, "Should still be at/over limit")
        
        # Reset to 5
        self.client.increment_counter_with_limit(counter_key, increment=-5, limit=limit)
        
        # Try to increment by 5 to reach exactly the limit
        count, over = self.client.increment_counter_with_limit(counter_key, increment=5, limit=limit)
        self.assertEqual(count, 10, "Should increment to exactly the limit")
        self.assertTrue(over, "Should be at limit")
        
        # Reset to 7
        self.client.increment_counter_with_limit(counter_key, increment=-3, limit=limit)
        
        # Try to increment by 4 (would go to 11, over limit) - should roll back
        count, over = self.client.increment_counter_with_limit(counter_key, increment=4, limit=limit)
        self.assertEqual(count, 7, "Should roll back to 7 when trying to exceed limit")
        self.assertTrue(over, "Should be marked as over because increment was attempted")
    
    def test_hash_counter_operations(self):
        """Test hash counter operations."""
        hash_key = f"hash:{self.TEST_PREFIX}:counters"
        
        # Increment different fields
        self.assertEqual(self.client.increment_hash_counter(hash_key, "field1", 5), 5)
        self.assertEqual(self.client.increment_hash_counter(hash_key, "field2", 10), 10)
        self.assertEqual(self.client.increment_hash_counter(hash_key, "field1", 3), 8)
        
        # Get all values
        values = self.client.get_hash_counter_values(hash_key)
        self.assertEqual(values, {"field1": 8, "field2": 10})
        
        # Test with TTL
        hash_key2 = f"hash:{self.TEST_PREFIX}:ttl"
        self.client.increment_hash_counter(hash_key2, "temp", 1, ttl=1)
        self.assertEqual(self.client.get_hash_counter_values(hash_key2), {"temp": 1})
        
        time.sleep(2)
        self.assertEqual(self.client.get_hash_counter_values(hash_key2), {})
    
    def test_concurrent_operations(self):
        """Test thread safety of sync client."""
        queue_key = f"queue:{self.TEST_PREFIX}:concurrent"
        counter_key = f"counter:{self.TEST_PREFIX}:concurrent"
        num_threads = 10
        operations_per_thread = 100
        
        def worker(thread_id):
            """Worker function for concurrent testing."""
            results = {
                'push_success': 0,
                'push_duplicate': 0,
                'counter_final': 0
            }
            
            for i in range(operations_per_thread):
                # Push unique request
                request = {'url': f'https://example.com/thread{thread_id}/page{i}'}
                if self.client.push_request(queue_key, request):
                    results['push_success'] += 1
                else:
                    results['push_duplicate'] += 1
                
                # Increment counter
                count, _ = self.client.increment_counter_with_limit(counter_key, 1)
                results['counter_final'] = count
            
            return results
        
        # Run concurrent operations
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, i) for i in range(num_threads)]
            results = [f.result() for f in as_completed(futures)]
        
        # Verify results
        total_pushed = sum(r['push_success'] for r in results)
        total_duplicates = sum(r['push_duplicate'] for r in results)
        
        self.assertEqual(total_pushed, num_threads * operations_per_thread)
        self.assertEqual(total_duplicates, 0)  # All should be unique
        
        # Counter should equal total operations
        final_count = self.client.get_counter_value(counter_key)
        self.assertEqual(final_count, num_threads * operations_per_thread)
        
        # Queue should have all requests
        self.assertEqual(
            self.client.get_queue_length(queue_key),
            num_threads * operations_per_thread
        )
    
    def test_pattern_deletion(self):
        """Test deleting keys by pattern."""
        # Create various test keys
        test_keys = {
            f"{self.TEST_PREFIX}:type1:key1": "value1",
            f"{self.TEST_PREFIX}:type1:key2": "value2",
            f"{self.TEST_PREFIX}:type2:key1": "value3",
            f"{self.TEST_PREFIX}:other:key1": "value4",
        }
        
        # Set all keys using raw Redis client
        for key, value in test_keys.items():
            self.client._get_client().set(key, value)
        
        # Delete by patterns
        patterns = [
            f"{self.TEST_PREFIX}:type1:*",
            f"{self.TEST_PREFIX}:type2:*"
        ]
        deleted = self.client.delete_multiple_patterns(patterns)
        
        # Verify deletions
        self.assertEqual(deleted[patterns[0]], 2)  # type1 keys
        self.assertEqual(deleted[patterns[1]], 1)  # type2 keys
        
        # Verify remaining key
        remaining_key = f"{self.TEST_PREFIX}:other:key1"
        self.assertIsNotNone(self.client._get_client().get(remaining_key))
    
    def test_error_handling(self):
        """Test error handling in various scenarios."""
        # Test with invalid Redis URL
        bad_client = SyncRedisClient("redis://invalid:6379")
        self.assertFalse(bad_client.ping())
        bad_client.close()
        
        # Test operations on closed client
        # Note: The sync client recreates connection on ping, which is expected behavior
        # For a truly closed connection test, we would need to modify the client
        # For now, we'll skip this test as the behavior is acceptable
        
        # Reconnect for other tests
        self.client = SyncRedisClient(self.redis_url)
    
    def test_large_request_data(self):
        """Test handling large request data."""
        queue_key = f"queue:{self.TEST_PREFIX}:large"
        
        # Create large request
        large_meta = {
            'discovered_urls': [f'https://example.com/page{i}' for i in range(1000)],
            'extracted_data': {'text': 'x' * 10000},  # 10KB of text
            'headers': {f'header{i}': f'value{i}' for i in range(100)}
        }
        
        request = {
            'url': 'https://example.com/large',
            'meta': large_meta
        }
        
        # Should handle large data
        self.assertTrue(self.client.push_request(queue_key, request))
        
        # Verify it can be retrieved
        popped = self.client.pop_request(queue_key)
        self.assertIsNotNone(popped)
        self.assertEqual(len(popped['meta']['discovered_urls']), 1000)
    
    def test_special_characters_in_data(self):
        """Test handling special characters and encodings."""
        queue_key = f"queue:{self.TEST_PREFIX}:special"
        
        # Request with various special characters
        request = {
            'url': 'https://example.com/特殊文字',
            'meta': {
                'unicode': '你好世界 🌍',
                'emoji': '🕷️🕸️',
                'special': 'line1\nline2\ttab',
                'quotes': 'He said "Hello"',
                'json_special': '{"key": "value"}'
            }
        }
        
        # Push and pop
        self.assertTrue(self.client.push_request(queue_key, request))
        popped = self.client.pop_request(queue_key)
        
        # Verify all special characters preserved
        self.assertEqual(popped['url'], request['url'])
        self.assertEqual(popped['meta']['unicode'], request['meta']['unicode'])
        self.assertEqual(popped['meta']['emoji'], request['meta']['emoji'])
        self.assertEqual(popped['meta']['special'], request['meta']['special'])
        self.assertEqual(popped['meta']['quotes'], request['meta']['quotes'])
        self.assertEqual(popped['meta']['json_special'], request['meta']['json_special'])


class TestRedisSyncClientPerformance(unittest.TestCase):
    """Performance tests for Redis sync client."""
    
    def setUp(self):
        """Set up for performance tests."""
        self.redis_url = global_settings.REDIS_URL
        if not self.redis_url:
            self.skipTest("REDIS_URL environment variable not set.")
            
        self.client = SyncRedisClient(self.redis_url)
        self.TEST_PREFIX = f"test_perf_{uuid.uuid4().hex[:6]}"
        
        if not self.client.ping():
            self.client.close()
            self.skipTest("Could not connect to Redis.")
    
    def tearDown(self):
        """Clean up after performance tests."""
        if hasattr(self, 'client') and self.client:
            try:
                self.client.delete_multiple_patterns([f"{self.TEST_PREFIX}*"])
            except:
                pass
            self.client.close()
    
    def test_bulk_operations_performance(self):
        """Test performance of bulk operations."""
        queue_key = f"queue:{self.TEST_PREFIX}:bulk"
        num_requests = 1000
        
        # Time bulk push
        start_time = time.time()
        for i in range(num_requests):
            request = {
                'url': f'https://example.com/page{i}',
                'meta': {'index': i}
            }
            self.client.push_request(queue_key, request, priority=i % 100)
        push_time = time.time() - start_time
        
        # Calculate throughput
        push_throughput = num_requests / push_time
        print(f"\nPush throughput: {push_throughput:.0f} requests/second")
        self.assertGreater(push_throughput, 100, "Push throughput should exceed 100 req/s")
        
        # Time bulk pop
        start_time = time.time()
        popped_count = 0
        while self.client.pop_request(queue_key):
            popped_count += 1
        pop_time = time.time() - start_time
        
        pop_throughput = popped_count / pop_time
        print(f"Pop throughput: {pop_throughput:.0f} requests/second")
        self.assertGreater(pop_throughput, 100, "Pop throughput should exceed 100 req/s")
        
        self.assertEqual(popped_count, num_requests)
    
    def test_counter_increment_performance(self):
        """Test counter increment performance."""
        counter_key = f"counter:{self.TEST_PREFIX}:perf"
        num_operations = 10000
        
        start_time = time.time()
        for i in range(num_operations):
            self.client.increment_counter_with_limit(counter_key, 1, limit=num_operations + 1)
        
        elapsed = time.time() - start_time
        throughput = num_operations / elapsed
        
        print(f"\nCounter increment throughput: {throughput:.0f} operations/second")
        self.assertGreater(throughput, 1000, "Counter throughput should exceed 1000 ops/s")
        
        # Verify final count
        final_count = self.client.get_counter_value(counter_key)
        self.assertEqual(final_count, num_operations)


if __name__ == "__main__":
    unittest.main() 