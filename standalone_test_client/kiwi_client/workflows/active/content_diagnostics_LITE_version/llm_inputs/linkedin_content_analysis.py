from typing import List, Union, Dict, Any
# --- Pydantic Schemas for LLM Outputs (Examples) ---
from pydantic import BaseModel, Field

from enum import Enum
class JoinType(str, Enum):
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
# --- End Mock ---


class ThemeSchema(BaseModel):
    """Schema for a single extracted theme."""
    theme_id: str = Field(..., description="Unique identifier for the theme (e.g., 'theme_1', 'theme_2').")
    theme_name: str = Field(
        description="A clear, specific name for the identified theme (e.g., 'Founder Lessons')."
    )
    theme_description: str = Field(
        description="A structured, human-readable description with clear bullet points explaining: (1) the main topics covered, (2) the purpose or intent behind these posts, and (3) any recurring patterns or characteristics that define this theme."
    )

class ExtractedThemesOutput(BaseModel):
    themes: List[ThemeSchema] = Field(
        description="A list of 5 key content themes extracted from the user's LinkedIn posts."
    )


THEME_EXTRACTION_USER_PROMPT_TEMPLATE = """
<context>
You are analyzing LinkedIn posts from a single author to identify their core content themes. These themes will be used to classify all posts and generate strategic insights.
</context>

<task>
Analyze the provided LinkedIn posts and extract EXACTLY 5 distinct content themes that represent the author's recurring focus areas.
</task>

<requirements>
1. Each theme must be:
   - Mutually exclusive (minimal overlap with other themes)
   - Substantive enough to encompass multiple posts
   - Specific and actionable (not generic like "Business" or "Life")
   
2. Theme naming:
   - Use 2-3 word descriptive labels
   - Be specific to the content (e.g., "AI Implementation" not "Technology")
   - Make themes instantly recognizable
   
3. Theme descriptions must include:
   - Primary topics and subtopics covered
   - The strategic intent or purpose
   - Distinguishing characteristics and patterns
   - Typical post formats or structures used
</requirements>

<input_data>
Posts to analyze:
```json
{posts_json}
```
</input_data>

<output_instructions>
Return ONLY a valid JSON object matching the ExtractedThemesOutput schema.
Do not include any explanatory text outside the JSON.
</output_instructions>
"""

THEME_EXTRACTION_SYSTEM_PROMPT_TEMPLATE = """
<role>
You are an elite content strategist with expertise in:
- Social media content analysis and taxonomy
- LinkedIn platform dynamics and best practices
- Content categorization and pattern recognition
- Strategic content planning and optimization
</role>

<objective>
Extract exactly 5 distinct, high-value content themes from a corpus of LinkedIn posts that will enable strategic content analysis and optimization.
</objective>

<methodology>
Apply this systematic approach:

1. **Initial Scan**: Read all posts to understand the content landscape
2. **Pattern Detection**: Identify recurring topics, formats, and objectives
3. **Clustering**: Group similar posts based on:
   - Subject matter and expertise areas
   - Audience intent and value proposition
   - Content style and presentation format
   - Strategic business objectives
4. **Theme Extraction**: Distill clusters into 5 distinct themes
5. **Validation**: Ensure each theme is substantial, unique, and actionable
</methodology>

<theme_quality_criteria>
✓ **Distinctiveness**: Each theme should have <20% overlap with others
✓ **Coverage**: Together, themes should classify 80-90% of posts effectively
✓ **Actionability**: Themes must enable strategic decision-making
✓ **Specificity**: Avoid generic labels; be precise and contextual
✓ **Balance**: Ensure reasonable distribution (no theme >40% or <10% of posts)
</theme_quality_criteria>

<theme_description_structure>
For each theme, provide:
• **Core Topics** (3-5 bullet points): Specific subjects and areas covered
• **Strategic Intent**: Why the author creates this type of content
• **Content Patterns**: Recurring elements, formats, or approaches
• **Audience Value**: What readers gain from these posts
• **Distinguishing Features**: What makes this theme unique
</theme_description_structure>

<edge_cases>
- If posts are highly diverse, focus on the 5 most substantial patterns
- If posts are very similar, find nuanced distinctions (format, depth, audience)
- Reserve "Other" classification for truly outlier content in later steps
</edge_cases>

<output_format>
Respond with a JSON object conforming exactly to this schema:
```json
{schema}
```

No additional text or markdown formatting.
</output_format>
"""


