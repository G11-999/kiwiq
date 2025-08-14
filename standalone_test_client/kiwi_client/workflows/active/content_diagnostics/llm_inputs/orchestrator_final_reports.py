"""
LLM Input Templates for Orchestrator Final Report Generation

This module contains the prompt templates for generating the final executive and company reports
by synthesizing data from various subworkflows.
"""

# ==================== SCHEMA DEFINITIONS (Pydantic) ====================
from typing import List
from pydantic import BaseModel, Field


# --- Executive: Content Performance ---
class ExecTopPostSchema(BaseModel):
    url: str = Field()
    engagement_rate: float = Field()
    key_message: str = Field()

class ExecContentThemeItemSchema(BaseModel):
    theme: str = Field()
    post_count: int = Field()
    avg_engagement: float = Field()
    top_performing_post: ExecTopPostSchema = Field()
    effectiveness_score: float = Field()

class ExecLikesDistributionSchema(BaseModel):
    average: float = Field()
    median: float = Field()
    top_10_percent: float = Field()

class ExecCommentsAnalysisSchema(BaseModel):
    average_per_post: float = Field()
    sentiment_score: float = Field()
    discussion_depth: str = Field()

class ExecSharesImpactSchema(BaseModel):
    average_shares: float = Field()
    viral_coefficient: float = Field()

class ExecEngagementBreakdownSchema(BaseModel):
    likes_distribution: ExecLikesDistributionSchema = Field()
    comments_analysis: ExecCommentsAnalysisSchema = Field()
    shares_impact: ExecSharesImpactSchema = Field()

class ExecPostingPatternsSchema(BaseModel):
    optimal_posting_time: str = Field()
    optimal_posting_day: str = Field()
    current_frequency: str = Field()
    recommended_frequency: str = Field()
    frequency_gap: str = Field()

class ExecDateRangeSchema(BaseModel):
    start_date: str = Field()
    end_date: str = Field()

class ExecPerformanceMetricsSchema(BaseModel):
    total_posts_analyzed: int = Field()
    date_range: ExecDateRangeSchema = Field()
    average_engagement_rate: float = Field()
    viral_post_count: int = Field()
    consistency_score: float = Field()

class ExecContentFormatPerfItemSchema(BaseModel):
    format: str = Field()
    usage_percentage: float = Field()
    avg_engagement: float = Field()
    recommendation: str = Field()

class ExecutiveContentPerformanceSchema(BaseModel):
    performance_metrics: ExecPerformanceMetricsSchema = Field()
    content_themes_analysis: List[ExecContentThemeItemSchema] = Field()
    posting_patterns: ExecPostingPatternsSchema = Field()
    engagement_breakdown: ExecEngagementBreakdownSchema = Field()
    content_format_performance: List[ExecContentFormatPerfItemSchema] = Field()

class ExecutiveContentPerformanceReport(BaseModel):
    executive_content_performance: ExecutiveContentPerformanceSchema = Field()


# --- Executive: Industry Benchmarking ---
class ExecBenchmarkVsTopPerformerSchema(BaseModel):
    engagement_gap: float = Field()
    follower_gap: int = Field()
    content_volume_gap: int = Field()
    authority_score_gap: float = Field()

class ExecBenchmarkVsIndustryAvgSchema(BaseModel):
    engagement_index: float = Field()
    visibility_index: float = Field()
    influence_index: float = Field()

class ExecDirectCompetitorSchema(BaseModel):
    competitor_name: str = Field()
    their_advantage: str = Field()
    your_advantage: str = Field()
    net_position: str = Field()

class ExecContentStrategyGapItemSchema(BaseModel):
    gap_area: str = Field()
    impact: str = Field()
    recommendation: str = Field()

class ExecCompetitiveAdvantageItemSchema(BaseModel):
    advantage: str = Field()
    evidence: str = Field()
    sustainability: str = Field()

class ExecBenchmarkMetricsSchema(BaseModel):
    vs_top_performer: ExecBenchmarkVsTopPerformerSchema = Field()
    vs_industry_average: ExecBenchmarkVsIndustryAvgSchema = Field()
    vs_direct_competitors: List[ExecDirectCompetitorSchema] = Field()

