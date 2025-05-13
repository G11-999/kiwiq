# Usage Guide: MapListRouterNode (map_list_router_node)

This guide explains how to configure and use the `MapListRouterNode` to iterate over collections (lists or dictionaries), optionally batch items, and dispatch individual items or batches to other nodes for processing, potentially in parallel.

## Purpose

The `MapListRouterNode` acts as a distributor or dispatcher in your workflow. It allows you to:

-   Take a list of items (e.g., a list of products, tasks, or documents) or the values from a dictionary found at a specific `source_path` in the input data.
-   For *each item* in that collection:
    -   Apply transformations based on mappings defined on the *outgoing edges*.
-   **Optionally batch** the processed items based on a specified `batch_size`.
-   Send the individual processed items (if `batch_size` is 1) or the batches (as lists) to one or more specified `destination` nodes.
-   **Optionally wrap** the sent item or batch list within a dictionary using a `batch_field_name` as the key.
-   Enable parallel processing of items/batches by leveraging LangGraph's `Send` mechanism, allowing multiple downstream nodes to potentially run concurrently for different items or batches.

This is fundamental for patterns like:
-   **Map-Reduce:** Processing each item in a list independently (map) before potentially aggregating results later (reduce).
-   **Batch Processing / Fan-Out:** Applying the same operation (like an LLM call or data validation) to multiple data points, potentially grouping them into batches for efficiency before sending.
-   **Dynamic Fan-Out:** Distributing tasks based on the content of a list generated earlier in the workflow.

**Key Concept:** Unlike nodes that process data as a whole, this node breaks down a collection, processes items based on edge mappings, optionally batches them, optionally wraps them, and initiates separate processing paths for the resulting payloads via `Send` commands.

## Configuration (`NodeConfig`)

You configure the `MapListRouterNode` within the `node_config` field of its entry in the `GraphSchema`.

```json
{
  "nodes": {
    "distribute_tasks": {
      "node_id": "distribute_tasks", // Unique ID for this node instance
      "node_name": "map_list_router_node", // ** Must be "map_list_router_node" **
      "node_config": { // This is the MapperConfigSchema
        // --- Base Router Settings ---
        "choices": ["process_batch_node", "log_item_node", "error_handler_node"], // List ALL possible destination node IDs
        // "allow_multiple": false, // Not directly used by mapper logic

        // --- Specific Distribution Rules ---
        "map_targets": [
          {
            // Rule 1: Send items from 'pending_tasks' list in batches of 10
            // to 'process_batch_node'. Wrap each batch in { "task_batch": [...] }.
            "source_path": "tasks.pending", // Path to the list in the input data
            "destinations": ["process_batch_node"], // Node ID to send batches to
            "batch_size": 10, // Group items into lists of 10
            "batch_field_name": "task_batch" // Wrap the sent list like this: { "task_batch": [item1, ..., item10] }
          },
          {
            // Rule 2: Send individual items from 'pending_tasks' list to 'log_item_node'.
            // No batching (default batch_size=1), no wrapping (default batch_field_name=null).
            "source_path": "tasks.pending",
            "destinations": ["log_item_node"],
            // batch_size defaults to 1
            // batch_field_name defaults to null
          },
          {
            // Rule 3: Send individual items from 'failed_tasks' list to 'error_handler_node'.
            // Wrap each item like this: { "failed_item": item }
            "source_path": "tasks.failed",
            "destinations": ["error_handler_node"],
            "batch_size": 1, // Explicitly sending one by one
            "batch_field_name": "failed_item" // Wrap the single sent item
          }
          // Add more map_target objects if you need to distribute items from other lists/dicts
        ]
      },
      // Input/Output schemas are dynamic for this node
      "dynamic_input_schema": null,
      "dynamic_output_schema": null
    },
    // --- Destination Nodes (Must be defined) ---
    "process_batch_node": {
      "node_id": "process_batch_node",
      /* ... other config ... */
      // CRITICAL for parallel processing (even with batches):
      "private_input_mode": true // Expects input like { "task_batch": [...] } directly
    },
    "log_item_node": {
      "node_id": "log_item_node",
      /* ... other config ... */
      "private_input_mode": true // Expects individual item directly
    },
    "error_handler_node": {
      "node_id": "error_handler_node",
      /* ... other config ... */
      "private_input_mode": true // Expects input like { "failed_item": item } directly
    },
    "next_node_after_processing": {
        "node_id": "next_node_after_processing",
        // IMPORTANT: If this node receives input from a node with private_output_mode=true,
        // it must also have private_input_mode=true to receive the direct Send.
        "private_input_mode": true
        /* ... other config ... */
    },
    "final_aggregator": { /* ... Node to potentially collect results ... */ }
    // ... other nodes
  }
  // ... other graph properties (Edges are crucial - see example below)
}
```

