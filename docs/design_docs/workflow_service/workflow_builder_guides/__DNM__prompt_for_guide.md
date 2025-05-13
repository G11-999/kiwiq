
# Workflows

## Add node to workflow (best to iteratively add nodes to a workflow ensuring valid flow??)

add Linkedin scraping node which fetches a user profile given their username fetched from the input field and passes to initial prompt constructor to generate a personalized linkedin post referencing the linkedin profile of the user ; modify prompts and how prompt is consturcted and create appropriate edges input -> scraping node -> prompt constructor; toggle fan in in prompt constructor by setting enable_node_fan_in=True in node_config (not nested node_config)
Also store the fetched user profile to central state
@post_creation_workflow.py 
@linkedin_scraping_node_guide.md 
@job_config_schema.py 


## Populate workflow template where graph structure / edges don't change

### NOTE: IMPORTANT: ONE SHOT SUCCESSFULL! IF GIVEN STRUCTURE, LLM is great to do menial, non reasoning tasks and rewrite vars while keeping structure same!
```
Modify the constants / variables (keep system docs as is, same are required to be loaded) and testing code of the workflow (the workflow itself, graph structure, edges - doesn't require any changes)

to make it work with roughly the new requirements mentioned:



## the files to be loaded are 4 : 
1& 2: user scraped profile and user analyzed linkedin content, the
3 user preferences
4. content pillars doc for user


filename pattern for linkedin profile: {
                "static_namespace": LINKEDIN_SCRAPING_NAMESPACE,
                # Use entity_name (from node input, mapped from $graph_state) for the pattern context
                "input_docname_field": "entity_username", # Field in node's input containing the value
                "input_docname_field_pattern": LINKEDIN_PROFILE_DOCNAME_PATTERN  # 'item' here will be the value of entity_name
              }


filename pattern for analyzed linkedin content: {
                "static_namespace": ANALYSIS_OUTPUT_NAMESPACE,
                "input_docname_field": "entity_username", # From state via edge mapping
                "input_docname_field_pattern": ANALYSIS_OUTPUT_DOCNAME_PATTERN
              }



## Generation changes (the graph now generates user dna)

**Static Prompt:** "Gather and analyze the following information about the user to build their User DNA: Full Name, Professional Descriptor, Background Summary, Personal Brand, Voice and Tone, Online Presence, Goals, and Audience Insights. Use the user's LinkedIn profile, Content Analysis, and any additional provided materials to complete the User Profile Template."

**Template Sections:**

1. Professional Identity (background, experience, expertise)
2. LinkedIn Profile Analysis (metrics, engagement data)
3. Brand Voice & Style (communication preferences)
4. Content Strategy Goals (objectives, audience, topics)
5. Personal Context (values, influences, story elements)
6. Analytics Insights (performance data, patterns)
7. Success Metrics (KPIs, timeline, benchmarks)
```

## Build workflow with text flow and copied rough nodes

Update the diff node configs (input is already accurate) and add edges as per the flow below and pass appropriate data while strictly following the reference graph structures / patterns since they are fully accurate and well tested.

IMPORTANT: Don't add any new options/node configs you don't see being used in other workflows, this is super important to avoid hallucination; don't assume or make stuff up!

Don't add any new nodes ro change the flow.

Also create template vars, inputs dict etc correctly as shown in reference graphs

@content_calendar_entry.py @content_generation.py 

Flow: 
1. input node -> load_all_context_docs and load_draft_posts
2. [load_all_context_docs, load_draft_posts] -> construct_initial_concepts_prompt (enable_node_fan_in true)
3. construct_initial_concepts_prompt -> generate_concepts
4. generate_concepts -> store_concepts
5. store_concepts -> capture_user_choice
5. capture_user_choice -> route_on_user_choice
6. route_on_user_choice -> construct_concepts_regeneration_prompt [selection: regenerate concepts]
7. route_on_user_choice -> output_node [selection: Go back to initial ideas brief generation]
8. route_on_user_choice -> filter_selected_concepts [selection: select list of concepts]
9. construct_concepts_regeneration_prompt -> generate_concepts (concepts regeneration loop, generate_concepts reads message_history from state)
10. filter_selected_concepts -> construct_update_content_brief_prompt
11. construct_update_content_brief_prompt -> generated_updated_content_brief
12. generated_updated_content_brief -> save_updated_content_brief
13. save_updated_content_brief -> output_node


