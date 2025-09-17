"""
LinkedIn Content Playbook Generation LLM Inputs

This module contains all the prompts and schemas for the LinkedIn content playbook generation workflow.

## UNDERSTANDING LINKEDIN CONTENT PLAYS:
LinkedIn content plays are strategic approaches for building executive thought leadership and business influence through LinkedIn posts.
Each play is a proven methodology that guides:
- WHAT to post about (founder stories, industry insights, customer wins, data-driven analysis)
- HOW to structure the posts (storytelling, contrarian takes, educational content, vulnerability)
- WHY it works (builds trust, demonstrates expertise, creates engagement, drives leads)

Multiple plays combine to form a comprehensive playbook - a complete LinkedIn content strategy that helps executives
achieve their business goals through consistent, strategic posting. For example:
- "The Transparent Founder Journey" builds trust through authentic behind-the-scenes content
- "The Teaching CEO" establishes expertise by educating the audience on complex topics
- "The Industry Contrarian" generates engagement through well-reasoned alternative viewpoints

The system works by:
1. Analyzing the executive's LinkedIn profile and content diagnostic report
2. Selecting 4-5 complementary plays that address their specific gaps and goals
3. Customizing those plays with specific post topics and implementation guidance
4. Creating an actionable posting schedule focused solely on LinkedIn text content

IMPORTANT: This system is ONLY for LinkedIn text post strategy. It does not cover videos, documents,
newsletters, or any other content formats beyond standard LinkedIn text posts.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum

# =============================================================================
# ENUMS AND CONSTANTS
# =============================================================================

class FeedbackManagementDecision(str, Enum):
    """Decisions for feedback management LLM"""
    SEND_TO_PLAYBOOK_GENERATOR = "send_to_playbook_generator"  # Clear on changes needed
    ASK_USER_CLARIFICATION = "ask_user_clarification"  # Need user clarification

# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================

class SelectedPlay(BaseModel):
    """Individual selected LinkedIn content play"""
    source_path_of_infomation: str = Field(description="Exact path of the document and section from which the information was extracted that led to selecting this play. Format: 'Document Name > Section > Subsection'. Examples: 'LinkedIn Profile > Business Goals > Content Objectives', 'Diagnostic Report > Content Gaps Analysis > Engagement Deficits'")
    reasoning_of_selection_of_this_play: str = Field(description="Concise, data-driven explanation citing specific metrics, gaps, or findings that justify this play selection. Must include: 1) Specific data points or findings from the source documents, 2) Clear connection between the data and LinkedIn goals, 3) How this play addresses the identified gap or opportunity. Example: 'Diagnostic Report shows engagement rate at 2.1% vs industry average of 4.5%, while LinkedIn Profile goals emphasize thought leadership building. Current content lacks personal storytelling (LinkedIn Profile > Content Challenges) making this play essential for authentic connection and improved engagement metrics.'")
    play_id: str = Field(description="ID of the content play (must match exactly from available plays)")

class PlaySelectionOutput(BaseModel):
    """Output schema for LinkedIn play selection"""
    overall_strategy_notes: str = Field(
        description="Brief explanation of how the selected plays work together as a LinkedIn strategy (2-3 concise points explaining the approach and synergies)"
    )
    selected_plays: List[SelectedPlay] = Field(
        description="List of 4-5 strategically selected LinkedIn content plays that work together to achieve posting goals",
        min_items=4,
        max_items=5
    )

PLAY_SELECTION_OUTPUT_SCHEMA = PlaySelectionOutput.model_json_schema()

# =============================================================================
# FEEDBACK MANAGEMENT SCHEMAS
# =============================================================================

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
        description="ONLY populate when user explicitly requests to ADD new plays or REPLACE existing plays. Use exact play_id values from playbook_selection_config (e.g., 'the_transparent_founder_journey', 'the_teaching_ceo', 'the_industry_contrarian')"
    )
    instructions_for_playbook_generator: Optional[List[str]] = Field(
        None, 
        description="Clear, step-by-step instructions for modifying the current playbook. Required when action is send_to_playbook_generator"
    )

FEEDBACK_MANAGEMENT_OUTPUT_SCHEMA = FeedbackManagementOutput.model_json_schema()

class ContentPlay(BaseModel):
    """Individual LinkedIn content play with implementation details"""
    play_name: str = Field(description="Name of the content play")
    reasoning_for_implementation_strategy: str = Field(description="Reasoning for this implementation strategy in 2-3 concise points")
    source_path_for_implementation_strategy: str = Field(description="Exact path of the document and section used for implementation strategy. Format: 'Document Name > Section > Subsection'. Examples: 'LinkedIn Profile > Target Audience > Decision Makers', 'Diagnostic Report > Competitive Analysis > Content Format Gaps'")
    implementation_strategy: str = Field(description="LinkedIn post implementation strategy - specific topics, posting angles, and narrative approaches to execute this play through LinkedIn text posts. Should align with the recommended posts per week frequency.")
    content_formats: List[str] = Field(description="Detailed types of LinkedIn text posts for this play (e.g., 'Hook-driven story posts (1000-1200 characters): Personal anecdote opening → Challenge faced → Solution discovered → Business lesson → Engagement question', 'Data insight posts (600-800 characters): Surprising statistic hook → Context and analysis → Contrarian take → Actionable insight → Call for perspectives')")
    success_metrics: List[str] = Field(description="LinkedIn post performance metrics to track (engagement rate, comments quality, profile views, connection requests, DM inquiries)")
    source_path_for_timeline: str = Field(description="Exact path of the document and section used for timeline planning. Format: 'Document Name > Section > Subsection'. Examples: 'LinkedIn Profile > Posting Schedule > Current Capacity', 'Diagnostic Report > Opportunity Areas > Quick Wins Timeline'")
    reasoning_for_timeline: str = Field(description="Reasoning for the posting timeline")
    timeline: List[str] = Field(description="LinkedIn posting timeline for the next 3 months with specific milestones")
    example_topics: Optional[List[str]] = Field(None, description="10-15 specific LinkedIn post topics that implement this play (e.g., 'How we went from 0 to $1M ARR in 18 months', 'The biggest mistake I made as a first-time founder')")

class PlaybookGenerationOutput(BaseModel):
    """Output schema for LinkedIn playbook generation"""
    posts_per_week: int = Field(description="Recommended number of LinkedIn posts per week (should align with the executive's capacity and goals from their profile)")
    playbook_title: str = Field(description="Title of the LinkedIn content playbook")
    executive_summary: str = Field(description="Executive summary of the playbook in 1-2 concise paragraphs without bullet points")
    content_plays: List[ContentPlay] = Field(description="List of LinkedIn content plays with implementation details")
    source_path_for_recommendations: str = Field(description="Exact path of the document and section used for recommendations. Format: 'Document Name > Section > Subsection'. Examples: 'LinkedIn Profile > Business Goals > Primary Objectives', 'Diagnostic Report > Content Gaps Analysis > Priority Areas'")
    reasoning_for_recommendations: str = Field(description="Reasoning for the LinkedIn strategy recommendations in 2-3 concise points")
    overall_recommendations: str = Field(description="Overall LinkedIn posting strategy recommendations in 2-3 concise points")
    next_steps: List[str] = Field(description="5-6 strategic next steps for implementing the LinkedIn content strategy (e.g., 'Set up content batching system for weekly production', 'Identify and document 20 customer success stories for the Customer Champion play', 'Establish measurement dashboard for tracking engagement metrics')")

PLAYBOOK_GENERATOR_OUTPUT_SCHEMA = PlaybookGenerationOutput.model_json_schema()

# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

"""
LINKEDIN PLAYBOOK GENERATION FLOW:
1. Play Selection: PLAY_SELECTION_SYSTEM_PROMPT + PLAY_SELECTION_USER_PROMPT_TEMPLATE
   - Analyzes LinkedIn profile and diagnostic report
   - Selects 4-5 complementary plays for LinkedIn posting strategy
   - Each play addresses different engagement approaches
   
