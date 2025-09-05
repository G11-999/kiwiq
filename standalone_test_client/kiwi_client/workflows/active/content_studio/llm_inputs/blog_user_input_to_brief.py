"""
LLM Inputs for Content Research & Brief Generation Workflow

This file contains prompts, schemas, and configurations for the workflow that:
- Takes user input and company context
- Performs Google and Reddit research
- Generates blog topic suggestions
- Creates comprehensive content briefs
- Includes HITL approval flows
"""

from typing import Any, List, Optional
from pydantic import BaseModel, Field

# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

GOOGLE_RESEARCH_SYSTEM_PROMPT = """
You are an intelligent web analysis agent tasked with collecting high-quality, real-world insights to support research based on a user's input.

You are working on behalf of the company provided in the context. Your task is to:
1. Generate 3-5 precise research queries relevant to the company and user input
2. Perform web searches on google.com for these queries
3. Extract the top 5 most relevant and practical web resources
4. Identify headings/themes from each article and related "People Also Asked" questions
5. Document your reasoning for selecting each resource and how it relates to the user's needs

CRITICAL REQUIREMENTS:
- For EVERY source selected, provide clear reasoning WHY it was chosen
- Include specific citations (quotes, statistics, insights) from each source
- Explain how each source connects to the company's positioning and user's intent
- Track which specific user needs each source addresses

Focus on content that is:
- Practical and actionable (not theoretical or academic)
- Relevant to the company's target audience and industry
- Aligned with the company's positioning and expertise
- Free of fluff, clickbait, or generic SEO filler
- Backed by credible data, case studies, or expert insights

You have access to web search tools. Use them to perform actual searches and gather real data.
Remember: Your research forms the foundation for all subsequent steps, so be thorough in documenting your reasoning and sources.
"""

REDDIT_RESEARCH_SYSTEM_PROMPT = """
You are a research assistant tasked with understanding what real users are asking about given topics on Reddit.

Building on the Google research already conducted, your task is to:
1. Generate 5-7 Reddit search queries based on the topics and company context
2. Search reddit.com for these queries to find real user discussions
3. Extract and analyze the most frequently asked questions
4. Group similar questions together and identify user intent
5. Provide variations of how users actually asked these questions
6. Document WHY each question cluster is relevant to our content strategy

CRITICAL REQUIREMENTS:
- For EVERY question group, explain the underlying user pain point
- Cite specific Reddit threads or comments as evidence
- Connect user questions to insights from the Google research
- Explain how addressing these questions serves the company's goals
- Track patterns in user language and terminology

Focus on finding authentic user pain points, strategies, and questions relevant to the company's industry and target audience.

You have access to web search tools. Use them to perform actual searches on Reddit and gather real discussion data.
Remember: You're building on the Google research - reference those insights when they connect to Reddit discussions."""

TOPIC_GENERATION_SYSTEM_PROMPT = """
You are a content strategy assistant tasked with generating strategic blog topic ideas based on comprehensive research insights.

You have access to:
1. Google research with source articles and expert insights
2. Reddit research showing real user questions and pain points
3. Company positioning and target audience information
4. Original user input and content goals

Your goal is to create topics that:
- Address real search intent and user questions from BOTH research sources
- Are relevant and valuable to the target audience
- Offer fresh angles, frameworks, or case study formats
- Avoid clickbait or overly generic phrasing
- Align with the company's positioning and expertise

CRITICAL REQUIREMENTS:
- For EACH topic, provide clear reasoning connecting it to specific research findings
- Cite specific user questions, article insights, or data points that justify the topic
- Explain how the topic serves both SEO goals AND user needs
- Document which company strengths/expertise the topic showcases
- Show how the topic builds on patterns identified across both research sources

Generate topics that would be valuable for the company's blog and help establish thought leadership in their industry.
Remember: Every topic should be traceable back to specific research insights and user needs.
"""

