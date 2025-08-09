import logging
import asyncio
import random
import traceback
# from workflow_service.services.scraping.settings import scraping_settings
from urllib.parse import urlencode
from typing import Optional, List, Dict, Tuple
from bs4 import BeautifulSoup
from bs4.element import Tag
import re
from time import monotonic

from workflow_service.services.scraping.browsers.actors.base_actor import BaseBrowserActor
from workflow_service.services.scraping.browsers.config import OPENAI_SELECTORS
from workflow_service.services.scraping.utils.markdown_converter import convert_to_markdown_from_raw_file_content

# logger = logging.getLogger(__name__)


class OpenAIBrowserActor(BaseBrowserActor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    async def wait_until_chatgpt_response_complete(
        self,
        poll_every: float = 10.0,
        timeout: float = 200.0,
    ) -> List[Dict[str, str]]:
        """
        Re‑run `extract_response_from_chatgpt_page()` in a loop until no additional
        characters appear in the answers (i.e. the model finished streaming).

        Args:
            poll_every: Seconds to wait between polls.
            timeout:    Max seconds to wait before giving up.

        Returns:
            The final list of {"question","answer","question_html","answer_html","links","citations"} pairs.

        Raises:
            TimeoutError: If the response never stabilises within `timeout`.
        """
        start_time           = monotonic()
        last_total_char_cnt  = -1          # force first loop to run
        stable_iterations    = 0
        STABLE_REQUIRED      = 2           # need the same length twice in a row

        while True:
            raw_html = await self.page.evaluate("() => document.documentElement.outerHTML")
            full_html = "<!DOCTYPE html>\n" + raw_html
            pairs = await asyncio.to_thread(self.extract_response_from_chatgpt_page, full_html)
            # concatenate all answers and count characters
            total_chars = sum(len(p["text"]) for p in pairs)

            if total_chars == last_total_char_cnt:
                stable_iterations += 1
            else:
                stable_iterations = 0      # reset if it changed

            if stable_iterations >= STABLE_REQUIRED:
                return pairs               # text stopped growing

            # timeout guard
            if monotonic() - start_time > timeout:
                raise TimeoutError("ChatGPT response did not stabilise in time")

            last_total_char_cnt = total_chars
            await asyncio.sleep(poll_every)
    
    def extract_response_from_chatgpt_page(self, full_html: str) -> list[dict]:
        """
        Capture current page HTML, pull every 'You said:' → 'ChatGPT said:' turn,
        collapse whitespace, return list of {'question','answer','question_html','answer_html','links','citations'}.
        """
        # --- grab full DOM HTML ------------------------------------
        

        # --- parse & extract ---------------------------------------
        soup = BeautifulSoup(full_html, "html.parser")
        headings = soup.select("h5.sr-only, h6.sr-only")

        user_re = re.compile(r"\byou\b", re.I)
        bot_re  = re.compile(r"\bchatgpt\b", re.I)

        def extract_links_and_citations(html_content: str) -> tuple[list, list]:
            """Extract links and citations from HTML content"""
            if not html_content:
                return [], []
            
            soup_content = BeautifulSoup(html_content, "html.parser")
            
            # Extract links
            links = []
            for a_tag in soup_content.find_all("a", href=True):
                link_data = {
                    "url": a_tag["href"],
                    "text": a_tag.get_text(strip=True),
                    "title": a_tag.get("title", "")
                }
                if link_data["url"] and not link_data["url"].startswith("#"):  # Skip anchor links
                    links.append(link_data)
            
            # Extract citations (look for citation patterns like [1], (1), etc.)
            citations = []
            citation_patterns = [
                r'\[(\d+)\]',  # [1], [2], etc.
                r'\((\d+)\)',  # (1), (2), etc.
                r'(?:Source|Ref|Reference):\s*(.+?)(?:\n|$)',  # Source: text
                r'(?:Citation|Cite):\s*(.+?)(?:\n|$)',  # Citation: text
            ]
            
            text_content = soup_content.get_text()
            for pattern in citation_patterns:
                matches = re.findall(pattern, text_content, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    if match and match.strip():
                        citations.append(match.strip())
            
            return links, citations

        def next_text_div(tag: Tag) -> tuple[str, str]:
            """Returns (text_content, html_content)"""
            div = tag.find_next("div")
            while div and not div.get_text(strip=True):
                div = div.find_next("div")
            if div:
                text_content = div.get_text(" ", strip=True)
                html_content = str(div)
                return text_content, html_content
            return "", ""

        def clean_ws(txt: str) -> str:
            return re.sub(r"\s+", " ", txt).strip()

        pairs, current_q, current_q_html = [], None, None
        for h in headings:
            label = h.get_text(strip=True)

            if user_re.search(label):
                text, html = next_text_div(h)
                current_q = text
                current_q_html = html

            elif bot_re.search(label) and current_q is not None:
                text, html = next_text_div(h)
                links, citations = extract_links_and_citations(html)
                pairs.append({
                    "query": clean_ws(current_q),
                    "text": clean_ws(text),
                    # "question_html": current_q_html,
                    "html": html,
                    "links": links,
                    "citations": citations,
                    "markdown": convert_to_markdown_from_raw_file_content(html),
                })
                current_q = None
                current_q_html = None

        return pairs
    
    async def single_query(self, query: str) -> List[Dict[str, str]]:
        async def close_popup():
            try:
                await self.wait_and_click(OPENAI_SELECTORS["close_popup"], timeout=1500)
                await self.wait_for_seconds(0.1, add_noise=True)
                self.logger.info(f"SUCCESS: Close popup button clicked")
            except Exception as e:
                self.logger.info(f"Close popup button not found: {e}")
        
        async def short_prompt_focus_sequence():
            await self.click_middle_with_offset()
            try:
                await self.wait_and_click(OPENAI_SELECTORS["stay_logged_out"], timeout=500)
                self.logger.info(f"SUCCESS: Stay logged out button clicked")
                await self.wait_for_seconds(0.1, add_noise=True)

            except Exception as e:
                self.logger.info(f"Stay logged out button not found: {e}")
            
            await close_popup()
            
            try:
                await self.wait_and_click(OPENAI_SELECTORS["search_web_no_login"], timeout=1500)
                # await self.page.click(OPENAI_SELECTORS["search_web_no_login"], timeout=1500)
                self.logger.info(f"SUCCESS: Search web no login button clicked")
                return True
            except Exception as e:

                await close_popup()

                self.logger.info(f"Search web no login button not found: {e}")
            return False
        
        clicked = False

        try:
            await self.go_to_page(OPENAI_SELECTORS["base_url"], timeout=10000)
        except Exception as e:
            self.logger.error(f"Error going to page: {e}")
            clicked = await short_prompt_focus_sequence()
            if not clicked:
                try:
                    await self.go_to_page(OPENAI_SELECTORS["base_url"], timeout=20000)
                    # NOTE: here you can try short focus sequence again and wait 10-20s as last resort, to counter any captchas!
                except Exception as e:
                    self.logger.error(f"Error going to page: {e}")

        # pause_until_confirm()
        # await self.page.reload()
        # # pause_until_confirm()
        if not clicked:
            clicked = await short_prompt_focus_sequence()
            if not clicked:
                clicked = await short_prompt_focus_sequence()
        
        await close_popup()

        # Send Q1
        await self.wait_for_seconds(0.25, add_noise=True)
        await self.wait_and_click(OPENAI_SELECTORS["prompt_input"])
        await self.wait_for_seconds(0.25, add_noise=True)
        # pause_until_confirm()
        await self.page.keyboard.type(query, delay=random.randint(1, 5))
        await self.wait_for_seconds(0.25, add_noise=True)

        await close_popup()

        try:
            await self.wait_and_click(OPENAI_SELECTORS["send_button"], timeout=1000)
        except Exception as e:
            self.logger.info(f"Send button not found: {e}")
            await close_popup()
            await self.wait_and_click(OPENAI_SELECTORS["send_button"])
        # pause_until_confirm()

        try:
            await self.wait_and_click(OPENAI_SELECTORS["stay_logged_out"], timeout=1000)
            self.logger.info(f"Stay logged out button clicked")
            await self.wait_for_seconds(0.1, add_noise=True)
        except Exception as e:
            self.logger.info(f"Stay logged out button not found: {e}")

        # Wait for GPT to finish
        pairs = await self.wait_until_chatgpt_response_complete()
        
        return pairs
    
    async def chatgpt_conversation(self, Q1: str, Q2: str, Q3: str, enable_search: bool = True):
        try:
            await self.go_to_page(OPENAI_SELECTORS["base_url"], timeout=10000)
        except Exception as e:
            self.logger.error(f"Error going to page: {e}")
            await self.go_to_page(OPENAI_SELECTORS["base_url"], timeout=20000)

        # pause_until_confirm()
        # await self.page.reload()
        # # pause_until_confirm()
        try:
            await self.wait_and_click(OPENAI_SELECTORS["stay_logged_out"], timeout=500)
            self.logger.info(f"Stay logged out button clicked")
            await self.wait_for_seconds(0.1, add_noise=True)
        except Exception as e:
            self.logger.info(f"Stay logged out button not found: {e}")
        # pause_until_confirm()
        # await self.page.reload()
        # # pause_until_confirm()

        if enable_search:
            await self.wait_and_click(OPENAI_SELECTORS["search_web_no_login"])
            await self.wait_for_seconds(1, add_noise=True)

        # Send Q1
        await self.wait_for_seconds(0.5, add_noise=True)
        await self.wait_and_click(OPENAI_SELECTORS["prompt_input"])
        await self.wait_for_seconds(0.5, add_noise=True)
        # pause_until_confirm()
        await self.page.keyboard.type(Q1, delay=random.randint(3, 15))
        await self.wait_for_seconds(0.5, add_noise=True)
        await self.wait_and_click(OPENAI_SELECTORS["send_button"])
        # pause_until_confirm()

        # Wait for GPT to finish
        pairs = await self.wait_until_chatgpt_response_complete() 
        print(pairs)
        # pause_until_confirm()

        # Send Q2
        await self.wait_and_click(OPENAI_SELECTORS["prompt_input"])
        await self.wait_for_seconds(0.5, add_noise=True)
        # pause_until_confirm()
        await self.page.keyboard.type(Q2, delay=random.randint(3, 15))
        await self.wait_for_seconds(0.5, add_noise=True)
        await self.wait_and_click(OPENAI_SELECTORS["send_button"])
        # pause_until_confirm()

        # Final wait for answer streaming
        pairs = await self.wait_until_chatgpt_response_complete() 
        print(pairs)
        # pause_until_confirm()

        # Send Q3
        await self.wait_and_click(OPENAI_SELECTORS["prompt_input"])
        await self.wait_for_seconds(0.5, add_noise=True)
        # pause_until_confirm()
        await self.page.keyboard.type(Q3, delay=random.randint(3, 15))
        await self.wait_for_seconds(0.5, add_noise=True)
        # pause_until_confirm()
        await self.wait_and_click(OPENAI_SELECTORS["send_button"])
        # pause_until_confirm()
        # await bot.wait_for_seconds(20)

        # Capture full page HTML
        pairs = await self.wait_until_chatgpt_response_complete() 
        print(pairs)
        
        # await self.close()

if __name__ == "__main__":
    from workflow_service.services.scraping.browsers.scrapeless.scrapeless_browser import ScrapelessBrowser
    async def main():
        async with ScrapelessBrowser() as browser:  # profile_id="39fd01df-7bf9-44b5-befb-4ea5d238caf8", persist_profile=True
            live_url = await browser.get_live_url()
            print("\n\nlive_url: ---> ",live_url)
            import ipdb; ipdb.set_trace()
            actor = OpenAIBrowserActor(browser=browser.browser, context=browser.context, page=browser.page, live_url=live_url)
            # try:
            #      result = await actor.chatgpt_conversation("What is the capital of France?", "What is the capital of Italy?", "What is the capital of Germany?")
            #      print(result)
            # except Exception as e:
            #     print(f"Error: {e}")
            #     # await actor.wait_and_click("h1:has-text('Welcome back')")
            #     # await actor.go_to_page(OPENAI_SELECTORS["base_url"])
            
            result = await actor.single_query("What is the capital of France?")
            print(result)
            import ipdb; ipdb.set_trace()

    asyncio.run(main())