### `node_config` Details (`MapperConfigSchema`):

-   **`choices`** (List[str], required): Inherited from the base router schema. This list **must** include the `node_id` of *every* possible destination node that any `map_target` might send items or batches to. It's used for graph validation and visualization.
-   **`allow_multiple`** (bool, default: `false`): Inherited, but not directly used by the mapper's distribution logic (which inherently sends to all specified destinations for an item/batch according to the rules).
-   **`map_targets`** (List[`MapTargetConfig`], required): **Core configuration**. A list where each item defines a rule for distributing items from a specific source collection.
    -   **Inside each `MapTargetConfig`**:
        *   **`source_path`** (str, required): Dot-notation path to the collection (list or dictionary) in the node's input data whose items you want to distribute (e.g., `customer_orders`, `results.analysis_items`). If it's a dictionary, the node iterates over its *values*.
        *   **`destinations`** (List[str], required): A list of `node_id`s. For *every item* found at the `source_path`, it will be processed (based on edge mappings), potentially batched with others according to `batch_size`, potentially wrapped according to `batch_field_name`, and then a `Send` command will be generated targeting each `node_id` in this list with the final payload. These IDs must be present in the top-level `choices`.
        *   **`batch_size`** (int, default: `1`, minimum: `1`): The number of *processed* items (after edge mapping) to group together before sending.
            -   `1` (default): Sends each processed item individually.
            -   `> 1`: Sends items in lists (batches). The last batch for a given source/destination pair might have fewer items than `batch_size`.
        *   **`batch_field_name`** (Optional[str], default: `null`): If provided, the final payload sent to the destination node will be a dictionary with this string as the key.
            -   If `batch_size` is `1`, the value will be the single processed item: `{ "your_field_name": processed_item }`.
            -   If `batch_size` is `> 1`, the value will be the list (batch) of processed items: `{ "your_field_name": [item1, item2, ...] }`.
            -   If `null` (default), the processed item (for `batch_size=1`) or the list of items (for `batch_size>1`) is sent directly as the payload.

### Data Transformation Happens on Edges!

**Crucially**, unlike the `TransformerNode` or `DataJoinNode`, the `MapListRouterNode` **does not** define how individual items are transformed within its *own* configuration. Transformations happen *before* batching/wrapping:

-   **Item transformations are defined via `mappings` on the outgoing `EdgeSchema`** connecting the `MapListRouterNode` to each destination node specified in `destinations`.
-   If an edge has mappings, *each individual item* from the `source_path` will be transformed into a new dictionary according to those mappings *before* it is considered for batching.
-   If an edge has *no* mappings (`mappings: []` or omitted), the original item is used for batching (after being copied).
-   The *same* original item can be transformed differently for different destinations (based on edge mappings) and then potentially batched differently (based on `batch_size` in the corresponding `MapTargetConfig`).

## Input (`DynamicSchema`)

-   The node expects input data containing the collections (lists or dictionaries) specified in the `source_path` of its `map_targets`.
-   It uses a `DynamicSchema` and adapts based on the `source_path` fields configured.

## Output (`Command`)

-   The `MapListRouterNode` does **not** produce a standard data output field like `transformed_data`.
-   Its primary output is a LangGraph `Command` object. This command contains:
    -   A list of `Send` actions. Depending on the `batch_size` and `batch_field_name` configuration for each source/destination pair, each `Send` action encapsulates:
        *   A single (potentially transformed) item.
        *   A list (batch) of (potentially transformed) items.
        *   A dictionary containing a single item under the `batch_field_name` key.
        *   A dictionary containing a list (batch) of items under the `batch_field_name` key.
        The `Send` action also includes the target `node_id`.
    -   A state update dictionary, primarily containing the execution order tracker (`__central_state__.node_execution_order`).

