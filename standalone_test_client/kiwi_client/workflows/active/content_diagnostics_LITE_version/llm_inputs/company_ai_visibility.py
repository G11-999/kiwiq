# import json
# from pydantic import BaseModel, Field
# from typing import List, Dict, Any, Optional

# # --- 3. Competitive Analysis ("Perplexity Analysis") ---
# COMPETITIVE_ANALYSIS_SYSTEM_PROMPT = (
#     "You are a business intelligence analyst tasked with creating comprehensive competitive "
#     "landscape analysis using ONLY the provided company documentation.\n\n"
#     "Guidelines:\n"
#     "- Be factual and neutral. Do not speculate beyond the provided data.\n"
#     "- If a required detail is missing, write 'Not specified'. Do not hallucinate.\n"
#     "- Keep each section concise, actionable, and free of marketing language.\n"
#     "- Use consistent terminology for entities across the output.\n"
#     "- Structure the output to exactly match the JSON schema provided.\n"
#     "- Prefer short sentences and bullet-style phrasing.\n\n"
#     "Deliverables:\n"
#     "- A structured analysis for the company and exactly three competitors covering overview, key offerings, and value propositions."
# )

# COMPETITIVE_ANALYSIS_USER_PROMPT_TEMPLATE = (
#     "Based on the provided company documentation, create a comprehensive competitive analysis following this structure:\n\n"
#     "1) Company Analysis (target entity):\n"
#     "   - Overview: Brief description, mission (if present), and market position\n"
#     "   - Key Offerings: Primary products/services and their main features\n"
#     "   - Value Proposition: Unique benefits and competitive advantages\n\n"
#     "2) Competitor Analysis (Top 3): For each competitor, provide the same three sections as above.\n\n"
#     "Rules:\n"
#     "- Use only evidence present in the documentation. Cite names consistently.\n"
#     "- If information is absent, write 'Not specified'.\n"
#     "- Keep each bullet 1–2 lines.\n\n"
#     "Company Document Data (verbatim JSON):\n{blog_company_data}"
# )

# # Simplified JSON schema (as Pydantic BaseModels) for competitive analysis output
# class EntityAnalysis(BaseModel):
#     """Structured analysis for a single entity (company or competitor)."""
#     overview: str = Field(description="Brief description and market position")
#     key_offerings: str = Field(description="Primary products/services and main features")
#     value_proposition: str = Field(description="Unique benefits and competitive advantages")


# class CompetitiveAnalysis(BaseModel):
#     """Competitive analysis for the company and top 3 competitors."""
#     company: EntityAnalysis
#     competitor_1: EntityAnalysis
#     competitor_2: EntityAnalysis
#     competitor_3: EntityAnalysis


# COMPETITIVE_ANALYSIS_SCHEMA = CompetitiveAnalysis.model_json_schema()


# # --- 4. Query Generation ---
# # 4.1 Blog Posts Coverage
# BLOG_COVERAGE_SYSTEM_PROMPT = (
#     "You are a content strategy analyst specializing in industry blog visibility analysis.\n\n"
#     "Objective:\n"
#     "- Generate search queries that real users would issue when seeking informational, educational, and thought-leadership content likely to surface blog posts.\n\n"
#     "Guidelines:\n"
#     "- Prioritize informational, how-to, best-practices, and comparison queries.\n"
#     "- Avoid brand-only navigational queries unless relevant to learning (e.g., '(brand) best practices' is acceptable).\n"
#     "- Avoid near-duplicates; ensure coverage diversity across subtopics and intents.\n"
#     "- Phrase queries naturally (questions or short statements).\n"
#     "- Keep each query 4–12 words; avoid punctuation unless needed.\n"
#     "- Use only details from the provided data; no hallucinations."
# )

# BLOG_COVERAGE_USER_PROMPT_TEMPLATE = (
#     "Based on the company documentation and competitive analysis provided, generate EXACTLY 15 search queries in total — not 14, not 16. "
#     "Do not exceed or fall short; if your draft has more or fewer, adjust to output exactly 15.\n\n"
#     "Coverage Requirements:\n"
#     "- Include a balance of: industry trends, best practices/how-to, problem-solving/solutions, comparisons/evaluations, and educational/informational.\n"
#     "- Avoid repeating the same core phrasing with minor token changes.\n"
#     "- Ensure queries plausibly return blog articles or thought leadership pages.\n\n"
#     "Output Format (JSON only, no commentary):\n"
#     "- Conform to the BlogCoverageQueries schema fields: industry_trends, best_practices, solution_oriented, educational_content.\n"
#     "- The sum of all list lengths MUST equal 15.\n\n"
#     "Company Document Data (verbatim JSON):\n{blog_company_data}\n\n"
#     "Competitive Analysis (verbatim JSON):\n{competitive_analysis}"
# )

# # For scraper compatibility, represent each segment as a list[str]
# class BlogCoverageQueries(BaseModel):
#     """Query templates grouped by searcher intent for blog coverage analysis."""
#     industry_trends: List[str] = Field(description="Queries about industry trends and insights")
#     best_practices: List[str] = Field(description="Queries about best practices and how-to content")
#     solution_oriented: List[str] = Field(description="Queries about solutions to problems")
#     educational_content: List[str] = Field(description="Queries about educational/informational topics")


# BLOG_COVERAGE_QUERIES_SCHEMA = BlogCoverageQueries.model_json_schema()

# # 4.2 Company and Competitor Analysis
# COMPANY_COMP_SYSTEM_PROMPT = (
#     "You are a competitive intelligence analyst tasked with generating buyer-research queries that reflect how evaluators compare vendors, "
#     "understand offerings, assess social proof, and plan implementations.\n\n"
#     "Guidelines:\n"
#     "- Use natural, realistic buyer phrasing.\n"
#     "- Ensure coverage of: overview, products/services, competitive comparisons, customer reviews, and technical integration.\n"
#     "- Avoid near-duplicates and salesy language.\n"
#     "- When referencing entities, use the exact names from the documentation.\n"
#     "- Use only supported facts from the input."
# )

