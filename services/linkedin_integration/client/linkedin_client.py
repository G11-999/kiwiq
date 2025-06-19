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

# Follower statistics models
class FollowerCounts(ResponseBaseModel):
    organic_follower_count: int = Field(..., alias="organicFollowerCount")
    paid_follower_count : int = Field(..., alias="paidFollowerCount")

class FollowerGain(ResponseBaseModel):
    organic_follower_gain: int = Field(..., alias="organicFollowerGain")
    paid_follower_gain: int = Field(..., alias="paidFollowerGain")

class FollowerStatistics(ResponseBaseModel):
    follower_counts: Optional[FollowerCounts] = Field(None, alias="followerCounts")
    follower_gains: Optional[FollowerGain] = Field(None, alias="followerGains")
    organizational_entity: str = Field(..., alias="organizationalEntity")
    time_range: Dict[str, int] = Field(..., alias="timeRange")

class FollowerStatisticsResponse(ResponseBaseModel):
    elements: List[FollowerStatistics]
    # paging: Dict[str, Any]


# Define a helper model to hold counts
class FollowerCountTotals(ResponseBaseModel):
    organic: int
    paid: int
    total: int

# Define the flattened Pydantic model
class FlattenedLinkedinFollowers(ResponseBaseModel):
    organizational_entity: str
    association_totals: FollowerCountTotals
    seniority_totals: FollowerCountTotals
    industry_totals: FollowerCountTotals
    function_totals: FollowerCountTotals
    staff_count_range_totals: FollowerCountTotals
    geo_country_totals: FollowerCountTotals
    geo_totals: FollowerCountTotals


# Member follower count models
class DateComponent(ResponseBaseModel):
    """Represents date components (year, month, day) in LinkedIn API responses."""
    year: int
    month: int
    day: int

class DateRange(ResponseBaseModel):
    """Represents a date range with start and end dates."""
    start: DateComponent
    end: DateComponent

class MemberFollowersCount(ResponseBaseModel):
    """
    Represents lifetime member followers count.
    
    Attributes:
        member_followers_count: Total number of followers for the member
    """
    member_followers_count: int = Field(..., alias="memberFollowersCount")

class MemberFollowersCountByDate(ResponseBaseModel):
    """
    Represents member followers count for a specific date range.
    
    Attributes:
        date_range: The date range for this count
        member_followers_count: Number of followers gained/lost in this date range
    """
    date_range: DateRange = Field(..., alias="dateRange")
    member_followers_count: int = Field(..., alias="memberFollowersCount")

class MemberFollowersCountResponse(ResponseBaseModel):
    """
    Response model for member followers count API (lifetime).
    
    Contains pagination information and a list of follower counts.
    """
    paging: Dict[str, Any]
    elements: List[MemberFollowersCount]

class MemberFollowersCountByDateResponse(ResponseBaseModel):
    """
    Response model for member followers count API (time-bound).
    
    Contains pagination information and a list of follower counts by date range.
    """
    paging: Dict[str, Any]
    elements: List[MemberFollowersCountByDate]

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
    # print(flattened.model_dump_json(indent=2))


#####################################################################################
############## POST Schema (NOTE: it may change depending on type of post!)  ########
#####################################################################################


class LinkedInPostDistribution(ResponseBaseModel):
    """
    Represents the distribution settings for a LinkedIn post.
    
    Attributes:
        feed_distribution: The feed distribution setting ("MAIN_FEED", "NONE", "GROUP_FEED")
        third_party_distribution_channels: List of third-party distribution channels
    """
    feed_distribution: str = Field(..., alias="feedDistribution")
    third_party_distribution_channels: List[str] = Field(default_factory=list, alias="thirdPartyDistributionChannels")


class LinkedInPostContentReference(ResponseBaseModel):
    """
    Represents a content reference in a LinkedIn post (e.g., job posting, article).
    
    Attributes:
        id: The URN or ID of the referenced content
    """
    id: str


class LinkedInPostContentMedia(ResponseBaseModel):
    """
    Represents media content in a LinkedIn post.
    
    Attributes:
        id: Media asset URN
        alt_text: Alternative text for the media (for accessibility)
        title: Title of the media (for documents/videos)
    """
    id: str
    alt_text: Optional[str] = Field(None, alias="altText")
    title: Optional[str] = None


class LinkedInPostContent(ResponseBaseModel):
    """
    Represents the content section of a LinkedIn post.
    
    This can contain different types of content including references to external content
    (like job postings) or media attachments (images, videos, documents).
    
    Attributes:
        reference: Reference to external content (e.g., job posting)
        media: Media content (image, video, document)
    """
    reference: Optional[LinkedInPostContentReference] = None
    media: Optional[LinkedInPostContentMedia] = None


class LinkedInPostReshareContext(ResponseBaseModel):
    """
    Represents the reshare context for LinkedIn posts that are reshares.
    
    Attributes:
        parent: URN of the immediate parent post being reshared
        root: URN of the original root post in the reshare chain
    """
    parent: str
    root: str


class LinkedInPostLifecycleStateInfo(ResponseBaseModel):
    """
    Represents lifecycle state information for a LinkedIn post.
    
    Attributes:
        is_edited_by_author: Whether the post has been edited by the author
    """
    is_edited_by_author: bool = Field(..., alias="isEditedByAuthor")


class LinkedInPostAPI(ResponseBaseModel):
    """
    Comprehensive schema for LinkedIn posts returned by the Posts API.
    
    This model represents the complete structure of LinkedIn posts as returned by
    both get_posts() and get_post_by_urn() methods, covering all variations including:
    - Original posts with text content
    - Posts with media attachments (images, videos, documents)
    - Posts with content references (job postings, articles)
    - Reshares with commentary
    - Various lifecycle states and visibility settings
    
    Attributes:
        id: Unique LinkedIn post URN (e.g., "urn:li:share:123" or "urn:li:ugcPost:456")
        author: URN of the post author (person or organization)
        commentary: Text content/commentary of the post
        created_at: Timestamp when the post was created (milliseconds since epoch)
        published_at: Timestamp when the post was published (milliseconds since epoch)
        last_modified_at: Timestamp when the post was last modified (milliseconds since epoch)
        lifecycle_state: Current state of the post ("PUBLISHED", "DRAFT", "PROCESSING", etc.)
        visibility: Visibility setting of the post ("PUBLIC", "CONNECTIONS", etc.)
        distribution: Distribution settings for the post
        content: Content section containing media or references
        reshare_context: Reshare information if this is a reshare
        lifecycle_state_info: Additional lifecycle state information
        is_reshare_disabled_by_author: Whether resharing is disabled by the author
    
    Design Notes:
        - All timestamp fields use LinkedIn's millisecond epoch format
        - URNs follow LinkedIn's standard format (urn:li:type:id)
        - Content can be either media or reference, not both simultaneously
        - Reshare context only exists for reshared posts
        - Commentary is the main text content visible to users
    """
    id: str
    author: str
    commentary: Optional[str] = None
    created_at: int = Field(..., alias="createdAt")
    published_at: Optional[int] = Field(None, alias="publishedAt")
    last_modified_at: int = Field(..., alias="lastModifiedAt")
    lifecycle_state: str = Field(..., alias="lifecycleState")
    visibility: str
    distribution: LinkedInPostDistribution
    content: Optional[LinkedInPostContent] = None
    reshare_context: Optional[LinkedInPostReshareContext] = Field(None, alias="reshareContext")
    lifecycle_state_info: LinkedInPostLifecycleStateInfo = Field(..., alias="lifecycleStateInfo")
    is_reshare_disabled_by_author: bool = Field(False, alias="isReshareDisabledByAuthor")

    @property
    def is_reshare(self) -> bool:
        """Check if this post is a reshare."""
        return self.reshare_context is not None

    @property
    def has_media(self) -> bool:
        """Check if this post has media content."""
        return self.content is not None and self.content.media is not None

    @property
    def has_reference(self) -> bool:
        """Check if this post has a content reference."""
        return self.content is not None and self.content.reference is not None

    @property
    def created_datetime(self) -> datetime:
        """Get created timestamp as Python datetime object."""
        from datetime import datetime, timezone
        return datetime.fromtimestamp(self.created_at / 1000, tz=timezone.utc)

    @property
    def published_datetime(self) -> Optional[datetime]:
        """Get published timestamp as Python datetime object if available."""
        if self.published_at is None:
            return None
        from datetime import datetime, timezone
        return datetime.fromtimestamp(self.published_at / 1000, tz=timezone.utc)


class LinkedInPostsResponse(ResponseBaseModel):
    """
    Response model for batch fetching LinkedIn posts.
    
    This model represents the paginated response from the LinkedIn Posts API
    when fetching multiple posts.
    
    Attributes:
        elements: List of LinkedIn posts
        paging: Pagination information including count, start, and links
    """
    elements: List[LinkedInPostAPI]
    paging: Optional[Dict[str, Any]] = None

#####################################################################################
#####################################################################################


# Organization role models
class OrganizationRole(ResponseBaseModel):
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

class OrganizationRolesResponse(ResponseBaseModel):
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


# Pydantic models for person/profile responses
class MultiLocaleString(ResponseBaseModel):
    """
    Represents a localized string with multiple locale support.
    
    Attributes:
        localized: Dictionary mapping locale strings to localized text
        preferred_locale: The preferred locale information
    """
    localized: Optional[Dict[str, str]] = None
    preferred_locale: Optional[Dict[str, str]] = Field(None, alias="preferredLocale")

class ProfilePicture(ResponseBaseModel):
    """
    Represents profile picture metadata.
    
    Attributes:
        display_image: URN or URL of the display image
        display_image_urn: URN format of the display image
    """
    display_image: Optional[str] = Field(None, alias="displayImage")
    display_image_urn: Optional[str] = Field(None, alias="displayImageUrn")

# Add the new UserInfo model after the existing Person model (around line 950)
class UserInfoLocale(ResponseBaseModel):
    """
    Represents locale information in LinkedIn API responses.
    
    Attributes:
        country: Country code (e.g., "US")
        language: Language code (e.g., "en")
    """
    country: Optional[str] = None
    language: Optional[str] = None

class UserInfo(ResponseBaseModel):
    """
    Represents LinkedIn user information from the /v2/userinfo endpoint.
    
    This model provides OpenID Connect-style user information including
    basic profile data, email information, and verification status.
    All fields except 'sub' are optional to handle cases where information
    is not available due to privacy settings or API permissions.
    
    Attributes:
        sub: Subject identifier - unique identifier for the user
        name: Full name of the user
        given_name: User's first name
        family_name: User's last name  
        picture: URL of the user's profile picture
        locale: User's locale (e.g., "en-US")
        email: User's primary email address (optional)
        email_verified: Whether the user's email has been verified (optional)
    """
    sub: str
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    picture: Optional[str] = None
    locale: Optional[UserInfoLocale] = None
    email: Optional[str] = None
    email_verified: Optional[bool] = None

    @property
    def full_name(self) -> Optional[str]:
        """Get the full name, preferring the 'name' field or constructing from given/family names."""
        if self.name:
            return self.name
        elif self.given_name and self.family_name:
            return f"{self.given_name} {self.family_name}"
        elif self.given_name:
            return self.given_name
        elif self.family_name:
            return self.family_name
        return None

    @property
    def has_email(self) -> bool:
        """Check if email information is available."""
        return self.email is not None

    @property
    def is_email_verified(self) -> bool:
        """Check if email is verified (returns False if email_verified is None)."""
        return self.email_verified is True


class Person(ResponseBaseModel):
    """
    Represents a LinkedIn person/member profile.
    
    All fields are optional to prevent errors when some fields are not available
    due to privacy settings or API permissions.
    
    Attributes:
        id: Unique identifying value for the member (personId)
        first_name: Localizable first name as MultiLocaleString
        localized_first_name: Localized version of firstName
        last_name: Localizable last name as MultiLocaleString
        localized_last_name: Localized version of lastName
        maiden_name: Localizable maiden name as MultiLocaleString
        localized_maiden_name: Localized version of maidenName
        headline: Localizable headline as MultiLocaleString
        localized_headline: Localized version of headline
        profile_picture: Profile picture metadata
        vanity_name: Vanity name used for public profile URL
    """
    id: Optional[str] = None
    first_name: Optional[MultiLocaleString] = Field(None, alias="firstName")
    localized_first_name: Optional[str] = Field(None, alias="localizedFirstName")
    last_name: Optional[MultiLocaleString] = Field(None, alias="lastName")
    localized_last_name: Optional[str] = Field(None, alias="localizedLastName")
    maiden_name: Optional[MultiLocaleString] = Field(None, alias="maidenName")
    localized_maiden_name: Optional[str] = Field(None, alias="localizedMaidenName")
    headline: Optional[MultiLocaleString] = None
    localized_headline: Optional[str] = Field(None, alias="localizedHeadline")
    profile_picture: Optional[ProfilePicture] = Field(None, alias="profilePicture")
    vanity_name: Optional[str] = Field(None, alias="vanityName")


