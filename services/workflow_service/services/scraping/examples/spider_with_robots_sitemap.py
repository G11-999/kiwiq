"""
Example of using the GenericSpider with robots.txt checking and sitemap discovery.

This example demonstrates:
1. Automatic robots.txt checking for all URLs
2. Automatic sitemap discovery and parsing
3. Manual seeding of bot-protected robots.txt and sitemaps
"""

from services.workflow_service.services.scraping.spider import run_scraping_job

# Example 1: Basic crawling with automatic robots.txt and sitemap handling
basic_job_config = {
    'job_id': 'example_basic_001',
    'start_urls': ['https://example.com/', 'https://blog.example.com/'],
    'allowed_domains': ['example.com', 'blog.example.com'],
    'max_urls_per_domain': 100,
    'max_crawl_depth': 3,
    'processor': 'default'
}

# The spider will automatically:
# 1. Fetch and cache robots.txt for example.com and blog.example.com
# 2. Check every URL against robots.txt before following
# 3. Discover and fetch sitemaps for each domain
# 4. Add all URLs from sitemaps to the crawl queue

# Example 2: Manual seeding for bot-protected resources
advanced_job_config = {
    'job_id': 'example_advanced_002',
    'start_urls': ['https://protected-site.com/'],
    'allowed_domains': ['protected-site.com'],
    
    # Manually provide robots.txt content (e.g., fetched through Playwright)
    'manual_robots_txt': {
        'protected-site.com': '''
User-agent: *
Disallow: /admin/
Disallow: /private/
Allow: /public/

User-agent: Googlebot
Allow: /

Sitemap: https://protected-site.com/sitemap.xml
'''
    },
    
    # Manually provide sitemap content
    'manual_sitemaps': {
        'https://protected-site.com/sitemap.xml': '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://protected-site.com/</loc>
        <lastmod>2024-01-01</lastmod>
    </url>
    <url>
        <loc>https://protected-site.com/products</loc>
        <lastmod>2024-01-01</lastmod>
    </url>
    <url>
        <loc>https://protected-site.com/about</loc>
        <lastmod>2024-01-01</lastmod>
    </url>
</urlset>'''
    },
    
    'max_urls_per_domain': 50,
    'max_crawl_depth': 2
}

# Example 3: Using special seed URLs for dynamic fetching
dynamic_job_config = {
    'job_id': 'example_dynamic_003',
    'start_urls': ['https://dynamic-site.com/'],
    'allowed_domains': ['dynamic-site.com'],
    
    # These URLs will be fetched with high priority through advanced anti-bot scraping
    'special_seed_urls': [
        # Simple format - type will be auto-detected
        'https://dynamic-site.com/robots.txt',
        'https://dynamic-site.com/sitemap.xml',
        
        # Explicit format with type specification
        {
            'url': 'https://dynamic-site.com/sitemap-posts.xml',
            'type': 'sitemap'
        },
        {
            'url': 'https://dynamic-site.com/feed.xml',
            'type': 'feed'  # RSS/Atom feeds also supported
        }
    ],
    
    'max_urls_per_domain': 200,
    'max_crawl_depth': 4,
    
    # Custom processor with domain-specific logic
    'processor': 'default',
    'processor_init_params': {
        'custom_param': 'value'
    }
}

# Example 4: Multi-domain with subdomain support
multi_domain_config = {
    'job_id': 'example_multi_004',
    'start_urls': [
        'https://company.com/',
        'https://blog.company.com/',
        'https://shop.company.com/',
        'https://support.company.com/'
    ],
    'allowed_domains': [
        'company.com',
        'blog.company.com',
        'shop.company.com', 
        'support.company.com'
    ],
    
    # Enable crawling all subdomains
    'custom_settings': {
        'ALLOW_ALL_SUBDOMAINS_BY_DEFAULT': True
    },
    
    'max_urls_per_domain': 100,
    'max_crawl_depth': 3
}

# The spider will:
# 1. Fetch robots.txt for each subdomain separately
# 2. Discover sitemaps for each subdomain's homepage
# 3. Respect different robots.txt rules per subdomain

if __name__ == '__main__':
    # Run one of the example configurations
    result = run_scraping_job(basic_job_config)
    print(f"Job completed: {result}") 