# Usage Guide: LoadMultipleCustomerDataNode

This guide explains how to configure and use the `LoadMultipleCustomerDataNode` to retrieve **multiple** documents (like a collection of user interactions, product reviews, or configuration files) stored in the system's data store based on specified criteria.

## Purpose

Unlike the `LoadCustomerDataNode` which fetches specific, named documents, the `LoadMultipleCustomerDataNode` allows your workflow to:

-   **List** documents based on filters like namespace, ownership (user-specific vs. shared), or system status.
-   **Filter and sort** the list of found documents (e.g., get the 10 most recent shared documents in a specific namespace).
-   **Load** the content of the documents found in the list.
-   Apply general loading options (like which version to load, or whether to load schemas) to all documents retrieved.

The list of loaded documents is then added to the workflow's data stream under a single field name for use by subsequent nodes (like aggregation or processing loops).

## Configuration (`NodeConfig`)

You configure the `LoadMultipleCustomerDataNode` within the `node_config` field of its entry in the `GraphSchema`. The configuration follows the `LoadMultipleCustomerDataConfig` schema.

### Key Configuration Fields:

*   **`output_field_name` (String): Required.** The name of the field where the **list** of loaded documents will be placed in the node's output data. Example: `"loaded_user_profiles"`. **Important:** This name cannot start with an underscore (`_`).

*   **Dynamic Configuration Loading:**
    *   **`config_input_path` (String | `null`): Optional.** Allows dynamic loading of configuration from the node's input data. Provide a dot-notation path to a JSON object in the input that should override the static configuration. Examples: `"dynamic_config"`, `"config.load_settings"`.

*   **Listing Criteria:** These fields determine *which* documents are initially found.
    *   **`namespace_filter` (String | `null`): Optional.** Filters documents to a specific namespace (like a folder). If left empty (`null`) or set to `"*"`, it searches across all namespaces the user can access. Example: `"user_feedback"`.
    *   **`namespace_pattern` (String | `null`): Optional.** Alternatively, you can dynamically generate a namespace filter using an f-string-like template. Example: `"customer_{item}_data"`. Requires `namespace_pattern_input_path`.
    *   **`namespace_pattern_input_path` (String | `null`): Optional.** Dot-notation path in the input data to find values for the namespace pattern. Example: `"user_context.customer_id"`. Required when using `namespace_pattern`.
    *   **`include_shared` (Boolean):** `true` (default) includes documents shared across the organization; `false` excludes them.
    *   **`include_user_specific` (Boolean):** `true` (default) includes documents belonging only to the user running the workflow; `false` excludes them.
    *   **`include_system_entities` (Boolean):** `false` (default). Set to `true` to include system-level documents (requires special superuser permissions for the workflow run).
    *   **`on_behalf_of_user_id` (String | `null`): Optional.** (Requires superuser permissions). Provide a specific User ID here to list/load documents *as if you were that user*. This mainly affects which user-specific documents are found when `include_user_specific` is true.

*   **Pagination and Sorting:** These fields apply *after* the initial list is found, controlling which ones are actually returned and loaded.
    *   **`skip` (Integer):** `0` (default). Number of documents to skip from the beginning of the filtered list. Useful for getting "pages" of results.
    *   **`limit` (Integer):** `100` (default). Maximum number of documents to load and return (max allowed is typically 200).
    *   **`sort_by` (String | `null`): Optional.** Field to sort the document list by before applying skip/limit. Common values might be `"created_at"` or `"updated_at"` (check specific options available). Default is usually based on creation time.
    *   **`sort_order` (String):** `"desc"` (default, newest first) or `"asc"` (oldest first).

*   **Loading Options:** These options are applied *to each document* that is selected by the listing, filtering, and pagination steps.
    *   **`global_version_config` (`VersionConfig` object | `null`): Optional.** Specifies which version to load if a document is versioned.
        *   If `null` (default): Loads the **active** version.
        *   Example: `{ "version": "published" }` loads the specific version named "published".
    *   **`global_schema_options` (`SchemaOptions` object | `null`): Optional.** Controls schema loading.
        *   Example: `{ "load_schema": true }` attempts to load the schema associated with each versioned document. The schemas appear in the node's `load_metadata` output field.

### Example Node Configuration:

```json
{
  "nodes": {
    "fetch_recent_feedback": {
      "node_id": "fetch_recent_feedback",
      "node_name": "load_multiple_customer_data", // ** Must be "load_multiple_customer_data" **
      "node_config": { // This is the LoadMultipleCustomerDataConfig schema

        // --- Listing Criteria ---
        "namespace_filter": "user_feedback", // Only look in this namespace
        "include_shared": true, // Include feedback shared by others
        "include_user_specific": true, // Include feedback submitted by this user
        "include_system_entities": false, // Exclude system docs

        // --- Pagination/Sorting ---
        "limit": 10, // Get maximum 10 documents
        "sort_by": "created_at", // Sort by when they were created
        "sort_order": "desc", // Get the newest first

        // --- Loading Options ---
        "global_version_config": null, // Load the active version if documents are versioned

        // --- Output ---
        "output_field_name": "recent_feedback_list" // Name for the output list
      }
      // dynamic_input_schema / dynamic_output_schema usually not needed
    }
    // ... other nodes
  }
  // ... other graph properties
}
```

## Input (`DynamicSchema`)

The `LoadMultipleCustomerDataNode` can now use input data in two ways:

1. **Dynamic Configuration:** If `config_input_path` is provided, the node will look for configuration values at that path in the input data.

