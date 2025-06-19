"""
LinkedIn API client implementation using Rest.li framework.

This module provides a high-level interface for interacting with LinkedIn's API
for both individual members and organization pages. It handles authentication,
post management, analytics, and employee advocacy features.
"""

from typing import Dict, List, Optional, Union, Any, Callable, Tuple
from datetime import datetime, timedelta, timezone
import json
import logging
from urllib.parse import urlencode, quote
import re
import asyncio

import aiohttp
from linkedin_api.clients.restli.client import RestliClient
import linkedin_api.clients.restli.utils.encoder as encoder
from linkedin_api.common.constants import RESTLI_METHODS
from linkedin_api.clients.restli.response_formatter import (
    UpdateResponseFormatter,
)

from pydantic import BaseModel, Field

# from linkedin_integration.caching import dump_to_json, load_and_get_key

# from linkedin_integration.models import (
#     LinkedInAccount, LinkedInPost, 
#     LinkedInComment,
#     LinkedInReaction, LinkedInAnalytics, LinkedInPostAnalytics
# )
from kiwi_app.settings import settings

logger = logging.getLogger(__name__)

from pydantic.config import ConfigDict

class ResponseBaseModel(BaseModel):
    model_config = ConfigDict(extra='allow')

    @classmethod
    def parse_response(cls, data: dict):
        return cls.model_construct(**data)

# Pydantic models for social actions responses


class CommentsSummary(ResponseBaseModel):
    selected_comments: List[Any] = Field([], alias="selectedComments")
    total_first_level_comments: int = Field(0, alias="totalFirstLevelComments")
    comments_state: str = Field("OPEN", alias="commentsState")
    aggregated_total_comments: int = Field(0, alias="aggregatedTotalComments")


# Pydantic models for likes responses
class CreatedModified(ResponseBaseModel):
    """Model for created/lastModified timestamps in LinkedIn API responses."""
    actor: str
    impersonator: Optional[str] = None
    time: int

class Like(ResponseBaseModel):
    """
    Represents a like on a LinkedIn post, share, or comment.
    
    Attributes:
        actor: URN of the entity that liked the content (person or organization)
        agent: URN of the person who performed the action (may differ from actor for organization posts)
        last_modified: Information about when the like was last modified
        id: Unique identifier for the like
        created: Information about when the like was created
        object: URN of the content that was liked
    """
    actor: str
    agent: Optional[str] = None
    last_modified: CreatedModified = Field(..., alias="lastModified")
    id: str
    created: CreatedModified
    object: str

class LikesResponse(ResponseBaseModel):
    """
    Response model for fetching likes on LinkedIn content.
    
    Contains pagination information and a list of likes.
    """
    paging: Dict[str, Any]
    elements: List[Like]

# Pydantic models for comments responses
class MessageAttribute(ResponseBaseModel):
    """Represents attributes in a comment message (mentions, formatting, etc.)."""
    start: Optional[int] = None
    length: Optional[int] = None
    value: Optional[Dict[str, Any]] = None

class CommentMessage(ResponseBaseModel):
    """
    Represents the message content of a comment.
    
    Attributes:
        attributes: List of message attributes (mentions, formatting, etc.)
        text: The actual text content of the comment
    """
    attributes: List[MessageAttribute] = []
    text: str

class LikesSummary(ResponseBaseModel):
    """
    Represents a summary of likes on a LinkedIn comment or post.
    
    This model captures aggregated information about likes including total counts,
    selected likes for preview, and whether the current user has liked the content.
    
    Attributes:
        selected_likes: List of URNs for a sample of likes (used for preview)
        aggregated_total_likes: Total number of likes across all types
        liked_by_current_user: Whether the authenticated user has liked this content
        total_likes: Total count of likes on this content
    """
    selected_likes: List[str] = Field(default_factory=list, alias="selectedLikes")
    aggregated_total_likes: int = Field(0, alias="aggregatedTotalLikes")
    liked_by_current_user: bool = Field(False, alias="likedByCurrentUser")
    total_likes: int = Field(0, alias="totalLikes")


class SocialActionsSummary(ResponseBaseModel):
    likes_summary: Optional[LikesSummary] = Field(None, alias="likesSummary")
    comments_summary: Optional[CommentsSummary] = Field(None, alias="commentsSummary")
    target: Optional[str] = None

class Comment(ResponseBaseModel):
    """
    Represents a comment on a LinkedIn post, share, or another comment.
    
    Attributes:
        actor: URN of the entity that made the comment (person or organization)
        comments_summary: Summary of nested comments if this is a top-level comment
        agent: URN of the person who performed the action (may differ from actor for organization posts)
        comment_urn: Full URN identifier for this comment
        created: Information about when the comment was created
        id: Unique identifier for the comment
        last_modified: Information about when the comment was last modified
        message: The comment message content
        likes_summary: Summary of likes on this comment including counts and preview
        object: URN of the content that was commented on
    """
    actor: str
    comments_summary: Optional[CommentsSummary] = Field(None, alias="commentsSummary")
    agent: Optional[str] = None
    comment_urn: str = Field(..., alias="commentUrn")
    created: CreatedModified
    id: str
    last_modified: CreatedModified = Field(..., alias="lastModified")
    message: CommentMessage
    likes_summary: Optional[LikesSummary] = Field(None, alias="likesSummary")
    object: str



class CommentsResponse(ResponseBaseModel):
    """
    Response model for fetching comments on LinkedIn content.
    
    Contains pagination information and a list of comments.
    """
    paging: Dict[str, Any]
    elements: List[Comment]

# Pydantic models for reactions responses
class Reaction(ResponseBaseModel):
    """
    Represents a reaction on a LinkedIn post, share, or other content.
    
    Attributes:
        id: Unique identifier for the reaction (composite URN)
        last_modified: Information about when the reaction was last modified
        reaction_type: Type of reaction (LIKE, CELEBRATE, SUPPORT, LOVE, INSIGHTFUL, FUNNY)
        created: Information about when the reaction was created
        root: URN of the content that was reacted to
    """
    id: str
    last_modified: CreatedModified = Field(..., alias="lastModified")
    reaction_type: str = Field(..., alias="reactionType")
    created: CreatedModified
    root: str

class ReactionsResponse(ResponseBaseModel):
    """
    Response model for fetching reactions on LinkedIn content.
    
    Contains pagination information and a list of reactions.
    """
    paging: Dict[str, Any]
    elements: List[Reaction]

