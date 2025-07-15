import asyncio
import os
import uuid
import unittest
import logging
from datetime import timedelta
from redis.exceptions import ConnectionError, AuthenticationError, TimeoutError, RedisError

# Import the AsyncRedisClient
from redis_client import AsyncRedisClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TestAsyncRedisClient(unittest.IsolatedAsyncioTestCase):
    """Test case for AsyncRedisClient."""
    
    async def asyncSetUp(self):
        """Set up test environment before each test method."""
        from global_config.settings import global_settings
        self.redis_url = global_settings.REDIS_URL
        if not self.redis_url:
            self.fail("REDIS_URL environment variable not set.")
        
        # Initialize client
        self.client = AsyncRedisClient(self.redis_url)
        self.client_raw = AsyncRedisClient(self.redis_url, decode_responses=False)
        self.TEST_PREFIX = f"test_run_{uuid.uuid4().hex[:6]}:"
        
        # Test connection
        is_connected = await self.client.ping()
        if not is_connected:
            await self.client.close()
            self.fail("Could not connect to Redis. Check connection URL and server status.")
        
        # Test connection
        is_connected = await self.client_raw.ping()
        if not is_connected:
            await self.client_raw.close()
            self.fail("Could not connect to Redis. Check connection URL and server status.")
        
        
        logger.info(f"Test setup complete with prefix: {self.TEST_PREFIX}")
    
    async def asyncTearDown(self):
        """Clean up after each test method."""
        if hasattr(self, 'client') and self.client:
            # Clean up any test keys
            try:
                await self.client.flush_cache(f"{self.TEST_PREFIX}*")
                await self.client_raw.flush_cache(f"{self.TEST_PREFIX}*")
            except:
                pass  # Ignore cleanup errors
            
            await self.client.close()
            await self.client_raw.close()
            logger.info("Redis client closed.")
    
    async def test_caching(self):
        """Test cache operations."""
        # Test set_cache and get_cache
        cache_key = f"{self.TEST_PREFIX}user:101"
        cache_data = {"name": "Dave", "age": 50, "active": False, "dept": "support"}
        
        await self.client.set_cache(cache_key, cache_data, ttl=60)
        retrieved_data = await self.client.get_cache(cache_key)
        
        self.assertEqual(retrieved_data, cache_data, "Cache data mismatch")
        
        # Test delete_cache
        delete_result = await self.client.delete_cache(cache_key)
        self.assertTrue(delete_result, "Delete operation failed")
        
        # Verify deletion
        retrieved_after_delete = await self.client.get_cache(cache_key)
        self.assertIsNone(retrieved_after_delete, "Key was not properly deleted")
    
    async def test_rate_limiting(self):
        """Test rate limiting functionality."""
        rate_key = f"{self.TEST_PREFIX}rate:user:101"
        
        # Register events
        for i in range(5):
            count, limited = await self.client.register_event(rate_key, window_seconds=10)
            self.assertEqual(count, i+1, f"Event count mismatch after {i+1} registrations")
            self.assertFalse(limited, "Should not be rate limited yet")
        
        # Check count
        count = await self.client.get_event_count(rate_key, window_seconds=10)
        self.assertEqual(count, 5, "Total event count mismatch")
        
        # Test rate limiting check
        is_limited = await self.client.is_rate_limited(rate_key, max_events=3, window_seconds=10)
        self.assertTrue(is_limited, "Should be rate limited with max=3")
        
        is_limited = await self.client.is_rate_limited(rate_key, max_events=10, window_seconds=10)
        self.assertFalse(is_limited, "Should not be rate limited with max=10")
    
    async def test_distributed_locking(self):
        """Test distributed locking mechanisms."""
        lock_name = f"{self.TEST_PREFIX}lock:resource1"
        
        # Test lock acquisition
        token = await self.client.acquire_lock(lock_name, timeout=5, ttl=10)
        self.assertIsNotNone(token, "Failed to acquire lock")
        
        # Test lock exclusivity
        second_token = await self.client.acquire_lock(lock_name, timeout=1, ttl=10)
        self.assertIsNone(second_token, "Should not be able to acquire locked resource")
        
        # Test lock release
        released = await self.client.release_lock(lock_name, token)
        self.assertTrue(released, "Failed to release lock")
        
        # Test lock re-acquisition after release
        token = await self.client.acquire_lock(lock_name, timeout=1, ttl=10)
        self.assertIsNotNone(token, "Failed to reacquire lock after release")
        await self.client.release_lock(lock_name, token)
    
    async def test_lock_context_manager(self):
        """Test lock context manager."""
        lock_name = f"{self.TEST_PREFIX}lock:context_test"
        
        # Test context manager acquisition
        async with self.client.with_lock(lock_name, timeout=5, ttl=10):
            # Verify lock is held - try to acquire again
            second_token = await self.client.acquire_lock(lock_name, timeout=1, ttl=10)
            self.assertIsNone(second_token, "Context manager did not acquire lock")
        
        # Verify lock is released after context exit
        token = await self.client.acquire_lock(lock_name, timeout=1, ttl=10)
        self.assertIsNotNone(token, "Context manager did not release lock")
        await self.client.release_lock(lock_name, token)
    
    async def test_server_info(self):
        """Test server information retrieval."""
        info = await self.client.info()
        self.assertIsInstance(info, dict, "Server info should be a dictionary")
        self.assertIn("redis_version", info, "Server info should contain redis_version")
    
    async def test_flush_cache(self):
        """Test cache flushing."""
        # Set multiple test keys
        for i in range(3):
            await self.client.set_cache(f"{self.TEST_PREFIX}flush_test:{i}", f"value_{i}")
        
        # Flush only these test keys
        flushed = await self.client.flush_cache(f"{self.TEST_PREFIX}flush_test:*")
        self.assertEqual(flushed, 3, "Should have flushed 3 keys")
        
        # Verify all flushed
        for i in range(3):
            value = await self.client.get_cache(f"{self.TEST_PREFIX}flush_test:{i}")
            self.assertIsNone(value, f"Key flush_test:{i} should be flushed")
    
    async def test_multi_window_rate_limiting(self):
        """Test multi-window rate limiting functionality."""
        client_id = f"{self.TEST_PREFIX}client:101"
        key_prefix = f"rate:{client_id}"
        
        # Define multiple windows to test
        windows = [
            (5, 5),    # 5 events per 5 seconds
            (10, 10),  # 10 events per 10 seconds
            (15, 15)   # 15 events per 15 seconds
        ]
        
        # Initially should not be rate limited for any window
        is_limited, counts = await self.client.check_multi_window_rate_limits(key_prefix, windows)
        
        self.assertFalse(is_limited, "Should not be rate limited initially")
        self.assertEqual(len(counts), 3, "Should have counts for all 3 windows")
        
        # All counts should be 0
        for window_seconds, count in counts.items():
            self.assertEqual(count, 0, f"Initial count for window {window_seconds}s should be 0")
        
        # Register 7 events - should hit first window limit but not others
        for i in range(7):
            window_list = [w[1] for w in windows]  # Extract just the window sizes
            counts = await self.client.register_multi_window_event(key_prefix, window_list)
            
            self.assertEqual(counts[5], i+1, f"Count for 5s window should be {i+1}")
            self.assertEqual(counts[10], i+1, f"Count for 10s window should be {i+1}")
            self.assertEqual(counts[15], i+1, f"Count for 15s window should be {i+1}")
        
        # Check limits - should be limited on first window (5 events per 5 seconds)
        is_limited, counts = await self.client.check_multi_window_rate_limits(key_prefix, windows)
        
        self.assertTrue(is_limited, "Should be rate limited now")
        self.assertEqual(counts[5], 7, "5s window should have 7 events")
        self.assertEqual(counts[10], 7, "10s window should have 7 events")
        self.assertEqual(counts[15], 7, "15s window should have 7 events")
        
        # The 5s window is rate limited (max 5, actual 7)
        # But the 10s and 15s windows are not (max 10/15, actual 7)

    async def test_multi_window_event_registration(self):
        """Test registering events across multiple windows."""
        client_id = f"{self.TEST_PREFIX}client:202"
        key_prefix = f"rate:{client_id}"
        
        # Define windows of different sizes
        windows = [5, 60, 3600]  # 5s, 1m, 1h
        
        # Register a single event across all windows
        counts = await self.client.register_multi_window_event(key_prefix, windows)
        
        # Verify counts for all windows are 1
        for window_size in windows:
            self.assertEqual(counts[window_size], 1, f"Count for {window_size}s window should be 1")
        
        # Register 4 more events
        for i in range(4):
            await self.client.register_multi_window_event(key_prefix, windows)
        
        # Get event counts for each window
        for window_size in windows:
            count = await self.client.get_event_count(f"{key_prefix}:{window_size}", window_size)
            self.assertEqual(count, 5, f"After 5 registrations, {window_size}s window should have 5 events")
        
        # Verify with check_multi_window_rate_limits
        limits = [(3, 5), (10, 60), (20, 3600)]  # Lower the 5s limit to 3 to trigger rate limiting
        
        is_limited, counts = await self.client.check_multi_window_rate_limits(key_prefix, limits)
        
        self.assertTrue(is_limited, "Should be rate limited on the 5s window")
        self.assertEqual(counts[5], 5, "5s window should have 5 events")
        self.assertEqual(counts[60], 5, "60s window should have 5 events")
        self.assertEqual(counts[3600], 5, "3600s window should have 5 events")
        
        # Only the 5s window should be rate limited (limit 3, actual 5)
        # The other windows should not be rate limited (limits 10, 20; actual 5)
    async def test_cache_with_primitive_types(self):
        """Test setting and retrieving cache entries with integer, float, and boolean values."""
        # Create unique test keys for each type
        int_key = f"{self.TEST_PREFIX}int_value"
        float_key = f"{self.TEST_PREFIX}float_value"
        bool_key = f"{self.TEST_PREFIX}bool_value"
        
        # Define test values for each primitive type
        original_int = 42
        original_float = 3.14159
        original_bool = True
        
        # Set values in cache with a short TTL
        await self.client.set_cache(int_key, original_int, ttl=60)
        await self.client.set_cache(float_key, original_float, ttl=60)
        await self.client.set_cache(bool_key, original_bool, ttl=60)
        
        # Retrieve values from cache
        retrieved_int = await self.client.get_cache(int_key)
        retrieved_float = await self.client.get_cache(float_key)
        retrieved_bool = await self.client.get_cache(bool_key)
        
        # Verify the retrieved values match the originals and have correct types
        self.assertEqual(retrieved_int, original_int, "Retrieved integer should match original")
        self.assertIsInstance(retrieved_int, int, "Retrieved value should be an integer")
        
        self.assertEqual(retrieved_float, original_float, "Retrieved float should match original")
        self.assertIsInstance(retrieved_float, float, "Retrieved value should be a float")
        
        self.assertEqual(retrieved_bool, original_bool, "Retrieved boolean should match original")
        self.assertIsInstance(retrieved_bool, bool, "Retrieved value should be a boolean")
        
        # Test with extreme values
        max_int = 9223372036854775807  # Max 64-bit signed integer
        min_float = 2.2250738585072014e-308  # Min positive normalized float (64-bit)
        
        # Set extreme values
        await self.client.set_cache(f"{int_key}_extreme", max_int)
        await self.client.set_cache(f"{float_key}_extreme", min_float)
        
        # Retrieve extreme values
        retrieved_max_int = await self.client.get_cache(f"{int_key}_extreme")
        retrieved_min_float = await self.client.get_cache(f"{float_key}_extreme")
        
        # Verify extreme values
        self.assertEqual(retrieved_max_int, max_int, "Retrieved extreme integer should match original")
        self.assertEqual(retrieved_min_float, min_float, "Retrieved extreme float should match original")

    async def test_multi_window_sliding_behavior(self):
        """Test that multi-window rate limiting properly implements sliding windows."""
        client_id = f"{self.TEST_PREFIX}client:303"
        key_prefix = f"rate:{client_id}"
        
        # Use a very short window for testing
        windows = [(3, 2)]  # 3 events per 2 seconds
        window_seconds = 2
        
        # Register 3 events (should not be rate limited yet)
        for i in range(3):
            await self.client.register_multi_window_event(key_prefix, [window_seconds])
        
        is_limited, counts = await self.client.check_multi_window_rate_limits(key_prefix, windows)
        self.assertFalse(is_limited, "Should not be rate limited with exactly 3 events")
        self.assertEqual(counts[window_seconds], 3, "Should have 3 events in the window")
        
        # Add 1 more event to exceed the limit
        await self.client.register_multi_window_event(key_prefix, [window_seconds])
        
        is_limited, counts = await self.client.check_multi_window_rate_limits(key_prefix, windows)
        self.assertTrue(is_limited, "Should be rate limited with 4 events")
        self.assertEqual(counts[window_seconds], 4, "Should have 4 events in the window")
        
        # Wait for the window to slide (events to expire)
        await asyncio.sleep(2.5)  # Wait longer than the window
        
        # All old events should have expired, so no longer rate limited
        is_limited, counts = await self.client.check_multi_window_rate_limits(key_prefix, windows)
        self.assertFalse(is_limited, "Should not be rate limited after window expired")
        self.assertEqual(counts[window_seconds], 0, "Should have 0 events in the window after expiry")
    
    async def test_cache_with_bytes_object(self):
        """Test setting and retrieving a cache entry with bytes object."""
        # Create a test key with a unique identifier
        cache_key = f"{self.TEST_PREFIX}bytes_object"
        
        # Create a bytes object
        original_bytes = b"This is a test bytes object \x00\x01\x02\x03\xff"
        
        # Set the bytes object in cache
        await self.client_raw.set_cache(cache_key, original_bytes, ttl=60)
        
        # Retrieve the bytes object from cache
        retrieved_bytes = await self.client_raw.get_binary_cache(cache_key)
        
        # Verify the retrieved object is bytes and matches the original
        self.assertIsInstance(retrieved_bytes, bytes, "Retrieved object should be bytes")
        self.assertEqual(retrieved_bytes, original_bytes, "Retrieved bytes should match original bytes")
        
        # Clean up
        await self.client_raw.delete_cache(cache_key)

    async def test_cache_with_compressed_large_string(self):
        """Test compressing a large string, caching it, and retrieving/decompressing it."""
        import zlib
        
        # Create a test key with a unique identifier
        cache_key = f"{self.TEST_PREFIX}compressed_string"
        
        # Create a string longer than 1024 characters
        original_string = "This is a test string. " * 100  # Creates a string ~2400 chars long
        self.assertGreater(len(original_string), 1024, "Test string should be longer than 1024 characters")
        
        # Compress the string
        compressed_bytes = zlib.compress(original_string.encode('utf-8'))
        
        # Log compression stats for debugging
        compression_ratio = len(compressed_bytes) / len(original_string)
        print(f"Original size: {len(original_string)}, Compressed size: {len(compressed_bytes)}, Ratio: {compression_ratio:.2f}")
        
        # Store the compressed bytes in cache
        await self.client_raw.set_cache(cache_key, compressed_bytes, ttl=60)
        
        # Retrieve the compressed bytes from cache
        retrieved_compressed = await self.client_raw.get_binary_cache(cache_key)
        
        # Verify the retrieved object is bytes
        self.assertIsInstance(retrieved_compressed, bytes, "Retrieved object should be bytes")
        self.assertEqual(retrieved_compressed, compressed_bytes, "Retrieved compressed data should match original compressed data")
        
        # Decompress the retrieved bytes
        decompressed_string = zlib.decompress(retrieved_compressed).decode('utf-8')
        
        # Verify the decompressed string matches the original
        self.assertEqual(decompressed_string, original_string, "Decompressed string should match original string")
        
        # Clean up
        await self.client_raw.delete_cache(cache_key)

    async def test_concurrent_lock_waiting(self):
        """
        Test concurrent operations waiting for locks to be released.
        This demonstrates how multiple tasks compete for the same lock and wait for each other.
        """
        lock_name = f"{self.TEST_PREFIX}lock:concurrent_test"
        execution_order = []
        lock_held_times = {}
        
        async def worker_task(worker_id: str, hold_duration: float, timeout: int = 15):
            """
            A worker task that tries to acquire a lock, holds it, then releases it.
            
            Args:
                worker_id: Unique identifier for this worker
                hold_duration: How long to hold the lock (seconds)
                timeout: How long to wait for lock acquisition (seconds)
            """
            start_time = asyncio.get_event_loop().time()
            logger.info(f"Worker {worker_id}: Starting lock acquisition attempt")
            
            try:
                # Try to acquire the lock
                token = await self.client.acquire_lock(lock_name, timeout=timeout, ttl=int(hold_duration + 5))
                
                if token:
                    acquire_time = asyncio.get_event_loop().time()
                    wait_time = acquire_time - start_time
                    execution_order.append(f"{worker_id}_acquired")
                    lock_held_times[worker_id] = {
                        'acquired_at': acquire_time,
                        'wait_time': wait_time
                    }
                    
                    logger.info(f"Worker {worker_id}: Lock acquired after {wait_time:.2f}s wait")
                    
                    # Hold the lock for the specified duration
                    await asyncio.sleep(hold_duration)
                    
                    # Release the lock
                    released = await self.client.release_lock(lock_name, token)
                    release_time = asyncio.get_event_loop().time()
                    lock_held_times[worker_id]['released_at'] = release_time
                    lock_held_times[worker_id]['held_duration'] = release_time - acquire_time
                    
                    execution_order.append(f"{worker_id}_released")
                    logger.info(f"Worker {worker_id}: Lock released after holding for {release_time - acquire_time:.2f}s")
                    
                    return {"success": True, "token": token, "released": released}
                else:
                    logger.warning(f"Worker {worker_id}: Failed to acquire lock within {timeout}s")
                    execution_order.append(f"{worker_id}_timeout")
                    return {"success": False, "reason": "timeout"}
                    
            except Exception as e:
                logger.error(f"Worker {worker_id}: Error during lock operation: {e}")
                execution_order.append(f"{worker_id}_error")
                return {"success": False, "reason": f"error: {e}"}
        
        # Test Case 1: Sequential lock acquisition with waiting
        logger.info("=== Test Case 1: Sequential lock acquisition ===")
        
        # Create tasks that will compete for the same lock
        # Worker A holds lock for 2 seconds, Worker B waits and then holds for 1 second
        tasks = [
            asyncio.create_task(worker_task("A", hold_duration=2.0, timeout=10)),
            asyncio.create_task(worker_task("B", hold_duration=1.0, timeout=10)),
        ]
        
        # Start all tasks simultaneously
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify results
        self.assertEqual(len(results), 2, "Should have 2 task results")
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.fail(f"Task {i} raised an exception: {result}")
            self.assertTrue(result["success"], f"Task {i} should have succeeded: {result}")
        
        # Verify execution order - both should acquire and release in sequence
        expected_patterns = [
            ["A_acquired", "A_released", "B_acquired", "B_released"],
            ["B_acquired", "B_released", "A_acquired", "A_released"]
        ]
        self.assertIn(execution_order[:4], expected_patterns, 
                     f"Execution order should follow one of the expected patterns. Got: {execution_order}")
        
        # Verify that locks were held for approximately the expected duration
        for worker_id in ["A", "B"]:
            if worker_id in lock_held_times:
                held_duration = lock_held_times[worker_id]["held_duration"]
                expected_duration = 2.0 if worker_id == "A" else 1.0
                # Allow some tolerance for timing
                self.assertAlmostEqual(held_duration, expected_duration, delta=0.5,
                                     msg=f"Worker {worker_id} should hold lock for ~{expected_duration}s")
        
        # Clear for next test
        execution_order.clear()
        lock_held_times.clear()
        
        # Test Case 2: Multiple workers competing with different timeouts
        logger.info("=== Test Case 2: Multiple workers with different timeouts ===")
        
        # Create more complex scenario with multiple workers
        tasks = [
            asyncio.create_task(worker_task("X", hold_duration=1.5, timeout=12)),
            asyncio.create_task(worker_task("Y", hold_duration=0.5, timeout=12)),
            asyncio.create_task(worker_task("Z", hold_duration=1.0, timeout=12)),
        ]
        
        # Add a small delay between starting tasks to create more realistic timing
        await asyncio.sleep(0.1)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify all tasks completed successfully
        successful_tasks = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Task {i} raised exception: {result}")
                continue
            if result["success"]:
                successful_tasks += 1
                
        self.assertGreaterEqual(successful_tasks, 2, 
                               "At least 2 out of 3 tasks should succeed in acquiring locks")
        
        # Verify no overlapping lock holds (mutual exclusion)
        acquired_times = []
        released_times = []
        
        for worker_id in ["X", "Y", "Z"]:
            if worker_id in lock_held_times:
                acquired_times.append((worker_id, lock_held_times[worker_id]["acquired_at"]))
                released_times.append((worker_id, lock_held_times[worker_id]["released_at"]))
        
        # Sort by acquisition time
        acquired_times.sort(key=lambda x: x[1])
        
        # Verify mutual exclusion: each lock should be released before the next is acquired
        for i in range(len(acquired_times) - 1):
            current_worker = acquired_times[i][0]
            next_worker = acquired_times[i + 1][0]
            
            current_release_time = lock_held_times[current_worker]["released_at"]
            next_acquire_time = lock_held_times[next_worker]["acquired_at"]
            
            self.assertLessEqual(current_release_time, next_acquire_time + 0.1,  # Small tolerance
                               f"Worker {current_worker} should release before worker {next_worker} acquires")
        
        logger.info(f"Final execution order: {execution_order}")
        logger.info(f"Lock timing details: {lock_held_times}")
        
        # Test Case 3: Context manager with concurrent access
        logger.info("=== Test Case 3: Context manager concurrent access ===")
        
        execution_order.clear()
        context_execution_order = []
        
        async def context_worker(worker_id: str, work_duration: float):
            """Worker that uses the lock context manager."""
            try:
                context_execution_order.append(f"{worker_id}_waiting")
                async with self.client.with_lock(lock_name, timeout=10, ttl=15):
                    context_execution_order.append(f"{worker_id}_entered")
                    logger.info(f"Context worker {worker_id}: Entered critical section")
                    await asyncio.sleep(work_duration)
                    context_execution_order.append(f"{worker_id}_exiting")
                    logger.info(f"Context worker {worker_id}: Exiting critical section")
                context_execution_order.append(f"{worker_id}_exited")
                return {"success": True}
            except Exception as e:
                context_execution_order.append(f"{worker_id}_error")
                logger.error(f"Context worker {worker_id}: Error: {e}")
                return {"success": False, "error": str(e)}
        
        # Create concurrent context manager tasks
        context_tasks = [
            asyncio.create_task(context_worker("CTX1", 1.0)),
            asyncio.create_task(context_worker("CTX2", 0.5)),
        ]
        
        context_results = await asyncio.gather(*context_tasks, return_exceptions=True)
        
        # Verify both context manager tasks succeeded
        for i, result in enumerate(context_results):
            if isinstance(result, Exception):
                self.fail(f"Context task {i} raised an exception: {result}")
            self.assertTrue(result["success"], f"Context task {i} should have succeeded")
        
        # Verify proper sequencing in context manager execution
        # Both workers should complete their full cycle
        expected_context_events = 8  # 4 events per worker (waiting, entered, exiting, exited)
        self.assertEqual(len(context_execution_order), expected_context_events,
                        f"Should have {expected_context_events} context events")
        
        # Verify that no two workers are in the critical section simultaneously
        in_critical_section = set()
        for event in context_execution_order:
            if event.endswith("_entered"):
                worker_id = event.split("_")[0]
                self.assertEqual(len(in_critical_section), 0, 
                               f"Worker {worker_id} entered while {in_critical_section} still in critical section")
                in_critical_section.add(worker_id)
            elif event.endswith("_exiting"):
                worker_id = event.split("_")[0]
                self.assertIn(worker_id, in_critical_section, 
                             f"Worker {worker_id} exiting but was not in critical section")
                in_critical_section.remove(worker_id)
        
        logger.info(f"Context execution order: {context_execution_order}")

    # === NEW TESTS FOR QUEUE MANAGEMENT METHODS ===

    async def test_push_request_basic(self):
        """Test basic push_request functionality."""
        queue_key = f"{self.TEST_PREFIX}queue:basic"
        
        # Clear any existing data first
        await self.client.clear_queue(queue_key, clear_dupefilter=True)
        
        # Test basic request push
        request_data = {
            "url": "https://example.com/page1",
            "method": "GET",
            "headers": {"User-Agent": "test"},
            "meta": {"depth": 1}
        }
        
        result = await self.client.push_request(queue_key, request_data, priority=5)
        self.assertTrue(result, "Request should be successfully queued")
        
        # Test duplicate filtering
        result = await self.client.push_request(queue_key, request_data, priority=5)
        self.assertFalse(result, "Duplicate request should be filtered")
        
        # Test with custom dedupe key
        request_data2 = {
            "url": "https://example.com/page2",
            "method": "GET",
            "headers": {"User-Agent": "test"},
            "meta": {"depth": 1}
        }
        
        result = await self.client.push_request(queue_key, request_data2, priority=3, dedupe_key="custom_key")
        self.assertTrue(result, "Request with custom dedupe key should be queued")
        
        # Test duplicate with same custom dedupe key
        result = await self.client.push_request(queue_key, request_data2, priority=3, dedupe_key="custom_key")
        self.assertFalse(result, "Duplicate custom dedupe key should be filtered")

    async def test_push_request_safe_memory_check(self):
        """Test push_request_safe with memory usage checking."""
        queue_key = f"{self.TEST_PREFIX}queue:safe"
        
        # Clear any existing data first
        await self.client.clear_queue(queue_key, clear_dupefilter=True)
        
        request_data = {
            "url": "https://example.com/safe_test",
            "method": "GET",
            "meta": {"test": "memory_safe"}
        }
        
        # This should work normally since memory usage is likely low
        result = await self.client.push_request_safe(queue_key, request_data, priority=1)
        self.assertTrue(result, "Request should be queued when memory usage is normal")
        
        # Verify the request was actually queued
        queue_length = await self.client.get_queue_length(queue_key)
        self.assertEqual(queue_length, 1, "Queue should contain 1 request")

    async def test_pop_request_basic(self):
        """Test basic pop_request functionality."""
        queue_key = f"{self.TEST_PREFIX}queue:pop"
        
        # Clear any existing data first
        await self.client.clear_queue(queue_key, clear_dupefilter=True)
        
        # Push requests with different priorities
        requests = [
            {"url": "https://example.com/low", "priority": 1},
            {"url": "https://example.com/high", "priority": 10},
            {"url": "https://example.com/medium", "priority": 5}
        ]
        
        for req in requests:
            await self.client.push_request(queue_key, req, priority=req["priority"])
        
        # Pop requests - should come out in priority order (highest first)
        popped1 = await self.client.pop_request(queue_key)
        self.assertIsNotNone(popped1, "Should pop a request")
        self.assertEqual(popped1["url"], "https://example.com/high", "Should pop highest priority first")
        
        popped2 = await self.client.pop_request(queue_key)
        self.assertIsNotNone(popped2, "Should pop second request")
        self.assertEqual(popped2["url"], "https://example.com/medium", "Should pop medium priority second")
        
        popped3 = await self.client.pop_request(queue_key)
        self.assertIsNotNone(popped3, "Should pop third request")
        self.assertEqual(popped3["url"], "https://example.com/low", "Should pop lowest priority last")
        
        # Pop from empty queue
        popped_empty = await self.client.pop_request(queue_key)
        self.assertIsNone(popped_empty, "Should return None for empty queue")

    async def test_push_requests_batch(self):
        """Test batch request pushing."""
        queue_key = f"{self.TEST_PREFIX}queue:batch"
        
        # Clear any existing data first to ensure test isolation
        await self.client.clear_queue(queue_key, clear_dupefilter=True)
        
        # Test batch push with duplicates
        requests = [
            {"url": "https://example.com/batch1", "priority": 1},
            {"url": "https://example.com/batch2", "priority": 2},
            {"url": "https://example.com/batch1", "priority": 3},  # Duplicate
            {"url": "https://example.com/batch3", "priority": 4}
        ]
        
        # Push with duplicate checking
        queued_count = await self.client.push_requests_batch(queue_key, requests, check_duplicates=True)
        self.assertEqual(queued_count, 3, "Should queue 3 unique requests")
        
        # Verify queue length
        queue_length = await self.client.get_queue_length(queue_key)
        self.assertEqual(queue_length, 3, "Queue should contain 3 requests")
        
        # Test batch push without duplicate checking
        more_requests = [
            {"url": "https://example.com/batch4", "priority": 5},
            {"url": "https://example.com/batch5", "priority": 6}
        ]
        
        queued_count = await self.client.push_requests_batch(queue_key, more_requests, check_duplicates=False)
        self.assertEqual(queued_count, 2, "Should queue 2 more requests")
        
        # Verify total queue length
        queue_length = await self.client.get_queue_length(queue_key)
        self.assertEqual(queue_length, 5, "Queue should contain 5 requests total")

    async def test_get_queue_length(self):
        """Test queue length checking."""
        queue_key = f"{self.TEST_PREFIX}queue:length"
        
        # Empty queue
        length = await self.client.get_queue_length(queue_key)
        self.assertEqual(length, 0, "Empty queue should have length 0")
        
        # Add some requests
        for i in range(5):
            await self.client.push_request(queue_key, {"url": f"https://example.com/test{i}"}, priority=i)
        
        length = await self.client.get_queue_length(queue_key)
        self.assertEqual(length, 5, "Queue should have length 5")

    async def test_clear_queue(self):
        """Test queue clearing functionality."""
        queue_key = f"{self.TEST_PREFIX}queue:clear"
        
        # Ensure queue is empty to start
        await self.client.clear_queue(queue_key, clear_dupefilter=True)
        
        # Add some requests
        for i in range(3):
            await self.client.push_request(queue_key, {"url": f"https://example.com/clear{i}"}, priority=i)
        
        # Verify queue has items
        length = await self.client.get_queue_length(queue_key)
        self.assertEqual(length, 3, "Queue should have 3 items before clearing")
        
        # Clear queue and dupefilter
        queue_removed, dupefilter_removed = await self.client.clear_queue(queue_key, clear_dupefilter=True)
        self.assertEqual(queue_removed, 3, "Should remove 3 items from queue")
        self.assertEqual(dupefilter_removed, 3, "Should remove 3 items from dupefilter")
        
        # Verify queue is empty
        length = await self.client.get_queue_length(queue_key)
        self.assertEqual(length, 0, "Queue should be empty after clearing")

    async def test_peek_queue(self):
        """Test queue peeking functionality."""
        queue_key = f"{self.TEST_PREFIX}queue:peek"
        
        # Add requests with different priorities
        requests = [
            {"url": "https://example.com/peek1", "priority": 1},
            {"url": "https://example.com/peek2", "priority": 5},
            {"url": "https://example.com/peek3", "priority": 3}
        ]
        
        for req in requests:
            await self.client.push_request(queue_key, req, priority=req["priority"])
        
        # Peek at queue (should be ordered by priority)
        peeked = await self.client.peek_queue(queue_key, count=2)
        self.assertEqual(len(peeked), 2, "Should peek at 2 requests")
        self.assertEqual(peeked[0]["url"], "https://example.com/peek2", "First should be highest priority")
        self.assertEqual(peeked[0]["_queue_priority"], 5, "Should include priority in peeked data")
        self.assertEqual(peeked[1]["url"], "https://example.com/peek3", "Second should be medium priority")
        
        # Verify queue is unchanged
        length = await self.client.get_queue_length(queue_key)
        self.assertEqual(length, 3, "Queue length should be unchanged after peeking")

    async def test_update_request_priority(self):
        """Test request priority updating."""
        queue_key = f"{self.TEST_PREFIX}queue:update"
        
        # Add requests
        requests = [
            {"url": "https://example.com/update1", "priority": 1},
            {"url": "https://example.com/update2", "priority": 2}
        ]
        
        for req in requests:
            await self.client.push_request(queue_key, req, priority=req["priority"])
        
        # Update priority of first request
        updated = await self.client.update_request_priority(queue_key, "https://example.com/update1", 10)
        self.assertTrue(updated, "Should successfully update priority")
        
        # Verify new priority order
        peeked = await self.client.peek_queue(queue_key, count=2)
        self.assertEqual(peeked[0]["url"], "https://example.com/update1", "Updated request should be first")
        self.assertEqual(peeked[0]["_queue_priority"], 10, "Priority should be updated")
        
        # Try to update non-existent request
        updated = await self.client.update_request_priority(queue_key, "https://example.com/nonexistent", 5)
        self.assertFalse(updated, "Should return False for non-existent request")

    async def test_get_queue_stats(self):
        """Test queue statistics retrieval."""
        queue_key = f"{self.TEST_PREFIX}queue:stats"
        
        # Add requests with different priorities
        requests = [
            {"url": "https://example.com/stats1", "priority": 1},
            {"url": "https://example.com/stats2", "priority": 10},
            {"url": "https://example.com/stats3", "priority": 5}
        ]
        
        for req in requests:
            await self.client.push_request(queue_key, req, priority=req["priority"])
        
        # Get queue stats
        stats = await self.client.get_queue_stats(queue_key)
        
        self.assertEqual(stats["queue_size"], 3, "Should report correct queue size")
        self.assertEqual(stats["dupefilter_size"], 3, "Should report correct dupefilter size")
        self.assertEqual(stats["highest_priority"], 10, "Should report correct highest priority")
        self.assertEqual(stats["lowest_priority"], 1, "Should report correct lowest priority")
        self.assertIsInstance(stats["dupefilter_ttl"], int, "Should report dupefilter TTL")
        self.assertGreater(stats["dupefilter_ttl"], 0, "Dupefilter TTL should be positive")

    # === NEW TESTS FOR MEMORY MONITORING METHODS ===

    async def test_check_memory_usage(self):
        """Test memory usage checking."""
        usage = await self.client.check_memory_usage()
        self.assertIsInstance(usage, float, "Memory usage should be a float")
        self.assertGreaterEqual(usage, 0, "Memory usage should be non-negative")
        self.assertLessEqual(usage, 100, "Memory usage should not exceed 100%")
        
        logger.info(f"Current Redis memory usage: {usage:.2f}%")

    async def test_get_memory_info(self):
        """Test detailed memory information retrieval."""
        memory_info = await self.client.get_memory_info()
        
        self.assertIsInstance(memory_info, dict, "Memory info should be a dictionary")
        
        # Check required fields
        required_fields = [
            'used_memory', 'used_memory_human', 'maxmemory', 'maxmemory_human',
            'maxmemory_policy', 'mem_fragmentation_ratio', 'usage_percent'
        ]
        
        for field in required_fields:
            self.assertIn(field, memory_info, f"Memory info should contain {field}")
        
        # Check data types
        self.assertIsInstance(memory_info['used_memory'], int, "used_memory should be integer")
        self.assertIsInstance(memory_info['used_memory_human'], str, "used_memory_human should be string")
        self.assertIsInstance(memory_info['maxmemory'], int, "maxmemory should be integer")
        self.assertIsInstance(memory_info['maxmemory_human'], str, "maxmemory_human should be string")
        self.assertIsInstance(memory_info['maxmemory_policy'], str, "maxmemory_policy should be string")
        self.assertIsInstance(memory_info['mem_fragmentation_ratio'], float, "mem_fragmentation_ratio should be float")
        self.assertIsInstance(memory_info['usage_percent'], float, "usage_percent should be float")
        
        logger.info(f"Memory info: {memory_info}")

    # === NEW TESTS FOR TEMPORARY STATE STORAGE METHODS ===

    async def test_set_job_state(self):
        """Test job state setting."""
        job_key = f"{self.TEST_PREFIX}job:state_test"
        
        state_data = {
            "status": "running",
            "progress": 0.5,
            "items_processed": 100,
            "errors": [],
            "metadata": {"start_time": "2023-01-01T00:00:00Z"}
        }
        
        # Set job state
        await self.client.set_job_state(job_key, state_data, ttl=3600)
        
        # Verify state was set by checking if key exists
        client = await self.client.get_client()
        exists = await client.exists(f"job_state:{job_key}")
        self.assertTrue(exists, "Job state key should exist")
        
        # Check TTL was set
        ttl = await client.ttl(f"job_state:{job_key}")
        self.assertGreater(ttl, 0, "TTL should be set")
        self.assertLessEqual(ttl, 3600, "TTL should not exceed set value")

    async def test_get_job_state(self):
        """Test job state retrieval."""
        job_key = f"{self.TEST_PREFIX}job:get_state"
        
        # Set initial state
        original_state = {
            "status": "processing",
            "progress": 0.75,
            "items_processed": 150,
            "errors": ["error1", "error2"],
            "metadata": {"worker_id": "worker-123"}
        }
        
        await self.client.set_job_state(job_key, original_state, ttl=3600)
        
        # Get state back
        retrieved_state = await self.client.get_job_state(job_key)
        
        self.assertEqual(retrieved_state, original_state, "Retrieved state should match original")
        
        # Test non-existent job state
        empty_state = await self.client.get_job_state(f"{self.TEST_PREFIX}job:nonexistent")
        self.assertEqual(empty_state, {}, "Non-existent job state should return empty dict")

    async def test_increment_job_counter(self):
        """Test job counter incrementing."""
        job_key = f"{self.TEST_PREFIX}job:counter"
        
        # Test initial increment
        count = await self.client.increment_job_counter(job_key, "processed_items", 1)
        self.assertEqual(count, 1, "Initial counter should be 1")
        
        # Test increment by different amounts
        count = await self.client.increment_job_counter(job_key, "processed_items", 5)
        self.assertEqual(count, 6, "Counter should be 6 after incrementing by 5")
        
        # Test multiple counters
        count = await self.client.increment_job_counter(job_key, "errors", 1)
        self.assertEqual(count, 1, "Error counter should be 1")
        
        count = await self.client.increment_job_counter(job_key, "warnings", 3)
        self.assertEqual(count, 3, "Warning counter should be 3")
        
        # Verify all counters exist in job state
        state = await self.client.get_job_state(job_key)
        self.assertEqual(state["processed_items"], 6, "Processed items should be 6 (integer)")
        self.assertEqual(state["errors"], 1, "Errors should be 1 (integer)")
        self.assertEqual(state["warnings"], 3, "Warnings should be 3 (integer)")

    async def test_job_state_mixed_operations(self):
        """Test mixed operations on job state."""
        job_key = f"{self.TEST_PREFIX}job:mixed"
        
        # Set initial state
        initial_state = {
            "status": "starting",
            "worker_id": "worker-456",
            "config": {"batch_size": 100}
        }
        
        await self.client.set_job_state(job_key, initial_state, ttl=3600)
        
        # Increment some counters
        await self.client.increment_job_counter(job_key, "batches_processed", 5)
        await self.client.increment_job_counter(job_key, "items_processed", 500)
        
        # Get combined state
        state = await self.client.get_job_state(job_key)
        
        # Verify original state is preserved
        self.assertEqual(state["status"], "starting", "Original status should be preserved")
        self.assertEqual(state["worker_id"], "worker-456", "Original worker_id should be preserved")
        self.assertEqual(state["config"], {"batch_size": 100}, "Original config should be preserved")
        
        # Verify counters are added (as integers)
        self.assertEqual(state["batches_processed"], 5, "Batches processed counter should be 5 (integer)")
        self.assertEqual(state["items_processed"], 500, "Items processed counter should be 500 (integer)")

    async def test_job_state_ttl_expiration(self):
        """Test that job state expires according to TTL."""
        job_key = f"{self.TEST_PREFIX}job:ttl_test"
        
        # Set job state with very short TTL
        state_data = {"status": "temporary", "test": True}
        await self.client.set_job_state(job_key, state_data, ttl=1)  # 1 second TTL
        
        # Verify state exists immediately
        state = await self.client.get_job_state(job_key)
        self.assertEqual(state, state_data, "State should exist immediately")
        
        # Wait for expiration
        await asyncio.sleep(2)
        
        # Verify state has expired
        expired_state = await self.client.get_job_state(job_key)
        self.assertEqual(expired_state, {}, "State should be empty after TTL expiration")

    async def test_queue_integration_workflow(self):
        """Test a complete workflow integrating queue operations."""
        queue_key = f"{self.TEST_PREFIX}queue:workflow"
        job_key = f"{self.TEST_PREFIX}job:workflow"
        
        # Clear any existing data first
        await self.client.clear_queue(queue_key, clear_dupefilter=True)
        
        # Initialize job state
        await self.client.set_job_state(job_key, {
            "status": "starting",
            "total_urls": 0,
            "processed_urls": 0
        })
        
        # Add URLs to queue
        urls = [
            {"url": "https://example.com/page1", "priority": 1},
            {"url": "https://example.com/page2", "priority": 5},
            {"url": "https://example.com/page3", "priority": 3}
        ]
        
        queued_count = await self.client.push_requests_batch(queue_key, urls)
        self.assertEqual(queued_count, 3, "Should queue 3 URLs")
        
        # Update job state with total count
        await self.client.increment_job_counter(job_key, "total_urls", queued_count)
        
        # Process URLs in priority order
        processed_urls = []
        while True:
            request = await self.client.pop_request(queue_key)
            if not request:
                break
                
            processed_urls.append(request["url"])
            await self.client.increment_job_counter(job_key, "processed_urls", 1)
        
        # Verify processing order (highest priority first)
        expected_order = [
            "https://example.com/page2",  # priority 5
            "https://example.com/page3",  # priority 3
            "https://example.com/page1"   # priority 1
        ]
        self.assertEqual(processed_urls, expected_order, "URLs should be processed in priority order")
        
        # Verify final job state (counters should be integers)
        final_state = await self.client.get_job_state(job_key)
        self.assertEqual(final_state["total_urls"], 3, "Total URLs should be 3 (integer)")
        self.assertEqual(final_state["processed_urls"], 3, "Processed URLs should be 3 (integer)")
        
        # Verify queue is empty
        queue_length = await self.client.get_queue_length(queue_key)
        self.assertEqual(queue_length, 0, "Queue should be empty after processing")

    # === NEW TESTS FOR PURGE_SPIDER_DATA METHOD ===

    async def test_purge_spider_data_without_job_id(self):
        """Test purging all data for a spider without job_id."""
        spider_name = f"{self.TEST_PREFIX}spider_test"
        
        # Create various types of data for the spider
        # Queue data
        queue_key = f"queue:{spider_name}:requests"
        await self.client.push_request(queue_key, {"url": "https://example.com/1"}, priority=1)
        await self.client.push_request(queue_key, {"url": "https://example.com/2"}, priority=2)
        
        # Job state data  
        job_state_key = f"{spider_name}:main_job"
        await self.client.set_job_state(job_state_key, {"status": "running", "processed": 50})
        
        # Additional job state
        job_state_key2 = f"{spider_name}:secondary_job"
        await self.client.set_job_state(job_state_key2, {"status": "completed", "processed": 100})
        
        # Verify data exists before purging
        queue_length = await self.client.get_queue_length(queue_key)
        self.assertEqual(queue_length, 2, "Queue should have 2 items before purging")
        
        state1 = await self.client.get_job_state(job_state_key)
        self.assertEqual(state1["status"], "running", "Job state should exist before purging")
        
        # Purge spider data
        purged = await self.client.purge_spider_data(spider_name)
        
        # Verify purge results
        self.assertIsInstance(purged, dict, "Purge result should be a dictionary")
        self.assertIn('queue', purged, "Should report queue deletions")
        self.assertIn('dupefilter', purged, "Should report dupefilter deletions")
        self.assertIn('job_state', purged, "Should report job_state deletions")
        self.assertIn('total_keys', purged, "Should report total deletions")
        
        self.assertGreater(purged['total_keys'], 0, "Should delete some keys")
        
        # Verify data is actually purged
        queue_length_after = await self.client.get_queue_length(queue_key)
        self.assertEqual(queue_length_after, 0, "Queue should be empty after purging")
        
        state1_after = await self.client.get_job_state(job_state_key)
        self.assertEqual(state1_after, {}, "Job state should be empty after purging")
        
        state2_after = await self.client.get_job_state(job_state_key2)
        self.assertEqual(state2_after, {}, "Secondary job state should be empty after purging")

    async def test_purge_spider_data_with_job_id(self):
        """Test purging data for a specific spider job."""
        spider_name = f"{self.TEST_PREFIX}spider_job"
        job_id = "job_123"
        
        # Create job-specific data
        job_queue_key = f"queue:{spider_name}:requests:{job_id}"
        await self.client.push_request(job_queue_key, {"url": "https://example.com/job1"}, priority=1)
        
        job_state_key = f"{spider_name}:{job_id}"
        await self.client.set_job_state(job_state_key, {"status": "running", "job_id": job_id})
        
        # Create data for different job (should NOT be purged)
        other_job_id = "job_456"
        other_queue_key = f"queue:{spider_name}:requests:{other_job_id}"
        await self.client.push_request(other_queue_key, {"url": "https://example.com/other"}, priority=1)
        
        other_job_state_key = f"{spider_name}:{other_job_id}"
        await self.client.set_job_state(other_job_state_key, {"status": "completed", "job_id": other_job_id})
        
        # Verify data exists before purging
        queue_length = await self.client.get_queue_length(job_queue_key)
        self.assertEqual(queue_length, 1, "Target job queue should have 1 item")
        
        other_queue_length = await self.client.get_queue_length(other_queue_key)
        self.assertEqual(other_queue_length, 1, "Other job queue should have 1 item")
        
        # Purge only specific job data
        purged = await self.client.purge_spider_data(spider_name, job_id=job_id)
        
        # Verify purge results
        self.assertGreater(purged['total_keys'], 0, "Should delete some keys")
        
        # Verify target job data is purged
        queue_length_after = await self.client.get_queue_length(job_queue_key)
        self.assertEqual(queue_length_after, 0, "Target job queue should be empty after purging")
        
        state_after = await self.client.get_job_state(job_state_key)
        self.assertEqual(state_after, {}, "Target job state should be empty after purging")
        
        # Verify other job data is preserved
        other_queue_length_after = await self.client.get_queue_length(other_queue_key)
        self.assertEqual(other_queue_length_after, 1, "Other job queue should be preserved")
        
        other_state_after = await self.client.get_job_state(other_job_state_key)
        self.assertEqual(other_state_after["status"], "completed", "Other job state should be preserved")

    async def test_purge_spider_data_mixed_types(self):
        """Test purging with mixed data types (queue, dupefilter, job_state)."""
        spider_name = f"{self.TEST_PREFIX}spider_mixed"
        
        # Create queue and dupefilter data
        queue_key = f"queue:{spider_name}:requests"
        await self.client.push_request(queue_key, {"url": "https://example.com/mixed1"}, priority=1)
        await self.client.push_request(queue_key, {"url": "https://example.com/mixed2"}, priority=2)
        
        # Create job state data
        job_state_key1 = f"{spider_name}:job1"
        await self.client.set_job_state(job_state_key1, {"status": "running", "items": 25})
        
        job_state_key2 = f"{spider_name}:job2"  
        await self.client.set_job_state(job_state_key2, {"status": "completed", "items": 50})
        
        # Create some counters
        await self.client.increment_job_counter(job_state_key1, "processed", 10)
        await self.client.increment_job_counter(job_state_key2, "errors", 2)
        
        # Purge all spider data
        purged = await self.client.purge_spider_data(spider_name)
        
        # Verify purge counts
        self.assertGreater(purged['total_keys'], 0, "Should delete some keys")
        
        # Verify all data is purged
        queue_length = await self.client.get_queue_length(queue_key)
        self.assertEqual(queue_length, 0, "Queue should be empty")
        
        state1 = await self.client.get_job_state(job_state_key1)
        self.assertEqual(state1, {}, "Job state 1 should be empty")
        
        state2 = await self.client.get_job_state(job_state_key2)
        self.assertEqual(state2, {}, "Job state 2 should be empty")

    async def test_purge_spider_data_no_matching_data(self):
        """Test purging when no matching data exists."""
        spider_name = f"{self.TEST_PREFIX}spider_empty"
        
        # Purge non-existent spider data
        purged = await self.client.purge_spider_data(spider_name)
        
        # Should return zero counts
        self.assertEqual(purged['queue'], 0, "Should report 0 queue deletions")
        self.assertEqual(purged['dupefilter'], 0, "Should report 0 dupefilter deletions")
        self.assertEqual(purged['job_state'], 0, "Should report 0 job_state deletions")
        self.assertEqual(purged['total_keys'], 0, "Should report 0 total deletions")

    async def test_purge_spider_data_selective_preservation(self):
        """Test that purge only deletes matching spider data and preserves others."""
        spider_name = f"{self.TEST_PREFIX}spider_selective"
        other_spider_name = f"{self.TEST_PREFIX}spider_other"
        
        # Create data for target spider
        target_queue_key = f"queue:{spider_name}:requests"
        await self.client.push_request(target_queue_key, {"url": "https://example.com/target"}, priority=1)
        
        target_job_state_key = f"{spider_name}:main"
        await self.client.set_job_state(target_job_state_key, {"status": "running"})
        
        # Create data for other spider (should be preserved)
        other_queue_key = f"queue:{other_spider_name}:requests"
        await self.client.push_request(other_queue_key, {"url": "https://example.com/other"}, priority=1)
        
        other_job_state_key = f"{other_spider_name}:main"
        await self.client.set_job_state(other_job_state_key, {"status": "completed"})
        
        # Create some unrelated data (should be preserved)
        unrelated_cache_key = f"{self.TEST_PREFIX}unrelated:cache"
        await self.client.set_cache(unrelated_cache_key, {"data": "should_be_preserved"})
        
        # Verify all data exists before purging
        self.assertEqual(await self.client.get_queue_length(target_queue_key), 1)
        self.assertEqual(await self.client.get_queue_length(other_queue_key), 1)
        self.assertEqual((await self.client.get_job_state(target_job_state_key))["status"], "running")
        self.assertEqual((await self.client.get_job_state(other_job_state_key))["status"], "completed")
        self.assertEqual((await self.client.get_cache(unrelated_cache_key))["data"], "should_be_preserved")
        
        # Purge only target spider data
        purged = await self.client.purge_spider_data(spider_name)
        
        # Verify target spider data is purged
        self.assertEqual(await self.client.get_queue_length(target_queue_key), 0)
        self.assertEqual(await self.client.get_job_state(target_job_state_key), {})
        
        # Verify other data is preserved
        self.assertEqual(await self.client.get_queue_length(other_queue_key), 1)
        self.assertEqual((await self.client.get_job_state(other_job_state_key))["status"], "completed")
        self.assertEqual((await self.client.get_cache(unrelated_cache_key))["data"], "should_be_preserved")
        
        # Verify purge reported correct counts
        self.assertGreater(purged['total_keys'], 0, "Should have deleted some keys")

    async def test_purge_spider_data_return_format(self):
        """Test that purge_spider_data returns the expected format."""
        spider_name = f"{self.TEST_PREFIX}spider_format"
        
        # Create some test data
        queue_key = f"queue:{spider_name}:requests"
        await self.client.push_request(queue_key, {"url": "https://example.com/format"}, priority=1)
        
        job_state_key = f"{spider_name}:format_job"
        await self.client.set_job_state(job_state_key, {"status": "testing"})
        
        # Purge data
        purged = await self.client.purge_spider_data(spider_name)
        
        # Verify return format
        self.assertIsInstance(purged, dict, "Should return a dictionary")
        
        expected_keys = ['queue', 'dupefilter', 'job_state', 'total_keys']
        for key in expected_keys:
            self.assertIn(key, purged, f"Should contain '{key}' in result")
            self.assertIsInstance(purged[key], int, f"'{key}' should be an integer")
            self.assertGreaterEqual(purged[key], 0, f"'{key}' should be non-negative")
        
        # Total should be sum of individual types (though some might be 0)
        self.assertGreaterEqual(purged['total_keys'], 
                               purged['queue'] + purged['dupefilter'] + purged['job_state'],
                               "Total should be at least the sum of individual types")

    async def test_purge_spider_data_complex_job_ids(self):
        """Test purging with complex job IDs containing special characters."""
        spider_name = f"{self.TEST_PREFIX}spider_complex"
        
        # Test with various job ID formats
        job_ids = [
            "job_123",
            "job-with-dashes",
            "job.with.dots",
            "job_123_456",
            "2023-01-01_job"
        ]
        
        # Create data for each job ID
        for job_id in job_ids:
            queue_key = f"queue:{spider_name}:requests:{job_id}"
            await self.client.push_request(queue_key, {"url": f"https://example.com/{job_id}"}, priority=1)
            
            job_state_key = f"{spider_name}:{job_id}"
            await self.client.set_job_state(job_state_key, {"status": "running", "job_id": job_id})
        
        # Purge data for one specific job
        target_job_id = "job_123_456"
        purged = await self.client.purge_spider_data(spider_name, job_id=target_job_id)
        
        # Verify only target job data is purged
        target_queue_key = f"queue:{spider_name}:requests:{target_job_id}"
        target_job_state_key = f"{spider_name}:{target_job_id}"
        
        self.assertEqual(await self.client.get_queue_length(target_queue_key), 0)
        self.assertEqual(await self.client.get_job_state(target_job_state_key), {})
        
        # Verify other jobs are preserved
        for job_id in job_ids:
            if job_id != target_job_id:
                queue_key = f"queue:{spider_name}:requests:{job_id}"
                job_state_key = f"{spider_name}:{job_id}"
                
                self.assertEqual(await self.client.get_queue_length(queue_key), 1,
                               f"Job {job_id} queue should be preserved")
                state = await self.client.get_job_state(job_state_key)
                self.assertEqual(state["job_id"], job_id,
                               f"Job {job_id} state should be preserved")

    # === NEW TESTS FOR COUNTER/LIMIT TRACKING METHODS ===

    async def test_increment_counter_with_limit(self):
        """Test counter increment with limit checking."""
        counter_key = f"{self.TEST_PREFIX}counter:test"
        
        # Test basic increment
        count, is_over = await self.client.increment_counter_with_limit(counter_key, 1)
        self.assertEqual(count, 1, "Counter should be 1")
        self.assertFalse(is_over, "Should not be over limit")
        
        # Test increment with limit
        count, is_over = await self.client.increment_counter_with_limit(
            counter_key, increment=2, limit=5
        )
        self.assertEqual(count, 3, "Counter should be 3")
        self.assertFalse(is_over, "Should not be over limit yet")
        
        # Test reaching limit
        count, is_over = await self.client.increment_counter_with_limit(
            counter_key, increment=2, limit=5
        )
        self.assertEqual(count, 5, "Counter should be 5")
        self.assertTrue(is_over, "Should be at limit")
        
        # Test exceeding limit
        count, is_over = await self.client.increment_counter_with_limit(
            counter_key, increment=1, limit=5
        )
        self.assertEqual(count, 6, "Counter should be 6")
        self.assertTrue(is_over, "Should be over limit")
        
        # Test with TTL
        ttl_key = f"{self.TEST_PREFIX}counter:ttl"
        count, is_over = await self.client.increment_counter_with_limit(
            ttl_key, increment=1, ttl=1
        )
        self.assertEqual(count, 1, "Counter should be 1")
        
        # Wait for expiration
        await asyncio.sleep(2)
        count = await self.client.get_counter_value(ttl_key)
        self.assertEqual(count, 0, "Counter should be 0 after expiration")

    async def test_get_counter_value(self):
        """Test getting counter values."""
        counter_key = f"{self.TEST_PREFIX}counter:get"
        
        # Test non-existent counter
        value = await self.client.get_counter_value(counter_key)
        self.assertEqual(value, 0, "Non-existent counter should return 0")
        
        # Set counter value
        await self.client.increment_counter_with_limit(counter_key, 42)
        
        # Get counter value
        value = await self.client.get_counter_value(counter_key)
        self.assertEqual(value, 42, "Counter value should be 42")

    async def test_check_counter_limit(self):
        """Test checking counter against limit without incrementing."""
        counter_key = f"{self.TEST_PREFIX}counter:check"
        
        # Test with non-existent counter
        is_over = await self.client.check_counter_limit(counter_key, 10)
        self.assertFalse(is_over, "Non-existent counter should not be over limit")
        
        # Set counter value
        await self.client.increment_counter_with_limit(counter_key, 8)
        
        # Check various limits
        is_over = await self.client.check_counter_limit(counter_key, 10)
        self.assertFalse(is_over, "8 should not be over limit 10")
        
        is_over = await self.client.check_counter_limit(counter_key, 8)
        self.assertTrue(is_over, "8 should be at limit 8")
        
        is_over = await self.client.check_counter_limit(counter_key, 5)
        self.assertTrue(is_over, "8 should be over limit 5")

    async def test_reset_counter(self):
        """Test resetting a counter."""
        counter_key = f"{self.TEST_PREFIX}counter:reset"
        
        # Reset non-existent counter
        existed = await self.client.reset_counter(counter_key)
        self.assertFalse(existed, "Non-existent counter should return False")
        
        # Create counter
        await self.client.increment_counter_with_limit(counter_key, 10)
        
        # Reset counter
        existed = await self.client.reset_counter(counter_key)
        self.assertTrue(existed, "Existing counter should return True")
        
        # Verify counter is gone
        value = await self.client.get_counter_value(counter_key)
        self.assertEqual(value, 0, "Counter should be 0 after reset")

    async def test_increment_hash_counter(self):
        """Test incrementing counters within a hash."""
        hash_key = f"{self.TEST_PREFIX}hash:counters"
        
        # Increment different fields
        count1 = await self.client.increment_hash_counter(hash_key, "field1", 5)
        self.assertEqual(count1, 5, "field1 should be 5")
        
        count2 = await self.client.increment_hash_counter(hash_key, "field2", 3)
        self.assertEqual(count2, 3, "field2 should be 3")
        
        # Increment existing field
        count1 = await self.client.increment_hash_counter(hash_key, "field1", 2)
        self.assertEqual(count1, 7, "field1 should be 7")
        
        # Test with TTL
        ttl_hash_key = f"{self.TEST_PREFIX}hash:ttl"
        await self.client.increment_hash_counter(ttl_hash_key, "field", 1, ttl=1)
        
        # Wait for expiration
        await asyncio.sleep(2)
        values = await self.client.get_hash_counter_values(ttl_hash_key)
        self.assertEqual(values, {}, "Hash should be empty after expiration")

    async def test_get_hash_counter_values(self):
        """Test getting all counter values from a hash."""
        hash_key = f"{self.TEST_PREFIX}hash:get"
        
        # Test empty hash
        values = await self.client.get_hash_counter_values(hash_key)
        self.assertEqual(values, {}, "Empty hash should return empty dict")
        
        # Set multiple counters
        await self.client.increment_hash_counter(hash_key, "counter1", 10)
        await self.client.increment_hash_counter(hash_key, "counter2", 20)
        await self.client.increment_hash_counter(hash_key, "counter3", 30)
        
        # Get all values
        values = await self.client.get_hash_counter_values(hash_key)
        expected = {"counter1": 10, "counter2": 20, "counter3": 30}
        self.assertEqual(values, expected, "Should return all counter values")

    async def test_delete_keys_by_pattern(self):
        """Test deleting keys by pattern."""
        pattern_prefix = f"{self.TEST_PREFIX}pattern"
        
        # Create multiple keys with pattern
        keys = [
            f"{pattern_prefix}:test:1",
            f"{pattern_prefix}:test:2",
            f"{pattern_prefix}:other:1",
            f"{pattern_prefix}_different"
        ]
        
        for key in keys:
            await self.client.set_cache(key, "value")
        
        # Delete by specific pattern
        deleted = await self.client.delete_keys_by_pattern(f"{pattern_prefix}:test:*")
        self.assertEqual(deleted, 2, "Should delete 2 keys matching pattern")
        
        # Verify correct keys were deleted
        self.assertIsNone(await self.client.get_cache(f"{pattern_prefix}:test:1"))
        self.assertIsNone(await self.client.get_cache(f"{pattern_prefix}:test:2"))
        self.assertIsNotNone(await self.client.get_cache(f"{pattern_prefix}:other:1"))
        self.assertIsNotNone(await self.client.get_cache(f"{pattern_prefix}_different"))
        
        # Delete remaining keys
        deleted = await self.client.delete_keys_by_pattern(f"{pattern_prefix}*")
        self.assertEqual(deleted, 2, "Should delete remaining 2 keys")

    async def test_delete_multiple_patterns(self):
        """Test deleting keys matching multiple patterns."""
        base_prefix = f"{self.TEST_PREFIX}multi"
        
        # Create keys matching different patterns
        keys = {
            f"{base_prefix}:queue:1": "queue",
            f"{base_prefix}:queue:2": "queue",
            f"{base_prefix}:cache:1": "cache",
            f"{base_prefix}:cache:2": "cache",
            f"{base_prefix}:state:1": "state"
        }
        
        for key, value in keys.items():
            await self.client.set_cache(key, value)
        
        # Delete multiple patterns
        patterns = [
            f"{base_prefix}:queue:*",
            f"{base_prefix}:cache:*"
        ]
        
        deleted_counts = await self.client.delete_multiple_patterns(patterns)
        
        # Verify deletion counts
        self.assertEqual(deleted_counts[f"{base_prefix}:queue:*"], 2)
        self.assertEqual(deleted_counts[f"{base_prefix}:cache:*"], 2)
        
        # Verify state key is preserved
        self.assertIsNotNone(await self.client.get_cache(f"{base_prefix}:state:1"))

    async def test_counter_operations_integration(self):
        """Test integration of counter operations for domain limiting scenario."""
        domain = "example.com"
        domain_key = f"{self.TEST_PREFIX}domain:{domain}"
        limit = 5
        
        # Simulate multiple URL requests for the same domain
        allowed_count = 0
        blocked_count = 0
        
        for i in range(10):
            count, is_over = await self.client.increment_counter_with_limit(
                domain_key, increment=1, limit=limit
            )
            
            if is_over and count > limit:
                # Decrement back if over limit
                await self.client.increment_counter_with_limit(
                    domain_key, increment=-1
                )
                blocked_count += 1
            else:
                allowed_count += 1
        
        # Verify results
        self.assertEqual(allowed_count, 5, "Should allow exactly 5 URLs")
        self.assertEqual(blocked_count, 5, "Should block 5 URLs")
        
        # Final count should be at limit
        final_count = await self.client.get_counter_value(domain_key)
        self.assertEqual(final_count, limit, "Final count should be at limit")

    async def test_hash_counter_for_depth_tracking(self):
        """Test hash counter for tracking URL counts by depth."""
        depth_key = f"{self.TEST_PREFIX}depth:spider1"
        
        # Simulate crawling at different depths
        depth_distribution = {
            0: 10,  # 10 URLs at depth 0
            1: 25,  # 25 URLs at depth 1
            2: 50,  # 50 URLs at depth 2
            3: 20,  # 20 URLs at depth 3
        }
        
        # Increment counters for each depth
        for depth, count in depth_distribution.items():
            for _ in range(count):
                await self.client.increment_hash_counter(
                    depth_key, str(depth), 1
                )
        
        # Get depth statistics
        depth_stats = await self.client.get_hash_counter_values(depth_key)
        
        # Verify statistics
        for depth, expected_count in depth_distribution.items():
            self.assertEqual(
                depth_stats.get(str(depth), 0), expected_count,
                f"Depth {depth} should have {expected_count} URLs"
            )
        
        # Total URLs crawled
        total_urls = sum(depth_stats.values())
        expected_total = sum(depth_distribution.values())
        self.assertEqual(total_urls, expected_total, "Total URL count should match")


def run_tests():
    unittest.main()

if __name__ == "__main__":
    run_tests()
