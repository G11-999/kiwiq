"""
LLM Prompts and Schemas for Company Analysis Workflow

This module contains all prompts and output schemas for analyzing internal 
company documents to extract comprehensive company information, generate 
Reddit research queries, analyze market insights, and create content pillars.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum

# ============================================
# DOCUMENT ANALYSIS PROMPTS & SCHEMAS
# ============================================

DOCUMENT_ANALYSIS_SYSTEM_PROMPT = """You are an expert business analyst specializing in extracting comprehensive company information from internal documents. Your task is to analyze the provided documents and extract key business intelligence about the company, their products, target audience, and market positioning.

Focus on identifying:
1. Core product features and capabilities
2. Unique value propositions and differentiators  
3. Target audience segments and buyer personas
4. Business goals and objectives
5. Industry positioning and competitive advantages
6. Key messaging and brand positioning
7. Technical specifications or implementation details
8. Pricing strategies or business models (if mentioned)
9. Customer pain points the company addresses
10. Company mission, vision, and values

Be thorough and extract ALL relevant information that helps understand the company's business, offerings, and market approach."""

DOCUMENT_ANALYSIS_USER_PROMPT_TEMPLATE = """
Analyze the following batch of internal company documents and extract comprehensive information about the company, their products, services, and target market.

Company Goals Context:
{company_goals}

Documents to Analyze:
{documents_batch}

Please analyze these documents thoroughly and extract all relevant business information according to the specified schema."""

# Pydantic Models for Document Analysis
class ProductFeature(BaseModel):
    feature_name: str = Field(description="Name of the feature")
    description: str = Field(description="Description of the feature")
    benefit: Optional[str] = Field(None, description="Benefit of the feature")

class TargetAudience(BaseModel):
    segment_name: str = Field(description="Name of the audience segment")
    characteristics: List[str] = Field(description="Characteristics of this segment")
    pain_points: List[str] = Field(description="Pain points of this segment")
    needs: List[str] = Field(description="Needs of this segment")

class IndustryInfo(BaseModel):
    industry_name: Optional[str] = Field(None, description="Name of the industry")
    market_position: Optional[str] = Field(None, description="Company's position in the market")
    competitive_advantages: List[str] = Field(description="Competitive advantages")
    competitors_mentioned: List[str] = Field(description="Competitors mentioned in documents")

class PricingInfo(BaseModel):
    pricing_model: Optional[str] = Field(None, description="Pricing model used")
    pricing_tiers: List[str] = Field(description="Different pricing tiers")
    pricing_strategy: Optional[str] = Field(None, description="Overall pricing strategy")

class CompanyInfo(BaseModel):
    mission: Optional[str] = Field(None, description="Company mission statement")
    vision: Optional[str] = Field(None, description="Company vision statement")
    values: List[str] = Field(description="Company core values")
    company_description: Optional[str] = Field(None, description="General company description")

class DocumentAnalysisOutput(BaseModel):
    product_features: List[ProductFeature] = Field(description="List of core product features and capabilities")
    value_propositions: List[str] = Field(description="Unique value propositions and differentiators")
    target_audiences: List[TargetAudience] = Field(description="Target audience segments with details")
    business_goals: List[str] = Field(description="Company's business goals and objectives")
    industry_info: Optional[IndustryInfo] = Field(None, description="Industry and market information")
    key_messaging: List[str] = Field(description="Key brand messages and positioning statements")
    technical_details: List[str] = Field(description="Technical specifications or implementation details")
    pricing_info: Optional[PricingInfo] = Field(None, description="Pricing information")
    customer_pain_points: List[str] = Field(description="Customer problems the company solves")
    company_info: Optional[CompanyInfo] = Field(None, description="Company mission, vision, and values")
    use_cases: List[str] = Field(description="Specific use cases or applications")
    insights_summary: str = Field(description="Brief summary of key insights from this batch")

# Convert to JSON schema for workflow usage
DOCUMENT_ANALYSIS_OUTPUT_SCHEMA = DocumentAnalysisOutput.model_json_schema()

# ============================================
# UNIQUE REPORT GENERATION PROMPTS & SCHEMAS
# ============================================

UNIQUE_REPORT_SYSTEM_PROMPT = """You are a senior business intelligence analyst tasked with synthesizing multiple analysis reports into a single, comprehensive report. Your goal is to:

1. Eliminate all duplicate information
2. Consolidate similar points into unified insights
3. Organize information logically and coherently
4. Preserve all unique insights and details
5. Create a comprehensive yet concise overview

Focus on creating a clear, actionable intelligence report that captures the complete picture of the company without redundancy."""

