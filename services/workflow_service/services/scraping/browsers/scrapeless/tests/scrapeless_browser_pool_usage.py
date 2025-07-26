#!/usr/bin/env python3
"""
ScrapelessBrowserPool Usage Examples

This file demonstrates how to use the ScrapelessBrowserPool for managing
Scrapeless browser instances with Redis-based concurrency control and
in-memory browser pooling.

Key Features Demonstrated:
1. Basic browser pool usage with automatic cleanup
2. Keep-alive pool mode for browser reuse
3. Individual browser context managers
4. Manual resource management
5. Pool status monitoring
6. Error handling and timeouts
7. TTL expiration handling
8. Force close mechanism for error recovery
9. Local concurrency limiting
"""

import asyncio
import logging
from typing import Optional
import random

# Configure logging to see pool operations
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from workflow_service.services.scraping.browsers.scrapeless.scrapeless_browser import (
    ScrapelessBrowserPool, 
    ScrapelessBrowserContextManager,
    ScrapelessBrowser
)
from redis_client.redis_client import AsyncRedisClient


async def example_basic_pool_usage():
    """
    Example 1: Basic browser pool usage with automatic cleanup.
    
    This shows the simplest way to use the pool where browsers are
    created and destroyed as needed without keep-alive behavior.
    """
    print("\n=== Example 1: Basic Pool Usage ===")
    
    # Create a browser pool with default settings
    pool = ScrapelessBrowserPool(
        max_concurrent=5,  # Lower limit for demo
        acquisition_timeout=10,
        browser_ttl=300  # 5 minutes TTL
    )
    
    try:
        # Acquire a browser directly from the pool
        browser_data = await pool.acquire_browser()
        if browser_data:
            browser = browser_data['browser']
            print(f"Acquired browser: {browser_data['session_id']}")
            
            # Use the browser for some work
            await browser.page.goto("https://example.com")
            print(f"Navigated to: {await browser.page.title()}")
            
            # Release the browser (will be closed since keep-alive is False)
            await pool.release_browser(browser_data)
            print("Browser released and closed")
        else:
            print("Failed to acquire browser")
    
    except Exception as e:
        print(f"Error in basic usage: {e}")
    
    finally:
        # Clean up any remaining browsers
        cleaned = await pool.cleanup_all_browsers()
        print(f"Cleaned up {cleaned} browsers")


async def example_keep_alive_pool():
    """
    Example 2: Keep-alive pool mode for browser reuse.
    
    This shows how to use the pool context manager to enable
    keep-alive behavior, allowing browsers to be reused efficiently.
    """
    print("\n=== Example 2: Keep-Alive Pool Mode ===")
    
    # Use pool as async context manager to enable keep-alive
    async with ScrapelessBrowserPool(
        max_concurrent=3,
        acquisition_timeout=15,
        browser_ttl=600  # 10 minutes TTL
    ) as pool:
        
        print("Pool activated with keep-alive enabled")
        
        # Acquire and use first browser
        browser_data1 = await pool.acquire_browser()
        if browser_data1:
            browser1 = browser_data1['browser']
            print(f"First browser acquired: {browser_data1['session_id']}")
            
            await browser1.page.goto("https://httpbin.org/ip")
            print("First browser: navigated to httpbin")
            
            # Release first browser (will be kept alive in pool)
            await pool.release_browser(browser_data1)
            print("First browser released to pool")
        
        # Check pool status
        status = await pool.get_pool_status()
        print(f"Pool status: {status}")
        
        # Acquire second browser (might reuse the first one)
        browser_data2 = await pool.acquire_browser()
        if browser_data2:
            browser2 = browser_data2['browser']
            print(f"Second browser acquired: {browser_data2['session_id']}")
            
            await browser2.page.goto("https://httpbin.org/user-agent")
            print("Second browser: navigated to user-agent endpoint")
            
            # Release second browser
            await pool.release_browser(browser_data2)
            print("Second browser released to pool")
        
        # Final pool status
        final_status = await pool.get_pool_status()
        print(f"Final pool status: {final_status}")
    
    print("Pool context exited - all browsers cleaned up")


