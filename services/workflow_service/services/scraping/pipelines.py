"""
Simple streaming pipeline for scraped data.

Just write each item to a JSON file as it comes.
No buffering, no complexity, no data loss.
"""

import json
import os
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Set
from urllib.parse import urlparse
from logging import Logger

from scrapy import Spider
from scrapy.crawler import Crawler
from scrapy.http import Response

from kiwi_app.workflow_app.service_customer_data import CustomerDataService
from kiwi_app.auth.models import User
from global_config.logger import get_prefect_or_regular_python_logger
from db.session import get_async_db_as_manager
from global_utils.utils import datetime_now_utc

from workflow_service.services.external_context_manager import get_customer_data_service_no_dependency, clean_customer_data_service_no_dependency
from workflow_service.services.scraping.settings import scraping_settings
from workflow_service.config.settings import settings as workflow_settings

from pydantic import BaseModel, Field
from openai import AsyncOpenAI

OPENAI_CLIENT = AsyncOpenAI(api_key=workflow_settings.OPENAI_API_KEY)


class BlogClassification(BaseModel):
    """Structured classification result for blog detection.

    - brief_reason: concise, human-readable reason (kept short via max_length and instruction)
    - is_blog: True if the content is a blog/article-like page, otherwise False
    """

    brief_reason: str = Field(..., max_length=200)
    is_blog: bool


BLOG_SYSTEM_PROMPT = """You are an expert SEO Analyst tasked with determining whether a given webpage content is a blog post. You will be provided with the URL and content of a webpage, typically from B2B tech companies that are commercial in nature. These blog posts are often used for SEO, Answer Engine Optimization, or as a customer acquisition channel.

Your task is to carefully analyze the provided URL and content to determine whether it is a blog post. Follow these steps:

1. Examine the URL structure and any relevant information it might provide about the content type.

2. Analyze the content for the following characteristics typically associated with blog posts:
   a. Informative or educational content related to the company's industry or products
   b. A clear title or headline
   c. Structured content with headings, subheadings, and paragraphs
   d. Presence of images, infographics, or other visual elements
   e. Internal or external links
   f. Author byline or publication date
   g. Social sharing buttons or a comments section
   h. Length of content (generally 300+ words for blog posts)

3. Consider the structure, tone, purpose, and any other relevant factors that might indicate whether this is a blog post.

Carefully analyze the provided content and consider these characteristics. Then, provide your brief reasoning for why you believe this web page is or is not a blog post. Consider the structure, tone, purpose, and any other relevant factors.

After providing your reasoning, give your final classification as either the provided page is a blog post or not.

Response schema (JSON only):
{
    "brief_reason": "..."
    "is_blog": true,    
}

Remember to base your decision solely on the provided URL and content, and the characteristics of blog posts described above. Do not make assumptions about content that isn't present in the given text.
"""


