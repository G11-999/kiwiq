# Content Studio Workflows

## Overview
Content Studio workflows handle the creation, optimization, and management of various content types including blog posts and LinkedIn content. These workflows incorporate AI-powered research, generation, and human-in-the-loop refinement.

## Available Workflows

### Blog Content Workflows

#### 1. [Blog User Input to Brief](./blog_user_input_to_brief.md)
- **File**: `wf_blog_user_input_to_brief.py`
- **Purpose**: Transforms user ideas into comprehensive, research-backed content briefs
- **Key Features**: Google/Reddit research, topic generation, HITL approval
- **Status**: ✅ Documented

#### 2. Blog Brief to Blog
- **File**: `wf_blog_brief_to_blog.py`
- **Purpose**: Converts approved briefs into full blog posts
- **Status**: 📝 To be documented

#### 3. Blog Calendar Selected Topic to Brief
- **File**: `wf_blog_calendar_selected_topic_to_brief.py`
- **Purpose**: Creates briefs from calendar-selected topics
- **Status**: 📝 To be documented

#### 4. Blog Content Calendar Entry
- **File**: `wf_blog_content_calendar_entry.py`
- **Purpose**: Manages blog content calendar entries
- **Status**: 📝 To be documented

#### 5. Blog Content Optimisation Workflow
- **File**: `wf_blog_content_optimisation_workflow.py`
- **Purpose**: Optimizes existing blog content
- **Status**: 📝 To be documented

### LinkedIn Content Workflows

#### 1. LinkedIn User Input to Brief
- **File**: `wf_linkedin_user_input_to_brief.py`
- **Purpose**: Creates LinkedIn content briefs from user input
- **Status**: 📝 To be documented

#### 2. LinkedIn Calendar Selected Topic to Brief
- **File**: `wf_linkedin_calendar_selected_topic_to_brief.py`
- **Purpose**: Generates LinkedIn briefs from calendar topics
- **Status**: 📝 To be documented

#### 3. LinkedIn Content Calendar Entry
- **File**: `wf_linkedin_content_calendar_entry.py`
- **Purpose**: Manages LinkedIn content calendar
- **Status**: 📝 To be documented

#### 4. LinkedIn Content Creation Workflow
- **File**: `wf_linkedin_content_creation_workflow.py`
- **Purpose**: Creates complete LinkedIn posts
- **Status**: 📝 To be documented

#### 5. LinkedIn Alternate Text Suggestion Workflow
- **File**: `wf_linkedin_alternate_text_suggestion_workflow.py`
- **Purpose**: Suggests alternative text variations for LinkedIn posts
- **Status**: 📝 To be documented

## Common Components

### LLM Inputs
All workflows use prompt templates and schemas stored in the `llm_inputs/` directory:
- System prompts for each stage
- User prompt templates with variables
- Output schemas for structured responses
- Feedback analysis prompts

### Document Models
Workflows interact with standardized document models:
- Company profiles
- Content strategies/playbooks
- Content briefs
- Published content

### HITL Integration
Most workflows include Human-in-the-Loop nodes for:
- Topic selection
- Brief approval
- Content review
- Iterative refinement with feedback

## Workflow Patterns

### Research → Generation → Refinement
1. Load context (company, strategy)
2. Conduct research (web, social)
3. Generate options (topics, briefs)
4. Human selection/approval
5. Iterative refinement
6. Final storage

### Iteration Limits
- Maximum regenerations: 3
- Maximum revisions: 3
- Maximum HITL iterations: 10

### State Management
- Persistent state via `$graph_state`
- Message history tracking
- Metadata for iteration counting
- Reducer patterns for updates

## Integration Points
- Customer data storage system
- Version control for documents
- HITL notification system
- Workflow runner API
- Analytics and monitoring

## Best Practices
1. Always load company context first
2. Use research to inform generation
3. Implement iteration limits
4. Support manual editing in HITL
5. Auto-save drafts at key points
6. Maintain clear audit trails
7. Version all document changes

## Next Steps
- Complete documentation for remaining workflows
- Create workflow comparison matrix
- Add performance benchmarks
- Document error handling patterns