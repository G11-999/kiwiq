# Usage Guide: PromptConstructorNode

This guide explains how to use the `PromptConstructorNode` to dynamically build text prompts for other nodes (like the `LLMNode`) using templates and variables. This node can use templates defined directly in its configuration or load them from the central Prompt Template database.

## 1. Purpose

The `PromptConstructorNode` takes text templates containing placeholders (like `{variable_name}`) and fills those placeholders with actual values. These values can come from input data (mapped via edges or looked up via configured paths), defined defaults within the node, or defaults from loaded templates. This allows you to create complex and context-specific prompts without hardcoding them directly into your workflow graph.

Think of it as a powerful mail merge tool for your workflow prompts.

Common use cases:
-   Creating personalized prompts using user data found anywhere in the input structure.
-   Building complex instructions for LLMs by combining static text with dynamic information loaded from the database or specific input paths.
-   Generating system prompts based on workflow state or loaded configurations.
-   Standardizing prompt structures across different parts of a workflow by loading shared templates.

## 2. Configuration (`NodeConfig`)

The main configuration happens within the `node_config` field, specifically using the `PromptConstructorConfig` schema.

```json
{
  "nodes": {
    "build_my_prompts": {
      "node_id": "build_my_prompts",
      "node_name": "prompt_constructor", // ** Must be "prompt_constructor" **
      "node_config": {
        // --- Define one or more templates ---
        "prompt_templates": {
          // --- Example 1: Static Definition with Custom Sourcing ---
          "static_greeting": { // Key used internally for organization
            "id": "greeting_prompt", // ** This becomes the output field name **
            "template": "Hello {user_name} from {location}, welcome to {service}!",
            "variables": {
              // List variables expected by this template
              "user_name": null, // MUST be provided by input (P3, P4, or P5/P6 if default exists)
              "service": "Our Awesome Platform", // P5: Default value if not sourced otherwise
              "location": null // MUST be provided by input (P1-P4)
            },
            "construct_options": { // P1: Highest priority source for 'location' in THIS template
              "location": "user_profile.address.city" // Path within node's input data
            }
            // template_load_config: null (Not used for static)
          },
          // --- Example 2: Dynamic Loading from DB ---
          "dynamic_summary": {
            "id": "summary_prompt_for_llm", // ** Another output field name **
            "template_load_config": { // Specify how to load the template
              "path_config": {
                "static_name": "customer_interaction_summary_v3"
              }
            },
            // Static variables can supplement/override loaded defaults
            "variables": {
              "tone": "professional", // P5: Override potential loaded default (P6) for 'tone'
              "max_length": 500,    // P5: Provide a variable not defined in the loaded template
              "customer_history": null // Must be provided by input (P1-P4)
            }
            // template: null (Not used for dynamic loading)
          },
          // --- Example 3: Dynamic Loading using Input Data ---
          "dynamic_email_body": {
            "id": "final_email_body",
            "template_load_config": {
              "path_config": {
                "input_name_field_path": "input.email_details.template_name",
                "input_version_field_path": "input.email_details.version_spec"
              }
            },
            "variables": {
              "recipient_name": null // Must be provided via input (P1-P4)
              // Other variables will come from the loaded template (P6) or input (P1-P4)
            }
          }
          // ... more templates
        },
        // --- NEW: Global Fallback Sourcing ---
        "global_construct_options": { // P2: Fallback source for variables across ALL templates
           "customer_history": "session_data.customer.full_history", // Path within node's input data
           "recipient_name": "input.default_recipient" // Path, lower priority than template-specific P1
           // Variables not listed here rely on P3, P4, P5, or P6
        }
      },
      // Input/Output schemas are DYNAMIC. They MUST be defined in the graph schema
      // to declare expected inputs and outputs.
      "dynamic_input_schema": { /* See Section 3 & 5 */ },
      "dynamic_output_schema": { /* See Section 4 & 5 */ }
    }
    // ... other nodes
  }
  // ... other graph properties
}
```

### `node_config` Details:

1.  **`prompt_templates`** (Dict[str, `PromptTemplateDefinition`], required): Defines each prompt construction task.
    *   The *key* (e.g., `"static_greeting"`) is for organization.
    *   Inside each `PromptTemplateDefinition`:
        *   **`id`** (str, required): Determines the output field name for the constructed prompt (e.g., `greeting_prompt`).
        *   **Template Source (Choose ONE):**
            *   `template` (str): Define the template string directly.
            *   `template_load_config` (`PromptTemplateLoadEntryConfig`): Configure dynamic loading from the DB (see `PromptTemplateLoaderNode` guide for details on `path_config`).
        *   **`variables`** (Dict[str, Optional[Any]], required): Lists variables *associated* with this template. Defines defaults (Priority 5/6) and required inputs.
            *   `null`: Variable *must* be provided via input (Priorities 1-4).
            *   Value (e.g., string, number): Default value (Priority 5), potentially overriding a loaded template's default (Priority 6).
        *   **`construct_options`** (Optional[Dict[str, str]]): **Priority 1**. Template-specific mapping from a `{variable_name}` to a dot-notation path within the node's input data (e.g., `"user_name": "user_context.name"`). Overrides all other sources for this variable *in this template only*.
