# LinkedIn User Input to Brief Workflow

## Overview
This workflow creates strategic LinkedIn content briefs based on executive profiles and content strategy. It loads executive profile and content playbook documents, generates strategic topic suggestions with content type recommendations, performs knowledge base research for selected topics, and creates comprehensive briefs with human-in-the-loop approval and revision capabilities.

## Frontend User Flow
[To be provided later]

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_studio/wf_linkedin_user_input_to_brief.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_user_input_to_brief.py`

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point for user ideas and parameters.

**Process**:
- Receives entity_username for document operations
- Accepts user_input with content ideas or topics
- Takes brief_uuid for unique identification
- Sets initial_status (defaults to "draft")

### 2. Load Executive and Playbook
**Node ID**: `load_executive_and_playbook`

**Purpose**: Loads strategic context documents.

**Process**:
- Loads LinkedIn user profile for executive voice
- Loads content playbook for strategy alignment
- Both from customer namespace
- Provides personalization and strategic context

### 3. Topic Generation LLM
**Node ID**: `topic_generation_llm`

**Purpose**: Generates strategic topic suggestions.

**Process**:
- Uses prompt constructor (`construct_topic_generation_prompt`)
- Creates 5 topic suggestions with content type diversity
- Each topic includes different LinkedIn content formats
- Aligns with executive profile and strategy

**Prompt Configuration**:
- **System Prompt**: [`TOPIC_GENERATION_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_user_input_to_brief.py#LTOPIC_GENERATION_SYSTEM_PROMPT)
- **User Template**: [`TOPIC_GENERATION_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_user_input_to_brief.py#LTOPIC_GENERATION_USER_PROMPT_TEMPLATE)
- **Regeneration Template**: [`TOPIC_REGENERATION_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_user_input_to_brief.py#LTOPIC_REGENERATION_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `user_input`: Initial ideas
  - `executive_profile`: Executive voice and expertise
  - `content_playbook`: Strategic guidelines
- **Output Schema**: [`TOPIC_GENERATION_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_user_input_to_brief.py#LTOPIC_GENERATION_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: anthropic
- Model: claude-sonnet-4-20250514
- Temperature: 0.7
- Max Tokens: 4000

### 4. Topic Selection HITL
**Node ID**: `topic_selection_hitl`

**Purpose**: Human selection of topic and content type.

**Process**:
- Presents 5 topics with multiple content types each
- User selects preferred topic and format
- Option to regenerate if none suitable (max 3 attempts)
- Routes based on selection

### 5. Knowledge Base Query LLM
**Node ID**: `knowledge_base_query_llm`

**Purpose**: Researches selected topic in knowledge base.

**Process**:
- Uses prompt constructor (`construct_knowledge_query_prompt`)
- Searches internal knowledge base for relevant information
- Gathers insights, examples, and data points
- Enriches brief with research

**Prompt Configuration**:
- **System Prompt**: [`KNOWLEDGE_BASE_QUERY_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_user_input_to_brief.py#LKNOWLEDGE_BASE_QUERY_SYSTEM_PROMPT)
- **User Template**: [`KNOWLEDGE_BASE_QUERY_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_user_input_to_brief.py#LKNOWLEDGE_BASE_QUERY_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `selected_topic`: Chosen topic details
  - `executive_profile`: Context for research
- **Output Schema**: [`KNOWLEDGE_BASE_QUERY_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_user_input_to_brief.py#LKNOWLEDGE_BASE_QUERY_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: anthropic
- Model: claude-sonnet-4-20250514
- Temperature: 0.7
- Max Tokens: 4000

### 6. Brief Generation LLM
**Node ID**: `brief_generation_llm`

**Purpose**: Creates comprehensive LinkedIn content brief.

**Process**:
- Uses prompt constructor (`construct_brief_generation_prompt`)
- Incorporates research, strategy, and executive voice
- Creates LinkedIn-specific brief with hooks and CTAs
- Structured for platform optimization

**Prompt Configuration**:
- **System Prompt**: [`BRIEF_GENERATION_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_user_input_to_brief.py#LBRIEF_GENERATION_SYSTEM_PROMPT)
- **User Template**: [`BRIEF_GENERATION_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_user_input_to_brief.py#LBRIEF_GENERATION_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `selected_topic`: Topic and content type
  - `knowledge_base_results`: Research findings
  - `executive_profile`: Voice and style
  - `content_playbook`: Strategy alignment
- **Output Schema**: [`BRIEF_GENERATION_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_user_input_to_brief.py#LBRIEF_GENERATION_OUTPUT_SCHEMA)

### 7. Save as Draft After Generation
**Node ID**: `save_as_draft_after_generation`

**Purpose**: Automatically saves initial brief.

**Process**:
- Stores brief in customer namespace
- Uses brief_uuid for identification
- Saves with draft status
- Enables versioning

### 8. Brief Approval HITL
**Node ID**: `brief_approval_hitl`

**Purpose**: Human review and approval of brief.

**Process**:
- Presents generated brief for review
- Allows manual editing
- Options: approve, revise, save draft, or cancel
- Supports feedback iterations (max 10)

### 9. Analyze Brief Feedback LLM (Conditional)
**Node ID**: `analyze_brief_feedback`

**Purpose**: Processes feedback for revision.

**Process**:
- Uses feedback analysis prompts
- Identifies required changes
- Generates revision instructions
- Feeds into brief revision

**Prompt Configuration**:
- **System Prompt**: [`BRIEF_FEEDBACK_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_user_input_to_brief.py#LBRIEF_FEEDBACK_SYSTEM_PROMPT)
- **User Prompt**: [`BRIEF_FEEDBACK_INITIAL_USER_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_user_input_to_brief.py#LBRIEF_FEEDBACK_INITIAL_USER_PROMPT)
- **Output Schema**: [`BRIEF_FEEDBACK_ANALYSIS_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_user_input_to_brief.py#LBRIEF_FEEDBACK_ANALYSIS_OUTPUT_SCHEMA)

### 10. Save Brief
**Node ID**: `save_brief`

**Purpose**: Saves approved brief as final.

**Process**:
- Updates status to "approved"
- Stores in customer namespace
- Document name: "linkedin_brief_{brief_uuid}"
- Ready for content creation

## Workflow Configuration
- **Maximum Regeneration**: 3 attempts (topics)
- **Maximum Revision**: 3 attempts (brief)
- **Maximum Iterations**: 10 (feedback loops)
- **Primary LLM**: Claude Sonnet (Anthropic)
- **Temperature**: 0.7 for generation, 0.5 for feedback
- **Content Types**: Multiple formats per topic
- **Document Versioning**: Enabled