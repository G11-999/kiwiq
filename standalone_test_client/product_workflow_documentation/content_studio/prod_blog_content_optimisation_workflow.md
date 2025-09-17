# Blog Content Optimization Workflow

## Overview
This workflow performs comprehensive blog content optimization through multi-faceted analysis including structure, SEO, readability, and content gaps. It executes parallel analysis using dynamic routing, applies improvements sequentially (content gaps → SEO → structure/readability), includes human-in-the-loop approval for analysis results and final content, and supports feedback-driven revision cycles.

## Frontend User Flow
[To be provided later]

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_studio/wf_blog_content_optimisation_workflow.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_optimisation_workflow.py`

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point that accepts blog content for optimization.

**Process**:
- Receives company_name for document operations
- Accepts original_blog content to be optimized
- Takes post_uuid for unique identification
- Sets route_all_choices (defaults to true) for parallel analysis
- Sets initial_status (defaults to "draft")

### 2. Load Company Document
**Node ID**: `load_company_doc`

**Purpose**: Loads company context for optimization guidelines.

**Process**:
- Loads company document with brand guidelines
- Used for maintaining brand voice during optimization
- Loaded from customer namespace
- Schema loading disabled for flexibility

### 3. Content Analyzer LLM
**Node ID**: `content_analyzer_llm`

**Purpose**: Analyzes content structure and readability.

**Process**:
- Triggered via `analysis_trigger_router` for parallel execution
- Uses prompt constructor (`construct_content_analyzer_prompt`)
- Analyzes structure, flow, readability, and engagement
- Identifies areas for improvement in content organization

**Prompt Configuration**:
- **System Prompt**: [`CONTENT_ANALYZER_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_optimisation_workflow.py#LCONTENT_ANALYZER_SYSTEM_PROMPT)
- **User Template**: [`CONTENT_ANALYZER_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_optimisation_workflow.py#LCONTENT_ANALYZER_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `target_audience`: From company doc
  - `content_goals`: From company doc
  - `original_blog`: Content to analyze
- **Output Schema**: [`CONTENT_ANALYZER_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_optimisation_workflow.py#LCONTENT_ANALYZER_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: anthropic
- Model: claude-sonnet-4-20250514
- Temperature: 0.7
- Max Tokens: 8000

### 4. SEO Intent Analyzer LLM
**Node ID**: `seo_intent_analyzer_llm`

**Purpose**: Analyzes SEO optimization and search intent alignment.

**Process**:
- Runs in parallel with other analyzers
- Uses prompt constructor (`construct_seo_intent_analyzer_prompt`)
- Evaluates keyword usage, meta descriptions, headers
- Identifies SEO improvement opportunities

**Prompt Configuration**:
- **System Prompt**: [`SEO_INTENT_ANALYZER_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_optimisation_workflow.py#LSEO_INTENT_ANALYZER_SYSTEM_PROMPT)
- **User Template**: [`SEO_INTENT_ANALYZER_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_optimisation_workflow.py#LSEO_INTENT_ANALYZER_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `company_doc`: Company context
  - `original_blog`: Content to analyze
- **Output Schema**: [`SEO_INTENT_ANALYZER_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_optimisation_workflow.py#LSEO_INTENT_ANALYZER_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: anthropic
- Model: claude-sonnet-4-20250514
- Temperature: 0.7
- Max Tokens: 8000

### 5. Content Gap Finder LLM
**Node ID**: `content_gap_finder_llm`

**Purpose**: Identifies missing content through competitive analysis.

**Process**:
- Runs in parallel with other analyzers
- Uses prompt constructor (`construct_content_gap_finder_prompt`)
- Leverages Perplexity for web research
- Identifies gaps compared to competitive content

**Prompt Configuration**:
- **System Prompt**: [`CONTENT_GAP_FINDER_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_optimisation_workflow.py#LCONTENT_GAP_FINDER_SYSTEM_PROMPT)
- **User Template**: [`CONTENT_GAP_FINDER_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_optimisation_workflow.py#LCONTENT_GAP_FINDER_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `company_doc`: Company context
  - `original_blog`: Content to analyze
- **Output Schema**: [`CONTENT_GAP_FINDER_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_optimisation_workflow.py#LCONTENT_GAP_FINDER_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: perplexity
- Model: sonar-pro
- Temperature: 0.3
- Max Tokens: 3000

### 6. Analysis Review HITL
**Node ID**: `analysis_review_hitl`

**Purpose**: Human review of analysis results before applying improvements.

**Process**:
- Waits for all parallel analyses to complete (fan-in enabled)
- Presents all analysis results for review
- User can approve to proceed or cancel
- Gates the improvement phase

### 7. Content Gap Improvement LLM
**Node ID**: `content_gap_improvement_llm`

**Purpose**: Applies content gap improvements first.

**Process**:
- Uses prompt constructor (`construct_content_gap_improvement_prompt`)
- Adds missing content identified in gap analysis
- Maintains existing content while filling gaps
- First step in sequential improvement chain

**Prompt Configuration**:
- **System Prompt**: [`CONTENT_GAP_IMPROVEMENT_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_optimisation_workflow.py#LCONTENT_GAP_IMPROVEMENT_SYSTEM_PROMPT)
- **User Template**: [`CONTENT_GAP_IMPROVEMENT_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_optimisation_workflow.py#LCONTENT_GAP_IMPROVEMENT_USER_PROMPT_TEMPLATE)

### 8. SEO Intent Improvement LLM
**Node ID**: `seo_intent_improvement_llm`

**Purpose**: Applies SEO optimizations to gap-filled content.

**Process**:
- Uses prompt constructor (`construct_seo_intent_improvement_prompt`)
- Optimizes keywords, meta descriptions, headers
- Works on content already improved with gap filling
- Second step in improvement chain

**Prompt Configuration**:
- **System Prompt**: [`SEO_INTENT_IMPROVEMENT_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_optimisation_workflow.py#LSEO_INTENT_IMPROVEMENT_SYSTEM_PROMPT)
- **User Template**: [`SEO_INTENT_IMPROVEMENT_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_optimisation_workflow.py#LSEO_INTENT_IMPROVEMENT_USER_PROMPT_TEMPLATE)

### 9. Structure Readability Improvement LLM
**Node ID**: `structure_readability_improvement_llm`

**Purpose**: Final improvements to structure and readability.

**Process**:
- Uses prompt constructor (`construct_structure_readability_improvement_prompt`)
- Improves flow, transitions, and readability
- Final polish on optimized content
- Last step in improvement chain

**Prompt Configuration**:
- **System Prompt**: [`STRUCTURE_READABILITY_IMPROVEMENT_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_optimisation_workflow.py#LSTRUCTURE_READABILITY_IMPROVEMENT_SYSTEM_PROMPT)
- **User Template**: [`STRUCTURE_READABILITY_IMPROVEMENT_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_optimisation_workflow.py#LSTRUCTURE_READABILITY_IMPROVEMENT_USER_PROMPT_TEMPLATE)
- **Output Schema**: [`FINAL_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_content_optimisation_workflow.py#LFINAL_OUTPUT_SCHEMA)

### 10. Final Approval HITL
**Node ID**: `final_approval_hitl`

**Purpose**: Human review and approval of optimized content.

**Process**:
- Presents fully optimized content for review
- Allows approval, revision request, or cancellation
- Routes to different paths based on user action
- Supports feedback iterations (max 10)

### 11. Save Blog Post
**Node ID**: `save_blog_post`

**Purpose**: Saves the approved optimized blog post.

**Process**:
- Stores optimized blog in customer namespace
- Uses post_uuid for identification
- Saves with appropriate status
- Enables versioning for tracking changes

## Workflow Configuration
- **Maximum Iterations**: 10 (for feedback loops)
- **Maximum Revision Attempts**: 3
- **Primary LLM**: Claude Sonnet (Anthropic) for analysis and improvement
- **Research LLM**: Sonar Pro (Perplexity) for content gap analysis
- **Temperature**: 0.7 for improvements, 0.3 for research
- **Parallel Analysis**: All three analyses run simultaneously
- **Sequential Improvement**: Content gaps → SEO → Structure/Readability