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

from kiwi_client.workflows.document_models.customer_docs import (
    # User Preferences
    USER_PREFERENCES_DOCNAME,
    USER_PREFERENCES_NAMESPACE_TEMPLATE,
    USER_PREFERENCES_IS_VERSIONED,
    
    # LinkedIn Profile
    LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE,
    LINKEDIN_PROFILE_DOCNAME,
    
    # Content Analysis Document
    CONTENT_ANALYSIS_DOCNAME,
    CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
    
    # Target Audience Framework (from previous onboarding)
    # Note: This would be a temporary document from the first onboarding workflow
    # For now, we'll assume it's stored in user_inputs namespace
)

from kiwi_client.workflows.llm_inputs.core_beliefs_perspectives_extraction import (
    CORE_BELIEFS_QUESTIONS_SCHEMA,
    PERSONALIZED_QUESTIONS_SCHEMA,
    CONTENT_INTELLIGENCE_SCHEMA,
    
    ANALYSIS_AND_QUESTIONS_SYSTEM_PROMPT,
    ANALYSIS_AND_QUESTIONS_USER_PROMPT,
    
    PERSONALIZATION_SYSTEM_PROMPT,
    PERSONALIZATION_USER_PROMPT,
    
    CONTENT_INTELLIGENCE_SYSTEM_PROMPT,
    CONTENT_INTELLIGENCE_USER_PROMPT,
)

# --- Workflow Configuration Constants ---

# LLM Configuration
LLM_PROVIDER = "openai"
GENERATION_MODEL = "gpt-4.1"
LLM_TEMPERATURE = 0.9  # Higher temperature for creative question generation
LLM_MAX_TOKENS = 2500

# --- Prompt Template Variables and Options ---

# Analysis and Questions Generation Node
ANALYSIS_AND_QUESTIONS_SYSTEM_PROMPT_VARIABLES = {
    "questions_schema": CORE_BELIEFS_QUESTIONS_SCHEMA
}

ANALYSIS_AND_QUESTIONS_USER_PROMPT_VARIABLES = {
    "content_analysis": None,
    "user_preferences": None,
    "profile_insights": None
}

ANALYSIS_AND_QUESTIONS_USER_PROMPT_CONSTRUCT_OPTIONS = {
    "content_analysis": "content_analysis",
    "user_preferences": "onboarding_responses",
    "profile_insights": "profile_insights"
}

# Personalization Node
PERSONALIZATION_SYSTEM_PROMPT_VARIABLES = {
    "personalized_schema": PERSONALIZED_QUESTIONS_SCHEMA
}

PERSONALIZATION_USER_PROMPT_VARIABLES = {
    "generated_questions": None,
    "content_analysis": None,
    "user_preferences": None,
    "profile_insights": None
}

PERSONALIZATION_USER_PROMPT_CONSTRUCT_OPTIONS = {
    "generated_questions": "core_beliefs_questions",
    "content_analysis": "content_analysis",
    "user_preferences": "onboarding_responses",
    "profile_insights": "profile_insights",
}

# Content Intelligence Node
CONTENT_INTELLIGENCE_SYSTEM_PROMPT_VARIABLES = {
    "content_intelligence_schema": CONTENT_INTELLIGENCE_SCHEMA
}

CONTENT_INTELLIGENCE_USER_PROMPT_VARIABLES = {
    "content_analysis": None
}

CONTENT_INTELLIGENCE_USER_PROMPT_CONSTRUCT_OPTIONS = {
    "content_analysis": "content_analysis"
}

# --- Edge Configurations ---

field_mappings_from_input_to_state = [
    {"src_field": "customer_context_doc_configs", "dst_field": "customer_context_doc_configs"},
    {"src_field": "entity_username", "dst_field": "entity_username"},
]

field_mappings_from_load_docs_to_state = [
    {"src_field": "content_analysis", "dst_field": "content_analysis"},
    {"src_field": "onboarding_responses", "dst_field": "onboarding_responses"},
    {"src_field": "profile_insights", "dst_field": "profile_insights"},
]

field_mappings_from_state_to_analysis_and_questions = [
    {"src_field": "content_analysis", "dst_field": "content_analysis"},
    {"src_field": "onboarding_responses", "dst_field": "onboarding_responses"},
    {"src_field": "profile_insights", "dst_field": "profile_insights"},
]

field_mappings_from_state_to_personalization = [
    {"src_field": "core_beliefs_questions", "dst_field": "core_beliefs_questions"},
    {"src_field": "content_analysis", "dst_field": "content_analysis"},
    {"src_field": "onboarding_responses", "dst_field": "onboarding_responses"},
    {"src_field": "profile_insights", "dst_field": "profile_insights"},
]

field_mappings_from_state_to_content_intelligence = [
    {"src_field": "content_analysis", "dst_field": "content_analysis"},
]

# --- Input Fields ---

INPUT_FIELDS = {
    "customer_context_doc_configs": {
        "type": "list",
        "required": True,
        "description": "List of document identifiers (namespace/docname pairs) for customer context including content analysis."
    },
    "entity_username": {
        "type": "str",
        "required": True,
        "description": "Username/identifier for the entity"
    },
}

# --- Workflow Graph Schema ---

