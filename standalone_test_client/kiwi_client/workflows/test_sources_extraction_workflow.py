"""
Workflow definition for extracting structured information from multiple documents,
merging the results, and saving them.

Steps:
1. Input: List of documents to load, LLM config, extraction schema, merge strategy, save location.
2. Load Documents: Load all specified documents using LoadCustomerDataNode.
3. Map Documents: Iterate over loaded documents using MapListRouterNode.
4. Extract Data: For each document, call LLMNode for structured extraction.
5. Aggregate Extractions (State): Collect individual extraction results using a reducer.
6. Merge Extractions (Node): Combine collected results using MergeAggregateNode.
7. Store Output: Save the final merged data using StoreCustomerDataNode.
8. Output: Return the path/status of the saved output.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Union
import json # Added for schema conversion


# Using Pydantic for easier schema generation
from pydantic import BaseModel, Field
from typing import List

# Internal dependencies (assuming similar structure to example)
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus
# from workflow_service.registry.schemas.reducers import ReducerType # Import ReducerType

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Workflow Configuration Placeholders ---
# These should be replaced with actual configuration values or loaded dynamically.

# Example LLM Config
LLM_PROVIDER = "openai"
EXTRACTION_MODEL_NAME = "gpt-4.1" # Or another model suitable for structured extraction
LLM_TEMPERATURE = 0.1
LLM_MAX_TOKENS = 10000

# Example Output Save Location (adjust as needed)
OUTPUT_NAMESPACE = "extractions"
OUTPUT_DOCNAME = "merged_extraction_output" # This could be made dynamic via input

# Example Document Identifiers (Needed for setup/cleanup, but not directly in workflow config)
SOURCE_NAMESPACE = "uploaded_files"
DOC1_NAME = "[Jason] Call Transcript"
DOC2_NAME = "[Mani] Meeting transcript"


class ProfessionalIdentitySchema(BaseModel):
    """Professional background and identity"""
    full_name: str = Field(description="User's full name")
    job_title: str = Field(description="Current job title")
    industry_sector: str = Field(description="Industry or business sector")
    company_name: str = Field(description="Current company name")
    company_size: str = Field(description="Size of current company")
    years_of_experience: int = Field(description="Years of professional experience")
    professional_certifications: List[str] = Field(description="Professional certifications held")
    areas_of_expertise: List[str] = Field(description="Areas of professional expertise")
    career_milestones: List[str] = Field(description="Significant career achievements")
    professional_bio: str = Field(description="Professional biography summary")


class LinkedInEngagementMetricsSchema(BaseModel):
    """Engagement performance metrics"""
    average_likes_per_post: int = Field(description="Average likes per post")
    average_comments_per_post: int = Field(description="Average comments per post")
    average_shares_per_post: int = Field(description="Average shares per post")


class LinkedInProfileAnalysisSchema(BaseModel):
    """Analysis of LinkedIn profile"""
    follower_count: int = Field(description="Number of LinkedIn followers")
    connection_count: int = Field(description="Number of LinkedIn connections")
    profile_headline_analysis: str = Field(description="Analysis of profile headline")
    about_section_summary: str = Field(description="Summary of 'About' section")
    engagement_metrics: LinkedInEngagementMetricsSchema = Field(description="Engagement performance metrics")
    top_performing_content_pillars: List[str] = Field(description="Best performing content categories")
    content_posting_frequency: str = Field(description="How often content is posted")
    content_types_used: List[str] = Field(description="Types of content posted")
    network_composition: List[str] = Field(description="Composition of LinkedIn network")


class BrandVoiceAndStyleSchema(BaseModel):
    """Personal brand voice characteristics"""
    communication_style: str = Field(description="Overall communication style")
    tone_preferences: List[str] = Field(description="Preferred tones in communication")
    vocabulary_level: str = Field(description="Level of vocabulary used")
    sentence_structure_preferences: str = Field(description="Preferred sentence structures")
    content_format_preferences: List[str] = Field(description="Preferred content formats")
    emoji_usage: str = Field(description="How emojis are used")
    hashtag_usage: str = Field(description="How hashtags are used")
    storytelling_approach: str = Field(description="Approach to storytelling")


class ContentStrategyGoalsSchema(BaseModel):
    """Content strategy goals and targets"""
    primary_goal: str = Field(description="Primary content goal")
    secondary_goals: List[str] = Field(description="Secondary content goals")
    target_audience_demographics: str = Field(description="Target audience demographics")
    ideal_reader_personas: List[str] = Field(description="Ideal reader descriptions")
    audience_pain_points: List[str] = Field(description="Pain points of target audience")
    value_proposition_to_audience: str = Field(description="Value proposition offered")
    call_to_action_preferences: List[str] = Field(description="Preferred calls to action")
    content_pillar_themes: List[str] = Field(description="Content pillar themes")
    topics_of_interest: List[str] = Field(description="Topics of interest to cover")
    topics_to_avoid: List[str] = Field(description="Topics to avoid covering")


class PersonalContextSchema(BaseModel):
    """Personal background context"""
    personal_values: List[str] = Field(description="Personal values")
    professional_mission_statement: str = Field(description="Professional mission statement")
    content_creation_challenges: List[str] = Field(description="Challenges in content creation")
    personal_story_elements_for_content: List[str] = Field(description="Personal story elements to use")
    notable_life_experiences: List[str] = Field(description="Notable life experiences")
    inspirations_and_influences: List[str] = Field(description="Sources of inspiration")
    books_resources_they_reference: List[str] = Field(description="Books and resources referenced")
    quotes_they_resonate_with: List[str] = Field(description="Resonating quotes")


class AnalyticsInsightsSchema(BaseModel):
    """Analytical insights about content"""
    optimal_content_length: str = Field(description="Optimal content length")
    audience_geographic_distribution: str = Field(description="Geographic distribution of audience")
    engagement_time_patterns: str = Field(description="Patterns in engagement timing")
    keyword_performance_analysis: str = Field(description="Performance of keywords")
    competitor_benchmarking: str = Field(description="Benchmark against competitors")
    growth_rate_metrics: str = Field(description="Growth rate metrics")


class SuccessMetricsSchema(BaseModel):
    """Metrics to measure success"""
    content_performance_kpis: List[str] = Field(description="KPIs for content performance")
    engagement_quality_metrics: List[str] = Field(description="Metrics for engagement quality")
    conversion_goals: List[str] = Field(description="Conversion goals")
    brand_perception_goals: List[str] = Field(description="Brand perception goals")
    timeline_for_expected_results: str = Field(description="Timeline for expected results")
    benchmarking_standards: str = Field(description="Standards for benchmarking")


class UserUnderstandingSchema(BaseModel):
    """Comprehensive user DNA profile derived from all inputs (AI-generated)"""
    professional_identity: ProfessionalIdentitySchema = Field(description="Professional background and identity")
    linkedin_profile_analysis: LinkedInProfileAnalysisSchema = Field(description="Analysis of LinkedIn profile")
    brand_voice_and_style: BrandVoiceAndStyleSchema = Field(description="Personal brand voice characteristics")
    content_strategy_goals: ContentStrategyGoalsSchema = Field(description="Content strategy goals and targets")
    personal_context: PersonalContextSchema = Field(description="Personal background context")
    analytics_insights: AnalyticsInsightsSchema = Field(description="Analytical insights about content")
    success_metrics: SuccessMetricsSchema = Field(description="Metrics to measure success")


class StrategyAudienceSchema(BaseModel):
    """Target audience segments for strategy"""
    primary: str = Field(description="Primary audience")
    secondary: str = Field(description="Secondary audience")
    tertiary: str = Field(description="Tertiary audience")


class FoundationElementsSchema(BaseModel):
    """Foundational elements of the strategy"""
    expertise: List[str] = Field(description="Areas of expertise")
    core_beliefs: List[str] = Field(description="Core beliefs")
    objectives: List[str] = Field(description="Strategy objectives")


class PostPerformanceAnalysisSchema(BaseModel):
    """Analysis of post performance"""
    current_engagement: str = Field(description="Current engagement levels")
    content_that_resonates: str = Field(description="Content types that resonate with audience")
    highest_performing_formats: str = Field(description="Best performing content formats")
    audience_response: str = Field(description="How audience responds to content")


class OverviewSchema(BaseModel):
    """Strategy overview"""
    post_performance_analysis: PostPerformanceAnalysisSchema = Field(description="Analysis of post performance")


class ContentPillarSchema(BaseModel):
    """Content pillar definitions"""
    name: str = Field(description="Pillar name")
    theme: str = Field(description="Pillar theme")
    sub_themes: List[str] = Field(description="Sub-themes within pillar")


class HighImpactFormatSchema(BaseModel):
    """High impact content formats"""
    name: str = Field(description="Format name")
    steps: List[str] = Field(description="Steps to create this format")
    example: str = Field(description="Example of the format")


class ImplementationSchema(BaseModel):
    """Implementation details"""
    weekly_content_calendar: str = Field(description="Weekly content schedule")
    thirty_day_targets: str = Field(description="30-day goals")
    ninety_day_targets: str = Field(description="90-day goals")


class ContentStrategySchema(BaseModel):
    """Content strategy document derived from user DNA (AI-generated)"""
    title: str = Field(description="Strategy title")
    navigation_menu: List[str] = Field(description="Navigation menu items")
    foundation_elements: FoundationElementsSchema = Field(description="Foundational elements of the strategy")
    overview: OverviewSchema = Field(description="Strategy overview")
    core_perspectives: List[str] = Field(description="Core content perspectives")
    content_pillars: List[ContentPillarSchema] = Field(description="Content pillar definitions")
    high_impact_formats: List[HighImpactFormatSchema] = Field(description="High impact content formats")
    implementation: ImplementationSchema = Field(description="Implementation details")
   
   
class ExtractionSchema(BaseModel):
		content_strategy: Optional[ContentStrategySchema]
		user_understanding: Optional[UserUnderstandingSchema]

# Generate JSON schema from the Pydantic model
EXTRACTION_JSON_SCHEMA = ExtractionSchema.model_json_schema()


# Placeholder - Define your actual system prompt
LLM_SYSTEM_PROMPT = """You are an AI assistant designed to extract structured information from documents. 
Respond only with the requested JSON object. The JSON schema is as follows: ```json\n{extraction_schema}\n```"""


# # Example Extraction Schema (replace with your actual schema)
# # This defines the structure the LLM should extract for *each* document.
# EXTRACTION_SCHEMA_SPEC = {
#     "schema_name": "DocumentExtraction",
#     "fields": {
#         "summary": { "type": "str", "required": True, "description": "A brief summary of the document content." },
#         "key_points": { "type": "list", "items_type": "str", "required": False, "description": "List of key points or topics discussed." },
#         "entities": { "type": "dict", "required": False, "description": "Detected entities (e.g., people, organizations, locations)." }
#     }
# }

# Example Merge Strategy (adjust based on how you want to combine extractions)
# This assumes the extraction schema above and merges fields from multiple extractions.
MERGE_STRATEGY_CONFIG = {
    "map_phase": { # Keep default map phase (auto-merge)
        "unspecified_keys_strategy": "auto_merge",
        "key_mappings": [] # No explicit renaming needed if keys match extraction schema
    },
    "reduce_phase": {
        # Define how to combine fields when merging extractions from different documents
        "default_reducer": "nested_merge_aggregate", # Default, but override specific keys below
        "reducers": {
            # "summary": "combine_in_list",     # Collect all summaries into a list
            # "key_points": "append",          # Append key points from all documents into one list
            # "entities": "nested_merge_replace" # Merge entity dictionaries (last one wins for conflicting keys)
        },
        "error_strategy": "coalesce_keep_non_empty"
    },
    "transformation_error_strategy": "skip_operation"
    # No post-merge transformations needed for this example
}

# --- Workflow Graph Schema Definition ---


workflow_graph_schema = {
  "nodes": {
    # --- 1. Input Node: Now accepts a list of documents to process ---
    "input_node": {
      "node_id": "input_node",
      "node_name": "input_node",
      "node_config": {},
      "dynamic_output_schema": {
          "fields": {
              "documents_to_process": {
                  "type": "list",
                  "required": True,
                  "description": "List of document identifiers (namespace/docname pairs) to load and process."
              }
          }
        }
    },

    # --- 3. Load Single Document (Inside Map Branch) ---
    "load_documents": { # Renamed from load_documents, now inside map loop
      "node_id": "load_documents",
      "node_name": "load_customer_data",
      "node_config": {
          # Global defaults remain the same
          "global_is_shared": False,
          "global_is_system_entity": False,
          "global_version_config": {"version": "default"},
          "global_schema_options": {"load_schema": False},
          # Configure to load *one* document based on the input identifier
          "load_configs_input_path": "documents_to_process",
        #   "load_paths": [
        #       {
        #           # Use input fields from the mapper item (doc_identifier)
        #         #   "filename_config": {
        #         #       # Assumes mapper passes {'namespace': '...', 'docname': '...'} as 'doc_identifier'
        #         #       "input_namespace_field": "doc_identifier.namespace",
        #         #       "input_docname_field": "doc_identifier.docname"
        #         #   },
                 
        #           # Output field name for the loaded content within this branch
        #           "output_field_name": "loaded_documents"
        #       }
        #   ]
      },
      "dynamic_output_schema": {
        "fields": {
          "loaded_documents": {
            "type": "any",
            "required": True,
            "description": "List or single document loaded from the input"
          }
        }
      }
      # Reads: doc_identifier (from map_identifiers_to_process item via private input)
      # Writes: loaded_document_content (via private output)
    },


    # --- 2. Map Identifiers to Processing Branch ---
    "map_identifiers_to_process": { # Renamed from map_docs_to_extract
        "node_id": "map_identifiers_to_process",
        "node_name": "map_list_router_node",
        "node_config": {
            "choices": ["construct_prompt"], # Target the loader node first in the branch
            "map_targets": [
                {
                    # Source path points to the list of identifiers from the input node
                    "source_path": "loaded_documents",
                    "destinations": ["construct_prompt"] # Start the branch here
                }
            ]
        },
        # Reads: documents_to_process (from input_node)
        # Iterates over the list items (dicts containing namespace/docname).
        # Sends each item -> doc_identifier to load_documents
    },

    # --- 4. Construct Prompt (Inside Map Branch) ---
    "construct_prompt": {
      "node_id": "construct_prompt",
      "node_name": "prompt_constructor",
      "private_input_mode": True,  # Receives input directly from map_identifiers_to_process
      "private_output_mode": True, # Sends output directly to extract_data
      "node_config": {
        "prompt_templates": {
          # User prompt template takes the document content from the loader
          "extraction_user_prompt": {
            "id": "extraction_user_prompt",
            # Updated template to reflect input source
            "template": "Please extract information from the following document content: \n\nFilename: {document_filename}\n\nContent: \n\n```md\n{document_content}\n```\n\n",
            "variables": {
              "document_content": None, # Required, mapped from load_documents edge
              "document_filename": None # Required, mapped from load_documents edge
            },
            "construct_options": {
               # Map from the input field provided by the edge from load_documents
               "document_content": "markdown_content",
               "document_filename": "source_filename"
            }
          },
          # System prompt is static
          "extraction_system_prompt": {
            "id": "extraction_system_prompt",
            "template": LLM_SYSTEM_PROMPT,
            "variables": {
                "extraction_schema": EXTRACTION_JSON_SCHEMA
            },
            "construct_options": {}
          }
        }
      }
      # Reads: document_data_input (mapped from load_documents via private input)
      # Writes: user_prompt, system_prompt (via private output)
    },

    # --- 5. Extract Data (LLM - Inside Map Branch) ---
    "extract_data": {
      "node_id": "extract_data",
      "node_name": "llm",
      "private_input_mode": True, # Receives input directly from construct_prompt
      # Output goes to the graph state aggregator (no longer private output)
      "node_config": {
          "llm_config": {
              "model_spec": {"provider": LLM_PROVIDER, "model": EXTRACTION_MODEL_NAME},
              "temperature": LLM_TEMPERATURE,
              "max_tokens": LLM_MAX_TOKENS
          },
          "output_schema": {
              # Use the schema definition generated from Pydantic model
             "schema_definition": EXTRACTION_JSON_SCHEMA
          },
      }
      # Reads: user_prompt, system_prompt (from construct_prompt via private input)
      # Writes: structured_output (sent to $graph_state)
    },

    # --- 6. Merge Extractions (Outside Map Branch) ---
    # TODO: LLM DEDUPE! Try this graph without map reduce and process all docs together!
    "merge_extractions": {
      "node_id": "merge_extractions",
      "node_name": "merge_aggregate",
      "node_config": {
          "operations": [
              {
                  "output_field_name": "merged_result_field",
                  # Path to the list of extractions collected in the state
                  "select_paths": ["collected_extractions"], # Input field name, mapped from state
                  "merge_strategy": MERGE_STRATEGY_CONFIG
              }
          ]
      },
      "dynamic_input_schema": {
        "fields": {
          "collected_extractions": {
            "type": "any",
            "required": True,
            "description": "List or single extracted data"
          }
        }
      }
      # Reads: collected_extractions (mapped from $graph_state.all_extractions)
      # Writes: merged_data
    },

    # --- 7. Store Merged Output (Outside Map Branch) ---
    "save_merged_extraction": {
      "node_id": "save_merged_extraction",
      "node_name": "store_customer_data",
      "node_config": {
          "store_configs": [
              {
                  "input_field_path": "merged_data.merged_result_field",
                  "target_path": {
                      "filename_config": {
                          "static_namespace": OUTPUT_NAMESPACE,
                          "static_docname": OUTPUT_DOCNAME
                      }
                  },
              }
          ],
        #   "global_is_shared": False,
        #   "global_is_system_entity": False,
          "global_versioning": {"is_versioned": False, "operation": "upsert"},
          "global_schema_options": {}
      }
      # Reads: data_to_save_container (mapped from merge_extractions.merged_data)
      # Writes: paths_processed
    },

    # --- 8. Output Node (Outside Map Branch) ---
    "output_node": {
      "node_id": "output_node",
      "node_name": "output_node",
      "node_config": {},
      "dynamic_input_schema": {
        "fields": {
          "all_extractions": {
            "type": "any",
            "required": True,
            "description": "List or single extracted data"
          }
        }
      }
      # Reads: final_save_details (from save_merged_extraction)
    }
  },

  # --- Edges Defining Data Flow ---
  "edges": [
    # --- Input -> Map ---
    { "src_node_id": "input_node", "dst_node_id": "load_documents", "mappings": [
        # Pass the list of document identifiers to the mapper
        { "src_field": "documents_to_process", "dst_field": "documents_to_process" }
      ],
      "description": "Pass the list of document identifiers to the load_documents node."
    },

    # --- Map -> Load (Private Branch Start) ---
    { "src_node_id": "load_documents", "dst_node_id": "map_identifiers_to_process", "mappings": [
        # Map the item being iterated (doc identifier dict) to the loader's expected input field
        { "src_field": "loaded_documents", "dst_field": "loaded_documents", "description": "Pass the documents to be processed."}
      ]
    },

    # --- Load -> Construct Prompt (Private Branch) ---
    { "src_node_id": "map_identifiers_to_process", "dst_node_id": "construct_prompt", "mappings": [
        # Map the loaded content to the prompt constructor's expected input field
        # No mapping required, entire object will be sent as is
      ]
    },

    # --- Construct Prompt -> Extract (Private Branch) ---
    { "src_node_id": "construct_prompt", "dst_node_id": "extract_data", "mappings": [
        { "src_field": "extraction_user_prompt", "dst_field": "user_prompt"},
        { "src_field": "extraction_system_prompt", "dst_field": "system_prompt"}
      ]
    },

    # --- Extract -> State (Aggregate - Branch End) ---
    { "src_node_id": "extract_data", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "structured_output", "dst_field": "all_extractions", "description": "Collect the structured output from each extraction branch."}
      ]
    },

    { "src_node_id": "extract_data", "dst_node_id": "merge_extractions", "mappings": [
      ]
    },

    # --- State -> Merge (After Map/Reduce) ---
    { "src_node_id": "$graph_state", "dst_node_id": "merge_extractions", "mappings": [
        { "src_field": "all_extractions", "dst_field": "collected_extractions", "description": "Pass the list of all extracted data to the merge node."}
      ]
    },

    # --- Merge -> Store ---
    { "src_node_id": "merge_extractions", "dst_node_id": "save_merged_extraction", "mappings": [
        { "src_field": "merged_data", "dst_field": "merged_data", "description": "Pass the container holding the merged data."}
      ]
    },


    # --- Merge -> State ---
    { "src_node_id": "merge_extractions", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "merged_data", "dst_field": "merged_data", "description": "Pass the merged data to the graph state."}
      ]
    },

    # --- Store -> Output ---
    { "src_node_id": "save_merged_extraction", "dst_node_id": "output_node", "mappings": [
        { "src_field": "paths_processed", "dst_field": "final_save_details", "description": "Pass the details of the saved document(s)."}
      ]
    },

    # --- State -> Output ---
    { "src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
        { "src_field": "all_extractions", "dst_field": "all_extractions", "description": "Pass the list of all extracted data to the merge node."},
        { "src_field": "merged_data", "dst_field": "merged_data", "description": "Pass the merged data to the graph state."},
      ]
    },
    
  ],

  # --- Define Start and End ---
  "input_node_id": "input_node",
  "output_node_id": "output_node",

  # --- State Reducers ---
  "metadata": {
      "$graph_state": {
        "reducer": {
          "all_extractions": "collect_values",
        }
      }
  }
}


# --- Test Execution Logic ---

async def validate_extraction_workflow_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """
    Custom validation function for the extraction workflow outputs.
    (Remains largely the same, checks the final saved output details)
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating extraction workflow outputs...")
    assert 'final_save_details' in outputs, "Validation Failed: 'final_save_details' key missing."
    final_details = outputs.get('final_save_details')
    assert isinstance(final_details, list), f"Validation Failed: 'final_save_details' should be a list, got {type(final_details)}"
    assert len(final_details) > 0, "Validation Failed: 'final_save_details' list is empty."
    assert isinstance(final_details[0], list), f"Validation Failed: First item in 'final_save_details' should be a list, got {type(final_details[0])}"
    assert len(final_details[0]) == 3, f"Validation Failed: Inner list in 'final_save_details' should have 3 elements (ns, dn, op), got {len(final_details[0])}"
    saved_ns, saved_dn, saved_op = final_details[0]
    assert saved_ns == OUTPUT_NAMESPACE, f"Validation Failed: Saved namespace mismatch. Expected {OUTPUT_NAMESPACE}, got {saved_ns}"
    assert saved_dn == OUTPUT_DOCNAME, f"Validation Failed: Saved docname mismatch. Expected {OUTPUT_DOCNAME}, got {saved_dn}"
    logger.info(f"   Found expected 'final_save_details': {final_details}")
    logger.info("✓ Output structure and content validation passed.")
    return True


