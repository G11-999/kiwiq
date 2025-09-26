from typing import Dict, Any, List, Optional
import asyncio
import logging
import json
from datetime import datetime

# Import document model constants
from kiwi_client.workflows.active.document_models.customer_docs import (
    # Blog Content Brief
    BLOG_CONTENT_BRIEF_NAMESPACE_TEMPLATE,
    # Blog Company Doc
    BLOG_COMPANY_DOCNAME,
    BLOG_COMPANY_NAMESPACE_TEMPLATE,
    # Blog Post
    BLOG_POST_DOCNAME,
    BLOG_POST_NAMESPACE_TEMPLATE,
    BLOG_POST_IS_VERSIONED,

    # Blog SEO Best Practices
    BLOG_SEO_BEST_PRACTICES_DOCNAME,
    BLOG_SEO_BEST_PRACTICES_NAMESPACE_TEMPLATE,
    BLOG_SEO_BEST_PRACTICES_IS_SHARED,
    BLOG_SEO_BEST_PRACTICES_IS_SYSTEM_ENTITY,
)

from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)

from kiwi_client.workflows.active.sandbox_identifiers import (
    test_sandbox_company_name,
)

test_brief_uuid = "test_brief_001"
test_brief_docname = f"blog_content_brief_{test_brief_uuid}"


