# Usage Guide: AIAnswerEngineScraperNode

This guide explains how to configure and use the `AIAnswerEngineScraperNode` to query AI providers (Google, OpenAI, Perplexity) about entities and automatically store the results in MongoDB. This node provides a high-level interface for AI-powered research with proper user/organization data isolation.

## Purpose

The `AIAnswerEngineScraperNode` allows your workflow to:

- **Query multiple AI providers** simultaneously to gather information about companies, people, or topics
- **Use template-based queries** with variable substitution for consistent information gathering
- **Process multiple entities** in a single workflow run for batch research
- **Store results automatically** in MongoDB with proper user/organization isolation
- **Cache results intelligently** to avoid redundant queries and save costs
- **Configure provider behavior** with retry logic and timeout settings
- **Scale performance** with parallel browser pools for faster execution

## How AI Querying Works

The node integrates with a sophisticated multi-provider query engine that manages the complexity of querying different AI services:

1. **Query Construction**: Your templates are combined with entity variables to create specific queries
2. **Cache Check**: Before querying, the node checks MongoDB for recent results to avoid redundancy
3. **Parallel Execution**: Queries are distributed across providers and executed in parallel
4. **Result Normalization**: Different provider responses are normalized into a consistent format
5. **Automatic Storage**: All results are stored in MongoDB with proper namespace isolation
6. **Statistics Tracking**: Detailed metrics are collected for monitoring and optimization

## Important: Cost and Performance Considerations

Unlike web scraping, AI provider queries **consume API resources** and may incur costs. The node includes several important features to manage this:

- **Smart Caching**: Results are cached by default to avoid redundant queries
- **Provider Selection**: You can disable expensive providers if needed
- **Batch Processing**: Multiple entities are processed efficiently in parallel
- **Retry Logic**: Failed queries are retried with configurable limits to balance reliability and cost

**Key Principle**: The default configuration balances comprehensive results with efficient resource usage. Always use caching unless you specifically need fresh data.

### Billing Information

The AI Answer Engine Scraper node uses a **flat-rate billing model**:

- **Cost**: $0.03 per query per provider (3 cents per API call)
- **Important**: Each query is sent to ALL enabled providers
- **Total cost**: Number of queries × Number of enabled providers × $0.03
- **Cached queries are free**: Only queries without cached results for ALL enabled providers consume credits
- **Credit allocation**: Credits are allocated before queries execute based on total API calls
- **Credit adjustment**: After execution, credits are adjusted based on successful API calls only
- **Failed queries don't charge**: You're only charged for successful query results

**Example Cost Calculation**:
- 10 entities × 5 query templates = 50 unique queries
- 3 enabled providers (Google, OpenAI, Perplexity)
- Total API calls: 50 × 3 = 150 calls
- Cost: 150 × $0.03 = $4.50

**Cache Optimization**:
- A query is only skipped if cached results exist for ALL enabled providers
- If you have cached results from Google but not OpenAI, the query will still be executed for all providers
- To maximize cache usage, keep your provider configuration consistent between runs
- **Important**: Cached results are filtered to only show results from currently enabled providers
- If you disable a provider, its cached results won't be returned even if they exist in the database
- **Deduplication**: If the same query was executed multiple times (e.g., on different days), only the most recent result for each (query, provider) combination is returned

**Understanding Result Counts**:
- **Unique queries**: The number of distinct queries (e.g., 3 queries from your templates)
- **Total results**: The total number of query-provider combinations (e.g., 3 queries × 2 providers = 6 results)
- **Cached results**: Only includes results from currently enabled providers
- Example: If you had 3 queries cached for 3 providers (9 results) but now only enable Google:
  - You'll see only 3 cached Google results (not all 9)
  - Results from disabled providers (OpenAI, Perplexity) are filtered out
  - The system returns a "completed_from_cache" status if all queries for enabled providers are cached

**Insufficient Credits**: If you don't have enough credits, the node will fail with an error before executing any queries.

## Configuration (`AIAnswerEngineScraperConfig`) - Use Defaults

The node comes with carefully tuned default settings. **We strongly recommend using the defaults** unless you have specific requirements. Here's what the configuration controls:

