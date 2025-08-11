

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
    
    async def close_popup(self) -> bool:
        """
        Attempts to close any popup that might appear on Perplexity.
        
        Returns:
            bool: True if a popup was found and closed, False otherwise.
        """
        try:
            # Wait a short time for popup to potentially appear
            await self.page.wait_for_selector(PERPLEXITY_SELECTORS["close_popup"], timeout=1000)
            await self.page.click(PERPLEXITY_SELECTORS["close_popup"])
            return True
        except Exception as e:
            # No popup found or couldn't close it - this is fine
            self.logger.error(f"Error closing popup: {e}", exc_info=True)
            return False

    async def wait_until_perplexity_response_complete(
        self,
        poll_every: float = 8.0,
        timeout: float = 200.0,
    ) -> List[Dict[str, str]]:
        """
        Poll `extract_response_from_perplexity_page()` until the combined
        character count of all answer segments no longer grows
        (i.e. streaming finished).

        Prints a short status line each time new content appears.

        Args:
            poll_every: seconds between polls.
            timeout:    maximum seconds to wait.

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

        while True:
            
            # 1. grab full HTML
            raw_html  = await self.page.evaluate("() => document.documentElement.outerHTML")
            full_html = "<!DOCTYPE html>\n" + raw_html
            self.logger.info(f"full_html extracted!")
            segments = await asyncio.to_thread(self.extract_response_from_perplexity_page, full_html)
            self.logger.info(f"segments extracted!")

            total    = sum(len(s["text"]) for s in segments)

            #  growth check
            if total == last_char_count:
                stable_iterations += 1
            else:
                stable_iterations  = 0
                self.logger.debug(f"… still generating ({total} chars captured)")  # progress

            # done?
            if stable_iterations >= STABLE_REQUIRED:
                self.logger.debug("Perplexity response complete.")
                return segments

            # timeout guard
            if monotonic() - start_time > timeout:
                raise TimeoutError("Perplexity answer did not stabilise in time")

            last_char_count = total
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
                await self.wait_and_click(PERPLEXITY_SELECTORS["close_popup"], timeout=500)
                await self.wait_for_seconds(0.1)
            except Exception as e:
                self.logger.info(f" close popup not found: {e}")
            
            try:
                await self.wait_and_click(PERPLEXITY_SELECTORS["prompt_input"], timeout=500)
                return True
            except Exception as e:
                self.logger.info(f" prompt input not found: {e}")
            
            return False
            
        clicked = False
        try:
            await self.go_to_page(PERPLEXITY_SELECTORS["base_url"], timeout=10000)
        except Exception as e:
            self.logger.error(f"Error going to page: {e}")
            clicked = await short_prompt_focus_sequence()
            if not clicked:
                try:
                    await self.go_to_page(PERPLEXITY_SELECTORS["base_url"], timeout=20000)
                except Exception as e:
                    self.logger.error(f"Error going to page: {e}")
        
        if not clicked:
            clicked = await short_prompt_focus_sequence()
        
        await self.page.keyboard.type(query, delay=random.randint(1, 5))

        # Press Enter to submit
        await self.page.keyboard.press("Enter")

        try:
            await self.wait_and_click(PERPLEXITY_SELECTORS["close_popup"], timeout=1000)
            await self.wait_for_seconds(0.1)
        except Exception as e:
            self.logger.info(f" close popup not found: {e}")
        
        
        answers = await self.wait_until_perplexity_response_complete()
        if answers and isinstance(answers[-1], dict) and "query" not in answers[-1]:
            answers[-1]["query"] = query
        
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
        await self.close_popup()
        
        # await self.wait_and_fill(PERPLEXITY_SELECTORS['prompt_input'], Q2)
        await self.wait_and_click(PERPLEXITY_SELECTORS["prompt_input"]) 
        await self.page.keyboard.type(Q2, delay=random.randint(3, 15))

        # Press Enter to submit
        await self.page.keyboard.press("Enter")
        
        answers = await self.wait_until_perplexity_response_complete()
        print(answers)
        
        # Try to close popup after second response
        await self.close_popup()
        
        # await self.wait_and_fill(PERPLEXITY_SELECTORS['prompt_input'], Q3)
        await self.wait_and_click(PERPLEXITY_SELECTORS["prompt_input"]) 
        await self.page.keyboard.type(Q3, delay=random.randint(3, 15))

        # Press Enter to submit
        await self.page.keyboard.press("Enter")
        
        answers = await self.wait_until_perplexity_response_complete()
        print(answers)
        
        # Try to close popup after third response
        await self.close_popup()

        # # pause_until_confirm()
        # import ipdb; ipdb.set_trace()


if __name__ == "__main__":
    from workflow_service.services.scraping.browsers.scrapeless.scrapeless_browser import ScrapelessBrowser
    async def main():
        async with ScrapelessBrowser() as browser:  # profile_id="39fd01df-7bf9-44b5-befb-4ea5d238caf8", persist_profile=True
            live_url = await browser.get_live_url()
            print("\n\nlive_url: ---> ",live_url)
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