UNIQUE_REPORT_USER_PROMPT_TEMPLATE = """Synthesize the following analysis reports into a single, comprehensive report with only unique information. Eliminate all duplicates and redundancies while preserving every unique insight.

Multiple Analysis Reports:
{collected_analyses}

{perplexity_research_section}

Create a unified report that captures all unique information about the company, their products, market positioning, and target audience. When both document analysis and perplexity research are available, prioritize the internal document insights while supplementing with external research findings where they add unique value."""

# Pydantic Models for Unique Report
class CompanyOverview(BaseModel):
    description: Optional[str] = Field(None, description="Company description")
    mission: Optional[str] = Field(None, description="Company mission")
    vision: Optional[str] = Field(None, description="Company vision")
    core_values: List[str] = Field(description="Core company values")

class ProductsAndServices(BaseModel):
    main_offerings: List[str] = Field(description="Main products and services")
    key_features: List[str] = Field(description="Key features across all offerings")
    unique_capabilities: List[str] = Field(description="Unique capabilities")

class ValueProposition(BaseModel):
    primary_value_props: List[str] = Field(description="Primary value propositions")
    competitive_differentiators: List[str] = Field(description="Competitive differentiators")

class BuyerPersona(BaseModel):
    persona_name: str = Field(description="Name or title of the buyer persona")
    job_title: Optional[str] = Field(None, description="Typical job title or role")
    demographics: Optional[str] = Field(None, description="Demographic information")
    goals: List[str] = Field(description="Primary goals and objectives")
    challenges: List[str] = Field(description="Main challenges and pain points")
    decision_criteria: List[str] = Field(description="Key factors in purchase decisions")
    preferred_channels: List[str] = Field(description="Preferred communication and information channels")
    objections: List[str] = Field(description="Common objections or concerns")

class TargetMarket(BaseModel):
    primary_segments: List[str] = Field(description="Primary market segments")
    buyer_personas: List[BuyerPersona] = Field(description="Detailed buyer personas")
    market_size: Optional[str] = Field(None, description="Market size estimate")
    geographic_focus: Optional[str] = Field(None, description="Geographic focus areas")

class CustomerInsights(BaseModel):
    main_pain_points: List[str] = Field(description="Main customer pain points")
    customer_needs: List[str] = Field(description="Customer needs")
    use_cases: List[str] = Field(description="Common use cases")

class MarketPosition(BaseModel):
    industry: Optional[str] = Field(None, description="Industry")
    positioning: Optional[str] = Field(None, description="Market positioning")
    key_competitors: List[str] = Field(description="Key competitors")
    competitive_advantages: List[str] = Field(description="Competitive advantages")

class BusinessModel(BaseModel):
    revenue_model: Optional[str] = Field(None, description="Revenue model")
    pricing_strategy: Optional[str] = Field(None, description="Pricing strategy")
    go_to_market: Optional[str] = Field(None, description="Go-to-market strategy")

class UniqueReportOutput(BaseModel):
    executive_summary: str = Field(description="High-level summary of the company and key findings")
    company_overview: CompanyOverview = Field(description="Company overview information")
    products_and_services: ProductsAndServices = Field(description="Products and services information")
    value_proposition: ValueProposition = Field(description="Value proposition details")
    target_market: TargetMarket = Field(description="Target market information")
    customer_insights: CustomerInsights = Field(description="Customer insights")
    market_position: Optional[MarketPosition] = Field(None, description="Market position details")
    business_model: Optional[BusinessModel] = Field(None, description="Business model information")
    key_insights: List[str] = Field(description="Most important strategic insights about the company")

# Convert to JSON schema for workflow usage
UNIQUE_REPORT_OUTPUT_SCHEMA = UniqueReportOutput.model_json_schema()

# ============================================
# REDDIT QUERY GENERATION PROMPTS & SCHEMAS
# ============================================

REDDIT_QUERY_SYSTEM_PROMPT = """You are a market research expert specializing in social listening and community insights. Your task is to generate strategic Reddit search queries that will help uncover real user discussions, pain points, and needs in the company's industry.

Generate queries that:
1. Focus on the industry and problem space, NOT the specific company
2. Target real user discussions about challenges and needs
3. Include relevant keywords that Reddit users would actually use
4. Mix broad industry queries with specific use-case queries
5. Include temporal elements (2024, 2025) for current relevance
6. Target both professional and casual discussion formats
7. Focus on high-engagement topics (questions, recommendations, comparisons)

The queries should help discover:
- What problems users are trying to solve (and how many are affected)
- What solutions they're currently using (and satisfaction levels)
- What features they wish existed (with demand indicators)
- Common frustrations and pain points (with frequency)
- Buying criteria and decision factors
- Industry trends and emerging needs
- Discussion volume and engagement levels for different topics"""

