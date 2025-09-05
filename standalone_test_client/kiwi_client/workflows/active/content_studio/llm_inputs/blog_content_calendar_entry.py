from typing import Dict, Any, Optional, List, Union, ClassVar, Type
import json
from enum import Enum

from datetime import date, datetime

# Using Pydantic for easier schema generation
from pydantic import BaseModel, Field


# --- Improved Theme Suggestion Prompts and Schemas ---

THEME_SUGGESTION_SYSTEM_PROMPT = """You are a senior content strategist with deep expertise in content planning and audience engagement. Your role is to strategically select the single most impactful theme for the next blog post based on data-driven insights and content strategy alignment.

Key Responsibilities:
1. Analyze the content playbook to understand play weightages and priorities
2. Review previous topics to identify gaps and opportunities
3. Select themes that balance strategic importance with audience needs
4. Provide actionable research directions for downstream processes
5. Ensure content variety while maintaining strategic focus"""

THEME_SUGGESTION_USER_PROMPT_TEMPLATE = """Select the most strategic theme for the next blog post based on comprehensive analysis.

# Context Documents

## Company Profile
{company_doc}

## Content Strategy Playbook
{playbook}

## Previously Generated Topics
{previous_topics}

# Critical Instructions

## Play Weightage Analysis
The playbook contains different plays/pillars with varying weightages indicating their strategic importance:
- Higher weightage plays should receive MORE topic coverage over time
- Balance immediate audience needs with long-term strategic goals
- Consider the distribution of recent topics across plays

## Previous Topics Context
The previous_topics list contains recently generated topic ideas. Each entry includes:
- **suggested_topics**: List of 4 specific topic suggestions around a common theme
- **theme**: The content pillar/play it belongs to
- **scheduled_date**: When it was/will be published
- **objective**: Primary goal (brand awareness, thought leadership, etc.)

## Theme Selection Criteria
1. **Strategic Alignment**: Choose themes from high-priority plays that haven't been overrepresented recently
2. **Content Gaps**: Identify underserved areas within the content strategy
3. **Audience Timing**: Consider seasonal relevance and current industry trends
4. **Topic Diversity**: Ensure variety in content objectives and depth levels
5. **Research Potential**: Select themes with rich research opportunities

## Research Domain Guidance
For the selected theme, identify specific research domains that will yield valuable insights:
- Industry forums and communities where target audience discusses this theme
- Types of questions they're likely asking (technical, strategic, implementation)
- Competitor content angles to differentiate from
- Emerging sub-topics within this theme

# Required Output
Provide a structured theme selection with clear reasoning and actionable research guidance."""

class ThemeSuggestionOutput(BaseModel):
    """Structured output for theme suggestion with enhanced reasoning and research guidance"""
    
    theme_reasoning: str = Field(
        description="Detailed reasoning explaining why this theme is the optimal choice now, considering play weightages, content gaps, and audience needs"
    )
    
    selected_theme: str = Field(
        description="The specific content theme selected for the next post (must align with a play from the playbook)"
    )
    
    play_alignment: str = Field(
        description="Which strategic play/pillar this theme belongs to and its weightage/priority"
    )
    
    research_domains: List[str] = Field(
        description="3-5 specific domains, platforms, or communities where research should focus (e.g., 'r/ITManagers subreddit', 'Gartner reports on ERP', 'LinkedIn CTO groups')"
    )
    
    research_focus_areas: List[str] = Field(
        description="3-5 specific aspects or questions to investigate during research (e.g., 'implementation challenges', 'ROI concerns', 'vendor selection criteria')"
    )
    
    differentiation_angle: str = Field(
        description="How this theme coverage will differ from typical industry content or our previous coverage"
    )

THEME_SUGGESTION_OUTPUT_SCHEMA = ThemeSuggestionOutput.model_json_schema()

# --- Improved Research Prompts and Schemas ---

RESEARCH_SYSTEM_PROMPT = """You are a content research specialist with expertise in audience intelligence and market analysis. Your research directly informs content creation by uncovering real user perspectives, pain points, and information gaps.

Research Principles:
1. Focus on authentic user voices and real discussions
2. Identify specific questions and concerns, not general topics
3. Uncover unique angles competitors haven't addressed
4. Find timely hooks and trending discussions
5. Validate assumptions with actual user sentiment"""

