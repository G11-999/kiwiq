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

### Billing Information

The Crawler Scraper node uses a **flat-rate billing model** based on the number of URLs processed:

- **Cost**: 5 processed URLs per cent ($0.01 per 5 URLs = $0.002 per URL)
- **Cached results are free**: Only new scraping consumes credits
- **Credit allocation**: Credits are allocated before scraping based on estimated URLs
- **Credit adjustment**: After execution, credits are adjusted based on actual URLs processed
- **Billing based on documents stored**: You're charged based on the actual number of pages successfully scraped and stored

**Example Cost Calculation**:
- Max processed URLs per domain: 200
- Number of domains: 2
- Estimated URLs: 200 × 2 = 400 URLs
- Estimated cost: 400 × $0.002 = $0.80
- If only 150 URLs were actually scraped: Final cost = 150 × $0.002 = $0.30

**Insufficient Credits**: If you don't have enough credits, the node will fail with an error before starting the scraping job.

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
- **`browser_pool_enabled`**: Default depends on system settings (typically `false`)
- **`browser_pool_size`**: Default 5 browsers for JavaScript rendering
- **`browser_pool_timeout`**: Default 30 seconds per page (system-level default)

**Recommendation**: Focus on configuring inputs rather than these settings. The defaults work well for most use cases.

### Content Classification and Markdown Cleaning

The node can classify pages as blog posts using an LLM and filter the returned sample accordingly.

- `classify_pages_as_blog` (bool, default `true`): If enabled, pages are classified and `scraped_data` is filtered to include only items where `is_blog == true`.
- `blog_classifier_model` (str, default from system settings): OpenAI model used for classification (e.g., `gpt-5-nano`).
- `blog_classifier_max_length` (int, default from system settings): Maximum characters considered from the `cleaned_markdown_content` field during classification.
- `clean_markdown` (bool, default `true`): If enabled, the node returns cleaned markdown content in the preview items. The output field `markdown_content` will be sourced from `cleaned_markdown_content` (URLs stripped, irrelevant boilerplate removed). If disabled, `markdown_content` will be sourced from `raw_markdown_content`.

### Data Quality Threshold

The node includes a data quality check to ensure sufficient content was collected:

- `min_blog_and_page_count` (int, default `10`, range: 1-100): Minimum number of pages required in the filtered sample for the result to be considered useful. If fewer pages are collected after filtering (blog classification, path filtering, etc.), the output field `has_insufficient_blog_and_page_count` will be set to `true` to indicate the data may not be sufficient for downstream processing.

Notes:
- Classification occurs in the scraping pipeline. When enabled, each stored document includes an `is_blog` boolean.
- For node output, the preview list `scraped_data` is filtered by `is_blog == true` when classification is enabled.
- **Automatic Disable**: Blog classification is automatically disabled when `include_only_paths` is specified in input, as path-based filtering provides more targeted content selection.
- **Quality Check**: The threshold is applied to the final filtered sample (after blog classification and other filtering), not the raw scraped count.



## Input (`CrawlerScraperInput`) - Focus Here

This is where you should focus your configuration efforts. Input parameters directly control what gets scraped and how much data is collected.

### Required Fields

```json
{
  "start_urls": [
    "https://example.com/blog",
    "https://example.com/news"
  ]
}
```

- **`start_urls`** (List[str], **Required**): URLs to begin crawling from
  - Must be valid HTTP/HTTPS URLs
  - These are your entry points - the crawler will discover more pages from here
  - **Impact**: More start URLs = more comprehensive coverage of the site
  
- **`allowed_domains`** (List[str], Optional): Domains allowed for crawling
  - Only pages from these domains will be scraped
  - If omitted, domains are automatically derived from `start_urls` (base domains)
  - Maximum 5 domains per job
  - **Impact**: More domains = broader data collection but potentially slower execution

### Path Filtering (Optional but Powerful)

Control which URL paths are crawled and processed using include/exclude patterns.

```json
{
  "include_only_paths": ["/blog", "/news", "/articles/*"],
  "exclude_paths": ["/admin/*", "/api/*"]
}
```

