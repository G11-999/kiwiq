# Usage Guide: CrawlerScraperNode

This guide explains how to configure and use the `CrawlerScraperNode` to perform web scraping operations with automatic MongoDB storage. This node provides a high-level interface for crawling websites and extracting content with proper user/organization data isolation.

## Purpose

The `CrawlerScraperNode` allows your workflow to:

- **Crawl multiple websites** starting from specified URLs with configurable depth and limits
- **Respect web standards** by automatically handling robots.txt files and sitemaps
- **Extract structured data** using configurable processors for domain-specific content
- **Store results automatically** in MongoDB with proper user/organization isolation
- **Cache results intelligently** to avoid redundant scraping of recently crawled content
- **Handle JavaScript-heavy sites** using browser pool support for dynamic content rendering
- **Scale performance** with configurable concurrency and rate limiting

## How Scraping Works

The node integrates with a sophisticated scraping infrastructure that follows web scraping best practices:

1. **Discovery Phase**: Starting from your provided URLs, the crawler discovers additional pages by following links within the allowed domains
2. **Respectful Crawling**: Automatically checks and respects robots.txt rules and discovers URLs from sitemaps
3. **Content Extraction**: Uses configurable processors to extract structured data from each page
4. **Storage**: Automatically stores all extracted data in MongoDB with proper namespace isolation
5. **Caching**: Results are cached to avoid re-scraping recently crawled content

## Important: Performance and Resource Considerations

Unlike API-based scraping, web crawling is **resource-intensive** and can impact target websites. The node includes several important safeguards:

- **Rate Limiting**: Built-in delays between requests to avoid overwhelming target servers
- **Respectful Defaults**: Conservative settings that balance performance with respectful crawling
- **Domain Limits**: Maximum of 5 domains per job to prevent overly broad crawling
- **URL Limits**: Default limits prevent runaway crawling that could consume excessive resources

**Key Principle**: The default configuration is carefully tuned for respectful, efficient crawling. Avoid changing configuration settings unless you have specific requirements and understand the implications.

## Configuration (`CrawlerScraperConfig`) - Use Defaults

The node comes with carefully tuned default settings. **We strongly recommend using the defaults** unless you have specific requirements. Here's what the configuration controls:

### Processor Settings (Usually Don't Change)
- **`processor`**: Default "default" uses generic HTML extraction. Custom processors available for specific sites
- **`processor_init_params`**: Additional processor parameters (advanced use only)

### Crawling Behavior (Rarely Change)
- **`respect_robots_txt`**: Default `true` - respects website crawling rules
- **`crawl_sitemaps`**: Default `true` - discovers URLs from sitemaps
- **`enable_blog_url_pattern_priority_boost`**: Default varies - prioritizes blog/news content

### Performance Settings (Don't Change Without Good Reason)
- **`concurrent_requests_per_domain`**: Default 100 - carefully tuned for most sites
- **`download_delay`**: Default 0.005 seconds - respectful delay between requests

### Browser Pool Settings (Advanced)
- **`browser_pool_enabled`**: Default depends on system settings
- **`browser_pool_size`**: Default 5 browsers for JavaScript rendering
- **`browser_pool_timeout`**: Default 5 seconds per page

**Recommendation**: Focus on configuring inputs rather than these settings. The defaults work well for most use cases.

## Input (`CrawlerScraperInput`) - Focus Here

This is where you should focus your configuration efforts. Input parameters directly control what gets scraped and how much data is collected.

### Required Fields

```json
{
  "start_urls": [
    "https://example.com/blog",
    "https://example.com/news"
  ],
  "allowed_domains": [
    "example.com",
    "blog.example.com"
  ]
}
```

- **`start_urls`** (List[str], **Required**): URLs to begin crawling from
  - Must be valid HTTP/HTTPS URLs
  - These are your entry points - the crawler will discover more pages from here
  - **Impact**: More start URLs = more comprehensive coverage of the site
  
- **`allowed_domains`** (List[str], **Required**): Domains allowed for crawling
  - Only pages from these domains will be scraped
  - Maximum 5 domains per job
  - **Impact**: More domains = broader data collection but potentially slower execution

### Crawling Limits (Key Performance Controls)

```json
{
  "max_urls_per_domain": 250,
  "max_processed_urls_per_domain": 200, 
  "max_crawl_depth": 4
}
```

- **`max_urls_per_domain`** (int, default 250): Maximum URLs to discover per domain
  - This is the discovery limit - how many pages the crawler will find
  - **Impact**: Higher values = more comprehensive coverage but longer execution time
  - **Range**: 1-100,000 (be very careful with high values)

