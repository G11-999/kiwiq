"""
LLM inputs for blog content analysis workflow including schemas and prompt templates.
"""

from enum import Enum
from typing import List, Any, Optional
from pydantic import BaseModel, Field

# --- Enums for Classification ---

class SalesFunnelStage(str, Enum):
    AWARENESS = "awareness"
    CONSIDERATION = "consideration"
    PURCHASE = "purchase"
    RETENTION = "retention"

# --- Classification Schemas ---

class PostClassificationSchema(BaseModel):
    post_url: str = Field(description="The URL of the blog post")
    sales_funnel_stage: SalesFunnelStage = Field(description="The sales funnel stage this post belongs to")

class PostClassificationBatchSchema(BaseModel):
    batch_id: str = Field(description="Batch ID")
    posts: List[PostClassificationSchema] = Field(description="List of posts")
    reasoning: str = Field(description="Reasoning process for classification")

# Modified E-E-A-T Analysis for Group Level (strategic insights only)
class EEATAnalysisSchema(BaseModel):
    expertise_signals: List[str] = Field(description="Specific expertise signals identified across content")
    authority_indicators: List[str] = Field(description="Authority indicators present")
    trust_elements: List[str] = Field(description="Trust-building elements found")

class ContentQualityScoringSchema(BaseModel):
    information_density: str = Field(description="Information density assessment (sparse/moderate/dense)")
    writing_quality: str = Field(description="Overall writing quality assessment")

class EntityRecognitionSchema(BaseModel):
    knowledge_graph_entities: List[str] = Field(description="Entities suitable for knowledge graphs")

class QuestionAnswerExtractionSchema(BaseModel):
    featured_snippet_potential: List[str] = Field(description="Content sections with featured snippet potential")

class ContentStructureElementsSchema(BaseModel):
    storytelling_elements: List[str] = Field(description="Storytelling elements used (problem/solution/case study/data)")
    supporting_evidence_types: List[str] = Field(description="Types of supporting evidence (stats/quotes/examples/research)")

class LogicalFlowReadabilitySchema(BaseModel):
    paragraph_transitions: str = Field(description="Quality of paragraph transitions (poor/good/excellent)")
    heading_hierarchy: str = Field(description="Heading hierarchy organization (poor/good/excellent)")
    content_scanability: str = Field(description="How easily content can be scanned (low/medium/high)")

class ContentThemesSchema(BaseModel):
    primary_narratives: List[str] = Field(description="The main list of narratives or stories being told")
    topic_clusters: List[str] = Field(description="Key topic clusters identified")
    content_strategy: str = Field(description="Inferred content strategy approach")
    unique_angles: List[str] = Field(description="Unique angles or perspectives taken")

class ContentAnalysisSchema(BaseModel):
    funnel_stage: str = Field(description="The sales funnel stage being analyzed")
    total_posts_analyzed: int = Field(description="Total number of posts analyzed in this group")
    content_themes: ContentThemesSchema = Field(description="Content themes analysis")
    eeat_analysis: EEATAnalysisSchema = Field(description="E-E-A-T (Expertise, Experience, Authority, Trust) analysis")
    content_quality_scoring: ContentQualityScoringSchema = Field(description="Content quality scoring")
    question_answer_extraction: QuestionAnswerExtractionSchema = Field(description="Question-Answer extraction for AEO/voice search")
    content_structure_elements: ContentStructureElementsSchema = Field(description="Content structure elements analysis")
    logical_flow_readability: LogicalFlowReadabilitySchema = Field(description="Logical flow and readability analysis")

    
# --- Schema Definitions for LLM ---

# Convert schemas to JSON for LLM consumption
BATCH_CLASSIFICATION_SCHEMA = PostClassificationBatchSchema.model_json_schema()
FUNNEL_STAGE_ANALYSIS_SCHEMA = ContentAnalysisSchema.model_json_schema()

# --- Prompt Templates ---

POST_CLASSIFICATION_SYSTEM_PROMPT_TEMPLATE = """You are an expert content analyst specializing in sales funnel classification. Your task is to analyze blog posts and return structured outputs that strictly conform to the provided JSON schema.

## Field Guidance (align with schema exactly):
- sales_funnel_stage: Choose one of the stages above.
- primary_topic: One concise phrase capturing the main topic.
- secondary_topics: Up to 5 concise related topics.

- readability_score, clarity_score, logical_flow_score, depth_score, originality_score: Float scores on a 0-100 scale.

- expertise_score, experience_score, authoritativeness_score, trustworthiness_score: Float scores on a 0-100 scale.

- has_table_of_contents, has_faq_section, has_author_bio, has_citations, has_code_examples, has_data_visualizations: Boolean flags based on presence in the post.

- content_pattern: One of [how-to, listicle, guide, comparison, opinion, case-study, news, tutorial].
- reading_level: One of [elementary, intermediate, advanced].

- questions_addressed: Up to 3 key questions answered by the post (concise phrasing).

- people_mentioned, products_mentioned, companies_mentioned: Up to 3 items each; use canonical names.

## Output Format:
Return output that matches this JSON schema exactly:

Instructions:
1. Analyze each post using title, content, and context.
2. Use exact field names and data types from the schema.
3. Populate every field; do not add any extra fields.
4. Keep strings concise but specific; scores must be 0-100 floats.
5. Output only JSON that conforms to the schema (no prose)."""

