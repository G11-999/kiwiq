from kiwi_client.workflows.document_models.customer_docs import (
    # User DNA
    USER_DNA_DOCNAME,
    USER_DNA_NAMESPACE_TEMPLATE,
    USER_DNA_IS_VERSIONED,
    # Content Strategy
    CONTENT_STRATEGY_DOCNAME,
    CONTENT_STRATEGY_NAMESPACE_TEMPLATE,
    CONTENT_STRATEGY_IS_VERSIONED,
    # NOTE: Style test results are NOT stored/persisted
)
from kiwi_client.workflows.llm_inputs.style_test_workflow import (
    STYLE_TEST_SYSTEM_PROMPT,
    STYLE_TEST_GENERATION_PROMPT,
    STYLE_TEST_LLM_OUTPUT_SCHEMA,
    DNA_UPDATE_INTERPRETATION_PROMPT,
    DNA_UPDATE_EXECUTION_PROMPT,
)
from kiwi_client.workflows.llm_inputs.user_understanding import (
    GENERATION_SCHEMA,
)

llm_provider = "anthropic"
generation_model_name = "claude-3-7-sonnet-20250219"
temperature = 0.7  # Slightly higher for creative style variation
max_tokens = 3000  # Increased for generating two posts
max_iterations = 1  # No feedback loop, single generation