- **`include_only_paths`** (Optional[List[str]], default `None`): List of URL path patterns or full URLs to include during crawling. If specified, only URLs matching these patterns will be followed and processed. Supports path patterns (`/blog/*`, `/news`), full URL patterns (`https://example.com/blog/*`, `http://site.com/news`), wildcard matching with `*`, and prefix matching. For full URLs, the domain must match the target URL's domain. Homepage URLs are always included unless explicitly excluded.
- **`exclude_paths`** (Optional[List[str]], default `None`): List of URL path patterns or full URLs to exclude during crawling. URLs matching these patterns will not be followed or processed. Supports path patterns (`/admin/*`, `/api`), full URL patterns (`https://example.com/admin/*`, `http://site.com/api`), wildcard matching with `*`, and prefix matching. For full URLs, the domain must match the target URL's domain. Takes precedence over `include_only_paths`.

**Pattern Matching Logic**:
1. **Path patterns**: Traditional path-based matching
   - **Wildcard matching**: Use `*` for flexible patterns (e.g., `/blog/*` matches `/blog/post1`, `/blog/category/tech`)
   - **Prefix matching**: Pattern acts as prefix (e.g., `/blog` matches `/blog`, `/blog/post1`, `/blogpost`) - implemented as `path.startswith(pattern)`
   - **Exact matching**: Pattern matches exactly (e.g., `/contact` matches only `/contact`)

2. **Full URL patterns**: Complete URL-based matching
   - **Domain matching**: Full URL patterns only apply to URLs with matching domains
   - **Path extraction**: Domain-specific path is extracted and matched using the same logic as path patterns
   - **Examples**: `https://example.com/blog/*` only matches URLs on `example.com` domain with paths starting with `/blog/`

**Note**: The matching logic combines both fnmatch wildcard support and prefix matching. A URL matches a pattern if either the wildcard pattern matches OR the path starts with the pattern string. For full URL patterns, domain matching is enforced first.

**Homepage Exception**: Homepage URLs (`/`, `/index.html`, `/home`, etc.) are always allowed in `should_follow_link` unless explicitly forbidden in `exclude_paths`. This ensures the crawler can start from and return to homepages even with restrictive include patterns.

**Processing vs Following**: Path filtering applies to both link following (`should_follow_link`) and content processing (`should_process_link`). A URL must pass path filtering to be both followed and processed.

**Caching Integration**: Path filtering configurations are considered when matching cached results. The cache system takes into account both `include_only_paths` and `exclude_paths` settings to ensure cached results match your current filtering criteria.

**Blog Classification Interaction**: When `include_only_paths` is specified, automatic blog classification (`classify_pages_as_blog`) is disabled. This is because path-based filtering already provides content targeting, making LLM-based blog classification redundant.

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
  - **Path Filtering Integration**: Cache matching considers `include_only_paths` and `exclude_paths` settings

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
- **`mongodb_namespaces`** (Union[str, List[str]]): MongoDB namespace(s) where data is stored
  - Format: `crawler_scraper_results_{uuid}_{YYYYMMDD}_{domain}`
  - On fresh runs, this is a list of concrete namespaces (one per domain)
  - When results are served from cache, this may be a single namespace pattern string (e.g., `crawler_scraper_results_{uuid}_*`)
  - Use this value to query stored results in subsequent nodes
- **`documents_stored`** (int): Number of documents successfully stored
- **`total_scraped_count`** (int): Total documents available (may include cached results)

### Sample Data
- **`scraped_data`** (Optional[List[Dict]]): Sample of scraped documents (up to 5 items)
  - Provides preview of extracted content
  - Full results are in MongoDB - use `mongodb_namespaces` to query them
  - If `classify_pages_as_blog` is enabled, this list is filtered to include only documents where `is_blog` is `true`
- **`has_insufficient_blog_and_page_count`** (bool): Indicates whether the scraping job collected fewer pages than the minimum threshold (`min_blog_and_page_count`) after filtering. When `true`, the scraped data may not be sufficient for meaningful downstream processing, and you may need to adjust scraping parameters or target different content.

### Cache Information
- **`used_cached_results`** (bool): Whether cached results were used
- **`cached_results_age_hours`** (Optional[float]): Age of cached results in hours

