import json
import asyncio
from typing import List, Optional, Dict, Any, Literal
from functools import partial

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

from kiwi_client.workflows.document_models.customer_docs import (
    LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE,
    LINKEDIN_PROFILE_DOCNAME,
    LINKEDIN_POST_DOCNAME,
    LINKEDIN_PROFILE_RAW_DOCNAME,
    LINKEDIN_POST_RAW_DOCNAME,
)

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
              "entity_username": { "type": "str", "required": True, "description": "Name of the entity (used for saving doc names)." },
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
                  "input_namespace_field_pattern": LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE, 
                  "input_namespace_field": "entity_username",
                  "static_docname": LINKEDIN_PROFILE_RAW_DOCNAME,
              }
            }
          },
          # Config 2: Store Raw Posts
          {
            "input_field_path": "scraping_results.scraped_posts_job",
            "target_path": {
              "filename_config": {
                "input_namespace_field_pattern": LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE, 
                  "input_namespace_field": "entity_username",
                  "static_docname": LINKEDIN_POST_RAW_DOCNAME,
              }
            }
          }
        ]
      }
      # Input fields expected: scraping_results (from scrape_entity), entity_name (from $graph_state)
      # Output: passthrough_data, paths_processed
    },



    # --- 5. Filter Posts Data ---
    "filter_scraped_data": {
      "node_id": "filter_scraped_data",
      "node_name": "filter_data",
      "node_config": {
        "non_target_fields_mode": "deny",
        "targets": [
            # PROFILE FILTERING
            # Keep username field
          {
            "filter_target": "data_to_filter.scraped_profile_job.username",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.username", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          # Keep firstName field
          {
            "filter_target": "data_to_filter.scraped_profile_job.firstName",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.firstName", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          # Keep lastName field
          {
            "filter_target": "data_to_filter.scraped_profile_job.lastName",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.lastName", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          # Keep summary field
          {
            "filter_target": "data_to_filter.scraped_profile_job.summary",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.summary", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          # Keep headline field
          {
            "filter_target": "data_to_filter.scraped_profile_job.headline",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.headline", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          # Keep geo fields
          {
            "filter_target": "data_to_filter.scraped_profile_job.geo",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.geo", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          # Keep geo.country field
          {
            "filter_target": "data_to_filter.scraped_profile_job.geo.country",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.geo.country", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          # Keep geo.city field
          {
            "filter_target": "data_to_filter.scraped_profile_job.geo.city",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.geo.city", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          # Keep geo.full field
          {
            "filter_target": "data_to_filter.scraped_profile_job.geo.full",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.geo.full", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          # Keep educations array
          {
            "filter_target": "data_to_filter.scraped_profile_job.educations",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.educations", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          # Education nested fields
          # Start date fields
          {
            "filter_target": "data_to_filter.scraped_profile_job.educations.start",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.educations.start", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_profile_job.educations.start.year",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.educations.start.year", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_profile_job.educations.start.month",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.educations.start.month", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_profile_job.educations.start.day",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.educations.start.day", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          # End date fields
          {
            "filter_target": "data_to_filter.scraped_profile_job.educations.end",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.educations.end", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_profile_job.educations.end.year",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.educations.end.year", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_profile_job.educations.end.month",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.educations.end.month", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_profile_job.educations.end.day",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.educations.end.day", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          # Other education fields
          {
            "filter_target": "data_to_filter.scraped_profile_job.educations.fieldOfStudy",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.educations.fieldOfStudy", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_profile_job.educations.degree",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.educations.degree", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_profile_job.educations.grade",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.educations.grade", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_profile_job.educations.schoolName",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.educations.schoolName", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_profile_job.educations.description",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.educations.description", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          # Keep positions array
          {
            "filter_target": "data_to_filter.scraped_profile_job.position",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.position", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          # Position nested fields
          {
            "filter_target": "data_to_filter.scraped_profile_job.position.companyName",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.position.companyName", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_profile_job.position.companyIndustry",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.position.companyIndustry", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_profile_job.position.location",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.position.location", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_profile_job.position.description",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_profile_job.position.description", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          # For each post in the list, keep only specific fields
          {
            "filter_target": "data_to_filter.scraped_posts_job.text",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_posts_job.text", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_posts_job.reposted",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_posts_job.reposted", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_posts_job.isBrandPartnership",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_posts_job.isBrandPartnership", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_posts_job.postedDate",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_posts_job.postedDate", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_posts_job.postedDateTimestamp",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_posts_job.postedDateTimestamp", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_posts_job.totalReactionCount",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_posts_job.totalReactionCount", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_posts_job.commentsCount",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_posts_job.commentsCount", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          },
          {
            "filter_target": "data_to_filter.scraped_posts_job.repostsCount",
            "filter_mode": "allow",
            "condition_groups": [
              {
                "conditions": [
                  { "field": "data_to_filter.scraped_posts_job.repostsCount", "operator": "is_not_empty" }
                ],
                "logical_operator": "and"
              }
            ],
            "group_logical_operator": "and"
          }
        ]
      }
    },

    # --- 6. Store Filtered Data ---
    "store_filtered_data": {
      "node_id": "store_filtered_data",
      "node_name": "store_customer_data",
      # "enable_node_fan_in": True,
      "node_config": {
        # Use upsert unversioned for simplicity in this example
        "global_versioning": { "is_versioned": False, "operation": "upsert" },
        "global_is_shared": False, # Assume user-specific storage
        "store_configs": [
          # Config 1: Store Filtered Profile
          {
            "input_field_path": "filtered_data.data_to_filter.scraped_profile_job",
            "target_path": {
              "filename_config": {
                  "input_namespace_field_pattern": LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE, 
                  "input_namespace_field": "entity_username",
                  "static_docname": LINKEDIN_PROFILE_DOCNAME,
              }
            }
          },
          # Config 2: Store Filtered Posts
          {
            "input_field_path": "filtered_data.data_to_filter.scraped_posts_job",
            "target_path": {
              "filename_config": {
                "input_namespace_field_pattern": LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE, 
                  "input_namespace_field": "entity_username",
                  "static_docname": LINKEDIN_POST_DOCNAME,
              }
            }
          }
        ]
      }
    },

    # --- 7. Output Node ---
    "output_node": {
      "node_id": "output_node",
      "node_name": "output_node",
      "node_config": {},
    }
  },

  # --- Edges Defining Data Flow ---
  "edges": [
    # Input -> State: Store entity_name globally for use in doc names
    { "src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "entity_username", "dst_field": "entity_username" }
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
    { "src_node_id": "scrape_entity", "dst_node_id": "$graph_state", "mappings": [
        { "src_field": "execution_summary", "dst_field": "scraping_status_summary" },
      ]
    },
    # State (entity_name) -> Store Raw Data: Pass entity name for doc naming pattern
    { "src_node_id": "$graph_state", "dst_node_id": "store_raw_data", "mappings": [
        { "src_field": "entity_username", "dst_field": "entity_username" }
      ]
    },
    # Scrape Entity -> Filter Posts Data: Pass posts data for filtering
    { "src_node_id": "scrape_entity", "dst_node_id": "filter_scraped_data", "mappings": [
        { "src_field": "scraping_results", "dst_field": "data_to_filter" }
      ]
    },

    # Filter Posts Data -> Store Filtered Data: Pass filtered posts data
    { "src_node_id": "filter_scraped_data", "dst_node_id": "store_filtered_data", "mappings": [
        { "src_field": "filtered_data", "dst_field": "filtered_data" }
      ]
    },
    # State (entity_name) -> Store Filtered Data: Pass entity name for doc naming pattern
    { "src_node_id": "$graph_state", "dst_node_id": "store_filtered_data", "mappings": [
        { "src_field": "entity_username", "dst_field": "entity_username" }
      ]
    },
    # Store Raw Data -> Output Node: Pass processed paths
    { "src_node_id": "store_raw_data", "dst_node_id": "output_node", "mappings": [
        { "src_field": "paths_processed", "dst_field": "raw_data_paths" }
      ]
    },
    # Store Filtered Data -> Output Node: Pass processed paths
    { "src_node_id": "store_filtered_data", "dst_node_id": "output_node", "mappings": [
        { "src_field": "paths_processed", "dst_field": "filtered_data_paths" }
      ]
    },
    # State -> Output Node: Pass entity name for reference
    { "src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
        { "src_field": "entity_username", "dst_field": "entity_username" },
        { "src_field": "scraping_status_summary", "dst_field": "scraping_status_summary" },
      ]
    }
  ],

  # --- Define Start and End ---
  "input_node_id": "input_node",
  "output_node_id": "output_node",
}


# --- Test Execution Logic ---

import asyncio
import json
# import httpx # Implicitly used by AuthenticatedClient - remove if not directly used
import logging
# import time # Remove if not directly used
from typing import Dict, Any, Optional

# Import necessary components
# Assuming run_workflow_test is now in test_run_workflow_client based on other files

from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    CleanupDocInfo
)
from kiwi_client.test_config import CLIENT_LOG_LEVEL
# Schemas are still needed
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus


# Setup logger (could also configure externally)
logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)


async def validate_linkedin_scraping_output(outputs: Optional[Dict[str, Any]], linkedin_scraping_inputs: Dict[str, Any]) -> bool:
    """
    Custom validation function for the LinkedIn scraping workflow outputs.

    Args:
        outputs: The dictionary of final outputs from the workflow run.

    Returns:
        True if the outputs are valid, False otherwise.

    Raises:
        AssertionError: If the outputs are None or do not contain the expected keys/values.
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating LinkedIn scraping workflow outputs...")

    # Check for expected keys based on the workflow's output_node edges
    assert 'raw_data_paths' in outputs, "Validation Failed: 'raw_data_paths' key missing in outputs."
    assert 'filtered_data_paths' in outputs, "Validation Failed: 'filtered_data_paths' key missing in outputs."
    assert "entity_username" in outputs, "Validation Failed: \"entity_username\" key missing in outputs."

    # Check if the processed entity name matches the input
    assert outputs["entity_username"] == linkedin_scraping_inputs["entity_username"], \
        f"Validation Failed: Expected entity_name '{linkedin_scraping_inputs["entity_username"]}' but got '{outputs["entity_username"]}'."

    # Optional: Check structure of raw_data_paths if needed
    assert isinstance(outputs['raw_data_paths'], list), "Validation Failed: 'raw_data_paths' should be a list."
    assert isinstance(outputs['filtered_data_paths'], list), "Validation Failed: 'filtered_data_paths' should be a list."
    
    # Example: Check if expected filenames are present (adjust patterns based on workflow)
    expected_profile_path_part = linkedin_scraping_inputs["entity_username"]
    expected_posts_path_part = linkedin_scraping_inputs["entity_username"]
    found_profile = any(expected_profile_path_part in str(p) for p in outputs['raw_data_paths'])
    found_posts = any(expected_posts_path_part in str(p) for p in outputs['raw_data_paths'])
    found_filtered_profile = any(expected_profile_path_part in str(p) for p in outputs['filtered_data_paths'])
    found_filtered_posts = any(expected_posts_path_part in str(p) for p in outputs['filtered_data_paths'])
    
    assert found_profile, f"Validation Failed: Expected profile path containing '{expected_profile_path_part}' not found in {outputs['raw_data_paths']}."
    assert found_posts, f"Validation Failed: Expected posts path containing '{expected_posts_path_part}' not found in {outputs['raw_data_paths']}."
    assert found_filtered_profile, f"Validation Failed: Expected filtered profile path containing '{expected_profile_path_part}' not found in {outputs['filtered_data_paths']}."
    assert found_filtered_posts, f"Validation Failed: Expected filtered posts path containing '{expected_posts_path_part}' not found in {outputs['filtered_data_paths']}."

    logger.info(f"   Found 'raw_data_paths': {outputs.get('raw_data_paths')}")
    logger.info(f"   Found 'filtered_data_paths': {outputs.get('filtered_data_paths')}")
    logger.info(f"   Found 'entity_username': {outputs.get("entity_username")} (Matches Input: ✓)")
    logger.info("✓ Output structure and content validation passed.")
    return True


async def main_test_linkedin_scraping():
    """
    Tests the LinkedIn Scraping Workflow using the run_workflow_test helper function.
    Includes cleanup for generated documents and output validation.
    """
    # --- Inputs for the LinkedIn Scraping Workflow ---
    # These inputs match the 'input_node' dynamic_output_schema
    LINKEDIN_SCRAPING_WORKFLOW_INPUTS = {
        # Replace with a valid LinkedIn profile URL for testing
        "entity_url": "https://www.linkedin.com/in/sytalal/",
        "entity_username": "sytalal", # Used for document naming in the workflow
    }
    test_name = "LinkedIn Scraping Test via Helper"
    print(f"--- Starting {test_name} --- ")

    entity_name = LINKEDIN_SCRAPING_WORKFLOW_INPUTS["entity_username"]

    # Define documents created by the workflow for cleanup
    profile_cleanup_doc: CleanupDocInfo = {
        'namespace': LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE,
        'docname': f"profile_{entity_name}", # Docname pattern from the workflow
        'is_shared': False, # Matches store_raw_data node config
        'is_versioned': False, # Matches store_raw_data node config
        'is_system_entity': False
    }
    posts_cleanup_doc: CleanupDocInfo = {
        'namespace': LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE,
        'docname': f"posts_{entity_name}", # Docname pattern from the workflow
        'is_shared': False, # Matches store_raw_data node config
        'is_versioned': False, # Matches store_raw_data node config
        'is_system_entity': False
    }

    # Execute the test using the reusable helper function
    # No setup_docs needed for this workflow
    # No hitl_inputs needed for this workflow
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=LINKEDIN_SCRAPING_WORKFLOW_INPUTS,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=None, # No HITL steps in this workflow
        setup_docs=[], # No prerequisite documents to set up
        # Add the documents created by the workflow to the cleanup list
        # cleanup_docs=[profile_cleanup_doc, posts_cleanup_doc],
        # Pass the custom validation function
        validate_output_func=partial(validate_linkedin_scraping_output, linkedin_scraping_inputs=LINKEDIN_SCRAPING_WORKFLOW_INPUTS),
        stream_intermediate_results=True, # Keep streaming enabled
        poll_interval_sec=3,
        timeout_sec=300 # Keep timeout relatively high for scraping
    )

    print(f"\n--- {test_name} Finished --- ")


if __name__ == "__main__":
    # Ensure API server is running and config (.env) is correct
    # Run with: PYTHONPATH=. python standalone_test_client/kiwi_client/workflows/test_linkedin_scraping_workflow.py
    print("="*50)
    print("Executing LinkedIn Scraping Workflow Test via Helper")
    print("="*50)

    # Handle potential nested asyncio loop issues
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        print("   Async event loop already running. Adding task...")
        # Schedule the task in the existing loop
        tsk = loop.create_task(main_test_linkedin_scraping())
        # Note: In a non-interactive script, you might need loop.run_until_complete(tsk) if called from sync code.
    else:
        print("   Starting new async event loop...")
        asyncio.run(main_test_linkedin_scraping())

    print("\nRun this script from the project root directory using:")
    print("PYTHONPATH=. python standalone_test_client/kiwi_client/workflows/test_linkedin_scraping_workflow.py")
