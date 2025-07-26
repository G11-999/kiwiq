# Scrapeless Browser Profile Manager

Comprehensive async management system for Scrapeless browser profiles with multi-processing safe operations and asymmetrical penalty-based load balancing.

## Features

- 🏗️ **Profile Pool Management**: Create and manage configurable number of browser profiles
- 🔒 **Multi-Processing Safe**: Redis-based distributed locking for safe concurrent operations
- 📊 **Asymmetrical Penalty System**: Smart load balancing with +2 allocation penalty, -1 release recovery
- 💾 **Atomic Cache Operations**: Multi-processing safe JSON persistence with merge strategies
- 🔄 **Complete Lifecycle Management**: Async init, reset, and cleanup operations
- 📈 **Advanced Statistics**: Comprehensive monitoring with penalty scoring and allocation tracking
- ⚡ **Pure Async Interface**: Native async/await support for all critical operations

## Quick Start

```python
import asyncio
from profiles import ScrapelessProfileManager

async def main():
    # Initialize manager (requires Redis URL, creates 100 profiles by default)
    manager = ScrapelessProfileManager(redis_url="redis://localhost:6379/0")

    # Initialize profile pool (async operation with Redis locking)
    await manager.init()

    # Allocate profile for use (sync operation - fast)
    profile = manager.allocate_profile()
    if profile:
        print(f"Using profile: {profile.name} (penalty: {profile.penalty_score})")
        # ... perform scraping work ...
        
        # Always release when done (sync operation - fast)
        manager.release_profile(profile.profile_id)

    # Cleanup when shutting down (async operation with Redis locking)
    await manager.delete_all_profiles()

if __name__ == "__main__":
    asyncio.run(main())
```

## Configuration

### Required Settings

**Redis Connection (Required)**:
```python
# Required for multi-processing safe operations
manager = ScrapelessProfileManager(redis_url="redis://localhost:6379/0")
```

**API Key (Required)**:
Set your Scrapeless API key in settings:
```python
# In scraping_settings.py
SCRAPELESS_API_KEY = "your-api-key-here"
```

### Optional Settings

Set in `config.py`:
- `DEFAULT_CONCURRENT_PROFILES = 100` - Number of profiles to maintain
- `DEFAULT_ENTITY_PREFIX = "quickIQ"` - Prefix for profile names

## Directory Structure

```
scrapeless/
├── profiles.py                    # Main async profile manager
├── demo_usage.py                  # Async usage examples and demos
├── test_asymmetrical_penalties.py # Advanced penalty system tests
├── config.py                      # Configuration settings
├── data/                          # Auto-created cache directory
│   ├── scrapeless_profiles_cache.json
│   ├── demo_concurrent_profiles.json
│   ├── penalty_test_profiles.json
│   └── *.json.backup              # Automatic backups
├── .gitignore                     # Version control exclusions
└── README.md
```

## Cache Files

All cache files are automatically saved in the `./data/` subdirectory with multi-processing safety:
- **Location**: `./data/scrapeless_profiles_cache.json` (default)
- **Multi-Processing Safe**: Redis-based distributed locking ensures atomicity
- **Smart Merging**: Automatic merge of cache updates from multiple processes
- **Backup**: Automatic `.backup` files created before overwriting
- **Content**: Profile metadata, penalty scores, allocation counts, timestamps

## API Configuration

Set your Scrapeless API key in the scraping settings:
```python
# In scraping_settings.py
SCRAPELESS_API_KEY = "your-api-key-here"
```

The manager will validate your API key on initialization and provide clear error messages if configuration is incorrect.

## Demo Usage

Run the comprehensive async demos:

**Basic Usage Demo:**
```bash
python demo_usage.py
```

**Asymmetrical Penalty System Test:**
```bash
python test_asymmetrical_penalties.py
```

These demonstrate:
- Async profile pool initialization
- Concurrent profile allocation with penalty system
- Multi-processing safe operations
- Redis-based distributed locking
- Profile lifecycle management
- Advanced statistics monitoring
- Proper async cleanup procedures

## Multi-Processing Safety

The system provides comprehensive safety at multiple levels:

**Redis-Based Distributed Locking:**
- `AsyncRedisClient.with_lock()` for critical operations
- Automatic retry with exponential backoff
- Distributed locks for `init()`, `reset()`, `delete_all_profiles()`
- Cache operations use atomic read-merge-write patterns

**Thread-Safe Allocation (Local Process):**
- `threading.RLock()` for reentrant locking within single process
- Asymmetrical penalty queue (`heapq`) for fair allocation
- Atomic operations for allocation/release tracking
- Per-thread allocation tracking with safeguards

**Cache Safety:**
- Multi-processing safe JSON persistence
- Smart merge strategies for concurrent updates
- Automatic backup creation before modifications

## Statistics

Get comprehensive metrics including penalty system details:
```python
stats = manager.get_stats()

# Basic metrics
print(f"Total profiles: {stats['total_profiles']}")
print(f"Active allocations: {stats['total_active_allocations']}")

# Penalty system metrics
penalty_info = stats['penalty_system']
print(f"Allocation penalty: +{penalty_info['allocation_penalty']}")
print(f"Release recovery: -{penalty_info['release_recovery']}")
print(f"Penalty distribution: {penalty_info['penalty_distribution']}")

# Lifetime statistics
lifetime = stats['lifetime_statistics']
print(f"Total allocations: {lifetime['total_allocations']}")
print(f"Over-release attempts: {lifetime['over_release_attempts']}")

# Per-profile details
for pid, details in stats['profile_details'].items():
    print(f"{details['profile_name']}: penalty={details['penalty_score']}, "
          f"active={details['actual_allocations']}")
```

## Error Handling

The manager includes robust error handling for:
- API communication failures
- File I/O errors
- Concurrent access conflicts
- Profile allocation exhaustion
- Network timeouts and rate limiting

## Best Practices

1. **Async Operations**: Use `await` for all critical operations (`init()`, `reset()`, `delete_all_profiles()`)
2. **Redis Required**: Always provide a valid Redis URL for multi-processing safety
3. **Always Release**: Use try/finally blocks to ensure profiles are released:
   ```python
   profile = manager.allocate_profile()
   try:
       # Use profile for scraping
       pass
   finally:
       if profile:
           manager.release_profile(profile.profile_id)
   ```
4. **Monitor Penalties**: Check penalty scores to understand load distribution
5. **Handle Failures**: Check for `None` return from `allocate_profile()`
6. **Initialize Once**: Call `await manager.init()` once at application startup
7. **Clean Shutdown**: Call `await manager.delete_all_profiles()` on application exit
8. **Avoid Over-Release**: The system tracks and prevents over-releasing profiles

## Troubleshooting

### Common Issues

**❌ "Redis URL is required" error**
- Ensure Redis is running on your system
- Provide a valid Redis URL: `redis://localhost:6379/0`
- Check Redis connectivity: `redis-cli ping`

**❌ "API client not available" error**
- Check that `SCRAPELESS_API_KEY` is set in `scraping_settings.py`
- Verify your API key is valid and active
- Ensure the API key is not empty or malformed

**❌ "Could not acquire [operation] lock" errors**
- Multiple processes trying to perform the same operation simultaneously
- This is normal behavior - the system will retry automatically
- If persistent, check Redis connectivity and increase timeout values

**❌ "Profile creation response missing ID field"**
- The API response structure may have changed
- Uncomment the debug line in `create_profile()` to see the full response
- Check if the profile ID is in a different field name

**❌ "Failed to initialize profile pool"**
- Verify internet connection and Redis connectivity
- Check API key validity in `scraping_settings.py`
- Ensure you have sufficient API credits
- Try with a smaller number of profiles first

### Debug Mode

Enable detailed API response logging by uncommenting this line in `profiles.py`:
```python
# In ScrapelessAPIClient.create_profile()
print(f"🔍 API Response for '{name}': {profile_data}")
```

### Getting Help

1. Verify Redis is running: `redis-cli ping`
2. Test with a small profile count (e.g., 3-5 profiles)
3. Check the `./data/` directory for cache files and backups
4. Review the console output for specific error messages
5. Run the test scripts to isolate issues:
   - `python test_asymmetrical_penalties.py`
   - `python demo_usage.py` 