# Usage Guide: WorkflowRunnerNode

This guide explains how to configure and use the `WorkflowRunnerNode` to execute workflows within workflows. This powerful node enables complex workflow orchestration by allowing one workflow to trigger and monitor other workflows.

## Purpose

The `WorkflowRunnerNode` allows your workflow to:

- **Execute other workflows** as part of your workflow's execution flow
- **Pass data dynamically** between parent and child workflows
- **Monitor execution** and wait for results from triggered workflows
- **Create modular workflows** by breaking complex processes into reusable components
- **Maintain conversation context** across multiple workflow executions (for conversational AI)
- **Handle errors gracefully** with configurable failure behavior
- **Support HITL workflows** by detecting when subworkflows need human input and enabling resumption

## How Workflow Execution Works

When this node runs, it performs the following steps:

1. **Identifies the target workflow** using the name or ID you provide
2. **Maps your input data** to the target workflow's expected inputs
3. **Executes the workflow** either as a subprocess (connected to parent) or independently
4. **Monitors the execution** until completion, timeout, or HITL pause
5. **Handles HITL states** by exposing required human input details for resumption
6. **Returns the results** from the executed workflow to continue your main workflow

## Important: Execution Modes

The node supports two execution modes that determine how the triggered workflow runs:

### Subprocess Mode (Default)
- **What it does**: Runs the workflow as a true child of your current workflow
- **Parent-child relationship**: Creates a traceable connection between workflows
- **Use when**: You want workflows to be logically connected and tracked together
- **Example**: A content creation workflow calling a research workflow as a sub-step

### Independent Mode
- **What it does**: Submits the workflow as a completely separate execution
- **No parent relationship**: Runs independently without connection to the triggering workflow
- **Use when**: You want to trigger workflows that should run on their own
- **Example**: Triggering a notification workflow that doesn't need to be tied to the main process

**Recommendation**: Use the default subprocess mode unless you specifically need independent execution.

## HITL (Human-in-the-Loop) Support

The WorkflowRunnerNode fully supports workflows that require human interaction. When a subworkflow reaches a state where it needs human input, the node will detect this and provide all necessary information for resumption.

### How HITL Works

1. **Detection**: When a subworkflow reaches `WAITING_HITL` state, the node detects this condition
2. **Information Exposure**: The node outputs HITL job details including:
   - **`run_id`**: The subworkflow run ID that needs attention
   - **`hitl_job_id`**: Unique ID of the HITL job
   - **`hitl_request_schema`**: JSON schema defining expected human response format
   - **`hitl_request_details`**: Human-readable description of what input is needed
3. **Resume Capability**: The parent workflow can later resume the subworkflow by providing HITL inputs

### HITL Input Fields

When resuming a workflow from HITL state, use these special input fields:

```json
{
  "hitl_inputs": {
    "user_decision": "approve",
    "feedback": "Looks good, proceed with publishing",
    "additional_notes": "Make sure to check spelling"
  },
  "subworkflow_run_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

- **`hitl_inputs`** (object): The human responses matching the required schema
- **`subworkflow_run_id`** (string): The exact run ID of the subworkflow to resume (from previous HITL output)

### HITL Output Fields

When a subworkflow enters HITL state, the output includes:

```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "waiting_hitl",
  "hitl_job_id": "123e4567-e89b-12d3-a456-426614174001",
  "hitl_request_schema": {
    "type": "object",
    "properties": {
      "user_decision": {"type": "string", "enum": ["approve", "reject"]},
      "feedback": {"type": "string"}
    },
    "required": ["user_decision"]
  },
  "hitl_request_details": {
    "prompt": "Please review the generated content and provide approval",
    "context": "Content generation completed, awaiting final review"
  }
}
```

### HITL Best Practices

1. **Save Run IDs**: Always save the `run_id` from HITL outputs for later resumption
2. **Validate HITL Inputs**: Ensure your HITL inputs match the provided schema exactly
3. **Handle HITL States**: Check output status for `waiting_hitl` to detect HITL requirements
4. **Thread Consistency**: Use the same `_thread_id` when resuming HITL workflows
5. **Timeout Considerations**: HITL workflows may pause for extended periods - plan accordingly

## Configuration (`WorkflowRunnerConfig`)

Most settings have sensible defaults. Focus on workflow identification and leave other settings unchanged unless you have specific requirements.

### Workflow Identification (Required - Choose One)

```json
{
  "workflow_name": "content_creation_workflow",
  "workflow_version": "v1.0"
}
```
OR
```json
{
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

- **`workflow_name`** (string): Name of the workflow to run
  - Takes precedence over workflow_id if both provided
  - Can be combined with `workflow_version` for specific versions
  
- **`workflow_id`** (string): UUID of the workflow to run
  - Use when you have the exact workflow ID
  - Version is determined by the specific workflow ID

- **`workflow_version`** (string, optional): Version tag of the workflow
  - Only used with `workflow_name`
  - If not specified, uses the latest version

### Execution Settings (Usually Keep Defaults)

```json
{
  "execution_mode": "subprocess",
  "poll_interval_seconds": 3,
  "timeout_seconds": 1200,
  "fail_on_workflow_error": true
}
```

- **`execution_mode`** (string, default "subprocess"): How to execute the workflow
  - `"subprocess"`: Connected execution with parent-child relationship
  - `"independent"`: Separate execution without parent connection
  
- **`poll_interval_seconds`** (int, default 3): How often to check workflow status
  - Range: 1-60 seconds
  - Lower values = more responsive but more system checks
  
- **`timeout_seconds`** (int, default 1200): Maximum wait time before timeout
  - Range: 10-3600 seconds (20 minutes default)
  - Increase for long-running workflows
  
- **`fail_on_workflow_error`** (bool, default true): Node behavior on workflow failure
  - `true`: This node fails if the triggered workflow fails
  - `false`: This node succeeds but includes error details in output

### Caching Settings (Optional)

```json
{
  "enable_workflow_cache": true,
  "cache_lookback_period": 7,
  "check_error_free_logs": true
}
```

- **`enable_workflow_cache`** (bool, default true): If true, the node attempts to reuse outputs from a recent run of the same workflow when inputs are identical.
- **`cache_lookback_period`** (int, default 7): Number of days to look back for matching runs.
- **`check_error_free_logs`** (bool, default true):
  - When true, the node only reuses runs whose Prefect logs contain no ERROR/CRITICAL entries.
  - When false, the node will pick the recent run with the fewest error logs (ties prefer the most recent).

How cache matching works:
- The node maps your `input_data` to the target workflow's inputs, then computes a deterministic hash from the normalized JSON (sorted keys) of those mapped inputs.
- It preferentially searches by `(workflow_name, owner_org_id, input_hash)` and falls back to `(workflow_id, owner_org_id, input_hash)` when needed.
- Only runs with status `COMPLETED` and without a stored error message are considered.
- If `check_error_free_logs=true`, the candidate must have zero error logs (from Prefect). If logs cannot be fetched, the run is considered unsafe for reuse.
- On a cache hit, the node immediately returns the cached run's outputs without re-executing the workflow. The `run_id` in the output corresponds to the reused run.

Example with caching enabled and strict log checks:
```json
{
  "node_config": {
    "workflow_name": "content_generation_workflow",
    "enable_workflow_cache": true,
    "cache_lookback_period": 14,
    "check_error_free_logs": true
  },
  "input": {
    "entity_username": "company_profile",
    "content_brief": "Write about our new product launch",
    "tone": "professional"
  }
}
```

Example using lenient log selection:
```json
{
  "node_config": {
    "workflow_name": "content_generation_workflow",
    "enable_workflow_cache": true,
    "cache_lookback_period": 7,
    "check_error_free_logs": false
  }
}
```

### Input/Output Mapping (Advanced)

```json
{
  "input_mapping": {
    "entity_username": "user.profile.username",
    "content_brief": "documents.brief"
  },
  "output_fields": ["generated_content", "metadata"]
}
```

- **`input_mapping`** (object, optional): Map workflow inputs to your data structure
  - Format: `{"workflow_field": "path.to.value"}`
  - Uses dot notation for nested values
  - If not specified, uses direct field name matching
  
- **`output_fields`** (array, optional): Specific fields to extract from results
  - If not specified, returns all workflow outputs
  - Use to filter large outputs to only needed data

## Input (`WorkflowRunnerInput`) - Dynamic Fields

This node accepts **any input fields** you provide. The fields are either:
1. **Directly matched** to the target workflow's inputs (if names match exactly)
2. **Mapped** using the `input_mapping` configuration

### Special Control Fields (Optional)

These special fields (prefixed with underscore or specific to HITL) can override configuration or provide HITL functionality:

```json
{
  "_override_workflow_name": "alternate_workflow",
  "_override_workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "_override_workflow_version": "v2.0",
  "_thread_id": "conversation-123",
  "hitl_inputs": {
    "user_decision": "approve",
    "feedback": "Looks good!"
  },
  "subworkflow_run_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

- **`_override_workflow_name`**: Override the configured workflow name
- **`_override_workflow_id`**: Override the configured workflow ID
- **`_override_workflow_version`**: Override the configured version
- **`_thread_id`**: Maintain conversation context across workflow executions
- **`hitl_inputs`**: Human responses for resuming a workflow from HITL state
- **`subworkflow_run_id`**: Required with `hitl_inputs` - the run ID to resume

### Example Input Patterns

#### Direct Field Matching
If your target workflow expects `entity_username` and `user_input`:
```json
{
  "entity_username": "john_doe",
  "user_input": "Write about AI trends",
  "past_context_posts_limit": 10
}
```

#### Using Input Mapping
If your data structure doesn't match the target workflow:
```json
{
  "user_data": {
    "profile": {
      "username": "john_doe"
    }
  },
  "content": {
    "prompt": "Write about AI"
  }
}
```
With configuration:
```json
{
  "input_mapping": {
    "entity_username": "user_data.profile.username",
    "user_input": "content.prompt"
  }
}
```

#### HITL Resume Pattern
When resuming a workflow that was paused for human input:
```json
{
  "hitl_inputs": {
    "user_decision": "approve",
    "feedback": "Content looks great, please proceed with publishing",
    "priority": "high"
  },
  "subworkflow_run_id": "550e8400-e29b-41d4-a716-446655440000",
  "_thread_id": "conversation-123"
}
```
This pattern resumes the specific workflow run with human-provided responses.

## Output (`WorkflowRunnerOutput`)

The node provides comprehensive information about the executed workflow.

### Execution Identification
- **`workflow_id`**: UUID of the executed workflow
- **`workflow_name`**: Name of the executed workflow
- **`workflow_version`**: Version that was executed
- **`run_id`**: Unique identifier for this execution

### Results
- **`status`**: Final execution status
  - `"completed"`: Workflow finished successfully
  - `"failed"`: Workflow encountered an error
  - `"cancelled"`: Workflow was cancelled
  - `"timeout"`: Execution exceeded timeout limit
  - `"waiting_hitl"`: Workflow paused and waiting for human input
  
- **`workflow_outputs`**: Results from the executed workflow
  - Contains either all outputs or filtered based on `output_fields`
  - Structure depends on the specific workflow being executed
  - May be null for workflows in `waiting_hitl` state

### Execution Metadata
- **`execution_mode`**: Mode used ("subprocess" or "independent")
- **`started_at`**: When execution began (ISO 8601 timestamp)
- **`completed_at`**: When execution finished
- **`duration_seconds`**: Total execution time
- **`parent_run_id`**: Parent workflow ID (only in subprocess mode)

### Error Information (if applicable)
- **`error_message`**: Human-readable error description
- **`error_details`**: Detailed error information for debugging

### HITL Information (when status is "waiting_hitl")
- **`hitl_job_id`**: Unique identifier for the HITL job requiring attention
- **`hitl_request_schema`**: JSON schema defining the expected format for human responses
- **`hitl_request_details`**: Human-readable information about what input is needed
  - Contains details like prompt, context, and instructions for human reviewers

## Example Configurations

### Basic Workflow Execution
```json
{
  "node_config": {
    "workflow_name": "content_generation_workflow"
  },
  "input": {
    "entity_username": "company_profile",
    "content_brief": "Write about our new product launch",
    "tone": "professional"
  }
}
```

### Workflow with Version Control
```json
{
  "node_config": {
    "workflow_name": "data_analysis_workflow",
    "workflow_version": "v2.1",
    "timeout_seconds": 600
  },
  "input": {
    "data_source": "sales_q4_2024",
    "analysis_type": "trend_analysis"
  }
}
```

### Conversational Workflow with Thread Context
```json
{
  "node_config": {
    "workflow_name": "ai_assistant_workflow"
  },
  "input": {
    "user_message": "What did we discuss earlier?",
    "_thread_id": "conversation-abc-123"
  }
}
```

### Complex Input Mapping
```json
{
  "node_config": {
    "workflow_name": "research_workflow",
    "input_mapping": {
      "search_query": "research.topic",
      "max_results": "settings.result_limit",
      "sources": "research.allowed_sources"
    },
    "output_fields": ["summary", "key_findings"]
  },
  "input": {
    "research": {
      "topic": "renewable energy trends",
      "allowed_sources": ["academic", "news"]
    },
    "settings": {
      "result_limit": 50
    }
  }
}
```

### Independent Execution with Error Handling
```json
{
  "node_config": {
    "workflow_name": "notification_workflow",
    "execution_mode": "independent",
    "fail_on_workflow_error": false
  },
  "input": {
    "recipient": "user@example.com",
    "message": "Process completed successfully"
  }
}
```

### HITL Workflow with Resume Capability
```json
{
  "node_config": {
    "workflow_name": "content_approval_workflow",
    "timeout_seconds": 1800
  },
  "input": {
    "content_draft": "Generated article content...",
    "approval_required": true
  }
}
```

**Initial execution output (when workflow reaches HITL):**
```json
{
  "workflow_id": "550e8400-e29b-41d4-a716-446655440001",
  "run_id": "550e8400-e29b-41d4-a716-446655440002",
  "status": "waiting_hitl",
  "workflow_outputs": null,
  "hitl_job_id": "123e4567-e89b-12d3-a456-426614174001",
  "hitl_request_schema": {
    "type": "object",
    "properties": {
      "approval_decision": {"type": "string", "enum": ["approve", "reject", "revise"]},
      "feedback": {"type": "string"},
      "revision_notes": {"type": "string"}
    },
    "required": ["approval_decision"]
  },
  "hitl_request_details": {
    "prompt": "Please review the generated content and make your approval decision",
    "context": "Content generation workflow completed, awaiting editorial review"
  }
}
```

**Resume execution with HITL inputs:**
```json
{
  "node_config": {
    "workflow_name": "content_approval_workflow"
  },
  "input": {
    "hitl_inputs": {
      "approval_decision": "approve",
      "feedback": "Content looks great, ready for publication",
      "revision_notes": "No revisions needed"
    },
    "subworkflow_run_id": "550e8400-e29b-41d4-a716-446655440002"
  }
}
```

## Common Use Cases

### 1. Modular Workflow Design
Break complex processes into reusable workflow components:
- **Main workflow**: Orchestrates the overall process
- **Sub-workflows**: Handle specific tasks (research, content creation, validation)
- **Benefit**: Reusable components, easier maintenance

### 2. Dynamic Workflow Selection
Choose which workflow to run based on conditions:
```json
{
  "input": {
    "_override_workflow_name": "{{selected_workflow_from_previous_node}}",
    "data": "{{dynamic_input_data}}"
  }
}
```

### 3. Conversational AI Flows
Maintain context across multiple interactions:
```json
{
  "input": {
    "user_query": "{{current_user_message}}",
    "_thread_id": "{{conversation_id}}",
    "context_window": 10
  }
}
```

### 4. Parallel Processing Patterns
Execute multiple workflows for different aspects:
- Use multiple WorkflowRunnerNodes in parallel
- Each handles a different aspect of processing
- Combine results in a subsequent node

### 5. Human-in-the-Loop Workflows
Create workflows that require human review or approval:
- **Content Review**: Generate content and pause for editorial approval
- **Decision Making**: Present options and wait for human selection
- **Quality Control**: Pause processing for manual inspection
- **Exception Handling**: Escalate to human when automated processing fails

## Best Practices

### Workflow Design
1. **Keep workflows focused**: Each workflow should have a clear, single purpose
2. **Use meaningful names**: Choose descriptive workflow names for easy identification
3. **Version appropriately**: Use versions when making breaking changes
4. **Document inputs**: Ensure target workflows have clear input requirements

### Performance Optimization
1. **Set appropriate timeouts**: Based on expected workflow duration
2. **Use subprocess mode**: For connected workflows (default)
3. **Consider caching**: In the target workflows for repeated operations
4. **Monitor execution times**: Adjust timeouts based on actual performance

### Error Handling
1. **Use fail_on_workflow_error wisely**:
   - `true` for critical dependencies
   - `false` for optional or notification workflows
2. **Check status in output**: Always verify execution status
3. **Log important executions**: Track workflow chains for debugging
4. **Handle timeouts gracefully**: Set realistic timeout values

### Data Management
1. **Map inputs explicitly**: Use input_mapping for clarity
2. **Filter outputs**: Use output_fields to reduce data transfer
3. **Validate data types**: Ensure input data matches target workflow expectations
4. **Preserve context**: Use thread_id for conversational workflows

### HITL (Human-in-the-Loop) Management
1. **Monitor status**: Always check output status for `waiting_hitl` state
2. **Store run IDs**: Save `run_id` from HITL outputs for later resumption
3. **Validate HITL inputs**: Ensure human responses match the provided schema exactly
4. **Handle timeouts**: HITL workflows may pause indefinitely - plan for extended wait times
5. **Maintain context**: Use consistent `_thread_id` when resuming HITL workflows
6. **Cache consideration**: HITL resume operations skip cache lookup by design
7. **Error handling**: Implement proper error handling for invalid HITL resume attempts

## Notes for Non-Coders

- **Purpose**: This node lets one workflow run another workflow, like calling a function
- **Think of it as**: A workflow calling a helper workflow to do part of the job
- **Default settings work**: You mainly need to specify which workflow to run
- **Input flexibility**: The node accepts any data and passes it to the target workflow
- **Automatic monitoring**: The node waits for the workflow to complete and returns results
- **Error handling**: By default, if the called workflow fails, this node fails too
- **Modular design**: Break complex processes into smaller, reusable workflows

## Troubleshooting Common Issues

### Workflow Not Found
- **Check** workflow name spelling and case sensitivity
- **Verify** workflow exists and is accessible to your organization
- **Consider** using workflow_id if name matching issues persist

### Input Data Not Passed Correctly
- **Review** field names match exactly (for direct matching)
- **Use** input_mapping for complex data structures
- **Check** data types match workflow expectations
- **Verify** required fields are provided

### Execution Timeout
- **Increase** timeout_seconds for long-running workflows
- **Check** if target workflow is actually running (may be queued)
- **Consider** breaking into smaller workflows if consistently timing out

### Missing Output Data
- **Verify** target workflow actually produces expected outputs
- **Check** output_fields spelling if filtering
- **Remove** output_fields to see all available outputs
- **Ensure** target workflow completed successfully

### Thread Context Not Maintained
- **Provide** _thread_id consistently across calls
- **Use** same thread_id format (UUID string)
- **Verify** target workflow supports thread context

### HITL Resume Issues
- **Missing subworkflow_run_id**: Always provide the exact run_id from the HITL output
- **Invalid HITL inputs**: Ensure your inputs match the hitl_request_schema exactly
- **Schema validation errors**: Check that all required fields are provided in hitl_inputs
- **Run not found**: Verify the subworkflow_run_id exists and is in HITL state
- **Workflow not resumable**: Some workflows may not support HITL resumption

### HITL Detection Problems
- **Status not detected**: Ensure you're checking the `status` field in outputs
- **Missing HITL details**: Check for network issues when fetching HITL job details
- **Timeout during HITL**: HITL workflows may pause indefinitely - this is expected behavior

## Integration Example in Workflow

```json
{
  "nodes": {
    "research_phase": {
      "node_id": "research_phase",
      "node_name": "workflow_runner",
      "node_config": {
        "workflow_name": "research_workflow",
        "output_fields": ["findings", "sources"]
      }
    },
    "content_creation": {
      "node_id": "content_creation",
      "node_name": "workflow_runner",
      "node_config": {
        "workflow_name": "content_generation_workflow",
        "input_mapping": {
          "research_data": "research_results.findings",
          "tone": "settings.writing_tone"
        }
      }
    }
  },
  "edges": [
    {
      "src_node_id": "research_phase",
      "dst_node_id": "content_creation",
      "mappings": [
        {"src_field": "workflow_outputs", "dst_field": "research_results"}
      ]
    }
  ]
}
```

## Summary

The WorkflowRunnerNode is your tool for creating sophisticated, modular workflow systems. It allows workflows to leverage other workflows as building blocks, enabling complex orchestration while maintaining clean, reusable components. With full HITL (Human-in-the-Loop) support, it can also manage workflows that require human interaction, automatically detecting when human input is needed and providing seamless resumption capabilities.

Key capabilities:
- **Workflow orchestration**: Execute subworkflows with proper parent-child relationships
- **Dynamic input mapping**: Flexible data passing between workflows
- **HITL support**: Full detection, schema exposure, and resumption for human-interactive workflows
- **Thread context**: Maintain conversation state across workflow executions
- **Error handling**: Configurable failure behavior and comprehensive status reporting

Focus on identifying the right workflow to run and mapping your data correctly - the node handles all the execution complexity, including HITL states, for you.