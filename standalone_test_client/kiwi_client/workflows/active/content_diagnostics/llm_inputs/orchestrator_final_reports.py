"""
LLM Input Templates for Orchestrator Final Report Generation

This module contains the prompt templates for generating the final executive and company reports
by synthesizing data from various subworkflows.
"""

# ==================== SCHEMA DEFINITIONS (Pydantic) ====================
from typing import List, Optional
from pydantic import BaseModel, Field


# --- Executive: Content Performance ---
class ExecTopPostSchema(BaseModel):
    url: Optional[str] = Field(default=None)
    engagement_rate: Optional[float] = Field(default=None)
    key_message: Optional[str] = Field(default=None)

class ExecContentThemeItemSchema(BaseModel):
    theme: Optional[str] = Field(default=None)
    post_count: Optional[int] = Field(default=None)
    avg_engagement: Optional[float] = Field(default=None)
    top_performing_post: Optional[ExecTopPostSchema] = Field(default=None)
    effectiveness_score: Optional[float] = Field(default=None)

class ExecLikesDistributionSchema(BaseModel):
    average: Optional[float] = Field(default=None)
    median: Optional[float] = Field(default=None)
    top_10_percent: Optional[float] = Field(default=None)

class ExecCommentsAnalysisSchema(BaseModel):
    average_per_post: Optional[float] = Field(default=None)
    sentiment_score: Optional[float] = Field(default=None)
    discussion_depth: Optional[str] = Field(default=None)

class ExecSharesImpactSchema(BaseModel):
    average_shares: Optional[float] = Field(default=None)
    viral_coefficient: Optional[float] = Field(default=None)

class ExecEngagementBreakdownSchema(BaseModel):
    likes_distribution: Optional[ExecLikesDistributionSchema] = Field(default=None)
    comments_analysis: Optional[ExecCommentsAnalysisSchema] = Field(default=None)
    shares_impact: Optional[ExecSharesImpactSchema] = Field(default=None)

class ExecPostingPatternsSchema(BaseModel):
    optimal_posting_time: Optional[str] = Field(default=None)
    optimal_posting_day: Optional[str] = Field(default=None)
    current_frequency: Optional[str] = Field(default=None)
    recommended_frequency: Optional[str] = Field(default=None)
    frequency_gap: Optional[str] = Field(default=None)

class ExecDateRangeSchema(BaseModel):
    start_date: Optional[str] = Field(default=None)
    end_date: Optional[str] = Field(default=None)

class ExecPerformanceMetricsSchema(BaseModel):
    total_posts_analyzed: Optional[int] = Field(default=None)
    date_range: Optional[ExecDateRangeSchema] = Field(default=None)
    average_engagement_rate: Optional[float] = Field(default=None)
    viral_post_count: Optional[int] = Field(default=None)
    consistency_score: Optional[float] = Field(default=None)

class ExecContentFormatPerfItemSchema(BaseModel):
    format: Optional[str] = Field(default=None)
    usage_percentage: Optional[float] = Field(default=None)
    avg_engagement: Optional[float] = Field(default=None)
    recommendation: Optional[str] = Field(default=None)

class ExecutiveContentPerformanceSchema(BaseModel):
    performance_metrics: Optional[ExecPerformanceMetricsSchema] = Field(default=None)
    content_themes_analysis: Optional[List[ExecContentThemeItemSchema]] = Field(default=None)
    posting_patterns: Optional[ExecPostingPatternsSchema] = Field(default=None)
    engagement_breakdown: Optional[ExecEngagementBreakdownSchema] = Field(default=None)
    content_format_performance: Optional[List[ExecContentFormatPerfItemSchema]] = Field(default=None)

class ExecutiveContentPerformanceReport(BaseModel):
    executive_content_performance: Optional[ExecutiveContentPerformanceSchema] = Field(default=None)


# --- Executive: Industry Benchmarking ---
class ExecBenchmarkVsTopPerformerSchema(BaseModel):
    engagement_gap: Optional[float] = Field(default=None)
    follower_gap: Optional[int] = Field(default=None)
    content_volume_gap: Optional[int] = Field(default=None)
    authority_score_gap: Optional[float] = Field(default=None)

class ExecBenchmarkVsIndustryAvgSchema(BaseModel):
    engagement_index: Optional[float] = Field(default=None)
    visibility_index: Optional[float] = Field(default=None)
    influence_index: Optional[float] = Field(default=None)