### Technical SEO and Robots
- **`technical_seo_summary`** (Optional[Dict]): Aggregated technical SEO metrics across pages when enabled
- **`robots_analysis`** (Optional[Dict]): Per-domain robots.txt analysis (disallowed prefixes, agent rules, crawl delays)

## Example Configurations

### Basic Blog Scraping
```json
{
  "node_config": {
    // Use all defaults - blog classification is enabled by default
  },
  "input": {
    "start_urls": ["https://company.com/blog"],
    "allowed_domains": ["company.com"],
    "max_processed_urls_per_domain": 50,
    "use_cached_scraping_results": true
  }
}
```

**Note**: This example doesn't use `include_only_paths`, so blog classification remains enabled and will filter the output to include only detected blog posts.

### Disable Blog Filtering (Return all page types in preview)
```json
{
  "node_config": {
    "classify_pages_as_blog": false
  },
  "input": {
    "start_urls": ["https://example.com"],
    "allowed_domains": ["example.com"]
  }
}
```

### Lower Quality Threshold for Small Sites
```json
{
  "node_config": {
    "min_blog_and_page_count": 3
  },
  "input": {
    "start_urls": ["https://small-blog.com"],
    "allowed_domains": ["small-blog.com"],
    "max_processed_urls_per_domain": 25
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

### Path Filtering Examples

#### Include Only Blog and News Content
```json
{
  "input": {
    "start_urls": ["https://example.com"],
    "allowed_domains": ["example.com"],
    "max_processed_urls_per_domain": 100,
    "include_only_paths": ["/blog", "/news", "/articles/*", "/posts/*"]
  }
}
```
This will crawl:
- Homepage (`/`) - always allowed due to homepage exception  
- `/blog` and any subpaths (`/blog/post1`, `/blog/category/tech`)
- `/news` and any subpaths (`/news/2024/article`)
- `/articles/anything` (wildcard match)
- `/posts/anything` (wildcard match)

But will skip:
- `/about`, `/contact`, `/services` (don't match patterns)

**Note**: Blog classification is automatically disabled since `include_only_paths` is specified.

#### Include Using Full URL Patterns
```json
{
  "input": {
    "start_urls": ["https://example.com", "https://blog.example.com"],
    "allowed_domains": ["example.com", "blog.example.com"],
    "max_processed_urls_per_domain": 100,
    "include_only_paths": [
      "https://example.com/blog/*",
      "https://blog.example.com/posts/*",
      "/news"
    ]
  }
}
```
This will crawl:
- Homepage (`/`) on both domains - homepage exception
- `https://example.com/blog/anything` - full URL pattern match on example.com
- `https://blog.example.com/posts/anything` - full URL pattern match on blog.example.com  
- `/news` on both domains - path pattern match

But will skip:
- `https://example.com/about` - doesn't match full URL patterns for example.com
- `https://blog.example.com/about` - doesn't match full URL patterns for blog.example.com
- `https://example.com/posts/anything` - full URL pattern specifies blog.example.com only

#### Exclude Admin and API Endpoints
```json
{
  "input": {
    "start_urls": ["https://webapp.com"],
    "allowed_domains": ["webapp.com"],
    "exclude_paths": ["/admin", "/api/*", "/private/*", "/login", "/register"]
  }
}
```
This will crawl everything except:
- `/admin` and subpaths (`/admin/dashboard`, `/admin/users`)
- Any API endpoints (`/api/v1/users`, `/api/data`)
- Private sections (`/private/docs`)
- Authentication pages (`/login`, `/register`)

#### Combined Include/Exclude (Exclude Takes Precedence)
```json
{
  "input": {
    "start_urls": ["https://company.com"],
    "allowed_domains": ["company.com"],
    "include_only_paths": ["/docs", "/help", "/support"],
    "exclude_paths": ["/docs/internal", "/help/admin"]
  }
}
```
This will crawl:
- Homepage (`/`) - homepage exception
- `/docs/public`, `/docs/api` - matches include pattern
- `/help/faq`, `/help/guides` - matches include pattern  
- `/support` and subpaths - matches include pattern

But will skip:
- `/docs/internal` and subpaths - excluded takes precedence
- `/help/admin` and subpaths - excluded takes precedence
- `/about`, `/contact` - don't match include patterns

