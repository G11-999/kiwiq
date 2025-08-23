"""
Onboarding prompt templates and structured output schemas.

This module defines:
- System and user prompt templates for LinkedIn executive profile onboarding and Blog company onboarding
- User-only revision prompt templates for iterative profile refinement based on user feedback
- Pydantic models that represent the expected structured outputs for onboarding
- Exported JSON Schema dictionaries derived from the Pydantic models for use with the LLM node

Design notes:
- We intentionally use Pydantic BaseModels to keep typing strict and readable, while exporting JSON schema dicts via `model_json_schema()`
- These schemas are consumed by the LLM node using `LLMStructuredOutputSchema(schema_definition=...)`
- Initial onboarding system prompts contain all task instructions, research guidance, and output requirements
- Initial onboarding user prompts contain only input data and context to minimize token usage and improve clarity
- The prompts include comprehensive research instructions for cases where additional context is insufficient
- Revision prompts are user-only and contain all necessary instructions inline
- Enums are used for standardized fields like posting days and company sizes for consistency

Available prompt templates:
- LINKEDIN_ONBOARDING_SYSTEM_PROMPT / LINKEDIN_ONBOARDING_USER_PROMPT: Initial LinkedIn profile creation
- BLOG_ONBOARDING_SYSTEM_PROMPT / BLOG_ONBOARDING_USER_PROMPT: Initial blog company profile creation  
- LINKEDIN_ONBOARDING_REVISION_USER_PROMPT: LinkedIn profile revisions
- BLOG_ONBOARDING_REVISION_USER_PROMPT: Blog company profile revisions
"""
from __future__ import annotations

from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl


# ================================
# Enums for Standardized Values
# ================================

class WeekDay(str, Enum):
    """Standardized weekday values for posting schedules."""
    MONDAY = "monday"
    TUESDAY = "tuesday" 
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"



# ================================
# LinkedIn Executive Profile Schema
# ================================

class ContentGoals(BaseModel):
    """Captures the primary and secondary content creation goals for LinkedIn strategy.
    
    These goals drive content planning and should be specific, measurable outcomes
    the executive wants to achieve through their LinkedIn presence.
    """
    primary_goal: Optional[str] = Field(
        None, 
        description="The main objective for LinkedIn content (e.g., 'Build thought leadership in AI/ML space', 'Generate qualified leads for consulting services')"
    )
    secondary_goal: Optional[str] = Field(
        None,
        description="Secondary content objective that supports the primary goal (e.g., 'Increase brand awareness', 'Network with industry peers')"
    )

class PostingSchedule(BaseModel):
    """Defines the LinkedIn posting cadence and timing preferences for content automation.
    
    This schedule will be used by content planning and publishing systems to optimize
    engagement and maintain consistent presence.
    """
    posts_per_week: int = Field(
        default=0,
        description="Number of posts to publish per week (0-14 range for practical limits)"
    )
    posting_days: List[WeekDay] = Field(
        default_factory=list,
        description="Preferred days of the week for posting content"
    )
    exclude_weekends: bool = Field(
        default=False,
        description="Whether to avoid posting on Saturday and Sunday"
    )

class Timezone(BaseModel):
    """IANA timezone configuration for scheduling content at optimal times.
    
    Critical for ensuring posts go live when the target audience is most active.
    All scheduling systems should use the IANA identifier as the source of truth.
    """
    iana_identifier: str = Field(
        default="",
        description="IANA timezone identifier (e.g., 'America/New_York', 'Europe/London')"
    )
    display_name: str = Field(
        default="",
        description="Human-readable timezone name for UI display (e.g., 'Eastern Time', 'GMT')"
    )
    utc_offset: str = Field(
        default="",
        description="Current UTC offset in format '+/-HH:MM' (e.g., '-05:00', '+01:00')"
    )
    supports_dst: bool = Field(
        default=False,
        description="Whether this timezone observes Daylight Saving Time"
    )
    current_offset: str = Field(
        default="",
        description="Current offset accounting for DST if applicable"
    )