async def main_test_extraction_workflow():
    """
    Tests the Sources Extraction Workflow using the run_workflow_test helper.
    Now provides a list of documents as input.
    """
    test_name = "Sources Extraction Workflow Test V5 (Map-Load-Extract)" # Updated test name
    print(f"--- Starting {test_name} --- ")

    # --- Define Input Data ---
    # Provide the list of document identifiers matching the input_node schema
    workflow_inputs: Dict[str, Any] = {
        "documents_to_process": [
            {
                "filename_config": {
                    "static_namespace": SOURCE_NAMESPACE,
                    "static_docname": DOC1_NAME
                },
                "output_field_name": "loaded_documents",
            },
            {
                "filename_config": {
                    "static_namespace": SOURCE_NAMESPACE,
                    "static_docname": DOC2_NAME
                },
                "output_field_name": "loaded_documents",
            }
        ]
    }

    # --- Define Setup and Cleanup ---
    # Setup and Cleanup remain the same, defining the external documents
    setup_docs: List[SetupDocInfo] = [
        # {
        #     'namespace': SOURCE_NAMESPACE, 'docname': DOC1_NAME, 'is_versioned': False,
        #     'initial_data': {
        #         "text": "Introduction to Content Strategy: John Doe is a marketing manager at TechCorp (500 employees) with 10 years experience. Focuses on B2B lead generation via blog posts and webinars. Prefers professional tone. Avoid politics. Goal: Increase MQL by 15%."
        #     }, 'is_shared': False, 'is_system_entity': False,
        # },
        # {
        #     'namespace': SOURCE_NAMESPACE, 'docname': DOC2_NAME, 'is_versioned': False,
        #     'initial_data': {
        #         "text": "Advanced SEO Tactics: Alice Brown, SEO Specialist at Innovate Solutions (startup), shares insights. Expertise in technical SEO, link building. Uses informal, engaging style with emojis. Goal: Improve organic traffic by 30%. Likes #SEO #DigitalMarketing."
        #     }, 'is_shared': False, 'is_system_entity': False,
        # }
    ]
    cleanup_docs: List[CleanupDocInfo] = [
        # {'namespace': SOURCE_NAMESPACE, 'docname': DOC1_NAME, 'is_versioned': False, 'is_shared': False},
        # {'namespace': SOURCE_NAMESPACE, 'docname': DOC2_NAME, 'is_versioned': False, 'is_shared': False},
        # {'namespace': OUTPUT_NAMESPACE, 'docname': OUTPUT_DOCNAME, 'is_versioned': False, 'is_shared': False},
    ]
    setup_schemas = None
    cleanup_created_schemas = False

    # --- Execute Test ---
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=workflow_inputs, # Use updated inputs with list of docs
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=[],
        setup_docs=setup_docs,
        cleanup_docs=cleanup_docs,
        setup_schemas=setup_schemas,
        cleanup_created_schemas=cleanup_created_schemas,
        validate_output_func=validate_extraction_workflow_output,
        stream_intermediate_results=False,
        poll_interval_sec=5,
        timeout_sec=900
    )

    print(f"\n--- {test_name} Finished --- ")
    if final_run_status_obj:
        print(f"Final Status: {final_run_status_obj.status}")
        if final_run_outputs:
            print(f"Final Save Details: {final_run_outputs.get('final_save_details')}")
        if final_run_status_obj.status != WorkflowRunStatus.COMPLETED:
             print(f"Error Message: {final_run_status_obj.error_message}")


# Standard Python entry point check.
if __name__ == "__main__":
    print("="*50)
    print("Executing Sources Extraction Workflow Test V5 (Map-Load-Extract)") # Updated print message
    print("="*50)
    try:
        asyncio.run(main_test_extraction_workflow())
    except KeyboardInterrupt:
        print("\nExecution interrupted by user.")
    except Exception as main_err:
        print(f"\nCritical error during script execution: {main_err}")
        logger.exception("Critical error running main")

    print("\nScript execution finished.")