### Query Templates (Customize If Needed)
```json
{
  "query_templates": {
    "basic_info": [
      "What is {entity_name}?",
      "Tell me about {entity_name}",
      "What does {entity_name} do?"
    ],
    "leadership": [
      "Who is the founder of {entity_name}?",
      "Who are the key executives at {entity_name}?"
    ],
    "business": [
      "What products or services does {entity_name} offer?",
      "What is the business model of {entity_name}?"
    ]
  }
}
```

- **Purpose**: Define categories of questions to ask about each entity
- **Variables**: Use `{variable_name}` format for substitution
- **Customization**: This is the main configuration you might want to customize based on your research needs

### Provider Settings (Rarely Change)
```json
{
  "default_providers_config": {
    "google": {"enabled": true, "max_retries": 2, "retry_delay": 2.0},
    "openai": {"enabled": true, "max_retries": 3, "retry_delay": 2.0},
    "perplexity": {"enabled": true, "max_retries": 2, "retry_delay": 2.0}
  }
}
```

- **`enabled`**: Whether to use this provider
- **`max_retries`**: How many times to retry failed queries
- **`retry_delay`**: Seconds between retry attempts
- **Recommendation**: Keep all providers enabled for best coverage

### Browser Pool Settings (Don't Change)
- **`max_concurrent_browsers`**: Default 35 - optimized for parallel execution
- **`browser_ttl`**: Default 900 seconds - browser session lifetime
- **`acquisition_timeout`**: Default 60 seconds - timeout for getting a browser
- **`use_browser_profiles`**: Default `true` - better anti-detection
- **`persist_browser_profile`**: Default `false` - fresh profile each time

**Recommendation**: These settings are optimized for the AI querying use case. Don't change them.

## Input (`AIAnswerEngineScraperInput`) - Focus Here

This is where you should focus your configuration efforts. Input parameters directly control what gets queried and how results are cached.

### Core Input Fields

- **`list_template_vars`** (Optional: List[Dict[str, str]] or Dict[str, str])
  - Multi-entity mode: provide a list of dicts; each dict must include `entity_name`.
  - Single-entity mode: provide a single dict; `entity_name` is not required here if you also set `entity_name`. If present, it must equal `entity_name`.
  - If omitted (and no `entity_name` provided), templates are used as-is with no substitution and a generic entity context.

- **`entity_name`** (Optional: str)
  - When provided (or resolved via config path), enables single-entity mode: all queries run exactly once for this entity.
  - In this mode, if `list_template_vars` is provided it must be a dict (not a list). If it includes `entity_name`, it must equal the `entity_name` field.

- **`query_templates`** (Optional: Dict[str, List[str]])
  - Override default templates. Variables use `{var_name}` format.

- **`providers_config`** (Optional: Dict[str, Dict])
  - Override per-provider settings.

- **`enable_mongodb_cache`** (bool, default `true`), **`cache_lookback_days`** (int, default 14), **`is_shared`** (bool, default `false`)

### Examples

Multi-entity (list of entities):
```json
{
  "list_template_vars": [
    {"entity_name": "OpenAI", "location": "San Francisco", "industry": "AI"},
    {"entity_name": "Tesla",  "location": "Palo Alto",      "industry": "Automotive"}
  ],
  "enable_mongodb_cache": true,
  "cache_lookback_days": 7
}
```

Single-entity (explicit entity_name):
```json
{
  "entity_name": "Anthropic",
  "list_template_vars": {"industry": "AI safety"},
  "query_templates": {
    "recent": ["What are the latest announcements from {entity_name}?"]
  }
}
```

No template vars (templates used as-is):
```json
{
  "enable_mongodb_cache": true
}
```
In this case, the node executes templates without substitution and stores under a generic entity namespace (see Namespace Pattern).

### Query Customization (Optional)

```json
{
  "query_templates": {
    "financial": [
      "What is the revenue of {entity_name}?",
      "What is the market cap of {entity_name}?"
    ],
    "technical": [
      "What technology does {entity_name} use?",
      "What are the key innovations from {entity_name}?"
    ]
  }
}
```

