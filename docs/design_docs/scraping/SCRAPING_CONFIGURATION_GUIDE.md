# Scraping Service Configuration Guide

## Redis Client Management

### Job-Specific Redis Clients

The scraping service uses a **job-specific Redis client architecture** to ensure proper resource management:

1. **Single Owner**: The `RedisScheduler` creates and owns the Redis clients for each job
2. **Shared Access**: Clients are stored in `crawler._redis_clients` for all components to access
3. **Automatic Cleanup**: Clients are properly closed when the job completes

### Architecture Overview

```
CrawlerProcess
  └── Crawler (job-specific)
      ├── RedisScheduler
      │   ├── Creates AsyncRedisClient
      │   ├── Creates SyncRedisClient
      │   └── Stores in crawler._redis_clients
      ├── Spider
      │   └── Accesses via self.redis_client property
      └── TieredDownloadHandler
          └── Accesses via self.redis_client property
```

### Key Benefits

1. **Connection Pooling**: Each job shares a single connection pool
2. **No Global State**: Redis clients are job-scoped, not global
3. **Automatic Cleanup**: Clients are closed when job completes
4. **Thread Safety**: Connection pools handle concurrent access

### Usage in Components

```python
# In Spider
redis_client = self.redis_client  # Gets sync client from crawler

# In Downloader
redis_client = self.redis_client  # Gets async client from crawler

# Utility functions accept client as parameter
stats = get_spider_stats('my_spider', redis_client=redis_client)
```

## URL Limiting and Filtering

The scraping service applies URL filtering at multiple stages. Understanding these stages helps avoid conflicts and unexpected behavior.

### Filtering Stages (in order)

1. **Spider Discovery** (parse method)
   - URLs discovered from HTML
   - Subject to `should_follow_link()` check

2. **Playwright Discovery** (if enabled)
   - Additional URLs discovered from JavaScript
   - Also subject to `should_follow_link()` check
   - Respects subdomain settings (see below)

3. **Scheduler Enqueue**
   - Depth limit check
   - Domain limit check (after should_follow_link)
   - Duplicate filter

4. **Item Processing** (NEW)
   - `should_process_link()` check for content quality
   - Processed items limit check per domain

### Subdomain Support

Enable automatic crawling of all subdomains:

```python
{
    'allowed_domains': ['example.com'],  # Just parent domain
    'custom_settings': {
        'ALLOW_ALL_SUBDOMAINS_BY_DEFAULT': True
    }
}
```

When enabled:
- `example.com` → matches `www.example.com`, `blog.example.com`, `api.example.com`, etc.
- Only affects Playwright URL discovery
- Spider's `allowed_domains` should contain parent domains only

Example: Crawling a site with multiple subdomains:
```python
{
    'start_urls': ['https://example.com'],
    'allowed_domains': ['example.com'],  # Parent only
    'custom_settings': {
        'ALLOW_ALL_SUBDOMAINS_BY_DEFAULT': True,
        # Will discover: blog.example.com, docs.example.com, etc.
    }
}

### Domain URL Limiting

**Two-Level Limiting System**:
1. **MAX_URLS_PER_DOMAIN**: Controls how many URLs are enqueued for crawling
2. **MAX_PROCESSED_URLS_PER_DOMAIN**: Controls how many items are actually yielded

This dual system provides predictable output control.

#### Configuration
```python
{
    'max_urls_per_domain': 1000,         # Maximum URLs to enqueue per domain
    'max_processed_urls_per_domain': 100, # Maximum items to yield per domain
    'max_crawl_depth': 5,                # Maximum depth to crawl
}
```

### Content Quality Filtering

The `should_process_link()` method filters content AFTER extraction but BEFORE yielding:

```python
def should_process_link(self, response: Response, data: Dict[str, Any], spider: Spider) -> bool:
    """Filter out low-quality content."""
    # Skip error pages
    if response.status >= 400:
        return False
        
    # Check content quality
    if data.get('page_type') == 'blog_post':
        # Must have title and sufficient content
        if not data.get('title') or len(data.get('content', '')) < 200:
            return False
            
    return True
