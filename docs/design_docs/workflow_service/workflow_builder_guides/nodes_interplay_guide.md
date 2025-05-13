# Guide: Making Workflow Nodes Work Together

This guide explains how different nodes in the workflow system connect and interact to create automated processes. Understanding how data flows and how nodes are configured is key to building effective workflows.

## 1. The Big Picture: Workflows as Graphs

Think of a workflow as a flowchart or a graph:

-   **Nodes:** These are the individual steps or actions in your workflow. Each node performs a specific task, like getting input, calling an AI, filtering data, waiting for human review, or producing output.
-   **Edges:** These are the connections or arrows between nodes. They define the sequence of steps and, crucially, how data is passed from one node to the next.

The entire structure – the nodes and their connections – is defined in a configuration file called the **`GraphSchema`**. This schema is the blueprint for your workflow.

## 2. Nodes: The Building Blocks

Each node in your workflow needs to be defined within the `GraphSchema`'s `nodes` section.

```json
{
  "nodes": {
    "a_unique_node_id": {  // <<< You choose a unique ID for this specific instance
      "node_id": "a_unique_node_id", // <<< Must match the key above
      "node_name": "type_of_node",   // <<< Specifies the node's function (see below)
      "node_config": { /* ... specific settings for this node ... */ }
    },
    "another_node_id": { /* ... definition for another node ... */ }
    // ... more nodes
  },
  // ... edges, input/output node definitions ...
}
```

-   **`node_id`**: This is a unique name *you give* to this specific instance of a node in your workflow (e.g., `get_user_email`, `summarize_report`, `human_approval_step`). It must match the key used in the `nodes` dictionary.
-   **`node_name`**: This tells the system *what kind* of node it is. It corresponds to a registered node type. You must use the correct `node_name` for the node to function as intended.
-   **`node_config`**: This dictionary holds the specific settings required by that particular `node_name`. For example, an `llm` node needs model details, a `filter_data` node needs filter conditions, etc. Refer to the specific node's guide for its configuration options.

**Available Node Types (`node_name`)**

Here are the core node types available for building workflows (refer to their individual guides for detailed configuration):

*   **Core & Flow:**
    *   `input_node`: Defines the starting point and initial data requirements. ([Guide](nodes/core_dynamic_nodes_guide.md))
    *   `output_node`: Defines the final output structure. ([Guide](nodes/core_dynamic_nodes_guide.md))
    *   `filter_data`: Selectively keeps or removes data based on conditions. ([Guide](nodes/filter_node_guide.md))
    *   `if_else_condition`: Evaluates conditions to decide between `true_branch` or `false_branch` outputs (used with a Router). ([Guide](nodes/if_else_node_guide.md))
    *   `hitl_node__default` (or other `hitl_*`): Pauses for human input or review. ([Guide](nodes/hitl_node_guide.md))
*   **Routing:**
    *   `router_node`: Routes workflow to different next steps based on simple data equality checks. ([Guide](nodes/dynamic_router_node_guide.md))
    *   `map_list_router_node`: Distributes items from a list to other nodes for individual processing (often in parallel). Supports batching items before sending and optionally wrapping them in a named field. ([Guide](nodes/map_list_router_node_guide.md))
*   **Data Operations:**
    *   `transform_data`: Restructures or renames data fields. ([Guide](nodes/transform_node_guide.md))
    *   `data_join_data`: Combines data from different sources based on matching keys. ([Guide](nodes/data_join_node_guide.md))
    *   `merge_aggregate`: Merges multiple data objects based on configurable strategies for mapping, conflict resolution, and transformation. Supports sequential transformations on non-dictionary results. ([Guide](nodes/merge_aggregate_node_guide.md))
*   **Data Storage:**
    *   `load_customer_data`: Fetches existing data records from storage using static or dynamic path resolution (including patterns based on input metadata). ([Guide](nodes/load_customer_data_node_guide.md))
    *   `store_customer_data`: Saves workflow data back into storage using static or dynamic path resolution (including patterns based on input metadata). ([Guide](nodes/store_customer_data_node_guide.md))
    *   `load_multiple_customer_data`: Lists and loads multiple documents based on criteria like namespace, shared status, and pagination. ([Guide](nodes/load_multiple_customer_node_guide.md))
