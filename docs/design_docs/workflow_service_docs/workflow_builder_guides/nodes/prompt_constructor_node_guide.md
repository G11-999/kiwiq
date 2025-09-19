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

## 1.1. What's new (v0.2.0)

- Template construction and loading have been merged into a single node.
- Version selection is optional when dynamically loading templates; if omitted, the latest semantic version is chosen automatically.
- Support for special variables: "$current_date" and "$current_datetime" are resolved at build time regardless of the source.
- Robust image support (static and dynamic collection) with validation and de-duplication.
- Optional per-template image outputs via `separate_images_by_template`.

## 1.2. Image Support

**NEW:** The `PromptConstructorNode` now supports collecting and organizing images alongside prompt construction. This is particularly useful for vision-enabled LLM workflows where you need to send both text prompts and images to models that support multimodal input.

**Image Collection Methods:**

1. **Static Images**: Define image URLs or base64-encoded images directly in the template configuration
2. **Dynamic Image Collection**: Specify paths in the input data to collect images from
   - Each path can point to a single image URL/base64 string
   - Each path can also point to a list of image URLs/base64 strings
   - Supports nested object navigation using dot notation (e.g., `user_data.uploads.images`)

**Image Output Options:**

- **Template-Specific Images**: Each template gets its own `{template_id}_images` output field (when `separate_images_by_template: true`)
- **Combined Images**: All images from all templates are combined into an `all_images` output field
- **Automatic Deduplication**: Duplicate images are automatically removed while preserving order
- **Validation**: Invalid URLs and malformed base64 data are filtered out with appropriate logging

**Integration with LLM Node:**

To use the collected images with an LLM node that supports vision:
```json
{
  "edges": [
    {
      "src_node_id": "prompt_constructor",
      "dst_node_id": "llm_node", 
      "mappings": [
        {"src_field": "my_prompt", "dst_field": "user_prompt"},
        {"src_field": "all_images", "dst_field": "image_input_url_or_base64"}
      ]
    }
  ]
}
```

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
            },
            "user_custom_instructions": "Focus on being friendly and personable in your response.", // Optional: Additional instructions appended to the template
            // Image support - static images
            "static_images": [
              "https://example.com/welcome-banner.jpg",
              "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
            ],
            // Image support - dynamic image collection
            "image_collection_paths": [
              "user_profile.avatar_url",           // Single image from user profile
              "welcome_data.promotional_images"    // List of promotional images
            ],
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
              "tone": "professional", // P5: Override a default loaded from DB for 'tone'
              "max_length": 500,    // P5: Provide a variable not defined in the loaded template
              "customer_history": null // Must be provided by input (P1-P4)
            },
            "user_custom_instructions": "Ensure the summary is comprehensive yet concise." // Optional additional instructions
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
              // Other variables will come from the loaded template defaults or input (P1-P4)
            }
          }
          // ... more templates
        },
        // --- NEW: Global Fallback Sourcing ---
        "global_construct_options": { // P2: Fallback source for variables across ALL templates
           "customer_history": "session_data.customer.full_history", // Path within node's input data
           "recipient_name": "input.default_recipient" // Path, lower priority than template-specific P1
           // Variables not listed here rely on P3, P4, P5, or P6
        },
        // --- NEW: Image Output Control ---
        "separate_images_by_template": true // Default: true. Set to false to only output combined "all_images" field
      }
      // Note: The node automatically receives all inputs piped to it via edges
      // Output fields are automatically created based on template IDs
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
            - Values must be dot-notation paths (pointers to input data), not literal values.
            - Do not place special variables here. Provide `$current_date` / `$current_datetime` as defaults in `variables` or as direct inputs.
            - If you want to source a special token via a path, the path's value in the input may be the token string; the `construct_options` value itself remains a path.
        *   **`user_custom_instructions`** (Optional[str]): Additional instructions or guidance that will be appended to the template content. This is useful for adding context-specific directions for LLM processing without modifying the base template. The instructions are appended with a clear header: `\n\n# Additional User Instructions\n{instructions}`.
        *   **`static_images`** (Optional[List[str]]): List of static image URLs or base64 encoded images to include with this template. These images will always be included in the output when this template is processed.
        *   **`image_collection_paths`** (Optional[List[str]]): List of dot-notation paths in the input data to collect images from. Each path can point to either:
            *   A single image URL/base64 string
            *   A list of image URLs/base64 strings
            *   The node will automatically handle both cases and flatten lists appropriately.