async def example_browser_context_manager():
    """
    Example 3: Using individual browser context managers.
    
    This shows how to use the ScrapelessBrowserContextManager for
    convenient automatic browser acquisition and release.
    """
    print("\n=== Example 3: Browser Context Manager ===")
    
    # Create pool for context manager usage
    async with ScrapelessBrowserPool(
        max_concurrent=2,
        acquisition_timeout=20
    ) as pool:
        
        # Use browser context manager for automatic management
        try:
            async with ScrapelessBrowserContextManager(
                pool,
                timeout=10,
                session_config={'proxy_country': 'US'}
            ) as browser:
                print("Browser acquired via context manager")
                
                # Use the browser
                await browser.page.goto("https://httpbin.org/headers")
                title = await browser.page.title()
                print(f"Page title: {title}")
                
                # Browser will be automatically released when exiting context
                
        except TimeoutError as e:
            print(f"Browser acquisition timed out: {e}")
        except Exception as e:
            print(f"Error using browser context manager: {e}")
        
        print("Browser context manager exited - browser automatically released")


async def example_concurrent_usage():
    """
    Example 4: Concurrent browser usage with pool limits.
    
    This demonstrates how the pool manages concurrent browser usage
    and respects the global concurrency limits via Redis.
    """
    print("\n=== Example 4: Concurrent Usage ===")
    
    async def worker_task(worker_id: int, pool: ScrapelessBrowserPool) -> None:
        """Worker task that uses a browser from the pool."""
        try:
            print(f"Worker {worker_id}: Requesting browser...")
            
            async with ScrapelessBrowserContextManager(
                pool,
                timeout=5  # Short timeout to demonstrate limits
            ) as browser:
                print(f"Worker {worker_id}: Got browser, working...")
                
                # Simulate some work
                await browser.page.goto("https://httpbin.org/delay/1")
                await asyncio.sleep(2)  # Simulate processing time
                
                print(f"Worker {worker_id}: Work completed")
                
        except TimeoutError:
            print(f"Worker {worker_id}: Timed out waiting for browser")
        except Exception as e:
            print(f"Worker {worker_id}: Error - {e}")
    
    # Create pool with low concurrency limit for demonstration
    async with ScrapelessBrowserPool(
        max_concurrent=2,  # Only 2 concurrent browsers allowed
        acquisition_timeout=30
    ) as pool:
        
        # Launch 5 concurrent workers (more than the limit)
        tasks = [
            asyncio.create_task(worker_task(i, pool))
            for i in range(1, 6)
        ]
        
        # Wait for all workers to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check final pool status
        status = await pool.get_pool_status()
        print(f"Final pool status after concurrent usage: {status}")


async def example_manual_resource_management():
    """
    Example 5: Manual resource management and monitoring.
    
    This shows how to manually manage browsers and monitor
    pool status for debugging and optimization.
    """
    print("\n=== Example 5: Manual Resource Management ===")
    
    pool = ScrapelessBrowserPool(
        max_concurrent=3,
        browser_ttl=120  # 2 minutes TTL for quick demonstration
    )
    
    try:
        # Manually acquire several browsers
        browsers = []
        for i in range(3):
            browser_data = await pool.acquire_browser(timeout=5)
            if browser_data:
                browsers.append(browser_data)
                print(f"Acquired browser {i+1}: {browser_data['session_id']}")
            else:
                print(f"Failed to acquire browser {i+1}")
        
        # Check pool status
        status = await pool.get_pool_status()
        print(f"Pool status with {len(browsers)} active browsers: {status}")
        
        # Try to acquire one more (should fail due to limit)
        extra_browser = await pool.acquire_browser(timeout=2)
        if extra_browser:
            print("Unexpected: Got extra browser beyond limit")
            browsers.append(extra_browser)
        else:
            print("Expected: Failed to acquire browser beyond limit")
        
        # Release first browser
        if browsers:
            released_browser = browsers.pop(0)
            await pool.release_browser(released_browser)
            print(f"Released browser: {released_browser['session_id']}")
        
        # Now try to acquire again (should succeed)
        new_browser = await pool.acquire_browser(timeout=5)
        if new_browser:
            print(f"Successfully acquired new browser: {new_browser['session_id']}")
            browsers.append(new_browser)
        
        # Manual cleanup
        print(f"Manually cleaning up {len(browsers)} browsers...")
        for browser_data in browsers:
            await pool.release_browser(browser_data)
        
        # Final cleanup
        total_cleaned = await pool.cleanup_all_browsers()
        print(f"Final cleanup removed {total_cleaned} browsers")
        
    except Exception as e:
        print(f"Error in manual management: {e}")
    
    finally:
        # Ensure cleanup
        await pool.cleanup_all_browsers()


