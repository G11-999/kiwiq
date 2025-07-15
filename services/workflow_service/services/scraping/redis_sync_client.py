"""
Synchronous Redis client for Scrapy integration.

This uses the synchronous redis-py library to avoid event loop conflicts
with Scrapy's Twisted reactor.
"""

import redis
import json
import time
import uuid
import threading
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse
from datetime import timedelta
from redis.exceptions import ConnectionError, AuthenticationError, TimeoutError, ResponseError, RedisError

from global_config.logger import get_logger

logger = get_logger(__name__)


class SyncRedisClient:
    """
    Synchronous Redis client for Scrapy integration.
    
    This client provides the same interface as AsyncRedisClient but uses
    synchronous operations compatible with Scrapy's scheduler.
    
    Features:
    - Connection Pooling with lazy initialization
    - Queue Management for Scrapy
    - Counter/Limit Tracking
    - Memory monitoring
    - Thread-safe counter operations with per-key locking
    
    IMPORTANT: This client is designed to be shared across components.
    The connection pool is thread-safe and handles concurrent access.
    DO NOT create multiple instances pointing to the same Redis server
    as this defeats the purpose of connection pooling.
    
    Best practice:
    - Create one instance per Redis server in your application
    - Share this instance across spider, scheduler, and other components
    - The client will manage connections efficiently via the pool
    """
    
    def __init__(
        self, 
        redis_url: str = "redis://localhost:6379/0",
        pool_size: int = 50,
        socket_connect_timeout: float = 5.0,
        decode_responses: bool = True,
    ):
        """
        Initialize Redis client with connection pool configuration.
        
        Args:
            redis_url: Redis connection URL (e.g., "redis://default:password@host:port/db")
            pool_size: Maximum number of connections in the pool
            socket_connect_timeout: Socket connection timeout in seconds
            decode_responses: Whether to decode responses from Redis
        """
        if not redis_url:
            raise ValueError("Redis URL cannot be empty.")
            
        self.redis_url = redis_url
        self.pool_size = pool_size
        self.socket_connect_timeout = socket_connect_timeout
        self._pool: Optional[redis.ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._decode_responses = decode_responses
        
        # Lock pool for thread-safe counter operations
        # Each counter key gets its own lock to avoid contention
        self._counter_locks: Dict[str, threading.RLock] = {}
        self._locks_lock = threading.RLock()  # Lock to protect the lock dictionary itself
        
        logger.info(f"Redis sync client configured. Target URL (credentials masked): {self._mask_url_password(redis_url)}")
        logger.debug(f"Redis sync client configured with pool size {pool_size}")
    
    def _get_counter_lock(self, key: str) -> threading.RLock:
        """
        Get or create a lock for a specific counter key.
        
        This method ensures thread-safe access to counter operations by providing
        a unique lock for each counter key, avoiding contention between different
        counters while ensuring thread safety for operations on the same counter.
        
        Args:
            key: The Redis counter key
            
        Returns:
            A reentrant lock for the specified key
        """
        # First check if lock exists (common case, no locking needed)
        if key in self._counter_locks:
            return self._counter_locks[key]
        
        # Lock doesn't exist, need to create it thread-safely
        with self._locks_lock:
            # Double-check pattern - another thread might have created it
            if key in self._counter_locks:
                return self._counter_locks[key]
            
            # Create new lock for this key
            lock = threading.RLock()
            self._counter_locks[key] = lock
            logger.debug(f"Created new counter lock for key: {key}")
            return lock
        
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
                    socket_keepalive=True,
                )
            except (RedisError, ValueError) as e:
                logger.error(f"Failed to create connection pool: {e}")
                raise ConnectionError(f"Failed to create connection pool: {e}") from e
        return self._pool
        
    def _get_client(self) -> redis.Redis:
        """
        Lazily creates and returns a client instance from the pool.
        Performs a PING check on first creation to ensure basic connectivity.
        """
        if self._client is None:
            logger.info("Client not initialized. Creating client from pool.")
            pool = self._get_pool()
            try:
                self._client = redis.Redis(connection_pool=pool)
                # Perform an initial ping check
                logger.debug("Performing initial PING check...")
                if not self.ping():
                    # Cleanup if initial ping fails
                    self._cleanup_connection()
                    raise ConnectionError("Initial PING check failed after creating client.")
                logger.info("Client created and initial PING successful.")
            except (AuthenticationError, ConnectionError, TimeoutError, RedisError) as e:
                logger.error(f"Failed to create client or initial ping failed: {e}")
                self._cleanup_connection()
                raise ConnectionError(f"Failed to create client or initial ping failed: {e}") from e
            except Exception as e:
                logger.error(f"Unexpected error creating client: {e}", exc_info=True)
                self._cleanup_connection()
                raise ConnectionError(f"Unexpected error creating client: {e}") from e
        
        return self._client
        
    def _cleanup_connection(self) -> None:
        """Safely closes pool and resets client state."""
        logger.debug("Cleaning up Redis connection state...")
        pool = self._pool
        client = self._client
        self._client = None
        self._pool = None
        
        if client:
            try:
                client.close()
            except Exception:
                logger.exception("Error closing client instance during cleanup.")
        
        if pool:
            try:
                pool.disconnect()
                logger.debug("Connection pool disconnected.")
            except Exception:
                logger.exception("Error disconnecting connection pool during cleanup.")
        
    def close(self):
        """Close the Redis connection pool gracefully."""
        logger.info("Closing Redis sync connection...")
        
        # Clean up counter locks
        with self._locks_lock:
            lock_count = len(self._counter_locks)
            self._counter_locks.clear()
            if lock_count > 0:
                logger.debug(f"Cleared {lock_count} counter locks")
        
        self._cleanup_connection()
        logger.info("Redis sync client closed.")
            
    def ping(self) -> bool:
        """
        Checks connectivity to Redis using the PING command.
        
        Returns:
            True if PING is successful, False otherwise
        """
        try:
            # Get client instance (handles connection/creation)
            client = self._get_client()
            # ping() returns True on success
            result = client.ping()
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
            
    # Queue Management Methods
    
    def push_request(
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
            client = self._get_client()
            
            # Use URL as dedupe key if not provided
            if dedupe_key is None:
                dedupe_key = request_data.get('url', '')
                
            # Check for duplicates
            dupefilter_key = f"{queue_key}:dupefilter"
            is_duplicate = client.sismember(dupefilter_key, dedupe_key)
            
            if is_duplicate:
                logger.debug(f"Duplicate request filtered: {dedupe_key}")
                return False
                
            # Add to queue and dupefilter atomically
            pipe = client.pipeline()
            # Add to priority queue (sorted set)
            pipe.zadd(queue_key, {json.dumps(request_data): -priority})
            # Add to dupefilter set
            pipe.sadd(dupefilter_key, dedupe_key)
            # Set TTL on dupefilter (7 days)
            pipe.expire(dupefilter_key, 7 * 86400)
            results = pipe.execute()
            
            added_to_queue = results[0] == 1
            logger.debug(f"Request queued: {dedupe_key}, priority: {priority}")
            return added_to_queue
            
        except RedisError as e:
            logger.error(f"Error pushing request to queue '{queue_key}': {e}")
            raise
            
    def push_request_safe(
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
            memory_usage = self.check_memory_usage()
            if memory_usage > 90:  # 90% threshold
                logger.warning(f"Redis memory usage at {memory_usage:.1f}%, skipping request")
                return False
                
            return self.push_request(queue_key, request_data, priority, dedupe_key)
            
        except RedisError as e:
            logger.error(f"Error in push_request_safe: {e}")
            raise
            
    def pop_request(self, queue_key: str) -> Optional[Dict[str, Any]]:
        """
        Pop highest priority request from the queue.
        
        Args:
            queue_key: Redis key for the queue
            
        Returns:
            Request data dict or None if queue empty
        """
        try:
            client = self._get_client()
            
            # Pop highest priority (lowest score) item
            result = client.zpopmin(queue_key, count=1)
            
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
            
    def get_queue_length(self, queue_key: str) -> int:
        """
        Get the current length of the request queue.
        
        Args:
            queue_key: Redis key for the queue
            
        Returns:
            Number of requests in queue
        """
        try:
            client = self._get_client()
            return client.zcard(queue_key)
        except RedisError as e:
            logger.error(f"Error getting queue length for '{queue_key}': {e}")
            raise
            
    def clear_queue(self, queue_key: str, clear_dupefilter: bool = True) -> Tuple[int, int]:
        """
        Clear the request queue and optionally the dupefilter.
        
        Args:
            queue_key: Redis key for the queue
            clear_dupefilter: Whether to also clear the dupefilter set
            
        Returns:
            Tuple of (queue_items_removed, dupefilter_items_removed)
        """
        try:
            client = self._get_client()
            
            # Get counts before deletion
            queue_count = client.zcard(queue_key)
            dupefilter_key = f"{queue_key}:dupefilter"
            dupefilter_count = client.scard(dupefilter_key) if clear_dupefilter else 0
            
            pipe = client.pipeline()
            # Delete the queue
            pipe.delete(queue_key)
            
            # Optionally delete dupefilter
            if clear_dupefilter:
                pipe.delete(dupefilter_key)
                
            pipe.execute()
            
            logger.info(f"Cleared queue '{queue_key}': {queue_count} items, "
                       f"dupefilter: {dupefilter_count} items")
            
            return queue_count, dupefilter_count
            
        except RedisError as e:
            logger.error(f"Error clearing queue '{queue_key}': {e}")
            raise
            
    def get_queue_stats(self, queue_key: str) -> Dict[str, Any]:
        """
        Get statistics about the request queue.
        
        Args:
            queue_key: Redis key for the queue
            
        Returns:
            Dictionary with queue statistics
        """
        try:
            client = self._get_client()
            dupefilter_key = f"{queue_key}:dupefilter"
            
            pipe = client.pipeline()
            pipe.zcard(queue_key)  # Queue size
            pipe.scard(dupefilter_key)  # Dupefilter size
            pipe.ttl(dupefilter_key)  # Dupefilter TTL
            # Get priority range
            pipe.zrange(queue_key, 0, 0, withscores=True)  # Highest priority
            pipe.zrange(queue_key, -1, -1, withscores=True)  # Lowest priority
            
            results = pipe.execute()
            
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
            
    # Counter/Limit Tracking Methods
    
    def increment_counter_with_limit(
        self,
        key: str,
        increment: int = 1,
        limit: Optional[int] = None,
        ttl: Optional[int] = None
    ) -> Tuple[int, bool]:
        """
        Thread-safe increment of a counter with optional limit checking.
        
        This method uses per-key locking to ensure thread safety while allowing
        concurrent operations on different counters. The implementation is optimized
        for the common case where increments stay within limits.
        
        Logic:
        1. Always perform the increment (regardless of sign)
        2. If limit exceeded and increment was positive, roll back
        3. Negative increments are never rolled back
        
        Args:
            key: Redis key for the counter
            increment: Amount to increment by (can be negative for decrement)
            limit: Optional maximum value allowed (positive increments won't exceed this)
            ttl: Optional TTL in seconds
            
        Returns:
            Tuple of (current_count, is_at_or_over_limit)
            - current_count: The value after operation (may be rolled back if limit exceeded)
            - is_at_or_over_limit: True if current value >= limit
        """
        # Get the lock for this specific counter key
        lock = self._get_counter_lock(key)
        
        with lock:
            try:
                client = self._get_client()
                
                # Always perform the increment first
                pipe = client.pipeline()
                pipe.incrby(key, increment)
                if ttl is not None:
                    pipe.expire(key, ttl)
                results = pipe.execute()
                
                new_count = results[0]
                
                # Check if we need to roll back (only for positive increments that exceed limit)
                if limit is not None and increment > 0 and new_count > limit:
                    # Roll back the increment
                    pipe = client.pipeline()
                    pipe.incrby(key, -increment)
                    if ttl is not None:
                        pipe.expire(key, ttl)
                    rollback_results = pipe.execute()
                    
                    final_count = rollback_results[0]
                    logger.debug(
                        f"Counter '{key}' increment rolled back due to limit "
                        f"({new_count} > {limit}): reverted to {final_count}"
                    )
                    return final_count, True  # At or over limit
                
                # No rollback needed - return the new count
                is_over_limit = limit is not None and new_count >= limit
                logger.debug(f"Counter '{key}' changed by {increment}: -> {new_count}")
                return new_count, is_over_limit
                
            except RedisError as e:
                logger.error(f"Error in increment_counter_with_limit for key '{key}': {e}")
                raise
            except ValueError as e:
                logger.error(f"Error parsing counter value for key '{key}': {e}")
                raise
            
    def get_counter_value(self, key: str) -> int:
        """
        Get current value of a counter.
        
        Args:
            key: Redis key for the counter
            
        Returns:
            Current counter value (0 if key doesn't exist)
        """
        try:
            client = self._get_client()
            value = client.get(key)
            return int(value) if value else 0
            
        except (RedisError, ValueError) as e:
            logger.error(f"Error getting counter value for key '{key}': {e}")
            if isinstance(e, RedisError):
                raise
            return 0
            
    def increment_hash_counter(
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
            client = self._get_client()
            
            pipe = client.pipeline()
            pipe.hincrby(hash_key, field, increment)
            if ttl is not None:
                pipe.expire(hash_key, ttl)
            results = pipe.execute()
            
            return results[0]
            
        except RedisError as e:
            logger.error(f"Error incrementing hash counter for '{hash_key}:{field}': {e}")
            raise
            
    def get_hash_counter_values(self, hash_key: str) -> Dict[str, int]:
        """
        Get all counter values from a hash.
        
        Args:
            hash_key: Redis hash key
            
        Returns:
            Dictionary of field:value pairs (as integers)
        """
        try:
            client = self._get_client()
            raw_values = client.hgetall(hash_key)
            
            # Convert string values to integers
            return {
                field: int(value) if isinstance(value, (str, bytes)) and str(value).isdigit() else 0
                for field, value in raw_values.items()
            }
            
        except RedisError as e:
            logger.error(f"Error getting hash counter values for '{hash_key}': {e}")
            raise
            
    def delete_multiple_patterns(self, patterns: List[str]) -> Dict[str, int]:
        """
        Delete keys matching multiple patterns.
        
        Args:
            patterns: List of Redis key patterns
            
        Returns:
            Dictionary mapping pattern to number of keys deleted
        """
        try:
            client = self._get_client()
            deleted_counts = {}
            
            for pattern in patterns:
                keys = client.keys(pattern)
                if keys:
                    count = client.delete(*keys)
                    deleted_counts[pattern] = count
                else:
                    deleted_counts[pattern] = 0
                    
            return deleted_counts
            
        except RedisError as e:
            logger.error(f"Error deleting multiple patterns: {e}")
            raise
            
    def check_memory_usage(self) -> float:
        """
        Check Redis memory usage percentage.
        
        Returns:
            Memory usage percentage (0-100)
        """
        try:
            client = self._get_client()
            info = client.info('memory')
            
            used = int(info.get('used_memory', 0))
            max_memory = int(info.get('maxmemory', 0))
            
            if max_memory > 0:
                usage_percent = (used / max_memory) * 100
            else:
                # No memory limit set
                usage_percent = 0.0
                
            return float(usage_percent)
            
        except RedisError as e:
            logger.error(f"Error checking memory usage: {e}")
            return 0.0 