class ExecDirectCompetitorSchema(BaseModel):
    competitor_name: Optional[str] = Field(default=None)
    their_advantage: Optional[str] = Field(default=None)
    your_advantage: Optional[str] = Field(default=None)
    net_position: Optional[str] = Field(default=None)

class ExecBenchmarkMetricsSchema(BaseModel):
    vs_top_performer: Optional[ExecBenchmarkVsTopPerformerSchema] = Field(default=None)
    vs_industry_average: Optional[ExecBenchmarkVsIndustryAvgSchema] = Field(default=None)
    vs_direct_competitors: Optional[List[ExecDirectCompetitorSchema]] = Field(default=None)

class ExecPositionSchema(BaseModel):
    industry_ranking: Optional[int] = Field(default=None)
    percentile: Optional[float] = Field(default=None)
    tier: Optional[str] = Field(default=None)

class ExecutiveIndustryBenchmarkingSchema(BaseModel):
    executive_position: Optional[ExecPositionSchema] = Field(default=None)
    benchmark_metrics: Optional[ExecBenchmarkMetricsSchema] = Field(default=None)
    content_strategy_gaps: Optional[List[dict]] = Field(default=None)
    competitive_advantages: Optional[List[dict]] = Field(default=None)

class ExecutiveIndustryBenchmarkingReport(BaseModel):
    industry_leader_benchmarking: Optional[ExecutiveIndustryBenchmarkingSchema] = Field(default=None)


# --- Executive: Personal Brand Opportunities ---
class BrandOpportunityItemSchema(BaseModel):
    opportunity_name: Optional[str] = Field(default=None)
    effort_required: Optional[str] = Field(default=None)
    expected_impact: Optional[str] = Field(default=None)
    implementation_steps: Optional[List[str]] = Field(default=None)
    success_metric: Optional[str] = Field(default=None)
    timeline: Optional[str] = Field(default=None)

class PowerMoveItemSchema(BaseModel):
    initiative_name: Optional[str] = Field(default=None)
    strategic_value: Optional[str] = Field(default=None)
    resource_requirement: Optional[str] = Field(default=None)
    expected_roi: Optional[str] = Field(default=None)
    implementation_plan: Optional[List[str]] = Field(default=None)
    risk_factors: Optional[List[str]] = Field(default=None)

class GameChangerItemSchema(BaseModel):
    transformation_name: Optional[str] = Field(default=None)
    market_impact: Optional[str] = Field(default=None)
    investment_needed: Optional[str] = Field(default=None)
    time_to_results: Optional[str] = Field(default=None)
    competitive_advantage: Optional[str] = Field(default=None)
    success_indicators: Optional[List[str]] = Field(default=None)

class ContentOpportunitiesSchema(BaseModel):
    untapped_topics: Optional[List[str]] = Field(default=None)
    format_innovations: Optional[List[str]] = Field(default=None)
    collaboration_opportunities: Optional[List[str]] = Field(default=None)
    platform_expansion: Optional[List[str]] = Field(default=None)

class PersonalBrandOpportunitiesSchema(BaseModel):
    quick_wins: Optional[List[BrandOpportunityItemSchema]] = Field(default=None)
    power_moves: Optional[List[PowerMoveItemSchema]] = Field(default=None)
    game_changers: Optional[List[GameChangerItemSchema]] = Field(default=None)
    content_opportunities: Optional[ContentOpportunitiesSchema] = Field(default=None)

class PersonalBrandOpportunitiesReport(BaseModel):
    personal_brand_opportunities: Optional[PersonalBrandOpportunitiesSchema] = Field(default=None)


# --- Executive: Action Plan ---
class ExecActionPlanItemSchema(BaseModel):
    action: Optional[str] = Field(default=None)
    expected_outcome: Optional[str] = Field(default=None)
    time_investment: Optional[str] = Field(default=None)
    resources_needed: Optional[str] = Field(default=None)

class ExecActionPlanInitiativeSchema(BaseModel):
    initiative: Optional[str] = Field(default=None)
    milestones: Optional[List[str]] = Field(default=None)
    success_criteria: Optional[str] = Field(default=None)

class ExecActionPlanCalendarItemSchema(BaseModel):
    week: Optional[int] = Field(default=None)
    content_theme: Optional[str] = Field(default=None)
    post_count: Optional[int] = Field(default=None)
    key_topics: Optional[List[str]] = Field(default=None)