2.  **`global_construct_options`** (Optional[Dict[str, str]]): **Priority 2**. Global mapping from `{variable_name}` to a dot-notation path within the node's input data. Used as a fallback if `template_specific_construct_options` (P1) is not defined for a variable.
3.  **`separate_images_by_template`** (bool, default: true): Controls how image outputs are structured:
    *   `true` (default): Creates both template-specific image fields (`{template_id}_images`) AND a combined `all_images` field
    *   `false`: Only creates the combined `all_images` field, omitting template-specific fields

### 2.1 Dynamic Template Loading: Name/Version Resolution and Prerequisites

When using `template_load_config.path_config`, resolution follows:

- Resolve name from `input_name_field_path` (if provided and found) else `static_name`. Name is required.
- Resolve version from `input_version_field_path` (if provided and found) else `static_version`. Version is optional.
- If version is omitted, the node will select the latest semantic version among matches.

Runtime prerequisites for dynamic loading:

- `runtime_config` must be provided at execution time and contain application and external context under keys `APPLICATION_CONTEXT_KEY` and `EXTERNAL_CONTEXT_MANAGER_KEY`.
- The application context must include `user` and `workflow_run_job` objects (used to scope org and permissions).
- If any of these are missing, the node records load errors and skips those templates.

## 3. Input (Automatic Input Handling)

The `PromptConstructorNode` automatically receives all input data piped to it via incoming edges. You don't need to declare input schemas - the node will have access to any data mapped to it through edge configurations.

**Available Input Data:**

The node can access any data mapped to it via edges using dot-notation paths in `construct_options` and `global_construct_options`. For example:
- If an edge maps `src_field: "user_data"` to `dst_field: "user_info"`, you can access nested data using paths like `"user_info.profile.name"`
- All mapped fields become immediately available for variable resolution

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

5.  **Defaults (Static or Loaded):**
    *   If not found via P1-P4, the node uses the defaults prepared for the template. For dynamically loaded templates, loaded defaults are combined with and overridden by any `variables` defined in the node config. For static templates, only the `variables` from the node config are used.

6.  **Required Input (Error):**
    *   If a variable placeholder exists in the final template string, and its value hasn't been determined by steps 1-5, the node will report the error in `prompt_template_errors` and omit that output field from the results.

## 4. Output (Automatic Output Generation)

The `PromptConstructorNode` automatically generates output fields based on the `id` values of your prompt templates. You don't need to define output schemas - the node creates the appropriate output structure automatically.

**Generated Output Fields:**

-   **Constructed Prompts:** For each `PromptTemplateDefinition` defined in `node_config.prompt_templates`, the node automatically creates an output field with the name matching the template's **`id`**.
    *   The **name** of the output field matches the `id` (e.g., `greeting_prompt`, `summary_prompt_for_llm`).
    *   The **value** will be the fully constructed prompt string if construction was successful.
    *   If construction fails, the field will be absent from the output.
-   **`prompt_template_errors`** (Optional[List[Dict]]): Automatically included when errors occur.
    *   Contains a list of dictionaries detailing template loading or construction errors (including `template_id` and `error`).
    *   Contains an empty list (`[]`) when no errors occur.
    *   Always available for downstream nodes to access error information.

