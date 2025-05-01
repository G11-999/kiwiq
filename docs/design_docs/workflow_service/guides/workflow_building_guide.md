# End-to-End Guide: Building Workflows

This guide provides a comprehensive walkthrough on how to design, configure, and build automated workflows using the `GraphSchema`. It covers the fundamental concepts, configuration details, data flow management, runtime context, and provides practical examples.

## 1. Introduction: What is a Workflow?

In this system, a workflow is an automated sequence of tasks designed to achieve a specific goal. Think of it as a digital assembly line or a flowchart where data moves through different processing steps.

-   **Tasks are Nodes:** Each step in the workflow is represented by a **Node**. Nodes perform specific actions like fetching data, transforming it, making decisions, calling AI models, waiting for human input, or storing results.
-   **Connections are Edges:** The sequence and flow of data between nodes are defined by **Edges**. Edges act like wires connecting the output of one node to the input of another.
-   **The Blueprint is `GraphSchema`:** The entire workflow – all its nodes, connections, and overall structure – is defined in a JSON configuration object called the `GraphSchema`. This schema is the master plan that the system reads to execute the workflow.

## 2. Understanding the `GraphSchema` Structure

The `GraphSchema` is the core JSON object defining your workflow. It has several key sections:

```json
// Example GraphSchema Structure
{
  "nodes": {
    // Node definitions go here (Section 3)
  },
  "edges": [
    // Edge definitions go here (Section 4)
  ],
  "input_node_id": "unique_id_for_start_node", // Typically "input_node"
  "output_node_id": "unique_id_for_end_node", // Typically "output_node" or the last processing node
  "metadata": {
    // Optional graph-level settings (e.g., for central state)
  }
}
```

-   **`nodes` (Object):** A dictionary where you define each individual node (task) in your workflow. The key is the unique `node_id` you assign, and the value is the node's configuration object.
-   **`edges` (List):** A list of objects defining the connections between nodes and how data flows along those connections.
-   **`input_node_id` (String):** Specifies the `node_id` of the node that acts as the entry point for the workflow. This node defines the data the workflow expects when it starts. Conventionally, this is often `"input_node"`.
-   **`output_node_id` (String):** Specifies the `node_id` of the node whose output is considered the final result of the entire workflow. Conventionally, this might be `"output_node"`, but it can be any node in the graph.
-   **`metadata` (Object):** Optional section for advanced graph-level configurations, such as defining how data should be combined in the central workflow state (using reducers).

*(See `services/workflow_service/graph/graph.py` for the precise Pydantic model definition.)*

## 3. Defining Nodes: The Workflow Steps

Each task in your workflow is a node, defined within the `nodes` dictionary of the `GraphSchema`.

```json
// Inside GraphSchema.nodes
"nodes": {
  "get_user_profile": { // <<< This is the unique node_id you choose
    "node_id": "get_user_profile", // <<< Must match the key above
    "node_name": "load_customer_data", // <<< Specifies the TYPE of node (its function)
    "node_config": { // <<< Node-specific configuration
      "load_paths": [
        {
          "filename_config": {
            "static_namespace": "user_profiles",
            "input_docname_field": "user_id" // Get docname from input data field (e.g., mapped from input_node)
          },
          "output_field_name": "profile_document"
        }
      ]
      // Note: User/Org context needed by this node comes from runtime_config (See Section 6)
    },
    // --- Optional Advanced Settings ---
    "private_input_mode": false, // Default: Read from shared state (See Section 9)
    "private_output_mode": false, // Default: Write to shared state (See Section 9)
    "dynamic_input_schema": null, // Usually inferred, see Section 7
    "dynamic_output_schema": null, // Usually inferred, see Section 7
    "enable_node_fan_in": false // Default: Node runs once per trigger (See advanced docs)
  },
  "summarize_profile": { /* ... another node definition ... */ }
  // ... more nodes
}
```

**Key Fields for Each Node:**