async def classify_item_is_blog(
    item: Dict[str, Any],
    *,
    allowed_keys: Optional[Set[str]] = None,
    model: Optional[str] = None,
    max_content_length: Optional[int] = None,
) -> Tuple[bool, BlogClassification, Dict[str, Any]]:
    """
    Classify whether a scraped JSON item represents a blog post using an OpenAI model
    with structured output, after pre-filtering item fields.

    This function intentionally avoids dependencies on internal repo utilities to ensure
    it can be used in isolation.

    Args:
        item: Arbitrary JSON-like mapping representing a scraped page/item.
        allowed_keys: Optional white-list of keys from the item that are relevant for
            classification. If not provided, a sensible default set is used.
        model: Optional override of the OpenAI model name. Defaults to
            `scraping_settings.BLOG_CLASSIFIER_MODEL`.
        max_markdown_length: Optional override for the maximum characters of
            `markdown_content` considered. Defaults to
            `scraping_settings.BLOG_CLASSIFIER_MAX_MARKDOWN_LENGTH`.

    Returns:
        A 3-tuple of:
            - is_blog (bool): Classification result.
            - classification (dict): Structured output with keys `is_blog` and `brief_reason`.
            - filtered_item (dict): The input item reduced to allowed keys, with
              `markdown_content` truncated as configured.

    Raises:
        ValueError: If the model response cannot be parsed into the expected schema.
    """

    # Establish defaults for allowed keys and settings-driven parameters
    if allowed_keys is None:
        allowed_keys = {
            "title",
            "url",
            "markdown_content",
            # "content",
            # "text",
            # "description",
            # "tags",
            # "category",
            # "author",
            # "published_at",
        }

    model_name: str = model or scraping_settings.BLOG_CLASSIFIER_MODEL
    max_len: int = (
        max_content_length
        if max_content_length is not None
        else scraping_settings.BLOG_CLASSIFIER_MAX_CONTENT_LENGTH
    )

    # Filter the item down to allowed keys only
    filtered_item: Dict[str, Any] = {k: item[k] for k in allowed_keys if k in item}

    # Truncate markdown content if present to avoid excessive token usage
    if "markdown_content" in filtered_item and isinstance(filtered_item["markdown_content"], str):
        filtered_item["markdown_content"] = filtered_item["markdown_content"][:max_len]

    user_input: str = (
        f"Page content:\n\n"
        f"{json.dumps(filtered_item, ensure_ascii=False)}\n"
    )

    response = await OPENAI_CLIENT.responses.parse(
        model=model_name,
        input=[
            {"role": "system", "content": BLOG_SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ],
        max_output_tokens=200,
        reasoning={"effort": "minimal"},
        text_format=BlogClassification,
    )

    parsed: Optional[BlogClassification] = getattr(response, "output_parsed", None)
    if parsed is None:
        # Provide a compact error with available details for debugging
        raise ValueError("Model did not return a parsed object for BlogClassification.")

    return bool(parsed.is_blog), parsed, filtered_item


# logger = 


class StreamingFilePipeline:
    """
    Simple streaming pipeline that writes each item to disk immediately.
    
    Features:
    - No buffering (no data loss risk)
    - Simple JSON format
    - One file per job
    - Automatic directory creation
    """
    
    def __init__(self, base_dir: str = "services/workflow_service/services/scraping/data", logger: Logger = None, config: Dict[str, Any] = None):
        """
        Initialize streaming pipeline.
        
        Args:
            base_dir: Base directory for output files
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.file_handles = {}  # job_id -> file handle
        self.item_counts = {}   # job_id -> count
        self.logger = logger
        self.config = config
        
    @classmethod
    def from_crawler(cls, crawler: Crawler):
        """Create pipeline from crawler settings."""
        settings = crawler.settings
        logger = crawler.spider.prefect_logger
        config = MongoCustomerDataPipeline._extract_crawler_config(crawler)
        return cls(
            base_dir=settings.get('PIPELINE_BASE_DIR', 'services/workflow_service/services/scraping/data'),
            logger=logger,
            config=config,
        )
    
    def open_spider(self, spider: Spider):
        """Open output file for spider."""
        job_id = getattr(spider, 'job_id', spider.name)
        
        # Create job directory
        job_dir = self.base_dir / job_id
        job_dir.mkdir(exist_ok=True)
        
        # Create output file with timestamp
        timestamp = datetime_now_utc().strftime('%Y%m%d_%H%M%S')
        output_file = job_dir / f"{job_id}_{timestamp}.jsonl"
        
        # Open file for streaming (line-delimited JSON)
        self.file_handles[job_id] = open(output_file, 'w', encoding='utf-8')
        self.item_counts[job_id] = 0
        
        self.logger.info(f"Opened output file: {output_file}")
    
    def close_spider(self, spider: Spider):
        """Close output file and log stats."""
        job_id = getattr(spider, 'job_id', spider.name)
        
        if job_id in self.file_handles:
            self.file_handles[job_id].close()
            count = self.item_counts.get(job_id, 0)
            self.logger.info(f"Closed output file for job {job_id}: {count} items written")
            
            # Cleanup
            del self.file_handles[job_id]
            del self.item_counts[job_id]
    
    def process_item_sync(self, item: Dict[str, Any], spider: Spider) -> Dict[str, Any]:
        """Write item immediately to file."""
        job_id = getattr(spider, 'job_id', spider.name)
        
        # Ensure file is open
        if job_id not in self.file_handles:
            self.open_spider(spider)
        
        # Add metadata
        item_with_meta = dict(item)
        item_with_meta['_job_id'] = job_id
        item_with_meta['_spider'] = spider.name
        item_with_meta['_timestamp'] = datetime_now_utc().isoformat()
        
        # Write as JSON line
        try:
            json_line = json.dumps(item_with_meta, ensure_ascii=False, default=str)
            self.file_handles[job_id].write(json_line + '\n')
            self.file_handles[job_id].flush()  # Ensure it's written to disk
            
            self.item_counts[job_id] = self.item_counts.get(job_id, 0) + 1
            
            # Log every 100 items
            if self.item_counts[job_id] % 100 == 0:
                self.logger.info(f"Job {job_id}: {self.item_counts[job_id]} items written")
                
        except Exception as e:
            self.logger.error(f"Failed to write item for job {job_id}: {e}")
            # Don't raise - we don't want to stop the spider for one bad item
            
        return item
    
    async def process_item(self, item: Dict[str, Any], spider: Spider) -> Dict[str, Any]:
        """Write item immediately to file."""
        job_id = getattr(spider, 'job_id', spider.name)
        
        # Ensure file is open
        if job_id not in self.file_handles:
            self.open_spider(spider)
        
        # Add metadata
        item_with_meta = dict(item)
        item_with_meta['_job_id'] = job_id
        item_with_meta['_spider'] = spider.name
        item_with_meta['_timestamp'] = datetime_now_utc().isoformat()

        if self.config.get('classify_pages_as_blog'):
            item_with_meta['is_blog'] = True
            try:
                is_blog, parsed_classification, _ = await classify_item_is_blog(
                    item_with_meta,
                    model=self.config.get('blog_classifier_model'),
                    max_content_length=self.config.get('blog_classifier_max_length'),
                )
                item_with_meta['is_blog'] = is_blog
                item_with_meta['is_blog__reason'] = parsed_classification.brief_reason
            except Exception as e:
                self.logger.error(f"Failed to classify item as blog: {e}. Item URL: {item_with_meta.get('url', 'unknown')}", exc_info=True)
        
        # Write as JSON line
        try:
            json_line = json.dumps(item_with_meta, ensure_ascii=False, default=str)
            self.file_handles[job_id].write(json_line + '\n')
            self.file_handles[job_id].flush()  # Ensure it's written to disk
            
            self.item_counts[job_id] = self.item_counts.get(job_id, 0) + 1
            
            # Log every 100 items
            if self.item_counts[job_id] % 100 == 0:
                self.logger.info(f"Job {job_id}: {self.item_counts[job_id]} items written")
                
        except Exception as e:
            self.logger.error(f"Failed to write item for job {job_id}: {e}")
            # Don't raise - we don't want to stop the spider for one bad item
            
        return item 


class MongoCustomerDataPipeline:
    """
    Pipeline to save scraped web pages to MongoDB using CustomerDataService.
    
    Saves each scraped page as an unversioned document in the customer data store
    with proper namespace/docname structure for organization and retrieval.
    
    Configuration:
    - The CustomerDataService is managed by RedisScheduler when MONGO_PIPELINE_ENABLED=True
    - Pipeline automatically gets the service from crawler._customer_data_service
    - No manual initialization required - service lifecycle is handled by the scheduler
    
    Usage in spider settings:
        ITEM_PIPELINES = {
            'workflow_service.services.scraping.pipelines.MongoCustomerDataPipeline': 300,
        }
        MONGO_PIPELINE_ENABLED = True  # Enable customer data service in scheduler
    """
    
    def __init__(self, config: Dict[str, Any], crawler: Crawler, logger: Logger = None):
        """Initialize the MongoDB pipeline."""
        self.config: Dict[str, Any] = config
        self.logger = logger
        
        self.crawler = crawler
        self.items_processed = 0
        self.items_saved = 0
        self.items_failed = 0
        self.date_str = config.get('date_str')
        self.customer_data_service = None
        self._service_init_lock = asyncio.Lock()  # Lock for thread-safe service initialization
        if not self.date_str:
            raise ValueError("date_str is required")
    
    @classmethod
    def from_crawler(cls, crawler):
        """Create pipeline instance from crawler."""
        config = MongoCustomerDataPipeline._extract_crawler_config(crawler)
        logger = crawler.spider.prefect_logger
        return cls(
            config=config,
            crawler=crawler,
            logger=logger,
        )
    
    @staticmethod
    def _generate_start_urls_uuid(start_urls: List[str]) -> str:
        """
        Generate a deterministic UUID from the start URLs for consistency.
        
        Args:
            start_urls: List of start URLs
            
        Returns:
            The generated UUID string (as string, not UUID object)
        """
        try:
            def _get_netloc(url: str) -> str:
                parsed_url = urlparse(url)
                netloc = parsed_url.netloc.replace(':', '~').replace('_', '~')
                return netloc
            # Sort netlocs to ensure consistency
            sorted_netlocs = list(sorted(list(set(_get_netloc(url) for url in start_urls))))
            # Join netlocs to create a deterministic string
            combined_string = ",".join(sorted_netlocs)
            # Generate UUID from the combined string
            start_urls_uuid = uuid.uuid5(uuid.NAMESPACE_URL, combined_string)
            return str(start_urls_uuid)
        except Exception as e:
            logger = get_prefect_or_regular_python_logger(
                name="workflow_service.scraping.pipelines", 
                return_non_prefect_logger=True
            )
            logger.error(f"Failed to generate UUID for start URLs: {start_urls}. Using random UUID. Error: {e}", exc_info=True)
            random_uuid = uuid.uuid4()
            return str(random_uuid)
    
    @staticmethod
    def _generate_namespace_static(url: str, date_str: str, start_urls_uuid: str, logger: Optional[Logger] = None) -> str:
        try:
            parsed_url = urlparse(url)
            netloc = parsed_url.netloc.replace(':', '~').replace('_', '~')
            namespace = f"crawler_scraper_results_{start_urls_uuid}_{date_str}_{netloc}"
            return namespace
        except Exception as e:
            logger = get_prefect_or_regular_python_logger(
                name="workflow_service.scraping.pipelines", 
                return_non_prefect_logger=True
            )
            if logger:
                logger.warning(f"Failed to parse URL for namespace: {url}. Using fallback. Error: {e}")
            return f"crawler_scraper_results_unknown_{date_str}"
    
    def _generate_namespace(self, url: str) -> str:
        """
        Generate namespace for the scraped data.
        
        Format: crawler_scraper_results_{start_urls_uuid}_YYYYMMDD_<netloc>
        
        Args:
            url: The URL that was scraped
            
        Returns:
            The generated namespace string
        """
        return self._generate_namespace_static(url, self.date_str, self.config['start_urls_uuid'], self.logger)
    
    def _generate_docname(self, url: str) -> str:
        """
        Generate document name for the scraped data.
        
        Format: scraped_url_result_<UUID> where UUID is constructed from URL
        
        Args:
            url: The URL that was scraped
            
        Returns:
            The generated document name string
        """
        try:
            # Generate a deterministic UUID from the URL for consistency
            url_uuid = uuid.uuid5(uuid.NAMESPACE_URL, url)
            docname = f"scraped_url_result_{url_uuid}"
            return docname
        except Exception as e:
            self.logger.warning(f"Failed to generate UUID for URL: {url}. Using random UUID. Error: {e}")
            random_uuid = uuid.uuid4()
            return f"scraped_url_result_{random_uuid}"

    @staticmethod
    def _extract_crawler_config(crawler) -> Dict[str, Any]:
        """
        Extract configuration from spider for MongoDB storage.
        
        Gets org_id, user, and is_shared settings from the spider's job_config.
        
        Args:
            spider: The spider instance
            
        Returns:
            Dictionary with extracted configuration
        """
        settings = crawler.settings
        
        # Extract required fields with sensible defaults
        start_urls = settings.get('start_urls')
        org_id = settings.get('org_id')
        user = settings.get('user')
        is_shared = settings.get('is_shared', False)
        date_str = settings.get('date_str')

        classify_pages_as_blog = settings.get('CLASSIFY_PAGES_AS_BLOG', scraping_settings.CLASSIFY_PAGES_AS_BLOG)
        blog_classifier_model = settings.get('BLOG_CLASSIFIER_MODEL', scraping_settings.BLOG_CLASSIFIER_MODEL)
        blog_classifier_max_length = settings.get('BLOG_CLASSIFIER_MAX_LENGTH', scraping_settings.BLOG_CLASSIFIER_MAX_CONTENT_LENGTH)

        if not (org_id and user):
            raise ValueError("Missing required configuration: org_id, user")
        
        return {
            'org_id': org_id,
            'user': user,
            'is_shared': is_shared,
            'start_urls_uuid': MongoCustomerDataPipeline._generate_start_urls_uuid(start_urls),
            "date_str": date_str,
            "classify_pages_as_blog": classify_pages_as_blog,
            "blog_classifier_model": blog_classifier_model,
            "blog_classifier_max_length": blog_classifier_max_length,
        }
    
    async def process_item(self, item: Dict[str, Any], spider: Spider) -> Dict[str, Any]:
        """
        Process and save a scraped item to MongoDB.
        
        Args:
            item: The scraped item data
            spider: The spider instance
            
        Returns:
            The original item (for potential further pipeline processing)
        """
                # Use double-checked locking pattern for thread-safe initialization
        if self.customer_data_service is None:
            async with self._service_init_lock:
                # Double-check after acquiring the lock
                if self.customer_data_service is None:
                    self.customer_data_service = await get_customer_data_service_no_dependency(
                            include_versioned=False
                    )

        self.items_processed += 1

        if self.config.get('classify_pages_as_blog'):
            item['is_blog'] = True
            try:
                is_blog, parsed_classification, _ = await classify_item_is_blog(
                    item,
                    model=self.config.get('blog_classifier_model'),
                    max_content_length=self.config.get('blog_classifier_max_length'),
                )
                item['is_blog'] = is_blog
                item['is_blog__reason'] = parsed_classification.brief_reason
            except Exception as e:
                self.logger.error(f"Failed to classify item as blog: {e}. Item URL: {item.get('url', 'unknown')}", exc_info=True)
        
        try:
            # Extract spider configuration
            config = self.config
            
            # Extract URL from item or try to infer from available data
            # In Scrapy, the URL is typically not stored in the item by default,
            # but we can get it from various sources
            current_url = item.get('url')
            
            # Generate namespace and docname
            namespace = self._generate_namespace(current_url)
            self.crawler.stats.inc_value(f'scraping_results/namespace/{namespace}', 1)
            docname = self._generate_docname(current_url)

            # TODO: FIXME: clean up namespaces before starting job to avoid collision conflicts from same day scrapes!
            #     POTENTIALLY also generate hash for scraping config to differentiate differently configured scrapes for caching??
            
            # Get database session using the proper async session manager
            async with get_async_db_as_manager() as db_session:
                # Save to MongoDB using the no-lock method for better performance
                # Note: no-lock method returns bool, not tuple
                is_created = await self.customer_data_service._create_or_update_unversioned_document_no_lock(
                    db=db_session,
                    org_id=config['org_id'],
                    namespace=namespace,
                    docname=docname,
                    is_shared=config['is_shared'],
                    user=config['user'],
                    data=item,
                    is_called_from_workflow=True,  # This is being called from a workflow context
                )
                
                self.items_saved += 1
                self.logger.debug(
                    f"Saved scraped item to MongoDB: namespace={namespace}, docname={docname}, "
                    f"created={is_created}, url={current_url}"
                )
                
                # Add storage info to item for potential use by other pipelines
                item['_mongodb_storage'] = {
                    'namespace': namespace,
                    'docname': docname,
                    'org_id': str(config['org_id']),
                    'is_shared': config['is_shared'],
                    'saved_at': datetime.now().isoformat(),
                    'is_created': is_created
                }
            
        except Exception as e:
            self.items_failed += 1
            self.logger.error(
                f"Failed to save item to MongoDB: {e}. Item URL: {item.get('url', 'unknown')}", 
                exc_info=True
            )
            
            # Add error info to item
            item['_mongodb_storage_error'] = {
                'error': str(e),
                'failed_at': datetime.now().isoformat()
            }
        
        return item 


if __name__ == "__main__":
    async def main():
        # pipeline = StreamingFilePipeline(base_dir="services/workflow_service/services/scraping/data")
        # item = {
        #     "url": "https://www.google.com",
        #     "title": "Google",
        #     "content": "Google is a search engine."
        # }
        # await pipeline.process_item(item, None)

        item = {
            "url": "https://www.google.com",
            "title": "Google",
            "content": "Google is a search engine."
        }
        is_blog, classification, filtered_item = await classify_item_is_blog(item)
        print(is_blog, classification, filtered_item)

        import ipdb; ipdb.set_trace()

        item = {
            "url": "https://www.google.com/blog/2025/01/google-is-a-search-engine.html",
            "title": "Google",
            "content": "Google is a search engine. This is a blog post about Google."
        }
        is_blog, classification, filtered_item = await classify_item_is_blog(item)
        print(is_blog, classification, filtered_item)

        import ipdb; ipdb.set_trace()
    
    # asyncio.run(main())

    # system_prompt: str = (
    #     "You are a precise content classifier. Determine if the provided item is a blog post.\n"
    #     "Definition of blog: long-form or article-like content such as posts, news, stories, case studies, "
    #     "or knowledge articles, typically intended for reading.\n\n"
    #     "Return only the structured object requested by the tool (no extra prose).\n"
    #     "Constraints: brief_reason must be at most 20 words (keep it succinct)."
    # )
    # print(system_prompt)
