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
    LITE_BLOG_DEEP_RESEARCH_REPORT_DOCNAME,
    LITE_BLOG_DEEP_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
    LITE_BLOG_DEEP_RESEARCH_REPORT_IS_VERSIONED,
    LITE_BLOG_COMPANY_DOCNAME,
    LITE_BLOG_COMPANY_NAMESPACE_TEMPLATE,
    LITE_BLOG_DEEP_RESEARCH_REPORT_DOCNAME,
    LITE_BLOG_DEEP_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
    LITE_BLOG_DEEP_RESEARCH_REPORT_IS_VERSIONED,
    LITE_BLOG_COMPANY_DOCNAME,
    LITE_BLOG_COMPANY_NAMESPACE_TEMPLATE,
    LITE_BLOG_DEEP_RESEARCH_REPORT_DOCNAME,
    LITE_BLOG_DEEP_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
    LITE_BLOG_DEEP_RESEARCH_REPORT_IS_VERSIONED,
    LITE_LINKEDIN_USER_PROFILE_DOCNAME,
    LITE_LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
    LITE_LINKEDIN_SCRAPED_PROFILE_DOCNAME,
    LITE_LINKEDIN_SCRAPED_PROFILE_NAMESPACE_TEMPLATE,
    LITE_LINKEDIN_DEEP_RESEARCH_REPORT_DOCNAME,
    LITE_LINKEDIN_DEEP_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
    LITE_LINKEDIN_DEEP_RESEARCH_REPORT_IS_VERSIONED,
)

from kiwi_client.workflows.active.content_diagnostics_LITE_version.llm_inputs.deep_research_content_strategy import (
    # Content Strategy only schemas and prompts
    GENERATION_SCHEMA_FOR_DEEP_RESEARCH_BLOG_CONTENT_STRATEGY,
    SYSTEM_PROMPT_TEMPLATE_FOR_DEEP_RESEARCH_BLOG_CONTENT_STRATEGY,
    USER_PROMPT_TEMPLATE_FOR_DEEP_RESEARCH_BLOG_CONTENT_STRATEGY,
    # LinkedIn Research only schemas and prompts
    SCHEMA_TEMPLATE_FOR_LINKEDIN_RESEARCH,
    SYSTEM_PROMPT_TEMPLATE_FOR_LINKEDIN_RESEARCH,
    USER_PROMPT_TEMPLATE_FOR_LINKEDIN_RESEARCH,
)

# --- Workflow Configuration Constants ---

