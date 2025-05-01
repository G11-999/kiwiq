# Usage Guide: LoadCustomerDataNode

This guide explains how to configure and use the `LoadCustomerDataNode` to retrieve documents (like customer profiles, product info, etc.) stored in the system's data store.

## Purpose

The `LoadCustomerDataNode` allows your workflow to fetch specific data records based on configurable criteria. You can:

-   Load one or multiple documents in a single step.
-   Specify documents using fixed names or dynamically based on data flowing through the workflow.
-   Retrieve specific versions of documents (if they are versioned).
-   Access data specific to the user, shared across the organization, or system-level data (with appropriate permissions).
-   Optionally load the schema associated with a versioned document.

The loaded data is then added to the workflow's data stream for use by subsequent nodes.

## Configuration (`NodeConfig`)

You configure the `LoadCustomerDataNode` within the `node_config` field of its entry in the `GraphSchema`. The configuration follows the `LoadCustomerDataConfig` schema.

**Configuration Source:**

You must define the load operations using *one* of the following methods:

1.  **`load_paths`**: A static list of `LoadPathConfig` objects directly defined in the workflow schema.
2.  **`load_configs_input_path`**: A dot-notation path pointing to data within the node's input which resolves to either a single `LoadPathConfig` object or a list of `LoadPathConfig` objects.

You **cannot** provide both `load_paths` and `load_configs_input_path`.

### Full Config and all fields with brief explanations
```python

# Example document identifiers to process
# This list demonstrates various ways to specify documents for loading
[
    # Example: Using FilenameConfig options with LoadPathConfig
    {
        "filename_config": {
            # --- NAMESPACE OPTIONS (choose ONE of these) ---
            # Static namespace (simplest approach)
            "static_namespace": "content_strategy_docs",
            
            # OR Dynamic field path for namespace
            "input_namespace_field": "metadata.doc_namespace",
            
            # OR Pattern using current item context
            "namespace_pattern": "{item[type]}_{item[year]}",
            
            # OR Pattern with specific input field
            "input_namespace_field_pattern": "ns_{item[category]}",
            
            # --- DOCNAME OPTIONS (choose ONE of these) ---
            # Static docname (simplest approach)
            "static_docname": "strategy_2023_q4",
            
            # OR Dynamic field path for docname
            "input_docname_field": "metadata.doc_id",
            
            # OR Pattern using current item context
            "docname_pattern": "{item[type]}_report_{item[quarter]}",
            
            # OR Pattern with specific input field
            "input_docname_field_pattern": "doc_{item[topic]}"
        },
        
        # Required field: where to place the loaded document in output
        "output_field_name": "loaded_document",
        
        # --- OPTIONAL LoadPathConfig FIELDS ---
        "version_config": {
            "version": "v2.1"                  # Specific version to load
        },
        "schema_options": {
            # Whether to load document schema
            "load_schema": True,
            
            # --- SCHEMA SOURCE OPTIONS (choose ONE if needed) ---
            # Option 1: Use a schema template
            "schema_template_name": "content_strategy_template",
            "schema_template_version": "1.0",
            
            # OR Option 2: Provide schema definition directly
            "schema_definition": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["title", "content"]
            }
        },
        "is_shared": True,                     # Access shared data
        "is_system_entity": False,             # Not system data
        "on_behalf_of_user_id": "user_123"     # Act on behalf of specific user
    }
]

# Note: In actual implementation, you would choose ONE namespace strategy and ONE docname strategy,
# not mix all options as shown in this comprehensive example.
# Similarly, for schema_options, you would choose either schema_template_name or schema_definition, not both.

```