workflow_graph_schema = {
    "nodes": {
        # --- 1. Input Node ---
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": INPUT_FIELDS
            }
        },

        # --- 2. Load Customer Context Documents ---
        "load_customer_context_docs": {
            "node_id": "load_customer_context_docs",
            "node_name": "load_customer_data",
            "node_config": {
                "load_configs_input_path": "customer_context_doc_configs",
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False},
            },
        },

        # --- 3. Construct Analysis and Questions Prompt ---
        "construct_analysis_and_questions_prompt": {
            "node_id": "construct_analysis_and_questions_prompt",
            "node_name": "prompt_constructor",
            "enable_node_fan_in": True,
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": ANALYSIS_AND_QUESTIONS_USER_PROMPT,
                        "variables": ANALYSIS_AND_QUESTIONS_USER_PROMPT_VARIABLES,
                        "construct_options": ANALYSIS_AND_QUESTIONS_USER_PROMPT_CONSTRUCT_OPTIONS
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": ANALYSIS_AND_QUESTIONS_SYSTEM_PROMPT,
                        "variables": ANALYSIS_AND_QUESTIONS_SYSTEM_PROMPT_VARIABLES,
                        "construct_options": {}
                    }
                }
            }
        },

        # --- 4. Generate Core Beliefs Questions ---
        "generate_core_beliefs_questions": {
            "node_id": "generate_core_beliefs_questions",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": GENERATION_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS
                },
                "output_schema": {
                    "schema_definition": CORE_BELIEFS_QUESTIONS_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                },
            }
        },

        # --- 5. Construct Personalization Prompt ---
        "construct_personalization_prompt": {
            "node_id": "construct_personalization_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": PERSONALIZATION_USER_PROMPT,
                        "variables": PERSONALIZATION_USER_PROMPT_VARIABLES,
                        "construct_options": PERSONALIZATION_USER_PROMPT_CONSTRUCT_OPTIONS
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": PERSONALIZATION_SYSTEM_PROMPT,
                        "variables": PERSONALIZATION_SYSTEM_PROMPT_VARIABLES,
                        "construct_options": {}
                    }
                }
            }
        },

        # --- 6. Personalize Questions (Final Output) ---
        "personalize_questions": {
            "node_id": "personalize_questions",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": GENERATION_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS
                },
                "output_schema": {
                    "schema_definition": PERSONALIZED_QUESTIONS_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                },
            }
        },

        # --- 7. Construct Content Intelligence Prompt ---
        "construct_content_intelligence_prompt": {
            "node_id": "construct_content_intelligence_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "user_prompt": {
                        "id": "user_prompt",
                        "template": CONTENT_INTELLIGENCE_USER_PROMPT,
                        "variables": CONTENT_INTELLIGENCE_USER_PROMPT_VARIABLES,
                        "construct_options": CONTENT_INTELLIGENCE_USER_PROMPT_CONSTRUCT_OPTIONS
                    },
                    "system_prompt": {
                        "id": "system_prompt",
                        "template": CONTENT_INTELLIGENCE_SYSTEM_PROMPT,
                        "variables": CONTENT_INTELLIGENCE_SYSTEM_PROMPT_VARIABLES,
                        "construct_options": {}
                    }
                }
            }
        },

        # --- 8. Generate Content Intelligence ---
        "generate_content_intelligence": {
            "node_id": "generate_content_intelligence",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {"provider": LLM_PROVIDER, "model": GENERATION_MODEL},
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS
                },
                "output_schema": {
                    "schema_definition": CONTENT_INTELLIGENCE_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                },
            }
        },

        # --- 9. Output Node ---
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {},
        },
    },

    # --- Edges Defining Data Flow ---
    "edges": [
        # --- Initial Setup ---
        # Input -> State: Store initial inputs globally
        {
            "src_node_id": "input_node",
            "dst_node_id": "$graph_state",
            "mappings": field_mappings_from_input_to_state
        },

        # --- Load Documents Flow ---
        # Input -> Load Customer Context Documents
        {
            "src_node_id": "input_node",
            "dst_node_id": "load_customer_context_docs",
            "mappings": [
                {"src_field": "customer_context_doc_configs", "dst_field": "customer_context_doc_configs"},
                {"src_field": "entity_username", "dst_field": "entity_username"}
            ]
        },

        # Load Documents -> State: Store loaded documents
        {
            "src_node_id": "load_customer_context_docs",
            "dst_node_id": "$graph_state",
            "mappings": field_mappings_from_load_docs_to_state
        },

        # --- Belief Analysis Flow ---
        # Load Documents -> Belief Analysis Prompt
        {
            "src_node_id": "load_customer_context_docs",
            "dst_node_id": "construct_analysis_and_questions_prompt"
        },

        # State -> Belief Analysis Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_analysis_and_questions_prompt",
            "mappings": field_mappings_from_state_to_analysis_and_questions
        },

        # Belief Analysis Prompt -> LLM
        {
            "src_node_id": "construct_analysis_and_questions_prompt",
            "dst_node_id": "generate_core_beliefs_questions",
            "mappings": [
                {"src_field": "user_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ],
            "description": "Send prompts to LLM for belief analysis"
        },

        # State -> Generate Core Beliefs Questions (for messages_history)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "generate_core_beliefs_questions",
            "mappings": [
                {"src_field": "messages_history", "dst_field": "messages_history"}
            ]
        },

        # Questions Generation -> State
        {
            "src_node_id": "generate_core_beliefs_questions",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "core_beliefs_questions"}
            ]
        },

        # --- Personalization Flow ---
        # Belief Analysis -> Personalization Prompt
        {
            "src_node_id": "generate_core_beliefs_questions",
            "dst_node_id": "construct_personalization_prompt"
        },

        # State -> Personalization Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_personalization_prompt",
            "mappings": field_mappings_from_state_to_personalization
        },

        # Personalization Prompt -> LLM
        {
            "src_node_id": "construct_personalization_prompt",
            "dst_node_id": "personalize_questions",
            "mappings": [
                {"src_field": "user_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ],
            "description": "Send prompts to LLM for personalization"
        },

        # State -> Personalize Questions (for messages_history)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "personalize_questions",
            "mappings": [
                {"src_field": "messages_history", "dst_field": "messages_history"}
            ]
        },

        # Personalization -> State
        {
            "src_node_id": "personalize_questions",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "personalized_questions"}
            ]
        },

        # --- Content Intelligence Flow ---
        # Personalization -> Content Intelligence Prompt
        {
            "src_node_id": "personalize_questions",
            "dst_node_id": "construct_content_intelligence_prompt"
        },

        # State -> Content Intelligence Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_content_intelligence_prompt",
            "mappings": field_mappings_from_state_to_content_intelligence
        },

        # Content Intelligence Prompt -> LLM
        {
            "src_node_id": "construct_content_intelligence_prompt",
            "dst_node_id": "generate_content_intelligence",
            "mappings": [
                {"src_field": "user_prompt", "dst_field": "user_prompt"},
                {"src_field": "system_prompt", "dst_field": "system_prompt"}
            ],
            "description": "Send prompts to LLM for content intelligence"
        },

        # Content Intelligence -> State
        {
            "src_node_id": "generate_content_intelligence",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "content_intelligence"}
            ]
        },

        # --- Final Output ---
        # Personalization -> Output
        {
            "src_node_id": "personalize_questions",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "personalized_questions"}
            ]
        },

        # Content Intelligence -> Output
        {
            "src_node_id": "generate_content_intelligence",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "content_intelligence"}
            ]
        },

        # State -> Output (for additional context)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "core_beliefs_questions", "dst_field": "core_beliefs_questions"},
                {"src_field": "content_intelligence", "dst_field": "content_intelligence"}
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
                # No special reducers needed for this workflow
            }
        }
    }
}


