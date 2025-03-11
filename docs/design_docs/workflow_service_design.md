Below is the updated design document. Every bullet point from the original has been incorporated—with additional context, detailed explanations, and explicit “TODO” markers where decisions or further research are indicated. At the end of each major section, a note summarizes whether any substantial new points (i.e. beyond rewording or reordering) were added that merit manual review.

---

# 1. Workflow Definition & Registries / Building Them

This section defines the core entities used to build workflows, how they are stored and versioned, and the central registry that underpins the entire system. In addition to a detailed explanation of each element, explicit “TODO” markers highlight areas requiring further decisions.

## 1.a. Key Entities

### Nodes

- **Inputs (Runtime):**
    - Each node can have one or more input fields.
    - **Optional Inputs:**
        - Some input fields may be optional—for example, when a default value is provided via configuration.
    - **User Visibility:**
        - Decide which input fields are user visible and which are internal.
- **Configuration (Instantiation):**
    - Nodes are instantiated with configuration parameters.
    - **Editable vs. Internal Fields:**
        - Some configuration fields are editable by users, while others remain internal.
    - **Defaults and Requirements:**
        - Default values and required fields must be clearly defined.
- **Outputs:**
    - Each node produces output data, which is passed to downstream nodes.
- **Identity and Versioning:**
    - Every node must have a unique name (within its scope) and an optional version number to manage upgrades and rollbacks.
- **Subnodes (Composability):**
    - Nodes can contain subnodes to enable complex, composite behavior.
- **Error Codes:**
    - Nodes should register explicit error codes along with details on:
        - How to process them,
        - Their meaning,
        - Actionable next steps for users.
    - **Alerts & Debugging:**
        - Unregistered error codes must trigger alerts.
    - **Implementation:**
        - Use try/catch blocks during node execution for known errors.
        - Maintain a central repository of error codes shared across nodes for consistent error handling.
- **Custom Events / Any Events:**
    - All events a node emits (for example, status updates or custom signals) must be registered.
    - Maintain a central repository of custom events to help with tracing and debugging.
- **Environment Flags:**
    - Nodes will be tagged with staging, experimental, or production flags.
    - Users only access production nodes, while admins and developers have access to all.

### Edges

- **Data Flow Edges:**
    - Edges connect nodes and pass data; they rely on a configuration-based method for accessing subfields (e.g., using subkeys on a parent node’s output).
- **Conditional Edges:**
    - Conditional routing is handled via dedicated If/Else nodes rather than implicit dependency-only edges (which are deprioritized).

### Workflows

- **Graph Structure:**
    - Workflows consist of input and output nodes that define the overall graph.
- **Workflow Templates:**
    - Templates are stored only in the database.
    - If a workflow template must be populated by code, this is done via scripts or workflow write APIs that store a JSON graph config (the same format received from the Agent Studio frontend).
    - **Versioning:**
        - Internal versioning is based on the node template versions.
        - A Git-like versioning system allows developers and users to tag or branch workflow templates as they evolve.
    - **Subgraphs:**
        - Templates have an attribute (e.g., `has_subgraphs`) indicating whether they include subgraphs.
        - **TODO:** Decide how to handle planning nodes that create dynamic graphs (e.g., a subgraph with at least two nodes—a planner and an executor—to propagate events upward).
- **Workflow Instances:**
    - Only workflow instances are executable.
    - Instances are created by users who adopt or build a workflow template.
    - They are owned by the user and have a unique ID but do not require globally unique names (they must be searchable/indexable).
    - **Graph Config Determinism:**
        - The JSON graph configuration must be deterministic and sorted to allow proper reconciliation and versioning.
    - **Staging Flags:**
        - Like nodes, workflow templates and instances are tagged as staging, experimental, or production.

### Templates and Instances

- **Templates vs. Instances:**
    - **Templates:**
        - Contain default configuration values and version numbers stored in the DB.
        - Are used as blueprints that can be adopted into executable instances.
    - **Instances:**
        - Are copies of template configurations with user-specific overrides.
        - Do not include code; they store only values (not metadata such as field types or descriptions).
        - Reference the source template (and thereby its code version) but do not have independent versioning.
    - **Auto-update Considerations:**
        - User instances (config copies) should auto-update with template changes to help restore previously working workflow versions.
        - **Config Versioning:**
            - Because only user-editable fields are preserved, there may be a need for separate config versioning to enable rollback without affecting non-editable fields.
        - **Field Deprecation:**
            - Instances include an extra marker for any field that is deprecated when removed from a template.