#### Social Metadata objects ####
class ReactionSummary(ResponseBaseModel):
    """
    Represents a summary of reactions of a specific type.
    
    Attributes:
        reaction_type: Type of reaction (e.g., EMPATHY, LIKE, CELEBRATE)
        count: Number of reactions of this type
    """
    reaction_type: str = Field(..., alias="reactionType")
    count: int

class CommentSummary(ResponseBaseModel):
    """
    Represents a summary of comments on content.
    
    Attributes:
        count: Total number of comments
        top_level_count: Number of top-level comments
    """
    count: int
    top_level_count: int = Field(..., alias="topLevelCount")

class SocialMetadata(ResponseBaseModel):
    """
    Represents social metadata for LinkedIn content.
    
    This model captures aggregated information about reactions and comments
    on a piece of content (post, share, or comment).
    
    Attributes:
        reaction_summaries: Dictionary mapping reaction types to their summaries
        comments_state: Current state of comments (e.g., "OPEN", "CLOSED")
        comment_summary: Summary of comments including counts
        entity: URN of the content this metadata is for
    """
    reaction_summaries: Dict[str, ReactionSummary] = Field(..., alias="reactionSummaries")
    comments_state: str = Field(..., alias="commentsState")
    comment_summary: CommentSummary = Field(..., alias="commentSummary")
    entity: str

class SocialMetadataResponse(ResponseBaseModel):
    """
    Response model for batch fetching social metadata.
    
    This model represents the response from the LinkedIn API when batch querying
    social metadata for multiple entities. It contains a dictionary mapping entity
    URNs to their corresponding social metadata.
    
    Attributes:
        results: Dictionary mapping entity URNs to their social metadata
    """
    results: Dict[str, SocialMetadata]


# Add the new request schema after the existing Pydantic models (around line 280, after ShareStatisticsResponse)

class TimeRange(ResponseBaseModel):
    """
    Represents a time range for statistics queries.
    
    Attributes:
        start: Exclusive starting timestamp in milliseconds since epoch
               Queries from beginning of time when not set
        end: Inclusive ending timestamp in milliseconds since epoch  
             Queries until current time when not set
    """
    start: Optional[int] = None
    end: Optional[int] = None

class TimeIntervals(ResponseBaseModel):
    """
    Represents time intervals configuration for statistics queries.
    
    Attributes:
        time_granularity_type: Granularity of the statistics (DAY or MONTH)
        time_range: The time range for the query
    """
    time_granularity_type: Optional[str]
    time_range: TimeRange
    
    def model_post_init(self, __context) -> None:
        """Validate time_granularity_type values after initialization."""
        if self.time_granularity_type and self.time_granularity_type not in ["DAY", "MONTH"]:
            raise ValueError("time_granularity_type must be either 'DAY' or 'MONTH'")

class ShareStatisticsRequest(ResponseBaseModel):
    """
    Comprehensive request schema for LinkedIn share statistics API.
    
    This schema supports all share statistics scenarios:
    - Lifetime statistics (no timeIntervals)
    - Time-bound statistics (with timeIntervals)
    - Statistics for specific posts (shares and/or ugcPosts)
    - Combination of time-bound and specific posts
    
    Attributes:
        organizational_entity: Organization identifier URN (required)
        time_intervals: Optional time restriction configuration
        shares: Optional list of share URNs for specific share statistics
        ugc_posts: Optional list of UGC post URNs for specific post statistics
    """
    organizational_entity: str
    time_intervals: Optional[TimeIntervals] = Field(None)
    shares: Optional[List[str]] = None
    ugc_posts: Optional[List[str]] = Field(None)
    
    def model_post_init(self, __context) -> None:
        """Validate the request after initialization."""
        # Validate organizational entity format
        if not (self.organizational_entity.startswith("urn:li:organization:") or 
                self.organizational_entity.startswith("urn:li:organizationBrand:")):
            raise ValueError(
                "organizational_entity must be of format 'urn:li:organization:{id}' "
                "or 'urn:li:organizationBrand:{id}'"
            )
        
        # Validate that at least shares or ugc_posts is provided when specific posts are requested
        if (self.shares is not None or self.ugc_posts is not None):
            if not self.shares and not self.ugc_posts:
                raise ValueError(
                    "When specifying shares or ugc_posts, at least one must contain values"
                )
    
    @classmethod
    def create_lifetime_request(cls, organizational_entity: str) -> "ShareStatisticsRequest":
        """
        Create a request for lifetime share statistics.
        
        Args:
            organizational_entity: Organization URN
            
        Returns:
            ShareStatisticsRequest: Request configured for lifetime statistics
        """
        return cls(organizational_entity=organizational_entity)
    
    @classmethod
    def create_timebound_request(
        cls,
        organizational_entity: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAY"
    ) -> "ShareStatisticsRequest":
        """
        Create a request for time-bound share statistics.
        
        Args:
            organizational_entity: Organization URN
            start_date: Start date for the time range
            end_date: End date for the time range
            granularity: Time granularity ("DAY" or "MONTH")
            
        Returns:
            ShareStatisticsRequest: Request configured for time-bound statistics
        """
        time_intervals = TimeIntervals(
            time_granularity_type=granularity,
            time_range=TimeRange(
                start=int(start_date.timestamp() * 1000),
                end=int(end_date.timestamp() * 1000)
            )
        )
        return cls(
            organizational_entity=organizational_entity,
            time_intervals=time_intervals
        )
    
    @classmethod
    def create_posts_request(
        cls,
        organizational_entity: str,
        share_urns: Optional[List[str]] = None,
        ugc_post_urns: Optional[List[str]] = None
    ) -> "ShareStatisticsRequest":
        """
        Create a request for specific posts statistics.
        
        Args:
            organizational_entity: Organization URN
            share_urns: Optional list of share URNs
            ugc_post_urns: Optional list of UGC post URNs
            
        Returns:
            ShareStatisticsRequest: Request configured for specific posts statistics
        """
        return cls(
            organizational_entity=organizational_entity,
            shares=share_urns,
            ugc_posts=ugc_post_urns
        )
    
    @classmethod
    def create_timebound_posts_request(
        cls,
        organizational_entity: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAY",
        share_urns: Optional[List[str]] = None,
        ugc_post_urns: Optional[List[str]] = None
    ) -> "ShareStatisticsRequest":
        """
        Create a request for time-bound statistics of specific posts.
        
        Args:
            organizational_entity: Organization URN
            start_date: Start date for the time range
            end_date: End date for the time range
            granularity: Time granularity ("DAY" or "MONTH")
            share_urns: Optional list of share URNs
            ugc_post_urns: Optional list of UGC post URNs
            
        Returns:
            ShareStatisticsRequest: Request configured for time-bound specific posts statistics
        """
        time_intervals = TimeIntervals(
            time_granularity_type=granularity,
            time_range=TimeRange(
                start=int(start_date.timestamp() * 1000),
                end=int(end_date.timestamp() * 1000)
            )
        )
        return cls(
            organizational_entity=organizational_entity,
            time_intervals=time_intervals,
            shares=share_urns,
            ugc_posts=ugc_post_urns
        )


