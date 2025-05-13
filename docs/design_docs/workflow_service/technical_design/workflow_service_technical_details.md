# NEW DESIGNS / BRAINSTORMING

#### Edges
There may be multiple edges passing data to multiple nodes from same output node / field!

#### Non-data flow edges
NOTE: edges can be non-data flow dependency ALSO -> eg: case of IF/ELSE nodes -> the have conditional edges going out but no data out
Fan in edges could be in one of their target nodes -> from previous node (data flow edge) and IF/ELSE nodes both!
Conditional edges will mostly be non-data flow edges!
NOTE: IF / ELSE nodes may have dynamic schema if too difficult for user to understand multi edge fan-in?? PROBABLY NOT to start with!


#### Dynamic Graph state
Graph State {
    "node_name": node_output_schema,
    ...
}
loop, hitl and multiple each node outputs??
replace, append or do some other reduction?

TODO: goal of this exercise is determining who has info / responsbility to construct the graph schema or edges contract, who assigns schema for hitl nodes
who understands info about types of reducers required in graph state??

Channels analogy from Langgraph -> which nodes / actors talk via the same channels or send updates there??
    Is loop detected to same node to setup reducers??
Can graph state be such that multiple nodes are talking via the same channel and appropriate reducers are used??

#### **Central Graph channels configuration**
Graph state / airtable sink node:
1. sync data to central graph store / table! specify properties of tables what it does to overwriting writes!
2. the same sink node can have incoming and outgoing edge specifying order of execution! can be multiple sink nodes in graph dictating execution order!
3. the sink node is just one way of visualizing central channels!
4. Can direclty be configured on output of node -> sink to graph and add to table and specify reducer (eg: add to list!)
5.    in above 4. case: edge can be direct between sink producer and ocnsumer (edge from node A to node B where node A adds to sink, then node B executes, reads entire same sink as node A! )
6. THEREFORE -> if output is configured to sink into central table sink and edge exists from that output key to next node's input; it will be able to read the entire sink's value including previous writes!
7. may have separate edge going from output key to input key directly without sink (jsut receive previous node's output)
8. this can either be configured at the node output level or the edge level!


This is a compile time config, not runtime -> it chnages the graph arcitecture -> changes graph state, and whether previous state can be reloaded in same graph or not!
It has to be part of the node config!
This should be detected as part of the config change!



##### NOTE: additional runtime config -> rename output schema; central graph state practically from the node's perspe ctive just menas to rename its output schema fields from node_name__<field_name> to <field_name>!
    There could be additional config during runtime -> telling node to output in different named channels! Graph central state could be separately named for eg!
An outbound edge from a node output field would by definition -> compel a node to output in the default private channel consumed by the node at the other end of the edge!
Unless the edge was coming from the graph central state itself! Then we don't need to think about it!
exception: the grpah central state must be filled by atleast one other node if its a required input to a node! TODO: think more!

check outgoing edges, have node output in default private chnanel if outgoing edge exists!
output in graph central channel if edge exists 

Graph central state could just be storage node! same inputs and outputs schema (single item vs list could be diff based on reducers!)!



##### CHECK ABOVE FOR ANSWER!
- Set of valid or invalid edges (can be non-exhaustive, by default edges with same data types are valid??)
- output fields annotated with same reducers or append?? messages i.e.e
- output fields annotated with diff reducers
- input fields -> how do they choose which channel to take? incoming edge node outputs in messages (or other field with non-replcaement reducer??) or graph wide channel 
- graph wide default config?? -> output channels with same reducers / append reducers create a graph central channel apart from node specific channel
---- can enable / disable central shared X-node channel
################################################################################################################################################################

#### **DynamicSchemaNode: New type of Node? NOPE!**
DynamicSchemaNode TODO: (schema changes for each instance!)
How will node lifecycle, schema validations be managed??

IT doesnt need validation! since schema same as other nodes!! just needs keys
its schema will be keys form input / output node whose fields to copy or CREATE / ADD to!

HITL node just needs keys of output schema of prev nodes and keys of input schema of next node to build its schema and get / populate data in right channels!
Its schema just needs to be lists of these keys!
The config of the HITL node determines its input and output schema dynamically!


#### patterns for HITL: 

1. before node init -> Caller node is diff than Receiver node

    a. new node only runs after hitl node and receives input from hitl before execution
| prev_node --edge--> new node (optional)
| prev_node --edge--> hitl node --edge--> new node

**Key Division of responsibilities**
- HITL node output is optional / required input in new node
- HITL node input is (optional) output from prev_node
Therefore -> edges between output and inputs will dictate the HITL schema!

2. after node init / first call -> Caller node is same as Receiver node (with additional IF/ELSE conditional step)

    a. new node in loop with hitl (new node starts from scratch each time receives hitl!)
| (has to be via IF ELSE --> it will trigger when loop with hitl node ends!)
| node --edge--> IF/ELSEE --conditional edge--> (HITL node) | (NEXT node)
| hitl node --edge--> node

**Key Division of responsibilities**
- HITL node output is optional input in Caller Node
- HITL node input is (optional) output from Caller Node --> note how will validation take place? If else must receive status of HITL message!!
- TODO: how will output optionality be handled?? Maybe all fields in output will be marked optional??


NOTE: hitl node is responsible for looping with user and following up in case of invalid data!

##### Plan for following types of HITL: 
Review comments, approve tool use, yes or no?
get settings (eg: model type)
input text! search query

how will a complex multi step loop work?
-> user provides task / query to agentic assistant
-> agent udnerstands user intent and confirms plan with user
-> user provides subjective feedback
-> agent executes detailed planning
-> plan is executed. Optionally, user is asked for confirmation for tool calls.
-> another LLM node parses tool outputs and diff execution component outputs to process the task and get final response / whether user's intent was achieved
-> the loops closes back to agentic assistant starting node -> either the loop successfully closed and user task was accomplished or its waiting in same thread for user's next task / follow-up

-> key point -> messages and continous states which are appended ==> are they appended to same message state or diff states eg: tool namespace, helper bot;
observations, etc??

Dyanamic Configuration for the graph
https://langchain-ai.github.io/langgraph/how-tos/configuration/



### Schemas

#### Phase I:



Registry / Node discovery!

#############################  TODO  ###############################

RunConfig
- enabled / disabled
- overwritten inputs! -> start from intermediate nodes!
NOTE: can just generate new graph and execute it and overlay inputs / outputs on builder viewer!


Builder workspace / canvas! (nodes may have coordinates?? visual aspects)
   - unconnected nodes in disabled state! not connected to central graph!

##### TODO: recursive node -> subgraph!
input node =-> input schema! 
output node ==> output schema!
config ==> nested config for all inside nodes!
These will be `_xyz` post computed / cached properties after graph structure is fixed! For every graph structure change, these all may change and need to be recomputed!
have a special object type specifier in graph config -> detect type graph and build graph recursively / fetch it!




############################################################

NodeConfig(BaseModel)
    - node name and version
    - NodeSchema!
    - [DEPRECATED] has additional optional output annotations to set it central graph states!
    - [DEPRECATED] NOTE: annotaitons directly in ndoes by default to set certain output fields as centraly shared states with reducers! changeable on instance level by Node COnfig! Default reducer ??!


EdgeSchema
    - src node
    - dst node

GraphSchema / GraphConfig
    - list of nodeconfigs
    - list of edgeconfigs
- custom validations (eg: all edges must reference nodes in list, all nodes are conected, graph validations etc!)
    - input is root and output is leaf
    - no dangling nodes!
    - all required inputs are fulfilled!
- build a graph
- Central state reducer config!
    - NOTE: this is just a special node for now!!


RuntimeConfig
    - {"inputs": node_name: {<input_field_key> : graph_state_key_source_of_input}}


Graph Runtime
Langgraph adapter
Adapter: 
    - compile graph
    - Run graph


TODO: Runtime Config!
- TODO: maybe just reuse edge config??

Runtime Context Manager

Execution Layer / manager! -> persistence, threads, langgraph etc!

Default graphs in code!




##### PHASE I - Part II:
########




@base.py @base.py @dynamic_nodes.py @graph.py 
Implemnet the graph builder (with building time validations), Graph Run config (how a graph is supposed to run, eg: enable checkpointing, etc), runtime config (edges mapping, passed to each node during runtime execution), graph runtime adapter base (should wrap diff runtime frameworks apis underneath our adapter api) and langgraph runtime adapter to run the graph (with checkpoints setting)

Also handle edges from / to from central graph state

building time validations include:
1. indiviudal node config validations during node init
2. all edges should reference fields in input / output schema which exist (access fields of baseschema class via __fields__ directly from class)
3. all edges to / from central graph state referencing same field should be of same type!
4. all node input fields have atmost 1 incoming edge and ensure all required input fields have atleast 1 incoming edge
5. check for more??

Also construct dynamic graph state containing all node's outputs and central graph state output.




graphschema
    - validations?? maybe merge with build graph validations!

GraphInstance

build graph:
    - validations
    - instantiate nodes
    - build runtime config
    - build graph central state!
    - build graph instance
    
# Runtime context manager --> build and add to config!
- user context
- DB connections?? APIs?? 
- long term memory, etc!

# runtime adapter!
- build and compile runtime adapter graph using Graph instance!

# NOTE: need thread ID and run ID or user context!
- execute graph in diff modes, checkpointer etc!
- generate output!


runtime adapter -> graph ops, fetch past runs, etc!



########





#### Phase II:

- HITL node
- Build nodes and eg / milestone workflows! Run and test! 
- Graph Ops! reload checkpoint, send updates etc!


#### Phase III:

- DB models!
- prod registry, potentially service or atleast migration / rollout pathway!

states for new NodeTemplate(s) in DB -> staging! only DB update, code not released yet! Once code released, registry will update it to prod / staging based on env config!

#### Phase IV:

- Core nodes such as trigger, etc

- worker pools
- background jobs, health, tracking, scaling!
- user namespace 
- billing etc integrations?
- notifcations



Router Node
    - config -> list of nodes it can redirect too? based on out edges (set during graph build time!)
        redirection config / conditions?
    - out edges -> dont set in langgraph??
    - set annotations for graph viz!!?? https://langchain-ai.github.io/langgraph/concepts/low_level/#send
    - output format (state + nodes redirected to) and compatiblity with adapter??
IF Else:
    - condition output too?
Nested Sub Graphs??!!



##### # TODO: NOTE: how will loops be constructed! test loops!
    #     Loop: Node --> HITL --> IF/ELSE + ROUTING --> conditional loop back to Node!
    #     Node -> dumps output to global state to retrieve previously processed outputs in each loop iteration!

TODO:
1. [DONE!] A union type primitive which is union of all primitive types (so can add any value to dict for eg);
while it being serializable; can have true JSONs in config!
2. configurable schema via JSON config -> specify fields in schema -> input / output / config etc
3. potentially mark which schemas are dynamic -> input / output or both?
4. IF - ELSE implementation -> specify Inputs schema via JSON! maybe additional field in NodeConfig?
    provide config -> field name, comparison value and operation (comparison) either between 2 fields or field and value
    value can be of any type -- atleast primitive! UNION
5. edges same dtype validation -> TODO: better way or disable it or user override in graph config if Enum (str) needs to be fed into str type!
    TODO: implement better type validation and compatible edges!

Potentially detect class fields as DynamicSchema and check provided config to build dynamic schema -> specify fields
if not specified, use edges to build schema; otherwise use fields from config to build the schema dynamically!
This potentially enables edges in between dynamic types. --> the dynamic node building logic would have to completely change


#### Phase V:
Core:
- Workflow service runtime management, context layer / manager, user and run states
- Streaming and graph Ops!

Other:
- Workflow builder interface (backend / froNTED)
- CORE guided USER FLOWS building + optimization
- DB layer, potentially check issues with JSON and use No-SQL too
- Tracing? Maybe later! Workflow debugging flows, logging etc!
- API -> workflow builder and workflow service API
- Integration with Tertiary services like billing, auth, notifications, HITL, queues, Redis
--> pause / interupted graph shelfing and resuming over long periods of time
- Worker pool and management; prefect
- speciality node types: trigger, wait, queue, etc
- graph ops with queue -> eg Resume

TODO: properly handle fan in / fan out and multiple incoming edges to same field / parallel branches
TODO: potentially implement a reduce node to aggregate inputs / results from multiple nodes in list!


TODO: FIXME:
NOTE: FAN IN and FAN OUT SUPER TRICKY especially with loops!
how to differentiate between fan in vs looping??
-> don't draw manual edges between router and the loop start in langgraph!
https://langchain-ai.github.io/langgraph/how-tos/command/#basic-usage

FOR EVERY EDGE incoming to a node; always do FAN IN??? 
TODO: check more about FAN IN!!
https://langchain-ai.github.io/langgraph/how-tos/branching/#parallel-node-fan-out-and-fan-in-with-extra-steps


#### NOTE: FOR interrupt and resume; same node may output into the previous outputted field!!!
TODO: FIXME: check!


#### TODO: add data only edge!
#### Happens via Central state!!!!

#### TODO: test node with partially defined dynamic schemas, input is not dynamic - explicity class, but output is dynamic!


#### TODO: FIXME: central state / dynamic schema most permissible types inferred from edges
while building central state or dynamic schemas; the inferred types should be highest permissible ones or all types should be same! Otherwise, the edges from lower permissible types may risk invalidating other edges!
SHOULD BE SUPERSETS!
#### TODO: visualize inferred node types on frontend!
TODO: use auto inferred type converters to convert into compatible / superset types using potentially type converting nodes!


#### Fan in temp fixes:
1. Use central state for data in only edges!
2. Check node while building inputs -> check if all required inputs have been filled, and if not, check if any parent node execution pending, i.e. which sends inputs to this node in required fields!
3. if parent pending and required fields not fulfilled, don't throw exception; wait until next call!
4. Create special FAn-innodes which aggregate inputs from multiple nodes!

Long term:
1. Do Graph DFS and mark all paths to same node without router node as Fan in automatically!!!


# TODO: debug central state building code; the node doesn't exist, need to check mapping keys!

#### DEBUG: when node receives input from both another node and central state!
Central state edge must recieve precedence since this will be latest input

## TODO: FIXME: Multiple edges to same input field, including from central state in loops / fan in!
NOTE: for any workflow with loops or input to same field from multiple nodes / loops + central state -> 
automatically convert all outputs to communicate via central state if its not specified with no reducer specified (replace only)!

## TODO: potentially do DFS and find execution order in pregel or langgraph??!! and sort edges in that order!



# TODO: prepare template doc for Product to provide Nodes / workflows / prompt templates!
Template for a Node and Workflows!

Also tips on prompt management and providing prompt templates!


#### TODO: allow specifying atleast a few of central state schema fields via config


Input Node

AI Node
  - input
    - user_prompt
    - message history [Optional]
  - output
    - AI response (to review node and central state)
  - edges
    - input to user_prompt
    - from router node (no data passed)
    - Central state to inputs (user_prompt and message history)

HITL Review Node
  - input
    - AI response (from AI node)
    - message history (from central state)
  - output
    - user prompt
    - approved status
  - edges
    - Router Node

Router Node
  - input
    - approved status
  - output
    - output choice?? --> try field inheritance on dynamic schema!
    - route to AI node or output!
  - edges
    - AI Node and Output Node


Output Node
    - incoming edges from Central State and Router Node




#### TODO: test field inheritance of set dynamic schemas subclasses -> it defines 1 field but rest defined via edges for eg!




#### TODO: FIXME: requried and default values / behaviour copied to dynamic schema -> think through and fix or TEST!
especially default values in central fields seem senseless!



#### TODO: FIXME: Potential Langgraph bug: forbid doesn't work since input schema receives extra field meant for central state init!
    model_config = ConfigDict(extra='ignore')  # Don't allow additional arguments during model init!


# TODO: test node return empty dict as output when required fields not met!

#### NOTE: CRITICAL: unnecessarily marking a schema as dynamic can have uninteded consequences!
##### DynamicSchema generation inherits from original dynamic schema so it has new dynamic fields as well as all fields defined in original base dynamic schema!


#### Multiple incoming edges bug!
Best to block multiple incoming edges on frontend -> use central state for data passing from multiple edges, use edges as part of a loop or explicitly handled FAN IN!



New Fixes TODO:
1. [X] Config to explicity turn on fan-in for a node
2. At graph build time -> assert all required inputs are fulfilled by either central state or the incoming edge data! since every edge will trigger node!
##### NOTE: Skipping this check since its tricky because of loops, currently user will ensure this is the case!

3. [X] have a default central state field -> node_execution order where each outputs its ID
that can be used to sort and fetch the last executed node for fulfilling inputs -> this helps in using fresh inputs instead of stale inputs in case when a node is executed multiple times as part of a loop or unhandled FAN IN!

### TODO: SEND: https://langchain-ai.github.io/langgraph/concepts/low_level/#send
### MAP REDUCE; operate on List
SEND: it will slightly change the input building since input is passed directly to the next node!

### TODO: FIXME overlapping incoming edges from node and central states both!
what if node field has incoming edge from central field as well as a node??
node vs node -> pick latest in execution order
Central state must overwrite if it exists!

`Central state > node > node (behind in execution order) > input fields don't exist`

## TODO: test complex workflow with 2 loops and 2 nodes feeding to same input fields -> ensure only fresh output is picked up!


#### TODO: FIXME
- Either change HITL node structure and add hooks like process_user_prompt, interrupt, process_user_input etc or leave this!
- pre-pre processor, lol!
- potentially override run method!
- Is is kinda natural for devs to define all this HITL logic right in the node rather than completely relying on dynamic edges!


#### TODO: node debug / verbose modes via runtime configs

TODO: remove psycopg2 and other dependencies like: 
fastapi-users = { extras = ["sqlalchemy"], version = "^14.0.1" }
fastapi-users-db-sqlalchemy = ">=7.0.0"


# LLM Router, etc!

LLM:
    1. Prompt templates (for system / user messages etc)
    2. Tools -> they are just instances of nodes? LLM node calls tools via routing?
        Tools can be configured by human pre-execution and input is LLM tool call output!
    3. Structured outputs or normal text
    4. follow up conversations - multi turn!
    5. Central state support!

1. Langchain interesting configs: 
    rate limiter object

2. Reasoning_effort
https://python.langchain.com/api_reference/openai/chat_models/langchain_openai.chat_models.base.ChatOpenAI.html





Retrieval and Ranking
- Memory and Search
- File Storage
- S3
Open AI / Cohere API supports retrieval, ranking, search, etc!
Maybe just use that!

# TODO: AI Editor Design
AI Editor
Deep Researcher Report on AI Editor
https://chatgpt.com/c/67e689aa-49f4-8006-ad54-2bbea38c554f



# Temp task stack
1. Annotate mock library everywhere its used so easier to refactor later!
2. Create base library empty class and mock library subclasses from it
3. Testing
4. add token counting and billing!
-- with message history
-- with thinking type messages, especially from AWS, Anthropic, Fireworks!
-- from each provider with diff config types! structured or str, reasoning!
-- diff reasoning configs!
-- with tools!
-- dynamic schemas

5. Stream in between stopped! Are the intermediate messages saved and can we continue generating from that state!!
6. # TODO: verify structured outputs in AWS Deepseek!
7. Fireworks -> check reasoning tokens parsed properly and new message created! Especially in structured output mode!


TODO: log exception tracebacks!

TODO: test LLM NOde / search with message history! + THINKING BLOCKS!



# Pending tasks

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



########################################################################

Create a separate permissions table and create a constnats.py and auth_setup.py file which sets up the DB with default permissions, roles, a default KiwiQ AI org and a defaul user admin which is superuser and also has admin role for KiwiQ AI.

LIst and plan 3 roles: admin (admin for the org, full acess, can add/remove users with roles + delete org / delete data + other perms), team member: can build, execute workflows and use platform normally without org admin access, and billing: has access to account billing and usage dashboards.

Create oauth 2.0 scopes for roles.
@https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#check-it 

Make the primary keys UUIDs.

Don't create BaseModels eg UserBase unless multiple models inherit from it; directly create the core models.

Use database async sessions/engine from created pool @session.py 

Use pyjwt instead of jose 
@https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#handle-jwt-tokens 

Create class based DAO classes for diff entities; for complex multi entity queries, create DAO classes with specified verbs which either access DAO or perform complex queries with joins.
Don't just write functions; create classes which makes code reusable nad more generic and classes can share db session pool and properly handle commit / close etc

Do not write DB queries directly in routers.py

Create additional services.py to create core services interacting with the DAO layer (multiple DAO objects) and performing key business logic; don't make routers.py bulky.

You have created LInkedinusermodel  in linkedin.py; instead move it to schemas.py

Ensure that the routes have the correct permissions (eg, while adding users to org with role, user must be admin or superuser) setup.

Also add ability for user to create new orgs and assign the user as the admin of new org by default

The user is also able to remove users from an org (remove their role) if the user is admin / superuser

So a user can be part of multiple orgs with diff roles.

Create a default org whenever a user is created for the first time and make the user admin for it.