RESEARCH_USER_PROMPT_TEMPLATE = """Conduct targeted content research to uncover authentic user perspectives and content opportunities.

# Context

## Company Information
{company_doc}

## Content Playbook
{playbook}

## Selected Theme and Research Guidance
{selected_theme}

## Previous Blog Posts (Avoid Repetition)
{previous_posts}

# Research Objectives

## Primary Research Goals
Based on the selected theme and research guidance provided:
1. **User Voice Discovery**: Find actual questions, concerns, and discussions from our target audience
2. **Pain Point Validation**: Identify specific challenges users face related to this theme
3. **Content Gap Analysis**: Discover angles and subtopics competitors haven't adequately covered
4. **Trend Identification**: Spot emerging discussions and timely opportunities

# Research Requirements

## User Perspective Priority
- Prioritize Reddit, Quora, and industry forums where users openly discuss challenges
- Look for questions that indicate knowledge gaps or confusion
- Identify recurring themes in user discussions
- Note emotional language that reveals frustration or excitement

## Differentiation Analysis
- Find angles that haven't been covered in our previous posts
- Identify oversimplified explanations in competitor content we can improve
- Discover niche use cases or edge scenarios worth addressing
- Look for controversial or debated aspects of the theme

## Actionable Insights
Each research finding should:
- Connect directly to our target audience's needs
- Suggest a specific content angle or approach
- Indicate the level of interest/urgency around the topic
- Provide evidence (discussion threads, question frequency, etc.)

# Output Requirements
Structure your research to directly inform topic ideation with specific, actionable insights."""

class ResearchInsight(BaseModel):
    """Individual research insight with reasoning and evidence"""
    finding: str = Field(description="The specific insight or discovery")
    evidence: str = Field(description="Where this was found and why it's credible")
    content_opportunity: str = Field(description="How this translates into a content topic")
    urgency_level: str = Field(description="High/Medium/Low - based on user discussion frequency and intensity")

class ResearchOutput(BaseModel):
    """Comprehensive research output with structured insights"""
    
    research_summary: str = Field(
        description="Executive summary of key research findings and overall user sentiment around the theme"
    )
    
    user_questions: List[str] = Field(
        description="Specific questions users are asking, with context about frequency and platform"
    )
    
    pain_points: List[ResearchInsight] = Field(
        description="Validated pain points with evidence and content opportunities"
    )
    
    trending_discussions: List[ResearchInsight] = Field(
        description="Current hot topics and emerging trends within the theme"
    )
    
    competitive_gaps: List[str] = Field(
        description="Content gaps where competitors haven't provided adequate coverage"
    )
    
    unique_angles: List[str] = Field(
        description="Differentiated perspectives we can take on this theme"
    )
    
    recommended_depth_levels: List[str] = Field(
        description="Suggested content depth for different subtopics (beginner/intermediate/advanced)"
    )

RESEARCH_OUTPUT_SCHEMA = ResearchOutput.model_json_schema()

# --- Improved Topic Generation Prompts ---

TOPIC_SYSTEM_PROMPT_TEMPLATE = """You are an expert blog content strategist specializing in creating compelling, strategic topic ideas that resonate with specific audiences.

# Core Responsibilities
1. Transform research insights into actionable content topics
2. Ensure each topic addresses specific user needs identified in research
3. Create cohesive topic sets that comprehensively cover the selected theme
4. Balance different content depths and formats within each set
5. Optimize for both user value and SEO potential

# Topic Generation Framework

## Topic Set Coherence
- All 4 topics must work together to provide comprehensive theme coverage
- Include a mix of content depths: introductory, intermediate, and advanced
- Vary content formats: how-to, analysis, case study, thought leadership
- Ensure logical progression or complementary perspectives

## User-Centric Approach
- Each topic must address specific questions or pain points from research
- Use language that resonates with the target audience
- Include clear value propositions in titles and descriptions
- Consider the user's journey and information needs

## Strategic Alignment
- Connect each topic to company expertise areas
- Support broader content objectives (thought leadership, lead gen, etc.)
- Include SEO optimization without sacrificing quality
- Build upon but don't duplicate previous content

## Important Context About Previous Topic Ideas
**CRITICAL**: The "Previous Topic Ideas (Avoid Repetition)" section contains topic ideas that users have already reviewed and did NOT approve or like. These are rejected ideas that should be avoided. However, you CAN reuse the scheduled dates from these previous ideas since the dates themselves are not the issue - only the topic content was rejected. For initial topic generation, schedule for TODAY or TOMORROW regardless of what dates appear in previous rejected ideas.

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
   - For initial topic generation: Schedule for TODAY or TOMORROW
   - For additional topic sets: Schedule based on previously suggested dates and posts per week frequency
   - Validate final date is:
     a) Not in the past
     b) Appropriate for the topic generation context (initial vs additional)

# Output Schema
{schema}"""

