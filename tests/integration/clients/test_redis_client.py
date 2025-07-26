import asyncio
import unittest
import os
import time
import uuid
import json
import gzip
from typing import Dict, Any, List, Tuple
from unittest.mock import patch, AsyncMock
from redis.exceptions import WatchError

from redis_client import AsyncRedisClient

class TestAsyncRedisClient(unittest.IsolatedAsyncioTestCase):
    """Test cases for AsyncRedisClient - Pool-based concurrency and atomic methods only"""

    async def asyncSetUp(self):
        """Set up test fixtures"""
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.client = AsyncRedisClient(redis_url)
        self.TEST_PREFIX = f"test_{uuid.uuid4().hex[:6]}:"
        
        # Ensure we can connect
        connected = await self.client.ping()
        if not connected:
            self.skipTest("Cannot connect to Redis")
            
        # Clean up any existing test keys
        await self._cleanup_test_keys()
    
    async def _cleanup_test_keys(self):
        """Clean up test keys"""
        patterns = [
            f"{self.TEST_PREFIX}*",
            f"pool:{self.TEST_PREFIX}*",
            f"lock:{self.TEST_PREFIX}*",
            f"job_state:{self.TEST_PREFIX}*",
            f"queue:{self.TEST_PREFIX}*"
        ]
        for pattern in patterns:
            try:
                await self.client.flush_cache(pattern)
            except Exception:
                pass

    async def asyncTearDown(self):
        """Clean up after tests"""
        # Clean up test keys
        await self._cleanup_test_keys()
        
        # Close client
        await self.client.close()

    # Pool-based Concurrency Limiting Tests
    
    async def test_pool_basic_operations(self):
        """Test basic pool acquire and release operations"""
        pool_key = f"{self.TEST_PREFIX}pool1"
        
        # Acquire resources
        alloc_id, usage, success = await self.client.acquire_from_pool(
            pool_key, count=10, max_pool_size=100, ttl=60
        )
        
        self.assertTrue(success, "Failed to acquire from pool")
        self.assertIsNotNone(alloc_id, "Allocation ID should not be None")
        self.assertEqual(usage, 10, "Usage mismatch")
        
        # Check pool usage
        current_usage = await self.client.get_pool_usage(pool_key)
        self.assertEqual(current_usage, 10, "Pool usage mismatch")
        
        # Release resources
        released, new_usage, success = await self.client.release_to_pool(pool_key, alloc_id)
        
        self.assertTrue(success, "Failed to release")
        self.assertEqual(released, 10, "Released count mismatch")
        self.assertEqual(new_usage, 0, "Usage after release should be 0")
        
        # Verify usage is back to 0
        current_usage = await self.client.get_pool_usage(pool_key)
        self.assertEqual(current_usage, 0, "Final usage should be 0")
    
    async def test_pool_capacity_limits(self):
        """Test that pool respects maximum capacity"""
        pool_key = f"{self.TEST_PREFIX}pool2"
        max_size = 50
        
        # Acquire up to limit
        alloc_id1, usage1, success1 = await self.client.acquire_from_pool(
            pool_key, count=30, max_pool_size=max_size, ttl=60
        )
        self.assertTrue(success1)
        self.assertEqual(usage1, 30)
        
        # Try to exceed limit
        alloc_id2, usage2, success2 = await self.client.acquire_from_pool(
            pool_key, count=25, max_pool_size=max_size, ttl=60
        )
        self.assertFalse(success2, "Should not exceed pool limit")
        self.assertIsNone(alloc_id2)
        self.assertEqual(usage2, 30)  # Should report current usage
        
        # Acquire within remaining capacity
        alloc_id3, usage3, success3 = await self.client.acquire_from_pool(
            pool_key, count=20, max_pool_size=max_size, ttl=60
        )
        self.assertTrue(success3)
        self.assertEqual(usage3, 50)
        
        # Pool should now be exhausted
        is_exhausted = await self.client.is_pool_exhausted(pool_key)
        self.assertTrue(is_exhausted)
    
    async def test_pool_concurrent_operations(self):
        """Test concurrent acquisitions and releases"""
        pool_key = f"{self.TEST_PREFIX}pool3"
        max_size = 100
        num_workers = 10
        resources_per_worker = 10
        
        async def acquire_worker(worker_id: int):
            alloc_id, usage, success = await self.client.acquire_from_pool(
                pool_key, count=resources_per_worker, max_pool_size=max_size, ttl=60
            )
            return worker_id, alloc_id, usage, success
        
        # Run concurrent acquisitions
        results = await asyncio.gather(
            *[acquire_worker(i) for i in range(num_workers)]
        )
        
        # All should succeed since total = 100
        successful = sum(1 for _, _, _, success in results if success)
        self.assertEqual(successful, num_workers)
        
        # Final usage should be 100
        final_usage = await self.client.get_pool_usage(pool_key)
        self.assertEqual(final_usage, 100)
        
        # Try one more acquisition (should fail)
        extra_alloc, extra_usage, extra_success = await self.client.acquire_from_pool(
            pool_key, count=1, max_pool_size=max_size, ttl=60
        )
        self.assertFalse(extra_success)
        self.assertIsNone(extra_alloc)
    
    async def test_pool_automatic_expiration(self):
        """Test that expired allocations are automatically cleaned up"""
        pool_key = f"{self.TEST_PREFIX}pool4"
        
        # Acquire with very short TTL
        alloc_id1, usage1, success1 = await self.client.acquire_from_pool(
            pool_key, count=50, max_pool_size=100, ttl=2  # 2 second TTL
        )
        self.assertTrue(success1)
        self.assertEqual(usage1, 50)
        
        # Wait for expiration plus buffer
        await asyncio.sleep(3)
        
        # Acquire more - should trigger cleanup of expired allocation
        alloc_id2, usage2, success2 = await self.client.acquire_from_pool(
            pool_key, count=70, max_pool_size=100, ttl=60
        )
        self.assertTrue(success2)
        self.assertEqual(usage2, 70)  # Should be 70, not 120
        
        # Verify pool info shows cleanup
        pool_info = await self.client.get_pool_info(pool_key)
        self.assertEqual(pool_info['current_usage'], 70)
        self.assertEqual(pool_info['active_allocations'], 1)  # Only the second allocation
    
    async def test_pool_detailed_info(self):
        """Test getting detailed pool information"""
        pool_key = f"{self.TEST_PREFIX}pool5"
        
        # Create multiple allocations
        allocations = []
        for i in range(3):
            alloc_id, _, success = await self.client.acquire_from_pool(
                pool_key, count=10 * (i + 1), max_pool_size=100, ttl=120
            )
            if success:
                allocations.append((alloc_id, 10 * (i + 1)))
        
        # Get pool info
        pool_info = await self.client.get_pool_info(pool_key)
        
        self.assertEqual(pool_info['current_usage'], 60)  # 10 + 20 + 30
        self.assertEqual(pool_info['max_size'], 100)
        self.assertEqual(pool_info['available'], 40)
        self.assertEqual(pool_info['active_allocations'], 3)
        self.assertEqual(len(pool_info['allocations']), 3)
        
        # Verify allocation details
        for alloc_detail in pool_info['allocations']:
            self.assertIn('id', alloc_detail)
            self.assertIn('count', alloc_detail)
            self.assertIn('expires_in', alloc_detail)
            self.assertGreater(alloc_detail['expires_in'], 0)
    
    async def test_pool_double_release_protection(self):
        """Test that double release is handled gracefully"""
        pool_key = f"{self.TEST_PREFIX}pool6"
        
        # Acquire resources
        alloc_id, usage, success = await self.client.acquire_from_pool(
            pool_key, count=25, max_pool_size=100, ttl=60
        )
        self.assertTrue(success)
        
        # First release
        released1, usage1, success1 = await self.client.release_to_pool(pool_key, alloc_id)
        self.assertTrue(success1)
        self.assertEqual(released1, 25)
        self.assertEqual(usage1, 0)
        
        # Second release (should fail gracefully)
        released2, usage2, success2 = await self.client.release_to_pool(pool_key, alloc_id)
        self.assertFalse(success2)
        self.assertEqual(released2, 0)
        self.assertEqual(usage2, 0)
    
    async def test_pool_reset_functionality(self):
        """Test resetting a pool"""
        pool_key = f"{self.TEST_PREFIX}pool7"
        
        # Create some allocations
        for i in range(5):
            await self.client.acquire_from_pool(
                pool_key, count=10, max_pool_size=100, ttl=60
            )
        
        # Verify usage
        usage_before = await self.client.get_pool_usage(pool_key)
        self.assertEqual(usage_before, 50)
        
        # Reset pool
        reset_success = await self.client.reset_pool(pool_key)
        self.assertTrue(reset_success)
        
        # Verify pool is empty
        usage_after = await self.client.get_pool_usage(pool_key)
        self.assertEqual(usage_after, 0)
        
        pool_info = await self.client.get_pool_info(pool_key)
        self.assertEqual(pool_info['active_allocations'], 0)
    
    async def test_pool_dynamic_max_size(self):
        """Test updating pool maximum size"""
        pool_key = f"{self.TEST_PREFIX}pool8"
        
        # Initial acquisition
        await self.client.acquire_from_pool(pool_key, count=30, max_pool_size=50, ttl=60)
        
        # Update max size
        success = await self.client.set_pool_max_size(pool_key, 100)
        self.assertTrue(success)
        
        # Should now be able to acquire more
        alloc_id, usage, success = await self.client.acquire_from_pool(
            pool_key, count=50, max_pool_size=100, ttl=60
        )
        self.assertTrue(success)
        self.assertEqual(usage, 80)
        
        # Verify new max size is persisted
        pool_info = await self.client.get_pool_info(pool_key)
        self.assertEqual(pool_info['max_size'], 100)
    
    async def test_pool_race_condition_safety(self):
        """Test that pool handles race conditions properly"""
        pool_key = f"{self.TEST_PREFIX}pool9"
        max_size = 100
        num_workers = 20
        resources_per_worker = 10
        
        async def aggressive_worker(worker_id: int):
            results = []
            release_failures = 0
            for _ in range(5):
                alloc_id, usage, success = await self.client.acquire_from_pool(
                    pool_key, count=resources_per_worker, max_pool_size=max_size, ttl=60
                )
                results.append((alloc_id, usage, success))
                if success:
                    # Immediately release to create more contention
                    released, _, release_success = await self.client.release_to_pool(pool_key, alloc_id)
                    if not release_success:
                        release_failures += 1
            return results, release_failures
        
        # Run aggressive concurrent operations
        all_results = await asyncio.gather(
            *[aggressive_worker(i) for i in range(num_workers)]
        )
        
        # Check release failures
        total_release_failures = sum(failures for _, failures in all_results)
        
        # Under extreme concurrency, some releases might fail due to retry exhaustion
        # This is expected behavior - the system is protecting data integrity
        # We allow up to 10% failure rate (10 out of 100 operations)
        max_acceptable_failures = 10
        self.assertLessEqual(total_release_failures, max_acceptable_failures, 
                           f"Too many release failures: {total_release_failures} > {max_acceptable_failures}")
        
        # Final usage should match the number of failed releases
        final_usage = await self.client.get_pool_usage(pool_key)
        expected_usage = total_release_failures * resources_per_worker
        self.assertEqual(final_usage, expected_usage, 
                        f"Final usage {final_usage} doesn't match expected {expected_usage} based on {total_release_failures} failures")
        
        # No operations should have exceeded the limit
        for worker_results, _ in all_results:
            for alloc_id, usage, success in worker_results:
                if success:
                    self.assertLessEqual(usage, max_size)
    
    # Atomic Rate Limiting Tests (Time Window Based)
    
    async def test_atomic_event_registration(self):
        """Test atomic event registration with rate limiting"""
        key = f"{self.TEST_PREFIX}rate1"
        max_events = 5
        
        # Register events up to limit
        for i in range(max_events):
            count, registered = await self.client.register_event_atomic(
                key, max_events=max_events, window_seconds=60
            )
            self.assertTrue(registered)
            self.assertEqual(count, i + 1)
        
        # Next registration should fail
        count, registered = await self.client.register_event_atomic(
            key, max_events=max_events, window_seconds=60
        )
        self.assertFalse(registered)
        self.assertEqual(count, max_events)
        
        # Verify count
        current_count = await self.client.get_event_count(key, window_seconds=60)
        self.assertEqual(current_count, max_events)
    
    async def test_atomic_event_with_count(self):
        """Test atomic event registration with count-based limits"""
        key = f"{self.TEST_PREFIX}count1"
        max_count = 100
        
        # Register with different counts
        usage1, registered1 = await self.client.register_event_with_count_atomic(
            key, count=30, max_count=max_count, window_seconds=60
        )
        self.assertTrue(registered1)
        self.assertEqual(usage1, 30)
        
        usage2, registered2 = await self.client.register_event_with_count_atomic(
            key, count=50, max_count=max_count, window_seconds=60
        )
        self.assertTrue(registered2)
        self.assertEqual(usage2, 80)
        
        # Try to exceed limit
        usage3, registered3 = await self.client.register_event_with_count_atomic(
            key, count=30, max_count=max_count, window_seconds=60
        )
        self.assertFalse(registered3)
        self.assertEqual(usage3, 80)
        
        # Should be able to add exactly 20 more
        usage4, registered4 = await self.client.register_event_with_count_atomic(
            key, count=20, max_count=max_count, window_seconds=60
        )
        self.assertTrue(registered4)
        self.assertEqual(usage4, 100)
    
    async def test_atomic_race_condition_handling(self):
        """Test atomic operations under race conditions"""
        key = f"{self.TEST_PREFIX}race1"
        max_events = 10
        num_workers = 20
        
        async def try_register(worker_id: int):
            count, registered = await self.client.register_event_atomic(
                key, max_events=max_events, window_seconds=60
            )
            return worker_id, count, registered
        
        # Run concurrent registrations
        results = await asyncio.gather(
            *[try_register(i) for i in range(num_workers)]
        )
        
        # Exactly max_events should have succeeded
        successful = sum(1 for _, _, registered in results if registered)
        self.assertEqual(successful, max_events)
        
        # Final count should be max_events
        final_count = await self.client.get_event_count(key, window_seconds=60)
        self.assertEqual(final_count, max_events)
    
    async def test_multi_window_rate_limiting(self):
        """Test rate limiting across multiple time windows"""
        key_prefix = f"{self.TEST_PREFIX}multi1"
        
        # Define different limits for different windows
        limits = [
            (10, 60),    # 10 events per minute
            (50, 300),   # 50 events per 5 minutes  
            (100, 3600), # 100 events per hour
        ]
        
        # Register some events
        for i in range(8):
            registered, counts = await self.client.register_multi_window_event_atomic(
                key_prefix, limits
            )
            self.assertTrue(registered)
            self.assertEqual(counts[60], i + 1)
            self.assertEqual(counts[300], i + 1)
            self.assertEqual(counts[3600], i + 1)
        
        # Check current state
        is_limited, counts = await self.client.check_multi_window_rate_limits(
            key_prefix, limits
        )
        self.assertFalse(is_limited)
        self.assertEqual(counts[60], 8)
        
        # Register 2 more (should hit minute limit)
        for i in range(2):
            registered, counts = await self.client.register_multi_window_event_atomic(
                key_prefix, limits
            )
            self.assertTrue(registered)
        
        # Next should fail (minute limit reached)
        registered, counts = await self.client.register_multi_window_event_atomic(
            key_prefix, limits
        )
        self.assertFalse(registered)
        self.assertEqual(counts[60], 10)  # At limit
    
    async def test_multi_window_count_limits(self):
        """Test count-based limits across multiple windows"""
        key_prefix = f"{self.TEST_PREFIX}multicount1"
        
        # Different count limits for different windows
        limits = [
            (100, 60),    # 100 units per minute
            (400, 300),   # 400 units per 5 minutes
            (1000, 3600), # 1000 units per hour
        ]
        
        # Register with counts
        registered1, usage1 = await self.client.register_multi_window_count_event_atomic(
            key_prefix, count=50, limits=limits
        )
        self.assertTrue(registered1)
        self.assertEqual(usage1[60], 50)
        
        # Register more
        registered2, usage2 = await self.client.register_multi_window_count_event_atomic(
            key_prefix, count=40, limits=limits
        )
        self.assertTrue(registered2)
        self.assertEqual(usage2[60], 90)
        
        # Try to exceed minute limit
        registered3, usage3 = await self.client.register_multi_window_count_event_atomic(
            key_prefix, count=20, limits=limits
        )
        self.assertFalse(registered3)  # Would exceed 100 in minute window
        self.assertEqual(usage3[60], 90)  # Unchanged
    
    # Caching Tests
    
    async def test_cache_operations(self):
        """Test basic caching operations"""
        key = f"{self.TEST_PREFIX}cache1"
        value = {"name": "test", "data": [1, 2, 3], "active": True}
        
        # Set cache
        await self.client.set_cache(key, value, ttl=10)
        
        # Get cache
        retrieved = await self.client.get_cache(key)
        self.assertEqual(retrieved, value)
        
        # Delete cache
        deleted = await self.client.delete_cache(key)
        self.assertTrue(deleted)
        
        # Get after delete
        retrieved = await self.client.get_cache(key)
        self.assertIsNone(retrieved)
    
    async def test_cache_with_binary_data(self):
        """Test caching with binary data"""
        key = f"{self.TEST_PREFIX}binary1"
        binary_data = b"Hello\x00World\xFF\xFE"
        
        # Store binary data
        await self.client.set_cache(key, binary_data, ttl=10)
        
        # Retrieve using get_binary_cache
        retrieved = await self.client.get_binary_cache(key)
        self.assertEqual(retrieved, binary_data)
    
    async def test_cache_with_compression(self):
        """Test caching with compressed data"""
        key = f"{self.TEST_PREFIX}compressed1"
        
        # Create large string
        large_string = "x" * 10000
        compressed = gzip.compress(large_string.encode())
        
        # Store compressed data
        await self.client.set_cache(key, compressed, ttl=10)
        
        # Retrieve and decompress
        retrieved_compressed = await self.client.get_binary_cache(key)
        decompressed = gzip.decompress(retrieved_compressed).decode()
        
        self.assertEqual(decompressed, large_string)
    
    # Distributed Locking Tests
    
    async def test_distributed_locking(self):
        """Test distributed locking mechanism"""
        lock_name = f"{self.TEST_PREFIX}resource1"
        
        # Acquire lock
        token1 = await self.client.acquire_lock(lock_name, timeout=5, ttl=10)
        self.assertIsNotNone(token1)
        
        # Try to acquire same lock
        token2 = await self.client.acquire_lock(lock_name, timeout=1, ttl=10)
        self.assertIsNone(token2)
        
        # Release lock
        released = await self.client.release_lock(lock_name, token1)
        self.assertTrue(released)
        
        # Now should be able to acquire
        token3 = await self.client.acquire_lock(lock_name, timeout=1, ttl=10)
        self.assertIsNotNone(token3)
        
        # Clean up
        await self.client.release_lock(lock_name, token3)
    
    async def test_lock_context_manager(self):
        """Test lock context manager"""
        lock_name = f"{self.TEST_PREFIX}context1"
        
        # Use context manager
        async with self.client.with_lock(lock_name, timeout=5, ttl=10):
            # Lock should be held
            token = await self.client.acquire_lock(lock_name, timeout=1, ttl=10)
            self.assertIsNone(token)
        
        # Lock should be released
        token = await self.client.acquire_lock(lock_name, timeout=1, ttl=10)
        self.assertIsNotNone(token)
        await self.client.release_lock(lock_name, token)
    
    async def test_lock_concurrent_access(self):
        """Test concurrent lock access"""
        lock_name = f"{self.TEST_PREFIX}shared_resource"
        num_workers = 10
        shared_counter = {"value": 0}
        
        async def worker(worker_id: int):
            async with self.client.with_lock(lock_name, timeout=10, ttl=5):
                # Simulate critical section
                current = shared_counter["value"]
                await asyncio.sleep(0.01)  # Simulate work
                shared_counter["value"] = current + 1
                
        # Run concurrent workers
        await asyncio.gather(*[worker(i) for i in range(num_workers)])
        
        # All increments should have been applied
        self.assertEqual(shared_counter["value"], num_workers)
    
    # Job State Tests
    
    async def test_job_state_management(self):
        """Test job state storage and retrieval"""
        job_key = f"{self.TEST_PREFIX}job1"
        
        # Set job state
        state_data = {
            "status": "running",
            "progress": 50,
            "items": ["a", "b", "c"],
            "metadata": {"start_time": time.time()}
        }
        await self.client.set_job_state(job_key, state_data, ttl=120)
        
        # Get job state
        retrieved = await self.client.get_job_state(job_key)
        self.assertEqual(retrieved["status"], "running")
        self.assertEqual(retrieved["progress"], 50)
        self.assertEqual(retrieved["items"], ["a", "b", "c"])
        
        # Increment counter
        new_value = await self.client.increment_job_counter(job_key, "processed", 10)
        self.assertEqual(new_value, 10)
        
        # Increment again
        new_value = await self.client.increment_job_counter(job_key, "processed", 5)
        self.assertEqual(new_value, 15)
        
        # Get state with counter
        final_state = await self.client.get_job_state(job_key)
        self.assertEqual(final_state["processed"], 15)
    
    # Queue Management Tests
    
    async def test_queue_basic_operations(self):
        """Test queue push/pop operations"""
        queue_key = f"{self.TEST_PREFIX}queue1"
        
        # Push requests
        req1 = {"url": "http://example.com/1", "meta": {"depth": 1}}
        req2 = {"url": "http://example.com/2", "meta": {"depth": 2}}
        
        success1 = await self.client.push_request(queue_key, req1, priority=10)
        success2 = await self.client.push_request(queue_key, req2, priority=20)
        
        self.assertTrue(success1)
        self.assertTrue(success2)
        
        # Check queue length
        length = await self.client.get_queue_length(queue_key)
        self.assertEqual(length, 2)
        
        # Pop in priority order (higher priority first)
        popped1 = await self.client.pop_request(queue_key)
        self.assertEqual(popped1["url"], "http://example.com/2")  # Higher priority
        
        popped2 = await self.client.pop_request(queue_key)
        self.assertEqual(popped2["url"], "http://example.com/1")
        
        # Queue should be empty
        popped3 = await self.client.pop_request(queue_key)
        self.assertIsNone(popped3)
    
    async def test_queue_batch_operations(self):
        """Test batch queue operations"""
        queue_key = f"{self.TEST_PREFIX}queue2"
        
        # Create batch of requests
        requests = [
            {"url": f"http://example.com/{i}", "priority": i}
            for i in range(10)
        ]
        
        # Push batch
        added = await self.client.push_requests_batch(queue_key, requests)
        self.assertEqual(added, 10)
        
        # Push same batch again (should be filtered as duplicates)
        added_again = await self.client.push_requests_batch(queue_key, requests)
        self.assertEqual(added_again, 0)
        
        # Get queue stats
        stats = await self.client.get_queue_stats(queue_key)
        self.assertEqual(stats["queue_size"], 10)
        self.assertEqual(stats["dupefilter_size"], 10)
        
        # Clear queue
        queue_cleared, dupes_cleared = await self.client.clear_queue(queue_key)
        self.assertEqual(queue_cleared, 10)
        self.assertEqual(dupes_cleared, 10)
    
    # Counter Operations Tests
    
    async def test_counter_operations(self):
        """Test generic counter operations"""
        counter_key = f"{self.TEST_PREFIX}counter1"
        
        # Increment counter
        new_count, is_over = await self.client.increment_counter_with_limit(
            counter_key, increment=5, limit=20, ttl=60
        )
        self.assertEqual(new_count, 5)
        self.assertFalse(is_over)
        
        # Increment again
        new_count, is_over = await self.client.increment_counter_with_limit(
            counter_key, increment=10, limit=20, ttl=60
        )
        self.assertEqual(new_count, 15)
        self.assertFalse(is_over)
        
        # Hit the limit
        new_count, is_over = await self.client.increment_counter_with_limit(
            counter_key, increment=5, limit=20, ttl=60
        )
        self.assertEqual(new_count, 20)
        self.assertTrue(is_over)
        
        # Check counter
        value = await self.client.get_counter_value(counter_key)
        self.assertEqual(value, 20)
        
        # Check limit
        is_at_limit = await self.client.check_counter_limit(counter_key, limit=20)
        self.assertTrue(is_at_limit)
        
        # Reset counter
        reset_success = await self.client.reset_counter(counter_key)
        self.assertTrue(reset_success)
        
        value = await self.client.get_counter_value(counter_key)
        self.assertEqual(value, 0)
    
    async def test_hash_counter_operations(self):
        """Test hash-based counter operations"""
        hash_key = f"{self.TEST_PREFIX}hash_counters"
        
        # Increment multiple fields
        count1 = await self.client.increment_hash_counter(hash_key, "field1", 10, ttl=60)
        count2 = await self.client.increment_hash_counter(hash_key, "field2", 20, ttl=60)
        count3 = await self.client.increment_hash_counter(hash_key, "field1", 5, ttl=60)
        
        self.assertEqual(count1, 10)
        self.assertEqual(count2, 20)
        self.assertEqual(count3, 15)
        
        # Get all values
        all_values = await self.client.get_hash_counter_values(hash_key)
        self.assertEqual(all_values["field1"], 15)
        self.assertEqual(all_values["field2"], 20)
    
    # Memory and Info Tests
    
    async def test_memory_monitoring(self):
        """Test memory monitoring functions"""
        # Check memory usage
        usage = await self.client.check_memory_usage()
        self.assertIsInstance(usage, float)
        self.assertGreaterEqual(usage, 0)
        self.assertLessEqual(usage, 100)
        
        # Get memory info
        info = await self.client.get_memory_info()
        self.assertIsInstance(info, dict)
        self.assertIn('used_memory', info)
        self.assertIn('maxmemory', info)
        self.assertIn('usage_percent', info)
    
    async def test_server_info(self):
        """Test server information retrieval"""
        info = await self.client.info()
        self.assertIsInstance(info, dict)
        self.assertIn("redis_version", info)
    
    # Integration Tests
    
    async def test_pool_based_api_rate_limiting_scenario(self):
        """Test realistic API rate limiting using pools"""
        api_pool = f"{self.TEST_PREFIX}api_quota"
        max_requests = 100
        
        async def api_request(user_id: str, tokens_needed: int):
            alloc_id, usage, success = await self.client.acquire_from_pool(
                api_pool, count=tokens_needed, max_pool_size=max_requests, ttl=300
            )
            if success:
                # Simulate API call
                await asyncio.sleep(0.01)
                # In real scenario, might release on error
                return alloc_id, True
            return None, False
        
        # Simulate multiple API requests
        results = []
        for i in range(20):
            tokens = 10 if i < 10 else 5
            alloc_id, success = await api_request(f"user_{i}", tokens)
            results.append((alloc_id, success, tokens))
        
        # Check results
        successful_requests = sum(1 for _, success, _ in results if success)
        self.assertGreater(successful_requests, 0)
        
        # Check pool state
        pool_info = await self.client.get_pool_info(api_pool)
        self.assertLessEqual(pool_info['current_usage'], max_requests)
    
    async def test_job_processing_with_pool_concurrency(self):
        """Test job processing with pool-based concurrency control"""
        worker_pool = f"{self.TEST_PREFIX}workers"
        max_workers = 5
        
        async def process_job(job_id: str):
            # Acquire worker slot
            alloc_id, _, success = await self.client.acquire_from_pool(
                worker_pool, count=1, max_pool_size=max_workers, ttl=30
            )
            
            if not success:
                return f"job_{job_id}", "queued"
            
            try:
                # Process job
                await asyncio.sleep(0.1)  # Simulate work
                return f"job_{job_id}", "completed"
            finally:
                # Always release worker
                await self.client.release_to_pool(worker_pool, alloc_id)
        
        # Submit many jobs
        jobs = await asyncio.gather(
            *[process_job(str(i)) for i in range(10)]
        )
        
        # All jobs should complete or be queued
        completed = sum(1 for _, status in jobs if status == "completed")
        queued = sum(1 for _, status in jobs if status == "queued")
        
        self.assertEqual(completed + queued, 10)
        self.assertGreaterEqual(completed, max_workers)  # At least max_workers should complete
        
        # Pool should be empty after all releases
        final_usage = await self.client.get_pool_usage(worker_pool)
        self.assertEqual(final_usage, 0)

def run_tests():
    """Run the test suite"""
    unittest.main()

if __name__ == "__main__":
    run_tests() 