async def example_error_handling():
    """
    Example 6: Error handling and recovery.
    
    This demonstrates proper error handling when working with
    the browser pool in various failure scenarios.
    """
    print("\n=== Example 6: Error Handling ===")
    
    # Test with invalid Redis connection (will use fallback behavior)
    try:
        # Create pool with potentially problematic settings
        pool = ScrapelessBrowserPool(
            redis_client=AsyncRedisClient("redis://invalid-host:6379/0"),
            max_concurrent=1,
            acquisition_timeout=5
        )
        
        print("Testing with invalid Redis connection...")
        
        # This should handle Redis connection errors gracefully
        browser_data = await pool.acquire_browser(timeout=3)
        if browser_data:
            print("Acquired browser despite Redis issues")
            await pool.release_browser(browser_data)
        else:
            print("Failed to acquire browser (expected with invalid Redis)")
        
    except Exception as e:
        print(f"Handled Redis connection error: {e}")
    
    # Test timeout handling
    try:
        pool = ScrapelessBrowserPool(
            max_concurrent=1,
            acquisition_timeout=2  # Very short timeout
        )
        
        # Acquire first browser
        browser_data1 = await pool.acquire_browser()
        if browser_data1:
            print("Acquired first browser")
            
            # Try to acquire second browser with short timeout (should fail)
            try:
                browser_data2 = await pool.acquire_browser(timeout=1)
                if browser_data2:
                    print("Unexpected: Got second browser")
                    await pool.release_browser(browser_data2)
                else:
                    print("Expected: Second browser acquisition timed out")
            except Exception as e:
                print(f"Handled timeout error: {e}")
            
            # Clean up
            await pool.release_browser(browser_data1)
        
        await pool.cleanup_all_browsers()
        
    except Exception as e:
        print(f"Error in timeout testing: {e}")


async def example_ttl_expiration_handling():
    """
    Example 7: TTL expiration handling.
    
    This demonstrates how the pool handles browser expiration based on TTL,
    automatically cleaning up expired browsers during acquisition.
    """
    print("\n=== Example 7: TTL Expiration Handling ===")
    
    # Create pool with very short TTL for demonstration
    async with ScrapelessBrowserPool(
        max_concurrent=3,
        browser_ttl=5,  # Very short TTL: 5 seconds
        acquisition_timeout=10
    ) as pool:
        
        print("Creating browsers with 5-second TTL...")
        
        # Acquire and release browsers to populate the pool
        browsers_created = []
        for i in range(2):
            browser_data = await pool.acquire_browser()
            if browser_data:
                print(f"Created browser {i+1}: {browser_data['session_id']}")
                browsers_created.append(browser_data['session_id'])
                await pool.release_browser(browser_data)  # Return to pool
        
        # Check pool status
        status = await pool.get_pool_status()
        print(f"Pool status after creation: available={status['available_browsers']}")
        
        # Wait for browsers to expire
        print("Waiting 6 seconds for browsers to expire...")
        await asyncio.sleep(6)
        
        # Try to acquire a browser - this should trigger cleanup of expired browsers
        print("Attempting to acquire browser (should cleanup expired ones)...")
        browser_data = await pool.acquire_browser()
        if browser_data:
            print(f"Got new browser: {browser_data['session_id']} (expired ones cleaned up)")
            print(f"Previous browsers were: {browsers_created}")
            await pool.release_browser(browser_data)
        
        # Final pool status
        final_status = await pool.get_pool_status()
        print(f"Final pool status: available={final_status['available_browsers']}")


