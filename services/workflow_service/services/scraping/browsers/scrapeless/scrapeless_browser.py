import random
from workflow_service.services.scraping.settings import scraping_settings
from urllib.parse import urlencode
from playwright.async_api import async_playwright, Page, BrowserContext, Browser, Request, Route
from typing import Optional, Dict, List, Set
import asyncio
import time
import uuid
from datetime import datetime

import logging

from workflow_service.services.scraping.browsers.config import DEFAULT_ENTITY_PREFIX, MAX_CONCURRENT_SCRAPELESS_BROWSERS, ACQUISITION_TIMEOUT

# Import profile management
from workflow_service.services.scraping.browsers.scrapeless.profiles import ScrapelessProfileManager, ProfileData

logger = logging.getLogger(__name__)


from global_config.settings import global_settings
from redis_client.redis_client import AsyncRedisClient

# redis_url: str = global_settings.REDIS_URL

class ScrapelessBrowser:
    def __init__(
        self, 
        token: Optional[str] = None, 
        session_name: Optional[str] = None, 
        session_ttl: Optional[str] = None,
        persist_profile: bool = False,
        profile_id: Optional[str] = None,
        intercept_media: bool = True,
        intercept_images: bool = True
    ):
        """
        Initialize a ScrapelessBrowser instance.
        
        Args:
            token: Scrapeless API token
            session_name: Name for the browser session
            session_ttl: Session time-to-live in seconds (default: 15 minutes)
            persist_profile: Whether to persist the browser profile
            profile_id: Specific profile ID to use
            intercept_media: Whether to block media resources (video, audio, etc.)
            intercept_images: Whether to block image resources
        """
        super().__init__()
        self.token = token or scraping_settings.SCRAPELESS_API_KEY
        self.session_name = session_name or f"{DEFAULT_ENTITY_PREFIX}-{random.randint(100000, 999999)}"
        self.session_ttl = session_ttl or str(60 * 15) # 15 minutes
        self.persist_profile = persist_profile
        self.profile_id = profile_id
        self.intercept_media = intercept_media
        self.intercept_images = intercept_images
        self.connection_url = None
        self.playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None


    def build_connection_url(
        self, 
        session_name: str, 
        session_ttl: str, 
        proxy_country: str = "US", 
        extension_ids: Optional[str] = None,
        profile_id: Optional[str] = None,
        profile_persist: bool = False
    ):
        """
        Builds the connection URL for the Scrapeless session.

        Args:
            session_name (str): The name of the session.
            session_ttl (str): seconds between 60 (1 minute) and 900 (15 minutes).
            proxy_country (str): The country of the proxy.
            extension_ids (Optional[str]): Comma separated list of extension IDs to use.
            profile_id (Optional[str]): Browser profile ID to use.
            profile_persist (bool): Whether to persist the profile after session ends.

        Returns:
            str: The connection URL for the Scrapeless session.
        """
        query = {
            "token": self.token,
            "proxy_country": proxy_country,
            "session_recording": "true",
            "session_ttl": session_ttl,
            "session_name": session_name,
        }
        
        if extension_ids:
            query["extension_ids"] = extension_ids
            
        # Add profile parameters if using profiles
        if profile_id:
            query["profile_id"] = profile_id
        query["profile_persist"] = "false"
        if profile_persist:
            query["profile_persist"] = "true"

        url = f"wss://browser.scrapeless.com/browser?{urlencode(query)}"
        logger.info(f"Connection URL: {url}")
        return url

    async def _setup_resource_blocking(self) -> None:
        """
        Set up resource blocking for images and media based on intercept settings.
        
        This method configures Playwright to block specific resource types:
        - Images: image resources (jpg, png, gif, webp, etc.)
        - Media: video, audio, font, and other media resources
        
        The blocking helps reduce bandwidth usage and improve scraping performance
        by preventing unnecessary resource downloads.
        """
        if not (self.intercept_images or self.intercept_media):
            return
            
        # Define resource types to block based on settings
        blocked_types: Set[str] = set()
        
        if self.intercept_images:
            blocked_types.add('image')
            logger.debug("Image resources will be blocked")
            
        if self.intercept_media:
            # Block various media and non-essential resource types
            blocked_types.update([
                'media', 
                'font',
            ])
            logger.debug("Media resources will be blocked")
        
        async def route_handler(route: Route, request: Request):
            """
            Route handler to block specific resource types.
            
            Args:
                route: Playwright route object
                request: Playwright request object
            """
            resource_type = request.resource_type
            
            if resource_type in blocked_types:
                # Block the request by aborting it
                await route.abort()
                logger.debug(f"Blocked {resource_type} request: {request.url}")
            else:
                # Allow the request to continue
                await route.continue_()
        
        try:
            # Set up route interception on the page context
            await self.context.route("**/*", route_handler)
            logger.info(f"Resource blocking configured - Images: {self.intercept_images}, Media: {self.intercept_media}")
        except Exception as e:
            logger.error(f"Failed to set up resource blocking: {e}")
            # Don't raise the exception as this is not critical for basic functionality
    
    async def start_session(
        self, 
        session_name: Optional[str] = None, 
        session_ttl: Optional[str] = None, 
        proxy_country: str = "US",
    ):
        """
        Starts a Scrapeless session and initializes Playwright.
        
        Args:
            session_name: Optional session name override
            session_ttl: Optional session TTL override  
            proxy_country: Proxy country code
        """
        try:
            if not session_name:
                session_name = self.session_name
            if not session_ttl:
                session_ttl = self.session_ttl
                
            # Handle profile allocation if using profiles
            profile_id_to_use = self.profile_id
                        
            self.connection_url = self.build_connection_url(
                session_name, 
                session_ttl, 
                proxy_country,
                profile_id=profile_id_to_use,
                profile_persist=self.persist_profile
            )
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.connect_over_cdp(self.connection_url)
            self.context = self.browser.contexts[0]
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
            
            # Set up resource blocking if intercept options are enabled
            await self._setup_resource_blocking()
            
            print(f"Connected to Scrapeless session: {self.connection_url}")
            return self.page.url
        except Exception as e:
            raise Exception(f"Failed to start Scrapeless session: {e}")
    
    async def get_live_url(self):
        # Create a new page (this is async in Playwright)
        new_page = self.page or await self.context.new_page()
        try:
            await new_page.goto("https://www.wikipedia.org", timeout=60000, wait_until="load")
            
            # Create CDP session using Playwright's API
            client = await self.context.new_cdp_session(new_page)
            try:
                # Send the CDP command
                result = await client.send('Agent.liveURL')
                return result
            finally:
                # Always close the CDP session when done
                # await client.detach()
                pass
                
        finally:
            pass
        #     # Close the new page since we're done with it
        #     await new_page.close()
    
    async def close_session(self):
        """
        Closes the Scrapeless session and releases resources.
        
        Args:
            profile_manager: Optional profile manager for profile cleanup
        """
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        
        self.browser = None
        self.context = None
        self.page = None
        self.connection_url = None
        self.playwright = None
        self.profile_id = None
    
    async def __aenter__(self) -> "ScrapelessBrowser":
        """Enables use as an async context manager, performing start_session."""
        await self.start_session()
        return self

    async def __aexit__(self, *args) -> None:
        """Closes the session when exiting the context."""
        await self.close_session()


