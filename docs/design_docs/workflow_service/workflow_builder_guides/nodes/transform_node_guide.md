# Usage Guide: TransformerNode (transform_data)

This guide explains how to configure and use the `TransformerNode` to restructure and remap data within your workflow.

## Purpose

The `TransformerNode` acts like a data reorganizer. It allows you to:

-   Take data from specific locations (fields) in the input.
-   Copy that data to new locations (fields) in the output.
-   Create nested structures (objects within objects) in the output on the fly.
-   Rename fields.
-   Select only the specific pieces of data you need for the next steps.

This is useful for preparing data for subsequent nodes that expect a different structure, simplifying complex objects, or extracting key information.

**Important:** This node creates a completely *new* output dictionary based on the mappings you define. It does *not* modify the original input data structure.

## Configuration (`NodeConfig`)

You configure the `TransformerNode` within the `node_config` field of its entry in the `GraphSchema`.

```json
{
  "nodes": {
    "restructure_user_data": {
      "node_id": "restructure_user_data", // Unique ID for this node instance
      "node_name": "transform_data", // ** Must be "transform_data" **
      "node_config": { // This is the TransformerConfigSchema
        "mappings": [ // List of copy instructions
          // --- Example 1: Simple field rename ---
          {
            "source_path": "input_user.profile.email_address", // Where to copy FROM (in input)
            "destination_path": "output_contact.primary_email" // Where to copy TO (in output)
          },
          // --- Example 2: Move a whole object ---
          {
            "source_path": "input_user.preferences", // Copy the entire preferences object
            "destination_path": "output_settings" // Place it here in the output
          },
          // --- Example 3: Create nested structure ---
          {
            "source_path": "input_user.id",
            "destination_path": "output_user.identifier.system_id" // Creates 'output_user' and 'identifier' if they don't exist
          },
          // --- Example 4: Extracting specific list item ---
          {
            "source_path": "input_orders.0.order_id", // Get the ID of the *first* order in the list
            "destination_path": "latest_order_ref"
          },
          // --- Example 5: Overwriting (Last mapping wins) ---
          {
            "source_path": "alternate_email",
            "destination_path": "output_contact.primary_email" // This would overwrite Example 1 if 'alternate_email' exists
          }
        ]
      }
      // dynamic_input_schema / dynamic_output_schema usually not needed for this node
    }
    // ... other nodes (e.g., a node providing 'input_user' data)
  }
  // ... other graph properties (edges etc.)
}
```

### Key Configuration Sections:

1.  **`mappings`** (List): **Required**. A list where each item defines a single copy operation from a source location to a destination location. Mappings are processed in the order they appear in the list.
2.  **Inside each `mapping` item**:
    *   **`source_path`** (String): **Required**. Dot-notation path indicating where to find the data *in the node's input*. Examples: `user.id`, `product.details.price`, `orders.0.items.1.sku` (accessing the second item in the items list of the first order).
    *   **`destination_path`** (String): **Required**. Dot-notation path indicating where to place the copied data *in the node's output*. Examples: `customer_id`, `item_price`, `order_item_sku`. If intermediate parts of the path (like `output_user` or `identifier` in Example 3) don't exist in the output being built, they will be created as dictionaries automatically.

### Dot Notation:

-   Use dots (`.`) to access fields inside objects (e.g., `user.profile.name`).
-   Use integer numbers to access items within lists (e.g., `orders.0` for the first order, `orders.1.items.0` for the first item in the second order).

### Behavior Notes:

-   **Order Matters:** Mappings are processed sequentially. If multiple mappings write to the exact same `destination_path`, the *last* mapping in the list will determine the final value.
-   **Source Not Found:** If a `source_path` does not exist in the input data, that specific mapping is simply skipped. No error occurs, and nothing is added to the output for that mapping.
-   **Creates New Output:** The node starts with an empty output dictionary `{}` and builds it up based *only* on the mappings provided. Data from the input is not included unless explicitly mapped.
-   **Deep Copies:** The node copies the data. If you map a list or an object, the entire structure is copied, ensuring that changes to the output data won't accidentally affect the original input data.

