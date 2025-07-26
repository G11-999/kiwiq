# MultiProviderQueryEngine Documentation

## Overview

The `MultiProviderQueryEngine` is a reusable querying class that orchestrates queries across multiple AI providers (OpenAI, Google AI Mode, and Perplexity) using browser automation with the ScrapelessBrowserPool.

## Features

- ✅ **Multi-Provider Support**: Query OpenAI, Google AI Mode, and Perplexity
- ✅ **Configurable Providers**: Enable/disable each provider independently  
- ✅ **Full Parallel Processing**: All queries across ALL providers processed simultaneously
- ✅ **Browser Pool Management**: Uses ScrapelessBrowserPool with keep-alive for efficiency
- ✅ **Profile Management**: Automatic browser profile allocation and cleanup
- ✅ **Retry Logic**: Configurable retry attempts with exponential backoff
- ✅ **Error Handling**: Comprehensive error handling and logging
- ✅ **JSON Output**: Saves all results to structured JSON files
- ✅ **Statistics**: Provides detailed success/failure statistics with timing
- ✅ **Response Normalization**: Normalizes different provider response formats

## Quick Start

### Basic Usage

```python
import asyncio
from browser_test import MultiProviderQueryEngine, ProviderConfig

async def simple_example():
    # Define your queries
    queries = [
        "What is artificial intelligence?",
        "How do solar panels work?"
    ]
    
    # Configure providers
    providers_config = {
        "google": ProviderConfig(enabled=True, max_retries=2),
        "openai": ProviderConfig(enabled=True, max_retries=2),
        "perplexity": ProviderConfig(enabled=False)  # Disabled
    }
    
    # Create and run engine
    # Calculate optimal browser pool size for cross-provider parallelization
    enabled_providers = sum(1 for config in providers_config.values() if config.enabled)
    total_tasks = len(queries) * enabled_providers
    
    engine = MultiProviderQueryEngine(
        queries=queries,
        providers_config=providers_config,
        max_concurrent_browsers=total_tasks + 1,  # Cross-provider parallel optimization + buffer
        browser_pool_config={
            "acquisition_timeout": 60  # Allow time for all browsers to be acquired
        }
    )
    
    results = await engine.process_all_queries()
    return results

# Run it
asyncio.run(simple_example())
```

### Running the Test Script

```bash
# Navigate to the browsers directory
cd services/workflow_service/services/scraping/browsers/

# Run the interactive test
python test_query_engine.py

# Or run the main browser test
python browser_test.py
```

## Cross-Provider Parallel Processing

The MultiProviderQueryEngine processes **ALL queries across ALL providers simultaneously** for maximum performance. This means:

- ✅ **Full Concurrent Execution**: All queries for all enabled providers run at the same time
- ✅ **Cross-Provider Parallelization**: No waiting between providers - everything runs together
- ✅ **Maximum Browser Pool Utilization**: Efficiently uses all available browsers from the pool  
- ✅ **Dramatic Speed Improvement**: Reduces total processing time to the longest single query
- ✅ **Resource Optimization**: No artificial delays or sequential bottlenecks
- ✅ **Smart Keep-Alive**: Automatically disables keep-alive when browsers ≥ tasks (saves resources)

### Browser Pool Sizing for Cross-Provider Parallelization

For optimal performance, size your browser pool based on **total tasks across ALL providers**:

```python
# Calculate total parallel tasks
enabled_providers = sum(1 for config in providers_config.values() if config.enabled)
total_parallel_tasks = len(queries) * enabled_providers

# Minimum: One browser per task for full parallelization
max_concurrent_browsers = total_parallel_tasks

# Recommended: Add buffer for retries and peak load
max_concurrent_browsers = total_parallel_tasks + 2

# Conservative: For resource-constrained environments
max_concurrent_browsers = min(total_parallel_tasks, 10)  # Cap at 10 browsers
```

### Performance Comparison

**Sequential Processing (old approach):**
- 3 queries × 3 providers × 60s each = 540s total
- Processes: Google → OpenAI → Perplexity sequentially
- Uses 1 browser at a time

**Provider Parallel (intermediate approach):**
- 3 queries × 60s per provider, but 3 providers sequentially = ~180s total  
- Processes queries within each provider in parallel
- Uses 3 browsers per provider

**Cross-Provider Parallel (current approach):**
- 3 queries × 3 providers × 60s = ~60s total (ALL tasks simultaneously)
- Processes ALL queries for ALL providers at the same time
- Uses 9 browsers concurrently (3 queries × 3 providers)
- 🚀 **9x faster than sequential!**

## Smart Keep-Alive Optimization

The MultiProviderQueryEngine includes an **automatic keep-alive optimization** that saves resources:

### How It Works

```python
total_tasks = num_queries * enabled_providers
if total_tasks <= max_concurrent_browsers:
    keep_alive = False  # DISABLED - each browser used once, then closed
else:
    keep_alive = True   # ENABLED - browsers reused for multiple tasks
```

### Scenarios

