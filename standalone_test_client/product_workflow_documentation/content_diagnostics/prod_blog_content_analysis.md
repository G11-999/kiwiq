# Blog Content Analysis Workflow

## Overview
This workflow analyzes blog content posts by classifying them into sales funnel stages, performing comprehensive content analysis, and generating detailed reports. The workflow crawls blog content, classifies posts into funnel stages (Awareness, Consideration, Purchase, Retention), performs portfolio-level analysis, and conducts technical SEO analysis.

## Frontend User Flow
*To be documented later*

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_diagnostics/wf_blog_content_analysis.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/blog_content_analysis.py`
- **Technical SEO Inputs**: `/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/technical_seo_analysis.py`

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point for the workflow that accepts company information and crawling parameters

**Input Requirements**:
- `company_name`: Name of the company/blog entity to analyze
- `funnel_stages_input`: Optional custom funnel stages (defaults to Awareness, Consideration, Purchase, Retention)
- `start_urls`: List of URLs to start crawling from
- `allowed_domains`: Optional list of allowed domains
- `max_urls_per_domain`: Maximum URLs to discover per domain (default: 250)
- `max_processed_urls_per_domain`: Maximum URLs to scrape (default: 200)
- `max_crawl_depth`: How deep to follow links (default: 3)
- `use_cached_scraping_results`: Whether to use cached results (default: true)
- `cache_lookback_period_days`: Days to look back for cache (default: 7)
- `is_shared`: Store as organization-shared data (default: false)
- `include_only_paths`: Optional paths to include
- `exclude_paths`: Optional paths to exclude

### 2. Web Crawler
**Node ID**: `web_crawler`

**Purpose**: Crawls and scrapes blog content from the specified URLs

**Process**: 
- Crawls starting from the provided URLs
- Respects domain restrictions and crawl depth limits
- Extracts blog post content and metadata
- Performs initial technical SEO analysis
- Analyzes robots.txt files

**Output**: 
- `scraped_data`: Raw posts data
- `technical_seo_summary`: Technical SEO metrics
- `robots_analysis`: Robots.txt analysis

### 3. Post Classification Stage
**Node ID**: `batch_and_route_posts` → `construct_classification_prompt` → `classify_batch`

**Purpose**: Classifies blog posts into sales funnel stages using LLM analysis

**Process**:
- Batches posts into groups of 10 for efficient processing
- Constructs classification prompts for each batch
- Uses LLM to classify posts into funnel stages

**Prompt Configuration**:
- **System Prompt**: [`POST_CLASSIFICATION_SYSTEM_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/blog_content_analysis.py#LPOST_CLASSIFICATION_SYSTEM_PROMPT_TEMPLATE)
- **User Template**: [`POST_CLASSIFICATION_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/blog_content_analysis.py#LPOST_CLASSIFICATION_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `posts_batch_json`: JSON representation of the batch of posts to classify
- **Output Schema**: [`BATCH_CLASSIFICATION_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/blog_content_analysis.py#LBATCH_CLASSIFICATION_SCHEMA)

**Model Configuration**:
- Provider: OpenAI
- Model: gpt-5
- Temperature: 0.5
- Max Tokens: 20000

### 4. Store Classified Posts
**Node ID**: `store_classified_posts`

**Purpose**: Saves the classified posts to customer data storage

**Process**:
- Stores classified posts with their funnel stage assignments
- Uses namespace pattern for organization
- Document Name: `blog_classified_posts`
- Namespace: `blog_classified_posts_{company_name}`

### 5. Funnel Stage Analysis
**Node ID**: `group_posts_by_funnel_stage` → `route_funnel_stage_groups` → `analyze_funnel_stage_group`

**Purpose**: Groups posts by funnel stage and performs detailed analysis on each group

**Process**:
- Groups posts by their classified funnel stage
- Sorts posts by update date (most recent first)
- Limits to top 20 posts per stage for analysis
- Analyzes content patterns, themes, and effectiveness for each funnel stage

**Prompt Configuration**:
- **System Prompt**: [`FUNNEL_STAGE_ANALYSIS_SYSTEM_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/blog_content_analysis.py#LFUNNEL_STAGE_ANALYSIS_SYSTEM_PROMPT_TEMPLATE)
- **User Template**: [`FUNNEL_STAGE_ANALYSIS_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/blog_content_analysis.py#LFUNNEL_STAGE_ANALYSIS_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `funnel_stage`: Name of the funnel stage being analyzed
  - `posts_group_json`: JSON of posts in this funnel stage
- **Output Schema**: [`FUNNEL_STAGE_ANALYSIS_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/blog_content_analysis.py#LFUNNEL_STAGE_ANALYSIS_SCHEMA)

**Model Configuration**:
- Provider: OpenAI
- Model: gpt-5
- Temperature: 0.5
- Max Tokens: 20000
- Reasoning Effort: high

### 6. Portfolio Analysis
**Node ID**: `portfolio_batch_router` → `run_portfolio_batch_analysis` → `run_final_synthesis`

**Purpose**: Performs comprehensive portfolio-level content analysis

**Process**:
- Batches classified posts into groups of 50
- Runs detailed analysis on each batch
- Synthesizes all batch reports into a final comprehensive analysis
- Uses code interpreter for advanced analysis capabilities

**Batch Analysis Prompt Configuration**:
- **System Prompt**: [`FINAL_ANALYSIS_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/blog_content_analysis.py#LFINAL_ANALYSIS_SYSTEM_PROMPT)
- **User Template**: [`FINAL_ANALYSIS_USER_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/blog_content_analysis.py#LFINAL_ANALYSIS_USER_PROMPT)
- **Template Inputs**:
  - `post_analysis_data`: Batch of posts to analyze
- **Output Schema**: [`FINAL_ANALYSIS_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/blog_content_analysis.py#LFINAL_ANALYSIS_SCHEMA)

**Final Synthesis Prompt Configuration**:
- **System Prompt**: [`FINAL_ANALYSIS_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/blog_content_analysis.py#LFINAL_ANALYSIS_SYSTEM_PROMPT)
- **User Template**: [`FINAL_SYNTHESIS_USER_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/blog_content_analysis.py#LFINAL_SYNTHESIS_USER_PROMPT)
- **Template Inputs**:
  - `batch_reports_json`: All batch analysis reports
- **Output Schema**: [`FINAL_ANALYSIS_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/blog_content_analysis.py#LFINAL_ANALYSIS_SCHEMA)

**Model Configuration**:
- Provider: OpenAI
- Model: gpt-5 (batch analysis: minimal reasoning, synthesis: high reasoning)
- Temperature: 0.5
- Max Tokens: 10000 (batch), 20000 (synthesis)
- Tools: Code Interpreter (synthesis only)

### 7. Store Analysis Results
**Node ID**: `store_analysis`, `store_portfolio_analysis`

**Purpose**: Stores the funnel stage analysis and portfolio analysis results

**Storage Locations**:
- **Funnel Analysis**: 
  - Document Name: `blog_content_analysis`
  - Namespace: `blog_content_analysis_{company_name}`
- **Portfolio Analysis**:
  - Document Name: `blog_content_portfolio_analysis`
  - Namespace: `blog_content_portfolio_analysis_{company_name}`

### 8. Technical SEO Analysis
**Node ID**: `construct_technical_analysis_prompt` → `run_technical_analysis` → `store_technical_analysis`

**Purpose**: Analyzes technical SEO aspects of the blog

**Process**:
- Uses technical audit data from web crawler
- Analyzes robots.txt configuration
- Generates comprehensive technical SEO report

**Prompt Configuration**:
- **System Prompt**: [`TECHNICAL_SEO_SYSTEM_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/technical_seo_analysis.py#LTECHNICAL_SEO_SYSTEM_PROMPT_TEMPLATE)
- **User Template**: [`TECHNICAL_SEO_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/technical_seo_analysis.py#LTECHNICAL_SEO_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `data`: Technical audit data from crawler
  - `robots_analysis`: Robots.txt analysis results
- **Output Schema**: [`TECHNICAL_SEO_REPORT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/technical_seo_analysis.py#LTECHNICAL_SEO_REPORT_SCHEMA)

**Model Configuration**:
- Provider: OpenAI
- Model: gpt-5
- Temperature: 0.5
- Max Tokens: 10000
- Reasoning Effort: low

**Storage Location**:
- Document Name: `blog_technical_analysis`
- Namespace: `blog_technical_analysis_{company_name}`

### 9. Output Node
**Node ID**: `output_node`

**Purpose**: Final output node that collects all analysis results

**Output**: Returns passthrough data from the storage operations

## Workflow Configuration Details

### Batch Sizes
- Post Classification: 10 posts per batch
- Funnel Stage Analysis: 20 posts per stage (after sorting by date)
- Portfolio Analysis: 50 posts per batch

### State Management
The workflow uses graph state with the following reducers:
- `all_classifications_batches`: collect_values
- `all_funnel_stage_reports`: collect_values
- `all_portfolio_batch_reports`: collect_values

### Document Storage Patterns
All documents are stored with:
- Versioning: Not versioned (upsert operation)
- Sharing: User-specific (not organization-shared by default)
- Namespace Pattern: `{document_type}_{company_name}`