### Additional Config egs
```json
{
  "nodes": {
    "fetch_customer_profile": {
      "node_id": "fetch_customer_profile", // Unique ID for this node instance
      "node_name": "load_customer_data", // ** Must be "load_customer_data" **
      "node_config": { // This is the LoadCustomerDataConfig schema
        // --- Global Defaults (Optional) ---
        // These apply unless overridden in a specific load_path
        "global_is_shared": false, // Default: load user-specific data
        "global_is_system_entity": false, // Default: not system data
        "global_version_config": {
          "version": "default" // Default: load the 'default' (usually latest active) version
        },
        "global_schema_options": {
          "load_schema": false // Default: don't load schema with the document
          // "schema_template_name": null,
          // "schema_template_version": null,
          // "schema_definition": null
        },
        "global_on_behalf_of_user_id": null, // Default: don't act on behalf of another user when loading

        // --- Option 1: Define Load Paths Statically ---
        "load_paths": [ // List of load instructions (Use this OR load_configs_input_path)
          // --- Example 1: Load a specific document with static path ---
          {
            "filename_config": {
              "static_namespace": "user_profiles",
              "static_docname": "profile_12345"
            },
            "output_field_name": "customer_profile_doc" // Data will be placed here in output
            // Inherits global defaults for shared/system/version/schema
          },
          // --- Example 2: Load based on input data field ---
          {
            "filename_config": {
              // Get namespace/docname from fields in the node's input data
              "input_namespace_field": "input_data.source_ns", // e.g., input has { "source_ns": "product_catalogs" }
              "input_docname_field": "input_data.product_id" // e.g., input has { "product_id": "prod_abc" }
            },
            "output_field_name": "product_details",
            "version_config": { // Override global version default
              "version": "published" // Load the 'published' version
            }
          },
          // --- Example 3: Load a shared configuration document ---
          {
            "filename_config": {
              "static_namespace": "workflow_configs",
              "static_docname": "global_settings"
            },
            "output_field_name": "workflow_settings",
            "is_shared": true // Override global: load shared data
          },
          // --- Example 4: Load a specific version and its schema ---
          {
            "filename_config": {
              "static_namespace": "analysis_results",
              "static_docname": "report_q3_final"
            },
            "output_field_name": "final_report",
            "version_config": { "version": "v2.1" },
            "schema_options": { "load_schema": true } // Load the schema too
          },
          // --- Example 5: Load system data (requires superuser context) ---
          {
            "filename_config": {
              "static_namespace": "system_internal",
              "static_docname": "node_registry"
            },
            "output_field_name": "registry_data",
            "is_system_entity": true, // Override global: load system data
            "is_shared": true // System entities often shared
          },
          // --- Example 6: Load using patterns based on input metadata --- 
          {
            "filename_config": {
              "input_namespace_field": "load_params", // Path to the metadata object in input
              "input_namespace_field_pattern": "config/{item[type]}", // Pattern using metadata
              "input_docname_field": "load_params.environment", // Path to specific field for docname data
              "input_docname_field_pattern": "settings_{item}" // Pattern using the environment value
              // e.g. if load_params is {"type": "global", "environment": "staging"}
              // the path loaded would be: config/global/settings_staging
            },
            "output_field_name": "dynamic_config",
            "is_shared": true // Assuming config is shared
          }
        ],
        // --- Option 2: Define Load Paths Dynamically from Input ---
        // "load_configs_input_path": "path.to.dynamic.load.configs" // Use this OR load_paths
        // Example Input Data for dynamic path:
        // { "path": { "to": { "dynamic": { "load": { "configs": [ { load_path_1_config }, { load_path_2_config } ] } } } } }
      }
      // dynamic_input_schema / dynamic_output_schema usually not needed
    }
    // ... other nodes
  }
  // ... other graph properties
}
```

### Key Configuration Sections:

1.  **Global Defaults (`global_is_shared`, `global_is_system_entity`, `global_version_config`, `global_schema_options`)**: (Optional) Set default behaviors for all load paths. These can be individually overridden within each `load_paths` item.
    *   `global_is_shared`: `false` (default) loads data belonging to the current user/org; `true` loads data shared within the organization.
    *   `global_is_system_entity`: `false` (default); `true` attempts to load system-level data (requires the workflow run context to have superuser privileges).
    *   `global_version_config`: Specifies the default `version` name (default: `"default"`) to load for versioned documents.
    *   `global_schema_options`: Controls default schema behavior.
        *   `load_schema`: `false` (default); `true` attempts to load the schema associated with the versioned document being loaded. The loaded schema appears in the node's `output_metadata` field.
        *   Other fields (`schema_template_name`, `schema_definition`) are less common for loading but could potentially be used for validation in the future.
