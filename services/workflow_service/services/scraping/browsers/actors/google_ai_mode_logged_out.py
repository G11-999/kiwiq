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
import json
from playwright.async_api import ElementHandle

from workflow_service.services.scraping.browsers.actors.base_actor import BaseBrowserActor
from workflow_service.services.scraping.browsers.config import AIMODE_SELECTORS
from workflow_service.services.scraping.utils.markdown_converter import convert_to_markdown_from_raw_file_content

logger = logging.getLogger(__name__)


class GoogleAIModeBrowserActor(BaseBrowserActor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)



    def extract_response_from_aimode_page_via_dom_tree_navigation(self, query: str, soup: Optional[BeautifulSoup] = None, full_html: Optional[str] = None) -> Tuple[Optional[BeautifulSoup], list[dict]]:
        """Extract AI mode response using BeautifulSoup from full HTML for better performance
        
        NOTE: filter out text extracted this way as it includes some separators from actual response and other text:
        
        AI responses may include mistakes. Learn more Thank you Your feedback helps Google improve. See our Privacy Policy . Share more feedback Report a problem
        """
        try:
            if soup is None:
                # Get full page HTML once
                soup = BeautifulSoup(full_html, "html.parser")
            
            # Find all divs that contain the query text (normalized)
            query_divs = []
            for div in soup.find_all("div"):
                div_text = div.get_text(strip=True)
                if query.lower().strip(" \t\n\r") == div_text.lower().strip(" \t\n\r"):
                    query_divs.append(div)
            
            if not query_divs:
                logger.warning(f"No divs found containing query: {query}")
                return soup, []
            
            # Find the outermost div that contains our query
            elder_div = None
            for div in query_divs:
                # Walk up the parent chain to find outermost container
                current = div
                while current.parent:
                    parent_text = current.parent.get_text(strip=True)
                    if parent_text.lower().strip(" \t\n\r") == query.lower().strip(" \t\n\r") and current.parent.name == 'div':
                        current = current.parent
                    else:
                        break
                
                # Keep the largest container found
                if elder_div is None or len(current.get_text()) > len(elder_div.get_text()):
                    elder_div = current
            
            if not elder_div:
                logger.warning(f"No elder div found for query: {query}")
                return soup, []
            
            # Get parent of elder div and find all div siblings with text
            elder_parent = elder_div.parent
            if not elder_parent:
                logger.warning("Elder div has no parent")
                return soup, []
            
            # Find all div children of the parent that have text content
            content_divs = []
            for child in elder_parent.find_all("div", recursive=False):  # Direct children only
                child_text = child.get_text(strip=True)
                if child_text:  # Only divs with actual text
                    content_divs.append(child)
            
            # Process all content divs using BeautifulSoup
            results = self.process_response_elements_from_soup(content_divs)
            
            return soup, results
            
        except Exception as e:
            logger.error(f"Error in DOM tree navigation for query '{query}': {e}", exc_info=True)
            return soup, []
    
    def process_response_elements_from_soup(self, soup_elements: list) -> list[dict]:
        """Common processing function for multiple soup elements"""
        results = []
        for i, element in enumerate(soup_elements):
            try:
                result = self.process_aimode_element_from_soup(element)
                if result and result.get("text", "").strip():  # Only add if has content
                    results.append(result)
            except Exception as e:
                logger.warning(f"Failed to process soup element {i}: {e}")
                continue
        return results

    def extract_response_from_aimode_page_via_turn_selector(self, query: str, full_html: str) -> Tuple[Optional[BeautifulSoup], list[dict]]:
        """Extract AI mode response using ai_mode_turn_selector from BeautifulSoup for better performance
        
        Subselects ai_mode_response_container within ai_mode_turn_selector if found, otherwise processes 
        ai_mode_turn_selector elements directly.
        
        NOTE: filter out text extracted this way as it includes some separators from actual response and other text:

        AI responses may include mistakes. Learn more Thank you Your feedback helps Google improve. See our Privacy Policy . Share more feedback Report a problem Close
        """
        soup = None
        try:
            # Get full page HTML once
            
            soup = BeautifulSoup(full_html, "html.parser")
            
            # Use BeautifulSoup-specific turn selector configuration
            bs_turn_selector = AIMODE_SELECTORS.get("bs_ai_mode_turn_selector", {"tag": "div", "attrs": {"data-scope-id": "turn"}})
            bs_response_container_selector = AIMODE_SELECTORS.get("bs_ai_mode_response_container", {"tag": "div", "attrs": {"data-container-id": "main-col"}})
            
            # Find turn selector elements using BeautifulSoup format
            turn_elements = soup.find_all(bs_turn_selector["tag"], attrs=bs_turn_selector["attrs"])
            
            if not turn_elements:
                logger.warning(f"No turn elements found using selector: {bs_turn_selector}")
                return soup, []
            
            # Process each turn element - check for response containers within it
            elements_to_process = []
            
            for turn_element in turn_elements:
                # Look for response container elements within this turn element
                response_containers = turn_element.find_all(
                    bs_response_container_selector["tag"], 
                    attrs=bs_response_container_selector["attrs"]
                )
                
                if response_containers:
                    # Found response containers within turn element - use those
                    logger.debug(f"Found {len(response_containers)} response containers within turn element")
                    elements_to_process.extend(response_containers)
                else:
                    # No response containers found - process the turn element directly
                    logger.debug("No response containers found within turn element, processing turn element directly")
                    elements_to_process.append(turn_element)
            
            if not elements_to_process:
                logger.warning("No elements to process after subselection logic")
                return soup, []
            
            # Process all selected elements
            results = self.process_response_elements_from_soup(elements_to_process)
            
            return soup, results
            
        except Exception as e:
            logger.error(f"Error in turn selector extraction for query '{query}': {e}", exc_info=True)
            return soup, []
    
    def process_aimode_element_from_soup(self, soup_element) -> dict:
        """Process a BeautifulSoup element and extract text, HTML, links, and citations"""
        if not soup_element:
            return {
                "text": "",
                "html": "",
                "links": [],
                "citations": [],
                "markdown": "",
            }
        
        try:
            # Extract text content using BeautifulSoup
            text_content = soup_element.get_text(" ", strip=True)
            text_content = re.sub(r"\s+", " ", text_content).strip()
            
            # Extract HTML content
            html_content = str(soup_element)
            
            # Extract links
            links = []
            for a_tag in soup_element.find_all("a", href=True):
                url = a_tag["href"]
                
                # Skip anchor links, javascript links, and non-http links
                if not url or url.startswith("#") or url.startswith("javascript:") or (not url.startswith('http')):
                    continue
                
                # Check against blacklist
                blacklist = AIMODE_SELECTORS.get("link_blacklist", set())
                is_blacklisted = False
                for blacklisted_domain in blacklist:
                    if blacklisted_domain in url:
                        is_blacklisted = True
                        break
                
                if not is_blacklisted:
                    link_data = {
                        "url": url,
                        "text": a_tag.get_text(strip=True),
                        "title": a_tag.get("title", ""),
                        "class": a_tag.get("class", []),
                        "target": a_tag.get("target", "")
                    }
                    links.append(link_data)
            
            # Extract citations using the same patterns as the ElementHandle version
            citations = []
            citation_patterns = [
                r'\[(\d+)\]',  # [1], [2], etc.
                r'(?:^|\s)(\d+)\.?\s',  # 1. 2. etc. at start of line
                r'(?:Source|Sources?):\s*(.+?)(?:\n|$)',  # Source: text
                r'(?:Reference|References?):\s*(.+?)(?:\n|$)',  # Reference: text
                r'(?:Learn more|More info):\s*(.+?)(?:\n|$)',  # Google-specific patterns
                r'(?:According to|As per)\s+([^,\n]+)',  # "According to XYZ"
            ]
            
            for pattern in citation_patterns:
                matches = re.findall(pattern, text_content, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    if match and match.strip() and len(match.strip()) > 1:
                        citations.append(match.strip())
            
            # Look for citation elements by Google-specific attributes
            citation_selectors = [
                '[data-ved]',  # Google's tracking attributes often mark sources
                '[jsname]',    # Google internal component names
                '.g',          # Google search result class
                '[data-async-context]'  # Google async content
            ]
            
            for selector in citation_selectors:
                try:
                    citation_elements = soup_element.select(selector)
                    for elem in citation_elements:
                        citation_text = elem.get_text(strip=True)
                        # Only add if it looks like a source
                        if citation_text and any(keyword in citation_text.lower() for keyword in ['http', 'www', '.com', '.org', 'source', 'via']):
                            if citation_text not in citations and len(citation_text) < 200:
                                citations.append(citation_text)
                except Exception:
                    continue
            
            return {
                "text": text_content,
                "html": html_content,
                "links": links,
                "citations": citations,
                "markdown": convert_to_markdown_from_raw_file_content(html_content),
            }
            
        except Exception as e:
            logger.error(f"Error processing soup element: {e}", exc_info=True)
            return {
                "text": "",
                "html": "",
                "links": [],
                "citations": [],
                "markdown": "",
            }
    
    async def single_query(self, query: str) -> dict:
        await self.go_to_page(AIMODE_SELECTORS["base_url"])
        # await self.page.reload()
        # await self.wait_for_seconds(10)
        await self.wait_and_fill(AIMODE_SELECTORS['search_bar'], query)
        try:
            await self.wait_and_click(AIMODE_SELECTORS['ai_mode_search_button'], timeout=30000)
        except Exception as e:
            logger.error(f"Error clicking ai_mode_search_button: {e}", exc_info=True)
            await self.page.keyboard.press("Enter")
            await self.wait_and_click(AIMODE_SELECTORS['ai_mode_button'])

        # await self.page.keyboard.press("Enter")
        # await self.wait_for_seconds(2)
        results, links = await self.get_content_with_stable_response(query)

        if results and isinstance(results[-1], dict):
            if ("links" not in results[-1] or (not results[-1]["links"])):
                results[-1]["links"] = links
            else:
                results[-1]["all_links"] = links
            
        
        return results

    
    async def google_conversation(self, Q1: str, Q2: str, Q3: str):
        await self.go_to_page(AIMODE_SELECTORS["base_url"])
        # await self.page.reload()
        # await self.wait_for_seconds(10)
        await self.wait_and_fill(AIMODE_SELECTORS['search_bar'], Q1)
        try:
            await self.wait_and_click(AIMODE_SELECTORS['ai_mode_search_button'], timeout=30000)
        except Exception as e:
            logger.error(f"Error clicking ai_mode_search_button: {e}", exc_info=True)
            await self.page.keyboard.press("Enter")
            await self.wait_and_click(AIMODE_SELECTORS['ai_mode_button'])

        # await self.page.keyboard.press("Enter")
        await self.wait_for_seconds(2)

        seen_urls = set()
        results, links = await self.get_content_with_stable_response(Q1)
        q1_links = links
        for link in links:
            seen_urls.add(link["url"])
        
        print(json.dumps([{"text": r["text"], "links": r["links"], "citations": r["citations"]} for r in results if r["text"]], indent=4))
        print(json.dumps(q1_links, indent=4))

        await self.wait_for_seconds(2)
        
        await self.wait_and_click(AIMODE_SELECTORS['ai_mode_follow_up'])
        await self.page.keyboard.type(Q2, delay=random.randint(3, 15))
        await self.page.keyboard.press("Enter")
        await self.wait_for_seconds(5)

        results, links = await self.get_content_with_stable_response(Q2)
        q2_links = []
        for link in links:
            if link["url"] not in seen_urls:  # Fixed: compare URL string, not entire dict
                q2_links.append(link)
            seen_urls.add(link["url"])
        
        print(json.dumps([{"text": r["text"], "links": r["links"], "citations": r["citations"]} for r in results if r["text"]], indent=4))
        print(json.dumps(q2_links, indent=4))

        await self.wait_for_seconds(2)

        await self.wait_and_click(AIMODE_SELECTORS['ai_mode_follow_up'])
        await self.page.keyboard.type(Q3, delay=random.randint(3, 15))
        await self.page.keyboard.press("Enter")
        # await self.wait_and_click(AIMODE_SELECTORS['ai_mode_button'])

        await self.wait_for_seconds(2)

        results, links = await self.get_content_with_stable_response(Q3)
        q3_links = []
        for link in links:
            if link["url"] not in seen_urls:  # Fixed: compare URL string, not entire dict
                q3_links.append(link)
            seen_urls.add(link["url"])
        
        print(json.dumps([{"text": r["text"], "links": r["links"], "citations": r["citations"]} for r in results if r["text"]], indent=4))
        print(json.dumps(q3_links, indent=4))
        
        await self.wait_for_seconds(20)

    
    async def extract_aimode_links_and_citations(self, element_handle: ElementHandle) -> tuple[list, list]:
        """Extract links and citations specifically for Google AI Mode format using Playwright ElementHandle"""
        if not element_handle:
            return [], []
        
        try:
            # Extract links using Playwright
            links = []
            link_elements = await element_handle.query_selector_all('a[href]')
            
            for a_element in link_elements:
                try:
                    url = await a_element.get_attribute('href')
                    text = await a_element.inner_text()
                    title = await a_element.get_attribute('title') or ''
                    class_attr = await a_element.get_attribute('class') or ''
                    target = await a_element.get_attribute('target') or ''
                    
                    if url and not url.startswith("#"):  # Skip anchor links
                        link_data = {
                            "url": url,
                            "text": text.strip(),
                            "title": title,
                            "class": class_attr.split() if class_attr else [],
                            "target": target
                        }
                        links.append(link_data)
                except Exception:
                    continue  # Skip problematic links
            
            # Extract Google AI Mode citations using Playwright
            citations = []
            
            # Get text content for pattern matching
            text_content = await element_handle.inner_text()
            
            # Google AI citation patterns
            citation_patterns = [
                r'\[(\d+)\]',  # [1], [2], etc.
                r'(?:^|\s)(\d+)\.?\s',  # 1. 2. etc. at start of line
                r'(?:Source|Sources?):\s*(.+?)(?:\n|$)',  # Source: text
                r'(?:Reference|References?):\s*(.+?)(?:\n|$)',  # Reference: text
                r'(?:Learn more|More info):\s*(.+?)(?:\n|$)',  # Google-specific patterns
                r'(?:According to|As per)\s+([^,\n]+)',  # "According to XYZ"
            ]
            
            for pattern in citation_patterns:
                matches = re.findall(pattern, text_content, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    if match and match.strip() and len(match.strip()) > 1:
                        citations.append(match.strip())
            
            # Look for citation elements by Google-specific attributes using Playwright
            citation_selectors = [
                '[data-ved]',  # Google's tracking attributes often mark sources
                '[jsname]',    # Google internal component names
                '.g',          # Google search result class
                '[data-async-context]'  # Google async content
            ]
            
            for selector in citation_selectors:
                try:
                    citation_elements = await element_handle.query_selector_all(selector)
                    for elem in citation_elements:
                        try:
                            citation_text = await elem.inner_text()
                            citation_text = citation_text.strip()
                            
                            # Only add if it looks like a source (has URL-like text or specific keywords)
                            if citation_text and any(keyword in citation_text.lower() for keyword in ['http', 'www', '.com', '.org', 'source', 'via']):
                                if citation_text not in citations and len(citation_text) < 200:  # Avoid very long text
                                    citations.append(citation_text)
                        except Exception:
                            continue
                except Exception:
                    continue
            
            return links, citations
            
        except Exception as e:
            logger.error(f"Error extracting links and citations: {e}", exc_info=True)
            return [], []
    
    def get_all_page_links_filtered_from_soup(self, soup: BeautifulSoup) -> list[dict]:
        """Get all links from BeautifulSoup object and filter using link_blacklist"""
        blacklist = AIMODE_SELECTORS.get("link_blacklist", set())
        filtered_links = []
        
        try:
            # Get all anchor elements with href attribute from soup
            link_elements = soup.find_all('a', href=True)
            
            for a_tag in link_elements:
                try:
                    url = a_tag.get('href')
                    text = a_tag.get_text(strip=True)
                    title = a_tag.get('title', '')
                    class_attr = a_tag.get('class', [])
                    target = a_tag.get('target', '')
                    rel = a_tag.get('rel', [])
                    
                    # Skip anchor links and javascript links
                    if not url or url.startswith('#') or url.startswith('javascript:') or (not url.startswith('http')):
                        continue
                    
                    # Check against blacklist in Python
                    is_blacklisted = False
                    for blacklisted_domain in blacklist:
                        if blacklisted_domain in url:
                            is_blacklisted = True
                            break
                    
                    if not is_blacklisted:
                        link_data = {
                            "url": url,
                            "text": text,
                            "title": title,
                            "class": class_attr if isinstance(class_attr, list) else class_attr.split() if class_attr else [],
                            "target": target,
                            "rel": rel if isinstance(rel, list) else rel.split() if rel else []
                        }
                        filtered_links.append(link_data)
                        
                except Exception as e:
                    # Skip individual links that cause errors
                    continue
                    
        except Exception as e:
            logger.error(f"Error fetching page links from soup: {e}", exc_info=True)
            
        return filtered_links

    async def get_all_page_links_filtered(self) -> list[dict]:
        """Get all links from the full page using Playwright Python API and filter using link_blacklist"""
        blacklist = AIMODE_SELECTORS.get("link_blacklist", set())
        filtered_links = []
        
        try:
            # Get all anchor elements with href attribute using Playwright
            link_elements = await self.page.query_selector_all('a[href]')
            
            for element in link_elements:
                try:
                    # Extract link attributes using Playwright Python API
                    url = await element.get_attribute('href')
                    text = await element.inner_text()
                    title = await element.get_attribute('title') or ''
                    class_attr = await element.get_attribute('class') or ''
                    target = await element.get_attribute('target') or ''
                    rel = await element.get_attribute('rel') or ''
                    
                    # Skip anchor links and javascript links
                    if not url or url.startswith('#') or url.startswith('javascript:'):
                        continue
                    
                    # Check against blacklist in Python
                    is_blacklisted = False
                    for blacklisted_domain in blacklist:
                        if blacklisted_domain in url:
                            is_blacklisted = True
                            break
                    
                    if not is_blacklisted:
                        link_data = {
                            "url": url,
                            "text": text.strip(),
                            "title": title,
                            "class": class_attr.split() if class_attr else [],
                            "target": target,
                            "rel": rel.split() if rel else []
                        }
                        filtered_links.append(link_data)
                        
                except Exception as e:
                    # Skip individual links that cause errors
                    continue
                    
        except Exception as e:
            logger.error(f"Error fetching page links: {e}", exc_info=True)
            
        return filtered_links
    
    async def process_aimode_element(self, element_handle: ElementHandle) -> dict:
        """Process a single ElementHandle and extract text, HTML, links, and citations"""
        if not element_handle:
            return {
                "text": "",
                "html": "",
                "links": [],
                "citations": []
            }
        
        try:
            # Extract text content using Playwright
            text_content = await element_handle.inner_text()
            text_content = re.sub(r"\s+", " ", text_content).strip()
            
            # Extract HTML content using Playwright
            html_content = await element_handle.evaluate("e => e.outerHTML")
            
            # Extract links and citations using the updated method
            links, citations = await self.extract_aimode_links_and_citations(element_handle)
            
            return {
                "text": text_content,
                "html": html_content,
                "links": links,
                "citations": citations
            }
            
        except Exception as e:
            logger.error(f"Error processing element: {e}", exc_info=True)
            return {
                "text": "",
                "html": "",
                "links": [],
                "citations": []
            }

    async def get_content_with_stable_response(
        self,
        query: str,
        poll_every: float = 5.0,
        timeout: float = 180.0,
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        """
        Poll extract_response_from_aimode_page_via_dom_tree_navigation until the combined
        character count of all response elements no longer grows (i.e. AI finished generating).

        Args:
            query: The search query to look for
            poll_every: seconds between polls
            timeout: maximum seconds to wait

        Returns:
            Tuple of (response_elements, filtered_links) - both lists of dicts with text, html, links, and citations

        Raises:
            TimeoutError if the response never stabilizes within timeout
        """
        query_selector = f'div:has-text("{query}")'
        await self.page.wait_for_selector(query_selector, timeout=60000)
        
        start_time = monotonic()
        last_char_count = -1
        stable_iterations = 0
        STABLE_REQUIRED = 2  # must see same length twice

        logger.debug(f" Waiting for Google AI Mode response to stabilize for query: '{query}'")

        

        final_soup = None
        final_response_elements = []

        while True:

            raw_html = await self.page.evaluate("() => document.documentElement.outerHTML")
            full_html = "<!DOCTYPE html>\n" + raw_html
            # Try turn selector method first
            soup, response_elements = await asyncio.to_thread(self.extract_response_from_aimode_page_via_turn_selector, query, full_html)
            
            # If no results from turn selector, fallback to DOM tree navigation
            if not response_elements:
                logger.debug(f"Turn selector found no results, trying DOM tree navigation for query: '{query}'")
                soup, response_elements = await asyncio.to_thread(self.extract_response_from_aimode_page_via_dom_tree_navigation, query, soup, full_html)

            if response_elements and isinstance(response_elements[-1], dict) and "query" not in response_elements[-1]:
                response_elements[-1]["query"] = query
            
            total = sum(len(elem.get("text", "")) for elem in response_elements)

            # Store the latest successful extraction
            if soup and response_elements:
                final_soup = soup
                final_response_elements = response_elements

            # Growth check
            if total == last_char_count:
                stable_iterations += 1
            else:
                stable_iterations = 0
                logger.debug(f"… still generating ({total} chars captured)")  # progress

            # Done?
            if stable_iterations >= STABLE_REQUIRED:
                logger.debug("Google AI Mode response complete.")
                break

            # Timeout guard
            if monotonic() - start_time > timeout:
                raise TimeoutError("Google AI Mode response did not stabilize in time")

            last_char_count = total
            await asyncio.sleep(poll_every)

        # Get filtered links from the final stable soup
        filtered_links = []
        if final_soup:
            filtered_links = self.get_all_page_links_filtered_from_soup(final_soup)

        return final_response_elements, filtered_links


if __name__ == "__main__":
    from workflow_service.services.scraping.browsers.scrapeless.scrapeless_browser import ScrapelessBrowser
    async def main():
        async with ScrapelessBrowser() as browser:  # profile_id="39fd01df-7bf9-44b5-befb-4ea5d238caf8", persist_profile=True
            live_url = await browser.get_live_url()
            print("\n\nlive_url: ---> ",live_url)
            actor = GoogleAIModeBrowserActor(browser=browser.browser, context=browser.context, page=browser.page, live_url=live_url)
            result = await actor.single_query("What is the capital of France?")
            print(result)
            # import ipdb; ipdb.set_trace()

    asyncio.run(main())
