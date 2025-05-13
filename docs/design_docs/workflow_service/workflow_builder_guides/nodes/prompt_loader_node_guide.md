# Usage Guide: PromptTemplateLoaderNode

This guide explains how to configure and use the `PromptTemplateLoaderNode` to load predefined Prompt Templates from the system's database.

## 1. Purpose

Prompt templates are reusable text structures with placeholders (variables) that can be filled in later. They are often used to construct dynamic prompts for Large Language Models (LLMs).

The `PromptTemplateLoaderNode` allows your workflow to:

-   Fetch one or more prompt templates stored in the database.
-   Identify templates using:
    -   Fixed names and versions defined directly in the configuration.
    -   Names and versions determined dynamically from data flowing through the workflow.
-   Load templates specific to the organization or system-wide templates.
-   Handle cases where a specific version is not required.

The loaded template content and associated metadata (like input variables) are then added to the workflow's data stream for use by subsequent nodes, typically a `PromptConstructorNode`.

## 2. Configuration (`NodeConfig`)

You configure the `PromptTemplateLoaderNode` within the `node_config` field of its entry in the `GraphSchema`. The configuration follows the `LoadPromptTemplatesConfig` schema.

```json
{
  "nodes": {
    "load_prompts": {
      "node_id": "load_prompts", // Unique ID for this node instance
      "node_name": "load_prompt_templates", // ** Must be "load_prompt_templates" **
      "node_config": { // This is the LoadPromptTemplatesConfig schema
        // --- List of templates to load ---
        "load_entries": [ // Required: List of load instructions (at least one)
          // --- Example 1: Load a specific template version statically ---
          {
            "path_config": { // How to find the template
              "static_name": "email_summary_v2", // Exact name
              "static_version": "2.1" // Exact version
              // input_name_field_path: null (not used)
              // input_version_field_path: null (not used)
            },
            "output_key_name": "summary_template" // Key for this template in the output dict
          },
          // --- Example 2: Load based on input data (version optional) ---
          {
            "path_config": {
              // Get name from a field in the node's input data
              "input_name_field_path": "input_data.template_selector.name", // e.g., input has { "template_selector": { "name": "customer_reply_base" } }
              // Version is optional: If input path not found and no static_version, loads latest/default matching the name.
              "input_version_field_path": "input_data.template_selector.version" // e.g., { "version": "1.0" } or missing
            },
            // output_key_name is omitted: defaults to the resolved template name (e.g., "customer_reply_base")
          },
          // --- Example 3: Load statically, version is optional ---
          {
            "path_config": {
              "static_name": "system_greeting" // Exact name
              // static_version: null (version is optional)
            },
            "output_key_name": "greeting_tpl"
          },
           // --- Example 4: Dynamic name, fallback static version ---
          {
            "path_config": {
              "input_name_field_path": "input_data.template_name", // e.g., "task_routing_logic"
              "static_version": "latest" // Use 'latest' version if input path for version isn't found or invalid
            },
            "output_key_name": "routing_tpl"
          }
        ]
      }
      // dynamic_input_schema / dynamic_output_schema usually not needed
    }
    // ... other nodes
  }
  // ... other graph properties
}
```

### Key Configuration Sections:

1.  **`load_entries`** (List[`PromptTemplateLoadEntry`]): **Required**. A list where each item defines one prompt template to load. Must contain at least one entry.
2.  **Inside each `load_entries` item**:
    *   **`path_config`** (`PromptTemplatePathConfig`, **Required**): Defines *how* to find the template's name and version.
        *   **Name Resolution (Mandatory):** You *must* provide a way to determine the template name.
            *   `static_name` (String): A fixed template name.
            *   `input_name_field_path` (String): A dot-notation path (e.g., `"details.prompt_name"`) to a field within the node's input data. The value of that field will be used as the template name.
            *   **Priority:** If `input_name_field_path` is provided and the path exists in the input data yielding a valid string, that value is used. Otherwise, the `static_name` (if provided) is used as a fallback. If neither resolves to a name, the load for this entry will fail.
        *   **Version Resolution (Optional):** Determining the version is optional. If not specified, the system typically loads the most relevant version (e.g., the latest or default) matching the resolved name.
            *   `static_version` (String): A fixed template version (e.g., `"1.0"`, `"latest"`).
            *   `input_version_field_path` (String): A dot-notation path to a field in the input data containing the version string.
            *   **Priority:** If `input_version_field_path` is provided and resolves to a valid string, that version is used. Otherwise, the `static_version` (if provided) is used as a fallback. If neither is provided or resolves, the version is considered `None` (optional).
    *   **`output_key_name`** (String, **Optional**): The key under which the loaded template data will be placed in the node's output `loaded_templates` dictionary.
        *   **If provided:** The loaded data for this entry will be accessible via `output.loaded_templates[your_output_key_name]`.
        *   **If omitted (or `null`):** The key will default to the *resolved template name* obtained from `path_config`. For example, if `static_name` was "email_body" and no `input_name_field_path` was used, the output key would be `"email_body"`.

## 3. Input (`DynamicSchema`)

The `PromptTemplateLoaderNode` accepts dynamic input (`DynamicSchema`). Input data is only required if one or more `load_entries` use `input_name_field_path` or `input_version_field_path` in their `path_config`.

-   If dynamic paths are configured, the input data must contain the fields specified by those paths (e.g., `{ "input_data": { "template_selector": { "name": "some_template" } } }`).
-   This input data should be mapped from previous nodes or the central state using Edges.

## 4. Output (`LoadPromptTemplatesOutput`)

The node produces an output object of type `LoadPromptTemplatesOutput` containing the results of the loading attempts.

```json
// Example Output Structure
{
  "loaded_templates": {
    "summary_template": { // Key matches 'output_key_name' from config
      "template": "Summarize this: {text}",
      "input_variables": { "text": null },
      "metadata": {
        "name": "email_summary_v2",
        "version": "2.1",
        "description": "Summarizes email content",
        "is_system_entity": false,
        "owner_org_id": "uuid-of-org"
      },
      "id": "uuid-of-template-version"
    },
    "customer_reply_base": { // Key matches resolved template name (default)
      "template": "Hello {customer_name}, ...",
      "input_variables": { "customer_name": null },
      "metadata": { /* ... */ },
      "id": "uuid-of-template-version-2"
    },
    "greeting_tpl": { /* ... */ }
    // Entries for templates that failed to load will NOT appear here.
  },
  "load_errors": [
    // List of errors encountered, if any.
    {
      "entry_index": 3, // Index in the config's load_entries list
      "config": { /* copy of the config for the failed entry */ },
      "resolved_name": "non_existent_template",
      "resolved_version": "1.0",
      "output_key": "some_key", // The intended output key
      "error": "Template 'non_existent_template' version '1.0' not found..."
    },
    {
      "entry_index": 4,
      "config": { /* ... */ },
      "error": "Path resolution failed: Input field 'bad.path.name' not found and no static_name provided."
      // resolved_name/version might be null if resolution failed early
    }
  ]
}
```

-   **`loaded_templates`** (Dict[str, `LoadedPromptTemplateData`]): A dictionary containing the data for successfully loaded templates.
    *   The **keys** are determined by the `output_key_name` configuration for each entry (or the resolved template name if `output_key_name` was omitted).
    *   The **values** are `LoadedPromptTemplateData` objects containing:
        *   `template` (String): The actual template content string.
        *   `input_variables` (Dict | `null`): A dictionary of variable names found in the template (keys) and their optional default values (values).
        *   `metadata` (Dict | `null`): Additional information about the template (name, version, description, system status, owner).
        *   `id` (String | `null`): The unique ID (UUID) of the loaded prompt template version.