2. Playbook Generation: PLAYBOOK_GENERATOR_SYSTEM_PROMPT + PLAYBOOK_GENERATOR_USER_PROMPT_TEMPLATE
   - Transforms selected plays into concrete LinkedIn post topics
   - Creates daily posting schedule with specific text post ideas
   - Focuses ONLY on LinkedIn text posts (no videos, documents, etc.)
   
3. Revision (if needed): PLAYBOOK_GENERATOR_REVISION_PROMPT_TEMPLATE
   - Handles user feedback on generated playbook
   - Makes targeted changes while maintaining focus on text posts
   - Returns complete updated playbook
   
Key Principles:
- LinkedIn text posts ONLY (no other content formats)
- Specific, actionable post topics (not vague recommendations)
- Concise outputs (1-2 paragraph summaries, 5-6 next steps)
- Character-conscious (posts under 1,500 characters)
"""

# Play Selection System Prompt
PLAY_SELECTION_SYSTEM_PROMPT = """You are a LinkedIn content strategy expert specializing in professional content playbooks. Your role is to analyze LinkedIn profile information and recommend LinkedIn content plays that will help achieve their business goals.

## CRITICAL INSTRUCTIONS:

### 1. STRICT INFORMATION BOUNDARIES
- Base your recommendations ONLY on the information explicitly provided in the LinkedIn profile and diagnostic report
- DO NOT make assumptions about the executive's industry, goals, or challenges beyond what is stated
- DO NOT infer information that is not directly mentioned in the provided documents
- If information is missing or unclear, work with what is available rather than assuming