# COMPANY_COMP_USER_PROMPT_TEMPLATE = (
#     "Using the competitive analysis and company documentation provided, generate EXACTLY 15 specific search queries — not 14, not 16 — organized into logical segments based on these reference templates:\n\n"
#     "Reference Query Templates (examples, adapt to entities):\n"
#     "- Company Overview: 'What is (entity_name)?', 'Tell me about (entity_name)'\n"
#     "- Products/Services: 'What products does (entity_name) offer?', '(entity_name) features and capabilities'\n"
#     "- Competitive Analysis: '(entity_name) vs competitors', 'What are alternatives to (entity_name)?'\n"
#     "- Customer Reviews: '(entity_name) customer reviews', 'What do users say about (entity_name)?'\n"
#     "- Technical Integration: '(entity_name) integrations', 'How to implement (entity_name)'\n\n"
#     "Organization Requirements:\n"
#     "- EXACTLY 5 segments with EXACTLY 3 queries each (total 15).\n"
#     "- Map segments to schema fields in order: company_overview, products_services, competitive_analysis, customer_reviews, technical_integration.\n"
#     "- Replace (entity_name) with the client company or named competitors as appropriate.\n"
#     "- Avoid duplicates across segments.\n\n"
#     "Output as JSON only, conforming to CompanyCompetitorQueries.\n\n"
#     "Company Document Data (verbatim JSON):\n{blog_company_data}\n\n"
#     "Competitive Analysis (verbatim JSON):\n{competitive_analysis}"
# )

# class CompanyCompetitorQueries(BaseModel):
#     """Query templates grouped by buyer research categories."""
#     company_overview: List[str] = Field(description="Overview-oriented queries about the entity")
#     products_services: List[str] = Field(description="Queries about products/services and capabilities")
#     competitive_analysis: List[str] = Field(description="Queries comparing with competitors / alternatives")
#     customer_reviews: List[str] = Field(description="Queries about customer reviews and feedback")
#     technical_integration: List[str] = Field(description="Queries about integrations and implementation")


# COMPANY_COMP_QUERIES_SCHEMA = CompanyCompetitorQueries.model_json_schema()

# # --- 6. Report Generation ---
# BLOG_COVERAGE_REPORT_SYSTEM_PROMPT = (
#     "You are a content intelligence analyst specializing in blog visibility and thought leadership analysis across answer engines. "
#     "Analyze query results from Perplexity, Google, and OpenAI to identify content visibility patterns, assess competitor performance, "
#     "identify gaps and opportunities, and provide quantitative metrics. Provide both an overall analysis and provider-specific analysis "
#     "for each of the three providers.\n\n"
#     "Methodology Constraints:\n"
#     "- Use only the provided results. Do not infer ranks or sources not present.\n"
#     "- When counting appearances, deduplicate by canonical domain where applicable.\n"
#     "- Explain scoring or estimation logic succinctly when reporting metrics (e.g., share of voice).\n"
#     "- If data is insufficient for a metric, state 'Insufficient data'.\n"
#     "- Keep recommendations specific and prioritized."
# )
# BLOG_COVERAGE_REPORT_USER_PROMPT_TEMPLATE = (
#     "Analyze the collected search results from blog coverage queries and generate a comprehensive Blog Coverage Report.\n\n"
#     "Inputs Provided (verbatim JSON):\n{loaded_query_results}\n\n"
#     "Your report MUST include: (1) an overall analysis aggregating across all providers, and (2) provider-specific analyses for EXACTLY these three providers: \n"
#     "- perplexity\n- google\n- openai\n\n"
#     "Requirements:\n"
#     "- Output JSON only that conforms to BlogCoverageReport.\n"
#     "- In 'query_level_analysis', include top_sources as normalized source labels (e.g., domains or publishers).\n"
#     "- Quantitative metrics must include num_queries, client_appearances, competitor_appearances, and avg_rank (if available).\n"
#     "- Provide 5–8 prioritized recommendations, each actionable.\n"
#     "- Provider names must match exactly: 'perplexity', 'google', 'openai'."
# )

# # Use explicit models made of simple fields for the report
# class AnalysisSummary(BaseModel):
#     summary_text: str = Field(description="Concise overview of findings")
#     key_findings: List[str] = Field(description="Bulleted key insights")
#     overall_visibility_score: float = Field(description="Overall visibility score (0-100)")


# class QueryLevelAnalysisItem(BaseModel):
#     query: str = Field(description="The query analyzed")
#     top_sources: List[str] = Field(description="Top sources returned for the query")
#     client_presence: str = Field(description="How the client appears for this query")
#     competitor_mentions: List[str] = Field(description="Competitors mentioned in top results")


# class CompetitorPresenceItem(BaseModel):
#     competitor_name: str = Field(description="Name of the competitor")
#     presence_score: float = Field(description="Score of competitor presence (0-100)")
#     notable_queries: List[str] = Field(description="Queries where competitor appears prominently")


# class ContentOpportunityItem(BaseModel):
#     opportunity: str = Field(description="Content opportunity identified")
#     rationale: str = Field(description="Why this opportunity matters")
#     priority: str = Field(description="Priority level, e.g., High/Medium/Low")


# class VisibilityGapItem(BaseModel):
#     gap: str = Field(description="Identified gap in visibility or coverage")
#     impact: str = Field(description="Business or visibility impact")
#     suggested_action: str = Field(description="Action to address the gap")


# class QuantitativeMetrics(BaseModel):
#     num_queries: int = Field(description="Total number of queries analyzed")
#     client_appearances: int = Field(description="Count of times client appears in results")
#     competitor_appearances: int = Field(description="Count of times competitors appear in results")
#     avg_rank: float = Field(description="Average rank/position of client when present")