async def example_force_close_mechanism():
    """
    Example 8: Force close mechanism for error recovery.
    
    This demonstrates how to force close browsers when they encounter errors,
    preventing problematic browsers from being returned to the pool.
    """
    print("\n=== Example 8: Force Close Mechanism ===")
    
    async with ScrapelessBrowserPool(
        max_concurrent=3,
        browser_ttl=300
    ) as pool:
        
        print("Demonstrating force close mechanism...")
        
        # Method 1: Manual force close
        print("\n--- Manual Force Close ---")
        browser_data = await pool.acquire_browser()
        if browser_data:
            browser = browser_data['browser']
            print(f"Acquired browser: {browser_data['session_id']}")
            
            try:
                # Simulate using the browser
                await browser.page.goto("https://httpbin.org/status/200")
                print("Browser working normally")
                
                # Simulate detecting an error condition
                error_detected = random.choice([True, False])
                if error_detected:
                    print("Error detected! Force closing browser...")
                    await pool.force_close_browser(browser_data)
                    print("Browser force closed - won't be reused")
                else:
                    print("No error - releasing browser normally")
                    await pool.release_browser(browser_data)
                    
            except Exception as e:
                print(f"Exception during browser usage: {e}")
                await pool.force_close_browser(browser_data)
        
        # Method 2: Context manager with automatic force close on error
        print("\n--- Automatic Force Close on Error ---")
        try:
            async with ScrapelessBrowserContextManager(
                pool, 
                force_close_on_error=True  # Auto force close on exceptions
            ) as browser:
                print("Browser acquired via context manager")
                
                # Simulate an operation that might fail
                should_fail = random.choice([True, False])
                if should_fail:
                    print("Simulating browser error...")
                    raise Exception("Simulated browser error")
                else:
                    await browser.page.goto("https://httpbin.org/status/200")
                    print("Browser operation successful")
                    
        except Exception as e:
            print(f"Exception handled: {e}")
            print("Browser was automatically force closed due to exception")
        
        # Method 3: Manual force close via context manager
        print("\n--- Manual Force Close via Context Manager ---")
        try:
            async with ScrapelessBrowserContextManager(pool) as browser:
                print("Browser acquired for manual force close demo")
                
                # Get reference to context manager for force close
                context_manager = browser  # In real usage, you'd store the context manager reference
                
                # Simulate detecting an issue
                issue_detected = True
                if issue_detected:
                    print("Issue detected - requesting force close...")
                    # In real usage, you'd call: await context_manager.force_close()
                    # For demo, we'll just raise an exception to trigger auto force close
                    raise Exception("Manual force close requested")
                    
        except Exception as e:
            print(f"Exception triggered force close: {e}")
        
        # Check final pool status
        status = await pool.get_pool_status()
        print(f"\nFinal pool status: {status}")


async def example_local_concurrency_limiting():
    """
    Example 9: Local concurrency limiting.
    
    This demonstrates how to set pool-specific concurrency limits
    that are lower than the global Redis limits.
    """
    print("\n=== Example 9: Local Concurrency Limiting ===")
    
    async def worker_with_artificial_limit(worker_id: int, pool: ScrapelessBrowserPool) -> str:
        """Worker task that tries to acquire a browser from a limited pool."""
        try:
            print(f"Worker {worker_id}: Requesting browser...")
            
            browser_data = await pool.acquire_browser(timeout=3)  # Short timeout
            if browser_data:
                print(f"Worker {worker_id}: Got browser {browser_data['session_id']}")
                
                # Simulate work
                await asyncio.sleep(1)
                
                await pool.release_browser(browser_data)
                return f"Worker {worker_id}: Success"
            else:
                return f"Worker {worker_id}: Failed - timeout/limit reached"
                
        except Exception as e:
            return f"Worker {worker_id}: Error - {e}"
    
    # Create pool with artificial local limit (lower than global)
    pool = ScrapelessBrowserPool(
        max_concurrent=100,  # Global limit via Redis
        max_concurrent_local=2,  # Local pool limit (artificially low)
        acquisition_timeout=30
    )
    
    try:
        print(f"Pool configured with local limit of 2 browsers (global limit: 100)")
        
        # Launch 5 concurrent workers (more than local limit)
        tasks = [
            asyncio.create_task(worker_with_artificial_limit(i, pool))
            for i in range(1, 6)
        ]
        
        # Wait for all workers and collect results
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        print("\nWorker Results:")
        for result in results:
            print(f"  {result}")
        
        # Check pool status
        status = await pool.get_pool_status()
        print(f"\nPool Status:")
        print(f"  Local Active Count: {status['local_active_count']}")
        print(f"  Effective Max Concurrent: {status['effective_max_concurrent']}")
        print(f"  Global Max: {status['max_concurrent']}")
        print(f"  Local Max: {status['max_concurrent_local']}")
        
    finally:
        await pool.cleanup_all_browsers()