### 2. PLAY ID REQUIREMENTS
- You MUST select play_id values that match EXACTLY the play_id field from the available playbooks list
- NEVER create, modify, or invent play_id values
- Each selected play MUST correspond to an actual play_id from the provided available playbooks
- Double-check that every play_id you select exists in the available playbooks list

### 3. DIAGNOSTIC ALIGNMENT MANDATORY
- Your play selections MUST directly address the gaps and problems identified in the diagnostic report
- Prioritize plays that solve the specific content challenges mentioned in the diagnostics
- Ensure selected plays align with the opportunities and quick wins identified in the diagnostic analysis
- Reference specific diagnostic findings when explaining your play selection reasoning

### 4. ANALYSIS FRAMEWORK
You will be provided with:
- **LinkedIn Profile Information**: Contains business goals, target audience, and strategic objectives
- **Available LinkedIn Content Plays**: Complete list of plays with their play_id, descriptions, and use cases
- **Diagnostic Report**: Current content performance, gaps, challenges, and identified opportunities

### 5. SELECTION CRITERIA
Base your recommendations on:
1. **Goal Alignment**: How well the play supports the stated business goals from the LinkedIn profile
2. **Gap Addressing**: How effectively the play addresses specific gaps identified in the diagnostic report
3. **Audience Fit**: How well the play resonates with the defined target audience
4. **Implementation Feasibility**: Consider the executive's current content maturity and capabilities
5. **Strategic Impact**: Potential to drive meaningful business outcomes based on provided context

### 6. REASONING AND CITATION REQUIREMENTS
For each recommended play, provide:
- **source_path_of_infomation**: Exact document path using format "Document Name > Section > Subsection"
  - Examples: "LinkedIn Profile > Business Goals > Thought Leadership Objectives"
  - Examples: "Diagnostic Report > Content Gaps Analysis > Engagement Deficits"
- **reasoning_of_selection_of_this_play**: Data-driven explanation that includes:
  - Specific metrics, percentages, or findings from source documents
  - Clear connection between the data and stated LinkedIn goals
  - How this play addresses the identified gap or opportunity
  - Example: "Diagnostic Report shows engagement rate at 2.1% vs industry average of 4.5%, while LinkedIn Profile goals emphasize thought leadership building. Current content lacks personal storytelling (LinkedIn Profile > Content Challenges) making this play essential for authentic connection and improved engagement metrics."

ALL AVAILABLE PLAYS:
{available_playbooks}

Always respond with structured JSON output following the provided schema. Ensure your selections are evidence-based and directly tied to the information provided. Every recommendation must be traceable to specific data points in the provided documents."""

# Playbook Generator System Prompt  
PLAYBOOK_GENERATOR_SYSTEM_PROMPT = """You are a LinkedIn content strategy expert who creates actionable LinkedIn posting playbooks focused exclusively on text-based posts.

## Understanding LinkedIn Content Plays:
A "play" is a strategic posting approach that achieves specific business goals through LinkedIn text content. Each play represents a proven pattern for what to post, how to structure it, and why it resonates with professional audiences.

## Your Role:
Transform selected content plays into a concrete LinkedIn posting plan. You synthesize play strategies with the executive's context to create an actionable daily posting roadmap.

## CRITICAL FOCUS - LINKEDIN TEXT POSTS ONLY:
You must focus EXCLUSIVELY on LinkedIn text post creation. DO NOT suggest or include:
- Video content or LinkedIn Live
- Document uploads or carousel posts  
- LinkedIn newsletters or articles
- External links or blog promotion
- Polls, events, or other LinkedIn features
- Any content beyond standard text posts

## Your Task:
1. **Interpret the Plays**: Understand each play's approach to LinkedIn engagement
2. **Apply Executive Context**: Use their profile and diagnostic data to personalize topics
3. **Create Post Topics**: Generate specific LinkedIn post ideas that implement each play
4. **Structure Posting Plan**: Define daily posting rhythm and content mix
5. **Focus on Text Posts**: Every recommendation should be about LinkedIn text posts

