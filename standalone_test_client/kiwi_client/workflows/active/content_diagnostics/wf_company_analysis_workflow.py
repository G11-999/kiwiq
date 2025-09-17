"""
Company Analysis Workflow - Internal Document Intelligence & Reddit Market Research

This workflow analyzes internal company documents to extract comprehensive business
intelligence, then conducts Reddit research to understand market needs and opportunities,
and finally generates strategic content pillars that align business goals with market demand.

Workflow Steps:
1. Load all company internal documents from uploaded files
2. Load company goals document 
3. Batch documents and analyze with LLM to extract company information
4. Synthesize analysis into unique comprehensive report
5. Generate Reddit search queries based on company analysis
6. Execute Reddit searches using Perplexity to gather market insights
7. Synthesize Reddit insights into market intelligence report with demand metrics
8. Generate strategic content pillars merging company strengths with market needs

Input: company_name
Output: Company analysis, market insights with demand indicators, and strategic content pillars
"""

from kiwi_client.workflows.active.document_models.customer_docs import (
    BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE,
    BLOG_COMPANY_DOCNAME,
    BLOG_COMPANY_NAMESPACE_TEMPLATE,
    BLOG_COMPANY_ANALYSIS_DOCNAME,
    BLOG_COMPANY_ANALYSIS_NAMESPACE_TEMPLATE
)

from kiwi_client.workflows.active.content_diagnostics.llm_inputs.company_analysis import (
    # Document Analysis
    DOCUMENT_ANALYSIS_SYSTEM_PROMPT,
    DOCUMENT_ANALYSIS_USER_PROMPT_TEMPLATE,
    DOCUMENT_ANALYSIS_OUTPUT_SCHEMA,
    # Unique Report
    UNIQUE_REPORT_SYSTEM_PROMPT,
    UNIQUE_REPORT_USER_PROMPT_TEMPLATE,
    UNIQUE_REPORT_OUTPUT_SCHEMA,
    # Reddit Query Generation
    REDDIT_QUERY_SYSTEM_PROMPT,
    REDDIT_QUERY_USER_PROMPT_TEMPLATE,
    REDDIT_QUERY_OUTPUT_SCHEMA,
    # Reddit Research
    REDDIT_RESEARCH_SYSTEM_PROMPT,
    REDDIT_RESEARCH_USER_PROMPT_TEMPLATE,
    REDDIT_RESEARCH_OUTPUT_SCHEMA,
    # Final Insights with Content Pillars
    FINAL_INSIGHTS_SYSTEM_PROMPT,
    FINAL_INSIGHTS_USER_PROMPT_TEMPLATE,
    FINAL_INSIGHTS_OUTPUT_SCHEMA,
    # Perplexity Company Research
    PERPLEXITY_COMPANY_RESEARCH_SYSTEM_PROMPT,
    PERPLEXITY_COMPANY_RESEARCH_USER_PROMPT_TEMPLATE,
    PERPLEXITY_COMPANY_RESEARCH_OUTPUT_SCHEMA
)

import json
import asyncio
from typing import List, Optional, Dict, Any

# --- Workflow Constants ---
# OpenAI Models
OPENAI_PROVIDER = "openai"
OPENAI_MODEL = "gpt-5"
OPENAI_TEMPERATURE = 0.5
OPENAI_MAX_TOKENS = 12000

# Perplexity Models for Reddit Research
PERPLEXITY_PROVIDER = "perplexity"
PERPLEXITY_MODEL = "sonar"
PERPLEXITY_TEMPERATURE = 0.3
PERPLEXITY_MAX_TOKENS = 6000

