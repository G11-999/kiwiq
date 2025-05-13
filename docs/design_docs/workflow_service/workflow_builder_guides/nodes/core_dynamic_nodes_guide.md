# Usage Guide: Core Dynamic Nodes (Input & Output)

This guide explains the `InputNode` and `OutputNode`, which are fundamental components for defining the start and end points of your workflows. These nodes are "dynamic" because their exact data fields (schema) are determined by how they are connected to other nodes in the workflow graph, rather than being predefined.

## 1. `InputNode`

### Purpose

The `InputNode` serves as the entry point for your workflow. It defines the initial data that needs to be provided when the workflow starts. Think of it as the "start" button and the form you fill out to kick off a process.

### Configuration (`NodeConfig`)

When defining an Input Node instance in your `GraphSchema`'s `nodes` dictionary:

```json
{
  "nodes": {
    "workflow_start": { // <<< You choose a unique node_id (e.g., "workflow_start")
      "node_id": "workflow_start", // <<< Must match the key above
      "node_name": "input_node",    // <<< Must be "input_node" to specify the InputNode type
      "node_config": {},
      "dynamic_output_schema": null // Usually defined by outgoing edges, but can be specified
    }
    // ... other nodes
  },
  // Crucially, the GraphSchema must point to the chosen node_id:
  "input_node_id": "workflow_start", // <<< Must match the node_id you chose above
  // ... other graph properties
}
```

-   `node_id`: **You choose** a unique identifier for this specific Input Node instance (e.g., `workflow_start`, `data_entry`, or often just `input_node` by convention). This ID must match the key used in the `nodes` dictionary.
-   `node_name`: **Must be `input_node`**. This tells the system to use the `InputNode` implementation.
-   `node_config`: Usually empty `{}`. The `InputNode` doesn't have specific settings you need to configure here.
-   `dynamic_output_schema`: (Optional) While you *can* explicitly define the output fields here using `ConstructDynamicSchema`, it's more common to let the system infer the schema based on the `EdgeSchema` definitions originating from this node. The fields defined by outgoing edges become the expected input data for the workflow.

**Key Point:** The `GraphSchema` object itself has an `input_node_id` field. This field **must** contain the exact `node_id` you assigned to your Input Node instance in the `nodes` dictionary (e.g., `"workflow_start"` in the example above). While the default and common convention is to use `input_node` for both the `node_id` and the `GraphSchema.input_node_id`, you have the flexibility to choose a different ID as long as they match.

### Input & Output

-   **Input:** The `InputNode` *receives* the initial data payload when the workflow is executed. The structure of this payload must match the fields defined by the outgoing edges originating from its `node_id`.
-   **Output:** The `InputNode` *produces* the validated initial data, making it available to the nodes it's connected to via `EdgeSchema` where `src_node_id` matches its `node_id`.

### Example (`GraphSchema`)

Let's say your workflow needs a `user_query` (text) and an `item_id` (number) to start. We'll use the conventional `input_node` ID here for simplicity.

```json
{
  "nodes": {
    "input_node": { // Using "input_node" as the node_id (conventional)
      "node_id": "input_node",
      "node_name": "input_node", // Type identifier
      "node_config": {}
      // Output schema is inferred from edges
    },
    "process_query": {
      "node_id": "process_query",
      "node_name": "some_processing_node", // Replace with actual node name
      "node_config": { // Config for the processing node
          // ...
      }
    }
    // ... other nodes
  },
  "edges": [
    {
      "src_node_id": "input_node", // Referencing the InputNode's ID
      "dst_node_id": "process_query",
      "mappings": [
        { "src_field": "user_query", "dst_field": "query_text" },
        { "src_field": "item_id", "dst_field": "target_item" }
      ]
    }
    // ... other edges
  ],
  // GraphSchema points to the Input Node instance ID
  "input_node_id": "input_node",
  "output_node_id": "workflow_end" // Points to the ID of the designated output node
  // ...
}
```

In this example, when executing the workflow, you would need to provide an input object like:
`{"user_query": "Summarize this document", "item_id": 12345}`.

### Notes for Non-Coders

-   The Input Node defines *what information is needed* to start the workflow. You mark a node as the Input Node by setting its `node_name` to `input_node`.
-   Give this Input Node a unique ID (`node_id`, e.g., `workflow_start`).
-   Tell the overall workflow which node is the starting point by setting the graph's `input_node_id` to match the ID you chose.
-   You don't usually configure the Input Node directly in the `node_config`. Its requirements are set by how you connect it to the *next* steps (nodes) using edges.
-   Each `src_field` in an edge starting from your Input Node's ID represents a piece of data the workflow expects at the beginning.

