"""
Synchronous Redis client for Scrapy integration.

This uses the synchronous redis-py library to avoid event loop conflicts
with Scrapy's Twisted reactor.

Supports both Redis-based and in-memory storage modes for flexibility in deployment.
In-memory mode is suitable for single-process deployments where Redis might be overkill.
"""

import redis
import json
import time
import uuid
import threading
import heapq
import fnmatch
from typing import Any, Dict, List, Optional, Tuple, Set
from urllib.parse import urlparse, urlunparse
from datetime import timedelta, datetime
from collections import defaultdict
from redis.exceptions import ConnectionError, AuthenticationError, TimeoutError, ResponseError, RedisError

from global_config.logger import get_logger

logger = get_logger(__name__)


class SyncRedisClient:
    """
    Synchronous Redis client for Scrapy integration with in-memory fallback.
    
    This client provides the same interface as AsyncRedisClient but uses
    synchronous operations compatible with Scrapy's scheduler.
    
    Features:
    - Connection Pooling with lazy initialization (Redis mode)
    - In-memory storage option for single-process deployments
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
        use_in_memory: bool = False,
    ):
        """
        Initialize Redis client with connection pool configuration.
        
        Args:
            redis_url: Redis connection URL (e.g., "redis://default:password@host:port/db")
            pool_size: Maximum number of connections in the pool
            socket_connect_timeout: Socket connection timeout in seconds
            decode_responses: Whether to decode responses from Redis
            use_in_memory: If True, use in-memory storage instead of Redis
        """
        self.use_in_memory = use_in_memory
        
        if self.use_in_memory:
            logger.info("Redis sync client configured in IN-MEMORY mode")
            # Initialize in-memory storage structures
            self._memory_queues: Dict[str, List[Tuple[float, float, str]]] = {}  # Priority queues (heapq) - (negative_priority, timestamp, json_data)
            self._memory_sets: Dict[str, Set[str]] = {}  # For deduplication
            self._memory_counters: Dict[str, int] = {}  # Simple counters
            self._memory_hashes: Dict[str, Dict[str, Any]] = {}  # Hash structures
            
            # Thread locks for in-memory operations
            self._memory_lock = threading.RLock()  # Global lock for structure creation
            self._queue_locks: Dict[str, threading.RLock] = {}  # Per-queue locks
            self._set_locks: Dict[str, threading.RLock] = {}  # Per-set locks
            self._counter_locks: Dict[str, threading.RLock] = {}  # Per-counter locks
            self._hash_locks: Dict[str, threading.RLock] = {}  # Per-hash locks
        else:
            if not redis_url:
                raise ValueError("Redis URL cannot be empty when not using in-memory mode.")
                
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
            
            logger.info(f"Redis sync client configured in REDIS mode. Target URL (credentials masked): {self._mask_url_password(redis_url)}")
            logger.debug(f"Redis sync client configured with pool size {pool_size}")
    
    def _get_or_create_lock(self, lock_dict: Dict[str, threading.RLock], key: str) -> threading.RLock:
        """
        Get or create a lock for a specific key in a thread-safe manner.
        
        Args:
            lock_dict: Dictionary storing locks
            key: The key to get/create lock for
            
        Returns:
            A reentrant lock for the specified key
        """
        # First check if lock exists (common case, no locking needed)
        if key in lock_dict:
            return lock_dict[key]
        
        # Lock doesn't exist, need to create it thread-safely
        with self._memory_lock:
            # Double-check pattern - another thread might have created it
            if key in lock_dict:
                return lock_dict[key]
            
            # Create new lock for this key
            lock = threading.RLock()
            lock_dict[key] = lock
            return lock
    

    
    def _get_counter_lock(self, key: str) -> threading.RLock:
        """
        Get or create a lock for a specific counter key (Redis mode).
        
        This method ensures thread-safe access to counter operations by providing
        a unique lock for each counter key, avoiding contention between different
        counters while ensuring thread safety for operations on the same counter.
        
        Args:
            key: The Redis counter key
            
        Returns:
            A reentrant lock for the specified key
        """
        if self.use_in_memory:
            return self._get_or_create_lock(self._counter_locks, key)
        else:
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
        if self.use_in_memory:
            logger.info("Closing in-memory sync client...")
            
            # Clean up all in-memory structures
            with self._memory_lock:
                self._memory_queues.clear()
                self._memory_sets.clear()
                self._memory_counters.clear()
                self._memory_hashes.clear()
                
                # Clear all locks
                self._queue_locks.clear()
                self._set_locks.clear()
                self._counter_locks.clear()
                self._hash_locks.clear()
                
            logger.info("In-memory sync client closed.")
        else:
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
        if self.use_in_memory:
            # In-memory mode is always "connected"
            return True
            
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
        if self.use_in_memory:
            return self._push_request_memory(queue_key, request_data, priority, dedupe_key)
            
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
    
    def _push_request_memory(
        self,
        queue_key: str,
        request_data: Dict[str, Any],
        priority: int = 0,
        dedupe_key: Optional[str] = None
    ) -> bool:
        """
        In-memory implementation of push_request.
        
        Uses a min-heap (heapq) for the priority queue where lower scores have higher priority.
        Thread-safe implementation with per-queue locks.
        
        Time complexity: O(log n) for heap push
        Space complexity: O(n) where n is number of requests
        """
        # Use URL as dedupe key if not provided
        if dedupe_key is None:
            dedupe_key = request_data.get('url', '')
        
        dupefilter_key = f"{queue_key}:dupefilter"
        
        # Get or create locks for queue and set
        queue_lock = self._get_or_create_lock(self._queue_locks, queue_key)
        set_lock = self._get_or_create_lock(self._set_locks, dupefilter_key)
        
        # Check for duplicates first (with set lock)
        with set_lock:
            if dupefilter_key not in self._memory_sets:
                self._memory_sets[dupefilter_key] = set()
                
            if dedupe_key in self._memory_sets[dupefilter_key]:
                logger.debug(f"Duplicate request filtered: {dedupe_key}")
                return False
        
        # Add to queue and dupefilter atomically
        with queue_lock:
            with set_lock:
                # Initialize queue if needed
                if queue_key not in self._memory_queues:
                    self._memory_queues[queue_key] = []
                
                # Add to priority queue (use negative priority for min-heap)
                # Include timestamp for stable sorting when priorities are equal
                heapq.heappush(
                    self._memory_queues[queue_key],
                    (-priority, time.time(), json.dumps(request_data))
                )
                
                # Add to dupefilter set
                self._memory_sets[dupefilter_key].add(dedupe_key)
                
        logger.debug(f"Request queued (in-memory): {dedupe_key}, priority: {priority}")
        return True
            
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
        if self.use_in_memory:
            return self._pop_request_memory(queue_key)
            
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
    
    def _pop_request_memory(self, queue_key: str) -> Optional[Dict[str, Any]]:
        """
        In-memory implementation of pop_request.
        
        Thread-safe pop from priority queue.
        
        Time complexity: O(log n) for heap pop
        """
        # Get queue lock
        queue_lock = self._get_or_create_lock(self._queue_locks, queue_key)
        
        with queue_lock:
            if queue_key not in self._memory_queues or not self._memory_queues[queue_key]:
                return None
            
            # Pop from min-heap (highest priority = lowest negative value)
            _, _, request_json = heapq.heappop(self._memory_queues[queue_key])
            request_data = json.loads(request_json)
            
            logger.debug(f"Popped request (in-memory): {request_data.get('url', 'unknown')}")
            return request_data
            
    def get_queue_length(self, queue_key: str) -> int:
        """
        Get the current length of the request queue.
        
        Args:
            queue_key: Redis key for the queue
            
        Returns:
            Number of requests in queue
        """
        if self.use_in_memory:
            return self._get_queue_length_memory(queue_key)
            
        try:
            client = self._get_client()
            return client.zcard(queue_key)
        except RedisError as e:
            logger.error(f"Error getting queue length for '{queue_key}': {e}")
            raise
    
    def _get_queue_length_memory(self, queue_key: str) -> int:
        """
        In-memory implementation of get_queue_length.
        
        Time complexity: O(1)
        """
        # Get queue lock
        queue_lock = self._get_or_create_lock(self._queue_locks, queue_key)
        
        with queue_lock:
            if queue_key not in self._memory_queues:
                return 0
            return len(self._memory_queues[queue_key])
            
    def clear_queue(self, queue_key: str, clear_dupefilter: bool = True) -> Tuple[int, int]:
        """
        Clear the request queue and optionally the dupefilter.
        
        Args:
            queue_key: Redis key for the queue
            clear_dupefilter: Whether to also clear the dupefilter set
            
        Returns:
            Tuple of (queue_items_removed, dupefilter_items_removed)
        """
        if self.use_in_memory:
            return self._clear_queue_memory(queue_key, clear_dupefilter)
            
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
    
    def _clear_queue_memory(self, queue_key: str, clear_dupefilter: bool = True) -> Tuple[int, int]:
        """
        In-memory implementation of clear_queue.
        
        Time complexity: O(1) for deletion
        """
        dupefilter_key = f"{queue_key}:dupefilter"
        
        # Get locks
        queue_lock = self._get_or_create_lock(self._queue_locks, queue_key)
        set_lock = self._get_or_create_lock(self._set_locks, dupefilter_key)
        
        queue_count = 0
        dupefilter_count = 0
        
        # Clear queue
        with queue_lock:
            if queue_key in self._memory_queues:
                queue_count = len(self._memory_queues[queue_key])
                del self._memory_queues[queue_key]
        
        # Clear dupefilter
        if clear_dupefilter:
            with set_lock:
                if dupefilter_key in self._memory_sets:
                    dupefilter_count = len(self._memory_sets[dupefilter_key])
                    del self._memory_sets[dupefilter_key]
        
        logger.info(f"Cleared queue (in-memory) '{queue_key}': {queue_count} items, "
                   f"dupefilter: {dupefilter_count} items")
        
        return queue_count, dupefilter_count
            
    def get_queue_stats(self, queue_key: str) -> Dict[str, Any]:
        """
        Get statistics about the request queue.
        
        Args:
            queue_key: Redis key for the queue
            
        Returns:
            Dictionary with queue statistics
        """
        if self.use_in_memory:
            return self._get_queue_stats_memory(queue_key)
            
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
    
    def _get_queue_stats_memory(self, queue_key: str) -> Dict[str, Any]:
        """
        In-memory implementation of get_queue_stats.
        
        Time complexity: O(n) for priority calculation, where n is queue size
        """
        dupefilter_key = f"{queue_key}:dupefilter"
        
        # Get locks
        queue_lock = self._get_or_create_lock(self._queue_locks, queue_key)
        set_lock = self._get_or_create_lock(self._set_locks, dupefilter_key)
        
        stats = {
            'queue_size': 0,
            'dupefilter_size': 0,
            'dupefilter_ttl': -1,  # No TTL in memory mode
            'highest_priority': None,
            'lowest_priority': None,
        }
        
        # Get queue stats
        with queue_lock:
            if queue_key in self._memory_queues and self._memory_queues[queue_key]:
                queue = self._memory_queues[queue_key]
                stats['queue_size'] = len(queue)
                
                # Get priority range (remember we store negative priorities)
                # Note: This is O(n) but acceptable for stats
                priorities = [-item[0] for item in queue]
                if priorities:
                    stats['highest_priority'] = max(priorities)
                    stats['lowest_priority'] = min(priorities)
        
        # Get dupefilter stats
        with set_lock:
            if dupefilter_key in self._memory_sets:
                stats['dupefilter_size'] = len(self._memory_sets[dupefilter_key])
        
        return stats
            
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
        if self.use_in_memory:
            return self._increment_counter_with_limit_memory(key, increment, limit, ttl)
            
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
    
    def _increment_counter_with_limit_memory(
        self,
        key: str,
        increment: int = 1,
        limit: Optional[int] = None,
        ttl: Optional[int] = None
    ) -> Tuple[int, bool]:
        """
        In-memory implementation of increment_counter_with_limit.
        
        This is smarter than Redis - it enforces the limit by blocking increments
        that would exceed it, rather than allowing the counter to go over.
        
        Time complexity: O(1)
        
        Returns:
            Tuple of (current_count, is_at_or_over_limit) where:
            - current_count: The counter value after the operation
            - is_at_or_over_limit: True if at/over limit (can't increment further) or increment was blocked
        
        Note: ttl parameter is ignored in memory mode as all data is cleared
        when the process ends or client is closed.
        """
        # Get counter lock
        lock = self._get_counter_lock(key)
        
        with lock:
            # Get current value
            current_value = self._memory_counters.get(key, 0)
            
            # Calculate what the new count would be
            new_count = current_value + increment
            
            # Smart limit enforcement for in-memory implementation
            if limit is not None and increment > 0 and new_count > limit:
                # Block the increment - would exceed the limit
                logger.debug(
                    f"Counter (in-memory) '{key}' increment blocked: would exceed limit "
                    f"({new_count} > {limit}), remains at {current_value}"
                )
                return current_value, True  # Increment was blocked
            
            # Apply the increment
            self._memory_counters[key] = new_count
            
            # Check if we're now at or would exceed the limit on next increment
            is_at_limit = limit is not None and new_count >= limit
            logger.debug(f"Counter (in-memory) '{key}' incremented by {increment}: {current_value} -> {new_count}")
            return new_count, is_at_limit  # Return True if at/over limit
            
    def get_counter_value(self, key: str) -> int:
        """
        Get current value of a counter.
        
        Args:
            key: Redis key for the counter
            
        Returns:
            Current counter value (0 if key doesn't exist)
        """
        if self.use_in_memory:
            return self._get_counter_value_memory(key)
            
        try:
            client = self._get_client()
            value = client.get(key)
            return int(value) if value else 0
            
        except (RedisError, ValueError) as e:
            logger.error(f"Error getting counter value for key '{key}': {e}")
            if isinstance(e, RedisError):
                raise
            return 0
    
    def _get_counter_value_memory(self, key: str) -> int:
        """
        In-memory implementation of get_counter_value.
        
        Time complexity: O(1)
        """
        # Get counter lock
        lock = self._get_counter_lock(key)
        
        with lock:
            return self._memory_counters.get(key, 0)
            
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
        if self.use_in_memory:
            return self._increment_hash_counter_memory(hash_key, field, increment, ttl)
            
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
    
    def _increment_hash_counter_memory(
        self,
        hash_key: str,
        field: str,
        increment: int = 1,
        ttl: Optional[int] = None
    ) -> int:
        """
        In-memory implementation of increment_hash_counter.
        
        Time complexity: O(1)
        
        Note: ttl parameter is ignored in memory mode.
        """
        # Get hash lock
        lock = self._get_or_create_lock(self._hash_locks, hash_key)
        
        with lock:
            # Initialize hash if needed
            if hash_key not in self._memory_hashes:
                self._memory_hashes[hash_key] = {}
            
            # Get current value
            current_value = self._memory_hashes[hash_key].get(field, 0)
            if isinstance(current_value, str) and current_value.isdigit():
                current_value = int(current_value)
            elif not isinstance(current_value, int):
                current_value = 0
            
            # Increment
            new_value = current_value + increment
            self._memory_hashes[hash_key][field] = new_value
            
            return new_value
            
    def get_hash_counter_values(self, hash_key: str) -> Dict[str, int]:
        """
        Get all counter values from a hash.
        
        Args:
            hash_key: Redis hash key
            
        Returns:
            Dictionary of field:value pairs (as integers)
        """
        if self.use_in_memory:
            return self._get_hash_counter_values_memory(hash_key)
            
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
    
    def _get_hash_counter_values_memory(self, hash_key: str) -> Dict[str, int]:
        """
        In-memory implementation of get_hash_counter_values.
        
        Time complexity: O(n) where n is number of fields in the hash
        """
        # Get hash lock
        lock = self._get_or_create_lock(self._hash_locks, hash_key)
        
        with lock:
            if hash_key not in self._memory_hashes:
                return {}
            
            # Convert values to integers
            result = {}
            for field, value in self._memory_hashes[hash_key].items():
                if isinstance(value, int):
                    result[field] = value
                elif isinstance(value, str) and value.isdigit():
                    result[field] = int(value)
                else:
                    result[field] = 0
            
            return result
            
    def delete_multiple_patterns(self, patterns: List[str]) -> Dict[str, int]:
        """
        Delete keys matching multiple patterns.
        
        Args:
            patterns: List of Redis key patterns
            
        Returns:
            Dictionary mapping pattern to number of keys deleted
        """
        if self.use_in_memory:
            return self._delete_multiple_patterns_memory(patterns)
            
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
    
    def _delete_multiple_patterns_memory(self, patterns: List[str]) -> Dict[str, int]:
        """
        In-memory implementation of delete_multiple_patterns.
        
        Time complexity: O(n * m) where n is total keys and m is number of patterns
        Uses fnmatch for Unix shell-style pattern matching.
        """
        deleted_counts = {}
        
        with self._memory_lock:
            for pattern in patterns:
                count = 0
                
                # Find all keys matching the pattern
                all_keys = set()
                all_keys.update(self._memory_queues.keys())
                all_keys.update(self._memory_sets.keys())
                all_keys.update(self._memory_counters.keys())
                all_keys.update(self._memory_hashes.keys())
                
                # Match keys against pattern using Unix shell-style wildcards
                matching_keys = [k for k in all_keys if fnmatch.fnmatch(k, pattern)]
                
                # Delete matching keys
                for key in matching_keys:
                    # Remove from all possible storages (a key might exist in multiple structures)
                    if key in self._memory_queues:
                        del self._memory_queues[key]
                        count += 1
                    if key in self._memory_sets:
                        del self._memory_sets[key]
                        count += 1
                    if key in self._memory_counters:
                        del self._memory_counters[key]
                        count += 1
                    if key in self._memory_hashes:
                        del self._memory_hashes[key]
                        count += 1
                    
                    # Remove associated locks
                    self._queue_locks.pop(key, None)
                    self._set_locks.pop(key, None)
                    self._counter_locks.pop(key, None)
                    self._hash_locks.pop(key, None)
                
                deleted_counts[pattern] = count
        
        return deleted_counts
            
    def check_memory_usage(self) -> float:
        """
        Check Redis memory usage percentage.
        
        Returns:
            Memory usage percentage (0-100)
        """
        if self.use_in_memory:
            # In-memory mode doesn't have meaningful memory limits
            # Could implement system memory checks if needed
            return 0.0
            
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
    
    # Pool-based Resource Management Methods
    
    def acquire_from_pool(
        self,
        pool_key: str,
        count: int = 1,
        max_pool_size: int = 10,
        ttl: int = 900  # 15 minutes default
    ) -> Tuple[Optional[str], int, bool]:
        """
        Acquire resources from a concurrency pool with distributed synchronization.
        
        This method provides thread-safe and process-safe resource acquisition using Redis
        or in-memory storage. It ensures that the total concurrent usage never exceeds
        the configured maximum.
        
        Args:
            pool_key: Unique identifier for the pool (e.g., "scrapeless_browsers")
            count: Number of resources to acquire
            max_pool_size: Maximum allowed concurrent resources
            ttl: Time-to-live for the allocation in seconds
            
        Returns:
            Tuple of (allocation_id, current_usage, success) where:
                - allocation_id: Unique ID for this allocation (None if failed)
                - current_usage: Current total usage of the pool
                - success: Whether the acquisition was successful
        """
        if self.use_in_memory:
            # In-memory implementation (single process only)
            with self._memory_lock:
                # Initialize pool data if not exists
                if pool_key not in self._memory_counters:
                    self._memory_counters[pool_key] = 0
                    self._memory_hashes[pool_key] = {}
                
                current_usage = self._memory_counters[pool_key]
                
                # Check if we can acquire
                if current_usage + count > max_pool_size:
                    return None, current_usage, False
                
                # Generate allocation ID
                allocation_id = str(uuid.uuid4())
                
                # Update usage
                self._memory_counters[pool_key] += count
                new_usage = self._memory_counters[pool_key]
                
                # Store allocation info
                expiry_time = time.time() + ttl
                self._memory_hashes[pool_key][allocation_id] = {
                    'count': count,
                    'expiry': expiry_time
                }
                
                logger.debug(f"Acquired {count} from in-memory pool '{pool_key}', "
                           f"allocation: {allocation_id}, usage: {new_usage}/{max_pool_size}")
                return allocation_id, new_usage, True
        
        try:
            client = self._get_client()
            max_retries = 10
            
            for retry in range(max_retries):
                allocation_id = str(uuid.uuid4())
                now = time.time()
                expiry = now + ttl
                
                # Keys for pool management
                pool_hash_key = f"pool:{pool_key}"
                allocs_key = f"pool:{pool_key}:allocs"
                alloc_key = f"pool:{pool_key}:alloc:{allocation_id}"
                
                # Use WATCH for optimistic locking
                pipe = client.pipeline()
                try:
                    # Watch both keys
                    pipe.watch(pool_hash_key, allocs_key)
                    
                    # Get current state (non-transactional reads)
                    pool_data = pipe.hgetall(pool_hash_key)
                    current_usage = int(pool_data.get('current', '0'))
                    stored_max = int(pool_data.get('max', str(max_pool_size)))
                    
                    # Use the stored max if it exists, otherwise use provided max
                    effective_max = stored_max if pool_data else max_pool_size
                    
                    # Get expired allocations
                    expired = pipe.zrangebyscore(allocs_key, 0, now)
                    
                    # Calculate expired count if any
                    expired_count = 0
                    if expired:
                        for expired_id in expired:
                            expired_alloc_key = f"pool:{pool_key}:alloc:{expired_id}"
                            expired_val = pipe.get(expired_alloc_key)
                            if expired_val:
                                expired_count += int(expired_val)
                    
                    # Calculate actual current usage after accounting for expired
                    actual_usage = max(0, current_usage - expired_count)
                    
                    # Check if we can acquire
                    if actual_usage + count > effective_max:
                        pipe.unwatch()
                        return None, actual_usage, False
                    
                    # Start transaction
                    pipe.multi()
                    
                    # Update pool state with actual usage
                    new_usage = actual_usage + count
                    pipe.hset(pool_hash_key, mapping={
                        'current': str(new_usage),
                        'max': str(effective_max)
                    })
                    
                    # Store allocation
                    pipe.set(alloc_key, str(count))
                    pipe.zadd(allocs_key, {allocation_id: expiry})
                    # Set a longer TTL as a safety measure (2x the allocation TTL)
                    pipe.expire(alloc_key, ttl * 2)
                    
                    # Clean up expired allocations
                    if expired:
                        pipe.zrem(allocs_key, *expired)
                        for expired_id in expired:
                            pipe.delete(f"pool:{pool_key}:alloc:{expired_id}")
                    
                    # Execute transaction
                    pipe.execute()
                    logger.debug(f"Acquired {count} from pool '{pool_key}', "
                               f"allocation: {allocation_id}, usage: {new_usage}/{effective_max}")
                    return allocation_id, new_usage, True
                    
                except redis.WatchError:
                    logger.debug(f"Watch error on pool acquire attempt {retry + 1}, retrying...")
                    time.sleep(0.01 * retry)  # Small backoff
                    continue
            
            # Max retries exceeded
            current_usage = self.get_pool_usage(pool_key)
            return None, current_usage, False
            
        except RedisError as e:
            logger.error(f"Error acquiring from pool '{pool_key}': {e}")
            raise
    
    def release_to_pool(
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
        if self.use_in_memory:
            # In-memory implementation
            with self._memory_lock:
                if pool_key not in self._memory_hashes:
                    return 0, 0, False
                
                alloc_info = self._memory_hashes[pool_key].get(allocation_id)
                if not alloc_info:
                    logger.warning(f"Allocation {allocation_id} not found for in-memory pool '{pool_key}'")
                    return 0, self._memory_counters.get(pool_key, 0), False
                
                # Release the resources
                count = alloc_info['count']
                self._memory_counters[pool_key] = max(0, self._memory_counters[pool_key] - count)
                new_usage = self._memory_counters[pool_key]
                
                # Remove allocation
                del self._memory_hashes[pool_key][allocation_id]
                
                logger.debug(f"Released {count} to in-memory pool '{pool_key}', "
                           f"allocation: {allocation_id}, usage: {new_usage}")
                return count, new_usage, True
        
        try:
            client = self._get_client()
            max_retries = 10
            
            for retry in range(max_retries):
                # Keys for pool management
                pool_hash_key = f"pool:{pool_key}"
                allocs_key = f"pool:{pool_key}:allocs"
                alloc_key = f"pool:{pool_key}:alloc:{allocation_id}"
                
                # Start transaction with WATCH
                pipe = client.pipeline()
                
                # Watch the pool hash and allocation
                pipe.watch(pool_hash_key, alloc_key)
                
                # Get allocation count
                alloc_count_str = pipe.get(alloc_key)
                if not alloc_count_str:
                    # Allocation doesn't exist or already released
                    pipe.unwatch()
                    current_usage = self.get_pool_usage(pool_key)
                    logger.warning(f"Allocation {allocation_id} not found for pool '{pool_key}' during release")
                    return 0, current_usage, False
                
                alloc_count = int(alloc_count_str)
                
                # Get current pool state
                pool_data = pipe.hgetall(pool_hash_key)
                current_usage = int(pool_data.get('current', '0'))
                
                # Start transaction
                pipe.multi()
                
                # Update pool state
                new_usage = max(0, current_usage - alloc_count)
                pipe.hset(pool_hash_key, 'current', str(new_usage))
                
                # Remove allocation
                pipe.delete(alloc_key)
                pipe.zrem(allocs_key, allocation_id)
                
                try:
                    pipe.execute()
                    logger.debug(f"Released {alloc_count} to pool '{pool_key}', "
                               f"allocation: {allocation_id}, usage: {new_usage}")
                    return alloc_count, new_usage, True
                except redis.WatchError:
                    logger.debug(f"Watch error on pool release attempt {retry + 1}, retrying...")
                    time.sleep(0.01 * retry)  # Small exponential backoff
                    continue
            
            # Max retries exceeded
            current_usage = self.get_pool_usage(pool_key)
            return 0, current_usage, False
            
        except RedisError as e:
            logger.error(f"Error releasing to pool '{pool_key}': {e}")
            raise
    
    def get_pool_usage(self, pool_key: str) -> int:
        """
        Get current usage of a concurrency pool.
        
        Args:
            pool_key: The pool identifier
            
        Returns:
            Current usage count
        """
        if self.use_in_memory:
            # In-memory implementation
            with self._memory_lock:
                # Clean up expired allocations first
                self._cleanup_in_memory_pool_expired(pool_key)
                return self._memory_counters.get(pool_key, 0)
        
        try:
            client = self._get_client()
            pool_hash_key = f"pool:{pool_key}"
            
            # Clean up expired allocations first
            self._cleanup_pool_expired_allocations(pool_key)
            
            # Get the updated usage after cleanup
            pool_data = client.hget(pool_hash_key, 'current')
            return int(pool_data) if pool_data else 0
            
        except RedisError as e:
            logger.error(f"Error getting pool usage for '{pool_key}': {e}")
            raise
    
    def get_pool_info(self, pool_key: str) -> Dict[str, Any]:
        """
        Get detailed information about a concurrency pool.
        
        Args:
            pool_key: The pool identifier
            
        Returns:
            Dictionary with pool information including usage, max size, allocations
        """
        if self.use_in_memory:
            # In-memory implementation
            with self._memory_lock:
                # Clean up expired allocations first
                self._cleanup_in_memory_pool_expired(pool_key)
                
                current_usage = self._memory_counters.get(pool_key, 0)
                allocations = []
                
                if pool_key in self._memory_hashes:
                    for alloc_id, alloc_info in self._memory_hashes[pool_key].items():
                        allocations.append({
                            'id': alloc_id,
                            'count': alloc_info['count'],
                            'expiry': alloc_info['expiry'],
                            'ttl': max(0, alloc_info['expiry'] - time.time())
                        })
                
                return {
                    'current_usage': current_usage,
                    'max_size': None,  # Not stored in memory mode
                    'allocation_count': len(allocations),
                    'allocations': allocations,
                    'mode': 'in-memory'
                }
        
        try:
            client = self._get_client()
            pool_hash_key = f"pool:{pool_key}"
            allocs_key = f"pool:{pool_key}:allocs"
            
            # Clean up expired allocations first
            self._cleanup_pool_expired_allocations(pool_key)
            
            # Get pool state
            pool_data = client.hgetall(pool_hash_key)
            current_usage = int(pool_data.get('current', '0'))
            max_size = int(pool_data.get('max', '0'))
            
            # Get all allocations with scores (expiry times)
            allocations = []
            alloc_data = client.zrange(allocs_key, 0, -1, withscores=True)
            
            for alloc_id, expiry in alloc_data:
                alloc_key = f"pool:{pool_key}:alloc:{alloc_id}"
                count = client.get(alloc_key)
                if count:
                    allocations.append({
                        'id': alloc_id,
                        'count': int(count),
                        'expiry': expiry,
                        'ttl': max(0, expiry - time.time())
                    })
            
            return {
                'current_usage': current_usage,
                'max_size': max_size,
                'allocation_count': len(allocations),
                'allocations': allocations,
                'mode': 'redis'
            }
            
        except RedisError as e:
            logger.error(f"Error getting pool info for '{pool_key}': {e}")
            raise
    
    def _cleanup_pool_expired_allocations(self, pool_key: str) -> int:
        """
        Clean up expired allocations from a pool (Redis mode).
        
        Args:
            pool_key: The pool identifier
            
        Returns:
            Number of allocations cleaned up
        """
        try:
            client = self._get_client()
            pool_hash_key = f"pool:{pool_key}"
            allocs_key = f"pool:{pool_key}:allocs"
            
            now = time.time()
            max_retries = 3
            
            logger.debug(f"Starting cleanup for pool '{pool_key}' at time {now}")
            
            for retry in range(max_retries):
                pipe = client.pipeline()
                
                # Watch the pool hash
                pipe.watch(pool_hash_key)
                
                # Get expired allocations
                expired = pipe.zrangebyscore(allocs_key, 0, now)
                if not expired:
                    pipe.unwatch()
                    return 0
                
                # Get current usage
                current_usage = pipe.hget(pool_hash_key, 'current')
                current_usage = int(current_usage) if current_usage else 0
                
                # Calculate total to release
                total_to_release = 0
                for expired_id in expired:
                    alloc_key = f"pool:{pool_key}:alloc:{expired_id}"
                    count = pipe.get(alloc_key)
                    if count:
                        total_to_release += int(count)
                
                # Start transaction
                pipe.multi()
                
                # Update pool usage
                new_usage = max(0, current_usage - total_to_release)
                if total_to_release > 0:
                    pipe.hset(pool_hash_key, 'current', str(new_usage))
                
                # Remove expired allocations
                pipe.zrem(allocs_key, *expired)
                for expired_id in expired:
                    pipe.delete(f"pool:{pool_key}:alloc:{expired_id}")
                
                try:
                    results = pipe.execute()
                    if len(expired) > 0:
                        logger.info(f"Cleaned up {len(expired)} expired allocations "
                                   f"from pool '{pool_key}', released {total_to_release} resources, "
                                   f"new usage: {new_usage}")
                    return len(expired)
                except redis.WatchError:
                    logger.warning(f"Watch error on cleanup attempt {retry + 1}, retrying...")
                    time.sleep(0.01 * retry)  # Small exponential backoff
                    continue
            
            return 0
            
        except RedisError as e:
            logger.error(f"Error cleaning up pool '{pool_key}': {e}")
            raise
    
    def _cleanup_in_memory_pool_expired(self, pool_key: str) -> int:
        """
        Clean up expired allocations from an in-memory pool.
        
        Args:
            pool_key: The pool identifier
            
        Returns:
            Number of allocations cleaned up
        """
        if pool_key not in self._memory_hashes:
            return 0
        
        now = time.time()
        expired_allocs = []
        total_to_release = 0
        
        # Find expired allocations
        for alloc_id, alloc_info in self._memory_hashes[pool_key].items():
            if alloc_info['expiry'] <= now:
                expired_allocs.append(alloc_id)
                total_to_release += alloc_info['count']
        
        # Remove expired allocations and update counter
        for alloc_id in expired_allocs:
            del self._memory_hashes[pool_key][alloc_id]
        
        if total_to_release > 0:
            self._memory_counters[pool_key] = max(0, self._memory_counters[pool_key] - total_to_release)
            logger.info(f"Cleaned up {len(expired_allocs)} expired allocations "
                       f"from in-memory pool '{pool_key}', released {total_to_release} resources")
        
        return len(expired_allocs)
    
    def reset_pool(self, pool_key: str) -> bool:
        """
        Reset a concurrency pool, clearing all allocations.
        
        Args:
            pool_key: The pool identifier
            
        Returns:
            True if pool was reset
        """
        if self.use_in_memory:
            # In-memory implementation
            with self._memory_lock:
                if pool_key in self._memory_counters:
                    self._memory_counters[pool_key] = 0
                if pool_key in self._memory_hashes:
                    self._memory_hashes[pool_key] = {}
                logger.debug(f"Reset in-memory pool '{pool_key}'")
                return True
        
        try:
            client = self._get_client()
            
            # Keys to delete
            keys_to_delete = [
                f"pool:{pool_key}",
                f"pool:{pool_key}:allocs"
            ]
            
            # Get all allocation keys
            allocs_key = f"pool:{pool_key}:allocs"
            allocations = client.zrange(allocs_key, 0, -1)
            for alloc_id in allocations:
                keys_to_delete.append(f"pool:{pool_key}:alloc:{alloc_id}")
            
            # Delete all keys
            if keys_to_delete:
                client.delete(*keys_to_delete)
                logger.debug(f"Reset pool '{pool_key}', deleted {len(keys_to_delete)} keys")
                return True
                
            return False
            
        except RedisError as e:
            logger.error(f"Error resetting pool '{pool_key}': {e}")
            raise 