# class ProviderBlogCoverageAnalysis(BaseModel):
#     provider_name: str = Field(description="Name of the provider. One of: perplexity, google, openai")
#     analysis_summary: AnalysisSummary
#     query_level_analysis: List[QueryLevelAnalysisItem]
#     competitor_presence: List[CompetitorPresenceItem]
#     content_opportunities: List[ContentOpportunityItem]
#     visibility_gaps: List[VisibilityGapItem]
#     quantitative_metrics: QuantitativeMetrics
#     recommendations: List[str]


# class BlogCoverageReport(BaseModel):
#     analysis_summary: AnalysisSummary
#     query_level_analysis: List[QueryLevelAnalysisItem]
#     competitor_presence: List[CompetitorPresenceItem]
#     content_opportunities: List[ContentOpportunityItem]
#     visibility_gaps: List[VisibilityGapItem]
#     quantitative_metrics: QuantitativeMetrics
#     recommendations: List[str]
#     provider_specific_analysis: List[ProviderBlogCoverageAnalysis]


# BLOG_COVERAGE_REPORT_SCHEMA = BlogCoverageReport.model_json_schema()

# COMPANY_COMP_REPORT_SYSTEM_PROMPT = (
#     "You are a competitive intelligence analyst specializing in digital presence and market positioning analysis across answer engines. "
#     "Analyze buyer intent patterns, competitive positioning, gaps, and provide strategic recommendations using results from Perplexity, Google, and OpenAI. "
#     "Provide both an overall analysis and provider-specific analysis for each of the three providers.\n\n"
#     "Methodology Constraints:\n"
#     "- Use only the provided results and entities.\n"
#     "- Clearly distinguish client vs competitor presence and positioning.\n"
#     "- Quantify where possible (counts, estimated share of voice), and explain estimation briefly.\n"
#     "- If evidence is lacking, mark items as 'Insufficient data' rather than guessing."
# )
# COMPANY_COMP_REPORT_USER_PROMPT_TEMPLATE = (
#     "Analyze the collected search results from company and competitor queries to generate a comprehensive Company & Competitor Analysis Report.\n\n"
#     "Inputs Provided (verbatim JSON):\n{loaded_query_results}\n\n"
#     "Your report MUST include: (1) an overall analysis aggregating across all providers, and (2) provider-specific analyses for EXACTLY these three providers: \n"
#     "- perplexity\n- google\n- openai\n\n"
#     "Requirements:\n"
#     "- Output JSON only that conforms to CompanyCompetitorReport.\n"
#     "- Populate buyer_intent_analysis with clear patterns and representative queries.\n"
#     "- In client_positioning_analysis and competitor_analysis, list strengths/weaknesses as short bullets tied to observed evidence.\n"
#     "- Provide 5–8 prioritized recommendations that are specific and feasible.\n"
#     "- Provider names must match exactly: 'perplexity', 'google', 'openai'."
# )

# class CompanyAnalysisSummary(BaseModel):
#     summary_text: str = Field(description="Concise overview of findings")
#     key_findings: List[str] = Field(description="Bulleted key insights")


# class ClientPositioningAnalysis(BaseModel):
#     positioning_summary: str = Field(description="Summary of client's market positioning")
#     strengths: List[str] = Field(description="Client strengths")
#     weaknesses: List[str] = Field(description="Client weaknesses")


# class CompetitorAnalysisItem(BaseModel):
#     name: str = Field(description="Competitor name")
#     positioning: str = Field(description="How the competitor is positioned")
#     strengths: List[str] = Field(description="Competitor strengths")
#     weaknesses: List[str] = Field(description="Competitor weaknesses")


# class BuyerIntentItem(BaseModel):
#     pattern: str = Field(description="Observed buyer intent pattern")
#     representative_queries: List[str] = Field(description="Queries representing the pattern")
#     implications: str = Field(description="Implications for the buyer journey")


# class CompetitiveGapItem(BaseModel):
#     gap: str = Field(description="Competitive gap identified")
#     risk: str = Field(description="Risk associated with the gap")
#     opportunity: str = Field(description="Opportunity associated with the gap")


# class MarketPerceptionInsights(BaseModel):
#     perception_summary: str = Field(description="Summary of market perception")
#     sentiment: str = Field(description="Overall sentiment descriptor")
#     common_themes: List[str] = Field(description="Common themes observed")


# class PositioningOpportunityItem(BaseModel):
#     opportunity: str = Field(description="Positioning opportunity")
#     expected_impact: str = Field(description="Expected impact of seizing the opportunity")
#     suggested_actions: List[str] = Field(description="Actions to seize the opportunity")


# class QueryPerformanceMetrics(BaseModel):
#     num_queries: int = Field(description="Total number of queries analyzed")
#     client_appearances: int = Field(description="Count of times client appears in results")
#     avg_rank: float = Field(description="Average rank/position of client when present")
#     share_of_voice_pct: float = Field(description="Estimated share of voice percentage (0-100)")


# class ProviderCompanyCompetitorAnalysis(BaseModel):
#     provider_name: str = Field(description="Name of the provider. One of: perplexity, google, openai")
#     analysis_summary: CompanyAnalysisSummary
#     client_positioning_analysis: ClientPositioningAnalysis
#     competitor_analysis: List[CompetitorAnalysisItem]
#     buyer_intent_analysis: List[BuyerIntentItem]
#     competitive_gaps: List[CompetitiveGapItem]
#     market_perception_insights: MarketPerceptionInsights
#     positioning_opportunities: List[PositioningOpportunityItem]
#     query_performance_metrics: QueryPerformanceMetrics
#     recommendations: List[str]


