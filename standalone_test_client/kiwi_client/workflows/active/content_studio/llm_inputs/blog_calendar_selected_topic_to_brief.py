"""
Enhanced LLM Inputs for Selected Topic to Brief Generation Workflow

This file contains enhanced prompts, schemas, and configurations for the workflow that:
- Takes a user-selected topic from ContentTopicsOutput
- Loads company context
- Performs web research (Google and Reddit)
- Generates a comprehensive content brief with detailed reasoning
- Allows HITL editing and approval with iteration limits
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from .blog_user_input_to_brief import ContentBriefDetailSchema

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

class ContentType(str, Enum):
    """Types of content based on playbook"""
    THOUGHT_LEADERSHIP = "thought_leadership"
    HOW_TO_GUIDE = "how_to_guide"
    CASE_STUDY = "case_study"
    INDUSTRY_ANALYSIS = "industry_analysis"
    PRODUCT_EDUCATION = "product_education"
    BEST_PRACTICES = "best_practices"

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
# WEB RESEARCH OUTPUT SCHEMAS
# =============================================================================

class GoogleSearchInsight(BaseModel):
    """Individual insight from Google search"""
    insight: str = Field(description="Key insight or finding from search results")
    source_url: str = Field(description="URL where this insight was found")
    relevance_score: str = Field(description="High/Medium/Low relevance to topic")
    how_to_use: str = Field(description="How this insight should inform the content")

class GoogleResearchOutput(BaseModel):
    """Output from Google research phase"""
    search_queries_used: List[str] = Field(description="Search queries that yielded results")
    trending_subtopics: List[str] = Field(description="Related trending topics in this space")
    competitor_angles: List[str] = Field(description="How competitors approach this topic")
    content_gaps: List[str] = Field(description="Gaps in existing content that we can fill")
    key_statistics: List[str] = Field(description="Important statistics with sources")
    expert_opinions: List[str] = Field(description="Expert quotes and opinions with attribution")
    common_questions: List[str] = Field(description="Frequently asked questions about this topic")
    insights: List[GoogleSearchInsight] = Field(description="Detailed insights from search")
    research_summary: str = Field(description="Executive summary of Google research findings")

class RedditDiscussion(BaseModel):
    """Individual Reddit discussion point"""
    discussion_point: str = Field(description="Key point from Reddit discussions")
    sentiment: str = Field(description="Positive/Negative/Neutral sentiment")
    user_pain_point: str = Field(description="Underlying pain point or need expressed")
    community_source: str = Field(description="Which subreddit or community this came from")

class RedditResearchOutput(BaseModel):
    """Output from Reddit research phase"""
    relevant_communities: List[str] = Field(description="Reddit communities discussing this topic")
    user_language_patterns: List[str] = Field(description="How users actually talk about this topic")
    common_misconceptions: List[str] = Field(description="Misconceptions to address in content")
    real_world_examples: List[str] = Field(description="User-shared examples and case studies")
    emotional_triggers: List[str] = Field(description="What emotionally resonates with users")
    objections_and_concerns: List[str] = Field(description="Common objections to address")
    success_stories: List[str] = Field(description="User success stories related to topic")
    discussions: List[RedditDiscussion] = Field(description="Key discussion points from Reddit")
    community_insights_summary: str = Field(description="Summary of community insights")

# =============================================================================
# ENHANCED OUTPUT SCHEMAS WITH REASONING
# =============================================================================

class ContentSectionSchema(BaseModel):
    """Enhanced schema for a content section in the brief."""
    section_reasoning: str = Field(description="REASONING: Why this section is essential based on research and strategy")
    section: str = Field(description="Name of the content section")
    description: str = Field(description="Detailed description of what should be covered in this section")
    word_count: int = Field(description="Estimated word count for this section")
    key_points_to_cover: List[str] = Field(description="Specific points that must be covered in this section")
    research_support: List[str] = Field(description="ALL relevant research findings, data points, statistics, expert quotes, user insights, and source information from Google/Reddit that should be referenced when writing this section. Include everything from the research that will help create comprehensive, well-supported content")
    user_questions_answered: List[str] = Field(description="User questions from research that this section addresses")
    playbook_alignment: str = Field(description="How this section aligns with playbook guidelines")
    data_to_include: List[str] = Field(description="Specific statistics or data points to include")
    examples_to_use: List[str] = Field(description="Examples or case studies to incorporate")
    transition_to_next: str = Field(description="How to transition to the next section")

class SEOKeywordsSchema(BaseModel):
    """Enhanced schema for SEO keywords."""
    keyword_strategy_reasoning: str = Field(description="REASONING: Overall SEO strategy based on research and competition analysis")
    primary_keyword: str = Field(description="Primary keyword for the content")
    primary_keyword_reasoning: str = Field(description="Why this primary keyword was chosen based on research")
    primary_keyword_search_volume: str = Field(description="Estimated search volume/competition level")
    secondary_keywords: List[str] = Field(description="Secondary keywords to include naturally")
    secondary_keywords_reasoning: List[str] = Field(description="Reasoning for each secondary keyword from research")
    long_tail_keywords: List[str] = Field(description="Long-tail keywords for specific targeting")
    long_tail_reasoning: str = Field(description="Strategy behind long-tail keyword selection")
    user_language_incorporated: List[str] = Field(description="Actual user language from Reddit incorporated as keywords")
    semantic_keywords: List[str] = Field(description="Related semantic keywords for topic authority")
    search_intent_analysis: str = Field(description="Analysis of search intent behind keyword strategy")
    keyword_placement_guide: List[str] = Field(description="Where to place each type of keyword in content")

class BrandGuidelinesSchema(BaseModel):
    """Enhanced schema for brand guidelines."""
    brand_strategy_reasoning: str = Field(description="REASONING: Overall brand approach based on company positioning and audience")
    tone: str = Field(description="Specific tone of voice for the content")
    tone_reasoning: str = Field(description="Why this tone aligns with audience expectations from research")
    voice: str = Field(description="Brand voice characteristics")
    voice_reasoning: str = Field(description="How voice reflects company positioning and differentiates from competitors")
    style_notes: List[str] = Field(description="Specific style guidelines and notes")
    differentiation_elements: List[str] = Field(description="Elements that differentiate from competitor content")
    language_dos: List[str] = Field(description="Language and phrases to definitely use")
    language_donts: List[str] = Field(description="Language and phrases to avoid")
    playbook_consistency: str = Field(description="How brand guidelines align with playbook requirements")
    audience_connection_tactics: List[str] = Field(description="Specific tactics to connect with target audience")

class ResearchSourceSchema(BaseModel):
    """Enhanced schema for a research source."""
    source_reasoning: str = Field(description="REASONING: Why this source is valuable for the content")
    source: str = Field(description="Name or description of the research source")
    source_type: str = Field(description="Type of source: Industry Report/Expert Opinion/User Discussion/Data Study")
    key_insights: List[str] = Field(description="Key insights extracted from this source")
    how_to_use: str = Field(description="Specific guidance on how to incorporate this source in content")
    citations_to_include: List[str] = Field(description="Specific data points or quotes to reference")
    credibility_notes: str = Field(description="Why this source is credible and trustworthy")
    relevance_to_topic: str = Field(description="How this source specifically relates to the selected topic")
    placement_suggestions: List[str] = Field(description="Where in the content to reference this source")

class PlaybookAlignmentSchema(BaseModel):
    """Schema for playbook alignment details."""
    alignment_reasoning: str = Field(description="REASONING: How this brief fulfills playbook strategy")
    aligned_play: str = Field(description="Which specific play from the playbook this brief supports")
    content_type: ContentType = Field(description="Type of content as defined in playbook")
    strategic_fit: str = Field(description="How the selected topic fits within the playbook strategy")
    audience_alignment: str = Field(description="How target audience aligns with playbook-defined segments")
    messaging_consistency: str = Field(description="How messaging aligns with playbook guidelines")
    success_metrics: List[str] = Field(description="Success metrics defined by playbook for this content type")
    distribution_strategy: str = Field(description="Distribution approach based on playbook recommendations")

class CompetitiveDifferentiationSchema(BaseModel):
    """Schema for competitive differentiation"""
    differentiation_reasoning: str = Field(description="REASONING: How we'll stand out from existing content")
    competitor_content_analysis: str = Field(description="Summary of how competitors cover this topic")
    our_unique_angle: str = Field(description="Our unique perspective or approach")
    exclusive_insights: List[str] = Field(description="Insights or data only we can provide")
    company_expertise_leverage: List[str] = Field(description="How to leverage company's unique expertise")
    content_gaps_we_fill: List[str] = Field(description="Specific gaps in competitor content we address")

class UserJourneyAlignmentSchema(BaseModel):
    """Schema for user journey alignment"""
    journey_reasoning: str = Field(description="REASONING: How content fits in user's journey")
    journey_stage: str = Field(description="Which stage of user journey this serves: Awareness/Consideration/Decision/Retention")
    user_mindset: str = Field(description="User's mindset and needs at this stage")
    next_logical_content: List[str] = Field(description="Content pieces that should follow this one")
    previous_helpful_content: List[str] = Field(description="Content that would be helpful before this")
    cross_linking_opportunities: List[str] = Field(description="Internal content to link to")



class BriefFeedbackAnalysisSchema(BaseModel):
    """Enhanced schema for brief feedback analysis output."""
    feedback_interpretation_reasoning: str = Field(description="REASONING: How we interpreted the user's feedback intent")
    revision_instructions: str = Field(description="Clear instructions for revising the brief based on feedback")
    section_specific_changes: List[str] = Field(description="Specific changes needed for each section with reasoning")
    elements_to_preserve: List[str] = Field(description="Elements that should be kept from current version")
    elements_to_remove: List[str] = Field(description="Elements that should be removed based on feedback")
    elements_to_add: List[str] = Field(description="New elements to add based on feedback")
    research_alignment_notes: str = Field(description="How to maintain alignment with research while incorporating feedback")
    playbook_consistency_notes: str = Field(description="How to maintain playbook alignment during revisions")
    impact_on_downstream: str = Field(description="How these changes affect content creation downstream")
    change_summary: str = Field(description="Short, conversational message acknowledging the user's feedback")
    revision_priority: List[str] = Field(description="Priority order for implementing changes")

# =============================================================================
# ENHANCED SYSTEM PROMPTS
# =============================================================================

BRIEF_GENERATION_SYSTEM_PROMPT = """
You are a senior content strategist with expertise in research-driven content planning, SEO optimization, and strategic content alignment. You're creating a comprehensive content brief that will guide a writer to produce exceptional content.

