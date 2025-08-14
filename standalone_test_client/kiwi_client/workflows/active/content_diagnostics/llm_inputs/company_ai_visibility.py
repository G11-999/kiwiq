import json
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# --- 3. Competitive Analysis ("Perplexity Analysis") ---
COMPETITIVE_ANALYSIS_SYSTEM_PROMPT = (
    "You are a business intelligence analyst tasked with creating comprehensive competitive "
    "landscape analysis. Your role is to extract and synthesize information about companies "
    "and their competitive environment from provided company documentation.\n\n"
    "Analyze the provided company documentation and generate a structured competitive analysis "
    "that covers the target company and its main competitors. Focus on factual, objective analysis "
    "that can be used for strategic planning and market positioning.\n\n"
    "For each entity (company and competitors), provide clear, concise information about their "
    "market position, core offerings, and unique value propositions."
)

COMPETITIVE_ANALYSIS_USER_PROMPT_TEMPLATE = (
    "Based on the provided company documentation, create a comprehensive competitive analysis following this structure:\n\n"
    "1. Company Analysis:\n"
    "   - Overview: Brief description of the company, its mission, and market position\n"
    "   - Key Offerings: Primary products/services and their main features\n"
    "   - Value Proposition: Unique benefits and competitive advantages\n\n"
    "2. Competitor Analysis (Top 3):\n"
    "   - Overview\n"
    "   - Key Offerings\n"
    "   - Value Proposition\n\n"
    "Company Document Data (verbatim JSON):\n{blog_company_data}"
)

# Simplified JSON schema (as Pydantic BaseModels) for competitive analysis output
class EntityAnalysis(BaseModel):
    """Structured analysis for a single entity (company or competitor)."""
    overview: str = Field(description="Brief description and market position")
    key_offerings: str = Field(description="Primary products/services and main features")
    value_proposition: str = Field(description="Unique benefits and competitive advantages")


class CompetitiveAnalysis(BaseModel):
    """Competitive analysis for the company and top 3 competitors."""
    company: EntityAnalysis
    competitor_1: EntityAnalysis
    competitor_2: EntityAnalysis
    competitor_3: EntityAnalysis


COMPETITIVE_ANALYSIS_SCHEMA = CompetitiveAnalysis.model_json_schema()


# --- 4. Query Generation ---
# 4.1 Blog Posts Coverage
BLOG_COVERAGE_SYSTEM_PROMPT = (
    "You are a content strategy analyst specializing in industry blog visibility analysis. "
    "Your task is to generate search queries that potential customers and industry stakeholders "
    "would use when seeking information about topics covered by industry blogs.\n\n"
    "Generate queries that represent genuine user search intent for industry-related information, "
    "best practices, solutions, and insights. These queries should be the type that would naturally "
    "return blog posts, articles, and thought leadership content from companies in the space.\n\n"
    "Focus on informational and educational queries that demonstrate thought leadership opportunities "
    "and content gaps in the industry."
)

BLOG_COVERAGE_USER_PROMPT_TEMPLATE = (
    "Based on the company documentation and competitive analysis provided, generate EXACTLY 15 search queries in total — not 14, not 16. "
    "Do not exceed or fall short; if your draft has more or fewer, adjust to output exactly 15.\n\n"
    "The queries should cover:\n"
    "- Industry trends and insights\n"
    "- Best practices and how-to content\n"
    "- Problem-solving and solution-oriented content\n"
    "- Comparison and evaluation content\n"
    "- Educational and informational content\n\n"
    "Organize the queries into logical segments as appropriate. Regardless of segmentation, the TOTAL number of queries must be EXACTLY 15 — not even one more.\n\n"
    "Company Document Data (verbatim JSON):\n{blog_company_data}\n\n"
    "Competitive Analysis (verbatim JSON):\n{competitive_analysis}"
)

# For scraper compatibility, represent each segment as a list[str]
class BlogCoverageQueries(BaseModel):
    """Query templates grouped by searcher intent for blog coverage analysis."""
    industry_trends: List[str] = Field(description="Queries about industry trends and insights")
    best_practices: List[str] = Field(description="Queries about best practices and how-to content")
    solution_oriented: List[str] = Field(description="Queries about solutions to problems")
    educational_content: List[str] = Field(description="Queries about educational/informational topics")


BLOG_COVERAGE_QUERIES_SCHEMA = BlogCoverageQueries.model_json_schema()

