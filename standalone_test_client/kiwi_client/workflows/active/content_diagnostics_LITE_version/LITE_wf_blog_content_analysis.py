"""
Blog Content Analysis Workflow - Sales Funnel Stage Classification

This workflow analyzes blog content posts by:
1. Loading raw content posts
2. Batching posts into groups of 30
3. Classifying posts into sales funnel stages
4. Grouping posts by funnel stage
5. Analyzing each funnel stage group
6. Generating a comprehensive report

Input: company_name (company/blog identifier)
Output: Structured analysis report by sales funnel stage
"""



"""
1. LLM-Powered Content Intelligence (High Impact)

E-E-A-T Analysis: Evaluate expertise, authority, and trust signals
Content Quality Scoring: Readability, clarity, and professional tone
Question-Answer Extraction: Perfect for AEO/voice search
Entity Recognition: Identify people, products, topics for knowledge graphs
Content Intent Classification: Informational vs. transactional

FAQ Detection ❌

What: Detecting FAQ sections
Why Low Accuracy: Relies on text patterns that vary widely across sites
Issues:

Text patterns like "FAQ", "Q:", "A:" can appear in non-FAQ contexts
Many sites use different formats (accordions, schema markup only, etc.)
False positives from blog content discussing FAQs


just analyse if this is present for not

Table of Contents Detection ⚠️

Related Topics/Articles ❌ - 

Schema Markup Types

8. Logical Flow Analysis and readability

"""

from kiwi_client.workflows.active.document_models.customer_docs import (
    LITE_BLOG_CONTENT_ANALYSIS_DOCNAME,
    LITE_BLOG_CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
)

from kiwi_client.workflows.active.content_diagnostics_LITE_version.llm_inputs.blog_content_analysis import (
    BATCH_CLASSIFICATION_SCHEMA,
    FUNNEL_STAGE_ANALYSIS_SCHEMA,
    POST_CLASSIFICATION_USER_PROMPT_TEMPLATE,
    POST_CLASSIFICATION_SYSTEM_PROMPT_TEMPLATE,
    FUNNEL_STAGE_ANALYSIS_USER_PROMPT_TEMPLATE,
    FUNNEL_STAGE_ANALYSIS_SYSTEM_PROMPT_TEMPLATE,
)

import json
import asyncio
from typing import List, Optional, Dict, Any, Literal

# --- Workflow Constants ---
LLM_PROVIDER = "openai"
CLASSIFICATION_MODEL = "gpt-5-mini"
ANALYSIS_MODEL = "gpt-5"
LLM_TEMPERATURE = 0.5
LLM_MAX_TOKENS_CLASSIFY = 20000
LLM_MAX_TOKENS_ANALYSIS = 20000

