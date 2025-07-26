import random
import json
import os
from workflow_service.services.scraping.settings import scraping_settings
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright, Page, BrowserContext, Browser, Request, Route
from typing import Optional, Dict, List, Set
import time
import uuid
from datetime import datetime
import logging
from dataclasses import dataclass

from workflow_service.services.scraping.browsers.config import DEFAULT_ENTITY_PREFIX, MAX_CONCURRENT_SCRAPELESS_BROWSERS, ACQUISITION_TIMEOUT
from workflow_service.services.scraping.settings import scraping_settings
from workflow_service.services.scraping.redis_sync_client import SyncRedisClient
from global_config.settings import global_settings

logger = logging.getLogger(__name__)


@dataclass
class ProfileData:
    """Simple profile data structure for sync version."""
    profile_id: str
    name: str
    created_at: str


class SimpleProfileManager:
    """
    Simple profile manager for sync version that reads cache and randomly selects profiles.
    
    This is a simplified version that:
    - Reads profile cache from disk once
    - Maintains profiles in memory  
    - Randomly selects profiles for allocation
    - No complex allocation tracking or Redis integration
    """
    
    def __init__(self, cache_file: str = "scrapeless_profiles_cache.json"):
        """
        Initialize simple profile manager.
        
        Args:
            cache_file: Profile cache file name (looked for in profiles/data directory)
        """
        # Locate cache file in profiles data directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        profiles_dir = os.path.join(current_dir, "data")
        self.cache_file = os.path.join(profiles_dir, cache_file)
        
        self.profiles: List[ProfileData] = []
        self._loaded = False
        
        logger.info(f"SimpleProfileManager initialized with cache: {self.cache_file}")
    
    def load_profiles(self) -> bool:
        """
        Load profiles from cache file.
        
        Returns:
            True if profiles loaded successfully, False otherwise
        """
        if self._loaded and self.profiles:
            logger.debug("Profiles already loaded")
            return True
            
        if not os.path.exists(self.cache_file):
            logger.warning(f"Profile cache file not found: {self.cache_file}")
            return False
        
        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            profile_dicts = cache_data.get("profiles", [])
            self.profiles = []
            
            for profile_dict in profile_dicts:
                profile = ProfileData(
                    profile_id=profile_dict.get("profile_id", ""),
                    name=profile_dict.get("name", ""),
                    created_at=profile_dict.get("created_at", "")
                )
                self.profiles.append(profile)
            
            self._loaded = True
            logger.info(f"Loaded {len(self.profiles)} profiles from cache")
            return True
            
        except Exception as e:
            logger.error(f"Error loading profiles from cache: {e}")
            return False
    
    def get_random_profile(self) -> Optional[ProfileData]:
        """
        Get a random profile from the loaded profiles.
        
        Returns:
            Random ProfileData if available, None otherwise
        """
        if not self._loaded:
            if not self.load_profiles():
                return None
        
        if not self.profiles:
            logger.warning("No profiles available")
            return None
        
        profile = random.choice(self.profiles)
        logger.debug(f"Selected random profile: {profile.name} (ID: {profile.profile_id[:8]}...)")
        return profile
    
    def get_profile_count(self) -> int:
        """Get number of loaded profiles."""
        return len(self.profiles)


