# Scraping Service with Redis Integration and Generic Spider API

## Overview

This document describes the implementation of the enhanced web scraping service with Redis integration for domain limiting, depth control, job isolation, and a flexible Generic Spider API that can be configured via API for any website.

## Key Features Implemented

### 1. Domain Limiting
- **Global Setting**: `MAX_URLS_PER_DOMAIN` (default: 100)
- **Per-Job Override**: `JOB_<job_id>_MAX_URLS_PER_DOMAIN`
- **How it works**: Tracks URLs per domain using Redis counters, blocks requests when limit reached
- **Result**: In testing, successfully filtered 1,436 URLs that exceeded domain limits

### 2. Depth Control
- **Max Depth Setting**: `MAX_CRAWL_DEPTH` (default: 5)
- **Priority Calculation**: `priority = 100 - (depth * 10)`
- **Result**: Ensures breadth-first crawling, lower depth URLs processed first

### 3. Job Isolation
- **Queue Strategy**: Can use 'job' or 'spider' strategy
- **Separate Queues**: Each job gets its own Redis queue
- **Separate Deduplication**: Each job maintains its own dupefilter set
- **Cleanup**: Automatic purging of job data on completion

### 4. Concurrent Request Control
- **Setting**: `CONCURRENT_REQUESTS_PER_DOMAIN` (default: 10)
- **Managed by Scrapy's built-in middleware**

### 5. Simple Streaming Storage
- **Streaming Pipeline**: Writes each item immediately to disk
- **No Buffering**: Zero risk of data loss
- **JSON Format**: Line-delimited JSON (.jsonl files)
- **Constant Memory**: Memory usage doesn't grow with crawl size

## Architecture

### Key Components

1. **`settings.py`** - Centralized configuration
   - Redis key patterns
   - Key construction methods
   - Priority calculation
   - Domain parsing utilities

2. **`redis_sync_client.py`** - Synchronous Redis client
   - Uses standard redis-py library
   - Avoids async/event loop conflicts with Scrapy
   - Provides queue, counter, and cleanup methods

3. **`scrapy_redis_integration.py`** - Custom Scrapy scheduler
   - Replaces Scrapy's default scheduler
   - Integrates Redis for request queuing
   - Implements domain limiting logic
   - Tracks depth statistics

4. **`pipelines.py`** - Simple streaming pipeline
   - StreamingFilePipeline: Writes each item immediately
   - No buffering, no complexity
   - Line-delimited JSON format

5. **`spider.py`** - Generic Spider with Processor Support
   - Configurable processors for domain-specific logic
   - Processors receive initialization parameters
   - `allowed_domains` automatically passed from spider

### Redis Key Structure

```
# Request queue (sorted set)
queue:<spider_name>:<job_id>:requests

# Deduplication filter (set)
queue:<spider_name>:<job_id>:requests:dupefilter

# Domain counter
domain:<domain>:<job_id>

# Depth statistics (hash)
depth_stats:<spider_name>:<job_id>
```

## Processor Configuration

### Overview

Processors handle domain-specific extraction logic and can be configured via job settings:

```python
job_config = {
    'processor': 'custom_processor',
    'allowed_domains': ['example.com'],  # Automatically passed to processor
    
    'processor_init_params': {
        # Additional parameters for processor
        'api_key': 'your_key',
        'extract_metadata': True
    }
}
```

### Creating Configurable Processors

```python
class MyProcessor(BaseProcessor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Access parameters
        self.api_key = kwargs.get('api_key')
        # self.allowed_domains is provided by base class
```

Key points:
- Always accept `*args, **kwargs`
- Call `super().__init__(*args, **kwargs)`
- Spider's `allowed_domains` is automatically included

## URL Discovery: The Dual Mechanism

### Understanding the Two Discovery Paths

The scraping service has two distinct URL discovery mechanisms that work together:

#### 1. Spider Discovery (spider.py)
- **Location**: `GenericSpider.parse()` → `_discover_urls()`
- **How it works**: 
  - Extracts links from HTML using CSS selectors
  - Finds URLs in JavaScript code
  - Calls `response.follow()` which goes through Scrapy's scheduler
- **Characteristics**:
  - Lightweight and fast
  - Finds static links only
  - Always respects `should_follow_link()`
  - Goes through normal Scrapy request flow

