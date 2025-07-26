"""
Example usage of the Generic Spider API for real-world scraping scenarios.

This demonstrates practical configurations for:
1. Blog/content sites (Otter.ai blog)
2. SaaS/product sites (Grain.com)
3. Large-scale crawling (1000+ URLs per domain)
4. Custom processors for specific sites
"""
import json
from typing import Dict, Any
from datetime import datetime
from scrapy.http import Response
from scrapy import Spider
from urllib.parse import urlparse

from scrapy.core.downloader.handlers.http import HTTPDownloadHandler

from workflow_service.services.scraping.spider import (
    run_scraping_job, push_urls_to_redis, get_spider_stats, 
    PROCESSOR_REGISTRY, BaseProcessor
)


# Custom processor for Otter.ai content
class OtterAIProcessor(BaseProcessor):
    """Extract Otter.ai specific content."""
    
    def __init__(self, *args, **kwargs):
        """Initialize with optional parameters."""
        super().__init__(*args, **kwargs)
    
    def on_response(self, response: Response, spider: Spider) -> Dict[str, Any]:
        """Extract data based on Otter.ai's structure."""
        data = super().on_response(response, spider)
        
        # Detect page type from URL patterns
        url = response.url.lower()
        
        if '/blog/' in url and url != 'https://otter.ai/blog':
            # Blog post page
            data['page_type'] = 'blog_post'
            data['title'] = response.css('h1::text').get()
            data['author'] = response.css('.author-name::text, .post-author::text').get()
            data['publish_date'] = response.css('time::attr(datetime), .post-date::text').get()
            data['category'] = response.css('.post-category::text, .category-tag::text').getall()
            
            # Content extraction
            content_selectors = [
                'article .content',
                '.post-content',
                'main [class*="content"]'
            ]
            for selector in content_selectors:
                content = response.css(f'{selector} ::text').getall()
                if content:
                    data['content'] = ' '.join(content).strip()
                    break
                    
            # Extract key insights/highlights
            data['highlights'] = response.css('.highlight, .key-point, blockquote::text').getall()
            
        elif url.endswith('/pricing') or '/pricing' in url:
            # Pricing page
            data['page_type'] = 'pricing'
            data['plans'] = []
            
            for plan in response.css('.pricing-card, .plan-card, [class*="pricing-plan"]'):
                plan_data = {
                    'name': plan.css('h2::text, h3::text, .plan-name::text').get(),
                    'price': plan.css('.price::text, .amount::text').get(),
                    'features': plan.css('li::text, .feature::text').getall()
                }
                if plan_data['name']:
                    data['plans'].append(plan_data)
                    
        elif '/careers' in url or '/jobs' in url:
            # Careers page
            data['page_type'] = 'careers'
            data['job_listings'] = []
            
            for job in response.css('.job-listing, .career-opportunity, [class*="job-post"]'):
                job_data = {
                    'title': job.css('.job-title::text, h3::text').get(),
                    'department': job.css('.department::text, .team::text').get(),
                    'location': job.css('.location::text, .job-location::text').get(),
                    'link': response.urljoin(job.css('a::attr(href)').get() or '')
                }
                if job_data['title']:
                    data['job_listings'].append(job_data)
                    
        elif '/use-cases' in url or '/solutions' in url:
            # Use cases/solutions page
            data['page_type'] = 'use_case'
            data['use_case_title'] = response.css('h1::text').get()
            data['benefits'] = response.css('.benefit::text, .advantage::text').getall()
            data['features'] = response.css('.feature-item::text').getall()
            
        else:
            # General page
            data['page_type'] = 'general'
        
        return data
    
    def should_follow_link(self, url: str, response: Response, spider: Spider) -> bool:
        """Control which links to follow on Otter.ai."""
        # First check robots.txt using parent method
        if not super().should_follow_link(url, response, spider):
            return False

        # Skip external links and assets
        if not any(domain in url for domain in ['otter.ai', 'blog.otter.ai']):
            return False
            
        # Skip media files and documents
        skip_extensions = ('.pdf', '.jpg', '.png', '.mp4', '.zip', '.dmg', '.exe')
        if any(url.lower().endswith(ext) for ext in skip_extensions):
            return False
            
        # Skip authentication and user-specific pages
        skip_patterns = [
            '/login', '/signin', '/signup', '/auth',
            '/dashboard', '/settings', '/account',
            'mailto:', 'tel:', 'javascript:',
            '#', '?utm_', '&utm_'  # Skip fragments and tracking params
        ]
        
        url_lower = url.lower()
        if any(pattern in url_lower for pattern in skip_patterns):
            return False
            
        return True
    
    def get_link_priority(self, url: str, depth: int, response: Response, spider: Spider) -> int:
        """Prioritize important content pages."""
        base_priority = 100 - (depth * 10)
        
        # High priority for content pages
        if '/blog/' in url.lower():
            return base_priority + 20
        elif any(x in url.lower() for x in ['/use-cases', '/solutions', '/features']):
            return base_priority + 15
        elif '/pricing' in url.lower():
            return base_priority + 10
            
        return base_priority
    
    def should_process_link(self, response: Response, data: Dict[str, Any], spider: Spider) -> bool:
        """Filter out low-quality or unwanted content."""
        if spider.settings.getbool('DEBUG_MODE', False):
            return True
        # return True
        
        # Skip error pages
        if response.status >= 400:
            return False
            
        # Check if it's a real content page (has meaningful data)
        page_type = data.get('page_type', 'general')
        
        if page_type == 'blog_post':
            # Must have title and content
            if not data.get('title') or not data.get('content'):
                return False
            # Skip very short blog posts
            if len(data.get('content', '')) < 200:
                return False
                
        elif page_type == 'use_case':
            # Must have use case title
            if not data.get('use_case_title'):
                return False
                
        elif page_type == 'pricing':
            # Must have pricing plans
            if not data.get('plans'):
                return False
                
        # Skip pages that are likely navigation/header/footer only
        if page_type == 'general' and not any(data.get(field) for field in ['title', 'content', 'features']):
            return False
            
        return True