REDDIT_QUERY_USER_PROMPT_TEMPLATE = """Based on the company analysis report below, generate 5 strategic Reddit search queries to understand user needs, pain points, and discussions in this industry. 

Company Analysis Report:
{company_report}

IMPORTANT GUIDELINES:
1. DO NOT include the company name in queries
2. Focus on the industry, use cases, and problem space
3. Include terms like "recommendation", "alternative", "best", "vs", "worth it", "experience", "struggling with", "looking for"
4. Add year markers (2024, 2025) for recent discussions
5. Mix technical and casual language that Reddit users would use
6. Target both r/specific_subreddits and general Reddit search
7. Include queries that will surface high-engagement discussions
8. Focus on queries that reveal market demand and user volume

Generate queries that will uncover:
- Authentic user discussions about their needs and challenges
- High-engagement threads with many participants
- Quantifiable demand signals and user interest levels
- Real pain points affecting multiple users"""

# Pydantic Models for Reddit Query Generation
class SearchQuery(BaseModel):
    query: str = Field(description="The actual search query string")
    intent: str = Field(description="What insights this query aims to uncover")
    target_subreddits: List[str] = Field(description="Suggested subreddits if applicable")

class RedditQueryOutput(BaseModel):
    search_queries: List[SearchQuery] = Field(min_items=5, max_items=5, description="List of 5 Reddit search queries")
    search_strategy: str = Field(description="Brief explanation of the overall search strategy")

# Convert to JSON schema for workflow usage
REDDIT_QUERY_OUTPUT_SCHEMA = RedditQueryOutput.model_json_schema()

# ============================================
# REDDIT RESEARCH PROMPTS & SCHEMAS
# ============================================

REDDIT_RESEARCH_SYSTEM_PROMPT = """You are a social listening analyst conducting market research on Reddit. Analyze the discussions and extract insights about:

1. User pain points and frustrations (with frequency indicators)
2. Feature requests and unmet needs (note how many users mention each)
3. Current solutions being used (with adoption levels)
4. Decision criteria for choosing solutions
5. Common complaints and issues (with severity and frequency)
6. Positive experiences and success stories
7. Industry trends and changes
8. Price sensitivity and budget considerations

IMPORTANT: Quantify user interest wherever possible:
- Note the number of upvotes, comments, or mentions
- Identify if topics are "very common", "common", "occasional", or "rare"
- Estimate the percentage or number of users affected
- Gauge discussion volume (high/medium/low)
- Track trending vs declining interest

Focus on authentic user voices and real experiences. Distinguish between different user segments when relevant."""

REDDIT_RESEARCH_USER_PROMPT_TEMPLATE = """Search Reddit for the following query and analyze the discussions to extract user insights:

Search Query: {search_query}
Query Intent: {query_intent}

Analyze the Reddit discussions found and extract insights about user needs, pain points, preferences, and experiences related to this topic. 

CRITICAL: Include quantifiable metrics wherever possible:
- Number of users discussing each topic
- Upvote counts on relevant posts/comments
- Frequency of mentions (very common, common, occasional, rare)
- Discussion volume trends
- Estimated percentage of users affected by issues

Focus on authentic user discussions and real-world experiences. Provide evidence of demand through discussion metrics."""

# Enums and Pydantic Models for Reddit Research
class FrequencyEnum(str, Enum):
    very_common = "very common"
    common = "common"
    occasional = "occasional"
    rare = "rare"

class SentimentEnum(str, Enum):
    very_positive = "very positive"
    positive = "positive"
    mixed = "mixed"
    negative = "negative"
    very_negative = "very negative"

class UserPainPoint(BaseModel):
    pain_point: str = Field(description="Description of the pain point")
    frequency: FrequencyEnum = Field(description="How frequently this pain point appears")
    user_quotes: List[str] = Field(max_items=2, description="Example user quotes")
    estimated_users_affected: Optional[str] = Field(None, description="Estimated number or percentage of users experiencing this")

