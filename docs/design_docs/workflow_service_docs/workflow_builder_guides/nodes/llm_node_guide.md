# Usage Guide: LLMNode

This guide explains how to configure and use the `LLMNode` to integrate Large Language Models (LLMs) like OpenAI's GPT, Anthropic's Claude, Google's Gemini, or others into your workflows.

## Purpose

The `LLMNode` allows you to:
-   Send prompts and conversation history to an LLM.
-   Configure various model parameters (temperature, max tokens, etc.).
-   Enable advanced features like reasoning modes (for supported models).
-   Receive text responses from the model.
-   (Optional) Receive structured data (JSON) based on a predefined schema.
-   (Optional) Enable the LLM to use "tools" (other nodes in your workflow or provider-inbuilt capabilities).
-   (Optional) Enable the LLM to perform web searches (for supported models).

## Configuration (`NodeConfig`)

The `LLMNode` has a rich set of configuration options nested within the `node_config` field.

```json
{
  "nodes": {
    "my_llm_call": {
      "node_id": "my_llm_call", // Unique ID for this node instance
      "node_name": "llm",      // ** Must be "llm" **
      "node_config": {
        // --- Core LLM Settings ---
        "llm_config": {
          "model_spec": {
            // See llm_node.py/config.py for specific enum values
            "provider": "openai",   // e.g., "openai", "anthropic", "google_genai", "perplexity", "fireworks", "aws_bedrock"
            "model": "gpt-4-turbo" // e.g., "gpt-4-turbo", "claude-3-7-sonnet-20250219", "gemini-2.5-pro-exp-03-25", "sonar-reasoning-pro"
          },
          "temperature": 0.5,       // 0.0 (deterministic) to 1.0+ (creative)
          "max_tokens": 1024,       // Max tokens in the *response* (check model limits)
          // --- Reasoning (Optional, Model-Dependent) ---
          "reasoning_effort_class": null, // e.g., "low", "high" (OpenAI O1/O3 Mini, Fireworks)
          "reasoning_effort_number": null, // e.g., 50 (Fireworks, range 0-20000)
          "reasoning_tokens_budget": null, // e.g., 1000 (Anthropic Claude 3.7+)
          "force_temperature_setting_when_thinking": false, // Usually keep false; thinking often requires temp=1.0
          // --- Other ---
          "kwargs": {}              // Optional extra provider-specific parameters (e.g., {"top_p": 0.9})
        },
        "default_system_prompt": "You are a helpful assistant.", // Optional default if no system message in input
        "thinking_tokens_in_prompt": "all", // "all", "latest_message", "none" (Anthropic specific)
        "cache_responses": true,     // NOTE: this is not implemented as of yet! Cache identical requests?
        "api_key_override": null,    // Optional: {"openai": "sk-...", "anthropic": "sk-..."}

        // --- Output Structure ---
        "output_schema": {
          // To get plain text output, omit output_schema entirely, or set its sub-fields (`schema_template_name`, `dynamic_schema_spec`, `schema_definition`) to `null`.
          // --- Methods to define the schema (Use ONLY ONE): ---
          "dynamic_schema_spec": null,   // Example below
          /* Example dynamic_schema_spec:
          "dynamic_schema_spec": {
            "schema_name": "ExtractedInfo",
            "fields": {
              "summary": { "type": "str", "required": true, "description": "A concise summary." },
              "sentiment": { "type": "enum", "enum_values": ["positive", "negative", "neutral"], "required": true },
              "key_points": { "type": "list", "items_type": "str", "required": false }
            }
          }
          */
          "schema_template_name": null, // e.g., "MyRegisteredSchema"
          "schema_template_version": null, // e.g., "1.0"
          "schema_definition": null, // Raw JSON schema
          "convert_loaded_schema_to_pydantic": true
        },
        // "stream": true, // Streaming behavior is typically handled by the graph execution engine

        // --- Tool Calling (Optional, Model-Dependent) ---
        "tool_calling_config": {
          "enable_tool_calling": true, // Set to true to allow tool use
          "tool_choice": null,         // e.g., "any", "auto", or specific tool name to force
          "parallel_tool_calls": true  // Allow model to call multiple tools at once? (Model-dependent)
        },
        "tools": [ // Required if enable_tool_calling is true; example below
          // Example of a custom tool (another node in your workflow)
          { 
            "tool_name": "get_current_weather", 
            "version": "1.0",
            "is_provider_inbuilt_tool": false 
            // For custom tools, control which input fields are exposed to the LLM
            // by how the 'get_current_weather' node's input schema is defined.
            // Fields not for LLM completion should be marked in their own schema.
          },
          // Example of a provider-inbuilt web search tool for OpenAI
          {
            "tool_name": "web_search_preview", // Specific name for OpenAI's inbuilt web search
            "is_provider_inbuilt_tool": true,
            "provider_inbuilt_user_config": { // Corresponds to OpenAIWebSearchToolConfig from openai_tools.py
              "search_context_size": "medium",
              "user_location": {
                "type": "approximate",
                "approximate": { "country": "US", "city": "New York", "region": "NY" }
              }
            }
          },
          // Example of a provider-inbuilt web search tool for Anthropic
          {
            "tool_name": "web_search", // Specific name for Anthropic's inbuilt web search
            "is_provider_inbuilt_tool": true,
            "provider_inbuilt_user_config": { // Corresponds to AnthropicSearchToolConfig from anthropic_tools.py
              "allowed_domains": ["wikipedia.org", "example.com"]
            }
          }
        ],
        /* Example tools structure:
        "tools": [
          // Custom tool (another node in the workflow)
          { 
            "tool_name": "your_custom_tool_node_name", 
            "version": "1.0", // Optional
            "is_provider_inbuilt_tool": false 
          },
          // Provider-inbuilt tool (e.g., web search for OpenAI)
          {
            "tool_name": "web_search_preview", // This is the specific name for OpenAI's web search tool
            "is_provider_inbuilt_tool": true,
            "provider_inbuilt_user_config": { 
              // This structure must match the config schema for the specific inbuilt tool
              // For OpenAIWebSearchTool, this could be OpenAIWebSearchToolConfig fields:
              "search_context_size": "medium", // "low", "medium", "high"
              "user_location": { // Optional UserLocation schema
                  "type": "approximate",
                  "approximate": { "country": "US", "city": "Austin", "region": "Texas" }
              }
            }
          },
          // Provider-inbuilt tool (e.g., web search for Anthropic)
          {
            "tool_name": "web_search", // This is the specific name for Anthropic's web search tool
            "is_provider_inbuilt_tool": true,
            "provider_inbuilt_user_config": {
              // This structure must match AnthropicSearchToolConfig fields:
              "max_uses": 5,
              "allowed_domains": ["example.com", "trusteddomain.org"]
            }
          }
        ]
        */

        // --- Web Search (Optional, Model-Dependent) ---
        "web_search_options": null
        /* Example web_search_options (for models supporting web search like Perplexity/OpenAI):
        "web_search_options": {
          "search_recency_filter": "week", // "day", "week", "month", "year"
          "search_domain_filter": ["example.com", "wikipedia.org"], // Limit search to these sites
          "search_context_size": "medium", // "low", "medium", "high" (controls detail provided to LLM)
          // OpenAI specific:
          "user_location": {
              "type": "approximate",
              "approximate": { "country": "US", "city": "Austin", "region": "Texas" }
          }
        }
        */
      }
      // dynamic_input_schema / dynamic_output_schema are usually null for LLMNode
    }
    // ... other nodes
  }
  // ... other graph properties
}
```