test_blog_brief_data = {
    "created_at": "2025-08-01T14:47:10.345000Z",
    "updated_at": "2025-08-01T14:47:10.360000Z",
    "title": "Conversation Intelligence ROI Calculator: Quantifying the True Value of Automated Sales Insights for Enterprise Revenue Teams",
    "content_goal": "Provide a clear methodology and downloadable calculator for quantifying the ROI of conversation intelligence platforms, helping revenue leaders build a business case for implementing these solutions while establishing our brand as a thought leader in revenue intelligence and AI-powered sales automation.",
    "seo_keywords": {
    "primary_keyword": "conversation intelligence ROI calculator",
    "long_tail_keywords": [
        "how to calculate conversation intelligence ROI",
        "measuring the value of automated sales insights",
        "quantifying time savings from CRM automation",
        "conversation intelligence business case for enterprise",
        "ROI of sales call recording and analysis",
        "how to justify conversation intelligence investment"
    ],
    "secondary_keywords": [
        "sales automation ROI",
        "CRM data entry automation",
        "revenue intelligence tools",
        "sales coaching ROI",
        "enterprise sales technology ROI"
    ]
    },
    "key_takeaways": [
    "Conversation intelligence platforms deliver measurable ROI across multiple dimensions including time savings, deal velocity, and revenue lift",
    "A structured approach to calculating ROI helps justify technology investments to finance and executive stakeholders",
    "The true value of conversation intelligence extends beyond efficiency to include improved coaching, better customer intelligence, and data-driven decision making",
    "Enterprise revenue teams can expect specific, quantifiable improvements in key metrics when implementing conversation intelligence solutions",
    "Different departments (sales, customer success, revenue operations) benefit from conversation intelligence in distinct, measurable ways"
    ],
    "call_to_action": "Download our free Conversation Intelligence ROI Calculator to build a customized business case for your organization. Enter your specific data to see potential time savings, deal velocity improvements, and revenue lift you could achieve with automated sales insights.",
    "target_audience": "Enterprise SaaS Revenue Teams, specifically Chief Revenue Officers (CROs), VPs of Sales/Sales Operations, and other revenue leaders looking to justify investments in conversation intelligence and sales automation technology.",
    "brand_guidelines": {
    "tone": "Authoritative yet approachable. Position the content as expert guidance from a trusted advisor who understands the challenges revenue leaders face. Use a consultative tone that demonstrates deep expertise while remaining accessible.",
    "voice": "Confident, data-driven, and solutions-oriented. Speak directly to revenue leaders as peers, acknowledging their challenges while providing clear, actionable solutions backed by data and expertise.",
    "style_notes": [
        "Use precise, specific language and avoid vague claims",
        "Include concrete examples and data points to support all assertions",
        "Maintain a balance between technical accuracy and readability",
        "Use active voice and direct address to engage the reader",
        "Include visual elements like charts, tables, and infographics to illustrate complex concepts",
        "Avoid jargon without explanation, but don't oversimplify complex concepts",
        "Frame the content in terms of business outcomes and value, not just features"
    ]
    },
    "difficulty_level": "Intermediate",
    "research_sources": [
    {
        "source": "WalkMe Blog: 10 Native & third-party Salesforce automation tools",
        "key_insights": [
        "AI chatbots and real-time automation are emerging as key tools for Salesforce data entry",
        "Third-party tools often provide more specialized functionality than native Salesforce options",
        "Integration capabilities are critical for seamless workflow automation"
        ]
    },
    {
        "source": "Momentum.io: Which Tools Help in Automating Salesforce Data Entry? 2025 Buyer's Guide",
        "key_insights": [
        "Key features of leading automation platforms include AI-powered data capture and analysis",
        "RevOps teams prioritize tools that maintain data hygiene and accuracy",
        "Common pitfalls include solutions that require extensive customization or lack scalability"
        ]
    },
    {
        "source": "Reddit Research: User Questions on Salesforce Automation",
        "key_insights": [
        "12 mentions of questions about automating Salesforce data entry to save time",
        "9 mentions seeking tools to improve CRM data hygiene and accuracy",
        "7 mentions looking for ways to extract actionable insights from customer conversations",
        "6 mentions seeking to automate post-call tasks and reduce administrative overhead"
        ]
    },
    {
        "source": "Industry Benchmark: Conversation Intelligence Impact Study (2023)",
        "key_insights": [
        "Enterprise sales teams report an average 23% reduction in administrative time after implementing conversation intelligence",
        "Organizations using AI for sales insights see 12-18% improvements in deal velocity",
        "Companies with mature conversation intelligence programs report 7-15% higher win rates"
        ]
    }
    ],
    "content_structure": [
    {
        "section": "Introduction: The Challenge of Quantifying Conversation Intelligence ROI",
        "word_count": 300,
        "description": "Set the context by discussing why it's difficult but essential to quantify the ROI of conversation intelligence platforms. Highlight the pressure revenue leaders face to justify technology investments with hard numbers. Introduce the calculator as a solution to this challenge."
    },
    {
        "section": "Understanding the Full Value Spectrum of Conversation Intelligence",
        "word_count": 500,
        "description": "Break down the various ways conversation intelligence creates value: time savings from automated data entry, improved deal velocity from better insights, revenue lift from coaching opportunities, reduced churn from better customer intelligence, etc. Include real examples and statistics where possible."
    },
    {
        "section": "The ROI Calculator: Methodology and Approach",
        "word_count": 400,
        "description": "Explain the methodology behind the calculator. Detail the key inputs (team size, average deal size, sales cycle length, etc.) and how they factor into the calculations. Provide transparency into the formulas and assumptions used."
    },
    {
        "section": "Time Savings: Quantifying the Value of Automated Data Entry and Task Reduction",
        "word_count": 400,
        "description": "Focus specifically on calculating the value of time saved through automated data entry, automated meeting summaries, and reduced administrative tasks. Include formulas for converting time savings to monetary value based on fully-loaded employee costs."
    },
    {
        "section": "Deal Velocity Improvements: Measuring the Impact on Sales Cycle Length",
        "word_count": 400,
        "description": "Detail how to calculate the value of shortened sales cycles through better visibility into deal progression, faster identification of deal risks, and improved follow-up processes. Include the time value of money concept."
    },
    {
        "section": "Revenue Lift: Quantifying the Impact of Better Coaching and Deal Execution",
        "word_count": 450,
        "description": "Explain how to measure revenue increases from improved coaching effectiveness, better sales execution, and increased win rates. Include formulas for calculating the expected lift based on industry benchmarks and case studies."
    },
    {
        "section": "Customer Success Impact: Calculating Reduced Churn and Expansion Revenue",
        "word_count": 400,
        "description": "Focus on the ROI for customer success teams, including formulas for calculating the value of reduced churn and increased expansion revenue through better customer intelligence and proactive issue identification."
    },
    {
        "section": "Putting It All Together: Your Total Conversation Intelligence ROI",
        "word_count": 350,
        "description": "Explain how to combine all the individual ROI components into a comprehensive business case. Include guidance on presenting the results to executives and finance teams, with tips on addressing common objections."
    },
    {
        "section": "Case Study: How [Enterprise Company] Achieved 327% ROI with Conversation Intelligence",
        "word_count": 400,
        "description": "Present a detailed case study of an enterprise company that successfully implemented conversation intelligence and measured the results. Include specific metrics, challenges overcome, and lessons learned."
    },
    {
        "section": "Conclusion and Next Steps: Building Your Business Case",
        "word_count": 200,
        "description": "Summarize the key points and provide clear next steps for readers to download the calculator and begin building their own ROI analysis. Include a brief overview of implementation considerations to set expectations."
    }
    ],
    "estimated_word_count": 3800,
    "writing_instructions": [
    "Include real-world examples and specific metrics throughout the article to make the ROI calculations tangible",
    "Create or source at least 3 visual elements: 1) a sample ROI calculation, 2) a flowchart of the ROI methodology, and 3) a before/after comparison showing impact of conversation intelligence",
    "Incorporate direct quotes or insights from industry experts or customers to add credibility",
    "Include specific formulas and calculation methods that readers can apply to their own situations",
    "Balance technical detail with clear explanations - assume the reader is knowledgeable about sales processes but may not be a financial or technical expert",
    "Ensure the content addresses the specific pain points of all three ICPs (Enterprise SaaS Revenue Teams, Growth-Stage Sales Organizations, and Customer Success Teams)",
    "Reference the downloadable calculator throughout the article, not just in the conclusion",
    "Use subheadings, bullet points, and numbered lists to make the content scannable and actionable",
    "Include a brief section addressing common objections or concerns about ROI calculations for conversation intelligence"
    ],
    "uuid": "e9a0b9e5-cc45-4794-92ce-b0eb18282161",
    "status": "complete"
}

