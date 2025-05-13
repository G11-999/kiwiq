# Usage Guide: DataJoinNode (data_join_data)

This guide explains how to configure and use the `DataJoinNode` to combine related data from different lists or objects within your workflow, similar to a "lookup" or "join" operation in databases.

## Purpose

The `DataJoinNode` allows you to enrich data by merging information from two different sources based on a common identifier (a "key"). You can:

-   Take a primary list (e.g., a list of users) and a secondary list (e.g., a list of departments).
-   Specify a key field in each list (e.g., `user.department_id` and `department.id`).
-   For each item in the primary list, find the matching item(s) in the secondary list based on the keys.
-   **Nest** the matching secondary item(s) *inside* the corresponding primary item under a new field name.
-   Perform multiple joins sequentially within the same node.
-   Handle cases where one side is a single object instead of a list.

This is useful for combining related information, like attaching order details to customer records, adding product information to line items, or linking user profiles to their assigned roles.

**Important:** This node operates on a *copy* of the input data. The original data structure passed into the node remains unchanged in the central state unless explicitly overwritten by subsequent steps.

## Configuration (`NodeConfig`)

You configure the `DataJoinNode` within the `node_config` field of its entry in the `GraphSchema`.

```json
{
  "nodes": {
    "enrich_users_with_dept": {
      "node_id": "enrich_users_with_dept", // Unique ID for this node instance
      "node_name": "data_join_data", // ** Must be "data_join_data" **
      "node_config": { // This is the MapperConfigSchema
        "joins": [ // List of join operations to perform sequentially
          // --- Join 1: Add Department Info to Users ---
          {
            "primary_list_path": "users", // Path to the main list (in input data)
            "secondary_list_path": "departments", // Path to the lookup list (in input data)
            "primary_join_key": "department_id", // Key field within each user object
            "secondary_join_key": "dept_id", // Key field within each department object
            "output_nesting_field": "department_info", // New field name inside each user to store matched dept
            "join_type": "one_to_one" // Expect only one matching department per user
          },
          // --- Join 2: Add User's Posts to Users (using the output of Join 1) ---
          {
            "primary_list_path": "users", // Path to the user list (now potentially modified by Join 1)
            "secondary_list_path": "posts", // Path to the list of posts
            "primary_join_key": "user_id", // Key field within each user object
            "secondary_join_key": "author_id", // Key field within each post object
            "output_nesting_field": "authored_posts", // New field inside each user for their posts
            "join_type": "one_to_many" // A user can have multiple posts, store as a list
          }
          // Add more join objects here to perform further joins sequentially
        ]
      }
      // dynamic_input_schema / dynamic_output_schema usually not needed for this node
    }
    // ... other nodes (e.g., nodes providing 'users', 'departments', 'posts' data)
  }
  // ... other graph properties (edges etc.)
}
```

### Key Configuration Sections:

1.  **`joins`** (List): **Required**. A list where each item defines a single join operation. Joins are executed sequentially; the output of one join becomes the input for the next within this node.
2.  **Inside each `joins` item**:
    *   **`primary_list_path`** (String): **Required**. Dot-notation path to the primary list or object in the input data (e.g., `user_data.active_users`, `order_details`). The join results will be nested within items of this list/object.
    *   **`secondary_list_path`** (String): **Required**. Dot-notation path to the secondary list or object used for lookups (e.g., `company_departments`, `product_catalog`).
    *   **`primary_join_key`** (String): **Required**. Dot-notation path *within each item* of the primary list/object to find the key value for matching (e.g., `dept_id`, `info.product_sku`).
    *   **`secondary_join_key`** (String): **Required**. Dot-notation path *within each item* of the secondary list/object to find the key value for matching (e.g., `id`, `details.sku`).
    *   **`output_nesting_field`** (String): **Required**. Dot-notation path *within each primary item* where the matched secondary item(s) should be placed (e.g., `department_details`, `product.info`). Intermediate dictionaries will be created if needed.
    *   **`join_type`** (String: `"one_to_one"` or `"one_to_many"`): **Required**. Determines how matches are nested:
        *   `"one_to_one"`: Finds the *first* matching secondary item and nests it directly (e.g., `user.department_info = {dept_id: 'd1', ...}`). If no match, nests `null`.
        *   `"one_to_many"`: Finds *all* matching secondary items and nests them as a *list* (e.g., `user.posts = [{post_id: 'p1', ...}, {post_id: 'p3', ...}]`). If no match, nests an empty list `[]`.