# Additional models for Organization profiles
class LocaleInfo(ResponseBaseModel):
    """
    Represents locale information in LinkedIn API responses.
    
    Attributes:
        country: Country code (e.g., "US")
        language: Language code (e.g., "en")
    """
    country: str
    language: str


class FoundedDate(ResponseBaseModel):
    """
    Represents the founding date of an organization.
    
    Attributes:
        year: The year the organization was founded
        month: Optional month the organization was founded
        day: Optional day the organization was founded
    """
    year: int
    month: Optional[int] = None
    day: Optional[int] = None


class CoverPhotoV2(ResponseBaseModel):
    """
    Represents cover photo information for an organization.
    
    Attributes:
        cropped: URN of the cropped cover photo asset
        original: URN of the original cover photo asset
        crop_info: Information about how the photo was cropped
    """
    cropped: Optional[str] = None
    original: Optional[str] = None
    crop_info: Optional[Dict[str, int]] = Field(None, alias="cropInfo")


class LogoV2(ResponseBaseModel):
    """
    Represents logo information for an organization.
    
    Attributes:
        cropped: URN of the cropped logo asset
        original: URN of the original logo asset
        crop_info: Information about how the logo was cropped
    """
    cropped: Optional[str] = None
    original: Optional[str] = None
    crop_info: Optional[Dict[str, int]] = Field(None, alias="cropInfo")


class OrganizationLocation(ResponseBaseModel):
    """
    Represents a location for an organization.
    
    All fields are optional as location data may not be fully available.
    """
    # This would be expanded based on actual location data structure
    # when available from the API
    pass


class LinkedinOrganization(ResponseBaseModel):
    """
    Represents a LinkedIn organization profile.
    
    This model captures comprehensive information about a LinkedIn organization including
    basic profile data, branding assets, company information, and metadata. All fields are
    optional to handle cases where information is not available due to privacy settings
    or API permissions.
    
    Attributes:
        id: Unique numeric identifier for the organization
        vanity_name: Vanity name used for public profile URL (e.g., "kiwiq-ai")
        name: Localizable organization name as MultiLocaleString
        localized_name: Localized version of the organization name
        description: Localizable organization description as MultiLocaleString
        localized_description: Localized version of the organization description
        website: Localizable website URL as MultiLocaleString
        localized_website: Localized version of the website URL
        founded_on: Date when the organization was founded
        organization_type: Type of organization (e.g., "PRIVATELY_HELD", "PUBLIC_COMPANY")
        primary_organization_type: Primary organization type classification
        staff_count_range: Range of staff count (e.g., "SIZE_2_TO_10", "SIZE_11_TO_50")
        specialties: List of organization specialties/focus areas
        localized_specialties: Localized versions of specialties
        alternative_names: List of alternative names for the organization
        locations: List of organization locations
        groups: List of groups the organization belongs to
        logo_v2: Logo information including cropped and original versions
        cover_photo_v2: Cover photo information including cropped and original versions
        default_locale: Default locale information for the organization
        version_tag: Version tag for the organization profile
        auto_created: Whether the organization profile was auto-created
        created: Information about when the organization profile was created
        last_modified: Information about when the organization profile was last modified
    """
    id: Optional[int] = None  # NOTE: this is simple int ID, not org URN!
    vanity_name: Optional[str] = Field(None, alias="vanityName")
    name: Optional[MultiLocaleString] = None
    localized_name: Optional[str] = Field(None, alias="localizedName")
    description: Optional[MultiLocaleString] = None
    localized_description: Optional[str] = Field(None, alias="localizedDescription")
    website: Optional[MultiLocaleString] = None
    localized_website: Optional[str] = Field(None, alias="localizedWebsite")
    founded_on: Optional[FoundedDate] = Field(None, alias="foundedOn")
    organization_type: Optional[str] = Field(None, alias="organizationType")
    primary_organization_type: Optional[str] = Field(None, alias="primaryOrganizationType")
    staff_count_range: Optional[str] = Field(None, alias="staffCountRange")
    specialties: Optional[List[str]] = None
    localized_specialties: Optional[List[str]] = Field(None, alias="localizedSpecialties")
    alternative_names: Optional[List[str]] = Field(None, alias="alternativeNames")
    locations: Optional[List[OrganizationLocation]] = None
    groups: Optional[List[str]] = None
    logo_v2: Optional[LogoV2] = Field(None, alias="logoV2")
    cover_photo_v2: Optional[CoverPhotoV2] = Field(None, alias="coverPhotoV2")
    default_locale: Optional[LocaleInfo] = Field(None, alias="defaultLocale")
    version_tag: Optional[str] = Field(None, alias="versionTag")
    auto_created: Optional[bool] = Field(None, alias="autoCreated")
    created: Optional[CreatedModified] = None
    last_modified: Optional[CreatedModified] = Field(None, alias="lastModified")

    @property
    def public_url(self) -> Optional[str]:
        """Get the public LinkedIn URL for this organization."""
        if self.vanity_name:
            return f"https://www.linkedin.com/company/{self.vanity_name}"
        return None

    @property
    def display_name(self) -> Optional[str]:
        """Get the best available display name for the organization."""
        return self.localized_name or (self.name.localized.get("en_US") if self.name and self.name.localized else None)

    @property
    def display_description(self) -> Optional[str]:
        """Get the best available description for the organization."""
        return self.localized_description or (self.description.localized.get("en_US") if self.description and self.description.localized else None)

    @property
    def display_website(self) -> Optional[str]:
        """Get the best available website URL for the organization."""
        return self.localized_website or (self.website.localized.get("en_US") if self.website and self.website.localized else None)

    @property
    def founded_year(self) -> Optional[int]:
        """Get the founding year if available."""
        return self.founded_on.year if self.founded_on else None


# Type alias for member profile - reuse existing Person model
LinkedinMemberProfile = Person


