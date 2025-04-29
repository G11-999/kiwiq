# Usage Guide: MergeAggregateNode (merge_aggregate)

This guide explains how to configure and use the `MergeAggregateNode` to combine data from multiple sources (objects or lists of objects) within your workflow payload, applying specific rules for how data should be merged and conflicts resolved.

## Purpose

The `MergeAggregateNode` is designed to intelligently combine multiple pieces of data (represented as JSON objects or dictionaries) into a single, consolidated result. Think of it like combining information from different reports or forms into one master document, following specific instructions on how to handle overlapping or conflicting information.

You can use it to:

-   Select data from various locations (paths) in your input.
-   Merge selected objects sequentially, giving priority based on the order you specify.
-   Rename or select specific fields (keys) during the merge.
-   Decide how to handle fields that aren't explicitly mentioned (either automatically merge them or ignore them).
-   Define rules (reducers) for what to do when the same field exists in multiple sources (e.g., keep the newest value, keep the oldest, add numbers together, combine lists, merge nested details).
-   Perform calculations or transformations (like averaging, multiplying) on the final merged values for specific fields.
-   Configure multiple, independent merge operations within a single node instance, each producing its own output field.

**Important:** This node operates on a *copy* of the input data. The original data structure passed into the node remains unchanged in the central state unless explicitly overwritten by subsequent steps.

## Core Concepts

1.  **Selection:** You specify where in the input data to find the objects you want to merge (`select_paths`). If a path points to a list of objects, the node will treat each object in the list as a separate source to be merged.
2.  **Sequential Merging:** The objects found via `select_paths` are merged one after the other, in the order specified. This means data from later sources can potentially overwrite data from earlier sources, depending on the rules.
3.  **Mapping (`map_phase`):** Before merging, you can define rules for how fields (keys) from the source objects should be mapped to the final merged object. This allows renaming fields or selecting specific nested values. You also decide the fate of fields not explicitly mapped (`unspecified_keys_strategy`: either `auto_merge` them if the name matches, or `ignore` them).
4.  **Reduction (`reduce_phase`):** When a field exists in both the current merged result (the "left" side) and the new object being merged (the "right" side), a "reducer" rule determines the outcome. You can set a default rule and specific rules for certain fields.
5.  **Transformation (`post_merge_transformations`):** After all objects for a single operation have been merged, you can apply final transformations to specific fields in the result (e.g., calculate an average, multiply by a factor).
6.  **Operations:** You can define multiple independent merge operations within one node. Each operation selects its own data, applies its own strategy, and saves its result to a unique output field name.

## Configuration (`NodeConfig`)

You configure the `MergeAggregateNode` within the `node_config` field of its entry in the `GraphSchema`.

