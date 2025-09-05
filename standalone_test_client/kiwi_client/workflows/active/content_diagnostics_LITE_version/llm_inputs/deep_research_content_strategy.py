from typing import List, Dict, Any, Optional
import json

# Using Pydantic for easier schema generation
from pydantic import BaseModel, Field

# --- Schema Definitions ---

class NarrativeBattle(BaseModel):
    """Individual narrative battle in the market"""
    battle_topic: str = Field(description="The narrative battle being fought")
    current_winner: str = Field(description="Who is currently winning this narrative battle")
    competitive_opportunity: str = Field(description="How this company could compete in this narrative")

class CompetitorVulnerability(BaseModel):
    """Specific competitor vulnerability and exploitation strategy"""
    competitor: str = Field(description="Competitor name or category")
    vulnerability: str = Field(description="Specific vulnerability in their positioning")
    exploitation_strategy: str = Field(description="How to exploit this vulnerability")

class ContentDiscoveryPathway(BaseModel):
    """How buyers discover content in specific channels"""
    channel: str = Field(description="Channel or platform name")
    discovery_mechanism: str = Field(description="How buyers actually discover content in this channel")
    optimization_opportunity: str = Field(description="How to optimize for this discovery pathway")

class ChannelRole(BaseModel):
    """Specific role a channel should play in content ecosystem"""
    channel: str = Field(description="Channel or platform name")
    strategic_role: str = Field(description="The specific role this channel should play")
    execution_approach: str = Field(description="How to execute this role effectively")

class ResourceAllocation(BaseModel):
    """Resource allocation strategy for competitive advantage"""
    resource_area: str = Field(description="Area where resources should be allocated")
    allocation_strategy: str = Field(description="How to allocate resources in this area")
    competitive_rationale: str = Field(description="Why this allocation creates competitive advantage")

class MarketDynamicsIntelligence(BaseModel):
    """Market evolution and changing competitive landscape"""
    buyer_behavior_shifts: List[str] = Field(description="How buyer behavior is actively changing in this market (not static patterns)")
    narrative_battles: List[NarrativeBattle] = Field(description="Key narrative battles being fought and who's winning each one")
    emerging_threats: List[str] = Field(description="Indirect competitors and market forces that could disrupt current strategies")
    algorithm_evolution_impact: str = Field(description="How platform algorithm changes are affecting content discovery and engagement")
    cultural_shifts_impact: str = Field(description="Broader cultural or behavioral shifts affecting how buyers consume content")
    market_timing_windows: List[str] = Field(description="Time-sensitive opportunities or threats based on market evolution")
    strategy_decay_analysis: str = Field(description="Which previously successful strategies are losing effectiveness and why")

class CompetitivePositioningIntelligence(BaseModel):
    """Unique positioning opportunities and competitive advantages"""
    ownable_narrative_positions: List[str] = Field(description="Narrative positions this company could uniquely own that competitors cannot match")
    competitor_vulnerabilities: List[CompetitorVulnerability] = Field(description="Specific vulnerabilities in competitor positioning and how to exploit them")
    unique_advantage_amplification: str = Field(description="How to amplify unique company advantages that competitors cannot replicate")
    narrative_reframing_opportunities: List[str] = Field(description="Ways to reframe market conversations to favor this company's strengths")
    competitive_blind_spots: List[str] = Field(description="Areas competitors are neglecting that present positioning opportunities")
    differentiation_moats: List[str] = Field(description="Sustainable differentiation strategies that create barriers to competitive replication")

class EcosystemOrchestrationIntelligence(BaseModel):
    """Cross-channel content flow and discovery ecosystem orchestration"""
    discovery_pathways: List[ContentDiscoveryPathway] = Field(description="How buyers actually discover content across different channels and platforms")
    narrative_origination_vs_validation: str = Field(description="Which channels are best for introducing new narratives vs. validating established ones")
    cross_channel_amplification_strategy: List[str] = Field(description="How to orchestrate content across channels for maximum cumulative impact")
    indirect_influence_channels: List[str] = Field(description="Channels that indirectly influence buyer perceptions (Reddit, AI training data, etc.)")
    ecosystem_timing_orchestration: str = Field(description="Optimal timing and sequencing of content across the discovery ecosystem")
    channel_roles: List[ChannelRole] = Field(description="The specific role each channel should play in the overall content ecosystem")

