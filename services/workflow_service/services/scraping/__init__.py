"""
Scraping service module for workflow_service.

This module provides web scraping capabilities with:
- Redis-based queue management
- Domain and depth limiting
- Job isolation
- Priority-based crawling
"""

from .settings import scraping_settings
from .spider import (
    GenericSpider, BaseProcessor, PROCESSOR_REGISTRY,
    run_scraping_job, push_urls_to_redis, get_spider_stats
)
from .scrapy_redis_integration import RedisScheduler, TieredDownloadHandler

__all__ = [
    'scraping_settings',
    'GenericSpider',
    'BaseProcessor',
    'PROCESSOR_REGISTRY',
    'run_scraping_job',
    'push_urls_to_redis',
    'get_spider_stats',
    'RedisScheduler',
    'TieredDownloadHandler',
] 