# Custom processor for Grain.com
class GrainProcessor(BaseProcessor):
    """Extract Grain.com specific content."""
    
    def __init__(self, *args, **kwargs):
        """Initialize with optional parameters."""
        super().__init__(*args, **kwargs)
    
    def on_response(self, response: Response, spider: Spider) -> Dict[str, Any]:
        """Extract data based on Grain.com's structure."""
        data = super().on_response(response, spider)
        
        url = response.url.lower()
        
        if '/blog/' in url and not url.endswith('/blog/'):
            # Blog article
            data['page_type'] = 'article'
            data['title'] = response.css('h1::text, .article-title::text').get()
            data['subtitle'] = response.css('h2:first-of-type::text, .article-subtitle::text').get()
            data['author'] = response.css('.author-name::text, [class*="author"]::text').get()
            data['read_time'] = response.css('.read-time::text, .reading-time::text').get()
            
            # Article content
            data['content'] = ' '.join(response.css('article ::text, .article-content ::text').getall())
            
            # Extract tips and best practices
            data['tips'] = response.css('.tip::text, .best-practice::text, .pro-tip::text').getall()
            
        elif '/features' in url:
            # Features page
            data['page_type'] = 'features'
            data['features'] = []
            
            for feature in response.css('.feature, .feature-block, [class*="feature-item"]'):
                feature_data = {
                    'name': feature.css('h3::text, .feature-title::text').get(),
                    'description': feature.css('p::text, .feature-description::text').get(),
                    'benefits': feature.css('li::text').getall()
                }
                if feature_data['name']:
                    data['features'].append(feature_data)
                    
        elif '/integrations' in url:
            # Integrations page
            data['page_type'] = 'integrations'
            data['integrations'] = []
            
            for integration in response.css('.integration, .app-card, [class*="integration-card"]'):
                integration_data = {
                    'name': integration.css('h3::text, .app-name::text').get(),
                    'category': integration.css('.category::text, .type::text').get(),
                    'description': integration.css('p::text').get()
                }
                if integration_data['name']:
                    data['integrations'].append(integration_data)
                    
        elif '/customers' in url or '/case-studies' in url:
            # Customer stories
            data['page_type'] = 'case_study'
            data['company'] = response.css('.company-name::text, h1::text').get()
            data['industry'] = response.css('.industry::text').get()
            data['results'] = response.css('.result::text, .outcome::text').getall()
            data['testimonial'] = response.css('blockquote::text, .testimonial::text').get()
            
        else:
            data['page_type'] = 'general'
            
        return data
    
    def should_follow_link(self, url: str, response: Response, spider: Spider) -> bool:
        """Control which links to follow on Grain.com."""
        if not super().should_follow_link(url, response, spider):
            return False

        # Only follow grain.com links
        if 'grain.com' not in url:
            return False
            
        # Skip auth and app pages
        skip_patterns = [
            '/login', '/signup', '/app.',
            'support.grain.com', 'help.grain.com',
            '.pdf', '.mp4', 'youtube.com', 'vimeo.com'
        ]
        
        url_lower = url.lower()
        return not any(pattern in url_lower for pattern in skip_patterns)
    
    def should_process_link(self, response: Response, data: Dict[str, Any], spider: Spider) -> bool:
        """Filter out low-quality Grain.com content."""
        # Skip error pages
        if response.status >= 400:
            return False
            
        page_type = data.get('page_type', 'general')
        
        if page_type == 'article':
            # Must have title and content
            if not data.get('title'):
                return False
            # Skip stub articles
            content = data.get('content', '')
            if len(content) < 100:
                return False
                
        elif page_type == 'features':
            # Must have actual features listed
            if not data.get('features'):
                return False
                
        elif page_type == 'integrations':
            # Must have integrations
            if not data.get('integrations'):
                return False
                
        elif page_type == 'case_study':
            # Must have company and some results or testimonial
            if not data.get('company'):
                return False
            if not (data.get('results') or data.get('testimonial')):
                return False
                
        # Skip navigation-only pages
        if page_type == 'general':
            # Check if it has any meaningful content
            meaningful_fields = ['title', 'content', 'features', 'integrations', 'company']
            if not any(data.get(field) for field in meaningful_fields):
                return False
                
        return True