-   **`node_id` (String, Required):** A unique identifier *you assign* to this specific instance of the node within this workflow (e.g., `fetch_order_details`, `generate_summary_llm`, `wait_for_manager_approval`). This ID is used in edges to refer to this node. It must match the key in the `nodes` dictionary. **Cannot start with `$`**.
-   **`node_name` (String, Required):** Specifies the *type* of node, determining its function and behavior. This must match a registered node type in the system (e.g., `llm`, `filter_data`, `transform_data`, `hitl_node__default`, `router_node`, `prompt_constructor`, `load_customer_data`, `store_customer_data`, `linkedin_scraping`, `merge_aggregate`). Refer to the individual node guides or the `nodes_interplay_guide.md` for a list of available types.
-   **`node_config` (Object, Optional):** A dictionary containing configuration parameters specific to the `node_name`. The structure and required fields within `node_config` vary significantly between node types. **Consult the specific node's guide for details.** Examples:
    *   An `llm` node needs `llm_config` (model, temperature, max_tokens), `output_schema` (for structured output), `tool_calling_config` & `tools` (for tool use), `web_search_options`, etc.
    *   A `filter_data` node needs `targets` defining filter conditions.
    *   A `transform_data` node needs `mappings` defining data restructuring.
    *   A `load_customer_data` node needs `load_paths` specifying which documents to fetch. It implicitly uses the **runtime context** (see Section 6) to determine the user and organization for access control. It supports resolving paths using `input_namespace_field_pattern` and `input_docname_field_pattern` based on other input data.
    *   A `store_customer_data` node needs `store_configs` defining data sources and target locations. It also uses the **runtime context** for access control. It supports resolving paths using `input_namespace_field_pattern` and `input_docname_field_pattern` based on other input data.
    *   A `load_multiple_customer_data` node needs filters (`namespace_filter`, `include_shared`, etc.), pagination (`skip`, `limit`), sorting (`sort_by`, `sort_order`), and an `output_field_name`. It uses runtime context for authorization.
    *   A `prompt_constructor` node needs `prompt_templates` (defining static `template` or dynamic `template_load_config`, `variables` for defaults/requirements, and optionally `construct_options` for path-based variable sourcing) and optionally `global_construct_options` for fallback path sourcing.
    *   A `linkedin_scraping` node needs `jobs` defining scraping tasks (profile info, posts, search). Each job defines parameters (static or dynamic via `InputSource` object, which supports `static_value`, `input_field_path`, and `expand_list`), limits (using system defaults if omitted), and an `output_field_name`. It can be run in `test_mode` to validate configs. See its guide for details on job types, credit consumption, defaults, and the output structure (`execution_summary`, `scraping_results`).
    *   A `merge_aggregate` node needs `operations`. Each operation defines `select_paths` (data sources), an `output_field_name`, and a `merge_strategy` (containing `map_phase`, `reduce_phase`, and optional `post_merge_transformations`) to intelligently combine objects. Supports sequential transformations on non-dictionary results. See its guide for details on strategies and reducers.
    *   *Deprecated:* `load_prompt_templates` node (use `prompt_constructor` with `template_load_config` instead).
-   **`private_input_mode` / `private_output_mode` (Boolean, Optional):** Advanced settings primarily used with `map_list_router_node` for parallel processing. See Section 9.
-   **`dynamic_input_schema` / `dynamic_output_schema` (Object, Optional):** Advanced settings for explicitly defining expected data structures, often used by dynamic nodes like `InputNode`, `OutputNode`, `HITLNode`, `PromptConstructorNode`. Defining these is highly recommended for dynamic nodes. See Section 7.

## 4. Connecting Nodes with Edges: Defining the Flow

Edges are the arrows in your workflow flowchart. They define the sequence and, crucially, how data is passed between nodes. Define them in the `edges` list of the `GraphSchema`.

```json
// Inside GraphSchema.edges
"edges": [
  {
    "src_node_id": "node_A", // The ID of the node SENDING data
    "dst_node_id": "node_B", // The ID of the node RECEIVING data
    "mappings": [ // Optional: Instructions for data transfer
      {
        "src_field": "output_field_from_A", // Field name in Node A's output
        "dst_field": "expected_input_field_in_B" // Name this data will have for Node B
      },
      // --- Using Dot Notation for Nested Data ---
      {
        "src_field": "complex_output.details.primary_email",
        "dst_field": "contact_info.email"
      },
      // --- Mapping a whole object ---
      {
        "src_field": "user_settings", // The entire 'user_settings' object from Node A
        "dst_field": "settings_for_B" // Will arrive as 'settings_for_B' in Node B
      },
      // --- Mapping to a template-specific variable (for PromptConstructorNode) ---
      {
         "src_field": "specific_tone_setting",
         "dst_field": "my_prompt_id::tone" // Sets 'tone' variable only for template with id 'my_prompt_id'
      }
    ]
  },
  // --- An edge for control flow (no data mapping needed) ---
  {
    "src_node_id": "node_B",
    "dst_node_id": "node_C"
    // "mappings" is omitted or empty []
  }
]
```

**Key Fields for Each Edge:**

-   **`src_node_id` (String, Required):** The `node_id` of the node where the connection starts (the data source).
-   **`dst_node_id` (String, Required):** The `node_id` of the node where the connection ends (the data destination).
-   **`mappings` (List[`EdgeMapping`], Optional):** This list defines *which* data fields flow from the source to the destination and what they should be called.
    *   Each object in the `mappings` list requires:
        *   **`src_field` (String):** The name of the field in the output of the `src_node_id`. Use dot notation (`.`) to access nested data (e.g., `customer.address.zip_code`).
        *   **`dst_field` (String):** The name the data from `src_field` should have when it becomes input for the `dst_node_id`. Can use dot notation. Can also use `TEMPLATE_ID::VARIABLE_NAME` format for template-specific inputs (e.g., for `PromptConstructorNode`).

**Why are Mappings Important?**

Nodes are often developed independently and have specific expectations for their input data names. Mappings act as adapters, ensuring the output data from one node matches the input requirements of the next. They are also essential for providing the necessary data structures when a node uses internal path lookups (like `construct_options`).

