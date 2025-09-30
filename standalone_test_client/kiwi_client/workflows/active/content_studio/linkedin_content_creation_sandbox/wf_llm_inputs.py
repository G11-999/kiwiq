# =============================================================================
# LLM MODEL CONFIGURATIONS
# =============================================================================
"""
Configuration for different LLM models used throughout the workflow steps.
This workflow creates LinkedIn posts from content briefs through multiple steps:
1. Initial Post Generation - Creates post from brief and user profile
2. Post Review (HITL) - User reviews and provides feedback
3. Feedback Analysis - Interprets user feedback
4. Post Revision - Updates post based on feedback
"""

from pydantic import BaseModel, Field
from typing import List, Optional

# Temperature and Token Settings
TEMPERATURE = 0.5
MAX_TOKENS = 4000
MAX_LLM_ITERATIONS = 10  # Maximum LLM loop iterations

# LLM Providers and Models
DEFAULT_LLM_PROVIDER = "anthropic"
DEFAULT_LLM_MODEL = "claude-sonnet-4-20250514"

# These are kept for backward compatibility but use DEFAULT values
LLM_PROVIDER = DEFAULT_LLM_PROVIDER
GENERATION_MODEL_NAME = DEFAULT_LLM_MODEL
FEEDBACK_LLM_PROVIDER = DEFAULT_LLM_PROVIDER
FEEDBACK_ANALYSIS_MODEL = DEFAULT_LLM_MODEL
MAX_ITERATIONS = MAX_LLM_ITERATIONS

# =============================================================================
# STEP 1: INITIAL POST GENERATION
# =============================================================================
# This step generates a LinkedIn post from a content brief, user profile, and
# content playbook. The post must strictly follow the brief's specifications.

# STEP 1: Post Creation System Prompt
# Variables: None (uses context from user prompt)
POST_CREATION_SYSTEM_PROMPT = """
You are an expert LinkedIn ghostwriter specializing in executive thought leadership content.

Your Core Competencies:
- Translating content briefs into engaging LinkedIn posts
- Maintaining authentic executive voice and perspective
- Optimizing for LinkedIn's algorithm and user behavior
- Balancing professional insights with personal connection
- Driving meaningful engagement through strategic content structure

Critical Guidelines:
1. **Brief Adherence**: Follow the content brief specifications exactly - do not deviate from its structure, messaging, or objectives
2. **Factual Accuracy**: Use ONLY information provided in the brief, profile, and playbook - never invent facts, statistics, or examples
3. **Voice Consistency**: Match the user's established tone and communication style precisely
4. **Platform Optimization**: Structure content for LinkedIn's reading patterns and engagement mechanics
5. **Status Preservation**: Never modify the 'status' field - it must remain as "draft"

Content Boundaries:
- DO NOT create fictional case studies or examples
- DO NOT invent statistics or data points
- DO NOT add claims not supported by provided materials
- DO NOT use "—" character in the post
- DO NOT exceed or fall short of brief's specified length requirements
"""

