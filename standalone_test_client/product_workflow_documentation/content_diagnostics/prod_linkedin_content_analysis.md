# LinkedIn Content Analysis Workflow

## Overview
This workflow analyzes LinkedIn posts by extracting themes, classifying posts into theme groups, and generating detailed reports for each theme. The workflow processes posts in batches, identifies up to 5 key themes, assigns posts to themes based on relevance, and produces comprehensive theme-based analysis.

## Frontend User Flow
*To be documented later*

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_diagnostics/wf_linkedin_content_analysis.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/linkedin_content_analysis.py`

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point that accepts the LinkedIn entity username

**Input Requirements**:
- `entity_username`: Name of the LinkedIn entity (person or company) whose posts are to be analyzed (required)

### 2. Load Posts
**Node ID**: `load_posts`

**Purpose**: Loads scraped LinkedIn posts for the specified entity

**Process**:
- Loads posts from the scraped posts document
- Retrieves full list of posts for analysis

**Configuration**:
- Namespace: `linkedin_scraped_posts_{entity_username}`
- Document Name: `linkedin_scraped_posts`
- Output Field: `raw_posts_data`

### 3. Extract Themes
**Node ID**: `construct_theme_extraction_prompt` → `extract_themes`

**Purpose**: Identifies up to 5 key themes from all posts

**Process**:
- Analyzes entire post collection for theme patterns
- Extracts major themes with confidence scores
- Uses all posts in context for comprehensive theme identification

**Prompt Configuration**:
- **System Prompt**: [`THEME_EXTRACTION_SYSTEM_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/linkedin_content_analysis.py#LTHEME_EXTRACTION_SYSTEM_PROMPT_TEMPLATE)
- **User Template**: [`THEME_EXTRACTION_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/linkedin_content_analysis.py#LTHEME_EXTRACTION_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `posts_json`: JSON representation of all posts
- **Output Schema**: [`EXTRACTED_THEMES_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/linkedin_content_analysis.py#LEXTRACTED_THEMES_SCHEMA)

**Model Configuration**:
- Provider: OpenAI
- Model: gpt-5
- Temperature: 0.5
- Max Tokens: 10000

### 4. Batch Posts for Classification
**Node ID**: `batch_posts`

**Purpose**: Creates batches of 10 posts for efficient classification

**Process**:
- Divides posts into manageable batches
- Routes batches for parallel processing
- Maintains post metadata through batching

**Configuration**:
- Batch Size: 10 posts per batch
- Source Path: `raw_posts_data`
- Batch Field Name: `post_batch`

### 5. Classify Posts by Theme
**Node ID**: `construct_classification_prompt` → `classify_batch`

**Purpose**: Assigns each post to the most relevant theme

**Process**:
- Analyzes each batch of posts
- Assigns posts to themes with confidence and relevance scores
- Only assigns themes when confidence is high (as instructed to LLM)

**Prompt Configuration**:
- **System Prompt**: [`POST_CLASSIFICATION_SYSTEM_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/linkedin_content_analysis.py#LPOST_CLASSIFICATION_SYSTEM_PROMPT_TEMPLATE)
- **User Template**: [`POST_CLASSIFICATION_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/linkedin_content_analysis.py#LPOST_CLASSIFICATION_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `posts_batch_json`: JSON of current batch of posts
  - `themes_json`: JSON of extracted themes
- **Output Schema**: [`BATCH_CLASSIFICATION_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/linkedin_content_analysis.py#LBATCH_CLASSIFICATION_SCHEMA)

**Model Configuration**:
- Provider: OpenAI
- Model: gpt-5-mini
- Temperature: 0.5
- Max Tokens: 10000
- Private Input/Output Mode: Yes

### 6. Merge Classifications
**Node ID**: `merge_batch_classifications`

**Purpose**: Combines all batch classifications into a single list

**Process**:
- Collects classifications from all batches
- Flattens nested structures
- Prepares data for theme grouping

**Configuration**:
- Operation: Flatten and merge all classification batches
- Output Field: `all_classified_posts`

### 7. Group Posts by Theme
**Node ID**: `group_posts_by_theme`

**Purpose**: Organizes posts into theme-based groups using data join

**Process**:
- Uses theme list as primary data
- Joins posts based on theme assignment
- Creates nested structure with posts under each theme

**Configuration**:
- Join Type: one_to_many
- Primary Key: `theme_id`
- Secondary Key: `assigned_theme_id`
- Output Nesting Field: `theme_posts`

### 8. Analyze Theme Groups
**Node ID**: `route_theme_groups` → `analyze_theme_group`

**Purpose**: Generates detailed analysis for each theme group

**Process**:
- Routes each theme group for individual analysis
- Creates comprehensive reports per theme
- Evaluates content patterns and engagement

**Prompt Configuration**:
- **System Prompt**: [`THEME_ANALYSIS_SYSTEM_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/linkedin_content_analysis.py#LTHEME_ANALYSIS_SYSTEM_PROMPT_TEMPLATE)
- **User Template**: [`THEME_ANALYSIS_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/linkedin_content_analysis.py#LTHEME_ANALYSIS_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `theme_name`: Name of the theme being analyzed
  - `posts_group_json`: JSON of posts in this theme
- **Output Schema**: [`THEME_ANALYSIS_REPORT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/linkedin_content_analysis.py#LTHEME_ANALYSIS_REPORT_SCHEMA)

**Model Configuration**:
- Provider: OpenAI
- Model: gpt-5
- Temperature: 0.5
- Max Tokens: 10000
- Private Input/Output Mode: Yes

### 9. Combine Reports
**Node ID**: `combine_reports`

**Purpose**: Merges all theme analysis reports into final output

**Process**:
- Collects all individual theme reports
- Creates comprehensive analysis document
- Prepares data for storage

**Configuration**:
- Maps entity username and combined reports
- Creates final report structure

### 10. Store Analysis Results
**Node ID**: `store_analysis`

**Purpose**: Saves the complete LinkedIn content analysis

**Process**:
- Stores combined theme analysis
- Maintains analysis history
- Saves to designated namespace

**Storage Configuration**:
- Namespace: `linkedin_content_analysis_{entity_username}`
- Document Name: `linkedin_content_analysis`
- Versioned: No (upsert operation)

### 11. Output Node
**Node ID**: `output_node`

**Purpose**: Returns final analysis results

**Configuration**:
- Enable Fan In: Yes

**Output**:
- Passthrough data from storage operation
- Complete theme-based analysis

## Workflow Configuration Details

### Batch Processing Strategy
- Posts processed in batches of 10 for classification
- Enables parallel processing while maintaining context
- Optimizes LLM token usage

### Theme Analysis Structure
Each theme analysis includes:
- Theme description and context
- Post count and distribution
- Content patterns and messaging
- Engagement metrics
- Key insights and recommendations

### State Management
The workflow uses graph state with the following reducers:
- `all_batch_classifications`: collect_values (accumulates batch results)
- `all_theme_analyses`: collect_values (accumulates theme reports)

### Classification Approach
- LLM instructed to only assign themes with high confidence
- Each post assigned to single most relevant theme
- Confidence and relevance scores tracked
- No separate filtering node - quality control built into prompts

### Data Flow Pattern
1. Load all posts → Extract themes
2. Batch posts → Classify in parallel
3. Merge classifications → Group by theme
4. Analyze each theme → Combine reports
5. Store final analysis

### Model Selection
- Theme Extraction: gpt-5 (comprehensive analysis)
- Post Classification: gpt-5-mini (efficient batching)
- Theme Analysis: gpt-5 (detailed reporting)