class ExecImmediate30DayPlanSchema(BaseModel):
    week_1_priorities: Optional[List[ExecActionPlanItemSchema]] = Field(default=None)
    week_2_4_initiatives: Optional[List[ExecActionPlanInitiativeSchema]] = Field(default=None)
    quick_content_calendar: Optional[List[ExecActionPlanCalendarItemSchema]] = Field(default=None)

class Exec90DayAuthoritySchema(BaseModel):
    pillar_content_strategy: Optional[dict] = Field(default=None)
    engagement_strategy: Optional[dict] = Field(default=None)
    visibility_amplification: Optional[dict] = Field(default=None)

class ExecSuccessKpiSchema(BaseModel):
    metric: Optional[str] = Field(default=None)
    current_value: Optional[str] = Field(default=None)
    _30_day_target: Optional[str] = Field(alias="30_day_target", default=None)
    _90_day_target: Optional[str] = Field(alias="90_day_target", default=None)

class ExecSuccessTrackingSchema(BaseModel):
    kpis: Optional[List[ExecSuccessKpiSchema]] = Field(default=None)
    review_schedule: Optional[str] = Field(default=None)
    adjustment_triggers: Optional[List[str]] = Field(default=None)

class ExecutiveActionPlanSchema(BaseModel):
    immediate_30_day_plan: Optional[ExecImmediate30DayPlanSchema] = Field(default=None)
    _90_day_authority_building: Optional[Exec90DayAuthoritySchema] = Field(alias="90_day_authority_building", default=None)
    success_tracking: Optional[ExecSuccessTrackingSchema] = Field(default=None)

class ExecutiveActionPlanReport(BaseModel):
    executive_action_plan: Optional[ExecutiveActionPlanSchema] = Field(default=None)


# --- Company: Blog Performance Health ---
class BlogDateRangeSchema(BaseModel):
    start: Optional[str] = Field(default=None)
    end: Optional[str] = Field(default=None)

class BlogOverallHealthMetricsSchema(BaseModel):
    health_score: Optional[float] = Field(default=None)
    health_status: Optional[str] = Field(default=None)
    total_posts_analyzed: Optional[int] = Field(default=None)
    date_range_analyzed: Optional[BlogDateRangeSchema] = Field(default=None)

class BlogContentVelocitySchema(BaseModel):
    current_rate: Optional[str] = Field(default=None)
    consistency_score: Optional[float] = Field(default=None)
    publishing_gaps: Optional[List[str]] = Field(default=None)
    optimal_rate: Optional[str] = Field(default=None)
    velocity_trend: Optional[str] = Field(default=None)

class BlogFunnelStageSchema(BaseModel):
    count: Optional[int] = Field(default=None)
    percentage: Optional[float] = Field(default=None)
    quality_score: Optional[float] = Field(default=None)

class BlogFunnelCoverageSchema(BaseModel):
    awareness_posts: Optional[BlogFunnelStageSchema] = Field(default=None)
    consideration_posts: Optional[BlogFunnelStageSchema] = Field(default=None)
    purchase_posts: Optional[BlogFunnelStageSchema] = Field(default=None)
    retention_posts: Optional[BlogFunnelStageSchema] = Field(default=None)
    funnel_balance_score: Optional[float] = Field(default=None)
    biggest_gap: Optional[str] = Field(default=None)

class BlogContentTypeItemSchema(BaseModel):
    type: Optional[str] = Field(default=None)
    count: Optional[int] = Field(default=None)
    avg_length: Optional[int] = Field(default=None)
    effectiveness_score: Optional[float] = Field(default=None)

class BlogContentMixEffectivenessSchema(BaseModel):
    content_types: Optional[List[BlogContentTypeItemSchema]] = Field(default=None)
    optimal_mix_recommendation: Optional[str] = Field(default=None)

class BlogPerformanceHealthSchema(BaseModel):
    overall_health_metrics: Optional[BlogOverallHealthMetricsSchema] = Field(default=None)
    content_velocity: Optional[BlogContentVelocitySchema] = Field(default=None)
    funnel_coverage: Optional[BlogFunnelCoverageSchema] = Field(default=None)
    content_mix_effectiveness: Optional[BlogContentMixEffectivenessSchema] = Field(default=None)

class BlogPerformanceHealthReport(BaseModel):
    blog_performance_health: Optional[BlogPerformanceHealthSchema] = Field(default=None)