# Pydantic models for share statistics responses
class ShareStatisticsData(ResponseBaseModel):
    click_count: int = Field(0, alias="clickCount")
    comment_count: int = Field(0, alias="commentCount")
    engagement: float = Field(0.0, alias="engagement")
    impression_count: int = Field(0, alias="impressionCount")
    like_count: int = Field(0, alias="likeCount")
    share_count: int = Field(0, alias="shareCount")
    unique_impressions_count: Optional[int] = Field(None, alias="uniqueImpressionsCount")
    comment_mentions_count: Optional[int] = Field(None, alias="commentMentionsCount")
    share_mentions_count: Optional[int] = Field(None, alias="shareMentionsCount")

class ShareStatistics(ResponseBaseModel):
    organizational_entity: str = Field(..., alias="organizationalEntity")
    share: Optional[str] = None  # For Share: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/share-statistics?view=li-lms-2025-02&tabs=http
    ugc_post: Optional[str] = Field(None, alias="ugcPost")  # For UGC Post
    time_range: Optional[Dict[str, int]] = Field(None, alias="timeRange")
    total_share_statistics: ShareStatisticsData = Field(..., alias="totalShareStatistics")

class ShareStatisticsResponse(ResponseBaseModel):
    elements: List[ShareStatistics]
    paging: Optional[Dict[str, Any]] = None

# Member Post Analytics Models

class DateComponent(ResponseBaseModel):
    """Represents date components (year, month, day) in LinkedIn API responses."""
    year: int
    month: int
    day: int

class DateRange(ResponseBaseModel):
    """Represents a date range with start and end components."""
    start: DateComponent
    end: DateComponent

class MemberPostAnalyticsDateRange(ResponseBaseModel):
    """
    Represents a date range for member post analytics queries.
    
    Attributes:
        start: Starting date component (inclusive)
        end: Ending date component (exclusive)
    """
    start: DateComponent
    end: DateComponent

class MemberPostAnalyticsRequest(ResponseBaseModel):
    """
    Comprehensive request schema for LinkedIn member post analytics API.
    
    This schema supports all member post analytics scenarios:
    - Aggregated member analytics (q=me)
    - Single post analytics (q=entity)
    - With or without date ranges
    - With or without daily aggregation
    
    Attributes:
        finder_type: Type of finder ("me" for aggregated, "entity" for specific post)
        query_type: Type of analytics metric (IMPRESSION, MEMBERS_REACHED, RESHARE, REACTION, COMMENT)
        aggregation: Type of aggregation (TOTAL or DAILY)
        date_range: Optional date range for time-bound analytics
        entity: Required for entity finder - the post URN to analyze
    """
    finder_type: str  # "me" or "entity"
    query_type: str  # IMPRESSION, MEMBERS_REACHED, RESHARE, REACTION, COMMENT
    aggregation: Optional[str] = None  # TOTAL, DAILY
    date_range: Optional[MemberPostAnalyticsDateRange] = None
    entity: Optional[str] = None  # Required for entity finder
    
    def model_post_init(self, __context) -> None:
        """Validate the request after initialization."""
        # Validate finder type
        if self.finder_type not in ["me", "entity"]:
            raise ValueError("finder_type must be either 'me' or 'entity'")
        
        # Validate query type
        valid_query_types = ["IMPRESSION", "MEMBERS_REACHED", "RESHARE", "REACTION", "COMMENT"]
        if self.query_type not in valid_query_types:
            raise ValueError(f"query_type must be one of: {valid_query_types}")
        
        # Validate aggregation type if provided
        if self.aggregation and self.aggregation not in ["TOTAL", "DAILY"]:
            raise ValueError("aggregation must be either 'TOTAL' or 'DAILY'")
        
        # Validate entity requirement for entity finder
        if self.finder_type == "entity" and not self.entity:
            raise ValueError("entity is required when finder_type is 'entity'")
        
        # Validate entity format if provided
        if self.entity:
            if not (self.entity.startswith("urn:li:share:") or 
                    self.entity.startswith("urn:li:ugcPost:")):
                raise ValueError(
                    "entity must be of format 'urn:li:share:{id}' or 'urn:li:ugcPost:{id}'"
                )
        
        # Validate MEMBERS_REACHED + DAILY combination
        if self.query_type == "MEMBERS_REACHED" and self.aggregation == "DAILY":
            raise ValueError("MEMBERS_REACHED query type does not support DAILY aggregation")
    
    @classmethod
    def create_member_total_request(
        cls,
        query_type: str,
        date_range: Optional[MemberPostAnalyticsDateRange] = None
    ) -> "MemberPostAnalyticsRequest":
        """
        Create a request for aggregated member analytics with total aggregation.
        
        Args:
            query_type: Type of analytics metric
            date_range: Optional date range for time-bound analytics
            
        Returns:
            MemberPostAnalyticsRequest: Request configured for aggregated member analytics
        """
        return cls(
            finder_type="me",
            query_type=query_type,
            aggregation="TOTAL",
            date_range=date_range
        )
    
    @classmethod
    def create_member_daily_request(
        cls,
        query_type: str,
        date_range: MemberPostAnalyticsDateRange
    ) -> "MemberPostAnalyticsRequest":
        """
        Create a request for aggregated member analytics with daily aggregation.
        
        Args:
            query_type: Type of analytics metric (cannot be MEMBERS_REACHED)
            date_range: Date range for time-bound analytics (required for daily)
            
        Returns:
            MemberPostAnalyticsRequest: Request configured for daily aggregated member analytics
        """
        return cls(
            finder_type="me",
            query_type=query_type,
            aggregation="DAILY",
            date_range=date_range
        )
    
    @classmethod
    def create_post_total_request(
        cls,
        entity: str,
        query_type: str,
        date_range: Optional[MemberPostAnalyticsDateRange] = None
    ) -> "MemberPostAnalyticsRequest":
        """
        Create a request for single post analytics with total aggregation.
        
        Args:
            entity: Post URN to analyze
            query_type: Type of analytics metric
            date_range: Optional date range for time-bound analytics
            
        Returns:
            MemberPostAnalyticsRequest: Request configured for single post analytics
        """
        return cls(
            finder_type="entity",
            query_type=query_type,
            aggregation="TOTAL",
            entity=entity,
            date_range=date_range
        )
    
    @classmethod
    def create_post_daily_request(
        cls,
        entity: str,
        query_type: str,
        date_range: MemberPostAnalyticsDateRange
    ) -> "MemberPostAnalyticsRequest":
        """
        Create a request for single post analytics with daily aggregation.
        
        Args:
            entity: Post URN to analyze
            query_type: Type of analytics metric (cannot be MEMBERS_REACHED)
            date_range: Date range for time-bound analytics (required for daily)
            
        Returns:
            MemberPostAnalyticsRequest: Request configured for daily single post analytics
        """
        return cls(
            finder_type="entity",
            query_type=query_type,
            aggregation="DAILY",
            entity=entity,
            date_range=date_range
        )
    
    @classmethod
    def create_from_datetime_range(
        cls,
        finder_type: str,
        query_type: str,
        start_date: datetime,
        end_date: datetime,
        aggregation: str = "TOTAL",
        entity: Optional[str] = None
    ) -> "MemberPostAnalyticsRequest":
        """
        Create a request using Python datetime objects.
        
        Args:
            finder_type: Type of finder ("me" or "entity")
            query_type: Type of analytics metric
            start_date: Start date for the analytics range
            end_date: End date for the analytics range
            aggregation: Type of aggregation (TOTAL or DAILY)
            entity: Post URN (required if finder_type is "entity")
            
        Returns:
            MemberPostAnalyticsRequest: Request configured with datetime range
        """
        date_range = MemberPostAnalyticsDateRange(
            start=DateComponent(
                year=start_date.year,
                month=start_date.month,
                day=start_date.day
            ),
            end=DateComponent(
                year=end_date.year,
                month=end_date.month,
                day=end_date.day
            )
        )
        
        return cls(
            finder_type=finder_type,
            query_type=query_type,
            aggregation=aggregation,
            date_range=date_range,
            entity=entity
        )