## Key Components to Include:
- **Executive Summary**: Brief (1-2 paragraphs) strategy overview linking plays to business goals
- **Posting Frequency**: MUST align with the executive's current capacity and goals from their LinkedIn profile (look for "posting_schedule" or similar fields)
- **For Each Play**:
  - **Source Path Citations**: Exact document paths for reasoning, implementation strategy, and timeline decisions
  - **Data-Driven Reasoning**: Specific justifications referencing LinkedIn profile data, diagnostic findings, and engagement constraints
  - Specific LinkedIn post topics (10-15 concrete ideas per play)
  - Detailed post structures with character counts, formatting, and flow (e.g., "Hook → Problem → Solution → Lesson → CTA")
  - How the implementation strategy accounts for the recommended posts per week
  - Posting frequency and optimal timing based on available capacity
  - How these posts address their competitive gaps identified in diagnostics
- **Next Steps**: 5-6 STRATEGIC positioning steps (NOT individual posts), such as:
  - Defining the unique thought leadership angle for the executive
  - Clarifying the executive’s core narrative and messaging pillars
  - Identifying how to differentiate from competitors in the LinkedIn landscape
  - Mapping content themes to specific business objectives and audience needs
  - Establishing the executive’s voice and point of view for maximum resonance
  - Outlining how the content strategy will position the executive as an industry authority

## Guidelines:
- **Cite All Decisions**: Every reasoning, implementation strategy, and timeline decision must include exact source path from provided documents
- **Data-Driven Reasoning**: All reasoning fields must reference specific findings, metrics, or constraints from LinkedIn profile or diagnostic report
- **Posting Frequency**: Extract the executive's posting goals from their profile and align your posts_per_week recommendation accordingly
- **Content Formats**: Provide detailed, structured formats for each post type with specific elements and flow based on audience analysis
- **Implementation Strategy**: Must consider and mention how the posts per week frequency affects the play execution based on capacity constraints
- **Strategic Next Steps**: Focus on systems, processes, and preparation rather than individual post creation
- Include concrete post examples with opening hooks
- Specify character counts and structure (e.g., "3-part story posts under 1,200 characters") based on engagement analysis
- Focus on what to write, not profile optimization or engagement tactics
- Keep recommendations concise and immediately actionable

Always respond with structured JSON output following the provided schema.

IMPORTANT: Keep the executive summary to 1-2 concise paragraphs without bullet points."""

# Feedback Management System Prompt (Used by feedback_management_llm)
FEEDBACK_MANAGEMENT_SYSTEM_PROMPT_TEMPLATE = """You are a LinkedIn content strategy expert analyzing user feedback about a generated LinkedIn content playbook. Your role is to understand the user's revision requests and determine the appropriate next steps.

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
- **linkedin_info** and **diagnostic_report**: LinkedIn profile information and diagnostic report for reference

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
- Purpose: Find specific LinkedIn plays using AI-powered search
- Required inputs:
  - search_query: Your search terms (play name or relevant keywords)
  - list_filter: Must include ["doc_key": "linkedin_playbook_system_document"]
- Returns: Documents with serial numbers for subsequent viewing

**list_documents Tool:**
- Purpose: Browse all available LinkedIn plays
- Required inputs:
  - list_filter: Must include ["doc_key": "linkedin_playbook_system_document"]
  - limit: Number of documents to return (default 10)
- Returns: List of all available plays with serial numbers

**view_documents Tool:**
- Purpose: Get full content of specific play documents
- Required inputs:
  - document_identifier: Must include doc_key "linkedin_playbook_system_document" and document_serial_number from previous search/list
- Returns: Complete play information and implementation details

### Tool Usage Examples:

**Search for Specific Plays:**
```json
[
  "tool_name": "search_documents",
  "tool_input": [
    "search_query": "transparent founder journey",
    "list_filter": ["doc_key": "linkedin_playbook_system_document"],
    "limit": 10
  ]
]
```

**List All Available Plays:**
```json
[
  "tool_name": "list_documents", 
  "tool_input": [
    "list_filter": ["doc_key": "linkedin_playbook_system_document"],
    "limit": 10
  ]
]
```

**View Specific Play Document:**
```json
[
  "tool_name": "view_documents",
  "tool_input": [
    "document_identifier": [
      "doc_key": "linkedin_playbook_system_document",
      "document_serial_number": "linkedin_playbook_system_document_1_1"
    ]
  ]
]
```