class DecisionIntelligence(BaseModel):
    """Actionable intelligence for strategic decision-making"""
    three_battles_to_win: List[str] = Field(description="The three specific competitive battles this company must win to succeed")
    one_position_to_own: str = Field(description="The single narrative position this company should own in the market")
    five_strategic_moves: List[str] = Field(description="The five specific moves to execute the positioning strategy")
    key_success_indicator: str = Field(description="The one key metric that indicates whether the strategy is working")
    execution_sequence_priority: List[str] = Field(description="The order in which strategic moves should be executed for maximum impact")
    resource_allocation: List[ResourceAllocation] = Field(description="How to allocate limited resources for maximum competitive advantage")

class SuccessfulContentPatternSchema(BaseModel):
    """Individual successful content pattern with strategic intelligence"""
    pattern: str = Field(description="Pattern description")
    industry_adoption: str = Field(description="Level of industry adoption (high/medium/low)")
    pipeline_impact: str = Field(description="How this pattern drives business outcomes")
    source_evidence: str = Field(description="Specific source or evidence supporting this pattern's effectiveness")

class ContentTypeIntelligence(BaseModel):
    """Content type with focused intelligence"""
    content_type: str = Field(description="Specific content type (e.g., 'data-driven case studies', 'peer comparison matrices')")
    effectiveness_score: int = Field(description="Effectiveness score out of 100 for this specific content type in successful company strategies")
    buyer_segment_fit: str = Field(description="Which buyer segments respond to this content type")
    roi_driver: str = Field(description="Primary mechanism by which this content type drives business outcomes")

class IndustryBestPracticesSchema(BaseModel):
    """Industry intelligence with context-specific insights rather than generic percentages"""
    content_type_intelligence: List[ContentTypeIntelligence] = Field(description="Deep intelligence on each content type's effectiveness mechanisms")
    market_context_analysis: str = Field(description="How market maturity, competitive intensity, and buyer sophistication affect content strategy")
    narrative_battle_landscape: str = Field(description="The key narrative battles being fought in this market and who's winning")
    buyer_trust_mechanism_analysis: str = Field(description="How buyers build trust in this market and what content formats facilitate trust")
    competitive_content_moats: str = Field(description="How market leaders create sustainable content advantages that competitors cannot replicate")
    content_timing_intelligence: str = Field(description="How content consumption patterns are evolving and what this means for strategy")
    successful_content_patterns: List[SuccessfulContentPatternSchema] = Field(description="List of successful content patterns with strategic analysis")
    source_validation: str = Field(description="Primary sources and evidence supporting these insights")

class ContentFormatStrategySchema(BaseModel):
    """Individual content format strategy with focused intelligence"""
    format: str = Field(description="Content format type")
    content_type: str = Field(description="Content type classification")
    strategic_purpose: str = Field(description="Why this format works at this stage")
    stage_allocation_score: int = Field(description="Allocation priority score out of 100 for this format within this stage")
    effectiveness_score: int = Field(description="Effectiveness score (1-100, where 100 is highest effectiveness)")
    performance_evidence: str = Field(description="Specific evidence or case studies supporting this format's effectiveness")

class TopicCategorySchema(BaseModel):
    """Individual topic category with strategic intelligence"""
    category: str = Field(description="Broad topic category")
    priority_level: int = Field(description="Priority level (1-100, where 100 is highest priority)")
    content_volume_recommendation: str = Field(description="Recommended content volume")
    example_topics: List[str] = Field(description="Example topics within this category")
    priority_rationale: str = Field(description="Strategic reasoning behind this priority level based on market analysis")
    business_impact_pathway: str = Field(description="How content in this category drives specific business outcomes")

