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
-   Enrich objects with additional fields from elsewhere in the workflow input.
-   Automatically generate and add UUIDs to objects being stored.
-   Use the same UUID in both the document filename and its content.


## Full Config and all fields with brief explanations

```python
{
    # --- CONFIG SOURCE OPTIONS (choose ONE of these) ---
    
    # Option 1: Static list of store configurations
    "store_configs": [
        {
            # Required: Path to the data within the node's input that you want to store
            # This can point to a dictionary, list, or primitive value
            "input_field_path": "analysis_output", 
            
            # Required: Defines where to store the data
            "target_path": {
                # Required: Configuration for determining namespace and docname
                "filename_config": {
                    # --- NAMESPACE OPTIONS (choose ONE of these) ---
                    
                    # Option 1: Fixed namespace string
                    "static_namespace": "analysis_reports",
                    
                    # Option 2: Path to a field in input data containing the namespace
                    "input_namespace_field": "metadata.namespace",
                    
                    # Option 3: Template for generating namespace from data at input_namespace_field
                    # Uses {'item': retrieved_data} context
                    "input_namespace_field_pattern": "ns_{item[category]}",
                    
                    # Option 4: Template for namespace using current item (when processing lists)
                    # Uses {'item': current_item, 'index': item_index} context
                    "namespace_pattern": "orders_{item[region]}",
                    
                    # --- DOCNAME OPTIONS (choose ONE of these) ---
                    
                    # Option 1: Fixed docname string
                    "static_docname": "report_final",
                    
                    # Option 2: Path to a field in input data containing the docname
                    "input_docname_field": "metadata.doc_id",
                    
                    # Option 3: Template for generating docname from data at input_docname_field
                    # Uses {'item': retrieved_data} context
                    # Special placeholders: {_uuid_} (UUID), {_timestamp_} (current UTC time)
                    "input_docname_field_pattern": "doc_{item[topic]}_{_timestamp_}",
                    
                    # Option 4: Template for docname using current item (when processing lists)
                    # Uses {'item': current_item, 'index': item_index} context
                    # Special placeholders: {_uuid_} (UUID), {_timestamp_} (current UTC time)
                    "docname_pattern": "order_{item[order_id]}_{_uuid_}"
                }
            },
            
            # Optional: Controls behavior if input_field_path points to a list
            # If true, each item processed separately; if false, entire list stored as one document
            "process_list_items_separately": True,
            
            # Optional: Whether to store as shared data (vs. user-specific)
            # Overrides global_is_shared
            "is_shared": False,
            
            # Optional: Whether to store as system data (requires superuser)
            # Overrides global_is_system_entity
            "is_system_entity": False,
            
            # Optional: User ID to act on behalf of (requires superuser privileges)
            # Overrides global_on_behalf_of_user_id
            "on_behalf_of_user_id": "d5f06b6a-e564-4f56-9fe0-b9f32bee8f89",
            
            # Optional: Versioning behavior for this specific store operation
            # Overrides global_versioning
            "versioning": {
                # Whether the target document is versioned
                "is_versioned": True,
                
                # Required: Operation to perform
                # Options: "initialize", "update", "upsert", "create_version", "upsert_versioned"
                "operation": "initialize",
                
                # Optional: Version name to use
                # For initialize: Name for initial version (defaults to "default")
                # For update: Version to update (null means active version)
                # For create_version: Name for the new version
                # For upsert_versioned: Version to update/create
                "version": "v1.0",
                
                # Optional: For create_version, specify source version
                # Defaults to active version if not specified
                "from_version": "draft",
                
                # Optional: For update/initialize/upsert_versioned, mark if document is complete
                # Relevant for version history tracking
                "is_complete": True
            },
            
            # Optional: Schema handling options
            # Overrides global_schema_options
            "schema_options": {
                # Whether to load schema (ignored during store)
                "load_schema": True,
                
                # Name of pre-registered schema template
                "schema_template_name": "AnalysisReportSchema",
                
                # Optional: Version of the template
                "schema_template_version": "1.2",
                
                # Alternative: Direct JSON schema definition
                # Cannot use both template and definition
                "schema_definition": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["title", "content"]
                }
            },
            
            # Optional: Whether to generate and add UUID to stored objects
            # For dicts: Adds "uuid" field directly
            # For non-dicts: Wraps as {"uuid": "...", "data": original_value}
            # Overrides global_generate_uuid
            "generate_uuid": True,
            
            # Optional: List of extra fields to add to objects being stored
            # Only applied to dictionary objects
            # Overrides global_extra_fields
            "extra_fields": [
                {
                    # Required: Path to value in input data
                    "src_path": "metadata.workflow_id",
                    
                    # Optional: Path where value should be placed in stored object
                    # If not provided, defaults to last segment of src_path
                    "dst_path": "source.workflow_id"
                },
                {
                    "src_path": "metadata.timestamp",
                    # dst_path defaults to "timestamp" in this case
                }
            ],
            
            # Optional: Fields that should be preserved during document creation
            # but removed during updates unless they exist in original
            # UUID is automatically added when generate_uuid=True
            # Overrides global_create_only_fields
            "create_only_fields": ["created_at", "created_by"],
            
            # Optional: Controls whether create-only fields should be preserved
            # during updates if they don't exist in original document
            # Overrides global_keep_create_fields_if_missing
            "keep_create_fields_if_missing": True
        }
    ],
    
    # Option 2: Path to find store configurations in input data
    # If specified, store_configs is ignored
    "store_configs_input_path": "dynamic_configs.store_jobs",
    
    # --- GLOBAL DEFAULTS (applied if not overridden in individual configs) ---
    
    # Default for storing as shared data (across organization)
    # False means user-specific storage
    "global_is_shared": False,
    
    # Default for storing as system-level data
    # Requires superuser context
    "global_is_system_entity": False,
    
    # Default versioning behavior
    "global_versioning": {
        "is_versioned": False,
        "operation": "upsert",
        "version": "default"
    },
    
    # Default schema options
    "global_schema_options": {
        "load_schema": False,
        "schema_template_name": None,
        "schema_template_version": None,
        "schema_definition": None
    },
    
    # Default user ID to act on behalf of (requires superuser)
    "global_on_behalf_of_user_id": None,
    
    # Default behavior for processing lists
    # True: Process each list item individually
    # False: Store entire list as one document
    "global_process_list_items_separately": False,
    
    # Default behavior for adding UUIDs to documents
    "global_generate_uuid": False,
    
    # Default extra fields to add to all stored documents
    "global_extra_fields": [
        {
            "src_path": "metadata.workflow_run_id",
            "dst_path": "source.workflow_run_id"
        }
    ],
    
    # Default create-only fields
    "global_create_only_fields": ["created_at"],
    
    # Default behavior for keeping create-only fields if missing in original
    "global_keep_create_fields_if_missing": True
}
```


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
        "global_generate_uuid": false, // Default: don't generate UUID for documents
        "global_extra_fields": [ // Default: no extra fields added to documents
          // Example global extra fields (optional)
          // { "src_path": "metadata.workflow_id", "dst_path": "source.workflow_id" }
        ],
        "global_create_only_fields": [], // Default: no create-only fields
        "global_keep_create_fields_if_missing": true, // Default: preserve create-only fields if missing

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
            "process_list_items_separately": false, // Store the entire list in one go
            "generate_uuid": false, // Don't add UUID to this document
            "extra_fields": [ // No extra fields for this document
              // ...
            ]
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
            "versioning": { "is_versioned": false, "operation": "upsert"}, // Store each as unversioned
            "extra_fields": [
              {
                "src_path": "batch_metadata.source", // Add field from global input
                "dst_path": "source" // Default would be just the last part of src_path
              },
              {
                "src_path": "batch_metadata.timestamp", // Add timestamp from global input
                "dst_path": "metadata.created_at" // Creating nested structure
              }
            ]
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
          },
          // --- Example 9: Store with UUID generation ---
          {
            "input_field_path": "user_activity",
            "target_path": {
              "filename_config": {
                "static_namespace": "activity_logs",
                "docname_pattern": "activity_{_uuid_}" // Use UUID in filename
              }
            },
            "versioning": { "is_versioned": false, "operation": "upsert" },
            "generate_uuid": true // Add UUID to document and use it in filename
          },
          // --- Example 10: Store non-dictionary data with UUID ---
          {
            "input_field_path": "simple_value", // Points to a string, number, etc.
            "target_path": {
              "filename_config": {
                "static_namespace": "primitive_values",
                "static_docname": "latest_value"
              }
            },
            "generate_uuid": true // Will wrap non-dict as {"uuid": "...", "data": original_value}
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

1.  **Global Defaults (`global_is_shared`, `global_is_system_entity`, `global_versioning`, `global_schema_options`, `global_on_behalf_of_user_id`, `global_process_list_items_separately`, `global_generate_uuid`, `global_extra_fields`, `global_create_only_fields`, `global_keep_create_fields_if_missing`)**: (Optional) Set default behaviors for all store operations. These can be individually overridden within each `store_configs` item.
    *   `global_versioning`: Defines the default versioning strategy.
        *   `is_versioned`: `true` or `false`.
        *   `operation`: Default action (e.g., `"upsert"`, `"update"`). A common default is `is_versioned: false, operation: "upsert"`.
        *   `version`: Default version name (e.g., `"default"`).
    *   `global_process_list_items_separately` (Optional bool): Default is `false`. If set to `true`, lists found at input_field_path will be processed item by item rather than stored as a single document.
    *   `global_generate_uuid` (Optional bool): Default is `false`. If set to `true`, a UUID will be added to all documents.
    *   `global_extra_fields` (Optional array): Default is an empty array. A list of extra fields to add to all documents. Each item needs `src_path` and optionally `dst_path`.
    *   `global_create_only_fields` (Optional List[str]): Default is an empty list. Specifies fields that should be preserved during document creation but removed during updates unless they already exist in the original document.
    *   `global_keep_create_fields_if_missing` (Optional bool): Default is `true`. Controls whether create-only fields should be preserved during updates if they don't exist in the original document.
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
            *   **Special placeholders in patterns:** When using `docname_pattern` or `input_docname_field_pattern`, you can include special placeholders:
                * `{_uuid_}`: Will be replaced with a UUID - if `generate_uuid` is `true`, the same UUID added to the document will be used; otherwise, a fresh UUID will be generated just for the filename.
                * `{_timestamp_}`: Will be replaced with the current UTC timestamp in ISO format.
    *   **`process_list_items_separately`** (Optional bool): Default is `null` (defers to global setting, which defaults to `false`). Controls behavior if `input_field_path` points to a list:
        *   `true`: Each item in the list is processed individually. Path resolution can use `{item[...]}` if items are dictionaries.
        *   `false`: The entire list is stored as a single document. Path resolution cannot use `{item[...]}`.
        *   `null`: Behavior is determined by `global_process_list_items_separately`. If that is also `null`, the behavior defaults to `false` (store list as a single document).
    *   **`generate_uuid`** (Optional bool): Default is `null` (defers to global setting, which defaults to `false`). Controls whether a UUID is automatically generated and added to each stored object:
        *   `true`: A UUID is generated for each document being stored.
        *   If the object is a dictionary, adds a `"uuid"` field directly to the dict.
        *   If the object is not a dictionary (string, number, etc.), it's wrapped in a structure like `{"uuid": "...", "data": original_value}`.
        *   The same UUID is used in `{_uuid_}` placeholders in docname patterns.
        *   When `generate_uuid` is `true`, the "uuid" field is automatically added to the internal `create_only_fields` list, ensuring the UUID is preserved during document updates.
        *   `false`: No UUID is added to the document.
        *   `null`: Behavior is determined by `global_generate_uuid`.
    *   **`extra_fields`** (Optional array): Default is `null` (defers to global setting, which defaults to `[]`). List of extra fields to add to objects being stored:
        *   Each entry must have:
            *   `src_path`: Dot-notation path to a value in the full input data.
            *   `dst_path` (Optional): Dot-notation path where the value should be placed in the stored object. If not provided, defaults to the last segment of `src_path`.
        *   Behavior notes:
            *   Extra fields are only added to dictionary objects. If storing primitives, extra fields are ignored.
            *   If a source path resolves to a list, that field is skipped (list values not copied).
            *   Nested destination paths are created as needed (e.g., `"metadata.source"` creates a `metadata` object if not present).
            *   The same extra fields are added to all objects when `process_list_items_separately` is `true`.
    *   **`create_only_fields`** (Optional List[str]): Default is `null` (defers to global setting, which defaults to `[]`). List of fields that should be preserved only during document creation and removed during updates unless they already exist in the original document. When using `generate_uuid=true`, the "uuid" field is automatically added to this list.
    *   **`keep_create_fields_if_missing`** (Optional bool): Default is `null` (defers to global setting, which defaults to `true`). If `true`, fields in `create_only_fields` will be preserved during updates if they don't already exist in the document being updated. This is particularly important for UUID preservation - when set to `false`, UUIDs may be discarded during updates if the original document doesn't have a UUID.
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
        "global_generate_uuid": true, // Add UUIDs to all documents
        "global_create_only_fields": ["created_at", "created_by"], // Fields that should never be overwritten
        "global_keep_create_fields_if_missing": true, // Add creation fields if missing
        "global_extra_fields": [
          {
            "src_path": "metadata.workflow_run_id",
            "dst_path": "source.workflow_run_id"
          },
          {
            "src_path": "metadata.timestamp", // dst_path defaults to "timestamp"
            "dst_path": "created_at"
          },
          {
            "src_path": "metadata.user_id",
            "dst_path": "created_by"
          }
        ],
        "store_configs": [
          {
            "input_field_path": "report_data", // Get data from this input field
            "target_path": {
              "filename_config": {
                "static_namespace": "generated_reports",
                "docname_pattern": "{item[report_type]}_{_uuid_}" // Use generated UUID in filename
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
        // Map the report data and metadata needed for extra fields
        { "src_field": "report_data", "dst_field": "report_data" },
        { "src_field": "workflow_metadata", "dst_field": "metadata" }
      ]
    },
    {
      "src_node_id": "store_report",
      "dst_node_id": "notify_user",
      "mappings": [
        // Pass through the original data if needed
        { "src_field": "passthrough_data", "dst_field": "original_input" }
        // Or map specific fields from the passthrough data
        // { "src_field": "passthrough_data.report_metadata.report_id", "dst_field": "processed_report_id" }
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
    *   `process_list_items_separately` (usually default/`null` which means `false`): If the data is a list, should each item be saved individually (`true`) or should the whole list be saved as one file (`false`)?
    *   `generate_uuid`: Should a unique ID be automatically added to each stored object? This ID can also be used in the filename using the `{_uuid_}` placeholder.
    *   `extra_fields`: A list of additional fields to add to the stored data, taken from other parts of the input. For example, add a timestamp or workflow ID to everything you save.
    *   `create_only_fields`: A list of field names that should never be overwritten after initial creation. For example, "created_at" timestamps or "created_by" values are preserved during updates.
    *   `keep_create_fields_if_missing`: If set to `true`, adds creation fields to existing documents if they're missing those fields. Useful when retrofitting metadata to existing objects.
    *   `target_path.filename_config`: Where should it be saved?
        -   `static_...`: Use if you know the exact name (e.g., save as `"latest_results"` in the `"daily_reports"` namespace).
        -   `input_..._field`: Use if the name comes from the data itself (e.g., save the order using the `"order_id"` field from the order data). **Works best if the item being saved is an object/dictionary.**
        -   `..._pattern`: Use when saving a list of items *individually* (`process_list_items_separately: true`), creating names based on each item's properties (e.g., save each product using its `"product_id"`). **Requires items in the list to be objects/dictionaries.** You can use special placeholders like `{_uuid_}` to include a unique ID in the filename.
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

## Common Use Cases for Extra Fields and UUID Generation

These features are particularly useful in several scenarios:

1. **Automatic Tracking and Auditing**:
   - Add metadata like workflow run ID, timestamp, and user ID to all stored documents
   - Generate a unique ID for each document for reliable tracking and referencing

2. **Creating Hierarchical Data Structures**:
   - Store related documents that reference each other via UUIDs
   - Maintain parent-child relationships between documents 

3. **Object Enrichment**:
   - Add global context (like batch ID, source system) to each item in a list
   - Maintain consistent metadata across all documents created in a workflow

4. **Simple Document Versioning** (even for unversioned documents):
   - Generate unique filenames with `{_uuid_}` while maintaining the same data structure
   - Track document lineage with source references

5. **Simplifying Access Patterns**:
   - Add lookup keys or normalized data to documents to simplify downstream queries
   - Enrich objects with computed values that aid in searching or filtering

## Advanced UUID and Creation Fields Management

The `create_only_fields` and `keep_create_fields_if_missing` parameters provide powerful controls for field preservation during document updates:

### UUID Generation and Preservation

When you set `generate_uuid: true`, the system:

1. Generates a unique UUID for each document being stored
2. Adds the UUID to the document (as a direct field for dictionaries, or wrapped for primitives)
3. **Automatically adds "uuid" to the `create_only_fields` list**
4. Ensures this UUID is:
   - Used in the filename via `{_uuid_}` placeholders if specified
   - **Preserved during all future updates** (the UUID never changes once assigned)

This behavior guarantees that once a document has been assigned a UUID, that identifier remains constant throughout its lifecycle, ensuring reliable referencing and tracking.

### How create_only_fields Work During Updates

When updating a document with the "update" or "upsert" operations, the following logic applies for fields in the `create_only_fields` list:

1. The system first checks if each create-only field exists in the original document
2. If the field exists in the original document, its value is preserved (the update value is ignored)
3. If the field doesn't exist in the original document:
   - When `keep_create_fields_if_missing` is `true`: The field from the update data is kept
   - When `keep_create_fields_if_missing` is `false`: The field from the update data is discarded

For UUID fields in particular:
- If updating a document that already has a UUID, that UUID is always preserved
- If updating a document without a UUID:
  - With `keep_create_fields_if_missing = true`: A new UUID is added to the document
  - With `keep_create_fields_if_missing = false`: No UUID is added (update-only behavior)

### Using Create-Only Fields

The `create_only_fields` parameter lets you designate specific fields that should:
- Be included when a document is first created
- Be preserved during updates (the original values are kept, not overwritten)

This is ideal for:
- **Creation timestamps**: Add a `created_at` field that's never modified
- **Creator identifiers**: Preserve information about who originally created the document
- **Source tracking**: Maintain information about where the document originally came from
- **Immutable reference IDs**: Ensure stable identifiers don't change, even if they're included in update data

### Controlling Missing Field Behavior

The `keep_create_fields_if_missing` parameter adds additional control:

- When `false` (Default behavior prior to changes): Create-only fields are only preserved if they already exist in the document
- When `true` (New default behavior): Create-only fields from the update data will be added if they don't exist in the original document

This is particularly useful when:
- Migrating data that's missing creation metadata
- Implementing a document recovery or repair process
- Retrofitting UUID generation to existing documents

### Example: Audit Trail Implementation

```json
{
  "store_configs": [{
    "input_field_path": "document_data",
    "target_path": { ... },
    "generate_uuid": true,  // Automatically adds "uuid" to create_only_fields
    "create_only_fields": ["created_at", "created_by", "source_system"],
    "keep_create_fields_if_missing": true,
    "extra_fields": [
      { "src_path": "metadata.timestamp", "dst_path": "created_at" },
      { "src_path": "metadata.user_id", "dst_path": "created_by" },
      { "src_path": "metadata.system", "dst_path": "source_system" },
      { "src_path": "metadata.timestamp", "dst_path": "updated_at" }
    ]
  }]
}
```

In this example:
- Every document gets a UUID that never changes
- Creation metadata (`created_at`, `created_by`, `source_system`) is preserved on updates
- If a document lacks these fields, they'll be added from the update data (`keep_create_fields_if_missing: true`)
- The `updated_at` field will change with each update since it's not in `create_only_fields`