class ScrapelessBrowserSync:
    """
    Synchronous version of ScrapelessBrowser using sync Playwright API.
    
    This is a simplified sync version that:
    - Uses sync Playwright API instead of async
    - Integrates with SimpleProfileManager for profile selection
    - Maintains core browser functionality
    - Removes complex async features like Redis integration
    """
    
    def __init__(
        self, 
        token: Optional[str] = None, 
        session_name: Optional[str] = None, 
        session_ttl: Optional[str] = None,
        persist_profile: bool = False,
        profile_id: Optional[str] = None,
        intercept_media: bool = True,
        intercept_images: bool = True,
        profile_manager: Optional[SimpleProfileManager] = None
    ):
        """
        Initialize a sync ScrapelessBrowser instance.
        
        Args:
            token: Scrapeless API token
            session_name: Name for the browser session
            session_ttl: Session time-to-live in seconds (default: 15 minutes)
            persist_profile: Whether to persist the browser profile
            profile_id: Specific profile ID to use (if None, will use random from profile manager)
            intercept_media: Whether to block media resources (video, audio, etc.)
            intercept_images: Whether to block image resources
            profile_manager: Optional profile manager (creates default if None)
        """
        self.token = token or scraping_settings.SCRAPELESS_API_KEY
        self.session_name = session_name or f"{DEFAULT_ENTITY_PREFIX}-{random.randint(100000, 999999)}"
        self.session_ttl = session_ttl or str(60 * 15)  # 15 minutes
        self.persist_profile = persist_profile
        self.profile_id = profile_id
        self.intercept_media = intercept_media
        self.intercept_images = intercept_images
        
        # Profile management
        self.profile_manager = profile_manager or SimpleProfileManager()
        self.selected_profile: Optional[ProfileData] = None
        
        # Browser state
        self.connection_url = None
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        logger.info(f"ScrapelessBrowserSync initialized: {self.session_name}")

    def _select_profile(self) -> Optional[str]:
        """
        Select a profile ID to use for the browser session.
        
        Returns:
            Profile ID to use, or None if no profile available
        """
        # Use explicitly provided profile ID if available
        if self.profile_id:
            logger.info(f"Using explicitly provided profile ID: {self.profile_id}")
            return self.profile_id
        
        # Try to get random profile from manager
        profile = self.profile_manager.get_random_profile()
        if profile:
            self.selected_profile = profile
            logger.info(f"Selected random profile: {profile.name} (ID: {profile.profile_id})")
            return profile.profile_id
        
        # No profile available
        logger.warning("No profile available - will create session without profile")
        return None

    def build_connection_url(
        self, 
        session_name: str, 
        session_ttl: str, 
        proxy_country: str = "US", 
        extension_ids: Optional[str] = None,
        profile_id: Optional[str] = None,
        profile_persist: bool = False
    ) -> str:
        """
        Build the connection URL for the Scrapeless session.

        Args:
            session_name: The name of the session
            session_ttl: seconds between 60 (1 minute) and 900 (15 minutes)
            proxy_country: The country of the proxy
            extension_ids: Comma separated list of extension IDs to use
            profile_id: Browser profile ID to use
            profile_persist: Whether to persist the profile after session ends

        Returns:
            The connection URL for the Scrapeless session
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
        logger.info(f"Connection URL built: {url}")
        return url

    def _setup_resource_blocking(self) -> None:
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
        
        def route_handler(route: Route, request: Request):
            """
            Route handler to block specific resource types.
            
            Args:
                route: Playwright route object
                request: Playwright request object
            """
            resource_type = request.resource_type
            
            if resource_type in blocked_types:
                # Block the request by aborting it
                route.abort()
                logger.debug(f"Blocked {resource_type} request: {request.url}")
            else:
                # Allow the request to continue
                route.continue_()
        
        try:
            # Set up route interception on the page context
            self.context.route("**/*", route_handler)
            logger.info(f"Resource blocking configured - Images: {self.intercept_images}, Media: {self.intercept_media}")
        except Exception as e:
            logger.error(f"Failed to set up resource blocking: {e}")
            # Don't raise the exception as this is not critical for basic functionality
    
    def start_session(
        self, 
        session_name: Optional[str] = None, 
        session_ttl: Optional[str] = None, 
        proxy_country: str = "US",
    ) -> str:
        """
        Start a Scrapeless session and initialize Playwright.
        
        Args:
            session_name: Optional session name override
            session_ttl: Optional session TTL override  
            proxy_country: Proxy country code
            
        Returns:
            Initial page URL
            
        Raises:
            Exception: If session startup fails
        """
        try:
            if not session_name:
                session_name = self.session_name
            if not session_ttl:
                session_ttl = self.session_ttl
                
            # Select profile to use
            profile_id_to_use = self._select_profile()
                        
            self.connection_url = self.build_connection_url(
                session_name, 
                session_ttl, 
                proxy_country,
                profile_id=profile_id_to_use,
                profile_persist=self.persist_profile
            )
            
            # Initialize sync Playwright
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.connect_over_cdp(self.connection_url)
            self.context = self.browser.contexts[0]
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            
            # Set up resource blocking if intercept options are enabled
            self._setup_resource_blocking()
            
            logger.info(f"Connected to Scrapeless session: {self.connection_url}")
            return self.page.url
            
        except Exception as e:
            logger.error(f"Failed to start Scrapeless session: {e}")
            raise Exception(f"Failed to start Scrapeless session: {e}")
    
    def get_live_url(self) -> Optional[Dict]:
        """
        Get the live URL for the current session.
        
        Returns:
            Live URL data if successful, None otherwise
        """
        if not self.page or not self.context:
            logger.error("Browser session not initialized")
            return None
            
        try:
            # Navigate to a test page first
            self.page.goto("https://www.wikipedia.org", timeout=60000, wait_until="load")
            
            # Create CDP session using Playwright's sync API
            client = self.context.new_cdp_session(self.page)
            try:
                # Send the CDP command
                result = client.send('Agent.liveURL')
                return result
            finally:
                # Clean up CDP session
                pass
                
        except Exception as e:
            logger.error(f"Error getting live URL: {e}")
            return None
    
    def close_session(self) -> None:
        """
        Close the Scrapeless session and release resources.
        """
        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            
            logger.info("Scrapeless session closed successfully")
            
        except Exception as e:
            logger.error(f"Error closing session: {e}")
        finally:
            # Reset state
            self.browser = None
            self.context = None
            self.page = None
            self.connection_url = None
            self.playwright = None
            self.selected_profile = None
    
    def __enter__(self) -> "ScrapelessBrowserSync":
        """Enable use as a sync context manager, performing start_session."""
        self.start_session()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close the session when exiting the context."""
        self.close_session()