- **`query_templates`** (Optional): Override default query templates
  - Use to ask specific questions relevant to your research
  - Categories help organize results
  - **Impact**: More queries = more comprehensive data but longer execution

### Provider Configuration (Advanced)

```json
{
  "providers_config": {
    "openai": {"enabled": false},
    "google": {"max_retries": 5}
  }
}
```

- **`providers_config`** (Optional): Override default provider settings
  - Disable providers to reduce costs or avoid specific services
  - Adjust retry logic for reliability vs speed tradeoff
  - **Impact**: Fewer providers = faster but potentially less comprehensive results

### Path-Based Dynamic Inputs (Optional)

You can provide inputs indirectly via dot-separated paths into your dynamic payload using node configuration fields:

- Config fields:
  - `query_templates_path`: path to find `query_templates` in the dynamic input
  - `list_template_vars_path`: path to find `list_template_vars` in the dynamic input
  - `entity_name_path`: path to find a single `entity_name` in the dynamic input (enables single-entity mode)

- Priority order per field:
  1. Direct top-level input field (if present)
  2. Value resolved at configured path (if path set)
  3. Default (only for `query_templates`; `list_template_vars` can be omitted entirely and templates will run as-is)

- Error behavior:
  - If `query_templates_path` is set but the value is not found, the node raises an error.
  - If `list_template_vars_path` is set but the value is not found, the node raises an error.
  - If `entity_name_path` is set but not found, single-entity mode is not enabled (falls back to multi-entity or generic mode).

Example using paths:
```json
{
  "node_config": {
    "query_templates_path": "payload.research.templates",
    "list_template_vars_path": "payload.targets.entities",
    "entity_name_path": "payload.target_entity"
  },
  "input": {
    "payload": {
      "research": {"templates": {"basic_info": ["What is {entity_name}?"]}},
      "targets": {"entities": [{"entity_name": "OpenAI"}, {"entity_name": "Google"}]},
      "target_entity": null
    }
  }
}
```
In this example, `query_templates` and `list_template_vars` are resolved from the payload. Because `target_entity` is null, single-entity mode is not activated.

### Caching Options (Performance Optimization)

```json
{
  "enable_mongodb_cache": true,
  "cache_lookback_days": 14
}
```

- **`enable_mongodb_cache`** (bool, default `true`): Use cached results if available
  - **Impact**: `true` = faster and cheaper, `false` = always fresh data
  - **Strong Recommendation**: Keep `true` unless you specifically need current data

- **`cache_lookback_days`** (int, default 14): How far back to look for cached results
  - **Impact**: Longer = more cache hits but potentially older data
  - **Range**: 1-90 days
  - **Recommendation**: 7-14 days for most use cases

### Storage Settings

```json
{
  "is_shared": false
}
```

- **`is_shared`** (bool, default `false`): Whether query results are accessible to all organization users
  - `false` = only accessible to the user who triggered the job
  - `true` = accessible to all users in the organization
  - **Impact**: Affects data visibility and team collaboration

## Output (`AIAnswerEngineScraperOutput`)

The node provides comprehensive information about the query operation and results.

### Job Identification
- **`job_id`** (str): Unique identifier (format: `ai_query_YYYYMMDD_HHMMSS_<uuid>`)
- **`status`** (str): Final job status
  - `"completed"` - Fresh queries executed successfully
  - `"completed_from_cache"` - All results from cache
  - `"completed_with_cache"` - Mix of cached and fresh results
  - `"failed"` - Query job failed

### Execution Statistics
- **`total_queries_executed`** (int): Number of fresh queries run
- **`successful_queries`** (int): Queries that returned results
- **`failed_queries`** (int): Queries that failed after retries
- **`cached_results_used`** (int): Number of results from cache
- **`completed_at`** (str): ISO 8601 timestamp when job completed

### Provider Statistics
- **`provider_stats`** (Dict): Detailed metrics per provider including:
  - Success rate percentage
  - Average attempts per query
  - Average duration per query
  - Total queries handled

### MongoDB Storage Information
- **`mongodb_namespaces`** (List[str]): MongoDB namespaces where data is stored
  - Format: `scraping_ai_answers_results_{entity_name}_{YYYYMMDD}`
  - One namespace per entity for easy organization
