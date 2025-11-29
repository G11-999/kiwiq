from typing import Dict, Any, Optional, List, Union, ClassVar, Type
import json
from enum import Enum

# Using Pydantic for easier schema generation
from pydantic import BaseModel, Field

class StrategyAudienceSchema(BaseModel):
    """Target audience segments for strategy"""
    primary: str = Field(description="Primary audience")
    secondary: Optional[str] = Field(description="Secondary audience")
    tertiary: Optional[str] = Field(description="Tertiary audience")

class FoundationElementsSchema(BaseModel):
    """Foundational elements of the strategy"""
    expertise: List[str] = Field(description="Areas of expertise")
    core_beliefs: List[str] = Field(description="Core beliefs")
    objectives: List[str] = Field(description="Strategy objectives")

class PostPerformanceAnalysisSchema(BaseModel):
    """Analysis of post performance"""
    current_engagement: str = Field(description="Current engagement levels")
    content_that_resonates: str = Field(description="Content types that resonate with audience")
    audience_response: str = Field(description="How audience responds to content")

class ContentPillarSchema(BaseModel):
    """Content pillar definitions"""
    name: str = Field(description="Pillar name")
    pillar: str = Field(description="Pillar theme")
    sub_topic: List[str] = Field(description="Sub-topics within pillar")

class ThirtyDayTargetsSchema(BaseModel):
    """30-day goals"""
    goal: str = Field(description="Overall goal for the 30 days")
    method: str = Field(description="Method to achieve the goal")
    targets: str = Field(description="Quantitative targets such as number of posts, number of likes, number of comments, number of shares, etc. based on the goal.")

class NinetyDayTargetsSchema(BaseModel):
    """90-day goals"""
    goal: str = Field(description="Overall goal for the 90 days")
    method: str = Field(description="Method to achieve the goal")
    targets: str = Field(description="Quantitative targets such as number of posts, number of likes, number of comments, number of shares, etc. based on the goal.")

class ImplementationSchema(BaseModel):
    """Implementation details"""
    thirty_day_targets: ThirtyDayTargetsSchema = Field(description="30-day goals")
    ninety_day_targets: NinetyDayTargetsSchema = Field(description="90-day goals")

class ContentStrategySchema(BaseModel):
    """Content strategy document derived from user DNA (AI-generated)"""
    title: str = Field(description="Strategy title")
    target_audience: StrategyAudienceSchema = Field(description="Target audience segments")
    foundation_elements: FoundationElementsSchema = Field(description="Foundational elements of the strategy")
    core_perspectives: List[str] = Field(description="Core content perspectives")
    content_pillars: List[ContentPillarSchema] = Field(description="Content pillar definitions")
    post_performance_analysis: Optional[PostPerformanceAnalysisSchema] = Field(description="Analysis of current post performance", default=None)
    implementation: ImplementationSchema = Field(description="Implementation details")

GENERATION_SCHEMA = ContentStrategySchema.model_json_schema()


SYSTEM_PROMPT_TEMPLATE = """
You are a strategic LinkedIn content consultant specializing in professional branding and audience growth. Develop comprehensive content strategy tailored to the user's professional background and goals. Respond strictly with the JSON output conforming to the schema: 
```json
{schema}
```
"""