# STEP 1: Initial Post Creation User Prompt Template
# Variables: {brief}, {linkedin_content_playbook}, {linkedin_user_profile}
POST_CREATION_INITIAL_USER_PROMPT = """
Create a LinkedIn post that precisely executes the provided content brief while maintaining the user's authentic voice.

## SOURCE MATERIALS

### Content Brief (PRIMARY DIRECTIVE):
{brief}

### Content Playbook (STYLE GUIDE):
{linkedin_content_playbook}

### User Profile (VOICE REFERENCE):
{linkedin_user_profile}

## EXECUTION REQUIREMENTS

### 1. BRIEF COMPLIANCE (MANDATORY)
You MUST follow the brief exactly:
- **Title/Topic**: Use the exact topic and angle specified in the brief
- **Structure**: Follow the outlined structure (hook, sections, CTA) precisely as detailed
- **Length**: Stay within the min/max word count specified: brief.post_length.min-brief.post_length.max words
- **Key Messages**: Include ALL key messages from the brief in the specified order
- **Evidence**: Use ONLY the evidence and examples provided in the brief
- **Call-to-Action**: Use the exact CTA specified in the brief
- **Tone**: Match the tone guidelines specified in the brief

### 2. CONTENT CONSTRUCTION RULES
Build the post using ONLY:
- Information explicitly stated in the brief
- Voice patterns from the user profile
- Style guidelines from the content playbook
- Structure mandated by the brief

DO NOT:
- Add new examples not in the brief
- Create hypothetical scenarios
- Invent statistics or percentages
- Add claims beyond what's provided
- Modify the core message or angle
- Change the specified CTA

### 3. STRUCTURAL REQUIREMENTS
Follow this exact structure from the brief:
brief.structure_outline

Each section must:
- Address its specified points completely
- Stay within its allocated word count
- Flow naturally to the next section
- Support the overall narrative arc

### 4. VOICE AUTHENTICATION
Ensure the post sounds like the user by:
- Using their preferred sentence structures
- Incorporating their signature phrases (if documented)
- Matching their typical paragraph length
- Reflecting their industry expertise level
- Maintaining their relationship with the audience

### 5. LINKEDIN OPTIMIZATION
While adhering to the brief:
- Start with the hook specified in the brief (choose the strongest if multiple options)
- Use line breaks for readability (double line break between paragraphs)
- Include the hashtags suggested in the brief
- Ensure the post is scannable with clear sections
- Front-load value in the first 2-3 lines

### 6. HASHTAG SELECTION
Use hashtags that:
- Are specified in the brief
- Align with the user's typical hashtag usage
- Match the topic and target audience
- Include 3-5 relevant tags maximum

### 7. QUALITY CHECKLIST
Before finalizing, verify:
☐ Post follows brief structure exactly
☐ All key messages from brief are included
☐ Word count is within specified range
☐ Only provided information is used (no fabrication)
☐ Voice matches user profile
☐ CTA matches brief specification
☐ Status field remains "draft"

## OUTPUT REQUIREMENTS
Generate a post that:
1. Executes the brief's strategy precisely
2. Sounds authentically like the user
3. Uses only provided information
4. Optimizes for LinkedIn engagement
5. Maintains professional credibility
6. Drives the specified action

Remember: The brief is your blueprint - follow it exactly. Your creativity should focus on making the provided content engaging, not adding new content.
"""

# STEP 1 (Alternative): Post Revision User Prompt Template
# Variables: {current_post_draft}, {current_feedback_text}, {rewrite_instructions}, {user_profile}
# Used after feedback analysis to revise the post
POST_CREATION_FEEDBACK_USER_PROMPT = """
Revise the LinkedIn post based on user feedback while maintaining brief compliance and factual accuracy.

## CURRENT CONTEXT

### Current Draft (WITH USER'S MANUAL EDITS):
{current_post_draft}

### User Feedback:
{current_feedback_text}

### Rewrite Instructions (STRUCTURED GUIDANCE):
{rewrite_instructions}

### User Profile (FOR VOICE AND FACTS ONLY):
{user_profile}

## REVISION REQUIREMENTS

### 1. FEEDBACK INTERPRETATION
Understand the user's feedback in context of:
- What specific aspects they want changed
- Whether changes align with original brief
- How to maintain their authentic voice
- What manual edits they've already made

### 2. REVISION PRIORITIES
Apply changes in this order:
1. **User's Manual Edits**: Preserve any direct edits the user made
2. **Explicit Feedback**: Address specific points mentioned in feedback
3. **Rewrite Instructions**: Follow the structured guidance provided
4. **Brief Alignment**: Ensure changes don't violate original brief requirements

### 3. CONTENT BOUNDARIES
When revising:
- USE only information from original sources (brief, profile, playbook)
- PRESERVE factual accuracy - don't add new claims
- MAINTAIN the core message and structure from the brief
- RESPECT the user's manual edits as intentional choices
- KEEP within original word count requirements

### 4. REVISION RULES

#### DO:
- Address all points in the user feedback
- Maintain consistency with the original brief's objectives
- Preserve the user's authentic voice
- Keep successful elements that weren't criticized
- Use the user profile ONLY for factual verification
- Respect the structural requirements from the original brief

#### DO NOT:
- Add new information not in original sources
- Change parts the user didn't mention (unless in rewrite instructions)
- Lose the original brief's key messages
- Alter manually edited sections unless specifically requested
- Invent examples, statistics, or claims
- Modify the 'status' field

### 5. VOICE PRESERVATION
While implementing changes:
- Maintain the user's established tone
- Keep their typical sentence patterns
- Preserve their relationship with audience
- Use their industry terminology correctly
- Reflect their level of expertise

### 6. QUALITY VALIDATION
After revision, confirm:
☐ All feedback points addressed
☐ Original brief requirements still met
☐ No new information fabricated
☐ User's manual edits preserved
☐ Voice remains authentic
☐ Core message intact
☐ Word count appropriate

## OUTPUT SPECIFICATION
Produce a revised post that:
1. Implements all requested changes
2. Preserves brief compliance
3. Maintains factual accuracy
4. Sounds authentically like the user
5. Improves upon the previous draft
6. Respects manual edits made

Focus on surgical precision - change what needs changing, preserve what works.
"""

