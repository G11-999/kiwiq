"""
LLM Inputs for LinkedIn Selected Topic to Brief Generation Workflow
IMPROVED VERSION with enhanced prompts and reasoning fields

This file contains prompts, schemas, and configurations for the workflow that:
- Takes a user-selected topic from ContentTopicsOutput
- Loads executive profile and content strategy
- Generates a comprehensive LinkedIn content brief
- Allows HITL editing and approval with iteration limits
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

# Import BriefGenerationOutput from the user input to brief file
from .linkedin_user_input_to_brief import BriefGenerationOutput

# =============================================================================
# ENUMS
# =============================================================================

class ContentObjective(str, Enum):
    """Primary objectives for content"""
    BRAND_AWARENESS = "brand_awareness"
    THOUGHT_LEADERSHIP = "thought_leadership"
    ENGAGEMENT = "engagement"
    EDUCATION = "education"
    LEAD_GENERATION = "lead_generation"
    COMMUNITY_BUILDING = "community_building"

class EngagementPriority(str, Enum):
    """Priority levels for engagement tactics"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

# =============================================================================
# INPUT SCHEMAS
# =============================================================================

class ContentTopic(BaseModel):
    """Individual content topic suggestion"""
    title: str = Field(..., description="Suggested content topic/title")
    description: str = Field(..., description="Description of suggested content topic/title")

class ContentTopicsOutput(BaseModel):
    """Content topic suggestions with scheduling and strategic context"""
    suggested_topics: List[ContentTopic] = Field(..., description="List of content topic suggestions")
    scheduled_date: datetime = Field(..., description="Scheduled date for the content in datetime format UTC TZ", format="date-time")
    theme: str = Field(..., description="Content theme this belongs to")
    play_aligned: str = Field(..., description="Which play this aligns with")
    objective: ContentObjective = Field(..., description="Primary objective for this content")
    why_important: str = Field(..., description="Brief explanation of why this topic matters")

# =============================================================================
# OUTPUT SCHEMAS WITH REASONING FIELDS
# =============================================================================

class ContentSectionSchema(BaseModel):
    """Schema for a content section in the brief with reasoning."""
    section_reasoning: str = Field(
        description="Explain why this section is important and how it contributes to the overall content goal"
    )
    section_title: str = Field(description="Title of the content section")
    key_points: List[str] = Field(description="Key points to cover in this section")
    transition_strategy: str = Field(
        description="How this section connects to the previous and next sections for smooth flow"
    )
    audience_hook: str = Field(
        description="Specific element in this section that will resonate with the target audience"
    )
    estimated_word_count: int = Field(description="Estimated word count for this section")

class LinkedInFormattingSchema(BaseModel):
    """Schema for LinkedIn-specific formatting with strategic reasoning."""
    formatting_reasoning: str = Field(
        description="Explain why these formatting choices optimize for LinkedIn's algorithm and user behavior"
    )
    hook_style: str = Field(description="Type of hook for the post")
    hook_psychology: str = Field(
        description="Psychological principle behind the chosen hook style and why it will work"
    )
    emoji_strategy: str = Field(description="How to use emojis effectively")
    emoji_placement_rationale: str = Field(
        description="Specific guidance on where to place emojis for maximum impact without appearing unprofessional"
    )
    hashtag_strategy: str = Field(description="Hashtag recommendations")
    hashtag_mix_reasoning: str = Field(
        description="Balance between trending, niche, and branded hashtags and why this mix"
    )
    formatting_notes: List[str] = Field(description="LinkedIn-specific formatting tips")
    visual_hierarchy_plan: str = Field(
        description="How formatting creates visual hierarchy to improve readability and engagement"
    )



class BriefFeedbackAnalysisSchema(BaseModel):
    """Enhanced schema for brief feedback analysis output."""
    feedback_interpretation: str = Field(
        description="How we understood the user's feedback and main concerns"
    )
    
    revision_reasoning: str = Field(
        description="Strategic reasoning behind the proposed revisions"
    )
    
    revision_instructions: str = Field(
        description="Clear instructions for revising the brief based on feedback"
    )
    
    preserved_elements: List[str] = Field(
        description="Elements from user edits that will be preserved",
        default_factory=list
    )
    
    change_summary: str = Field(
        description="Short, conversational message acknowledging the user's feedback"
    )
    
    impact_assessment: str = Field(
        description="How these changes will improve the content's effectiveness"
    )

