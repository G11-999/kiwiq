# ScrapelessBrowserPool

A comprehensive browser pool manager for Scrapeless browser instances with Redis-based concurrency control and in-memory browser pooling.

## Features

### 🚀 **Core Capabilities**
- **Global Concurrency Control**: Respects `MAX_CONCURRENT_SCRAPELESS_BROWSERS` limit across all processes via Redis
- **Local Concurrency Limiting**: Optional pool-specific limits that override global limits when set lower
- **In-Memory Browser Pooling**: Maintains a pool of active browsers for efficient reuse
- **Configurable Keep-Alive**: Browsers can be kept alive between uses to reduce initialization overhead
- **TTL Expiration Handling**: Automatic cleanup of expired browsers during acquisition
- **Force Close Mechanism**: Immediate browser closure for error recovery, bypassing normal pool logic
- **Timeout Support**: Configurable timeouts for resource acquisition with graceful fallback
- **Automatic Cleanup**: Background cleanup of expired browsers and comprehensive manual cleanup
- **Thread-Safe Operations**: All pool operations are protected with async locks

### 🔧 **Redis Integration**
- Uses `AsyncRedisClient` for distributed resource management
- Tracks browser usage with sliding window counters
- Implements resource acquisition/release with atomic operations
- Handles Redis connection failures gracefully

### 📊 **Monitoring & Debugging**
- Real-time pool status monitoring including local vs global limits
- Detailed logging of all pool operations including TTL cleanup and force closes
- Browser usage statistics and metadata tracking
- Comprehensive error handling and reporting

## Quick Start

### Basic Usage

```python
from workflow_service.services.scraping.browsers.scrapeless.scrapeless_browser import ScrapelessBrowserPool

# Create a browser pool
pool = ScrapelessBrowserPool(
    max_concurrent=10,          # Global limit via Redis
    max_concurrent_local=5,     # Pool-specific limit (optional)
    acquisition_timeout=30,
    browser_ttl=600             # 10 minutes TTL
)

# Acquire and use a browser
browser_data = await pool.acquire_browser()
if browser_data:
    browser = browser_data['browser']
    try:
        await browser.page.goto("https://example.com")
        # Use browser...
    except Exception as e:
        # Force close on error to prevent reuse of problematic browser
        await pool.force_close_browser(browser_data)
    else:
        # Normal release (may return to pool)
        await pool.release_browser(browser_data)

# Clean up
await pool.cleanup_all_browsers()
```

### Keep-Alive Mode with Error Handling (Recommended)

```python
# Use pool as async context manager for keep-alive behavior
async with ScrapelessBrowserPool(
    max_concurrent=5,
    browser_ttl=900  # 15 minutes
) as pool:
    
    # Automatic error handling with force close
    try:
        async with ScrapelessBrowserContextManager(
            pool, 
            force_close_on_error=True  # Auto force close on exceptions
        ) as browser:
            await browser.page.goto("https://example.com")
            # Use browser...
            # Browser automatically returned to pool if no errors
    except Exception as e:
        print(f"Browser error handled: {e}")
        # Problematic browser was automatically force closed
        
    # Pool automatically cleans up on exit
```

### Manual Force Close for Error Recovery

```python
async with ScrapelessBrowserPool() as pool:
    browser_data = await pool.acquire_browser()
    if browser_data:
        try:
            browser = browser_data['browser']
            await browser.page.goto("https://problematic-site.com")
            # ... operations that might fail
        except Exception as e:
            print(f"Browser error: {e}")
            # Force close immediately, don't return to pool
            await pool.force_close_browser(browser_data)
        else:
            # Normal operation, return to pool
            await pool.release_browser(browser_data)
```

## Configuration

