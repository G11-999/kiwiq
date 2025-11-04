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

from kiwi_client.workflows.active.content_diagnostics.company_analysis_workflow_sandbox.wf_llm_inputs import (
    # LLM Configuration
    OPENAI_PROVIDER,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    OPENAI_MAX_TOKENS,
    PERPLEXITY_PROVIDER,
    PERPLEXITY_MODEL,
    PERPLEXITY_TEMPERATURE,
    PERPLEXITY_MAX_TOKENS,
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

# Batching Configuration
DOCUMENT_BATCH_SIZE = 5

# --- Workflow Graph Definition ---
workflow_graph_schema = {
    "nodes": {
        # --- 1. Input Node ---
        "input_node": {
            "node_id": "input_node",
            "node_category": "system",
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
            "node_category": "system",
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
            "node_category": "system",
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

                # --- 3.7. Construct Perplexity Research Prompt (for sufficient content path) ---
        "construct_perplexity_research_prompt": {
            "node_id": "construct_perplexity_research_prompt",
            "node_category": "research",
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
            "node_category": "research",
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

        # --- 3.5. Route Based on Content Sufficiency ---
        "route_content_path": {
            "node_id": "route_content_path",
            "node_category": "system",
            "node_name": "router_node",
            "node_config": {
                "choices": ["merge_document_lists", "batch_company_documents"],
                "allow_multiple": False,
                "default_choice": "merge_document_lists",
                "choices_with_conditions": [
                    {
                        "choice_id": "batch_company_documents",
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
            "node_category": "system",
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

        # --- 4a. Batch Documents for Insufficient Content Path ---
        "batch_merged_documents": {
            "node_id": "batch_merged_documents",
            "node_category": "system",
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
            "node_category": "system",
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
            "node_category": "analysis",
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
                            "documents_batch": "",
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
            "node_category": "analysis",
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
            "node_category": "analysis",
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
            "node_category": "analysis",
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
            "node_category": "research",
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
            "node_category": "research",
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
            "node_category": "system",
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
            "node_category": "research",
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
            "node_category": "research",
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
            "node_category": "analysis",
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
            "node_category": "analysis",
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
            "node_category": "system",
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
            "node_category": "system",
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
            "node_category": "system",
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
        {"src_node_id": "load_company_context", "dst_node_id": "construct_perplexity_research_prompt", "mappings": []},

                # Pass company_context to construct_perplexity_research_prompt (sufficient content path)
        {"src_node_id": "$graph_state", "dst_node_id": "construct_perplexity_research_prompt", "mappings": [
            {"src_field": "company_context", "dst_field": "company_context"}
        ]},

                # Perplexity research flow (sufficient content path)
        {"src_node_id": "construct_perplexity_research_prompt", "dst_node_id": "execute_perplexity_research", "mappings": [
            {"src_field": "perplexity_user_prompt", "dst_field": "user_prompt"},
            {"src_field": "perplexity_system_prompt", "dst_field": "system_prompt"}
        ]},
        {"src_node_id": "execute_perplexity_research", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "perplexity_research"}
        ]},

        {"src_node_id": "execute_perplexity_research", "dst_node_id": "route_content_path", "mappings": []},


        # Pass has_insufficient_blog_and_page_count to router
        {"src_node_id": "$graph_state", "dst_node_id": "route_content_path", "mappings": [
            {"src_field": "has_insufficient_blog_and_page_count", "dst_field": "has_insufficient_blog_and_page_count"}
        ]},

        # Router to merge_document_lists (insufficient content path)
        {"src_node_id": "route_content_path", "dst_node_id": "merge_document_lists", "mappings": []},

        # Router to construct_perplexity_research_prompt (sufficient content path)
        {"src_node_id": "route_content_path", "dst_node_id": "batch_company_documents", "mappings": []},

        # Pass company_documents and scraped_data to merge node (insufficient content path)
        {"src_node_id": "$graph_state", "dst_node_id": "merge_document_lists", "mappings": [
            {"src_field": "company_documents", "dst_field": "company_documents"},
            {"src_field": "scraped_data", "dst_field": "scraped_data"}
        ]},

        # Store documents in state
        {"src_node_id": "merge_document_lists", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "merged_data", "dst_field": "merged_data"}
        ]},
        
        # Flow to batch documents - Insufficient content path
        {"src_node_id": "merge_document_lists", "dst_node_id": "batch_merged_documents", "mappings": []},
        {"src_node_id": "$graph_state", "dst_node_id": "batch_merged_documents", "mappings": [
            {"src_field": "merged_data", "dst_field": "merged_data"}
        ]},

        # Flow to batch documents - Sufficient content path          
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