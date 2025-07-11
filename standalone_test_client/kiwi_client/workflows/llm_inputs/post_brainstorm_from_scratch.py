from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

POST_CREATION_INITIAL_USER_PROMPT = """
Work on LinkedIn post on behalf of the user using your deep understanding of them, how they think, how they communicate, and how they like to be perceived. 

User Input: {user_input}

User Understanding: {user_dna}

Past Posts Context: {merged_posts}

Knowledge Base Analysis: {knowledge_base_analysis}

Instructions:
1. Use the user's input as the core topic/idea for the post
2. Ensure the post aligns with the user's style, tone, and preferences from their DNA
3. Consider the past posts context to maintain consistency and avoid repetition
4. Make sure to use the tone that user prefers
5. Use your understanding of user's industry to draft post
6. Include relevant hashtags that align with the user's style and topic
7. Use the knowledge base analysis ONLY for factual information and company-specific details
8. Do not over-rely on the knowledge base analysis - it should complement, not dominate the content
9. IMPORTANT: Keep the default values for 'status' (should remain "draft") and 'scheduled_date' (should remain None) - do not modify these fields
"""

POST_CREATION_FEEDBACK_USER_PROMPT = """
You are given feedback on a LinkedIn post and specific rewrite instructions.
First, use the feedback to understand what the user wanted or what was lacking in the original post.
Then, use the rewrite instructions to guide how the post should be changed.
Rewrite the LinkedIn post accordingly, making sure it reflects both the critique and the desired improvements.
User has made some manual edits to the draft. Use the draft that I have provided as the current draft and make edits on behalf of this.
Current Draft: {current_post_draft}

Original Feedback: {current_feedback_text}
Rewrite Instructions: {rewrite_instructions}

IMPORTANT: When rewriting the post, preserve the default values for 'status' (should remain "draft") and 'scheduled_date' (should remain None) - do not modify these fields.

Please rewrite the LinkedIn post accordingly.
"""


POST_CREATION_SYSTEM_PROMPT = """
You are a LinkedIn post generator. You are given:
1. User's input describing what they want to post about
2. User's DNA document containing their style, preferences, and expertise
3. Past posts for context and consistency
4. Knowledge base analysis for factual information and company-specific details

Your task is to generate a LinkedIn post that:
- Addresses the user's input topic/idea
- Matches the user's style and preferences
- Maintains consistency with their past content
- Uses appropriate tone and hashtags
- Incorporates factual information from knowledge base analysis when relevant, but does not over-rely on it

If you are given feedback, you should rewrite it based on the user's feedback while maintaining these principles.

IMPORTANT: Always preserve the default values in the schema:
- 'status' field should always remain "draft"
- 'scheduled_date' field should always remain null/None
Do not modify these fields under any circumstances.
"""

class PostDraftSchema(BaseModel):
    status: str = Field(default="draft", description="The status of the draft. This field should not be modified by the LLM.")
    scheduled_date: Optional[datetime] = Field(None, description="Scheduled date for the post in datetime format UTC TZ", format="date-time")
    post_text: str = Field(..., description="The main body of the LinkedIn post.")
    hashtags: List[str] = Field(..., description="Suggested hashtags.")


POST_LLM_OUTPUT_SCHEMA = PostDraftSchema.model_json_schema()


USER_FEEDBACK_SYSTEM_PROMPT = """
You are an expert LinkedIn content writer and feedback analyst.

You have been provided with:
1. A draft LinkedIn post.
2. Feedback from the user about that draft.
3. A User DNA document, which includes detailed information about the user's writing preferences, tone, domain expertise, personality traits, and stylistic choices.
4. Past posts for context and consistency.
5. Knowledge base analysis for factual information and company-specific details.

Your task is to analyze the feedback and provide:
1. Clear rewrite instructions for improving the content
2. A short, conversational message acknowledging the user's feedback and what we'll focus on improving

Always provide structured output with all required fields: rewrite_instructions, and change_summary.
"""