#### 2. Playwright Discovery (scrapy_redis_integration.py)
- **Location**: `TieredDownloadHandler._download_playwright()` → `_discover_urls()`
- **How it works**:
  - Renders page with full browser
  - Executes JavaScript
  - Scrolls to trigger lazy loading
  - Discovers dynamically created links
- **Characteristics**:
  - Resource intensive
  - Finds dynamic links (SPAs, infinite scroll)
  - NOW respects `should_follow_link()` (after fix)
  - Directly pushes to Redis queue

### Key Differences and Nuances

1. **Discovery Control**:
   - Spider discovery: Always happens during parsing
   - Playwright discovery: Controlled by `request.meta['discover_urls']`

2. **Link Validation**:
   - Both mechanisms now call `processor.should_follow_link()`
   - Ensures consistent filtering regardless of discovery source

3. **Deduplication**:
   - Redis deduplication handles both sources
   - Prevents crawling same URL twice even if discovered by both methods

4. **Use Cases**:
   - Static sites: Spider discovery is sufficient
   - JavaScript-heavy sites: Playwright discovery is essential
   - Mixed sites: Both work together seamlessly

### Configuration Example

```python
job_config = {
    'job_id': 'spa_crawl',
    'processor': 'custom_processor',
    'custom_settings': {
        # Enable Playwright for specific URL patterns
        'TIER_RULES': {
            r'^https://spa\.site\.com/app/.*': 'playwright',
            r'.*': 'basic'
        },
        # Control discovery
        'PLAYWRIGHT_DISCOVER_URLS': True,
        'PLAYWRIGHT_MAX_DISCOVERIES_PER_PAGE': 100
    }
}
```

## Data Flow: From Spider to Storage

### Simple Streaming Data Flow

```
1. Spider extracts data (parse method)
   ↓
2. Spider yields item (Python dict)
   ↓
3. StreamingFilePipeline:
   - Adds metadata (_job_id, _spider, _timestamp)
   - Converts to JSON
   - Writes line to file
   - Flushes to disk
```

### Why Streaming is Better

For web scraping, streaming is superior to buffering because:

1. **Network I/O Dominates**: Downloading a page takes 100-1000ms, writing JSON takes <1ms
2. **No Data Loss**: Every item is saved immediately 
3. **Constant Memory**: Memory usage doesn't grow with crawl size
4. **Simpler**: No buffer management, no edge cases
5. **Debuggable**: Can `tail -f` the output file during crawl

### Output Format

Line-delimited JSON (`.jsonl`):
```json
{"url": "https://example.com/page1", "title": "Page 1", "_job_id": "job_123", "_timestamp": "2024-01-15T12:00:01Z"}
{"url": "https://example.com/page2", "title": "Page 2", "_job_id": "job_123", "_timestamp": "2024-01-15T12:00:02Z"}
{"url": "https://example.com/page3", "title": "Page 3", "_job_id": "job_123", "_timestamp": "2024-01-15T12:00:03Z"}
```

Easy to process with standard tools:
```bash
# Count items
wc -l output.jsonl

# Extract titles
jq -r .title output.jsonl

# Filter by page type
grep '"page_type": "blog_post"' output.jsonl
```

## Usage Example

```python
from workflow_service.services.scraping.spider import run_scraping_job

# Configure job
job_config = {
    'job_id': 'job_123',
    'start_urls': ['https://example.com'],
    'allowed_domains': ['example.com'],
    
    # Processor configuration
    'processor': 'custom_processor',
    'processor_init_params': {
        'extract_metadata': True,
        'api_key': 'your_key'
    },
    
    # Limits
    'max_urls_per_domain': 100,
    'max_crawl_depth': 3,
    
    'custom_settings': {
        # Enable streaming pipeline
        'ITEM_PIPELINES': {
            'workflow_service.services.scraping.pipelines.StreamingFilePipeline': 300,
        },
        
        # Enable subdomain crawling
        'ALLOW_ALL_SUBDOMAINS_BY_DEFAULT': True,
        
        # Concurrency
        'CONCURRENT_REQUESTS_PER_DOMAIN': 10,
    }
}

# Run the job
result = run_scraping_job(job_config)
```

## Test Results

### Domain Limiting Test
- Set limit: 20 URLs per domain
- Result: Successfully enforced across multiple domains
  - otter.ai: 20 URLs (limit reached)
  - help.otter.ai: 20 URLs (limit reached)
  - go.otter.ai: 20 URLs (limit reached)
  - Total filtered: 1,436 URLs blocked

