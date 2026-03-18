import asyncio
import logging
import os
# import ipdb
from typing import Dict, Any, Optional

from workflow_service.services.scraping.browsers.actors.base_actor import BaseBrowserActor
from workflow_service.services.scraping.browsers.config import SCRAPELESS_DASHBOARD_AUTOMATION
from workflow_service.services.scraping.browsers.scrapeless.scrapeless_browser import ScrapelessBrowser

logger = logging.getLogger(__name__)


class ScrapelessLoggedInBrowserActor(BaseBrowserActor):
    """
    Browser actor for automating Scrapeless dashboard operations.
    
    This actor handles:
    - Manual login flow with user interaction
    - Automatic profile creation using dashboard selectors
    - Navigation to profile management interface
    
    Key Design Decisions:
    - Uses manual login to avoid storing credentials
    - Implements robust waiting mechanisms for dashboard elements
    - Follows existing actor pattern from perplexity_logged_out.py
    
    Caveats:
    - Requires user interaction during login phase
    - Assumes specific dashboard structure and selectors
    - May need selector updates if Scrapeless UI changes
    """
    
    def __init__(self, *args, **kwargs):
        """
        Initialize the Scrapeless browser actor.
        
        Args:
            *args: Arguments passed to BaseBrowserActor
            **kwargs: Keyword arguments passed to BaseBrowserActor
        """
        super().__init__(*args, **kwargs)
        self.profile_management_url = f"https://app.scrapeless.com/{os.getenv('SCRAPELESS_USERNAME', 'your-username')}/products/browser/profiles/list"
        # self.live_url = kwargs.get("live_url")
    
    async def wait_for_manual_login(self) -> str:
        """
        Pause execution to allow user to manually log in to Scrapeless.
        
        This method:
        1. Navigates to Scrapeless dashboard
        2. Pauses with debugger for manual login
        3. Continues after user proceeds
        
        Returns:
            str: Current URL after login process
            
        Raises:
            Exception: If navigation fails or login process encounters issues
        """
        try:
            logger.info("Navigating to Scrapeless dashboard for manual login...")
            
            # Navigate to main Scrapeless page
            await self.go_to_page("https://app.scrapeless.com/")
            
            # Wait a moment for page to load
            await self.wait_for_seconds(2)
            
            logger.info("Please log in manually in the browser window...")
            logger.info("After logging in successfully, continue in the debugger...")
            # print(f"Live URL: {self.live_url}")
            logger.info(f"Live URL: {self.live_url}")
            
            # Pause for manual login - user interaction required
            import ipdb; ipdb.set_trace()
            
            logger.info("Continuing after manual login...")
            
            # Navigate to profile management page after login
            await self.go_to_page(self.profile_management_url)
            await self.wait_for_seconds(2)
            
            current_url = self.page.url
            logger.info(f"Successfully navigated to profile management: {current_url}")
            
            return current_url
            
        except Exception as e:
            logger.error(f"Error during manual login process: {e}", exc_info=True)
            raise Exception(f"Failed to complete manual login process: {e}")
    
    async def create_profile_automatically(self, profile_name) -> Dict[str, Any]:
        """
        Automatically create a new browser profile using dashboard selectors.
        
        This method implements the complete profile creation flow:
        1. Click create profile button
        2. Fill in profile name
        3. Save the profile
        4. Wait for confirmation
        
        Args:
            profile_name: Name for the new profile
            
        Returns:
            Dict containing profile creation results with keys:
            - success: bool indicating if creation succeeded
            - profile_name: str name of created profile
            - url: str current URL after creation
            - message: str status message
            
        Raises:
            Exception: If profile creation fails at any step
        """
            
        try:
            logger.info(f"Starting automatic profile creation for: {profile_name}")
            
            # Wait for and click the create profile button
            logger.info("Clicking create profile button...")
            await self.wait_and_click(
                SCRAPELESS_DASHBOARD_AUTOMATION["create_profile"],
                timeout=10000
            )
            
            # Wait for the form to appear and fill in profile name
            logger.info(f"Filling profile name: {profile_name}")
            await self.wait_and_fill(
                SCRAPELESS_DASHBOARD_AUTOMATION["form_input"],
                profile_name
            )
            
            # # Wait a moment before saving
            # await self.wait_for_seconds(1)
            
            # Click save button
            logger.info("Saving profile...")
            await self.wait_and_click(
                SCRAPELESS_DASHBOARD_AUTOMATION["save_profile"],
                timeout=5000
            )
            
            # Optimized for remote browsers: minimal operations with single ID extraction
            logger.info("Extracting profile ID (includes confirmation checks)...")
            actual_profile_id = None
            
            # Extract profile ID - this handles profile list waiting internally
            actual_profile_id = await self._extract_profile_id(profile_name)
            
            if actual_profile_id:
                success = True
                message = f"Profile created successfully with ID: {actual_profile_id}"
                logger.info(f"Successfully extracted profile ID: {actual_profile_id}")
            else:
                # Profile creation likely succeeded but ID extraction failed
                success = True
                message = "Profile creation completed (profile ID extraction failed)"
                logger.warning("Could not extract profile ID - profile likely created but ID not retrieved")
            
            # Get current URL for response
            current_url = self.page.url
            
            result = {
                "success": success,
                "profile_name": profile_name,
                "profile_id": actual_profile_id,  # Include the actual extracted profile ID
                "url": current_url,
                "message": message
            }
            
            logger.info(f"Profile creation result: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error during profile creation: {e}", exc_info=True)
            error_result = {
                "success": False,
                "profile_name": profile_name,
                "profile_id": None,  # No profile ID available on failure
                "url": self.page.url,
                "message": f"Profile creation failed: {str(e)}"
            }
            return error_result
    
    async def _extract_profile_id(self, profile_name: str) -> Optional[str]:
        """
        Extract the actual profile ID from Scrapeless dashboard using the copy button.
        
        This method (optimized for remote browsers):
        1. Waits for profile to appear in dashboard list (confirms creation success)
        2. Clicks the copy button descendant to copy profile ID to clipboard
        3. Retrieves the profile ID from clipboard
        
        Args:
            profile_name: Name of the profile to extract ID for
            
        Returns:
            str: The actual profile ID if extraction successful, None otherwise
            
        Note:
            Uses clipboard API to retrieve the copied profile ID. 
            Includes profile creation confirmation by waiting for profile list appearance.
        """
        try:
            logger.info(f"Extracting profile ID for profile: {profile_name}")
            
            # Optimized for remote browsers: single selector for copy button as descendant of profile row
            profile_list_profile_selector = SCRAPELESS_DASHBOARD_AUTOMATION["profile_list_profile_selector"].format(profile_name=profile_name)
            copy_button_selector = f"tr:has({profile_list_profile_selector}) {SCRAPELESS_DASHBOARD_AUTOMATION['profile_copy_selector']}"
            
            logger.info(f"Clicking copy button to extract profile ID...")
            
            # Single efficient operation: click copy button to copy profile ID to clipboard
            await self.wait_and_click(copy_button_selector, timeout=10000)
            
            # Minimal wait for clipboard operation (optimized for remote latency)
            await self.wait_for_seconds(0.3)
            
            # Get the profile ID from clipboard using browser clipboard API
            logger.info("Retrieving profile ID from clipboard...")
            profile_id = await self.page.evaluate("""
                async () => {
                    try {
                        // Read the profile ID that was copied to clipboard by the copy button
                        const text = await navigator.clipboard.readText();
                        console.log('Clipboard content:', text);
                        return text.trim();
                    } catch (error) {
                        console.error('Clipboard read failed - check browser permissions:', error);
                        return null;
                    }
                }
            """)
            
            if profile_id and len(profile_id) > 0:
                logger.info(f"Successfully extracted profile ID: {profile_id}")
                return profile_id
            else:
                logger.warning("Clipboard was empty or clipboard read failed")
                return None
                
        except Exception as e:
            logger.error(f"Error extracting profile ID for {profile_name}: {e}", exc_info=True)
            return None
    
    async def full_profile_creation_flow(self, profile_name: str) -> Dict[str, Any]:
        """
        Complete end-to-end profile creation flow including manual login.
        
        This is the main method that orchestrates:
        1. Manual login process
        2. Navigation to profile management
        3. Automatic profile creation
        
        Args:
            profile_name: Name for the new profile.
            
        Returns:
            Dict containing complete flow results with keys:
            - login_success: bool indicating if login succeeded
            - profile_creation: Dict with profile creation results
            - final_url: str final URL after complete process
            
        Raises:
            Exception: If any step in the flow fails critically
        """
            
        try:
            logger.info(f"Starting full profile creation flow for: {profile_name}")
            
            # Step 1: Manual login
            login_url = await self.wait_for_manual_login()
            login_success = True
            
            # Step 2: Create profile automatically
            profile_result = await self.create_profile_automatically(profile_name)
            
            # Compile final results
            final_result = {
                "login_success": login_success,
                "login_url": login_url,
                "profile_creation": profile_result,
                "final_url": self.page.url
            }
            
            logger.info(f"Complete flow finished: {final_result}")
            return final_result
            
        except Exception as e:
            logger.error(f"Error in full profile creation flow: {e}", exc_info=True)
            raise Exception(f"Profile creation flow failed: {e}")
    
    async def navigate_to_profile_management(self) -> str:
        """
        Navigate directly to the profile management URL.
        
        Utility method for direct navigation to profile list.
        
        Returns:
            str: Current URL after navigation
            
        Raises:
            Exception: If navigation fails
        """
        try:
            logger.info(f"Navigating to profile management: {self.profile_management_url}")
            await self.go_to_page(self.profile_management_url)
            await self.wait_for_seconds(1)
            
            current_url = self.page.url
            logger.info(f"Successfully navigated to: {current_url}")
            return current_url
            
        except Exception as e:
            logger.error(f"Failed to navigate to profile management: {e}", exc_info=True)
            raise Exception(f"Navigation to profile management failed: {e}")



if __name__ == "__main__":
    async def main():
        async with ScrapelessBrowser(profile_id="39fd01df-7bf9-44b5-befb-4ea5d238caf8", persist_profile=True) as browser:  # profile_id="39fd01df-7bf9-44b5-befb-4ea5d238caf8", persist_profile=True
            live_url = await browser.get_live_url()
            actor = ScrapelessLoggedInBrowserActor(browser=browser.browser, context=browser.context, page=browser.page, live_url=live_url)
            result = await actor.full_profile_creation_flow("test-profile-with-id")
            print(result)
            import ipdb; ipdb.set_trace()

    asyncio.run(main())
