"""
Blog Content Playbook Generation Workflow

This workflow generates a comprehensive blog content playbook by:
- Loading company blog documents
- Selecting relevant content plays based on company context
- Creating detailed implementation strategies for each play
- Providing actionable recommendations and timelines

Key Features:
- Automatic play selection based on company profile
- Human-in-the-loop approval for play selection and playbook review
- Document search integration for informed recommendations
- Structured playbook output with implementation details
"""

from typing import Dict, Any, List, Optional
import asyncio
import logging
import json
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import workflow testing utilities
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

    # Import document model constants
from kiwi_client.workflows.active.document_models.customer_docs import (
    BLOG_COMPANY_DOCNAME,
    BLOG_COMPANY_NAMESPACE_TEMPLATE,
    BLOG_COMPANY_IS_SHARED,
    BLOG_COMPANY_IS_VERSIONED,
    BLOG_COMPANY_IS_SYSTEM_ENTITY,
    BLOG_CONTENT_STRATEGY_DOCNAME,
    BLOG_CONTENT_STRATEGY_NAMESPACE_TEMPLATE,
    BLOG_CONTENT_STRATEGY_IS_VERSIONED,
    BLOG_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
    BLOG_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE,
    BLOG_CONTENT_DIAGNOSTIC_REPORT_IS_VERSIONED,
    BLOG_CONTENT_DIAGNOSTIC_REPORT_IS_SHARED,
    BLOG_CONTENT_DIAGNOSTIC_REPORT_IS_SYSTEM_ENTITY,
    BLOG_CONTENT_STRATEGY_IS_SHARED
)

# Import LLM inputs
from kiwi_client.workflows.active.playbook.llm_inputs.blog_content_playbook_generation import (
    # System prompts
    PLAY_SELECTION_SYSTEM_PROMPT,
    PLAYBOOK_GENERATOR_SYSTEM_PROMPT,
    FEEDBACK_MANAGEMENT_SYSTEM_PROMPT_TEMPLATE,
    
    # User prompt templates
    PLAY_SELECTION_USER_PROMPT_TEMPLATE,
    PLAY_SELECTION_REVISION_USER_PROMPT_TEMPLATE,
    FEEDBACK_MANAGEMENT_PROMPT_TEMPLATE,
    PLAYBOOK_GENERATOR_USER_PROMPT_TEMPLATE,
    PLAYBOOK_GENERATOR_REVISION_PROMPT_TEMPLATE,
    ENHANCED_FEEDBACK_PROMPT_TEMPLATE,
    ADDITIONAL_FEEDBACK_USER_PROMPT_TEMPLATE,
    
    # Output schemas
    PLAY_SELECTION_OUTPUT_SCHEMA,
    FEEDBACK_MANAGEMENT_OUTPUT_SCHEMA,
    PLAYBOOK_GENERATOR_OUTPUT_SCHEMA
)

# Configuration constants
LLM_PROVIDER = "openai"  # anthropic    openai
LLM_MODEL = "gpt-5"  # o4-mini   gpt-4.1    claude-sonnet-4-20250514
TEMPERATURE = 0.7
MAX_TOKENS = 8000
MAX_TOOL_CALLS = 25  # Maximum total tool calls allowed
MAX_FEEDBACK_ITERATIONS = 30  # Maximum LLM loop iterations # Maximum feedback loops to prevent infinite iterations

MAX_TOKENS_FOR_TOOLS = 10000
LLM_PROVIDER_FOR_TOOLS = "openai"  # anthropic    openai
LLM_MODEL_FOR_TOOLS = "gpt-5"  # o4-mini   gpt-4.1    claude-sonnet-4-20250514

