"""
Investor Lead Scoring Workflow

This workflow demonstrates:
1. Taking a list of investor leads with fund/partner information
2. (Optional) LinkedIn URL finding: If LinkedIn URL missing, uses Perplexity to find current profile
3. LinkedIn scraping: Scrapes LinkedIn profile data AND 20 recent posts for partner insights
4. Step 1: Deep research using Perplexity Sonar Deep Research model with comprehensive web search
5. Step 2: Structured extraction and scoring using Claude Sonnet 4.5 based on 100-point framework
6. Using private mode passthrough data to preserve all context (including deep research report and LinkedIn data)
7. Collecting final results with comprehensive investor insights, scores, and talking points

Input: List of investor leads with fund name, partner details, and optional reference information
Output: Scored and qualified investors with detailed research reports, scores (0-100), and outreach recommendations

The workflow processes leads in parallel, conducting autonomous deep research and then extracting
structured scoring information based on a 100-point framework covering:

**Scoring Framework (100 points total):**
- **Fund Vitals (0-25 pts)**: Fund size (0-15) + recent activity 2024-2025 (0-10)
- **Lead Capability (0-25 pts)**: Lead behavior pattern (0-15) + typical check size (0-10)
- **Thesis Alignment (0-30 pts)**: AI B2B portfolio (0-12) + MarTech portfolio (0-10) + explicit thesis (0-8) + DevTools/API focus (0-5) + PLG focus (0-5)
- **Partner Value (0-15 pts)**: Title/authority (0-8) + operational background (0-7 additive: ex-founder, ex-CMO, ex-VP Sales, active creator)
- **Strategic Factors (0-5 pts)**: Geography (0-3: US/India) + momentum (0-2: new fund/exits/follow-ons)

**Single Disqualification Criterion**: Fund AUM < $20M

**Scoring Tiers:**
- 85-100: 🔥 A-Tier (Top Priority - Must pursue immediately)
- 70-84: ⭐ B-Tier (High Priority - Direct outreach)
- 50-69: 📋 C-Tier (Medium Priority - Consider timing)
- <50: ❄️ D-Tier (Low Priority - Backup list)

Key Design Decisions:
- **LinkedIn URL finder integration**: If URL missing, uses Perplexity to find it (detects firm changes)
- **LinkedIn scraping integration**: Scrapes profile data + 20 recent posts for partner insights and thesis understanding
- **Data filtering**: Filters scraped LinkedIn data to keep only relevant fields, reducing token usage and focusing on key insights
- **Perplexity Sonar Deep Research**: Autonomous, comprehensive fact-gathering with web search
- **Claude Sonnet 4.5 with Pydantic schemas**: Reliable structured output extraction with 100-point scoring
- **Smart employment verification**: Prioritizes LinkedIn scraped data > LinkedIn URL search > name search
- **Current firm tracking**: Detects and documents if partner moved firms since input data was collected
- **LinkedIn posts analysis**: Uses partner's recent posts for thesis insights, recent positioning, and pitch prep
- Deep research report included in final output for transparency and reference
- Web search citations preserved for fact verification
- Private mode ensures all context flows through the pipeline (including LinkedIn data)
- No filtering step - all leads are scored (disqualification is a field in output, not a filter)

Workflow Flow:
1. Map router distributes each investor
2. Check if LinkedIn URL exists
   - If NO: Use Perplexity to find LinkedIn URL → Scrape profile + posts → Filter data
   - If YES: Scrape LinkedIn profile + 20 recent posts → Filter data
3. Filter LinkedIn data to keep only relevant fields (profile: name, headline, summary, geo, education, positions; posts: text, engagement, resharedPost.text)
4. Deep research using Perplexity (uses filtered scraped data for accurate employment verification)
5. Structured extraction and scoring with Claude Sonnet (100-point framework)
6. Output results with comprehensive scoring and actionable intelligence

Cost Estimate: ~$0.50-1.00 per investor lead (Perplexity deep research) + $0.01-0.02 for LinkedIn scraping + $0.05 for URL finding (if needed)
Time Estimate: ~2-3 minutes per lead for deep research + extraction + scraping
"""

