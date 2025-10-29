# Investor Personalization Workflow

Generate tailored personalization lines for investor outreach based on their context data - **from both Founder A's and Founder B's perspectives**.

## Overview

This workflow uses GPT-4.1 to analyze investor data and generate compelling, specific personalization lines that can be used in outreach emails. The system generates **TWO personalization lines per investor** - one from Founder A's perspective (ex-BigTech ML Lead) and one from Founder B's perspective (agency operator, ex-Amazon).

The system is fully generic - you can feed it any CSV with any columns, and it will intelligently build context from the available data.

**The personalization framework follows a proven methodology:**
- **Thesis alignment**: Match their stated beliefs to your reality
- **Portfolio patterns**: Show how you're the logical next step
- **Category creation empathy**: Connect to their GTM challenges
- **Founder background fit**: Match criteria to actual backgrounds
- **Personal connections**: Leverage shared experiences

The framework explicitly avoids buzzwords, made-up metrics, and generic flattery. It emphasizes concrete facts, specific quotes, and genuine connections.

## Files

- **`wf_investor_personalization.py`** - Main workflow definition
- **`wf_personalization_llm_inputs.py`** - LLM prompts, schemas, and model configs
- **`wf_testing/personalization_runner.py`** - Batch processing runner script

## Quick Start

### Basic Usage

```bash
# Process entire CSV with all columns as context
python wf_testing/personalization_runner.py \
    --input investors.csv \
    --output personalized_investors.csv
```

### With Column Filtering

```bash
# Only include specific columns in context
python wf_testing/personalization_runner.py \
    --input investors.csv \
    --output personalized_investors.csv \
    --allow-cols "investor_name,firm_name,recent_investments,investment_thesis,linkedin_activity"

# Exclude sensitive/internal columns
python wf_testing/personalization_runner.py \
    --input investors.csv \
    --output personalized_investors.csv \
    --deny-cols "email,phone,internal_notes,created_at,updated_at"
```

### Performance Tuning

```bash
# Process 100 rows with 5 concurrent batches
python wf_testing/personalization_runner.py \
    --input investors.csv \
    --output personalized_investors.csv \
    --start-row 0 \
    --end-row 100 \
    --batch-parallelism-limit 5

# Run sequentially with delays (rate limiting)
python wf_testing/personalization_runner.py \
    --input investors.csv \
    --output personalized_investors.csv \
    --sequential \
    --delay 60
```

## Input CSV Format

The input CSV must have a `row_index` column (or one will be auto-generated). All other columns will be used as context for personalization.

**Example Input:**

| row_index | investor_name | firm_name | recent_investments | investment_thesis | linkedin_activity | typical_check_size |
|-----------|---------------|-----------|-------------------|-------------------|-------------------|-------------------|
| 1 | John Smith | Acme Ventures | TechCo, DataFlow | Seed B2B SaaS | Posted about AI in dev tools | $1M-$3M |
| 2 | Jane Doe | Beta Capital | CloudOps, FinFlow | Fintech & infrastructure | Tweet about future of payments | $500K-$2M |

## Output CSV Format

The output CSV contains **dual perspective** results:

| Column | Description |
|--------|-------------|
| `row_index` | Original row identifier for tracking |
| `personalization_line_founder_a` | 1-2 sentence line from Founder A's perspective (ex-BigTech ML Lead) |
| `personalization_reason_founder_a` | 2-3 sentence explanation for Founder A's approach |
| `personalization_line_founder_b` | 1-2 sentence line from Founder B's perspective (agency operator, ex-Amazon) |
| `personalization_reason_founder_b` | 2-3 sentence explanation for Founder B's approach |

**Example Output:**

| row_index | personalization_line_founder_a | personalization_line_founder_b |
|-----------|----------------------------|---------------------------|
| 1 | "You wrote 'best AI tools execute, not recommend' — I led Gemini ML at Google, saw how complex systems coordinate at scale, that's what we're building for marketing teams." | "You wrote 'best AI tools execute, not recommend' — I ran an agency for 2 years, watched clients drown in tools that only suggest, built agents that actually run campaigns." |

## Column Filtering Logic