#### Force Homepage Exclusion (Rare Use Case)
```json
{
  "input": {
    "start_urls": ["https://example.com/blog"],
    "allowed_domains": ["example.com"],
    "include_only_paths": ["/blog"],
    "exclude_paths": ["/", "/index.html"]
  }
}
```
This will explicitly exclude the homepage despite the homepage exception, since exclude patterns take precedence.

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

### Path Filtering Impact
- **Include patterns**: Restricts crawling to specific sections, reducing execution time and data volume
- **Exclude patterns**: Prevents crawling unwanted areas (admin, APIs) improving efficiency and avoiding restricted content
- **Over-restrictive includes**: May miss valuable content if patterns are too narrow
- **Homepage exception**: Ensures crawler functionality even with restrictive patterns
- **Cache integration**: Path filtering settings are considered in cache matching, ensuring cached results align with current filtering criteria
- **Blog classification**: Automatically disabled when `include_only_paths` is used, as path targeting makes content classification redundant

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
The node returns a filtered preview of each document with safe, high-signal fields:
```json
{
  "_job_id": "crawler_20240115_143000_abc123",
  "url": "https://example.com/article",
  "markdown_content": "Page content as Markdown (source depends on clean_markdown)",
  "technical_seo": {
    "dates": { /* detected publish/update dates if available */ }
  },
  "is_url_in_sitemap": true,
  "last_modified_from_sitemap": "2024-01-15T10:30:00Z",
  "feed_published_parsed": "2024-01-15T08:00:00Z",
  "feed_updated_parsed": "2024-01-15T09:00:00Z",
  "feed_created_parsed": "2024-01-14T23:00:00Z"
}
```

#### Field provenance: `markdown_content`

- When `clean_markdown` is `true` (default), `scraped_data[i].markdown_content` comes from `cleaned_markdown_content` which removes markdown links' URLs and prunes non-primary content. Link texts are preserved in brackets (e.g., `[Example](https://x.com)` → `[Example]`).
- When `clean_markdown` is `false`, `scraped_data[i].markdown_content` comes from `raw_markdown_content` (direct markdown conversion with minimal cleaning).

## Data Quality Threshold

The Crawler Scraper node includes a built-in data quality check to help ensure that scraping jobs collect sufficient content for meaningful downstream processing.

### How It Works

1. **Threshold Setting**: The `min_blog_and_page_count` configuration (default: 10) sets the minimum number of pages required in the final filtered sample.

2. **Quality Check**: After all filtering is applied (blog classification, path filtering, etc.), the node counts the pages in the final `scraped_data` sample.

3. **Quality Indicator**: The output field `has_insufficient_blog_and_page_count` is set to:
   - `false` if the filtered sample meets or exceeds the threshold (sufficient data)
   - `true` if the filtered sample is below the threshold (insufficient data)

### When Quality Checks Trigger

The quality threshold is evaluated on the **final filtered sample**, which means it accounts for:
- Blog classification filtering (when enabled)
- Path filtering effects (include/exclude patterns)
- Content extraction success/failure
- Any other filtering applied during processing

### Using Quality Information

**In Workflow Logic**:
```json
{
  "conditional_logic": {
    "if": "crawler_output.has_insufficient_blog_and_page_count == true",
    "then": "retry_with_broader_parameters",
    "else": "proceed_with_analysis"
  }
}
```

**Common Responses to Insufficient Data**:
- Increase `max_processed_urls_per_domain` to collect more pages
- Broaden `include_only_paths` patterns or remove restrictive filtering
- Disable blog classification if it's filtering too aggressively
- Try different start URLs or domains with more content
- Lower the `min_blog_and_page_count` threshold if appropriate for your use case

### Quality vs. Quantity Balance

- **Higher thresholds** (15-30): Ensure robust datasets but may require more extensive crawling
- **Lower thresholds** (5-10): Accept smaller datasets but faster execution
- **Very low thresholds** (1-3): Useful for testing or when any content is valuable

**Note**: The quality check is informational - the node will still return all collected data even when the threshold isn't met. This allows downstream nodes to decide how to handle insufficient data scenarios.

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