TOPIC_USER_PROMPT_TEMPLATE = """Generate strategic blog topic suggestions based on research insights and content strategy.

# Context

## Company Profile
{company_doc}

## Content Strategy/Playbook
{playbook}

## Current Date
{current_datetime}

## Selected Theme and Strategic Context
{selected_theme}

## Research Insights
{research_insights}

## Previous Topic Ideas (Avoid Repetition)
**IMPORTANT**: These are topic ideas that users have already reviewed and did NOT like or approve. Avoid these rejected topics completely, but you can use similar scheduled dates since the dates themselves were not the issue - only the topic content was rejected.
{previous_topics}

# Topic Generation Requirements

## Topic Set Composition
Create exactly **4 interconnected topics** for the scheduled date that:

**CRITICAL SCHEDULING REQUIREMENT**: The scheduled date for your topic ideas should be TODAY or TOMORROW ({current_datetime}). Do not schedule posts for dates beyond tomorrow unless specifically generating additional topic sets.

### 1. Comprehensive Theme Coverage
- **Topic 1**: Address the most pressing user question/pain point from research
- **Topic 2**: Provide practical implementation or how-to guidance
- **Topic 3**: Offer strategic/analytical perspective or industry trends
- **Topic 4**: Present case study, success story, or advanced technique

### 2. Research Integration
For each topic, explicitly incorporate:
- Specific user questions or pain points it addresses
- Research insights that informed this topic
- Why this angle hasn't been adequately covered elsewhere
- Expected reader outcome or transformation

### 3. Content Specifications
Each topic must include:
- **reasoning**: Why this specific topic was chosen based on research and strategy
- **title**: SEO-optimized but reader-focused headline
- **description**: Clear explanation of content coverage and value
- **target_audience_segment**: Specific subset of our audience this serves
- **content_depth**: Beginner/Intermediate/Advanced
- **estimated_reading_time**: Based on planned word count
- **primary_cta**: What action we want readers to take

## Strategic Considerations

### Play Alignment
- Ensure topics strongly align with the selected play's objectives
- Consider the play's weightage in overall content strategy
- Support the play's key messages and positioning

### Differentiation
- Leverage unique company expertise and perspectives
- Avoid generic topics covered extensively elsewhere
- Include proprietary insights or methodologies where possible

### SEO Optimization
- Include primary and long-tail keywords naturally
- Consider search intent and user journey stage
- Balance keyword optimization with readability

# Output Format
Provide the complete JSON structure with all required fields, including clear reasoning for each choice."""

# Enhanced Topic Output Schema
class EnhancedContentTopic(BaseModel):
    """Individual blog topic with comprehensive planning details"""
    
    topic_reasoning: str = Field(
        description="Detailed reasoning for selecting this topic based on research insights and strategy, keep it short and concise"
    )
    
    title: str = Field(
        description="SEO-optimized blog post title that clearly conveys value"
    )
    
    description: str = Field(
        description="Comprehensive description of content coverage, main points, and reader value, keep it short and concise"
    )
    
    research_connection: str = Field(
        description="Specific research insights or user questions this topic addresses"
    )
    
    target_audience_segment: str = Field(
        description="Specific audience segment this content serves (e.g., 'CTOs evaluating ERP solutions'), keep it short and concise"
    )

class EnhancedBlogContentTopicsOutput(BaseModel):
    """Enhanced blog content topic suggestions with strategic context"""
    
    topic_set_reasoning: str = Field(
        description="Overall reasoning for this specific set of 4 topics and how they work together"
    )
    
    suggested_topics: List[EnhancedContentTopic] = Field(
        description="List of 4 interconnected blog topic suggestions"
    )
    
    scheduled_date: datetime = Field(
        description="Scheduled publication date in ISO 8601 UTC format",
        format="date-time"
    )
    
    theme: str = Field(
        description="Content theme/pillar this topic set belongs to"
    )
    
    play_aligned: str = Field(
        description="Strategic play this aligns with and its priority/weightage"
    )
    
    objective: str = Field(
        description="Primary objective: brand_awareness/thought_leadership/engagement/education/lead_generation/seo_optimization/product_awareness"
    )
    
    content_journey_stage: str = Field(
        description="Where these topics fit in the reader journey: Awareness/Consideration/Decision/Retention"
    )

TOPIC_LLM_OUTPUT_SCHEMA = EnhancedBlogContentTopicsOutput.model_json_schema()

# --- Additional Theme Prompt for Multiple Iterations ---