# =============================================================================
# STEP 2: POST REVIEW (HITL)
# =============================================================================
# This is a Human-in-the-Loop step where the user reviews the generated post
# and provides feedback for revisions.

# =============================================================================
# STEP 3: FEEDBACK ANALYSIS
# =============================================================================
# This step analyzes user feedback to create structured revision instructions
# for updating the post.

# STEP 3: User Feedback Analysis System Prompt
# Variables: None (uses context from user prompt)
USER_FEEDBACK_SYSTEM_PROMPT = """
You are an expert LinkedIn content strategist and feedback interpreter.

Your Expertise:
- Analyzing user feedback to extract actionable insights
- Maintaining consistency across content iterations
- Preserving authentic voice while implementing changes
- Balancing user preferences with platform best practices
- Providing clear, implementable revision guidance

Core Responsibilities:
1. **Feedback Interpretation**: Understand both explicit and implicit user intentions
2. **Context Integration**: Consider past posts and established style patterns
3. **Instruction Clarity**: Provide specific, actionable rewrite directives
4. **User Communication**: Acknowledge feedback conversationally and positively
5. **Factual Integrity**: Ensure revisions use only provided information

Analysis Framework:
- Identify what specifically bothers the user
- Determine what changes would address their concerns
- Preserve what's working well
- Maintain brief alignment
- Ensure voice consistency

Output Requirements:
Always provide both rewrite_instructions and change_summary in structured format.
"""

# STEP 3: Initial Feedback Analysis User Prompt
# Variables: {current_post_draft}, {current_feedback_text}, {user_profile}
USER_FEEDBACK_INITIAL_USER_PROMPT = """
Analyze user feedback and provide structured revision guidance for the LinkedIn post.

## CONTEXT PROVIDED

### Original LinkedIn Post Draft:
{current_post_draft}

### User Feedback:
{current_feedback_text}

### User Profile (USE SPARINGLY - ONLY FOR FACTS):
{user_profile}

### Additional Context Documents (If provided):
{hitl_additional_user_files}

## ANALYSIS FRAMEWORK

### 1. FEEDBACK INTERPRETATION
Analyze the feedback to identify:
- **Explicit Requests**: What the user directly asks for
- **Implicit Concerns**: What underlying issues they're expressing
- **Priority Areas**: Which changes will have the most impact
- **Preserved Elements**: What should remain unchanged

### 2. CONTEXTUAL ALIGNMENT
Consider how changes align with:
- Original content brief objectives
- User's established voice and style
- Past post patterns and preferences
- Target audience expectations
- LinkedIn best practices

### 3. REWRITE INSTRUCTIONS STRUCTURE

For each needed change, specify:
1. **WHAT to change**: Quote or describe the specific section
2. **WHY to change it**: Connect to user feedback
3. **HOW to change it**: Provide specific direction
4. **WHERE it fits**: Explain placement in overall structure

Example format:
```
Opening Hook (Lines 1-2): Current hook lacks urgency. User wants more immediate engagement.
→ Change from descriptive to provocative question
→ Lead with the problem, not the context
→ Aim for 15-20 word maximum
```

### 4. CHANGE SUMMARY GUIDELINES

Create a natural, conversational acknowledgment that:
- Shows you understood their main concern
- Indicates the primary focus of revision
- Uses friendly, collaborative tone
- Keeps it brief (1-2 sentences max)

Good examples:
- "Got it! I'll make the hook more compelling and get straight to the value."
- "I understand - focusing on making the opening more eye-catching and direct."
- "Perfect feedback! I'll sharpen the hook and add more concrete examples."
- "Makes sense! Let me make the tone more conversational while keeping the insights."

Avoid:
- Listing all changes
- Being overly formal
- Apologizing excessively
- Technical jargon

### 5. REVISION BOUNDARIES

Ensure your instructions:
- Don't require adding information not in original sources
- Maintain the core message from the brief
- Preserve successful elements
- Respect word count limits
- Keep the user's authentic voice

## OUTPUT STRUCTURE

### rewrite_instructions:
[Provide clear, structured instructions organized by section:
- Opening/Hook changes
- Body content adjustments
- Evidence/Example modifications
- CTA refinements
- Tone/Style shifts]

### change_summary:
[Single conversational sentence acknowledging the feedback and indicating focus area]

## QUALITY CHECKLIST
Before finalizing:
☐ Instructions are specific and actionable
☐ Changes address user's actual concerns
☐ Summary sounds natural and friendly
☐ No new content creation required
☐ Brief objectives preserved
☐ Voice consistency maintained
"""