```

### Predictable Output Control

Use MAX_PROCESSED_URLS_PER_DOMAIN when you need exact control over output:

```python
{
    # Allow broad discovery
    'max_urls_per_domain': 1000,
    
    # But limit actual output
    'max_processed_urls_per_domain': 50,  # Exactly 50 items per domain
}
```

Benefits:
- **Predictable costs**: Know exactly how many items you'll process
- **Quality control**: Only high-quality content counts toward limit
- **Efficient crawling**: Can discover many URLs but process only the best

### Concurrent Request Settings

**Avoid Redundant Settings**:
```python
# BAD - Redundant configuration
{
    'CONCURRENT_REQUESTS': 100,         # Total limit
    'CONCURRENT_REQUESTS_PER_DOMAIN': 50,  # Per domain
}
# With 2 domains, effective limit is min(100, 2*50) = 100
# The total setting adds no value

# GOOD - Clear configuration
{
    'CONCURRENT_REQUESTS_PER_DOMAIN': 50,  # Per domain limit
    # Total concurrency = domains * per_domain_limit
}
```

### Best Practices

1. **Pre-filter in Processors**
   ```python
   def should_follow_link(self, url: str, response: Response, spider: Spider) -> bool:
       """Filter URLs early to save domain quota."""
       # Reject off-domain URLs
       if 'mydomain.com' not in url:
           return False
       
       # Reject known uninteresting paths
       skip_patterns = ['/login', '/logout', '/api/', '.pdf']
       return not any(pattern in url.lower() for pattern in skip_patterns)
   ```

2. **Quality Filter in should_process_link**
   ```python
   def should_process_link(self, response: Response, data: Dict[str, Any], spider: Spider) -> bool:
       """Only yield high-quality content."""
       # Check for meaningful content
       if not data.get('title') or not data.get('content'):
           return False
       
       # Minimum content length
       if len(data.get('content', '')) < 100:
           return False
           
       return True
   ```

3. **Set Realistic Limits**
   ```python
   {
       # For focused crawls
       'max_urls_per_domain': 100-500,
       'max_processed_urls_per_domain': 50-100,
       'max_crawl_depth': 3-4,
       
       # For comprehensive crawls
       'max_urls_per_domain': 1000-5000,
       'max_processed_urls_per_domain': 500-1000,
       'max_crawl_depth': 5-6,
   }
   ```

4. **Monitor Stats**
   - `scheduler/filtered/should_follow`: URLs filtered by processor
   - `scheduler/filtered/domain_limit`: URLs rejected due to limit
   - `items/filtered/should_process`: Items filtered for quality
   - `items/filtered/processed_limit`: Items rejected due to processed limit
   - `domain_url_counts`: URLs enqueued per domain
   - `domain_processed_counts`: Items actually yielded per domain

### Debugging URL Limits

If seeing fewer items than expected:

1. Check `domain_url_counts` vs `domain_processed_counts`
2. Look for high `items/filtered/should_process` values (quality issues)
3. Review `should_process_link()` logic - it may be too restrictive
4. Consider if error pages are consuming processed quota

### Example: Multi-Domain Crawl

```python
job_config = {
    'start_urls': [
        'https://example.com',
        'https://another.com',
    ],
    
    'allowed_domains': ['example.com', 'another.com'],
    
    # URL discovery limits
    'max_urls_per_domain': 1000,  # Discover up to 1000 URLs per domain
    
    # Output limits  
    'max_processed_urls_per_domain': 100,  # But only yield 100 items per domain
    
    # Depth limit applies to all
    'max_crawl_depth': 4,
    
    'custom_settings': {
        # Concurrent requests per domain
        'CONCURRENT_REQUESTS_PER_DOMAIN': 8,
        # Total = 2 domains * 8 = 16 concurrent max
        
        # Don't set CONCURRENT_REQUESTS - it's calculated automatically
    }
}
```

Expected output: Exactly 200 items (100 per domain), assuming sufficient quality content exists.

### URL Discovery Control

Control URL discovery per request:
```python
# Disable URL discovery for specific pages
yield Request(
    url,
    meta={
        'discover_urls': False,  # Don't discover new URLs from this page
        'depth': depth + 1
    }
)

# Or disable globally for Playwright
'PLAYWRIGHT_DISCOVER_URLS': False
```

## Summary

The key improvements made:
1. **Pre-filtering**: URLs are filtered by `should_follow_link()` BEFORE counting against domain limits
2. **Quality filtering**: `should_process_link()` ensures only quality content is yielded
3. **Dual limits**: Separate limits for URL discovery vs actual processing
4. **Start URL Protection**: Start URLs bypass should_follow_link filtering
5. **Consistent Filtering**: Both spider and Playwright discoveries respect the same filters
6. **Clear Stats**: New stats help identify where URLs and items are being filtered

This ensures domain quotas are used efficiently and output is predictable. 