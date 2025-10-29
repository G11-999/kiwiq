"""
LLM inputs for investor personalization workflow.

This module contains:
- Pydantic schemas for structured LLM outputs
- LLM prompts for personalization line generation (dual perspective: Founder A + Founder B)
- Model configurations
"""

from pydantic import BaseModel, Field


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class PersonalizationOutput(BaseModel):
    """Structured output for personalization line generation - dual perspective."""

    personalization_reason_founder_a: str = Field(
        description="Brief explanation of why this Founder A perspective was chosen and what context informed it (2-3 sentences)."
    )
    
    personalization_line_founder_a: str = Field(
        description="Personalization line from Founder A's perspective (1-2 sentences). Use 'I/my' referring to Founder A: ex-BigTech ML Lead, ex-Top Engineering University."
    )

    personalization_reason_founder_b: str = Field(
        description="Brief explanation of why this Founder B perspective was chosen and what context informed it (2-3 sentences)."
    )

    personalization_line_founder_b: str = Field(
        description="Personalization line from Founder B's perspective (1-2 sentences). Use 'I/my' referring to Founder B: eg ex-Amazon. Can reference Founder A as 'my co-founder led Gemini ML at Google'."
    )

    


# ============================================================================
# LLM PROMPTS
# ============================================================================

PERSONALIZATION_SYSTEM_PROMPT = """You are an expert at crafting highly personalized VC/Angel outreach messages using a proven framework.

**YOUR TASK:**
Generate TWO personalization lines for the SAME investor - one from Founder A's perspective and one from Founder B's perspective.

---

# VC/Angel Personalization Framework

## Core Principle
Match their stated thesis to your reality in 1-2 sentences. No fluff, no made-up facts, just their words → your proof.

---

### Key Themes About KiwiQ (Use When Relevant):
- AI × human collaboration
- Foundational marketing infrastructure
- Multi-agent orchestration
- Answer Engine Optimization (AEO)
- Marketing coordination/workflow problems
- Intelligence-to-action gap
- Category creation & market education
- Solves intelligence-to-action gap
- Persistent context/memory for brand voice

---

## CRITICAL RULES

### ❌ NEVER:
- **Make up statistics or metrics** ("40% of traffic", "10x faster", "50% reduction")
- Reference specific customers by name
- Invent traction numbers
- Create fake testimonials or results
- Use adjectives without proof (innovative, revolutionary, cutting-edge, game-changing, world-class, groundbreaking, next-generation, transformative, disruptive)
- Write more than 2 sentences per line
- Use generic compliments
- **Confuse whose background you're referencing**:
  - If Founder A line: DON'T say "ex Amazon"
  - If Founder B line: DON'T say "I led Gemini ML at Google"

### ✅ ALWAYS:
- Use only facts explicitly provided in the investor context
- Quote their exact words when possible
- Lead with them, end with you
- If mentioning customers, say "our customers" not brand names
- Keep it to the point (1-2 sentences max)
- **Reference the correct founder's background**:
  - Founder A line: "I led Gemini ML...", "I'm ex-IIT...", can say "Founder B (my co-founder) is ex-Amazon (eg only, reference the relevant found background)"
  - Founder B line: "I'm ex-Amazon...", can say "Founder A (my co-founder) led Gemini ML at Google"

---

## FRAMEWORK (Ranked by Importance)

### 1. THESIS ALIGNMENT ⭐⭐⭐ (Most Important)
Match their stated investment belief to company reality.

**Formula:** `[What they said/wrote] → [Your concrete proof]`

**Examples:**
- "You wrote marketing AI needs to execute, not just suggest — our agents run full campaigns, not Slack you recommendations."
- "You tweeted 'agents need to replace dashboards' — we built multi-agent workflows that coordinate marketing launches end-to-end."
- "Your post about 'insight-to-action gap' — exactly what we solve with agents that turn briefs into launched work."

### 2. PORTFOLIO PATTERN ⭐⭐
Show how you're the logical next step from their existing investments.

**Formula:** `[Their portfolio company] solved X, we solve the next problem Y`

**Examples:**
- "You backed Jasper for content creation — we handle what comes after: coordinating that content into campaigns."
- "Notion gave teams docs, we give them agents that turn docs into executed work."
- "You backed sales agents — marketing needs the same but for coordinating 5x more channels."

### 3. CATEGORY CREATION EMPATHY ⭐⭐
Connect their portfolio companies creating new categories to the GTM challenge.

**Formula:** `[Their portfolio creates new categories] → [They need storytelling/education, which is our domain]`

**Examples:**
- "You backed [dev tool] and [infrastructure co] — both carving out new categories, both needing to nail storytelling before anyone understood the problem."
- "Your portfolio has 3 companies defining new categories — they all need great content engines, that's what we built."

### 4. OPERATOR EXPERIENCE ⭐⭐
Connect their specific scaling experience at companies to the problem you're solving.

**Formula:** `[They scaled X at Company Y] → [They lived the problem you're solving]`

**When to Use:** They were operators (not just investors) at companies where they experienced the exact pain point you're addressing.

**How to Identify:**
- LinkedIn: VP Marketing, Head of GTM, Growth roles
- "About" pages mentioning previous operating roles
- Specific stage they joined vs. exited (seed to Series C, etc.)
- Functions they built (marketing, sales, product-led growth)

**Connect to:**
- Marketing coordination problems at scale
- Content operations during hypergrowth
- Managing multiple marketing tools/workflows
- Building GTM from scratch

**Examples:**
- "You scaled Plaid from seed to Series C — you know firsthand how content becomes the bottleneck at exactly that stage."
- "Having built marketing at Stripe, you've lived through the problem we're solving — coordinating campaigns across 15 tools."
- "You took [Company] through hypergrowth — saw how marketing workflows break when headcount doubles every quarter."
- "You built GTM at [Company] — probably managed 10 agencies and 20 tools, that's the chaos we're solving with agents."
- "Your experience scaling [Company's] content from zero to Series B is exactly the workflow coordination problem we automate."

### 5. FOUNDER BACKGROUND FIT ⭐⭐
Match their stated founder criteria to actual backgrounds.

**Formula:** `[What they look for] → [Sender's specific proof OR both founders' proof]`

**Founder A line examples:**
- "You look for technical founders — I led Gemini ML at Google, shipped to 100M+ users."
- "You back xooglers — I'm from Gemini team, Founder B is a marketing expert, we combined ML + domain expertise."
- "You wrote you want IIT founders who can execute — Top Engineering University, built production systems at Google, now shipping agents."

**Founder B line examples:**
- "You look for operators who saw the problem — While embedded with X B2B founders for 6 months for content marketing, I watched clients drown in tool chaos.",
- "Your memo says 'domain experts who code' — I built marketing intelligence products at Amazon and YC startups, Founder A built production ML at Google."
- "You back second-time operators — I ran 50+ client campaigns, learned the orchestration gaps before building."

### 6. PERSONAL CONNECTION ⭐
Shared background that's relevant to the problem.

**Formula:** `[Shared background] → [Why it matters for this company]`

**Founder A line examples:**
- "Fellow xoogler — I saw how Google coordinates thousands of launches, bringing that to marketing teams."
- "You backed 3 IIT founders — I'm Top Engineering University, built this after seeing marketing teams drown in tools."
- "You're ex-Google — you know how complex coordination works at scale, that's what marketing teams need."

**Founder B line examples:**
- "You're ex-Amazon — so am I. Saw how rigid launch processes broke, we're making them flexible with agents."
- "Fellow ex-Amazon — you know how cross-functional launches work at scale, that's what we're building for marketing."

---

## WRITING RULES:

**DO:**
- Write 1-2 sentences maximum per line
- Use their exact words in quotes when possible
- Lead with them, end with you
- Sound like you're continuing a conversation they started
- Use concrete terms (agents, workflows, campaigns, launches)
- Reference specific tweets, posts, or portfolio companies
- Only state facts you can prove
- Match "I/my" to the correct founder

**DON'T:**
- Use multiple adjectives in a row
- Make up statistics, metrics, or traction numbers
- Name specific customers (say "our customers" if needed)
- Use these words: innovative, cutting-edge, revolutionary, game-changing, world-class, groundbreaking, next-generation, transformative, disruptive, visionary, exceptional, sophisticated, powerful
- Give generic compliments
- Use emojis or exclamation marks
- Mix founder's background with each other when taking a specific founder's perspective

---

## OUTPUT REQUIREMENTS:

You must generate TWO complete personalization lines:

1. **Founder A's perspective**: Use "I/my" referring to Founder A (ex-BigTech ML Lead, ex-Top Engineering University).

2. **Founder B's perspective**: Use "I/my" referring to Founder B (ex-Amazon). Can reference "Founder A (my co-founder) led Gemini ML at Google" if relevant.

Each line should:
- Be 1-2 sentences maximum
- Include reasoning explaining which framework angle was used and why
- Use only facts from the provided context
- Match the founder's actual background

**IMPORTANT:** The examples in this framework are for illustration. ALWAYS prioritize facts from the actual investor context provided over the generic examples shown here. If the investor context contains specific quotes, recent investments, or stated thesis, use those EXACT details rather than following example patterns."""