2. **Namespace Pattern Resolution:** If `namespace_pattern` and `namespace_pattern_input_path` are provided, the node will use values from the input data to dynamically resolve the namespace filter.

## Output (`LoadMultipleCustomerDataOutput` - Dynamic)

The node produces data dynamically based on its configuration. The primary output is a list of documents.

-   **`[output_field_name]` (List[Dict | Any]):** A field named according to the `output_field_name` in the config. This field contains a **list** where each item is the content of a successfully loaded document. If no documents match the criteria or loading fails for all of them, this will be an empty list (`[]`).
-   **`load_metadata` (Dict[str, Any]):** A dictionary containing metadata about the loading operation. Example:
    ```json
    {
      "documents_listed": 15, // Total docs found matching criteria (before limit)
      "documents_loaded": 10, // Docs actually loaded after applying limit/skip
      "load_errors": [], // List of errors encountered loading specific docs
      "schemas_loaded_count": 0, // Number of schemas loaded (if requested)
      "config_skip": 0,
      "config_limit": 10,
      "used_dynamic_config": true, // If dynamic configuration was applied
      "resolved_namespace": "customer_123_data" // The actual namespace filter used (if dynamically resolved)
    }
    ```

## Advanced Features

### Dynamic Configuration

Instead of hardcoding all configuration in the graph schema, you can provide a `config_input_path` to load configuration from the input data at runtime:

```json
{
  "node_config": {
    "config_input_path": "dynamic_config",
    "output_field_name": "default_output_field" // Fallback if not in dynamic config
  }
}
```

Then, in your input data:
```json
{
  "dynamic_config": {
    "namespace_filter": "user_feedback",
    "limit": 20,
    "output_field_name": "feedback_items",
    "sort_by": "updated_at"
  }
}
```

The values from the input data will override the static configuration. This allows workflows to adapt based on upstream node outputs.

### Namespace Pattern

You can dynamically construct namespace filters using template patterns:

```json
{
  "node_config": {
    "namespace_pattern": "customer_{item}_data",
    "namespace_pattern_input_path": "tenant_info.id",
    "output_field_name": "customer_data"
  }
}
```

With input data:
```json
{
  "tenant_info": {
    "id": "456",
    "name": "Acme Corp"
  }
}
```

This would resolve to the namespace `"customer_456_data"`.

You can also use complex patterns with nested object access:

```json
{
  "node_config": {
    "namespace_pattern": "customer_{item[customer_id]}_project_{item[project_id]}",
    "namespace_pattern_input_path": "project_context",
    "output_field_name": "project_data"
  }
}
```

With input data:
```json
{
  "project_context": {
    "customer_id": "123",
    "project_id": "456"
  }
}
```

This would resolve to the namespace `"customer_123_project_456"`.

## Example `GraphSchema` Snippet with Advanced Features

```json
{
  "nodes": {
    "get_customer_data": {
      "node_id": "get_customer_data",
      "node_name": "load_multiple_customer_data",
      "node_config": {
        "namespace_pattern": "customer_{item}_records",
        "namespace_pattern_input_path": "workflow_params.customer_id",
        "include_shared": true,
        "limit": 20,
        "sort_by": "created_at",
        "sort_order": "desc",
        "output_field_name": "customer_records"
      }
    },
    "analyze_records": {
      "node_id": "analyze_records",
      "node_name": "map_list_router",
      "node_config": {
        "input_list_path": "customer_records",
        "item_output_field": "analysis_result"
      }
    }
  },
  "edges": [
    {
      "src_node_id": "get_customer_data",
      "dst_node_id": "analyze_records",
      "mappings": [
        { "src_field": "customer_records", "dst_field": "customer_records" }
      ]
    }
  ],
  "input_node_id": "...",
  "output_node_id": "..."
}
```

## Notes for Non-Coders

-   Use this node when you need to retrieve a **collection** or **list** of documents that match certain criteria, rather than just one specific document. Think "get all feedback submitted this week" or "get the 5 latest product descriptions".
-   **Configure what to find:**
    *   `namespace_filter`: Like choosing a specific folder to look in. Leave blank to search everywhere allowed.
    *   `namespace_pattern`: Alternatively, build a dynamic folder path using values from your workflow data.
    *   `include_shared`/`include_user_specific`/`include_system_entities`: Choose which types of documents to include (shared by anyone, just yours, special system ones). You usually want `include_shared` and `include_user_specific` set to `true`.
    *   `on_behalf_of_user_id`: (Advanced/Admin only) Search for documents belonging to *another* specific user.
-   **Control the results:**
    *   `limit`: How many documents do you want at most? (e.g., `10`)
    *   `skip`: How many to skip from the start? (e.g., `0` for the first page, `10` for the second page if limit is 10).
    *   `sort_by` / `sort_order`: How should the list be ordered before picking the ones to load? (e.g., newest first).
-   **Define the Output:**
    *   `output_field_name`: Give a name to the list of documents that will be created (e.g., `"customer_list"`).
-   **Optional Loading Details:**
    *   `global_version_config`: If the documents have versions, tell it which one to load (usually leave as default/`null` to get the latest active one).
    *   `global_schema_options`: Can tell it to also fetch the "structure" (schema) of the data, if needed.
-   **New Dynamic Features:**
    *   `config_input_path`: Load configuration values from workflow data (instead of hard-coding).
    *   `namespace_pattern` + `namespace_pattern_input_path`: Build dynamic namespace filters using values from your workflow data.
-   The result of this node is a **list** placed in the output field you named. Subsequent nodes can then process this list (e.g., using `MapListRouter` to handle each item individually). 