class FunnelStageAnalysisSchema(BaseModel):
    """Complete analysis for a single funnel stage with strategic intelligence"""
    stage: str = Field(description="Funnel stage name")
    business_impact_score: int = Field(description="Business impact score (1-100, where 100 is highest business impact)")
    reach_potential_score: int = Field(description="Reach potential score (1-100, where 100 is highest reach potential)")
    industry_priority_level: int = Field(description="Industry priority level (1-100, where 100 is highest industry priority)")
    rationale: str = Field(description="Why this allocation based on industry best practices")
    primary_personas: List[str] = Field(description="Primary personas for this stage")
    user_intent: str = Field(description="What users are trying to accomplish at this stage")
    conversion_psychology: str = Field(description="Psychological factors that drive progression from this stage to the next")
    competitive_battleground_analysis: str = Field(description="How competitors compete at this stage and opportunities for differentiation")
    resource_allocation_rationale: str = Field(description="Why this percentage allocation maximizes ROI based on market dynamics")
    success_pattern_analysis: str = Field(description="Patterns observed in companies that excel at this funnel stage")
    common_failure_modes: List[str] = Field(description="Common ways companies fail at this stage and how to avoid them")
    measurement_framework: str = Field(description="How to measure success at this stage and leading indicators")
    content_format_strategy: List[ContentFormatStrategySchema] = Field(description="Content format strategies for this stage")
    topic_categories: List[TopicCategorySchema] = Field(description="Topic categories for this stage")

class DeepResearchContentStrategySchema(BaseModel):
    """Complete strategic intelligence report for competitive content advantage"""
    industry_best_practices: IndustryBestPracticesSchema = Field(description="Industry intelligence with context-specific insights")
    funnel_stage_analysis: List[FunnelStageAnalysisSchema] = Field(description="Analysis for all funnel stages")
    market_dynamics_intelligence: MarketDynamicsIntelligence = Field(description="Market evolution and changing competitive landscape")
    competitive_positioning_intelligence: CompetitivePositioningIntelligence = Field(description="Unique positioning opportunities and competitive advantages")
    ecosystem_orchestration_intelligence: EcosystemOrchestrationIntelligence = Field(description="Cross-channel content flow and discovery ecosystem orchestration")
    decision_intelligence: DecisionIntelligence = Field(description="Actionable intelligence for strategic decision-making")

# Export the schema for use in the workflow
GENERATION_SCHEMA_FOR_DEEP_RESEARCH_BLOG_CONTENT_STRATEGY = DeepResearchContentStrategySchema.model_json_schema()

# --- Prompt Templates ---

