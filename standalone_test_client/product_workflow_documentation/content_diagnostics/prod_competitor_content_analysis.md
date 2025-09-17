# Competitor Content Analysis Workflow

## Overview
This workflow analyzes competitor content strategies by loading company competitor information, distributing competitors for parallel analysis using Perplexity LLM, and saving comprehensive analysis results. It provides insights into each competitor's content approach, topics, and strategies.

## Frontend User Flow
*To be documented later*

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_diagnostics/wf_competitor_content_analysis.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/competitor_content_analysis.py`

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point that accepts the company name for analysis

**Input Requirements**:
- `company_name`: Name of the company for document operations (required)

### 2. Load Company Document
**Node ID**: `load_company_doc`

**Purpose**: Loads the company document containing competitor information

**Process**:
- Loads company profile document
- Retrieves competitor list from the document
- Prepares data for parallel competitor analysis

**Configuration**:
- Namespace: `blog_company_profile_{company_name}`
- Document Name: `blog_company`
- Shared: No
- System Entity: No

**Output**:
- `company_doc`: Company profile with competitors list

### 3. Distribute Competitors
**Node ID**: `distribute_competitors`

**Purpose**: Distributes competitors for parallel processing using map_list_router

**Process**:
- Takes the competitors list from company document
- Creates individual processing tasks for each competitor
- Routes to analysis nodes with batch size of 1

**Configuration**:
- Source Path: `company_doc.competitors`
- Destinations: `construct_analysis_prompt`
- Batch Size: 1
- Batch Field Name: `competitor_item`

### 4. Construct Analysis Prompt
**Node ID**: `construct_analysis_prompt`

**Purpose**: Constructs prompts for competitor content analysis

**Process**:
- Creates personalized prompts for each competitor
- Extracts competitor name and website URL
- Prepares structured prompts for LLM analysis

**Prompt Configuration**:
- **System Prompt**: [`COMPETITOR_CONTENT_ANALYSIS_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/competitor_content_analysis.py#LCOMPETITOR_CONTENT_ANALYSIS_SYSTEM_PROMPT)
- **User Template**: [`COMPETITOR_CONTENT_ANALYSIS_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/competitor_content_analysis.py#LCOMPETITOR_CONTENT_ANALYSIS_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `competitor_name`: Name of the competitor being analyzed
  - `competitor_website`: Website URL of the competitor
- **Output Schema**: [`COMPETITOR_CONTENT_ANALYSIS_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/competitor_content_analysis.py#LCOMPETITOR_CONTENT_ANALYSIS_OUTPUT_SCHEMA)

**Node Configuration**:
- Private Input Mode: Yes
- Output to Central State: Yes
- Private Output Mode: Yes

### 5. Analyze Competitor Content
**Node ID**: `analyze_competitor_content`

**Purpose**: Performs deep content analysis using Perplexity LLM

**Process**:
- Analyzes competitor's content strategy
- Identifies key topics and themes
- Evaluates content quality and approach
- Extracts insights about content distribution

**Model Configuration**:
- Provider: Perplexity
- Model: sonar-pro
- Temperature: 0.5
- Max Tokens: 4000

**Node Configuration**:
- Private Input Mode: Yes
- Output to Central State: Yes

### 6. Route for Saving
**Node ID**: `route_for_saving`

**Purpose**: Routes analyzed competitor data for storage

**Process**:
- Collects all competitor analysis results
- Prepares data for batch storage
- Routes to save operation

**Configuration**:
- Enable Fan In: Yes
- Source Path: `all_competitor_analysis_results`
- Destinations: `save_competitor_analysis`
- Batch Size: 1
- Batch Field Name: `competitor_data`

### 7. Save Competitor Analysis
**Node ID**: `save_competitor_analysis`

**Purpose**: Stores competitor analysis results to customer data

**Process**:
- Saves each competitor's analysis as a separate document
- Uses dynamic naming based on competitor name
- Generates UUID for tracking

**Storage Configuration**:
- **Namespace Pattern**: `blog_competitive_intelligence_{company_name}`
- **Document Name Pattern**: `blog_competitor_content_analysis_{competitor_name}`
- **Versioning**: Not versioned (upsert operation)
- **Shared**: No
- **System Entity**: No
- **Generate UUID**: Yes

**Node Configuration**:
- Private Input Mode: Yes
- Output to Central State: Yes

### 8. Output Node
**Node ID**: `output_node`

**Purpose**: Final output node that collects results

**Configuration**:
- Enable Fan In: Yes

**Output**:
- `competitor_analysis_passthrough_data`: Collection of all saved analysis results

## Workflow Configuration Details

### State Management
The workflow uses graph state with the following reducers:
- `company_doc`: replace
- `all_competitor_analysis_results`: collect_values
- `competitor_analysis_passthrough_data`: collect_values

### Parallel Processing
- Each competitor is analyzed independently in parallel
- Results are collected and stored separately
- Improves performance for multiple competitors

### Document Storage Convention
- Each competitor gets its own analysis document
- Documents are stored in a shared namespace for the company
- Naming convention ensures easy retrieval and organization

### Data Flow
1. Load company document with competitors
2. Split competitors into individual processing tasks
3. Analyze each competitor in parallel
4. Collect all results
5. Store each analysis as a separate document
6. Return confirmation of storage

## Example Competitor Data Structure
```json
{
  "competitors": [
    {
      "name": "Grammarly Business",
      "website_url": "https://grammarly.com"
    },
    {
      "name": "Jasper",
      "website_url": "https://jasper.ai"
    },
    {
      "name": "Copy.ai",
      "website_url": "https://copy.ai"
    }
  ]
}
```

## Output Document Structure
Each competitor analysis is saved with comprehensive insights including:
- Content strategy overview
- Key topics and themes
- Content quality assessment
- Distribution channels
- Competitive positioning
- Strengths and weaknesses