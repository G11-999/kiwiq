from typing import Dict, Any, Optional, List, Union
import json # Added for schema conversion


# Using Pydantic for easier schema generation
from pydantic import BaseModel, Field


# class ProfessionalIdentitySchema(BaseModel):
#     """Professional background and identity"""
#     full_name: str = Field(description="User's full name")
#     job_title: str = Field(description="Current job title")
#     industry_sector: str = Field(description="Industry or business sector")
#     company_name: str = Field(description="Current company name")
#     company_size: str = Field(description="Size of current company")
#     years_of_experience: int = Field(description="Years of professional experience")
#     professional_certifications: List[str] = Field(description="Professional certifications held")
#     areas_of_expertise: List[str] = Field(description="Areas of professional expertise")
#     career_milestones: List[str] = Field(description="Significant career achievements")
#     professional_bio: str = Field(description="Professional biography summary")


# class LinkedInEngagementMetricsSchema(BaseModel):
#     """Engagement performance metrics"""
#     average_likes_per_post: int = Field(description="Average likes per post")
#     average_comments_per_post: int = Field(description="Average comments per post")
#     average_shares_per_post: int = Field(description="Average shares per post")


# class LinkedInProfileAnalysisSchema(BaseModel):
#     """Analysis of LinkedIn profile"""
#     follower_count: int = Field(description="Number of LinkedIn followers")
#     connection_count: int = Field(description="Number of LinkedIn connections")
#     profile_headline_analysis: str = Field(description="Analysis of profile headline")
#     about_section_summary: str = Field(description="Summary of 'About' section")
#     engagement_metrics: LinkedInEngagementMetricsSchema = Field(description="Engagement performance metrics")
#     top_performing_content_pillars: List[str] = Field(description="Best performing content categories")
#     content_posting_frequency: str = Field(description="How often content is posted")
#     content_types_used: List[str] = Field(description="Types of content posted")
#     network_composition: List[str] = Field(description="Composition of LinkedIn network")


# class BrandVoiceAndStyleSchema(BaseModel):
#     """Personal brand voice characteristics"""
#     communication_style: str = Field(description="Overall communication style")
#     tone_preferences: List[str] = Field(description="Preferred tones in communication")
#     vocabulary_level: str = Field(description="Level of vocabulary used")
#     sentence_structure_preferences: str = Field(description="Preferred sentence structures")
#     content_format_preferences: List[str] = Field(description="Preferred content formats")
#     emoji_usage: str = Field(description="How emojis are used")
#     hashtag_usage: str = Field(description="How hashtags are used")
#     storytelling_approach: str = Field(description="Approach to storytelling")


# class ContentStrategyGoalsSchema(BaseModel):
#     """Content strategy goals and targets"""
#     primary_goal: str = Field(description="Primary content goal")
#     secondary_goals: List[str] = Field(description="Secondary content goals")
#     target_audience_demographics: str = Field(description="Target audience demographics")
#     ideal_reader_personas: List[str] = Field(description="Ideal reader descriptions")
#     audience_pain_points: List[str] = Field(description="Pain points of target audience")
#     value_proposition_to_audience: str = Field(description="Value proposition offered")
#     call_to_action_preferences: List[str] = Field(description="Preferred calls to action")
#     content_pillar_themes: List[str] = Field(description="Content pillar themes")
#     topics_of_interest: List[str] = Field(description="Topics of interest to cover")
#     topics_to_avoid: List[str] = Field(description="Topics to avoid covering")


# class PersonalContextSchema(BaseModel):
#     """Personal background context"""
#     personal_values: List[str] = Field(description="Personal values")
#     professional_mission_statement: str = Field(description="Professional mission statement")
#     content_creation_challenges: List[str] = Field(description="Challenges in content creation")
#     personal_story_elements_for_content: List[str] = Field(description="Personal story elements to use")
#     notable_life_experiences: List[str] = Field(description="Notable life experiences")
#     inspirations_and_influences: List[str] = Field(description="Sources of inspiration")
#     books_resources_they_reference: List[str] = Field(description="Books and resources referenced")
#     quotes_they_resonate_with: List[str] = Field(description="Resonating quotes")


# class AnalyticsInsightsSchema(BaseModel):
#     """Analytical insights about content"""
#     optimal_content_length: str = Field(description="Optimal content length")
#     audience_geographic_distribution: str = Field(description="Geographic distribution of audience")
#     engagement_time_patterns: str = Field(description="Patterns in engagement timing")
#     keyword_performance_analysis: str = Field(description="Performance of keywords")
#     competitor_benchmarking: str = Field(description="Benchmark against competitors")
#     growth_rate_metrics: str = Field(description="Growth rate metrics")