- **`max_processed_urls_per_domain`** (int, default 200): Maximum URLs to actually scrape per domain
  - This is the processing limit - how many pages will have content extracted
  - Must be ≤ `max_urls_per_domain`
  - **Impact**: Higher values = more data but significantly longer execution time and storage usage

- **`max_crawl_depth`** (int, default 4): How deep to follow links from start URLs
  - 0 = only start URLs, 1 = start URLs + directly linked pages, etc.
  - **Impact**: Higher depth = discovers more pages but can lead to very broad crawling
  - **Range**: 0-10 (depths >6 rarely useful and can be very slow)

### Caching Options (Performance Optimization)

```json
{
  "use_cached_scraping_results": true,
  "cache_lookback_period_days": 7
}
```

- **`use_cached_scraping_results`** (bool, default `true`): Use cached results if available
  - **Impact**: `true` = faster execution for recently scraped content, `false` = always fresh data
  - **Recommendation**: Keep `true` unless you specifically need fresh data

- **`cache_lookback_period_days`** (int, default 7): How far back to look for cached results
  - **Impact**: Longer periods = more cache hits but potentially staler data
  - **Range**: 1-30 days

### Storage Settings

```json
{
  "is_shared": false
}
```

- **`is_shared`** (bool, default `false`): Whether scraped data is accessible to all organization users
  - `false` = only accessible to the user who triggered the job
  - `true` = accessible to all users in the organization
  - **Impact**: Affects data visibility and collaboration capabilities

## Output (`CrawlerScraperOutput`)

The node provides comprehensive information about the scraping operation and results.

### Job Identification
- **`job_id`** (str): Unique identifier for the scraping job (format: `crawler_YYYYMMDD_HHMMSS_<uuid>`)
- **`status`** (str): Final job status
  - `"completed"` - Fresh scraping completed successfully
  - `"completed_from_cache"` - Results retrieved from cache
  - `"failed"` - Scraping job failed

### Execution Statistics
- **`stats`** (Dict): Detailed execution statistics including:
  - Pages crawled and items scraped
  - Errors encountered
  - Robots.txt and sitemap handling results
  - Timing information
- **`completed_at`** (str): ISO 8601 timestamp when job completed

### MongoDB Storage Information
- **`mongodb_namespaces`** (Union[str, List[str]]): MongoDB namespace pattern where data is stored
  - Format: `crawler_scraper_results_{uuid}_{YYYYMMDD}_{domain}`
  - Use this pattern to query stored results in subsequent nodes
- **`documents_stored`** (int): Number of documents successfully stored
- **`total_scraped_count`** (int): Total documents available (may include cached results)

### Sample Data
- **`scraped_data`** (Optional[List[Dict]]): Sample of scraped documents (up to 5 items)
  - Provides preview of extracted content
  - Full results are in MongoDB - use `mongodb_namespaces` to query them

### Cache Information
- **`used_cached_results`** (bool): Whether cached results were used
- **`cached_results_age_hours`** (Optional[float]): Age of cached results in hours

## Example Configurations

### Basic Blog Scraping
```json
{
  "node_config": {
    // Use all defaults - no config needed for most cases
  },
  "input": {
    "start_urls": ["https://company.com/blog"],
    "allowed_domains": ["company.com"],
    "max_processed_urls_per_domain": 50,
    "use_cached_scraping_results": true
  }
}
```

### Multi-Domain News Scraping
```json
{
  "input": {
    "start_urls": [
      "https://techcrunch.com/category/artificial-intelligence/",
      "https://venturebeat.com/ai/"
    ],
    "allowed_domains": ["techcrunch.com", "venturebeat.com"],
    "max_processed_urls_per_domain": 100,
    "max_crawl_depth": 2,
    "cache_lookback_period_days": 1
  }
}
```

### Comprehensive Site Analysis
```json
{
  "input": {
    "start_urls": ["https://competitor.com"],
    "allowed_domains": ["competitor.com"],
    "max_urls_per_domain": 500,
    "max_processed_urls_per_domain": 300,
    "max_crawl_depth": 5,
    "use_cached_scraping_results": false,
    "is_shared": true
  }
}
```

## Impact of Input Changes

### Increasing URL Limits
- **Small increase** (50→100 URLs): ~2x execution time, ~2x storage usage
- **Large increase** (100→500 URLs): ~5x execution time, ~5x storage usage, potential timeout issues
- **Very large increase** (500→2000+ URLs): May hit system limits, very long execution times

### Increasing Crawl Depth
- **Depth +1**: Potentially exponential increase in discovered URLs
- **Depth >5**: Often discovers too many low-value pages
- **Recommendation**: Start with depth 2-3, increase gradually if needed

### Multiple Domains
- **2-3 domains**: Manageable, good for comparative analysis
- **4-5 domains**: Maximum allowed, significantly longer execution
- **Performance impact**: Each additional domain roughly multiplies total execution time

