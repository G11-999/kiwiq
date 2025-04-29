
# Workflows

## Add node to workflow (best to iteratively add nodes to a workflow ensuring valid flow??)

add Linkedin scraping node which fetches a user profile given their username fetched from the input field and passes to initial prompt constructor to generate a personalized linkedin post referencing the linkedin profile of the user ; modify prompts and how prompt is consturcted and create appropriate edges input -> scraping node -> prompt constructor; toggle fan in in prompt constructor by setting enable_node_fan_in=True in node_config (not nested node_config)
Also store the fetched user profile to central state
@post_creation_workflow.py 
@linkedin_scraping_node_guide.md 
@job_config_schema.py 


## Build workflow from scratch

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
class LinkedInProfileSchema(BaseSchema):
    """LinkedIn profile data structure (scraped from LinkedIn)"""
    full_name: str = Field(description="User's full name from LinkedIn")
    headline: str = Field(description="LinkedIn headline")
    location: str = Field(description="User's geographic location")
    about: str = Field(description="About section content")
    follower_count: str = Field(description="Number of followers")
    phone: Optional[str] = Field(None, description="Contact phone number if available")
    company: str = Field(description="Current company name")
    company_description: str = Field(description="Description of current company")
    company_industry: str = Field(description="Industry of current company")
    experiences: List[ExperienceSchema] = Field(description="Work experience history")
    educations: List[EducationSchema] = Field(description="Educational background")

class ExperienceSchema(BaseSchema):
    """Work experience entry from LinkedIn profile"""
    title: str = Field(description="Job title")
    company: str = Field(description="Company name")
    company_id: Optional[str] = Field(None, description="LinkedIn company identifier")
    company_linkedin_url: Optional[str] = Field(None, description="URL to company LinkedIn page")
    company_logo_url: Optional[str] = Field(None, description="URL to company logo")
    date_range: str = Field(description="Employment date range as string")
    description: Optional[str] = Field(None, description="Job description")
    duration: str = Field(description="Employment duration")
    start_month: Optional[int] = Field(None, description="Start month")
    start_year: int = Field(description="Start year")
    end_month: Optional[int] = Field(None, description="End month if applicable")
    end_year: Optional[int] = Field(None, description="End year if applicable")
    is_current: bool = Field(description="Whether this is current position")
    job_type: Optional[str] = Field(None, description="Type of employment (full-time, contract, etc.)")
    location: Optional[str] = Field(None, description="Job location")
    skills: Optional[str] = Field(None, description="Relevant skills")


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
class LinkedInPostSchema(BaseSchema):
    """LinkedIn post data structure (scraped from LinkedIn)"""
    text: str = Field(description="Post content text")
    posted_at_timestamp: str = Field(description="When the post was published (DD/MM/YYYY, HH:MM:SS)")
    type: Literal["Image", "Video", "Text"] = Field(description="Type of LinkedIn post")
    engagement_metrics: EngagementMetricsSchema = Field(description="Post engagement data")
    
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
