# Redis for Asynchronous Applications

## 1. Introduction to AsyncRedisClient

AsyncRedisClient is a high-performance, asynchronous wrapper for Redis, providing streamlined access to Redis features while adding robust error handling and connection management. This library excels in modern asyncio-based Python applications where non-blocking operations are essential.

```python
client = AsyncRedisClient(
    redis_url="redis://username:password@localhost:6379/0",
    pool_size=50,
    default_ttl_seconds=3600,
    socket_connect_timeout=5.0
)
```

## 2. Redis Core Concepts

### Keys and Values
- Redis is a key-value store where keys are strings
- Values can have different data types (strings, lists, sets, hashes, sorted sets)
- Our client primarily works with JSON-serialized values for flexibility

### Connection Pool
- Manages multiple connections to Redis server
- Allows concurrent operations without creating new connections
- Improves performance under high concurrency

### Expiration (TTL)
- Time-to-live defines how long a key exists before automatic deletion
- Can be applied to any key regardless of data type
- Enables automatic cache invalidation

### Atomicity
- Redis commands are atomic, including complex operations with pipelines
- Important for race-condition-free operations
- Leveraged in our distributed locking implementation

## 3. Client Features Overview

### Rate Limiting
- Sliding window implementation for accurate rate limiting
- Tracks events over time using Redis sorted sets
- Supports flexible window sizes and limits
- Multi-window rate limiting for complex rate limit policies

### Key-Value Caching
- JSON serialization for structured data
- Configurable TTL at both client and operation level
- Atomic set and expire operations

### Distributed Locking
- Mutex locks across distributed systems
- Token-based ownership verification
- Automatic lock release with context manager

## 4. Basic Operations

### Setting and Getting Values
```python
# Store a Python object as JSON
await client.set_cache(
    key="user:1001",
    value={"name": "Alice", "roles": ["admin", "editor"]},
    ttl=3600  # seconds
)

# Retrieve the object
user = await client.get_cache("user:1001")
```

### Deleting Values
```python
# Delete a specific key
success = await client.delete_cache("user:1001")

# Delete multiple keys by pattern
count = await client.flush_cache("user:*")
```

### Connection Management
```python
# Check if Redis is available
is_connected = await client.ping()

# Close connections properly when done
await client.close()
```

## 5. Rate Limiting Implementation

### Basic Rate Limiting
```python
# Register an event and check if rate limited
key = "api:client:123"
count, limited = await client.register_event(key, window_seconds=60)

# Rate limit at 100 requests per minute
is_limited = await client.is_rate_limited(
    key="api:client:123",
    max_events=100,
    window_seconds=60
)

if is_limited:
    # Return 429 Too Many Requests
    return "Rate limit exceeded"
```

### Multi-Window Rate Limiting

The client supports rate limiting across multiple time windows simultaneously, allowing you to implement complex rate limit policies such as "100 requests per minute, 1,000 requests per hour, and 10,000 requests per day" with a single Redis round-trip.

#### Checking Multiple Windows
```python
# Define your rate limits: [(max_events, window_seconds), ...]
limits = [
    (100, 60),     # 100 requests per minute
    (1000, 3600),  # 1000 requests per hour
    (10000, 86400) # 10000 requests per day
]

# Check if rate limited across all windows
client_id = "123"
key_prefix = f"rate:client:{client_id}"
is_limited, counts = await client.check_multi_window_rate_limits(key_prefix, limits)

if is_limited:
    # Return 429 Too Many Requests
    return "Rate limit exceeded"
else:
    # Process the request
    return "Request accepted"
```