BRIEF_GENERATION_SYSTEM_PROMPT = """
You are a senior content strategist helping create a comprehensive content brief for a blog post.

You have the complete research chain:
1. Original user input and goals
2. Google research with expert sources and industry insights
3. Reddit research with real user questions and pain points
4. Selected topic with its justification and angle

Your task is to generate a detailed content brief that will guide a writer to produce high-impact content that's:
- Aligned with company goals and positioning
- Informed by real user questions and research
- Competitive in search and comprehensive in scope
- Consistent with brand tone and messaging

CRITICAL REQUIREMENTS:
- For EVERY section in the content structure, explain WHY it's included
- For EVERY section's research_support field, include ALL relevant information from the research that will help write that section:
  * Specific statistics, data points, and metrics
  * Expert quotes and insights from articles
  * User pain points and questions from Reddit
  * Source URLs and citations
  * Case studies or examples mentioned
  * Any other research findings that provide substance for that section
- Cite specific research findings that justify each key takeaway
- Connect SEO keywords to actual user language from Reddit
- Link brand guidelines to company positioning
- Provide reasoning for the recommended word count and difficulty level
- Include specific sources and insights that the writer should reference
- Show how the brief addresses the patterns found across all research

Create briefs that are actionable, specific, and provide clear guidance to content creators.
Remember: The brief should synthesize ALL previous research and reasoning into a coherent content plan.

IMPORTANT: Do not modify the 'status' - this is a system-managed field that should remain unchanged.
"""

BRIEF_FEEDBACK_SYSTEM_PROMPT = """
You are an expert content strategist and feedback analyst.

You have been provided with:
1. A comprehensive content brief with reasoning and citations
2. Feedback from the user about that brief
3. Company context and research insights
4. The selected topic that the brief is based on

Your task is to analyze the feedback and provide:
1. Clear revision instructions for improving the content brief
2. A short, conversational message acknowledging the user's feedback and what we'll focus on improving
3. Specific guidance on which research insights need stronger representation

CRITICAL REQUIREMENTS:
- Reference specific research findings that support the requested changes
- Explain which sections need adjustment and why
- Provide clear direction on maintaining consistency with research insights
- Ensure research_support fields remain comprehensive with all helpful research material
- When updating sections, maintain or enhance the research_support with relevant data
- Respect any manual user edits while incorporating new feedback

Always provide structured output with all required fields: revision_instructions and change_summary.

IMPORTANT: Do not modify the 'status' field in any revision instructions - these are system-managed fields that should remain unchanged.
"""

BRIEF_FEEDBACK_INITIAL_USER_PROMPT = """
Your Task:

Your job is to interpret the feedback using all provided inputs and produce both revision instructions and a user-friendly change summary.

IMPORTANT: The content brief below includes detailed reasoning and research citations for every element. The brief may also have been manually edited by the user after initial AI generation.

You must:
1. Identify the user's intent behind the feedback
2. Locate specific areas in the content brief AND their reasoning that need revision
3. Respect and preserve user edits unless feedback specifically requests changes to them
4. Determine what changes are required, guided by:
   - The reasoning and citations provided in the brief
   - The company's positioning and target audience
   - The comprehensive research insights
   - The selected topic and its research basis
5. Specify section-specific changes while maintaining research alignment
6. Be precise about what should change in the brief and why
7. Create a short, conversational message that acknowledges the user's feedback

IMPORTANT: Do not include instructions to modify the 'status' or 'run_id' fields - these are system-managed and should not be changed.

---

Provided Context:

Content Brief (with reasoning, citations, and potential user edits): 
{content_brief}

---

User Feedback: 
{revision_feedback}

---

Company Context:
- Company Context: {company_doc}
- Content Playbook Guidance: {content_playbook_doc}

---

Selected Topic (with reasoning): {selected_topic}

---

Research Foundation (with sources and citations):
Google Research: {google_research_output}
Reddit Research: {reddit_research_output}

REMEMBER: Use the research citations and reasoning to justify any changes while respecting user modifications.
"""

# =============================================================================
# USER PROMPT TEMPLATES
# =============================================================================

GOOGLE_RESEARCH_USER_PROMPT_TEMPLATE = """
Based on the company context and user input provided, perform web research and return results in the exact JSON format specified.

Company Context:
- Company Context: {company_doc}

User Input: {user_input}

Tasks:
1. Generate 3-5 research queries relevant to the user input and company context
   - Explain your reasoning for each query
   - Show how it connects to user needs and company goals
   
2. Search google.com for these queries
   - Document why you selected each search term
   
3. Extract top 5 most relevant articles/resources
   - For EACH article, explain WHY it was selected
   - Include specific value it provides to our research
   
4. Identify key headings from each article
   - Note which headings address user pain points
   - Cite specific insights or data from each section
   
5. Collect related "People Also Asked" questions
   - Explain patterns you notice in these questions
   - Connect them to the company's content opportunities

REMEMBER: Your reasoning and citations will guide all subsequent research and content decisions.

Return in this exact JSON format with all reasoning and citation fields populated.
"""

