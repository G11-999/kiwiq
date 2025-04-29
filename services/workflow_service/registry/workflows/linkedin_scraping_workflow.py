import json
import asyncio
from typing import List, Optional, Dict, Any, Literal

# --- Target Schema Definitions (for reference) ---

# Placeholder classes mirroring the user's request for transformation targets.
# These are NOT used directly by the workflow nodes but serve as documentation
# for the intended transformation output.

# class BaseSchema: # Minimal base for Pydantic-like structure display
#     pass

# class EngagementMetricsSchema(BaseSchema):
#     """LinkedIn post engagement data structure (target)"""
#     likes: Dict[str, int] = {} # Field(description="Number of different reaction types") # NOTE: transform_data cannot create this structure
#     comments: int = 0 # Field(description="Number of comments on the post")
#     shares: int = 0 # Field(description="Number of times the post was shared")

# class LinkedInPostSchema(BaseSchema):
#     """LinkedIn post data structure (target)"""
#     text: str = "" # Field(description="Post content text")
#     posted_at_timestamp: str = "" # Field(description="When the post was published (DD/MM/YYYY, HH:MM:SS)") # NOTE: transform_data cannot format this
#     type: Literal["Image", "Video", "Text"] = "Text" # Field(description="Type of LinkedIn post") # NOTE: transform_data cannot determine this logic
#     engagement_metrics: EngagementMetricsSchema = EngagementMetricsSchema() # Field(description="Post engagement data")


# class ExperienceSchema(BaseSchema):
#     """Work experience entry from LinkedIn profile (target)"""
#     title: str = "" # Field(description="Job title")
#     company: str = "" # Field(description="Company name")
#     company_id: Optional[str] = None # Field(None, description="LinkedIn company identifier")
#     company_linkedin_url: Optional[str] = None # Field(None, description="URL to company LinkedIn page")
#     company_logo_url: Optional[str] = None # Field(None, description="URL to company logo")
#     date_range: str = "" # Field(description="Employment date range as string") # NOTE: transform_data cannot construct this
#     description: Optional[str] = None # Field(None, description="Job description")
#     duration: str = "" # Field(description="Employment duration") # NOTE: transform_data cannot calculate this
#     start_month: Optional[int] = None # Field(None, description="Start month")
#     start_year: int = 0 # Field(description="Start year")
#     end_month: Optional[int] = None # Field(None, description="End month if applicable")
#     end_year: Optional[int] = None # Field(None, description="End year if applicable")
#     is_current: bool = False # Field(description="Whether this is current position") # NOTE: transform_data cannot determine this reliably without logic
#     job_type: Optional[str] = None # Field(None, description="Type of employment (full-time, contract, etc.)")
#     location: Optional[str] = None # Field(None, description="Job location")
#     skills: Optional[str] = None # Field(None, description="Relevant skills") # NOTE: transform_data cannot extract/format this easily

# class EducationSchema(BaseSchema):
#     """Education entry from LinkedIn profile (target)"""
#     school: str = "" # Field(description="School/university name")
#     school_id: Optional[str] = None # Field(None, description="LinkedIn school identifier")
#     school_linkedin_url: Optional[str] = None # Field(None, description="URL to school LinkedIn page")
#     school_logo_url: Optional[str] = None # Field(None, description="URL to school logo")
#     degree: Optional[str] = None # Field(None, description="Degree obtained")
#     field_of_study: Optional[str] = None # Field(None, description="Field of study/major")