# 4.2 Company and Competitor Analysis
COMPANY_COMP_SYSTEM_PROMPT = (
    "You are a competitive intelligence analyst tasked with generating search queries that buyers and researchers use when "
    "evaluating companies and their competitive landscape.\n\n"
    "Use the provided query templates as reference patterns and generate specific queries tailored to the company and competitors from the documentation. "
    "Focus on queries that represent genuine buyer research behavior - the questions they ask when comparing solutions, evaluating vendors, "
    "and making purchase decisions."
)

COMPANY_COMP_USER_PROMPT_TEMPLATE = (
    "Using the competitive analysis and company documentation provided, generate EXACTLY 15 specific search queries — not 14, not 16 — organized into logical segments based on these reference templates:\n\n"
    "Reference Query Templates:\n"
    "- Company Overview: \"What is (entity_name)?\", \"Tell me about (entity_name)\"\n"
    "- Products/Services: \"What products does (entity_name) offer?\", \"(entity_name) features and capabilities\"\n"
    "- Competitive Analysis: \"(entity_name) vs competitors\", \"What are alternatives to (entity_name)?\"\n"
    "- Customer Reviews: \"(entity_name) customer reviews\", \"What do users say about (entity_name)?\"\n"
    "- Technical Integration: \"(entity_name) integrations\", \"How to implement (entity_name)\"\n\n"
    "Organize into 5 segments with EXACTLY 3 queries each (total 15). The TOTAL number of queries must be EXACTLY 15 — not even one more.\n\n"
    
    
    "Company Document Data (verbatim JSON):\n{blog_company_data}\n\n"
    "Competitive Analysis (verbatim JSON):\n{competitive_analysis}"
)

class CompanyCompetitorQueries(BaseModel):
    """Query templates grouped by buyer research categories."""
    company_overview: List[str] = Field(description="Overview-oriented queries about the entity")
    products_services: List[str] = Field(description="Queries about products/services and capabilities")
    competitive_analysis: List[str] = Field(description="Queries comparing with competitors / alternatives")
    customer_reviews: List[str] = Field(description="Queries about customer reviews and feedback")
    technical_integration: List[str] = Field(description="Queries about integrations and implementation")


COMPANY_COMP_QUERIES_SCHEMA = CompanyCompetitorQueries.model_json_schema()

# 4.3 Executive Visibility
EXEC_VISIBILITY_SYSTEM_PROMPT = (
    "You are a professional research analyst specializing in executive visibility and thought leadership analysis. "
    "Your task is to generate search queries that buyers, partners, and industry stakeholders use when researching executives and business leaders.\n\n"
    "Generate queries that represent how people search for information about executives when evaluating potential partnerships, investment opportunities, "
    "speaking engagements, or business relationships. Focus on queries that would surface professional reputation, expertise, and industry presence."
)

EXEC_VISIBILITY_USER_PROMPT_TEMPLATE = (
    "Based on the executive profile information and scraped LinkedIn data provided, generate EXACTLY 10 search queries in total — not 9, not 11 — organized into logical segments that represent how buyers and stakeholders research executives.\n\n"
    "The queries should cover:\n"
    "- Professional background and expertise\n"
    "- Industry thought leadership and presence\n"
    "- Company association and role\n"
    "- Speaking and content contributions\n"
    "- Professional reputation and achievements\n\n"
    "Organize into logical segments as appropriate. Regardless of segmentation, the TOTAL number of queries must be EXACTLY 10 — not even one more.\n\n"
    "LinkedIn User Profile (verbatim JSON):\n{linkedin_user_profile}\n\n"
    "LinkedIn Scraped Profile (verbatim JSON):\n{linkedin_scraped_profile}"
)

class ExecutiveVisibilityQueries(BaseModel):
    """Query templates for researching executives and leaders."""
    professional_background: List[str] = Field(description="Queries about professional background and expertise")
    thought_leadership: List[str] = Field(description="Queries about industry thought leadership and presence")
    company_association: List[str] = Field(description="Queries about role and company association")
    reputation_achievements: List[str] = Field(description="Queries about reputation, achievements, and recognition")


EXEC_VISIBILITY_QUERIES_SCHEMA = ExecutiveVisibilityQueries.model_json_schema()