The runner supports flexible column filtering using allow/deny lists:

### How It Works

1. **`row_index` is always excluded** from context (used only for tracking)
2. **Deny list takes precedence**: If a column is in `--deny-cols`, it's excluded (even if in allow list)
3. **Allow list defines whitelist**: If `--allow-cols` is specified, only those columns are included (unless denied)
4. **Default behavior**: If no filters specified, all columns except `row_index` are included

### Examples

```bash
# Include ONLY these columns
--allow-cols "investor_name,firm_name,investment_thesis"

# Exclude these columns (include everything else)
--deny-cols "email,phone,internal_notes"

# Combine: include specific columns BUT exclude some
--allow-cols "investor_name,firm_name,recent_investments,email,phone" \
--deny-cols "email,phone"
# Result: Only investor_name, firm_name, recent_investments are included
```

## Context Format

The workflow builds context in markdown format:

```markdown
# investor_name:
John Smith

# firm_name:
Acme Ventures

# recent_investments:
TechCo (AI-powered analytics), DataFlow (data infrastructure)

# investment_thesis:
Seed-stage B2B SaaS focusing on developer tools and infrastructure

# linkedin_activity:
Recently posted about the future of AI in developer workflows

# typical_check_size:
$1M-$3M at seed
```

This format helps the LLM parse structured data and generate better personalization.

## Founder/Company Context

The `--founder-company-context` parameter allows you to provide additional information that applies to ALL investors in the batch.

### Default Context: Low-Fidelity Memo

**By default**, the runner automatically loads the content from `Low-Fidelity Memo.md` in the same directory as the runner. This memo contains:
- Current company state (5 B2B customers, $10K ACV, private beta)
- Specific traction metrics (50% gross margins, 40% faster by month 3)
- Product positioning and differentiators
- Founder backgrounds and expertise
- Vision and fundraising context

**Why this matters:**
- The framework prompts emphasize using provided facts over generic examples
- Ensures concrete, factual claims in all personalization lines
- Maintains consistency across all outreach

### Custom Context

You can override the default by providing your own context:

```bash
python personalization_runner.py \
    --input investors.csv \
    --output personalized.csv \
    --founder-company-context "We just hit 10 active customers. Our agents coordinated 150+ campaigns in the last 3 months. Recent launch: persistent memory system for brand voice."
```

**Or use an empty string to disable context entirely:**
```bash
python personalization_runner.py \
    --input investors.csv \
    --output personalized.csv \
    --founder-company-context ""
```

### What to Include

Good founder/company context includes:
- **Recent traction/milestones**: "We just hit 10 active customers" or "Closed $500K in ARR this quarter"
- **Product updates**: "Recent launch: persistent context system for brand voice"
- **Team updates**: "Expanded to 5 engineers, shipping weekly"
- **Specific facts to emphasize**: Concrete metrics and achievements

**Note**: Keep it factual. The LLM is instructed to use facts from context, not make up claims.

## Batch Processing

The runner automatically splits large CSVs into batches and processes them with configurable parallelism.

### Configuration Options

| Flag | Default | Description |
|------|---------|-------------|
| `--batch-size` | 200 | Number of rows per batch |
| `--batch-parallelism-limit` | 1 | Max concurrent batches (parallel mode) |
| `--sequential` | False | Run batches sequentially instead of parallel |
| `--delay` | 60 | Delay in seconds between sequential batches |
| `--start-row` | 0 | Starting row index (0-based, after header) |
| `--end-row` | None | Ending row index (exclusive, processes all if not set) |
| `--founder-company-context` | Low-Fidelity Memo.md | Additional context about founders/company (loaded from memo file) |
| `--allow-cols` | None | Whitelist specific columns for context |
| `--deny-cols` | None | Blacklist specific columns from context |

### Batch Output

Batch results are saved to `personalization_batches/batch_001.csv`, `batch_002.csv`, etc.

These are automatically combined into the final output file, but preserved for debugging/inspection.

## Cost & Performance Estimates