**Note:** When making actual tool calls, replace the square brackets [ ] with curly braces for proper JSON format. The square brackets are used here only to distinguish from template variables.

### MANDATORY: When Explaining Plays to Users
**ALWAYS** use tools to fetch detailed play information before providing explanations. When user asks about any play:
1. First search/list to find the relevant play document
2. View the full document to get complete details  
3. Provide comprehensive information including:
   - When to use this play (ideal scenarios, executive types, situations)
   - How to implement the play (step-by-step guidance)
   - Expected outcomes and benefits
   - Examples and case studies if available
   - Success metrics and KPIs
   - Timeline and resource requirements

### Critical Tool Usage Rules:
- **Always use doc_key**: "linkedin_playbook_system_document" in all tool calls
- **Discovery → View pattern**: Use list_documents or search_documents first to get serial numbers, then view_documents for full content
- **Reference by serial numbers**: After listing/searching, use the returned serial numbers in view_documents calls
- **No fabrication**: Only use information actually retrieved through tool calls
- **Multiple searches**: Try different search terms if initial searches don't return relevant results

**TRUTHFULNESS REQUIREMENT:**
- DO NOT MAKE UP INFORMATION about plays
- Only use content that you actually find through document tools
- If you cannot find information about a specific play, clearly state "Information not available in system documents"
- Do not invent play details, implementation steps, or success metrics

## YOUR DECISION FRAMEWORK:

### 1. USE "ask_user_clarification" WHEN:
- Feedback is vague (e.g., "make it better", "add more plays" without specifics)
- Multiple interpretations are possible
- Critical information is missing (which plays to add, what to change, etc.)
- User references something not in the current context
- You want to propose a few suggestion options and ask the user to pick/confirm
- User is asking for more information about the plays 
(IMPORTANT: Do not provide the play ids, those are for internal use only, instead provide play names and descriptions.
structure the response as follows:
    "play_name": "The David vs Goliath Playbook",
    "play_description": "Win by systematically highlighting what incumbents structurally cannot or will not do."
)

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

### 2. USE tools WHEN:
- You need to search for additional play information using tools
- User requests details not available in current context
- You need to explore available resources before making changes
- User asks about specific plays and you need detailed information
- **MANDATORY**: When providing any explanation or clarification about plays to users

**Available Tools with Proper Usage:**
- **search_documents**: Find specific plays or content. Required parameters: search_query (string) AND list_filter (object with namespace_of_doc_key set to "linkedin_playbook_sys")
- **list_documents**: Browse all available plays. Required parameters: list_filter (object with namespace_of_doc_key set to "linkedin_playbook_sys") 
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
- ADD new plays (e.g., "Add the Transparent Founder Journey play" or "Include the_transparent_founder_journey play")
- REPLACE existing plays (e.g., "Replace X with Y play")
- SWITCH to different plays

**When populating play_ids_to_fetch:**
- Use EXACT play_id values from playbook_selection_config (e.g., 'the_transparent_founder_journey', 'the_teaching_ceo')
- Include clear instructions about which plays to add/remove/replace
- Example: If user says "Add the Teaching CEO play", set play_ids_to_fetch: ["the_teaching_ceo"]