### Pool Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `redis_client` | `AsyncRedisClient` | `None` | Custom Redis client (auto-created if None) |
| `max_concurrent` | `int` | `100` | Maximum concurrent browsers globally via Redis |
| `max_concurrent_local` | `int` | `None` | Pool-specific limit (overrides global if lower) |
| `acquisition_timeout` | `int` | `30` | Timeout for acquiring browsers (seconds) |
| `browser_ttl` | `int` | `900` | Browser time-to-live in pool (seconds) |
| `pool_id` | `str` | `None` | Unique pool identifier (auto-generated if None) |

### Context Manager Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pool` | `ScrapelessBrowserPool` | Required | The browser pool to acquire from |
| `timeout` | `int` | `None` | Timeout for browser acquisition |
| `session_config` | `Dict` | `None` | Session configuration for new browsers |
| `force_close_on_error` | `bool` | `True` | Auto force close on exceptions |

## Advanced Features

### 1. **TTL Expiration Handling**

Browsers are automatically checked for expiration during acquisition:

```python
async with ScrapelessBrowserPool(browser_ttl=300) as pool:  # 5 minute TTL
    # Expired browsers are automatically cleaned up during acquire_browser()
    browser_data = await pool.acquire_browser()
    # You'll always get a fresh or valid browser
```

### 2. **Local Concurrency Limiting**

Set pool-specific limits lower than global Redis limits:

```python
pool = ScrapelessBrowserPool(
    max_concurrent=100,        # Global Redis limit
    max_concurrent_local=5     # This pool limited to 5 browsers
)

# Pool will never exceed 5 browsers regardless of global availability
status = await pool.get_pool_status()
print(f"Effective limit: {status['effective_max_concurrent']}")  # Will be 5
```

### 3. **Force Close Mechanism**

Multiple ways to force close problematic browsers:

```python
# Method 1: Manual force close
browser_data = await pool.acquire_browser()
try:
    # ... use browser
    pass
except Exception:
    await pool.force_close_browser(browser_data)  # Force close immediately

# Method 2: Context manager with auto force close
async with ScrapelessBrowserContextManager(
    pool, 
    force_close_on_error=True
) as browser:
    # Any exception will trigger force close
    await browser.page.goto("https://problematic-site.com")

# Method 3: Manual force close via context manager
async with ScrapelessBrowserContextManager(pool) as browser_cm:
    try:
        # ... operations
        pass
    except SpecificError:
        await browser_cm.force_close()  # Explicitly request force close
```

### 4. **Enhanced Pool Status**

```python
status = await pool.get_pool_status()
print(f"""
Enhanced Pool Status:
- Pool ID: {status['pool_id']}
- Available Browsers: {status['available_browsers']}
- Active Browsers: {status['active_browsers']}
- Local Active Count: {status['local_active_count']}
- Keep-Alive Enabled: {status['keep_alive_enabled']}
- Pool Active: {status['pool_active']}
- Global Max Concurrent: {status['max_concurrent']}
- Local Max Concurrent: {status['max_concurrent_local']}
- Effective Max Concurrent: {status['effective_max_concurrent']}
- Browser TTL: {status['browser_ttl']} seconds
""")
```

## Usage Patterns

### 1. **Production Service with Error Recovery**
```python
async with ScrapelessBrowserPool(
    max_concurrent_local=10,  # Limit this service to 10 browsers
    browser_ttl=1800,         # 30 minute TTL
    acquisition_timeout=60
) as pool:
    
    async def process_url(url: str, max_retries: int = 3):
        for attempt in range(max_retries):
            try:
                async with ScrapelessBrowserContextManager(
                    pool, 
                    timeout=30,
                    force_close_on_error=True
                ) as browser:
                    await browser.page.goto(url, timeout=30000)
                    # Process page...
                    return "success"
                    
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
    
    # Process URLs with automatic error recovery
    urls = ["https://site1.com", "https://site2.com", ...]
    tasks = [process_url(url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
```