# class LinkedInProfileSchema(BaseSchema):
#     """LinkedIn profile data structure (target)"""
#     full_name: str = "" # Field(description="User's/Company's full name from LinkedIn") # NOTE: transform_data cannot combine names
#     headline: str = "" # Field(description="LinkedIn headline")
#     location: str = "" # Field(description="User's geographic location") # NOTE: transform_data cannot combine fields easily
#     about: str = "" # Field(description="About section content")
#     follower_count: Optional[int] = 0 # Field(None, description="Number of followers") # NOTE: May not be available on person profile
#     phone: Optional[str] = None # Field(None, description="Contact phone number if available")
#     company: Optional[str] = "" # Field(description="Current company name (for person) or entity name (for company)")
#     company_description: Optional[str] = "" # Field(description="Description of current company (for person) or entity (for company)")
#     company_industry: Optional[str] = "" # Field(description="Industry of current company (for person) or entity (for company)")
#     experiences: List[ExperienceSchema] = [] # Field(description="Work experience history") # NOTE: Detailed mapping difficult with transform_data
#     educations: List[EducationSchema] = [] # Field(description="Educational background") # NOTE: Detailed mapping difficult with transform_data

# --- Workflow Constants ---
TARGET_NAMESPACE = "linkedin_scraping_results"
POST_LIMIT = 50