class CurrentSolution(BaseModel):
    solution: str = Field(description="Name or description of the solution")
    pros_mentioned: List[str] = Field(description="Pros mentioned by users")
    cons_mentioned: List[str] = Field(description="Cons mentioned by users")
    user_adoption_level: Optional[str] = Field(None, description="How widely adopted this solution is")

class UserSegment(BaseModel):
    segment: str = Field(description="Segment name or description")
    characteristics: List[str] = Field(description="Characteristics of this segment")
    specific_needs: List[str] = Field(description="Specific needs of this segment")
    estimated_size: Optional[str] = Field(None, description="Estimated size of this segment based on discussion volume")

class SentimentInsights(BaseModel):
    overall_sentiment: SentimentEnum = Field(description="Overall sentiment from discussions")
    sentiment_drivers: List[str] = Field(description="Factors driving the sentiment")
    discussion_volume: Optional[str] = Field(None, description="Volume of discussions (high/medium/low)")

class RedditResearchOutput(BaseModel):
    query_searched: str = Field(description="The query that was searched")
    discussions_analyzed: Optional[int] = Field(None, description="Number of relevant discussions found")
    user_pain_points: List[UserPainPoint] = Field(description="Pain points and frustrations expressed by users")
    feature_requests: List[str] = Field(description="Features users want or wish existed")
    current_solutions: List[CurrentSolution] = Field(description="Solutions users currently use")
    decision_factors: List[str] = Field(description="Factors users consider when choosing solutions")
    user_segments: List[UserSegment] = Field(description="Different types of users identified")
    sentiment_insights: Optional[SentimentInsights] = Field(None, description="Sentiment analysis of discussions")
    trending_topics: List[str] = Field(description="Emerging trends or hot topics in discussions")
    engagement_metrics: Optional[str] = Field(None, description="Metrics on user engagement (upvotes, comments, etc.)")
    key_insights: List[str] = Field(max_items=5, description="Most important insights from this search")

# Convert to JSON schema for workflow usage
REDDIT_RESEARCH_OUTPUT_SCHEMA = RedditResearchOutput.model_json_schema()

# ============================================
# FINAL INSIGHTS & CONTENT PILLAR GENERATION PROMPTS & SCHEMAS
# ============================================

FINAL_INSIGHTS_SYSTEM_PROMPT = """You are a strategic content strategist and market intelligence analyst. Your task is to synthesize Reddit research with company analysis to create data-driven content pillars that align business goals with verified market needs.

Your analysis should:
1. Identify patterns across all Reddit research results with quantifiable demand indicators
2. Prioritize the most significant user needs based on frequency and impact
3. Merge market insights with company strengths and capabilities
4. Create strategic content pillars that address real market needs
5. Ensure each pillar is backed by market demand metrics
6. Align content strategy with business goals and growth objectives

Focus on creating content pillars that:
- Address verified market needs with measurable demand
- Leverage company strengths and differentiators
- Support business goals and growth objectives
- Have clear audience segments and use cases
- Include metrics for measuring success
- Are prioritized by market demand and business impact"""

FINAL_INSIGHTS_USER_PROMPT_TEMPLATE = """Analyze and synthesize the Reddit research with company analysis to create strategic content pillars that align business goals with verified market needs.

Reddit Research Results:
{reddit_research_results}

Company Analysis Report:
{company_analysis}

Company Goals:
{company_goals}

Create a comprehensive content strategy that:
1. Identifies the most critical user pain points and needs (with frequency/volume indicators)
2. Maps market opportunities to company strengths
3. Generates 5-7 strategic content pillars based on demand and alignment
4. Includes quantifiable metrics on user interest and demand for each pillar
5. Provides implementation roadmap and success metrics
6. Prioritizes pillars based on market demand and business impact

Each content pillar should be data-driven, actionable, and directly tied to both verified user needs (with demand indicators) and business objectives."""