class ExecPositionSchema(BaseModel):
    industry_ranking: int = Field()
    percentile: float = Field()
    tier: str = Field()

class ExecutiveIndustryBenchmarkingSchema(BaseModel):
    executive_position: ExecPositionSchema = Field()
    benchmark_metrics: ExecBenchmarkMetricsSchema = Field()
    content_strategy_gaps: List[ExecContentStrategyGapItemSchema] = Field()
    competitive_advantages: List[ExecCompetitiveAdvantageItemSchema] = Field()

class ExecutiveIndustryBenchmarkingReport(BaseModel):
    industry_leader_benchmarking: ExecutiveIndustryBenchmarkingSchema = Field()


# --- Executive: Personal Brand Opportunities ---
class BrandOpportunityItemSchema(BaseModel):
    opportunity_name: str = Field()
    effort_required: str = Field()
    expected_impact: str = Field()
    implementation_steps: List[str] = Field()
    success_metric: str = Field()
    timeline: str = Field()

class PowerMoveItemSchema(BaseModel):
    initiative_name: str = Field()
    strategic_value: str = Field()
    resource_requirement: str = Field()
    expected_roi: str = Field()
    implementation_plan: List[str] = Field()
    risk_factors: List[str] = Field()

class GameChangerItemSchema(BaseModel):
    transformation_name: str = Field()
    market_impact: str = Field()
    investment_needed: str = Field()
    time_to_results: str = Field()
    competitive_advantage: str = Field()
    success_indicators: List[str] = Field()

class ContentOpportunitiesSchema(BaseModel):
    untapped_topics: List[str] = Field()
    format_innovations: List[str] = Field()
    collaboration_opportunities: List[str] = Field()
    platform_expansion: List[str] = Field()

class PersonalBrandOpportunitiesSchema(BaseModel):
    quick_wins: List[BrandOpportunityItemSchema] = Field()
    power_moves: List[PowerMoveItemSchema] = Field()
    game_changers: List[GameChangerItemSchema] = Field()
    content_opportunities: ContentOpportunitiesSchema = Field()

class PersonalBrandOpportunitiesReport(BaseModel):
    personal_brand_opportunities: PersonalBrandOpportunitiesSchema = Field()


# --- Executive: Action Plan ---
class ExecActionPlanItemSchema(BaseModel):
    action: str = Field()
    expected_outcome: str = Field()
    time_investment: str = Field()
    resources_needed: str = Field()

class ExecActionPlanInitiativeSchema(BaseModel):
    initiative: str = Field()
    milestones: List[str] = Field()
    success_criteria: str = Field()

class ExecActionPlanCalendarItemSchema(BaseModel):
    week: int = Field()
    content_theme: str = Field()
    post_count: int = Field()
    key_topics: List[str] = Field()

class ExecImmediate30DayPlanSchema(BaseModel):
    week_1_priorities: List[ExecActionPlanItemSchema] = Field()
    week_2_4_initiatives: List[ExecActionPlanInitiativeSchema] = Field()
    quick_content_calendar: List[ExecActionPlanCalendarItemSchema] = Field()

class ExecPillarContentStrategySchema(BaseModel):
    pillars: List[str] = Field()
    summary: str = Field()

class ExecEngagementStrategySchema(BaseModel):
    channels: List[str] = Field()
    cadence: str = Field()
    community_programs: List[str] = Field()

class ExecVisibilityAmplificationSchema(BaseModel):
    tactics: List[str] = Field()
    collaboration_opportunities: List[str] = Field()
    paid_amplification: List[str] = Field()

class Exec90DayAuthoritySchema(BaseModel):
    pillar_content_strategy: ExecPillarContentStrategySchema = Field()
    engagement_strategy: ExecEngagementStrategySchema = Field()
    visibility_amplification: ExecVisibilityAmplificationSchema = Field()

class ExecSuccessKpiSchema(BaseModel):
    metric: str = Field()
    current_value: str = Field()
    day_30_target: str = Field(alias="30_day_target")
    day_90_target: str = Field(alias="90_day_target")

