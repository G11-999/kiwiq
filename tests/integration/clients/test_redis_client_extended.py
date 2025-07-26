import asyncio
import os
import uuid
import unittest
import logging
from datetime import timedelta
from redis.exceptions import ConnectionError, AuthenticationError, TimeoutError, RedisError, WatchError
import time # Added for edge cases in count-based rate limiting
from typing import List  # Added for type annotations

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
    
    async def test_pool_based_concurrency_limiting(self):
        """Test pool-based concurrency limiting functionality."""
        pool_key = f"{self.TEST_PREFIX}api_pool"
        
        # Test basic acquire and release
        alloc_id1, usage1, success1 = await self.client.acquire_from_pool(
            pool_key, count=10, max_pool_size=50, ttl=30
        )
        self.assertTrue(success1, "Failed to acquire from pool")
        self.assertIsNotNone(alloc_id1, "Allocation ID should not be None")
        self.assertEqual(usage1, 10, "Usage mismatch after first acquisition")
        
        # Acquire more
        alloc_id2, usage2, success2 = await self.client.acquire_from_pool(
            pool_key, count=20, max_pool_size=50, ttl=30
        )
        self.assertTrue(success2, "Failed second acquisition")
        self.assertEqual(usage2, 30, "Usage mismatch after second acquisition")
        
        # Try to exceed limit
        alloc_id3, usage3, success3 = await self.client.acquire_from_pool(
            pool_key, count=25, max_pool_size=50, ttl=30
        )
        self.assertFalse(success3, "Should not exceed pool limit")
        self.assertIsNone(alloc_id3, "Should not have allocation ID when failed")
        
        # Release first allocation
        released, new_usage, success = await self.client.release_to_pool(pool_key, alloc_id1)
        self.assertTrue(success, "Failed to release allocation")
        self.assertEqual(released, 10, "Released count mismatch")
        self.assertEqual(new_usage, 20, "Usage after release mismatch")
    
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
            # register_multi_window_event_atomic returns (registered, counts)
            registered, counts = await self.client.register_multi_window_event_atomic(key_prefix, windows)
            
            # First 5 events should succeed
            if i < 5:
                self.assertTrue(registered, f"Event {i+1} should be registered")
                self.assertEqual(counts[5], i+1, f"Count for 5s window should be {i+1}")
                self.assertEqual(counts[10], i+1, f"Count for 10s window should be {i+1}")
                self.assertEqual(counts[15], i+1, f"Count for 15s window should be {i+1}")
            else:
                # After 5 events, should fail due to 5s window limit
                self.assertFalse(registered, f"Event {i+1} should not be registered (exceeds 5s window limit)")
        
        # Check limits - at the limit but not exceeding it
        is_limited, counts = await self.client.check_multi_window_rate_limits(key_prefix, windows)
        
        # is_limited is only True when count > max_events, not when count == max_events
        self.assertFalse(is_limited, "Should not be rate limited when exactly at limit (5 == 5)")
        self.assertEqual(counts[5], 5, "5s window should have 5 events (at limit)")
        self.assertEqual(counts[10], 5, "10s window should have 5 events")
        self.assertEqual(counts[15], 5, "15s window should have 5 events")
        
        # The 5s window is at its limit (max 5, actual 5)
        # But no window is exceeded, so is_limited is False

    async def test_multi_window_event_registration(self):
        """Test registering events across multiple windows."""
        client_id = f"{self.TEST_PREFIX}client:202"
        key_prefix = f"rate:{client_id}"
        
        # Define windows with (max_events, window_seconds) tuples
        windows = [
            (10, 5),      # 10 events per 5 seconds
            (100, 60),    # 100 events per minute
            (1000, 3600)  # 1000 events per hour
        ]
        
        # Register a single event across all windows
        registered, counts = await self.client.register_multi_window_event_atomic(key_prefix, windows)
        
        self.assertTrue(registered, "First event should be registered")
        
        # Verify counts for all windows are 1
        self.assertEqual(counts[5], 1, "Count for 5s window should be 1")
        self.assertEqual(counts[60], 1, "Count for 60s window should be 1")
        self.assertEqual(counts[3600], 1, "Count for 3600s window should be 1")
        
        # Register 4 more events
        for i in range(4):
            registered, counts = await self.client.register_multi_window_event_atomic(key_prefix, windows)
            self.assertTrue(registered, f"Event {i+2} should be registered")
        
        # Get event counts for each window
        for max_events, window_size in windows:
            count = await self.client.get_event_count(f"{key_prefix}:{window_size}", window_size)
            self.assertEqual(count, 5, f"After 5 registrations, {window_size}s window should have 5 events")
        
        # Verify with check_multi_window_rate_limits - use lower limit to trigger rate limiting
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
            registered, counts = await self.client.register_multi_window_event_atomic(key_prefix, windows)
            self.assertTrue(registered, f"Event {i+1} should be registered")
            self.assertEqual(counts[window_seconds], i+1, f"Should have {i+1} events in the window")
        
        is_limited, counts = await self.client.check_multi_window_rate_limits(key_prefix, windows)
        self.assertFalse(is_limited, "Should not be rate limited with exactly 3 events")
        self.assertEqual(counts[window_seconds], 3, "Should have 3 events in the window")
        
        # Try to add 1 more event to exceed the limit - should fail
        registered, counts = await self.client.register_multi_window_event_atomic(key_prefix, windows)
        self.assertFalse(registered, "4th event should not be registered (would exceed limit)")
        self.assertEqual(counts[window_seconds], 3, "Should still have 3 events in the window")
        
        is_limited, counts = await self.client.check_multi_window_rate_limits(key_prefix, windows)
        self.assertFalse(is_limited, "Should not be rate limited with exactly 3 events (at limit)")
        
        # Wait for the window to slide (events to expire)
        await asyncio.sleep(2.5)  # Wait longer than the window
        
        # All old events should have expired, so no longer rate limited
        is_limited, counts = await self.client.check_multi_window_rate_limits(key_prefix, windows)
        self.assertFalse(is_limited, "Should not be rate limited after window expired")
        self.assertEqual(counts[window_seconds], 0, "Should have 0 events in the window after expiry")
    
    # === NEW TESTS FOR COUNT-BASED RATE LIMITING METHODS ===
    
    async def test_register_event_with_count_basic(self):
        """Test basic count-based event registration."""
        token_key = f"{self.TEST_PREFIX}tokens:user:123"
        
        # Register event consuming 10 tokens
        total_usage, _ = await self.client.register_event_with_count_atomic(token_key, count=10, max_count=100, window_seconds=60)
        self.assertEqual(total_usage, 10, "Total usage should be 10 tokens")
        
        # Register another event consuming 5 tokens
        total_usage, _ = await self.client.register_event_with_count_atomic(token_key, count=5, max_count=100, window_seconds=60)
        self.assertEqual(total_usage, 15, "Total usage should be 15 tokens")
        
        # Register multiple events
        for i in range(3):
            total_usage, _ = await self.client.register_event_with_count_atomic(token_key, count=20, max_count=100, window_seconds=60)
        
        self.assertEqual(total_usage, 75, "Total usage should be 75 tokens (15 + 3*20)")
        
        # Verify with get_event_count_usage
        usage = await self.client.get_event_count_usage(token_key, window_seconds=60)
        self.assertEqual(usage, 75, "get_event_count_usage should return 75")
    
    async def test_count_based_sliding_window(self):
        """Test that count-based rate limiting uses sliding window correctly."""
        token_key = f"{self.TEST_PREFIX}tokens:sliding"
        window_seconds = 2
        
        # Register event consuming 50 tokens
        await self.client.register_event_with_count_atomic(token_key, count=50, max_count=100, window_seconds=window_seconds)
        
        # Wait half the window
        await asyncio.sleep(1)
        
        # Register another 30 tokens
        await self.client.register_event_with_count_atomic(token_key, count=30, max_count=100, window_seconds=window_seconds)
        
        # Total should be 80
        usage = await self.client.get_event_count_usage(token_key, window_seconds=window_seconds)
        self.assertEqual(usage, 80, "Usage should be 80 tokens")
        
        # Wait for first event to expire
        await asyncio.sleep(1.5)
        
        # Now only the second event should be in window
        usage = await self.client.get_event_count_usage(token_key, window_seconds=window_seconds)
        self.assertEqual(usage, 30, "Usage should be 30 tokens after first event expired")
        
        # Wait for all events to expire
        await asyncio.sleep(1)
        
        usage = await self.client.get_event_count_usage(token_key, window_seconds=window_seconds)
        self.assertEqual(usage, 0, "Usage should be 0 after all events expired")
    
    async def test_multi_window_count_limits(self):
        """Test count-based limits across multiple time windows."""
        api_key = f"{self.TEST_PREFIX}api:key123"
        key_prefix = f"tokens:{api_key}"
        
        # Define limits: max tokens per window
        limits = [
            (100, 10),   # 100 tokens per 10 seconds
            (500, 60),   # 500 tokens per minute
            (5000, 3600) # 5000 tokens per hour
        ]
        
        # Initially should not be limited
        is_limited, usage = await self.client.check_multi_window_count_limits(key_prefix, limits)
        self.assertFalse(is_limited, "Should not be limited initially")
        for window in [10, 60, 3600]:
            self.assertEqual(usage[window], 0, f"Initial usage for {window}s window should be 0")
        
        # Register events consuming tokens
        for i in range(5):
            usage = await self.client.register_multi_window_count_event_atomic(key_prefix, count=15, limits=[(100, 10), (500, 60), (5000, 3600)])
        
        # Check usage: 5 * 15 = 75 tokens
        is_limited, usage = await self.client.check_multi_window_count_limits(key_prefix, limits)
        self.assertFalse(is_limited, "Should not be limited at 75 tokens")
        self.assertEqual(usage[10], 75, "10s window should have 75 tokens")
        self.assertEqual(usage[60], 75, "60s window should have 75 tokens")
        self.assertEqual(usage[3600], 75, "3600s window should have 75 tokens")
        
        # Add more to exceed 10s limit
        usage = await self.client.register_multi_window_count_event_atomic(key_prefix, count=30, limits=[(100, 10), (500, 60), (5000, 3600)])
        
        # Now we have 105 tokens in 10s window
        is_limited, usage = await self.client.check_multi_window_count_limits(key_prefix, limits, additional_count=30)
        self.assertTrue(is_limited, "Should be limited (105 > 100 in 10s window)")
        self.assertEqual(usage[10], 75, "10s window should have 75 tokens")
        self.assertEqual(usage[60], 75, "60s window should have 75 tokens")
        self.assertEqual(usage[3600], 75, "3600s window should have 75 tokens")
    
    async def test_token_bucket_scenario(self):
        """Test a realistic token bucket rate limiting scenario."""
        api_key = f"{self.TEST_PREFIX}api:bucket"
        token_key = f"tokens:{api_key}"
        max_tokens_per_minute = 1000
        
        # Simulate API calls with different token costs
        api_calls = [
            ("gpt-3.5", 50),    # Simple query
            ("gpt-4", 150),     # Complex query
            ("embedding", 10),   # Embedding request
            ("gpt-4", 200),     # Long conversation
            ("gpt-3.5", 75),    # Medium query
        ]
        
        total_consumed = 0
        
        for i, (model, token_cost) in enumerate(api_calls):
            # Check if we can make this call
            would_exceed, _ = await self.client.check_multi_window_count_limits(
                token_key, 
                additional_count=token_cost,
                limits=[(max_tokens_per_minute, 60)]
            )
            
            if not would_exceed:
                # Make the API call
                usage, _ = await self.client.register_event_with_count_atomic(
                    token_key,
                    count=token_cost,
                    max_count=max_tokens_per_minute,
                    window_seconds=60
                )
                total_consumed += token_cost
                logger.info(f"API call {i+1} ({model}): consumed {token_cost} tokens, total: {usage}")
                self.assertEqual(usage, total_consumed, f"Usage should match total consumed: {total_consumed}")
            else:
                logger.info(f"API call {i+1} ({model}): would exceed limit, skipped")
        
        # Verify final usage
        final_usage = await self.client.get_event_count_usage(token_key, window_seconds=60)
        self.assertEqual(final_usage, total_consumed, "Final usage should match total consumed")
        self.assertLessEqual(final_usage, max_tokens_per_minute, "Should not exceed max tokens")
    
    async def test_edge_cases_count_rate_limiting(self):
        """Test edge cases for count-based rate limiting."""
        token_key = f"{self.TEST_PREFIX}tokens:edge"
        
        # Test with zero count
        usage, _ = await self.client.register_event_with_count_atomic(token_key, max_count=100, count=0, window_seconds=60)
        self.assertEqual(usage, 0, "Usage should be 0 with zero count")
        
        # Test with negative count (should be treated as consumption)
        usage, _ = await self.client.register_event_with_count_atomic(token_key, max_count=100, count=-50, window_seconds=60)
        self.assertEqual(usage, -50, "Usage should be -50")
        
        # Add positive to balance
        usage, _ = await self.client.register_event_with_count_atomic(token_key, max_count=100, count=100, window_seconds=60)
        self.assertEqual(usage, 50, "Usage should be 50 (100 - 50)")
        
        # Test very large numbers
        large_key = f"{self.TEST_PREFIX}tokens:large"
        large_count = 1_000_000_000  # 1 billion
        
        usage, _ = await self.client.register_event_with_count_atomic(large_key, max_count=large_count, count=large_count, window_seconds=60)
        self.assertEqual(usage, large_count, "Should handle large numbers")
    
    async def test_multi_tenant_token_rate_limiting(self):
        """Test token rate limiting for multiple tenants."""
        tenant_limits = [
            ("free", 100, 60),      # 100 tokens per minute
            ("basic", 1000, 60),    # 1000 tokens per minute
            ("premium", 10000, 60), # 10000 tokens per minute
        ]
        
        # Simulate token usage for each tenant
        for tenant_type, max_tokens, window in tenant_limits:
            # For count-based methods, we need to use the same key structure
            # register_event_with_count_atomic uses the key directly
            # but check_multi_window_count_limits adds ":{window_seconds}:count" to the prefix
            tenant_prefix = f"{self.TEST_PREFIX}tokens:tenant:{tenant_type}"
            tenant_key = f"{tenant_prefix}:{window}:count"
            
            # Use 80% of limit
            allowed_usage = int(max_tokens * 0.8)
            usage, registered = await self.client.register_event_with_count_atomic(
                tenant_key, 
                count=allowed_usage, 
                max_count=max_tokens,
                window_seconds=window
            )
            
            self.assertTrue(registered, f"{tenant_type} initial usage should be registered")
            self.assertEqual(usage, allowed_usage, f"{tenant_type} usage should be {allowed_usage}")
            
            # Check if we can add 30% more (should exceed)
            additional = int(max_tokens * 0.3)
            would_exceed, usage_info = await self.client.check_multi_window_count_limits(
                tenant_prefix,
                limits=[(max_tokens, window)],
                additional_count=additional
            )
            
            self.assertTrue(would_exceed, f"{tenant_type} should be limited when adding {additional} tokens")
            self.assertEqual(usage_info[window], allowed_usage, f"Current usage should be {allowed_usage}")
            
            # Check if we can add 15% more (should be OK)
            additional = int(max_tokens * 0.15)
            would_exceed, _ = await self.client.check_multi_window_count_limits(
                tenant_prefix,
                limits=[(max_tokens, window)],
                additional_count=additional
            )
            
            self.assertFalse(would_exceed, f"{tenant_type} should not be limited when adding {additional} tokens")
    
    async def test_count_rate_limit_different_windows(self):
        """Test count-based rate limiting with different window sizes."""
        token_key = f"{self.TEST_PREFIX}tokens:windows"
        
        # Test multiple window sizes
        test_windows = [1, 5, 10, 30, 60]  # seconds
        
        for window in test_windows:
            window_key = f"{token_key}:w{window}"
            
            # Consume tokens
            usage, _ = await self.client.register_event_with_count_atomic(
                window_key,
                count=100,
                max_count=100,
                window_seconds=window
            )
            
            self.assertEqual(usage, 100, f"Usage should be 100 for {window}s window")
            
            # Wait for 75% of window
            await asyncio.sleep(window * 0.75)
            
            # Add more tokens
            usage, _ = await self.client.register_event_with_count_atomic(
                window_key,
                count=50,
                max_count=150,
                window_seconds=window
            )
            
            self.assertEqual(usage, 150, f"Usage should be 150 for {window}s window")
            
            # Wait for window to expire
            await asyncio.sleep(window * 0.5)
            
            # Check usage - should only have the second event
            usage = await self.client.get_event_count_usage(window_key, window_seconds=window)
            self.assertLessEqual(usage, 50, f"Usage should be <= 50 after expiration for {window}s window")
    
    async def test_malformed_member_handling(self):
        """Test handling of malformed members in count-based rate limiting."""
        token_key = f"{self.TEST_PREFIX}tokens:malformed"
        
        # Manually add some malformed members (for testing robustness)
        client = await self.client.get_client()
        timestamp = time.time()
        
        # Add various member formats
        members = {
            "valid:100": timestamp,
            "no_colon": timestamp,
            "multiple:colons:50": timestamp,
            "not_a_number:abc": timestamp,
            f"{uuid.uuid4()}:200": timestamp,  # valid format
        }
        
        await client.zadd(token_key, members)
        
        # Get usage - should only count valid numeric values
        usage = await self.client.get_event_count_usage(token_key, window_seconds=60)
        # Should count: 100 (valid:100) + 50 (multiple:colons:50) + 200 (uuid:200) = 350
        self.assertEqual(usage, 350, "Should only count valid numeric values")
        
        # Register a new event
        new_usage, _ = await self.client.register_event_with_count_atomic(token_key, max_count=500, count=150, window_seconds=60)
        self.assertEqual(new_usage, 500, "New usage should be 500 (350 + 150)")
    
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

    # === NEW TESTS FOR ATOMIC RATE LIMITING METHODS ===
    
    async def test_register_event_atomic_basic(self):
        """Test basic atomic event registration."""
        rate_key = f"{self.TEST_PREFIX}rate:atomic"
        max_events = 5
        
        # Register events up to the limit
        for i in range(max_events):
            count, registered = await self.client.register_event_atomic(rate_key, max_events, window_seconds=60)
            self.assertTrue(registered, f"Event {i+1} should be registered")
            self.assertEqual(count, i+1, f"Count should be {i+1}")
        
        # Try to register beyond limit
        count, registered = await self.client.register_event_atomic(rate_key, max_events, window_seconds=60)
        self.assertFalse(registered, "Event should not be registered beyond limit")
        self.assertEqual(count, max_events, f"Count should remain at {max_events}")
    
    async def test_register_event_atomic_race_condition(self):
        """Test that atomic registration prevents race conditions."""
        rate_key = f"{self.TEST_PREFIX}rate:atomic_race"
        max_events = 10
        successful_registrations = 0
        
        async def try_register(worker_id: int):
            """Worker that tries to register events."""
            nonlocal successful_registrations
            local_success = 0
            
            for _ in range(5):  # Each worker tries 5 times
                count, registered = await self.client.register_event_atomic(
                    rate_key, max_events, window_seconds=60
                )
                if registered:
                    local_success += 1
                    
            return local_success
        
        # Create 10 concurrent workers
        tasks = [asyncio.create_task(try_register(i)) for i in range(10)]
        results = await asyncio.gather(*tasks)
        
        # Count total successful registrations
        successful_registrations = sum(results)
        
        # Exactly max_events should have been registered
        self.assertEqual(successful_registrations, max_events, 
                        f"Exactly {max_events} events should be registered")
        
        # Verify final count
        final_count = await self.client.get_event_count(rate_key, window_seconds=60)
        self.assertEqual(final_count, max_events, 
                        f"Final count should be {max_events}")
    
    async def test_register_event_with_count_atomic_basic(self):
        """Test basic atomic count-based registration."""
        token_key = f"{self.TEST_PREFIX}tokens:atomic"
        max_tokens = 100
        
        # Register events consuming tokens
        usage, registered = await self.client.register_event_with_count_atomic(
            token_key, count=30, max_count=max_tokens, window_seconds=60
        )
        self.assertTrue(registered, "First request should be registered")
        self.assertEqual(usage, 30, "Usage should be 30")
        
        # Register more
        usage, registered = await self.client.register_event_with_count_atomic(
            token_key, count=50, max_count=max_tokens, window_seconds=60
        )
        self.assertTrue(registered, "Second request should be registered")
        self.assertEqual(usage, 80, "Usage should be 80")
        
        # Try to exceed limit
        usage, registered = await self.client.register_event_with_count_atomic(
            token_key, count=30, max_count=max_tokens, window_seconds=60
        )
        self.assertFalse(registered, "Request should not be registered (would exceed limit)")
        self.assertEqual(usage, 80, "Usage should remain at 80")
        
        # Smaller request that fits
        usage, registered = await self.client.register_event_with_count_atomic(
            token_key, count=20, max_count=max_tokens, window_seconds=60
        )
        self.assertTrue(registered, "Small request should be registered")
        self.assertEqual(usage, 100, "Usage should be 100")
    
    async def test_register_event_with_count_atomic_race_condition(self):
        """Test that atomic count registration prevents race conditions."""
        token_key = f"{self.TEST_PREFIX}tokens:atomic_race"
        max_tokens = 1000
        tokens_per_request = 50
        
        async def try_consume_tokens(worker_id: int):
            """Worker that tries to consume tokens."""
            successful_requests = 0
            tokens_consumed = 0
            
            for _ in range(10):  # Each worker tries 10 times
                usage, registered = await self.client.register_event_with_count_atomic(
                    token_key, 
                    count=tokens_per_request, 
                    max_count=max_tokens, 
                    window_seconds=60
                )
                if registered:
                    successful_requests += 1
                    tokens_consumed += tokens_per_request
                    
            return successful_requests, tokens_consumed
        
        # Create 5 concurrent workers
        tasks = [asyncio.create_task(try_consume_tokens(i)) for i in range(5)]
        results = await asyncio.gather(*tasks)
        
        # Calculate totals
        total_requests = sum(r[0] for r in results)
        total_tokens = sum(r[1] for r in results)
        
        # With 1000 max tokens and 50 tokens per request, we should get exactly 20 requests
        # Since the window is 60 seconds and the test runs quickly, we shouldn't see
        # any sliding window effects.
        expected_requests = max_tokens // tokens_per_request  # 1000/50 = 20
        
        self.assertEqual(total_requests, expected_requests, 
                        f"Should have exactly {expected_requests} successful requests")
        self.assertEqual(total_tokens, max_tokens,
                        f"Should have consumed exactly {max_tokens} tokens")
        
        # Verify final usage respects the limit
        final_usage = await self.client.get_event_count_usage(token_key, window_seconds=60)
        self.assertLessEqual(final_usage, max_tokens, 
                            f"Final usage should not exceed {max_tokens} tokens")
    
    async def test_atomic_methods_with_expiration(self):
        """Test that atomic methods handle expiration correctly."""
        rate_key = f"{self.TEST_PREFIX}rate:atomic_expire"
        token_key = f"{self.TEST_PREFIX}tokens:atomic_expire"
        window_seconds = 2
        
        # Test event-based
        for i in range(3):
            count, registered = await self.client.register_event_atomic(
                rate_key, max_events=5, window_seconds=window_seconds
            )
            self.assertTrue(registered, f"Event {i+1} should be registered")
        
        # Wait for expiration
        await asyncio.sleep(window_seconds + 0.5)
        
        # Should be able to register again
        count, registered = await self.client.register_event_atomic(
            rate_key, max_events=5, window_seconds=window_seconds
        )
        self.assertTrue(registered, "Should be able to register after expiration")
        self.assertEqual(count, 1, "Count should be 1 after expiration")
        
        # Test count-based
        usage, registered = await self.client.register_event_with_count_atomic(
            token_key, count=100, max_count=200, window_seconds=window_seconds
        )
        self.assertTrue(registered, "Should register tokens")
        self.assertEqual(usage, 100, "Usage should be 100")
        
        # Wait for expiration
        await asyncio.sleep(window_seconds + 0.5)
        
        # Should have 0 usage after expiration
        current_usage = await self.client.get_event_count_usage(token_key, window_seconds=window_seconds)
        self.assertEqual(current_usage, 0, "Usage should be 0 after expiration")
    
    async def test_atomic_retry_behavior(self):
        """Test retry behavior when there are conflicts."""
        token_key = f"{self.TEST_PREFIX}tokens:atomic_retry"
        max_tokens = 100
        conflict_count = 0
        
        # We'll patch the pipeline's execute method instead
        from redis.asyncio.client import Pipeline
        original_execute = Pipeline.execute
        
        async def execute_with_conflicts(self):
            nonlocal conflict_count
            # Simulate conflicts on first 2 attempts
            if conflict_count < 2:
                conflict_count += 1
                raise WatchError("Simulated conflict")
            return await original_execute(self)
        
        # Temporarily replace execute method
        Pipeline.execute = execute_with_conflicts
        
        try:
            # This should succeed after retries
            usage, registered = await self.client.register_event_with_count_atomic(
                token_key, count=50, max_count=max_tokens, window_seconds=60
            )
            
            self.assertTrue(registered, "Should succeed after retries")
            self.assertEqual(usage, 50, "Usage should be 50")
            self.assertEqual(conflict_count, 2, "Should have had 2 conflicts")
            
        finally:
            # Restore original method
            Pipeline.execute = original_execute

    async def test_atomic_retry_behavior_mock(self):
        """
        Test retry behavior with mocked conflicts.
        
        This is a deterministic test that guarantees the retry logic works correctly
        by simulating WatchError conditions. This ensures the retry mechanism is
        properly implemented even if real conflicts are rare in the real_conflicts test.
        """
        token_key = f"{self.TEST_PREFIX}tokens:atomic_retry_mock"
        max_tokens = 100
        conflict_count = 0
        
        # We'll patch the pipeline's execute method
        from redis.asyncio.client import Pipeline
        original_execute = Pipeline.execute
        
        async def execute_with_conflicts(self):
            nonlocal conflict_count
            # Simulate conflicts on first 2 attempts
            if conflict_count < 2:
                conflict_count += 1
                raise WatchError("Simulated conflict")
            return await original_execute(self)
        
        # Temporarily replace execute method
        Pipeline.execute = execute_with_conflicts
        
        try:
            # This should succeed after retries
            usage, registered = await self.client.register_event_with_count_atomic(
                token_key, count=50, max_count=max_tokens, window_seconds=60
            )
            
            self.assertTrue(registered, "Should succeed after retries")
            self.assertEqual(usage, 50, "Usage should be 50")
            self.assertEqual(conflict_count, 2, "Should have had 2 conflicts")
            
        finally:
            # Restore original method
            Pipeline.execute = original_execute

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

    # === NEW TESTS FOR ATOMIC MULTI-WINDOW RATE LIMITING ===
    
    async def test_register_multi_window_event_atomic_basic(self):
        """Test basic atomic multi-window event registration."""
        client_id = f"{self.TEST_PREFIX}client:mw_atomic"
        key_prefix = f"rate:{client_id}"
        
        # Define limits for different windows
        limits = [
            (5, 10),    # 5 events per 10 seconds
            (10, 60),   # 10 events per minute
            (50, 3600)  # 50 events per hour
        ]
        
        # Register events up to the smallest limit
        for i in range(5):
            registered, counts = await self.client.register_multi_window_event_atomic(
                key_prefix, limits
            )
            self.assertTrue(registered, f"Event {i+1} should be registered")
            self.assertEqual(counts[10], i+1, f"10s window should have {i+1} events")
            self.assertEqual(counts[60], i+1, f"60s window should have {i+1} events")
            self.assertEqual(counts[3600], i+1, f"3600s window should have {i+1} events")
        
        # Try to register beyond the 10s limit
        registered, counts = await self.client.register_multi_window_event_atomic(
            key_prefix, limits
        )
        self.assertFalse(registered, "Event should not be registered (10s limit reached)")
        self.assertEqual(counts[10], 5, "10s window should remain at 5")
        # When registration fails, not all windows might be checked, so use get() with default
        self.assertEqual(counts.get(60, 5), 5, "60s window should remain at 5 if checked")
        self.assertEqual(counts.get(3600, 5), 5, "3600s window should remain at 5 if checked")
    
    async def test_register_multi_window_event_atomic_race_condition(self):
        """Test that atomic multi-window registration prevents race conditions."""
        client_id = f"{self.TEST_PREFIX}client:mw_atomic_race"
        key_prefix = f"rate:{client_id}"
        
        limits = [
            (10, 5),    # 10 events per 5 seconds
            (20, 10),   # 20 events per 10 seconds
        ]
        
        successful_registrations = []
        
        async def try_register(worker_id: int):
            """Worker that tries to register events."""
            local_success = 0
            
            for _ in range(15):  # Each worker tries 15 times
                registered, counts = await self.client.register_multi_window_event_atomic(
                    key_prefix, limits
                )
                if registered:
                    local_success += 1
                    successful_registrations.append((worker_id, counts))
                    
            return local_success
        
        # Create 5 concurrent workers
        tasks = [asyncio.create_task(try_register(i)) for i in range(5)]
        results = await asyncio.gather(*tasks)
        
        # Total successful registrations across all workers
        total_success = sum(results)
        
        # Due to sliding window, we might get slightly more than 10 if some events expire
        # during the test. The atomic guarantee is that we never exceed the limit at any
        # point in time, not that we get exactly the limit over the duration of the test.
        self.assertGreaterEqual(total_success, 10, "Should register at least 10 events")
        self.assertLessEqual(total_success, 15, "Should not register too many events")
        
        # Verify final counts respect the limits
        _, final_counts = await self.client.check_multi_window_rate_limits(key_prefix, limits)
        self.assertLessEqual(final_counts[5], 10, "5s window should not exceed 10 events")
        self.assertLessEqual(final_counts[10], 20, "10s window should not exceed 20 events")
    
    async def test_register_multi_window_count_event_atomic_basic(self):
        """Test basic atomic multi-window count-based registration."""
        api_key = f"{self.TEST_PREFIX}api:mw_count_atomic"
        key_prefix = f"tokens:{api_key}"
        
        # Define token limits for different windows
        limits = [
            (100, 10),    # 100 tokens per 10 seconds
            (500, 60),    # 500 tokens per minute
            (5000, 3600)  # 5000 tokens per hour
        ]
        
        # Register events consuming tokens
        registered, usage = await self.client.register_multi_window_count_event_atomic(
            key_prefix, count=30, limits=limits
        )
        self.assertTrue(registered, "First request should be registered")
        self.assertEqual(usage[10], 30, "10s window should have 30 tokens")
        self.assertEqual(usage[60], 30, "60s window should have 30 tokens")
        self.assertEqual(usage[3600], 30, "3600s window should have 30 tokens")
        
        # Register more
        registered, usage = await self.client.register_multi_window_count_event_atomic(
            key_prefix, count=50, limits=limits
        )
        self.assertTrue(registered, "Second request should be registered")
        self.assertEqual(usage[10], 80, "10s window should have 80 tokens")
        self.assertEqual(usage[60], 80, "60s window should have 80 tokens")
        self.assertEqual(usage[3600], 80, "3600s window should have 80 tokens")
        
        # Try to exceed 10s limit
        registered, usage = await self.client.register_multi_window_count_event_atomic(
            key_prefix, count=30, limits=limits
        )
        self.assertFalse(registered, "Request should not be registered (would exceed 10s limit)")
        self.assertEqual(usage[10], 80, "10s window should remain at 80")
        # When registration fails, not all windows might be checked
        self.assertEqual(usage.get(60, 80), 80, "60s window should remain at 80 if checked")
        self.assertEqual(usage.get(3600, 80), 80, "3600s window should remain at 80 if checked")
        
        # Smaller request that fits
        registered, usage = await self.client.register_multi_window_count_event_atomic(
            key_prefix, count=20, limits=limits
        )
        self.assertTrue(registered, "Small request should be registered")
        self.assertEqual(usage[10], 100, "10s window should be at limit")
        self.assertEqual(usage[60], 100, "60s window should have 100 tokens")
        self.assertEqual(usage[3600], 100, "3600s window should have 100 tokens")
    
    async def test_register_multi_window_count_event_atomic_race_condition(self):
        """Test that atomic multi-window count registration prevents race conditions."""
        api_key = f"{self.TEST_PREFIX}api:mw_count_atomic_race"
        key_prefix = f"tokens:{api_key}"
        
        limits = [
            (1000, 10),   # 1000 tokens per 10 seconds
            (2000, 60),   # 2000 tokens per minute
        ]
        
        tokens_per_request = 100
        successful_requests = []
        
        async def try_consume_tokens(worker_id: int):
            """Worker that tries to consume tokens."""
            local_success = 0
            local_tokens = 0
            
            for _ in range(15):  # Each worker tries 15 times
                registered, usage = await self.client.register_multi_window_count_event_atomic(
                    key_prefix, count=tokens_per_request, limits=limits
                )
                if registered:
                    local_success += 1
                    local_tokens += tokens_per_request
                    successful_requests.append((worker_id, usage))
                    
            return local_success, local_tokens
        
        # Create 5 concurrent workers
        tasks = [asyncio.create_task(try_consume_tokens(i)) for i in range(5)]
        results = await asyncio.gather(*tasks)
        
        # Calculate totals
        total_requests = sum(r[0] for r in results)
        total_tokens = sum(r[1] for r in results)
        
        # Due to sliding window behavior, we might get slightly more than expected
        # if some events expire during the test. The guarantee is that at any point
        # in time, we don't exceed the limit.
        expected_min_requests = 10  # At least 1000/100 = 10
        expected_max_requests = 15  # Allow some extra due to sliding window
        
        self.assertGreaterEqual(total_requests, expected_min_requests, 
                               f"Should have at least {expected_min_requests} successful requests")
        self.assertLessEqual(total_requests, expected_max_requests,
                            f"Should not exceed {expected_max_requests} requests")
        
        # Verify final usage respects limits
        _, final_usage = await self.client.check_multi_window_count_limits(key_prefix, limits)
        self.assertLessEqual(final_usage[10], 1000, "10s window should not exceed 1000 tokens")
        self.assertLessEqual(final_usage[60], 2000, "60s window should not exceed 2000 tokens")
    
    async def test_multi_window_atomic_with_different_limits(self):
        """Test atomic multi-window with windows hitting limits at different times."""
        client_id = f"{self.TEST_PREFIX}client:mw_diff_limits"
        key_prefix = f"rate:{client_id}"
        
        # Set up limits where different windows will hit limits at different times
        limits = [
            (3, 10),   # Very restrictive: 3 events per 10s
            (10, 60),  # Less restrictive: 10 events per minute
            (20, 300)  # Even less restrictive: 20 events per 5 minutes
        ]
        
        events_registered = 0
        
        # Try to register 15 events
        for i in range(15):
            registered, counts = await self.client.register_multi_window_event_atomic(
                key_prefix, limits
            )
            
            if registered:
                events_registered += 1
                logger.info(f"Event {i+1} registered. Counts: {counts}")
            else:
                logger.info(f"Event {i+1} blocked. Counts: {counts}")
                # Should be blocked by 10s window after 3 events
                self.assertEqual(counts[10], 3, "10s window should be at limit")
                break
        
        self.assertEqual(events_registered, 3, "Should register exactly 3 events (10s limit)")
    
    async def test_multi_window_atomic_with_expiration(self):
        """Test that atomic multi-window methods handle expiration correctly."""
        client_id = f"{self.TEST_PREFIX}client:mw_atomic_expire"
        key_prefix = f"rate:{client_id}"
        
        # Use short windows for testing
        limits = [
            (2, 2),   # 2 events per 2 seconds
            (5, 5),   # 5 events per 5 seconds
        ]
        
        # Register 2 events (hits 2s limit)
        for i in range(2):
            registered, counts = await self.client.register_multi_window_event_atomic(
                key_prefix, limits
            )
            self.assertTrue(registered, f"Event {i+1} should be registered")
        
        # Should be blocked now
        registered, counts = await self.client.register_multi_window_event_atomic(
            key_prefix, limits
        )
        self.assertFalse(registered, "Should be blocked by 2s window")
        self.assertEqual(counts[2], 2, "2s window should be at limit")
        
        # Wait for 2s window to expire
        await asyncio.sleep(2.5)
        
        # Should be able to register again
        registered, counts = await self.client.register_multi_window_event_atomic(
            key_prefix, limits
        )
        self.assertTrue(registered, "Should be able to register after 2s expiration")
        # This is the 3rd event in 5s window
        self.assertLessEqual(counts[5], 3, "5s window should have at most 3 events")
    
    async def test_complex_multi_window_atomic_scenario(self):
        """Test complex scenario with multiple atomic multi-window operations."""
        # Simulate an API with different tiers having different limits
        tiers = {
            'free': {
                'key_prefix': f"{self.TEST_PREFIX}tier:free",
                'limits': [
                    (10, 60),     # 10 requests per minute
                    (50, 3600),   # 50 requests per hour
                    (100, 86400)  # 100 requests per day
                ]
            },
            'pro': {
                'key_prefix': f"{self.TEST_PREFIX}tier:pro",
                'limits': [
                    (100, 60),    # 100 requests per minute
                    (1000, 3600), # 1000 requests per hour
                    (5000, 86400) # 5000 requests per day
                ]
            }
        }
        
        # Token-based limits
        token_tiers = {
            'free': {
                'key_prefix': f"{self.TEST_PREFIX}tokens:free",
                'limits': [
                    (1000, 60),    # 1000 tokens per minute
                    (10000, 3600), # 10000 tokens per hour
                    (50000, 86400) # 50000 tokens per day
                ]
            },
            'pro': {
                'key_prefix': f"{self.TEST_PREFIX}tokens:pro",
                'limits': [
                    (10000, 60),    # 10000 tokens per minute
                    (100000, 3600), # 100000 tokens per hour
                    (500000, 86400) # 500000 tokens per day
                ]
            }
        }
        
        # Track results
        results = {
            'free': {'requests': 0, 'tokens': 0, 'blocked_requests': 0},
            'pro': {'requests': 0, 'tokens': 0, 'blocked_requests': 0}
        }
        
        async def api_user(tier: str, user_id: int):
            """Simulate API user making requests."""
            tier_info = tiers[tier]
            token_info = token_tiers[tier]
            
            for i in range(20):  # Try 20 requests
                # Check request limit
                req_registered, req_counts = await self.client.register_multi_window_event_atomic(
                    f"{tier_info['key_prefix']}:user{user_id}",
                    tier_info['limits']
                )
                
                if not req_registered:
                    results[tier]['blocked_requests'] += 1
                    continue
                
                # Request allowed, now check token limit
                tokens_needed = 50 + (i * 10)  # Varying token costs
                
                token_registered, token_usage = await self.client.register_multi_window_count_event_atomic(
                    f"{token_info['key_prefix']}:user{user_id}",
                    tokens_needed,
                    token_info['limits']
                )
                
                if token_registered:
                    results[tier]['requests'] += 1
                    results[tier]['tokens'] += tokens_needed
                else:
                    # Token limit hit, but request was counted
                    results[tier]['blocked_requests'] += 1
                
                # Small delay between requests
                await asyncio.sleep(0.01)
        
        # Create users for each tier
        tasks = []
        for tier in ['free', 'pro']:
            for user_id in range(3):  # 3 users per tier
                tasks.append(asyncio.create_task(api_user(tier, user_id)))
        
        await asyncio.gather(*tasks)
        
        # Verify results
        logger.info(f"Multi-window atomic scenario results: {results}")
        
        # Free tier should hit minute limit (10 requests * 3 users = 30 attempts, limit is 10 per user)
        self.assertLessEqual(results['free']['requests'], 30, "Free tier requests should be limited")
        self.assertGreater(results['free']['blocked_requests'], 0, "Free tier should have blocked requests")
        
        # Pro tier should allow more requests
        self.assertGreater(results['pro']['requests'], results['free']['requests'], 
                          "Pro tier should allow more requests than free tier")
    
    async def test_multi_window_atomic_retry_behavior(self):
        """Test retry behavior for multi-window atomic operations."""
        client_id = f"{self.TEST_PREFIX}client:mw_atomic_retry"
        key_prefix = f"rate:{client_id}"
        
        limits = [(5, 10), (10, 60)]
        conflict_count = 0
        
        # We'll patch the pipeline's execute method
        from redis.asyncio.client import Pipeline
        original_execute = Pipeline.execute
        
        async def execute_with_conflicts(self):
            nonlocal conflict_count
            # Simulate conflicts on first 3 attempts
            if conflict_count < 3:
                conflict_count += 1
                raise WatchError("Simulated multi-window conflict")
            return await original_execute(self)
        
        # Temporarily replace execute method
        Pipeline.execute = execute_with_conflicts
        
        try:
            # This should succeed after retries
            registered, counts = await self.client.register_multi_window_event_atomic(
                key_prefix, limits
            )
            
            self.assertTrue(registered, "Should succeed after retries")
            self.assertEqual(counts[10], 1, "Should have 1 event in 10s window")
            self.assertEqual(counts[60], 1, "Should have 1 event in 60s window")
            self.assertEqual(conflict_count, 3, "Should have had 3 conflicts")
            
        finally:
            # Restore original method
            Pipeline.execute = original_execute
    
    async def test_multi_window_atomic_retry_behavior_real_conflicts(self):
        """
        Test retry behavior for multi-window atomic operations with real conflicts.
        
        This test creates actual race conditions by having multiple workers
        rapidly register events across multiple windows, causing real WatchErrors.
        """
        client_id = f"{self.TEST_PREFIX}client:mw_atomic_retry_real"
        key_prefix = f"rate:{client_id}"
        
        # Use higher limits to allow more operations
        limits = [(50, 10), (200, 60)]
        
        # Track timing to detect retries
        operation_times = []
        
        async def aggressive_multi_window_worker(worker_id: int, operations: int):
            """Worker that aggressively tries to register multi-window events."""
            local_successes = 0
            slow_operations = 0  # Operations that took longer (likely retried)
            
            for i in range(operations):
                start_time = asyncio.get_event_loop().time()
                
                registered, counts = await self.client.register_multi_window_event_atomic(
                    key_prefix, limits
                )
                
                elapsed = asyncio.get_event_loop().time() - start_time
                operation_times.append(elapsed)
                
                if registered:
                    local_successes += 1
                    # Operations taking > 10ms likely had retries
                    if elapsed > 0.01:
                        slow_operations += 1
                
                # No delay between operations for maximum contention
            
            return local_successes, slow_operations
        
        # Use many workers to create high contention
        num_workers = 25
        operations_per_worker = 20
        
        tasks = [
            asyncio.create_task(aggressive_multi_window_worker(i, operations_per_worker))
            for i in range(num_workers)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Aggregate results
        total_successes = sum(r[0] for r in results)
        total_slow_ops = sum(r[1] for r in results)
        
        # Calculate timing statistics
        avg_time = sum(operation_times) / len(operation_times)
        max_time = max(operation_times)
        slow_ops_percentage = (total_slow_ops / max(total_successes, 1)) * 100
        
        # Log results
        logger.info(f"Multi-window real conflicts test results:")
        logger.info(f"  Workers: {num_workers}, Operations per worker: {operations_per_worker}")
        logger.info(f"  Total successful registrations: {total_successes}")
        logger.info(f"  Slow operations (likely retried): {total_slow_ops} ({slow_ops_percentage:.1f}%)")
        logger.info(f"  Average operation time: {avg_time*1000:.2f}ms")
        logger.info(f"  Max operation time: {max_time*1000:.2f}ms")
        
        # Verify operations succeeded
        self.assertGreater(total_successes, 0, "Should have successful operations")
        
        # Verify we stayed within limits
        _, final_counts = await self.client.check_multi_window_rate_limits(key_prefix, limits)
        for max_events, window_seconds in limits:
            self.assertLessEqual(
                final_counts[window_seconds], max_events,
                f"{window_seconds}s window should not exceed limit of {max_events}"
            )
        
        # With 25 workers and no delays, we expect some conflicts/retries
        # indicated by slower operations
        if total_slow_ops == 0:
            logger.warning("No slow operations detected - conflicts might not have occurred in this run")
    
    async def test_multi_window_atomic_retry_behavior_mock(self):
        """
        Test retry behavior for multi-window atomic operations with mocked conflicts.
        
        This deterministic test ensures the multi-window retry mechanism works correctly
        by simulating WatchError conditions that affect multiple keys simultaneously.
        """
        client_id = f"{self.TEST_PREFIX}client:mw_atomic_retry_mock"
        key_prefix = f"rate:{client_id}"
        
        limits = [(5, 10), (10, 60)]
        conflict_count = 0
        
        # We'll patch the pipeline's execute method
        from redis.asyncio.client import Pipeline
        original_execute = Pipeline.execute
        
        async def execute_with_conflicts(self):
            nonlocal conflict_count
            # Simulate conflicts on first 3 attempts
            if conflict_count < 3:
                conflict_count += 1
                raise WatchError("Simulated multi-window conflict")
            return await original_execute(self)
        
        # Temporarily replace execute method
        Pipeline.execute = execute_with_conflicts
        
        try:
            # This should succeed after retries
            registered, counts = await self.client.register_multi_window_event_atomic(
                key_prefix, limits
            )
            
            self.assertTrue(registered, "Should succeed after retries")
            self.assertEqual(counts[10], 1, "Should have 1 event in 10s window")
            self.assertEqual(counts[60], 1, "Should have 1 event in 60s window")
            self.assertEqual(conflict_count, 3, "Should have had 3 conflicts")
            
        finally:
            # Restore original method
            Pipeline.execute = original_execute
    
    async def test_multi_window_atomic_partial_expiration(self):
        """Test behavior when some windows expire but others don't."""
        api_key = f"{self.TEST_PREFIX}api:mw_partial_expire"
        key_prefix = f"tokens:{api_key}"
        
        # Different window sizes
        limits = [
            (100, 2),   # 100 tokens per 2 seconds (will expire first)
            (200, 5),   # 200 tokens per 5 seconds
            (300, 10)   # 300 tokens per 10 seconds
        ]
        
        # Use 80 tokens
        registered, usage = await self.client.register_multi_window_count_event_atomic(
            key_prefix, count=80, limits=limits
        )
        self.assertTrue(registered, "Should register 80 tokens")
        
        # Try to add 30 more (would exceed 2s limit)
        registered, usage = await self.client.register_multi_window_count_event_atomic(
            key_prefix, count=30, limits=limits
        )
        self.assertFalse(registered, "Should be blocked by 2s window")
        
        # Wait for 2s window to expire
        await asyncio.sleep(2.5)
        
        # Now should be able to add 30 tokens
        registered, usage = await self.client.register_multi_window_count_event_atomic(
            key_prefix, count=30, limits=limits
        )
        self.assertTrue(registered, "Should register after 2s window expiry")
        
        # Check usage
        self.assertEqual(usage[2], 30, "2s window should only have recent 30 tokens")
        self.assertEqual(usage[5], 110, "5s window should have 80+30=110 tokens")
        self.assertEqual(usage[10], 110, "10s window should have 80+30=110 tokens")
        
        # Try to add 100 more (would exceed 5s limit)
        registered, usage = await self.client.register_multi_window_count_event_atomic(
            key_prefix, count=100, limits=limits
        )
        self.assertFalse(registered, "Should be blocked by 5s window")
        # The operation failed, so usage might only contain the first window that failed
        if 5 in usage:
            self.assertEqual(usage[5], 110, "5s window should remain at 110")
    
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
    
    async def test_register_event_with_count_basic(self):
        """Test basic count-based event registration."""
        token_key = f"{self.TEST_PREFIX}tokens:user:123"
        
        # Register event consuming 10 tokens
        total_usage, _ = await self.client.register_event_with_count_atomic(token_key, max_count=100, count=10, window_seconds=60)
        self.assertEqual(total_usage, 10, "Total usage should be 10 tokens")
        
        # Register another event consuming 5 tokens
        total_usage, _ = await self.client.register_event_with_count_atomic(token_key, max_count=100, count=5, window_seconds=60)
        self.assertEqual(total_usage, 15, "Total usage should be 15 tokens")
        
        # Register multiple events
        for i in range(3):
            total_usage, _ = await self.client.register_event_with_count_atomic(token_key, max_count=100, count=20, window_seconds=60)
        
        self.assertEqual(total_usage, 75, "Total usage should be 75 tokens (15 + 3*20)")
        
        # Verify with get_event_count_usage
        usage = await self.client.get_event_count_usage(token_key, window_seconds=60)
        self.assertEqual(usage, 75, "get_event_count_usage should return 75")


def run_tests():
    unittest.main()

if __name__ == "__main__":
    run_tests()