class PostClassificationSchema(BaseModel):
    """Schema for classifying a single post."""
    post_id: str = Field(..., description="The unique identifier (URN) of the post being classified.")
    reasoning: str = Field(..., description="Brief explanation for why the theme was assigned.")
    assigned_theme_id: str = Field(..., description="The theme_id from the provided list that best fits this post. Must match one of the 5 extracted themes or be 'Other'.")

class BatchClassificationOutput(BaseModel):
    """Schema for the output of the batch classification LLM."""
    classifications: List[PostClassificationSchema] = Field(..., description="List of classifications for each post in the batch.")


POST_CLASSIFICATION_USER_PROMPT_TEMPLATE = """
<context>
You are classifying LinkedIn posts into predefined content themes for strategic analysis. Accurate classification is critical for generating actionable insights.
</context>

<task>
Classify each post in the batch to its most relevant theme based on content alignment, not just keyword matching.
</task>

<classification_rules>
1. Each post must be assigned to exactly ONE theme
2. Use "Other" ONLY when confidence for all themes is below 40%
3. Consider the full context of the post, not just keywords
4. Maintain consistency - similar posts must receive the same classification
5. Use the 'urn' field as the post_id for each classification
</classification_rules>

<available_themes>
```json
{themes_json}
```
</available_themes>

<posts_to_classify>
```json
{posts_batch_json}
```
</posts_to_classify>

<output_instructions>
Return ONLY a valid JSON object matching the BatchClassificationOutput schema.
Include all posts from the batch in your response.
</output_instructions>
"""

POST_CLASSIFICATION_SYSTEM_PROMPT_TEMPLATE = """
<role>
You are a precision content classification system specialized in LinkedIn content categorization with expertise in:
- Natural language understanding and semantic analysis
- Content pattern recognition
- Consistent taxonomy application
- Multi-criteria decision making
</role>

<objective>
Accurately classify each LinkedIn post into the most appropriate predefined theme to enable strategic content analysis.
</objective>

<classification_methodology>
For each post, apply this decision framework:

1. **Content Analysis** (40% weight):
   - Primary topic and subject matter
   - Key concepts and terminology used
   - Depth and breadth of coverage

2. **Intent Matching** (30% weight):
   - Alignment with theme's strategic purpose
   - Value proposition consistency
   - Audience targeting alignment

3. **Pattern Recognition** (20% weight):
   - Structural similarity to theme patterns
   - Stylistic and format alignment
   - Recurring elements or frameworks

4. **Context Consideration** (10% weight):
   - Post timing and sequencing
   - Explicit theme indicators
   - Cross-references to other content
</classification_methodology>

<confidence_scoring_guidelines>
- 90-100: Perfect theme match, all criteria strongly align
- 70-89: Good fit, most criteria align with minor exceptions
- 50-69: Moderate fit, mixed signals but lean toward this theme
- 30-49: Weak fit, some alignment but significant differences
- 0-29: Poor fit, consider "Other" classification

Assign "Other" when ALL themes score below 40% confidence.
</confidence_scoring_guidelines>

<reasoning_template>
Structure your reasoning as: "Primary match: [main alignment point]. Secondary indicators: [supporting evidence]. Confidence driver: [what drives the score]."
Keep reasoning concise (under 100 words).
</reasoning_template>

<consistency_requirements>
- Posts with similar content MUST receive the same classification
- Maintain classification patterns across the batch
- If uncertain between themes, choose based on strongest single indicator
- Document edge cases in reasoning
</consistency_requirements>

<critical_reminders>
⚠️ Use the exact 'urn' value from each post as the post_id
⚠️ Never create new theme_ids - use only provided themes or "Other"
⚠️ Include EVERY post from the batch in your output
⚠️ Maintain JSON validity - escape special characters properly
</critical_reminders>

<output_format>
Return a JSON object conforming exactly to this schema:
```json
{schema}
```

No additional text or formatting.
</output_format>
"""


# ---------- Sub-schemas ----------
class Citation(BaseModel):
    post_id: str = Field(..., description="Unique identifier of the source post")
    post_date: str = Field(..., description="Date of the cited post")
    excerpt: str = Field(..., description="Relevant excerpt from the post (max 200 chars)")