class ScrapelessBrowserPoolSync:
    """
    Synchronous browser pool for ScrapelessBrowserSync instances with Redis-based global concurrency.
    
    This sync version provides:
    - Global concurrency limits via Redis resource tracking
    - In-memory browser pooling for reuse
    - Configurable keep-alive behavior for browsers
    - Timeout support for resource acquisition
    - Manual cleanup functionality
    - Force close mechanism for error recovery
    - Local concurrency limiting
    
    Features:
    - Respects MAX_CONCURRENT_SCRAPELESS_BROWSERS limit globally across all processes
    - Maintains a pool of active browsers in memory for reuse
    - Uses Redis for distributed resource counting and locking
    - Provides comprehensive error handling and cleanup
    """
    
    def __init__(
        self, 
        redis_client: Optional[SyncRedisClient] = None,
        max_concurrent: int = MAX_CONCURRENT_SCRAPELESS_BROWSERS,
        max_concurrent_local: Optional[int] = None,  # Pool-specific limit
        acquisition_timeout: int = ACQUISITION_TIMEOUT,
        browser_ttl: int = 900,  # 15 minutes default TTL for browsers
        pool_id: Optional[str] = None,
        profile_manager: Optional[SimpleProfileManager] = None,
        enable_keep_alive: bool = True  # Control keep-alive behavior
    ):
        """
        Initialize sync browser pool with Redis-based concurrency management.
        
        Args:
            redis_client: Optional Redis client for resource management
            max_concurrent: Maximum concurrent browsers allowed globally via Redis
            max_concurrent_local: Optional pool-specific concurrency limit (overrides global if lower)
            acquisition_timeout: Timeout in seconds for acquiring browser resources
            browser_ttl: Time-to-live for browsers in the pool (seconds)
            pool_id: Optional unique identifier for this pool instance
            profile_manager: Optional profile manager (creates default if None)
            enable_keep_alive: Whether to enable keep-alive behavior in context manager (default: True)
        """
        self.redis_client = redis_client or SyncRedisClient(global_settings.REDIS_URL)
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
        self.profile_manager = profile_manager or SimpleProfileManager()
        self.enable_keep_alive = enable_keep_alive
        
        # Redis pool key for resource management
        self.pool_key = scraping_settings.SCRAPELESS_BROWSERS_POOL_KEY
        
        # Browser pool storage with metadata
        self.available_browsers: List[Dict] = []  # Available browsers ready for use
        self.active_browsers: Dict[str, Dict] = {}  # Currently active browsers by session_id
        self._browser_metadata: Dict[str, Dict] = {}  # Metadata for tracking browsers
        
        # Local concurrency tracking
        self._local_active_count: int = 0  # Track local active browsers for artificial limiting
        
        # Pool configuration
        self._keep_alive_on_release = False  # Will be set by pool context manager
        self._pool_active = False
        
        # Thread safety
        import threading
        self._lock = threading.Lock()  # For thread-safe pool operations
        
        logger.info(
            f"ScrapelessBrowserPoolSync initialized: {self.pool_id}, "
            f"max_concurrent={max_concurrent}, effective_max={self.effective_max_concurrent}, "
            f"enable_keep_alive={enable_keep_alive}"
        )
    
    def _acquire_redis_resource(self) -> Optional[str]:
        """
        Acquire a resource slot from Redis pool.
        
        Returns:
            Allocation ID if resource was acquired, None if failed
        """
        try:
            # Use the pool-based resource management
            allocation_id, current_usage, success = self.redis_client.acquire_from_pool(
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
    
    def _release_redis_resource(self, allocation_id: str) -> bool:
        """
        Release a resource slot back to Redis pool.
        
        Args:
            allocation_id: The allocation ID returned from _acquire_redis_resource
            
        Returns:
            True if resource was released successfully
        """
        try:
            released_count, current_usage, success = self.redis_client.release_to_pool(
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
    
    def _create_new_browser(self, session_config: Optional[Dict] = None) -> Dict:
        """
        Create a new ScrapelessBrowserSync instance with metadata.
        
        Args:
            session_config: Optional configuration for the browser session
            
        Returns:
            Dictionary containing browser instance and metadata
        """
        session_config = session_config or {}
        
        # Create browser instance
        browser = ScrapelessBrowserSync(
            session_name=session_config.get('session_name'),
            session_ttl=session_config.get('session_ttl'),
            persist_profile=session_config.get('persist_profile', False),
            profile_id=session_config.get('profile_id'),
            intercept_media=session_config.get('intercept_media', True),
            intercept_images=session_config.get('intercept_images', True),
            profile_manager=self.profile_manager
        )
        
        # Start the browser session
        browser.start_session(
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
        }
        
        logger.info(f"🌐 Created new browser: {session_id}")
        return metadata
    
    def _check_browser_expired(self, browser_data: Dict) -> bool:
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
    
    def _cleanup_expired_browser(self, browser_data: Dict) -> None:
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
                self._release_redis_resource(allocation_id)
            except Exception as e:
                logger.error(f"Failed to release Redis resource during cleanup for {session_id}: {e}")
        
        try:
            # Close browser session
            browser_data['browser'].close_session()
            
            # Decrement local counter if this was an active browser
            if browser_data['session_id'] in self.active_browsers:
                self._local_active_count = max(0, self._local_active_count - 1)
            logger.info(f"✅ Successfully cleaned up expired browser: {session_id}")
        except Exception as e:
            logger.error(f"Error cleaning up expired browser {session_id}: {e}", exc_info=True)
    
    def acquire_browser(
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
            with self._lock:
                # First, clean up any expired browsers from available pool
                expired_browsers = []
                for browser_data in self.available_browsers[:]:
                    if self._check_browser_expired(browser_data):
                        expired_browsers.append(browser_data)
                        self.available_browsers.remove(browser_data)
                
                # Clean up expired browsers
                for browser_data in expired_browsers:
                    self._cleanup_expired_browser(browser_data)
                
                # Try to get a valid available browser from pool
                if self.available_browsers:
                    browser_data = self.available_browsers.pop()
                    browser_data['last_used'] = datetime.now()
                    browser_data['use_count'] += 1
                    self.active_browsers[browser_data['session_id']] = browser_data
                    self._local_active_count += 1
                    logger.info(f"♻️ Reused browser from pool: {browser_data['session_id']}")
                    return browser_data
                
                # Check local concurrency limit before attempting to create new browser
                if self._local_active_count >= self.effective_max_concurrent:
                    logger.debug(f"Local concurrency limit reached: {self._local_active_count}/{self.effective_max_concurrent}")
                    # Continue to retry loop, don't try to create new browser
                    time.sleep(0.5)
                    continue
                
                # Reserve a slot for the new browser we're about to create
                # This prevents race conditions where multiple threads might think they can create browsers
                self._local_active_count += 1
            
            # Now try to create a new browser outside the lock (allows parallel creation)
            try:
                # Acquire Redis resource (operation outside lock)
                allocation_id = self._acquire_redis_resource()
                if not allocation_id:
                    # Failed to get Redis resource, release the local slot
                    with self._lock:
                        self._local_active_count = max(0, self._local_active_count - 1)
                    time.sleep(0.5)
                    continue
                
                # Create browser (operation outside lock)
                try:
                    browser_data = self._create_new_browser(session_config)
                    browser_data['redis_allocation_id'] = allocation_id
                    browser_data['use_count'] = 1
                    
                    # Add to active browsers (quick operation, hold lock)
                    with self._lock:
                        self.active_browsers[browser_data['session_id']] = browser_data
                    
                    return browser_data
                    
                except Exception as e:
                    # Browser creation failed, cleanup
                    logger.error(f"❌ Failed to create new browser: {e}", exc_info=True)
                    self._release_redis_resource(allocation_id)
                    # Release the local slot we reserved
                    with self._lock:
                        self._local_active_count = max(0, self._local_active_count - 1)
                    # Continue to retry
                    
            except Exception as e:
                # Unexpected error, release the local slot
                logger.error(f"Unexpected error during browser acquisition: {e}", exc_info=True)
                with self._lock:
                    self._local_active_count = max(0, self._local_active_count - 1)
            
            # Wait a bit before retrying
            time.sleep(0.5)
        
        logger.warning(f"Browser acquisition timed out after {timeout}s")
        return None
    
    def release_browser(self, browser_data: Dict) -> bool:
        """
        Release a browser back to the pool or close it.
        
        Args:
            browser_data: Browser metadata dict returned from acquire_browser
            
        Returns:
            True if browser was released successfully
        """
        session_id = browser_data['session_id']
        allocation_id = browser_data.get('redis_allocation_id')
        
        with self._lock:
            # Check if browser is expired
            is_expired = self._check_browser_expired(browser_data)
            
            # Remove from active browsers
            if session_id in self.active_browsers:
                del self.active_browsers[session_id]
                self._local_active_count = max(0, self._local_active_count - 1)
            
            # Check if we should keep the browser alive
            if (self._keep_alive_on_release and 
                self._pool_active and 
                not is_expired):
                # Add back to available pool
                browser_data['last_used'] = datetime.now()
                self.available_browsers.append(browser_data)
                logger.debug(f"Browser returned to pool: {session_id}")
                return True
            else:
                # Close the browser and release all resources
                try:
                    # Close browser session
                    browser_data['browser'].close_session()
                    
                    # Release Redis resource if allocation ID exists
                    if allocation_id:
                        self._release_redis_resource(allocation_id)
                    
                    if is_expired:
                        logger.debug(f"Browser closed due to expiration: {session_id}")
                    else:
                        logger.debug(f"Browser closed and resource released: {session_id}")
                    return True
                except Exception as e:
                    logger.error(f"Error closing browser {session_id}: {e}")
                    # Still try to release resources even if browser close failed
                    if allocation_id:
                        self._release_redis_resource(allocation_id)
                    return False
    
    def force_close_browser(self, browser_data: Dict) -> bool:
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
        
        with self._lock:
            # Remove from both active and available browsers
            if session_id in self.active_browsers:
                del self.active_browsers[session_id]
                self._local_active_count = max(0, self._local_active_count - 1)
            
            # Remove from available browsers if present
            self.available_browsers = [
                b for b in self.available_browsers 
                if b['session_id'] != session_id
            ]
            
            # Force close the browser and release all resources
            try:
                # Force close browser session
                browser_data['browser'].close_session()
                
                # Release Redis resource if allocation ID exists
                if allocation_id:
                    self._release_redis_resource(allocation_id)
                
                logger.info(f"Browser force closed: {session_id}")
                return True
            except Exception as e:
                logger.error(f"Error force closing browser {session_id}: {e}")
                # Still release resources even if browser close failed
                if allocation_id:
                    self._release_redis_resource(allocation_id)
                return False
    
    def cleanup_all_browsers(self) -> int:
        """
        Manually clean up all browsers in the pool.
        
        Returns:
            Number of browsers cleaned up
        """
        logger.info(f"🧹 Starting cleanup of all browsers in pool: {self.pool_id}")
        
        with self._lock:
            total_cleaned = 0
            total_redis_resources_released = 0
            
            # Close all available browsers
            for browser_data in self.available_browsers[:]:
                session_id = browser_data.get('session_id', 'unknown')
                allocation_id = browser_data.get('redis_allocation_id')
                
                # Always try to release Redis resource first
                if allocation_id:
                    try:
                        self._release_redis_resource(allocation_id)
                        total_redis_resources_released += 1
                    except Exception as e:
                        logger.error(f"Failed to release Redis resource for {session_id}: {e}")
                
                try:
                    # Close browser
                    browser_data['browser'].close_session()
                    total_cleaned += 1
                except Exception as e:
                    logger.error(f"Error cleaning up browser {session_id}: {e}", exc_info=True)
            
            self.available_browsers.clear()
            
            # Close all active browsers (force cleanup)
            for browser_data in list(self.active_browsers.values()):
                session_id = browser_data.get('session_id', 'unknown')
                allocation_id = browser_data.get('redis_allocation_id')
                
                # Always try to release Redis resource first
                if allocation_id:
                    try:
                        self._release_redis_resource(allocation_id)
                        total_redis_resources_released += 1
                    except Exception as e:
                        logger.error(f"Failed to release Redis resource for active browser {session_id}: {e}")
                
                try:
                    # Close browser
                    browser_data['browser'].close_session()
                    total_cleaned += 1
                except Exception as e:
                    logger.error(f"Error cleaning up active browser {session_id}: {e}", exc_info=True)
            
            self.active_browsers.clear()
            
            # Reset local counter
            self._local_active_count = 0
            
            logger.info(f"✅ Cleaned up {total_cleaned} browsers, released {total_redis_resources_released} Redis resources from pool: {self.pool_id}")
            return total_cleaned
    
    def force_cleanup_redis_pool(self) -> bool:
        """
        Force cleanup the Redis pool by resetting all allocations.
        
        WARNING: This will clear ALL allocations for this pool across ALL processes.
        Use this only when the pool is in a corrupted state and needs recovery.
        
        Returns:
            True if pool was successfully reset, False otherwise
        """
        try:
            logger.warning(f"Force cleaning up Redis pool: {self.pool_key}")
            success = self.redis_client.reset_pool(self.pool_key)
            if success:
                logger.info(f"Successfully reset Redis pool: {self.pool_key}")
            else:
                logger.warning(f"Failed to reset Redis pool: {self.pool_key}")
            return success
        except Exception as e:
            logger.error(f"Error force cleaning up Redis pool {self.pool_key}: {e}")
            return False
    
    def get_pool_status(self) -> Dict:
        """
        Get current status of the browser pool.
        
        Returns:
            Dictionary with pool status information
        """
        with self._lock:
            # Get Redis pool info
            redis_pool_info = {}
            try:
                redis_pool_info = self.redis_client.get_pool_info(self.pool_key)
            except Exception as e:
                logger.error(f"Error getting Redis pool info: {e}")
                redis_pool_info = {'error': str(e)}
            
            return {
                'pool_id': self.pool_id,
                'available_browsers': len(self.available_browsers),
                'active_browsers': len(self.active_browsers),
                'local_active_count': self._local_active_count,
                'keep_alive_enabled': self._keep_alive_on_release,
                'pool_active': self._pool_active,
                'max_concurrent': self.max_concurrent,
                'max_concurrent_local': self.max_concurrent_local,
                'effective_max_concurrent': self.effective_max_concurrent,
                'browser_ttl': self.browser_ttl,
                'redis_pool_info': redis_pool_info,
                'profile_count': self.profile_manager.get_profile_count()
            }
    
    def __enter__(self) -> "ScrapelessBrowserPoolSync":
        """
        Context manager entry for pool-level management.
        Conditionally enables keep-alive behavior and activates the pool.
        """
        self._pool_active = True
        self._keep_alive_on_release = self.enable_keep_alive
        
        logger.info(f"ScrapelessBrowserPoolSync activated with keep-alive: {self.pool_id}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Context manager exit for pool-level management.
        Disables keep-alive and cleans up all browsers.
        """
        self._pool_active = False
        self._keep_alive_on_release = False
        
        # Clean up all browsers
        self.cleanup_all_browsers()
        
        logger.info(f"ScrapelessBrowserPoolSync deactivated and cleaned up: {self.pool_id}")


class ScrapelessBrowserContextManagerSync:
    """
    Sync context manager for individual browser instances from the pool.
    
    This provides a convenient way to acquire and automatically release
    browsers from the pool with proper error handling and force close capability.
    
    Similar to the async version but uses sync operations and ScrapelessBrowserPoolSync.
    """
    
    def __init__(
        self, 
        pool: ScrapelessBrowserPoolSync, 
        timeout: Optional[int] = None,
        session_config: Optional[Dict] = None,
        force_close_on_error: bool = True,
        persist_profile: Optional[bool] = None,
        intercept_media: Optional[bool] = None,
        intercept_images: Optional[bool] = None,
        proxy_country: Optional[str] = None
    ):
        """
        Initialize browser context manager for sync usage.
        
        Args:
            pool: The ScrapelessBrowserPoolSync to acquire from
            timeout: Timeout for browser acquisition (not implemented in simple pool)
            session_config: Optional session configuration (not used in simple sync version)
            force_close_on_error: If True, force close browser when exceptions occur
            persist_profile: Override profile persistence setting (passed to browser)
            intercept_media: Override media resource blocking setting
            intercept_images: Override image resource blocking setting
            proxy_country: Override proxy country setting
        """
        self.pool = pool
        self.timeout = timeout
        self.session_config = session_config or {}
        self.force_close_on_error = force_close_on_error
        
        # Browser configuration overrides
        self.persist_profile = persist_profile
        self.intercept_media = intercept_media
        self.intercept_images = intercept_images
        self.proxy_country = proxy_country or "US"
        
        # Internal state
        self.browser_data: Optional[Dict] = None
        self._force_close_requested = False
        
        logger.debug(f"ScrapelessBrowserContextManagerSync initialized with force_close_on_error={force_close_on_error}")
    
    def force_close(self) -> bool:
        """
        Force close the current browser, bypassing normal release logic.
        
        This is useful when the browser encounters errors and should not
        be returned to the pool for reuse.
        
        Returns:
            True if browser was force closed successfully
        """
        if self.browser_data:
            self._force_close_requested = True
            return self.pool.force_close_browser(self.browser_data)
        return False
    
    def __enter__(self) -> ScrapelessBrowserSync:
        """
        Acquire a browser from the pool.
        
        Returns:
            ScrapelessBrowserSync instance ready for use
            
        Raises:
            RuntimeError: If browser acquisition fails
        """
        self.browser_data = self.pool.acquire_browser(
            timeout=self.timeout,
            session_config=self.session_config
        )
        
        if not self.browser_data:
            raise RuntimeError(f"Failed to acquire browser from pool within {self.timeout}s")
        
        browser = self.browser_data['browser']
        
        # Apply configuration overrides if specified
        try:
            # Update browser configuration if overrides provided
            if self.persist_profile is not None:
                browser.persist_profile = self.persist_profile
            if self.intercept_media is not None:
                browser.intercept_media = self.intercept_media
            if self.intercept_images is not None:
                browser.intercept_images = self.intercept_images
            
            logger.debug(f"Acquired browser from pool: {browser.session_name}")
            return browser
            
        except Exception as e:
            # If configuration failed, release browser back to pool
            logger.error(f"Error configuring acquired browser: {e}")
            if self.browser_data:
                self.pool.release_browser(self.browser_data)
                self.browser_data = None
            raise RuntimeError(f"Failed to configure acquired browser: {e}")
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
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
                reason = 'explicit request' if self._force_close_requested else f'exception: {exc_type.__name__}'
                logger.info(f"Force closing browser due to {reason}")
                self.force_close()
            else:
                # Normal release back to pool
                try:
                    success = self.pool.release_browser(self.browser_data)
                    if success:
                        logger.debug(f"Released browser back to pool: {self.browser_data['session_id']}")
                    else:
                        logger.warning(f"Failed to release browser to pool: {self.browser_data['session_id']}")
                except Exception as e:
                    logger.error(f"Error releasing browser to pool: {e}")
                    # Force close as fallback if normal release fails
                    try:
                        self.browser_data['browser'].close_session()
                    except Exception as close_error:
                        logger.error(f"Error force closing browser after release failure: {close_error}")
            
            self.browser_data = None




def cleanup_scrapeless_redis_pool_sync(redis_url: Optional[str] = None) -> bool:
    """
    Standalone utility function to force cleanup the Scrapeless browser Redis pool (sync version).
    
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
        from workflow_service.services.scraping.redis_sync_client import SyncRedisClient
        from global_config.settings import global_settings
        
        redis_client = SyncRedisClient(redis_url or global_settings.REDIS_URL)
        pool_key = scraping_settings.SCRAPELESS_BROWSERS_POOL_KEY
        
        logger.warning(f"Force cleaning up Scrapeless Redis pool: {pool_key}")
        success = redis_client.reset_pool(pool_key)
        
        if success:
            logger.info(f"✅ Successfully reset Scrapeless Redis pool: {pool_key}")
        else:
            logger.warning(f"❌ Failed to reset Scrapeless Redis pool: {pool_key}")
            
        return success
        
    except Exception as e:
        logger.error(f"Error during Scrapeless Redis pool cleanup: {e}", exc_info=True)
        return False
    
    

# Example usage
if __name__ == "__main__":
    def example_single_browser():
        """Example of using a single sync browser."""
        print("=== Single Browser Example ===")
        
        # Create and use browser with automatic profile selection
        with ScrapelessBrowserSync() as browser:
            print(f"Browser started with session: {browser.session_name}")
            if browser.selected_profile:
                print(f"Using profile: {browser.selected_profile.name}")
            
            # Use the browser for scraping
            if browser.page:
                browser.page.goto("https://example.com")
                title = browser.page.title()
                print(f"Page title: {title}")
        
        print("Browser automatically closed")
    
    def example_browser_pool():
        """Example of using sync browser pool."""
        print("\n=== Browser Pool Example ===")
        
        with ScrapelessBrowserPoolSync() as pool:
            print(f"Pool status: {pool.get_pool_status()}")
            
            # Acquire browsers
            browser_data1 = pool.acquire_browser()
            browser_data2 = pool.acquire_browser()
            
            if browser_data1 and browser_data2:
                print("Acquired 2 browsers from pool")
                
                # Use browsers...
                browser1 = browser_data1['browser']
                browser2 = browser_data2['browser']
                
                if browser1.page:
                    browser1.page.goto("https://example.com")
                if browser2.page:
                    browser2.page.goto("https://httpbin.org")
                
                # Release browsers back to pool
                pool.release_browser(browser_data1)
                pool.release_browser(browser_data2)
                print("Released browsers back to pool")
            
            print(f"Final pool status: {pool.get_pool_status()}")
        
        print("Pool automatically cleaned up")
    
    def example_context_manager():
        """Example of using sync browser context manager."""
        print("\n=== Context Manager Example ===")
        
        with ScrapelessBrowserPoolSync() as pool:
            print(f"Initial pool status: {pool.get_pool_status()}")
            
            # Use context manager for automatic acquisition and release
            with ScrapelessBrowserContextManagerSync(pool, force_close_on_error=True) as browser:
                print(f"Acquired browser: {browser.session_name}")
                if browser.selected_profile:
                    print(f"Using profile: {browser.selected_profile.name}")
                
                # Use the browser for scraping
                if browser.page:
                    browser.page.goto("https://example.com")
                    title = browser.page.title()
                    print(f"Page title: {title}")
                
                # Browser automatically released when exiting context
            
            print("Browser automatically released")
            print(f"Final pool status: {pool.get_pool_status()}")
        
        print("Pool automatically cleaned up")
    
    def example_context_manager_with_error():
        """Example showing error handling with context manager."""
        print("\n=== Context Manager Error Handling Example ===")
        
        with ScrapelessBrowserPoolSync() as pool:
            try:
                with ScrapelessBrowserContextManagerSync(
                    pool, 
                    force_close_on_error=True,
                    intercept_images=True,
                    intercept_media=True
                ) as browser:
                    print(f"Acquired browser: {browser.session_name}")
                    
                    # Simulate an error
                    raise ValueError("Simulated scraping error")
                    
            except ValueError as e:
                print(f"Caught expected error: {e}")
                print("Browser was force closed due to error")
            
            print(f"Pool status after error: {pool.get_pool_status()}")
        
        print("Pool cleaned up after error handling")
    
    def example_manual_force_close():
        """Example of manually force closing a browser."""
        print("\n=== Manual Force Close Example ===")
        
        with ScrapelessBrowserPoolSync() as pool:
            context_manager = ScrapelessBrowserContextManagerSync(pool)
            
            with context_manager as browser:
                print(f"Acquired browser: {browser.session_name}")
                
                # Simulate detecting a problematic condition
                if True:  # Simulate condition
                    print("Detected problem, force closing browser")
                    context_manager.force_close()
                    print("Browser force closed manually")
            
            print(f"Pool status after manual force close: {pool.get_pool_status()}")
        
        print("Pool cleaned up")

    example_context_manager()
    
    # Run examples (commented out to avoid actual browser creation)
    print("Sync ScrapelessBrowser examples:")
    print("1. Single browser: example_single_browser()")
    print("2. Browser pool: example_browser_pool()")
    print("3. Context manager: example_context_manager()")
    print("4. Error handling: example_context_manager_with_error()")
    print("5. Manual force close: example_manual_force_close()")
    print("\nUncomment the example calls below to run them:")
    print("# example_single_browser()")
    print("# example_browser_pool()")
    print("# example_context_manager()")
    print("# example_context_manager_with_error()")
    print("# example_manual_force_close()")
