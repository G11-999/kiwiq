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
from scraper_service.client.schemas.activity_schema import GetProfileCommentResponse
from scraper_service.client.schemas.profile_schema import (
    ProfileResponse,
    ProfileRequest,
    CompanyRequest,
    CompanyResponse
)
from scraper_service.client.schemas.posts_schema import (
    
    ProfilePostCommentsRequest
)

from scraper_service.client.schemas.activity_schema import (
    GetProfileCommentResponse
)


from pydantic import BaseModel


from global_config.logger import get_prefect_or_regular_python_logger

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
        self.logger = get_prefect_or_regular_python_logger(__name__)
        
        # Verify API key is set
        if not self.api_key:
            self.logger.warning("RapidAPI key is not set. API requests will fail.")

    def _get_url(self, endpoint: str) -> str:
        return f"https://{self.base_url}{endpoint}"
    
    def validate_api_key(self) -> bool:
        """
        Validate that the API key is set.
        
        Returns:
            bool: True if API key is set, False otherwise.
        """
        return bool(self.api_key)
    
    async def parse_response(self, response: aiohttp.ClientResponse) -> Dict[str, Any]:
        """
        Parses the HTTP response from aiohttp.

        Args:
            response (aiohttp.ClientResponse): The response object.

        Returns:
            Dict[str, Any]: Parsed JSON data or an error dictionary.
        """
        try:
            # Check for non-successful status codes first
            response.raise_for_status() 
            # Attempt to parse JSON
            json_response = await response.json()
            # import ipdb; ipdb.set_trace()
            # Basic check if the API itself indicates failure (common pattern)
            if isinstance(json_response, dict) and not json_response.get("success", True):
                 error_msg = json_response.get("message", "API indicated failure without specific message.")
                 self.logger.warning(f"API request successful (HTTP {response.status}) but API returned success=false: {error_msg}")
                 # Include the error message in the response for upstream handling
                 json_response["error"] = error_msg # Add error key for consistency

            return json_response
        except aiohttp.ClientResponseError as http_error:
            # Handle HTTP errors (4xx, 5xx)
            self.logger.error(f"HTTP error {http_error.status}: {http_error.message} for URL {response.url}")
            # Try to get error details from response body if possible
            try:
                error_body = await response.text()
                self.logger.error(f"Error response body: {error_body[:500]}") # Log beginning of body
                # Attempt to parse as JSON to extract API specific error message
                error_json = json.loads(error_body)
                api_message = error_json.get("message", http_error.message)
                return {"error": f"HTTP {http_error.status}: {api_message}", "status_code": http_error.status}
            except Exception: # Fallback if body isn't JSON or other error
                 return {"error": f"HTTP {http_error.status}: {http_error.message}", "status_code": http_error.status}
        except json.JSONDecodeError:
            # Handle cases where response is not valid JSON
            self.logger.error(f"Failed to decode JSON response from {response.url}. Status: {response.status}")
            return {"error": "Invalid JSON response from API", "status_code": response.status}
        except Exception as e:
            # Catch any other unexpected errors during parsing
            self.logger.error(f"Unexpected error parsing response from {response.url}: {str(e)}")
            return {"error": f"Failed to parse response: {str(e)}", "status_code": response.status}
    
    async def make_get_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make an asynchronous GET request to the API endpoint.

        Args:
            endpoint (str): API endpoint to request (relative path).
            params (Optional[Dict[str, Any]]): Dictionary of query parameters.

        Returns:
            Dict[str, Any]: raw JSON response, potentially with an 'error' key on failure.

        Raises:
            ClientError: If there's an HTTP client error.
            TimeoutError: If the request times out.
            Exception: For any other unexpected errors.
        """
        url = self._get_url(endpoint)
        # Log the request with parameters for better debugging
        self.logger.info(f"Making GET API request to: {url} with params: {params}")

        try:
            async with aiohttp.ClientSession() as session:
                # Pass the params dictionary directly to session.get
                async with session.get(url, headers=self.headers, params=params, timeout=rapid_api_settings.SCRAPING_SERVICE_REQUEST_TIMEOUT) as response:
                    # Reuse the existing response parsing logic
                    return await self.parse_response(response)

        except aiohttp.ClientError as client_error:
            # Log and return structured error
            self.logger.error(f"HTTP client error during GET {url}: {str(client_error)}")
            return {"error": f"HTTP request failed: {str(client_error)}"}
        except asyncio.TimeoutError:
            # Log and return structured error
            self.logger.error(f"Request timed out after {rapid_api_settings.SCRAPING_SERVICE_REQUEST_TIMEOUT} seconds for GET {url}")
            return {"error": f"Request timed out after {rapid_api_settings.SCRAPING_SERVICE_REQUEST_TIMEOUT} seconds"}
        except Exception as e:
            # Log and return structured error for unexpected issues
            self.logger.error(f"Unexpected error in make_get_request for {url}: {str(e)}")
            return {"error": f"Request failed: {str(e)}"}

    async def make_get_request_with_delay(self, endpoint: str, delay_seconds: int = None) -> Union[T, Dict[str, Any]]:
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
        await asyncio.sleep(delay_seconds or rapid_api_settings.SCRAPER_SERVICE_DEFAULT_DELAY_SECONDS)
        return await self.make_get_request(endpoint)
    
    async def make_post_request(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make an asynchronous POST request to the API endpoint.

        Args:
            endpoint (str): API endpoint to request.
            payload (Dict[str, Any]): JSON payload to send.

        Returns:
            Dict[str, Any]: raw JSON response, potentially with an 'error' key on failure.

        Raises:
            ClientError: If there's an HTTP client error.
            TimeoutError: If the request times out.
            Exception: For any other unexpected errors.
        """
        url = self._get_url(endpoint)
        self.logger.info(f"Making POST API request to: {url}")
        # Avoid logging sensitive parts of payload if necessary in future
        self.logger.debug(f"Request payload: {payload}")

        try:
            async with aiohttp.ClientSession() as session:
                # Ensure Content-Type is set for JSON payload
                headers = self.headers.copy()
                headers['Content-Type'] = 'application/json'

                async with session.post(url, headers=headers, json=payload, timeout=rapid_api_settings.SCRAPING_SERVICE_REQUEST_TIMEOUT) as response:
                     # Reuse the same response parsing logic
                    return await self.parse_response(response)

        except aiohttp.ClientError as client_error:
            # Log and return structured error
            self.logger.error(f"HTTP client error during POST {url}: {str(client_error)}")
            return {"error": f"HTTP request failed: {str(client_error)}"}
        except asyncio.TimeoutError:
            # Log and return structured error
            self.logger.error(f"Request timed out after {rapid_api_settings.SCRAPING_SERVICE_REQUEST_TIMEOUT} seconds for POST {url}")
            return {"error": f"Request timed out after {rapid_api_settings.SCRAPING_SERVICE_REQUEST_TIMEOUT} seconds"}
        except Exception as e:
            # Log and return structured error
            self.logger.error(f"Unexpected error in make_post_request for {url}: {str(e)}")
            return {"error": f"Request failed: {str(e)}"}
    
    async def get_profile_data(self, request: Dict[str, Any]) -> ProfileResponse:
        """
        Get LinkedIn profile data.
        
        Args:
            request (Dict[str, Any]): Request object containing the LinkedIn username.
            
        Returns:
            ProfileResponse: Profile data response object.
            
        Example:
            >>> request = ProfileRequest(username="john-doe") # TODO: FIXME: this is not correct!
            >>> profile = await client.get_profile_data(request)
            >>> print(profile.firstName, profile.lastName)
        """
       
        endpoint = f"{rapid_api_settings.RAPID_API_ENDPOINTS['profile']}"
        params = {"username": request['username']}
        response = await self.make_get_request(endpoint, params=params)
        if "error" in response:
            self.logger.error(f"Error fetching profile data for {request['username']}: {response['error']}")
            return response
        if "data" in response:
            response = response["data"]
        # NOTE: this will propagate errors too in errors keys!
        return ProfileResponse.model_construct(**response)
    
    
    async def get_company_data(self, request: Dict[str, Any]) -> CompanyResponse:
        """
        Get LinkedIn company data.
        
        Args:
            request (Dict[str, Any]): Request object containing the LinkedIn company username.
            
        Returns:
            CompanyResponse: Company data response object.
            
        Example:
            >>> request = CompanyRequest(username="microsoft") # TODO: FIXME: this is not correct!
            >>> company = await client.get_company_data(request)
            >>> print(company.data.name, company.data.followerCount)
        """
        endpoint = f"{rapid_api_settings.RAPID_API_ENDPOINTS['company_details']}"
        params = {"username": request['username']}
        response_data = await self.make_get_request(endpoint, params=params)
        if "error" in response_data:
            self.logger.error(f"Error fetching company data for {request['username']}: {response_data['error']}")
            return response_data
        if "data" in response_data:
            response_data = response_data["data"]

        # NOTE: this will propagate errors too in errors keys!
        return CompanyResponse.model_construct(**response_data)