class ScrapelessBrowserPool:
    """
    A pool manager for ScrapelessBrowser instances with Redis-based concurrency control.
    
    This class provides:
    - Global concurrency limits via Redis resource tracking
    - In-memory browser pooling for reuse
    - Configurable keep-alive behavior for browsers
    - Timeout support for resource acquisition
    - Manual cleanup functionality
    - Force close mechanism for error recovery
    - Local concurrency limiting
    - Force cleanup Redis pool functionality
    
    Features:
    - Respects MAX_CONCURRENT_SCRAPELESS_BROWSERS limit globally across all processes
    - Maintains a pool of active browsers in memory for reuse
    - Uses Redis for distributed resource counting and locking
    - Supports both individual browser context managers and pool-level management
    - Provides comprehensive error handling and cleanup
    - Checks browser TTL expiration during acquisition
    - Force close problematic browsers regardless of keep-alive settings
    - Force cleanup Redis pool for recovery from corrupted state
    """
    
    def __init__(
        self, 
        redis_client: Optional[AsyncRedisClient] = None,
        max_concurrent: int = MAX_CONCURRENT_SCRAPELESS_BROWSERS,
        max_concurrent_local: Optional[int] = None,  # Pool-specific limit
        acquisition_timeout: int = ACQUISITION_TIMEOUT,
        browser_ttl: int = 900,  # 15 minutes default TTL for browsers
        pool_id: Optional[str] = None,
        use_profiles: bool = True,
        persist_profile: bool = False,
        profile_manager: Optional[ScrapelessProfileManager] = None,
        enable_keep_alive: bool = True  # Control keep-alive behavior
    ):
        """
        Initialize the ScrapelessBrowserPool.
        
        Args:
            redis_client: Optional Redis client for resource management
            max_concurrent: Maximum concurrent browsers allowed globally via Redis
            max_concurrent_local: Optional pool-specific concurrency limit (overrides global if lower)
            acquisition_timeout: Timeout in seconds for acquiring browser resources
            browser_ttl: Time-to-live for browsers in the pool (seconds)
            pool_id: Optional unique identifier for this pool instance
            use_profiles: Whether to use browser profiles (default: True)
            persist_profile: Whether to persist profiles after browser sessions (default: False)
            profile_manager: Optional external profile manager (if None, creates internal one)
            enable_keep_alive: Whether to enable keep-alive behavior in context manager (default: True)
        """
        self.redis_client = redis_client or AsyncRedisClient(global_settings.REDIS_URL)
        self.max_concurrent = max_concurrent
        # Use local limit if specified and lower than global limit
        self.max_concurrent_local = max_concurrent_local
        self.effective_max_concurrent = (
            min(max_concurrent, max_concurrent_local) 
            if max_concurrent_local is not None 
            else max_concurrent
        )
        self.acquisition_timeout = acquisition_timeout
        self.browser_ttl = browser_ttl
        self.pool_id = pool_id or f"scrapeless_pool_{uuid.uuid4().hex[:8]}"
        self.use_profiles = use_profiles
        self.persist_profile = persist_profile
        self.enable_keep_alive = enable_keep_alive
        
        # Redis pool key for resource management
        self.pool_key = scraping_settings.SCRAPELESS_BROWSERS_POOL_KEY
        
        # Profile management
        if self.use_profiles:
            self.profile_manager = profile_manager or ScrapelessProfileManager(
                save_cache_on_operations=False  # Efficient cache saving
            )
            self._profile_manager_owned = profile_manager is None  # Track if we created it
        else:
            self.profile_manager = None
            self._profile_manager_owned = False
        
        # In-memory browser pool
        self._available_browsers: List[Dict] = []  # Available browsers ready for use
        self._active_browsers: Dict[str, Dict] = {}  # Currently active browsers by session_id
        self._browser_metadata: Dict[str, Dict] = {}  # Metadata for tracking browsers
        
        # Local concurrency tracking
        self._local_active_count: int = 0  # Track local active browsers for artificial limiting
        
        # Pool configuration
        self._keep_alive_on_release = False  # Will be set by pool context manager
        self._pool_active = False
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()  # For thread-safe pool operations
        
        logger.info(
            f"ScrapelessBrowserPool initialized: {self.pool_id}, "
            f"max_concurrent={max_concurrent}, effective_max={self.effective_max_concurrent}, "
            f"use_profiles={use_profiles}, persist_profile={persist_profile}, "
            f"enable_keep_alive={enable_keep_alive}"
        )
    
    async def force_cleanup_redis_pool(self) -> bool:
        """
        Force cleanup the Redis pool by resetting all allocations.
        
        WARNING: This will clear ALL allocations for this pool across ALL processes.
        Use this only when the pool is in a corrupted state and needs recovery.
        
        Returns:
            True if pool was successfully reset, False otherwise
        """
        try:
            logger.warning(f"Force cleaning up Redis pool: {self.pool_key}")
            success = await self.redis_client.reset_pool(self.pool_key)
            if success:
                logger.info(f"Successfully reset Redis pool: {self.pool_key}")
            else:
                logger.warning(f"Failed to reset Redis pool: {self.pool_key}")
            return success
        except Exception as e:
            logger.error(f"Error force cleaning up Redis pool {self.pool_key}: {e}")
            return False
    
    async def _acquire_redis_resource(self) -> Optional[str]:
        """
        Acquire a resource slot from Redis pool.
        
        Returns:
            Allocation ID if resource was acquired, None if failed
        """
        try:
            # Use the new pool-based resource management
            allocation_id, current_usage, success = await self.redis_client.acquire_from_pool(
                pool_key=self.pool_key,
                count=1,
                max_pool_size=self.max_concurrent,
                ttl=self.browser_ttl
            )
            
            if success and allocation_id:
                logger.info(f"✅ Redis resource acquired. Allocation ID: {allocation_id}, Current usage: {current_usage}/{self.max_concurrent}")
                return allocation_id
            else:
                logger.warning(f"❌ Redis resource acquisition failed. Current usage: {current_usage}/{self.max_concurrent}")
                return None
                
        except Exception as e:
            logger.error(f"Error acquiring Redis resource: {e}", exc_info=True)
            return None
    
    async def _release_redis_resource(self, allocation_id: str) -> bool:
        """
        Release a resource slot back to Redis pool.
        
        Args:
            allocation_id: The allocation ID returned from _acquire_redis_resource
            
        Returns:
            True if resource was released successfully
        """
        try:
            released_count, current_usage, success = await self.redis_client.release_to_pool(
                pool_key=self.pool_key,
                allocation_id=allocation_id
            )
            
            if success:
                logger.info(f"✅ Redis resource released. Allocation ID: {allocation_id}, Released: {released_count}, Current usage: {current_usage}")
                return True
            else:
                logger.warning(f"❌ Redis resource release failed for allocation ID: {allocation_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error releasing Redis resource for allocation {allocation_id}: {e}", exc_info=True)
            return False
    
    async def _create_new_browser(self, session_config: Optional[Dict] = None) -> Dict:
        """
        Create a new ScrapelessBrowser instance with metadata.
        
        Args:
            session_config: Optional configuration for the browser session
            
        Returns:
            Dictionary containing browser instance and metadata
        """
        session_config = session_config or {}
        
        # Pre-allocate profile if using profiles
        allocated_profile = None
        if self.use_profiles and self.profile_manager:
            try:
                allocated_profile = await self.profile_manager.allocate_profile()
                if allocated_profile:
                    logger.debug(f"Pre-allocated profile for browser: {allocated_profile.name}")
                else:
                    logger.warning("Failed to pre-allocate profile, browser will proceed without profile")
            except Exception as e:
                logger.error(f"Error pre-allocating profile: {e}")
        
        # Create browser instance with profile configuration
        browser = ScrapelessBrowser(
            session_name=session_config.get('session_name'),
            session_ttl=session_config.get('session_ttl'),
            persist_profile=self.persist_profile,
            profile_id=allocated_profile.profile_id if allocated_profile else None,
            intercept_media=session_config.get('intercept_media', True),
            intercept_images=session_config.get('intercept_images', True)
        )
        
        # Start the browser session with profile support
        await browser.start_session(
            proxy_country=session_config.get('proxy_country', 'US'),
        )
        
        # Create metadata
        session_id = f"{self.pool_id}_{uuid.uuid4().hex[:8]}"
        metadata = {
            'browser': browser,
            'session_id': session_id,
            'created_at': datetime.now(),
            'last_used': datetime.now(),
            'use_count': 0,
            'session_config': session_config,
            'redis_allocation_id': None,  # Will be set when resource is acquired
            'allocated_profile': allocated_profile  # Store profile reference for cleanup
        }
        
        logger.info(f"🌐 Created new browser: {session_id} with profile: {allocated_profile.name if allocated_profile else 'None'}")
        return metadata
    
    async def _check_browser_expired(self, browser_data: Dict) -> bool:
        """
        Check if a browser has expired based on TTL.
        
        Args:
            browser_data: Browser metadata dictionary
            
        Returns:
            True if browser is expired, False otherwise
        """
        current_time = datetime.now()
        age = (current_time - browser_data['created_at']).total_seconds()
        return age > self.browser_ttl
    
    async def _cleanup_expired_browser(self, browser_data: Dict) -> None:
        """
        Clean up an expired browser and release its resources.
        
        Args:
            browser_data: Browser metadata dictionary to clean up
        """
        session_id = browser_data.get('session_id', 'unknown')
        allocation_id = browser_data.get('redis_allocation_id')
        
        logger.info(f"🧹 Cleaning up expired browser: {session_id}, allocation_id: {allocation_id}")
        
        # Always try to release Redis resource first
        if allocation_id:
            try:
                await self._release_redis_resource(allocation_id)
            except Exception as e:
                logger.error(f"Failed to release Redis resource during cleanup for {session_id}: {e}")
        
        try:
            # Close browser session with profile cleanup
            await browser_data['browser'].close_session()
            
            # Release profile if not already released by browser close
            allocated_profile = browser_data.get('allocated_profile')
            if (allocated_profile and 
                self.use_profiles and 
                self.profile_manager):
                try:
                    await self.profile_manager.release_profile(allocated_profile.profile_id)
                    logger.debug(f"Released profile during cleanup: {allocated_profile.name}")
                except Exception as e:
                    logger.error(f"Error releasing profile during cleanup: {e}")
            
            # Decrement local counter if this was an active browser
            if browser_data['session_id'] in self._active_browsers:
                self._local_active_count = max(0, self._local_active_count - 1)
            logger.info(f"✅ Successfully cleaned up expired browser: {session_id}")
        except Exception as e:
            logger.error(f"Error cleaning up expired browser {session_id}: {e}", exc_info=True)
    
    async def _cleanup_expired_browsers(self):
        """
        Clean up expired browsers from the pool.
        This runs as a background task.
        """
        while self._pool_active:
            try:
                async with self._lock:
                    current_time = datetime.now()
                    expired_browsers = []
                    
                    # Check available browsers for expiration
                    for browser_data in self._available_browsers[:]:
                        age = (current_time - browser_data['created_at']).total_seconds()
                        if age > self.browser_ttl:
                            expired_browsers.append(browser_data)
                            self._available_browsers.remove(browser_data)
                    
                    # Close expired browsers
                    for browser_data in expired_browsers:
                        await self._cleanup_expired_browser(browser_data)
                
                # Sleep before next cleanup cycle
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(60)
    
    async def acquire_browser(
        self, 
        timeout: Optional[int] = None,
        session_config: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        Acquire a browser from the pool or create a new one.
        
        This method:
        1. Checks available browsers for TTL expiration
        2. Reuses valid available browsers
        3. Creates new browsers if resources allow
        4. Respects both global (Redis) and local concurrency limits
        
        Args:
            timeout: Timeout in seconds for acquiring a browser
            session_config: Optional configuration for new browser sessions
            
        Returns:
            Browser metadata dict or None if acquisition failed/timed out
        """
        timeout = timeout or self.acquisition_timeout
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # First check if we can reuse an available browser (quick operation, hold lock)
            async with self._lock:
                # First, clean up any expired browsers from available pool
                expired_browsers = []
                for browser_data in self._available_browsers[:]:
                    if await self._check_browser_expired(browser_data):
                        expired_browsers.append(browser_data)
                        self._available_browsers.remove(browser_data)
                
                # Clean up expired browsers
                for browser_data in expired_browsers:
                    await self._cleanup_expired_browser(browser_data)
                
                # Try to get a valid available browser from pool
                if self._available_browsers:
                    browser_data = self._available_browsers.pop()
                    browser_data['last_used'] = datetime.now()
                    browser_data['use_count'] += 1
                    self._active_browsers[browser_data['session_id']] = browser_data
                    self._local_active_count += 1
                    logger.info(f"♻️ Reused browser from pool: {browser_data['session_id']}")
                    return browser_data
                
                # Check local concurrency limit before attempting to create new browser
                if self._local_active_count >= self.effective_max_concurrent:
                    logger.debug(f"Local concurrency limit reached: {self._local_active_count}/{self.effective_max_concurrent}")
                    # Continue to retry loop, don't try to create new browser
                    await asyncio.sleep(0.5)
                    continue
                
                # Reserve a slot for the new browser we're about to create
                # This prevents race conditions where multiple tasks might think they can create browsers
                self._local_active_count += 1
            
            # Now try to create a new browser outside the lock (allows parallel creation)
            try:
                # Acquire Redis resource (slow operation, do outside lock)
                allocation_id = await self._acquire_redis_resource()
                if not allocation_id:
                    # Failed to get Redis resource, release the local slot
                    async with self._lock:
                        self._local_active_count = max(0, self._local_active_count - 1)
                    await asyncio.sleep(0.5)
                    continue
                
                # Create browser (slow operation, do outside lock)
                try:
                    browser_data = await self._create_new_browser(session_config)
                    browser_data['redis_allocation_id'] = allocation_id
                    browser_data['use_count'] = 1
                    
                    # Add to active browsers (quick operation, hold lock)
                    async with self._lock:
                        self._active_browsers[browser_data['session_id']] = browser_data
                    
                    return browser_data
                    
                except Exception as e:
                    # Browser creation failed, cleanup
                    logger.error(f"❌ Failed to create new browser: {e}", exc_info=True)
                    await self._release_redis_resource(allocation_id)
                    # Release the local slot we reserved
                    async with self._lock:
                        self._local_active_count = max(0, self._local_active_count - 1)
                    # Continue to retry
                    
            except Exception as e:
                # Unexpected error, release the local slot
                logger.error(f"Unexpected error during browser acquisition: {e}", exc_info=True)
                async with self._lock:
                    self._local_active_count = max(0, self._local_active_count - 1)
            
            # Wait a bit before retrying
            await asyncio.sleep(0.5)
        
        logger.warning(f"Browser acquisition timed out after {timeout}s")
        return None
    
    async def release_browser(self, browser_data: Dict) -> bool:
        """
        Release a browser back to the pool or close it.
        
        Args:
            browser_data: Browser metadata dict returned from acquire_browser
            
        Returns:
            True if browser was released successfully
        """
        session_id = browser_data['session_id']
        allocation_id = browser_data.get('redis_allocation_id')
        allocated_profile = browser_data.get('allocated_profile')
        
        async with self._lock:
            # Check if browser is expired
            is_expired = await self._check_browser_expired(browser_data)
            
            # Remove from active browsers
            if session_id in self._active_browsers:
                del self._active_browsers[session_id]
                self._local_active_count = max(0, self._local_active_count - 1)
            
            # Check if we should keep the browser alive
            if (self._keep_alive_on_release and 
                self._pool_active and 
                not is_expired):
                # Add back to available pool
                browser_data['last_used'] = datetime.now()
                self._available_browsers.append(browser_data)
                logger.debug(f"Browser returned to pool: {session_id}")
                return True
            else:
                # Close the browser and release all resources
                try:
                    # Close browser session with profile cleanup
                    await browser_data['browser'].close_session()
                    
                    # Release Redis resource if allocation ID exists
                    if allocation_id:
                        await self._release_redis_resource(allocation_id)
                    
                    # Release profile if not already released and not persisting
                    if (allocated_profile and 
                        self.use_profiles and 
                        self.profile_manager):
                        try:
                            await self.profile_manager.release_profile(allocated_profile.profile_id)
                            logger.debug(f"Released profile during browser release: {allocated_profile.name}")
                        except Exception as e:
                            logger.error(f"Error releasing profile during browser release: {e}")
                    
                    if is_expired:
                        logger.debug(f"Browser closed due to expiration: {session_id}")
                    else:
                        logger.debug(f"Browser closed and resource released: {session_id}")
                    return True
                except Exception as e:
                    logger.error(f"Error closing browser {session_id}: {e}")
                    # Still try to release resources even if browser close failed
                    if allocation_id:
                        await self._release_redis_resource(allocation_id)
                    if (allocated_profile and 
                        self.use_profiles and 
                        self.profile_manager):
                        try:
                            await self.profile_manager.release_profile(allocated_profile.profile_id)
                        except Exception:
                            pass  # Already logged above
                    return False
    
    async def force_close_browser(self, browser_data: Dict) -> bool:
        """
        Force close a browser immediately, regardless of keep-alive settings or TTL.
        
        This method is useful when a browser encounters errors and needs to be
        closed immediately without returning to the pool.
        
        Args:
            browser_data: Browser metadata dict to force close
            
        Returns:
            True if browser was closed successfully
        """
        session_id = browser_data['session_id']
        allocation_id = browser_data.get('redis_allocation_id')
        allocated_profile = browser_data.get('allocated_profile')
        
        async with self._lock:
            # Remove from both active and available browsers
            if session_id in self._active_browsers:
                del self._active_browsers[session_id]
                self._local_active_count = max(0, self._local_active_count - 1)
            
            # Remove from available browsers if present
            self._available_browsers = [
                b for b in self._available_browsers 
                if b['session_id'] != session_id
            ]
            
            # Force close the browser and release all resources
            try:
                # Force close browser session with profile cleanup
                await browser_data['browser'].close_session()
                
                # Release Redis resource if allocation ID exists
                if allocation_id:
                    await self._release_redis_resource(allocation_id)
                
                # Force release profile (even if persisting, since this is force close)
                if (allocated_profile and 
                    self.use_profiles and 
                    self.profile_manager):
                    try:
                        await self.profile_manager.release_profile(allocated_profile.profile_id)
                        logger.debug(f"Force released profile: {allocated_profile.name}")
                    except Exception as e:
                        logger.error(f"Error force releasing profile: {e}")
                
                logger.info(f"Browser force closed: {session_id}")
                return True
            except Exception as e:
                logger.error(f"Error force closing browser {session_id}: {e}")
                # Still release resources even if browser close failed
                if allocation_id:
                    await self._release_redis_resource(allocation_id)
                if (allocated_profile and 
                    self.use_profiles and 
                    self.profile_manager):
                    try:
                        await self.profile_manager.release_profile(allocated_profile.profile_id)
                    except Exception:
                        pass  # Already logged above
                return False
    
    async def cleanup_all_browsers(self) -> int:
        """
        Manually clean up all browsers in the pool.
        
        Returns:
            Number of browsers cleaned up
        """
        logger.info(f"🧹 Starting cleanup of all browsers in pool: {self.pool_id}")
        
        async with self._lock:
            total_cleaned = 0
            total_redis_resources_released = 0
            
            # Close all available browsers
            for browser_data in self._available_browsers[:]:
                session_id = browser_data.get('session_id', 'unknown')
                allocation_id = browser_data.get('redis_allocation_id')
                
                # Always try to release Redis resource first
                if allocation_id:
                    try:
                        await self._release_redis_resource(allocation_id)
                        total_redis_resources_released += 1
                    except Exception as e:
                        logger.error(f"Failed to release Redis resource for {session_id}: {e}")
                
                try:
                    # Close with profile cleanup
                    await browser_data['browser'].close_session()
                    
                    # Release profile if not persisting
                    allocated_profile = browser_data.get('allocated_profile')
                    if (allocated_profile and 
                        self.use_profiles and 
                        self.profile_manager):
                        try:
                            await self.profile_manager.release_profile(allocated_profile.profile_id)
                        except Exception as e:
                            logger.error(f"Error releasing profile during cleanup: {e}")
                    
                    total_cleaned += 1
                except Exception as e:
                    logger.error(f"Error cleaning up browser {session_id}: {e}", exc_info=True)
            
            self._available_browsers.clear()
            
            # Close all active browsers (force cleanup)
            for browser_data in list(self._active_browsers.values()):
                session_id = browser_data.get('session_id', 'unknown')
                allocation_id = browser_data.get('redis_allocation_id')
                
                # Always try to release Redis resource first
                if allocation_id:
                    try:
                        await self._release_redis_resource(allocation_id)
                        total_redis_resources_released += 1
                    except Exception as e:
                        logger.error(f"Failed to release Redis resource for active browser {session_id}: {e}")
                
                try:
                    # Close with profile cleanup
                    await browser_data['browser'].close_session()
                    
                    # Release profile if not persisting
                    allocated_profile = browser_data.get('allocated_profile')
                    if (allocated_profile and 
                        self.use_profiles and 
                        self.profile_manager):
                        try:
                            await self.profile_manager.release_profile(allocated_profile.profile_id)
                        except Exception as e:
                            logger.error(f"Error releasing profile during cleanup: {e}")
                    
                    total_cleaned += 1
                except Exception as e:
                    logger.error(f"Error cleaning up active browser {session_id}: {e}", exc_info=True)
            
            self._active_browsers.clear()
            
            # Reset local counter
            self._local_active_count = 0
            
            logger.info(f"✅ Cleaned up {total_cleaned} browsers, released {total_redis_resources_released} Redis resources from pool: {self.pool_id}")
            return total_cleaned
    
    async def get_pool_status(self) -> Dict:
        """
        Get current status of the browser pool.
        
        Returns:
            Dictionary with pool status information
        """
        async with self._lock:
            # Get Redis pool info
            redis_pool_info = {}
            try:
                redis_pool_info = await self.redis_client.get_pool_info(self.pool_key)
            except Exception as e:
                logger.error(f"Error getting Redis pool info: {e}")
                redis_pool_info = {'error': str(e)}
            
            # Get profile manager stats if available
            profile_stats = {}
            if self.use_profiles and self.profile_manager:
                try:
                    profile_stats = await self.profile_manager.get_stats()
                except Exception as e:
                    logger.error(f"Error getting profile stats: {e}")
                    profile_stats = {'error': str(e)}
            
            return {
                'pool_id': self.pool_id,
                'available_browsers': len(self._available_browsers),
                'active_browsers': len(self._active_browsers),
                'local_active_count': self._local_active_count,
                'keep_alive_enabled': self._keep_alive_on_release,
                'pool_active': self._pool_active,
                'max_concurrent': self.max_concurrent,
                'max_concurrent_local': self.max_concurrent_local,
                'effective_max_concurrent': self.effective_max_concurrent,
                'browser_ttl': self.browser_ttl,
                'use_profiles': self.use_profiles,
                'persist_profile': self.persist_profile,
                'redis_pool_info': redis_pool_info,
                'profile_stats': profile_stats
            }
    
    async def __aenter__(self) -> "ScrapelessBrowserPool":
        """
        Async context manager entry for pool-level management.
        Conditionally enables keep-alive behavior and starts cleanup task.
        """
        self._pool_active = True
        self._keep_alive_on_release = self.enable_keep_alive
        
        # Initialize profile manager if we own it
        if self.use_profiles and self.profile_manager and self._profile_manager_owned:
            try:
                # Open profile manager (this initializes it if needed)
                await self.profile_manager.open()
                logger.info(f"Profile manager initialized for pool: {self.pool_id}")
            except Exception as e:
                logger.error(f"Failed to initialize profile manager: {e}")
                # Continue without profiles if profile manager fails
                self.use_profiles = False
        
        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_browsers())
        
        logger.info(f"ScrapelessBrowserPool activated with keep-alive: {self.pool_id}")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit for pool-level management.
        Disables keep-alive and cleans up all browsers.
        """
        self._pool_active = False
        self._keep_alive_on_release = False
        
        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Clean up all browsers
        await self.cleanup_all_browsers()
        
        # Close profile manager if we own it
        if self.use_profiles and self.profile_manager and self._profile_manager_owned:
            try:
                await self.profile_manager.close()
                logger.info(f"Profile manager closed for pool: {self.pool_id}")
            except Exception as e:
                logger.error(f"Error closing profile manager: {e}")
        
        logger.info(f"ScrapelessBrowserPool deactivated and cleaned up: {self.pool_id}")


async def cleanup_scrapeless_redis_pool(redis_url: Optional[str] = None) -> bool:
    """
    Standalone utility function to force cleanup the Scrapeless browser Redis pool.
    
    This can be used for:
    - Server startup cleanup
    - Manual recovery from corrupted state
    - Test setup/teardown
    
    Args:
        redis_url: Optional Redis URL. If not provided, uses global settings.
        
    Returns:
        True if cleanup was successful, False otherwise
    """
    try:
        from redis_client.redis_client import AsyncRedisClient
        from global_config.settings import global_settings
        
        redis_client = AsyncRedisClient(redis_url or global_settings.REDIS_URL)
        pool_key = scraping_settings.SCRAPELESS_BROWSERS_POOL_KEY
        
        logger.warning(f"Force cleaning up Scrapeless Redis pool: {pool_key}")
        success = await redis_client.reset_pool(pool_key)
        
        if success:
            logger.info(f"✅ Successfully reset Scrapeless Redis pool: {pool_key}")
        else:
            logger.warning(f"❌ Failed to reset Scrapeless Redis pool: {pool_key}")
            
        return success
        
    except Exception as e:
        logger.error(f"Error during Scrapeless Redis pool cleanup: {e}", exc_info=True)
        return False


class ScrapelessBrowserContextManager:
    """
    Context manager for individual browser instances from the pool.
    
    This provides a convenient way to acquire and automatically release
    browsers from the pool with proper error handling and force close capability.
    """
    
    def __init__(
        self, 
        pool: ScrapelessBrowserPool, 
        timeout: Optional[int] = None,
        session_config: Optional[Dict] = None,
        force_close_on_error: bool = True,
        use_profiles: Optional[bool] = None,
        persist_profile: Optional[bool] = None,
        intercept_media: Optional[bool] = None,
        intercept_images: Optional[bool] = None
    ):
        """
        Initialize browser context manager.
        
        Args:
            pool: The ScrapelessBrowserPool to acquire from
            timeout: Timeout for browser acquisition
            session_config: Optional session configuration
            force_close_on_error: If True, force close browser when exceptions occur
            use_profiles: Override pool's profile usage setting (None = use pool setting)
            persist_profile: Override pool's profile persistence setting (None = use pool setting)
            intercept_media: Override media resource blocking setting (None = default True)
            intercept_images: Override image resource blocking setting (None = default True)
        """
        self.pool = pool
        self.timeout = timeout
        self.session_config = session_config or {}
        self.force_close_on_error = force_close_on_error
        
        # Profile settings - use provided overrides or inherit from pool
        self.use_profiles = use_profiles if use_profiles is not None else pool.use_profiles
        self.persist_profile = persist_profile if persist_profile is not None else pool.persist_profile
        
        # Resource blocking settings - use provided overrides or default to True
        self.intercept_media = intercept_media if intercept_media is not None else True
        self.intercept_images = intercept_images if intercept_images is not None else True
        
        # Update session config with profile preferences if not already set
        if 'use_profiles' not in self.session_config:
            self.session_config['use_profiles'] = self.use_profiles
        if 'persist_profile' not in self.session_config:
            self.session_config['persist_profile'] = self.persist_profile
        if 'intercept_media' not in self.session_config:
            self.session_config['intercept_media'] = self.intercept_media
        if 'intercept_images' not in self.session_config:
            self.session_config['intercept_images'] = self.intercept_images
        
        self.browser_data: Optional[Dict] = None
        self._force_close_requested = False
    
    async def force_close(self) -> bool:
        """
        Force close the current browser, bypassing normal release logic.
        
        This is useful when the browser encounters errors and should not
        be returned to the pool for reuse.
        
        Returns:
            True if browser was force closed successfully
        """
        if self.browser_data:
            self._force_close_requested = True
            return await self.pool.force_close_browser(self.browser_data)
        return False
    
    async def __aenter__(self) -> ScrapelessBrowser:
        """
        Acquire a browser from the pool.
        
        Returns:
            ScrapelessBrowser instance ready for use
            
        Raises:
            TimeoutError: If browser acquisition times out
            RuntimeError: If browser acquisition fails
        """
        self.browser_data = await self.pool.acquire_browser(
            timeout=self.timeout,
            session_config=self.session_config
        )
        
        if not self.browser_data:
            raise TimeoutError(f"Failed to acquire browser from pool within {self.timeout}s")
        
        return self.browser_data['browser']
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Release the browser back to the pool or force close on error.
        
        If an exception occurred and force_close_on_error is True,
        the browser will be force closed instead of returned to the pool.
        """
        if self.browser_data:
            # Check if we should force close due to exception or explicit request
            should_force_close = (
                self._force_close_requested or 
                (self.force_close_on_error and exc_type is not None)
            )
            
            if should_force_close:
                logger.info(f"Force closing browser due to {'explicit request' if self._force_close_requested else 'exception'}: {exc_type}")
                await self.pool.force_close_browser(self.browser_data)
            else:
                await self.pool.release_browser(self.browser_data)
            
            self.browser_data = None  