### Key Configuration Sections:

1.  **`llm_config`**:
    *   `model_spec`: **Required**. Specifies the AI `provider` and the exact `model` name. Check `llm_node.py` or `config.py` for available provider/model enums (e.g., `LLMModelProvider.ANTHROPIC`, `AnthropicModels.CLAUDE_3_7_SONNET`).
    *   `temperature`: Controls randomness (0.0 deterministic, ~1.0 creative). **Note:** Models in reasoning/thinking mode often default to or require a high temperature (e.g., 1.0 for Anthropic).
    *   `max_tokens`: Limits the length of the *generated response*. Ensure this is within the model's limits.
    *   `reasoning_effort_class` / `reasoning_effort_number` / `reasoning_tokens_budget`: **Optional & Model-Specific**. Use *only one* of these to enable reasoning modes if the model supports it (see `llm_node.py` metadata or tests). Provide the type supported by the specific model (e.g., budget for Claude 3.7+, class/number for Fireworks, class for OpenAI O1/O3 Mini).
    *   `force_temperature_setting_when_thinking`: (Default: `false`) Tries to use the specified `temperature` even in reasoning mode. Often ineffective, especially for Anthropic which requires 1.0.
    *   `kwargs`: Advanced, provider-specific parameters (e.g., `top_p`, `frequency_penalty`). Use with caution, verify provider documentation.

