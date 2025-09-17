# Product Requirements Document (PRD)
## Document Context Usage in Blog Brief to Blog Workflow - Backend

**Workflow File**: `/standalone_client/kiwi_client/workflows/active/content_studio/wf_blog_brief_to_blog.py`
**LLM Inputs File**: `/standalone_client/kiwi_client/workflows/active/content_studio/llm_inputs/blog_brief_to_blog.py`

### 1. Executive Summary

This PRD outlines the backend changes needed to add document context capabilities to the Blog Brief to Blog workflow. The workflow will accept additional context documents from the previous workflow (Blog User Input to Brief) and allow users to add more documents during content review. These documents will provide additional context for blog generation and revisions.

### 2. Problem Statement

Currently, the Blog Brief to Blog workflow only uses:
- The blog brief document
- Company guidelines
- SEO best practices

It doesn't utilize the additional context documents that were uploaded and used in the Brief creation workflow, missing valuable reference materials that could improve blog quality.

### 3. Solution Overview

We will enable document context at two points:
1. **At workflow start** - Accept the list of context documents from the previous workflow
2. **During content review HITL** - Allow users to add more context documents

These documents will be used as additional context for:
- Initial blog content generation
- Content revisions based on feedback

### 4. Workflow Changes

#### 4.1 Input Changes

The workflow input will accept an optional array of document names passed from the previous workflow:
- **Field name**: `additional_context_documents`
- **Type**: Array of strings (document names without extensions)
- **Required**: False (optional)
- **Example**: `["research_report_2024", "brand_guidelines_v2", "competitor_analysis"]`
- **Source**: This field comes from the output of Blog User Input to Brief workflow

#### 4.2 New Workflow Steps

**After Input Node:**
1. Check if context documents were provided
2. If yes, load all documents using a map list router
3. Process and combine document content into a single context string
4. Continue to existing workflow steps

**During Content Generation:**
- Include document context in the prompt alongside brief, guidelines, and SEO practices
- The LLM will consider these documents when generating blog content

**During Content Approval HITL:**
1. Allow users to upload additional context documents
   - **Field name**: `hitl_context_documents`
   - **Type**: Array of strings (document names without extensions)
   - **Required**: False (optional)
2. Check if new documents were provided
3. If yes, load the new documents
4. Provide new document context as additional input to revision prompt (previous context is already in message history)

### 5. Node Additions and Modifications

#### 5.1 New Nodes Needed

1. **Check Context Documents** - Checks if context documents exist in input
2. **Context Document Router** - Routes to document loading if documents exist
3. **Load Context Documents (Map List)** - Loads multiple documents in parallel
4. **Load Single Context Document** - Loads individual document content
5. **Process Context Documents** - Combines document content into context string
6. **Check HITL Documents** - Checks for new documents during content review
7. **Load HITL Documents** - Loads newly provided documents

#### 5.2 Modified Nodes

1. **Content Generation Prompt Constructor** - Add document context as input variable
2. **Content Approval HITL** - Add field for new context documents
3. **Feedback Analysis Prompt** - Include document context for revisions
4. **Content Update Prompt** - Add document context for regeneration

### 6. Data Flow

#### 6.1 Initial Document Context Flow
```
Input with additional_context_documents → Check if documents exist →
Load documents → Process into context → Pass to content generation
```

#### 6.2 HITL Document Context Flow
```
User provides hitl_context_documents → Check new documents →
Load new documents → Pass as additional context to content revision prompt
```

### 7. Document Storage

Documents are stored using the same pattern as Brief workflow:
- Namespace: `blog_uploaded_files_{company_name}`
- Document name: The document name from the array

Each document contains:
- The extracted text content
- Metadata about the document

### 8. Prompt Updates

**Note: This document does not cover actual detailed prompt updates. The specific prompt modifications will be handled in the implementation phase.**

#### 8.1 Content Generation
Add a section to the content generation prompt:
- "Additional Context Documents" (if documents exist)
- Include the combined document context
- Instruct the LLM to consider these materials when generating content

#### 8.2 Content Revision
Add new document context to revision prompt:
- "Additional Context Documents" (if HITL documents exist)
- Include only the new document context (previous context is in message history)
- Instruct the LLM to use this context when addressing feedback

---

*Document Version: 1.0*
*Created: 2025-01-16*
*Status: Draft*