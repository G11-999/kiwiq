

## Phase 2

- ingestion via ingestion script, searching / fetching ingested workflow and testing it
    - ingestion:
        - DON'T USE API DIRECTLY, USE STANDALONE CLIENT and methods
        - [WORKFLOW DELETE API / method] delete previous workflow with same name
        - [WORKFLOW CREATE API / method]
            - ingest in raunak superuser's org ID: name: KIWIQ (workflow owner org)
            - Ingest using workflow name / version exactly same as fetched from artifacts API
            - mark is_system_entity and is_public : both True
        - [Write SCRIPT using the standalone SDK methods]
            - write ingestion script to automate this process and remove errors
    - search via [workflows SEARCH API ]
        - via name and ensure later version is returned (check created at, check graph schema is fresh schema and not older schema)
    - testing:
        - [Run the workflow via RUN CLIENT using workflow ID and workflow inputs]
        - [query artifacts clients via SDK]:
            - Fetch workflow inputs using artifacts client method
            - ensure workflow inputs are aligned with the new graph schema inputs
        - try running the ingested workflow using SDK client to see outputs are expected via testing script (with setup / cleanup docs) on prod
        - check workflow logs (errors, warnings), workflow state via API (each node's output and central state) to ensure error free execution

## Phase 3

- Frontend Integration and testing:
    - Use artifacts API to fetch workflow name / version to search workflow and receive workflow inputs (use workflow key in the API)
    - Search and fetch workflow via fetched name / version
    - Workflow Inputs
        - For fetched inputs, if any field is None, add
    -