# --- Company: Content Quality & Structure ---
class ContentQualityReadabilityDistributionSchema(BaseModel):
    easy: Optional[float] = Field(default=None)
    moderate: Optional[float] = Field(default=None)
    difficult: Optional[float] = Field(default=None)

class ContentQualityReadabilitySchema(BaseModel):
    average_score: Optional[float] = Field(default=None)
    distribution: Optional[ContentQualityReadabilityDistributionSchema] = Field(default=None)

class ContentStructureQualitySchema(BaseModel):
    avg_headings_per_post: Optional[float] = Field(default=None)
    avg_paragraphs_per_post: Optional[float] = Field(default=None)
    bullet_points_usage: Optional[float] = Field(default=None)
    media_inclusion_rate: Optional[float] = Field(default=None)

class ContentDepthAnalysisSchema(BaseModel):
    avg_word_count: Optional[int] = Field(default=None)
    comprehensive_posts: Optional[float] = Field(default=None)
    surface_level_posts: Optional[float] = Field(default=None)

class ContentQualityMetricsSchema(BaseModel):
    readability_analysis: Optional[ContentQualityReadabilitySchema] = Field(default=None)
    structure_quality: Optional[ContentStructureQualitySchema] = Field(default=None)
    depth_analysis: Optional[ContentDepthAnalysisSchema] = Field(default=None)

class TopicAuthorityItemSchema(BaseModel):
    topic: Optional[str] = Field(default=None)
    post_count: Optional[int] = Field(default=None)
    authority_score: Optional[float] = Field(default=None)
    coverage_depth: Optional[str] = Field(default=None)

class TopicAuthoritySchema(BaseModel):
    primary_topics: Optional[List[TopicAuthorityItemSchema]] = Field(default=None)
    topic_gaps: Optional[List[str]] = Field(default=None)
    emerging_topics: Optional[List[str]] = Field(default=None)

class UserIntentAlignmentSchema(BaseModel):
    informational_content: Optional[float] = Field(default=None)
    commercial_content: Optional[float] = Field(default=None)
    transactional_content: Optional[float] = Field(default=None)
    navigational_content: Optional[float] = Field(default=None)
    intent_balance_score: Optional[float] = Field(default=None)

class ContentQualityStructureSchema(BaseModel):
    eeat_assessment: Optional[dict] = Field(default=None)
    content_quality_metrics: Optional[ContentQualityMetricsSchema] = Field(default=None)
    topic_authority: Optional[TopicAuthoritySchema] = Field(default=None)
    user_intent_alignment: Optional[UserIntentAlignmentSchema] = Field(default=None)

class ContentQualityStructureReport(BaseModel):
    content_quality_structure: Optional[ContentQualityStructureSchema] = Field(default=None)


# --- Company: Competitive Intelligence ---
class CompetitiveMarketPositionSchema(BaseModel):
    overall_ranking: Optional[int] = Field(default=None)
    market_share_estimate: Optional[float] = Field(default=None)
    position_trend: Optional[str] = Field(default=None)
    key_differentiators: Optional[List[str]] = Field(default=None)

class CompetitiveCompetitorItemSchema(BaseModel):
    competitor_name: Optional[str] = Field(default=None)
    threat_level: Optional[str] = Field(default=None)
    content_strategy: Optional[dict] = Field(default=None)
    competitive_advantages: Optional[List[str]] = Field(default=None)
    vulnerabilities: Optional[List[str]] = Field(default=None)
    win_strategy: Optional[str] = Field(default=None)

class CompetitiveGapItemSchema(BaseModel):
    gap_area: Optional[str] = Field(default=None)
    impact: Optional[str] = Field(default=None)
    competitors_ahead: Optional[List[str]] = Field(default=None)
    catch_up_strategy: Optional[str] = Field(default=None)
    estimated_time: Optional[str] = Field(default=None)

class CompetitiveOpportunityItemSchema(BaseModel):
    opportunity: Optional[str] = Field(default=None)
    first_mover_advantage: Optional[bool] = Field(default=None)
    difficulty: Optional[str] = Field(default=None)
    expected_impact: Optional[str] = Field(default=None)

class CompetitiveIntelligenceSchema(BaseModel):
    market_position: Optional[CompetitiveMarketPositionSchema] = Field(default=None)
    competitor_analysis: Optional[List[CompetitiveCompetitorItemSchema]] = Field(default=None)
    competitive_gaps: Optional[List[CompetitiveGapItemSchema]] = Field(default=None)
    competitive_opportunities: Optional[List[CompetitiveOpportunityItemSchema]] = Field(default=None)