REDDIT_RESEARCH_USER_PROMPT_TEMPLATE = """
Based on the following inputs INCLUDING the Google research already completed, perform Reddit research and return results in the exact JSON format specified.

Company Context:
- Company Context: {company_doc}

PREVIOUS RESEARCH COMPLETED:
Google Research Results: {google_research_output}

User Input: {user_input}

Tasks:
1. Generate 5-7 Reddit search queries using relevant subreddits for the industry
   - Build on patterns identified in Google research
   - Explain how each query targets specific user segments
   
2. Search reddit.com for these queries (focus on last 3 months)
   - Document why each subreddit was chosen
   
3. Analyze the discussions to identify frequently asked questions
   - For EACH question, cite the specific thread/comment
   - Explain the underlying pain point or need
   
4. Group similar questions and determine user intent
   - Connect question groups to insights from Google research
   - Explain how these align with company offerings
   
5. Extract variations of how users actually phrased these questions
   - Note specific terminology and language patterns
   - Identify emotional triggers and urgency indicators

Use relevant subreddits like: r/marketing, r/ecommerce, r/smallbusiness, r/startups, etc.
Do NOT include brand names in queries.

REMEMBER: Show how Reddit insights complement and expand on the Google research findings.

Return in this exact JSON format with all reasoning and citation fields populated.
"""

TOPIC_GENERATION_USER_PROMPT_TEMPLATE = """
Based on the comprehensive research insights and company context, generate 5 strategic blog topic ideas.

Company Context:
- Company Context: {company_doc}
- Content Playbook Guidance: {content_playbook_doc}

COMPLETE RESEARCH CHAIN:
Google Research (with sources and citations): {google_research_output}
Reddit Research (with user questions and pain points): {reddit_research_output}
Original User Input: {user_input}

Generate 5 strategic blog topic ideas that:
- Address real user intent from BOTH research sources
- Are valuable to the target audience
- Offer a fresh angle or framework
- Are credible and practical
- Align with the company's expertise area

CRITICAL REQUIREMENTS FOR EACH TOPIC:
1. Provide clear reasoning connecting it to specific research findings
2. Cite at least 2 specific data points (user questions, article insights, statistics)
3. Explain how it serves both SEO goals and user needs
4. Document which company strengths it showcases
5. Show how it synthesizes patterns from both Google and Reddit research

IMPORTANT: Each topic must include:
- A unique topic_id (topic_01, topic_02, topic_03, topic_04, topic_05)
- Clear reasoning with research citations
- Connection to user pain points and company expertise

Return in this exact JSON format with all reasoning and citation fields populated.
"""