class LinkedInProfileDocument(BaseModel):
    """Complete LinkedIn executive profile for content automation and strategy.
    
    This document serves as the foundation for all LinkedIn content generation,
    scheduling, and personalization. It should capture the executive's professional
    brand, goals, and preferences comprehensively.
    """
    profile_url: HttpUrl = Field(
        description="Valid LinkedIn profile URL (e.g., 'https://www.linkedin.com/in/username/')"
    )
    username: Optional[str] = Field(
        None,
        description="LinkedIn username/handle extracted from profile URL"
    )
    persona_tags: Optional[List[str]] = Field(
        None,
        description="Professional persona keywords that define the executive's brand (e.g., ['AI Expert', 'Tech Leader', 'Startup Advisor'])"
    )
    content_goals: Optional[ContentGoals] = Field(
        None,
        description="Strategic objectives for LinkedIn content creation"
    )
    posting_schedule: Optional[PostingSchedule] = Field(
        None,
        description="Preferred timing and frequency for content publication"
    )
    timezone: Optional[Timezone] = Field(
        None,
        description="Timezone configuration for optimal content scheduling"
    )


# Export JSON schema for LLM structured output (as a plain dict)
LINKEDIN_PROFILE_SCHEMA = LinkedInProfileDocument.model_json_schema()


# =========================
# Blog Company Profile Schema
# =========================

class ICP(BaseModel):
    """Ideal Customer Profile (ICP) defining the company's target market for content strategy.
    
    This profile guides all blog content creation to ensure relevance and engagement
    with the most valuable prospects and customers.
    """
    icp_name: str = Field(
        description="Descriptive name for this ICP segment (e.g., 'Mid-market SaaS CTOs', 'Healthcare IT Directors')"
    )
    target_industry: Optional[str] = Field(
        None,
        description="Primary industry vertical this ICP operates in (e.g., 'Technology', 'Healthcare', 'Finance', 'Manufacturing', 'Education', 'Consulting', 'Real Estate')"
    )
    company_size: Optional[str] = Field(
        None,
        description="Typical company size range for this ICP as employee count (e.g., '1-10 employees', '50-200 employees', '500-1000 employees', '1000+ employees')"
    )
    buyer_persona: Optional[str] = Field(
        None,
        description="Detailed buyer persona including role, responsibilities, and decision-making authority (e.g., 'VP of Engineering at 100-500 person tech companies, responsible for infrastructure decisions')"
    )
    pain_points: Optional[List[str]] = Field(
        None,
        description="Key challenges and pain points this ICP faces that our content should address"
    )

# class ContentDistributionMix(BaseModel):
#     """Content marketing funnel distribution strategy defining what percentage of content 
#     should target each stage of the customer journey.
    
#     This mix ensures balanced content that nurtures prospects from awareness through retention.
#     Total percentages may not sum to 100% if some stages are not prioritized.
#     """
#     awareness_percent: Optional[float] = Field(
#         None, 
#         ge=0, 
#         le=100,
#         description="Percentage of content focused on brand awareness and top-of-funnel education (0-100%)"
#     )
#     consideration_percent: Optional[float] = Field(
#         None, 
#         ge=0, 
#         le=100,
#         description="Percentage of content for prospects evaluating solutions (0-100%)"
#     )
#     purchase_percent: Optional[float] = Field(
#         None, 
#         ge=0, 
#         le=100,
#         description="Percentage of content supporting purchase decisions and conversion (0-100%)"
#     )
#     retention_percent: Optional[float] = Field(
#         None, 
#         ge=0, 
#         le=100,
#         description="Percentage of content for existing customers focused on retention and expansion (0-100%)"
#     )

class Competitor(BaseModel):
    """Competitive intelligence for content differentiation and market positioning.
    
    Understanding competitors helps create unique content angles and identify content gaps.
    """
    website_url: Optional[HttpUrl] = Field(
        None,
        description="Competitor's primary website URL for content analysis"
    )
    name: Optional[str] = Field(
        None,
        description="Competitor company name"
    )

class CompanyPostingSchedule(BaseModel):
    """Blog publishing cadence for consistent content delivery and audience engagement.
    
    Regular publishing schedules improve SEO performance and audience retention.
    """
    posts_per_month: int = Field(
        default=4,
        description="Target number of blog posts to publish per month (1-31 range)"
    )

class CompanyDocument(BaseModel):
    """Complete company profile for blog content strategy and automation.
    
    This document provides the foundation for all blog content planning, creation,
    and distribution. It should capture the company's market position, audience,
    and content objectives comprehensively.
    """
    name: str = Field(
        description="Official company name as it appears in marketing materials"
    )
    website_url: HttpUrl = Field(
        description="Company's primary website URL (canonical root domain)"
    )
    value_proposition: Optional[str] = Field(
        None,
        description="Clear, concise statement of the unique value the company provides to customers (1-2 sentences)"
    )
    icps: Optional[ICP] = Field(
        None,
        description="Primary ideal customer profile for content targeting"
    )
    competitors: Optional[List[Competitor]] = Field(
        None,
        description="Key competitors for market positioning and content differentiation"
    )
    goals: Optional[List[str]] = Field(
        None,
        description="Primary business objectives the blog content should support (e.g., 'Generate 50 qualified leads per month', 'Establish thought leadership in AI space')"
    )
    posting_schedule: Optional[CompanyPostingSchedule] = Field(
        None,
        description="Target publishing frequency and cadence"
    )