## Build workflow from scratch

### Content Idea Brief Draft generation

Generate worklfow based on below steps:


1. Generate content briefs for next X weeks: (X) int input optional, default 1
2. Load list of customer context docs such as dna, strategy doc etc
3. Load multiple user draft posts using multiple loader node within posts namespace, load latest N posts (limit and sort by updated_at, DESC); also load user preferences from onboarding namespace, user preferences doc which has user's requested posting frequency / week
4. Load scraped posts for the user
5. Merge both lists and limit the merged list limit using merge aggregate node; also in another operation: compute next X weeks (input) multiplied by user preferences post frequency / week (this is number of content briefs we have to generate)
6. construct prompt for first generation (includes system prompt) with all user docs and merged list in prompt
7. Generate 1 structured output content brief; it reads message history from LLM; this also has fields such as date / time of posting; it sends structured outputs to all_generated_briefs with reducer collect values
8. check IF else on iteration limit, if we have generated the required number of briefs
9. Router node to route to graph finish or store node
10. store node stores draft briefs in separate paths using filename pattern with draft ID
11. send all briefs to output node

reference workflows:
@test_run_content_workflow.py 
@test_linkedin_content_analysis_workflow.py 
@merge_aggregate_node.py 









### Complex workflow: linkedin content analysis

```
Add the workflow with following stesp in file @test_linkedin_content_analysis_workflow.py  :

1. Inputs: entity name
2. Load posts using entity name and scraping namespace
3. Optional: Posts filtering -> only get text content
4. Extract upto 5 themes using all posts in context with LLM (you can use generated theme name to be theme ID potentially?)
5. create batches of 10 posts each
6. For each batch classify posts into the most relevant theme with LLM -> check above structure for classification
7. Map each post to the most relevant theme to create theme groups; merge all batches together
8. Analyze each theme group with LLM to create a detailed report for each group
9. combine all reports together
10. Store combined results

@test_linkedin_scraping_workflow.py 
@map_list_router_node.py 
@test_sources_extraction_workflow.py 
@transform_node.py 
```


### LInkedin Scraping workflow

```
create a linkedin scraping workflow in file @linkedin_scraping_workflow.py  which given user/company's URL and entity name (name is not username) in input: 

## I. scrapes the following: @linkedin_scraping.py 
1. entity profile
2. Upto 50 posts for entity


## II. Stores data into the following paths: 
@customer_data.py 
namespace: linkedin_scraping_results
doc_name for profile: profile_{entity-name}
doc_name for posts: posts_{entity-name}


## III. Transforms data using transform node @transform_node.py  from src schema @posts_schema.py @profile_schema.py to following formats:

NOTE: (only need json with same fields, pydantic is just for reference)

### Profile Schemas 
```

class EducationSchema(BaseSchema):
    """Education entry from LinkedIn profile"""
    school: str = Field(description="School/university name")
    school_id: Optional[str] = Field(None, description="LinkedIn school identifier")
    school_linkedin_url: Optional[str] = Field(None, description="URL to school LinkedIn page")
    school_logo_url: Optional[str] = Field(None, description="URL to school logo")
    degree: Optional[str] = Field(None, description="Degree obtained")
    field_of_study: Optional[str] = Field(None, description="Field of study/major")
```

### Posts schema

```

    
class EngagementMetricsSchema(BaseSchema):
    likes: Dict = Field(description="Number of different reaction types (LIKE, CELEBRATE, SUPPORT, LOVE, INSIGHTFUL, CURIOUS)")
    comments: int = Field(description="Number of comments on the post")
    shares: int = Field(description="Number of times the post was shared")
```

## IV. Stores data into same namespace but diff docname
doc_name for profile: profile_filtered_{entity-name}
doc_name for posts: posts_filtered_{entity-name}

Workflow reference: @post_creation_workflow.py 
```

