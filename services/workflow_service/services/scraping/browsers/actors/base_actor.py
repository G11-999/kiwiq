import asyncio
import random
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
        await page.mouse.click(click_x, click_y)
        
        # print(f"Clicked at position: ({click_x}, {click_y})")
        # print(f"Random offset applied: {random_offset} pixels")

    async def wait_and_click(self, selector: str, timeout: int = 30000) -> str:
        """
        Wait for a CSS selector to appear then click it.

        Args:
            selector: Playwright-compatible selector.

        Returns:
            Current URL after the click.

        Raises:
            Exception: If the element can’t be interacted with.
        """
        try:
            # print(selector)
            await self.page.wait_for_selector(selector, timeout=timeout)
            await self.page.click(selector)
            return self.page.url
        except Exception as e:
            raise Exception(f"Failed to click selector '{selector}': {e}")

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