2.  **`load_paths`** (List): **Required (unless `load_configs_input_path` is used)**. A list where each item defines a document to be loaded. Provide this OR `load_configs_input_path`.
3.  **`load_configs_input_path`** (String): **Required (unless `load_paths` is used)**. A dot-notation path (e.g., `"dynamic_load_jobs"`) within the node's input data. The data at this path must be either a single JSON object matching the `LoadPathConfig` structure, or a list of such JSON objects. If this path is provided, the static `load_paths` list is ignored. This allows generating the entire load plan dynamically based on previous workflow steps.
4.  **Inside each `load_paths` item** (whether defined statically or loaded dynamically):
    *   **`filename_config`**: **Required**. Defines *how* to find the document name and its namespace (like a folder). Exactly one method must be chosen for namespace and one for docname:
        *   `static_namespace` / `static_docname`: Provide fixed string values for the namespace and document name.
        *   `input_namespace_field` / `input_docname_field`: Provide a dot-notation path (e.g., `"input.customer_id"`, `"details.report_name"`) to a field *within the node's input data*. The value of that field will be used as the namespace or docname. **Note:** This path is also used to fetch data for the `input_*_field_pattern` options below.
        *   `namespace_pattern` / `docname_pattern`: (Less common for loading, more for storing lists) Provide an f-string like template (e.g., `"user_{item[user_id]}"`). This is primarily useful when the node is processing a list and needs context from the specific `item` being processed. Uses context `{'item': current_item_data, 'index': item_index}`.
        *   `input_namespace_field_pattern` / `input_docname_field_pattern`: **New!** An f-string like template that uses data found at the path specified by `input_namespace_field` or `input_docname_field` respectively. The context provided to the format string is `{'item': retrieved_data}`. This allows determining the load path based on metadata located elsewhere in the input. **Note:** If you use `input_..._field_pattern`, you *must* also provide the corresponding `input_..._field` to specify where to get the data for the pattern.
    *   **`output_field_name`**: **Required**. The name of the field where the loaded document's content will be placed in the node's output data. **Important:** This name cannot start with an underscore (`_`).
    *   **`is_shared`** (Optional bool): Overrides `global_is_shared` for this specific load path.
    *   **`is_system_entity`** (Optional bool): Overrides `global_is_system_entity` for this specific load path.
    *   **`on_behalf_of_user_id`** (Optional str): Overrides global default. **Requires the workflow run context to have superuser privileges.** If provided and `is_shared` is `false`, the node attempts to load the document stored under the path associated with this user ID. This parameter is ignored if `is_shared` is `true` or `is_system_entity` is `true`.
    *   **`version_config`** (Optional `VersionConfig` object): Overrides `global_version_config`. Allows specifying a specific `version` name to load.
    *   **`schema_options`** (Optional `SchemaOptions` object): Overrides `global_schema_options`. Allows enabling `load_schema: true` for this specific path.

## Input (`DynamicSchema`)

The `LoadCustomerDataNode` primarily uses its configuration to determine what to load. However, it requires input data if any `load_paths` configuration uses `input_namespace_field` or `input_docname_field` to dynamically determine the document path.

-   Input data containing the necessary fields (e.g., `{ "product_id": "prod_xyz" }`) should be mapped from previous nodes or the central state.

## Output (`LoadCustomerDataOutput` - Dynamic)

The node produces data dynamically based on the `load_paths` configuration. The output object will have fields corresponding to each `output_field_name` specified in the configuration.

-   **`[output_field_name_1]`** (Dict | List | Any | `null`): A field named according to the `output_field_name` in the config, containing the loaded document data. If the document was not found or access was denied, this field might be absent or `null` depending on the output schema definition (usually defaults to `None` if the field is Optional in the dynamic model construction).
    **Note on Overlapping Fields:** If multiple `load_paths` items specify the *same* `output_field_name`, the node will collect all successfully loaded documents into a **List** under that single field name. Documents that fail to load (due to not existing, permissions, etc.) will be omitted from the list.
