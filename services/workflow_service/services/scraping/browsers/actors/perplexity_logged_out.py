

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
from workflow_service.services.scraping.browsers.config import PERPLEXITY_SELECTORS
from workflow_service.services.scraping.utils.markdown_converter import convert_to_markdown_from_raw_file_content

# logger = logging.getLogger(__name__)


class PerplexityBrowserActor(BaseBrowserActor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    async def close_popup(self, timeout=5000, popup: bool = True, popup_floater: bool = True) -> tuple[bool, bool]:
        """
        Attempts to close any popup that might appear on Perplexity.
        
        Returns:
            bool: True if a popup was found and closed, False otherwise.
        """
        closed_popup = False
        closed_popup_floater = False
        if popup:
            try:
                # Wait a short time for popup to potentially appear
                await self.wait_and_click(PERPLEXITY_SELECTORS["close_popup"], timeout=timeout, delay=50)  # , timeout=timeout
                closed_popup = True
            except Exception as e:
                # No popup found or couldn't close it - this is fine
                self.logger.warning(f"Error closing popup: {e}", exc_info=True)
        
        if popup_floater:
            try:
                # Wait a short time for popup to potentially appear
                await self.wait_and_click(PERPLEXITY_SELECTORS["close_popup_floater"], timeout=timeout, delay=50)
                closed_popup_floater = True
            except Exception as e:
                # No popup found or couldn't close it - this is fine
                self.logger.warning(f"Error closing FLOATING popup: {e}", exc_info=True)
        
        return closed_popup, closed_popup_floater

    async def wait_for_generation_start(
        self,
        timeout: float = 30.0,
    ) -> bool:
        """
        Wait until Perplexity starts generating a response.

        Strategy:
        - Wait for presence of a div with class "prose" which wraps the streaming
          answer content in Perplexity UI.

        Args:
            timeout: Maximum seconds to wait before giving up.

        Returns:
            True when the response container appears.

        Raises:
            TimeoutError if the response container is not detected within `timeout`.
        """
        try:
            # Use Playwright to wait for any element with class 'prose'
            # which indicates the answer content is rendering/streaming.
            await self.page.wait_for_selector(PERPLEXITY_SELECTORS["answer_marker"], timeout=int(timeout * 1000))
            return True
        except Exception as e:
            raise TimeoutError(f"Did not detect Perplexity response container ({PERPLEXITY_SELECTORS['answer_marker']}) in time: {e}")

    async def scroll_to_bottom_once(self) -> None:
        """
        Scroll to the bottom of the page one time.

        Useful for revealing toolbars like the Copy button that are positioned
        near the turn footer.
        """
        try:
            await self.page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        except Exception as e:
            self.logger.info(f"Single scroll to bottom failed (non-fatal): {e}")

    def parse_links_and_citations_from_copied_text(self, copied_text: str) -> tuple[list[dict], dict[str, str]]:
        """
        Parse numbered link references from copied text and build citations that
        correspond only to the numbers shown to the left of each URL.

        Expected trailing format:
            [1] https://example.com/foo
            [2] https://another.example/bar

        Returns:
            (links, citations)
            - links: list of dicts with keys: url
            - citations: list of bracketed reference numbers, e.g., ["[1]", "[2]"]
              in the same order as the links list so they can be joined later by
              citation indices in text.

        Note:
            We intentionally do NOT parse other inline citations from the body.
            Only the explicit reference list at the end is used to build citations.
        """
        if not copied_text:
            return [], []

        # Build mapping and ordered list from reference number to URL from the
        # reference list at the end, preserving original order of appearance.
        ref_pattern = re.compile(r"^\[(\d+)\]\s+(https?://\S+)", re.MULTILINE)
        num_to_url: dict[str, str] = {}
        ref_order: list[str] = []
        for match in ref_pattern.finditer(copied_text):
            ref_num = match.group(1).strip()
            url = match.group(2).strip()
            # Strip trailing punctuation that might be captured
            url = url.rstrip(').,;')
            num_to_url[ref_num] = url
            ref_order.append(ref_num)

        # Construct links in the same order as their reference numbers
        links: list[dict] = []
        for ref_num in ref_order:
            url = num_to_url.get(ref_num, "")
            if not url:
                continue
            try:
                links.append({
                    "url": url,
                })
            except Exception:
                continue

        # Citations strictly derived from the reference list, formatted with brackets
        citations = num_to_url

        citations = [{k: v} for k, v in num_to_url.items()]

        return links, citations

    async def extract_via_copy_button_after_start(
        self,
        query: str,
        wait_timeout: int = 10,
        copied: bool = False,
        iteration: int = 0,
    ) -> tuple[Optional[Dict[str, str]], bool]:
        """
        Extraction strategy: once generation starts, scroll to bottom once, then
        wait for the Copy button and click it. Attempt to read the copied content
        from clipboard and return it.

        This does not wait for response completion; it captures whatever is
        available at click time. Upstream callers may still fall back to the
        DOM-based stable extraction for a complete answer.

        Args:
            query: The user query associated with this answer.
            wait_timeout: Timeout (s) to wait for the Copy button.

        Returns:
            A dict payload conforming to the existing extraction format, or None
            if clipboard read fails or button is not found.
            Copied: True if the copy button was clicked, False otherwise.
        """
        try:
            # 1) Wait for any signal that generation has started
            if not iteration:
                await self.wait_for_generation_start()

            # 2) Reveal tools that may sit near the footer
            await self.scroll_to_bottom_once()

            # 3) Wait for and click the Copy button
            if not copied:
                try:
                    # await self.page.wait_for_selector(PERPLEXITY_SELECTORS["copy_button"], timeout=int(wait_timeout * 1000))
                    await self.wait_and_click(PERPLEXITY_SELECTORS["copy_button"], timeout=int(wait_timeout * 1000), delay=50)
                    copied = True
                    await self.wait_for_seconds(1)
                except Exception as e:
                    self.logger.info(f"Copy button not found/clickable yet: {e}")
                    return None, copied
            
            # raw_html  = await self.page.evaluate("() => document.documentElement.outerHTML")
            # full_html = "<!DOCTYPE html>\n" + raw_html

            # 4) Brief pause to allow clipboard operation to resolve
            

            # 5) Try to read copied content from clipboard
            try:
                # self.logger.info(f"Attempting to read clipboard...")
                copied_text = await self.page.evaluate(
                    """
                    async () => {
                        try {
                            const text = await navigator.clipboard.readText();
                            return (text || '').trim();
                        } catch (err) {
                            // console.error('navigator.clipboard.readText failed', err);
                            return '';
                        }
                    }
                    """
                )
                if not copied_text:
                    self.logger.info(f"Clipboard read failed!")
                # else:
                #     self.logger.info(f"Copied SUCCESS: {copied_text}")
            except Exception as e:
                self.logger.info(f"Clipboard read failed: {e}")
                copied_text = ""

            if copied_text:
                links, citations = self.parse_links_and_citations_from_copied_text(copied_text)
                payload = {
                    "query": query,
                    "text": copied_text,
                    "html": "",
                    "links": links,
                    "citations": citations,
                    "markdown": copied_text,
                }
                return payload, copied

            return None, copied

        except Exception as e:
            # Do not fail the overall flow if this quick strategy fails
            self.logger.info(f"Copy-button extraction strategy failed (non-fatal): {e}")
            return None, copied

    async def wait_until_perplexity_response_complete(
        self,
        query: Optional[str] = None,
        poll_every: float = 2.0,
        timeout: float = 200.0,
        closed_popup: bool = False,
        closed_popup_floater: bool = False,
    ) -> List[Dict[str, str]]:
        """
        Poll `extract_response_from_perplexity_page()` until the combined
        character count of all answer segments no longer grows
        (i.e. streaming finished).

        Prints a short status line each time new content appears.

        Args:
            query:      the query that was sent to Perplexity.
            poll_every: seconds between polls.
            timeout:    maximum seconds to wait.
            closed_popup:       True if the popup was closed, False otherwise.
            closed_popup_floater: True if the floating popup was closed, False otherwise.

        Returns:
            Final list of answer segment dictionaries with 'text', 'html', 'links', and 'citations' keys.

        Raises:
            TimeoutError if the response never stabilises within `timeout`.
        """
        start_time          = monotonic()
        last_char_count     = -1
        stable_iterations   = 0
        STABLE_REQUIRED     = 2      # must see same length twice

        self.logger.debug(" Waiting for Perplexity to finish streaming…")
        copied = False
        # closed_popup = False
        # closed_popup_floater = False
        iteration = 0

        while True:
            
            # 1. grab full HTML
            # raw_html  = await self.page.evaluate("() => document.documentElement.outerHTML")
            # full_html = "<!DOCTYPE html>\n" + raw_html
            # self.logger.info(f"full_html extracted!")
            if (not closed_popup_floater) or (not closed_popup):
                closed_popup, closed_popup_floater = await self.close_popup(popup=(not closed_popup), popup_floater=(not closed_popup_floater))
                # overwrite closed_popup, we don't want to try it again!
                closed_popup = True
            payload, copied = await self.extract_via_copy_button_after_start(query, wait_timeout=poll_every, copied=copied, iteration=iteration)
            if payload:
                return [payload]
            # segments = await asyncio.to_thread(self.extract_response_from_perplexity_page, full_html)
            # self.logger.info(f"segments extracted!")

            # total    = sum(len(s["text"]) for s in segments)

            # #  growth check
            # if total == last_char_count:
            #     stable_iterations += 1
            # else:
            #     stable_iterations  = 0
            #     self.logger.debug(f"… still generating ({total} chars captured)")  # progress

            # # done?
            # if stable_iterations >= STABLE_REQUIRED:
            #     self.logger.debug("Perplexity response complete.")
            #     return segments

            # timeout guard
            if monotonic() - start_time > timeout:
                raise TimeoutError("Perplexity answer did not stabilise in time")

            # last_char_count = total
            await asyncio.sleep(poll_every)
    
    def extract_response_from_perplexity_page(self, full_html: str) -> list[dict]:
        """
        Pull the current Perplexity page's DOM, locate every *Answer/Answer* pair,
        and return the plain-text, HTML, links, and citations that appears **between** pairs and **after** the
        last pair (the pre-amble before the first pair is skipped).  Whitespace is
        collapsed to single spaces.  The result is a list of dictionaries with 'text', 'html', 'links', and 'citations' keys
        in the order they appear on the page.
        """
        
        def extract_perplexity_links_and_citations(html_content: str) -> tuple[list, list]:
            """Extract links and citations specifically for Perplexity format"""
            if not html_content:
                return [], []
            
            soup_content = BeautifulSoup(html_content, "html.parser")
            
            # Extract links
            links = []
            for a_tag in soup_content.find_all("a", href=True):
                link_data = {
                    "url": a_tag["href"],
                    "text": a_tag.get_text(strip=True),
                    "title": a_tag.get("title", ""),
                    "class": a_tag.get("class", [])
                }
                if link_data["url"] and not link_data["url"].startswith("#"):  # Skip anchor links
                    links.append(link_data)
            
            # Extract Perplexity-style citations
            citations = []
            text_content = soup_content.get_text()
            
            # Perplexity citation patterns
            citation_patterns = [
                r'\[(\d+)\]',  # [1], [2], etc.
                r'(?:^|\s)(\d+)\.?\s',  # 1. 2. etc. at start of line
                r'(?:Source|Sources?):\s*(.+?)(?:\n|$)',  # Source: text
                r'(?:Reference|References?):\s*(.+?)(?:\n|$)',  # Reference: text
                r'(?:Citation|Citations?):\s*(.+?)(?:\n|$)',  # Citation: text
                r'(?:Via|From):\s*(.+?)(?:\n|$)',  # Via: text, From: text
            ]
            
            for pattern in citation_patterns:
                matches = re.findall(pattern, text_content, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    if match and match.strip() and len(match.strip()) > 1:
                        citations.append(match.strip())
            
            # Look for citation elements by class/attribute (Perplexity specific)
            citation_elements = soup_content.find_all(attrs={"class": re.compile(r"citation|reference|source", re.I)})
            for elem in citation_elements:
                citation_text = elem.get_text(strip=True)
                if citation_text and citation_text not in citations:
                    citations.append(citation_text)
            
            # Look for numbered references in superscript or similar
            sup_elements = soup_content.find_all(["sup", "sub"])
            for elem in sup_elements:
                sup_text = elem.get_text(strip=True)
                if sup_text.isdigit() and sup_text not in citations:
                    citations.append(sup_text)
            
            return links, citations

        # 2. locate every "…>Answer<…" tag
        answer_rx = re.compile(r">\s*Answer\s*<", re.I)
        hits      = list(answer_rx.finditer(full_html))
        pair_cnt  = len(hits) // 2
        if pair_cnt == 0:
            return []   # nothing to extract

        # 3. build slice boundaries
        cuts = [0]
        for i in range(pair_cnt):
            first, second = hits[2 * i], hits[2 * i + 1]
            cuts.extend((first.start(), second.end()))
        cuts.append(len(full_html))
        cuts = sorted(set(cuts))

        # 4. keep slices *outside* the Answer/Answer blocks,
        #    skipping the very first slice (pre-amble)
        segments: list[dict] = []
        for idx, (a, b) in enumerate(zip(cuts, cuts[1:])):
            # idx 0  = before first pair → skip
            # even idx ≥2 = between pairs or after last pair → keep
            if idx != 0 and idx % 2 == 0:
                seg_html = full_html[a:b]
                text = BeautifulSoup(seg_html, "html.parser").get_text(" ", strip=True)
                text = re.sub(r"\s+", " ", text).strip()
                if text:
                    links, citations = extract_perplexity_links_and_citations(seg_html)
                    segments.append({
                        "text": text,
                        "html": seg_html,
                        "links": links,
                        "citations": citations,
                        "markdown": convert_to_markdown_from_raw_file_content(seg_html),
                    })

        return segments

    async def single_query(self, query: str) -> List[Dict[str, str]]:
        async def short_prompt_focus_sequence():
            try:
                # await self.wait_and_click(PERPLEXITY_SELECTORS["close_popup"], timeout=500)
                closed_popup, closed_popup_floater = await self.close_popup()
                if closed_popup or closed_popup_floater:
                    await self.wait_for_seconds(0.1)
            except Exception as e:
                self.logger.info(f" close popup not found: {e}")
            
            try:
                await self.wait_and_click(PERPLEXITY_SELECTORS["prompt_input"], timeout=5000, delay=50)
                return True, closed_popup, closed_popup_floater
            except Exception as e:
                self.logger.info(f" prompt input not found: {e}")
            
            return False, closed_popup, closed_popup_floater
            
        clicked = False
        try:
            await self.go_to_page(PERPLEXITY_SELECTORS["base_url"], timeout=15000)
        except Exception as e:
            self.logger.warning(f"Error going to page: {e}")
            clicked, closed_popup, closed_popup_floater = await short_prompt_focus_sequence()

            if not clicked:
                try:
                    current_url = self.page.url
                    self.logger.info(f"Current URL: {current_url}")
                    if (not current_url.strip(" /").startswith(PERPLEXITY_SELECTORS["base_url"].strip(" /"))):  #  (not current_url) or  current_url != OPENAI_SELECTORS["base_url"]
                        await self.go_to_page(PERPLEXITY_SELECTORS["base_url"], timeout=10000)
                except Exception as e:
                    self.logger.warning(f"Error going to page: {e}")
        
        if not clicked:
            clicked, closed_popup, closed_popup_floater = await short_prompt_focus_sequence()
        
        await self.wait_for_seconds(1)
        
        await self.page.keyboard.type(query, delay=random.randint(1, 5))

        # Press Enter to submit
        await self.page.keyboard.press("Enter")

        # try:
        #     # await self.wait_and_click(PERPLEXITY_SELECTORS["close_popup"], timeout=1000)
        #     await self.wait_for_seconds(0.5)
        #     await self.close_popup(timeout=3000)
        #     await self.wait_for_seconds(0.1)
        # except Exception as e:
        #     self.logger.info(f" close popup not found: {e}")
        
        answers = await self.wait_until_perplexity_response_complete(query, closed_popup=closed_popup, closed_popup_floater=closed_popup_floater)
        # if answers and isinstance(answers[-1], dict) and "query" not in answers[-1]:
        #     answers[-1]["query"] = query
        
        return answers
    
    async def perplexity_conversation(self, Q1: str, Q2: str, Q3: str):
        await self.go_to_page(PERPLEXITY_SELECTORS["base_url"])
 
        # Inject localStorage (page-scope) and reload so Perplexity picks it up
        
        await self.wait_for_seconds(1)
        
        # Focus the textarea and type your prompt  
        # await self.wait_and_fill(PERPLEXITY_SELECTORS['prompt_input'], Q1)

        await self.wait_and_click(PERPLEXITY_SELECTORS["prompt_input"])
        await self.page.keyboard.type(Q1, delay=random.randint(1, 5))

        # Press Enter to submit
        await self.page.keyboard.press("Enter")
        
        
        answers = await self.wait_until_perplexity_response_complete()
        print(answers)
        
        # Try to close popup after first response
        # await self.close_popup()
        
        # await self.wait_and_fill(PERPLEXITY_SELECTORS['prompt_input'], Q2)
        await self.wait_and_click(PERPLEXITY_SELECTORS["prompt_input"]) 
        await self.page.keyboard.type(Q2, delay=random.randint(3, 15))

        # Press Enter to submit
        await self.page.keyboard.press("Enter")
        
        answers = await self.wait_until_perplexity_response_complete()
        print(answers)
        
        # Try to close popup after second response
        # await self.close_popup()
        
        # await self.wait_and_fill(PERPLEXITY_SELECTORS['prompt_input'], Q3)
        await self.wait_and_click(PERPLEXITY_SELECTORS["prompt_input"]) 
        await self.page.keyboard.type(Q3, delay=random.randint(3, 15))

        # Press Enter to submit
        await self.page.keyboard.press("Enter")
        
        answers = await self.wait_until_perplexity_response_complete()
        print(answers)
        
        # Try to close popup after third response
        # await self.close_popup()

        # # pause_until_confirm()
        # import ipdb; ipdb.set_trace()


if __name__ == "__main__":
    from workflow_service.services.scraping.browsers.scrapeless.scrapeless_browser import ScrapelessBrowser
    async def main():
        async with ScrapelessBrowser() as browser:  # profile_id="39fd01df-7bf9-44b5-befb-4ea5d238caf8", persist_profile=True
            live_url = await browser.get_live_url()
            print("\n\nlive_url: ---> ",live_url)
            import ipdb; ipdb.set_trace()
            actor = PerplexityBrowserActor(browser=browser.browser, context=browser.context, page=browser.page, live_url=live_url)
            result = await actor.single_query("What is the capital of France?")
            import json
            print(json.dumps(result, indent=4))
            """
            [
                {
                    "text": "/div> Images Sources \u00b7 Steps wikimedia foundation, inc. France - Wikipedia encyclopedia britannica France | History, Maps, Flag, Population, Cities, Capital, & Facts wikimedia foundation, inc. Kingdom of France - Wikipedia airline tickets: cheap flights to france & worldwide | air france usa | air france, united states Airline tickets: cheap flights to France & worldwide | Air France USA The capital of France is Paris . wikipedia +1 Paris serves as the country's largest city as well as its main cultural and economic center. As the seat of government, it is the location of major institutions including the presidential residence and both houses of Parliament (the Senate and National Assembly). France has had Paris as its capital since before the medieval period, and it remains widely recognized as a global city for its influence in art, culture, politics, and finance. britannica +1 Share Export Rewrite Related What are the main geographical features of France How has France's his2025-08-11 16:05:03,852 - PerplexityBrowserActor - INFO - segments extracted!
            tory influenced its current political structure What are the key cultural traditions unique to France How do France's overseas territories impact its global presence What are the economic strengths and challenges of France Ask a follow-up\u2026 Sign in or create an account Unlock Pro Search and History Continue with Google Continue with Apple Continue with email Single sign-on (SSO)",
                    "html": "",
                    "links": [
                        {
                            "url": "https://en.wikipedia.org/wiki/France",
                            "text": "wikimedia foundation, inc.France - Wikipedia",
                            "title": "",
                            "class": [
                                "group",
                                "flex",
                                "w-full",
                                "cursor-pointer",
                                "items-stretch",
                                "h-full"
                            ]
                        },
                    ],
                    "citations": [
                        "wikipedia+1",
                        "britannica+1"
                    ],
                    "markdown": "/div>\n\nImages\n\nSources\n\n\u00b7\n\nSteps\n\n[wikimedia foundation, inc.\n\nFrance - Wikipedia](https://en.wikipedia.org/wiki/France)\n\n[encyclopedia britannica\n\nFrance | History, Maps, Flag, Population, Cities, Capital, & Facts](https://www.britannica.com/place/France)\n\n[wikimedia foundation, inc.\n\nKingdom of France - Wikipedia](https://en.wikipedia.org/wiki/Kingdom_of_France)\n\n[airline tickets: cheap flights to france & worldwide | air france usa | air france, united states\n\nAirline tickets: cheap flights to France & worldwide | Air France USA](https://wwws.airfrance.us)\n\n![Al-Sharaa's visit to France: A European gateway towards ...](https://d2u1z1lopyfwlx.cloudfront.net/thumbnails/4db3a823-5133-5849-ae0e-2f45268147ae/971c32be-5eed-5cff-ad6c-b82aa22c2583.jpg)\n\n![Overseas France - Wikipedia](https://d2u1z1lopyfwlx.cloudfront.net/thumbnails/014aa4c7-5253-5675-80a2-d416628774f9/01a84265-e09c-5682-92ce-681c89a1afe2.jpg)\n\n![German military administration in occupied France during ...](https://d2u1z1lopyfwlx.cloudfront.net/thumbnails/4ddd2748-1588-572e-b6ba-55ca572caad1/01a84265-e09c-5682-92ce-681c89a1afe2.jpg)\n\n![Macron asks Syria\u2019s interim President al-Sharaa to protect all Syrians  during Elys\u00e9e visit](https://d2u1z1lopyfwlx.cloudfront.net/thumbnails/cfb791da-a2f5-5d93-8b19-1d6f3bcee02b/030f02cd-5c6f-5002-8969-b27852e7c726.jpg)\n\n![France | History, Maps, Flag, Population, Cities, Capital ...](https://d2u1z1lopyfwlx.cloudfront.net/thumbnails/d44e0360-06f7-5e78-909b-013f2be1619f/e91e73d4-022b-59db-9713-717a2a198855.jpg)\n\nThe **capital of France is Paris**.[wikipedia+1](https://en.wikipedia.org/wiki/France)\n\nParis serves as the country's largest city as well as its main cultural and economic center. As the seat of government, it is the location of major institutions including the presidential residence and both houses of Parliament (the Senate and National Assembly). France has had Paris as its capital since before the medieval period, and it remains widely recognized as a global city for its influence in art, culture, politics, and finance.[britannica+1](https://www.britannica.com/place/France)\n\nShare\n\nExport\n\nRewrite\n\nRelated\n\nWhat are the main geographical features of France\n\nHow has France's history influenced its current political structure\n\nWhat are the key cultural traditions unique to France\n\nHow do France's overseas territories impact its global presence\n\nWhat are the economic strengths and challenges of France\n\nAsk a follow-up\u2026\n\nSign in or create an account\n\nUnlock Pro Search and History\n\nContinue with Google\n\nContinue with Apple\n\nContinue with email\n\nSingle sign-on (SSO)",
                    "query": "What is the capital of France?"
                }

            """
            # import ipdb; ipdb.set_trace()

    asyncio.run(main())