- **Model**: GPT-4.1 (gpt-5 alias)
- **Output**: 2 personalization lines per investor (Founder A + Founder B perspectives)
- **Cost**: ~$0.01-0.02 per row (both perspectives included)
- **Time**: ~10-15 seconds per batch of 20 rows (sequential)
- **Concurrency**: Supports parallel batch processing for faster throughput

**Example**: 1,000 investors
- Cost: ~$10-20
- Output: 2,000 personalization lines total (1,000 from Founder A, 1,000 from Founder B)
- Time: 
  - Sequential (1 batch at a time): ~50-75 minutes
  - Parallel (5 batches at a time): ~10-15 minutes

## Advanced Usage

### Combine Existing Batches

If you need to re-combine batch files without re-running the workflow:

```bash
python wf_testing/personalization_runner.py \
    --output personalized_investors.csv \
    --combine-only
```

### Test Run First

Process a small subset to validate configuration:

```bash
python wf_testing/personalization_runner.py \
    --input investors.csv \
    --output test_personalized.csv \
    --start-row 0 \
    --end-row 10
```

### High-Speed Processing

For large datasets, maximize parallelism:

```bash
python wf_testing/personalization_runner.py \
    --input investors.csv \
    --output personalized_investors.csv \
    --batch-size 50 \
    --batch-parallelism-limit 10
```

**Note**: Monitor for rate limits or system resource constraints.

## Personalization Quality Tips

To get the best personalization lines:

1. **Include rich context columns**:
   - Recent investments/portfolio companies
   - Investment thesis or focus areas
   - LinkedIn/Twitter activity
   - Blog posts or public statements
   - Geographic preferences
   - Stage preferences

2. **Use allow-list for focused personalization**:
   ```bash
   --allow-cols "recent_investments,investment_thesis,linkedin_activity,blog_posts"
   ```
   This helps the LLM focus on the most relevant signal.

3. **Exclude noisy or irrelevant columns**:
   ```bash
   --deny-cols "created_at,updated_at,internal_id,email,phone"
   ```

4. **Clean your data first**: Remove empty fields, ensure consistent formatting

## Workflow Architecture

The workflow follows a simple map-reduce pattern:

```
Input CSV
   ↓
Load & Build Context (with column filtering)
   ↓
Map: Distribute rows to workflow
   ↓
LLM: Generate personalization line + reasoning
   ↓
Format Output
   ↓
Collect Results
   ↓
Output CSV
```

Key nodes:
- **`route_investors_to_personalization`**: Map list router for parallel processing
- **`generate_personalization_prompt`**: Prompt constructor with context injection
- **`generate_personalization_llm`**: GPT-4.1 with structured output
- **`format_personalization_output`**: Code runner to format results

## Testing the Workflow

Test the workflow directly without the runner:

```bash
cd standalone_test_client
poetry run python kiwi_client/workflows/active/investor/investor_lead_scoring_sandbox/wf_investor_personalization.py
```

This runs a small test with 2 sample investors to verify everything works.

## Troubleshooting

### Issue: "No investors to process"
- **Solution**: Check that input CSV exists and has data
- Verify `--start-row` and `--end-row` range is valid

### Issue: Empty personalization lines
- **Solution**: Check that context is being built properly
- Review column filtering (allow/deny lists)
- Ensure input columns have actual data (not all NaN)

### Issue: Slow processing
- **Solution**: Increase `--batch-parallelism-limit`
- Reduce `--batch-size` for faster initial results
- Check network latency to API endpoint

### Issue: High costs
- **Solution**: Test on small subset first
- Consider using cheaper model (edit `wf_personalization_llm_inputs.py`)
- Filter columns to reduce context size

## Customization

### Change LLM Model

Edit `wf_personalization_llm_inputs.py`:

```python
PERSONALIZATION_MODEL_CONFIG = {
    "model": "gpt-4o-mini",  # Cheaper option
    "temperature": 0.7,
    "max_tokens": 1000,
    "reasoning_effort": "low",
}
```

### Modify Prompts

Edit the system/user prompts in `wf_personalization_llm_inputs.py` to change personalization style or focus.

### Adjust Output Schema

Modify `PersonalizationOutput` in `wf_personalization_llm_inputs.py` to add/remove fields.

## Integration with Other Workflows