class ExecSuccessTrackingSchema(BaseModel):
    kpis: List[ExecSuccessKpiSchema] = Field()
    review_schedule: str = Field()
    adjustment_triggers: List[str] = Field()

class ExecutiveActionPlanSchema(BaseModel):
    immediate_30_day_plan: ExecImmediate30DayPlanSchema = Field()
    day_90_authority_building: Exec90DayAuthoritySchema = Field(alias="90_day_authority_building")
    success_tracking: ExecSuccessTrackingSchema = Field()

class ExecutiveActionPlanReport(BaseModel):
    executive_action_plan: ExecutiveActionPlanSchema = Field()


# --- Company: Blog Performance Health ---
class BlogDateRangeSchema(BaseModel):
    start: str = Field()
    end: str = Field()

class BlogOverallHealthMetricsSchema(BaseModel):
    health_score: float = Field()
    health_status: str = Field()
    total_posts_analyzed: int = Field()
    date_range_analyzed: BlogDateRangeSchema = Field()

class BlogContentVelocitySchema(BaseModel):
    current_rate: str = Field()
    consistency_score: float = Field()
    publishing_gaps: List[str] = Field()
    optimal_rate: str = Field()
    velocity_trend: str = Field()

class BlogFunnelStageSchema(BaseModel):
    count: int = Field()
    percentage: float = Field()
    quality_score: float = Field()

class BlogFunnelCoverageSchema(BaseModel):
    awareness_posts: BlogFunnelStageSchema = Field()
    consideration_posts: BlogFunnelStageSchema = Field()
    purchase_posts: BlogFunnelStageSchema = Field()
    retention_posts: BlogFunnelStageSchema = Field()
    funnel_balance_score: float = Field()
    biggest_gap: str = Field()

class BlogContentTypeItemSchema(BaseModel):
    type: str = Field()
    count: int = Field()
    avg_length: int = Field()
    effectiveness_score: float = Field()

class BlogContentMixEffectivenessSchema(BaseModel):
    content_types: List[BlogContentTypeItemSchema] = Field()
    optimal_mix_recommendation: str = Field()

class BlogPerformanceHealthSchema(BaseModel):
    overall_health_metrics: BlogOverallHealthMetricsSchema = Field()
    content_velocity: BlogContentVelocitySchema = Field()
    funnel_coverage: BlogFunnelCoverageSchema = Field()
    content_mix_effectiveness: BlogContentMixEffectivenessSchema = Field()

class BlogPerformanceHealthReport(BaseModel):
    blog_performance_health: BlogPerformanceHealthSchema = Field()


# --- Company: Content Quality & Structure ---
class ContentQualityReadabilityDistributionSchema(BaseModel):
    easy: float = Field()
    moderate: float = Field()
    difficult: float = Field()

class ContentQualityReadabilitySchema(BaseModel):
    average_score: float = Field()
    distribution: ContentQualityReadabilityDistributionSchema = Field()

class ContentStructureQualitySchema(BaseModel):
    avg_headings_per_post: float = Field()
    avg_paragraphs_per_post: float = Field()
    bullet_points_usage: float = Field()
    media_inclusion_rate: float = Field()

class ContentDepthAnalysisSchema(BaseModel):
    avg_word_count: int = Field()
    comprehensive_posts: float = Field()
    surface_level_posts: float = Field()

class ContentQualityMetricsSchema(BaseModel):
    readability_analysis: ContentQualityReadabilitySchema = Field()
    structure_quality: ContentStructureQualitySchema = Field()
    depth_analysis: ContentDepthAnalysisSchema = Field()

class TopicAuthorityItemSchema(BaseModel):
    topic: str = Field()
    post_count: int = Field()
    authority_score: float = Field()
    coverage_depth: str = Field()

class TopicAuthoritySchema(BaseModel):
    primary_topics: List[TopicAuthorityItemSchema] = Field()
    topic_gaps: List[str] = Field()
    emerging_topics: List[str] = Field()

class UserIntentAlignmentSchema(BaseModel):
    informational_content: float = Field()
    commercial_content: float = Field()
    transactional_content: float = Field()
    navigational_content: float = Field()
    intent_balance_score: float = Field()

