# Usage Guide: RouterNode

This guide explains how to use the `RouterNode` to introduce conditional branching into your workflows based on the data flowing through them.

## Purpose

The `RouterNode` acts as a decision point in your workflow. It examines the input data it receives and, based on conditions you define, determines which downstream node(s) the workflow should proceed to next.

Think of it as a conditional fork in the road or an "if-then-else" switch for your workflow. NOTE: there's a separate IFElseCondition node which evaluates complex conditions and outputs results; which can then be checked in the router node for equality with results eg, If `result == True` then route to this:

Common use cases:
-   Routing based on user input (e.g., `if user_feedback == 'positive', go to thank_you_node, else go to follow_up_node`).
-   Routing based on data properties -- Only Supported by IfElseConditionNode (e.g., `if order.amount > 1000, go to manager_approval, else go to auto_approve`).
-   Checking status flags (e.g., `if task_status == 'completed', go to archive_node, else go to retry_node`).

## Configuration (`NodeConfig`)

The core logic of the `RouterNode` is defined within its `node_config`, using the `RouterConfigSchema`.

```json
{
  "nodes": {
    "decision_point": {
      "node_id": "decision_point", // You choose a unique ID
      "node_name": "router_node",  // ** Must be "router_node" **
      "node_config": {
        // --- Base Router Settings ---
        "choices": ["node_A", "node_B", "node_C"], // List ALL possible destinations
        "allow_multiple": false, // false = route to FIRST match only; true = route to ALL matches
        "default_choice": "node_C", // Optional fallback if no conditions match

        // --- Specific Routing Conditions ---
        "choices_with_conditions": [
          {
            "choice_id": "node_A", // Destination if this condition is met
            "input_path": "data.status", // Field to check in the input data (use "." for nesting)
            "target_value": "approved" // Value to compare against (must be equal)
          },
          {
            "choice_id": "node_B",
            "input_path": "user_data.needs_review",
            "target_value": true
          }
          // Add more conditions as needed
        ]
      },
      // Input/Output schemas are usually dynamic/inferred
      "dynamic_input_schema": null,
      "dynamic_output_schema": null
    }
    // ... other nodes (node_A, node_B, node_C must be defined here)
  }
  // ... other graph properties
}
```

### `node_config` Details (`RouterConfigSchema`):

-   **`choices`** (List[str], required): A list of *all* possible `node_id`s that this router could potentially route to. Every `choice_id` used in `choices_with_conditions` **must** be included in this list.
-   **`allow_multiple`** (bool, default: `false`):
    *   If `false`: The router evaluates conditions in order. It routes to the *first* `choice_id` whose condition matches. Subsequent matches are ignored.
    *   If `true`: The router evaluates *all* conditions. It routes to *every* `choice_id` whose condition matches. This can cause the workflow to branch into multiple parallel paths.
-   **`default_choice`** (str, optional):
    *   Specifies which node to route to if none of the conditions match. 
    *   Must be one of the nodes listed in the main `choices` list.
    *   If not provided and no conditions match, the router will raise an error and the workflow will fail.
-   **`choices_with_conditions`** (List[`RouterChoiceCondition`], required):
    *   This is a list defining the actual routing logic. Conditions are evaluated in the order they appear.
    *   Each item in the list is a `RouterChoiceCondition` object with:
        *   **`choice_id`** (str, required): The `node_id` of the destination node to route to if this specific condition is met. Must be one of the nodes listed in the main `choices` list.
        *   **`input_path`** (str, required): The path to the field within the incoming data that you want to check. Use `.` as a delimiter for nested fields (e.g., `user.address.city`, `results.0.status`).
        *   **`target_value`** (any, required): The value that the data at the `input_path` must be *equal to* for this condition to match. The type of `target_value` should match the expected type of the data field (e.g., use `true`/`false` for booleans, numbers for numeric fields, strings for text fields).

## Input & Output

