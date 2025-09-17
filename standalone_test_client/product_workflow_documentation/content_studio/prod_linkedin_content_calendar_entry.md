# LinkedIn Content Calendar Entry Workflow

## Overview
This workflow generates LinkedIn content topic suggestions for a specified time period (default 2 weeks). It loads user context including strategy documents and scraped posts, generates themed topic clusters based on posting frequency preferences, creates 4 topic variations per theme for LinkedIn engagement, and stores all generated topics with scheduling metadata.

## Frontend User Flow
[To be provided later]

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_studio/wf_linkedin_content_calendar_entry.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_content_calendar_entry.py`

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point for calendar generation parameters.

**Process**:
- Receives entity_username for document operations
- Accepts weeks_to_generate (defaults to 2 weeks)
- Takes start_date and end_date for calendar period
- Accepts search_params for filtering existing topics

### 2. Load All Context Docs
**Node ID**: `load_all_context_docs`

**Purpose**: Loads comprehensive user context for topic generation.

**Process**:
- Loads LinkedIn content playbook/strategy document
- Loads user profile with posting preferences
- Both documents from customer namespace
- Provides strategic and preference context

### 3. Load User Drafts
**Node ID**: `load_user_drafts`

**Purpose**: Loads recent draft posts to avoid repetition.

**Process**:
- Loads recent LinkedIn draft documents
- Limited to most recent posts
- Sorted by updated_at descending
- Prevents topic duplication

### 4. Load Scraped Posts
**Node ID**: `load_scraped_posts`

**Purpose**: Loads previously scraped LinkedIn posts.

**Process**:
- Loads scraped LinkedIn posts from user's profile
- Provides historical content context
- Helps maintain content variety
- Avoids repeating past themes

### 5. Load Previous Topics
**Node ID**: `load_previous_topics`

**Purpose**: Loads existing topic suggestions.

**Process**:
- Searches for previously generated LinkedIn ideas
- Uses date range filtering
- Prevents duplicate topic generation
- Loaded from LinkedIn idea namespace

### 6. Generate Topics LLM
**Node ID**: `generate_topics`

**Purpose**: Generates themed topic clusters for LinkedIn.

**Process**:
- Uses `prepare_generation_context` to merge and process data
- Calculates required topics based on posting frequency
- Creates 4 LinkedIn topic variations per theme
- Supports iteration if more topics needed
- Routes through `check_topic_count` for flow control

**Prompt Configuration**:
- **System Prompt**: [`TOPIC_SYSTEM_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_content_calendar_entry.py#LTOPIC_SYSTEM_PROMPT_TEMPLATE)
- **User Template**: [`TOPIC_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_content_calendar_entry.py#LTOPIC_USER_PROMPT_TEMPLATE)
- **Additional Template**: [`TOPIC_ADDITIONAL_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_content_calendar_entry.py#LTOPIC_ADDITIONAL_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `playbook`: Content strategy
  - `user_profile`: User preferences and voice
  - `merged_past_posts`: Historical content context
  - `previous_topics`: Already generated topics
- **Output Schema**: [`TOPIC_LLM_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_content_calendar_entry.py#LTOPIC_LLM_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: openai
- Model: gpt-4.1
- Temperature: 1.0 (for creativity)
- Max Tokens: 5000

### 7. Delete Previous Entries
**Node ID**: `delete_previous_entries`

**Purpose**: Removes old topic entries before storing new ones.

**Process**:
- Uses `construct_delete_search_params` for criteria
- Deletes existing topics in date range
- Ensures clean slate for new topics
- Prevents conflicting entries

### 8. Store All Topics
**Node ID**: `store_all_topics`

**Purpose**: Saves all generated topics to calendar.

**Process**:
- Stores each topic as separate document
- Uses LinkedIn idea namespace
- Includes scheduled date and metadata
- Enables versioning for tracking
- Returns paths of stored topics

## Workflow Flow Control

The workflow includes control nodes for iteration:

- **prepare_generation_context**: Merges drafts, scraped posts, and context
- **check_topic_count**: Verifies sufficient topics generated
- **route_on_topic_count**: Routes to generate more or store
- **construct_additional_topic_prompt**: Prepares prompt for more topics

## Workflow Configuration
- **Default Weeks**: 2 weeks of content
- **Past Context Limit**: 10 posts for context
- **Topics Per Theme**: 4 LinkedIn variations
- **Primary LLM**: GPT-4.1 (OpenAI)
- **Temperature**: 1.0 for creative generation
- **Max Tokens**: 5000
- **Posting Frequency**: User-defined in profile
- **Document Versioning**: Enabled for all topics