class EeatAssessmentSchema(BaseModel):
    experience: float = Field()
    expertise: float = Field()
    authoritativeness: float = Field()
    trustworthiness: float = Field()
    notes: str = Field()

class ContentQualityStructureSchema(BaseModel):
    eeat_assessment: EeatAssessmentSchema = Field()
    content_quality_metrics: ContentQualityMetricsSchema = Field()
    topic_authority: TopicAuthoritySchema = Field()
    user_intent_alignment: UserIntentAlignmentSchema = Field()

class ContentQualityStructureReport(BaseModel):
    content_quality_structure: ContentQualityStructureSchema = Field()


# --- Company: Competitive Intelligence ---
class CompetitiveMarketPositionSchema(BaseModel):
    overall_ranking: int = Field()
    market_share_estimate: float = Field()
    position_trend: str = Field()
    key_differentiators: List[str] = Field()

class CompetitiveContentStrategySchema(BaseModel):
    summary: str = Field()
    key_elements: List[str] = Field()

class CompetitiveCompetitorItemSchema(BaseModel):
    competitor_name: str = Field()
    threat_level: str = Field()
    content_strategy: CompetitiveContentStrategySchema = Field()
    competitive_advantages: List[str] = Field()
    vulnerabilities: List[str] = Field()
    win_strategy: str = Field()

class CompetitiveGapItemSchema(BaseModel):
    gap_area: str = Field()
    impact: str = Field()
    competitors_ahead: List[str] = Field()
    catch_up_strategy: str = Field()
    estimated_time: str = Field()

class CompetitiveOpportunityItemSchema(BaseModel):
    opportunity: str = Field()
    first_mover_advantage: bool = Field()
    difficulty: str = Field()
    expected_impact: str = Field()

class CompetitiveIntelligenceSchema(BaseModel):
    market_position: CompetitiveMarketPositionSchema = Field()
    competitor_analysis: List[CompetitiveCompetitorItemSchema] = Field()
    competitive_gaps: List[CompetitiveGapItemSchema] = Field()
    competitive_opportunities: List[CompetitiveOpportunityItemSchema] = Field()

class CompetitiveIntelligenceReport(BaseModel):
    competitive_intelligence: CompetitiveIntelligenceSchema = Field()


# --- Company: Content Gap Analysis ---
class ContentGapRecommendedItemSchema(BaseModel):
    content_title: str = Field()
    content_type: str = Field()
    target_keywords: List[str] = Field()
    estimated_impact: str = Field()

class CompetitorCoverageSchema(BaseModel):
    competitors: List[str] = Field()
    coverage_level: str = Field()
    notes: str = Field()

class ContentGapCriticalItemSchema(BaseModel):
    gap_title: str = Field()
    gap_type: str = Field()
    business_impact: str = Field()
    competitor_coverage: CompetitorCoverageSchema = Field()
    recommended_content: List[ContentGapRecommendedItemSchema] = Field()

class ContentGapOpportunityItemSchema(BaseModel):
    topic: str = Field()
    search_volume: str = Field()
    competition_level: float = Field()
    relevance_score: float = Field()
    priority: str = Field()

class QuickWinItemSchema(BaseModel):
    topic: str = Field()
    rationale: str = Field()
    expected_impact: str = Field()

class ContentGapOpportunityMatrixSchema(BaseModel):
    high_value_low_competition: List[ContentGapOpportunityItemSchema] = Field()
    quick_wins: List[QuickWinItemSchema] = Field()

class ContentCalendarRecommendationItemSchema(BaseModel):
    week: int = Field()
    priority_topics: List[str] = Field()
    content_formats: List[str] = Field()
    funnel_stage: str = Field()

class ContentCalendarRecommendationsSchema(BaseModel):
    next_30_days: List[ContentCalendarRecommendationItemSchema] = Field()
    quarterly_themes: List[str] = Field()

class ContentGapAnalysisSchema(BaseModel):
    critical_content_gaps: List[ContentGapCriticalItemSchema] = Field()
    opportunity_matrix: ContentGapOpportunityMatrixSchema = Field()
    content_calendar_recommendations: ContentCalendarRecommendationsSchema = Field()