# class CompanyCompetitorReport(BaseModel):
#     analysis_summary: CompanyAnalysisSummary
#     client_positioning_analysis: ClientPositioningAnalysis
#     competitor_analysis: List[CompetitorAnalysisItem]
#     buyer_intent_analysis: List[BuyerIntentItem]
#     competitive_gaps: List[CompetitiveGapItem]
#     market_perception_insights: MarketPerceptionInsights
#     positioning_opportunities: List[PositioningOpportunityItem]
#     query_performance_metrics: QueryPerformanceMetrics
#     recommendations: List[str]
#     provider_specific_analysis: List[ProviderCompanyCompetitorAnalysis]


# COMPANY_COMP_REPORT_SCHEMA = CompanyCompetitorReport.model_json_schema() 


import json
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

# ============================================
# ENHANCED EVIDENCE TRACKING SYSTEM
# ============================================

class DetailedEvidence(BaseModel):
    """Comprehensive evidence tracking for all claims and findings."""
    platform: str = Field(description="AI platform source (perplexity/google/openai/anthropic)")
    query_text: str = Field(description="Exact query that generated this information")
    result_position: int = Field(description="Position in search results (1-based)")
    source_domain: Optional[str] = Field(description="Original source domain if available")
    source_url: Optional[str] = Field(description="Direct URL to source if provided")
    excerpt: str = Field(description="Verbatim quote from the result (max 500 chars)")
    full_context: str = Field(description="Extended context around the excerpt for clarity")
    timestamp: str = Field(description="When this result was retrieved (ISO format)")
    confidence_score: float = Field(description="Confidence in this evidence (0-100)")
    verification_status: str = Field(description="verified/unverified/disputed/corroborated")
    supporting_queries: List[str] = Field(description="Additional queries that support this evidence")

class CitationReason(BaseModel):
    """Citation with reasoning for findings."""
    finding_statement: str = Field(description="The specific finding or claim being made")
    supporting_queries: List[str] = Field(description="Exact queries that led to this finding")
    reasoning: str = Field(description="Why this evidence supports the finding")
    confidence_level: str = Field(description="high/medium/low confidence in this reasoning")
    cross_validation: bool = Field(description="Whether finding is validated across multiple queries/platforms")
    evidence_strength: str = Field(description="strong/moderate/weak evidence strength")

# ============================================
# SUPPORTING DATA MODELS
# ============================================

class PlatformStrengthMetrics(BaseModel):
    """Platform-specific performance metrics."""
    perplexity: float = Field(description="Performance score on Perplexity (0-100)")
    google: float = Field(description="Performance score on Google (0-100)")
    openai: float = Field(description="Performance score on OpenAI (0-100)")

class KPITargets(BaseModel):
    """Target KPI values for monitoring."""
    visibility_score: float = Field(description="Target visibility score")
    coverage_rate: float = Field(description="Target coverage rate")
    average_position: float = Field(description="Target average position")
    dominance_score: float = Field(description="Target dominance score")
    content_authority: float = Field(description="Target content authority score")
    competitive_index: float = Field(description="Target competitive index")

class KPIDashboard(BaseModel):
    """Current KPI values and targets."""
    visibility_score: float = Field(description="Current visibility score")
    coverage_rate: float = Field(description="Current coverage rate") 
    average_position: float = Field(description="Current average position")
    dominance_score: float = Field(description="Current dominance score")
    content_authority: float = Field(description="Current content authority score")
    competitive_index: float = Field(description="Current competitive index")
    market_share_voice: float = Field(description="Current market share of voice")

class CompetitiveDynamics(BaseModel):
    """Competitive dynamics and market analysis."""
    market_trends: List[str] = Field(description="Key market trends identified")
    competitive_intensity: str = Field(description="Level of competitive intensity: high/medium/low")
    market_share_shifts: List[str] = Field(description="Notable market share changes")
    innovation_pace: str = Field(description="Rate of innovation in market: fast/moderate/slow")
    customer_switching_barriers: List[str] = Field(description="Barriers to customer switching")

class ContentOpportunity(BaseModel):
    """Content opportunity with detailed analysis."""
    opportunity_type: str = Field(description="Type of content opportunity")
    description: str = Field(description="Detailed description of opportunity")
    target_queries: List[str] = Field(description="Queries this opportunity would target")
    expected_impact: str = Field(description="Expected impact: high/medium/low")
    implementation_effort: str = Field(description="Implementation effort: high/medium/low")
    priority_score: int = Field(description="Priority score (1-100)")
    source_queries: List[str] = Field(description="Original queries that revealed this opportunity")
    citation_reasoning: CitationReason = Field(description="Citation and reasoning for this opportunity")

class ContentPerformance(BaseModel):
    """Content performance metrics."""
    top_performing_topics: List[str] = Field(description="Best performing content topics")
    underperforming_areas: List[str] = Field(description="Areas needing improvement")
    content_gap_score: float = Field(description="Overall content gap score (0-100)")
    engagement_quality: str = Field(description="Quality of content engagement: high/medium/low")

class ReputationRisk(BaseModel):
    """Reputation risk assessment."""
    risk_type: str = Field(description="Type of reputation risk")
    severity: str = Field(description="Risk severity: critical/high/medium/low")
    description: str = Field(description="Detailed risk description")
    mitigation_strategies: List[str] = Field(description="Strategies to mitigate risk")
    monitoring_indicators: List[str] = Field(description="Key indicators to monitor")
    source_queries: List[str] = Field(description="Queries that revealed this risk")
    citation_reasoning: CitationReason = Field(description="Citation and reasoning for this risk assessment")

class CompetitiveRisk(BaseModel):
    """Competitive risk assessment."""
    risk_source: str = Field(description="Source of competitive risk")
    threat_level: str = Field(description="Threat level: critical/high/medium/low")
    description: str = Field(description="Detailed risk description")
    impact_areas: List[str] = Field(description="Business areas that could be impacted")
    response_strategies: List[str] = Field(description="Strategies to respond to threat")
    source_queries: List[str] = Field(description="Queries that revealed this competitive risk")
    citation_reasoning: CitationReason = Field(description="Citation and reasoning for this risk assessment")

