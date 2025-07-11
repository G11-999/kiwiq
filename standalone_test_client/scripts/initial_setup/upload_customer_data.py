import asyncio
import logging
from uuid import UUID
from typing import Optional, List, Tuple, Dict, Any
import json

from kiwi_client.customer_data_client import CustomerDataTestClient
from kiwi_client.auth_client import AuthenticatedClient
from kiwi_client.schemas.workflow_api_schemas import CustomerDataVersionedUpsert, CustomerDataVersionedUpsertResponse
from scripts.initial_setup.document_config import DocumentConfigManager


class JSONSerializableCustomerDataVersionedUpsert(CustomerDataVersionedUpsert):
    """Custom wrapper that ensures model_dump always uses mode='json' for UUID serialization"""
    
    def model_dump(self, **kwargs):
        # Always use mode='json' to ensure UUID objects are serialized as strings
        kwargs['mode'] = 'json'
        return super().model_dump(**kwargs)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class CustomerFileUploader:
    def __init__(self):
        self.client: Optional[CustomerDataTestClient] = None

    async def authenticate(self):
        try:
            auth_client = await AuthenticatedClient().__aenter__()
            logger.info("Authenticated.")
            self.client = CustomerDataTestClient(auth_client)
        except Exception as e:
            logger.exception("Authentication failed: %s", str(e))
            raise

    async def upsert_document(
        self,
        docname: str,
        entity_username: str,
        user_id: UUID,
        data: str,
        version: str = "v1"
    ) -> Optional[CustomerDataVersionedUpsertResponse]:
        try:
            if not self.client:
                await self.authenticate()

            namespace, config = DocumentConfigManager.get_config(docname, user_id, entity_username, data)
            # Use custom class that ensures proper JSON serialization of UUID objects
            payload = JSONSerializableCustomerDataVersionedUpsert(version=version, **config)
            return await self.client.upsert_versioned_document(namespace=namespace, docname=docname, data=payload)
        except Exception as e:
            logger.exception("Failed to upsert document %s: %s", docname, str(e))
            return None

    async def run_bulk_upsert_for_docs(
        self,
        user_id: UUID,
        entity_username: str,
        doc_data_pairs: List[Tuple[str, str]]
    ):
        try:
            if not self.client:
                await self.authenticate()

            for docname, data in doc_data_pairs:
                try:
                    response = await self.upsert_document(
                        docname=docname,
                        entity_username=entity_username,
                        user_id=user_id,
                        data=data
                    )
                    if response:
                        logger.info("Upsert successful for %s:\n%s", docname, response.model_dump_json(indent=2))
                    else:
                        logger.info("Upsert failed for %s.", docname)
                except Exception as e:
                    logger.exception("Error during upsert for %s: %s", docname, str(e))
        except Exception as e:
            logger.exception("Unexpected error in bulk upsert: %s", str(e))


