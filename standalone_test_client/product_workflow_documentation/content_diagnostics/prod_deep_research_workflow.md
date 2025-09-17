# Deep Research Workflow

## Overview
This workflow performs deep research on content strategy and LinkedIn executive profiles using OpenAI's deep research model (o4-mini-deep-research). It can run blog content strategy research, LinkedIn executive research, or both simultaneously, leveraging web search capabilities to gather comprehensive insights.

## Frontend User Flow
*To be documented later*

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_diagnostics/wf_deep_research_workflow.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/deep_research_content_strategy.py`

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point with routing options for different research types

**Input Requirements**:
- `company_name`: Name of the company to analyze (optional, required for blog analysis)
- `entity_username`: LinkedIn username for executive research (optional, required for LinkedIn analysis)
- `run_blog_analysis`: Whether to run content strategy research (required, boolean)
- `run_linkedin_exec`: Whether to run LinkedIn research (required, boolean)

### 2. Document Router
**Node ID**: `document_router`

**Purpose**: Routes to appropriate data loading nodes based on research type

**Process**:
- Routes to `load_company_data` if `run_blog_analysis` is true
- Routes to `load_linkedin_data` if `run_linkedin_exec` is true
- Can route to both for combined research

**Configuration**:
- Allow Multiple: Yes
- Conditional routing based on input flags

### 3. Load Company Data
**Node ID**: `load_company_data`

**Purpose**: Loads company profile for blog content strategy research

**Process**:
- Loads company document from namespace
- Provides context for content strategy analysis

**Configuration**:
- Namespace: `blog_company_profile_{company_name}`
- Document Name: `blog_company`
- Output Field: `company_data`

### 4. Load LinkedIn Data
**Node ID**: `load_linkedin_data`

**Purpose**: Loads LinkedIn profile data for executive research

**Process**:
- Loads both user profile and scraped profile data
- Provides comprehensive LinkedIn context

**Configuration**:
- **User Profile**:
  - Namespace: `linkedin_user_profile_{entity_username}`
  - Document Name: `linkedin_user_profile`
  - Output Field: `linkedin_user_profile`
- **Scraped Profile**:
  - Namespace: `linkedin_scraped_profile_{entity_username}`
  - Document Name: `linkedin_scraped_profile`
  - Output Field: `linkedin_scraped_profile`

### 5. Content Strategy Research Path
**Node ID**: `construct_content_strategy_prompt` → `deep_researcher_content_strategy`

**Purpose**: Performs deep research on blog content strategy

**Process**:
- Analyzes industry best practices
- Researches content patterns and benchmarks
- Performs funnel stage analysis
- Utilizes web search for current insights

**Prompt Configuration**:
- **System Prompt**: [`SYSTEM_PROMPT_TEMPLATE_FOR_DEEP_RESEARCH_BLOG_CONTENT_STRATEGY`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/deep_research_content_strategy.py#LSYSTEM_PROMPT_TEMPLATE_FOR_DEEP_RESEARCH_BLOG_CONTENT_STRATEGY)
- **User Template**: [`USER_PROMPT_TEMPLATE_FOR_DEEP_RESEARCH_BLOG_CONTENT_STRATEGY`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/deep_research_content_strategy.py#LUSER_PROMPT_TEMPLATE_FOR_DEEP_RESEARCH_BLOG_CONTENT_STRATEGY)
- **Template Inputs**:
  - `company_info`: Company profile data
- **Output Schema**: [`GENERATION_SCHEMA_FOR_DEEP_RESEARCH_BLOG_CONTENT_STRATEGY`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/deep_research_content_strategy.py#LGENERATION_SCHEMA_FOR_DEEP_RESEARCH_BLOG_CONTENT_STRATEGY)

**Model Configuration**:
- Provider: OpenAI
- Model: o4-mini-deep-research
- Temperature: 0.8
- Max Tokens: 100000
- Max Tool Calls: 40
- Tools: web_search_preview (provider built-in)

### 6. LinkedIn Research Path
**Node ID**: `construct_linkedin_prompt` → `deep_researcher_linkedin`

**Purpose**: Performs deep research on LinkedIn executive profiles

**Process**:
- Analyzes peer benchmarks
- Researches industry trends
- Gathers audience topic intelligence
- Uses web search for competitive insights

**Prompt Configuration**:
- **System Prompt**: [`SYSTEM_PROMPT_TEMPLATE_FOR_LINKEDIN_RESEARCH`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/deep_research_content_strategy.py#LSYSTEM_PROMPT_TEMPLATE_FOR_LINKEDIN_RESEARCH)
- **User Template**: [`USER_PROMPT_TEMPLATE_FOR_LINKEDIN_RESEARCH`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/deep_research_content_strategy.py#LUSER_PROMPT_TEMPLATE_FOR_LINKEDIN_RESEARCH)
- **Template Inputs**:
  - `linkedin_user_profile`: User profile data
  - `linkedin_scraped_profile`: Scraped profile data
- **Output Schema**: [`SCHEMA_TEMPLATE_FOR_LINKEDIN_RESEARCH`](/standalone_client/kiwi_client/workflows/active/content_diagnostics/llm_inputs/deep_research_content_strategy.py#LSCHEMA_TEMPLATE_FOR_LINKEDIN_RESEARCH)

**Model Configuration**:
- Provider: OpenAI
- Model: o4-mini-deep-research
- Temperature: 0.8
- Max Tokens: 100000
- Max Tool Calls: 25
- Tools: web_search_preview (provider built-in)

### 7. Store Blog Research
**Node ID**: `store_blog_research`

**Purpose**: Stores blog content strategy research results

**Process**:
- Saves comprehensive research report
- Uses versioning for tracking changes

**Storage Configuration**:
- Namespace: `blog_deep_research_report_{company_name}`
- Document Name: `blog_deep_research_report`
- Versioned: Yes (based on document model configuration)
- Operation: upsert

### 8. Store LinkedIn Research
**Node ID**: `store_linkedin_research`

**Purpose**: Stores LinkedIn executive research results

**Process**:
- Saves detailed LinkedIn analysis
- Maintains version history

**Storage Configuration**:
- Namespace: `linkedin_deep_research_report_{entity_username}`
- Document Name: `linkedin_deep_research_report`
- Versioned: Yes (based on document model configuration)
- Operation: upsert

### 9. Output Node
**Node ID**: `output_node`

**Purpose**: Returns storage paths and research results

**Configuration**:
- Defer Node: Yes (waits for all paths to complete)

**Output**:
- `blog_storage_paths`: Paths where blog research was stored
- `linkedin_storage_paths`: Paths where LinkedIn research was stored

## Workflow Configuration Details

### Research Capabilities
- **Content Strategy Research**: Industry best practices, content patterns, funnel stage analysis, content mix benchmarks
- **LinkedIn Research**: Peer benchmarking, industry trends, audience intelligence, competitive positioning
- **Combined Research**: Both analyses run in parallel with integrated insights

### Web Search Integration
- Both research paths use web_search_preview tool
- Enables real-time data gathering
- Provides citations and sources
- Parallel tool calls for efficiency

### State Management
The workflow uses graph state with the following reducers:
- `company_name`: replace
- `entity_username`: replace
- `run_blog_analysis`: replace
- `run_linkedin_exec`: replace
- `company_data`: replace
- `linkedin_user_profile`: replace
- `linkedin_scraped_profile`: replace
- `linkedin_exec_context`: replace
- `combined_output`: replace
- `research_type`: replace

### Tool Usage Limits
- Blog Content Strategy: Up to 40 web searches
- LinkedIn Research: Up to 25 web searches
- Enables comprehensive research while managing API usage

### Output Structure
The workflow generates structured research reports containing:

**For Blog Content Strategy**:
- Industry best practices and benchmarks
- Content mix recommendations
- Funnel stage content allocation
- Successful content patterns
- Topic recommendations

**For LinkedIn Research**:
- Peer category benchmarks
- Industry trend analysis
- Audience topic intelligence
- Executive positioning insights
- Content strategy recommendations

### Parallel Processing
When both research types are enabled, they run in parallel after data loading, significantly reducing total execution time while maintaining research quality.