class ContentGapAnalysisReport(BaseModel):
    content_gap_analysis: ContentGapAnalysisSchema = Field()


# --- Company: Strategic Opportunities ---
class MarketOpportunityItemSchema(BaseModel):
    opportunity_name: str = Field()
    market_size: str = Field()
    growth_potential: str = Field()
    competitive_landscape: str = Field()
    entry_strategy: str = Field()
    resource_requirements: str = Field()
    expected_timeline: str = Field()

class ContentDifferentiationItemSchema(BaseModel):
    angle: str = Field()
    rationale: str = Field()
    implementation_approach: str = Field()
    competitive_advantage: str = Field()

class AiOptimizationOpportunityItemSchema(BaseModel):
    suggestion: str = Field()
    expected_impact: str = Field()

class PartnershipOpportunityItemSchema(BaseModel):
    partner: str = Field()
    rationale: str = Field()
    expected_impact: str = Field()

class StrategicOpportunitiesSchema(BaseModel):
    market_opportunities: List[MarketOpportunityItemSchema] = Field()
    content_differentiation: List[ContentDifferentiationItemSchema] = Field()
    ai_optimization_opportunities: List[AiOptimizationOpportunityItemSchema] = Field()
    partnership_opportunities: List[PartnershipOpportunityItemSchema] = Field()

class StrategicOpportunitiesReport(BaseModel):
    strategic_opportunities: StrategicOpportunitiesSchema = Field()


# --- Company: Action Plan ---
class CompanyPriorityFixItemSchema(BaseModel):
    action: str = Field()
    category: str = Field()
    effort: str = Field()
    impact: str = Field()
    owner: str = Field()
    deadline: str = Field()

class Company30DayInitiativeSchema(BaseModel):
    initiative: str = Field()
    objectives: List[str] = Field()
    success_metrics: List[str] = Field()
    resources_needed: str = Field()

class Company90DayProjectMilestoneSchema(BaseModel):
    milestone: str = Field()
    target_date: str = Field()
    deliverable: str = Field()

class Company90DayProjectSchema(BaseModel):
    project: str = Field()
    milestones: List[Company90DayProjectMilestoneSchema] = Field()
    expected_outcome: str = Field()

class CompanyContentMixSchema(BaseModel):
    awareness: float = Field()
    consideration: float = Field()
    purchase: float = Field()
    retention: float = Field()

class ContentCalendarSchema(BaseModel):
    entries: List[str] = Field()

class FormatDistributionSchema(BaseModel):
    blog: float = Field()
    video: float = Field()
    guide: float = Field()
    webinar: float = Field()
    other: float = Field()

class CompanyContentStrategySchema(BaseModel):
    content_calendar: ContentCalendarSchema = Field()
    topic_priorities: List[str] = Field()
    format_distribution: FormatDistributionSchema = Field()

class CompanyTechnicalImprovementsSchema(BaseModel):
    critical_fixes: List[str] = Field()
    optimization_queue: List[str] = Field()
    monitoring_setup: List[str] = Field()

class CompanyCompetitiveResponseSchema(BaseModel):
    defensive_actions: List[str] = Field()
    offensive_moves: List[str] = Field()
    monitoring_targets: List[str] = Field()

class CompanyResourceAllocationSchema(BaseModel):
    budget_recommendations: str = Field()
    team_requirements: str = Field()
    tool_requirements: List[str] = Field()
    training_needs: List[str] = Field()

class CompanyPriorityRoadmapSchema(BaseModel):
    immediate_fixes: List[CompanyPriorityFixItemSchema] = Field()
    day_30_initiatives: List[Company30DayInitiativeSchema] = Field(alias="30_day_initiatives")
    day_90_projects: List[Company90DayProjectSchema] = Field(alias="90_day_projects")

class CompanyActionPlanSchema(BaseModel):
    priority_roadmap: CompanyPriorityRoadmapSchema = Field()
    content_strategy: CompanyContentStrategySchema = Field()
    technical_improvements: CompanyTechnicalImprovementsSchema = Field()
    competitive_response: CompanyCompetitiveResponseSchema = Field()
    resource_allocation: CompanyResourceAllocationSchema = Field()

