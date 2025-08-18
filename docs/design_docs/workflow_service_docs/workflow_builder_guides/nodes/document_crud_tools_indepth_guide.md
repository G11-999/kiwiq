# Document CRUD Tools — In‑Depth Usage Guide (for Product Teams)

This guide explains how to use the document management tools available to workflows and LLM agents:

- `view_documents`: Read a single document or list multiple documents
- `list_documents`: Browse documents (metadata only, fast)
- `search_documents`: Find content inside documents using AI (RAG)
- `edit_document`: Modify or delete a document

New in this version:
- `value_filter` (optional) for both `list_documents` and `search_documents` to filter by exact key/value pairs in document data.

The focus here is practical usage: what each tool is for, how to combine them, configuration choices, edge cases, and how to prompt LLMs to use them effectively. This is not a technical design doc; it’s a hands‑on usage guide, including system documents (playbooks, guidelines) scenarios.

If you’re wiring these tools inside workflows, see the separate reference: “ToolExecutorNode Usage Guide” in `llm_tools_executor_and_document_crud_guide.md`.


## Core concepts (read first)

Before using the tools, a few shared concepts help everything click.

- **doc_key**: The type of document (e.g., `brief`, `concept`, `user_dna_doc`, or a system doc key like `system_playbook_doc`). Product teams do not need the full template details; just use the correct `doc_key` as configured in your environment.
- **High cardinality vs. unitary docs**:
  - High cardinality docs have many instances (e.g., many `brief`s). You must identify which one to act on.
  - Unitary docs exist as a single canonical document per entity (e.g., `user_dna_doc`). Often just the `doc_key` is enough.
- **DocumentIdentifier (how a document is selected)**:
  - Always includes `doc_key`.
  - For high cardinality docs, provide either:
    - `docname` (the exact name), or
    - `document_serial_number` (a human‑readable tag the tools generate, e.g., `brief_78_1`), which requires a `view_context` provided by a prior `view_documents`/`list_documents`/`search_documents` run.
  - For unitary docs, `doc_key` alone can be sufficient.
- **Serial numbers & view context**:
  - Listing/searching tools return a dictionary keyed by generated serial numbers (e.g., `brief_23_2`). They also return `state_changes` you can store as `view_context`.
  - Subsequent tool calls can reference those serial numbers instead of exact names, which is safer for LLMs and humans.
- **Versioning & shared vs. user documents**:
  - Some docs are versioned (e.g., drafts/briefs); others are unversioned (e.g., unitary configs).
  - Some docs are user‑specific; others are shared; system docs are read‑only by default.
- **System documents**:
  - Curated, organization‑wide content (e.g., playbooks, guidelines). They are discoverable and searchable. Editing is typically disabled in production (configurable) and should be routed through approval if allowed.
- **Context provisioning**:
  - The workflow typically passes `entity_username` and/or `company_name` (depending on doc family) and the evolving `view_context` automatically to tools. You should not ask LLMs to invent these.
  - Use `entity_username` for LinkedIn/user‑centric docs; use `company_name` for blog/company‑centric docs. Both are supported and only the relevant one is used by each template.


## Quick “which tool do I use?”

- I want to quickly browse what exists by type/date → use `list_documents` (fast metadata only)
- I want full content of a specific doc or a small set → use `view_documents`
- I want to find text inside documents → use `search_documents`
- I need to change a document → use `edit_document` (typically after viewing it)

Recommended flow for AI agents: discover (list/search) → view (confirm exact doc) → edit (if needed) → view (verify).


## Tool details and best‑practice usage

### 1) View Documents (`view_documents`)

Purpose: Retrieve full content of a specific document or list multiple documents with content.

Two modes:

1) Single document
- Provide `document_identifier` with `doc_key` and either `docname` or `document_serial_number`.

2) List mode
- Provide `list_filter` to discover multiple docs (by `doc_key` or by `namespace_of_doc_key`).
- Supports optional date filters and pagination (`limit` 1–10, default 5; `offset`).

Key input fields:

