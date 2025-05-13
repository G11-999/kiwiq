# Usage Guide: HITLNode (Human-in-the-Loop)

This guide explains the `HITLNode`, which allows you to introduce points in your workflow where a human needs to review data, provide input, or make a decision.

## Purpose

The `HITLNode` (Human-in-the-Loop) represents a point in the workflow execution graph where the process pauses to wait for input from a designated human user via an external system or UI. It's essential for tasks requiring human judgment, approval, correction, or additional information that the automated parts of the workflow cannot provide.

Common use cases:
-   Content review and approval (e.g., reviewing AI-generated text before publishing).
-   Data validation or correction.
-   Decision making based on complex or ambiguous information.
-   Gathering additional context or details from a user.

The `HITLNode` itself, within the workflow graph definition, primarily serves to define the **data contract** for this interaction point.

## Configuration (`NodeConfig`)

Based on the core implementation (`dynamic_nodes.py`), the base `HITLNode` class **does not utilize the `node_config` field**. Any configuration placed here will likely be ignored by the node's processing logic.

```json
{
  "nodes": {
    "human_review_step": {
      "node_id": "human_review_step", // Choose a descriptive ID
      // Use 'hitl_' prefix. Suffix might map to external UI/task type.
      "node_name": "hitl_node__default", 
      // Base HITLNode ignores config. Specific implementations MIGHT use it,
      // but that depends on their custom code. Assume empty for standard use.
      "node_config": {}, 
      // Define expected output explicitly for clarity (Optional but recommended)
      "dynamic_output_schema": { 
        "fields": {
          "approval_status": { "type": "enum", "enum_values": ["approved", "rejected"], "required": true },
          "feedback_text": { "type": "string", "required": false }
        }
      },
      // Input schema is dynamically determined by incoming edges.
      "dynamic_input_schema": null 
    }
    // ... other nodes
  }
  // ... other graph properties
}
```

-   `node_id`: A unique identifier for this specific HITL step in your workflow.
-   `node_name`: Must start with `hitl_` (e.g., `hitl_node__default`, `hitl_content_review`). The suffix might be used by the external system/UI to select the correct task interface.
-   `node_config`: **Should generally be empty `{}`**. The base `HITLNode` implementation does not read from this field. Specific, custom-coded HITL node types (with different `node_name` values) *might* define their own configuration schemas, but this is not standard.
-   `dynamic_input_schema`: The structure of the data the HITL node *receives* is determined dynamically by the fields mapped via incoming `EdgeSchema` definitions. This defines what data is *available* to be presented to the human reviewer by the external UI.
-   `dynamic_output_schema`: Defines the structure of the data the HITL node is *expected to produce* after human interaction. This defines what the human (via the UI) must provide. It's recommended to explicitly define this using `dynamic_output_schema` for clarity, although it can also be implicitly defined by the fields expected by outgoing `EdgeSchema` mappings.

## Input & Output

-   **Input:** Receives data from upstream nodes via incoming `EdgeSchema` mappings. These mappings populate the node's dynamic input schema. The external system/UI handling the HITL task reads this input data to present it to the human.
-   **Output:** Produces data based on the human's input provided via the external system/UI. The structure of this output data **must** match the `dynamic_output_schema` (if defined) or the fields expected by outgoing `EdgeSchema` mappings. The workflow remains paused until the external system signals completion and provides the output data conforming to the expected schema.

## Example (`GraphSchema`)

Imagine a workflow where an AI generates text, and then a human reviews and approves/rejects it, optionally adding comments.

```json
{
  "nodes": {
    "ai_generator": {
      "node_id": "ai_generator",
      "node_name": "llm", // Assuming an LLM node generates content
      "node_config": { /* ... LLM config ... */ }
      // Outputs: generated_text, source_prompt
    },
    "human_review": {
      "node_id": "human_review",
      "node_name": "hitl_review", // Specific HITL task type for UI
      "node_config": {}, // Config is empty
      // Explicitly defining the output schema
      "dynamic_output_schema": {
        "fields": {
          "approved": { "type": "enum", "enum_values": ["yes", "no"], "required": true },
          "review_comments": { "type": "string", "required": false }
        }
      }
      // Input schema implicitly defined by incoming edge: { "text_to_review": str, "original_prompt": str }
    },
    "approval_router": { // Node to route based on human input
      "node_id": "approval_router",
      "node_name": "router_node", // Using standard router
      "node_config": { 
         "choices": ["process_approved", "request_revision"],
         "allow_multiple": false,
         "choices_with_conditions": [
           { "choice_id": "process_approved", "input_path": "decision", "target_value": "yes" },
           { "choice_id": "request_revision", "input_path": "decision", "target_value": "no" }
         ]
      }
    },
    "process_approved": { /* ... */ },
    "request_revision": { /* ... */ }
  },
  "edges": [
    // AI Generator output TO HITL input (Defines HITL Input Schema)
    {
      "src_node_id": "ai_generator",
      "dst_node_id": "human_review",
      "mappings": [
        // Data fields provided TO the HITL node (for the UI to display)
        { "src_field": "generated_text", "dst_field": "text_to_review" },
        { "src_field": "source_prompt", "dst_field": "original_prompt" }
      ]
    },
    // HITL output TO Router input (Reads from HITL Output Schema)
    {
      "src_node_id": "human_review",
      "dst_node_id": "approval_router",
      "mappings": [
        // Data fields provided BY the HITL node (after human input)
        { "src_field": "approved", "dst_field": "decision" }, // Map 'approved' output to router's 'decision' input
        { "src_field": "review_comments", "dst_field": "comments" } // Pass comments along
      ]
    },
    // Router outgoing edges...
    { "src_node_id": "approval_router", "dst_node_id": "process_approved" },
    { "src_node_id": "approval_router", "dst_node_id": "request_revision" }
  ],
  "input_node_id": "__INPUT__",
  "output_node_id": "__OUTPUT__"
}
```

In this example:
1.  The `ai_generator` sends `generated_text` and `source_prompt` to the `human_review` node. These define the *input schema* for `human_review`.
2.  The external UI associated with `hitl_review` reads `text_to_review` and `original_prompt` and displays them.
3.  The `dynamic_output_schema` requires the human (via the UI) to provide values for `approved` (either "yes" or "no") and optionally `review_comments`.
4.  This data (`approved`, `review_comments`) becomes the output of the `human_review` node, conforming to its *output schema*.
5.  The `approval_router` receives this output. Its edge mapping takes the `approved` field and maps it to its own input field named `decision`. The router then uses the value of `decision` ("yes" or "no") to route execution.

*(See `test_AI_loop.py` for a runnable example of an AI-Human feedback loop using HITL).*

### Notes for Non-Coders

-   Use the `HITLNode` in your graph definition whenever you need a human to look at something or provide information before the workflow continues.
-   **Don't worry about `node_config` - leave it empty (`{}`).** The node doesn't use it.
-   Focus on the **edges** connected to the `HITLNode`:
    -   *Incoming edges*: Define what information the human needs *to see*. Map the necessary fields *from* previous nodes *to* the `HITLNode`.
    -   *Outgoing edges*: Define what information the human needs *to provide*. Map the expected fields *from* the `HITLNode` *to* the next nodes.
-   Optionally, use `dynamic_output_schema` inside the `HITLNode` definition to clearly list the fields the human must provide. This is good for documentation and validation.
-   The `node_name` (like `hitl_review`) is important as it might tell the external application which specific screen or task interface to show the human.
