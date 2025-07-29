"""
Generic Spider with Custom Processing Hooks.

This module provides a flexible spider that can be configured via API
with custom processing hooks for domain-specific logic.

## Key Features:

### Processor Configuration
Processors can now be initialized with custom parameters through job configuration:
- `processor_init_params`: Dictionary of parameters passed to processor __init__
- `allowed_domains` is automatically passed from spider configuration
- Useful for domain-specific configuration, API keys, custom behavior, etc.

Example:
```python
job_config = {
    'processor': 'multi_site',
    'allowed_domains': ['example.com', 'another.com'],
    'processor_init_params': {
        # allowed_domains is automatically added from above
        'api_key': 'your_key',
        'custom_param': 'value'
    }
}
```

### Subdomain Support
Enable subdomain crawling with global setting:

```python
'custom_settings': {
    'ALLOW_ALL_SUBDOMAINS_BY_DEFAULT': True
}
```

When enabled, if 'example.com' is in allowed_domains, the spider will also crawl:
- sub.example.com
- deep.sub.example.com
- any.subdomain.example.com

This is particularly useful for crawling sites that use multiple subdomains for
different content types (blog.site.com, support.site.com, docs.site.com, etc).
"""
import asyncio
import re
import uuid
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from typing import Dict, Any, List, Optional, Callable, Type, Set, Union, Tuple
from datetime import datetime
from urllib.parse import urlparse, urljoin, ParseResult
from threading import Lock
import requests

from usp.fetch_parse import XMLSitemapParser
from typing import List, Union
import xml.etree.ElementTree as ET
import feedparser

from scrapy import Spider, Request
from scrapy.http import Response
from scrapy.crawler import CrawlerProcess, CrawlerRunner
from scrapy.utils.project import get_project_settings
from scrapy.linkextractors import LinkExtractor, IGNORED_EXTENSIONS

from global_utils.utils import datetime_now_utc

from prefect.logging.handlers import APILogHandler

# Import special URL parsing libraries
import protego
import feedparser
from usp.tree import sitemap_tree_for_homepage
from usp.web_client.requests_client import RequestsWebClient
from usp.helpers import strip_url_to_homepage
import xml.etree.ElementTree as ET

from workflow_service.services.scraping.settings import scraping_settings, get_queue_key, calculate_priority_from_depth, parse_domain_from_url, get_processed_items_key, get_depth_stats_key, get_domain_limit_key
from workflow_service.services.scraping.redis_sync_client import SyncRedisClient
from workflow_service.services.scraping.utils.feedparse import extract_urls_from_feed
from workflow_service.services.scraping.pipelines import MongoCustomerDataPipeline
from kiwi_app.auth.crud import UserDAO
from linkedin_integration.models import LinkedinUserOauth, LinkedinIntegration, OrgLinkedinAccount

from global_config.logger import get_prefect_or_regular_python_logger
from db.session import get_db_as_manager 

import warnings

warnings.filterwarnings(
    "ignore",
    message=r'.*generator and includes a "return" statement.*',
    category=UserWarning,
    module=r"scrapy\.core\.scraper"
)

# Registry for custom processors
PROCESSOR_REGISTRY: Dict[str, Type['BaseProcessor']] = {}

PROXIES = {"http": scraping_settings.PROXY_URL_EVOMI_ROTATING, "https": scraping_settings.PROXY_URL_EVOMI_ROTATING}

# logger.setLevel(scraping_settings.LOG_LEVEL)