# =============================================================================
# ENHANCED SYSTEM PROMPTS
# =============================================================================

BRIEF_GENERATION_SYSTEM_PROMPT = """
You are an elite LinkedIn content strategist with deep expertise in creating viral, high-engagement content for executives. Your role combines strategic thinking, psychological insight, and platform-specific optimization.

YOUR EXPERTISE INCLUDES:
1. **LinkedIn Algorithm Mastery**: You understand how LinkedIn's algorithm prioritizes content based on dwell time, early engagement, and conversation depth.
2. **Executive Positioning**: You craft content that builds thought leadership while maintaining authenticity and approachability.
3. **Audience Psychology**: You know what makes professionals stop scrolling, engage, and share content.
4. **Data-Driven Strategy**: Every recommendation is backed by reasoning about why it will work.

YOUR TASK:
Generate a comprehensive content brief that transforms a selected topic into a high-impact LinkedIn post. The brief must be so detailed and strategic that any competent writer could create exceptional content from it.

KEY PRINCIPLES:
1. **Reasoning First**: Always explain WHY before WHAT. Every tactical choice needs strategic justification.
2. **Audience-Centric**: Frame everything through the lens of "What's in it for the reader?"
3. **Engagement Engineering**: Design content to trigger specific psychological responses and behaviors.
4. **Platform Optimization**: Leverage LinkedIn-specific features and user behaviors.
5. **Measurable Impact**: Connect every element to measurable outcomes.

BRIEF STRUCTURE REQUIREMENTS:
- Start with strategic reasoning that connects the topic to broader business goals
- Include psychological insights about why certain approaches will resonate
- Provide specific, actionable guidance (not generic advice)
- Anticipate potential objections or risks
- Build in conversation catalysts at multiple points
- Design for both immediate engagement and long-term relationship building

IMPORTANT FOCUS AREAS:
1. **The Hook**: The first 2-3 lines determine success. Make them count.
2. **Value Density**: Every paragraph must deliver insight, not filler.
3. **Emotional Journey**: Map the reader's emotional progression through the content.
4. **Social Proof**: Incorporate credibility markers naturally.
5. **Action Triggers**: Multiple micro-commitments leading to the main CTA.

Remember: You're not just creating a brief for content; you're engineering a strategic asset that advances the executive's professional brand and business objectives. Every element should have a clear purpose and expected outcome.

CRITICAL: Focus exclusively on the specific selected topic provided, not the entire list of suggested topics. The brief should fully explore this one topic with depth and nuance.
"""

BRIEF_FEEDBACK_SYSTEM_PROMPT = """
You are an expert LinkedIn content strategist and feedback interpreter with deep experience in iterative content development.

YOUR SPECIALIZED SKILLS:
1. **Feedback Analysis**: You can read between the lines to understand what users really want, even when they don't articulate it clearly.
2. **User Intent Recognition**: You identify the underlying goals behind feedback requests.
3. **Strategic Preservation**: You know what elements to keep, enhance, or replace based on feedback.
4. **Diplomatic Revision**: You make changes that honor user input while maintaining strategic integrity.

YOUR APPROACH TO FEEDBACK:
1. **Respect User Edits**: Any manual changes the user made are intentional and should be preserved unless explicitly contradicted by new feedback.
2. **Build, Don't Replace**: Enhance existing good elements rather than starting over.
3. **Strategic Alignment**: Ensure revisions still serve the original objective and audience.
4. **Clear Communication**: Acknowledge what you understood and what you'll change.

FEEDBACK INTERPRETATION FRAMEWORK:
- **Explicit Requests**: Direct changes the user has asked for
- **Implicit Needs**: Underlying issues the feedback suggests
- **Preserved Elements**: User edits and strong original elements to maintain
- **Strategic Implications**: How changes affect overall content effectiveness

YOUR TASK:
1. Analyze the feedback to understand both explicit requests and implicit needs
2. Identify which parts of the brief need revision while respecting user edits
3. Provide clear, actionable revision instructions that improve the brief
4. Create a friendly message that shows you understood the feedback
5. Assess how the changes will impact content effectiveness

CRITICAL CONSIDERATIONS:
- User edits represent deliberate choices - preserve them unless feedback says otherwise
- Some feedback may conflict with best practices - navigate this diplomatically
- Multiple rounds of feedback should build progressively, not circle back
- Maintain consistency with the executive's voice and brand throughout revisions

Always provide structured output with all required fields, including reasoning about why changes will improve outcomes.
"""