#### Registering Events Across Multiple Windows
```python
# Register an event across multiple windows
client_id = "123"
key_prefix = f"rate:client:{client_id}"
windows = [60, 3600, 86400]  # minute, hour, day

# Returns counts for each window
counts = await client.register_multi_window_event(key_prefix, windows)

# You can use the counts to inform the client about their rate limit usage
response = {
    "status": "success",
    "rate_limits": {
        "minute": {
            "used": counts[60],
            "limit": 100,
            "remaining": max(0, 100 - counts[60])
        },
        "hour": {
            "used": counts[3600],
            "limit": 1000,
            "remaining": max(0, 1000 - counts[3600])
        },
        "day": {
            "used": counts[86400],
            "limit": 10000,
            "remaining": max(0, 10000 - counts[86400])
        }
    }
}
```

#### Comprehensive Rate Limiting API
```python
# Complete rate limiting flow with multi-window support
async def handle_api_request(client_id, request_data):
    # Define rate limit windows
    limits = [
        (100, 60),     # 100 requests per minute
        (1000, 3600),  # 1000 requests per hour
        (10000, 86400) # 10000 requests per day
    ]
    
    key_prefix = f"rate:client:{client_id}"
    
    # Check if already rate limited
    is_limited, counts = await client.check_multi_window_rate_limits(key_prefix, limits)
    
    if is_limited:
        # Determine which limit was exceeded for detailed response
        exceeded_windows = []
        for max_events, window_seconds in limits:
            if counts.get(window_seconds, 0) > max_events:
                window_name = "minute" if window_seconds == 60 else "hour" if window_seconds == 3600 else "day"
                exceeded_windows.append(window_name)
        
        return {
            "status": "error",
            "code": 429,
            "message": f"Rate limit exceeded for {', '.join(exceeded_windows)}"
        }
    
    # Not rate limited, register this event across all windows
    windows = [limit[1] for limit in limits]
    updated_counts = await client.register_multi_window_event(key_prefix, windows)
    
    # Process the actual request
    result = await process_request(request_data)
    
    # Return success with rate limit info
    return {
        "status": "success",
        "data": result,
        "rate_limits": {
            "minute": {
                "used": updated_counts[60],
                "limit": 100,
                "remaining": max(0, 100 - updated_counts[60])
            },
            "hour": {
                "used": updated_counts[3600],
                "limit": 1000,
                "remaining": max(0, 1000 - updated_counts[3600])
            },
            "day": {
                "used": updated_counts[86400],
                "limit": 10000,
                "remaining": max(0, 10000 - updated_counts[86400])
            }
        }
    }
```

### Rate Limiting Round Trips and Latency

Each rate limit check requires at least one round trip to Redis, which adds latency to API requests:

```
Client Request → API Server → Redis → API Server → Client Response
```

**Latency Considerations:**
- Local Redis instance: 0.2-1ms per round trip
- Remote Redis instance: 5-50ms per round trip
- Multiple window checks: n × round trip time (without pipelining)

**Optimization Strategies:**
1. **Redis Pipelining**: Batch multiple Redis commands in a single network round trip
   ```python
   # Without pipelining: 3 round trips
   await client.get_event_count(minute_key)
   await client.get_event_count(hour_key)
   await client.get_event_count(day_key)
   
   # With pipelining: 1 round trip
   pipeline = await client.get_client().pipeline()
   pipeline.zcount(minute_key, minute_start, "+inf")
   pipeline.zcount(hour_key, hour_start, "+inf")
   pipeline.zcount(day_key, day_start, "+inf")
   minute_count, hour_count, day_count = await pipeline.execute()
   ```

2. **Local Caching**: Cache rate limit status briefly
   ```python
   # Cache rate limit status for 1 second to reduce Redis calls
   @cache(ttl=1)
   async def is_rate_limited(client_id):
       return await redis_client.is_rate_limited(
           key=f"rate:{client_id}",
           max_events=100,
           window_seconds=60
       )
   ```

3. **Asynchronous Updates**: Register events asynchronously without waiting
   ```python
   # Don't wait for the rate limit registration to complete
   asyncio.create_task(client.register_event(key, window_seconds=60))
   
   # Continue processing the request immediately
   return process_request()
   ```