# Register processors
PROCESSOR_REGISTRY['otter.ai'] = OtterAIProcessor
PROCESSOR_REGISTRY['grain.com'] = GrainProcessor


def example_otter_ai_blog_crawl():
    """
    Real-world example: Crawl Otter.ai blog for content insights.
    
    This demonstrates crawling a content-heavy blog with:
    - Custom extraction for blog posts
    - Handling pagination
    - Extracting structured data
    """
    
    job_config = {
        'job_id': f'otter_blog_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
        
        'start_urls': [
            'https://otter.ai',
            # 'https://otter.ai/blog',
            # 'https://blog.otter.ai/',  # They might use subdomain
        ],
        
        'allowed_domains': ['otter.ai', 'blog.otter.ai'],
        'processor': 'otter.ai',
        'debug_mode': True,
        
        # Large-scale settings
        'max_urls_per_domain': 1000,  # Crawl up to 1000 pages
        'max_crawl_depth': 0,  # Blog pagination can be deep
        # 'max_sitemap_depth': 0,  # Sitemap depth
        
        'custom_settings': {
            # Streaming pipeline for handling large crawls
            'ITEM_PIPELINES': {
                'workflow_service.services.scraping.pipelines.StreamingFilePipeline': 300,
            },
            
            # Output directory
            'PIPELINE_BASE_DIR': 'services/workflow_service/services/scraping/data',
            
            # Performance settings
            'CONCURRENT_REQUESTS': 16,
            'CONCURRENT_REQUESTS_PER_DOMAIN': 8,
            'DOWNLOAD_DELAY': 0.5,  # Be respectful
            
            # Handle large pages
            'DOWNLOAD_MAXSIZE': 10485760,  # 10MB
            'DOWNLOAD_TIMEOUT': 30,
            
            # Retry configuration
            'RETRY_TIMES': 2,
            'RETRY_HTTP_CODES': [500, 502, 503, 504, 408, 429],
        }
    }
    
    print(f"Starting Otter.ai blog crawl (up to 1000 pages)...")
    result = run_scraping_job(job_config)
    
    print(f"\nCrawl completed!")
    print(f"Job ID: {result['job_id']}")
    print(f"Check results in: services/workflow_service/services/scraping/data/{result['job_id']}/items.jsonl")

    print("\n\nStats:\n\n", json.dumps(result['stats'], indent=4, default=str))
    
    return result['job_id']


def example_grain_comprehensive_crawl():
    """
    Real-world example: Comprehensive Grain.com crawl.
    
    This demonstrates:
    - SaaS product site crawling
    - Multiple content types (blog, features, integrations)
    - Structured data extraction
    """
    
    job_config = {
        'job_id': f'grain_full_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
        
        'start_urls': [
            'https://grain.com',
            'https://grain.com/blog',
            'https://grain.com/features',
            'https://grain.com/integrations',
            'https://grain.com/customers',
            'https://grain.com/use-cases',
        ],
        
        'allowed_domains': ['grain.com', 'www.grain.com'],
        'processor': 'grain.com',
        
        # Large-scale settings
        'max_urls_per_domain': 1000,
        'max_crawl_depth': 4,
        
        'custom_settings': {
            'ITEM_PIPELINES': {
                'workflow_service.services.scraping.pipelines.StreamingFilePipeline': 300,
            },
            
            'PIPELINE_BASE_DIR': 'services/workflow_service/services/scraping/data',
            
            # Higher performance for comprehensive crawl
            'CONCURRENT_REQUESTS': 20,
            'CONCURRENT_REQUESTS_PER_DOMAIN': 10,
            'DOWNLOAD_DELAY': 0.25,  # Faster but still respectful
            
            # JavaScript handling for dynamic content
            'DOWNLOAD_HANDLERS': {
                'https': 'workflow_service.services.scraping.scrapy_redis_integration.TieredDownloadHandler',
            },
            
            # Use Playwright for dynamic pages
            'TIER_RULES': {
                r'^https://grain\.com/integrations.*': 'playwright',  # Dynamic content
                r'^https://grain\.com/features.*': 'playwright',  # Interactive demos
                r'.*': 'basic',  # Static content
            },
            
            'PLAYWRIGHT_DISCOVER_URLS': True,
            'PLAYWRIGHT_MAX_DISCOVERIES_PER_PAGE': 50,
        }
    }
    
    print(f"Starting comprehensive Grain.com crawl...")
    result = run_scraping_job(job_config)
    
    print(f"\nCrawl completed!")
    print(f"Job ID: {result['job_id']}")
    print(f"Data location: services/workflow_service/services/scraping/data/{result['job_id']}/items.jsonl")
    
    return result['job_id']


