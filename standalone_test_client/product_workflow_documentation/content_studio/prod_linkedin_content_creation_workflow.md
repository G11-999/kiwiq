# LinkedIn Content Creation Workflow

## Overview
This workflow transforms a LinkedIn content brief into a complete, platform-optimized post. It loads user profile, content playbook, and brief documents, generates LinkedIn-specific content with engagement hooks, provides human-in-the-loop approval with iterative feedback, and saves approved posts with proper versioning.

## Frontend User Flow
[To be provided later]

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_studio/wf_linkedin_content_creation_workflow.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_content_creation_workflow.py`

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point with brief and user identifiers.

**Process**:
- Receives post_uuid for unique post identification
- Accepts brief_docname to identify source brief
- Takes entity_username for document operations
- Sets initial_status (defaults to "draft")

### 2. Load All Context Docs
**Node ID**: `load_all_context_docs`

**Purpose**: Loads comprehensive context for content creation.

**Process**:
- Loads LinkedIn content brief using brief_docname
- Loads LinkedIn user profile for voice and style
- Loads LinkedIn content playbook for strategy
- All documents from customer namespace

### 3. Generate Content LLM
**Node ID**: `generate_content`

**Purpose**: Creates LinkedIn post from brief and context.

**Process**:
- Uses prompt constructor (`construct_initial_prompt`) with all context
- Generates LinkedIn-optimized content with hooks and CTAs
- Follows platform best practices for engagement
- Creates structured post with proper formatting

**Prompt Configuration**:
- **System Prompt**: [`POST_CREATION_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_content_creation_workflow.py#LPOST_CREATION_SYSTEM_PROMPT)
- **User Template**: [`POST_CREATION_INITIAL_USER_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_content_creation_workflow.py#LPOST_CREATION_INITIAL_USER_PROMPT)
- **Template Inputs**:
  - `content_brief`: Source brief document
  - `linkedin_user_profile`: User voice and style
  - `linkedin_content_playbook`: Content strategy
- **Output Schema**: [`POST_LLM_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_content_creation_workflow.py#LPOST_LLM_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: anthropic
- Model: claude-sonnet-4-20250514
- Temperature: 0.5
- Max Tokens: 4000

### 4. Save Draft
**Node ID**: `save_draft`

**Purpose**: Automatically saves generated post as draft.

**Process**:
- Stores LinkedIn post in customer namespace
- Uses post_uuid for identification
- Saves with draft status
- Document name pattern: "linkedin_draft_{post_uuid}"
- Enables versioning

### 5. Capture Approval HITL
**Node ID**: `capture_approval`

**Purpose**: Human review and approval of generated post.

**Process**:
- Presents generated LinkedIn post for review
- Allows approval or revision request
- Options:
  - Approve: Finalizes the post
  - Request changes: Enters feedback loop
  - Save draft: Saves current version
  - Cancel: Deletes draft

### 6. Analyze User Feedback LLM (Conditional)
**Node ID**: `analyze_user_feedback`

**Purpose**: Processes feedback for post revision.

**Process**:
- Activated when revision requested and limit not exceeded (max 10)
- Uses `construct_feedback_prompt` to analyze user input
- Identifies specific changes for LinkedIn optimization
- Generates revision instructions

**Prompt Configuration**:
- **System Prompt**: [`USER_FEEDBACK_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_content_creation_workflow.py#LUSER_FEEDBACK_SYSTEM_PROMPT)
- **Initial User Prompt**: [`USER_FEEDBACK_INITIAL_USER_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_content_creation_workflow.py#LUSER_FEEDBACK_INITIAL_USER_PROMPT)
- **Additional User Prompt**: [`USER_FEEDBACK_ADDITIONAL_USER_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_content_creation_workflow.py#LUSER_FEEDBACK_ADDITIONAL_USER_PROMPT)

**Model Configuration**:
- Provider: anthropic
- Model: claude-sonnet-4-20250514
- Temperature: 0.5
- Max Tokens: 4000

### 7. Update Draft
**Node ID**: `update_draft`

**Purpose**: Saves approved post as final version.

**Process**:
- Updates post status to "approved"
- Stores in customer namespace
- Maintains post_uuid for tracking
- Ready for publishing

### 8. Delete Draft on Cancel
**Node ID**: `delete_draft_on_cancel`

**Purpose**: Removes draft when cancelled.

**Process**:
- Deletes draft from storage
- Cleans up temporary data
- Ends workflow without saving

## Workflow Flow Control

Includes routing for feedback management:

- **route_on_approval**: Routes based on user decision
  - Approved → update_draft
  - Needs changes → check_iteration_limit
  - Save draft → returns to approval
  - Cancel → delete_draft_on_cancel

- **check_iteration_limit**: Prevents infinite loops
- **route_on_iteration_limit**: Routes based on count

## Workflow Configuration
- **Maximum Iterations**: 10
- **Primary LLM**: Claude Sonnet (Anthropic)
- **Temperature**: 0.5 (balanced creativity)
- **Max Tokens**: 4000
- **LinkedIn Optimization**: Platform-specific formatting
- **Document Versioning**: Enabled for all posts