# ============================================
# QUERY GENERATION SYSTEM - Enhanced & Generic
# ============================================

EXEC_VISIBILITY_SYSTEM_PROMPT = (
    "You are a senior research intelligence analyst specializing in digital presence and reputation analysis. "
    "Your task is to generate exactly 5 authentic search queries that various stakeholders (buyers, partners, investors, "
    "employees, media, analysts) would actually use when researching executives on AI-powered platforms. "
    "Output must be valid JSON conforming exactly to the provided schema. "
    "Core principles: "
    "(1) AUTHENTIC - Queries should mirror real search behavior patterns observed in professional research; "
    "(2) FOCUSED - Cover the most critical professional aspects without redundancy; "
    "(3) INTENT-DRIVEN - Each query should have a clear information-seeking purpose; "
    "(4) CONTEXTUAL - Leverage provided profile data to create personalized, relevant queries; "
    "(5) PROFESSIONAL - Focus exclusively on business-relevant aspects; "
    "(6) NATURAL - Use conversational language as people actually type in AI assistants; "
    "(7) VARIED - Mix direct name searches, role-based queries, and topical investigations."
)

EXEC_VISIBILITY_USER_PROMPT_TEMPLATE = (
    "Based on the executive profile data below, generate EXACTLY 5 search queries that stakeholders would use "
    "to research this person on AI platforms (ChatGPT, Perplexity, Gemini, Claude). "
    "Current Date: {current_date}\n\n"
    "Distribute queries across these categories:\n\n"
    "- expertise_credibility (1-2): Domain expertise, technical knowledge, industry credibility\n"
    "- leadership_impact (1): Leadership philosophy, team building, organizational impact\n"
    "- market_position (1-2): Competitive positioning, market insights, industry standing\n"
    "- network_influence (1): Industry connections, speaking engagements, media presence\n\n"
    "Query requirements:\n"
    "- Natural language, 4-15 words each\n"
    "- Mix of: direct name searches (30%), role/company queries (30%), topical expertise (40%)\n"
    "- Include conversational phrases like 'what does X think about', 'how did X achieve', 'X's approach to'\n"
    "- Vary query styles: questions, comparisons, opinion-seeking, fact-finding\n"
    "- No duplicates or trivial variations\n\n"
    "Return ONLY valid JSON matching the schema.\n\n"
    "Profile Data:\n{linkedin_user_profile}\n\n"
    "Additional Context:\n{linkedin_scraped_profile}"
)

from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class ExecutiveVisibilityQueries(BaseModel):
    """Comprehensive query set for executive AI visibility analysis."""
    
    expertise_credibility: List[str] = Field(
        description="Queries about domain expertise, technical knowledge, and professional credibility",
        min_items=1, max_items=2
    )
    leadership_impact: List[str] = Field(
        description="Queries about leadership style, team impact, and organizational transformation",
        min_items=1, max_items=1
    )
    market_position: List[str] = Field(
        description="Queries about competitive positioning, market insights, and industry standing",
        min_items=1, max_items=2
    )
    network_influence: List[str] = Field(
        description="Queries about industry connections, thought leadership, and sphere of influence",
        min_items=1, max_items=1
    )

EXEC_VISIBILITY_QUERIES_SCHEMA = ExecutiveVisibilityQueries.model_json_schema()

# ============================================
# REPORT GENERATION SYSTEM - Enhanced
# ============================================

EXEC_VISIBILITY_REPORT_SYSTEM_PROMPT = (
    "You are a strategic intelligence analyst specializing in executive digital presence and AI-powered reputation analysis. "
    "Your task is to synthesize search results from multiple AI platforms into actionable intelligence reports. "
    "Core analytical framework: "
    "(1) EVIDENCE-BASED - Every claim must be traceable to specific search results with source attribution; "
    "(2) COMPARATIVE - Analyze relative performance across AI platforms to identify platform-specific strengths/gaps; "
    "(3) CONTEXTUAL - Position findings within industry benchmarks and competitive landscape; "
    "(4) ACTIONABLE - Provide specific, prioritized recommendations with implementation rationale; "
    "(5) QUANTITATIVE - Use metrics consistently: coverage_pct, depth_score, sentiment_index, freshness_score; "
    "(6) STRATEGIC - Connect visibility gaps to business impact and opportunity cost. "
    "CRITICAL: ALL supporting_evidence fields must contain complete SourceEvidence objects with: "
    "platform (exact AI platform name), query_used (the specific search query), relevant_excerpt (direct quote from results), "
    "source_url (if available), and confidence_level (high/medium/low). Never leave supporting_evidence fields empty. "
    "Output must be valid JSON conforming to the schema."
)