def example_combined_multi_site_crawl():
    """
    Real-world example: Crawl multiple sites in a single job.
    
    This demonstrates:
    - Single job handling multiple domains
    - Per-domain limits (1000 each)
    - Mixed processor handling
    - Efficient resource usage
    """
    
    # Create a combined processor that handles both sites
    class MultiSiteProcessor(BaseProcessor):
        """Processor that delegates to site-specific processors."""
        
        def __init__(self, *args, allowed_domains=None, **kwargs):
            """
            Initialize multi-site processor with domain configuration.
            
            Args:
                allowed_domains: List of allowed domains (automatically passed from spider)
                **kwargs: Additional parameters passed to parent
            """
            super().__init__(*args, **kwargs)
            
            # Store domain configuration
            self.allowed_domains = allowed_domains or []
            
            # Initialize sub-processors with same configuration
            processor_kwargs = {
                'allowed_domains': self.allowed_domains
            }
            self.otter_processor = OtterAIProcessor(**processor_kwargs)
            self.grain_processor = GrainProcessor(**processor_kwargs)
        
        def on_response(self, response: Response, spider: Spider) -> Dict[str, Any]:
            """Route to appropriate processor based on domain."""
            if 'otter.ai' in response.url:
                return self.otter_processor.on_response(response, spider)
            elif 'grain.com' in response.url:
                return self.grain_processor.on_response(response, spider)
            else:
                # Fallback to base processor
                return super().on_response(response, spider)
        
        def should_follow_link(self, url: str, response: Response, spider: Spider) -> bool:
            """Route link filtering to appropriate processor."""
            if not super().should_follow_link(url, response, spider):
                return False

            if 'otter.ai' in response.url:
                return self.otter_processor.should_follow_link(url, response, spider)
            elif 'grain.com' in response.url:
                return self.grain_processor.should_follow_link(url, response, spider)
            else:
                # Default: follow if same domain
                return urlparse(url).netloc == urlparse(response.url).netloc
        
        def get_link_priority(self, url: str, depth: int, response: Response, spider: Spider) -> int:
            """Route priority calculation to appropriate processor."""
            if 'otter.ai' in url:
                return self.otter_processor.get_link_priority(url, depth, response, spider)
            elif 'grain.com' in url:
                return self.grain_processor.get_link_priority(url, depth, response, spider)
            else:
                return super().get_link_priority(url, depth, response, spider)
        
        def should_process_link(self, response: Response, data: Dict[str, Any], spider: Spider) -> bool:
            """Route processing filter to appropriate processor."""
            if 'otter.ai' in response.url:
                return self.otter_processor.should_process_link(response, data, spider)
            elif 'grain.com' in response.url:
                return self.grain_processor.should_process_link(response, data, spider)
            else:
                # Default: accept if has data
                return bool(data)
    
    # Register the multi-site processor
    PROCESSOR_REGISTRY['multi_site'] = MultiSiteProcessor
    
    job_config = {
        'job_id': f'combined_crawl_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
        
        # Start URLs from both sites
        'start_urls': [
            # Otter.ai URLs
            'https://otter.ai',
            'https://otter.ai/blog',
            'https://otter.ai/use-cases',
            'https://otter.ai/pricing',
            
            # Grain.com URLs
            'https://grain.com',
            'https://grain.com/blog',
            'https://grain.com/features',
            'https://grain.com/integrations',
            'https://grain.com/customers',
        ],
        
        # Allow both domains
        'allowed_domains': [
            'otter.ai', 'blog.otter.ai',
            'grain.com', 'www.grain.com'
        ],
        
        # Use multi-site processor
        'processor': 'multi_site',
        
        # High limits for comprehensive crawl
        'max_urls_per_domain': 500,  # Max URLs to enqueue per domain
        'max_processed_urls_per_domain': 100,  # Max items to actually yield per domain
        'max_crawl_depth': 5,
        
        'custom_settings': {
            # Streaming pipeline
            'ITEM_PIPELINES': {
                'workflow_service.services.scraping.pipelines.StreamingFilePipeline': 300,
            },
            
            'PIPELINE_BASE_DIR': 'services/workflow_service/services/scraping/data',
            
            # Higher concurrency for multiple domains
            'CONCURRENT_REQUESTS': 100,  # Total concurrent
            'CONCURRENT_REQUESTS_PER_DOMAIN': 50,  # Per domain
            'DOWNLOAD_DELAY': 0.01,
            
            # Handle both static and dynamic content
            'DOWNLOAD_HANDLERS': {
                'https': 'workflow_service.services.scraping.scrapy_redis_integration.TieredDownloadHandler',
            },
            
            # Use Playwright for known dynamic pages
            'TIER_RULES': {
                # Otter.ai dynamic pages
                r'^https://otter\.ai/use-cases.*': 'playwright',
                
                # Grain.com dynamic pages
                r'^https://grain\.com/integrations.*': 'playwright',
                r'^https://grain\.com/features.*': 'playwright',
                
                # Everything else uses basic handler
                r'.*': 'basic',
            },
            
            # Enable URL discovery for dynamic pages
            'PLAYWRIGHT_DISCOVER_URLS': True,
            'PLAYWRIGHT_MAX_DISCOVERIES_PER_PAGE': 50,
            
            # Redis configuration for domain tracking
            'SCHEDULER': 'workflow_service.services.scraping.scrapy_redis_integration.RedisScheduler',
            # 'REDIS_URL': 'redis://localhost:6379/0',
            'REDIS_QUEUE_KEY_STRATEGY': 'job',
            
            # Memory and timeout settings
            'DOWNLOAD_MAXSIZE': 10485760,  # 10MB
            'DOWNLOAD_TIMEOUT': 30,
            
            # Retry configuration
            'RETRY_TIMES': 2,
            'RETRY_HTTP_CODES': [500, 502, 503, 504, 408, 429],
        }
    }
    
    print(f"Starting combined multi-site crawl...")
    print(f"Target: Otter.ai + Grain.com (up to 1000 URLs each)")
    print(f"Job ID: {job_config['job_id']}")
    print()
    
    result = run_scraping_job(job_config)
    
    print(f"\nCrawl completed!")
    print(f"Output: services/workflow_service/services/scraping/data/{result['job_id']}/items.jsonl")
    print()
    print("Analyze results by site:")
    print(f"  # Count by domain")
    print(f"  jq -r .url services/workflow_service/services/scraping/data/{result['job_id']}/items.jsonl | cut -d/ -f3 | sort | uniq -c")
    print()
    print(f"  # Otter.ai pages")
    print(f"  grep 'otter.ai' services/workflow_service/services/scraping/data/{result['job_id']}/items.jsonl | jq -r .page_type | sort | uniq -c")
    print()
    print(f"  # Grain.com pages") 
    print(f"  grep 'grain.com' services/workflow_service/services/scraping/data/{result['job_id']}/items.jsonl | jq -r .page_type | sort | uniq -c")
    
    return result['job_id']


