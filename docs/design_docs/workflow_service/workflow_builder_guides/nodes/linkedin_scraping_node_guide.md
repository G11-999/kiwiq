# Usage Guide: LinkedInScrapingNode

This guide explains how to configure and use the `LinkedInScrapingNode` to perform various LinkedIn scraping tasks like fetching profile information, entity posts, user activity, or searching posts by keyword/hashtag.

## Purpose

The `LinkedInScrapingNode` allows your workflow to interact with the LinkedIn scraping service. You can configure it to:

-   Define one or multiple scraping jobs to run within a single node execution.
-   Configure job parameters (like username, keyword, limits) using fixed values or dynamically based on data flowing through the workflow.
-   Trigger multiple similar jobs based on a list in the input data (e.g., scrape profiles for a list of usernames).
-   Run in a `test_mode` to validate configurations without actually performing the scraping, allowing for easier debugging.
-   Retrieve the results from the scraping service for use by subsequent nodes.

## How Jobs are Executed

When multiple jobs are defined (either through separate `JobDefinition` entries or via `expand_list`), the node attempts to run them concurrently using asynchronous operations (`asyncio`). This means jobs don't necessarily wait for the previous one to finish before starting. However, the actual execution speed and concurrency depend heavily on the underlying scraping service's capacity and potential rate limits.

## API Credits and Rate Limits (Important Caveat)

The underlying LinkedIn scraping service used by this node consumes **API credits** for most operations. Different actions (like fetching a profile, getting a batch of posts, fetching comments, fetching reactions) consume different amounts of credits.

-   **Rate Limits:** The external scraping service may impose rate limits (how many requests you can make per second/minute/hour). Exceeding these limits can lead to temporary blocking or errors (`429 Too Many Requests`). The node itself doesn't explicitly handle rate limiting beyond basic delays between paginated requests within a single job type (like fetching reactions); designing workflows to stay within reasonable limits is important.
-   **Credit Consumption:** Each successful action costs credits. Complex jobs that fetch many posts, comments, and reactions can consume a significant number of credits.
-   **Estimation:** Accurately estimating credit usage beforehand is complex. The table below provides a *rough, simplified* guide based on observed patterns in the scraping service (`credit_calculator.py`). **Actual consumption can vary.**
-   **Future Feature:** Automatic estimation and tracking of actual credit consumption within the workflow service is planned but **not yet implemented**. Currently, you need to estimate costs manually based on your configuration and expected data volume.

### Simplified Credit Consumption Guide (Estimates)

| Action                       | Approximate Credit Cost        | Notes                                                            |
| :--------------------------- | :----------------------------- | :--------------------------------------------------------------- |
| Get Profile Info (Person)    | 1 credit                       | Fetches basic profile details.                                   |
| Get Company Info             | 1 credit                       | Fetches basic company details.                                   |
| Get Entity Posts (Batch)     | 1 credit per batch of ~50 posts | Fetching 100 posts usually takes 2 batches (2 credits).          |
| Get Activity Reactions (Batch) | 1 credit per batch of ~100 posts | Fetching 200 liked posts usually takes 2 batches (2 credits).      |
| Get Activity Comments (Base) | 1 credit                       | To fetch the list of posts the user commented on.                |
| Get Post Comments (Per Post) | 1 credit per post              | Fetching comments for 10 posts costs 10 credits (plus post costs). |
| Get Post Reactions (Per Post) | Varies (1-5+ credits per post) | Depends heavily on the number of reactions and batching (~50).   |
| Search Posts (Keyword/Hashtag)| 1 credit per page/batch       | Number of pages depends on `post_limit` and API batch size.      |

**Note:** This is a simplified guide. The actual cost, especially for reactions, can fluctuate based on the specific number fetched and how the external API batches them. Batch sizes mentioned below also influence credit usage for paginated results. Always refer to the scraping service's documentation for the most accurate pricing.

### Example Credit Calculation (Estimate)

Let's estimate the cost for fetching **10 Person Posts** (`job_type: entity_posts`, `type: person`), including **Comments** (`post_comments: yes`) and **Reactions** (`post_reactions: yes`, `reaction_limit: 50`).

1.  **Fetch Posts:** 10 posts fit in one batch (<= 50) -> **1 credit**
2.  **Fetch Comments:** Fetching comments for each of the 10 posts -> **10 credits** (1 per post)
3.  **Fetch Reactions:** Fetching up to 50 reactions for each of the 10 posts. 50 reactions usually fits in the first batch for reactions per post (based on `credit_calculator.py`, assuming batch size ~49/50). -> ~**1 credit per post** * 10 posts = **~10 credits** (This is the most variable part).

