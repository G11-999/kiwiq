# Product Requirements Document (PRD)
## Document Upload and Context Usage in Blog User Input to Brief Workflow - Backend

**Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_studio/wf_blog_user_input_to_brief.py`
**LLM Inputs File**: `/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_user_input_to_brief.py`

### 1. Executive Summary

This PRD outlines the backend changes needed to add document upload capabilities to the Blog User Input to Brief workflow. Users will be able to upload reference documents that will be used as additional context when generating topics and briefs. They can also add more documents during the brief review phase.

### 2. Problem Statement

Currently, the workflow only uses:
- User's text input
- Company profile and content strategy documents
- Web research from Google and Reddit

Users often have valuable reference materials (PDFs, previous content, research reports) that could improve the quality of generated topics and briefs. There's no way to include these user-provided documents in the workflow.

### 3. Solution Overview

We will enable document uploads at two points in the workflow:
1. **At the start** - Users can upload documents when initiating the workflow
2. **During brief review** - Users can add more documents while reviewing the generated brief

These documents will be used as additional context for:
- Topic generation
- Brief creation
- Brief revisions

All documents used will be tracked and passed to downstream workflows.

### 4. Workflow Changes

#### 4.1 Input Changes

The workflow input will accept an optional array of document names:
- **Field name**: `uploaded_document_names`
- **Type**: Array of strings (document names without extensions)
- **Required**: False (optional)
- **Example**: `["research_report_2024", "brand_guidelines_v2", "previous_blog_content"]`

#### 4.2 New Workflow Steps

**After Input Node:**
1. Check if documents were uploaded
2. If yes, load all documents using a map list router
3. Process and combine document content into a single context string
4. Continue to existing workflow steps

**During Topic Generation:**
- Include document context in the prompt alongside existing inputs
- The LLM will consider uploaded documents when suggesting topics

**During Brief Generation:**
- Include document context in the prompt
- The LLM will incorporate insights from documents into the brief

**During Brief Review (HITL):**
1. Allow users to upload additional documents
   - **Field name**: `hitl_uploaded_document_names`
   - **Type**: Array of strings (document names without extensions)
   - **Required**: False (optional)
2. Check if new documents were uploaded
3. If yes, load the new documents
4. Provide new document context as additional input to revision prompt (previous context is already in message history)

**Before Output:**
- Aggregate all document names (initial + HITL uploads)
- Include aggregated document name list in the workflow output for downstream use
  - **Output field name**: `additional_context_documents`
  - **Type**: Array of strings (all document names used, not content)

### 5. Node Additions and Modifications

#### 5.1 New Nodes Needed

1. **Document Check Condition** - Checks if documents exist in the input
2. **Document Router** - Routes to document loading if documents exist
3. **Document Loader (Map List)** - Loads multiple documents in parallel
4. **Single Document Loader** - Loads individual document content
5. **Document Processor** - Combines document content and extracts metadata
6. **HITL Document Check** - Checks for new documents during brief review
7. **HITL Document Loader** - Loads newly uploaded documents
8. **Document Name Aggregator** - Aggregates all document names (not content) before output

#### 5.2 Modified Nodes

1. **Topic Generation Prompt** - Add document context as an input variable
2. **Brief Generation Prompt** - Add document context as an input variable
3. **Brief Approval HITL** - Add field for new document uploads
4. **Brief Revision Prompt** - Include updated document context

### 6. Data Flow

#### 6.1 Initial Document Flow
```
User uploads documents → Check if documents exist → Load documents →
Process into context → Pass to topic generation
```

#### 6.2 HITL Document Flow
```
User uploads new documents during review → Check new documents →
Load new documents → Pass as additional context to brief revision prompt
```

#### 6.3 Output Flow
```
Aggregate all document names → Include name list in output →
Available for content creation workflow
```

### 7. Document Storage

Documents will be stored using the pattern:
- Namespace: `blog_uploaded_files_{company_name}`
- Document name: The document name from the input array

Each document will contain:
- The extracted text content
- Metadata (size, page count, upload time, etc.)

### 8. Prompt Updates

**Note: This document does not cover actual detailed prompt updates. The specific prompt modifications will be handled in the implementation phase.**

#### 8.1 Topic Generation
Add a section to the prompt:
- "Reference Documents Provided" (if documents exist)
- Include the combined document context
- Instruct the LLM to consider these materials when suggesting topics

#### 8.2 Brief Generation
Add a section to the prompt:
- "Reference Documents" (if documents exist)
- Include the combined document context
- Instruct the LLM to incorporate insights from documents

#### 8.3 Brief Revision
Add new document context to revision prompt:
- "Additional Reference Documents" (if HITL documents exist)
- Include only the new document context (previous context is in message history)
- Instruct the LLM to consider new materials for revisions

---

*Document Version: 1.0*
*Created: 2025-01-16*
*Status: Draft*