POST_BATCH_SIZE = 10
POST_BATCH_SIZE_ANALYSIS = 20



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
                    "company_name": {
                        "type": "str", 
                        "required": True, 
                        "description": "Name of the company/blog entity whose content is to be analyzed."
                    },
                    "funnel_stages_input": {
                        "type": "list",
                        "required": False,
                        "default": [
    {"stage_id": "awareness", "stage_name": "Awareness", "stage_description": "Top of funnel - building brand awareness"},
    {"stage_id": "consideration", "stage_name": "Consideration", "stage_description": "Middle of funnel - evaluating solutions"},
    {"stage_id": "purchase", "stage_name": "Purchase", "stage_description": "Bottom of funnel - ready to buy"},
    {"stage_id": "retention", "stage_name": "Retention", "stage_description": "Post-purchase - customer success"}
],
                        "description": "Optional override list of funnel stages to use for grouping"
                    },
                    "start_urls": {
                        "type": "list",
                        "items_type": "str",
                        "required": True,
                        "description": "List of URLs to start crawling from"
                    },
                    "allowed_domains": {
                        "type": "list",
                        "items_type": "str",
                        "required": False,
                        "description": "Optional list of allowed domains; derived from start_urls if omitted"
                    },
                    "max_urls_per_domain": {
                        "type": "int",
                        "required": False,
                        "default": 100,
                        "description": "Maximum URLs to discover per domain"
                    },
                    "max_processed_urls_per_domain": {
                        "type": "int",
                        "required": False,
                        "default": 100,
                        "description": "Maximum URLs to actually scrape per domain"
                    },
                    "max_crawl_depth": {
                        "type": "int",
                        "required": False,
                        "default": 3,
                        "description": "How deep to follow links from start URLs"
                    },
                    "use_cached_scraping_results": {
                        "type": "bool",
                        "required": False,
                        "default": True,
                        "description": "Whether to use cached results if available"
                    },
                    "cache_lookback_period_days": {
                        "type": "int",
                        "required": False,
                        "default": 7,
                        "description": "How many days back to look for cached results"
                    },
                    "is_shared": {
                        "type": "bool",
                        "required": False,
                        "default": False,
                        "description": "Store data as organization-shared (vs user-specific)"
                    },
                    "include_only_paths": {
                        "type": "list",
                        "items_type": "str",
                        "required": False,
                        "description": "Optional list of paths to include in the analysis"
                    }
                }
            }
        },

        # --- 2. Crawl Blog Posts ---
        "web_crawler": {
            "node_id": "web_crawler",
            "node_name": "crawler_scraper",
            "node_config": {
            }
        },

        # --- 3. Batch Posts ---
        "batch_and_route_posts": {
            "node_id": "batch_and_route_posts",
            "node_name": "map_list_router_node",
            "node_config": {
                "choices": ["construct_classification_prompt"],
                "map_targets": [
                    {
                        "source_path": "raw_posts_data",
                        "destinations": ["construct_classification_prompt"],
                        "batch_size": POST_BATCH_SIZE,
                        "batch_field_name": "post_batch"
                    }
                ]
            }
        },

        # --- 4. Classify Posts per Batch ---
        "construct_classification_prompt": {
            "node_id": "construct_classification_prompt",
            "node_name": "prompt_constructor",
            "private_input_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_mode": True,
            "node_config": {
                "prompt_templates": {
                    "classify_user_prompt": {
                        "id": "classify_user_prompt",
                        "template": POST_CLASSIFICATION_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "posts_batch_json": None
                        },
                        "construct_options": {
                            "posts_batch_json": "post_batch"
                        }
                    },
                    "classify_system_prompt": {
                        "id": "classify_system_prompt",
                        "template": POST_CLASSIFICATION_SYSTEM_PROMPT_TEMPLATE,
                        "variables": {
                        },
                        "construct_options": {}
                    }
                }
            }
        },

        "classify_batch": {
            "node_id": "classify_batch",
            "node_name": "llm",
            "private_input_mode": True,
            "output_private_output_to_central_state": True,
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": CLASSIFICATION_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS_CLASSIFY
                },
                "output_schema": {
                    "schema_definition": BATCH_CLASSIFICATION_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },

        # --- 5. Flatten Classification Results ---
        "flatten_classifications": {
            "node_id": "flatten_classifications",
            "node_name": "merge_aggregate",
            "node_config": {
                "operations": [
                    {
                        "output_field_name": "flat_classifications",
                        "select_paths": ["all_classifications_batches"],
                        "merge_each_object_in_selected_list": True,
                        "merge_strategy": {
                            "map_phase": {
                                "key_mappings": [
                                    {"source_keys": ["posts"], "destination_key": "flat_list"}
                                ],
                                "unspecified_keys_strategy": "ignore"
                            },
                            "reduce_phase": {
                                "default_reducer": "replace_right",
                                "reducers": {
                                    "flat_list": "extend"
                                },
                                "error_strategy": "fail_node"
                            },
                            "post_merge_transformations": {
                                "flat_list": {
                                    "operation_type": "recursive_flatten_list"
                                }
                            }
                        }
                    }
                ]
            }
        },

        # --- 6. Join Classifications to Posts ---
        "join_classifications_to_posts": {
            "node_id": "join_classifications_to_posts",
            "node_name": "data_join_data",
            "node_config": {
                "joins": [
                    {
                        "primary_list_path": "raw_posts_data",
                        "secondary_list_path": "merged_data.flat_classifications.flat_list",
                        "primary_join_key": "url",
                        "secondary_join_key": "post_url",
                        "output_nesting_field": "funnel_classification",
                        "join_type": "one_to_one"
                    }
                ]
            }
        },

        # --- 8. Extract Funnel Stages for Grouping ---
        # Create funnel stage objects to use as primary list for grouping
        "extract_funnel_stages": {
            "node_id": "extract_funnel_stages",
            "node_name": "transform_data",
            "node_config": {
                "mappings": [
                    {
                        "source_path": "funnel_stages_input",
                        "destination_path": "funnel_stages"
                    }
                ]
            }
        },

        # --- 9. Group Posts by Sales Funnel Stage ---
        # Use data_join_data to group posts under their respective funnel stages
        "group_posts_by_funnel_stage": {
            "node_id": "group_posts_by_funnel_stage",
            "node_name": "data_join_data",
            "enable_node_fan_in": True,
            "node_config": {
                "joins": [
                    {
                        "primary_list_path": "transformed_data.funnel_stages",  # List of funnel stage objects
                        "secondary_list_path": "mapped_data.raw_posts_data",    # List of classified posts
                        "primary_join_key": "stage_id",                         # Key in funnel stage object
                        "secondary_join_key": "funnel_classification.sales_funnel_stage",  # Nested key in post
                        "output_nesting_field": "stage_posts",                  # Nest posts under this field
                        "join_type": "one_to_many"
                    }
                ]
            }
        },

        "route_funnel_stage_groups": {
            "node_id": "route_funnel_stage_groups",
            "node_name": "map_list_router_node",
            "node_config": {
                "choices": ["preprocess_stage_group_sort_posts"],
                "map_targets": [
                    {
                        "source_path": "mapped_data.transformed_data.funnel_stages",  # List of funnel stages with posts
                        "destinations": ["preprocess_stage_group_sort_posts"],
                        "batch_size": 1,
                        "batch_field_name": "funnel_stage_group"
                    }
                ]
            }
        },

        # --- 10a. Preprocess Stage Group: Sort posts by updated desc ---
        "preprocess_stage_group_sort_posts": {
            "node_id": "preprocess_stage_group_sort_posts",
            "node_name": "merge_aggregate",
            "private_input_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_mode": True,
            "node_config": {
                "operations": [
                    {
                        "output_field_name": "stage_group",
                        "select_paths": ["funnel_stage_group"],
                        "merge_strategy": {
                            "post_merge_transformations": {
                                "stage_posts": {
                                    "operation_type": "sort_list",
                                    "operand": {"key": "dates.updated", "order": "descending"}
                                }
                            }
                        }
                    }
                ]
            }
        },

        # --- 10b. Preprocess Stage Group: Limit to top 20 posts ---
        "preprocess_stage_group_limit_posts": {
            "node_id": "preprocess_stage_group_limit_posts",
            "node_name": "merge_aggregate",
            "private_input_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_mode": True,
            "node_config": {
                "operations": [
                    {
                        "output_field_name": "stage_group",
                        "select_paths": ["funnel_stage_group.stage_group"],
                        "merge_strategy": {
                            "post_merge_transformations": {
                                "stage_posts": {
                                    "operation_type": "limit_list",
                                    "operand": 20
                                }
                            }
                        }
                    }
                ]
            }
        },
        # --- 10. Route Funnel Stage Groups for Analysis ---
        
        
        # --- 10. Analyze Each Funnel Stage Group ---
        "construct_analysis_prompt": {
            "node_id": "construct_analysis_prompt",
            "node_name": "prompt_constructor",
            "private_input_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_mode": True,
            "node_config": {
                "prompt_templates": {
                    "analyze_user_prompt": {
                        "id": "analyze_user_prompt",
                        "template": FUNNEL_STAGE_ANALYSIS_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "funnel_stage": None,
                            "posts_group_json": None
                            },
                        "construct_options": {
                            "funnel_stage": "funnel_stage_group.stage_group.stage_name",
                            "posts_group_json": "funnel_stage_group.stage_group.stage_posts"
                            }
                    },
                    "analyze_system_prompt": {
                        "id": "analyze_system_prompt",
                        "template": FUNNEL_STAGE_ANALYSIS_SYSTEM_PROMPT_TEMPLATE,
                        "variables": {},
                        "construct_options": {}
                    }
                }
            }
        },

        "analyze_funnel_stage_group": {
            "node_id": "analyze_funnel_stage_group",
            "node_name": "llm",
            "private_input_mode": True,
            "output_private_output_to_central_state": True,
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": ANALYSIS_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS_ANALYSIS,
                    "reasoning_effort_class": "low"
                },
                "output_schema": {
                    "schema_definition": FUNNEL_STAGE_ANALYSIS_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },

        # --- 11. Combine All Analysis Reports ---
        "combine_funnel_reports": {
            "node_id": "combine_funnel_reports",
            "node_name": "transform_data",
            "node_config": {
                "mappings": [
                    {"source_path": "company_name", "destination_path": "final_report_data.company_name"},
                    {"source_path": "all_funnel_stage_reports", "destination_path": "final_report_data.funnel_analysis"}
                ]
            }
        },



        # --- 12. Store Analysis Results ---
        "store_analysis": {
            "node_id": "store_analysis",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {"is_versioned": False, "operation": "upsert"},
                "global_is_shared": False,
                "store_configs": [
                    {
                        "input_field_path": "transformed_data.final_report_data",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": LITE_BLOG_CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "company_name",
                                "static_docname": LITE_BLOG_CONTENT_ANALYSIS_DOCNAME,
                            }
                        }
                    }
                ]
            }
        },



        # --- 14. Output Node ---
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "enable_node_fan_in": True,
            "node_config": {}
        }
    },

    # --- Edges Defining Data Flow ---
    "edges": [
        # Input & Setup
        {"src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"},
            {"src_field": "funnel_stages_input", "dst_field": "funnel_stages_input"}
        ]},
        {"src_node_id": "input_node", "dst_node_id": "web_crawler", "mappings": [
            {"src_field": "start_urls", "dst_field": "start_urls"},
            {"src_field": "allowed_domains", "dst_field": "allowed_domains"},
            {"src_field": "max_urls_per_domain", "dst_field": "max_urls_per_domain"},
            {"src_field": "max_processed_urls_per_domain", "dst_field": "max_processed_urls_per_domain"},
            {"src_field": "max_crawl_depth", "dst_field": "max_crawl_depth"},
            {"src_field": "use_cached_scraping_results", "dst_field": "use_cached_scraping_results"},
            {"src_field": "cache_lookback_period_days", "dst_field": "cache_lookback_period_days"},
            {"src_field": "is_shared", "dst_field": "is_shared"},
            {"src_field": "include_only_paths", "dst_field": "include_only_paths"}
        ]},
        
        # Store posts in state for later joins
        {"src_node_id": "web_crawler", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "scraped_data", "dst_field": "raw_posts_data"},
            {"src_field": "technical_seo_summary", "dst_field": "technical_seo_summary"},
            {"src_field": "robots_analysis", "dst_field": "robots_analysis"}
        ]},
        
        # Batch and classify posts
        {"src_node_id": "web_crawler", "dst_node_id": "batch_and_route_posts", "mappings": [
            {"src_field": "scraped_data", "dst_field": "raw_posts_data"}
        ]},
        {"src_node_id": "batch_and_route_posts", "dst_node_id": "construct_classification_prompt", "mappings": []},
        {"src_node_id": "construct_classification_prompt", "dst_node_id": "classify_batch", "mappings": [
            {"src_field": "classify_user_prompt", "dst_field": "user_prompt"},
            {"src_field": "classify_system_prompt", "dst_field": "system_prompt"}
        ]},
        
        # Message history for classification

        {"src_node_id": "classify_batch", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "all_classifications_batches"}        ]},
        
        # Flatten and join classifications
        {"src_node_id": "classify_batch", "dst_node_id": "flatten_classifications", "mappings": []},
        {"src_node_id": "$graph_state", "dst_node_id": "flatten_classifications", "mappings": [
            {"src_field": "all_classifications_batches", "dst_field": "all_classifications_batches"}
        ]},
        {"src_node_id": "flatten_classifications", "dst_node_id": "join_classifications_to_posts", "mappings": [
            {"src_field": "merged_data", "dst_field": "merged_data"}
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "join_classifications_to_posts", "mappings": [
            {"src_field": "raw_posts_data", "dst_field": "raw_posts_data"}
        ]},


        
        # Store mapped data in state for later use
        {"src_node_id": "join_classifications_to_posts", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "mapped_data", "dst_field": "mapped_data_flat_list"}
        ]},
        
        # Extract funnel stages
        {"src_node_id": "join_classifications_to_posts", "dst_node_id": "extract_funnel_stages", "mappings": []},
        {"src_node_id": "$graph_state", "dst_node_id": "extract_funnel_stages", "mappings": [
            {"src_field": "funnel_stages_input", "dst_field": "funnel_stages_input"}
        ]},
        
        # Group posts by funnel stage
        {"src_node_id": "extract_funnel_stages", "dst_node_id": "group_posts_by_funnel_stage", "mappings": [
            {"src_field": "transformed_data", "dst_field": "transformed_data"}
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "group_posts_by_funnel_stage", "mappings": [
            {"src_field": "mapped_data_flat_list", "dst_field": "mapped_data"}
        ]},
        
        # Route and analyze funnel stage groups
        {"src_node_id": "group_posts_by_funnel_stage", "dst_node_id": "route_funnel_stage_groups", "mappings": [
            {"src_field": "mapped_data", "dst_field": "mapped_data"}
        ]},

        {"src_node_id": "route_funnel_stage_groups", "dst_node_id": "preprocess_stage_group_sort_posts", "mappings": []},
        {"src_node_id": "preprocess_stage_group_sort_posts", "dst_node_id": "preprocess_stage_group_limit_posts", "mappings": [
            {"src_field": "merged_data", "dst_field": "funnel_stage_group"}
        ]},

        {"src_node_id": "preprocess_stage_group_limit_posts", "dst_node_id": "construct_analysis_prompt", "mappings": [
            {"src_field": "merged_data", "dst_field": "funnel_stage_group"}
        ]},

        {"src_node_id": "construct_analysis_prompt", "dst_node_id": "analyze_funnel_stage_group", "mappings": [
            {"src_field": "analyze_user_prompt", "dst_field": "user_prompt"},
            {"src_field": "analyze_system_prompt", "dst_field": "system_prompt"}
        ]},
        

        {"src_node_id": "analyze_funnel_stage_group", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "all_funnel_stage_reports"}        ]},
        
        # Combine reports
        {"src_node_id": "analyze_funnel_stage_group", "dst_node_id": "combine_funnel_reports", "mappings": []},
        {"src_node_id": "$graph_state", "dst_node_id": "combine_funnel_reports", "mappings": [
            {"src_field": "all_funnel_stage_reports", "dst_field": "all_funnel_stage_reports"},
            {"src_field": "company_name", "dst_field": "company_name"}
        ]},
        
        # Store results
        {"src_node_id": "combine_funnel_reports", "dst_node_id": "store_analysis", "mappings": [
            {"src_field": "transformed_data", "dst_field": "transformed_data"}
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "store_analysis", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"}
        ]},

        # Output
        {"src_node_id": "store_analysis", "dst_node_id": "$graph_state", "mappings": []},
        {"src_node_id": "store_analysis", "dst_node_id": "output_node", "mappings": [
            {"src_field": "passthrough_data", "dst_field": "passthrough_data"}
        ]}
    ],

    # Define start and end
    "input_node_id": "input_node",
    "output_node_id": "output_node",

    # State reducers
    "metadata": {
        "$graph_state": {
            "reducer": {
                "all_classifications_batches": "collect_values",
                "all_funnel_stage_reports": "collect_values"
            }
        }
    }
}

