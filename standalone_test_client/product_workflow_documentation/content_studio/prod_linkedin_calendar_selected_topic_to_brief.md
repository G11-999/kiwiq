# LinkedIn Calendar Selected Topic to Brief Workflow

## Overview
This workflow transforms a pre-selected LinkedIn topic from a content calendar into a comprehensive content brief. It loads executive profile and content strategy documents, generates a strategic LinkedIn-specific brief based on the selected topic, provides human-in-the-loop editing and approval with iteration limits, and saves the approved brief for content creation.

## Frontend User Flow
[To be provided later]

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_studio/wf_linkedin_calendar_selected_topic_to_brief.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_calendar_selected_topic_to_brief.py`

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point that receives a pre-selected LinkedIn topic.

**Process**:
- Receives entity_username for document operations
- Accepts selected_topic containing title, description, theme, and objective
- Takes brief_uuid for unique brief identification
- Sets initial_status (defaults to "draft")

### 2. Load Executive and Playbook
**Node ID**: `load_executive_and_playbook`

**Purpose**: Loads executive profile and content strategy documents.

**Process**:
- Loads LinkedIn user profile document for executive context
- Loads LinkedIn content playbook document for strategy
- Both documents loaded from customer namespace
- Provides personalization and strategic alignment

### 3. Brief Generation LLM
**Node ID**: `brief_generation_llm`

**Purpose**: Generates comprehensive LinkedIn content brief from topic.

**Process**:
- Uses prompt constructor (`construct_brief_generation_prompt`)
- Creates LinkedIn-specific brief with platform best practices
- Incorporates executive voice and content strategy
- Generates structured brief with hook, body, and CTA

**Prompt Configuration**:
- **System Prompt**: [`BRIEF_GENERATION_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_calendar_selected_topic_to_brief.py#LBRIEF_GENERATION_SYSTEM_PROMPT)
- **User Template**: [`BRIEF_GENERATION_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_calendar_selected_topic_to_brief.py#LBRIEF_GENERATION_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `selected_topic`: Pre-selected topic from calendar
  - `executive_profile_doc`: Executive LinkedIn profile
  - `playbook_doc`: Content strategy playbook
- **Output Schema**: [`BRIEF_GENERATION_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_calendar_selected_topic_to_brief.py#LBRIEF_GENERATION_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: anthropic
- Model: claude-sonnet-4-20250514
- Temperature: 0.7
- Max Tokens: 4000

### 4. Save as Draft After Generation
**Node ID**: `save_as_draft_after_generation`

**Purpose**: Automatically saves initial brief as draft.

**Process**:
- Stores generated brief in customer namespace
- Uses brief_uuid for unique identification
- Saves with draft status
- Document name pattern: "linkedin_brief_{brief_uuid}"
- Enables versioning for tracking changes

### 5. Brief Approval HITL
**Node ID**: `brief_approval_hitl`

**Purpose**: Human review and approval of generated brief.

**Process**:
- Presents generated LinkedIn brief for review
- Allows manual editing of brief content
- Provides approval options:
  - Approve: Finalizes the brief
  - Request revision: Enters feedback loop
  - Save as draft: Saves current version
  - Cancel: Deletes draft and ends workflow

### 6. Analyze Brief Feedback LLM (Conditional)
**Node ID**: `analyze_brief_feedback`

**Purpose**: Processes feedback when revision is requested.

**Process**:
- Activated when iteration limit not exceeded (max 10 iterations)
- Uses `construct_brief_feedback_prompt` to analyze user feedback
- Identifies specific changes needed for LinkedIn context
- Generates revision instructions for brief update

**Prompt Configuration**:
- **System Prompt**: [`BRIEF_FEEDBACK_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_calendar_selected_topic_to_brief.py#LBRIEF_FEEDBACK_SYSTEM_PROMPT)
- **Initial User Prompt**: [`BRIEF_FEEDBACK_INITIAL_USER_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_calendar_selected_topic_to_brief.py#LBRIEF_FEEDBACK_INITIAL_USER_PROMPT)
- **Additional User Prompt**: [`BRIEF_FEEDBACK_ADDITIONAL_USER_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_calendar_selected_topic_to_brief.py#LBRIEF_FEEDBACK_ADDITIONAL_USER_PROMPT)
- **Output Schema**: [`BRIEF_FEEDBACK_ANALYSIS_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_calendar_selected_topic_to_brief.py#LBRIEF_FEEDBACK_ANALYSIS_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: anthropic
- Model: claude-sonnet-4-20250514
- Temperature: 0.5
- Max Tokens: 3000

### 7. Save Brief
**Node ID**: `save_brief`

**Purpose**: Saves the approved brief as final version.

**Process**:
- Updates brief status to "approved"
- Stores in customer namespace with versioning
- Maintains brief_uuid for tracking
- Document ready for LinkedIn content creation workflow

### 8. Save as Draft (Alternative Path)
**Node ID**: `save_as_draft`

**Purpose**: Saves current version as draft when user chooses to pause.

**Process**:
- Updates draft with current brief content
- Maintains draft status
- Returns to approval HITL for continued editing
- Allows iterative refinement

### 9. Delete on Cancel
**Node ID**: `delete_on_cancel`

**Purpose**: Removes draft when user cancels the workflow.

**Process**:
- Deletes the draft brief from storage
- Cleans up temporary data
- Ends workflow without saving

## Workflow Flow Control

The workflow includes routing and iteration management:

- **route_brief_approval**: Routes based on user action
  - Approved → save_brief
  - Needs revision → check_iteration_limit
  - Save draft → save_as_draft
  - Cancel → delete_on_cancel

- **check_iteration_limit**: Prevents infinite feedback loops
- **route_on_limit_check**: Routes based on iteration count

## Workflow Configuration
- **Maximum Iterations**: 10 (for feedback loops)
- **Primary LLM**: Claude Sonnet (Anthropic) for brief generation
- **Feedback LLM**: Claude Sonnet for feedback analysis
- **Temperature**: 0.7 for generation, 0.5 for feedback
- **Max Tokens**: 4000 for generation, 3000 for feedback
- **Document Versioning**: Enabled for all brief documents
- **LinkedIn-Specific**: Optimized for LinkedIn platform best practices