## 6. Caching Patterns

### Simple Key-Value Caching
```python
# Cache a computation result
await client.set_cache(
    key="compute:result:123",
    value=calculation_result,
    ttl=3600  # 1 hour
)
```

### Cache-Aside Pattern
```python
async def get_user(user_id):
    cache_key = f"user:{user_id}"
    
    # Try to get from cache first
    user = await client.get_cache(cache_key)
    if user:
        return user
    
    # Cache miss - get from database
    user = await database.fetch_user(user_id)
    
    # Store in cache for next time
    await client.set_cache(cache_key, user, ttl=1800)  # 30 minutes
    return user
```

### Cache Invalidation
```python
# Invalidate when data changes
async def update_user(user_id, data):
    # Update database
    await database.update_user(user_id, data)
    
    # Invalidate cache
    await client.delete_cache(f"user:{user_id}")
```

### Batch Invalidation
```python
# Invalidate multiple related caches
async def delete_organization(org_id):
    # Delete organization
    await database.delete_org(org_id)
    
    # Invalidate all related caches
    await client.flush_cache(f"org:{org_id}:*")
```

## 7. Distributed Locking

### Basic Lock Usage
```python
# Acquire a lock with timeout
lock_token = await client.acquire_lock(
    lock_name="process:daily-report",
    timeout=5,   # Wait up to 5 seconds to acquire
    ttl=600      # Lock expires after 10 minutes
)

if lock_token:
    try:
        # Critical section - only one process can execute this
        await generate_daily_report()
    finally:
        # Release the lock when done
        await client.release_lock("process:daily-report", lock_token)
```

### Context Manager Approach
```python
# Automatically acquire and release lock
async def run_single_instance_task():
    try:
        async with client.with_lock("task:singleton", timeout=5, ttl=300):
            # This code is guaranteed to run in only one process/instance
            await perform_exclusive_operation()
    except TimeoutError:
        # Handle case where lock couldn't be acquired
        logger.warning("Task already running in another instance")
```

### Lock Renewal for Long Tasks
```python
# For tasks that might run longer than the TTL
async def long_running_task():
    lock_name = "task:long-process"
    token = await client.acquire_lock(lock_name, ttl=60)
    
    if not token:
        return "Task already running"
    
    # Start a background task to renew the lock
    stop_renewal = asyncio.Event()
    renewal_task = asyncio.create_task(
        renew_lock_periodically(client, lock_name, token, 45, stop_renewal)
    )
    
    try:
        # Perform long-running task
        await very_long_operation()
    finally:
        # Signal renewal to stop and release lock
        stop_renewal.set()
        await renewal_task
        await client.release_lock(lock_name, token)

async def renew_lock_periodically(client, lock_name, token, interval, stop_event):
    while not stop_event.is_set():
        try:
            # Try to renew before TTL expires
            await asyncio.sleep(interval)
            if stop_event.is_set():
                break
                
            # Check if we still own the lock before extending
            is_owner = await client.check_lock_ownership(lock_name, token)
            if is_owner:
                await client.extend_lock(lock_name, token, 60)
        except Exception as e:
            logger.error(f"Error renewing lock: {e}")
```

## 8. Connection Management

### Lifecycle Management
```python
# Recommended pattern for clean connection handling
async def process_with_redis():
    client = AsyncRedisClient(redis_url)
    try:
        # Use Redis
        result = await client.get_cache("some-key")
        return result
    finally:
        # Always close client when done
        await client.close()
```

### Connection Health Checks
```python
# Verify Redis is responsive
async def check_redis_health():
    try:
        if await client.ping():
            return {"status": "healthy", "latency_ms": await measure_latency()}
        else:
            return {"status": "unhealthy", "reason": "ping failed"}
    except Exception as e:
        return {"status": "unhealthy", "reason": str(e)}

async def measure_latency():
    start = time.time()
    await client.ping()
    return round((time.time() - start) * 1000, 2)  # ms
```