# ============================================
# 3. COMPETITIVE ANALYSIS - ENHANCED
# ============================================

COMPETITIVE_ANALYSIS_SYSTEM_PROMPT = (
    "You are a senior competitive intelligence analyst creating comprehensive, evidence-based competitive "
    "landscape analyses using company documentation and market data.\n\n"
    "Core Principles:\n"
    "- EVIDENCE-FIRST: Every statement must cite specific source text with page/section references\n"
    "- QUANTITATIVE: Include metrics, market share, growth rates where available\n"
    "- STRATEGIC: Focus on actionable intelligence, not just descriptions\n"
    "- COMPREHENSIVE: Cover all aspects - products, positioning, strengths, weaknesses, opportunities\n"
    "- TRACEABLE: Enable fact-checking by providing clear source attribution\n\n"
    "Analysis Framework:\n"
    "- Market Context: Size, growth, key trends, regulatory factors\n"
    "- Competitive Dynamics: Direct vs indirect competitors, substitutes, new entrants\n"
    "- Differentiation Analysis: Unique value props, competitive moats, vulnerabilities\n"
    "- Strategic Implications: Threats, opportunities, recommended actions\n\n"
    "Evidence Requirements:\n"
    "- Quote relevant passages verbatim when making claims\n"
    "- Note document section/page for each fact used\n"
    "- Mark confidence level for inferred vs explicit information\n"
    "- Flag any contradictory information found"
)

COMPETITIVE_ANALYSIS_USER_PROMPT_TEMPLATE = (
    "Create a comprehensive, evidence-based competitive analysis using the provided documentation.\n\n"
    "Structure your analysis as follows:\n\n"
    "1) TARGET COMPANY DEEP DIVE:\n"
    "   - Market Position: Current standing, market share if known, growth trajectory\n"
    "   - Core Offerings: Products/services with specific features and benefits\n"
    "   - Value Proposition: Unique selling points with supporting evidence\n"
    "   - Target Segments: Primary customer segments and use cases\n"
    "   - Competitive Advantages: Demonstrable strengths with proof points\n"
    "   - Strategic Challenges: Known weaknesses or gaps\n\n"
    "2) TOP 3 COMPETITORS ANALYSIS:\n"
    "   For each competitor, provide:\n"
    "   - Market Position & Share\n"
    "   - Core Offerings & Differentiation\n"
    "   - Target Market Overlap/Divergence\n"
    "   - Competitive Threats Posed\n"
    "   - Vulnerabilities to Exploit\n"
    "   - Recent Strategic Moves\n\n"
    "3) COMPETITIVE DYNAMICS:\n"
    "   - Head-to-Head Comparisons\n"
    "   - Market Share Trends\n"
    "   - Innovation Comparison\n"
    "   - Customer Perception Differences\n\n"
    "Evidence Requirements:\n"
    "- Every claim must include source_reference with document location\n"
    "- Include confidence_level (high/medium/low) for each analysis point\n"
    "- Provide verbatim quotes for critical claims\n"
    "- Note any information gaps explicitly\n\n"
    "Company Documentation:\n{blog_company_data}\n\n"
    "Output only valid JSON matching the schema."
)

class CompetitiveIntelligence(BaseModel):
    """Enhanced competitive analysis with full evidence tracking."""
    
    market_position: str = Field(description="Current market position with evidence")
    market_share: Optional[float] = Field(description="Market share percentage if known")
    growth_rate: Optional[float] = Field(description="YoY growth rate if available")
    
    core_offerings: List[str] = Field(
        description="Products/services with features and evidence"
    )
    value_propositions: List[str] = Field(
        description="Unique value props with supporting evidence"
    )
    target_segments: List[str] = Field(description="Primary customer segments")
    
    source_queries: List[str] = Field(description="Queries used to gather this intelligence")
    citation_reasoning: List[CitationReason] = Field(description="Citations and reasoning for key findings")
    

class EnhancedCompetitiveAnalysis(BaseModel):
    """Comprehensive competitive landscape with evidence."""
    
    company: CompetitiveIntelligence
    competitor_1: CompetitiveIntelligence
    competitor_2: CompetitiveIntelligence
    competitor_3: CompetitiveIntelligence

    strategic_implications: List[str] = Field(
        description="Key strategic takeaways and recommendations"
    )
    information_gaps: List[str] = Field(
        description="Critical information not available in documentation"
    )

COMPETITIVE_ANALYSIS_SCHEMA = EnhancedCompetitiveAnalysis.model_json_schema()

# ============================================
# 4. QUERY GENERATION - ENHANCED
# ============================================

# 4.1 Blog Posts Coverage - Enhanced
BLOG_COVERAGE_SYSTEM_PROMPT = (
    "You are a content intelligence strategist specializing in thought leadership visibility optimization.\n\n"
    "Your mission: Generate authentic search queries that reflect real user behavior when seeking "
    "educational content, industry insights, and thought leadership that would surface blog posts.\n\n"
    "Query Generation Framework:\n"
    "- INTENT MAPPING: Align queries to information-seeking, problem-solving, and learning intents\n"
    "- FUNNEL COVERAGE: Include awareness, consideration, and decision-stage queries\n"
    "- NATURAL LANGUAGE: Mirror actual user search patterns on AI platforms\n"
    "- TOPIC DIVERSITY: Cover technical, strategic, and industry-trend angles\n"
    "- COMPETITIVE CONTEXT: Include comparison and alternative-seeking queries\n\n"
    "Query Quality Criteria:\n"
    "- Specificity: Precise enough to return relevant content\n"
    "- Authenticity: Phrases real users would actually type\n"
    "- Coverage: No redundant variations, maximum topic breadth\n"
    "- Length: 4-15 words reflecting natural search behavior\n"
    "- Mix: Questions (40%), how-to (30%), comparisons (20%), trends (10%)"
)