POST_CLASSIFICATION_USER_PROMPT_TEMPLATE = """Please analyze and classify the following batch of blog posts:

{posts_batch_json}

For each post, produce a JSON object with these fields (exact names and types):
- post_url
- sales_funnel_stage
- primary_topic
- secondary_topics (≤ 5)
- readability_score, clarity_score, logical_flow_score, depth_score, originality_score (0-100 floats)
- expertise_score, experience_score, authoritativeness_score, trustworthiness_score (0-100 floats)
- has_table_of_contents, has_faq_section (booleans)

Ensure the final output strictly matches the provided schema and includes one object per post in the batch."""

FUNNEL_STAGE_ANALYSIS_SYSTEM_PROMPT_TEMPLATE = """You are an expert content strategist and analyst specializing in content intelligence. Your task is to analyze a group of blog posts for a specific sales funnel stage and return structured insights that strictly conform to the provided JSON schema.

## Analyze the group across these dimensions (mapped to schema fields):

### 1. Content Themes (content_themes)
- primary_narratives: Key narratives that repeatedly appear.
- topic_clusters: Core topics and their clusters.
- content_strategy: Concise description of the inferred strategy for this stage.
- unique_angles: Distinctive angles or perspectives observed.

### 2. E-E-A-T Analysis (eeat_analysis)
- expertise_signals: Concrete indicators of expertise.
- authority_indicators: Citations, recognitions, or authority markers.
- trust_elements: Transparency, accuracy, references, or other trust signals.

### 3. Content Quality Scoring (content_quality_scoring)
- information_density: One of [sparse, moderate, dense].
- writing_quality: Brief qualitative assessment of overall writing quality.

### 4. Question-Answer Extraction (question_answer_extraction)
- featured_snippet_potential: Questions/answers or sections likely to win featured snippets.

### 5. Content Structure Elements (content_structure_elements)
- storytelling_elements: Problem/solution, case study, data, etc.
- supporting_evidence_types: Stats, quotes, examples, research, etc.

### 6. Logical Flow & Readability (logical_flow_readability)
- storytelling_elements: Problem/solution, case study, data, etc.
- supporting_evidence_types: Stats, quotes, examples, research, etc.

### 7. Logical Flow & Readability (logical_flow_readability)
- paragraph_transitions: One of [poor, good, excellent].
- heading_hierarchy: One of [poor, good, excellent].
- content_scanability: One of [low, medium, high].

## Output Format:
Return output that matches this JSON schema exactly

## Instructions:
1. Consider all posts in the group; cite titles or short snippets only when necessary to ground findings.
2. Use exact field names and data types from the schema; populate all fields.
3. Provide multiple items for list fields when applicable.
4. Do not invent fields; return only JSON that conforms to the schema (no prose)."""

FUNNEL_STAGE_ANALYSIS_USER_PROMPT_TEMPLATE = """Please perform a content intelligence analysis of the following {funnel_stage} stage content group:

{posts_group_json}

Produce a single JSON object that strictly follows the schema and includes:
- funnel_stage: "{funnel_stage}"
- total_posts_analyzed: Integer count of posts provided
- content_themes: primary_narratives, topic_clusters, content_strategy, unique_angles
- eeat_analysis: expertise_signals, authority_indicators, trust_elements
- content_quality_scoring: information_density (sparse/moderate/dense), writing_quality
- question_answer_extraction: featured_snippet_potential
- content_structure_elements: storytelling_elements, supporting_evidence_types
- logical_flow_readability: paragraph_transitions (poor/good/excellent), heading_hierarchy (poor/good/excellent), content_scanability (low/medium/high)

Return only JSON adhering to the provided schema."""

# --- New: Final Portfolio Analysis Schemas and Prompts ---

class ContentQualityMetrics(BaseModel):
    average_readability: float = Field(description="Average readability score across all posts")
    average_clarity: float = Field(description="Average clarity score across all posts")
    average_depth: float = Field(description="Average content depth score")
    average_originality: float = Field(description="Average originality score")
    overall_eeat_score: float = Field(description="Combined E-E-A-T score average")
    content_structure_adoption: float = Field(description="% of posts with good structure Table of Content/Frequently Asked Questions")