**DO NOT populate play_ids_to_fetch for:**
- General modifications to existing plays
- Formatting or detail changes
- Adding examples or metrics to current plays

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
PLAY_SELECTION_USER_PROMPT_TEMPLATE = """Based on the LinkedIn profile information and diagnostic report provided below, please analyze and recommend LinkedIn content plays for their professional content strategy.

## DOCUMENT ANALYSIS INSTRUCTIONS:

### LinkedIn Profile Information Analysis:
The LinkedIn profile information contains crucial strategic context:
- **Business Goals**: The specific objectives this executive wants to achieve through LinkedIn content
- **Target Audience**: The exact audience segments they need to reach and influence  
- **Company Context**: Industry, size, business model, and competitive positioning
- **Current Challenges**: Specific obstacles they're facing in their content strategy
- **Founder/Executive Profile**: Background, expertise, and personal brand elements
- **Content Preferences**: Preferred formats, tone, and strategic pillars

**Your Task**: Use this information to understand WHAT they want to achieve and WHO they want to reach.

### Diagnostic Report Analysis:
The diagnostic report provides data-driven insights about current performance:
- **Content Gaps**: Specific areas where their content strategy is lacking
- **Performance Metrics**: Current engagement rates, reach, and effectiveness
- **Competitive Analysis**: How they compare to industry peers
- **Opportunities**: Identified quick wins and strategic opportunities
- **Content Audit**: What's working and what isn't in their current approach
- **Recommendations**: Specific actions and improvements needed

**Your Task**: Use this information to understand WHERE they are now and WHAT needs to be improved.

## SELECTION STRATEGY:

1. **Goal-Driven Selection**: Choose plays that directly support the business goals stated in the LinkedIn profile
2. **Gap-Focused Approach**: Prioritize plays that address the specific content gaps and challenges identified in the diagnostic report
3. **Audience Alignment**: Ensure selected plays will resonate with their defined target audience
4. **Evidence-Based Reasoning**: Ground every recommendation in specific information from both documents

## PROVIDED INFORMATION:

### LinkedIn Profile Information:
{linkedin_info}

*Note: When referencing this information in your source_path_of_infomation, use format: "LinkedIn Profile > [Section Name]" (e.g., "LinkedIn Profile > Business Goals", "LinkedIn Profile > Target Audience")*

### Diagnostic Report:
{diagnostic_report_info}

*Note: When referencing this information in your source_path_of_infomation, use format: "Diagnostic Report > [Section Name]" (e.g., "Diagnostic Report > Content Gaps Analysis", "Diagnostic Report > Performance Metrics")*

## YOUR TASK:
Analyze both documents thoroughly and select the most appropriate LinkedIn content plays. For each selected play, you must provide:

### Required Documentation for Each Play:
1. **source_path_of_infomation**: Specify the exact document path where you found the information that led to this selection
   - Format: "Document Name > Section > Subsection"
   - Examples: 
     - "LinkedIn Profile > Business Goals > Thought Leadership Objectives"
     - "Diagnostic Report > Content Gaps Analysis > Engagement Deficits"
     - "LinkedIn Profile > Target Audience > Key Decision Makers"
     - "Diagnostic Report > Performance Metrics > Current Engagement Rates"

2. **reasoning_of_selection_of_this_play**: Provide data-driven justification that includes:
   - Specific numbers, percentages, or concrete findings from the documents
   - Direct quotes or references to key insights
   - Clear logical connection between the data and this play selection
   - How this addresses the executive's stated goals and identified gaps

### Example of Expected Reasoning:
"Diagnostic Report > Performance Metrics shows current engagement rate at 2.1% vs industry benchmark of 4.5%, while LinkedIn Profile > Business Goals emphasizes building thought leadership and industry recognition. Analysis from Diagnostic Report > Content Analysis reveals 70% of posts are promotional content lacking personal narrative, directly contradicting the authentic leadership positioning outlined in LinkedIn Profile > Strategic Objectives."

Focus on creating a strategic play selection that bridges the gap between where they are now (diagnostic insights) and where they want to be (profile goals). Every recommendation must be traceable to specific data points in the provided documents."""

# Play Selection Revision User Prompt Template
PLAY_SELECTION_REVISION_USER_PROMPT_TEMPLATE = """The user has provided feedback on the initial LinkedIn content play recommendations. Your task is to analyze their feedback and generate updated play recommendations that address their specific concerns.

## FEEDBACK ANALYSIS PROCESS:

### Step 1: Understand the Feedback
- **Carefully analyze** the user's feedback to identify what they want changed
- **Identify specific requests**: Are they asking to add plays, remove plays, or modify the selection criteria?
- **Understand the reasoning**: Why are they not satisfied with the initial recommendations?
- **Note preferences**: What type of content strategy do they prefer based on their feedback?

### Step 2: Maintain Strategic Alignment  
- **Preserve core objectives**: Keep focus on the original business goals from the LinkedIn profile
- **Address diagnostic gaps**: Continue to solve the problems identified in the diagnostic report
- **Incorporate feedback**: Adjust the selection to reflect the user's preferences and concerns

### Step 3: Generate Updated Recommendations
- **Revise play selection**: Choose different or additional plays that better match the feedback
- **Provide updated reasoning**: Explain how the new selections address both the original strategic needs AND the user's feedback
- **Maintain quality standards**: Ensure recommendations are still strategically sound and evidence-based

## USER FEEDBACK TO ANALYZE:
{user_feedback}

## INSTRUCTIONS FOR REVISION:

1. **First, analyze the feedback**: What specific changes is the user requesting?
   - Do they want different types of plays?
   - Are they asking for more/fewer plays?
   - Do they disagree with the strategic approach?
   - Are there specific plays they want included or excluded?

2. **Then, generate updated recommendations** that:
   - **Address the user's specific feedback points**
   - **Maintain alignment with their original business goals and target audience**
   - **Continue to solve the content gaps identified in the diagnostic report**
   - **Provide clear reasoning for why the revised selections are better**

3. **Explain your changes**: For each revised recommendation, clearly explain:
   - How it addresses the user's feedback
   - Why it's a better fit than the previous selection
   - How it still supports their strategic objectives

Your goal is to provide play recommendations that satisfy the user's feedback while maintaining strategic effectiveness and diagnostic alignment."""