This workflow is designed to complement the lead scoring workflow:

1. **Score investors** using `wf_investor_rescoring.py`
2. **Generate personalization** using `wf_investor_personalization.py`
3. **Merge results** using utility scripts (e.g., `join_sheets.py`)

Example pipeline:
```bash
# Step 1: Score check sizes
python wf_testing/rescore_runner.py --input investors.csv --output scored_investors.csv

# Step 2: Generate personalization
python wf_testing/personalization_runner.py --input investors.csv --output personalized.csv

# Step 3: Join results
python util_scripts/join_sheets.py --left scored_investors.csv --right personalized.csv --output final.csv
```

## Questions?

Refer to the main workflow documentation in the repository or check:
- `ONBOARDING_WORKFLOW_TESTING.md` for general workflow patterns
- `CLAUDE.md` for project conventions and best practices











# Personalization Framework


# VC/Angel Personalization Framework

## Core Principle
Match their stated thesis to your reality in 1-2 sentences. No fluff, no made-up facts, just their words → your proof.

---

## INPUT REQUIREMENTS

### About Them (Required):
- Recent investments (last 12-18 months)
- Public statements: tweets, blog posts, podcast quotes
- Portfolio patterns: stage, sector, founder types
- Specific pain points they've mentioned

### About You (Required):
- **Who's sending:** Founder B or Founder A (critical for "I/my" references)
- **Founder backgrounds:**
  - Founder A: ex-BigTech ML Lead, ex-Top Engineering University
  - Founder B: agency operator, ex-Amazon
- Company positioning (multi-agent marketing, AEO focus, intelligence-to-action gap)
- Product reality (what agents actually do, what workflows actually run)
- Actual traction/milestones (only if you provide them)

### Key Themes About KiwiQ (Use When Relevant):
- AI × human collaboration
- Foundational marketing infrastructure
- Multi-agent orchestration
- Answer Engine Optimization (AEO)
- Marketing coordination/workflow problems
- Intelligence-to-action gap
- Category creation & market education

---

## CRITICAL RULES

### ❌ NEVER:
- **Make up statistics or metrics** ("40% of traffic", "10x faster", "50% reduction")
- Reference specific customers by name
- Invent traction numbers
- Create fake testimonials or results
- Use adjectives without proof (innovative, revolutionary, cutting-edge, game-changing, world-class, groundbreaking, next-generation, transformative, disruptive)
- Write more than 2 sentences
- Use generic compliments
- **Confuse whose background you're referencing** (if Founder B sends, don't say "my Google background")

### ✅ ALWAYS:
- Use only facts explicitly provided in inputs
- Quote their exact words when possible
- Lead with them, end with you
- If mentioning customers, say "our customers" not brand names
- Keep it to the point
- Make every word count
- **Reference the correct sender's background** (Founder B = agency/Amazon, Founder A = Google/IIT)

---

## FRAMEWORK (Ranked by Importance)

## 1. THESIS ALIGNMENT ⭐⭐⭐ (Most Important)

**What It Is:** Match their stated investment belief to your company reality.

**Formula:** `[What they said/wrote] → [Your concrete proof]`

**When to Use:** They have clear public statements about market direction, product philosophy, or investment thesis.

**How to Find Their Thesis:**
- Recent blog posts or memos
- Twitter threads about market shifts
- Podcast appearances
- "Why we invested in..." posts
- Fund announcements

### ✅ GOOD EXAMPLES:

1. "You wrote marketing AI needs to execute, not just suggest — our agents run full campaigns, not Slack you recommendations."

2. "You tweeted 'agents need to replace dashboards' — we built multi-agent workflows that coordinate marketing launches end-to-end."

3. "You said LLMs need memory for business contexts — we built persistent context so agents remember brand voice across months."

4. "Your post about 'insight-to-action gap' — exactly what we solve with agents that turn briefs into launched work."

5. "You backed agents for sales — marketing has the same problem but 10x more tools to coordinate."

### ❌ BAD EXAMPLES:

1. "I love your thesis on AI transformation and think we align perfectly with your vision." (says nothing)

2. "Your innovative approach to AI investing resonates with our revolutionary platform." (buzzword soup)