logging.basicConfig(level=scraping_settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

# import ipdb; ipdb.set_trace()

# loggers_to_configure = [
#     'scrapy',
#     'scrapy.core.engine',
#     'scrapy.downloadermiddlewares',
#     'scrapy.spidermiddlewares',
#     'scrapy.extensions',
#     'generic_spider',
#     __name__  # Current module logger
# ]

# for logger_name in loggers_to_configure:
#     logger = logging.getLogger(logger_name)
#     # Avoid adding duplicate handlers
#     logger.setLevel(scraping_settings.LOG_LEVEL)

# root_logger = logging.getLogger()
# logger.setLevel(scraping_settings.LOG_LEVEL)

# import ipdb; ipdb.set_trace()

class RobotsCache:
    """
    Thread-safe cache for robots.txt files by domain/subdomain.
    
    This cache stores parsed robots.txt files for each domain to avoid
    repeated fetching and parsing. It's used to check if URLs can be
    fetched according to robots.txt rules.
    """
    
    def __init__(self, logger=None):
        """Initialize the robots cache with thread safety."""
        self._cache: Dict[str, protego.Protego] = {}
        self._lock = Lock()
        self.logger = logger or logging.getLogger(__name__)
        # User agents to check - we follow if ANY of these are allowed
        self.check_user_agents = ['Googlebot', 'Google-Extended', 'ChatGPT-User']
    
    def get_url_domain(self, url: str, return_parsed: bool = False) -> Union[str, Tuple[ParseResult, str]]:
        """
        Get the domain from a URL.
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if return_parsed:
            return parsed, domain
        return domain
    
    def get_robots_url(self, url: str, scheme: Optional[str] = None) -> Tuple[str, str]:
        """
        Get the robots.txt URL for a given URL's domain.
        """
        parsed, domain = self.get_url_domain(url, return_parsed=True)
        if scheme is None:
            scheme = parsed.scheme
        return domain, f"{scheme}://{domain}/robots.txt"

    def get_robots_no_lock(self, url: str, fetch_if_missing: bool = True) -> Optional[protego.Protego]:
        domain, robots_url = self.get_robots_url(url)
        
        if domain in self._cache:
            return self._cache[domain], False
        
        if not fetch_if_missing:
            return None, False
        
        try:
            self.logger.debug(f"Fetching robots.txt for {domain}")
            response = requests.get(robots_url, timeout=10, allow_redirects=True, proxies=PROXIES)
            
            if response.status_code == 200:
                # Parse robots.txt
                robots = protego.Protego.parse(response.text)
                
                # Cache it
                self._cache[domain] = robots
                    
                self.logger.info(f"Cached robots.txt for {domain}")
                return robots, True
            else:
                self.logger.warning(f"Failed to fetch robots.txt for {domain}: HTTP {response.status_code}")
                # Cache None to avoid repeated failed fetches
                self._cache[domain] = None
                return None, True
                
        except Exception as e:
            self.logger.warning(f"Error fetching robots.txt for {domain}: {e}")
            # Cache None to avoid repeated failed fetches
            self._cache[domain] = None
            return None, True
        
    def get_robots(self, url: str, fetch_if_missing: bool = True) -> Optional[protego.Protego]:
        """
        Get robots.txt for a given URL's domain.
        
        Args:
            url: URL to get robots.txt for
            fetch_if_missing: Whether to fetch robots.txt if not cached
            
        Returns:
            Parsed robots.txt object or None if not found/error
        """
        domain, robots_url = self.get_robots_url(url)
        
        if not domain:
            return None
            
        # Check cache first
        # with self._lock:
        if domain in self._cache:
            return self._cache[domain]
                
        if not fetch_if_missing:
            return None
        
        with self._lock:
            robots, fetched_now = self.get_robots_no_lock(url, fetch_if_missing)
            return robots
            
    def can_fetch(self, url: str) -> bool:
        """
        Check if URL can be fetched according to robots.txt.
        
        Returns True if ANY of the check_user_agents can fetch the URL,
        or if robots.txt doesn't exist/can't be parsed.
        
        Args:
            url: URL to check
            
        Returns:
            True if URL can be fetched, False otherwise
        """
        robots = self.get_robots(url)
        
        if robots is None:
            # No robots.txt or error fetching - allow by default
            return True
            
        # Check if any of our user agents can fetch
        for user_agent in self.check_user_agents:
            if robots.can_fetch(url, user_agent):
                return True
                
        return False
        
    def set_robots(self, url: str, robots_content: str):
        """
        Manually set robots.txt content for a domain.
        
        Used when robots.txt is provided through scraping request.
        
        Args:
            domain: Domain to set robots.txt for
            robots_content: Raw robots.txt content
        """
        domain = self.get_url_domain(url)
        try:
            robots = protego.Protego.parse(robots_content)
            with self._lock:
                self._cache[domain.lower()] = robots
            self.logger.info(f"Manually set robots.txt for {domain}")
        except Exception as e:
            self.logger.error(f"Error parsing robots.txt for {domain}: {e}")
    
    def is_robots_fetched(self, url: str) -> bool:
        """
        Check if robots.txt has been fetched for a given URL.
        """
        domain = self.get_url_domain(url)
        return domain in self._cache
    
    def get_sitemaps(self, url: str) -> List[str]:
        """
        Get sitemap URLs for a given URL's homepage.
        """
        rp = self.get_robots(url)
        if rp is None:
            return []
        return list(rp.sitemaps)
            
    def clear(self):
        """Clear the robots cache."""
        with self._lock:
            self._cache.clear()


class SitemapCache:
    """
    Thread-safe cache for sitemap data by homepage URL.
    
    This cache stores sitemap trees and extracted URLs to avoid
    repeated fetching and parsing of sitemaps.
    """

    SITEMAP_PATTERNS = {
        "sitemap.xml",
        "sitemap.xml.gz",
        "sitemap_index.xml",
        "sitemap-index.xml",
        "sitemap_index.xml.gz",
        "sitemap-index.xml.gz",
        ".sitemap.xml",
        "sitemap",
        "admin/config/search/xmlsitemap",
        "sitemap/sitemap-index.xml",
    }
    
    def __init__(self, logger=None):
        """Initialize the sitemap cache with thread safety."""
        self._cache: Dict[str, Set[str]] = {}  # homepage -> list of URLs
        self._fetched_homepages: set = set()  # Track which homepages we've tried
        self._lock = Lock()
        self.logger = logger or logging.getLogger(__name__)
    
    def get_sitemap_candidate_urls(self, url: str) -> Set[str]:
        """
        Get sitemap URLs for a given URL's homepage.
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        base_urls = []
        for scheme in ['https', 'http']:
            base_urls.append(f"{scheme}://{domain}")
        sitemap_urls = []
        for base_url in base_urls:
            for pattern in self.SITEMAP_PATTERNS:
                sitemap_urls.append(f"{base_url}/{pattern}")
        return set(sitemap_urls)
        
    def get_and_set_sitemap_urls_no_lock(self, url: str, fetch_if_missing: bool = True, homepage: Optional[str] = None) -> Tuple[List[str], bool]:
        """
        Get sitemap URLs for a given URL's homepage and set them in the cache.
        """
        try:
            if homepage is None:
                homepage = strip_url_to_homepage(url)
        except Exception as e:
            self.logger.debug(f"Could not strip URL to homepage: {url} - {e}")
            return [], False

        if homepage in self._cache:
            return self._cache[homepage].copy(), False
            
        # Check if we've already tried this homepage
        if homepage in self._fetched_homepages:
            return [], False
            
        if not fetch_if_missing:
            return [], False
            
        # Mark that we're trying this homepage
        self._fetched_homepages.add(homepage)
            
        # Fetch sitemap
        urls = set()
        try:
            self.logger.debug(f"Fetching sitemap for homepage: {homepage}")
            web_client = RequestsWebClient()
            web_client.set_proxies(PROXIES)
            tree = sitemap_tree_for_homepage(homepage, web_client=web_client)
            
            # Extract all URLs
            for page in tree.all_pages():
                urls.add(page.url)
                    
            # Cache the URLs
            self._cache[homepage] = urls
                
            self.logger.info(f"Cached {len(urls)} URLs from sitemap for {homepage}")
            
        except Exception as e:
            self.logger.warning(f"Error fetching sitemap for {homepage}: {e}")
            # Cache empty list to avoid repeated failed fetches
            self._cache[homepage] = set()
                
        return urls.copy(), True

    def get_sitemap_urls(self, url: str, fetch_if_missing: bool = True) -> List[str]:
        """
        Get sitemap URLs for a given URL's homepage.
        
        Args:
            url: URL to get sitemap for
            fetch_if_missing: Whether to fetch sitemap if not cached
            
        Returns:
            List of URLs from sitemap or empty list
        """
        try:
            homepage = strip_url_to_homepage(url)
        except Exception as e:
            self.logger.debug(f"Could not strip URL to homepage: {url} - {e}")
            return []

        if homepage in self._cache:
            return self._cache[homepage].copy()
            
        # Check cache first
        with self._lock:
            urls, fetched_now = self.get_and_set_sitemap_urls_no_lock(url, fetch_if_missing, homepage)
            return urls
    
    def is_sitemap_fetched(self, url: str) -> bool:
        """
        Check if sitemap URLs have been fetched for a given URL's homepage.
        """
        try:
            homepage = strip_url_to_homepage(url)
        except Exception as e:
            self.logger.debug(f"Could not strip URL to homepage: {url} - {e}")
            return False
        
        return homepage in self._fetched_homepages
        
    def set_sitemap_urls(self, homepage: str, urls: List[str]):
        """
        Manually set sitemap URLs for a homepage.
        
        Args:
            homepage: Homepage URL
            urls: List of URLs from sitemap
        """
        with self._lock:
            self._cache[homepage] = urls.copy()
            self._fetched_homepages.add(homepage)
        self.logger.info(f"Manually set {len(urls)} sitemap URLs for {homepage}")

    def parse_sitemap_content(self, content: str, base_url: str) -> Tuple[List[str], bool]:
        """
        Parse XML sitemap content and return a list of URLs.
        
        This function handles both sitemap index files (which contain references to other sitemaps)
        and regular sitemaps (which contain page URLs).
        
        Args:
            xml_content: Raw XML content of the sitemap
            
        Returns:
            - List of URLs found in the sitemap. These can be:
                - Page URLs (from regular sitemaps)
                - Sitemap URLs (from sitemap index files)
            - Whether this is a sitemap index file (True) or a regular sitemap (False)

        Raises:
            xml.etree.ElementTree.ParseError: If XML content is malformed

        """
        if not content:
            return [], None
        content = content.strip(" \n\t")
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            self.logger.error(f"Failed to parse XML content: {e}")
            return [], None
        
        is_sitemap_index = False
        urls = []

        # Check if this is a sitemap index (contains references to other sitemaps)
        root_tag = root.tag.split("}")[-1]  # Remove namespace if present
        
        if root_tag == "sitemapindex":
            # This is a sitemap index file - extract sitemap URLs
            is_sitemap_index = True
            for sitemap_elem in root:
                for child in sitemap_elem:
                    if "loc" in child.tag:
                        urls.append(child.text)

        else:  # if root_tag == "urlset":
            # This is a regular sitemap - extract page URLs

            parser = XMLSitemapParser(
                    url=base_url,
                    content=content,
                    recursion_level=1,
                    web_client=None,  # RequestsWebClient()  None
                    parent_urls=set(),
                )
            sitemap = parser.sitemap()
            urls = [page.url for page in sitemap.all_pages()]
            
        # else:
        #     logging.warning(f"Unknown sitemap root tag: {root_tag}")
        
        # Filter out None values and empty strings
        urls = [url for url in urls if url and url.strip()]
        
        return urls, is_sitemap_index
        
    def clear(self):
        """Clear the sitemap cache."""
        with self._lock:
            self._cache.clear()
            self._fetched_homepages.clear()


# class PrefectScrapyLogHandler(logging.Handler):
#     """
#     Custom logging handler that redirects Scrapy logs to Prefect's logger.
    
#     This handler intercepts all Scrapy log messages and forwards them to
#     Prefect's run logger, ensuring all logs are captured in the Prefect UI.
#     """
    
#     def __init__(self, prefect_logger=None):
#         super().__init__()
#         self.prefect_logger = prefect_logger
        
#     def emit(self, record):
#         """Forward log records to Prefect logger."""
#         if self.prefect_logger is None:
#             self.prefect_logger = get_prefect_or_regular_python_logger("scrapy")
        
#         # Map Scrapy log levels to Prefect logger methods
#         level_mapping = {
#             logging.DEBUG: self.prefect_logger.debug,
#             logging.INFO: self.prefect_logger.info,
#             logging.WARNING: self.prefect_logger.warning,
#             logging.ERROR: self.prefect_logger.error,
#             logging.CRITICAL: self.prefect_logger.critical,
#         }
        
#         log_func = level_mapping.get(record.levelno, self.prefect_logger.info)
        
#         # Format the message with Scrapy context
#         msg = self.format(record)
#         if record.name.startswith('scrapy'):
#             msg = f"[SCRAPY] {msg}"
            
#         log_func(msg)


class BaseProcessor:
    """
    Base class for domain-specific processors.
    
    Implement custom logic by subclassing and registering.
    
    Processors can accept initialization parameters via job config:
        - allowed_domains: List of allowed domains (automatically passed)
        - Any other custom parameters needed by the processor
        
    Processors can also override special URL handling methods to customize
    how robots.txt, sitemaps, and feeds are processed for specific domains.
    """
    
    def __init__(self, *args, **kwargs):
        """
        Initialize processor with optional parameters.
        
        Args:
            *args: Positional arguments (for compatibility)
            **kwargs: Keyword arguments passed from job config
        """
        # Store any initialization parameters
        self.allowed_domains = kwargs.get('allowed_domains', [])
        # Store all kwargs for subclasses to use
        self.init_params = kwargs
        # Store reference to robots cache if provided
        self.logger = kwargs.get('logger', None)
        self.robots_cache: RobotsCache = kwargs.get('robots_cache', None)
        self.crawl_sitemaps = kwargs.get('crawl_sitemaps', scraping_settings.CRAWL_SITEMAPS)
        self.respect_robots_txt = kwargs.get('respect_robots_txt', scraping_settings.RESPECT_ROBOTS_TXT)
    
    def on_response(self, response: Response, spider: Spider) -> Dict[str, Any]:
        """
        Process response and extract data.
        
        Args:
            response: Scrapy Response object
            spider: Spider instance
            
        Returns:
            Extracted data dictionary
        """
        return {
            'url': response.url,
            'status': response.status,
            'timestamp': datetime_now_utc().isoformat(),
            'content': response.text,
        }
    
    def should_follow_link(self, url: str, response: Response, spider: Spider) -> bool:
        """
        Determine if a link should be followed.
        
        This method now checks robots.txt rules before allowing a link to be followed.
        
        Args:
            url: URL to potentially follow
            response: Current response
            spider: Spider instance
            
        Returns:
            True if link should be followed
        """
        url_domain = parse_domain_from_url(url)
        if not any(domain in url_domain for domain in self.allowed_domains):
            return False
        
        # Check robots.txt if we have a robots cache
        if self.respect_robots_txt and self.robots_cache:
            if not self.robots_cache.can_fetch(url):
                spider.logger.debug(f"URL blocked by robots.txt: {url}")
                return False
        
        if url.endswith(tuple(IGNORED_EXTENSIONS)) and (not url.endswith(url_domain)):
            return False
        
        return True
    
    def should_process_link(self, response: Response, data: Dict[str, Any], spider: Spider) -> bool:
        """
        Determine if a response should be processed and yielded.
        
        This is called AFTER data extraction but BEFORE yielding.
        Use this to filter out low-quality or unwanted content.
        
        Args:
            response: Response object
            data: Extracted data
            spider: Spider instance
            
        Returns:
            True if item should be yielded
        """
        # Check response status
        if response.status >= 400:
            return False
            
        # Check if we have meaningful content
        # Override in subclasses for domain-specific checks
        return True
    
    def transform_data(self, data: Dict[str, Any], response: Response, spider: Spider) -> Dict[str, Any]:
        """
        Transform extracted data before yielding.
        
        Args:
            data: Extracted data
            response: Response object
            spider: Spider instance
            
        Returns:
            Transformed data
        """
        return data
    
    def get_link_priority(self, url: str, depth: int, response: Optional[Response], spider: Optional[Spider], is_start_url: bool = False) -> int:
        """
        Calculate priority for a discovered link.
        
        Args:
            url: Discovered URL
            depth: Current depth
            response: Current response
            spider: Spider instance
            is_start_url: Whether the URL is a start URL

        Returns:
            Priority value (higher = processed sooner)
        """
        
        n_priority = scraping_settings.BASE_PRIORITY if is_start_url else 0
        if (not is_start_url) and spider.settings.get('ENABLE_BLOG_URL_PATTERN_PRIORITY_BOOST', scraping_settings.DEFAULT_ENABLE_BLOG_URL_PATTERN_PRIORITY_BOOST):
            if any(keyword in url for keyword in scraping_settings.BLOG_URL_KEYWORDS):
                n_priority += scraping_settings.BASE_PRIORITY
                # spider.logger.info(f"Boosting priority for blog URL: {url}")
        
        return n_priority + calculate_priority_from_depth(depth)

# Register processors
PROCESSOR_REGISTRY['default'] = BaseProcessor


class GenericSpider(Spider):
    """
    Generic configurable spider for API-driven scraping.
    
    Can be customized via:
    - Custom processors for domain-specific logic
    - Configuration passed at runtime
    - Hooks and callbacks
    """
    
    name = 'generic_spider'
    
    def __init__(self, job_config: Dict[str, Any] = None, *args, **kwargs):
        """
        Initialize spider with job configuration.
        
        Args:
            job_config: Job configuration dict containing:
                - job_id: Unique job identifier
                - start_urls: List of URLs to start crawling
                - allowed_domains: List of allowed domains
                - processor: Processor name or 'default'
                - processor_init_params: Dict of parameters for processor initialization
                - max_urls_per_domain: Domain limit
                - max_crawl_depth: Depth limit
                - custom_settings: Additional Scrapy settings
                - extract_rules: CSS/XPath extraction rules
        """
        super().__init__(*args, **kwargs)
        
        self.job_config = job_config or {}
        self.job_id = self.job_config.get('job_id', f'job_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        
        # Configure spider
        self.start_urls = self.job_config.get('start_urls', [])
        self.allowed_domains = self.job_config.get('allowed_domains', [])

        self.prefect_logger = self.logger  # get_prefect_or_regular_python_logger("scrapy")  # self.logger  #

        configure_logging()
        
        # Initialize caches
        self.robots_cache = RobotsCache(logger=self.prefect_logger)
        self.sitemap_cache = SitemapCache(logger=self.prefect_logger)

        self.respect_robots_txt = self.job_config.get('respect_robots_txt', scraping_settings.RESPECT_ROBOTS_TXT)
        self.crawl_sitemaps = self.job_config.get('crawl_sitemaps', scraping_settings.CRAWL_SITEMAPS)

        if not self.allowed_domains:
            self.allowed_domains = [".".join(parse_domain_from_url(url).split(".")[-2:]) for url in self.start_urls]
        
        # Get processor with optional initialization parameters
        processor_name = self.job_config.get('processor', 'default')
        processor_class = PROCESSOR_REGISTRY.get(processor_name, BaseProcessor)
        
        # Get processor init params from job config
        processor_init_params = self.job_config.get('processor_init_params', {})
        
        # Always pass allowed_domains to processor
        processor_init_params['allowed_domains'] = self.allowed_domains
        # Pass robots cache to processor
        processor_init_params['robots_cache'] = self.robots_cache
        processor_init_params['crawl_sitemaps'] = self.crawl_sitemaps
        processor_init_params['respect_robots_txt'] = self.respect_robots_txt
        processor_init_params['logger'] = self.prefect_logger
        
        # Initialize processor with parameters
        self.processor = processor_class(**processor_init_params)
        
        # Extraction rules
        self.extract_rules = self.job_config.get('extract_rules', {})
        
        # Stats
        self.pages_crawled = 0
        self.items_extracted = 0
        
    @property
    def redis_client(self):
        """
        Get the Redis sync client from the crawler.
        
        The scheduler creates job-specific Redis clients and stores them
        in the crawler for all components to share.
        
        Returns None if clients not available.
        """
        if hasattr(self, 'crawler') and hasattr(self.crawler, '_redis_clients'):
            return self.crawler._redis_clients.get('sync')
        return None

    def _get_robots_requests_for_url(self, url: str, return_args_kwargs: bool = False, depth: int = 0) -> List[Request]:
        """
        Get robots.txt requests for a given URL.
        
        Args:
            url: The URL to get robots.txt requests for
            return_args_kwargs: If True, return (args, kwargs) tuples instead of Request objects
            
        Returns:
            List of Request objects or (args, kwargs) tuples for creating requests
        """
        requests = []
        for scheme in ['https', 'http']:
            domain, robots_url = self.robots_cache.get_robots_url(url, scheme)
            
            # Create args and kwargs for Request instantiation
            args = [robots_url]
            kwargs = {
                'priority': 1000,
                'callback': self.parse,
                'meta': {'is_start_url': True, 'depth': depth, "is_robots": True, "domain": domain}
            }
            
            if return_args_kwargs:
                requests.append((args, kwargs))
            else:
                requests.append(Request(*args, **kwargs))
                
        return requests
    
    def _get_sitemap_request(self, sitemap_url: str, sitemap_urls: Set[str], return_args_kwargs: bool = False, depth: int = 0) -> Request:
        args = [sitemap_url]
        kwargs = {
            'priority': 950,
            'callback': self.parse,
            'meta': {'is_start_url': True, 'depth': depth, "is_sitemap": True, "is_sitemap_candidate": sitemap_url not in sitemap_urls}
        }
        
        if return_args_kwargs:
            return (args, kwargs)
        else:
            return Request(*args, **kwargs)
    
    def _get_sitemap_requests_for_url(self, url: str, sitemap_urls: Union[List[str], Set[str]] = [], return_args_kwargs: bool = False, depth: int = 0) -> List[Request]:
        """
        Get sitemap.xml requests for a given URL.
        
        Args:
            url: The URL to get sitemap requests for
            sitemap_urls: Additional sitemap URLs to include
            return_args_kwargs: If True, return (args, kwargs) tuples instead of Request objects
            
        Returns:
            List of Request objects or (args, kwargs) tuples for creating requests
        """
        requests = []
        sitemap_urls = set(sitemap_urls)
        for sitemap_url in self.sitemap_cache.get_sitemap_candidate_urls(url) | sitemap_urls:
            # Create args and kwargs for Request instantiation
            request = self._get_sitemap_request(sitemap_url, sitemap_urls, return_args_kwargs, depth)
            
            requests.append(request)
                
        return requests
    
    async def start(self):
        # If you still need your old start_requests logic:
        for req in super().start_requests():
            yield req
        
    def start_requests(self):
        """Generate start requests with special flag."""
        # Initialize robots.txt for all allowed domains
        
        # Then generate normal start requests
        all_sitemap_pages = set()
        for url in self.start_urls:
            robots = self.robots_cache.get_robots(url, fetch_if_missing=True)

            domain = parse_domain_from_url(url)

            if self.settings.getint('MAX_CRAWL_DEPTH', 5) > 0 and any(allowed_domain in domain for allowed_domain in self.allowed_domains):
                if self.respect_robots_txt:
                    if not robots:
                        self.crawler.stats.inc_value('scraping_strategy/robots/std/not_found')
                        for request in self._get_robots_requests_for_url(url):
                            yield request
                    else:
                        self.crawler.stats.inc_value('scraping_strategy/robots/std/found')
                
                if self.crawl_sitemaps:
                    sitemap_pages = self.sitemap_cache.get_sitemap_urls(url, fetch_if_missing=True)
                    if not sitemap_pages:
                        self.crawler.stats.inc_value('scraping_strategy/sitemap/std/not_found')
                        sitemap_urls = self.robots_cache.get_sitemaps(url)
                        for request in self._get_sitemap_requests_for_url(url, sitemap_urls):
                            yield request
                    else:
                        self.crawler.stats.inc_value('scraping_strategy/sitemap/std/found')
                        self.crawler.stats.inc_value('scraping_strategy/sitemap/urls_found', len(sitemap_pages))
                        all_sitemap_pages.update(sitemap_pages)

            yield Request(
                url,
                callback=self.parse,
                meta={'is_start_url': True, 'depth': 0},
                priority = self.processor.get_link_priority(url, 0, None, self, is_start_url=True),
                # TODO: FIXME: investigate `dont_filter` argument and ascertain these requests aren't filtered!
            )
        
        if self.crawl_sitemaps:
            for url in all_sitemap_pages:
                yield Request(
                    url,
                    callback=self.parse,
                    meta={'is_start_url': False, 'depth': 0, "from_sitemap": True},
                    priority = self.processor.get_link_priority(url, 0, None, self),
                )
    
    def _check_processed_limit(self, response: Response, domain: str) -> bool:
        """
        Check if we've reached the processed items limit for this domain.
        
        Args:
            response: The response being processed
            domain: The domain of the URL
            
        Returns:
            True if we can process this item, False if limit reached
        """
        max_processed = self.settings.getint('MAX_PROCESSED_URLS_PER_DOMAIN', 0)
        
        # No limit set, always allow
        if max_processed <= 0:
            return True
            
        # Get Redis client from scheduler
        redis_client = self.redis_client
                
        if not redis_client:
            # Fallback: create temporary client (should rarely happen)
            # This only happens when spider is run outside of Scrapy framework
            
            raise Exception("Redis client not found in crawler within generic spider!")
        
            # redis_url = self.settings.get('REDIS_URL')
            # if not redis_url:
            #     return True  # No Redis, can't track limits
                
            # from .redis_sync_client import SyncRedisClient
            # temp_client = SyncRedisClient(redis_url)
            # try:
            #     return self._do_processed_limit_check(temp_client, domain, max_processed)
            # finally:
            #     # Important: close temporary client to avoid connection leaks
            #     temp_client.close()
        else:
            return self._do_processed_limit_check(redis_client, domain, max_processed)
            
    def _do_processed_limit_check(self, redis_client: SyncRedisClient, domain: str, max_processed: int) -> bool:
        """
        Perform the actual processed limit check using the provided Redis client.
        
        This method uses the thread-safe increment_counter_with_limit which performs
        optimistic increments and rolls back if the limit would be exceeded.
        
        Args:
            redis_client: The Redis client to use
            domain: The domain to check
            max_processed: The maximum allowed processed items
            
        Returns:
            True if we can process, False if over limit
        """
        # Get the key based on strategy
        queue_strategy = self.settings.get('REDIS_QUEUE_KEY_STRATEGY', 'spider')
        processed_key = get_processed_items_key(
            self.name, domain, self.job_id, queue_strategy
        )
        
        # Try to increment - will be rolled back if exceeds limit
        count, is_over = redis_client.increment_counter_with_limit(
            processed_key,
            increment=1,
            limit=max_processed,
            ttl=7 * 86400  # 7 days
        )
        
        if is_over:
            # Either at limit or increment was rolled back
            self.prefect_logger.debug(
                f"Item filtered by processed limit ({domain}: {count}/{max_processed})"
            )
            
            if hasattr(self, 'crawler') and self.crawler.stats:
                self.crawler.stats.inc_value('items/filtered/processed_limit')
                
            return False
            
        return True


    def _is_domain_over_url_limit(self, domain: str) -> tuple[int, bool]:
        """
        Check if a domain has reached its processed items limit.
        
        This is used for early stopping - no point in crawling URLs from domains
        that have already reached their processed item quota.
        
        Args:
            domain: Domain to check
            
        Returns:
            Tuple of (remaining, is_over_limit)
        """
        # If no processed limit is set, never over limit
        limit = self.settings.getint('MAX_URLS_PER_DOMAIN', 0)
        if limit <= 0:
            return (1000, False)
            
        # Get the processed items key
        queue_strategy = self.settings.get('REDIS_QUEUE_KEY_STRATEGY', 'spider')
        limit_key = get_domain_limit_key(
            self.name, domain, self.job_id, queue_strategy,
        )
        
        # Get current count (don't increment, just check)
        current_count = self.redis_client.get_counter_value(limit_key)
        
        # Check if over limit
        is_over = current_count >= limit
        remaining = limit - current_count
        
        if is_over:
            self.prefect_logger.debug(
                f"Domain {domain} has reached URL limit: "
                f"{current_count}/{limit}"
            )
            
        return (remaining, is_over)
    
    def parse(self, response: Response):
        """Main parsing method."""
        self.pages_crawled += 1
        depth = response.meta.get('depth', 0)
        is_start_url = response.meta.get('is_start_url', False)
        is_robots = response.meta.get('is_robots', False)
        is_sitemap = response.meta.get('is_sitemap', False)
        is_sitemap_candidate = response.meta.get('is_sitemap_candidate', False)
        from_sitemap = response.meta.get('from_sitemap', False)
        
        self.prefect_logger.debug(
            f"[JOB {self.job_id}] Crawled {self.pages_crawled}: {response.url} "
            f"(depth: {depth})"
        )

        could_be_sitemap = "sitemap" in response.url and (response.url.endswith(".xml") or response.url.endswith(".xml.gz"))
        
        url_domain = parse_domain_from_url(response.url)
        
        # Process response with custom processor
        sitemap_pages = []

        robots_requests = []
        sitemap_requests = []

        all_next_urls = set()
        
        try:

            if is_robots:
                if response.status < 400:
                    self.crawler.stats.inc_value('scraping_strategy/robots/scraped/success')
                    self.robots_cache.set_robots(response.url, response.text)
                    robots_sitemap_urls = self.robots_cache.get_sitemaps(response.url)
                    robots_sitemap_urls = set(robots_sitemap_urls)
                    for sitemap_url in robots_sitemap_urls:
                        if sitemap_url != response.url:
                            args, kwargs = self._get_sitemap_request(sitemap_url, robots_sitemap_urls, return_args_kwargs=True, depth=depth)
                            sitemap_requests.append((args, kwargs))
                            # yield response.follow(*args, **kwargs)
                    all_next_urls.update(robots_sitemap_urls)
                else:
                    self.crawler.stats.inc_value('scraping_strategy/robots/scraped/failed')
                    self.prefect_logger.warning(f"Failed to fetch robots.txt for {response.url}: {response.status}")
            
            elif is_sitemap or could_be_sitemap:
                if response.status < 400:
                    sitemap_pages_or_urls, is_sitemap_index = self.sitemap_cache.parse_sitemap_content(response.text, response.url)
                    
                    if sitemap_pages_or_urls:
                        if is_sitemap_candidate:
                            self.crawler.stats.inc_value('scraping_strategy/sitemap/scraped/success/candidate_found')
                        self.crawler.stats.inc_value('scraping_strategy/sitemap/scraped/success')
                    else:
                        fail_suffix = ""
                        if response.status >= 300:
                            fail_suffix = f"/3XX"
                        if is_sitemap_candidate:
                            self.crawler.stats.inc_value(f'scraping_strategy/sitemap/scraped/failed/candidate_not_found{fail_suffix}')
                        self.crawler.stats.inc_value(f'scraping_strategy/sitemap/scraped/failed{fail_suffix}')
                    
                    if is_sitemap_index:
                        self.crawler.stats.inc_value('scraping_strategy/sitemap/scraped/success/index_found')
                        sitemap_pages_or_urls = set(sitemap_pages_or_urls)
                        for sitemap_url in sitemap_pages_or_urls:
                            if sitemap_url != response.url:
                                args, kwargs = self._get_sitemap_request(sitemap_url, sitemap_pages_or_urls, return_args_kwargs=True, depth=depth)
                                sitemap_requests.append((args, kwargs))
                                # yield response.follow(*args, **kwargs)
                        all_next_urls.update(sitemap_pages_or_urls)
                    else:
                        feed_urls = extract_urls_from_feed(response.text, flatten_results=True)
                        if len(sitemap_pages_or_urls):
                            self.crawler.stats.inc_value('scraping_strategy/sitemap/scraped/urls_found', len(sitemap_pages_or_urls))
                        sitemap_pages = list(set(sitemap_pages_or_urls) | feed_urls)
                        all_next_urls.update(sitemap_pages)
                else:
                    self.crawler.stats.inc_value('scraping_strategy/sitemap/scraped/failed')
                    if is_sitemap_candidate:
                        self.crawler.stats.inc_value('scraping_strategy/sitemap/scraped/failed/candidate_not_found')
                    self.prefect_logger.warning(f"Failed to fetch sitemap.xml {'(candidate)' if is_sitemap_candidate else ''} for {response.url}: {response.status}")
                
            if (not (is_robots or is_sitemap)) and self.settings.getint('MAX_CRAWL_DEPTH', 5) > 0 and any(allowed_domain in url_domain for allowed_domain in self.allowed_domains):
                url = response.url
                robots_sitemap_urls = []
                if (not self.robots_cache.is_robots_fetched(url)) and self.respect_robots_txt:
                    with self.robots_cache._lock:
                        robots, fetched_now = self.robots_cache.get_robots_no_lock(url, fetch_if_missing=True)
                    if fetched_now:
                        robots_sitemap_urls = self.robots_cache.get_sitemaps(url)

                        if not robots:
                            self.crawler.stats.inc_value('scraping_strategy/robots/std/not_found')
                            for args, kwargs in self._get_robots_requests_for_url(url, return_args_kwargs=True, depth=depth):
                                robots_requests.append((args, kwargs))
                                # yield response.follow(*args, **kwargs)
                
                if not self.sitemap_cache.is_sitemap_fetched(url) and self.crawl_sitemaps:
                    with self.sitemap_cache._lock:
                        sitemap_urls, fetched_now = self.sitemap_cache.get_and_set_sitemap_urls_no_lock(url, fetch_if_missing=True)
                    if fetched_now:
                        sitemap_pages = self.sitemap_cache.get_sitemap_urls(url)

                        if not sitemap_pages:
                            self.crawler.stats.inc_value('scraping_strategy/sitemap/std/not_found')
                            
                            for args, kwargs in self._get_sitemap_requests_for_url(url, robots_sitemap_urls, return_args_kwargs=True, depth=depth):
                                sitemap_requests.append((args, kwargs))
                                # yield response.follow(*args, **kwargs)
                            all_next_urls.update(robots_sitemap_urls)
                        else:
                            self.crawler.stats.inc_value('scraping_strategy/sitemap/std/urls_found', len(sitemap_pages))
                            self.crawler.stats.inc_value('scraping_strategy/sitemap/std/found')

            if not (is_robots or is_sitemap):
                # NOTE: if we want to process / scrape the robots / sitemap directly, we add them in the starter urls set 
                #     and for those, is_robots and is_sitemap flags won't be set! These flags are just set for discovery 
                #     of the website and we don't want to further process those requests!
            
                data = self.processor.on_response(response, self)
                
                # Apply custom extraction rules
                if self.extract_rules:
                    data.update(self._apply_extraction_rules(response))
                
                # Transform data
                data = self.processor.transform_data(data, response, self)
                
                # Check if we should process this item
                if self.processor.should_process_link(response, data, self):
                    # Check processed items limit
                    domain = parse_domain_from_url(response.url)
                    if self._check_processed_limit(response, domain):
                        # Add metadata
                        data['_job_id'] = self.job_id
                        data['_spider'] = self.name
                        data['_crawled_at'] = datetime_now_utc().isoformat()
                        data['_depth'] = depth
                        
                        # Yield item
                        self.items_extracted += 1

                        if self.settings.getbool('DEBUG_MODE', False):
                            
                            discovered_urls = self._discover_urls(response) if not (is_robots or is_sitemap) else []
                            processed_urls = set()
                            for url_list, from_sitemap in [(sitemap_pages, True), (discovered_urls, False)]:
                                for url in url_list:
                                    if self.processor.should_follow_link(url, response, self):
                                        all_next_urls.add(url)

                            data['_all_next_urls'] = list(all_next_urls)

                        yield data
                else:
                    self.prefect_logger.debug(f"Item filtered by should_process_link: {response.url}")
                    if hasattr(self, 'crawler') and self.crawler.stats:
                        self.crawler.stats.inc_value('items/filtered/should_process')
                
        except Exception as e:
            self.prefect_logger.error(f"Error processing {response.url}: {e}", exc_info=True)
            yield {
                'url': response.url,
                'error': str(e),
                '_job_id': self.job_id,
                '_spider': self.name,
                '_crawled_at': datetime_now_utc().isoformat()
            }
        
        # Discover and follow links

        if depth <= self.settings.getint('MAX_CRAWL_DEPTH', 5):
            for args, kwargs in sitemap_requests:
                yield response.follow(*args, **kwargs)

            for args, kwargs in robots_requests:
                yield response.follow(*args, **kwargs)
        
        if depth < self.settings.getint('MAX_CRAWL_DEPTH', 5):
            # NOTE: We already processed the is_robts / is_sitemaps for urls to follow, no need to process them again!
            discovered_urls = self._discover_urls(response) if not (is_robots or is_sitemap) else []

            if not self.crawl_sitemaps:
                sitemap_pages = []
            
            processed_urls = set()
            next_requests = []
            for url_list, from_sitemap in [(sitemap_pages, True), (discovered_urls, False)]:
                for url in url_list:
                    if self.processor.should_follow_link(url, response, self):
                        priority = self.processor.get_link_priority(url, depth + 1, response, self)
                        if url not in processed_urls:
                            processed_urls.add(url)
                            args = [url]
                            kwargs = {
                                'callback': self.parse,
                                'priority': priority,
                                'meta': {'depth': depth + 1, 'from_sitemap': from_sitemap}
                            }
                            next_requests.append((args, kwargs))
            
            # self.crawler.engine._slot.scheduler._do
            
            domain_cache = {}
            for args, kwargs in sorted(next_requests, key=lambda x: x[1]['priority'], reverse=True):
                url = args[0]
                domain = parse_domain_from_url(url)
                if domain not in domain_cache:
                    domain_cache[domain] = list(self._is_domain_over_url_limit(domain))
                if domain_cache[domain][1] and domain_cache[domain][0] <= 0:
                    limit = self.settings.getint('MAX_URLS_PER_DOMAIN', 0)
                    self.prefect_logger.debug(f"Domain {domain} has reached URL limit: {domain_cache[domain][0]}/{limit}")
                    continue
                domain_cache[domain][0] -= 1
                yield response.follow(*args, **kwargs)
    
    def _discover_urls(self, response: Response) -> List[str]:
        """Discover URLs from response.
        
        This method extracts URLs from:
        1. Regular HTML links (<a> tags)
        2. JavaScript code
        3. Special files (robots.txt, sitemaps, feeds) via _parse_special_urls
        4. Automatically fetches sitemaps for new domains/subdomains
        
        TODO: FIXME: remove URLS like: mailto:hello@grain.com (leads to value error in scrapy from response lib!)
        """
        urls = set()
        
        # First, check if this response is a special URL that needs custom parsing
        feed_urls = extract_urls_from_feed(response.text, flatten_results=True)
        urls.update(feed_urls)
        
        # special_urls = self._parse_special_urls(response)
        # urls.update(special_urls)
        
        # Extract all regular HTML links
        for link in response.css('a::attr(href)').getall():
            if link:
                # Filter out invalid URLs that cause Scrapy errors
                if not any(link.startswith(prefix) for prefix in ['mailto:', 'tel:', 'javascript:', '#']):
                    absolute_url = response.urljoin(link)
                    urls.add(absolute_url)
        
        # # Also check for URLs in JavaScript (common in SPAs)
        # js_url_patterns = [
        #     r'["\']/([\w\-/]+)["\']',  # Relative paths
        #     r'https?://[^\s"\')]+',     # Absolute URLs
        # ]
        
        # for script in response.css('script::text').getall():
        #     for pattern in js_url_patterns:
                
        #         for match in re.finditer(pattern, script):
        #             url = match.group(0).strip('"\'')
        #             if url.startswith('/'):
        #                 url = response.urljoin(url)
        #             if url.startswith('http'):
        #                 urls.add(url)
        
        # Extract all link URLs without filtering - domain restrictions handle the filtering
        # Get all href attributes from link tags (canonical, alternate, etc.)
        for link in response.css('link::attr(href)').getall():
            if link and not any(link.startswith(prefix) for prefix in ['mailto:', 'tel:', 'javascript:', '#']):
                absolute_url = response.urljoin(link)
                urls.add(absolute_url)
        
        # Look for special file references in the HTML content that might not be linked
        # Combined regex pattern for efficiency - finds robots.txt, sitemaps, feeds, etc.
        # Simple pattern without complex lookaheads for better compatibility
        special_files_pattern = r'["\'/](robots\.txt|sitemap[^"\'\s]*\.xml|feed\.(?:xml|json)|rss\.xml|atom\.xml)'
        
        # Search in page content for special file references
        for match in re.finditer(special_files_pattern, response.text):
            potential_url = response.urljoin(match.group(1))
            urls.add(potential_url)
        
        # # Automatically check for sitemap URLs for this domain
        # # This ensures we discover all URLs from sitemaps for each domain/subdomain
        # if self.sitemap_cache:
        #     sitemap_urls = self.sitemap_cache.get_sitemap_urls(response.url, fetch_if_missing=True)
        #     if sitemap_urls:
        #         self.prefect_logger.debug(f"Adding {len(sitemap_urls)} URLs from sitemap for {response.url}")
        #         urls.update(sitemap_urls)
        
        return list(urls)
    
    # def _parse_special_urls(self, response: Response) -> List[str]:
    #     """
    #     Parse special URLs like robots.txt, sitemap.xml, RSS/Atom feeds to discover more URLs.
        
    #     This method detects the type of special URL based on patterns and uses appropriate
    #     parsers to extract additional URLs:
    #     - robots.txt: Uses protego library to parse robots file
    #     - sitemap.xml: Uses ultimate-sitemap-parser to extract URLs from sitemaps
    #     - RSS/Atom/JSON feeds: Uses feedparser to extract links from feeds
        
    #     This method also handles manually seeded content that was provided in the job config
    #     and retrieved through advanced anti-bot scraping.
        
    #     Args:
    #         response: The response object containing the special URL content
            
    #     Returns:
    #         List of discovered URLs from parsing special files
    #     """
    #     return []
    
    def _apply_extraction_rules(self, response: Response) -> Dict[str, Any]:
        """Apply custom extraction rules."""
        extracted = {}
        
        for field, rule in self.extract_rules.items():
            try:
                if isinstance(rule, dict):
                    selector_type = rule.get('type', 'css')
                    selector = rule.get('selector')
                    extract = rule.get('extract', 'text')
                    
                    if selector_type == 'css':
                        elements = response.css(selector)
                    elif selector_type == 'xpath':
                        elements = response.xpath(selector)
                    else:
                        continue
                    
                    if extract == 'text':
                        values = elements.getall()
                    elif extract == 'href':
                        values = elements.css('::attr(href)').getall()
                    elif extract.startswith('attr:'):
                        attr_name = extract.split(':', 1)[1]
                        values = elements.css(f'::attr({attr_name})').getall()
                    else:
                        values = elements.getall()
                    
                    # Single value or list
                    if rule.get('multiple', False):
                        extracted[field] = values
                    else:
                        extracted[field] = values[0] if values else None
                        
            except Exception as e:
                self.prefect_logger.warning(f"Failed to extract {field}: {e}")
        
        return extracted
    
    def closed(self, reason):
        """Called when spider closes."""
        # self.stats_data = self.crawler.stats.get_stats()
        self.prefect_logger.info(
            f"Spider closed: {reason}. "
            f"Pages: {self.pages_crawled}, Items: {self.items_extracted}"
        )


def configure_logging():
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(scraping_settings.LOG_LEVEL)
    
    # Set level for all existing loggers
    for name in logging.root.manager.loggerDict:
        logging.getLogger(name).setLevel(scraping_settings.LOG_LEVEL)
    
    # Specifically target known noisy loggers
    noisy_loggers = [
        'httpcore', 'httpcore.connection', 'httpcore.http11',
        'urllib3', 'urllib3.connectionpool',
        'scrapy', 'scrapy.core.engine',
        'httpx', 'generic_spider', 'usp', 'usp.helpers', 'usp.fetch_parse',
        'workflow_service',
        'scrapy.downloadermiddlewares',
        'scrapy.spidermiddlewares',
        'scrapy.extensions',
        'scrapy.core.engine',
        'scrapy.core.scraper',
        "scrapy.utils.log",
        __name__  # Current module logger
    ]
    
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(scraping_settings.LOG_LEVEL)


def run_scraping_job(job_config: Dict[str, Any], use_prefect_logging: bool = False) -> Dict[str, Any]:
    """
    Run a scraping job with the given configuration.
    
    Args:
        job_config: Job configuration dictionary
        
    Returns:
        Job execution results
    """
    # APILogHandler
    # # Configure Scrapy logging
    debug_mode_enabled = job_config.get('debug_mode', False)
    log_level = job_config.get('log_level', 'INFO' if not debug_mode_enabled else 'DEBUG')

    logger.info(f"\n\n\n\n SETTING SCRAPY LOG LEVEL: {log_level}\n\n\n\n")
    log_level = logging.DEBUG if log_level.lower() == 'debug' else (logging.INFO if log_level.lower() == 'info' else logging.WARNING)
    logger.info(f"\n\n\n\n SETTING SCRAPY LOG LEVEL: {log_level}\n\n\n\n")
    
    # # Set up rotating file handler for logging
    # # Get the directory where spider.py is located
    # current_dir = os.path.dirname(os.path.abspath(__file__))
    # logs_dir = os.path.join(current_dir, 'logs')
    
    # # Create logs directory if it doesn't exist
    # os.makedirs(logs_dir, exist_ok=True)
    
    # # Create log filename with job_id and timestamp
    # job_id = job_config.get('job_id', f'job_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
    # log_filename = os.path.join(logs_dir, f'scraping_{job_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
    # # Set up rotating file handler
    # # maxBytes: 10MB, backupCount: 5 (keeps 5 old log files)
    # file_handler = RotatingFileHandler(
    #     filename=log_filename,
    #     maxBytes=10 * 1024 * 1024,  # 10MB
    #     backupCount=5,
    #     encoding='utf-8'
    # )
    
    # # Set formatter for file handler
    # formatter = logging.Formatter(
    #     '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    #     datefmt='%Y-%m-%d %H:%M:%S'
    # )
    # file_handler.setFormatter(formatter)
    # file_handler.setLevel(getattr(logging, log_level))
    
    # # Add file handler to relevant loggers
    # loggers_to_configure = [
    #     'scrapy',
    #     'scrapy.core.engine',
    #     'scrapy.downloadermiddlewares',
    #     'scrapy.spidermiddlewares',
    #     'scrapy.extensions',
    #     'generic_spider',
    #     __name__  # Current module logger
    # ]
    
    # for logger_name in loggers_to_configure:
    #     logger = logging.getLogger(logger_name)
    #     # Avoid adding duplicate handlers
    #     if not any(isinstance(h, RotatingFileHandler) and h.baseFilename == log_filename for h in logger.handlers):
    #         logger.addHandler(file_handler)
    #         logger.setLevel(getattr(logging, log_level))
    
    # # Log the start of the job
    # logging.getLogger(__name__).info(f"Starting scraping job {job_id}, logging to: {log_filename}")
    
    # if use_prefect_logging:
    #     # for handler in logging.root.handlers:
    #     #     handler.addFilter(ContentFilter())
    #     # Disable default Scrapy logging configuration
    #     # configure_logging(install_root_handler=False)
    #     # settings.set('LOG_ENABLED', True)
        
    #     # Add our custom Prefect handler to root logger
    #     level = logging.INFO if log_level == 'INFO' else logging.DEBUG
    #     root_logger = logging.getLogger()
    #     root_logger.addHandler(APILogHandler(level=level))
    #     scrapy_logger = logging.getLogger('scrapy')
    #     scrapy_logger.addHandler(APILogHandler(level=level))
    #     generic_spider_logger = logging.getLogger('generic_spider')
    #     generic_spider_logger.addHandler(APILogHandler(level=level))
        
    #     # Remove existing handlers to avoid duplicate logs
    #     for handler in scrapy_logger.handlers[:]:
    #         scrapy_logger.removeHandler(handler)
        
    #     # Add Prefect handler
    #     prefect_handler = PrefectScrapyLogHandler(logger)
    #     prefect_handler.setFormatter(
    #         logging.Formatter('%(name)s - %(levelname)s - %(message)s')
    #     )
    #     scrapy_logger.addHandler(prefect_handler)
    #     scrapy_logger.setLevel(getattr(logging, job_config.get('log_level', 'INFO')))
        
    #     # Also add to specific Scrapy component loggers
    #     for component in ['scrapy.core.engine', 'scrapy.downloadermiddlewares', 
    #                     'scrapy.spidermiddlewares', 'scrapy.extensions']:
    #         component_logger = logging.getLogger(component)
    #         component_logger.addHandler(prefect_handler)
    #         component_logger.setLevel(getattr(logging, job_config.get('log_level', 'INFO')))
        
    #     logger.info("Scrapy logging redirected to Prefect")
    # else:
    #     # Use default Scrapy logging
    #     settings.set('LOG_LEVEL', job_config.get('log_level', 'INFO'))
    #     logger.info("Using default Scrapy logging")



    # Prepare settings
    settings = get_project_settings()
    
    # Apply Redis configuration

    settings.set('start_urls', job_config.get('start_urls', []))
    logger.info(f"START_URLS: {settings.get('start_urls')}")
    
    settings.set('SCHEDULER', 'services.workflow_service.services.scraping.scrapy_redis_integration.RedisScheduler')
    settings.set('REDIS_URL', job_config.get('redis_url', scraping_settings.REDIS_URL))
    settings.set('USE_IN_MEMORY_QUEUE', job_config.get('use_in_memory', scraping_settings.USE_IN_MEMORY_QUEUE))
    settings.set('REDIS_QUEUE_KEY_STRATEGY', 'job')
    settings.set('SCRAPY_JOB_ID', job_config['job_id'])
    settings.set('DEBUG_MODE', debug_mode_enabled)
    settings.set('LOG_LEVEL', log_level)
    # Fix scrapy GZIP errors
    settings.set('COMPRESSION_ENABLED', False)
    # Apply job-specific settings
    
    # DEBUG
    settings.set('CONCURRENT_ITEMS', job_config.get('concurrent_items', 200))

    settings.set('MAX_URLS_PER_DOMAIN', job_config.get('max_urls_per_domain', scraping_settings.DEFAULT_MAX_URLS_PER_DOMAIN))
    settings.set('MAX_PROCESSED_URLS_PER_DOMAIN', job_config.get('max_processed_urls_per_domain', scraping_settings.DEFAULT_MAX_PROCESSED_URLS_PER_DOMAIN))
    
    logger.info(f"MAX_URLS_PER_DOMAIN: {settings.get('MAX_URLS_PER_DOMAIN')}")
    logger.info(f"MAX_PROCESSED_URLS_PER_DOMAIN: {settings.get('MAX_PROCESSED_URLS_PER_DOMAIN')}")

    settings.set('MAX_CRAWL_DEPTH', job_config.get('max_crawl_depth', scraping_settings.DEFAULT_MAX_CRAWL_DEPTH))
    concurrent_requests_per_domain = job_config.get('concurrent_requests_per_domain', 10)
    settings.set('CONCURRENT_REQUESTS_PER_DOMAIN', concurrent_requests_per_domain)
    
    # DEBUG
    settings.set('CONCURRENT_REQUESTS', job_config.get('concurrent_requests', concurrent_requests_per_domain))

    settings.set('CRAWL_SITEMAPS', job_config.get('crawl_sitemaps', scraping_settings.CRAWL_SITEMAPS))
    settings.set('RESPECT_ROBOTS_TXT', job_config.get('respect_robots_txt', scraping_settings.RESPECT_ROBOTS_TXT))
    settings.set('ENABLE_BLOG_URL_PATTERN_PRIORITY_BOOST', job_config.get('enable_blog_url_pattern_priority_boost', scraping_settings.DEFAULT_ENABLE_BLOG_URL_PATTERN_PRIORITY_BOOST))
    
    # Configure download handler with browser pool support
    settings.set('DOWNLOAD_HANDLERS', {
        'http': 'services.workflow_service.services.scraping.scrapy_redis_integration.TieredDownloadHandler',
        'https': 'services.workflow_service.services.scraping.scrapy_redis_integration.TieredDownloadHandler',
    })
    
    # Configure browser pool settings
    settings.set('BROWSER_POOL_ENABLED', job_config.get('browser_pool_enabled', scraping_settings.BROWSER_POOL_ENABLED))
    settings.set('BROWSER_POOL_SIZE', job_config.get('browser_pool_size', scraping_settings.BROWSER_POOL_SIZE))
    settings.set('BROWSER_POOL_LOCAL_CONCURRENCY_LIMIT', job_config.get('browser_pool_local_concurrency_limit', scraping_settings.BROWSER_POOL_LOCAL_CONCURRENCY_LIMIT))
    settings.set('BROWSER_POOL_TIMEOUT', job_config.get('browser_pool_timeout', scraping_settings.BROWSER_POOL_TIMEOUT))
    settings.set('BROWSER_POOL_INTERCEPT_MEDIA', job_config.get('browser_pool_intercept_media', scraping_settings.BROWSER_POOL_INTERCEPT_MEDIA))
    settings.set('BROWSER_POOL_INTERCEPT_IMAGES', job_config.get('browser_pool_intercept_images', scraping_settings.BROWSER_POOL_INTERCEPT_IMAGES))
    settings.set('BROWSER_POOL_PROXY_COUNTRY', job_config.get('browser_pool_proxy_country', scraping_settings.BROWSER_POOL_PROXY_COUNTRY))
    settings.set('BROWSER_POOL_MAX_FALLBACKS_PER_JOB', job_config.get('browser_pool_max_fallbacks_per_job', scraping_settings.BROWSER_POOL_MAX_FALLBACKS_PER_JOB))
    
    # Proxy tier settings
    settings.set('PROXY_TIER_ENABLED', job_config.get('proxy_tier_enabled', scraping_settings.PROXY_TIER_ENABLED))
    settings.set('PROXY_TIER_MAX_FALLBACKS_PER_JOB', job_config.get('proxy_tier_max_fallbacks_per_job', scraping_settings.PROXY_TIER_MAX_FALLBACKS_PER_JOB))

    settings.set('MONGO_PIPELINE_ENABLED', job_config.get('mongo_pipeline_enabled', scraping_settings.MONGO_PIPELINE_ENABLED))

    logger.info(f"MONGO_PIPELINE_ENABLED: {settings.get('MONGO_PIPELINE_ENABLED')}")
    
    user = job_config.get('user', None)
    if isinstance(user, (str, uuid.UUID)):
        with get_db_as_manager() as db:
            user = UserDAO().get_by_id_sync(db, uuid.UUID(user) if isinstance(user, str) else user)

    settings.set('user', user)
    settings.set('org_id', job_config.get('org_id', None))
    settings.set('is_shared', job_config.get('is_shared', False))

    date_str = job_config.get('date_str', datetime.now().strftime('%Y%m%d'))
    settings.set('date_str', date_str)

    # start_urls_uuid = MongoCustomerDataPipeline._generate_start_urls_uuid(job_config.get('start_urls', []))
    # settings.set('start_urls_uuid', start_urls_uuid)

    # MongoCustomerDataPipeline._generate_namespace_static()

    # Apply custom settings
    custom_settings = job_config.get('custom_settings', {})
    for key, value in custom_settings.items():
        settings.set(key, value)
    
    # Don't persist queue after job
    settings.set('SCHEDULER_PERSIST', False)
    settings.set('SCHEDULER_PURGE_ON_CLOSE', True)
    
    # Create process
    process = CrawlerProcess(settings)
    # process = CrawlerRunner(settings)
    
    # Run spider
    # spider_instance = GenericSpider()
    crawler = process.create_crawler(GenericSpider)
    process.crawl(crawler, job_config=job_config)
    process.start()

    stats = crawler.stats.get_stats()

    namespaces = {}
    for key, value in stats.items():
        if key.startswith('scraping_results/namespace/'):
            namespace = key[len('scraping_results/namespace/'):]
            namespaces[namespace] = value
        # del stats[key]

    # get_db_as_manager
    
    # Log completion
    logging.getLogger(__name__).info(f"Scraping job {job_config['job_id']} completed successfully")

    # Return job stats
    return {
        'job_id': job_config['job_id'],
        'status': 'completed',
        'completed_at': datetime_now_utc().isoformat(),
        'stats': stats,
        "result_namespaces": namespaces,
        # 'log_file': log_filename,  # Include log file path in results
    }

def push_urls_to_redis(
    spider_name: str,
    urls: List[str],
    redis_client: SyncRedisClient = None,
    redis_url: str = None,
    job_id: str = None,
    queue_key_strategy: str = 'spider',
    max_urls_per_domain: int = 0,
    max_crawl_depth: int = 5,
    initial_depth: int = 0,
    use_in_memory: bool = None
) -> Dict[str, Any]:
    """
    Push URLs to Redis queue for processing.
    
    Args:
        spider_name: Name of the spider
        urls: List of URLs to push
        redis_client: Optional Redis client to use (job-specific)
        redis_url: Redis connection URL (only used if client not provided)
        job_id: Optional job ID for queue isolation
        queue_key_strategy: 'spider' or 'job' strategy
        max_urls_per_domain: Max URLs per domain (0 = no limit)
        max_crawl_depth: Maximum crawl depth
        initial_depth: Initial depth for URLs
        use_in_memory: If True, use in-memory storage instead of Redis
        
    Returns:
        Statistics about the push operation
    """
    # Use provided client or create temporary one
    own_client = False
    if not redis_client:
        redis_url = redis_url or scraping_settings.REDIS_URL
        if use_in_memory is None:
            use_in_memory = scraping_settings.USE_IN_MEMORY_QUEUE
        redis_client = SyncRedisClient(redis_url, use_in_memory=use_in_memory)
        own_client = True
    
    # Get queue key
    queue_key = get_queue_key(spider_name, job_id, queue_key_strategy)
    
    stats = {
        'spider_name': spider_name,
        'job_id': job_id,
        'queue_key': queue_key,
        'urls_provided': len(urls),
        'urls_pushed': 0,
        'duplicates': 0,
        'domain_distribution': {}
    }
    
    try:
        for url in urls:
            # Create request data
            request_data = {
                'url': url,
                'method': 'GET',
                'meta': {'depth': initial_depth},
                'priority': calculate_priority_from_depth(initial_depth),
                'dont_filter': False
            }
            
            # Push to queue
            if redis_client.push_request(queue_key, request_data, priority=request_data['priority']):
                stats['urls_pushed'] += 1
                
                # Track domain distribution
                
                domain = parse_domain_from_url(url)
                stats['domain_distribution'][domain] = stats['domain_distribution'].get(domain, 0) + 1
            else:
                stats['duplicates'] += 1
                
    except Exception as e:
        logging.error(f"Error pushing URLs to Redis: {e}")
        raise
    finally:
        # Only close if we created the client
        if own_client:
            redis_client.close()
    
    return stats


def get_spider_stats(
    spider_name: str, 
    job_id: str = None, 
    redis_client: SyncRedisClient = None,
    redis_url: str = None,
    use_in_memory: bool = None
) -> Dict[str, Any]:
    """
    Get statistics for a spider/job.
    
    Args:
        spider_name: Spider name
        job_id: Optional job ID
        redis_client: Optional Redis client to use (job-specific)
        redis_url: Redis URL (only used if client not provided)
        use_in_memory: If True, use in-memory storage instead of Redis
        
    Returns:
        Spider/job statistics
    """
    # Use provided client or create temporary one
    own_client = False
    if not redis_client:
        redis_url = redis_url or scraping_settings.REDIS_URL
        if use_in_memory is None:
            use_in_memory = scraping_settings.USE_IN_MEMORY_QUEUE
        redis_client = SyncRedisClient(redis_url, use_in_memory=use_in_memory)
        own_client = True
    
    stats = {
        'spider_name': spider_name,
        'job_id': job_id,
        'queue_stats': {},
        'domain_stats': {},
        'depth_distribution': {},
        'total_urls_crawled': 0,
        'domains_crawled': 0
    }
    
    try:
        # Get queue stats
        queue_key = get_queue_key(spider_name, job_id, 'job' if job_id else 'spider')
        stats['queue_stats'] = redis_client.get_queue_stats(queue_key)
        
        # Get domain stats (simplified - would need to track keys properly)
        depth_key = get_depth_stats_key(spider_name)
        stats['depth_distribution'] = redis_client.get_hash_counter_values(depth_key)
        
        # Calculate totals
        stats['total_urls_crawled'] = sum(stats['depth_distribution'].values())
        stats['domains_crawled'] = len(stats['domain_stats'])
        
    except Exception as e:
        
        logging.error(f"Error getting spider stats: {e}")
        # Return partial stats on error
        pass
    finally:
        # Only close if we created the client
        if own_client:
            redis_client.close()
    
    return stats