CONFIG = [
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 1: The Problem Authority Stack"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_problem_authority_stack",
    "play_name": "The Problem Authority Stack",
    "description": "Become the definitive expert on the problem before selling the solution. This play focuses on comprehensively documenting every aspect of a business problem - its causes, costs, variations, and evolution - to become the trusted advisor before ever mentioning your product. It captures prospects earlier in their journey when they're still trying to understand their challenge.",
    "perfect_for": [
      "Seed/Series A companies still validating product-market fit",
      "Companies entering new markets or segments", 
      "Founders who identified a problem through personal experience",
      "Products solving poorly understood or emerging problems"
    ],
    "when_to_use": [
      "When prospects struggle to understand/articulate their challenge",
      "When you have deep insights into problem causes and variations",
      "When competitors focus on solutions without addressing root problems",
      "When you need to capture prospects earlier in their journey"
    ],
    "success_metrics": [
      "Ranking for 50%+ of \"[problem]\" related queries within 90 days",
      "AI visibility score increasing from 0% to 25% for problem queries",
      "Inbound leads asking about solutions (not just problems)",
      "Industry recognition as problem expert (speaking invitations, media quotes)"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 2: The Category Pioneer Manifesto"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_category_pioneer_manifesto",
    "play_name": "The Category Pioneer Manifesto",
    "description": "Create and own a new category by defining its vocabulary, vision, and values. This play establishes new terminology, frameworks, and mental models that become industry standard, positioning you as the visionary who saw the opportunity first and making your category terminology the default industry vocabulary.",
    "perfect_for": [
      "Companies with genuinely new approaches",
      "Products that don't fit existing categories",
      "Visionary founders with strong perspectives",
      "Markets ready for disruption"
    ],
    "when_to_use": [
      "When creating new category definitions and terminology",
      "When existing categories don't capture your innovation",
      "When you want to establish new mental models in the market",
      "When you can balance education with evangelism effectively"
    ],
    "success_metrics": [
      "Your terminology appearing in competitor content",
      "Media using your category definition",
      "AI systems citing your manifesto when explaining the category",
      "Conference tracks dedicated to your category"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 3: The David vs Goliath Playbook"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_david_vs_goliath_playbook",
    "play_name": "The David vs Goliath Playbook",
    "description": "Win by systematically highlighting what incumbents structurally cannot or will not do. This play identifies and exploits the structural disadvantages of large competitors (technical debt, slow decision-making, innovator's dilemma) through content that positions your agility and innovation against their inertia.",
    "perfect_for": [
      "Startups competing against established players",
      "Companies with 10x better user experience",
      "Products built on modern architecture vs legacy systems",
      "Founders with insider knowledge of incumbent weaknesses"
    ],
    "when_to_use": [
      "When facing well-funded, established competitors",
      "When you have clear structural advantages (speed, innovation, architecture)",
      "When market sentiment favors underdogs",
      "When incumbents have innovator's dilemma challenges"
    ],
    "success_metrics": [
      "15%+ visibility for \"[competitor] alternative\" searches",
      "Customer switching stories and testimonials",
      "Competitor forced to respond to your messaging",
      "Media picking up David vs Goliath narrative"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 4: The Practitioner's Handbook"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_practitioners_handbook",
    "play_name": "The Practitioner's Handbook",
    "description": "Share tactical, in-the-trenches expertise so deep that it becomes the industry's operational bible. Rather than high-level thought leadership, this creates content that practitioners bookmark, share, and reference daily, demonstrating real expertise through teaching rather than just marketing claims.",
    "perfect_for": [
      "Technical founding teams",
      "Complex products requiring deep expertise",
      "Developer tools or technical platforms",
      "Companies with strong engineering cultures"
    ],
    "when_to_use": [
      "When you have unprecedented technical depth",
      "When your team can create content competitors' marketers can't replicate",
      "When practitioners need detailed, bookmark-worthy resources",
      "When you want to demonstrate expertise through teaching, not claiming"
    ],
    "success_metrics": [
      "Featured snippets for technical queries",
      "GitHub stars on related repositories",
      "Technical community recognition",
      "Conference workshop invitations"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 5: The Use Case Library"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_use_case_library",
    "play_name": "The Use Case Library",
    "description": "Create comprehensive playbooks for every possible application of your product. This play solves the problem of versatile products struggling with buyer uncertainty by creating detailed, tactical guides for every use case, making the path from interest to implementation crystal clear.",
    "perfect_for": [
      "Platform products with multiple applications",
      "Tools serving diverse buyer personas",
      "Products where success varies by use case",
      "Companies with strong customer segmentation"
    ],
    "when_to_use": [
      "When versatile products struggle with buyer uncertainty",
      "When you need to reduce implementation risk perception",
      "When you have clear use case segmentation",
      "When buyers can't envision specific applications"
    ],
    "success_metrics": [
      "Dominating \"[product] for [use case]\" searches",
      "Reduced sales cycle for specific use cases",
      "Higher conversion rates by use case",
      "Template download numbers"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 6: The Migration Magnet"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_migration_magnet",
    "play_name": "The Migration Magnet",
    "description": "Become the trusted guide for customers ready to leave your competitors. This play captures the 30-40% of SaaS customers considering switching at any given time by addressing every concern, question, and objection about migration, positioning you as the obvious choice for those ready to move.",
    "perfect_for": [
      "Later entrants to established markets",
      "Products competing against legacy solutions",
      "Companies with clear migration advantages",
      "Strong competitive positioning"
    ],
    "when_to_use": [
      "When 30-40% of competitor customers are considering switching",
      "When you have migration expertise and success stories",
      "When you can provide valuable guidance regardless of vendor choice",
      "When you want to capture highest-intent prospects"
    ],
    "success_metrics": [
      "40%+ visibility for migration-related searches",
      "Migration guide becoming industry resource",
      "Competitor customers reaching out proactively",
      "Shortened migration sales cycles"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 7: The Integration Authority"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_integration_authority",
    "play_name": "The Integration Authority",
    "description": "Own the knowledge layer of how your product connects with everything else. In the API economy, this play establishes you as the expert on not just your product, but how it fits into the broader tech stack, solving integration anxiety and demonstrating technical sophistication.",
    "perfect_for": [
      "API-first products",
      "Platform businesses",
      "Products requiring multiple integrations",
      "Technical buyer personas"
    ],
    "when_to_use": [
      "When success depends on ecosystem connectivity",
      "When integration anxiety is a buying barrier",
      "When you need to demonstrate technical sophistication",
      "When your API/platform strategy is core to growth"
    ],
    "success_metrics": [
      "Top results for \"[product] + [tool]\" searches",
      "Developer community engagement",
      "Integration partner inquiries",
      "API usage growth"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 8: The Vertical Dominator"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_vertical_dominator",
    "play_name": "The Vertical Dominator",
    "description": "Achieve category leadership by becoming the undisputed expert for one specific industry. This play focuses all content effort on dominating one vertical, speaking their language, understanding their unique challenges, and becoming their obvious choice through deep specialization.",
    "perfect_for": [
      "Horizontal products choosing a beachhead",
      "Companies with early traction in one vertical",
      "Founders with specific industry expertise",
      "Markets with unique vertical requirements"
    ],
    "when_to_use": [
      "When horizontal messaging feels generic",
      "When you can speak industry-specific language deeply",
      "When vertical has unique compliance/workflow needs",
      "When you want to become the obvious choice for one segment"
    ],
    "success_metrics": [
      "Dominating \"[industry] + [function]\" searches",
      "Industry conference speaking invitations",
      "Industry publication coverage",
      "Vertical-specific partnership inquiries"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 9: The Customer Intelligence Network"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_customer_intelligence_network",
    "play_name": "The Customer Intelligence Network",
    "description": "Transform aggregated customer insights into unique, valuable content. This play leverages your customer base as a unique data asset, aggregating anonymized insights, benchmarks, and patterns to create content competitors can't replicate while positioning your platform as the intelligence hub.",
    "perfect_for": [
      "Products with network effects",
      "Platforms with rich usage data",
      "B2B SaaS with benchmark potential",
      "Community-driven products"
    ],
    "when_to_use": [
      "When you have unique data assets from customer base",
      "When you can create insights competitors can't replicate",
      "When network effects drive product value",
      "When exclusive intelligence creates FOMO for non-customers"
    ],
    "success_metrics": [
      "Media citations of your data",
      "Benchmark report download numbers",
      "Non-customer engagement rates",
      "Network growth acceleration"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 10: The Research Engine"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_research_engine",
    "play_name": "The Research Engine",
    "description": "Generate original research that becomes required reading in your industry. By investing in studies, surveys, and analysis that others won't or can't do, you become a primary source that others must cite, creating scarcity value through unique insights available nowhere else.",
    "perfect_for": [
      "Companies with research budgets",
      "Products generating unique data",
      "Analytical founding teams",
      "Industries hungry for data"
    ],
    "when_to_use": [
      "When you can invest in original studies and surveys",
      "When you want to become a primary source that others cite",
      "When your data generates unique market insights",
      "When you can create content moats through research"
    ],
    "success_metrics": [
      "Academic and media citations",
      "Industry report references",
      "\"According to [Company]\" in content",
      "Research partnership inquiries"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 11: The Remote Revolution Handbook"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_remote_revolution_handbook",
    "play_name": "The Remote Revolution Handbook",
    "description": "Own the transformation to distributed work in your specific domain. This play positions you as the guide for remote work transformation by addressing both tactical and strategic challenges of distributed teams while positioning your solution as essential for remote success.",
    "perfect_for": [
      "Collaboration tools",
      "Productivity platforms",
      "Async-first products",
      "Companies enabling remote work"
    ],
    "when_to_use": [
      "When remote work transformation affects your domain",
      "When you enable distributed team success",
      "When you can address both tactical and strategic remote challenges",
      "When async/remote is core to your value proposition"
    ],
    "success_metrics": [
      "\"Remote [function]\" search dominance",
      "Remote work community engagement",
      "Partnership with remote work advocates",
      "Geographic market expansion"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 12: The Maturity Model Master"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_maturity_model_master",
    "play_name": "The Maturity Model Master",
    "description": "Guide organizations through every stage of sophistication in your domain. This play creates content for each organizational evolution stage, helping prospects self-diagnose and see the path forward, making you the natural partner for long-term transformation journeys.",
    "perfect_for": [
      "Transformation products",
      "Platform solutions",
      "Consultative sales processes",
      "Multiple buyer stages"
    ],
    "when_to_use": [
      "When organizations evolve through predictable stages",
      "When you need to meet buyers where they are",
      "When you want to show the path forward",
      "When you have solutions for different maturity levels"
    ],
    "success_metrics": [
      "Assessment tool completion rates",
      "Content journey tracking",
      "Sales using maturity model",
      "Partner adoption of framework"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 13: The Community-Driven Roadmap"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_community_driven_roadmap",
    "play_name": "The Community-Driven Roadmap",
    "description": "Turn product development transparency into content and community loyalty. This play makes product development public, turning your roadmap into content while building community investment by making users feel heard and involved in the product's evolution.",
    "perfect_for": [
      "PLG companies",
      "Strong user communities",
      "Transparent cultures",
      "Rapid iteration products"
    ],
    "when_to_use": [
      "When you have strong user community engagement",
      "When transparency aligns with company culture",
      "When users want to feel involved in product evolution",
      "When community feedback drives product decisions"
    ],
    "success_metrics": [
      "Community engagement rates",
      "Feature adoption rates",
      "User-generated content volume",
      "Reduced churn from transparency"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 14: The Enterprise Translator"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_enterprise_translator",
    "play_name": "The Enterprise Translator",
    "description": "Bridge the gap between startup agility and enterprise requirements. This play creates content that demonstrates enterprise readiness without losing innovation edge, addressing enterprise concerns proactively while highlighting agility advantages for upmarket expansion.",
    "perfect_for": [
      "Series B+ moving upmarket",
      "Adding enterprise features",
      "Competing for larger deals",
      "Security/compliance focus"
    ],
    "when_to_use": [
      "When moving from SMB to enterprise market",
      "When you need to demonstrate enterprise readiness",
      "When enterprise buyers have specific concerns about startup vendors",
      "When you want to maintain innovation edge while showing stability"
    ],
    "success_metrics": [
      "Enterprise lead quality",
      "Deal size increases",
      "Security review pass rates",
      "Enterprise logo acquisition"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 15: The Ecosystem Architect"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_ecosystem_architect",
    "play_name": "The Ecosystem Architect",
    "description": "Build gravity by enabling partner success through content. This play creates content that attracts, enables, and celebrates partners while building network effects, making partner success easier and more visible to create gravitational pull for ecosystem participation.",
    "perfect_for": [
      "Platform businesses",
      "API-first companies",
      "Channel strategies",
      "Developer ecosystems"
    ],
    "when_to_use": [
      "When platform success depends on ecosystem health",
      "When you want to attract and enable partners",
      "When network effects drive business value",
      "When partner success creates competitive moats"
    ],
    "success_metrics": [
      "Partner application rates",
      "Ecosystem transaction volume",
      "Partner-generated revenue",
      "Developer community growth"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 16: The AI Specialist"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_ai_specialist",
    "play_name": "The AI Specialist",
    "description": "Demonstrate domain-specific AI expertise beyond generic AI hype. This play shows deep understanding of AI applications in your specific domain, moving beyond buzzwords to practical, industry-specific AI implementation guidance that helps organizations navigate AI adoption.",
    "perfect_for": [
      "AI-powered products",
      "AI features in traditional products",
      "Industries with AI skepticism",
      "Regulated AI use cases"
    ],
    "when_to_use": [
      "When you have genuine AI expertise beyond marketing claims",
      "When your industry has specific AI applications and challenges",
      "When AI regulatory compliance is important",
      "When you need to differentiate from generic AI buzz"
    ],
    "success_metrics": [
      "AI + industry search rankings",
      "Thought leadership recognition",
      "Advisory board invitations",
      "Enterprise AI deals"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 17: The Efficiency Engine"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_efficiency_engine",
    "play_name": "The Efficiency Engine",
    "description": "Become the authority on doing more with less during economic uncertainty. This play positions you as the expert on optimization, cost reduction, and productivity improvement, providing concrete ROI evidence during budget-conscious times while demonstrating deep understanding of operational efficiency.",
    "perfect_for": [
      "Cost reduction value props",
      "Automation products",
      "Productivity tools",
      "CFO-targeted solutions"
    ],
    "when_to_use": [
      "During economic downturns or budget constraints",
      "When ROI and efficiency are top buyer concerns",
      "When you can provide concrete cost reduction evidence",
      "When CFOs are key decision makers"
    ],
    "success_metrics": [
      "CFO/finance engagement",
      "ROI calculator usage",
      "Budget holder leads",
      "Economic downturn resilience"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 18: The False Start Chronicles"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_false_start_chronicles",
    "play_name": "The False Start Chronicles",
    "description": "Build credibility by publicly analyzing why previous attempts at solving your problem failed. This play shows you understand not just the opportunity but the pitfalls, demonstrating market timing awareness and learning from history to position yourself as the solution that learned from past mistakes.",
    "perfect_for": [
      "Spaces with notable failures",
      "\"Why now\" positioning needed",
      "Skeptical investors/customers",
      "Timing-dependent solutions"
    ],
    "when_to_use": [
      "When entering markets with previous failures",
      "When timing and market readiness are critical",
      "When you need to address \"why will you succeed when others failed\"",
      "When you have insights into previous failure patterns"
    ],
    "success_metrics": [
      "Investor confidence metrics",
      "Media coverage quality",
      "Customer objection reduction",
      "\"Why now\" clarity"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 19: The Compliance Simplifier"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_compliance_simplifier",
    "play_name": "The Compliance Simplifier",
    "description": "Demystify complex regulations while demonstrating your compliance expertise. This play shows deep regulatory knowledge while making compliance approachable and manageable, reducing compliance anxiety and demonstrating you've already solved the hard regulatory problems.",
    "perfect_for": [
      "Fintech/healthtech/govtech",
      "Compliance as differentiator",
      "Risk-averse buyers",
      "Complex regulatory environments"
    ],
    "when_to_use": [
      "When operating in heavily regulated industries",
      "When compliance anxiety is a buying barrier",
      "When regulatory expertise is a competitive advantage",
      "When you've solved complex compliance challenges"
    ],
    "success_metrics": [
      "Compliance query rankings",
      "Regulated industry leads",
      "Audit success rates",
      "Trust signal improvement"
    ]
  },
  {
    "load_config": {
      "filename_config": {
        "static_namespace": "blog_playbook_sys",
        "static_docname": "Play 20: The Talent Magnet"
      },
      "output_field_name": "playbook",
      "is_shared": True,
      "is_system_entity": True
    },
    "play_id": "the_talent_magnet",
    "play_name": "The Talent Magnet",
    "description": "Use technical content to attract the scarce engineering talent you need. This play creates content that showcases interesting technical challenges, engineering culture, and growth opportunities, attracting engineers who want to work on meaningful, complex technical challenges through authentic technical content.",
    "perfect_for": [
      "High-growth technical companies",
      "Competitive talent markets",
      "Engineering-first cultures",
      "Unique technical challenges"
    ],
    "when_to_use": [
      "When talent acquisition is critical for growth",
      "When you're solving interesting technical problems",
      "When engineering brand affects recruiting",
      "When you compete for top technical talent"
    ],
    "success_metrics": [
      "Quality of applicants",
      "Engineering brand strength",
      "Reduced recruiting costs",
      "Technical community engagement"
    ]
  }
]

# Workflow JSON structure
workflow_graph_schema = {
    "nodes": {
        # 1. Input Node - No input required
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "company_name": {
                        "type": "str",
                        "required": True,
                        "description": "Entity username for document operations"
                    },
                    "playbook_selection_config": {
                        "type": "list",
                        "required": False,
                        "default": CONFIG,
                        "description": "Configuration for the playbook generation"
                    }
                }
            }
        },
        
        # 2. Load Company Blog Documents
        "load_company_doc": {
            "node_id": "load_company_doc",
            "node_name": "load_customer_data",
            "node_config": {
                "load_paths": [
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": BLOG_COMPANY_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": BLOG_COMPANY_DOCNAME,
                        },
                        "output_field_name": "company_doc"
                    },
                    {
                        "filename_config": {
                            "input_namespace_field_pattern": BLOG_CONTENT_DIAGNOSTIC_REPORT_NAMESPACE_TEMPLATE,
                            "input_namespace_field": "company_name",
                            "static_docname": BLOG_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
                        },
                        "output_field_name": "diagnostic_report_doc"
                    }
                ],
                "global_is_shared": False,
                "global_is_system_entity": False,
                "global_schema_options": {"load_schema": False}
            }
        },
        
        # 3. Extract Playbooks (from CONFIG) - Filter to play metadata fields
        "extract_playbooks": {
            "node_id": "extract_playbooks",
            "node_name": "filter_data",
            "node_config": {
                "targets": [
                    {
                        "filter_target": "playbook_selection_config.play_id",
                        "filter_mode": "allow",
                        "condition_groups": [
                            { "conditions": [ { "field": "playbook_selection_config.play_id", "operator": "is_not_empty" } ], "logical_operator": "and" }
                        ],
                        "group_logical_operator": "and"
                    },
                    {
                        "filter_target": "playbook_selection_config.play_name",
                        "filter_mode": "allow",
                        "condition_groups": [
                            { "conditions": [ { "field": "playbook_selection_config.play_name", "operator": "is_not_empty" } ], "logical_operator": "and" }
                        ],
                        "group_logical_operator": "and"
                    },
                    {
                        "filter_target": "playbook_selection_config.description",
                        "filter_mode": "allow",
                        "condition_groups": [
                            { "conditions": [ { "field": "playbook_selection_config.description", "operator": "is_not_empty" } ], "logical_operator": "and" }
                        ],
                        "group_logical_operator": "and"
                    },
                    # {
                    #     "filter_target": "playbook_selection_config.perfect_for",
                    #     "filter_mode": "allow",
                    #     "condition_groups": [
                    #         { "conditions": [ { "field": "playbook_selection_config.perfect_for", "operator": "is_not_empty" } ], "logical_operator": "and" }
                    #     ],
                    #     "group_logical_operator": "and"
                    # },
                    # {
                    #     "filter_target": "playbook_selection_config.when_to_use",
                    #     "filter_mode": "allow",
                    #     "condition_groups": [
                    #         { "conditions": [ { "field": "playbook_selection_config.when_to_use", "operator": "is_not_empty" } ], "logical_operator": "and" }
                    #     ],
                    #     "group_logical_operator": "and"
                    # },
                    # {
                    #     "filter_target": "playbook_selection_config.success_metrics",
                    #     "filter_mode": "allow",
                    #     "condition_groups": [
                    #         { "conditions": [ { "field": "playbook_selection_config.success_metrics", "operator": "is_not_empty" } ], "logical_operator": "and" }
                    #     ],
                    #     "group_logical_operator": "and"
                    # }
                ],
                "non_target_fields_mode": "deny"
            }
        },
        
        # 3. Play Selection - Prompt Constructor
        "construct_play_selection_prompt": {
            "node_id": "construct_play_selection_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "play_selection_user_prompt": {
                        "id": "play_selection_user_prompt",
                        "template": PLAY_SELECTION_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "company_info": None,
                            "diagnostic_report_info": None
                        },
                        "construct_options": {
                            "company_info": "company_doc",
                            "diagnostic_report_info": "diagnostic_report_doc",
                        }
                    },
                    "play_selection_system_prompt": {
                        "id": "play_selection_system_prompt",
                        "template": PLAY_SELECTION_SYSTEM_PROMPT,
                        "variables": {
                            "available_playbooks": None
                        },
                        "construct_options": {
                            "available_playbooks": "available_playbooks"
                        }
                    }
                }
            }
        },
        
        # 4. Play Selection - LLM Node
        "play_suggestion_llm": {
            "node_id": "play_suggestion_llm",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER,
                        "model": LLM_MODEL
                    },
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS,
                    # "reasoning_tokens_budget":2000
                    # "reasoning_effort_class": "low"
                },
                "output_schema": {
                    "schema_definition": PLAY_SELECTION_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 4.b Validate Play IDs
        "validate_play_ids": {
            "node_id": "validate_play_ids",
            "node_name": "if_else_condition",
            "node_config": {
                "tagged_conditions": [
                    {
                        "tag": "selected_ids_valid",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "structured_output.selected_plays.play_id",
                                "operator": "equals_any_of",
                                "value_path": "playbook_selection_config.play_id",
                                "apply_to_each_value_in_list_field": True,
                                "list_field_logical_operator": "and"
                            }],
                            "logical_operator": "and"
                        }],
                        "group_logical_operator": "and",
                        "nested_list_logical_operator": "and"
                    }
                ],
                "branch_logic_operator": "and"
            }
        },
        
        # 4.c Route based on validation
        "route_play_id_validation": {
            "node_id": "route_play_id_validation",
            "node_name": "router_node",
            "node_config": {
                "choices": ["filter_playbook_selection_config", "construct_play_id_correction_prompt"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "filter_playbook_selection_config",
                        "input_path": "ids_valid",
                        "target_value": True
                    },
                    {
                        "choice_id": "construct_play_id_correction_prompt",
                        "input_path": "ids_valid",
                        "target_value": False
                    }
                ],
                "default_choice": "construct_play_id_correction_prompt"
            }
        },
        
        # 4.d Construct Play ID Correction Prompt
        "construct_play_id_correction_prompt": {
            "node_id": "construct_play_id_correction_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "play_id_correction_user_prompt": {
                        "id": "play_id_correction_user_prompt",
                        "template": "Some selected plays have missing or incorrect play_id values.\n\nPlease verify and correct them using the lowercase_underscore convention that exactly matches the play names.\n\nInstructions:\n- Compare the final selected plays against the available plays list\n- For each play, set play_id to its name in lowercase with underscores (e.g., \"The Problem Authority Stack\" -> \"the_problem_authority_stack\")\n- Reply with a JSON array of corrections like:\n[\n  \"play_name\": \"The Problem Authority Stack\", \"play_id\": \"the_problem_authority_stack\"\n]\n\nAvailable Plays:\n{playbook_selection_config}",
                        "variables": {
                            "playbook_selection_config": None
                        },
                        "construct_options": {
                            "playbook_selection_config": "playbook_selection_config"
                        }
                    }
                }
            }
        },

        # 4.d.i Filter Playbook Selection Config (remove load_config)
        "filter_playbook_selection_config": {
            "node_id": "filter_playbook_selection_config",
            "node_name": "filter_data",
            "node_config": {
                "targets": [
                    {
                        "filter_target": "playbook_selection_config.play_id",
                        "filter_mode": "allow",
                        "condition_groups": [
                            {
                                "conditions": [
                                    { "field": "playbook_selection_config.play_id", "operator": "is_not_empty" }
                                ],
                                "logical_operator": "and"
                            }
                        ],
                        "group_logical_operator": "and"
                    },
                    {
                        "filter_target": "playbook_selection_config.play_name",
                        "filter_mode": "allow",
                        "condition_groups": [
                            {
                                "conditions": [
                                    { "field": "playbook_selection_config.play_name", "operator": "is_not_empty" }
                                ],
                                "logical_operator": "and"
                            }
                        ],
                        "group_logical_operator": "and"
                    },
                    {
                        "filter_target": "playbook_selection_config.description",
                        "filter_mode": "allow",
                        "condition_groups": [
                            {
                                "conditions": [
                                    { "field": "playbook_selection_config.description", "operator": "is_not_empty" }
                                ],
                                "logical_operator": "and"
                            }
                        ],
                        "group_logical_operator": "and"
                    }
                ],
                "non_target_fields_mode": "deny"
            }
        },
        
        # 4.e Join Play Metadata
        "join_play_metadata": {
            "node_id": "join_play_metadata",
            "node_name": "data_join_data",
            "node_config": {
                "joins": [
                    {
                        "primary_list_path": "filtered_data.playbook_selection_config",
                        "secondary_list_path": "selected_plays.selected_plays",
                        "primary_join_key": "play_id",
                        "secondary_join_key": "play_id",
                        "output_nesting_field": "selection_reasoning",
                        "join_type": "one_to_one"
                    }
                ]
            }
        },
        
        # 4.e.ii Filter Joined Plays With Reasoning
        "filter_joined_plays_with_reasoning": {
            "node_id": "filter_joined_plays_with_reasoning",
            "node_name": "filter_data",
            "node_config": {
                "targets": [
                    {
                        "filter_target": "mapped_data.filtered_data.playbook_selection_config",
                        "filter_mode": "allow",
                        "condition_groups": [
                            {
                                "conditions": [
                                    { "field": "mapped_data.filtered_data.playbook_selection_config.selection_reasoning", "operator": "is_not_empty" }
                                ],
                                "logical_operator": "and"
                            }
                        ],
                        "group_logical_operator": "and"
                    }
                ],
                "non_target_fields_mode": "deny"
            }
        },
        
        # 4.e.iii Flatten Play Recommendations
        "flatten_play_recommendations": {
            "node_id": "flatten_play_recommendations",
            "node_name": "transform_data",
            "node_config": {
                "merge_conflicting_paths_as_list": False,
                "mappings": [
                    { "source_path": "input_data.mapped_data.filtered_data.playbook_selection_config", "destination_path": "play_recommendations" }
                ]
            }
        },
        
        # 5. Play Selection HITL
        "play_selection_hitl": {
            "node_id": "play_selection_hitl",
            "node_name": "hitl_node__default",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "user_action": {
                        "type": "enum",
                        "enum_values": ["approve_plays", "revise_plays", "cancel_workflow"],
                        "required": True,
                        "description": "User's decision on the selected plays"
                    },
                    "feedback": {
                        "type": "str",
                        "required": False,
                        "description": "User feedback for play modifications"
                    },
                    "final_selected_plays": {
                        "type": "list",
                        "required": False,
                        "description": "Final list of plays approved/modified by user"
                    }
                }
            }
        },
        
        # 6. Route Play Selection
        "route_play_selection": {
            "node_id": "route_play_selection", 
            "node_name": "router_node",
            "node_config": {
                "choices": ["filter_plays_data", "construct_play_selection_revision_prompt", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "filter_plays_data",
                        "input_path": "user_action",
                        "target_value": "approve_plays"
                    },
                    {
                        "choice_id": "construct_play_selection_revision_prompt",
                        "input_path": "user_action",
                        "target_value": "revise_plays"
                    },
                    {
                        "choice_id": "output_node",
                        "input_path": "user_action",
                        "target_value": "cancel_workflow"
                    }
                ],
                "default_choice": "output_node"
            }
        },
        
        # 7. Play Selection Revision - Prompt Constructor
        "construct_play_selection_revision_prompt": {
            "node_id": "construct_play_selection_revision_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "play_selection_revision_user_prompt": {
                        "id": "play_selection_revision_user_prompt",
                        "template": PLAY_SELECTION_REVISION_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "user_feedback": None,
                            "previous_recommendations": None
                        },
                        "construct_options": {
                            "user_feedback": "user_feedback",
                            "previous_recommendations": "selected_plays"
                        }
                    }
                }
            }
        },
        
        # 8. Filter Plays Data
        "filter_plays_data": {
            "node_id": "filter_plays_data",
            "node_name": "filter_data",
            "node_config": {
                "targets": [
                    {
                        "filter_target": "playbook_selection_config",
                        "filter_mode": "allow",
                        "condition_groups": [
                            {
                                "conditions": [
                                    {
                                        "field": "playbook_selection_config.play_id",
                                        "operator": "equals_any_of",
                                        "value_path": "approved_plays.play_id"
                                    }
                                ],
                                "logical_operator": "and"
                            }
                        ],
                        "group_logical_operator": "and",
                        "nested_list_logical_operator": "and"
                    },
                ],
                "non_target_fields_mode": "deny"
            }
        },

        # 9. Prepare Load Configs (transform filtered structure to flat list)
        "prepare_load_configs": {
            "node_id": "prepare_load_configs",
            "node_name": "transform_data",
            "node_config": {
                "merge_conflicting_paths_as_list": False,
                "mappings": [
                    { "source_path": "available_playbooks.playbook_selection_config.load_config", "destination_path": "load_configs" }
                ]
            }
        },
        # 10. Load Playbooks
        "load_selected_playbooks": {
            "node_id": "load_selected_playbooks",
            "node_name": "load_customer_data",
            "node_config": {
                "load_configs_input_path": "available_playbooks.load_configs",
                "global_is_shared": True,
                "global_is_system_entity": True,
                "global_schema_options": {"load_schema": False},
            }
            
        },
        
        # 15. Playbook Generator - Prompt Constructor
        "construct_playbook_generator_prompt": {
            "node_id": "construct_playbook_generator_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "playbook_generator_user_prompt": {
                        "id": "playbook_generator_user_prompt",
                        "template": PLAYBOOK_GENERATOR_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "fetched_information": None,
                            "company_info": None,
                            "diagnostic_report_info": None
                        },
                        "construct_options": {
                            "fetched_information": "fetched_information",
                            "company_info": "company_doc",
                            "diagnostic_report_info": "diagnostic_report_doc",
                            "approved_plays": "approved_plays"
                        }
                    },
                    "playbook_generator_system_prompt": {
                        "id": "playbook_generator_system_prompt",
                        "template": PLAYBOOK_GENERATOR_SYSTEM_PROMPT,
                        "variables": {}
                    }
                }
            }
        },
        
        # 16. Playbook Generator - LLM Node (no tools, just synthesis)
        "playbook_generator_llm": {
            "node_id": "playbook_generator_llm",
            "node_name": "llm", 
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER,
                        "model": LLM_MODEL
                    },
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS,
                    "verbosity": "high"
                },
                "output_schema": {
                    "schema_definition": PLAYBOOK_GENERATOR_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 22. Playbook Review HITL
        "playbook_review_hitl": {
            "node_id": "playbook_review_hitl",
            "node_name": "hitl_node__default",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "user_action": {
                        "type": "enum",
                        "enum_values": ["approve_playbook", "request_revisions", "cancel"],
                        "required": True,
                        "description": "User's decision on the generated playbook"
                    },
                    "revision_feedback": {
                        "type": "str",
                        "required": False,
                        "description": "Feedback for playbook revisions"
                    },
                    "generated_playbook": {
                        "type": "dict",
                        "required": True,
                        "description": "Generated playbook"
                    }
                }
            }
        },
        
        # 23. Route Playbook Review
        "route_playbook_review": {
            "node_id": "route_playbook_review",
            "node_name": "router_node",
            "node_config": {
                "choices": ["store_playbook", "check_revision_iteration", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "store_playbook",
                        "input_path": "user_action",
                        "target_value": "approve_playbook"
                    },
                    {
                        "choice_id": "check_revision_iteration",
                        "input_path": "user_action",
                        "target_value": "request_revisions"
                    },
                    {
                        "choice_id": "output_node",
                        "input_path": "user_action",
                        "target_value": "cancel"
                    }
                ],
                "default_choice": "output_node"
            }
        },
        
        # 24.a Check Revision Iteration (initial vs additional)
        "check_revision_iteration": {
            "node_id": "check_revision_iteration",
            "node_name": "if_else_condition",
            "node_config": {
                "tagged_conditions": [
                    {
                        "tag": "is_additional_iteration",
                        "condition_groups": [{
                            "logical_operator": "and",
                            "conditions": [{
                                "field": "metadata.iteration_count",
                                "operator": "greater_than",
                                "value": 1
                            }]
                        }],
                        "group_logical_operator": "and"
                    }
                ],
                "branch_logic_operator": "and"
            }
        },
        
        # 24.b Route based on Revision Iteration
        "route_revision_iteration": {
            "node_id": "route_revision_iteration",
            "node_name": "router_node",
            "node_config": {
                "choices": ["construct_feedback_management_prompt", "construct_additional_feedback_prompt"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "construct_additional_feedback_prompt",
                        "input_path": "if_else_condition_tag_results.is_additional_iteration",
                        "target_value": True
                    },
                    {
                        "choice_id": "construct_feedback_management_prompt",
                        "input_path": "if_else_condition_tag_results.is_additional_iteration",
                        "target_value": False
                    }
                ]
            }
        },

                # 24. Feedback Management Prompt Constructor
        "construct_feedback_management_prompt": {
            "node_id": "construct_feedback_management_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "feedback_management_user_prompt": {
                        "id": "feedback_management_user_prompt",
                        "template": FEEDBACK_MANAGEMENT_PROMPT_TEMPLATE,
                        "variables": {
                            "revision_feedback": None,
                            "current_playbook": None,
                            "selected_plays": None,
                            "company_info": None,
                            "diagnostic_report_info": None,
                        },
                        "construct_options": {
                            "revision_feedback": "revision_feedback",
                            "current_playbook": "current_playbook",
                            "selected_plays": "approved_plays",
                            "company_info": "company_doc",
                            "diagnostic_report_info": "diagnostic_report_doc",
                        }
                    },
                    "feedback_management_system_prompt": {
                        "id": "feedback_management_system_prompt",
                        "template": FEEDBACK_MANAGEMENT_SYSTEM_PROMPT_TEMPLATE,
                        "variables": {
                            "available_plays_list": None
                        },
                        "construct_options": {
                            "available_plays_list": "playbook_selection_config"
                        }
                    }
                }
            }
        },
        
        # 24.c Additional Feedback Prompt Constructor (subsequent cycles)
        "construct_additional_feedback_prompt": {
            "node_id": "construct_additional_feedback_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "additional_feedback_user_prompt": {
                        "id": "additional_feedback_user_prompt",
                        "template": ADDITIONAL_FEEDBACK_USER_PROMPT_TEMPLATE,
                        "variables": {
                            "revision_feedback": None,
                            "current_playbook": None,
                        },
                        "construct_options": {
                            "revision_feedback": "revision_feedback",
                            "current_playbook": "current_playbook",
                        }
                    }
                }
            }
        },
        
        # 25. Feedback Management LLM (Central Feedback Controller)
        "feedback_management_llm": {
            "node_id": "feedback_management_llm",
            "node_name": "llm",
            "node_config": {
                "llm_config": {
                    "model_spec": {
                        "provider": LLM_PROVIDER_FOR_TOOLS,
                        "model": LLM_MODEL_FOR_TOOLS
                    },
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS_FOR_TOOLS,
                    # "reasoning_tokens_budget": 2048,
                    "reasoning_effort_class": "high"
                },
                "tool_calling_config": {
                    "enable_tool_calling": True,
                    "parallel_tool_calls": True
                },
                "tools": [
                    {
                        "tool_name": "search_documents",
                        "is_provider_inbuilt_tool": False,
                        "provider_inbuilt_user_config": {}
                    },
                    {
                        "tool_name": "view_documents",
                        "is_provider_inbuilt_tool": False,
                        "provider_inbuilt_user_config": {}
                    },
                    {
                        "tool_name": "list_documents",
                        "is_provider_inbuilt_tool": False,
                        "provider_inbuilt_user_config": {}
                    }
                ],
                "output_schema": {
                    "schema_definition": FEEDBACK_MANAGEMENT_OUTPUT_SCHEMA,
                    "convert_loaded_schema_to_pydantic": False
                }
            }
        },
        
        # 26. Check Feedback Management Action
        "check_feedback_management_action": {
            "node_id": "check_feedback_management_action",
            "node_name": "if_else_condition",
            "node_config": {
                "tagged_conditions": [
                    {
                        "tag": "has_tool_calls",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "tool_calls",
                                "operator": "is_not_empty"
                            }]
                        }]
                    },
                    {
                        "tag": "send_to_playbook_generator",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "structured_output.workflow_control.action",
                                "operator": "equals",
                                "value": "send_to_playbook_generator"
                            }]
                        }]
                    },
                    {
                        "tag": "ask_user_clarification",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "structured_output.workflow_control.action",
                                "operator": "equals",
                                "value": "ask_user_clarification"
                            }]
                        }]
                    },
                    {
                        "tag": "iteration_limit_reached",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "feedback_iteration_count",
                                "operator": "greater_than_or_equals",
                                "value": MAX_FEEDBACK_ITERATIONS
                            }]
                        }]
                    }
                ],
                "branch_logic_operator": "or"
            }
        },
        
        # 27. Route Feedback Management
        "route_feedback_management": {
            "node_id": "route_feedback_management",
            "node_name": "router_node",
            "node_config": {
                "choices": ["feedback_tool_executor", "check_play_ids_to_fetch", "feedback_clarification_hitl", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "feedback_tool_executor",
                        "input_path": "tag_results.has_tool_calls",
                        "target_value": True
                    },
                    {
                        "choice_id": "check_play_ids_to_fetch",
                        "input_path": "tag_results.send_to_playbook_generator",
                        "target_value": True
                    },
                    {
                        "choice_id": "feedback_clarification_hitl",
                        "input_path": "tag_results.ask_user_clarification",
                        "target_value": True
                    },
                    {
                        "choice_id": "output_node",
                        "input_path": "tag_results.iteration_limit_reached",
                        "target_value": True
                    }
                ],
                "default_choice": "output_node"
            }
        },
        
        # 28. Feedback Tool Executor
        "feedback_tool_executor": {
            "node_id": "feedback_tool_executor",
            "node_name": "tool_executor",
            "node_config": {
                "default_timeout": 30.0,
                "max_concurrent_executions": 3,
                "continue_on_error": True,
                "include_error_details": True,
                "map_executor_input_fields_to_tool_input": True
            }
        },
        
        # 30. Feedback Clarification HITL
        "feedback_clarification_hitl": {
            "node_id": "feedback_clarification_hitl",
            "node_name": "hitl_node__default",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    "user_action": {
                        "type": "enum",
                        "enum_values": ["provide_clarification", "cancel_workflow"],
                        "required": True,
                        "description": "User's response to clarification request"
                    },
                    "clarification_response": {
                        "type": "str",
                        "required": False,
                        "description": "Additional clarification from user"
                    }
                }
            }
        },
        
        # 31. Route Feedback Clarification
        "route_feedback_clarification": {
            "node_id": "route_feedback_clarification",
            "node_name": "router_node",
            "node_config": {
                "choices": ["construct_enhanced_feedback_prompt", "output_node"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "construct_enhanced_feedback_prompt",
                        "input_path": "user_action",
                        "target_value": "provide_clarification"
                    },
                    {
                        "choice_id": "output_node",
                        "input_path": "user_action",
                        "target_value": "cancel_workflow"
                    }
                ],
                "default_choice": "output_node"
            }
        },
        
        # 32. Construct Enhanced Feedback Prompt
        "construct_enhanced_feedback_prompt": {
            "node_id": "construct_enhanced_feedback_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "enhanced_feedback_prompt": {
                        "id": "enhanced_feedback_prompt",
                        "template": ENHANCED_FEEDBACK_PROMPT_TEMPLATE,
                        "variables": {
                            "revision_feedback": None,
                            "clarification_response": None
                        },
                        "construct_options": {
                            "revision_feedback": "revision_feedback",
                            "clarification_response": "clarification_response"
                        }
                    }
                }
            }
        },
        
        # 33. Construct Playbook Update Prompt
        "construct_playbook_update_prompt": {
            "node_id": "construct_playbook_update_prompt",
            "node_name": "prompt_constructor",
            "node_config": {
                "prompt_templates": {
                    "playbook_update_user_prompt": {
                        "id": "playbook_update_user_prompt",
                        "template": PLAYBOOK_GENERATOR_REVISION_PROMPT_TEMPLATE,
                        "variables": {
                            "current_playbook": None,
                            "revision_feedback": None,
                            "additional_information": None,
                            "company_info": None,
                            "additional_play_data": ""
                        },
                        "construct_options": {
                            "current_playbook": "current_playbook",
                            "revision_feedback": "revision_feedback",
                            "additional_information": "additional_information.instructions_for_playbook_generator",
                            "company_info": "company_doc",
                            "additional_play_data": "additional_play_data"
                        }
                    }
                }
            }
        },
        
        # 34. Store Playbook
        "store_playbook": {
            "node_id": "store_playbook",
            "node_name": "store_customer_data",
            "node_config": {
                "global_versioning": {
                    "is_versioned": BLOG_CONTENT_STRATEGY_IS_VERSIONED,
                    "operation": "upsert_versioned"
                },
                "global_is_shared": BLOG_CONTENT_STRATEGY_IS_SHARED,
                "store_configs": [
                    {
                        "input_field_path": "final_playbook",
                        "target_path": {
                            "filename_config": {
                                "input_namespace_field_pattern": BLOG_CONTENT_STRATEGY_NAMESPACE_TEMPLATE,
                                "input_namespace_field": "company_name",
                                "static_docname": BLOG_CONTENT_STRATEGY_DOCNAME,
                            }
                        },
                        "versioning": {
                            "is_versioned": BLOG_CONTENT_STRATEGY_IS_VERSIONED,
                            "operation": "upsert_versioned",
                            "version": "default"
                        }
                    }
                ],
            }
        },
        
        
        
        # 24.d Check Play IDs to Fetch
        "check_play_ids_to_fetch": {
            "node_id": "check_play_ids_to_fetch",
            "node_name": "if_else_condition",
            "node_config": {
                "tagged_conditions": [
                    {
                        "tag": "has_play_ids_to_fetch",
                        "condition_groups": [{
                            "conditions": [{
                                "field": "feedback_management_output.play_ids_to_fetch",
                                "operator": "is_not_empty"
                            }],
                            "logical_operator": "and"
                        }],
                        "group_logical_operator": "and"
                    }
                ],
                "branch_logic_operator": "and"
            }
        },

        # 24.e Route based on play_ids_to_fetch
        "route_play_ids_to_fetch": {
            "node_id": "route_play_ids_to_fetch",
            "node_name": "router_node",
            "node_config": {
                "choices": ["filter_plays_for_update", "construct_playbook_update_prompt"],
                "allow_multiple": False,
                "choices_with_conditions": [
                    {
                        "choice_id": "filter_plays_for_update",
                        "input_path": "tag_results.has_play_ids_to_fetch",
                        "target_value": True
                    },
                    {
                        "choice_id": "construct_playbook_update_prompt",
                        "input_path": "tag_results.has_play_ids_to_fetch",
                        "target_value": False
                    }
                ],
                "default_choice": "construct_playbook_update_prompt"
            }
        },

        # 24.f Filter Plays for Update
        "filter_plays_for_update": {
            "node_id": "filter_plays_for_update",
            "node_name": "filter_data",
            "node_config": {
                "targets": [
                    {
                        "filter_target": "playbook_selection_config",
                        "filter_mode": "allow",
                        "condition_groups": [
                            {
                                "conditions": [
                                    {
                                        "field": "playbook_selection_config.play_id",
                                        "operator": "equals_any_of",
                                        "value_path": "play_ids_to_fetch"
                                    }
                                ],
                                "logical_operator": "and"
                            }
                        ],
                        "group_logical_operator": "and",
                        "nested_list_logical_operator": "and"
                    }
                ],
                "non_target_fields_mode": "deny"
            }
        },

        # 24.g Prepare Load Configs for Update
        "prepare_load_configs_for_update": {
            "node_id": "prepare_load_configs_for_update",
            "node_name": "transform_data",
            "node_config": {
                "merge_conflicting_paths_as_list": False,
                "mappings": [
                    { "source_path": "available_playbooks.playbook_selection_config.load_config", "destination_path": "load_configs" }
                ]
            }
        },

        # 24.h Load Selected Playbooks for Update
        "load_selected_playbooks_for_update": {
            "node_id": "load_selected_playbooks_for_update",
            "node_name": "load_customer_data",
            "node_config": {
                "load_configs_input_path": "available_playbooks.load_configs",
                "global_is_shared": True,
                "global_is_system_entity": True,
                "global_schema_options": {"load_schema": False}
            }
        },

        # 35. Output Node
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {}
        },
    },
    
    "edges": [
        # Input -> State
        {
            "src_node_id": "input_node",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "playbook_selection_config", "dst_field": "playbook_selection_config"}
            ]
        },
        
        # Input -> Load Company Doc
        {
            "src_node_id": "input_node",
            "dst_node_id": "load_company_doc",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"}
            ]
        },
        
        # Input -> Extract Playbooks
        {
            "src_node_id": "input_node",
            "dst_node_id": "extract_playbooks",
            "mappings": [
                {"src_field": "playbook_selection_config", "dst_field": "playbook_selection_config"}
            ]
        },

        # Company Doc -> State
        {
            "src_node_id": "load_company_doc",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "diagnostic_report_doc", "dst_field": "diagnostic_report_doc"}
            ]
        },
        
        # Extract Playbooks -> State
        {
            "src_node_id": "extract_playbooks",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "filtered_data", "dst_field": "available_playbooks"}
            ]
        },

        {
            "src_node_id": "extract_playbooks",
            "dst_node_id": "construct_play_selection_prompt",
            "mappings": [
                {"src_field": "filtered_data", "dst_field": "available_playbooks"}
            ]
        },
        
        # Company Doc -> Play Selection Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_play_selection_prompt",
            "mappings": [
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "diagnostic_report_doc", "dst_field": "diagnostic_report_doc"}
            ]
        },
                
        # Play Selection Prompt -> LLM
        {
            "src_node_id": "construct_play_selection_prompt",
            "dst_node_id": "play_suggestion_llm",
            "mappings": [
                {"src_field": "play_selection_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "play_selection_system_prompt", "dst_field": "system_prompt"}
            ]
        },

        {
            "src_node_id": "$graph_state",
            "dst_node_id": "play_suggestion_llm",
            "mappings": [
                {"src_field": "play_suggestion_message_history", "dst_field": "messages_history"}
            ]
        },
        
        # Play Selection LLM -> State
        {
            "src_node_id": "play_suggestion_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "selected_plays"},
                {"src_field": "current_messages", "dst_field": "play_suggestion_message_history"}
            ]
        },
        
        # Play Selection LLM -> Validate Play IDs
        {
            "src_node_id": "play_suggestion_llm",
            "dst_node_id": "validate_play_ids",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "structured_output"}
            ]
        },
        # State -> Validate Play IDs (available plays list)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "validate_play_ids",
            "mappings": [
                {"src_field": "playbook_selection_config", "dst_field": "playbook_selection_config"}
            ]
        },
        # Validate -> Route Validation
        {
            "src_node_id": "validate_play_ids",
            "dst_node_id": "route_play_id_validation",
            "mappings": [
                {"src_field": "condition_result", "dst_field": "ids_valid"}
            ]
        },

        # Route Validation -> Construct Correction Prompt (invalid)
        {
            "src_node_id": "route_play_id_validation",
            "dst_node_id": "filter_playbook_selection_config"
        },
        # Route Validation -> Filter Playbook Selection Config (for correction prompt path)
        {
            "src_node_id": "route_play_id_validation",
            "dst_node_id": "construct_play_id_correction_prompt"
        },
        # State -> Construct Correction Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_play_id_correction_prompt",
            "mappings": [
                {"src_field": "playbook_selection_config", "dst_field": "playbook_selection_config"}
            ]
        },
        # State -> Filter Playbook Selection Config (input data)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "filter_playbook_selection_config",
            "mappings": [
                {"src_field": "playbook_selection_config", "dst_field": "playbook_selection_config"}
            ]
        },
        # Filtered Selection -> Construct Correction Prompt (override with filtered version)
        {
            "src_node_id": "filter_playbook_selection_config",
            "dst_node_id": "join_play_metadata",
            "mappings": [
                {"src_field": "filtered_data", "dst_field": "filtered_data"}
            ]
        },
        # Correction Prompt -> Play Selection LLM (loop)
        {
            "src_node_id": "construct_play_id_correction_prompt",
            "dst_node_id": "play_suggestion_llm",
            "mappings": [
                {"src_field": "play_id_correction_user_prompt", "dst_field": "user_prompt"}
            ]
        },
        # State -> Prepare Join Inputs
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "join_play_metadata",
            "mappings": [
                {"src_field": "selected_plays", "dst_field": "selected_plays"},
            ]
        },

        # Join -> Filter Joined Plays With Reasoning
        {
            "src_node_id": "join_play_metadata",
            "dst_node_id": "filter_joined_plays_with_reasoning",
            "mappings": [
                {"src_field": "mapped_data", "dst_field": "mapped_data"}
            ]
        },
        # Filtered Joined Plays -> HITL
        {
            "src_node_id": "filter_joined_plays_with_reasoning",
            "dst_node_id": "flatten_play_recommendations",
            "mappings": [
                {"src_field": "filtered_data", "dst_field": "input_data"}
            ]
        },
        # Flatten Play Recommendations -> HITL
        {
            "src_node_id": "flatten_play_recommendations",
            "dst_node_id": "play_selection_hitl",
            "mappings": [
                {"src_field": "transformed_data", "dst_field": "play_recommendations"}
            ]
        },
        
        # HITL -> State
        {
            "src_node_id": "play_selection_hitl",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "final_selected_plays", "dst_field": "approved_plays"},
                {"src_field": "feedback", "dst_field": "current_user_feedback_on_plays"}
            ]
        },
        
        # HITL -> Router
        {
            "src_node_id": "play_selection_hitl",
            "dst_node_id": "route_play_selection",
            "mappings": [
                {"src_field": "user_action", "dst_field": "user_action"}
            ]
        },
        
        # Router -> Filter Plays Data (on approve)
        {
            "src_node_id": "route_play_selection",
            "dst_node_id": "filter_plays_data"
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "filter_plays_data",
            "mappings": [
                {"src_field": "playbook_selection_config", "dst_field": "playbook_selection_config"},
                {"src_field": "approved_plays", "dst_field": "approved_plays"}
            ]
        },
        {
            "src_node_id": "filter_plays_data",
            "dst_node_id": "prepare_load_configs",
            "mappings": [
                {"src_field": "filtered_data", "dst_field": "available_playbooks"}
            ]
        },

        {
            "src_node_id": "prepare_load_configs",
            "dst_node_id": "load_selected_playbooks",
            "mappings": [
                {"src_field": "transformed_data", "dst_field": "available_playbooks"}
            ]
        },

        {
            "src_node_id": "load_selected_playbooks",
            "dst_node_id": "construct_playbook_generator_prompt",
            "mappings": [
                {"src_field": "playbook", "dst_field": "fetched_information"}
            ]
        },
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_playbook_generator_prompt",
            "mappings": [
                {"src_field": "approved_plays", "dst_field": "approved_plays"},
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "diagnostic_report_doc", "dst_field": "diagnostic_report_doc"}
            ]
        },
        
        # Router -> Output (cancel)
        {
            "src_node_id": "route_play_selection",
            "dst_node_id": "output_node"
        },
        
        # Router -> Play Selection Revision Prompt (revise plays)
        {
            "src_node_id": "route_play_selection",
            "dst_node_id": "construct_play_selection_revision_prompt"
        },
        
        # State -> Play Selection Revision Prompt (provide documents and feedback)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_play_selection_revision_prompt",
            "mappings": [
                {"src_field": "current_user_feedback_on_plays", "dst_field": "user_feedback"},
                {"src_field": "selected_plays", "dst_field": "selected_plays"},
            ]
        },
        
        # Play Selection Revision Prompt -> Revision LLM
        {
            "src_node_id": "construct_play_selection_revision_prompt",
            "dst_node_id": "play_suggestion_llm",
            "mappings": [
                {"src_field": "play_selection_revision_user_prompt", "dst_field": "user_prompt"},
            ]
        },


        # Playbook Generator Prompt -> Playbook Generator LLM
        {
            "src_node_id": "construct_playbook_generator_prompt",
            "dst_node_id": "playbook_generator_llm",
            "mappings": [
                {"src_field": "playbook_generator_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "playbook_generator_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # Playbook Generator LLM -> State
        {
            "src_node_id": "playbook_generator_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "playbook_generator_output"},
                {"src_field": "current_messages", "dst_field": "playbook_generator_message_history"},
                {"src_field": "metadata", "dst_field": "playbook_generator_metadata"}
            ]
        },
        
        # Playbook Generator LLM -> Playbook Review HITL (when playbook generated)
        {
            "src_node_id": "playbook_generator_llm",
            "dst_node_id": "playbook_review_hitl",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "generated_playbook"}
            ]
        },
        
        # HITL Review -> Route Playbook Review
        {
            "src_node_id": "playbook_review_hitl",
            "dst_node_id": "route_playbook_review",
            "mappings": [
                {"src_field": "user_action", "dst_field": "user_action"}
            ]
        },
        # HITL Review -> State (store revision feedback)
        {
            "src_node_id": "playbook_review_hitl",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "user_action", "dst_field": "final_approval"},
                {"src_field": "revision_feedback", "dst_field": "revision_feedback"},
                {"src_field": "generated_playbook", "dst_field": "user_edited_generated_playbook"}
            ]
        },
        
        # Route Playbook Review -> Store Playbook (approve)
        {
            "src_node_id": "route_playbook_review",
            "dst_node_id": "store_playbook"
        },
        
        # Route Playbook Review -> Feedback Management Prompt Constructor (revise)
        {
            "src_node_id": "route_playbook_review",
            "dst_node_id": "check_revision_iteration"
        },
        
        # State -> Check Revision Iteration (provide generator metadata)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "check_revision_iteration",
            "mappings": [
                {"src_field": "playbook_generator_metadata", "dst_field": "metadata"}
            ]
        },
        
        # Check Revision Iteration -> Route
        {
            "src_node_id": "check_revision_iteration",
            "dst_node_id": "route_revision_iteration",
            "mappings": [
                {"src_field": "tag_results", "dst_field": "if_else_condition_tag_results"},
                {"src_field": "condition_result", "dst_field": "if_else_overall_condition_result"}
            ]
        },
        
        # Route -> Initial Feedback Prompt (first iteration)
        {
            "src_node_id": "route_revision_iteration",
            "dst_node_id": "construct_feedback_management_prompt"
        },
        
        # Route -> Additional Feedback Prompt (additional iterations)
        {
            "src_node_id": "route_revision_iteration",
            "dst_node_id": "construct_additional_feedback_prompt"
        },
        
        # State -> Additional Feedback Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_additional_feedback_prompt",
            "mappings": [
                {"src_field": "revision_feedback", "dst_field": "revision_feedback"},
                {"src_field": "user_edited_generated_playbook", "dst_field": "current_playbook"},
            ]
        },
        
        # Additional Feedback Prompt -> Feedback Management LLM
        {
            "src_node_id": "construct_additional_feedback_prompt",
            "dst_node_id": "feedback_management_llm",
            "mappings": [
                {"src_field": "additional_feedback_user_prompt", "dst_field": "user_prompt"},
            ]
        },
        
        # State -> Feedback Management Prompt Constructor
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_feedback_management_prompt",
            "mappings": [
                {"src_field": "revision_feedback", "dst_field": "revision_feedback"},
                {"src_field": "user_edited_generated_playbook", "dst_field": "current_playbook"},
                {"src_field": "approved_plays", "dst_field": "approved_plays"},
                {"src_field": "company_doc", "dst_field": "company_doc"},
                {"src_field": "diagnostic_report_doc", "dst_field": "diagnostic_report_doc"},
                {"src_field": "playbook_selection_config", "dst_field": "playbook_selection_config"}
            ]
        },
        
        # Feedback Management Prompt Constructor -> Feedback Management LLM
        {
            "src_node_id": "construct_feedback_management_prompt",
            "dst_node_id": "feedback_management_llm",
            "mappings": [
                {"src_field": "feedback_management_user_prompt", "dst_field": "user_prompt"},
                {"src_field": "feedback_management_system_prompt", "dst_field": "system_prompt"}
            ]
        },
        
        # Feedback Management LLM -> State
        {
            "src_node_id": "feedback_management_llm",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "structured_output", "dst_field": "feedback_management_output"},
                {"src_field": "tool_calls", "dst_field": "feedback_tool_calls"},
                {"src_field": "current_messages", "dst_field": "feedback_management_messages"}
            ]
        },
        
        # Feedback Management LLM -> Check Feedback Management Action
        {
            "src_node_id": "feedback_management_llm",
            "dst_node_id": "check_feedback_management_action",
            "mappings": [
                {"src_field": "tool_calls", "dst_field": "tool_calls"},
                {"src_field": "structured_output", "dst_field": "structured_output"}
            ]
        },
        
        # State -> Check Feedback Management Action (provide iteration count)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "check_feedback_management_action",
            "mappings": [
                {"src_field": "feedback_iteration_count", "dst_field": "feedback_iteration_count"}
            ]
        },
        
        # Check Feedback Management Action -> Route Feedback Management
        {
            "src_node_id": "check_feedback_management_action",
            "dst_node_id": "route_feedback_management",
            "mappings": [
                {"src_field": "tag_results", "dst_field": "tag_results"}
            ]
        },
        
        # Route Feedback Management -> Feedback Tool Executor
        {
            "src_node_id": "route_feedback_management",
            "dst_node_id": "feedback_tool_executor"
        },
        
        # Route Feedback Management -> Check Play IDs to Fetch
        {
            "src_node_id": "route_feedback_management",
            "dst_node_id": "check_play_ids_to_fetch"
        },
        
        # Route Feedback Management -> Feedback Clarification HITL
        {
            "src_node_id": "route_feedback_management",
            "dst_node_id": "feedback_clarification_hitl"
        },
        
        # Route Feedback Management -> Output (iteration limit)
        {
            "src_node_id": "route_feedback_management",
            "dst_node_id": "output_node"
        },
        
        # State -> Feedback Tool Executor
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "feedback_tool_executor",
            "mappings": [
                {"src_field": "company_name", "dst_field": "company_name"},
                {"src_field": "feedback_tool_calls", "dst_field": "tool_calls"}
            ]
        },
        
        # Feedback Tool Executor -> Construct Feedback Context Prompt
        {
            "src_node_id": "feedback_tool_executor",
            "dst_node_id": "feedback_management_llm",
            "mappings": [
                {"src_field": "tool_outputs", "dst_field": "tool_outputs"}
            ]
        },
        
        # State -> Feedback Management LLM (provide message history)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "feedback_management_llm",
            "mappings": [
                {"src_field": "feedback_management_messages", "dst_field": "messages_history"}
            ]
        },
        
        # State -> Feedback Clarification HITL (provide clarification question)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "feedback_clarification_hitl",
            "mappings": [
                {"src_field": "feedback_management_output", "dst_field": "clarification_question"}
            ]
        },
        
        # Feedback Clarification HITL -> Route Feedback Clarification
        {
            "src_node_id": "feedback_clarification_hitl",
            "dst_node_id": "route_feedback_clarification",
            "mappings": [
                {"src_field": "user_action", "dst_field": "user_action"}
            ]
        },
        
        # Feedback Clarification HITL -> State (store clarification)
        {
            "src_node_id": "feedback_clarification_hitl",
            "dst_node_id": "$graph_state",
            "mappings": [
                {"src_field": "clarification_response", "dst_field": "clarification_response"}
            ]
        },
        
        # Route Feedback Clarification -> Construct Enhanced Feedback Prompt
        {
            "src_node_id": "route_feedback_clarification",
            "dst_node_id": "construct_enhanced_feedback_prompt"
        },
        
        # Route Feedback Clarification -> Output (cancel)
        {
            "src_node_id": "route_feedback_clarification",
            "dst_node_id": "output_node"
        },
        
        # State -> Construct Enhanced Feedback Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_enhanced_feedback_prompt",
            "mappings": [
                {"src_field": "revision_feedback", "dst_field": "revision_feedback"},
                {"src_field": "clarification_response", "dst_field": "clarification_response"}
            ]
        },
        
        # Construct Enhanced Feedback Prompt -> Feedback Management LLM (continue with clarification)
        {
            "src_node_id": "construct_enhanced_feedback_prompt",
            "dst_node_id": "feedback_management_llm",
            "mappings": [
                {"src_field": "enhanced_feedback_prompt", "dst_field": "user_prompt"}
            ]
        },
        # 24.h Load Selected Playbooks for Update
        {
            "src_node_id": "load_selected_playbooks_for_update",
            "dst_node_id": "construct_playbook_update_prompt",
            "mappings": [
                {"src_field": "playbook", "dst_field": "additional_play_data"}
            ]
        },
        
        
        # State -> Check Play IDs to Fetch (provide feedback output)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "check_play_ids_to_fetch",
            "mappings": [
                {"src_field": "feedback_management_output", "dst_field": "feedback_management_output"}
            ]
        },
        
        # Check Play IDs to Fetch -> Route Play IDs to Fetch
        {
            "src_node_id": "check_play_ids_to_fetch",
            "dst_node_id": "route_play_ids_to_fetch",
            "mappings": [
                {"src_field": "tag_results", "dst_field": "tag_results"},
                {"src_field": "branch", "dst_field": "branch_decision"}
            ]
        },
        
        # Route Play IDs to Fetch -> Filter Plays for Update (if has ids)
        {
            "src_node_id": "route_play_ids_to_fetch",
            "dst_node_id": "filter_plays_for_update"
        },
        
        # Route Play IDs to Fetch -> Construct Playbook Update Prompt (if empty)
        {
            "src_node_id": "route_play_ids_to_fetch",
            "dst_node_id": "construct_playbook_update_prompt"
        },
        
        # State -> Filter Plays for Update (available config + ids)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "filter_plays_for_update",
            "mappings": [
                {"src_field": "playbook_selection_config", "dst_field": "playbook_selection_config"},
                {"src_field": "feedback_management_output.play_ids_to_fetch", "dst_field": "play_ids_to_fetch"}
            ]
        },
        
        # Filter Plays for Update -> Prepare Load Configs for Update
        {
            "src_node_id": "filter_plays_for_update",
            "dst_node_id": "prepare_load_configs_for_update",
            "mappings": [
                {"src_field": "filtered_data", "dst_field": "available_playbooks"}
            ]
        },
        
        # Prepare Load Configs for Update -> Load Selected Playbooks for Update
        {
            "src_node_id": "prepare_load_configs_for_update",
            "dst_node_id": "load_selected_playbooks_for_update",
            "mappings": [
                {"src_field": "transformed_data", "dst_field": "available_playbooks"}
            ]
        },
                # State -> Construct Playbook Update Prompt
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "construct_playbook_update_prompt",
            "mappings": [
                {"src_field": "playbook_generator_output", "dst_field": "current_playbook"},
                {"src_field": "revision_feedback", "dst_field": "revision_feedback"},
                {"src_field": "feedback_management_output", "dst_field": "additional_information"},
                {"src_field": "company_doc", "dst_field": "company_doc"}
            ]
        },
        
        # Construct Playbook Update Prompt -> Playbook Generator LLM (update playbook)
        {
            "src_node_id": "construct_playbook_update_prompt",
            "dst_node_id": "playbook_generator_llm",
            "mappings": [
                {"src_field": "playbook_update_user_prompt", "dst_field": "user_prompt"}
            ]
        },
        
        # State -> Playbook Generator LLM (provide message history for updates)
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "playbook_generator_llm",
            "mappings": [
                {"src_field": "playbook_generator_message_history", "dst_field": "messages_history"}
            ]
        },
        
        # State -> Store Playbook
        {
            "src_node_id": "$graph_state",
            "dst_node_id": "store_playbook",
            "mappings": [
                {"src_field": "playbook_generator_output", "dst_field": "final_playbook"},
                {"src_field": "company_name", "dst_field": "company_name"}
            ]
        },
        
        # Store Playbook -> Output
        {
            "src_node_id": "store_playbook",
            "dst_node_id": "output_node",
            "mappings": [
                {"src_field": "paths_processed", "dst_field": "paths_processed"}
            ]
        },
    ],
    
    "input_node_id": "input_node",
    "output_node_id": "output_node",
    
    "metadata": {
        "$graph_state": {
            "reducer": {
                "company_doc": "replace",
                "diagnostic_report_doc": "replace",
                "selected_plays": "replace",
                "approved_plays": "replace",
                "current_user_feedback_on_plays": "replace",
                "document_fetcher_output": "replace",
                "document_fetcher_tool_calls": "replace",
                "document_fetcher_messages": "add_messages",
                "clarification_response_during_document_fetcher": "replace",
                "playbook_generator_output": "replace",
                "user_feedback": "replace",
                "revision_feedback": "replace",
                "play_suggestion_message_history": "add_messages",
                "feedback_management_output": "replace",
                "feedback_tool_calls": "replace",
                "user_edited_generated_playbook": "replace",
                "feedback_management_messages": "add_messages",
                "playbook_generator_message_history": "add_messages",
                "feedback_iteration_count": "replace",
                "playbook_generator_clarification_response": "replace",
                "available_playbooks": "replace",
                "playbook_selection_config": "replace",
                "playbook_generator_metadata": "replace",
                "available_plays_list": "replace"
            }
        }
    }
}