class MemberPostAnalytics(ResponseBaseModel):
    """
    Represents member post analytics data.
    
    Attributes:
        target_entity: URN of the target entity (for entity finder)
        metric_type: Type of analytics metric returned
        count: The analytics count value
        date_range: Optional date range for the analytics data
    """
    target_entity: Optional[Union[str, Dict[str, str]]] = Field(None, alias="targetEntity")
    metric_type: Union[str, Dict[str, str]] = Field(..., alias="metricType")
    count: int
    date_range: Optional[Union[DateRange, Dict]] = Field(None, alias="dateRange")

    def model_post_init(self, __context) -> None:
        """Process complex LinkedIn API response formats after initialization."""
        # Handle complex metricType format
        if isinstance(self.metric_type, dict):
            # Extract the actual metric type from LinkedIn's complex response
            # e.g., {'com.linkedin.adsexterna...icTypeV1': 'IMPRESSION'} -> 'IMPRESSION'
            for key, value in self.metric_type.items():
                if 'MetricTypeV1' in key or 'MetricType' in key:
                    self.metric_type = value
                    break
            else:
                # Fallback: take the first value
                self.metric_type = list(self.metric_type.values())[0] if self.metric_type else "UNKNOWN"
        
        # Handle complex targetEntity format
        if isinstance(self.target_entity, dict):
            # Extract the URN from LinkedIn's complex response
            # e.g., {'share': 'urn:li:share:123'} -> 'urn:li:share:123'
            if 'share' in self.target_entity:
                self.target_entity = self.target_entity['share']
            elif 'ugcPost' in self.target_entity:
                self.target_entity = self.target_entity['ugcPost']
            else:
                # Fallback: take the first value
                self.target_entity = list(self.target_entity.values())[0] if self.target_entity else None
        
        # Handle empty dateRange object
        if isinstance(self.date_range, dict) and not self.date_range:
            self.date_range = None

class MemberPostAnalyticsResponse(ResponseBaseModel):
    """
    Response model for member post analytics API.
    
    Contains pagination information and a list of analytics entries.
    """
    elements: List[MemberPostAnalytics] = Field(default_factory=list)
    paging: Optional[Dict[str, Any]] = None

    def model_post_init(self, __context) -> None:
        """Handle None elements from API response."""
        if self.elements is None:
            self.elements = []

# Activities API Models

class Activity(ResponseBaseModel):
    """
    Represents a LinkedIn activity.
    
    Attributes:
        id: Activity URN (optional, may not be in response)
        actor: URN of the entity that created the activity (optional)
        verb: Action verb (e.g., "SHARE") (optional)
        object: URN of the shared content (optional, may be in domainEntity)
        published: Timestamp when the activity was published (optional)
        domain_entity: Alternative field for the shared content URN
    """
    id: Optional[str] = None
    actor: Optional[str] = None
    verb: Optional[str] = None
    object: Optional[str] = None
    published: Optional[int] = None
    domain_entity: Optional[str] = Field(None, alias="domainEntity")

    def model_post_init(self, __context) -> None:
        """Process LinkedIn activity response to extract share URN."""
        # If object is not available but domainEntity is, use that
        if not self.object and self.domain_entity:
            self.object = self.domain_entity

class ActivitiesResponse(ResponseBaseModel):
    """
    Response model for activities API.
    
    Contains a dictionary mapping activity URNs to activity data.
    """
    results: Dict[str, Activity]