# class SuccessMetricsSchema(BaseModel):
#     """Metrics to measure success"""
#     content_performance_kpis: List[str] = Field(description="KPIs for content performance")
#     engagement_quality_metrics: List[str] = Field(description="Metrics for engagement quality")
#     conversion_goals: List[str] = Field(description="Conversion goals")
#     brand_perception_goals: List[str] = Field(description="Brand perception goals")
#     timeline_for_expected_results: str = Field(description="Timeline for expected results")
#     benchmarking_standards: str = Field(description="Standards for benchmarking")


# class UserUnderstandingSchema(BaseModel):
#     """Comprehensive user DNA profile derived from all inputs (AI-generated)"""
#     professional_identity: ProfessionalIdentitySchema = Field(description="Professional background and identity")
#     linkedin_profile_analysis: LinkedInProfileAnalysisSchema = Field(description="Analysis of LinkedIn profile")
#     brand_voice_and_style: BrandVoiceAndStyleSchema = Field(description="Personal brand voice characteristics")
#     content_strategy_goals: ContentStrategyGoalsSchema = Field(description="Content strategy goals and targets")
#     personal_context: PersonalContextSchema = Field(description="Personal background context")
#     analytics_insights: AnalyticsInsightsSchema = Field(description="Analytical insights about content")
#     success_metrics: SuccessMetricsSchema = Field(description="Metrics to measure success")


# class StrategyAudienceSchema(BaseModel):
#     """Target audience segments for strategy"""
#     primary: str = Field(description="Primary audience")
#     secondary: str = Field(description="Secondary audience")
#     tertiary: str = Field(description="Tertiary audience")


# class FoundationElementsSchema(BaseModel):
#     """Foundational elements of the strategy"""
#     expertise: List[str] = Field(description="Areas of expertise")
#     core_beliefs: List[str] = Field(description="Core beliefs")
#     objectives: List[str] = Field(description="Strategy objectives")


# class PostPerformanceAnalysisSchema(BaseModel):
#     """Analysis of post performance"""
#     current_engagement: str = Field(description="Current engagement levels")
#     content_that_resonates: str = Field(description="Content types that resonate with audience")
#     highest_performing_formats: str = Field(description="Best performing content formats")
#     audience_response: str = Field(description="How audience responds to content")


# class OverviewSchema(BaseModel):
#     """Strategy overview"""
#     post_performance_analysis: PostPerformanceAnalysisSchema = Field(description="Analysis of post performance")


# class ContentPillarSchema(BaseModel):
#     """Content pillar definitions"""
#     name: str = Field(description="Pillar name")
#     theme: str = Field(description="Pillar theme")
#     sub_themes: List[str] = Field(description="Sub-themes within pillar")


# class HighImpactFormatSchema(BaseModel):
#     """High impact content formats"""
#     name: str = Field(description="Format name")
#     steps: List[str] = Field(description="Steps to create this format")
#     example: str = Field(description="Example of the format")


# class ImplementationSchema(BaseModel):
#     """Implementation details"""
#     weekly_content_calendar: str = Field(description="Weekly content schedule")
#     thirty_day_targets: str = Field(description="30-day goals")
#     ninety_day_targets: str = Field(description="90-day goals")


# class ContentStrategySchema(BaseModel):
#     """Content strategy document derived from user DNA (AI-generated)"""
#     title: str = Field(description="Strategy title")
#     navigation_menu: List[str] = Field(description="Navigation menu items")
#     foundation_elements: FoundationElementsSchema = Field(description="Foundational elements of the strategy")
#     overview: OverviewSchema = Field(description="Strategy overview")
#     core_perspectives: List[str] = Field(description="Core content perspectives")
#     content_pillars: List[ContentPillarSchema] = Field(description="Content pillar definitions")
#     high_impact_formats: List[HighImpactFormatSchema] = Field(description="High impact content formats")
#     implementation: ImplementationSchema = Field(description="Implementation details")
   
   
# class ExtractionSchema(BaseModel):
#     content_strategy: Optional[ContentStrategySchema]
#     user_understanding: Optional[UserUnderstandingSchema]