class CompetitiveIntelligenceReport(BaseModel):
    competitive_intelligence: Optional[CompetitiveIntelligenceSchema] = Field(default=None)


# --- Company: Content Gap Analysis ---
class ContentGapRecommendedItemSchema(BaseModel):
    content_title: Optional[str] = Field(default=None)
    content_type: Optional[str] = Field(default=None)
    target_keywords: Optional[List[str]] = Field(default=None)
    estimated_impact: Optional[str] = Field(default=None)

class ContentGapCriticalItemSchema(BaseModel):
    gap_title: Optional[str] = Field(default=None)
    gap_type: Optional[str] = Field(default=None)
    business_impact: Optional[str] = Field(default=None)
    competitor_coverage: Optional[dict] = Field(default=None)
    recommended_content: Optional[List[ContentGapRecommendedItemSchema]] = Field(default=None)

class ContentGapOpportunityItemSchema(BaseModel):
    topic: Optional[str] = Field(default=None)
    search_volume: Optional[str] = Field(default=None)
    competition_level: Optional[float] = Field(default=None)
    relevance_score: Optional[float] = Field(default=None)
    priority: Optional[str] = Field(default=None)

class ContentGapOpportunityMatrixSchema(BaseModel):
    high_value_low_competition: Optional[List[ContentGapOpportunityItemSchema]] = Field(default=None)
    quick_wins: Optional[List[dict]] = Field(default=None)

class ContentCalendarRecommendationItemSchema(BaseModel):
    week: Optional[int] = Field(default=None)
    priority_topics: Optional[List[str]] = Field(default=None)
    content_formats: Optional[List[str]] = Field(default=None)
    funnel_stage: Optional[str] = Field(default=None)

class ContentCalendarRecommendationsSchema(BaseModel):
    next_30_days: Optional[List[ContentCalendarRecommendationItemSchema]] = Field(default=None)
    quarterly_themes: Optional[List[str]] = Field(default=None)

class ContentGapAnalysisSchema(BaseModel):
    critical_content_gaps: Optional[List[ContentGapCriticalItemSchema]] = Field(default=None)
    opportunity_matrix: Optional[ContentGapOpportunityMatrixSchema] = Field(default=None)
    content_calendar_recommendations: Optional[ContentCalendarRecommendationsSchema] = Field(default=None)

class ContentGapAnalysisReport(BaseModel):
    content_gap_analysis: Optional[ContentGapAnalysisSchema] = Field(default=None)


# --- Company: Strategic Opportunities ---
class MarketOpportunityItemSchema(BaseModel):
    opportunity_name: Optional[str] = Field(default=None)
    market_size: Optional[str] = Field(default=None)
    growth_potential: Optional[str] = Field(default=None)
    competitive_landscape: Optional[str] = Field(default=None)
    entry_strategy: Optional[str] = Field(default=None)
    resource_requirements: Optional[str] = Field(default=None)
    expected_timeline: Optional[str] = Field(default=None)

class ContentDifferentiationItemSchema(BaseModel):
    angle: Optional[str] = Field(default=None)
    rationale: Optional[str] = Field(default=None)
    implementation_approach: Optional[str] = Field(default=None)
    competitive_advantage: Optional[str] = Field(default=None)

class StrategicOpportunitiesSchema(BaseModel):
    market_opportunities: Optional[List[MarketOpportunityItemSchema]] = Field(default=None)
    content_differentiation: Optional[dict] = Field(default=None)
    ai_optimization_opportunities: Optional[List[dict]] = Field(default=None)
    partnership_opportunities: Optional[List[dict]] = Field(default=None)

class StrategicOpportunitiesReport(BaseModel):
    strategic_opportunities: Optional[StrategicOpportunitiesSchema] = Field(default=None)


# --- Company: Action Plan ---
class CompanyPriorityFixItemSchema(BaseModel):
    action: Optional[str] = Field(default=None)
    category: Optional[str] = Field(default=None)
    effort: Optional[str] = Field(default=None)
    impact: Optional[str] = Field(default=None)
    owner: Optional[str] = Field(default=None)
    deadline: Optional[str] = Field(default=None)

