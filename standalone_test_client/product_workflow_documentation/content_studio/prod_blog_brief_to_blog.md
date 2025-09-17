# Blog Brief to Blog Generation Workflow

## Overview
This workflow transforms a blog content brief into a complete, SEO-optimized blog post. It enriches the brief with domain knowledge from the knowledge base, generates comprehensive content, and includes human-in-the-loop approval with iterative feedback processing and content refinement.

## Frontend User Flow
[To be provided later]

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_studio/wf_blog_brief_to_blog.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_brief_to_blog.py`

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point that accepts company name, brief document name, and post UUID.

**Process**:
- Receives company_name for document namespace
- Accepts brief_docname to identify which brief to use
- Takes post_uuid for unique post identification
- Sets initial_status (defaults to "draft") for document versioning

### 2. Load All Context Documents
**Node ID**: `load_all_context_docs`

**Purpose**: Loads all necessary context documents for blog generation.

**Process**:
- Loads the blog content brief using company_name and brief_docname
- Loads company guidelines document for brand consistency
- Loads SEO best practices from system entity for optimization guidance
- All documents loaded with schema validation disabled for flexibility

### 3. Knowledge Enrichment LLM
**Node ID**: `knowledge_enrichment_llm`

**Purpose**: Enriches the brief with relevant domain knowledge and research.

**Process**:
- Uses prompt constructor (`construct_knowledge_enrichment_prompt`) to prepare context
- Performs document searches to gather relevant information
- Enriches brief with industry insights, statistics, and examples
- Supports parallel tool calls for efficient research
- Routes through condition checker to manage tool execution flow
- Tool executor node handles actual document searches when needed

**Prompt Configuration**:
- **System Prompt**: [`KNOWLEDGE_ENRICHMENT_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_brief_to_blog.py#LKNOWLEDGE_ENRICHMENT_SYSTEM_PROMPT)
- **User Template**: [`KNOWLEDGE_ENRICHMENT_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_brief_to_blog.py#LKNOWLEDGE_ENRICHMENT_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `blog_brief`: The content brief to be enriched
  - `company_name`: Company context for relevant research
- **Output Schema**: [`KNOWLEDGE_ENRICHMENT_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_brief_to_blog.py#LKNOWLEDGE_ENRICHMENT_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: openai
- Model: gpt-5
- Temperature: 0.7
- Max Tokens: 20000
- Tool Calling: Enabled with parallel calls
- Reasoning Effort: High

### 4. Content Generation LLM
**Node ID**: `content_generation_llm`

**Purpose**: Generates the complete blog post from enriched brief.

**Process**:
- Uses prompt constructor (`construct_content_generation_prompt`) with enriched context
- Generates SEO-optimized blog content following company guidelines
- Creates structured content with proper headings, meta descriptions, and keywords
- Outputs complete blog post ready for review

**Prompt Configuration**:
- **System Prompt**: [`CONTENT_GENERATION_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_brief_to_blog.py#LCONTENT_GENERATION_SYSTEM_PROMPT)
- **User Template**: [`CONTENT_GENERATION_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_brief_to_blog.py#LCONTENT_GENERATION_USER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `blog_brief`: Original brief
  - `enriched_context`: Knowledge-enriched information
  - `company_guidelines`: Brand and style guidelines
  - `seo_best_practices`: SEO optimization rules
- **Output Schema**: [`CONTENT_GENERATION_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_brief_to_blog.py#LCONTENT_GENERATION_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: openai
- Model: gpt-4.1
- Temperature: 0.7
- Max Tokens: 20000

### 5. Store Draft
**Node ID**: `store_draft`

**Purpose**: Saves the generated blog post as a draft.

**Process**:
- Stores blog post in customer namespace
- Uses post_uuid for unique identification
- Saves with initial_status (draft)
- Enables versioning for tracking changes
- Document name: "blog_post"

### 6. Content Approval HITL
**Node ID**: `content_approval`

**Purpose**: Human review and approval of generated content.

**Process**:
- Presents generated blog post for review
- Allows approval, revision request, save as draft, or cancellation
- Routes to different paths based on user action:
  - Approved: Saves final draft
  - Needs revision: Enters feedback loop (max 10 iterations)
  - Save draft: Saves current version as draft
  - Cancel: Deletes draft and ends workflow

### 7. Feedback Analysis LLM (Conditional)
**Node ID**: `feedback_analysis_llm`

**Purpose**: Analyzes feedback and generates content updates when revision is requested.

**Process**:
- Activated when iteration limit not exceeded
- Uses `construct_feedback_analysis_prompt` to process feedback
- Analyzes user feedback to identify required changes
- Generates specific update instructions
- Feeds into `construct_content_update_prompt` for content regeneration

**Prompt Configuration**:
- **System Prompt**: [`FEEDBACK_ANALYSIS_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_brief_to_blog.py#LFEEDBACK_ANALYSIS_SYSTEM_PROMPT)
- **User Template**: [`FEEDBACK_ANALYSIS_USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_brief_to_blog.py#LFEEDBACK_ANALYSIS_USER_PROMPT_TEMPLATE)
- **Output Schema**: [`FEEDBACK_ANALYSIS_OUTPUT_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_brief_to_blog.py#LFEEDBACK_ANALYSIS_OUTPUT_SCHEMA)

**Model Configuration**:
- Provider: openai
- Model: gpt-4.1
- Temperature: 0.7
- Max Tokens: 20000

### 8. Save Final Draft
**Node ID**: `save_final_draft`

**Purpose**: Saves the approved blog post as final version.

**Process**:
- Updates blog post status to "approved"
- Stores in customer namespace with versioning
- Maintains post_uuid for tracking
- Document marked as final deliverable

### 9. Save Draft (Alternative Path)
**Node ID**: `save_draft`

**Purpose**: Saves current version as draft when user chooses to save progress.

**Process**:
- Updates draft with current content
- Maintains draft status
- Allows user to return later for completion
- Returns to content approval for continued editing

### 10. Delete Draft on Cancel
**Node ID**: `delete_draft_on_cancel`

**Purpose**: Removes draft when user cancels the workflow.

**Process**:
- Deletes the draft blog post from storage
- Cleans up temporary data
- Ends workflow without saving

## Workflow Configuration
- **Maximum LLM Iterations**: 10 (for feedback loops)
- **Maximum Tool Calls**: 15 (for knowledge enrichment)
- **Temperature**: 0.7 for creative content generation
- **Tool-calling Model**: gpt-5 (for research)
- **Default Model**: gpt-4.1 (for content generation)
- **Document Versioning**: Enabled for all blog posts