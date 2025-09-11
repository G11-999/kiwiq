"""
Lead Scoring and Personalized Talking Points Generation Workflow

This workflow demonstrates:
1. Taking a list of lead items with LinkedIn URL, Company, First Name, Last Name, Company website, Email ID, Job Title
2. Step 1: Parallel company qualification assessment using Perplexity LLM with structured output
3. Filtering qualified leads based on qualification_check_passed = True
4. Steps 2-4: Sequential LLM processing for each qualified lead:
   - Step 2: ContentQ scoring + content gap analysis
   - Step 3: Strategic content opportunity identification  
   - Step 4: Personalized talking points + pitch generation
5. Using private mode passthrough data to preserve context across all steps
6. Collecting final results with comprehensive lead insights and talking points

Input: List of lead items with required fields
Output: Qualified leads with ContentQ scores, content opportunities, and personalized talking points





# Setup instructions:

you can set it up and play around with prompts if you want (chatgpt / cursor / claude will guide you how to do it step by step)

0. `git clone https://github.com/KiwiQAI/standalone_client `
1. install python 3.12,
2. poetry instlal from repo standalone_test_client
3. setup .env file as below in folder like this standalone_test_client/kiwi_client/.env
4. download leads.csv from your sheet in folder (export to csv and rename file form google sheets) standalone_test_client/kiwi_client/workflows/active/sdr/
5. run file with diff limits (start and end row) to process diff rows in leads.csv https://github.com/KiwiQAI/standalone_client/blob/main/kiwi_client/workflows/active/sdr/wf_lead_scoring_personalized_talking_points.py


cursor is great to play around with it

.env file for step 3)
```
TEST_ENV=
TEST_USER_EMAIL=
TEST_USER_PASSWORD=
TEST_ORG_ID=
TEST_USER_ID=
```

NOTE: entries in leads.csv must be in same format as : https://docs.google.com/spreadsheets/d/10fgZhj7vQll-TkYMSKr5ogA0G3MSJ0BteZ8o1ETyGEM/edit?gid=0#gid=0

Also, above file processes 0 - 20 row indexes, i.e. 20 rows at a time by default and works without being rate limited





# Sample Results

============================================================
COMBINING BATCH RESULTS
============================================================
INFO:__main__:Combining 6 batch result files into: /path/to/project/standalone_test_client/kiwi_client/workflows/active/sdr/results.csv
INFO:__main__:Loaded 8 results from batch file 1: /path/to/project/standalone_test_client/kiwi_client/workflows/active/sdr/batch_results/batch_001_rows_165-179.csv
INFO:__main__:Loaded 9 results from batch file 2: /path/to/project/standalone_test_client/kiwi_client/workflows/active/sdr/batch_results/batch_002_rows_180-194.csv
INFO:__main__:Loaded 6 results from batch file 3: /path/to/project/standalone_test_client/kiwi_client/workflows/active/sdr/batch_results/batch_003_rows_195-209.csv
INFO:__main__:Loaded 5 results from batch file 4: /path/to/project/standalone_test_client/kiwi_client/workflows/active/sdr/batch_results/batch_004_rows_210-224.csv
INFO:__main__:Loaded 9 results from batch file 5: /path/to/project/standalone_test_client/kiwi_client/workflows/active/sdr/batch_results/batch_005_rows_225-239.csv
INFO:__main__:Loaded 5 results from batch file 6: /path/to/project/standalone_test_client/kiwi_client/workflows/active/sdr/batch_results/batch_006_rows_240-249.csv
INFO:__main__:Successfully combined 42 total results into: /path/to/project/standalone_test_client/kiwi_client/workflows/active/sdr/results.csv
INFO:__main__:Final Summary: 42/42 leads qualified, Average ContentQ Score: 76.6
✓ All batch results combined into: /path/to/project/standalone_test_client/kiwi_client/workflows/active/sdr/results.csv
✓ Individual batch files preserved in: /path/to/project/standalone_test_client/kiwi_client/workflows/active/sdr/batch_results
============================================================
BATCH PROCESSING COMPLETE
============================================================
Total batches: 6
Successful batches: 6
Failed batches: 0
Final merged results saved to: /path/to/project/standalone_test_client/kiwi_client/workflows/active/sdr/results.csv
Individual batch files available in: /path/to/project/standalone_test_client/kiwi_client/workflows/active/sdr/batch_results

============================================================
COMPREHENSIVE TIMING STATISTICS
============================================================
📊 OVERALL PERFORMANCE:
  Total execution time: 1638.9 seconds (27.3 minutes)
  Pure workflow time: 1188.8 seconds (19.8 minutes)
  Artificial delay time: 450.0 seconds (7.5 minutes)
  Setup/cleanup time: 0.0 seconds
  Total leads processed: 42
  Pure workflow time per lead: 28.3 seconds
  Workflow throughput (excluding delays): 127.2 leads/hour
  Overall throughput (including delays): 92.3 leads/hour

⏰ TIME BREAKDOWN:
  Pure workflow processing: 72.5% (1188.8s)
  Artificial delays: 27.5% (450.0s)
  Setup/cleanup overhead: 0.0% (0.0s)
  Processing efficiency: 72.5% (workflow time / total processing time)

⏱️  BATCH PERFORMANCE:
  Average batch duration: 198.1 seconds
  Fastest batch: 160.8 seconds
  Slowest batch: 240.8 seconds
  Batch duration std dev: 27.4 seconds

🎯 PER-LEAD PERFORMANCE:
  Average time per lead: 29.2 seconds
  Fastest lead processing: 24.8 seconds
  Slowest lead processing: 35.1 seconds

📈 DETAILED BATCH BREAKDOWN:
  Batch  1: 198.7s total,  8 leads, 24.8s/lead
  Batch  2: 224.3s total,  9 leads, 24.9s/lead
  Batch  3: 189.0s total,  6 leads, 31.5s/lead
  Batch  4: 175.3s total,  5 leads, 35.1s/lead
  Batch  5: 240.8s total,  9 leads, 26.8s/lead
  Batch  6: 160.8s total,  5 leads, 32.2s/lead

🔮 PERFORMANCE PROJECTIONS:
  Pure workflow time estimates (excluding delays):
    100 leads: 47.2 minutes
    500 leads: 235.9 minutes
    1000 leads: 471.8 minutes
  Total time estimates (including 90s delays):
    100 leads: 68.2 minutes (15.0 batches)
    500 leads: 342.4 minutes (72.0 batches)
    1000 leads: 684.8 minutes (143.0 batches)
============================================================



# Some key improvements:
some companies are not from US, eg from Nigeria, etc; we can include location in column and qualification criterion
we can scrape linkedin / posts and blogs too and use that to summarize / add richer detail instead of perplexity pulling all the weight research wise (unknown delta)
"""

import json
import asyncio
import csv
import argparse
import sys
import time
import pandas as pd
from pathlib import Path
from typing import List, Optional, Dict, Any, Literal
import logging

# --- Workflow Constants ---
LLM_PROVIDER_RESEARCH = "perplexity"  # Using Perplexity for research capabilities
LLM_MODEL_RESEARCH = "sonar-pro"  # Perplexity model with online search
LLM_TEMPERATURE_RESEARCH = 0.5
LLM_MAX_TOKENS_RESEARCH = 2000

LLM_PROVIDER_WRITER = "anthropic"
LLM_MODEL_WRITER = "claude-sonnet-4-20250514"
LLM_TEMPERATURE_WRITER = 0.5
LLM_MAX_TOKENS_WRITER = 4000

# --- System Prompts for Each Step ---

STEP1_SYSTEM_PROMPT = """You are a B2B lead qualification expert specializing in fast company assessment. Your goal is to quickly determine if a company is a good fit for B2B content marketing services.

You have access to real-time web search to gather current information about companies. Use this capability to research the company thoroughly but efficiently.

Focus on gathering the essential qualification data points and making a clear pass/fail decision based on the criteria provided."""

STEP2_SYSTEM_PROMPT = """You are applying ContentQ's proven lead scoring methodology. You are an expert at evaluating B2B companies for content marketing opportunities and calculating precise scores based on multiple business factors.

Use your knowledge of B2B SaaS, funding stages, content marketing, and competitive landscapes to provide accurate assessments."""

STEP3_SYSTEM_PROMPT = """You are a senior content strategist at ContentQ with deep expertise in B2B technical content marketing. Your specialty is identifying unique content opportunities that drive measurable business outcomes.

Focus on strategic, high-impact content opportunities that leverage the company's unique position and the individual's expertise to create competitive advantages."""

STEP4_SYSTEM_PROMPT = """You are a senior sales development expert at ContentQ, skilled at creating personalized, research-backed talking points that demonstrate deep understanding of prospects' businesses.

Your talking points should be specific, insightful, and create urgency while positioning ContentQ as the expert solution for their content marketing needs."""

# --- Private mode passthrough data keys for preserving context across steps ---
# Step 1 outputs that need to be preserved through all subsequent steps
step1_passthrough_keys = ["linkedinUrl", "Company", "firstName", "lastName", "companyWebsite", "emailId", "jobTitle", "qualification_result", "qualification_result_citations"]

# Step 2 outputs that need to be preserved through steps 3-4  
step2_passthrough_keys = ["linkedinUrl", "Company", "firstName", "lastName", "companyWebsite", "emailId", "jobTitle", "qualification_result", "qualification_result_citations", "contentq_and_content_analysis", "contentq_and_content_analysis_citations"]

