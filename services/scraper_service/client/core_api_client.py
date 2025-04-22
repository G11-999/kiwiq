"""
Core RapidAPI client for LinkedIn scraping.

This module provides a base class for making requests to the RapidAPI LinkedIn scraper.
"""

import json
import time
import aiohttp
import asyncio
import http.client
from typing import Dict, List, Any, Optional, Union, TypeVar, Type, Generic
from pydantic import TypeAdapter

from scraper_service.client.utils.url_helper import extract_urn_from_url, encode_urn
from scraper_service.settings import rapid_api_settings
from scraper_service.client.schemas import (
    ProfileResponse,
    ProfileRequest,
    CompanyRequest,
    CompanyResponse,
    GetProfileCommentResponse,

 
)
from pydantic import BaseModel


from global_config.logger import get_logger
logger = get_logger(__name__)

# Generic type for Pydantic models
T = TypeVar('T', bound=BaseModel)

 #This module covers the core api client for the rapid api
 #First api is for validating the api key , basically to check if the api key is valid or not
 #Second api is for getting the profile data , basically to get the profile data of the Linkedin user
 #Third api is for getting the profile post comments , basically to get the comments of the profile posts
 #Fourth api is for getting the company data , basically to get the company data of the user

class RapidAPIClient(Generic[T]):
    """
    Base client for interacting with the RapidAPI LinkedIn scraper.
    
    This client handles the HTTP connection and request formatting
    for the RapidAPI LinkedIn scraper. It provides methods for making
    GET and POST requests with appropriate headers and error handling.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        Initialize the RapidAPI client.
        
        Args:
            api_key (Optional[str]): API key for RapidAPI. Defaults to settings value.
            base_url (Optional[str]): Base URL for the RapidAPI endpoint. Defaults to settings value.
        """
        self.api_key = api_key or rapid_api_settings.RAPID_API_KEY
        self.base_url = base_url or rapid_api_settings.RAPID_API_HOST
        self.headers = {
            'x-rapidapi-key': self.api_key,
            'x-rapidapi-host': self.base_url
        }
        
        # Verify API key is set
        if not self.api_key:
            logger.warning("RapidAPI key is not set. API requests will fail.")

    def validate_api_key(self) -> bool:
        """
        Validate that the API key is set.
        
        Returns:
            bool: True if API key is set, False otherwise.
        """
        return bool(self.api_key)

    async def make_get_request(self, endpoint: str, response_model: Type[T] = None) -> Union[T, Dict[str, Any]]:
        """
        Make an asynchronous GET request to the API endpoint.
        
        Args:
            endpoint (str): API endpoint to request.
            response_model (Type[T], optional): Pydantic model to parse the response.
            
        Returns:
            Union[T, Dict[str, Any]]: Parsed model instance or raw JSON response.
            
        Raises:
            ClientError: If there's an HTTP client error.
            TimeoutError: If the request times out.
            Exception: For any other unexpected errors.
        """
        url = f"https://{self.base_url}{endpoint}"
        logger.info(f"Making API request to: {url}")
        
        try:
            async with aiohttp.ClientSession() as session:
                safe_headers = self.headers.copy()
                if 'x-rapidapi-key' in safe_headers:
                    safe_headers['x-rapidapi-key'] = safe_headers['x-rapidapi-key'][:8] + '...'
                logger.info(f"Request headers: {safe_headers}")
                
                async with session.get(url, headers=self.headers, timeout=rapid_api_settings.REQUEST_TIMEOUT) as response:
                    logger.info(f"API response status: {response.status}")
                    
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"API error response: {error_text[:200]}...")
                        return {"error": f"Request failed with status {response.status}"}
                    
                    result = await response.json()
                    logger.info(f"API response keys: {list(result.keys())}")

                    # Auto-detect whether 'data' wrapping is needed
                    if response_model and result:
                        try:
                            if 'data' in result and hasattr(response_model, '__fields__') and 'data' in response_model.__fields__:
                                return response_model.model_validate(result)
                            elif 'data' in result:
                                return response_model.model_validate(result['data'])
                            else:
                                return response_model.model_validate(result)
                        except Exception as parse_error:
                            logger.error(f"Failed to parse response with model {response_model.__name__}: {str(parse_error)}")
                            return result
                    
                    return result

        except aiohttp.ClientError as client_error:
            logger.error(f"HTTP client error: {str(client_error)}")
            return {"error": f"HTTP request failed: {str(client_error)}"}
        except asyncio.TimeoutError:
            logger.error(f"Request timed out after {rapid_api_settings.REQUEST_TIMEOUT} seconds")
            return {"error": f"Request timed out after {rapid_api_settings.REQUEST_TIMEOUT} seconds"}
        except Exception as e:
            logger.error(f"Unexpected error in make_get_request: {str(e)}")
            return {"error": f"Request failed: {str(e)}"}

    async def make_get_request_with_delay(self, endpoint: str, response_model: Type[T] = None, delay_seconds: int = None) -> Union[T, Dict[str, Any]]:
        """
        Make a GET request to the API with rate limiting delay.
        
        Args:
            endpoint (str): API endpoint to request.
            response_model (Type[T], optional): Pydantic model to parse the response.
            delay_seconds (int, optional): Number of seconds to wait before making the request.
            
        Returns:
            Union[T, Dict[str, Any]]: Parsed model instance or raw JSON response.
        """
        # Apply delay before each request (use settings default if not specified)
        await asyncio.sleep(delay_seconds or rapid_api_settings.DEFAULT_DELAY_SECONDS)
        return await self.make_get_request(endpoint, response_model)
    
    async def make_post_request(self, endpoint: str, payload: Dict[str, Any], response_model: Type[T] = None) -> Union[T, Dict[str, Any]]:
        """
        Make an asynchronous POST request to the API endpoint.
        
        Args:
            endpoint (str): API endpoint to request.
            payload (Dict[str, Any]): JSON payload to send.
            response_model (Type[T], optional): Pydantic model to parse the response.
            
        Returns:
            Union[T, Dict[str, Any]]: Parsed model instance or raw JSON response.
            
        Raises:
            ClientError: If there's an HTTP client error.
            TimeoutError: If the request times out.
            Exception: For any other unexpected errors.
        """
        url = f"https://{self.base_url}{endpoint}"
        logger.info(f"Making POST API request to: {url}")
        
        try:
            async with aiohttp.ClientSession() as session:
                # Add content type header for POST requests
                headers = self.headers.copy()
                headers['Content-Type'] = 'application/json'
                
                # Log headers (remove sensitive parts)
                safe_headers = headers.copy()
                if 'x-rapidapi-key' in safe_headers:
                    safe_headers['x-rapidapi-key'] = safe_headers['x-rapidapi-key'][:8] + '...'
                logger.info(f"Request headers: {safe_headers}")
                logger.info(f"Request payload: {payload}")
                
                async with session.post(url, headers=headers, json=payload, timeout=rapid_api_settings.REQUEST_TIMEOUT) as response:
                    status = response.status
                    logger.info(f"API response status: {status}")
                    
                    if status != 200:
                        try:
                            error_text = await response.text()
                            logger.error(f"API error response: {error_text[:200]}...")
                        except Exception as text_error:
                            logger.error(f"Failed to read error response: {str(text_error)}")
                        return {"error": f"Request failed with status {status}"}
                    
                    try:
                        result = await response.json()
                        if isinstance(result, dict):
                            logger.info(f"API response keys: {list(result.keys())}")
                            
                        # Parse response using the provided model if specified
                        if response_model and result:
                            try:
                                return response_model(**result)
                            except Exception as parse_error:
                                logger.error(f"Failed to parse response with model {response_model.__name__}: {str(parse_error)}")
                                return result
                        return result
                    except Exception as json_error:
                        text = await response.text()
                        logger.error(f"Failed to parse JSON, first 200 chars: {text[:200]}...")
                        return {"error": "Failed to parse JSON", "response": text[:500]}
        except aiohttp.ClientError as client_error:
            logger.error(f"HTTP client error: {str(client_error)}")
            return {"error": f"HTTP request failed: {str(client_error)}"}
        except asyncio.TimeoutError:
            logger.error(f"Request timed out after {rapid_api_settings.REQUEST_TIMEOUT} seconds")
            return {"error": f"Request timed out after {rapid_api_settings.REQUEST_TIMEOUT} seconds"}
        except Exception as e:
            logger.error(f"Unexpected error in make_post_request: {str(e)}")
            return {"error": f"Request failed: {str(e)}"}
    
    async def get_profile_data(self, request: ProfileRequest) -> ProfileResponse:
        """
        Get LinkedIn profile data.
        
        Args:
            request (ProfileRequest): Request object containing the LinkedIn username.
            
        Returns:
            ProfileResponse: Profile data response object.
            
        Example:
            >>> request = ProfileRequest(username="john-doe")
            >>> profile = await client.get_profile_data(request)
            >>> print(profile.firstName, profile.lastName)
        """
        endpoint = f"{rapid_api_settings.ENDPOINTS['profile']}?username={request.username}"
        return await self.make_get_request(endpoint, ProfileResponse)

        
    async def get_profile_post_comments(self, request: ProfileRequest) -> List[GetProfileCommentResponse]:
        """
        Fetch LinkedIn profile comments for a user.

        Args:
            request (ProfileRequest): Request with LinkedIn username

        Returns:
            List[GetProfileCommentResponse]: List of parsed comment models
        """
        endpoint = f"{rapid_api_settings.ENDPOINTS['profile_comments_made']}?username={request.username}"
        raw_response = await self.make_get_request(endpoint, GetProfileCommentResponse)

        # Ensure response is list
        if not isinstance(raw_response, list):
            raise ValueError(f"Expected list from API, got: {type(raw_response)} - {raw_response}")

        return TypeAdapter(List[GetProfileCommentResponse]).validate_python(raw_response)
    
    async def get_company_data(self, request: CompanyRequest) -> CompanyResponse:
        """
        Get LinkedIn company data.
        
        Args:
            request (CompanyRequest): Request object containing the LinkedIn company username.
            
        Returns:
            CompanyResponse: Company data response object.
            
        Example:
            >>> request = CompanyRequest(username="microsoft")
            >>> company = await client.get_company_data(request)
            >>> print(company.data.name, company.data.followerCount)
        """
        endpoint = f"{rapid_api_settings.ENDPOINTS['company_details']}?username={request.username}"
        return await self.make_get_request(endpoint, CompanyResponse)
    
    @staticmethod
    async def extract_urn(post_url: str) -> Optional[str]:
        """
        Extract the URN from a LinkedIn post URL.
        
        Args:
            post_url (str): LinkedIn post URL.
            
        Returns:
            Optional[str]: Extracted URN or None if not found.
            
        Example:
            >>> post_url = "https://www.linkedin.com/posts/john-doe_activity-1234567890"
            >>> urn = await RapidAPIClient.extract_urn(post_url)
            >>> print(urn)
            "urn:li:activity:1234567890"
        """
        return extract_urn_from_url(post_url) 