## Parallel Processing & Private Modes

The `MapListRouterNode` enables parallel execution using LangGraph's `Send` mechanism, **whether sending individual items or batches**. Here's how it works and why `private_input_mode` / `private_output_mode` are essential:

1.  **Dispatch via `Send`:** For each payload (item or batch, possibly wrapped) generated according to the `map_targets` rules, the mapper generates a `Send(node_id=destination, data=payload)` action within a `Command`.
2.  **Independent Execution:** LangGraph interprets this `Command`. Each `Send` action effectively triggers an independent execution instance of the `destination` node with the provided `payload`. If you send 5 batches of 10 items to 1 destination, you could potentially trigger 5 parallel node runs (subject to runtime execution limits).
3.  **The State Conflict Problem:** If these parallel destination nodes read from and write to the *shared central graph state*, they can interfere with each other, leading to race conditions and incorrect results. Imagine multiple parallel runs trying to update the same `summary` field in the central state – the final result would be unpredictable because the order of updates isn't guaranteed.
4.  **Solution: `private_input_mode`:** To enable safe parallel processing, the **destination nodes** receiving the `Send` commands **must** be configured with `private_input_mode: true`.
    -   This tells the node: "Expect your input data *directly* from the `Send` command that triggered you, not by reading from the shared central graph state."
    -   It effectively gives each parallel run its own isolated input data (the specific item or batch sent to it), preventing state conflicts on input.
5.  **Solution: `private_output_mode`:** If a node *downstream* from a private-input node also needs to operate in this isolated, per-item/per-batch context, it must *also* have `private_input_mode: true`. Furthermore, the node *immediately preceding it* (the one that received the private input) must be configured with `private_output_mode: true`.
    -   This tells the node: "Instead of writing my output to the central state, package it and `Send` it directly to my downstream nodes (which must be expecting private input)."
    -   This continues the isolated processing chain for that specific item or batch branch, preventing the intermediate node from polluting the shared state.
6.  **Convergence:** Branches running in private mode do not automatically merge their results back into the main graph state. You typically need a dedicated aggregator/reducer node later in the workflow that is designed to collect results. This aggregator often reads from the central state where parallel branches might eventually write their final outputs (perhaps using specific state update mechanisms like reducers configured in the `GraphSchema` metadata), or it might be designed to receive inputs directly if the preceding private nodes also use `private_output_mode`. The `MapListRouterNode` itself *does not* handle this aggregation or reduction.

**In short: To run branches in parallel after this mapper (sending items OR batches), set `private_input_mode: true` on the immediate destination nodes. If the parallel branches continue further, subsequent nodes also need `private_input_mode: true`, and the nodes feeding them need `private_output_mode: true`. Plan for how results will be aggregated later.**

## Example `GraphSchema` Snippet (Focus on Batching & Wrapping)

