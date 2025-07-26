# Scrapeless Browser Redis Pool Cleanup Guide

## Overview

The Scrapeless browser pool uses Redis for distributed concurrency control. Sometimes, resources may not be properly released due to crashes, network issues, or other failures. This guide explains how to diagnose and fix these issues.

## Symptoms of Pool Corruption

You may need to cleanup the Redis pool if you see:

- `Redis resource acquisition failed. Current usage: X/Y` where X > Y
- Browsers failing to acquire even when none are in use
- Persistent high resource usage after all processes have stopped

## Cleanup Methods

### 1. Automatic Cleanup in Code

Add cleanup at the start of your scripts:

```python
from workflow_service.services.scraping.browsers.scrapeless.scrapeless_browser import cleanup_scrapeless_redis_pool

# Cleanup before starting
await cleanup_scrapeless_redis_pool()
```

### 2. Manual Cleanup Script

Run the cleanup script from the command line:

```bash
cd /path/to/kiwiq-backend
python services/workflow_service/services/scraping/browsers/cleanup_redis_pool.py
```

### 3. In Python/IPython

```python
import asyncio
from workflow_service.services.scraping.browsers.scrapeless.scrapeless_browser import cleanup_scrapeless_redis_pool

# Run cleanup
asyncio.run(cleanup_scrapeless_redis_pool())
```

### 4. From Browser Pool Instance

If you have a browser pool instance:

```python
pool = ScrapelessBrowserPool()
await pool.force_cleanup_redis_pool()
```

## Best Practices

1. **Server Startup**: Consider adding cleanup to your server startup routine
2. **Test Setup**: Always cleanup before running tests
3. **Error Recovery**: Use force_close_browser() when browsers encounter errors
4. **Monitoring**: Check pool status regularly with `get_pool_status()`

## Pool Status Checking

To check the current pool status:

```python
from redis_client.redis_client import AsyncRedisClient
from global_config.settings import global_settings

redis_client = AsyncRedisClient(global_settings.REDIS_URL)
pool_info = await redis_client.get_pool_info("scrapeless_browsers_pool")
print(pool_info)
```

## Debugging Tips

1. Enable detailed logging to track resource allocation/deallocation
2. Look for allocation IDs in logs (e.g., `✅ Redis resource acquired. Allocation ID: xxx`)
3. Check if matching release logs exist for each allocation
4. Use the cleanup script to get before/after pool status

## Warning

Force cleanup will terminate ALL active browser sessions across ALL processes. Only use when you're sure no legitimate browser sessions are running.

## Parallel Browser Acquisition

### Fixed Issue (as of latest update)

Previously, the browser pool had a bug where only one browser could be acquired at a time, even when multiple slots were available. This was due to holding a lock during the entire acquisition process, including slow operations like Redis resource acquisition and browser creation.

### How It Works Now

The pool now supports true parallel acquisition:
1. Quick operations (checking pool state) are done under lock
2. Slow operations (Redis calls, browser creation) are done outside the lock
3. Multiple tasks can acquire browsers simultaneously up to the configured limits

### Testing Parallel Acquisition

Run the test script to verify parallel acquisition:

```bash
python services/workflow_service/services/scraping/browsers/test_parallel_acquisition.py
```

### Configuration for Parallel Usage

```python
# Create pool with appropriate limits
pool = ScrapelessBrowserPool(
    max_concurrent=100,  # Global Redis limit
    max_concurrent_local=9,  # Local process limit
    enable_keep_alive=False,  # Set based on your use case
)

# Use with async context manager for automatic cleanup
async with pool:
    # Launch multiple parallel tasks
    tasks = [acquire_and_use_browser(pool) for _ in range(9)]
    await asyncio.gather(*tasks)
```

### Performance Tips

1. **Set appropriate limits**: Don't set `max_concurrent_local` higher than you actually need
2. **Use keep-alive wisely**: Enable for many sequential operations, disable for one-time parallel bursts
3. **Monitor pool status**: Use `get_pool_status()` to track resource usage
4. **Handle failures gracefully**: Always use try-except blocks and cleanup on errors 