# Usage Guide: IfElseConditionNode

This guide explains how to configure and use the `IfElseConditionNode` to create decision points and control the flow of your workflow based on data conditions.

## Purpose

The `IfElseConditionNode` acts like a traffic controller or a fork in the road for your workflow. It allows you to:
-   Evaluate one or more sets of conditions against the current data.
-   Determine if the overall conditions evaluate to `true` or `false`.
-   **Output which branch (`true_branch` or `false_branch`) should be taken next.**

This is essential for building workflows that adapt their behavior based on the data they are processing, such as routing leads based on qualification criteria, handling different types of user requests, or implementing approval steps.

**Important:** This node *determines* the desired branch but does *not* perform the actual routing action in the workflow execution graph. You typically need to connect its output to a **Router Node** (like `DynamicRouterNode` or a custom router) which will read the `branch` output and direct the flow accordingly.

## Configuration (`NodeConfig`)

You configure the `IfElseConditionNode` within the `node_config` field of its entry in the `GraphSchema`.

```json
{
  "nodes": {
    "check_lead_qualification": {
      "node_id": "check_lead_qualification", // Unique ID for this node instance
      "node_name": "if_else_condition", // ** Must be "if_else_condition" **
      "node_config": { // This is the IfElseConfigSchema
        "tagged_conditions": [ // A list of named condition sets to evaluate
          // --- Tag 1: Check for High Score OR Priority Flag ---
          {
            "tag": "high_value_or_priority", // Unique name for this condition set
            "condition_groups": [
              {
                "conditions": [
                  { "field": "lead.score", "operator": "greater_than_or_equals", "value": 70 }
                ],
                "logical_operator": "and"
              },
              {
                "conditions": [
                    { "field": "lead.flags", "operator": "contains", "value": "priority"}
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "or" // Pass if score >= 70 OR flags contains "priority"
          },
          // --- Tag 2: Check for Contact Info and Recent Activity ---
          {
            "tag": "contactable_and_active",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "lead.email", "operator": "is_not_empty" },
                  { "field": "lead.last_activity_days_ago", "operator": "less_than", "value": 30 }
                ],
                "logical_operator": "and" // Must have email AND be active recently
              }
            ],
            "group_logical_operator": "and",
            "nested_list_logical_operator": "and"
          },
          // --- Tag 3: Compare fields dynamically using value_path ---
          {
            "tag": "spending_exceeds_budget",
            "condition_groups": [
              {
                "conditions": [
                  // Compare current_spend against their budget_limit dynamically
                  { "field": "customer.current_spend", "operator": "greater_than", "value_path": "customer.budget_limit" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          // --- Tag 4: Dynamic threshold comparison ---
          {
            "tag": "meets_premium_criteria",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "user.account.balance", "operator": "greater_than_or_equals", "value_path": "app_config.thresholds.premium_min_balance" },
                  { "field": "user.age", "operator": "greater_than_or_equals", "value_path": "app_config.thresholds.premium_min_age" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          }
        ],
        // How to combine results of the *tags*: Both tags must pass.
        "branch_logic_operator": "and"
      }
      // dynamic_input_schema / dynamic_output_schema usually not needed
    },
    // --- Subsequent Nodes --- 
    // The actual routing is done here based on the output of 'check_lead_qualification'
    "qualification_router": { 
      "node_id": "qualification_router",
      "node_name": "approval_router", // Or another dynamic router type
      "node_config": {
        "field_name": "branch", // Check the 'branch' output from the IfElse node
        "field_value": "true_branch", // Value corresponding to the true path
        "route_if_true": "assign_to_sales", // Node ID for true branch
        "route_if_false": "send_to_nurturing", // Node ID for false branch
        "choices": ["assign_to_sales", "send_to_nurturing"], // Possible routes
        "allow_multiple": false
      }
    },
    "assign_to_sales": { "node_id": "assign_to_sales" /* ... */ },
    "send_to_nurturing": { "node_id": "send_to_nurturing" /* ... */ }
    // ... other nodes
  }
  // ... other graph properties like edges
}
```