*   **LLM & Prompts:**
    *   `prompt_constructor`: Builds text prompts using templates and variables. Can define templates statically (`template`) or load them dynamically from the database (`template_load_config`). Supports sourcing variables via input paths (`construct_options`) or direct mappings. ([Guide](nodes/prompt_constructor_node_guide.md))
    *   `llm`: Interacts with Large Language Models (like GPT, Claude, Gemini), supporting text/structured output, tool calling, and web search. ([Guide](nodes/llm_node_guide.md))
*   **External Services:**
    *   `linkedin_scraping`: Executes configured scraping `jobs` (like profile fetch, post search) via an external service. Uses `InputSource` for dynamic parameters, supports `expand_list` for batch jobs, and has a `test_mode`. Consumes API credits. ([Guide](nodes/linkedin_scraping_node_guide.md))
*   *Deprecated:* `load_prompt_templates` (Functionality merged into `prompt_constructor`).

*(Refer to `services/workflow_service/services/db_node_register.py` for the authoritative list of registered nodes.)*

## 3. Edges: Connecting Nodes and Passing Data

Edges define how nodes are connected and how data flows between them. They are defined in the `GraphSchema`'s `edges` list.

```json
{
  // ... nodes definition ...
  "edges": [
    {
      "src_node_id": "node_that_produces_data", // ID of the node sending data
      "dst_node_id": "node_that_needs_data",   // ID of the node receiving data
      "mappings": [ // Instructions on WHICH data to send
        {
          "src_field": "output_field_name", // Name of the data field from the source node's output
          "dst_field": "input_field_name"   // Name this data should have in the target node's input
        },
        { /* ... more mappings ... */ }
      ]
    },
    { /* ... definition for another edge ... */ }
  ],
  // ... input/output node definitions ...
}
```

-   **`src_node_id`**: The `node_id` of the node where the data originates.
-   **`dst_node_id`**: The `node_id` of the node that will receive the data.
-   **`mappings`**: This optional list is crucial for controlling data flow. Each item (`EdgeMapping`) specifies:
    *   **`src_field`**: The name of a field in the `src_node_id`'s output data. You can use dot notation (`.`) for nested fields (e.g., `user_profile.email`).
    *   **`dst_field`**: The name that this data should have when it arrives as input for the `dst_node_id`. This is how you connect the output of one node to the expected input of another. This can also include the template-specific mapping syntax (`TEMPLATE_ID.VARIABLE_NAME`) for nodes like `PromptConstructorNode`.

**What if `mappings` is empty or omitted?**

-   This often implies that the connection is primarily for control flow (ensuring one node runs after another) or that the destination node might read data from a central workflow state or use internal mechanisms (like `construct_options` in `PromptConstructorNode`) to find its data. However, relying on specific data transfer usually requires explicit mappings for clarity and robustness.

**Special Case: The Central Workflow State (`"$graph_state"`)**

