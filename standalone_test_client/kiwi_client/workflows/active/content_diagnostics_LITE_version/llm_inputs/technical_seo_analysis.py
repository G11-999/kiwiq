from typing import List, Literal
from pydantic import BaseModel, Field, conint

# System and User prompt templates
TECHNICAL_SEO_SYSTEM_PROMPT_TEMPLATE = """You are a senior technical SEO analyst specializing in technical SEO audits based on measurable HTML and technical factors. Your role is to analyze concrete technical SEO metrics and create actionable reports for development teams and marketing executives.

Key responsibilities:
- Analyze technical SEO health based on measurable HTML standards and best practices
- Identify critical technical issues that impact crawlability, indexability, and user experience
- Analyze robots.txt configuration and bot access permissions
- Prioritize issues based on their direct impact on search engine visibility
- Provide specific, technically accurate recommendations with clear implementation paths
- Focus on fixing foundational technical issues before suggesting optimizations

Analysis guidelines:
- Technical requirements (HTTPS, mobile-friendly, canonical tags) are non-negotiable baselines
- Missing fundamental elements (title, H1, meta description) are critical issues
- Consider pages with <50% implementation of best practices as requiring attention
- Pages with <30% implementation need immediate action
- Prioritize issues that directly block search engines (noindex, missing titles, broken hierarchy)
- Factor in the scale of issues (e.g., 80% of pages missing meta descriptions is critical)
- Analyze robots.txt for proper bot access - blocking beneficial bots is a critical issue
- Identify opportunities to allow important SEO and AI bots that are currently blocked

Metrics interpretation:
- Title/Meta Description: Essential for SERP appearance and CTR
- H1 and Hierarchy: Critical for content understanding and accessibility
- HTTPS: Mandatory for security and ranking
- Mobile-friendly: Required for mobile-first indexing
- Canonical tags: Essential for duplicate content management
- Schema markup: Important for rich results and AI understanding
- Alt text: Critical for accessibility and image search
- Internal linking: Essential for crawlability and PageRank flow
- Robots.txt: Critical for controlling bot access and ensuring beneficial bots can crawl

Report tone: Technical, precise, actionable, and data-driven.
Report focus: Concrete technical issues with measurable impact on search performance, including bot access optimization.

You must structure your response as a valid JSON object matching the TechnicalSEOReport schema provided."""

TECHNICAL_SEO_USER_PROMPT_TEMPLATE = """Please analyze the following technical SEO audit data and generate a comprehensive technical SEO report. Focus on identifying critical technical issues and providing actionable fixes, including robots.txt optimization.

## Technical SEO Audit Data:

{data}

## Robots Analysis:

{robots_analysis}

## Analysis Instructions:

1. Calculate technical health scores based on the implementation rates of SEO best practices
2. Analyze the robots.txt configuration to identify blocked beneficial bots and accessibility issues
3. Identify 3-5 critical technical issues that directly impact search visibility (including bot access issues)
4. Provide 3-4 immediate technical fixes that can be implemented quickly
5. Identify structural gaps that require longer-term development effort
6. Create specific recommendations for robots.txt optimization to improve bot access
7. Create a prioritized timeline for fixing critical issues

Focus on technical issues that can be directly measured and fixed through code changes. Pay special attention to:
- Which beneficial bots (Google, Bing, AI crawlers) are being blocked unnecessarily
- Whether important SEO bots have proper access to key site areas
- Robots.txt rules that might be preventing optimal crawling and indexing

Base all recommendations on the concrete metrics and robots analysis provided.

Please return your analysis as a valid JSON object following the TechnicalSEOReport schema."""


# Pydantic schemas for the LLM structured output
class TechnicalHealth(BaseModel):
    """Technical SEO health scores based on measurable HTML metrics."""

    overall_score: conint(ge=0, le=100) = Field(
        ..., description="0-100 score based on aggregate technical SEO metrics (title, meta, headers, etc.)"
    )
    crawlability_score: conint(ge=0, le=100) = Field(
        ..., description="0-100 score based on technical factors affecting search engine crawling (HTTPS, HTML lang, canonical tags, robots.txt)"
    )
    structure_score: conint(ge=0, le=100) = Field(
        ..., description="0-100 score based on HTML structure metrics (heading hierarchy, lists, semantic HTML)"
    )
    mobile_readiness_score: conint(ge=0, le=100) = Field(
        ..., description="0-100 score based on mobile-friendly viewport and HTTPS usage"
    )
    status_summary: str = Field(
        ..., description="One-sentence summary of the technical SEO health based on measured metrics"
    )