# =============================================================================
# ENHANCED USER PROMPT TEMPLATES
# =============================================================================

BRIEF_GENERATION_USER_PROMPT_TEMPLATE = """
You are creating a strategic LinkedIn content brief for a senior executive. This brief will guide the creation of high-impact content that advances both thought leadership and business objectives.

**SELECTED TOPIC AND STRATEGIC CONTEXT:**
{selected_topic}

Carefully analyze the selected topic above. Note:
- The specific title and description from suggested_topics (this is your focus)
- The strategic theme it belongs to
- The primary objective (brand_awareness, thought_leadership, engagement, etc.)
- Why this topic is important now
- The scheduled publication date

**EXECUTIVE PROFILE AND POSITIONING:**
{executive_profile}

Extract key insights from the profile:
- Unique expertise and credibility markers
- Tone and communication style
- Target audience characteristics and pain points
- Content pillars and areas of authority
- Personal brand attributes to emphasize

**CONTENT STRATEGY & PLAYBOOK:**
{playbook_doc}

Identify relevant guidelines:
- Platform-specific best practices
- Proven content structures and formats
- Engagement tactics that work for this audience
- Success metrics and benchmarks
- Compliance or brand guidelines to follow

**YOUR TASK:**
Create a comprehensive LinkedIn content brief that transforms this selected topic into exceptional content.

**BRIEF REQUIREMENTS:**

1. **STRATEGIC FOUNDATION**
   - Explain WHY this approach will achieve the stated objective
   - Connect the topic to the executive's broader goals
   - Identify the key audience insight we're leveraging
   - Articulate how this content differentiates from competitors

2. **CONTENT ARCHITECTURE**
   - Design a compelling title with reasoning for its effectiveness
   - Choose the optimal content type and format with justification
   - Create a detailed section-by-section structure with:
     * Why each section matters
     * How sections flow together
     * Specific audience hooks within each section
     * Transition strategies between sections

3. **ENGAGEMENT ENGINEERING**
   - Design multiple engagement tactics with:
     * Reasoning for why each will work
     * Implementation timing
     * Expected outcomes
     * Priority levels
   - Include conversation starters that will generate meaningful discussions
   - Plan for both immediate and sustained engagement

4. **LINKEDIN OPTIMIZATION**
   - Formatting strategy with reasoning about algorithm optimization
   - Hook design based on psychological principles
   - Strategic emoji and hashtag usage with clear rationale
   - Visual hierarchy planning for maximum readability

5. **MEASUREMENT & ITERATION**
   - Define success metrics with:
     * Why each metric matters
     * Target values based on benchmarks
     * Measurement timeframes
     * Action thresholds for optimization

6. **RISK MITIGATION & OPPORTUNITIES**
   - Identify potential controversial elements and mitigation strategies
   - Suggest repurposing opportunities for extended value
   - Propose follow-up content to maintain momentum

The brief should be so comprehensive and strategic that:
- Any skilled writer could create exceptional content from it
- Every recommendation has clear reasoning
- The executive understands not just WHAT to write but WHY
- Success metrics are clearly defined and measurable
- The content will stand out in a crowded LinkedIn feed

Remember: This is not just a content brief—it's a strategic blueprint for achieving specific business outcomes through LinkedIn content.
"""

