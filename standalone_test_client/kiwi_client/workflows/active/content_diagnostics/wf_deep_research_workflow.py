import asyncio
import logging
from typing import Dict, Any, Optional, List, Union, ClassVar, Type
import json
from enum import Enum

# Using Pydantic for easier schema generation
from pydantic import BaseModel, Field

# Internal dependencies
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

from kiwi_client.workflows.active.document_models.customer_docs import (
    # Deep Research Report
    BLOG_DEEP_RESEARCH_REPORT_DOCNAME,
    BLOG_DEEP_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
    BLOG_DEEP_RESEARCH_REPORT_IS_VERSIONED,
    BLOG_COMPANY_DOCNAME,
    BLOG_COMPANY_NAMESPACE_TEMPLATE,
    BLOG_DEEP_RESEARCH_REPORT_DOCNAME,
    BLOG_DEEP_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
    BLOG_DEEP_RESEARCH_REPORT_IS_VERSIONED,
    BLOG_COMPANY_DOCNAME,
    BLOG_COMPANY_NAMESPACE_TEMPLATE,
    BLOG_DEEP_RESEARCH_REPORT_DOCNAME,
    BLOG_DEEP_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
    BLOG_DEEP_RESEARCH_REPORT_IS_VERSIONED,
)

from kiwi_client.workflows.active.document_models.customer_docs import (
    LINKEDIN_USER_PROFILE_DOCNAME,
    LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
    LINKEDIN_SCRAPED_PROFILE_DOCNAME,
    LINKEDIN_SCRAPED_PROFILE_NAMESPACE_TEMPLATE,
    LINKEDIN_DEEP_RESEARCH_REPORT_DOCNAME,
    LINKEDIN_DEEP_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
    LINKEDIN_DEEP_RESEARCH_REPORT_IS_VERSIONED,
)

from kiwi_client.workflows.active.content_diagnostics.llm_inputs.deep_research_content_strategy import (
    # Content Strategy only schemas and prompts
    GENERATION_SCHEMA_FOR_DEEP_RESEARCH_BLOG_CONTENT_STRATEGY,
    SYSTEM_PROMPT_TEMPLATE_FOR_DEEP_RESEARCH_BLOG_CONTENT_STRATEGY,
    USER_PROMPT_TEMPLATE_FOR_DEEP_RESEARCH_BLOG_CONTENT_STRATEGY,
    # LinkedIn Research only schemas and prompts
    SCHEMA_TEMPLATE_FOR_LINKEDIN_RESEARCH,
    SYSTEM_PROMPT_TEMPLATE_FOR_LINKEDIN_RESEARCH,
    USER_PROMPT_TEMPLATE_FOR_LINKEDIN_RESEARCH,
    # Combined schemas and prompts
    GENERATION_SCHEMA_FOR_COMBINED_DEEP_RESEARCH,
    SYSTEM_PROMPT_TEMPLATE_FOR_COMBINED_DEEP_RESEARCH,
    USER_PROMPT_TEMPLATE_FOR_COMBINED_DEEP_RESEARCH,
)

# --- Workflow Configuration Constants ---

# LLM Configuration for Deep Research Model
LLM_PROVIDER = "openai"
LLM_MODEL = "o4-mini-deep-research"  # Deep research model
LLM_TEMPERATURE = 0.7
LLM_MAX_TOKENS = 100000

STRUCTURED_OUTPUT_PROVIDER = "anthropic"
STRUCTURED_OUTPUT_MODEL = "claude-sonnet-4-20250514"
STRUCTURED_OUTPUT_MAX_TOKENS = 4000