class Company30DayInitiativeSchema(BaseModel):
    initiative: Optional[str] = Field(default=None)
    objectives: Optional[List[str]] = Field(default=None)
    success_metrics: Optional[List[str]] = Field(default=None)
    resources_needed: Optional[str] = Field(default=None)

class Company90DayProjectMilestoneSchema(BaseModel):
    milestone: Optional[str] = Field(default=None)
    target_date: Optional[str] = Field(default=None)
    deliverable: Optional[str] = Field(default=None)

class Company90DayProjectSchema(BaseModel):
    project: Optional[str] = Field(default=None)
    milestones: Optional[List[Company90DayProjectMilestoneSchema]] = Field(default=None)
    expected_outcome: Optional[str] = Field(default=None)

class CompanyContentMixSchema(BaseModel):
    awareness: Optional[float] = Field(default=None)
    consideration: Optional[float] = Field(default=None)
    purchase: Optional[float] = Field(default=None)
    retention: Optional[float] = Field(default=None)

class CompanyContentStrategySchema(BaseModel):
    content_calendar: Optional[dict] = Field(default=None)
    topic_priorities: Optional[List[str]] = Field(default=None)
    format_distribution: Optional[dict] = Field(default=None)

class CompanyTechnicalImprovementsSchema(BaseModel):
    critical_fixes: Optional[List[str]] = Field(default=None)
    optimization_queue: Optional[List[str]] = Field(default=None)
    monitoring_setup: Optional[List[str]] = Field(default=None)

class CompanyCompetitiveResponseSchema(BaseModel):
    defensive_actions: Optional[List[str]] = Field(default=None)
    offensive_moves: Optional[List[str]] = Field(default=None)
    monitoring_targets: Optional[List[str]] = Field(default=None)

class CompanyResourceAllocationSchema(BaseModel):
    budget_recommendations: Optional[str] = Field(default=None)
    team_requirements: Optional[str] = Field(default=None)
    tool_requirements: Optional[List[str]] = Field(default=None)
    training_needs: Optional[List[str]] = Field(default=None)

class CompanyPriorityRoadmapSchema(BaseModel):
    immediate_fixes: Optional[List[CompanyPriorityFixItemSchema]] = Field(default=None)
    _30_day_initiatives: Optional[List[Company30DayInitiativeSchema]] = Field(alias="30_day_initiatives", default=None)
    _90_day_projects: Optional[List[Company90DayProjectSchema]] = Field(alias="90_day_projects", default=None)

class CompanyActionPlanSchema(BaseModel):
    priority_roadmap: Optional[CompanyPriorityRoadmapSchema] = Field(default=None)
    content_strategy: Optional[CompanyContentStrategySchema] = Field(default=None)
    technical_improvements: Optional[CompanyTechnicalImprovementsSchema] = Field(default=None)
    competitive_response: Optional[CompanyCompetitiveResponseSchema] = Field(default=None)
    resource_allocation: Optional[CompanyResourceAllocationSchema] = Field(default=None)

class CompanyActionPlanReport(BaseModel):
    company_action_plan: Optional[CompanyActionPlanSchema] = Field(default=None)


# --- Final: Business Impact Projection ---
class ProjectionImpactWindowSchema(BaseModel):
    traffic_increase: Optional[float] = Field(default=None)
    engagement_increase: Optional[float] = Field(default=None)
    lead_generation: Optional[str] = Field(default=None)
    brand_visibility: Optional[str] = Field(default=None)
    organic_growth: Optional[float] = Field(default=None)
    conversion_improvement: Optional[float] = Field(default=None)
    authority_score_change: Optional[float] = Field(default=None)
    competitive_position_change: Optional[str] = Field(default=None)
    revenue_impact: Optional[str] = Field(default=None)
    market_share_change: Optional[float] = Field(default=None)
    customer_acquisition: Optional[str] = Field(default=None)
    retention_improvement: Optional[float] = Field(default=None)

class ProjectionRoiAnalysisSchema(BaseModel):
    total_investment: Optional[str] = Field(default=None)
    break_even_point: Optional[str] = Field(default=None)
    _12_month_roi: Optional[float] = Field(alias="12_month_roi", default=None)
    payback_period: Optional[str] = Field(default=None)

class ProjectionRiskItemSchema(BaseModel):
    risk: Optional[str] = Field(default=None)
    probability: Optional[str] = Field(default=None)
    impact: Optional[str] = Field(default=None)
    mitigation: Optional[str] = Field(default=None)