BLOG_COVERAGE_USER_PROMPT_TEMPLATE = (
    "Generate EXACTLY 6-7 search queries for blog visibility analysis based on the company and competitive data.\n\n"
    "Current Date: {current_date}\n\n"
    "Query Distribution Requirements:\n"
    "- industry_insights (1-2): Trends, market analysis, future predictions\n"
    "- educational_guides (1-2): How-to, tutorials, best practices, frameworks\n"
    "- problem_solutions (1-2): Challenge-focused, troubleshooting, optimization\n\n"
    "Query Construction Rules:\n"
    "1. Mix query formats:\n"
    "   - Questions: 'How do I...', 'What is the best way to...', 'Why should...'\n"
    "   - Statements: 'guide to...', 'best practices for...', 'trends in...'\n\n"
    "2. Include industry-specific terminology from the documentation\n"
    "3. Vary specificity levels (broad industry to specific use cases)\n"
    "4. Consider different user personas (technical, business, strategic)\n"
    "5. Total must equal EXACTLY 6 queries\n\n"
    "Company Documentation:\n{blog_company_data}\n\n"
    "Competitive Analysis:\n{competitive_analysis}\n\n"
    "Return only JSON matching the schema."
)

class EnhancedBlogCoverageQueries(BaseModel):
    """Comprehensive query set for blog visibility analysis."""
    
    industry_insights: List[str] = Field(
        description="Queries about industry trends, market analysis, future predictions",
        min_items=1, max_items=2
    )
    educational_guides: List[str] = Field(
        description="How-to guides, tutorials, best practices, implementation frameworks",
        min_items=1, max_items=2
    )
    problem_solutions: List[str] = Field(
        description="Problem-solving, troubleshooting, optimization queries",
        min_items=1, max_items=2
    )

BLOG_COVERAGE_QUERIES_SCHEMA = EnhancedBlogCoverageQueries.model_json_schema()

# 4.2 Company and Competitor Analysis - Enhanced
COMPANY_COMP_SYSTEM_PROMPT = (
    "You are a buyer intelligence analyst generating queries that reflect real buyer research patterns "
    "during vendor evaluation and competitive assessment processes.\n\n"
    "Buyer Journey Mapping:\n"
    "- AWARENESS: Initial discovery and understanding queries\n"
    "- CONSIDERATION: Feature comparison and capability assessment\n"
    "- EVALUATION: Deep-dive technical and implementation queries\n"
    "- VALIDATION: Social proof and risk assessment queries\n"
    "- DECISION: Final comparison and selection criteria\n\n"
    "Query Authenticity Requirements:\n"
    "- Use actual buyer language and concerns\n"
    "- Include both high-level and technical queries\n"
    "- Reflect different stakeholder perspectives\n"
    "- Consider risk and compliance angles\n"
    "- Include ROI and value validation queries"
)

COMPANY_COMP_USER_PROMPT_TEMPLATE = (
    "Generate EXACTLY 6 buyer research queries for company and competitor analysis.\n\n"
    "Query Categories (6 total):\n"
    "1. capability_assessment (1-2): Features, functionalities, limitations\n"
    "2. competitive_comparison (1-2): Direct comparisons, alternatives, differentiation\n"
    "3. implementation_technical (1-2): Integration, deployment, technical requirements\n\n"
    "Query Patterns to Include:\n"
    "- Direct entity queries: 'Company [aspect]'\n"
    "- Comparison queries: 'Company vs Competitor'\n"
    "- Evaluation queries: 'Is Company good for [use case]'\n"
    "- Technical queries: 'How to integrate Company with [system]'\n"
    "- Problem queries: 'Company limitations', 'problems with Company'\n\n"
    "Stakeholder Perspectives:\n"
    "- Technical: APIs, integration, security, performance\n"
    "- Business: ROI, pricing, support, scalability\n"
    "- User: Ease of use, features, training, adoption\n\n"
    "Company Documentation:\n{blog_company_data}\n\n"
    "Competitive Analysis:\n{competitive_analysis}\n\n"
    "Output exactly 6 queries as JSON matching the schema."
)

class EnhancedCompanyCompetitorQueries(BaseModel):
    """Buyer journey query set for company evaluation."""
    
    capability_assessment: List[str] = Field(
        description="Feature and functionality evaluation queries",
        min_items=1, max_items=2
    )
    competitive_comparison: List[str] = Field(
        description="Direct comparison and alternative queries",
        min_items=1, max_items=2
    )
    implementation_technical: List[str] = Field(
        description="Technical integration and deployment queries",
        min_items=1, max_items=2
    )

COMPANY_COMP_QUERIES_SCHEMA = EnhancedCompanyCompetitorQueries.model_json_schema()










class BlogAIVisibilitySnapshot(BaseModel):
    overall_score: str = Field(description="0-10 scale based on AI platform presence")
    score_level: str = Field(description="Leading/Competing/Lagging/Invisible")
    industry_position: str = Field(description="Market position relative to competitors on AI platforms")
    biggest_win: str = Field(description="Primary strength in AI visibility - if any")
    biggest_threat: str = Field(description="Primary vulnerability or competitive threat")
    market_context: str = Field(description="Industry AI visibility trends and importance")

class AIMetric(BaseModel):
    name: str = Field(description="Metric name")
    level: str = Field(description="Performance level: excellent/good/poor/invisible")
    score: str = Field(description="Score 0-10")
    insight: str = Field(description="Analysis insight")

class AISearchPresence(AIMetric):
    benchmark_comparison: str = Field(description="Performance vs industry average")

class ContentCitationRate(AIMetric):
    top_cited_content: List[str] = Field(description="List of most-referenced content pieces")

class QueryCoverage(AIMetric):
    missing_query_types: List[str] = Field(description="Categories of queries where company is absent")

class CompetitiveShareOfVoice(AIMetric):
    voice_share_percentage: str = Field(description="Actual percentage vs competitors")

