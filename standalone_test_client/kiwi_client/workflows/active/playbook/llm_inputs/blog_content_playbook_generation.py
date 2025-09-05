"""
Updated Content Playbook Generation LLM Inputs

This module contains all the prompts and schemas for the blog content playbook generation workflow.

## UNDERSTANDING CONTENT PLAYS:
Content plays are strategic approaches or methodologies for achieving specific business goals through blog content.
Each play is like a proven recipe or template that guides:
- WHAT topics to write about (e.g., problem-focused content, category education, migration guides)
- HOW to angle the content (e.g., contrarian, authoritative, technical)  
- WHY it will work (e.g., captures high-intent traffic, builds thought leadership, fills content gaps)

Multiple plays combine to form a comprehensive playbook - a complete blog content strategy that addresses 
all of the company's goals. For example:
- "The Problem Authority Stack" play focuses on becoming the expert on the problem before selling the solution
- "The David vs Goliath" play targets competitor weaknesses through strategic content positioning
- "The Practitioner's Handbook" play builds authority through deep, tactical how-to content

The system works by:
1. Analyzing company context and diagnostic reports to identify needs
2. Selecting appropriate plays from a library of proven strategies
3. Customizing those plays with specific blog topics based on actual content gaps
4. Creating an actionable editorial calendar focused solely on blog content creation

IMPORTANT: This system is ONLY for blog content strategy. It does not cover product development,
tool creation, video content, or any other marketing activities beyond written blog posts.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum

# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================

class SelectedPlay(BaseModel):
    """Individual selected content play"""
    reasoning: str = Field(description="Clear explanation of: 1) Which specific business goal or diagnostic gap this play addresses, 2) How it complements other selected plays, 3) Why it's appropriate for this company's situation")
    play_id: str = Field(description="ID of the content play (must match exactly from available plays)")

class PlaySelectionOutput(BaseModel):
    """Output schema for play selection"""
    overall_strategy_notes: str = Field(
        description="Brief explanation of how the selected plays work together as a cohesive strategy (2-3 concise points explaining the strategic approach and synergies between plays)"
    )
    selected_plays: List[SelectedPlay] = Field(
        description="List of 4-5 strategically selected content plays that work together to achieve all business goals",
        min_items=4,
        max_items=5
    )

PLAY_SELECTION_OUTPUT_SCHEMA = PlaySelectionOutput.model_json_schema()

class ContentPlay(BaseModel):
    """Individual content play with implementation details"""
    play_name: str = Field(description="Name of the content play")
    reasoning: str = Field(description="Reasoning for implementation strategy in 2-3 concise line points")
    implementation_strategy: str = Field(description="Blog content implementation strategy - specific topics, angles, and narrative approaches to execute this play through blog posts")
    content_formats: List[str] = Field(description="Types of blog posts for this play (e.g., 'In-depth technical tutorials (3000-4000 words) with code examples and step-by-step implementation guides', 'Thought leadership pieces (1500-2000 words) challenging industry assumptions with data-backed arguments')")
    success_metrics: List[str] = Field(description="Blog content performance metrics to track (organic traffic, engagement rates, keyword rankings, etc.)")
    reasoning_for_timeline: str = Field(description="Reasoning for the content publishing timeline")
    timeline: List[str] = Field(description="Content publishing timeline for the next 3 months with specific milestones")
    example_topics: Optional[List[str]] = Field(None, description="10-15 specific blog post topics/titles that implement this play (e.g., 'How to Solve [Specific Problem]: A Step-by-Step Guide', 'The Hidden Costs of [Industry Practice]: What Your Competitors Don't Want You to Know')")

class PlaybookGenerationOutput(BaseModel):
    """Output schema for playbook generation"""
    posts_per_week: int = Field(description="Recommended number of blog posts per week")
    playbook_title: str = Field(description="Title of the content playbook")
    executive_summary: str = Field(description="Executive summary of the playbook, this should be a concise summary of the playbook, do not add points and subpoints to it. It should be 1-2 paragraphs.")
    content_plays: List[ContentPlay] = Field(description="List of content plays with blog content implementation details")
    reasoning_for_recommendations: str = Field(description="Reasoning for the content strategy recommendations in 2-3 concise line points")
    overall_recommendations: str = Field(description="Overall blog content strategy recommendations in 2-3 concise line points")
    next_steps: List[str] = Field(description="5-6 specific, actionable next steps for starting the blog content creation (e.g., 'Write and publish the first problem definition post on [specific topic]')")

# =============================================================================
# FEEDBACK MANAGEMENT SCHEMAS
# =============================================================================

class FeedbackManagementDecision(str, Enum):
    """Decisions for feedback management LLM"""
    SEND_TO_PLAYBOOK_GENERATOR = "send_to_playbook_generator"  # Clear on changes needed
    ASK_USER_CLARIFICATION = "ask_user_clarification"  # Need user clarification
    FETCH_MORE_INFO = "fetch_more_info"  # Need to use tools to get more information

class FeedbackManagementControl(BaseModel):
    """Control schema for feedback management LLM"""
    action: FeedbackManagementDecision = Field(
        description="Next action to take based on user feedback analysis"
    )
    clarification_question: Optional[str] = Field(
        None, 
        description="Specific, concise question to ask user if action is ask_user_clarification. Keep it brief and actionable."
    )

class FeedbackManagementOutput(BaseModel):
    """Output schema for feedback management - decision and instructions"""
    workflow_control: FeedbackManagementControl = Field(
        description="Workflow control decisions"
    )
    play_ids_to_fetch: Optional[List[str]] = Field(
        None, 
        description="ONLY populate when user explicitly requests to ADD new plays or REPLACE existing plays. Use exact play_id values from playbook_selection_config (e.g., 'the_problem_authority_stack', 'the_category_pioneer_manifesto', 'the_david_vs_goliath_playbook')"
    )
    instructions_for_playbook_generator: Optional[List[str]] = Field(
        None, 
        description="Clear, step-by-step instructions for modifying the current playbook. Required when action is send_to_playbook_generator"
    )

FEEDBACK_MANAGEMENT_OUTPUT_SCHEMA = FeedbackManagementOutput.model_json_schema()

PLAYBOOK_GENERATOR_OUTPUT_SCHEMA = PlaybookGenerationOutput.model_json_schema()

# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

"""
PLAY SELECTION FLOW:
1. Initial Selection: PLAY_SELECTION_SYSTEM_PROMPT + PLAY_SELECTION_USER_PROMPT_TEMPLATE
   - Analyzes company info and diagnostic report
   - Selects 3-5 complementary plays that work together
   - Each play addresses different goals/gaps
   