class ProjectionSuccessMetricSchema(BaseModel):
    metric: Optional[str] = Field(default=None)
    baseline: Optional[str] = Field(default=None)
    _30_day_target: Optional[str] = Field(alias="30_day_target", default=None)
    _60_day_target: Optional[str] = Field(alias="60_day_target", default=None)
    _90_day_target: Optional[str] = Field(alias="90_day_target", default=None)
    measurement_method: Optional[str] = Field(default=None)

class BusinessImpactProjectionSchema(BaseModel):
    expected_outcomes: Optional[dict] = Field(default=None)
    roi_analysis: Optional[ProjectionRoiAnalysisSchema] = Field(default=None)
    risk_assessment: Optional[dict] = Field(default=None)
    success_metrics: Optional[dict] = Field(default=None)
    next_steps: Optional[dict] = Field(default=None)

class BusinessImpactProjectionReport(BaseModel):
    business_impact_projection: Optional[BusinessImpactProjectionSchema] = Field(default=None)


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
{{linkedin_content_data}}
"""

EXECUTIVE_INDUSTRY_BENCHMARKING_PROMPT = """
You are generating an executive industry benchmarking report by comparing the executive's LinkedIn performance against competitors.

Follow the provided output schema strictly. Do not include any example schema in your response.

LinkedIn Content Data:
{{linkedin_content_data}}

Competitor Analysis Data:
{{competitor_data}}
"""

PERSONAL_BRAND_OPPORTUNITIES_PROMPT = """
You are identifying personal brand opportunities based on LinkedIn content analysis and AI visibility data.

Follow the provided output schema strictly. Do not include any example schema in your response.

LinkedIn Content Analysis:
{{linkedin_content_data}}

AI Visibility Data:
{{ai_visibility_data}}
"""

EXECUTIVE_ACTION_PLAN_PROMPT = """
You are creating a comprehensive executive action plan based on all executive analysis reports.

Follow the provided output schema strictly. Do not include any example schema in your response.

Executive Reports Summary:
- Visibility Scorecard: {{visibility_scorecard}}
- Content Performance: {{content_performance}}
- Industry Benchmarking: {{industry_benchmarking}}
- AI Recognition: {{ai_recognition}}
- Brand Opportunities: {{brand_opportunities}}
"""

# ==================== COMPANY REPORTS ====================

BLOG_PERFORMANCE_HEALTH_PROMPT = """
You are analyzing blog content data to generate a comprehensive blog performance health check report.

Follow the provided output schema strictly. Do not include any example schema in your response.

Blog Content Analysis Data:
{{blog_content_data}}
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
You are generating a competitive intelligence report based on competitor content analysis and AI visibility data.

Follow the provided output schema strictly. Do not include any example schema in your response.

Competitor Analysis Data:
{{competitor_data}}

Company AI Visibility Data:
{{ai_visibility_data}}
"""

CONTENT_GAP_ANALYSIS_PROMPT = """
You are performing a content gap analysis by comparing company content against competitors and market research.

Follow the provided output schema strictly. Do not include any example schema in your response.

Blog Content Analysis:
{{blog_content_data}}

Competitor Content Analysis:
{{competitor_data}}

Deep Research Insights:
{{deep_research_data}}
"""

STRATEGIC_OPPORTUNITIES_PROMPT = """
You are identifying strategic opportunities based on deep research and comprehensive market analysis.

Follow the provided output schema strictly. Do not include any example schema in your response.

Deep Research Data:
{{deep_research_data}}

All Analysis Reports:
{{all_reports_summary}}
"""

COMPANY_ACTION_PLAN_PROMPT = """
You are creating a comprehensive company action plan based on all company analysis reports.

Follow the provided output schema strictly. Do not include any example schema in your response.

Company Reports Summary:
- AI Visibility: {{ai_visibility_overview}}
- Blog Performance: {{blog_performance}}
- Technical SEO: {{technical_seo}}
- Content Quality: {{content_quality}}
- Competitive Intelligence: {{competitive_intel}}
- Content Gaps: {{content_gaps}}
- Strategic Opportunities: {{strategic_opps}}
"""

BUSINESS_IMPACT_PROJECTION_PROMPT = """
You are creating a business impact projection based on all executive and company analysis reports.

Follow the provided output schema strictly. Do not include any example schema in your response.

Executive Action Plan:
{{executive_action_plan}}

Company Action Plan:
{{company_action_plan}}

All Reports Summary:
{{all_reports}}
"""