def example_predictable_output_crawl():
    """
    Example: Crawl with predictable output limits.
    
    This demonstrates using MAX_PROCESSED_URLS_PER_DOMAIN to get
    exactly the number of items you want, regardless of how many
    URLs are discovered or enqueued.
    """

    # Create a combined processor that handles both sites
    # class MultiSiteProcessor(BaseProcessor):
    #     """Processor that delegates to site-specific processors."""
        
    #     def __init__(self, *args, allowed_domains=None, **kwargs):
    #         """
    #         Initialize multi-site processor with domain configuration.
            
    #         Args:
    #             allowed_domains: List of allowed domains (automatically passed from spider)
    #             **kwargs: Additional parameters passed to parent
    #         """
    #         super().__init__(*args, **kwargs)
            
    #         # Store domain configuration
    #         self.allowed_domains = allowed_domains or []
            
    #         # Initialize sub-processors with same configuration
    #         processor_kwargs = {
    #             'allowed_domains': self.allowed_domains
    #         }
    #         self.otter_processor = OtterAIProcessor(**processor_kwargs)
    #         self.grain_processor = GrainProcessor(**processor_kwargs)
        
    #     def on_response(self, response: Response, spider: Spider) -> Dict[str, Any]:
    #         """Route to appropriate processor based on domain."""
    #         if 'otter.ai' in response.url:
    #             return self.otter_processor.on_response(response, spider)
    #         elif 'grain.com' in response.url:
    #             return self.grain_processor.on_response(response, spider)
    #         else:
    #             # Fallback to base processor
    #             return super().on_response(response, spider)
        
    #     def should_follow_link(self, url: str, response: Response, spider: Spider) -> bool:
    #         """Route link filtering to appropriate processor."""
    #         if not super().should_follow_link(url, response, spider):
    #             return False

    #         if 'otter.ai' in response.url:
    #             return self.otter_processor.should_follow_link(url, response, spider)
    #         elif 'grain.com' in response.url:
    #             return self.grain_processor.should_follow_link(url, response, spider)
    #         else:
    #             # Default: follow if same domain
    #             return urlparse(url).netloc == urlparse(response.url).netloc
        
    #     def get_link_priority(self, url: str, depth: int, response: Response, spider: Spider) -> int:
    #         """Route priority calculation to appropriate processor."""
    #         if 'otter.ai' in url:
    #             return self.otter_processor.get_link_priority(url, depth, response, spider)
    #         elif 'grain.com' in url:
    #             return self.grain_processor.get_link_priority(url, depth, response, spider)
    #         else:
    #             return super().get_link_priority(url, depth, response, spider)
        
    #     def should_process_link(self, response: Response, data: Dict[str, Any], spider: Spider) -> bool:
    #         """Route processing filter to appropriate processor."""
    #         if response.status >= 400:
    #             return False
            
    #         if "blog" in response.url:
    #             return True
            
    #         return False
    #         # if 'otter.ai' in response.url:
    #         #     return self.otter_processor.should_process_link(response, data, spider)
    #         # elif 'grain.com' in response.url:
    #         #     return self.grain_processor.should_process_link(response, data, spider)
    #         # else:
    #         #     # Default: accept if has data
    #         #     return bool(data)
    
    # # Register the multi-site processor
    # PROCESSOR_REGISTRY['multi_site'] = MultiSiteProcessor
    
    job_config = {
        'job_id': f'predictable_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
        
        'start_urls': [
            'https://otter.ai/blog',
            # 'https://crowdstrike.com',
            'https://grain.com/blog',
        ],
        
        'allowed_domains': ['otter.ai', 'grain.com', 
                            # 'crowdstrike.com'
                            ],
        'processor': 'default',  # multi_site  default
        
        # URL limits
        'max_urls_per_domain': 20000,  # Allow discovering many URLs  # 20000
        'max_processed_urls_per_domain': 200,  # But only process 50 per domain  # 200
        'max_crawl_depth': 4,  # 4
        
        'custom_settings': {
            'ITEM_PIPELINES': {
                'workflow_service.services.scraping.pipelines.StreamingFilePipeline': 300,
            },
            
            'PIPELINE_BASE_DIR': 'services/workflow_service/services/scraping/data',
            
            # Moderate concurrency
            'CONCURRENT_REQUESTS_PER_DOMAIN': 100,
            'DOWNLOAD_DELAY': 0.005,
            
            # Log filtering stats
            'LOG_LEVEL': 'INFO',
        }
    }
    
    print("=" * 70)
    print("Predictable Output Crawl Example")
    print("=" * 70)
    print()
    print("This crawl will:")
    print(f"- Discover up to {job_config['max_urls_per_domain']} URLs per domain")
    print(f"- But only yield {job_config['max_processed_urls_per_domain']} quality items per domain")
    print(f"- Total expected output: ~{job_config['max_processed_urls_per_domain'] * 2} items")
    print()
    print("The should_process_link filters ensure we get high-quality content:")
    print("- Blog posts with sufficient content (>200 chars)")
    print("- Articles with title and content")
    print("- Feature pages with actual features listed")
    print("- No navigation-only or error pages")
    print()
    
    result = run_scraping_job(job_config)
    
    print(f"\nCrawl completed!")
    print(f"Job ID: {result['job_id']}")
    print(f"\nExpected output: exactly {job_config['max_processed_urls_per_domain']} items per domain")
    print(f"(or fewer if not enough quality content exists)")

    print("\n\nStats:\n\n", json.dumps(result['stats'], indent=4, default=str))
    
    return result['job_id']


