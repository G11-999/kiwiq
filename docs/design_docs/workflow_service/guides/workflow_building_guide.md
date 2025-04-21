# End-to-End Guide: Building Workflows

This guide provides a comprehensive walkthrough on how to design, configure, and build automated workflows using the `GraphSchema`. It covers the fundamental concepts, configuration details, data flow management, and provides practical examples.

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
            "input_docname_field": "user_id" // Get docname from input data
          },
          "output_field_name": "profile_document"
        }
      ]
    },
    // --- Optional Advanced Settings ---
    "private_input_mode": false, // Default: Read from shared state (See Section 8)
    "private_output_mode": false, // Default: Write to shared state (See Section 8)
    "dynamic_input_schema": null, // Usually inferred, see Section 6
    "dynamic_output_schema": null, // Usually inferred, see Section 6
    "enable_node_fan_in": false // Default: Node runs once per trigger (See advanced docs)
  },
  "summarize_profile": { /* ... another node definition ... */ }
  // ... more nodes
}
```

**Key Fields for Each Node:**

-   **`node_id` (String, Required):** A unique identifier *you assign* to this specific instance of the node within this workflow (e.g., `fetch_order_details`, `generate_summary_llm`, `wait_for_manager_approval`). This ID is used in edges to refer to this node. It must match the key in the `nodes` dictionary. **Cannot start with `$`**.
-   **`node_name` (String, Required):** Specifies the *type* of node, determining its function and behavior. This must match a registered node type in the system (e.g., `llm`, `filter_data`, `transform_data`, `hitl_node__default`, `router_node`). Refer to the individual node guides or the `nodes_interplay_guide.md` for a list of available types.
-   **`node_config` (Object, Optional):** A dictionary containing configuration parameters specific to the `node_name`. The structure and required fields within `node_config` vary significantly between node types. **Consult the specific node's guide for details.** Examples:
    *   An `llm` node needs `llm_config` (model, temperature, etc.).
    *   A `filter_data` node needs `targets` defining filter conditions.
    *   A `transform_data` node needs `mappings` defining data restructuring.
    *   A `load_customer_data` node needs `load_paths` specifying which documents to fetch.
-   **`private_input_mode` / `private_output_mode` (Boolean, Optional):** Advanced settings primarily used with `map_list_router_node` for parallel processing. See Section 8.
-   **`dynamic_input_schema` / `dynamic_output_schema` (Object, Optional):** Advanced settings for explicitly defining expected data structures, often used by dynamic nodes like `InputNode`, `OutputNode`, `HITLNode`. Usually, these are inferred from edge mappings. See Section 6.

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
        *   **`dst_field` (String):** The name the data from `src_field` should have when it becomes input for the `dst_node_id`.

**Why are Mappings Important?**

Nodes are often developed independently and have specific expectations for their input data names. Mappings act as adapters, ensuring the output data from one node matches the input requirements of the next.

**What if `mappings` is empty?**

An edge without mappings primarily defines execution order: `dst_node_id` will run after `src_node_id`. The `dst_node_id` might not need direct data from the `src_node_id` (perhaps it reads from the central state, see Section 5), or it might process the entire state passed along implicitly. However, relying on implicit data flow is less clear than using explicit mappings.

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

**c) Central Workflow State (`__GRAPH_STATE__`)**

Workflows often need a shared "memory" or central state accessible by multiple nodes. This is represented by a special node ID (e.g., `__GRAPH_STATE__` or the value of `GRAPH_STATE_SPECIAL_NODE_NAME`).

-   **Writing to Central State:** An edge *from* a regular node *to* `__GRAPH_STATE__` saves data.
    ```json
    {
      "src_node_id": "calculate_score", // Produces { "final_score": 95 }
      "dst_node_id": "__GRAPH_STATE__",
      "mappings": [
        { "src_field": "final_score", "dst_field": "lead_score" } // Store as "lead_score" in state
      ]
    }
    ```
-   **Reading from Central State:** An edge *from* `__GRAPH_STATE__` *to* a regular node retrieves data.
    ```json
    {
      "src_node_id": "__GRAPH_STATE__",
      "dst_node_id": "send_notification", // Needs the lead_score calculated earlier
      "mappings": [
        { "src_field": "lead_score", "dst_field": "score_to_include" }
      ]
    }
    ```
-   **Reducers (Advanced):** The `metadata` section of the `GraphSchema` can define "reducers" for central state fields, specifying how new data should be combined with existing data (e.g., appending to a list like message history). See `test_AI_loop.py` metadata example and LangGraph documentation for details.

## 6. Working with Dynamic Schemas

Some nodes don't have fixed input/output structures but adapt based on connections.

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
-   **`HITLNode`:** Often, the data *shown* to the human is defined by incoming edge mappings (`dst_field`), and the data the human *provides* is defined by outgoing edge mappings (`src_field`). The `HITLNode`'s guide provides more details.
-   **Other Dynamically Configured Nodes:** Nodes like `FilterNode`, `IfElseConditionNode`, `RouterNode`, `Load/StoreCustomerDataNode`, `DataJoinNode`, `PromptConstructorNode`, and `TransformerNode` determine their required inputs based on the field paths specified within their respective `node_config` sections. Ensure the data containing these paths is available to them, either through direct edge mappings or the central state.

## 7. Advanced Pattern: Conditional Logic

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

## 8. Advanced Pattern: Processing Lists in Parallel (`MapListRouterNode`)

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
4.  **Convergence:** Branches running in private mode don't automatically write back to the main central state. Results often need to be collected later using specific state reducers or dedicated aggregator nodes.

*(See the `MapListRouterNode` guide for a detailed example.)*

## 9. Example Workflow: Customer Support Ticket Routing

**Goal:** Receive a support ticket, determine its topic using an LLM, and route it to the correct department.

```json
{
  "nodes": {
    "input_node": { // Receives: { "ticket_id": "...", "ticket_body": "..." }
      "node_id": "input_node", "node_name": "input_node", "node_config": {}
    },
    "build_prompt": {
      "node_id": "build_prompt", "node_name": "prompt_constructor",
      "node_config": {
        "prompt_templates": {
          "topic_tpl": {
            "id": "llm_user_prompt", // Output field name
            "template": "Analyze the following support ticket and determine the primary topic. Choose ONLY ONE from: Billing, Technical, Account, General Inquiry.

Ticket Body:
{body}",
            "variables": { "body": null }
          }
        }
      }
    },
    "determine_topic_llm": {
      "node_id": "determine_topic_llm", "node_name": "llm",
      "node_config": {
        "llm_config": { "model_spec": { "provider": "openai", "model": "gpt-3.5-turbo" }, "temperature": 0.1 },
        "output_schema": { // Expect structured output
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
          { "choice_id": "billing_queue", "input_path": "structured_output::topic", "target_value": "Billing" },
          { "choice_id": "tech_queue", "input_path": "structured_output::topic", "target_value": "Technical" },
          { "choice_id": "account_queue", "input_path": "structured_output::topic", "target_value": "Account" },
          { "choice_id": "general_queue", "input_path": "structured_output::topic", "target_value": "General Inquiry" }
        ]
      }
    },
    "billing_queue": { "node_id": "billing_queue", "node_name": "store_customer_data", "node_config": { /* store ticket in billing namespace */ } },
    "tech_queue": { "node_id": "tech_queue", "node_name": "store_customer_data", "node_config": { /* store ticket in tech namespace */ } },
    "account_queue": { "node_id": "account_queue", "node_name": "store_customer_data", "node_config": { /* store ticket in account namespace */ } },
    "general_queue": { "node_id": "general_queue", "node_name": "store_customer_data", "node_config": { /* store ticket in general namespace */ } }
  },
  "edges": [
    // Input -> Build Prompt
    { "src_node_id": "input_node", "dst_node_id": "build_prompt", "mappings": [ { "src_field": "ticket_body", "dst_field": "body" } ] },
    // Build Prompt -> LLM
    { "src_node_id": "build_prompt", "dst_node_id": "determine_topic_llm", "mappings": [ { "src_field": "llm_user_prompt", "dst_field": "user_prompt" } ] },
    // LLM -> Router (Pass the structured output containing the topic)
    { "src_node_id": "determine_topic_llm", "dst_node_id": "routing_decision", "mappings": [ { "src_field": "structured_output", "dst_field": "structured_output" } ] },
    // LLM -> Store Nodes (Pass original ticket data) - Example using central state or direct pass-through needed
    { "src_node_id": "input_node", "dst_node_id": "__GRAPH_STATE__", "mappings": [ { "src_field": "ticket_id", "dst_field": "current_ticket_id" }, { "src_field": "ticket_body", "dst_field": "current_ticket_body" } ] },
    { "src_node_id": "__GRAPH_STATE__", "dst_node_id": "billing_queue", "mappings": [ { "src_field": "current_ticket_id", "dst_field": "ticket_id" }, { "src_field": "current_ticket_body", "dst_field": "ticket_data" } ] },
    // ... similar edges from __GRAPH_STATE__ to tech_queue, account_queue, general_queue ...
    // Router -> Queue Nodes (Control flow only)
    { "src_node_id": "routing_decision", "dst_node_id": "billing_queue" },
    { "src_node_id": "routing_decision", "dst_node_id": "tech_queue" },
    { "src_node_id": "routing_decision", "dst_node_id": "account_queue" },
    { "src_node_id": "routing_decision", "dst_node_id": "general_queue" }
  ],
  "input_node_id": "input_node",
  // Output node determined by which store node runs last
  "output_node_id": "general_queue" // Example, depends on actual implementation (could use a dedicated OutputNode collecting status)
}
```

## 10. Example Workflow: Data Enrichment and Summarization

**Goal:** Load user data, load related company data, join them, filter out inactive users, and generate a summary using an LLM.

```json
{
  "nodes": {
    "input_node": { // Receives: { "user_ids": ["u1", "u2", ...] }
      "node_id": "input_node", "node_name": "input_node", "node_config": {}
    },
    "load_users": { // Load user data for each ID
      "node_id": "load_users", "node_name": "load_customer_data",
      "node_config": {
        "load_paths": [
          {
            "filename_config": { "static_namespace": "users", "input_docname_field": "user_id" }, // Need to iterate or use MapListRouter first
            "output_field_name": "user_profile" // This config needs refinement for list processing
          }
        ]
      },
      // NOTE: This node needs modification or a MapListRouter before it to handle a list of IDs.
      // For simplicity, assume it outputs a list: { "user_profiles": [ { "id": "u1", ... }, ... ] }
    },
    "load_companies": { // Load company data
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
            "join_type": "one_to_one"
          }
        ]
      }
    },
    "filter_inactive": {
      "node_id": "filter_inactive", "node_name": "filter_data",
      "node_config": {
        "targets": [
          {
            "filter_target": "mapped_data.user_profiles", // Filter items in the list produced by join_data
            "filter_mode": "allow", // Keep only active users
            "condition_groups": [ { "conditions": [ { "field": "status", "operator": "equals", "value": "active" } ] } ]
          }
        ]
      }
    },
    "build_summary_prompt": {
      "node_id": "build_summary_prompt", "node_name": "prompt_constructor",
      "node_config": {
        "prompt_templates": {
          "summary_tpl": {
            "id": "summary_prompt",
            "template": "Summarize the key information for the following active users:
{user_data_json}",
            "variables": { "user_data_json": null }
          }
        }
      }
    },
    "generate_summary": {
      "node_id": "generate_summary", "node_name": "llm",
      "node_config": { "llm_config": { "model_spec": { "provider": "openai", "model": "gpt-4-turbo" } } }
    },
    "output_node": { // Outputs: { "summary": "..." }
      "node_id": "output_node", "node_name": "output_node", "node_config": {}
    }
  },
  "edges": [
    // Assume InputNode provides user_ids list... need MapListRouter or modified Load node
    // For simplicity, let's assume load_users/load_companies provide the needed lists directly
    { "src_node_id": "load_users", "dst_node_id": "join_data", "mappings": [ { "src_field": "user_profiles", "dst_field": "user_profiles" } ] },
    { "src_node_id": "load_companies", "dst_node_id": "join_data", "mappings": [ { "src_field": "company_list", "dst_field": "company_list" } ] },
    // Joiner -> Filter
    { "src_node_id": "join_data", "dst_node_id": "filter_inactive", "mappings": [ { "src_field": "mapped_data", "dst_field": "mapped_data" } ] },
    // Filter -> Prompt Builder (Need to stringify JSON)
    // Requires a transform step here to convert filtered_data.mapped_data.user_profiles list to JSON string
    // { "src_node_id": "filter_inactive", "dst_node_id": "build_summary_prompt", "mappings": [ { "src_field": "filtered_data", "dst_field": "user_data_json" } ] }, // Simplification
     // Assuming a transform step exists: transform_to_json
    { "src_node_id": "filter_inactive", "dst_node_id": "transform_to_json", "mappings": [ { "src_field": "filtered_data", "dst_field": "input_data" } ] },
    { "src_node_id": "transform_to_json", "dst_node_id": "build_summary_prompt", "mappings": [ { "src_field": "json_string", "dst_field": "user_data_json" } ] },
    // Prompt Builder -> LLM
    { "src_node_id": "build_summary_prompt", "dst_node_id": "generate_summary", "mappings": [ { "src_field": "summary_prompt", "dst_field": "user_prompt" } ] },
    // LLM -> Output
    { "src_node_id": "generate_summary", "dst_node_id": "output_node", "mappings": [ { "src_field": "content", "dst_field": "summary" } ] }
  ],
  "input_node_id": "input_node",
  "output_node_id": "output_node"
}
```
*(Note: The list processing in Example 2 requires careful handling, potentially using `MapListRouterNode` before `LoadCustomerDataNode` or modifying `LoadCustomerDataNode` to handle list inputs directly. The example simplifies this for clarity.)*

## 11. Tips and Best Practices

-   **Plan First:** Sketch your workflow logic before writing the JSON. Identify steps, decisions, and data needs.
-   **Use Meaningful IDs:** Choose descriptive `node_id`s (e.g., `extract_invoice_data`, `route_by_amount`), IDs also help to identify and differentiate the same node type used multiple times in a workflow.
-   **Consult Node Guides:** Each node has unique `node_config` requirements and specific input/output fields. Refer to the guides constantly.
-   **Validate Mappings:** Ensure `src_field` exists in the source node's output and `dst_field` matches the destination node's expected input or is handled dynamically. Check dot notation carefully.
-   **Start Simple:** Build and test core paths first, then add complexity like branching, looping, or parallel processing.
-   **Handle Errors:** Consider how your workflow should behave if a node fails (e.g., LLM errors, data not found). LangGraph offers error handling mechanisms.
-   **Central State vs. Direct Mapping:** Use central state (`__GRAPH_STATE__`) when data needs to be accessed by multiple, non-sequential nodes or preserved across loops. Use direct edge mappings for clear, sequential data flow.
-   **Test Thoroughly:** Execute your workflow with various inputs, including edge cases, to ensure it behaves as expected. Use logging and inspect intermediate states.
-   **Keep it Readable:** Add comments to your JSON (if supported by your editor/parser) or maintain separate documentation explaining complex logic.

## 12. Conclusion

Building workflows involves defining nodes (tasks) and edges (connections/data flow) within a `GraphSchema`. By understanding the configuration options for each node type, mastering edge mappings, and leveraging patterns for conditional logic and list processing, you can create sophisticated automations. Always refer to the specific node documentation and start with simpler flows before building complex ones.