### Key Configuration Sections:

1.  **`tagged_conditions`** (List): A list where each item defines a named set of conditions to evaluate. Each item in this list must have a unique `tag`.
2.  **Inside each `tagged_condition`**:
    *   **`tag`** (String): **Required**. A unique name or identifier for this specific condition set (e.g., `"is_urgent"`, `"needs_manager_approval"`). This helps in understanding the output.
    *   **`condition_groups`** (List): One or more groups of conditions. Works exactly like in the `FilterNode`.
    *   **`group_logical_operator`** (String: `"and"` or `"or"`): How to combine the boolean results (`true`/`false`) of the `condition_groups` *within this tag*. `and` means all groups must pass for this tag to be true; `or` means at least one group must pass.
    *   **`nested_list_logical_operator`** (String: `"and"` or `"or"`): How to combine results when evaluating conditions on nested lists. Works exactly like in the `FilterNode`.
    *   **Conditions within `condition_groups`**: Each `condition` has `field`, `operator`, and `value` (and list options like `apply_to_each_value_in_list_field`), working exactly as described in the `FilterNode` guide. Handles non-existent fields similarly (usually evaluating to `false` except for `is_empty`).
    *   **Inside each `condition`**:
        *   **`field`** (String): Dot-notation path to the data field to check (e.g., `"user.id"`, `"items.price"`, `"metadata.source"`).
        *   **`operator`** (String): The comparison to perform. See the full list of operators at the end of this guide.
        *   **`value`** (Any | `null`): The value to compare against. Required for most operators.
        *   **`value_path`** (String, Optional): Instead of providing a static `value`, you can specify a dot-notation path to another field in the data to use as the comparison value. This enables dynamic comparisons between fields (e.g., `{"field": "lead.score", "operator": "greater_than", "value_path": "lead.qualification_threshold"}`). Note: You cannot provide both `value` and `value_path` in the same condition.
        *   **`apply_to_each_value_in_list_field`** (Boolean, Default: `false`): When set to `true` and the `field` points to a list, applies the operator to each value in the list and combines results with the `list_field_logical_operator`.
        *   **`list_field_logical_operator`** (String: `"and"` or `"or"`, Default: `"and"`): Used when `apply_to_each_value_in_list_field` is `true` to combine results from evaluating each item in a list.
3.  **`branch_logic_operator`** (String: `"and"` or `"or"`): **Crucial**. This determines how the boolean results (`true`/`false`) of *all* the `tagged_conditions` are combined to get the final overall result (`condition_result` in the output).
    *   `"and"`: The final result is `true` **only if** *all* tagged conditions evaluate to `true`.
    *   `"or"`: The final result is `true` **if** *at least one* tagged condition evaluates to `true`.

## Dynamic Value Comparison with `value_path`

The `value_path` feature allows you to create dynamic decision logic where comparison values are extracted from other fields in your data, rather than using static values. This is particularly powerful for:

- **Configuration-driven decisions**: Use settings stored in the data to drive branching logic
- **Threshold-based routing**: Compare values against dynamic thresholds for intelligent routing
- **Cross-field validation**: Make decisions based on relationships between different data fields
- **Adaptive workflows**: Create workflows that adjust their behavior based on runtime data

### How `value_path` Works in IfElse Nodes

When you specify `value_path` instead of `value` in a condition:

1. **Value Resolution**: Before evaluating the condition, the system navigates to the specified path and extracts the value
2. **Dynamic Comparison**: The extracted value is then used as the comparison value for the condition
3. **Nested List Support**: When `value_path` points to data within nested lists, the system uses `fetch_nested_list_items=True` to collect values from all matching locations
4. **Branch Decision**: The results influence which branch (`true_branch` or `false_branch`) is selected

### `value_path` Examples for Decision Making

