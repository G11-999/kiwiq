## Usage Guide: DeleteCustomerDataNode

This guide explains how to configure and use the `DeleteCustomerDataNode` to find and delete documents stored in the customer data store. It is written for workflow builders and product teams (not a technical design doc).

### Purpose

Use this node when you want to remove customer data records that match certain criteria, such as:
- Cleaning up stale or test data
- Removing documents created during a time window
- Deleting items under a particular namespace/docname pattern

The node will:
- Run a system-level search to locate candidate documents
- Delete each document found (fail-fast by default)
- Return a summary (counts, sample identifiers, any failures if configured)

### How it Works (high level)

1) You provide search criteria (namespace/docname patterns, optional `value_filter`, etc.).
2) The node finds matching documents using a system search.
3) The node deduplicates results per document and deletes each document once.
4) If any delete fails, the node stops and fails by default. You can opt into continuing on errors.

---

## Configuration (`NodeConfig`)

You configure the node under its `node_config` field in the GraphSchema. The node accepts configuration directly or via input overrides.

### Configuration source

Provide search parameters using exactly one of these methods:
- `search_params` (static, inside `node_config`), or
- `search_params_input_path` (dynamic, a dot-path into the node input where a dict of search parameters exists)

If both are present, the data at `search_params_input_path` overrides the static values. In most workflows, prefer `search_params_input_path` so product teams can provide parameters via the input node.

### Search Parameters

The search object supports:
- `namespace_pattern` (string, required): Namespace wildcard pattern (e.g., "content_briefs", "invoices*").
- `docname_pattern` (string, required): Docname wildcard pattern (e.g., "*", "2025-*").
- `text_search_query` (string, optional): Text search term.
- `value_filter` (object, optional): Filter on document values (e.g., a date range).
- `skip` (int, optional, default 0): Pagination offset.
- `limit` (int, optional, default 1000): Pagination limit.
- `sort_by` (enum, optional): `CREATED_AT` or `UPDATED_AT`.
- `sort_order` (enum, optional): `ASC` or `DESC` (default).

Notes:
- Sorting and pagination are usually not required for deletes; keep defaults unless needed.
- The node automatically performs system search in a mode intended for mutations (permissions-aware); this is not configurable.

### Delete Options

Set these in `node_config`, and optionally override them at runtime via `delete_options_input_path` pointing to a dict in the node input:
- `dry_run` (bool, default `false`): If `true`, no deletions happen; the node only reports what would be deleted.
- `continue_on_error` (bool, default `false`): If `true`, keep deleting after a failure and report failures at the end. By default, the node fails on the first delete error.
- `max_deletes` (int, optional): Safety cap for how many documents to delete in one run.
- `on_behalf_of_user_id` (UUID string, optional): Act on behalf of another user (requires superuser). Usually not needed.

### Permissions

- Deleting shared or user-specific data requires normal user access to those paths.
- Deleting system entities or acting `on_behalf_of_user_id` requires a superuser workflow context.
- If no matching documents are found, the node logs a warning and completes successfully.

---

## Input

If you use dynamic configuration, provide the search parameters in the node input and set `search_params_input_path` accordingly. Example input mapped from an input node:

```json
{
  "search_params": {
    "namespace_pattern": "content_briefs",
    "docname_pattern": "*",
    "value_filter": {
      "scheduled_date": {
        "$gt": "2025-08-14T00:00:00Z",
        "$lte": "2025-08-17T00:00:00Z"
      }
    }
  }
}
```

Optionally, you can pass delete options via input using `delete_options_input_path` (e.g., "delete_options").

---

## Output

The node returns a simple summary object with the following fields:
- `found_count` (int): Number of unique documents found by the search.
- `deleted_count` (int): Number of documents successfully deleted.
- `dry_run` (bool): Whether this run was a dry run.
- `deleted_documents` (list): Identifiers of deleted docs (org_id if applicable, namespace, docname, is_shared, is_versioned, is_system_entity).
- `failures` (list): Only populated if `continue_on_error=true`. Each failure includes the document identifiers and an error message.

---

## Example `GraphSchema` Snippet

```json
{
  "nodes": {
    "input_node": {
      "node_id": "input_node",
      "node_name": "input_node",
      "node_config": {}
    },
    "delete_node": {
      "node_id": "delete_node",
      "node_name": "delete_customer_data",
      "node_config": {
        "search_params_input_path": "search_params"
        // Optionally allow dynamic delete options too:
        // "delete_options_input_path": "delete_options"
      }
    },
    "output_node": {
      "node_id": "output_node",
      "node_name": "output_node",
      "node_config": {}
    }
  },
  "edges": [
    {
      "src_node_id": "input_node",
      "dst_node_id": "delete_node",
      "mappings": [
        {"src_field": "search_params", "dst_field": "search_params"}
        // If using runtime delete options:
        // {"src_field": "delete_options", "dst_field": "delete_options"}
      ]
    },
    {
      "src_node_id": "delete_node",
      "dst_node_id": "output_node",
      "mappings": [
        {"src_field": "found_count", "dst_field": "found_count"},
        {"src_field": "deleted_count", "dst_field": "deleted_count"},
        {"src_field": "dry_run", "dst_field": "dry_run"},
        {"src_field": "deleted_documents", "dst_field": "deleted_documents"},
        {"src_field": "failures", "dst_field": "failures"}
      ]
    }
  ],
  "input_node_id": "input_node",
  "output_node_id": "output_node"
}
```

### Example runtime inputs

```json
{
  "search_params": {
    "namespace_pattern": "content_briefs",
    "docname_pattern": "*",
    "value_filter": {
      "scheduled_date": {
        "$gt": "2025-08-14T00:00:00Z",
        "$lte": "2025-08-17T00:00:00Z"
      }
    }
  }
  // Optionally:
  // "delete_options": { "dry_run": true, "continue_on_error": true, "max_deletes": 100 }
}
```

---

## Tips for Product Teams

- **Start with dry runs**: Set `dry_run=true` first to review which documents would be deleted.
- **Use caps in sensitive environments**: Set `max_deletes` to a small number initially.
- **Fail-fast is safest**: Default behavior stops at the first failure so you can investigate immediately. Switch to `continue_on_error=true` only when you want a full sweep with a failure report.
- **Be precise**: Combine namespace/docname patterns and `value_filter` to target exactly what you need.
- **Permissions**: Deleting system data or acting on behalf of a user requires superuser context.

---

## Related Files

- Node implementation: `services/workflow_service/registry/nodes/db/delete_customer_data_node.py`
- Example workflow: `standalone_test_client/kiwi_client/workflows/examples/wf_delete_customer_data_eg.py`
- Reference guide (loading): `docs/design_docs/workflow_service_docs/workflow_builder_guides/nodes/load_customer_data_node_guide.md`


