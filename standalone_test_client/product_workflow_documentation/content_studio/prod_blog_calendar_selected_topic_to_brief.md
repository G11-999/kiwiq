# Blog Calendar Selected Topic to Brief Workflow

## Overview
This workflow transforms a pre-selected topic from a content calendar into a comprehensive blog content brief. It performs web research using Google and Reddit insights, generates a strategic brief based on the selected topic, provides human-in-the-loop editing and approval with iteration limits, and saves the approved brief for blog creation.

## Frontend User Flow
[To be provided later]

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_studio/wf_blog_calendar_selected_topic_to_brief.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_calendar_selected_topic_to_brief.py`

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point that receives a pre-selected topic from content calendar.

**Process**:
- Receives company_name for document operations
- Accepts selected_topic containing title, description, theme, and objective
- Takes brief_uuid for unique brief identification
- Sets initial_status (defaults to "draft")

### 2. Load Company and Playbook Documents
**Node ID**: `load_company_and_playbook`

**Purpose**: Loads company context and content strategy documents.

**Process**:
- Loads company document for brand guidelines and context
- Loads blog content strategy/playbook document
- Both documents loaded from customer namespace
- Schema loading disabled for flexibility

### 3. Google Research LLM
**Node ID**: `google_research_llm`

**Purpose**: Performs web research using Google/Perplexity for topic insights.

**Process**:
- Uses prompt constructor (`construct_google_research_prompt`) to prepare research query
- Leverages Perplexity's Sonar Pro model for web research
- Gathers current trends, statistics, and relevant information
- Provides comprehensive research output for brief generation

**Prompt Configuration**:
- **System Prompt**: [`GOOGLE_RESEARCH_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LGOOGLE_RESEARCH_SYSTEM_PROMPT)
- **User Template**: [`GOOGLE_RESEARCH_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LGOOGLE_RESEARCH_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `company_doc`: Company context and guidelines
  - `user_input`: Selected topic information
- **Output Schema**: [`GOOGLE_RESEARCH_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LGOOGLE_RESEARCH_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: perplexity
- Model: sonar-pro
- Temperature: 0.5
- Max Tokens: 3000

### 4. Reddit Research LLM
**Node ID**: `reddit_research_llm`

**Purpose**: Gathers community insights and discussions from Reddit.

**Process**:
- Uses prompt constructor (`construct_reddit_research_prompt`) with topic context
- Searches Reddit for relevant discussions and user perspectives
- Captures pain points, questions, and community sentiment
- Complements Google research with user-generated content insights

**Prompt Configuration**:
- **System Prompt**: [`REDDIT_RESEARCH_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LREDDIT_RESEARCH_SYSTEM_PROMPT)
- **User Template**: [`REDDIT_RESEARCH_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LREDDIT_RESEARCH_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `company_doc`: Company context
  - `user_input`: Selected topic details
- **Output Schema**: [`REDDIT_RESEARCH_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LREDDIT_RESEARCH_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: perplexity
- Model: sonar-pro
- Temperature: 0.5
- Max Tokens: 3000

### 5. Brief Generation LLM
**Node ID**: `brief_generation_llm`

**Purpose**: Generates comprehensive content brief from research and topic.

**Process**:
- Uses prompt constructor (`construct_brief_generation_prompt`) with all research
- Combines selected topic, company context, and research insights
- Creates detailed brief with structure, key points, and content strategy
- Outputs complete brief ready for review

**Prompt Configuration**:
- **System Prompt**: [`BRIEF_GENERATION_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_calendar_selected_topic_to_brief.py#LBRIEF_GENERATION_SYSTEM_PROMPT)
- **User Template**: [`BRIEF_GENERATION_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_calendar_selected_topic_to_brief.py#LBRIEF_GENERATION_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `selected_topic`: Pre-selected topic from calendar
  - `company_doc`: Company guidelines
  - `playbook_doc`: Content strategy playbook
  - `google_research`: Web research results
  - `reddit_research`: Community insights
- **Output Schema**: [`BRIEF_GENERATION_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py#LBRIEF_GENERATION_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: anthropic
- Model: claude-sonnet-4-20250514
- Temperature: 0.7
- Max Tokens: 8000

### 6. Save as Draft After Generation
**Node ID**: `save_as_draft_after_generation`

**Purpose**: Automatically saves initial brief as draft.

**Process**:
- Stores generated brief in customer namespace
- Uses brief_uuid for unique identification
- Saves with draft status
- Enables versioning for tracking changes
- Document name pattern: "blog_content_brief_{brief_uuid}"

### 7. Brief Approval HITL
**Node ID**: `brief_approval_hitl`

**Purpose**: Human review and approval of generated brief.

**Process**:
- Presents generated brief for review
- Allows manual editing of the brief content
- Provides approval options:
  - Approve: Finalizes the brief
  - Request revision: Enters feedback loop
  - Save as draft: Saves current version
  - Cancel: Deletes draft and ends workflow

### 8. Analyze Brief Feedback LLM (Conditional)
**Node ID**: `analyze_brief_feedback`

**Purpose**: Processes feedback when revision is requested.

**Process**:
- Activated when iteration limit not exceeded (max 10 iterations)
- Uses `construct_brief_feedback_prompt` to analyze user feedback
- Identifies specific changes needed in the brief
- Generates revision instructions for brief update
- Feeds into `construct_brief_revision_prompt` for regeneration

**Prompt Configuration**:
- **System Prompt**: [`BRIEF_FEEDBACK_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_calendar_selected_topic_to_brief.py#LBRIEF_FEEDBACK_SYSTEM_PROMPT)
- **User Template**: [`BRIEF_FEEDBACK_INITIAL_USER_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_calendar_selected_topic_to_brief.py#LBRIEF_FEEDBACK_INITIAL_USER_PROMPT)
- **Output Schema**: [`BRIEF_FEEDBACK_ANALYSIS_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_calendar_selected_topic_to_brief.py#LBRIEF_FEEDBACK_ANALYSIS_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: anthropic
- Model: claude-sonnet-4-20250514
- Temperature: 0.5
- Max Tokens: 3000

### 9. Save Brief
**Node ID**: `save_brief`

**Purpose**: Saves the approved brief as final version.

**Process**:
- Updates brief status to "approved"
- Stores in customer namespace with versioning
- Maintains brief_uuid for tracking
- Document ready for blog generation workflow

### 10. Save as Draft (Alternative Path)
**Node ID**: `save_as_draft`

**Purpose**: Saves current version as draft when user chooses to pause.

**Process**:
- Updates draft with current brief content
- Maintains draft status
- Returns to approval HITL for continued editing
- Allows iterative refinement

### 11. Delete on Cancel
**Node ID**: `delete_on_cancel`

**Purpose**: Removes draft when user cancels the workflow.

**Process**:
- Deletes the draft brief from storage
- Cleans up temporary data
- Ends workflow without saving

## Workflow Configuration
- **Maximum Iterations**: 10 (for feedback loops)
- **Primary LLM**: Claude Sonnet (Anthropic) for brief generation
- **Research LLM**: Sonar Pro (Perplexity) for web research
- **Temperature**: 0.7 for generation, 0.5 for research and feedback
- **Document Versioning**: Enabled for all brief documents