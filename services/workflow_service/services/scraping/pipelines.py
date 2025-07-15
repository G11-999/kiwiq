"""
Simple streaming pipeline for scraped data.

Just write each item to a JSON file as it comes.
No buffering, no complexity, no data loss.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from scrapy import Spider
from global_config.logger import get_logger

logger = get_logger(__name__)


class StreamingFilePipeline:
    """
    Simple streaming pipeline that writes each item to disk immediately.
    
    Features:
    - No buffering (no data loss risk)
    - Simple JSON format
    - One file per job
    - Automatic directory creation
    """
    
    def __init__(self, base_dir: str = "services/workflow_service/services/scraping/data"):
        """
        Initialize streaming pipeline.
        
        Args:
            base_dir: Base directory for output files
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.file_handles = {}  # job_id -> file handle
        self.item_counts = {}   # job_id -> count
        
    @classmethod
    def from_crawler(cls, crawler):
        """Create pipeline from crawler settings."""
        settings = crawler.settings
        return cls(
            base_dir=settings.get('PIPELINE_BASE_DIR', 'services/workflow_service/services/scraping/data')
        )
    
    def open_spider(self, spider: Spider):
        """Open output file for spider."""
        job_id = getattr(spider, 'job_id', spider.name)
        
        # Create job directory
        job_dir = self.base_dir / job_id
        job_dir.mkdir(exist_ok=True)
        
        # Create output file with timestamp
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        output_file = job_dir / f"{job_id}_{timestamp}.jsonl"
        
        # Open file for streaming (line-delimited JSON)
        self.file_handles[job_id] = open(output_file, 'w', encoding='utf-8')
        self.item_counts[job_id] = 0
        
        logger.info(f"Opened output file: {output_file}")
    
    def close_spider(self, spider: Spider):
        """Close output file and log stats."""
        job_id = getattr(spider, 'job_id', spider.name)
        
        if job_id in self.file_handles:
            self.file_handles[job_id].close()
            count = self.item_counts.get(job_id, 0)
            logger.info(f"Closed output file for job {job_id}: {count} items written")
            
            # Cleanup
            del self.file_handles[job_id]
            del self.item_counts[job_id]
    
    def process_item(self, item: Dict[str, Any], spider: Spider) -> Dict[str, Any]:
        """Write item immediately to file."""
        job_id = getattr(spider, 'job_id', spider.name)
        
        # Ensure file is open
        if job_id not in self.file_handles:
            self.open_spider(spider)
        
        # Add metadata
        item_with_meta = dict(item)
        item_with_meta['_job_id'] = job_id
        item_with_meta['_spider'] = spider.name
        item_with_meta['_timestamp'] = datetime.utcnow().isoformat()
        
        # Write as JSON line
        try:
            json_line = json.dumps(item_with_meta, ensure_ascii=False, default=str)
            self.file_handles[job_id].write(json_line + '\n')
            self.file_handles[job_id].flush()  # Ensure it's written to disk
            
            self.item_counts[job_id] = self.item_counts.get(job_id, 0) + 1
            
            # Log every 100 items
            if self.item_counts[job_id] % 100 == 0:
                logger.info(f"Job {job_id}: {self.item_counts[job_id]} items written")
                
        except Exception as e:
            logger.error(f"Failed to write item for job {job_id}: {e}")
            # Don't raise - we don't want to stop the spider for one bad item
            
        return item 