-   **`[output_field_name_2]`** (Dict | List | Any | `null`): Another field for another loaded document.
-   ... and so on for each item in `load_paths`.
-   **`output_metadata`** (Dict[str, Dict[str, Any]]): A dictionary containing metadata about the loaded documents, primarily used for schemas. It's keyed by the `output_field_name`. Example:
    ```json
    {
      "final_report": { "schema": { "type": "object", ... } } 
    }
    ```
    If `load_schema` was `false` or no schema was found/applicable, the entry for that field might be missing or empty.

## Example `GraphSchema` Snippet

```json
{
  "nodes": {
    "get_input_ids": { /* ... node outputting customer_id and order_id ... */ },
    "load_data": {
      "node_id": "load_data",
      "node_name": "load_customer_data",
      "node_config": {
        "load_paths": [
          {
            "filename_config": {
              "static_namespace": "customers",
              "input_docname_field": "customer_id" // Get docname from input
            },
            "output_field_name": "customer_doc"
          },
          {
            "filename_config": {
              "static_namespace": "orders",
              "input_docname_field": "order_id" // Get docname from input
            },
            "output_field_name": "order_doc",
            "version_config": { "version": "latest_approved" }
          }
        ]
      }
    },
    "process_loaded_data": { /* ... node that uses customer_doc and order_doc ... */ }
  },
  "edges": [
    {
      "src_node_id": "get_input_ids",
      "dst_node_id": "load_data",
      "mappings": [
        // Map IDs needed to resolve dynamic paths
        { "src_field": "customer_id", "dst_field": "customer_id" },
        { "src_field": "order_id", "dst_field": "order_id" }
      ]
    },
    {
      "src_node_id": "load_data",
      "dst_node_id": "process_loaded_data",
      "mappings": [
        // Map the dynamically created output fields
        { "src_field": "customer_doc", "dst_field": "customer_input" },
        { "src_field": "order_doc", "dst_field": "order_input" },
        { "src_field": "output_metadata", "dst_field": "load_metadata" }
      ]
    }
  ],
  "input_node_id": "...",
  "output_node_id": "..."
}
```

## Notes for Non-Coders

-   Use this node to fetch existing data records needed by your workflow.
-   You can either define the load instructions (`load_paths`) directly when building the workflow, OR you can provide a path (`load_configs_input_path`) to where those instructions can be found in the data coming into this node. Use one method or the other.
-   `load_paths` (or the data found at `load_configs_input_path`): Tell the node which documents to get.
-   Inside each load instruction:
    *   `filename_config`: How to find the document.
        *   `static_...`: Use if you know the exact name (e.g., load `"global_config"` from the `"settings"` namespace).
        *   `input_..._field`: Use if the name comes from earlier steps (e.g., load the customer profile using the `"customer_id"` provided as input).
        *   `input_..._field_pattern`: Use when the name needs to be constructed using a template based on data from the input (e.g., loading configuration based on `environment` and `region` fields in the input).
    *   `output_field_name`: What name should the loaded data have in the output? (e.g., `"loaded_customer_profile"`).
    *   `version_config`: If the data has versions, specify which one (e.g., `"published"`, `"v3"`, default is usually the latest).
    *   `is_shared`: Set to `true` to load data accessible by everyone in the org, not just the user.
    *   `is_system_entity`: Set to `true` only for specific system data (rarely needed, requires special permissions).
    *   `on_behalf_of_user_id`: (Superusers only) Provide a user ID here to load data belonging to *that specific user* (only applies when `is_shared` is false).
    *   `schema_options.load_schema`: Set to `true` if you need the structure (schema) of the data along with the data itself (useful for validation later).
-   The node outputs the data under the `output_field_name` you specified. Connect this field to the input of the next node that needs the data.
-   If a document isn't found, the corresponding output field might be empty or missing. 