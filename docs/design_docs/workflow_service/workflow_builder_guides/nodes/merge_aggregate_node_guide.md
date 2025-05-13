# Usage Guide: MergeAggregateNode (merge_aggregate)

This guide explains how to configure and use the `MergeAggregateNode` to combine data from multiple sources (objects or lists of objects) within your workflow payload, applying specific rules for how data should be merged and conflicts resolved.

## Purpose

The `MergeAggregateNode` is designed to intelligently combine multiple pieces of data (represented as JSON objects/dictionaries, or simpler types like numbers, strings, and lists) into a single, consolidated result. Think of it like combining information from different reports or forms into one master document, following specific instructions on how to handle overlapping or conflicting information.

You can use it to:

-   Select data from various locations (paths) in your input.
-   Merge selected objects or values sequentially, giving priority based on the order you specify.
-   Treat lists found at selection paths either as collections of objects to flatten and merge, or as single atomic items to be merged directly.
-   Rename or select specific fields (keys) during the merge when working with objects.
-   Decide how to handle fields that aren't explicitly mentioned when merging objects (`auto_merge` or `ignore`).
-   Define rules (reducers) for what to do when the same field exists in multiple source objects, or how to combine sequential non-dictionary values (e.g., keep the newest value, keep the oldest, add numbers together, combine items into lists, merge nested details).
-   Perform calculations or transformations (like averaging, multiplying, flattening lists, limiting lists) on the final merged values.
-   Configure multiple, independent merge operations within a single node instance, each producing its own output field.
-   **Perform transformations on a single selected object or value**, even without performing a multi-source merge.

**Important:** This node operates on a *copy* of the input data. The original data structure passed into the node remains unchanged in the central state unless explicitly overwritten by subsequent steps.

## Core Concepts

1.  **Selection (`select_paths`)**: You specify where in the input data to find the data items you want to merge.
    *   **Merging Dictionaries (Default):** If `merge_each_object_in_selected_list` is `True` (default), and a path points to a list, the node treats each *dictionary* inside that list as a separate source to be merged sequentially. Non-dictionary items in the list are skipped. If a path points to a single dictionary, it's treated as one source.
    *   **Merging Non-Dictionaries:** If `merge_each_object_in_selected_list` is `False`, the node takes the value found at *each* `select_paths` exactly as it is (be it a number, string, boolean, list, or null). It does **not** look inside lists. All selected items are then merged sequentially using the `default_reducer`. **Crucially, when this flag is `False`, none of the selected items can be dictionaries.**
2.  **Sequential Merging:** The selected data items (dictionaries or individual values) are merged one after the other, in the order specified by `select_paths`. This means data from later sources can potentially overwrite data from earlier sources, depending on the rules (reducers).
3.  **Mapping (`map_phase`, Dictionary Merging Only):** When merging dictionaries (`merge_each_object_in_selected_list: True`), you can define rules *before* merging for how fields (keys) from the source objects map to the final merged object. This allows renaming fields or selecting specific nested values. You also decide the fate of fields not explicitly mapped (`unspecified_keys_strategy`: `auto_merge` or `ignore`). This phase is **ignored** when merging non-dictionaries (`merge_each_object_in_selected_list: False`).
4.  **Reduction (`reduce_phase`):**
    *   **Dictionary Merging:** When a field/key exists in both the current merged result ("left") and the new object being merged ("right"), a "reducer" rule determines the outcome.
    *   **Non-Dictionary Merging:** When merging a sequence of non-dictionary items, the `default_reducer` is applied sequentially to the current merged result ("left") and the next item ("right").
    *   You can set a `default_reducer` and, for dictionary merges, specific `reducers` for certain destination keys.
5.  **Transformation (`post_merge_transformations`):** After all items for a single operation have been merged, you can apply final transformations.
    *   **Dictionary Results:** Apply transformations to specific fields (using their `destination_key`) within the merged dictionary.
    *   **Non-Dictionary Results:** Apply **only the first listed transformation** to the *entire* final merged value. Any other transformations defined for that operation are ignored. For example, you could flatten a list and *then* limit its size using two sequential transformations in the configuration, but only the flatten would run if applied to a non-dictionary list. **Correction**: Multiple transformations *can* apply sequentially to a non-dictionary result; the output of one transformation becomes the input to the next one listed in the `post_merge_transformations` dictionary.
6.  **Operations:** Define multiple independent merge/transform tasks within one node. Each operation selects its data, applies its strategy, and saves its result to a unique `output_field_name`.

## Configuration (`NodeConfig`)

You configure the `MergeAggregateNode` within the `node_config` field of its entry in the `GraphSchema`.