- **`documents_stored`** (int): Total documents stored (including cached)

### Results Data
- **`query_results`** (List[Dict]): Sample of query results (up to 10)
  - Provides preview of responses
  - Full results are in MongoDB
- **`entity_results`** (Dict): Results organized by entity showing:
  - Namespace for each entity
  - Cached vs new query counts
  - Results categorized by query type
- **`executed_queries`** (List[str]): Actual queries run after template substitution
- **`used_cached_results`** (bool): Whether any cached results were used

## Example Configurations

### Basic Company Research
```json
{
  "node_config": {
    // Use all defaults - no config needed
  },
  "input": {
    "list_template_vars": [
      {"entity_name": "Microsoft"},
      {"entity_name": "Apple"},
      {"entity_name": "Google"}
    ],
    "enable_mongodb_cache": true,
    "cache_lookback_days": 7
  }
}
```

### Detailed Competitor Analysis
```json
{
  "node_config": {
    "query_templates": {
      "market": [
        "What is the market share of {entity_name} in {industry}?",
        "Who are the main competitors of {entity_name}?",
        "What are the competitive advantages of {entity_name}?"
      ],
      "financial": [
        "What is the revenue growth of {entity_name}?",
        "What are the profit margins of {entity_name}?"
      ]
    }
  },
  "input": {
    "list_template_vars": [
      {"entity_name": "Tesla", "industry": "electric vehicles"},
      {"entity_name": "Rivian", "industry": "electric vehicles"},
      {"entity_name": "Lucid Motors", "industry": "electric vehicles"}
    ],
    "enable_mongodb_cache": true,
    "is_shared": true
  }
}
```

### Fresh Data Research (No Cache)
```json
{
  "input": {
    "list_template_vars": [
      {"entity_name": "OpenAI", "focus": "latest developments"},
      {"entity_name": "Anthropic", "focus": "recent announcements"}
    ],
    "enable_mongodb_cache": false,
    "providers_config": {
      "perplexity": {"enabled": false}  // Disable if not needed
    }
  }
}
```

### Single-Entity Research (New)
```json
{
  "input": {
    "entity_name": "LangChain",
    "list_template_vars": {"focus": "tooling"},
    "query_templates": {
      "recent": ["What are the latest releases from {entity_name}?"]
    }
  }
}
```

### Single-Entity via Path (New)
```json
{
  "node_config": {
    "entity_name_path": "ctx.entity.name"
  },
  "input": {
    "ctx": {"entity": {"name": "Weaviate"}}
  }
}
```

## Impact of Input Changes

### Adding More Entities
- **Small batch** (1-5 entities): Minimal impact, efficient parallel processing
- **Medium batch** (5-20 entities): Proportional increase in time, still efficient
- **Large batch** (20+ entities): Consider splitting into multiple jobs for better monitoring

### Adding More Query Templates
- **Each additional query**: Multiplies total queries by number of entities
- **Example**: 5 entities × 10 queries = 50 total AI queries
- **Cost impact**: Each query consumes API resources
- **Time impact**: Parallel execution keeps time reasonable

### Disabling Providers
- **Disabling 1 provider**: ~33% fewer results but faster execution
- **Disabling 2 providers**: Only one perspective, much faster but less comprehensive
- **Recommendation**: Keep all providers for best coverage

### Cache Settings Impact
- **Disabling cache** (`enable_mongodb_cache: false`): 
  - Fresh data every time
  - Significantly higher API usage and costs
  - Slower execution
- **Shorter cache period** (1-3 days): More current data but more API calls
- **Longer cache period** (30-90 days): Maximum efficiency but potentially stale data

## MongoDB Data Access

Query results are automatically stored in MongoDB with entity-specific namespaces.

### Namespace Pattern
```
scraping_ai_answers_results_{entity_name}_{YYYYMMDD}
```
Example: `scraping_ai_answers_results_openai_20240115`

Notes:
- In single-entity mode, `{entity_name}` is the provided/resolved value.
- If no template vars or entity name are provided, the node uses `generic` for `{entity_name}` and executes templates without substitution.