async def example_comprehensive_error_scenarios():
    """
    Example 10: Comprehensive error handling scenarios.
    
    This demonstrates various error scenarios and how the pool handles them,
    including browser failures, network issues, and recovery strategies.
    """
    print("\n=== Example 10: Comprehensive Error Scenarios ===")
    
    async with ScrapelessBrowserPool(
        max_concurrent=3,
        browser_ttl=60,
        acquisition_timeout=10
    ) as pool:
        
        # Scenario 1: Browser fails during usage
        print("\n--- Scenario 1: Browser Failure During Usage ---")
        try:
            async with ScrapelessBrowserContextManager(
                pool, 
                force_close_on_error=True
            ) as browser:
                print("Testing browser failure scenario...")
                
                # Simulate browser failure
                should_simulate_failure = True
                if should_simulate_failure:
                    print("Simulating browser failure...")
                    # In real scenario, this might be a navigation timeout, 
                    # page crash, or other browser-specific error
                    raise Exception("Browser session crashed")
                    
        except Exception as e:
            print(f"Browser failure handled: {e}")
            print("Problematic browser was force closed")
        
        # Scenario 2: Partial failure with retry
        print("\n--- Scenario 2: Retry Logic with Force Close ---")
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with ScrapelessBrowserContextManager(pool) as browser:
                    print(f"Attempt {attempt + 1}: Trying browser operation...")
                    
                    # Simulate intermittent failure
                    if attempt < 2:  # Fail first 2 attempts
                        raise Exception(f"Simulated failure on attempt {attempt + 1}")
                    
                    # Success on 3rd attempt
                    print("Operation successful!")
                    break
                    
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    print("Max retries reached")
                else:
                    print("Browser force closed, retrying with new browser...")
                    await asyncio.sleep(0.5)  # Brief delay before retry
        
        # Scenario 3: Resource exhaustion handling
        print("\n--- Scenario 3: Resource Exhaustion Handling ---")
        
        # Acquire all available browsers
        acquired_browsers = []
        for i in range(pool.effective_max_concurrent):
            browser_data = await pool.acquire_browser(timeout=2)
            if browser_data:
                acquired_browsers.append(browser_data)
                print(f"Acquired browser {i+1}: {browser_data['session_id']}")
        
        print(f"Acquired {len(acquired_browsers)} browsers (pool limit)")
        
        # Try to acquire one more (should fail)
        extra_browser = await pool.acquire_browser(timeout=1)
        if extra_browser:
            print("Unexpected: Got browser beyond limit")
            acquired_browsers.append(extra_browser)
        else:
            print("Expected: No more browsers available (limit reached)")
        
        # Simulate one browser having issues and force close it
        if acquired_browsers:
            problematic_browser = acquired_browsers.pop(0)
            print(f"Force closing problematic browser: {problematic_browser['session_id']}")
            await pool.force_close_browser(problematic_browser)
            
            # Now we should be able to acquire a new browser
            replacement_browser = await pool.acquire_browser(timeout=2)
            if replacement_browser:
                print(f"Successfully acquired replacement browser: {replacement_browser['session_id']}")
                acquired_browsers.append(replacement_browser)
        
        # Clean up remaining browsers
        print(f"Cleaning up {len(acquired_browsers)} remaining browsers...")
        for browser_data in acquired_browsers:
            await pool.release_browser(browser_data)
        
        # Final status
        final_status = await pool.get_pool_status()
        print(f"Final pool status: {final_status}")


