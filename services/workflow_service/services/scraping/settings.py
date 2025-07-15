"""
Centralized settings and key management for the scraping service.

This module provides configuration settings, Redis key patterns, and key construction
methods for the scraping service components.
"""

from typing import Optional, Dict, Any
from functools import lru_cache
from global_config.settings import global_settings
from workflow_service.config.settings import settings as workflow_settings


class ScrapingSettings:
    """
    Settings specific to the scraping service.
    
    This class centralizes all configuration, key patterns, and key construction
    methods used by the scraping components.
    """
    
    # Redis configuration
    REDIS_URL: str = workflow_settings.REDIS_URL or global_settings.REDIS_URL
    
    # Queue key patterns
    QUEUE_KEY_PATTERN_SPIDER = "queue:{spider}:requests"
    QUEUE_KEY_PATTERN_JOB = "queue:{spider}:{job}:requests"
    
    # Dupefilter key pattern (appended to queue key)
    DUPEFILTER_SUFFIX = "dupefilter"
    
    # Job state patterns
    JOB_STATE_PATTERN = "job_state:{key}"
    
    # Domain limit patterns
    DOMAIN_LIMIT_PATTERN_SPIDER = "domain_limit:{spider}:{domain}"
    DOMAIN_LIMIT_PATTERN_JOB = "domain_limit:{spider}:{job}:{domain}"
    
    # Processed items patterns (tracks actually yielded items)
    PROCESSED_ITEMS_PATTERN_SPIDER = "processed_items:{spider}:{domain}"
    PROCESSED_ITEMS_PATTERN_JOB = "processed_items:{spider}:{job}:{domain}"
    
    # Depth tracking patterns
    DEPTH_STATS_PATTERN_SPIDER = "depth_stats:{spider}"
    DEPTH_STATS_PATTERN_JOB = "depth_stats:{spider}:{job}"
    
    # Default limits
    DEFAULT_MAX_URLS_PER_DOMAIN = 1000
    DEFAULT_MAX_PROCESSED_URLS_PER_DOMAIN = 500  # Default limit for actually processed items
    DEFAULT_MAX_CRAWL_DEPTH = 10
    DEFAULT_DUPEFILTER_TTL = 7 * 86400  # 7 days
    
    # Priority calculation
    BASE_PRIORITY = 100
    PRIORITY_DECAY_PER_DEPTH = 10  # Reduce priority by 10 for each depth level
    
    # Body handling settings
    DEFAULT_SKIP_BODY_FOR_GET = True  # Skip storing body for GET requests
    DEFAULT_COMPRESS_BODY_THRESHOLD = 1024  # Compress bodies larger than 1KB
    
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
            return cls.QUEUE_KEY_PATTERN_JOB.format(spider=spider_name, job=job_id)
        return cls.QUEUE_KEY_PATTERN_SPIDER.format(spider=spider_name)
    
    @classmethod
    def get_dupefilter_key(cls, queue_key: str) -> str:
        """
        Generate dupefilter key from queue key.
        
        Args:
            queue_key: The queue key
            
        Returns:
            Dupefilter key
        """
        return f"{queue_key}:{cls.DUPEFILTER_SUFFIX}"
    
    @classmethod
    def get_job_state_key(cls, key: str) -> str:
        """
        Generate job state key.
        
        Args:
            key: The job identifier
            
        Returns:
            Job state key
        """
        return cls.JOB_STATE_PATTERN.format(key=key)
    
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
        if strategy == 'job' and job_id:
            return cls.DOMAIN_LIMIT_PATTERN_JOB.format(
                spider=spider_name, job=job_id, domain=domain
            )
        return cls.DOMAIN_LIMIT_PATTERN_SPIDER.format(
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
        if strategy == 'job' and job_id:
            return cls.PROCESSED_ITEMS_PATTERN_JOB.format(
                spider=spider_name, job=job_id, domain=domain
            )
        return cls.PROCESSED_ITEMS_PATTERN_SPIDER.format(
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
            return cls.DEPTH_STATS_PATTERN_JOB.format(spider=spider_name, job=job_id)
        return cls.DEPTH_STATS_PATTERN_SPIDER.format(spider=spider_name)
    
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
            base_priority = cls.BASE_PRIORITY
            
        # Reduce priority as depth increases
        priority = base_priority - (depth * cls.PRIORITY_DECAY_PER_DEPTH)
        
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
            ]
        else:
            # Spider-level patterns
            return [
                f"queue:{spider_name}:*",
                f"job_state:{spider_name}*",
                f"domain_limit:{spider_name}:*",
                f"processed_items:{spider_name}:*",
                f"depth_stats:{spider_name}*",
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