```json
{
  "nodes": {
    "consolidate_data": {
      "node_id": "consolidate_data", // Unique ID for this node instance
      "node_name": "merge_aggregate", // ** Must be "merge_aggregate" **
      "node_config": { // This is the MergeObjectsConfigSchema
        "operations": [ // List of merge/transform operations
          // --- Operation 1: Merge User Dictionaries ---
          {
            "output_field_name": "user_profile",
            "select_paths": [
              "source_system_a.user",
              "source_system_b.data",
              "manual_overrides"
            ],
            "merge_each_object_in_selected_list": true, // Default: flatten lists, merge dicts
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
          // --- Operation 2: Combine List Values ---
          {
            "output_field_name": "all_tags",
            "select_paths": ["system_a_tags", "system_b_tags", "manual_tags"], // Paths point to lists or primitives
            "merge_each_object_in_selected_list": false, // Treat lists/values as atomic items
            "merge_strategy": {
              "reduce_phase": {
                "default_reducer": "combine_in_list" // Combine all selected items into a single list
                // 'reducers' dict is ignored here
              },
              "post_merge_transformations": {
                "flatten_tags": { // Apply to the combined list result
                  "operation_type": "recursive_flatten_list"
                },
                 "limit_tags": { // Can apply another transformation sequentially
                   "operation_type": "limit_list",
                   "operand": 10 // Keep only the first 10 tags after flattening
                 }
                // Multiple transformations can apply sequentially to non-dictionary results
              }
            }
          },
          // --- Operation 3: Transform a Single Object ---
          {
            "output_field_name": "processed_report",
            "select_paths": ["raw_report_data"], // Select just one object
            // merge_each_object_in_selected_list: true (default, applies to the single object)
            "merge_strategy": {
               // map_phase and reduce_phase might be empty or default if no merging needed
               "post_merge_transformations": {
                  "final_score": { "operation_type": "multiply", "operand": 10 },
                  "report_status": { "operation_type": "...", "operand": "..." }
                  // Multiple transformations can apply to different fields in the dictionary result
               }
            }
          }
          // Add more operation objects here
        ]
      }
    }
    // ... other nodes (e.g., nodes providing 'source_system_a', 'source_system_b', 'manual_overrides')
  }
  // ... other graph properties (edges etc.)
}
```

### Key Configuration Sections:

