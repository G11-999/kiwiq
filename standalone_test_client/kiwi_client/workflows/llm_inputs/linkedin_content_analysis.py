from typing import List, Union
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
Here is a set of LinkedIn posts written by a single user.

Your task is to analyze these posts and return exactly 5 key content themes. Each theme must have a name and a detailed description.

Posts:
```json
{posts_json}
```

Respond ONLY with the JSON object matching the specified schema.
"""

THEME_EXTRACTION_SYSTEM_PROMPT_TEMPLATE = """
You are an expert content strategist specializing in social media analysis.

Your task is to analyze a series of LinkedIn posts and identify exactly 5 key content themes that represent the user's recurring focus areas. Each theme should be unique, clearly named, and reflect distinct patterns in tone, topic, or objective across the posts.

Guidelines:
- Identify **exactly 5 themes**, no more or less
- Each theme must have a **concise, specific name** (e.g., "Startup Lessons", not "Business")
- For each theme, write a **structured, human-readable description** using clear bullet points that cover: (1) main topics, (2) purpose or intent, and (3) recurring patterns or characteristics
- Do not infer the user's goals — base your themes only on the text content provided
- Be as concrete and precise as possible; avoid vague or generic labels

Respond only with the JSON output conforming to the schema: ```json\n{schema}\n```
"""


class PostClassificationSchema(BaseModel):
    """Schema for classifying a single post."""
    post_id: str = Field(..., description="The unique identifier (URN) of the post being classified.")
    reasoning: str = Field(..., description="Brief explanation for why the theme was assigned.")
    assigned_theme_id: str = Field(..., description="The theme_id from the provided list that best fits this post. Must match one of the 5 extracted themes or be 'Other'.")
    confidence_score: float = Field(..., description="Confidence score (0.0 to 1.0) for the theme assignment.")

class BatchClassificationOutput(BaseModel):
    """Schema for the output of the batch classification LLM."""
    classifications: List[PostClassificationSchema] = Field(..., description="List of classifications for each post in the batch.")


POST_CLASSIFICATION_USER_PROMPT_TEMPLATE = """
You are given a list of LinkedIn posts and 5 predefined themes.

Assign each post to its most relevant theme. If no theme fits well, label it as "Other".

[THEMES]
```json
{themes_json}
```

Posts Batch (use 'urn' as the ID for classification):
```json
{posts_batch_json}
```
"""

POST_CLASSIFICATION_SYSTEM_PROMPT_TEMPLATE = """
You are a classification model trained in content categorization and social media tagging.

Your task is to classify each LinkedIn post into the **most relevant theme** from a predefined list of 5 themes. Each post must belong to one — and only one — theme. If none of the themes are a good match, assign it to "Other".

Guidelines:
- Use the theme descriptions provided to make accurate assignments
- Do not make up new themes
- Preserve all original post data (e.g., post text, ID)
- Include the name of the matched theme alongside the original post ID
- Be consistent in your classifications: similar posts should be grouped under the same theme
- For each post, provide its ID -- Don't generate it, use the post URN from the 'urn' field from the input post data, its a number and will be the post_id, the assigned theme ID or "Other", a confidence score (0.0-1.0), and a brief reasoning.