3. "We're disrupting marketing automation with next-generation agentic infrastructure." (no connection to them)

4. "I noticed you invest in AI and believe we'd be a great fit for your portfolio." (generic)

5. "Your forward-thinking perspective on AI-powered solutions is what we're building." (empty flattery)

---

## 2. PORTFOLIO PATTERN ⭐⭐

**What It Is:** Show how you're the logical next step from their existing investments.

**Formula:** `[Their portfolio company] solved X, we solve the next problem Y`

**When to Use:** You can draw a clear line from what they've backed to what you're building.

**How to Find Patterns:**
- Look at their portfolio page
- Identify 2-3 recent similar investments
- Find the gap between those investments and your space

### ✅ GOOD EXAMPLES:

1. "You backed Jasper for content creation — we handle what comes after: coordinating that content into campaigns."

2. "Notion gave teams docs, we give them agents that turn docs into executed work."

3. "You invested in [analytics tool] — we're the layer that takes those insights and runs campaigns."

4. "Your portfolio has 3 content tools — we're the orchestration layer that makes them work together."

5. "You backed sales agents — marketing needs the same but for coordinating 5x more channels."

### ❌ BAD EXAMPLES:

1. "I see you have an amazing portfolio of innovative companies and we'd be complementary." (vague)

2. "Your investments in X, Y, and Z show your sophisticated understanding of SaaS." (ass-kissing)

3. "We'd fit perfectly alongside your other groundbreaking AI investments." (no specificity)

4. "Looking at your impressive portfolio, we share a vision for transforming marketing." (empty)

5. "You've built a world-class portfolio and we'd be honored to join." (begging)

---

## 3. CATEGORY CREATION EMPATHY ⭐⭐

**What It Is:** Connect their portfolio companies creating new categories to the GTM challenge you solve or face.

**Formula:** `[Their portfolio creates new categories] → [They need storytelling/education, which is our domain]`

**When to Use:** Their portfolio has companies building novel/complex products that require market education (dev tools, infrastructure, new AI categories, etc.)

**How to Identify:**
- Portfolio companies that don't fit existing buckets
- "First-of-its-kind" positioning in their announcements
- Companies defining new terms/categories
- Technical products requiring buyer education

**Two Angles:**
1. **We solve this for them:** Your product helps category creators with marketing
2. **We face this too:** You understand this challenge because you're category creating

### ✅ GOOD EXAMPLES:

1. "You backed [dev tool] and [infrastructure co] — both carving out new categories, both needing to nail storytelling before anyone understood the problem."

2. "Your portfolio has 3 companies defining new categories — they all need great content engines, that's what we built."

3. "You invest in category creators like [X] — you know they need marketing that educates, not just promotes, which is what our system does for our customers."

4. "You backed [complex product] — probably spent months explaining what it does. We're solving that education problem for technical products."

5. "As an investor in [technical infrastructure co], you've seen how hard it is to explain new primitives — we're building the marketing layer for that."

### ❌ BAD EXAMPLES:

1. "Your portfolio companies are innovative and would benefit from our revolutionary marketing platform." (generic)

2. "I know your investments face complex go-to-market challenges and we can help transform their approach." (consultant speak)

3. "As someone who invests in groundbreaking companies, you understand the importance of world-class marketing." (buzzwords)

4. "Your portfolio needs better storytelling and that's exactly what we provide." (presumptuous)

5. "I'm sure you appreciate how critical marketing is for category creation in today's landscape." (obvious filler)

---

## 4. FOUNDER BACKGROUND FIT ⭐⭐

**What It Is:** Match their stated founder criteria to your actual backgrounds.

**Formula:** `[What they look for] → [Sender's specific proof OR both founders' proof]`

**When to Use:** They've written about founder qualities, not just market or product.

**What to Reference Based on Sender:**

**If Founder B sends:**
- "I ran a content agency..."
- "I saw the coordination problem firsthand..."
- "I'm ex-Amazon, saw how..."
- "Founder A (my co-founder) led Gemini ML at Google..."

**If Founder A sends:**
- "I led Gemini ML at Google..."
- "I'm ex-Top Engineering University..."
- "I shipped models to 100M+ users..."
- "Founder B (my co-founder) ran an agency and saw..."