1.  **`operations`** (List): **Required**. A list where each item defines one independent merge or transformation task. They run in the order listed, but the result of one does *not* directly feed into the next (unless you design subsequent operations to select the output of previous ones).
2.  **Inside each `operations` item**:
    *   **`output_field_name`** (String): **Required**. The name of the field where the final result of *this specific merge operation* will be stored in the node's overall output. Must be unique across all operations in this node.
    *   **`select_paths`** (List of Strings): **Required**. Dot-notation paths to the source data in the input.
        *   Order matters! This defines the sequence of merging (left-to-right).
        *   How lists at these paths are handled depends on `merge_each_object_in_selected_list`.
    *   **`merge_each_object_in_selected_list`** (Boolean): **Optional, Default: `true`**.
        *   `true` (Default): If a path selects a list, the node iterates through it, merging each *dictionary* found sequentially. Non-dictionary items in the list are skipped. Use this for standard object merging.
        *   `false`: Treats the entire value found at each `select_path` (including lists) as a single, atomic item. Merges these values sequentially using only the `default_reducer`. **Crucially, all selected items must be non-dictionary types** (string, number, boolean, list, null). Dictionaries will cause an error in this mode.
    *   **`merge_strategy`** (Object): **Required**. Contains the detailed rules for this merge/transform operation.
        *   **`map_phase`** (Object): **(Used only if `merge_each_object_in_selected_list` is `true`)** Rules for handling fields *before* merging dictionary conflicts.
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
        *   **`reduce_phase`** (Object): Rules for resolving conflicts (dictionary merging) or combining sequential items (non-dictionary merging).
            *   `default_reducer` (String): The rule applied if no specific reducer is listed for the key. **Required** when `merge_each_object_in_selected_list` is `false`. For dictionary merges (`true`), defaults to `replace_right`.
            *   `reducers` (Object): **(Used only if `merge_each_object_in_selected_list` is `true`)** Map specific `destination_key` names (dot-notation supported) to specific reducer rules for dictionary fields, overriding the default.
                *   **Nested Paths:** Keys in this object *can be nested paths* (e.g., `"user.details.settings": "nested_merge_replace"`). When a conflict occurs during dictionary merging, the node looks for the *most specific matching reducer path* in this configuration. For example, if merging the `user` object triggers a conflict at `user.details.settings`, the reducer specified for that exact path will be used, potentially overriding a more general reducer defined for just `user`.
                *   Common Reducers:
                    *   `replace_right`: The value from the new source object overwrites the existing value. (Default for dict merge)
                    *   `replace_left`: Keep the existing value; ignore the value from the new source object.
                    *   `append`: Expects the left value to be a list. Appends the entire right value as a single new element to the list.
                    *   `extend`: Expects *both* values to be lists. Extends the left list with the elements from the right list.
                    *   `combine_in_list`: Creates a list containing `[left_value, right_value]`. If the left value is already a list, it appends the right value to it. Handles initial item correctly.
                    *   `sum`, `min`, `max`: Perform numerical aggregation (expects numbers).
                    *   `simple_merge_replace`: Expects both values to be dictionaries. Merges *top-level* keys from the right dictionary into the left. If keys collide, the right value replaces the left. Does *not* recurse into nested dictionaries.
                    *   `simple_merge_aggregate`: Expects both values to be dictionaries. Merges *top-level* keys. If keys collide, values are combined into a list (`[left_value, right_value]`). Does *not* recurse.
                    *   `nested_merge_replace`: Handles any value types. If *both* values are dictionaries, it merges them recursively, applying the 'replace' logic at each level. For non-dictionary collisions, the right value replaces the left (if not None).
                    *   `nested_merge_aggregate`: Handles any value types. This provides a deep aggregation:
                        *   If *both* values are dictionaries, it merges them recursively, applying the 'aggregate' logic at each level.
                        *   If *both* values are lists, it extends the left list with the non-None items from the right list.
                        *   If values have different types or are primitives (numbers, strings, booleans), they are combined into a list. If the left value is already a list, the right value is appended.
                        *   `None` values on the right side are ignored and do not get added to lists or overwrite existing values during aggregation.
            *   `error_strategy` (String): How to handle errors during reduction (e.g., trying to `sum` text). Default is `coalesce_keep_non_empty`. Options:
                *   `coalesce_keep_left`: Keep the original ("left") value.
                *   `coalesce_keep_non_empty`: **(Default)** Keep the original ("left") value if it exists and is considered "truthy" (not `null`, `false`, `0`, empty string/list/dict). Otherwise, use the new ("right") value. This is useful for accumulating values where the first non-empty value encountered should be kept if subsequent reductions fail.
                *   `skip_operation`: Keep the original ("left") value.
                *   `set_none`: Set the value to `null`.
                *   `fail_node`: Stop the node and report an error.
        *   **`post_merge_transformations`** (Object, Optional): Apply calculations/transformations *after* merging is complete.
            *   **Dictionary Results:** Maps `destination_key` names (dot-notation supported) to transformation rules. Multiple transformations can target different keys.
            *   **Non-Dictionary Results:** Maps arbitrary keys to transformation rules. **Caveat: Only the first transformation listed in this dictionary will be applied** to the single, final non-dictionary value. Others are ignored. **Correction:** Transformations are applied **sequentially** based on their order in the `post_merge_transformations` dictionary. The output of one transformation becomes the input for the next.
            *   Each rule specifies:
                *   `operation_type` (String): The calculation/transformation. Common types:
                    *   `average`: Calculates average (uses internal count of merged items for that key).
                    *   `multiply`, `divide`, `add`, `subtract`: Basic arithmetic (requires `operand`).
                    *   `recursive_flatten_list`: Flattens a potentially nested list into a single level. Expects the input value to be a list.
                    *   `limit_list`: Truncates a list to keep only the first N items (requires numeric `operand`). Expects the input value to be a list.
                    *   `sort_list`: Sorts a list. Specify the key (optional, dot-notation for nested keys in dictionaries, can be a list of keys for multi-level sort) and order (`ascending` or `descending`) in the `operand` dictionary. `None` values (both `None` items and items where the sort key resolves to `None`) are always placed at the end of the sorted list, regardless of the specified order.
                *   `operand` (Any, Optional): The value needed for the operation (e.g., the number to multiply by, the limit for `limit_list`, the sort configuration dictionary for `sort_list`). Required for most arithmetic and `limit_list`. Provide this *or* `operand_path`.
                *   `operand_path` (String, Optional): A dot-notation path within the node's *input data* to dynamically fetch the operand value. Use this if the operand isn't fixed but depends on other input data. Provide this *or* `operand`. Required for arithmetic/`limit_list` if `operand` isn't set.
        *   **`transformation_error_strategy`** (String): How to handle errors during transformations (e.g., `divide` by zero). Default is `skip_operation`. Same options as `error_strategy`.

## Using for Single-Object Transformations

You can use this node simply to apply transformations to a single object or value without complex merging.

**Scenario 1: Transform fields within a single dictionary**