**Keep-Alive DISABLED (Resource Efficient):**
- ✅ You have enough browsers for all tasks
- ✅ Each browser handles one task, then closes immediately
- ✅ Lower memory usage, no idle browsers
- ✅ Example: 9 tasks, 10+ browsers

**Keep-Alive ENABLED (Reuse Efficient):**
- ✅ You have fewer browsers than tasks
- ✅ Browsers stay alive and handle multiple tasks
- ✅ Higher throughput with limited browsers
- ✅ Example: 9 tasks, 3 browsers

### Configuration Example

```python
queries = ["Query 1", "Query 2", "Query 3"]  # 3 queries
providers = {"google": True, "openai": True}  # 2 providers
total_tasks = 3 * 2 = 6  # 6 total tasks

# Scenario 1: Enough browsers (keep-alive DISABLED)
engine = MultiProviderQueryEngine(
    queries=queries,
    max_concurrent_browsers=8,  # 8 >= 6 tasks
    # keep_alive automatically set to False
)

# Scenario 2: Limited browsers (keep-alive ENABLED)  
engine = MultiProviderQueryEngine(
    queries=queries,
    max_concurrent_browsers=3,  # 3 < 6 tasks
    # keep_alive automatically set to True
)
```

## Configuration Options

### ProviderConfig

Configure each provider individually:

```python
from browser_test import ProviderConfig

# Default configuration
config = ProviderConfig(
    enabled=True,        # Enable/disable this provider
    max_retries=3,       # Number of retry attempts
    retry_delay=2.0,     # Base delay between retries (exponential backoff)
    timeout=180          # Timeout per query in seconds
)
```

### MultiProviderQueryEngine Parameters

```python
engine = MultiProviderQueryEngine(
    queries=["Your", "queries", "here"],
    providers_config={
        "openai": ProviderConfig(enabled=True, max_retries=2),
        "google": ProviderConfig(enabled=True, max_retries=2), 
        "perplexity": ProviderConfig(enabled=True, max_retries=2)
    },
    max_concurrent_browsers=3,  # Number of browsers in pool
    browser_pool_config={       # Additional browser pool settings
        "browser_ttl": 900,     # Browser TTL in seconds
        "use_profiles": True,   # Enable browser profiles
        "persist_profile": False # Don't persist profiles
    },
    output_file="results.json", # Output filename (optional)
    data_dir="/path/to/data"    # Output directory (optional)
)
```

## Output Format

### JSON Structure

The engine saves results in a structured JSON format similar to the profiles cache:

```json
{
  "created_at": "2024-01-15T10:30:00.000Z",
  "operation": "multi_provider_query",
  "version": "1.0",
  "data": {
    "metadata": {
      "start_time": "2024-01-15T10:30:00.000Z",
      "end_time": "2024-01-15T10:35:00.000Z",
      "total_duration_seconds": 300.5,
      "queries": ["Query 1", "Query 2"],
      "total_queries": 2,
      "enabled_providers": ["google", "openai"],
      "browser_pool_config": {...}
    },
    "results": {
      "google": [
        {
          "query": "Query 1",
          "query_index": 0,
          "provider": "google",
          "success": true,
          "attempts": 1,
          "start_time": "2024-01-15T10:30:00.000Z",
          "end_time": "2024-01-15T10:31:30.000Z",
          "duration_seconds": 90.5,
          "response": {
            "provider": "google",
            "raw_response": {...},
            "processed_data": [...],
            "links": [...],
            "citations": [...]
          }
        }
      ],
      "openai": [...]
    },
    "errors": {
      "perplexity": {
        "error": "Connection timeout",
        "error_type": "TimeoutError",
        "timestamp": "2024-01-15T10:32:00.000Z"
      }
    },
    "statistics": {
      "google": {
        "total_queries": 2,
        "successful_queries": 2,
        "failed_queries": 0,
        "success_rate": 1.0
      },
      "openai": {...}
    }
  }
}
```

### Response Normalization

Each provider's response is normalized to a common format:

```python
{
    "provider": "google",
    "raw_response": {...},           # Original provider response
    "processed_data": [...],         # Extracted main content
    "links": [                       # Deduplicated links
        {
            "url": "https://example.com",
            "text": "Link text",
            "title": "Link title"
        }
    ],
    "citations": ["Citation 1", "Citation 2"]  # Deduplicated citations
}
```

## Error Handling

### Retry Logic

The engine implements exponential backoff retry logic:

1. **Initial attempt**: Execute query normally
2. **Retry 1**: Wait 2.0s, then retry
3. **Retry 2**: Wait 4.0s, then retry  
4. **Retry 3**: Wait 8.0s, then retry
5. **Give up**: Mark query as failed

### Error Categories

- **Browser Errors**: Browser crashes, navigation failures
- **Timeout Errors**: Query takes longer than configured timeout
- **Provider Errors**: Provider-specific errors (blocked, rate limited, etc.)
- **Network Errors**: Connection issues, DNS failures

### Error Recovery

- **Force Close**: Problematic browsers are force-closed and replaced
- **Profile Cleanup**: Browser profiles are properly released on errors
- **Pool Management**: Browser pool continues operating despite individual failures