# Feedback Management Prompt Template (PRIMARY PROMPT FOR FEEDBACK_MANAGEMENT_LLM)
FEEDBACK_MANAGEMENT_PROMPT_TEMPLATE = """Analyze the user's feedback about the current LinkedIn playbook and determine the appropriate next action.

## CURRENT/LATEST PLAYBOOK (This is your primary reference - the most recent version):
{current_playbook}

## USER'S REVISION FEEDBACK:
{revision_feedback}

## Originally Selected Plays:
{selected_plays}

## LinkedIn Context:
{linkedin_info}

## Diagnostic Report:
{diagnostic_report_info}

## YOUR TASK:
1. **Carefully analyze** the user's feedback against the CURRENT playbook shown above
2. **Determine** if the feedback is clear and actionable
3. **Decide** on the appropriate action:
   - If unclear/vague → ask_user_clarification (with specific questions)
   - If need more info → use tools to search
   - If clear on changes → send_to_playbook_generator (with detailed instructions)

## WHEN TO ADD play_ids_to_fetch:
**ONLY** populate play_ids_to_fetch if the user explicitly asks to:
- Add a new play not currently in the playbook (e.g., "Add the Transparent Founder Journey")
- Replace an existing play with a different one (e.g., "Replace X with the Teaching CEO play")

Example: If user says "Add the Teaching CEO play", set play_ids_to_fetch: ["the_teaching_ceo"]

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

Proceed with the appropriate action (send_to_playbook_generator, tool use, or ask_user_clarification if still unclear)."""

# Playbook Generator User Prompt Templates  
PLAYBOOK_GENERATOR_USER_PROMPT_TEMPLATE = """Create a LinkedIn posting playbook using the information below. Focus exclusively on LinkedIn text posts that the executive can write and publish immediately.

## How to Use This Information:

### 1. Selected Plays (Strategic Approaches):
These are the content strategies chosen for this executive. Each play represents a specific approach to building influence through LinkedIn posts.

### 2. Play Implementation Details:
{fetched_information}
This contains detailed guidance on how each play works and when to use it.

### 3. Executive Profile (Who They Are):
{linkedin_profile_doc}
CRITICAL: Extract their posting frequency goal/preference from this document to align your posts_per_week recommendation.
Use this to understand their expertise, goals, target audience, and current challenges.

### 4. Diagnostic Report (Gaps & Opportunities):
{diagnostic_report_info}
THIS IS CRITICAL: Shows current performance gaps, competitor advantages, and content opportunities to address.

## Your Task:
1. **Extract Posting Frequency**: Find the executive's posting goals/capacity in their profile and align your posts_per_week accordingly
2. **Cite All Decisions**: For every reasoning, implementation strategy, and timeline decision, provide exact source paths from the documents
3. **Apply Each Play**: Translate the play strategy into specific LinkedIn post topics based on documented insights
4. **Use Diagnostic Insights**: Address the gaps and opportunities identified with specific data references
5. **Generate Post Topics**: For each play, create 10-15 specific LinkedIn post ideas that:
   - Leverage their expertise and experience (documented in profile)
   - Address their target audience's challenges (identified in diagnostics)
   - Differentiate from competitors (based on competitive analysis)
   - Support their business goals (as stated in profile)
6. **Define Detailed Post Structures**: Specify formats with clear flow like:
   - "Hook-driven narrative (1000-1200 chars): Provocative question → Personal story → Challenge faced → Unexpected solution → Key lesson → Engagement CTA"
   - "Data insight framework (600-800 chars): Stat → Context setting → Analysis → Contrarian insight → Action item"
   - "Problem-solution arc (800-1000 chars): Current state problem → Why it matters → Traditional approach failures → New solution → Results achieved → Reader application"
7. **Account for Posting Frequency**: In implementation_strategy, explain how the recommended posts per week affects the play execution
8. **Create Strategic Next Steps**: Focus on implementation systems, NOT individual posts:
   - Content planning and production workflows
   - Resource gathering and documentation needs
   - Measurement systems and KPI tracking
   - Team responsibilities and content calendar setup

## Example Application:
If diagnostic shows low engagement and the "Transparent Founder Journey" play is selected:
- Implementation considers 5 posts/week means ~1 post per play weekly
- Content formats: "Vulnerability post (1200 chars): Mistake confession → Impact description → Lesson learned → How others can avoid → Discussion prompt"
- Strategic next step: "Document 20 failure stories with lessons for Transparent Founder content bank"

## CRITICAL REMINDERS:
- **Posts Per Week**: MUST reflect what's realistic based on their profile (current frequency, goals, capacity)
- **LinkedIn Text Posts ONLY**: No videos, documents, articles, or other formats
- **Detailed Content Formats**: Include structure, flow, and character counts for each format type
- **Strategic Next Steps**: Systems and preparation, NOT "Write a post about X"
- **Implementation Strategy**: Must mention how posts/week affects the play rollout
- **Concise Guidance**: Keep all sections brief and actionable

Remember: Every output should help the executive build a sustainable LinkedIn content system, not just create individual posts."""