### ✅ GOOD EXAMPLES:

**If Founder B sends:**
1. "You look for operators who saw the problem — I ran a content agency for 6 months, watched clients drown in tool chaos."
2. "Your memo says 'domain experts who code' — I ran a content agency for 6 months, Founder A built production ML at Google."
3. "You back second-time operators — I ran 50+ client campaigns, learned the orchestration gaps before building."
4. "You wrote you want speed — I went from agency insights to product with Founder A (ex-BigTech ML) in 6 months."
5. "You said you bet on technical + domain expertise — Founder A's Gemini ML, I ran a content agency, we lived both sides."

**If Founder A sends:**
1. "You look for technical founders — I led Gemini ML at Google, shipped to 100M+ users."
2. "Your memo says 'researchers who ship' — I published ML papers and shipped Gemini features."
3. "You back xooglers — I'm from Gemini team, Founder B ran an agency, we combined ML + domain expertise."
4. "You wrote you want IIT founders who can execute — Top Engineering University, built production systems at Google, now shipping agents."
5. "You said you bet on technical depth — I built LLM infrastructure at Google, saw how complex coordination should work."

### ❌ BAD EXAMPLES:

1. "We're passionate entrepreneurs with strong backgrounds and proven track records." (resume speak)

2. "Our team brings world-class expertise in AI, marketing, and enterprise software." (generic)

3. "We have an exceptional founding team with deep industry experience." (says nothing)

4. "As experienced founders, we understand the challenges of building companies." (filler)

5. "Our complementary skill sets position us uniquely to execute on this vision." (buzzwords)

---

## 5. PERSONAL CONNECTION ⭐

**What It Is:** Shared background that's relevant to the problem you're solving.

**Formula:** `[Shared background] → [Why it matters for this company]`

**When to Use:** They're ex-Google, ex-IIT, ex-Amazon, or have clear affinity for certain founder profiles.

**What You Can Use Based on Sender:**

**If Founder B sends:**
- Ex-Amazon connection (if they are too)
- Agency operator background
- Reference Founder A as "my co-founder is ex-Google/IIT"

**If Founder A sends:**
- Ex-Google connection
- Ex-IIT connection
- Reference Founder B as "my co-founder ran an agency"

### ✅ GOOD EXAMPLES:

**If Founder B sends:**
1. "You're ex-Amazon — so am I. Saw how rigid launch processes broke, we're making them flexible with agents."
2. "You backed 3 agency operators turned founders — same path, learned coordination problems can't be solved with more tools."
3. "Founder A (my co-founder) is ex-BigTech ML — we're bringing BigTech-level launch coordination to marketing teams."
4. "Fellow ex-Amazon — you know how cross-functional launches work at scale, that's what we're building for marketing."
5. "You invest in operator-turned-founders — I ran an agency before this, saw the problem for 2 years before building."

**If Founder A sends:**
1. "Fellow xoogler — I saw how Google coordinates thousands of launches, bringing that to marketing teams."
2. "You backed 3 IIT founders — I'm Top Engineering University, built this after seeing marketing teams drown in tools."
3. "You're ex-Google — you know how complex coordination works at scale, that's what marketing teams need."
4. "You invested in 2 xooglers last year — I'm from Gemini team, building marketing's version of internal tools."
5. "Fellow IITian — you know the technical depth that takes, applying it to multi-agent orchestration for marketing."

### ❌ BAD EXAMPLES:

1. "I noticed we both went to top schools and thought we'd connect well." (irrelevant)

2. "As fellow members of the Google alumni network, I wanted to reach out." (networking fluff)

3. "We share similar backgrounds which creates natural synergy." (empty)

4. "Saw you went to [school] — I have friends there, small world!" (waste of words)

5. "We're both passionate about technology and innovation." (meaningless)

---

## TOP 10 OVERALL: GOOD ✅

1. "You wrote marketing AI needs to execute, not suggest — our agents run campaigns end-to-end, not Slack recommendations."

2. "You backed Jasper for content creation — we solve what comes after: coordinating that content into multi-channel campaigns."