## Input (`DynamicSchema`)

The `DataJoinNode` expects input data containing the lists or objects specified in the `primary_list_path` and `secondary_list_path` of its join configurations.

-   The node uses a `DynamicSchema` and adapts based on the paths configured in the `joins`.
-   Data typically flows from previous nodes or the central graph state.

## Output (`MapperOutputSchema`)

The node produces a *modified copy* of its input data structure.

-   **`mapped_data`** (Dict[str, Any] | `null`): A dictionary containing the data structure after all configured join operations have been applied sequentially. The primary lists/objects specified in the joins will now contain the nested data under the `output_nesting_field`. If a critical error occurs (like a specified path not being found), this might be `null`.

## Example `GraphSchema` Snippet (Focus on Edges)

```json
{
  "nodes": {
    "get_user_list": { /* ... outputs 'users' list ... */ },
    "get_dept_list": { /* ... outputs 'departments' list ... */ },
    "combine_data": {
      "node_id": "combine_data",
      "node_name": "data_join_data",
      "node_config": {
        "joins": [
          {
            "primary_list_path": "all_users", // Expects input field 'all_users'
            "secondary_list_path": "all_departments", // Expects input field 'all_departments'
            "primary_join_key": "department_id",
            "secondary_join_key": "id",
            "output_nesting_field": "department_info",
            "join_type": "one_to_one"
          }
        ]
      }
    },
    "process_enriched_users": { /* ... expects input with users having 'department_info' ... */ }
  },
  "edges": [
    // Edges feeding data INTO the join node
    {
      "src_node_id": "get_user_list",
      "dst_node_id": "combine_data",
      "mappings": [ { "src_field": "users", "dst_field": "all_users" } ]
    },
    {
      "src_node_id": "get_dept_list",
      "dst_node_id": "combine_data",
      "mappings": [ { "src_field": "departments", "dst_field": "all_departments" } ]
    },
    // Edge sending the enriched data OUT of the join node
    {
      "src_node_id": "combine_data",
      "dst_node_id": "process_enriched_users",
      "mappings": [
        // The output field 'mapped_data' contains the whole structure, potentially with modifications
        { "src_field": "mapped_data", "dst_field": "enriched_user_data" }
      ]
    }
  ],
  "input_node_id": "...",
  "output_node_id": "..."
}
```

## Notes for Non-Coders

-   Use this node when you have two related sets of data (like users and their departments) and you want to combine them.
-   Think of it like looking up information. For each user, you want to look up their department details and add them to the user's record.
-   **`joins`**: Define your lookup rules here. You can have multiple lookups happen one after another.
    -   `primary_list_path`: Which list are you adding information *to*? (e.g., `users`)
    -   `secondary_list_path`: Where is the information you want to add? (e.g., `departments`)
    -   `primary_join_key`: What field in the primary list links it to the secondary list? (e.g., `user.department_id`)
    -   `secondary_join_key`: What field in the secondary list matches the primary key? (e.g., `department.id`)
    -   `output_nesting_field`: What should the added information be called inside the primary item? (e.g., `department_details`)
    -   `join_type`:
        -   `one_to_one`: Use if each primary item matches exactly one secondary item (like a user having one main department).
        -   `one_to_many`: Use if a primary item can match multiple secondary items (like a user having multiple posts). The result will be a list.
-   **Dot Notation:** Use dots (`.`) to specify fields within objects (e.g., `user.profile.id`).
-   **It Modifies a Copy:** The node works on a copy of the data, so the original input remains untouched unless the output (`mapped_data`) is used to overwrite it later.
-   Connect the necessary input data lists/objects to this node. Connect the output field `mapped_data` to the next node that needs the combined data. 