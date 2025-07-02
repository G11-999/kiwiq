ALL_DOCUMENT_SCHEMAS = """
# All document schemas

**Content Brief Schema:**

```python
class TargetAudienceSchema(BaseModel):
    '''Target audience information for brief'''
    primary: str = Field(description="Primary target audience")
    secondary: Optional[str] = Field(None, description="Secondary target audience")

class StructureOutlineSchema(BaseModel):
    '''Outline of post structure'''
    opening_hook: str = Field(description="Opening hook to grab attention")
    common_misconception: str = Field(description="Common misconception to address")
    core_perspective: str = Field(description="Core perspective to present")
    supporting_evidence: str = Field(description="Supporting evidence for perspective")
    practical_framework: str = Field(description="Practical framework or application")
    strategic_takeaway: str = Field(description="Strategic takeaway for reader")
    engagement_question: str = Field(description="Question to drive engagement")

class PostLengthSchema(BaseModel):
    '''Target post length range'''
    min: int = Field(description="Minimum length")
    max: int = Field(description="Maximum length")

class ContentBriefSchema(BaseModel):
    '''Detailed content brief based on selected concept (AI-generated)'''
    # uuid: str = Field(description="Unique identifier for the brief")
    title: str = Field(description="Brief title")
    scheduled_date: datetime = Field(description="Scheduled date for the post in datetime format UTC TZ", format="date-time")
    content_pillar: str = Field(description="Content pillar category")
    target_audience: TargetAudienceSchema = Field(description="Target audience information")
    core_perspective: str = Field(description="Core perspective for the post")
    post_objectives: List[str] = Field(description="Objectives of the post")
    key_messages: List[str] = Field(description="Key messages to convey")
    evidence_and_examples: List[str] = Field(description="Supporting evidence and examples")
    tone_and_style: str = Field(description="Tone and style guidelines")
    structure_outline: StructureOutlineSchema = Field(description="Outline of post structure")
    suggested_hook_options: List[str] = Field(description="Suggested hook options")
    call_to_action: str = Field(description="Call to action")
    hashtags: List[str] = Field(description="Suggested hashtags")
    post_length: PostLengthSchema = Field(description="Target post length range")
```

User preference:

```json
"data": {
        "created_at": "",
        "updated_at": "",
        "goals_answers": [
            {
                "question": "",
                "answer": ""
            }
        ],
        "user_preferences": {
            "audience": {
                "segments": [
                    {
                        "audience_type": "",
                        "description": ""
                    }
                ]
            },
            "posting_schedule": {
                "posts_per_week": 0,
                "posting_days": [
                    ""
                ],
                "exclude_weekends": False
            }
        },
        "timezone": {
            "iana_identifier": "",
            "display_name": "",
            "utc_offset": "",
            "supports_dst": False,
            "current_offset": ""
        }
    }
```

Post Concepts:

```json
class PostConceptSchema(BaseModel):
    concept_id: str = Field(description="Unique identifier for the concept")
    hook: str = Field(description="Attention-grabbing hook")
    message: str = Field(description="Main message of the concept")

class PostConceptListSchema(BaseModel):
    concepts: List[PostConceptSchema] = Field(description="List of post concepts")
```

post draft schema:

```json
class PostDraftSchema(BaseModel):
	  status: str
	  scheduled_date: str
		post_text: str = Field(description: "The main body of the LinkedIn post.")
    hashtags: List[str] = Field(description: "Suggested hashtags.")
```

content strategy schema:

```json
class StrategyAudienceSchema(BaseModel):
    '''Target audience segments for strategy'''
    primary: str = Field(description="Primary audience")
    secondary: Optional[str] = Field(description="Secondary audience")
    tertiary: Optional[str] = Field(description="Tertiary audience")

class FoundationElementsSchema(BaseModel):
    '''Foundational elements of the strategy'''
    expertise: List[str] = Field(description="Areas of expertise")
    core_beliefs: List[str] = Field(description="Core beliefs")
    objectives: List[str] = Field(description="Strategy objectives")

class PostPerformanceAnalysisSchema(BaseModel):
    '''Analysis of post performance'''
    current_engagement: str = Field(description="Current engagement levels")
    content_that_resonates: str = Field(description="Content types that resonate with audience")
    audience_response: str = Field(description="How audience responds to content")

class ContentPillarSchema(BaseModel):
    '''Content pillar definitions'''
    name: str = Field(description="Pillar name")
    pillar: str = Field(description="Pillar theme")
    sub_topic: List[str] = Field(description="Sub-topics within pillar")

class ThirtyDayTargetsSchema(BaseModel):
    '''30-day goals'''
    goal: str = Field(description="Overall goal for the 30 days")
    method: str = Field(description="Method to achieve the goal")
    targets: str = Field(description="Quantitative targets such as number of posts, number of likes, number of comments, number of shares, etc. based on the goal.")

class NinetyDayTargetsSchema(BaseModel):
    '''90-day goals'''
    goal: str = Field(description="Overall goal for the 90 days")
    method: str = Field(description="Method to achieve the goal")
    targets: str = Field(description="Quantitative targets such as number of posts, number of likes, number of comments, number of shares, etc. based on the goal.")

class ImplementationSchema(BaseModel):
    '''Implementation details'''
    thirty_day_targets: ThirtyDayTargetsSchema = Field(description="30-day goals")
    ninety_day_targets: NinetyDayTargetsSchema = Field(description="90-day goals")

class ContentStrategySchema(BaseModel):
    '''Content strategy document derived from user DNA (AI-generated)'''
    title: str = Field(description="Strategy title")
    target_audience: StrategyAudienceSchema = Field(description="Target audience segments")
    foundation_elements: FoundationElementsSchema = Field(description="Foundational elements of the strategy")
    core_perspectives: List[str] = Field(description="Core content perspectives")
    content_pillars: List[ContentPillarSchema] = Field(description="Content pillar definitions")
    post_performance_analysis: Optional[PostPerformanceAnalysisSchema] = Field(description="Analysis of current post performance", default=None)
    implementation: ImplementationSchema = Field(description="Implementation details")
```

User DNA schema:

```json
class ProfessionalIdentitySchema(BaseModel):
    '''Professional background and identity'''
    full_name: str = Field(description="User's full name")
    job_title: str = Field(description="Current job title")
    industry_sector: str = Field(description="Industry or business sector")
    company_name: str = Field(description="Current company name")
    company_size: str = Field(description="Size of current company")
    years_of_experience: int = Field(description="Years of professional experience")
    professional_certifications: List[str] = Field(description="Professional certifications held")
    areas_of_expertise: List[str] = Field(description="Areas of professional expertise")
    career_milestones: List[str] = Field(description="Significant career achievements")
    professional_bio: str = Field(description="Professional biography summary")

class LinkedInEngagementMetricsSchema(BaseModel):
    '''Engagement performance metrics'''
    average_likes_per_post: int = Field(description="Average likes per post")
    average_comments_per_post: int = Field(description="Average comments per post")
    average_shares_per_post: int = Field(description="Average shares per post")

class LinkedInProfileAnalysisSchema(BaseModel):
    '''Analysis of LinkedIn profile'''
    follower_count: int = Field(description="Number of LinkedIn followers")
    connection_count: int = Field(description="Number of LinkedIn connections")
    profile_headline_analysis: str = Field(description="Analysis of profile headline")
    about_section_summary: str = Field(description="Summary of 'About' section")
    engagement_metrics: LinkedInEngagementMetricsSchema = Field(description="Engagement performance metrics")
    top_performing_content_pillars: List[str] = Field(description="Best performing content categories")
    content_posting_frequency: str = Field(description="How often content is posted")
    content_types_used: List[str] = Field(description="Types of content posted")
    network_composition: List[str] = Field(description="Composition of LinkedIn network")

class BrandVoiceAndStyleSchema(BaseModel):
    '''Personal brand voice characteristics'''
    communication_style: str = Field(description="Overall communication style")
    tone_preferences: List[str] = Field(description="Preferred tones in communication")
    vocabulary_level: str = Field(description="Level of vocabulary used")
    sentence_structure_preferences: str = Field(description="Preferred sentence structures")
    content_format_preferences: List[str] = Field(description="Preferred content formats")
    emoji_usage: str = Field(description="How emojis are used")
    hashtag_usage: str = Field(description="How hashtags are used")
    storytelling_approach: str = Field(description="Approach to storytelling")

class ContentStrategyGoalsSchema(BaseModel):
    '''Content strategy goals and targets'''
    primary_goal: str = Field(description="Primary content goal")
    secondary_goals: List[str] = Field(description="Secondary content goals")
    target_audience_demographics: str = Field(description="Target audience demographics")
    ideal_reader_personas: List[str] = Field(description="Ideal reader descriptions")
    audience_pain_points: List[str] = Field(description="Pain points of target audience")
    value_proposition_to_audience: str = Field(description="Value proposition offered")
    call_to_action_preferences: List[str] = Field(description="Preferred calls to action")
    content_pillar_themes: List[str] = Field(description="Content pillar themes")
    topics_of_interest: List[str] = Field(description="Topics of interest to cover")
    topics_to_avoid: List[str] = Field(description="Topics to avoid covering")

class PersonalContextSchema(BaseModel):
    '''Personal background context'''
    personal_values: List[str] = Field(description="Personal values")
    professional_mission_statement: str = Field(description="Professional mission statement")
    content_creation_challenges: List[str] = Field(description="Challenges in content creation")
    personal_story_elements_for_content: List[str] = Field(description="Personal story elements to use")
    notable_life_experiences: List[str] = Field(description="Notable life experiences")
    inspirations_and_influences: List[str] = Field(description="Sources of inspiration")
    books_resources_they_reference: List[str] = Field(description="Books and resources referenced")
    quotes_they_resonate_with: List[str] = Field(description="Resonating quotes")

class AnalyticsInsightsSchema(BaseModel):
    '''Analytical insights about content'''
    optimal_content_length: str = Field(description="Optimal content length")
    audience_geographic_distribution: str = Field(description="Geographic distribution of audience")
    engagement_time_patterns: str = Field(description="Patterns in engagement timing")
    keyword_performance_analysis: str = Field(description="Performance of keywords")
    competitor_benchmarking: str = Field(description="Benchmark against competitors")
    growth_rate_metrics: str = Field(description="Growth rate metrics")

class SuccessMetricsSchema(BaseModel):
    '''Metrics to measure success'''
    content_performance_kpis: List[str] = Field(description="KPIs for content performance")
    engagement_quality_metrics: List[str] = Field(description="Metrics for engagement quality")
    conversion_goals: List[str] = Field(description="Conversion goals")
    brand_perception_goals: List[str] = Field(description="Brand perception goals")
    timeline_for_expected_results: str = Field(description="Timeline for expected results")
    benchmarking_standards: str = Field(description="Standards for benchmarking")

class UserDNA(BaseModel):
    '''Comprehensive user DNA profile derived from all inputs (AI-generated)'''
    professional_identity: ProfessionalIdentitySchema = Field(description="Professional background and identity")
    linkedin_profile_analysis: LinkedInProfileAnalysisSchema = Field(description="Analysis of LinkedIn profile")
    brand_voice_and_style: BrandVoiceAndStyleSchema = Field(description="Personal brand voice characteristics")
    content_strategy_goals: ContentStrategyGoalsSchema = Field(description="Content strategy goals and targets")
    personal_context: PersonalContextSchema = Field(description="Personal background context")
    analytics_insights: AnalyticsInsightsSchema = Field(description="Analytical insights about content")
    success_metrics: SuccessMetricsSchema = Field(description="Metrics to measure success")
```

Idea schema:

```json
class PostIdeaSchema(BaseModel):
    '''Content idea schema for a single LinkedIn post idea.'''
    idea_id: str = Field(description="Unique identifier for the idea")
    hook: str = Field(description="Attention-grabbing hook")
    message: str = Field(description="Main message of the idea")

class PostIdeaListSchema(BaseModel):
    '''List of post ideas generated by the LLM.'''
    ideas: List[PostIdeaSchema] = Field(description="List of post ideas")
```

Source Page analysis schema:

```json
class ProfessionalIdentitySchema(BaseModel):
    '''Professional background and identity'''
    full_name: str = Field(description="User's full name")
    job_title: str = Field(description="Current job title")
    industry_sector: str = Field(description="Industry or business sector")
    company_name: str = Field(description="Current company name")
    company_size: str = Field(description="Size of current company")
    years_of_experience: int = Field(description="Years of professional experience")
    professional_certifications: List[str] = Field(description="Professional certifications held")
    areas_of_expertise: List[str] = Field(description="Areas of professional expertise")
    career_milestones: List[str] = Field(description="Significant career achievements")
    professional_bio: str = Field(description="Professional biography summary")

class LinkedInEngagementMetricsSchema(BaseModel):
    '''Engagement performance metrics'''
    average_likes_per_post: int = Field(description="Average likes per post")
    average_comments_per_post: int = Field(description="Average comments per post")
    average_shares_per_post: int = Field(description="Average shares per post")

class LinkedInProfileAnalysisSchema(BaseModel):
    '''Analysis of LinkedIn profile'''
    follower_count: int = Field(description="Number of LinkedIn followers")
    connection_count: int = Field(description="Number of LinkedIn connections")
    profile_headline_analysis: str = Field(description="Analysis of profile headline")
    about_section_summary: str = Field(description="Summary of 'About' section")
    engagement_metrics: LinkedInEngagementMetricsSchema = Field(description="Engagement performance metrics")
    top_performing_content_pillars: List[str] = Field(description="Best performing content categories")
    content_posting_frequency: str = Field(description="How often content is posted")
    content_types_used: List[str] = Field(description="Types of content posted")
    network_composition: List[str] = Field(description="Composition of LinkedIn network")

class BrandVoiceAndStyleSchema(BaseModel):
    '''Personal brand voice characteristics'''
    communication_style: str = Field(description="Overall communication style")
    tone_preferences: List[str] = Field(description="Preferred tones in communication")
    vocabulary_level: str = Field(description="Level of vocabulary used")
    sentence_structure_preferences: str = Field(description="Preferred sentence structures")
    content_format_preferences: List[str] = Field(description="Preferred content formats")
    emoji_usage: str = Field(description="How emojis are used")
    hashtag_usage: str = Field(description="How hashtags are used")
    storytelling_approach: str = Field(description="Approach to storytelling")

class ContentStrategyGoalsSchema(BaseModel):
    '''Content strategy goals and targets'''
    primary_goal: str = Field(description="Primary content goal")
    secondary_goals: List[str] = Field(description="Secondary content goals")
    target_audience_demographics: str = Field(description="Target audience demographics")
    ideal_reader_personas: List[str] = Field(description="Ideal reader descriptions")
    audience_pain_points: List[str] = Field(description="Pain points of target audience")
    value_proposition_to_audience: str = Field(description="Value proposition offered")
    call_to_action_preferences: List[str] = Field(description="Preferred calls to action")
    content_pillar_themes: List[str] = Field(description="Content pillar themes")
    topics_of_interest: List[str] = Field(description="Topics of interest to cover")
    topics_to_avoid: List[str] = Field(description="Topics to avoid covering")

class PersonalContextSchema(BaseModel):
    '''Personal background context'''
    personal_values: List[str] = Field(description="Personal values")
    professional_mission_statement: str = Field(description="Professional mission statement")
    content_creation_challenges: List[str] = Field(description="Challenges in content creation")
    personal_story_elements_for_content: List[str] = Field(description="Personal story elements to use")
    notable_life_experiences: List[str] = Field(description="Notable life experiences")
    inspirations_and_influences: List[str] = Field(description="Sources of inspiration")
    books_resources_they_reference: List[str] = Field(description="Books and resources referenced")
    quotes_they_resonate_with: List[str] = Field(description="Resonating quotes")

class AnalyticsInsightsSchema(BaseModel):
    '''Analytical insights about content'''
    optimal_content_length: str = Field(description="Optimal content length")
    audience_geographic_distribution: str = Field(description="Geographic distribution of audience")
    engagement_time_patterns: str = Field(description="Patterns in engagement timing")
    keyword_performance_analysis: str = Field(description="Performance of keywords")
    competitor_benchmarking: str = Field(description="Benchmark against competitors")
    growth_rate_metrics: str = Field(description="Growth rate metrics")

class SuccessMetricsSchema(BaseModel):
    '''Metrics to measure success'''
    content_performance_kpis: List[str] = Field(description="KPIs for content performance")
    engagement_quality_metrics: List[str] = Field(description="Metrics for engagement quality")
    conversion_goals: List[str] = Field(description="Conversion goals")
    brand_perception_goals: List[str] = Field(description="Brand perception goals")
    timeline_for_expected_results: str = Field(description="Timeline for expected results")
    benchmarking_standards: str = Field(description="Standards for benchmarking")

class UserUnderstandingSchema(BaseModel):
    '''Comprehensive user DNA profile derived from all inputs (AI-generated)'''
    professional_identity: ProfessionalIdentitySchema = Field(description="Professional background and identity")
    linkedin_profile_analysis: LinkedInProfileAnalysisSchema = Field(description="Analysis of LinkedIn profile")
    brand_voice_and_style: BrandVoiceAndStyleSchema = Field(description="Personal brand voice characteristics")
    content_strategy_goals: ContentStrategyGoalsSchema = Field(description="Content strategy goals and targets")
    personal_context: PersonalContextSchema = Field(description="Personal background context")
    analytics_insights: AnalyticsInsightsSchema = Field(description="Analytical insights about content")
    success_metrics: SuccessMetricsSchema = Field(description="Metrics to measure success")

class StrategyAudienceSchema(BaseModel):
    '''Target audience segments for strategy'''
    primary: str = Field(description="Primary audience")
    secondary: str = Field(description="Secondary audience")
    tertiary: str = Field(description="Tertiary audience")

class FoundationElementsSchema(BaseModel):
    '''Foundational elements of the strategy'''
    expertise: List[str] = Field(description="Areas of expertise")
    core_beliefs: List[str] = Field(description="Core beliefs")
    objectives: List[str] = Field(description="Strategy objectives")

class PostPerformanceAnalysisSchema(BaseModel):
    '''Analysis of post performance'''
    current_engagement: str = Field(description="Current engagement levels")
    content_that_resonates: str = Field(description="Content types that resonate with audience")
    highest_performing_formats: str = Field(description="Best performing content formats")
    audience_response: str = Field(description="How audience responds to content")

class OverviewSchema(BaseModel):
    '''Strategy overview'''
    post_performance_analysis: PostPerformanceAnalysisSchema = Field(description="Analysis of post performance")

class ContentPillarSchema(BaseModel):
    '''Content pillar definitions'''
    name: str = Field(description="Pillar name")
    theme: str = Field(description="Pillar theme")
    sub_themes: List[str] = Field(description="Sub-themes within pillar")

class HighImpactFormatSchema(BaseModel):
    '''High impact content formats'''
    name: str = Field(description="Format name")
    steps: List[str] = Field(description="Steps to create this format")
    example: str = Field(description="Example of the format")

class ImplementationSchema(BaseModel):
    '''Implementation details'''
    weekly_content_calendar: str = Field(description="Weekly content schedule")
    thirty_day_targets: str = Field(description="30-day goals")
    ninety_day_targets: str = Field(description="90-day goals")

class ContentStrategySchema(BaseModel):
    '''Content strategy document derived from user DNA (AI-generated)'''
    title: str = Field(description="Strategy title")
    navigation_menu: List[str] = Field(description="Navigation menu items")
    foundation_elements: FoundationElementsSchema = Field(description="Foundational elements of the strategy")
    overview: OverviewSchema = Field(description="Strategy overview")
    core_perspectives: List[str] = Field(description="Core content perspectives")
    content_pillars: List[ContentPillarSchema] = Field(description="Content pillar definitions")
    high_impact_formats: List[HighImpactFormatSchema] = Field(description="High impact content formats")
    implementation: ImplementationSchema = Field(description="Implementation details")

class ExtractionSchema(BaseModel):
		content_strategy: Optional[ContentStrategySchema]
		user_understanding: Optional[UserUnderstandingSchema]

```

Content Analysis schema:

```python
class ToneAnalysisSchema(BaseModel):
    dominant_tones: List[str] = Field(description="List of the most prominent tones observed in the posts.")
    tone_distribution: Dict[str, str] = Field(description="Distribution of tones with corresponding percentages.")
    tone_description: str = Field(description="Narrative description explaining the tonal characteristics and how to replicate them.")

class PostFormatSchema(BaseModel):
    primary_format: str = Field(description="The dominant post format used (e.g., Numbered Lists, Bullet Points).")
    metrics: Dict[str, Union[str, float]] = Field(description="Relevant format-related metrics like average word count.")
    example: str = Field(description="Example of a post matching this format.")

class ConcisenessSchema(BaseModel):
    level: str = Field(description="Conciseness classification (e.g., Concise, Highly Concise).")
    metrics: Dict[str, Union[str, float]] = Field(description="Numeric data about sentence or paragraph length.")
    description: str = Field(description="Detailed analysis of how concise the writing is.")

class DataIntensitySchema(BaseModel):
    level: str = Field(description="Level of data usage in posts (e.g., Low, Moderate, High).")
    metrics: Dict[str, Union[str, float]] = Field(description="Counts of numeric/statistical references and jargon.")
    example: str = Field(description="Example text showing how data or metrics are used.")

class StructureAnalysisSchema(BaseModel):
    post_format: PostFormatSchema
    conciseness: ConcisenessSchema
    data_intensity: DataIntensitySchema
    common_structures: Dict[str, str] = Field(description="Frequencies of commonly observed structures.")
    structure_description: str = Field(description="Narrative explanation of content structure patterns and how to replicate them.")

class HookTypeSchema(BaseModel):
    type: str = Field(description="Type of hook used in the opening (e.g., Bold Claim, Question).")
    metrics: Dict[str, Union[str, float]] = Field(description="Quantitative metrics related to the hook.")

class EngagementBreakdownSchema(BaseModel):
    average_likes: float
    average_comments: float
    average_reposts: float

class HookAnalysisSchema(BaseModel):
    hook_type: HookTypeSchema
    hook_text: str = Field(description="Example hook used.")
    engagement_correlation: Dict[str, EngagementBreakdownSchema] = Field(description="Engagement data correlated with different hook types.")
    hook_description: str = Field(description="Description of how hook types affect engagement and how to replicate.")

class UniqueTermSchema(BaseModel):
    frequency: int
    example: str

class EmojiUsageSchema(BaseModel):
    category: str = Field(description="Emoji frequency category (e.g., Frequently, Sometimes).")
    metrics: Dict[str, float] = Field(description="Average number of emojis per post.")

class LinguisticStyleSchema(BaseModel):
    unique_terms: Dict[str, UniqueTermSchema] = Field(description="Specialized or repetitive terms with frequencies and examples.")
    emoji_usage: EmojiUsageSchema
    linguistic_description: str = Field(description="Analysis of language patterns, vocabulary, and style.")

class RecentTopicSchema(BaseModel):
    date: str = Field(description="Date of the post.")
    summary: str = Field(description="Summary of the post topic.")
    engagement: EngagementBreakdownSchema

class ContentThemeAnalysisSchema(BaseModel):
    theme: str = Field(description="Name of the theme.")
    theme_description: str = Field(description="Narrative description of what this theme encompasses.")
    tone_analysis: ToneAnalysisSchema
    structure_analysis: StructureAnalysisSchema
    hook_analysis: HookAnalysisSchema
    linguistic_style: LinguisticStyleSchema
    recent_topics: Dict[str, RecentTopicSchema] = Field(description="Key recent posts and their engagement metrics.")

class FullThemeAnalysisListSchema(BaseModel):
    records: List[Dict[str, ContentThemeAnalysisSchema]] = Field(
        description="List of detailed content theme analyses for a user."
    )
```

updated content analysis workflow (not yet implemented):

```json
class ToneAnalysisSchema(BaseModel):
    '''Analysis of the overall tone and emotional characteristics in user's posts'''
    dominant_tones: List[str] = Field(
        description="List of the most prominent tones observed across all posts (e.g., Professional, Casual, Enthusiastic, Analytical). Identify the top 3-5 most frequent tones."
    )
    tone_description: str = Field(
        description="Comprehensive narrative description explaining the tonal characteristics, emotional range, and specific guidance on how to replicate the user's tone in new content."
    )

class ConcisenessSchema(BaseModel):
    '''Analysis of how concise or verbose the user's writing style is'''
    level: str = Field(
        description="Conciseness classification based on sentence length and information density (e.g., Highly Concise, Moderately Concise, Verbose, Highly Verbose)."
    )
    description: str = Field(
        description="Detailed analysis of the user's conciseness patterns, including average sentence length, paragraph structure, and how they balance brevity with completeness."
    )

class StructureAnalysisSchema(BaseModel):
    '''Analysis of how the user structures and organizes their content'''
    conciseness: ConcisenessSchema
    data_intensity: str = Field(
        description="Level of data, statistics, and technical information usage in posts (e.g., Low - minimal data usage, Moderate - occasional metrics, High - frequent statistics and numbers)."
    )
    structure_description: str = Field(
        description="Comprehensive narrative explanation of content organization patterns, including how posts are structured, flow between ideas, use of headers/lists, and actionable guidance for replicating these structural patterns."
    )

class EmojiMetricsSchema(BaseModel):
    '''Metrics for specific emoji usage patterns'''
    average_frequency: float = Field(description="Average number of times this emoji appears per post")
    emoji: str = Field(description="The specific emoji character being analyzed")

class EmojiUsageSchema(BaseModel):
    '''Analysis of emoji usage patterns and frequency'''
    category: str = Field(
        description="Overall emoji usage frequency category (e.g., Frequently - multiple emojis per post, Sometimes - occasional emoji use, Rarely - minimal emoji usage, Never - no emoji usage)."
    )
    metrics: List[EmojiMetricsSchema] = Field(
        description="Detailed breakdown of specific emojis used most frequently, including their average frequency per post."
    )
    
class EngagementBreakdownSchema(BaseModel):
    average_likes: float
    average_comments: float
    average_reposts: float

class RecentTopicSchema(BaseModel):
    '''Information about recent topics and themes discussed by the user'''
    topic: str = Field(description="The main topic or theme of the post (e.g., Product Launch, Industry Trends, Personal Insights)")
    date: str = Field(description="Date when the post was published (YYYY-MM-DD format)")
    summary: str = Field(description="Brief summary of the post content and key points discussed")
    engagement: EngagementBreakdownSchema

class WritingStyleFingerprint(BaseModel):
    '''Condensed writing style profile for content generation - extract the most frequent patterns and characteristics'''
    signature_phrases: List[str] = Field(
        description="Extract the most frequently used phrases, expressions, and verbal patterns that are unique to this user. Focus on recurring language patterns that appear multiple times across posts."
    )
    sentence_structure_patterns: List[str] = Field(
        description="Identify the most common sentence construction patterns (e.g., 'I believe that...', 'The key is...', 'What I've learned is...'). Extract recurring grammatical structures and sentence beginnings."
    )
    transition_words: List[str] = Field(
        description="Most frequently used transition words and phrases for connecting ideas (e.g., 'However', 'Additionally', 'That said', 'Here's the thing'). Focus on the user's preferred connectors."
    )
    opening_patterns: List[str] = Field(
        description="Extract the most common patterns for how the user typically starts their posts (e.g., questions, bold statements, personal anecdotes, statistics). Identify recurring opening formulas."
    )
    closing_patterns: List[str] = Field(
        description="Identify the most frequent patterns for how the user ends their posts (e.g., call-to-action, question to audience, summary statement, personal reflection). Focus on recurring conclusion styles."
    )
    frequent_adjectives: List[str] = Field(
        description="Extract the most frequently used adjectives that characterize the user's descriptive language and emotional expression. Focus on adjectives that appear multiple times across posts."
    )
    linguistic_description: str = Field(
        description="Comprehensive analysis of language patterns, vocabulary preferences, stylistic choices, and overall linguistic fingerprint. Include guidance on replicating the user's unique voice and communication style."
    )

class ContentThemeAnalysisSchema(BaseModel):
    '''Complete analysis of a user's content theme including tone, structure, and writing style'''
    theme_id: str = Field(description="Unique identifier for the theme being analyzed (e.g., 'professional_insights', 'personal_branding')")
    theme_name: str = Field(description="Descriptive name of the theme being analyzed (e.g., 'Professional Insights', 'Personal Branding Content')")
    theme_description: str = Field(
        description="Comprehensive narrative description of what this theme encompasses, including the types of content, target audience, and overall purpose of posts in this theme."
    )
    tone_analysis: ToneAnalysisSchema = Field(description="Analysis of tonal characteristics and emotional patterns in the theme")
    structure_analysis: StructureAnalysisSchema = Field(description="Analysis of content organization and structural patterns")
    emoji_usage: EmojiUsageSchema = Field(description="Analysis of emoji usage patterns and frequency")
    recent_topics: List[RecentTopicSchema] = Field(
        description="List of recent topics and posts within this theme, providing context for current content focus and engagement patterns."
    )
    writing_style_fingerprint: WritingStyleFingerprint = Field(
        description="Condensed writing style profile containing the most frequent patterns and characteristics needed for accurate content generation in this user's voice."
    )

```

core beliefs and perspective:

```json
{
  "beliefs": [
    {
      "question": "",
      "answer_belief": ""
    }
  ]
}
```

content pillars:

```json
class ContentPillar(BaseModel):
    pillar: str = Field(description="Name of the pillar.")
    pillar_description: str = Field(description="Narrative description of what this pillar encompasses.")
    
class ContentPillarListSchema(BaseModel):
    pillars: List[ContentPillar] = Field(
        description="A list of content pillars"
    )
```

content pillar json:

```json
{
  "pillars": [
    {
      "pillar": "",
      "pillar_description": ""
    }
  ]
}
```
"""