```json
{
  "nodes": {
    "get_data": { /* ... outputs { "items": [ {"id":1,"v":"A"}, {"id":2,"v":"B"}, {"id":3,"v":"C"}, {"id":4,"v":"D"} ] } ... */ },
    "distribute_work": {
      "node_id": "distribute_work",
      "node_name": "map_list_router_node",
      "node_config": {
        "choices": ["process_batch", "archive_single"],
        "map_targets": [
          { // Rule 1: Batch processing
            "source_path": "items", // Iterate over this list
            "destinations": ["process_batch"], // Send batches here
            "batch_size": 2, // Batches of 2
            "batch_field_name": "input_batch" // Wrap: { "input_batch": [...] }
          },
          { // Rule 2: Individual archiving
            "source_path": "items",
            "destinations": ["archive_single"],
            "batch_size": 1, // Send one by one (default)
            "batch_field_name": null // Send item directly (default)
          }
        ]
      }
    },
    "process_batch": {
      "node_id": "process_batch",
      "node_name": "batch_processor_node", // Handles input like { "input_batch": [...] }
      "private_input_mode": true, // Expect direct input via Send
      // Potentially private_output_mode: true if followed by more private steps
      "node_config": { /* ... */ }
    },
    "archive_single": {
      "node_id": "archive_single",
      "node_name": "single_item_archiver_node", // Handles input like { "record_id": N }
      "private_input_mode": true, // Expect direct input via Send
      "node_config": { /* ... */ }
    },
    "collect_results": { /* ... Node to gather results ... */ }
  },
  "edges": [
    // Data into the mapper
    { "src_node_id": "get_data", "dst_node_id": "distribute_work", "mappings": [{ "src_field": "items", "dst_field": "items" }] },

    // --- Edges FROM the Mapper (Define item transformations here!) ---
    {
      // Edge for Rule 1 (process_batch)
      "src_node_id": "distribute_work",
      "dst_node_id": "process_batch",
      // Mappings apply to *each item* BEFORE batching/wrapping
      "mappings": [
        { "src_field": "id", "dst_field": "task_id" },
        { "src_field": "v", "dst_field": "value_data" }
      ]
      // Resulting Send payload to process_batch will be like:
      // { "input_batch": [ { "task_id": 1, "value_data": "A" }, { "task_id": 2, "value_data": "B" } ] }
      // { "input_batch": [ { "task_id": 3, "value_data": "C" }, { "task_id": 4, "value_data": "D" } ] }
    },
    {
      // Edge for Rule 2 (archive_single)
      "src_node_id": "distribute_work",
      "dst_node_id": "archive_single",
      // Mappings apply to *each item* BEFORE sending (since batch_size=1 and no wrapping)
      "mappings": [
        { "src_field": "id", "dst_field": "record_id" }
        // Note: 'v' field is not mapped here
      ]
      // Resulting Send payloads to archive_single will be like:
      // { "record_id": 1 }
      // { "record_id": 2 }
      // { "record_id": 3 }
      // { "record_id": 4 }
    }
    // --- Edges converging later ---
    // { "src_node_id": "process_batch", "dst_node_id": "collect_results", /* ... */ },
    // { "src_node_id": "archive_single", "dst_node_id": "collect_results", /* ... */ }
  ],
  "input_node_id": "...",
  "output_node_id": "..."
}
```

## Notes for Non-Coders

-   Use this node (`map_list_router_node`) when you have a list of things and want to do something **for each thing (or groups of things)**, maybe even at the same time (in parallel).
-   Think of it like taking a stack of papers (your list) and handing them out:
    -   One paper at a time to person A (`batch_size: 1`).
    -   Groups (batches) of 5 papers stapled together to person B (`batch_size: 5`).
-   **`map_targets`**: Define your distribution rules.
    -   `source_path`: Where is the list of items located in the input data? (e.g., `products_to_update`).
    -   `destinations`: Which node(s) should receive the items/batches from that list? (e.g., `["update_inventory_node", "log_update_node"]`).
    -   **`batch_size`** (Optional, default 1): How many items to group together? `1` means send individually. `10` means send lists containing 10 items each.
    -   **`batch_field_name`** (Optional, default none): Do you want to wrap the sent item or batch list in a labeled container? If yes, provide the label name here (e.g., `"product_info"`). If no, leave it out.
        -   Example (batch_size=1, batch_field_name="product_info"): Sends `{ "product_info": the_item }`
        -   Example (batch_size=10, batch_field_name="product_batch"): Sends `{ "product_batch": [item1, ..., item10] }`
        -   Example (batch_size=1, no batch_field_name): Sends `the_item`
        -   Example (batch_size=10, no batch_field_name): Sends `[item1, ..., item10]`
-   **Data Shape Changes on Edges:** If you need to rename fields or select only parts of an item, you configure that on the **connecting line (edge)** going from *this* node to the destination node. This happens *before* items are grouped into batches.
-   **Parallel Work Setup:** Still requires setting `private_input_mode: true` on the destination nodes receiving the items *or* batches. The rules haven't changed here.
-   Connect the input data containing the list to this node.
-   Connect this node with **edges** to all the destination nodes listed in `choices`. Define any necessary item transformations in the `mappings` section *of those edges*. 