class ProfessionalIdentitySchema(BaseModel):
    """Professional background and identity"""
    full_name: str = Field(description="User's full name")
    job_title: str = Field(description="Current job title")
    industry_sector: str = Field(description="Industry or business sector")
    company_name: str = Field(description="Current company name")
    company_size: str = Field(description="Size of current company")
    years_of_experience: int = Field(description="Years of professional experience")
    professional_certifications: List[str] = Field(description="Professional certifications held")
    areas_of_expertise: List[str] = Field(description="Areas of professional expertise")
    career_milestones: List[str] = Field(description="Significant career achievements")
    professional_bio: str = Field(description="Professional biography summary")


class LinkedInEngagementMetricsSchema(BaseModel):
    """Engagement performance metrics"""
    average_likes_per_post: int = Field(description="Average likes per post")
    average_comments_per_post: int = Field(description="Average comments per post")
    average_shares_per_post: int = Field(description="Average shares per post")


class LinkedInProfileAnalysisSchema(BaseModel):
    """Analysis of LinkedIn profile"""
    follower_count: int = Field(description="Number of LinkedIn followers")
    connection_count: int = Field(description="Number of LinkedIn connections")
    profile_headline_analysis: str = Field(description="Analysis of profile headline")
    about_section_summary: str = Field(description="Summary of 'About' section")
    engagement_metrics: LinkedInEngagementMetricsSchema = Field(description="Engagement performance metrics")
    top_performing_content_pillars: List[str] = Field(description="Best performing content categories")
    content_posting_frequency: str = Field(description="How often content is posted")
    content_types_used: List[str] = Field(description="Types of content posted")
    network_composition: List[str] = Field(description="Composition of LinkedIn network")


class BrandVoiceAndStyleSchema(BaseModel):
    """Personal brand voice characteristics"""
    communication_style: str = Field(description="Overall communication style")
    tone_preferences: List[str] = Field(description="Preferred tones in communication")
    vocabulary_level: str = Field(description="Level of vocabulary used")
    sentence_structure_preferences: str = Field(description="Preferred sentence structures")
    content_format_preferences: List[str] = Field(description="Preferred content formats")
    emoji_usage: str = Field(description="How emojis are used")
    hashtag_usage: str = Field(description="How hashtags are used")
    storytelling_approach: str = Field(description="Approach to storytelling")


class ContentStrategyGoalsSchema(BaseModel):
    """Content strategy goals and targets"""
    primary_goal: str = Field(description="Primary content goal")
    secondary_goals: List[str] = Field(description="Secondary content goals")
    target_audience_demographics: str = Field(description="Target audience demographics")
    ideal_reader_personas: List[str] = Field(description="Ideal reader descriptions")
    audience_pain_points: List[str] = Field(description="Pain points of target audience")
    value_proposition_to_audience: str = Field(description="Value proposition offered")
    call_to_action_preferences: List[str] = Field(description="Preferred calls to action")
    content_pillar_themes: List[str] = Field(description="Content pillar themes")
    topics_of_interest: List[str] = Field(description="Topics of interest to cover")
    topics_to_avoid: List[str] = Field(description="Topics to avoid covering")


class PersonalContextSchema(BaseModel):
    """Personal background context"""
    personal_values: List[str] = Field(description="Personal values")
    professional_mission_statement: str = Field(description="Professional mission statement")
    content_creation_challenges: List[str] = Field(description="Challenges in content creation")
    personal_story_elements_for_content: List[str] = Field(description="Personal story elements to use")
    notable_life_experiences: List[str] = Field(description="Notable life experiences")
    inspirations_and_influences: List[str] = Field(description="Sources of inspiration")
    books_resources_they_reference: List[str] = Field(description="Books and resources referenced")
    quotes_they_resonate_with: List[str] = Field(description="Resonating quotes")


class AnalyticsInsightsSchema(BaseModel):
    """Analytical insights about content"""
    optimal_content_length: str = Field(description="Optimal content length")
    audience_geographic_distribution: str = Field(description="Geographic distribution of audience")
    engagement_time_patterns: str = Field(description="Patterns in engagement timing")
    keyword_performance_analysis: str = Field(description="Performance of keywords")
    competitor_benchmarking: str = Field(description="Benchmark against competitors")
    growth_rate_metrics: str = Field(description="Growth rate metrics")


class SuccessMetricsSchema(BaseModel):
    """Metrics to measure success"""
    content_performance_kpis: List[str] = Field(description="KPIs for content performance")
    engagement_quality_metrics: List[str] = Field(description="Metrics for engagement quality")
    conversion_goals: List[str] = Field(description="Conversion goals")
    brand_perception_goals: List[str] = Field(description="Brand perception goals")
    timeline_for_expected_results: str = Field(description="Timeline for expected results")
    benchmarking_standards: str = Field(description="Standards for benchmarking")


