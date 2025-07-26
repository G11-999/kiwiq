"""
Scrapeless Browser Profile Manager

This module provides comprehensive management of Scrapeless browser profiles including:
- Profile creation, deletion, and retrieval
- Local JSON persistence of profile data
- Thread-safe in-memory allocation manager with priority queue
- Automatic profile pool management and load balancing

Key Features:
- Creates configured number of concurrent profiles
- Maintains local cache of profile metadata
- Thread-safe allocation/deallocation
- Priority-based allocation (least used profiles first)
- Automatic profile pool reset and recreation

Author: Generated for KiwiQ Backend
"""

import json
import os
import threading
import time
import asyncio
import random
from collections import defaultdict
from heapq import heappush, heappop
from typing import Dict, List, Tuple, Any, Optional
from urllib.parse import urlencode
from dataclasses import dataclass, asdict
from datetime import datetime

from global_config.settings import global_settings

import requests

from workflow_service.services.scraping.browsers.config import (
    DEFAULT_ENTITY_PREFIX, 
    DEFAULT_CONCURRENT_PROFILES
)
from workflow_service.services.scraping.settings import scraping_settings

# Import Redis client for multi-processing safe cache operations
from redis_client.redis_client import AsyncRedisClient

# Import browser automation for fallback profile creation


@dataclass
class ProfileData:
    """
    Data class representing a Scrapeless browser profile with asymmetrical penalty system.
    
    Attributes:
        profile_id: Unique identifier for the profile
        name: Human-readable name of the profile
        created_at: Timestamp when profile was created
        penalty_score: Asymmetrical penalty score for allocation priority (lower = higher priority)
        actual_allocations: Current number of active allocations (for safeguard against over-releasing)
        total_allocations: Total lifetime allocations (for statistics)
    """
    profile_id: str
    name: str
    created_at: str
    penalty_score: int = 0
    actual_allocations: int = 0
    total_allocations: int = 0


