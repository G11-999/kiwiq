import asyncio
import random
from typing import Optional
# from workflow_service.services.scraping.settings import scraping_settings
from playwright.async_api import Page, BrowserContext, Browser, ElementHandle
from time import monotonic

import logging

logger = logging.getLogger(__name__)
from global_config.logger import get_prefect_or_regular_python_logger

class BaseBrowserActor:
    def __init__(self, browser: Browser, context: BrowserContext, page: Page, *args, **kwargs):
        self.browser = browser
        self.context = context
        self.page = page
        self.live_url = kwargs.get("live_url", None)
        self.logger = get_prefect_or_regular_python_logger(self.__class__.__name__)
    
    async def click_middle_with_offset(self):
        page = self.page
        # Get viewport size
        # viewport = page.viewport_size

        dimensions = await self.page.evaluate('''() => {
            return {
                width: window.innerWidth || document.documentElement.clientWidth,
                height: window.innerHeight || document.documentElement.clientHeight
            }
        }''')
        
        # Calculate middle of the viewport
        middle_x = dimensions['width'] // 2
        middle_y = dimensions['height'] // 2
        
        # Generate random x offset between 10-100 pixels
        random_offset = random.randint(10, 100)
        
        # Calculate final click position
        click_x = middle_x + random_offset
        click_y = middle_y
        
        # Click at the calculated position
        await page.mouse.click(click_x, click_y, delay=random.randint(5, 10))
        
        # print(f"Clicked at position: ({click_x}, {click_y})")
        # print(f"Random offset applied: {random_offset} pixels")

    async def wait_and_click(self, selector: str, timeout: int = 30000, delay: Optional[int] = None) -> str:
        """
        Wait for a CSS selector to appear then click it.

        Args:
            selector: Playwright-compatible selector.

        Returns:
            Current URL after the click.

        Raises:
            Exception: If the element can’t be interacted with.
        
        TODO: better way to click using locators probably: https://claude.ai/chat/96925ea0-80be-406a-a1dd-e74e7c2382e4
        """
        try:
            # print(selector)
            # NOTE: maybe move mouse to selector and hover for 5 ms then click??
            # TODO: wait for some other event or use playwright's code to find selector instead since this sometimes don't trigger or use force click!

            await self.page.wait_for_selector(selector, timeout=timeout)
            await self.page.click(selector, delay=delay or random.randint(5, 10))  # , timeout=timeout
            return self.page.url
        except Exception as e:
            raise Exception(f"Failed to click selector '{selector}': {e}")
    
    async def wait_and_click_optional(self, selector: str, timeout: int = 1500, required: bool = False) -> tuple[bool, str]:
        """
        Attempts to click an element if it exists. Won't fail if element is not found.
        
        Args:
            selector: CSS selector to click
            timeout: Max time to wait for element
            required: If True, raises exception when element not found. If False, returns gracefully.
        
        Returns:
            Tuple of (success: bool, current_url: str)
        """
        try:
            # First, check if element exists without waiting full timeout
            try:
                # Use a short timeout to check existence
                await self.page.wait_for_selector(selector, timeout=min(timeout, 1000), state="attached")
            except:
                # Element doesn't exist, this is okay for optional elements
                if not required:
                    self.logger.debug(f"Optional selector '{selector}' not found, skipping")
                    return (False, self.page.url)
                else:
                    raise Exception(f"Required selector '{selector}' not found on page")
            
            # Element exists, now try to click it robustly
            return await self._perform_click(selector, timeout)
            
        except Exception as e:
            if required:
                raise Exception(f"Failed to click required selector '{selector}': {e}")
            else:
                self.logger.info(f"Optional click failed for '{selector}': {e}")
                return (False, self.page.url)

    async def _perform_click(self, selector: str, timeout: int = 1500) -> tuple[bool, str]:
        """
        Internal method to perform the actual click with multiple strategies.
        Assumes element exists.
        """
        locator = self.page.locator(selector).first()
        
        try:
            # Wait for element to be visible and stable
            await locator.wait_for(state="visible", timeout=timeout)
            
            # Small wait for animations/transitions to complete
            await self.page.wait_for_timeout(100)
            
            # Get element info for debugging
            is_visible = await locator.is_visible()
            is_enabled = await locator.is_enabled()
            
            if not is_visible:
                self.logger.warning(f"Element '{selector}' not visible, attempting force click")
            
            # Try multiple click strategies in order of preference
            click_strategies = [
                ("normal", self._try_normal_click),
                ("force", self._try_force_click),
                ("javascript", self._try_js_click),
                ("dispatch", self._try_dispatch_click)
            ]
            
            last_error = None
            for strategy_name, strategy_func in click_strategies:
                try:
                    await strategy_func(locator, timeout)
                    
                    # Add delay after successful click (as you had before)
                    await self.page.wait_for_timeout(random.randint(5, 10))
                    
                    self.logger.debug(f"Successfully clicked '{selector}' using {strategy_name} strategy")
                    return (True, self.page.url)
                    
                except Exception as e:
                    last_error = e
                    self.logger.debug(f"{strategy_name} click failed for '{selector}': {str(e)[:100]}")
                    continue
            
            # All strategies failed
            raise Exception(f"All click strategies failed. Last error: {last_error}")
            
        except Exception as e:
            raise Exception(f"Click failed for '{selector}': {e}")

    # Individual click strategies
    async def _try_normal_click(self, locator, timeout: int):
        """Normal Playwright click with actionability checks."""
        await locator.click(timeout=timeout, delay=random.randint(5, 10))

    async def _try_force_click(self, locator, timeout: int):
        """Force click that bypasses actionability checks."""
        await locator.click(timeout=timeout, force=True, delay=random.randint(5, 10))

    async def _try_js_click(self, locator, timeout: int):
        """JavaScript click that bypasses most visibility/overlay issues."""
        await locator.evaluate("element => element.click()")

    async def _try_dispatch_click(self, locator, timeout: int):
        """Dispatch click event directly to the element."""
        await locator.dispatch_event("click")


    async def wait_and_fill(self, selector: str, value: str) -> str:
        """
        Wait for `selector` then fill its value.

        Args:
            selector: CSS selector.
            value: Text to fill.

        Returns:
            Current URL.

        Raises:
            Exception: On timeout or fill error.
        """
        try:
            # print(selector, value)
            await self.page.wait_for_selector(selector)
            await self.page.fill(selector, value)
            return self.page.url
        except Exception as e:
            raise Exception(f"Failed to fill selector '{selector}': {e}")

    async def wait_for_seconds(self, seconds: int, add_noise: bool = True, noise_fraction: float = 0.1) -> str:
        """
        Passive sleep helper (async-friendly).

        Args:
            seconds: How long to wait.

        Returns:
            Current URL after the wait.
        """
        try:
            noise = 0
            if add_noise:
                noise = random.randint(100, 1200)
                if noise_fraction:
                    base_range = int(seconds * 1000 * noise_fraction)
                    noise = random.randint(base_range, base_range * 2)
            await self.page.wait_for_timeout(int(seconds * 1000) + noise)
            return self.page.url
        except Exception as e:
            raise Exception(f"Failed to wait for {seconds} seconds: {e}")

    async def go_to_page(self, url: str, timeout: int = 30000) -> str:
        """
        Navigate the active tab to `url`.

        Args:
            url: Destination.

        Returns:
            Final URL after navigation.
        """
        try:
            await self.page.goto(url, timeout=timeout)
            return self.page.url
        except Exception as e:
            raise Exception(f"Failed to go to page '{url}': {e}")
    
    async def poll_until_stable(
        self,
        element: ElementHandle,
        interval: float = 3.0,
        timeout: float = 180.0,
        stable_count_required: int = 2
    ) -> str:
        """
        Poll `await element.inner_text()` every `interval` seconds.
        Return as soon as text is identical for 2 consecutive checks,
        or raise TimeoutError after `timeout` seconds.
        Uses time.monotonic() to measure elapsed time.
        """
        start = monotonic()
        prev_text = None
        stable_count = 0

        while True:
            current = (await element.inner_text()).strip()

            if prev_text is not None and current == prev_text:
                stable_count += 1
                if stable_count >= stable_count_required:
                    return current
            else:
                stable_count = 0

            prev_text = current

            # timeout based on monotonic clock
            if monotonic() - start > timeout:
                raise TimeoutError(
                    f"Timed out after {timeout}s; last observed text was: '{current}'"
                )

            await asyncio.sleep(interval)