### Cache Settings
- **Disabling cache** (`use_cached_scraping_results: false`): Always fresh data but much slower
- **Shorter cache period** (1-2 days): More up-to-date data but fewer cache hits
- **Longer cache period** (14-30 days): Faster execution but potentially stale data

## MongoDB Data Access

Scraped data is automatically stored in MongoDB with the following structure:

### Namespace Pattern
```
crawler_scraper_results_{uuid}_{YYYYMMDD}_{domain}
```

### Accessing Results in Subsequent Nodes
Use the `load_customer_data` or `load_multiple_customer_data` nodes with the namespace pattern from the output:

```json
{
  "namespace_pattern": "crawler_scraper_results_abc123_20240115_*",
  "docname_pattern": "*"
}
```

### Document Structure (Typical)
```json
{
  "_job_id": "crawler_20240115_143000_abc123",
  "url": "https://example.com/article",
  "title": "Article Title",
  "content": "Extracted article content...",
  "meta_description": "Article description",
  "published_date": "2024-01-15",
  "author": "Author Name",
  // ... additional extracted fields based on processor
}
```

## Best Practices

### Start Small and Scale
1. **Begin with conservative limits**: 50 URLs, depth 2-3
2. **Test with single domain** before adding multiple domains
3. **Review sample output** before increasing limits
4. **Scale gradually** based on actual needs

### Respectful Crawling
1. **Keep default rate limits** unless absolutely necessary
2. **Use caching** to avoid redundant requests
3. **Don't crawl more than needed** - higher limits aren't always better
4. **Consider target site load** - avoid overwhelming small sites

### Performance Optimization
1. **Enable caching** for most use cases
2. **Use appropriate cache periods** (1-7 days for news, 7-30 days for static content)
3. **Limit crawl depth** to avoid discovering irrelevant pages
4. **Monitor execution time** and adjust limits accordingly

### Data Management
1. **Use descriptive job names** by including relevant dates/targets in start URLs
2. **Set appropriate sharing** (`is_shared`) based on team needs
3. **Plan for storage growth** - each document takes MongoDB space
4. **Clean up old data** periodically if not needed long-term

## Example Graph Schema Integration

```json
{
  "nodes": {
    "web_scraper": {
      "node_id": "web_scraper",
      "node_name": "crawler_scraper",
      "node_config": {
        // Use defaults - no configuration needed
      }
    },
    "process_scraped_content": {
      "node_id": "process_scraped_content", 
      "node_name": "load_multiple_customer_data",
      "node_config": {
        "namespace_pattern_source": "input_field",
        "docname_pattern": "*"
      }
    }
  },
  "edges": [
    {
      "src_node_id": "input",
      "dst_node_id": "web_scraper",
      "mappings": [
        {"src_field": "target_websites", "dst_field": "start_urls"},
        {"src_field": "allowed_domains", "dst_field": "allowed_domains"},
        {"src_field": "max_pages", "dst_field": "max_processed_urls_per_domain"}
      ]
    },
    {
      "src_node_id": "web_scraper", 
      "dst_node_id": "process_scraped_content",
      "mappings": [
        {"src_field": "mongodb_namespaces", "dst_field": "namespace_pattern"}
      ]
    }
  ]
}
```

## Notes for Non-Coders

- **Purpose**: This node automatically crawls websites and saves the content to your database
- **Default Settings**: The node is pre-configured with safe, respectful settings - don't change them unless you understand the impact
- **Focus on Inputs**: Spend your time configuring what to scrape (URLs, domains, limits) rather than how to scrape it
- **Start Small**: Begin with small limits (50 pages) and increase only if you need more data
- **Caching**: Leave caching enabled - it makes repeat jobs much faster
- **Storage**: All scraped content automatically goes to your database where other nodes can access it
- **Performance**: More pages = longer wait times. Balance thoroughness with speed
- **Respectful**: The node automatically follows website rules and doesn't overload servers

## Troubleshooting Common Issues

### Job Takes Too Long
- **Reduce** `max_processed_urls_per_domain` and `max_crawl_depth`
- **Enable** caching if disabled
- **Consider** fewer domains per job

### Not Enough Data Collected
- **Increase** `max_processed_urls_per_domain` gradually
- **Check** if `allowed_domains` includes all relevant subdomains
- **Verify** start URLs are accessible and contain links to more content

### Cache Not Working
- **Check** `use_cached_scraping_results` is `true`
- **Verify** same start URLs are being used
- **Consider** if `cache_lookback_period_days` is too short

### JavaScript Content Missing
- **Ensure** `browser_pool_enabled` is `true` in system settings
- **Note**: Browser pool settings are system-wide, not per-job configurable 