class ScrapelessAPIClient:
    """
    Low-level API client for Scrapeless browser profile operations with browser automation fallback.
    
    Handles direct communication with Scrapeless API including:
    - Authentication management
    - Profile CRUD operations
    - Error handling and retries
    - Response parsing
    - Browser automation fallback when API fails
    
    Key Features:
    - Primary method: API-based profile creation (fast, headless)
    - Fallback method: Browser automation (slower, requires user interaction, but more reliable)
    - Automatic fallback when API fails
    - Caches browser session for multiple profile creations
    """
    
    def __init__(self, use_browser_fallback: bool = True):
        """
        Initialize API client with configuration from settings.
        
        Args:
            use_browser_fallback: Whether to use browser automation as fallback when API fails
        """
        
        # Validate API key is present and not empty (allow empty for browser-only mode)
        api_key = scraping_settings.SCRAPELESS_API_KEY
        self.has_api_key = bool(api_key and api_key.strip())
        
        if self.has_api_key:
            self.api_config = {
                "host": "https://api.scrapeless.com",
                "headers": {
                    "x-api-token": api_key.strip(),
                    "Content-Type": "application/json"
                }
            }
            print(f"🔑 API Client initialized with key: {api_key[:8]}...{api_key[-4:] if len(api_key) > 12 else '***'}")
        else:
            self.api_config = None
            print("⚠️ No API key found - will use browser automation only")
        
        # Browser automation configuration
        self.use_browser_fallback = use_browser_fallback
        from workflow_service.services.scraping.browsers.scrapeless.scrapeless_browser import ScrapelessBrowser
        from workflow_service.services.scraping.browsers.actors.scrapeless_logged_in_browser_actor import ScrapelessLoggedInBrowserActor
        self._browser_session: Optional[ScrapelessBrowser] = None
        self._browser_actor: Optional[ScrapelessLoggedInBrowserActor] = None
        self._browser_logged_in = False
        
        print(f"🔧 Browser fallback {'enabled' if use_browser_fallback else 'disabled'}")
    
    async def _ensure_browser_session(self) -> bool:
        """
        Ensure browser session is initialized and user is logged in.
        
        This method:
        1. Creates browser session if not exists
        2. Handles user login flow if not already logged in
        3. Navigates to profile management page
        
        Returns:
            True if browser session ready, False if failed
            
        Note:
            This method will trigger manual login flow with ipdb.set_trace() on first use
        """
        try:
            if self._browser_session is None:
                print("🔄 Initializing browser session for profile creation...")
                from workflow_service.services.scraping.browsers.scrapeless.scrapeless_browser import ScrapelessBrowser
                from workflow_service.services.scraping.browsers.actors.scrapeless_logged_in_browser_actor import ScrapelessLoggedInBrowserActor
                self._browser_session = ScrapelessBrowser(profile_id="39fd01df-7bf9-44b5-befb-4ea5d238caf8", persist_profile=True)
                await self._browser_session.start_session()
                
                self._browser_actor = ScrapelessLoggedInBrowserActor(
                    browser=self._browser_session.browser,
                    context=self._browser_session.context,
                    page=self._browser_session.page,
                    live_url=self._browser_session.get_live_url()
                )
                print("✅ Browser session initialized")
            
            if not self._browser_logged_in:
                print("🔐 Starting browser login flow...")
                await self._browser_actor.wait_for_manual_login()
                self._browser_logged_in = True
                print("✅ Browser session logged in and ready")
            
            return True
            
        except Exception as e:
            print(f"❌ Error ensuring browser session: {e}")
            await self._cleanup_browser_session()
            return False
    
    async def _cleanup_browser_session(self) -> None:
        """
        Clean up browser session resources.
        
        Properly closes browser session and resets internal state.
        """
        try:
            if self._browser_session:
                await self._browser_session.close_session()
                self._browser_session = None
                self._browser_actor = None
                self._browser_logged_in = False
                print("🧹 Browser session cleaned up")
        except Exception as e:
            print(f"⚠️ Error during browser cleanup: {e}")
    
    async def create_profile_via_browser(self, name: str) -> Dict[str, Any] | None:
        """
        Create profile using browser automation instead of API.
        
        This method:
        1. Ensures browser session is ready (handles login if needed)
        2. Uses browser automation to create profile via UI
        3. Returns profile data in API-compatible format
        
        Args:
            name: Name for the new profile
            
        Returns:
            Profile data dict if successful, None if failed
            
        Note:
            First call will trigger manual login flow with ipdb.set_trace()
        """
        try:
            print(f"🌐 Creating profile via browser automation: {name}")
            
            # Ensure browser session is ready
            if not await self._ensure_browser_session():
                print("❌ Failed to ensure browser session for profile creation")
                return None
            
            # Create profile using browser automation
            result = await self._browser_actor.create_profile_automatically(name)
            
            if result and result.get("success"):
                print(f"✅ Profile created successfully via browser: {name}")
                
                # Extract actual profile ID from browser automation result
                actual_profile_id = result.get("profile_id")
                
                if actual_profile_id:
                    print(f"   - Extracted actual profile ID: {actual_profile_id}")
                    profile_id = actual_profile_id
                else:
                    print(f"   - No profile ID extracted, using fallback ID")
                    # Fallback to generated ID if extraction failed
                    profile_id = f"browser_created_{name}_{int(time.time())}"
                
                # Return API-compatible format with actual or fallback profile ID
                return {
                    "id": profile_id,
                    "name": name,
                    "created_via": "browser_automation",
                    "creation_timestamp": datetime.now().isoformat(),
                    "browser_result": result,
                    "actual_profile_id_extracted": bool(actual_profile_id)
                }
            else:
                error_msg = result.get("message", "Unknown error") if result else "No result returned"
                print(f"❌ Browser profile creation failed: {error_msg}")
                return None
                
        except Exception as e:
            print(f"❌ Error creating profile via browser: {e}")
            # Cleanup browser session on error
            await self._cleanup_browser_session()
            return None
    
    # def test_connection(self) -> bool:
    #     """
    #     Test API connectivity and authentication.
        
    #     Returns:
    #         True if connection successful, False otherwise
    #     """
    #     try:
    #         print("🔍 Testing API connection...")
    #         response = self.get_profiles(page=1, page_size=1)
    #         if response is not None:
    #             print("✅ API connection test successful")
    #             return True
    #         else:
    #             print("❌ API connection test failed")
    #             return False
    #     except Exception as e:
    #         print(f"❌ API connection test failed: {e}")
    #         return False
    
    async def create_profile(self, name: str, timeout: int = 30, force_browser: bool = False) -> Dict[str, Any] | None:
        """
        Create a new browser profile via Scrapeless API with browser automation fallback.
        
        This method tries multiple approaches in order:
        1. API-based creation (if API key available and not forced to use browser)
        2. Browser automation fallback (if enabled and API fails or is forced)
        
        Args:
            name: Name for the new profile
            timeout: Request timeout in seconds for API calls
            force_browser: If True, skip API and use browser automation directly
            
        Returns:
            Profile data dict if successful, None if failed
            
        Note:
            Browser automation fallback will trigger manual login with ipdb.set_trace() on first use
        """
        
        # Try API first (unless forced to use browser or no API key)
        if not force_browser and self.has_api_key and self.api_config:
            api_result = await self._create_profile_via_api(name, timeout)
            if api_result is not None:
                return api_result
            
            print(f"⚠️ API profile creation failed for '{name}', attempting browser fallback...")
        
        # Fallback to browser automation if enabled
        if self.use_browser_fallback:
            if not self.has_api_key:
                print(f"🌐 No API key available, using browser automation for '{name}'")
            elif force_browser:
                print(f"🌐 Browser automation forced for '{name}'")
            else:
                print(f"🌐 Using browser automation fallback for '{name}'")
                
            return await self.create_profile_via_browser(name)
        
        # All methods failed or disabled
        print(f"❌ All profile creation methods failed or disabled for '{name}'")
        return None
    
    async def _create_profile_via_api(self, name: str, timeout: int = 30) -> Dict[str, Any] | None:
        """
        Create profile via API (internal method).
        
        Args:
            name: Name for the new profile
            timeout: Request timeout in seconds
            
        Returns:
            Profile data dict if successful, None if failed
        """
        if not self.api_config:
            print(f"❌ No API configuration available for '{name}'")
            return None
            
        url = f"{self.api_config['host']}/browser/profiles"
        payload = {"name": name}
        
        try:
            print(f"🔌 Attempting API profile creation: {name}")
            response = requests.post(
                url, 
                headers=self.api_config["headers"], 
                json=payload, 
                timeout=timeout
            )
            response.raise_for_status()
            
            profile_data = response.json()
            
            # Debug: Print full response only if verbose debugging is needed
            # Uncomment the next line for detailed API response debugging:
            # print(f"🔍 API Response for '{name}': {profile_data}")
            
            # Check for profile ID in common possible fields
            profile_id = None
            for id_field in ['id', 'profileId', 'profile_id', '_id', 'uuid']:
                if id_field in profile_data:
                    profile_id = profile_data[id_field]
                    break
            
            if profile_id:
                print(f"✅ Profile created successfully via API: {name} (ID: {profile_id})")
                profile_data["created_via"] = "api"
                return profile_data
            else:
                print(f"⚠️ API profile creation response missing ID field: {name}")
                print(f"   Available fields: {list(profile_data.keys())}")
                return None
            
        except requests.RequestException as error:
            print(f"❌ API error creating profile '{name}': {error}")
            if hasattr(error, 'response') and error.response is not None:
                try:
                    error_data = error.response.json()
                    print(f"   API Error Details: {error_data}")
                except:
                    print(f"   Response Status: {error.response.status_code}")
                    print(f"   Response Text: {error.response.text}")
            return None
    
    async def cleanup(self) -> None:
        """
        Clean up all resources including browser sessions.
        
        Should be called when done with the API client to properly clean up browser resources.
        """
        await self._cleanup_browser_session()
        print("🧹 ScrapelessAPIClient cleanup completed")
    
    def get_profiles(self, page: int = 1, page_size: int = 100) -> Dict[str, Any] | None:
        """
        Retrieve list of existing profiles from Scrapeless API.
        
        Args:
            page: Page number for pagination
            page_size: Number of profiles per page
            
        Returns:
            API response with profile list if successful, None if failed
        """
        query = {"page": page, "pageSize": page_size}
        query_str = urlencode(query)
        url = f"{self.api_config['host']}/browser/profiles?{query_str}"
        
        try:
            response = requests.get(url, headers=self.api_config["headers"])
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as error:
            print(f"❌ Error retrieving profiles: {error}")
            return None
    
    def get_profile(self, profile_id: str) -> Dict[str, Any] | None:
        """
        Get details for a specific profile.
        
        Args:
            profile_id: ID of the profile to retrieve
            
        Returns:
            Profile details if successful, None if failed
        """
        url = f"{self.api_config['host']}/browser/profiles/{profile_id}"
        
        try:
            response = requests.get(url, headers=self.api_config["headers"])
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as error:
            print(f"❌ Error retrieving profile {profile_id}: {error}")
            return None
    
    def delete_profile(self, profile_id: str) -> bool:
        """
        Delete a specific profile via Scrapeless API.
        
        Args:
            profile_id: ID of the profile to delete
            
        Returns:
            True if deletion successful, False otherwise
        """
        url = f"{self.api_config['host']}/browser/profiles/{profile_id}"
        
        try:
            response = requests.delete(url, headers=self.api_config["headers"])
            response.raise_for_status()
            print(f"✅ Profile deleted successfully: {profile_id}")
            return True
            
        except requests.RequestException as error:
            print(f"❌ Error deleting profile {profile_id}: {error}")
            return False