# Export JSON schema for LLM structured output (as a plain dict)
BLOG_COMPANY_PROFILE_SCHEMA = CompanyDocument.model_json_schema()


# =========================
# Prompt Templates (LinkedIn)
# =========================

LINKEDIN_ONBOARDING_SYSTEM_PROMPT = """You are an expert LinkedIn content strategist and executive onboarding specialist. Your role is to create comprehensive LinkedIn profiles for executives entering a content automation system.

CRITICAL INSTRUCTIONS:
1. **Use Additional Context**: If additional_context is provided, prioritize this information heavily. Use it to fill schema fields directly rather than making assumptions or generating generic content.

2. **Research When Context is Insufficient**: If additional_context doesn't contain sufficient information to populate the profile fields, you must actively research and infer details based on:
   - LinkedIn profile analysis (if accessible via the profile URL)
   - Industry standards for similar executive roles
   - Company context and industry positioning
   - Professional networking patterns and content consumption habits
   - Geographic and temporal factors affecting optimal posting times

3. **Supplement Missing Information**: Even when additional_context provides partial information for complex objects, you must research and supplement ALL missing subfields and subschemas. For example:
   - If context mentions "posts 3 times a week" but doesn't specify days, research optimal posting days for the executive's industry/timezone
   - If context mentions "tech executive" but lacks specific persona tags, research and add relevant expertise areas (e.g., "AI/ML Expert", "SaaS Leader")
   - If context provides location but no timezone details, research and populate complete timezone information with IANA identifier, UTC offset, and DST support
   - If content goals are mentioned generally, research industry-specific objectives and make them actionable and measurable

4. **Output Format**: Produce STRICT JSON that exactly matches the provided schema. No commentary, explanations, or additional text.

5. **Data Quality**: Create actionable, specific content that will drive real LinkedIn engagement and business results.

6. **Professional Standards**: Ensure all content reflects executive-level professionalism and strategic thinking.

TASK REQUIREMENTS:
**Focus Areas for Profile Creation:**
1. **Persona Tags**: Extract or infer professional identity, expertise areas, and industry focus from available information
2. **Content Goals**: Identify primary business objectives for LinkedIn presence (thought leadership, lead generation, networking, etc.) based on executive role and industry context
3. **Posting Schedule**: Set realistic posting frequency and preferred days based on executive availability and industry engagement patterns
4. **Timezone**: Determine appropriate timezone for optimal posting times based on geographic location and target audience

**Research Guidelines When Additional Context is Limited:**
- Analyze the LinkedIn profile URL and username for professional context clues
- Consider industry-specific content consumption patterns and optimal posting times
- Infer executive-level responsibilities and strategic priorities based on role indicators
- Research typical content goals for executives in similar positions/industries
- Apply best practices for executive social media presence and engagement optimization

SCHEMA ADHERENCE:
- Follow all field types, constraints, and enum values exactly
- Use null for truly unknown fields rather than placeholder text
- Ensure URLs are properly formatted and valid
- Make posting schedules realistic and sustainable (typically 1-5 posts per week for executives)

OUTPUT REQUIREMENTS:
- Valid JSON matching the LinkedInProfileDocument schema exactly
- Specific, actionable content goals that drive business results
- Realistic posting schedules aligned with executive capacity
- Professional persona tags that reflect expertise and market position
- Proper timezone configuration for scheduling optimization

When additional context is provided, extract relevant information to populate:
- persona_tags (from role, expertise, industry mentions)
- content_goals (from business objectives, target outcomes)
- posting_schedule (from availability, preferences, current habits)
- timezone (from location, schedule preferences)"""

LINKEDIN_ONBOARDING_USER_PROMPT = """Create a comprehensive LinkedIn executive profile for content automation based on the following input data:

**INPUT DATA:**
- Username: {entity_username}
- Profile URL: {linkedin_profile_url}
- Additional Context: {additional_context}
"""

# ======================
# Prompt Templates (Blog)
# ======================