def _generate_example_content(num_words: int = 525000) -> str:
    """
    Generate approximately 300k tokens (225k words) of example content for prompt testing.
    
    This generates repetitive but structured content including:
    - Example LinkedIn posts across various topics
    - Sample industry insights
    - Content strategy examples
    - Audience engagement patterns
    
    Args:
        num_words: Target number of words to generate (default ~225k words ≈ 300k tokens)
        
    Returns:
        str: Generated example content
    """
    # Base templates for different content types
    post_templates = [
        "Example LinkedIn Post #{num}: The future of {topic} is transforming rapidly. Here are five key insights every professional should know about {subtopic}. First, understanding the fundamentals of {detail1} allows teams to build stronger foundations. Second, leveraging {detail2} creates competitive advantages in modern markets. Third, implementing {detail3} drives measurable business outcomes. Fourth, adopting {detail4} enables scalable growth strategies. Fifth, mastering {detail5} positions organizations for long-term success. What trends are you seeing in your industry?",
        
        "Industry Insight #{num}: Three critical lessons about {topic} that changed my perspective on {subtopic}. After working with dozens of companies implementing {detail1}, I've noticed consistent patterns. Organizations that prioritize {detail2} consistently outperform competitors. Leaders who embrace {detail3} build more resilient teams. Companies investing in {detail4} see faster time-to-market. The common thread? Understanding {detail5} drives sustainable competitive advantage. Share your thoughts below.",
        
        "Professional Development Post #{num}: How to master {topic} in {subtopic} - a comprehensive guide. Step one involves deeply understanding {detail1} through hands-on practice and continuous learning. Step two requires building expertise in {detail2} by working on real-world projects. Step three focuses on developing proficiency with {detail3} to accelerate professional growth. Step four emphasizes mastering {detail4} for career advancement. Step five centers on leveraging {detail5} to create lasting impact. What strategies have worked for you?",
        
        "Thought Leadership #{num}: Why {topic} matters more than ever for {subtopic}. The landscape has shifted dramatically with {detail1} becoming table stakes. Organizations must now prioritize {detail2} to remain competitive. Teams that excel at {detail3} deliver superior results. Leaders who champion {detail4} build stronger cultures. Companies focused on {detail5} achieve better outcomes. Let me know your perspective in the comments.",
        
        "Case Study #{num}: How one company transformed {topic} through innovative {subtopic} strategies. They started by reimagining {detail1} from first principles. Next, they invested heavily in {detail2} capabilities across the organization. Then, they systematically improved {detail3} through data-driven iteration. Additionally, they doubled down on {detail4} as a core competency. Finally, they scaled {detail5} across all business units. The results speak for themselves - what would you do differently?",
    ]
    
    # Topic and detail variations for generating diverse content
    topics = [
        "artificial intelligence", "digital transformation", "leadership development", "team collaboration",
        "data analytics", "customer experience", "innovation management", "organizational culture",
        "strategic planning", "change management", "product development", "market research",
        "business strategy", "operational excellence", "talent acquisition", "employee engagement",
        "sales optimization", "marketing automation", "brand positioning", "competitive analysis",
        "financial planning", "risk management", "supply chain", "sustainability practices",
        "remote work", "hybrid teams", "agile methodology", "design thinking",
        "customer success", "user experience", "growth hacking", "content marketing",
        "social media strategy", "thought leadership", "personal branding", "professional networking",
        "career development", "skill building", "mentorship programs", "executive coaching",
        "board governance", "stakeholder management", "investor relations", "corporate communications"
    ]
    
    subtopics = [
        "modern enterprises", "fast-growing startups", "global organizations", "distributed teams",
        "technology sectors", "healthcare industries", "financial services", "retail markets",
        "manufacturing operations", "professional services", "education institutions", "government agencies",
        "nonprofit organizations", "consulting firms", "media companies", "entertainment industry",
        "real estate development", "logistics networks", "energy sector", "telecommunications",
        "automotive industry", "aerospace engineering", "biotechnology firms", "pharmaceutical companies",
        "consumer electronics", "software development", "cloud computing", "cybersecurity",
        "blockchain applications", "mobile technology", "internet platforms", "e-commerce businesses",
        "marketing agencies", "advertising firms", "public relations", "brand management",
        "human resources", "talent development", "organizational design", "business operations",
        "customer service", "technical support", "quality assurance", "continuous improvement"
    ]
    
    details = [
        "strategic alignment", "data-driven decision making", "cross-functional collaboration",
        "customer-centric approaches", "agile processes", "continuous improvement",
        "technological innovation", "organizational learning", "performance metrics",
        "stakeholder engagement", "resource allocation", "risk mitigation",
        "talent development", "leadership commitment", "cultural transformation",
        "market intelligence", "competitive positioning", "value proposition",
        "operational efficiency", "quality standards", "regulatory compliance",
        "financial discipline", "investment strategy", "growth mindset",
        "customer insights", "user feedback", "behavioral analysis",
        "team dynamics", "communication patterns", "collaboration tools",
        "process optimization", "workflow automation", "system integration",
        "knowledge management", "best practices", "lessons learned",
        "change readiness", "adoption strategies", "training programs",
        "measurement frameworks", "analytics capabilities", "reporting systems",
        "strategic partnerships", "ecosystem building", "network effects",
        "scalability factors", "sustainability practices", "long-term thinking"
    ]
    
    # Generate content by cycling through templates and filling with variations
    content_blocks = []
    post_num = 1
    
    # Calculate how many posts we need (average ~180 words per post)
    num_posts = num_words // 180
    
    for i in range(num_posts):
        template = post_templates[i % len(post_templates)]
        
        # Select topic variations
        topic_idx = (i * 7) % len(topics)
        subtopic_idx = (i * 11) % len(subtopics)
        
        # Generate post content with cycling details
        post_content = template.format(
            num=post_num,
            topic=topics[topic_idx],
            subtopic=subtopics[subtopic_idx],
            detail1=details[(i * 3) % len(details)],
            detail2=details[(i * 3 + 1) % len(details)],
            detail3=details[(i * 3 + 2) % len(details)],
            detail4=details[(i * 5) % len(details)],
            detail5=details[(i * 5 + 1) % len(details)]
        )
        
        content_blocks.append(post_content)
        post_num += 1
        
        # Add separator every 10 posts for readability
        if post_num % 10 == 0:
            content_blocks.append("\n--- Content Section Divider ---\n")
    
    return "\n\n".join(content_blocks)