# --- 6. Report Generation ---
BLOG_COVERAGE_REPORT_SYSTEM_PROMPT = (
    "You are a content intelligence analyst specializing in blog visibility and thought leadership analysis across answer engines. "
    "Analyze query results to identify content visibility patterns, assess competitor performance, identify gaps and opportunities, and provide quantitative metrics."
)
BLOG_COVERAGE_REPORT_USER_PROMPT_TEMPLATE = (
    "Analyze the collected search results from blog coverage queries and generate a comprehensive Blog Coverage Report.\n\n"
    "Inputs Provided (verbatim JSON):\n{loaded_query_results}\n\n"
    "Include quantitative metrics and prioritized recommendations."
)

# Use explicit models made of simple fields for the report
class AnalysisSummary(BaseModel):
    summary_text: str = Field(description="Concise overview of findings")
    key_findings: List[str] = Field(description="Bulleted key insights")
    overall_visibility_score: Optional[float] = Field(default=None, description="Overall visibility score (0-100)")


class QueryLevelAnalysisItem(BaseModel):
    query: str = Field(description="The query analyzed")
    top_sources: List[str] = Field(description="Top sources returned for the query")
    client_presence: str = Field(description="How the client appears for this query")
    competitor_mentions: List[str] = Field(description="Competitors mentioned in top results")


class CompetitorPresenceItem(BaseModel):
    competitor_name: str = Field(description="Name of the competitor")
    presence_score: Optional[float] = Field(default=None, description="Score of competitor presence (0-100)")
    notable_queries: List[str] = Field(description="Queries where competitor appears prominently")


class ContentOpportunityItem(BaseModel):
    opportunity: str = Field(description="Content opportunity identified")
    rationale: str = Field(description="Why this opportunity matters")
    priority: Optional[str] = Field(default=None, description="Priority level, e.g., High/Medium/Low")


class VisibilityGapItem(BaseModel):
    gap: str = Field(description="Identified gap in visibility or coverage")
    impact: Optional[str] = Field(default=None, description="Business or visibility impact")
    suggested_action: Optional[str] = Field(default=None, description="Action to address the gap")


class QuantitativeMetrics(BaseModel):
    num_queries: int = Field(description="Total number of queries analyzed")
    client_appearances: int = Field(description="Count of times client appears in results")
    competitor_appearances: int = Field(description="Count of times competitors appear in results")
    avg_rank: Optional[float] = Field(default=None, description="Average rank/position of client when present")


class BlogCoverageReport(BaseModel):
    analysis_summary: AnalysisSummary
    query_level_analysis: Optional[List[QueryLevelAnalysisItem]] = None
    competitor_presence: Optional[List[CompetitorPresenceItem]] = None
    content_opportunities: Optional[List[ContentOpportunityItem]] = None
    visibility_gaps: Optional[List[VisibilityGapItem]] = None
    quantitative_metrics: Optional[QuantitativeMetrics] = None
    recommendations: List[str]


BLOG_COVERAGE_REPORT_SCHEMA = BlogCoverageReport.model_json_schema()

COMPANY_COMP_REPORT_SYSTEM_PROMPT = (
    "You are a competitive intelligence analyst specializing in digital presence and market positioning analysis across answer engines. "
    "Analyze buyer intent patterns, competitive positioning, gaps, and provide strategic recommendations."
)
COMPANY_COMP_REPORT_USER_PROMPT_TEMPLATE = (
    "Analyze the collected search results from company and competitor queries to generate a comprehensive Company & Competitor Analysis Report.\n\n"
    "Inputs Provided (verbatim JSON):\n{loaded_query_results}\n\n"
    "Focus on buyer perspective and quantitative backing for insights."
)

class CompanyAnalysisSummary(BaseModel):
    summary_text: str = Field(description="Concise overview of findings")
    key_findings: List[str] = Field(description="Bulleted key insights")


class ClientPositioningAnalysis(BaseModel):
    positioning_summary: str = Field(description="Summary of client's market positioning")
    strengths: List[str] = Field(description="Client strengths")
    weaknesses: List[str] = Field(description="Client weaknesses")


class CompetitorAnalysisItem(BaseModel):
    name: str = Field(description="Competitor name")
    positioning: str = Field(description="How the competitor is positioned")
    strengths: List[str] = Field(description="Competitor strengths")
    weaknesses: List[str] = Field(description="Competitor weaknesses")


class BuyerIntentItem(BaseModel):
    pattern: str = Field(description="Observed buyer intent pattern")
    representative_queries: List[str] = Field(description="Queries representing the pattern")
    implications: str = Field(description="Implications for the buyer journey")


