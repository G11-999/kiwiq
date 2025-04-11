import traceback
import redis.asyncio as redis
import asyncio
import time
import uuid
import json
import logging
from typing import Any, Dict, List, Optional, Union, Callable, TypeVar, Generic, Tuple
from datetime import timedelta
from contextlib import asynccontextmanager
from urllib.parse import urlparse, urlunparse
from redis.exceptions import ConnectionError, AuthenticationError, TimeoutError, ResponseError, RedisError

# Configure logging
from global_config.logger import get_logger
logger = get_logger(__name__)

T = TypeVar('T')

class AsyncRedisClient:
    """
    Asynchronous Redis client wrapper for rate limiting, caching, and distributed locking
    using redis-py's asyncio interface and connection pooling.
    
    Features:
    - Connection Pooling with lazy initialization
    - Rate Limiting with sliding window
    - Key-Value Caching with TTL support
    - Distributed Locking mechanism
    - Health check functionality
    """
    
    def __init__(
        self, 
        redis_url: str = "redis://localhost:6379/0", 
        pool_size: int = 50,
        default_ttl_seconds: int = 3600,
        socket_connect_timeout: float = 5.0,
        decode_responses: bool = True,
    ):
        """
        Initialize Redis client with connection pool configuration.
        
        Args:
            redis_url: Redis connection URL (e.g., "redis://default:password@host:port/db")
            pool_size: Maximum number of connections in the pool
            default_ttl_seconds: Default TTL for cache entries in seconds
            socket_connect_timeout: Socket connection timeout in seconds
            decode_responses: Whether to decode responses from Redis
        """
        if not redis_url:
            raise ValueError("Redis URL cannot be empty.")
            
        self.redis_url = redis_url
        self.pool_size = pool_size
        self.default_ttl = timedelta(seconds=default_ttl_seconds)
        self.socket_connect_timeout = socket_connect_timeout
        self._pool: Optional[redis.ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._decode_responses = decode_responses  # For simpler key/value handling
        
        logger.info(f"Redis client configured. Target URL (credentials masked): {self._mask_url_password(redis_url)}")
        logger.debug(f"Redis client configured with pool size {pool_size}")
    
    def _mask_url_password(self, url: str) -> str:
        """Helper to mask password in URL for safe logging."""
        try:
            parsed = urlparse(url)
            if parsed.password:
                user_part = f"{parsed.username or 'default'}:*****@"
                new_netloc = f"{user_part}{parsed.hostname}"
                if parsed.port:
                    new_netloc += f":{parsed.port}"
                masked_parts = list(parsed)
                masked_parts[1] = new_netloc
                return urlunparse(masked_parts)
            else:
                return url
        except Exception:
            return "Error masking URL"
    
    def _get_pool(self) -> redis.ConnectionPool:
        """Lazily creates and returns the connection pool."""
        if self._pool is None:
            logger.info(f"Creating connection pool for URL: {self._mask_url_password(self.redis_url)}")
            try:
                self._pool = redis.ConnectionPool.from_url(
                    self.redis_url,
                    max_connections=self.pool_size,
                    decode_responses=self._decode_responses,
                    socket_connect_timeout=self.socket_connect_timeout,
                    socket_keepalive=True,  # Enable keepalive
                )
            except (RedisError, ValueError) as e:
                logger.error(f"Failed to create connection pool: {e}")
                raise ConnectionError(f"Failed to create connection pool: {e}") from e
        return self._pool
    
    async def get_client(self) -> redis.Redis:
        """
        Lazily creates and returns a client instance from the pool.
        Performs a PING check on first creation to ensure basic connectivity.
        """
        if self._client is None:
            logger.info("Client not initialized. Creating client from pool.")
            pool = self._get_pool()  # Get or create pool
            try:
                self._client = redis.Redis(connection_pool=pool)
                # Perform an initial ping check when client is first created
                logger.debug("Performing initial PING check...")
                if not await self.ping():
                    # Cleanup if initial ping fails
                    await self._cleanup_connection()
                    raise ConnectionError("Initial PING check failed after creating client.")
                logger.info("Client created and initial PING successful.")
            except (AuthenticationError, ConnectionError, TimeoutError, RedisError) as e:
                logger.error(f"Failed to create client or initial ping failed: {e}")
                await self._cleanup_connection()  # Ensure cleanup on error
                raise ConnectionError(f"Failed to create client or initial ping failed: {e}") from e
            except Exception as e:
                logger.error(f"Unexpected error creating client: {e}", exc_info=True)
                await self._cleanup_connection()
                raise ConnectionError(f"Unexpected error creating client: {e}") from e
        
        return self._client
    
    async def ping(self) -> bool:
        """
        Checks connectivity to Redis using the PING command.
        
        Returns:
            True if PING is successful, False otherwise
        """
        try:
            # Get client instance (handles connection/creation)
            client = await self.get_client()
            # ping() returns True on success
            result = await client.ping()
            logger.debug(f"Ping result: {result}")
            return result
        except AuthenticationError:
            logger.warning("Ping failed: Authentication Error.")
            return False
        except (ConnectionError, TimeoutError):
            logger.warning("Ping failed: Connection or Timeout Error.")
            return False
        except RedisError as e:
            logger.error(f"Ping failed: RedisError: {e}")
            return False
        except Exception as e:
            logger.error(f"Ping failed: Unexpected error: {e}", exc_info=True)
            return False
    
    async def close(self) -> None:
        """Closes the Redis connection pool gracefully."""
        logger.info("Closing Redis connection...")
        await self._cleanup_connection()
        logger.info("Redis client closed.")
    
    async def _cleanup_connection(self) -> None:
        """Safely closes pool and resets client state."""
        logger.debug("Cleaning up Redis connection state...")
        pool = self._pool
        client = self._client  # Local ref for potential client-specific cleanup
        self._client = None
        self._pool = None
        
        if client:
            try:
                await client.aclose()  # Explicitly close client instance
            except Exception:
                logger.exception("Error closing client instance during cleanup.")
        
        if pool:
            try:
                await pool.disconnect()
                logger.debug("Connection pool disconnected.")
            except Exception:
                logger.exception("Error disconnecting connection pool during cleanup.")
    
    # Rate Limiting Methods
    
    async def register_event(self, key: str, window_seconds: int = 60) -> Tuple[int, bool]:
        """
        Register an event occurrence and return (count, is_rate_limited).
        Uses a sliding window for accurate rate limiting.
        
        Args:
            key: The rate limit key
            window_seconds: Time window in seconds
            
        Returns:
            Tuple of (current count, whether rate limit would be exceeded)
        """
        try:
            client = await self.get_client()
            timestamp = time.time()
            window_start = timestamp - window_seconds
            
            # Use pipeline for atomic operations
            async with client.pipeline() as pipe:
                # Remove events outside the window
                await pipe.zremrangebyscore(key, 0, window_start)
                # Add the current event
                await pipe.zadd(key, {str(uuid.uuid4()): timestamp})
                # Set expiration on the sorted set
                await pipe.expire(key, window_seconds * 2)
                # Count events in the window
                await pipe.zcount(key, window_start, "+inf")
                results = await pipe.execute()
            
            count = results[3]
            return count, False
        except RedisError as e:
            logger.error(f"Error registering event for key '{key}': {e}")
            raise
        
    async def get_event_count(self, key: str, window_seconds: int = 60) -> int:
        """
        Get current count of events in the specified window.
        
        Args:
            key: The rate limit key
            window_seconds: Time window in seconds
            
        Returns:
            Current count of events in the window
        """
        try:
            client = await self.get_client()
            window_start = time.time() - window_seconds
            return await client.zcount(key, window_start, "+inf")
        except RedisError as e:
            logger.error(f"Error getting event count for key '{key}': {e}")
            raise
    
    async def is_rate_limited(self, key: str, max_events: int, window_seconds: int = 60) -> bool:
        """
        Check if rate limit is exceeded without registering an event.
        
        Args:
            key: The rate limit key
            max_events: Maximum allowed events in the window
            window_seconds: Time window in seconds
            
        Returns:
            True if rate limited, False otherwise
        """
        try:
            count = await self.get_event_count(key, window_seconds)
            return count >= max_events
        except Exception as e:
            logger.error(f"Error checking rate limit for key '{key}': {e}")
            # In case of error, default to not rate-limited to prevent blocking legitimate traffic
            return False
    
    # Multi window rate limits

    async def check_multi_window_rate_limits(
        self, 
        key_prefix: str,
        limits: List[Tuple[int, int]]  # [(max_events, window_seconds), ...]
    ) -> Tuple[bool, Dict[str, int]]:
        """
        Check rate limits across multiple time windows in a single Redis round-trip.
        
        Args:
            key_prefix: Base key for rate limit
            limits: List of (max_events, window_seconds) tuples
            
        Returns:
            Tuple of (is_limited, counts_by_window) where:
                - is_limited: True if any window limit is exceeded
                - counts_by_window: Dictionary mapping window_seconds to current event count
        """
        try:
            client = await self.get_client()
            pipeline = await client.pipeline()
            now = time.time()
            
            # Add all window checks to pipeline
            for max_events, window_seconds in limits:
                window_key = f"{key_prefix}:{window_seconds}"
                window_start = now - window_seconds
                
                # Remove expired events
                await pipeline.zremrangebyscore(window_key, 0, window_start)
                # Count current events in window
                await pipeline.zcount(window_key, window_start, "+inf")
                
            # Execute all checks in a single round-trip
            results = await pipeline.execute()
            
            # Process results
            is_limited = False
            counts = {}
            
            for i, (max_events, window_seconds) in enumerate(limits):
                # Each window has two operations: zremrangebyscore and zcount
                # So we need to get the result from position i*2 + 1 (the zcount result)
                count = results[i*2 + 1]
                counts[window_seconds] = count
                
                if count > max_events:
                    is_limited = True
                    
            return is_limited, counts
        except RedisError as e:
            logger.error(f"Error checking multi-window rate limits for key '{key_prefix}': {e}")
            # Default to not rate-limited in case of error
            return False, {}

    async def register_multi_window_event(
        self,
        key_prefix: str,
        windows: List[int]  # List of window sizes in seconds
    ) -> Dict[int, int]:
        """
        Register an event across multiple time windows in a single Redis round-trip.
        
        Args:
            key_prefix: Base key for rate limit
            windows: List of window sizes in seconds
            
        Returns:
            Dictionary mapping window_seconds to current event count
        """
        try:
            client = await self.get_client()
            pipeline = await client.pipeline()
            now = time.time()
            event_id = str(uuid.uuid4())  # Generate a unique ID for this event
            
            # For each window, add the event and clean up expired events
            for window_seconds in windows:
                window_key = f"{key_prefix}:{window_seconds}"
                window_start = now - window_seconds
                
                # Remove events outside the window
                await pipeline.zremrangebyscore(window_key, 0, window_start)
                # Add the current event with the same ID but current timestamp
                await pipeline.zadd(window_key, {event_id: now})
                # Set expiration on the sorted set (2× window to ensure proper cleanup)
                await pipeline.expire(window_key, window_seconds * 2)
                # Count events in the window
                await pipeline.zcount(window_key, window_start, "+inf")
                
            # Execute all operations in a single round-trip
            results = await pipeline.execute()
            
            # Process results to get counts
            counts = {}
            for i, window_seconds in enumerate(windows):
                # Each window has four operations: zremrangebyscore, zadd, expire, zcount
                # So we need to get the count from position i*4 + 3
                counts[window_seconds] = results[i*4 + 3]
                
            return counts
        except RedisError as e:
            logger.error(f"Error registering multi-window event for key '{key_prefix}': {e}")
            raise
    
    # Caching Methods
    
    async def set_cache(
        self, 
        key: str, 
        value: Union[Dict, List, str, int, float, bool, None],
        ttl: Optional[Union[int, timedelta]] = None
    ) -> None:
        """
        Sets a value in the Redis cache by serializing it to JSON string.
        Handles JSON-compatible types.
        
        Args:
            key: The cache key
            value: The value to cache (must be JSON serializable)
            ttl: Optional TTL in seconds or timedelta. Uses default if not specified.
            
        Raises:
            TypeError: If value is not JSON serializable
            RedisError: For Redis-specific errors
            ConnectionError: For connection/auth issues
        """
        try:
            client = await self.get_client()
            
            # Convert value to JSON string
            # If value is already bytes, store it directly
            # Otherwise, serialize to JSON string
            if isinstance(value, bytes):
                json_value = value
            else:
                json_value = json.dumps(value)
            
            ttl_to_use = ttl if ttl is not None else self.default_ttl
            if isinstance(ttl_to_use, timedelta):
                ttl_seconds = int(ttl_to_use.total_seconds())
            elif isinstance(ttl_to_use, int):
                ttl_seconds = ttl_to_use
            else:
                ttl_seconds = int(self.default_ttl.total_seconds())
            
            if ttl_seconds <= 0:
                ttl_seconds = int(self.default_ttl.total_seconds())
            
            # Use pipeline for atomicity of SET + EXPIRE
            async with client.pipeline() as pipe:
                await pipe.set(key, json_value)
                if ttl_seconds > 0:
                    await pipe.expire(key, ttl_seconds)
                results = await pipe.execute()
            
            set_ok = results[0]
            expire_ok = results[1] if ttl_seconds > 0 else True
            
            if not set_ok:
                raise RedisError(f"SET command failed for key {key}")
            if ttl_seconds > 0 and not expire_ok:
                logger.warning(f"Set cache OK for key '{key}' but EXPIRE failed.")
            
            logger.debug(f"Cache set for key '{key}' with TTL {ttl_seconds}s")
            
        except TypeError as e:
            logger.error(f"Value for key '{key}' is not JSON serializable: {e}")
            raise TypeError(f"Value for key '{key}' is not JSON serializable: {e}") from e
        except AuthenticationError as e:
            logger.error(f"Authentication error during set_cache for key '{key}': {e}")
            raise ConnectionError("Authentication failed during set_cache") from e
        except RedisError as e:
            logger.error(f"Error setting cache for key '{key}': {e}")
            raise
    
    async def get_cache(self, key: str) -> Any:
        """
        Gets a value from the Redis cache by deserializing from JSON string.
        Returns None if key not found.
        
        Args:
            key: The cache key to retrieve
            
        Returns:
            The deserialized value or None if key doesn't exist
            
        Raises:
            RedisError: For Redis-specific errors
            ConnectionError: For connection/auth issues
            json.JSONDecodeError: If stored value is not valid JSON
        """
        result = None
        try:
            client = await self.get_client()
            json_str = await client.get(key)
            
            if json_str is not None:
                # If value is bytes, deserialize to bytes
                result = json.loads(json_str)
                logger.debug(f"Cache hit for key '{key}'")
            else:
                logger.debug(f"Cache miss for key '{key}'")
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to deserialize JSON for key '{key}': {e}")
            raise json.JSONDecodeError(f"Invalid JSON stored for key '{key}'", e.doc, e.pos) from e
        except AuthenticationError as e:
            logger.error(f"Authentication error during get_cache for key '{key}': {e}")
            raise ConnectionError("Authentication failed during get_cache") from e
        except RedisError as e:
            logger.error(f"Error getting cache for key '{key}': {e}")
            raise
            
        return result
    
    async def get_binary_cache(self, key: str) -> Optional[bytes]:
        """
        Gets binary data from Redis without JSON deserialization.
        Returns None if key not found.
        
        Args:
            key: The cache key to retrieve
            
        Returns:
            The binary data or None if key doesn't exist
            
        Raises:
            RedisError: For Redis-specific errors
            ConnectionError: For connection/auth issues
        """
        try:
            client = await self.get_client()
            
            # Need to get the raw value without automatic decoding
            # Since the client uses decode_responses=True by default, 
            # we need a special handling here to get the raw bytes
            
            # We can use execute_command to bypass the automatic decoding
            # or set up a dedicated pipeline with a specific encoding setting
            binary_data = await client.execute_command('GET', key)
            
            if binary_data is not None:
                # If using decode_responses=True, the value might be 
                # a string that needs to be converted back to bytes
                if isinstance(binary_data, str):
                    # import ipdb; ipdb.set_trace()
                    binary_data = binary_data.encode('latin1')  # Use latin1 to preserve byte values
                
                logger.debug(f"Binary cache hit for key '{key}', size {len(binary_data)} bytes")
            else:
                logger.debug(f"Binary cache miss for key '{key}'")
            
            return binary_data
                
        except AuthenticationError as e:
            logger.error(f"Authentication error during get_binary_cache for key '{key}': {e}")
            raise ConnectionError("Authentication failed during get_binary_cache") from e
        except RedisError as e:
            logger.error(f"Error getting binary cache for key '{key}': {e}")
            raise

    async def delete_cache(self, key: str) -> bool:
        """
        Delete a cached value.
        
        Args:
            key: Cache key
            
        Returns:
            True if key was deleted, False if key didn't exist
        """
        deleted = False
        try:
            client = await self.get_client()
            deleted_count = await client.delete(key)
            deleted = deleted_count > 0
            logger.debug(f"Cache delete for key '{key}', count: {deleted_count}")
        except RedisError as e:
            logger.error(f"Error deleting cache key '{key}': {e}")
            raise
        return deleted
    
    async def flush_cache(self, pattern: str = "*") -> int:
        """
        Flush all cache matching pattern.
        WARNING: Use with caution!
        
        Args:
            pattern: Key pattern to match
            
        Returns:
            Number of keys deleted
        """
        try:
            client = await self.get_client()
            keys = await client.keys(pattern)
            if not keys:
                return 0
            return await client.delete(*keys)
        except RedisError as e:
            logger.error(f"Error flushing cache with pattern '{pattern}': {e}")
            raise
    
    async def set_max_cache_size(self, max_size_bytes: int, policy: str = "allkeys-lru") -> bool:
        """
        Configure maximum cache size.
        
        Args:
            max_size_bytes: Maximum cache size in bytes
            policy: Eviction policy (allkeys-lru, volatile-lru, allkeys-random, etc.)
            
        Returns:
            True if successful
        """
        try:
            client = await self.get_client()
            success1 = await client.config_set("maxmemory", str(max_size_bytes))
            success2 = await client.config_set("maxmemory-policy", policy)
            return success1 and success2
        except RedisError as e:
            logger.error(f"Error setting max cache size: {e}")
            raise
    
    # Distributed Lock Methods
    
    async def acquire_lock(self, lock_name: str, timeout: int = 10, ttl: Optional[int] = None) -> Optional[str]:
        """
        Acquire a distributed lock with timeout.
        
        Args:
            lock_name: Lock identifier
            timeout: Maximum time to wait for lock in seconds
            ttl: Time-to-live for lock in seconds, defaults to timeout
            
        Returns:
            Lock token if acquired, None otherwise
        """
        if ttl is None:
            ttl = timeout
            
        try:
            client = await self.get_client()
            
            # Generate a unique token for this lock instance
            token = str(uuid.uuid4())
            lock_key = f"lock:{lock_name}"
            
            end_time = time.time() + timeout
            while time.time() < end_time:
                # Try to acquire the lock
                acquired = await client.set(lock_key, token, ex=ttl, nx=True)
                if acquired:
                    logger.debug(f"Lock acquired: {lock_name} with token {token}")
                    return token
                
                # Wait a bit before retrying
                await asyncio.sleep(0.1)
                
            logger.warning(f"Failed to acquire lock {lock_name} after {timeout}s")
            return None
        except RedisError as e:
            logger.error(f"Error acquiring lock '{lock_name}': {e}")
            raise
    
    async def release_lock(self, lock_name: str, token: str) -> bool:
        """
        Release a previously acquired lock.
        
        Args:
            lock_name: Lock identifier
            token: Lock token returned from acquire_lock
            
        Returns:
            True if lock was released, False if not owned by this token
        """
        try:
            client = await self.get_client()
            lock_key = f"lock:{lock_name}"
            
            # Only release if the lock token matches (prevent releasing other's locks)
            async with client.pipeline() as pipe:
                await pipe.watch(lock_key)
                current_token = await pipe.get(lock_key)
                
                if current_token != token:
                    logger.warning(f"Cannot release lock {lock_name}: token mismatch")
                    return False
                    
                pipe.multi()
                await pipe.delete(lock_key)
                await pipe.execute()
                logger.debug(f"Lock released: {lock_name}")
                return True
        except RedisError as e:
            logger.error(f"Error releasing lock '{lock_name}': {e}")
            raise
    
    @asynccontextmanager
    async def with_lock(self, lock_name: str, timeout: int = 10, ttl: Optional[int] = None):
        """
        Async context manager for automatically acquiring and releasing a lock.
        
        Args:
            lock_name: Lock identifier
            timeout: Maximum time to wait for lock in seconds
            ttl: Time-to-live for lock in seconds, defaults to timeout
            
        Raises:
            TimeoutError: If lock cannot be acquired within timeout
        """
        token = await self.acquire_lock(lock_name, timeout, ttl)
        if not token:
            raise TimeoutError(f"Could not acquire lock {lock_name}")
        
        try:
            yield
        finally:
            await self.release_lock(lock_name, token)
    
    # Helper Methods
    
    async def info(self) -> Dict[str, Any]:
        """
        Get Redis server information.
        
        Returns:
            Dictionary of server info
        """
        try:
            client = await self.get_client()
            return await client.info()
        except RedisError as e:
            logger.error(f"Error getting server info: {e}")
            raise


async def test_redis_client():
    """Test the AsyncRedisClient functionality."""
    import os
    redis_url = os.environ.get("REDIS_URL", None)
    if not redis_url:
        raise ValueError("REDIS_URL environment variable not set.")

    # Use the async Redis client
    client = AsyncRedisClient(redis_url)
    TEST_PREFIX = f"test_run_{uuid.uuid4().hex[:6]}:"

    try:
        print(f"\n--- Starting Redis Client Test Run with Prefix: {TEST_PREFIX} ---")

        # --- Test Ping ---
        print("\n--- Testing Ping via Client ---")
        is_connected = await client.ping()
        print(f"Client ping successful: {is_connected}")
        if not is_connected:
            print("Initial ping failed. Aborting.")
            await client.close()
            return

        # --- Test Caching ---
        print("\n--- Testing Caching ---")
        cache_key = f"{TEST_PREFIX}user:101"
        cache_data = {"name": "Dave", "age": 50, "active": False, "dept": "support"}
        await client.set_cache(cache_key, cache_data, ttl=60)  # Shorter TTL for test
        print(f"Set JSON data for key '{cache_key}'")

        retrieved_data = await client.get_cache(cache_key)
        print(f"Got cache value for '{cache_key}': {retrieved_data}")
        assert retrieved_data == cache_data, "JSON data mismatch!"

        # Test deletion
        delete_result = await client.delete_cache(cache_key)
        print(f"Deleted '{cache_key}': {delete_result}")
        assert delete_result is True, "Delete failed!"
        assert await client.get_cache(cache_key) is None, "Key not deleted!"

        # --- Test Rate Limiting ---
        print("\n--- Testing Rate Limiting ---")
        rate_key = f"{TEST_PREFIX}rate:user:101"
        
        # Register events
        for i in range(5):
            count, limited = await client.register_event(rate_key, window_seconds=10)
            print(f"Registered event {i+1}, count: {count}, limited: {limited}")
        
        # Check count and rate limit
        count = await client.get_event_count(rate_key, window_seconds=10)
        print(f"Event count for '{rate_key}': {count}")
        assert count == 5, "Event count mismatch!"
        
        is_limited = await client.is_rate_limited(rate_key, max_events=3, window_seconds=10)
        print(f"Is rate limited (max 3 events): {is_limited}")
        assert is_limited is True, "Should be rate limited!"
        
        is_limited = await client.is_rate_limited(rate_key, max_events=10, window_seconds=10)
        print(f"Is rate limited (max 10 events): {is_limited}")
        assert is_limited is False, "Should not be rate limited!"
        
        # Clean up rate limit key
        await client.delete_cache(rate_key)
        
        # --- Test Distributed Locking ---
        print("\n--- Testing Distributed Locking ---")
        lock_name = f"{TEST_PREFIX}lock:resource1"
        
        # Acquire lock
        token = await client.acquire_lock(lock_name, timeout=5, ttl=10)
        print(f"Acquired lock '{lock_name}' with token: {token}")
        assert token is not None, "Failed to acquire lock!"
        
        # Try to acquire same lock (should fail)
        second_token = await client.acquire_lock(lock_name, timeout=1, ttl=10)
        print(f"Tried to acquire same lock again, got token: {second_token}")
        assert second_token is None, "Should not acquire lock twice!"
        
        # Release lock
        released = await client.release_lock(lock_name, token)
        print(f"Released lock '{lock_name}': {released}")
        assert released is True, "Failed to release lock!"
        
        # Try to acquire lock again (should succeed now)
        token = await client.acquire_lock(lock_name, timeout=1, ttl=10)
        print(f"Acquired lock after release with token: {token}")
        assert token is not None, "Failed to reacquire lock!"
        
        # Release lock again
        await client.release_lock(lock_name, token)
        
        # Test context manager
        print("\n--- Testing Lock Context Manager ---")
        async with client.with_lock(lock_name, timeout=5, ttl=10):
            print(f"Acquired lock '{lock_name}' using context manager")
            # Verify lock is held
            second_token = await client.acquire_lock(lock_name, timeout=1, ttl=10)
            assert second_token is None, "Context manager lock not working!"
        
        # Verify lock is released
        token = await client.acquire_lock(lock_name, timeout=1, ttl=10)
        assert token is not None, "Context manager didn't release lock!"
        await client.release_lock(lock_name, token)
        
        # --- Test Server Info ---
        print("\n--- Testing Server Info ---")
        info = await client.info()
        print(f"Server info: redis_version={info.get('redis_version')}, clients_connected={info.get('connected_clients')}")
        
        # --- Test Flush Cache ---
        print("\n--- Testing Flush Cache ---")
        # Set multiple test keys
        for i in range(3):
            await client.set_cache(f"{TEST_PREFIX}flush_test:{i}", f"value_{i}")
        
        # Flush only these test keys
        flushed = await client.flush_cache(f"{TEST_PREFIX}flush_test:*")
        print(f"Flushed {flushed} keys with pattern '{TEST_PREFIX}flush_test:*'")
        assert flushed == 3, "Should have flushed 3 keys!"

        print("\n--- Redis Client Test Run Completed Successfully ---")

    except ConnectionError as e:
        print(f"Connection Error during test run: {e}")
    except AuthenticationError:
        print(f"Authentication Error: Check credentials in REDIS_URL environment variable.")
    except Exception as e:
        print(f"An unexpected error occurred during test run: {e}")
        print(traceback.format_exc())
    finally:
        # Always attempt to close the client
        if client:
            await client.close()
            print("\nRedis client closed.")

async def main():
    await test_redis_client()

if __name__ == "__main__":
    asyncio.run(main())
