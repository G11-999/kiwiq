# LinkedIn Content Playbook Generation Workflow

## Overview
This workflow generates a comprehensive LinkedIn content playbook by analyzing LinkedIn profile documents, selecting relevant content plays based on the user's LinkedIn presence, creating detailed implementation strategies for each play, and providing actionable recommendations with timelines. The workflow includes human-in-the-loop approval for play selection and playbook review.

## Frontend User Flow
This workflow is triggered when users want to generate a strategic LinkedIn content playbook. Users access this through the playbook generation section to create customized LinkedIn content strategies based on their profile, industry position, and professional goals.

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/playbook/wf_linkedin_content_playbook_generation.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/linkedin_content_playbook_generation.py`

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point for the workflow that accepts entity username and playbook configuration.

**Process**: 
- Receives entity_username for document operations
- Accepts optional playbook_selection_config with predefined LinkedIn content plays (defaults to 10 strategic plays)
- The CONFIG includes plays like "The Transparent Founder Journey", "The Teaching CEO", "The Industry Contrarian", etc.

### 2. Load LinkedIn Documents
**Node ID**: `load_linkedin_doc`

**Purpose**: Loads essential LinkedIn documents needed for playbook generation.

**Process**:
- Loads LinkedIn user profile document using entity_username
- Optionally loads LinkedIn content diagnostic report if available
- Documents are loaded from customer namespace
- Profile document provides context about user's current LinkedIn presence

### 3. Play Selection LLM
**Node ID**: `play_suggestion_llm`

**Purpose**: Analyzes LinkedIn profile and selects appropriate content plays.

**Process**:
- Routes through prompt constructor nodes based on document availability
- Uses extracted playbook metadata for context
- Validates selected play IDs against available plays
- If invalid IDs found, corrects them through `construct_play_id_correction_prompt`
- Considers user's industry, role, and LinkedIn presence strength

**Prompt Configuration**:
- **System Prompt**: [`PLAY_SELECTION_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/linkedin_content_playbook_generation.py#LPLAY_SELECTION_SYSTEM_PROMPT)
- **User Template**: [`PLAY_SELECTION_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/linkedin_content_playbook_generation.py#LPLAY_SELECTION_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `linkedin_profile_doc`: User's LinkedIn profile information
  - `diagnostic_report_doc`: LinkedIn diagnostic analysis (optional)
  - `available_plays`: List of strategic LinkedIn plays to choose from
- **Output Schema**: [`PLAY_SELECTION_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/linkedin_content_playbook_generation.py#LPLAY_SELECTION_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: openai
- Model: gpt-5
- Temperature: 0.7
- Max Tokens: 30000

### 4. Play Selection HITL
**Node ID**: `play_selection_hitl`

**Purpose**: Human review and approval of selected LinkedIn plays.

**Process**:
- Presents flattened play recommendations to human reviewer
- Displays reasoning for each selected play
- Allows approval, rejection, or revision of selected plays
- Routes to different paths based on user action:
  - Approved: Proceeds to playbook generation
  - Rejected: Ends workflow
  - Revision needed: Returns to play selection with feedback

### 5. Load Selected Playbooks
**Node ID**: `load_selected_playbooks`

**Purpose**: Loads detailed playbook content for selected LinkedIn plays.

**Process**:
- Filters and prepares load configurations for approved plays
- Loads playbook documents from system namespace (linkedin_playbook_sys)
- Each playbook contains LinkedIn-specific implementation guidance
- Playbooks include posting strategies, content templates, and engagement tactics

### 6. Playbook Generator LLM
**Node ID**: `playbook_generator_llm`

**Purpose**: Generates customized LinkedIn playbook based on selected plays and user profile.

**Process**:
- Synthesizes selected playbooks with user's LinkedIn context
- Creates personalized content calendar and posting strategies
- Develops specific content themes aligned with user's professional brand
- Supports document search through tool executor for additional context

**Prompt Configuration**:
- **System Prompt**: [`PLAYBOOK_GENERATOR_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/linkedin_content_playbook_generation.py#LPLAYBOOK_GENERATOR_SYSTEM_PROMPT)
- **User Template**: [`PLAYBOOK_GENERATOR_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/linkedin_content_playbook_generation.py#LPLAYBOOK_GENERATOR_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `linkedin_profile_doc`: User's LinkedIn profile
  - `selected_playbooks`: Detailed playbook content
  - `diagnostic_report_doc`: LinkedIn diagnostic insights (optional)
- **Output Schema**: [`PLAYBOOK_GENERATOR_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/linkedin_content_playbook_generation.py#LPLAYBOOK_GENERATOR_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: openai
- Model: gpt-5
- Temperature: 0.7
- Max Tokens: 30000
- Tool Support: Document search enabled

### 7. Playbook Review HITL
**Node ID**: `playbook_review_hitl`

**Purpose**: Human review of generated LinkedIn playbook.

**Process**:
- Presents complete LinkedIn content playbook for review
- Shows implementation timeline and content strategies
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
- Can fetch additional LinkedIn playbooks if new plays are requested
- Updates playbook based on feedback while maintaining LinkedIn best practices

**Prompt Configuration**:
- **System Prompt**: [`FEEDBACK_MANAGEMENT_SYSTEM_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/linkedin_content_playbook_generation.py#LFEEDBACK_MANAGEMENT_SYSTEM_PROMPT_TEMPLATE)
- **User Template**: [`FEEDBACK_MANAGEMENT_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/linkedin_content_playbook_generation.py#LFEEDBACK_MANAGEMENT_PROMPT_TEMPLATE)
- **Output Schema**: [`FEEDBACK_MANAGEMENT_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/playbook/llm_inputs/linkedin_content_playbook_generation.py#LFEEDBACK_MANAGEMENT_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: openai
- Model: gpt-5
- Temperature: 0.7
- Max Tokens: 30000
- Reasoning Effort: High

### 9. Store Playbook
**Node ID**: `store_playbook`

**Purpose**: Saves approved LinkedIn playbook to customer storage.

**Process**:
- Stores final playbook document in customer namespace
- Document name: "linkedin_content_playbook"
- Versioning enabled for tracking changes
- Document marked as shared for team collaboration

## Workflow Configuration
- **Maximum Feedback Iterations**: 30
- **Maximum Tool Calls**: 25
- **Available LinkedIn Plays**: 10 predefined content plays
  - The Transparent Founder Journey
  - The Teaching CEO
  - The Industry Contrarian
  - The Customer Champion
  - The Connector CEO
  - The Ecosystem Builder
  - The Data-Driven Executive
  - The Future-Back Leader
  - The Vulnerable Leader
  - The Grateful Leader
- **Document Versioning**: Enabled for all customer documents
- **System Playbooks**: Pre-written LinkedIn strategic templates stored in system namespace