# Enums and Pydantic Models for Final Insights with Content Pillars
class ImportanceEnum(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"

class DemandLevelEnum(str, Enum):
    very_high = "very high"
    high = "high"
    moderate = "moderate"
    emerging = "emerging"

class PriorityEnum(str, Enum):
    immediate = "immediate"
    short_term = "short-term"
    medium_term = "medium-term"
    long_term = "long-term"

class ImpactEnum(str, Enum):
    transformative = "transformative"
    high = "high"
    moderate = "moderate"

class CriticalUserNeed(BaseModel):
    need: str = Field(description="Description of the user need")
    importance: ImportanceEnum = Field(description="Importance level of this need")
    evidence: str = Field(description="Evidence supporting this need from Reddit research")
    opportunity: str = Field(description="Business opportunity related to this need")

class MarketOpportunity(BaseModel):
    opportunity: str = Field(description="Description of the opportunity")
    source_path_of_information: str = Field(description="Exact document path and section supporting this opportunity")
    reasoning_why_this_is_an_opportunity: str = Field(description="Specific data points justifying this opportunity")
    user_demand_level: DemandLevelEnum = Field(description="Level of user demand")
    supporting_metrics: Optional[str] = Field(None, description="Metrics supporting this opportunity (discussion volume, user count, etc.)")
    company_advantage: Optional[str] = Field(None, description="How company is positioned to capture this opportunity")

class ContentPillarAudience(BaseModel):
    segment_name: str = Field(description="Name of the target audience segment")
    key_characteristics: List[str] = Field(description="Key characteristics of this segment")
    pain_points: List[str] = Field(description="Main pain points from Reddit research")
    content_preferences: List[str] = Field(description="Content format and style preferences")

class ContentTopicCluster(BaseModel):
    topic: str = Field(description="Specific content topic")
    user_demand_indicator: str = Field(description="Demand level based on Reddit research (very high/high/moderate)")
    reddit_evidence: str = Field(description="Evidence from Reddit discussions supporting this topic")
    business_value: str = Field(description="How this topic supports business goals")
    content_formats: List[str] = Field(description="Recommended content formats (blog, whitepaper, etc.)")

class SuccessMetric(BaseModel):
    metric_name: str = Field(description="Name of the success metric")
    target_value: Optional[str] = Field(None, description="Target value for this metric")
    measurement_method: str = Field(description="How to measure this metric")

class ContentPillar(BaseModel):
    pillar_name: str = Field(description="Name of the content pillar")
    pillar_description: str = Field(description="Detailed description of the content pillar")
    market_need_addressed: str = Field(description="Primary market need this pillar addresses")
    source_path_of_information: str = Field(description="Exact document path and section supporting this pillar")
    reasoning_why_this_is_a_pillar: str = Field(description="Specific data points justifying this pillar")
    reddit_insights: List[str] = Field(description="Key insights from Reddit research supporting this pillar")
    company_strength_leveraged: str = Field(description="Company strength or differentiator this pillar leverages")
    target_audiences: List[ContentPillarAudience] = Field(description="Target audience segments for this pillar")
    topic_clusters: List[ContentTopicCluster] = Field(min_items=3, max_items=8, description="Specific topic clusters within this pillar")
    content_distribution: str = Field(description="Distribution across funnel stages (awareness, consideration, decision, retention)")
    competitive_advantage: str = Field(description="How this pillar creates competitive advantage")

class FinalInsightsOutput(BaseModel):
    executive_summary: str = Field(description="High-level summary combining market insights with content strategy")
    
    # # Company Overview Section
    # what_company_does: str = Field(description="Clear, concise description of what the company does and their core business")
    # target_audience: str = Field(description="Specific description of who the company is targeting (demographics, job titles, company types)")
    # what_company_offers: List[str] = Field(description="Specific products, services, or solutions the company offers")
    
    # Market Intelligence Section
    critical_user_needs: List[CriticalUserNeed] = Field(description="Most important unmet user needs with demand indicators")
    market_opportunities: List[MarketOpportunity] = Field(description="Specific opportunities with demand metrics and company positioning")
    market_demand_summary: str = Field(description="Summary of market demand indicators (discussion volumes, user counts, engagement metrics)")
    user_preference_trends: List[str] = Field(description="Emerging trends in user preferences from Reddit")
    
    # Content Strategy Section  
    content_pillars: List[ContentPillar] = Field(min_items=5, max_items=7, description="Strategic content pillars based on market demand and company strengths")
    
    # Implementation Section
    implementation_roadmap: List[str] = Field(description="Prioritized implementation sequence based on demand and impact")    


# Convert to JSON schema for workflow usage
FINAL_INSIGHTS_OUTPUT_SCHEMA = FinalInsightsOutput.model_json_schema()

# ============================================
# PERPLEXITY COMPANY RESEARCH PROMPTS & SCHEMAS
# ============================================

PERPLEXITY_COMPANY_RESEARCH_SYSTEM_PROMPT = """You are an expert business research analyst conducting comprehensive research about a company. Your task is to find detailed information about the company's value proposition, products, services, and general business information using web search.

Focus on finding:
1. Company's core value proposition and unique selling points
2. Main products and services offered
3. Target market and customer segments
4. Company background and founding story
5. Business model and revenue streams
6. Key differentiators and competitive advantages
7. Recent news, updates, or announcements
8. Industry position and market reputation
9. Technology stack or methodologies used
10. Company size, funding, and growth stage

Use authoritative sources and provide comprehensive insights based on publicly available information."""

PERPLEXITY_COMPANY_RESEARCH_USER_PROMPT_TEMPLATE = """Please conduct comprehensive research about the following company and provide detailed business intelligence:

Company Information:
{company_context}

Research Focus Areas:
1. Value Proposition: What makes this company unique and valuable to customers?
2. Products & Services: What exactly does the company offer? Include features, capabilities, and benefits.
3. Target Market: Who are their ideal customers? What market segments do they serve?
4. Business Model: How does the company make money? What's their pricing strategy?
5. Competitive Positioning: How do they position themselves against competitors?
6. Company Background: Founding story, mission, vision, key milestones
7. Technology & Innovation: What technologies or methodologies do they use?
8. Market Presence: Industry reputation, partnerships, customer base
9. Recent Developments: Latest news, product launches, or business updates
10. Growth & Funding: Company size, funding status, growth trajectory

Please provide thorough research findings with specific details and insights from credible sources."""

# Pydantic Models for Perplexity Research
class CompanyValueProposition(BaseModel):
    primary_value_prop: str = Field(description="Main value proposition statement")
    unique_selling_points: List[str] = Field(description="Key unique selling points")
    customer_benefits: List[str] = Field(description="Primary benefits for customers")

class ProductServiceInfo(BaseModel):
    product_name: str = Field(description="Name of the product or service")
    description: str = Field(description="Detailed description")
    key_features: List[str] = Field(description="Key features and capabilities")
    target_use_cases: List[str] = Field(description="Primary use cases")

class MarketPositioning(BaseModel):
    target_segments: List[str] = Field(description="Target market segments")
    ideal_customer_profile: str = Field(description="Description of ideal customer")
    market_size_info: Optional[str] = Field(None, description="Market size or addressable market information")
    competitive_landscape: List[str] = Field(description="Key competitors and positioning")

class BusinessModelInfo(BaseModel):
    revenue_model: str = Field(description="How the company generates revenue")
    pricing_strategy: Optional[str] = Field(None, description="Pricing approach or strategy")
    business_type: str = Field(description="Type of business (B2B, B2C, marketplace, etc.)")

class CompanyBackground(BaseModel):
    founding_story: Optional[str] = Field(None, description="Company founding and origin story")
    mission_statement: Optional[str] = Field(None, description="Company mission")
    vision_statement: Optional[str] = Field(None, description="Company vision")
    key_milestones: List[str] = Field(description="Important company milestones")

class TechnologyInfo(BaseModel):
    technology_stack: List[str] = Field(description="Technologies used by the company")
    innovation_areas: List[str] = Field(description="Areas of innovation or R&D focus")
    methodologies: List[str] = Field(description="Business or operational methodologies")

class MarketPresence(BaseModel):
    industry_reputation: str = Field(description="Company's reputation in the industry")
    partnerships: List[str] = Field(description="Key partnerships or integrations")
    customer_testimonials: List[str] = Field(description="Customer testimonials or case studies")
    awards_recognition: List[str] = Field(description="Awards or industry recognition")

class RecentDevelopments(BaseModel):
    latest_news: List[str] = Field(description="Recent news or announcements")
    product_updates: List[str] = Field(description="Recent product launches or updates")
    business_developments: List[str] = Field(description="Recent business developments")

class PerplexityCompanyResearchOutput(BaseModel):
    value_proposition: CompanyValueProposition = Field(description="Company's value proposition details")
    products_services: List[ProductServiceInfo] = Field(description="Products and services offered")
    market_positioning: MarketPositioning = Field(description="Market positioning and target audience")
    business_model: BusinessModelInfo = Field(description="Business model and revenue information")
    company_background: CompanyBackground = Field(description="Company background and history")
    technology_info: TechnologyInfo = Field(description="Technology and innovation details")
    market_presence: MarketPresence = Field(description="Market presence and reputation")
    recent_developments: RecentDevelopments = Field(description="Recent news and developments")

# Convert to JSON schema for workflow usage
PERPLEXITY_COMPANY_RESEARCH_OUTPUT_SCHEMA = PerplexityCompanyResearchOutput.model_json_schema() 