**Estimated Total:** 1 (posts) + 10 (comments) + 10 (reactions) = **~21 credits**.

### List Expansion and Credits (`expand_list: true`)

When you use `expand_list: true` on an input field (e.g., a list of 10 usernames), the node generates **one separate job** for *each item* in that list.

**Crucially, this multiplies the credit consumption.**

If scraping one profile costs 1 credit, scraping a list of 10 usernames using `expand_list` will cost approximately **10 credits** (1 credit/profile * 10 profiles). If the job involves fetching posts+comments+reactions (like the ~21 credit example above), expanding a list of 10 usernames for that job would cost roughly **210 credits** (~21 credits/job * 10 jobs).

**Use `expand_list` carefully and be mindful of the potential credit cost.**

## Default Limits and Batch Sizes

If you don't explicitly provide limits (like `post_limit`, `comment_limit`, `reaction_limit`) in your `JobDefinition`, the system uses default values defined in the scraping service settings (`services/scraper_service/settings.py` -> `rapid_api_settings`).

-   **Default Post Limit (`post_limit`):** If not specified, typically defaults to **50**. This applies to `entity_posts`, `activity_comments`, `activity_reactions`, `search_post_by_keyword`, `search_post_by_hashtag`.
-   **Default Comment Limit (`comment_limit`):** If not specified when `post_comments` is "yes", defaults to **50**.
-   **Default Reaction Limit (`reaction_limit`):** If not specified when `post_reactions` is "yes", defaults to **49**.

Furthermore, the underlying service fetches data in batches when results are paginated (e.g., fetching posts, comments, reactions, likes, search results). These internal batch sizes affect how many API calls (and thus credits) are needed to reach your specified `limit`.

-   **Entity Posts Batch Size:** ~**50** posts per API call.
-   **Activity Reactions (Likes) Batch Size:** ~**100** items per API call.
-   **Post Comments Batch Size:** Varies by endpoint (Profile vs Company), often around **50**.
-   **Post Reactions Batch Size:** Typically retrieves up to **49** reactions per API call per post. Fetching more requires additional calls/credits for that post.
-   **Search Results Batch Size:** Varies by keyword/hashtag endpoint, often around **50**.

You usually don't configure the batch size directly, but be aware that requesting, for example, 120 company posts (`post_limit: 120`) will likely require 3 API calls (batches of 50, 50, 20) and thus consume 3 credits just for fetching the posts, before considering comments or reactions.

## Configuration (`NodeConfig`)

You configure the `LinkedInScrapingNode` within the `node_config` field of its entry in the `GraphSchema`.

```json
{
  "nodes": {
    "linkedin_scraper_step": {
      "node_id": "linkedin_scraper_step", // Unique ID for this node instance
      "node_name": "linkedin_scraping", // ** Must be "linkedin_scraping" **
      "node_config": { // This is the LinkedInScrapingConfig schema
        // --- Global Settings ---
        "test_mode": false, // Default: false. Set to true to validate configs without running jobs.

        // --- Job Definitions ---
        "jobs": [ // List of job definitions
          // --- Example 1: Static Profile Info ---
          {
            "output_field_name": "founder_profile", // Results stored here
            "job_type": { "static_value": "profile_info" },
            "type": { "static_value": "person" },
            "username": { "static_value": "billgates" },
            "profile_info": { "static_value": "yes" } // Required flag alignment
            // Limits will use system defaults (e.g., 50 for post_limit if applicable)
          },
          // --- Example 2: Dynamic Company Posts with URL ---
          {
            "output_field_name": "target_company_posts_via_url",
            "job_type": { "static_value": "entity_posts" },
            // Use URL directly - username and type will be extracted automatically
            "url": { "input_field_path": "input.company_profile_url" }, // Get URL from input
            "post_limit": { "input_field_path": "input.config.post_count" }, // Override default
            "post_comments": { "static_value": "yes" },
            "comment_limit": { "static_value": 10 }, // Override default (50)
            "entity_posts": { "static_value": "yes" } // Required flag alignment
          },
          // --- Example 3: Dynamic Company Posts with Explicit Username/Type ---
          {
            "output_field_name": "target_company_posts_via_name",
            "job_type": { "static_value": "entity_posts" },
            "type": { "static_value": "company" },
            "username": { "input_field_path": "input.company_name" }, // Get from input
            "post_limit": { "input_field_path": "input.config.post_count" }, // Override default
            "post_comments": { "static_value": "yes" },
            "comment_limit": { "static_value": 10 }, // Override default (50)
            "entity_posts": { "static_value": "yes" } // Required flag alignment
          },
          // --- Example 4: Expand List of Keywords (Uses Default Post Limit) ---
          {
            "output_field_name": "keyword_search_results",
            "job_type": { "static_value": "search_post_by_keyword" },
            "keyword": { "input_field_path": "input.keywords_to_search", "expand_list": true }, // Expand this list
            // post_limit not specified, will use default (e.g., 50) per keyword
            "search_post_by_keyword": { "static_value": "yes" } // Required flag alignment
          },
          // --- Example 5: Test Mode Validation ---
          {
            "output_field_name": "validated_config_only", // In test_mode, this field will contain the generated config dict
            "job_type": { "static_value": "activity_reactions" },
            "username": { "input_field_path": "input.user_for_activity" },
            "post_limit": { "static_value": 2 }, // Explicitly low limit
            "activity_reactions": { "static_value": "yes" } // Required flag alignment
          }
        ]
      }
      // dynamic_input_schema / dynamic_output_schema usually not needed
    }
    // ... other nodes
  }
  // ... other graph properties
}

```

