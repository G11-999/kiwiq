# Scraping Service Examples

This directory contains comprehensive examples demonstrating practical usage and advanced concepts of the web scraping service.

## Examples Overview

### 1. Real-World Usage (`example_usage.py`)

Demonstrates practical scraping scenarios with real sites:
- **Otter.ai Blog Crawl**: Large-scale content extraction (1000 URLs)
- **Grain.com Full Crawl**: SaaS site with multiple content types
- **Parallel Crawling**: Running multiple jobs efficiently
- **Custom Processors**: Site-specific data extraction
- **API Endpoint**: Exposing scraping as a service

**Run examples:**
```bash
python example_usage.py otter     # Crawl Otter.ai blog (1000 URLs)
python example_usage.py grain     # Crawl Grain.com (1000 URLs)
python example_usage.py parallel  # Parallel crawl configuration
python example_usage.py analyze   # Data analysis examples
python example_usage.py api       # API endpoint simulation
```

### 2. Advanced Concepts (`example_advanced.py`)

Deep dive into advanced scraping concepts:
- **URL Discovery Control**: Spider vs Playwright mechanisms
- **Streaming Architecture**: How streaming provides constant memory
- **JavaScript SPAs**: Configuration for modern web apps
- **Per-Request Control**: Dynamic behavior modification
- **Practical Tips**: Optimization and monitoring

**Run examples:**
```bash
python example_advanced.py discovery  # URL discovery mechanisms
python example_advanced.py streaming  # Streaming architecture
python example_advanced.py spa        # JavaScript SPA config
python example_advanced.py behavior   # Discovery comparison
python example_advanced.py tips       # Practical tips
python example_advanced.py demo       # Full demonstration
```

## Key Concepts

### Real-World Patterns (from `example_usage.py`)

**Otter.ai Processor:**
- Blog post extraction with metadata
- Pricing plan structured data
- Career listings parsing
- Content categorization

**Grain.com Processor:**
- Feature extraction
- Integration discovery
- Case study analysis
- Multi-type content handling

### Advanced Features (from `example_advanced.py`)

**URL Discovery:**
- **Spider Discovery**: Static HTML parsing (always active)
- **Playwright Discovery**: JavaScript rendering (configurable)
- **Deduplication**: Redis ensures URLs crawled once
- **should_follow_link()**: Consistent filtering for both methods

**Streaming Benefits:**
- **Constant Memory**: 1KB or 1M items = same memory usage
- **Zero Data Loss**: Items saved immediately
- **Simple Config**: Just add StreamingFilePipeline
- **Real-time Monitoring**: `tail -f` output files

## Configuration Examples

### Large-Scale Blog Crawl (Otter.ai)
```python
{
    'max_urls_per_domain': 1000,
    'processor': 'otter.ai',
    'custom_settings': {
        'ITEM_PIPELINES': {
            'pipelines.StreamingFilePipeline': 300,
        },
        'CONCURRENT_REQUESTS': 16,
        'DOWNLOAD_DELAY': 0.5,
    }
}
```

### JavaScript-Heavy Site
```python
{
    'custom_settings': {
        'TIER_RULES': {
            r'^https://app\.site\.com/.*': 'playwright',
        },
        'PLAYWRIGHT_DISCOVER_URLS': True,
        'PLAYWRIGHT_MAX_DISCOVERIES_PER_PAGE': 100,
    }
}
```

### Parallel Crawling
```python
# Run multiple jobs with resource limits
jobs = [
    {'site': 'otter.ai', 'max_urls': 500},
    {'site': 'grain.com', 'max_urls': 500},
]
# Each job gets conservative settings
'CONCURRENT_REQUESTS': 8  # Lower per spider
'DOWNLOAD_DELAY': 1       # More delay when parallel
```

## Output Processing

The `.jsonl` format enables easy analysis:

```bash
# Basic statistics
wc -l items.jsonl
jq -r .page_type items.jsonl | sort | uniq -c

# Extract specific data
jq -r 'select(.page_type=="blog_post") | .title' items.jsonl
jq -r 'select(.plans) | .plans[] | [.name, .price] | @csv' items.jsonl

# Real-time monitoring
tail -f items.jsonl | jq '{url, title, page_type}'

# Export for analysis
jq -r '[.url, .title, .publish_date] | @csv' items.jsonl > blog_posts.csv
```

## Best Practices

1. **Start Small**: Test with limited URLs first
2. **Use Streaming**: Always use StreamingFilePipeline for large crawls
3. **Monitor Progress**: Use `tail -f` to watch output
4. **Set Limits**: Configure max_urls_per_domain and max_crawl_depth
5. **Be Respectful**: Use appropriate DOWNLOAD_DELAY
6. **Custom Processors**: Create site-specific processors for better extraction

## Common Use Cases

### Content Aggregation
- Blog posts and articles
- Product information
- Job listings
- Documentation

### Market Research  
- Competitor analysis
- Pricing comparison
- Feature tracking
- Content strategy

### Data Collection
- Training data for ML
- Business intelligence
- Content migration
- API alternatives

## Performance Tips

1. **Network I/O Dominates**: Page downloads take 100-1000ms
2. **Disk Writes are Fast**: Streaming adds <1ms overhead
3. **Use Basic Handler**: When JavaScript not needed
4. **Limit Playwright**: Lower concurrency for browser rendering
5. **Redis Deduplication**: Prevents redundant crawling

## Troubleshooting

- **Memory Issues**: Ensure StreamingFilePipeline is enabled
- **Slow Crawling**: Check DOWNLOAD_DELAY and concurrency
- **Missing Content**: Enable Playwright for JavaScript sites
- **Duplicate URLs**: Redis deduplication should handle this
- **Rate Limits**: Increase delays, reduce concurrency 