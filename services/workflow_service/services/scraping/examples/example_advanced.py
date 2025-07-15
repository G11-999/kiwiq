"""
Advanced Scraping Examples

This file demonstrates advanced concepts:
1. URL Discovery Control (Spider vs Playwright)
2. Streaming Pipeline Architecture
3. Per-Request Configuration
4. JavaScript-Heavy Sites
"""

from datetime import datetime
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from workflow_service.services.scraping.spider import GenericSpider, PROCESSOR_REGISTRY, BaseProcessor


class AdvancedProcessor(BaseProcessor):
    """Processor demonstrating advanced control features."""
    
    def on_response(self, response, spider):
        """Extract data and control discovery per-page."""
        data = super().on_response(response, spider)
        
        # Track discovery source
        data['discovery_source'] = response.meta.get('discovered_from', 'seed_url')
        data['depth'] = response.meta.get('depth', 0)
        
        # Control discovery based on page content
        if data['depth'] >= 3:
            # Disable discovery for deep pages
            response.meta['discover_urls'] = False
            spider.logger.info(f"Disabled discovery at depth {data['depth']}")
        
        return data
    
    def should_follow_link(self, url, response, spider):
        """
        Fine-grained URL filtering - called by BOTH:
        1. Spider's parse method (static HTML discovery)
        2. Playwright downloader (JavaScript discovery)
        """
        # Get configuration
        follow_patterns = spider.job_config.get('follow_patterns', [])
        skip_patterns = spider.job_config.get('skip_patterns', [])
        
        # Skip patterns take precedence
        for pattern in skip_patterns:
            if pattern in url:
                return False
        
        # If follow patterns exist, URL must match one
        if follow_patterns:
            return any(pattern in url for pattern in follow_patterns)
        
        return True


PROCESSOR_REGISTRY['advanced'] = AdvancedProcessor


def example_discovery_control():
    """
    Example 1: URL Discovery Control
    
    Demonstrates the dual discovery mechanisms and how to control them.
    """
    
    print("=== URL Discovery Control ===\n")
    
    print("1. TWO Discovery Mechanisms:")
    print("   a) Spider Discovery (spider.py parse method)")
    print("      - Extracts from static HTML")
    print("      - Always active")
    print("      - Controlled by should_follow_link()")
    print()
    print("   b) Playwright Discovery (scrapy_redis_integration.py)")  
    print("      - Extracts from rendered JavaScript")
    print("      - Controlled by request.meta['discover_urls']")
    print("      - Also respects should_follow_link()")
    print()
    
    # Configuration examples
    configs = {
        "No Discovery": {
            'custom_settings': {
                'PLAYWRIGHT_DISCOVER_URLS': False,  # Disable Playwright discovery
            },
            'processor': 'advanced',  # Processor can disable per-request
        },
        
        "Selective Discovery": {
            'follow_patterns': ['/blog/', '/articles/'],
            'skip_patterns': ['.pdf', 'mailto:', '/login'],
            'custom_settings': {
                'PLAYWRIGHT_DISCOVER_URLS': True,
            }
        },
        
        "JavaScript-Heavy Site": {
            'custom_settings': {
                'PLAYWRIGHT_DISCOVER_URLS': True,
                'PLAYWRIGHT_MAX_DISCOVERIES_PER_PAGE': 100,
                'TIER_RULES': {
                    r'^https://spa\.site\.com/.*': 'playwright',
                }
            }
        }
    }
    
    for name, config in configs.items():
        print(f"Configuration: {name}")
        print(f"  Settings: {config}")
        print()
    
    print("2. Per-Request Control:")
    print("   # In your processor:")
    print("   def on_response(self, response, spider):")
    print("       # Disable discovery for specific pages")
    print("       if 'no-follow' in response.url:")
    print("           response.meta['discover_urls'] = False")
    print()
    
    print("3. Discovery + Deduplication:")
    print("   URL → should_follow_link() → Redis dedup → Queue")
    print("   - should_follow_link: Business logic (skip login pages)")
    print("   - Redis dedup: Prevents re-crawling")
    print("   - Both mechanisms share the same deduplication")