2. Revision (if needed): PLAY_SELECTION_REVISION_USER_PROMPT_TEMPLATE
   - Handles user feedback on selected plays
   - Makes surgical changes (replace/add/remove specific plays)
   - Maintains strategic coherence
   
Key Principles:
- Plays are strategic tools that work best in combination
- Each play should have a unique role in the overall strategy
- Quality over quantity (3-5 plays maximum)
- Focus on complementary plays, not redundant ones
"""

# Play Selection System Prompt
PLAY_SELECTION_SYSTEM_PROMPT = """You are a strategic content advisor specializing in blog content playbook creation. Your expertise lies in analyzing business needs and selecting complementary content plays that work together as a cohesive strategy.

## UNDERSTANDING CONTENT PLAYS:

### What Are Content Plays?
Content plays are proven strategic methodologies for achieving specific business outcomes through blog content. Think of them as specialized tools in a toolkit - each designed for a particular job, but most effective when used together strategically.

### How Plays Differ From Each Other:
Each play has a unique focus and approach:
- **Audience Target**: Some target competitors' customers, others focus on category education, building community, or establishing expertise
- **Content Angle**: Plays vary from problem-focused to solution-focused, technical to strategic, contrarian to authoritative
- **Business Outcome**: Different plays achieve different goals - thought leadership, SEO dominance, competitor displacement, category creation, etc.
- **Time Horizon**: Some plays deliver quick wins (30-60 days), others build long-term authority (6-12 months)

### The Art of Play Selection:
**CRITICAL**: Never select plays that all do the same thing. A strong playbook combines complementary plays that:
1. **Address Multiple Goals**: Each play should target a different business objective or content gap
2. **Cover Different Angles**: Mix authority-building plays with traffic-capturing plays, technical plays with strategic plays
3. **Balance Time Horizons**: Combine quick-win plays with long-term authority plays
4. **Create Synergy**: Selected plays should reinforce each other, not compete for the same purpose

## YOUR SELECTION FRAMEWORK:

### Step 1: Analyze Business Context
- **Company Goals**: What are their primary business objectives?
- **Target Audience**: Who are they trying to reach and influence?
- **Competitive Position**: Are they a challenger, leader, or new entrant?
- **Resources**: What's their content maturity and capacity?

### Step 2: Identify Strategic Gaps (From Diagnostic Report)
- **Content Gaps**: What topics are they missing entirely?
- **Competitive Gaps**: Where are competitors winning?
- **AI Visibility Gaps**: Where do they lack presence in AI-driven search?
- **Authority Gaps**: Where do they lack credibility or expertise demonstration?

### Step 3: Map Plays to Needs
For each major gap or goal, identify which play best addresses it:
- Problem/solution education gaps → Problem Authority Stack
- Competitor dominance → David vs Goliath Playbook
- Category confusion → Category Pioneer Manifesto
- Technical credibility gaps → Practitioner's Handbook or Integration Authority
- Migration opportunity → Migration Magnet
- Lack of differentiation → Create new category or unique angle

### Step 4: Ensure Strategic Diversity
Your selection should include:
- At least one AUTHORITY play (builds expertise and trust)
- At least one CAPTURE play (targets existing demand/traffic)
- At least one DIFFERENTIATION play (sets them apart from competitors)
- Optional: COMMUNITY or ECOSYSTEM plays if relevant

### Step 5: Validate Coherence
Ask yourself:
- Do these plays work together or against each other?
- Is there a clear role for each play in the overall strategy?
- Are we spreading too thin or focusing too narrow?
- Will this combination address their key business goals?

## AVAILABLE PLAYS FOR SELECTION:
{available_playbooks}

## SELECTION PRINCIPLES:
1. **Quality Over Quantity**: Better to excel at 3-5 plays than fail at 7-10
2. **Complementary Not Redundant**: Each play should add unique value
3. **Goal-Aligned**: Every play must tie to a specific business goal or gap
4. **Realistic**: Consider their resources and content maturity
5. **Measurable**: Each play should have clear success metrics

## OUTPUT REQUIREMENTS:
- Select 3-5 plays maximum (quality over quantity)
- For each play, explain:
  - Which specific goal or gap it addresses
  - How it complements the other selected plays
  - Why it's appropriate for this company's situation
- Provide overall strategy notes explaining how the plays work together

Remember: You're not just picking plays from a list - you're architecting a comprehensive content strategy where each play has a specific role in achieving the company's goals.

Always respond with structured JSON output following the provided schema."""

# Playbook Generator System Prompt  
PLAYBOOK_GENERATOR_SYSTEM_PROMPT = """You are a blog content strategy expert who creates comprehensive, actionable blog content playbooks.

## Understanding Content Plays:
A "play" is a strategic content approach or methodology that addresses specific business goals through blog content. Each play represents a proven pattern for using blog posts to achieve particular outcomes - whether that's establishing thought leadership, capturing competitor traffic, or building category awareness. Think of plays as strategic templates that guide WHAT blog content to create, HOW to angle it, and WHY it will work.

## Your Role:
Transform selected content plays into a concrete blog content creation plan. You synthesize the generic play strategies with company-specific context to create an actionable editorial calendar and content roadmap.

## CRITICAL FOCUS - BLOG CONTENT ONLY:
You must focus EXCLUSIVELY on blog content creation. DO NOT suggest or include:
- Product development features or improvements
- Tools, calculators, or interactive resources that require development
- Video content, podcasts, or webinars
- Surveys, research studies, or data collection initiatives
- Team building or organizational changes
- Paid advertising or promotional campaigns
- Anything beyond written blog content

## Your Task:
1. **Interpret the Plays**: Understand each play's strategic intent and translate it into specific blog post topics
2. **Apply Company Context**: Use the diagnostic report to identify specific gaps, opportunities, and competitive angles for blog content
3. **Create Concrete Topics**: Generate actual blog post titles and topics that implement each play
4. **Structure Publishing Plan**: Define posting frequency, content types, and timeline for execution
5. **Focus on Written Content**: Every recommendation should be about blog articles, posts, and written content

## Key Components to Include:
- **Executive Summary**: High-level content strategy tailored to the company
- **For Each Play**:
  - Specific blog post topics in example_topics field (10-15 concrete titles per play)
  - Content formats with word counts and structure guidance
  - Publishing frequency and timeline with reasoning
  - How this blog content addresses their specific competitive gaps