# Batching Configuration
DOCUMENT_BATCH_SIZE = 5

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
                        "description": "Name of the company whose documents will be analyzed"
                    },
                    "scraped_data": {
                        "type": "list",
                        "required": True,
                        "description": "Web scraped data from the company's website"
                    },
                    "has_insufficient_blog_and_page_count": {
                        "type": "bool",
                        "required": True,
                        "description": "Whether the company has insufficient blog and page count"
                    }
                }
            }
        },

        # --- 2. Load All Company Documents ---
        "load_company_documents": {
            "node_id": "load_company_documents",
            "node_name": "load_multiple_customer_data",
            "node_config": {
                "namespace_pattern": BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE,
                "namespace_pattern_input_path": "company_name",
                "include_shared": False,
                "include_user_specific": True,
                "include_system_entities": False,
                "limit": 200,  # Max documents to load
                "output_field_name": "company_documents",
                "global_load_active_version_only": True,
                "global_schema_options": {"load_schema": False}
            }
        },

        # --- 3. Load Company Goals Document ---
        "load_company_context": {
            "node_id": "load_company_context",
            "node_name": "load_customer_data",
            "node_config": {
                "load_paths": [
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": BLOG_COMPANY_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": BLOG_COMPANY_DOCNAME
                        },
                        "output_field_name": "company_context"
                    }
                ]
            }
        },

        # --- 3.5. Route Based on Content Sufficiency ---
        "route_content_path": {
            "node_id": "route_content_path",
            "node_name": "router_node",
            "node_config": {
                "choices": ["merge_document_lists", "construct_perplexity_research_prompt"],
                "allow_multiple": False,
                "default_choice": "merge_document_lists",
                "choices_with_conditions": [
                    {
                        "choice_id": "construct_perplexity_research_prompt",
                        "input_path": "has_insufficient_blog_and_page_count",
                        "target_value": False
                    },
                    {
                        "choice_id": "merge_document_lists",
                        "input_path": "has_insufficient_blog_and_page_count",
                        "target_value": True
                    }
                ]
            }
        },

        # --- 3.6. Merge Document Lists (for insufficient content path) ---
        "merge_document_lists": {
            "node_id": "merge_document_lists",
            "node_name": "merge_aggregate",
            "node_config": {
                "operations": [
                    {
                        "output_field_name": "all_documnents",
                        "select_paths": [
                            "company_documents",  # List from load_company_documents
                            "scraped_data"    # List from input (if provided)
                        ],
                        "merge_each_object_in_selected_list": False,  # Treat lists as atomic items
                        "merge_strategy": {
                            "reduce_phase": {
                                "default_reducer": "combine_in_list"  # Combine both lists
                            },
                            "post_merge_transformations": {
                                "flatten_all": {
                                    "operation_type": "recursive_flatten_list"  # Flatten [[docs1], [docs2]] to [docs1, docs2]
                                }
                            }
                        }
                    }
                ]
            }
        },

        # --- 3.7. Construct Perplexity Research Prompt (for sufficient content path) ---
        "construct_perplexity_research_prompt": {
            "node_id": "construct_perplexity_research_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "perplexity_user_prompt": {
                        "id": "perplexity_user_prompt",
                        "template": PERPLEXITY_COMPANY_RESEARCH_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "company_context": None
                        },
                        "construct_options": {
                            "company_context": "company_context"
                        }
                    },
                    "perplexity_system_prompt": {
                        "id": "perplexity_system_prompt",
                        "template": PERPLEXITY_COMPANY_RESEARCH_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },

        # --- 3.8. Execute Perplexity Research (for sufficient content path) ---
        "execute_perplexity_research": {
            "node_id": "execute_perplexity_research",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": PERPLEXITY_PROVIDER,
                        "model": PERPLEXITY_MODEL
                    },
                    "temperature": PERPLEXITY_TEMPERATURE,
                    "max_tokens": PERPLEXITY_MAX_TOKENS
                },
                "output_schema": {
                    "schema_definition": PERPLEXITY_COMPANY_RESEARCH_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },

        # --- 4a. Batch Documents for Insufficient Content Path ---
        "batch_merged_documents": {
            "node_id": "batch_merged_documents",
            "node_name": "map_list_router_node",
            "node_config": {
                "choices": ["construct_analysis_prompt"],
                "map_targets": [
                    {
                        "source_path": "merged_data.all_documnents",
                        "destinations": ["construct_analysis_prompt"],
                        "batch_size": DOCUMENT_BATCH_SIZE,
                        "batch_field_name": "documents_batch"
                    }
                ]
            }
        },

        # --- 4b. Batch Documents for Sufficient Content Path ---
        "batch_company_documents": {
            "node_id": "batch_company_documents",
            "node_name": "map_list_router_node",
            "node_config": {
                "choices": ["construct_analysis_prompt"],
                "map_targets": [
                    {
                        "source_path": "company_documents",
                        "destinations": ["construct_analysis_prompt"],
                        "batch_size": DOCUMENT_BATCH_SIZE,
                        "batch_field_name": "documents_batch"
                    }
                ]
            }
        },

        # --- 5. Construct Document Analysis Prompt ---
        "construct_analysis_prompt": {
            "node_id": "construct_analysis_prompt",
            "node_name": "prompt_constructor",
            "private_input_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_mode": True,
            "node_config": {
                "prompt_templates": {
                    "analysis_user_prompt": {
                        "id": "analysis_user_prompt",
                        "template": DOCUMENT_ANALYSIS_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "documents_batch": None,
                            "company_goals": None
                        },
                        "construct_options": {
                            "documents_batch": "documents_batch",
                            "company_goals": "company_context"
                        }
                    },
                    "analysis_system_prompt": {
                        "id": "analysis_system_prompt",
                        "template": DOCUMENT_ANALYSIS_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },

        # --- 6. Analyze Document Batch with LLM ---
        "analyze_documents": {
            "node_id": "analyze_documents",
            "node_name": "llm",
            "private_input_mode": True,
            "output_private_output_to_central_state": True,
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": OPENAI_PROVIDER,
                        "model": OPENAI_MODEL
                    },
                    "temperature": OPENAI_TEMPERATURE,
                    "max_tokens": OPENAI_MAX_TOKENS
                },
                "output_schema": {
                    "schema_definition": DOCUMENT_ANALYSIS_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },

        # --- 7. Construct Unique Report Prompt ---
        "construct_unique_report_prompt": {
            "node_id": "construct_unique_report_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
            "node_config": {
                "prompt_templates": {
                    "unique_report_user_prompt": {
                        "id": "unique_report_user_prompt",
                        "template": UNIQUE_REPORT_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "collected_analyses": None,
                            "perplexity_research_section": None
                        },
                        "construct_options": {
                            "collected_analyses": "all_document_analyses",
                            "perplexity_research_section": "perplexity_research_section"
                        }
                    },
                    "unique_report_system_prompt": {
                        "id": "unique_report_system_prompt",
                        "template": UNIQUE_REPORT_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },

        # --- 8. Generate Unique Report ---
        "generate_unique_report": {
            "node_id": "generate_unique_report",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": OPENAI_PROVIDER,
                        "model": OPENAI_MODEL
                    },
                    "temperature": OPENAI_TEMPERATURE,
                    "max_tokens": OPENAI_MAX_TOKENS,
                    "reasoning_effort_class": "low"
                },
                "output_schema": {
                    "schema_definition": UNIQUE_REPORT_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },

        # --- 9. Construct Reddit Query Generation Prompt ---
        "construct_query_generation_prompt": {
            "node_id": "construct_query_generation_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "query_gen_user_prompt": {
                        "id": "query_gen_user_prompt",
                        "template": REDDIT_QUERY_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "company_report": None,
                        },
                        "construct_options": {
                            "company_report": "structured_output"
                        }
                    },
                    "query_gen_system_prompt": {
                        "id": "query_gen_system_prompt",
                        "template": REDDIT_QUERY_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },

        # --- 10. Generate Reddit Queries ---
        "generate_reddit_queries": {
            "node_id": "generate_reddit_queries",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": OPENAI_PROVIDER,
                        "model": OPENAI_MODEL
                    },
                    "temperature": 0.7,  # Higher for creative query generation
                    "max_tokens": OPENAI_MAX_TOKENS,
                    "reasoning_effort_class": "low"
                },
                "output_schema": {
                    "schema_definition": REDDIT_QUERY_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },

        # --- 11. Route Reddit Queries for Individual Processing ---
        "route_reddit_queries": {
            "node_id": "route_reddit_queries",
            "node_name": "map_list_router_node",
            "node_config": {
                "choices": ["construct_reddit_search_prompt"],
                "map_targets": [
                    {
                        "source_path": "structured_output.search_queries",
                        "destinations": ["construct_reddit_search_prompt"],
                        "batch_size": 1,
                        "batch_field_name": "query_item"
                    }
                ]
            }
        },

        # --- 12. Construct Reddit Search Prompt ---
        "construct_reddit_search_prompt": {
            "node_id": "construct_reddit_search_prompt",
            "node_name": "prompt_constructor",
            "private_input_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_mode": True,
            "node_config": {
                "prompt_templates": {
                    "reddit_search_user_prompt": {
                        "id": "reddit_search_user_prompt",
                        "template": REDDIT_RESEARCH_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "search_query": None,
                            "query_intent": None
                        },
                        "construct_options": {
                            "search_query": "query_item.query",
                            "query_intent": "query_item.intent"
                        }
                    },
                    "reddit_search_system_prompt": {
                        "id": "reddit_search_system_prompt",
                        "template": REDDIT_RESEARCH_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },

        # --- 13. Execute Reddit Research ---
        "reddit_research_llm": {
            "node_id": "reddit_research_llm",
            "node_name": "llm",
            "private_input_mode": True,
            "output_private_output_to_central_state": True,
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": PERPLEXITY_PROVIDER,
                        "model": PERPLEXITY_MODEL
                    },
                    "temperature": PERPLEXITY_TEMPERATURE,
                    "max_tokens": PERPLEXITY_MAX_TOKENS
                },
                "web_search_options": {
                    "search_domain_filter": [
                        "reddit.com",
                        "quora.com",
                        "g2.com",
                        "slashdot.org",
                        "trustpilot.com",
                        "trustradius.com",
                        "capterra.in",
                        "capterra.com",
                        "capterra.co.uk"
                    ]
                },
                "output_schema": {
                    "schema_definition": REDDIT_RESEARCH_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },

        # --- 14. Construct Final Insights Prompt ---
        "construct_final_insights_prompt": {
            "node_id": "construct_final_insights_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
            "node_config": {
                "prompt_templates": {
                    "final_insights_user_prompt": {
                        "id": "final_insights_user_prompt",
                        "template": FINAL_INSIGHTS_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "reddit_research_results": None,
                            "company_analysis": None,
                            "company_goals": None
                        },
                        "construct_options": {
                            "reddit_research_results": "all_reddit_research",
                            "company_analysis": "company_analysis_report",
                            "company_goals": "company_context"
                        }
                    },
                    "final_insights_system_prompt": {
                        "id": "final_insights_system_prompt",
                        "template": FINAL_INSIGHTS_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },

        # --- 15. Generate Final Market Insights ---
        "generate_final_insights": {
            "node_id": "generate_final_insights",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": OPENAI_PROVIDER,
                        "model": OPENAI_MODEL
                    },
                    "temperature": OPENAI_TEMPERATURE,
                    "max_tokens": OPENAI_MAX_TOKENS,
                    "reasoning_effort_class": "high"
                },
                "output_schema": {
                    "schema_definition": FINAL_INSIGHTS_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },

        # --- 16. Aggregate Both Reports ---
        "aggregate_reports": {
            "node_id": "aggregate_reports",
            "node_name": "transform_data",
            "node_config": {
                "mappings": [
                    {
                        "source_path": "company_analysis_report",
                        "destination_path": "aggregated_report.company_analysis"
                    },
                    {
                        "source_path": "final_insights",
                        "destination_path": "aggregated_report.final_insights_with_content_pillars"
                    }
                ]
            }
        },

        # --- 17. Store Aggregated Report ---
        "store_final_insights_report": {
            "node_id": "store_final_insights_report",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {
                    "is_versioned": False,
                    "operation": "upsert"
                },
                "store_configs": [
                    {
                        "input_field_path": "structured_output",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field": "company_name",
                                "input_namespace_field_pattern": BLOG_COMPANY_ANALYSIS_NAMESPACE_TEMPLATE,
                                "static_docname": BLOG_COMPANY_ANALYSIS_DOCNAME
                            }
                        }
                    }
                ]
            }
        },

        # --- 18. Output Node ---
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "enable_node_fan_in": True,
            "node_config": {}
        }
    },

    # --- Edges Defining Data Flow ---
    "edges": [
        # Input to State and Loading Nodes
        {"src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"},
            {"src_field": "scraped_data", "dst_field": "scraped_data"},
            {"src_field": "has_insufficient_blog_and_page_count", "dst_field": "has_insufficient_blog_and_page_count"}
        ]},
        {"src_node_id": "input_node", "dst_node_id": "load_company_documents", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"}
        ]},
        {"src_node_id": "load_company_documents", "dst_node_id": "load_company_context", "mappings": []},

        {"src_node_id": "load_company_documents", "dst_node_id": "$graph_state", "mappings": [   
            {"src_field": "company_documents", "dst_field": "company_documents"}
        ]},

        {"src_node_id": "$graph_state", "dst_node_id": "load_company_context", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"}
        ]},

        # Store loaded data in state
        {"src_node_id": "load_company_context", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "company_context", "dst_field": "company_context"}
        ]},

        # Flow to router node
        {"src_node_id": "load_company_context", "dst_node_id": "route_content_path", "mappings": []},

        # Pass has_insufficient_blog_and_page_count to router
        {"src_node_id": "$graph_state", "dst_node_id": "route_content_path", "mappings": [
            {"src_field": "has_insufficient_blog_and_page_count", "dst_field": "has_insufficient_blog_and_page_count"}
        ]},

        # Router to merge_document_lists (insufficient content path)
        {"src_node_id": "route_content_path", "dst_node_id": "merge_document_lists", "mappings": []},

        # Router to construct_perplexity_research_prompt (sufficient content path)
        {"src_node_id": "route_content_path", "dst_node_id": "construct_perplexity_research_prompt", "mappings": []},

        # Pass company_documents and scraped_data to merge node (insufficient content path)
        {"src_node_id": "$graph_state", "dst_node_id": "merge_document_lists", "mappings": [
            {"src_field": "company_documents", "dst_field": "company_documents"},
            {"src_field": "scraped_data", "dst_field": "scraped_data"}
        ]},

        # Pass company_context to construct_perplexity_research_prompt (sufficient content path)
        {"src_node_id": "$graph_state", "dst_node_id": "construct_perplexity_research_prompt", "mappings": [
            {"src_field": "company_context", "dst_field": "company_context"}
        ]},

        # Store documents in state
        {"src_node_id": "merge_document_lists", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "merged_data", "dst_field": "merged_data"}
        ]},

        # Perplexity research flow (sufficient content path)
        {"src_node_id": "construct_perplexity_research_prompt", "dst_node_id": "execute_perplexity_research", "mappings": [
            {"src_field": "perplexity_user_prompt", "dst_field": "user_prompt"},
            {"src_field": "perplexity_system_prompt", "dst_field": "system_prompt"}
        ]},
        {"src_node_id": "execute_perplexity_research", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "perplexity_research"}
        ]},
        
        # Flow to batch documents - Insufficient content path
        {"src_node_id": "merge_document_lists", "dst_node_id": "batch_merged_documents", "mappings": []},
        {"src_node_id": "$graph_state", "dst_node_id": "batch_merged_documents", "mappings": [
            {"src_field": "merged_data", "dst_field": "merged_data"}
        ]},

        # Flow to batch documents - Sufficient content path  
        {"src_node_id": "execute_perplexity_research", "dst_node_id": "batch_company_documents", "mappings": []},
        {"src_node_id": "$graph_state", "dst_node_id": "batch_company_documents", "mappings": [
            {"src_field": "company_documents", "dst_field": "company_documents"}
        ]},

        # Document Analysis Flow (Private Mode) - from both batch nodes
        {"src_node_id": "batch_merged_documents", "dst_node_id": "construct_analysis_prompt", "mappings": []},
        {"src_node_id": "batch_company_documents", "dst_node_id": "construct_analysis_prompt", "mappings": []},

        # Pass company context to private input mode node
        {"src_node_id": "$graph_state", "dst_node_id": "construct_analysis_prompt", "mappings": [
            {"src_field": "company_context", "dst_field": "company_context"}
        ]},
        
        {"src_node_id": "construct_analysis_prompt", "dst_node_id": "analyze_documents", "mappings": [
            {"src_field": "analysis_user_prompt", "dst_field": "user_prompt"},
            {"src_field": "analysis_system_prompt", "dst_field": "system_prompt"}
        ]},

        # Collect Analysis Results
        {"src_node_id": "analyze_documents", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "all_document_analyses"}
        ]},

        # Unique Report Generation
        {"src_node_id": "analyze_documents", "dst_node_id": "construct_unique_report_prompt", "mappings": []},
        {"src_node_id": "$graph_state", "dst_node_id": "construct_unique_report_prompt", "mappings": [
            {"src_field": "all_document_analyses", "dst_field": "all_document_analyses"},
            {"src_field": "perplexity_research", "dst_field": "perplexity_research_section"}
        ]},
        {"src_node_id": "construct_unique_report_prompt", "dst_node_id": "generate_unique_report", "mappings": [
            {"src_field": "unique_report_user_prompt", "dst_field": "user_prompt"},
            {"src_field": "unique_report_system_prompt", "dst_field": "system_prompt"}
        ]},

        # Store unique report
        {"src_node_id": "generate_unique_report", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "company_analysis_report"}
        ]},

        # Reddit Query Generation
        {"src_node_id": "generate_unique_report", "dst_node_id": "construct_query_generation_prompt", "mappings": [
            {"src_field": "structured_output", "dst_field": "structured_output"}
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "construct_query_generation_prompt", "mappings": [
            {"src_field": "company_context", "dst_field": "company_context"}
        ]},
        {"src_node_id": "construct_query_generation_prompt", "dst_node_id": "generate_reddit_queries", "mappings": [
            {"src_field": "query_gen_user_prompt", "dst_field": "user_prompt"},
            {"src_field": "query_gen_system_prompt", "dst_field": "system_prompt"}
        ]},

        # Route Reddit Queries
        {"src_node_id": "generate_reddit_queries", "dst_node_id": "route_reddit_queries", "mappings": [
            {"src_field": "structured_output", "dst_field": "structured_output"}
        ]},

        # Reddit Research Flow (Private Mode)
        {"src_node_id": "route_reddit_queries", "dst_node_id": "construct_reddit_search_prompt", "mappings": []},
        {"src_node_id": "construct_reddit_search_prompt", "dst_node_id": "reddit_research_llm", "mappings": [
            {"src_field": "reddit_search_user_prompt", "dst_field": "user_prompt"},
            {"src_field": "reddit_search_system_prompt", "dst_field": "system_prompt"}
        ]},

        # Collect Reddit Research Results
        {"src_node_id": "reddit_research_llm", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "all_reddit_research"}
        ]},

        # Final Insights Generation
        {"src_node_id": "reddit_research_llm", "dst_node_id": "construct_final_insights_prompt", "mappings": []},
        {"src_node_id": "$graph_state", "dst_node_id": "construct_final_insights_prompt", "mappings": [
            {"src_field": "all_reddit_research", "dst_field": "all_reddit_research"},
            {"src_field": "company_analysis_report", "dst_field": "company_analysis_report"},
            {"src_field": "company_context", "dst_field": "company_context"}
        ]},
        {"src_node_id": "construct_final_insights_prompt", "dst_node_id": "generate_final_insights", "mappings": [
            {"src_field": "final_insights_user_prompt", "dst_field": "user_prompt"},
            {"src_field": "final_insights_system_prompt", "dst_field": "system_prompt"}
        ]},

        # Store final insights in state (optional, for debugging)
        {"src_node_id": "generate_final_insights", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "final_insights"}
        ]},

        # Flow to aggregate both reports
        {"src_node_id": "generate_final_insights", "dst_node_id": "aggregate_reports", "mappings": []},
        {"src_node_id": "$graph_state", "dst_node_id": "aggregate_reports", "mappings": [
            {"src_field": "company_analysis_report", "dst_field": "company_analysis_report"},
            {"src_field": "final_insights", "dst_field": "final_insights"}
        ]},

        # Flow from aggregated reports to store
        {"src_node_id": "aggregate_reports", "dst_node_id": "store_final_insights_report", "mappings": [
            {"src_field": "transformed_data", "dst_field": "structured_output"}
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "store_final_insights_report", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"}
        ]},

        # Output
        {"src_node_id": "store_final_insights_report", "dst_node_id": "output_node", "mappings": [
            {"src_field": "passthrough_data", "dst_field": "aggregated_report"}
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
            {"src_field": "company_analysis_report", "dst_field": "company_analysis"},
            {"src_field": "final_insights", "dst_field": "final_insights_with_content_pillars"},
            {"src_field": "company_name", "dst_field": "company_name"}
        ]}
    ],

    # Define start and end
    "input_node_id": "input_node",
    "output_node_id": "output_node",

    # State reducers
    "metadata": {
        "$graph_state": {
            "reducer": {
                "all_document_analyses": "collect_values",
                "all_reddit_research": "collect_values",
                "perplexity_research": "replace",
                "has_insufficient_blog_and_page_count": "replace"
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
    "company_name": "company_analysis_test",  # Replace with actual company name for testing
    "scraped_data": [  # Optional web scraped data that will be merged with company documents
        {"doc_data": "ContentAI announced today the launch of advanced enterprise features including custom AI model training and dedicated support. The new features are designed to help large organizations scale their content creation efforts while maintaining brand consistency."},
        {"doc_data": "TechCorp, a leading B2B SaaS provider, achieved a 300% increase in content output after implementing ContentAI. The marketing team now publishes 20 high-quality articles per month, up from 5, while reducing content creation costs by 60%."}
    ],
    "has_insufficient_blog_and_page_count": True,
}

async def validate_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """Custom validation function for the workflow outputs."""
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating company analysis workflow outputs...")
    
    # Check required fields
    assert 'company_name' in outputs, "Validation Failed: 'company_name' missing."
    assert 'company_analysis' in outputs, "Validation Failed: 'company_analysis' missing."
    assert 'final_insights_with_content_pillars' in outputs, "Validation Failed: 'final_insights_with_content_pillars' missing."
    assert 'aggregated_report' in outputs, "Validation Failed: 'aggregated_report' missing."
    
    # Validate company analysis structure
    company_analysis = outputs.get('company_analysis', {})
    assert 'executive_summary' in company_analysis, "Validation Failed: Company executive summary missing."
    assert 'products_and_services' in company_analysis, "Validation Failed: Products and services missing."
    assert 'target_market' in company_analysis, "Validation Failed: Target market missing."
    
    # Validate final insights with content pillars structure
    final_insights = outputs.get('final_insights_with_content_pillars', {})
    assert 'executive_summary' in final_insights, "Validation Failed: Final insights executive summary missing."
    assert 'critical_user_needs' in final_insights, "Validation Failed: Critical user needs missing."
    assert 'market_opportunities' in final_insights, "Validation Failed: Market opportunities missing."
    assert 'content_pillars' in final_insights, "Validation Failed: Content pillars missing."
    assert 'market_demand_summary' in final_insights, "Validation Failed: Market demand summary missing."
    assert 'implementation_roadmap' in final_insights, "Validation Failed: Implementation roadmap missing."
    
    # Validate aggregated report structure
    aggregated_report = outputs.get('aggregated_report', {})
    assert aggregated_report, "Validation Failed: Aggregated report is empty."
    assert 'company_analysis' in aggregated_report, "Validation Failed: Company analysis missing from aggregated report."
    assert 'final_insights_with_content_pillars' in aggregated_report, "Validation Failed: Final insights missing from aggregated report."
    
    # Check that we have at least 5 content pillars
    content_pillars = final_insights.get('content_pillars', [])
    assert len(content_pillars) >= 5, f"Validation Failed: Expected at least 5 content pillars, got {len(content_pillars)}"
    
    # Validate each content pillar has demand evidence
    for i, pillar in enumerate(content_pillars):
        assert 'demand_evidence' in pillar, f"Validation Failed: Content pillar {i+1} missing demand evidence"
        assert 'reddit_insights' in pillar, f"Validation Failed: Content pillar {i+1} missing Reddit insights"
        assert 'priority_score' in pillar, f"Validation Failed: Content pillar {i+1} missing priority score"
    
    logger.info(f"   Company name: {outputs.get('company_name')}")
    logger.info(f"   Company analysis sections: {list(company_analysis.keys())}")
    logger.info(f"   Final insights sections: {list(final_insights.keys())}")
    logger.info(f"   Aggregated report available: {bool(aggregated_report)}")
    logger.info(f"   Aggregated report sections: {list(aggregated_report.keys())}")
    logger.info(f"   Content pillars count: {len(content_pillars)}")
    logger.info(f"   Critical user needs count: {len(final_insights.get('critical_user_needs', []))}")
    logger.info(f"   Market opportunities count: {len(final_insights.get('market_opportunities', []))}")
    logger.info("✓ Output structure and content validation passed.")
    return True

async def main_test_company_analysis():
    test_name = "Company Analysis Workflow Test - Internal Documents & Reddit Research"
    print(f"--- Starting {test_name} ---")
    
    company_name = TEST_INPUTS["company_name"]

    # Build setup documents similar to LinkedIn workflow style
    setup_docs: List[SetupDocInfo] = [
        # Company Goals Document
        {
            'namespace': BLOG_COMPANY_NAMESPACE_TEMPLATE.format(item=company_name),
            'docname': BLOG_COMPANY_DOCNAME,
            'initial_data': {
                "name": "KiwiQ",
                "website_url": "https://www.kiwiq.ai",
                "value_proposition": "AI-powered content generation platform specifically designed for B2B SaaS companies. Our platform leverages GPT-5 and proprietary algorithms to create high-quality blog posts, whitepapers, and marketing content that resonates with technical B2B audiences.",
                "company_goals": [
                    "Become the leading AI-powered content creation platform for B2B SaaS companies",
                    "Achieve 10,000 active users by end of 2025", 
                    "Expand into enterprise market with custom solutions",
                    "Build strategic partnerships with major marketing agencies",
                    "Establish thought leadership in AI content generation space"
                ],
                "target_metrics": {
                    "user_growth": "50% MoM",
                    "revenue_target": "10M ARR by 2025",
                    "customer_satisfaction": "NPS > 50"
                }
            },
            'is_shared': False,
            'is_versioned': False,
            'is_system_entity': False,
        },
        # Sample Internal Company Documents (multiple docs under uploaded files namespace)
        {
            'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name),
            'docname': "kiwiq_product_overview_doc_1",
            'initial_data': {"doc_data": """KiwiQ is an advanced AI-powered content generation platform designed specifically for B2B SaaS companies. Our platform leverages GPT-5 and proprietary algorithms to create high-quality blog posts, whitepapers, and marketing content.       
                        Key Features:
                        - AI content generation with industry-specific training
                        - SEO optimization built into every piece of content
                        - Content calendar management and scheduling
                        - Multi-channel publishing (blog, LinkedIn, Twitter)
                        - Advanced analytics dashboard with content performance metrics
                        - Team collaboration tools for content review and approval
                        - Integration with major CMS platforms (WordPress, HubSpot, etc.)

                        Our unique value proposition is the industry-specific training that ensures content resonates with technical B2B audiences. Unlike general-purpose AI writers, ContentAI understands the nuances of SaaS marketing, technical concepts, and enterprise buyer journeys.

                        Technology Stack:
                        - Frontend: React with TypeScript
                        - Backend: Python FastAPI
                        - AI Models: Fine-tuned GPT-5 with proprietary training data
                        - Infrastructure: AWS with auto-scaling capabilities
                        - Database: PostgreSQL for structured data, Redis for caching
                        """},
            'is_shared': False,
            'is_versioned': False,
            'is_system_entity': False,
        },
        {
            'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name),
            'docname': "kiwiq_product_overview_doc_2",
            'initial_data': {"doc_data": """
            # KiwiQ User Guide

## Welcome to KiwiQ

This comprehensive guide will help you get started with KiwiQ and master all its features to transform your content operations.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Dashboard Overview](#dashboard-overview)
3. [Content Diagnostics](#content-diagnostics)
4. [Content Creation Studio](#content-creation-studio)
5. [Content Optimization](#content-optimization)
6. [Analytics & Reporting](#analytics-reporting)
7. [Integrations Setup](#integrations-setup)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Account Setup

#### Step 1: Registration
1. Visit www.kiwiq.ai/signup
2. Enter your business email
3. Verify your email address
4. Complete your profile information

#### Step 2: Company Profile
1. Navigate to **Settings > Company Profile**
2. Enter your company information:
   - Company name and website
   - Industry and target audience
   - Content goals and objectives
   - Brand voice and guidelines

#### Step 3: Team Setup
1. Go to **Settings > Team Management**
2. Click **Invite Team Members**
3. Assign roles:
   - **Admin**: Full platform access
   - **Editor**: Content creation and editing
   - **Viewer**: Read-only access

### Initial Configuration

#### Connect Your Website
1. Navigate to **Integrations > CMS**
2. Select your CMS platform
3. Follow the authentication flow
4. Verify connection with test sync

#### Setup Analytics
1. Go to **Integrations > Analytics**
2. Connect Google Analytics 4
3. Connect Google Search Console
4. Configure data sync frequency

---

## Dashboard Overview

### Main Dashboard Components

#### Performance Metrics Panel
- **Content Published**: Total articles this month
- **Organic Traffic**: Current vs. previous period
- **AI Visibility Score**: LLM citation tracking
- **SEO Health**: Overall technical score

#### Quick Actions
- **New Content Brief**: Start content creation
- **Run Diagnostics**: Analyze existing content
- **View Reports**: Access performance data
- **Schedule Content**: Plan publishing calendar

#### Activity Feed
- Recent content updates
- Team member activities
- Integration status
- System notifications

### Navigation Structure

```
Main Menu
├── Dashboard
├── Content Studio
│   ├── Create New
│   ├── Content Calendar
│   └── Drafts
├── Diagnostics
│   ├── Run Analysis
│   ├── Reports
│   └── Recommendations
├── Analytics
│   ├── Performance
│   ├── SEO Metrics
│   └── AI Visibility
├── Integrations
└── Settings
```

---

## Content Diagnostics

### Running Your First Diagnostic

#### Step 1: Initiate Analysis
1. Click **Diagnostics > Run Analysis**
2. Select analysis type:
   - **Quick Scan**: 5-minute overview
   - **Deep Analysis**: Comprehensive audit
   - **Competitor Analysis**: Benchmark comparison

#### Step 2: Configure Parameters
```
Analysis Settings:
- Website URL: [your-domain.com]
- Content Type: [Blog/Landing Pages/All]
- Date Range: [Last 30/60/90 days]
- Include Competitors: [Yes/No]
```

#### Step 3: Review Results

##### Content Health Report
- **Technical SEO Issues**
  - Crawlability problems
  - Missing meta descriptions
  - Broken links
  - Page speed issues

- **Content Quality Metrics**
  - Readability scores
  - Content depth analysis
  - Keyword optimization
  - Semantic structure

- **AI Visibility Assessment**
  - LLM-friendly formatting
  - Schema markup status
  - Featured snippet potential
  - Voice search optimization

### Understanding Diagnostic Scores

#### SEO Health Score (0-100)
- **90-100**: Excellent - Minor optimizations only
- **70-89**: Good - Some improvements needed
- **50-69**: Fair - Significant opportunities
- **Below 50**: Poor - Critical issues to address

#### AI Visibility Score (0-100)
- Measures how well content performs in AI search
- Tracks citations in ChatGPT, Claude, etc.
- Analyzes structured data implementation
- Evaluates content comprehensiveness

---

## Content Creation Studio

### Creating Your First Content Brief

#### Step 1: Choose Creation Method

##### Method A: AI-Suggested Topics
1. Click **Create New > AI Suggestions**
2. System analyzes your:
   - Current content gaps
   - Competitor content
   - Search trends
   - User intent data
3. Select from suggested topics

##### Method B: Manual Input
1. Click **Create New > Manual Brief**
2. Enter your topic or idea
3. Add context and requirements

#### Step 2: Research & Validation

The platform automatically performs:
- **Google Research**: Top-ranking content analysis
- **Reddit Research**: User discussions and pain points
- **Competitor Analysis**: Content gap identification
- **Keyword Research**: Search volume and difficulty

#### Step 3: Brief Generation

##### AI-Generated Brief Components
```
Content Brief Structure:
1. Title and Meta Description
2. Target Keywords (Primary & Secondary)
3. Search Intent Analysis
4. Content Outline
   - Introduction hooks
   - Main sections
   - Subheadings
   - Conclusion CTA
5. Word Count Recommendation
6. Internal Linking Opportunities
7. Visual Content Suggestions
8. SEO Optimization Checklist
```

### Content Calendar Management

#### Planning Your Content
1. Navigate to **Content Studio > Calendar**
2. View monthly/weekly/daily views
3. Drag and drop to reschedule
4. Color coding by status:
   - 🔵 Planned
   - 🟡 In Progress
   - 🟢 Published
   - 🔴 Needs Review

#### Batch Operations
- Select multiple content pieces
- Apply bulk actions:
  - Change status
  - Assign team members
  - Update categories
  - Schedule publishing

### Writing with AI Assistance

#### Step 1: Open Editor
1. Click on any content brief
2. Select **Start Writing**
3. Choose writing mode:
   - **Full AI Generation**: Complete article
   - **Section by Section**: Guided writing
   - **Outline Only**: Manual writing

#### Step 2: AI Writing Features

##### Smart Suggestions
- Real-time SEO recommendations
- Readability improvements
- Fact-checking alerts
- Citation suggestions

##### Writing Tools
- **Rewrite**: Improve any paragraph
- **Expand**: Add more detail
- **Summarize**: Create concise versions
- **Tone Adjust**: Match brand voice

#### Step 3: Optimization Check
Before publishing, the system checks:
- ✅ Keyword density
- ✅ Meta descriptions
- ✅ Image alt text
- ✅ Internal links
- ✅ Readability score
- ✅ Grammar and spelling

---

## Content Optimization

### Optimizing Existing Content

#### Identify Optimization Opportunities
1. Go to **Diagnostics > Reports**
2. Filter by **Needs Optimization**
3. Sort by potential impact

#### Optimization Workflow

##### Step 1: Select Content
- Choose article to optimize
- Review current performance metrics
- Identify specific issues

##### Step 2: Apply Optimizations
Available optimization types:
- **Content Refresh**: Update statistics and information
- **SEO Enhancement**: Improve keyword targeting
- **Structure Improvement**: Better headings and formatting
- **Length Expansion**: Add comprehensive coverage
- **Visual Enhancement**: Add images and videos

##### Step 3: A/B Testing
1. Create variant versions
2. Split traffic between versions
3. Monitor performance metrics
4. Implement winning version

### Content Repurposing

#### Repurpose Workflows
Transform existing content into:
- **Social Media Posts**: LinkedIn, Twitter threads
- **Email Newsletters**: Subscriber content
- **Video Scripts**: YouTube content
- **Infographics**: Visual summaries
- **Podcasts Scripts**: Audio content

#### Automated Repurposing
1. Select source content
2. Choose target format
3. AI generates adapted version
4. Review and edit
5. Schedule distribution

---

## Analytics & Reporting

### Performance Dashboard

#### Key Metrics Tracked
- **Traffic Metrics**
  - Page views
  - Unique visitors
  - Session duration
  - Bounce rate

- **Engagement Metrics**
  - Time on page
  - Scroll depth
  - Social shares
  - Comments

- **Conversion Metrics**
  - Lead generation
  - Email signups
  - Demo requests
  - Sales attribution

### Custom Reports

#### Creating Custom Reports
1. Navigate to **Analytics > Custom Reports**
2. Select metrics to include
3. Choose visualization type:
   - Line graphs
   - Bar charts
   - Heat maps
   - Tables
4. Set schedule for automated delivery

#### Report Templates
- **Executive Summary**: High-level KPIs
- **Content Performance**: Detailed content metrics
- **SEO Progress**: Search visibility tracking
- **Competitor Comparison**: Benchmark analysis

### AI Visibility Tracking

#### Monitor AI Performance
- **ChatGPT Citations**: Track mentions
- **Perplexity Appearances**: Answer inclusion
- **Bing Chat References**: Content usage
- **Google SGE**: Generative results

#### Optimization Recommendations
Based on AI tracking, receive:
- Structure improvements
- Content depth suggestions
- FAQ additions
- Schema markup updates

---

## Integrations Setup

### CMS Integration

#### WordPress Setup
1. Install KiwiQ WordPress plugin
2. Enter API key from KiwiQ dashboard
3. Configure sync settings:
   - Auto-publish
   - Draft sync
   - Category mapping
4. Test connection

#### HubSpot Setup
1. Navigate to **Integrations > HubSpot**
2. Click **Connect HubSpot**
3. Authorize permissions
4. Map content types
5. Configure workflow triggers

### Analytics Integration

#### Google Analytics 4
1. Go to **Integrations > GA4**
2. Sign in with Google account
3. Select property
4. Choose data streams
5. Configure metrics import

#### Google Search Console
1. Navigate to **Integrations > GSC**
2. Verify domain ownership
3. Select properties
4. Configure data sync frequency

### Communication Tools

#### Slack Integration
1. Click **Add to Slack**
2. Choose workspace
3. Select notification channel
4. Configure alerts:
   - Content published
   - Performance milestones
   - Team mentions

---

## Best Practices

### Content Strategy Best Practices

#### Topic Selection
- Focus on user intent, not just keywords
- Prioritize topics with business impact
- Balance trending vs. evergreen content
- Consider content clustering

#### Content Quality
- Aim for comprehensive coverage
- Include original research or data
- Add expert quotes and citations
- Update content regularly

#### SEO Optimization
- Natural keyword integration
- Optimize for featured snippets
- Include related keywords
- Build topical authority

### Workflow Best Practices

#### Team Collaboration
- Define clear roles and responsibilities
- Use comments for feedback
- Set realistic deadlines
- Regular content reviews

#### Content Calendar
- Plan 1-2 months ahead
- Mix content types
- Align with business goals
- Leave room for trending topics

#### Performance Monitoring
- Weekly performance reviews
- Monthly strategy adjustments
- Quarterly comprehensive audits
- Annual strategy planning

---

## Troubleshooting

### Common Issues & Solutions

#### Integration Issues

**Problem**: CMS sync not working
```
Solution:
1. Check API key validity
2. Verify permissions
3. Test connection
4. Contact support if persistent
```

**Problem**: Analytics data missing
```
Solution:
1. Confirm integration active
2. Check date range
3. Verify tracking code
4. Allow 24 hours for sync
```

#### Content Creation Issues

**Problem**: AI suggestions not relevant
```
Solution:
1. Update company profile
2. Refine target audience
3. Add competitor URLs
4. Provide more context
```

**Problem**: Brief generation stuck
```
Solution:
1. Refresh browser
2. Clear cache
3. Try different topic
4. Check system status
```

### Getting Help

#### Support Resources
- **Help Center**: help.kiwiq.ai
- **Video Tutorials**: kiwiq.ai/tutorials
- **Community Forum**: community.kiwiq.ai
- **Email Support**: support@kiwiq.ai

#### Support Tiers
- **Starter**: Email support (48h response)
- **Professional**: Priority support (24h)
- **Enterprise**: Dedicated success manager

### Keyboard Shortcuts

#### Global Shortcuts
- **Ctrl/Cmd + K**: Quick search
- **Ctrl/Cmd + N**: New content
- **Ctrl/Cmd + D**: Dashboard
- **Ctrl/Cmd + ?**: Help menu

#### Editor Shortcuts
- **Ctrl/Cmd + S**: Save draft
- **Ctrl/Cmd + Enter**: Publish
- **Ctrl/Cmd + /**: AI suggestions
- **Ctrl/Cmd + Z**: Undo

---

## Appendix

### Glossary of Terms

- **AI Visibility**: How well content appears in AI-powered search
- **Content Brief**: Detailed outline for content creation
- **LLM**: Large Language Model (like ChatGPT)
- **SGE**: Search Generative Experience (Google's AI search)
- **SERP**: Search Engine Results Page
- **CTR**: Click-Through Rate
- **Core Web Vitals**: Google's page experience metrics

### System Requirements

#### Browser Support
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

#### Recommended Specifications
- Screen resolution: 1366x768 minimum
- Internet speed: 10 Mbps+
- JavaScript enabled
- Cookies enabled

---

*Last Updated: January 2025*
*Version: 2.0*
*© KiwiQ - All Rights Reserved*
                        """},
            'is_shared': False,
            'is_versioned': False,
            'is_system_entity': False,
        },
        {
            'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name),
            'docname': "kiwiq_product_overview_doc_3",
            'initial_data': {"doc_data": """
            # KiwiQ Technical Architecture Documentation

## System Overview

KiwiQ is built as a modern, scalable, microservices-based platform that leverages AI models, real-time data processing, and cloud-native technologies to deliver comprehensive content operations capabilities.

## Architecture Principles

### Core Design Principles
- **Microservices Architecture**: Loosely coupled services for scalability
- **Event-Driven Design**: Asynchronous processing for performance
- **API-First Development**: RESTful and GraphQL APIs
- **Cloud-Native**: Containerized, orchestrated deployment
- **Security by Design**: Zero-trust architecture with encryption at rest and in transit

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend Layer                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ React Web App│  │ Mobile PWA   │  │ Admin Portal │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        API Gateway                           │
│               (Authentication, Rate Limiting)                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Application Services                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │Content Mgmt │  │ AI Engine   │  │ Analytics   │        │
│  │   Service   │  │   Service   │  │   Service   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ Workflow    │  │ Integration │  │Notification │        │
│  │   Engine    │  │    Hub      │  │   Service   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Data Layer                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ PostgreSQL  │  │   Redis     │  │ Elasticsearch│        │
│  │  (Primary)  │  │   (Cache)   │  │   (Search)  │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

## Component Architecture

### 1. Frontend Layer

#### React Web Application
- **Framework**: React 18 with TypeScript
- **State Management**: Redux Toolkit with RTK Query
- **UI Components**: Custom component library based on Tailwind CSS
- **Build Tools**: Vite for development, optimized production builds
- **Testing**: Jest, React Testing Library, Cypress for E2E

#### Key Features
- Server-side rendering for SEO
- Progressive Web App capabilities
- Real-time updates via WebSocket
- Responsive design for all devices

### 2. API Gateway

#### Technology Stack
- **Framework**: Kong Gateway
- **Authentication**: OAuth 2.0, JWT tokens
- **Rate Limiting**: Token bucket algorithm
- **Monitoring**: Prometheus metrics integration

#### Endpoints Structure
```
/api/v1/
├── /auth           - Authentication endpoints
├── /content        - Content management
├── /workflows      - Workflow operations
├── /analytics      - Performance metrics
├── /integrations   - Third-party connections
└── /admin          - Administrative functions
```

### 3. Core Services

#### Content Management Service
- **Purpose**: Handle all content-related operations
- **Technology**: Node.js with Express
- **Database**: PostgreSQL for structured data
- **Features**:
  - CRUD operations for content
  - Version control and history
  - Content scheduling
  - Multi-format support

#### AI Engine Service
- **Purpose**: Process AI-related requests
- **Technology**: Python FastAPI
- **ML Framework**: LangChain for LLM orchestration
- **Models Integration**:
  - OpenAI GPT-4 for content generation
  - Claude for analysis and editing
  - Perplexity for research
  - Custom fine-tuned models

#### Workflow Engine
- **Purpose**: Orchestrate complex content workflows
- **Technology**: Apache Airflow
- **Features**:
  - DAG-based workflow definition
  - Parallel processing
  - Error handling and retry logic
  - Human-in-the-loop support

#### Analytics Service
- **Purpose**: Process and aggregate performance data
- **Technology**: Node.js with streaming capabilities
- **Data Processing**: Apache Spark for batch processing
- **Real-time**: Apache Kafka for event streaming

### 4. Integration Layer

#### Supported Integrations
```yaml
CMS Platforms:
  - WordPress (REST API)
  - HubSpot (OAuth 2.0)
  - Contentful (GraphQL)
  - Ghost (Admin API)

Analytics:
  - Google Analytics 4 (Data API)
  - Google Search Console (API)
  - Adobe Analytics (API 2.0)

SEO Tools:
  - SEMrush (API v3)
  - Ahrefs (API v2)
  - Moz (API)

Communication:
  - Slack (Web API)
  - Microsoft Teams (Graph API)
  - Email (SMTP/SendGrid)
```

### 5. Data Architecture

#### Primary Database (PostgreSQL)
```sql
-- Core Tables Structure
content_items (
  id UUID PRIMARY KEY,
  title VARCHAR(255),
  slug VARCHAR(255) UNIQUE,
  content JSONB,
  status ENUM,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  metadata JSONB
)

workflows (
  id UUID PRIMARY KEY,
  name VARCHAR(255),
  definition JSONB,
  status ENUM,
  created_by UUID,
  execution_history JSONB[]
)

analytics_data (
  id UUID PRIMARY KEY,
  content_id UUID,
  metric_type VARCHAR(50),
  value NUMERIC,
  timestamp TIMESTAMP,
  source VARCHAR(50)
)
```

#### Cache Layer (Redis)
- Session management
- API response caching
- Real-time analytics aggregation
- Workflow state management

#### Search Engine (Elasticsearch)
- Full-text content search
- Faceted search capabilities
- Analytics aggregations
- Log analysis

## Security Architecture

### Authentication & Authorization
- **OAuth 2.0** for third-party integrations
- **JWT tokens** for API authentication
- **Role-Based Access Control (RBAC)**
- **Multi-Factor Authentication (MFA)**

### Data Security
- **Encryption at Rest**: AES-256 for database
- **Encryption in Transit**: TLS 1.3
- **Key Management**: AWS KMS or HashiCorp Vault
- **Data Masking**: PII protection

### Compliance
- **GDPR Compliant**: Data privacy controls
- **SOC 2 Type II**: Security certification
- **CCPA Ready**: California privacy law
- **ISO 27001**: Information security

## Infrastructure

### Cloud Platform
- **Primary**: AWS (us-east-1, eu-west-1)
- **CDN**: CloudFlare for global distribution
- **Container Orchestration**: Kubernetes (EKS)
- **Service Mesh**: Istio for microservices communication

### Deployment Pipeline
```yaml
CI/CD Pipeline:
  1. Code Commit (GitHub)
  2. Automated Tests (GitHub Actions)
  3. Build Docker Images
  4. Security Scanning (Snyk)
  5. Deploy to Staging (ArgoCD)
  6. Integration Tests
  7. Deploy to Production (Blue-Green)
  8. Health Checks
  9. Monitoring Alerts
```

### Monitoring & Observability

#### Metrics Collection
- **Prometheus**: System and application metrics
- **Grafana**: Visualization dashboards
- **Custom Metrics**: Business KPIs

#### Logging
- **ELK Stack**: Elasticsearch, Logstash, Kibana
- **Structured Logging**: JSON format
- **Log Aggregation**: Centralized logging

#### Tracing
- **Jaeger**: Distributed tracing
- **OpenTelemetry**: Instrumentation
- **Performance Monitoring**: Real User Monitoring (RUM)

## Scalability Strategy

### Horizontal Scaling
- Auto-scaling groups for services
- Load balancing with health checks
- Database read replicas
- Caching at multiple levels

### Performance Optimization
- **Response Time**: < 200ms p95
- **Throughput**: 10,000 requests/second
- **Availability**: 99.9% uptime SLA
- **Data Processing**: Batch and stream processing

## API Design

### RESTful API Standards
```javascript
// Example API Response Structure
{
  "status": "success",
  "data": {
    "id": "uuid",
    "type": "content",
    "attributes": {
      // Resource attributes
    },
    "relationships": {
      // Related resources
    }
  },
  "meta": {
    "timestamp": "2025-01-15T10:00:00Z",
    "version": "1.0"
  }
}
```

### GraphQL Schema
```graphql
type Content {
  id: ID!
  title: String!
  slug: String!
  body: String
  status: ContentStatus!
  author: User!
  analytics: Analytics
  createdAt: DateTime!
  updatedAt: DateTime!
}

type Query {
  content(id: ID!): Content
  contents(filter: ContentFilter): [Content!]!
}

type Mutation {
  createContent(input: ContentInput!): Content!
  updateContent(id: ID!, input: ContentInput!): Content!
  deleteContent(id: ID!): Boolean!
}
```

## Development Environment

### Local Development Setup
```bash
# Prerequisites
- Docker Desktop
- Node.js 18+
- Python 3.11+
- PostgreSQL 15
- Redis 7

# Environment Setup
docker-compose up -d
npm install
npm run dev

# Service URLs
Frontend: http://localhost:3000
API: http://localhost:8000
Admin: http://localhost:3001
```

### Testing Strategy
- **Unit Tests**: 80% code coverage minimum
- **Integration Tests**: API endpoint testing
- **E2E Tests**: Critical user journeys
- **Performance Tests**: Load testing with K6
- **Security Tests**: OWASP ZAP scanning

## Disaster Recovery

### Backup Strategy
- **Database**: Daily automated backups, 30-day retention
- **File Storage**: S3 versioning enabled
- **Configuration**: Git-based config management
- **Recovery Time Objective (RTO)**: 4 hours
- **Recovery Point Objective (RPO)**: 1 hour

### Failover Procedures
1. Automatic health checks every 30 seconds
2. Automated failover to standby region
3. DNS update via Route53
4. Cache warming procedures
5. Notification to operations team

## Performance Benchmarks

### System Requirements
- **CPU**: 8 cores minimum per service
- **Memory**: 16GB RAM per service
- **Storage**: SSD with 10,000 IOPS
- **Network**: 10 Gbps internal connectivity

### Load Testing Results
- **Concurrent Users**: 10,000
- **Requests/Second**: 5,000
- **Average Latency**: 150ms
- **Error Rate**: < 0.1%

## Future Architecture Enhancements

### Planned Improvements
1. **Edge Computing**: Deploy services closer to users
2. **AI Model Optimization**: Custom model training pipeline
3. **Real-time Collaboration**: WebRTC integration
4. **Blockchain Integration**: Content verification
5. **Quantum-Ready Encryption**: Post-quantum cryptography

---

*Last Updated: January 2025*
    *Version: 2.0*"""},
            'is_shared': False,
            'is_versioned': False,
            'is_system_entity': False,
        },
        {
            'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name),
            'docname': "kiwiq_target_audience_analysis_1",
            'initial_data': {"doc_data": """# KiwiQ Product Overview

## Executive Summary

KiwiQ is an AI-powered ContentOps platform designed to revolutionize how organizations create, optimize, and manage blog content. By leveraging advanced AI models and comprehensive data integration, KiwiQ helps marketing teams systematically improve content performance, identify high-impact opportunities, and automate content workflows.

## Problem We Solve

Organizations face significant challenges in content management:
- **Fragmented workflows** across analytics, SEO, CMS, and editorial tools
- **Lack of unified strategy** for prioritizing content updates
- **Difficulty identifying** high-impact content opportunities
- **Manual processes** for SEO research and performance tracking
- **Poor AI visibility** in emerging LLM-powered search engines

## Core Value Proposition

KiwiQ delivers measurable results through:
- **30% reduction** in content production time
- **2x improvement** in SEO performance metrics
- **Automated workflows** that eliminate manual research
- **Data-driven insights** for content prioritization
- **AI-optimized content** for better visibility in ChatGPT and other LLMs

## Key Features

### 1. Content Diagnostics Intelligence
- **Comprehensive Content Audit**: Analyze existing blog content for performance gaps
- **SEO Health Assessment**: Technical SEO analysis including crawlability, semantic structure, and Core Web Vitals
- **AI Visibility Analysis**: Track and optimize content for LLM citations and bot traffic
- **Competitor Benchmarking**: Compare content performance against industry competitors

### 2. Content Creation Studio
- **AI-Powered Brief Generation**: Transform ideas into comprehensive content briefs
- **Research Automation**: Automated Google and Reddit research for topic validation
- **Topic Ideation Engine**: Generate high-impact content ideas based on data
- **Content Calendar Management**: Plan and schedule content with AI recommendations

### 3. Content Optimization Workflows
- **Content Update Prioritization**: Identify which content needs updates based on performance
- **SEO Enhancement**: Automatic recommendations for improving search visibility
- **Content Repurposing**: Transform existing content into new formats
- **Performance Tracking**: Monitor content metrics across multiple channels

### 4. Data Integration Hub
- **Google Analytics 4**: Session, engagement, and conversion tracking
- **Google Search Console**: Keyword rankings, CTR, and search performance
- **CMS Integration**: Direct connection to WordPress, HubSpot, and other platforms
- **AI Bot Tracking**: Monitor ChatGPT-User and other AI crawler activity

## Target Users

### Primary Users
- **Content Marketing Managers**: Leading content strategy and team execution
- **SEO Specialists**: Optimizing content for search and AI visibility
- **Marketing Directors**: Overseeing content ROI and performance

### Ideal Customer Profile
- **Company Size**: 50-500 employees
- **Industry**: B2B SaaS, Technology, Professional Services
- **Content Volume**: Publishing 4+ blog posts per month
- **Team Size**: 2-10 person marketing team

## Platform Architecture

### Technology Stack
- **AI Models**: GPT-4, Claude, Perplexity for content generation
- **Data Processing**: Real-time integration with analytics platforms
- **Workflow Engine**: Automated pipeline for content operations
- **User Interface**: Modern React-based dashboard

### Key Integrations
- Google Analytics 4
- Google Search Console
- WordPress, HubSpot CMS
- SEMrush, Ahrefs
- Slack, Microsoft Teams

## Success Metrics

### Performance KPIs
- **Content Production Speed**: 30% faster brief-to-publish cycle
- **SEO Performance**: 2x improvement in organic traffic
- **AI Visibility**: 50% increase in LLM citations
- **Team Efficiency**: 40% reduction in manual research time

### Business Impact
- **ROI**: 3x return on content investment within 6 months
- **Lead Generation**: 45% increase in content-driven leads
- **Brand Authority**: Improved thought leadership positioning

## Pricing Model

### Starter Plan - $499/month
- Up to 10 content pieces per month
- Basic SEO analysis
- Standard integrations

### Professional Plan - $999/month
- Up to 30 content pieces per month
- Advanced AI features
- Priority support
- Custom integrations

### Enterprise Plan - Custom Pricing
- Unlimited content
- Dedicated success manager
- Custom workflows
- API access

## Competitive Advantages

1. **Unified Platform**: Single solution for entire content lifecycle
2. **AI-First Approach**: Built for the age of AI search and LLMs
3. **Data-Driven Insights**: Decisions based on real performance data
4. **Automation at Scale**: Reduce manual work by 70%
5. **Proven Methodology**: Based on successful content strategies

## Future Roadmap

### Q1 2025
- LinkedIn content optimization
- Advanced competitor analysis
- Multi-language support

### Q2 2025
- Video content optimization
- Podcast content workflows
- Enhanced AI personalization

### Q3 2025
- Predictive content performance
- Advanced attribution modeling
- Enterprise API expansion

## Getting Started

1. **Discovery Call**: Understand your content challenges
2. **Platform Demo**: See KiwiQ in action
3. **Pilot Program**: 30-day trial with your content
4. **Onboarding**: Guided setup and integration
5. **Success Planning**: Develop content strategy with our team

## Contact Information

**Website**: www.kiwiq.ai
**Email**: hello@kiwiq.ai
**Support**: support@kiwiq.ai
**Sales**: sales@kiwiq.ai

---

*KiwiQ - Transform Your Content Operations with AI*"""},
            'is_shared': False,
            'is_versioned': False,
            'is_system_entity': False,
        },
        {
            'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name),
            'docname': "kiwiq_pricing_strategy_doc",
            'initial_data': {"doc_data": """Tiered SaaS Pricing Model - Effective January 2025

Starter Plan: 299 USD/month
- 5 users
- 20 AI-generated articles per month
- Basic SEO optimization
- Email support
- Standard integrations

Growth Plan: 799 USD/month  
- 15 users
- 60 AI-generated articles per month
- Advanced SEO tools and keyword research
- Priority support with 4-hour SLA
- Custom integrations
- Content calendar and workflow tools
- Team collaboration features

Enterprise Plan: 2499 USD/month
- Unlimited users
- Unlimited AI-generated articles
- White-glove onboarding and training
- Dedicated account manager
- Custom AI model training on company data
- API access for custom integrations
- 99.9 percent uptime SLA
- Quarterly business reviews

Pricing Philosophy:
- Positioned 30 percent below Jasper AI but with superior B2B features
- Price based on value delivered (time saved times content quality)
- Annual contracts receive 20 percent discount
- Free 14-day trial with full features (no credit card required)

Competitive Positioning:
- Jasper AI: 50K USD/year enterprise - We're 60 percent less expensive with better B2B focus
- Copy.ai: Consumer focused - We offer enterprise features they lack
- Writesonic: Limited customization - We provide industry-specific models"""},
            'is_shared': False,
            'is_versioned': False,
            'is_system_entity': False,
        },
    ]

    # Add more example docs (kept smaller for brevity during tests)

    cleanup_docs: List[CleanupDocInfo] = [
        {'namespace': BLOG_COMPANY_NAMESPACE_TEMPLATE.format(item=company_name), 'docname': BLOG_COMPANY_DOCNAME, 'is_versioned': False, 'is_shared': False},
        {'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name), 'docname': "kiwiq_product_overview_doc_1", 'is_versioned': False, 'is_shared': False},
        {'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name), 'docname': "kiwiq_product_overview_doc_2", 'is_versioned': False, 'is_shared': False},
        {'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name), 'docname': "kiwiq_product_overview_doc_3", 'is_versioned': False, 'is_shared': False},
        {'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name), 'docname': "kiwiq_target_audience_analysis_1", 'is_versioned': False, 'is_shared': False},
        {'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name), 'docname': "kiwiq_pricing_strategy_doc", 'is_versioned': False, 'is_shared': False},
    ]
    
    print("\n--- Running Workflow Test ---")
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=TEST_INPUTS,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        setup_docs=setup_docs,
        cleanup_docs=cleanup_docs,
        validate_output_func=validate_output,
        stream_intermediate_results=True,
        poll_interval_sec=5,
        timeout_sec=3600  # 60 minutes for complete analysis
    )

if __name__ == "__main__":
    print("="*50)
    print("Company Analysis Workflow - Internal Documents & Reddit Research")
    print("="*50)
    logging.basicConfig(level=logging.INFO)
    
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        print("Async event loop already running. Scheduling task...")
        loop.create_task(main_test_company_analysis())
    else:
        print("Starting new async event loop...")
        asyncio.run(main_test_company_analysis())
