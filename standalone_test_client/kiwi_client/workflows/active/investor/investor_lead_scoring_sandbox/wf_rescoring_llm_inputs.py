"""
LLM inputs for investor check size rescoring workflow.

This module contains:
- Pydantic schemas for structured LLM outputs
- LLM prompts for check size scoring
- Model configurations
"""

from pydantic import BaseModel, Field
from typing import Optional


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class CheckSizeScore(BaseModel):
    """Structured output for check size scoring."""

    # reasoning: str = Field(
    #     description="Brief explanation of why this score was assigned (1-2 sentences)."
    # )

    parsed_typical_amount: Optional[str] = Field(
        default=None,
        description="The typical/midpoint check size extracted from the string (e.g., '$1.5M', '$500K', 'N/A')"
    )

    new_check_size_points: int = Field(
        description="New check size score based on rescoring rules. Must be 0, 2, 6, or 10."
    )


# ============================================================================
# LLM PROMPTS
# ============================================================================

RESCORE_CHECK_SIZE_SYSTEM_PROMPT = """You are an expert at analyzing venture capital check size data and applying scoring rules.

Your task is to parse check size strings (which can be messy, contain ranges, have multiple scenarios, etc.) and assign a score based on these rules:

**SCORING RULES:**
- **10 points**: Typical check size is $500K-$2M
- **6 points**: Typical check size is $250K-$500K
- **2 points**: Typical check size is $2M-$10M
- **0 points**: Typical check size is >$10M, <$250K, N/A, Unknown, or not a VC investor

**HOW TO PARSE CHECK SIZES:**

1. **For ranges** (e.g., "$1M-$3M"):
   - Calculate the midpoint ($2M in this case)
   - If the text mentions "typical", "average", "sweet spot", use that value instead
   - Score based on where the midpoint/typical value falls

2. **For multiple scenarios** (e.g., "$100K-$500K (pre-seed), $1M-$3M (seed)"):
   - Focus on the SEED stage check size (most relevant for scoring)
   - Ignore pre-seed, Series A+, growth equity unless that's their primary focus

3. **For "up to" or "can go up to"** (e.g., "$500K typical, up to $5M"):
   - Use the "typical" amount, not the maximum
   - The "up to" is for outliers, not the norm

4. **For complex descriptions**:
   - Extract what they TYPICALLY invest at seed stage
   - Ignore one-off large deals or follow-ons
   - If they say "seed" explicitly, use that amount

5. **Edge cases**:
   - "N/A", "Unknown", "Does not write checks", "Not a VC" → 0 points
   - "Growth equity", ">$10M", "$10M-$50M" → 0 points (too large)
   - "$25K-$100K", "angel level" → 0 points (too small, <$250K)
   - "$250K-$1M" → Use midpoint $625K → 10 points
   - "$1M-$3M" → Use midpoint $2M → 10 points (on the boundary, but overlaps with sweet spot)
   - "$2M-$5M" → Use midpoint $3.5M → 2 points
   - "$500K-$10M" → Wide range, use typical seed behavior: if seed-focused likely $1M-$2M → 10 points

**EXAMPLES:**

Input: "$250K-$2M (average $1.1M, current range $1.2M-$1.5M)"
Output: 10 points (typical is $1.1M which falls in $500K-$2M)

Input: "$1M-$5M"
Output: 2 points (midpoint $3M falls in $2M-$10M range)

Input: "$500K-$10M (seed through Series B+), typical seed $2M-$5M"
Output: 2 points (typical seed is $2M-$5M, midpoint $3.5M)

Input: "$100K-$500K"
Output: 0 points (midpoint $300K is <$500K, and range is mostly below threshold)

Input: "$1M-$3M at seed"
Output: 10 points (seed checks, midpoint $2M, overlaps with sweet spot)

Input: "$10M-$150M"
Output: 0 points (>$10M, growth equity)

Input: "Unknown"
Output: 0 points (no data)

Input: "$250K-$500K"
Output: 6 points (falls exactly in the $250K-$500K range)

**IMPORTANT:**
- Be conservative: when in doubt between two scores, choose the lower one
- Focus on SEED stage checks when multiple stages mentioned
- Use midpoint logic for ranges unless "typical" or "average" explicitly stated
- Return only 0, 2, 6, or 10 as valid scores
"""

RESCORE_CHECK_SIZE_USER_PROMPT = """Please score this check size:

**Row Index:** {row_index}
**Investor Name:** {investor_name}
**Current Check Size String:** "{typical_check_size}"
**Current Score:** {current_score} points

Analyze the check size string and assign a new score (0, 2, 6, or 10) based on the scoring rules.

Return your analysis in the structured format."""


# ============================================================================
# MODEL CONFIGURATIONS
# ============================================================================

RESCORE_MODEL_CONFIG = {
    "model": "gpt-5",  # GPT-4o for cost-efficiency and speed
    "temperature": 0.0,  # Deterministic scoring
    "max_tokens": 1000,   # Short structured output
    "reasoning_effort": "low",
}