class CompanyActionPlanReport(BaseModel):
    company_action_plan: CompanyActionPlanSchema = Field()


# --- Final: Business Impact Projection ---
class ProjectionImpactWindowSchema(BaseModel):
    traffic_increase: float = Field()
    engagement_increase: float = Field()
    lead_generation: str = Field()
    brand_visibility: str = Field()
    organic_growth: float = Field()
    conversion_improvement: float = Field()
    authority_score_change: float = Field()
    competitive_position_change: str = Field()
    revenue_impact: str = Field()
    market_share_change: float = Field()
    customer_acquisition: str = Field()
    retention_improvement: float = Field()

class ProjectionRoiAnalysisSchema(BaseModel):
    total_investment: str = Field()
    break_even_point: str = Field()
    month_12_roi: float = Field(alias="12_month_roi")
    payback_period: str = Field()

class ProjectionRiskItemSchema(BaseModel):
    risk: str = Field()
    probability: str = Field()
    impact: str = Field()
    mitigation: str = Field()

class ProjectionSuccessMetricSchema(BaseModel):
    metric: str = Field()
    baseline: str = Field()
    day_30_target: str = Field(alias="30_day_target")
    day_60_target: str = Field(alias="60_day_target")
    day_90_target: str = Field(alias="90_day_target")
    measurement_method: str = Field()

class BusinessRiskAssessmentSchema(BaseModel):
    risks: List[ProjectionRiskItemSchema] = Field()
    summary: str = Field()

class BusinessSuccessMetricsSchema(BaseModel):
    metrics: List[ProjectionSuccessMetricSchema] = Field()

class NextStepsSchema(BaseModel):
    immediate_actions: List[str] = Field()
    long_term_actions: List[str] = Field()

class BusinessImpactProjectionSchema(BaseModel):
    expected_outcomes: ProjectionImpactWindowSchema = Field()
    roi_analysis: ProjectionRoiAnalysisSchema = Field()
    risk_assessment: BusinessRiskAssessmentSchema = Field()
    success_metrics: BusinessSuccessMetricsSchema = Field()
    next_steps: NextStepsSchema = Field()

class BusinessImpactProjectionReport(BaseModel):
    business_impact_projection: BusinessImpactProjectionSchema = Field()


# --- Export JSON Schema dictionaries ---
EXECUTIVE_CONTENT_PERFORMANCE_SCHEMA = ExecutiveContentPerformanceReport.model_json_schema()
EXECUTIVE_INDUSTRY_BENCHMARKING_SCHEMA = ExecutiveIndustryBenchmarkingReport.model_json_schema()
PERSONAL_BRAND_OPPORTUNITIES_SCHEMA = PersonalBrandOpportunitiesReport.model_json_schema()
EXECUTIVE_ACTION_PLAN_SCHEMA = ExecutiveActionPlanReport.model_json_schema()
BLOG_PERFORMANCE_HEALTH_SCHEMA = BlogPerformanceHealthReport.model_json_schema()
CONTENT_QUALITY_STRUCTURE_SCHEMA = ContentQualityStructureReport.model_json_schema()
COMPETITIVE_INTELLIGENCE_SCHEMA = CompetitiveIntelligenceReport.model_json_schema()
CONTENT_GAP_ANALYSIS_SCHEMA = ContentGapAnalysisReport.model_json_schema()
STRATEGIC_OPPORTUNITIES_SCHEMA = StrategicOpportunitiesReport.model_json_schema()
COMPANY_ACTION_PLAN_SCHEMA = CompanyActionPlanReport.model_json_schema()
BUSINESS_IMPACT_PROJECTION_SCHEMA = BusinessImpactProjectionReport.model_json_schema()


# ==================== EXECUTIVE REPORTS ====================

EXECUTIVE_CONTENT_PERFORMANCE_PROMPT = """
You are analyzing LinkedIn content performance data to generate an executive content performance report.

Follow the provided output schema strictly. Do not include any example schema in your response.

LinkedIn Content Analysis Data:
{linkedin_content_data}

AI Visibility Data:
{ai_visibility_data}
"""