async def main():
    try:   
     
        # data =  {
        #   "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa1",
        #   "entity_username": "kunal_tester_1",
        #   "doc_data": [
        #     ["user_dna_doc", "This is the testing file 1"],
        #     ["content_strategy_doc", "This is the testing file 2"],
        #     ["user_source_analysis", "This is the testing file 2"],
        #     ["uploaded_files", "This is the testing file 2"],
        #     ["core_beliefs_perspectives_doc", "This is the testing file 2"],
        #     ["content_pillars_doc", "This is the testing file 2"],
        #     ["user_preferences_doc", "This is the testing file 2"],
        #     ["content_analysis_doc", "This is the testing file 2"],
        #     ["linkedin_scraped_profile_doc", "This is the testing file 2"],
        #     ["linkedin_scraped_posts_doc", "This is the testing file 2"]
        #   ]
        # }
        
        data = {
            "user_id": "39a2fc5b-c7b9-4d3a-81ca-bd1def5922b5",
            "entity_username": "example-user-3",
            "doc_data": [
                ["user_dna_doc", {
    "professional_identity": {
        "full_name": "Test User",
        "job_title": "SDR Manager",
        "industry_sector": "SaaS / Software Development (Customer Support Technology)",
        "company_name": "Assembled",
        "company_size": "Medium (Works with enterprise clients like Zoom, Stripe, and The New York Times)",
        "years_of_experience": 9,
        "professional_certifications": [],
        "areas_of_expertise": [
            "Sales team development and management",
            "SDR/BDR leadership", 
            "Relationship building in sales contexts",
            "Communications and conflict resolution",
            "Team culture development",
            "Leadership development",
            "Professional growth mindset"
        ],
        "career_milestones": [
            "SDR Manager at Assembled (Feb 2023 - Present)",
            "Founding Member at ADAK (Mar 2024 - Present)", 
            "Mentor at The Cannon Project (2019 - Present)",
            "Member at Soul Sessions (Dec 2023 - Present)",
            "Head of Business Development at Fingerprint (Jun 2022 - Jan 2023)",
            "Consultant at Tenbound (Feb 2022 - Nov 2022)",
            "SDR Manager at Airkit (Feb 2020 - May 2022)",
            "Account Executive at Beyond Pricing (Sep 2019 - Jan 2020)",
            "BDR Manager at Beyond Pricing (2019 - Sep 2019)",
            "Business Development Representative at Beyond Pricing (Mar 2018 - Sep 2019)",
            "Professional Track and Field Athlete (Oct 2014 - Aug 2017)"
        ],
        "professional_bio": "Test User is an SDR Manager at Assembled, where he leads the Sales Development team in optimizing workforce management for support teams. With a background that spans from being a professional athlete to building high-performance sales teams, Damon brings a unique blend of athletic discipline and sales expertise to his leadership role. Originally from Jamaica, he has built his career in the SaaS industry with a focus on relationship-building and authentic leadership."
    },
    "linkedin_profile_analysis": {
        "follower_count": 15777,
        "connection_count": 0,
        "profile_headline_analysis": "Asking the important questions | Sharing learnings about work, leadership, mastery, and high-performance mindset. Learn with me",
        "about_section_summary": "Offers practical tips and systems for work life transformation. Connects his track and field athletic background to business skills. Emphasizes goal-setting, perseverance, and teamwork. Values teammates as significant resources. Focuses on mastery while staying grounded. Acknowledges his roots.",
        "engagement_metrics": {
            "average_likes_per_post": 7,
            "average_comments_per_post": 3,
            "average_shares_per_post": 1
        },
        "top_performing_content_pillars": [
            "Sales techniques and relationship building",
            "Leadership and team management", 
            "Professional development and workplace authenticity",
            "Communication and conflict resolution"
        ],
        "content_posting_frequency": "Regular (multiple posts weekly)",
        "content_types_used": [
            "Text-only posts",
            "Statement-counterstatement format",
            "Question-answer format", 
            "Short paragraphs with line breaks"
        ],
        "network_composition": [
            "Sales professionals",
            "SDR/BDR leaders",
            "Team managers",
            "Former athletes in business"
        ]
    },
    "brand_voice_and_style": {
        "communication_style": "Direct, concise, and authoritative with reflective elements",
        "tone_preferences": [
            "Instructive/Authoritative (60%)",
            "Reflective/Insightful (30%)",
            "Conversational/Questioning (10%)"
        ],
        "vocabulary_level": "Professional but accessible; uses industry terminology (SDRs, CRM, SaaS) sparingly (0.88 terms per post)",
        "sentence_structure_preferences": "Short, impactful sentences (average 12.3-14 words per sentence). Single-sentence paragraphs with line breaks. Statement-counterstatement structure (particularly for leadership content)",
        "content_format_preferences": [
            "Short paragraphs with line breaks",
            "Statement-Counter Statement structure",
            "Question-Answer Format",
            "Short-form insights"
        ],
        "emoji_usage": "Selective (0.75 per post in sales content, none in leadership/philosophical content); fire emojis (🔥) most common",
        "hashtag_usage": "Minimal to none (50% of Communication posts use hashtags, rare in other content types)",
        "storytelling_approach": "Balances personal anecdotes with frameworks and principles; connects athletic background to business contexts"
    },
    "content_strategy_goals": {
        "primary_goal": "Establish thought leadership in sales development and leadership",
        "secondary_goals": [
            "Share insights about team building and management",
            "Demonstrate expertise in relationship-building for sales",
            "Provide frameworks for professional communication and conflict resolution",
            "Create community around high-performance mindset",
            "Connect athletic discipline to professional success principles",
            "Share learning experiences and professional growth",
            "Build authentic connections with audience"
        ],
        "target_audience_demographics": "Sales professionals (particularly SDRs/BDRs), Sales managers and leaders, Team leaders across industries, Professionals seeking career advancement, Former athletes transitioning to business",
        "ideal_reader_personas": [
            "Sales Development Representatives seeking leadership guidance",
            "Sales managers building high-performance teams", 
            "Former athletes transitioning to business",
            "Professionals seeking authentic leadership examples"
        ],
        "audience_pain_points": [
            "Building effective sales teams",
            "Developing strong relationships with prospects/customers",
            "Navigating career growth without traditional experience",
            "Managing team dynamics and culture",
            "Balancing authenticity with professionalism", 
            "Resolving workplace conflicts effectively",
            "Finding adequate support in work environments"
        ],
        "value_proposition_to_audience": "Practical frameworks for difficult conversations and team management. Insights from athletic discipline applied to business. Authentic perspective on professional growth. Direct, actionable advice on sales relationship building. Reframing common workplace challenges.",
        "call_to_action_preferences": [
            "Implicit rather than explicit",
            "Focuses on sharing insights rather than direct calls to action"
        ],
        "content_pillar_themes": [
            "Sales Relationship Building",
            "Leadership & Team Support", 
            "Professional Growth & Authenticity",
            "Communication & Conflict Resolution",
            "Athletic Discipline in Business"
        ],
        "topics_of_interest": [
            "Relationship-building in sales",
            "Team culture development",
            "Authentic professional identity",
            "Structured frameworks for difficult conversations",
            "Belief systems in teams",
            "Leadership behavior and company culture",
            "Sales techniques and strategies",
            "Cold email effectiveness",
            "Career advancement without traditional experience",
            "Focus and curiosity for mastery"
        ],
        "topics_to_avoid": []
    },
    "personal_context": {
        "personal_values": [
            "Continuous learning and growth",
            "Authenticity in professional contexts",
            "Understanding others' perspectives",
            "Building meaningful relationships",
            "Creating supportive environments",
            "Mastery through disciplined practice",
            "High-performance mindset"
        ],
        "professional_mission_statement": "Helping professionals transform their work life through practical frameworks while maintaining authenticity and pursuing continuous growth.",
        "content_creation_challenges": [],
        "personal_story_elements_for_content": [
            "Track and field athletic background",
            "Princeton University education",
            "Jamaican heritage",
            "Transition from professional athlete to business professional",
            "Experience building SDR teams from the ground up"
        ],
        "notable_life_experiences": [
            "Princeton University triple jump record holder",
            "Jamaican national triple-jump champion",
            "Commonwealth Games competitor (10th place)",
            "First BDR hire at Beyond Pricing, helping build the playbook",
            "Transition from athletics to business leadership"
        ],
        "inspirations_and_influences": [],
        "books_resources_they_reference": [
            "Kelly McGonigal research on stress",
            "Bjork research on learning techniques"
        ],
        "quotes_they_resonate_with": []
    },
    "analytics_insights": {
        "optimal_content_length": "Leadership posts: 58 words average (range 40-70 words), Sales content: 42.6 words average, Professional development: 42 words average, Communication: 112 words average",
        "audience_geographic_distribution": "Not specified in provided documents",
        "engagement_time_patterns": "Not specified in provided documents", 
        "keyword_performance_analysis": "Top performing terms: 'belief' in leadership content, 'relationships' in sales content, 'professional' and 'authenticity' in career content, 'framework/approach' in communication content",
        "competitor_benchmarking": "Not specified in provided documents",
        "growth_rate_metrics": "Not specified in provided documents"
    },
    "success_metrics": {
        "content_performance_kpis": [
            "Engagement rate (likes, comments, reposts)",
            "Content that drives conversation (comment quality)"
        ],
        "engagement_quality_metrics": [
            "Statement hooks generate higher engagement than questions",
            "Contrarian statements receive 175% more engagement than personal narratives", 
            "Direct statements receive 33% more engagement than other formats"
        ],
        "conversion_goals": [],
        "brand_perception_goals": [
            "Recognized thought leader in SDR/sales development leadership"
        ],
        "timeline_for_expected_results": "Not specified in provided documents",
        "benchmarking_standards": "Not specified in provided documents"
    }
}
],
                ["content_strategy_doc", {
    "title": "Content Strategy for Test User",
    "foundation_elements": {
        "expertise": [
            "Sales Development Leadership - Building and leading high-performance SDR teams, developing sales processes for early-stage startups, implementing effective sales frameworks across industries, optimizing SDR-to-AE pipeline conversion (60%+ conversion rate)",
            "Team Culture & Leadership Development - Creating supportive environments for high-stress roles, leading underrepresented professionals in tech sales, implementing frameworks for effective communication, building psychologically safe environments for peak performance",
            "Performance Mindset & Mastery - Translating athletic discipline to business success, process-focused goal-setting methodologies, structured approaches to skill development, balancing performance with sustainable growth"
        ],
        "core_beliefs": [
            "Connection overcomes transactionalism - Genuine relationship-building is the foundation of successful sales and leadership",
            "Courage in communication shapes outcomes - Speaking up with authenticity and conviction changes trajectories in work and life",
            "Process goals outperform outcome goals - Focusing on controllable inputs creates more consistent, sustainable results than fixating on outcomes",
            "High performance requires intentional rest - Peak performers need structured downtime, not constant grind, to sustain excellence",
            "Nuance matters more than absolutes - There are few one-size-fits-all solutions; success depends on context and adaptation",
            "Innovation should extend to how work is done - Companies that only innovate in products but not in work processes miss opportunities",
            "Authentic leadership doesn't require conformity - Success shouldn't depend on adopting majority cultural norms or hiding one's background",
            "Silent confidence outperforms loud bravado - True mastery manifests as quiet competence, not performative intensity"
        ],
        "objectives": [
            "Establish Thought Leadership - Become recognized as a leading voice in SDR leadership and team building, increase meaningful post engagement by 30% in 90 days",
            "Build Authentic Community - Create a network of like-minded professionals, especially underrepresented individuals, target 100 engaged followers who consistently interact with content",
            "Develop Content Foundation - Establish consistent posting rhythm and content formats that resonate, target 2-3 high-quality posts weekly with growing engagement",
            "Position for Future Opportunities - Create pathways to future offerings (courses, newsletter, consulting), build foundation for monetized content within 9-12 months"
        ]
    },
    "core_perspectives": [
        "Authoritative yet approachable - Direct and clear statements of expertise, warm accessible language that invites dialogue, conversational without being overly casual",
        "Balanced formality - Professional vocabulary without unnecessary jargon, occasional industry terminology (0.8 terms per post), selective use of emojis in specific contexts",
        "Short impactful sentences (12-14 words on average), single-sentence paragraphs with line breaks for readability, statement-counter statement structure for impact",
        "Communication style: 60% Instructive/Authoritative, 30% Reflective/Insightful, 10% Conversational/Questioning"
    ],
    "content_pillars": [
        {
            "name": "High-Performance Sales Leadership",
            "pillar": "Translating athletic discipline into sales team excellence",
            "sub_topic": [
                "Building process-focused sales teams",
                "Metrics that matter beyond surface KPIs",
                "Creating systems that scale with company growth",
                "Decision frameworks for sales leaders",
                "Multi-industry sales leadership approaches"
            ]
        },
        {
            "name": "Authentic Leadership in Tech",
            "pillar": "Leading with your whole self, especially as an underrepresented professional",
            "sub_topic": [
                "Navigating cultural differences in professional settings",
                "Communication frameworks for difficult conversations",
                "Creating psychologically safe team environments",
                "Inclusive team building practices",
                "Leadership without conformity"
            ]
        },
        {
            "name": "Performance Mindset & Mastery",
            "pillar": "Structured approaches to professional excellence and growth",
            "sub_topic": [
                "Process vs. outcome goals",
                "Intentional rest and recovery cycles",
                "Focus techniques for high-pressure environments",
                "Learning frameworks backed by cognitive science",
                "Transferable skills from athletic to business performance"
            ]
        },
        {
            "name": "Career Navigation & Growth",
            "pillar": "Strategic career development, especially for non-traditional backgrounds",
            "sub_topic": [
                "Transitioning between careers and industries",
                "Building experiences that translate across contexts",
                "Leveraging distinctive backgrounds as advantages",
                "Strategic relationship building for career advancement",
                "Identifying and seizing growth opportunities"
            ]
        }
    ],
    "implementation": {
        "thirty_day_targets": {
            "goal": "Develop Content Foundation and establish consistent posting rhythm",
            "method": "Focus on foundation building through consistent posting cadence, format testing, and relationship building with commenters. Implement Authority and Value blocks with Connection and Engagement blocks for community building.",
            "targets": "8-10 high-quality posts, average of 15+ likes and 5+ comments per post, reply to 100% of comments, try all 4 format templates at least once"
        },
        "ninety_day_targets": {
            "goal": "Establish Thought Leadership and Build Authentic Community",
            "method": "Double down on highest-performing content types, increase depth within successful topics, begin featuring audience insights and stories, and explore content expansion opportunities. Focus on consistency and testing through optimization.",
            "targets": "25-30 foundational posts in content library, 30% increase in average engagement, 5-10 meaningful new connections per week, 2-3 external recognition signals (mentions, shares by industry figures)"
        }
    }
}
],
                ["user_preferences_doc", {
  "goals_answers": [
    {
      "question": "What is your goal with LinkedIn content?",
      "answer": "Become recognized as a leading voice in SDR leadership and team building, increase meaningful post engagement by 30% in 90 days."
    },
    {
      "question": "How do you want content to support your business?",
      "answer": "Create pathways to future offerings (courses, newsletter, consulting), build foundation for monetized content within 9-12 months."
    },
    {
      "question": "Are you looking to build a community or network?",
      "answer": "Create a network of like-minded professionals, especially underrepresented individuals, target 100 engaged followers who consistently interact with content."
    },
    {
      "question": "Do you want to position your brand uniquely?",
      "answer": "Establish consistent posting rhythm and content formats that resonate, target 2-3 high-quality posts weekly with growing engagement."
    }
  ],
  "user_preferences": {
    "audience": {
      "segments": [
        {
          "audience_type": "Underrepresented Professionals in Tech Sales",
          "description": "Early to mid-career professionals often feeling pressure to code-switch or conform, seeking authentic leadership examples and frameworks for managing stress and career growth in Technology/SaaS companies."
        },
        {
          "audience_type": "Sales Development Leaders & Managers",
          "description": "Leaders responsible for pipeline generation and team performance, focused on scalable processes and struggling with rep retention and performance. Typically found in medium to large Technology/SaaS companies."
        },
        {
          "audience_type": "High-Performance Professionals Across Industries",
          "description": "Individuals in high-pressure roles, such as former athletes transitioning into business. They seek performance mindset insights and sustainable excellence strategies, with intermediate to advanced knowledge levels."
        },
        {
          "audience_type": "Early-Stage Startup Leaders",
          "description": "Startup founders and executives building initial sales processes and scalable SDR/BDR teams. They have beginner to intermediate knowledge and work in small or startup-stage Technology companies."
        }
      ]
    },
    "posting_schedule": {
      "posts_per_week": 3,
      "posting_days": [
        "Tuesday",
        "Wednesday",
        "Thursday"
      ],
      "exclude_weekends": True
    }
  },
  "timezone": {
    "iana_identifier": "America/New_York",
    "display_name": "Eastern Daylight Time",
    "utc_offset": "-04:00",
    "supports_dst": True,
    "current_offset": "-04:00"
  }
}

]
            
            ]
        }


        if data['user_id']!="none":
            sample_user_id = UUID(data["user_id"])
        else:
            sample_user_id = None
            
        sample_entity_username = data["entity_username"]
        sample_doc_data = [tuple(doc) for doc in data["doc_data"]]
        
        uploader = CustomerFileUploader()
        await uploader.run_bulk_upsert_for_docs(sample_user_id, sample_entity_username, sample_doc_data)
    except Exception as e:
        logger.exception("Fatal error in main: %s", str(e))


if __name__ == "__main__":
    asyncio.run(main())