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
        close_popup_after_timeout: float = 3000,
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

        retry_count = 0
        while True:
            if await self.retry_button(timeout=3000):
                retry_count += 1
                if retry_count > 3:
                    raise Exception("Too many retries, giving up this session")
                continue
            await self.stay_logged_out(timeout=close_popup_after_timeout)
            
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
    
    async def retry_button(self, timeout=1000):
        try:
            await self.wait_and_click(OPENAI_SELECTORS["retry_button"], timeout=timeout)
            self.logger.info(f"SUCCESS: Retry button clicked")
            return True
        except Exception as e:
            self.logger.info(f"Retry button not found: {e}")
            return False
    
    async def stay_logged_out(self, timeout=5000):
        try:
            await self.wait_and_click(OPENAI_SELECTORS["stay_logged_out"], timeout=timeout)
            self.logger.info(f"SUCCESS: Stay logged out button clicked")
            await self.wait_for_seconds(0.1, add_noise=True)
            return True
        except Exception as e:
            self.logger.info(f"Stay logged out button not found: {e}")
            return False
    
    async def single_query(self, query: str) -> List[Dict[str, str]]:
        # TODO: better way to click using locators probably: https://claude.ai/chat/96925ea0-80be-406a-a1dd-e74e7c2382e4
        async def close_popup(timeout=5000):
            try:
                await self.wait_and_click(OPENAI_SELECTORS["close_popup"], timeout=timeout)
                await self.wait_for_seconds(0.1, add_noise=True)
                self.logger.info(f"SUCCESS: Close popup button clicked")
            except Exception as e:
                self.logger.info(f"Close popup button not found: {e}")

        async def short_prompt_focus_sequence():
            await self.click_middle_with_offset()

            await self.stay_logged_out()
            await close_popup()
            
            try:
                await self.wait_and_click(OPENAI_SELECTORS["search_web_no_login"], timeout=5000)
                # NOTE: can add delay in click up / click down events; add separate timeout for finding element vs actual click?? 
                #     this may be better as recommended by claude https://claude.ai/chat/96925ea0-80be-406a-a1dd-e74e7c2382e4
                # await self.page.locator(OPENAI_SELECTORS["prompt_input"]).focus(timeout=30000)
                # await self.page.click(OPENAI_SELECTORS["search_web_no_login"], timeout=1500)
                self.logger.info(f"SUCCESS: Search web no login button clicked")
                return True
            except Exception as e:

                await close_popup()
                await self.stay_logged_out()

                self.logger.info(f"Search web no login button not found: {e}")
            return False
        
        clicked = False

        # try:
        #     await self.go_to_page(OPENAI_SELECTORS["base_url"], timeout=10000)
        # except Exception as e:
        #     self.logger.warning(f"Error going to page: {e}")
        
        clicked = False
        iterations = 0
        count_navigations = 0
        while (not clicked) and iterations < 5:
            try:
                current_url = self.page.url
                self.logger.info(f"Current URL: {current_url}")
                if (not iterations) or (not current_url.strip(" /").startswith(OPENAI_SELECTORS["base_url"].strip(" /"))):  #  (not current_url) or  current_url != OPENAI_SELECTORS["base_url"]
                    if count_navigations >= 3:
                        raise Exception("Too many navigations, giving up this session, current url: {current_url}")
                    await self.go_to_page(OPENAI_SELECTORS["base_url"], timeout=10000)
                    count_navigations += 1
                # NOTE: here you can try short focus sequence again and wait 10-20s as last resort, to counter any captchas!
            except Exception as e:
                self.logger.warning(f"Error going to page: {e}")
            clicked = await short_prompt_focus_sequence()
            iterations += 1
        
        close_popup_after_timeout = 5000
        
        await close_popup(timeout=close_popup_after_timeout)
        await self.stay_logged_out(timeout=close_popup_after_timeout)

        # Send Q1
        await self.wait_for_seconds(0.25, add_noise=True)
        # await self.wait_and_click(OPENAI_SELECTORS["prompt_input"])
        await self.page.locator(OPENAI_SELECTORS["prompt_input"]).focus(timeout=30000)
        await self.wait_for_seconds(0.25, add_noise=True)
        # pause_until_confirm()
        await self.page.keyboard.type(query, delay=random.randint(1, 5))
        await self.wait_for_seconds(0.25, add_noise=True)

        await close_popup(timeout=close_popup_after_timeout)
        await self.stay_logged_out(timeout=close_popup_after_timeout)

        try:
            await self.wait_and_click(OPENAI_SELECTORS["send_button"], timeout=1000)
        except Exception as e:
            self.logger.info(f"Send button not found: {e}")
            await close_popup(timeout=close_popup_after_timeout)
            await self.stay_logged_out(timeout=close_popup_after_timeout)
            await self.wait_and_click(OPENAI_SELECTORS["send_button"])
        # pause_until_confirm()

        try:
            await self.wait_and_click(OPENAI_SELECTORS["stay_logged_out"], timeout=1000)
            self.logger.info(f"Stay logged out button clicked")
            await self.wait_for_seconds(0.1, add_noise=True)
        except Exception as e:
            self.logger.info(f"Stay logged out button not found: {e}")

        # Wait for GPT to finish
        pairs = await self.wait_until_chatgpt_response_complete(close_popup_after_timeout=close_popup_after_timeout)
        
        return pairs
    
    async def chatgpt_conversation(self, Q1: str, Q2: str, Q3: str, enable_search: bool = True):
        try:
            await self.go_to_page(OPENAI_SELECTORS["base_url"], timeout=10000)
        except Exception as e:
            self.logger.warning(f"Error going to page: {e}")
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
            import json
            print(json.dumps(result, indent=4))
            """
            [
                {
                    "query": "What is the capital of France?",
                    "text": "The capital of France is Paris.",
                    "html": "<div class=\"text-base my-auto mx-auto pb-10 [--thread-content-margin:--spacing(4)] @[37rem]:[--thread-content-margin:--spacing(6)] @[72rem]:[--thread-content-margin:--spacing(16)] px-(--thread-content-margin)\"><div class=\"[--thread-content-max-width:32rem] @[34rem]:[--thread-content-max-width:40rem] @[64rem]:[--thread-content-max-width:48rem] mx-auto max-w-(--thread-content-max-width) flex-1 group/turn-messages focus-visible:outline-hidden relative flex w-full min-w-0 flex-col agent-turn\" tabindex=\"-1\"><div class=\"flex max-w-full flex-col grow\"><div class=\"min-h-8 text-message relative flex w-full flex-col items-end gap-2 text-start break-words whitespace-normal [.text-message+&amp;]:mt-5\" data-message-author-role=\"assistant\" data-message-id=\"ea898f95-d273-488f-bcad-c79de71d72f1\" data-message-model-slug=\"gpt-4o\" dir=\"auto\"><div class=\"flex w-full flex-col gap-1 empty:hidden first:pt-[3px]\"><div class=\"markdown prose dark:prose-invert w-full break-words light markdown-new-styling\"><p data-end=\"31\" data-is-last-node=\"\" data-is-only-node=\"\" data-start=\"0\">The capital of France is Paris.</p></div></div></div></div><div class=\"flex min-h-[46px] justify-start\"><div class=\"touch:-me-2 touch:-ms-3.5 -ms-2.5 -me-1 flex flex-wrap items-center gap-y-4 p-1 select-none touch:w-[calc(100%+--spacing(3.5))] -mt-1 w-[calc(100%+--spacing(2.5))] duration-[1.5s] focus-within:transition-none hover:transition-none pointer-events-none [mask-image:linear-gradient(to_right,black_33%,transparent_66%)] [mask-size:300%_100%] [mask-position:100%_0%] motion-safe:transition-[mask-position] group-hover/turn-messages:pointer-events-auto group-hover/turn-messages:[mask-position:0_0] group-focus-within/turn-messages:pointer-events-auto group-focus-within/turn-messages:[mask-position:0_0] has-data-[state=open]:pointer-events-auto has-data-[state=open]:[mask-position:0_0]\" style=\"mask-position: 0% 0%;\"><button aria-label=\"Copy\" aria-pressed=\"false\" class=\"text-token-text-secondary hover:bg-token-bg-secondary rounded-lg\" data-state=\"closed\" data-testid=\"copy-turn-action-button\"><span class=\"touch:w-10 flex h-8 w-8 items-center justify-center\"><svg class=\"icon\" fill=\"currentColor\" height=\"20\" viewbox=\"0 0 20 20\" width=\"20\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M12.668 10.667C12.668 9.95614 12.668 9.46258 12.6367 9.0791C12.6137 8.79732 12.5758 8.60761 12.5244 8.46387L12.4688 8.33399C12.3148 8.03193 12.0803 7.77885 11.793 7.60254L11.666 7.53125C11.508 7.45087 11.2963 7.39395 10.9209 7.36328C10.5374 7.33197 10.0439 7.33203 9.33301 7.33203H6.5C5.78896 7.33203 5.29563 7.33195 4.91211 7.36328C4.63016 7.38632 4.44065 7.42413 4.29688 7.47559L4.16699 7.53125C3.86488 7.68518 3.61186 7.9196 3.43555 8.20703L3.36524 8.33399C3.28478 8.49198 3.22795 8.70352 3.19727 9.0791C3.16595 9.46259 3.16504 9.95611 3.16504 10.667V13.5C3.16504 14.211 3.16593 14.7044 3.19727 15.0879C3.22797 15.4636 3.28473 15.675 3.36524 15.833L3.43555 15.959C3.61186 16.2466 3.86474 16.4807 4.16699 16.6348L4.29688 16.6914C4.44063 16.7428 4.63025 16.7797 4.91211 16.8027C5.29563 16.8341 5.78896 16.835 6.5 16.835H9.33301C10.0439 16.835 10.5374 16.8341 10.9209 16.8027C11.2965 16.772 11.508 16.7152 11.666 16.6348L11.793 16.5645C12.0804 16.3881 12.3148 16.1351 12.4688 15.833L12.5244 15.7031C12.5759 15.5594 12.6137 15.3698 12.6367 15.0879C12.6681 14.7044 12.668 14.211 12.668 13.5V10.667ZM13.998 12.665C14.4528 12.6634 14.8011 12.6602 15.0879 12.6367C15.4635 12.606 15.675 12.5492 15.833 12.4688L15.959 12.3975C16.2466 12.2211 16.4808 11.9682 16.6348 11.666L16.6914 11.5361C16.7428 11.3924 16.7797 11.2026 16.8027 10.9209C16.8341 10.5374 16.835 10.0439 16.835 9.33301V6.5C16.835 5.78896 16.8341 5.29563 16.8027 4.91211C16.7797 4.63025 16.7428 4.44063 16.6914 4.29688L16.6348 4.16699C16.4807 3.86474 16.2466 3.61186 15.959 3.43555L15.833 3.36524C15.675 3.28473 15.4636 3.22797 15.0879 3.19727C14.7044 3.16593 14.211 3.16504 13.5 3.16504H10.667C9.9561 3.16504 9.46259 3.16595 9.0791 3.19727C8.79739 3.22028 8.6076 3.2572 8.46387 3.30859L8.33399 3.36524C8.03176 3.51923 7.77886 3.75343 7.60254 4.04102L7.53125 4.16699C7.4508 4.32498 7.39397 4.53655 7.36328 4.91211C7.33985 5.19893 7.33562 5.54719 7.33399 6.00195H9.33301C10.022 6.00195 10.5791 6.00131 11.0293 6.03809C11.4873 6.07551 11.8937 6.15471 12.2705 6.34668L12.4883 6.46875C12.984 6.7728 13.3878 7.20854 13.6533 7.72949L13.7197 7.87207C13.8642 8.20859 13.9292 8.56974 13.9619 8.9707C13.9987 9.42092 13.998 9.97799 13.998 10.667V12.665ZM18.165 9.33301C18.165 10.022 18.1657 10.5791 18.1289 11.0293C18.0961 11.4302 18.0311 11.7914 17.8867 12.1279L17.8203 12.2705C17.5549 12.7914 17.1509 13.2272 16.6553 13.5313L16.4365 13.6533C16.0599 13.8452 15.6541 13.9245 15.1963 13.9619C14.8593 13.9895 14.4624 13.9935 13.9951 13.9951C13.9935 14.4624 13.9895 14.8593 13.9619 15.1963C13.9292 15.597 13.864 15.9576 13.7197 16.2939L13.6533 16.4365C13.3878 16.9576 12.9841 17.3941 12.4883 17.6982L12.2705 17.8203C11.8937 18.0123 11.4873 18.0915 11.0293 18.1289C10.5791 18.1657 10.022 18.165 9.33301 18.165H6.5C5.81091 18.165 5.25395 18.1657 4.80371 18.1289C4.40306 18.0962 4.04235 18.031 3.70606 17.8867L3.56348 17.8203C3.04244 17.5548 2.60585 17.151 2.30176 16.6553L2.17969 16.4365C1.98788 16.0599 1.90851 15.6541 1.87109 15.1963C1.83431 14.746 1.83496 14.1891 1.83496 13.5V10.667C1.83496 9.978 1.83432 9.42091 1.87109 8.9707C1.90851 8.5127 1.98772 8.10625 2.17969 7.72949L2.30176 7.51172C2.60586 7.0159 3.04236 6.6122 3.56348 6.34668L3.70606 6.28027C4.04237 6.136 4.40303 6.07083 4.80371 6.03809C5.14051 6.01057 5.53708 6.00551 6.00391 6.00391C6.00551 5.53708 6.01057 5.14051 6.03809 4.80371C6.0755 4.34588 6.15483 3.94012 6.34668 3.56348L6.46875 3.34473C6.77282 2.84912 7.20856 2.44514 7.72949 2.17969L7.87207 2.11328C8.20855 1.96886 8.56979 1.90385 8.9707 1.87109C9.42091 1.83432 9.978 1.83496 10.667 1.83496H13.5C14.1891 1.83496 14.746 1.83431 15.1963 1.87109C15.6541 1.90851 16.0599 1.98788 16.4365 2.17969L16.6553 2.30176C17.151 2.60585 17.5548 3.04244 17.8203 3.56348L17.8867 3.70606C18.031 4.04235 18.0962 4.40306 18.1289 4.80371C18.1657 5.25395 18.165 5.81091 18.165 6.5V9.33301Z\"></path></svg></span></button><button aria-label=\"Edit in canvas\" aria-pressed=\"false\" class=\"text-token-text-secondary hover:bg-token-bg-secondary rounded-lg\" data-state=\"closed\"><span class=\"touch:w-10 flex h-8 w-8 items-center justify-center\"><svg class=\"icon\" fill=\"currentColor\" height=\"20\" viewbox=\"0 0 20 20\" width=\"20\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M12.0303 4.11328C13.4406 2.70317 15.7275 2.70305 17.1377 4.11328C18.5474 5.52355 18.5476 7.81057 17.1377 9.2207L10.8457 15.5117C10.522 15.8354 10.2868 16.0723 10.0547 16.2627L9.82031 16.4395C9.61539 16.5794 9.39783 16.7003 9.1709 16.7998L8.94141 16.8916C8.75976 16.9582 8.57206 17.0072 8.35547 17.0518L7.59082 17.1865L5.19727 17.5859C5.05455 17.6097 4.90286 17.6358 4.77441 17.6455C4.67576 17.653 4.54196 17.6555 4.39648 17.6201L4.24707 17.5703C4.02415 17.4746 3.84119 17.3068 3.72559 17.0957L3.67969 17.0029C3.59322 16.8013 3.59553 16.6073 3.60547 16.4756C3.61519 16.3473 3.6403 16.1963 3.66406 16.0537L4.06348 13.6602C4.1638 13.0582 4.22517 12.6732 4.3584 12.3096L4.45117 12.0791C4.55073 11.8521 4.67152 11.6346 4.81152 11.4297L4.9873 11.1953C5.17772 10.9632 5.4146 10.728 5.73828 10.4043L12.0303 4.11328ZM6.67871 11.3447C6.32926 11.6942 6.14542 11.8803 6.01953 12.0332L5.90918 12.1797C5.81574 12.3165 5.73539 12.4618 5.66895 12.6133L5.60742 12.7666C5.52668 12.9869 5.48332 13.229 5.375 13.8789L4.97656 16.2725L4.97559 16.2744H4.97852L7.37207 15.875L8.08887 15.749C8.25765 15.7147 8.37336 15.6839 8.4834 15.6436L8.63672 15.5811C8.78817 15.5146 8.93356 15.4342 9.07031 15.3408L9.2168 15.2305C9.36965 15.1046 9.55583 14.9207 9.90527 14.5713L14.8926 9.58301L11.666 6.35742L6.67871 11.3447ZM16.1963 5.05371C15.3054 4.16304 13.8616 4.16305 12.9707 5.05371L12.6074 5.41602L15.833 8.64258L16.1963 8.2793C17.0869 7.38845 17.0869 5.94456 16.1963 5.05371Z\"></path><path d=\"M4.58301 1.7832C4.72589 1.7832 4.84877 1.88437 4.87695 2.02441C4.99384 2.60873 5.22432 3.11642 5.58398 3.50391C5.94115 3.88854 6.44253 4.172 7.13281 4.28711C7.27713 4.3114 7.38267 4.43665 7.38281 4.58301C7.38281 4.7295 7.27723 4.8546 7.13281 4.87891C6.44249 4.99401 5.94116 5.27746 5.58398 5.66211C5.26908 6.00126 5.05404 6.43267 4.92676 6.92676L4.87695 7.1416C4.84891 7.28183 4.72601 7.38281 4.58301 7.38281C4.44013 7.38267 4.31709 7.28173 4.28906 7.1416C4.17212 6.55728 3.94179 6.04956 3.58203 5.66211C3.22483 5.27757 2.72347 4.99395 2.0332 4.87891C1.88897 4.85446 1.7832 4.72938 1.7832 4.58301C1.78335 4.43673 1.88902 4.3115 2.0332 4.28711C2.72366 4.17203 3.22481 3.88861 3.58203 3.50391C3.94186 3.11638 4.17214 2.60888 4.28906 2.02441L4.30371 1.97363C4.34801 1.86052 4.45804 1.78333 4.58301 1.7832Z\"></path></svg></span></button></div></div></div></div>",
                    "links": [],
                    "citations": [],
                    "markdown": "The capital of France is Paris."
                }
            ]
            """
            import ipdb; ipdb.set_trace()

    asyncio.run(main())
