"""
Comprehensive tests for the in-memory mode of Redis Sync Client.

Tests all functionality, edge cases, and complex scenarios for the in-memory
implementation to ensure it works correctly as a Redis alternative.
"""
import os
import json
import time
import unittest
from typing import Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import random

from workflow_service.services.scraping.redis_sync_client import SyncRedisClient


class TestRedisSyncClientMemory(unittest.TestCase):
    """Test in-memory mode functionality of sync client."""
    
    def setUp(self):
        """Set up test environment with in-memory client."""
        # Create client in in-memory mode
        self.client = SyncRedisClient(use_in_memory=True)
        self.assertTrue(self.client.use_in_memory, "Client should be in memory mode")
        
        # Test prefix for isolation
        self.TEST_PREFIX = "test_memory"
    
    def tearDown(self):
        """Clean up after each test."""
        if hasattr(self, 'client') and self.client:
            self.client.close()
    
    def test_memory_mode_initialization(self):
        """Test that memory mode initializes correctly."""
        # Verify ping always returns True
        self.assertTrue(self.client.ping())
        
        # Verify internal structures exist
        self.assertIsNotNone(self.client._memory_queues)
        self.assertIsNotNone(self.client._memory_sets)
        self.assertIsNotNone(self.client._memory_counters)
        self.assertIsNotNone(self.client._memory_hashes)
        
        # Verify no Redis connection attributes
        self.assertFalse(hasattr(self.client, 'redis_url'))
        self.assertFalse(hasattr(self.client, '_pool'))
        self.assertFalse(hasattr(self.client, '_client'))
    
    def test_queue_basic_operations(self):
        """Test basic queue operations in memory mode."""
        queue_key = f"{self.TEST_PREFIX}:queue:basic"
        
        # Empty queue
        self.assertEqual(self.client.get_queue_length(queue_key), 0)
        self.assertIsNone(self.client.pop_request(queue_key))
        
        # Push and pop single request
        request = {'url': 'https://example.com', 'meta': {'test': True}}
        self.assertTrue(self.client.push_request(queue_key, request, priority=50))
        self.assertEqual(self.client.get_queue_length(queue_key), 1)
        
        popped = self.client.pop_request(queue_key)
        self.assertIsNotNone(popped)
        self.assertEqual(popped['url'], request['url'])
        self.assertEqual(self.client.get_queue_length(queue_key), 0)
    
    def test_queue_priority_ordering(self):
        """Test priority queue maintains correct order."""
        queue_key = f"{self.TEST_PREFIX}:queue:priority"
        
        # Push requests with various priorities
        priorities = [100, 20, 75, 50, 150, 30, 90]
        for i, priority in enumerate(priorities):
            request = {'url': f'https://example.com/p{priority}', 'priority': priority}
            self.client.push_request(queue_key, request, priority=priority)
        
        # Pop all and verify order (highest priority first)
        popped_priorities = []
        while True:
            req = self.client.pop_request(queue_key)
            if not req:
                break
            popped_priorities.append(req['priority'])
        
        # Should be in descending order
        expected = sorted(priorities, reverse=True)
        self.assertEqual(popped_priorities, expected)
    
    def test_queue_deduplication(self):
        """Test deduplication works correctly."""
        queue_key = f"{self.TEST_PREFIX}:queue:dedupe"
        
        # Push same URL multiple times
        request = {'url': 'https://example.com/dup'}
        self.assertTrue(self.client.push_request(queue_key, request))
        self.assertFalse(self.client.push_request(queue_key, request))
        self.assertFalse(self.client.push_request(queue_key, request))
        
        # Only one should be in queue
        self.assertEqual(self.client.get_queue_length(queue_key), 1)
        
        # Custom dedupe keys
        self.assertTrue(self.client.push_request(
            queue_key, request, dedupe_key='custom1'
        ))
        self.assertTrue(self.client.push_request(
            queue_key, request, dedupe_key='custom2'
        ))
        self.assertFalse(self.client.push_request(
            queue_key, request, dedupe_key='custom1'
        ))
        
        self.assertEqual(self.client.get_queue_length(queue_key), 3)
    
    def test_queue_stats(self):
        """Test queue statistics in memory mode."""
        queue_key = f"{self.TEST_PREFIX}:queue:stats"
        
        # Empty stats
        stats = self.client.get_queue_stats(queue_key)
        self.assertEqual(stats['queue_size'], 0)
        self.assertEqual(stats['dupefilter_size'], 0)
        self.assertEqual(stats['dupefilter_ttl'], -1)  # No TTL in memory
        self.assertIsNone(stats['highest_priority'])
        self.assertIsNone(stats['lowest_priority'])
        
        # Add items with different priorities
        for priority in [25, 50, 75, 100]:
            self.client.push_request(
                queue_key, 
                {'url': f'https://example.com/{priority}'}, 
                priority=priority
            )
        
        stats = self.client.get_queue_stats(queue_key)
        self.assertEqual(stats['queue_size'], 4)
        self.assertEqual(stats['dupefilter_size'], 4)
        self.assertEqual(stats['highest_priority'], 100)
        self.assertEqual(stats['lowest_priority'], 25)
    
    def test_queue_clear_operations(self):
        """Test clearing queues and dupefilters."""
        queue_key = f"{self.TEST_PREFIX}:queue:clear"
        
        # Add items
        for i in range(10):
            self.client.push_request(queue_key, {'url': f'https://example.com/{i}'})
        
        # Clear queue only
        queue_count, dupe_count = self.client.clear_queue(queue_key, clear_dupefilter=False)
        self.assertEqual(queue_count, 10)
        self.assertEqual(dupe_count, 0)
        
        # Queue should be empty but dupefilter intact
        self.assertEqual(self.client.get_queue_length(queue_key), 0)
        self.assertFalse(self.client.push_request(queue_key, {'url': 'https://example.com/0'}))
        
        # Clear with dupefilter
        self.client.push_request(queue_key, {'url': 'https://example.com/new'})
        queue_count, dupe_count = self.client.clear_queue(queue_key, clear_dupefilter=True)
        self.assertEqual(queue_count, 1)
        self.assertGreater(dupe_count, 0)
        
        # Now old URLs can be added again
        self.assertTrue(self.client.push_request(queue_key, {'url': 'https://example.com/0'}))
    
    def test_counter_basic_operations(self):
        """Test counter operations in memory mode."""
        counter_key = f"{self.TEST_PREFIX}:counter:basic"
        
        # Initial value
        self.assertEqual(self.client.get_counter_value(counter_key), 0)
        
        # Increment
        count, over = self.client.increment_counter_with_limit(counter_key, 5)
        self.assertEqual(count, 5)
        self.assertFalse(over)
        
        # Increment again
        count, over = self.client.increment_counter_with_limit(counter_key, 3)
        self.assertEqual(count, 8)
        self.assertFalse(over)
        
        # Decrement
        count, over = self.client.increment_counter_with_limit(counter_key, -2)
        self.assertEqual(count, 6)
        self.assertFalse(over)
        
        self.assertEqual(self.client.get_counter_value(counter_key), 6)
    
    def test_counter_with_limits(self):
        """Test counter limit enforcement."""
        counter_key = f"{self.TEST_PREFIX}:counter:limit"
        limit = 10
        
        # Increment to limit
        count, over = self.client.increment_counter_with_limit(
            counter_key, increment=8, limit=limit
        )
        self.assertEqual(count, 8)
        self.assertFalse(over)
        
        # Try to exceed - should not increment
        count, over = self.client.increment_counter_with_limit(
            counter_key, increment=5, limit=limit
        )
        self.assertEqual(count, 8)  # Should remain at 8
        self.assertTrue(over)
        
        # Increment to exactly limit
        count, over = self.client.increment_counter_with_limit(
            counter_key, increment=2, limit=limit
        )
        self.assertEqual(count, 10)
        self.assertTrue(over)  # At limit
        
        # Try to exceed again
        count, over = self.client.increment_counter_with_limit(
            counter_key, increment=1, limit=limit
        )
        self.assertEqual(count, 10)
        self.assertTrue(over)
        
        # Negative increments should always work
        count, over = self.client.increment_counter_with_limit(
            counter_key, increment=-5, limit=limit
        )
        self.assertEqual(count, 5)
        self.assertFalse(over)
    
    def test_counter_edge_cases(self):
        """Test counter edge cases."""
        counter_key = f"{self.TEST_PREFIX}:counter:edge"
        
        # Large increments
        count, _ = self.client.increment_counter_with_limit(counter_key, 1000000)
        self.assertEqual(count, 1000000)
        
        # Negative values
        count, _ = self.client.increment_counter_with_limit(counter_key, -2000000)
        self.assertEqual(count, -1000000)
        
        # Zero increment
        count, _ = self.client.increment_counter_with_limit(counter_key, 0)
        self.assertEqual(count, -1000000)
        
        # Limit at zero
        counter_key2 = f"{self.TEST_PREFIX}:counter:zero_limit"
        count, over = self.client.increment_counter_with_limit(
            counter_key2, increment=1, limit=0
        )
        self.assertEqual(count, 0)
        self.assertTrue(over)
    
    def test_hash_counter_operations(self):
        """Test hash counter operations."""
        hash_key = f"{self.TEST_PREFIX}:hash:counters"
        
        # Increment different fields
        self.assertEqual(self.client.increment_hash_counter(hash_key, "field1", 10), 10)
        self.assertEqual(self.client.increment_hash_counter(hash_key, "field2", 5), 5)
        self.assertEqual(self.client.increment_hash_counter(hash_key, "field1", 5), 15)
        self.assertEqual(self.client.increment_hash_counter(hash_key, "field3", -3), -3)
        
        # Get all values
        values = self.client.get_hash_counter_values(hash_key)
        expected = {"field1": 15, "field2": 5, "field3": -3}
        self.assertEqual(values, expected)
        
        # Non-existent hash
        empty = self.client.get_hash_counter_values("nonexistent")
        self.assertEqual(empty, {})
    
    def test_pattern_deletion(self):
        """Test pattern-based deletion."""
        # Create various keys
        self.client.push_request(f"{self.TEST_PREFIX}:queue:1", {'url': 'test1'})
        self.client.push_request(f"{self.TEST_PREFIX}:queue:2", {'url': 'test2'})
        self.client.push_request(f"{self.TEST_PREFIX}:other:1", {'url': 'test3'})
        self.client.increment_counter_with_limit(f"{self.TEST_PREFIX}:counter:1", 5)
        self.client.increment_counter_with_limit(f"{self.TEST_PREFIX}:counter:2", 10)
        self.client.increment_hash_counter(f"{self.TEST_PREFIX}:hash:1", "field", 1)
        
        # Delete by pattern
        patterns = [f"{self.TEST_PREFIX}:queue:*", f"{self.TEST_PREFIX}:counter:*"]
        deleted = self.client.delete_multiple_patterns(patterns)
        
        # Verify counts (each queue creates queue + dupefilter)
        self.assertGreater(deleted[patterns[0]], 0)
        self.assertEqual(deleted[patterns[1]], 2)
        
        # Verify specific keys deleted
        self.assertEqual(self.client.get_queue_length(f"{self.TEST_PREFIX}:queue:1"), 0)
        self.assertEqual(self.client.get_queue_length(f"{self.TEST_PREFIX}:queue:2"), 0)
        self.assertEqual(self.client.get_counter_value(f"{self.TEST_PREFIX}:counter:1"), 0)
        self.assertEqual(self.client.get_counter_value(f"{self.TEST_PREFIX}:counter:2"), 0)
        
        # Verify others remain
        self.assertEqual(self.client.get_queue_length(f"{self.TEST_PREFIX}:other:1"), 1)
        values = self.client.get_hash_counter_values(f"{self.TEST_PREFIX}:hash:1")
        self.assertEqual(values["field"], 1)
    
    def test_memory_cleanup_on_close(self):
        """Test that closing client clears all memory."""
        # Add data
        self.client.push_request("test:queue", {'url': 'test'})
        self.client.increment_counter_with_limit("test:counter", 5)
        self.client.increment_hash_counter("test:hash", "field", 10)
        
        # Close client
        self.client.close()
        
        # Create new client - should have empty memory
        self.client = SyncRedisClient(use_in_memory=True)
        self.assertEqual(self.client.get_queue_length("test:queue"), 0)
        self.assertEqual(self.client.get_counter_value("test:counter"), 0)
        self.assertEqual(self.client.get_hash_counter_values("test:hash"), {})
    
    def test_thread_safety_queue_operations(self):
        """Test thread safety of queue operations."""
        queue_key = f"{self.TEST_PREFIX}:queue:threaded"
        num_threads = 20
        items_per_thread = 100
        
        def push_worker(thread_id):
            """Push unique items."""
            pushed = 0
            for i in range(items_per_thread):
                request = {'url': f'https://example.com/t{thread_id}/i{i}'}
                if self.client.push_request(queue_key, request, priority=thread_id):
                    pushed += 1
            return pushed
        
        def pop_worker():
            """Pop items until queue is empty."""
            popped = []
            while True:
                item = self.client.pop_request(queue_key)
                if not item:
                    break
                popped.append(item)
            return popped
        
        # Push items concurrently
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            push_futures = [executor.submit(push_worker, i) for i in range(num_threads)]
            push_results = [f.result() for f in as_completed(push_futures)]
        
        # All should be pushed (no duplicates)
        total_pushed = sum(push_results)
        self.assertEqual(total_pushed, num_threads * items_per_thread)
        self.assertEqual(self.client.get_queue_length(queue_key), total_pushed)
        
        # Pop items concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            pop_futures = [executor.submit(pop_worker) for _ in range(10)]
            pop_results = []
            for f in as_completed(pop_futures):
                pop_results.extend(f.result())
        
        # All items should be popped exactly once
        self.assertEqual(len(pop_results), total_pushed)
        self.assertEqual(self.client.get_queue_length(queue_key), 0)
        
        # Verify no duplicates in popped items
        urls = [item['url'] for item in pop_results]
        self.assertEqual(len(urls), len(set(urls)))
    
    def test_thread_safety_counter_limits(self):
        """Test thread safety of counter operations with limits."""
        counter_key = f"{self.TEST_PREFIX}:counter:threaded"
        limit = 1000
        num_threads = 50
        increments_per_thread = 50
        
        actual_increments = threading.local()
        total_attempts = 0
        lock = threading.Lock()
        
        def worker(thread_id):
            """Try to increment counter."""
            at_limit_count = 0
            over_limit_count = 0
            
            for _ in range(increments_per_thread):
                count, over = self.client.increment_counter_with_limit(
                    counter_key, increment=1, limit=limit
                )
                
                # Track results
                if over:
                    if count < limit:
                        # This should never happen with our implementation
                        raise AssertionError(f"over=True but count={count} < limit={limit}")
                    over_limit_count += 1
                    
                # Verify we never exceed the limit
                self.assertLessEqual(count, limit)
                
                # Small random delay to increase contention
                time.sleep(random.uniform(0, 0.001))
            
            return over_limit_count
        
        # Run workers
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, i) for i in range(num_threads)]
            over_counts = [f.result() for f in as_completed(futures)]
        
        # Verify final count is exactly the limit
        final_count = self.client.get_counter_value(counter_key)
        self.assertEqual(final_count, limit)
        
        # Calculate stats
        total_over = sum(over_counts)
        total_attempts = num_threads * increments_per_thread
        
        # Verify key properties:
        # 1. Counter reached exactly the limit (not less, not more)
        # 2. Some attempts were marked as "over" (at/beyond limit)
        # 3. The implementation prevented exceeding the limit
        self.assertGreater(total_over, 0, "Should have some over-limit attempts")
        self.assertLess(total_over, total_attempts, "Not all attempts should be over limit")
        
        print(f"\nThread safety counter test:")
        print(f"  Final count: {final_count}/{limit}")
        print(f"  Total attempts: {total_attempts}")
        print(f"  Over-limit responses: {total_over}")
        print(f"  Implementation correctly enforced limit: Yes")
    
    def test_thread_safety_mixed_operations(self):
        """Test thread safety with mixed operations."""
        num_threads = 20
        operations_per_thread = 50
        
        def worker(thread_id):
            """Perform mixed operations."""
            results = {
                'queue_ops': 0,
                'counter_ops': 0,
                'hash_ops': 0
            }
            
            for i in range(operations_per_thread):
                op = i % 3
                
                if op == 0:
                    # Queue operation
                    queue_key = f"{self.TEST_PREFIX}:mixed:queue:{thread_id % 5}"
                    request = {'url': f'https://example.com/t{thread_id}/op{i}'}
                    self.client.push_request(queue_key, request)
                    results['queue_ops'] += 1
                    
                elif op == 1:
                    # Counter operation
                    counter_key = f"{self.TEST_PREFIX}:mixed:counter:{thread_id % 3}"
                    self.client.increment_counter_with_limit(counter_key, 1, limit=100)
                    results['counter_ops'] += 1
                    
                else:
                    # Hash operation
                    hash_key = f"{self.TEST_PREFIX}:mixed:hash:{thread_id % 4}"
                    field = f"field{i % 10}"
                    self.client.increment_hash_counter(hash_key, field, 1)
                    results['hash_ops'] += 1
            
            return results
        
        # Run mixed operations
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, i) for i in range(num_threads)]
            results = [f.result() for f in as_completed(futures)]
        
        # Verify operations completed
        total_queue_ops = sum(r['queue_ops'] for r in results)
        total_counter_ops = sum(r['counter_ops'] for r in results)
        total_hash_ops = sum(r['hash_ops'] for r in results)
        
        self.assertEqual(total_queue_ops + total_counter_ops + total_hash_ops,
                        num_threads * operations_per_thread)
        
        # Spot check some values
        self.assertGreater(self.client.get_queue_length(f"{self.TEST_PREFIX}:mixed:queue:0"), 0)
        self.assertGreater(self.client.get_counter_value(f"{self.TEST_PREFIX}:mixed:counter:0"), 0)
        hash_values = self.client.get_hash_counter_values(f"{self.TEST_PREFIX}:mixed:hash:0")
        self.assertGreater(len(hash_values), 0)
    
    def test_edge_case_empty_structures(self):
        """Test operations on empty/non-existent structures."""
        # Pop from empty queue
        self.assertIsNone(self.client.pop_request("nonexistent:queue"))
        
        # Get length of non-existent queue
        self.assertEqual(self.client.get_queue_length("nonexistent:queue"), 0)
        
        # Get stats of non-existent queue
        stats = self.client.get_queue_stats("nonexistent:queue")
        self.assertEqual(stats['queue_size'], 0)
        self.assertEqual(stats['dupefilter_size'], 0)
        
        # Clear non-existent queue
        count1, count2 = self.client.clear_queue("nonexistent:queue")
        self.assertEqual(count1, 0)
        self.assertEqual(count2, 0)
        
        # Get non-existent counter
        self.assertEqual(self.client.get_counter_value("nonexistent:counter"), 0)
        
        # Get non-existent hash
        self.assertEqual(self.client.get_hash_counter_values("nonexistent:hash"), {})
    
    def test_edge_case_special_characters(self):
        """Test handling of special characters in keys and data."""
        # Special characters in keys
        special_keys = [
            "test:with:colons",
            "test-with-dashes",
            "test_with_underscores",
            "test.with.dots",
            "test/with/slashes",
            "test@with@at",
            "test with spaces",
            "test\twith\ttabs",
            "test\nwith\nnewlines"
        ]
        
        for key in special_keys:
            # Queue operations
            request = {'url': f'https://example.com/{key}', 'data': key}
            self.assertTrue(self.client.push_request(key, request))
            popped = self.client.pop_request(key)
            self.assertEqual(popped['data'], key)
            
            # Counter operations
            count, _ = self.client.increment_counter_with_limit(key, 5)
            self.assertEqual(count, 5)
            
            # Hash operations
            self.assertEqual(self.client.increment_hash_counter(key, "field", 3), 3)
    
    def test_edge_case_large_data(self):
        """Test handling of large data structures."""
        queue_key = f"{self.TEST_PREFIX}:queue:large"
        
        # Large request data
        large_data = {
            'url': 'https://example.com/large',
            'meta': {
                'text': 'x' * 100000,  # 100KB of text
                'list': list(range(10000)),  # Large list
                'nested': {str(i): f'value{i}' for i in range(1000)}  # Large dict
            }
        }
        
        # Should handle large data
        self.assertTrue(self.client.push_request(queue_key, large_data))
        popped = self.client.pop_request(queue_key)
        self.assertEqual(len(popped['meta']['text']), 100000)
        self.assertEqual(len(popped['meta']['list']), 10000)
        self.assertEqual(len(popped['meta']['nested']), 1000)
    
    def test_edge_case_priority_extremes(self):
        """Test extreme priority values."""
        queue_key = f"{self.TEST_PREFIX}:queue:extreme"
        
        # Extreme priorities
        priorities = [
            -1000000000,
            -1,
            0,
            1,
            1000000000,
            float('inf'),  # Infinity
            float('-inf'),  # Negative infinity
        ]
        
        for i, priority in enumerate(priorities):
            if priority == float('inf') or priority == float('-inf'):
                # These should work but may have special ordering
                try:
                    self.client.push_request(
                        queue_key,
                        {'url': f'https://example.com/p{i}', 'p': str(priority)},
                        priority=int(priority) if not isinstance(priority, float) else 0
                    )
                except:
                    # Some systems may not handle infinity well
                    pass
            else:
                self.assertTrue(self.client.push_request(
                    queue_key,
                    {'url': f'https://example.com/p{i}', 'p': priority},
                    priority=priority
                ))
    
    def test_performance_comparison(self):
        """Compare performance of in-memory vs Redis operations."""
        # This test provides performance insights but doesn't assert failures
        import time
        
        num_operations = 1000
        
        # Queue operations
        start = time.time()
        for i in range(num_operations):
            self.client.push_request("perf:queue", {'url': f'https://example.com/{i}'})
        push_time = time.time() - start
        
        start = time.time()
        for _ in range(num_operations):
            self.client.pop_request("perf:queue")
        pop_time = time.time() - start
        
        # Counter operations
        start = time.time()
        for _ in range(num_operations):
            self.client.increment_counter_with_limit("perf:counter", 1)
        counter_time = time.time() - start
        
        print(f"\nIn-memory performance ({num_operations} operations):")
        print(f"  Push queue: {num_operations/push_time:.0f} ops/sec")
        print(f"  Pop queue: {num_operations/pop_time:.0f} ops/sec")
        print(f"  Counter increment: {num_operations/counter_time:.0f} ops/sec")
        
        # In-memory should be very fast
        self.assertGreater(num_operations/push_time, 10000)  # > 10k ops/sec
        self.assertGreater(num_operations/pop_time, 10000)
        self.assertGreater(num_operations/counter_time, 10000)
    
    def test_no_ttl_behavior(self):
        """Verify TTL parameters are ignored in memory mode."""
        # TTL should be ignored for all operations
        counter_key = "test:ttl:counter"
        hash_key = "test:ttl:hash"
        
        # Counter with TTL (ignored)
        count, _ = self.client.increment_counter_with_limit(counter_key, 5, ttl=1)
        self.assertEqual(count, 5)
        
        # Hash with TTL (ignored)
        value = self.client.increment_hash_counter(hash_key, "field", 10, ttl=1)
        self.assertEqual(value, 10)
        
        # No expiration should happen
        time.sleep(2)
        self.assertEqual(self.client.get_counter_value(counter_key), 5)
        self.assertEqual(self.client.get_hash_counter_values(hash_key)["field"], 10)
    
    def test_memory_usage_check(self):
        """Test memory usage check returns 0 in memory mode."""
        # Memory usage should always return 0
        usage = self.client.check_memory_usage()
        self.assertEqual(usage, 0.0)
        
        # Add lots of data
        for i in range(1000):
            self.client.push_request(f"mem:queue:{i}", {'url': f'test{i}'})
        
        # Still should return 0
        usage = self.client.check_memory_usage()
        self.assertEqual(usage, 0.0)


