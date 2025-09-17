# LinkedIn Alternate Text Suggestion Workflow

## Overview
This workflow generates alternative text suggestions for selected portions of LinkedIn content. It loads user DNA (content playbook) for personalization, generates multiple creative alternatives based on context, includes human-in-the-loop approval with feedback capability, and supports iterative refinement based on user feedback (max 5 iterations).

## Frontend User Flow
[To be provided later]

## File Locations
- **Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_studio/wf_linkedin_alternate_text_suggestion_workflow.py`
- **LLM Inputs**: `/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_alternate_text_suggestion_workflow.py`

## Key Components

### 1. Input Node
**Node ID**: `input_node`

**Purpose**: Entry point that accepts selected text and context.

**Process**:
- Receives selected_text that user wants alternatives for
- Accepts complete_content_doc containing the full LinkedIn post
- Takes optional user_feedback for specific requirements
- Receives entity_username for loading user DNA

### 2. Load All Context Docs
**Node ID**: `load_all_context_docs`

**Purpose**: Loads user DNA/content playbook for personalization.

**Process**:
- Loads LinkedIn content playbook document
- Uses entity_username to locate user-specific document
- Provides personalization context for alternative generation
- Loaded from customer namespace

### 3. Generate Content LLM
**Node ID**: `generate_content`

**Purpose**: Generates creative alternative text suggestions.

**Process**:
- Uses prompt constructor (`construct_prompt`) to prepare context
- Generates multiple alternative versions of selected text
- Maintains consistency with overall content tone
- Incorporates user DNA for personalized suggestions

**Prompt Configuration**:
- **System Prompt**: [`SYSTEM_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_alternate_text_suggestion_workflow.py#LSYSTEM_PROMPT_TEMPLATE)
- **User Template**: [`USER_PROMPT_TEMPLATE`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_alternate_text_suggestion_workflow.py#LUSER_PROMPT_TEMPLATE)
- **Template Inputs**:
  - `selected_text`: Text to generate alternatives for
  - `content_draft`: Complete LinkedIn post for context
  - `user_dna`: User's content playbook
  - `feedback_section`: User feedback (if iterating)
- **Output Schema**: [`GENERATION_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_alternate_text_suggestion_workflow.py#LGENERATION_SCHEMA)

**Model Configuration**:
- Provider: openai
- Model: gpt-5
- Temperature: 1.0 (for creativity)
- Max Tokens: 4000

### 4. Capture Approval HITL
**Node ID**: `capture_approval`

**Purpose**: Human review and selection of alternatives.

**Process**:
- Presents generated alternatives for review
- User can approve one alternative or request revisions
- Captures optional feedback for improvements
- Routes based on approval status

### 5. Check Iteration Limit (Conditional)
**Node ID**: `check_iteration_limit`

**Purpose**: Prevents infinite feedback loops.

**Process**:
- Routes through `route_on_approval` based on user decision
- Checks if iteration count exceeds maximum (5)
- If limit reached, routes to output
- If within limit, routes to feedback processing

### 6. Construct Feedback Prompt (Conditional)
**Node ID**: `construct_feedback_prompt`

**Purpose**: Prepares feedback for next iteration.

**Process**:
- Routes through `route_on_iteration_limit` when more iterations allowed
- Constructs prompt incorporating user feedback
- Maintains conversation history for context
- Prepares for regeneration with improvements

**Prompt Configuration**:
- **System Prompt**: [`FEEDBACK_SYSTEM_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_alternate_text_suggestion_workflow.py#LFEEDBACK_SYSTEM_PROMPT)
- **Initial User Prompt**: [`FEEDBACK_INITIAL_USER_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_alternate_text_suggestion_workflow.py#LFEEDBACK_INITIAL_USER_PROMPT)
- **Additional User Prompt**: [`FEEDBACK_ADDITIONAL_USER_PROMPT`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_alternate_text_suggestion_workflow.py#LFEEDBACK_ADDITIONAL_USER_PROMPT)

### 7. Analyze Feedback LLM (Conditional)
**Node ID**: `analyze_feedback`

**Purpose**: Processes feedback to improve suggestions.

**Process**:
- Analyzes user feedback to understand requirements
- Identifies specific improvements needed
- Generates refined alternatives based on feedback
- Returns to content generation with improvements

**Prompt Configuration**:
- Uses feedback prompts defined above
- **Output Schema**: [`FEEDBACK_SCHEMA`](/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/linkedin_alternate_text_suggestion_workflow.py#LFEEDBACK_SCHEMA)

**Model Configuration**:
- Provider: openai
- Model: gpt-5
- Temperature: 1.0
- Max Tokens: 4000

## Workflow Flow Control

The workflow includes routing logic for iteration management:

- **route_on_approval**: Routes based on user approval status
  - "approved" → output_node
  - "needs_work" → check_iteration_limit
  
- **route_on_iteration_limit**: Routes based on iteration count
  - Within limit → construct_feedback_prompt
  - Limit exceeded → output_node

## Workflow Configuration
- **Maximum Iterations**: 5
- **Primary LLM**: GPT-5 (OpenAI)
- **Temperature**: 1.0 (for creative alternatives)
- **Max Tokens**: 4000
- **User DNA Integration**: LinkedIn content playbook for personalization