"""
Settings for the RapidAPI LinkedIn scraper client.
This module provides configuration settings for the RapidAPI LinkedIn scraper client,
inheriting from the global settings configuration.
"""

import os
from typing import Optional, Dict, Any, List
from pathlib import Path
from global_config.settings import Settings as GlobalSettings


class RapidAPISettings(GlobalSettings):
    """
    Settings for the RapidAPI LinkedIn scraper client.
    
    This class inherits from the global settings and provides additional configuration
    specific to the RapidAPI LinkedIn scraper client.
    Settings can be provided through environment variables or .env files.
    """
    
    # API Settings
    RAPID_API_KEY: Optional[str] = os.getenv("RAPID_API_KEY")
    RAPID_API_HOST: str = os.getenv("RAPID_API_HOST", "real-time-people-company-data.p.rapidapi.com")  # real-time-people-company-data.p.rapidapi.com    linkedin-data-api.p.rapidapi.com
        
    # Retry configuration
    SCRAPER_SERVICE_MAX_RETRIES: int = int(os.getenv("SCRAPER_SERVICE_MAX_RETRIES", 3))
    SCRAPER_SERVICE_RETRY_DELAY: int = int(os.getenv("SCRAPER_SERVICE_RETRY_DELAY", 5))  # seconds
    
    # Request Settings
    DEFAULT_POST_LIMIT: int = int(os.getenv("DEFAULT_POST_LIMIT", 50))  # Multiple of 50 always , because batch size is 50 so basically if this 1 or 50 , the credit consumed will be same that is why 50
    DEFAULT_COMMENT_LIMIT: int = int(os.getenv("DEFAULT_COMMENT_LIMIT", 50)) #this will not matter actually , as comments are fetched per post
    # TODO: FIXME: confirm this here for paginated API: https://rapidapi.com/rockapis-rockapis-default/api/linkedin-data-api/playground/apiendpoint_05186403-0154-462c-ab21-a10657f13a58
    DEFAULT_REACTION_LIMIT: int = int(os.getenv("DEFAULT_REACTION_LIMIT", 50)) #this limit is a little varied , was trying was getting different amount in every batch

    SCRAPER_SERVICE_BATCH_SIZE: int = int(os.getenv("SCRAPER_SERVICE_BATCH_SIZE", 50))
    SCRAPER_SERVICE_BATCH_SIZE_FOR_ACTIVITY_REACTIONS: int = int(os.getenv("SCRAPER_SERVICE_BATCH_SIZE_FOR_ACTIVITY_REACTIONS", 100))
    SCRAPER_SERVICE_RATE_LIMIT_REQUESTS: int = int(os.getenv("SCRAPER_SERVICE_RATE_LIMIT_REQUESTS", 10))  # Number of requests per time window

    SCRAPER_SERVICE_SEARCH_BY_KEYWORD_BATCH_SIZE: int = 10
    SCRAPER_SERVICE_SEARCH_BY_HASHTAG_BATCH_SIZE: int = 50

    # Rate Limiting Settings
    SCRAPER_SERVICE_DEFAULT_DELAY_SECONDS: int = int(os.getenv("SCRAPER_SERVICE_DEFAULT_DELAY_SECONDS", 1))
    SCRAPER_SERVICE_RATE_LIMIT_PERIOD: int = int(os.getenv("SCRAPER_SERVICE_RATE_LIMIT_PERIOD", 60))    # Time window in seconds
    
    # Default Headers
    @property
    def DEFAULT_HEADERS(self) -> Dict[str, str]:
        """Return the default headers for RapidAPI requests."""
        headers = {
            "X-RapidAPI-Host": self.RAPID_API_HOST,
            "Content-Type": "application/json"
        }
        if self.RAPID_API_KEY:
            headers["X-RapidAPI-Key"] = self.RAPID_API_KEY
        return headers
    
    # Pagination Settings
    SCRAPING_SERVICE_DEFAULT_PAGE_SIZE: int = int(os.getenv("SCRAPING_SERVICE_DEFAULT_PAGE_SIZE", 20))
    SCRAPING_SERVICE_MAX_PAGE_SIZE: int = int(os.getenv("SCRAPING_SERVICE_MAX_PAGE_SIZE", 100))
    SCRAPING_SERVICE_MIN_PAGE_SIZE: int = int(os.getenv("SCRAPING_SERVICE_MIN_PAGE_SIZE", 5))

    
    # Request Timeout
    SCRAPING_SERVICE_REQUEST_TIMEOUT: int = int(os.getenv("SCRAPING_SERVICE_REQUEST_TIMEOUT", 30))  # Request timeout in seconds
    
    # Endpoint Configuration
    RAPID_API_ENDPOINTS: Dict[str, str] = {
        "profile": "/",
        "company": "/get-company-details", 
        "company_details": "/get-company-details",
        "comments": "/get-post-comments",
        "profile_posts": "/get-profile-posts",
        "company_posts": "/get-company-posts",
        "profile_post_comments": "/get-profile-posts-comments",
        "company_post_comments": "/get-company-post-comments",
        "post_reactions":"/get-post-reactions",
        "profile_likes": "/get-profile-likes",
        "profile_comments_made": "/get-profile-comments", # Endpoint for comments *made by* the user
        "search_post_by_keyword":"/search-posts",
        "search_post_by_hashtag":"/search-posts-by-hashtag",
        "post_details":"/get-post",
    }
    
# Create settings instance
rapid_api_settings = RapidAPISettings() 