# Full GraphSchema Structure
workflow_graph_schema = {
  "nodes": {
    # --- 1. Input Node ---
    "input_node": {
      "node_id": "input_node",
      "node_name": "input_node",
      "node_config": {
      },
      "dynamic_output_schema": {
          "fields": {
              "customer_context_doc_configs": {
                  "type": "list",
                  "required": True,
                  "description": "List of document identifiers (namespace/docname pairs) for customer context like DNA, strategy docs."
              },
              "entity_username": { "type": "str", "required": True, "description": "Username of the entity for which the style test is being conducted." }
          }
        }
    },

    # --- 2. Load Customer Context Documents ---
    "load_all_context_docs": {
        "node_id": "load_all_context_docs",
        "node_name": "load_customer_data",
        "node_config": {
            "load_configs_input_path": "customer_context_doc_configs",
            "global_is_shared": False,
            "global_is_system_entity": False,
            "global_schema_options": {"load_schema": False},
        },
    },

    # --- 3. Construct Style Test Prompt ---
    "construct_style_test_prompt": {
      "node_id": "construct_style_test_prompt",
      "node_name": "prompt_constructor",
      "enable_node_fan_in": True,
      "node_config": {
        "prompt_templates": {
          "style_generation_prompt": {
            "id": "style_generation_prompt",
            "template": STYLE_TEST_GENERATION_PROMPT,
            "variables": {
              "user_dna": None,
              "content_strategy": None,
            },
            "construct_options": {
               "user_dna": "user_dna",
               "content_strategy": "content_strategy",
            }
          },
          "system_prompt": {
            "id": "system_prompt",
            "template": STYLE_TEST_SYSTEM_PROMPT,
            "variables": {}
          }
        }
      }
    },

    # --- 4. Generate Style Test Posts ---
    "generate_style_posts": {
      "node_id": "generate_style_posts",
      "node_name": "llm",
      "node_config": {
        "llm_config": {
          "model_spec": {
            "provider": f"{llm_provider}",
            "model": f"{generation_model_name}"
          },
          "temperature": temperature,
          "max_tokens": max_tokens,
        },
        "output_schema": {
          "schema_definition": STYLE_TEST_LLM_OUTPUT_SCHEMA,
          "convert_loaded_schema_to_pydantic": False
        }
      }
    },

    # --- 5. Collect Style Feedback ---
    "collect_style_feedback": {
      "node_id": "collect_style_feedback",
      "node_name": "hitl_node__default",
      "enable_node_fan_in": True,
      "node_config": {},
      "dynamic_output_schema": {
          "fields": {
              "feedback_post_a": {
                  "type": "str",
                  "required": False,
                  "description": "Detailed feedback specifically for Post A - what works, what doesn't, tone, style, etc."
              },
              "rating_post_a": {
                  "type": "int",
                  "required": True,
                  "description": "Rating for Post A on scale of 1-5 (1=poor, 5=excellent)"
              },
              "feedback_post_b": {
                  "type": "str",
                  "required": False,
                  "description": "Detailed feedback specifically for Post B - what works, what doesn't, tone, style, etc."
              },
              "rating_post_b": {
                  "type": "int",
                  "required": True,
                  "description": "Rating for Post B on scale of 1-5 (1=poor, 5=excellent)"
              }
          }
      }
    },

    # --- 6. Construct DNA Update Prompt ---
    "construct_dna_update_prompt": {
      "node_id": "construct_dna_update_prompt",
      "node_name": "prompt_constructor",
      "enable_node_fan_in": True,
      "node_config": {
        "prompt_templates": {
          "dna_update_prompt": {
            "id": "dna_update_prompt",
            "template": DNA_UPDATE_INTERPRETATION_PROMPT,
            "variables": {
              "current_user_dna": None,
              "post_a_text": None,
              "post_b_text": None,
              "feedback_post_a": None,
              "rating_post_a": None,
              "feedback_post_b": None,
              "rating_post_b": None,
            },
            "construct_options": {
              "current_user_dna": "user_dna",
              "post_a_text": "style_test_posts.post_a.post_text",
              "post_b_text": "style_test_posts.post_b.post_text",
              "feedback_post_a": "feedback_post_a",
              "rating_post_a": "rating_post_a",
              "feedback_post_b": "feedback_post_b",
              "rating_post_b": "rating_post_b",
            }
          }
        }
      }
    },

    # --- 7. Interpret Feedback for DNA Updates ---
    "interpret_feedback_for_dna_updates": {
      "node_id": "interpret_feedback_for_dna_updates",
      "node_name": "llm",
      "node_config": {
        "llm_config": {
          "model_spec": {
            "provider": f"{llm_provider}",
            "model": f"{generation_model_name}"
          },
          "temperature": 0.3,  # Lower temperature for more consistent analysis
          "max_tokens": 2000,
        }
      }
    },

    # --- 8. Construct DNA Update Execution Prompt ---
    "construct_dna_update_execution_prompt": {
      "node_id": "construct_dna_update_execution_prompt",
      "node_name": "prompt_constructor",
      "enable_node_fan_in": True,
      "node_config": {
        "prompt_templates": {
          "dna_update_execution_prompt": {
            "id": "dna_update_execution_prompt",
            "template": DNA_UPDATE_EXECUTION_PROMPT,
            "variables": {
              "current_user_dna": None,
              "update_analysis": None,
            },
            "construct_options": {
              "current_user_dna": "user_dna",
              "update_analysis": "content",
            }
          }
        }
      }
    },

    # --- 9. Update User DNA Document ---
    "update_user_dna_document": {
      "node_id": "update_user_dna_document",
      "node_name": "llm",
      "node_config": {
        "llm_config": {
          "model_spec": {
            "provider": f"{llm_provider}",
            "model": f"{generation_model_name}"
          },
          "temperature": 0.1,  # Very low temperature for precise schema following
          "max_tokens": 3000,
        },
        "output_schema": {
          "schema_definition": GENERATION_SCHEMA,
          "convert_loaded_schema_to_pydantic": False
        }
      }
    },

    # --- 10. Save Updated User DNA ---
    "save_updated_user_dna": {
      "node_id": "save_updated_user_dna", 
      "node_name": "store_customer_data",
      "node_config": {
        "global_versioning": {
          "is_versioned": USER_DNA_IS_VERSIONED,
          "operation": "upsert_versioned",
          "version": "default"
        },
        "global_is_shared": False,
        "global_is_system_entity": False,
        "store_configs": [
          {
            "input_field_path": "updated_user_dna",
            "target_path": {
              "filename_config": {
                "input_namespace_field_pattern": USER_DNA_NAMESPACE_TEMPLATE,
                "input_namespace_field": "entity_username",
                "static_docname": USER_DNA_DOCNAME
              }
            }
          }
        ]
      }
    },

    # --- 11. Output Node ---
    "output_node": {
      "node_id": "output_node",
      "node_name": "output_node",
      "node_config": {}
    }
  },

  # --- Edges Defining Data Flow ---
  "edges": [

    { 
      "src_node_id": "input_node", 
      "dst_node_id": "$graph_state", 
      "mappings": [
        { "src_field": "entity_username", "dst_field": "entity_username"},
        { "src_field": "customer_context_doc_configs", "dst_field": "customer_context_doc_configs"},
      ]
    },

    # Input → Load Context Documents
    { 
      "src_node_id": "input_node", 
      "dst_node_id": "load_all_context_docs",
      "mappings": [
        { "src_field": "customer_context_doc_configs", "dst_field": "customer_context_doc_configs"},
        { "src_field": "entity_username", "dst_field": "entity_username"},
      ]
    },

    # Load Context Documents → Global State
    { 
      "src_node_id": "load_all_context_docs", 
      "dst_node_id": "$graph_state", 
      "mappings": [
        { "src_field": "user_dna", "dst_field": "user_dna"},
        { "src_field": "content_strategy", "dst_field": "content_strategy"},
      ]
    },

    # Load Context Documents → Style Test Prompt Construction (ensure sequencing)
    { 
      "src_node_id": "load_all_context_docs", 
      "dst_node_id": "construct_style_test_prompt", 
      "mappings": []
    },

    # Global State → Prompt Construction (user context)
    { 
      "src_node_id": "$graph_state", 
      "dst_node_id": "construct_style_test_prompt", 
      "mappings": [
        { "src_field": "user_dna", "dst_field": "user_dna"},
        { "src_field": "content_strategy", "dst_field": "content_strategy"},
      ]
    },

    # Prompt Construction → Style Post Generation
    { 
      "src_node_id": "construct_style_test_prompt", 
      "dst_node_id": "generate_style_posts", 
      "mappings": [
        { "src_field": "style_generation_prompt", "dst_field": "user_prompt"},
        { "src_field": "system_prompt", "dst_field": "system_prompt"}
      ]
    },

    # Style Generation → Global State (store generated posts)
    { 
      "src_node_id": "generate_style_posts", 
      "dst_node_id": "$graph_state", 
      "mappings": [
        { "src_field": "structured_output", "dst_field": "style_test_posts"},
      ]
    },

    # Global State → Feedback Collection (provide generated posts for review)
    { 
      "src_node_id": "generate_style_posts", 
      "dst_node_id": "collect_style_feedback", 
      "mappings": []
    },

    { 
      "src_node_id": "$graph_state", 
      "dst_node_id": "collect_style_feedback", 
      "mappings": [
        { "src_field": "style_test_posts", "dst_field": "style_test_posts"}
      ]
    },
    # Feedback Collection → Global State (store feedback data)
    { 
      "src_node_id": "collect_style_feedback", 
      "dst_node_id": "$graph_state", 
      "mappings": [
        { "src_field": "feedback_post_a", "dst_field": "feedback_post_a"},
        { "src_field": "rating_post_a", "dst_field": "rating_post_a"},
        { "src_field": "feedback_post_b", "dst_field": "feedback_post_b"},
        { "src_field": "rating_post_b", "dst_field": "rating_post_b"},
      ]
    },

    { 
      "src_node_id": "collect_style_feedback", 
      "dst_node_id": "construct_dna_update_prompt", 
      "mappings": []
    },

    # Global State → DNA Update Prompt Construction (all required data)
    { 
      "src_node_id": "$graph_state", 
      "dst_node_id": "construct_dna_update_prompt", 
      "mappings": [
        { "src_field": "user_dna", "dst_field": "user_dna"},
        { "src_field": "style_test_posts", "dst_field": "style_test_posts"},
        { "src_field": "feedback_post_a", "dst_field": "feedback_post_a"},
        { "src_field": "rating_post_a", "dst_field": "rating_post_a"},
        { "src_field": "feedback_post_b", "dst_field": "feedback_post_b"},
        { "src_field": "rating_post_b", "dst_field": "rating_post_b"},
      ]
    },

    # DNA Update Prompt → Feedback Interpretation
    { 
      "src_node_id": "construct_dna_update_prompt", 
      "dst_node_id": "interpret_feedback_for_dna_updates", 
      "mappings": [
        { "src_field": "dna_update_prompt", "dst_field": "user_prompt"}
      ]
    },

    # Feedback Interpretation → DNA Update Execution Prompt Construction (ensure sequencing)
    { 
      "src_node_id": "interpret_feedback_for_dna_updates", 
      "dst_node_id": "construct_dna_update_execution_prompt", 
      "mappings": [
        { "src_field": "content", "dst_field": "content"}
      ]
    },

    # Feedback Interpretation → Global State (capture analysis)
    { 
      "src_node_id": "interpret_feedback_for_dna_updates", 
      "dst_node_id": "$graph_state", 
      "mappings": [
        { "src_field": "content", "dst_field": "dna_update_analysis"}
      ]
    },

    # Global State → DNA Update Execution Prompt (current DNA)
    { 
      "src_node_id": "$graph_state", 
      "dst_node_id": "construct_dna_update_execution_prompt", 
      "mappings": [
        { "src_field": "user_dna", "dst_field": "user_dna"}
      ]
    },

    # DNA Update Execution Prompt → DNA Document Update
    { 
      "src_node_id": "construct_dna_update_execution_prompt", 
      "dst_node_id": "update_user_dna_document", 
      "mappings": [
        { "src_field": "dna_update_execution_prompt", "dst_field": "user_prompt"}
      ]
    },

    # DNA Document Update → Save Updated DNA
    { 
      "src_node_id": "update_user_dna_document", 
      "dst_node_id": "save_updated_user_dna", 
      "mappings": [
        { "src_field": "structured_output", "dst_field": "updated_user_dna"}
      ]
    },

    # Global State → Save Updated DNA (entity username for save location)
    { 
      "src_node_id": "$graph_state", 
      "dst_node_id": "save_updated_user_dna", 
      "mappings": [
        { "src_field": "entity_username", "dst_field": "entity_username"}
      ]
    },

    # Save Updated DNA → Global State (capture save result)
    { 
      "src_node_id": "save_updated_user_dna", 
      "dst_node_id": "$graph_state", 
      "mappings": [
        { "src_field": "passthrough_data", "dst_field": "dna_save_result"}
      ]
    },

    # Save Updated DNA → Output Node (trigger final output)
    { 
      "src_node_id": "save_updated_user_dna", 
      "dst_node_id": "output_node", 
      "mappings": []
    },

    # ═══════════════════════════════════════════════════════════════
    # PHASE 6: FINAL OUTPUT ASSEMBLY
    # ═══════════════════════════════════════════════════════════════
    
    # Global State → Final Output (all data from graph state)
    { 
      "src_node_id": "$graph_state", 
      "dst_node_id": "output_node", 
      "mappings": [
        { "src_field": "style_test_posts", "dst_field": "style_test_posts"},
        { "src_field": "dna_save_result", "dst_field": "dna_save_result"}
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
      }
      }
  }
}


