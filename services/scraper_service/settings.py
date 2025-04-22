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
    RAPID_API_BASE_URL: str = "linkedin-profiles-and-company-data.p.rapidapi.com"
    RAPID_API_HOST: str = "linkedin-profiles-and-company-data.p.rapidapi.com"
    
    # Test Settings
    TEST_PROFILE_USERNAME: str = ""
    TEST_PROFILE_URL: str = ""
    TEST_POST_PROFILE_USERNAME: str = ""
    TEST_POST_COMPANY_USERNAME: str = ""
    TEST_COMPANY_USERNAME: str = ""
    TEST_COMPANY_URL: str = ""

    
    # Retry configuration
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 2  # seconds
    
    # Request Settings
    DEFAULT_POST_LIMIT: int = 50  # Multiple of 50 always , because batch size is 50 so basically if this 1 or 50 , the credit consumed will be same that is why 50
    DEFAULT_COMMENT_LIMIT: int = 50 #this will not matter actually , as comments are fetched per post
    DEFAULT_REACTION_LIMIT: int = 30 #this limit is a little varied , was trying was getting different amount in every batch

    
    # Rate Limiting Settings
    DEFAULT_DELAY_SECONDS: int = 5
    BATCH_SIZE: int = 50
    RATE_LIMIT_REQUESTS: int = 10  # Number of requests per time window
    RATE_LIMIT_PERIOD: int = 60    # Time window in seconds
    RATE_LIMIT_BACKOFF: int = 2    # Exponential backoff multiplier
    
    # Default Headers
    @property
    def DEFAULT_HEADERS(self) -> Dict[str, str]:
        return {
            "X-RapidAPI-Key": self.RAPID_API_KEY,
            "X-RapidAPI-Host": self.RAPID_API_HOST,
            "Content-Type": "application/json"
        }
    
    # Pagination Settings
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100
    MIN_PAGE_SIZE: int = 5
    

    
    # Request Timeout
    REQUEST_TIMEOUT: int = 30  # Request timeout in seconds
    
    # Endpoint Configuration
    ENDPOINTS: Dict[str, str] = {
        "profile": "/",
        "company": "/get-company-details",
        "company_details": "/get-company-details",
        "posts": "/get-post",
        "comments": "/get-post-comments",
        "reactions": "/get-post-reactions"
    }
    
    class Config:
        """
        Pydantic configuration for settings.
        """
        env_file = ".env"
        env_prefix = "SCRAPER_"
        case_sensitive = True

# Create settings instance
rapid_api_settings = RapidAPISettings() 