-   **`load_errors`** (List[Dict]): A list detailing any errors that occurred during the loading process for any `load_entries`. Each error dictionary typically includes:
    *   `entry_index`: The 0-based index of the entry in the `node_config.load_entries` list that failed.
    *   `config`: The configuration of the specific `PromptTemplateLoadEntry` that failed.
    *   `resolved_name`/`resolved_version`: The name/version the node attempted to load (if resolution succeeded).
    *   `output_key`: The intended key for the output dictionary.
    *   `error`: A string describing the reason for failure (e.g., "not found", "Path resolution failed").

## 5. Example `GraphSchema` Snippet

```json
{
  "nodes": {
    "get_input_params": {
      /* ... node that outputs required template info ... */
      // Example Output: { "template_info": { "name": "dynamic_email", "version": "2.0" } }
    },
    "load_prompts": {
      "node_id": "load_prompts",
      "node_name": "load_prompt_templates",
      "node_config": {
        "load_entries": [
          { // Static load
            "path_config": { "static_name": "standard_header", "static_version": "1.0" },
            "output_key_name": "header_tpl"
          },
          { // Dynamic load from get_input_params output
            "path_config": {
              "input_name_field_path": "template_info.name", // Map from input field
              "input_version_field_path": "template_info.version" // Map from input field
            },
            // Output key will default to the resolved name (e.g., "dynamic_email")
          }
        ]
      }
    },
    "build_final_prompt": {
      "node_id": "build_final_prompt",
      "node_name": "prompt_constructor", // Needs loaded templates as input
      "node_config": { /* ... */ }
    }
  },
  "edges": [
    {
      "src_node_id": "get_input_params",
      "dst_node_id": "load_prompts", // Provide input for dynamic path resolution
      "mappings": [
        // Map the whole 'template_info' object, or individual fields
        { "src_field": "template_info", "dst_field": "template_info" }
      ]
    },
    {
      "src_node_id": "load_prompts",
      "dst_node_id": "build_final_prompt", // Pass loaded templates to the constructor
      "mappings": [
        // Map the entire output dictionary
        // { "src_field": "loaded_templates", "dst_field": "loaded_templates_input" }
        // Or map specific templates if the constructor expects named inputs
         { "src_field": "loaded_templates.header_tpl", "dst_field": "header_template_data" },
         // Assuming the dynamic template was 'dynamic_email'
         { "src_field": "loaded_templates.dynamic_email", "dst_field": "body_template_data" }
      ]
    },
    // Edge to handle potential errors (optional)
    {
       "src_node_id": "load_prompts",
       "dst_node_id": "handle_load_errors_node", // Some node to log or manage errors
       "mappings": [ { "src_field": "load_errors", "dst_field": "template_load_failures"} ]
    }
  ],
  "input_node_id": "...",
  "output_node_id": "..."
}
```

## 6. Notes for Non-Coders

-   Use this node to grab pre-written text templates (like email outlines or AI instructions) that are stored centrally.
-   `load_entries`: Tell the node *which* templates to get. You can ask for multiple templates at once.
-   Inside each request (`load_entries` item):
    -   `path_config`: How to find the template.
        -   `static_name`/`static_version`: Use if you know the *exact* name and version you need (e.g., load template `"welcome_email"` version `"v3"`).
        -   `input_..._field`: Use if the name/version depends on earlier steps in the workflow (e.g., load the template whose name is stored in the `"chosen_template_name"` field from the previous step's output).
        -   **Name is required, Version is optional:** You *must* tell it the name somehow. If you don't specify a version, it usually finds the latest or default one.
    -   `output_key_name`: Give a nickname to the loaded template so you can easily refer to it in the next step (e.g., call the loaded template `"email_body_template"`). If you don't give a nickname, it uses the template's actual name.
-   The node outputs a list of successfully loaded templates (in `loaded_templates`) and a separate list of any errors it encountered (in `load_errors`).
-   Connect the `loaded_templates` output (or specific templates within it) to the next node that needs them, usually a `PromptConstructorNode`.