class ProfileAllocationManager:
    """
    Thread-safe in-memory manager for profile allocation with asymmetrical penalty system.
    
    Uses asymmetrical penalty scoring where:
    - Allocation increases penalty by +2 (heavily penalizes active profiles)
    - Release decreases penalty by -1 (gradual recovery)
    - Always allocates profile with lowest penalty score
    - Supports unlimited allocations beyond pool size
    
    Key Features:
    - Asymmetrical penalty system for better load balancing
    - Priority queue based on penalty scores (not usage count)
    - Thread-safe operations with locks
    - Safeguards against over-releasing
    - Unlimited scalability beyond pool size
    """
    
    def __init__(self, allocation_penalty: int = 2, release_recovery: int = 1):
        """
        Initialize allocation manager with asymmetrical penalty system.
        
        Args:
            allocation_penalty: Penalty increase on allocation (default: 2)
            release_recovery: Penalty decrease on release (default: 1)
        """
        self._allocation_lock = threading.RLock()  # Reentrant lock for nested calls
        self._profile_heap: List[Tuple[int, str]] = []  # (penalty_score, profile_id)
        self._profile_data: Dict[str, ProfileData] = {}
        self._allocated_profiles: Dict[str, List[threading.Thread]] = {}  # Track multiple allocations per profile
        
        # Asymmetrical penalty configuration
        self.allocation_penalty = allocation_penalty
        self.release_recovery = release_recovery
        
        # Statistics tracking
        self._lifetime_allocations = 0
        self._lifetime_releases = 0
        self._over_release_attempts = 0
        
        print(f"🔧 Profile allocation manager initialized with asymmetrical penalties:")
        print(f"   ➕ Allocation penalty: +{allocation_penalty}")
        print(f"   ➖ Release recovery: -{release_recovery}")
    
    def load_profiles(self, profiles: List[ProfileData]) -> None:
        """
        Load profiles into allocation manager with penalty system.
        
        Properly seeds penalty scores based on actual allocations from cache.
        
        Args:
            profiles: List of ProfileData objects to manage
            
        Note:
            Thread-safe operation that rebuilds internal priority queue using penalty scores
        """
        with self._allocation_lock:
            print(f"📥 Loading {len(profiles)} profiles into allocation manager...")
            
            self._profile_data.clear()
            self._profile_heap.clear()
            self._allocated_profiles.clear()
            
            # Randomly shuffle profiles before loading to avoid allocation patterns
            shuffled_profiles = profiles.copy()  # Create copy to avoid modifying original list
            random.shuffle(shuffled_profiles)
            print(f"🔀 Randomly shuffled {len(shuffled_profiles)} profiles for load balancing")
            
            for profile in shuffled_profiles:
                self._profile_data[profile.profile_id] = profile
                # Initialize allocated profiles tracking
                self._allocated_profiles[profile.profile_id] = []
                
                # Seed penalty score based on actual allocations if loading from cache
                # This ensures proper priority even after restart
                if profile.actual_allocations > 0:
                    # Calculate penalty based on active allocations
                    # Each active allocation should contribute the allocation penalty
                    profile.penalty_score = profile.actual_allocations * self.allocation_penalty
                    print(f"   Seeded {profile.name} penalty to {profile.penalty_score} "
                          f"(based on {profile.actual_allocations} active allocations)")
                
                # Add to heap with penalty score as priority (lower = higher priority)
                heappush(self._profile_heap, (profile.penalty_score, profile.profile_id))
            
            print(f"✅ Successfully loaded {len(profiles)} profiles (penalty scores seeded from cache)")
    
    def allocate_profile(self) -> ProfileData | None:
        """
        Thread-safe allocation with asymmetrical penalty system.
        
        Always allocates the profile with the lowest penalty score, even if all profiles
        are currently allocated. Applies heavy penalty (+2) to discourage immediate reuse.
        
        Returns:
            ProfileData if allocation successful, None only if no profiles exist
            
        Note:
            - Increases penalty_score by +allocation_penalty (default: +2)
            - Increases actual_allocations by +1
            - Tracks each allocation thread for proper release validation
            - Supports unlimited allocations beyond pool size
        """
        with self._allocation_lock:
            if not self._profile_heap:
                print("⚠️ No profiles available for allocation - pool is empty")
                return None
            
            # Get profile with lowest penalty score, handling stale heap entries
            while self._profile_heap:
                penalty_score, profile_id = heappop(self._profile_heap)
                
                if profile_id not in self._profile_data:
                    # Skip stale entries (shouldn't happen normally)
                    continue
                
                profile = self._profile_data[profile_id]
                
                # Check if this heap entry is current (not stale)
                if penalty_score == profile.penalty_score:
                    break  # Found current entry
                else:
                    # This is a stale entry, continue to next one
                    continue
            else:
                # No valid entries found (shouldn't happen)
                print("⚠️ No valid profiles found in heap")
                return None
            
            # Apply asymmetrical penalties
            profile.penalty_score += self.allocation_penalty  # Heavy penalty for allocation
            profile.actual_allocations += 1  # Track active allocations
            profile.total_allocations += 1  # Lifetime counter
            
            # Track allocation thread for release validation
            current_thread = threading.current_thread()
            self._allocated_profiles[profile_id].append(current_thread)
            
            # Statistics
            self._lifetime_allocations += 1
            
            # Return profile to heap with updated penalty score (always available for reallocation)
            heappush(self._profile_heap, (profile.penalty_score, profile_id))
            
            # Determine status message
            status = "🔄 REUSING" if profile.actual_allocations > 1 else "🎯 ALLOCATED"
            
            print(f"{status} profile: {profile.name} (ID: {profile_id[:8]}..., "
                  f"Penalty: {profile.penalty_score}, Active: {profile.actual_allocations}, "
                  f"Total: {profile.total_allocations})")
            
            return profile
    
    def release_profile(self, profile_id: str) -> bool:
        """
        Thread-safe release with asymmetrical penalty recovery and safeguards.
        
        Decreases penalty score by -1 and actual allocation count. Includes safeguards
        to prevent over-releasing (releasing more times than allocated).
        
        Args:
            profile_id: ID of profile to release
            
        Returns:
            True if release successful, False if invalid release attempt
            
        Note:
            - Decreases penalty_score by -release_recovery (default: -1)
            - Decreases actual_allocations by -1 (with safeguard)
            - Validates release against actual allocation tracking
            - Updates heap position with new penalty score
        """
        with self._allocation_lock:
            if profile_id not in self._profile_data:
                print(f"⚠️ Cannot release profile {profile_id}: profile not found")
                return False
            
            profile = self._profile_data[profile_id]
            
            # Safeguard: Check if profile has any active allocations
            if profile.actual_allocations <= 0:
                print(f"⚠️ Cannot release profile {profile.name}: no active allocations "
                      f"(current: {profile.actual_allocations})")
                self._over_release_attempts += 1
                return False
            
            # Safeguard: Check if we have tracked allocations for this profile
            if profile_id not in self._allocated_profiles or not self._allocated_profiles[profile_id]:
                print(f"⚠️ Cannot release profile {profile.name}: no tracked allocations")
                self._over_release_attempts += 1
                return False
            
            # Remove one allocation thread from tracking (FIFO)
            released_thread = self._allocated_profiles[profile_id].pop(0)
            
            # Apply asymmetrical recovery
            profile.penalty_score -= self.release_recovery  # Gradual penalty recovery
            profile.actual_allocations -= 1  # Reduce active allocation count
            
            # Prevent penalty score from going negative (optional safeguard)
            if profile.penalty_score < 0:
                profile.penalty_score = 0
            
            # Statistics
            self._lifetime_releases += 1
            
            # Update heap: We need to find and update the existing entry
            # Since heapq doesn't support decrease-key, we'll add a new entry
            # The old entry will be ignored when popped (profile_id lookup will handle this)
            heappush(self._profile_heap, (profile.penalty_score, profile_id))
            
            # Determine status message
            status = "🔄 RELEASED" if profile.actual_allocations > 0 else "✅ FULLY RELEASED"
            
            print(f"{status} profile: {profile.name} (ID: {profile_id[:8]}..., "
                  f"Penalty: {profile.penalty_score}, Active: {profile.actual_allocations}, "
                  f"Thread: {str(released_thread)[:20]}...)")
            
            return True
    
    def get_allocation_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive allocation statistics for asymmetrical penalty system.
        
        Returns:
            Dictionary with detailed metrics including penalty scores and safeguard statistics
        """
        with self._allocation_lock:
            total_profiles = len(self._profile_data)
            actively_allocated_profiles = sum(1 for p in self._profile_data.values() if p.actual_allocations > 0)
            total_active_allocations = sum(p.actual_allocations for p in self._profile_data.values())
            
            # Calculate penalty distribution
            penalty_distribution = {}
            for profile in self._profile_data.values():
                penalty = profile.penalty_score
                penalty_distribution[penalty] = penalty_distribution.get(penalty, 0) + 1
            
            # Profile details with penalty system information
            profile_details = {}
            for pid, profile in self._profile_data.items():
                allocated_threads = self._allocated_profiles.get(pid, [])
                profile_details[pid] = {
                    "profile_name": profile.name,
                    "penalty_score": profile.penalty_score,
                    "actual_allocations": profile.actual_allocations,
                    "total_allocations": profile.total_allocations,
                    "allocated_threads": [str(thread)[:30] + "..." for thread in allocated_threads],
                    "is_busy": profile.actual_allocations > 0
                }
            
            return {
                # Basic metrics
                "total_profiles": total_profiles,
                "actively_allocated_profiles": actively_allocated_profiles,
                "total_active_allocations": total_active_allocations,
                "available_profiles": total_profiles,  # All profiles are always "available" for allocation
                
                # Asymmetrical penalty system metrics
                "penalty_system": {
                    "allocation_penalty": self.allocation_penalty,
                    "release_recovery": self.release_recovery,
                    "penalty_distribution": penalty_distribution
                },
                
                # Lifetime statistics
                "lifetime_statistics": {
                    "total_allocations": self._lifetime_allocations,
                    "total_releases": self._lifetime_releases,
                    "over_release_attempts": self._over_release_attempts,
                    "allocation_release_ratio": (
                        self._lifetime_allocations / max(self._lifetime_releases, 1)
                        if self._lifetime_releases > 0 else self._lifetime_allocations
                    )
                },
                
                # Detailed profile information
                "profile_details": profile_details,
                
                # Backward compatibility
                "allocated_profiles": actively_allocated_profiles
            }


class ScrapelessProfileManager:
    """
    Main profile manager orchestrating profile lifecycle and allocation.
    
    Comprehensive manager that handles:
    - Profile pool initialization and management
    - Local JSON persistence
    - API communication via ScrapelessAPIClient
    - Thread-safe allocation via ProfileAllocationManager
    - Profile pool reset and recreation
    - Async context manager support for resource management
    
    Usage:
        # As async context manager (recommended)
        async with ScrapelessProfileManager() as manager:
            profile = await manager.allocate_profile()
            # ... use profile for scraping ...
            await manager.release_profile(profile.profile_id)
        # Cache is automatically saved on exit
        
        # Or manual management
        manager = ScrapelessProfileManager()
        await manager.open()  # Initialize
        profile = await manager.allocate_profile()
        # ... use profile ...
        await manager.release_profile(profile.profile_id)
        await manager.close()  # Save cache and cleanup
    """
    
    def __init__(self, 
                 num_profiles: int = DEFAULT_CONCURRENT_PROFILES,
                 name_prefix: str = DEFAULT_ENTITY_PREFIX,
                 cache_file: str = "scrapeless_profiles_cache.json",
                 redis_url: str = global_settings.REDIS_URL,
                 save_cache_on_operations: bool = False):
        """
        Initialize profile manager with configuration.
        
        Args:
            num_profiles: Number of concurrent profiles to maintain
            name_prefix: Prefix for profile names
            cache_file: Local JSON cache file path (relative to data directory)
            redis_url: Redis URL for multi-processing safe cache operations
            save_cache_on_operations: If True, save cache on every allocate/release (default: False)
        """
        self.num_profiles = num_profiles
        self.name_prefix = name_prefix
        self.save_cache_on_operations = save_cache_on_operations
        
        # Create data directory path relative to current file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(current_dir, "data")
        
        # Ensure data directory exists
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Set cache file path within data directory
        self.cache_file = os.path.join(self.data_dir, cache_file)
        
        # Initialize Redis client for multi-processing safe operations
        if not redis_url:
            raise ValueError("Redis URL is required for multi-processing safe operations")
        
        self.redis_client = AsyncRedisClient(redis_url)
        self.cache_lock_key = f"scrapeless_cache_lock:{os.path.basename(self.cache_file)}"
        print(f"🔒 Redis-based locking enabled for cache operations")
        
        # Initialize components
        try:
            self.api_client = ScrapelessAPIClient()
        except ValueError as e:
            print(f"❌ Failed to initialize API client: {e}")
            self.api_client = None
            
        self.allocation_manager = ProfileAllocationManager()
        
        # Internal state
        self._profiles: List[ProfileData] = []
        self._initialization_lock = threading.Lock()
        self._is_initialized = False
        self._is_opened = False
        
        # Track initial state for delta calculations during cache save
        self._initial_profile_state: Dict[str, Dict[str, int]] = {}
        
        print(f"🚀 ScrapelessProfileManager initialized:")
        print(f"   📊 Target profiles: {num_profiles}")
        print(f"   🏷️  Name prefix: {name_prefix}")
        print(f"   📁 Data directory: {self.data_dir}")
        print(f"   💾 Cache file: {self.cache_file}")
        print(f"   🔄 Save on operations: {save_cache_on_operations}")
    
    async def __aenter__(self):
        """Async context manager entry - opens the profile manager."""
        await self.open()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - closes the profile manager and saves cache."""
        await self.close()
        return False  # Don't suppress exceptions
    
    async def open(self) -> bool:
        """
        Open the profile manager and initialize the profile pool.
        
        This method:
        1. Initializes the profile pool if not already done
        2. Records initial state for delta tracking
        3. Marks the manager as opened
        
        Returns:
            True if opened successfully, False otherwise
        """
        if self._is_opened:
            print("ℹ️ Profile manager already opened")
            return True
        
        # Initialize profile pool
        if not self._is_initialized:
            success = await self.init()
            if not success:
                print("❌ Failed to open profile manager: initialization failed")
                return False
        
        # Record initial state for delta tracking
        self._record_initial_state()
        
        self._is_opened = True
        print(f"✅ Profile manager opened (save_on_operations: {self.save_cache_on_operations})")
        return True
    
    async def close(self) -> None:
        """
        Close the profile manager and save final cache state.
        
        This method:
        1. Saves the current cache state with deltas
        2. Cleans up API client resources (including browser sessions)
        3. Marks the manager as closed
        4. Performs cleanup operations
        """
        if not self._is_opened:
            print("ℹ️ Profile manager already closed or never opened")
            return
        
        try:
            # Save final cache state with all accumulated deltas
            await self._save_profiles_to_cache()
            print("💾 Final cache state saved during close")
        except Exception as e:
            print(f"⚠️ Error saving cache during close: {e}")
        
        try:
            # Clean up API client resources (browser sessions, etc.)
            if self.api_client:
                await self.api_client.cleanup()
        except Exception as e:
            print(f"⚠️ Error cleaning up API client during close: {e}")
        
        self._is_opened = False
        print("🔒 Profile manager closed")
    
    def _record_initial_state(self) -> None:
        """
        Record initial state of all profiles for delta tracking.
        
        This captures the baseline values when the manager is opened,
        so we can calculate deltas during cache save operations.
        """
        self._initial_profile_state.clear()
        
        for profile in self._profiles:
            self._initial_profile_state[profile.profile_id] = {
                "actual_allocations": profile.actual_allocations,
                "total_allocations": profile.total_allocations,
                "penalty_score": profile.penalty_score
            }
        
        print(f"📊 Recorded initial state for {len(self._profiles)} profiles")
    
    async def _generate_profile_name(self, index: int) -> str:
        """Generate profile name using configured prefix and index."""
        return f"{self.name_prefix}-{index}"
    
    async def _save_profiles_to_cache(self) -> None:
        """
        Save current profile list to local JSON cache with multi-processing safety.
        
        Uses Redis-based distributed locking to ensure thread/process safety.
        Merges existing cache data rather than overwriting to preserve updates from other processes.
        """
        # Use Redis-based locking for multi-processing safety
        await self._save_profiles_to_cache_async()
    

    async def _save_profiles_to_cache_async(self) -> None:
        """
        Async implementation of cache save with Redis-based distributed locking and delta tracking.
        
        This method:
        1. Acquires a distributed lock via Redis
        2. Reads existing cache data from file
        3. Calculates deltas from initial state and applies them to existing data
        4. Saves merged data atomically
        5. Updates initial state if save_cache_on_operations is True (for accurate incremental tracking)
        6. Releases the lock
        
        Delta tracking approach:
        - Records initial state when manager opens
        - Calculates positive deltas during this session
        - Adds deltas to values read from cache (no max() usage)
        - Updates initial state after save if immediate mode to prevent double-counting
        - Ensures consistent incremental updates across processes
        """
        max_retries = 5
        retry_delay = 0.5
        lock_timeout = 30
        
        for attempt in range(max_retries):
            try:
                print(f"🔒 Attempting to acquire cache lock (attempt {attempt + 1}/{max_retries})...")
                
                # Acquire distributed lock with timeout
                async with self.redis_client.with_lock(
                    self.cache_lock_key, 
                    timeout=lock_timeout, 
                    ttl=lock_timeout + 10
                ):
                    print(f"✅ Cache lock acquired, performing safe delta merge operation...")
                    
                    # Read existing cache data while holding lock
                    existing_data = {}
                    existing_profiles = {}
                    
                    if os.path.exists(self.cache_file):
                        try:
                            with open(self.cache_file, 'r') as f:
                                existing_data = json.load(f)
                                
                            # Build lookup of existing profiles by ID
                            for profile_dict in existing_data.get("profiles", []):
                                existing_profiles[profile_dict["profile_id"]] = profile_dict
                                
                            print(f"📥 Read {len(existing_profiles)} existing profiles from cache")
                            
                        except (json.JSONDecodeError, IOError) as e:
                            print(f"⚠️ Could not read existing cache, will create new: {e}")
                    
                    # Merge current profiles with existing data using delta tracking
                    merged_profiles = []
                    current_profile_ids = set()
                    
                    for profile in self._profiles:
                        current_profile_ids.add(profile.profile_id)
                        profile_dict = asdict(profile)
                        
                        # Check if profile exists in cache
                        if profile.profile_id in existing_profiles:
                            existing_profile = existing_profiles[profile.profile_id]
                            
                            # Calculate deltas from initial state for this session
                            initial_state = self._initial_profile_state.get(profile.profile_id, {})
                            
                            # Calculate deltas (positive changes during this session)
                            total_allocations_delta = max(0, 
                                profile.total_allocations - initial_state.get("total_allocations", 0)
                            )
                            
                            # For actual_allocations, use current value as it reflects real-time state
                            # but log the delta for monitoring
                            actual_allocations_delta = (
                                profile.actual_allocations - initial_state.get("actual_allocations", 0)
                            )
                            
                            # Apply deltas to existing cache values
                            profile_dict["total_allocations"] = (
                                existing_profile.get("total_allocations", 0) + total_allocations_delta
                            )
                            
                            # For actual_allocations, use current value (reflects real-time state)
                            profile_dict["actual_allocations"] = profile.actual_allocations
                            
                            # Log delta information for monitoring
                            if total_allocations_delta > 0 or actual_allocations_delta != 0:
                                print(f"📈 Profile {profile.name} deltas: "
                                      f"total_allocations +{total_allocations_delta}, "
                                      f"actual_allocations {actual_allocations_delta:+d}")
                        else:
                            # New profile - use current values as-is
                            print(f"🆕 New profile {profile.name}: using current values")
                        
                        merged_profiles.append(profile_dict)
                        
                    # Add any profiles from existing cache that we don't have
                    for profile_id, existing_profile in existing_profiles.items():
                        if profile_id not in current_profile_ids:
                            merged_profiles.append(existing_profile)
                            print(f"📝 Preserved profile {existing_profile.get('name', profile_id)} from cache")
                    
                    # Create backup before saving
                    if os.path.exists(self.cache_file):
                        backup_file = f"{self.cache_file}.backup"
                        try:
                            os.rename(self.cache_file, backup_file)
                            print(f"📋 Created cache backup: {backup_file}")
                        except OSError as e:
                            print(f"⚠️ Could not create backup: {e}")
                    
                    # Save merged data with delta tracking metadata
                    cache_data = {
                        "created_at": datetime.now().isoformat(),
                        "last_updated_by": f"pid_{os.getpid()}",
                        "update_method": "delta_tracking",
                        "session_opened": self._is_opened,
                        "num_profiles": len(merged_profiles),
                        "profiles": merged_profiles
                    }
                    
                    with open(self.cache_file, 'w') as f:
                        json.dump(cache_data, f, indent=2)
                    
                    print(f"💾 Safely saved {len(merged_profiles)} profiles to cache with delta tracking: {self.cache_file}")
                    
                    # Update initial state after successful save if in immediate save mode
                    # This prevents double-counting deltas in subsequent saves during the same session
                    if self.save_cache_on_operations:
                        print(f"🔄 Updating initial state after cache save (immediate mode)")
                        self._update_initial_state_after_save()
                    
                    print(f"🔓 Cache lock released")
                    return  # Success - exit retry loop
                    
            except asyncio.TimeoutError:
                print(f"⏳ Lock acquisition timeout on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                continue
                
            except Exception as error:
                print(f"❌ Error in cache save attempt {attempt + 1}: {error}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                continue
        
        # All retries failed
        print(f"❌ Failed to acquire cache lock after {max_retries} attempts")
        raise Exception("Could not acquire cache lock for safe save operation")
    
    def _update_initial_state_after_save(self) -> None:
        """
        Update initial state after cache save to prevent double-counting deltas.
        
        This method is called after successful cache saves when save_cache_on_operations=True
        to ensure that subsequent saves in the same session calculate deltas correctly.
        """
        for profile in self._profiles:
            if profile.profile_id in self._initial_profile_state:
                # Update initial state to current values after successful save
                self._initial_profile_state[profile.profile_id].update({
                    "actual_allocations": profile.actual_allocations,
                    "total_allocations": profile.total_allocations,
                    "penalty_score": profile.penalty_score
                })
        
        print(f"📊 Updated initial state for {len(self._profiles)} profiles (prevents double-counting)")
    
    async def _load_profiles_from_cache(self) -> bool:
        """
        Load profiles from local JSON cache.
        
        Returns:
            True if cache loaded successfully, False otherwise
        """
        if not os.path.exists(self.cache_file):
            print(f"ℹ️ No cache file found: {self.cache_file}")
            return False
        
        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            profile_dicts = cache_data.get("profiles", [])
            self._profiles = [ProfileData(**profile_dict) for profile_dict in profile_dicts]
            
            print(f"📥 Loaded {len(self._profiles)} profiles from cache")
            return True
            
        except Exception as error:
            print(f"❌ Error loading profiles from cache: {error}")
            return False
    
    async def init(self) -> bool:
        """
        Initialize profile pool by creating all configured profiles with multi-processing safety.
        
        Creates the specified number of profiles via Scrapeless API,
        saves them to local cache, and loads them into allocation manager.
        Uses Redis-based distributed locking to prevent conflicts.
        
        Returns:
            True if initialization successful, False otherwise
            
        Note:
            Thread-safe operation that prevents multiple simultaneous initializations
        """
        with self._initialization_lock:
            if self._is_initialized:
                print("ℹ️ Profile manager already initialized")
                return True
            
            # Check if API client is available
            if not self.api_client:
                print("❌ Cannot initialize: API client not available (check API key configuration)")
                return False
            
            # Use Redis-based locking for multi-processing safety
            return await self._init_async()
    
    async def _init_async(self) -> bool:
        """
        Async implementation of init with Redis-based distributed locking.
        
        Ensures only one process can initialize the profile pool at a time.
        """
        init_lock_key = f"scrapeless_init_lock:{self.name_prefix}"
        max_retries = 3
        retry_delay = 2.0
        lock_timeout = 120  # Long timeout for profile creation
        
        for attempt in range(max_retries):
            try:
                print(f"🔒 Attempting to acquire init lock (attempt {attempt + 1}/{max_retries})...")
                
                # Acquire distributed lock with longer timeout for init
                async with self.redis_client.with_lock(
                    init_lock_key, 
                    timeout=lock_timeout, 
                    ttl=lock_timeout + 30
                ):
                    print(f"✅ Init lock acquired, performing safe initialization...")
                    
                    # Check if another process already initialized while we waited
                    if os.path.exists(self.cache_file):
                        try:
                            with open(self.cache_file, 'r') as f:
                                existing_data = json.load(f)
                            
                            existing_profiles = existing_data.get("profiles", [])
                            if len(existing_profiles) >= self.num_profiles:
                                print(f"ℹ️ Found existing {len(existing_profiles)} profiles in cache, skipping creation")
                                
                                # Load existing profiles
                                self._profiles = [ProfileData(**profile_dict) for profile_dict in existing_profiles]
                                self.allocation_manager.load_profiles(self._profiles)
                                self._is_initialized = True
                                print(f"🔓 Init lock released (loaded from cache)")
                                return True
                                
                        except (json.JSONDecodeError, IOError) as e:
                            print(f"⚠️ Could not read existing cache during init: {e}")
                    
                    # Perform actual initialization
                    result = await self._init_profiles()
                    print(f"🔓 Init lock released")
                    return result
                    
            except asyncio.TimeoutError:
                print(f"⏳ Init lock acquisition timeout on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                continue
                
            except Exception as error:
                print(f"❌ Error in init attempt {attempt + 1}: {error}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                continue
        
        # All retries failed
        print(f"❌ Failed to acquire init lock after {max_retries} attempts")
        raise Exception("Could not acquire init lock for safe initialization")
    
    async def _init_profiles(self) -> bool:
        """
        Core profile creation logic (called from async context).
        
        Returns:
            True if initialization successful, False otherwise
        """
        print(f"🔄 Creating {self.num_profiles} profiles...")
        
        # # Test API connection before creating profiles
        # if not self.api_client.test_connection():
        #     print("❌ Profile initialization failed: Cannot connect to Scrapeless API")
        #     print("   Please check your API key and network connection")
        #     return False
        
        created_profiles = []
        success_count = 0
        
        for i in range(1, self.num_profiles + 1):
            profile_name = await self._generate_profile_name(i)
            
            print(f"📝 Creating profile {i}/{self.num_profiles}: {profile_name}")
            
            # Create profile via API with browser fallback
            api_response = await self.api_client.create_profile(profile_name)
            
            if api_response:
                # Extract profile ID from response (check multiple possible field names)
                profile_id = None
                for id_field in ['id', 'profileId', 'profile_id', '_id', 'uuid']:
                    if id_field in api_response:
                        profile_id = api_response[id_field]
                        break
                
                if profile_id:
                    profile_data = ProfileData(
                        profile_id=str(profile_id),  # Ensure it's a string
                        name=profile_name,
                        created_at=datetime.now().isoformat(),
                        penalty_score=0,  # Initialize with no penalty
                        actual_allocations=0,  # No active allocations
                        total_allocations=0  # No lifetime allocations yet
                    )
                    created_profiles.append(profile_data)
                    success_count += 1
                else:
                    print(f"⚠️ Profile creation failed - no valid ID in response: {profile_name}")
            else:
                print(f"⚠️ Profile creation failed - no response: {profile_name}")
            
            # Add small delay to avoid rate limiting
            time.sleep(0.1)
        
        # Update internal state
        self._profiles = created_profiles
        
        # Save to cache (use fresh save during init, no merging)
        await self._save_profiles_to_cache_fresh()
        
        # Load into allocation manager
        self.allocation_manager.load_profiles(self._profiles)
        
        self._is_initialized = True
        
        print(f"✅ Profile pool initialization complete:")
        print(f"   🎯 Successfully created: {success_count}/{self.num_profiles}")
        print(f"   💾 Cached profiles: {len(self._profiles)}")
        
        return success_count > 0
    
    async def _save_profiles_to_cache_fresh(self) -> None:
        """
        Save profiles to cache with fresh state (no merging) - used during init/reset.
        
        This method is used when we want to create a completely fresh cache
        without trying to merge with existing data.
        """
        try:
            # Create backup if cache exists
            if os.path.exists(self.cache_file):
                backup_file = f"{self.cache_file}.init_backup"
                try:
                    os.rename(self.cache_file, backup_file)
                    print(f"📋 Created init backup: {backup_file}")
                except OSError as e:
                    print(f"⚠️ Could not create init backup: {e}")
            
            # Save fresh profiles data
            cache_data = {
                "created_at": datetime.now().isoformat(),
                "last_updated_by": f"pid_{os.getpid()}_init",
                "operation": "fresh_init",
                "num_profiles": len(self._profiles),
                "profiles": [asdict(profile) for profile in self._profiles]
            }
            
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            print(f"💾 Saved {len(self._profiles)} profiles to cache (fresh init): {self.cache_file}")
            
        except Exception as error:
            print(f"❌ Error saving profiles to cache (fresh init): {error}")
    
    async def reset(self) -> bool:
        """
        Reset profile pool by deleting all existing profiles and recreating with multi-processing safety.
        
        Performs complete reset:
        1. Deletes all existing profiles via API
        2. Completely clears local cache (no count merging)
        3. Reinitializes with fresh profile pool
        
        Uses Redis-based distributed locking to prevent conflicts.
        
        Returns:
            True if reset successful, False otherwise
        """
        if not self.api_client:
            print("❌ Cannot reset: API client not available")
            return False
        
        # Use Redis-based locking for multi-processing safety
        return await self._reset_async()
    
    async def _reset_async(self) -> bool:
        """
        Async implementation of reset with Redis-based distributed locking.
        
        Ensures only one process can reset the profile pool at a time.
        """
        reset_lock_key = f"scrapeless_reset_lock:{self.name_prefix}"
        max_retries = 3
        retry_delay = 2.0
        lock_timeout = 180  # Long timeout for profile deletion + recreation
        
        for attempt in range(max_retries):
            try:
                print(f"🔒 Attempting to acquire reset lock (attempt {attempt + 1}/{max_retries})...")
                
                # Acquire distributed lock with longer timeout for reset
                async with self.redis_client.with_lock(
                    reset_lock_key, 
                    timeout=lock_timeout, 
                    ttl=lock_timeout + 30
                ):
                    print(f"✅ Reset lock acquired, performing safe reset...")
                    
                    # Completely clear cache file first (no count processing during reset)
                    await self._clear_cache_completely()
                    
                    # Perform actual reset
                    result = await self._reset_profiles()
                    print(f"🔓 Reset lock released")
                    return result
                    
            except asyncio.TimeoutError:
                print(f"⏳ Reset lock acquisition timeout on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                continue
                
            except Exception as error:
                print(f"❌ Error in reset attempt {attempt + 1}: {error}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                continue
        
        # All retries failed
        print(f"❌ Failed to acquire reset lock after {max_retries} attempts")
        raise Exception("Could not acquire reset lock for safe reset operation")
    
    async def _clear_cache_completely(self) -> None:
        """
        Completely clear the cache file during reset - no count processing.
        
        This is called during reset operations to ensure clean state.
        """
        try:
            if os.path.exists(self.cache_file):
                # Create backup before clearing
                backup_file = f"{self.cache_file}.reset_backup"
                try:
                    os.rename(self.cache_file, backup_file)
                    print(f"📋 Created reset backup: {backup_file}")
                except OSError as e:
                    print(f"⚠️ Could not create reset backup: {e}")
                    # Continue with reset even if backup fails
                    os.remove(self.cache_file)
                
                print(f"🗑️ Completely cleared cache file during reset: {self.cache_file}")
            else:
                print(f"ℹ️ No cache file to clear: {self.cache_file}")
                
        except Exception as error:
            print(f"❌ Error clearing cache during reset: {error}")
    
    async def _reset_profiles(self) -> bool:
        """
        Core reset logic (called from async context).
        
        Returns:
            True if reset successful, False otherwise
        """            
        print("🔄 Deleting existing profiles...")
        
        # Delete all existing profiles
        deleted_count = 0
        for profile in self._profiles:
            print(f"🗑️ Deleting profile: {profile.name} (ID: {profile.profile_id})")
            if self.api_client.delete_profile(profile.profile_id):
                deleted_count += 1
            time.sleep(0.1)  # Rate limiting
        
        print(f"✅ Deleted {deleted_count}/{len(self._profiles)} profiles")
        
        # Clear internal state
        self._profiles.clear()
        self._is_initialized = False
        
        # Clean up API client browser sessions before reinitialization
        try:
            await self.api_client.cleanup()
        except Exception as e:
            print(f"⚠️ Error cleaning up API client during reset: {e}")
        
        # Reinitialize with fresh state
        return await self._init_profiles()
    
    async def get_profiles(self) -> List[ProfileData]:
        """
        Get list of all managed profiles.
        
        Returns:
            List of ProfileData objects for all profiles in pool
        """
        return self._profiles.copy()
    
    async def get_profile(self, profile_id: str) -> ProfileData | None:
        """
        Get specific profile by ID.
        
        Args:
            profile_id: ID of profile to retrieve
            
        Returns:
            ProfileData if found, None otherwise
        """
        for profile in self._profiles:
            if profile.profile_id == profile_id:
                return profile
        return None
    
    async def allocate_profile(self) -> ProfileData | None:
        """
        Allocate profile from pool for use.
        
        Conditionally persists updated allocation counts to cache based on save_cache_on_operations flag.
        
        Returns:
            ProfileData of allocated profile, None if none available
        """
        if not self._is_initialized:
            print("⚠️ Profile manager not initialized. Call open() first.")
            return None
        
        profile = self.allocation_manager.allocate_profile()
        
        # Conditionally persist updated allocation counts based on flag
        if profile and self.save_cache_on_operations:
            await self._save_profiles_to_cache()
            print("💾 Cache saved after allocation (save_cache_on_operations=True)")
            
        return profile
    
    async def release_profile(self, profile_id: str) -> bool:
        """
        Release allocated profile back to pool.
        
        Conditionally persists updated allocation counts to cache based on save_cache_on_operations flag.
        
        Args:
            profile_id: ID of profile to release
            
        Returns:
            True if release successful, False otherwise
        """
        success = self.allocation_manager.release_profile(profile_id)
        
        # Conditionally persist updated allocation counts based on flag
        if success and self.save_cache_on_operations:
            await self._save_profiles_to_cache()
            print("💾 Cache saved after release (save_cache_on_operations=True)")
            
        return success
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive manager statistics.
        
        Returns:
            Dictionary with manager state and allocation statistics
        """
        base_stats = {
            "is_initialized": self._is_initialized,
            "is_opened": self._is_opened,
            "total_profiles": len(self._profiles),
            "cache_file": self.cache_file,
            "configuration": {
                "num_profiles": self.num_profiles,
                "name_prefix": self.name_prefix,
                "save_cache_on_operations": self.save_cache_on_operations
            }
        }
        
        if self._is_initialized:
            allocation_stats = self.allocation_manager.get_allocation_stats()
            base_stats.update(allocation_stats)
        
        return base_stats
    
    async def delete_all_profiles(self) -> bool:
        """
        Delete all managed profiles (cleanup method) with multi-processing safety.
        
        Uses Redis-based distributed locking to prevent conflicts.
        Completely removes the cache file after successful deletion.
        
        Returns:
            True if all profiles deleted successfully
        """
        if not self.api_client:
            print("❌ Cannot delete profiles: API client not available")
            return False
        
        # Use Redis-based locking for multi-processing safety
        return await self._delete_all_profiles_async()
    
    async def _delete_all_profiles_async(self) -> bool:
        """
        Async implementation of delete all profiles with Redis-based distributed locking.
        """
        delete_lock_key = f"scrapeless_delete_lock:{self.name_prefix}"
        max_retries = 3
        retry_delay = 1.0
        lock_timeout = 120  # Long timeout for profile deletion
        
        for attempt in range(max_retries):
            try:
                print(f"🔒 Attempting to acquire delete lock (attempt {attempt + 1}/{max_retries})...")
                
                # Acquire distributed lock
                async with self.redis_client.with_lock(
                    delete_lock_key, 
                    timeout=lock_timeout, 
                    ttl=lock_timeout + 30
                ):
                    print(f"✅ Delete lock acquired, performing safe cleanup...")
                    
                    # Completely clear cache file first (no count processing during cleanup)
                    await self._clear_cache_completely()
                    
                    # Perform actual deletion
                    result = await self._delete_profiles()
                    print(f"🔓 Delete lock released")
                    return result
                    
            except asyncio.TimeoutError:
                print(f"⏳ Delete lock acquisition timeout on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                continue
                
            except Exception as error:
                print(f"❌ Error in delete attempt {attempt + 1}: {error}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                continue
        
        # All retries failed
        print(f"❌ Failed to acquire delete lock after {max_retries} attempts")
        raise Exception("Could not acquire delete lock for safe cleanup operation")
    
    async def _delete_profiles(self) -> bool:
        """
        Core profile deletion logic (called from async context).
        
        Returns:
            True if all profiles deleted successfully
        """
        print("🗑️ Deleting all managed profiles...")
        
        deleted_count = 0
        for profile in self._profiles:
            if self.api_client.delete_profile(profile.profile_id):
                deleted_count += 1
            time.sleep(0.1)
        
        success = deleted_count == len(self._profiles)
        print(f"✅ Deleted {deleted_count}/{len(self._profiles)} profiles")
        
        if success:
            self._profiles.clear()
            self._is_initialized = False
            
            # Clean up API client browser sessions after deletion
            try:
                await self.api_client.cleanup()
            except Exception as e:
                print(f"⚠️ Error cleaning up API client during delete: {e}")
            
            # Remove cache file completely after successful deletion
            if os.path.exists(self.cache_file):
                try:
                    backup_file = f"{self.cache_file}.delete_backup"
                    os.rename(self.cache_file, backup_file)
                    print(f"📋 Created delete backup: {backup_file}")
                except OSError:
                    os.remove(self.cache_file)
                print(f"🗑️ Completely removed cache file: {self.cache_file}")
        
        return success


# Example usage demonstrating async context manager functionality

if __name__ == "__main__":
    # async def main():
    #     manager = ScrapelessProfileManager()
    #     await manager.init()
    
    # asyncio.run(main())

    # api_key = scraping_settings.SCRAPELESS_API_KEY

    # import requests
    # import json

    # url = "https://api.scrapeless.com/browser/profiles"

    # payload = json.dumps({
    # "name": "test"
    # })
    # headers = {
    # 'Content-Type': 'application/json',
    # 'x-api-token': api_key,
    # }

    # response = requests.request("POST", url, headers=headers, data=payload)
    # import ipdb; ipdb.set_trace()

    # print(response.text)

    
    # api_key = scraping_settings.SCRAPELESS_API_KEY
    # print(api_key[:5])
    # import http.client
    # import json

    # conn = http.client.HTTPSConnection("api.scrapeless.com")
    # payload = json.dumps({
    # "name": "test"
    # })
    # headers = {
    # 'Content-Type': 'application/json',
    # 'x-api-token': api_key,
    # }
    # conn.request("POST", "/browser/profiles", payload, headers)
    # res = conn.getresponse()
    # data = res.read()
    # import ipdb; ipdb.set_trace()
    # print(data.decode("utf-8"))

    async def test_browser_profile_creation():
        scrapeless_api_client = ScrapelessAPIClient(use_browser_fallback=True)
        
        # Create profile via browser automation with real profile ID extraction
        print("🌐 Testing browser automation profile creation with ID extraction...")
        profile_result = await scrapeless_api_client.create_profile_via_browser("test-profile-with-id")
        
        if profile_result:
            print(f"✅ Profile created successfully:")
            print(f"   - Name: {profile_result.get('name')}")
            print(f"   - Profile ID: {profile_result.get('id')}")
            print(f"   - Created via: {profile_result.get('created_via')}")
            print(f"   - Actual ID extracted: {profile_result.get('actual_profile_id_extracted', False)}")
            
            # Show detailed browser result
            browser_result = profile_result.get('browser_result', {})
            if browser_result:
                print(f"   - Browser result: {browser_result.get('message')}")
                if browser_result.get('profile_id'):
                    print(f"   - Scrapeless profile ID: {browser_result.get('profile_id')}")
        else:
            print("❌ Profile creation failed")
        
        await scrapeless_api_client.cleanup()
        return profile_result
    
    # Run the test
    # profiles = asyncio.run(test_browser_profile_creation())
    # print("\n📊 Final result:")
    # print(profiles)
    # import ipdb; ipdb.set_trace()



    print("""
    async def example_usage():
        # Cache is saved only once at the end (efficient)
        async with ScrapelessProfileManager(num_profiles=3) as manager:
            # Allocate multiple profiles
            profile1 = await manager.allocate_profile()
            profile2 = await manager.allocate_profile()
            
            # Use profiles for scraping...
            print(f"Using profiles: {profile1.name}, {profile2.name}")
            
            # Release profiles
            await manager.release_profile(profile1.profile_id)
            await manager.release_profile(profile2.profile_id)
            
        # Cache automatically saved here with all deltas
    """)
    
    print("\n2. Manual Management:")
    print("""
    async def manual_example():
        manager = ScrapelessProfileManager(
            num_profiles=3,
            save_cache_on_operations=True  # Save on every operation
        )
        await manager.open()
        
        profile = await manager.allocate_profile()  # Cache saved here
        await manager.release_profile(profile.profile_id)  # Cache saved here
        
        await manager.close()  # Final cache save
    """)
    
    print("\n3. Configuration Options:")
    print("""
    # Efficient mode (default): save cache only on close
    async with ScrapelessProfileManager(save_cache_on_operations=False) as manager:
        # Multiple operations without disk I/O
        pass
    
    # Immediate mode: save cache on every allocate/release
    async with ScrapelessProfileManager(save_cache_on_operations=True) as manager:
        # Each operation triggers cache save
        pass
    """)
    
    print("\n4. Browser Automation Fallback:")
    print("""
    # Automatic fallback when API fails
    async with ScrapelessProfileManager() as manager:
        # Will try API first, then browser automation if API fails
        profile = await manager.allocate_profile()
    
    # Force browser automation (skip API)
    manager.api_client.create_profile("test-profile", force_browser=True)
    
    # Browser-only mode (no API key needed)
    manager = ScrapelessProfileManager()
    # If no API key is configured, will automatically use browser automation
    """)
    
    print("\n5. Browser Automation Notes:")
    print("""
    - First browser automation call will trigger manual login with ipdb.set_trace()
    - Browser session is cached for subsequent profile creations
    - Browser automation is slower but more reliable than API
    - Automatically cleans up browser sessions when manager closes
    """)
    
    print("\nFor complete examples, run:")
    print("  python demo_usage.py")
    print("  python test_asymmetrical_penalties.py")