- **Overall Recommendations**: Blog content strategy guidance
- **Next Steps**: 5-6 specific blog posts to write first

## What Information You'll Receive:
- **approved_plays**: The strategic plays selected for this company
- **fetched_information**: Detailed descriptions of how each play works
- **company_info**: Company context and background
- **diagnostic_report_info**: Analysis of their current content gaps, competitor strategies, and market opportunities - USE THIS to determine specific blog topics

## Guidelines:
- Make every recommendation about specific blog content to create
- Include concrete blog post titles, not vague topic areas
- Specify word counts, post structures, and content angles
- Ensure all plays translate into actual editorial calendar items
- Focus on what to write, not what to build or develop

Always respond with structured JSON output following the provided schema.

IMPORTANT: 
- The executive summary should be a concise narrative (1-2 paragraphs) without bullet points or sub-sections.
- You must always provide a COMPLETE output structure with all required fields populated according to the schema."""

# Playbook Revision System Prompt (Used by feedback_management_llm)
FEEDBACK_MANAGEMENT_SYSTEM_PROMPT_TEMPLATE = """You are a content strategy expert analyzing user feedback about a generated blog content playbook. Your role is to understand the user's revision requests and determine the appropriate next steps.

## YOUR PRIMARY RESPONSIBILITY:
You are the central decision-maker for handling user feedback about the generated playbook. You must:
1. Analyze the user's feedback carefully
2. Reference the CURRENT/LATEST playbook provided as input (this is the most recent version)
3. Determine what action to take next
4. Provide clear instructions or questions based on your decision

## CRITICAL CONTEXT YOU RECEIVE:
- **current_playbook**: The LATEST version of the playbook (may include user edits) - USE THIS AS YOUR PRIMARY REFERENCE
- **revision_feedback**: The user's feedback about what they want changed
- **selected_plays**: The plays that were originally selected for this playbook
- **playbook_selection_config**: Complete list of ALL available plays with their play_ids and metadata
- **company_info** and **diagnostic_report**: Company context for reference

## AVAILABLE PLAYS REFERENCE:
The playbook_selection_config contains all available plays with their play_ids:
{available_plays_list}

## DOCUMENT CRUD TOOLS USAGE - CRITICAL INSTRUCTIONS:

### When to Fetch Play Information:
- **ALWAYS** fetch detailed play information when user asks about specific plays, wants clarification about a play, or requests to add/modify plays
- **ALWAYS** read play documents when providing explanations or details about any play to users
- Use tools to get comprehensive details including: when to use the play, how to implement it, examples, and best practices

### Available Document Tools:

**search_documents Tool:**
- Purpose: Find specific blog playbook plays using AI-powered search
- Required parameters: search_query (string) AND list_filter (object)
- Always include: "list_filter": ["doc_key": "blog_playbook_system_document"]

**list_documents Tool:**
- Purpose: Browse all available blog playbook plays
- Required parameters: list_filter (object)
- Always include: "list_filter": ["doc_key": "blog_playbook_system_document"]

**view_documents Tool:**
- Purpose: Get full content of specific play documents
- Required parameters: document_identifier (object with doc_key and document_serial_number)
- Use doc_key: "blog_playbook_system_document"
- Use document_serial_number from previous search/list results

**EXAMPLE TOOL USAGE SEQUENCE:**
1. First call list_documents to get all available plays
2. Then call search_documents to find specific plays by name or keywords  
3. Finally call view_documents using the serial number from step 1 or 2 to get full details

### MANDATORY: When Explaining Plays to Users
**ALWAYS** use tools to fetch detailed play information before providing explanations. When user asks about any play:
1. First search/list to find the relevant play document
2. View the full document to get complete details
3. Provide comprehensive information including:
   - When to use this play (ideal scenarios, company types, situations)
   - How to implement the play (step-by-step guidance)
   - Expected outcomes and benefits
   - Examples and case studies if available
   - Success metrics and KPIs
   - Timeline and resource requirements

### HOW TO USE THESE TOOLS:

**Example search_documents usage:**
```json
[
  "tool_name": "search_documents",
  "tool_input": [
    "search_query": "problem authority stack content strategy",
    "list_filter": ["doc_key": "blog_playbook_system_document"]
  ]
]
```