# ---------- Content Quality Metrics ----------

class ContentQualityMetrics(BaseModel):
    readability_score: float = Field(..., description="Flesch Reading Ease score or similar (0-100)")
    clarity_score: float = Field(..., description="Message clarity rating (0-100)")
    uniqueness_score: float = Field(..., description="Content originality score (0-100)")
    value_proposition_strength: float = Field(..., description="How clearly value is communicated (0-100)")
    quality_summary: str = Field(..., description="Overall content quality assessment")
    citations: List[Citation] = Field(..., description="Examples of high and low quality posts")

# ---------- Narrative and Storytelling ----------

class StorytellingMetrics(BaseModel):
    story_usage_pct: float = Field(..., description="Percentage of posts using storytelling")
    story_types: List[str] = Field(..., description="Types of stories used (personal, case study, analogy, etc.)")
    avg_story_engagement_lift: float = Field(..., description="Engagement boost from storytelling posts")
    best_story_example: Citation = Field(..., description="Most engaging story post")
    storytelling_summary: str = Field(..., description="Analysis of storytelling effectiveness")

# ---------- Call-to-Action Analysis ----------

class CTATypeDistribution(BaseModel):
    """OpenAI-compatible alternative to Dict[str, float] for CTA type distribution."""
    cta_type: str = Field(..., description="Type of CTA (comment, share, link, etc.)")
    percentage: float = Field(..., description="Percentage of posts using this CTA type")

class CTAMetrics(BaseModel):
    cta_usage_pct: float = Field(..., description="Percentage of posts with clear CTAs")
    cta_types: List[CTATypeDistribution] = Field(..., description="Distribution of CTA types as list of type-percentage pairs")
    avg_cta_conversion: float = Field(..., description="Average CTA response rate")
    most_effective_cta: str = Field(..., description="Highest performing CTA type")
    cta_examples: List[Citation] = Field(..., description="Examples of effective CTAs")
    cta_summary: str = Field(..., description="CTA strategy effectiveness analysis")

# ---------- Keywords and Topics ----------

class KeywordAnalysis(BaseModel):
    top_keywords: List[str] = Field(..., description="Most frequent keywords with frequency and engagement")
    trending_keywords: List[str] = Field(..., description="Keywords gaining traction recently")
    keyword_density: float = Field(..., description="Average keyword density percentage")
    keyword_performance: str = Field(..., description="Analysis of keyword impact on engagement")
    citations: List[Citation] = Field(..., description="Posts with effective keyword usage")

# ---------- Hashtag Analysis ----------

class HashtagMetrics(BaseModel):
    avg_hashtags_per_post: float
    hashtag_reach_impact: float = Field(..., description="Estimated reach increase from hashtags (%)")
    optimal_hashtag_count: int = Field(..., description="Number of hashtags for best engagement")
    hashtag_strategy: str = Field(..., description="Assessment of hashtag usage effectiveness")
    citations: List[Citation] = Field(..., description="Posts with effective hashtag strategies")

# ---------- Enhanced Format Metrics ----------

class FormatMetrics(BaseModel):
    format_type: str = Field(..., description="Content format (Text-only, Image, Document, Video, Carousel, Poll, etc.).")
    usage_pct: float = Field(..., description="Percentage of theme posts using this format (0 to 100).")
    avg_engagement: float = Field(..., description="Average engagement rate for posts in this format.")
    avg_reach: float = Field(..., description="Average reach for this format")
    format_trend: str = Field(..., description="Whether usage is increasing, stable, or decreasing")
    best_example: Citation = Field(..., description="Top performing post in this format")

class StructureAnalysisSchema(BaseModel):
    top_formats: List[FormatMetrics]
    avg_word_count: float = Field(..., description="Mean word count of posts in this theme.")
    avg_read_time_sec: float = Field(..., description="Estimated reading time in seconds.")
    bullet_point_usage: float = Field(..., description="Percentage of posts using bullet points")
    structure_summary: str = Field(..., description="Explanation of structural patterns and how they affect performance.")
    citations: List[Citation] = Field(..., description="Examples of effective structures")

# ---------- Enhanced Hook Analysis ----------