### 2. **High-Throughput Concurrent Processing**
```python
async def worker(worker_id: int, pool: ScrapelessBrowserPool, work_queue: asyncio.Queue):
    while True:
        try:
            # Get work item
            url = await asyncio.wait_for(work_queue.get(), timeout=1.0)
            
            # Process with browser
            async with ScrapelessBrowserContextManager(pool, timeout=10) as browser:
                await browser.page.goto(url)
                # Process...
                
            work_queue.task_done()
            
        except asyncio.TimeoutError:
            break  # No more work
        except Exception as e:
            print(f"Worker {worker_id} error: {e}")
            # Browser auto force closed on error

# Setup high-throughput processing
async with ScrapelessBrowserPool(max_concurrent_local=20) as pool:
    work_queue = asyncio.Queue()
    
    # Add work items
    for url in urls:
        await work_queue.put(url)
    
    # Launch workers
    workers = [
        asyncio.create_task(worker(i, pool, work_queue))
        for i in range(10)
    ]
    
    # Wait for completion
    await work_queue.join()
    
    # Cancel workers
    for w in workers:
        w.cancel()
```

### 3. **Resource-Constrained Environment**
```python
# Limited resource environment - strict local limits
pool = ScrapelessBrowserPool(
    max_concurrent=100,        # Global limit (shared with other services)
    max_concurrent_local=3,    # Very conservative local limit
    browser_ttl=600,           # 10 minute TTL to conserve memory
    acquisition_timeout=120    # Longer timeout for limited resources
)

async def careful_processing(urls: List[str]):
    for url in urls:
        # Process one at a time to minimize resource usage
        browser_data = await pool.acquire_browser(timeout=60)
        if browser_data:
            try:
                browser = browser_data['browser']
                await browser.page.goto(url)
                # Process carefully...
                
            except Exception as e:
                print(f"Error processing {url}: {e}")
                await pool.force_close_browser(browser_data)
            else:
                await pool.release_browser(browser_data)
        else:
            print(f"Could not acquire browser for {url}")

await careful_processing(urls)
await pool.cleanup_all_browsers()
```

## Error Handling Best Practices

### 1. **Always Use Force Close for Errors**
```python
# Good: Force close on error
try:
    async with ScrapelessBrowserContextManager(
        pool, 
        force_close_on_error=True
    ) as browser:
        await browser.page.goto(url)
except Exception:
    # Browser automatically force closed
    pass

# Also good: Manual force close
browser_data = await pool.acquire_browser()
try:
    # ... use browser
    pass
except Exception:
    await pool.force_close_browser(browser_data)  # Don't return to pool
else:
    await pool.release_browser(browser_data)  # Safe to return to pool
```

### 2. **Implement Retry Logic**
```python
async def robust_browser_operation(pool, operation_func, max_retries=3):
    for attempt in range(max_retries):
        try:
            async with ScrapelessBrowserContextManager(pool) as browser:
                return await operation_func(browser)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            print(f"Attempt {attempt + 1} failed, retrying: {e}")
            await asyncio.sleep(0.5 * (attempt + 1))

# Usage
result = await robust_browser_operation(
    pool, 
    lambda browser: browser.page.goto("https://example.com")
)
```

### 3. **Monitor Pool Health**
```python
async def monitor_pool_health(pool: ScrapelessBrowserPool, interval: int = 60):
    while True:
        try:
            status = await pool.get_pool_status()
            
            # Check for potential issues
            if status['active_browsers'] == status['effective_max_concurrent']:
                print("Warning: Pool at maximum capacity")
            
            if status['available_browsers'] == 0 and status['active_browsers'] > 0:
                print("Info: No available browsers, all in use")
            
            # Log status
            print(f"Pool health: {status['active_browsers']}/{status['effective_max_concurrent']} active")
            
        except Exception as e:
            print(f"Error monitoring pool: {e}")
        
        await asyncio.sleep(interval)

# Run monitoring in background
monitor_task = asyncio.create_task(monitor_pool_health(pool))
```

## Performance Considerations

### Enhanced Performance Features

1. **TTL-Based Expiration**: Browsers are proactively cleaned up during acquisition, preventing resource leaks
2. **Local Concurrency Control**: Prevents resource contention by limiting pool-specific usage
3. **Force Close Mechanism**: Quickly removes problematic browsers from circulation
4. **Enhanced Status Monitoring**: Provides detailed metrics for optimization

