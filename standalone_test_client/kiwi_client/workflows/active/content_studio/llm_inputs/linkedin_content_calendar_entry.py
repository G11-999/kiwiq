from typing import Dict, Any, Optional, List, Union, ClassVar, Type
import json
from enum import Enum

from datetime import date, datetime

# Using Pydantic for easier schema generation
from pydantic import BaseModel, Field


# --- Content Objective Enum ---
class ContentObjective(str, Enum):
    """Primary objectives for content"""
    BRAND_AWARENESS = "brand_awareness"
    THOUGHT_LEADERSHIP = "thought_leadership"
    ENGAGEMENT = "engagement"
    EDUCATION = "education"
    LEAD_GENERATION = "lead_generation"
    COMMUNITY_BUILDING = "community_building"


TOPIC_USER_PROMPT_TEMPLATE = """Generate content topic suggestions for LinkedIn posts.

**Rules:**
- Do NOT fabricate facts or statistics. Base suggestions on the provided documents and user expertise.
- Use the **exact content pillar names** from the provided `strategy_doc` when assigning themes to topics.
- Generate diverse and unique topic ideas that align with the user's expertise and audience needs.
- Use `merged_posts` to understand the **style, tone, and content themes** that the user typically covers.
- Align suggestions to the **expertise areas and content strategy** from `strategy_doc`, especially:  
  - `foundation_elements.expertise`  
  - `foundation_elements.objectives`
  - `content_pillars`
- Consider the user's `content_goals` from `user_profile` for strategic alignment.

**TIMEZONE AND SCHEDULING REQUIREMENTS:**
1. **Date Selection:**
   - Current Date: {current_datetime}
   - CRITICAL: NEVER select a date that is in the past or before the current date
   - Schedule topics across the **next 2 weeks** (14 days starting from tomorrow)
   - Dates must fall on preferred days listed in `user_profile.posting_schedule.posting_days`
   - Distribute topics evenly across the 2-week period
   - If today is the last day of the week, start from next Monday

2. **Timezone Handling:**
   - Use complete timezone information from `user_timezone`:
     - iana_identifier: Technical timezone code
     - display_name: User-friendly name
     - current_offset: Current offset (including DST if applicable)
     - supports_dst: Whether timezone uses daylight saving time

3. **Optimal Posting Times:**
   - Choose from these peak LinkedIn engagement windows in user's local timezone:
     - **Morning slot**: 8:00 AM - 10:00 AM (peak professional start-of-day activity)
     - **Afternoon slot**: 12:00 PM - 3:00 PM (lunch break and mid-day professional browsing)
   - Select specific time within these windows based on user's audience and industry
   - Convert final scheduled time to UTC using current_offset
   - Account for daylight saving time if supports_dst is true

4. **Output Format:**
   - scheduled_date must be in ISO 8601 UTC format (YYYY-MM-DDTHH:MM:SSZ)
   - Double-check that the generated datetime is:
     a) Not in the past
     b) Within the next 2 weeks
     c) On a preferred posting day
     d) In UTC format

**Context:**
- Content Strategy: {strategy_doc}
- User Timezone Information: {user_timezone}
- Recent User Posts (Drafts/Scraped): {merged_posts}
- Today's Date: {current_datetime}

**Task:**
Create compelling topic suggestions that align with the user's expertise, audience pain points, and content strategy. 

**CRITICAL REQUIREMENTS:**
- Generate exactly **4 topic ideas** for each scheduled date
- All 4 topics must be unified around **one common theme** from the user's content pillars
- The theme must align with a specific **play** from the user's strategy (a "play" is a strategic content approach or pillar from the content strategy)
- Each individual topic should:
  - Be clearly defined with a descriptive **title** and **description**
  - Connect to the user's **areas of expertise** from `strategy_doc.foundation_elements.expertise`
  - Address **audience needs** mentioned in the strategy document
  - Offer a unique angle or perspective within the common theme
  - Complement the other 3 topics to provide comprehensive coverage of the theme
- Have a clear **objective** (brand awareness, thought leadership, etc.) for the entire topic set
- Include explanation of **why this topic matters** to the audience

Respond ONLY with the JSON object matching the specified schema.
"""