2.  **`default_system_prompt`**: (Optional) A default instruction if no system message is in the input `messages_history`. Ignored if `messages_history` is provided.

3.  **`thinking_tokens_in_prompt`**: (Anthropic specific) Controls inclusion of Anthropic's internal `<thinking>` messages in subsequent prompts (`all`, `none`, `latest_message`).

4.  **`cache_responses`**: If `true`, identical requests might return cached results. NOTE: this is not implemented as of yet! 

5.  **`api_key_override`**: (Optional) Provide API keys directly, e.g., `{"openai": "sk-..."}`, overriding system settings.

6.  **`output_schema`**: **Crucial for structured output** (getting JSON back instead of just text).
    *   To get plain text output, omit `output_schema` entirely, or set its sub-fields (`schema_template_name`, `dynamic_schema_spec`, `schema_definition`) to `null`.
    *   **Methods to define the schema (Use ONLY ONE):**
        *   **`dynamic_schema_spec` (Recommended for node-specific schemas):** Define the output structure directly within the node config using `fields`. Specify `type` (`str`, `int`, `list`, `enum`, etc.), `required` status, `description`, and type specifics (`items_type` for lists, `enum_values` for enums). See `dynamic_nodes.py:ConstructDynamicSchema` for details.
        *   **`schema_template_name` (Recommended for reusable schemas):** Use a predefined schema registered in the system by its unique `schema_name`. You can optionally specify a `schema_template_version`.
        *   **`schema_definition` (Advanced):** Provide the raw JSON schema definition directly. Use with caution, as validation might be less straightforward.
    *   `convert_loaded_schema_to_pydantic`: (Default: `true`) If loading a schema via `schema_template_name` or `schema_definition` (which are typically JSON schemas), this flag controls whether it's converted to an internal Pydantic model before being used with the LLM. Pydantic models can sometimes offer better compatibility with certain LangChain structured output mechanisms.
    *   **Important Note:** Structured output reliability varies by model. Anthropic models currently use forced tool calling (which can conflict with reasoning modes), while OpenAI/Gemini generally handle JSON mode more directly. Check provider documentation and test thoroughly. See `llm_node.py:LLMStructuredOutputSchema` docstring and `test_basic_llm_workflow.py` for examples.

7.  **`tool_calling_config` & `tools`**: **Optional & Model-Specific**
    *   Set `enable_tool_calling` to `true` to allow the LLM to request execution of other tool nodes on the platform (custom tools) or provider-integrated functionalities (inbuilt tools). Requires model support (check `llm_node.py` `ModelMetadata`).
    *   If enabled, `tools` **must** be a list defining allowed tools. Each item in the list is a `ToolConfig` object with the following fields:
        *   `tool_name`: **Required**.
            *   For *custom tools*: Must exactly match the `node_name` of a registered tool node in the platform that is designed for tool use.
            *   For *provider-inbuilt tools*: Must be the specific name the provider uses for that tool (e.g., `"web_search_preview"` for OpenAI's search, `"web_search"` for Anthropic's search). Check `config.py` or provider documentation.
        *   `version`: (Optional) Specify a custom tool's version.
        *   `is_provider_inbuilt_tool`: (Optional, Default: `false`) Set to `true` if this tool is an internal capability provided by the LLM provider (like web search), rather than a custom workflow node.
        *   `provider_inbuilt_user_config`: (Optional) If `is_provider_inbuilt_tool` is `true`, this dictionary allows you to pass configuration specific to that inbuilt tool. The structure of this dictionary must match the configuration schema defined for that tool (e.g., `OpenAIWebSearchToolConfig` for OpenAI's web search, `AnthropicSearchToolConfig` for Anthropic's). See `openai_tools.py` and `anthropic_tools.py` for examples.
    *   **Controlling Field Visibility for Custom Tools**: When defining custom tools (other tool nodes in the platform), it's important to control which of their input fields are exposed to the LLM. This is not done via an `input_overwrites` field directly within the `tools` array of the `LLMNode`'s configuration. Instead, the visibility of fields to the LLM is determined by how the input schema for the custom tool node itself is defined. Fields intended as system-provided or that should not be filled by the LLM must be marked accordingly within their schema (e.g., by ensuring they are not included in the subset of fields passed to the LLM during the tool binding process, typically handled by internal mechanisms like `BaseSchema._is_field_for_llm_tool_call`). The LLM will then not see or be asked to fill these hidden or system-set fields.
    *   `tool_choice`: (Optional) Force the LLM to use a specific tool (`"tool_name"`), any tool (`"any"`), or let it decide (`"auto"`, default). Model-dependent.
    *   `parallel_tool_calls`: (Optional, Default: `true`) Allow the model to request multiple tool calls simultaneously. Model-dependent.

