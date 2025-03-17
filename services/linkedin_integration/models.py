"""
Database models for LinkedIn integration using SQLModel.

This module contains SQLModel models for storing LinkedIn-related data including:
- LinkedIn accounts (both individual and organization)
- Posts and their analytics
- Comments and reactions
- Employee advocacy tracking
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from enum import Enum
from sqlmodel import SQLModel, Field, JSON, Relationship

class AccountType(str, Enum):
    """Enum for LinkedIn account types"""
    INDIVIDUAL = "individual"
    ORGANIZATION = "organization"

class LinkedInAccount(SQLModel, table=True):
    """
    Represents a LinkedIn account (either individual or organization).
    """
    __tablename__ = "linkedin_accounts"

    id: str = Field(primary_key=True)
    linkedin_id: str = Field(unique=True, index=True)
    account_type: AccountType
    access_token: str
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    
    # Profile information
    name: str
    profile_url: Optional[str] = None
    profile_picture_url: Optional[str] = None
    
    # Organization-specific fields
    organization_size: Optional[int] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    
    # Relationships
    posts: List["LinkedInPost"] = Relationship(back_populates="account")
    analytics: List["LinkedInAnalytics"] = Relationship(back_populates="account")

class LinkedInPost(SQLModel, table=True):
    """
    Represents a LinkedIn post with its content and metadata.
    """
    __tablename__ = "linkedin_posts"

    id: str = Field(primary_key=True)
    linkedin_post_id: Optional[str] = Field(unique=True, index=True)  # Null for scheduled posts
    account_id: str = Field(foreign_key="linkedin_accounts.id", index=True)
    
    # Content
    content_text: str
    media_urls: Optional[List[str]] = Field(default=None, sa_type=JSON)
    post_type: str  # text, article, image, video
    
    # Scheduling
    scheduled_time: Optional[datetime] = None
    published_time: Optional[datetime] = None
    is_published: bool = Field(default=False)
    
    # Employee advocacy
    is_advocacy_post: bool = Field(default=False)
    original_post_id: Optional[str] = Field(default=None, foreign_key="linkedin_posts.id")
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Relationships
    account: LinkedInAccount = Relationship(back_populates="posts")
    comments: List["LinkedInComment"] = Relationship(back_populates="post")
    reactions: List["LinkedInReaction"] = Relationship(back_populates="post")
    analytics: Optional["LinkedInPostAnalytics"] = Relationship(back_populates="post")

class LinkedInComment(SQLModel, table=True):
    """
    Represents comments on LinkedIn posts.
    """
    __tablename__ = "linkedin_comments"

    id: str = Field(primary_key=True)
    linkedin_comment_id: str = Field(unique=True, index=True)
    post_id: str = Field(foreign_key="linkedin_posts.id", index=True)
    author_id: str  # LinkedIn URN of commenter
    
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Parent comment for nested comments
    parent_comment_id: Optional[str] = Field(default=None, foreign_key="linkedin_comments.id")
    
    # Relationships
    post: LinkedInPost = Relationship(back_populates="comments")
    replies: List["LinkedInComment"] = Relationship()

class LinkedInReaction(SQLModel, table=True):
    """
    Represents reactions (likes, etc.) on LinkedIn posts.
    """
    __tablename__ = "linkedin_reactions"

    id: str = Field(primary_key=True)
    post_id: str = Field(foreign_key="linkedin_posts.id", index=True)
    actor_id: str  # LinkedIn URN of reactor
    reaction_type: str  # LIKE, CELEBRATE, SUPPORT, FUNNY, LOVE, INSIGHTFUL, CURIOUS
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Relationships
    post: LinkedInPost = Relationship(back_populates="reactions")

class LinkedInAnalytics(SQLModel, table=True):
    """
    Stores account-level analytics for organizations/individuals.
    """
    __tablename__ = "linkedin_analytics"

    id: int = Field(primary_key=True)
    account_id: str = Field(foreign_key="linkedin_accounts.id", index=True)
    date: datetime = Field(index=True)
    
    # Follower metrics
    follower_count: Optional[int] = None
    follower_gain: Optional[int] = None
    
    # Engagement metrics
    engagement_rate: Optional[float] = None
    impressions: Optional[int] = None
    
    # Organization-specific metrics
    page_views: Optional[int] = None
    unique_visitors: Optional[int] = None
    
    # Relationships
    account: LinkedInAccount = Relationship(back_populates="analytics")

class LinkedInPostAnalytics(SQLModel, table=True):
    """
    Stores analytics data for individual posts.
    """
    __tablename__ = "linkedin_post_analytics"

    id: int = Field(primary_key=True)
    post_id: str = Field(foreign_key="linkedin_posts.id", unique=True, index=True)
    
    # Engagement metrics
    impressions: int = Field(default=0)
    clicks: int = Field(default=0)
    reactions_count: int = Field(default=0)
    comments_count: int = Field(default=0)
    shares_count: int = Field(default=0)
    
    # Derived metrics
    engagement_rate: Optional[float] = None
    
    # Time-based metrics
    first_24h_engagement: int = Field(default=0)
    peak_engagement_time: Optional[datetime] = None
    
    # Relationships
    post: LinkedInPost = Relationship(back_populates="analytics")

class EmployeeAdvocacy(SQLModel, table=True):
    """
    Tracks employee advocacy program metrics and participation.
    """
    __tablename__ = "employee_advocacy"

    id: str = Field(primary_key=True)
    organization_id: str = Field(foreign_key="linkedin_accounts.id", index=True)
    employee_id: str = Field(foreign_key="linkedin_accounts.id", index=True)
    
    # Program metrics
    posts_shared: int = Field(default=0)
    total_engagement: int = Field(default=0)
    active_status: bool = Field(default=True)
    
    # Timestamps
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_share_at: Optional[datetime] = None
    
    # Relationships
    # organization: LinkedInAccount = Relationship(back_populates=organization_id)
    # employee: LinkedInAccount = Relationship(back_populates=employee_id) 