### Optimization Guidelines

1. **Set Appropriate TTL**: Balance between reuse efficiency and memory usage
   ```python
   # Short-lived tasks: shorter TTL
   pool = ScrapelessBrowserPool(browser_ttl=300)  # 5 minutes
   
   # Long-running service: longer TTL
   pool = ScrapelessBrowserPool(browser_ttl=1800)  # 30 minutes
   ```

2. **Use Local Limits for Resource Control**:
   ```python
   # High-resource service
   pool = ScrapelessBrowserPool(max_concurrent_local=20)
   
   # Resource-constrained service
   pool = ScrapelessBrowserPool(max_concurrent_local=3)
   ```

3. **Implement Proper Error Handling**:
   ```python
   # Always force close on errors to prevent problematic browsers from being reused
   async with ScrapelessBrowserContextManager(pool, force_close_on_error=True) as browser:
       # Your code here
       pass
   ```

## Troubleshooting

### Enhanced Troubleshooting

1. **"Browsers not being cleaned up"**
   - Check TTL settings: `browser_ttl` parameter
   - Monitor pool status: `get_pool_status()`
   - Ensure proper exception handling with force close

2. **"Local limit reached but global capacity available"**
   - This is expected behavior when `max_concurrent_local` is set
   - Increase `max_concurrent_local` if needed
   - Check if other pool instances are using global capacity

3. **"Browsers failing repeatedly"**
   - Ensure `force_close_on_error=True` in context managers
   - Implement retry logic with force close
   - Monitor for systematic issues (network, API limits, etc.)

4. **"TTL expiration not working"**
   - Verify `browser_ttl` is set appropriately
   - Check that browsers are being acquired regularly (TTL check happens during acquisition)
   - Monitor logs for cleanup messages

### Debug Mode with Enhanced Logging

```python
import logging

# Enable detailed logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('workflow_service.services.scraping.browsers.scrapeless.scrapeless_browser')
logger.setLevel(logging.DEBUG)

# This will show:
# - TTL expiration checks and cleanup
# - Force close operations
# - Local vs global concurrency decisions
# - Detailed browser lifecycle events
```

## API Reference

### ScrapelessBrowserPool

#### Enhanced Constructor

```python
ScrapelessBrowserPool(
    redis_client: Optional[AsyncRedisClient] = None,
    max_concurrent: int = MAX_CONCURRENT_SCRAPELESS_BROWSERS,
    max_concurrent_local: Optional[int] = None,  # NEW: Pool-specific limit
    acquisition_timeout: int = 30,
    browser_ttl: int = 900,
    pool_id: Optional[str] = None
)
```

#### Enhanced Methods

- `acquire_browser(timeout=None, session_config=None)` → `Optional[Dict]`
  - Now includes TTL expiration checking
  - Respects local concurrency limits
- `release_browser(browser_data)` → `bool`
  - Now checks TTL before returning to pool
- `force_close_browser(browser_data)` → `bool` **NEW**
  - Immediately closes browser regardless of settings
- `cleanup_all_browsers()` → `int`
  - Enhanced to reset local counters
- `get_pool_status()` → `Dict`
  - Enhanced with local limit information

### ScrapelessBrowserContextManager

#### Enhanced Constructor

```python
ScrapelessBrowserContextManager(
    pool: ScrapelessBrowserPool,
    timeout: Optional[int] = None,
    session_config: Optional[Dict] = None,
    force_close_on_error: bool = True  # NEW: Auto force close on exceptions
)
```

#### Enhanced Methods

- `force_close()` → `bool` **NEW**
  - Manually request force close of current browser
- `__aexit__(exc_type, exc_val, exc_tb)`
  - Enhanced to auto force close on exceptions when enabled

For complete examples including all new features, see `scrapeless_browser_pool_usage.py` in the examples directory. 