EXEC_VISIBILITY_REPORT_USER_PROMPT_TEMPLATE = (
    "Analyze the AI platform search results to generate a comprehensive Executive AI Visibility Intelligence Report.\n\n"
    "Search Results Data:\n{loaded_query_results}\n\n"
    "Analysis Requirements:\n"
    "1. PLATFORM ANALYSIS:\n"
    "   - Group results by provider (perplexity, google, openai, anthropic)\n"
    "   - Calculate metrics per platform:\n"
    "     • coverage_score: (queries with substantive answers / total queries) * 100\n"
    "     • depth_score: Average answer comprehensiveness (1-100 scale)\n"
    "     • accuracy_score: Factual correctness based on known information (1-100)\n"
    "     • sentiment_index: Tone of coverage (-100 negative to +100 positive)\n"
    "     • source_quality: Quality and authority of cited sources (1-100)\n"
    "   - Extract verbatim quotes and source URLs as evidence\n\n"
    "2. COMPETITIVE INTELLIGENCE:\n"
    "   - Identify all mentioned competitors/peers\n"
    "   - Analyze comparative positioning language\n"
    "   - Note share-of-voice in industry discussions\n\n"
    "3. INSIGHT SYNTHESIS:\n"
    "   - Cross-platform consistency analysis\n"
    "   - Information freshness assessment\n"
    "   - Narrative coherence evaluation\n"
    "   - Gap identification with business impact\n\n"
    "4. STRATEGIC RECOMMENDATIONS:\n"
    "   - Prioritize by potential impact (use impact_score 1-100)\n"
    "   - Include implementation complexity (low/medium/high)\n"
    "   - Provide specific content/action examples\n"
    "   - MANDATORY: Each recommendation must include complete supporting_evidence with:\n"
    "     • platform: exact platform name (perplexity/google/openai/anthropic)\n"
    "     • query_used: the specific search query that revealed this insight\n"
    "     • relevant_excerpt: direct quote from the search result (minimum 20 words)\n"
    "     • source_url: URL if provided in the search result\n"
    "     • confidence_level: assessment of information reliability (high/medium/low)\n\n"
    "5. EVIDENCE REQUIREMENTS FOR ALL FIELDS:\n"
    "   - competitive_landscape.evidence: Must contain specific quotes about competitors\n"
    "   - representative_evidence: Must include actual search result excerpts\n"
    "   - supporting_evidence: Required for every strategic recommendation\n"
    "   - All evidence objects must be complete - no empty or partial SourceEvidence entries\n\n"
    "Return ONLY valid JSON matching the schema. Every evidence field must contain complete, detailed SourceEvidence objects."
)

# Enhanced Schema Classes

class SourceEvidence(BaseModel):
    """Evidence attribution for claims and findings."""
    platform: str = Field(description="AI platform source (perplexity/google/openai/anthropic)")
    query_used: str = Field(description="The specific query that generated this information")
    relevant_excerpt: str = Field(description="Verbatim quote or summary from the result")
    source_url: Optional[str] = Field(description="URL if provided in the search result", default=None)
    confidence_level: str = Field(description="Confidence in this information: high/medium/low")

class PlatformMetrics(BaseModel):
    """Detailed metrics for each AI platform's performance."""
    coverage_score: float = Field(description="% of queries with substantive answers (0-100)")
    depth_score: float = Field(description="Average answer comprehensiveness (0-100)")
    accuracy_score: float = Field(description="Factual accuracy based on known info (0-100)")
    sentiment_index: float = Field(description="Tone of coverage (-100 to +100)")
    source_quality: float = Field(description="Quality/authority of cited sources (0-100)")
    response_consistency: float = Field(description="Consistency across similar queries (0-100)")
    information_recency: str = Field(description="How current the information is: current/recent/dated/unknown")