### Accessing Results in Subsequent Nodes
Use the `load_customer_data` or `load_multiple_customer_data` nodes:

```json
{
  "namespace_pattern": "scraping_ai_answers_results_openai_*",
  "docname_pattern": "*"
}
```

### Document Structure
```json
{
  "query": "What is OpenAI?",
  "query_index": 0,
  "provider": "google",
  "success": true,
  "attempts": 1,
  "start_time": "2024-01-15T10:30:00Z",
  "end_time": "2024-01-15T10:30:05Z",
  "response": {
    "processed_data": "OpenAI is an AI research company...",
    "raw_response": "...",
    "metadata": {...}
  },
  "duration_seconds": 5.2
}
```

## Best Practices

### Query Design
1. **Start with default templates** and add custom ones as needed
2. **Group related queries** into logical categories
3. **Keep queries focused** - specific questions get better answers
4. **Test with one entity** before running large batches

### Cache Management
1. **Always enable caching** unless you need real-time data
2. **Use appropriate cache periods**:
   - 1-3 days for rapidly changing information
   - 7-14 days for general company information  
   - 30 days for historical data
3. **Consider data freshness needs** vs cost/performance

### Batch Processing
1. **Group similar entities** for consistent results
2. **Ensure all entities have same template variables**
3. **Start with small batches** (5-10) to test
4. **Monitor execution time** and scale accordingly

### Cost Optimization
1. **Use caching aggressively** to avoid redundant queries
2. **Disable unused providers** if you don't need comprehensive coverage
3. **Review query templates** to avoid asking redundant questions
4. **Check cached results first** before adding new queries

## Example Graph Schema Integration

```json
{
  "nodes": {
    "ai_researcher": {
      "node_id": "ai_researcher",
      "node_name": "ai_answer_engine_scraper",
      "node_config": {
        // Use defaults or add custom query templates
      }
    },
    "process_results": {
      "node_id": "process_results",
      "node_name": "load_multiple_customer_data",
      "node_config": {
        "namespace_pattern_source": "input_field",
        "docname_pattern": "*"
      }
    }
  },
  "edges": [
    {
      "src_node_id": "input",
      "dst_node_id": "ai_researcher",
      "mappings": [
        {"src_field": "companies_to_research", "dst_field": "list_template_vars"},
        {"src_field": "use_cache", "dst_field": "enable_mongodb_cache"}
      ]
    },
    {
      "src_node_id": "ai_researcher",
      "dst_node_id": "process_results",
      "mappings": [
        {"src_field": "mongodb_namespaces", "dst_field": "namespace_pattern"}
      ]
    }
  ]
}
```

## Notes for Non-Coders

- **Purpose**: This node asks AI services questions about companies, people, or topics and saves the answers
- **Templates**: Pre-written questions with blanks that get filled in with your entity names
- **Multiple Providers**: Like asking three different experts the same question for comprehensive answers
- **Caching**: Saves previous answers so you don't ask the same question twice (saves time and money)
- **Default Settings**: Pre-configured to work well - focus on what entities to research, not how
- **Batch Processing**: Research multiple companies at once efficiently
- **Storage**: All answers automatically saved to your database for other nodes to use

## Troubleshooting Common Issues

### Queries Taking Too Long
- **Check** number of entities and queries - reduce if too many
- **Verify** all providers are responsive
- **Consider** disabling slower providers temporarily
- **Enable** caching if disabled

### Not Getting Expected Results
- **Review** query templates - make them more specific
- **Check** template variables match across all entities
- **Verify** providers are enabled
- **Look at** sample results to understand response format

### Cache Not Working
- **Verify** `enable_mongodb_cache` is `true`
- **Check** you're researching same entities (exact name match required)
- **Consider** if `cache_lookback_days` is too short
- **Note**: Cache is query-specific, slight changes bypass cache

### Inconsistent Template Variables
- **Ensure** all entities in `list_template_vars` have same keys
- **Example**: If one has "location", all must have "location"
- **Check** error messages for missing variable warnings

### High API Usage
- **Enable** caching immediately
- **Reduce** number of query templates
- **Process** entities in smaller batches
- **Consider** longer cache periods for stable data