**What if `mappings` is empty?**

An edge without mappings primarily defines execution order: `dst_node_id` will run after `src_node_id`. The `dst_node_id` might not need direct data from the `src_node_id` (perhaps it reads from the central state or uses mechanisms like `construct_options`), or it might process the entire state passed along implicitly. However, relying on implicit data flow is less clear than using explicit mappings.

## 5. Handling Data Flow

Data is the lifeblood of the workflow. Understanding how it moves is critical.

**a) Basic Data Passing via Mappings:**

As shown above, `EdgeMapping`s are the standard way to pass specific data fields:

```json
// Node A produces: { "result_summary": "...", "status_code": 200 }
// Node B expects: { "summary_text": "...", "outcome": "..." }

// Edge from A to B:
{
  "src_node_id": "node_A",
  "dst_node_id": "node_B",
  "mappings": [
    { "src_field": "result_summary", "dst_field": "summary_text" },
    // Note: status_code is not mapped, so Node B doesn't receive it directly via this edge.
  ]
}
```

**b) Accessing Nested Data:**

Use dot notation (`.`) in `src_field` and `dst_field` to access data within nested objects or lists (using numerical indices for lists):

```json
// Node A produces: { "report": { "details": { "author": "...", "tags": ["urgent", "internal"] } } }
// Node C expects: { "report_author": "...", "first_tag": "..." }

// Edge from A to C:
{
  "src_node_id": "node_A",
  "dst_node_id": "node_C",
  "mappings": [
    { "src_field": "report.details.author", "dst_field": "report_author" },
    { "src_field": "report.details.tags.0", "dst_field": "first_tag" } // Get the first tag
  ]
}
```

**c) Central Workflow State (`"$graph_state"`)**

Workflows often need a shared **memory** or **scratchpad** accessible by multiple nodes throughout the execution. This allows data to persist across steps that aren't directly connected or to manage state during loops (like tracking `iteration_count` from an `LLMNode`'s metadata). This shared memory is accessed using the special node ID `"$graph_state"`.

-   **Writing to Central State:** An edge *from* a regular node *to* `"$graph_state"` saves data into the shared memory.
    ```json
    {
      "src_node_id": "calculate_score", // Produces { "final_score": 95 }
      "dst_node_id": "$graph_state", // Target the shared memory
      "mappings": [
        { "src_field": "final_score", "dst_field": "lead_score" } // Store as "lead_score" in the shared memory
      ]
    }
    ```
-   **Reading from Central State:** An edge *from* `"$graph_state"` *to* a regular node retrieves data from the shared memory.
    ```json
    {
      "src_node_id": "$graph_state", // Read from the shared memory
      "dst_node_id": "send_notification", // Node that needs the stored data
      "mappings": [
        { "src_field": "lead_score", "dst_field": "score_to_include" } // Get "lead_score" from memory, provide as "score_to_include" to the node
      ]
    }
    ```
-   **Important Note on Execution Flow:** Edges originating *from* `"$graph_state"` are solely for **data retrieval**. They **do not** trigger the execution of the destination node (`dst_node_id`). The destination node must still receive an incoming connection from another regular node (or be the `input_node_id`) to be executed as part of the workflow's sequence. Think of reading from `"$graph_state"` as looking up information when the node runs, not as a signal to run.
-   **Reducers (Advanced):** When multiple nodes write to the *same key* in the central state (e.g., adding items to a history list), you might need to define how that data is combined. This is done using "reducers" configured in the `GraphSchema.metadata`. Common reducers include `replace` (last write wins - the default), `add_messages` (for chat history), and `append_list`. See `test_AI_loop.py` or LangGraph documentation for details. If not specified, the default behavior usually replaces the old value.

## 6. Accessing Runtime Context

Beyond the data explicitly passed via edges or stored in the central state (`$graph_state`), nodes often need access to information about the *current execution environment* and *shared services*. This is provided through the **runtime configuration** (`runtime_config`).

**What is `runtime_config`?**

When a workflow is executed (e.g., via the `workflow_execution_flow` in `worker.py`), the system prepares a special `runtime_config` dictionary. This dictionary is automatically passed to the `process` method of every node when it runs. It contains crucial context that nodes can use without requiring explicit mappings in the `GraphSchema`.

**Key Context Items:**

-   **`APPLICATION_CONTEXT_KEY` (`"application_context"`):** This key holds a dictionary containing information specific to the current workflow run.
    *   **`workflow_run_job` (`WorkflowRunJobCreate`):** Contains details like the current `run_id`, `workflow_id`, `owner_org_id`, `triggered_by_user_id`, the initial `inputs` provided to the workflow, and `thread_id`.
    *   **`user` (`User` model):** The fully loaded user object corresponding to `triggered_by_user_id`. This allows nodes to perform actions based on user roles, permissions, or preferences.