8.  **`web_search_options`**: **Optional & Model-Specific**
    *   Enables and configures LLMs with integrated web search (e.g., Perplexity models, OpenAI Search Preview models). This is an alternative way to enable web search if the provider offers it as a general model option rather than (or in addition to) an inbuilt tool.
    *   `search_recency_filter`: Limit results by age (`day`, `week`, `month`, `year`).
    *   `search_domain_filter`: List of domains to restrict search (e.g., `["arxiv.org"]`).
    *   `search_context_size`: Controls detail level given to LLM (`low`, `medium`, `high`).
    *   `user_location`: (OpenAI specific) Provide location context for better results (see example format).

## Input (`LLMNodeInputSchema`)

Provide input via incoming `EdgeSchema` mappings:

-   **`messages_history`** (List[Message Object]): The recommended way for multi-turn conversations. Provide a list of past message objects (usually from a previous `LLMNode`'s `current_messages` output or manually constructed). Expected format (similar to LangChain Message types): `[{ "type": "human", "content": "..." }, { "type": "ai", "content": "..." }, ...]` including `system` and `tool` types. Overrides `user_prompt` and `system_prompt` if provided.
-   **`user_prompt`** (str, Optional): A simple text prompt. Used if `messages_history` is not provided.
-   **`system_prompt`** (str, Optional): A specific system message for this call. Overrides `default_system_prompt` in the config. Only used if `messages_history` is not provided.
-   **`tool_outputs`** (List[Tool Output Object], Optional): Required if the *previous* turn resulted in `tool_calls` from this LLM. Provide the results here as a list of objects: `[{ "tool_name": "...", "tool_id": "...", "content": "...result...", "status": "success" }, ...]`. Match `tool_id` from the request.

**Note:** At least one of `messages_history`, `user_prompt`, or `tool_outputs` must provide content for the LLM to process.

## Output (`LLMNodeOutputSchema`)

The node produces data matching the `LLMNodeOutputSchema`:

-   **`current_messages`** (List[Message Object]): The updated message list *including* the latest AI response (and potentially thinking/tool call messages). Feed this into the next `LLMNode`'s `messages_history` for conversational context.
-   **`content`** (str or List): The primary textual content of the AI's response. Can be a simple string or sometimes a list containing text and other elements (like thinking steps or tool requests, especially with Anthropic).
-   **`metadata`** (`LLMMetadata`): Information about the call:
    *   `model_name`: Model used.
    *   `token_usage`: Dict with `prompt_tokens`, `completion_tokens`, `total_tokens`, and potentially `reasoning_tokens`, `cached_tokens`. Structure is normalized from provider-specific outputs. See `llm_node.py:_parse_response` and `normalize_metadata_to_openai_format` for details.
    *   `finish_reason`: Why the model stopped (e.g., `stop`, `max_tokens`, `tool_calls`). Normalized where possible.
    *   `latency`: Call duration (seconds).
    *   `response_metadata`: Raw, provider-specific metadata dictionary.
    *   `iteration_count`: (Integer, default 0) Tracks the number of AI responses within the `current_messages` list. Useful for limiting loops or tracking conversation depth.
-   **`structured_output`** (Dict[str, Any] | `null`): If `output_schema` was configured (and the model successfully produced compliant output), this holds the parsed JSON object matching the schema. `null` otherwise or if parsing failed.
-   **`tool_calls`** (List[`ToolCall`] | `null`): If the LLM requested tool calls, this list contains objects with `tool_name`, `tool_input` (arguments dict), and `tool_id`. `null` otherwise. **Note:** Internal calls used by some providers for structured output (e.g., by Anthropic) are filtered out and won't appear here; the result will be in `structured_output`.
-   **`web_search_result`** (`WebSearchResult` | `null`): If web search was used (either via `web_search_options` or an inbuilt search tool), this field contains the results. It includes an optional list of `citations` (each with `url`, `title`, `snippet`, `timestamp`, and `metadata`) and potentially `search_metadata` from the provider. `null` if web search was not used or yielded no results. See `llm_node.py:_parse_search_results` and `_parse_citations_from_response` for parsing logic.

## Example (`GraphSchema`)

```json
// See test_basic_llm_workflow.py for diverse examples using different providers
// and configurations (text, structured, reasoning, web search).

// Simplified example for structured output:
{
  "nodes": {
    "get_prompt": { /* ... provides user_prompt ... */ },
    "extract_info": {
      "node_id": "extract_info",
      "node_name": "llm",
      "node_config": {
        "llm_config": {
          "model_spec": { "provider": "openai", "model": "gpt-4o" },
          "temperature": 0.1
        },
        "output_schema": {
          "dynamic_schema_spec": {
            "schema_name": "ExtractedData",
            "fields": {
              "person_name": { "type": "str", "required": true },
              "company": { "type": "str", "required": false },
              "meeting_summary": { "type": "str", "required": true }
            }
          }
        }
      }
    },
    "save_output": { /* ... consumes structured_output ... */ }
  },
  "edges": [
    {
      "src_node_id": "get_prompt",
      "dst_node_id": "extract_info",
      "mappings": [ { "src_field": "prompt_text", "dst_field": "user_prompt" } ]
    },
    {
      "src_node_id": "extract_info",
      "dst_node_id": "save_output",
      "mappings": [
        // Use '.' delimiter to access nested fields within structured_output
        { "src_field": "structured_output.person_name", "dst_field": "contact_name" },
        { "src_field": "structured_output.company", "dst_field": "account_name" },
        { "src_field": "structured_output.meeting_summary", "dst_field": "notes" },
        // Map the entire metadata object
        { "src_field": "metadata", "dst_field": "llm_metadata" }
        // Note: Mapping directly to nested fields like "metadata.token_usage.total_tokens"
        // in src_field might not be supported currently by the EdgeMapping mechanism.
        // You may need an intermediate node (e.g., a Transformer node) to extract
        // specific nested values from the metadata object if needed.
      ]
    }
  ]
  // ... input_node_id, output_node_id ...
}
```

## Notes for Non-Coders

-   Use `LLMNode` for AI tasks: writing, summarizing, Q&A, extraction, tool selection.
-   **Pick the Right Model:** `model_spec` is key. Consider cost, speed, and features (reasoning, tools, web search, structured output support).
-   **Control Creativity:** Use `temperature` (low=factual, high=creative).
-   **Get Specific Info:** Use `output_schema` (via `dynamic_schema_spec` or `schema_template_name`) to tell the AI *exactly* what fields you want back (e.g., `"email_subject"`, `"priority"`). Leave blank for plain text.
-   **Let AI Use Functions/Tools:** Enable `tool_calling_config` and list allowed `tools`.
    *   For *custom tools* (other workflow nodes), ensure their input schemas are designed to expose only necessary fields to the AI.
    *   For *provider-inbuilt tools* (like web search on some models), set `is_provider_inbuilt_tool: true` and use `provider_inbuilt_user_config` to pass any specific settings for that tool.
-   **Enable Web Search:** Use `web_search_options` for models that support it as a general option (like Perplexity or some OpenAI models), OR configure an inbuilt web search tool via the `tools` array if the provider offers it that way.
-   **Connect Inputs:** Provide `user_prompt` or `messages_history`. If tools ran before this node, connect their results to `tool_outputs`.
-   **Connect Outputs:** Use the results: `content` (text), `structured_output.your_field_name` (specific extracted data - using `.` here *is* supported for structured output), `tool_calls` (to trigger tool nodes), or the whole `metadata` object (which includes `iteration_count` for loop control). To get specific values *from* metadata (like token count), you might need another node step after the LLM. Refer to `test_basic_llm_workflow.py` for many configuration patterns.