## 2. `OutputNode`

### Purpose

The `OutputNode` serves as the designated exit point for your workflow. It defines the final data structure that the workflow will produce as its result. Think of it as the final report or outcome of the process.

*(Note: While a specific `OutputNode` instance is common, as seen in `test_AI_loop.py`, a graph can also designate *any* node as its final output via the `GraphSchema.output_node_id`. The data produced by that designated node becomes the graph's result.)*

### Configuration (`NodeConfig`)

When defining an Output Node instance:

```json
{
  "nodes": {
    "workflow_end": { // <<< You choose a unique node_id (e.g., "workflow_end")
      "node_id": "workflow_end", // <<< Must match the key above
      "node_name": "output_node",   // <<< Must be "output_node" to specify the OutputNode type
      "node_config": {},
      "dynamic_input_schema": null // Usually defined by incoming edges, but can be specified
    }
    // ... other nodes
  },
  // The GraphSchema must point to the chosen node_id:
  "output_node_id": "workflow_end", // <<< Must match the node_id you chose above
  // ... other graph properties
}
```

-   `node_id`: **You choose** a unique identifier (e.g., `workflow_end`, `final_result`, or often `output_node` by convention).
-   `node_name`: **Must be `output_node`**. This specifies the `OutputNode` type.
-   `node_config`: Usually empty `{}`.
-   `dynamic_input_schema`: (Optional) You *can* explicitly define the expected input fields using `ConstructDynamicSchema`, but typically, the schema is inferred from the `EdgeSchema` definitions targeting this node's `node_id`. The fields defined by incoming edges become the fields in the final workflow result.

**Key Point:** The `GraphSchema` object has an `output_node_id` field. This field **must** contain the `node_id` you assigned to your Output Node instance (or any other node you wish to designate as the final output). Similar to the input node, using `output_node` for the `node_id` is conventional but not mandatory if the `GraphSchema.output_node_id` points correctly.

### Input & Output

-   **Input:** The `OutputNode` *receives* data from upstream nodes via incoming `EdgeSchema` mappings where the `dst_node_id` matches its `node_id`. The structure of this received data must match the fields defined by the incoming edges.
-   **Output:** The `OutputNode` *produces* the final workflow result object, containing the fields collected from its inputs.

### Example (`GraphSchema`)

Let's say your workflow finishes by producing a `summary` (text) and a `status` (text). We use the conventional `output_node` ID.

```json
{
  "nodes": {
    "generate_summary": {
      "node_id": "generate_summary",
      "node_name": "some_summary_node", // Replace with actual node name
      "node_config": { /* ... */ }
    },
    "output_node": { // Using "output_node" as the node_id (conventional)
      "node_id": "output_node",
      "node_name": "output_node", // Type identifier
      "node_config": {}
      // Input schema is inferred from edges
    }
    // ... other nodes
  },
  "edges": [
    {
      "src_node_id": "generate_summary",
      "dst_node_id": "output_node", // Referencing the OutputNode's ID
      "mappings": [
        { "src_field": "generated_summary", "dst_field": "summary" },
        { "src_field": "final_status", "dst_field": "status" }
      ]
    }
    // ... other edges
  ],
  "input_node_id": "input_node", // Points to the Input Node instance ID
  // GraphSchema points to the Output Node instance ID
  "output_node_id": "output_node"
  // ...
}
```

In this example, the final result object produced by the workflow would look like:
`{"summary": "This is the generated summary.", "status": "Completed"}`.

### Notes for Non-Coders

-   The Output Node defines *what information the workflow produces* at the end. You mark a node as the Output Node by setting its `node_name` to `output_node`.
-   Give this Output Node a unique ID (`node_id`, e.g., `final_summary`).
-   Tell the overall workflow which node is the ending point by setting the graph's `output_node_id` to match the ID you chose. (Technically, you can point `output_node_id` to *any* node, and that node's output will be the final result, but using a dedicated `OutputNode` is common).
-   You don't usually configure the Output Node directly. Its structure is determined by the data fed into it from the *previous* steps (nodes) using edges.
-   Each `dst_field` in an edge ending at your Output Node's ID represents a piece of data included in the final workflow result. 