# --- Workflow Graph Definition ---
workflow_graph_schema = {
  "nodes": {
    # --- 1. Input Node ---
    "input_node": {
      "node_id": "input_node",
      "node_name": "input_node",
      "node_config": {},
      "dynamic_output_schema": {
          "fields": {
              "entity_url": { "type": "str", "required": True, "description": "URL of the LinkedIn entity (person or company)." },
              "entity_name": { "type": "str", "required": True, "description": "Name of the entity (used for saving doc names)." },
          }
        }
    },

    # --- 2. Scrape LinkedIn Data ---
    "scrape_entity": {
      "node_id": "scrape_entity",
      "node_name": "linkedin_scraping",
      "node_config": {
        "test_mode": False, # Set to True for testing without API calls/credits
        "jobs": [
          # Job 1: Get Profile Info
          {
            "output_field_name": "scraped_profile_job", # Intermediate output name for this job's result
            "job_type": { "static_value": "profile_info" },
            "url": { "input_field_path": "entity_url" },   # Get URL from node input
            "profile_info": { "static_value": "yes" } # Required flag alignment
          },
          # Job 2: Get Entity Posts
          {
            "output_field_name": "scraped_posts_job", # Intermediate output name for this job's result
            "job_type": { "static_value": "entity_posts" },
            "url": { "input_field_path": "entity_url" },   # Get URL from node input
            "post_limit": { "static_value": POST_LIMIT },
            "entity_posts": { "static_value": "yes" } # Required flag alignment
            # post_comments, post_reactions defaults to "no"
          }
        ]
      }
      # Input fields expected: entity_url (from input_node)
      # Output fields: execution_summary, scraping_results (containing scraped_profile_job, scraped_posts_job)
    },

    # --- 3. Store Raw Scraped Data ---
    "store_raw_data": {
      "node_id": "store_raw_data",
      "node_name": "store_customer_data",
      "node_config": {
        # Use upsert unversioned for simplicity in this example
        "global_versioning": { "is_versioned": False, "operation": "upsert" },
        "global_is_shared": False, # Assume user-specific storage
        "store_configs": [
          # Config 1: Store Raw Profile
          {
            # Use the 'scraping_results' which contains outputs keyed by 'output_field_name' from the scraper jobs
            "input_field_path": "scraping_results.scraped_profile_job",
            "target_path": {
              "filename_config": {
                "static_namespace": TARGET_NAMESPACE,
                # Use entity_name (from node input, mapped from $graph_state) for the pattern context
                "input_docname_field": "entity_name", # Field in node's input containing the value
                "input_docname_field_pattern": "profile_{item}" # 'item' here will be the value of entity_name
              }
            }
          },
          # Config 2: Store Raw Posts
          {
            "input_field_path": "scraping_results.scraped_posts_job",
            "target_path": {
              "filename_config": {
                "static_namespace": TARGET_NAMESPACE,
                # Use entity_name (from node input, mapped from $graph_state) for the pattern context
                "input_docname_field": "entity_name", # Field in node's input containing the value
                "input_docname_field_pattern": "posts_{item}" # 'item' here will be the value of entity_name
              }
            }
          }
        ]
      }
      # Input fields expected: scraping_results (from scrape_entity), entity_name (from $graph_state)
      # Output: passthrough_data, paths_processed
    },

    # # --- 4. Transform Combined Data ---
    # "transform_combined_data": {
    #   "node_id": "transform_combined_data",
    #   "node_name": "transform_data",
    #   "node_config": {
    #     "mappings": [
    #       # Profile Mappings (prefixed with input field name)
    #       # NOTE: Limitations of transform_data still apply (no combining fields, complex logic).
    #       { "source_path": "input_profile_data.firstName", "destination_path": "profile.first_name" },
    #       { "source_path": "input_profile_data.lastName", "destination_path": "profile.last_name" },
    #       { "source_path": "input_profile_data.headline", "destination_path": "profile.headline" },
    #       { "source_path": "input_profile_data.geo.full", "destination_path": "profile.location" }, # Assumes person schema
    #       { "source_path": "input_profile_data.summary", "destination_path": "profile.about" }, # Assumes person schema
    #       { "source_path": "input_profile_data.position.0.companyName", "destination_path": "profile.current_company_name" }, # Risky assumption
    #       { "source_path": "input_profile_data.position.0.companyIndustry", "destination_path": "profile.current_company_industry" }, # Risky assumption
    #       { "source_path": "input_profile_data.position", "destination_path": "profile.experiences_raw" }, # Raw list
    #       { "source_path": "input_profile_data.educations", "destination_path": "profile.educations_raw" }, # Raw list

    #       # Posts Mappings (prefixed with input field name)
    #       # NOTE: Still just copying the raw list due to transform_data limitations.
    #       { "source_path": "input_posts_data", "destination_path": "posts.raw_list" }
    #       # Example if transforming specific fields was possible:
    #       # { "source_path": "input_posts_data.0.text", "destination_path": "posts.first_post_text" },
    #     ]
    #   }
    #   # Input fields expected: input_profile_data, input_posts_data (mapped from scrape_entity)
    #   # Output: transformed_data (containing fields like profile.first_name, posts.raw_list etc.)
    # },

    # # --- 5. Store Transformed Data ---
    # "store_transformed_data": {
    #   "node_id": "store_transformed_data",
    #   "node_name": "store_customer_data",
    #   "node_config": {
    #     "global_versioning": { "is_versioned": False, "operation": "upsert" },
    #     "global_is_shared": False,
    #     "store_configs": [
    #       # Config 1: Store Transformed Profile (from the combined output)
    #       {
    #         # Access the 'profile' sub-object within the transform_combined_data output
    #         "input_field_path": "transformed_data.profile",
    #         "target_path": {
    #           "filename_config": {
    #             "static_namespace": TARGET_NAMESPACE,
    #              # Use entity_name (from node input, mapped from $graph_state) for the pattern context
    #             "input_docname_field": "entity_name", # Field in node's input containing the value
    #             "input_docname_field_pattern": "profile_filtered_{item}" # 'item' here will be the value of entity_name
    #           }
    #         }
    #       },
    #       # Config 2: Store Transformed Posts (from the combined output)
    #       {
    #         # Access the 'posts' sub-object within the transform_combined_data output
    #         "input_field_path": "transformed_data.posts",
    #         "target_path": {
    #           "filename_config": {
    #             "static_namespace": TARGET_NAMESPACE,
    #              # Use entity_name (from node input, mapped from $graph_state) for the pattern context
    #             "input_docname_field": "entity_name", # Field in node's input containing the value
    #             "input_docname_field_pattern": "posts_filtered_{item}" # 'item' here will be the value of entity_name
    #           }
    #         }
    #       }
    #     ]
    #   }
    #   # Input fields expected: transformed_data (from transform_combined_data), entity_name (from $graph_state)
    #   # Output: passthrough_data, paths_processed
    # },

    # --- 6. Output Node ---
    "output_node": {
      "node_id": "output_node",
      "node_name": "output_node",
      "node_config": {},
    #    "dynamic_output_schema": {
    #       "fields": {
    #           "raw_data_paths": { "type": "list", "required": False, "description": "Paths where raw scraped data was stored." },
    #         #   "transformed_data_paths": { "type": "list", "required": False, "description": "Paths where transformed data was stored." },
    #           "entity_name_processed": { "type": "str", "required": False, "description": "The name of the entity processed." }
    #       }
    #     }
    }
  },

  # --- Edges Defining Data Flow ---
  "edges": [
    # Input -> State: Store entity_name globally for use in doc names
    { "src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "entity_name", "dst_field": "entity_name" }
      ]
    },
    # Input -> Scrape Entity: Pass URL and Type
    { "src_node_id": "input_node", "dst_node_id": "scrape_entity", "mappings": [
        { "src_field": "entity_url", "dst_field": "entity_url" },
      ]
    },
    # Scrape Entity -> Store Raw Data: Pass scraped results
    { "src_node_id": "scrape_entity", "dst_node_id": "store_raw_data", "mappings": [
        { "src_field": "scraping_results", "dst_field": "scraping_results" }
      ]
    },
    # State (entity_name) -> Store Raw Data: Pass entity name for doc naming pattern
    # The store_customer_data node needs entity_name in its DIRECT input to resolve input_docname_field
    { "src_node_id": "$graph_state", "dst_node_id": "store_raw_data", "mappings": [
        { "src_field": "entity_name", "dst_field": "entity_name" }
      ]
    },
    # # Scrape Entity -> Transform Combined Data: Pass profile and posts data under specific keys
    # { "src_node_id": "scrape_entity", "dst_node_id": "transform_combined_data", "mappings": [
    #     # Map profile job result to 'input_profile_data' field in transform node input
    #     { "src_field": "scraping_results.scraped_profile_job", "dst_field": "input_profile_data" },
    #     # Map posts job result to 'input_posts_data' field in transform node input
    #     { "src_field": "scraping_results.scraped_posts_job", "dst_field": "input_posts_data" }
    #   ]
    # },
    # # Transform Combined Data -> Store Transformed Data: Pass the unified transformed output
    # { "src_node_id": "transform_combined_data", "dst_node_id": "store_transformed_data", "mappings": [
    #     # The output of transform_data is under the 'transformed_data' key by default
    #     # This key now contains both profile and posts structured data
    #     { "src_field": "transformed_data", "dst_field": "transformed_data" }
    #   ]
    # },
    #  # State (entity_name) -> Store Transformed Data: Pass entity name for doc naming pattern
    #  # The store_customer_data node needs entity_name in its DIRECT input to resolve input_docname_field
    # { "src_node_id": "$graph_state", "dst_node_id": "store_transformed_data", "mappings": [
    #     { "src_field": "entity_name", "dst_field": "entity_name" }
    #   ]
    # },
    # Store Raw Data -> Output Node (Optional): Pass processed paths
    { "src_node_id": "store_raw_data", "dst_node_id": "output_node", "mappings": [
        { "src_field": "paths_processed", "dst_field": "raw_data_paths" }
      ]
    },
    #  # Store Transformed Data -> Output Node: Pass processed paths
    # { "src_node_id": "store_transformed_data", "dst_node_id": "output_node", "mappings": [
    #     { "src_field": "paths_processed", "dst_field": "transformed_data_paths" }
    #   ]
    # },
     # State -> Output Node: Pass entity name for reference
    { "src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
        { "src_field": "entity_name", "dst_field": "entity_name_processed" }
      ]
    }
  ],

  # --- Define Start and End ---
  "input_node_id": "input_node",
  "output_node_id": "output_node",

#   # --- Optional Metadata ---
#   "metadata": {
#      "description": "Workflow to scrape LinkedIn profile and posts, store raw data, attempt transformation, and store transformed data.",
#      "state_reducers": {
#        # Default reducer is 'replace', which is suitable for entity_name stored once.
#        "entity_name": { "reducer_type": "replace" }
#      }
#   }
}