async def example_profile_management():
    """
    Example 11: Profile management with browser pools.
    
    This demonstrates how to use browser profiles for improved consistency
    and management across browser sessions.
    """
    print("\n=== Example 11: Profile Management ===")
    
    # Example 1: Using profiles with default settings (profiles enabled)
    print("\n--- Profiles Enabled (Default) ---")
    async with ScrapelessBrowserPool(
        max_concurrent=2,
        browser_ttl=300,
        use_profiles=True,  # Default behavior
        persist_profile=False  # Don't persist profiles after use
    ) as pool:
        
        print("Pool with profiles enabled")
        
        # Check pool status to see profile information
        status = await pool.get_pool_status()
        print(f"Profile usage: {status['use_profiles']}")
        print(f"Profile persistence: {status['persist_profile']}")
        if 'profile_stats' in status and status['profile_stats']:
            print(f"Available profiles: {status['profile_stats'].get('total_profiles', 'N/A')}")
        
        # Acquire browsers - each should get a profile
        browsers = []
        for i in range(2):
            browser_data = await pool.acquire_browser()
            if browser_data:
                browser = browser_data['browser']
                allocated_profile = browser_data.get('allocated_profile')
                profile_info = allocated_profile.name if allocated_profile else 'None'
                print(f"Browser {i+1}: {browser_data['session_id']} with profile: {profile_info}")
                
                # Use the browser
                try:
                    await browser.page.goto("https://httpbin.org/headers")
                    print(f"Browser {i+1}: Navigation successful")
                except Exception as e:
                    print(f"Browser {i+1}: Navigation error: {e}")
                
                browsers.append(browser_data)
        
        # Release browsers
        for i, browser_data in enumerate(browsers):
            await pool.release_browser(browser_data)
            print(f"Released browser {i+1}")
        
        # Final status
        final_status = await pool.get_pool_status()
        print(f"Final profile stats: {final_status.get('profile_stats', {})}")
    
    # Example 2: Disabling profiles
    print("\n--- Profiles Disabled ---")
    async with ScrapelessBrowserPool(
        max_concurrent=2,
        browser_ttl=300,
        use_profiles=False  # Disable profile usage
    ) as pool:
        
        print("Pool with profiles disabled")
        
        browser_data = await pool.acquire_browser()
        if browser_data:
            browser = browser_data['browser']
            allocated_profile = browser_data.get('allocated_profile')
            print(f"Browser without profile: profile = {allocated_profile}")
            
            try:
                await browser.page.goto("https://httpbin.org/ip")
                print("Navigation successful without profile")
            except Exception as e:
                print(f"Navigation error: {e}")
            
            await pool.release_browser(browser_data)
    
    # Example 3: Persistent profiles
    print("\n--- Persistent Profiles ---")
    async with ScrapelessBrowserPool(
        max_concurrent=1,
        browser_ttl=300,
        use_profiles=True,
        persist_profile=True  # Keep profiles after browser sessions
    ) as pool:
        
        print("Pool with persistent profiles")
        
        # First browser session
        browser_data1 = await pool.acquire_browser()
        if browser_data1:
            browser1 = browser_data1['browser']
            allocated_profile1 = browser_data1.get('allocated_profile')
            profile_name1 = allocated_profile1.name if allocated_profile1 else 'None'
            print(f"First session: Using profile {profile_name1}")
            
            try:
                await browser1.page.goto("https://httpbin.org/cookies/set/test/persistent")
                print("Set cookie in first session")
            except Exception as e:
                print(f"Cookie setting error: {e}")
            
            await pool.release_browser(browser_data1)
            print("Released first browser (profile should persist)")
        
        # Second browser session - might reuse the persisted profile
        browser_data2 = await pool.acquire_browser()
        if browser_data2:
            browser2 = browser_data2['browser']
            allocated_profile2 = browser_data2.get('allocated_profile')
            profile_name2 = allocated_profile2.name if allocated_profile2 else 'None'
            print(f"Second session: Using profile {profile_name2}")
            
            try:
                await browser2.page.goto("https://httpbin.org/cookies")
                print("Checked cookies in second session")
            except Exception as e:
                print(f"Cookie check error: {e}")
            
            await pool.release_browser(browser_data2)