class LinkedInClient:
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
        version: str = settings.LINKEDIN_API_VERSION,
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

    async def get_member_organization_roles(self) -> Tuple[bool, Optional[OrganizationRolesResponse]]:
        """
        Fetch all organizations and member roles for the authenticated member.

        This method retrieves the roles assigned to the authenticated member within
        various organizations using the LinkedIn API's organization access control endpoint.

        Returns:
            Tuple[bool, Optional[OrganizationRolesResponse]]: Tuple containing:
                - bool: True if the roles were successfully retrieved
                - Optional[OrganizationRolesResponse]: Response object containing organization role assignments if successful, None otherwise

        Raises:
            Exception: If there is an error fetching the organization roles.
        """

        try:
            # Make API call to fetch organization roles
            response = await asyncio.to_thread(
                self.client.finder,
                resource_path="/organizationAcls",
                finder_name="roleAssignee",
                # query_params={"q": "roleAssignee"},
                version_string=self.version,
                access_token=self.access_token
            )
            
            # Check response status code
            success = response.status_code == 200
            if success:
                response_data = {"elements": response.elements}
                # Parse into OrganizationRolesResponse
                roles_response = OrganizationRolesResponse(**response_data)
                logger.info(f"Successfully retrieved {len(roles_response.elements)} organization roles")
                return success, roles_response
            else:
                logger.error(f"Failed to fetch organization roles. Status: {response.status_code}")
                return False, None

        except Exception as e:
            logger.error(f"Error fetching organization roles for the authenticated member: {str(e)}")
            return False, None

    async def get_organization_details(
        self,
        organization_id: str
    ) -> Tuple[bool, Optional[LinkedinOrganization]]:
        """
        Fetch detailed information about a LinkedIn organization.
        
        This method retrieves comprehensive details about an organization including
        name, description, website, industry, logo, and other profile information.
        
        Args:
            organization_id: LinkedIn organization ID or URN
            
        Returns:
            Tuple[bool, Optional[LinkedinOrganization]]: Tuple containing:
                - bool: True if the organization details were successfully retrieved
                - Optional[LinkedinOrganization]: Organization profile details as a Pydantic model if successful, None otherwise
            
        Raises:
            Exception: If there is an error fetching the organization details
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/organizations/organization-lookup-api
            
        Example:
            org = await client.get_organization_details("105029503")
            print(f"Name: {org.display_name}")
            print(f"Website: {org.display_website}")
            print(f"Founded: {org.founded_year}")
            print(f"URL: {org.public_url}")
            
        Note:
            - The organization ID can be provided with or without the URN prefix
            - All response fields are optional to prevent parsing errors
            - Some fields may not be available due to privacy settings or API permissions
            - Use the display_* properties for the best available localized text
        
        {
            "vanityName": "kiwiq-ai",
            "localizedName": "KiwiQ AI",
            "website": {
                "localized": {
                    "en_US": "https://kiwiq.ai/pilot"
                },
                "preferredLocale": {
                    "country": "US",
                    "language": "en"
                }
            },
            "foundedOn": {
                "year": 2024
            },
            "created": {
                "actor": "urn:li:person:qUvas1UvE2",
                "time": 1731526104166
            },
            "groups": [],
            "description": {
                "localized": {
                    "en_US": "KiwiQ.ai is building the intelligence layer for modern marketing teams. In a world where marketers juggle a bazillion tools, our AI Agents seamlessly integrate with your existing marketing stack to deliver high-context intelligence you can take action on. \n\nFounded by ex-BigTech alumni with 20 years combined experience in AI, Marketing and Product leadership, we are backed by top-tier marketing leaders from LinkedIn, Canva, and Kantar. \n\nLaunching soon. Get in touch with us on hello@kiwiq.ai."
                },
                "preferredLocale": {
                    "country": "US",
                    "language": "en"
                }
            },
            "versionTag": "3191572956",
            "coverPhotoV2": {
                "cropped": "urn:li:digitalmediaAsset:D4E3DAQFQB_jwXs7tow",
                "original": "urn:li:digitalmediaAsset:D4E1BAQGE8xGDj63RwQ",
                "cropInfo": {
                    "x": 0,
                    "width": 1128,
                    "y": 0,
                    "height": 191
                }
            },
            "defaultLocale": {
                "country": "US",
                "language": "en"
            },
            "organizationType": "PRIVATELY_HELD",
            "alternativeNames": [],
            "specialties": [],
            "staffCountRange": "SIZE_2_TO_10",
            "localizedSpecialties": [],
            "name": {
                "localized": {
                    "en_US": "KiwiQ AI"
                },
                "preferredLocale": {
                    "country": "US",
                    "language": "en"
                }
            },
            "primaryOrganizationType": "NONE",
            "locations": [],
            "id": 105029503,
            "lastModified": {
                "actor": "urn:li:person:H5Arsrp8KM",
                "time": 1747450161732
            },
            "localizedDescription": "KiwiQ.ai is building the intelligence layer for modern marketing teams. In a world where marketers juggle a bazillion tools, our AI Agents seamlessly integrate with your existing marketing stack to deliver high-context intelligence you can take action on. \n\nFounded by ex-BigTech alumni with 20 years combined experience in AI, Marketing and Product leadership, we are backed by top-tier marketing leaders from LinkedIn, Canva, and Kantar. \n\nLaunching soon. Get in touch with us on hello@kiwiq.ai.",
            "autoCreated": false,
            "localizedWebsite": "https://kiwiq.ai/pilot",
            "logoV2": {
                "cropped": "urn:li:digitalmediaAsset:D4E0BAQHia5snU2zbig",
                "original": "urn:li:digitalmediaAsset:D4E0BAQHia5snU2zbig",
                "cropInfo": {
                    "x": 0,
                    "width": 0,
                    "y": 0,
                    "height": 0
                }
            }
        }
        """
        # Generate cache key
        organization_id = organization_id.split(":")[-1] if "urn:" in organization_id else organization_id
        
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
            response = await asyncio.to_thread(
                self.client.get,
                resource_path=f"/organizations/{organization_id}",
                # query_params={"fields": ",".join(fields)},
                version_string=self.version,
                access_token=self.access_token
            )
            
            # Check response status code
            success = response.status_code == 200
            if success:
                response_data = response.entity
                
                # Parse response with Pydantic model
                organization = LinkedinOrganization(**response_data)
                
                logger.info(f"Successfully retrieved organization profile for ID: {organization_id}")
                return success, organization
            else:
                logger.error(f"Failed to fetch organization details for {organization_id}. Status: {response.status_code}")
                return False, None
            
        except Exception as e:
            logger.error(f"Error fetching organization details for {organization_id}: {str(e)}")
            return False, None
    
    async def get_member_profile(
        self,
        # member_id: str
    ) -> Tuple[bool, Optional[LinkedinMemberProfile]]:
        """
        Fetch detailed information about the authenticated LinkedIn member profile.
        
        This method retrieves comprehensive details about the authenticated member including
        name, headline, profile picture, vanity name, and other available profile information.
        All fields are optional to handle cases where information is not available due to
        privacy settings or API permissions.
            
        Returns:
            Tuple[bool, Optional[LinkedinMemberProfile]]: Tuple containing:
                - bool: True if the member profile was successfully retrieved
                - Optional[LinkedinMemberProfile]: Member profile details as a Pydantic model (alias for Person) if successful, None otherwise
            
        Raises:
            Exception: If there is an error fetching the member profile
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/shared/integrations/people/profile-api
            
        Example:
            member = await client.get_member_profile()
            print(f"Name: {member.localized_first_name} {member.localized_last_name}")
            print(f"Headline: {member.localized_headline}")
            if member.vanity_name:
                print(f"Profile URL: https://linkedin.com/in/{member.vanity_name}")
            
        Note:
            - This method retrieves the authenticated member's profile using /me endpoint
            - All response fields are optional to prevent parsing errors
            - Some fields may not be available due to privacy settings or API permissions
            - MemberProfile is an alias for the Person model for semantic clarity
        """
        
        try:
            # Make API call to get authenticated member profile
            response = await asyncio.to_thread(
                self.client.get,
                resource_path=f"/me",
                version_string=self.version,
                access_token=self.access_token
            )
            
            # Check response status code
            success = response.status_code == 200
            if success:
                response_data = response.entity
                
                # Parse response with Pydantic model
                member_profile = LinkedinMemberProfile(**response_data)
                
                logger.info(f"Successfully retrieved authenticated member profile")
                return success, member_profile
            else:
                logger.error(f"Failed to fetch member profile. Status: {response.status_code}")
                return False, None
            
        except Exception as e:
            logger.error(f"Error fetching member profile: {str(e)}")
            return False, None

    async def get_person_profile(
        self,
        person_id: str
    ) -> Tuple[bool, Optional[Person]]:
        """
        Fetch detailed information about a LinkedIn person profile by ID.
        
        This method retrieves comprehensive details about a person including
        name, headline, profile picture, vanity name, and other available profile information.
        All fields are optional to handle cases where information is not available due to
        privacy settings or API permissions.
        
        Args:
            person_id: LinkedIn person ID (can be with or without URN prefix)
            
        Returns:
            Tuple[bool, Optional[Person]]: Tuple containing:
                - bool: True if the person profile was successfully retrieved
                - Optional[Person]: Person profile details as a Pydantic model with optional fields if successful, None otherwise
            
        Raises:
            Exception: If there is an error fetching the person profile
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/shared/integrations/people/profile-api
            
        Example:
            person = await client.get_person_profile("abc123")
            # print(f"Name: {person.localized_first_name} {person.localized_last_name}")
            # print(f"Headline: {person.localized_headline}")
            
        Note:
            - The person ID can be provided with or without the URN prefix
            - All response fields are optional to prevent parsing errors
            - Some fields may not be available due to the person's privacy settings
            - The vanity name is used for public profile URLs: linkedin.com/in/{vanity_name}
        """
        
        try:
            # Clean the person ID (remove URN prefix if present)
            if person_id.startswith("urn:li:person:"):
                clean_person_id = person_id.replace("urn:li:person:", "")
            else:
                clean_person_id = person_id
            
            # Make API call to get person profile
            response = await asyncio.to_thread(
                self.client.get,
                resource_path=f"/people/(id:{clean_person_id})",
                version_string=self.version,
                access_token=self.access_token
            )
            
            # Check response status code
            success = response.status_code == 200
            if success:
                response_data = response.entity
                
                # Parse response with Pydantic model
                person = Person(**response_data)
                
                logger.info(f"Successfully retrieved person profile for ID: {person_id}")
                return success, person
            else:
                logger.error(f"Failed to fetch person profile for {person_id}. Status: {response.status_code}")
                return False, None
            
        except Exception as e:
            logger.error(f"Error fetching person profile for {person_id}: {str(e)}")
            return False, None
    
    async def get_member_info_including_email(self) -> Tuple[bool, UserInfo]:
        """
        Fetch user information from the LinkedIn /v2/userinfo endpoint.
        
        This method retrieves OpenID Connect-style user information for the authenticated
        user including basic profile data, email information, and verification status.
        This endpoint provides different information compared to the standard profile APIs.
        
        Returns:
            Tuple[bool, UserInfo]: Tuple containing success flag and UserInfo object containing information including subject ID, names, picture, locale, and optional email data
            
        Raises:
            Exception: If there is an error fetching the user information
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow
            
        Example:
            user_info = await client.get_user_info()
            print(f"User: {user_info.full_name}")
            print(f"Subject ID: {user_info.sub}")
            print(f"Locale: {user_info.locale}")
            if user_info.has_email:
                print(f"Email: {user_info.email} (verified: {user_info.is_email_verified})")
            
        Note:
            - This method uses the /v2/userinfo endpoint which returns OpenID Connect style data
            - The 'sub' field is always present and serves as a unique user identifier
            - Email fields are optional and may not be present due to scope limitations
            - This endpoint requires appropriate OAuth scopes including 'openid' and optionally 'email'
            - The response format differs from the standard LinkedIn profile APIs
            
        Sample Response:
            {
                "sub": "782bbtaQ",
                "name": "John Doe", 
                "given_name": "John",
                "family_name": "Doe",
                "picture": "https://media.licdn-ei.com/dms/image/...",
                "locale": "en-US",
                "email": "doe@email.com",
                "email_verified": true
            }
        """
        try:
            # Construct the full URL for the userinfo endpoint
            url = f"https://api.linkedin.com/v2/userinfo"
            
            # Set up headers with authorization and content type
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            logger.info(f"Making GET request to userinfo endpoint: {url}")
            
            # Make asynchronous HTTP GET request using aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    # Check if the request was successful
                    response.raise_for_status()
                    
                    # Parse JSON response
                    response_data = await response.json()
                    
                    # print("\n\n\n\n RESPONSE DATA: ", response_data, "\n\n\n\n")
                    
                    # Parse response with Pydantic model
                    user_info = UserInfo(**response_data)
                    
                    logger.info(f"Successfully retrieved user info for subject ID: {user_info.sub}")
                    return True, user_info
                    
        except aiohttp.ClientResponseError as http_error:
            # Handle HTTP errors (4xx, 5xx status codes)
            logger.error(f"HTTP error {http_error.status}: {http_error.message} when fetching user info")
            return False, None
        except aiohttp.ClientError as client_error:
            # Handle other aiohttp client errors (connection issues, etc.)
            logger.error(f"HTTP client error when fetching user info: {str(client_error)}")
            return False, None
        except asyncio.TimeoutError:
            # Handle request timeout
            logger.error("Request timed out when fetching user info")
            return False, None
        except json.JSONDecodeError as json_error:
            # Handle JSON parsing errors
            logger.error(f"Failed to decode JSON response when fetching user info: {str(json_error)}")
            return False, None
        except Exception as e:
            # Handle any other unexpected errors
            logger.error(f"Error fetching user info: {str(e)}")
            return False, None
    
    # async def _cache_result(self, key: str, result: Any) -> None:
    #     """
    #     Cache a result using the key.
        
    #     Args:
    #         key: Unique identifier for the cached result
    #         result: Data to cache (can be a Pydantic model or other data)
            
    #     Note:
    #         This method will only cache results if caching is enabled.
    #         Pydantic models are properly serialized to JSON before caching.
    #     """
    #     if not self.enable_caching:
    #         return
            
    #     # Convert Pydantic models to dict for proper serialization
    #     if isinstance(result, BaseModel):
    #         result_dict = result.model_dump(by_alias=True)
    #         dump_to_json({key: result_dict})
    #     elif isinstance(result, list) and all(isinstance(item, BaseModel) for item in result):
    #         # Handle list of Pydantic models
    #         result_dict = [item.model_dump(by_alias=True) for item in result]
    #         dump_to_json({key: result_dict})
    #     elif isinstance(result, dict) and any(isinstance(value, BaseModel) for value in result.values()):
    #         # Handle dict with Pydantic model values
    #         result_dict = {k: v.model_dump(by_alias=True) if isinstance(v, BaseModel) else v 
    #                       for k, v in result.items()}
    #         dump_to_json({key: result_dict})
    #     else:
    #         # Handle regular data
    #         dump_to_json({key: result})
    
    # async def _get_cached_result(self, key: str) -> Optional[Any]:
    #     """
    #     Get a cached result using the key.
        
    #     Args:
    #         key: Unique identifier for the cached result
            
    #     Returns:
    #         Any: The cached result if found and caching is enabled, None otherwise.
    #              Pydantic models are properly reconstructed from cached JSON.
    #     """
    #     if not self.enable_caching:
    #         return None
            
    #     try:
    #         cached_data = load_and_get_key(key)
    #         if cached_data is None:
    #             return None
                
    #         return cached_data
    #     except (FileNotFoundError, json.JSONDecodeError):
    #         return None
    
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
    
    async def get_posts(
        self,
        account_id: str,
        limit: Optional[int] = None,
        days: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Tuple[bool, Optional[List[Dict[str, Any]]]]:
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
            Tuple[bool, Optional[List[Dict[str, Any]]]]: Tuple containing:
                - bool: True if the posts were successfully retrieved
                - Optional[List[Dict[str, Any]]]: List of LinkedIn posts matching the criteria if successful, None otherwise
            
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
            
        # Prepare query parameters for LinkedIn Posts API
        author_urn = account_id  # f"urn:li:{'person' if account.account_type == 'individual' else 'organization'}:{account.linkedin_id}"
        query_params = {
            "author": author_urn,
            "sortBy": "LAST_MODIFIED"
        }
        
        # Determine fetch limit - use limit if provided, otherwise use max posts per page
        fetch_limit = min(limit, self.MAX_POSTS_PER_PAGE) if limit else self.MAX_POSTS_PER_PAGE
        
        
        try:
            # Use _paginated_fetch to get all posts
            raw_posts = await self._paginated_fetch(
                resource_path="/posts",
                method="finder",
                finder_name="author",
                total_limit=fetch_limit,
                elements_per_page=min(fetch_limit, self.MAX_POSTS_PER_PAGE),
                query_params=query_params
            )
            
            # Process and filter posts
            posts = []
            for post_data in raw_posts:
                created_time = datetime.fromtimestamp(post_data["createdAt"] / 1000, tz=timezone.utc)
                
                # Apply date filtering
                if start_date and created_time < start_date:
                    continue
                if end_date and created_time > end_date:
                    continue
                
                # print("\n\n\n\n POST DATA: ", post_data, "\n\n")
                # print("\n\n\n\n JSON DUMP: ", json.dumps(post_data, indent=4), "\n\n\n\n")
                posts.append(post_data)
                
                # Apply limit after filtering
                if limit and len(posts) >= limit:
                    break
            
            logger.info(f"Successfully retrieved {len(posts)} posts for account {author_urn}")
            return True, posts
            
        except Exception as e:
            logger.error(f"Error fetching posts for account {author_urn}: {str(e)}")
            return False, None
    
    # Post Management Methods
    
    async def get_post_by_urn(
        self,
        post_urn: str,
        view_context: str = "READER"
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Get a LinkedIn post by its URN.
        
        This method retrieves a specific post using its URN (Universal Resource Name).
        The URN can be either a ugcPostUrn (urn:li:ugcPost:{id}) or shareUrn (urn:li:share:{id}).
        
        Args:
            post_urn: LinkedIn post URN (e.g., "urn:li:ugcPost:12345" or "urn:li:share:67890")
            view_context: View context for the post (default is "READER")
                        - "READER": Published version viewable to general audience
                        - "AUTHOR": Latest version which may be in DRAFT, PROCESSING, or PUBLISHED state
                        
        Returns:
            Tuple[bool, Optional[Dict[str, Any]]]: Tuple containing:
                - bool: True if the post was successfully retrieved
                - Optional[Dict[str, Any]]: Post data including content, metadata, and analytics information if successful, None otherwise
            
        Raises:
            Exception: If there is an error fetching the post
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/posts-api
            
        Note:
            URNs are automatically URL encoded when making the API call.
            Use the Images API and Videos API to retrieve additional details about media assets.
        """
        
        try:
            # URL encode the URN for the API call
            encoded_urn = quote(post_urn, safe="")
            
            # Prepare query parameters
            query_params = {}
            # if view_context != "READER":
            query_params["viewContext"] = view_context
            
            # Make API call to get the post
            response = await asyncio.to_thread(
                self.client.get,
                resource_path=f"/posts/{encoded_urn}",
                query_params=query_params if query_params else None,
                version_string=self.version,
                access_token=self.access_token
            )
            
            # Check response status code
            success = response.status_code == 200
            if success:
                response_data = response.entity
                logger.info(f"Successfully retrieved post with URN: {post_urn}")
                return success, response_data
            else:
                logger.error(f"Failed to fetch post with URN {post_urn}. Status: {response.status_code}")
                return False, None
            
        except Exception as e:
            logger.error(f"Error fetching post by URN {post_urn}: {str(e)}")
            return False, None
    
    async def create_post(
        self,
        account_urn: str,
        content: str,
        feed_distribution: str = "MAIN_FEED",  # "NONE", "GROUP_FEED"
        # scheduled_time: Optional[datetime] = None,
        # visibility: str = "PUBLIC"
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Create a new post on LinkedIn.
        
        Args:
            account_urn: LinkedIn account URN (person or organization)
            content: Post text content
            feed_distribution: Feed distribution setting ("MAIN_FEED", "NONE", "GROUP_FEED")
            
        Returns:
            Tuple[bool, Optional[str], Optional[Dict[str, Any]]]: Tuple containing:
                - bool: True if the post was successfully created
                - Optional[str]: LinkedIn post ID if successful, None otherwise
                - Optional[Dict[str, Any]]: Created post entity data if successful, None otherwise
                
        Raises:
            Exception: If there is an error creating the post
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/posts-api
        
        NOTE: doesn't return the created object, only the ID!
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
        
        try:
            # Make API call
            response = await asyncio.to_thread(
                self.client.create,
                resource_path="/posts",
                entity=post_request,
                version_string=self.version,
                access_token=self.access_token
            )
            
            # print("\n\nSTATUS CODE: ", response.status_code)
            # print("\n\nRAW CONTENT: ", response.response.content)
            # print("\n\nENTITY ID: ", response.entity_id)
            # print("\n\nENTITY: ", json.dumps(response.entity, indent=4))
            
            success = response.status_code in [200, 201]
            if success:
                logger.info(f"Successfully created LinkedIn post: {response.entity_id}")
                return success, response.entity_id, response.entity
            else:
                logger.error(f"Failed to create LinkedIn post. Status: {response.status_code}")
                return False, None, None
                
        except Exception as e:
            logger.error(f"Error creating LinkedIn post: {str(e)}")
            raise

    async def create_reshare(
        self,
        account_urn: str,
        reshare_commentary: str,
        post_urn: str,
        feed_distribution: str = "MAIN_FEED",  # "NONE", "GROUP_FEED"
        # scheduled_time: Optional[datetime] = None,
        # visibility: str = "PUBLIC"
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Create a new reshare on LinkedIn.
        
        Args:
            account_urn: LinkedIn account URN (person or organization)
            reshare_commentary: Commentary text for the reshare
            post_urn: URN of the post to reshare
            feed_distribution: Feed distribution setting ("MAIN_FEED", "NONE", "GROUP_FEED")
            
        Returns:
            Tuple[bool, Optional[str], Optional[Dict[str, Any]]]: Tuple containing:
                - bool: True if the reshare was successfully created
                - Optional[str]: LinkedIn reshare ID if successful, None otherwise
                - Optional[Dict[str, Any]]: Created reshare entity data if successful, None otherwise
                
        Raises:
            Exception: If there is an error creating the reshare
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/posts-api
        """
        # Prepare reshare content
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
        
        try:
            # Make API call
            response = await asyncio.to_thread(
                self.client.create,
                resource_path="/posts",
                entity=reshare_post_request,
                version_string=self.version,
                access_token=self.access_token
            )
            
            # print("\n\nSTATUS CODE: ", response.status_code)
            # print("\n\nRAW CONTENT: ", response.response.content)
            # print("\n\nENTITY ID: ", response.entity_id)
            # print("\n\nENTITY: ", json.dumps(response.entity, indent=4))
            
            success = response.status_code in [200, 201]
            if success:
                logger.info(f"Successfully created LinkedIn reshare: {response.entity_id}")
                return success, response.entity_id, response.entity
            else:
                logger.error(f"Failed to create LinkedIn reshare. Status: {response.status_code}")
                return False, None, None
                
        except Exception as e:
            logger.error(f"Error creating LinkedIn reshare: {str(e)}")
            raise
    
    async def delete_post(self, post_urn: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Delete a LinkedIn post.
        
        This method deletes a post from LinkedIn using the post's ID. The post must be
        owned by the authenticated user or an organization that the user has permission to manage.
        
        Args:
            post_urn: LinkedIn post ID (UGC post URN or share URN)
            
        Returns:
            Tuple[bool, Optional[Dict[str, Any]]]: Tuple containing:
                - bool: True if the post was successfully deleted
                - Optional[Dict[str, Any]]: Response entity data if available, None otherwise
            
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
            response = await asyncio.to_thread(
                self.client.delete,
                resource_path=f"/posts/{encoded_urn}",
                version_string=self.version,
                access_token=self.access_token
            )
            
            # print("\n\nSTATUS CODE: ", response.status_code)
            # print("\n\nRAW CONTENT: ", response.response.content)
            # if hasattr(response, 'entity') and response.entity:
            #     print("\n\nENTITY: ", json.dumps(response.entity, indent=4))
            
            # If we reach here without exception, deletion was successful
            success = response.status_code in [200, 204]
            if success:
                logger.info(f"Successfully deleted LinkedIn post: {post_urn}")
            else:
                logger.error(f"Failed to delete LinkedIn post. Status: {response.status_code}")
            
            # Clean up any cached data for this post
            # if self.enable_caching:
            #     try:
            #         # Remove from cache if it exists
            #         await self.cache_result(cache_key, None)
            #     except Exception as cache_error:
            #         logger.warning(f"Failed to clean up cache for deleted post {post_id}: {str(cache_error)}")
            
            return success, getattr(response, 'entity', None)
            
        except Exception as e:
            logger.error(f"Error deleting LinkedIn post {post_urn}: {str(e)}")
            raise
    
    async def get_post_social_actions(
        self,
        post_id: str
    ) -> Tuple[bool, Optional[SocialActionsSummary]]:
        """
        Fetch social actions (likes, comments) for a specific post.
        
        Args:
            post_id: LinkedIn post URN (already formatted as URN)
            
        Returns:
            Tuple[bool, Optional[SocialActionsSummary]]: Tuple containing:
                - bool: True if the social actions were successfully retrieved
                - Optional[SocialActionsSummary]: Summary of social actions on the post if successful, None otherwise
        """
            
        # Make API call if no cached data
        encoded_urn = quote(post_id, safe="")
        
        try:
            response = await asyncio.to_thread(
                self.client.get,
                resource_path=f"/socialActions/{encoded_urn}",
                version_string=self.version,
                access_token=self.access_token
            )
            
            # Check response status code
            success = response.status_code == 200
            if success:
                response_data = response.entity
                
                # Add target field if not present
                if "target" not in response_data:
                    response_data["target"] = post_id
                # print(json.dumps(response_data, indent=4))    
                # Parse response with Pydantic model
                # print(json.dumps(response_data, indent=4))
                social_actions = SocialActionsSummary(**response_data)
                
                logger.info(f"Successfully retrieved social actions for post {post_id}")
                return success, social_actions
            else:
                logger.error(f"Failed to fetch social actions for post {post_id}. Status: {response.status_code}")
                return False, None
            
        except Exception as e:
            logger.error(f"Error fetching social actions for post {post_id}: {str(e)}")
            return False, None
    
    async def batch_get_post_social_actions(
        self,
        post_ids: List[str]
    ) -> Tuple[bool, Optional[Dict[str, SocialActionsSummary]]]:
        """
        Batch fetch social actions for multiple posts.
        
        Args:
            post_ids: List of LinkedIn post URNs
            
        Returns:
            Tuple[bool, Optional[Dict[str, SocialActionsSummary]]]: Tuple containing:
                - bool: True if the social actions were successfully retrieved
                - Optional[Dict[str, SocialActionsSummary]]: Dictionary mapping post URNs to their social actions summaries if successful, None otherwise
        """
            
        # Make API call if no cached data
        try:
            # Prepare batch request with Rest.li batch_get method
            # Format the URNs for batch_get request
            
            response = await asyncio.to_thread(
                self.client.batch_get,
                resource_path="/socialActions",
                ids=post_ids,  # ids_param,  # TODO: check! potentially incorrect escape
                version_string=self.version,
                access_token=self.access_token
            )
            
            # Check response status code
            success = response.status_code == 200
            if success:
                response_data = {"results": response.results}
                # Parse response with Pydantic models
                result = {}
                for post_id, data in response_data.get("results", {}).items():
                    # Add target field if not present
                    if "target" not in data:
                        data["target"] = post_id
                    result[post_id] = SocialActionsSummary(**data)
                
                # Cache the results - convert SocialActionsSummary objects to dicts
                result_dict = {post_id: model.model_dump(by_alias=True) for post_id, model in result.items()}
                
                logger.info(f"Successfully batch retrieved social actions for {len(result)} posts")
                return success, result
            else:
                logger.error(f"Failed to batch fetch social actions. Status: {response.status_code}")
                return False, None
            
        except Exception as e:
            logger.error(f"Error batch fetching social actions: {str(e)}")
            return False, None

    async def batch_get_reactions(
        self,
        actor_entity_pairs: List[tuple[str, str]]
    ) -> Tuple[bool, Optional[List[Reaction]]]:
        """
        Batch fetch reactions for multiple (actor, entity) pairs.
        
        This method retrieves reactions for multiple combinations of actors and entities
        in a single API call, which is more efficient than individual requests.
        
        Args:
            actor_entity_pairs: List of (actor_urn, entity_urn) tuples where:
                               - actor_urn: URN of the person or organization who reacted
                               - entity_urn: URN of the content that was reacted to (post, share, comment, etc.)
            
        Returns:
            Tuple[bool, Optional[List[Reaction]]]: Tuple containing:
                - bool: True if the reactions were successfully retrieved
                - Optional[List[Reaction]]: List of Reaction objects if successful, None otherwise
            
        Raises:
            Exception: If there is an error fetching reactions
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/network-update-social-actions
            
        Example:
            pairs = [
                ("urn:li:person:12345", "urn:li:activity:67890"),
                ("urn:li:organization:11111", "urn:li:ugcPost:22222")
            ]
            reactions = await client.batch_get_reactions(pairs)
            
        Note:
            Only reactions that exist will be included in the results. If a reaction
            doesn't exist for a given (actor, entity) pair, it won't appear in the results.
            The response may also include status codes and errors for each requested pair.
        
        [
            {
                "id": "urn:li:reaction:(urn:li:person:Ijrl-eBf6x,urn:li:activity:7288408229108203520)",
                "last_modified": {
                    "actor": "urn:li:person:Ijrl-eBf6x",
                    "impersonator": null,
                    "time": 1737695015581
                },
                "reaction_type": "LIKE",
                "created": {
                    "actor": "urn:li:person:Ijrl-eBf6x",
                    "impersonator": null,
                    "time": 1737695015581
                },
                "root": "urn:li:activity:7288408229108203520"
            },
            {
                "id": "urn:li:reaction:(urn:li:person:YojiUWre4z,urn:li:activity:7288408229108203520)",
                "last_modified": {
                    "actor": "urn:li:person:YojiUWre4z",
                    "impersonator": null,
                    "time": 1737692298186
                },
                "reaction_type": "INTEREST",
                "created": {
                    "actor": "urn:li:person:YojiUWre4z",
                    "impersonator": null,
                    "time": 1737692298186
                },
                "root": "urn:li:activity:7288408229108203520"
            }
        ]
        """
        # Generate cache key
        pairs_str = "_".join([f"{actor}_{entity}" for actor, entity in sorted(actor_entity_pairs)])
            
        # Make API call if no cached data
        try:
            # Format the IDs for batch_get request
            # Each ID should be a dict with "actor" and "entity" keys
            batch_ids = []
            original_pair_map = {}  # Map from string representation to original pair
            
            for actor_urn, entity_urn in actor_entity_pairs:
                # Create the batch ID format expected by LinkedIn API
                dict_batch_id = {"actor": actor_urn, "entity": entity_urn}
                batch_ids.append(dict_batch_id)
                
                # Store mapping for response parsing - use the string format that appears in response
                string_key = f"(actor:{actor_urn},entity:{entity_urn})"
                original_pair_map[string_key] = (actor_urn, entity_urn)
            
            response = await asyncio.to_thread(
                self.client.batch_get,
                resource_path="/reactions",
                ids=batch_ids,
                version_string=self.version,
                access_token=self.access_token
            )

            # print("\n\nSTATUS: ", response.status_code)
            # print("\n\nRAW_CONTENT: ", response.response.content)
            # print("\n\nRESPONSE RESULTS: ", json.dumps(response.results, indent=4))
            
            # Check response status code
            success = response.status_code == 200
            if success:
                # Parse response
                result = []
                
                # The response.results keys are URL-encoded versions of the batch_ids
                for encoded_key, reaction_data in response.results.items():
                    # URL decode the key to get back the original batch_id format
                    result.append(Reaction(**reaction_data))
                
                logger.info(f"Successfully retrieved {len(result)} reactions from batch request")
                return success, result
            else:
                logger.error(f"Failed to batch fetch reactions. Status: {response.status_code}")
                return False, None
            
        except Exception as e:
            logger.error(f"Error batch fetching reactions: {str(e)}")
            return False, None

    def batch_reactions_to_dict(
        self,
        reactions: Dict[tuple[str, str], Reaction]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Convert batch reactions result to a JSON-serializable dictionary.
        
        This helper method converts the tuple keys from batch_get_reactions to string keys
        that can be JSON serialized, making it easier to work with the results in debugging
        or when sending data to APIs that require JSON.
        
        Args:
            reactions: Result from batch_get_reactions with tuple keys
            
        Returns:
            Dict[str, Dict[str, Any]]: Dictionary with string keys in format "actor_urn|entity_urn"
                                      and reaction data as values
                                      
        Example:
            reactions = await client.batch_get_reactions(pairs)
            json_ready = client.batch_reactions_to_dict(reactions)
        """
        result = {}
        for (actor_urn, entity_urn), reaction in reactions.items():
            # Use pipe separator to avoid conflicts with URN format
            key = f"{actor_urn}|{entity_urn}"
            result[key] = reaction.model_dump(by_alias=True)
        return result
    
    # Organization Share Statistics Methods
    
    async def get_org_share_statistics(
        self,
        request: ShareStatisticsRequest
    ) -> Tuple[bool, Optional[ShareStatisticsResponse]]:
        """
        CRITICAL NOTE: this is only tested with shares of format: urn:li:share:7328113604275142657
        Doesn't seem to work with shares of the format: urn:li:activity:7313213674821730304
        But occationally, also works with not owned organization, eg: Microsoft (not share specific, lifetime or time bound only)!


        Unified method to fetch LinkedIn share statistics for an organization.
        
        This comprehensive method handles all share statistics scenarios:
        - Lifetime statistics (when time_intervals is None)
        - Time-bound statistics (when time_intervals is provided)
        - Statistics for specific posts (when shares or ugc_posts are provided)
        - Combination of time-bound and specific posts
        
        Args:
            request: ShareStatisticsRequest object containing all query parameters
            
        Returns:
            Tuple[bool, Optional[ShareStatisticsResponse]]: Tuple containing:
                - bool: True if the statistics were successfully retrieved
                - Optional[ShareStatisticsResponse]: Share statistics matching the request criteria if successful, None otherwise
            
        Raises:
            Exception: If there is an error fetching the statistics
            ValueError: If the request parameters are invalid
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/share-statistics?view=li-lms-2025-02&tabs=http
            
        Examples:
                         # Lifetime statistics for organization
             request = ShareStatisticsRequest.create_lifetime_request(
                 organizational_entity="urn:li:organization:12345"
             )
             success, stats = await client.get_share_statistics(request)
             
             # Time-bound statistics
             request = ShareStatisticsRequest.create_timebound_request(
                 organizational_entity="urn:li:organization:12345",
                 start_date=datetime(2024, 1, 1),
                 end_date=datetime(2024, 1, 31),
                 granularity="DAY"
             )
             success, stats = await client.get_share_statistics(request)
             
             # Statistics for specific posts
             request = ShareStatisticsRequest.create_posts_request(
                 organizational_entity="urn:li:organization:12345",
                 share_urns=["urn:li:share:123", "urn:li:share:456"],
                 ugc_post_urns=["urn:li:ugcPost:789"]
             )
             success, stats = await client.get_share_statistics(request)
             
             # Time-bound statistics for specific posts
             request = ShareStatisticsRequest.create_timebound_posts_request(
                 organizational_entity="urn:li:organization:12345",
                 start_date=datetime(2024, 1, 1),
                 end_date=datetime(2024, 1, 31),
                 granularity="DAY",
                 ugc_post_urns=["urn:li:ugcPost:789"]
             )
             success, stats = await client.get_share_statistics(request)
            
        Note:
            - This method replaces the need for separate lifetime, time-bound, and post-specific methods
            - The request schema provides validation and convenience methods for common scenarios
            - Time ranges are specified in milliseconds since epoch (automatically converted from datetime)
            - Both shares and ugcPosts can be mixed in the same request
            - The organizational entity must be a valid organization or organization brand URN
        """
        
        try:
            # Validate the request
            
            # Build query parameters for the LinkedIn API call
            query_params = {
                "organizationalEntity": request.organizational_entity
            }
            
            # Add time intervals if provided
            if request.time_intervals:
                time_intervals_dict = {
                    "timeRange": request.time_intervals.time_range.model_dump(exclude_none=True)
                }
                if request.time_intervals.time_granularity_type:
                    time_intervals_dict["timeGranularityType"] = request.time_intervals.time_granularity_type
                    
                query_params["timeIntervals"] = time_intervals_dict
            
            # Add shares if provided
            if request.shares:
                # Format shares as LinkedIn API expects
                shares_list = ','.join([quote(s, safe="") for s in request.shares])
                query_params["shares"] = request.shares  # f"List({shares_list})"
            
            # Add UGC posts if provided
            if request.ugc_posts:
                # Format UGC posts as LinkedIn API expects
                query_params["ugcPosts"] = request.ugc_posts
                # for i, ugc_post_urn in enumerate(request.ugc_posts):
                #     query_params[f"ugcPosts[{i}]"] = ugc_post_urn
            
            # Make API call using Rest.li finder method
            response = await asyncio.to_thread(
                self.client.finder,
                resource_path="/organizationalEntityShareStatistics",
                finder_name="organizationalEntity",
                query_params=query_params,
                version_string=self.version,
                access_token=self.access_token
            )
            
            # Check response status code
            success = response.status_code == 200

            response_data = {"elements": response.elements}

            stats_response = None
            try:
                # Parse response with Pydantic model
                stats_response = ShareStatisticsResponse(**response_data)
            except Exception as e:
                logger.error(f"Error parsing share statistics response: {str(e)}", exc_info=True)
                logger.error(f"Response data: {response_data}")
                logger.error(f"\n\n ++++ Response RAW content: {response.response.content}\n\n")
                success = False
            
            if success:
                # Log successful request details
                request_type = []
                if request.time_intervals:
                    request_type.append("time-bound")
                else:
                    request_type.append("lifetime")
                    
                if request.shares or request.ugc_posts:
                    post_count = (len(request.shares) if request.shares else 0) + \
                            (len(request.ugc_posts) if request.ugc_posts else 0)
                    request_type.append(f"specific posts ({post_count})")
                
                logger.info(
                    f"Successfully retrieved {', '.join(request_type)} share statistics "
                    f"for {request.organizational_entity}: {len(stats_response.elements)} entries"
                )
                
            else:
                logger.error(
                    f"Failed to retrieve share statistics. Status code: {response.status_code}"
                )
            
            return success, stats_response
            
        except Exception as e:
            logger.error(f"Error fetching share statistics: {str(e)}")
            logger.error(f"Request parameters: {request.model_dump(by_alias=True)}")
            raise

    # Organization Follower Statistics Methods
    
    async def get_organization_follower_statistics(
        self,
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAY"
    ) -> Tuple[bool, Optional[FollowerStatisticsResponse]]:
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
            Tuple[bool, Optional[FollowerStatisticsResponse]]: Tuple containing:
                - bool: True if the follower statistics were successfully retrieved
                - Optional[FollowerStatisticsResponse]: Follower statistics for the organization if successful, None otherwise
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/follower-statistics?view=li-lms-2025-02&tabs=http
        """
        
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
            response = await asyncio.to_thread(
                self.client.finder,
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
            
            # Check response status code
            success = response.status_code == 200
            if success:
                response_data = {"elements": response.elements}
                
                # Parse response with Pydantic model
                follower_stats = FollowerStatisticsResponse(**response_data)
                
                logger.info(f"Successfully retrieved follower statistics for organization {organization_id}")
                return success, follower_stats
            else:
                logger.error(f"Failed to fetch follower statistics for organization {organization_id}. Status: {response.status_code}")
                return False, None
            
        except Exception as e:
            logger.error(f"Error fetching follower statistics for organization {organization_id}: {str(e)}")
            return False, None
    
    async def get_organization_follower_count(
        self,
        organization_id: str
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Fetch the current follower count for an organization.
        
        This method retrieves the current total follower count for an organization.
        
        Args:
            organization_id: LinkedIn organization ID
            
        Returns:
            Tuple[bool, Optional[Dict[str, Any]]]: Tuple containing:
                - bool: True if the follower count was successfully retrieved
                - Optional[Dict[str, Any]]: Flattened follower counts dictionary if successful, None otherwise
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/follower-statistics?view=li-lms-2025-02&tabs=http
        """
        
        try:
            org_urn = organization_id  # f"urn:li:organization:{organization_id}"
            # encoded_org_urn = quote(org_urn, safe="")
            
            response = await asyncio.to_thread(
                self.client.finder,
                resource_path=f"/organizationalEntityFollowerStatistics",
                finder_name="organizationalEntity",
                query_params={  # TODO: check!!! manually corrected version
                    # "q": "followingStatistics",  # finder_name added to query params automatically!  // organizationalEntity
                    "organizationalEntity": org_urn,
                },
                version_string=self.version,
                access_token=self.access_token
            )
            
            # Check response status code
            success = response.status_code == 200
            if success:
                response_data = {"elements": response.elements}
                flattened_follower_counts = process_follower_counts(response_data)
                
                # Extract follower count from the response
                # follower_count = 0
                # if "elements" in response_data and len(response_data["elements"]) > 0:
                #     if "followerCounts" in response_data["elements"][0]:
                #         follower_count = response_data["elements"][0]["followerCounts"].get("end", 0)
                
                logger.info(f"Successfully retrieved follower count for organization {organization_id}")
                return success, flattened_follower_counts
            else:
                logger.error(f"Failed to fetch follower count for organization {organization_id}. Status: {response.status_code}")
                return False, None
            
        except Exception as e:
            logger.error(f"Error fetching follower count for organization {organization_id}: {str(e)}")
            return False, None
    
    async def get_post_likes(
        self,
        post_urn: str,
        total_limit: Optional[int] = None,
        elements_per_page: Optional[int] = None,
        start: int = 0
    ) -> Tuple[bool, Optional[List[Like]]]:
        """
        Fetch likes for a specific LinkedIn post, share, or comment.
        
        This method retrieves likes with pagination support using configurable limits.
        
        Args:
            post_urn: LinkedIn post, share, or comment URN  
            total_limit: Maximum total number of likes to return (default: DEFAULT_TOTAL_ELEMENTS_FETCHED_LIMIT)
            elements_per_page: Number of likes to fetch per API call (default: DEFAULT_ELEMENTS_PER_PAGE)
            start: Starting position for pagination (default: 0)
            
        Returns:
            Tuple[bool, Optional[List[Like]]]: Tuple containing:
                - bool: True if the likes were successfully retrieved
                - Optional[List[Like]]: List of likes on the specified content if successful, None otherwise
            
        Raises:
            Exception: If there is an error fetching likes
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/network-update-social-actions
            
        Note:
            - LinkedIn recommends checking social actions summary before fetching likes
            - If no likes exist, the API may return 404 - Not Found
        """
        
        try:
            # URL encode the URN for the API call
            encoded_urn = quote(post_urn, safe="")
            
            # Use helper method for paginated fetching
            likes = await self._paginated_fetch(
                resource_path=f"/socialActions/{encoded_urn}/likes",
                method="get_all",
                response_model_class=LikesResponse,
                total_limit=total_limit,
                elements_per_page=elements_per_page,
                start=start
            )
            
            logger.info(f"Successfully retrieved {len(likes)} likes for post {post_urn}")
            return True, likes
            
        except Exception as e:
            logger.error(f"Error fetching likes for post {post_urn}: {str(e)}")
            return False, None
    
    async def get_post_comments(
        self,
        post_urn: str,
        total_limit: Optional[int] = None,
        elements_per_page: Optional[int] = None,
        start: int = 0
    ) -> Tuple[bool, Optional[List[Comment]]]:
        """
        Fetch comments for a specific LinkedIn post, share, or comment.
        
        This method retrieves comments with pagination support using configurable limits.
        
        Args:
            post_urn: LinkedIn post, share, or comment URN
            total_limit: Maximum total number of comments to return (default: DEFAULT_TOTAL_ELEMENTS_FETCHED_LIMIT)
            elements_per_page: Number of comments to fetch per API call (default: DEFAULT_ELEMENTS_PER_PAGE)
            start: Starting position for pagination (default: 0)
            
        Returns:
            Tuple[bool, Optional[List[Comment]]]: Tuple containing:
                - bool: True if the comments were successfully retrieved
                - Optional[List[Comment]]: List of comments on the specified content if successful, None otherwise
            
        Raises:
            Exception: If there is an error fetching comments
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/network-update-social-actions
            
        Note:
            - LinkedIn recommends checking social actions summary before fetching comments
            - If no comments exist, the API may return 404 - Not Found
            - Top-level comments may include preview of nested comments in commentsSummary
        """
        
        try:
            # URL encode the URN for the API call
            encoded_urn = quote(post_urn, safe="")
            
            # Use helper method for paginated fetching
            comments = await self._paginated_fetch(
                resource_path=f"/socialActions/{encoded_urn}/comments",
                method="get_all",
                response_model_class=CommentsResponse,
                total_limit=total_limit,
                elements_per_page=elements_per_page,
                start=start
            )

            logger.info(f"Successfully retrieved {len(comments)} comments for post {post_urn}")
            return True, comments
            
        except Exception as e:
            logger.error(f"Error fetching comments for post {post_urn}: {str(e)}")
            return False, None
    
    async def get_all_post_likes(
        self,
        post_urn: str,
        elements_per_page: Optional[int] = None
    ) -> Tuple[bool, Optional[List[Like]]]:
        """
        Fetch all likes for a specific LinkedIn post, share, or comment.
        
        This method uses the maximum total limit to retrieve as many likes as possible.
        
        Args:
            post_urn: LinkedIn post, share, or comment URN
            elements_per_page: Number of likes to fetch per API call (default: DEFAULT_ELEMENTS_PER_PAGE)
            
        Returns:
            Tuple[bool, Optional[List[Like]]]: Tuple containing:
                - bool: True if the likes were successfully retrieved
                - Optional[List[Like]]: Complete list of all likes on the specified content (up to MAX_TOTAL_ELEMENTS_FETCHED_LIMIT) if successful, None otherwise
            
        Raises:
            Exception: If there is an error fetching likes
            
        Note:
            - This method uses MAX_TOTAL_ELEMENTS_FETCHED_LIMIT to prevent excessive API calls
            - Consider using get_post_likes() with custom limits for better control
        """
        return await self.get_post_likes(
            post_urn=post_urn,
            total_limit=self.MAX_TOTAL_ELEMENTS_FETCHED_LIMIT,
            elements_per_page=elements_per_page
        )
    
    async def get_all_post_comments(
        self,
        post_urn: str,
        elements_per_page: Optional[int] = None
    ) -> Tuple[bool, Optional[List[Comment]]]:
        """
        Fetch all comments for a specific LinkedIn post, share, or comment.
        
        This method uses the maximum total limit to retrieve as many comments as possible.
        
        Args:
            post_urn: LinkedIn post, share, or comment URN
            elements_per_page: Number of comments to fetch per API call (default: DEFAULT_ELEMENTS_PER_PAGE)
            
        Returns:
            Tuple[bool, Optional[List[Comment]]]: Tuple containing:
                - bool: True if the comments were successfully retrieved
                - Optional[List[Comment]]: Complete list of all comments on the specified content (up to MAX_TOTAL_ELEMENTS_FETCHED_LIMIT) if successful, None otherwise
            
        Raises:
            Exception: If there is an error fetching comments
            
        Note:
            - This method uses MAX_TOTAL_ELEMENTS_FETCHED_LIMIT to prevent excessive API calls
            - Consider using get_post_comments() with custom limits for better control
        """
        return await self.get_post_comments(
            post_urn=post_urn,
            total_limit=self.MAX_TOTAL_ELEMENTS_FETCHED_LIMIT,
            elements_per_page=elements_per_page
        )

    async def get_post_reactions(
        self,
        entity_urn: str,
        limit: Optional[int] = None,
        start: int = 0,
        sort: str = "REVERSE_CHRONOLOGICAL"
    ) -> List[Reaction]:
        """
        Fetch reactions for a specific LinkedIn post, share, or other content.
        
        This method retrieves reactions using LinkedIn's reactions finder API with pagination support.
        Reactions are returned in the specified sort order (newest first by default).
        
        Args:
            entity_urn: LinkedIn entity URN (post, share, etc.) to get reactions for
            limit: Optional maximum number of reactions to return
            start: Starting position for pagination (default: 0)
            sort: Sort order for reactions (default: "REVERSE_CHRONOLOGICAL")
                  - "REVERSE_CHRONOLOGICAL": Sort by created date descending (newest first)
                  - "CHRONOLOGICAL": Sort by created date ascending (oldest first)  
                  - "RELEVANCE": Sort by relevance to the viewer
                  
        Returns:
            List[Reaction]: List of reactions on the specified content
            
        Raises:
            Exception: If there is an error fetching reactions
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/network-update-social-actions
            
        Note:
            - Reaction types include: LIKE, CELEBRATE, SUPPORT, LOVE, INSIGHTFUL, FUNNY
            - The entity URN should be the full URN (e.g., "urn:li:activity:1234567890")
            - Use get_all_post_reactions() to fetch all available reactions
        
        NOTE:
        the below works, but somehow the client doesnt' work!

        curl -X GET 'https://api.linkedin.com/rest/reactions/(entity:urn%3Ali%3Aactivity%3A7313213674821730304)?q=entity&sort=(value:REVERSE_CHRONOLOGICAL)' \
        -H 'X-Restli-Protocol-Version: 2.0.0' \
        -H 'LinkedIn-Version: 202505' \
        -H 'Authorization: Bearer XXXXX'
        
        """
        raise Exception("Not implemented")
        
        # Input validation for sort parameter
        valid_sort_values = ["REVERSE_CHRONOLOGICAL", "CHRONOLOGICAL", "RELEVANCE"]
        if sort not in valid_sort_values:
            raise ValueError(f"Invalid sort value '{sort}'. Must be one of: {valid_sort_values}")
        
        # Prepare query parameters for LinkedIn Reactions API
        query_params = {
            "sort": {
                "value": sort,
            },
            "q": "entity",
        }

        # path_keys={"entity": entity_urn}

        entity_urn_encoded = quote(entity_urn, safe="")
        
        # Determine fetch limit - use limit if provided, otherwise use default
        fetch_limit = limit if limit else self.DEFAULT_TOTAL_ELEMENTS_FETCHED_LIMIT
        
        try:
            # Use _paginated_fetch to get all reactions
            raw_reactions = await self._paginated_fetch(
                resource_path=f"/reactions/(entity:{entity_urn_encoded})",
                method="get_all",
                # finder_name="entity",
                total_limit=fetch_limit,
                start=start,
                query_params=query_params,
                # path_keys=path_keys,
            )
            
            # Convert raw reaction data to Reaction objects
            reactions: List[Reaction] = []
            for reaction_data in raw_reactions:
                reaction = Reaction(**reaction_data)
                reactions.append(reaction)
                
            logger.info(f"Successfully retrieved {len(reactions)} reactions for entity {entity_urn}")
            return reactions
            
        except Exception as e:
            logger.error(f"Error fetching reactions for entity {entity_urn}: {str(e)}")
            raise
    
    async def update_post(
        self,
        post_urn: str,
        commentary: Optional[str] = None,
        content_call_to_action_label: Optional[str] = None,
        content_landing_page: Optional[str] = None,
        lifecycle_state: Optional[str] = None,
        dsc_name: Optional[str] = None,
        dsc_status: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Update an existing LinkedIn post.
        
        This method allows partial updates to specific fields of a LinkedIn post.
        Only the fields provided will be updated; other fields remain unchanged.
        
        Args:
            post_urn: LinkedIn post URN (e.g., "urn:li:ugcPost:12345" or "urn:li:share:67890")
            commentary: Optional updated commentary/text content of the post
            content_call_to_action_label: Optional call to action label (e.g., "LEARN_MORE")
            content_landing_page: Optional URL of the landing page
            lifecycle_state: Optional lifecycle state (typically "PUBLISHED")
            dsc_name: Optional updated name for sponsored content
            dsc_status: Optional updated status for sponsored content
            
        Returns:
            Tuple[bool, Optional[Dict[str, Any]]]: Tuple containing:
                - bool: True if the post was successfully updated
                - Optional[Dict[str, Any]]: Updated post data if successful, None otherwise
            
        Raises:
            Exception: If there is an error updating the post
            ValueError: If no update fields are provided
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api?view=li-lms-2025-05&tabs=http#update-posts
            https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/posts-api
            
        Note:
            - The request uses PARTIAL_UPDATE method with patch format
            - Only provided fields will be updated
            - A successful response returns HTTP 204 (No Content)
            - Lifecycle states: DRAFT, PUBLISHED, PUBLISH_REQUESTED, PUBLISH_FAILED
        """
        # Validate that at least one field is provided for update
        update_fields = [
            commentary, content_call_to_action_label, content_landing_page,
            lifecycle_state, dsc_name, dsc_status
        ]
        if not any(field is not None for field in update_fields):
            raise ValueError("At least one field must be provided for update")
        
        try:
            # Build the patch request body
            partial_update_data = {}
            
            # Add fields to update if they are provided
            if commentary is not None:
                partial_update_data["commentary"] = commentary
            if content_call_to_action_label is not None:
                partial_update_data["contentCallToActionLabel"] = content_call_to_action_label
            if content_landing_page is not None:
                partial_update_data["contentLandingPage"] = content_landing_page
            if lifecycle_state is not None:
                partial_update_data["lifecycleState"] = lifecycle_state
            
            # Handle adContext updates separately if provided
            if dsc_name is not None or dsc_status is not None:
                partial_update_data["adContext"] = {}
                if dsc_name is not None:
                    partial_update_data["adContext"]["dscName"] = dsc_name
                if dsc_status is not None:
                    partial_update_data["adContext"]["dscStatus"] = dsc_status
            
            # URL encode the URN for the API call
            encoded_urn = quote(post_urn, safe="")
            
            # Make API call to update the post
            response = await asyncio.to_thread(
                self.client.partial_update,
                resource_path=f"/posts/{encoded_urn}",
                patch_set_object=partial_update_data,
                version_string=self.version,
                access_token=self.access_token
            )
            
            # print("\n\nSTATUS CODE: ", response.status_code)
            # print("\n\nRAW CONTENT: ", response.response.content)
            # print("\n\nENTITY: ", json.dumps(response.entity, indent=4))
            
            logger.info(f"Successfully updated LinkedIn post: {post_urn}")
            return response.status_code == 204, response.entity
            
        except Exception as e:
            logger.error(f"Error updating LinkedIn post {post_urn}: {str(e)}")
            raise

    async def create_comment(
        self,
        target_urn: str,
        actor_urn: str,
        message_text: str,
        parent_comment_urn: Optional[str] = None,
        content_entities: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[bool, Comment]:
        """
        Create a comment on a LinkedIn post, share, or another comment.
        
        This method creates a new comment on the specified target content. Comments can be
        created on posts, shares, or as replies to other comments (nested comments).
        
        Args:
            target_urn: URN of the target content (post, share, or comment) to comment on
            actor_urn: URN of the entity creating the comment (person or organization)
            message_text: Text content of the comment
            parent_comment_urn: Optional URN of parent comment for nested comments
            content_entities: Optional list of content entities (e.g., images)
                            Format: [{"entity": {"image": "urn:li:image:..."}}]
            
        Returns:
            Tuple[bool, Optional[Dict[str, Any]]]: Tuple containing:
                - bool: True if the comment was successfully created
                - Optional[Dict[str, Any]]: Created comment data if successful, None otherwise
            
        Raises:
            Exception: If there is an error creating the comment
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/network-update-social-actions
            
        Example:
            success, comment_data = await client.create_comment(
                target_urn="urn:li:activity:1234567890",
                actor_urn="urn:li:person:abcdef",
                message_text="Great post! Thanks for sharing.",
                content_entities=[{"entity": {"image": "urn:li:image:xyz123"}}]
            )
            
        Note:
            - Use the returned comment URN for further operations on the comment
            - For nested comments, use the parent comment's URN in parent_comment_urn
            - Images in inline comments may not be supported in all contexts
            - Rate limits apply: 1 minute rate limit for comment creation per member
        
            
        RAW CONTENT:  b'{"actor":"urn:li:organization:102995539","agent":"urn:li:person:NxwL-IvR2n","commentUrn":"urn:li:comment:(urn:li:activity:7339624640027250689,7339624647514083329)","created":{"actor":"urn:li:organization:102995539","impersonator":"urn:li:person:NxwL-IvR2n","time":1749902879600},"id":"7339624647514083329","lastModified":{"actor":"urn:li:organization:102995539","impersonator":"urn:li:person:NxwL-IvR2n","time":1749902879600},"message":{"attributes":[],"text":"Writing test comment, ignore."},"likesSummary":{"selectedLikes":[],"aggregatedTotalLikes":0,"likedByCurrentUser":false,"totalLikes":0},"object":"urn:li:activity:7339624640027250689"}'


        ENTITY:  {
            "actor": "urn:li:organization:102995539",
            "agent": "urn:li:person:NxwL-IvR2n",
            "commentUrn": "urn:li:comment:(urn:li:activity:7339624640027250689,7339624647514083329)",
            "created": {
                "actor": "urn:li:organization:102995539",
                "impersonator": "urn:li:person:NxwL-IvR2n",
                "time": 1749902879600
            },
            "id": "7339624647514083329",
            "lastModified": {
                "actor": "urn:li:organization:102995539",
                "impersonator": "urn:li:person:NxwL-IvR2n",
                "time": 1749902879600
            },
            "message": {
                "attributes": [],
                "text": "Writing test comment, ignore."
            },
            "likesSummary": {
                "selectedLikes": [],
                "aggregatedTotalLikes": 0,
                "likedByCurrentUser": false,
                "totalLikes": 0
            },
            "object": "urn:li:activity:7339624640027250689"
        }
        """
        try:
            # Build the comment request body
            comment_request = {
                "actor": actor_urn,
                "object": target_urn,
                "message": {
                    "text": message_text,
                    "attributes": []  # Can be extended for mentions, formatting, etc.
                }
            }
            
            # Add parent comment for nested comments
            if parent_comment_urn:
                comment_request["parentComment"] = parent_comment_urn
            
            # Add content entities if provided (e.g., images)
            if content_entities:
                comment_request["content"] = content_entities
            
            # URL encode the target URN for the API call
            encoded_target_urn = quote(target_urn, safe="")
            
            # Make API call to create the comment
            response = await asyncio.to_thread(
                self.client.create,
                resource_path=f"/socialActions/{encoded_target_urn}/comments",
                entity=comment_request,
                version_string=self.version,
                access_token=self.access_token
            )
            
            # print("\n\nSTATUS CODE: ", response.status_code)
            # print("\n\nRAW CONTENT: ", response.response.content)
            # print("\n\nENTITY: ", json.dumps(response.entity, indent=4))
            
            # The response entity contains the full comment data
            success = response.status_code in [200, 201]
            if success:
                logger.info(f"Successfully created comment on {target_urn} by {actor_urn}")
                return success, Comment(**response.entity)
            else:
                logger.error(f"Failed to create comment on {target_urn}. Status: {response.status_code}")
                return False, None
            
        except Exception as e:
            logger.error(f"Error creating comment on {target_urn}: {str(e)}")
            raise

    async def update_comment(
        self,
        target_urn: str,
        comment_id: str,
        message_text: str,
        actor_urn: Optional[str] = None,
        message_attributes: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Update an existing comment on a LinkedIn post or share.
        
        This method allows updating the text content and attributes of an existing comment.
        Only the message text and attributes can be modified; other fields are immutable.
        
        Args:
            target_urn: URN of the target content (post or share) containing the comment
            comment_id: ID of the comment to update (not the full comment URN)
            message_text: Updated text content of the comment
            actor_urn: Optional URN of the organization actor (required when editing as organization)
            message_attributes: Optional list of message attributes (mentions, formatting, etc.)
                               Format: [{"start": 0, "length": 5, "value": {...}}]
            
        Returns:
            Tuple[bool, Optional[Dict[str, Any]]]: Tuple containing:
                - bool: True if the comment was successfully updated
                - Optional[Dict[str, Any]]: Updated comment data if successful, None otherwise
            
        Raises:
            Exception: If there is an error updating the comment
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/network-update-social-actions
            
        Example:
            success, updated_comment = await client.update_comment(
                target_urn="urn:li:activity:1234567890",
                comment_id="6915442672119734272",
                message_text="Updated comment message",
                actor_urn="urn:li:organization:12345"
            )
            
        Note:
            - Only message text and attributes can be updated
            - Actor URN is required when editing comments as an organization
            - The comment must be owned by the authenticated user or organization
            - Comment ID is the numeric ID, not the full composite URN
        
        RAW CONTENT:  b'{"actor":"urn:li:organization:102995539","agent":"urn:li:person:NxwL-IvR2n","commentUrn":"urn:li:comment:(urn:li:activity:7339624640027250689,7339624647514083329)","created":{"actor":"urn:li:organization:102995539","impersonator":"urn:li:person:NxwL-IvR2n","time":1749902879600},"id":"7339624647514083329","lastModified":{"actor":"urn:li:organization:102995539","impersonator":"urn:li:person:NxwL-IvR2n","time":1749902929275},"message":{"attributes":[],"text":"Writing test update on comment, ignore."},"likesSummary":{"selectedLikes":[],"aggregatedTotalLikes":0,"likedByCurrentUser":false,"totalLikes":0},"object":"urn:li:activity:7339624640027250689"}'


        ENTITY:  {
            "actor": "urn:li:organization:102995539",
            "agent": "urn:li:person:NxwL-IvR2n",
            "commentUrn": "urn:li:comment:(urn:li:activity:7339624640027250689,7339624647514083329)",
            "created": {
                "actor": "urn:li:organization:102995539",
                "impersonator": "urn:li:person:NxwL-IvR2n",
                "time": 1749902879600
            },
            "id": "7339624647514083329",
            "lastModified": {
                "actor": "urn:li:organization:102995539",
                "impersonator": "urn:li:person:NxwL-IvR2n",
                "time": 1749902929275
            },
            "message": {
                "attributes": [],
                "text": "Writing test update on comment, ignore."
            },
            "likesSummary": {
                "selectedLikes": [],
                "aggregatedTotalLikes": 0,
                "likedByCurrentUser": false,
                "totalLikes": 0
            },
            "object": "urn:li:activity:7339624640027250689"
        }
        """
        try:
            # Build the update request body
            update_request = {
                "message": {
                    "text": message_text,
                }
            }

            if message_attributes:
                update_request["message"]["attributes"] = message_attributes
            
            
            # URL encode the target URN for the API call
            encoded_target_urn = quote(target_urn, safe="")
            # encoded_comment_id = quote(comment_id, safe="")
            
            # Prepare query parameters
            query_params = {}
            if actor_urn:
                query_params["actor"] = actor_urn
            
            # # Make API call to update the comment
            # response = self.client.partial_update(
            #     resource_path=f"/socialActions/{encoded_target_urn}/comments/{comment_id}",
            #     patch_set_object=update_request,
            #     query_params=query_params if query_params else None,
            #     version_string=self.version,
            #     access_token=self.access_token
            # )

            resource_path=f"/socialActions/{encoded_target_urn}/comments/{comment_id}"
            patch_set_object=update_request
            query_params=query_params if query_params else None
            version_string=self.version
            access_token=self.access_token

            encoded_query_param_string = encoder.param_encode(query_params)

            request_body = {
                "patch": {
                    "message": {
                        "$set": update_request["message"]
                    }
                }
            }

            response = await asyncio.to_thread(
                self.client._RestliClient__send_and_format_response,
                restli_method=RESTLI_METHODS.PARTIAL_UPDATE,
                resource_path=resource_path,
                # path_keys=path_keys,
                encoded_query_param_string=encoded_query_param_string,
                request_body=request_body,
                access_token=access_token,
                version_string=version_string,
                formatter=UpdateResponseFormatter,
            )
            
            # print("\n\nSTATUS CODE: ", response.status_code)
            # print("\n\nRAW CONTENT: ", response.response.content)
            # print("\n\nENTITY: ", json.dumps(response.entity, indent=4))
            
            # The response entity contains the updated comment data
            success = response.status_code in [200, 204]
            if success:
                logger.info(f"Successfully updated comment {comment_id} on {target_urn}")
                return success, response.entity
            else:
                logger.error(f"Failed to update comment {comment_id} on {target_urn}. Status: {response.status_code}")
                return False, None
            
        except Exception as e:
            logger.error(f"Error updating comment {comment_id} on {target_urn}: {str(e)}")
            raise

    async def delete_comment(
        self,
        target_urn: str,
        comment_id: str,
        actor_urn: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Delete a comment from a LinkedIn post or share.
        
        This method deletes an existing comment from the specified target content.
        The comment must be owned by the authenticated user or an organization that
        the user has permission to manage.
        
        Args:
            target_urn: URN of the target content (post or share) containing the comment
            comment_id: ID of the comment to delete (not the full comment URN)
            actor_urn: Optional URN of the organization actor (required when deleting as organization)
            
        Returns:
            Tuple[bool, Optional[Dict[str, Any]]]: Tuple containing:
                - bool: True if the comment was successfully deleted
                - Optional[Dict[str, Any]]: Response entity data if available, None otherwise
            
        Raises:
            Exception: If there is an error deleting the comment
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/network-update-social-actions
            
        Example:
            success, response_data = await client.delete_comment(
                target_urn="urn:li:activity:1234567890",
                comment_id="6915442672119734272",
                actor_urn="urn:li:organization:12345"
            )
            
        Note:
            - Actor URN is required when deleting comments as an organization
            - The comment must be owned by the authenticated user or organization
            - Comment ID is the numeric ID, not the full composite URN
            - Successful deletion returns HTTP 204 (No Content)
        """
        try:
            # URL encode the target URN for the API call
            encoded_target_urn = quote(target_urn, safe="")
            encoded_comment_id = quote(comment_id, safe="")
            
            # Prepare query parameters
            query_params = {}
            if actor_urn:
                query_params["actor"] = actor_urn
            
            # Make API call to delete the comment
            response = await asyncio.to_thread(
                self.client.delete,
                resource_path=f"/socialActions/{encoded_target_urn}/comments/{encoded_comment_id}",
                query_params=query_params if query_params else None,
                version_string=self.version,
                access_token=self.access_token
            )
            
            # print("\n\nSTATUS CODE: ", response.status_code)
            # print("\n\nRAW CONTENT: ", response.response.content)
            # if hasattr(response, 'entity') and response.entity:
            #     print("\n\nENTITY: ", json.dumps(response.entity, indent=4))
            
            success = response.status_code in [200, 204]
            if success:
                logger.info(f"Successfully deleted comment {comment_id} from {target_urn}")
            else:
                logger.error(f"Failed to delete comment {comment_id} from {target_urn}. Status: {response.status_code}")
            
            return success, getattr(response, 'entity', None)
            
        except Exception as e:
            logger.error(f"Error deleting comment {comment_id} from {target_urn}: {str(e)}")
            raise

    async def create_like(
        self,
        target_urn: str,
        actor_urn: str,
        object_urn: str
    ) -> Tuple[bool, Optional[Like]]:
        """
        Create a like on a LinkedIn post, share, or comment.
        
        This method creates a new like on the specified target content. Likes can be
        created on posts, shares, or comments by the authenticated user or organization.
        
        Args:
            target_urn: URN of the target content to like (post, share, or comment)
            actor_urn: URN of the entity creating the like (person or organization)
            object_urn: URN of the top-level content being liked (usually the share/post URN)
            
        Returns:
            Tuple[bool, Optional[Like]]: Tuple containing:
                - bool: True if the like was successfully created
                - Optional[Like]: Created like object if successful, None otherwise
            
        Raises:
            Exception: If there is an error creating the like
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/network-update-social-actions
            
        Example:
            # Like a post
            success, like_data = await client.create_like(
                target_urn="urn:li:activity:1234567890",
                actor_urn="urn:li:person:abcdef",
                object_urn="urn:li:share:1234567890"
            )
            
            # Like a comment
            success, like_data = await client.create_like(
                target_urn="urn:li:comment:6915442672119734272",
                actor_urn="urn:li:person:abcdef", 
                object_urn="urn:li:share:1234567890"
            )
            
        Note:
            - The object_urn should typically be the top-level share/post URN
            - The target_urn determines what is being liked (post, share, or comment)
            - Actor can be either a person or organization URN
            - Multiple likes by the same actor on the same content are not allowed
        """
        try:
            # Build the like request body
            like_request = {
                "actor": actor_urn,
                "object": object_urn
            }
            
            # URL encode the target URN for the API call
            encoded_target_urn = quote(target_urn, safe="")
            
            # Make API call to create the like
            response = await asyncio.to_thread(
                self.client.create,
                resource_path=f"/socialActions/{encoded_target_urn}/likes",
                entity=like_request,
                version_string=self.version,
                access_token=self.access_token
            )
            
            # print("\n\nSTATUS CODE: ", response.status_code)
            # print("\n\nRAW CONTENT: ", response.response.content)
            # print("\n\nENTITY: ", json.dumps(response.entity, indent=4))
            
            # The response entity contains the full like data
            success = response.status_code in [200, 201]
            if success:
                logger.info(f"Successfully created like on {target_urn} by {actor_urn}")
                like_obj = Like(**response.entity)
                return success, like_obj
            else:
                logger.error(f"Failed to create like on {target_urn}. Status: {response.status_code}")
                return False, None
            
        except Exception as e:
            logger.error(f"Error creating like on {target_urn}: {str(e)}")
            raise

    async def delete_like(
        self,
        target_urn: str,
        actor_urn: str
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Delete a like from a LinkedIn post, share, or comment.
        
        This method deletes an existing like from the specified target content.
        The like must be owned by the authenticated user or an organization that
        the user has permission to manage.
        
        Args:
            target_urn: URN of the target content containing the like (post, share, or comment)
            actor_urn: URN of the entity that created the like (person or organization)
            
        Returns:
            Tuple[bool, Optional[Dict[str, Any]]]: Tuple containing:
                - bool: True if the like was successfully deleted
                - Optional[Dict[str, Any]]: Response entity data if available, None otherwise
            
        Raises:
            Exception: If there is an error deleting the like
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/network-update-social-actions
            
        Example:
            success, response_data = await client.delete_like(
                target_urn="urn:li:activity:1234567890",
                actor_urn="urn:li:person:abcdef"
            )
            
            # Delete like from a comment
            success, response_data = await client.delete_like(
                target_urn="urn:li:comment:6915442672119734272",
                actor_urn="urn:li:organization:12345"
            )
            
        Note:
            - The actor_urn must match the entity that originally created the like
            - Actor URN is required as both a path parameter and query parameter
            - Successful deletion returns HTTP 204 (No Content)
            - Only the entity that created the like can delete it
        """
        try:
            # URL encode the URNs for the API call
            encoded_target_urn = quote(target_urn, safe="")
            encoded_actor_urn = quote(actor_urn, safe="")
            
            # Prepare query parameters (actor is required)
            query_params = {"actor": actor_urn}
            
            # Make API call to delete the like
            # The actor URN is used both in the path and as a query parameter
            response = await asyncio.to_thread(
                self.client.delete,
                resource_path=f"/socialActions/{encoded_target_urn}/likes/{encoded_actor_urn}",
                query_params=query_params,
                version_string=self.version,
                access_token=self.access_token
            )
            
            # print("\n\nSTATUS CODE: ", response.status_code)
            # print("\n\nRAW CONTENT: ", response.response.content)
            # if hasattr(response, 'entity') and response.entity:
            #     print("\n\nENTITY: ", json.dumps(response.entity, indent=4))
            
            success = response.status_code in [200, 204]
            if success:
                logger.info(f"Successfully deleted like by {actor_urn} from {target_urn}")
            else:
                logger.error(f"Failed to delete like by {actor_urn} from {target_urn}. Status: {response.status_code}")
            
            return success, getattr(response, 'entity', None)
            
        except Exception as e:
            logger.error(f"Error deleting like by {actor_urn} from {target_urn}: {str(e)}")
            raise

    # Member Follower Count Methods
    
    async def get_member_followers_count_lifetime(self) -> Tuple[bool, Optional[int]]:
        """
        Fetch the current lifetime follower count for the authenticated member.
        
        This method retrieves the total number of followers for the authenticated member
        across their entire LinkedIn history.
        
        Returns:
            Tuple[bool, Optional[int]]: Tuple containing:
                - bool: True if the follower count was successfully retrieved
                - Optional[int]: Current lifetime follower count for the member if successful, None otherwise
            
        Raises:
            Exception: If there is an error fetching the follower count
            
        Reference:
            LinkedIn API: GET /rest/memberFollowersCount?q=me
            
        Example:
            follower_count = await client.get_member_followers_count_lifetime()
            # print(f"Total followers: {follower_count}")
            
        Note:
            - This method requires the authenticated member's access token
            - Returns the total accumulated followers count
            - Does not provide historical breakdown
        """
        
        try:
            # Make API call using Rest.li finder method with "me" finder
            response = await asyncio.to_thread(
                self.client.finder,
                resource_path="/memberFollowersCount",
                finder_name="me",
                version_string=self.version,
                access_token=self.access_token
            )
            
            # Check response status code
            success = response.status_code == 200
            if success:
                response_data = {"paging": {"start": response.paging.start, "count": response.paging.count, "total": response.paging.total}, "elements": response.elements}
                
                # Parse response with Pydantic model
                followers_response = MemberFollowersCountResponse(**response_data)
                
                # Extract follower count from the response
                follower_count = 0
                if followers_response.elements:
                    follower_count = followers_response.elements[0].member_followers_count
                
                logger.info(f"Successfully retrieved lifetime follower count: {follower_count}")
                return success, follower_count
            else:
                logger.error(f"Failed to fetch lifetime member follower count. Status: {response.status_code}")
                return False, None
            
        except Exception as e:
            logger.error(f"Error fetching lifetime member follower count: {str(e)}")
            return False, None
    
    async def get_member_followers_count_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Tuple[bool, Optional[List[MemberFollowersCountByDate]]]:
        """
        Fetch member followers count changes within a specific date range.
        
        This method retrieves the follower count changes for the authenticated member
        within the specified date range. The response includes daily breakdowns of
        follower gains/losses during the period.
        
        Args:
            start_date: Start date for the follower count range
            end_date: End date for the follower count range
            
        Returns:
            Tuple[bool, Optional[List[MemberFollowersCountByDate]]]: Tuple containing:
                - bool: True if the follower count changes were successfully retrieved
                - Optional[List[MemberFollowersCountByDate]]: List of follower count changes by date range if successful, None otherwise
            
        Raises:
            Exception: If there is an error fetching the follower count data
            ValueError: If start_date is after end_date
            
        Reference:
            LinkedIn API: GET /rest/memberFollowersCount?q=dateRange&dateRange=...
            
        Example:
            from datetime import datetime, timedelta
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            follower_changes = await client.get_member_followers_count_by_date_range(
                start_date=start_date,
                end_date=end_date
            )
            
            # for change in follower_changes:
            #     print(f"Date: {change.date_range.start.year}-{change.date_range.start.month}-{change.date_range.start.day}")
            #     print(f"Followers change: {change.member_followers_count}")
                
        Note:
            - This method requires the authenticated member's access token
            - Returns daily breakdown of follower changes
            - Negative values indicate follower losses, positive values indicate gains
            - The date range is inclusive of both start and end dates
        """
        
        # Input validation
        if start_date >= end_date:
            raise ValueError("start_date must be before end_date")
        
        try:
            # Prepare date range parameter in LinkedIn's expected format
            date_range_param = {
                "start": {
                    "year": start_date.year,
                    "month": start_date.month,
                    "day": start_date.day
                },
                "end": {
                    "year": end_date.year,
                    "month": end_date.month,
                    "day": end_date.day
                }
            }
            
            # Make API call using Rest.li finder method with "dateRange" finder
            response = await asyncio.to_thread(
                self.client.finder,
                resource_path="/memberFollowersCount",
                finder_name="dateRange",
                query_params={
                    "dateRange": date_range_param
                },
                version_string=self.version,
                access_token=self.access_token
            )
            
            # Check response status code
            success = response.status_code == 200
            if success:
                response_data = {"paging": {"start": response.paging.start, "count": response.paging.count, "total": response.paging.total}, "elements": response.elements}
                
                # Parse response with Pydantic model
                followers_response = MemberFollowersCountByDateResponse(**response_data)
                
                logger.info(f"Successfully retrieved follower count changes for date range: {len(followers_response.elements)} entries")
                return success, followers_response.elements
            else:
                logger.error(f"Failed to fetch member follower count by date range. Status: {response.status_code}")
                return False, None
            
        except Exception as e:
            logger.error(f"Error fetching member follower count by date range: {str(e)}")
            return False, None

    async def get_social_metadata(
        self,
        entity_urn: str
    ) -> Tuple[bool, Optional[SocialMetadata]]:
        """
        Fetch social metadata for a specific LinkedIn content.
        
        This method retrieves aggregated information about reactions and comments
        on a piece of content (post, share, or comment).
        
        Args:
            entity_urn: LinkedIn entity URN (post, share, or comment) to get metadata for
            
        Returns:
            Tuple[bool, Optional[SocialMetadata]]: Tuple containing:
                - bool: True if the social metadata was successfully retrieved
                - Optional[SocialMetadata]: Social metadata for the specified content if successful, None otherwise
            
        Raises:
            Exception: If there is an error fetching social metadata
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/social-metadata
        """
        try:
            # Encode the URN for the URL
            encoded_urn = quote(entity_urn, safe="")
            
            # Make API call
            response = await asyncio.to_thread(
                self.client.get,
                resource_path=f"/socialMetadata/{encoded_urn}",
                version_string=self.version,
                access_token=self.access_token
            )
            
            # Check response status code
            success = response.status_code == 200
            if success:
                # Parse response with Pydantic model
                social_metadata = SocialMetadata(**response.entity)
                logger.info(f"Successfully retrieved social metadata for entity {entity_urn}")
                return success, social_metadata
            else:
                logger.error(f"Failed to fetch social metadata for entity {entity_urn}. Status: {response.status_code}")
                return False, None
            
        except Exception as e:
            logger.error(f"Error fetching social metadata for entity {entity_urn}: {str(e)}")
            return False, None

    async def batch_get_social_metadata(
        self,
        entity_urns: List[str]
    ) -> Tuple[bool, Optional[Dict[str, SocialMetadata]]]:
        """
        Batch fetch social metadata for multiple LinkedIn content items.
        
        This method efficiently retrieves aggregated information about reactions
        and comments for multiple pieces of content in a single API call.
        
        Args:
            entity_urns: List of LinkedIn entity URNs (posts, shares, or comments)
            
        Returns:
            Tuple[bool, Optional[Dict[str, SocialMetadata]]]: Tuple containing:
                - bool: True if the social metadata was successfully retrieved
                - Optional[Dict[str, SocialMetadata]]: Dictionary mapping entity URNs to their social metadata if successful, None otherwise
            
        Raises:
            Exception: If there is an error fetching social metadata
            
        Reference:
            https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/social-metadata
        """
        try:
            
            # Make API call
            response = await asyncio.to_thread(
                self.client.batch_get,
                resource_path="/socialMetadata",
                version_string=self.version,
                access_token=self.access_token,
                ids=entity_urns,
            )
            
            # Check response status code
            success = response.status_code == 200
            if success:
                # Parse response with Pydantic model
                metadata_response = SocialMetadataResponse(results=response.results)
                logger.info(f"Successfully batch retrieved social metadata for {len(metadata_response.results)} entities")
                return success, metadata_response.results
            else:
                logger.error(f"Failed to batch fetch social metadata. Status: {response.status_code}")
                return False, None
            
        except Exception as e:
            logger.error(f"Error batch fetching social metadata for entities: {str(e)}")
            return False, None