# Generate the large example content (approximately 300k tokens)
_LARGE_EXAMPLE_CONTENT = _generate_example_content()
print(len(_LARGE_EXAMPLE_CONTENT))


USER_PROMPT_TEMPLATE = """
As a world-class content strategist, your task is to develop a comprehensive LinkedIn content strategy document for user using the Content Strategy Methodology. Analyze the provided inputs to understand user's background, goals, and voice. Fill in the Content Strategy Template with their Content Pillars, Target Audience, Content Goals, Tone and Voice Guidelines, Posting Frequency, Content Mix, and Implementation Plan.

Do not make up any information. Only use the information provided in the inputs.

**Strategic Framework:**

- Content Methodology:(use these as a methodology to create the strategy) {building_blocks}
- Implementation Guidelines:(use these as a guideline to implement the methodology) {methodology_implementation}

**User Information:**

- Content Preferences: {user_preferences}
- Content Pillars: {content_pillars}
- Core Beliefs & Perspectives: {core_beliefs_perspectives}
- User Source Analysis: {user_source_analysis}

**Instructions for Using the Above Documents:**

- Use *Content Preferences* to define the user's audience, goals, tone, and posting cadence.
- Use *Content Pillars* to shape the key domains around which the strategy will be structured. Any topics or themes shared are to be treated as **examples only** — not exhaustive or prescriptive. The AI agent using this strategy must independently generate fresh content ideas aligned with the intent of each pillar.
- Use *Core Beliefs & Perspectives* to establish the user's worldview, positioning, and messaging anchors.
- Use *User Source Analysis* only where relevant — focus on useful details such as platform behavior insights, storytelling patterns, or audience motivations. Do not include irrelevant background.
- Apply the *Building Blocks Methodology* to design modular content pieces suited to different content types (awareness, authority, engagement, etc.).
- Follow the *AI Copilot Guidelines* to simulate a working model where content is co-created, improved over time through performance feedback, and personalized iteratively.

**Important Note:**

Clearly mention that any specific examples in this strategy (such as content topics, headlines, or formats) are for **illustration only**. The AI content generation agent using this strategy must **not** reuse them directly or limit itself to those examples. It should ideate original, relevant content within the strategic direction defined here — adapting to the user's goals and evolving audience needs.

This content strategy will be used by an AI content writing agent to drive weekly content planning and execution.

**Example Content Library (For Reference - Approximately 300k tokens):**

The following extensive library contains example LinkedIn posts, industry insights, case studies, and thought leadership content across various topics and industries. These examples serve as reference material to understand content patterns, engagement strategies, and professional communication styles. Use these examples to inform the strategy's tone, structure, and approach, but DO NOT copy them directly.

"""  #  + _LARGE_EXAMPLE_CONTENT
