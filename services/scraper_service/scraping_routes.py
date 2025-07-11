import asyncio
from collections import defaultdict
import json
import uuid
from typing import List, Optional, Dict, Any, Annotated, Union, AsyncGenerator

from fastapi import (
    APIRouter, Depends, HTTPException, status, Query, WebSocket,
    WebSocketDisconnect, Body, Path, Response # Added Path, Response
)

# --- Core Dependencies ---
from kiwi_app.settings import settings

# --- Auth Dependencies ---
from kiwi_app.auth.models import User
from kiwi_app.auth.dependencies import (
    get_current_active_verified_user,
)
# from kiwi_app.workflow_app.utils import workflow_logger
from kiwi_app.utils import get_kiwi_logger

from scraper_service.client.schemas.job_config_schema import parse_linkedin_url

scraping_logger = get_kiwi_logger(name="scraper_service.scraping")

scraping_router = APIRouter(
    prefix="/scraping",
    tags=["scraping"],
)
from pydantic import BaseModel, HttpUrl, ConfigDict
from typing import Optional

# Schema for LinkedIn URL parsing
class LinkedInURLSchema(BaseModel):
    """Schema for LinkedIn URL parsing request."""
    url: HttpUrl
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "https://www.linkedin.com/in/username/"
            }
        }
    )

# Schema for LinkedIn URL parsing
class LinkedInUsernameParseResponse(BaseModel):
    """Schema for LinkedIn URL parsing request."""
    username: str
    entity_type: str
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "username",
                "entity_type": "person"
            }
        }
    )

@scraping_router.post(
    "/parse-linkedin-url",
    response_model=LinkedInUsernameParseResponse,
    summary="Parse LinkedIn URL to extract username and entity type",
)
async def parse_linkedin_url_endpoint(
    url_data: LinkedInURLSchema,
    user: User = Depends(get_current_active_verified_user),
):
    """
    Parses a LinkedIn URL to extract the username and entity type (person or company).
    
    This endpoint accepts a LinkedIn profile or company URL and returns the extracted
    username and entity type. It's useful for preprocessing LinkedIn URLs before
    using them in other operations.
    
    Args:
        url_data: A dictionary containing the LinkedIn URL to parse
        
    Returns:
        A dictionary with extracted 'username' and 'type' fields
        
    Raises:
        HTTPException: If the URL is invalid or doesn't match expected LinkedIn patterns
    """
    try:
        # Create a copy of the input data to avoid modifying the original
        data_copy = url_data.model_dump()
        
        # Use the parse_linkedin_url function from job_config_schema
        username, entity_type = parse_linkedin_url(data_copy, set_in_data=False)
        
        scraping_logger.info(f"User {user.id} successfully parsed LinkedIn URL: {url_data.url}")
        return {"username": username, "entity_type": entity_type}
    
    except ValueError as e:
        scraping_logger.warning(f"User {user.id} provided invalid LinkedIn URL: {url_data.url} - {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
    except Exception as e:
        scraping_logger.error(f"Error parsing LinkedIn URL: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="An unexpected error occurred while parsing the LinkedIn URL"
        )