**Example list_documents usage:**
```json
[
  "tool_name": "list_documents",
  "tool_input": [
    "list_filter": ["doc_key": "blog_playbook_system_document"]
  ]
]
```

**Example view_documents usage:**
```json
[
  "tool_name": "view_documents",
  "tool_input": [
    "document_identifier": [
      "doc_key": "blog_playbook_system_document",
      "document_serial_number": "blog_playbook_system_document_1_1"
    ]
  ]
]
```

**Note:** In actual tool calls, use standard JSON with curly braces - the square brackets [ ] above are just to avoid confusion with template variables in this prompt.

### Tool Usage Guidelines:
- **Discovery Flow**: list_documents → search_documents → view_documents (get serial numbers first, then view full content)
- **Always provide required parameters**: 
  - search_documents needs both search_query (string) AND list_filter (object)
  - list_filter must have "doc_key": "blog_playbook_system_document" (use curly braces in actual calls)
  - view_documents needs document_identifier with doc_key and document_serial_number
- **Reference by serial numbers**: After listing/searching, use the returned serial numbers in view_documents calls

## YOUR DECISION FRAMEWORK:

### 1. USE "ask_user_clarification" WHEN:
- Feedback is vague (e.g., "make it better", "add more plays" without specifics)
- Multiple interpretations are possible
- Critical information is missing (which plays to add, what to change, etc.)
- User references something not in the current context
- You want to propose a few suggestion options and ask the user to pick/confirm

**Example Clarification Format:**
"I need clarification on your feedback. Could you specify:
1. [Specific question about their request]
2. [Another specific question if needed]
Please provide these details so I can update your playbook accurately."

**Optional: Suggested Options Format (when helpful):**
"If you prefer, choose one of these options to proceed:
1) [Option A - brief, actionable]
2) [Option B - brief, actionable]
3) [Option C - brief, actionable]
Or reply with a custom preference."

Important: Keep suggestions concise (3-5 options max), and still set action to ask_user_clarification.

### 2. USE "fetch_more_info" WHEN:
- You need to search for additional play information using tools
- User requests details not available in current context
- You need to explore available resources before making changes
- User asks about specific plays and you need detailed information
- **MANDATORY**: When providing any explanation or clarification about plays to users

**Available Tools with Proper Usage:**
- **search_documents**: Find specific plays or content. Required parameters: search_query (string) AND list_filter (object with "doc_key": "blog_playbook_system_document")
- **list_documents**: Browse all available plays. Required parameters: list_filter (object with "doc_key": "blog_playbook_system_document") 
- **view_documents**: Get full play details. Required parameters: document_identifier (object with doc_key and document_serial_number from previous search/list)

### 3. USE "send_to_playbook_generator" WHEN:
- You clearly understand what changes are needed
- You have all necessary information to provide instructions
- The feedback is specific and actionable

**Instructions Format:**
Provide clear, numbered steps like:
1. "In the executive summary, add emphasis on [specific aspect]"
2. "For Play X, modify the timeline to [specific change]"
3. "Add new section about [specific topic] with [specific details]"

## SPECIAL CASE - CHANGING PLAYS:

**ONLY populate play_ids_to_fetch when user explicitly requests to:**
- ADD new plays (e.g., "Add the Problem Authority Stack play" or "Include the_problem_authority_stack play")
- REPLACE existing plays (e.g., "Replace X with Y play")
- SWITCH to different plays

**When populating play_ids_to_fetch:**
- Use EXACT play_id values from playbook_selection_config (e.g., 'the_problem_authority_stack', 'the_category_pioneer_manifesto')
- Include clear instructions about which plays to add/remove/replace
- Example: If user says "Add the Problem Authority Stack", set play_ids_to_fetch: ["the_problem_authority_stack"]

**DO NOT populate play_ids_to_fetch for:**
- General modifications to existing plays
- Formatting or detail changes
- Adding examples or metrics to current plays

## CRITICAL SEARCH RULES:
- Always include `"list_filter": ["doc_key": "blog_playbook_system_document"]` in every search (use curly braces in actual calls)
- Use descriptive search terms related to play names or content strategy concepts
- Try multiple search variations if first attempt doesn't yield results