Follow the instructions precisely and respond only with the JSON output conforming to the schema: ```json\n{schema}\n```
"""
# assign theme Other if not a good fit to any themes!
# - Assign a theme to a post even if confidence is low, but reflect it in the score.




class SentimentSchema(BaseModel):
    label: str = Field(description="Overall sentiment classification (e.g., Positive, Neutral, Negative).")
    average_score: float = Field(description="Average sentiment score across posts.")

class ToneSchema(BaseModel):
    tone: str = Field(description="The tone of the post.")
    percentage: float = Field(description="The percentage of posts that are of this tone.")


class ToneAnalysisSchema(BaseModel):
    dominant_tones: List[str] = Field(description="List of the most prominent tones observed in the posts.")
    sentiment: SentimentSchema = Field(description="Aggregated sentiment label and score.")
    tone_distribution: List[ToneSchema] = Field(description="Distribution of tones with corresponding percentages.")
    tone_description: str = Field(description="Narrative description explaining the tonal characteristics and how to replicate them.")

class MetricSchema(BaseModel):
    """Schema for representing a single metric with name and value."""
    metric_name: str = Field(description="Name of the metric being measured.")
    metric_value: Union[str, float] = Field(description="Value of the metric, can be numeric or descriptive.")

class PostFormatSchema(BaseModel):
    primary_format: str = Field(description="The dominant post format used (e.g., Numbered Lists, Bullet Points).")
    metrics: List[MetricSchema] = Field(description="Relevant format-related metrics like average word count.")
    example: str = Field(description="Example of a post matching this format.")

class ConcisenessSchema(BaseModel):
    level: str = Field(description="Conciseness classification (e.g., Concise, Highly Concise).")
    metrics: List[MetricSchema] = Field(description="Numeric data about sentence or paragraph length.")
    description: str = Field(description="Detailed analysis of how concise the writing is.")

class DataIntensitySchema(BaseModel):
    level: str = Field(description="Level of data usage in posts (e.g., Low, Moderate, High).")
    metrics: List[MetricSchema] = Field(description="Counts of numeric/statistical references and jargon.")
    example: str = Field(description="Example text showing how data or metrics are used.")

class CommonStructureSchema(BaseModel):
    structure: str = Field(description="The structure of the post.")
    frequency: str = Field(description="The frequency of the structure in the posts.")

class StructureAnalysisSchema(BaseModel):
    post_format: PostFormatSchema
    conciseness: ConcisenessSchema
    data_intensity: DataIntensitySchema
    common_structures: List[CommonStructureSchema] = Field(description="Frequencies of commonly observed structures.")
    structure_description: str = Field(description="Narrative explanation of content structure patterns and how to replicate them.")

class HookTypeSchema(BaseModel):
    type: str = Field(description="Type of hook used in the opening (e.g., Bold Claim, Question).")
    metrics: List[MetricSchema] = Field(description="Quantitative metrics related to the hook.")

class EngagementBreakdownSchema(BaseModel):
    average_likes: float
    average_comments: float
    average_reposts: float

class HookAnalysisSchema(BaseModel):
    hook_type: HookTypeSchema
    hook_text: str = Field(description="Example hook used.")
    engagement_correlation: List[EngagementBreakdownSchema] = Field(description="Engagement data correlated with different hook types.")
    hook_description: str = Field(description="Description of how hook types affect engagement and how to replicate.")

class UniqueTermSchema(BaseModel):
    term: str = Field(description="The unique term being analyzed.")
    frequency: int
    example: str

class EmojiMetricsSchema(BaseModel):
    average_frequency: float
    emoji: str

class EmojiUsageSchema(BaseModel):
    category: str = Field(description="Emoji frequency category (e.g., Frequently, Sometimes).")
    metrics: List[EmojiMetricsSchema] = Field(description="Average number of emojis per post.")

class LinguisticStyleSchema(BaseModel):
    unique_terms: List[UniqueTermSchema] = Field(description="Specialized or repetitive terms with frequencies and examples.")
    emoji_usage: EmojiUsageSchema
    linguistic_description: str = Field(description="Analysis of language patterns, vocabulary, and style.")

class RecentTopicSchema(BaseModel):
    topic: str = Field(description="The topic of the post.")
    date: str = Field(description="Date of the post.")
    summary: str = Field(description="Summary of the post topic.")
    engagement: EngagementBreakdownSchema

class ContentThemeAnalysisSchema(BaseModel):
    theme_id: str = Field(..., description="The ID of the theme being analyzed.")
    theme_name: str = Field(..., description="The name of the theme being analyzed.")
    theme_description: str = Field(description="Narrative description of what this theme encompasses.")
    tone_analysis: ToneAnalysisSchema
    structure_analysis: StructureAnalysisSchema
    hook_analysis: HookAnalysisSchema
    linguistic_style: LinguisticStyleSchema
    recent_topics: List[RecentTopicSchema] = Field(description="Key recent posts and their engagement metrics.")


THEME_ANALYSIS_USER_PROMPT_TEMPLATE = """
Analyze the following set of LinkedIn posts, all belonging to the same theme.

The group focuses on the theme '{theme_name}' ({theme_id}).
Theme Description: {theme_description}

Identify writing patterns, tone, structure, and engagement insights. Return your analysis and actionable suggestions.

[Posts] in this theme group (under 'mapped_posts'):
```json
{theme_group_json}
```
"""

THEME_ANALYSIS_SYSTEM_PROMPT_TEMPLATE = """
You are a social media content analyst with expertise in tone, structure, writing style, and audience engagement patterns.

You are analyzing a set of LinkedIn posts grouped by a specific theme. Your job is to identify how the user writes within this theme and extract actionable insights.

For the given theme:
- Analyze **tone** (dominant tones, emotional expression, sentiment trends)
- Evaluate **structure** (common formats, conciseness, length patterns)
- Examine **hooks** (opening lines, question usage, statistics, storytelling)
- Describe **linguistic style** (formality, use of emojis, jargon, formatting)
- Identify **frequent topics**
- Comment on **engagement trends** (what post types get more interaction)
- End with **3–5 recommendations** to improve performance or consistency within this theme

Be clear, concrete, and specific. Use examples where useful, but don't repeat full post texts. Your goal is to make the insights easy to apply.

Respond only with the JSON output conforming to the schema: ```json\n{schema}\n```
"""

EXTRACTED_THEMES_SCHEMA = ExtractedThemesOutput.model_json_schema()

BATCH_CLASSIFICATION_SCHEMA = BatchClassificationOutput.model_json_schema()

THEME_ANALYSIS_REPORT_SCHEMA = ContentThemeAnalysisSchema.model_json_schema()