# Step 3 outputs that need to be preserved through step 4
step3_passthrough_keys = ["linkedinUrl", "Company", "firstName", "lastName", "companyWebsite", "emailId", "jobTitle", "qualification_result", "qualification_result_citations", "contentq_and_content_analysis", "contentq_and_content_analysis_citations", "strategic_analysis", "strategic_analysis_citations"]

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
                    "leads_to_process": {
                        "type": "list",
                        "required": False,
                        "default": [
                            {
                                "linkedinUrl": "https://www.linkedin.com/in/ACoAAAGSbXUBOy1FuiRw9wcaJ-_24TnS_u4dgS8",
                                "Company": "Metadata.Io",
                                "firstName": "Dee", 
                                "lastName": "Acosta 🤖",
                                "companyWebsite": "metadata.io",
                                "emailId": "dee.acosta@metadata.io",
                                "jobTitle": "Ad AI, Sales, and GTM	"
                            },
                            {
                                "linkedinUrl": "https://www.linkedin.com/in/ACoAAAAMYK4BCyNT23Ui4i6ijdr7-Xu2s8H1pa4",
                                "Company": "Stacklok",
                                "firstName": "Christine",
                                "lastName": "Simonini", 
                                "companyWebsite": "stacklok.com",
                                "emailId": "csimonini@appomni.com",
                                "jobTitle": "Advisor"
                            },
                            {
                                "linkedinUrl": "https://www.linkedin.com/in/ACoAACngUhwBxcSAdAIis1EyHyGe0oSxoLg0lVE",
                                "Company": "Cresta",
                                "firstName": "Kurtis",
                                "lastName": "Wagner",
                                "companyWebsite": "cresta.com", 
                                "emailId": "kurtis@cresta.ai",
                                "jobTitle": "AI Agent Architect"
                            }
                        ],
                        "description": "List of leads with LinkedIn URL, Company, First Name, Last Name, Company website, Email ID, Job Title"
                    }
                }
            }
        },

        # --- 2. Map List Router Node - Routes each lead to Step 1 qualification ---
        "route_leads_to_qualification": {
            "node_id": "route_leads_to_qualification",
            "node_name": "map_list_router_node",
            "node_config": {
                "choices": ["step1_qualification_prompt"],
                "map_targets": [
                    {
                        "source_path": "leads_to_process",
                        "destinations": ["step1_qualification_prompt"],
                        "batch_size": 1
                    }
                ]
            }
        },

        # --- 3. Step 1: Prompt Constructor for Qualification Assessment ---
        "step1_qualification_prompt": {
            "node_id": "step1_qualification_prompt",
            "node_name": "prompt_constructor",
            "private_input_mode": True,
            "private_output_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": step1_passthrough_keys,
            "node_config": {
                "prompt_templates": {
                    "qualification_system_prompt": {
                        "id": "qualification_system_prompt",
                        "template": STEP1_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    },
                    "qualification_user_prompt": {
                        "id": "qualification_user_prompt", 
                        "template": """Goal: Fast company fit assessment + foundation data

Research Actions:
1. Company website scan: Industry, employee signals, content presence
2. Single Crunchbase lookup: Funding stage, size, recent news
3. Quick LinkedIn validation: Confirm individual role/title
4. Basic fit check: B2B, technical product, 10-500 employees

Simple Qualification Criteria:
PASS if:
✓ B2B company (not pure consumer)
✓ 10-500 employee range
✓ Individual has marketing/growth/revenue/founder role

FAIL = Stop research, mark as unqualified

INPUT DATA:
Company: {Company}
Individual: {firstName} {lastName}, {jobTitle}
LinkedIn: {linkedinUrl}
Website: {companyWebsite}
Email: {emailId}

Please research this company and individual thoroughly using web search, then provide your assessment.""",
                        "variables": {
                            "Company": None,
                            "firstName": None,
                            "lastName": None,
                            "jobTitle": None,
                            "linkedinUrl": None,
                            "companyWebsite": None,
                            "emailId": None
                        },
                        "construct_options": {
                            "Company": "Company",
                            "firstName": "firstName",
                            "lastName": "lastName", 
                            "jobTitle": "jobTitle",
                            "linkedinUrl": "linkedinUrl",
                            "companyWebsite": "companyWebsite",
                            "emailId": "emailId"
                        }
                    }
                }
            }
        },

        # --- 4. Step 1: Company Qualification Assessment ---
        "step1_qualification_assessment": {
            "node_id": "step1_qualification_assessment",
            "node_name": "llm",
            "private_input_mode": True,
            # "private_output_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": step1_passthrough_keys,
            "private_output_to_central_state_node_output_key": "qualification_result",
            "write_to_private_output_passthrough_data_from_output_mappings": {
                "web_search_result": "qualification_result_citations"
            },
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER_RESEARCH, "model": LLM_MODEL_RESEARCH},
                    "temperature": LLM_TEMPERATURE_RESEARCH,
                    "max_tokens": LLM_MAX_TOKENS_RESEARCH
                },
                "output_schema": {
                    "dynamic_schema_spec": {
                        "schema_name": "QualificationResult",
                        "fields": {
                            "company_info": {
                                "type": "str", 
                                "required": True,
                                "description": "Comprehensive company research summary including industry, size, funding, business model"
                            },
                            "individual_info": {
                                "type": "str",
                                "required": True, 
                                "description": "Individual role validation and background information"
                            },
                            "industry": {
                                "type": "str",
                                "required": True,
                                "description": "Primary industry/category of the company"
                            },
                            "employee_count_estimate": {
                                "type": "str", 
                                "required": True,
                                "description": "Estimated employee count range"
                            },
                            "funding_stage": {
                                "type": "str",
                                "required": True,
                                "description": "Current funding stage (Pre-seed, Seed, Series A, etc.)"
                            },
                            "qualification_reasoning": {
                                "type": "str",
                                "required": True,
                                "description": "Detailed explanation of why the lead passed or failed qualification"
                            },
                            "qualification_check_passed": {
                                "type": "bool",
                                "required": True,
                                "description": "True if company passes qualification criteria, False otherwise"
                            },                            
                        }
                    }
                }
            }
        },

        # --- 5. Filter Node - Keep only qualified leads ---
        "filter_qualified_leads": {
            "node_id": "filter_qualified_leads", 
            "node_name": "filter_data",
            "enable_node_fan_in": True,
            "node_config": {
                "targets": [
                    {
                        "filter_target": "qualification_results",
                        "filter_mode": "allow",
                        "condition_groups": [
                            {
                                "conditions": [
                                    {
                                        "field": "qualification_results.qualification_result.qualification_check_passed",
                                        "operator": "equals",
                                        "value": True
                                    }
                                ],
                                "logical_operator": "and"
                            }
                        ],
                        "group_logical_operator": "and"
                    }
                ],
                "non_target_fields_mode": "allow"
            }
        },

        # --- 6. Map List Router Node - Route qualified leads to Step 2 ---
        "route_qualified_to_step2": {
            "node_id": "route_qualified_to_step2",
            "node_name": "map_list_router_node", 
            "node_config": {
                "choices": ["step2_contentq_prompt"],
                "map_targets": [
                    {
                        "source_path": "filtered_data.qualification_results",
                        "destinations": ["step2_contentq_prompt"],
                        "batch_size": 1
                    }
                ]
            }
        },

        # --- 7. Step 2: Prompt Constructor for ContentQ Scoring ---
        "step2_contentq_prompt": {
            "node_id": "step2_contentq_prompt",
            "node_name": "prompt_constructor",
            "private_input_mode": True,
            "private_output_mode": True,
            "output_private_output_to_central_state": True,  # Don't write to central state, pass to next step
            "private_output_passthrough_data_to_central_state_keys": step2_passthrough_keys,
            "node_config": {
                "prompt_templates": {
                    "contentq_system_prompt": {
                        "id": "contentq_system_prompt",
                        "template": STEP2_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    },
                    "contentq_user_prompt": {
                        "id": "contentq_user_prompt",
                        "template": """You are applying ContentQ's proven lead scoring methodology. Provide a comprehensive analysis in structured markdown format.

## ContentQ Lead Scoring Analysis

### Company Overview
**Company:** {company_name}  
**Individual:** {first_name} {last_name}, {title}  
**Website:** {website_url}

### Scoring Methodology

**COMPANY SCORING:**
- Funding Stage: Seed/Series A (+25), Pre-seed (+15), Series B+ (-10)
- Employee Count: 10-50 (+20), 5-10 (+10), 50-100 (+5)  
- Industry: Dev tools/API/Prosumer (+20), B2B SaaS (+15), B2C (disqualify)
- Founded: 1-3 years (+15), 6mo-1yr (+10), 4+ years (+5)

**CONTENT GAP SCORING:**
- No blog/broken blog (+30), Last post >60 days (+25), 1-3 posts/month (+20), 4+ generic posts (+10), Strong content (-20)
- AI Invisibility: Not in ChatGPT responses (+20), Competitors mentioned instead (+15)

**INDIVIDUAL SCORING:**
- Founder/CEO (+30), VP Marketing (+25), Fractional CMO (+25), Marketing Manager (+15), Content Manager (+5)
- LinkedIn: Recent posts (+10), <500 followers (+5), New role (+10)

**URGENCY FACTORS:**
- Recent funding <6mo (+20), Product launch (+15), New marketing hire (+15)

**OVERRIDE RULES:**
- "No Blog Rule": B2B company + 10+ employees + no blog = automatic 80+ score
- "Category Creator": No direct competitors = +20

### Analysis Structure Required:

#### 1. Company Assessment
- **Funding Stage Analysis:** [Current stage with reasoning and sources]
- **Employee Count Analysis:** [Size assessment with sources]
- **Industry Classification:** [Category with justification]
- **Company Age Analysis:** [Founded date and implications]
- **Score Calculation:** [Points awarded with reasoning]

#### 2. Content Gap Analysis
- **Current Content Audit:** [Blog status, posting frequency, content quality with specific examples]
- **AI Visibility Check:** [Search results in ChatGPT/AI responses with citations]
- **Content Gap Identification:** [Specific opportunities with reasoning]
- **Score Calculation:** [Points awarded with justification]

#### 3. Individual Assessment
- **Role Analysis:** [Title evaluation and authority level]
- **LinkedIn Presence:** [Follower count, recent activity, engagement with sources]
- **Authority Potential:** [Ability to create thought leadership content]
- **Score Calculation:** [Points awarded with reasoning]

#### 4. Urgency Factors
- **Recent Developments:** [Funding, launches, hires with dates and sources]
- **Market Timing:** [Why now is important with context]
- **Score Calculation:** [Additional points with justification]

#### 5. Final ContentQ Score
**TOTAL SCORE: [X]/100 - [TIER CLASSIFICATION]**
- 🔥 ON FIRE (80-100): Immediate priority
- 🌟 HOT LEAD (60-79): High priority  
- ⚡ WARM LEAD (40-59): Medium priority
- ❄️ COLD LEAD (0-39): Low priority

#### 6. Competitive Intelligence
- **Primary Competitors:** [Top 1-2 competitors with analysis]
- **Their Content Approach:** [What they're doing well/poorly]
- **Competitive Advantage Opportunity:** [How to differentiate]

#### 7. Strategic Recommendation
- **Biggest Content Opportunity:** [Most impactful area to focus]
- **Reasoning:** [Why this will drive business results]
- **Supporting Evidence:** [Data points and citations]

**Research Context:**
{company_research}

**Research Citations and Sources:**
{research_citations}

Please provide detailed analysis with specific citations and reasoning for each section. Use actual data points and sources where available. Reference the citations provided above when making claims.""",
                        "variables": {
                            "company_name": None,
                            "first_name": None,
                            "last_name": None,
                            "title": None,
                            "website_url": None,
                            "company_research": None,
                            "research_citations": ""
                        },
                        "construct_options": {
                            "company_name": "Company",
                            "first_name": "firstName",
                            "last_name": "lastName",
                            "title": "jobTitle",
                            "website_url": "companyWebsite", 
                            "company_research": "qualification_result",
                            "research_citations": "qualification_result_citations"
                        }
                    }
                }
            }
        },

        # --- 8. Step 2: ContentQ Scoring + Content Gap Analysis ---
        "step2_contentq_scoring": {
            "node_id": "step2_contentq_scoring",
            "node_name": "llm",
            "private_input_mode": True,
            "private_output_mode": True,
            "output_private_output_to_central_state": True,  # Don't write to central state, pass to next step
            "private_output_passthrough_data_to_central_state_keys": step2_passthrough_keys,
            "write_to_private_output_passthrough_data_from_output_mappings": {
                "text_content": "contentq_and_content_analysis",
                "web_search_result": "contentq_and_content_analysis_citations"
            },
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER_RESEARCH, "model": LLM_MODEL_RESEARCH},
                    "temperature": LLM_TEMPERATURE_RESEARCH,
                    "max_tokens": LLM_MAX_TOKENS_RESEARCH
                }
            }
        },

        # --- 9. Step 3: Prompt Constructor for Strategic Content Opportunity ---
        "step3_strategic_prompt": {
            "node_id": "step3_strategic_prompt",
            "node_name": "prompt_constructor",
            "private_input_mode": True,
            "private_output_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": step3_passthrough_keys,
            "node_config": {
                "prompt_templates": {
                    "strategic_system_prompt": {
                        "id": "strategic_system_prompt",
                        "template": STEP3_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    },
                    "strategic_user_prompt": {
                        "id": "strategic_user_prompt",
                        "template": """You are a senior content strategist at ContentQ. Provide a comprehensive strategic analysis in structured markdown format.

## Strategic Content Opportunity Analysis

### Company Profile
**Company:** {company_name}  
**Individual:** {first_name} {last_name}, {title}  
**Website:** {website_url}

### Context Integration

**Previous Analysis Summary:**
- **Qualification Results:** {qualification_analysis}
- **Qualification Citations:** {qualification_citations}
- **ContentQ Scoring & Content Analysis:** {contentq_analysis}
- **ContentQ Analysis Citations:** {contentq_citations}

### Strategic Framework

ContentQ helps B2B technical companies generate pipeline through thought leadership content. We focus on content that creates measurable business outcomes: lead generation, competitive differentiation, market authority.

### Analysis Structure Required:

#### 1. Strategic Content Positioning
- **Unique Content Angle:** [What content territory could this company own? With reasoning and market evidence]
- **Authority Building Opportunity:** [How the individual can become an industry thought leader]
- **Competitive Differentiation:** [Content angles competitors aren't covering with citations]
- **Market Timing Analysis:** [Why now is the right time with supporting data]

#### 2. Business Context Analysis  
- **Funding Stage Impact:** [How their current funding creates content urgency with timeline reasoning]
- **Company Size Advantage:** [How their scale creates content opportunities with examples]
- **Industry Positioning:** [Category-specific content opportunities with market analysis]
- **Growth Stage Implications:** [Content needs based on business maturity with citations]

#### 3. Individual Authority Assessment
- **Current Authority Level:** [Assessment of individual's existing thought leadership with sources]
- **Authority Building Potential:** [Specific areas where they could establish expertise]
- **Content Creation Capacity:** [Realistic assessment of their ability to produce content]
- **Network Leverage:** [How to use their existing network for content amplification]

#### 4. Content Strategy Framework
- **Primary Content Pillar:** [Main topic area with business rationale and evidence]
- **Secondary Content Pillars:** [2-3 supporting topics with strategic reasoning]
- **Content Format Recommendations:** [Best formats for their audience with justification]
- **Distribution Strategy:** [Optimal channels based on their market with data]

#### 5. Business Impact Projection
- **90-Day Outcomes:** [Expected results from content investment with benchmarks]
- **Lead Generation Potential:** [Specific pipeline impact with industry comparisons]
- **Brand Authority Building:** [How content will establish market position]
- **Competitive Advantage Creation:** [Sustainable differentiation through content]

#### 6. Implementation Roadmap
- **Phase 1 (Month 1):** [Immediate content opportunities with rationale]
- **Phase 2 (Month 2-3):** [Scaling content production with supporting evidence]
- **Success Metrics:** [KPIs to track content effectiveness with benchmarks]
- **Resource Requirements:** [Team, tools, budget considerations with justification]

#### 7. Risk Assessment & Mitigation
- **Content Creation Challenges:** [Potential obstacles with solutions]
- **Market Timing Risks:** [What could change the opportunity with contingencies]
- **Competitive Response:** [How competitors might react with counter-strategies]

Please provide detailed strategic analysis with specific reasoning, citations, and actionable recommendations for each section. Focus on measurable business outcomes and competitive advantages.""",
                        "variables": {
                            "company_name": None,
                            "first_name": None,
                            "last_name": None,
                            "title": None,
                            "website_url": None,
                            "qualification_analysis": None,
                            "qualification_citations": "",
                            "contentq_analysis": None,
                            "contentq_citations": ""
                        },
                        "construct_options": {
                            "company_name": "Company",
                            "first_name": "firstName",
                            "last_name": "lastName",
                            "title": "jobTitle",
                            "website_url": "companyWebsite",
                            "qualification_analysis": "qualification_result",
                            "qualification_citations": "qualification_result_citations",
                            "contentq_analysis": "contentq_and_content_analysis",
                            "contentq_citations": "contentq_and_content_analysis_citations"
                        }
                    }
                }
            }
        },

        # --- 10. Step 3: Strategic Content Opportunity Identification ---
        "step3_strategic_opportunity": {
            "node_id": "step3_strategic_opportunity",
            "node_name": "llm",
            "private_input_mode": True,
            "private_output_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": step3_passthrough_keys,
            "write_to_private_output_passthrough_data_from_output_mappings": {
                "text_content": "strategic_analysis",
                "web_search_result": "strategic_analysis_citations"
            },
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER_RESEARCH, "model": LLM_MODEL_RESEARCH},
                    "temperature": LLM_TEMPERATURE_RESEARCH,
                    "max_tokens": LLM_MAX_TOKENS_RESEARCH
                }
            }
        },

        # --- 11. Step 4: Prompt Constructor for Talking Points ---
        "step4_talking_points_prompt": {
            "node_id": "step4_talking_points_prompt",
            "node_name": "prompt_constructor",
            "private_input_mode": True,
            "private_output_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": step3_passthrough_keys,
            "node_config": {
                "prompt_templates": {
                    "talking_points_system_prompt": {
                        "id": "talking_points_system_prompt",
                        "template": STEP4_SYSTEM_PROMPT,
                        "variables": {},
                        "construct_options": {}
                    },
                    "talking_points_user_prompt": {
                        "id": "talking_points_user_prompt",
                        "template": """Create personalized email talking points that prove ContentQ understands this prospect's business and content opportunity. Use all previous analysis context to create highly specific, data-driven insights.

## Personalized Talking Points Generation

### Company Profile
**Company:** {company_name}  
**Individual:** {first_name} {last_name}, {title}  
**Website:** {website_url}

### Complete Analysis Context

**Step 1 - Qualification Analysis:**
{qualification_analysis}

**Step 1 - Qualification Citations:**
{qualification_citations}

**Step 2 - ContentQ Scoring & Content Analysis:**
{contentq_analysis}

**Step 2 - ContentQ Citations:**
{contentq_citations}

**Step 3 - Strategic Content Opportunity Analysis:**
{strategic_analysis}

**Step 3 - Strategic Citations:**
{strategic_citations}

### Talking Points Requirements

**GOAL:** Generate 4 specific insights that demonstrate deep expertise and create urgency for ContentQ's services.

**TALKING POINT CRITERIA:**
- Specific to their company/industry (not generic)
- Based on real research findings from analysis above
- Shows we understand their business context intimately
- Creates urgency for content marketing investment
- Positions ContentQ as the expert solution
- Include reasoning and citations for each point

**CONTENTQ VALUE PROPS BY INDUSTRY:**
- SaaS/Tech: Technical thought leadership, developer authority, product differentiation
- Fintech: Regulatory expertise, trust building, compliance content  
- Healthcare: Clinical authority, patient education, HIPAA-compliant content
- Industrial: Technical expertise, safety/compliance, B2B education

### Output Requirements

Generate structured output with detailed reasoning and citations for each talking point. Extract the ContentQ score from the analysis above and include it in your response.

IMPORTANT: while citing sources in the citations field, make sure to cite the source of the data (URL, snippet, title, etc.).
""",
                        "variables": {
                            "company_name": None,
                            "first_name": None,
                            "last_name": None,
                            "title": None,
                            "website_url": None,
                            "qualification_analysis": None,
                            "qualification_citations": "",
                            "contentq_analysis": None,
                            "contentq_citations": "",
                            "strategic_analysis": None,
                            "strategic_citations": ""
                        },
                        "construct_options": {
                            "company_name": "Company",
                            "first_name": "firstName",
                            "last_name": "lastName",
                            "title": "jobTitle",
                            "website_url": "companyWebsite",
                            "qualification_analysis": "qualification_result",
                            "qualification_citations": "qualification_result_citations",
                            "contentq_analysis": "contentq_and_content_analysis",
                            "contentq_citations": "contentq_and_content_analysis_citations",
                            "strategic_analysis": "strategic_analysis",
                            "strategic_citations": "strategic_analysis_citations"
                        }
                    }
                }
            }
        },

        # --- 12. Step 4: Personalized Talking Points + Pitch Generation ---
        "step4_talking_points": {
            "node_id": "step4_talking_points",
            "node_name": "llm",
            "private_input_mode": True,
            # "private_output_mode": True,
            "output_private_output_to_central_state": True,
            "private_output_passthrough_data_to_central_state_keys": step3_passthrough_keys,
            "private_output_to_central_state_node_output_key": "talking_points_result",
            # "write_to_private_output_passthrough_data_from_output_mappings": {
            #     "structured_output": "final_talking_points"
            # },
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER_WRITER, "model": LLM_MODEL_WRITER},
                    "temperature": LLM_TEMPERATURE_WRITER,
                    "max_tokens": LLM_MAX_TOKENS_WRITER
                },
                "output_schema": {
                    "dynamic_schema_spec": {
                        "schema_name": "TalkingPointsWithReasoningResult",
                        "fields": {
                            "contentq_score": {
                                "type": "float",
                                "required": True,
                                "description": "ContentQ score extracted from previous analysis (e.g., 85.0)"
                            },
                            "contentq_score_text": {
                                "type": "str",
                                "required": True,
                                "description": "ContentQ score extracted from previous analysis (e.g., '85/100 - 🔥 ON FIRE')"
                            },
                            "talking_point_1_reasoning_citations": {
                                "type": "str",
                                "required": True,
                                "description": "Detailed reasoning and citations for talking point 1"
                            },
                            "talking_point_1": {
                                "type": "str",
                                "required": True,
                                "description": "First talking point - business context observation"
                            },
                            "talking_point_2_reasoning_citations": {
                                "type": "str",
                                "required": True,
                                "description": "Detailed reasoning and citations for talking point 2"
                            },
                            "talking_point_2": {
                                "type": "str", 
                                "required": True,
                                "description": "Second talking point - content gap insight"
                            },
                            "talking_point_3_reasoning_citations": {
                                "type": "str",
                                "required": True,
                                "description": "Detailed reasoning and citations for talking point 3"
                            },
                            "talking_point_3": {
                                "type": "str",
                                "required": True,
                                "description": "Third talking point - authority opportunity"
                            },
                            "talking_point_4_reasoning_citations": {
                                "type": "str",
                                "required": True,
                                "description": "Detailed reasoning and citations for talking point 4"
                            },
                            "talking_point_4": {
                                "type": "str",
                                "required": True,
                                "description": "Fourth talking point - timing/urgency factor"
                            },
                            "contentq_pitch_reasoning_citations": {
                                "type": "str",
                                "required": True,
                                "description": "Strategic reasoning behind the pitch with supporting evidence"
                            },
                            "contentq_pitch": {
                                "type": "str",
                                "required": True,
                                "description": "2-3 sentence personalized value proposition"
                            },
                            "subject_line_reasoning": {
                                "type": "str",
                                "required": True,
                                "description": "Psychology and strategy behind the subject line choice"
                            },
                            "email_subject_line": {
                                "type": "str",
                                "required": True,
                                "description": "Specific, curiosity-driven email subject line"
                            },
                        }
                    }
                }
            }
        },

        # --- 13. Output Node with Fan-In ---
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
            {"src_field": "leads_to_process", "dst_field": "original_leads"}
        ]},
        
        # Input to Step 1 router
        {"src_node_id": "input_node", "dst_node_id": "route_leads_to_qualification", "mappings": [
            {"src_field": "leads_to_process", "dst_field": "leads_to_process"}
        ]},
        
        # Step 1 router to qualification prompt constructor (private mode)
        {"src_node_id": "route_leads_to_qualification", "dst_node_id": "step1_qualification_prompt", "mappings": []},
        
        # Step 1 prompt constructor to qualification LLM
        {"src_node_id": "step1_qualification_prompt", "dst_node_id": "step1_qualification_assessment", "mappings": [
            {"src_field": "qualification_system_prompt", "dst_field": "system_prompt"},
            {"src_field": "qualification_user_prompt", "dst_field": "user_prompt"}
        ]},

        {"src_node_id": "step1_qualification_assessment", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "qualification_results"},
        ]},

        {"src_node_id": "step1_qualification_assessment", "dst_node_id": "filter_qualified_leads", "mappings": []},
        
        # State to filter (collect all qualification results)
        {"src_node_id": "$graph_state", "dst_node_id": "filter_qualified_leads", "mappings": [
            {"src_field": "qualification_results", "dst_field": "qualification_results"}
        ]},
        
        # Filter to Step 2 router
        {"src_node_id": "filter_qualified_leads", "dst_node_id": "route_qualified_to_step2", "mappings": [
            {"src_field": "filtered_data", "dst_field": "filtered_data"}
        ]},
        
        # Step 2 router to ContentQ prompt constructor (private mode)
        {"src_node_id": "route_qualified_to_step2", "dst_node_id": "step2_contentq_prompt", "mappings": []},
        
        # Step 2 prompt constructor to ContentQ scoring LLM
        {"src_node_id": "step2_contentq_prompt", "dst_node_id": "step2_contentq_scoring", "mappings": [
            {"src_field": "contentq_system_prompt", "dst_field": "system_prompt"},
            {"src_field": "contentq_user_prompt", "dst_field": "user_prompt"}
        ]},
        
        # Step 2 to Step 3 prompt constructor (private mode with passthrough data)
        {"src_node_id": "step2_contentq_scoring", "dst_node_id": "step3_strategic_prompt", "mappings": []},
        
        # Step 3 prompt constructor to strategic opportunity LLM
        {"src_node_id": "step3_strategic_prompt", "dst_node_id": "step3_strategic_opportunity", "mappings": [
            {"src_field": "strategic_system_prompt", "dst_field": "system_prompt"},
            {"src_field": "strategic_user_prompt", "dst_field": "user_prompt"}
        ]},
        
        # Step 3 to Step 4 prompt constructor (private mode with passthrough data)
        {"src_node_id": "step3_strategic_opportunity", "dst_node_id": "step4_talking_points_prompt", "mappings": []},
        
        # Step 4 prompt constructor to talking points LLM
        {"src_node_id": "step4_talking_points_prompt", "dst_node_id": "step4_talking_points", "mappings": [
            {"src_field": "talking_points_system_prompt", "dst_field": "system_prompt"},
            {"src_field": "talking_points_user_prompt", "dst_field": "user_prompt"}
        ]},
        
        # Step 4 to output (with fan-in)
        {"src_node_id": "step4_talking_points", "dst_node_id": "output_node", "mappings": []},

        {"src_node_id": "step4_talking_points", "dst_node_id": "$graph_state", "mappings": [
            {"src_field": "structured_output", "dst_field": "final_results"},
        ]},
        
        # State to output for final collection
        {"src_node_id": "$graph_state", "dst_node_id": "output_node", "mappings": [
            {"src_field": "final_results", "dst_field": "processed_leads"},
            # {"src_field": "original_leads", "dst_field": "original_leads"}
        ]}
    ],

    # Define start and end
    "input_node_id": "input_node",
    "output_node_id": "output_node",

    # State reducers - collect all results
    "metadata": {
        "$graph_state": {
            "reducer": {
                "qualification_results": "collect_values",
                "final_results": "collect_values"
            }
        }
    }
}