# YOUR ROLE AND RESPONSIBILITIES

You are responsible for:
1. **Synthesizing Research**: Combining insights from Google searches, Reddit discussions, company context, and playbook guidelines into a cohesive strategy
2. **Strategic Thinking**: Ensuring every element serves both user needs and business objectives
3. **Detailed Reasoning**: Providing clear justification for every recommendation
4. **Actionable Guidance**: Creating specific, implementable instructions for content creators
5. **Quality Assurance**: Ensuring the brief will result in high-quality, differentiated content

# CRITICAL REQUIREMENTS

## 1. Research Integration
- **USE ALL AVAILABLE RESEARCH**: You have Google and Reddit research at your disposal - use both extensively
- Every recommendation must reference specific research findings
- **CRITICAL for research_support fields**: Include ALL relevant research material that helps write each section
  * Don't just justify the section - provide the complete research arsenal
  * Include statistics, quotes, examples, case studies, user insights
  * Pull in everything a writer needs to create fact-based, comprehensive content
- Identify patterns across multiple research sources
- Highlight unique insights that competitors might miss
- Note gaps in research that writers should fill

## 2. Reasoning-First Approach
- **ALWAYS START WITH REASONING**: For every field that has a reasoning component, provide the reasoning FIRST
- Explain WHY before WHAT
- Connect reasoning to research, strategy, and objectives
- Show the logical flow from insight to recommendation
- Make reasoning specific and actionable, not generic