# --- Test Execution Logic ---
async def main_test_core_beliefs_perspectives_extraction():
    """
    Test for Core Beliefs and Perspectives Extraction Workflow.
    """
    test_name = "Core Beliefs and Perspectives Extraction Workflow Test"
    print(f"--- Starting  ---")

    # Example test inputs
    test_inputs = {
        "customer_context_doc_configs": [
            {
                "filename_config": {
                    "input_namespace_field_pattern": CONTENT_ANALYSIS_NAMESPACE_TEMPLATE,
                    "input_namespace_field": "entity_username",
                    "static_docname": CONTENT_ANALYSIS_DOCNAME,
                },
                "output_field_name": "content_analysis",
            },
            {
                "filename_config": {
                    "input_namespace_field_pattern": USER_PREFERENCES_NAMESPACE_TEMPLATE,
                    "input_namespace_field": "entity_username",
                    "static_docname": USER_PREFERENCES_DOCNAME,
                },
                "output_field_name": "onboarding_responses",
            },
            {
                "filename_config": {
                    "input_namespace_field_pattern": LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE,
                    "input_namespace_field": "entity_username",
                    "static_docname": LINKEDIN_PROFILE_DOCNAME,
                },
                "output_field_name": "profile_insights",
            },
            # Target audience framework would come from previous onboarding workflow
            # For testing, we'll provide it directly for now
        ],
        "entity_username": "test_user_ai_founder"
    }

    # Setup documents (create test documents that will be loaded)
    entity_username = test_inputs["entity_username"]
    setup_docs = [
        # Content Analysis Document
        SetupDocInfo(
            namespace=CONTENT_ANALYSIS_NAMESPACE_TEMPLATE.format(item=entity_username),
            docname=CONTENT_ANALYSIS_DOCNAME,
            initial_data={
      "entity_username": "example-user",
      "theme_reports": [
        {
          "theme_id": "theme_1",
          "theme_name": "AI-Driven Marketing Transformation",
          "hook_analysis": {
            "hook_text": "Look, I've been in tech for twenty years, and I've never seen anything like this. The game with AI isn't playing out like previous tech waves. If you're thinking you can hang back and wait for best practices to emerge like we did with cloud or mobile, you're in for a rough wake-up call.",
            "hook_type": {
              "type": "Storytelling + Bold Claim",
              "metrics": [
                {
                  "metric_name": "Usage Frequency",
                  "metric_value": 6
                },
                {
                  "metric_name": "Average Post Engagement When Present",
                  "metric_value": 191
                }
              ]
            },
            "hook_description": "Posts often open with either a provocative observation (e.g., 'never seen anything like this'), direct industry comparisons ('The game with AI isn't like previous tech waves'), or with a leading question. Question and storytelling hooks correlate with increased comments and engagement. Statistic-driven hooks (e.g., '78% of CMOs say…') foster authority but see moderate engagement. To replicate high-impact hooks, open with a bold claim, a contrarian opinion, or an anecdote relevant to AI change.",
            "engagement_correlation": [
              {
                "average_likes": 132,
                "average_reposts": 6,
                "average_comments": 12
              }
            ]
          },
          "recent_topics": [
            {
              "date": "2025-03-03 21:32:52.507 +0000 UTC",
              "topic": "Weekly AI news impacting marketing (OpenAI, Claude Sonnet, Grok, Adobe data)",
              "summary": "A round-up highlighting the week's most important AI advancements (GPT-4.5, Claude Sonnet, Grok AdTech features), focusing on their impact on marketing and the imperative of keeping up.",
              "engagement": {
                "average_likes": 11,
                "average_reposts": 2,
                "average_comments": 1
              }
            },
            {
              "date": "2025-02-19 07:23:59.189 +0000 UTC",
              "topic": "Grok 3: Large-scale compute and its implications",
              "summary": "Analysis of Grok 3's technological leap and its importance in the GenAI and LLM landscape.",
              "engagement": {
                "average_likes": 12,
                "average_reposts": 1,
                "average_comments": 0
              }
            },
            {
              "date": "2025-01-27 21:07:22.656 +0000 UTC",
              "topic": "DeepSeek breakthrough for marketers (cost-performance, open source)",
              "summary": "Breakdown of DeepSeek's technical and commercial advantages for marketers—inexpensive, open, customizable—plus implications for in-house AI.",
              "engagement": {
                "average_likes": 17,
                "average_reposts": 4,
                "average_comments": 0
              }
            },
            {
              "date": "2025-01-21 09:58:44.453 +0000 UTC",
              "topic": "Cultural urgency: Why marketers must experiment with AI now",
              "summary": "A visionary perspective urging marketers to build cultures of experimentation, framing AI as an exponential force multiplier in business.",
              "engagement": {
                "average_likes": 382,
                "average_reposts": 20,
                "average_comments": 35
              }
            },
            {
              "date": "2025-01-16 18:46:03.449 +0000 UTC",
              "topic": "AI-driven personalization as the 2025 marketing mandate",
              "summary": "Highlights the necessity of AI hyper-personalization, real-time engagement, and the death of traditional segmentation.",
              "engagement": {
                "average_likes": 16,
                "average_reposts": 3,
                "average_comments": 2
              }
            }
          ],
          "tone_analysis": {
            "sentiment": {
              "label": "Positive/Inspirational",
              "average_score": 0.78
            },
            "dominant_tones": [
              "Visionary",
              "Urgent",
              "Authoritative",
              "Encouraging"
            ],
            "tone_description": "Posts consistently project a forward-thinking, urgent optimism: the future is being rewritten by AI, and marketers must act fast or fall behind. There is a positive, excited energy urging experimentation and adaptation. Personal encouragement (\"Get your hands dirty. Break things. Learn. Adapt.\") mixes with authoritative commentary on industry data and trends. Posts rarely express skepticism, instead focusing on opportunities and empowerment.",
            "tone_distribution": [
              {
                "tone": "Visionary",
                "percentage": 35
              },
              {
                "tone": "Urgent",
                "percentage": 25
              },
              {
                "tone": "Authoritative",
                "percentage": 20
              },
              {
                "tone": "Encouraging",
                "percentage": 15
              },
              {
                "tone": "Neutral/Informative",
                "percentage": 5
              }
            ]
          },
          "linguistic_style": {
            "emoji_usage": {
              "metrics": [
                {
                  "emoji": "🚀",
                  "average_frequency": 0.5
                },
                {
                  "emoji": "✅",
                  "average_frequency": 0.4
                },
                {
                  "emoji": "✨",
                  "average_frequency": 0.3
                }
              ],
              "category": "Moderate"
            },
            "unique_terms": [
              {
                "term": "AI Agent",
                "example": "AI Agents independently plan and adapt actions based on feedback.",
                "frequency": 7
              },
              {
                "term": "Generative AI",
                "example": "#GenAI #Grok3 #LLM",
                "frequency": 5
              },
              {
                "term": "Customer Journey",
                "example": "AI agents that can discover organic user paths Marketing and Product teams haven't mapped.",
                "frequency": 4
              },
              {
                "term": "MarTech",
                "example": "#MarTech",
                "frequency": 5
              },
              {
                "term": "Hyper-personalization",
                "example": "AI-driven hyper-personalization will be non-negotiable for brands.",
                "frequency": 2
              }
            ],
            "linguistic_description": "Language is semi-formal, mixing business terminology ('orchestrator', 'intelligence', 'exponential') with approachable phrases and personal anecdotes. Hashtags and bolded bullet points are used to call out trends. Emojis (mostly tech, rocket, checkmark, sparkle) add emphasis without oversaturation. There's light jargon (LLM, SLM, reinforcement learning), but most explanations are made accessible with analogies and plain language."
          },
          "theme_description": "Posts in this theme focus on how artificial intelligence, particularly AI agents and generative models, are revolutionizing marketing operations and intelligence. The content includes market analyses, commentary on AI breakthroughs (like DeepSeek and Grok), and prognostications about the future of marketing powered by AI. The tone is often visionary, urging marketers to embrace rapid experimentation, data-driven personalization, and continuous learning to harness AI's potential.",
          "structure_analysis": {
            "conciseness": {
              "level": "Moderate",
              "metrics": [
                {
                  "metric_name": "Avg Sentences Per Post",
                  "metric_value": 12
                },
                {
                  "metric_name": "Avg Words Per Post",
                  "metric_value": 180
                },
                {
                  "metric_name": "Max Paragraphs",
                  "metric_value": 8
                }
              ],
              "description": "Posts vary from concise announcements (30-40 words) to detailed explainers (300+ words). Most are divided with line breaks, bold headings, and bullet/numbered lists, aiding scan-ability. Longer posts use subheaders ('Bottom line:', 'Why you should care…'), but could sometimes be trimmed for sharper impact. Single-idea posts see higher shares; dense explainers drive more comments."
            },
            "post_format": {
              "example": "Quick snapshot of seven of the top AI news drops from the last 1 week:\n\n⚛️ OpenAI Launches GPT 4.5\n...\n\n(Links in comments)",
              "metrics": [
                {
                  "metric_name": "Format Frequency: Bullet List",
                  "metric_value": 7
                },
                {
                  "metric_name": "Format Frequency: Narrative/Story",
                  "metric_value": 4
                },
                {
                  "metric_name": "Format Frequency: Numbered List",
                  "metric_value": 3
                }
              ],
              "primary_format": "Bullet Points & Narrative Mix"
            },
            "data_intensity": {
              "level": "Moderate-High",
              "example": "78% of CMOs say leadership expects AI-led growth, but few have mastered it.",
              "metrics": [
                {
                  "metric_name": "Posts Citing Specific Stats",
                  "metric_value": 4
                },
                {
                  "metric_name": "Posts Using Technical Jargon",
                  "metric_value": 8
                }
              ]
            },
            "common_structures": [
              {
                "frequency": "6 out of 12",
                "structure": "Hook (bold claim or observation) → List of points/features (bullets) → Strategic takeaway → Call to action or discussion prompt"
              },
              {
                "frequency": "3 out of 12",
                "structure": "Hook → Personal perspective/story → Industry comparison → Closing challenge or encouragement"
              },
              {
                "frequency": "3 out of 12",
                "structure": "Announcement → Invitation to connect/learn more → Reference to more content (e.g., link in comments, swipe for carousel)"
              }
            ],
            "structure_description": "Posts typically open with a dynamic hook: a striking claim, question, or reference to personal experience. Core content either summarizes market/tech news via bullet points or narrates an industry shift via analogy/story. Takeaways are called out as 'Bottom line', 'Why you should care', or with bolded line-breaks. Most posts conclude with an encouragement to experiment, an open invitation for discussion, or a pointer to external resources. To replicate, combine a compelling opener, concise bulleted insights, a strategic takeaway, and end with a call-to-action."
          }
        },
        {
          "theme_id": "theme_2",
          "theme_name": "Building and Empowering Marketing Teams with AI",
          "hook_analysis": {
            "hook_text": "True Story. The first document I wrote at Amazon came back absolutely butchered.",
            "hook_type": {
              "type": "Storytelling",
              "metrics": [
                {
                  "metric_name": "Frequency",
                  "metric_value": 0.4
                }
              ]
            },
            "hook_description": "Posts in this theme often open with engaging stories or anecdotes, questions that invite reflection, or strong future-focused statements (\"It's 2027. Picture this vision for your day as a Marketer\"). This story- or vision-led approach hooks the reader emotionally and frames AI as both practical and aspirational. Data shows that posts starting with a personal story or vivid scenario (vs. straightforward announcements) garner more comments and higher overall engagement.",
            "engagement_correlation": [
              {
                "average_likes": 60,
                "average_reposts": 3,
                "average_comments": 5
              }
            ]
          },
          "recent_topics": [
            {
              "date": "2025-03-27 17:38:09.4 +0000 UTC",
              "topic": "Communication and AI Empowerment",
              "summary": "Reflection on communication norms, context-switching, and how AI can help democratize effective storytelling for marketers.",
              "engagement": {
                "average_likes": 104,
                "average_reposts": 0,
                "average_comments": 17
              }
            },
            {
              "date": "2025-02-12 21:00:39.3 +0000 UTC",
              "topic": "Super Bowl Marketing & Shifting to Smart Growth with AI",
              "summary": "Spotlighting Expert in Residence, trends in smarter growth marketing, and how teams are adapting with AI.",
              "engagement": {
                "average_likes": 7,
                "average_reposts": 1,
                "average_comments": 0
              }
            },
            {
              "date": "2025-01-21 20:01:52.218 +0000 UTC",
              "topic": "Vision for Autonomous AI-Powered Marketing Operations",
              "summary": "A future scenario for marketers empowered by AI, shared by an Expert in Residence, with vivid use cases.",
              "engagement": {
                "average_likes": 31,
                "average_reposts": 3,
                "average_comments": 2
              }
            },
            {
              "date": "2025-01-08 18:07:11.673 +0000 UTC",
              "topic": "Expert Announcement: Khyati Srivastava joins as Expert in Residence",
              "summary": "Introduction to a new expert, their qualifications, and their role in AI-driven marketing transformation.",
              "engagement": {
                "average_likes": 40,
                "average_reposts": 4,
                "average_comments": 4
              }
            },
            {
              "date": "2024-12-26 22:31:59.717 +0000 UTC",
              "topic": "Reflections on Human-AI Synergy in Teams",
              "summary": "Year-end reflection on learning, human-AI collaboration, and closing gaps in team adoption and trust.",
              "engagement": {
                "average_likes": 23,
                "average_reposts": 4,
                "average_comments": 3
              }
            }
          ],
          "tone_analysis": {
            "sentiment": {
              "label": "Positive",
              "average_score": 0.74
            },
            "dominant_tones": [
              "Collaborative",
              "Aspirational",
              "Expertise/Authority"
            ],
            "tone_description": "Posts consistently exude optimism about the future of marketing with AI, warmth in team-building, and a respect for subject-matter expertise. The language is inclusive (\"we\", \"together\", \"our journey\") and often highlights humble learning or gratitude. This positive, team-focused style encourages buy-in and is well-suited to nurturing a following of ambitious marketing professionals. To replicate: use inclusive language, spotlight expertise, and frame AI as an enabler for all.",
            "tone_distribution": [
              {
                "tone": "Collaborative",
                "percentage": 50
              },
              {
                "tone": "Aspirational",
                "percentage": 30
              },
              {
                "tone": "Authoritative",
                "percentage": 20
              }
            ]
          },
          "linguistic_style": {
            "emoji_usage": {
              "metrics": [
                {
                  "emoji": "✨",
                  "average_frequency": 0.13
                },
                {
                  "emoji": "🎉",
                  "average_frequency": 0.07
                },
                {
                  "emoji": "🎯",
                  "average_frequency": 0.03
                },
                {
                  "emoji": "☕️",
                  "average_frequency": 0.03
                },
                {
                  "emoji": "🚀",
                  "average_frequency": 0.07
                }
              ],
              "category": "Sometimes"
            },
            "unique_terms": [
              {
                "term": "Expert(s) in Residence",
                "example": "Excited to welcome another founding Expert in Residence to KiwiQ AI!",
                "frequency": 7
              },
              {
                "term": "AI agent(s)",
                "example": "We are building AI agents to empower Marketing and Growth teams with enhanced intelligence",
                "frequency": 6
              },
              {
                "term": "empower/empowering",
                "example": "empower Marketing teams with better intelligence",
                "frequency": 6
              },
              {
                "term": "KiwiQ AI",
                "example": "At KiwiQ AI, Founder A and I are excited about solving this exact problem",
                "frequency": 10
              }
            ],
            "linguistic_description": "Writing is semi-formal, professional, and accessible. Occasional use of emojis adds personality without diminishing authority. Jargon such as 'AI agent', 'growth marketing', and 'workflow integration' is common but usually explained for comprehension. Frequent use of bulleted/numbered lists and section dividers helps with readability. Tagging/mentioning experts and leveraging quotes increases credibility and engagement."
          },
          "theme_description": "This theme highlights the strategic integration of AI tools into marketing and growth teams, often referencing specific experts and collaboration within the KiwiQ AI initiative. Posts feature introductions of Experts in Residence, reflections on leadership and culture, and concrete examples of how empowered teams can leverage AI for smarter workflows. The tone is collaborative and aspirational, often spotlighting expertise, mentorship, and the value of human-AI synergy in team performance.",
          "structure_analysis": {
            "conciseness": {
              "level": "Moderately Concise",
              "metrics": [
                {
                  "metric_name": "Average words per post",
                  "metric_value": 175
                },
                {
                  "metric_name": "Average paragraphs per post",
                  "metric_value": 6
                }
              ],
              "description": "Posts are longer than typical LinkedIn announcements but well-structured. Most contain personal anecdotes, expert quotes, or context setting, followed by practical takeaways or calls to action. Long paragraphs are broken up by lists, numbers, and section dividers, ensuring scannability."
            },
            "post_format": {
              "example": "- Cross-channel data analyzed before your morning coffee\n- Direct control over campaign optimizations, without needing specialized teams or agencies\n- Instant ability to test messaging across email, social & web...",
              "metrics": [
                {
                  "metric_name": "Posts using bullets or lists",
                  "metric_value": "60%"
                },
                {
                  "metric_name": "Average use of quote blocks",
                  "metric_value": "40%"
                }
              ],
              "primary_format": "Anecdote/Reflection + Bulleted or Numbered Lists + Expert Quotes"
            },
            "data_intensity": {
              "level": "Moderate",
              "example": "\"We're taking multi-week projects and completing them in 15-20 minutes. The real unlock isn't just time savings - it's our ability to run exponentially more experiments.\"",
              "metrics": [
                {
                  "metric_name": "Posts with data/statistics",
                  "metric_value": "30%"
                },
                {
                  "metric_name": "Jargon frequency per post",
                  "metric_value": 4
                }
              ]
            },
            "common_structures": [
              {
                "frequency": "Common",
                "structure": "Opening personal anecdote or expert quote, followed by bulleted key takeaways and a collaborative closing."
              },
              {
                "frequency": "Regular",
                "structure": "Team or expert introduction, with career background and future vision, ending with a call-to-action or invitation."
              }
            ],
            "structure_description": "Most posts begin with a story or expert quote, progress into a structured list (bullets/numbers) summarizing insights or steps, and conclude with a collaborative note (inviting comments, connection, or shared learning). This approach encourages skimming for busy professionals. Use of white space, bold statements, and clear divisions between inspiration and action makes posts easy to absorb and replicate. Providing concrete examples or expert sound bites increases relatability and authority."
          }
        },
        {
          "theme_id": "theme_3",
          "theme_name": "Productization of Content and Marketing Processes",
          "hook_analysis": {
            "hook_text": "⏳ 18 minutes.\n\nThat's how long B2B decision-makers spend on LinkedIn daily.",
            "hook_type": {
              "type": "Data-Driven Statistic",
              "metrics": [
                {
                  "metric_name": "Posts with data/statistics as hook",
                  "metric_value": 1
                },
                {
                  "metric_name": "Posts with analogy/story as hook",
                  "metric_value": 1
                }
              ]
            },
            "hook_description": "Posts in this theme often open with a data point or compelling analogy, quickly establishing authority and relevance. Statistic- or analogy-driven hooks drive higher engagement (higher average reaction/comment count) than generic introductions, as they tap into curiosity and position the author as insightful and sharp. To replicate, begin with a surprising number, bold analogy, or a direct challenge to conventional wisdom.",
            "engagement_correlation": [
              {
                "average_likes": 49,
                "average_reposts": 2,
                "average_comments": 6
              },
              {
                "average_likes": 38,
                "average_reposts": 1,
                "average_comments": 15
              }
            ]
          },
          "recent_topics": [
            {
              "date": "2025-04-23",
              "topic": "Content Creation as Product Management",
              "summary": "Draws explicit parallels between product management principles (audience focus, sprints, prioritization) and systematic LinkedIn content production. Invites process discussion.",
              "engagement": {
                "average_likes": 38,
                "average_reposts": 1,
                "average_comments": 15
              }
            },
            {
              "date": "2025-02-21",
              "topic": "Missed Content Opportunities and Authenticity",
              "summary": "Analyzes how B2B leaders spend time on LinkedIn, points out pitfalls in 'thought leadership' content, and advocates a productized, authentic approach for founders.",
              "engagement": {
                "average_likes": 49,
                "average_reposts": 2,
                "average_comments": 6
              }
            }
          ],
          "tone_analysis": {
            "sentiment": {
              "label": "Positive",
              "average_score": 0.67
            },
            "dominant_tones": [
              "Analytical",
              "Optimistic",
              "Authoritative"
            ],
            "tone_description": "Posts consistently balance an analytical, solution-oriented tone with optimism about systematic improvement. They demonstrate authority through confident recommendations and practitioner insights. The positive sentiment emerges through the language of opportunity, improvement, and actionable frameworks. To replicate, write in a confident yet approachable style, emphasize clarity, and use forward-looking language (e.g., 'improvement', 'opportunity', 'guiding direction').",
            "tone_distribution": [
              {
                "tone": "Analytical",
                "percentage": 55
              },
              {
                "tone": "Optimistic",
                "percentage": 25
              },
              {
                "tone": "Authoritative",
                "percentage": 15
              },
              {
                "tone": "Invitational",
                "percentage": 5
              }
            ]
          },
          "linguistic_style": {
            "emoji_usage": {
              "metrics": [
                {
                  "emoji": "👀",
                  "average_frequency": 0.5
                },
                {
                  "emoji": "🙂",
                  "average_frequency": 0.5
                }
              ],
              "category": "Sparingly"
            },
            "unique_terms": [
              {
                "term": "product management",
                "example": "Here are 3 powerful product parallels...",
                "frequency": 3
              },
              {
                "term": "sprint",
                "example": "Product teams don't ship randomly; they use sprints.",
                "frequency": 2
              },
              {
                "term": "audience focus",
                "example": "Who is this for, and what specific pain/goal does it address?",
                "frequency": 2
              },
              {
                "term": "prioritization",
                "example": "Edit brutally. Cut out the luxury features, sharpen focus",
                "frequency": 2
              }
            ],
            "linguistic_description": "Language is semi-formal to formal, with clear professional jargon tailored to product and marketing practitioners (e.g., 'sprints', 'scope creep', 'content as product'). Formatting is deliberate: uses bullet points, bold statements, and numbered formats to convey clarity. Emojis are used sparingly for occasional emphasis or tone softening, not for playfulness. Sentences are direct and active. Hashtags focus on process, AI, and thought leadership. To replicate, use business-focused vocabulary, concise sentences, and formatting to highlight key concepts."
          },
          "theme_description": "Posts grouped here draw parallels between software/product development and effective content creation or marketing execution. The content discusses how applying product management principles—such as clear audience focus, sprint-based execution, and ruthless prioritization—leads to better marketing strategies and predictable improvements. The intent is to share process frameworks and lessons, inviting engagement from other professionals, and promoting a systematic, rigorous approach to marketing work.",
          "structure_analysis": {
            "conciseness": {
              "level": "Concise",
              "metrics": [
                {
                  "metric_name": "Average sentence length",
                  "metric_value": 15
                },
                {
                  "metric_name": "Average paragraphs per post",
                  "metric_value": 5
                },
                {
                  "metric_name": "Typical word count range",
                  "metric_value": "175–350"
                }
              ],
              "description": "Posts are tightly edited, rarely wandering off topic. Information is grouped in short blocks or bullets, each unit purposefully shaped around a takeaway or actionable idea. Rarely padded with fluff or digressions; each paragraph or bullet delivers standalone value."
            },
            "post_format": {
              "example": "Here are 3 powerful product parallels that have stood out for me...",
              "metrics": [
                {
                  "metric_name": "Average bullets/lists per post",
                  "metric_value": 3
                }
              ],
              "primary_format": "Numbered/Bulleted Lists alongside narrative explanation"
            },
            "data_intensity": {
              "level": "Moderate",
              "example": "\"⏳ 18 minutes. That's how long B2B decision-makers spend on LinkedIn daily.\"",
              "metrics": [
                {
                  "metric_name": "Posts with statistical/data-driven references",
                  "metric_value": 1
                },
                {
                  "metric_name": "Posts referencing frameworks/processes",
                  "metric_value": 2
                }
              ]
            },
            "common_structures": [
              {
                "frequency": "High (100%)",
                "structure": "Opens with statistic or provocative analogy, followed by key takeaways framed as bullets or steps."
              },
              {
                "frequency": "Medium (50%)",
                "structure": "Explicit question or CTA for audience involvement at the end."
              }
            ],
            "structure_description": "Each post opens with a high-impact statement (either data or analogy), followed by 2–4 compact sections or bullets, typically containing a principle, process, or 'lesson learned.' Posts close with an open-ended question or CTA, steering discussion and inviting knowledge sharing. To replicate, plan your post around 3–4 substantial takeaways, lead with a statistic or analogy, support each point with an actionable tip, and close with an explicit invitation for comments or peer insights."
          }
        },
        {
          "theme_id": "theme_4",
          "theme_name": "Commentary on Industry Shifts and Emerging Tech Trends",
          "hook_analysis": {
            "hook_text": "Marketing Tech Procurement is Broken.",
            "hook_type": {
              "type": "Bold Statement",
              "metrics": [
                {
                  "metric_name": "Usage Frequency",
                  "metric_value": 3
                },
                {
                  "metric_name": "Average Engagement (reactions+comments+reposts)",
                  "metric_value": 60.5
                }
              ]
            },
            "hook_description": "Posts often open with either a bold statement (e.g., 'Marketing Tech Procurement is Broken'), a provocative question (e.g., 'Can AR be to the internet what the internet was to computing?'), or a quick summary/set-up (e.g., 'Quick snapshot of seven of the top AI news drops'). Bold, attention-grabbing statements correlate strongly with higher engagement, especially when paired with a clear, actionable insight or storytelling segue. Direct questions also generate above-average comment volumes, as they invite readers' perspectives.",
            "engagement_correlation": [
              {
                "average_likes": 53,
                "average_reposts": 4.5,
                "average_comments": 20
              }
            ]
          },
          "recent_topics": [
            {
              "date": "2025-04-01 23:38:07.16 +0000 UTC",
              "topic": "April Fool's Satire on Developer Side Gigs",
              "summary": "Humorous take on the developer gig economy and non-technical 'vibe coders'. Satirical commentary on tech labor market.",
              "engagement": {
                "average_likes": 256,
                "average_reposts": 8,
                "average_comments": 34
              }
            },
            {
              "date": "2025-03-17 19:09:35.131 +0000 UTC",
              "topic": "Google and Gemini AI Launch",
              "summary": "Brief commentary on Google's ongoing AI launches and anticipation to test Gemini features.",
              "engagement": {
                "average_likes": 12,
                "average_reposts": 0,
                "average_comments": 0
              }
            },
            {
              "date": "2025-02-24 20:06:07.334 +0000 UTC",
              "topic": "Weekly Top AI News Drops",
              "summary": "Summarizes major AI developments and company announcements, including Microsoft, Google, xAI, Adobe, Meta, legal rulings, and marketing efficiency studies.",
              "engagement": {
                "average_likes": 16,
                "average_reposts": 2,
                "average_comments": 2
              }
            },
            {
              "date": "2025-02-06 01:58:37.793 +0000 UTC",
              "topic": "Problems with Martech Procurement",
              "summary": "Analytical breakdown of issues in marketing technology procurement, including organizational misalignment, process flaws, and digital transformation gaps.",
              "engagement": {
                "average_likes": 43,
                "average_reposts": 3,
                "average_comments": 14
              }
            },
            {
              "date": "2024-12-03 01:50:36.054 +0000 UTC",
              "topic": "From Cloud to AI-Native Architectures",
              "summary": "Macro-industry comparison between cloud transition and upcoming 'AI native' tech movement, implications for service industries.",
              "engagement": {
                "average_likes": 88,
                "average_reposts": 7,
                "average_comments": 42
              }
            },
            {
              "date": "2016-07-14 14:26:44.295 +0000 UTC",
              "topic": "AR as a Transformative Platform",
              "summary": "Speculates on AR's potential impact, in playful context referencing Pokémon Go and paradigm shifts in computing.",
              "engagement": {
                "average_likes": 3,
                "average_reposts": 0,
                "average_comments": 0
              }
            }
          ],
          "tone_analysis": {
            "sentiment": {
              "label": "Generally Positive",
              "average_score": 0.66
            },
            "dominant_tones": [
              "Analytical",
              "Insightful",
              "Humorous",
              "Optimistic"
            ],
            "tone_description": "The posts prominently feature an analytical, macro-level perspective, often synthesizing complex trends for marketing and tech audiences. There is a strong 'thought leadership' flavor, blending insight with forward-looking observations. Humor and light sarcasm are strategically deployed, especially in seasonal or special posts (e.g., April Fool's), which spike engagement. Sentiment is generally positive and future-oriented, with occasional warnings about underestimating shifts. To replicate this, combine market context with actionable insight and, where appropriate, inject wit to humanize the analysis.",
            "tone_distribution": [
              {
                "tone": "Analytical",
                "percentage": 70
              },
              {
                "tone": "Humorous/Satirical",
                "percentage": 15
              },
              {
                "tone": "Optimistic",
                "percentage": 10
              },
              {
                "tone": "Cautionary/Warning",
                "percentage": 5
              }
            ]
          },
          "linguistic_style": {
            "emoji_usage": {
              "metrics": [
                {
                  "emoji": "\u0019d\nde16\nde14\nde00",
                  "average_frequency": 2.3
                },
                {
                  "emoji": "\u0019d\nde15",
                  "average_frequency": 1
                }
              ],
              "category": "Sometimes"
            },
            "unique_terms": [
              {
                "term": "Martech",
                "example": "Marketing Tech Procurement is Broken. It's not that procurement doesn't understand Martech.",
                "frequency": 5
              },
              {
                "term": "AI-native",
                "example": "Will AI disrupt the existing cloud incumbents? Not really. The incumbents have the distribution and the data—and foundation models are accessible to everyone. But... what if that is wrong?",
                "frequency": 2
              },
              {
                "term": "Procurement",
                "example": "Marketing Tech Procurement is Broken. It's not that procurement doesn't understand Martech ...",
                "frequency": 7
              },
              {
                "term": "Vibecoder",
                "example": "Vibefix.dev connects desperate non-technical vibe-coders...",
                "frequency": 2
              }
            ],
            "linguistic_description": "Posts are written in a semi-formal, direct style. Paragraphs are short, and key points are sometimes introduced with emoji markers or bulleted/numbered lists for emphasis. There is moderate use of technical and marketing jargon ('Martech', 'AI-native', 'cloud shift', etc.), matched to the intended senior or sophisticated audience. Hashtags are present but not overused. Rare use of emojis—mainly for section breaks or to denote highlights—injects subtle personality without diminishing professionalism. Posts sometimes use personalized rhetorical questions or address the reader as 'we' to foster engagement and shared perspective."
          },
          "theme_description": "This theme encompasses commentary on wider technology and business shifts impacting marketing, such as changes in martech procurement, the evolution from cloud to AI-native architectures, or new research and breakthroughs from major tech firms. The tone ranges from analytical to occasionally humorous (as in the April Fool's post), and the posts often synthesize takeaways or highlight macro-level trends that require adaptation in marketing and business operations.",
          "structure_analysis": {
            "conciseness": {
              "level": "Varies: Concise to Extended",
              "metrics": [
                {
                  "metric_name": "Shortest post word count",
                  "metric_value": 18
                },
                {
                  "metric_name": "Longest post word count",
                  "metric_value": 497
                },
                {
                  "metric_name": "Average post length",
                  "metric_value": 179
                }
              ],
              "description": "Post lengths vary widely depending on depth of topic. Short news reactions are concise (under 25 words), while analytical explainers and trend breakdowns are long-form (300-500 words), subdivided by bullet points, numbered lists, and clearly demarcated sections. Longer posts balance detail with scannability by segmenting content—crucial for maintaining engagement on dense or technical topics. Conciseness is maintained within sections even when the total post is lengthy."
            },
            "post_format": {
              "example": "Marketing Tech Procurement is Broken... 1. Marketing doesn't articulate what it actually needs. 2. Procurement follows a rigid buying process... Most Martech failures begin with how it's bought. Fix that, and you solve half the problem before it even begins.",
              "metrics": [
                {
                  "metric_name": "Posts with bullet/numbered lists",
                  "metric_value": 4
                },
                {
                  "metric_name": "Posts using summary setup",
                  "metric_value": 3
                }
              ],
              "primary_format": "Bullet and Numbered Lists with Narrative Intro/Outro"
            },
            "data_intensity": {
              "level": "Moderate",
              "example": "54% of procurement leaders say digital transformation skills are critical, yet only 36% feel equipped to handle them.",
              "metrics": [
                {
                  "metric_name": "Posts with stats or data points",
                  "metric_value": 2
                },
                {
                  "metric_name": "Posts referencing research/reports",
                  "metric_value": 3
                }
              ]
            },
            "common_structures": [
              {
                "frequency": "Frequently",
                "structure": "Headline statement or question, followed by scannable bullets/sections, then summary or call to action"
              },
              {
                "frequency": "Occasionally",
                "structure": "Single-paragraph commentary on breaking tech news (e.g., Google Gemini post)"
              },
              {
                "frequency": "Sometimes",
                "structure": "Storytelling or satire blend (April Fool's-style, AR/pokémon anecdote)"
              }
            ],
            "structure_description": "The dominant structure starts with either a bold claim or a clarifying question, moves into a segmented discussion (bullets or numbered points), and concludes with a macro-level takeaway or open-ended question. Posts on rapid-fire news often adopt a list format with each bullet summarizing a trend or announcement, while longer analytical pieces split concepts into digestible chunks—improving reader retention. Humor and cultural references sometimes shape the open or close, making dense topics approachable."
          }
        },
        {
          "theme_id": "theme_5",
          "theme_name": "Community, Networking, and Advocacy",
          "hook_analysis": {
            "hook_text": "\u001f4a5 URGENT: Help Save 8-Year Old Kaia's Life \u001f4a5",
            "hook_type": {
              "type": "Bold Claim / Call to Action",
              "metrics": [
                {
                  "metric_name": "Usage Frequency",
                  "metric_value": 2
                },
                {
                  "metric_name": "Average Placement",
                  "metric_value": "Sentence 1"
                }
              ]
            },
            "hook_description": "Posts often open with a strong call to action or statement of urgency, especially in advocacy or event-driven posts (examples: 'URGENT', 'Excited to partner', '10 days left'). These direct hooks immediately signal purpose and draw attention. Event invitations and hiring posts frequently use excitement language ('Excited to share', 'We are hiring'), while advocacy may use emotional urgency. This approach generates strong engagement for high-stakes or personally relevant content (e.g., the Kaia donor call saw the highest engagement by far). Recommendations: Continue using strong, action-oriented first sentences for critical or time-sensitive posts; experiment with more questions as hooks to spark conversation.",
            "engagement_correlation": [
              {
                "average_likes": 950,
                "average_reposts": 172,
                "average_comments": 110
              },
              {
                "average_likes": 60,
                "average_reposts": 5,
                "average_comments": 10
              }
            ]
          },
          "recent_topics": [
            {
              "date": "2025-05-02 03:49:42.525 +0000 UTC",
              "topic": "Medical advocacy and urgent donor call",
              "summary": "Urgent appeal to find a bone marrow donor for a child, inclusive instructions, and amplification request.",
              "engagement": {
                "average_likes": 1629,
                "average_reposts": 504,
                "average_comments": 216
              }
            },
            {
              "date": "2025-04-17 22:12:28.193 +0000 UTC",
              "topic": "Tech event partnership and networking",
              "summary": "Promotion of a multi-stakeholder tech networking event with detailed agenda highlights.",
              "engagement": {
                "average_likes": 42,
                "average_reposts": 0,
                "average_comments": 2
              }
            },
            {
              "date": "2025-01-15 21:28:38.056 +0000 UTC",
              "topic": "Accelerator program recruitment",
              "summary": "Call for applications to an equity-free accelerator program, emphasizing mission and founder support.",
              "engagement": {
                "average_likes": 49,
                "average_reposts": 9,
                "average_comments": 1
              }
            },
            {
              "date": "2022-10-03 15:25:24.746 +0000 UTC",
              "topic": "Webinar: Data for elections and advocacy",
              "summary": "Invitation to a webinar based on meta-analysis of political ad impact, sharing new data insights.",
              "engagement": {
                "average_likes": 35,
                "average_reposts": 5,
                "average_comments": 1
              }
            },
            {
              "date": "2022-06-18 17:57:43.249 +0000 UTC",
              "topic": "Career update and team invitation",
              "summary": "Announcement of a new role, company mission, team gratitude, and open job opportunities.",
              "engagement": {
                "average_likes": 280,
                "average_reposts": 0,
                "average_comments": 32
              }
            },
            {
              "date": "2021-12-02 00:08:20.512 +0000 UTC",
              "topic": "Startup milestone and hiring",
              "summary": "Celebration of company progress with invitation for talent to join the team.",
              "engagement": {
                "average_likes": 12,
                "average_reposts": 0,
                "average_comments": 0
              }
            },
            {
              "date": "2021-09-02 02:06:53.923 +0000 UTC",
              "topic": "Senior technical hiring",
              "summary": "Open call for engineering and program management talent in a scaling startup.",
              "engagement": {
                "average_likes": 21,
                "average_reposts": 0,
                "average_comments": 0
              }
            },
            {
              "date": "2020-03-26 23:10:56.88 +0000 UTC",
              "topic": "Hiring: Amazon Senior Data Scientist",
              "summary": "Job ad targeting experienced data scientists, emphasizing opportunity and impact.",
              "engagement": {
                "average_likes": 28,
                "average_reposts": 0,
                "average_comments": 3
              }
            }
          ],
          "tone_analysis": {
            "sentiment": {
              "label": "Positive",
              "average_score": 0.68
            },
            "dominant_tones": [
              "Inclusive",
              "Mobilizing",
              "Supportive",
              "Urgent (occasionally)"
            ],
            "tone_description": "Writing is consistently positive, welcoming, and designed to rally participation. Many posts use emotionally resonant language when the situation demands (e.g., medical advocacy), while others stick to energetic encouragement and gratitude for milestones or calls for recruitment. The tone often blends a sense of shared purpose with supportive or forward-looking optimism.",
            "tone_distribution": [
              {
                "tone": "Inclusive/Supportive",
                "percentage": 60
              },
              {
                "tone": "Mobilizing/Urgent",
                "percentage": 20
              },
              {
                "tone": "Celebratory",
                "percentage": 10
              },
              {
                "tone": "Grateful/Appreciative",
                "percentage": 10
              }
            ]
          },
          "linguistic_style": {
            "emoji_usage": {
              "metrics": [
                {
                  "emoji": "\u001f4a5",
                  "average_frequency": 0.2
                },
                {
                  "emoji": "\u001f680",
                  "average_frequency": 0.25
                },
                {
                  "emoji": "\u001f525",
                  "average_frequency": 0.13
                },
                {
                  "emoji": "\u001f3a4",
                  "average_frequency": 0.13
                },
                {
                  "emoji": "\u001f3b7",
                  "average_frequency": 0.13
                }
              ],
              "category": "Sometimes"
            },
            "unique_terms": [
              {
                "term": "hiring",
                "example": "we are hiring across the board",
                "frequency": 5
              },
              {
                "term": "community",
                "example": "building affordable biochemical tests for diagnosing genetic diseases",
                "frequency": 3
              },
              {
                "term": "join us",
                "example": "If you're someone that refuses to let history pass you by... then join us.",
                "frequency": 2
              }
            ],
            "linguistic_description": "Language is semi-formal, direct, and motivational. Uncommon to see slang; contractions and conversational tone ('hit me up', 'let's chat') make the writer approachable. Formatting uses spacing, bold elements (via emojis), bulleted/numbered highlights, and occasionally hashtags for reach. Domain-specific jargon (e.g., 'equity-free', 'bio founder', 'AUM') is used when audience context is specialized. Posts close with a call to connect, apply, or share."
          },
          "theme_description": "Posts in this category are oriented around building community, facilitating events, and advocacy—whether that's rallying support for medical causes, announcing partnerships, celebrating team milestones, or sharing hiring opportunities. The tone is inclusive and mobilizing, encouraging readers to connect, participate, or support broader professional and social initiatives, occasionally extending beyond AI and martech to address urgent human needs or career development.",
          "structure_analysis": {
            "conciseness": {
              "level": "Moderately Concise",
              "metrics": [
                {
                  "metric_name": "Average Sentence Length",
                  "metric_value": 18
                },
                {
                  "metric_name": "Average Paragraph Count",
                  "metric_value": 3.5
                },
                {
                  "metric_name": "Longest Post (Words)",
                  "metric_value": 370
                },
                {
                  "metric_name": "Shortest Post (Words)",
                  "metric_value": 27
                }
              ],
              "description": "Posts are generally short to mid-length. Event and hiring announcements are concise (50-100 words); advocacy and accelerator descriptions extend up to 350+ words when providing stories or urgent context. Sections are broken by whitespace for readability. Calls to action are always clear and separated by an empty line."
            },
            "post_format": {
              "example": "\u001f680 Panels with VCs from LG Ventures, Blackrock, SignalFire...\n> repeat bio founder building affordable biochemical tests...\napply: joinsavant.com",
              "metrics": [
                {
                  "metric_name": "Bulleted List Usage",
                  "metric_value": "60%"
                },
                {
                  "metric_name": "Hashtags per Post",
                  "metric_value": 2
                }
              ],
              "primary_format": "Bulleted or Emphasized Point List, Sectioned by Whitespace"
            },
            "data_intensity": {
              "level": "Moderate",
              "example": "over $4 trillion in capital meets 2,000+ founders, VCs, and family offices — all in one night.",
              "metrics": [
                {
                  "metric_name": "Numerical References per Post",
                  "metric_value": 2.1
                },
                {
                  "metric_name": "Jargon/Industry Term Usage",
                  "metric_value": 3.7
                }
              ]
            },
            "common_structures": [
              {
                "frequency": "45%",
                "structure": "Event or job announcement with bulleted highlights, link at end"
              },
              {
                "frequency": "25%",
                "structure": "Storytelling or advocacy post (first-person, emotional appeal, multi-paragraph with white space)"
              },
              {
                "frequency": "20%",
                "structure": "Short gratitude update or career milestone, call to connect"
              },
              {
                "frequency": "10%",
                "structure": "Webinar/data insight invites with action link"
              }
            ],
            "structure_description": "Most posts use an easy-to-digest format: open with a hook, use whitespace for scannability, introduce lists or bullet points for facts/highlights, and close with a link or call to action. Urgency or emotional context (notably in medical appeals) drives longer, more narrative structures. All posts include clear instructions for reader action. Hashtags are present but not excessive."
          }
        }
      ],
      "created_at": "2025-05-24T05:12:05.769000",
      "updated_at": "2025-05-24T05:12:05.769000"
    },
            is_versioned=False,
            is_shared=False,
            initial_version="default",
            is_system_entity=False
        ),
        # User Preferences / Onboarding Responses
        SetupDocInfo(
            namespace=USER_PREFERENCES_NAMESPACE_TEMPLATE.format(item=entity_username),
            docname=USER_PREFERENCES_DOCNAME,
            initial_data={
      "created_at": "2025-05-15T11:20:19.225000",
      "updated_at": "2025-05-24T05:16:20.700000",
      "goals": {
        "selected": [
          {
            "goal_id": "personal-branding",
            "name": "Personal Branding",
            "description": "Cultivate a distinctive professional identity that makes you instantly recognizable in your field."
          },
          {
            "goal_id": "career-development",
            "name": "Career Development",
            "description": "Demonstrate your professional growth journey and expertise to attract better opportunities and connections."
          },
          {
            "goal_id": "knowledge-sharing",
            "name": "Establish Thought Leadership",
            "description": "Establish yourself as an industry authority by sharing valuable insights your network can't find elsewhere."
          }
        ],
        "custom_goals": None
      },
      "audience": {
        "segments": [
          {
            "name": "Industry Professionals"
          },
          {
            "name": "Customers & Prospects"
          },
          {
            "name": "Business Stakeholders"
          }
        ]
      }
    },
            is_versioned=USER_PREFERENCES_IS_VERSIONED,
            is_shared=False,
            initial_version="default",
            is_system_entity=False
        ),
        # LinkedIn Profile
        SetupDocInfo(
            namespace=LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE.format(item=entity_username),
            docname=LINKEDIN_PROFILE_DOCNAME,
            initial_data={
      "geo": {
        "country": "United States",
        "city": "San Francisco Bay Area",
        "full": "San Francisco Bay Area",
        "countryCode": "us"
      },
      "username": "example-user",
      "summary": "Entrepreneurial product leader passionate about building futuristic customer solutions, using technology, behavioral understanding, a lot of enthusiasm and some patience. I get energized by bold ideas, smart cross-functional teams and meaningful problem spaces. \n\nIf you want to connect, feel free to drop me a line on user9@example.com.",
      "firstName": "Founder B",
      "headline": "Founder at KiwiQ AI | Building Intelligent Teammates for Marketers",
      "lastName": "Bharadwaj",
      "educations": [
        {
          "end": {
            "year": 2017,
            "month": 0,
            "day": 0
          },
          "fieldOfStudy": "Business Administration and Management, General",
          "start": {
            "year": 2015,
            "month": 0,
            "day": 0
          },
          "degree": "MBA",
          "schoolName": "University of Michigan - Stephen M. Ross School of Business"
        },
        {
          "end": {
            "year": 2011,
            "month": 0,
            "day": 0
          },
          "fieldOfStudy": "Mechanical Engineering",
          "start": {
            "year": 2007,
            "month": 0,
            "day": 0
          },
          "degree": "B.Tech",
          "schoolName": "National Institute of Technology, Tiruchirappalli"
        }
      ],
      "position": [
        {
          "location": "San Francisco Bay Area",
          "companyName": "Pavilion",
          "companyIndustry": "Think Tanks"
        },
        {
          "location": "San Francisco Bay Area",
          "description": "Building Agent helpers for Marketing teams",
          "companyName": "KiwiQ AI",
          "companyIndustry": "Computer Software"
        },
        {
          "location": "San Francisco Bay Area",
          "description": "OnDeck Founder Fellow",
          "companyName": "On Deck",
          "companyIndustry": "Computer Software"
        },
        {
          "description": "Advising B2B startups with their GTM\n\nAngel invested in a few startups (B2B, Deeptech)",
          "companyName": "Various Startups",
          "companyIndustry": "Computer Software"
        },
        {
          "location": "San Francisco, California, United States",
          "description": "Led research, planning, and delivery of 0-to-1 self-serve product targeting Brand Managers and Ad Agencies, scaling to 15 beta users first $100K ARR. \n\nWorked closely with the Founders, leading a cross-functional team of 4 Engineers and 1 UX Designer.",
          "companyName": "Swayable",
          "companyIndustry": "Computer Software"
        },
        {
          "location": "San Francisco Bay Area",
          "description": "Closely partnered with an enterprise beta client to deliver Sounding Board's first SaaS product (0-to-1),\nmanaging a team of 9 engineers and 2 designers.",
          "companyName": "Sounding Board, Inc",
          "companyIndustry": "Professional Training & Coaching"
        },
        {
          "location": "Cupertino, California, United States",
          "description": "Single-threaded leader of the 3P fulfillment workstream for Amazon B2B; developed multi-\nyear product roadmap, driving feature prioritization and technical delivery plan.",
          "companyName": "Amazon",
          "companyIndustry": "Computer Software"
        },
        {
          "location": "Santa Clara, California, United States",
          "description": "Led the internal GTM for a 0-to-1 customer insights product using NLP, growing to 50+ internal team users",
          "companyName": "Amazon",
          "companyIndustry": "Computer Software"
        },
        {
          "location": "Luxembourg",
          "description": "Led product for personalization and customer experience for Amazon's launch in the Netherlands.",
          "companyName": "Amazon",
          "companyIndustry": "Computer Software"
        },
        {
          "location": "Greater Seattle Area",
          "description": "Set up an NLP-powered Voice of Customer product function within Amazon's used products business.",
          "companyName": "Amazon",
          "companyIndustry": "Computer Software"
        },
        {
          "location": "Austin, Texas Area",
          "companyName": "Dell",
          "companyIndustry": "Computer Hardware"
        },
        {
          "location": "São Paulo Area, Brazil",
          "companyName": "Bunzl plc",
          "companyIndustry": "Wholesale"
        },
        {
          "location": "Bengaluru Area, India",
          "description": "Launched the company's fastest growing category (0-to-1), wearing multiple hats to make it happen.",
          "companyName": "Urban Ladder",
          "companyIndustry": "Computer Software"
        }
      ],
      "created_at": "2025-05-24T05:10:33.407000",
      "updated_at": "2025-05-24T05:10:33.407000"
    },
            is_versioned=False,
            is_shared=False,
            initial_version="default",
            is_system_entity=False
        ),
    ]

    # Cleanup documents - explicitly clean up all test documents created during setup
    cleanup_docs = [
        # Content Analysis Document
        CleanupDocInfo(
            namespace=CONTENT_ANALYSIS_NAMESPACE_TEMPLATE.format(item=entity_username),
            docname=CONTENT_ANALYSIS_DOCNAME,
            is_versioned=False,
            is_shared=False,
            is_system_entity=False
        ),
        # User Preferences Document
        CleanupDocInfo(
            namespace=USER_PREFERENCES_NAMESPACE_TEMPLATE.format(item=entity_username),
            docname=USER_PREFERENCES_DOCNAME,
            is_versioned=USER_PREFERENCES_IS_VERSIONED,
            is_shared=False,
            is_system_entity=False
        ),
        # LinkedIn Profile Document
        CleanupDocInfo(
            namespace=LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE.format(item=entity_username),
            docname=LINKEDIN_PROFILE_DOCNAME,
            is_versioned=False,
            is_shared=False,
            is_system_entity=False
        ),
    ]

    try:
        # Run the workflow test
        final_run_status_obj, final_run_outputs = await run_workflow_test(
            test_name=test_name,
            workflow_graph_schema=workflow_graph_schema,
            initial_inputs=test_inputs,
            expected_final_status=WorkflowRunStatus.COMPLETED,
            hitl_inputs=[],
            setup_docs=setup_docs,
            cleanup_docs_created_by_setup=True,  # Auto-cleanup setup docs
            cleanup_docs=cleanup_docs,  # Explicit cleanup docs for safety
            validate_output_func=validate_core_beliefs_perspectives_extraction_output,
            stream_intermediate_results=True,
            poll_interval_sec=5,
            timeout_sec=600
        )

        print(f"---Finished ---")
        if final_run_status_obj.status == WorkflowRunStatus.COMPLETED:
            print(f"completed successfully!")
            
            # Display the personalized questions output
            if final_run_outputs:
                personalized_output = final_run_outputs.get("personalized_questions", {})
                if personalized_output:
                    print("\n--- TOP QUESTIONS FOR CONTENT CREATION ---")
                    print(f"Introduction: {personalized_output.get('introduction', '')[:200]}...")
                    
                    top_questions = personalized_output.get("top_questions", [])
                    print(f"✓ Selected {len(top_questions)} top questions for content creation")
                    
                    # Show first few questions as examples
                    for i, question in enumerate(top_questions[:3]):
                        print(f"\nQuestion {i+1}:")
                        print(f"  Text: {question.get('question_text', '')}")
                        print(f"  Context: {question.get('context_explanation', '')[:100]}...")
                    
                    selection_reasoning = personalized_output.get('selection_reasoning', '')
                    if selection_reasoning:
                        print(f"\nSelection Reasoning: {selection_reasoning[:200]}...")
                
                # Display content intelligence output
                content_intelligence = final_run_outputs.get("content_intelligence", {})
                if content_intelligence:
                    print("\n--- CONTENT INTELLIGENCE SUMMARY ---")
                    print(f"📊 Total Themes: {content_intelligence.get('total_themes_identified', 0)}")
                    print(f"🏆 Top Theme: {content_intelligence.get('top_theme_name', 'N/A')}")
                    
                    top_3_themes = content_intelligence.get("top_3_themes", [])
                    if top_3_themes:
                        print(f"\n🎯 TOP 3 CONTENT THEMES:")
                        for i, theme in enumerate(top_3_themes[:3]):
                            print(f"\n{i+1}. {theme.get('theme_name', 'Unknown')}")
                            print(f"   📈 Avg Likes: {theme.get('avg_engagement_likes', 0)}")
                            print(f"   💬 Avg Comments: {theme.get('avg_engagement_comments', 0)}")
                            print(f"   🎭 Tone: {theme.get('dominant_tone', 'N/A')}")
                    
                    writing_dna = content_intelligence.get("writing_dna", {})
                    if writing_dna:
                        print(f"\n📝 WRITING DNA:")
                        signature_phrases = writing_dna.get("signature_phrases", [])
                        if signature_phrases:
                            print(f"   🎨 Signature Phrases: {', '.join(signature_phrases[:3])}")
                        print(f"   ✍️ Writing Style: {writing_dna.get('writing_style', 'N/A')}")
                        print(f"   📊 Data Usage: {writing_dna.get('data_usage_level', 'N/A')}")
                        print(f"   😊 Emoji Style: {writing_dna.get('emoji_style', 'N/A')}")
                    
                    winning_formulas = content_intelligence.get("winning_formulas", {})
                    if winning_formulas:
                        print(f"\n🚀 WINNING FORMULAS:")
                        opening_patterns = winning_formulas.get("top_opening_patterns", [])
                        if opening_patterns:
                            print(f"   🎯 Top Openings: {', '.join(opening_patterns[:2])}")
                        closing_patterns = winning_formulas.get("top_closing_patterns", [])
                        if closing_patterns:
                            print(f"   🏁 Top Closings: {', '.join(closing_patterns[:2])}")
                        power_words = winning_formulas.get("power_words", [])
                        if power_words:
                            print(f"   💪 Power Words: {', '.join(power_words[:5])}")
                
                # Show core questions structure
                core_questions = final_run_outputs.get("core_beliefs_questions", {})
                if core_questions:
                    total_questions = sum(len(questions) for questions in core_questions.values() if isinstance(questions, list))
                    print(f"\n✓ Generated {total_questions} initial questions, filtered to top {len(top_questions)} for content creation")
            
            return final_run_status_obj, final_run_outputs
        else:
            print(f"failed with status: {final_run_status_obj.status}")
            print(f"Error: {final_run_status_obj.error}")
            return final_run_status_obj, final_run_outputs

    except Exception as e:
        logging.error("failed with exception: {str(e)}")
        print(f"failed with exception: {str(e)}")
        return None, None