async def example_profile_context_manager():
    """
    Example 12: Profile usage with context managers.
    
    This demonstrates how profile settings can be overridden at the
    context manager level for fine-grained control.
    """
    print("\n=== Example 12: Profile Context Manager ===")
    
    # Create pool with profiles enabled
    async with ScrapelessBrowserPool(
        max_concurrent=3,
        use_profiles=True,
        persist_profile=False
    ) as pool:
        
        print("Testing profile overrides in context manager")
        
        # Context manager with default pool settings
        print("\n--- Using Pool Profile Settings ---")
        try:
            async with ScrapelessBrowserContextManager(pool, timeout=10) as browser:
                print("Browser acquired with pool's profile settings")
                await browser.page.goto("https://httpbin.org/headers")
                print("Navigation successful")
        except Exception as e:
            print(f"Error with pool settings: {e}")
        
        # Context manager with profile persistence override
        print("\n--- Overriding Profile Persistence ---")
        try:
            async with ScrapelessBrowserContextManager(
                pool, 
                timeout=10,
                persist_profile=True  # Override pool setting
            ) as browser:
                print("Browser acquired with persistent profile override")
                await browser.page.goto("https://httpbin.org/user-agent")
                print("Navigation successful with persistent profile")
        except Exception as e:
            print(f"Error with persistence override: {e}")
        
        # Context manager with profiles disabled
        print("\n--- Disabling Profiles for This Browser ---")
        try:
            async with ScrapelessBrowserContextManager(
                pool,
                timeout=10, 
                use_profiles=False  # Override pool setting
            ) as browser:
                print("Browser acquired without profile (override)")
                await browser.page.goto("https://httpbin.org/ip")
                print("Navigation successful without profile")
        except Exception as e:
            print(f"Error without profiles: {e}")


async def example_profile_error_handling():
    """
    Example 13: Profile error handling and fallback behavior.
    
    This demonstrates how the system handles profile-related errors
    gracefully and continues operation.
    """
    print("\n=== Example 13: Profile Error Handling ===")
    
    # Test with potentially problematic profile configuration
    print("\n--- Testing Profile Error Recovery ---")
    
    try:
        # Create pool with profiles but potentially invalid Redis for profile manager
        pool = ScrapelessBrowserPool(
            max_concurrent=2,
            use_profiles=True,
            # Profile manager will use default Redis, but we'll test error scenarios
        )
        
        # Test browser acquisition even if profile system has issues
        browser_data = await pool.acquire_browser(timeout=5)
        if browser_data:
            browser = browser_data['browser']
            allocated_profile = browser_data.get('allocated_profile')
            print(f"Browser acquired despite potential profile issues: profile = {allocated_profile}")
            
            try:
                await browser.page.goto("https://httpbin.org/status/200")
                print("Browser navigation successful")
            except Exception as e:
                print(f"Navigation error: {e}")
            
            await pool.release_browser(browser_data)
            print("Browser released successfully")
        else:
            print("Failed to acquire browser")
        
        await pool.cleanup_all_browsers()
        
    except Exception as e:
        print(f"Handled profile error gracefully: {e}")
    
    # Test force close with profiles
    print("\n--- Testing Force Close with Profiles ---")
    async with ScrapelessBrowserPool(
        max_concurrent=2,
        use_profiles=True,
        persist_profile=False
    ) as pool:
        
        browser_data = await pool.acquire_browser()
        if browser_data:
            allocated_profile = browser_data.get('allocated_profile')
            profile_name = allocated_profile.name if allocated_profile else 'None'
            print(f"Acquired browser with profile: {profile_name}")
            
            # Simulate an error condition requiring force close
            print("Simulating error condition - force closing browser...")
            success = await pool.force_close_browser(browser_data)
            if success:
                print("Browser force closed successfully (profile should be released)")
            else:
                print("Force close failed")
        
        # Check pool status after force close
        status = await pool.get_pool_status()
        print(f"Pool status after force close: active={status['active_browsers']}")