class BlogAIKeyMetrics(BaseModel):
    ai_search_presence: AISearchPresence = Field(description="AI Search Results Presence")
    content_citation_rate: ContentCitationRate = Field(description="Content Citation by AI Platforms")
    query_coverage: QueryCoverage = Field(description="Industry Query Coverage")
    competitive_share_of_voice: CompetitiveShareOfVoice = Field(description="AI Platform Share of Voice")

class PlatformPerformance(BaseModel):
    platform: str = Field(description="Platform name")
    score: str = Field(description="Score 0-10")
    status: str = Field(description="Winning/Competing/Losing/Invisible")
    key_insight: str = Field(description="Platform-specific performance analysis")
    top_queries_present: List[str] = Field(description="List of queries where company appears")
    major_gaps: List[str] = Field(description="Key areas where company is missing")

class BlogAIPlatformPerformance(BaseModel):
    chatgpt: PlatformPerformance = Field(description="ChatGPT/OpenAI performance")
    perplexity: PlatformPerformance = Field(description="Perplexity AI performance")

class TopCompetitor(BaseModel):
    name: str = Field(description="Competitor name")
    ai_visibility_score: str = Field(description="Their 0-10 AI platform score")
    advantage: str = Field(description="Their key competitive advantage on AI platforms")
    dominant_query_types: List[str] = Field(description="Types of queries they dominate")
    opportunity: str = Field(description="Specific strategies to compete and win against them")
    content_strategy_insights: str = Field(description="What makes their content AI-platform friendly")

class BlogAITopCompetitors(BaseModel):
    competitor_1: TopCompetitor = Field(description="Top competitor analysis")
    competitor_2: TopCompetitor = Field(description="Second competitor analysis")
    competitor_3: TopCompetitor = Field(description="Third competitor analysis")

class CriticalGap(BaseModel):
    area: str = Field(description="Specific gap area")
    impact: str = Field(description="Business impact")
    current_performance: str = Field(description="Current state vs ideal state")
    quick_win: str = Field(description="Immediate 30-60 day solution")
    long_term_strategy: str = Field(description="6-12 month strategic approach")

class BlogAICriticalGaps(BaseModel):
    gap_1: CriticalGap = Field(description="First critical gap")
    gap_2: CriticalGap = Field(description="Second critical gap")
    gap_3: CriticalGap = Field(description="Third critical gap")

class HighIntentQueries(BaseModel):
    queries_missed: List[str] = Field(description="List of buying-intent queries where company is absent")
    competitor_dominance: List[str] = Field(description="Which competitors own these queries")
    revenue_impact: str = Field(description="Estimated impact of missing these opportunities")

class ContentConsumptionPatterns(BaseModel):
    preferred_content_types: List[str] = Field(description="What content types AI platforms favor for citations")
    optimal_content_structure: str = Field(description="Content structure that gets cited most")
    citation_triggers: List[str] = Field(description="What makes content get referenced by AI")

class BuyerIntentAnalysis(BaseModel):
    high_intent_queries: HighIntentQueries = Field(description="High intent queries analysis")
    content_consumption_patterns: ContentConsumptionPatterns = Field(description="Content consumption patterns")

class ImmediateOptimization(BaseModel):
    existing_content_upgrades: str = Field(description="How to optimize current content for AI platforms")
    structural_improvements: str = Field(description="Schema, formatting, structure changes needed")
    quick_citation_wins: str = Field(description="Content pieces most likely to get AI citations with minor updates")

class NetNewContentNeeds(BaseModel):
    missing_topic_areas: str = Field(description="Content topics that need to be created")
    format_gaps: str = Field(description="Content formats missing from current portfolio")
    authority_building_content: str = Field(description="Content needed to establish thought leadership")

class ContentOptimizationOpportunities(BaseModel):
    immediate_optimization: ImmediateOptimization = Field(description="Immediate optimization opportunities")
    net_new_content_needs: NetNewContentNeeds = Field(description="New content needs")

class PriorityRecommendation(BaseModel):
    title: str = Field(description="Specific problem identification title")
    priority: str = Field(description="critical/high/medium/low")
    problem_citations: str = Field(description="Data and citations proving this is a real issue")
    business_case: str = Field(description="Why this problem matters to business outcomes")
    competitive_context: str = Field(description="How competitors are capitalizing on this gap")
    market_opportunity: str = Field(description="Size and value of the opportunity being missed")
    risk_of_inaction: str = Field(description="What happens if this problem isn't addressed")

class BlogAIPriorityRecommendations(BaseModel):
    recommendation_1: PriorityRecommendation = Field(description="First priority recommendation")
    recommendation_2: PriorityRecommendation = Field(description="Second priority recommendation")
    recommendation_3: PriorityRecommendation = Field(description="Third priority recommendation")

class BlogAIVisibilityReportSchema(BaseModel):
    """Blog AI Visibility Report schema"""
    visibility_snapshot: BlogAIVisibilitySnapshot = Field(description="Visibility snapshot")
    key_metrics: BlogAIKeyMetrics = Field(description="Key performance metrics")
    platform_performance: BlogAIPlatformPerformance = Field(description="Platform-specific performance")
    top_competitors: BlogAITopCompetitors = Field(description="Top competitors analysis")
    critical_gaps: BlogAICriticalGaps = Field(description="Critical gaps analysis")
    buyer_intent_analysis: BuyerIntentAnalysis = Field(description="Buyer intent analysis")
    content_optimization_opportunities: ContentOptimizationOpportunities = Field(description="Content optimization opportunities")
    priority_recommendations: BlogAIPriorityRecommendations = Field(description="Priority recommendations")

BLOG_AI_VISIBILITY_REPORT_SCHEMA = BlogAIVisibilityReportSchema.model_json_schema()