-   **`EXTERNAL_CONTEXT_MANAGER_KEY` (`"external_context_manager"`):** This key holds an instance of the `ExternalContextManager`. This manager provides managed access to shared external resources and services.
    *   **Database Connections:** Access to the asynchronous database pool (`db`).
    *   **Service Clients:** Ready-to-use clients for interacting with other services, such as `customer_data_service` (for MongoDB interactions), `rabbit` (for message queue publishing), etc.
    *   **Registries:** Access to registries like `db_registry` (for schema templates, etc.).

**How Nodes Use Runtime Context:**

Nodes needing this information (like `load_customer_data` or `store_customer_data`) retrieve it directly from the `runtime_config` passed to their `process` method.

```python
# Simplified example inside a node's process method
# from workflow_service.config.constants import APPLICATION_CONTEXT_KEY, EXTERNAL_CONTEXT_MANAGER_KEY
# from kiwi_app.auth.models import User
# from kiwi_app.workflow_app.schemas import WorkflowRunJobCreate

async def process(self, input_data, runtime_config, *args, **kwargs):
    if not runtime_config:
        self.logger.error("Missing runtime_config.")
        return # Handle error

    # Retrieve the specific context dictionaries
    app_context = runtime_config.get("configurable", {}).get(APPLICATION_CONTEXT_KEY)
    ext_context = runtime_config.get("configurable", {}).get(EXTERNAL_CONTEXT_MANAGER_KEY)

    if not app_context or not ext_context:
        self.logger.error("Missing required keys in runtime_config.")
        return # Handle error

    # Access information from Application Context
    user: Optional[User] = app_context.get("user")
    run_job: Optional[WorkflowRunJobCreate] = app_context.get("workflow_run_job")

    if not user or not run_job:
        self.logger.error("Missing user or run_job in application context.")
        return # Handle error

    org_id = run_job.owner_org_id
    user_id = user.id
    self.logger.info(f"Node running for Org: {org_id}, User: {user_id}")

    # Access services from External Context Manager
    customer_data_service = ext_context.customer_data_service
    # rabbit_client = ext_context.rabbit

    # Example: Use the service with implicit org/user context
    # (The service uses the provided 'user' object for permission checks)
    try:
        # No need to pass org_id/user_id explicitly to the node config!
        # The service method receives the 'user' object for context.
        document = await customer_data_service.get_unversioned_document(
            org_id=org_id, # org_id is required by the service method signature
            namespace="some_namespace",
            docname="some_doc",
            is_shared=False, # Example flag
            user=user # Pass the user object for authorization checks
        )
        # ... process document ...
    except Exception as e:
        self.logger.error(f"Failed to load document: {e}")

    # ... rest of node logic ...
```

**Benefits of Runtime Context:**

-   **Simpler Graph Schemas:** You don't need to clutter your `GraphSchema` by explicitly passing `user_id`, `org_id`, or service connection details through edges.
-   **Security:** Nodes automatically operate within the correct organizational and user context, simplifying permission enforcement.
-   **Maintainability:** Centralizes access to external services, making it easier to manage connections and configurations.

## 7. Working with Dynamic Schemas

Some nodes don't have fixed input/output structures but adapt based on connections or configuration.

-   **`InputNode`:** Its *output* is defined by the `src_field`s on its outgoing edges. These become the workflow's initial required inputs.
    ```json
    // Edge from InputNode:
    { "src_node_id": "input_node", "dst_node_id": "some_node", "mappings": [ { "src_field": "user_query", "dst_field": "query" } ] }
    // This means the workflow requires an input named "user_query".
    ```
-   **`OutputNode`:** Its *input* is defined by the `dst_field`s on its incoming edges. These define the workflow's final output structure.
    ```json
    // Edge to OutputNode:
    { "src_node_id": "some_node", "dst_node_id": "output_node", "mappings": [ { "src_field": "result", "dst_field": "final_answer" } ] }
    // This means the workflow will output a field named "final_answer".
    ```
