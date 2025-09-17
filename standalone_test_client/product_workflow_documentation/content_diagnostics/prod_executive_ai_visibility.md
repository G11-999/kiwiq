# Executive AI Visibility Workflow

## Overview
This workflow analyzes an executive's AI visibility by generating targeted queries about their professional profile, executing these queries on AI answer engines, and generating a comprehensive visibility report. It helps executives understand how they appear in AI-generated responses and provides insights for improving their digital presence.

## Frontend User Flow
*To be documented later*

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_diagnostics/wf_executive_ai_visibility.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/executive_ai_visibility.py`

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point that accepts executive information and cache settings

**Input Requirements**:
- `entity_username`: LinkedIn username of the executive (required)
- `enable_cache`: Whether to use cached results (optional, default: true)
- `cache_lookback_days`: Days to look back for cache (optional, default: 7)

### 2. Load Context Documents
**Node ID**: `load_context_docs`

**Purpose**: Loads LinkedIn profile documents for the executive

**Process**:
- Loads user profile document with professional information
- Loads scraped profile with recent posts and engagement metrics
- Provides comprehensive context for visibility analysis

**Configuration**:
- **User Profile**:
  - Namespace: `linkedin_user_profile_{entity_username}`
  - Document Name: `linkedin_user_profile`
  - Output Field: `linkedin_user_profile_doc`
- **Scraped Profile**:
  - Namespace: `linkedin_scraped_profile_{entity_username}`
  - Document Name: `linkedin_scraped_profile`
  - Output Field: `linkedin_scraped_profile_doc`

### 3. Generate Executive Queries
**Node ID**: `construct_exec_queries_prompt` → `generate_exec_queries`

**Purpose**: Creates targeted queries to test executive's AI visibility

**Process**:
- Analyzes executive's profile and expertise
- Generates queries that potential customers might ask
- Creates queries testing thought leadership visibility
- Includes temporal context with current date

**Prompt Configuration**:
- **System Prompt**: [`EXEC_VISIBILITY_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/executive_ai_visibility.py#LEXEC_VISIBILITY_SYSTEM_PROMPT)
- **User Template**: [`EXEC_VISIBILITY_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/executive_ai_visibility.py#LEXEC_VISIBILITY_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `linkedin_user_profile`: User profile data
  - `linkedin_scraped_profile`: Scraped profile data
  - `current_date`: Current date for temporal context
- **Output Schema**: [`EXEC_VISIBILITY_QUERIES_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/executive_ai_visibility.py#LEXEC_VISIBILITY_QUERIES_SCHEMA)

**Model Configuration**:
- Provider: Anthropic
- Model: claude-sonnet-4-20250514
- Temperature: 0.3
- Max Tokens: 1500

### 4. Execute AI Queries
**Node ID**: `exec_ai_query`

**Purpose**: Runs generated queries on AI answer engines

**Process**:
- Executes queries on multiple AI platforms
- Collects responses for analysis
- Returns nested entity results
- Uses caching if enabled

**Configuration**:
- Return Nested Entity Results: Yes
- Entity Name Path: `entity_name`
- MongoDB Cache: Configurable
- Cache Lookback: Based on input settings

### 5. Store Raw Scraper Results
**Node ID**: `store_exec_raw_scraper_results`

**Purpose**: Stores raw AI engine responses for audit trail

**Process**:
- Saves unprocessed query results
- Generates UUID for tracking
- Maintains data lineage

**Storage Configuration**:
- Namespace: `linkedin_uploaded_files_{entity_username}`
- Document Name: `linkedin_user_ai_visibility_raw_data`
- Generate UUID: Yes
- Versioned: No (upsert)

### 6. Generate Executive Report
**Node ID**: `construct_exec_report_prompt` → `generate_exec_report`

**Purpose**: Analyzes query results and generates visibility report

**Process**:
- Evaluates executive's presence in AI responses
- Identifies visibility strengths and gaps
- Provides actionable recommendations
- Assesses competitive positioning

**Prompt Configuration**:
- **System Prompt**: [`EXEC_VISIBILITY_REPORT_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/executive_ai_visibility.py#LEXEC_VISIBILITY_REPORT_SYSTEM_PROMPT)
- **User Template**: [`EXEC_VISIBILITY_REPORT_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/executive_ai_visibility.py#LEXEC_VISIBILITY_REPORT_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `loaded_query_results`: Results from AI engine queries
- **Output Schema**: [`EXEC_VISIBILITY_REPORT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/executive_ai_visibility.py#LEXEC_VISIBILITY_REPORT_SCHEMA)

**Model Configuration**:
- Provider: Anthropic
- Model: claude-sonnet-4-20250514
- Temperature: 0.4
- Max Tokens: 3500

### 7. Store Executive Report
**Node ID**: `store_exec_report`

**Purpose**: Stores the final visibility analysis report

**Process**:
- Saves versioned report document
- Enables tracking of visibility changes over time
- Maintains report history

**Storage Configuration**:
- Namespace: `linkedin_user_ai_visibility_test_{entity_username}`
- Document Name: `linkedin_user_ai_visibility_test`
- Versioned: Yes (upsert_versioned)
- Operation: upsert_versioned

### 8. Output Node
**Node ID**: `output_node`

**Purpose**: Returns final results and storage paths

**Configuration**:
- Enable Fan In: Yes

**Output**:
- `passthrough_data`: Data passed through from storage operations
- `stored_exec_report_paths`: Paths where reports were stored

## Workflow Configuration Details

### State Management
The workflow uses graph state with the following reducers:
- `exec_queries`: replace
- `exec_query_results`: replace
- `exec_loaded_query_results`: replace
- `exec_report`: replace
- `stored_exec_report_paths`: replace

### Query Generation Strategy
The workflow generates queries across multiple categories:
- Professional expertise and thought leadership
- Industry influence and recognition
- Company and product mentions
- Competitive comparisons
- Recent activities and contributions

### AI Engine Integration
- Queries multiple AI answer engines
- Aggregates responses for comprehensive analysis
- Supports result caching for efficiency
- Handles nested entity results

### Report Components
The generated report includes:
- **Visibility Score**: Overall AI visibility assessment
- **Presence Analysis**: Where and how the executive appears
- **Content Coverage**: Topics and expertise highlighted
- **Competitive Position**: Comparison with industry peers
- **Recommendations**: Actionable steps to improve visibility
- **Gap Analysis**: Areas where visibility is lacking

### Document Versioning
- Raw data stored without versioning for audit trail
- Final reports versioned to track visibility evolution
- Enables trend analysis over time

### Cache Management
- Optional MongoDB caching for AI engine queries
- Configurable lookback period
- Reduces API calls and improves performance
- Maintains result freshness based on settings