SYSTEM_PROMPT_TEMPLATE_FOR_DEEP_RESEARCH_BLOG_CONTENT_STRATEGY = """You are a strategic content intelligence analyst. Your mission is to identify the THREE BATTLES this company must win, the ONE POSITION they can own, and the FIVE MOVES to get there.

**COMPREHENSIVE DATA GATHERING MANDATE:**
For EVERY field in the schema, provide as much detailed, strategic intelligence as possible. Do not leave fields sparse or incomplete. Each section should be rich with insights, examples, and actionable intelligence.

**SOURCE ANALYSIS REQUIREMENT:**
Include detailed observations from all sources you analyze. For every insight, pattern, or recommendation, provide:
- Specific citations and references from the sources analyzed
- Direct quotes or data points that support your conclusions
- Links to relevant sources, studies, or examples when available
- Clear attribution of where each insight originated from your research

**STRATEGIC THINKING MANDATE:**
Start with market reality, not company analysis. Ask:
- What narrative battles are being fought in this market?
- Which positioning territories are contested vs. ownable?
- How is buyer behavior evolving and what does this create?
- What indirect threats could reshape competitive dynamics?
- Where are competitors vulnerable and how can this be exploited?

**MARKET DYNAMICS ANALYSIS:**
Focus on evolution, not static snapshots:
- How buyer behavior is CHANGING (not current patterns)
- Which strategies are LOSING effectiveness and why
- What narrative positions are GAINING/LOSING power
- How algorithm changes are RESHAPING discovery
- What cultural shifts are AFFECTING content consumption
- Where the market is HEADING, not where it's been

**COMPETITIVE POSITIONING INTELLIGENCE:**
Identify unique advantage opportunities:
- What narrative positions could this company OWN that competitors cannot match?
- Where are competitors vulnerable and how can this be exploited?
- How can this company reframe market conversations to favor their strengths?
- What differentiation moats can be built that competitors cannot replicate?
- Which competitive blind spots present positioning opportunities?

**ECOSYSTEM ORCHESTRATION STRATEGY:**
Map the full discovery ecosystem:
- How do buyers actually discover content across channels?
- Which channels originate narratives vs. validate them?
- How does content flow between Reddit, AI training, search, and social?
- What indirect influence channels shape buyer perceptions?
- How should content be orchestrated across the ecosystem for maximum impact?

**DECISION INTELLIGENCE OUTPUT:**
Provide actionable strategic intelligence:
- The THREE specific battles this company must win
- The ONE narrative position they should own
- The FIVE strategic moves to execute
- The KEY indicator that shows it's working
- The execution sequence for maximum impact

**INDUSTRY-ADAPTIVE FUNNEL ANALYSIS:**
First identify the industry-specific buyer journey stages relevant to this company:
- Standard B2B SaaS: Awareness → Consideration → Decision → Adoption → Expansion → Advocacy
- Enterprise Healthcare: Problem Recognition → Compliance Research → Vendor Evaluation → Pilot Program → Implementation → Scale → Advocacy
- Manufacturing/Industrial: Need Identification → Technical Validation → ROI Analysis → Proof of Concept → Procurement → Deployment → Optimization
- Financial Services: Awareness → Risk Assessment → Regulatory Review → Pilot Testing → Full Implementation → Performance Monitoring → Advocacy
- Identify the 4-7 stages most relevant to this company's specific industry and buyer context

**PROGRESSIVE DEEPENING APPROACH:**

**Phase 1: Pattern Identification**
Identify the most critical patterns in:
- Market dynamics and competitive positioning
- Content strategy effectiveness across industry-specific buyer stages
- Buyer behavior evolution within this industry context

**Phase 2: Deep Analysis of Critical Patterns**
For the TOP 3-5 patterns only, analyze:
- Core mechanism (why it works in this industry)
- Competitive advantage potential within industry dynamics
- Execution requirements specific to this buyer journey

**Phase 3: Strategic Synthesis**
Synthesize insights into:
- The THREE battles to win in this industry context
- The ONE position to own within industry dynamics
- The FIVE strategic moves adapted to industry buyer behavior
- Key success indicators relevant to this industry's sales cycles

**CONTEXT-SPECIFIC INTELLIGENCE:**
Avoid generic advice. Instead:
- "Buyers at evaluation stage trust peer reviews 3x more than vendor comparisons - here's how to leverage that asymmetry"
- "The client's competitor owns 'ease of use' because they show 60-second setup. You can't win on ease, but you can reframe to 'enterprise-powerful' where they're vulnerable"
- "Data-driven infographics work because they satisfy the buyer's need to justify decisions with 'objective' data, but only when the data addresses their specific fear of making the wrong choice"

**Output Format:**
```json
{schema}
```

Focus on strategic intelligence that drives competitive advantage, not generic best practices.

**COMPREHENSIVE FIELD POPULATION REQUIREMENT:**
Ensure EVERY field in the schema is thoroughly populated with detailed, strategic insights:
- Provide multiple examples and case studies where relevant
- Include specific percentages, metrics, and performance indicators
- Offer detailed rationales and mechanism explanations
- Supply comprehensive lists with strategic reasoning for each item
- Give rich context and market intelligence for all recommendations
- Ensure all nested objects and arrays contain substantial, actionable content"""