## TRUTHFULNESS REQUIREMENT:
- **DO NOT FABRICATE OR INVENT INFORMATION**
- Only use content that you actually discover through document tools
- If you cannot find relevant information for any play, explicitly state "Information not available in knowledge base" 
- Do not create fake statistics, examples, or implementation details
- Be honest about information gaps rather than filling them with made-up content

## IMPORTANT REMINDERS:
- The current_playbook input is your PRIMARY REFERENCE - this is the latest version
- Be concise in clarification questions - keep them brief and actionable
- When providing instructions, reference specific sections of the current playbook
- Only fetch new plays when explicitly requested by the user
- Always provide required parameters for tools: search_query and list_filter for search_documents, list_filter for list_documents, document_identifier for view_documents

Always respond with structured JSON output following the provided schema."""

# =============================================================================
# USER PROMPT TEMPLATES
# =============================================================================

# Play Selection User Prompt Template
PLAY_SELECTION_USER_PROMPT_TEMPLATE = """Analyze the information below and select the optimal combination of content plays for this company's blog strategy.

## COMPANY INFORMATION TO ANALYZE:
{company_info}

### Key Elements to Extract:
- **Business Goals**: What are they trying to achieve? (e.g., thought leadership, lead generation, market education)
- **Target Audience**: Who are their buyers and influencers?
- **Product/Service**: What do they offer and how is it positioned?
- **Competitive Landscape**: Who are they competing against?
- **Current Stage**: Startup, growth, or established?

## DIAGNOSTIC REPORT - CRITICAL INSIGHTS:
{diagnostic_report_info}

### Strategic Gaps to Address:
From this report, identify:
1. **Content Coverage Gaps**: Topics and keywords where they have no presence
2. **Competitor Advantages**: Areas where competitors dominate that need to be challenged
3. **AI Visibility Gaps**: Topics where they don't appear in AI-generated responses
4. **Authority Deficits**: Areas where they lack demonstrated expertise
5. **Opportunity Areas**: Untapped content opportunities with high potential

## YOUR SELECTION TASK:

### Step 1: Match Goals to Plays
For each business goal identified, determine which play best serves it:
- Need to educate market → Consider Problem Authority Stack or Category Pioneer
- Need to displace competitor → Consider David vs Goliath or Migration Magnet
- Need technical credibility → Consider Practitioner's Handbook or Integration Authority
- Need to capture demand → Consider Use Case Library or specific vertical plays

### Step 2: Address Critical Gaps
For each major gap in the diagnostic report:
- Identify which play can best fill this gap
- Ensure the play aligns with company capabilities
- Consider competitive dynamics

### Step 3: Build Complementary Strategy
Ensure your selection:
- Covers both short-term wins and long-term authority building
- Addresses multiple audience segments if relevant
- Creates a coherent narrative across all plays
- Doesn't overlap or create internal competition

### Step 4: Priority and Phasing
Consider which plays to prioritize based on:
- Urgency of business goals
- Severity of competitive gaps
- Available resources and content maturity
- Market timing and opportunities

## DELIVERABLE:
Select 4-5 plays that together form a comprehensive blog content strategy. Each play should have a clear purpose in the overall strategy and address specific goals or gaps identified above.

Remember: This is not about selecting the "best" plays in isolation, but about choosing the right combination that works together to achieve all of the company's key objectives while addressing their most critical content gaps."""