class UserUnderstandingSchema(BaseModel):
    """Comprehensive user DNA profile derived from all inputs (AI-generated)"""
    professional_identity: ProfessionalIdentitySchema = Field(description="Professional background and identity")
    linkedin_profile_analysis: LinkedInProfileAnalysisSchema = Field(description="Analysis of LinkedIn profile")
    brand_voice_and_style: BrandVoiceAndStyleSchema = Field(description="Personal brand voice characteristics")
    content_strategy_goals: ContentStrategyGoalsSchema = Field(description="Content strategy goals and targets")
    personal_context: PersonalContextSchema = Field(description="Personal background context")
    analytics_insights: AnalyticsInsightsSchema = Field(description="Analytical insights about content")
    success_metrics: SuccessMetricsSchema = Field(description="Metrics to measure success")


class StrategyAudienceSchema(BaseModel):
    """Target audience segments for strategy"""
    primary: str = Field(description="Primary audience")
    secondary: str = Field(description="Secondary audience")
    tertiary: str = Field(description="Tertiary audience")


class FoundationElementsSchema(BaseModel):
    """Foundational elements of the strategy"""
    expertise: List[str] = Field(description="Areas of expertise")
    core_beliefs: List[str] = Field(description="Core beliefs")
    objectives: List[str] = Field(description="Strategy objectives")


class PostPerformanceAnalysisSchema(BaseModel):
    """Analysis of post performance"""
    current_engagement: str = Field(description="Current engagement levels")
    content_that_resonates: str = Field(description="Content types that resonate with audience")
    highest_performing_formats: str = Field(description="Best performing content formats")
    audience_response: str = Field(description="How audience responds to content")


class OverviewSchema(BaseModel):
    """Strategy overview"""
    post_performance_analysis: PostPerformanceAnalysisSchema = Field(description="Analysis of post performance")


class ContentPillarSchema(BaseModel):
    """Content pillar definitions"""
    name: str = Field(description="Pillar name")
    theme: str = Field(description="Pillar theme")
    sub_themes: List[str] = Field(description="Sub-themes within pillar")


class HighImpactFormatSchema(BaseModel):
    """High impact content formats"""
    name: str = Field(description="Format name")
    steps: List[str] = Field(description="Steps to create this format")
    example: str = Field(description="Example of the format")


class ImplementationSchema(BaseModel):
    """Implementation details"""
    weekly_content_calendar: str = Field(description="Weekly content schedule")
    thirty_day_targets: str = Field(description="30-day goals")
    ninety_day_targets: str = Field(description="90-day goals")


class ContentStrategySchema(BaseModel):
    """Content strategy document derived from user DNA (AI-generated)"""
    title: str = Field(description="Strategy title")
    navigation_menu: List[str] = Field(description="Navigation menu items")
    foundation_elements: FoundationElementsSchema = Field(description="Foundational elements of the strategy")
    overview: OverviewSchema = Field(description="Strategy overview")
    core_perspectives: List[str] = Field(description="Core content perspectives")
    content_pillars: List[ContentPillarSchema] = Field(description="Content pillar definitions")
    high_impact_formats: List[HighImpactFormatSchema] = Field(description="High impact content formats")
    implementation: ImplementationSchema = Field(description="Implementation details")
   
   
class ExtractionSchema(BaseModel):
    content_strategy: Optional[ContentStrategySchema]
    user_understanding: Optional[UserUnderstandingSchema]


# Generate JSON schema from the Pydantic model
EXTRACTION_JSON_SCHEMA = ExtractionSchema.model_json_schema()


SOURCES_EXTRACTION_SYSTEM_PROMPT = """
You are a document‑analysis and extraction expert.

Your job is to extract structured data from uploaded document and fill the predefined schema *only* with information explicitly present in that document.  
• Never infer or fabricate.  
• If a field isn’t mentioned, leave it null.  
• Match the schema’s structure, names, and data types exactly.  
• Return a single JSON object and nothing else.

Populate the schema shared strictly with information found in the document and return **only** the resulting JSON object.

Respond only with the requested JSON schema as follows: ```json\n{extraction_schema}\n```
"""


SOURCES_EXTRACTION_USER_PROMPT = """
I am uploading a document to help define the user’s professional profile and content strategy. Your task is to extract all relevant information from the document and populate the data schema shared with you:

Filename: {document_filename}

Content: 

```md
{document_content}
```
"""