TOPIC_SYSTEM_PROMPT_TEMPLATE = """You are an expert LinkedIn content strategist specializing in topic ideation and scheduling.

Your job is to generate high-quality, strategic content topic suggestions using structured user data. You must:

**Content Requirements:**
- NEVER invent facts or statistics. Base all suggestions on information from the documents (`strategy_doc`, `user_profile`, or `merged_posts`).
- Use content pillars exactly as defined in `strategy_doc.content_pillars[*].name` or `strategy_doc.content_pillars[*].pillar`.
- Generate topics that leverage the user's demonstrated expertise from `strategy_doc.foundation_elements.expertise`.
- Address audience needs from `strategy_doc.strategy_audience` and align with `strategy_doc.foundation_elements.objectives`.
- Ensure topics align with the user's `content_goals` from `user_profile`.

**Topic Generation Requirements:**
- Generate exactly **4 topic ideas** for each scheduled date
- All 4 topics must be unified around **one common theme** from the user's content pillars
- Each topic should offer a unique angle or perspective within that common theme
- The theme must align with a specific **play** from the user's content strategy (a "play" is a strategic content approach or pillar)
- Each of the 4 topics should complement each other to provide comprehensive coverage of the theme
- Vary the complexity and depth of topics within the theme
- Consider seasonal relevance and industry trends where applicable
- Ensure the 4 topics work together as a cohesive content set for that scheduled date

**Timezone and Scheduling Requirements:**
1. **Timezone Information Processing:**
   - Process complete timezone information including:
     - iana_identifier: Technical timezone code (e.g., "Europe/London")
     - display_name: User-friendly name (e.g., "British Time - London")  
     - utc_offset: Standard offset (e.g., "+00:00")
     - current_offset: Current offset accounting for DST (e.g., "+01:00")
     - supports_dst: Whether timezone uses daylight saving time

2. **Date Selection:**
   - Current Date: {current_datetime}
   - CRITICAL: NEVER select a date that is in the past or before the current date
   - Schedule topics across the next 2 weeks (14 days starting from tomorrow)
   - Align with user's preferred posting days from user_profile.posting_schedule.posting_days
   - Distribute topics evenly across the 2-week period
   - If today is the last day of the week, start from next Monday
   - Validate final date is:
     a) Not in the past
     b) Within the next 2 weeks
     c) On a preferred posting day

3. **Time Selection:**
   - Select from LinkedIn's peak engagement windows in user's local timezone:
     - **Morning window**: 8:00 AM - 10:00 AM (professionals checking LinkedIn at work start)
     - **Lunch window**: 12:00 PM - 3:00 PM (mid-day professional browsing and lunch break activity)
   - Pick specific time within these windows based on typical LinkedIn activity patterns
   - Convert final scheduling to UTC using current_offset
   - Account for daylight saving time transitions if applicable

4. **Output Format:**
   - scheduled_date must be in ISO 8601 UTC format: YYYY-MM-DDTHH:MM:SSZ
   - Final validation: Ensure the generated datetime is not in the past

Respond strictly with the JSON output conforming to the schema: ```json\n{schema}\n```"""

TOPIC_ADDITIONAL_USER_PROMPT_TEMPLATE = """Generate one additional content topic suggestion.

**CRITICAL REQUIREMENTS:**
- Generate exactly **4 topic ideas** for the scheduled date
- All 4 topics must be unified around **one common theme** from the user's content pillars
- The theme must align with a specific **play** from the user's content strategy
- Each topic should offer a unique angle or perspective within the common theme

Ensure:
- It is distinct in theme and scheduled date from all previously generated suggestions
- It respects all schema fields and draws only from the provided documents (`strategy_doc`, `user_profile`, `merged_posts`)
- It uses a different content pillar/theme from previous suggestions or what best aligns with the user's content strategy
- It has a unique scheduled date that fits within the 2-week planning window
- No invented facts. Base all suggestions on the provided user context

**Example Structure:**
If previous suggestion was "RevOps Education & Best Practices", this could be "Founder Friday" with 4 topics around founder journey insights."""

# --- Pydantic Schemas for LLM Outputs ---

class ContentTopic(BaseModel):
    """Individual content topic suggestion"""
    reasoning: str = Field(..., description="Reasoning for the suggested content topic, keep it short and concise")
    title: str = Field(..., description="Suggested content topic/title")
    description: str = Field(..., description="Description of suggested content topic/title, keep it short and concise")

class ContentTopicsOutput(BaseModel):
    """Content topic suggestions with scheduling and strategic context"""
    suggested_topics: List[ContentTopic] = Field(..., description="List of content topic suggestions")
    scheduled_date: datetime = Field(..., description="Scheduled date for the content in datetime format ISO 8601 UTC", format="date-time")
    theme: str = Field(..., description="Content theme this belongs to")
    play_aligned: str = Field(..., description="Which play this aligns with")
    objective: ContentObjective = Field(..., description="Primary objective for this content")
    why_important: str = Field(..., description="Brief explanation of why this topic matters")


TOPIC_LLM_OUTPUT_SCHEMA = ContentTopicsOutput.model_json_schema()