# Create test company guidelines data
test_company_data = {
    "name": "momentum",
    "website_url": "https://www.momentum.io",
    "value_proposition": "AI-native Revenue Orchestration Platform that extracts, structures, and moves GTM data automatically. Momentum tracks what's said in every customer interaction and turns it into structured, usable data, updating CRM fields in real time for cleaner pipeline, better reporting, and smarter AI agents with context.",
    "company_offerings": [
        {
            "offering": "AI-powered Revenue Orchestration Platform",
            "use_case": [
                "Automated CRM data entry and hygiene",
                "Real-time deal tracking and forecasting",
                "Customer conversation intelligence and insights",
                "Sales process automation and optimization",
                "Revenue pipeline visibility and reporting"
            ],
            "ideal_users": [
                "Chief Revenue Officers",
                "VP of Sales",
                "Sales Operations Managers",
                "VP of Customer Success",
                "Revenue Operations Teams"
            ]
        },
        {
            "offering": "Conversation Intelligence and Analytics",
            "use_case": [
                "Call transcription and sentiment analysis",
                "Customer feedback extraction and categorization",
                "Competitive intelligence gathering",
                "Product feedback and feature request tracking",
                "Risk signal identification and churn prevention"
            ],
            "ideal_users": [
                "Sales Representatives",
                "Customer Success Managers",
                "Product Marketing Managers",
                "Business Development Teams",
                "Executive Leadership"
            ]
        },
        {
            "offering": "Automated GTM Data Workflows",
            "use_case": [
                "Salesforce integration and data synchronization",
                "Multi-platform data orchestration",
                "Custom field mapping and data transformation",
                "Workflow automation and trigger management",
                "Data quality monitoring and alerts"
            ],
            "ideal_users": [
                "Sales Operations Analysts",
                "CRM Administrators",
                "Revenue Operations Directors",
                "IT and Systems Integration Teams",
                "Data Analytics Teams"
            ]
        }
    ],
    "icps": [
        {
            "icp_name": "Enterprise SaaS Revenue Teams",
            "target_industry": "SaaS/Technology",
            "company_size": "Enterprise (1000+ employees)",
            "buyer_persona": "Chief Revenue Officer (CRO)",
            "pain_points": [
                "Manual, repetitive Salesforce data entry",
                "Poor CRM data hygiene and accuracy",
                "Lack of visibility into deal progression and forecast risk",
                "Difficulty extracting insights from customer conversations",
                "Revenue team inefficiencies and administrative overhead"
            ]
        },
        {
            "icp_name": "Growth-Stage Sales Organizations",
            "target_industry": "B2B SaaS",
            "company_size": "Mid-market (200-1000 employees)",
            "buyer_persona": "VP of Sales/Sales Operations",
            "pain_points": [
                "Inconsistent sales process execution",
                "Manual deal room management and collaboration",
                "Missing customer intelligence and buying signals",
                "Time-consuming post-call administrative tasks",
                "Lack of real-time coaching and performance insights"
            ]
        },
        {
            "icp_name": "Customer Success Teams",
            "target_industry": "Technology/SaaS",
            "company_size": "Mid-market to Enterprise (500+ employees)",
            "buyer_persona": "VP of Customer Success",
            "pain_points": [
                "Inability to predict and prevent customer churn",
                "Manual tracking of customer health and satisfaction",
                "Difficulty identifying expansion opportunities",
                "Lack of visibility into customer feedback and product insights",
                "Inefficient handoff processes from sales to customer success"
            ]
        }
    ],
    "content_distribution_mix": {
        "awareness_percent": 30.0,
        "consideration_percent": 40.0,
        "purchase_percent": 20.0,
        "retention_percent": 10.0
    },
    "competitors": [
        {
            "website_url": "https://www.gong.io",
            "name": "Gong"
        },
        {
            "website_url": "https://www.outreach.io",
            "name": "Outreach"
        },
        {
            "website_url": "https://www.avoma.com",
            "name": "Avoma"
        }
    ],
    "goals": [
        "Establish thought leadership in revenue intelligence and AI-powered sales automation",
        "Educate target audience about the benefits of automated GTM data workflows",
        "Generate qualified leads through valuable content addressing CRM and sales operation challenges",
        "Build brand awareness among enterprise revenue teams and sales operations professionals",
        "Create content that drives organic traffic for high-intent keywords related to revenue orchestration and conversation intelligence"
    ]
}