# --- Test Execution Logic ---
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

logger = logging.getLogger(__name__)

def load_csv_data(csv_filename: str, start_row: int = 0, end_row: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Load CSV data and convert to the required format for workflow processing.
    
    Args:
        csv_filename: Path to the CSV file containing lead data
        start_row: Starting row index (0-based, excluding header)
        end_row: Ending row index (0-based, exclusive). If None, process all rows from start_row
        
    Returns:
        List of lead dictionaries with required fields
        
    Expected CSV columns (supports aliases):
        - linkedinUrl: LinkedIn profile URL (aliases: 'linkedinUrl', 'LinkedIn URL', 'LinkedIn')
        - Company: Company name (aliases: 'Company', 'Company Name', 'Organization')
        - firstName: First name (aliases: 'firstName', 'First Name', 'First')
        - lastName: Last name (aliases: 'lastName', 'Last Name', 'Last')
        - companyWebsite: Company website URL (aliases: 'companyWebsite', 'Company website', 'Website', 'Company Website')
        - emailId: Email address (aliases: 'emailId', 'Email ID', 'Email', 'Email Address')
        - jobTitle: Job title/role (aliases: 'jobTitle', 'Job Title', 'Title', 'Position')
    """
    try:
        # Read CSV file using pandas for better handling
        df = pd.read_csv(csv_filename)
        
        # Apply row range filtering
        if end_row is not None:
            df = df.iloc[start_row:end_row]
        else:
            df = df.iloc[start_row:]
            
        logger.info(f"Loaded {len(df)} rows from CSV file: {csv_filename}")
        logger.info(f"Row range: {start_row} to {end_row if end_row else 'end'}")
        logger.info(f"Available columns: {list(df.columns)}")
        
        # Define column aliases mapping - maps standard field names to possible CSV column names
        column_aliases = {
            'linkedinUrl': ['linkedinUrl', 'LinkedIn URL', 'LinkedIn', 'linkedin_url', 'linkedin'],
            'Company': ['Company', 'Company Name', 'Organization', 'company', 'company_name'],
            'firstName': ['firstName', 'First Name', 'First', 'first_name', 'first'],
            'lastName': ['lastName', 'Last Name', 'Last', 'last_name', 'last'],
            'companyWebsite': ['companyWebsite', 'Company website', 'Website', 'Company Website', 'company_website', 'website'],
            'emailId': ['emailId', 'Email ID', 'Email', 'Email Address', 'email_id', 'email', 'email_address'],
            'jobTitle': ['jobTitle', 'Job Title', 'Title', 'Position', 'job_title', 'title', 'position']
        }
        
        # Create mapping from CSV columns to standard field names
        column_mapping = {}
        available_columns = list(df.columns)
        
        for standard_field, possible_names in column_aliases.items():
            found_column = None
            for possible_name in possible_names:
                if possible_name in available_columns:
                    found_column = possible_name
                    break
            
            if found_column:
                column_mapping[standard_field] = found_column
                logger.info(f"Mapped '{standard_field}' to CSV column '{found_column}'")
            else:
                logger.warning(f"Could not find column for '{standard_field}'. Tried: {possible_names}")
        
        # Check if all required fields have been mapped
        required_fields = ['linkedinUrl', 'Company', 'firstName', 'lastName', 'companyWebsite', 'emailId', 'jobTitle']
        missing_fields = [field for field in required_fields if field not in column_mapping]
        
        if missing_fields:
            available_cols_str = ", ".join(available_columns)
            missing_aliases = {field: column_aliases[field] for field in missing_fields}
            raise ValueError(
                f"Could not map required fields to CSV columns: {missing_fields}\n"
                f"Available CSV columns: {available_cols_str}\n"
                f"Expected column names for missing fields: {missing_aliases}"
            )
        
        # Convert to list of dictionaries using the column mapping
        leads_data = []
        
        for _, row in df.iterrows():
            lead_data = {}
            for standard_field, csv_column in column_mapping.items():
                # Handle NaN values by converting to empty string
                value = row[csv_column]
                if pd.isna(value):
                    lead_data[standard_field] = ""
                else:
                    lead_data[standard_field] = str(value).strip()
            
            leads_data.append(lead_data)
        
        logger.info(f"Successfully processed {len(leads_data)} leads from CSV")
        logger.info(f"Column mappings used: {column_mapping}")
        return leads_data
        
    except FileNotFoundError:
        logger.error(f"CSV file not found: {csv_filename}")
        raise
    except Exception as e:
        logger.error(f"Error loading CSV file {csv_filename}: {str(e)}")
        raise


def save_results_to_csv(final_run_outputs: Dict[str, Any], output_csv_filename: str) -> None:
    """
    Save workflow results to CSV file with comprehensive lead data and talking points.
    
    Args:
        final_run_outputs: Final workflow outputs containing processed_leads
        output_csv_filename: Path to output CSV file
    """
    try:
        processed_leads = final_run_outputs.get('processed_leads', [])
        
        if not processed_leads:
            logger.warning("No processed leads found in workflow outputs")
            return
        
        # Prepare CSV rows with flattened data structure
        csv_rows = []
        
        for lead in processed_leads:
            row = {}
            
            # Basic lead information
            row['linkedinUrl'] = lead.get('linkedinUrl', '')
            row['Company'] = lead.get('Company', '')
            row['firstName'] = lead.get('firstName', '')
            row['lastName'] = lead.get('lastName', '')
            row['companyWebsite'] = lead.get('companyWebsite', '')
            row['emailId'] = lead.get('emailId', '')
            row['jobTitle'] = lead.get('jobTitle', '')
            
            # Qualification result fields - handle both dict and JSON string formats
            qualification_result_raw = lead.get('qualification_result', {})
            if isinstance(qualification_result_raw, str):
                try:
                    qualification_result = json.loads(qualification_result_raw)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"Failed to parse qualification_result as JSON: {qualification_result_raw}")
                    qualification_result = {}
            elif isinstance(qualification_result_raw, dict):
                qualification_result = qualification_result_raw
            else:
                logger.warning(f"Unexpected qualification_result type: {type(qualification_result_raw)}")
                qualification_result = {}
                
            row['industry'] = qualification_result.get('industry', '') if isinstance(qualification_result, dict) else ''
            row['company_info'] = qualification_result.get('company_info', '') if isinstance(qualification_result, dict) else ''
            row['funding_stage'] = qualification_result.get('funding_stage', '') if isinstance(qualification_result, dict) else ''
            row['individual_info'] = qualification_result.get('individual_info', '') if isinstance(qualification_result, dict) else ''
            row['employee_count_estimate'] = qualification_result.get('employee_count_estimate', '') if isinstance(qualification_result, dict) else ''
            row['qualification_reasoning'] = qualification_result.get('qualification_reasoning', '') if isinstance(qualification_result, dict) else ''
            row['qualification_check_passed'] = qualification_result.get('qualification_check_passed', False) if isinstance(qualification_result, dict) else False
            
            # ContentQ analysis (truncated for CSV readability)
            contentq_analysis = lead.get('contentq_and_content_analysis', '')
            row['contentq_analysis_summary'] = contentq_analysis[:500] + '...' if len(contentq_analysis) > 500 else contentq_analysis
            
            # Strategic analysis (truncated for CSV readability)  
            strategic_analysis = lead.get('strategic_analysis', '')
            row['strategic_analysis_summary'] = strategic_analysis[:500] + '...' if len(strategic_analysis) > 500 else strategic_analysis
            
            # Talking points result - handle both dict and JSON string formats
            talking_points_result_raw = lead.get('talking_points_result', {})
            if isinstance(talking_points_result_raw, str):
                try:
                    talking_points_result = json.loads(talking_points_result_raw)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"Failed to parse talking_points_result as JSON: {talking_points_result_raw}")
                    talking_points_result = {}
            elif isinstance(talking_points_result_raw, dict):
                talking_points_result = talking_points_result_raw
            else:
                logger.warning(f"Unexpected talking_points_result type: {type(talking_points_result_raw)}")
                talking_points_result = {}
                
            row['contentq_score'] = talking_points_result.get('contentq_score', 0.0) if isinstance(talking_points_result, dict) else 0.0
            row['contentq_score_text'] = talking_points_result.get('contentq_score_text', '') if isinstance(talking_points_result, dict) else ''
            row['contentq_pitch'] = talking_points_result.get('contentq_pitch', '') if isinstance(talking_points_result, dict) else ''
            row['email_subject_line'] = talking_points_result.get('email_subject_line', '') if isinstance(talking_points_result, dict) else ''
            
            # Individual talking points
            row['talking_point_1'] = talking_points_result.get('talking_point_1', '') if isinstance(talking_points_result, dict) else ''
            row['talking_point_2'] = talking_points_result.get('talking_point_2', '') if isinstance(talking_points_result, dict) else ''
            row['talking_point_3'] = talking_points_result.get('talking_point_3', '') if isinstance(talking_points_result, dict) else ''
            row['talking_point_4'] = talking_points_result.get('talking_point_4', '') if isinstance(talking_points_result, dict) else ''
            
            # Reasoning for talking points (truncated)
            for i in range(1, 5):
                reasoning_key = f'talking_point_{i}_reasoning_citations'
                reasoning = talking_points_result.get(reasoning_key, '') if isinstance(talking_points_result, dict) else ''
                row[f'talking_point_{i}_reasoning'] = reasoning[:300] + '...' if len(reasoning) > 300 else reasoning
            
            # ContentQ pitch reasoning
            pitch_reasoning = talking_points_result.get('contentq_pitch_reasoning_citations', '') if isinstance(talking_points_result, dict) else ''
            row['contentq_pitch_reasoning'] = pitch_reasoning[:300] + '...' if len(pitch_reasoning) > 300 else pitch_reasoning
            
            # Subject line reasoning
            subject_reasoning = talking_points_result.get('subject_line_reasoning', '') if isinstance(talking_points_result, dict) else ''
            row['subject_line_reasoning'] = subject_reasoning[:200] + '...' if len(subject_reasoning) > 200 else subject_reasoning
            
            csv_rows.append(row)
        
        # Write to CSV file
        if csv_rows:
            fieldnames = list(csv_rows[0].keys())
            
            with open(output_csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(csv_rows)
            
            logger.info(f"Successfully saved {len(csv_rows)} processed leads to: {output_csv_filename}")
            
            # Log summary statistics
            total_qualified = len([row for row in csv_rows if row['qualification_check_passed']])
            avg_score = sum(float(row['contentq_score']) for row in csv_rows if row['contentq_score']) / len(csv_rows)
            
            logger.info(f"Summary: {total_qualified}/{len(csv_rows)} leads qualified, Average ContentQ Score: {avg_score:.1f}")
        else:
            logger.warning("No data to write to CSV file")
            
    except Exception as e:
        logger.error(f"Error saving results to CSV file {output_csv_filename}: {str(e)}")
        raise


# Example Test Inputs (kept for backward compatibility)
TEST_INPUTS = {
    "leads_to_process": [
        {
            "linkedinUrl": "https://www.linkedin.com/in/ACoAAAGSbXUBOy1FuiRw9wcaJ-_24TnS_u4dgS8",
            "Company": "Metadata.Io",
            "firstName": "Dee", 
            "lastName": "Acosta 🤖",
            "companyWebsite": "metadata.io",
            "emailId": "dee.acosta@metadata.io",
            "jobTitle": "Ad AI, Sales, and GTM	"
        },
        {
            "linkedinUrl": "https://www.linkedin.com/in/ACoAAAAMYK4BCyNT23Ui4i6ijdr7-Xu2s8H1pa4",
            "Company": "Stacklok",
            "firstName": "Christine",
            "lastName": "Simonini", 
            "companyWebsite": "stacklok.com",
            "emailId": "csimonini@appomni.com",
            "jobTitle": "Advisor"
        },
        {
            "linkedinUrl": "https://www.linkedin.com/in/ACoAACngUhwBxcSAdAIis1EyHyGe0oSxoLg0lVE",
            "Company": "Cresta",
            "firstName": "Kurtis",
            "lastName": "Wagner",
            "companyWebsite": "cresta.com", 
            "emailId": "kurtis@cresta.ai",
            "jobTitle": "AI Agent Architect"
        }
    ]
}

async def validate_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """
    Custom validation function for the workflow outputs.
    
    Validates that:
    1. Leads were processed through qualification
    2. Qualified leads received ContentQ scoring and talking points
    3. Final results contain all required fields for qualified leads
    4. Output structure includes lead information and talking points
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating lead scoring workflow outputs...")
    
    # Check if we have the expected output fields
    assert 'processed_leads' in outputs, "Validation Failed: 'processed_leads' key missing."
    # assert 'original_leads' in outputs, "Validation Failed: 'original_leads' key missing."
    
    # original_leads = outputs.get('original_leads', [])
    processed_results = outputs.get('processed_leads', [])
    
    # logger.info(f"Original leads count: {len(original_leads)}")
    logger.info(f"Processed results count: {len(processed_results)}")
    
    # Validate that we have some processed results
    assert len(processed_results) > 0, "Validation Failed: No leads were processed successfully."
    
    # Validate the structure of processed results
    for i, result in enumerate(processed_results):
        logger.info(f"Validating result {i+1}...")
        
        # Check for required lead information (from passthrough data)
        required_lead_fields = ['Company', 'firstName', 'lastName', 'emailId', 'jobTitle']
        for field in required_lead_fields:
            assert field in result, f"Validation Failed: Missing lead field '{field}' in result {i+1}"
        
        # Check for talking points result
        assert 'talking_points_result' in result, f"Validation Failed: Missing talking_points_result in result {i+1}"
        
        talking_points = result['talking_points_result']
        required_talking_point_fields = [
            'contentq_score', 'contentq_score_text', 'talking_point_1', 'talking_point_1_reasoning_citations', 
            'talking_point_2', 'talking_point_2_reasoning_citations', 'talking_point_3', 'talking_point_3_reasoning_citations',
            'talking_point_4', 'talking_point_4_reasoning_citations', 'contentq_pitch', 'contentq_pitch_reasoning_citations',
            'email_subject_line', 'subject_line_reasoning'
        ]
        
        for field in required_talking_point_fields:
            assert field in talking_points, f"Validation Failed: Missing talking point field '{field}' in result {i+1}"
            if field == 'contentq_score':
                assert talking_points[field] > 0, f"Validation Failed: ContentQ score is less than 0 in result {i+1}"
                continue
            assert len(talking_points[field]) > 0, f"Validation Failed: Empty talking point field '{field}' in result {i+1}"
        
        logger.info(f"  ✓ Lead: {result['firstName']} {result['lastName']} from {result['Company']}")
        logger.info(f"  ✓ Email Subject: {talking_points['email_subject_line']}")
        logger.info(f"  ✓ ContentQ Pitch: {talking_points['contentq_pitch'][:100]}...")
        
        # Check for ContentQ score from final talking points
        logger.info(f"  ✓ ContentQ Score: {talking_points['contentq_score']}")
        logger.info(f"  ✓ Talking Point 1: {talking_points['talking_point_1'][:80]}...")
        logger.info(f"  ✓ Has reasoning for all points: {len([f for f in required_talking_point_fields if 'reasoning' in f])} reasoning fields")
    
    logger.info("✓ All validation checks passed successfully!")
    return True

async def run_batch_workflow(input_csv: str,
                             output_csv: str, 
                             batch_start: int,
                             batch_end: int,
                             batch_number: int,
                             total_batches: int) -> tuple:
    """
    Run a single batch of the workflow.
    
    Returns:
        Tuple of (status, outputs, duration, leads_processed)
    """
    batch_start_time = time.time()
    batch_size = batch_end - batch_start
    test_name = f"Batch {batch_number}/{total_batches}"
    
    print(f"  Loading {batch_size} leads from rows {batch_start}-{batch_end-1}...")
    
    try:
        # Load CSV data for this batch
        leads_data = load_csv_data(input_csv, batch_start, batch_end)
        initial_inputs = {"leads_to_process": leads_data}
        
        print(f"  Running workflow for {len(leads_data)} leads...")
        
        # Run workflow for this batch
        final_run_status_obj, final_run_outputs = await run_single_workflow(
            input_data=initial_inputs,
            test_name=test_name
        )
        
        # Save batch results to file
        leads_processed = 0
        if final_run_outputs and 'processed_leads' in final_run_outputs:
            save_results_to_csv(final_run_outputs, output_csv)
            leads_processed = len(final_run_outputs['processed_leads'])
            print(f"  Saved {leads_processed} results to: {Path(output_csv).name}")
        else:
            print(f"  ⚠️  No results to save")
        
        batch_duration = time.time() - batch_start_time
        
        return final_run_status_obj, final_run_outputs, batch_duration, leads_processed
        
    except Exception as e:
        batch_duration = time.time() - batch_start_time
        print(f"  ❌ Batch failed: {str(e)}")
        return None, None, batch_duration, 0


def combine_existing_batch_files(batch_folder: str, output_csv: str) -> None:
    """
    Combine all existing batch CSV files in the batch folder into a single output file.
    
    Args:
        batch_folder: Path to folder containing batch result files
        output_csv: Path to final combined output CSV file
    """
    batch_folder_path = Path(batch_folder)
    
    if not batch_folder_path.exists():
        print(f"❌ Batch folder does not exist: {batch_folder}")
        return
    
    # Find all CSV files in the batch folder
    batch_files = list(batch_folder_path.glob("batch_*.csv"))
    
    if not batch_files:
        print(f"❌ No batch files found in: {batch_folder}")
        return
    
    # Sort batch files by name to ensure consistent ordering
    batch_files.sort()
    batch_file_paths = [str(f) for f in batch_files]
    
    print(f"📁 Found {len(batch_files)} batch files in: {batch_folder}")
    for batch_file in batch_files:
        print(f"  - {batch_file.name}")
    
    # Use existing combine function
    combine_batch_results(batch_file_paths, output_csv)
    
    print(f"✅ Combined {len(batch_files)} batch files into: {output_csv}")


def combine_batch_results(batch_output_files: List[str], final_output_csv: str) -> None:
    """
    Combine results from multiple batch CSV files into a single output file.
    
    Args:
        batch_output_files: List of batch CSV file paths
        final_output_csv: Path to final combined output CSV file
    """
    logger.info(f"Combining {len(batch_output_files)} batch result files into: {final_output_csv}")
    
    combined_rows = []
    
    for i, batch_file in enumerate(batch_output_files):
        if not Path(batch_file).exists():
            logger.warning(f"Batch file does not exist: {batch_file}")
            continue
            
        try:
            # Read batch CSV file
            batch_df = pd.read_csv(batch_file)
            logger.info(f"Loaded {len(batch_df)} results from batch file {i+1}: {batch_file}")
            
            # Convert to list of dictionaries and add to combined results
            batch_rows = batch_df.to_dict('records')
            combined_rows.extend(batch_rows)
            
        except Exception as e:
            logger.error(f"Error reading batch file {batch_file}: {str(e)}")
            continue
    
    if combined_rows:
        # Write combined results to final CSV
        combined_df = pd.DataFrame(combined_rows)
        combined_df.to_csv(final_output_csv, index=False)
        
        logger.info(f"Successfully combined {len(combined_rows)} total results into: {final_output_csv}")
        
        # Log summary statistics
        total_qualified = len([row for row in combined_rows if row.get('qualification_check_passed', False)])
        avg_score = sum(float(row.get('contentq_score', 0)) for row in combined_rows if row.get('contentq_score')) / len(combined_rows) if combined_rows else 0
        
        logger.info(f"Final Summary: {total_qualified}/{len(combined_rows)} leads qualified, Average ContentQ Score: {avg_score:.1f}")
    else:
        logger.warning("No batch results to combine")

# counter = 0
async def run_single_workflow(input_data: Dict[str, Any], test_name: str) -> tuple:
    """
    Run a single workflow instance with given input data.
    
    Args:
        input_data: Input data for the workflow
        test_name: Name for this workflow test
        
    Returns:
        Tuple of (final_run_status_obj, final_run_outputs)
    """
    import io
    import contextlib
    
    logger.info(f"Starting {test_name}...")
    
    # Capture all stdout to prevent WorkflowRunRead objects from being printed
    captured_output = io.StringIO()
    
    try:
        with contextlib.redirect_stdout(captured_output):
            final_run_status_obj, final_run_outputs = await run_workflow_test(
                test_name=test_name,
                workflow_graph_schema=workflow_graph_schema,
                initial_inputs=input_data,
                expected_final_status=WorkflowRunStatus.COMPLETED,
                setup_docs=None,
                cleanup_docs=None,
                stream_intermediate_results=False,  # Suppress verbose workflow output
                dump_artifacts=False,  # Don't create artifact files
                poll_interval_sec=5,
                timeout_sec=600  # 10 minutes for comprehensive research and analysis
            )
    except Exception as e:
        logger.error(f"Workflow execution failed: {str(e)}")
        raise
    
    # Log completion status without printing the full object
    status_str = str(final_run_status_obj.status) if final_run_status_obj else "None"
    logger.info(f"{test_name} completed with status: {status_str}")
    
    return final_run_status_obj, final_run_outputs


def print_partial_statistics(overall_start_time: float, 
                            batch_timings: List[Dict],
                            total_leads_processed: int,
                            successful_batches: int,
                            failed_batches: int,
                            total_delay_time: float,
                            current_batch: int,
                            total_batches: int,
                            start_row: int,
                            batch_size: int) -> None:
    """
    Print partial statistics when job stops due to failure.
    
    Args:
        overall_start_time: Start time of the overall job
        batch_timings: List of batch timing data
        total_leads_processed: Total leads processed before failure
        successful_batches: Number of successful batches
        failed_batches: Number of failed batches
        total_delay_time: Total artificial delay time
        current_batch: Current batch number where failure occurred
        total_batches: Total planned batches
        start_row: Starting row of processing
        batch_size: Batch size
    """
    current_time = time.time()
    partial_execution_time = current_time - overall_start_time
    
    # Calculate pure workflow time from successful batches
    successful_batch_timings = [b for b in batch_timings if b['leads_processed'] > 0]
    pure_workflow_time = sum(b['duration'] for b in successful_batch_timings)
    
    print(f"\n{'='*60}")
    print(f"JOB STOPPED DUE TO BATCH FAILURE - PARTIAL STATISTICS")
    print(f"{'='*60}")
    
    print(f"📊 PROGRESS AT FAILURE:")
    print(f"  Batches completed: {successful_batches}/{total_batches}")
    print(f"  Batches failed: {failed_batches}")
    print(f"  Current batch: {current_batch}")
    print(f"  Leads processed: {total_leads_processed}")
    
    # Calculate processed rows
    processed_rows = successful_batches * batch_size
    if current_batch > 1:
        last_successful_row = start_row + processed_rows - 1
        print(f"  Rows processed: {start_row} to {last_successful_row} ({processed_rows} rows)")
    else:
        print(f"  Rows processed: None (failed on first batch)")
    
    print(f"\n⏰ TIMING AT FAILURE:")
    print(f"  Total execution time: {partial_execution_time:.1f} seconds ({partial_execution_time/60:.1f} minutes)")
    print(f"  Pure workflow time: {pure_workflow_time:.1f} seconds ({pure_workflow_time/60:.1f} minutes)")
    print(f"  Artificial delay time: {total_delay_time:.1f} seconds ({total_delay_time/60:.1f} minutes)")
    
    if total_leads_processed > 0:
        print(f"  Average time per lead: {pure_workflow_time/total_leads_processed:.1f} seconds")
        print(f"  Throughput: {total_leads_processed/(pure_workflow_time/3600):.1f} leads/hour")
    
    if successful_batch_timings:
        batch_durations = [b['duration'] for b in successful_batch_timings]
        print(f"  Average batch duration: {sum(batch_durations)/len(batch_durations):.1f} seconds")
        print(f"  Fastest batch: {min(batch_durations):.1f} seconds")
        print(f"  Slowest batch: {max(batch_durations):.1f} seconds")
    
    print(f"\n📈 SUCCESSFUL BATCHES BREAKDOWN:")
    if successful_batch_timings:
        for batch_timing in successful_batch_timings:
            batch_num = batch_timing['batch_num']
            duration = batch_timing['duration']
            leads = batch_timing['leads_processed']
            avg_time = batch_timing['avg_time_per_lead']
            print(f"  Batch {batch_num:2d}: {duration:5.1f}s total, {leads:2d} leads, {avg_time:4.1f}s/lead")
    else:
        print(f"  No batches completed successfully")
    
    print(f"{'='*60}")


async def main_batch_lead_scoring(input_csv: Optional[str] = None,
                                  output_csv: Optional[str] = None,
                                  batch_folder: Optional[str] = None,
                                  start_row: int = 0,
                                  end_row: Optional[int] = None,
                                  batch_size: int = 20,
                                  delay: int = 45,
                                  stop_on_failure: bool = True):
    """
    Main function for batch processing lead scoring workflow.
    
    Args:
        input_csv: Path to input CSV file with lead data
        output_csv: Path to output CSV file for results  
        batch_folder: Folder to store individual batch result files
        start_row: Starting row index for processing (0-based, excluding header)
        end_row: Ending row index for processing (0-based, exclusive)
        batch_size: Number of leads to process in each batch
        delay: Delay in seconds between consecutive batch workflows
        stop_on_failure: If True, stop processing and throw exception on batch failure
    """
    print(f"--- Starting Batch Lead Scoring Workflow ---")
    print(f"Configuration:")
    print(f"  Input CSV: {input_csv if input_csv else 'Using default test data'}")
    print(f"  Output CSV: {output_csv if output_csv else 'No output file'}")
    print(f"  Batch folder: {batch_folder}")
    print(f"  Row range: {start_row} to {end_row if end_row else 'end'}")
    print(f"  Batch size: {batch_size}")
    print(f"  Inter-batch delay: {delay} seconds")
    print(f"  Stop on failure: {stop_on_failure}")
    print()
    
    # Start overall timing
    overall_start_time = time.time()
    
    # Handle case where no CSV is provided (use default test data)
    if not input_csv or not Path(input_csv).exists():
        if input_csv:
            print(f"CSV file not found: {input_csv}")
        print("Using default test inputs (single workflow run)")
        
        # Run single workflow with default test data
        test_name = "Lead Scoring and Personalized Talking Points Generation"
        workflow_start_time = time.time()
        final_run_status_obj, final_run_outputs = await run_single_workflow(
            input_data=TEST_INPUTS,
            test_name=test_name
        )
        workflow_end_time = time.time()
        
        # Save results if output file specified
        if output_csv and final_run_outputs:
            print(f"Saving results to: {output_csv}")
            save_results_to_csv(final_run_outputs, output_csv)
            print(f"Results saved successfully to: {output_csv}")
        
        # Calculate and display timing stats for single run
        overall_duration = time.time() - overall_start_time
        workflow_duration = workflow_end_time - workflow_start_time
        leads_processed = len(final_run_outputs.get('processed_leads', [])) if final_run_outputs else 0
        
        print(f"\n{'='*60}")
        print(f"TIMING STATISTICS - SINGLE RUN")
        print(f"{'='*60}")
        print(f"Total execution time: {overall_duration:.1f} seconds ({overall_duration/60:.1f} minutes)")
        print(f"Workflow execution time: {workflow_duration:.1f} seconds ({workflow_duration/60:.1f} minutes)")
        print(f"Leads processed: {leads_processed}")
        if leads_processed > 0:
            print(f"Average time per lead: {workflow_duration/leads_processed:.1f} seconds")
        print(f"{'='*60}")
        
        return final_run_status_obj, final_run_outputs
    
    # Calculate total rows to process and number of batches
    df = pd.read_csv(input_csv)
    total_rows = len(df)
    
    # Determine actual end row
    actual_end_row = min(end_row if end_row is not None else total_rows, total_rows)
    
    # Calculate batch ranges
    total_leads_to_process = actual_end_row - start_row
    total_batches = (total_leads_to_process + batch_size - 1) // batch_size  # Ceiling division
    
    print(f"Batch Processing Plan:")
    print(f"  Total rows in CSV: {total_rows}")
    print(f"  Processing rows {start_row} to {actual_end_row-1} ({total_leads_to_process} leads)")
    print(f"  Batch size: {batch_size}")
    print(f"  Total batches: {total_batches}")
    print()
    
    # Create batch results folder
    batch_folder_path = Path(batch_folder)
    batch_folder_path.mkdir(parents=True, exist_ok=True)
    print(f"Batch results will be stored in: {batch_folder_path.resolve()}")
    
    batch_output_files = []
    successful_batches = 0
    failed_batches = 0
    
    # Timing tracking for batches
    batch_timings = []
    total_leads_processed = 0
    total_delay_time = 0  # Track artificial delay time separately
    batch_processing_start_time = time.time()
    
    # Process each batch sequentially
    for batch_num in range(1, total_batches + 1):
        batch_start = start_row + (batch_num - 1) * batch_size
        batch_end = min(batch_start + batch_size, actual_end_row)
        
        # Create batch-specific output file in batch folder
        output_suffix = Path(output_csv).suffix
        batch_output_file = batch_folder_path / f"batch_{batch_num:03d}_rows_{batch_start}-{batch_end-1}{output_suffix}"
        batch_output_files.append(str(batch_output_file))
        
        print(f"{'='*60}")
        print(f"BATCH {batch_num}/{total_batches}: Processing rows {batch_start}-{batch_end-1}")
        print(f"{'='*60}")
        
        # Run workflow for this batch
        batch_status, batch_outputs, batch_duration, leads_processed = await run_batch_workflow(
            input_csv=input_csv,
            output_csv=str(batch_output_file),
            batch_start=batch_start,
            batch_end=batch_end,
            batch_number=batch_num,
            total_batches=total_batches
        )
        
        # Track timing and processing stats
        batch_timings.append({
            'batch_num': batch_num,
            'duration': batch_duration,
            'leads_processed': leads_processed,
            'avg_time_per_lead': batch_duration / leads_processed if leads_processed > 0 else 0
        })
        total_leads_processed += leads_processed
        
        # Check batch result
        if batch_status and batch_status.status == WorkflowRunStatus.COMPLETED:
            successful_batches += 1
            print(f"✅ Batch {batch_num} completed in {batch_duration:.1f}s ({leads_processed} leads)")
        else:
            failed_batches += 1
            error_msg = f"Batch {batch_num} failed"
            print(f"❌ {error_msg}")
            
            if stop_on_failure:
                print_partial_statistics(
                    overall_start_time=overall_start_time,
                    batch_timings=batch_timings,
                    total_leads_processed=total_leads_processed,
                    successful_batches=successful_batches,
                    failed_batches=failed_batches,
                    total_delay_time=total_delay_time,
                    current_batch=batch_num,
                    total_batches=total_batches,
                    start_row=start_row,
                    batch_size=batch_size
                )
                raise RuntimeError(f"Job stopped due to batch failure. {error_msg}")
        
        print(f"Batch {batch_num} completed. Progress: {batch_num}/{total_batches} batches")
        
        # Add delay between batches (except after the last batch)
        if batch_num < total_batches and delay > 0:
            print(f"⏳ Waiting {delay} seconds before next batch...")
            delay_start_time = time.time()
            await asyncio.sleep(delay)
            delay_end_time = time.time()
            actual_delay_time = delay_end_time - delay_start_time
            total_delay_time += actual_delay_time
        
        print()
    
    batch_processing_end_time = time.time()
    total_batch_processing_time = batch_processing_end_time - batch_processing_start_time
    
    # Calculate pure workflow time (excluding artificial delays)
    pure_workflow_time = total_batch_processing_time - total_delay_time
    
    # Combine all batch results into final output file
    print(f"{'='*60}")
    print(f"COMBINING BATCH RESULTS")
    print(f"{'='*60}")
    
    try:
        combine_batch_results(batch_output_files, output_csv)
        print(f"✓ All batch results combined into: {output_csv}")
        
        # Keep batch files for reference (don't clean up automatically)
        print(f"✓ Individual batch files preserved in: {batch_folder_path}")
        
    except Exception as e:
        logger.error(f"Error combining batch results: {str(e)}")
        print(f"✗ Error combining batch results: {str(e)}")
    
    # Calculate overall timing statistics
    overall_end_time = time.time()
    total_execution_time = overall_end_time - overall_start_time
    
    # Calculate statistics from successful batches only
    successful_batch_timings = [b for b in batch_timings if b['leads_processed'] > 0]
    
    # Final summary with comprehensive timing statistics
    print(f"{'='*60}")
    print(f"BATCH PROCESSING COMPLETE")
    print(f"{'='*60}")
    print(f"Total batches: {total_batches}")
    print(f"Successful batches: {successful_batches}")
    print(f"Failed batches: {failed_batches}")
    print(f"Final merged results saved to: {output_csv}")
    print(f"Individual batch files available in: {batch_folder_path}")
    
    print(f"\n{'='*60}")
    print(f"COMPREHENSIVE TIMING STATISTICS")
    print(f"{'='*60}")
    
    # Overall timing
    print(f"📊 OVERALL PERFORMANCE:")
    print(f"  Total execution time: {total_execution_time:.1f} seconds ({total_execution_time/60:.1f} minutes)")
    print(f"  Pure workflow time: {pure_workflow_time:.1f} seconds ({pure_workflow_time/60:.1f} minutes)")
    print(f"  Artificial delay time: {total_delay_time:.1f} seconds ({total_delay_time/60:.1f} minutes)")
    print(f"  Setup/cleanup time: {total_execution_time - total_batch_processing_time:.1f} seconds")
    print(f"  Total leads processed: {total_leads_processed}")
    
    if total_leads_processed > 0:
        print(f"  Pure workflow time per lead: {pure_workflow_time/total_leads_processed:.1f} seconds")
        print(f"  Workflow throughput (excluding delays): {total_leads_processed/(pure_workflow_time/3600):.1f} leads/hour")
        print(f"  Overall throughput (including delays): {total_leads_processed/(total_execution_time/3600):.1f} leads/hour")
        
        # Time breakdown percentages
        print(f"\n⏰ TIME BREAKDOWN:")
        workflow_pct = (pure_workflow_time / total_execution_time) * 100
        delay_pct = (total_delay_time / total_execution_time) * 100
        setup_pct = ((total_execution_time - total_batch_processing_time) / total_execution_time) * 100
        
        print(f"  Pure workflow processing: {workflow_pct:.1f}% ({pure_workflow_time:.1f}s)")
        print(f"  Artificial delays: {delay_pct:.1f}% ({total_delay_time:.1f}s)")
        print(f"  Setup/cleanup overhead: {setup_pct:.1f}% ({total_execution_time - total_batch_processing_time:.1f}s)")
        
        if delay > 0:
            efficiency_ratio = pure_workflow_time / (pure_workflow_time + total_delay_time)
            print(f"  Processing efficiency: {efficiency_ratio*100:.1f}% (workflow time / total processing time)")
    
    # Batch-level statistics
    if successful_batch_timings:
        batch_durations = [b['duration'] for b in successful_batch_timings]
        per_lead_times = [b['avg_time_per_lead'] for b in successful_batch_timings if b['avg_time_per_lead'] > 0]
        
        print(f"\n⏱️  BATCH PERFORMANCE:")
        print(f"  Average batch duration: {sum(batch_durations)/len(batch_durations):.1f} seconds")
        print(f"  Fastest batch: {min(batch_durations):.1f} seconds")
        print(f"  Slowest batch: {max(batch_durations):.1f} seconds")
        print(f"  Batch duration std dev: {(sum([(x - sum(batch_durations)/len(batch_durations))**2 for x in batch_durations])/len(batch_durations))**0.5:.1f} seconds")
        
        if per_lead_times:
            print(f"\n🎯 PER-LEAD PERFORMANCE:")
            print(f"  Average time per lead: {sum(per_lead_times)/len(per_lead_times):.1f} seconds")
            print(f"  Fastest lead processing: {min(per_lead_times):.1f} seconds")
            print(f"  Slowest lead processing: {max(per_lead_times):.1f} seconds")
        
        print(f"\n📈 DETAILED BATCH BREAKDOWN:")
        for batch_timing in successful_batch_timings:
            batch_num = batch_timing['batch_num']
            duration = batch_timing['duration']
            leads = batch_timing['leads_processed']
            avg_time = batch_timing['avg_time_per_lead']
            print(f"  Batch {batch_num:2d}: {duration:5.1f}s total, {leads:2d} leads, {avg_time:4.1f}s/lead")
    
    # Performance projections
    if successful_batches > 0 and total_leads_processed > 0:
        avg_pure_batch_time = pure_workflow_time / successful_batches
        avg_leads_per_batch = total_leads_processed / successful_batches
        avg_delay_per_batch = total_delay_time / max(successful_batches - 1, 1)  # -1 because last batch has no delay
        
        print(f"\n🔮 PERFORMANCE PROJECTIONS:")
        print(f"  Pure workflow time estimates (excluding delays):")
        print(f"    100 leads: {(avg_pure_batch_time * 100 / avg_leads_per_batch)/60:.1f} minutes")
        print(f"    500 leads: {(avg_pure_batch_time * 500 / avg_leads_per_batch)/60:.1f} minutes")
        print(f"    1000 leads: {(avg_pure_batch_time * 1000 / avg_leads_per_batch)/60:.1f} minutes")
        
        if delay > 0:
            print(f"  Total time estimates (including {delay}s delays):")
            batches_for_100 = (100 + avg_leads_per_batch - 1) // avg_leads_per_batch  # Ceiling division
            batches_for_500 = (500 + avg_leads_per_batch - 1) // avg_leads_per_batch
            batches_for_1000 = (1000 + avg_leads_per_batch - 1) // avg_leads_per_batch
            
            total_time_100 = (avg_pure_batch_time * 100 / avg_leads_per_batch) + ((batches_for_100 - 1) * delay)
            total_time_500 = (avg_pure_batch_time * 500 / avg_leads_per_batch) + ((batches_for_500 - 1) * delay)
            total_time_1000 = (avg_pure_batch_time * 1000 / avg_leads_per_batch) + ((batches_for_1000 - 1) * delay)
            
            print(f"    100 leads: {total_time_100/60:.1f} minutes ({batches_for_100} batches)")
            print(f"    500 leads: {total_time_500/60:.1f} minutes ({batches_for_500} batches)")
            print(f"    1000 leads: {total_time_1000/60:.1f} minutes ({batches_for_1000} batches)")
    
    print(f"{'='*60}")
    
    return successful_batches, failed_batches




def parse_arguments():
    """Parse command line arguments for CSV input/output functionality."""
    parser = argparse.ArgumentParser(
        description="Lead Scoring and Personalized Talking Points Generation Workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default hardcoded test data
  python wf_lead_scoring_personalized_talking_points.py
  
  # Process entire CSV file in batches (default: batch size 20, rows 0-250)
  python wf_lead_scoring_personalized_talking_points.py --input leads.csv --output results.csv
  
  # Process specific row range with custom batch size
  python wf_lead_scoring_personalized_talking_points.py --input leads.csv --output results.csv --start-row 10 --end-row 100 --batch-size 15
  
  # Process from row 5 to 50 with batch size 10 and custom batch folder
  python wf_lead_scoring_personalized_talking_points.py --input leads.csv --output results.csv --start-row 5 --end-row 50 --batch-size 10 --batch-folder my_batches/
  
  # Process with custom delay between batches (30 seconds instead of default 45)
  python wf_lead_scoring_personalized_talking_points.py --input leads.csv --output results.csv --delay 30
  
  # Process with no delay between batches (for faster processing)
  python wf_lead_scoring_personalized_talking_points.py --input leads.csv --output results.csv --delay 0
  
  # Continue processing even if some batches fail
  python wf_lead_scoring_personalized_talking_points.py --input leads.csv --output results.csv --continue-on-failure
  
  # Combine existing batch files without running workflows
  python wf_lead_scoring_personalized_talking_points.py --output results.csv --combine-only

Batch Processing:
  The workflow processes leads in batches to manage resource usage and provide progress tracking.
  Each batch runs sequentially, with individual results stored in the batch folder.
  After all batches complete, results are combined into the final output CSV file.
  
  Default behavior: Process rows 0-250 in batches of 20 leads each with 60-second delays.
  Individual batch files are saved to batch_results/ folder and preserved for reference.
  
  Inter-batch Delay:
  A configurable delay is added between batches to prevent API rate limiting and reduce server load.
  Set --delay 0 to disable delays for faster processing (use with caution).
  
  Failure Handling:
  By default, the job stops and throws an exception if any batch fails (--stop-on-failure).
  Use --continue-on-failure to process all batches even if some fail, then combine available results.
  When a job stops due to failure, partial statistics are displayed showing progress made.
  
  Combine-Only Mode:
  Use --combine-only to merge existing batch files without running any workflows.
  This is useful for combining results from previous runs or after manual intervention.
  Only requires --output argument; finds all batch_*.csv files in the batch folder.

Required CSV columns (supports multiple naming conventions):
  • LinkedIn URL: 'linkedinUrl', 'LinkedIn URL', 'LinkedIn'
  • Company: 'Company', 'Company Name', 'Organization' 
  • First Name: 'firstName', 'First Name', 'First'
  • Last Name: 'lastName', 'Last Name', 'Last'
  • Company Website: 'companyWebsite', 'Company website', 'Website', 'Company Website'
  • Email: 'emailId', 'Email ID', 'Email', 'Email Address'
  • Job Title: 'jobTitle', 'Job Title', 'Title', 'Position'

Example CSV formats supported:
  linkedinUrl,Company,First Name,Last Name,Company website,Email ID,Job Title
  LinkedIn URL,Company Name,firstName,lastName,Website,Email,Position
        """
    )

    # Get the directory where this script is located
    current_file_dir = Path(__file__).parent
    
    # Set default file paths relative to current script directory
    default_input_csv = str(current_file_dir / "leads.csv")
    default_output_csv = str(current_file_dir / "results.csv")
    default_batch_folder = str(current_file_dir / "batch_results")
    start_row = 0
    end_row = 30  # 250
    batch_size = 15
    default_delay_in_between_batches = 90  # 60
    default_stop_on_failure = True
    default_combine_batch_files_only_mode = False

    kwargs = {
        'type': str,
        'help': 'Path to input CSV file containing lead data'
    }
    if default_input_csv is not None:
        kwargs['default'] = default_input_csv
        kwargs['help'] = f'Path to input CSV file containing lead data (default: {default_input_csv})'
    
    parser.add_argument(
        '--input', '--input-csv', 
        **kwargs
    )
    
    kwargs = {
        'type': str,
        'help': 'Path to output CSV file for processed results'
    }
    if default_output_csv is not None:
        kwargs['default'] = default_output_csv
        kwargs['help'] = f'Path to output CSV file for processed results (default: {default_output_csv})'
    
    parser.add_argument(
        '--output', '--output-csv',
        **kwargs
    )
    
    parser.add_argument(
        '--start-row',
        type=int,
        default=start_row,
        help='Starting row index for processing (0-based, excluding header). Default: 0'
    )
    
    kwargs = {
        'type': int,
        'help': 'Ending row index for processing (0-based, exclusive). If not specified, process to end of file'
    }
    if end_row is not None:
        kwargs['default'] = end_row
        kwargs['help'] = f'Ending row index for processing (0-based, exclusive). If not specified, process to end of file (default: {end_row})'
    
    parser.add_argument(
        '--end-row',
        **kwargs
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=batch_size,
        help=f'Number of leads to process in each batch. Default: {batch_size}'
    )
    
    parser.add_argument(
        '--batch-folder',
        type=str,
        default=default_batch_folder,
        help=f'Folder to store individual batch result files. Default: {default_batch_folder}'
    )
    
    parser.add_argument(
        '--delay',
        type=int,
        default=default_delay_in_between_batches,
        help=f'Delay in seconds between consecutive batch workflows. Default: {default_delay_in_between_batches} seconds'
    )
    
    parser.add_argument(
        '--stop-on-failure',
        action='store_true',
        default=default_stop_on_failure,
        help='Stop processing and throw exception if any batch fails. Default: True'
    )
    
    parser.add_argument(
        '--continue-on-failure',
        action='store_false',
        dest='stop_on_failure',
        help='Continue processing remaining batches even if some fail. Overrides --stop-on-failure'
    )
    
    parser.add_argument(
        '--combine-only',
        action='store_true',
        default=default_combine_batch_files_only_mode,
        help='Only combine existing batch files in batch folder without running workflows. Default: False'
    )
    
    args = parser.parse_args()
    
    # Convert input path to absolute path and validate
    input_path = Path(args.input).resolve()
    print(f"Input path: {input_path}")
    
    # Only validate file existence if it's not using the default path
    # (allow default path to not exist for backward compatibility)
    if args.input != default_input_csv and not input_path.exists():
        parser.error(f"Input CSV file does not exist: {args.input}")
    
    # Update args with resolved paths
    args.input = str(input_path)
    args.output = str(Path(args.output).resolve())
    
    if args.start_row < 0:
        parser.error("Start row must be >= 0")
        
    if args.end_row is not None and args.end_row <= args.start_row:
        parser.error("End row must be greater than start row")
        
    if args.batch_size <= 0:
        parser.error("Batch size must be greater than 0")
        
    if args.delay < 0:
        parser.error("Delay must be >= 0 seconds")
    
    return args

if __name__ == "__main__":
    print("="*80)
    print("Lead Scoring and Personalized Talking Points Generation Workflow")
    print("="*80)
    logging.basicConfig(level=logging.INFO)
    
    # Parse command line arguments
    args = parse_arguments()
    
    print(f"Configuration:")
    print(f"  Input CSV: {args.input if args.input else 'Using default test data'}")
    print(f"  Output CSV: {args.output if args.output else 'No output file'}")
    print(f"  Batch folder: {args.batch_folder}")
    print(f"  Row range: {args.start_row} to {args.end_row if args.end_row else 'end'}")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Inter-batch delay: {args.delay} seconds")
    print(f"  Stop on failure: {args.stop_on_failure}")
    print(f"  Combine only: {args.combine_only}")
    print()
    
    # Handle combine-only mode
    if args.combine_only:
        print("🔄 COMBINE-ONLY MODE: Combining existing batch files...")
        combine_existing_batch_files(args.batch_folder, args.output)
        print("✅ Combine-only operation completed.")
        sys.exit(0)
    
    asyncio.run(main_batch_lead_scoring(
        input_csv=args.input,
        output_csv=args.output,
        batch_folder=args.batch_folder,
        start_row=args.start_row,
        end_row=args.end_row,
        batch_size=args.batch_size,
        delay=args.delay,
        stop_on_failure=args.stop_on_failure
    ))