def example_parallel_large_crawls():
    """
    Example: Running multiple large crawls in parallel.
    
    Shows how to efficiently crawl multiple sites simultaneously
    with proper resource allocation.
    """
    
    # Configuration for parallel crawls
    crawl_configs = [
        {
            'site': 'otter.ai',
            'job_id': f'otter_parallel_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
            'start_urls': ['https://otter.ai/blog', 'https://otter.ai/use-cases'],
            'processor': 'otter.ai',
            'max_urls': 500,  # Split the load
        },
        {
            'site': 'grain.com',
            'job_id': f'grain_parallel_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
            'start_urls': ['https://grain.com/blog', 'https://grain.com/features'],
            'processor': 'grain.com',
            'max_urls': 500,
        },
        {
            'site': 'otter.ai-pricing',
            'job_id': f'otter_pricing_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
            'start_urls': ['https://otter.ai/pricing', 'https://otter.ai/careers'],
            'processor': 'otter.ai',
            'max_urls': 200,
        }
    ]
    
    # Shared settings for all parallel crawls
    shared_settings = {
        'ITEM_PIPELINES': {
            'workflow_service.services.scraping.pipelines.StreamingFilePipeline': 300,
        },
        'PIPELINE_BASE_DIR': 'services/workflow_service/services/scraping/data',
        
        # Conservative settings for parallel execution
        'CONCURRENT_REQUESTS': 8,  # Lower per spider
        'CONCURRENT_REQUESTS_PER_DOMAIN': 4,
        'DOWNLOAD_DELAY': 1,  # More delay when running parallel
        
        # Memory efficiency
        'DOWNLOAD_MAXSIZE': 5242880,  # 5MB limit
        'CONCURRENT_ITEMS': 100,
    }
    
    print("Parallel Crawl Configuration:")
    print("-" * 60)
    print("Running 3 crawls simultaneously with resource limits:")
    print()
    
    for config in crawl_configs:
        job_config = {
            'job_id': config['job_id'],
            'start_urls': config['start_urls'],
            'allowed_domains': [config['site'], f'www.{config["site"]}'],
            'processor': config['processor'],
            'max_urls_per_domain': config['max_urls'],
            'max_crawl_depth': 3,
            'custom_settings': shared_settings
        }
        
        print(f"Job: {config['job_id']}")
        print(f"  Site: {config['site']}")
        print(f"  Max URLs: {config['max_urls']}")
        print(f"  Start URLs: {len(config['start_urls'])}")
        print()
        
        # In production, you would run these with CrawlerProcess
        # or submit to a job queue for parallel execution
    
    print("Benefits of parallel crawling:")
    print("- Better resource utilization")
    print("- Faster overall completion")
    print("- Site-specific configurations")
    print("- Isolated job management")