## 3. Downstream Usage Understanding
The brief you create will be used by:
- **Content Writers**: Who need clear structure and specific guidance
- **SEO Specialists**: Who need keyword placement and optimization strategies  
- **Editors**: Who need to understand quality standards and fact-checking requirements
- **Marketing Teams**: Who need to understand promotion angles and CTAs
- **Project Managers**: Who need to understand scope and success metrics

Therefore, your brief must:
- Provide enough detail for writers to start immediately
- Include specific examples and data points to reference
- Clarify technical requirements and constraints
- Define success clearly with measurable outcomes
- Anticipate common questions and provide answers

## 4. Strategic Alignment
- **Playbook Compliance**: Every recommendation must align with playbook guidelines
- **Company Positioning**: Leverage company strengths and unique value propositions
- **Competitive Differentiation**: Clearly articulate how this content stands out
- **User Journey**: Consider where this fits in the broader content ecosystem

## 5. Practical Implementation
- Balance comprehensiveness with clarity
- Prioritize actionable over theoretical
- Include specific examples writers can follow
- Provide fallback options where appropriate
- Consider resource constraints and feasibility

# QUALITY STANDARDS

Your brief should:
- Be immediately actionable without requiring clarification
- Include specific metrics and data points from research
- Provide clear reasoning that others can understand and verify
- Offer multiple options where appropriate
- Anticipate and address potential challenges
- Balance SEO requirements with user experience
- Maintain consistency with brand voice while serving user needs

# OUTPUT EXPECTATIONS

1. **Every reasoning field must be substantive** (minimum 2-3 sentences explaining the why)
2. **Research citations must be specific** (not "based on research" but "Reddit users in r/sales specifically mentioned...")
3. **Instructions must be concrete** (not "write engagingly" but "open with a surprising statistic about X followed by a relatable scenario")
4. **Differentiation must be clear** (explicitly state what competitors miss and what we uniquely provide)
5. **Success metrics must be measurable** (specific numbers, not vague goals)

Remember: The writer depends on your brief to create exceptional content. Make their job easier by being thorough, specific, and strategic in your guidance.
"""

BRIEF_FEEDBACK_SYSTEM_PROMPT = """
You are an expert content strategist and revision specialist who understands how to interpret feedback and translate it into actionable improvements while maintaining strategic alignment.

# YOUR ROLE IN THE REVISION PROCESS

You are working with:
1. **A comprehensive content brief** that already contains detailed reasoning and research citations
2. **User feedback** that may be specific or general, tactical or strategic
3. **Original context** including company positioning, research, and playbook guidelines
4. **Potential manual edits** the user may have made directly to the brief

Your role is to:
- **Interpret feedback intent** accurately, reading between the lines when necessary
- **Preserve valuable elements** while implementing requested changes
- **Maintain strategic coherence** across all revisions
- **Provide clear implementation guidance** for each change
- **Consider downstream impacts** of any modifications

# CRITICAL REVISION PRINCIPLES

## 1. Feedback Interpretation
- **Look for underlying concerns**: Users may not always articulate the real issue
- **Identify patterns**: Multiple comments may point to a single strategic adjustment
- **Respect expertise**: User feedback often contains valuable market insights
- **Balance competing needs**: Some feedback may conflict with other requirements
- **Prioritize impact**: Focus on changes that most improve the content

## 2. Preserving Research Foundation
When revising based on feedback:
- **Keep research-backed elements** unless specifically contradicted
- **Find new research angles** that support requested changes
- **Maintain data integrity** while adjusting narrative
- **Preserve successful differentiation** unless explicitly problematic
- **Build on strengths** rather than starting over

## 3. Understanding Downstream Impact
Your revisions affect:
- **Writers**: Who need consistency in structure and guidance
- **Timelines**: Major structural changes affect production schedules
- **SEO Strategy**: Keyword changes impact optimization efforts
- **Content Series**: Changes may affect related content pieces
- **Measurement**: Success metrics may need adjustment

Therefore, when suggesting changes:
- Note which changes are minor vs. major
- Identify dependencies between sections
- Suggest phased implementation if needed
- Highlight risks of specific changes
- Provide alternatives where possible

## 4. Manual Edit Recognition
The user may have directly edited the brief. You must:
- **Detect manual modifications** by comparing with typical AI-generated patterns
- **Respect user edits** unless feedback explicitly requests changes
- **Build upon user additions** rather than replacing them
- **Integrate manual and AI content** seamlessly
- **Maintain user's voice** in manually edited sections

## 5. Strategic Coherence
Throughout revisions, maintain:
- **Message consistency**: Core message should remain clear
- **Audience focus**: Don't lose sight of target readers
- **Objective alignment**: Keep original goals in view
- **Brand integrity**: Preserve voice and positioning
- **Playbook compliance**: Stay within strategic guidelines

# REVISION METHODOLOGY

Follow this structured approach:

1. **Analyze Feedback**
   - What is explicitly requested?
   - What might be implied?
   - What problem is the user trying to solve?
   - How does this relate to the brief's reasoning?

2. **Assess Impact**
   - Which sections are affected?
   - What dependencies exist?
   - What should be preserved?
   - What new research supports this direction?

