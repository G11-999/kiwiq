# Usage Guide: FilterNode

This guide explains how to configure and use the `FilterNode` to selectively filter data within your workflows based on defined conditions.

## Purpose

The `FilterNode` acts like a sieve for your data. It allows you to:
-   **Keep or Remove Entire Data Objects:** Decide whether the entire input data object should pass through based on conditions evaluating the *entire* object's data.
-   **Filter Items within Lists:** Selectively keep or remove specific items from a list based on conditions applied to those items or their sub-fields.
-   **Keep or Remove Specific Fields:** Selectively keep or delete certain fields (or nested fields) from the data if they meet specific conditions, potentially based on the values of *other* fields.

This is useful for cleaning data, selecting relevant information, removing sensitive fields, or preparing data before it goes to the next step in the workflow.

## Configuration (`NodeConfig`)

You configure the `FilterNode` within the `node_config` field of its entry in the `GraphSchema`.

```json
{
  "nodes": {
    "my_data_filter": {
      "node_id": "my_data_filter", // Unique ID for this node instance
      "node_name": "filter_data",  // ** Must be "filter_data" **
      "node_config": { // This is the FilterTargets schema
        "targets": [ // A list of filter rules to apply, executed in order.
          // --- Example 1: Filter the whole object (ALLOW mode) ---
          // Keep the *entire* object ONLY IF user is active.
          {
            "filter_target": null, // 'null' means apply to the entire input object
            "filter_mode": "allow", // Keep the object ONLY IF conditions pass
            "condition_groups": [
              {
                "conditions": [
                  { "field": "user.status", "operator": "equals", "value": "active" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          // --- Example 2: Filter items within a list (DENY mode) ---
          // Remove orders that are 'cancelled' OR have a value less than 10.
          {
            "filter_target": "orders", // Path to the list field to filter
            "filter_mode": "deny",     // REMOVE list items IF conditions pass
            "condition_groups": [
              { // Group 1: Check status
                "conditions": [
                  // Condition applies to fields *within* each 'orders' item
                  { "field": "status", "operator": "equals", "value": "cancelled" }
                ],
                "logical_operator": "and"
              },
              { // Group 2: Check value
                "conditions": [
                   { "field": "value", "operator": "less_than", "value": 10 }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "or", // Combine the groups with OR: Remove if Group 1 OR Group 2 passes.
            "nested_list_logical_operator": "and" // How to handle conditions on nested lists within list items (usually AND)
          },
          // --- Example 3: Remove a specific field conditionally (DENY mode) ---
          // Remove 'user.internal_notes' field IF 'metadata.is_sensitive' is true.
          {
            "filter_target": "user.internal_notes", // Path to the field to potentially remove
            "filter_mode": "deny", // REMOVE this field IF conditions pass
            "condition_groups": [
              {
                "conditions": [
                  // Condition uses data from elsewhere in the object
                  { "field": "metadata.is_sensitive", "operator": "equals", "value": true }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          // --- Example 4: Filter list items based on properties of sub-objects (ALLOW mode) ---
          // Keep products ONLY IF their 'details.in_stock' field is true.
          {
            "filter_target": "products", // Path to a list named 'products'
            "filter_mode": "allow",    // Keep items only if the condition passes
            "condition_groups": [
              {
                "conditions": [
                  // Check a field *inside* an object *within* each list item
                  { "field": "details.in_stock", "operator": "equals", "value": true }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and",
            "nested_list_logical_operator": "and"
          },
          // --- Example 5: Filtering based on list field content (using apply_to_each_value_in_list_field) ---
          // Keep the *entire user object* only if *any* tag in the 'user.tags' list is "priority".
          {
            "filter_target": null, // Apply to the whole object based on a list condition
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  {
                    "field": "user.tags", // The list field itself
                    "operator": "equals", // Check each item for equality
                    "value": "priority",
                    "apply_to_each_value_in_list_field": true, // Check *each item* in the list
                    "list_field_logical_operator": "or" // Pass if *any* tag equals "priority"
                  }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          // --- Example 6: Keep only specific fields using ALLOW mode ---
          // Keep *only* the 'name' and 'age' fields within the 'person' object.
          // Note: You need separate targets for each field you want to keep.
          {
            "filter_target": "person.name",
            "filter_mode": "allow",
            "condition_groups": [{ "conditions": [{ "field": "person.name", "operator": "is_not_empty" }] }]
          },
          {
            "filter_target": "person.age",
            "filter_mode": "allow",
            "condition_groups": [{ "conditions": [{ "field": "person.age", "operator": "is_not_empty" }] }]
          },
          // --- Example 7: Dynamic comparison using value_path ---
          // Keep orders only if their value is greater than their individual threshold
          {
            "filter_target": "orders",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  // Compare order.value against order.threshold_value dynamically
                  { "field": "value", "operator": "greater_than", "value_path": "threshold_value" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          // --- Example 8: Cross-field comparison using value_path ---
          // Keep users only if their age meets the minimum requirement from settings
          {
            "filter_target": "users",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "users.age", "operator": "greater_than_or_equals", "value_path": "settings.min_age" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          }
        ],
        "non_target_fields_mode": "allow" // Controls whether fields not explicitly targeted should be allowed (default) or denied
      }
      // dynamic_input_schema / dynamic_output_schema usually not needed unless interacting with dynamic graph state
    }
    // ... other nodes
  }
  // ... other graph properties
}
```

