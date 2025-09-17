# Orchestrator Workflow

## Overview
This is the master workflow that orchestrates the execution of multiple content analysis workflows. It manages parallel execution of various diagnostic workflows based on input flags, coordinates data flow between workflows, generates comprehensive reports, and produces final diagnostic summaries for both blog and LinkedIn content strategies.

## Frontend User Flow
*To be documented later*

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_diagnostics/wf_orchestrator_workflow.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/orchestrator_final_reports.py`

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point that accepts all configuration parameters

**Input Requirements**:
- **LinkedIn Parameters**:
  - `entity_username`: LinkedIn username (required if run_linkedin_exec=true)
  - `entity_url`: LinkedIn profile URL (required if run_linkedin_exec=true)
  - `run_linkedin_exec`: Execute LinkedIn workflows (required)
- **Blog Parameters**:
  - `company_name`: Company name for blog analysis (required if run_blog_analysis=true)
  - `start_urls`: Blog URLs to crawl (required if run_blog_analysis=true)
  - `run_blog_analysis`: Execute blog workflows (required)
- **Common Parameters**:
  - `exclude_paths`: Paths to exclude from crawling (optional)
  - `include_only_paths`: Paths to include in crawling (optional)
  - `use_cached_scraping_results`: Use cached results (default: true)
  - `cache_lookback_period_days`: Cache validity period (default: 7)

### 2. Initial Router
**Node ID**: `initial_router`

**Purpose**: Routes to appropriate workflow paths based on flags

**Process**:
- Routes to LinkedIn scraping if `run_linkedin_exec` is true
- Routes to blog analysis workflows if `run_blog_analysis` is true
- Enables parallel execution of independent workflows

**Configuration**:
- Allow Multiple: Yes
- Defer Node: Yes (synchronizes parallel paths)

### 3. LinkedIn Workflow Path

#### 3a. LinkedIn Scraping
**Node ID**: `run_linkedin_scraping`

**Purpose**: Executes LinkedIn profile and posts scraping

**Process**:
- Runs `linkedin_linkedin_scraping_workflow`
- Scrapes profile information and recent posts
- Stores scraped data for analysis

**Timeout**: 600 seconds (10 minutes)

#### 3b. LinkedIn Content Analysis
**Node ID**: `run_linkedin_analysis`

**Purpose**: Analyzes scraped LinkedIn content

**Process**:
- Runs `linkedin_linkedin_content_analysis_workflow`
- Extracts themes from posts
- Performs theme-based analysis

**Timeout**: 1200 seconds (20 minutes)

### 4. Blog Workflow Path

#### 4a. Company Analysis
**Node ID**: `run_company_analysis`

**Purpose**: Analyzes company and competitive landscape

**Process**:
- Runs `blog_company_analysis_workflow`
- Performs company profiling
- Analyzes competitive positioning

**Timeout**: 1200 seconds (20 minutes)

#### 4b. Blog Content Analysis
**Node ID**: `run_blog_content_analysis`

**Purpose**: Analyzes blog content and SEO

**Process**:
- Runs `blog_content_analysis_workflow`
- Classifies posts by funnel stage
- Performs portfolio and technical analysis

**Timeout**: 1200 seconds (20 minutes)

#### 4c. Competitor Content Analysis
**Node ID**: `run_competitor_content_analysis`

**Purpose**: Analyzes competitor content strategies

**Process**:
- Runs `blog_competitor_content_analysis_workflow`
- Analyzes each competitor's content approach
- Identifies competitive insights

**Timeout**: 1200 seconds (20 minutes)

### 5. AI Visibility Workflows

#### 5a. Executive AI Visibility
**Node ID**: `run_executive_ai_visibility`

**Purpose**: Analyzes executive's AI visibility (LinkedIn path)

**Process**:
- Runs `executive_ai_visibility_workflow`
- Tests executive presence in AI responses
- Generates visibility report

**Timeout**: 1200 seconds (20 minutes)

#### 5b. Company AI Visibility
**Node ID**: `run_company_ai_visibility`

**Purpose**: Analyzes company's AI visibility (Blog path)

**Process**:
- Runs appropriate workflow based on blog presence
- Tests company visibility in AI engines
- Generates comparative analysis

**Timeout**: 1200 seconds (20 minutes)

### 6. Deep Research Workflows

#### 6a. Blog Deep Research
**Node ID**: `run_blog_deep_research`

**Purpose**: Performs deep research on content strategy

**Process**:
- Runs `deep_research_workflow` for blog content
- Uses OpenAI deep research model
- Generates comprehensive insights

**Timeout**: 1800 seconds (30 minutes)

#### 6b. LinkedIn Deep Research
**Node ID**: `run_linkedin_deep_research`

**Purpose**: Performs deep research on LinkedIn strategy

**Process**:
- Runs `deep_research_workflow` for LinkedIn
- Analyzes executive positioning
- Generates strategic insights

**Timeout**: 1800 seconds (30 minutes)

### 7. Document Loading
**Node ID**: `load_document_router` → Various load nodes

**Purpose**: Loads all generated documents for report generation

**Process**:
- Routes to appropriate document loading nodes
- Loads LinkedIn analysis documents if available
- Loads blog analysis documents if available
- Handles missing documents gracefully

### 8. Report Generation

The workflow generates multiple specialized reports for both LinkedIn and blog paths:

#### LinkedIn Reports:
1. **Competitive Intelligence** (`generate_linkedin_competitive_intelligence`)
2. **Content Performance Analysis** (`generate_linkedin_content_performance`)
3. **Content Strategy Gaps** (`generate_linkedin_strategy_gaps`)
4. **Strategic Recommendations** (`generate_linkedin_strategic_recommendations`)
5. **Executive Summary** (`generate_linkedin_executive_summary`)

#### Blog Reports:
1. **AI Visibility Report** (`generate_blog_ai_visibility_report`)
2. **Competitive Intelligence** (`generate_blog_competitive_intelligence`)
3. **Performance Report** (`generate_blog_performance_report`)
4. **Gap Analysis** (`generate_blog_gap_analysis`)
5. **Strategic Recommendations** (`generate_blog_strategic_recommendations`)
6. **Executive Summary** (`generate_blog_executive_summary`)

### 9. Store Final Reports
**Node IDs**: `store_linkedin_diagnostic_report`, `store_blog_diagnostic_report`

**Purpose**: Stores comprehensive diagnostic reports

**Storage Configuration**:
- **LinkedIn Report**:
  - Namespace: `linkedin_content_diagnostic_report_{entity_username}`
  - Document Name: `linkedin_content_diagnostic_report`
- **Blog Report**:
  - Namespace: `blog_content_diagnostic_report_{company_name}`
  - Document Name: `blog_content_diagnostic_report`

### 10. Output Node
**Node ID**: `output_node`

**Purpose**: Returns final results and storage paths

## Workflow Configuration Details

### Parallel Execution Strategy
- LinkedIn and blog paths execute independently
- Sub-workflows within each path run in parallel when possible
- Synchronization points ensure data availability for reports

### Report Generation Models
- **Strategic Recommendations**: OpenAI gpt-5
- **Other Reports**: Anthropic claude-sonnet-4-20250514
- Temperature: 0.5-0.7 depending on report type
- Max Tokens: 4000-20000 depending on complexity

### State Management
The workflow maintains extensive state including:
- Workflow execution results
- Document paths
- Report sections
- Error handling states

### Error Handling
- Graceful handling of missing documents
- Conditional report generation based on available data
- Edge case handling for no-blog scenarios

### Workflow Dependencies
Successfully orchestrates:
1. `deep_research_workflow`
2. `blog_content_analysis_workflow`
3. `executive_ai_visibility_workflow`
4. `company_ai_visibility_workflow`
5. `company_analysis_workflow`
6. `blog_competitor_content_analysis_workflow`
7. `linkedin_linkedin_scraping_workflow`
8. `linkedin_linkedin_content_analysis_workflow`

### Cache Management
- Configurable caching for all sub-workflows
- Default cache lookback: 7 days
- Reduces API calls and improves performance

### Timeout Configuration
- Deep Research: 30 minutes
- Analysis Workflows: 20 minutes
- Scraping: 10 minutes
- Total orchestrator timeout: Typically 60-90 minutes

## Report Structure

### LinkedIn Diagnostic Report Contains:
1. Competitive Intelligence
2. Content Performance Analysis
3. Strategy Gap Analysis
4. Strategic Recommendations
5. Executive Summary

### Blog Diagnostic Report Contains:
1. AI Visibility Assessment
2. Competitive Intelligence
3. Performance Metrics
4. Gap Analysis & Validation
5. Strategic Recommendations
6. Executive Summary

## Edge Cases Handled
- No blog content scenario
- Missing LinkedIn profile
- Partial data availability
- Failed sub-workflows
- Document not found errors