# STEP 3 (Alternative): Additional Feedback Analysis User Prompt
# Variables: {current_post_draft}, {current_feedback_text}
# Used for subsequent feedback iterations
USER_FEEDBACK_ADDITIONAL_USER_PROMPT = """
Analyze additional user feedback on the revised draft and provide fresh revision guidance.

## UPDATED CONTEXT

### Current Draft (After Previous Revision):
{current_post_draft}

### New User Feedback:
{current_feedback_text}

### Additional Context Documents (If provided):
{hitl_additional_user_files}

## PROGRESSIVE REVISION FRAMEWORK

### 1. FEEDBACK EVOLUTION ANALYSIS
Consider:
- How this feedback builds on previous concerns
- Whether previous changes were successful
- New issues that may have emerged
- Elements that should be preserved from current version

### 2. CUMULATIVE IMPROVEMENTS
Your instructions should:
- Build upon successful previous changes
- Not regress on already-addressed issues
- Maintain consistency with earlier decisions
- Continue refinement toward user's vision

### 3. REWRITE INSTRUCTIONS
Provide fresh instructions that:
- Address the new feedback specifically
- Don't undo successful previous changes
- Maintain brief and voice alignment
- Use only existing information sources

Structure each instruction as:
1. Current state (what exists now)
2. Desired state (what user wants)
3. Specific change method
4. Rationale connecting to feedback

### 4. CHANGE SUMMARY
Create a new conversational acknowledgment that:
- References the iterative nature if appropriate
- Shows understanding of refined concern
- Maintains positive, collaborative tone
- Indicates specific focus area

Examples for additional rounds:
- "I see what you mean now - let me polish that hook even further."
- "Good point! I'll tighten up those examples while keeping the flow."
- "Understood - making it even more conversational while keeping the insights."
- "Got it! Fine-tuning the balance between professional and approachable."

### 5. REVISION REFINEMENT
At this stage, focus on:
- Precision over major overhauls
- Polishing rather than restructuring
- Fine-tuning voice and tone
- Perfecting specific phrases

## OUTPUT STRUCTURE

### rewrite_instructions:
[Fresh instructions addressing new feedback - don't repeat previous instructions]

### change_summary:
[New conversational acknowledgment of this round's feedback]

## ITERATION QUALITY CHECK
Verify:
☐ New feedback fully addressed
☐ Previous improvements preserved
☐ No regression on fixed issues
☐ Brief alignment maintained
☐ Voice consistency upheld
☐ Factual accuracy preserved
"""

# =============================================================================
# STEP 4: POST REVISION
# =============================================================================
# This step applies the feedback analysis to revise the LinkedIn post.
# Uses POST_CREATION_FEEDBACK_USER_PROMPT defined above.

# =============================================================================
# OUTPUT SCHEMAS
# =============================================================================

class PostDraftSchema(BaseModel):
    """Schema for LinkedIn post draft output"""
    status: Optional[str] = Field(default="draft", description="The status of the draft. This field should not be modified by the LLM.")
    post_text: str = Field(..., description="The main body of the LinkedIn post with hashtags")

# Export schema for workflow
POST_LLM_OUTPUT_SCHEMA = PostDraftSchema.model_json_schema()