### Key Configuration Sections:

1.  **`targets`** (List): A list where each item defines a specific filtering rule. Rules are applied sequentially. Object-level filters (`filter_target: null`) run first, then list filters, then field filters.
2.  **`non_target_fields_mode`** (String: `"allow"` or `"deny"`, Default: `"allow"`): Controls how fields not explicitly targeted by filter rules are handled:
    *   `"allow"` (Default): Keep all fields that aren't explicitly targeted in the final output. Only fields specifically targeted with conditions that fail will be removed.
    *   `"deny"`: Remove all fields that aren't explicitly targeted with `filter_mode: "allow"`. This creates a "whitelist" approach where only fields explicitly allowed will appear in the output.
3.  **Inside each `target`**:
    *   **`filter_target`** (String | `null`):
        *   `null`: The rule applies to the *entire input data object*. Use this to decide if the whole object passes or gets filtered out based on conditions evaluated against the full data. Only one target can have `filter_target: null`.
        *   `"path.to.list"`: The rule applies to *items within the list* found at this path (e.g., `"orders"`). Conditions will be evaluated against each item in the list. Use this to remove specific list items.
        *   `"path.to.field"`: The rule applies to a *specific field* (e.g., `"user.profile.address"`). Use `filter_mode: "deny"` to remove this field if conditions pass, or `filter_mode: "allow"` to *keep only this field* if conditions pass (potentially removing sibling fields if they aren't also targeted with `allow`).
    *   **`filter_mode`** (String: `"allow"` or `"deny"`):
        *   `"allow"` (Default): **Keep** the data (object, list item, or field) *only if* the overall conditions for this target evaluate to `true`. Remove/exclude it if `false`. Useful for selecting specific items or fields.
        *   `"deny"`: **Remove** the data (object, list item, or field) *if* the overall conditions for this target evaluate to `true`. Keep it if `false`. Useful for excluding specific items or removing sensitive fields.
    *   **`condition_groups`** (List): One or more groups of conditions. All conditions within a group are evaluated first.
    *   **`group_logical_operator`** (String: `"and"` or `"or"`): How to combine the boolean results (`true`/`false`) of the `condition_groups` to get the final result for *this target*. `and` means all groups must pass; `or` means at least one group must pass.
    *   **Inside each `condition_group`**:
        *   **`conditions`** (List): One or more individual conditions.
        *   **`logical_operator`** (String: `"and"` or `"or"`): How to combine the boolean results (`true`/`false`) of the `conditions` *within this group*. `and` means all conditions in this group must pass for the group to be true; `or` means at least one condition must pass.
        *   **Inside each `condition`**:
            *   **`field`** (String): Dot-notation path to the data field to check (e.g., `"user.id"`, `"items.price"`, `"metadata.source"`).
                *   When `filter_target` is a list path (e.g., `"orders"`), the `field` path is *relative to each item* being evaluated in the list (e.g., `field: "status"` checks `order_item.status`).
                *   However, you can still reference fields *outside* the current list item using the full path from the root (e.g., `field: "global_flag"` inside an `"orders"` target checks the top-level `global_flag` for *each* order being evaluated). See `test_list_item_filter_absolute_cond`.
                *   If `apply_to_each_value_in_list_field` is true, this `field` should be the path to the list field itself (e.g., `user.tags`).
            *   **`operator`** (String): The comparison to perform. Available operators:
                *   `"equals"`: Field value is exactly equal to `value`.
                *   `"equals_any_of"`: Field value is equal to *any* item in the `value` list (e.g., `value: ["admin", "editor"]`).
                *   `"not_equals"`: Field value is not equal to `value`.
                *   `"greater_than"`: Field value > `value` (numeric comparison).
                *   `"less_than"`: Field value < `value` (numeric comparison).
                *   `"greater_than_or_equals"`: Field value >= `value` (numeric comparison).
                *   `"less_than_or_equals"`: Field value <= `value` (numeric comparison).
                *   `"contains"`: Field value (string, list, tuple, set, dict) contains the `value`. For dicts, checks if `value` is a key.
                *   `"not_contains"`: Field value does not contain the `value`.
                *   `"starts_with"`: Field value (string) starts with `value`.
                *   `"ends_with"`: Field value (string) ends with `value`.
                *   `"is_empty"`: Field value is `null` (None), `""` (empty string), `[]` (empty list), or `{}` (empty dict). Ignores `value`. **Returns `true` if the field path does not exist.**
                *   `"is_not_empty"`: Field value is not empty. Ignores `value`. **Returns `false` if the field path does not exist.**
            *   **`value`** (Any | `null`): The value to compare against. Required for most operators. For `equals_any_of`, this must be a list. Not used for `is_empty` / `is_not_empty`.
            *   **`value_path`** (String, Optional): Instead of providing a static `value`, you can specify a dot-notation path to another field in the data to use as the comparison value. This allows for dynamic comparisons between fields (e.g., `{"field": "order.total", "operator": "greater_than", "value_path": "order.minimum_threshold"}`). Note: You cannot provide both `value` and `value_path` in the same condition.
            *   **`apply_to_each_value_in_list_field`** (Boolean, Default: `false`): **Important for checking list contents.** If the `field` points to a list (e.g., `"user.tags"`) and this is `true`, the `operator` (like `equals`, `greater_than`) and `value` will be applied to *each individual item* within that list. The results from each item are combined using `list_field_logical_operator`. If `false` (default), the operator applies to the list *as a whole* (e.g., `contains` checks if the `value` exists *anywhere* in the list). See Example 5 vs `test_nested_list_cond_path_single_list_or`.
            *   **`list_field_logical_operator`** (String: `"and"` or `"or"`, Default: `"and"`): Used only when `apply_to_each_value_in_list_field` is `true`. Determines how the results from checking each list item are combined to give the final result for this condition. `and` means the condition passes only if it's true for *all* items in the list. `or` means it passes if true for *at least one* item.
    *   **`nested_list_logical_operator`** (String: `"and"` or `"or"`, Default: `"and"`): How to combine results when evaluating conditions on nested lists *within* list items (e.g., if filtering `orders` and a condition checks `order.items.category == 'X'`). Defines if *all* nested items must match (`and`) or *any* (`or`).

## Dynamic Value Comparison with `value_path`

The `value_path` feature allows you to create dynamic comparisons where the comparison value is extracted from another field in your data, rather than using a static value. This is particularly powerful for:

- **Threshold-based filtering**: Compare values against thresholds stored elsewhere in the data
- **Cross-field validation**: Ensure one field meets criteria relative to another field
- **Configuration-driven filtering**: Use configuration values stored in the data to drive filtering logic

### How `value_path` Works

When you specify `value_path` instead of `value` in a condition:

1. **Value Resolution**: Before evaluating the condition, the system navigates to the specified path and extracts the value
2. **Dynamic Comparison**: The extracted value is then used as the comparison value for the condition
3. **Nested List Support**: When `value_path` points to data within nested lists, the system uses `fetch_nested_list_items=True` to collect values from all matching locations

### `value_path` Examples

#### Basic Cross-Field Comparison
```json
{
  "filter_target": "users",
  "filter_mode": "allow",
  "condition_groups": [{
    "conditions": [{
      "field": "users.age",
      "operator": "greater_than_or_equals",
      "value_path": "settings.minimum_age"  // Compare against dynamic threshold
    }]
  }]
}
```

**Input Data:**
```json
{
  "settings": { "minimum_age": 25 },
  "users": [
    {"id": 1, "name": "Alice", "age": 30},
    {"id": 2, "name": "Bob", "age": 22}
  ]
}
```

**Result:** Only Alice (age 30 ≥ 25) is kept.

#### Multiple Dynamic Thresholds
```json
{
  "filter_target": "products",
  "filter_mode": "allow",
  "condition_groups": [{
    "conditions": [
      {
        "field": "products.price",
        "operator": "less_than_or_equals",
        "value_path": "budget.max_price"
      },
      {
        "field": "products.stock",
        "operator": "greater_than_or_equals",
        "value_path": "requirements.min_stock"
      }
    ],
    "logical_operator": "and"
  }]
}
```

#### Deeply Nested Value Paths
```json
{
  "field": "transaction.amount",
  "operator": "greater_than",
  "value_path": "security.settings.risk.thresholds.high_value_transaction"
}
```

### `value_path` with Lists

When `value_path` points to data within lists, the system automatically handles the complexity:

```json
{
  "field": "order.total",
  "operator": "greater_than",
  "value_path": "customer.preferences.spending_limits.daily_max"
}
```

If the path crosses multiple lists, the system will collect all matching values and use them appropriately for the comparison.

### Error Handling for `value_path`

- **Non-existent Path**: If the `value_path` doesn't exist, the extracted value will be `None`
- **Comparison with None**: Most operators will evaluate to `false` when comparing against `None`
- **Type Mismatches**: The system handles type mismatches gracefully, typically resulting in `false` evaluations

## Advanced List Processing with `fetch_nested_list_items`

The `fetch_nested_list_items` parameter is an internal mechanism that controls how the system handles value extraction when paths cross multiple nested lists. While you don't directly configure this parameter, understanding its behavior helps explain how complex nested data structures are processed.

### When `fetch_nested_list_items` is Used

This mechanism is automatically activated when:

1. **`value_path` Resolution**: When resolving a `value_path` that crosses nested lists
2. **Complex Data Traversal**: When the system encounters lists while navigating to extract comparison values

### Behavior with Nested Lists

Consider this data structure:
```json
{
  "departments": [
    {
      "name": "Engineering",
      "teams": [
        {"name": "Backend", "members": [{"name": "Alice", "salary": 75000}]},
        {"name": "Frontend", "members": [{"name": "Bob", "salary": 70000}]}
      ]
    },
    {
      "name": "Sales", 
      "teams": [
        {"name": "Enterprise", "members": [{"name": "Charlie", "salary": 80000}]}
      ]
    }
  ]
}
```

When using a `value_path` like `"departments.teams.members.salary"`, the system:

1. **Traverses Lists**: Navigates through each department, then each team, then each member
2. **Collects Values**: Gathers all salary values: `[75000, 70000, 80000]`
3. **Returns Collection**: Provides the collected values for comparison

### Practical Implications

This automatic handling means you can write conditions that work across complex nested structures without worrying about the traversal logic:

```json
{
  "field": "current_user.salary",
  "operator": "greater_than",
  "value_path": "company.departments.teams.members.salary"  // Gets all salaries for comparison
}
```

The system will automatically handle the nested list traversal and provide meaningful comparison values.

### Handling Non-Existent Fields

-   **Condition Fields:** If a `field` specified in a condition does *not* exist in the data:
    -   Operators like `equals`, `greater_than`, `contains`, `starts_with`, `ends_with` will generally evaluate to `false`.
    -   `is_empty` will evaluate to `true`.
    -   `is_not_empty` will evaluate to `false`.
    -   `not_equals` might evaluate to `true` (since `None != value`).
    -   `not_contains` will evaluate to `true`.
-   **Target Fields:** If a `filter_target` path does not exist in the data, that specific target rule is skipped gracefully without error. The rest of the data remains unchanged by that rule.
-   **Value Paths:** If a `value_path` doesn't exist, the condition will typically evaluate to `false` (except for operators like `not_equals` or `not_contains`).

## Using Non-Target Fields Mode for Comprehensive Field Filtering

The `non_target_fields_mode` configuration provides a powerful way to control which fields appear in the filtered output:

### Default Behavior (non_target_fields_mode = "allow")

By default, the filter only removes fields explicitly targeted and filtered by rules. All other fields remain untouched.

### Whitelist Pattern (non_target_fields_mode = "deny")

When set to `"deny"`, any field not explicitly targeted with `filter_mode: "allow"` will be removed from the output. This creates a whitelist pattern where you must explicitly specify each field to keep.

```json
{
  "node_config": {
    "targets": [
      {"filter_target": "user.name", "filter_mode": "allow", "condition_groups": [
        {"conditions": [{"field": "user.name", "operator": "is_not_empty"}]}
      ]},
      {"filter_target": "user.email", "filter_mode": "allow", "condition_groups": [
        {"conditions": [{"field": "user.email", "operator": "is_not_empty"}]}
      ]}
    ],
    "non_target_fields_mode": "deny"
  }
}
```

With this configuration, only `user.name` and `user.email` will appear in the output if they pass their conditions. All other fields (like `user.address`, `user.phone`, etc.) will be removed even if they weren't explicitly targeted by a rule.

This is particularly useful for:
- Creating strict data schemas for downstream nodes
- Implementing comprehensive PII removal
- Ensuring only explicitly allowed fields pass through

#### Handling Fields Within Nested Lists

When using `non_target_fields_mode: "deny"` with nested lists, you have two options:

**Option 1: Preserve the entire list item structure**

If you explicitly allow the list itself but don't specify any fields within its items, the list will be treated as a self-contained unit. Each list item that passes any filter conditions will be preserved completely with all its original fields and nested structures.

```json
{
  "node_config": {
    "targets": [
      // Allow the orders list - only orders with status="completed" will remain
      {"filter_target": "orders", "filter_mode": "allow", "condition_groups": [
        {"conditions": [{"field": "orders.status", "operator": "equals", "value": "completed"}]}
      ]}
    ],
    "non_target_fields_mode": "deny"
  }
}
```

This will keep only orders with status="completed", but each remaining order item will retain all its original fields (id, total, items, shipping, etc.). This approach treats the list as already pre-filtered by its own conditions.

**Option 2: Select specific fields within list items**

Alternatively, you can explicitly allow both the list and specific fields within its items:

```json
{
  "node_config": {
    "targets": [
      // Allow the orders list
      {"filter_target": "orders", "filter_mode": "allow", "condition_groups": [
        {"conditions": [{"field": "orders", "operator": "is_not_empty"}]}
      ]},
      // Allow specific fields within orders
      {"filter_target": "orders.id", "filter_mode": "allow", "condition_groups": [
        {"conditions": [{"field": "orders.id", "operator": "is_not_empty"}]}
      ]},
      {"filter_target": "orders.total", "filter_mode": "allow", "condition_groups": [
        {"conditions": [{"field": "orders.total", "operator": "is_not_empty"}]}
      ]}
    ],
    "non_target_fields_mode": "deny"
  }
}
```

This will preserve the `orders` list but keep only the `id` and `total` fields within each order item. Other fields like `orders.date` or `orders.shipping` will be removed from each item.

## Input (`DynamicSchema`)

The `FilterNode` typically receives the entire data object from the previous node or the central graph state. The specific fields it expects depend entirely on the `field` paths used in your conditions.

-   Data can be passed via incoming `EdgeSchema` mappings directly to the node, or implicitly via the graph's central state if edges connect to/from `GRAPH_STATE_SPECIAL_NODE_NAME`.

## Output (`FilterOutputSchema`)

The node produces data matching the `FilterOutputSchema`:

-   **`filtered_data`** (Dict[str, Any] | `null`):
    *   If the filtering resulted in keeping the data (potentially modified by removing list items or fields), this field contains the resulting dictionary. Objects/lists might be empty if all their contents were filtered out.
    *   If an object-level filter (`filter_target: null`) caused the entire object to be filtered out (e.g., `filter_mode: "allow"` and conditions failed, or `filter_mode: "deny"` and conditions passed), this field will be `null`.
    *   If an error occurred during filtering, this might also be `null`.

## Example `GraphSchema` Snippet

```json
{
  "nodes": {
    "load_user_data": { /* ... node that outputs user data with orders ... */ },
    "filter_orders_and_pii": {
      "node_id": "filter_orders_and_pii",
      "node_name": "filter_data",
      "node_config": {
        "targets": [
          // Rule 1: Keep only shipped/completed orders with value >= 50
          {
            "filter_target": "orders", // Target the 'orders' list
            "filter_mode": "allow",   // Keep only orders that match
            "condition_groups": [
              {
                "conditions": [
                  { "field": "status", "operator": "equals_any_of", "value": ["shipped", "completed"] },
                  { "field": "value", "operator": "greater_than_or_equals", "value": 50 }
                ],
                "logical_operator": "and" // Must be shipped/completed AND value >= 50
              }
            ],
            "group_logical_operator": "and"
          },
          // Rule 2: Remove user's age field (example of PII removal)
          {
            "filter_target": "user.age",
            "filter_mode": "deny", // Remove if condition passes (always passes here)
            "condition_groups": [{ "conditions": [{ "field": "user.age", "operator": "is_not_empty"}]}]
          },
          // Rule 3: Dynamic comparison using value_path
          {
            "filter_target": "orders",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  // Compare order.value against order.threshold_value dynamically
                  { "field": "value", "operator": "greater_than", "value_path": "threshold_value" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          // Rule 4: Cross-field comparison with value_path
          {
            "filter_target": "users",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  // Compare user age against global minimum age setting
                  { "field": "users.age", "operator": "greater_than_or_equals", "value_path": "settings.minimum_user_age" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          }
        ],
        "non_target_fields_mode": "allow" // Default behavior: keep fields not explicitly targeted
      }
    },
    "process_filtered_data": { /* ... node that uses the filtered data ... */ }
  },
  "edges": [
    {
      "src_node_id": "load_user_data",
      "dst_node_id": "filter_orders_and_pii",
      "mappings": [] // Assumes data flows via central state or direct input passthrough
    },
    {
      "src_node_id": "filter_orders_and_pii",
      "dst_node_id": "process_filtered_data",
      "mappings": [
        // Map the output of the filter node
        { "src_field": "filtered_data", "dst_field": "cleaned_user_data" }
      ]
    }
  ],
  "input_node_id": "...",
  "output_node_id": "..."
}
```

## Notes for Non-Coders

-   Think of this node as setting rules to decide what data to keep or throw away.
-   `filter_target`: Tells the node *what* you want to filter:
    -   The whole data (`null`)
    -   Items in a specific list (`"list_name"`)
    -   A single field (`"field_name"`)
-   `filter_mode`:
    -   `"allow"`: **Keep ONLY IF** rules match. Good for selecting specific things.
    -   `"deny"`: **REMOVE IF** rules match. Good for excluding bad data or sensitive fields.
-   `non_target_fields_mode`:
    -   `"allow"` (default): Fields you didn't mention in your rules stay untouched.
    -   `"deny"`: Only fields you explicitly targeted with `"allow"` remain in your data; everything else gets removed.
    -   **When working with lists**: If you use `"deny"` mode with lists (like `"customers"` or `"orders"`), you have two options:
        -   **Option 1 - Keep everything in list items**: If you only allow the list itself (e.g., `"orders"`), any list items that pass your filter conditions will keep all their fields intact. This is useful when you want to filter which items appear but keep their complete structure.
        -   **Option 2 - Pick specific fields in list items**: If you allow both the list (e.g., `"orders"`) AND specific fields within it (e.g., `"orders.id"`, `"orders.total"`), only those specific fields will be kept in each list item.
-   `conditions`: These are your rules.
    -   `field`: Which piece of data are you looking at? (e.g., `"customer_status"`, `"order_total"`, `"tags"`)
    -   `operator`: How are you comparing it? (e.g., `equals`, `greater_than`, `contains`, `is_empty`, `starts_with`)
    -   `value`: What are you comparing it to? (e.g., `"active"`, `100`, `"important"`, `["admin", "editor"]` for `equals_any_of`)
    -   `value_path`: Instead of a fixed value, use the value from another field in your data (e.g., compare `"current_spend"` against `"budget_limit"`). This is great for dynamic thresholds and configuration-driven filtering.
-   You can group conditions with `and` (all must be true) or `or` (at least one must be true).
-   Use `apply_to_each_value_in_list_field: true` with an operator like `equals` or `greater_than` if you want to check *every item* inside a list field (like checking if *any* tag in a `tags` list is `"urgent"` using `logical_operator: "or"`).
-   If a field in your condition doesn't exist, the rule usually fails (unless using `is_empty`).
-   The output is usually named `filtered_data`. Connect this to the next node that needs the cleaned-up information. 