## Plan
Create a detailed plan including a detailed mermaid diagram to build a workflow using the appropriate nodes available given the workflow PRD; translate requirements in our available nodes and config schema only and suggest caveats / watchouts as required; add placeholders (eg: for loading or storing specific data and config needed for it -- i.e. name/version etc), user inputs, user HITL etc as required for the right kinds of inputs to the graph.
Add each node config in detail as required

All nodes registered here are available:
@db_node_register.py 

Guide file for node specific guides:
@core_dynamic_nodes_guide.md 
@data_join_node_guide.md 
@llm_node_guide.md 
@hitl_node_guide.md 
@filter_node_guide.md 
@if_else_node_guide.md 
@transform_node_guide.md 
@load_customer_data_node_guide.md 
@store_customer_data_node_guide.md 
@prompt_constructor_node_guide.md 
@dynamic_router_node_guide.md 
@map_list_router_node_guide.md 

Guide for nodes interplay and building workflows
@nodes_interplay_guide.md 
@workflow_building_guide.md 


/# PRD
...


## Corrections

There are a lot of hallucinations, incorrect configs and improper graph structure in the workflow plan; correct it using the appropriate context provided and ensure full correct graph config is written with available options and each node config is correctly setup with available options , not non-existing ones and edges are properly configured.

Output full configs, don't miss anything or write placeholders (eg: existing code, or keep as is etc).


## Config
Write in code with placeholders? placeholders can be filled up with the various docs etc!



# Guides

## Nodes Guides

Write a usage guide in directory [guides] @guides to understand and use each of the nodes available below
include everything needed to configure and include a node in a workflow graph schema and make it easy to read and use as guide for people not familar with the codebase and just need to build workflows using the documentation and creating node configs to include in their own workflows.

This should also be readable by product teams or non-coders to understand and configure the node for their workflows.

All nodes registered here are available:
@db_node_register.py 

Code for Nodes available to us:
@flow_nodes.py 
@customer_data.py 
@map_list_router_node.py
@transform_node.py 

@dynamic_nodes
@router_node.py 
@llm_node
@prompt

Test file for nodes for reference usage:
@test_customer_data_nodes.py 
@test_transform_node.py 


For context, we will use Graph schema to construct the grpah schema to define the workflow graph @graph.py; eg: @test_AI_loop.py 

Eg guide for if else node @if_else_node_guide.md 


## Nodes interplay guides


WRite guide on how to make nodes work with each other i.e. node interplay as part of a owrkflow, taking care of dynamic schemas, tips and guide etc on integrating nodes with each other as part of an overall workflow


Include everything needed to configure and include nodes in a workflow graph schema and make it easy to read and use as guide for people not familar with the codebase and just need to build workflows using the documentation and creating node configs to include in their own workflows.

This should also be readable by product teams or non-coders to understand and configure the node for their workflows.

All nodes registered here are available:
@db_node_register.py 

Guide file for node specific guides:
@core_dynamic_nodes_guide.md 
@data_join_node_guide.md 
@llm_node_guide.md 
@hitl_node_guide.md 
@filter_node_guide.md 
@if_else_node_guide.md 
@transform_node_guide.md 
@load_customer_data_node_guide.md 
@store_customer_data_node_guide.md 
@prompt_constructor_node_guide.md 
@dynamic_router_node_guide.md 
@map_list_router_node_guide.md 


For context, we will use Graph schema to construct the grpah schema to define the workflow graph @graph.py; eg: @test_AI_loop.py 


## Workflow Guides


Similarly, ADd more details  and write the e2e guide on how to build workflows, graph schemas etc with diff configuration options and how to configure / use nodes in them;
provide ample egs of workflows using complex nodes, etc
write it in document @workflow_building_guide.md 
@nodes_interplay_guide.md 

@graph.py @test_AI_loop.py 

All nodes registered here are available:
@db_node_register.py 

Guide file for node specific guides:
@core_dynamic_nodes_guide.md 
@data_join_node_guide.md 
@llm_node_guide.md 
@hitl_node_guide.md 
@filter_node_guide.md 
@if_else_node_guide.md 
@transform_node_guide.md 
@load_customer_data_node_guide.md 
@store_customer_data_node_guide.md 
@prompt_constructor_node_guide.md 
@dynamic_router_node_guide.md 
@map_list_router_node_guide.md 