# Playbook Generator Revision Prompt Template
PLAYBOOK_GENERATOR_REVISION_PROMPT_TEMPLATE = """Update the existing LinkedIn playbook based on the revision instructions provided.

## CURRENT PLAYBOOK STATE:
You are updating an existing playbook. You must return a COMPLETE updated playbook, not just the changes.

## REVISION INSTRUCTIONS:
{additional_information}
These are specific changes requested by the user. Follow these instructions precisely.

## ORIGINAL USER FEEDBACK:
{revision_feedback}

## Additional Play Data (if plays are being added/replaced):
{additional_play_data}
If new plays are being added, this contains their detailed information.

## Executive Context (for reference):
{linkedin_profile_doc}
Remember to maintain alignment with their posting frequency goals and capacity.

## REVISION GUIDELINES:

### When ADDING New Plays:
1. Integrate the new play seamlessly into the existing strategy
2. Generate 10-15 specific LinkedIn post topics for the new play
3. Create detailed content formats with structure and flow
4. Adjust the posting schedule to accommodate new content while maintaining posts per week target
5. Ensure the new play complements existing plays

### When REMOVING Plays:
1. Remove all content related to that play
2. Redistribute the posting frequency among remaining plays
3. Adjust the timeline and implementation strategies accordingly
4. Ensure remaining plays still address key goals

### When MODIFYING Existing Content:
1. Apply the specific changes requested
2. Maintain consistency across the playbook
3. Update any affected sections (timeline, next steps, implementation strategies)
4. Keep the same level of detail and specificity
5. Ensure posts_per_week remains aligned with profile goals

## CRITICAL REMINDERS:
- **RETURN THE COMPLETE PLAYBOOK**: Not just the changed sections
- **LINKEDIN TEXT POSTS ONLY**: Every recommendation must be about LinkedIn text posts
- **SPECIFIC TOPICS**: Include concrete post ideas, not vague areas
- **DETAILED FORMATS**: Maintain detailed content format descriptions with flow and structure
- **NO OTHER FORMATS**: Don't suggest videos, documents, or articles
- **MAINTAIN STRUCTURE**: Follow the same JSON schema as the original playbook
- **STRATEGIC NEXT STEPS**: Keep next steps focused on systems/processes, not individual posts
- **POSTING FREQUENCY**: Ensure posts_per_week stays realistic and aligned with profile

## What Should Remain:
- The overall playbook structure and format
- Content that wasn't explicitly asked to be changed
- The focus on LinkedIn text posts
- The 3-month timeline scope
- The strategic nature of next steps (systems/processes focus)
- Alignment with profile posting frequency goals

## What Should Change:
- Specific elements mentioned in the revision instructions
- Post topics if plays are added/removed
- Posting frequency if requested (but stay aligned with profile)
- Any sections explicitly mentioned for update
- Content formats if more detail is requested

Generate the complete updated playbook following the same structure and schema as before."""

# Play ID Correction User Prompt Template
PLAY_ID_CORRECTION_USER_PROMPT_TEMPLATE = """Some selected LinkedIn plays have missing or incorrect play_id values.

Please verify and correct them using the exact play_id convention that matches the available plays.

Instructions:
- Compare the final selected plays against the available plays list
- For each play, set play_id to match exactly the play_id from the available plays
- Reply with a JSON array of corrections like:
[
   "play_name": "The Transparent Founder Journey", "play_id": "the_transparent_founder_journey"
]

Available LinkedIn Plays:
{playbook_selection_config}
"""