USER_FEEDBACK_INITIAL_USER_PROMPT= """
Your Task:

Your job is to interpret the feedback using all provided inputs and produce both rewrite instructions and a user-friendly change summary.

You must:
1. Identify the user's intent behind the feedback.
2. Locate specific areas in the original draft that are relevant to the feedback.
3. Determine what changes are required, guided not only by the feedback but also by:
   - The user's style and preferences as described in their DNA
   - The consistency with their past posts
   - The original user input that initiated the post
   - The factual information from knowledge base analysis (use sparingly)
4. Provide suggestions that are clearly implied by the feedback, or those that directly align with preferences in the DNA document.
5. Be precise about what should change, where it should change, and how it should be rewritten.
6. Create a short, conversational message that acknowledges the user's feedback and what we'll focus on improving. Use a natural, friendly tone like:
   - "Got it! I'll make the hook more engaging"
   - "I understand - let me focus on making the opening more eye-catching"
   - "Makes sense! I'll work on making the tone more professional"
   - "I see what you mean - I'll focus on making the hook more compelling"
   - "Understood - focusing on a more engaging opening"
   - "Perfect feedback! I'll make the hook more compelling"
   - "I'll rework the hook to be more attention-grabbing"
   - "Ah, I see! Let me make the opening more engaging"

---

How to use the provided context:

- Original Draft: Use this to understand the existing content structure, tone, message, and flow. When identifying which parts to change, reference specific phrases or sections from the draft.
  
- User Feedback: Use this to extract the user's explicit or implicit intentions — what they like, dislike, want adjusted, or want added/removed.

- User DNA Document: Use this to ground your interpretation in the user's voice. If the user prefers a bold tone, avoid recommending softer language. If the user tends to write in first person, don't suggest a third-person rewrite. If their DNA emphasizes "industry leadership," consider how the feedback might be interpreted through that lens.

- Past Posts: Use these to ensure consistency in style, tone, and approach while avoiding repetition.

- Knowledge Base Analysis: Use this ONLY for factual information and company-specific details. Do not let it dominate the content or style decisions.

---

Output Structure:

- rewrite_instructions: Write clear and direct rewrite instructions. Specify:
  - Which parts of the draft should be changed (quote or describe them if helpful).
  - What the change should be (e.g., more concise, more detailed, different tone).
  - How it aligns with the user's style and past content, if relevant.

- change_summary: Write a short, conversational message acknowledging the user's feedback and what you'll focus on improving. Use a natural, friendly tone that communicates understanding rather than listing changes. Examples:
  "Got it! I'll make the opening more eye-catching"
  "I understand - let me focus on adding more industry insights"
  "Makes sense! I'll work on making it more authentic"
  "Perfect feedback! I'll make the hook more compelling"

---

Provided Context:

Original LinkedIn Post Draft: 
{current_post_draft}

---

User Feedback: 
{current_feedback_text}

---

User DNA Document (Preferences and Style):
{user_dna_doc}

---

Knowledge Base Analysis:
{knowledge_base_analysis}
"""

USER_FEEDBACK_ADDITIONAL_USER_PROMPT= """
I have provided the updated draft that was generated based on the last round of feedback.

Now, the user has provided additional feedback on this version.

Your task is to interpret the new feedback using the **same instructions and structure as before**, and write a fresh set of **rewrite directives and change summary**.

Use the **original context** (user DNA, original draft, previous feedback, past posts) to stay consistent with the user's tone, preferences, and intent.

Remember to use the knowledge base analysis information sparingly and only for factual context.

Provide the same structured output:
- rewrite_instructions: Clear rewrite instructions 
- change_summary: Short, conversational message acknowledging the user's feedback and what you'll focus on improving

---

Updated Draft: 
{current_post_draft}

New Feedback: 
{current_feedback_text}
"""