BRIEF_FEEDBACK_INITIAL_USER_PROMPT = """
You are analyzing feedback on a LinkedIn content brief to provide strategic revisions that enhance effectiveness while respecting user intent.

**CRITICAL CONTEXT:** 
The content brief below may contain manual edits from the user. These represent deliberate choices that should be preserved unless the new feedback specifically requests changes to them. Your role is to build upon and enhance, not override, user modifications.

**YOUR ANALYTICAL FRAMEWORK:**

1. **FEEDBACK INTERPRETATION**
   - What is the user explicitly asking for?
   - What underlying needs or concerns does the feedback suggest?
   - What successful elements should be preserved?
   - How do the requests align with LinkedIn best practices?

2. **REVISION STRATEGY**
   - Identify specific sections requiring changes
   - Determine what level of revision is needed (minor tweaks vs. major restructuring)
   - Plan how to incorporate feedback while maintaining strategic integrity
   - Consider the cascade effects of changes on other brief sections

3. **USER EDIT PRESERVATION**
   - Identify any manual modifications in the current brief
   - Understand the intent behind user edits
   - Plan revisions that build upon user changes
   - Flag any conflicts between new feedback and existing edits

---

**CURRENT CONTENT BRIEF:**
{content_brief}

Analyze this brief carefully, noting:
- Structure and flow
- Strategic elements
- Any sections that appear manually edited
- Strong elements to preserve

---

**USER FEEDBACK:**
{revision_feedback}

Interpret this feedback considering:
- Explicit change requests
- Implicit concerns or goals
- Tone and priority indicators
- Alignment with content objectives

---

**STRATEGIC CONTEXT:**

**Selected Topic Details:**
{selected_topic}

Consider how feedback aligns with:
- Original topic intent
- Strategic theme and objective
- Target timeline
- Success metrics

**Executive Profile:**
{executive_profile}

Ensure revisions maintain:
- Executive's authentic voice
- Expertise positioning
- Audience relevance
- Brand consistency

**Content Strategy Guidelines:**
{playbook_doc}

Verify revisions follow:
- Platform best practices
- Proven content patterns
- Engagement strategies
- Compliance requirements

---

**YOUR DELIVERABLES:**

1. **feedback_interpretation**: Clear explanation of how you understood the feedback and main concerns

2. **revision_reasoning**: Strategic rationale for your proposed changes and why they'll improve outcomes

3. **revision_instructions**: Specific, actionable instructions for improving the brief:
   - Exactly what to change in each section
   - What to add or remove
   - How to restructure if needed
   - Specific examples where helpful

4. **preserved_elements**: List of user edits and strong original elements being maintained

5. **change_summary**: Conversational 1-2 sentence acknowledgment (e.g., "Got it! I'll make the tone more conversational and add specific examples from your industry experience.")

6. **impact_assessment**: How these revisions will improve content effectiveness and goal achievement

Ensure your revision instructions are clear enough that they can be implemented without ambiguity, while respecting the user's editorial choices and maintaining strategic alignment.
"""

BRIEF_FEEDBACK_ADDITIONAL_USER_PROMPT = """
The user has provided additional feedback on the revised brief. This represents continued iteration to refine the content strategy.

**ITERATION CONTEXT:**
- This is a follow-up round of feedback
- Previous changes have been implemented
- User may be refining earlier requests or addressing new concerns
- Progressive improvement is the goal - avoid reverting earlier progress

**YOUR ANALYTICAL APPROACH:**

1. **FEEDBACK EVOLUTION**
   - How does this feedback relate to previous requests?
   - Are we refining the same areas or addressing new ones?
   - What indicates the user is satisfied with previous changes?
   - What new priorities have emerged?

2. **CUMULATIVE IMPROVEMENT**
   - Build upon successful previous revisions
   - Don't undo progress unless explicitly requested
   - Look for patterns in feedback evolution
   - Identify if we're converging on the ideal brief

---

**UPDATED BRIEF (Including Previous Revisions):**
{content_brief}

Note what has already been improved and should be maintained.

---

**NEW FEEDBACK:**
{revision_feedback}

Analyze for:
- Refinements to previous changes
- Entirely new concerns
- Satisfaction indicators
- Priority shifts

---

**PROVIDE THE SAME STRUCTURED OUTPUT:**
- feedback_interpretation: Understanding of new feedback in context of iteration history
- revision_reasoning: Why these additional changes will perfect the brief
- revision_instructions: Clear next steps for improvement
- preserved_elements: What's working well and should stay
- change_summary: Brief, friendly acknowledgment of the feedback
- impact_assessment: How we're getting closer to the ideal outcome

Focus on convergence - each iteration should bring us closer to a brief that perfectly balances user vision, strategic objectives, and LinkedIn best practices.
"""

# =============================================================================
# SCHEMA EXPORTS
# =============================================================================

# Convert Pydantic models to JSON schemas for LLM use
BRIEF_GENERATION_OUTPUT_SCHEMA = BriefGenerationOutput.model_json_schema()
BRIEF_FEEDBACK_ANALYSIS_OUTPUT_SCHEMA = BriefFeedbackAnalysisSchema.model_json_schema()

# Input schemas for validation (not for LLM output)
CONTENT_TOPICS_OUTPUT_SCHEMA = ContentTopicsOutput.model_json_schema()
CONTENT_TOPIC_SCHEMA = ContentTopic.model_json_schema()