class RobotsInsight(BaseModel):
    """Insights about robots.txt configuration and bot access."""
    
    bot_name: str = Field(..., description="Name of the bot or crawler (e.g., 'Googlebot', 'Bingbot', 'GPTBot')")
    current_access: Literal["Allowed", "Blocked", "Partially Blocked"] = Field(
        ..., description="Current access level based on robots.txt analysis"
    )
    recommended_access: Literal["Allow", "Block", "Selective Allow"] = Field(
        ..., description="Recommended access level for optimal SEO performance"
    )
    seo_impact: str = Field(..., description="How the current access setting impacts SEO and visibility")
    action_needed: str = Field(..., description="Specific action to take in robots.txt (e.g., 'Remove Disallow rule for /blog/')")


class TechnicalIssue(BaseModel):
    """A specific technical SEO issue identified from the metrics."""

    issue: str = Field(..., description="Specific technical problem (e.g., '45% of pages missing meta descriptions')")
    metric_value: str = Field(..., description="The actual metric value from the analysis (e.g., '45%', '2.3 avg H1s')")
    seo_impact: str = Field(..., description="How this technical issue affects search engine visibility and rankings")
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = Field(
        ..., description="Severity based on the metric value and SEO best practices"
    )


class TechnicalImprovement(BaseModel):
    """A specific technical fix based on the analyzed metrics."""

    action: str = Field(..., description="Specific technical action (e.g., 'Add missing title tags to 23% of pages')")
    current_metric: str = Field(..., description="Current metric value that needs improvement (e.g., '77% have titles')")
    target_metric: str = Field(..., description="Target metric value after implementation (e.g., '100% with titles')")
    expected_impact: Literal["High", "Medium", "Low"] = Field(
        ..., description="Expected SEO impact based on the importance of this technical factor"
    )


class TechnicalGap(BaseModel):
    """Technical implementation gap identified from the metrics."""

    gap_area: str = Field(..., description="Technical area with low metrics (e.g., 'Schema Markup', 'Open Graph')")
    current_implementation: str = Field(..., description="Current implementation percentage or metric (e.g., '15% have schema')")
    best_practice_target: str = Field(..., description="Industry best practice target (e.g., '100% schema implementation')")
    implementation_priority: Literal["High", "Medium", "Low"] = Field(
        ..., description="Priority based on SEO impact and current gap size"
    )


class KeyMetricHighlight(BaseModel):
    """Important metric to highlight from the analysis."""

    metric_name: str = Field(..., description="Name of the metric (e.g., 'Pages with H1', 'Mobile-friendly pages')")
    value: str = Field(..., description="Actual value from the analysis (e.g., '67%', '4.2 average')")
    benchmark: str = Field(..., description="SEO best practice benchmark (e.g., '100%', '1 H1 per page')")
    status: Literal["Good", "Needs Improvement", "Critical"] = Field(
        ..., description="Status based on comparison to benchmark"
    )


class TechnicalSEOReport(BaseModel):
    """
    Technical SEO report based on measurable HTML and technical metrics.
    All insights are derived from concrete, verifiable technical factors.
    """

    technical_health: TechnicalHealth = Field(
        ..., description="Overall technical health scores based on analyzed metrics"
    )

    robots_insights: List[RobotsInsight] = Field(
        ..., description="Analysis of robots.txt configuration and bot access recommendations", max_items=8
    )

    critical_technical_issues: List[TechnicalIssue] = Field(
        ..., description="Top technical issues ordered by severity, based on actual metrics", max_items=5
    )

    immediate_technical_fixes: List[TechnicalImprovement] = Field(
        ..., description="Quick technical improvements based on the metrics analyzed", max_items=4
    )

    technical_implementation_gaps: List[TechnicalGap] = Field(
        ..., description="Major technical gaps in SEO implementation", max_items=4
    )

    key_metrics: List[KeyMetricHighlight] = Field(
        ..., description="Important metrics to highlight for stakeholders", max_items=6
    )

    executive_summary: str = Field(
        ..., description="2-3 sentence executive summary of technical SEO status based on metrics, including robots.txt status"
    )

    pages_analyzed: int = Field(..., description="Total number of pages analyzed in this report")


# Export JSON schema for use in LLM node configuration
TECHNICAL_SEO_REPORT_SCHEMA = TechnicalSEOReport.model_json_schema() 