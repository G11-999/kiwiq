# Usage Guide: StoreCustomerDataNode

This guide explains how to configure and use the `StoreCustomerDataNode` to save or update documents (like customer profiles, analysis results, generated content, etc.) in the system's data store.

## Purpose

The `StoreCustomerDataNode` allows your workflow to write data back to the central data store. You can:

-   Store one or multiple documents (or lists of documents) in a single step.
-   Specify the target location (namespace and document name) using fixed names or dynamically based on the data being stored or other workflow data.
-   Control how data is stored:
    -   **Initialize:** Create a new versioned document (fails if it already exists).
    -   **Update:** Modify an existing document (versioned or unversioned). Fails if the document or specific version doesn't exist.
    -   **Upsert:** Create a new unversioned document or update it if it exists.
    -   **Create Version:** Create a new named version branching off an existing version of a document.
    -   **Upsert Versioned:** Update a specific version of a versioned document if it exists, otherwise initialize that version (or the document itself if it's entirely new).
-   Associate a schema with the stored data for validation and structure.
-   Store data as user-specific, shared across the organization, or as system-level data (with appropriate permissions).

## Configuration (`NodeConfig`)

You configure the `StoreCustomerDataNode` within the `node_config` field of its entry in the `GraphSchema`. The configuration follows the `StoreCustomerDataConfig` schema.

**Configuration Source:**

You must define the store operations using *one* of the following methods:

1.  **`store_configs`**: A static list of `StoreConfig` objects directly defined in the workflow schema.
2.  **`store_configs_input_path`**: A dot-notation path pointing to data within the node's input which resolves to either a single `StoreConfig` object or a list of `StoreConfig` objects.

You **cannot** provide both `store_configs` and `store_configs_input_path`.

```json
{
  "nodes": {
    "save_results": {
      "node_id": "save_results", // Unique ID for this node instance
      "node_name": "store_customer_data", // ** Must be "store_customer_data" **
      "node_config": { // This is the StoreCustomerDataConfig schema
        // --- Global Defaults (Optional) ---
        // These apply unless overridden in a specific store_config
        "global_is_shared": false, // Default: store user-specific data
        "global_is_system_entity": false, // Default: not system data
        "global_versioning": {
          // Default behavior: Create or update an *unversioned* document
          "is_versioned": false,
          "operation": "upsert"
          // "version": "default" // Not typically needed for upsert
        },
        "global_schema_options": {
          // "schema_template_name": null, // Default: no schema association
          // "schema_definition": null
        },
        "global_on_behalf_of_user_id": null, // Default: don't act on behalf of another user
        "global_process_list_items_separately": true, // Default: process items in lists individually

        // --- Option 1: Define Store Configs Statically ---
        "store_configs": [ // List of store instructions (Use this OR store_configs_input_path)
          // --- Example 1: Upsert an unversioned document (using default versioning) ---
          {
            "input_field_path": "analysis_output", // Path to the data in the node's input
            "target_path": {
              "filename_config": {
                "static_namespace": "analysis_reports",
                "static_docname": "report_final"
              }
            },
            "process_list_items_separately": false // Store the entire list in one go
          },
          // --- Example 2: Initialize a new versioned document ---
          {
            "input_field_path": "generated_customer_profile",
            "target_path": {
              "filename_config": {
                "input_namespace_field": "customer_metadata.namespace", // Get ns from input
                "input_docname_field": "customer_metadata.customer_id" // Get docname from input
              }
            },
            "versioning": { // Override global versioning
              "is_versioned": true,
              "operation": "initialize", // Must not exist yet
              "version": "v1.0" // Name the initial version
            },
            "schema_options": { // Associate a schema
              "schema_template_name": "CustomerProfileSchema",
              "schema_template_version": "1.2"
            }
          },
          // --- Example 3: Update an existing versioned document ---
          {
            "input_field_path": "updated_settings_object",
            "target_path": {
              "filename_config": {
                "static_namespace": "user_settings",
                "input_docname_field": "user_id"
              }
            },
            "versioning": {
              "is_versioned": true,
              "operation": "update",
              "version": "default" // Update the 'default' (active) version
            }
          },
          // --- Example 4: Create a new version from an existing one ---
          {
            "input_field_path": "approved_content",
            "target_path": {
              "filename_config": {
                "static_namespace": "documents",
                "static_docname": "policy_manual"
              }
            },
            "versioning": {
              "is_versioned": true,
              "operation": "create_version",
              "version": "v3.0_approved", // Name of the new version
              "from_version": "v2.5_draft" // Branch from this existing version
            }
          },
          // --- Example 5: Store a list of items using a pattern ---
          {
            "input_field_path": "processed_orders", // Assumes this is a list of order dicts
            "target_path": {
              "filename_config": {
                "namespace_pattern": "orders_{item[region]}", // Namespace based on item's region field
                "docname_pattern": "order_{item[order_id]}" // Docname based on item's order_id
              }
            },
            "versioning": { "is_versioned": false, "operation": "upsert"} // Store each as unversioned
          },
          // --- Example 6: Upsert a specific version of a versioned document ---
          {
            "input_field_path": "latest_draft_content",
            "target_path": {
              "filename_config": {
                "static_namespace": "project_drafts",
                "input_docname_field": "project_id"
              }
            },
            "versioning": {
              "is_versioned": true,
              "operation": "upsert_versioned", // Try update, then initialize if needed
              "version": "latest_auto_save" // Target this specific version name
              // If "latest_auto_save" exists, it will be updated.
              // If it doesn't exist (but the doc does), it will be initialized.
              // If the doc doesn't exist, the doc will be initialized with this version.
            }
          },
          // --- Example 7: Store using patterns based on separate input metadata --- 
          {
            "input_field_path": "log_data_payload", // The actual data to store
            "target_path": {
              "filename_config": {
                "input_namespace_field": "run_metadata", // Path to the metadata object
                "input_namespace_field_pattern": "logs/{item[source_system]}/{item[year]}", // Pattern using metadata
                "input_docname_field": "run_metadata.run_id", // Path to specific field for docname data
                "input_docname_field_pattern": "run_{item}.log" // Pattern using the run_id value
                // e.g. if run_metadata is {"source_system": "A", "year": 2024, "run_id": "xyz"}
                // the path would be: logs/A/2024/run_xyz.log
              }
            },
            "versioning": { "is_versioned": false, "operation": "upsert" } 
          },
          // --- Example 8: Store a list as a single document ---
          {
             "input_field_path": "list_of_tags", // Path to a list of strings
             "target_path": {
               "filename_config": {
                 "static_namespace": "metadata",
                 "static_docname": "all_tags"
               }
             },
             "process_list_items_separately": false // Store the entire list in one go
          }
        ],
        // --- Option 2: Define Store Configs Dynamically from Input ---
        // "store_configs_input_path": "path.to.dynamic.configs.in.input" // Use this OR store_configs
        // Example Input Data for dynamic path:
        // { "path": { "to": { "dynamic": { "configs": { "in": { "input": [ { store_config_1 }, { store_config_2 } ] } } } } } }
      }
      // dynamic_input_schema / dynamic_output_schema usually not needed
    }
    // ... other nodes
  }
  // ... other graph properties
}
```

### Key Configuration Sections:

1.  **Global Defaults (`global_is_shared`, `global_is_system_entity`, `global_versioning`, `global_schema_options`, `global_on_behalf_of_user_id`, `global_process_list_items_separately`)**: (Optional) Set default behaviors for all store operations. These can be individually overridden within each `store_configs` item.
    *   `global_versioning`: Defines the default versioning strategy.
        *   `is_versioned`: `true` or `false`.
        *   `operation`: Default action (e.g., `"upsert"`, `"update"`). A common default is `is_versioned: false, operation: "upsert"`.
        *   `version`: Default version name (e.g., `"default"`).
    *   `global_process_list_items_separately` (Optional bool): Default is `null`. If set to `true` or `false`, this provides the default behavior for list processing when the local `process_list_items_separately` is `null`. If both global and local are `null`, the ultimate fallback is `false` (store list as a single document).
    *   See `LoadCustomerDataNode` guide for details on other global defaults.
2.  **`store_configs`** (List): **Required (unless `store_configs_input_path` is used)**. A list where each item defines a specific store operation. Provide this OR `store_configs_input_path`.
3.  **`store_configs_input_path`** (String): **Required (unless `store_configs` is used)**. A dot-notation path (e.g., `"dynamic_configs.store_jobs"`) within the node's input data. The data at this path must be either a single JSON object matching the `StoreConfig` structure, or a list of such JSON objects. If this path is provided, the static `store_configs` list is ignored. This allows generating the entire storage plan dynamically based on previous workflow steps.
4.  **Inside each `store_configs` item** (whether defined statically or loaded dynamically):
    *   **`input_field_path`**: **Required**. Dot-notation path (e.g., `"results.summary"`, `"customer_data"`, `"simple_string"`) to the data *within the node's input* that you want to store. This can point to a dictionary, a list (of dictionaries, primitives, etc.), or a primitive value (string, number, boolean, null).
    *   **`target_path`**: **Required**. Defines *where* to store the data.
        *   **`filename_config`**: **Required**. Defines the target namespace and docname. Exactly one method must be chosen for namespace and one for docname:
            *   `static_namespace` / `static_docname`: Fixed string values.
            *   `input_namespace_field` / `input_docname_field`: Dot-notation path to a field in the node's input data *or* within the item being stored (if `input_field_path` points to a list and `process_list_items_separately` is `true`). The system checks the item first, then the overall input data. **Note:** If `process_list_items_separately` is `false`, path resolution cannot depend on fields *within* the list items themselves using this method. This path is also used to fetch data for the `input_*_field_pattern` options below.
            *   `namespace_pattern` / `docname_pattern`: An f-string like template using `{item[...]}` and `{index}`. Used when `input_field_path` points to a list *and `process_list_items_separately` is `true`*. `{item[...]}` accesses fields within the current list item being stored (assumed to be a dict), and `{index}` provides its position in the list (0, 1, 2...). Example: `"order_{item[order_id]}_{index}"`. **Note:** This method will likely fail if items in the list are not dictionaries or if `process_list_items_separately` is `false`.
            *   `input_namespace_field_pattern` / `input_docname_field_pattern`: An f-string like template that uses data found at the path specified by `input_namespace_field` or `input_docname_field` respectively. The context provided to the format string is `{'item': retrieved_data}`. This allows generating paths based on metadata located elsewhere in the input. **Note:** If you use `input_..._field_pattern`, you *must* also provide the corresponding `input_..._field` to specify where to get the data for the pattern.
    *   **`process_list_items_separately`** (Optional bool): Default is `null`. Controls behavior if `input_field_path` points to a list:
        *   `true`: Each item in the list is processed individually. Path resolution can use `{item[...]}` if items are dictionaries.
        *   `false`: The entire list is stored as a single document. Path resolution cannot use `{item[...]}`.
        *   `null`: Behavior is determined by `global_process_list_items_separately`. If that is also `null`, the behavior defaults to `false` (store list as a single document).
    *   **`is_shared`** (Optional bool): Overrides global default.
    *   **`is_system_entity`** (Optional bool): Overrides global default (requires superuser context).
    *   **`on_behalf_of_user_id`** (Optional str): Overrides global default. **Requires the workflow run context to have superuser privileges.** If provided and `is_shared` is `false`, the data will be stored under the path associated with this user ID instead of the user running the workflow. This parameter is ignored if `is_shared` is `true` or `is_system_entity` is `true`.
    *   **`versioning`** (Optional `VersioningInfo` object): Overrides global default. Defines versioning behavior for *this specific* store operation:
        *   `is_versioned` (bool): Is the target location versioned?
        *   `operation` (StoreOperation Enum): **Required**. The action to perform:
            *   `"initialize"`: (Versioned only) Create the very first version. Fails if the document already exists. Requires `version` field.
            *   `"update"`: (Versioned or Unversioned) Modify an existing document/version. Fails if it doesn't exist. Uses `version` field for versioned docs (defaults to `default`/active version if `version` is null).
            *   `"upsert"`: (Unversioned only) Create if it doesn't exist, update if it does.
            *   `"create_version"`: (Versioned only) Create a new version based on another. Requires `version` (the name for the new version) and optionally `from_version` (defaults to the active version).
            *   `"upsert_versioned"`: (Versioned only) **Attempts to update first, then initializes if update fails.** Specifically:
                1.  **Try Update:** Attempts to update the specified `version` (or the active version if `version` is null). If successful, the operation is complete.
                2.  **Try Initialize (Fallback):** If the update fails (e.g., the document or the specific version doesn't exist), it attempts to initialize the document with the specified `version` (or `"default"` if `version` was null).
                3.  **Fails:** If both the update and the subsequent initialize attempt fail, the operation fails overall. This is useful for ensuring a specific named version exists and has the latest data, creating it if necessary. Requires `is_versioned: true`.
        *   `version` (Optional str): Name of the version to initialize, update, create, or upsert. For `update` and `upsert_versioned`, `null` means the active version. For `initialize`, `null` means the `"default"` version.
        *   `from_version` (Optional str): Used only with `create_version` to specify the source version.
        *   `is_complete` (Optional bool): Used with `update` or `upsert_versioned` on versioned docs. Marks if this update represents a 'complete' state of the document (relevant for version history tracking).
    *   **`schema_options`** (Optional `SchemaOptions` object): Overrides global default. Associate a schema with the stored data:
        *   `schema_template_name`: Name of a pre-registered schema template.
        *   `schema_template_version`: Optional version of the template.
        *   `schema_definition`: Provide the JSON schema directly in the config.
        *   **Note:** The service will attempt to validate the data against the schema before storing if a schema is provided. `load_schema` field is ignored during store.

## Input (`DynamicSchema`)

The `StoreCustomerDataNode` requires input data containing the document(s) or value(s) to be stored, located at the path(s) specified in `input_field_path`. The data can be a dictionary, a list, or a primitive type (string, number, boolean, null).

-   It might also require additional fields in the input if `input_namespace_field` or `input_docname_field` are used in the `filename_config`.
-   Input data should be mapped from previous nodes or the central state.

## Output (`StoreCustomerDataOutput`)

The node primarily performs a write operation and then passes through the original input data.

-   **`passthrough_data`** (Dict[str, Any]): A copy of the complete input data that was received by the node.
-   **`paths_processed`** (List[List[str]]): A list indicating which documents were successfully processed. Each inner list contains `[namespace, docname, operation_string]`. Example: `[["analysis_reports", "report_final", "upsert_unversioned"], ["user_settings", "user_123", "update_versioned_default"], ["project_drafts", "proj_abc", "upsert_versioned_updated_latest_auto_save"]]`. The operation string provides detail on what action occurred (e.g., `upsert_versioned_initialized_...`, `upsert_versioned_updated_...`).

## Example `GraphSchema` Snippet

```json
{
  "nodes": {
    "generate_report": { /* ... node outputting report_data ... */ },
    "store_report": {
      "node_id": "store_report",
      "node_name": "store_customer_data",
      "node_config": {
        "global_versioning": {
          "is_versioned": true, // Default to versioned storage
          "operation": "upsert_versioned" // Default to upserting versioned docs
        },
        "store_configs": [
          {
            "input_field_path": "report_data", // Get data from this input field
            "target_path": {
              "filename_config": {
                "static_namespace": "generated_reports",
                "input_docname_field": "report_metadata.report_id" // Docname from input
              }
            },
            "versioning": {
              "version": "latest_analysis" // Use the global operation (upsert_versioned) for this version
            }
          }
        ]
      }
    },
    "notify_user": { /* ... next step ... */ }
  },
  "edges": [
    {
      "src_node_id": "generate_report",
      "dst_node_id": "store_report",
      "mappings": [
        // Map the report data and the ID needed for the path
        { "src_field": "report_data", "dst_field": "report_data" },
        { "src_field": "report_metadata", "dst_field": "report_metadata" }
      ]
    },
    {
      "src_node_id": "store_report",
      "dst_node_id": "notify_user",
      "mappings": [
        // Pass through the original data if needed
        { "src_field": "passthrough_data", "dst_field": "original_input" }
        // Or map specific fields from the passthrough data
        // { "src_field": "passthrough_data::report_metadata::report_id", "dst_field": "processed_report_id" }
      ]
    }
  ],
  "input_node_id": "...",
  "output_node_id": "..."
}
```

## Notes for Non-Coders

-   Use this node to save data generated or modified by your workflow.
-   You can either define the save instructions (`store_configs`) directly when building the workflow, OR you can provide a path (`store_configs_input_path`) to where those instructions can be found in the data coming into this node. Use one method or the other.
-   `store_configs` (or the data found at `store_configs_input_path`): Tell the node what data to save and where.
-   Inside each save instruction:
    *   `input_field_path`: Which piece of data from the previous step should be saved? (e.g., `"customer_summary"`, `"list_of_names"`, `"final_score"`).
    *   `process_list_items_separately` (usually default/`null` which means `false`): If the data is a list, should each item be saved individually (`true`) or should the whole list be saved as one file (`false`)? If you don't set it, it usually defaults to saving the **whole list as one file (`false`)**.
    *   `target_path.filename_config`: Where should it be saved?
        -   `static_...`: Use if you know the exact name (e.g., save as `"latest_results"` in the `"daily_reports"` namespace).
        -   `input_..._field`: Use if the name comes from the data itself (e.g., save the order using the `"order_id"` field from the order data). **Works best if the item being saved is an object/dictionary.**
        -   `..._pattern`: Use when saving a list of items *individually* (`process_list_items_separately: true`), creating names based on each item's properties (e.g., save each product using its `"product_id"`). **Requires items in the list to be objects/dictionaries.**
        -   `input_..._field_pattern`: Use when the name needs to be constructed using a template, but the data for the template comes from *another* part of the input, not the item being saved (e.g., creating a log filename using `run_id` and `system_name` provided elsewhere in the input).
    *   `versioning`: How to handle saving?
        -   `is_versioned: false, operation: "upsert"`: Simple save - create if new, overwrite if exists (good for status dashboards, latest configs, simple values).
        -   `is_versioned: true, operation: "initialize"`: Save the *first version* of something important (e.g., initial customer profile).
        -   `is_versioned: true, operation: "update"`: Update the *current* version of something (e.g., update user preferences). Fails if the document/version doesn't exist.
        -   `is_versioned: true, operation: "create_version"`: Save as a *new version* (e.g., save `"v2_approved"` after edits to `"v1_draft"`).
        -   `is_versioned: true, operation: "upsert_versioned"`: **Update or Create a specific version**. It first tries to update the version you specify. If that version (or the whole document) doesn't exist, it creates it. Useful for things like auto-saving drafts where you want to overwrite the latest auto-save but create it if it's the first time.
    -   `schema_options`: Optionally link the saved data to a predefined structure (schema) for consistency.
    -   `is_shared`: Set to `true` to save data accessible by everyone in the org.
    -   `on_behalf_of_user_id`: (Superusers only) Provide a user ID here to save the data as if you *were* that user (only applies when `is_shared` is false). The data gets saved under their specific path.
-   The node mostly passes through the data it received. You can use the `paths_processed` output to see a list of what was successfully saved. 