> Substantial Matter Changes (Section 1.a):
> 
> 
> In addition to reorganizing the original points, we have added explicit guidelines on error handling, event registration, environment flagging, and the nuances between templates and instances. These new clarifications require manual review to ensure alignment with the intended design.
> 

---

## Registry

The registry is a critical component for managing nodes, workflows, and their versions.

1. **Lookup Keys:**
    - Nodes and workflows are fetched using a composite key (unique name + version); if only the unique name is provided, the latest version is returned.
2. **Historical Recovery:**
    - Past versions of nodes must be recoverable—leveraging Git-like versioning—to restore previously successful workflow runs.
3. **Hot Swapping (Future Adapter Pattern):**
    - **IMP NOTE:** Design the system so that later the node/workflow code and config can be hot-swapped (e.g., pulled from S3) without a full CI/CD cycle.
    - Future registry services should reconcile the latest nodes and workflows, store previous versions, and manage compatibility issues.
4. **Leader Consensus:**
    - [Deprioritized] A leader consensus mechanism may be needed later to ensure all nodes are up-to-date.
5. **Timing of Version Passing:**
    - **Key Question:** At what point during execution is the node/workflow version passed to the state or context manager?
        - The conversion from user graph config to a langgraph-compiled graph should include version information for all nodes.
6. **Database-to-Code Reconciliation:**
    - Whenever nodes/workflows are present in code, reconciliation should occur.
    - **TODO:** Review Arjun’s workflow/nodes discovery service for insights.

### Central Registry Service

- **Purpose:**
    - A central service must register all nodes/workflows and handle rollouts of new versions.
    - It should apply short-term entity-level locks during updates to ensure consistency.
- **Responsibilities:**
    - Reconcile code state with DB state.
    - Manage migrations and obtain user notifications/consent for changes.
    - Determine atomic changes from code updates and migrate them automatically.
- **Local Registries:**
    - Each worker or workflow service has a local registry mapping node identifiers to code objects, which communicates with the central registry.
- **Edge Case:**
    - If a workflow is validated and assigned to a worker but then a node update occurs, the registry validation might expire. This scenario must be managed.
- **Dependency Navigation:**
    - During migrations, the registry must navigate the dependency tree of workflows/nodes affected by an update.
- **Initialization & Locks:**
    - The registry must block queries during initialization (e.g., on new commits or CI/CD runs).
    - **TODO:** Develop a strategy for entity-level locks during migrations to enable graceful workflow planning and blocking.

> Substantial Matter Changes (Registry):
> 
> 
> In addition to reordering, this section now explicitly details hot swapping, version-passing timing, and the role of a central registry service. These points introduce new operational considerations that need manual review.
> 

---

## Workflow Builder

### Frontend

- **User Interaction:**
    - The workflow builder UI must support history, redo/undo, and a Git-like system.
    - **User Activity Tracking:**
        - **TODO:** Integrate Posthog (or similar) to track user actions (e.g., how users interact with Agent Studio, the workflow builder, and run outputs) to collect implicit like/dislike signals.
- **Handling Base Template Changes:**
    - Define how changes in the base template code affect user-modified workflows.

### Backend

- **Registries and Querying:**
    - Backend systems will manage registry queries and graph-building.
- **Schema Enforcement:**
    - Enforce schema validation and provide tools for building graphs.

### ML Layer

- **Integration:**
    - Explore integration of an ML layer for additional functionality (e.g., recommendations, dynamic validations).

> Substantial Matter Changes (Workflow Builder):
> 
> 
> Additional details on user activity tracking, base template change handling, and ML integration have been introduced. These new points require manual review.
> 

---

# 2. Workflow Execution

This section describes the runtime aspects of workflows—from run object management and runtime context to state persistence, asynchronous tasks, caching, safeguards, error handling, and execution operations.

## Run Entities

- **Run Object Structure:**
    1. **Metadata:**
        - May include a parent Run ID (for forks) and fork configuration.
        - Contains information such as the user context and which instance was executed.
    2. **Run ID:**
        - This serves as the thread ID within langgraph.
    3. **Workflow State:**
        - Stores the entire workflow state, including configuration and runtime data.
- **DB Transactions:**
    - **TODO:** Identify areas where DB transactions are needed for fault tolerance.
