from pydantic import BaseModel, Field
from typing import List

POST_CREATION_INITIAL_USER_PROMPT = """
Work on LinkedIn post on behalf of the user using your deep understanding of them, how they think, how they communicate, and how they like to be perceived. Ensure each draft aligns with the Content Brief specifications for tone, structure, and call-to-action: {brief}. \n User Understanding:(Use this to get an understanding of users industry and expertise) {user_dna}\n\n. Make sure you are using the tone that user prefers. User your understanding of user's industry to draft post.
"""

POST_CREATION_FEEDBACK_USER_PROMPT = """
You are given feedback on a LinkedIn post and specific rewrite instructions.
First, use the feedback to understand what the user wanted or what was lacking in the original post.
Then, use the rewrite instructions to guide how the post should be changed.
Rewrite the LinkedIn post accordingly, making sure it reflects both the critique and the desired improvements.
Original Feedback: {current_feedback_text}
Rewrite Instructions: {rewrite_instructions}
Please rewrite the LinkedIn post accordingly.
"""


POST_CREATION_SYSTEM_PROMPT = """
You are a LinkedIn post generator. You are given a brief and a user understanding. You need to generate a LinkedIn post based on the brief and  deep understnading of user. If you are given feedback, you should rewrite it based on the user's feedback.
"""

class PostDraftSchema(BaseModel):
    post_text: str = Field(..., description="The main body of the LinkedIn post.")
    hashtags: List[str] = Field(..., description="Suggested hashtags.")


POST_LLM_OUTPUT_SCHEMA = PostDraftSchema.model_json_schema()


USER_FEEDBACK_SYSTEM_PROMPT = """
You are an expert LinkedIn content writer.

You have been provided with:
1. A draft LinkedIn post.
2. Feedback from the user about that draft.
3. A User DNA document, which includes detailed information about the user’s writing preferences, tone, domain expertise, personality traits, and stylistic choices.
"""


USER_FEEDBACK_INITIAL_USER_PROMPT= """
Your Task:

Your job is to interpret the feedback using all three inputs and produce a structured set of rewrite directives.

You must:
1. Identify the user's intent behind the feedback.
2. Locate specific areas in the original draft that are relevant to the feedback.
3. Determine what changes are required, guided not only by the feedback but also by the user’s style and preferences as described in their DNA.
4. Provide suggestions that are clearly implied by the feedback, or those that directly align with preferences in the DNA document.
5. Be precise about what should change, where it should change, and how it should be rewritten.

---

How to use the provided context:

- Original Draft: Use this to understand the existing content structure, tone, message, and flow. When identifying which parts to change, reference specific phrases or sections from the draft.
  
- User Feedback: Use this to extract the user's explicit or implicit intentions — what they like, dislike, want adjusted, or want added/removed.

- User DNA Document: Use this to ground your interpretation in the user's voice. If the user prefers a bold tone, avoid recommending softer language. If the user tends to write in first person, don’t suggest a third-person rewrite. If their DNA emphasizes “industry leadership,” consider how the feedback might be interpreted through that lens.

---

Output Structure:

- feedback_type:  Classify the feedback’s intent (multiple values allowed if applicable) eg: ("rewrite_request", "tone_change", "clarity_issue", "length_issue", "add_content", "remove_content", "style_adjustment", "grammar_spelling", "unclear").

- rewrite_instructions: Write clear and direct rewrite instructions. Specify:
  - Which parts of the draft should be changed (quote or describe them if helpful).
  - What the change should be (e.g., more concise, more detailed, different tone).
  - How it aligns with the user’s style, if relevant (e.g., “User prefers confident and human tone – rephrase this line to feel more relatable.”)

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
"""

USER_FEEDBACK_ADDITIONAL_USER_PROMPT= """
I have provided the updated draft that was generated based on the last round of feedback.

Now, the user has provided additional feedback on this version.

Your task is to interpret the new feedback using the **same instructions and structure as before**, and write a fresh set of **rewrite directives**.

Use the **original context** (user DNA, original draft, previous feedback) to stay consistent with the user’s tone, preferences, and intent.

---

Updated Draft: 
{current_post_draft}

New Feedback: 
{current_feedback_text}
"""

