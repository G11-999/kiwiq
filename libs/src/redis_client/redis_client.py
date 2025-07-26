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
from redis.exceptions import ConnectionError, AuthenticationError, TimeoutError, ResponseError, RedisError, WatchError

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
    - Pool-based Concurrency Limiting (replaces sliding window rate limiting)
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
    
    # Pool-based Concurrency Limiting Methods
    
    async def acquire_from_pool(
        self,
        pool_key: str,
        count: int = 1,
        max_pool_size: int = 100,
        ttl: int = 3600
    ) -> Tuple[Optional[str], int, bool]:
        """
        Atomically acquire resources from a concurrency pool.
        
        This implements a pool-based rate limiter where resources are explicitly
        acquired and released, rather than using time windows.
        
        Args:
            pool_key: The pool identifier
            count: Number of resources to acquire (default 1)
            max_pool_size: Maximum pool capacity
            ttl: Time-to-live for the allocation in seconds
            
        Returns:
            Tuple of (allocation_id, current_usage, success) where:
                - allocation_id: Unique ID for this allocation (None if failed)
                - current_usage: Current total usage of the pool
                - success: Whether the acquisition was successful
        """
        try:
            client = await self.get_client()
            max_retries = 10  # Increased for better race condition handling
            
            for retry in range(max_retries):
                allocation_id = str(uuid.uuid4())
                now = time.time()
                expiry = now + ttl
                
                # Keys for pool management
                pool_hash_key = f"pool:{pool_key}"
                allocs_key = f"pool:{pool_key}:allocs"
                alloc_key = f"pool:{pool_key}:alloc:{allocation_id}"
                
                # Start transaction with WATCH
                async with client.pipeline() as pipe:
                    try:
                        # Watch both keys
                        await pipe.watch(pool_hash_key, allocs_key)
                        
                        # Get current state (non-transactional reads)
                        pool_data = await pipe.hgetall(pool_hash_key)
                        current_usage = int(pool_data.get('current', '0'))
                        stored_max = int(pool_data.get('max', str(max_pool_size)))
                        
                        # Use the stored max if it exists, otherwise use provided max
                        effective_max = stored_max if pool_data else max_pool_size
                        
                        # Get expired allocations
                        expired = await pipe.zrangebyscore(allocs_key, 0, now)
                        
                        # Calculate expired count if any
                        expired_count = 0
                        if expired:
                            for expired_id in expired:
                                expired_alloc_key = f"pool:{pool_key}:alloc:{expired_id}"
                                expired_val = await pipe.get(expired_alloc_key)
                                if expired_val:
                                    expired_count += int(expired_val)
                        
                        # Calculate actual current usage after accounting for expired
                        actual_usage = max(0, current_usage - expired_count)
                        
                        # Check if we can acquire
                        if actual_usage + count > effective_max:
                            await pipe.unwatch()
                            return None, actual_usage, False
                        
                        # Start transaction
                        pipe.multi()
                        
                        # Update pool state with actual usage
                        new_usage = actual_usage + count
                        await pipe.hset(pool_hash_key, mapping={
                            'current': str(new_usage),
                            'max': str(effective_max)
                        })
                        
                        # Store allocation (don't set TTL on the key itself, we track expiry in the sorted set)
                        await pipe.set(alloc_key, str(count))
                        await pipe.zadd(allocs_key, {allocation_id: expiry})
                        # Set a longer TTL as a safety measure (2x the allocation TTL)
                        await pipe.expire(alloc_key, ttl * 2)
                        
                        # Clean up expired allocations
                        if expired:
                            await pipe.zrem(allocs_key, *expired)
                            for expired_id in expired:
                                await pipe.delete(f"pool:{pool_key}:alloc:{expired_id}")
                        
                        # Execute transaction
                        await pipe.execute()
                        logger.debug(f"Acquired {count} from pool '{pool_key}', "
                                   f"allocation: {allocation_id}, usage: {new_usage}/{effective_max}")
                        return allocation_id, new_usage, True
                        
                    except WatchError:
                        logger.debug(f"Watch error on pool acquire attempt {retry + 1}, retrying...")
                        await asyncio.sleep(0.01 * retry)  # Small backoff
                        continue
            
            # Max retries exceeded
            current_usage = await self.get_pool_usage(pool_key)
            return None, current_usage, False
            
        except RedisError as e:
            logger.error(f"Error acquiring from pool '{pool_key}': {e}")
            raise
    
    async def release_to_pool(
        self,
        pool_key: str,
        allocation_id: str
    ) -> Tuple[int, int, bool]:
        """
        Release resources back to a concurrency pool.
        
        Args:
            pool_key: The pool identifier
            allocation_id: The allocation ID returned from acquire_from_pool
            
        Returns:
            Tuple of (released_count, current_usage, success) where:
                - released_count: Number of resources released
                - current_usage: Current total usage after release
                - success: Whether the release was successful
        """
        try:
            client = await self.get_client()
            max_retries = 10  # Increased for better race condition handling
            
            for retry in range(max_retries):
                # Keys for pool management
                pool_hash_key = f"pool:{pool_key}"
                allocs_key = f"pool:{pool_key}:allocs"
                alloc_key = f"pool:{pool_key}:alloc:{allocation_id}"
                
                # Start transaction with WATCH
                async with client.pipeline() as pipe:
                    # Watch the pool hash and allocation
                    await pipe.watch(pool_hash_key, alloc_key)
                    
                    # Get allocation count
                    alloc_count_str = await pipe.get(alloc_key)
                    if not alloc_count_str:
                        # Allocation doesn't exist or already released
                        await pipe.unwatch()
                        current_usage = await self.get_pool_usage(pool_key)
                        logger.warning(f"Allocation {allocation_id} not found for pool '{pool_key}' during release")
                        return 0, current_usage, False
                    
                    alloc_count = int(alloc_count_str)
                    
                    # Get current pool state
                    pool_data = await pipe.hgetall(pool_hash_key)
                    current_usage = int(pool_data.get('current', '0'))
                    
                    # Start transaction
                    pipe.multi()
                    
                    # Update pool state
                    new_usage = max(0, current_usage - alloc_count)
                    await pipe.hset(pool_hash_key, 'current', str(new_usage))
                    
                    # Remove allocation
                    await pipe.delete(alloc_key)
                    await pipe.zrem(allocs_key, allocation_id)
                    
                    try:
                        await pipe.execute()
                        logger.debug(f"Released {alloc_count} to pool '{pool_key}', "
                                   f"allocation: {allocation_id}, usage: {new_usage}")
                        return alloc_count, new_usage, True
                    except WatchError:
                        logger.debug(f"Watch error on pool release attempt {retry + 1}, retrying...")
                        await asyncio.sleep(0.01 * retry)  # Small exponential backoff
                        continue
            
            # Max retries exceeded
            current_usage = await self.get_pool_usage(pool_key)
            return 0, current_usage, False
            
        except RedisError as e:
            logger.error(f"Error releasing to pool '{pool_key}': {e}")
            raise
    
    async def get_pool_usage(self, pool_key: str) -> int:
        """
        Get current usage of a concurrency pool.
        
        Args:
            pool_key: The pool identifier
            
        Returns:
            Current usage count
        """
        try:
            client = await self.get_client()
            pool_hash_key = f"pool:{pool_key}"
            
            # Clean up expired allocations first
            await self._cleanup_pool_expired_allocations(pool_key)
            
            # Get the updated usage after cleanup
            pool_data = await client.hget(pool_hash_key, 'current')
            return int(pool_data) if pool_data else 0
            
        except RedisError as e:
            logger.error(f"Error getting pool usage for '{pool_key}': {e}")
            raise
    
    async def get_pool_info(self, pool_key: str) -> Dict[str, Any]:
        """
        Get detailed information about a concurrency pool.
        
        Args:
            pool_key: The pool identifier
            
        Returns:
            Dictionary with pool information
        """
        try:
            client = await self.get_client()
            pool_hash_key = f"pool:{pool_key}"
            allocs_key = f"pool:{pool_key}:allocs"
            
            # Clean up expired allocations first
            cleaned = await self._cleanup_pool_expired_allocations(pool_key)
            
            # Get pool data
            pool_data = await client.hgetall(pool_hash_key)
            current_usage = int(pool_data.get('current', '0'))
            max_size = int(pool_data.get('max', '0'))
            
            # Get active allocations count
            active_count = await client.zcard(allocs_key)
            
            # Get allocation details
            now = time.time()
            allocations = await client.zrange(allocs_key, 0, -1, withscores=True)
            
            allocation_details = []
            for alloc_id, expiry in allocations:
                alloc_key = f"pool:{pool_key}:alloc:{alloc_id}"
                count = await client.get(alloc_key)
                if count:
                    allocation_details.append({
                        'id': alloc_id,
                        'count': int(count),
                        'expires_in': int(expiry - now)
                    })
            
            return {
                'current_usage': current_usage,
                'max_size': max_size,
                'available': max_size - current_usage if max_size > 0 else 0,
                'active_allocations': active_count,
                'cleaned_expired': cleaned,
                'allocations': allocation_details
            }
            
        except RedisError as e:
            logger.error(f"Error getting pool info for '{pool_key}': {e}")
            raise
    
    async def _cleanup_pool_expired_allocations(self, pool_key: str) -> int:
        """
        Clean up expired allocations from a pool.
        
        Args:
            pool_key: The pool identifier
            
        Returns:
            Number of allocations cleaned up
        """
        try:
            client = await self.get_client()
            pool_hash_key = f"pool:{pool_key}"
            allocs_key = f"pool:{pool_key}:allocs"
            
            now = time.time()
            max_retries = 3
            
            logger.debug(f"Starting cleanup for pool '{pool_key}' at time {now}")
            
            for retry in range(max_retries):
                async with client.pipeline() as pipe:
                    # Watch the pool hash
                    await pipe.watch(pool_hash_key)
                    
                    # Get expired allocations
                    expired = await pipe.zrangebyscore(allocs_key, 0, now)
                    if not expired:
                        await pipe.unwatch()
                        return 0
                    
                    # Get current usage
                    current_usage = await pipe.hget(pool_hash_key, 'current')
                    current_usage = int(current_usage) if current_usage else 0
                    
                    # Calculate total to release
                    total_to_release = 0
                    for expired_id in expired:
                        alloc_key = f"pool:{pool_key}:alloc:{expired_id}"
                        count = await pipe.get(alloc_key)
                        if count:
                            total_to_release += int(count)
                    
                    # Start transaction
                    pipe.multi()
                    
                    # Update pool usage
                    new_usage = max(0, current_usage - total_to_release)
                    if total_to_release > 0:
                        await pipe.hset(pool_hash_key, 'current', str(new_usage))
                    
                    # Remove expired allocations
                    await pipe.zrem(allocs_key, *expired)
                    for expired_id in expired:
                        await pipe.delete(f"pool:{pool_key}:alloc:{expired_id}")
                    
                    try:
                        results = await pipe.execute()
                        if len(expired) > 0:
                            logger.info(f"Cleaned up {len(expired)} expired allocations "
                                       f"from pool '{pool_key}', released {total_to_release} resources, "
                                       f"new usage: {new_usage}")
                        return len(expired)
                    except WatchError:
                        logger.warning(f"Watch error on cleanup attempt {retry + 1}, retrying...")
                        await asyncio.sleep(0.01 * retry)  # Small exponential backoff
                        continue
            
            return 0
            
        except RedisError as e:
            logger.error(f"Error cleaning up pool '{pool_key}': {e}")
            raise
    
    async def reset_pool(self, pool_key: str) -> bool:
        """
        Reset a concurrency pool, clearing all allocations.
        
        Args:
            pool_key: The pool identifier
            
        Returns:
            True if pool was reset
        """
        try:
            client = await self.get_client()
            
            # Keys to delete
            keys_to_delete = [
                f"pool:{pool_key}",
                f"pool:{pool_key}:allocs"
            ]
            
            # Get all allocation keys
            allocs_key = f"pool:{pool_key}:allocs"
            allocations = await client.zrange(allocs_key, 0, -1)
            for alloc_id in allocations:
                keys_to_delete.append(f"pool:{pool_key}:alloc:{alloc_id}")
            
            # Delete all keys
            if keys_to_delete:
                await client.delete(*keys_to_delete)
                logger.debug(f"Reset pool '{pool_key}', deleted {len(keys_to_delete)} keys")
                return True
                
            return False
            
        except RedisError as e:
            logger.error(f"Error resetting pool '{pool_key}': {e}")
            raise
    
    async def set_pool_max_size(self, pool_key: str, max_size: int) -> bool:
        """
        Update the maximum size of a concurrency pool.
        
        Args:
            pool_key: The pool identifier
            max_size: New maximum size
            
        Returns:
            True if updated successfully
        """
        try:
            client = await self.get_client()
            pool_hash_key = f"pool:{pool_key}"
            
            await client.hset(pool_hash_key, 'max', str(max_size))
            logger.debug(f"Updated pool '{pool_key}' max size to {max_size}")
            return True
            
        except RedisError as e:
            logger.error(f"Error setting pool max size for '{pool_key}': {e}")
            raise
    
    async def is_pool_exhausted(self, pool_key: str, additional_count: int = 0) -> bool:
        """
        Check if a pool is exhausted (at or over capacity).
        
        Args:
            pool_key: The pool identifier
            additional_count: Additional count to check (0 = just check current)
            
        Returns:
            True if pool is exhausted
        """
        try:
            client = await self.get_client()
            pool_hash_key = f"pool:{pool_key}"
            
            # Clean up expired allocations first
            await self._cleanup_pool_expired_allocations(pool_key)
            
            pool_data = await client.hgetall(pool_hash_key)
            current_usage = int(pool_data.get('current', '0'))
            max_size = int(pool_data.get('max', '100'))
            
            return (current_usage + additional_count) >= max_size
            
        except RedisError as e:
            logger.error(f"Error checking if pool '{pool_key}' is exhausted: {e}")
            return True  # Default to exhausted on error
    
    # Time-window based atomic rate limiting methods (for sliding window functionality)
    
    async def register_event_atomic(
        self, 
        key: str, 
        max_events: int,
        window_seconds: int = 60
    ) -> Tuple[int, bool]:
        """
        Atomically register an event only if it doesn't exceed the rate limit.
        Uses sliding window for accurate rate limiting.
        
        Args:
            key: The rate limit key
            max_events: Maximum allowed events in the window
            window_seconds: Time window in seconds
            
        Returns:
            Tuple of (current count after attempt, whether event was registered)
        """
        try:
            client = await self.get_client()
            max_retries = 10  # Increased for better race condition handling
            
            for retry in range(max_retries):
                timestamp = time.time()
                window_start = timestamp - window_seconds
                
                # Start a transaction with WATCH
                async with client.pipeline() as pipe:
                    # Watch the key for changes
                    await pipe.watch(key)
                    
                    # Get current state
                    await pipe.zremrangebyscore(key, 0, window_start)
                    current_count = await pipe.zcount(key, window_start, "+inf")
                    
                    # Check if adding would exceed limit
                    if current_count >= max_events:
                        # Don't add, just return current state
                        await pipe.unwatch()
                        return current_count, False
                    
                    # Start transaction
                    pipe.multi()
                    
                    # Add the event
                    await pipe.zadd(key, {str(uuid.uuid4()): timestamp})
                    await pipe.expire(key, window_seconds * 2)
                    await pipe.zcount(key, window_start, "+inf")
                    
                    try:
                        results = await pipe.execute()
                        # Transaction succeeded
                        new_count = results[-1]  # Last operation was zcount
                        return new_count, True
                    except WatchError:
                        # Key was modified, retry with backoff
                        logger.debug(f"Watch error on attempt {retry + 1}, retrying...")
                        await asyncio.sleep(0.01 * retry)  # Small exponential backoff
                        continue
            
            # Max retries exceeded, get current count
            current_count = await self.get_event_count(key, window_seconds)
            return current_count, False
            
        except RedisError as e:
            logger.error(f"Error in atomic event registration for key '{key}': {e}")
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
            # Clean up old events first
            await client.zremrangebyscore(key, 0, window_start)
            return await client.zcount(key, window_start, "+inf")
        except RedisError as e:
            logger.error(f"Error getting event count for key '{key}': {e}")
            raise
    
    async def register_event_with_count_atomic(
        self,
        key: str,
        count: int,
        max_count: int,
        window_seconds: int = 60
    ) -> Tuple[int, bool]:
        """
        Atomically register an event with count only if it doesn't exceed the limit.
        Uses sliding window with count-based limits (e.g., for token bucket).
        
        Args:
            key: The rate limit key
            count: Number of units to consume (e.g., 10 tokens)
            max_count: Maximum allowed total count in the window
            window_seconds: Time window in seconds
            
        Returns:
            Tuple of (current total usage after attempt, whether event was registered)
        """
        try:
            client = await self.get_client()
            max_retries = 5
            
            for retry in range(max_retries):
                timestamp = time.time()
                window_start = timestamp - window_seconds
                
                # Start a transaction with WATCH
                async with client.pipeline() as pipe:
                    # Watch the key for changes
                    await pipe.watch(key)
                    
                    # Get current state
                    await pipe.zremrangebyscore(key, 0, window_start)
                    members = await pipe.zrangebyscore(key, window_start, "+inf")
                    
                    # Calculate current usage
                    current_usage = 0
                    for member in members:
                        parts = member.split(':')
                        if len(parts) >= 2:
                            try:
                                member_count = int(parts[-1])
                                current_usage += member_count
                            except ValueError:
                                pass
                    
                    # Check if adding would exceed limit
                    if current_usage + count > max_count:
                        # Don't add, just return current state
                        await pipe.unwatch()
                        return current_usage, False
                    
                    # Start transaction
                    pipe.multi()
                    
                    # Add the event with count
                    member = f"{uuid.uuid4()}:{count}"
                    await pipe.zadd(key, {member: timestamp})
                    await pipe.expire(key, window_seconds * 2)
                    
                    try:
                        await pipe.execute()
                        # Transaction succeeded
                        return current_usage + count, True
                    except WatchError:
                        # Key was modified, retry with backoff
                        logger.debug(f"Watch error on attempt {retry + 1}, retrying...")
                        await asyncio.sleep(0.01 * retry)  # Small exponential backoff
                        continue
            
            # Max retries exceeded, get current usage
            current_usage = await self.get_event_count_usage(key, window_seconds)
            return current_usage, False
            
        except RedisError as e:
            logger.error(f"Error in atomic count registration for key '{key}': {e}")
            raise
    
    async def get_event_count_usage(
        self,
        key: str,
        window_seconds: int = 60
    ) -> int:
        """
        Get current total usage (sum of all counts) in the specified window.
        
        Args:
            key: The rate limit key
            window_seconds: Time window in seconds
            
        Returns:
            Current total usage in the window
        """
        try:
            client = await self.get_client()
            window_start = time.time() - window_seconds
            
            # Get all members in the window
            members = await client.zrangebyscore(key, window_start, "+inf")
            
            # Calculate total usage
            total_usage = 0
            for member in members:
                parts = member.split(':')
                if len(parts) >= 2:
                    try:
                        member_count = int(parts[-1])
                        total_usage += member_count
                    except ValueError:
                        pass
            
            return max(0, total_usage)
        except RedisError as e:
            logger.error(f"Error getting event count usage for key '{key}': {e}")
            raise
    
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
    
    async def register_multi_window_event_atomic(
        self,
        key_prefix: str,
        limits: List[Tuple[int, int]]  # [(max_events, window_seconds), ...]
    ) -> Tuple[bool, Dict[int, int]]:
        """
        Atomically register an event across multiple time windows only if ALL windows allow it.
        
        Args:
            key_prefix: Base key for rate limit
            limits: List of (max_events, window_seconds) tuples
            
        Returns:
            Tuple of (event_registered, counts_by_window) where:
                - event_registered: True if event was registered in ALL windows
                - counts_by_window: Dictionary mapping window_seconds to current count
        """
        try:
            client = await self.get_client()
            max_retries = 5
            
            for retry in range(max_retries):
                now = time.time()
                event_id = str(uuid.uuid4())
                
                # Start a transaction with WATCH on all window keys
                async with client.pipeline() as pipe:
                    # Watch all window keys
                    window_keys = []
                    for _, window_seconds in limits:
                        window_key = f"{key_prefix}:{window_seconds}"
                        window_keys.append(window_key)
                    
                    for key in window_keys:
                        await pipe.watch(key)
                    
                    # Check current state for all windows
                    current_counts = {}
                    can_register = True
                    
                    for max_events, window_seconds in limits:
                        window_key = f"{key_prefix}:{window_seconds}"
                        window_start = now - window_seconds
                        
                        # Clean up expired events
                        await pipe.zremrangebyscore(window_key, 0, window_start)
                        count = await pipe.zcount(window_key, window_start, "+inf")
                        current_counts[window_seconds] = count
                        
                        if count >= max_events:
                            can_register = False
                            break
                    
                    if not can_register:
                        # At least one window is at limit
                        await pipe.unwatch()
                        return False, current_counts
                    
                    # Start transaction
                    pipe.multi()
                    
                    # Add event to all windows
                    for _, window_seconds in limits:
                        window_key = f"{key_prefix}:{window_seconds}"
                        await pipe.zadd(window_key, {event_id: now})
                        await pipe.expire(window_key, window_seconds * 2)
                    
                    try:
                        await pipe.execute()
                        # Transaction succeeded - update counts
                        for window_seconds in current_counts:
                            current_counts[window_seconds] += 1
                        return True, current_counts
                    except WatchError:
                        # Key was modified, retry with backoff
                        logger.debug(f"Watch error on multi-window attempt {retry + 1}, retrying...")
                        await asyncio.sleep(0.01 * retry)  # Small exponential backoff
                        continue
            
            # Max retries exceeded
            is_limited, counts = await self.check_multi_window_rate_limits(key_prefix, limits)
            return not is_limited, counts
            
        except RedisError as e:
            logger.error(f"Error in atomic multi-window event registration for key '{key_prefix}': {e}")
            raise
    
    async def check_multi_window_count_limits(
        self,
        key_prefix: str,
        limits: List[Tuple[int, int]],  # [(max_count, window_seconds), ...]
        additional_count: int = 0
    ) -> Tuple[bool, Dict[int, int]]:
        """
        Check count-based rate limits across multiple time windows.
        
        Args:
            key_prefix: Base key for rate limit
            limits: List of (max_count, window_seconds) tuples
            additional_count: Additional count to check (0 = just check current)
            
        Returns:
            Tuple of (is_limited, usage_by_window) where:
                - is_limited: True if any window limit is exceeded (including additional_count)
                - usage_by_window: Dictionary mapping window_seconds to current usage
        """
        try:
            client = await self.get_client()
            pipeline = await client.pipeline()
            now = time.time()
            
            # Add all window checks to pipeline
            for max_count, window_seconds in limits:
                window_key = f"{key_prefix}:{window_seconds}:count"
                window_start = now - window_seconds
                
                # Remove expired events
                await pipeline.zremrangebyscore(window_key, 0, window_start)
                # Get all members in window
                await pipeline.zrangebyscore(window_key, window_start, "+inf")
                
            # Execute all checks in a single round-trip
            results = await pipeline.execute()
            
            # Process results
            is_limited = False
            usage = {}
            
            for i, (max_count, window_seconds) in enumerate(limits):
                # Each window has two operations: zremrangebyscore and zrangebyscore
                # Get members from position i*2 + 1
                members = results[i*2 + 1]
                
                # Calculate total usage
                total_usage = 0
                for member in members:
                    parts = member.split(':')
                    if len(parts) >= 2:
                        try:
                            member_count = int(parts[-1])
                            total_usage += member_count
                        except ValueError:
                            pass
                
                usage[window_seconds] = max(0, total_usage)
                
                # Check if current usage plus additional count would exceed limit
                if usage[window_seconds] + additional_count > max_count:
                    is_limited = True
                    
            return is_limited, usage
        except RedisError as e:
            logger.error(f"Error checking multi-window count limits for key '{key_prefix}': {e}")
            return False, {}
    
    async def register_multi_window_count_event_atomic(
        self,
        key_prefix: str,
        count: int,
        limits: List[Tuple[int, int]]  # [(max_count, window_seconds), ...]
    ) -> Tuple[bool, Dict[int, int]]:
        """
        Atomically register an event with count across multiple windows only if ALL windows allow it.
        
        Args:
            key_prefix: Base key for rate limit
            count: Number of units to consume (e.g., tokens)
            limits: List of (max_count, window_seconds) tuples
            
        Returns:
            Tuple of (event_registered, usage_by_window) where:
                - event_registered: True if event was registered in ALL windows
                - usage_by_window: Dictionary mapping window_seconds to current usage
        """
        try:
            client = await self.get_client()
            max_retries = 5
            
            for retry in range(max_retries):
                now = time.time()
                event_id = str(uuid.uuid4())
                member = f"{event_id}:{count}"
                
                # Start a transaction with WATCH on all window keys
                async with client.pipeline() as pipe:
                    # Watch all window keys
                    window_keys = []
                    for _, window_seconds in limits:
                        window_key = f"{key_prefix}:{window_seconds}:count"
                        window_keys.append(window_key)
                    
                    for key in window_keys:
                        await pipe.watch(key)
                    
                    # Check current usage for all windows
                    current_usage = {}
                    can_register = True
                    
                    for max_count, window_seconds in limits:
                        window_key = f"{key_prefix}:{window_seconds}:count"
                        window_start = now - window_seconds
                        
                        # Clean up expired events
                        await pipe.zremrangebyscore(window_key, 0, window_start)
                        members = await pipe.zrangebyscore(window_key, window_start, "+inf")
                        
                        # Calculate current usage
                        total_usage = 0
                        for existing_member in members:
                            parts = existing_member.split(':')
                            if len(parts) >= 2:
                                try:
                                    member_count = int(parts[-1])
                                    total_usage += member_count
                                except ValueError:
                                    pass
                        
                        current_usage[window_seconds] = total_usage
                        
                        # Check if adding would exceed limit
                        if total_usage + count > max_count:
                            can_register = False
                            break
                    
                    if not can_register:
                        # At least one window would exceed limit
                        await pipe.unwatch()
                        return False, current_usage
                    
                    # Start transaction
                    pipe.multi()
                    
                    # Add event to all windows
                    for _, window_seconds in limits:
                        window_key = f"{key_prefix}:{window_seconds}:count"
                        await pipe.zadd(window_key, {member: now})
                        await pipe.expire(window_key, window_seconds * 2)
                    
                    try:
                        await pipe.execute()
                        # Transaction succeeded - update usage
                        for window_seconds in current_usage:
                            current_usage[window_seconds] += count
                        return True, current_usage
                    except WatchError:
                        # Key was modified, retry with backoff
                        logger.debug(f"Watch error on multi-window count attempt {retry + 1}, retrying...")
                        await asyncio.sleep(0.01 * retry)  # Small exponential backoff
                        continue
            
            # Max retries exceeded
            is_limited, usage = await self.check_multi_window_count_limits(key_prefix, limits)
            return not is_limited, usage
            
        except RedisError as e:
            logger.error(f"Error in atomic multi-window count registration for key '{key_prefix}': {e}")
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
            
            # Calculate TTL first
            ttl_to_use = ttl if ttl is not None else self.default_ttl
            if isinstance(ttl_to_use, timedelta):
                ttl_seconds = int(ttl_to_use.total_seconds())
            elif isinstance(ttl_to_use, int):
                ttl_seconds = ttl_to_use
            else:
                ttl_seconds = int(self.default_ttl.total_seconds())
            
            if ttl_seconds <= 0:
                ttl_seconds = int(self.default_ttl.total_seconds())
            
            # Handle different value types
            if isinstance(value, bytes):
                # For bytes, we need to use a binary-safe client
                binary_client = redis.Redis(
                    connection_pool=redis.ConnectionPool.from_url(
                        self.redis_url,
                        decode_responses=False,  # Don't decode for binary data
                        socket_connect_timeout=self.socket_connect_timeout,
                        socket_keepalive=True,
                    )
                )
                
                # Use pipeline for atomicity of SET + EXPIRE
                async with binary_client.pipeline() as pipe:
                    await pipe.set(key, value)
                    if ttl_seconds > 0:
                        await pipe.expire(key, ttl_seconds)
                    results = await pipe.execute()
                
                await binary_client.aclose()
                
                set_ok = results[0]
                expire_ok = results[1] if ttl_seconds > 0 else True
                
                if not set_ok:
                    raise RedisError(f"SET command failed for key {key}")
                if ttl_seconds > 0 and not expire_ok:
                    logger.warning(f"Set cache OK for key '{key}' but EXPIRE failed.")
                
                logger.debug(f"Binary cache set for key '{key}' with TTL {ttl_seconds}s")
                return
            else:
                # For non-binary data, serialize to JSON
                json_value = json.dumps(value)
            
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
            # Create a separate connection that doesn't decode responses
            # to properly handle binary data
            pool = self._get_pool()
            binary_client = redis.Redis(
                connection_pool=redis.ConnectionPool.from_url(
                    self.redis_url,
                    decode_responses=False,  # Don't decode for binary data
                    socket_connect_timeout=self.socket_connect_timeout,
                    socket_keepalive=True,
                )
            )
            
            binary_data = await binary_client.get(key)
            
            if binary_data is not None:
                logger.debug(f"Binary cache hit for key '{key}', size {len(binary_data)} bytes")
            else:
                logger.debug(f"Binary cache miss for key '{key}'")
            
            # Clean up the binary client
            await binary_client.aclose()
            
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
    
    # Queue Management Methods for Scrapy Integration

    async def push_request(
        self, 
        queue_key: str,
        request_data: Dict[str, Any],
        priority: int = 0,
        dedupe_key: Optional[str] = None
    ) -> bool:
        """
        Push a request to the priority queue.
        
        Args:
            queue_key: Redis key for the queue (e.g., "spider:requests")
            request_data: Serialized request data including URL, meta, etc.
            priority: Request priority (higher = processed first)
            dedupe_key: Optional key for deduplication (defaults to URL)
            
        Returns:
            True if request was queued, False if duplicate
        """
        try:
            client = await self.get_client()
            
            # Use URL as dedupe key if not provided
            if dedupe_key is None:
                dedupe_key = request_data.get('url', '')
                
            # Check for duplicates
            dupefilter_key = f"{queue_key}:dupefilter"
            is_duplicate = await client.sismember(dupefilter_key, dedupe_key)
            
            if is_duplicate:
                logger.debug(f"Duplicate request filtered: {dedupe_key}")
                return False
                
            # Add to queue and dupefilter atomically
            async with client.pipeline() as pipe:
                # Add to priority queue (sorted set)
                await pipe.zadd(queue_key, {json.dumps(request_data): -priority})
                # Add to dupefilter set
                await pipe.sadd(dupefilter_key, dedupe_key)
                # Set TTL on dupefilter (7 days)
                await pipe.expire(dupefilter_key, 7 * 86400)
                results = await pipe.execute()
                
            added_to_queue = results[0] == 1
            logger.debug(f"Request queued: {dedupe_key}, priority: {priority}")
            return added_to_queue
            
        except RedisError as e:
            logger.error(f"Error pushing request to queue '{queue_key}': {e}")
            raise

    async def push_request_safe(
        self,
        queue_key: str,
        request_data: Dict[str, Any],
        priority: int = 0,
        dedupe_key: Optional[str] = None
    ) -> bool:
        """
        Push request with memory safety check.
        
        Args:
            Same as push_request
            
        Returns:
            True if request was queued, False if duplicate or memory full
        """
        try:
            # Check memory usage first
            memory_usage = await self.check_memory_usage()
            if memory_usage > 90:  # 90% threshold
                logger.warning(f"Redis memory usage at {memory_usage:.1f}%, skipping request")
                # Could implement disk overflow here
                return False
                
            return await self.push_request(queue_key, request_data, priority, dedupe_key)
            
        except RedisError as e:
            logger.error(f"Error in push_request_safe: {e}")
            raise

    async def pop_request(self, queue_key: str) -> Optional[Dict[str, Any]]:
        """
        Pop highest priority request from the queue.
        
        Args:
            queue_key: Redis key for the queue
            
        Returns:
            Request data dict or None if queue empty
        """
        try:
            client = await self.get_client()
            
            # Pop highest priority (lowest score) item
            result = await client.zpopmin(queue_key, count=1)
            
            if not result:
                return None
                
            # Result is [(member, score)]
            request_json, score = result[0]
            request_data = json.loads(request_json)
            
            logger.debug(f"Popped request: {request_data.get('url', 'unknown')}")
            return request_data
            
        except RedisError as e:
            logger.error(f"Error popping request from queue '{queue_key}': {e}")
            raise

    async def push_requests_batch(
        self,
        queue_key: str,
        requests: List[Dict[str, Any]],
        check_duplicates: bool = True
    ) -> int:
        """
        Push multiple requests to queue in a single pipeline.
        
        Args:
            queue_key: Redis key for the queue
            requests: List of request data dicts with 'url' and optional 'priority'
            check_duplicates: Whether to filter duplicates
            
        Returns:
            Number of requests actually queued (excluding duplicates)
        """
        try:
            client = await self.get_client()
            dupefilter_key = f"{queue_key}:dupefilter"
            
            if check_duplicates:
                # First, deduplicate within the batch itself
                seen_urls = set()
                deduplicated_requests = []
                for req in requests:
                    url = req.get('url', '')
                    if url not in seen_urls:
                        seen_urls.add(url)
                        deduplicated_requests.append(req)
                
                # Then check against existing duplicates in Redis
                urls = [req.get('url', '') for req in deduplicated_requests]
                async with client.pipeline() as pipe:
                    for url in urls:
                        await pipe.sismember(dupefilter_key, url)
                    duplicate_checks = await pipe.execute()
                    
                # Filter out requests that exist in dupefilter
                new_requests = []
                for req, is_dup in zip(deduplicated_requests, duplicate_checks):
                    if not is_dup:
                        new_requests.append(req)
                        
                if not new_requests:
                    logger.debug("All requests were duplicates")
                    return 0
            else:
                new_requests = requests
                
            # Add all new requests in a single pipeline
            async with client.pipeline() as pipe:
                for req in new_requests:
                    priority = req.get('priority', 0)
                    url = req.get('url', '')
                    await pipe.zadd(queue_key, {json.dumps(req): -priority})
                    if check_duplicates:
                        await pipe.sadd(dupefilter_key, url)
                        
                # Set TTL on dupefilter
                if check_duplicates:
                    await pipe.expire(dupefilter_key, 7 * 86400)
                    
                await pipe.execute()
                
            logger.debug(f"Batch queued {len(new_requests)} requests")
            return len(new_requests)
            
        except RedisError as e:
            logger.error(f"Error batch pushing requests to queue '{queue_key}': {e}")
            raise

    async def get_queue_length(self, queue_key: str) -> int:
        """
        Get the current length of the request queue.
        
        Args:
            queue_key: Redis key for the queue
            
        Returns:
            Number of requests in queue
        """
        try:
            client = await self.get_client()
            return await client.zcard(queue_key)
        except RedisError as e:
            logger.error(f"Error getting queue length for '{queue_key}': {e}")
            raise

    async def clear_queue(self, queue_key: str, clear_dupefilter: bool = True) -> Tuple[int, int]:
        """
        Clear the request queue and optionally the dupefilter.
        
        Args:
            queue_key: Redis key for the queue
            clear_dupefilter: Whether to also clear the dupefilter set
            
        Returns:
            Tuple of (queue_items_removed, dupefilter_items_removed)
        """
        try:
            client = await self.get_client()
            
            # Get counts before deletion
            queue_count = await client.zcard(queue_key)
            dupefilter_key = f"{queue_key}:dupefilter"
            dupefilter_count = await client.scard(dupefilter_key) if clear_dupefilter else 0
            
            async with client.pipeline() as pipe:
                # Delete the queue
                await pipe.delete(queue_key)
                
                # Optionally delete dupefilter
                if clear_dupefilter:
                    await pipe.delete(dupefilter_key)
                    
                await pipe.execute()
                
            logger.info(f"Cleared queue '{queue_key}': {queue_count} items, "
                    f"dupefilter: {dupefilter_count} items")
            
            return queue_count, dupefilter_count
            
        except RedisError as e:
            logger.error(f"Error clearing queue '{queue_key}': {e}")
            raise

    async def peek_queue(self, queue_key: str, count: int = 10) -> List[Dict[str, Any]]:
        """
        Peek at top requests in queue without removing them.
        
        Args:
            queue_key: Redis key for the queue
            count: Number of requests to peek at
            
        Returns:
            List of request data dicts
        """
        try:
            client = await self.get_client()
            
            # Get items with lowest scores (highest priority)
            items = await client.zrange(queue_key, 0, count - 1, withscores=True)
            
            requests = []
            for request_json, score in items:
                request_data = json.loads(request_json)
                request_data['_queue_priority'] = -score  # Convert back to original priority
                requests.append(request_data)
                
            return requests
            
        except RedisError as e:
            logger.error(f"Error peeking queue '{queue_key}': {e}")
            raise

    async def update_request_priority(
        self,
        queue_key: str,
        url: str,
        new_priority: int
    ) -> bool:
        """
        Update the priority of a queued request.
        
        Args:
            queue_key: Redis key for the queue
            url: URL of the request to update
            new_priority: New priority value
            
        Returns:
            True if updated, False if not found
        """
        try:
            client = await self.get_client()
            
            # Find the request by scanning the queue
            items = await client.zrange(queue_key, 0, -1, withscores=True)
            
            for request_json, score in items:
                request_data = json.loads(request_json)
                if request_data.get('url') == url:
                    # Remove old entry and add with new priority
                    async with client.pipeline() as pipe:
                        await pipe.zrem(queue_key, request_json)
                        await pipe.zadd(queue_key, {request_json: -new_priority})
                        results = await pipe.execute()
                        
                    if results[0] == 1:  # Successfully removed
                        logger.debug(f"Updated priority for {url} to {new_priority}")
                        return True
                        
            return False
            
        except RedisError as e:
            logger.error(f"Error updating request priority in queue '{queue_key}': {e}")
            raise

    async def get_queue_stats(self, queue_key: str) -> Dict[str, Any]:
        """
        Get statistics about the request queue.
        
        Args:
            queue_key: Redis key for the queue
            
        Returns:
            Dictionary with queue statistics
        """
        try:
            client = await self.get_client()
            dupefilter_key = f"{queue_key}:dupefilter"
            
            async with client.pipeline() as pipe:
                await pipe.zcard(queue_key)  # Queue size
                await pipe.scard(dupefilter_key)  # Dupefilter size
                await pipe.ttl(dupefilter_key)  # Dupefilter TTL
                # Get priority range
                await pipe.zrange(queue_key, 0, 0, withscores=True)  # Highest priority
                await pipe.zrange(queue_key, -1, -1, withscores=True)  # Lowest priority
                
                results = await pipe.execute()
                
            stats = {
                'queue_size': results[0],
                'dupefilter_size': results[1],
                'dupefilter_ttl': results[2],
                'highest_priority': -results[3][0][1] if results[3] else None,
                'lowest_priority': -results[4][0][1] if results[4] else None,
            }
            
            return stats
            
        except RedisError as e:
            logger.error(f"Error getting queue stats for '{queue_key}': {e}")
            raise

    # Memory Monitoring Methods

    async def check_memory_usage(self) -> float:
        """
        Check Redis memory usage percentage.
        
        Returns:
            Memory usage percentage (0-100)
        """
        try:
            client = await self.get_client()
            info = await client.info('memory')
            
            used = int(info.get('used_memory', 0))
            max_memory = int(info.get('maxmemory', 0))
            
            if max_memory > 0:
                usage_percent = (used / max_memory) * 100
            else:
                # No memory limit set
                usage_percent = 0.0  # Ensure it's a float
                
            return float(usage_percent)  # Ensure return type is always float
            
        except RedisError as e:
            logger.error(f"Error checking memory usage: {e}")
            return 0.0  # Return float instead of int

    async def get_memory_info(self) -> Dict[str, Any]:
        """
        Get detailed memory information.
        
        Returns:
            Dictionary with memory statistics
        """
        try:
            client = await self.get_client()
            info = await client.info('memory')
            
            return {
                'used_memory': info.get('used_memory', 0),
                'used_memory_human': info.get('used_memory_human', '0B'),
                'maxmemory': info.get('maxmemory', 0),
                'maxmemory_human': info.get('maxmemory_human', '0B'),
                'maxmemory_policy': info.get('maxmemory_policy', 'noeviction'),
                'mem_fragmentation_ratio': info.get('mem_fragmentation_ratio', 1.0),
                'usage_percent': float(await self.check_memory_usage())  # Ensure float
            }
            
        except RedisError as e:
            logger.error(f"Error getting memory info: {e}")
            return {}

    # Temporary State Storage Methods

    async def set_job_state(
        self,
        job_key: str,
        state_data: Dict[str, Any],
        ttl: int = 86400  # 24 hours default
    ) -> None:
        """
        Store temporary job state.
        
        Args:
            job_key: Job identifier key
            state_data: State data to store
            ttl: Time to live in seconds
        """
        try:
            client = await self.get_client()
            await client.hset(f"job_state:{job_key}", mapping={
                k: json.dumps(v) if not isinstance(v, str) else v
                for k, v in state_data.items()
            })
            await client.expire(f"job_state:{job_key}", ttl)
            
        except RedisError as e:
            logger.error(f"Error setting job state for '{job_key}': {e}")
            raise

    async def get_job_state(self, job_key: str) -> Dict[str, Any]:
        """
        Retrieve temporary job state.
        
        Args:
            job_key: Job identifier key
            
        Returns:
            State data dictionary
        """
        try:
            client = await self.get_client()
            raw_state = await client.hgetall(f"job_state:{job_key}")
            
            # Deserialize JSON values
            state = {}
            for k, v in raw_state.items():
                # Handle both string and integer values (from hincrby)
                if isinstance(v, int):
                    state[k] = v
                else:
                    try:
                        state[k] = json.loads(v)
                    except json.JSONDecodeError:
                        state[k] = v  # Keep as string if not JSON
                    
            return state
            
        except RedisError as e:
            logger.error(f"Error getting job state for '{job_key}': {e}")
            raise

    async def increment_job_counter(
        self,
        job_key: str,
        counter_name: str,
        amount: int = 1
    ) -> int:
        """
        Increment a job counter atomically.
        
        Args:
            job_key: Job identifier key
            counter_name: Name of the counter
            amount: Amount to increment by
            
        Returns:
            New counter value
        """
        try:
            client = await self.get_client()
            return await client.hincrby(f"job_state:{job_key}", counter_name, amount)
            
        except RedisError as e:
            logger.error(f"Error incrementing counter '{counter_name}' for job '{job_key}': {e}")
            raise
    
    async def purge_spider_data(self, spider_name: str, job_id: Optional[str] = None) -> Dict[str, int]:
        """
        Purge all Redis data for a spider/job.
        
        Args:
            spider_name: Name of the spider
            job_id: Optional job ID for job-specific purging
            
        Returns:
            Dictionary with counts of purged items by type
        """
        try:
            client = await self.get_client()
            purged = {
                'queue': 0,
                'dupefilter': 0,
                'job_state': 0,
                'total_keys': 0
            }
            
            # Build key patterns based on job_id
            if job_id:
                patterns = [
                    f"queue:{spider_name}:{job_id}:*",
                    f"queue:{spider_name}:requests:{job_id}",
                    f"job_state:{spider_name}:{job_id}",
                ]
            else:
                patterns = [
                    f"queue:{spider_name}:*",
                    f"job_state:{spider_name}*",
                ]
                
            # Find and delete all matching keys
            for pattern in patterns:
                keys = await client.keys(pattern)
                if keys:
                    deleted = await client.delete(*keys)
                    purged['total_keys'] += deleted
                    
                    # Track specific types
                    if 'queue' in pattern and 'dupefilter' not in pattern:
                        purged['queue'] += deleted
                    elif 'dupefilter' in pattern:
                        purged['dupefilter'] += deleted
                    elif 'job_state' in pattern:
                        purged['job_state'] += deleted
                        
            logger.info(f"Purged spider data: {purged}")
            return purged
            
        except RedisError as e:
            logger.error(f"Error purging spider data: {e}")
            raise
    
    # Generic Counter/Limit Tracking Methods
    
    async def increment_counter_with_limit(
        self,
        key: str,
        increment: int = 1,
        limit: Optional[int] = None,
        ttl: Optional[int] = None
    ) -> Tuple[int, bool]:
        """
        Increment a counter and check against an optional limit.
        
        Args:
            key: Redis key for the counter
            increment: Amount to increment by (default 1)
            limit: Optional maximum value allowed
            ttl: Optional TTL in seconds
            
        Returns:
            Tuple of (new_count, is_at_or_over_limit)
        """
        try:
            client = await self.get_client()
            
            # Use pipeline for atomic operation
            async with client.pipeline() as pipe:
                await pipe.incrby(key, increment)
                if ttl is not None:
                    await pipe.expire(key, ttl)
                results = await pipe.execute()
                
            new_count = results[0]
            is_over_limit = False
            
            if limit is not None:
                is_over_limit = new_count >= limit
                
            return new_count, is_over_limit
            
        except RedisError as e:
            logger.error(f"Error incrementing counter for key '{key}': {e}")
            raise
    
    async def get_counter_value(self, key: str) -> int:
        """
        Get current value of a counter.
        
        Args:
            key: Redis key for the counter
            
        Returns:
            Current counter value (0 if key doesn't exist)
        """
        try:
            client = await self.get_client()
            value = await client.get(key)
            return int(value) if value else 0
            
        except (RedisError, ValueError) as e:
            logger.error(f"Error getting counter value for key '{key}': {e}")
            if isinstance(e, RedisError):
                raise
            return 0
    
    async def check_counter_limit(self, key: str, limit: int) -> bool:
        """
        Check if a counter has reached or exceeded a limit without incrementing.
        
        Args:
            key: Redis key for the counter
            limit: Maximum value to check against
            
        Returns:
            True if at or over limit, False otherwise
        """
        try:
            current_value = await self.get_counter_value(key)
            return current_value >= limit
            
        except RedisError as e:
            logger.error(f"Error checking counter limit for key '{key}': {e}")
            raise
    
    async def reset_counter(self, key: str) -> bool:
        """
        Reset a counter to 0.
        
        Args:
            key: Redis key for the counter
            
        Returns:
            True if key existed and was reset, False if key didn't exist
        """
        try:
            client = await self.get_client()
            return await client.delete(key) > 0
            
        except RedisError as e:
            logger.error(f"Error resetting counter for key '{key}': {e}")
            raise
    
    async def increment_hash_counter(
        self,
        hash_key: str,
        field: str,
        increment: int = 1,
        ttl: Optional[int] = None
    ) -> int:
        """
        Increment a counter within a hash field.
        
        Args:
            hash_key: Redis hash key
            field: Field within the hash
            increment: Amount to increment by
            ttl: Optional TTL for the entire hash
            
        Returns:
            New counter value
        """
        try:
            client = await self.get_client()
            
            async with client.pipeline() as pipe:
                await pipe.hincrby(hash_key, field, increment)
                if ttl is not None:
                    await pipe.expire(hash_key, ttl)
                results = await pipe.execute()
                
            return results[0]
            
        except RedisError as e:
            logger.error(f"Error incrementing hash counter for '{hash_key}:{field}': {e}")
            raise
    
    async def get_hash_counter_values(self, hash_key: str) -> Dict[str, int]:
        """
        Get all counter values from a hash.
        
        Args:
            hash_key: Redis hash key
            
        Returns:
            Dictionary of field:value pairs (as integers)
        """
        try:
            client = await self.get_client()
            raw_values = await client.hgetall(hash_key)
            
            # Convert string values to integers
            return {
                field: int(value) if isinstance(value, (str, bytes)) and value.isdigit() else 0
                for field, value in raw_values.items()
            }
            
        except RedisError as e:
            logger.error(f"Error getting hash counter values for '{hash_key}': {e}")
            raise
    
    async def delete_keys_by_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a pattern.
        
        Args:
            pattern: Redis key pattern (e.g., "prefix:*")
            
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
            logger.error(f"Error deleting keys by pattern '{pattern}': {e}")
            raise
    
    async def delete_multiple_patterns(self, patterns: List[str]) -> Dict[str, int]:
        """
        Delete keys matching multiple patterns.
        
        Args:
            patterns: List of Redis key patterns
            
        Returns:
            Dictionary mapping pattern to number of keys deleted
        """
        try:
            deleted_counts = {}
            
            for pattern in patterns:
                count = await self.delete_keys_by_pattern(pattern)
                deleted_counts[pattern] = count
                
            return deleted_counts
            
        except RedisError as e:
            logger.error(f"Error deleting multiple patterns: {e}")
            raise
    
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

        # --- Test Pool-based Concurrency Limiting ---
        print("\n--- Testing Pool-based Concurrency Limiting ---")
        pool_key = f"{TEST_PREFIX}api_pool"
        
        # Acquire resources from pool
        alloc_id1, usage1, success1 = await client.acquire_from_pool(pool_key, count=10, max_pool_size=50, ttl=30)
        print(f"Acquired 10 resources: alloc_id={alloc_id1}, usage={usage1}, success={success1}")
        assert success1 is True, "Failed to acquire from pool!"
        assert usage1 == 10, "Usage mismatch!"
        
        # Acquire more resources
        alloc_id2, usage2, success2 = await client.acquire_from_pool(pool_key, count=20, max_pool_size=50, ttl=30)
        print(f"Acquired 20 more resources: alloc_id={alloc_id2}, usage={usage2}, success={success2}")
        assert success2 is True, "Failed to acquire from pool!"
        assert usage2 == 30, "Usage mismatch!"
        
        # Try to exceed pool limit
        alloc_id3, usage3, success3 = await client.acquire_from_pool(pool_key, count=25, max_pool_size=50, ttl=30)
        print(f"Tried to acquire 25 more (would exceed limit): alloc_id={alloc_id3}, usage={usage3}, success={success3}")
        assert success3 is False, "Should not exceed pool limit!"
        assert alloc_id3 is None, "Should not have allocation ID!"
        
        # Release some resources
        released1, usage_after_release1, success_release1 = await client.release_to_pool(pool_key, alloc_id1)
        print(f"Released allocation {alloc_id1}: released={released1}, usage={usage_after_release1}, success={success_release1}")
        assert success_release1 is True, "Failed to release!"
        assert released1 == 10, "Released count mismatch!"
        assert usage_after_release1 == 20, "Usage after release mismatch!"
        
        # Now we should be able to acquire more
        alloc_id4, usage4, success4 = await client.acquire_from_pool(pool_key, count=25, max_pool_size=50, ttl=30)
        print(f"Acquired 25 after release: alloc_id={alloc_id4}, usage={usage4}, success={success4}")
        assert success4 is True, "Should be able to acquire after release!"
        assert usage4 == 45, "Usage mismatch!"
        
        # Get pool info
        pool_info = await client.get_pool_info(pool_key)
        print(f"Pool info: {pool_info}")
        assert pool_info['current_usage'] == 45, "Pool info usage mismatch!"
        assert pool_info['max_size'] == 50, "Pool max size mismatch!"
        
        # Clean up pool
        await client.reset_pool(pool_key)
        print(f"Reset pool '{pool_key}'")
        
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