USER_PROMPT_TEMPLATE_FOR_DEEP_RESEARCH_BLOG_CONTENT_STRATEGY = """### Company Profile
- **Company Info**: {company_info}

## Strategic Intelligence Mission

Identify the THREE BATTLES this company must win, the ONE POSITION they can own, and the FIVE MOVES to execute. Focus on competitive advantage, not best practices.

**INDUSTRY-SPECIFIC BUYER JOURNEY MAPPING:**
First, identify the industry-specific buyer journey stages for this company:
- Analyze the company's industry context and typical buyer behavior patterns
- Map the 4-7 most relevant stages for this specific industry (not generic SaaS stages)
- Consider industry-specific requirements like compliance validation, pilot programs, technical validation, etc.
- Examples:
  * Enterprise Healthcare: Problem Recognition → Compliance Research → Vendor Evaluation → Pilot Program → Implementation → Scale → Advocacy
  * Manufacturing: Need Identification → Technical Validation → ROI Analysis → Proof of Concept → Procurement → Deployment → Optimization
  * Financial Services: Awareness → Risk Assessment → Regulatory Review → Pilot Testing → Implementation → Performance Monitoring → Advocacy

**MARKET REALITY ANALYSIS:**
Start with market dynamics, not company gaps:

1. **Narrative Battle Mapping**:
   - What narrative battles are being fought in the client's market?
   - Who's winning the key positioning battles in the industry?
   - Which positioning territories are contested vs. ownable?
   - Where are narrative opportunities that competitors are missing?

2. **Industry-Specific Buyer Behavior Evolution**:
   - How is buyer evaluation behavior CHANGING in the client's industry across their specific journey stages?
   - What new buyer fears or desires are emerging at each stage of their industry-specific funnel?
   - How are discovery patterns shifting across digital channels for this industry's buyer journey?
   - Which content consumption habits are GAINING/LOSING effectiveness within this industry context?

3. **Competitive Vulnerability Analysis**:
   - Where are the client's main competitors vulnerable that this company could exploit?
   - What narrative positions do key competitors own that can't be challenged?
   - Which competitive blind spots present positioning opportunities?
   - How could indirect competitors (major tech companies) disrupt current strategies?

**STRATEGIC POSITIONING INTELLIGENCE:**

1. **Ownable Position Identification**:
   - What unique narrative could this company own that competitors cannot match?
   - How can company strengths be amplified into competitive moats?
   - What market conversations can be reframed to favor this company?
   - Which differentiation strategies create barriers to competitive replication?

2. **Ecosystem Orchestration Strategy**:
   - How do buyers discover solutions in the client's industry across the full ecosystem?
   - Which channels originate trust vs. validate existing perceptions?
   - How does content flow from community discussions to buyer research?
   - What indirect influence channels (forums, communities) shape perceptions?

**DECISION INTELLIGENCE REQUIREMENTS:**

Extract and provide:
- **The 3 Battles**: Specific competitive battles this company must win
- **The 1 Position**: Single narrative position to own in the market  
- **The 5 Moves**: Strategic moves to execute the positioning
- **The Key Indicator**: Primary metric that shows strategy is working
- **Execution Sequence**: Order of moves for maximum impact

**CRITICAL PATTERN FOCUS:**
Identify and deeply analyze only the 3-5 most impactful patterns within this industry's buyer journey context:
- Core mechanisms that drive success across industry-specific funnel stages
- Competitive advantage potential within this industry's buying behavior patterns
- Key execution requirements for this industry's sales cycle complexity
- Strategic implications for positioning within industry-specific buyer journey stages

**CONTEXT-SPECIFIC INTELLIGENCE EXAMPLES:**
- Instead of "create comparison content" → "Buyers trust peer reviews 3x more than vendor comparisons at evaluation stage - here's how to systematically capture and amplify peer validation"
- Instead of "increase educational content" → "Educational content builds trust when it addresses the specific fear of making the wrong choice and looking incompetent to colleagues - focus on risk mitigation narratives"
- Instead of "post more frequently" → "Platform algorithms reward engagement velocity in first 90 minutes - here's how to orchestrate launch sequences for maximum reach"

Provide strategic intelligence that drives competitive differentiation, not generic optimization.

**COMPREHENSIVE RESEARCH REQUIREMENT:**
For each section of your analysis, provide exhaustive intelligence:
- **Industry Best Practices**: Include multiple successful content patterns with detailed evidence and source validation
- **Funnel Stage Analysis**: Provide comprehensive analysis for each industry-specific stage with detailed rationales, success patterns, and failure modes
- **Market Dynamics**: Offer extensive buyer behavior shifts, narrative battles, emerging threats, and market timing insights
- **Competitive Positioning**: Supply detailed competitor vulnerabilities, unique advantage amplification strategies, and differentiation moats
- **Ecosystem Orchestration**: Provide comprehensive discovery pathway analysis and cross-channel amplification strategies
- **Decision Intelligence**: Deliver detailed strategic moves, resource allocation strategies, and execution sequences

Ensure every field contains substantial, actionable intelligence with specific examples and strategic reasoning.
```"""