BRIEF_GENERATION_USER_PROMPT_TEMPLATE = """
Create a comprehensive content brief for the selected blog post topic, synthesizing ALL research and reasoning from previous steps.

Company Context:
- Company Context: {company_doc}
- Content Playbook Guidance: {content_playbook_doc}

Selected Topic by User(with its reasoning and research basis): {selected_topic}

COMPLETE RESEARCH FOUNDATION:
Google Research (with sources and citations): {google_research_output}
Reddit Research (with user questions and patterns): {reddit_research_output}
Original User Input: {user_input}

CRITICAL PLAYBOOK ALIGNMENT REQUIREMENTS:
- The brief MUST align with one of the specific themes/plays outlined in the Content Playbook
- Use the target audience definitions and content goals as specified in the playbook
- Ensure the content strategy matches the playbook's strategic direction
- Reference which specific play from the playbook this brief supports
- Adapt the tone, messaging, and approach to match the playbook guidelines

Create a comprehensive content brief that includes:

1. Playbook alignment section
   - Identify which specific theme/play from the playbook this brief supports
   - Explain how the selected topic fits within the playbook strategy
   - Use the audience and goals defined in the playbook for this play
   
2. Content structure with reasoning for each section
   - Explain WHY each section is necessary
   - In research_support field: Include ALL relevant research information that will help write this section
     * Pull in specific data, statistics, quotes, examples, case studies
     * Include user questions, pain points, and Reddit insights  
     * Add source URLs and expert opinions
     * Provide everything a writer needs to create well-supported content
   - Cite specific research that justifies its inclusion
   - Show how structure aligns with playbook recommendations
   
3. SEO considerations based on actual user language
   - Connect keywords to Reddit discussions and Google searches
   - Explain search intent behind each keyword cluster
   - Ensure SEO strategy supports playbook objectives
   
4. Brand guidelines aligned with company positioning AND playbook
   - Show how tone serves the playbook-defined target audience
   - Connect style to both company differentiation and playbook guidance
   - Reference specific playbook tone and messaging guidelines
   
5. Specific research sources to reference
   - Include key insights from each source
   - Explain how to use each source in the content
   - Connect sources to playbook themes and messaging
   
6. Writing instructions based on research patterns AND playbook
   - Address specific user questions identified
   - Include data points and citations to reference
   - Incorporate playbook-specific messaging and positioning

CRITICAL: For EVERY element of the brief, provide:
- Clear reasoning for its inclusion
- Citations to specific research findings
- Connection to user needs and company goals
- Explicit alignment with the chosen playbook theme/play

ESPECIALLY IMPORTANT for research_support in each section:
- Don't just justify the section - provide ALL the research material needed to write it
- Include every relevant statistic, quote, insight, example, and data point from your research
- The writer should have everything they need to create comprehensive, fact-based content
- Think of research_support as the "research arsenal" for writing that specific section

IMPORTANT: Do not modify the 'status' field - these are system-managed fields that should remain unchanged.

Return in this exact JSON format with all reasoning and citation fields populated.
"""

BRIEF_REVISION_USER_PROMPT_TEMPLATE = """
Based on the analyzed feedback, revise the content brief while maintaining alignment with all research insights and company context.

REVISION INSTRUCTIONS:
{revision_instructions}

CRITICAL REQUIREMENTS:
1. Apply the specific changes requested in the revision instructions
2. Maintain consistency with:
   - The selected topic and its research foundation
   - Google and Reddit research insights already gathered
   - Company positioning and content playbook guidelines
   - SEO opportunities identified in the research
   
3. Preserve elements that aren't mentioned in the revision instructions
4. Ensure all reasoning and citations remain connected to the research
5. Keep the same level of detail and comprehensiveness
   - Especially maintain comprehensive research_support for each section
   - Continue to include ALL relevant research material that helps write each section
6. Do not modify the 'status' field - this is system-managed

APPROACH:
- Focus on the specific sections or elements mentioned in the revision instructions
- Strengthen connections to research where feedback requests more evidence
- Adjust tone, structure, or focus as directed while keeping research alignment
- If feedback requests new angles, draw from existing research to support them
- Maintain the strategic value of the content for the company's goals

Remember: This is a revision, not a complete rewrite. Make targeted improvements based on the feedback while preserving the strong foundation already established.

Return the revised content brief in the exact same JSON format with all fields populated.
"""

TOPIC_REGENERATION_USER_PROMPT_TEMPLATE = """
Based on the user's feedback, regenerate blog topic suggestions that better align with their needs while maintaining connection to the research insights.

USER FEEDBACK FOR TOPIC REGENERATION:
{regeneration_instructions}

CRITICAL REQUIREMENTS:
1. Address the specific concerns or preferences expressed in the feedback
2. Continue to draw from:
   - Google research insights and source articles already gathered
   - Reddit user questions and pain points identified
   - Company positioning and expertise areas
   - Content playbook strategic guidance
   
3. Maintain the quality bar:
   - Each topic must still have clear research citations
   - Topics should address real user intent from both research sources
   - Maintain strategic alignment with company goals
   - Offer fresh angles or frameworks as requested
   
4. Adjust your approach based on the feedback:
   - If user wants more technical topics, emphasize technical insights from research
   - If user wants different angles, explore alternative framings of the research
   - If user wants specific focus areas, filter research insights accordingly
   - If user wants broader/narrower scope, adjust topic breadth appropriately

IMPORTANT REMINDERS:
- Keep the same format with unique topic_ids (topic_01, topic_02, etc.)
- Provide clear reasoning connecting each topic to research findings
- Include at least 2 specific data points per topic
- Show how topics synthesize patterns from both Google and Reddit research
- Explain how each topic serves the user's refined direction

Build on the research foundation already established - don't start from scratch, but refine and redirect based on the feedback.

Return 5 new strategic blog topic ideas in the exact same JSON format with all reasoning and citation fields populated.
"""

# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================

class SourceArticleSchema(BaseModel):
    """Enhanced schema for a single source article from research."""
    title: str = Field(description="Title of the article")
    url: str = Field(description="URL of the article")
    headings_covered: List[str] = Field(description="Key headings or themes covered in the article")
    selection_reasoning: str = Field(description="Why this article was selected for our research")
    key_citations: List[str] = Field(description="Specific quotes, statistics, or insights from this article")
    relevance_to_user_input: str = Field(description="How this article addresses the user's needs")
    relevance_to_company: str = Field(description="How this article aligns with company positioning")

class GoogleResearchSchema(BaseModel):
    """Enhanced schema for Google research results."""
    research_queries: List[str] = Field(description="List of research queries used for web search")
    query_reasoning: List[str] = Field(description="Reasoning for each query choice")
    source_articles: List[SourceArticleSchema] = Field(description="List of relevant articles found during research")
    people_also_asked: List[str] = Field(description="Related questions from search results")
    paa_patterns: str = Field(description="Patterns identified in People Also Asked questions")
    research_synthesis: str = Field(description="Overall synthesis of findings from Google research")

class UserQuestionSchema(BaseModel):
    """Enhanced schema for a user question from Reddit research."""
    question: str = Field(description="The user question")
    mentions: int = Field(description="Number of times this question or similar was mentioned")
    user_intent: str = Field(description="The underlying intent behind the question")
    pain_point_analysis: str = Field(description="Deep analysis of the pain point driving this question")
    longtail_queries: List[str] = Field(description="Long-tail variations of how users asked this question")
    reddit_citations: List[str] = Field(description="Specific Reddit threads/comments where this was discussed")
    connection_to_google_research: str = Field(description="How this question relates to Google research findings")
    urgency_level: str = Field(description="How urgent/important this question is to users (high/medium/low)")

class RedditResearchSchema(BaseModel):
    """Enhanced schema for Reddit research results."""
    user_questions_summary: List[UserQuestionSchema] = Field(description="Summary of user questions from Reddit research")
    subreddits_analyzed: List[str] = Field(description="List of subreddits searched and why")
    user_language_patterns: List[str] = Field(description="Common phrases and terminology used by users")
    emotional_triggers: List[str] = Field(description="Emotional aspects identified in user discussions")
    research_synthesis: str = Field(description="Overall synthesis connecting Reddit findings to Google research")



class BlogTopicSchema(BaseModel):
    """Enhanced schema for a single blog topic suggestion."""
    topic_id: str = Field(description="Unique identifier for this topic (topic_01, topic_02, etc.)")
    title: str = Field(description="The blog topic title")
    angle: str = Field(description="Brief description of the unique angle or approach this topic will take")
    topic_reasoning: str = Field(description="Detailed reasoning for why this topic was chosen")
    research_citations: List[str] = Field(description="Specific research findings that justify this topic")
    user_questions_addressed: List[str] = Field(description="User questions from Reddit this topic will answer")
    seo_opportunity: str = Field(description="SEO opportunity this topic captures")
    company_expertise_showcase: str = Field(description="How this topic showcases company strengths")

class TopicSuggestionsSchema(BaseModel):
    """Enhanced schema for blog topic suggestions."""
    suggested_blog_topics: List[BlogTopicSchema] = Field(description="List of suggested blog topics with unique angles")
    topic_strategy_summary: str = Field(description="Overall strategy connecting all topics to research and company goals")



class ContentSectionSchema(BaseModel):
    """Enhanced schema for a content section in the brief."""
    section: str = Field(description="Name of the content section")
    description: str = Field(description="Description of what should be covered in this section")
    word_count: int = Field(description="Estimated word count for this section")
    section_reasoning: str = Field(description="Why this section is essential to the content")
    research_support: List[str] = Field(description="ALL relevant research findings, data points, statistics, expert quotes, user insights, and source information that should be referenced when writing this section. Include everything from the research that will help create comprehensive, well-supported content")
    user_questions_answered: List[str] = Field(description="User questions this section addresses")

