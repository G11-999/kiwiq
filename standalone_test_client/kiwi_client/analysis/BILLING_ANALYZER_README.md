# Billing Analyzer for Workflow Runs

The Billing Analyzer Client provides comprehensive billing analysis for workflow runs, including hierarchical run structures with parent-child relationships.

## Features

### API Enhancement
Added `parent_run_id` filter to the workflow runs API to support querying child runs:
- **Schema Update**: Added `parent_run_id` field to `WorkflowRunListQuery` 
- **CRUD Update**: Added `parent_run_id` filter support in `WorkflowRunDAO._build_run_filters()`
- **Service/Routes**: Automatically supported through existing infrastructure

### Billing Analysis Capabilities

1. **Hierarchical Run Analysis**
   - Analyzes a root run and all its descendant runs
   - Builds complete run hierarchy tree
   - Aggregates billing across entire run tree

2. **Multiple Breakdown Views**
   - **By Workflow**: Credits consumed per workflow type
   - **By Event Type**: Credits per event type (e.g., llm_token_usage, web_search)
     - Note: The `__dollar_credit_fallback_for` suffix is automatically removed if present
   - **By Event Subtype**: Automatic extraction of subtypes (split by `__`)
   - **By Model**: For LLM and search events, breakdown by model name
   - **By Node (per workflow)**: Credits by `node_id` (and `node_name` when present)
   - **Node × Model (per workflow)**: Matrix of `node_id` by model within a workflow
   - **Node × Model (global)**: Across all workflows combined

3. **Model Usage Analytics**
   - Overall model usage across all runs
   - Per-workflow model usage breakdown
   - Provider information for each model

## Usage

### Basic Usage

```python
from kiwi_client.auth_client import AuthenticatedClient
from kiwi_client.run_billing_analyzer_client import RunBillingAnalyzerClient

# Initialize
auth_client = AuthenticatedClient()
await auth_client.login()

analyzer = RunBillingAnalyzerClient(auth_client)

# Analyze a run with default depth (5 levels)
analysis = await analyzer.analyze_run_billing(run_id="your-run-id")

# Analyze with custom depth limit
analysis = await analyzer.analyze_run_billing(
    run_id="your-run-id",
    max_hierarchy_depth=3  # Only go 3 levels deep
)

# Save results with depth control
analysis, md_path, json_path = await analyzer.analyze_and_save(
    run_id="your-run-id",
    output_dir="billing_analysis",
    max_hierarchy_depth=2  # Shallow analysis for quick results
)
```

### Using the Test Script

```bash
# Analyze a specific run
python standalone_test_client/kiwi_client/test_billing_analyzer.py <run_id>

# Interactive mode - select from recent runs
python standalone_test_client/kiwi_client/test_billing_analyzer.py
```

### Direct Client Usage

```python
# Get child runs of a parent
from kiwi_client.run_client import WorkflowRunTestClient

run_client = WorkflowRunTestClient(auth_client)
child_runs = await run_client.list_runs(parent_run_id="parent-run-id")
```

## Output Formats

### Markdown Report
The analyzer generates a comprehensive markdown report including:
- Summary statistics
- Model usage tables
- Workflow-specific breakdowns
- Event type analysis with subtypes
- Run hierarchy visualization
- Node usage per workflow
- Node × Model breakdown per workflow and global

### JSON Data
Complete structured data including:
- All billing metrics
- Run hierarchy structure
- Raw events (optional)
- Detailed breakdowns

## Event Type Analysis

The analyzer specially handles:

1. **LLM Token Usage Events** (`llm_token_usage*`)
   - Breaks down by model name
   - Tracks providers
   - Handles allocation/adjustment subtypes
   - Automatically removes `__dollar_credit_fallback_for` suffix if present

2. **Web Search Events**
   - Model-based breakdown
   - Provider tracking

3. **Event Subtypes**
   - Automatically extracts subtypes from event names (e.g., `llm_token_usage__allocation`)
   - Provides separate metrics for each subtype

## Node-level Analysis

The analyzer additionally leverages `usage_metadata.node_id` and `usage_metadata.node_name` when present in usage events to compute:

1. Per-workflow node usage totals (credits and event counts)
2. Per-workflow Node × Model breakdown (credits and events)
3. Global Node × Model breakdown across all workflows

These sections are included in the markdown report and are accessible via the `RunBillingAnalysis` object fields:

- `workflow_breakdown[wf].node_usage`
- `workflow_breakdown[wf].node_model_usage`
- `overall_node_model_usage`

## Example Output

```markdown
# Workflow Run Billing Analysis

**Total Credits Consumed:** $0.0506825
**Total Runs Analyzed:** 3
**Total Events:** 15

## Overall Model Usage
| Model | Credits | Events | Providers |
|-------|---------|--------|-----------|
| gpt-5 | $0.0456825 | 12 | openai |
| claude-3 | $0.0050000 | 3 | anthropic |

## Breakdown by Workflow
### data_processing_workflow
- **Runs:** 2
- **Total Credits:** $0.0306825

### analysis_workflow  
- **Runs:** 1
- **Total Credits:** $0.0200000
```

## Implementation Details

### Files Modified

1. **API Layer**
   - `services/kiwi_app/workflow_app/schemas.py`: Added `parent_run_id` to `WorkflowRunListQuery`
   - `services/kiwi_app/workflow_app/crud.py`: Added filter support in `_build_run_filters()`
   - `services/kiwi_app/workflow_app/services.py`: No changes needed (uses generic filtering)

2. **Client Layer**
   - `standalone_test_client/kiwi_client/run_client.py`: Added `parent_run_id` parameter
   - `standalone_test_client/kiwi_client/analysis/run_billing_analyzer_client.py`: Analyzer extended with Node and Node × Model analyses
   - `standalone_test_client/kiwi_client/analysis/test_billing_analyzer.py`: Test/demo extended to print new summaries

### Key Classes

- `RunBillingAnalyzerClient`: Main analyzer class
- `RunBillingAnalysis`: Complete analysis result model
- `WorkflowBillingBreakdown`: Per-workflow breakdown
- `EventTypeBreakdown`: Event type analysis with model breakdown
- `ModelUsageStats`: Model usage statistics

## Performance Considerations & Safety Features

### Cycle Detection
The analyzer includes robust cycle detection to prevent infinite loops:
- Tracks processed runs to detect circular references
- Warns when cycles are detected and skips already-processed runs
- Essential for complex workflows that may have circular dependencies

### Depth Limiting
Configurable maximum depth traversal (default: 5 levels):
- Prevents excessive API calls for very deep hierarchies
- Protects against runaway queries
- Customizable per analysis (range: 1-10)

### Pagination Support
- Handles runs with many children (up to 1000 children per run)
- Uses pagination for large event sets (1000 events per request)
- Efficiently builds run hierarchy using parent_run_id filter
- Aggregates data in single pass through events

### Progress Tracking
The analyzer provides real-time progress updates:
- Shows hierarchy building progress with indentation
- Displays number of children found at each level
- Reports billing event fetching progress
- Warns about cycles and depth limits

## Future Enhancements

Potential improvements:
- Add time-based filtering for billing events
- Support for cost projections
- Comparison between multiple runs
- Export to CSV/Excel formats
- Real-time streaming of billing events
- Alerting on cost thresholds