### Handling Connection Disruptions
```python
# Retry pattern for transient connection issues
async def resilient_cache_operation(key, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await client.get_cache(key)
        except ConnectionError:
            if attempt < max_retries - 1:
                # Exponential backoff
                await asyncio.sleep(0.1 * (2 ** attempt))
                continue
            raise
```

## 9. Performance Optimization

### Batching Operations
```python
# Use pipeline for multiple operations in one round trip
async def batch_update_counters(user_id, actions):
    redis = await client.get_client()
    async with redis.pipeline() as pipe:
        for action in actions:
            pipe.hincrby(f"user:{user_id}:counts", action, 1)
        await pipe.execute()
```

### Serialization Efficiency
```python
# For large objects, consider compression
import zlib

async def set_large_cache(key, value, ttl=3600):
    json_str = json.dumps(value)
    
    # Only compress if it's worth it (>1KB)
    if len(json_str) > 1024:
        compressed = zlib.compress(json_str.encode())
        await client.set_cache(f"{key}:compressed", compressed, ttl)
    else:
        await client.set_cache(key, value, ttl)

async def get_large_cache(key):
    # Try compressed version first
    compressed = await client.get_cache(f"{key}:compressed")
    if compressed:
        json_str = zlib.decompress(compressed).decode()
        return json.loads(json_str)
    
    # Fall back to uncompressed
    return await client.get_cache(key)
```

### Memory Optimization
```python
# Set maximum memory and eviction policy
await client.set_max_cache_size(
    max_size_bytes=1024 * 1024 * 1024,  # 1GB
    policy="volatile-lru"  # Evict least recently used keys with TTL
)
```

## 10. Error Handling Best Practices

### Graceful Degradation
```python
# Cache-aside with fallback on Redis errors
async def resilient_get_user(user_id):
    try:
        # Try cache first
        cached = await client.get_cache(f"user:{user_id}")
        if cached:
            return cached
    except RedisError:
        # Log error but continue to database
        logger.error("Redis error during cache get", exc_info=True)
    
    # Fallback to database
    return await database.get_user(user_id)
```

### Circuit Breaker Pattern
```python
class RedisCircuitBreaker:
    def __init__(self, client, failure_threshold=5, reset_timeout=30):
        self.client = client
        self.failures = 0
        self.threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.open_until = 0
        
    async def execute(self, operation, *args, **kwargs):
        if time.time() < self.open_until:
            # Circuit is open, fail fast
            raise CircuitBreakerOpen("Redis circuit is open")
            
        try:
            # Try to execute the Redis operation
            result = await operation(*args, **kwargs)
            # Success resets failure count
            self.failures = 0
            return result
        except RedisError:
            # Track failures
            self.failures += 1
            if self.failures >= self.threshold:
                # Open the circuit
                self.open_until = time.time() + self.reset_timeout
                logger.warning(f"Redis circuit opened for {self.reset_timeout}s")
            raise
```

### Monitoring and Alerts
```python
async def monitor_redis_health(interval=60):
    while True:
        try:
            info = await client.info()
            used_memory = int(info.get('used_memory', 0))
            
            # Alert on high memory usage
            if used_memory > 1024 * 1024 * 900:  # 900MB
                alert_team("Redis memory usage >90%")
                
            # Alert on low hit rate
            hits = int(info.get('keyspace_hits', 0))
            misses = int(info.get('keyspace_misses', 0))
            if hits + misses > 0:
                hit_rate = hits / (hits + misses)
                if hit_rate < 0.5:
                    alert_team(f"Redis cache hit rate low: {hit_rate:.2%}")
        except Exception as e:
            logger.error(f"Redis monitoring error: {e}")
            
        await asyncio.sleep(interval)
```

The AsyncRedisClient provides a robust foundation for implementing caching, rate limiting, and distributed locking patterns in asynchronous Python applications, with thoughtful error handling and performance optimizations.
