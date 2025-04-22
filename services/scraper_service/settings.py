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
    RAPID_API_HOST: str = os.getenv("RAPID_API_HOST", "linkedin-profiles-and-company-data.p.rapidapi.com")
    
    # Test Settings
    TEST_PROFILE_USERNAME: str = os.getenv("TEST_PROFILE_USERNAME")
    TEST_PROFILE_URL: str = os.getenv("TEST_PROFILE_URL")
    TEST_POST_PROFILE_USERNAME: str = os.getenv("TEST_POST_PROFILE_USERNAME")
    TEST_POST_COMPANY_USERNAME: str = os.getenv("TEST_POST_COMPANY_USERNAME")
    TEST_COMPANY_USERNAME: str = os.getenv("TEST_COMPANY_USERNAME")
    TEST_COMPANY_URL: str = os.getenv("TEST_COMPANY_URL")

    
    # Retry configuration
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES"))
    RETRY_DELAY: int = int(os.getenv("RETRY_DELAY"))  # seconds
    
    # Request Settings
    DEFAULT_POST_LIMIT: int = int(os.getenv("DEFAULT_POST_LIMIT", 50))  # Multiple of 50 always , because batch size is 50 so basically if this 1 or 50 , the credit consumed will be same that is why 50
    DEFAULT_COMMENT_LIMIT: int = int(os.getenv("DEFAULT_COMMENT_LIMIT", 50)) #this will not matter actually , as comments are fetched per post
    DEFAULT_REACTION_LIMIT: int = int(os.getenv("DEFAULT_REACTION_LIMIT", 30)) #this limit is a little varied , was trying was getting different amount in every batch


    # Rate Limiting Settings
    DEFAULT_DELAY_SECONDS: int = int(os.getenv("DEFAULT_DELAY_SECONDS"))
    BATCH_SIZE: int = int(os.getenv("BATCH_SIZE"))
    RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS"))  # Number of requests per time window
    RATE_LIMIT_PERIOD: int = int(os.getenv("RATE_LIMIT_PERIOD"))    # Time window in seconds
    
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
    DEFAULT_PAGE_SIZE: int = int(os.getenv("DEFAULT_PAGE_SIZE", 20))
    MAX_PAGE_SIZE: int = int(os.getenv("MAX_PAGE_SIZE", 100))
    MIN_PAGE_SIZE: int = int(os.getenv("MIN_PAGE_SIZE", 5))
    

    
    # Request Timeout
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", 30))  # Request timeout in seconds
    
    # Endpoint Configuration
    ENDPOINTS: Dict[str, str] = {
        "profile": "/",
        "company": "/get-company-details",
        "company_details": "/get-company-details",
        "posts": "/get-post",
        "comments": "/get-post-comments",
        "reactions": "/get-post-reactions",
        "profile_posts": "/get-profile-posts",
        "company_posts": "/get-company-posts",
        "profile_post_comments": "/get-profile-posts-comments",
        "company_post_comments": "/get-company-post-comments",
        "profile_likes": "/get-profile-likes",
        "profile_comments_made": "/get-profile-comments", # Endpoint for comments *made by* the user
    }
    
# Create settings instance
rapid_api_settings = RapidAPISettings() 