## Advanced Usage

### Custom Provider Configuration

```python
# Different retry strategies per provider
providers_config = {
    "google": ProviderConfig(
        enabled=True, 
        max_retries=3,     # More retries for Google
        timeout=240        # Longer timeout
    ),
    "openai": ProviderConfig(
        enabled=True,
        max_retries=1,     # Fewer retries for OpenAI
        timeout=120,       # Shorter timeout
        retry_delay=1.0    # Faster retries
    ),
    "perplexity": ProviderConfig(enabled=False)  # Disabled
}
```

### Browser Pool Optimization

```python
# High-performance cross-provider parallel processing configuration
queries = ["Query 1", "Query 2", "Query 3", "Query 4", "Query 5"]
providers_config = {
    "google": ProviderConfig(enabled=True),
    "openai": ProviderConfig(enabled=True),
    "perplexity": ProviderConfig(enabled=True)
}

# Calculate total parallel tasks across all providers
enabled_providers = sum(1 for config in providers_config.values() if config.enabled)
total_tasks = len(queries) * enabled_providers  # 5 queries × 3 providers = 15 tasks

browser_pool_config = {
    "browser_ttl": 1800,              # 30-minute browser lifetime
    "use_profiles": True,             # Enable profiles for consistency
    "persist_profile": False,         # Don't persist (memory optimization)
    "acquisition_timeout": 90,        # Longer timeout for all browser acquisition
}

engine = MultiProviderQueryEngine(
    queries=queries,
    providers_config=providers_config,
    max_concurrent_browsers=total_tasks + 3,  # 15 parallel tasks + buffer
    browser_pool_config=browser_pool_config
)
```

### Statistics and Monitoring

```python
# Process queries
results = await engine.process_all_queries()

# Get summary statistics
summary = engine.get_summary_statistics(results)

print(f"Success rate: {summary['overall']['overall_success_rate']:.1%}")
print(f"Duration: {summary['total_duration']:.1f}s")

# Per-provider stats
for provider, stats in summary["providers"].items():
    print(f"{provider}: {stats['successful_queries']}/{stats['successful_queries'] + stats['failed_queries']} "
          f"({stats['success_rate']:.1%})")
```

## File Locations

- **Main Class**: `browser_test.py` - Contains `MultiProviderQueryEngine`
- **Test Script**: `test_query_engine.py` - Interactive test runner
- **Output Directory**: `./data/` - JSON results saved here by default
- **Documentation**: `README_MultiProviderQueryEngine.md` - This file

## Dependencies

The engine requires:

- **ScrapelessBrowserPool**: Browser pool management with profiles
- **Provider Actors**: GoogleAIModeBrowserActor, OpenAIBrowserActor, PerplexityBrowserActor
- **Redis**: For distributed browser pool coordination
- **Valid API Keys**: Scrapeless API key configured in settings

## Best Practices

### Performance

1. **Batch Queries**: Process multiple queries in a single engine run
2. **Cross-Provider Parallelization**: Size browser pool for total tasks across ALL providers (`queries × enabled_providers`)
3. **Smart Keep-Alive**: Let the engine auto-optimize keep-alive based on browser-to-task ratio
4. **Optimize Browsers**: Use appropriate pool sizes with longer acquisition timeouts for parallel processing
5. **Buffer Browsers**: Add 2-3 extra browsers beyond total task count for retry overhead
6. **Profile Management**: Use profiles for consistency, avoid persistence for memory efficiency
7. **Concurrent Limits**: Monitor provider rate limits carefully with high parallelization
8. **Resource Planning**: Consider memory usage with high browser counts (each browser uses ~100-200MB)

### Reliability

1. **Configure Retries**: Set appropriate retry counts for each provider
2. **Monitor Timeouts**: Adjust timeouts based on query complexity
3. **Error Handling**: Check results for errors and handle gracefully
4. **Resource Cleanup**: Use engine as async context manager when possible

### Cost Management

1. **Selective Providers**: Only enable providers you need
2. **Query Optimization**: Group similar queries together
3. **Browser Reuse**: Use keep-alive to reduce browser startup costs
4. **Profile Efficiency**: Use profiles but avoid persistence unless needed

## Troubleshooting

### Common Issues

1. **"Browser acquisition timeout"**
   - Increase `max_concurrent_browsers`
   - Check Redis connectivity
   - Verify Scrapeless API key

2. **"Query timeout"**
   - Increase `timeout` in ProviderConfig
   - Simplify queries
   - Check provider availability

3. **"Profile allocation failed"**
   - Check Redis connection
   - Verify profile manager initialization
   - Increase browser pool TTL

4. **High failure rates**
   - Increase retry counts
   - Add delays between queries
   - Check provider-specific issues

### Debug Mode

Enable debug logging for detailed information:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

This provides detailed information about:
- Browser pool operations
- Profile allocation/release
- Retry attempts
- Error details

## Support

For issues and questions:

1. Check the logs for detailed error information
2. Verify all dependencies are properly configured
3. Test with a single provider first
4. Use the simple test script to isolate issues
5. Review provider-specific documentation 