1.  Set `select_paths` to point to the single dictionary you want to transform.
2.  Ensure `merge_each_object_in_selected_list` is `true` (default).
3.  Leave `map_phase` and `reduce_phase` with defaults or empty if no mapping/reduction is needed.
4.  Define your transformations in `post_merge_transformations`, targeting the specific fields within the dictionary by their keys.

**Scenario 2: Transform a single non-dictionary value (e.g., flatten a list)**

1.  Set `select_paths` to point to the single value (e.g., a list).
2.  Set `merge_each_object_in_selected_list` to `false`. (This is crucial, otherwise, it might try to merge items *within* the list if they were dictionaries).
3.  The `reduce_phase` will technically run with the `default_reducer` on the single item, but effectively just passes the item through.
4.  Define your transformation in `post_merge_transformations`. Give it any key (e.g., `"flatten_op"`).
    *   **Caveat:** If you define multiple transformations here, **only the first one listed will be applied** to the non-dictionary value. **Correction:** Multiple transformations can be applied sequentially. For example, define a `"flatten_op"` first, then a `"limit_op"` second.

## Input (`DynamicSchema`)

Input data (dictionary or `DynamicSchema`) containing the data referenced by `select_paths`.

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

-   Use this node when you need to combine information from different places into one structured object or value, especially when the same information might appear in multiple places and you need rules to decide which version to keep or how to combine them. It can also be used just to transform a single piece of data.
-   Think of it like creating a "best version" of a record by layering information from several sources, or applying a calculation to existing data.
-   **`operations`**: You can set up multiple independent combining/transforming tasks in one node. Each task gets its own name (`output_field_name`).
    -   `select_paths`: Tell the node where to find the data pieces for *this* task. The order you list them matters for some rules (like "keep the last value seen" or sequential non-dictionary reduction).
    -   `merge_each_object_in_selected_list`:
        -   `true` (Default): Good for combining multiple detailed records (dictionaries). If it finds a list, it looks *inside* for dictionaries to merge.
        -   `false`: Good for combining simple values or lists directly. Treats lists as single items. **Cannot be used if any selected item is a dictionary.**
    -   `merge_strategy`: The core instructions for combining/transforming.
        -   **`map_phase`** (Only for dictionary merging): Prepare the fields before merging. Use `key_mappings` to rename fields (e.g., `customer_id` -> `clientID`) or grab nested values. Use `unspecified_keys_strategy` to decide if other fields are included (`auto_merge`) or dropped (`ignore`). See the Configuration section for important nuances on `auto_merge`.
        -   **`reduce_phase`**: Handle overlaps (dict merging) or combine sequence (non-dict merging). Use `default_reducer` to pick the main rule (e.g., `replace_right`, `combine_in_list`, `sum`). For dictionary merging, you can use `reducers` to apply special rules for specific fields (even nested ones like `user.settings`). Use `nested_merge_replace` or `nested_merge_aggregate` to combine complex nested dictionary data deeply.
        -   **`post_merge_transformations`**: Final tweaks after combining. If the result is a dictionary, you can transform multiple fields (e.g., calculate an `average`, `multiply` a value). If the result is *not* a dictionary (e.g., a number, a list), **Correction:** Transformations apply sequentially (e.g., flatten then limit). Use `recursive_flatten_list` to turn `[1, [2, 3], [[4]]]` into `[1, 2, 3, 4]`. Use `limit_list` (with an `operand` or `operand_path` pointing to the limit number) to keep only the first few items of a list. Use `sort_list` (with an `operand` or `operand_path` specifying sort criteria) to order items.
-   **Single Item Transformation:** You *can* use this node to just transform one piece of data. Select only that piece in `select_paths`. If it's a dictionary, use transformations as normal. If it's a list or value, set `merge_each_object_in_selected_list` to `false` and define one or more transformations in `post_merge_transformations` - they will apply sequentially. Use `operand` for fixed values or `operand_path` to get values from the input.
-   **Dot Notation:** Use dots (`.`) to access data inside objects (e.g., `customer.address.zipcode`).
-   **It Modifies a Copy:** The node doesn't change the original input data; it creates a new combined result in its output field (`merged_data`).
-   Connect the necessary input data sources to this node using edges and mappings. Connect the `merged_data` field (or a specific field *inside* it like `merged_data.my_output_name`) to the next node that needs the combined result.

## Comparison to DataJoinNode

-   `MergeAggregateNode`: Combines *multiple sources* into *one output object/value* based on sequence and rules. Good for consolidation or sequential processing/transformation.
-   `DataJoinNode`: Links items *between two lists/objects* based on matching key values (like a database join). It typically *nests* the matched 
item(s) from the second list inside the corresponding item of the first list. Good for enriching items in one list with related details from 
another.