- `document_identifier`: Uses `DocumentIdentifier` (see Core concepts). For high cardinality docs, prefer a prior list/search to generate a serial number, then reference it here.
- Context: Provide `entity_username` (LinkedIn/user-centric) or `company_name` (blog/company-centric) as applicable; both are supported and provided by the workflow, not by LLMs.
- `list_filter`: Uses `DocumentListFilter`:
  - Provide either `doc_key` or `namespace_of_doc_key` (not both).
  - Optional date ranges:
    - `scheduled_date_range_start/end` (for doc types that support scheduling)
    - `created_at_range_start/end`
- Context: Provide `entity_username` or `company_name` based on the target doc family; the underlying resolver uses the relevant one.
- `limit`, `offset`: Pagination for list mode. `limit` is capped at 10.

Output:

- `documents`: Dict keyed by serial number → each value includes metadata and full content
- `state_changes`: Dict keyed by the same serial numbers (docname/version) to merge into `view_context`
- `view_mode`: `single` or `list`

Config (`node_config`):

- `max_view_limit` (int): Maximum number of documents that can be returned at once (default 10). Use lower limits for performance; increase cautiously if you truly need bigger batches.

Example — view a single unitary doc by `doc_key`:

```json
{
  "tool_name": "view_documents",
  "tool_input": {
    "document_identifier": {
      "doc_key": "user_dna_doc"
    }
  }
}
```

Example — list recent `concept` documents and get their contents:

```json
{
  "tool_name": "view_documents",
  "tool_input": {
    "list_filter": {
      "doc_key": "concept",
      "created_at_range_start": "2024-01-01T00:00:00Z"
    },
    "limit": 5
  }
}
```

Example — view a specific doc via prior serial number:

```json
{
  "tool_name": "view_documents",
  "tool_input": {
    "document_identifier": {
      "doc_key": "brief",
      "document_serial_number": "brief_78_1"
    }
  }
}
```

When to use: After discovery (`list_documents` or `search_documents`) to fetch full content for inspection or to prepare for editing.


### 2) List Documents (`list_documents`)

Purpose: Fast browsing and pagination with metadata only (no full content). Ideal for UIs and quick discovery.

Inputs:

- `list_filter` (`DocumentListFilter`): Provide either `doc_key` or `namespace_of_doc_key`. Optionally add date ranges.
- `list_filter.value_filter` (optional): List of `{key, value}` pairs to match exactly against document data. Keys support dot-notation for nested fields (e.g., `metadata.category`). Only equality matches are supported here.
- `limit` (1–10, default 10) and `offset` for pagination.

Output:

- `documents`: Dict keyed by serial number → metadata only
- `state_changes`: Same serial numbers you can merge into `view_context` and reuse later
- `filter_applied`: Echo of the effective query parameters

Config (`node_config`):

- `max_list_limit` (int): Upper bound on how many docs can be listed at once (default 10).

Example — list scheduled `brief` docs for a date range:

```json
{
  "tool_name": "list_documents",
  "tool_input": {
    "list_filter": {
      "doc_key": "brief",
      "scheduled_date_range_start": "2024-01-15T00:00:00Z",
      "scheduled_date_range_end": "2024-01-22T00:00:00Z"
    },
    "limit": 10
  }
}
```

When to use: First step to discover candidates. Follow up with `view_documents` for content or `search_documents` if you need text search.

Example — list concepts with an exact value filter:

```json
{
  "tool_name": "list_documents",
  "tool_input": {
    "list_filter": {
      "doc_key": "concept",
      "value_filter": [{"key": "status", "value": "published"}]
    },
    "limit": 10
  }
}
```


### 3) Search Documents (`search_documents`)

Purpose: Find content using AI search (hybrid vector + keyword) via the RAG service. It can search within a single document or across many.

Requirements: RAG must be available and the documents you expect to find should be ingested into RAG.

Inputs:

