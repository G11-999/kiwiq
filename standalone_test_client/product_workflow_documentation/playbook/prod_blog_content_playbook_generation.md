# Blog Content Playbook Generation Workflow

## Overview
This workflow generates a comprehensive blog content playbook by analyzing company blog documents, selecting relevant content plays based on company context, creating detailed implementation strategies for each play, and providing actionable recommendations with timelines. The workflow includes human-in-the-loop approval for play selection and playbook review.

## Frontend User Flow
This workflow is triggered when users want to generate a strategic blog content playbook. Users access this through the playbook generation section to create customized blog content strategies based on their company's unique profile and needs.

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/playbook/wf_blog_content_playbook_generation.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/blog_content_playbook_generation.py`

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point for the workflow that accepts entity username and playbook configuration.

**Process**: 
- Receives entity_username for document operations
- Accepts optional playbook_selection_config with predefined content plays (defaults to 13 strategic plays)
- The CONFIG includes plays like "The Problem Authority Stack", "The Category Pioneer Manifesto", "The David vs Goliath Playbook", etc.

### 2. Load Company Documents
**Node ID**: `load_company_doc`

**Purpose**: Loads essential company documents needed for playbook generation.

**Process**:
- Loads company blog document using entity_username
- Optionally loads blog content strategy document if available
- Optionally loads blog content diagnostic report if available
- Documents are loaded from customer namespace with versioning enabled

### 3. Play Selection LLM
**Node ID**: `play_suggestion_llm`

**Purpose**: Analyzes company documents and selects appropriate content plays.

**Process**:
- Routes through prompt constructor nodes based on whether diagnostic report exists
- If diagnostic report exists, uses `construct_play_selection_prompt` with detailed analysis
- If starting from scratch, uses `construct_play_selection_prompt_from_scratch`
- Validates selected play IDs against available plays
- If invalid IDs found, corrects them through `construct_play_id_correction_prompt`

**Prompt Configuration**:
- **System Prompt (with diagnostics)**: [`PLAY_SELECTION_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/blog_content_playbook_generation.py#LPLAY_SELECTION_SYSTEM_PROMPT)
- **System Prompt (from scratch)**: [`PLAY_SELECTION_SYSTEM_PROMPT_FROM_SCRATCH`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/blog_content_playbook_generation.py#LPLAY_SELECTION_SYSTEM_PROMPT_FROM_SCRATCH)
- **User Template**: [`PLAY_SELECTION_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/blog_content_playbook_generation.py#LPLAY_SELECTION_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `company_blog_doc`: Company blog information
  - `blog_content_diagnostic_report`: Diagnostic analysis (optional)
  - `blog_content_strategy`: Content strategy (optional)
  - `available_plays`: List of strategic plays to choose from
- **Output Schema**: [`PLAY_SELECTION_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/blog_content_playbook_generation.py#LPLAY_SELECTION_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: openai
- Model: gpt-5
- Temperature: 0.7
- Max Tokens: 20000

### 4. Play Selection HITL
**Node ID**: `play_selection_hitl`

**Purpose**: Human review and approval of selected plays.

**Process**:
- Presents flattened play recommendations to human reviewer
- Allows approval, rejection, or revision of selected plays
- Routes to different paths based on user action:
  - Approved: Proceeds to playbook generation
  - Rejected: Ends workflow
  - Revision needed: Returns to play selection with feedback

### 5. Load Selected Playbooks
**Node ID**: `load_selected_playbooks`

**Purpose**: Loads detailed playbook content for selected plays.

**Process**:
- Filters and prepares load configurations for approved plays
- Loads playbook documents from system namespace
- Each playbook contains detailed implementation guidance
- Playbooks are pre-written strategic templates stored as system entities

### 6. Playbook Generator LLM
**Node ID**: `playbook_generator_llm`

**Purpose**: Generates customized playbook based on selected plays and company context.

**Process**:
- Routes through prompt constructor based on diagnostic report availability
- Synthesizes selected playbooks with company-specific context
- Creates implementation timeline and specific recommendations
- Supports document search through tool executor for additional context

**Prompt Configuration**:
- **System Prompt (with diagnostics)**: [`PLAYBOOK_GENERATOR_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/blog_content_playbook_generation.py#LPLAYBOOK_GENERATOR_SYSTEM_PROMPT)
- **System Prompt (from scratch)**: [`PLAYBOOK_GENERATOR_SYSTEM_PROMPT_FROM_SCRATCH`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/blog_content_playbook_generation.py#LPLAYBOOK_GENERATOR_SYSTEM_PROMPT_FROM_SCRATCH)
- **User Template**: [`PLAYBOOK_GENERATOR_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/blog_content_playbook_generation.py#LPLAYBOOK_GENERATOR_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `company_blog_doc`: Company information
  - `selected_playbooks`: Detailed playbook content
  - `blog_content_diagnostic_report`: Diagnostic insights (optional)
  - `blog_content_strategy`: Strategy document (optional)
- **Output Schema**: [`PLAYBOOK_GENERATOR_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/blog_content_playbook_generation.py#LPLAYBOOK_GENERATOR_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: openai  
- Model: gpt-5
- Temperature: 0.7
- Max Tokens: 20000
- Tool Support: Document search enabled

### 7. Playbook Review HITL
**Node ID**: `playbook_review_hitl`

**Purpose**: Human review of generated playbook.

**Process**:
- Presents complete playbook for review
- Allows approval or revision request
- If revision needed, enters feedback loop
- Supports up to 30 feedback iterations

### 8. Feedback Management LLM (Conditional)
**Node ID**: `feedback_management_llm`

**Purpose**: Manages feedback and revision process when playbook needs updates.

**Process**:
- Activated when revision is requested
- Routes through feedback management prompt constructor
- Analyzes feedback and determines action (search, fetch plays, clarification, or direct update)
- Can execute document searches via `feedback_tool_executor`
- Can request clarification via `feedback_clarification_hitl`
- Can fetch additional playbooks if new plays are requested
- Updates playbook based on feedback

**Prompt Configuration**:
- **System Prompt**: [`FEEDBACK_MANAGEMENT_SYSTEM_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/blog_content_playbook_generation.py#LFEEDBACK_MANAGEMENT_SYSTEM_PROMPT_TEMPLATE)
- **User Template**: [`FEEDBACK_MANAGEMENT_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/blog_content_playbook_generation.py#LFEEDBACK_MANAGEMENT_PROMPT_TEMPLATE)
- **Output Schema**: [`FEEDBACK_MANAGEMENT_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/blog_content_playbook_generation.py#LFEEDBACK_MANAGEMENT_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: openai
- Model: gpt-5
- Temperature: 0.7
- Max Tokens: 20000
- Reasoning Effort: High

### 9. Store Playbook
**Node ID**: `store_playbook`

**Purpose**: Saves approved playbook to customer storage.

**Process**:
- Stores final playbook document in customer namespace
- Document name: "blog_content_playbook"
- Versioning enabled for tracking changes
- Document marked as shared for team access

## Workflow Configuration
- **Maximum Feedback Iterations**: 30
- **Maximum Tool Calls**: 25
- **Available Strategic Plays**: 13 predefined content plays
- **Document Versioning**: Enabled for all customer documents
- **System Playbooks**: Pre-written strategic templates stored in system namespace