```json
{
  "nodes": {
    "consolidate_user_data": {
      "node_id": "consolidate_user_data", // Unique ID for this node instance
      "node_name": "merge_aggregate", // ** Must be "merge_aggregate" **
      "node_config": { // This is the MergeObjectsConfigSchema
        "operations": [ // List of merge operations to perform sequentially
          // --- Operation 1: Create a primary user profile ---
          {
            "output_field_name": "user_profile", // Result stored here
            "select_paths": [
              "source_system_a.user", // 1st source (highest priority if 'replace_left')
              "source_system_b.data", // 2nd source
              "manual_overrides"      // 3rd source (highest priority if 'replace_right')
            ],
            "merge_strategy": {
              "map_phase": {
                "key_mappings": [
                  // Rename 'userId' from any source to 'profile_id' in the output
                  {"source_keys": ["userId", "user_id", "id"], "destination_key": "profile_id"},
                  // Get email, trying 'emailAddress' first, then 'email'
                  {"source_keys": ["emailAddress", "email"], "destination_key": "contact_email"}
                ],
                "unspecified_keys_strategy": "auto_merge" // Bring over other fields like 'name', 'status' automatically
              },
              "reduce_phase": {
                "default_reducer": "replace_right", // Default: value from later source wins
                "reducers": {
                  // For 'tags', combine all lists found into one list
                  "tags": "extend",
                  // For 'login_count', add the values together
                  "login_count": "sum"
                },
                "error_strategy": "coalesce_keep_left" // If 'sum' fails (e.g., non-number), keep the existing value
              },
              "post_merge_transformations": {
                  // After merging, calculate average login count (example - requires specific setup)
                  // "average_logins": {"operation_type": "average"} // More complex setup usually needed for AVG
              },
              "transformation_error_strategy": "skip_operation" // If a transformation fails, just keep the pre-transform value
            }
          },
          // --- Operation 2: Aggregate scores ---
          {
            "output_field_name": "score_aggregation",
            "select_paths": ["system_scores.all", "bonus_points"], // system_scores.all might be a list
            "merge_strategy": {
                "map_phase": { "unspecified_keys_strategy": "ignore"}, // Only consider explicitly mapped keys
                "reduce_phase": {
                    "key_mappings": [
                        {"source_keys": ["score"], "destination_key": "total_score"},
                        {"source_keys": ["count"], "destination_key": "item_count"}
                    ],
                    "reducers": {
                        "total_score": "sum",
                        "item_count": "sum"
                    },
                     "default_reducer": "replace_right" // Should not be needed if ignoring unspecified
                },
                 "post_merge_transformations": {
                    "final_average": { "operation_type": "average"} // calculate average based on total_score's merged count
                 },
                 "map_phase": {
                     "key_mappings": [
                         {"source_keys": ["score"], "destination_key": "total_score"},
                         {"source_keys": ["count"], "destination_key": "item_count"},
                         // Map score to avg key for AVERAGE transform
                         {"source_keys": ["score"], "destination_key": "final_average"}
                     ],
                     "unspecified_keys_strategy": "ignore"
                 },
                 "reduce_phase": {
                     "reducers": {
                         "total_score": "sum",
                         "item_count": "sum",
                         "final_average": "sum" // Sum scores into the key that will be averaged
                     },
                     "default_reducer": "replace_right"
                 }
            }
          }
          // Add more operation objects here
        ]
      }
      // dynamic_input_schema / dynamic_output_schema usually not needed for this node
    }
    // ... other nodes (e.g., nodes providing 'source_system_a', 'source_system_b', 'manual_overrides')
  }
  // ... other graph properties (edges etc.)
}
```

### Key Configuration Sections:

1.  **`operations`** (List): **Required**. A list where each item defines one independent merge task. They run in the order listed, but the result of one does *not* directly feed into the next (unless you design subsequent operations to select the output of previous ones).
2.  **Inside each `operations` item**:
    *   **`output_field_name`** (String): **Required**. The name of the field where the final result of *this specific merge operation* will be stored in the node's overall output. Must be unique across all operations in this node.
    *   **`select_paths`** (List of Strings): **Required**. Dot-notation paths to the source objects or lists of objects in the input data.
        *   Order matters! This defines the sequence of merging (left-to-right).
        *   If a path points to a list, each object inside that list is merged sequentially.
    *   **`merge_strategy`** (Object): **Required**. Contains the detailed rules for this merge operation.
        *   **`map_phase`** (Object): Rules for handling fields *before* merging conflicts are resolved.
            *   `key_mappings` (List of Objects): Define explicit field handling. Each mapping has:
                *   `source_keys` (List of Strings): Paths within the *source* object to look for a value. Tries them in order; uses the first non-null value found.
                *   `destination_key` (String, Optional): The desired field name in the *output*. If omitted, defaults to the first `source_keys` entry. Supports dot-notation for nested output (e.g., `user.contact.email`).
            *   `unspecified_keys_strategy` (String: `"auto_merge"` or `"ignore"`): What to do with source fields *not* mentioned in `key_mappings`.
                *   `"auto_merge"`: Copy the field and its value directly to the output using the same name. Conflicts handled by the `reduce_phase`.
                    *   **Nuance:** Auto-merge iterates through the *top-level keys* of the incoming ("right") object.
                    *   It checks if a top-level key from the right object is *explicitly listed* as a `destination_key` in any `key_mappings`. If yes, auto-merge **skips** this key (it's handled by the mapping).
                    *   It also checks if a top-level key is a *prefix* of an explicit `destination_key` (e.g., right key `user`, explicit destination `user.profile.id`). If yes, auto-merge **also skips** this key to avoid merging the whole parent object when only children were mapped.
                    *   Auto-merge does *not* skip a key just because it was used as a `source_key` in a mapping. A key can be both auto-merged under its own name and used as a source for a *different* destination key.
                *   `"ignore"`: Discard these fields.
        *   **`reduce_phase`** (Object): Rules for resolving conflicts when a `destination_key` (either explicitly mapped or auto-merged) already exists in the merged result.
            *   `default_reducer` (String): The rule applied if no specific reducer is listed for the key. Default is `replace_right`.
            *   `reducers` (Object): Map specific `destination_key` names (dot-notation supported) to specific reducer rules.
                *   **Nested Paths:** Keys in this object *can be nested paths* (e.g., `"user.details.settings": "nested_merge_replace"`). When a conflict occurs during the merge (whether from an explicit map or auto-merge), the node looks for the *most specific matching reducer path* in this configuration. For example, if merging the `user` object triggers a conflict at `user.details.settings`, the reducer specified for that exact path will be used, potentially overriding a more general reducer defined for just `user`.
                *   Common Reducers:
                    *   `replace_right`: The value from the new source object overwrites the existing value. (Default)
                    *   `replace_left`: Keep the existing value; ignore the value from the new source object.
                    *   `append`: Expects the left value to be a list. Appends the entire right value as a single new element to the list.
                    *   `extend`: Expects *both* values to be lists. Extends the left list with the elements from the right list.
                    *   `combine_in_list`: Creates a list containing `[left_value, right_value]`. If the left value is already a list, it appends the right value to it.
                    *   `sum`, `min`, `max`: Perform numerical aggregation (expects numbers).
                    *   `simple_merge_replace`: Expects both values to be dictionaries. Merges *top-level* keys from the right dictionary into the left. If keys collide, the right value replaces the left. Does *not* recurse into nested dictionaries.
                    *   `simple_merge_aggregate`: Expects both values to be dictionaries. Merges *top-level* keys. If keys collide, values are combined into a list (`[left_value, right_value]`). Does *not* recurse.
                    *   `nested_merge_replace`: Handles any value types. If *both* values are dictionaries, it merges them recursively, applying the 'replace' logic at each level. For non-dictionary collisions, the right value replaces the left (if not None).
                    *   `nested_merge_aggregate`: Handles any value types. This provides a deep aggregation:
                        *   If *both* values are dictionaries, it merges them recursively, applying the 'aggregate' logic at each level.
                        *   If *both* values are lists, it extends the left list with the non-None items from the right list.
                        *   If values have different types or are primitives (numbers, strings, booleans), they are combined into a list. If the left value is already a list, the right value is appended.
                        *   `None` values on the right side are ignored and do not get added to lists or overwrite existing values during aggregation.
            *   `error_strategy` (String): How to handle errors during reduction (e.g., trying to `sum` text). Options:
                *   `coalesce_keep_left`: Keep the original (\"left\") value.
                *   `coalesce_keep_non_empty`: **(Default)** Keep the original (\"left\") value if it exists and is considered \"truthy\" (not `null`, `false`, `0`, empty string/list/dict). Otherwise, use the new (\"right\") value. This is useful for accumulating values where the first non-empty value encountered should be kept if subsequent reductions fail.
                *   `skip_operation`: Keep the original (\"left\") value.
                *   `set_none`: Set the value to `null`.
                *   `fail_node`: Stop the node and report an error.
        *   **`post_merge_transformations`** (Object, Optional): Apply calculations *after* all sources for this operation are merged. Maps `destination_key` names to transformation rules.
            *   Each rule specifies:
                *   `operation_type` (String): The calculation to perform. Common types:
                    *   `average`: Calculates the average. Assumes the current value is a sum and uses an internally tracked count of how many items were merged into that sum.
                    *   `multiply`: Multiply the value by the `operand`.
                    *   `divide`: Divide the value by the `operand`.
                    *   `add`: Add the `operand` to the value.
                    *   `subtract`: Subtract the `operand` from the value.
                *   `operand` (Any): The number to use for multiply, divide, add, subtract. **Required** for those operations.
        *   **`transformation_error_strategy`** (String): How to handle errors during transformations (e.g., `divide` by zero). Same options as `error_strategy`. Default is `skip_operation`.

## Input (`DynamicSchema`)

The `MergeAggregateNode` expects input data (typically a dictionary or `DynamicSchema`) containing the data structures referenced by the `select_paths` in its configuration.

## Output (`MergeObjectsOutputSchema`)

The node produces an output object containing:

-   **`merged_data`** (Dict[str, Any]): A dictionary where keys are the `output_field_name` values defined in each operation, and the values are the final merged results for those operations. If a critical error occurs that prevents processing (like invalid config or a `fail_node` error strategy being triggered), the `merged_data` might be empty or reflect partial results up to the failure point.

## Example `GraphSchema` Snippet (Focus on Edges)

```json
{
  "nodes": {
    "get_crm_data": { /* ... outputs object like { "user": {...}, "details": {...} } ... */ },
    "get_activity_data": { /* ... outputs object like { "data": {...} } ... */ },
    "get_manual_data": { /* ... outputs object like { "overrides": {...} } ... */ },

    "consolidate_data": {
      "node_id": "consolidate_data",
      "node_name": "merge_aggregate",
      "node_config": {
        "operations": [
          {
            "output_field_name": "final_user_record",
            "select_paths": [
              "crm_user", // Input field name
              "activity_info", // Input field name
              "manual_input" // Input field name
            ],
            "merge_strategy": { /* ... defined strategy ... */ }
          }
        ]
      }
    },
    "process_final_record": { /* ... expects input with 'final_user_record' ... */ }
  },
  "edges": [
    // Edges feeding data INTO the merge node
    {
      "src_node_id": "get_crm_data",
      "dst_node_id": "consolidate_data",
      "mappings": [ { "src_field": "user", "dst_field": "crm_user" } ] // Map CRM output 'user' to input 'crm_user'
    },
    {
      "src_node_id": "get_activity_data",
      "dst_node_id": "consolidate_data",
      "mappings": [ { "src_field": "data", "dst_field": "activity_info" } ] // Map activity output 'data' to input 'activity_info'
    },
     {
      "src_node_id": "get_manual_data",
      "dst_node_id": "consolidate_data",
      "mappings": [ { "src_field": "overrides", "dst_field": "manual_input" } ] // Map manual output 'overrides' to input 'manual_input'
    },
    // Edge sending the merged data OUT
    {
      "src_node_id": "consolidate_data",
      "dst_node_id": "process_final_record",
      "mappings": [
        // The output field 'merged_data' contains a dict with 'final_user_record' inside
        { "src_field": "merged_data.final_user_record", "dst_field": "user_record_to_process" }
      ]
    }
  ],
  "input_node_id": "...",
  "output_node_id": "..."
}
```

## Notes for Non-Coders

-   Use this node when you need to combine information from different places into one structured object, especially when the same information might appear in multiple places and you need rules to decide which version to keep or how to combine them.
-   Think of it like creating a "best version" of a record by layering information from several sources.
-   **`operations`**: You can set up multiple independent combining tasks in one node. Each task gets its own name (`output_field_name`).
    -   `select_paths`: Tell the node where to find the data pieces to combine for *this* task. The order you list them matters for some rules (like "keep the last value seen").
    -   `merge_strategy`: The core instructions for combining.
        -   **`map_phase`**: Prepare the fields.
            -   `key_mappings`: Use this to rename fields (e.g., call `customer_id` -> `clientID`) or grab nested values.
            -   `unspecified_keys_strategy`: Should fields *not* specifically mentioned in mappings be included (`auto_merge`) or dropped (`ignore`)? See the **Configuration** section for important nuances on how `auto_merge` interacts with explicit mappings and nested keys.
        -   **`reduce_phase`**: Handle overlaps.
            -   `default_reducer`: The basic rule (usually "keep the last value seen").
            -   `reducers`: Special rules for specific fields (e.g., `sum` for numbers, `extend` for lists, `nested_merge` for complex details). These can target nested paths directly (e.g., `user.settings`).
                -   Use `nested_merge_replace` or `nested_merge_aggregate` to combine complex nested data structures deeply.
                -   `nested_merge_aggregate` is useful for combining everything found: it merges nested objects, extends lists, and groups differing values into lists.
        -   **`post_merge_transformations`**: Final tweaks after combining (e.g., calculate an `average`, `multiply` a value).
-   **Dot Notation:** Use dots (`.`) to access data inside objects (e.g., `customer.address.zipcode`).
-   **It Modifies a Copy:** The node doesn't change the original input data; it creates a new combined result in its output field (`merged_data`).
-   Connect the necessary input data sources to this node using edges and mappings. Connect the `merged_data` field (or a specific field *inside* it like `merged_data.my_output_name`) to the next node that needs the combined result.

## Comparison to DataJoinNode

-   `MergeAggregateNode`: Combines *multiple source objects* into *one output object* based on sequential order and explicit rules for key mapping and conflict resolution. Good for creating a single, consolidated view from potentially overlapping sources.
-   `DataJoinNode`: Links items *between two lists/objects* based on matching key values (like a database join). It typically *nests* the matched item(s) from the second list inside the corresponding item of the first list. Good for enriching items in one list with related details from another.