- `search_query` (string): The text to find.
- Target scope (provide at most one):
  - `document_identifier`: Search within a single document.
  - `list_filter`: Search across all documents that match the filter.
  - If neither is provided, you can use `search_only_system_entities: true` to search only system docs globally.
- Options:
  - `limit` (1–10, default 10), `offset` for pagination
  - `search_only_system_entities` (bool): If true (and if no other filters override), restrict the search to system docs
  - `value_filter` (optional): List of `{key, value}` pairs to post-filter results. The tool over-fetches from RAG (up to 100 when 10 are requested), fetches each candidate's full document, filters by the provided key/value pairs, and returns up to the requested `limit` after filtering.

Output:

- `results`: Dict keyed by serial number → each item has metadata, a content preview, an optional score, and (optionally) full contents
- `state_changes`: Same serial numbers to merge into `view_context`
- `total_results`, `search_scope`: Summary

Config (`node_config`):

- `return_full_document_contents` (bool): If true, fetch full contents for each result (slower).
- `max_results_limit` (int): Cap on results per call (default 10).

Examples — search across briefs:

```json
{
  "tool_name": "search_documents",
  "tool_input": {
    "search_query": "Q4 goals",
    "list_filter": {"doc_key": "brief"},
    "limit": 10
  }
}
```

Example — search within one document by serial number:
Example — search concepts with value filters (post-filtering):

```json
{
  "tool_name": "search_documents",
  "tool_input": {
    "search_query": "Q4 goals",
    "list_filter": {"doc_key": "concept"},
    "value_filter": [
      {"key": "status", "value": "published"},
      {"key": "metadata.category", "value": "b2b"}
    ],
    "limit": 10
  }
}
```

```json
{
  "tool_name": "search_documents",
  "tool_input": {
    "search_query": "marketing strategy",
    "document_identifier": {
      "doc_key": "brief",
      "document_serial_number": "brief_78_1"
    }
  }
}
```

When to use: To quickly locate relevant content, then hand off to `view_documents` to read fully or to `edit_document` to modify. Provide `entity_username` or `company_name` depending on the doc family; the resolver uses whichever is relevant.


### 4) Edit Document (`edit_document`)

Purpose: Apply edits to one document or delete it. Supports JSON and text operations, including nested JSON edits with array indices.

Inputs:

- `document_identifier`: Select the target document (see Core concepts). For high cardinality docs, always specify `docname` or use `document_serial_number` plus `view_context`.
- `operations` (list, at least one): Apply in sequence; the tool stops on the first failure.
  - Operation types:
    - `json_upsert_keys` → Provide `json_operation.json_keys`
    - `json_edit_key` → Provide `json_operation.json_key_path` and exactly one of:
      - `json_operation.replacement_value` (replace the value), or
      - `json_operation.text_edit_on_value` (substring replace or position insert on the string at that path)
    - `text_replace_substring` → Provide `text_operation.text_to_find` and `text_operation.replacement_text`
    - `text_add_at_position` → Provide `text_operation.position` and `text_operation.text_to_add`
    - `replace_document` → Provide `new_content` (string or JSON). Strings that are valid JSON will be parsed; otherwise stored as text.
    - `delete_document` → No additional fields; stops further processing.

Output:

- `operation_results`: Per‑operation success messages or errors
- `final_content`: Final content after all successful operations (not for deletes)
- `document_info`, `success`, `message`: Summary

Config (`node_config`):

- `max_document_size_mb` (float): Safety/guardrail for large docs.
- `allow_system_document_edits` (bool): Defaults to false. Keep false in production unless a strong approval flow exists.

Examples — upsert JSON keys:

```json
{
  "tool_name": "edit_document",
  "tool_input": {
    "document_identifier": {
      "doc_key": "brief",
      "document_serial_number": "brief_78_1"
    },
    "operations": [
      {
        "operation_type": "json_upsert_keys",
        "json_operation": {
          "json_keys": {"status": "published", "priority": "high"}
        }
      }
    ]
  }
}
```

Example — edit a nested array element:

```json
{
  "tool_name": "edit_document",
  "tool_input": {
    "document_identifier": {"doc_key": "brief", "docname": "brief_123..."},
    "operations": [
      {
        "operation_type": "json_edit_key",
        "json_operation": {
          "json_key_path": "items.2.price",
          "replacement_value": 19.99
        }
      }
    ]
  }
}
```

Example — text replacement inside a JSON string value at a path:

```json
{
  "tool_name": "edit_document",
  "tool_input": {
    "document_identifier": {"doc_key": "concept", "document_serial_number": "concept_23_2"},
    "operations": [
      {
        "operation_type": "json_edit_key",
        "json_operation": {
          "json_key_path": "description",
          "text_edit_on_value": {
            "text_to_find": "original description",
            "replacement_text": "updated description"
          }
        }
      }
    ]
  }
}
```

Example — delete a document:

```json
{
  "tool_name": "edit_document",
  "tool_input": {
    "document_identifier": {"doc_key": "brief", "document_serial_number": "brief_42_1"},
    "operations": [{"operation_type": "delete_document"}]
  }
}
```

When to use: After you’ve confirmed the correct doc via `view_documents`. Keep edits small and explicit. Prefer multiple smaller operations rather than one huge replacement for traceability.


## Working with System Documents (playbooks, guidelines)

System docs are curated, global assets (e.g., “Tone of Voice Guidelines”, “SEO Playbook”, “LinkedIn Outreach Playbook”). They are often read‑only in production.

How to find and use them:

- Search across system docs on demand:

```json
{
  "tool_name": "search_documents",
  "tool_input": {
    "search_query": "LinkedIn outreach messaging",
    "search_only_system_entities": true,
    "limit": 10
  }
}
```

- List system docs by `doc_key` (your environment will have specific system doc keys, e.g., `system_playbook_doc`, `guidelines_doc`):

```json
{
  "tool_name": "list_documents",
  "tool_input": {
    "list_filter": {"doc_key": "system_playbook_doc"},
    "limit": 10
  }
}
```

- View a specific system doc by serial number from a prior list/search:

```json
{
  "tool_name": "view_documents",
  "tool_input": {
    "document_identifier": {
      "doc_key": "system_playbook_doc",
      "document_serial_number": "system_playbook_doc_12_1"
    }
  }
}
```

Editing system docs:

- By default, `edit_document` disallows system edits (`allow_system_document_edits: false`). If your program explicitly enables this, route through human‑in‑the‑loop approval. Otherwise, treat system docs as read‑only and copy to a user doc before modifying.


## Effective prompting patterns for LLMs

These patterns help models reliably use tools and avoid common mistakes.

General rules to bake into prompts:

- “Do not guess document names. First list or search, then reference documents via serial numbers and pass the `document_serial_number` with the current `view_context`.”
- “For high‑cardinality types (e.g., `brief`), always choose an instance explicitly via serial number or exact `docname`.”
- “When planning edits, first fetch full content (`view_documents`) to confirm the target and the exact JSON path.”
- “For system docs, prefer `search_documents` with `search_only_system_entities: true` or list with the appropriate system `doc_key`.”
- “Use small, explicit edits (`json_edit_key` or `json_upsert_keys`) rather than large replacements.”

Pattern — Discover → View → Edit → Verify:

1) Discover candidates

```json
{
  "tool_name": "list_documents",
  "tool_input": {"list_filter": {"doc_key": "brief"}, "limit": 5}
}
```

2) View the chosen doc by serial number

```json
{
  "tool_name": "view_documents",
  "tool_input": {"document_identifier": {"doc_key": "brief", "document_serial_number": "brief_78_1"}}
}
```

3) Edit a precise field

```json
{
  "tool_name": "edit_document",
  "tool_input": {
    "document_identifier": {"doc_key": "brief", "document_serial_number": "brief_78_1"},
    "operations": [{
      "operation_type": "json_edit_key",
      "json_operation": {"json_key_path": "status", "replacement_value": "published"}
    }]
  }
}
```

4) Verify (re‑view)

