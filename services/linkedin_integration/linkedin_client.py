"""
LinkedIn API client implementation using Rest.li framework.

This module provides a high-level interface for interacting with LinkedIn's API
for both individual members and organization pages. It handles authentication,
post management, analytics, and employee advocacy features.
"""

from typing import Dict, List, Optional, Union, Any
from datetime import datetime, timedelta, timezone
import json
import logging
from urllib.parse import urlencode, quote
import re

from linkedin_api.clients.restli.client import RestliClient
from pydantic import BaseModel, Field

from linkedin_integration.caching import dump_to_json, load_and_get_key

from linkedin_integration.models import (
    LinkedInAccount, LinkedInPost, 
    LinkedInComment,
    LinkedInReaction, LinkedInAnalytics, LinkedInPostAnalytics
)
from global_config.settings import global_settings

logger = logging.getLogger(__name__)

# Pydantic models for social actions responses
class LikesSummary(BaseModel):
    selected_likes: List[Any] = Field([], alias="selectedLikes")
    aggregated_total_likes: int = Field(0, alias="aggregatedTotalLikes")
    liked_by_current_user: bool = Field(False, alias="likedByCurrentUser")
    total_likes: int = Field(0, alias="totalLikes")

class CommentsSummary(BaseModel):
    selected_comments: List[Any] = Field([], alias="selectedComments")
    total_first_level_comments: int = Field(0, alias="totalFirstLevelComments")
    comments_state: str = Field("OPEN", alias="commentsState")
    aggregated_total_comments: int = Field(0, alias="aggregatedTotalComments")

class SocialActionsSummary(BaseModel):
    likes_summary: Optional[LikesSummary] = Field(None, alias="likesSummary")
    comments_summary: Optional[CommentsSummary] = Field(None, alias="commentsSummary")
    target: Optional[str] = None

# Pydantic models for share statistics responses
class ShareStatisticsData(BaseModel):
    click_count: int = Field(0, alias="clickCount")
    comment_count: int = Field(0, alias="commentCount")
    engagement: float = Field(0.0, alias="engagement")
    impression_count: int = Field(0, alias="impressionCount")
    like_count: int = Field(0, alias="likeCount")
    share_count: int = Field(0, alias="shareCount")
    unique_impressions_count: Optional[int] = Field(None, alias="uniqueImpressionsCount")
    comment_mentions_count: Optional[int] = Field(None, alias="commentMentionsCount")
    share_mentions_count: Optional[int] = Field(None, alias="shareMentionsCount")

class ShareStatistics(BaseModel):
    organizational_entity: str = Field(..., alias="organizationalEntity")
    share: Optional[str] = None  # For Share: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/share-statistics?view=li-lms-2025-02&tabs=http
    ugc_post: Optional[str] = Field(None, alias="ugcPost")  # For UGC Post
    time_range: Optional[Dict[str, int]] = Field(None, alias="timeRange")
    total_share_statistics: ShareStatisticsData = Field(..., alias="totalShareStatistics")

class ShareStatisticsResponse(BaseModel):
    elements: List[ShareStatistics]
    # paging: Dict[str, Any]

# Follower statistics models
class FollowerCounts(BaseModel):
    organic_follower_count: int = Field(..., alias="organicFollowerCount")
    paid_follower_count : int = Field(..., alias="paidFollowerCount")

class FollowerGain(BaseModel):
    organic_follower_gain: int = Field(..., alias="organicFollowerGain")
    paid_follower_gain: int = Field(..., alias="paidFollowerGain")

class FollowerStatistics(BaseModel):
    follower_counts: Optional[FollowerCounts] = Field(None, alias="followerCounts")
    follower_gains: Optional[FollowerGain] = Field(None, alias="followerGains")
    organizational_entity: str = Field(..., alias="organizationalEntity")
    time_range: Dict[str, int] = Field(..., alias="timeRange")

class FollowerStatisticsResponse(BaseModel):
    elements: List[FollowerStatistics]
    # paging: Dict[str, Any]


# Define a helper model to hold counts
class FollowerCountTotals(BaseModel):
    organic: int
    paid: int
    total: int

# Define the flattened Pydantic model
class FlattenedLinkedinFollowers(BaseModel):
    organizational_entity: str
    association_totals: FollowerCountTotals
    seniority_totals: FollowerCountTotals
    industry_totals: FollowerCountTotals
    function_totals: FollowerCountTotals
    staff_count_range_totals: FollowerCountTotals
    geo_country_totals: FollowerCountTotals
    geo_totals: FollowerCountTotals

def sum_counts(category_list):
    organic = sum(item["followerCounts"]["organicFollowerCount"] for item in category_list)
    paid = sum(item["followerCounts"]["paidFollowerCount"] for item in category_list)
    return {"organic": organic, "paid": paid, "total": organic + paid}