# --- Test Execution Logic ---
import asyncio
import logging
from typing import Dict, Any, Optional, List

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus


async def validate_style_test_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """
    Custom validation function for the style test workflow outputs.
    Validates core requirements for the final workflow outputs.
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating style test workflow outputs...")

    # Check for expected keys - style test posts
    assert 'style_test_posts' in outputs, "Validation Failed: 'style_test_posts' key missing."

    # Validate post structure
    posts = outputs.get('style_test_posts')
    assert 'post_a' in posts, "Validation Failed: 'post_a' missing in generated posts."
    assert 'post_b' in posts, "Validation Failed: 'post_b' missing in generated posts."
    
    # Validate each post has required fields
    for post_key in ['post_a', 'post_b']:
        post = posts[post_key]
        assert 'post_text' in post, f"Validation Failed: 'post_text' missing in {post_key}."
        assert 'hashtags' in post, f"Validation Failed: 'hashtags' missing in {post_key}."
        assert isinstance(post['hashtags'], list), f"Validation Failed: hashtags should be a list in {post_key}."

    # Check for DNA save result (indicates workflow completed successfully)
    if 'dna_save_result' in outputs:
        logger.info("✓ DNA save result found - workflow completed successfully")

    logger.info("✓ Style test output validation passed.")
    return True


async def main_test_style_workflow():
    """
    Tests the Style Test Workflow using the run_workflow_test helper function.
    
    This workflow generates two different style variants of posts based on user DNA
    and content strategy, then collects real user feedback to update the DNA document.
    The workflow requires interactive human input for style feedback and ratings.
    """
    test_name = "Style Test Workflow"
    print(f"--- Starting {test_name} ---")

    # Define test parameters
    test_entity_username = "example-user"
    
    # Define document namespaces
    user_dna_namespace = USER_DNA_NAMESPACE_TEMPLATE.format(item=test_entity_username)
    content_strategy_namespace = CONTENT_STRATEGY_NAMESPACE_TEMPLATE.format(item=test_entity_username)

    # Define test context document configurations
    test_context_docs = [
        {
            "filename_config": {
                "input_namespace_field_pattern": USER_DNA_NAMESPACE_TEMPLATE, 
                "input_namespace_field": "entity_username",
                "static_docname": USER_DNA_DOCNAME,
            },
            "output_field_name": "user_dna"
        },
        {
            "filename_config": {
                "input_namespace_field_pattern": CONTENT_STRATEGY_NAMESPACE_TEMPLATE, 
                "input_namespace_field": "entity_username",
                "static_docname": CONTENT_STRATEGY_DOCNAME,
            },
            "output_field_name": "content_strategy"
        }
    ]

    # Define workflow input parameters
    STYLE_TEST_WORKFLOW_INPUTS = {
        "customer_context_doc_configs": test_context_docs,
        "entity_username": test_entity_username,
    }

    # Define setup documents
    setup_docs: List[SetupDocInfo] = [
        # User DNA Document
        {
            'namespace': user_dna_namespace,
            'docname': USER_DNA_DOCNAME,
            'initial_data': {
                "professional_identity": {
                    "full_name": "Example User",
                    "job_title": "Senior Growth Marketing Manager",
                    "industry_sector": "SaaS Technology and Marketing",
                    "company_name": "TechFlow Solutions",
                    "company_size": "Mid-market (200-500 employees)",
                    "years_of_experience": 8,
                    "professional_certifications": ["Google Analytics Certified", "HubSpot Inbound Marketing", "Facebook Blueprint Certified"],
                    "areas_of_expertise": [
                        "Performance marketing and paid acquisition",
                        "Marketing analytics and attribution modeling",
                        "Growth experimentation and A/B testing",
                        "Customer lifecycle marketing and retention",
                        "Marketing automation and lead nurturing",
                        "Content marketing strategy and SEO",
                        "Conversion rate optimization (CRO)",
                        "Multi-channel campaign management",
                        "Data-driven decision making and KPI frameworks",
                        "Marketing technology stack optimization"
                    ],
                    "career_milestones": [
                        "Led 300% growth in qualified leads at current company (2022-2024)",
                        "Reduced customer acquisition cost by 40% through optimization (2023)",
                        "Built and scaled growth team from 2 to 8 members (2021-2023)",
                        "Launched successful product marketing campaigns generating $2M+ ARR",
                        "Implemented marketing attribution system improving ROI visibility by 60%",
                        "Recognized as 'Marketing Professional of the Year' at TechFlow (2023)"
                    ],
                    "professional_bio": "Example User is a Senior Growth Marketing Manager at TechFlow Solutions, where he leads performance marketing initiatives and growth experimentation. With 8 years of experience in SaaS marketing, he specializes in data-driven growth strategies, marketing analytics, and building scalable acquisition channels. His expertise spans the full marketing funnel from awareness to retention, with a particular focus on optimizing customer acquisition costs and improving marketing attribution."
                },
                "linkedin_profile_analysis": {
                    "follower_count": 3200,
                    "connection_count": 2800,
                    "profile_headline_analysis": "Senior Growth Marketing Manager | SaaS Growth Expert | Data-Driven Marketing Strategist",
                    "about_section_summary": "Passionate about leveraging data and technology to drive sustainable business growth. Experienced in building and optimizing marketing funnels, implementing growth experiments, and creating scalable acquisition strategies for B2B SaaS companies.",
                    "engagement_metrics": {
                        "average_likes_per_post": 120,
                        "average_comments_per_post": 25,
                        "average_shares_per_post": 8
                    },
                    "top_performing_content_pillars": [
                        "Growth Marketing Strategies",
                        "Marketing Analytics & Data",
                        "Career Development in Marketing",
                        "SaaS Industry Insights"
                    ],
                    "content_posting_frequency": "3-4 times per week with focus on Tuesday and Thursday for maximum engagement",
                    "content_types_used": [
                        "Data-driven insights with charts and metrics",
                        "Personal career stories and lessons learned",
                        "Industry trend analysis and predictions",
                        "Marketing tool reviews and comparisons",
                        "Growth experiment case studies",
                        "Thread-style educational content",
                        "Behind-the-scenes team and culture posts"
                    ],
                    "network_composition": [
                        "70% marketing professionals and growth experts",
                        "15% SaaS founders and executives",
                        "10% data analysts and marketing technologists",
                        "5% content creators and industry influencers",
                        "Geographic spread: 60% North America, 30% Europe, 10% Asia-Pacific"
                    ]
                },
                "brand_voice_and_style": {
                    "communication_style": "Data-driven storyteller with authentic vulnerability",
                    "tone_preferences": [
                        "Analytical yet accessible",
                        "Confident but humble about learnings",
                        "Enthusiastic about growth discoveries",
                        "Honest about failures and lessons",
                        "Supportive of other marketers' journey",
                        "Curious and always learning"
                    ],
                    "vocabulary_level": "Professional with marketing-specific terminology explained for broader audience; uses data points and metrics frequently; balances technical depth with accessibility",
                    "sentence_structure_preferences": "Mix of short punchy statements for key insights and longer explanatory paragraphs for complex concepts; uses numbered lists for frameworks; questions to engage audience at post end",
                    "content_format_preferences": [
                        "Data visualizations and chart screenshots",
                        "Before/after comparison formats",
                        "Step-by-step process breakdowns",
                        "Numbered lists for actionable insights",
                        "Personal story + professional lesson structure",
                        "Myth-busting format (❌ vs ✅)",
                        "Framework and template sharing"
                    ],
                    "emoji_usage": "Strategic and moderate use; primarily 📊📈 for data posts, 🧵 for threads, ✅❌ for comparisons, 💡 for insights; typically 3-6 emojis per post",
                    "hashtag_usage": "Consistent use of 5-8 relevant hashtags; mix of broad (#Marketing #Growth) and specific (#MarketingAnalytics #SaaSGrowth) tags; placed at end of posts",
                    "storytelling_approach": "Personal experience as foundation → Data/insights → Actionable takeaway; vulnerable about mistakes and learning process; celebrates team wins over individual achievements"
                },
                "content_strategy_goals": {
                    "primary_goal": "Establish thought leadership in growth marketing and build professional network",
                    "secondary_goals": [
                        "Share knowledge and help other marketers grow",
                        "Build personal brand for future career opportunities",
                        "Generate speaking and consulting opportunities",
                        "Create connections with other growth professionals",
                        "Document learning journey and experiments",
                        "Contribute to marketing community knowledge base"
                    ],
                    "target_audience_demographics": "Marketing professionals (manager to director level), SaaS growth teams, founders of early-stage companies, marketing technology enthusiasts",
                    "ideal_reader_personas": [
                        "Growth marketers looking to level up their skills",
                        "Marketing managers transitioning to senior roles",
                        "SaaS founders needing growth marketing insights",
                        "Data analysts moving into marketing roles",
                        "Marketing leaders building high-performing teams"
                    ],
                    "audience_pain_points": [
                        "Struggling with marketing attribution and measurement",
                        "Difficulty proving marketing ROI to leadership",
                        "Overwhelmed by marketing technology options",
                        "Need for scalable growth strategies",
                        "Challenges in hiring and building marketing teams",
                        "Keeping up with rapidly changing digital marketing landscape",
                        "Balancing experimentation with consistent results",
                        "Understanding which metrics actually matter for growth"
                    ],
                    "value_proposition_to_audience": "Practical, data-backed growth marketing insights from real-world experience; honest sharing of both successes and failures; actionable frameworks and templates; authentic mentorship and career guidance",
                    "call_to_action_preferences": [
                        "Questions that spark meaningful discussions",
                        "Invitations to share similar experiences",
                        "Requests for specific feedback or advice",
                        "Offers to help with marketing challenges",
                        "Sharing of templates or resources"
                    ],
                    "content_pillar_themes": [
                        "Growth experiment results and learnings (30%)",
                        "Marketing analytics and measurement (25%)",
                        "Career development and team building (20%)",
                        "Industry trends and predictions (15%)",
                        "Tool reviews and marketing stack optimization (10%)"
                    ],
                    "topics_of_interest": [
                        "Attribution modeling and multi-touch analytics",
                        "Customer acquisition cost optimization",
                        "Growth experimentation methodologies",
                        "Marketing automation and lifecycle campaigns",
                        "Conversion rate optimization techniques",
                        "Team leadership and hiring best practices",
                        "Marketing technology integration",
                        "SaaS metrics and growth frameworks",
                        "Personal branding for marketers",
                        "Data visualization and reporting"
                    ]
                },
                "personal_context": {
                    "personal_values": [
                        "Continuous learning and skill development",
                        "Data-driven decision making",
                        "Team collaboration and knowledge sharing",
                        "Authenticity and transparency",
                        "Work-life balance and mental health",
                        "Helping others succeed in their careers"
                    ],
                    "professional_mission_statement": "To democratize growth marketing knowledge and help marketing professionals build data-driven, scalable strategies that drive meaningful business impact while fostering inclusive, high-performing teams.",
                    "content_creation_challenges": [
                        "Balancing technical depth with accessibility",
                        "Finding time for consistent content creation",
                        "Sharing proprietary data while maintaining confidentiality",
                        "Staying current with rapidly evolving marketing landscape",
                        "Creating original insights in saturated marketing content space"
                    ],
                    "personal_story_elements_for_content": [
                        "Transition from traditional marketing to growth marketing",
                        "Early career mistakes and expensive lessons learned",
                        "Building marketing team from scratch experiences",
                        "International experience and cultural perspectives",
                        "Side projects and freelance consulting stories",
                        "Mentorship experiences and helping junior marketers"
                    ],
                    "notable_life_experiences": [
                        "Led marketing during company pivot that saved business",
                        "Managed marketing budget through economic downturn",
                        "Built remote marketing team across multiple time zones",
                        "Spoke at major marketing conferences and events",
                        "Mentored 15+ junior marketers in career development"
                    ],
                    "inspirations_and_influences": [
                        "Sean Ellis (Growth Hacking movement)",
                        "Andy Raskin (Positioning and messaging)",
                        "April Dunford (Product positioning)",
                        "Brian Balfour (Reforge methodology)"
                    ],
                    "quotes_they_resonate_with": [
                        "Growth is never by mere chance; it is the result of forces working together",
                        "Data beats opinions",
                        "The best marketing doesn't feel like marketing"
                    ]
                },
                "analytics_insights": {
                    "optimal_content_length": "Data-heavy posts perform best at 150-200 words; story-driven content performs well at 250-300 words; thread format for educational content 8-12 posts",
                    "audience_geographic_distribution": "North America 60%, Europe 30%, Asia-Pacific 8%, Other 2%",
                    "engagement_time_patterns": "Peak engagement Tuesday-Thursday 9-11 AM EST and 2-4 PM EST; lower engagement on Mondays and Fridays",
                    "keyword_performance_analysis": "High-performing keywords: growth marketing, marketing analytics, SaaS growth, customer acquisition, marketing attribution, growth experiments, marketing ROI",
                    "competitor_benchmarking": "Outperforming similar profiles in engagement rate (4.2% vs industry 2.8%); strong performance in saves and shares indicating educational value",
                    "growth_rate_metrics": "25% follower growth year-over-year; 40% increase in post engagement; 3x increase in inbound opportunities"
                },
                "success_metrics": {
                    "content_performance_kpis": [
                        "Engagement rate (target: >4%)",
                        "Share-to-like ratio (target: >0.1)",
                        "Comment quality and length",
                        "Profile visits from posts",
                        "Connection requests from content"
                    ],
                    "engagement_quality_metrics": [
                        "Meaningful conversations in comments",
                        "Questions and follow-up discussions",
                        "Requests for advice or consultation",
                        "Shares with personal commentary"
                    ],
                    "conversion_goals": [
                        "Speaking opportunities at conferences",
                        "Consulting and advisory requests",
                        "Job opportunities and career advancement",
                        "Collaboration proposals from other marketers",
                        "Invitations to podcasts and interviews"
                    ],
                    "brand_perception_goals": [
                        "Recognized as data-driven growth marketing expert",
                        "Seen as approachable mentor and teacher",
                        "Known for practical, actionable insights",
                        "Viewed as authentic and transparent leader",
                        "Associated with marketing analytics excellence"
                    ],
                    "timeline_for_expected_results": "6-12 months for thought leadership establishment; 3-6 months for engagement improvement",
                    "benchmarking_standards": "Compare against top 10% of growth marketing professionals; track monthly against previous performance"
                }
            },
            'is_shared': False,
            'is_versioned': USER_DNA_IS_VERSIONED,
            'initial_version': "default",
            'is_system_entity': False
        },
        
        # Content Strategy Document
        {
            'namespace': content_strategy_namespace,
            'docname': CONTENT_STRATEGY_DOCNAME,
            'initial_data': {
                "content_pillars": [
                    {
                        "name": "Growth Marketing Strategies & Experiments",
                        "description": "Sharing results from growth experiments, optimization strategies, and scalable acquisition tactics",
                        "target_percentage": 30,
                        "example_topics": [
                            "A/B testing methodologies and results",
                            "Customer acquisition channel analysis",
                            "Conversion rate optimization case studies",
                            "Growth experiment frameworks and processes"
                        ]
                    },
                    {
                        "name": "Marketing Analytics & Data Insights", 
                        "description": "Deep dives into marketing measurement, attribution modeling, and data-driven decision making",
                        "target_percentage": 25,
                        "example_topics": [
                            "Marketing attribution model comparisons",
                            "KPI framework development",
                            "Data visualization techniques",
                            "Analytics tool evaluations"
                        ]
                    },
                    {
                        "name": "Career Development & Team Building",
                        "description": "Insights on growing as a marketing professional and building high-performing marketing teams",
                        "target_percentage": 20,
                        "example_topics": [
                            "Marketing career progression paths",
                            "Hiring and onboarding best practices",
                            "Leadership lessons and team management",
                            "Skill development recommendations"
                        ]
                    },
                    {
                        "name": "SaaS Industry Trends & Predictions",
                        "description": "Analysis of SaaS marketing trends, industry changes, and future predictions",
                        "target_percentage": 15,
                        "example_topics": [
                            "Emerging marketing channels and tactics",
                            "Industry benchmark analysis",
                            "Economic impact on SaaS marketing",
                            "Technology adoption trends"
                        ]
                    },
                    {
                        "name": "Marketing Technology & Tools",
                        "description": "Reviews, comparisons, and optimization strategies for marketing technology stack",
                        "target_percentage": 10,
                        "example_topics": [
                            "Marketing automation platform comparisons",
                            "Tool integration strategies",
                            "ROI analysis of marketing technologies",
                            "Implementation best practices"
                        ]
                    }
                ],
                "posting_frequency": "3-4 times per week (Tuesday, Wednesday, Thursday, and occasional Saturday)",
                "target_audience_details": {
                    "primary": "Growth marketers and marketing managers in B2B SaaS companies",
                    "secondary": "Marketing leaders, SaaS founders, and data-driven marketing professionals",
                    "tertiary": "Marketing students and early-career professionals seeking mentorship",
                    "pain_points": [
                        "Proving marketing ROI and attribution",
                        "Scaling growth while maintaining efficiency",
                        "Keeping up with rapidly changing marketing landscape",
                        "Building and managing high-performing marketing teams",
                        "Optimizing marketing technology investments"
                    ],
                    "goals_and_aspirations": [
                        "Advance to senior marketing leadership roles",
                        "Build data-driven marketing competencies",
                        "Improve marketing measurement and attribution",
                        "Scale their companies' growth effectively",
                        "Stay current with marketing best practices"
                    ]
                },
                "content_objectives": [
                    "Establish thought leadership in growth marketing and analytics",
                    "Share practical, actionable insights from real-world experience",
                    "Build meaningful professional relationships with marketing peers",
                    "Generate speaking, consulting, and career opportunities",
                    "Contribute valuable knowledge to the marketing community",
                    "Create a personal brand that opens doors for future opportunities"
                ],
                "engagement_strategies": {
                    "question_formats": [
                        "What's your experience with [specific marketing challenge]?",
                        "How do you measure [specific marketing metric] at your company?",
                        "What tools do you use for [specific marketing function]?",
                        "Have you tried [specific marketing tactic]? What were your results?"
                    ],
                    "discussion_starters": [
                        "Controversial opinions backed by data",
                        "Common marketing myths to debunk",
                        "Predictions about future of marketing",
                        "Lessons learned from marketing failures"
                    ],
                    "value_add_approaches": [
                        "Share templates and frameworks",
                        "Offer free mini-consultations in comments",
                        "Provide detailed explanations of complex concepts",
                        "Connect people with similar challenges"
                    ]
                }
            },
            'is_versioned': CONTENT_STRATEGY_IS_VERSIONED,
            'is_shared': False,
            'initial_version': "default"
        }
    ]

    # Define cleanup documents
    cleanup_docs: List[CleanupDocInfo] = [
        {
            'namespace': user_dna_namespace,
            'docname': USER_DNA_DOCNAME,
            'is_shared': False,
            'is_versioned': USER_DNA_IS_VERSIONED,
            'is_system_entity': False
        },
        {
            'namespace': content_strategy_namespace,
            'docname': CONTENT_STRATEGY_DOCNAME,
            'is_shared': False,
            'is_versioned': CONTENT_STRATEGY_IS_VERSIONED,
            'is_system_entity': False
        }
    ]

    # Predefined HITL inputs - fixed format to match expected structure
    # The inputs should be the direct dictionary that the HITL node expects,
    # not wrapped in a structure with node_id and inputs
    predefined_hitl_inputs = [
        {
            "feedback_post_a": "Post A is highly engaging and effective. The use of a provocative hook — \"I just killed our best-performing marketing channel\" — immediately grabs attention and encourages readers to continue. The storytelling format with numbered points clearly explains the problem and solution, making it easy to follow. The tone is conversational and authentic, which helps build trust and relatability. The call to action inviting comments to share the incrementality testing framework is well-placed to encourage engagement. The post balances technical detail and accessibility well for a marketing-savvy LinkedIn audience.",
            "rating_post_a": 5,
            "feedback_post_b": "Post B is thoughtful and insightful, with a strong conceptual framing around the paradox of marketing attribution. It appeals to a professional audience by highlighting the complexity and imperfection of attribution models and advocates a balanced approach. The tone is more formal and reflective than Post A, which might reduce immediate emotional engagement but strengthens credibility. The post could benefit from a slightly stronger hook to boost initial attention. The inclusion of a hybrid framework and the invitation to discuss challenges fosters community, but it reads somewhat more abstract and less narrative-driven compared to Post A.",
            "rating_post_b": 4
        }
    ]
    
    # Execute the test
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=STYLE_TEST_WORKFLOW_INPUTS,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=predefined_hitl_inputs,
        setup_docs=setup_docs,
        cleanup_docs=cleanup_docs,
        cleanup_docs_created_by_setup=True,
        validate_output_func=validate_style_test_output,
        stream_intermediate_results=True,
        poll_interval_sec=5,  # Increased from 3 to 5 seconds
        timeout_sec=600  # Increased from 300 to 600 seconds for longer workflows
    )

    print(f"\n--- {test_name} Finished ---")
    
    # Display results
    if final_run_outputs and 'style_test_posts' in final_run_outputs:
        posts = final_run_outputs['style_test_posts']
        
        print("\n" + "="*60)
        print("GENERATED STYLE TEST POSTS")
        print("="*60)
        
        print("-" * 50)
        print("POST A:")
        print("-" * 50)
        print(posts['post_a']['post_text'])
        print(f"\nHashtags: {', '.join(posts['post_a']['hashtags'])}")
        
        print("-" * 50)
        print("POST B:")
        print("-" * 50)
        print(posts['post_b']['post_text'])
        print(f"\nHashtags: {', '.join(posts['post_b']['hashtags'])}")
        
        # Check if DNA was successfully updated
        if final_run_outputs.get('dna_save_result'):
            print(f"\n✅ User DNA updated successfully based on style feedback!")
        
        print("="*60)


# Standard Python entry point
if __name__ == "__main__":
    print("="*50)
    print("Executing Style Test Workflow")
    print("="*50)
    print("NOTE: This workflow requires interactive user input for style feedback.")
    print("The workflow will pause and wait for your feedback on the generated posts.")
    print("="*50)
    try:
        asyncio.run(main_test_style_workflow())
    except KeyboardInterrupt:
        print("\nExecution interrupted by user.")
    except Exception as main_err:
        print(f"\nCritical error during script execution: {main_err}")
        logger.exception("Critical error running main")

    print("\nScript execution finished.")
    print(f"Run this script from the project root directory using:")
    print(f"PYTHONPATH=. python kiwi_client/workflows/wf_style_test.py") 