-   **Input:** Receives data from upstream nodes via incoming `EdgeSchema` mappings. The `RouterNode` uses this data to evaluate the conditions defined in its `choices_with_conditions`.
-   **Output:** The `RouterNode` primarily outputs a routing decision. Internally, it produces a special `ROUTER_CHOICE_KEY` containing a list of the matched `choice_id`(s). If `allow_multiple` is false, this list will contain zero or one ID. If `allow_multiple` is true, it can contain multiple IDs. If no conditions match and no default choice is specified, the node will raise an error. The node also passes through its input data unchanged via the `TEMP_STATE_UPDATE_KEY`.

## Example (`GraphSchema`)

Let's route based on a `status` field.

```json
{
  "nodes": {
    "check_status": { /* ... Node that produces a 'status' field ... */ },
    "status_router": {
      "node_id": "status_router",
      "node_name": "router_node",
      "node_config": {
        "choices": ["handle_approved", "handle_rejected", "needs_review"],
        "allow_multiple": false,
        "default_choice": "needs_review", // Fallback if no conditions match
        "choices_with_conditions": [
          {
            "choice_id": "handle_approved",
            "input_path": "status", // Check the top-level 'status' field
            "target_value": "Approved"
          },
          {
            "choice_id": "handle_rejected",
            "input_path": "status",
            "target_value": "Rejected"
          }
        ]
      }
    },
    "handle_approved": { /* ... */ },
    "handle_rejected": { /* ... */ },
    "needs_review": { /* ... */ }
  },
  "edges": [
    // Edge feeding data INTO the router
    {
      "src_node_id": "check_status",
      "dst_node_id": "status_router",
      "mappings": [
        // Pass all relevant fields the router might need to check
        { "src_field": "status", "dst_field": "status" },
        { "src_field": "review_flag", "dst_field": "needs_manual_review" }
      ]
    },
    // Edges representing possible paths FROM the router
    {
      "src_node_id": "status_router",
      "dst_node_id": "handle_approved", // Destination for the first choice_id
      "mappings": [] // Usually empty
    },
    {
      "src_node_id": "status_router",
      "dst_node_id": "handle_rejected", // Destination for the second choice_id
      "mappings": []
    },
    {
      "src_node_id": "status_router",
      "dst_node_id": "needs_review", // Destination for the third choice_id (default)
      "mappings": []
    }
    // ... other edges
  ],
  "input_node_id": "__INPUT__",
  "output_node_id": "__OUTPUT__"
}
```

**How it works:**
1.  The `status_router` receives data containing `status` and `needs_manual_review` fields.
2.  It first checks if `status == "Approved"`. If yes, it decides to route to `handle_approved` and stops checking (because `allow_multiple` is false).
3.  If not approved, it checks if `status == "Rejected"`. If yes, it routes to `handle_rejected` and stops.
4.  If none of the conditions match, it routes to the `default_choice`, which is `needs_review`.
5.  If no `default_choice` was specified and no conditions matched, the router would raise an error and the workflow would fail.

**Key points about edges from a router:**
-   You **must** define an `EdgeSchema` in the graph for *every* node ID listed in the router's `choices` list, originating from the router's `node_id`.
-   These outgoing edges typically have empty `mappings`, as the router's job is decision-making, not data transformation.
-   The workflow execution engine uses the router's internal decision (the list of matched `choice_id`s) to select which outgoing edge path(s) to follow.

### Notes for Non-Coders

-   Use the `RouterNode` (with `node_name`: `router_node`) when your workflow needs to make a choice based on data.
-   Configure it by:
    -   Listing all possible destination node IDs in `choices`.
    -   Deciding if you want to go to the *first* place that matches (`allow_multiple: false`) or *all* places that match (`allow_multiple: true`).
    -   Setting a `default_choice` to specify where to go if none of the conditions match (recommended).
    -   Setting up rules in `choices_with_conditions`:
        -   `choice_id`: Where to go if the rule matches.
        -   `input_path`: What piece of information to look at (use `.` to look inside data, like `order.details.item_name`).
        -   `target_value`: What the information must be *exactly equal to* for the rule to match.
-   Rules are checked in the order you list them.
-   Connect the `RouterNode` *to* all the possible next steps listed in `choices` using edges (these edges usually don't need data mappings). 