### Depth Priority Test
- Crawled pages by depth:
  - Depth 0: 1 page
  - Depth 1: 15 pages  
  - Depth 2: 21 pages
- Confirmed breadth-first traversal

## Benefits

1. **Multi-tenancy**: Each job/customer gets isolated resources
2. **Rate Limiting**: Prevents overwhelming target domains
3. **Scalability**: Redis enables distributed crawling
4. **Flexibility**: Per-job configuration overrides
5. **Monitoring**: Real-time statistics via Redis
6. **Reliability**: Streaming ensures no data loss
7. **Simplicity**: Minimal moving parts, easy to debug

## Configuration Reference

### Spider Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `MAX_URLS_PER_DOMAIN` | 100 | Maximum URLs to crawl per domain |
| `MAX_CRAWL_DEPTH` | 5 | Maximum depth to crawl |
| `CONCURRENT_REQUESTS_PER_DOMAIN` | 10 | Concurrent requests per domain |
| `REDIS_QUEUE_KEY_STRATEGY` | 'spider' | Queue isolation strategy ('job' or 'spider') |
| `SCRAPY_JOB_ID` | None | Job identifier for isolation |
| `SCHEDULER_PURGE_ON_CLOSE` | False | Clean up Redis data on spider close |
| `ALLOW_ALL_SUBDOMAINS_BY_DEFAULT` | False | Enable subdomain crawling in Playwright |

### Pipeline Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `PIPELINE_BASE_DIR` | 'services/.../data' | Base directory for output files |

### Per-Job Configuration

```python
# Job configuration
job_config = {
    'processor': 'custom_processor',
    'processor_init_params': {
        'api_key': 'key123',
        'custom_setting': 'value'
    }
}

# Override domain limit for specific job
settings['JOB_job123_MAX_URLS_PER_DOMAIN'] = 50

# Override depth for specific job  
settings['JOB_job123_MAX_CRAWL_DEPTH'] = 2
```

### URL Discovery Control

The `discover_urls` setting controls whether Playwright should discover URLs during page rendering:

```python
# Global setting (applies to all Playwright-rendered pages)
settings['PLAYWRIGHT_DISCOVER_URLS'] = True  # Default: True

# Per-request control (overrides global setting)
request.meta['discover_urls'] = False  # Disable for this specific request
```

**When to disable discovery:**
- Deep pages (to prevent exponential growth)
- Non-content pages (login, settings, etc.)
- Pages with known excessive links
- When you only need the page content, not its links

**Example in processor:**
```python
def on_response(self, response, spider):
    # Disable discovery for deep pages
    if response.meta.get('depth', 0) >= 3:
        response.meta['discover_urls'] = False
    return data
```

### Pipeline Priority

Scrapy pipelines execute in order based on their priority number (lower executes first):

```python
'ITEM_PIPELINES': {
    'ValidationPipeline': 100,      # Runs 1st - Validate data
    'EnrichmentPipeline': 200,      # Runs 2nd - Add metadata
    'StreamingFilePipeline': 300,   # Runs 3rd - Store data
    'MetricsPipeline': 400,         # Runs 4th - Track stats
}
```

**Common priority ranges:**
- 0-99: Validation and filtering
- 100-199: Data cleaning and normalization
- 200-299: Data enrichment and transformation
- 300-399: Storage pipelines
- 400-499: Analytics and monitoring
- 500+: Post-processing and cleanup

**Key points:**
- Pipelines can modify or drop items
- If a pipeline drops an item, subsequent pipelines won't see it
- Use consistent ranges across your project
- Leave gaps for future pipelines

## Integration with Workflow Service

The scraping service integrates seamlessly with the workflow service:

1. **Node Registration**: Scraping nodes can be registered in the workflow registry
2. **Job Tracking**: Each workflow execution gets a unique job ID
3. **Resource Isolation**: Each workflow's scraping is isolated
4. **Progress Monitoring**: Real-time stats available via Redis

## Future Enhancements

1. **Distributed Crawling**: Multiple workers pulling from same Redis queue
2. **Advanced Scheduling**: Time-based crawling, priority queues
3. **Bandwidth Limiting**: Track and limit bandwidth usage
4. **Proxy Rotation**: Integrate proxy management
5. **MongoDB Integration**: Direct storage to MongoDB (when needed)