class CompetitiveGapItem(BaseModel):
    gap: str = Field(description="Competitive gap identified")
    risk: Optional[str] = Field(default=None, description="Risk associated with the gap")
    opportunity: Optional[str] = Field(default=None, description="Opportunity associated with the gap")


class MarketPerceptionInsights(BaseModel):
    perception_summary: str = Field(description="Summary of market perception")
    sentiment: Optional[str] = Field(default=None, description="Overall sentiment descriptor")
    common_themes: List[str] = Field(description="Common themes observed")


class PositioningOpportunityItem(BaseModel):
    opportunity: str = Field(description="Positioning opportunity")
    expected_impact: Optional[str] = Field(default=None, description="Expected impact of seizing the opportunity")
    suggested_actions: List[str] = Field(description="Actions to seize the opportunity")


class QueryPerformanceMetrics(BaseModel):
    num_queries: int = Field(description="Total number of queries analyzed")
    client_appearances: int = Field(description="Count of times client appears in results")
    avg_rank: Optional[float] = Field(default=None, description="Average rank/position of client when present")
    share_of_voice_pct: Optional[float] = Field(default=None, description="Estimated share of voice percentage")


class CompanyCompetitorReport(BaseModel):
    analysis_summary: CompanyAnalysisSummary
    client_positioning_analysis: Optional[ClientPositioningAnalysis] = None
    competitor_analysis: Optional[List[CompetitorAnalysisItem]] = None
    buyer_intent_analysis: Optional[List[BuyerIntentItem]] = None
    competitive_gaps: Optional[List[CompetitiveGapItem]] = None
    market_perception_insights: Optional[MarketPerceptionInsights] = None
    positioning_opportunities: Optional[List[PositioningOpportunityItem]] = None
    query_performance_metrics: Optional[QueryPerformanceMetrics] = None
    recommendations: List[str]


COMPANY_COMP_REPORT_SCHEMA = CompanyCompetitorReport.model_json_schema()

EXEC_VISIBILITY_REPORT_SYSTEM_PROMPT = (
    "You are an executive visibility analyst specializing in personal brand and thought leadership assessment across AI-powered answer engines. "
    "Assess visibility, positioning versus leaders, and provide actionable recommendations."
)
EXEC_VISIBILITY_REPORT_USER_PROMPT_TEMPLATE = (
    "Analyze the collected search results from executive visibility queries to generate an Executive Visibility Report.\n\n"
    "Inputs Provided (verbatim JSON):\n{loaded_query_results}\n\n"
    "Focus on professional reputation, opportunities, and quantitative metrics."
)

class MarketPositioning(BaseModel):
    positioning_summary: str = Field(description="Summary of executive's positioning versus peers")
    strengths: List[str] = Field(description="Strengths of the executive's presence")
    areas_to_improve: List[str] = Field(description="Areas needing improvement")
    relative_rank: Optional[int] = Field(default=None, description="Relative rank vs named peers if available")


class CompetitorThreatItem(BaseModel):
    name: str = Field(description="Name of competing executive/leader")
    threat_summary: str = Field(description="Summary of competitive threat")


class CriticalGapItem(BaseModel):
    gap: str = Field(description="Critical gap in executive visibility")
    urgency: Optional[str] = Field(default=None, description="Urgency level")


class MarketOpportunityItem(BaseModel):
    opportunity: str = Field(description="Market opportunity for executive visibility")
    channel: Optional[str] = Field(default=None, description="Primary channel for opportunity (e.g., LinkedIn, Podcasts)")
    suggested_action: Optional[str] = Field(default=None, description="Action to capture opportunity")


class RecentMovementItem(BaseModel):
    date: Optional[str] = Field(default=None, description="Date of the movement, if known")
    description: str = Field(description="Description of the movement or update")


class ExecutiveVisibilityReport(BaseModel):
    market_positioning: MarketPositioning
    competitor_threats: Optional[List[CompetitorThreatItem]] = None
    critical_gaps: Optional[List[CriticalGapItem]] = None
    market_opportunities: Optional[List[MarketOpportunityItem]] = None
    recent_movements: Optional[List[RecentMovementItem]] = None
    competitive_outlook: Optional[str] = None
    immediate_priorities: List[str]
    next_analysis_date: Optional[str] = None


EXEC_VISIBILITY_REPORT_SCHEMA = ExecutiveVisibilityReport.model_json_schema() 