### Key Configuration Sections:

1.  **`test_mode`** (bool): **Optional** (default: `false`).
    *   If `false` (default), the node executes the configured scraping jobs (consumes credits).
    *   If `true`, the node only resolves parameters, validates configurations, and outputs them without calling the scraper service (consumes no credits). Use this for debugging.
2.  **`jobs`** (List[`JobDefinition`]): **Required**. A list where each item (`JobDefinition`) defines how to construct and execute one or more scraping tasks.
3.  **Inside each `JobDefinition`**:
    *   **`output_field_name`** (str): **Required**. The name for the results of this job definition in the node's output `scraping_results`. Cannot start with `_`.
    *   **Job Parameters (e.g., `job_type`, `type`, `username`, `keyword`, `hashtag`, `post_limit`, `post_comments`, etc.)**: Set using an `InputSource` object. If optional parameters like `post_limit`, `comment_limit`, or `reaction_limit` are not provided via `InputSource`, system defaults will be used (see "Default Limits" section above).
    *   **Job Flags (`profile_info`, `entity_posts`, etc.)**: Set using `InputSource`. The flag matching the resolved `job_type` *must* end up as `"yes"` for validation. Explicitly set it for clarity.
    *   **`InputSource` Object**: How to get a parameter's value:
        *   `static_value` (Any): Fixed value (e.g., `"profile_info"`, `"yes"`).
        *   `input_field_path` (str): Dot-notation path to a field in the node's input data (e.g., `"input.user_id"`).
        *   `expand_list` (bool): Default `false`. If `true` and `input_field_path` points to a list, run one job per list item. **Warning:** Multiplies credit cost. Only one field per `JobDefinition` can use this.
    *   **URL Input (`url`)**:
        *   You can provide the full LinkedIn profile URL (e.g., `https://www.linkedin.com/in/username/` or `https://www.linkedin.com/company/company-name/`) using an `InputSource` for the `url` field.
        *   If `url` is provided, the node (specifically the underlying `ScrapingRequest` validator) will attempt to parse the `username` and `type` (person/company) directly from the URL.
        *   **Important:** If a valid `url` is provided, any values provided for `username` or `type` in the same `JobDefinition` will be ignored (and may cause a validation error if explicitly provided alongside `url`). Use either `url` OR (`username` and `type`), not both.

### Job Types and Required Inputs

Choose the `job_type` that matches the task you want to perform. Certain fields are required based on the `job_type`:

-   `profile_info`: Get profile details for a specific person or company.
    -   Requires: `url` OR (`type` (person/company) AND `username`).
-   `entity_posts`: Get posts made by a specific person or company.
    -   Requires: `url` OR (`type` (person/company) AND `username`).
    -   Optional: `post_limit`, `post_comments`, `comment_limit`, `post_reactions`, `reaction_limit`.
-   `activity_comments`: Get posts that a specific person has commented on.
    -   Requires: `url` (must resolve to a person profile URL) OR `username`.
    -   Optional: `post_limit` (limits *which* commented-on posts are retrieved), `post_comments` (fetch *other* comments on those posts), `comment_limit`, `post_reactions` (fetch reactions on those posts), `reaction_limit`.
-   `activity_reactions`: Get posts that a specific person has reacted to (liked, etc.).
    -   Requires: `url` (must resolve to a person profile URL) OR `username`.
    -   Optional: `post_limit` (limits *which* reacted-to posts are retrieved), `post_comments` (fetch comments on those posts), `comment_limit`, `post_reactions` (fetch *other* reactions on those posts), `reaction_limit`.
-   `search_post_by_keyword`: Search for posts containing specific keywords.
    -   Requires: `keyword`.
    -   Optional: `post_limit`.