class TopicAuthorityInsight(BaseModel):
    topic_name: str = Field(description="Topic name")
    total_posts: int = Field(description="Posts covering this topic")
    funnel_coverage: List[str] = Field(description="Funnel stages covered for this topic")
    authority_level: str = Field(description="Topic authority assessment (Expert/Strong/Developing/Weak)")
    coverage_gaps: List[str] = Field(description="Missing funnel stages or content types")

class FunnelStageInsight(BaseModel):
    stage_name: str = Field(description="Sales funnel stage")
    post_count: int = Field(description="Number of posts in this stage")
    avg_quality_score: float = Field(description="Average quality score for this stage")

class FinalContentAnalysisReport(BaseModel):
    executive_summary: str = Field(description="3-4 sentence strategic overview of content portfolio health and opportunities")
    content_portfolio_health: ContentQualityMetrics = Field(description="Overall content quality metrics")
    topic_authority_analysis: List[TopicAuthorityInsight] = Field(description="Topic authority insights for top 5-8 topics", max_items=8)
    funnel_stage_insights: List[FunnelStageInsight] = Field(description="Analysis by sales funnel stage", max_items=4)
    strategic_recommendations: List[str] = Field(description="Top 4-5 actionable strategic recommendations", max_items=5)
    content_gaps_priority: List[str] = Field(description="Top 3-4 priority content gaps to address", max_items=4)

FINAL_ANALYSIS_SCHEMA = FinalContentAnalysisReport.model_json_schema()

FINAL_ANALYSIS_SYSTEM_PROMPT = """You are a senior content strategist analyzing a complete blog content portfolio. Your role is to synthesize individual post data into strategic insights and actionable recommendations.

## Analysis Process:

### 1. Content Portfolio Health Assessment
- Calculate average scores across quality dimensions (readability, clarity, depth, originality, E-E-A-T)
- Identify overall content quality trends and patterns
- Assess structural content adoption (TOC, FAQ usage rates)

### 2. Topic Authority Analysis
- Group posts by primary_topic and analyze coverage depth
- For each major topic (3+ posts), evaluate:
  * Funnel stage coverage (awareness → retention)
  * Content depth and quality consistency
  * Authority level based on comprehensiveness
- Identify topics with strong authority vs. those needing development
- Flag topics covered in only 1-2 funnel stages (authority gaps)

### 3. Funnel Stage Analysis
- Analyze content distribution across sales funnel stages
- Compare quality scores between funnel stages
- Identify over/under-invested stages
- Map topic coverage gaps within each stage

### 4. Strategic Gap Identification
- Find topics with high post count but poor funnel coverage
- Identify high-quality topics that could be expanded
- Spot funnel stages lacking authoritative content
- Detect content format gaps (structural elements)

## Output Guidelines:
- Executive summary should highlight 1-2 key strengths and 1-2 critical gaps
- Focus on actionable insights over descriptive statistics
- Prioritize recommendations by potential impact
- Keep topic authority analysis to most significant topics (5-8 max)
- Base authority levels on both quantity and funnel stage coverage

## Authority Level Criteria:
- **Expert**: 8+ posts across 3-4 funnel stages with high quality scores
- **Strong**: 5-7 posts across 2-3 funnel stages with good quality
- **Developing**: 3-4 posts with limited funnel coverage
- **Weak**: 1-2 posts or single funnel stage coverage

Return only JSON that strictly conforms to the provided schema
"""

FINAL_ANALYSIS_USER_PROMPT = """Analyze the following blog content portfolio data and generate a strategic content analysis report.

The input is a list of per-post records with fields including: post_url, primary_topic, sales_funnel_stage, readability_score, clarity_score, logical_flow_score, depth_score, originality_score, expertise_score, experience_score, authoritativeness_score, trustworthiness_score, has_table_of_contents, has_faq_section.

## Portfolio Data (Batch):

## Individual Post Analysis Results (JSON list):
{post_analysis_data}

Provide your analysis in the structured JSON format specified by the schema."""

FINAL_SYNTHESIS_USER_PROMPT = """You will receive multiple batch-level portfolio analysis reports that already follow the final report schema. Consolidate them into a single final report.

Guidelines:
- Concatenate and deduplicate topic authority insights (limit to 5-8 most significant topics)
- Average numeric metrics across batches correctly (weighted by counts where applicable)
- Merge funnel stage insights (sum counts, recompute averages)
- Recompute content_structure_adoption as a single portfolio percentage

Input:
- Batch Reports (JSON list of FinalContentAnalysisReport objects):
{batch_reports_json}

Output:
- A single FinalContentAnalysisReport JSON object strictly matching the schema.""" 