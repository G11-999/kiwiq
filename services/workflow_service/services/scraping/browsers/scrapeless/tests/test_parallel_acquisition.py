#!/usr/bin/env python
"""
Test script to verify parallel browser acquisition works correctly.

This script tests that multiple browsers can be acquired simultaneously
without serialization due to lock contention.
"""

import asyncio
import time
import logging
from typing import List, Dict

from workflow_service.services.scraping.browsers.scrapeless.scrapeless_browser import (
    ScrapelessBrowserPool,
    cleanup_scrapeless_redis_pool
)
from workflow_service.services.scraping.settings import scraping_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def acquire_browser_with_timing(pool: ScrapelessBrowserPool, browser_id: int) -> Dict:
    """
    Acquire a browser and measure the time taken.
    
    Args:
        pool: The browser pool to acquire from
        browser_id: ID for logging purposes
        
    Returns:
        Dictionary with browser data and timing information
    """
    start_time = time.time()
    logger.info(f"Browser {browser_id}: Starting acquisition...")
    
    try:
        browser_data = await pool.acquire_browser()
        acquisition_time = time.time() - start_time
        
        if browser_data:
            logger.info(f"✅ Browser {browser_id}: Acquired successfully in {acquisition_time:.2f}s")
            return {
                'browser_id': browser_id,
                'browser_data': browser_data,
                'acquisition_time': acquisition_time,
                'success': True
            }
        else:
            logger.error(f"❌ Browser {browser_id}: Failed to acquire after {acquisition_time:.2f}s")
            return {
                'browser_id': browser_id,
                'browser_data': None,
                'acquisition_time': acquisition_time,
                'success': False
            }
            
    except Exception as e:
        acquisition_time = time.time() - start_time
        logger.error(f"❌ Browser {browser_id}: Exception during acquisition after {acquisition_time:.2f}s: {e}")
        return {
            'browser_id': browser_id,
            'browser_data': None,
            'acquisition_time': acquisition_time,
            'success': False,
            'error': str(e)
        }


async def test_parallel_acquisition(num_browsers: int = 5):
    """
    Test that multiple browsers can be acquired in parallel.
    
    Args:
        num_browsers: Number of browsers to acquire simultaneously
    """
    logger.info("=" * 80)
    logger.info(f"🧪 Testing Parallel Browser Acquisition ({num_browsers} browsers)")
    logger.info("=" * 80)
    
    # Cleanup Redis pool first
    logger.info("🧹 Cleaning up Redis pool...")
    await cleanup_scrapeless_redis_pool()
    
    # Create browser pool
    pool = ScrapelessBrowserPool(
        max_concurrent=100,  # Global limit
        max_concurrent_local=num_browsers,  # Local limit
        enable_keep_alive=False,
        use_profiles=False,
        acquisition_timeout=30
    )
    
    # Get initial pool status
    initial_status = await pool.get_pool_status()
    logger.info(f"Initial pool status: {initial_status}")
    
    try:
        # Create tasks to acquire browsers simultaneously
        logger.info(f"\n⏳ Starting parallel acquisition of {num_browsers} browsers...")
        start_time = time.time()
        
        # Launch all acquisition tasks at once
        tasks = [
            acquire_browser_with_timing(pool, i+1) 
            for i in range(num_browsers)
        ]
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks)
        
        total_time = time.time() - start_time
        
        # Analyze results
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]
        
        logger.info(f"\n📊 Results Summary:")
        logger.info(f"  - Total time: {total_time:.2f}s")
        logger.info(f"  - Successful acquisitions: {len(successful)}/{num_browsers}")
        logger.info(f"  - Failed acquisitions: {len(failed)}/{num_browsers}")
        
        if successful:
            avg_time = sum(r['acquisition_time'] for r in successful) / len(successful)
            max_time = max(r['acquisition_time'] for r in successful)
            min_time = min(r['acquisition_time'] for r in successful)
            
            logger.info(f"  - Average acquisition time: {avg_time:.2f}s")
            logger.info(f"  - Min acquisition time: {min_time:.2f}s")
            logger.info(f"  - Max acquisition time: {max_time:.2f}s")
            
            # Check if acquisitions were truly parallel
            # If they were serial, total_time would be close to sum of individual times
            sum_of_times = sum(r['acquisition_time'] for r in successful)
            parallelism_ratio = sum_of_times / total_time
            
            logger.info(f"  - Parallelism ratio: {parallelism_ratio:.2f}x")
            logger.info(f"    (Higher is better; 1x means serial, {num_browsers}x means perfect parallelism)")
            
            if parallelism_ratio < 1.5:
                logger.warning("⚠️  Low parallelism detected! Acquisitions appear to be serialized.")
            else:
                logger.info("✅ Good parallelism achieved!")
        
        # Get final pool status
        final_status = await pool.get_pool_status()
        logger.info(f"\nFinal pool status: {final_status}")
        
        # Test cleanup
        logger.info(f"\n🧹 Cleaning up browsers...")
        for result in successful:
            await pool.release_browser(result['browser_data'])
        
        # Verify cleanup
        cleanup_status = await pool.get_pool_status()
        logger.info(f"Status after cleanup: {cleanup_status}")
        
        if cleanup_status['active_browsers'] == 0 and cleanup_status['local_active_count'] == 0:
            logger.info("✅ All browsers cleaned up successfully!")
        else:
            logger.warning("⚠️  Some browsers may not have been cleaned up properly")
        
    except Exception as e:
        logger.error(f"Test failed with exception: {e}", exc_info=True)
    finally:
        # Final cleanup
        await pool.cleanup_all_browsers()
        await cleanup_scrapeless_redis_pool()
        logger.info("🏁 Test completed")


async def main():
    """Main function to run the parallel acquisition test."""
    # Test with different numbers of browsers
    test_configs = [
        {'num_browsers': 3, 'description': 'Small parallel test'},
        {'num_browsers': 5, 'description': 'Medium parallel test'},
        {'num_browsers': 9, 'description': 'Large parallel test'},
    ]
    
    for config in test_configs:
        logger.info(f"\n\n{'='*80}")
        logger.info(f"Running: {config['description']}")
        logger.info(f"{'='*80}")
        await test_parallel_acquisition(config['num_browsers'])
        await asyncio.sleep(2)  # Brief pause between tests


if __name__ == "__main__":
    asyncio.run(main()) 