def process_follower_counts(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process the follower counts response and return a dictionary with the total counts.
    """
    element = data["elements"][0]
    # Flatten each category by summing totals
    assoc_totals = sum_counts(element.get("followerCountsByAssociationType", []))
    seniority_totals = sum_counts(element.get("followerCountsBySeniority", []))
    industry_totals = sum_counts(element.get("followerCountsByIndustry", []))
    function_totals = sum_counts(element.get("followerCountsByFunction", []))
    staff_totals = sum_counts(element.get("followerCountsByStaffCountRange", []))
    geo_country_totals = sum_counts(element.get("followerCountsByGeoCountry", []))
    geo_totals = sum_counts(element.get("followerCountsByGeo", []))

    # Create the flat Pydantic object
    flattened = FlattenedLinkedinFollowers(
        organizational_entity=element["organizationalEntity"],
        association_totals=FollowerCountTotals(**assoc_totals),
        seniority_totals=FollowerCountTotals(**seniority_totals),
        industry_totals=FollowerCountTotals(**industry_totals),
        function_totals=FollowerCountTotals(**function_totals),
        staff_count_range_totals=FollowerCountTotals(**staff_totals),
        geo_country_totals=FollowerCountTotals(**geo_country_totals),
        geo_totals=FollowerCountTotals(**geo_totals)
    )
    print(flattened.model_dump_json(indent=2))


# Organization role models
class OrganizationRole(BaseModel):
    """
    Represents a role assignment for a LinkedIn organization.
    
    This model captures the relationship between a member (roleAssignee) and an organization,
    including the specific role they have and the current state of that role assignment.
    
    Attributes:
        role: The type of role assigned (e.g., DIRECT_SPONSORED_CONTENT_POSTER, ADMINISTRATOR)
        organization: The URN of the organization
        role_assignee: The URN of the member who is assigned the role
        state: The current state of the role assignment (e.g., REQUESTED, APPROVED)
    """
    role: str
    organization: str
    role_assignee: str = Field(..., alias="roleAssignee")
    state: str

class OrganizationRolesResponse(BaseModel):
    """
    Response model for organization roles API.
    
    This model represents the response from the LinkedIn API when querying for
    organization roles. It contains a list of role assignments and pagination information.
    
    Attributes:
        elements: List of organization role assignments
        paging: Pagination information including count, start, and links
    """
    elements: List[OrganizationRole]
    # paging: Dict[str, Any]


class LinkedInClient:
    """
    High-level client for LinkedIn API interactions.
    
    This client wraps the official LinkedIn API client and provides additional
    functionality for managing posts, comments, analytics, and employee advocacy.
    """
    
    # Maximum posts per page in LinkedIn API
    MAX_POSTS_PER_PAGE = 100
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        access_token: Optional[str] = None,
        version: str = global_settings.LINKEDIN_API_VERSION,
        enable_caching: bool = True
    ):
        """
        Initialize the LinkedIn client.
        
        Args:
            client_id: LinkedIn application client ID
            client_secret: LinkedIn application client secret
            access_token: Optional OAuth access token
            version: API version string (defaults to v202302)
            enable_caching: Whether to enable result caching (defaults to True)
        """
        self.client = RestliClient(
            # client_id=client_id,
            # client_secret=client_secret,
            # access_token=access_token,
            # version=version
        )
        self.version = version
        self.access_token = access_token
        self.enable_caching = enable_caching
    
    async def set_access_token(self, access_token: str) -> None:
        """Update the client's access token."""
        self.client.access_token = access_token
        self.access_token = access_token

    async def get_organization_details(
        self,
        organization_id: str
    ) -> Dict[str, Any]:
        """
        Fetch detailed information about a LinkedIn organization.
        
        This method retrieves comprehensive details about an organization including
        name, description, website, industry, logo, and other profile information.
        
        Args:
            organization_id: LinkedIn organization ID or URN
            
        Returns:
            Dict[str, Any]: Organization details including profile information
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/organizations/organization-lookup-api
        """
        # Generate cache key
        organization_id = organization_id.split(":")[-1] if "urn:" in organization_id else organization_id
        cache_key = f"org_details_{organization_id}"
        
        # Try to get cached result first
        cached_data = await self.get_cached_result(cache_key)
        if cached_data:
            logger.info(f"Using cached organization details for {organization_id}")
            return cached_data
        
        try:
            # Ensure we have a clean organization ID
            org_urn = organization_id
            
            # Ensure the organization ID is properly URL-encoded for the path
            # encoded_org_urn = quote(org_urn, safe="")
            
            # Define fields to retrieve
            # fields = [
            #     "id", "name", "vanityName", "localizedName", "localizedDescription",
            #     "tagline", "logoV2", "websiteUrl", "industries", "locations",
            #     "organizationType", "status", "foundedOn", "specialties", "staffCount"
            # ]
            
            # Make API call to get organization details
            response = self.client.get(
                resource_path=f"/organizations/{organization_id}",
                # query_params={"fields": ",".join(fields)},
                version_string=self.version,
                access_token=self.access_token
            )
            response = response.entity
            
            # Cache the results
            await self.cache_result(cache_key, response)
            
            return response
            
        except Exception as e:
            logger.error(f"Error fetching organization details for {organization_id}: {str(e)}")
            raise
    
    async def get_member_profile(
        self,
        # member_id: str
    ) -> Dict[str, Any]:
        """
        Fetch detailed information about a LinkedIn member profile.
        
        This method retrieves comprehensive details about a member including
        name, headline, current position, location, and other profile information.
            
        Returns:
            Dict[str, Any]: Member profile details
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/shared/integrations/people/profile-api
        """
        # Generate cache key
        cache_key = f"member_profile_{self.access_token}"
        
        # Try to get cached result first
        cached_data = await self.get_cached_result(cache_key)
        if cached_data:
            logger.info(f"Using cached member profile for {cached_data}")
            return cached_data
        
        try:
            # Ensure we have a clean member ID
            # person_urn = member_id
            
            # Define fields to retrieve - these are the commonly available fields
            # Note: Some fields may require additional permissions
            # fields = [
            #     "id", "firstName", "lastName", "profilePicture", "headline",
            #     "vanityName", "publicProfileUrl", "industryName", "location",
            #     "positions", "educations"
            # ]
            
            # Make API call to get member profile
            response = self.client.get(
                resource_path=f"/me",
                # query_params={"fields": ",".join(fields)},
                version_string=self.version,
                access_token=self.access_token
            )
            response = response.entity
            
            # Cache the results
            await self.cache_result(cache_key, response)
            
            return response
            
        except Exception as e:
            logger.error(f"Error fetching member profile!: {str(e)}")
            raise
    
    async def cache_result(self, key: str, result: Any) -> None:
        """
        Cache a result using the key.
        
        Args:
            key: Unique identifier for the cached result
            result: Data to cache (can be a Pydantic model or other data)
            
        Note:
            This method will only cache results if caching is enabled.
            Pydantic models are properly serialized to JSON before caching.
        """
        if not self.enable_caching:
            return
            
        # Convert Pydantic models to dict for proper serialization
        if isinstance(result, BaseModel):
            result_dict = result.model_dump(by_alias=True)
            dump_to_json({key: result_dict})
        elif isinstance(result, list) and all(isinstance(item, BaseModel) for item in result):
            # Handle list of Pydantic models
            result_dict = [item.model_dump(by_alias=True) for item in result]
            dump_to_json({key: result_dict})
        elif isinstance(result, dict) and any(isinstance(value, BaseModel) for value in result.values()):
            # Handle dict with Pydantic model values
            result_dict = {k: v.model_dump(by_alias=True) if isinstance(v, BaseModel) else v 
                          for k, v in result.items()}
            dump_to_json({key: result_dict})
        else:
            # Handle regular data
            dump_to_json({key: result})
    
    async def get_cached_result(self, key: str) -> Optional[Any]:
        """
        Get a cached result using the key.
        
        Args:
            key: Unique identifier for the cached result
            
        Returns:
            Any: The cached result if found and caching is enabled, None otherwise.
                 Pydantic models are properly reconstructed from cached JSON.
        """
        if not self.enable_caching:
            return None
            
        try:
            cached_data = load_and_get_key(key)
            if cached_data is None:
                return None
                
            return cached_data
        except (FileNotFoundError, json.JSONDecodeError):
            return None
    
    async def get_posts(
        self,
        account_id: str,
        limit: Optional[int] = None,
        days: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[LinkedInPost]:
        """
        Fetch posts from a LinkedIn account with optional filtering by limit or date range.
        
        This method supports both individual and organization accounts. It will fetch posts
        in reverse chronological order (newest first). You can either specify a limit to get
        the N most recent posts, or provide a date range using either days or explicit start/end dates.
        
        The method will fetch posts up to MAX_POSTS_PER_PAGE (100) from LinkedIn's API. Date filtering
        is performed client-side after fetching the posts. If the earliest fetched post is newer
        than the requested start_date, the method will continue fetching more posts until either:
        1. We find posts older than start_date
        2. We hit the MAX_POSTS_PER_PAGE limit
        3. There are no more posts to fetch
        
        Args:
            account_id: LinkedInAccount model instance ID
            limit: Optional maximum number of posts to return (max 100)
            days: Optional number of days to look back (mutually exclusive with start_date/end_date)
            start_date: Optional start date for post range (requires end_date)
            end_date: Optional end date for post range (requires start_date)
            
        Returns:
            List[LinkedInPost]: List of LinkedIn posts matching the criteria
            
        Raises:
            ValueError: If both days and start_date/end_date are provided
            ValueError: If only one of start_date or end_date is provided
            ValueError: If limit is greater than MAX_POSTS_PER_PAGE
        """
        # Input validation
        if days and (start_date or end_date):
            raise ValueError("Cannot specify both 'days' and start_date/end_date range")
        if bool(start_date) != bool(end_date):
            raise ValueError("Must provide both start_date and end_date or neither")
            
        # Calculate date range if days is provided
        if days:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days)
            
        # Initialize variables for pagination
        posts: List[LinkedInPost] = []
        total_fetched = 0
        should_continue = True
        earliest_created_time = None
        # Prepare base query parameters
        author_urn = account_id  # f"urn:li:{'person' if account.account_type == 'individual' else 'organization'}:{account.linkedin_id}"
        params = {
            "author": author_urn,
            "count": min(limit, self.MAX_POSTS_PER_PAGE) if limit else self.MAX_POSTS_PER_PAGE,
            # "q": "author",
            "sortBy": "LAST_MODIFIED"
        }
        
        # Generate cache key based on account and query parameters
        cache_key = f"posts_{author_urn}_{limit}_{days}_{start_date}_{end_date}"
        
        # Try to get cached result first
        cached_data = await self.get_cached_result(cache_key)
        if cached_data:
            logger.info(f"Using cached posts data for account {author_urn}")
            # Convert cached data back to LinkedInPost objects
            for post_data in cached_data:
                post_data['created_at'] = datetime.fromisoformat(post_data['created_at'])
                # post_data['updated_at'] = datetime.fromisoformat(post_data['updated_at'])
            return [LinkedInPost(**post_data) for post_data in cached_data]
        
        try:
            while should_continue and total_fetched < self.MAX_POSTS_PER_PAGE:
                # Make API call to fetch posts
                response = self.client.finder(
                    resource_path="/posts",
                    finder_name="author",
                    query_params=params,
                    version_string=self.version,
                    access_token=self.access_token
                )
                response = {"elements": response.elements}
                print(response)
                
                # Process posts
                if "elements" in response and response.get("elements", []):
                    for post_data in response.get("elements", []):
                        created_time = datetime.fromtimestamp(
                            post_data["createdAt"] / 1000
                        )  # , tz=timezone.utc
                        if earliest_created_time is None or created_time < earliest_created_time:
                            earliest_created_time = created_time
                            
                        print("\n\n\n\n POST DATA: ", post_data, "\n\n")
                        print("\n\n\n\n JSON DUMP: ", json.dumps(post_data, indent=4), "\n\n\n\n")
                        post = LinkedInPost(
                            id=post_data["id"],
                            content_text=post_data.get("commentary", ""),
                            created_at=created_time,
                            account_id=author_urn,
                            # visibility=post_data.get("visibility", "PUBLIC"),
                            media_urls=[json.dumps(post_data.get("content", {}).get("media", []))],
                            is_published=post_data.get("lifecycleState", "PUBLISHED") == "PUBLISHED"
                        )
                        posts.append(post)
                        total_fetched += 1
                
                # Check if we've hit the limit
                if limit and total_fetched >= limit:
                    should_continue = False
                    break
                
                # Check date range if specified
                if start_date and created_time < start_date:
                    should_continue = False
                    break
                if end_date and created_time > end_date:
                    continue
                
                # Check for next page
                if should_continue and "paging" in response and "next" in response["paging"]:
                    params["start"] = response["paging"]["next"]["start"]
                else:
                    break
                    
            # Apply limit if specified
            # if limit and len(posts) > limit:
            #     posts = posts[:limit]
            
            # Cache the results - convert LinkedInPost objects to dicts for caching
            # Convert LinkedInPost objects to dicts for caching
            # We need to convert datetime objects to string timestamps for JSON serialization
            posts_dict_data = []
            for post in posts:
                post_dict = {
                    'id': post.id,
                    'content_text': post.content_text,
                    'created_at': post.created_at,
                    'account_id': post.account_id,
                    # 'visibility': post.visibility,
                    'media_urls': post.media_urls,
                    'is_published': post.is_published,
                }
                # Convert created_time datetime to string timestamp format
                if post_dict.get('created_at'):
                    post_dict['created_at'] = post_dict['created_at'].isoformat()
                    # post_dict['updated_at'] = post_dict['updated_at'].isoformat()
                posts_dict_data.append(post_dict)
            await self.cache_result(cache_key, posts_dict_data)
                
            return posts
            
        except Exception as e:
            logger.error(f"Error fetching posts for account {author_urn}: {str(e)}")
            raise
    
    # Post Management Methods
    
    async def create_post(
        self,
        account_urn: str,
        content: str,
        feed_distribution: str = "MAIN_FEED",  # "NONE", "GROUP_FEED"
        # scheduled_time: Optional[datetime] = None,
        # visibility: str = "PUBLIC"
    ) -> str:
        """
        Create a new post on LinkedIn.
        
        Args:
            account: LinkedInAccount model instance
            content: Post text content
            media_urls: Optional list of media URLs to attach
            scheduled_time: Optional timestamp to schedule the post
            visibility: Post visibility ("PUBLIC", "CONNECTIONS", etc.)
            
        Returns:
            str: LinkedIn post ID
        """
        # Prepare post content

        post_request = {
                "author": account_urn,
                "lifecycleState": "PUBLISHED",
                "visibility": "PUBLIC",
                "commentary": content,
                "distribution": {
                    "feedDistribution": feed_distribution,
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
            # "isReshareDisabledByAuthor": False
            }
        
        # Add media if provided
        # if media_urls:
        #     post_request["content"] = {
        #         "media": [{"url": url} for url in media_urls]
        #     }
        
        # Schedule post if timestamp provided
        # if scheduled_time:
        #     post_request["scheduledTime"] = int(scheduled_time.timestamp() * 1000)
        #     post_request["lifecycleState"] = "SCHEDULED"
        
        # Make API call
        response = self.client.create(
            resource_path="/posts",
            entity=post_request,
            version_string=self.version,
            access_token=self.access_token
        ) # TODO: check entity ID is URN or not!!
        print(response.entity, response.entity_id)
        return response.entity_id

    async def create_reshare(
        self,
        account_urn: str,
        reshare_commentary: str,
        post_urn: str,
        feed_distribution: str = "MAIN_FEED",  # "NONE", "GROUP_FEED"
        # scheduled_time: Optional[datetime] = None,
        # visibility: str = "PUBLIC"
    ) -> str:
        """
        Create a new post on LinkedIn.
        
        Args:
            account: LinkedInAccount model instance
            content: Post text content
            media_urls: Optional list of media URLs to attach
            scheduled_time: Optional timestamp to schedule the post
            visibility: Post visibility ("PUBLIC", "CONNECTIONS", etc.)
            
        Returns:
            str: LinkedIn post ID
        """
        # Prepare post content

        reshare_post_request = {
            "author": account_urn,
            "commentary": reshare_commentary,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": feed_distribution,
                "targetEntities": [],
                "thirdPartyDistributionChannels": []
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
            "reshareContext": {
                "parent": post_urn
            }
        }
        
        
        # Add media if provided
        # if media_urls:
        #     post_request["content"] = {
        #         "media": [{"url": url} for url in media_urls]
        #     }
        
        # Schedule post if timestamp provided
        # if scheduled_time:
        #     post_request["scheduledTime"] = int(scheduled_time.timestamp() * 1000)
        #     post_request["lifecycleState"] = "SCHEDULED"
        
        # Make API call
        response = self.client.create(
            resource_path="/posts",
            entity=reshare_post_request,
            version_string=self.version,
            access_token=self.access_token
        ) # TODO: check entity ID is URN or not!!
        print(response.entity, response.entity_id)
        return response.entity_id
    
    async def delete_post(self, post_urn: str) -> bool:
        """
        Delete a LinkedIn post.
        
        This method deletes a post from LinkedIn using the post's ID. The post must be
        owned by the authenticated user or an organization that the user has permission to manage.
        
        Args:
            post_urn: LinkedIn post ID (UGC post URN or share URN)
            
        Returns:
            bool: True if the post was successfully deleted, False otherwise
            
        Raises:
            Exception: If there is an error deleting the post
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/posts-api
        """
        # Generate cache key for potential cleanup
        # cache_key = f"post_{post_id}"
        encoded_urn = quote(post_urn, safe="")
        try:
            # Ensure we have a clean post ID (remove URN prefix if present)
            
            # Make API call to delete the post
            response = self.client.delete(
                resource_path=f"/posts/{encoded_urn}",
                version_string=self.version,
                access_token=self.access_token
            )
            
            # If we reach here without exception, deletion was successful
            logger.info(f"Successfully deleted LinkedIn post: {post_urn}")
            
            # Clean up any cached data for this post
            # if self.enable_caching:
            #     try:
            #         # Remove from cache if it exists
            #         await self.cache_result(cache_key, None)
            #     except Exception as cache_error:
            #         logger.warning(f"Failed to clean up cache for deleted post {post_id}: {str(cache_error)}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting LinkedIn post {post_urn}: {str(e)}")
            raise

    async def get_member_organization_roles(self) -> OrganizationRolesResponse:
        """
        Fetch all organizations and member roles for the authenticated member.

        This method retrieves the roles assigned to the authenticated member within
        various organizations using the LinkedIn API's organization access control endpoint.

        Returns:
            OrganizationRolesResponse: A response object containing organization role assignments.

        Raises:
            Exception: If there is an error fetching the organization roles.
        """
        # Generate cache key
        cache_key = f"member_organization_roles_{self.access_token}"

        # Try to get cached result first
        cached_data = await self.get_cached_result(cache_key)
        if cached_data:
            logger.info("Using cached organization roles data for the authenticated member")
            # Reconstruct OrganizationRolesResponse from cached data
            return OrganizationRolesResponse(**cached_data)

        try:
            # Make API call to fetch organization roles
            response = self.client.finder(
                resource_path="/organizationAcls",
                finder_name="roleAssignee",
                # query_params={"q": "roleAssignee"},
                version_string=self.version,
                access_token=self.access_token
            )
            response = {"elements": response.elements}
            # Parse into OrganizationRolesResponse
            roles_response = OrganizationRolesResponse(**response)
            
            # Cache the results
            await self.cache_result(cache_key, response)

            return roles_response

        except Exception as e:
            logger.error(f"Error fetching organization roles for the authenticated member: {str(e)}")
            raise
    
    async def get_post_social_actions(
        self,
        post_id: str
    ) -> SocialActionsSummary:
        """
        Fetch social actions (likes, comments) for a specific post.
        
        Args:
            post_id: LinkedIn post URN (already formatted as URN)
            
        Returns:
            SocialActionsSummary: Summary of social actions on the post
        """
        # Generate cache key
        cache_key = f"post_social_actions_{post_id}"
        
        # Try to get cached result first
        cached_data = await self.get_cached_result(cache_key)
        if cached_data:
            logger.info(f"Using cached social actions data for post {post_id}")
            return SocialActionsSummary(**cached_data)
            
        # Make API call if no cached data
        encoded_urn = quote(post_id, safe="")
        
        try:
            response = self.client.get(
                resource_path=f"/socialActions/{encoded_urn}",
                version_string=self.version,
                access_token=self.access_token
            )
            response = response.entity
            
            # Add target field if not present
            if "target" not in response:
                response["target"] = post_id
            # print(json.dumps(response, indent=4))    
            # Parse response with Pydantic model
            social_actions = SocialActionsSummary(**response)
            
            # Cache the results
            await self.cache_result(cache_key, response)
            
            return social_actions
            
        except Exception as e:
            logger.error(f"Error fetching social actions for post {post_id}: {str(e)}")
            raise
    
    async def batch_get_post_social_actions(
        self,
        post_ids: List[str]
    ) -> Dict[str, SocialActionsSummary]:
        """
        Batch fetch social actions for multiple posts.
        
        Args:
            post_ids: List of LinkedIn post URNs
            
        Returns:
            Dict[str, SocialActionsSummary]: Dictionary mapping post URNs to their social actions summaries
        """
        # Generate cache key
        post_ids_str = "_".join(list(sorted(post_ids)))
        cache_key = f"batch_post_social_actions_{post_ids_str}"
        
        # Try to get cached result first
        cached_data = await self.get_cached_result(cache_key)
        if cached_data:
            logger.info(f"Using cached batch social actions data for posts")
            # Reconstruct SocialActionsSummary objects from cached data
            return {
                post_id: SocialActionsSummary(**data) 
                for post_id, data in cached_data.items()
            }
            
        # Make API call if no cached data
        try:
            # Prepare batch request with Rest.li batch_get method
            # Format the URNs for batch_get request
            encoded_ids = [quote(post_id, safe="") for post_id in post_ids]
            ids_param = f"List({','.join(encoded_ids)})"
            
            response = self.client.batch_get(
                resource_path="/socialActions",
                ids=post_ids,  # ids_param,  # TODO: check! potentially incorrect escape
                version_string=self.version,
                access_token=self.access_token
            )
            response = {"results": response.results}
            # Parse response with Pydantic models
            result = {}
            for post_id, data in response.get("results", {}).items():
                # Add target field if not present
                if "target" not in data:
                    data["target"] = post_id
                result[post_id] = SocialActionsSummary(**data)
            
            # Cache the results - convert SocialActionsSummary objects to dicts
            result_dict = {post_id: model.model_dump(by_alias=True) for post_id, model in result.items()}
            await self.cache_result(cache_key, result_dict)
            
            return result
            
        except Exception as e:
            logger.error(f"Error batch fetching social actions: {str(e)}")
            raise
    
    # Organization Share Statistics Methods
    
    def _is_ugc_post(self, post_id: str) -> bool:
        """
        Determine if a post URN is a UGC post or a share.
        
        Args:
            post_id: LinkedIn post URN
            
        Returns:
            bool: True if the URN is a UGC post, False if it's a share
        """
        return "ugcPost" in post_id
    
    async def get_organization_share_statistics_for_posts(
        self,
        organization_id: str,
        post_ids: List[str]
    ) -> ShareStatisticsResponse:
        """
        Fetch statistics for specific organization posts.
        
        This method detects if the provided URNs are UGC posts or shares and
        uses the appropriate batch API to fetch statistics.
        
        Args:
            organization_id: LinkedIn organization ID
            post_ids: List of LinkedIn post URNs
            
        Returns:
            ShareStatisticsResponse: Statistics for the specified posts
        """
        # Generate cache key
        post_ids_str = "_".join(list(sorted(post_ids)))
        cache_key = f"org_post_stats_{organization_id}_{post_ids_str}"
        
        # Try to get cached result first
        cached_data = await self.get_cached_result(cache_key)
        if cached_data:
            logger.info(f"Using cached organization post statistics")
            return ShareStatisticsResponse(**cached_data)
        
        # Separate UGC posts and shares
        # Assume post IDs are URNs!
        ugc_post_ids = [post_id for post_id in post_ids if self._is_ugc_post(post_id)]
        share_ids = [post_id for post_id in post_ids if not self._is_ugc_post(post_id)]
        
        try:
            # Make API call using Rest.li finder method
            org_urn = organization_id  # f"urn:li:organization:{organization_id}"
            # encoded_org_urn = quote(org_urn, safe="")
            
            # Initialize query parameters
            query_params = {
                # "q": "organizationalEntity",
                "organizationalEntity": org_urn
            }
            
            # Add share URNs if any
            if share_ids:
                encoded_share_urns = [share_id for share_id in share_ids]  # [quote(share_id, safe="") for share_id in share_ids]
                query_params["shares"] = f"List({','.join(encoded_share_urns)})"
            
            # Add UGC post URNs if any
            if ugc_post_ids:
                for i, ugc_post_id in enumerate(ugc_post_ids):
                    query_params[f"ugcPosts[{i}]"] = ugc_post_id  # quote(ugc_post_id, safe="")
            
            response = self.client.finder(
                resource_path="/organizationalEntityShareStatistics",
                finder_name="organizationalEntity",
                query_params=query_params,
                version_string=self.version,
                access_token=self.access_token
            )
            response = {"elements": response.elements}
            
            # Parse response with Pydantic model
            stats_response = ShareStatisticsResponse(**response)
            
            # Cache the results
            await self.cache_result(cache_key, response)
            
            return stats_response
            
        except Exception as e:
            logger.error(f"Error fetching organization post statistics: {str(e)}")
            raise 
    
    # Organization Page Methods
    
    async def get_organization_lifetime_share_statistics(
        self, 
        organization_id: str
    ) -> ShareStatisticsResponse:
        """
        Fetch lifetime (aggregated) share statistics for an organization.
        
        This method retrieves all-time aggregated statistics for an organization's shares.
        The statistics include metrics such as impressions, clicks, likes, comments, and shares.
        
        Args:
            organization_id: LinkedIn organization ID
            
        Returns:
            ShareStatisticsResponse: Lifetime share statistics for the organization
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/share-statistics?view=li-lms-2025-02&tabs=http
        """
        # Generate cache key
        cache_key = f"org_lifetime_share_stats_{organization_id}"
        
        # Try to get cached result first
        cached_data = await self.get_cached_result(cache_key)
        if cached_data:
            logger.info(f"Using cached lifetime share statistics for organization {organization_id}")
            return ShareStatisticsResponse(**cached_data)
        
        try:
            # Make API call using Rest.li finder method
            org_urn = organization_id  # f"urn:li:organization:{organization_id}"
            # encoded_org_urn = quote(org_urn, safe="")
            
            response = self.client.finder(
                resource_path="/organizationalEntityShareStatistics",
                finder_name="organizationalEntity",
                query_params={
                    # "q": "organizationalEntity",
                    "organizationalEntity": org_urn
                },
                version_string=self.version,
                access_token=self.access_token
            )
            response = {"elements": response.elements}
            
            # Parse response with Pydantic model
            stats_response = ShareStatisticsResponse(**response)
            
            # Cache the results
            await self.cache_result(cache_key, response)
            
            return stats_response
            
        except Exception as e:
            logger.error(f"Error fetching lifetime share statistics for organization {organization_id}: {str(e)}")
            raise
    
    async def get_organization_timebound_share_statistics(
        self,
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAY"
    ) -> ShareStatisticsResponse:
        """
        Fetch time-bound share statistics for an organization.
        
        This method retrieves share statistics for an organization within a specific date range,
        aggregated by the specified granularity (DAY or MONTH).
        
        Args:
            organization_id: LinkedIn organization ID
            start_date: Start date for the time range
            end_date: End date for the time range
            granularity: Time granularity for aggregation ("DAY" or "MONTH")
            
        Returns:
            ShareStatisticsResponse: Time-bound share statistics for the organization
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/share-statistics?view=li-lms-2025-02&tabs=http
        """
        # Generate cache key
        cache_key = f"org_timebound_share_stats_{organization_id}_{start_date.isoformat()}_{end_date.isoformat()}_{granularity}"
        
        # Try to get cached result first
        cached_data = await self.get_cached_result(cache_key)
        if cached_data:
            logger.info(f"Using cached time-bound share statistics for organization {organization_id}")
            return ShareStatisticsResponse(**cached_data)
        
        try:
            # Make API call using Rest.li finder method
            org_urn = organization_id  # f"urn:li:organization:{organization_id}"
            # encoded_org_urn = quote(org_urn, safe="")
            
            # Prepare timeIntervals parameter
            time_intervals = {
                "timeRange": {
                    "start": int(start_date.timestamp() * 1000),
                    "end": int(end_date.timestamp() * 1000)
                },
                "timeGranularityType": granularity
            }
            
            response = self.client.finder(
                resource_path="/organizationalEntityShareStatistics",
                finder_name="organizationalEntity",
                query_params={
                    # "q": "organizationalEntity",
                    "organizationalEntity": org_urn,
                    "timeIntervals": time_intervals
                },
                version_string=self.version,
                access_token=self.access_token
            )
            response = {"elements": response.elements}
            
            # Parse response with Pydantic model
            stats_response = ShareStatisticsResponse(**response)
            
            # Cache the results
            await self.cache_result(cache_key, response)
            
            return stats_response
            
        except Exception as e:
            logger.error(f"Error fetching time-bound share statistics for organization {organization_id}: {str(e)}")
            raise

    # Organization Follower Statistics Methods
    
    async def get_organization_follower_statistics(
        self,
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAY"
    ) -> FollowerStatisticsResponse:
        """
        Fetch follower statistics for an organization.
        
        This method retrieves follower statistics for an organization within a specific date range,
        aggregated by the specified granularity (DAY or MONTH).
        
        Args:
            organization_id: LinkedIn organization ID
            start_date: Start date for the time range
            end_date: End date for the time range
            granularity: Time granularity for aggregation ("DAY" or "MONTH")
            
        Returns:
            FollowerStatisticsResponse: Follower statistics for the organization
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/follower-statistics?view=li-lms-2025-02&tabs=http
        """
        # Generate cache key
        cache_key = f"org_follower_stats_{organization_id}_{start_date.isoformat()}_{end_date.isoformat()}_{granularity}"
        
        # Try to get cached result first
        cached_data = await self.get_cached_result(cache_key)
        if cached_data:
            logger.info(f"Using cached follower statistics for organization {organization_id}")
            return FollowerStatisticsResponse(**cached_data)
        
        try:
            org_urn = organization_id  # f"urn:li:organization:{organization_id}"
            # encoded_org_urn = quote(org_urn, safe="")
            # Prepare time intervals parameter
            time_intervals = {
                "timeGranularityType": granularity,
                "timeRange": {
                    "start": int(start_date.timestamp() * 1000),
                    "end": int(end_date.timestamp() * 1000)
                }
            }
            
            # response = self.client.finder(
            #     resource_path=f"/organizations/{organization_id}/followingStatistics",
            #     finder_name="followingStatistics",
            #     query_params={
            #         "q": "followingStatistics",
            #         "timeIntervals": time_intervals
            #     },
            #     version_string=self.version,
            #     access_token=self.access_token
            # )
            response = self.client.finder(
                resource_path=f"/organizationalEntityFollowerStatistics",
                finder_name="organizationalEntity",
                query_params={  # TODO: check!!! manually corrected version
                    # "q": "followingStatistics",  # finder_name added to query params automatically!  // organizationalEntity
                    "organizationalEntity": org_urn,
                    "timeIntervals": time_intervals
                },
                version_string=self.version,
                access_token=self.access_token
            )
            response = {"elements": response.elements}
            
            # Parse response with Pydantic model
            follower_stats = FollowerStatisticsResponse(**response)
            
            # Cache the results
            await self.cache_result(cache_key, response)
            
            return follower_stats
            
        except Exception as e:
            logger.error(f"Error fetching follower statistics for organization {organization_id}: {str(e)}")
            raise
    
    async def get_organization_follower_count(
        self,
        organization_id: str
    ) -> int:
        """
        Fetch the current follower count for an organization.
        
        This method retrieves the current total follower count for an organization.
        
        Args:
            organization_id: LinkedIn organization ID
            
        Returns:
            int: Current follower count
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/follower-statistics?view=li-lms-2025-02&tabs=http
        """
        # Generate cache key
        cache_key = f"org_follower_count_{organization_id}"
        
        # Try to get cached result first
        cached_data = await self.get_cached_result(cache_key)
        if cached_data:
            logger.info(f"Using cached follower count for organization {organization_id}")
            return cached_data
        
        try:
            org_urn = organization_id  # f"urn:li:organization:{organization_id}"
            # encoded_org_urn = quote(org_urn, safe="")
            
            response = self.client.finder(
                resource_path=f"/organizationalEntityFollowerStatistics",
                finder_name="organizationalEntity",
                query_params={  # TODO: check!!! manually corrected version
                    # "q": "followingStatistics",  # finder_name added to query params automatically!  // organizationalEntity
                    "organizationalEntity": org_urn,
                },
                version_string=self.version,
                access_token=self.access_token
            )
            response = {"elements": response.elements}
            flattened_follower_counts = process_follower_counts(response)
            
            # Extract follower count from the response
            # follower_count = 0
            # if "elements" in response and len(response["elements"]) > 0:
            #     if "followerCounts" in response["elements"][0]:
            #         follower_count = response["elements"][0]["followerCounts"].get("end", 0)
            
            # Cache the results
            await self.cache_result(cache_key, flattened_follower_counts)
            
            return flattened_follower_counts
            
        except Exception as e:
            logger.error(f"Error fetching follower count for organization {organization_id}: {str(e)}")
            raise

    # Comment & Reaction Methods
    
    # async def create_comment(
    #     self,
    #     post_id: str,
    #     content: str,
    #     author_id: str,
    #     parent_comment_id: Optional[str] = None
    # ) -> Dict[str, Any]:
    #     """
    #     Create a comment on a post or reply to another comment.
        
    #     Args:
    #         post_id: LinkedIn post ID
    #         content: Comment text
    #         author_id: LinkedIn member ID of commenter
    #         parent_comment_id: Optional ID of parent comment for replies
            
    #     Returns:
    #         Dict[str, Any]: Created comment data
    #     """
    #     comment_request = {
    #         "object": f"urn:li:post:{post_id}",
    #         "message": {
    #             "text": content
    #         }
    #     }
        
    #     if parent_comment_id:
    #         comment_request["object"] = f"urn:li:comment:{parent_comment_id}"
        
    #     return self.client.social_actions.create_comment(comment_request)
    
    # async def add_reaction(
    #     self,
    #     post_id: str,
    #     actor_id: str,
    #     reaction_type: str = "LIKE"
    # ) -> Dict[str, Any]:
    #     """
    #     Add a reaction to a post.
        
    #     Args:
    #         post_id: LinkedIn post ID
    #         actor_id: LinkedIn member ID of reactor
    #         reaction_type: Type of reaction (LIKE, CELEBRATE, etc.)
            
    #     Returns:
    #         Dict[str, Any]: Created reaction data
    #     """
    #     return self.client.social_actions.create_reaction(
    #         f"urn:li:post:{post_id}",
    #         reaction_type
    #     )
    
    # # Employee Advocacy Methods
    
    # async def share_organization_post(
    #     self,
    #     post_id: str,
    #     employee_id: str,
    #     custom_message: Optional[str] = None
    # ) -> Dict[str, Any]:
    #     """
    #     Share an organization's post through an employee's account.
        
    #     Args:
    #         post_id: LinkedIn post ID to share
    #         employee_id: LinkedIn member ID of sharing employee
    #         custom_message: Optional custom message to add with share
            
    #     Returns:
    #         Dict[str, Any]: Created share data
    #     """
    #     share_content = {
    #         "reshareContext": {
    #             "parent": f"urn:li:post:{post_id}",
    #             "message": custom_message if custom_message else ""
    #         }
    #     }
        
    #     return self.client.posts.create(share_content)
    
    # Social Actions Methods for Individual Posts
    

    # async def get_individual_share_statistics(
    #     self,
    #     person_id: str,
    #     post_ids: List[str]
    # ) -> Dict[str, SocialActionsSummary]:
    #     """
    #     Fetch social actions for posts by an individual member.
        
    #     This method retrieves social actions (likes, comments) for posts authored by an individual.
        
    #     Args:
    #         person_id: LinkedIn person ID
    #         post_ids: List of LinkedIn post URNs
            
    #     Returns:
    #         Dict[str, SocialActionsSummary]: Dictionary mapping post URNs to their social actions summaries
            
    #     Reference:
    #         https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/network-update-social-actions?view=li-lms-2025-02&tabs=http
    #     """
    #     # For individuals, we use the batch_get_post_social_actions method
    #     # since LinkedIn doesn't provide an aggregated share statistics API for individuals
    #     return await self.batch_get_post_social_actions(post_ids)
    
    # async def get_individual_follower_count(
    #     self,
    #     person_id: str
    # ) -> int:
    #     """
    #     Fetch the current follower count for an individual member.
        
    #     This method retrieves the current total follower count for an individual member profile.
    #     Note: This requires special API permissions that are not available to all developers.
        
    #     Args:
    #         person_id: LinkedIn person ID
            
    #     Returns:
    #         int: Current follower count or 0 if the API is not accessible
            
    #     Note:
    #         Access to individual follower counts is restricted and may require special permissions.
    #     """
    #     logger.warning("Individual follower count API requires special permissions and may not be accessible.")
        
    #     # Generate cache key
    #     cache_key = f"individual_follower_count_{person_id}"
        
    #     # Try to get cached result first
    #     cached_data = await self.get_cached_result(cache_key)
    #     if cached_data:
    #         logger.info(f"Using cached follower count for individual {person_id}")
    #         return cached_data
        
    #     try:
    #         # Attempt to fetch individual profile to get follower count
    #         response = self.client.get(
    #             resource_path=f"/people/{person_id}",
    #             query_params={
    #                 "fields": "numFollowers"
    #             },
    #             version_string=self.version,
    #             access_token=self.access_token
    #         )
            
    #         # Extract follower count from the response (if available)
    #         follower_count = response.get("numFollowers", 0)
            
    #         # Cache the results
    #         await self.cache_result(cache_key, follower_count)
            
    #         return follower_count
            
    #     except Exception as e:
    #         logger.error(f"Error fetching follower count for individual {person_id}: {str(e)}")
    #         # Return 0 instead of raising an exception since this API may not be accessible
    #         return 0
