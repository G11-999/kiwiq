########################################################################################################################################################

Pending Tasks:



- DB layer
- Auth, user/orgs, oauth; secure AUTH + CSRF!!! User roles --> assign same user roles in multiple orgs!
- workflow service / registry DB layer; potential migration conflicts?
- Worklfow Ops; how to pend / pause workflow and store in DB
- Admins, perms
- backend API; integrate auto API documentation
- notifications, websockets
- notifications of job completion, job triggered/started, job progress live events, tokens streaming, job failure, HITL notification / request!
- HITL jobs table
- user sends back HITL job done!
- Key nodes / workflows with application context / external service context!
    - Embeddings + RAG + Retrieval + hybrid retrieval + llamaindex
- prefect setup!
- linkedin integrations
- billing and payments??
- scraping integrations!!??
- Deployment! External services packages / deployment! hosted vs managed!
- security brainstorming: https://claude.ai/chat/b553f08f-fd40-490c-8504-5f98318ded7c

- Scheduling?
- Triggers?
    - web hooks

########################################################################################################################################################


# DB Layer

TODO: handle paginations for all DB clients - postgres, mongo!
TODO: mongo DB permissions handling -> handle permissions much more efficiently instead of O(N^2) complexity!

Key Entities:
1. User (unique_name / ID > 1 char, * not allowed in name/ID)
2. Organization (unique_name / ID > 1 char, * not allowed in name/ID)
3. user roles
    - org permissions
    - user account permissions (another user controlling someone else's account)
    - Roles:
        - admin: has all permissions
        - 
    - permissions: TODO:
        - full access
        - workflow builder
        - workflow executor + scheduler
        - workflow delete access
        - data access: read + delete
        - billing

Auth data
- API tokens and sessions!
- Oauth data, eg: linkedin

#############################################################################


NOTE: Node Instance, Workflow, prompt template, schema template -> they can be owned by orgs!

Workflow entities: ()
1. Node Template
    - (type: template) (no owner) launch_status/ENV: prod, etc (They never have owners, owned by KIWIQ!)
2. Workflow (They don't have templates since they are fully defined via configs!)
owner org + pointers to parent_templates -> parent workflow copied and each node config will point to a node template (via node name / version)

NOTE: the below can either be in Postgres or Mongo -- stored under customer / namespaces!
Registry manages the details!
3. Prompt Template
4. Schema Template -- Json schema or Construct dynamic schema config or stored in code and just registered!


Runs
- Run ID!
- Thread ID! -> reusable for other Runs, can be potentially same as Run ID!
- Run state / status (A unique Instance) -- scheduled, running, paused, cancelled, failed, waiting for I/O
- Run stream
- results!
- node execution order; events / streams / tokens
- each node execution order, potentially inputs?? (maybe later) or atleast outputs!
- the execution state is persisted and appears even when page is refreshed with fresh incoming notifications!
NOTE: can have diff collections / databases exclusive to KIWIQ, or Langgraph runs states!

Differentiate between what data will be stored in SQL vs Mongo! 
stream data, large results should be stored in Mongo; final results may also be stored in SQL




User Notifications Table (Show active/pending jobs separately on UI than notifications!)
- workflow results / run finished -> with link to results!
message: Dict
User Jobs (HITL) (is_pending)
response_schema: Dict
response: 
resume_ID: Run ID of Run!
created_at
responded_at


# Streams
[https://www.rabbitmq.com/tutorials/tutorial-two-python-stream](https://www.rabbitmq.com/tutorials/tutorial-two-python-stream)
[https://github.com/rabbitmq-community/rstreamtab=readme-ov-file#server-side-offset-tracking](https://github.com/rabbitmq-community/rstreamtab=readme-ov-file#server-side-offset-tracking)

## Faststream does support streaming, check support for extra streaming args: 
[https://github.com/ag2ai/faststream/blob/3857cc3469f496408746d31cfd75032c172ba56b/faststream/rabbit/schemas/queue.py#L237](https://github.com/ag2ai/faststream/blob/3857cc3469f496408746d31cfd75032c172ba56b/faststream/rabbit/schemas/queue.py#L237)



Then implenment the websockets endpoint in @routes.py  and implemnet the rabbitmq consumer; also implement a sample rabbitmq producer to test the consumer setup
@rabbitmq_practical_guide_lib_concepts.md 

@mongo_client_v2_secure.py 



ALso do the following:
Notifications handler -> listens to rabbitmq for push notifications and registered callback to handle it
Diff notifications: 
- workflow run status change
    - Failure events
- Outputs
- Immediate requests from user for HITL which block the workflow execution!

NOtifications object schema (some notifications needs to be immeidately stored to db and delivered to user vs other notifications to system / webapp from workflow manager/pool )

workflow stream events
- the kiwi_app has a dedicated consumer func listening to workflow events stream
(details provided below)
there is a specific events schema and event types

Also write a test to consumer from a stream using to check if the offset is picked up correctly -- to check if the consumer starts again from where it left off previously! track the consumer's offset correctly or rabbitmq / client / faststream does it automatically?

MongoDB collection for storing workflow stream data after consuming from stream as mentioned below

Websockets endpoint and connection management to notify the user immediately if user is connected if notification schema says user notification

Add appropriate constants / settings to configure behaviour / names of queues etc

Streams & Queues: (persistent queues)
https://faststream.airt.ai/0.5/rabbit/examples/direct/
https://faststream.airt.ai/latest/rabbit/publishing/
https://faststream.airt.ai/0.5/rabbit/examples/stream/?h=stream
https://faststream.airt.ai/latest/rabbit/security/
https://faststream.airt.ai/latest/api/faststream/rabbit/RabbitQueue/
https://www.rabbitmq.com/docs/queues#optional-arguments




```Stream design notes

Okay, let's address those two important concerns about using a single RabbitMQ Stream for `workflow_events`: managing size and ensuring correct consumption with offsets.

These are precisely the problems that RabbitMQ Streams (like Kafka) are designed to solve through built-in features.

**1. How to Keep Stream Size Limits and Ensure the Stream Doesn't Bloat?**

RabbitMQ Streams are *not* designed to store data indefinitely by default. You control their size using **Retention Policies**, which automatically discard older data based on configured limits. This prevents the stream from growing forever.

* **Key Retention Policies:**
    * **`max-age`**: Sets a time limit for how long messages are kept in the stream. Messages older than this duration are eligible for deletion. Examples: `7d` (7 days), `24h` (24 hours), `60m` (60 minutes).
    * **`max-length-bytes`**: Sets a hard limit on the total size of the stream data (sum of message bodies) stored on disk. When this limit is exceeded, RabbitMQ deletes the *oldest* data segment(s) to make space for new messages. Example: `10GB` (10 gigabytes), `10737418240` (bytes for 10GB).

* **How to Configure Retention:**
    * **Stream Declaration:** You typically set these when you first create the stream using tools like `rabbitmqctl` or the Management UI.
        ```bash
        # Example using rabbitmqctl to create a stream with 7-day retention OR 10GB size limit
        # (whichever is hit first usually triggers deletion)
        rabbitmqctl add_stream workflow_events \
          arguments='[{"max-age", "7d"}, {"max-length-bytes", 10737418240}]'

        # Or just time-based:
        rabbitmqctl add_stream workflow_events arguments='[{"max-age", "3d"}]'

        # Or just size-based:
        rabbitmqctl add_stream workflow_events arguments='[{"max-length-bytes", 21474836480}]' # 20GB
        ```
    * **RabbitMQ Policies (Recommended for flexibility):** You can define a RabbitMQ policy that applies to the stream name (or a pattern) and sets the retention definitions (`stream-max-age`, `stream-max-length`). This allows you to change limits without recreating the stream.

* **Choosing Limits:**
    * Consider how long you *need* the data *in RabbitMQ* for replayability or recovery of your consumer/MongoDB writer. Your primary long-term storage is MongoDB.
    * The stream retention should typically cover:
        * Maximum expected downtime of your consumer service.
        * A buffer period for debugging or potential reprocessing needs.
        * Disk space constraints on your RabbitMQ nodes.
    * A retention policy of a few days (e.g., `3d` or `7d`) combined with a reasonable size limit (e.g., 10-50GB, depending on message volume and disk) is often a good starting point.

* **FastStream Context:** Remember, FastStream's default `RabbitBroker` doesn't manage stream declarations or properties directly (as it uses AMQP 0.9.1). You need to configure these retention policies outside your FastStream application code using RabbitMQ's native tools or policies.

**2. How to Ensure Stream Gets Consumed from the Right Offsets if Only 1 Stream?**

This is handled by the core **offset tracking** mechanism of RabbitMQ Streams and the consumer client library. It ensures each consumer reads messages sequentially and reliably, even in a shared stream.

* **Offsets:** Every message in a RabbitMQ Stream has a unique, sequential 64-bit integer **offset**. This offset represents the message's position in the immutable log.
* **Consumer Responsibility:** It's the *consumer's* job (specifically, the Streams client library it uses) to keep track of the offset of the last message it successfully processed.
* **Connecting/Subscribing:** When your consumer service connects to the stream, it tells the broker where to start reading from:
    * `first`: Start from the very beginning (offset 0). Useful for reprocessing or initial setup.
    * `last` / `next`: Start consuming only *new* messages arriving after the consumer connects.
    * `offset`: Resume from a specific, previously saved numerical offset. **This is key for reliable processing.**
    * `timestamp`: Start from the first message at or after a specific time.
* **Storing/Committing Offsets (Crucial Step):**
    * As your consumer successfully processes messages (e.g., after writing them to MongoDB), it needs to tell the broker the offset of the last processed message. This is often called "committing" or "storing" the offset.
    * **Broker-Side Offset Storage (Highly Recommended):** RabbitMQ Streams allows consumers to store their offsets directly on the broker, associated with a unique consumer name or subscription ID (e.g., `my-fastapi-consumer-1`).
        * The Streams client library provides functions for this (e.g., `client.store_offset(processed_offset)`).
        * When the consumer restarts, it reconnects using the *same consumer name*. The broker then automatically tells it the last stored offset, ensuring it resumes exactly where it left off.
        * You typically store offsets periodically (e.g., every N messages or every T seconds) or after each successfully processed batch to balance performance and recovery granularity.
    * **External Offset Storage (Less Common):** The consumer could store its offset in an external database (Postgres/Mongo). This requires more complex application logic to manage correctly, especially during consumer failures or scaling. Broker-side storage is generally preferred.
* **How it Works with 1 Stream, Multiple Runs:**
    * The consumer connects and subscribes, starting from its last known offset (provided by the broker if using broker-side storage).
    * It reads messages *sequentially* from the stream based on the offset, regardless of which `run_id` is inside the message payload.
    * *After* receiving a message, your consumer's application logic inspects the payload (e.g., `message['run_id']`, `message['event_type']`).
    * Based on this payload data, the consumer decides how to process it (e.g., write to the correct document in MongoDB, push to a specific WebSocket).
    * The offset tracking ensures that the consumer reads *every message* in order from its perspective within the stream. The application logic handles the *demultiplexing* based on the message content (`run_id`). No messages are missed due to other runs being present in the stream.

**In summary:**

* **Control size** using `max-age` and/or `max-length-bytes` retention policies configured directly on the RabbitMQ Stream (outside FastStream).
* **Ensure correct consumption** using the built-in offset mechanism of RabbitMQ Streams. Use a dedicated Streams client library in your consumer, leverage **broker-side offset storage** for reliability, and commit offsets after successful processing. Your application logic filters messages based on `run_id` *after* they are consumed sequentially based on the offset.
###################


Okay, let's break down this architecture for streaming workflow events and results using FastAPI, Prefect, and RabbitMQ.

**Overall Goal Recap:**

* Trigger/manage Prefect workflows via FastAPI.
* Prefect workers execute tasks.
* Workers need to communicate back to the main app (FastAPI backend):
    * Token-by-token streams (e.g., LLM output).
    * Intermediate results/outputs.
    * Final results.
    * Workflow state changes (running, completed, failed, etc.).
* Persist streaming/intermediate data (MongoDB).
* Persist final structured results (PostgreSQL).

**Review of Proposed Design Components:**

1.  **FastAPI:** Good choice for the API layer. It can handle triggering workflows and potentially serving real-time updates via WebSockets.
2.  **Prefect:** Excellent for workflow orchestration and management. Handles task execution, retries, dependencies, and state tracking internally.
3.  **RabbitMQ:** Suitable as the message bus for decoupling Prefect workers from the FastAPI application. The key question is *how* to use it effectively.
4.  **MongoDB:** Good fit for storing large volumes of potentially semi-structured streaming data (tokens, intermediate events) associated with a workflow run. Its flexibility is an advantage here.
5.  **PostgreSQL:** Ideal for storing the final, structured results of the workflow, leveraging relational integrity and transactional guarantees.

**Deep Dive: RabbitMQ Communication Strategy (Prefect -> FastAPI)**

This is the most critical part of your question. Let's compare the options:

**Option 1: RabbitMQ Queues with Fixed TTL**

* **How it works:** Each event (token, state change, output) is a message sent to a queue, maybe specific to the workflow run (`run_id_queue`) or a general queue with `run_id` in the message body. TTL automatically discards messages if not consumed.
* **Pros:**
    * Uses standard AMQP 0.9.1, well-supported by `aio-pika` and potentially easier integration with standard libraries/frameworks (like FastStream's default `RabbitBroker`).
    * Simpler broker concept than Streams.
* **Cons:**
    * **Not Persistent/Replayable:** If the FastAPI consumer is down or slow, messages can expire due to TTL (leading to data loss) or back up significantly if no TTL (consuming broker resources). Cannot easily replay the event stream for a run later.
    * **Not Ideal for Streaming:** Sending every single token as a separate AMQP message can have high overhead (framing, routing).
    * **Ordering:** While queues are FIFO, ensuring strict end-to-end ordering across potentially distributed consumers/publishers and broker hops requires careful design.
    * **Data Loss Risk:** TTL is problematic if guaranteed delivery to your persistence layer (Mongo) is required.

**Option 2: RabbitMQ Streams**

* **How it works:** A persistent, append-only log on the broker. Publishers write messages, consumers track their position (offset) and read sequentially. Supports retention policies (time/size).
* **Pros:**
    * **Persistent & Replayable:** Data stays in the stream (subject to retention). Consumers can join anytime and read from a specific offset (or the beginning). Ideal if you need to potentially re-process events or recover the MongoDB log.
    * **Designed for Streaming:** Handles high throughput and ordered sequences efficiently. Better suited for token-by-token style events.
    * **Decoupling:** Consumers read at their own pace without affecting publishers or other consumers.
* **Cons:**
    * **Different Protocol:** Requires a specific RabbitMQ Streams client library (check `stream-py` or others, ensure compatibility/maintenance) or using protocol adapters (like AMQP 1.0/MQTT if configured, adding complexity). Standard `aio-pika` (used by FastStream's `RabbitBroker`) doesn't speak the native stream protocol.
    * **Broker Setup:** Might require enabling the plugin and potentially more configuration than standard queues.

**Option 3: Stream-per-Workflow Run (Using RabbitMQ Streams)**

* **How it works:** Dynamically create a unique RabbitMQ Stream (e.g., `run_123_stream`) for each workflow run. Publish all events for that run to its dedicated stream. Delete the stream after completion and consumption.
* **Pros:**
    * Excellent data isolation per run.
    * Simplifies consumption logic (just read the one stream).
    * Cleanup is explicit (delete the stream).
* **Cons:**
    * **High Overhead:** Creating and deleting streams frequently can be resource-intensive on the RabbitMQ broker and is generally not recommended for very high-frequency, short-lived runs.
    * **Management Complexity:** Requires robust logic for stream creation, deletion, and ensuring the consumer knows which stream to attach to. Error handling during deletion needs care.

**Recommendation for RabbitMQ:**

**Use RabbitMQ Streams, but *not* one stream per workflow run.**

1.  **Create one (or a few logical) persistent RabbitMQ Stream(s):** e.g., `workflow_events`.
2.  **Structure Messages:** Every message published by a Prefect worker to this stream *must* contain:
    * `run_id`: (Crucial!) To identify which workflow run the event belongs to.
    * `event_type`: e.g., `TOKEN`, `STATE_CHANGE`, `INTERMEDIATE_OUTPUT`, `FINAL_OUTPUT`, `LOG`.
    * `payload`: The actual data (the token string, state info dictionary, output data).
    * `timestamp`: ISO format timestamp.
    * (Optional) `task_id`: Which task generated the event.
    * (Optional) `sequence`: A sequence number within the run/task for strict ordering if needed beyond the stream offset.
3.  **Prefect Worker Publishing:** The worker task needs to use a RabbitMQ Streams client library to publish these structured messages to the `workflow_events` stream.
4.  **FastAPI Consumer Logic:** A dedicated consumer service (can be part of the FastAPI app or a separate process) reads from the `workflow_events` stream. It then filters/fans-out messages based on `run_id` and `event_type` for further processing (writing to DB, pushing via WebSockets).

**Why this approach?**

* Leverages the persistence, replayability, and streaming efficiency of RabbitMQ Streams.
* Avoids the high overhead of creating/deleting streams per run.
* Keeps the RabbitMQ setup simpler (fewer streams to manage).
* Relies on filtering logic in the consumer, which is a standard pattern.

**Proposed Architecture Flow:**

1.  **Request:** User interacts with FastAPI endpoint.
2.  **Trigger:** FastAPI endpoint validates request, uses Prefect client library (`prefect.client.orchestration`) to submit a flow run (e.g., `create_flow_run_from_deployment`), and gets the `flow_run_id`. FastAPI might store this `run_id` associated with the user session/request.
3.  **Execution:** Prefect schedules the flow run. A Prefect worker/agent picks it up.
4.  **Event Publishing (Worker):**
    * Inside Prefect tasks (`@task`), use a RabbitMQ Streams client.
    * When generating tokens, intermediate results, or completing, publish messages to the `workflow_events` stream, including the `flow_run_id`, `event_type`, and `payload`.
    * Prefect automatically tracks state changes; you might need separate logic (or Prefect hooks/automations if available and suitable) to also publish `STATE_CHANGE` events to the stream if needed beyond Prefect's own UI/API tracking.
5.  **Event Consumption (FastAPI Backend / Separate Service):**
    * A continuously running consumer service uses a RabbitMQ Streams client to subscribe to `workflow_events` stream, tracking its offset.
    * For each message received:
        * Parse the message (get `run_id`, `event_type`, `payload`).
        * **Filtering/Routing:**
            * If `event_type` is `TOKEN` or `INTERMEDIATE_OUTPUT`: Write the `payload` to MongoDB, linked to the `run_id`.
            * If `event_type` is `STATE_CHANGE`: Update internal state tracking if necessary, potentially log to Mongo.
            * If `event_type` is `FINAL_OUTPUT`: Write the structured `payload` to PostgreSQL, linked to the `run_id`. Mark the run as complete in Mongo/other state tracking.
            * **WebSocket Push (Optional):** Check if any active WebSocket connection is subscribed to this `run_id`. If yes, forward the relevant event/token/state to that client.
6.  **Persistence:**
    * **MongoDB:** Stores the time-series log of tokens, intermediate outputs, and potentially state changes for each `run_id`. Allows reconstructing the "stream" of events later.
    * **PostgreSQL:** Stores the final, validated, structured result associated with the `run_id`.

**WebSockets for Real-time UI:**

* When a client connects via WebSocket (e.g., from the FastAPI frontend after triggering a run), FastAPI should maintain a mapping (e.g., `Dict[str, List[WebSocket]]`) of `run_id` to active WebSocket connections interested in that run.
* The RabbitMQ consumer, after processing a message, checks this mapping for the message's `run_id` and pushes data to the relevant sockets.

**Considerations & Trade-offs:**

* **Streams Client:** You need to select and integrate a suitable Python RabbitMQ Streams client library in both the Prefect worker environment and the FastAPI consumer. This adds a dependency distinct from standard `aio-pika`.
* **Consumer Robustness:** The consumer service reading from RabbitMQ Streams and writing to databases is critical. It needs proper error handling, retry logic (for database writes), offset management, and potentially scaling.
* **Idempotency:** Ensure database writes are idempotent if the consumer might re-process messages after a failure/restart.
* **Prefect Integration:** How easily can you inject the RabbitMQ Streams publishing logic into your Prefect tasks? Consider using context managers or shared utility functions within your tasks.
* **Backpressure:** Monitor MongoDB and PostgreSQL write performance. If they become bottlenecks, the RabbitMQ consumer might fall behind, but the data remains safe in the Stream (up to retention limits).

This architecture leverages the strengths of each component while using RabbitMQ Streams for its intended purpose – handling persistent, ordered event streams effectively. It avoids the pitfalls of using standard queues for this specific streaming/persistence requirement and the overhead of managing streams per run.



```


######


Application Workflows + States
- These are workflows owned by Admin / KiwiQ which are run for diff users; 
    - Same instances run for diff users in diff runs
    - can access kiwiq namespace for our docs / prompts etc!
- orchestration between core workflow journeys
- User State



Data
- Data scopes: shared with org, private to user, public data! 
    {org/shared; org/user_id; shared/ file paths!} May include KiwiQ default data for customers in path too here!
    BTW kiwiq data (like eg content ideas!) won't be public, but it will be owned by default KIWIQ org and shared across org and leverages by users belonging to this system org!
NOTE: can have diff collections / databases exclusive to KIWIQ, or Langgraph runs states!

- User State + journey orchestration; user flow!
- User Data
- workflow data; responses, etc

Entities


PLans + Subscriptions
    - Tiers + Rate Limits + usage limits
Billing + Payments
Usage


# [IN FUTURE] Workflow Builder Workspaces



# EDIT / UNDO: TODO!


###### DEPRECATED 
####### Instances (Owned by users / orgs AND RUNNABLE!)
####### - Node Instance: (type: instance) config copy + owner org + parent_template: (basically all the config part of the workflow belonging to a specific Node!)
####### - Workflow (same as above!) They have a parent pointer + owner --> will be fully configured