SYSTEM_PROMPT_TEMPLATE_FOR_LINKEDIN_RESEARCH = """
You are a senior social-media strategist and industry analyst with full web-browsing capabilities.

MISSION
• Produce a deep-research report that guides an executive's LinkedIn strategy.
• Output **MUST** be valid JSON that matches the "LinkedInResearchReport" Pydantic schema (see below).

**COMPREHENSIVE DATA GATHERING MANDATE:**
For EVERY field in the LinkedInResearchReport schema, provide extensive, detailed intelligence:
- Populate ALL peer analysis fields with comprehensive data and strategic insights
- Include multiple high-leverage tactics with detailed execution requirements
- Provide extensive industry trend analysis with business impact assessments
- Supply comprehensive narrative hooks with detailed proof points and credibility analysis
- Deliver thorough audience persona analysis with specific pain points and preferences
- Ensure topic mapping includes detailed sub-topics and data-driven examples

**SOURCE ANALYSIS REQUIREMENT:**
Include detailed observations from all sources you analyze. For every insight, pattern, or recommendation, provide:
- Specific citations and references from the sources analyzed
- Direct quotes or data points that support your conclusions
- Links to relevant sources, studies, or examples when available
- Clear attribution of where each insight originated from your research

KEY RULES
1. **Peer & category benchmark** – Select 5-10 comparator executives (same function + industry, similar company size/funding stage, preferably same region).  
2. **Freshness** – All performance metrics and trend references come from the last 90 days unless clearly noted otherwise.  
3. **Privacy** – Do NOT expose peer names, job titles, or personal bios. Use anonymous `peer_id` slugs.  
4. **Sources** – For any field that calls for a `source_id`, assign a unique integer (starting at 1 and incrementing globally). Do not include a reference list in the final JSON.  
5. **Completeness** – Populate every field; if data is genuinely unavailable, return an empty string `""` or empty list `[]`, but keep the field present.  
6. **Numbers** – Use plain numbers (no % symbols). Dates **MUST** be ISO (`YYYY-MM-DD`).  
7. **No extraneous keys** – Output must validate against the schema exactly; no additional properties or nesting levels.

SCHEMA (reference, not to be reproduced in the output)
{schema}

After analysis, respond with the single JSON object only—no prose, no markdown fence.
"""

USER_PROMPT_TEMPLATE_FOR_LINKEDIN_RESEARCH = """
Please execute the LinkedIn deep-research workflow using the instructions in the system prompt.

EXECUTIVE CONTEXT
LinkedIn user profile:
{linkedin_user_profile}

LinkedIn scraped profile:
{linkedin_scraped_profile}

DELIVERABLE
Return a fully populated **LinkedInResearchReport** JSON document that obeys the schema and rules provided in the system prompt.
"""

# ───────────────────────────────────────────────────────
# Re-usable “dict-like” helper models
# ───────────────────────────────────────────────────────



class RisingTerm(BaseModel):
    """Keyword or hashtag showing fast growth but low competition."""
    term: str = Field(description="Exact keyword or hashtag (without #).")
    growth_momentum_score: int = Field(description="Year-over-year search-volume growth momentum score out of 100.")

# ───────────────────────────────────────────────────────
# SECTION-1  PEER & CATEGORY BENCHMARK
# ───────────────────────────────────────────────────────