def example_streaming_architecture():
    """
    Example 2: Streaming Pipeline Architecture
    
    Shows how streaming provides constant memory usage for any crawl size.
    """
    
    print("\n=== Streaming Pipeline Architecture ===\n")
    
    print("1. Data Flow:")
    print("   Spider → StreamingFilePipeline → Disk")
    print("   ↓")
    print("   parse() extracts data")
    print("   ↓")
    print("   yield dict (item)")
    print("   ↓")
    print("   Pipeline adds metadata")
    print("   ↓")
    print("   Write JSON line to file")
    print("   ↓")
    print("   Flush immediately")
    print()
    
    print("2. Memory Characteristics:")
    print("   - Memory per item: ~1-10KB (just the current item)")
    print("   - Memory for 1M items: Still ~1-10KB!")
    print("   - No buffering = no memory growth")
    print("   - Network I/O dominates (100-1000ms per page)")
    print("   - Disk write is instant (<1ms)")
    print()
    
    print("3. Configuration (that's all!):")
    print("   'ITEM_PIPELINES': {")
    print("       'workflow_service.services.scraping.pipelines.StreamingFilePipeline': 300,")
    print("   }")
    print()
    
    print("4. Pipeline Priority (the 300):")
    print("   Lower numbers run first:")
    print("   100 - Data validation")
    print("   200 - Data transformation")
    print("   300 - Storage (streaming)")
    print("   400 - Analytics/metrics")


def example_javascript_spa_config():
    """
    Example 3: JavaScript SPA Configuration
    
    Real configuration for modern JavaScript applications.
    """
    
    job_config = {
        'job_id': f'spa_crawl_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
        'start_urls': ['https://app.example.com'],
        'processor': 'advanced',
        
        # Only follow app routes
        'follow_patterns': [
            '/app/', '/dashboard/', '/projects/',
            '/api/data/',  # SPAs often load data via API
        ],
        'skip_patterns': [
            '/static/', '.js', '.css', '.map',
            '/auth/', '/login', '/logout'
        ],
        
        'custom_settings': {
            # Enable tiered download handler
            'DOWNLOAD_HANDLERS': {
                'https': 'workflow_service.services.scraping.scrapy_redis_integration.TieredDownloadHandler',
            },
            
            # Use Playwright for app pages
            'TIER_RULES': {
                r'^https://app\.example\.com/app/.*': 'playwright',
                r'^https://app\.example\.com/dashboard/.*': 'playwright',
                r'^https://app\.example\.com/api/.*': 'basic',  # APIs don't need rendering
            },
            
            # Enable JavaScript discovery
            'PLAYWRIGHT_DISCOVER_URLS': True,
            'PLAYWRIGHT_MAX_DISCOVERIES_PER_PAGE': 100,
            
            # Streaming storage
            'ITEM_PIPELINES': {
                'workflow_service.services.scraping.pipelines.StreamingFilePipeline': 300,
            },
            
            # Lower concurrency for Playwright
            'CONCURRENT_REQUESTS': 4,
            'DOWNLOAD_TIMEOUT': 60,  # JavaScript rendering takes time
        }
    }
    
    print("\n=== JavaScript SPA Configuration ===\n")
    print("Key Points:")
    print("1. Playwright renders JavaScript to discover dynamic URLs")
    print("2. Tier rules determine which pages need rendering")
    print("3. API endpoints use basic handler (faster)")
    print("4. Lower concurrency due to browser resource usage")
    print("5. Streaming handles any amount of discovered content")
    print()
    print(f"Configuration: {job_config}")


def example_discovery_behavior():
    """
    Example 4: Discovery Behavior Comparison
    
    Shows real differences between discovery methods.
    """
    
    print("\n=== Discovery Behavior in Practice ===\n")
    
    # Static site example
    print("1. Static News Site:")
    print("   Spider Discovery finds:")
    print("   - /article/123")
    print("   - /category/tech")
    print("   - /about")
    print("   Total: ~50 URLs from homepage")
    print()
    
    # JavaScript site example  
    print("2. Same Site with Infinite Scroll:")
    print("   Spider Discovery finds: 50 URLs (initial HTML)")
    print("   Playwright Discovery adds:")
    print("   - /article/124-150 (from scroll)")
    print("   - /api/articles?page=2-10 (AJAX calls)")
    print("   - /related/content (dynamic sidebar)")
    print("   Total: ~200 URLs from homepage")
    print()
    
    print("3. Deduplication prevents redundancy:")
    print("   - Spider finds: /article/123")
    print("   - Playwright also finds: /article/123")
    print("   - Redis deduplication ensures it's crawled once")
    print()
    
    print("4. should_follow_link() provides consistency:")
    print("   - Both discoveries call the same method")
    print("   - Ensures uniform filtering logic")
    print("   - Business rules applied consistently")