# --- Test Execution Logic ---
import logging
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

logger = logging.getLogger(__name__)

# Example Input
TEST_INPUTS = {
    "company_name": "retool",
    "include_only_paths": ["/blog"],
    "start_urls": "https://retool.com"
}

async def validate_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """Custom validation function for the workflow outputs."""
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating blog content analysis workflow outputs...")
    
    assert 'company_name' in outputs, "Validation Failed: 'company_name' key missing."
    assert outputs['company_name'] == TEST_INPUTS['company_name'], "Validation Failed: Entity name mismatch."
    
    logger.info(f"   Company name: {outputs.get('company_name')}")
    logger.info("✓ Output structure and content validation passed.")
    return True

async def main_test_blog_analysis():
    test_name = "Blog Content Analysis Workflow Test - Sales Funnel Classification"
    print(f"--- Starting {test_name} ---")
    
    # Prepare inputs for crawler: ensure start_urls is a list and derive allowed_domains if missing
    prepared_inputs = dict(TEST_INPUTS)
    start_urls_val = prepared_inputs.get("start_urls")
    if isinstance(start_urls_val, str):
        prepared_inputs["start_urls"] = [start_urls_val]
    elif isinstance(start_urls_val, list):
        prepared_inputs["start_urls"] = start_urls_val
    else:
        raise AssertionError("Invalid 'start_urls' provided. Expected str or List[str].")

    if not prepared_inputs.get("allowed_domains"):
        try:
            from urllib.parse import urlparse
            prepared_inputs["allowed_domains"] = list({urlparse(url).netloc for url in prepared_inputs["start_urls"] if url})
        except Exception as e:
            logger.warning(f"Could not derive allowed_domains from start_urls: {e}")

    print("\n--- Running Workflow Test ---")
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=prepared_inputs,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        setup_docs=None,
        cleanup_docs=None,
        validate_output_func=validate_output,
        stream_intermediate_results=True,
        poll_interval_sec=5,
        timeout_sec=1800
    )

if __name__ == "__main__":
    print("="*50)
    print("Blog Content Analysis Workflow - Sales Funnel Classification")
    print("="*50)
    logging.basicConfig(level=logging.INFO)
    
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        print("Async event loop already running. Scheduling task...")
        loop.create_task(main_test_blog_analysis())
    else:
        print("Starting new async event loop...")
        asyncio.run(main_test_blog_analysis())