def example_analyzing_crawl_results():
    """
    Example: Analyzing results from large crawls.
    
    Shows how to process and analyze the scraped data.
    """
    
    print("=== Analyzing Large Crawl Results ===\n")
    
    print("1. Basic Statistics:")
    print("   # Count total pages")
    print("   wc -l services/workflow_service/services/scraping/data/otter_blog_*/items.jsonl")
    print()
    print("   # Count by page type")
    print("   jq -r .page_type services/workflow_service/services/scraping/data/otter_blog_*/items.jsonl | sort | uniq -c")
    print()
    
    print("2. Content Analysis:")
    print("   # Extract all blog titles")
    print("   jq -r 'select(.page_type==\"blog_post\") | .title' items.jsonl")
    print()
    print("   # Find posts about specific topics")
    print("   grep -i \"transcription\" items.jsonl | jq '{title, url}'")
    print()
    
    print("3. Structured Data Extraction:")
    print("   # Extract pricing information")
    print("   jq -r 'select(.page_type==\"pricing\") | .plans[] | [.name, .price] | @csv' items.jsonl")
    print()
    print("   # Extract job listings")
    print("   jq -r 'select(.page_type==\"careers\") | .job_listings[] | [.title, .department, .location] | @csv' items.jsonl")
    print()
    
    print("4. Data Quality Checks:")
    print("   # Find pages with missing data")
    print("   jq 'select(.title == null and .page_type == \"blog_post\")' items.jsonl")
    print()
    print("   # Check for duplicate URLs")
    print("   jq -r .url items.jsonl | sort | uniq -d")
    print()
    
    print("5. Export for Analysis:")
    print("   # Convert to CSV for spreadsheet analysis")
    print("   jq -r '[.url, .page_type, .title, .publish_date] | @csv' items.jsonl > blog_posts.csv")
    print()
    print("   # Extract specific data for NLP")
    print("   jq -r 'select(.content != null) | .content' items.jsonl > all_content.txt")