THEME_ADDITIONAL_USER_PROMPT_TEMPLATE = """The previously suggested theme has been successfully used to generate blog content. Now you must strategically plan and select the NEXT theme for the content calendar.

# Strategic Context:

## Previously Generated Topics: These are the topics that have already been generated and you can use scheduled_date to check what are the themes that we have used previously. And based on that you can select the next theme.
{previous_topics}

{all_generated_topics}


## Content Planning Status
- The previous theme selection has been completed and blog posts have been generated
- You are now planning the NEXT strategic theme in the content calendar sequence
- This requires strategic thinking to ensure optimal content distribution and audience engagement
- Consider the overall content strategy trajectory and long-term planning goals

# Strategic Theme Selection Requirements

## Play Weightage Consideration
Review the playbook's play weightages and the distribution of already-generated topics:
1. If high-weightage plays are underrepresented, prioritize them
2. Ensure overall topic distribution aligns with strategic priorities
3. Consider cumulative coverage across all generated topics

## Differentiation Requirements
The new theme must:
- Come from a DIFFERENT play/pillar than recently covered themes
- Address different audience segments or needs
- Complement (not duplicate) existing topic coverage
- Fill identified content gaps

## Strategic Planning and Reasoning
Use strategic thinking to determine the optimal NEXT theme by considering:
- **Content Calendar Balance**: How this theme complements and balances the overall content strategy
- **Strategic Gap Analysis**: Which critical gaps in content coverage this theme will address
- **Audience Journey Progression**: How this theme advances the audience through their content journey
- **Timing Optimization**: Why this specific theme is strategically optimal for the next content cycle
- **Competitive Positioning**: How this theme strengthens market positioning and thought leadership
- **Long-term Content Trajectory**: How this theme fits into the broader content planning roadmap

# Required Output
Provide the strategically planned NEXT theme selection with comprehensive reasoning and research guidance. This should demonstrate strategic thinking about content calendar progression and long-term content planning objectives."""

# --- Additional Topic Generation Prompt for Multiple Iterations ---

TOPIC_ADDITIONAL_USER_PROMPT_TEMPLATE = """Generate additional strategic blog topic suggestions for the next iteration, building on research insights and previous topics.

# Context

## Current Date
{current_datetime}

## Selected Theme and Strategic Context for this topic
{selected_theme}

## Research Insights
{research_insights}

# Additional Topic Generation Requirements

## Iteration Context
This is a follow-up iteration to generate more topics. Consider:
- Topics already generated in this session
- Need to maintain theme coherence while avoiding duplication
- Different angles or audience segments within the same theme
- Complementary content depths and formats
- Keep the user's/company context and tone consistent with the playbook

## Scheduling Requirements
CRITICAL: This is a COMPLETELY NEW and SEPARATE topic set that must be scheduled on a DIFFERENT date:
- The previously suggested topic set has already been saved to the calendar
- This new set is the NEXT entry in the content calendar sequence
- MUST use a different date than any previously generated topics in this session
- Never choose a date in the past relative to {current_datetime}
- Never schedule on the same date as previously generated topics
- Use ISO 8601 UTC format (YYYY-MM-DDTHH:MM:SSZ)
- **CRITICAL SCHEDULING LOGIC**: Calculate the next scheduled date based on:
  1. The most recent previously suggested date from this session
  2. The user's posting frequency ({posts_per_week} posts per week)
  3. Appropriate spacing: If 2 posts/week = space 3-4 days apart, if 1 post/week = schedule for the following week
  4. The next date should be the immediate next posting date according to this frequency, not randomly within 2 weeks

## Topic Set Composition
Create exactly **4 new interconnected topics** that:

### 1. Build on Previous Coverage
- **Expand** on angles introduced in earlier topics
- **Deepen** specific aspects that deserve more attention
- **Address** different audience skill levels or roles
- **Complement** existing topics without duplicating content

### 2. Research Integration
For each additional topic, incorporate:
- Underexplored research insights from the initial research phase
- Secondary pain points or questions that weren't addressed
- Advanced or niche aspects of the theme
- Implementation or follow-up content for earlier topics

### 3. Content Specifications
Each topic must include all the same fields as the initial generation:
- **reasoning**: Why this additional topic adds unique value
- **title**: SEO-optimized but reader-focused headline
- **description**: Clear explanation of content coverage and value
- **target_audience_segment**: Specific subset of our audience this serves
- **content_depth**: Beginner/Intermediate/Advanced
- **estimated_reading_time**: Based on planned word count
- **primary_cta**: What action we want readers to take

## Strategic Considerations

### Theme Consistency
- Maintain strong alignment with the selected theme
- Ensure all topics work together as a cohesive content series
- Build logical progression or complementary perspectives

### Audience Value
- Address different user journey stages within the theme
- Provide varying content depths for different experience levels
- Include both strategic and tactical perspectives

### Content Differentiation
- Explore subtopics not covered in initial generation
- Consider different content formats (guides, case studies, analyses)
- Include emerging or advanced aspects of the theme

# Output Format
Provide the complete JSON structure with all required fields, ensuring clear differentiation from previously generated topics while maintaining thematic coherence."""