from kiwi_client.workflows.active.investor.investor_lead_scoring_sandbox.wf_llm_inputs import (
    # LinkedIn URL Finder
    LINKEDIN_URL_FINDER_SYSTEM_PROMPT, LINKEDIN_URL_FINDER_USER_PROMPT,
    LINKEDIN_URL_FINDER_OUTPUT_SCHEMA,
    LLM_PROVIDER_URL_FINDER, LLM_MODEL_URL_FINDER, LLM_TEMPERATURE_URL_FINDER, LLM_MAX_TOKENS_URL_FINDER,
    # Deep Research
    STEP1_DEEP_RESEARCH_SYSTEM_PROMPT, STEP1_DEEP_RESEARCH_USER_PROMPT,
    LLM_PROVIDER_DEEP_RESEARCH, LLM_MODEL_DEEP_RESEARCH, LLM_TEMPERATURE_DEEP_RESEARCH,
    LLM_MAX_TOKENS_DEEP_RESEARCH, LLM_DEEP_RESEARCH_REASONING_EFFORT, LLM_DEEP_RESEARCH_SEARCH_CONTEXT_SIZE,
    # Structured Extraction
    STEP2_EXTRACTION_SYSTEM_PROMPT, STEP2_EXTRACTION_USER_PROMPT,
    INVESTOR_LEAD_SCORING_OUTPUT_SCHEMA,
    LLM_PROVIDER_EXTRACTION, LLM_MODEL_EXTRACTION, LLM_TEMPERATURE_EXTRACTION, LLM_MAX_TOKENS_EXTRACTION,
    LLM_EXTRACTION_REASONING_EFFORT,
    VERBOSITY_EXTRACTION,
)

# Import filter targets configuration for LinkedIn data filtering
from kiwi_client.workflows.active.investor.investor_lead_scoring_sandbox.filter_targets_config import ALL_FILTER_TARGETS