## Input (`DynamicSchema`)

The `TransformerNode` typically receives data from a previous node or the central graph state. It uses a `DynamicSchema`, meaning it doesn't have a fixed input structure but adapts based on the `source_path` fields used in your `mappings`.

-   Ensure the input data actually contains the fields specified in your `source_path` mappings.

## Output (`TransformerOutputSchema`)

The node produces data matching the `TransformerOutputSchema`:

-   **`transformed_data`** (Dict[str, Any]): The newly constructed dictionary containing only the data copied according to the `mappings`. If no mappings were successful (e.g., all source paths were invalid or the input was empty), this will be an empty dictionary `{}`.

## Example `GraphSchema` Snippet (Focus on Edges)

```json
{
  "nodes": {
    "fetch_raw_data": { /* ... node outputting complex 'raw_user' object ... */ },
    "clean_up_user": {
      "node_id": "clean_up_user",
      "node_name": "transform_data",
      "node_config": {
        "mappings": [
          { "source_path": "raw_user.data.id", "destination_path": "user_id" },
          { "source_path": "raw_user.data.profile.displayName", "destination_path": "name" },
          { "source_path": "raw_user.data.contactPoints[0].value", "destination_path": "primary_email" } // Assuming contactPoints is a list
        ]
      }
    },
    "send_to_crm": { /* ... node expecting simple input with 'user_id', 'name', 'primary_email' ... */ }
  },
  "edges": [
    // Edge feeding raw data into the transformer
    {
      "src_node_id": "fetch_raw_data",
      "dst_node_id": "clean_up_user",
      "mappings": [
        // Pass the entire raw user object (or specific parts needed by source_path)
        { "src_field": "raw_user", "dst_field": "raw_user" } // Input field name matches source_path base
      ]
    },
    // Edge sending the simplified data OUT of the transformer
    {
      "src_node_id": "clean_up_user",
      "dst_node_id": "send_to_crm",
      "mappings": [
        // The output 'transformed_data' contains the new structure
        // Map fields from transformed_data to the input of the next node
        { "src_field": "transformed_data.user_id", "dst_field": "crm_user_id" },
        { "src_field": "transformed_data.name", "dst_field": "customer_name" },
        { "src_field": "transformed_data.primary_email", "dst_field": "email" }
      ]
    }
    // Alternative edge: Pass the whole transformed object if the next node accepts it
    // { 
    //   "src_node_id": "clean_up_user", 
    //   "dst_node_id": "send_to_crm", 
    //   "mappings": [ { "src_field": "transformed_data", "dst_field": "simplified_user_data" } ]
    // }
  ],
  "input_node_id": "...",
  "output_node_id": "..."
}
```

## Notes for Non-Coders

-   Use this node when you need to **change the shape** of your data.
-   Think of it like **copy-pasting specific pieces of information** from one place (the input) to a new, cleaner structure (the output).
-   **`mappings`**: This is your list of copy-paste instructions.
    -   `source_path`: Where do I find the data I want to copy? (e.g., `customer.details.email`)
    -   `destination_path`: Where should I put the copied data in the new structure? (e.g., `contact_email` or `lead.info.email`)
-   **Dot Notation:** Use dots (`.`) to go inside objects (like folders) and numbers (`0`, `1`, `2`...) to pick items from lists.
-   **Creates New Output:** It doesn't change the original data. It builds a *new* data object containing only what you told it to copy.
-   **Renaming:** You can easily rename fields by using different `source_path` and `destination_path` names.
-   **Simplifying:** You can pick just the few fields you need from a large, messy input object.
-   Connect the input data to this node. Connect the output field `transformed_data` (or specific fields within it using dot notation) to the next node that needs the restructured data. 