-   **Image Outputs:** The node automatically creates image output fields when templates include images:
    *   **Template-Specific Images** (`{template_id}_images`): When `separate_images_by_template: true` (default), each template that has images gets its own output field named `{template_id}_images` (e.g., `greeting_prompt_images`, `summary_prompt_images`).
        *   The **value** will be a list of valid image URLs/base64 strings collected for that specific template.
        *   Only created when the template actually has images.
    *   **Combined Images** (`all_images`): A field containing all unique images collected from all templates.
        *   The **value** will be a list of unique image URLs/base64 strings (duplicates automatically removed, order preserved).
        *   Only created when any template has images.
        *   This field is always created when any images are collected, regardless of the `separate_images_by_template` setting.
    *   **Image Validation and Order**:
        *   Valid inputs include: `http(s)://`, `ftp(s)://`, `data:image/...;base64,...`, or sufficiently long raw base64 that decodes successfully.
        *   Static images are added first, then dynamically collected images from paths; duplicates are removed while preserving first-seen order.
        *   When `separate_images_by_template` is `false`, per-template image fields are omitted and only `all_images` is output.

## 4.1 Special Variables and Template Formatting

- Special tokens are supported when provided as default values (`variables`) or as direct inputs:
  - `$current_date` → resolved to YYYY-MM-DD in UTC at build time.
  - `$current_datetime` → resolved to YYYY-MM-DD HH:MM:SS in UTC at build time.
- Do not place special tokens directly in `construct_options`. `construct_options` is strictly for dot-notation paths into the node's input. To source a special token by path, point the path to an input field whose value is the token string (e.g., `data.special_date == "$current_date"`).
- Placeholders are processed via Python `str.format`. Escape literal braces in templates using `{{` and `}}`.
- If a resolved variable value is a dict or list, it is JSON-serialized before insertion into the template.
- `None` values are allowed and will render as the string `"None"` unless your template omits such placeholders.

## 5. Example (`GraphSchema`)

### 5.1. Image Processing Example

Here's an example showing how to use the image collection features with an LLM node for vision processing:

```json
{
  "nodes": {
    "user_input": {
      /* ... node outputting user data with images ... */
      // Example Output: { 
      //   "user_profile": { "name": "Alice", "avatar": "https://example.com/alice.jpg" }, 
      //   "uploaded_files": ["https://example.com/doc1.png", "https://example.com/doc2.jpg"],
      //   "analysis_type": "document_analysis"
      // }
    },
    "build_vision_prompt": {
      "node_id": "build_vision_prompt",
      "node_name": "prompt_constructor",
      "node_config": {
        "prompt_templates": {
          "analysis_request": {
            "id": "vision_prompt",
            "template": "Please analyze these images for {user_name}. Focus on: {analysis_type}",
            "variables": { "user_name": null, "analysis_type": "general analysis" },
            "construct_options": { "user_name": "user_profile.name" },
            "static_images": ["https://example.com/instruction_diagram.png"], // Always include instructions
            "image_collection_paths": [
              "user_profile.avatar",     // Single profile image
              "uploaded_files"           // List of uploaded images
            ],
            "user_custom_instructions": "Provide detailed analysis with confidence scores."
          }
        },
        "global_construct_options": {
          "analysis_type": "analysis_type"
        },
        "separate_images_by_template": true
      }
      // Output will automatically include: vision_prompt, vision_prompt_images, all_images, prompt_template_errors
    },
    "vision_llm": {
      "node_id": "vision_llm",
      "node_name": "llm",
      "node_config": {
        "llm_config": {
          "model_spec": { "provider": "openai", "model": "gpt-4o" },
          "max_tokens": 1000
        }
      }
    }
  },
  "edges": [
    {
      "src_node_id": "user_input",
      "dst_node_id": "build_vision_prompt",
      "mappings": [
        { "src_field": "user_profile", "dst_field": "user_profile" },
        { "src_field": "uploaded_files", "dst_field": "uploaded_files" },
        { "src_field": "analysis_type", "dst_field": "analysis_type" }
      ]
    },
    {
      "src_node_id": "build_vision_prompt", 
      "dst_node_id": "vision_llm",
      "mappings": [
        { "src_field": "vision_prompt", "dst_field": "user_prompt" },
        { "src_field": "all_images", "dst_field": "image_input_url_or_base64" }
      ]
    }
  ]
}
```