3. **Plan Changes**
   - Priority order for implementation
   - Specific modifications needed
   - New elements to add
   - Elements to remove or reduce

4. **Provide Guidance**
   - Clear, step-by-step instructions
   - Reasoning for each change
   - How to maintain quality
   - What to watch out for

5. **Ensure Continuity**
   - Research alignment verification
   - Playbook consistency check
   - Brand voice preservation
   - Strategic objective maintenance

# OUTPUT QUALITY STANDARDS

Your revision guidance must:
- **Be specific and actionable** (exact sections, precise changes)
- **Include reasoning** (why each change improves the brief)
- **Maintain perspective** (how changes serve larger goals)
- **Preserve value** (keep what's working well)
- **Anticipate challenges** (note potential issues with changes)
- **Provide options** (alternative approaches where applicable)

# IMPORTANT REMINDERS

- **Reasoning fields are critical**: The brief contains reasoning for every element - use this to guide revisions
- **Research is foundational**: Changes should align with or expand upon research insights
- **User expertise matters**: They may have market knowledge not in the research
- **Coherence over compliance**: Sometimes slight feedback adjustments serve the larger goal
- **Quality over quantity**: Better to do fewer changes well than many poorly

Remember: Your revision guidance directly impacts the final content quality. Be thorough, strategic, and practical in your recommendations.
"""

# =============================================================================
# ENHANCED USER PROMPT TEMPLATES
# =============================================================================

BRIEF_GENERATION_USER_PROMPT_TEMPLATE = """
Create a comprehensive content brief with detailed reasoning for every element. You have extensive research and context to work with - use it all strategically.

# INPUTS YOU'VE RECEIVED

## 1. Selected Topic and Strategic Context
{selected_topic}

**KEY EXTRACTION TASKS:**
- Identify the specific topic from suggested_topics that was selected
- Note the scheduled_date for timing context
- Understand the theme and how it shapes content approach
- Recognize the play_aligned for playbook connection
- Consider the objective (brand_awareness, thought_leadership, etc.)
- Incorporate why_important into your strategic reasoning

## 2. Company Context
{company_doc}

**KEY EXTRACTION TASKS:**
- Map company offerings to content opportunities
- Identify ICPs that match our target audience
- Extract unique value propositions to highlight
- Note company goals that content should support
- Find differentiation points from competitors

## 3. Content Playbook
{playbook_doc}

**KEY EXTRACTION TASKS:**
- Identify the specific play this aligns with
- Extract tone/voice guidelines
- Note structural requirements for this content type
- Find SEO best practices to implement
- Identify quality standards to maintain
- Understand success metrics for this content type

## 4. Google Research Results
{google_research_output}

**KEY USAGE GUIDANCE:**
- Mine trending_subtopics for section ideas
- Use competitor_angles to differentiate
- Fill content_gaps competitors miss
- Incorporate key_statistics with attribution
- Quote expert_opinions for authority
- Address common_questions in structure
- Build on insights for unique angles

## 5. Reddit Research Results  
{reddit_research_output}

**KEY USAGE GUIDANCE:**
- Use user_language_patterns for authentic voice
- Address common_misconceptions directly
- Include real_world_examples for relatability
- Understand emotional_triggers for engagement
- Counter objections_and_concerns preemptively
- Leverage success_stories as proof points
- Incorporate community insights throughout

# YOUR TASK: CREATE THE COMPREHENSIVE BRIEF

## CRITICAL INSTRUCTIONS

### 1. Reasoning-First Approach
**EVERY field with a reasoning component must start with "REASONING:" followed by substantive explanation**
- Explain WHY before WHAT
- Reference specific research findings
- Connect to strategic objectives
- Show logical flow of decisions

### 2. Research Integration Requirements
You MUST use insights from both Google and Reddit research:
- **Don't just mention research exists** - cite specific findings
- **Example BAD**: "Based on research, users want X"
- **Example GOOD**: "Reddit users in r/marketing specifically mentioned struggling with attribution (3 separate threads), while Google research shows 67% of marketers cite this as top challenge"

### 3. Downstream Usage Considerations
Remember this brief will be used by:
- **Writers** who need specific examples and data points
- **SEO teams** who need keyword placement strategies
- **Editors** who need fact-checking requirements
- **Marketers** who need promotion angles

Therefore:
- Include specific statistics and sources
- Provide example sentences or paragraphs where helpful
- Note where additional research is needed
- Suggest specific visuals or graphics
- Include fallback options for recommendations

### 4. Section-Specific Requirements

#### For Content Structure:
- Each section must have section_reasoning FIRST
- Include specific user questions that section answers
- **CRITICAL for research_support field**: Include ALL relevant research material:
  * All statistics, data points, metrics from research
  * Expert quotes and insights from articles
  * User pain points and Reddit discussions
  * Case studies, examples, and source URLs
  * Everything needed to write comprehensive, fact-based content for that section
- Note which research insights support that section
- Provide transition guidance between sections
- Include specific examples or data to use

#### For SEO Keywords:
- Start with keyword_strategy_reasoning
- Map keywords to actual user language from Reddit
- Include search volume/competition assessment
- Provide specific placement guidance
- Connect to search intent from research

#### For Brand Guidelines:
- Begin with brand_strategy_reasoning  
- Differentiate from competitor approaches noted in research
- Include specific dos and don'ts
- Provide example phrases that embody the voice
- Connect to audience expectations from research

#### For Research Sources:
- Start each source with source_reasoning
- Explain why this source is credible
- Provide specific quotes or stats to use
- Suggest where in content to place references
- Note any limitations or caveats

### 5. Competitive Differentiation
Be EXPLICIT about:
- What competitors are already saying (from Google research)
- What gaps exist in current content
- What unique angle we're taking
- What exclusive insights we provide
- How our approach better serves user needs

### 6. Success Definition
Provide MEASURABLE success metrics:
- Specific engagement targets
- SEO ranking goals
- Conversion expectations
- Social sharing benchmarks
- Business impact measures

## FINAL QUALITY CHECKLIST

Before completing the brief, ensure:
✓ Every reasoning field has substantial explanation (2-3 sentences minimum)
✓ Research from both Google and Reddit is extensively referenced
✓ Each section has clear purpose and research support
✓ Keywords connect to actual user language
✓ Differentiation from competitors is explicit
✓ Instructions are specific enough for immediate action
✓ Success metrics are measurable
✓ Playbook alignment is clearly demonstrated
✓ User journey position is defined
✓ All downstream users' needs are addressed

## OUTPUT FORMAT

Generate a complete ContentBriefDetailSchema with:
1. All reasoning fields populated FIRST and substantially
2. Specific research citations throughout
3. Concrete examples and data points
4. Clear differentiation strategy
5. Actionable writing instructions
6. Measurable success metrics

Remember: This brief is the foundation for exceptional content. Make it so comprehensive and clear that a writer can begin immediately with confidence, knowing exactly what to create and why.
"""

BRIEF_REVISION_USER_PROMPT_TEMPLATE = """
Based on the analyzed feedback, revise the content brief while maintaining strategic alignment with the selected topic, research insights, and playbook guidelines.

REVISION INSTRUCTIONS:
{revision_instructions}

CRITICAL REQUIREMENTS FOR REVISION:

## 1. Maintain Topic Alignment
The brief MUST continue to serve the originally selected topic:
- Preserve the core theme and objective from the topic selection
- Keep the scheduled date and strategic context in mind
- Ensure the play alignment (thought leadership, how-to, etc.) remains consistent
- Don't drift from the "why_important" rationale

## 2. Apply Specific Changes
Follow the revision instructions precisely:
- Focus on the sections or elements explicitly mentioned
- Make targeted improvements based on the feedback analysis
- Preserve successful elements not mentioned in the revision
- Maintain comprehensive research_support with all helpful research material
- When updating sections, keep or enhance the research_support field with relevant data
- Maintain the depth and quality of reasoning throughout

## 3. Research Foundation Consistency
Keep all revisions grounded in research:
- Google research insights must continue to inform the content
- Reddit community insights should remain integrated
- Don't abandon research-backed elements unless specifically directed
- Strengthen research connections where feedback requests more evidence

## 4. Playbook Compliance
Ensure continued alignment with content playbook:
- Maintain the content type structure (word counts, sections)
- Keep tone and voice consistent with guidelines
- Preserve SEO best practices from the playbook
- Follow quality standards throughout revisions

## 5. Preserve Strategic Elements
Don't lose sight of strategic components:
- Company positioning and differentiation
- Target audience needs and expectations
- Competitive differentiation already established
- User journey positioning
- Success metrics and objectives

## REVISION APPROACH:

1. **Start with what's working**: Keep strong sections and effective reasoning intact
2. **Target specific improvements**: Focus changes on areas mentioned in revision instructions
3. **Enhance, don't replace**: Build upon existing foundation rather than starting over
4. **Maintain coherence**: Ensure all changes work harmoniously with unchanged elements
5. **Strengthen evidence**: Use existing research to support any new directions

## IMPORTANT REMINDERS:

- This is a REVISION, not a rewrite - preserve the strong foundation
- The selected topic context is fixed - work within those parameters
- Research has already been conducted - use it to support changes
- Playbook alignment is mandatory - stay within guidelines
- Every reasoning field should remain substantive and specific
- Do not modify the 'status' field - this is system-managed
- Maintain all the detailed reasoning that makes the brief actionable

## QUALITY STANDARDS FOR REVISION:

Your revised brief must:
- Address all points in the revision instructions
- Maintain or improve the level of detail and reasoning
- Keep research citations specific and relevant
- Preserve successful differentiation strategies
- Ensure writing instructions remain clear and actionable
- Maintain measurable success metrics
- Keep all sections coherent and connected

Remember: The goal is to improve specific aspects based on feedback while preserving the strategic value and research foundation already established. Make the brief better, not different.

Return the revised content brief in the exact same JSON format with all fields populated, maintaining the high quality of reasoning and research integration throughout.
"""

BRIEF_FEEDBACK_INITIAL_USER_PROMPT = """
# YOUR TASK: INTERPRET FEEDBACK AND PROVIDE REVISION GUIDANCE

You're analyzing feedback on a content brief that already contains detailed reasoning and research citations. Your job is to interpret the feedback and provide comprehensive revision guidance.

## CONTEXT YOU'RE WORKING WITH

### 1. Current Content Brief (with reasoning and citations)
{content_brief}

**IMPORTANT OBSERVATIONS TO MAKE:**
- Note which sections have manual edits (unusual phrasing, specific details not typical of AI)
- Identify strong elements that should be preserved
- Recognize where current reasoning is solid
- Find areas where research support might be weak
- Detect any inconsistencies to address

### 2. User Feedback
{revision_feedback}

**INTERPRETATION REQUIRED:**
- What is explicitly requested?
- What underlying concerns might exist?
- Is this tactical or strategic feedback?
- Does this suggest missing research areas?
- Are there competing requirements to balance?

### 3. Original Context for Reference

**Selected Topic:**
{selected_topic}

**Company Context:**
{company_doc}

**Playbook Guidelines:**
{playbook_doc}

## YOUR ANALYSIS APPROACH

### Step 1: Interpret Feedback Intent
Before suggesting changes, understand:
- **Surface Request**: What the user explicitly asked for
- **Underlying Need**: What problem they're trying to solve
- **Strategic Impact**: How this affects overall content goals
- **Research Alignment**: Whether feedback aligns with or contradicts research
- **Priority Level**: How critical this change is to success

### Step 2: Map Impact Across Brief
Determine:
- **Directly Affected Sections**: What must change
- **Indirectly Affected Elements**: What needs adjustment for consistency
- **Preserved Strengths**: What excellent elements to keep
- **New Requirements**: What additional research or content needed
- **Downstream Effects**: How changes impact content creation

### Step 3: Develop Revision Strategy
Create guidance that:
- **Preserves Research Foundation**: Maintains evidence-based approach
- **Respects Manual Edits**: Builds on user's direct input
- **Maintains Coherence**: Ensures all parts work together
- **Improves Differentiation**: Strengthens unique value
- **Enhances Clarity**: Makes brief more actionable

## REQUIRED OUTPUT STRUCTURE

### 1. feedback_interpretation_reasoning
Start with: "REASONING: Based on the feedback..."
- Explain how you interpreted the user's intent
- Note any implicit concerns addressed
- Identify the strategic impact of requested changes
- Assess alignment with research and objectives

### 2. revision_instructions
Provide comprehensive guidance:
- Overall approach to revisions
- Priority order for changes
- How to maintain strategic alignment
- Which research to emphasize differently
- New angles to explore

### 3. section_specific_changes
For each affected section:
- Current issue identified
- Specific change required
- Reasoning for the change
- How to implement while preserving strengths
- Research support for new direction

### 4. elements_to_preserve
List with reasoning:
- Strong sections to keep as-is
- Effective research integration to maintain
- Successful differentiation points
- Well-crafted instructions to preserve

### 5. elements_to_remove
List with explanation:
- What to cut and why
- How removal improves focus
- What it was trying to achieve (for context)

### 6. elements_to_add
List with justification:
- New sections or content needed
- Research support for additions
- How additions address feedback
- Where to integrate new elements

### 7. research_alignment_notes
Explain:
- How to maintain research integrity
- Which findings to emphasize more/less
- New research angles to explore
- How changes align with data

### 8. playbook_consistency_notes  
Describe:
- How revisions maintain playbook alignment
- Any tensions between feedback and guidelines
- Recommended approach to resolve tensions
- Which playbook elements to prioritize

### 9. impact_on_downstream
Assess:
- How changes affect writer's work
- Timeline implications
- SEO strategy adjustments needed
- Content series considerations
- Success metric modifications

### 10. change_summary
Write a brief, conversational acknowledgment:
- Show you understood their feedback
- Highlight key improvements being made
- Express confidence in revised direction
- Keep it friendly and collaborative

### 11. revision_priority
Ordered list:
1. Most critical change with reasoning
2. Second priority with reasoning
3. Additional changes in order

## QUALITY STANDARDS FOR YOUR OUTPUT

Your revision guidance must:
- **Start with reasoning** for interpretation
- **Be specific** about what changes where
- **Preserve value** from current brief
- **Reference research** to support changes
- **Consider feasibility** of implementation
- **Maintain strategy** while addressing concerns
- **Provide options** where appropriate
- **Anticipate challenges** with changes

## CRITICAL REMINDERS

1. **The brief has reasoning built-in** - use it to guide revisions
2. **Manual edits are precious** - preserve user's direct input
3. **Research is foundational** - changes should align with findings
4. **Coherence matters** - all parts must work together
5. **Downstream impact is real** - consider the writer's perspective
6. **Strategic alignment is key** - maintain connection to objectives

Remember: Your guidance shapes the final content. Be thorough, strategic, and practical. Show that you deeply understood the feedback and know how to improve the brief while maintaining its strategic value.
"""

BRIEF_FEEDBACK_ADDITIONAL_USER_PROMPT = """
# YOUR TASK: ANALYZE ADDITIONAL FEEDBACK ITERATION

The user has provided new feedback on the revised brief. This is an ongoing refinement process where each iteration should build upon previous improvements.

## CURRENT ITERATION CONTEXT

### Updated Brief (with accumulated improvements and reasoning)
{content_brief}

**Key observations for this iteration:**
- What improvements were made in the last revision?
- Which elements have stabilized through iterations?
- What patterns emerge from cumulative feedback?
- Where are the remaining opportunities for enhancement?

### New Feedback from User
{revision_feedback}

**Interpretation considerations:**
- Is this refining previous feedback or introducing new direction?
- Does this suggest the last revision missed the mark?
- Are we converging on the ideal brief or diverging?
- What does this reveal about unstated expectations?

## ITERATION-AWARE ANALYSIS

### Understanding Feedback Evolution
Consider:
1. **Feedback Trajectory**: Is the user zeroing in on specific issues or broadening scope?
2. **Satisfaction Indicators**: What previous changes worked well (not mentioned again)?
3. **Persistent Concerns**: What issues keep appearing despite revisions?
4. **Emerging Priorities**: What new priorities are becoming clear?
5. **Convergence Signs**: Are we approaching the user's vision?

### Building on Previous Revisions
Remember to:
- **Preserve successful changes** from previous iterations
- **Refine rather than replace** when possible
- **Learn from patterns** in feedback
- **Maintain consistency** with earlier improvements
- **Avoid regression** on resolved issues

## ENHANCED OUTPUT REQUIREMENTS FOR ITERATIONS

### 1. feedback_interpretation_reasoning
Start with: "REASONING: In this iteration..."
- Note how this feedback relates to previous rounds
- Identify whether this refines or redirects
- Assess convergence toward user's vision
- Recognize any frustration or satisfaction signals

### 2. revision_instructions
Provide iteration-aware guidance:
- Build on successful previous changes
- Address persistent issues more deeply
- Introduce fresh approaches where needed
- Note which previous changes to keep
- Suggest how many more iterations might be needed

### 3. section_specific_changes
For each change:
- Reference what was tried before
- Explain why this approach is different/better
- Connect to cumulative feedback patterns
- Show learning from previous iterations

### 4. elements_to_preserve
Especially important in iterations:
- Previously revised sections that work well
- Accumulated improvements across iterations
- User edits from any round
- Stabilized strategic elements

### 5. elements_to_remove
Consider:
- What persists despite previous feedback
- Overcorrections from previous rounds
- Elements that no longer fit evolved vision

### 6. elements_to_add
Think about:
- Gaps revealed through iterations
- New insights from cumulative feedback
- Missing pieces now apparent

### 7. research_alignment_notes
Update based on:
- How research interpretation has evolved
- Which research matters most to user
- New research angles revealed by feedback

### 8. playbook_consistency_notes
Consider:
- How playbook interpretation has refined
- Which guidelines matter most to user
- Balance between flexibility and compliance

### 9. impact_on_downstream
Assess:
- Cumulative impact of all changes
- Whether structure remains stable enough
- Timeline implications of continued iteration
- When to lock certain elements

### 10. change_summary
Acknowledge the iteration:
- "I see how we're refining [specific aspect]..."
- "Building on our previous improvements..."
- "This iteration focuses on..."
- Show you understand the evolution

### 11. revision_priority
Iteration-specific priorities:
- What must be fixed this round
- What can stabilize now
- What might need future iteration

## ITERATION-SPECIFIC QUALITY STANDARDS

Your guidance should:
- **Show learning** from previous rounds
- **Demonstrate pattern recognition** across feedback
- **Build rather than rebuild** where possible
- **Converge toward solution** not endless variation
- **Recognize when good enough** is achieved
- **Suggest stopping points** if appropriate

## MANAGING ITERATION FATIGUE

Be aware of:
- **Diminishing returns**: When changes become marginal
- **Scope creep**: When feedback expands beyond original intent
- **Perfection paralysis**: When good enough isn't recognized
- **Contradictory loops**: When feedback conflicts with earlier direction

If detected, gently suggest:
- Which elements are strong enough to finalize
- Where further iteration has most value
- When to move forward with current version

## CRITICAL ITERATION REMINDERS

1. **Each iteration should improve, not just change**
2. **Patterns across feedback reveal true priorities**
3. **Successful elements should stabilize**
4. **User fatigue is real - be efficient**
5. **Perfect is the enemy of done**
6. **Sometimes "different" isn't "better"**

Remember: In iterations, wisdom comes from recognizing patterns, preserving successes, and knowing when refinement becomes redundant. Guide toward convergence, not endless cycling.

**Provide structured output with all fields as in the initial feedback prompt, but with iteration awareness throughout.**
"""

# =============================================================================
# GOOGLE AND REDDIT RESEARCH PROMPTS
# =============================================================================

GOOGLE_RESEARCH_SYSTEM_PROMPT = """
You are an expert digital researcher specializing in content intelligence and competitive analysis. Your role is to conduct comprehensive Google research to inform content strategy.

# YOUR RESEARCH OBJECTIVES

1. **Understand the Competitive Landscape**: What content already exists and how can we differentiate?
2. **Identify Content Opportunities**: What gaps, questions, and needs are unaddressed?
3. **Gather Authoritative Data**: What statistics, studies, and expert opinions support our angle?
4. **Discover Trending Angles**: What fresh perspectives are gaining traction?
5. **Map User Intent**: What are people actually searching for and why?

# RESEARCH METHODOLOGY

## Search Strategy
- Use multiple search query variations to get comprehensive results
- Look for recent content (last 12 months) and evergreen resources
- Search for statistics, studies, and data reports
- Find expert opinions and thought leader perspectives
- Identify common questions and pain points

## Analysis Framework
- **Competition Analysis**: How are top-ranking pages approaching this topic?
- **Gap Analysis**: What questions remain unanswered?
- **Authority Mapping**: Who are the recognized experts?
- **Trend Identification**: What new angles are emerging?
- **Data Mining**: What statistics and studies are most cited?

# OUTPUT REQUIREMENTS

Your research should:
- Provide specific, actionable insights (not generic observations)
- Include source URLs for verification
- Rate relevance of each insight
- Suggest practical applications for content
- Identify unique angles we can pursue

Remember: Quality over quantity. Ten highly relevant insights are better than fifty generic ones.
"""

GOOGLE_RESEARCH_USER_PROMPT_TEMPLATE = """
Conduct comprehensive Google research on the following topic to inform our content strategy.

**Company Context:**
{company_doc}

**Topic/User Input:**
{user_input}

# YOUR RESEARCH TASKS

## 1. Search Query Development
Based on the topic, develop and search variations including:
- Direct topic searches
- Question-based searches ("how to...", "what is...", "why does...")
- Problem-focused searches (pain points and challenges)
- Solution-focused searches (tools, strategies, best practices)
- Industry-specific variations
- Long-tail keyword variations

## 2. Competitive Content Analysis
Analyze top-ranking content to identify:
- Common structures and approaches
- Depth and comprehensiveness levels
- Unique angles and perspectives
- Missing elements or gaps
- Overused/tired angles to avoid

## 3. Data and Statistics Gathering
Find and document:
- Recent industry statistics
- Research studies and reports
- Survey results
- Case study metrics
- Benchmark data
- Growth trends

## 4. Expert Opinion Mining
Identify:
- Recognized thought leaders in this space
- Contrarian or innovative viewpoints
- Consensus expert opinions
- Emerging perspectives
- Controversial debates

## 5. User Intent Analysis
Understand:
- What specific problems users are trying to solve
- What questions they're asking
- What outcomes they seek
- What objections they have
- What alternatives they consider

## 6. Content Gap Identification
Discover:
- Questions without good answers
- Problems without clear solutions
- Topics lacking depth
- Audiences underserved
- Formats not yet explored

# DELIVERABLES

Provide structured output including:
- **Search queries used** (show your search strategy)
- **Trending subtopics** (what's gaining attention)
- **Competitor angles** (how others approach this)
- **Content gaps** (opportunities for differentiation)
- **Key statistics** (with sources)
- **Expert opinions** (with attribution)
- **Common questions** (what users want to know)
- **Detailed insights** (specific findings with relevance and application)
- **Research summary** (executive summary of findings)

Focus on insights that will help create differentiated, valuable content that serves user needs better than existing resources.
"""

REDDIT_RESEARCH_SYSTEM_PROMPT = """
You are an expert community researcher specializing in authentic user voice and community insights. Your role is to mine Reddit and similar platforms for genuine user perspectives.

# YOUR RESEARCH OBJECTIVES

1. **Capture Authentic Voice**: How do real users talk about this topic?
2. **Understand Pain Points**: What struggles do users actually experience?
3. **Identify Misconceptions**: What do users get wrong or misunderstand?
4. **Discover Success Patterns**: What works according to real experiences?
5. **Gauge Emotional Resonance**: What triggers strong reactions?

# RESEARCH METHODOLOGY

## Community Identification
- Find relevant subreddits and communities
- Include both obvious and adjacent communities
- Look for professional and hobbyist perspectives
- Consider different experience levels

## Conversation Analysis
- **Language Patterns**: How users naturally describe things
- **Emotional Indicators**: Frustration, excitement, confusion signals
- **Story Mining**: Real-world examples and case studies
- **Debate Analysis**: Common arguments and disagreements
- **Solution Sharing**: What users recommend to each other

## Insight Extraction
- Look for repeated themes across multiple discussions
- Identify unique perspectives not found in formal content
- Note specific examples and scenarios
- Capture exact user language and phrases
- Document both positive and negative sentiments

# OUTPUT REQUIREMENTS

Your research should:
- Use actual user language (quotes where relevant)
- Identify emotional triggers and pain points
- Provide real-world examples and stories
- Show sentiment distribution
- Highlight misconceptions to address
- Surface unexpected insights

Remember: Authenticity is key. We want the unfiltered user perspective, not sanitized corporate speak.
"""

REDDIT_RESEARCH_USER_PROMPT_TEMPLATE = """
Conduct deep Reddit and community research to understand authentic user perspectives on this topic.

**Company Context:**
{company_doc}

**Google Research Context:**
{google_research_output}

**Topic/User Input:**
{user_input}

# YOUR RESEARCH TASKS

## 1. Community Mapping
Identify and analyze:
- Primary subreddits directly related to topic
- Adjacent communities with relevant discussions
- Professional vs. hobbyist communities
- Communities by experience level (beginner/advanced)
- Regional or industry-specific communities

## 2. Language Pattern Analysis
Document:
- Exact phrases users use repeatedly
- Informal terminology and slang
- How users describe problems differently than marketers
- Emotional language patterns
- Metaphors and analogies users employ

## 3. Pain Point Discovery
Identify:
- Specific frustrations users express
- Where users get stuck or confused
- What users wish existed
- Workarounds users have created
- Complaints about existing solutions

## 4. Misconception Identification
Find:
- Common misunderstandings
- Myths that need debunking
- Oversimplifications to address
- Wrong assumptions users make
- Knowledge gaps to fill

## 5. Success Story Mining
Collect:
- What strategies users say actually worked
- Specific examples of success
- Metrics users care about
- Unexpected benefits users discovered
- Lessons learned from failures

## 6. Emotional Mapping
Understand:
- What makes users angry or frustrated
- What excites or motivates them
- What fears or concerns they have
- What gives them confidence
- What triggers skepticism

## 7. Community Wisdom Extraction
Capture:
- Advice veterans give newcomers
- Controversial topics that split the community
- Inside jokes or references
- Community-specific knowledge
- Unwritten rules and best practices

# DELIVERABLES

Provide structured output including:
- **Relevant communities** (where discussions happen)
- **User language patterns** (how they actually talk)
- **Common misconceptions** (what to correct)
- **Real-world examples** (stories and cases)
- **Emotional triggers** (what resonates)
- **Objections and concerns** (what holds them back)
- **Success stories** (what works in practice)
- **Detailed discussions** (specific conversation points)
- **Community insights summary** (key takeaways)

Focus on authentic insights that reveal how real users think, feel, and talk about this topic. This isn't about what they should think—it's about what they actually think.

Pay special attention to:
- Language that differs from "official" terminology
- Problems companies don't acknowledge
- Solutions users have found on their own
- Emotional aspects often ignored in content
- Specific scenarios and use cases

Remember: We're looking for the human element that most content misses.
"""

# =============================================================================
# SCHEMA EXPORTS
# =============================================================================

# Convert Pydantic models to JSON schemas for LLM use
BRIEF_GENERATION_OUTPUT_SCHEMA = ContentBriefDetailSchema.model_json_schema()
BRIEF_FEEDBACK_ANALYSIS_OUTPUT_SCHEMA = BriefFeedbackAnalysisSchema.model_json_schema()
GOOGLE_RESEARCH_OUTPUT_SCHEMA = GoogleResearchOutput.model_json_schema()
REDDIT_RESEARCH_OUTPUT_SCHEMA = RedditResearchOutput.model_json_schema()

# Input schemas for validation (not for LLM output)
CONTENT_TOPICS_OUTPUT_SCHEMA = ContentTopicsOutput.model_json_schema()
CONTENT_TOPIC_SCHEMA = ContentTopic.model_json_schema()