BLOG_ONBOARDING_SYSTEM_PROMPT = """You are an expert content marketing strategist and company onboarding specialist. Your role is to create comprehensive company profiles for businesses entering a blog content automation system.

CRITICAL INSTRUCTIONS:
1. **Use Additional Context**: If additional_context is provided, prioritize this information heavily. Use it to fill schema fields directly rather than making assumptions or generating generic content.

2. **Research When Context is Insufficient**: If additional_context doesn't contain sufficient information to populate the company profile fields, you must actively research and infer details based on:
   - Company website analysis (if accessible via the website URL)
   - Industry research and market positioning analysis
   - Competitive landscape research for similar companies
   - Market segment analysis and buyer persona development
   - Content marketing best practices for the specific industry vertical
   - Business model analysis to determine appropriate content goals and distribution strategies

3. **Supplement Missing Information**: Even when additional_context provides partial information for complex objects, you must research and supplement ALL missing subfields and subschemas. For example:
   - If context mentions "B2B SaaS company" but lacks specific ICP details, research typical buyer personas, company sizes, and pain points for that market
   - If context provides industry but no competitors, research and identify key competitive players with websites
   - If context mentions "lead generation" as a goal but lacks specificity, research industry-standard metrics and make goals measurable (e.g., "Generate 50 qualified MQLs per month")
   - If context provides company size hint but no detailed ICP, research target market segments and populate complete buyer persona details
   - If posting frequency is mentioned but not specific cadence, research optimal publishing schedules for the industry and company size

4. **Output Format**: Produce STRICT JSON that exactly matches the provided schema. No commentary, explanations, or additional text.

5. **Strategic Focus**: Create data-driven content strategies that align with business objectives and target market needs.

6. **Market Intelligence**: Develop realistic ICPs and competitive positioning based on available information.

TASK REQUIREMENTS:
**Focus Areas for Company Profile Creation:**
1. **Value Proposition**: Clear, differentiated value statement that resonates with target customers, based on company positioning and market analysis
2. **Ideal Customer Profile**: Detailed profile of the primary target market including industry, company size, buyer persona, and pain points derived from market research
3. **Competitive Intelligence**: Key competitors for positioning and differentiation identified through industry analysis
4. **Business Goals**: Specific, measurable objectives the blog should support, aligned with typical business outcomes for companies in similar markets
5. **Publishing Schedule**: Sustainable content cadence aligned with resource capacity and industry engagement patterns

**Research Guidelines When Additional Context is Limited:**
- Analyze the company website URL for business model, target market, and value proposition clues
- Research the industry vertical to understand typical customer profiles and pain points
- Identify key competitors through market analysis and positioning research
- Infer business goals based on company stage, market segment, and typical content marketing objectives
- Apply content marketing best practices specific to the company's industry and target market
- Consider resource constraints and realistic publishing capabilities for companies of similar size/stage

SCHEMA ADHERENCE:
- Follow all field types, constraints, and enum values exactly
- Use null for truly unknown fields rather than placeholder text
- Ensure URLs are properly formatted and valid
- Make posting schedules sustainable and aligned with content marketing best practices (typically 2-8 posts per month)

OUTPUT REQUIREMENTS:
- Valid JSON matching the CompanyDocument schema exactly
- Specific, actionable business goals that content can measurably support
- Realistic posting schedules aligned with typical resource capacity
- Detailed ICP with clear targeting criteria and pain points based on market research
- Strategic competitive positioning that creates content differentiation opportunities

When additional context is provided, extract relevant information to populate:
- value_proposition (from company descriptions, mission statements)
- icps (from target customer descriptions, market segments)
- competitors (from competitive landscape mentions)
- goals (from business objectives, marketing targets)"""

BLOG_ONBOARDING_USER_PROMPT = """Create a comprehensive company profile for blog content automation and strategy based on the following input data:

**INPUT DATA:**
- Company Name: {company_name}
- Website URL: {company_url}
- Additional Context: {additional_context}
"""


# =============================
# Revision Prompt Templates
# =============================

LINKEDIN_ONBOARDING_REVISION_USER_PROMPT = """Revise the LinkedIn executive profile based on user feedback.

You will be given the current profile JSON and revision feedback. Update ONLY the fields that the feedback requests to change. Preserve all other fields exactly as-is unless the feedback explicitly requires adjustments. Continue to prioritize any Additional Context if present.

Revision Feedback:
{revision_feedback}
"""

BLOG_ONBOARDING_REVISION_USER_PROMPT = """Revise the company blog profile based on user feedback.

You will be given the current company profile JSON and revision feedback. Update ONLY the fields that the feedback requests to change. Preserve all other fields exactly as-is unless the feedback explicitly requires adjustments. Continue to prioritize any Additional Context if present.

Revision Feedback:
{revision_feedback}
"""