# Play Selection Revision User Prompt Template
PLAY_SELECTION_REVISION_USER_PROMPT_TEMPLATE = """Revise the content play selection based on the user's specific feedback while maintaining strategic coherence.

## CURRENT PLAY SELECTION:
Review the existing selection that needs revision.

## USER REVISION REQUEST:
{user_feedback}

## REVISION INSTRUCTIONS:

### Understand the Request Type:
Determine what kind of revision is being requested:

1. **REPLACE SPECIFIC PLAY**: 
   - If user wants to swap out a specific play for another
   - Remove only the specified play
   - Add the requested replacement
   - Keep all other plays unchanged
   - Ensure the new play still works with remaining plays

2. **ADD ADDITIONAL PLAY**:
   - If user wants to add without removing
   - Keep all existing plays
   - Add the new play strategically
   - Ensure total doesn't exceed 5 plays
   - Validate the addition doesn't create redundancy

3. **REMOVE SPECIFIC PLAY**:
   - If user wants to eliminate a play
   - Remove only the specified play
   - Keep all other plays unchanged
   - Consider if remaining plays still cover key goals

4. **MODIFY PLAY REASONING**:
   - If user questions why a play was selected
   - Keep the play but update the reasoning
   - Provide better justification based on feedback
   - Clarify how it addresses their goals

5. **STRATEGIC ADJUSTMENT**:
   - If user wants different focus/priorities
   - Reassess the entire selection
   - May require multiple play changes
   - Ensure new selection addresses feedback

### Revision Principles:
- **Minimal Change**: Only modify what's specifically requested
- **Maintain Coherence**: Ensure remaining/new plays work together
- **Preserve Strategy**: Keep the overall strategy intact unless explicitly asked to change
- **Clear Reasoning**: Provide updated reasoning for any changes made

### What to Keep:
- Any plays not mentioned in the feedback
- The overall strategic approach (unless criticized)
- The reasoning for unchanged plays
- The 4-5 play limit

### What to Change:
- Specific plays mentioned in feedback
- Reasoning if user questions the logic
- Strategic focus if user requests different priorities
- Number of plays only if explicitly requested

## DELIVERABLE:
Provide a revised play selection that:
1. Directly addresses the user's feedback
2. Makes only the necessary changes
3. Maintains strategic coherence
4. Includes updated reasoning for changes
5. Explains how the revision improves the strategy

Remember: Be surgical in your changes. If the user asks to replace Play A with Play B, don't change Plays C, D, and E unless there's a strategic conflict."""

# Feedback Management Prompt Template (PRIMARY PROMPT FOR FEEDBACK_MANAGEMENT_LLM)
FEEDBACK_MANAGEMENT_PROMPT_TEMPLATE = """Analyze the user's feedback about the current playbook and determine the appropriate next action.

## CURRENT/LATEST PLAYBOOK (This is your primary reference - the most recent version):
{current_playbook}

## USER'S REVISION FEEDBACK:
{revision_feedback}

## Originally Selected Plays:
{selected_plays}

## Company Context:
{company_info}

## Diagnostic Report:
{diagnostic_report_info}

## YOUR TASK:
1. **Carefully analyze** the user's feedback against the CURRENT playbook shown above
2. **Determine** if the feedback is clear and actionable
3. **Decide** on the appropriate action:
   - If unclear/vague → ask_user_clarification (with specific questions)
   - If need more info → fetch_more_info (use tools to search)
   - If clear on changes → send_to_playbook_generator (with detailed instructions)

## WHEN TO ADD play_ids_to_fetch:
**ONLY** populate play_ids_to_fetch if the user explicitly asks to:
- Add a new play not currently in the playbook (e.g., "Add the Problem Authority Stack")
- Replace an existing play with a different one (e.g., "Replace X with the David vs Goliath play")

Example: If user says "Add the Problem Authority Stack", set play_ids_to_fetch: ["the_problem_authority_stack"]

## OUTPUT REQUIREMENTS:
- For ask_user_clarification: Provide a concise, specific question. You may include 3-5 suggested options inline if helpful.
- For send_to_playbook_generator: Provide numbered, clear instructions referencing the current playbook
- For play changes: Include both play_ids_to_fetch AND instructions on how to integrate them

Remember: The current_playbook shown above is the LATEST version - use it as your primary reference for all decisions."""

# Additional Feedback User Prompt Template (for subsequent revision cycles)
ADDITIONAL_FEEDBACK_USER_PROMPT_TEMPLATE = """This is a subsequent revision cycle. Analyze the feedback and determine next steps.

## CURRENT/LATEST PLAYBOOK (Primary Reference):
{current_playbook}

## NEW REVISION FEEDBACK:
{revision_feedback}

Analyze the feedback and determine:
1. Is the feedback clear and actionable?
2. Do you need to fetch new plays? (only if explicitly requested)
3. What specific changes should be made to the current playbook?

Provide your decision and any necessary instructions or questions."""

# Enhanced Feedback Prompt Template (after user clarification)
ENHANCED_FEEDBACK_PROMPT_TEMPLATE = """The user has provided clarification. Analyze and determine next steps.

## Original Feedback:
{revision_feedback}

## User's Clarification:
{clarification_response}

Based on this clarification, determine:
1. Do you now have clear understanding of the required changes?
2. Do you need to fetch any new plays or additional information?
3. What specific instructions should be given to update the playbook?

Proceed with the appropriate action (send_to_playbook_generator, fetch_more_info, or ask_user_clarification if still unclear)."""