-   **`HITLNode`:** Its input (data shown) and output (data provided) schemas are often defined by incoming/outgoing edge mappings.
-   **`LLMNode` with `output_schema`:** While the base `LLMNode` has static I/O fields (`user_prompt`, `content`, `metadata`, etc.), configuring `output_schema` in its `node_config` causes it to produce an additional `structured_output` field whose *content* structure matches your definition. You may map in the future *from* this structured data using `structured_output::field_name`. NOTE: currently mapping is only possible with first level fields in edges, so this type of notation can go in some node's configs to access subfields, but not directly via edges as of now!
-   **`PromptConstructorNode`:** Its input schema is dynamic, derived from several sources: fields needed for `construct_options` path lookups (e.g., if a path is `user.profile.name`, it needs the `user` field mapped), fields needed for dynamic template loading (`input_name_field_path`, `input_version_field_path`), fields mapped directly via edges (globally like `variable_name` or template-specific like `template_id::variable_name`), and variables marked `null` in its config. Its output dictionary *always* contains fields matching the `id` of each successfully constructed template, plus a `prompt_template_errors` list (empty if no errors). The structure of the final *validated output object* passed downstream is determined by the `dynamic_output_schema` defined for the node in the `GraphSchema`. This schema should list the expected template `id` fields and can optionally include `prompt_template_errors`. **It is highly recommended to explicitly define `dynamic_input_schema` and `dynamic_output_schema` for this node in the `GraphSchema` for clarity and validation.**
-   *Deprecated:* `PromptTemplateLoaderNode` (Functionality merged into `prompt_constructor`).
-   **Other Config-Driven Nodes:** Nodes like `FilterNode`, `IfElseConditionNode`, `RouterNode`, `Load/StoreCustomerDataNode`, `DataJoinNode`, `TransformerNode`, `MergeAggregateNode`, and `LinkedInScrapingNode` determine required inputs and/or shape their outputs based on values within their `node_config`. Ensure data for necessary input paths (e.g., `field`, `input_path`, `source_path`, `input_field_path`, `select_paths`) is available via edges or central state. For `LinkedInScrapingNode`, the output structure under `scraping_results` is determined by the `output_field_name` in each configured `job`. For `MergeAggregateNode`, the output structure under `merged_data` is determined by the `output_field_name` in each configured `operation`. Many of these nodes (especially `Load/StoreCustomerDataNode`) also rely on the **runtime context** (see Section 6) for permissions and service access.

## 8. Advanced Pattern: Conditional Logic

Workflows often need to make decisions. This is typically done using an `IfElseConditionNode` combined with a `RouterNode`.

1.  **Evaluate Conditions:** The `IfElseConditionNode` evaluates complex conditions (potentially multiple sets combined with AND/OR logic) based on its input data. See its guide for detailed configuration.
2.  **Output Decision:** It produces an output field named `branch`, whose value will be either the string `"true_branch"` or `"false_branch"`.
3.  **Map Decision to Router:** An edge connects the `IfElseConditionNode` to a `RouterNode`, mapping the `branch` output field to an input field the router will check.
    ```json
    {
      "src_node_id": "my_if_else_node",
      "dst_node_id": "my_router_node",
      "mappings": [ { "src_field": "branch", "dst_field": "decision_result" } ]
    }
    ```
4.  **Configure Router:** The `RouterNode` is configured (see its guide) to check the value of the mapped field (`decision_result` in this case). It defines which `choice_id` (downstream node ID) corresponds to the `"true_branch"` value and which corresponds to the `"false_branch"` value.
    ```json
    // Inside my_router_node node_config:
    "choices_with_conditions": [
      { "choice_id": "node_for_true_path", "input_path": "decision_result", "target_value": "true_branch" },
      { "choice_id": "node_for_false_path", "input_path": "decision_result", "target_value": "false_branch" }
    ]
    ```
5.  **Connect Router Outputs:** Define edges from the `RouterNode` to both potential downstream nodes (`node_for_true_path` and `node_for_false_path`). The execution engine will only follow the path chosen by the router based on the `decision_result`.

## 9. Advanced Pattern: Processing Lists in Parallel (`MapListRouterNode`)

To process each item in a list independently (and potentially in parallel), use the `MapListRouterNode`.

1.  **Configure Mapper:**
    *   Set `node_name` to `map_list_router_node`.
    *   In `node_config`:
        *   Specify the `source_path` to the list/dictionary in the input data.
        *   List the `destinations` (target `node_id`s) where *each item* should be sent.
        *   Include all destinations in the top-level `choices` list.
2.  **Define Item Transformation on Edges:**
    *   Create edges from the `MapListRouterNode` to each destination node.
    *   The `mappings` on *these specific edges* define how *each individual item* from the source list is transformed before being sent to that destination. If mappings are empty, the item is sent as-is.