EXECUTIVE_INDUSTRY_BENCHMARKING_PROMPT = """
You are generating an executive industry benchmarking report by comparing the executive's LinkedIn performance against competitors.

Follow the provided output schema strictly. Do not include any example schema in your response.

LinkedIn Content Data:
{linkedin_content_data}

Deep Research Data:
{deep_research_data}

Competitor Analysis Data:
{competitor_data}
"""

PERSONAL_BRAND_OPPORTUNITIES_PROMPT = """
You are identifying personal brand opportunities based on LinkedIn content analysis and AI visibility data.

Follow the provided output schema strictly. Do not include any example schema in your response.

LinkedIn Content Analysis:
{linkedin_content_data}

AI Visibility Data:
{ai_visibility_data}
"""

EXECUTIVE_ACTION_PLAN_PROMPT = """
You are creating a comprehensive executive action plan based on all executive analysis reports.

Follow the provided output schema strictly. Do not include any example schema in your response.

Executive Reports Summary:
- Visibility Scorecard: {visibility_scorecard}
- Content Performance: {content_performance}
- Industry Benchmarking: {industry_benchmarking}
- AI Recognition: {ai_recognition}
- Brand Opportunities: {brand_opportunities}
"""

# ==================== COMPANY REPORTS ====================

BLOG_PERFORMANCE_HEALTH_PROMPT = """
You are analyzing blog content data to generate a comprehensive blog performance health check report.

Follow the provided output schema strictly. Do not include any example schema in your response.

Blog Content Analysis Data:
{blog_content_data}

Blog Portfolio Analysis Data:
{blog_portfolio_data}
"""

CONTENT_QUALITY_STRUCTURE_PROMPT = """
You are analyzing blog content quality and structure based on classified posts and content analysis data.

Follow the provided output schema strictly. Do not include any example schema in your response.

Classified Posts Data:
{{classified_posts_data}}

Content Analysis Data:
{{content_analysis_data}}
"""

COMPETITIVE_INTELLIGENCE_PROMPT = """
You are generating a competitive intelligence report based on company blog content, competitor content analysis and deep research insights.

Follow the provided output schema strictly. Do not include any example schema in your response.

Blog Content Analysis:
{blog_content_data}

Competitor Content Analysis:
{competitor_data}

Deep Research Insights:
{deep_research_data}
"""

CONTENT_GAP_ANALYSIS_PROMPT = """
You are performing a content gap analysis by comparing company content against competitors and market research.

Follow the provided output schema strictly. Do not include any example schema in your response.

Blog Content Analysis:
{blog_content_data}

Competitor Content Analysis:
{competitor_data}

Deep Research Insights:
{deep_research_data}
"""

STRATEGIC_OPPORTUNITIES_PROMPT = """
You are identifying strategic opportunities based on deep research, blog portfolio analysis, and comprehensive blog analysis.

Follow the provided output schema strictly. Do not include any example schema in your response.

Deep Research Data:
{deep_research_data}  

Blog Portfolio Analysis:
{blog_portfolio_data}

Blog Content Analysis:
{blog_content_data}
"""

COMPANY_ACTION_PLAN_PROMPT = """
You are creating a comprehensive company action plan based on all company analysis reports.

Follow the provided output schema strictly. Do not include any example schema in your response.

Company Reports Summary:
- AI Visibility: {ai_visibility_overview}
- Blog Performance: {blog_performance}
- Technical SEO: {technical_seo}
- Content Quality: {content_quality}
- Competitive Intelligence: {competitive_intel}
- Content Gaps: {content_gaps}
- Strategic Opportunities: {strategic_opps}
"""

BUSINESS_IMPACT_PROJECTION_PROMPT = """
You are creating a business impact projection based on all executive and company analysis reports.

Follow the provided output schema strictly. Do not include any example schema in your response.

Executive Action Plan:
{executive_action_plan}

Company Action Plan:
{company_action_plan}

All Reports Summary:
{all_reports}
"""