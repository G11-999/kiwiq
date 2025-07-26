#!/usr/bin/env python
"""
Manual cleanup script for Scrapeless browser Redis pool.

This script can be used to force cleanup the Redis pool when it's in a corrupted state.

Usage:
    python cleanup_redis_pool.py
"""

import asyncio
import logging
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """
    Main function to perform Redis pool cleanup.
    """
    try:
        # Import the cleanup function
        from workflow_service.services.scraping.browsers.scrapeless.scrapeless_browser import (
            cleanup_scrapeless_redis_pool,
            ScrapelessBrowserPool
        )
        from redis_client.redis_client import AsyncRedisClient
        from global_config.settings import global_settings
        from workflow_service.services.scraping.settings import scraping_settings   
        
        logger.info("=" * 80)
        logger.info("🧹 Scrapeless Browser Redis Pool Cleanup Tool")
        logger.info("=" * 80)
        
        # Get pool status before cleanup
        redis_client = AsyncRedisClient(global_settings.REDIS_URL)
        pool_key = scraping_settings.SCRAPELESS_BROWSERS_POOL_KEY
        
        logger.info(f"📊 Getting pool status before cleanup...")
        try:
            pool_info = await redis_client.get_pool_info(pool_key)
            logger.info(f"Current pool status:")
            logger.info(f"  - Current usage: {pool_info.get('current_usage', 'N/A')}")
            logger.info(f"  - Max size: {pool_info.get('max_size', 'N/A')}")
            logger.info(f"  - Active allocations: {pool_info.get('active_allocations', 'N/A')}")
            logger.info(f"  - Available: {pool_info.get('available', 'N/A')}")
        except Exception as e:
            logger.warning(f"Could not get pool info: {e}")
        
        # Perform cleanup
        logger.info(f"\n🔧 Performing force cleanup of Redis pool...")
        success = await cleanup_scrapeless_redis_pool()
        
        if success:
            logger.info("✅ Redis pool cleanup completed successfully!")
            
            # Check pool status after cleanup
            logger.info(f"\n📊 Getting pool status after cleanup...")
            try:
                pool_info = await redis_client.get_pool_info(pool_key)
                logger.info(f"Pool status after cleanup:")
                logger.info(f"  - Current usage: {pool_info.get('current_usage', 'N/A')}")
                logger.info(f"  - Max size: {pool_info.get('max_size', 'N/A')}")
                logger.info(f"  - Active allocations: {pool_info.get('active_allocations', 'N/A')}")
                logger.info(f"  - Available: {pool_info.get('available', 'N/A')}")
            except Exception as e:
                logger.info(f"Pool has been reset (no data found, which is expected)")
        else:
            logger.error("❌ Redis pool cleanup failed!")
            
    except Exception as e:
        logger.error(f"Error during cleanup: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code) 