3.  **Enable Parallelism with Private Modes:**
    *   **Problem:** If multiple instances of a destination node run in parallel and modify the shared central state, they can interfere with each other.
    *   **Solution:**
        *   Set **`private_input_mode: true`** on the **destination nodes** (the ones listed in the mapper's `destinations`). This tells them to get their input directly from the mapper's `Send` command, not the shared state.
        *   If a parallel branch continues further (NodeA -> NodeB, both running per-item), NodeA needs **`private_output_mode: true`** (to send its output directly) and NodeB needs **`private_input_mode: true`** (to receive it directly).
4.  **Convergence / Aggregation:** By default, branches running in private mode don't automatically write their final results back to the *main* shared central state when they finish (they operate in isolated sub-states). However, you *can* explicitly write data back to the central state (`"$graph_state"`) from nodes within these parallel branches. To combine results from multiple parallel runs (e.g., collecting all generated items into a single list), you **must** configure appropriate **reducers** in the `GraphSchema.metadata`. For instance, using an `append_list` reducer on a specific key in `"$graph_state"` allows each parallel branch to add its result to that list, effectively aggregating the output in the central state. Without such reducers, concurrent writes to the same key would likely overwrite each other (default `replace` behavior).

*(See the `MapListRouterNode` guide for a detailed example.)*

## 10. Example Workflow: Customer Support Ticket Routing

**Goal:** Receive a support ticket, determine its topic using an LLM, and route it to the correct department, storing the ticket data using runtime context.

```json
{
  "nodes": {
    "input_node": { // Receives: { "ticket_id": "...", "ticket_body": "..." }
      "node_id": "input_node", "node_name": "input_node", "node_config": {}
    },
    "build_prompt": { // Uses PromptConstructor for loading AND construction
      "node_id": "build_prompt",
      "node_name": "prompt_constructor",
      "node_config": {
        "prompt_templates": {
           "classifier_task": { // Key for organization
             "id": "llm_user_prompt", // Output field name
             "template_load_config": { // Load the template from DB
               "path_config": {
                 "static_name": "support_topic_classifier",
                 "static_version": "1.0"
               }
             },
             "variables": { "body": null } // Mark 'body' as required input
           }
         }
      },
      // Explicit schemas recommended
      "dynamic_input_schema": { "fields": { "body": { "type": "str", "required": true } } },
      "dynamic_output_schema": { "fields": { "llm_user_prompt": { "type": "str", "required": true }, "prompt_template_errors": { "type": "list", "required": false } } }
    },
    "determine_topic_llm": {
      "node_id": "determine_topic_llm", "node_name": "llm",
      "node_config": {
        "llm_config": { "model_spec": { "provider": "openai", "model": "gpt-3.5-turbo" }, "temperature": 0.1 },
        "output_schema": { // Expect structured output matching this spec
          "dynamic_schema_spec": {
            "schema_name": "TopicResult",
            "fields": { "topic": { "type": "enum", "enum_values": ["Billing", "Technical", "Account", "General Inquiry"], "required": true } }
          }
        }
      }
    },
    "routing_decision": {
      "node_id": "routing_decision", "node_name": "router_node",
      "node_config": {
        "choices": ["billing_queue", "tech_queue", "account_queue", "general_queue"],
        "allow_multiple": false,
        "choices_with_conditions": [
          // NOTE: Using structured_output::topic notation requires adapter/node support
          { "choice_id": "billing_queue", "input_path": "topic_from_llm.topic", "target_value": "Billing" },
          { "choice_id": "tech_queue", "input_path": "topic_from_llm.topic", "target_value": "Technical" },
          { "choice_id": "account_queue", "input_path": "topic_from_llm.topic", "target_value": "Account" },
          { "choice_id": "general_queue", "input_path": "topic_from_llm.topic", "target_value": "General Inquiry" }
        ]
      }
    },
    // Store nodes configuration - these use runtime context for org/user and service access
    "billing_queue": {
      "node_id": "billing_queue", "node_name": "store_customer_data",
      "node_config": {
        "store_configs": [{
          "input_field_path": "original_ticket", // Get data from central state
          "target_path": { "filename_config": { "static_namespace": "tickets_billing", "input_docname_field": "original_ticket.id" } }
          // versioning/schema defaults are likely sufficient (upsert unversioned)
        }]
      }
    },
    "tech_queue": {
      "node_id": "tech_queue", "node_name": "store_customer_data",
      "node_config": {
        "store_configs": [{
          "input_field_path": "original_ticket",
          "target_path": { "filename_config": { "static_namespace": "tickets_tech", "input_docname_field": "original_ticket.id" } }
        }]
      }
    },
    "account_queue": {
      "node_id": "account_queue", "node_name": "store_customer_data",
      "node_config": {
        "store_configs": [{
          "input_field_path": "original_ticket",
          "target_path": { "filename_config": { "static_namespace": "tickets_account", "input_docname_field": "original_ticket.id" } }
        }]
      }
    },
    "general_queue": {
      "node_id": "general_queue", "node_name": "store_customer_data",
      "node_config": {
        "store_configs": [{
          "input_field_path": "original_ticket",
          "target_path": { "filename_config": { "static_namespace": "tickets_general", "input_docname_field": "original_ticket.id" } }
        }]
      }
    }
  },
  "edges": [
    // Input -> Build Prompt (Provide the required 'body' variable)
    { "src_node_id": "input_node", "dst_node_id": "build_prompt", "mappings": [ { "src_field": "ticket_body", "dst_field": "body" } ] },
    // Build Prompt -> LLM (Use the 'id' from the config as src_field)
    { "src_node_id": "build_prompt", "dst_node_id": "determine_topic_llm", "mappings": [ { "src_field": "llm_user_prompt", "dst_field": "user_prompt" } ] },
    // LLM -> Router (Map the structured output to a field the router expects)
    { "src_node_id": "determine_topic_llm", "dst_node_id": "routing_decision", "mappings": [ { "src_field": "structured_output", "dst_field": "topic_from_llm" } ] },

    // State management: Store original ticket data in central state for later retrieval by store nodes
    { "src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "ticket_id", "dst_field": "original_ticket.id" },
        { "src_field": "ticket_body", "dst_field": "original_ticket.body" }
        // Add other relevant ticket fields if needed by store nodes
      ]
    },
    // State management: Read original ticket data from central state for store nodes
    // Note: These edges ONLY provide data, they DON'T trigger the store nodes. The router does.
    { "src_node_id": "$graph_state", "dst_node_id": "billing_queue", "mappings": [ { "src_field": "original_ticket", "dst_field": "original_ticket" } ] },
    { "src_node_id": "$graph_state", "dst_node_id": "tech_queue", "mappings": [ { "src_field": "original_ticket", "dst_field": "original_ticket" } ] },
    { "src_node_id": "$graph_state", "dst_node_id": "account_queue", "mappings": [ { "src_field": "original_ticket", "dst_field": "original_ticket" } ] },
    { "src_node_id": "$graph_state", "dst_node_id": "general_queue", "mappings": [ { "src_field": "original_ticket", "dst_field": "original_ticket" } ] },

    // Router -> Queue Nodes (Control flow only, data comes from $graph_state edges above)
    { "src_node_id": "routing_decision", "dst_node_id": "billing_queue" },
    { "src_node_id": "routing_decision", "dst_node_id": "tech_queue" },
    { "src_node_id": "routing_decision", "dst_node_id": "account_queue" },
    { "src_node_id": "routing_decision", "dst_node_id": "general_queue" }
  ],
  "input_node_id": "input_node",
  "output_node_id": "general_queue" // Example end point - could also be a dedicated output node collecting results
}
```

## 11. Example Workflow: Data Enrichment and Summarization

**Goal:** Load user data based on IDs from input, load related company data, join them, filter out inactive users, and generate a summary using an LLM. Runtime context is used by `load_customer_data`.

```json
{
  "nodes": {
    "input_node": { // Receives: { "user_ids": ["u1", "u2", ...], "filter_status": "active" }
      "node_id": "input_node", "node_name": "input_node", "node_config": {}
    },
    "load_users": { // Load user data for each ID (requires MapListRouter or custom logic)
      "node_id": "load_users", "node_name": "load_customer_data",
      "node_config": {
        "load_paths": [
          {
            // Assumes input is {"user_id": "uX"} for each item after mapping/routing
            "filename_config": { "static_namespace": "users", "input_docname_field": "user_id" },
            "output_field_name": "user_profile"
          }
        ]
      },
      // NOTE: This example simplifies list processing. A MapListRouter node would typically precede
      // this node to iterate over 'user_ids' from the input_node, mapping each ID to the
      // 'user_id' field expected by filename_config. This node would then run once per user ID.
      // Output shown below assumes aggregation after parallel runs.
      // Assumed aggregated output: { "user_profiles": [ { "id": "u1", ... }, ... ] }
    },
    "load_companies": { // Load company data (uses runtime context)
      "node_id": "load_companies", "node_name": "load_customer_data",
      "node_config": {
        "load_paths": [ { "filename_config": { "static_namespace": "companies", "static_docname": "all_company_data" }, "output_field_name": "company_list" } ]
      }
    },
    "join_data": {
      "node_id": "join_data", "node_name": "data_join_data",
      "node_config": {
        "joins": [
          {
            "primary_list_path": "user_profiles", // List from load_users output
            "secondary_list_path": "company_list", // List from load_companies output
            "primary_join_key": "company_id", // Field in user profile
            "secondary_join_key": "id", // Field in company data
            "output_nesting_field": "company_info", // Add company data here
            "join_type": "one_to_one" // Or appropriate type
          }
        ],
        "output_field_name": "joined_user_list" // Name of the output list field
      }
    },
    "filter_by_status": { // Filter using status provided in initial workflow input
      "node_id": "filter_by_status", "node_name": "filter_data",
      "node_config": {
        "targets": [
          {
            "filter_target": "joined_user_list", // Input list field name (after mapping)
            "filter_mode": "allow", // Keep matching items
            "condition_groups": [ { "conditions": [ { "field": "status", "operator": "equals", "input_value_path": "status_to_filter" } ] } ] // Compare user status to input value
          }
        ],
         "output_field_name": "filtered_users" // Name of the output field containing the filtered list
      }
    },
    "transform_to_json": { // Node to convert filtered list to JSON string for LLM
      "node_id": "transform_to_json", "node_name": "transform_data", // Assuming a node that can stringify
      "node_config": {
        "mappings": [
          { "source_path": "filtered_users", "destination_path": "user_data_json", "action": "stringify" }
         ]
      }
    },
    "build_summary_prompt": {
      "node_id": "build_summary_prompt",
      "node_name": "prompt_constructor",
      "node_config": {
         "prompt_templates": {
           "summary_task": {
             "id": "summary_prompt", // Output field name
             "template_load_config": { /* ... Config to load template from DB ... */ },
             "variables": { "user_data_json": null } // Mark as required input
           }
         }
      },
      "dynamic_input_schema": { "fields": { "user_data_json": { "type": "str", "required": true } } },
      "dynamic_output_schema": { "fields": { "summary_prompt": { "type": "str", "required": true }, "prompt_template_errors": { "type": "list", "required": false } } }
    },
    "generate_summary": {
      "node_id": "generate_summary", "node_name": "llm",
      "node_config": { "llm_config": { "model_spec": { "provider": "openai", "model": "gpt-4-turbo" } } }
    },
    "output_node": {
      "node_id": "output_node", "node_name": "output_node", "node_config": {}
    }
  },
  "edges": [
    // Input to Load/Filter nodes
    // Note: For list processing, 'input_node' -> MapListRouter -> 'load_users' would be needed.
    // Edges below assume 'load_users' magically handles the list or aggregation occurs.
    { "src_node_id": "input_node", "dst_node_id": "load_users", "mappings": [ { "src_field": "user_ids", "dst_field": "user_ids_list" } ] }, // Simplified
    { "src_node_id": "input_node", "dst_node_id": "filter_by_status", "mappings": [ { "src_field": "filter_status", "dst_field": "status_to_filter" } ] },

    // Data loading and joining
    { "src_node_id": "load_users", "dst_node_id": "join_data", "mappings": [ { "src_field": "user_profiles", "dst_field": "user_profiles" } ] }, // List of loaded profiles
    { "src_node_id": "load_companies", "dst_node_id": "join_data", "mappings": [ { "src_field": "company_list", "dst_field": "company_list" } ] },

    // Joiner -> Filter (Pass the joined list)
    { "src_node_id": "join_data", "dst_node_id": "filter_by_status", "mappings": [ { "src_field": "joined_user_list", "dst_field": "joined_user_list" } ] },

    // Filter -> Transform (Pass the filtered list)
    { "src_node_id": "filter_by_status", "dst_node_id": "transform_to_json", "mappings": [ { "src_field": "filtered_users", "dst_field": "filtered_users" } ] },

    // Transform -> Build Prompt (Provide JSON string)
    { "src_node_id": "transform_to_json", "dst_node_id": "build_summary_prompt", "mappings": [ { "src_field": "user_data_json", "dst_field": "user_data_json" } ] },

    // Prompt Builder -> LLM
    { "src_node_id": "build_summary_prompt", "dst_node_id": "generate_summary", "mappings": [ { "src_field": "summary_prompt", "dst_field": "user_prompt" } ] },

    // LLM -> Output
    { "src_node_id": "generate_summary", "dst_node_id": "output_node", "mappings": [ { "src_field": "content", "dst_field": "final_summary" } ] }
  ],
  "input_node_id": "input_node",
  "output_node_id": "output_node"
}
```
*(Note: Example 2 still simplifies list processing. A `MapListRouterNode` would typically be used before `load_users` to handle the list of `user_ids`.)*

## 12. Tips and Best Practices

-   **Plan First:** Sketch your workflow logic before writing the JSON.
-   **Use Meaningful IDs:** Choose descriptive `node_id`s.
-   **Consult Node Guides:** Each node has unique `node_config` requirements.
-   **Validate Mappings:** Ensure `src_field` exists and `dst_field` matches expectations. For nodes using path lookups (like `construct_options`), ensure the *container object* holding the start of the path is mapped correctly.
-   **Leverage Runtime Context:** Avoid passing user/org IDs via mappings; rely on the runtime context (Section 6) for nodes that need it (e.g., `load/store/load_multiple_customer_data`).
-   **Start Simple:** Build and test core paths first.
-   **Handle Errors:** Consider error paths and logging.
-   **Central State vs. Direct Mapping:** Use central state (`"$graph_state"`) for shared/persistent data, direct mappings for sequential flow.
-   **Test Thoroughly:** Use various inputs and edge cases.
-   **Keep it Readable:** Use comments or separate documentation.
-   **Check Model Capabilities:** Verify LLM features before configuring them.
-   **Check External Service Costs:** Be mindful of nodes like `LinkedInScrapingNode` that consume external resources (like API credits) based on configuration and usage. Use `test_mode` where available for validation without incurring costs.
-   **Use `MergeAggregateNode` for Consolidation:** When needing to combine data from multiple potentially overlapping sources into a single structure with specific rules for conflict resolution (beyond simple joins), use the `MergeAggregateNode`.
-   **Explicit Schemas:** Define `dynamic_input_schema` and `dynamic_output_schema` for nodes like `PromptConstructorNode`, `InputNode`, `OutputNode`, `HITLNode` for better validation and clarity. Note that for `PromptConstructorNode`, `prompt_template_errors` is always present in the internal output dictionary, but defining it in the schema makes it robustly accessible downstream via the validated output object.

## 13. Conclusion

Building workflows involves defining nodes (tasks) and edges (connections/data flow) within a `GraphSchema`. By understanding node configurations (especially the versatile `PromptConstructorNode`), mastering edge mappings, leveraging the runtime context for implicit information like user/org context and service access, and utilizing patterns for logic and data handling, you can create sophisticated automations. Always refer to the specific node documentation and start with simpler flows.