class LinkedInMemberAnalyticsClient:
    """
    High-level client for LinkedIn API interactions.
    
    This client wraps the official LinkedIn API client and provides additional
    functionality for managing posts, comments, analytics, and employee advocacy.
    """
    
    # Maximum posts per page in LinkedIn API
    MAX_POSTS_PER_PAGE = 100
    
    # Constants for social actions (likes/comments) pagination and limits
    DEFAULT_ELEMENTS_PER_PAGE = 100  # Conservative default for API calls
    DEFAULT_TOTAL_ELEMENTS_FETCHED_LIMIT = 100  # Default total elements to fetch
    MAX_ELEMENTS_PER_PAGE = 200  # Maximum elements per single API call
    MAX_TOTAL_ELEMENTS_FETCHED_LIMIT = 1000  # Maximum total elements to prevent excessive API calls
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        access_token: Optional[str] = None,
        version: str = settings.LINKEDIN_API_MEMBER_ANALYTICS_VERSION,
        enable_caching: bool = False
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
    
    async def _set_access_token(self, access_token: str) -> None:
        """Update the client's access token."""
        self.client.access_token = access_token
        self.access_token = access_token

    async def _paginated_fetch(
        self,
        resource_path: str,
        method: str = "get_all",
        finder_name: Optional[str] = None,
        response_model_class: Optional[type] = None,
        response_parser_function: Optional[Callable] = None,  # Callable[[Any], Tuple[Paging, List[Any]]]
        total_limit: Optional[int] = None,
        elements_per_page: Optional[int] = None,
        start: int = 0,
        query_params: Optional[Dict[str, Any]] = None,
        path_keys: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        """
        Generic helper method for paginated fetching of LinkedIn API resources.
        
        Args:
            resource_path: API resource path (e.g., "/socialActions/{urn}/likes")
            response_model_class: Pydantic model class for parsing responses
            response_parser_function: Function to parse the response (Only used if response_model_class is not provided)
            total_limit: Maximum total number of elements to fetch
            elements_per_page: Number of elements to fetch per API call
            start: Starting position for pagination
            query_params: Optional query parameters for the API call
            path_keys: Optional path keys for the API call
            
        Returns:
            List[Any]: List of elements from all fetched pages
            
        Raises:
            Exception: If there is an error during API calls
        """
        assert not (response_model_class is not None and response_parser_function is not None), "Can't provide both response_model_class and response_parser_function"
        
        if total_limit is None:
            total_limit = self.DEFAULT_TOTAL_ELEMENTS_FETCHED_LIMIT
        if elements_per_page is None:
            elements_per_page = self.DEFAULT_ELEMENTS_PER_PAGE
            
        # Validate limits
        total_limit = min(total_limit, self.MAX_TOTAL_ELEMENTS_FETCHED_LIMIT)
        elements_per_page = min(elements_per_page, self.MAX_ELEMENTS_PER_PAGE)

        all_elements = []
        current_start = start
        remaining_limit = total_limit
        
        while remaining_limit > 0:
            # Calculate count for this page
            page_count = min(remaining_limit, elements_per_page)
            
            # Make API call
            base_params = {
                "start": current_start,
                "count": page_count
            }
            if query_params:
                base_params.update(query_params)
                
            kwargs = {
                "resource_path": resource_path,
                "query_params": base_params,
                "version_string": self.version,
                "access_token": self.access_token,
            }
            if path_keys:
                kwargs["path_keys"] = path_keys
            if method == "finder":
                kwargs["finder_name"] = finder_name
                full_response = await asyncio.to_thread(self.client.finder, **kwargs)
            elif method == "get_all":
                full_response = await asyncio.to_thread(self.client.get_all, **kwargs)
            else:
                raise ValueError(f"Invalid method: {method}")
            
            status_code = full_response.status_code
            if status_code != 200:
                if all_elements:
                    return all_elements
                logger.error(f"Failed to fetch {resource_path}. Status: {status_code}")
                raise Exception(f"Failed to fetch {resource_path}. Status: {status_code}")
            raw_content = full_response.response.content
            # print("\n\nSTATUS CODE: ", status_code)
            # print("\n\nRAW CONTENT: ", raw_content)
            paging = full_response.paging
            response = {"paging": {"start": paging.start, "count": paging.count, "total": paging.total}, "elements": full_response.elements}
            # print("\n\nENTITIES: ", json.dumps(full_response.elements, indent=4))

            # import ipdb; ipdb.set_trace()
            
            # Parse response with Pydantic model
            if response_model_class:
                try:
                    parsed_response = response_model_class(**response)
                    elements = parsed_response.elements
                    paging = parsed_response.paging
                except Exception as e:
                    logger.error(f"Error parsing response: {e}")
                    elements = response.get("elements", [])
                    paging = response.get("paging", {})
            elif response_parser_function:
                paging, elements = response_parser_function(response)
            else:
                elements = response.get("elements", [])
                paging = response.get("paging", {})
            
            elements = elements or []
            
            # Add elements from this page
            all_elements.extend(elements)
            
            # Update pagination variables
            remaining_limit -= len(elements)
            current_start += len(elements)
            
            # Check if we've reached the end or gotten fewer results than requested
            total = paging.get("total", float('inf')) if isinstance(paging, dict) else getattr(paging, 'total', float('inf'))
            if (len(elements) < page_count or 
                len(elements) == 0 or
                current_start >= total):
                break
                
        return all_elements

    async def get_member_post_analytics(
        self,
        request: MemberPostAnalyticsRequest
    ) -> Tuple[bool, Optional[MemberPostAnalyticsResponse]]:
        """
        Unified method to fetch LinkedIn member post analytics.
        
        This comprehensive method handles all member post analytics scenarios:
        - Aggregated member analytics (q=me)
        - Single post analytics (q=entity)
        - With or without date ranges
        - With or without daily aggregation
        
        Args:
            request: MemberPostAnalyticsRequest object containing all query parameters
            
        Returns:
            Tuple[bool, Optional[MemberPostAnalyticsResponse]]: Tuple containing:
                - bool: True if the analytics were successfully retrieved
                - Optional[MemberPostAnalyticsResponse]: Analytics data if successful, None otherwise
            
        Raises:
            Exception: If there is an error fetching the analytics
            ValueError: If the request parameters are invalid
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/members/post-statistics?view=li-lms-2025-06&tabs=http
            
        Examples:
            # Aggregated member analytics
            request = MemberPostAnalyticsRequest.create_member_total_request(
                query_type="IMPRESSION"
            )
            success, analytics = await client.get_member_post_analytics(request)
            
            # Single post analytics
            request = MemberPostAnalyticsRequest.create_post_total_request(
                entity="urn:li:share:1234567890",
                query_type="REACTION"
            )
            success, analytics = await client.get_member_post_analytics(request)
            
            # Daily aggregated analytics with date range
            date_range = MemberPostAnalyticsDateRange(
                start=DateComponent(year=2024, month=5, day=4),
                end=DateComponent(year=2024, month=5, day=6)
            )
            request = MemberPostAnalyticsRequest.create_member_daily_request(
                query_type="IMPRESSION",
                date_range=date_range
            )
            success, analytics = await client.get_member_post_analytics(request)
            
        Note:
            - MEMBERS_REACHED does not support DAILY aggregation
            - Date ranges are required for DAILY aggregation
            - Entity is required for "entity" finder type
        """
        
        try:
            # Build query parameters for the LinkedIn API call
            query_params = {
                "queryType": request.query_type
            }
            
            # Add aggregation if provided
            if request.aggregation:
                query_params["aggregation"] = request.aggregation
            
            # Add date range if provided
            if request.date_range:
                date_range_dict = {
                    "start": {
                        "year": request.date_range.start.year,
                        "month": request.date_range.start.month,
                        "day": request.date_range.start.day
                    },
                    "end": {
                        "year": request.date_range.end.year,
                        "month": request.date_range.end.month,
                        "day": request.date_range.end.day
                    }
                }
                query_params["dateRange"] = date_range_dict
            
            # Add entity for entity finder
            if request.finder_type == "entity":
                # Format entity as expected by LinkedIn API
                if request.entity.startswith("urn:li:share:"):
                    entity_value = {"share": request.entity}
                elif request.entity.startswith("urn:li:ugcPost:"):
                    entity_value = {"ugcPost": request.entity}
                else:
                    raise ValueError(f"Unsupported entity format: {request.entity}")
                
                query_params["entity"] = entity_value
            
            # Use _paginated_fetch for proper pagination handling
            analytics_elements = await self._paginated_fetch(
                resource_path="/memberCreatorPostAnalytics",
                method="finder",
                finder_name=request.finder_type,
                total_limit=self.DEFAULT_TOTAL_ELEMENTS_FETCHED_LIMIT,
                elements_per_page=self.DEFAULT_ELEMENTS_PER_PAGE,
                query_params=query_params
            )
            
            # Debug: Log raw response to understand format
            if analytics_elements:
                logger.debug(f"Raw analytics elements sample: {json.dumps(analytics_elements[0], indent=2)}")
            
            # Create response object with proper Pydantic parsing
            analytics_response = MemberPostAnalyticsResponse(elements=analytics_elements)
            success = True
            
            # Log successful request details
            request_details = [
                f"finder: {request.finder_type}",
                f"query_type: {request.query_type}"
            ]
            
            if request.aggregation:
                request_details.append(f"aggregation: {request.aggregation}")
            
            if request.date_range:
                request_details.append("with date range")
            
            if request.entity:
                request_details.append(f"entity: {request.entity}")
            
            logger.info(
                f"Successfully retrieved member post analytics ({', '.join(request_details)}): "
                f"{len(analytics_response.elements)} entries"
            )
            
            return success, analytics_response
            
        except Exception as e:
            logger.error(f"Error fetching member post analytics: {str(e)}")
            logger.error(f"Request parameters: {request.model_dump(by_alias=True)}")
            return False, None

    async def get_activities(
        self,
        activity_urns: List[str]
    ) -> Tuple[bool, Optional[ActivitiesResponse]]:
        """
        Fetch LinkedIn activities to convert activity URNs to share URNs.
        
        This method is critical for converting UGC activity URNs to share URNs
        that can be used in analytics APIs. The LinkedIn analytics APIs often
        require share URNs rather than activity URNs.
        
        Args:
            activity_urns: List of LinkedIn activity URNs to fetch
            
        Returns:
            Tuple[bool, Optional[ActivitiesResponse]]: Tuple containing:
                - bool: True if the activities were successfully retrieved
                - Optional[ActivitiesResponse]: Activities data if successful, None otherwise
            
        Raises:
            Exception: If there is an error fetching the activities
            
        Reference:
            LinkedIn API v2 activities endpoint
            
        Examples:
            # Single activity
            success, activities = await client.get_activities([
                "urn:li:activity:7288408229108203520"
            ])
            
            # Multiple activities
            success, activities = await client.get_activities([
                "urn:li:activity:7288408229108203520",
                "urn:li:activity:7311079094459252736"
            ])
            
            # Extract share URNs from activities
            if success and activities:
                for activity_urn, activity in activities.results.items():
                    share_urn = activity.object
                    print(f"Activity {activity_urn} -> Share {share_urn}")
            
        Note:
            - This method uses the LinkedIn v2 API (not Rest.li)
            - The response maps activity URNs to activity objects
            - The activity.object field contains the share URN
            - This is essential for using activity URNs in analytics APIs
        """
        
        try:
            # Construct the full URL for the activities endpoint
            # Use comma-separated IDs for multiple activities
            ids_param = ",".join(activity_urns)
            url = f"https://api.linkedin.com/v2/activities?ids={ids_param}"
            
            # Set up headers with authorization and content type
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            logger.info(f"Making GET request to activities endpoint: {url}")
            
            # Make asynchronous HTTP GET request using aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    # Check if the request was successful
                    response.raise_for_status()
                    
                    # Parse JSON response
                    response_data = await response.json()
                    
                    # Parse response with Pydantic model
                    activities_response = ActivitiesResponse(**response_data)
                    
                    logger.info(f"Successfully retrieved {len(activities_response.results)} activities")
                    return True, activities_response
                    
        except aiohttp.ClientResponseError as http_error:
            # Handle HTTP errors (4xx, 5xx status codes)
            logger.error(f"HTTP error {http_error.status}: {http_error.message} when fetching activities")
            return False, None
        except aiohttp.ClientError as client_error:
            # Handle other aiohttp client errors (connection issues, etc.)
            logger.error(f"HTTP client error when fetching activities: {str(client_error)}")
            return False, None
        except asyncio.TimeoutError:
            # Handle request timeout
            logger.error("Request timed out when fetching activities")
            return False, None
        except json.JSONDecodeError as json_error:
            # Handle JSON parsing errors
            logger.error(f"Failed to decode JSON response when fetching activities: {str(json_error)}")
            return False, None
        except Exception as e:
            # Handle any other unexpected errors
            logger.error(f"Error fetching activities: {str(e)}")
            return False, None

    async def get_activity(
        self,
        activity_urn: str
    ) -> Tuple[bool, Optional[Activity]]:
        """
        Fetch a single LinkedIn activity to convert activity URN to share URN.
        
        This is a convenience method for fetching a single activity.
        
        Args:
            activity_urn: LinkedIn activity URN to fetch
            
        Returns:
            Tuple[bool, Optional[Activity]]: Tuple containing:
                - bool: True if the activity was successfully retrieved
                - Optional[Activity]: Activity data if successful, None otherwise
            
        Raises:
            Exception: If there is an error fetching the activity
            
        Example:
            success, activity = await client.get_activity("urn:li:activity:7288408229108203520")
            if success and activity:
                share_urn = activity.object
                print(f"Activity {activity_urn} -> Share {share_urn}")
        """
        
        success, activities_response = await self.get_activities([activity_urn])
        
        if success and activities_response and activity_urn in activities_response.results:
            return True, activities_response.results[activity_urn]
        
        return False, None

    def extract_share_urns_from_activities(
        self,
        activities_response: ActivitiesResponse
    ) -> Dict[str, str]:
        """
        Extract a mapping of activity URNs to share URNs from activities response.
        
        This helper method simplifies the process of converting activity URNs to share URNs
        that can be used in analytics APIs.
        
        Args:
            activities_response: Response from get_activities()
            
        Returns:
            Dict[str, str]: Dictionary mapping activity URNs to share URNs
            
        Example:
            success, activities = await client.get_activities([
                "urn:li:activity:7288408229108203520",
                "urn:li:activity:7311079094459252736"
            ])
            
            if success and activities:
                activity_to_share_map = client.extract_share_urns_from_activities(activities)
                # activity_to_share_map = {
                #     "urn:li:activity:7288408229108203520": "urn:li:share:1234567890",
                #     "urn:li:activity:7311079094459252736": "urn:li:share:0987654321"
                # }
        """
        
        result = {}
        for activity_urn, activity in activities_response.results.items():
            # Get the share URN from either object or domain_entity
            share_urn = activity.object
            if not share_urn and activity.domain_entity:
                share_urn = activity.domain_entity
            
            if share_urn:
                result[activity_urn] = share_urn
        
        return result

    # Convenience methods for common analytics scenarios
    
    async def get_member_impressions_total(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Tuple[bool, Optional[MemberPostAnalyticsResponse]]:
        """
        Convenience method to get total impressions for the authenticated member.
        
        Args:
            start_date: Optional start date for analytics range
            end_date: Optional end date for analytics range
            
        Returns:
            Tuple[bool, Optional[MemberPostAnalyticsResponse]]: Analytics response
        """
        
        date_range = None
        if start_date and end_date:
            date_range = MemberPostAnalyticsDateRange(
                start=DateComponent(year=start_date.year, month=start_date.month, day=start_date.day),
                end=DateComponent(year=end_date.year, month=end_date.month, day=end_date.day)
            )
        
        request = MemberPostAnalyticsRequest.create_member_total_request(
            query_type="IMPRESSION",
            date_range=date_range
        )
        
        return await self.get_member_post_analytics(request)

    async def get_member_impressions_daily(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Tuple[bool, Optional[MemberPostAnalyticsResponse]]:
        """
        Convenience method to get daily impressions for the authenticated member.
        
        Args:
            start_date: Start date for analytics range (required)
            end_date: End date for analytics range (required)
            
        Returns:
            Tuple[bool, Optional[MemberPostAnalyticsResponse]]: Analytics response
        """
        
        date_range = MemberPostAnalyticsDateRange(
            start=DateComponent(year=start_date.year, month=start_date.month, day=start_date.day),
            end=DateComponent(year=end_date.year, month=end_date.month, day=end_date.day)
        )
        
        request = MemberPostAnalyticsRequest.create_member_daily_request(
            query_type="IMPRESSION",
            date_range=date_range
        )
        
        return await self.get_member_post_analytics(request)

    async def get_post_impressions_total(
        self,
        entity_urn: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Tuple[bool, Optional[MemberPostAnalyticsResponse]]:
        """
        Convenience method to get total impressions for a specific post.
        
        Args:
            entity_urn: Post URN (share or ugcPost)
            start_date: Optional start date for analytics range
            end_date: Optional end date for analytics range
            
        Returns:
            Tuple[bool, Optional[MemberPostAnalyticsResponse]]: Analytics response
        """
        
        date_range = None
        if start_date and end_date:
            date_range = MemberPostAnalyticsDateRange(
                start=DateComponent(year=start_date.year, month=start_date.month, day=start_date.day),
                end=DateComponent(year=end_date.year, month=end_date.month, day=end_date.day)
            )
        
        request = MemberPostAnalyticsRequest.create_post_total_request(
            entity=entity_urn,
            query_type="IMPRESSION",
            date_range=date_range
        )
        
        return await self.get_member_post_analytics(request)

    async def get_post_reactions_total(
        self,
        entity_urn: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Tuple[bool, Optional[MemberPostAnalyticsResponse]]:
        """
        Convenience method to get total reactions for a specific post.
        
        Args:
            entity_urn: Post URN (share or ugcPost)
            start_date: Optional start date for analytics range
            end_date: Optional end date for analytics range
            
        Returns:
            Tuple[bool, Optional[MemberPostAnalyticsResponse]]: Analytics response
        """
        
        date_range = None
        if start_date and end_date:
            date_range = MemberPostAnalyticsDateRange(
                start=DateComponent(year=start_date.year, month=start_date.month, day=start_date.day),
                end=DateComponent(year=end_date.year, month=end_date.month, day=end_date.day)
            )
        
        request = MemberPostAnalyticsRequest.create_post_total_request(
            entity=entity_urn,
            query_type="REACTION",
            date_range=date_range
        )
        
        return await self.get_member_post_analytics(request)

    async def get_post_reactions_daily(
        self,
        entity_urn: str,
        start_date: datetime,
        end_date: datetime
    ) -> Tuple[bool, Optional[MemberPostAnalyticsResponse]]:
        """
        Convenience method to get daily reactions for a specific post.
        
        Args:
            entity_urn: Post URN (share or ugcPost)
            start_date: Start date for analytics range (required)
            end_date: End date for analytics range (required)
            
        Returns:
            Tuple[bool, Optional[MemberPostAnalyticsResponse]]: Analytics response
        """
        
        date_range = MemberPostAnalyticsDateRange(
            start=DateComponent(year=start_date.year, month=start_date.month, day=start_date.day),
            end=DateComponent(year=end_date.year, month=end_date.month, day=end_date.day)
        )
        
        request = MemberPostAnalyticsRequest.create_post_daily_request(
            entity=entity_urn,
            query_type="REACTION",
            date_range=date_range
        )
        
        return await self.get_member_post_analytics(request)

    # Enhanced methods with pagination control
    
    async def get_member_post_analytics_with_limits(
        self,
        request: MemberPostAnalyticsRequest,
        total_limit: Optional[int] = None,
        elements_per_page: Optional[int] = None
    ) -> Tuple[bool, Optional[MemberPostAnalyticsResponse]]:
        """
        Fetch LinkedIn member post analytics with custom pagination limits.
        
        This method provides fine-grained control over pagination limits for large datasets.
        
        Args:
            request: MemberPostAnalyticsRequest object containing all query parameters
            total_limit: Maximum total number of analytics entries to fetch
            elements_per_page: Number of analytics entries to fetch per API call
            
        Returns:
            Tuple[bool, Optional[MemberPostAnalyticsResponse]]: Analytics response with custom limits
            
        Note:
            - Use this method when you need to control pagination limits
            - For large datasets, consider using smaller elements_per_page values
            - total_limit is capped at MAX_TOTAL_ELEMENTS_FETCHED_LIMIT
        """
        
        try:
            # Build query parameters for the LinkedIn API call
            query_params = {
                "queryType": request.query_type
            }
            
            # Add aggregation if provided
            if request.aggregation:
                query_params["aggregation"] = request.aggregation
            
            # Add date range if provided
            if request.date_range:
                date_range_dict = {
                    "start": {
                        "year": request.date_range.start.year,
                        "month": request.date_range.start.month,
                        "day": request.date_range.start.day
                    },
                    "end": {
                        "year": request.date_range.end.year,
                        "month": request.date_range.end.month,
                        "day": request.date_range.end.day
                    }
                }
                query_params["dateRange"] = date_range_dict
            
            # Add entity for entity finder
            if request.finder_type == "entity":
                # Format entity as expected by LinkedIn API
                if request.entity.startswith("urn:li:share:"):
                    entity_value = {"share": request.entity}
                elif request.entity.startswith("urn:li:ugcPost:"):
                    entity_value = {"ugcPost": request.entity}
                else:
                    raise ValueError(f"Unsupported entity format: {request.entity}")
                
                query_params["entity"] = entity_value
            
            # Use _paginated_fetch with custom limits
            analytics_elements = await self._paginated_fetch(
                resource_path="/memberCreatorPostAnalytics",
                method="finder",
                finder_name=request.finder_type,
                total_limit=total_limit,
                elements_per_page=elements_per_page,
                query_params=query_params
            )
            
            # Debug: Log raw response to understand format
            if analytics_elements:
                logger.debug(f"Raw analytics elements sample: {json.dumps(analytics_elements[0], indent=2)}")
            
            # Create response object with proper Pydantic parsing
            analytics_response = MemberPostAnalyticsResponse(elements=analytics_elements)
            success = True
            
            # Log successful request details
            request_details = [
                f"finder: {request.finder_type}",
                f"query_type: {request.query_type}"
            ]
            
            if request.aggregation:
                request_details.append(f"aggregation: {request.aggregation}")
            
            if request.date_range:
                request_details.append("with date range")
            
            if request.entity:
                request_details.append(f"entity: {request.entity}")
            
            if total_limit:
                request_details.append(f"total_limit: {total_limit}")
            
            if elements_per_page:
                request_details.append(f"elements_per_page: {elements_per_page}")
            
            logger.info(
                f"Successfully retrieved member post analytics with limits ({', '.join(request_details)}): "
                f"{len(analytics_response.elements)} entries"
            )
            
            return success, analytics_response
            
        except Exception as e:
            logger.error(f"Error fetching member post analytics with limits: {str(e)}")
            logger.error(f"Request parameters: {request.model_dump(by_alias=True)}")
            return False, None

    async def get_all_member_post_analytics(
        self,
        request: MemberPostAnalyticsRequest,
        elements_per_page: Optional[int] = None
    ) -> Tuple[bool, Optional[MemberPostAnalyticsResponse]]:
        """
        Fetch all available LinkedIn member post analytics.
        
        This method uses the maximum total limit to retrieve as many analytics entries as possible.
        
        Args:
            request: MemberPostAnalyticsRequest object containing all query parameters
            elements_per_page: Number of analytics entries to fetch per API call
            
        Returns:
            Tuple[bool, Optional[MemberPostAnalyticsResponse]]: Complete analytics response (up to MAX_TOTAL_ELEMENTS_FETCHED_LIMIT)
            
        Note:
            - This method uses MAX_TOTAL_ELEMENTS_FETCHED_LIMIT to prevent excessive API calls
            - Consider using get_member_post_analytics_with_limits() for better control
        """
        return await self.get_member_post_analytics_with_limits(
            request=request,
            total_limit=self.MAX_TOTAL_ELEMENTS_FETCHED_LIMIT,
            elements_per_page=elements_per_page
        )

    # Enhanced convenience methods with pagination control
    
    async def get_all_member_impressions_daily(
        self,
        start_date: datetime,
        end_date: datetime,
        elements_per_page: Optional[int] = None
    ) -> Tuple[bool, Optional[MemberPostAnalyticsResponse]]:
        """
        Fetch all available daily impressions for the authenticated member.
        
        Args:
            start_date: Start date for analytics range (required)
            end_date: End date for analytics range (required)
            elements_per_page: Number of analytics entries to fetch per API call
            
        Returns:
            Tuple[bool, Optional[MemberPostAnalyticsResponse]]: Complete daily impressions response
        """
        
        date_range = MemberPostAnalyticsDateRange(
            start=DateComponent(year=start_date.year, month=start_date.month, day=start_date.day),
            end=DateComponent(year=end_date.year, month=end_date.month, day=end_date.day)
        )
        
        request = MemberPostAnalyticsRequest.create_member_daily_request(
            query_type="IMPRESSION",
            date_range=date_range
        )
        
        return await self.get_all_member_post_analytics(
            request=request,
            elements_per_page=elements_per_page
        )

    async def get_all_post_analytics(
        self,
        entity_urn: str,
        query_type: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        aggregation: str = "TOTAL",
        elements_per_page: Optional[int] = None
    ) -> Tuple[bool, Optional[MemberPostAnalyticsResponse]]:
        """
        Fetch all available analytics for a specific post.
        
        Args:
            entity_urn: Post URN (share or ugcPost)
            query_type: Type of analytics metric (IMPRESSION, REACTION, COMMENT, etc.)
            start_date: Optional start date for analytics range
            end_date: Optional end date for analytics range
            aggregation: Type of aggregation (TOTAL or DAILY)
            elements_per_page: Number of analytics entries to fetch per API call
            
        Returns:
            Tuple[bool, Optional[MemberPostAnalyticsResponse]]: Complete post analytics response
        """
        
        date_range = None
        if start_date and end_date:
            date_range = MemberPostAnalyticsDateRange(
                start=DateComponent(year=start_date.year, month=start_date.month, day=start_date.day),
                end=DateComponent(year=end_date.year, month=end_date.month, day=end_date.day)
            )
        
        if aggregation == "DAILY" and date_range:
            request = MemberPostAnalyticsRequest.create_post_daily_request(
                entity=entity_urn,
                query_type=query_type,
                date_range=date_range
            )
        else:
            request = MemberPostAnalyticsRequest.create_post_total_request(
                entity=entity_urn,
                query_type=query_type,
                date_range=date_range
            )
        
        return await self.get_all_member_post_analytics(
            request=request,
            elements_per_page=elements_per_page
        )