3. "You invest in category creators like [X] — you know they need marketing that educates, not just promotes, that's what our system does for our customers."

4. "Your tweet about agents replacing dashboards — we built multi-agent workflows that coordinate marketing launches with no human handoffs."

5. **[If Founder A sends]** "You look for technical founders — I led Gemini ML at Google, shipped to 100M+ users."  
   **[If Founder B sends]** "You look for operators who saw the problem — I ran an agency for 2 years, watched clients drown in tool chaos."

6. "You said LLMs need memory for business contexts — we built persistent context so agents remember brand voice across campaigns."

7. **[If Founder A sends]** "Fellow xoogler — I saw how Google coordinates thousands of launches, bringing that to marketing teams."  
   **[If Founder B sends]** "You're ex-Amazon — so am I. Saw how rigid launch processes broke, we're making them flexible with agents."

8. "You backed [dev tool] and [infrastructure co] — both carving out new categories, both needing to nail storytelling first."

9. "Your post about 'insight-to-action gap' — exactly what we solve with agents that turn briefs into launched campaigns."

10. "You invested in [analytics co] for insights — we're the execution layer that takes those insights and runs campaigns automatically."

---

## TOP 10 OVERALL: BAD ❌

1. "I greatly admire your innovative portfolio and forward-thinking investment thesis in the AI space."

2. "We're building a revolutionary, next-generation platform disrupting marketing automation with cutting-edge AI."

3. "Your world-class portfolio of groundbreaking companies demonstrates your sophisticated understanding of enterprise transformation."

4. "As passionate entrepreneurs with proven track records, we're uniquely positioned to execute on this game-changing vision."

5. "I believe we share powerful synergy and alignment in our approach to solving complex marketing challenges."

6. "We'd be honored to explore how our innovative solution could complement your impressive portfolio of AI investments."

7. "Looking at your amazing investments, I think we'd be a perfect fit for your thesis on transformative technologies."

8. "I'm sure you appreciate how important great marketing is for category creation in today's complex landscape."

9. "Your portfolio companies face go-to-market challenges and we can help them with our revolutionary platform."

10. "Your visionary approach to investing resonates deeply with our mission to revolutionize marketing operations."

---

## DETAILED DOS AND DON'TS

### WRITING RULES:

**DO:**
- ✓ Write 1-2 sentences maximum
- ✓ Use their exact words in quotes when possible
- ✓ Lead with them, end with you
- ✓ Make it pass the "remove proper nouns" test
- ✓ Sound like you're continuing a conversation they started
- ✓ Use concrete terms (agents, workflows, campaigns, launches)
- ✓ Reference specific tweets, posts, or portfolio companies
- ✓ Only state facts you can prove
- ✓ **Match "I/my" to who's actually sending** (Founder B = agency/Amazon, Founder A = Google/IIT)

**DON'T:**
- ✗ Use multiple adjectives in a row
- ✗ Make up statistics, metrics, or traction numbers
- ✗ Name specific customers (say "our customers" if needed)
- ✗ Use these words: innovative, cutting-edge, revolutionary, game-changing, world-class, groundbreaking, next-generation, transformative, disruptive, visionary, exceptional, sophisticated, powerful
- ✗ Give generic compliments
- ✗ Explain things they already know
- ✗ Use emojis or exclamation marks
- ✗ Apologize or ask permission ("I hope this isn't too forward")
- ✗ **Say "I'm ex-Google" if Founder B is sending, or "I ran an agency" if Founder A is sending**

### RESEARCH PROCESS:

**Step 1: Gather Intel**
- Read their last 5 tweets or posts if available
- Find their most recent blog post or memo
- Check "portfolio" page for patterns
- Look for podcast appearances
- Note exact phrases they use
- Look for category-creating portfolio companies

**Step 2: Map to Your Reality**
- What have they said that you actually do?
- Which portfolio company is closest to you?
- Do they back category creators? (Can use section 3)
- What founder trait do they mention that you have?
- Is there a shared background?
- **Who's sending this email?** (Changes how you reference backgrounds)