workflow_graph_schema = {
    "nodes": {
        # --- 1. Input Node with routing options ---
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "company_name": { "type": "str", "required": False, "description": "Name of the company to analyze" },
                    "entity_username": { "type": "str", "required": False, "description": "LinkedIn username for executive research" },
                    "run_blog_analysis": { "type": "bool", "required": True, "description": "Whether to run content strategy research" },
                    "run_linkedin_exec": { "type": "bool", "required": True, "description": "Whether to run LinkedIn research" }
                }
            }
        },
        
        # --- 2. Load Company Data ---
        "load_company_data": {
            "node_id": "load_company_data",
            "node_name": "load_customer_data",
            "node_config": {
                "load_paths": [
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": BLOG_COMPANY_NAMESPACE_TEMPLATE, 
                            "input_namespace_field": "company_name",
                            "static_docname": BLOG_COMPANY_DOCNAME,
                        },
                        "output_field_name": "company_data"
                    },
                ],
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False}
            },
        },
        
        # --- 3. Load LinkedIn Data (conditional) ---
        "load_linkedin_data": {
            "node_id": "load_linkedin_data",
            "node_name": "load_customer_data",
            "node_config": {
                "load_paths": [
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": LINKEDIN_USER_PROFILE_DOCNAME,
                        },
                        "output_field_name": "linkedin_user_profile"
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": LINKEDIN_SCRAPED_PROFILE_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": LINKEDIN_SCRAPED_PROFILE_DOCNAME,
                        },
                        "output_field_name": "linkedin_scraped_profile"
                    },
                ],
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False}
            },
        },
        
        # --- 4.a IfElse: decide combined vs single ---
        "if_combined": {
            "node_id": "if_combined",
            "node_name": "if_else_condition",
            "node_config": {
                "tagged_conditions": [
                    {
                        "tag": "both_selected",
                        "condition_groups": [
                            {
                                "conditions": [
                                    {"field": "run_blog_analysis", "operator": "equals", "value": True},
                                    {"field": "run_linkedin_exec", "operator": "equals", "value": True}
                                ],
                                "logical_operator": "and"
                            }
                        ],
                        "group_logical_operator": "and"
                    }
                ],
                "branch_logic_operator": "and"
            }
        },
        
        # --- 4. Router Node ---
        "route_research_type": {
            "node_id": "route_research_type",
            "node_name": "router_node",
            "node_config": {
                "choices": [
                    "construct_content_strategy_prompt",
                    "construct_linkedin_prompt",
                    "construct_combined_prompt",
                ],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {"choice_id": "construct_combined_prompt", "input_path": "branch", "target_value": "true_branch"},
                    {"choice_id": "construct_content_strategy_prompt", "input_path": "run_blog_analysis", "target_value": True},
                    {"choice_id": "construct_linkedin_prompt", "input_path": "run_linkedin_exec", "target_value": True}
                ],
            },
        },
        
        # --- 5. Prompt Constructors for Different Research Types ---
        "construct_content_strategy_prompt": {
            "node_id": "construct_content_strategy_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": USER_PROMPT_TEMPLATE_FOR_DEEP_RESEARCH_BLOG_CONTENT_STRATEGY,
                        "variables": {
                            "company_info": None,
                        },
                        "construct_options": {
                            "company_info": "company_data"
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": SYSTEM_PROMPT_TEMPLATE_FOR_DEEP_RESEARCH_BLOG_CONTENT_STRATEGY,
                        "variables": {
                            "schema": json.dumps(GENERATION_SCHEMA_FOR_DEEP_RESEARCH_BLOG_CONTENT_STRATEGY, indent=2)
                        },
                        "construct_options": {}
                    }
                }
            }
        },
        
        "construct_linkedin_prompt": {
            "node_id": "construct_linkedin_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": USER_PROMPT_TEMPLATE_FOR_LINKEDIN_RESEARCH,
                        "variables": {
                            "linkedin_user_profile": None,
                            "linkedin_scraped_profile": None
                        },
                        "construct_options": {
                            "linkedin_user_profile": "linkedin_user_profile",
                            "linkedin_scraped_profile": "linkedin_scraped_profile"
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": SYSTEM_PROMPT_TEMPLATE_FOR_LINKEDIN_RESEARCH,
                        "variables": {
                            "schema": json.dumps(SCHEMA_TEMPLATE_FOR_LINKEDIN_RESEARCH, indent=2)
                        },
                        "construct_options": {}
                    }
                }
            }
        },
        
        "construct_combined_prompt": {
            "node_id": "construct_combined_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": USER_PROMPT_TEMPLATE_FOR_COMBINED_DEEP_RESEARCH,
                        "variables": {
                            "company_info": None,
                            "linkedin_user_profile": None,
                            "linkedin_scraped_profile": None
                        },
                        "construct_options": {
                            "company_info": "company_data",
                            "linkedin_user_profile": "linkedin_user_profile",
                            "linkedin_scraped_profile": "linkedin_scraped_profile"
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": SYSTEM_PROMPT_TEMPLATE_FOR_COMBINED_DEEP_RESEARCH,
                        "variables": {
                            "schema": json.dumps(GENERATION_SCHEMA_FOR_COMBINED_DEEP_RESEARCH, indent=2)
                        },
                        "construct_options": {}
                    }
                }
            }
        },
        
        "construct_combined_structured_prompt": {
            "node_id": "construct_combined_structured_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": "You will be given a combined deep research report text. Extract and structure the information strictly according to the provided JSON schema. Only output valid JSON. Source text:\n{combined_text}",
                        "variables": {
                            "combined_text": None
                        },
                        "construct_options": {
                            "combined_text": "combined_text"
                        }
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": "You are a precise information extraction model. Produce strictly valid JSON that conforms exactly to this schema definition",
                        "variables": {},
                        "construct_options": {}
                    }
                }
            }
        },
 
        "structure_combined_output": {
            "node_id": "structure_combined_output",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": STRUCTURED_OUTPUT_PROVIDER,
                        "model": STRUCTURED_OUTPUT_MODEL
                    },
                    "temperature": 0.2,
                    "max_tokens": STRUCTURED_OUTPUT_MAX_TOKENS
                },
                "output_schema": {
                    "schema_definition": GENERATION_SCHEMA_FOR_COMBINED_DEEP_RESEARCH
                }
            }
        },

        # --- 7. Deep Research LLM Nodes for different research types ---
        "deep_researcher_content_strategy": {
            "node_id": "deep_researcher_content_strategy",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER, 
                        "model": LLM_MODEL
                    },
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS,
                },
                "output_schema": {
                },
                "tool_calling_config": {
                    "enable_tool_calling": True,
                    "parallel_tool_calls": True
                },
                "tools": [
                    {
                        "tool_name": "web_search_preview",
                        "is_provider_inbuilt_tool": True,
                    }
                ]
            }
        },
        
        "deep_researcher_linkedin": {
            "node_id": "deep_researcher_linkedin",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER, 
                        "model": LLM_MODEL
                    },
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS,
                },
                "output_schema": {
                },
                "tool_calling_config": {
                    "enable_tool_calling": True,
                    "parallel_tool_calls": True
                },
                "tools": [
                    {
                        "tool_name": "web_search_preview",
                        "is_provider_inbuilt_tool": True,
                    }
                ]
            }
        },
        
        "deep_researcher_combined": {
            "node_id": "deep_researcher_combined",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER, 
                        "model": LLM_MODEL
                    },
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS,
                },
                "output_schema": {},
                "tool_calling_config": {
                    "enable_tool_calling": True,
                    "parallel_tool_calls": True
                },
                "tools": [
                    {
                        "tool_name": "web_search_preview",
                        "is_provider_inbuilt_tool": True,
                    },
                    {
                        "tool_name": "code_interpreter",
                        "is_provider_inbuilt_tool": True,
                    }
                ]
            }
        },

        # --- 8. Transform nodes to extract reports from combined output ---
        "extract_content_strategy_report": {
            "node_id": "extract_content_strategy_report",
            "node_name": "transform_data",
            "node_config": {
                "mappings": [
                    {
                        "source_path": "content_strategy_research",
                        "destination_path": "content_strategy_report"
                    }
                ]
            }
        },
        
        "extract_linkedin_report": {
            "node_id": "extract_linkedin_report",
            "node_name": "transform_data",
            "node_config": {
                "mappings": [
                    {
                        "source_path": "linkedin_research",
                        "destination_path": "linkedin_report"
                    }
                ]
            }
        },
        
        # --- 9. Store Research Results - Separate nodes for each report type ---
        "store_blog_research": {
            "node_id": "store_blog_research",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {"is_versioned": BLOG_DEEP_RESEARCH_REPORT_IS_VERSIONED, "operation": "upsert"},
                "global_is_shared": False,
                "global_is_system_entity": False,
                "store_configs": [
                    {
                        "input_field_path": "content_strategy_report",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": BLOG_DEEP_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "company_name",
                                "static_docname": BLOG_DEEP_RESEARCH_REPORT_DOCNAME,
                            }
                        }
                    }
                ]
            }
        },
        
        "store_linkedin_research": {
            "node_id": "store_linkedin_research",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {"is_versioned": LINKEDIN_DEEP_RESEARCH_REPORT_IS_VERSIONED, "operation": "upsert"},
                "global_is_shared": False,
                "global_is_system_entity": False,
                "store_configs": [
                    {
                        "input_field_path": "linkedin_report",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": LINKEDIN_DEEP_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "entity_username",
                                "static_docname": LINKEDIN_DEEP_RESEARCH_REPORT_DOCNAME,
                            }
                        }
                    }
                ]
            }
        },

        # --- 10. Output Node ---
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {
                "dynamic_input_schema": {
                    "fields": {
                        "deep_research_results": {"type": "any", "required": False},
                        "blog_storage_paths": {"type": "any", "required": False},
                        "linkedin_storage_paths": {"type": "any", "required": False},
                        "research_type": {"type": "str", "required": False}
                    }
                }
            }
        },
    },

    "edges": [
        # --- Initial Setup: Store inputs to graph state ---
        {"src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"},
            {"src_field": "entity_username", "dst_field": "entity_username"},
            {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"},
            {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"},
        ]},
        
        # Route Data Loading -> Load Company Data (if run_blog_analysis is true)
        {"src_node_id": "input_node", "dst_node_id": "load_company_data", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"}
        ]},
        
        {"src_node_id": "load_company_data", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "company_data", "dst_field": "company_data"}
        ]},
        # Route Data Loading -> Load LinkedIn Data (if run_linkedin_exec is true)
        {"src_node_id": "load_company_data", "dst_node_id": "load_linkedin_data"},

        {"src_node_id": "$graph_state", "dst_node_id": "load_linkedin_data", "mappings": [
            {"src_field": "entity_username", "dst_field": "entity_username"}
        ]},

        {"src_node_id": "load_linkedin_data", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "linkedin_user_profile", "dst_field": "linkedin_user_profile"},
            {"src_field": "linkedin_scraped_profile", "dst_field": "linkedin_scraped_profile"}
        ]},
        
        {"src_node_id": "load_linkedin_data", "dst_node_id": "if_combined"},
        # State -> Router
        {"src_node_id": "$graph_state", "dst_node_id": "if_combined", "mappings": [
            {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"},
            {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"}
        ]},
        {"src_node_id": "if_combined", "dst_node_id": "route_research_type", "mappings": [
            {"src_field": "branch", "dst_field": "branch"}
        ]},
        {"src_node_id": "$graph_state", "dst_node_id": "route_research_type", "mappings": [
            {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"},
            {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"}
        ]},

        # Router -> Prompt constructors (control flow)
        {"src_node_id": "route_research_type", "dst_node_id": "construct_content_strategy_prompt"},
        {"src_node_id": "route_research_type", "dst_node_id": "construct_linkedin_prompt"},
        {"src_node_id": "route_research_type", "dst_node_id": "construct_combined_prompt"},
        
        # --- Content Strategy Path ---
        {"src_node_id": "$graph_state", "dst_node_id": "construct_content_strategy_prompt", "mappings": [
            {"src_field": "company_data", "dst_field": "company_data"}
        ]},
        {"src_node_id": "construct_content_strategy_prompt", "dst_node_id": "deep_researcher_content_strategy", "mappings": [
            {"src_field": "user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"}
        ]},
        {"src_node_id": "deep_researcher_content_strategy", "dst_node_id": "store_blog_research", "mappings": [
            {"src_field": "text_content", "dst_field": "content_strategy_report"}
        ]},
        
        # --- LinkedIn Path ---
        {"src_node_id": "$graph_state", "dst_node_id": "construct_linkedin_prompt", "mappings": [
            {"src_field": "linkedin_user_profile", "dst_field": "linkedin_user_profile"},
            {"src_field": "linkedin_scraped_profile", "dst_field": "linkedin_scraped_profile"}
        ]},
        {"src_node_id": "construct_linkedin_prompt", "dst_node_id": "deep_researcher_linkedin", "mappings": [
            {"src_field": "user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"}
        ]},
        {"src_node_id": "deep_researcher_linkedin", "dst_node_id": "store_linkedin_research", "mappings": [
            {"src_field": "text_content", "dst_field": "linkedin_report"}
        ]},
        
        # --- Combined Path ---
        {"src_node_id": "$graph_state", "dst_node_id": "construct_combined_prompt", "mappings": [
            {"src_field": "company_data", "dst_field": "company_data"},
            {"src_field": "linkedin_user_profile", "dst_field": "linkedin_user_profile"},
            {"src_field": "linkedin_scraped_profile", "dst_field": "linkedin_scraped_profile"}
        ]},
        {"src_node_id": "construct_combined_prompt", "dst_node_id": "deep_researcher_combined", "mappings": [
            {"src_field": "user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"}
        ]},
        {"src_node_id": "deep_researcher_combined", "dst_node_id": "construct_combined_structured_prompt", "mappings": [
            {"src_field": "text_content", "dst_field": "combined_text"}
        ]},
        {"src_node_id": "construct_combined_structured_prompt", "dst_node_id": "structure_combined_output", "mappings": [
            {"src_field": "user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"}
        ]},
        
        # Combined -> State (store full output)
        {"src_node_id": "structure_combined_output", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "combined_output"}
        ]},
        
        # State -> Extract reports (pass combined output to transform nodes)
        {"src_node_id": "structure_combined_output", "dst_node_id": "extract_content_strategy_report", "mappings": [
            {"src_field": "structured_output", "dst_field": "content_strategy_research"}
        ]},
        {"src_node_id": "structure_combined_output", "dst_node_id": "extract_linkedin_report", "mappings": [
            {"src_field": "structured_output", "dst_field": "linkedin_research"}
        ]},
        
        # Extract -> Store
        {"src_node_id": "extract_content_strategy_report", "dst_node_id": "store_blog_research", "mappings": [
            {"src_field": "transformed_data", "dst_field": "content_strategy_report"}
        ]},

        # State -> Store nodes (for namespace fields)
        {"src_node_id": "$graph_state", "dst_node_id": "store_blog_research", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"}
        ]},

        {"src_node_id": "extract_linkedin_report", "dst_node_id": "store_linkedin_research", "mappings": [
            {"src_field": "transformed_data", "dst_field": "linkedin_report"}
        ]},

        {"src_node_id": "$graph_state", "dst_node_id": "store_linkedin_research", "mappings": [
            {"src_field": "entity_username", "dst_field": "entity_username"}
        ]},
        # Store -> Output
        {"src_node_id": "store_blog_research", "dst_node_id": "output_node", "mappings": [
            {"src_field": "paths_processed", "dst_field": "blog_storage_paths"}
        ]},
        {"src_node_id": "store_linkedin_research", "dst_node_id": "output_node", "mappings": [
            {"src_field": "paths_processed", "dst_field": "linkedin_storage_paths"}
        ]},

    ],

    # --- Define Start and End ---
    "input_node_id": "input_node",
    "output_node_id": "output_node",
    
    # --- State Reducers ---
    "metadata": {
        "$graph_state": {
            "reducer": {
                "company_name": "replace",
                "entity_username": "replace",
                "run_blog_analysis": "replace",
                "run_linkedin_exec": "replace",
                "company_data": "replace",
                "linkedin_user_profile": "replace",
                "linkedin_scraped_profile": "replace",
                "linkedin_exec_context": "replace",
                "combined_output": "replace",
                "research_type": "replace",
            }
        }
    }
}