class PlatformAnalysis(BaseModel):
    """Comprehensive analysis for each AI platform."""
    platform: str = Field(description="Platform identifier")
    metrics: PlatformMetrics
    visibility_assessment: str = Field(description="Overall visibility assessment for this platform")
    key_narratives: List[str] = Field(description="Main themes/stories about the executive")
    unique_insights: List[str] = Field(description="Insights unique to this platform")
    coverage_gaps: List[str] = Field(description="What this platform doesn't know/cover")
    representative_evidence: List[SourceEvidence] = Field(description="Key evidence examples")
    improvement_actions: List[str] = Field(description="Platform-specific optimization actions")

class CompetitorInfo(BaseModel):
    """Information about a competitor mentioned in the analysis."""
    name: str = Field(description="Competitor name or company")
    context: str = Field(description="Context in which this competitor was mentioned")

class CompetitiveLandscape(BaseModel):
    """Competitive positioning intelligence."""
    direct_competitors: List[CompetitorInfo] = Field(
        description="List of competitors with their mention context"
    )
    positioning_statement: str = Field(description="How the executive is positioned vs. peers")
    differentiation_factors: List[str] = Field(description="Unique differentiators identified")
    competitive_gaps: List[str] = Field(description="Areas where competitors have stronger presence")
    market_share_voice: float = Field(description="Estimated share of voice in category (0-100)")
    evidence: List[SourceEvidence] = Field(description="Supporting evidence for competitive analysis")

class StrategicRecommendation(BaseModel):
    """Actionable recommendation with full context."""
    action: str = Field(description="Specific action to take")
    rationale: str = Field(description="Why this action will improve AI visibility")
    impact_score: int = Field(description="Expected impact on visibility (1-100)")
    effort_level: str = Field(description="Implementation complexity: low/medium/high")
    timeline: str = Field(description="Suggested timeline: immediate/short-term/long-term")
    success_metrics: List[str] = Field(description="How to measure success")
    supporting_evidence: List[SourceEvidence] = Field(description="Evidence supporting this recommendation")

class InformationQuality(BaseModel):
    """Assessment of information quality across platforms."""
    accuracy_assessment: str = Field(description="Overall accuracy of information found")
    consistency_score: float = Field(description="Cross-platform consistency (0-100)")
    information_gaps: List[str] = Field(description="Key information not found on any platform")
    misinformation_risks: List[str] = Field(description="Potential misinformation or outdated info")
    verification_status: List[str] = Field(description="Status of key claims as text descriptions")

class PlatformRanking(BaseModel):
    """Platform ranking with justification."""
    platform: str = Field(description="Platform name")
    rank: int = Field(description="Ranking position (1 = best)")
    justification: str = Field(description="Reason for this ranking")

class ExecutiveAIVisibilityReport(BaseModel):
    """Comprehensive AI Visibility Intelligence Report."""
    
    # Executive Summary
    executive_summary: str = Field(description="High-level visibility assessment across all AI platforms")
    overall_visibility_score: float = Field(description="Aggregate visibility score (0-100)")
    
    # Platform-Specific Analysis
    platform_analyses: List[PlatformAnalysis] = Field(description="Detailed analysis per platform")
    best_performing_platform: str = Field(description="Platform with strongest executive presence")
    platform_rankings: List[PlatformRanking] = Field(description="Platforms ranked with justification")
    
    # Competitive Intelligence
    competitive_landscape: CompetitiveLandscape = Field(description="Competitive positioning analysis")
    
    # Information Quality
    information_quality: InformationQuality = Field(description="Quality assessment of available information")
    
    # Strategic Recommendations
    strategic_recommendations: List[StrategicRecommendation] = Field(
        description="Prioritized recommendations with evidence"
    )
    
    # Quick Wins
    immediate_actions: List[str] = Field(description="Actions that can be implemented within 48 hours")
    
    # Risk Assessment
    reputation_risks: List[str] = Field(description="Identified risks to executive reputation")
    
    # Monitoring Cadence
    next_analysis_date: str = Field(description="Recommended date for next analysis")
    monitoring_triggers: List[str] = Field(description="Events that should trigger immediate re-analysis")

EXEC_VISIBILITY_REPORT_SCHEMA = ExecutiveAIVisibilityReport.model_json_schema()