class HookMetrics(BaseModel):
    hook_type: str = Field(..., description="Opening device (e.g., Question, Bold Claim, Statistic, Story Snippet).")
    usage_pct: float = Field(..., description="Usage percentage (0 to 100)")
    avg_engagement: float
    avg_hook_length: int = Field(..., description="Average character count of hook")
    effectiveness_score: float = Field(..., description="Hook effectiveness rating (0-100)")

class HookAnalysisSchema(BaseModel):
    top_hooks: List[HookMetrics]
    best_hook_example: str = Field(..., description="Short example of the highest-performing hook in this theme.")
    worst_hook_example: str = Field(..., description="Example of ineffective hook for learning")
    hook_diversity_score: float = Field(..., description="Variety in hook usage (0-100)")
    hook_summary: str = Field(..., description="Why these hooks work and when to use them.")
    citations: List[Citation] = Field(..., description="Posts with notable hooks")

# ---------- Enhanced Engagement Performance ----------

class EngagementPerformanceSchema(BaseModel):
    avg_likes: float
    avg_comments: float
    avg_reposts: float
    avg_impressions: float = Field(..., description="Average post impressions")
    engagement_rate: float = Field(..., description="(likes + comments + reposts) ÷ followers, averaged across posts (0 to 100).")
    virality_score: float = Field(..., description="Measure of content spread beyond immediate network (0-100)")
    comment_sentiment: float = Field(..., description="Average sentiment of comments received (0-100)")
    top_post_engagement: float
    bottom_post_engagement: float
    engagement_variance: float = Field(..., description="Consistency of engagement across posts")
    performance_summary: str = Field(..., description="Key drivers of engagement and any anomalies to note.")
    top_performers: List[Citation] = Field(..., description="Highest engagement posts")
    low_performers: List[Citation] = Field(..., description="Lowest engagement posts for comparison")

# ---------- Audience Analysis ----------

class AudienceInsights(BaseModel):
    primary_audience_segments: List[str] = Field(..., description="Main audience categories engaging with content")
    evidence: List[Citation] = Field(..., description="Posts attracting target audience")

# ---------- Enhanced Timing and Cadence ----------

class TimingCadenceMetrics(BaseModel):
    posting_frequency_days: float = Field(..., description="Average number of days between posts in this theme.")
    peak_days: List[str] = Field(..., description="Weekdays that earn above-average engagement (e.g., ['Tuesday', 'Thursday']).")
    peak_hours: List[int] = Field(..., description="Hours of day with highest engagement (0-23)")
    engagement_lift_at_peaks: float = Field(..., description="Percentage lift in engagement during peak windows (0 to 100).")
    consistency_score: float = Field(..., description="How consistent the posting schedule is (0-100)")
    optimal_frequency: str = Field(..., description="Recommended posting frequency based on data")
    timing_summary: str = Field(..., description="Interpretation of cadence and timing insights.")


class RecentTopicSchema(BaseModel):
    date: str
    topic: str
    engagement_rate: float
    reach: int
    sentiment_score: float
    short_summary: str
    post_citation: Citation

# ---------- Actionable Recommendations ----------

class Recommendation(BaseModel):
    priority: str = Field(..., description="Priority level (High, Medium, Low)")
    category: str = Field(..., description="Category (Content, Timing, Format, Engagement, etc.)")
    recommendation: str = Field(..., description="Specific actionable recommendation")
    expected_impact: str = Field(..., description="Expected outcome if implemented")
    implementation_difficulty: str = Field(..., description="Ease of implementation (Easy, Medium, Hard)")
    supporting_data: List[Citation] = Field(..., description="Data supporting this recommendation")

# ---------- Main Theme-level Diagnostics ----------

class ContentThemeAnalysisSchema(BaseModel):
    """
    Comprehensive diagnostics for a single content theme after classifying and analyzing LinkedIn posts.
    Includes detailed metrics, citations, and actionable insights for content optimization.
    """
    # Core Theme Information
    theme_name: str
    theme_description: str
    total_posts_analyzed: int
    
    # Content Analysis Sections
    content_quality: ContentQualityMetrics
    structure_analysis: StructureAnalysisSchema
    hook_analysis: HookAnalysisSchema
    storytelling_analysis: StorytellingMetrics
    cta_analysis: CTAMetrics
    
    # Performance Metrics
    engagement_performance: EngagementPerformanceSchema
    audience_insights: AudienceInsights
    timing_cadence: TimingCadenceMetrics
    
    # Strategic Analysis
    recent_topics: List[RecentTopicSchema]
    
    # Actionable Insights
    key_findings: List[str] = Field(..., description="Top 5-7 most important findings")
    recommendations: List[Recommendation] = Field(..., description="Prioritized actionable recommendations")
    success_factors: List[str] = Field(..., description="What's working well that should continue")
    risk_factors: List[str] = Field(..., description="Potential issues to address")
    
    # Metadata
    confidence_score: float = Field(..., description="Overall confidence in analysis (0-100)")
    data_completeness: float = Field(..., description="Completeness of available data (0-100)")
    analysis_limitations: List[str] = Field(..., description="Any limitations or caveats in the analysis")