# --- Private mode passthrough data keys for preserving context across steps ---
# Step 1 outputs that need to be preserved through step 2
step1_passthrough_keys = [
    "first_name", "last_name", "title", "firm_company", "firm_id", "investor_type",
    "investor_role_detail", "relationship_status", "linkedin_url", "twitter_url",
    "crunchbase_url", "investment_criteria", "notes", "source_sheets",
    "linkedin_url_found",  # URL found by Perplexity if originally missing
    "linkedin_scraped_profile",  # LinkedIn scraped profile data
    "linkedin_scraped_posts",  # LinkedIn scraped posts data (20 posts)
    "deep_research_report", "deep_research_citations"
]

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
                    "investors_to_process": {
                        "type": "list",
                        "required": False,
                        "default": [
                            {
                                "first_name": "Oliver",
                                "last_name": "Hsu",
                                "title": "Investment Partner",
                                "firm_company": "Andreessen Horowitz",
                                "firm_id": "FIRM_001",
                                "investor_type": "VC/Institutional",
                                "investor_role_detail": "VC (Partner/Principal)",
                                "relationship_status": "WARM",
                                "linkedin_url": "https://www.linkedin.com/in/ohsu",
                                "twitter_url": "https://twitter.com/oyhsu",
                                "crunchbase_url": "",
                                "investment_criteria": "AI/B2B SaaS, Seed to Series A",
                                "notes": "Location: New York, New York, United States | GOOD FIT: Partner at US-based VC",
                                "source_sheets": "Test Data"
                            },
                            {
                                "first_name": "Dror",
                                "last_name": "Berman",
                                "title": "General Partner",
                                "firm_company": "Innovation Endeavors",
                                "firm_id": "FIRM_003",
                                "investor_type": "VC/Institutional",
                                "investor_role_detail": "VC (Partner/Principal)",
                                "relationship_status": "COLD",
                                "linkedin_url": "",
                                "twitter_url": "",
                                "crunchbase_url": "",
                                "investment_criteria": "Infrastructure; Developer Tools; AI | Seed; Series A | $2,000,000",
                                "notes": "Tel Aviv (Israel), Strong focus on infrastructure and developer tools",
                                "source_sheets": "Test Data"
                            }
                        ],
                        "description": "List of investor leads with fund/partner information and optional reference data"
                    }
                }
            }
        },

        # --- 2. Map List Router Node - Routes each investor to URL check ---
        "route_investors_to_research": {
            "node_id": "route_investors_to_research",
            "node_name": "map_list_router_node",
            "node_config": {
                "choices": ["check_linkedin_url_exists"],
                "map_targets": [
                    {
                        "source_path": "investors_to_process",
                        "destinations": ["check_linkedin_url_exists"],
                        "batch_size": 1
                    }
                ]
            }
        },

        # --- 3. If/Else Node - Check if LinkedIn URL exists ---
        "check_linkedin_url_exists": {
            "node_id": "check_linkedin_url_exists",
            "node_name": "if_else_condition",
            "private_input_mode": True,
            "private_output_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": step1_passthrough_keys,
            "write_to_private_output_passthrough_data_from_output_mappings": {
                "condition_result": "condition_result",
            },
            "node_config": {
                "tagged_conditions": [
                    {
                        "tag": "has_linkedin_url",
                        "condition_groups": [
                            {
                                "conditions": [
                                    {"field": "linkedin_url", "operator": "is_not_empty"}
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

        # --- 4. Router Node - Route based on URL existence ---
        "route_based_on_linkedin_url": {
            "node_id": "route_based_on_linkedin_url",
            "node_name": "router_node",
            "private_input_mode": True,
            "private_output_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": step1_passthrough_keys,
            "node_config": {
                "choices": ["placeholder_node_1", "find_linkedin_url_prompt"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "placeholder_node_1",
                        "input_path": "condition_result",
                        "target_value": True
                    },
                    {
                        "choice_id": "find_linkedin_url_prompt",
                        "input_path": "condition_result",
                        "target_value": False
                    }
                ]
            }
        },

        # --- 16. Aggregate Both Reports ---
        "placeholder_node_1": {
            "node_id": "placeholder_node_1",
            "node_name": "transform_data",
            "private_input_mode": True,
            "private_output_mode": True,
            "private_output_passthrough_data_to_central_state_keys": step1_passthrough_keys,
            "node_config": {
                "mappings": [
                ]
            }
        },

        # --- 16. Aggregate Both Reports ---
        "placeholder_node_2": {
            "node_id": "placeholder_node_2",
            "node_name": "transform_data",
            "private_input_mode": True,
            "private_output_mode": True,
            "private_output_passthrough_data_to_central_state_keys": step1_passthrough_keys,
            "node_config": {
                "mappings": [
                ]
            }
        },

        # --- 5. Prompt Constructor for LinkedIn URL Finder ---
        "find_linkedin_url_prompt": {
            "node_id": "find_linkedin_url_prompt",
            "node_name": "prompt_constructor",
            "private_input_mode": True,
            "private_output_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": step1_passthrough_keys,
            "node_config": {
                "prompt_templates": {
                    "url_finder_system_prompt": {
                        "id": "url_finder_system_prompt",
                        "template": LINKEDIN_URL_FINDER_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    },
                    "url_finder_user_prompt": {
                        "id": "url_finder_user_prompt",
                        "template": LINKEDIN_URL_FINDER_USER_PROMPT,
                        "variables": {
                            "first_name": "",
                            "last_name": "",
                            "title": "",
                            "firm_company": "",
                            "investment_criteria": "",
                            "notes": ""
                        },
                        "construct_options": {
                            "first_name": "first_name",
                            "last_name": "last_name",
                            "title": "title",
                            "firm_company": "firm_company",
                            "investment_criteria": "investment_criteria",
                            "notes": "notes"
                        }
                    }
                }
            }
        },

        # --- 6. LinkedIn URL Finder using Perplexity Sonar ---
        "find_linkedin_url_with_perplexity": {
            "node_id": "find_linkedin_url_with_perplexity",
            "node_name": "llm",
            "private_input_mode": True,
            "private_output_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": step1_passthrough_keys,
            "write_to_private_output_passthrough_data_from_output_mappings": {
                "structured_output.linkedin_url": "linkedin_url_found",
                "structured_output.linkedin_url": "linkedin_url"  # Also update the linkedin_url field for scraping
            },
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER_URL_FINDER,
                        "model": LLM_MODEL_URL_FINDER
                    },
                    "temperature": LLM_TEMPERATURE_URL_FINDER,
                    "max_tokens": LLM_MAX_TOKENS_URL_FINDER
                },
                "output_schema": {
                    "schema_definition": LINKEDIN_URL_FINDER_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },

        # --- 7. LinkedIn Scraping - Profile + Posts (20 posts) ---
        "scrape_linkedin_profile": {
            "node_id": "scrape_linkedin_profile",
            "node_name": "linkedin_scraping",
            "private_input_mode": True,
            "private_output_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": step1_passthrough_keys,
            "node_config": {
                "test_mode": False,  # Set to True for testing without API calls/credits
                "jobs": [
                    # Job 1: Get Profile Info
                    {
                        "output_field_name": "scraped_profile_job",
                        "job_type": {"static_value": "profile_info"},
                        "url": {"input_field_path": "linkedin_url"},
                        "profile_info": {"static_value": "yes"}
                    },
                    # Job 2: Get 20 Recent Posts
                    {
                        "output_field_name": "scraped_posts_job",
                        "job_type": {"static_value": "entity_posts"},
                        "url": {"input_field_path": "linkedin_url"},
                        "post_limit": {"static_value": 20},
                        "entity_posts": {"static_value": "yes"}
                    }
                ]
            }
        },

        # --- 8. Filter LinkedIn Scraped Data (Profile + Posts) ---
        "filter_linkedin_data": {
            "node_id": "filter_linkedin_data",
            "node_name": "filter_data",
            "private_input_mode": True,
            "private_output_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": step1_passthrough_keys,
            "write_to_private_output_passthrough_data_from_output_mappings": {
                "filtered_data.data_to_filter.scraped_profile_job": "linkedin_scraped_profile",
                "filtered_data.data_to_filter.scraped_posts_job": "linkedin_scraped_posts"
            },
            "node_config": {
                "non_target_fields_mode": "deny",
                "targets": ALL_FILTER_TARGETS
            }
        },

        # --- 9. Step 1: Prompt Constructor for Deep Research ---
        "step1_research_prompt": {
            "node_id": "step1_research_prompt",
            "node_name": "prompt_constructor",
            "private_input_mode": True,
            "private_output_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": step1_passthrough_keys,
            "node_config": {
                "prompt_templates": {
                    "research_system_prompt": {
                        "id": "research_system_prompt",
                        "template": STEP1_DEEP_RESEARCH_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    },
                    "research_user_prompt": {
                        "id": "research_user_prompt",
                        "template": STEP1_DEEP_RESEARCH_USER_PROMPT,
                        "variables": {
                            "first_name": "",
                            "last_name": "",
                            "title": "",
                            "firm_company": "",
                            "investor_type": "",
                            "investor_role_detail": "",
                            "relationship_status": "",
                            "linkedin_url": "",
                            "twitter_url": "",
                            "crunchbase_url": "",
                            "investment_criteria": "",
                            "notes": "",
                            "source_sheets": "",
                            "linkedin_scraped_profile": "",
                            # "linkedin_scraped_posts": ""
                        },
                        "construct_options": {
                            "first_name": "first_name",
                            "last_name": "last_name",
                            "title": "title",
                            "firm_company": "firm_company",
                            "investor_type": "investor_type",
                            "investor_role_detail": "investor_role_detail",
                            "relationship_status": "relationship_status",
                            "linkedin_url": "linkedin_url",
                            "twitter_url": "twitter_url",
                            "crunchbase_url": "crunchbase_url",
                            "investment_criteria": "investment_criteria",
                            "notes": "notes",
                            "source_sheets": "source_sheets",
                            "linkedin_scraped_profile": "linkedin_scraped_profile",
                            # "linkedin_scraped_posts": "linkedin_scraped_posts"
                        }
                    }
                }
            }
        },

        # --- 4. Step 1: Deep Research using Perplexity Sonar Deep Research ---
        "step1_deep_research": {
            "node_id": "step1_deep_research",
            "node_name": "llm",
            "private_input_mode": True,
            "private_output_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": step1_passthrough_keys,
            "write_to_private_output_passthrough_data_from_output_mappings": {
                "text_content": "deep_research_report",
                "web_search_result": "deep_research_citations"
            },
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER_DEEP_RESEARCH,
                        "model": LLM_MODEL_DEEP_RESEARCH
                    },
                    "temperature": LLM_TEMPERATURE_DEEP_RESEARCH,
                    "max_tokens": LLM_MAX_TOKENS_DEEP_RESEARCH,
                    # "reasoning_effort_class": LLM_DEEP_RESEARCH_REASONING_EFFORT,
                },
                # "web_search_options": {
                #     "search_context_size": LLM_DEEP_RESEARCH_SEARCH_CONTEXT_SIZE
                # },
            }
        },

        # --- 5. Step 2: Prompt Constructor for Structured Extraction ---
        "step2_extraction_prompt": {
            "node_id": "step2_extraction_prompt",
            "node_name": "prompt_constructor",
            "private_input_mode": True,
            "private_output_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": step1_passthrough_keys,
            "node_config": {
                "prompt_templates": {
                    "extraction_system_prompt": {
                        "id": "extraction_system_prompt",
                        "template": STEP2_EXTRACTION_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    },
                    "extraction_user_prompt": {
                        "id": "extraction_user_prompt",
                        "template": STEP2_EXTRACTION_USER_PROMPT,
                        "variables": {
                            "first_name": "",
                            "last_name": "",
                            "title": "",
                            "firm_company": "",
                            "investor_type": "",
                            "investment_criteria": "",
                            "notes": "",
                            "linkedin_scraped_profile": "",
                            "linkedin_scraped_posts": "",
                            "deep_research_report": "",
                            "deep_research_citations": ""
                        },
                        "construct_options": {
                            "first_name": "first_name",
                            "last_name": "last_name",
                            "title": "title",
                            "firm_company": "firm_company",
                            "investor_type": "investor_type",
                            "investment_criteria": "investment_criteria",
                            "notes": "notes",
                            "linkedin_scraped_profile": "linkedin_scraped_profile",
                            "linkedin_scraped_posts": "linkedin_scraped_posts",
                            "deep_research_report": "deep_research_report",
                            "deep_research_citations": "deep_research_citations"
                        }
                    }
                }
            }
        },

        # --- 6. Step 2: Structured Extraction and Scoring using Claude Sonnet ---
        "step2_structured_extraction": {
            "node_id": "step2_structured_extraction",
            "node_name": "llm",
            "private_input_mode": True,
            # private_output_mode False - we want to write structured output to central state
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": step1_passthrough_keys,
            "private_output_to_central_state_node_output_key": "scoring_result",
            "node_config": {
                # "max_random_artificial_delay_in_seconds": 120,
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER_EXTRACTION,
                        "model": LLM_MODEL_EXTRACTION
                    },
                    "temperature": LLM_TEMPERATURE_EXTRACTION,
                    "max_tokens": LLM_MAX_TOKENS_EXTRACTION,
                    "reasoning_effort_class": LLM_EXTRACTION_REASONING_EFFORT,
                    "verbosity": VERBOSITY_EXTRACTION
                },
                "output_schema": {
                    "schema_definition": INVESTOR_LEAD_SCORING_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },

        # --- 7. Output Node with Fan-In ---
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "enable_node_fan_in": True,
            "node_config": {}
        }
    },

    # --- Edges Defining Data Flow ---
    "edges": [
        # Input to state and router
        {"src_node_id": "input_node", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "investors_to_process", "dst_field": "original_investors"}
        ]},

        # Input to investor router (distributes each investor to URL check)
        {"src_node_id": "input_node", "dst_node_id": "route_investors_to_research", "mappings": [
            {"src_field": "investors_to_process", "dst_field": "investors_to_process"}
        ]},

        # Map router to if_else check (check if LinkedIn URL exists)
        {"src_node_id": "route_investors_to_research", "dst_node_id": "check_linkedin_url_exists", "mappings": []},

        # If/else check to router (pass branch decision)
        {"src_node_id": "check_linkedin_url_exists", "dst_node_id": "route_based_on_linkedin_url", "mappings": []},

        # Router to URL finder prompt (if no URL - false_branch)
        {"src_node_id": "route_based_on_linkedin_url", "dst_node_id": "find_linkedin_url_prompt", "mappings": []},

        # URL finder prompt to URL finder LLM
        {"src_node_id": "find_linkedin_url_prompt", "dst_node_id": "find_linkedin_url_with_perplexity", "mappings": [
            {"src_field": "url_finder_system_prompt", "dst_field": "system_prompt"},
            {"src_field": "url_finder_user_prompt", "dst_field": "user_prompt"}
        ]},

        # URL finder to LinkedIn scraping (with found URL)
        {"src_node_id": "find_linkedin_url_with_perplexity", "dst_node_id": "scrape_linkedin_profile", "mappings": []},

        # Router to LinkedIn scraping (if URL exists - true_branch)
        {"src_node_id": "route_based_on_linkedin_url", "dst_node_id": "placeholder_node_1", "mappings": []},

        {"src_node_id": "placeholder_node_1", "dst_node_id": "placeholder_node_2", "mappings": []},

        {"src_node_id": "placeholder_node_2", "dst_node_id": "scrape_linkedin_profile", "mappings": []},

        # LinkedIn scraping to filter (pass raw scraping results for filtering)
        {"src_node_id": "scrape_linkedin_profile", "dst_node_id": "filter_linkedin_data", "mappings": [
            {"src_field": "scraping_results", "dst_field": "data_to_filter"}
        ]},
        
        # Filter to research prompt (with filtered profile + posts data in passthrough)
        {"src_node_id": "filter_linkedin_data", "dst_node_id": "step1_research_prompt", "mappings": []},
        
        # Step 1 prompt constructor to deep research LLM
        {"src_node_id": "step1_research_prompt", "dst_node_id": "step1_deep_research", "mappings": [
            {"src_field": "research_system_prompt", "dst_field": "system_prompt"},
            {"src_field": "research_user_prompt", "dst_field": "user_prompt"}
        ]},
        
        # Step 1 deep research to Step 2 extraction prompt (private mode with passthrough data)
        {"src_node_id": "step1_deep_research", "dst_node_id": "step2_extraction_prompt", "mappings": []},
        
        # Step 2 extraction prompt constructor to extraction LLM
        {"src_node_id": "step2_extraction_prompt", "dst_node_id": "step2_structured_extraction", "mappings": [
            {"src_field": "extraction_system_prompt", "dst_field": "system_prompt"},
            {"src_field": "extraction_user_prompt", "dst_field": "user_prompt"}
        ]},
        
        # Step 2 to output (with fan-in) and state
        {"src_node_id": "step2_structured_extraction", "dst_node_id": "output_node", "mappings": []},
        
        {"src_node_id": "step2_structured_extraction", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "final_results"}
        ]},
        
        # State to output for final collection
        {"src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
            {"src_field": "final_results", "dst_field": "scored_investors"}
        ]}
    ],

    # Define start and end
    "input_node_id": "input_node",
    "output_node_id": "output_node",
    
    # Runtime configuration - use large pool tier for deep research workloads
    "runtime_config": {
        "db_concurrent_pool_tier": "large"
    },

    # State reducers - collect all results
    "metadata": {
        "$graph_state": {
            "reducer": {
                "final_results": "collect_values"
            }
        }
    }
}

import asyncio
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus
from kiwi_client.test_run_workflow_client import run_workflow_test

async def test():
    final_run_status_obj, final_run_outputs = await run_workflow_test(
            test_name="investor_lead_scoring_test",
            workflow_graph_schema=workflow_graph_schema,
            initial_inputs={},
            expected_final_status=WorkflowRunStatus.COMPLETED,
            setup_docs=None,
            cleanup_docs=None,
            stream_intermediate_results=False,  # Suppress verbose workflow output
            dump_artifacts=True,  # Don't create artifact files
            poll_interval_sec=10,  # Poll every 10 seconds
            timeout_sec=1800  # 30 minutes for deep research workflows
        )

if __name__ == "__main__":
    asyncio.run(test())