#### Basic Dynamic Threshold Check
```json
{
  "tag": "premium_eligible",
  "condition_groups": [{
    "conditions": [
      {
        "field": "user.account.balance",
        "operator": "greater_than_or_equals",
        "value_path": "app_config.thresholds.premium_min_balance"
      },
      {
        "field": "user.age",
        "operator": "greater_than_or_equals",
        "value_path": "app_config.thresholds.premium_min_age"
      }
    ],
    "logical_operator": "and"
  }]
}
```

**Input Data:**
```json
{
  "user": {
    "account": { "balance": 1500 },
    "age": 35
  },
  "app_config": {
    "thresholds": {
      "premium_min_balance": 1000,
      "premium_min_age": 25
    }
  }
}
```

**Result:** `premium_eligible` evaluates to `true` (1500 ≥ 1000 AND 35 ≥ 25).

#### Security Risk Assessment
```json
{
  "tag": "high_risk_transaction",
  "condition_groups": [{
    "conditions": [
      {
        "field": "transaction.amount",
        "operator": "greater_than",
        "value_path": "security.settings.risk.thresholds.high_value_transaction"
      },
      {
        "field": "transaction.risk_score",
        "operator": "greater_than_or_equals",
        "value_path": "security.settings.risk.thresholds.suspicious_score"
      }
    ],
    "logical_operator": "or"  // High risk if EITHER condition is true
  }]
}
```

#### Multi-Level Configuration Comparison
```json
{
  "tag": "requires_approval",
  "condition_groups": [
    {
      "conditions": [
        {
          "field": "request.amount",
          "operator": "greater_than",
          "value_path": "user.approval_limits.single_transaction"
        }
      ]
    },
    {
      "conditions": [
        {
          "field": "request.category",
          "operator": "equals_any_of",
          "value_path": "company.policies.restricted_categories"
        }
      ]
    }
  ],
  "group_logical_operator": "or"  // Needs approval if amount OR category triggers it
}
```

### Complex Decision Trees with `value_path`

You can create sophisticated decision logic by combining multiple tagged conditions with dynamic comparisons:

```json
{
  "tagged_conditions": [
    {
      "tag": "user_qualified",
      "condition_groups": [{
        "conditions": [
          {
            "field": "user.experience_years",
            "operator": "greater_than_or_equals",
            "value_path": "job.requirements.min_experience"
          },
          {
            "field": "user.skills",
            "operator": "contains",
            "value_path": "job.requirements.primary_skill"
          }
        ],
        "logical_operator": "and"
      }]
    },
    {
      "tag": "position_available",
      "condition_groups": [{
        "conditions": [
          {
            "field": "job.openings",
            "operator": "greater_than",
            "value": 0
          },
          {
            "field": "job.budget_remaining",
            "operator": "greater_than_or_equals",
            "value_path": "user.salary_expectation"
          }
        ],
        "logical_operator": "and"
      }]
    }
  ],
  "branch_logic_operator": "and"  // Both conditions must be true for hiring
}
```

### Error Handling for `value_path` in Decision Making

- **Non-existent Path**: If the `value_path` doesn't exist, the extracted value will be `None`
- **Comparison with None**: Most operators will evaluate to `false` when comparing against `None`
- **Impact on Branching**: Failed `value_path` resolutions typically lead to the `false_branch` being selected
- **Graceful Degradation**: The system continues processing other conditions even if some `value_path` resolutions fail

## Advanced List Processing with `fetch_nested_list_items`

The `fetch_nested_list_items` parameter is an internal mechanism that controls how the system handles value extraction when paths cross multiple nested lists. While you don't directly configure this parameter, understanding its behavior helps explain how complex nested data structures are processed in decision logic.

### When `fetch_nested_list_items` is Used

This mechanism is automatically activated when:

1. **`value_path` Resolution**: When resolving a `value_path` that crosses nested lists
2. **Complex Decision Logic**: When the system encounters lists while navigating to extract comparison values for branching decisions

### Behavior with Nested Lists in Decision Making

