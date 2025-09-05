"""
LLM Inputs for Competitor Content Analysis Workflow

This file contains prompts, schemas, and configurations for the workflow that:
- Analyzes competitor blog content and content strategy
- Assesses content metrics, themes, and positioning
- Evaluates SEO performance and AI visibility
- Identifies content gaps and competitive positioning
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, HttpUrl

# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

COMPETITOR_CONTENT_ANALYSIS_SYSTEM_PROMPT = """
You are an expert content strategist and competitive intelligence analyst tasked with conducting a comprehensive analysis of a competitor's blog content and content strategy.

Your role is to:
1. Analyze the competitor's blog/content section thoroughly
2. Assess their content production metrics and publishing patterns
3. Identify their main content themes, narrative, and positioning strategy
4. Evaluate their SEO performance and optimization approach
5. Assess their AI visibility and recognition across AI platforms
6. Identify content gaps and opportunities compared to the reference company
7. Analyze their competitive positioning and differentiation claims
8. Provide a quality assessment of their content depth and authority

You have access to Perplexity search tools to gather comprehensive, real-time data about the competitor's content strategy.

Focus on providing actionable insights that can inform content strategy decisions and identify opportunities for competitive advantage.

Be thorough in your analysis and provide specific, data-driven insights wherever possible.
"""

# =============================================================================
# USER PROMPT TEMPLATES
# =============================================================================

COMPETITOR_CONTENT_ANALYSIS_USER_PROMPT_TEMPLATE = """

site:{competitor_website}

Conduct a comprehensive competitive content analysis for the following company:

Competitor to Analyze:
- Competitor Name: {competitor_name}
- Competitor Website: {competitor_website}

Analysis Requirements:

1. CONTENT METRICS ANALYSIS:
   - Research their blog/content section thoroughly
   - Analyze posting frequency and content velocity over the past 3-6 months
   - Assess average word count and content length patterns
   - Identify content format mix (blogs, case studies, whitepapers, etc.)

2. CONTENT THEMES & STRATEGY:
   - Identify their primary brand narrative and positioning
   - Map out their main topic clusters and content pillars
   - Analyze their apparent content strategy approach
   - Identify unique angles or positioning they use

3. SEO PERFORMANCE ASSESSMENT:
   - Evaluate their blog's SEO health and optimization
   - Identify keywords they appear to target
   - Assess content optimization quality
   - Analyze technical SEO implementation

4. AI VISIBILITY ANALYSIS:
   - Research how often their content appears in AI platform responses
   - Assess their recognition level across AI tools (ChatGPT, Claude, Perplexity, etc.)
   - Evaluate citation rates and expert recognition
   - Identify categories where they dominate AI responses

5. CONTENT GAPS IDENTIFICATION:
   - Compare their content coverage to the reference company
   - Identify topics they cover that the reference company doesn't
   - Analyze content formats and engagement strategies they use
   - Assess their authority building approaches

6. COMPETITIVE POSITIONING:
   - Look for direct comparisons or mentions of the reference company
   - Identify how they differentiate from competitors
   - Analyze their positioning strategy and market narrative
   - Assess their competitive messaging approach

7. CONTENT QUALITY ASSESSMENT:
   - Evaluate content depth and expertise demonstration
   - Assess originality and thought leadership
   - Identify authority signals and credibility markers
   - Analyze engagement indicators and content performance

Use Perplexity search extensively to gather comprehensive, up-to-date information about the competitor's content strategy and performance.

Return your analysis in the exact JSON format specified in the schema.
"""

# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================
# PART 1: CONTENT STRATEGY & SALES FUNNEL SCHEMAS
from enum import Enum
from pydantic import BaseModel, Field
from typing import List

# COMPLETE CONTENT ANALYSIS SCHEMA - PORTFOLIO LEVEL
from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Dict

# Enums for content strategy
class SalesFunnelStage(str, Enum):
    AWARENESS = "awareness"
    CONSIDERATION = "consideration"
    PURCHASE = "purchase"
    RETENTION = "retention"

# -----------------------------------------------------------------------------
# Group-level schemas (referenced from blog_content_analysis.py)
# -----------------------------------------------------------------------------
class EEATAnalysisSchema(BaseModel):
    expertise_signals: List[str] = Field(description="Specific expertise signals identified across content")
    authority_indicators: List[str] = Field(description="Authority indicators present")
    trust_elements: List[str] = Field(description="Trust-building elements found")

class ContentQualityScoringSchema(BaseModel):
    information_density: int = Field(description="Information density score out of 100 (0-100)", ge=0, le=100)
    writing_quality: int = Field(description="Overall writing quality score out of 100 (0-100)", ge=0, le=100)

class QuestionAnswerExtractionSchema(BaseModel):
    featured_snippet_potential: List[str] = Field(description="Content sections with featured snippet potential")

class ContentStructureElementsSchema(BaseModel):
    storytelling_elements: List[str] = Field(description="Storytelling elements used (problem/solution/case study/data)")
    supporting_evidence_types: List[str] = Field(description="Types of supporting evidence (stats/quotes/examples/research)")

class LogicalFlowReadabilitySchema(BaseModel):
    paragraph_transitions: int = Field(description="Quality of paragraph transitions score out of 100 (0-100)", ge=0, le=100)
    heading_hierarchy: int = Field(description="Heading hierarchy organization score out of 100 (0-100)", ge=0, le=100)
    content_scanability: int = Field(description="How easily content can be scanned score out of 100 (0-100)", ge=0, le=100)

class ContentThemesSchema(BaseModel):
    primary_narratives: List[str] = Field(description="The main list of narratives or stories being told")
    topic_clusters: List[str] = Field(description="Key topic clusters identified")
    content_strategy: str = Field(description="Inferred content strategy approach")
    unique_angles: List[str] = Field(description="Unique angles or perspectives taken")

class FunnelStageGroupAnalysis(BaseModel):
    """Analysis for a single sales funnel stage (group-level)."""
    total_posts_analyzed: int = Field(description="Total number of posts analyzed in this stage")
    content_themes: ContentThemesSchema = Field(description="Content themes analysis for the stage")
    eeat_analysis: EEATAnalysisSchema = Field(description="E-E-A-T analysis for the stage")
    content_quality_scoring: ContentQualityScoringSchema = Field(description="Content quality scoring for the stage")
    question_answer_extraction: QuestionAnswerExtractionSchema = Field(description="QA/featured snippet potential")
    content_structure_elements: ContentStructureElementsSchema = Field(description="Content structure elements used")
    logical_flow_readability: LogicalFlowReadabilitySchema = Field(description="Logical flow and readability assessment")

class FunnelStagesPortfolioAnalysis(BaseModel):
    """Unified analysis across all four sales funnel stages in a single schema."""
    name: str = Field(description="Name of the competitor")
    awareness: FunnelStageGroupAnalysis = Field(description="Analysis for awareness stage")
    consideration: FunnelStageGroupAnalysis = Field(description="Analysis for consideration stage")
    purchase: FunnelStageGroupAnalysis = Field(description="Analysis for purchase stage")
    retention: FunnelStageGroupAnalysis = Field(description="Analysis for retention stage")

# Convert Pydantic models to JSON schemas for LLM use
COMPETITOR_CONTENT_ANALYSIS_OUTPUT_SCHEMA = FunnelStagesPortfolioAnalysis.model_json_schema() 