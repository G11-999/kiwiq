# Blog User Input to Brief Workflow

## Overview
This workflow transforms user content ideas into comprehensive blog briefs through research and topic generation. It performs Google and Reddit research for real-time insights, generates AI-powered topic suggestions with human selection, creates detailed content briefs with SEO and structure guidelines, and includes human-in-the-loop approval with manual editing support.

## Frontend User Flow
[To be provided later]

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_studio/wf_blog_user_input_to_brief.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py`

## Key Components

### 1. Context Loading Stage
**Node IDs**:
- Input: `input_node`
- Load: `load_company_doc`

**Purpose**: Establishes foundational company and strategy context for all subsequent operations.

**Inputs Required**:
- `company_name`: Name of the company for document operations
- `user_input`: User's content ideas, brainstorm, or transcript  
- `brief_uuid`: UUID of the brief being generated
- `initial_status`: Initial status of the workflow (default: "draft")

**Documents Loaded**:
- Company Profile Document
- Content Strategy/Playbook Document

### 2. Google Research Phase
**Node IDs**:
- LLM: `google_research_llm`

**Purpose**: Gathers high-quality web insights and industry trends relevant to the user's content ideas.

**Process**:
- Generates 3-5 precise research queries based on company context and user input
- Performs web searches on google.com for authoritative sources
- Extracts top 5 most relevant and practical web resources
- Identifies key themes and "People Also Asked" questions
- Documents reasoning for each source selection

**Prompt Configuration**:
- **System Prompt**: [`GOOGLE_RESEARCH_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LGOOGLE_RESEARCH_SYSTEM_PROMPT)
- **User Template**: [`GOOGLE_RESEARCH_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LGOOGLE_RESEARCH_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `company_doc`: Company profile and positioning information
  - `user_input`: Original user's content ideas and requirements
- **Output Schema**: [`GOOGLE_RESEARCH_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LGOOGLE_RESEARCH_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: Perplexity
- Model: sonar-pro
- Temperature: 0.3
- Max Tokens: 3000

### 3. Reddit Research Phase
**Node IDs**:
- LLM: `reddit_research_llm`

**Purpose**: Understands real user pain points, questions, and discussion patterns from Reddit communities.

**Process**:
- Generates 5-7 Reddit-specific search queries building on Google research
- Searches reddit.com and quora.com for authentic user discussions
- Extracts and analyzes frequently asked questions
- Groups similar questions by user intent
- Captures variations in how users express their needs

**Prompt Configuration**:
- **System Prompt**: [`REDDIT_RESEARCH_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LREDDIT_RESEARCH_SYSTEM_PROMPT)
- **User Template**: [`REDDIT_RESEARCH_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LREDDIT_RESEARCH_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `company_doc`: Company profile and positioning information
  - `google_research_output`: Results from Google research phase
  - `user_input`: Original user's content ideas
- **Output Schema**: [`REDDIT_RESEARCH_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LREDDIT_RESEARCH_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: Perplexity
- Model: sonar-pro
- Temperature: 0.3
- Max Tokens: 3000
- Domain Filter: reddit.com, quora.com

### 4. Topic Generation Stage
**Node IDs**:
- LLM: `topic_generation_llm`
- HITL: `topic_selection_hitl`
- Router: `route_topic_selection`

**Purpose**: Creates strategic blog topic ideas that address both SEO opportunities and user needs.

**Process**:
- Analyzes insights from both Google and Reddit research
- Generates 3-5 blog topic suggestions aligned with company expertise
- Provides clear reasoning connecting each topic to research findings
- Ensures topics offer fresh angles, frameworks, or case study formats
- Avoids clickbait while maintaining engagement potential

**Prompt Configuration**:
- **System Prompt**: [`TOPIC_GENERATION_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LTOPIC_GENERATION_SYSTEM_PROMPT)
- **User Template**: [`TOPIC_GENERATION_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LTOPIC_GENERATION_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `company_doc`: Company profile and positioning
  - `content_playbook_doc`: Content strategy and guidelines
  - `google_research_output`: Google research results
  - `reddit_research_output`: Reddit research findings
  - `user_input`: Original user requirements
- **Output Schema**: [`TOPIC_GENERATION_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LTOPIC_GENERATION_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: OpenAI
- Model: gpt-4.1
- Temperature: 0.7
- Max Tokens: 4000

### 5. Human-in-the-Loop Topic Selection
**Node IDs**:
- HITL: `topic_selection_hitl`
- Router: `route_topic_selection`
- Filter: `filter_selected_topic`

**Purpose**: Enables human review and selection of the most appropriate topic with iterative refinement options.

**User Actions Available**:
- **Complete**: Accept a specific topic and proceed to brief generation
- **Provide Feedback**: Request topic regeneration with specific guidance
- **Cancel Workflow**: Exit the workflow without generating a brief

**Feedback Processing**:
**Node IDs for Feedback Loop**:
- LLM: `analyze_topic_feedback`
- LLM: `topic_regeneration_llm`

When feedback is provided, the system:
- **Feedback Analysis Prompt**: [`TOPIC_FEEDBACK_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LTOPIC_FEEDBACK_SYSTEM_PROMPT)
- **Feedback User Template**: [`TOPIC_FEEDBACK_INITIAL_USER_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LTOPIC_FEEDBACK_INITIAL_USER_PROMPT)
- **Template Inputs**:
  - `suggested_blog_topics`: Current topic suggestions
  - `regeneration_feedback`: User's feedback text
  - `company_doc`: Company context
  - `content_playbook_doc`: Content strategy
  - `google_research_output`: Google research
  - `reddit_research_output`: Reddit research
  - `user_input`: Original requirements
- Generates new topics incorporating the feedback
- Maintains context from previous suggestions
- Limits iterations to prevent infinite loops (max: 10)

### 6. Brief Generation Stage
**Node IDs**:
- LLM: `brief_generation_llm`
- Save: `save_as_draft_after_brief_generation`

**Purpose**: Creates a comprehensive content brief with all necessary elements for content creation.

**Process**:
- Uses selected topic and all accumulated research data
- Generates structured content outline with clear sections
- Defines target audience and content goals
- Creates SEO keyword strategy
- Provides detailed section breakdowns with word counts
- Includes brand guidelines and tone specifications

**Prompt Configuration**:
- **System Prompt**: [`BRIEF_GENERATION_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LBRIEF_GENERATION_SYSTEM_PROMPT)
- **User Template**: [`BRIEF_GENERATION_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LBRIEF_GENERATION_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `company_doc`: Company profile and positioning
  - `content_playbook_doc`: Content strategy guidelines
  - `selected_topic`: The chosen topic from selection phase
  - `google_research_output`: Google research results
  - `reddit_research_output`: Reddit research findings
  - `user_input`: Original user requirements
- **Output Schema**: [`BRIEF_GENERATION_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LBRIEF_GENERATION_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: OpenAI
- Model: gpt-4.1
- Temperature: 0.7
- Max Tokens: 4000

**Generated Brief Includes**:
- Title and target audience definition
- Content goal and key takeaways
- Detailed content structure with sections
- SEO keywords (primary and secondary)
- Brand voice guidelines
- Research sources and citations
- Call to action strategy
- Estimated word count
- Content difficulty level
- Specific writing instructions

### 7. Human-in-the-Loop Brief Approval
**Node IDs**:
- HITL: `brief_approval_hitl`
- Router: `route_brief_approval`
- Save (Draft): `save_as_draft`
- Save (Final): `save_brief`

**Purpose**: Allows human review, editing, and approval of the generated brief with revision options.

**User Actions Available**:
- **Complete**: Approve the brief as final
- **Provide Feedback**: Request revisions with specific instructions
- **Draft**: Save current version as draft and continue editing
- **Cancel Workflow**: Exit without saving

**Manual Editing Capability**:
Users can directly edit any part of the brief content before approval, including:
- Modifying the title or sections
- Adjusting word counts or structure
- Updating SEO keywords
- Refining writing instructions

**Feedback Processing**:
**Node IDs for Feedback Loop**:
- Check: `check_iteration_limit`
- Router: `route_on_limit_check`
- LLM: `analyze_brief_feedback`
- LLM: `brief_revision_llm`

When revision is requested:
- **Feedback Analysis Prompt**: [`BRIEF_FEEDBACK_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LBRIEF_FEEDBACK_SYSTEM_PROMPT)
- **Feedback User Template**: [`BRIEF_FEEDBACK_INITIAL_USER_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LBRIEF_FEEDBACK_INITIAL_USER_PROMPT)
- **Template Inputs**:
  - `content_brief`: Current brief version
  - `revision_feedback`: User's revision feedback
  - `company_doc`: Company context
  - `content_playbook_doc`: Content strategy
  - `selected_topic`: Selected topic
  - `google_research_output`: Google research
  - `reddit_research_output`: Reddit research
  - `user_input`: Original requirements
- Regenerates brief incorporating specific changes
- Preserves successful elements from previous version
- Limits iterations to prevent infinite loops (max: 10)

### 8. Document Storage and Versioning
**Node IDs**:
- Save (After Generation): `save_as_draft_after_brief_generation`
- Save (Draft): `save_as_draft`
- Save (Final): `save_brief`
- Output: `output_node`

**Auto-Save Points**:
- After initial brief generation (as draft)
- When user selects "Save as Draft"
- Upon final approval

**Version Control**:
- All briefs are versioned
- Each save creates a new version
- Previous versions remain accessible
- UUID tracking for brief identification