- **Instance Config Initialization:**
    - Instance configuration values are merged with template defaults during node instantiation.

## Runtime Context Manager

- **Purpose:**
    - Passed via dynamic config in langgraph, it allows nodes and workflows to interact with external systems (e.g., databases).
- **Capabilities:**
    - **Traceability:**
        - Enables tracking across node executions, including composable nodes that invoke subnodes.
        - **TODO:** (Quick hack) Consider storing node runs separately to trace thread IDs, checkpoints, and parent node relationships.
    - **Subscription/Billing:**
        - May also be used to manage subscription details or billing.
        - **TODO:** Review callback mechanisms in [langchain callbacks](https://python.langchain.com/docs/concepts/callbacks/).
    - **External Interactions:**
        - Although it might not be necessary to route all external interactions via the context manager, it should at least manage user ID and cross-thread memory storage.
- **Non-JSON Serializable Objects:**
    - Support dynamic runtime configs that include non-JSON serializable objects (see provided reference).

## 2.a. Workflow State Management

- **State and Checkpointing:**
    - Every run stores the full configuration and inputs for reproducibility.
    - **Tracing:**
        - This includes both composable nodes and subgraphs. Subgraphs may either share the parent’s state (static) or build a separate state graph (dynamic).
- **Custom Events Streaming:**
    - Nodes emit custom events that are streamed and can be filtered or aggregated.
    - **References:**
        - See langgraph guides on streaming events and filtering configurations.
- **Handling Forks:**
    - **TODO:** Explore strategies for forking state:
        - Options include copying the state to a new thread or replaying checkpoints.
        - Consider how to update specific nodes if branches diverge.
- **Langgraph State Persistence:**
    - **State Object Schema:** [Reference](https://langchain-ai.github.io/langgraph/concepts/persistence/#get-state)
    - **StateSnapshot:**
        - Checkpoints and history are defined in the langgraph types.
        - **NOTE:** The `get_state_history` may return the complete state history—verify behavior with nested subgraphs.
    - **Subgraph Persistence:**
        - Tasks include storing subgraph configurations as part of the parent’s state.
        - **Resources:**
            - [Subgraph persistence guide](https://langchain-ai.github.io/langgraph/how-tos/subgraph-persistence/#verify-persistence-works)
            - [How-to notebooks for subgraphs](https://github.com/langchain-ai/langgraph/blob/main/docs/docs/how-tos/subgraph-persistence.ipynb)

### 2.a.i. Async Background Jobs / Tasks

- **Examples:**
    - Logging database calls (e.g., storing events).
    - Tracking composable node usage asynchronously.

## 2.b. Caching

- **Scope:**
    - Evaluate whether caching should be implemented at the node level, workflow level, or even for LLM responses.

## 2.c. Safeguards

- **Runtime Limits:**
    - Maximum number of allowed loops.
    - Execution timeouts.
    - Maximum data generation limits.
    - Maximum token budget.
- **Default Limits:**
    - Use langgraph’s built-in recursion limits and implement LLM Gateway guardrails.

## 2.d. Worker Pools

- **Technologies:**
    - Support integration with worker pool frameworks such as Celery and Prefect.

## Errors and Recovery; Failing Gracefully; Debugging Flows

- **Error Handling Policy:**
    - Failed workflows are not automatically retried; instead, the user is notified and given a one-click retry option.
    - **Retry Policies:**
        - Leverage langgraph’s retry policies.
        - Failures can be detected using state snapshot tasks.
- **Known Errors:**
    - **Examples:**
        - Billing out of budget, tool access not provided, wrong API key.
    - **Action Items:**
        1. Create custom error codes.
        2. Emit error events for tracing.
        3. Gracefully fail with clear user notifications (error code, message, next steps).
        4. Handle external dependency failures (LLM router issues, tool downtimes, etc.).
        5. **TODO:** Evaluate custom events logging and visualization in langfuse.
        6. **TODO:** Investigate integration with langgraph’s error handling infrastructure.
        7. **TODO:** In the event of system failure or update, decide whether pending workflows should be marked as failed or automatically retried.

## Workflow Execution Operations

- **Lifecycle Controls:**
    1. **Resume:**
        - Support resuming workflows that were pended due to unmet dependencies or crashes.
    2. **Pause/Cancel:**
        - Allow workflows to be paused or cancelled.
    3. **Replay/Fork/Debug Modes:**
        - Provide a debug mode for executing a single or group of nodes.
        - **Forking:**
            - Use langgraph’s time-travel/replay capabilities (see [replaying guide](https://langchain-ai.github.io/langgraph/concepts/time-travel/#replaying)).
            - **Input Management:**
                - Automatically detect and provide inputs either by forking from the last run or by letting the user override them.
    4. **Alternate Execution:**
        - [Possible, but not in scope] Continue execution from a different node by updating the execution pointer.
- **Pended and Resume:**
    - Langgraph’s state manager (e.g., using Postgres) handles pended workflows.
    - A persisted HITL queue ensures that workflows wait for human input even if the response is delayed.

### Update State: HITL & Forking

1. **State Checkpointing:**
    - The update state operation creates a new checkpoint.
    - **Reference:** [State checkpoint discussion](https://github.com/langchain-ai/langgraph/discussions/938#discussioncomment-9988020)
2. **MessageState:**
    - Updates are handled via a MessageState object and reducers that replace existing messages (if the ID is unchanged) rather than appending.
    - **References:**
        - [Working with messages in graph state](https://langchain-ai.github.io/langgraph/concepts/low_level/#working-with-messages-in-graph-state)
3. **Fork Checkpoint Terminology:**
    - **TODO:** Decide if explicit naming is needed for fork checkpoints or branches.
    - Update state returns a branch configuration that can be used for replaying (see [branch off a past state](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/time-travel/#branch-off-a-past-state)).
4. **Impact on Execution/State History:**
    - **TODO:** Investigate how HITL/forking changes the state history and what visualization should occur.

### HITL (Human-in-the-Loop)

- **Design:**
    - Implement a separate HITL node that loops until the human approves.
- **Interrupts:**
    - **TODO:** Determine how events are tracked (e.g., via langfuse) when an interrupt occurs.
    - If an interrupt happens in the middle of a node, the node may restart entirely—this is a potential source of dynamic interrupts.
    - **Design Patterns:**
        - Refer to [langgraph’s human-in-the-loop design patterns](https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/#design-patterns) for approaches like:
            - Approve/Reject
            - Review/Edit graph state or outputs (e.g., a review tool call)
            - Multi-turn conversations to gather requirements
            - Validating human input through loops and multiple interrupts

> Substantial Matter Changes (Section 2):
> 
> 
> This section now includes comprehensive details on state management, asynchronous background tasks, caching, safeguards, worker pool integrations, and an in-depth discussion on error handling and HITL/forking. These new details and clarifications introduce significant new operational strategies that require manual review.
> 

---

# 3. Past Workflow Runs

**Observability, Logging, and Tracing:**

- **Monitoring:**
    - Integrate observability tools such as OpenTelemetry with langgraph.
    - Langchain callbacks may also be used to capture detailed trace data.
- **Trace Fetching:**
    - Retrieve and visualize traces via langfuse.
- **User Feedback:**
    - **TODO:** Add mechanisms for users to provide feedback (likes/dislikes, scoring, flagging outputs or intermediate results).

> Substantial Matter Changes (Section 3):
> 
> 
> This section now explicitly outlines observability, logging, and feedback channels. These additions—though mostly clarificatory—should be reviewed for operational fit.
> 

---

# 4. Workflow/Node New Launch / Migrations / Versioning

This section covers change management, versioning of nodes and workflows, and the implications for backward compatibility.

## Change Management System

1. **Backward Compatibility:**
    - Ensure that changes to nodes or workflows do not break existing executions.
2. **Node Composability & Dependency Management:**
    - **Node Init Mode:**
        - Decide whether a node is initialized from a full workflow, a subworkflow, or as a composable module.
    - **Composable Mode Tracing:**
        - Trace composable nodes (used as functions/modules) using context managers that track internal variables.
    - **Subnode Tracking:**
        - Ensure that subnodes are traced via dynamic configuration passed at runtime.
3. **Scheduled Maintenance and Rollout:**
    - **New Versions:**
        - Implement scheduled blackouts where new workloads are not accepted during maintenance.
    - **Rollout Strategy:**
        - Use CI/CD initially; later, migrate to a dedicated registry service that handles rollouts.

> Substantial Matter Changes (Change Management):
> 
> 
> New strategies for handling node composability, scheduled rollouts, and migration impacts have been added. These changes introduce additional complexity that requires manual review.
> 

## Node Versioning and Updates

### Operations Needing Backward Compatibility:

1. **Forking/Replay Past Runs:**
    - Enable workflows to be restarted from the same configuration and inputs.
2. **Overlayed Node Outputs:**
    - **TODO:** Confirm if a feature to display past node-level outputs overlaid in the workflow builder is required.
3. **Current Instances:**
    - Support day-to-day and scheduled workflow runs while allowing dynamic input changes.

### Types of Node Changes and Considerations:

1. **Node Code Changes:**
    - Version node code so that rollback is possible via Git.
    - **Notification:**
        - **NOTE:** Inform users of silent upgrades and provide support links for rollback requests.
2. **Input Schema Changes:**
    - Schema modifications (change, add, remove, rename, or change type) must be carefully managed:
        - Removing a field can be non-breaking if the corresponding data mapping is reconciled.
        - Adding a field is breaking—new edges or modifications are needed.
        - **Suggested Solution:**
            - Create a new node version while keeping the old version available; inform users via an update channel.
3. **Configuration Changes:**
    - Any new config fields must be propagated to all workflow instances.
    - Removal should mark a field as deprecated before complete deletion.
4. **Default Value Changes:**
    - These are backward compatible, but for UX purposes, users should be notified (and possibly given a side-by-side comparison on the UI).
5. **Node Deletion:**
    - Prefer deprecation over deletion; notify users to migrate to newer versions.
6. **Unique Name Changes:**
    - If a node’s unique name changes, update all references (instances, templates, registry entries) and notify users.
7. **Additional Considerations (Deprioritized):**
    - **TODO:** Evaluate adding node interrupts or new error/streaming events.
8. **Changelist Extraction:**
    - **Approaches:**
        - Supply a changelist in code.
        - Or automatically deduce atomic changes by reconciling code with DB versions.

## Workflow Versioning

1. **Graph Architecture & Config Changes:**
    - Changes may involve adding/removing nodes or edges and modifying existing connections.
    - Workflow templates use a Git-like model:
        - The base template is the “main” thread.
        - User modifications create branches.
    - All edit histories and tagged releases must be preserved for both developer and user changes.
    - **TODO:** Determine how to reconcile past runs with newer workflow versions (forking may not be allowed in some cases).
    - **TODO:** Investigate how langfuse stores graph architecture during trace capture.
2. **Breaking Changes:**
    - When node templates change, user workflows might break; a mechanism to notify users and enable rollback must be provided.
3. **Instance vs. Template Config:**
    - Typically, config changes only affect instances.
    - **TODO:** Decide how to handle cases where the template config is changed—should instance config be updated or remain frozen?

> Substantial Matter Changes (Section 4):
> 
> 
> Detailed strategies for node and workflow versioning, including a comprehensive list of change types and backward compatibility issues, have been added. These additions are significant and require manual review.
> 

---

# 5. Key Nodes and Prebuilt Workflows

This section describes core node types and prebuilt workflows that serve as building blocks for common tasks.

- **Trigger Nodes:**
    - May include internal triggers and predicate-based triggers.
- **Scheduling Nodes:**
    - Manage time-based or event-based initiation of workflows.
- **Wait Node:**
    - Pauses the workflow until a specified event or schedule triggers resumption.
    - **Use Case:**
        - For waits longer than a typical API call duration, a wait node can pend the workflow and then create a trigger/schedule to restart execution.
- **SEND Nodes:**
    - Implement map-reduce-like functionality as described in langgraph.
- **Routing Nodes:**
    - Include If/Else nodes and Command nodes.
        - **Command Nodes:**
            - Handle both updates and conditional routing (e.g., for multi-agent handoffs).
    - **Conditional Edges:**
        - Support routing logic based on dynamic conditions.
- **Playbooks:**
    - Allow developers to register new node playbooks that interact with the registry for streamlined adoption.

## 5.a. Memory Nodes

- **Purpose:**
    - Integrate user feedback to improve node outputs and retain “memories” (preferences, alignment data).
- **Enhancements:**
    - **TODO:** Research how reinforcement learning (RL) can be used to fine-tune nodes or LLMs for specific tasks (e.g., see Deepseek R1).
- **Persistence:**
    - Long-term memory may be persisted via langgraph stores (or other mechanisms) and passed along with graph state via the context manager.
    - **Note:** Memory is not tied to the thread ID.
- **User Visibility:**
    - **TODO:** Develop a UI mechanism to provide users with visibility into stored memories.
- **Reference:**
    - See [Agent/assistant Mode → infinite threads in a never ending workflow](https://www.notion.so/7-Agent-assistant-Mode-infinite-threads-in-a-never-ending-workflow-1b012cba067e80168128e66eb829ae97?pvs=21) for further context.

> Substantial Matter Changes (Section 5):
> 
> 
> This section now explicitly covers memory nodes—including RL and long-term persistence—and introduces playbooks. These additions are new and need manual review.
> 

---

# 6. Tools and Actions (Adhoc Query and Performing an Action, e.g., CRUD)

- **Nodes as Tools:**
    - Nodes may function as tools that perform actions (such as CRUD operations) and must return outputs in line with langgraph expectations.
- **Model Context Protocol (MCP):**
    - Evaluate whether to build an MCP server for integrations (for example, LinkedIn integrations).
- **Handy References:**
    - [Anthropic MCP Docs](https://modelcontextprotocol.io/introduction)
    - [How to integrate MCP in Cursor](https://docs.cursor.com/context/model-context-protocol)
    - [Composio’s List of MCP Servers](https://mcp.composio.dev/)

> Substantial Matter Changes (Section 6):
> 
> 
> Clarifications regarding nodes as tools and MCP integration have been added. These new details require manual review.
> 

---

# 7. Agent/Assistant Mode → Infinite Threads in a Never Ending Workflow

This section addresses the design for continuous, “agentful” workflows that operate indefinitely.

- **Concept:**
    - Inspired by ChatGPT and Anthropic threads, the system can support workflows that continuously process inputs and generate outputs.
- **Characteristics:**
    1. May run as a main assistant thread with additional auxiliary threads.
    2. Can invoke external tools and interpret user intent in an “agentful” manner.
- **Challenges:**
    - **Infinite Loops:**
        - **TODO:** Define strategies to prevent runaway agent loops while still allowing continuous operation.
    - **Storage Costs:**
        - Consider that repeated state snapshots might lead to high storage costs.
    - **Long-Term Memory:**
        - Persist generated artifacts, previous threads, and user preferences/alignments in a long-term memory store.
    - **User Visibility:**
        - The UI should expose past messages and allow users to see node-specific thread histories.
    - **Implementation Consideration:**
        - Likely to be implemented as cross-thread persistence.
        - Initially, one main assistant thread per workflow may be sufficient.

> Substantial Matter Changes (Section 7):
> 
> 
> This section introduces new considerations around continuous agent workflows, including loop prevention and long-term memory management. These points are new and need manual review.
> 

---

# 8. Admin

- **Administrative Operations:**
    1. CRUD operations for workflow templates and their graph configurations.
    2. Ability to deregister or blacklist nodes.
    3. Future functionality to add new nodes.
    4. Admins (and possibly developers) have enhanced access to the workflow builder UI.

> Substantial Matter Changes (Section 8):
> 
> 
> This section is mostly a reorganization of the original points with no major new technical elements; it requires only a brief manual review.
> 

---

# 9. User Flows → Application Development

- **User Onboarding and Interaction:**
    - Define user flows for adopting workflow templates, customizing configurations, and executing workflow instances.
- **Integration:**
    - Provide APIs and UI components for embedding workflow capabilities within larger applications.
- **Continuous Improvement:**
    - Leverage user analytics and feedback to iteratively improve workflows.

> Substantial Matter Changes (Section 9):
> 
> 
> This section has been reorganized for clarity with minimal new technical details. A brief review is recommended.
> 

---

# Appendix

1. **Other Cognitive Architectures:**
    - **TODO:** Investigate other multiagent systems built on top of langgraph/langchain (see [Langchain Blog on Prebuilt Agents](https://blog.langchain.dev/langgraph-0-3-release-prebuilt-agents/)).
2. **JSON Patch:**
    - Consider strategies using JSON patch for managing dynamic configuration changes.

> Substantial Matter Changes (Appendix):
> 
> 
> No new functional points have been added; this section is maintained as a list of references and TODOs for further research.
> 

---

# Conclusion

This design document now covers all original points with detailed explanations, explicit “TODO” markers for areas needing further decisions, and added context for error handling, versioning, and execution details. Several new operational strategies—particularly in registry management, state handling (including HITL and forking), and continuous agent workflows—have been introduced. Each section includes a “Substantial Matter Changes” note indicating the additions that require manual review.

Please review the sections marked for manual review to ensure that the additional details and new operational strategies align with overall system goals.