# ---------- Enhanced Prompt Templates ----------

THEME_ANALYSIS_USER_PROMPT_TEMPLATE = """
<context>
You are conducting a comprehensive performance analysis of LinkedIn posts grouped by content theme. This analysis will drive strategic content decisions and optimization efforts.
</context>

<theme_information>
Theme Name: {theme_name}
Theme ID: {theme_id}
Theme Description: {theme_description}
</theme_information>

<analysis_objectives>
1. Identify what drives engagement within this theme
2. Uncover content patterns that correlate with performance
3. Diagnose strengths and weaknesses in content execution
4. Generate data-driven recommendations for improvement
5. Benchmark against LinkedIn best practices
</analysis_objectives>

<required_analysis_dimensions>
Analyze these critical areas with supporting evidence:

1. **Content Quality Assessment**
   - Readability and accessibility
   - Value delivery and uniqueness
   - Message clarity and impact

2. **Structural Patterns**
   - Format effectiveness (text, media, documents)
   - Length optimization
   - Visual hierarchy and formatting

3. **Engagement Mechanics**
   - Hook effectiveness and types
   - Storytelling impact
   - CTA performance and conversion

4. **Discovery Optimization**
   - Keyword strategy and density
   - Hashtag effectiveness
   - Search visibility factors

5. **Performance Analytics**
   - Engagement rate patterns
   - Virality indicators
   - Audience quality metrics

6. **Timing Intelligence**
   - Optimal posting windows
   - Frequency impact
   - Consistency effects

7. **Asset ROI**
   - Media type performance
   - Production effort vs. return
   - Visual strategy effectiveness

8. **Competitive Position**
   - Performance benchmarks
   - Differentiation opportunities
   - Gap analysis
</required_analysis_dimensions>

<data_to_analyze>
Posts in this theme (under 'mapped_posts'):
```json
{theme_group_json}
```
</data_to_analyze>

<output_requirements>
1. Every metric must be calculated from actual post data
2. Every insight must include specific post citations
3. Recommendations must be prioritized and actionable
4. Include both successes to replicate and failures to avoid
5. Maintain objectivity - let data drive conclusions
</output_requirements>

<deliverable>
Return ONLY a valid JSON object matching the ContentThemeAnalysisSchema.
</deliverable>"""