### 5.2. Basic Text Prompt Example

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
            "user_custom_instructions": "Maintain a professional tone, but be friendly. Avoid excessive formality." // Additional instructions for LLM
            // city will use P2 (global option)
          }
        },
        "global_construct_options": { // P2 Sources
          "city": "user_profile.address.city"
        }
      }
      // Output will automatically include: email_subject, email_body, prompt_template_errors
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
        // The node will automatically have access to this data for construct_options paths
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
    // Handle errors (automatically available)
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
    *   **Dynamic Load:** Use `template_load_config` to load templates from the database.
-   **Add Custom Instructions:** Use `user_custom_instructions` to append specialized guidance for the LLM without changing the base template. These appear after your template with a clear "Additional User Instructions" section.
-   **Tell it *Where* to Find Input Values (Highest Priority):**
    *   `construct_options`: Inside a specific task (`id`), map a `{variable}` to a specific location in the input data (e.g., tell it `{user_name}` is found at `user_profile.name`). This wins over everything else for *that task*.
    *   `global_construct_options`: Map variables to input locations as a fallback for *all* tasks if they don't have a specific `construct_options` for that variable.
-   **Alternatively, Provide Input Values *Directly* (Lower Priority):**
    *   Use edges to map values *directly* to the node.
    *   Map to `TEMPLATE_ID.VARIABLE_NAME` (e.g., `final_greeting.user_name`) to set it just for that template (Priority 3).
    *   Map to `VARIABLE_NAME` (e.g., `user_name`) to set it for all templates (Priority 4).
    *   **Important:** These direct mappings are *lower* priority than `construct_options`.
-   **Defaults (Lowest Priority):** If no input is found via the methods above, the node uses the prepared defaults for the template (P5). For dynamically loaded templates, loaded defaults are combined with and can be overridden by `variables` in the node config.
-   **Connect Inputs:** Use edges to feed the *data structures* needed for `construct_options` lookups (e.g., map the whole `user_profile` object) and any direct inputs (P3/P4). The node automatically receives all mapped data.
-   **Connect Outputs:** Use edges to take the finished prompts (using the template `id` as the `src_field`) and `prompt_template_errors` to the next nodes. All template IDs automatically become available output fields. Image outputs (`{template_id}_images` and `all_images`) are also automatically available when templates include images.

### Dynamic Loading Tips for Non-Coders

- You can reference the template name/version from upstream node output using dot paths in `path_config`.
- If you don't specify a version, the node picks the latest available version automatically.
- Your workflow runtime must include application and external context; if missing, dynamic templates won’t load and errors will be surfaced in `prompt_template_errors` (when that field is declared).

### Image Support for Non-Coders:

-   **Add Images to Templates:** Each template can include images in two ways:
    *   **Static Images:** List image URLs or base64 data directly in `static_images` (e.g., company logos, instruction diagrams that are always the same).
    *   **Dynamic Images:** Use `image_collection_paths` to tell the node where to find images in the input data (e.g., user uploaded photos, profile pictures).
-   **Image Paths Work Like Variable Paths:** Use dot notation to specify where images are located (e.g., `user_data.profile_photo` for a single image, `uploads.documents` for a list of images).
-   **Automatic Image Processing:** The node automatically:
    *   Combines images from static and dynamic sources
    *   Removes duplicate images 
    *   Filters out invalid/broken image URLs
    *   Creates organized output fields for downstream nodes
-   **Image Output Fields:** The node automatically creates:
    *   `{template_id}_images`: Images specific to each template (when `separate_images_by_template: true`)
    *   `all_images`: All images from all templates combined (always created when images are present)
-   **Connect Images to Vision LLMs:** Use edges to map image outputs to LLM nodes that support vision:
    *   Map `all_images` → `image_input_url_or_base64` for the LLM node
    *   The LLM will receive both your constructed prompt and all collected images