async def validate_core_beliefs_perspectives_extraction_output(
    outputs: Optional[Dict[str, Any]]
) -> bool:
    """
    Validate the core beliefs and perspectives extraction workflow output.
    """
    if not outputs:
        logging.error("No outputs received from workflow")
        return False

    # Check for required output fields
    required_fields = ["personalized_questions", "core_beliefs_questions", "content_intelligence"]
    
    for field in required_fields:
        if field not in outputs:
            logging.error(f"Missing required output field: {field}")
            return False

    # Validate personalized questions output structure
    personalized_output = outputs.get("personalized_questions", {})
    if not isinstance(personalized_output, dict):
        logging.error("personalized_questions is not a dictionary")
        return False

    # Check for required personalized output fields
    required_personalized_fields = ["top_questions"]
    for field in required_personalized_fields:
        if field not in personalized_output:
            logging.error(f"Missing required personalized output field: {field}")
            return False

    # Validate questions
    top_questions = personalized_output.get("top_questions", [])
    if not isinstance(top_questions, list) or len(top_questions) == 0:
        logging.error("top_questions should be a non-empty list")
        return False

    # Validate that each question has the required fields
    for i, question in enumerate(top_questions):
        if not isinstance(question, dict):
            logging.error(f"Question {i} is not a dictionary")
            return False
        
        required_question_fields = ["question_text", "context_explanation"]
        for field in required_question_fields:
            if field not in question:
                logging.error(f"Question {i} missing required field: {field}")
                return False
            
            if not question[field] or len(question[field].strip()) < 10:
                logging.error(f"Question {i} field '{field}' should be substantial")
                return False

    # Validate core beliefs questions structure
    core_questions = outputs.get("core_beliefs_questions", {})
    if not isinstance(core_questions, dict):
        logging.error("core_beliefs_questions is not a dictionary")
        return False

    # Validate content intelligence output structure
    content_intelligence = outputs.get("content_intelligence", {})
    if not isinstance(content_intelligence, dict):
        logging.error("content_intelligence is not a dictionary")
        return False

    # Check for required content intelligence fields
    required_intelligence_fields = ["total_themes_identified", "top_theme_name", "top_3_themes", "writing_dna", "winning_formulas"]
    for field in required_intelligence_fields:
        if field not in content_intelligence:
            logging.error(f"Missing required content intelligence field: {field}")
            return False

    # Validate top_3_themes is a list
    top_3_themes = content_intelligence.get("top_3_themes", [])
    if not isinstance(top_3_themes, list):
        logging.error("top_3_themes should be a list")
        return False

    # Validate writing_dna structure
    writing_dna = content_intelligence.get("writing_dna", {})
    if not isinstance(writing_dna, dict):
        logging.error("writing_dna should be a dictionary")
        return False

    # Validate winning_formulas structure
    winning_formulas = content_intelligence.get("winning_formulas", {})
    if not isinstance(winning_formulas, dict):
        logging.error("winning_formulas should be a dictionary")
        return False

    logging.info("Core beliefs and perspectives extraction output validation passed")
    return True


# --- Main Execution ---
if __name__ == "__main__":
    try:
        asyncio.run(main_test_core_beliefs_perspectives_extraction())
    except KeyboardInterrupt:
        print("\nExecution interrupted.")
    except Exception as e:
        print(f"\nError running test: {e}")
        logging.error(f"Error running test: {e}") 