def example_practical_tips():
    """
    Example 5: Practical Configuration Tips
    """
    
    print("\n=== Practical Tips ===\n")
    
    print("1. When to Use Playwright Discovery:")
    print("   ✓ Single-page applications")
    print("   ✓ Infinite scroll")
    print("   ✓ Dynamic content loading")
    print("   ✗ Static blogs")
    print("   ✗ Simple HTML sites")
    print()
    
    print("2. Optimizing Discovery:")
    print("   # Limit discoveries to prevent memory issues")
    print("   'PLAYWRIGHT_MAX_DISCOVERIES_PER_PAGE': 50")
    print()
    print("   # Disable for specific pages")
    print("   if response.url.endswith('/sitemap'):")
    print("       response.meta['discover_urls'] = False")
    print()
    
    print("3. Monitoring:")
    print("   # Watch real-time output")
    print("   tail -f services/workflow_service/services/scraping/data/job_id/items.jsonl | jq .")
    print()
    print("   # Check discovery sources")
    print("   jq .discovery_source items.jsonl | sort | uniq -c")
    print()
    
    print("4. Common Patterns:")
    print("   - Blog: Static discovery only")
    print("   - E-commerce: Playwright for product listings")
    print("   - SaaS docs: Mixed (static + search)")
    print("   - Social media: Heavy JavaScript discovery")


def run_demonstration():
    """
    Run a demonstration crawl showing all concepts.
    """
    
    job_config = {
        'job_id': 'demo_advanced',
        'start_urls': ['https://example.com'],
        'processor': 'advanced',
        'max_urls_per_domain': 100,
        
        # Selective following
        'follow_patterns': ['/blog/', '/products/'],
        'skip_patterns': ['/admin/', '/login', '.pdf'],
        
        'custom_settings': {
            # Streaming pipeline
            'ITEM_PIPELINES': {
                'workflow_service.services.scraping.pipelines.StreamingFilePipeline': 300,
            },
            
            # Mixed discovery
            'DOWNLOAD_HANDLERS': {
                'https': 'workflow_service.services.scraping.scrapy_redis_integration.TieredDownloadHandler',
            },
            'TIER_RULES': {
                r'.*\/products\/.*': 'playwright',  # Dynamic product pages
                r'.*': 'basic',  # Everything else
            },
            'PLAYWRIGHT_DISCOVER_URLS': True,
            
            # Output location
            'PIPELINE_BASE_DIR': 'demo_output',
        }
    }
    
    print("\n=== Running Demonstration ===\n")
    print("This configuration demonstrates:")
    print("- Selective URL following")
    print("- Mixed static/JavaScript discovery")
    print("- Streaming to disk")
    print("- Per-page discovery control")
    print()
    print("To run: Initialize CrawlerProcess with these settings")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "discovery":
            example_discovery_control()
        elif sys.argv[1] == "streaming":
            example_streaming_architecture()
        elif sys.argv[1] == "spa":
            example_javascript_spa_config()
        elif sys.argv[1] == "behavior":
            example_discovery_behavior()
        elif sys.argv[1] == "tips":
            example_practical_tips()
        elif sys.argv[1] == "demo":
            run_demonstration()
    else:
        print("Advanced Scraping Examples")
        print("=" * 50)
        print()
        print("Usage:")
        print("  python example_advanced.py discovery  # URL discovery control")
        print("  python example_advanced.py streaming  # Streaming architecture")
        print("  python example_advanced.py spa        # JavaScript SPA config")
        print("  python example_advanced.py behavior   # Discovery comparison")
        print("  python example_advanced.py tips       # Practical tips")
        print("  python example_advanced.py demo       # Full demonstration")
        print()
        print("Topics covered:")
        print("- Dual discovery mechanisms (Spider + Playwright)")
        print("- Per-request discovery control")
        print("- Streaming pipeline architecture")
        print("- JavaScript-heavy site configuration")
        print("- Practical optimization tips") 