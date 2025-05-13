# Phase 1: Development, testing and Productionizing the workflow

# Phase 2: Use SDK: application workflow ingestion and testing from SDK

## Workflow Ingestion Process

The ingestion process involves several key steps for properly importing workflow schemas into the system, verifying ingestion, and validating workflow behavior through testing.

### Workflow Ingestion Steps

1. **Preparation and Configuration**
   - Prepare .env to have email, password, org ID for admin@example.com superuser and KIWIQ org (fetch orgs for admin@example.com from [api.prod.kiwiq.ai/docs](https://api.prod.kiwiq.ai/docs) )

   - Define workflow configurations with required properties:
     - `workflow_key`: The unique identifier for the workflow (reference the [Workflow Config](https://www.notion.so/Workflow-Config-1ef12cba067e8074b16aeecb3498c4fa))
     - `module_path`: Path to the Python module containing the workflow schema
     - `run_test` (optional): Boolean flag to indicate if test should be run after ingestion
     - `test_inputs_override` (optional): Dictionary of input values to override default inputs
     - `test_timeout_sec` (optional): Timeout duration for test execution (default: 600 seconds)
     - `hitl_inputs` (optional): Predefined responses for HITL steps in the workflow

2. **Workflow Schema Import**
   - Import the workflow schema from the relevant module (e.g., `workflows/wf_content_generation.py`)
   - Validate schema structure before proceeding with ingestion

3. **Superuser Verification**
   - Verify the authenticated user has superuser permissions
   - Confirm user email matches expected superuser email (typically `admin@example.com`)

4. **Workflow Information Lookup**
   - Use artifact client to retrieve workflow name and version from workflow key
   - This ensures consistent naming and versioning based on the workflow configuration

5. **Cleanup of Existing Workflows**
   - Search for any existing workflow with the same name/version
   - Delete previous versions to avoid conflicts

6. **Workflow Creation**
   - Ingest the workflow with following parameters:
     - Set workflow name/version exactly as retrieved from artifacts API
     - Set organization ID to superuser's org (typically KIWIQ)
     - Set `is_system_entity` and `is_public` to `True`
     - Set appropriate description and launch status

7. **Verification of Ingestion**
   - Search for the ingested workflow to confirm successful creation
   - Verify the graph schema matches the expected structure

### Workflow Testing Process

If testing is enabled through the `run_test` flag:

1. **Input Preparation**
   - Fetch default workflow inputs using artifacts client
   - Apply any input overrides specified in the configuration
   - Verify all required inputs have values (none are `None`)

2. **Execute Test Run**
   - Launch workflow execution with prepared inputs
   - Monitor workflow state through polling or event streaming
   - Handle any HITL interactions if configured

3. **Validation**
   - Verify workflow reaches `COMPLETED` status
   - Check outputs match expected structure and values
   - Review workflow logs for errors or warnings
   - Ensure all output files are properly generated

4. **Documentation**
   - Log results of ingestion and testing process
   - Record workflow ID for future reference


From client `test_run_workflow_client.py` import and use the below function as follows while providing the appropriate workflow inputs

```python
import asyncio
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus
from kiwi_client.test_run_workflow_client import run_workflow_test

test_name = 
workflow_key = 
workflow_inputs = 
predefined_hitl_inputs = []
validate_workflow_output = None

async def test():
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        
        workflow_key=workflow_key,
        initial_inputs=workflow_inputs,
        
        # OPTIONAL: if not provided, user is prompted to enter input in JSON during workflow execution
        hitl_inputs=predefined_hitl_inputs,

        # OPTIONAL: can be None, a function to assert and only to validate final workflow output
        validate_output_func=validate_workflow_output,

        # Don't change unless necessary
        expected_final_status=WorkflowRunStatus.COMPLETED,
        stream_intermediate_results=True,
        poll_interval_sec=3,
        timeout_sec=600
    )

if __name__ == "__main__":
    asyncio.run(test())

```


### Example Code for Workflow Ingestion

```python
# Configure workflow for ingestion
workflow_config = {
    "workflow_key": "content_creation_workflow",
    "module_path": "workflows.wf_content_generation",
    "run_test": True,
    "test_inputs_override": {
        "user_id": "test_user_123",
        "content_type": "blog_post"
    }
}

# Initialize the ingestion client
ingestion_client = WorkflowIngestionClient(auth_client)

# Perform ingestion and testing
workflow_id, test_success = await ingestion_client.ingest_workflow(
    workflow_schema=import_workflow_schema_from_path(workflow_config["module_path"]),
    workflow_key=workflow_config["workflow_key"],
    run_test=workflow_config.get("run_test", False),
    test_inputs_override=workflow_config.get("test_inputs_override"),
    test_timeout_sec=workflow_config.get("test_timeout_sec", 600)
)

# Check results
if workflow_id and test_success:
    print(f"Workflow {workflow_config['workflow_key']} successfully ingested and tested")
else:
    print(f"Issue with workflow {workflow_config['workflow_key']}")
```



# Phase 2.b: Prerequisite Documents for Workflows

Before executing any workflow, ensure all prerequisite documents are properly ingested:

1. **Document Requirements**
   - Each workflow may depend on specific documents being available in the system
   - These documents must be ingested before workflow execution can succeed

2. **Document Types**  - TODO: Gaurav --> link to the document schemas??
   - **User-specific documents**: Must be ingested in the correct namespace/docname for the user
   - **System documents**: Must be ingested with `is_system_entity=True` and `is_shared=True` flag set

3. **Document Validation**
   - Ensure document structure/schema is consistent with what's expected in the workflow 
   - Documents must be ingested as JSON (if schema-based and not text based) and not as JSON strings
   - Reference [Document Config](https://www.notion.so/Document-Config-1ef12cba067e80fba3a0f2996b1f9547) for configuration details

4. **Document Ingestion Process**
   - Use appropriate document ingestion methods from the SDK
   - Verify document exists and has correct structure before workflow execution
   - For system documents, ensure proper visibility settings

> **IMPORTANT**: Document schema inconsistencies are a common source of workflow failures. Always validate document structure against workflow expectations.


# Phase 3: Frontend Integration and Testing Using APIs Directly

This phase outlines how to integrate workflows into frontends using direct API calls instead of the SDK.

## Workflow Discovery and Setup

### 1. Workflow Lookup and Configuration
- **Fetch Workflow Information**
  - Use artifacts API to retrieve workflow name/version using workflow key
  - Reference workflow keys from [Workflow Config](https://www.notion.so/Workflow-Config-1ef12cba067e8074b16aeecb3498c4fa)
- **Search and Retrieve Workflow**
  - Use workflow search API with fetched name/version to get workflow details

### 2. Input Preparation
- **Process Workflow Inputs**
  - Analyze inputs from artifacts API response
  - For any `None` fields, collect required inputs from:
    - User interface inputs
    - Application state
    - Other contextual sources

## Workflow Execution

### 1. Launch Workflow
- **Execute Workflow**
  - Call workflow execution API with prepared inputs
  - Store returned `run_id` for monitoring and resumption
  - For long-term persistence, save `run_id` in `app_state`
  - **NOTE**: You can list all user's workflow runs using [/api/v1/runs]() API with status filters (running, completed)
    - This API returns timestamps (`created_at`, `updated_at`) for chronological sorting

### 2. Progress Monitoring

#### Real-Time Notifications via WebSockets
- **Notification Channels**:
  - **Global notifications**: High-level workflow state changes and HITL notifications
  - **Run-specific stream**: All workflow events including token-level LLM streaming and HITL jobs

#### Status Monitoring via APIs
- **Run Detail APIs** (MongoDB-backed):
  - **Details API**: [/api/v1/runs/{run_id}/details]()
    - Provides node-specific output events and final outputs/HITL jobs
  - **Stream API**: [/api/v1/runs/{run_id}/stream]()
    - Includes all events: node outputs, LLM token streaming, HITL jobs

- **Run Status Summary** (PostgreSQL-backed):
  - **Status API**: [/api/v1/runs/{run_id}]()
    - Returns current workflow state: `SCHEDULED`/`RUNNING`/`FAILED`/`COMPLETED`/`WAITING_HITL`
    - Provides final workflow output (only when status is `COMPLETED`)

### 3. Human-in-the-Loop (HITL) Processing

- **HITL Job Management**
  - When workflow state is `WAITING_HITL`, check HITL API: [/api/v1/hitl]()
  - Use `run_id` and `pending_only=True` parameters to filter relevant HITL jobs
  - Extract from response:
    - `request_details`: Data to display to user
    - `response_schema`: Required format for user input

- **User Input Processing**
  - Present `request_details` to user in appropriate UI
  - Collect user input according to `response_schema`
  - Validate input against schema in a loop until valid
  - **Important**: Invalid inputs will cause workflow HITL to fail

- **Resume Workflow After HITL**
  - Call workflow run API [/api/v1/runs]() with:
    - `resume_after_hitl=True`
    - `run_id=<Original Run ID>`
  - **CRITICAL**: You MUST store the original run ID to enable workflow resumption

### 4. Workflow Completion

- **Retrieve Final Output**
  - Once workflow reaches `COMPLETED` state:
    - Call run summary API [/api/v1/runs/{run_id}]()
    - Process and display final workflow output

## Testing and Validation

### Integration Testing
- Conduct end-to-end testing with:
  - Superuser account
  - Regular user account

### Validation Criteria
- Verify:
  - Final outputs are correct
  - Workflow reaches `COMPLETED` status
  - All expected output files are correctly written
  
### Logs and State Analysis
- Use SDK helper methods:
  - `get_run_logs` and `get_run_state` in `run_client.py`
  - Check logs for absence of ERROR/WARNING/CRITICAL entries
  - Verify central state values and node outputs match expectations









# ARCHIVE - IGNORE

###### Phase 3: Frontend integration and testing using APIs directly

- Frontend Integration and testing:
    - Use artifacts API to fetch workflow name / version to search workflow and receive workflow inputs (use workflow key in the API -- this can be referenced from https://www.notion.so/Workflow-Config-1ef12cba067e8074b16aeecb3498c4fa)
    - Search and fetch workflow via fetched name / version using workflow search API
    - Workflow Inputs
        - For fetched inputs from artifacts API, if any field is None, that field needs inputs from user or app state, properly populate that with user specific inputs either from the user or the app state
    - Execute the workflow and store `run_id` either locally, or if user can leave the platform and come back, store it in `app_state` -> request additional keys in app_state to store diff run_ids if required
        - NOTE: there is also List workflow runs API: [/api/v1/runs]()  to get all user's runs and also filter by status (running, completed) it will return fields like `created_at` `updated_at` for further filtering / sorting
    - plug into the following to show user facing progress while workflow is running:
        - websockets (real time notifications): 
            - notifications only for high level workflow state change notifications and HITL jobs
            - run ID specific stream for all workflow run events including token level LLM streaming, HITL jobs
        - run APIs (via MONGO DB):
            - details [/api/v1/runs/{run_id}/details]() 
                -- receive every node specific output events and final outputs / hitl jobs
            - stream [/api/v1/runs/{run_id}/stream]() 
                -- receive all events, including node specific outputs, LLM token level streaming events from LLM calls, including HITL jobs
    - Either process above events or poll run status summary (below API) to get workflow status indicating completion: either of FAILED / WAITING_HITL / COMPLETED state
    - Get run status summary (via POSTGRES) [/api/v1/runs/{run_id}]() : 
        -- receive current state of workflow: either SCHEDULED / RUNNING / FAILED / COMPLETED / WAITING_HITL and also final output from workflow only after workflow has COMPLETED!
    - WAITING_HITL
        - If workflow is in WAITING_HITL state, the data to be shown to user and requested data schema are attached to a new HITL Job fetched via the HITL API [/api/v1/hitl]() using the `run_id` and `pending_only=True` to filter HITL jobs.
        - Get appropriate inputs from user in the exact schema as determined by `response_schema` from fetched HITL job while showing user data from `request_details`
            - Take inputs from the user in a loop until the user's inputs are validated and consistent with the request schema otherwise the workflow HITL will fail
        - RESUME RUN after HITL:
            - Use same workflow run submit API [/api/v1/runs]()  with `resume_after_hitl=True` and `run_id=<Above RUN's ID>` **YOU MUST STORE RUN ID TO BE ABLE TO RESUME WORKFLOWS!**
    - Get final workflow output after workflow state is in COMPLETED state:
        - run summary API (via POSTGRES) [/api/v1/runs/{run_id}]() : -- receive final output from workflow
    - Test frontend integrations:
        - After e2e integration based on above guidelines is done, test the workflow with both superuser account and regular user account
        - For each workflow, you need to test not just the final outputs and COMPLETED status, but also whether all files the workflow is outputing were written correctly
        - Use methods such as `get_run_logs` and `get_run_state` in the `run_client.py` to get run logs and state rendered and dumped into markdown and ensure there are no ERROR/WARNING/CRITICAL logs
        - Ensure the state is correct: check central state values and each node outputs and they should be consistent with the expected workflow node outputs / central state