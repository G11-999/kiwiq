# Company AI Visibility Workflow

## Overview
This workflow analyzes a company's AI visibility and competitive positioning by performing competitive analysis, generating blog coverage queries, and company comparison queries. It uses AI answer engines to assess how the company and its competitors appear in AI-generated responses, then generates comprehensive visibility reports.

## Frontend User Flow
*To be documented later*

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_diagnostics/wf_company_ai_visibility_workflow.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/company_ai_visibility.py`

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point that accepts company information and cache settings

**Input Requirements**:
- `company_name`: Name of the company to analyze (required)
- `enable_cache`: Whether to use cached results (default: true)
- `cache_lookback_days`: Days to look back for cache (default: 7)

### 2. Load Context Documents
**Node ID**: `load_context_docs`

**Purpose**: Loads the company profile document containing company information

**Process**:
- Loads company document from namespace: `blog_company_profile_{company_name}`
- Document name: `blog_company`
- Contains company details, competitors, value propositions, etc.

**Output**:
- `blog_company_doc`: Loaded company profile data

### 3. Competitive Analysis
**Node ID**: `construct_competitive_analysis_prompt` → `competitive_analysis_llm`

**Purpose**: Performs initial competitive analysis using Perplexity AI

**Process**:
- Analyzes company positioning against competitors
- Identifies key differentiators and market position
- Uses web search to gather current competitive intelligence

**Prompt Configuration**:
- **System Prompt**: [`COMPETITIVE_ANALYSIS_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/company_ai_visibility.py#LCOMPETITIVE_ANALYSIS_SYSTEM_PROMPT)
- **User Template**: [`COMPETITIVE_ANALYSIS_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/company_ai_visibility.py#LCOMPETITIVE_ANALYSIS_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `blog_company_data`: Company profile information
- **Output Schema**: [`COMPETITIVE_ANALYSIS_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/company_ai_visibility.py#LCOMPETITIVE_ANALYSIS_SCHEMA)

**Model Configuration**:
- Provider: Perplexity
- Model: sonar-pro
- Temperature: 0.8
- Max Tokens: 2000

### 4. Blog Coverage Query Generation
**Node ID**: `construct_blog_queries_prompt` → `generate_blog_queries`

**Purpose**: Generates queries to test blog content visibility in AI responses

**Process**:
- Creates targeted queries based on company's blog topics
- Incorporates competitive analysis insights
- Generates queries to test content discoverability

**Prompt Configuration**:
- **System Prompt**: [`BLOG_COVERAGE_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/company_ai_visibility.py#LBLOG_COVERAGE_SYSTEM_PROMPT)
- **User Template**: [`BLOG_COVERAGE_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/company_ai_visibility.py#LBLOG_COVERAGE_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `blog_company_data`: Company profile
  - `competitive_analysis`: Results from competitive analysis
  - `current_date`: Current date for temporal context
- **Output Schema**: [`BLOG_COVERAGE_QUERIES_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/company_ai_visibility.py#LBLOG_COVERAGE_QUERIES_SCHEMA)

**Model Configuration**:
- Provider: Anthropic
- Model: claude-sonnet-4-20250514
- Temperature: 0.3
- Max Tokens: 2000

### 5. Company Comparison Query Generation
**Node ID**: `construct_company_comp_queries_prompt` → `generate_company_comp_queries`

**Purpose**: Generates queries to compare company against competitors in AI responses

**Process**:
- Creates comparison queries for company vs competitors
- Tests how AI engines position the company in the market
- Evaluates relative visibility and positioning

**Prompt Configuration**:
- **System Prompt**: [`COMPANY_COMP_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/company_ai_visibility.py#LCOMPANY_COMP_SYSTEM_PROMPT)
- **User Template**: [`COMPANY_COMP_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/company_ai_visibility.py#LCOMPANY_COMP_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `blog_company_data`: Company profile
  - `competitive_analysis`: Competitive analysis results
- **Output Schema**: [`COMPANY_COMP_QUERIES_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/company_ai_visibility.py#LCOMPANY_COMP_QUERIES_SCHEMA)

**Model Configuration**:
- Provider: Anthropic
- Model: claude-sonnet-4-20250514
- Temperature: 0.3
- Max Tokens: 2000

### 6. AI Answer Engine Scraping
**Node IDs**: `blog_coverage_ai_query`, `company_comp_ai_query`

**Purpose**: Executes generated queries on AI answer engines

**Process**:
- Runs blog coverage queries on AI platforms
- Runs company comparison queries
- Collects responses for analysis
- Returns nested entity results

**Configuration**:
- Uses MongoDB caching if enabled
- Entity name from company_name field
- Returns structured query results

### 7. Store Raw Scraper Results
**Node IDs**: `store_blog_raw_scraper_results`, `store_company_comp_raw_scraper_results`

**Purpose**: Stores raw AI engine responses for audit trail

**Storage Location**:
- Namespace: `blog_uploaded_files_{company_name}`
- Document Name: `blog_ai_visibility_raw_data`
- Generates UUID for each storage operation

### 8. Blog Coverage Report Generation
**Node ID**: `construct_blog_coverage_report_prompt` → `generate_blog_coverage_report` → `store_blog_coverage_report`

**Purpose**: Analyzes blog coverage query results and generates report

**Process**:
- Analyzes how well blog content appears in AI responses
- Identifies coverage gaps and opportunities
- Provides recommendations for improving visibility

**Prompt Configuration**:
- **System Prompt**: [`BLOG_COVERAGE_REPORT_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/company_ai_visibility.py#LBLOG_COVERAGE_REPORT_SYSTEM_PROMPT)
- **User Template**: [`BLOG_COVERAGE_REPORT_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/company_ai_visibility.py#LBLOG_COVERAGE_REPORT_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `loaded_query_results`: Results from AI engine queries
- **Output Schema**: [`BLOG_COVERAGE_REPORT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/company_ai_visibility.py#LBLOG_COVERAGE_REPORT_SCHEMA)

**Model Configuration**:
- Provider: Anthropic
- Model: claude-sonnet-4-20250514
- Temperature: 0.4
- Max Tokens: 10000

**Storage Location**:
- Document Name: `blog_ai_visibility_test`
- Namespace: `blog_ai_visibility_test_{company_name}`
- Versioned: Yes (upsert_versioned)

### 9. Company Comparison Report Generation
**Node ID**: `construct_company_comp_report_prompt` → `generate_company_comp_report` → `store_company_comp_report`

**Purpose**: Analyzes company comparison results and generates competitive report

**Process**:
- Evaluates company's positioning vs competitors in AI responses
- Identifies competitive advantages and weaknesses
- Provides strategic recommendations

**Prompt Configuration**:
- **System Prompt**: [`COMPANY_COMP_REPORT_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/company_ai_visibility.py#LCOMPANY_COMP_REPORT_SYSTEM_PROMPT)
- **User Template**: [`COMPANY_COMP_REPORT_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/company_ai_visibility.py#LCOMPANY_COMP_REPORT_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `loaded_query_results`: Company comparison query results
- **Output Schema**: [`COMPANY_COMP_REPORT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/company_ai_visibility.py#LCOMPANY_COMP_REPORT_SCHEMA)

**Model Configuration**:
- Provider: Anthropic
- Model: claude-sonnet-4-20250514
- Temperature: 0.4
- Max Tokens: 10000

**Storage Location**:
- Document Name: `blog_company_ai_visibility_test`
- Namespace: `blog_company_ai_visibility_test_{company_name}`
- Versioned: Yes (upsert_versioned)

### 10. Output Node
**Node ID**: `output_node`

**Purpose**: Collects and returns final reports

**Output**:
- `blog_coverage_report`: Blog visibility analysis report
- `company_comp_report`: Company comparison report

## Workflow Configuration Details

### State Management
The workflow uses graph state with the following reducers:
- `competitive_analysis`: replace
- `blog_coverage_queries`: replace
- `company_comp_queries`: replace
- `blog_coverage_query_results`: replace
- `company_comp_query_results`: replace
- `blog_loaded_query_results`: replace
- `company_loaded_query_results`: replace
- `blog_coverage_report`: replace
- `company_comp_report`: replace
- `stored_blog_report_paths`: replace
- `stored_company_report_paths`: replace

### Document Storage Patterns
- **Input Documents**: User-specific, not versioned
- **Raw Data**: Stored with UUID in uploaded_files namespace
- **Reports**: Versioned documents for tracking changes over time
- **Namespace Pattern**: Various patterns based on document type

### Parallel Processing
The workflow executes blog coverage and company comparison analyses in parallel after the initial competitive analysis, improving performance and reducing total execution time.