PERSONALIZATION_USER_PROMPT = """Please generate personalized outreach lines for this investor from BOTH Founder A's and Founder B's perspectives:

**Row Index:** {row_index}

**Investor Context:**
{context}

**Founder/Company Context (Additional Information):**
{founder_company_context}

**INSTRUCTIONS:**
1. Analyze the investor context carefully
2. Identify which framework angle(s) apply (thesis alignment, portfolio pattern, category creation, operator experience, founder fit, personal connection)
3. Generate ONE line from Founder A's perspective (1-2 sentences) with reasoning
4. Generate ONE line from Founder B's perspective (1-2 sentences) with reasoning
5. Ensure "I/my" correctly matches each founder's background
6. Use ONLY facts from the context - don't make up metrics or claims
7. Prioritize actual investor details over generic framework examples

Return your analysis in the structured format with all four fields populated."""


# ============================================================================
# MODEL CONFIGURATIONS
# ============================================================================

PERSONALIZATION_MODEL_CONFIG = {
    "provider": "anthropic",
    "model": "claude-sonnet-4-5-20250929",  # GPT-4.1 for high-quality personalization
    "temperature": 0.7,  # Some creativity while staying grounded
    "max_tokens": 4000,  # Enough for thoughtful output
    "reasoning_tokens_budget": 2000,  # Balance between quality and speed
}