-   `search_post_by_hashtag`: Search for posts containing a specific hashtag.
    -   Requires: `hashtag` (provide *without* the `#`).
    -   Optional: `post_limit`.

The node relies on the underlying `ScrapingRequest` validation to enforce these requirements.

## Input (`DynamicSchema`)

Input data is required if any `JobDefinition` uses `input_field_path`. Ensure the input contains the fields specified by those paths.

-   Example: `{ "company_name": "microsoft", "keywords_to_search": ["AI", "ML"] }`
-   Map the required data from previous nodes.

## Output (`LinkedInScrapingOutput`)

The node produces an output object containing results and metadata.

-   **`execution_summary`** (Dict[str, Dict[str, Any]]): Metadata for each `JobDefinition` (keyed by `output_field_name`), including `jobs_triggered`, `successful`, `failed` counts, and a list of `errors`.
-   **`scraping_results`** (Dict[str, Any]): The main results, keyed by `output_field_name`.
    -   **Normal Mode (`test_mode: false`)**: Contains the actual JSON data returned by the scraping service for each job (or list of results if `expand_list` was used). Failed jobs will contain an error dictionary `{"error": "..."}`.
    -   **Test Mode (`test_mode: true`)**: Contains the *validated configuration* dictionary for each job that *would* have run (or list of configs if `expand_list` was used). Failed validations will contain an error dictionary `{"error": "Validation failed: ...", "details": [...]}`.

## Example `GraphSchema` Snippet

```json
{
  "nodes": {
    "prepare_inputs": { /* ... node outputs user_ids list and company_target ... */ },
    "scrape_linkedin_data": {
      "node_id": "scrape_linkedin_data",
      "node_name": "linkedin_scraping",
      "node_config": {
        "test_mode": false,
        "jobs": [
          { // Expand list of user IDs for profile scraping
            "output_field_name": "user_profiles",
            "job_type": {"static_value": "profile_info"},
            "type": {"static_value": "person"},
            "username": {"input_field_path": "user_ids", "expand_list": true},
            "profile_info": {"static_value": "yes"}
          },
          { // Get posts for a single company using URL
            "output_field_name": "company_updates_url",
            "job_type": {"static_value": "entity_posts"},
            "url": {"input_field_path": "company_url"}, // Input provides the URL
            "post_limit": {"static_value": 5},
            "entity_posts": {"static_value": "yes"}
          }
        ]
      }
    },
    "process_scraped_data": { /* ... uses user_profiles and company_updates ... */ }
  },
  "edges": [
    { // Map inputs needed for dynamic paths
      "src_node_id": "prepare_inputs",
      "dst_node_id": "scrape_linkedin_data",
      "mappings": [
        { "src_field": "user_ids_output", "dst_field": "user_ids" },
        { "src_field": "company_name_output", "dst_field": "company_target" },
        { "src_field": "company_url_output", "dst_field": "company_url" } // Added mapping for URL example
      ]
    },
    { // Map results to the next node
      "src_node_id": "scrape_linkedin_data",
      "dst_node_id": "process_scraped_data",
      "mappings": [
        // Access results via scraping_results.<output_field_name>
        { "src_field": "scraping_results.user_profiles", "dst_field": "profiles_input" },
        { "src_field": "scraping_results.company_updates_url", "dst_field": "company_posts_input" },
        { "src_field": "execution_summary", "dst_field": "scraping_metadata" } // Optional
      ]
    }
  ],
  "input_node_id": "...", "output_node_id": "..."
}
```

## Notes for Non-Coders

-   Use this node to get data from LinkedIn.
-   **Credits:** This node costs credits based on usage. Fetching lots of data costs more. See the simplified credit table.
-   **Defaults:** If you don't specify limits (like how many posts), the system uses defaults (often 50 posts, 50 comments, 49 reactions).
-   `jobs`: Define your scraping tasks.
-   Inside `jobs`:
    -   `output_field_name`: A name for this task's results (e.g., `"ceo_profile"`).
    -   Parameters (`job_type`, `username`, etc.): Define task details.
        -   `static_value`: Use a fixed value.
        -   `input_field_path`: Use a value from a previous step.
        -   `expand_list: true`: **Use carefully!** Runs the task for each item in an input list, multiplying credit cost.
    -   Choose the correct `job_type`.
    -   For profiles/company posts, provide either the `url` OR the `username` and `type`. For activity jobs, provide a person's `url` or `username`. For searches, provide `keyword` or `hashtag`.
-   `test_mode: true`: Check setup without spending credits. Output shows planned jobs.
-   Results are in `scraping_results` under the `output_field_name`. Connect this to the next node.
