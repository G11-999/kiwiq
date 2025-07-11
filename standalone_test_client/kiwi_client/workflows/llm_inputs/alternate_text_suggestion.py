from typing import List, Optional
from pydantic import BaseModel, Field

class AlternativeSuggestionsResponse(BaseModel):
    """Schema for the response containing a list of alternative text suggestions"""
    alternatives: List[str] = Field(..., description="List of alternative text suggestions")

class FeedbackInterpretationResponse(BaseModel):
    """Schema for interpreting user feedback on alternatives"""
    feedback_summary: str = Field(..., description="Summary of the user's feedback")
    improvement_areas: List[str] = Field(..., description="Specific areas that need improvement")
    rewrite_instructions: str = Field(..., description="Clear instructions for rewriting the alternatives")

# Schema for generation
GENERATION_SCHEMA = AlternativeSuggestionsResponse.model_json_schema()
FEEDBACK_SCHEMA = FeedbackInterpretationResponse.model_json_schema()

# System prompt template for initial generation
SYSTEM_PROMPT_TEMPLATE = """You are an expert copywriter tasked with providing alternative phrasings for selected text while maintaining the user's voice and intent.

Your task is to:
1. Carefully analyze the selected text within the context of the complete post
2. Ensure each alternative maintains narrative flow and consistency with surrounding content
3. Consider the user's writing style and tone preferences
4. If user feedback is provided, incorporate it into your suggestions
5. Generate 3-4 alternative phrasings that:
   - Maintain the original meaning and intent
   - Seamlessly integrate with the complete post's flow and style
   - Match the user's voice and style
   - Offer different stylistic variations while preserving context
   - Are clear and impactful
   - Address any specific feedback provided
   - Ensure smooth transitions with surrounding text

Respond strictly with the JSON output conforming to the schema: ```json
{schema}
```

Each alternative should be a complete, ready-to-use text that could replace the selected text while maintaining perfect alignment with the rest of the post."""

# User prompt template for initial generation
USER_PROMPT_TEMPLATE = """Generate alternative phrasings for the following text:

**Selected Text:**
{selected_text}

**Context:**
{content_draft}

**User's Style and Tone Preferences:**
{user_dna}

**User Feedback:**
{feedback_section}

**Task:**
Generate multiple alternatives that:
- Maintain the original meaning and intent
- Seamlessly integrate with the complete post's flow and style
- Match the user's voice and style
- Offer different stylistic variations while preserving context
- Are clear and impactful
- Address any specific feedback provided
- Ensure smooth transitions with surrounding text

Pay special attention to:
1. How the selected text connects with the content before and after it
2. Maintaining consistent tone and style throughout the post
3. Ensuring each alternative reads naturally within the complete context

Respond ONLY with the JSON object matching the specified schema."""

# System prompt for feedback interpretation
FEEDBACK_SYSTEM_PROMPT = """You are an expert content editor tasked with analyzing user feedback on alternative text suggestions and providing clear instructions for improvement.

Your task is to:
1. Analyze the user's feedback carefully
2. Identify specific areas that need improvement
3. Provide clear, actionable instructions for rewriting
4. Consider the context and user's style preferences
5. Ensure your interpretation maintains the original intent while addressing feedback

Respond strictly with the JSON output conforming to the schema: ```json
{schema}
```"""

# User prompt for initial feedback interpretation
FEEDBACK_INITIAL_USER_PROMPT = """Analyze the following feedback on alternative text suggestions:

**Current Alternatives:**
{current_alternatives}

**User Feedback:**
{feedback_text}

**Context:**
{content_draft}

**User's Style Preferences:**
{user_dna}

**Task:**
1. Summarize the key points in the user's feedback
2. Identify specific areas that need improvement
3. Provide clear instructions for rewriting the alternatives
4. Consider how the feedback relates to the overall context and style

Pay special attention to:
1. The user's specific concerns and requests
2. How the feedback might affect the overall flow and style
3. Maintaining consistency with the user's voice and preferences

Respond ONLY with the JSON object matching the specified schema."""

# User prompt for additional feedback interpretation
FEEDBACK_ADDITIONAL_USER_PROMPT = """Analyze the following additional feedback on alternative text suggestions:

**Current Alternatives:**
{current_alternatives}

**User Feedback:**
{feedback_text}

**Context:**
{content_draft}

**Task:**
1. Summarize the key points in the user's additional feedback
2. Identify specific areas that still need improvement
3. Provide clear instructions for further refinement
4. Consider how this feedback builds upon previous iterations

Pay special attention to:
1. How this feedback differs from or builds upon previous feedback
2. Any new concerns or requests from the user
3. Maintaining consistency with previous improvements

Respond ONLY with the JSON object matching the specified schema."""