async def example_mixed_profile_usage():
    """
    Example 14: Mixed profile usage scenarios.
    
    This demonstrates various combinations of profile settings
    and how they interact in complex usage patterns.
    """
    print("\n=== Example 14: Mixed Profile Usage ===")
    
    async def worker_with_profiles(worker_id: int, pool: ScrapelessBrowserPool, use_profiles: bool) -> str:
        """Worker that uses or doesn't use profiles based on parameter."""
        try:
            async with ScrapelessBrowserContextManager(
                pool,
                timeout=5,
                use_profiles=use_profiles,
                session_config={'proxy_country': 'US'}
            ) as browser:
                allocated_profile = getattr(browser, 'profile_id', None)
                profile_info = f"with profile {allocated_profile}" if allocated_profile else "without profile"
                print(f"Worker {worker_id}: Got browser {profile_info}")
                
                # Simulate work
                await browser.page.goto("https://httpbin.org/delay/1")
                await asyncio.sleep(0.5)
                
                return f"Worker {worker_id}: Success {profile_info}"
                
        except Exception as e:
            return f"Worker {worker_id}: Error - {e}"
    
    # Create pool with profiles enabled
    async with ScrapelessBrowserPool(
        max_concurrent=4,
        use_profiles=True,
        persist_profile=False
    ) as pool:
        
        print("Testing mixed profile usage patterns")
        
        # Launch workers with different profile preferences
        tasks = []
        for i in range(1, 5):
            use_profiles = i % 2 == 1  # Alternate between using profiles and not
            tasks.append(
                asyncio.create_task(worker_with_profiles(i, pool, use_profiles))
            )
        
        # Wait for all workers
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        print("\nWorker Results:")
        for result in results:
            print(f"  {result}")
        
        # Final pool status
        status = await pool.get_pool_status()
        print(f"\nFinal Status:")
        print(f"  Active browsers: {status['active_browsers']}")
        print(f"  Use profiles: {status['use_profiles']}")
        if 'profile_stats' in status and status['profile_stats']:
            profile_stats = status['profile_stats']
            print(f"  Profile allocations: {profile_stats.get('total_active_allocations', 'N/A')}")


async def main():
    """
    Main function to run all examples.
    
    Uncomment the examples you want to run. Note that some examples
    require a valid Scrapeless API key and Redis connection.
    """
    print("ScrapelessBrowserPool Usage Examples")
    print("===================================")
    
    try:
        # Run examples (comment out any you don't want to run)
        
        await example_basic_pool_usage()
        await asyncio.sleep(1)  # Brief pause between examples
        
        await example_keep_alive_pool()
        await asyncio.sleep(1)
        
        await example_browser_context_manager()
        await asyncio.sleep(1)
        
        await example_concurrent_usage()
        await asyncio.sleep(1)
        
        await example_manual_resource_management()
        await asyncio.sleep(1)
        
        await example_error_handling()
        await asyncio.sleep(1)
        
        # New examples demonstrating enhanced features
        await example_ttl_expiration_handling()
        await asyncio.sleep(1)
        
        await example_force_close_mechanism()
        await asyncio.sleep(1)
        
        await example_local_concurrency_limiting()
        await asyncio.sleep(1)
        
        await example_comprehensive_error_scenarios()
        await asyncio.sleep(1)
        
        # NEW: Profile management examples
        await example_profile_management()
        await asyncio.sleep(1)
        
        await example_profile_context_manager()
        await asyncio.sleep(1)
        
        await example_profile_error_handling()
        await asyncio.sleep(1)
        
        await example_mixed_profile_usage()
        
    except KeyboardInterrupt:
        print("\nExamples interrupted by user")
    except Exception as e:
        print(f"Error in examples: {e}")
    
    print("\nAll examples completed!")


if __name__ == "__main__":
    # Run the examples
    asyncio.run(main()) 