class Peer(BaseModel):
    """Benchmark datapoints for a single comparator executive."""
    name: str = Field(description="Name of the peer.")
    profile_url: str = Field(description="Direct link to the peer’s public LinkedIn profile.")
    headline: str = Field(description="Role and company as shown on LinkedIn (e.g. 'CRO @ FinTechCo').")
    avg_posts_per_month_90d: int = Field(description="Average number of posts per month in the last 90 days.")
    text_format_score: int = Field(description="Text-only posts frequency score out of 100.")
    carousel_format_score: int = Field(description="Multi-image carousel posts frequency score out of 100.")
    doc_format_score: int = Field(description="Document/PDF posts frequency score out of 100.")
    video_format_score: int = Field(description="Native video posts frequency score out of 100.")
    poll_format_score: int = Field(description="LinkedIn poll posts frequency score out of 100.")
    median_engagement: float = Field(description="Median engagements over the last 90 days.")
    signature_moves: List[str] = Field(description="Recurring content plays (e.g. 'Friday AMA').")
    content_pillars: List[str] = Field(description="Primary thematic buckets the peer posts about (max five).")

class HighLeverageTactic(BaseModel):
    """A repeatable text-based content tactic distilled from multiple peers with industry and user-specific strategic intelligence."""
    tactic: str = Field(description="Short name of the text-based content tactic specific to this user's industry and role (e.g. 'Industry-specific case study frameworks').")
    tactic_desciption: str = Field(description="Detailed description of the text-based tactic tailored to this user's specific industry context and professional goals.")
    why_it_works: str = Field(description="Core reason this text-based tactic is effective specifically for this user's industry and target audience")
    execution_requirements: str = Field(description="Key resources and skills needed for success, considering this user's specific industry constraints and capabilities")


# ───────────────────────────────────────────────────────
# SECTION-2  INDUSTRY TREND RESEARCH
# ───────────────────────────────────────────────────────

class TrendItem(BaseModel):
    """Industry and user-specific development with strategic intelligence focused on text-based content implications."""
    title: str = Field(description="Concise label for the industry-specific trend or development relevant to this user's sector.")
    summary: str = Field(description="One-sentence explanation with supporting numbers or facts specific to this user's industry context.")
    business_impact: str = Field(description="How this trend impacts business models and strategy specifically for this user's industry and role")
    opportunity: str = Field(description="Key opportunity this trend creates for text-based content strategy tailored to this user's specific goals and market")


# ───────────────────────────────────────────────────────
# SECTION-3  AUDIENCE & TOPIC INTELLIGENCE
# ───────────────────────────────────────────────────────
class Persona(BaseModel):
    """Snapshot of a priority audience segment for text-based content consumption."""
    role_titles: List[str] = Field(description="Representative job titles within this segment relevant to this user's industry and target market.")
    seniority: str = Field(description="Typical seniority band (e.g. 'C-level / VP') specific to this user's industry context.")
    urgent_pain_points: List[str] = Field(description="List of acute needs or frustrations experienced by the persona in this user's specific industry.")
    preferred_formats: List[str] = Field(description="Text-based content types this persona engages with most (articles, whitepapers, case studies, etc.).")
    tone_style: str = Field(description="Voice or style that resonates with the persona for text-based content in this user's industry context.")


# ───────────────────────────────────────────────────────
# ROOT MODEL
# ───────────────────────────────────────────────────────

class LinkedInResearchReport(BaseModel):
    peers: List[Peer] = Field(description="List of benchmark peers (ideally 5-10) - DO NOT include the user themselves in this list.")
    repeated_high_leverage_tactics: List[HighLeverageTactic] = Field(description="Rank-ordered list of the most effective text-based content tactics specific to this user's industry and role.")
    macro_trends: List[TrendItem] = Field(description="Broad market or regulatory shifts specific to this user's industry and professional context.")
    micro_trends: List[TrendItem] = Field(description="Niche product or technology developments relevant to this user's specific industry sector and role.")
    personas: List[Persona] = Field(description="Audience segments relevant to this user's specific industry and target market for text-based content.")


SCHEMA_TEMPLATE_FOR_LINKEDIN_RESEARCH = LinkedInResearchReport.model_json_schema()