### Path Filtering Best Practices
1. **Start without filters** to understand site structure, then add targeted patterns
2. **Use exclude patterns** to avoid unwanted areas (admin, API endpoints, login pages)
3. **Be specific with includes** - overly broad patterns may still crawl unwanted content
4. **Test patterns carefully** - verify they match the intended URL structure
5. **Combine strategically** - use both include/exclude for precise control
6. **Consider prefix matching** - pattern `/blog` catches `/blog`, `/blog/posts`, `/blogroll`
7. **Use full URL patterns for multi-domain precision** - when crawling multiple domains, use full URL patterns to target specific paths on specific domains
8. **Mix pattern types** - combine path patterns (apply to all domains) with full URL patterns (domain-specific) for flexible control

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
- **Path Filtering**: Use include/exclude paths to focus on specific website sections (e.g., only blog posts) or avoid unwanted areas (e.g., admin pages)
- **Robots/Sitemaps**: The node analyzes robots.txt and sitemaps and stores a robots analysis snapshot alongside results
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

### Insufficient Data Quality (`has_insufficient_blog_and_page_count` is `true`)
This indicates the final filtered sample contains fewer pages than the `min_blog_and_page_count` threshold:

**First, diagnose the cause**:
- Check the `scraped_data` sample size vs. `documents_stored` - if much smaller, filtering is removing most content
- Review `stats` for crawling issues (robots.txt blocks, errors, etc.)
- If blog classification is enabled, many pages may have been classified as non-blog content

**Solutions to try**:
- **Increase crawling limits**: Raise `max_processed_urls_per_domain` to collect more raw content
- **Broaden path filtering**: Make `include_only_paths` patterns less restrictive or remove them entirely
- **Disable blog classification**: Set `classify_pages_as_blog: false` if it's filtering too aggressively
- **Adjust quality threshold**: Lower `min_blog_and_page_count` if your use case can work with smaller datasets
- **Try different targets**: Use different `start_urls` or domains that may have more relevant content
- **Check site structure**: Some sites may have most content behind login or in areas not accessible to crawlers

### Cache Not Working
- **Check** `use_cached_scraping_results` is `true`
- **Verify** same start URLs are being used
- **Consider** if `cache_lookback_period_days` is too short
- **Path filtering mismatch**: Cache considers both `include_only_paths` and `exclude_paths` - different filtering settings won't match cached results

### JavaScript Content Missing
- **Ensure** `browser_pool_enabled` is `true` in system settings
- **Note**: Browser pool settings are system-wide, not per-job configurable 
 
### Path Filtering Issues
- **Too few results with include_only_paths**: Check if patterns are too restrictive or don't match actual URL structure
- **Patterns not working**: Verify URL paths start with `/` and patterns use correct syntax
- **Homepage blocked unexpectedly**: Check if homepage is explicitly listed in `exclude_paths`
- **Full URL patterns not matching**: Verify the domain in the full URL pattern exactly matches the target domain (case-sensitive)
- **Mixed domains with full URL patterns**: Remember that full URL patterns only apply to their specific domain - use path patterns for cross-domain matching
- **Debug path matching**: Enable debug logging to see which URLs are blocked by path filtering

### Allowed Domains Behavior
- If `allowed_domains` is omitted, the node will automatically derive base domains from `start_urls`.
- Include subdomains explicitly (e.g., `blog.example.com`) if you need to restrict crawling to specific subdomains. When omitted, the spider allows subdomains of the base domain.

### Path Filtering Behavior
- **Pattern Types**: Supports both path patterns (`/blog`, `/admin/*`) and full URL patterns (`https://example.com/blog`, `http://site.com/admin/*`).
- **Pattern Matching**: Uses fnmatch wildcard (`*`) and prefix matching via `startswith()`. Pattern `/blog` matches `/blog`, `/blog/post1`, `/blogpost`.
- **Domain Filtering**: Full URL patterns only match URLs with exactly matching domains (case-sensitive).
- **Path Normalization**: All paths are normalized to start with `/` before matching.
- **Priority**: Exclude patterns always take precedence over include patterns.
- **Homepage Exception**: Homepage URLs are allowed in link following unless explicitly excluded.
- **Implementation Detail**: A path matches if either `fnmatch.fnmatch(path, pattern)` returns True OR `path.startswith(pattern)` returns True. For full URLs, domain must match first.