Consider this data structure for a workflow that routes based on team performance:
```json
{
  "departments": [
    {
      "name": "Engineering",
      "teams": [
        {"name": "Backend", "performance_score": 85},
        {"name": "Frontend", "performance_score": 92}
      ]
    },
    {
      "name": "Sales", 
      "teams": [
        {"name": "Enterprise", "performance_score": 78}
      ]
    }
  ],
  "company_targets": {
    "min_team_performance": 80
  }
}
```

When using a condition like:
```json
{
  "field": "current_team.performance_score",
  "operator": "greater_than",
  "value_path": "departments.teams.performance_score"  // Gets all team scores
}
```

The system:

1. **Traverses Lists**: Navigates through each department, then each team
2. **Collects Values**: Gathers all performance scores: `[85, 92, 78]`
3. **Enables Comparison**: Provides the collected values for decision logic

### Practical Implications for Workflow Routing

This automatic handling enables sophisticated decision logic across complex nested structures:

```json
{
  "tag": "above_average_performance",
  "condition_groups": [{
    "conditions": [{
      "field": "employee.current_score",
      "operator": "greater_than",
      "value_path": "company.departments.teams.members.average_score"
    }]
  }]
}
```

The system will automatically handle the nested list traversal and provide meaningful comparison values for routing decisions.

## Input (`DynamicSchema`)

The `IfElseConditionNode` typically receives the entire data object from the previous node or the central graph state. The specific fields it expects depend entirely on the `field` paths used in your conditions across all tags.

-   Data can be passed via incoming `EdgeSchema` mappings directly to the node, or implicitly via the graph's central state.

## Output (`IfElseOutputSchema`)

The node produces data matching the `IfElseOutputSchema`:

-   **`data`** (Dict[str, Any]): A copy of the original input data that was passed into the node. This allows the data to continue flowing down the chosen branch.
-   **`tag_results`** (Dict[str, bool]): A dictionary showing the boolean result (`true` or `false`) for each `tag` defined in the configuration. Example: `{"high_value_or_priority": true, "contactable_and_active": false}`.
-   **`condition_result`** (bool): The final, overall boolean result after combining the `tag_results` using the `branch_logic_operator`.
-   **`branch`** (String: `"true_branch"` or `"false_branch"`): Indicates which path the workflow *should* take next based on the `condition_result`. **This field is typically consumed by a subsequent Router Node.**

## Connecting to a Router Node (Required for Branching)

The `IfElseConditionNode` calculates the decision, but a **Router Node** executes it.

1.  **Output Connection:** The `IfElseConditionNode`'s output needs to be connected to a router node (e.g., `DynamicRouterNode`, `approval_router`).
2.  **Mapping:** You need an edge mapping from the `IfElseConditionNode`'s output field `branch` to an input field on the router node that the router uses to make its decision (e.g., the `field_name` configured in `ApprovalRouterNode` could be set to check the incoming `branch` value).
3.  **Router Configuration:** The router node must be configured to know which downstream node corresponds to the `"true_branch"` value and which corresponds to the `"false_branch"` value.
4.  **Downstream Connections:** The router node will then have edges connecting to the actual nodes that represent the true and false paths of your workflow.

See the configuration example above for how `check_lead_qualification` (IfElse) feeds into `qualification_router`.

## Example `GraphSchema` Snippet (Focus on Edges)