**Step 3: Write & Test**
- Write the line
- **Check: Does the "I/my" match the sender?**
- Remove all proper nouns
- If it sounds generic, rewrite
- If you made up a fact, delete it
- If it's over 2 sentences, cut it

### THE SNIFF TEST:

Ask yourself:
- [ ] Could this line work for any AI company? (If yes, rewrite)
- [ ] Did I make up any numbers or claims? (If yes, delete them)
- [ ] Does this reference something specific they said/did? (If no, research more)
- [ ] Is this under 2 sentences? (If no, cut words)
- [ ] Would I roll my eyes if I received this? (If yes, start over)
- [ ] **Does "I/my" match who's actually sending?** (If no, fix it)

---

## TEMPLATE FOR YOUR TEAM

When creating personalization lines, fill this out first:

**Who's Sending:** [ ] Founder B [ ] Founder A

**Investor Name:**

**Their Thesis (exact quote):**

**Recent Portfolio Co (relevant):**

**Category Creators in Portfolio:**

**What They Look For in Founders:**

**Shared Background:**

**Our Angle:**
- [ ] Thesis match
- [ ] Portfolio evolution
- [ ] Category creation empathy
- [ ] Founder fit
- [ ] Personal connection

**Draft Line:**

**Test:** Remove "KiwiQ" and investor name. Does it still sound specific? Y/N

**Test:** Does "I/my" match the sender? Y/N

**Final Line:**

---

## EXAMPLES WITH INPUTS

### Example 1: Thesis Alignment (Sender: Founder B)

**Input Provided:**
- VC tweeted: "The best AI tools execute, not just recommend"
- KiwiQ: Multi-agent system that runs campaigns
- Sender: Founder B

**Output:**
"You tweeted 'best AI tools execute, not just recommend' — our agents run full campaigns, not Slack you suggestions."

---

### Example 2: Category Creation Empathy (Sender: Founder A)

**Input Provided:**
- VC backed: [Dev tool company] and [Infrastructure startup], both creating new categories
- KiwiQ helps technical products with market education
- Sender: Founder A

**Output:**
"You backed [dev tool] and [infrastructure co] — both defining new categories, both needing to nail storytelling before buyers understood the problem."

---

### Example 3: Founder Fit (Sender: Founder B)

**Input Provided:**
- VC's memo: "We look for operators who lived the problem"
- Founder B ran agency for 2 years
- Founder A: Google Gemini ML Lead
- Sender: Founder B

**Output:**
"You look for operators who lived the problem — I ran an agency for 2 years, Founder A built ML at Google, we saw coordination chaos from both sides."

---

### Example 4: Founder Fit (Sender: Founder A)

**Input Provided:**
- VC's memo: "We back technical founders from top labs"
- Founder A: Google Gemini ML Lead, Top Engineering University
- Sender: Founder A

**Output:**
"You back technical founders from top labs — I led Gemini ML at Google, Top Engineering University, shipped models to 100M+ users."

---

### Example 5: Personal Connection (Sender: Founder B)

**Input Provided:**
- VC is ex-Amazon
- Founder B is ex-Amazon
- Sender: Founder B

**Output:**
"Fellow ex-Amazon — you know how cross-functional launches work at scale, that's what we're building for marketing teams."

---

### Example 6: Personal Connection (Sender: Founder A)

**Input Provided:**
- VC is ex-Google
- Founder A is ex-BigTech ML
- Sender: Founder A

**Output:**
"Fellow xoogler — I saw how Google coordinates thousands of launches, bringing that orchestration to marketing teams."

---

## FINAL CHECKLIST BEFORE SENDING

- [ ] Is this 1-2 sentences?
- [ ] Did I quote their exact words?
- [ ] Did I avoid all buzzwords?
- [ ] Did I make up any facts? (If yes, DELETE)
- [ ] Does this sound like me, not ChatGPT?
- [ ] Would this work if I sent it to 10 different VCs? (If yes, make it more specific)
- [ ] Is there a concrete proof point?
- [ ] Did I lead with them, end with us?
- [ ] **Does "I/my" match who's sending?** (Founder B = agency/Amazon, Founder A = Google/IIT)

**If all checks pass → send it.**
**If any check fails → rewrite it.**