def example_custom_api_endpoint():
    """
    Example: API endpoint for on-demand crawling.
    
    Shows how to expose crawling as a service.
    """
    
    def handle_crawl_request(request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle API request for web crawling.
        
        POST /api/crawl
        {
            "url": "https://example.com",
            "max_pages": 100,
            "extract_blog_content": true,
            "follow_patterns": ["/blog/", "/news/"]
        }
        """
        
        # Validate and prepare configuration
        url = request_data['url']
        domain = url.split('/')[2]
        
        job_config = {
            'job_id': f'api_{domain}_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
            'start_urls': [url],
            'allowed_domains': [domain, f'www.{domain}'],
        'max_urls_per_domain': request_data.get('max_pages', 100),
        'max_crawl_depth': request_data.get('depth', 3),
            
            # Determine processor
            'processor': 'otter.ai' if 'otter.ai' in domain else 
                        'grain.com' if 'grain.com' in domain else 
                        'default',
            
            # Apply follow patterns if provided
            'follow_patterns': request_data.get('follow_patterns', []),
            
            'custom_settings': {
                'ITEM_PIPELINES': {
                    'workflow_service.services.scraping.pipelines.StreamingFilePipeline': 300,
                },
                'PIPELINE_BASE_DIR': 'api_crawls',
                'CONCURRENT_REQUESTS': 8,
                'DOWNLOAD_DELAY': 0.5,
            }
        }
        
            # Start crawl
        result = run_scraping_job(job_config)
        
            # Return response
        return {
            'job_id': result['job_id'],
                'status': 'started',
                'estimated_time': f"{request_data.get('max_pages', 100) * 2} seconds",
                'results_url': f'/api/crawl/{result["job_id"]}/results',
                'stats_url': f'/api/crawl/{result["job_id"]}/stats'
            }
        
    # Example API usage
    print("API Endpoint Example:")
    print("-" * 60)
    
    example_request = {
        'url': 'https://otter.ai/blog',
        'max_pages': 200,
        'extract_blog_content': True,
        'follow_patterns': ['/blog/', '/2024/', '/2023/']
    }
    
    response = handle_crawl_request(example_request)
    print(f"Request: POST /api/crawl")
    print(f"Body: {example_request}")
    print(f"Response: {response}")


if __name__ == '__main__':
    import sys

    # example_otter_ai_blog_crawl()  # DEBUG mode enabled for single page parsing!
    example_predictable_output_crawl()
    # example_combined_multi_site_crawl()

    # example_otter_ai_blog_crawl()
    # example_grain_comprehensive_crawl()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == 'otter':
            # Run Otter.ai blog crawl

            job_id = example_otter_ai_blog_crawl()
            print(f"\nTo monitor progress:")
            print(f"  tail -f services/workflow_service/services/scraping/data/{job_id}/items.jsonl | jq .")
            
        elif sys.argv[1] == 'grain':
            # Run Grain.com comprehensive crawl
            job_id = example_grain_comprehensive_crawl()
            print(f"\nTo see results:")
            print(f"  jq '.page_type' services/workflow_service/services/scraping/data/{job_id}/items.jsonl | sort | uniq -c")
            
        elif sys.argv[1] == 'parallel':
            # Show parallel crawl configuration
            example_parallel_large_crawls()
            
        elif sys.argv[1] == 'analyze':
            # Show analysis examples
            example_analyzing_crawl_results()
            
        elif sys.argv[1] == 'api':
            # Show API endpoint example
            example_custom_api_endpoint()
            
        elif sys.argv[1] == 'combined':
            # Run combined multi-site crawl
            job_id = example_combined_multi_site_crawl()
            print(f"\nTo see results:")
            print(f"  jq -r .page_type services/workflow_service/services/scraping/data/{job_id}/items.jsonl | sort | uniq -c")
            
        elif sys.argv[1] == 'predictable':
            # Run predictable output crawl example
            job_id = example_predictable_output_crawl()
            print(f"\nTo see results:")
            print(f"  jq -r .page_type services/workflow_service/services/scraping/data/{job_id}/items.jsonl | sort | uniq -c")
            
        # elif sys.argv[1] == 'subdomain':
        #     # Run subdomain crawl example
        #     job_id = example_subdomain_crawl_with_processor_config()
        #     print(f"\nTo see results by subdomain:")
        #     print(f"  jq -r .url services/workflow_service/services/scraping/data/{job_id}/items.jsonl | cut -d/ -f3 | sort | uniq -c")
            
    # else:
    #     print("Usage:")
    #     print("  python example_usage.py otter     # Run Otter.ai crawl (1000 URLs)")
    #     print("  python example_usage.py grain     # Run Grain.com crawl (1000 URLs)")
    #     print("  python example_usage.py parallel  # Parallel crawl example")
    #     print("  python example_usage.py analyze   # Analysis examples")
    #     print("  python example_usage.py api       # API endpoint example")
    #     print("  python example_usage.py combined  # Combined multi-site crawl example")
    #     print("  python example_usage.py predictable # Predictable output crawl example")
    #     print("  python example_usage.py subdomain # Subdomain crawl with processor config")
    #     print()
    #     print("Examples demonstrate:")
    #     print("- Real-world site crawling (Otter.ai, Grain.com)")
    #     print("- Large-scale configurations (1000 URLs/domain)")
    #     print("- Custom processors for specific sites")
    #     print("- Streaming storage for memory efficiency")
    #     print("- Parallel crawling strategies")
    #     print("- Result analysis techniques") 