2.  **`global_construct_options`** (Optional[Dict[str, str]]): **Priority 2**. Global mapping from `{variable_name}` to a dot-notation path within the node's input data. Used as a fallback if `template_specific_construct_options` (P1) is not defined for a variable.

## 3. Input (Dynamic Schema)

The `PromptConstructorNode` requires specific fields in its input data to function correctly. These fields must be declared in the node's `dynamic_input_schema` within the `GraphSchema` and provided via incoming `EdgeSchema` mappings.

**Required Inputs:**

1.  **Fields for `construct_options`:** Any top-level keys that are the start of a path used in `construct_options` or `global_construct_options` (e.g., if you have path `"user_profile.address.city"`, the input schema needs a field named `"user_profile"` of type `any` or `object`).
2.  **Fields for Dynamic Template Loading:** Any fields referenced by `input_name_field_path` or `input_version_field_path` if using `template_load_config`.
3.  **Fields for Direct Input Mappings (P3/P4):** Any fields mapped directly via edges with `dst_field` matching `TEMPLATE_ID.VARIABLE_NAME` (P3) or `variable_name` (P4).

**Variable Resolution Priority:**

The node resolves the final value for each placeholder (`{variable}`) in each template according to this strict priority order:

1.  **Template-Specific `construct_options` (Highest Priority):**
    *   Checks the `construct_options` defined within the specific `PromptTemplateDefinition` (keyed by `id`).
    *   If the `variable_name` exists as a key, it attempts to retrieve the value from the node's input data using the specified dot-notation path. If found, this value is used.

2.  **Global `construct_options`:**
    *   If not found via P1, checks the `global_construct_options` defined at the top level of `node_config`.
    *   If the `variable_name` exists as a key, it attempts to retrieve the value from the input data using the specified dot-notation path. If found, this value is used.

3.  **Template-Specific Input Mapping:**
    *   If not found via P1 or P2, checks if the node's input data contains a key matching `TEMPLATE_ID.VARIABLE_NAME` (e.g., `greeting_prompt.user_name`).
    *   If the key exists and its value is not `None`, that value is used *only* for this template. (Requires an incoming edge mapping to this `dst_field`).

4.  **Global Input Mapping:**
    *   If not found via P1, P2, or P3, checks if the node's input data contains a key exactly matching the `variable_name` (e.g., `user_name`).
    *   If the key exists and its value is not `None`, that value is used for the variable in *any* template requiring it (unless already set by P1, P2, or P3). (Requires an incoming edge mapping to this `dst_field`).

5.  **Static Default / Override (in `node_config`)**:
    *   If not found via P1-P4, checks the `variables` dictionary defined *within the specific `PromptTemplateDefinition`* in the `node_config`.
    *   If the `variable_name` exists and its value is *not* `null`, that value is used.

6.  **Loaded Default (from DB Template):**
    *   If the template was loaded dynamically (`template_load_config`) and not found via P1-P5, checks the `input_variables` dictionary loaded from the database template.
    *   If a default value exists there, it's used.

7.  **Required Input (Error):**
    *   If a variable placeholder exists in the final template string, and its value hasn't been determined by steps 1-6, the node will fail during output validation if that output field (`id`) is marked as required in the `dynamic_output_schema`. The error will be reported in `prompt_template_errors`.

## 4. Output (Dynamic Schema - `PromptConstructorOutput`)

The `PromptConstructorNode` produces a dynamic output object. Its structure **must** be defined in the node's `dynamic_output_schema` within the `GraphSchema`. This schema dictates which fields the node will attempt to include in its final, validated output.

-   **Constructed Prompts:** For each `PromptTemplateDefinition` defined in `node_config.prompt_templates`, the `dynamic_output_schema` should include a field definition matching the template's **`id`**.
    *   The **name** of the output field matches the `id` (e.g., `greeting_prompt`, `summary_prompt_for_llm`).
    *   The **value** will be the fully constructed prompt string *if* construction was successful.
    *   Mark the field as `required: true` in the schema if the workflow depends on this prompt being successfully generated. If construction fails for a required field, the node execution will fail with a `ValidationError`. If marked `required: false`, the field will simply be absent from the output model if construction fails.
-   **`prompt_template_errors`** (Optional[List[Dict]]): To receive errors, you **must** define a field named `prompt_template_errors` (typically `type: "list", required: false`) in the `dynamic_output_schema`.
    *   If defined and errors occur during template loading or construction, this field will contain a list of dictionaries detailing those errors (including `template_id` and `error`).
    *   If defined and no errors occur, this field will contain an empty list (`[]`).
    *   If this field is *not* defined in the `dynamic_output_schema`, any internal errors will still be logged, but they will not be included in the node's output object passed to downstream nodes.