```json
{
  "nodes": {
    "get_lead_data": { /* ... */ },
    "check_qualification": { /* ... IfElseConditionNode config ... */ },
    "qualification_router": { /* ... DynamicRouterNode config checking 'branch' ... */ },
    "assign_to_sales": { /* ... node for TRUE branch ... */ },
    "send_to_nurturing": { /* ... node for FALSE branch ... */ },
    "final_step": { /* ... common node after branching ... */ }
  },
  "edges": [
    // Data flows into the condition node
    {
      "src_node_id": "get_lead_data",
      "dst_node_id": "check_qualification",
      "mappings": [] // Assumes direct passthrough or central state
    },
    // --- Edge from IfElse to Router --- 
    // Pass the decision result to the router
    {
      "src_node_id": "check_qualification",
      "dst_node_id": "qualification_router",
      "mappings": [
        // Map the 'branch' output field to the field the router expects
        { "src_field": "branch", "dst_field": "branch_decision" } 
        // Router's node_config would be set to check 'branch_decision' field
        // Note: Also map original data if needed: { "src_field": "data", "dst_field": "original_lead_data" }
      ]
    },
    // --- Edges FROM the Router Node --- 
    // These edges are defined, but the router *selects* which one to follow based on its logic
    {
      "src_node_id": "qualification_router",
      "dst_node_id": "assign_to_sales" // Router routes here if branch_decision == "true_branch"
    },
    {
      "src_node_id": "qualification_router",
      "dst_node_id": "send_to_nurturing" // Router routes here if branch_decision == "false_branch"
    },
    // --- Edges converging after branch ---
    {
      "src_node_id": "assign_to_sales",
      "dst_node_id": "final_step"
    },
    {
      "src_node_id": "send_to_nurturing",
      "dst_node_id": "final_step"
    }
  ],
  "input_node_id": "...",
  "output_node_id": "..."
}
```

## Operators
class FilterOperator(str, Enum):
    """
    Operators for filter conditions that define how field values are compared.
    
    Attributes:
        EQUALS: Field value equals the condition value
        EQUALS_ANY_OF: Field value equals any value in a list of condition values
        NOT_EQUALS: Field value does not equal the condition value
        GREATER_THAN: Field value is greater than the condition value
        LESS_THAN: Field value is less than the condition value
        GREATER_THAN_OR_EQUALS: Field value is greater than or equal to the condition value
        LESS_THAN_OR_EQUALS: Field value is less than or equal to the condition value
        CONTAINS: Field value contains the condition value (for strings, lists, etc.)
        NOT_CONTAINS: Field value does not contain the condition value
        STARTS_WITH: Field value (string) starts with the condition value
        ENDS_WITH: Field value (string) ends with the condition value
        IS_EMPTY: Field value is None, empty string, empty list, or empty dict
        IS_NOT_EMPTY: Field value is not empty
    """
    EQUALS = "equals"
    EQUALS_ANY_OF = "equals_any_of"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_THAN_OR_EQUALS = "greater_than_or_equals"
    LESS_THAN_OR_EQUALS = "less_than_or_equals"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"

## Notes for Non-Coders

-   Use this node when your workflow needs to make a decision: "If X is true, go path A, otherwise go path B".
-   `tagged_conditions`: Define your checks here. Give each check a clear `tag` name (like `"is_urgent"`). Set up the conditions (`field`, `operator`, `value`) just like in the Filter node.
-   You can use `value_path` in your conditions to compare one field against another field dynamically, rather than against a fixed value. This is perfect for:
    -   **Smart thresholds**: Compare user scores against minimum requirements stored in your data
    -   **Budget checks**: Compare spending against budget limits that might change
    -   **Permission levels**: Compare user access levels against required levels for different actions
    -   **Dynamic routing**: Route based on comparisons between current values and stored targets
-   `branch_logic_operator`: Decide how the results of your tagged checks combine. `"and"` means *all* checks must pass to choose the 'true' path. `"or"` means only *one* check needs to pass.
-   **Important:** This node *only* outputs the decision (`"true_branch"` or `"false_branch"`). It *doesn't* actually send the workflow down the path.
-   **You MUST connect this node's output to a `Router` node.** The Router node reads the `branch` decision and directs the workflow to the correct next step (`assign_to_sales` or `send_to_nurturing` in the example).
-   In the workflow editor, you connect the `IfElse` node to the `Router`, and then connect the `Router` to the two different downstream nodes.
-   The original data is passed along in the `data` output field, so the nodes in the chosen branch can use it.
-   When using `value_path`, if the path doesn't exist in your data, the condition will usually fail (evaluate to false), which typically leads to the "false" branch being taken. 