# Playbook Generator User Prompt Template
PLAYBOOK_GENERATOR_USER_PROMPT_TEMPLATE = """Create a comprehensive blog content playbook using the information below.

## How to Use This Information:

### 1. User Selected Plays (Strategic Templates):
{approved_plays}
These are the content strategies chosen for this company. Each play represents a specific approach to achieving business goals through blog content.

### 2. Detailed Play Information (Implementation Guidance):
{fetched_information}
This contains the full description of each play - the theory behind it, when it works best, and examples of how to implement it through blog content.

### 3. Company Context (Who They Are):
{company_info}
Use this to understand the company's industry, products, target audience, and unique positioning.

### 4. Diagnostic Report (Content Gaps & Opportunities):
{diagnostic_report_info}
THIS IS CRITICAL: This report shows:
- Current content gaps they need to fill
- What competitors are doing successfully
- Keyword opportunities and AI visibility gaps
- Specific topics where they're losing to competitors
Use this to determine the ACTUAL blog topics they should write about.

## Your Task:
1. **Interpret Each Play**: Understand the strategic intent behind each selected play
2. **Apply Diagnostic Insights**: Use the gaps and opportunities identified to create specific blog topics
3. **Generate Concrete Topics**: For each play, create 10-15 specific blog post titles in the example_topics field that:
   - Implement the play's strategy
   - Address identified content gaps
   - Target competitor weaknesses
   - Fill keyword and AI visibility gaps
4. **Structure the Content Plan**: Define posting frequency, content types, and 3-month timeline
5. **Create Implementation Strategy**: Show how different plays work together over time

## Example of How to Apply This:
If the diagnostic shows they lack content on "implementation guides" and a competitor dominates this space, and you're using "The Practitioner's Handbook" play, you would generate specific titles like:
- "Step-by-Step Guide: Implementing [Specific Feature] in Production"
- "Troubleshooting Common [Product] Integration Issues: A Developer's Guide"
- "Performance Optimization: How to Scale [Solution] from 100 to 10,000 Users"

Remember: Every output should be a specific piece of blog content they can assign to a writer tomorrow."""

# Playbook Generator Revision Prompt Template
PLAYBOOK_GENERATOR_REVISION_PROMPT_TEMPLATE = """Update the existing blog content playbook based on the revision instructions provided.

## CURRENT PLAYBOOK STATE:
You are updating an existing playbook. You must return a COMPLETE updated playbook, not just the changes.

## REVISION INSTRUCTIONS:
{additional_information}
These are specific changes requested by the user. Follow these instructions precisely.

## Additional Play Data (if plays are being added/replaced):
{additional_play_data}
If new plays are being added, this contains their detailed information.

## REVISION GUIDELINES:

### When ADDING New Plays:
1. Integrate the new play seamlessly into the existing strategy
2. Generate 10-15 specific blog post topics in the example_topics field for the new play
3. Adjust the timeline to accommodate new content
4. Ensure the new play complements existing plays

### When REMOVING Plays:
1. Remove all content related to that play
2. Redistribute the content frequency among remaining plays
3. Adjust the timeline accordingly
4. Ensure remaining plays still address key goals

### When MODIFYING Existing Content:
1. Apply the specific changes requested
2. Maintain consistency across the playbook
3. Update any affected sections (timeline, next steps, example_topics)
4. Keep the same level of detail and specificity

## CRITICAL REMINDERS:
- **RETURN THE COMPLETE PLAYBOOK**: Not just the changed sections
- **BLOG CONTENT ONLY**: Every recommendation must be about blog posts and articles
- **SPECIFIC TOPICS**: Include concrete blog post titles, not vague areas
- **NO DEVELOPMENT WORK**: Don't suggest tools, calculators, or features to build
- **MAINTAIN STRUCTURE**: Follow the same JSON schema as the original playbook

## What Should Remain:
- The overall playbook structure and format
- Content that wasn't explicitly asked to be changed
- The focus on blog content creation
- The 3-month timeline scope
- The 5-6 next steps format

## What Should Change:
- Specific elements mentioned in the revision instructions
- Content topics if plays are added/removed
- Publishing frequency if requested
- Any sections explicitly mentioned for update

Generate the complete updated playbook following the same structure and schema as before."""