"""
Centralized settings and key management for the scraping service.

This module provides configuration settings, Redis key patterns, and key construction
methods for the scraping service components.
"""

from typing import Optional, Dict, Any
from functools import lru_cache
from global_config.settings import global_settings, Settings
from workflow_service.config.settings import settings as workflow_settings


class ScrapingSettings(Settings):
    """
    Settings specific to the scraping service.
    
    This class centralizes all configuration, key patterns, and key construction
    methods used by the scraping components.
    """

    SCRAPELESS_API_KEY: str = ""
    BROWSERBASE_API_KEY: str = ""
    PROXY_URL_EVOMI_ROTATING: str = ""
    SCRAPELESS_BROWSERS_POOL_KEY: str = "scrapeless_browsers_pool"
    # In-memory vs Redis storage
    USE_IN_MEMORY_QUEUE: bool = True  # Use in-memory storage instead of Redis (suitable for single-process deployments)

    # Browser Pool Configuration for backup scraping strategy
    BROWSER_POOL_ENABLED: bool = False  # Enable browser pool as backup scraping strategy
    BROWSER_POOL_SIZE: int = 5  # Maximum number of browsers to maintain in pool
    BROWSER_POOL_LOCAL_CONCURRENCY_LIMIT: int = 5  # Local concurrency limit for browser pool operations
    BROWSER_POOL_TIMEOUT: int = 30  # Timeout in seconds for browser acquisition
    BROWSER_POOL_SESSION_TTL: int = 900  # Session TTL in seconds (15 minutes)
    BROWSER_POOL_PERSIST_PROFILE: bool = False  # Whether to persist browser profiles
    BROWSER_POOL_INTERCEPT_MEDIA: bool = True  # Block media resources to save bandwidth
    BROWSER_POOL_INTERCEPT_IMAGES: bool = True  # Block image resources to save bandwidth
    BROWSER_POOL_PROXY_COUNTRY: str = "US"  # Default proxy country for browsers
    
    # Browser pool fallback limits
    BROWSER_POOL_MAX_FALLBACKS_PER_JOB: int = 10  # Maximum browser fallbacks allowed per job (expensive operation)
    BROWSER_POOL_FALLBACK_COUNTER_KEY_PATTERN: str = "browser_fallback_count:{spider}:{job}"  # Key pattern for tracking fallback usage
    
    # Proxy tier fallback limits
    PROXY_TIER_ENABLED: bool = True  # Enable proxy tier as backup scraping strategy
    PROXY_TIER_MAX_FALLBACKS_PER_JOB: int = 100  # Maximum proxy tier fallbacks allowed per job (moderate cost)
    PROXY_TIER_FALLBACK_COUNTER_KEY_PATTERN: str = "proxy_fallback_count:{spider}:{job}"  # Key pattern for tracking proxy tier usage
    MONGO_PIPELINE_ENABLED: bool = True  # Enable MongoDB pipeline for storing scraped data
    
    # Blocked URL tracking configuration
    MAX_BLOCKED_URL_EXAMPLES: int = 10  # Maximum number of example URLs to store per trigger type
    
    # HTTP status codes that should trigger browser pool fallback
    BROWSER_POOL_TRIGGER_CODES: list[int] = [
        401,  # Unauthorized
        403,  # Forbidden
        407,  # Proxy Authentication Required
        429,  # Too Many Requests
        503,  # Service Unavailable
        511,  # Network Authentication Required
        520,  # Cloudflare: Web Server Returns Unknown Error
        521,  # Cloudflare: Web Server Is Down
        522,  # Cloudflare: Connection Timed Out
        523,  # Cloudflare: Origin Is Unreachable
        524,  # Cloudflare: A Timeout Occurred
    ]
    
    # Content patterns that indicate anti-bot measures (case-insensitive)
    BROWSER_POOL_TRIGGER_PATTERNS: list[str] = [
        # Cloudflare specific
        # "cloudflare",
        "cf-browser-verification",
        "ray id",  # Cloudflare Ray ID
        "just a moment",  # Cloudflare's signature phrase
        "checking your browser",
        
        # CAPTCHA variants
        "captcha",
        "recaptcha",
        "hcaptcha",
        "i'm not a robot",
        "i am not a robot",
        
        # Generic bot detection
        "access denied",
        "access to this page",
        # "blocked",
        "bot detection",
        "unusual traffic",
        "suspicious activity",
        
        # Challenge/verification
        # "challenge",
        # "verification",
        "please verify",
        "verify you are human",
        "verify you are a human",
        "security check",
        
        # DDoS protection
        "ddos protection",
        "ddos-guard",
        "under attack mode",
        
        # JavaScript requirements
        "javascript is disabled",
        "javascript is required",
        "enable javascript",
        # "noscript",
    ]
    
    # Redis configuration
    # REDIS_URL: str = workflow_settings.REDIS_URL or global_settings.REDIS_URL
    
    # Queue key patterns
    QUEUE_KEY_PATTERN_SPIDER: str  = "queue:{spider}:requests"
    QUEUE_KEY_PATTERN_JOB: str  = "queue:{spider}:{job}:requests"
    
    # Dupefilter key pattern (appended to queue key)
    DUPEFILTER_SUFFIX: str = "dupefilter"
    
    # Job state patterns
    JOB_STATE_PATTERN: str = "job_state:{key}"
    
    # Domain limit patterns
    DOMAIN_LIMIT_PATTERN_SPIDER: str = "domain_limit:{spider}:{domain}"
    DOMAIN_LIMIT_PATTERN_JOB: str = "domain_limit:{spider}:{job}:{domain}"
    
    # Processed items patterns (tracks actually yielded items)
    PROCESSED_ITEMS_PATTERN_SPIDER: str = "processed_items:{spider}:{domain}"
    PROCESSED_ITEMS_PATTERN_JOB: str = "processed_items:{spider}:{job}:{domain}"
    
    # Depth tracking patterns
    DEPTH_STATS_PATTERN_SPIDER: str = "depth_stats:{spider}"
    DEPTH_STATS_PATTERN_JOB: str = "depth_stats:{spider}:{job}"
    CRAWL_SITEMAPS: bool = True
    RESPECT_ROBOTS_TXT: bool = True
    
    # Default limits
    DEFAULT_MAX_URLS_PER_DOMAIN: int = 1000
    DEFAULT_MAX_PROCESSED_URLS_PER_DOMAIN: int = 500  # Default limit for actually processed items
    DEFAULT_MAX_CRAWL_DEPTH: int = 4
    DEFAULT_DUPEFILTER_TTL: int = 7 * 86400  # 7 days

    LIMIT_DOMAINS_BY_SUBDOMAIN_INSTEAD_OF_BASE_DOMAIN: bool = False
    
    # Technical SEO analysis
    # When enabled, the spider will compute per-page technical SEO metrics and dates
    PERFORM_TECHNICAL_SEO: bool = False
    # Optional: number of sample internal/external links to include in analysis output
    TECHNICAL_SEO_LINK_SAMPLE_SIZE: int = 10
    DISABLE_HTML_DUMP_IN_DATA: bool = True

    # Priority calculation
    BASE_PRIORITY: int = 100
    PRIORITY_DECAY_PER_DEPTH: int = 10  # Reduce priority by 10 for each depth level
    DEFAULT_ENABLE_BLOG_URL_PATTERN_PRIORITY_BOOST: bool = True

    BLOG_URL_KEYWORDS: list[str] = [
        'blog',
        'new',
        'article',
        'post',
        'story',
        'update',
        'press',
        'post',
        'feed',
        'knowledge',
        'learn',
        'insight',
        'resource',
        'guide',
        'tutorial',
        'walkthrough',
        'tech',
        "customer",
        "stories",
        "story",
        "case",
        "use",
        "study",
        "success",
        "update",
        "press",
        "post",
        "feed",
        "knowledge",
        "learn",
        "engineer",
        "developer",
        "strateg",
        "report",
        "research",
        "product",
        'how',
        "best",
        "practice",
        "tips",
        "tactic",
        "industry",
        "whitepaper",
        "book",
    ]
    
    # Body handling settings
    DEFAULT_SKIP_BODY_FOR_GET: bool = True  # Skip storing body for GET requests
    DEFAULT_COMPRESS_BODY_THRESHOLD: int = 1024  # Compress bodies larger than 1KB
    
    # Billing configuration
    AI_ANSWER_ENGINE_PRICE_PER_QUERY: float = 0.035  # 3.5 cents per query (any provider)
    CRAWLER_SCRAPER_PRICE_PER_URL: float = 0.003  # 1 cent / 5 URLs = 0.2 cents per URL
    CLEANUP_SCRAPELESS_REDIS_POOL_ON_STARTUP: bool = False

    # Blog classifier configuration
    # Default OpenAI model used for the blog classifier. Must support structured output.
    CLASSIFY_PAGES_AS_BLOG: bool = True
    BLOG_CLASSIFIER_MODEL: str = "gpt-5-mini"
    # Maximum number of characters from the `cleaned_markdown_content` field to consider during classification
    BLOG_CLASSIFIER_MAX_CONTENT_LENGTH: int = 15000
    
    @classmethod
    def get_queue_key(cls, spider_name: str, job_id: Optional[str] = None, 
                      strategy: str = 'spider') -> str:
        """
        Generate queue key based on strategy.
        
        Args:
            spider_name: Name of the spider
            job_id: Optional job ID for job-specific queues
            strategy: 'spider' (shared) or 'job' (isolated)
            
        Returns:
            Formatted queue key
        """
        if strategy == 'job' and job_id:
            return scraping_settings.QUEUE_KEY_PATTERN_JOB.format(spider=spider_name, job=job_id)
        return scraping_settings.QUEUE_KEY_PATTERN_SPIDER.format(spider=spider_name)
    
    @classmethod
    def get_dupefilter_key(cls, queue_key: str) -> str:
        """
        Generate dupefilter key from queue key.
        
        Args:
            queue_key: The queue key
            
        Returns:
            Dupefilter key
        """
        return f"{queue_key}:{scraping_settings.DUPEFILTER_SUFFIX}"
    
    @classmethod
    def get_job_state_key(cls, key: str) -> str:
        """
        Generate job state key.
        
        Args:
            key: The job identifier
            
        Returns:
            Job state key
        """
        return scraping_settings.JOB_STATE_PATTERN.format(key=key)
    
    @classmethod
    def get_domain_limit_key(cls, spider_name: str, domain: str, 
                            job_id: Optional[str] = None,
                            strategy: str = 'spider') -> str:
        """
        Generate domain limit tracking key.
        
        Args:
            spider_name: Name of the spider
            domain: Domain to track
            job_id: Optional job ID for job-specific tracking
            strategy: 'spider' or 'job'
            
        Returns:
            Domain limit key
        """
        if not scraping_settings.LIMIT_DOMAINS_BY_SUBDOMAIN_INSTEAD_OF_BASE_DOMAIN:
            domain = ".".join(domain.split(".")[-2:])
        if strategy == 'job' and job_id:
            return scraping_settings.DOMAIN_LIMIT_PATTERN_JOB.format(
                spider=spider_name, job=job_id, domain=domain
            )
        return scraping_settings.DOMAIN_LIMIT_PATTERN_SPIDER.format(
            spider=spider_name, domain=domain
        )
    
    @classmethod
    def get_processed_items_key(cls, spider_name: str, domain: str, 
                               job_id: Optional[str] = None,
                               strategy: str = 'spider') -> str:
        """
        Generate processed items tracking key.
        
        Args:
            spider_name: Name of the spider
            domain: Domain to track
            job_id: Optional job ID for job-specific tracking
            strategy: 'spider' or 'job'
            
        Returns:
            Processed items key
        """
        if not scraping_settings.LIMIT_DOMAINS_BY_SUBDOMAIN_INSTEAD_OF_BASE_DOMAIN:
            domain = ".".join(domain.split(".")[-2:])
        if strategy == 'job' and job_id:
            return scraping_settings.PROCESSED_ITEMS_PATTERN_JOB.format(
                spider=spider_name, job=job_id, domain=domain
            )
        return scraping_settings.PROCESSED_ITEMS_PATTERN_SPIDER.format(
            spider=spider_name, domain=domain
        )
    
    @classmethod
    def get_depth_stats_key(cls, spider_name: str, job_id: Optional[str] = None,
                           strategy: str = 'spider') -> str:
        """
        Generate depth statistics tracking key.
        
        Args:
            spider_name: Name of the spider
            job_id: Optional job ID for job-specific tracking
            strategy: 'spider' or 'job'
            
        Returns:
            Depth stats key
        """
        if strategy == 'job' and job_id:
            return scraping_settings.DEPTH_STATS_PATTERN_JOB.format(spider=spider_name, job=job_id)
        return scraping_settings.DEPTH_STATS_PATTERN_SPIDER.format(spider=spider_name)
    
    @classmethod
    def calculate_priority_from_depth(cls, depth: int, base_priority: Optional[int] = None) -> int:
        """
        Calculate request priority based on depth.
        Lower depth = higher priority (processed first).
        
        Args:
            depth: Current crawl depth
            base_priority: Optional base priority to start from
            
        Returns:
            Calculated priority (higher number = higher priority)
        """
        if base_priority is None:
            base_priority = scraping_settings.BASE_PRIORITY
            
        # Reduce priority as depth increases
        priority = base_priority - (depth * scraping_settings.PRIORITY_DECAY_PER_DEPTH)
        
        # Ensure priority doesn't go below 1
        return max(1, priority)
    
    @classmethod
    def get_purge_patterns(cls, spider_name: str, job_id: Optional[str] = None) -> list[str]:
        """
        Get all Redis key patterns that should be purged for a spider/job.
        
        Args:
            spider_name: Name of the spider
            job_id: Optional job ID for job-specific purging
            
        Returns:
            List of key patterns to purge
        """
        if job_id:
            # Job-specific patterns
            return [
                f"queue:{spider_name}:{job_id}:*",
                f"queue:{spider_name}:requests:{job_id}",
                f"job_state:{spider_name}:{job_id}*",
                f"domain_limit:{spider_name}:{job_id}:*",
                f"processed_items:{spider_name}:{job_id}:*",
                f"depth_stats:{spider_name}:{job_id}",
                f"browser_fallback_count:{spider_name}:{job_id}",  # Browser fallback counter
                f"proxy_fallback_count:{spider_name}:{job_id}",  # Proxy tier fallback counter
            ]
        else:
            # Spider-level patterns
            return [
                f"queue:{spider_name}:*",
                f"job_state:{spider_name}*",
                f"domain_limit:{spider_name}:*",
                f"processed_items:{spider_name}:*",
                f"depth_stats:{spider_name}*",
                f"browser_fallback_count:{spider_name}:*",  # Browser fallback counters
                f"proxy_fallback_count:{spider_name}:*",  # Proxy tier fallback counters
            ]
    
    @classmethod
    def parse_domain_from_url(cls, url: str) -> str:
        """
        Extract domain from URL for domain limiting.
        
        Args:
            url: The URL to parse
            
        Returns:
            Domain string (without port)
        """
        from urllib.parse import urlparse
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        
        # Handle authentication in URL (user:pass@domain)
        if '@' in netloc:
            # Split off the auth part
            netloc = netloc.split('@', 1)[1]
        
        # Handle IPv6 addresses (enclosed in brackets)
        if netloc.startswith('[') and ']' in netloc:
            # IPv6 address - extract everything up to and including the closing bracket
            bracket_end = netloc.index(']') + 1
            # Check if there's a port after the bracket
            if bracket_end < len(netloc) and netloc[bracket_end] == ':':
                # Remove port
                return netloc[:bracket_end]
            return netloc
        
        # For regular domains, remove port if present
        if ':' in netloc:
            netloc = netloc.split(':')[0]
        return netloc


# Create a singleton instance
scraping_settings = ScrapingSettings()


# Export commonly used methods at module level for convenience
get_queue_key = ScrapingSettings.get_queue_key
get_dupefilter_key = ScrapingSettings.get_dupefilter_key
get_job_state_key = ScrapingSettings.get_job_state_key
get_domain_limit_key = ScrapingSettings.get_domain_limit_key
get_processed_items_key = ScrapingSettings.get_processed_items_key
get_depth_stats_key = ScrapingSettings.get_depth_stats_key
calculate_priority_from_depth = ScrapingSettings.calculate_priority_from_depth
get_purge_patterns = ScrapingSettings.get_purge_patterns
parse_domain_from_url = ScrapingSettings.parse_domain_from_url

# print(scraping_settings.REDIS_URL)