-   Think of the workflow having a shared **memory** or **scratchpad** that nodes can write to and read from throughout the process. This shared memory is accessed using the special node ID `"$graph_state"`.
-   Using this shared memory is essential when data needs to be available across different steps that aren't directly connected, or when information needs to be remembered between loops (like in the AI review example).
-   **Writing to Shared Memory:** An edge with `src_node_id` as a regular node and `dst_node_id` as `"$graph_state"` saves data *into* the shared memory.
-   **Reading from Shared Memory:** An edge with `src_node_id` as `"$graph_state"` and `dst_node_id` as a regular node reads data *from* the shared memory.
-   **Mappings Still Apply:** Even when interacting with the shared memory, you still use `mappings`. `src_field` specifies the data field from the node (when writing) or the key in the shared memory (when reading). `dst_field` specifies the key in the shared memory (when writing) or the input field name for the node (when reading).

    *Example: Saving a score:* `src_node_id: "calculate_score"`, `dst_node_id: "$graph_state"`, `mappings: [{ "src_field": "final_score", "dst_field": "current_lead_score" }]` (Saves the node's `final_score` into the shared memory under the key `current_lead_score`).
    *Example: Reading the score:* `src_node_id: "$graph_state"`, `dst_node_id: "send_email"`, `mappings: [{ "src_field": "current_lead_score", "dst_field": "score_to_include" }]` (Reads the value associated with `current_lead_score` from shared memory and provides it to the `send_email` node as `score_to_include`).

## 4. Data Schemas: Defining Input and Output

Every node expects data in a certain format (its **input schema**) and produces data in a certain format (its **output schema**).

-   **Static Schemas:** Many nodes have fixed, predefined schemas. For example, the `llm` node always expects inputs like `user_prompt` or `messages_history` and produces known outputs like `content` and `metadata`. You need to use `EdgeMapping` to map data *to* these expected input names and *from* these known output names.
-   **Statically Defined Structured Output:** Some nodes, like `llm`, can be configured to produce *structured* output (JSON) instead of just text. You define the desired structure in the node's `node_config` (using `output_schema`), and the node attempts to format its response accordingly. You then map *from* the fields within this structured output (e.g., `src_field: "structured_output"` - accessing nested fields within `structured_output` via edge mappings might have limitations, check node documentation).
-   **Dynamic Schemas:** Some nodes are flexible and adapt their schemas based on how they are used:
    *   **`InputNode`**: Its *output* schema is defined by the `src_field` names in the `EdgeMapping`s of edges *originating from it*. These `src_field`s become the required inputs for the entire workflow.
    *   **`OutputNode`**: Its *input* schema is defined by the `dst_field` names in the `EdgeMapping`s of edges *pointing to it*. These `dst_field`s define the final output structure of the workflow.
    *   **`HITLNode`**: Similar to Input/Output, its input (data shown to human) and output (data provided by human) schemas are often defined by incoming and outgoing edge mappings, respectively.
    *   **`TransformerNode`**: Its output schema is explicitly constructed based *only* on the `destination_path` fields defined in its `node_config.mappings`. Its input schema is implicitly defined by the `source_path` fields it needs.
    *   **`PromptConstructorNode`**: Its input schema is dynamic, determined by variables marked `null` in config `variables`, fields needed for `template_load_config`, fields needed for `construct_options` path lookups, and fields mapped directly (globally or template-specific). Its output *dictionary* contains fields named after the template `id`s defined in its config for successfully constructed prompts, and *always* includes a `prompt_template_errors` list (which is empty if no errors occurred). The final *validated output object* passed downstream depends on the node's `dynamic_output_schema` definition in the `GraphSchema`, which should include the expected template `id` fields and can optionally include `prompt_template_errors` if downstream nodes need to access it robustly via the validated schema. Explicitly defining `dynamic_input_schema` and `dynamic_output_schema` is highly recommended.
    *   *Deprecated:* `PromptTemplateLoaderNode` (Functionality merged into `prompt_constructor`).
    *   **Other Nodes:** Nodes like `FilterNode`, `IfElseConditionNode`, `RouterNode`, `LoadCustomerDataNode`, `StoreCustomerDataNode`, `DataJoinNode` often adapt based on the field paths (`field`, `input_path`, `source_path`, etc.) mentioned in their `node_config`. They implicitly require these paths to exist in their input data.

**Key Takeaway for Dynamic Nodes:** The `EdgeMapping`s you create connecting *to* or *from* dynamic nodes, along with configurations like `construct_options` or `template_load_config`, play a critical role in defining what data they expect or produce. Explicitly defining `dynamic_input_schema` and `dynamic_output_schema` for such nodes is highly recommended.

## 5. Configuring the Workflow (`GraphSchema`)

The `GraphSchema` brings everything together:

```json
{
  // 1. Define all node instances
  "nodes": {
    "input_node": { "node_id": "input_node", "node_name": "input_node", "node_config": {} },
    "transform_step": { "node_id": "transform_step", "node_name": "transform_data", "node_config": { /* mappings... */ } },
    "output_node": { "node_id": "output_node", "node_name": "output_node", "node_config": {} }
    // ... other nodes
  },
  // 2. Define all connections and data flow
  "edges": [
    {
      "src_node_id": "input_node",
      "dst_node_id": "transform_step",
      "mappings": [ { "src_field": "raw_data", "dst_field": "data_to_transform" } ]
    },
    {
      "src_node_id": "transform_step",
      "dst_node_id": "output_node",
      "mappings": [ { "src_field": "transformed_data", "dst_field": "final_result" } ]
    }
    // ... other edges
  ],
  // 3. Specify the official start and end points
  "input_node_id": "input_node",
  "output_node_id": "output_node",
  // 4. Optional metadata (e.g., for central state reducers)
  "metadata": { /* ... */ }
}
```

-   Ensure every `node_id` used in `edges`, `input_node_id`, or `output_node_id` exists as a key in the `nodes` dictionary.
-   Make sure the `node_name` corresponds to a valid, registered node type.
-   Carefully define `EdgeMapping`s to ensure data flows correctly between nodes, matching source output fields to destination input fields. Consider all input sources for complex nodes like `PromptConstructorNode` (direct mappings, `construct_options` paths).

## 6. Common Interaction Patterns

Here are examples of how nodes work together:

-   **Simple Data Transformation:**
    `InputNode` -> `TransformerNode` -> `OutputNode`
    *   `InputNode` defines workflow inputs (e.g., `raw_customer_data`).
    *   Edge maps `raw_customer_data` from `InputNode` to the `TransformerNode`.
    *   `TransformerNode` config maps fields from `raw_customer_data` to a new structure (e.g., `simplified_profile`).
    *   Edge maps `transformed_data` (output of transformer) to `OutputNode`.
    *   `OutputNode` defines the final output (e.g., `simplified_profile`).

-   **Conditional Routing:**
    `SomeNode` -> `IfElseConditionNode` -> `RouterNode` -> (`BranchA_Node` OR `BranchB_Node`)
    *   `IfElseConditionNode` evaluates complex conditions based on data from `SomeNode`.
    *   Edge maps `IfElseConditionNode`'s `branch` output (either `"true_branch"` or `"false_branch"`) to `RouterNode`.
    *   `RouterNode` config checks the incoming `branch` value and routes to `BranchA_Node` if `"true_branch"`, else to `BranchB_Node`.
    *   Edges exist from `RouterNode` to both `BranchA_Node` and `BranchB_Node`, but only one path is taken per run (unless `allow_multiple: true`).

-   **AI Content Generation & Review Loop:**
    `InputNode` -> `AIGeneratorNode` -> `HumanReviewNode` -> `ApprovalRouterNode` --(yes)--> `FinalProcessorNode`
                     ^                                                |
                     |-------------------(no)--------------------------|
    *   `AIGeneratorNode` (often an `llm` node) generates content (potentially using `PromptConstructorNode` first). It might produce text or structured output.
    *   `HumanReviewNode` (HITL) presents content, gets `approved` status ("yes"/"no") and `review_comments`.
    *   `ApprovalRouterNode` checks the `approved` status.
    *   If "yes", routes to `FinalProcessorNode`.
    *   If "no", routes back to `AIGeneratorNode` (passing `review_comments` potentially via the central state `"$graph_state"`).

-   **Loading Prompts and Generating Content:**
    `InputNode` -> `PromptConstructorNode` -> `LLMNode`
    *   `InputNode` provides data needed for template variables and/or dynamic template loading/`construct_options` paths (as defined in `PromptConstructorNode`'s `dynamic_input_schema`).
    *   `PromptConstructorNode` defines templates statically (`template`) *or* configures dynamic loading (`template_load_config`) and sources variables according to its priority rules (construct options, direct mappings, defaults). It outputs constructed prompts (named by template `id`) and a `prompt_template_errors` list.
    *   Edge maps the constructed prompt output field(s) (e.g., `src_field: "final_user_prompt"`) to the `LLMNode` (e.g., `dst_field: "user_prompt"`).
    *   Edge can optionally map the `prompt_template_errors` field to another node for error handling.
    *   Edges provide necessary inputs to `PromptConstructorNode`.
    *   `LLMNode` executes the prompt.

-   **Fetching External Data (LinkedIn Example):**
    `InputNode` -> `LinkedInScrapingNode` -> `OutputNode`
    *   `InputNode` provides necessary inputs (e.g., `list_of_usernames`, `company_target`).
    *   Edges map these inputs to the `LinkedInScrapingNode`.
    *   `LinkedInScrapingNode` `node_config` defines `jobs` (e.g., scrape profiles for the list, get company posts). Jobs specify how to use inputs (e.g., `input_field_path`, `expand_list`) and where to place results (`output_field_name`).
    *   Edge maps the results (e.g., `src_field: "scraping_results.user_profiles"`) to the `OutputNode` (e.g., `dst_field: "linkedin_profiles"`).

-   **Fetching and Combining Data:**
    `InputNode` -> `LoadCustomerDataNode` -> `DataJoinNode` -> `OutputNode`
    *   `InputNode` provides an ID (e.g., `user_id`).
    *   `LoadCustomerDataNode` uses `user_id` to fetch `user_profile` and maybe `user_orders` documents.
    *   `DataJoinNode` config joins `user_orders` onto the `user_profile` based on `user_id`.
    *   Edge maps the `mapped_data` (output of joiner) to the `OutputNode`.

-   **Processing List Items:**
    `LoadCustomerDataNode` -> `MapListRouterNode` -> (`ProcessItemNode` & `LogItemNode`)
    *   `LoadCustomerDataNode` fetches a list (e.g., `product_list`).
    *   `MapListRouterNode` config specifies `source_path: "product_list"` and `destinations: ["ProcessItemNode", "LogItemNode"]`. May also specify `batch_size` and `batch_field_name`.
    *   Crucially, edges from `MapListRouterNode` to `ProcessItemNode` and `LogItemNode` define how *each item* is mapped (e.g., sending `item.id` and `item.price` to `ProcessItemNode`).
    *   `ProcessItemNode` and `LogItemNode` likely run with `private_input_mode: true` to handle items/batches independently/in parallel.

-   **Merging Multiple Data Sources:**
    (`SourceANode` & `SourceBNode`) -> `MergeAggregateNode` -> `OutputNode`
    *   `SourceANode` and `SourceBNode` produce data objects (e.g., `crm_data`, `activity_data`).
    *   Edges map these outputs to the `MergeAggregateNode`.
    *   `MergeAggregateNode` `node_config` defines one or more `operations` with `select_paths` pointing to the input data (`crm_data`, `activity_data`).
    *   The `merge_strategy` within the operation specifies how to map fields, resolve conflicts (e.g., keep newest, sum values, extend lists), and potentially transform the result (including sequential non-dictionary transforms).
    *   Edge maps the desired output field from `MergeAggregateNode`'s `merged_data` (e.g., `src_field: "merged_data.consolidated_record"`) to the `OutputNode`.

## 7. Tips for Building Workflows

-   **Plan Your Flow:** Sketch out the steps and decisions like a flowchart before configuring the `GraphSchema`.
-   **Use Clear IDs:** Give your `node_id`s meaningful names (e.g., `summarize_meeting_notes`, `check_if_urgent`).
-   **Map Data Carefully:** Double-check `src_field` and `dst_field` in your `EdgeMapping`s. Ensure the source node actually produces that `src_field`. Ensure the destination node receives all required inputs, considering direct mappings, central state, and internal mechanisms like `construct_options` (which require the *container* object holding the path to be mapped).
-   **Consult Node Guides:** Each node type has specific configuration options and behaviors. Always refer to the relevant guide (linked above).
-   **Start Simple, Iterate:** Build a basic version of your workflow first, test it, and then add complexity.
-   **Use `PromptConstructorNode` for Prompts:** Prefer using the `PromptConstructorNode` for defining static prompts, loading/constructing dynamic prompts, and sourcing variables from various inputs.
-   **Understand Dynamic Nodes:** Remember that for Input, Output, HITL, and PromptConstructor nodes, the connected edges and explicit schema definitions (`dynamic_input_schema`, `dynamic_output_schema`) are crucial for defining their data requirements and outputs.
-   **Test with Examples:** Run your workflow with different kinds of input data to ensure it handles various scenarios correctly.

By understanding how nodes, edges, mappings, and schemas work together within the `GraphSchema`, you can build powerful and flexible automated workflows. Remember to consult the individual node guides for specific configuration details.