## 5. Example (`GraphSchema`)

```json
{
  "nodes": {
    "get_context": {
      /* ... node outputting complex context object ... */
      // Example Output: { "user_profile": { "name": "Alice", "address": { "city": "Wonderland" } }, "session_data": { ... }, "specific_template": "customer_followup" }
    },
    "build_email_prompts": {
      "node_id": "build_email_prompts",
      "node_name": "prompt_constructor",
      "node_config": {
        "prompt_templates": {
          "header": {
            "id": "email_subject", // Output field name
            "template": "Regarding your inquiry - {user_name}",
            "variables": { "user_name": null }, // Required from input
            "construct_options": { "user_name": "user_profile.name" } // P1 Source
          },
          "body": {
            "id": "email_body", // Output field name
            "template": "Hi {user_name}, Thanks for contacting us from {city}.",
            "variables": { "user_name": null, "city": "Unknown" }, // city has P5 default
            "construct_options": { "user_name": "user_profile.name" }, // P1 for user_name
            // city will use P2 (global option)
          }
        },
        "global_construct_options": { // P2 Sources
          "city": "user_profile.address.city"
        }
      },
      // Define expected inputs for lookups
      "dynamic_input_schema": {
        "fields": {
          "user_profile": { "type": "any", "required": true, "description": "Needed for construct options" }
        }
      },
      // Define expected outputs (MUST be defined)
      "dynamic_output_schema": {
        "fields": {
          "email_subject": { "type": "str", "required": true }, // This prompt MUST succeed
          "email_body": { "type": "str", "required": true }, // This prompt MUST succeed
          "prompt_template_errors": { "type": "list", "required": false } // Include errors if they occur
        }
      }
    },
    "send_email": { /* ... uses email_subject, email_body ... */ },
    "log_errors": { /* ... uses prompt_template_errors ... */ }
  },
  "edges": [
    // Provide the structured input needed by construct_options
    {
      "src_node_id": "get_context",
      "dst_node_id": "build_email_prompts",
      "mappings": [
        // Map the container object needed for path lookups
        { "src_field": "user_profile", "dst_field": "user_profile" }
        // No need to map individual variables if solely using construct_options
      ]
    },
    // Use constructed prompts
    {
      "src_node_id": "build_email_prompts",
      "dst_node_id": "send_email",
      "mappings": [
        { "src_field": "email_subject", "dst_field": "subject" },
        { "src_field": "email_body", "dst_field": "body" }
      ]
    },
    // Handle errors (only works if errors field defined in output schema)
    {
      "src_node_id": "build_email_prompts",
      "dst_node_id": "log_errors",
      "mappings": [ { "src_field": "prompt_template_errors", "dst_field": "errors" } ]
    }
  ],
  // ... input/output nodes ...
}
```

## 6. Notes for Non-Coders

-   Use `PromptConstructorNode` to create reusable prompt text by filling in blanks `{like_this}`.
-   **Define Tasks:** In `node_config.prompt_templates`, set up each prompt you want to build. Give each a unique `id` (e.g., `"final_greeting"`). This `id` becomes the name of the output field containing the finished prompt.
-   **Choose Source:**
    *   **Static:** Write the text directly in `template`.
    *   **Dynamic Load:** Use `template_load_config` to grab a template from the central library.
-   **List Variables:** In `variables` for each task (`id`):
    *   List all `{variable}` names needed.
    *   Use `null` if the value *must* come from input.
    *   Provide a default value (like `"professional"`) if needed.
-   **Tell it *Where* to Find Input Values (Highest Priority):**
    *   `construct_options`: Inside a specific task (`id`), map a `{variable}` to a specific location in the input data (e.g., tell it `{user_name}` is found at `user_profile.name`). This wins over everything else for *that task*.
    *   `global_construct_options`: Map variables to input locations as a fallback for *all* tasks if they don't have a specific `construct_options` for that variable.
-   **Alternatively, Provide Input Values *Directly* (Lower Priority):**
    *   Use edges to map values *directly* to the node.
    *   Map to `TEMPLATE_ID.VARIABLE_NAME` (e.g., `final_greeting.user_name`) to set it just for that template (Priority 3).
    *   Map to `VARIABLE_NAME` (e.g., `user_name`) to set it for all templates (Priority 4).
    *   **Important:** These direct mappings are *lower* priority than `construct_options`.
-   **Defaults (Lowest Priority):** If no input is found via the methods above, the node uses the default value from `variables` (P5), then the default from a loaded template (P6).
-   **Connect Inputs:** Use edges to feed the *data structures* needed for `construct_options` lookups (e.g., map the whole `user_profile` object) and any direct inputs (P3/P4). Define the expected inputs in `dynamic_input_schema`.
-   **Connect Outputs:** Use edges to take the finished prompts (using the template `id` as the `src_field`) and `prompt_template_errors` to the next nodes. Define the expected outputs (including the template `id`s and optionally `prompt_template_errors`) in `dynamic_output_schema`. 