# --- Testing Code ---

async def validate_playbook_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """
    Validate the content playbook generation workflow outputs.
    
    Args:
        outputs: The dictionary of final outputs from the workflow run.
        
    Returns:
        True if the outputs are valid, False otherwise.
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating content playbook generation workflow outputs...")
    
    # Check for expected keys
    expected_keys = [
        'final_playbook',
        'original_play_recommendations',
        'approved_plays'
    ]
    
    for key in expected_keys:
        if key in outputs:
            logger.info(f"✓ Found expected key: {key}")
        else:
            logger.warning(f"⚠ Missing optional key: {key}")
    
    # Validate final playbook structure
    if 'final_playbook' in outputs:
        playbook = outputs['final_playbook']
        assert isinstance(playbook, dict), "Final playbook should be a dict"
        
        required_fields = ['playbook_title', 'executive_summary', 'content_plays']
        for field in required_fields:
            assert field in playbook, f"Playbook missing required field: {field}"
        
        # Validate content plays
        content_plays = playbook['content_plays']
        assert isinstance(content_plays, list), "Content plays should be a list"
        assert len(content_plays) > 0, "Should have at least one content play"
        
        logger.info(f"✓ Generated playbook with {len(content_plays)} content plays")
        logger.info(f"✓ Playbook title: {playbook['playbook_title']}")
    
    # Check for playbook document ID if saved
    if 'playbook_document_id' in outputs and outputs['playbook_document_id'] is not None:
        doc_id = outputs['playbook_document_id']
        if isinstance(doc_id, str) and len(doc_id) > 0:
            logger.info(f"✓ Playbook saved with document ID: {doc_id}")
    
    logger.info("✓ Content playbook generation workflow output validation passed.")
    return True


async def main_test_playbook_workflow():
    """
    Test for Blog Content Playbook Generation Workflow.
    """
    test_name = "Blog Content Playbook Generation Workflow Test"
    print(f"--- Starting {test_name} ---")
    
    # Test parameters
    test_company_name = "test_blog_company"
    
    # Create test company document data
    company_data = {
        "company_name": "TechVenture Solutions",
        "industry": "B2B SaaS",
        "target_audience": "Small to medium businesses looking for digital transformation",
        "business_goals": [
            "Increase brand awareness in the SMB market",
            "Generate qualified leads for sales team",
            "Establish thought leadership in digital transformation"
        ],
        "current_content_challenges": [
            "Limited content creation resources",
            "Difficulty in measuring content ROI",
            "Need for more industry-specific content"
        ],
        "competitive_landscape": "Competing with larger enterprise solutions and smaller niche tools",
        "unique_value_proposition": "Enterprise-grade features at SMB pricing with exceptional customer support"
    }
    
    # Create comprehensive diagnostic report data
    diagnostic_report_data = {
        "executive_summary": {
            "current_position": "TechVenture Solutions has a solid foundation in B2B SaaS content but lacks consistent thought leadership presence and measurable ROI tracking across digital channels.",
            "biggest_opportunity": "Establishing executive thought leadership through strategic content positioning and AI-optimized SEO approach to capture high-intent SMB prospects.",
            "critical_risk": "Limited content resources may result in inconsistent messaging and missed opportunities in the rapidly evolving digital transformation market.",
            "overall_diagnostic_score": 6.8
        },
        "immediate_opportunities": {
            "top_content_opportunities": [
                {
                    "title": "Executive Thought Leadership Series",
                    "content_type": "Long-form Articles",
                    "impact_score": 9.2,
                    "implementation_effort": "Medium",
                    "timeline": "6-8 weeks"
                },
                {
                    "title": "SMB Digital Transformation Guides",
                    "content_type": "Practical Guides",
                    "impact_score": 8.5,
                    "implementation_effort": "High",
                    "timeline": "8-12 weeks"
                },
                {
                    "title": "Industry-Specific Case Studies",
                    "content_type": "Case Studies",
                    "impact_score": 8.8,
                    "implementation_effort": "Medium",
                    "timeline": "4-6 weeks"
                }
            ],
            "seo_quick_wins": [
                {
                    "action": "Optimize existing content for 'digital transformation SMB' keyword cluster",
                    "estimated_impact": "15-25% traffic increase",
                    "timeline": "2-3 weeks"
                },
                {
                    "action": "Create topic clusters around competitive advantage themes",
                    "estimated_impact": "Enhanced topical authority",
                    "timeline": "4-6 weeks"
                }
            ],
            "executive_visibility_actions": [
                {
                    "platform": "LinkedIn",
                    "action": "Launch weekly thought leadership posts on digital transformation trends",
                    "frequency": "2-3 posts per week",
                    "timeline": "Immediate"
                },
                {
                    "platform": "Industry Publications",
                    "action": "Contribute guest articles to key B2B SaaS publications",
                    "frequency": "Monthly",
                    "timeline": "2-4 weeks"
                }
            ],
            "ai_optimization_priorities": [
                {
                    "priority": "High",
                    "action": "Optimize content for AI search queries related to SMB digital transformation",
                    "expected_benefit": "Improved AI visibility and citations"
                },
                {
                    "priority": "Medium", 
                    "action": "Develop AI-friendly FAQ and resource sections",
                    "expected_benefit": "Enhanced structured data for AI comprehension"
                }
            ]
        },
        "content_audit_summary": {
            "total_content_pieces": 32,
            "avg_engagement_rate": 4.2,
            "top_performing_topics": ["Digital Transformation", "SMB Solutions", "Customer Success"],
            "content_gaps": ["AI Implementation", "Security Compliance", "Integration Challenges"]
        },
        "competitive_analysis": {
            "main_competitors": ["Enterprise Corp", "NicheSoft", "BigTech Solutions"],
            "competitive_advantages": ["SMB focus", "Customer support", "Pricing flexibility"],
            "market_opportunities": ["Underserved mid-market", "Industry-specific solutions", "Integration partnerships"]
        }
    }
    
    # Setup test documents
    setup_docs: List[SetupDocInfo] = [
        {
            'namespace': f"blog_company_profile_{test_company_name}",
            'docname': BLOG_COMPANY_DOCNAME,
            'initial_data': company_data,
            'is_shared': BLOG_COMPANY_IS_SHARED,
            'is_versioned': BLOG_COMPANY_IS_VERSIONED,
            'initial_version': None,
            'is_system_entity': BLOG_COMPANY_IS_SYSTEM_ENTITY
        },
        {
            'namespace': f"blog_content_diagnostic_report_{test_company_name}",
            'docname': BLOG_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
            'initial_data': diagnostic_report_data,
            'is_shared': BLOG_CONTENT_DIAGNOSTIC_REPORT_IS_SHARED,
            'is_versioned': BLOG_CONTENT_DIAGNOSTIC_REPORT_IS_VERSIONED,
            'initial_version': None,
            'is_system_entity': BLOG_CONTENT_DIAGNOSTIC_REPORT_IS_SYSTEM_ENTITY
        }
    ]
    
    # Cleanup configuration
    cleanup_docs: List[CleanupDocInfo] = [
        {
            'namespace': f"blog_company_profile_{test_company_name}",
            'docname': BLOG_COMPANY_DOCNAME,
            'is_shared': BLOG_COMPANY_IS_SHARED,
            'is_versioned': BLOG_COMPANY_IS_VERSIONED,
            'is_system_entity': BLOG_COMPANY_IS_SYSTEM_ENTITY
        },
        {
            'namespace': f"blog_content_diagnostic_report_{test_company_name}",
            'docname': BLOG_CONTENT_DIAGNOSTIC_REPORT_DOCNAME,
            'is_shared': BLOG_CONTENT_DIAGNOSTIC_REPORT_IS_SHARED,
            'is_versioned': BLOG_CONTENT_DIAGNOSTIC_REPORT_IS_VERSIONED,
            'is_system_entity': BLOG_CONTENT_DIAGNOSTIC_REPORT_IS_SYSTEM_ENTITY
        }
    ]
    
    # Test inputs - just entity username
    test_inputs = {
        "company_name": test_company_name
    }
    
    # Predefined HITL inputs - leaving empty for interactive testing
    predefined_hitl_inputs = [
{"user_action":"revise_plays","feedback":"suggest some other plays","final_selected_plays":[{"play_id":"the_david_vs_goliath_playbook","play_name":"The David vs Goliath Playbook"},{"play_id":"the_practitioners_handbook","play_name":"The Practitioner's Handbook"},{"play_id":"the_vertical_dominator","play_name":"The Vertical Dominator"}]},

{
  "user_action": "approve_plays",
  "feedback": None,
  "final_selected_plays": [
    {
      "play_id": "the_david_vs_goliath_playbook",
      "play_name": "The David vs Goliath Playbook",
      "play_description": "Win by systematically highlighting what incumbents structurally cannot or will not do.",
      "reasoning": "Perfect strategic fit for TechVenture's competitive position. They're competing against 'larger enterprise solutions' with clear structural advantages: SMB pricing, exceptional customer support, and pricing flexibility. Their UVP of 'enterprise-grade features at SMB pricing' is classic David vs Goliath positioning. This play directly addresses their goal of increasing brand awareness in the SMB market by highlighting what big competitors can't offer."
    },
    {
      "play_id": "the_practitioners_handbook",
      "play_name": "The Practitioner's Handbook",
      "play_description": "Share tactical, in-the-trenches expertise so deep that it becomes the industry's operational bible.",
      "reasoning": "Addresses multiple strategic needs: establishes thought leadership in digital transformation, provides industry-specific content (addressing current challenge), and generates qualified leads through valuable resources. The diagnostic shows top opportunities in 'SMB Digital Transformation Guides' and 'Executive Thought Leadership Series' - this play combines both. Limited resources make deep, practical content more valuable than broad coverage."
    },
    {
      "play_id": "the_vertical_dominator",
      "play_name": "The Vertical Dominator",
      "play_description": "Achieve category leadership by becoming the undisputed expert for one specific industry.",
      "reasoning": "Strategic solution to resource constraints and content challenges. Instead of creating generic SMB content, focus on 1-2 specific verticals where they can speak industry-specific language deeply. Addresses the identified need for 'more industry-specific content' and competitive advantage of 'SMB focus.' Helps maximize impact of limited content creation resources by going deep rather than broad."
    }
  ]
},

{"user_action":"request_revisions","revision_feedback":"suggest some other plays which are relevant for my profile","generated_playbook":{"playbook_title":"TechVenture Solutions Blog Content Playbook: Dominating the SMB Digital Transformation Market","executive_summary":"TechVenture Solutions is positioned to capture significant market share in the SMB digital transformation space through strategic content plays that leverage your unique positioning as \"David vs Goliath,\" establish deep practitioner credibility, and dominate vertical-specific conversations. With a current diagnostic score of 6.8/10, this playbook addresses your core challenges of limited content resources and ROI measurement while capitalizing on your competitive advantages of SMB focus, exceptional customer support, and enterprise-grade features at accessible pricing. The three selected plays will establish thought leadership, generate qualified leads, and create measurable content ROI within 12 weeks of implementation.","content_plays":[{"play_name":"The David vs Goliath Playbook","implementation_strategy":"Position TechVenture Solutions as the scrappy, customer-focused alternative to enterprise giants. Create content that highlights how smaller, agile companies can outmaneuver larger competitors through better customer service, faster implementation, and more flexible pricing. Focus on authentic storytelling that resonates with SMB decision-makers who feel overlooked by enterprise solutions.","content_formats":["Comparison blog posts","Customer success stories","Behind-the-scenes content","Founder/executive thought leadership pieces","Video testimonials","Interactive comparison tools"],"example_topics":["Why SMBs Choose Agile Solutions Over Enterprise Giants","The Real Cost of Enterprise Software for Small Businesses","Customer Support That Actually Cares: Our Story","How We Built Enterprise Features for SMB Budgets","David vs Goliath: 5 Ways Small Companies Win"],"success_metrics":["Brand sentiment score improvement","Share of voice vs competitors","Customer acquisition cost reduction","Content engagement rates","Lead quality scores","Organic traffic growth"],"timeline":"8-10 weeks for full implementation","resource_requirements":"1 content strategist, 1 writer, 1 video producer, executive participation for authenticity"},{"play_name":"The Practitioner's Handbook","implementation_strategy":"Establish TechVenture Solutions as the go-to resource for practical digital transformation guidance. Create in-depth, actionable content that SMB leaders can immediately implement. Focus on tactical advice, step-by-step guides, and real-world applications that demonstrate deep understanding of SMB operational challenges.","content_formats":["Comprehensive how-to guides","Implementation checklists","Template downloads","Video tutorials","Webinar series","Interactive assessments","Podcast series"],"example_topics":["The Complete SMB Digital Transformation Checklist","Security Compliance Made Simple for Small Businesses","Integration Challenges: A Practitioner's Guide","AI Implementation for SMBs: Start Here","Measuring ROI on Digital Transformation"],"success_metrics":["Content download rates","Time spent on page","Return visitor rates","Email list growth","Webinar attendance","Content sharing rates","Lead nurturing progression"],"timeline":"10-12 weeks for comprehensive resource library","resource_requirements":"2 subject matter experts, 1 technical writer, 1 designer for templates, marketing automation setup"},{"play_name":"The Vertical Dominator","implementation_strategy":"Dominate specific industry verticals by creating highly targeted content that addresses unique challenges and opportunities in key SMB sectors. Focus on 2-3 high-potential verticals initially, creating comprehensive content ecosystems that establish TechVenture Solutions as the industry expert for digital transformation in those sectors.","content_formats":["Industry-specific case studies","Vertical market reports","Sector-focused webinars","Industry newsletter","Vertical-specific landing pages","Industry partnership content"],"example_topics":["Digital Transformation in Manufacturing SMBs","Healthcare Practice Management: Technology Solutions","Retail Revolution: SMB Digital Strategies","Professional Services Automation Guide","Construction Industry Tech Adoption"],"success_metrics":["Vertical market share growth","Industry-specific organic rankings","Qualified leads by vertical","Industry event speaking opportunities","Partnership development","Vertical content engagement"],"timeline":"12-16 weeks per vertical (staggered approach)","resource_requirements":"Industry research analyst, vertical-specific writers, industry relationship manager, targeted advertising budget"}],"reasoning_for_recommendations":"These three plays directly address TechVenture Solutions' competitive position and business goals. The David vs Goliath approach leverages your natural positioning against larger competitors while building authentic brand connection. The Practitioner's Handbook establishes the thought leadership you need while providing immediate value to prospects, addressing the content ROI challenge through clear lead generation metrics. The Vertical Dominator creates the industry-specific content you're lacking while allowing focused resource allocation. Together, these plays create a comprehensive content ecosystem that builds brand awareness, generates qualified leads, and establishes measurable thought leadership in the SMB digital transformation space.","overall_recommendations":"Start with The David vs Goliath Playbook for immediate brand differentiation and quick wins, as it requires the least resources and can generate early momentum. Simultaneously begin research for The Practitioner's Handbook to establish your content foundation. Once these are showing results (8-10 weeks), launch The Vertical Dominator focusing on your two highest-opportunity verticals. Implement robust analytics tracking from day one to measure content ROI and optimize resource allocation. Consider partnering with industry experts or freelance specialists to supplement your limited internal resources while maintaining quality and consistency.","next_steps":["Conduct competitive content analysis to identify specific David vs Goliath messaging opportunities","Interview 5-10 existing customers for authentic success stories and testimonials","Set up content performance tracking dashboard with ROI metrics","Identify and recruit subject matter experts for Practitioner's Handbook content","Research and prioritize 2-3 target verticals based on current customer concentration and market opportunity","Establish content calendar with staggered play implementation timeline","Create content templates and brand guidelines for consistency across plays","Set up lead scoring system to measure content-driven lead quality improvement"]}},

{"user_action":"provide_clarification","clarification_response":"Add Problem Authority Stack + State of SMB Report, optimize for Lead gen"}


# {"user_action":"approve_playbook","revision_feedback":None,"generated_playbook":{"playbook_title":"TechVenture Solutions Blog Content Playbook: Dominating the SMB Digital Transformation Market","executive_summary":"TechVenture Solutions is positioned to capture significant market share in the SMB digital transformation space through strategic content plays that leverage your unique positioning as \"David vs Goliath,\" establish deep practitioner credibility, and dominate vertical-specific conversations. With a current diagnostic score of 6.8/10, this playbook addresses your core challenges of limited content resources and ROI measurement while capitalizing on your competitive advantages of SMB focus, exceptional customer support, and enterprise-grade features at accessible pricing. The three selected plays will establish thought leadership, generate qualified leads, and create measurable content ROI within 12 weeks of implementation.","content_plays":[{"play_name":"The David vs Goliath Playbook","implementation_strategy":"Position TechVenture Solutions as the scrappy, customer-focused alternative to enterprise giants. Create content that highlights how smaller, agile companies can outmaneuver larger competitors through better customer service, faster implementation, and more flexible pricing. Focus on authentic storytelling that resonates with SMB decision-makers who feel overlooked by enterprise solutions.","content_formats":["Comparison blog posts","Customer success stories","Behind-the-scenes content","Founder/executive thought leadership pieces","Video testimonials","Interactive comparison tools"],"example_topics":["Why SMBs Choose Agile Solutions Over Enterprise Giants","The Real Cost of Enterprise Software for Small Businesses","Customer Support That Actually Cares: Our Story","How We Built Enterprise Features for SMB Budgets","David vs Goliath: 5 Ways Small Companies Win"],"success_metrics":["Brand sentiment score improvement","Share of voice vs competitors","Customer acquisition cost reduction","Content engagement rates","Lead quality scores","Organic traffic growth"],"timeline":"8-10 weeks for full implementation","resource_requirements":"1 content strategist, 1 writer, 1 video producer, executive participation for authenticity"},{"play_name":"The Practitioner's Handbook","implementation_strategy":"Establish TechVenture Solutions as the go-to resource for practical digital transformation guidance. Create in-depth, actionable content that SMB leaders can immediately implement. Focus on tactical advice, step-by-step guides, and real-world applications that demonstrate deep understanding of SMB operational challenges.","content_formats":["Comprehensive how-to guides","Implementation checklists","Template downloads","Video tutorials","Webinar series","Interactive assessments","Podcast series"],"example_topics":["The Complete SMB Digital Transformation Checklist","Security Compliance Made Simple for Small Businesses","Integration Challenges: A Practitioner's Guide","AI Implementation for SMBs: Start Here","Measuring ROI on Digital Transformation"],"success_metrics":["Content download rates","Time spent on page","Return visitor rates","Email list growth","Webinar attendance","Content sharing rates","Lead nurturing progression"],"timeline":"10-12 weeks for comprehensive resource library","resource_requirements":"2 subject matter experts, 1 technical writer, 1 designer for templates, marketing automation setup"},{"play_name":"The Vertical Dominator","implementation_strategy":"Dominate specific industry verticals by creating highly targeted content that addresses unique challenges and opportunities in key SMB sectors. Focus on 2-3 high-potential verticals initially, creating comprehensive content ecosystems that establish TechVenture Solutions as the industry expert for digital transformation in those sectors.","content_formats":["Industry-specific case studies","Vertical market reports","Sector-focused webinars","Industry newsletter","Vertical-specific landing pages","Industry partnership content"],"example_topics":["Digital Transformation in Manufacturing SMBs","Healthcare Practice Management: Technology Solutions","Retail Revolution: SMB Digital Strategies","Professional Services Automation Guide","Construction Industry Tech Adoption"],"success_metrics":["Vertical market share growth","Industry-specific organic rankings","Qualified leads by vertical","Industry event speaking opportunities","Partnership development","Vertical content engagement"],"timeline":"12-16 weeks per vertical (staggered approach)","resource_requirements":"Industry research analyst, vertical-specific writers, industry relationship manager, targeted advertising budget"}],"reasoning_for_recommendations":"These three plays directly address TechVenture Solutions' competitive position and business goals. The David vs Goliath approach leverages your natural positioning against larger competitors while building authentic brand connection. The Practitioner's Handbook establishes the thought leadership you need while providing immediate value to prospects, addressing the content ROI challenge through clear lead generation metrics. The Vertical Dominator creates the industry-specific content you're lacking while allowing focused resource allocation. Together, these plays create a comprehensive content ecosystem that builds brand awareness, generates qualified leads, and establishes measurable thought leadership in the SMB digital transformation space.","overall_recommendations":"Start with The David vs Goliath Playbook for immediate brand differentiation and quick wins, as it requires the least resources and can generate early momentum. Simultaneously begin research for The Practitioner's Handbook to establish your content foundation. Once these are showing results (8-10 weeks), launch The Vertical Dominator focusing on your two highest-opportunity verticals. Implement robust analytics tracking from day one to measure content ROI and optimize resource allocation. Consider partnering with industry experts or freelance specialists to supplement your limited internal resources while maintaining quality and consistency.","next_steps":["Conduct competitive content analysis to identify specific David vs Goliath messaging opportunities","Interview 5-10 existing customers for authentic success stories and testimonials","Set up content performance tracking dashboard with ROI metrics","Identify and recruit subject matter experts for Practitioner's Handbook content","Research and prioritize 2-3 target verticals based on current customer concentration and market opportunity","Establish content calendar with staggered play implementation timeline","Create content templates and brand guidelines for consistency across plays","Set up lead scoring system to measure content-driven lead quality improvement"]}}

    ]

    
    # Execute the test
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=test_inputs,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=predefined_hitl_inputs,
        setup_docs=setup_docs,
        cleanup_docs=cleanup_docs,
        cleanup_docs_created_by_setup=False,
        validate_output_func=validate_playbook_output,
        stream_intermediate_results=True,
        poll_interval_sec=3,
        timeout_sec=1800  # 30 minutes
    )
    
    print(f"--- {test_name} Finished ---")
    if final_run_outputs:
        if 'final_playbook' in final_run_outputs:
            playbook = final_run_outputs['final_playbook']
            print(f"Generated Playbook: {playbook.get('playbook_title', 'N/A')}")
            print(f"Content Plays: {len(playbook.get('content_plays', []))}")
        
        if 'playbook_document_id' in final_run_outputs:
            print(f"Playbook Saved: Document ID {final_run_outputs['playbook_document_id']}")


# Entry point
if __name__ == "__main__":
    print("="*80)
    print("Blog Content Playbook Generation Workflow Test")
    print("="*80)
    
    try:
        asyncio.run(main_test_playbook_workflow())
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        logger.exception("Test execution failed")
    
    print("\nTest execution finished.")
    print("Run from project root: PYTHONPATH=. python kiwi_client/workflows_for_blog_teammate/wf_blog_content_playbook_generation.py")