THEME_ANALYSIS_SYSTEM_PROMPT_TEMPLATE = """
<role>
You are a world-class LinkedIn content strategist and data analyst with deep expertise in:
- Content performance optimization and A/B testing
- LinkedIn algorithm dynamics and platform best practices
- Engagement psychology and audience behavior analysis
- Data-driven decision making and statistical analysis
- Competitive intelligence and market positioning
- Content ROI measurement and attribution
</role>

<mission>
Deliver a comprehensive, actionable analysis of LinkedIn posts within a specific theme that enables data-driven content optimization and strategic decision-making.
</mission>

<analytical_framework>

## 1. Data Processing Pipeline
- **Extraction**: Parse all posts to extract metrics, text, timestamps, and metadata
- **Normalization**: Standardize metrics for fair comparison
- **Segmentation**: Group posts by performance tiers (top 20%, middle 60%, bottom 20%)
- **Pattern Recognition**: Identify correlations between content attributes and performance

## 2. Content Quality Analysis
Evaluate each post for:
- **Readability**: Flesch score, sentence complexity, paragraph structure
- **Clarity**: Main message identification, value proposition strength
- **Uniqueness**: Original insights vs. recycled content ratio
- **Authority**: Expertise demonstration, credibility markers

Score methodology: 
- Compare within theme and against LinkedIn benchmarks
- Weight recent posts higher for trend identification

## 3. Structural Analysis
Examine:
- **Format Distribution**: Track performance by format type
- **Length Optimization**: Correlate word count with engagement
- **Visual Elements**: Impact of images, videos, documents
- **Formatting**: Bullet points, emojis, white space usage

Key insight: Identify the "golden formula" for this theme

## 4. Hook Engineering
Analyze opening lines for:
- **Hook Types**: Question, statistic, story, controversy, etc.
- **Length Impact**: Character count vs. click-through
- **Emotional Triggers**: Which emotions drive engagement
- **Curiosity Gaps**: How well hooks create information gaps

Success metric: Engagement rate within first hour

## 5. Storytelling Assessment
Evaluate narrative elements:
- **Story Presence**: Percentage using narrative structure
- **Story Types**: Personal, client, industry, hypothetical
- **Engagement Lift**: Performance delta for story posts
- **Emotional Arc**: Beginning, conflict, resolution presence

## 6. CTA Optimization
Analyze calls-to-action:
- **Placement**: Beginning, middle, end effectiveness
- **Type**: Comment, share, click, follow, DM
- **Clarity**: Explicit vs. implicit CTAs
- **Conversion**: Response rate by CTA type

## 7. Discovery Mechanics
Evaluate findability:
- **Keywords**: Density, placement, trending terms
- **Hashtags**: Count, specificity, reach impact
- **LinkedIn SEO**: Profile optimization signals
- **Viral Mechanics**: Share-worthiness factors

## 8. Engagement Forensics
Deep dive into metrics:
- **Engagement Rate**: (Interactions / Impressions) × 100
- **Virality Coefficient**: Shares and ripple effects
- **Comment Quality**: Length, sentiment, conversation depth
- **Audience Retention**: Dwell time indicators

## 9. Timing Intelligence
Analyze temporal patterns:
- **Day Performance**: Weekday vs. weekend
- **Hour Optimization**: Peak engagement windows
- **Frequency Impact**: Posting cadence effects
- **Recency Bias**: How quickly posts decay

## 10. Asset ROI Analysis
Evaluate media usage:
- **Type Performance**: Images, videos, carousels, documents
- **Quality Impact**: Professional vs. casual assets
- **Effort-Return**: Production cost vs. engagement lift
- **Brand Consistency**: Visual identity maintenance

</analytical_framework>

<recommendation_framework>
Structure recommendations as:

**High Priority** (Implement within 1 week):
- Quick wins with high impact
- Critical issues blocking performance
- Easy optimizations with proven results

**Medium Priority** (Implement within 1 month):
- Strategic improvements requiring planning
- Testing opportunities for optimization
- Process enhancements

**Low Priority** (Consider for future):
- Nice-to-have improvements
- Experimental strategies
- Long-term positioning plays

Each recommendation must include:
1. Specific action to take
2. Expected impact (quantified if possible)
3. Implementation complexity
4. Success metrics to track
5. Supporting evidence from data
</recommendation_framework>

<quality_checks>
Before finalizing:
✓ Verify all metrics are calculated correctly
✓ Ensure every major claim has supporting citations
✓ Check that recommendations are specific and actionable
✓ Confirm analysis covers all required dimensions
✓ Validate JSON structure and data types
✓ Review for insights that contradict each other
✓ Ensure confidence scores reflect data quality
</quality_checks>

<citation_requirements>
- Include post_id, date, and relevant excerpt (max 200 chars)
- Cite both positive and negative examples for balance
- Ensure citations directly support the point being made
- Distribute citations across time range for representativeness
</citation_requirements>

<output_specifications>
Return a complete JSON object conforming to this schema:

Requirements:
- All numeric fields must be between 0-100 unless otherwise specified
- All lists must contain at least 1 item
- Strings must be concise but complete (aim for 50-200 words for summaries)
- Maintain professional tone while being specific and actionable
- No markdown formatting in string fields
</output_specifications>
"""

EXTRACTED_THEMES_SCHEMA = ExtractedThemesOutput.model_json_schema()

BATCH_CLASSIFICATION_SCHEMA = BatchClassificationOutput.model_json_schema()

THEME_ANALYSIS_REPORT_SCHEMA = ContentThemeAnalysisSchema.model_json_schema()