```json
{
  "tool_name": "view_documents",
  "tool_input": {"document_identifier": {"doc_key": "brief", "document_serial_number": "brief_78_1"}}
}
```

Pattern — Fetch guidelines/playbooks on demand (system docs):

```json
{
  "tool_name": "search_documents",
  "tool_input": {
    "search_query": "tone of voice",
    "search_only_system_entities": true,
    "limit": 5
  }
}
```

If needed, view specific results via returned serial numbers.


## Edge cases, caveats, and how to avoid them

- High cardinality without identification: For types like `brief`, you must provide `docname` or `document_serial_number`. If missing, the tools will error.
- JSON path rules in `edit_document`:
  - Dot notation with arrays allowed (e.g., `users.0.email`).
  - Numeric string keys in dicts are treated as keys, not indices (e.g., `data.4` refers to key "4").
  - Lists must already exist; the tool won’t auto‑create them. Indices must be in range; negative indices are not supported.
  - If you attempt JSON operations on non‑JSON content (or text ops on JSON objects), the tool errors. Choose the correct operation type.
- System document edits: Disabled by default. Attempts will be rejected unless explicitly enabled via config.
- Timezones: When editing date/time values, store in UTC as `YYYY-MM-DDTHH:MM:SSZ`. If you have local times, convert to UTC first before storing.
- RAG availability: `search_documents` requires the RAG service. If unavailable or documents aren’t ingested, results may be empty.
- Pagination caps: `limit` is capped at 10 for list/view/search. Use offsets to paginate.
- Value filters:
  - Only exact equality matches are supported; use date range inputs for temporal filtering.
  - Keys use document data paths (dot-notation supported). Do not prefix with `data.`.
  - For search, post-filtering requires fetching full document contents, which may add latency; the tool mitigates this by over-fetching candidates and filtering before returning up to `limit` results.

Common error messages and what they mean:

- “High cardinality document requires either `docname` or `document_serial_number`” → First list/search, then reference by serial number.
- “Provide either `doc_key` or `namespace_of_doc_key`, not both” → Fix your `list_filter` to include only one.
- “Cannot perform JSON operations on non‑JSON content” → Use `replace_document` or text operations, or fetch and confirm the content type.
- “Cannot perform text operations on JSON/dictionary content” → Use JSON operations or `replace_document` with JSON.
- “Index out of range / non‑numeric key for list” → Fix the path or confirm the structure via `view_documents`.
- “RAG service is required for search functionality” → Search won’t work until RAG is available.


## Configuration philosophies and recommended combinations

- Keep list/view limits conservative (5–10). This reduces latency and keeps the LLM context manageable.
- Prefer `list_documents` → `view_documents` over directly viewing many documents in one go.
- Use `return_full_document_contents: true` in `search_documents` only when you truly need the full content; otherwise keep it false for speed.
- Keep `allow_system_document_edits: false` in production, and route any system‑level changes via approval workflows.

Typical combinations:

- Discovery: `list_documents` with date filters → skim metadata; if needed, `view_documents` for details.
- Research: `search_documents` across a doc type or system docs → then `view_documents` for the most relevant hits.
- Editing flow: `view_documents` (confirm structure) → `edit_document` (small, explicit operations) → `view_documents` (verify).


## FAQ

- Do I need to pass `entity_username` and `view_context`? In workflows, these are typically mapped automatically. Your prompts should not ask the model to invent them.
- How do I reference a specific document without knowing its exact name? Use `list_documents` or `search_documents` first, then pass the `document_serial_number` to `view_documents`/`edit_document` together with the current `view_context`.
- Can I mix user and system docs in a single search? Yes, if you don’t restrict using filters — but prefer explicit scoping (e.g., set `search_only_system_entities` for system‑only searches) for clarity and speed.
- Are scheduled date filters universal? No. They apply only to doc types that support scheduling (e.g., `brief`, `draft`). If you include scheduled date filters for other types, you’ll get a validation error.


## See also

- Tool execution orchestration and field mapping: `llm_tools_executor_and_document_crud_guide.md`