# Setup test documents
setup_docs: List[SetupDocInfo] = [
    # Blog brief document
    {
        'namespace': f"blog_brief_namespace_{test_sandbox_company_name}",
        'docname': test_brief_docname,
        'initial_data': test_blog_brief_data,
        'is_shared': False,
        'is_versioned': True,
        'initial_version': "default",
        'is_system_entity': False
    },
    # Company guidelines document
    {
        'namespace': f"blog_company_profile_{test_sandbox_company_name}",
        'docname': BLOG_COMPANY_DOCNAME,
        'initial_data': test_company_data,
        'is_shared': False,
        'is_versioned': False,
        'initial_version': "None",
        'is_system_entity': False
    },

    {
        'namespace': f"blog_uploaded_files_{test_sandbox_company_name}",
        'docname': "ai_marketing_trends_2024",
        'initial_data': {
            "title": "AI Marketing Trends 2024",
            "content": "Recent studies show 73% of marketers use AI tools for content creation. Key trends include automated personalization, predictive analytics, and AI-powered customer segmentation.",
            "statistics": ["73% adoption rate", "40% efficiency improvement", "25% cost reduction"],
            "case_studies": ["Company X increased engagement by 150% using AI personalization"]
        },
        'is_shared': False,
        'is_versioned': False,
        'initial_version': "None",
        'is_system_entity': False
    }
]

# Cleanup configuration
#  These docs are deleted after the workflow test is done!
cleanup_docs: List[CleanupDocInfo] = [
    # {
    #     'namespace': f"blog_content_creation_{test_sandbox_company_name}",
    #     'docname': test_brief_docname,
    #     'is_shared': False,
    #     'is_versioned': True,
    #     'is_system_entity': False
    # },
    # {
    #     'namespace': f"blog_company_profile_{test_sandbox_company_name}",
    #     'docname': BLOG_COMPANY_DOCNAME,
    #     'is_shared': False,
    #     'is_versioned': False,
    #     'is_system_entity': False
    # },
]
