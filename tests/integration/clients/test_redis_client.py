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


def run_tests():
    unittest.main()

if __name__ == "__main__":
    run_tests()