# --- Test Execution Logic ---
async def main_test_deep_research_workflow():
    """
    Test for B2B Content Strategy Deep Research Workflow.
    """
    test_name = "B2B Content Strategy Deep Research Workflow Test"
    print(f"--- Starting {test_name} ---")

    # Test inputs with routing options
    test_inputs = {
        "company_name": "kiwiq",
        "entity_username": "jmkmba",  # Example LinkedIn username
        "run_blog_analysis": True,  # Can be True/False
        "run_linkedin_exec": True,  # Can be True/False - set both to True for combined research
    }
    # Company document data that will be loaded
    COMPANY_DOCUMENT_DATA = {
        "name": "KiwiQ",
        "website_url": "https://writer.com",
        "value_proposition": "Enterprise-grade AI writing platform that combines content creation with intelligent workflow automation",
        "icp": {
            "icp_name": "Marketing Director",
            "target_industry": "Technology / B2B SaaS",
            "company_size": "Mid to large enterprise",
            "buyer_persona": "Senior marketing professional responsible for content strategy and lead generation",
            "pain_points": [
                "Manual content creation is time-consuming",
                "Difficulty maintaining consistent brand voice",
                "Limited content ROI measurement",
                "Scaling content production efficiently"
            ],
            "goals": [
                "Increase enterprise customer acquisition and retention",
                "Establish thought leadership in AI writing space",
                "Improve content ROI for customers",
                "Streamline content creation workflows"
            ]
        },
        "competitors": [
            {
                "name": "Grammarly Business",
                "website_url": "https://www.grammarly.com/business"
            },
            {
                "name": "Jasper AI",
                "website_url": "https://www.jasper.ai"
            },
            {
                "name": "Copy.ai",
                "website_url": "https://www.copy.ai"
            }
        ]
    }
    
    # LinkedIn profile data that will be loaded (if LinkedIn research is enabled)
    LINKEDIN_PROFILE_DATA = {
        "username": "jmkmba",
        "full_name": "Jayaram M",
        "headline": "AI Sales & GTM Leader | Revenue Orchestration | RevOps Strategy",
        "summary": "Go-to-market and revenue operations leader focused on AI-driven workflows, data quality, and pipeline execution.",
        "experience": [
            {"title": "Head of GTM", "company": "Momentum", "duration": "2+ years"},
            {"title": "Revenue Operations Leader", "company": "Prior Companies", "duration": "5+ years"}
        ],
        "skills": ["Revenue Operations", "Sales Strategy", "AI in GTM", "Salesforce"],
    }
    
    LINKEDIN_SCRAPED_DATA = {
        "profile_url": "https://www.linkedin.com/in/jmkmba/",
        "full_name": "Jayaram M",
        "headline": "AI Sales & GTM Leader | Revenue Orchestration | RevOps Strategy",
        "location": "San Francisco Bay Area",
        "about": "Go-to-market and revenue operations leader focused on AI-driven workflows, data quality, and pipeline execution.",
        "current_position": {
            "title": "Head of GTM",
            "company": "Momentum",
            "duration": "2 yrs 3 mos"
        },
        "past_positions": [
            {
                "title": "Revenue Operations Leader",
                "company": "Prior Companies",
                "duration": "5 yrs 1 mo"
            }
        ],
        "education": [
            {
                "school": "Stanford University",
                "degree": "MBA",
                "years": "2015 – 2017"
            }
        ],
        "skills": [
            "Revenue Operations",
            "Sales Strategy",
            "AI in GTM",
            "Salesforce"
        ],
        "follower_count": 15000,
        "connection_count": 500,
    }
    # Setup documents - create company and LinkedIn profile documents
    setup_docs: List[SetupDocInfo] = [
        SetupDocInfo(
            docname=BLOG_COMPANY_DOCNAME,
            namespace=BLOG_COMPANY_NAMESPACE_TEMPLATE.format(item="kiwiq"),
            initial_data=COMPANY_DOCUMENT_DATA,
            is_versioned=False,
            is_shared=False,
            is_system_entity=False
        )
    ]
    
    # Add LinkedIn documents if LinkedIn research is enabled
    if test_inputs.get("run_linkedin_exec"):
        setup_docs.extend([
            SetupDocInfo(
                docname=LINKEDIN_USER_PROFILE_DOCNAME,
                namespace=LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE.format(item="jmkmba"),
                initial_data=LINKEDIN_PROFILE_DATA,
                is_versioned=False,
                is_shared=False,
                is_system_entity=False
            ),
            SetupDocInfo(
                docname=LINKEDIN_SCRAPED_PROFILE_DOCNAME,
                namespace=LINKEDIN_SCRAPED_PROFILE_NAMESPACE_TEMPLATE.format(item="jmkmba"),
                initial_data=LINKEDIN_SCRAPED_DATA,
                is_versioned=False,
                is_shared=False,
                is_system_entity=False
            )
        ])
    
    # No cleanup documents needed
    cleanup_docs: List[CleanupDocInfo] = []

    # No predefined HITL inputs needed
    predefined_hitl_inputs = []

    # Output validation function
    async def validate_deep_research_output(outputs, test_inputs=test_inputs) -> bool:
        """
        Validates the output from the deep research workflow.
        
        Args:
            outputs: The workflow output dictionary to validate
            
        Returns:
            bool: True if validation passes, raises AssertionError otherwise
        """
        assert outputs is not None, "Validation Failed: Workflow returned no outputs."
        
        # Check that we have the expected output fields
        expected_fields = ['deep_research_results']
        for field in expected_fields:
            assert field in outputs, f"Validation Failed: '{field}' missing from outputs."
        
        # Validate deep research results structure based on what was run
        research_results = outputs.get('deep_research_results', {})
        run_content = test_inputs.get('run_blog_analysis', False)
        run_linkedin = test_inputs.get('run_linkedin_exec', False)
        
        if run_content and run_linkedin:
            # Combined research should have both sections
            assert 'content_strategy_research' in research_results, "Combined research missing 'content_strategy_research'"
            assert 'linkedin_research' in research_results, "Combined research missing 'linkedin_research'"
        elif run_content:
            # Content strategy only
            assert 'industry_best_practices' in research_results, "Research results missing 'industry_best_practices'"
            assert 'funnel_stage_analysis' in research_results, "Research results missing 'funnel_stage_analysis'"
        elif run_linkedin:
            # LinkedIn only
            assert 'peer_category_benchmark' in research_results, "LinkedIn research missing 'peer_category_benchmark'"
            assert 'industry_trend_research' in research_results, "LinkedIn research missing 'industry_trend_research'"
            assert 'audience_topic_intelligence' in research_results, "LinkedIn research missing 'audience_topic_intelligence'"
        
        # Validate storage paths based on what was run
        if run_content:
            blog_paths = outputs.get('blog_storage_paths', [])
            assert isinstance(blog_paths, list), "Blog storage paths should be a list"
            assert len(blog_paths) > 0, "Blog storage paths should not be empty"
        
        if run_linkedin:
            linkedin_paths = outputs.get('linkedin_storage_paths', [])
            assert isinstance(linkedin_paths, list), "LinkedIn storage paths should be a list"
            assert len(linkedin_paths) > 0, "LinkedIn storage paths should not be empty"
        
        # Check combined output structure if both were run
        if run_content and run_linkedin:
            content_strategy = research_results.get('content_strategy_research', {})
            linkedin_research = research_results.get('linkedin_research', {})
            
            # Validate content strategy section
            if content_strategy:
                assert 'industry_best_practices' in content_strategy, "Content strategy missing 'industry_best_practices'"
                assert 'funnel_stage_analysis' in content_strategy, "Content strategy missing 'funnel_stage_analysis'"
            
            # Validate LinkedIn section
            if linkedin_research:
                assert 'peer_category_benchmark' in linkedin_research, "LinkedIn missing 'peer_category_benchmark'"
                assert 'industry_trend_research' in linkedin_research, "LinkedIn missing 'industry_trend_research'"
        
        # Check if web search was used (optional)
        web_search_result = outputs.get('web_search_result')
        if web_search_result:
            print(f"✓ Web search was used - found search results")
            if 'citations' in web_search_result and web_search_result['citations']:
                print(f"✓ Citations found: {len(web_search_result['citations'])} sources")
        
        # Check if tools were called (optional)
        tool_calls = outputs.get('tool_calls')
        if tool_calls:
            print(f"✓ Tool calls made: {len(tool_calls)} calls")
        
        # Check metadata if available
        metadata = outputs.get('metadata')
        if metadata:
            print(f"✓ Model used: {metadata.get('model_name', 'unknown')}")
            print(f"✓ Total tokens: {metadata.get('token_usage', {}).get('total_tokens', 0)}")
            print(f"✓ Latency: {metadata.get('latency', 0):.2f}s")
        
        # Log success message
        print(f"✓ Deep research workflow validated successfully")
        if run_content:
            print(f"✓ Content strategy research completed and stored")
        if run_linkedin:
            print(f"✓ LinkedIn research completed and stored")
        
        return True

    # Execute the test
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=test_inputs,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=predefined_hitl_inputs,
        setup_docs=setup_docs,
        cleanup_docs_created_by_setup=False,
        cleanup_docs=cleanup_docs,
        validate_output_func=validate_deep_research_output,
        stream_intermediate_results=True,
        poll_interval_sec=5,
        timeout_sec=1800  # 30 minutes timeout for deep research tasks
    )

    print(f"--- {test_name} Finished ---")
    
    if final_run_outputs:
        # Display key results
        research_results = final_run_outputs.get('deep_research_results', {})
        blog_paths = final_run_outputs.get('blog_storage_paths', [])
        linkedin_paths = final_run_outputs.get('linkedin_storage_paths', [])
        metadata = final_run_outputs.get('metadata', {})
        
        print(f"\n=== DEEP RESEARCH RESULTS ===")
        print(f"Research Type: {'Combined' if test_inputs.get('run_blog_analysis') and test_inputs.get('run_linkedin_exec') else 'Content Strategy' if test_inputs.get('run_blog_analysis') else 'LinkedIn'}")
        print(f"Model: {metadata.get('model_name', 'unknown')}")
        print(f"Total Tokens: {metadata.get('token_usage', {}).get('total_tokens', 0)}")
        print(f"Tool Calls: {metadata.get('tool_call_count', 0)}")
        print(f"Latency: {metadata.get('latency', 0):.2f}s")
        
        # Show results based on research type
        if test_inputs.get('run_blog_analysis') and test_inputs.get('run_linkedin_exec'):
            # Combined research
            content_strategy = research_results.get('content_strategy_research', {})
            linkedin_research = research_results.get('linkedin_research', {})
            
            if content_strategy:
                print(f"\n=== CONTENT STRATEGY RESEARCH ===")
                best_practices = content_strategy.get('industry_best_practices', {})
                if best_practices:
                    print(f"Content patterns identified: {len(best_practices.get('successful_content_patterns', []))}")
            
            if linkedin_research:
                print(f"\n=== LINKEDIN RESEARCH ===")
                peers = linkedin_research.get('peer_category_benchmark', {}).get('peers', [])
                print(f"Peers analyzed: {len(peers)}")
        elif test_inputs.get('run_blog_analysis'):
            # Content strategy only
            print(f"\n=== CONTENT STRATEGY RESULTS ===")
            best_practices = research_results.get('industry_best_practices', {})
            if best_practices:
                content_mix = best_practices.get('content_mix_benchmark', {})
                print(f"Content mix recommendations provided")
        elif test_inputs.get('run_linkedin_exec'):
            # LinkedIn only
            print(f"\n=== LINKEDIN RESULTS ===")
            peer_benchmark = research_results.get('peer_category_benchmark', {})
            if peer_benchmark:
                peers = peer_benchmark.get('peers', [])
                print(f"Peers analyzed: {len(peers)}")
        
        # Show content mix benchmark
        best_practices = research_results.get('industry_best_practices', {})
        content_mix = best_practices.get('content_mix_benchmark', {})
        if content_mix:
            print(f"\n=== CONTENT MIX BENCHMARK ===")
            for content_type, percentage in content_mix.items():
                if isinstance(percentage, (int, float)):
                    print(f"{content_type.replace('_', ' ').title()}: {percentage}%")
        
        # Show funnel stage analysis
        funnel_analysis = research_results.get('funnel_stage_analysis', [])
        if funnel_analysis:
            print(f"\n=== FUNNEL STAGE ANALYSIS ===")
            for stage_data in funnel_analysis[:3]:  # Show first 3 stages
                stage = stage_data.get('stage', 'Unknown')
                allocation = stage_data.get('content_allocation', {})
                share_pct = allocation.get('recommended_share_pct', 0)
                print(f"{stage}: {share_pct}% allocation")
        
        # Show web search results if available
        web_search_result = final_run_outputs.get('web_search_result')
        if web_search_result and web_search_result.get('citations'):
            print(f"\n=== SOURCES USED ===")
            for i, citation in enumerate(web_search_result['citations'][:3], 1):  # Show first 3 sources
                print(f"{i}. {citation.get('title', 'No title')}")
                print(f"   URL: {citation.get('url', 'No URL')}")
                print()
        
        print(f"\n=== END RESULTS ===")

if __name__ == "__main__":
    try:
        asyncio.run(main_test_deep_research_workflow())
    except KeyboardInterrupt:
        print("\nExecution interrupted.")
    except Exception as e:
        print(f"\nError running test: {e}")
        import traceback
        traceback.print_exc()