class SEOKeywordsSchema(BaseModel):
    """Enhanced schema for SEO keywords."""
    primary_keyword: str = Field(description="Primary keyword for the content")
    primary_keyword_reasoning: str = Field(description="Why this primary keyword was chosen based on research")
    secondary_keywords: List[str] = Field(description="Secondary keywords to include")
    secondary_keywords_reasoning: List[str] = Field(description="Reasoning for each secondary keyword")
    long_tail_keywords: List[str] = Field(description="Long-tail keywords for SEO")
    reddit_language_incorporated: List[str] = Field(description="User language from Reddit incorporated as keywords")
    search_intent_analysis: str = Field(description="Analysis of search intent behind keyword strategy")

class BrandGuidelinesSchema(BaseModel):
    """Enhanced schema for brand guidelines."""
    tone: str = Field(description="Tone of voice for the content")
    tone_reasoning: str = Field(description="Why this tone aligns with audience and company")
    voice: str = Field(description="Brand voice characteristics")
    voice_reasoning: str = Field(description="How voice reflects company positioning")
    style_notes: List[str] = Field(description="Additional style guidelines and notes")
    differentiation_elements: List[str] = Field(description="Elements that differentiate from competitors")

class ResearchSourceSchema(BaseModel):
    """Enhanced schema for a research source."""
    source: str = Field(description="Name or description of the research source")
    key_insights: List[str] = Field(description="Key insights extracted from this source")
    how_to_use: str = Field(description="Specific guidance on how to incorporate this source")
    citations_to_include: List[str] = Field(description="Specific data points or quotes to reference")

class ContentBriefDetailSchema(BaseModel):
    """Enhanced schema for the detailed content brief."""
    title: str = Field(description="Title of the content")
    title_reasoning: str = Field(description="Why this title was chosen based on research")
    target_audience: str = Field(description="Target audience for the content")
    audience_reasoning: str = Field(description="How audience definition connects to research insights")
    content_goal: str = Field(description="Primary goal of the content")
    goal_reasoning: str = Field(description="How this goal serves user needs and company objectives")
    key_takeaways: List[str] = Field(description="Key takeaways for the audience")
    takeaways_reasoning: List[str] = Field(description="Research basis for each key takeaway")
    content_structure: List[ContentSectionSchema] = Field(description="Detailed content structure")
    structure_reasoning: str = Field(description="Overall reasoning for content flow and structure")
    seo_keywords: SEOKeywordsSchema = Field(description="SEO keyword strategy")
    brand_guidelines: BrandGuidelinesSchema = Field(description="Brand voice and style guidelines")
    research_sources: List[ResearchSourceSchema] = Field(description="Research sources used")
    call_to_action: str = Field(description="Call to action for the content")
    estimated_word_count: int = Field(description="Estimated total word count")
    difficulty_level: str = Field(description="Content difficulty level (beginner, intermediate, advanced)")
    writing_instructions: List[str] = Field(description="Specific instructions for the writer")

# =============================================================================
# FEEDBACK ANALYSIS SCHEMAS
# =============================================================================

class BriefFeedbackAnalysisSchema(BaseModel):
    """Enhanced schema for brief feedback analysis output."""
    revision_instructions: str = Field(description="Clear instructions for revising the brief based on feedback, write section specific changes needed for each section")
    research_alignment_notes: str = Field(description="How to maintain alignment with research while incorporating feedback")
    change_summary: str = Field(description="Short, conversational message acknowledging the user's feedback")

# Convert Pydantic models to JSON schemas for LLM use
GOOGLE_RESEARCH_OUTPUT_SCHEMA = GoogleResearchSchema.model_json_schema()

REDDIT_RESEARCH_OUTPUT_SCHEMA = RedditResearchSchema.model_json_schema()

TOPIC_GENERATION_OUTPUT_SCHEMA = TopicSuggestionsSchema.model_json_schema()

BRIEF_GENERATION_OUTPUT_SCHEMA = ContentBriefDetailSchema.model_json_schema()

BRIEF_FEEDBACK_ANALYSIS_OUTPUT_SCHEMA = BriefFeedbackAnalysisSchema.model_json_schema()