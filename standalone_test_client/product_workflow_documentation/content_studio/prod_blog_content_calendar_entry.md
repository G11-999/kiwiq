# Blog Content Calendar Entry Workflow

## Overview
This workflow generates blog content topic suggestions for a specified time period (default 2 weeks). It loads customer context documents, generates themed topic clusters based on content strategy, performs web research for each theme, and stores all generated topics. The workflow creates 4 topic variations per theme to provide diverse content options aligned with the company's blog strategy.

## Frontend User Flow
[To be provided later]

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_studio/wf_blog_content_calendar_entry.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_calendar_entry.py`

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point that accepts parameters for calendar generation.

**Process**:
- Receives company_name for document operations
- Accepts weeks_to_generate (defaults to 2 weeks)
- Takes start_date and end_date for the calendar period
- Accepts optional search_params for filtering existing topics

### 2. Load All Context Documents
**Node ID**: `load_all_context_docs`

**Purpose**: Loads essential company context for topic generation.

**Process**:
- Loads company document with brand guidelines and profile
- Loads blog content strategy/playbook document
- Both documents loaded from customer namespace
- Schema loading disabled for flexibility

### 3. Load Previous Posts
**Node ID**: `load_previous_posts`

**Purpose**: Loads recent blog posts to avoid content repetition.

**Process**:
- Loads up to 10 most recent blog posts
- Sorted by updated_at in descending order
- Used to ensure new topics don't duplicate recent content
- Loaded from blog post namespace

### 4. Load Previous Topics
**Node ID**: `load_previous_topics`

**Purpose**: Loads existing topic suggestions from the calendar.

**Process**:
- Searches for previously generated topic ideas
- Uses date range filtering based on input parameters
- Helps maintain topic diversity and avoid duplicates
- Loaded from topic ideas card namespace

### 5. Theme Suggestion LLM
**Node ID**: `theme_suggestion_llm`

**Purpose**: Generates content themes based on strategy and context.

**Process**:
- Uses prompt constructor (`construct_theme_prompt`) with company context
- Generates strategic themes aligned with content playbook
- Creates themes that will guide topic generation
- Supports iteration if more themes are needed
- Routes through `prepare_generation_context` node to merge and aggregate data

**Prompt Configuration**:
- **System Prompt**: [`THEME_SUGGESTION_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_calendar_entry.py#LTHEME_SUGGESTION_SYSTEM_PROMPT)
- **User Template**: [`THEME_SUGGESTION_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_calendar_entry.py#LTHEME_SUGGESTION_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `company_doc`: Company profile and guidelines
  - `playbook`: Content strategy document
  - `previous_posts`: Recent blog posts to avoid duplication
- **Output Schema**: [`THEME_SUGGESTION_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_calendar_entry.py#LTHEME_SUGGESTION_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: openai
- Model: gpt-4.1
- Temperature: 1.0 (for creativity)
- Max Tokens: 5000

### 6. Research LLM
**Node ID**: `research_llm`

**Purpose**: Performs web research for each generated theme.

**Process**:
- Uses prompt constructor (`construct_research_prompt`) with theme context
- Leverages Perplexity for current web insights
- Gathers trends, statistics, and relevant information per theme
- Provides research context for topic generation

**Prompt Configuration**:
- **System Prompt**: [`RESEARCH_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_calendar_entry.py#LRESEARCH_SYSTEM_PROMPT)
- **User Template**: [`RESEARCH_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_calendar_entry.py#LRESEARCH_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `company_doc`: Company context
  - `theme_suggestion`: Current theme to research
  - `playbook`: Content strategy guidelines
- **Output Schema**: [`RESEARCH_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_calendar_entry.py#LRESEARCH_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: perplexity
- Model: sonar-pro
- Temperature: 0.5
- Max Tokens: 3000

### 7. Generate Topics LLM
**Node ID**: `generate_topics`

**Purpose**: Generates 4 topic variations per theme.

**Process**:
- Uses prompt constructor (`construct_topic_prompt` or `construct_additional_topic_prompt`)
- Creates 4 diverse topic suggestions around each theme
- Each topic includes title, description, objective, and metadata
- Routes through iteration check to ensure sufficient topics generated
- Uses `check_theme_iteration` and `check_topic_count` nodes for flow control

**Prompt Configuration**:
- **System Prompt**: [`TOPIC_SYSTEM_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_calendar_entry.py#LTOPIC_SYSTEM_PROMPT_TEMPLATE)
- **User Template**: [`TOPIC_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_calendar_entry.py#LTOPIC_USER_PROMPT_TEMPLATE)
- **Additional Template**: [`TOPIC_ADDITIONAL_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_calendar_entry.py#LTOPIC_ADDITIONAL_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `company_doc`: Company guidelines
  - `playbook`: Content strategy
  - `theme_suggestion`: Current theme
  - `research_insights`: Web research results
  - `previous_topics`: Already generated topics (for additional generation)
- **Output Schema**: [`TOPIC_LLM_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_calendar_entry.py#LTOPIC_LLM_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: openai
- Model: gpt-4.1
- Temperature: 1.0 (for creativity)
- Max Tokens: 5000

### 8. Delete Previous Entries
**Node ID**: `delete_previous_entries`

**Purpose**: Removes old topic entries before storing new ones.

**Process**:
- Uses `construct_delete_search_params` to prepare deletion criteria
- Deletes existing topics in the specified date range
- Ensures clean slate for new topic storage
- Prevents duplicate or conflicting entries

### 9. Store All Topics
**Node ID**: `store_all_topics`

**Purpose**: Saves all generated topics to the calendar.

**Process**:
- Stores each topic as a separate document
- Uses topic ideas card namespace
- Each topic includes scheduled date and metadata
- Enables versioning for tracking changes
- Returns paths of all stored topics

## Workflow Flow Control

The workflow includes several control nodes for managing iteration:

- **prepare_generation_context**: Merges and aggregates context data
- **check_theme_iteration**: Determines if first theme or additional themes needed
- **route_on_theme_iteration**: Routes to appropriate prompt constructor
- **check_topic_count**: Verifies if enough topics have been generated
- **route_on_topic_count**: Routes to either generate more themes or store topics
- **construct_additional_theme_prompt**: Prepares prompt for additional themes when needed

## Workflow Configuration
- **Default Weeks**: 2 weeks of content generation
- **Default Posts Per Week**: 2 posts per week
- **Topics Per Theme**: 4 topic variations
- **Primary LLM**: GPT-4.1 (OpenAI) for generation
- **Research LLM**: Sonar Pro (Perplexity) for web research
- **Temperature**: 1.0 for creative generation, 0.5 for research
- **Document Versioning**: Enabled for all topic documents