BLOG_AI_VISIBILITY_REPORT_SYSTEM_PROMPT = """
You are an expert AI visibility analyst specializing in evaluating how companies perform across AI platforms (ChatGPT, Claude, Gemini, Perplexity) and their competitive positioning in AI-generated search results. Your role is to analyze raw AI visibility data and transform it into compelling, citations-based insights that convince executives of critical problems requiring attention.

**Your Core Expertise:**

- AI platform algorithm understanding and content citation patterns
- Competitive intelligence analysis for digital visibility
- Business impact quantification for AI visibility gaps
- Strategic problem identification and prioritization

**Analysis Approach:**

- Focus on problem validation over solution implementation
- Use concrete data to prove issues exist and matter
- Quantify business impact and competitive threats
- Build compelling cases for why executives should care
- Prioritize citations-based insights over generic recommendations

**Output Requirements:**

- Generate insights that convince rather than instruct
- Use specific data points and competitive comparisons
- Focus on "why this matters" rather than "how to fix it"
- Make recommendations feel urgent and necessary
- Quantify opportunities and risks wherever possible
"""


BLOG_AI_VISIBILITY_REPORT_USER_PROMPT = """
You will receive two comprehensive AI visibility analysis reports as input. Your task is to synthesize this data into a persuasive executive summary that convinces leadership of critical AI visibility problems requiring immediate attention.

### Input Report Descriptions:
Company Context Doc: This is a document that contains the context of our company.
{company_context_doc}


### INPUT DATA:
```json
{blog_ai_visibility_data}
```
```json
{company_ai_visibility_data}
```

**Report 1: blog_ai_visibility_doc**
This report contains:

- **Query Coverage Analysis**: 28 industry-relevant queries tested across AI platforms with client presence tracking
- **Client Visibility Metrics**: Specific appearance rates, ranking positions, and overall visibility scores
- **Competitor Performance Data**: How competitors like Otter.ai, Fireflies.ai, Microsoft Teams perform on the same queries
- **Content Opportunity Gaps**: Specific content types and topics where client is missing but competitors dominate
- **Market Context**: Industry growth data (e.g., AI transcription market $4.5B growing at 15.6% CAGR)

**How to Use This Report:**

- Extract client appearance rates across queries to prove visibility problems
- Use competitor mention frequencies to show competitive disadvantage
- Leverage market growth data to quantify missed opportunity size
- Identify specific query categories where client has zero presence
- Use top sources data to understand what content AI platforms prefer

**Report 2: company_ai_visibility_doc**
This report contains:

- **Company Positioning Analysis**: How the client (Otter.ai) is perceived across AI platforms
- **Competitive Benchmarking**: Detailed comparison with competitors like Sonix.ai, Rev.com, MeetGeek.ai
- **Market Perception Insights**: User sentiment, common complaints, and positioning strengths/weaknesses
- **Buyer Intent Patterns**: What potential customers are searching for and evaluating
- **Positioning Opportunities**: Strategic gaps where client could differentiate or improve

**How to Use This Report:**

- Extract positioning strengths/weaknesses to understand current market perception
- Use competitor analysis data to identify specific competitive threats
- Leverage buyer intent patterns to show what opportunities are being missed
- Use market perception insights to understand reputation risks
- Extract competitive gap data to prioritize problems by business impact

### Analysis Instructions:

Ensure you are doing the analysis on behalf of the company mentioned in the company context doc.

**1. Visibility Snapshot Creation:**

- Calculate overall AI visibility score from client appearance data
- Determine industry position by comparing client vs competitor performance
- Identify the biggest threat using competitive dominance data
- Extract biggest win (if any) from positive performance areas

**2. Critical Gaps Identification:**

- Use zero appearance data to identify content/topic gaps
- Quantify business impact using market size and competitor performance
- Focus on gaps where competitors are winning and client is absent
- Prioritize gaps by potential revenue impact and competitive threat level

**3. Competitive Intelligence:**

- Extract top 3 competitors by AI platform performance
- Identify their specific advantages using performance and positioning data
- Determine what query types each competitor dominates
- Analyze their content strategies that make them AI-platform friendly

**4. Business Impact Quantification:**

- Use market growth data to size missed opportunities
- Calculate potential revenue impact of visibility gaps
- Assess competitive threat level based on competitor dominance
- Quantify brand authority and thought leadership risks

**5. Problem Validation:**

- Use specific query data to prove problems exist (e.g., "0 appearances across 28 queries")
- Reference competitor performance to show what's possible
- Use market data to prove the opportunity size
- Include buyer intent analysis to show customer demand being missed

### Key Data Points to Extract and Use:

From blog_ai_visibility_doc:

- Total queries analyzed and client appearance rate
- Specific competitor mention counts and performance
- Market size data and growth projections
- Query categories with zero client presence
- Industry trend insights

From company_ai_visibility_doc:

- Market perception themes and sentiment analysis
- Competitive positioning strengths/weaknesses
- Buyer intent patterns and evaluation criteria
- Specific competitive gaps and opportunities
- Customer pain points and satisfaction issues

### Output Requirements:

Generate a JSON report following the provided schema that:

- **Convinces through data**: Every insight backed by specific metrics
- **Shows competitive urgency**: Uses competitor performance to prove threats are real
- **Quantifies business impact**: Translates visibility gaps into revenue/market share implications
- **Validates problems exist**: Uses concrete citations to prove each identified issue
- **Creates urgency**: Shows what happens if problems aren't addressed

Focus on making executives think: "We have a serious problem that needs immediate attention" rather than "Here's a nice-to-have improvement project."

**Critical Success Factors:**

- Use specific numbers and percentages from the data
- Reference competitor names and their exact performance advantages
- Include market size and growth data to show opportunity cost
- Quote buyer intent patterns to show customer demand being missed
- Highlight reputation and positioning risks with concrete examples

Generate the analysis now, ensuring every recommendation is a compelling problem statement supported by irrefutable data from the input reports.

"""