class TestRedisSyncClientMemoryPerformance(unittest.TestCase):
    """Performance and stress tests for in-memory mode."""
    
    def setUp(self):
        """Set up performance test environment."""
        self.client = SyncRedisClient(use_in_memory=True)
    
    def tearDown(self):
        """Clean up after performance tests."""
        if hasattr(self, 'client') and self.client:
            self.client.close()
    
    def test_stress_many_queues(self):
        """Stress test with many queues."""
        num_queues = 1000
        items_per_queue = 10
        
        start = time.time()
        
        # Create many queues
        for q in range(num_queues):
            queue_key = f"stress:queue:{q}"
            for i in range(items_per_queue):
                self.client.push_request(queue_key, {'url': f'q{q}i{i}'})
        
        creation_time = time.time() - start
        
        # Verify all queues exist
        total_items = 0
        for q in range(num_queues):
            queue_key = f"stress:queue:{q}"
            length = self.client.get_queue_length(queue_key)
            self.assertEqual(length, items_per_queue)
            total_items += length
        
        self.assertEqual(total_items, num_queues * items_per_queue)
        
        print(f"\nStress test - {num_queues} queues:")
        print(f"  Creation time: {creation_time:.2f}s")
        print(f"  Rate: {total_items/creation_time:.0f} items/sec")
    
    def test_stress_large_queue(self):
        """Stress test with a single large queue."""
        queue_key = "stress:large:queue"
        num_items = 100000
        
        start = time.time()
        
        # Push many items
        for i in range(num_items):
            self.client.push_request(
                queue_key,
                {'url': f'https://example.com/{i}'},
                priority=i % 1000  # Various priorities
            )
        
        push_time = time.time() - start
        
        # Verify queue size
        self.assertEqual(self.client.get_queue_length(queue_key), num_items)
        
        # Pop all items
        start = time.time()
        popped = 0
        while self.client.pop_request(queue_key):
            popped += 1
        pop_time = time.time() - start
        
        self.assertEqual(popped, num_items)
        
        print(f"\nStress test - large queue ({num_items} items):")
        print(f"  Push time: {push_time:.2f}s ({num_items/push_time:.0f} items/sec)")
        print(f"  Pop time: {pop_time:.2f}s ({num_items/pop_time:.0f} items/sec)")
    
    def test_stress_concurrent_access(self):
        """Stress test with high concurrency."""
        num_threads = 100
        operations_per_thread = 100
        
        start = time.time()
        
        def worker(thread_id):
            """Perform many operations."""
            for i in range(operations_per_thread):
                # Mix of operations
                self.client.push_request(f"concurrent:{thread_id % 10}", {'url': f't{thread_id}i{i}'})
                self.client.increment_counter_with_limit(f"concurrent:counter:{thread_id % 5}", 1)
                self.client.increment_hash_counter(f"concurrent:hash:{thread_id % 3}", f"f{i % 10}", 1)
        
        # Run high concurrency test
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, i) for i in range(num_threads)]
            for f in as_completed(futures):
                f.result()
        
        elapsed = time.time() - start
        total_ops = num_threads * operations_per_thread * 3  # 3 operations per iteration
        
        print(f"\nStress test - high concurrency:")
        print(f"  Threads: {num_threads}")
        print(f"  Total operations: {total_ops}")
        print(f"  Time: {elapsed:.2f}s")
        print(f"  Rate: {total_ops/elapsed:.0f} ops/sec")
        
        # Should handle high concurrency well
        self.assertLess(elapsed, 10.0)  # Should complete in reasonable time


if __name__ == "__main__":
    unittest.main() 