# LLM Configuration for Deep Research Model
LLM_PROVIDER = "perplexity"
LLM_MODEL = "sonar-deep-research"  # Deep research model
LLM_TEMPERATURE = 0.8
LLM_MAX_TOKENS = 16384
MAX_TOOL_CALLS = 30

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

        "document_router": {
            "node_id": "document_router",
            "node_name": "router_node",
            "node_config": {
                "choices": [
                    "load_company_data",
                    "load_linkedin_data"
                ],
                "allow_multiple": True,
                "default_choice": None,
                "choices_with_conditions": [
                    {"choice_id": "load_company_data", "input_path": "run_blog_analysis", "target_value": True},
                    {"choice_id": "load_linkedin_data", "input_path": "run_linkedin_exec", "target_value": True}
                ]
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
                                                    "input_namespace_field_pattern": LITE_BLOG_COMPANY_NAMESPACE_TEMPLATE,
                        "input_namespace_field": "company_name",
                        "static_docname": LITE_BLOG_COMPANY_DOCNAME,
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
                                                    "input_namespace_field_pattern": LITE_LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE,
                        "input_namespace_field": "entity_username",
                        "static_docname": LITE_LINKEDIN_USER_PROFILE_DOCNAME,
                        },
                        "output_field_name": "linkedin_user_profile"
                    },
                    {
                        "filename_config": {
                                                    "input_namespace_field_pattern": LITE_LINKEDIN_SCRAPED_PROFILE_NAMESPACE_TEMPLATE,
                        "input_namespace_field": "entity_username",
                        "static_docname": LITE_LINKEDIN_SCRAPED_PROFILE_DOCNAME,
                        },
                        "output_field_name": "linkedin_scraped_profile"
                    },
                ],
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False}
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
                    "max_tool_calls": MAX_TOOL_CALLS,
                    "max_tokens": LLM_MAX_TOKENS,
                },
                "output_schema": {
                },
                "tool_calling_config": {
                    "enable_tool_calling": True,
                    "parallel_tool_calls": True
                },
                # "tools": [
                #     {
                #         "tool_name": "web_search_preview",
                #         "is_provider_inbuilt_tool": True,
                #     }
                # ]
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
                    "max_tool_calls": 20,
                },
                "output_schema": {
                },
                "tool_calling_config": {
                    "enable_tool_calling": True,
                    "parallel_tool_calls": True
                },
                # "tools": [
                #     {
                #         "tool_name": "web_search_preview",
                #         "is_provider_inbuilt_tool": True,
                #     }
                # ]
            }
        },
        
        # --- 9. Store Research Results - Separate nodes for each report type ---
        "store_blog_research": {
            "node_id": "store_blog_research",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {"is_versioned": LITE_BLOG_DEEP_RESEARCH_REPORT_IS_VERSIONED, "operation": "upsert"},
                "global_is_shared": False,
                "global_is_system_entity": False,
                "store_configs": [
                    {
                        "input_field_path": "content_strategy_report",
                        "target_path": {
                            "filename_config": {
                                                            "input_namespace_field_pattern": LITE_BLOG_DEEP_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": LITE_BLOG_DEEP_RESEARCH_REPORT_DOCNAME,
                            }
                        },
                        "extra_fields": [
                            {"src_path": "web_search_result", "dst_path": "web_search_result"}
                        ]
                    },
                    
                ]
            }
        },
        
        "store_linkedin_research": {
            "node_id": "store_linkedin_research",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {"is_versioned": LITE_LINKEDIN_DEEP_RESEARCH_REPORT_IS_VERSIONED, "operation": "upsert"},
                "global_is_shared": False,
                "global_is_system_entity": False,
                "store_configs": [
                    {
                        "input_field_path": "linkedin_report",
                        "target_path": {
                            "filename_config": {
                                                            "input_namespace_field_pattern": LITE_LINKEDIN_DEEP_RESEARCH_REPORT_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "entity_username",
                            "static_docname": LITE_LINKEDIN_DEEP_RESEARCH_REPORT_DOCNAME,
                            }
                        },
                        "extra_fields": [
                            {"src_path": "web_search_result", "dst_path": "web_search_result"}
                        ]
                    }
                ]
            }
        },

        # --- 10. Output Node ---
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "defer_node": True,
            "node_config": {}
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

        {"src_node_id": "input_node", "dst_node_id": "document_router", "mappings": [
            {"src_field": "run_blog_analysis", "dst_field": "run_blog_analysis"},
            {"src_field": "run_linkedin_exec", "dst_field": "run_linkedin_exec"}
        ]},

        {"src_node_id": "document_router", "dst_node_id": "load_company_data", "mappings": []}, 
        {"src_node_id": "document_router", "dst_node_id": "load_linkedin_data", "mappings": []},
        
        # Route Data Loading -> Load Company Data (if run_blog_analysis is true)
        {"src_node_id": "$graph_state", "dst_node_id": "load_company_data", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"}
        ]},

        {"src_node_id": "$graph_state", "dst_node_id": "load_linkedin_data", "mappings": [
            {"src_field": "entity_username", "dst_field": "entity_username"}
        ]},
        
        {"src_node_id": "load_company_data", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "company_data", "dst_field": "company_data"}
        ]},

        {"src_node_id": "load_linkedin_data", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "linkedin_user_profile", "dst_field": "linkedin_user_profile"},
            {"src_field": "linkedin_scraped_profile", "dst_field": "linkedin_scraped_profile"}
        ]},

        # Router -> Prompt constructors (control flow)
        {"src_node_id": "load_company_data", "dst_node_id": "construct_content_strategy_prompt"},
        {"src_node_id": "load_linkedin_data", "dst_node_id": "construct_linkedin_prompt"},
        
        # --- Content Strategy Path ---
        {"src_node_id": "$graph_state", "dst_node_id": "construct_content_strategy_prompt", "mappings": [
            {"src_field": "company_data", "dst_field": "company_data"}
        ]},
        {"src_node_id": "construct_content_strategy_prompt", "dst_node_id": "deep_researcher_content_strategy", "mappings": [
            {"src_field": "user_prompt", "dst_field": "user_prompt"},
            {"src_field": "system_prompt", "dst_field": "system_prompt"}
        ]},
        {"src_node_id": "deep_researcher_content_strategy", "dst_node_id": "store_blog_research", "mappings": [
            {"src_field": "text_content", "dst_field": "content_strategy_report"},
            {"src_field": "web_search_result", "dst_field": "web_search_result"}
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
            {"src_field": "text_content", "dst_field": "linkedin_report"},
            {"src_field": "web_search_result", "dst_field": "web_search_result"}
        ]},

        # State -> Store nodes (for namespace fields)
        {"src_node_id": "$graph_state", "dst_node_id": "store_blog_research", "mappings": [
            {"src_field": "company_name", "dst_field": "company_name"}
        ]},

        {"src_node_id": "$graph_state", "dst_node_id": "store_linkedin_research", "mappings": [
            {"src_field": "entity_username", "dst_field": "entity_username"}
        ]},

        # Store -> Output
        {"src_node_id": "store_blog_research", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "paths_processed", "dst_field": "blog_storage_paths"}
        ]},
        {"src_node_id": "store_linkedin_research", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "paths_processed", "dst_field": "linkedin_storage_paths"}
        ]},

        {"src_node_id": "store_blog_research", "dst_node_id": "output_node", "mappings": [
        ]},
        {"src_node_id": "store_linkedin_research", "dst_node_id": "output_node", "mappings": [
        ]},

        {"src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
            {"src_field": "blog_storage_paths", "dst_field": "blog_storage_paths"},
            {"src_field": "linkedin_storage_paths", "dst_field": "linkedin_storage_paths"}
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
        "company_name": "otter",
        "entity_username": "samliang",  # Example LinkedIn username
        "run_blog_analysis": True,  # Can be True/False
        "run_linkedin_exec": True,  # Can be True/False - set both to True for combined research
    }
    # Company document data that will be loaded
    COMPANY_DOCUMENT_DATA = {
"name": "otter.ai",
"website_url": "https://otter.ai",
"value_proposition": "AI meeting assistant that transcribes, summarizes, and automates follow-ups to boost team productivity across meetings, calls, and interviews",
"icp": {
"icp_name": "Marketing Director",
"target_industry": "Technology / B2B SaaS",
"company_size": "Mid to large enterprise",
"buyer_persona": "Senior marketing professional responsible for content strategy, team collaboration, and pipeline-driving meetings",
"pain_points": [
"Manual note-taking during meetings reduces focus and misses key details",
"Inconsistent documentation and poor knowledge transfer across teams",
"Difficulty turning meetings into actionable tasks and content assets",
"Limited visibility into meeting insights and follow-ups across stakeholders"
],
"goals": [
"Increase meeting productivity and reduce time spent on note-taking",
"Standardize meeting documentation and accelerate cross-functional alignment",
"Automatically generate action items and summaries to speed execution",
"Repurpose customer and internal meeting insights into content and enablement"
]
},
"competitors": [
{
"name": "Fireflies.ai",
"website_url": "https://fireflies.ai"
},
{
"name": "Fathom",
"website_url": "https://fathom.video"
},
{
"name": "Microsoft Copilot (Teams Premium)",
"website_url": "https://www.microsoft.com/microsoft-teams/premium"
}
]
}
    
    # LinkedIn profile data that will be loaded (if LinkedIn research is enabled)
    LINKEDIN_PROFILE_DATA = {
"username": "samliang",
"full_name": "Sam Liang",
"headline": "Co-founder & CEO at Otter.ai | Stanford PhD | Ex-Google Maps Location Platform Lead",
"summary": "Founder-CEO focused on AI meeting assistants that transcribe, summarize, and activate knowledge from conversations. Previously led Google’s Maps Location Platform; founded Alohar Mobile (acquired). Stanford PhD in Electrical Engineering.",
"experience": [
{ "title": "CEO & Co-founder", "company": "Otter.ai", "duration": "2016 – Present" },
{ "title": "CEO & Co-founder", "company": "Alohar Mobile", "duration": "2010 – 2013 (acquired)" },
{ "title": "Lead, Maps Location Platform & API", "company": "Google", "duration": "2006 – 2010" }
],
"skills": ["Artificial Intelligence", "Speech Recognition", "NLP", "Distributed Systems", "Product-Led Growth", "Location Services"]
}
    
    LINKEDIN_SCRAPED_DATA = {
"profile_url": "https://www.linkedin.com/in/samliang",
"full_name": "Sam Liang",
"headline": "Co-founder & CEO at Otter.ai | Stanford PhD | Ex-Google Maps Location Platform Lead",
"location": "Mountain View, California",
"about": "Founder-CEO building AI meeting assistants that transcribe, summarize, and activate knowledge from conversations. Previously led Google’s Map Location Platform; founder/CEO of Alohar Mobile (acquired). Stanford PhD in EE focused on large-scale distributed systems.",
"current_position": {
"title": "CEO & Co-founder",
"company": "Otter.ai",
"duration": "Feb 2016 – Present"
},
"past_positions": [
{
"title": "CEO & Co-founder",
"company": "Alohar Mobile",
"duration": "2010 – 2013 (acquired by AutoNavi/Alibaba)"
},
{
"title": "Lead, Google Map Location Platform & API",
"company": "Google",
"duration": "2006 – 2010"
},
{
"title": "Member",
"company": "Forbes Technology Council",
"duration": "Jun 2020 – Jun 2021"
}
],
"education": [
{
"school": "Stanford University",
"degree": "Ph.D., Electrical Engineering",
"years": ""
}
],
"skills": [
"Artificial Intelligence",
"Speech Recognition",
"NLP",
"Distributed Systems",
"Product-Led Growth",
"Location Services"
],
"notable_highlights": [
"Founded Otter.ai, scaling to tens of millions of users and billions of captured meeting minutes",
"Pioneered Google Maps ‘blue dot’ location services work",
"Built proprietary speech recognition and summarization stack at Otter.ai",
"Recognized in Top 50 CEOs to Watch"
],
"social_proof": [
"Regular media/features on AI meeting assistants and AI avatars for meetings",
"Interview appearances discussing Otter.ai’s AI agents and enterprise adoption"
],
"follower_count": 15000
}
    # Setup documents - create company and LinkedIn profile documents
    setup_docs: List[SetupDocInfo] = [
        SetupDocInfo(
                            docname=LITE_BLOG_COMPANY_DOCNAME,
                namespace=LITE_BLOG_COMPANY_NAMESPACE_TEMPLATE.format(item="otter"),
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
                docname=LITE_LINKEDIN_USER_PROFILE_DOCNAME,
                namespace=LITE_LINKEDIN_USER_PROFILE_NAMESPACE_TEMPLATE.format(item="samliang"),
                initial_data=LINKEDIN_PROFILE_DATA,
                is_versioned=False,
                is_shared=False,
                is_system_entity=False
            ),
            SetupDocInfo(
                docname=LITE_LINKEDIN_SCRAPED_PROFILE_DOCNAME,
                namespace=LITE_LINKEDIN_SCRAPED_PROFILE_NAMESPACE_TEMPLATE.format(item="samliang"),
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
