"""
LLM Inputs for Investor Lead Scoring Workflow

This module supports two scoring frameworks:
1. VC Framework: For institutional VC fund partners (100-point system)
2. Angel Framework: For individual angel investors (105-point system, normalized to 100)

**Framework Selection:**
Set ACTIVE_FRAMEWORK = "VC" or "ANGEL" to switch between frameworks.

**VC Scoring System:**
- Total: 100 points
- Categories: Fund Vitals (25), Lead Capability (25), Thesis Alignment (30), Partner Value (15), Strategic Factors (5)
- Disqualification: Fund AUM < $20M
- Tiers: A (85-100), B (70-84), C (50-69), D (<50)

**Angel Scoring System:**
- Total: 105 points raw, normalized to 100
- Categories: Employer Brand (25), Functional Expertise (25), VC Network (20), Check Activity (20), Shared Affinity (15)
- No disqualification criterion
- Tiers: A (75-100), B (60-74), C (40-59), D (<40)
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# ========================================
# FRAMEWORK SELECTION - CHANGE THIS TO SWITCH FRAMEWORKS
# ========================================

ACTIVE_FRAMEWORK: Literal["VC", "ANGEL"] = "ANGEL"  # Set to "VC" or "ANGEL"


# ========================================
# Common LLM Model Configurations (used by both frameworks)
# ========================================

# LinkedIn URL Finder (Perplexity Sonar)
LLM_PROVIDER_URL_FINDER = "perplexity"
LLM_MODEL_URL_FINDER = "sonar-pro"
LLM_TEMPERATURE_URL_FINDER = 0.3
LLM_MAX_TOKENS_URL_FINDER = 1000

# Deep Research (Perplexity Sonar Deep Research)
LLM_PROVIDER_DEEP_RESEARCH = "perplexity"
LLM_MODEL_DEEP_RESEARCH = "sonar-deep-research"  # sonar-deep-research  sonar-pro
# LLM_MODEL_DEEP_RESEARCH = "sonar-pro"
LLM_TEMPERATURE_DEEP_RESEARCH = 0.3
LLM_MAX_TOKENS_DEEP_RESEARCH = 16000  # 16000  8000
LLM_DEEP_RESEARCH_REASONING_EFFORT = "low"
LLM_DEEP_RESEARCH_SEARCH_CONTEXT_SIZE = "low"

# Structured Extraction (Claude Sonnet / GPT-5)
LLM_PROVIDER_EXTRACTION = "openai"  # anthropic
LLM_MODEL_EXTRACTION = "gpt-5"  # claude-sonnet-4-5-20250929
LLM_TEMPERATURE_EXTRACTION = 0.1
LLM_MAX_TOKENS_EXTRACTION = 16000
LLM_EXTRACTION_REASONING_EFFORT = "low"
VERBOSITY_EXTRACTION = "high"

LLM_PROVIDER_PERSONALIZATION = "anthropic"
LLM_MODEL_PERSONALIZATION = "claude-sonnet-4-5-20250929"
LLM_TEMPERATURE_PERSONALIZATION = 0.3
LLM_MAX_TOKENS_PERSONALIZATION = 500
# LLM_PERSONALIZATION_REASONING_EFFORT = "low"

# ========================================
# LinkedIn URL Finder Configuration (Common to both frameworks)
# ========================================

LINKEDIN_URL_FINDER_SYSTEM_PROMPT = """You are an expert at finding LinkedIn profiles for investors using web search.

Your task is to find the correct LinkedIn URL for a given investor based on their name and firm information.

**IMPORTANT CONTEXT:**
- The investor may have switched firms since the input data was collected
- Search broadly if you don't find them at the provided firm
- Prioritize recent, verified information
- Only return a URL if you have high confidence it's the correct person

**SEARCH STRATEGY:**

1. **Primary Search:**
   - Search: "<name> <firm_company> LinkedIn"
   - Look for exact name match with venture capital role

2. **If Not Found at Input Firm:**
   - The investor may have moved to a different fund
   - Search more broadly: "<name> venture capital LinkedIn"
   - Search: "<name> general partner LinkedIn"
   - Look for recent announcements or profile updates

3. **Verification Checks:**
   - Verify the person is in venture capital/investing
   - Check if title matches VC roles (Partner, GP, Managing Partner, Principal, VP, etc.)
   - Look for recent activity to confirm profile is active
   - If they moved firms, note the current firm name

4. **Output Requirements:**
   - Provide the full LinkedIn profile URL (e.g., https://www.linkedin.com/in/username)
   - Indicate confidence level (high/medium/low)
   - If investor changed firms, note the current firm
   - If you cannot find it, return empty URL with explanation

**Be thorough but accurate. Only return a URL if you're confident it's the correct investor.**
"""

LINKEDIN_URL_FINDER_USER_PROMPT = """Find the LinkedIn profile URL for the following investor:

**Investor Information:**
Name: {first_name} {last_name}
Title (from input): {title}
Current Firm (from input): {firm_company}
Investment Criteria: {investment_criteria}
Notes: {notes}
"""

class LinkedInURLFinderOutput(BaseModel):
    """Output schema for LinkedIn URL finder."""
    reason_and_evidence: str = Field(default="", description="Brief reason and evidence for the LinkedIn URL found, or empty string if not found with confidence")
    linkedin_url: str = Field(description="The LinkedIn profile URL found, or empty string if not found with confidence")
    current_firm_if_changed: str = Field(default="", description="Current firm name if the investor moved from the input firm, empty otherwise")
    confidence: Literal["high", "medium", "low"] = Field(description="Confidence level in the found URL")

# Generate JSON Schema from Pydantic Model
LINKEDIN_URL_FINDER_OUTPUT_SCHEMA = LinkedInURLFinderOutput.model_json_schema()


# ================================================================================
# VC FRAMEWORK: Deep Research & Extraction Prompts and Schemas
# ================================================================================

# ========================================
# VC Framework: Step 1 - Deep Research Configuration
# ========================================

VC_STEP1_DEEP_RESEARCH_SYSTEM_PROMPT = """You are an expert venture capital researcher specializing in comprehensive fact-gathering on seed-stage investors.

Your task is to conduct thorough, factual research on VC investors, funds, and partners. You are gathering data for downstream scoring and analysis - focus on facts, numbers, dates, and specific examples.

**Research Areas:**

**1. FUND VITALS**
- Fund size (AUM) - find exact numbers in $M
- Recent investment activity: List specific deals in 2024-2025 with dates
- Fund stage/number (Fund I, II, III, etc.)
- Latest fund raise date

**2. LEAD CAPABILITY**
- Does fund lead seed rounds? Find examples of rounds they "led" or were "lead investor"
- List seed rounds led in 2024-2025 with company names, dates, round sizes
- Typical check size at seed stage - find specific amounts
- Co-lead vs sole lead behavior

**3. THESIS ALIGNMENT & PORTFOLIO**
- List AI B2B companies in portfolio with dates
- List MarTech companies in portfolio with dates
- List DevTools/API/PLG companies with dates
- Extract investment thesis statements (use exact quotes)
- Portfolio composition by sector

**4. PARTNER VALUE**
- Partner's exact title at current firm
- Previous roles: Was partner ex-founder? Ex-CMO? Ex-VP Marketing? Ex-VP Sales?
- Companies worked at before VC
- Board seats (list company names)
- Public activity: Twitter/LinkedIn follower count, recent posts/content
- Specific value-add examples with numbers (e.g., "Introduced 15 candidates")

**5. STRATEGIC FACTORS**
- Fund HQ location (city, country)
- Recent exits (last 3 years) - company names, exit type, dates
- Fund deployment stage - how much capital deployed?
- Portfolio follow-on activity

**6. ACTIONABLE INTELLIGENCE**
- Recent public statements, tweets, blog posts (with dates and quotes)
- Investment pace and process details
- Deal preferences and traction requirements
- Co-investors they work with frequently

**CRITICAL INSTRUCTIONS:**
- Provide SPECIFIC examples with DATES and NUMBERS
- Use exact quotes when citing thesis statements or partner views
- Don't summarize - provide raw facts for scoring
- If data not found, explicitly state "Information not found"
- Be comprehensive and thorough

**⚠️ CRITICAL FIRST STEP - VERIFY CURRENT FIRM:**

**0. CURRENT EMPLOYMENT VERIFICATION** (DO THIS FIRST):

**SEARCH STRATEGY** (follow this order for best results):

IMPORTANT NOTE: it may be possible that provided linkedin profile / url is actually from a different person, so you need to be careful and verify that the profile / url belongs to the person you are looking for.

**Step 0a: Use LinkedIn Scraped Data (MOST RELIABLE if available)**
   - If LinkedIn scraped data is provided (<linkedin_scraped_profile>), use it as PRIMARY source:
     * Check the "position" array for current employment
     * Look for the position with no end date or most recent start date
     * Extract: current company name, current title, start date
     * This is the MOST ACCURATE source - no need to web search for current employment

**Step 0b: LinkedIn URL Search (SECOND MOST RELIABLE)**
   - If LinkedIn scraped data NOT available but LinkedIn URL provided, use it as PRIMARY source:
     * Extract LinkedIn username from URL (e.g., "/in/ohsu" → search "ohsu linkedin")
     * Search: "site:linkedin.com/in/<username>" OR "<username> linkedin current"
     * LinkedIn profiles are most up-to-date for current employment

   **LinkedIn Name Variations**: Partners may use different names on LinkedIn vs input:
   - LinkedIn might show: Nickname, middle name, different spelling
   - Example: "ABCDEF XYZ" might be "ABC H. XYZ" (first name shortened for eg) on LinkedIn
   - **Trust the LinkedIn profile name** if URL is valid

**Step 0c: Verify if Still at Input Firm (SPECIFIC SEARCH)**
   - Search: "<name> <firm_company>" OR "<linkedin_username> <firm_company>"
   - Look for recent activity at input firm: press releases, announcements, fund website
   - Check firm's team page: Is partner still listed?
   - Search: "site:<fund_website>" AND "<partner_name>"

**Step 0d: Find Current Firm if Changed (GENERAL SEARCH)**
   - If Step 0c shows partner NOT at input firm anymore:
   - Search: "<name> venture capital" OR "<linkedin_username> VC current"
   - Search: "<name> general partner" OR "managing partner"
   - Look for recent announcements, news, new fund announcements
   - Check: "<partner_name> joins" OR "<partner_name> moved to"

**EDGE CASES TO HANDLE:**
   - If LinkedIn URL doesn't work (404, outdated): Fall back to name searches
   - If partner name yields multiple people: Use title/fund context to disambiguate
   - If input fund name is an alias (e.g., "a16z" vs "Andreessen Horowitz"): Search both variations
   - If partner is between firms (recently left, not yet announced new role): State "In transition"

**WHAT TO EXTRACT:**
   - **Current fund/firm name**: Use the FULL official name (e.g., "Andreessen Horowitz" not "a16z")
   - **Current title**: Exact title from most recent source (LinkedIn or firm website)
   - **Is still at input firm?**: Boolean - Does current firm match <firm_company>? (be smart about aliases)
   - **Firm change detected?**: Has partner moved to a different fund?
   - **Firm change details**: If moved, provide: "Moved from <Old Fund> to <New Fund> in <Month Year>. <Context if available>"
   - **Still in VC?**: Is partner still active in venture capital, or moved to startup/retired/other?
   - **Employment notes**: Any relevant context (e.g., "Recently promoted to GP", "On sabbatical", "Now at portfolio company")

**IMPORTANT INSTRUCTIONS**:
   - **Prioritize LinkedIn scraped data FIRST** (if provided) - it's the most accurate and up-to-date
   - Second priority: LinkedIn URL searches (more reliable than name searches, handles name variations)
   - If partner moved firms: ALL subsequent research should focus on the NEW current firm
   - Be smart about VC name matching: "Sequoia Capital" = "Sequoia" = "Sequoia VC"
   - If partner is no longer in VC, note it but still research their last VC firm for context
   - If you can't determine current employment with confidence, state "Unable to verify - limited public data"

---

**RESEARCH FRAMEWORK** (aligned with 100-point scoring system):

**1. FUND VITALS** (data for 0-25 points):
   - **Fund Size (AUM)**: Find exact amount in $M (search: "[Fund] AUM", "[Fund] crunchbase fund size")
   - **Recent Activity 2024-2025**: List specific deals with dates (search: "[Fund] invests 2025", "[Fund] portfolio 2024")
     * Count deals in 2025 vs 2024 only
     * Provide company names, dates, round types
   - **Fund number**: Fund I, II, III, etc.
   - **Latest fund raise date**

**2. LEAD CAPABILITY** (data for 0-25 points):
   - **Lead Behavior**: Find examples where fund "led" seed rounds (search: "[Fund] led seed 2024 OR 2025")
     * List seed rounds LED with: company name, date, round size
     * Note if they co-lead vs sole lead
     * Pattern: regularly leads, co-leads, mostly participates, or unclear
   - **Check Size at Seed**: Find typical check amounts (search: "[Fund] check size seed", "[Fund] investment amount")
     * Look for $500K-$1M, $1M-$3M, $3M-$5M ranges
     * Provide specific examples with amounts

**3. THESIS ALIGNMENT & PORTFOLIO** (data for 0-30 points):
   - **AI B2B Companies**: Count and list portfolio companies (search: "site:[fund-site.com] portfolio AI B2B")
     * Need 3+ for maximum points
     * Include company names and investment dates
   - **MarTech Companies**: Count and list portfolio companies
     * Need 2+ for points
     * Include company names and dates
   - **Explicit AI/B2B Thesis**: Find thesis statements (search: "[Fund] thesis AI MarTech", "[Fund] investment focus")
     * Use exact quotes from fund website or partner statements
   - **Focus Areas** (additive):
     * Dev tools/API companies in portfolio? List them
     * PLG (Product-Led Growth) focus? Find evidence in thesis or portfolio

**4. PARTNER VALUE** (data for 0-15 points):
   - **Title at Current Firm**: Exact title
     * Managing Partner/GP, Principal/VP, Venture Partner, Associate, etc.
   - **Operational Background** (search: "[Partner] linkedin", "[Partner] CMO OR founder before:[fund]"):
     * Ex-Founder of MarTech/B2B company? Which company?
     * Ex-CMO or VP Marketing? Which company?
     * Ex-VP Sales or Growth? Which company?
     * Companies worked at before VC with roles
   - **Active Creator**: Blog, Twitter/X, LinkedIn content
     * Follower counts, posting frequency
     * Recent thought leadership examples

**5. STRATEGIC FACTORS** (data for 0-5 points):
   - **Geography**: Fund HQ location - city and country (search: "[Fund] location headquarters")
     * US-based? India-based? Other?
   - **Momentum** (pick one):
     * New fund raised in last 18 months? When?
     * Recent exits (2+ in last 3 years)? List companies, exit type, dates
     * Portfolio follow-on activity? Examples of funds following on in later rounds

**6. ACTIONABLE INTELLIGENCE** (for pitch prep - gather specific, actionable details):
   - **Portfolio Pattern**: Stage, traction levels, founder profiles they invest in
   - **Partner Insights**: Recent content, beliefs, what excites them (you may use their any kind of public posts / content!)
   - **Investment Pace & Process**: Deals per quarter, timeline, IC process
   - **Value-Add Evidence**: Specific examples with numbers (e.g., "Introduced 15 VP Marketing candidates in 2024")
   - **Deal Preferences**: Traction bar, team requirements, what they pass on
   - **Recent Positioning**: Thesis updates, market views from posts/tweets - capture exact language
   - **Fund Context**: Deployment stage, team changes, pressure/urgency
   - **Competitive Intel**: Portfolio overlaps, gaps, frequent co-investors
   - **Pitch Prep Details**: Specific portfolio companies or statements to reference, angle to use

**CRITICAL RULES:**
- ONLY disqualification criterion: Fund AUM < $20M (if found, state "DQ - Fund <$20M" and stop detailed research)
- Don't disqualify for: No leading history, no 2025 activity, portfolio overlaps
- Use SPECIFIC examples with DATES and NUMBERS
- Use exact QUOTES for thesis statements and partner views
- If data not found, state "Information not found" explicitly

Provide comprehensive, factual research with specific details and evidence for downstream scoring.
"""

VC_STEP1_DEEP_RESEARCH_USER_PROMPT = """Research the following venture capital investor/partner for seed-stage fundraising evaluation:

**INVESTOR DETAILS PROVIDED:**
Partner Name: {first_name} {last_name}
Title (from input): {title}
Firm/Company (from input): {firm_company}
Investor Type: {investor_type}
Investor Role Detail: {investor_role_detail}
Relationship Status: {relationship_status}
LinkedIn URL: {linkedin_url}
Twitter URL: {twitter_url}
Crunchbase URL: {crunchbase_url}
Investment Criteria (from input): {investment_criteria}
Notes (from input): {notes}
Source: {source_sheets}

**LINKEDIN PROFILE DATA** (if available - most reliable source for current employment):
{linkedin_scraped_profile}
"""

# **LINKEDIN RECENT POSTS** (20 most recent posts - analyze for insights on partner's interests, thesis, recent activity):
# {linkedin_scraped_posts}

# ========================================
# VC Framework: Step 2 - Structured Extraction Configuration
# ========================================

VC_STEP2_EXTRACTION_SYSTEM_PROMPT = """You are an expert venture capital analyst specializing in investor scoring for seed-stage B2B AI/MarTech fundraising.

Your task is to analyze research data and produce a structured score (0-100) with actionable intelligence for pitch preparation.

**SCORING FRAMEWORK (100 points max):**

**A. FUND VITALS (0-25 pts)**
```
Fund Size:
  $200M-$500M = 15 pts
  $500M-$1B = 12 pts
  $100M-$200M = 10 pts
  $50M-$100M = 7 pts
  $20M-$50M = 5 pts
  <$20M = DQ (disqualified)

Activity (2024-2025):
  3+ deals in 2025 = 10 pts
  1-2 deals in 2025 = 7 pts
  Active in 2024 only = 4 pts
  No recent activity = 0 pts
```

**B. LEAD CAPABILITY (0-25 pts)**
```
Lead Behavior:
  Regularly leads = 15 pts
  Co-leads = 10 pts
  Mostly participates = 5 pts
  Unclear = 2 pts

Check Size:
  $1M-$3M = 10 pts
  $500K-$1M = 7 pts
  $3M-$5M = 8 pts
  Other = 3 pts
```

**C. THESIS ALIGNMENT (0-30 pts)**
```
Portfolio:
  3+ AI B2B companies = 12 pts
  2+ MarTech companies = 10 pts
  Explicit AI/B2B thesis = 8 pts

Focus (additive):
  Dev tools/API = +5 pts
  PLG focus = +5 pts
```

**D. PARTNER VALUE (0-15 pts)**
```
Title:
  Managing Partner/GP = 8 pts
  Principal/VP = 5 pts
  Venture Partner = 4 pts
  Associate = 2 pts

Background (additive):
  Ex-Founder (MarTech/B2B) = +4 pts
  Ex-CMO/VP Marketing = +4 pts
  Ex-VP Sales/Growth = +3 pts
  Active creator = +2 pts
```

**E. STRATEGIC FACTORS (0-5 pts)**
```
Geography:
  US-based = 3 pts
  India-based = 2 pts

Momentum (pick one):
  New fund <18mo = 2 pts
  2+ exits in 3 yrs = 2 pts
  Portfolio follow-ons = 2 pts
```

**TIER ASSIGNMENT:**
- A: 85-100 points (Top Priority)
- B: 70-84 points (High Priority)
- C: 50-69 points (Medium Priority)
- D: <50 points (Low Priority)

**CRITICAL RULES:**
- ONLY DQ if: Fund AUM < $20M
- Don't DQ for: No leading, no 2025 activity, portfolio overlaps
- Use specifics: Not "helps with hiring" but "Intro'd 15 VP Marketing candidates to portfolio in 2024"
- Special situations: Partner moved firms (research CURRENT firm), new fund <6mo (don't penalize for no 2025 deals)

Apply scoring rigorously based on evidence. Be conservative but fair.

**TASK:**

1. **Employment Verification** (DO THIS FIRST):
   - Determine partner's CURRENT firm (may have moved from input firm)
   - Use LinkedIn profile data as primary source for current employment
   - If partner moved, document the change and use CURRENT firm for all scoring

2. **Score Calculation** (100-point framework):
   - **Fund Vitals** (0-25 pts): Fund size + recent activity
   - **Lead Capability** (0-25 pts): Lead behavior + check size
   - **Thesis Alignment** (0-30 pts): Portfolio (AI B2B, MarTech) + thesis + focus (DevTools/API, PLG)
   - **Partner Value** (0-15 pts): Title + background (ex-founder, ex-CMO, ex-VP Sales, active creator)
   - **Strategic Factors** (0-5 pts): Geography + momentum
   - **Total**: Sum all categories (max 100)

3. **DQ Check**:
   - ONLY disqualify if Fund AUM < $20M
   - Calculate scores even if DQ'd

4. **Tier Assignment**:
   - A: 85-100 (Top Priority)
   - B: 70-84 (High Priority)
   - C: 50-69 (Medium)
   - D: <50 (Low)

5. **Actionable Intelligence** (9 sections from playbook):
   - Portfolio Pattern
   - Partner Insights (use LinkedIn posts!)
   - Investment Pace & Process
   - Value-Add Evidence
   - Deal Preferences
   - Recent Positioning (use exact language from posts/tweets)
   - Fund Context
   - Competitive Intel (portfolio gaps for AI B2B content/marketing tool)
   - Pitch Prep (reference, angle, opening)

**💡 HOW TO USE LINKEDIN POSTS DATA EFFECTIVELY:**

The LinkedIn posts provide valuable real-time insights into the partner's:
- **Recent Investment Thesis**: What topics are they posting about? (AI, MarTech, PLG, developer tools, etc.)
- **Current Interests**: What companies/trends are they sharing or commenting on?
- **Active Engagement**: Are they actively posting? Recent activity = fund is likely active
- **Portfolio Updates**: Announcements about new investments or portfolio milestones
- **Thought Leadership**: What are their views on AI, B2B SaaS, MarTech trends?
- **Value-Add Evidence**: Posts about helping portfolio companies, making intros, sharing resources
- **Recent Positioning**: Use their exact language and terminology in pitch prep

**ANALYZE POSTS FOR:**
1. Investment announcement posts (new deals, portfolio updates)
2. Thought leadership content (blog posts, threads on AI/B2B/MarTech)
3. Engagement patterns (what topics get their attention)
4. Specific quotes and statements (use exact language for pitch prep)
5. Recent activity level (posting frequency indicates fund activity)

**IMPORTANT INSTRUCTIONS:**
- Use LinkedIn profile data as PRIMARY source for current firm verification
- Use LinkedIn posts to understand partner's recent interests, thesis, and positioning
- For "Competitive Intel", specifically analyze portfolio gaps for AI B2B content/marketing tools
- Use SPECIFIC examples with DATES and NUMBERS
- Use exact QUOTES from posts for "Recent Positioning"
- If partner moved firms, document in structured output and score the CURRENT firm
- Be evidence-based - only score what you can verify
"""

VC_STEP2_EXTRACTION_USER_PROMPT = """Based on the research report and LinkedIn data, extract structured information and calculate a 0-100 lead score using the new scoring framework.

**INVESTOR INPUT DATA:**
Partner: {first_name} {last_name}
Title (from input): {title}
Firm (from input): {firm_company}
Investor Type: {investor_type}
Investment Criteria: {investment_criteria}
Notes: {notes}

**LINKEDIN PROFILE DATA:**
{linkedin_scraped_profile}

**DEEP RESEARCH REPORT:**
{deep_research_report}

**WEB SEARCH CITATIONS:**
{deep_research_citations}

**LINKEDIN POSTS DATA (20 recent posts):**
{linkedin_scraped_posts}
"""


# ========================================
# VC Framework: Pydantic Output Schema Models
# ========================================

class VC_PortfolioCompany(BaseModel):
    """Portfolio company details."""
    company_name: str = Field(description="Company name")
    sector: str = Field(description="Sector (e.g., 'AI B2B', 'MarTech', 'DevTools')")
    investment_date: Optional[str] = Field(default=None, description="Investment date if available")
    stage_at_investment: Optional[str] = Field(default=None, description="Stage at investment")

class VC_LedRoundExample(BaseModel):
    """Seed round led by the fund."""
    company_name: str = Field(description="Company name")
    date: str = Field(description="Round date")
    round_size: Optional[str] = Field(default=None, description="Total round size")
    fund_check_size: Optional[str] = Field(default=None, description="Fund's investment amount")
    source: Optional[str] = Field(default=None, description="Information source")

class VC_ExitDetails(BaseModel):
    """Portfolio exit details."""
    company_name: str = Field(description="Exited company name")
    exit_type: str = Field(description="Exit type (Acquisition, IPO, Unicorn)")
    exit_date: Optional[str] = Field(default=None, description="Exit date")
    acquirer_or_details: Optional[str] = Field(default=None, description="Acquirer or details")

class VC_FundVitalsScoring(BaseModel):
    """Fund vitals scoring (0-25 points)."""
    fund_size_usd: str = Field(description="Fund AUM in millions (e.g., '$300M', '$120M', 'Unknown')")
    fund_size_points: int = Field(ge=0, le=15, description="$200M-$500M=15, $500M-$1B=12, $100M-$200M=10, $50M-$100M=7, $20M-$50M=5")
    fund_size_reasoning: str = Field(description="Explanation of fund size scoring")

    recent_activity_2024_2025: str = Field(description="Recent investment activity details")
    deals_in_2025_count: int = Field(ge=0, description="Number of deals in 2025")
    deals_in_2024_count: int = Field(ge=0, description="Number of deals in 2024")
    activity_points: int = Field(ge=0, le=10, description="3+ deals in 2025=10, 1-2 in 2025=7, Active 2024 only=4, None=0")
    activity_reasoning: str = Field(description="Explanation of activity scoring")

    fund_number: Optional[str] = Field(default=None, description="Fund I, II, III, etc.")
    latest_fund_raise_date: Optional[str] = Field(default=None, description="Latest fund raise date")

    category_total: int = Field(ge=0, le=25, description="Fund Vitals total (fund_size_points + activity_points)")

class VC_LeadCapabilityScoring(BaseModel):
    """Lead capability scoring (0-25 points)."""
    lead_behavior: str = Field(description="Lead behavior pattern (Regularly leads, Co-leads, Mostly participates, Unclear)")
    led_rounds_count: int = Field(ge=0, description="Number of seed rounds led in 2024-2025")
    led_round_examples: List[VC_LedRoundExample] = Field(default_factory=list, description="Specific examples of led rounds")
    lead_behavior_points: int = Field(ge=0, le=15, description="Regularly leads=15, Co-leads=10, Mostly participates=5, Unclear=2")
    lead_behavior_reasoning: str = Field(description="Explanation of lead behavior scoring")

    typical_check_size: str = Field(description="Typical check size at seed (e.g., '$2M', '$500K-$1M', 'Unknown')")
    check_size_points: int = Field(ge=0, le=10, description="$1M-$3M=10, $500K-$1M=7, $3M-$5M=8, Other=3")
    check_size_reasoning: str = Field(description="Explanation of check size scoring")

    category_total: int = Field(ge=0, le=25, description="Lead Capability total (lead_behavior_points + check_size_points)")

class VC_ThesisFitScoring(BaseModel):
    """Thesis alignment scoring (0-30 points)."""
    # Portfolio analysis
    ai_b2b_portfolio_count: int = Field(ge=0, description="Number of AI B2B companies in portfolio")
    ai_b2b_companies: List[VC_PortfolioCompany] = Field(default_factory=list)
    ai_b2b_points: int = Field(ge=0, le=12, description="3+ companies=12pts, use judgment for 1-2")

    martech_portfolio_count: int = Field(ge=0, description="Number of MarTech companies in portfolio")
    martech_companies: List[VC_PortfolioCompany] = Field(default_factory=list)
    martech_points: int = Field(ge=0, le=10, description="2+ companies=10pts, use judgment for 1")

    # Thesis analysis
    has_explicit_ai_b2b_thesis: bool = Field(description="Has explicit AI/B2B investment thesis")
    investment_thesis_summary: str = Field(description="Summary of investment thesis with quotes")
    thesis_points: int = Field(ge=0, le=8, description="Explicit AI/B2B thesis=8pts")

    # Focus areas (additive)
    devtools_api_portfolio_count: int = Field(ge=0, description="Number of DevTools/API companies")
    devtools_api_companies: List[VC_PortfolioCompany] = Field(default_factory=list)
    has_devtools_api_focus: bool = Field(description="Has DevTools/API focus")
    devtools_api_points: int = Field(ge=0, le=5, description="DevTools/API focus=5pts")

    plg_portfolio_count: int = Field(ge=0, description="Number of PLG companies")
    plg_companies: List[VC_PortfolioCompany] = Field(default_factory=list)
    has_plg_focus: bool = Field(description="Has PLG (Product-Led Growth) focus")
    plg_points: int = Field(ge=0, le=5, description="PLG focus=5pts")

    thesis_alignment_reasoning: str = Field(description="Overall reasoning for thesis alignment scoring")
    category_total: int = Field(ge=0, le=30, description="Thesis Alignment total (sum of all thesis components, max 30)")

class VC_PartnerValueScoring(BaseModel):
    """Partner value scoring (0-15 points)."""
    # Title
    partner_title: str = Field(description="Exact title at current firm")
    decision_authority_level: Literal["Managing Partner/GP", "Principal/VP", "Venture Partner", "Associate", "Unknown"] = Field(description="Decision authority category")
    title_points: int = Field(ge=0, le=8, description="Managing Partner/GP=8, Principal/VP=5, Venture Partner=4, Associate=2")
    title_reasoning: str = Field(description="Explanation of title scoring")

    # Background (additive, max total from all backgrounds)
    operational_background_summary: str = Field(description="Summary of partner's pre-VC background")
    is_ex_founder_martech_b2b: bool = Field(description="Ex-Founder of MarTech/B2B company")
    founder_details: Optional[str] = Field(default=None, description="Which company, when")
    ex_founder_points: int = Field(ge=0, le=4, description="Ex-Founder MarTech/B2B=4pts")

    is_ex_cmo_vp_marketing: bool = Field(description="Ex-CMO or VP Marketing")
    cmo_marketing_details: Optional[str] = Field(default=None, description="Which company, when")
    ex_cmo_marketing_points: int = Field(ge=0, le=4, description="Ex-CMO/VP Marketing=4pts")

    is_ex_vp_sales_growth: bool = Field(description="Ex-VP Sales or Growth")
    vp_sales_growth_details: Optional[str] = Field(default=None, description="Which company, when")
    ex_vp_sales_points: int = Field(ge=0, le=3, description="Ex-VP Sales/Growth=3pts")

    is_active_creator: bool = Field(description="Active content creator (blog, Twitter, LinkedIn)")
    active_creator_details: Optional[str] = Field(default=None, description="Platform, following, frequency")
    active_creator_points: int = Field(ge=0, le=2, description="Active creator=2pts")

    background_total_points: int = Field(ge=0, le=7, description="Sum of background points (max 7 from additive categories)")
    background_reasoning: str = Field(description="Explanation of background scoring")

    category_total: int = Field(ge=0, le=15, description="Partner Value total (title_points + background_total_points, max 15)")

class VC_StrategicFactorsScoring(BaseModel):
    """Strategic factors scoring (0-5 points)."""
    # Geography
    fund_hq_location: str = Field(description="Fund HQ location (city, country)")
    geography_category: Literal["US", "India", "Other"] = Field(description="Geography category")
    geography_points: int = Field(ge=0, le=3, description="US-based=3pts, India-based=2pts")

    # Momentum (pick one best fit)
    has_new_fund_under_18mo: bool = Field(description="New fund raised in last 18 months")
    new_fund_details: Optional[str] = Field(default=None, description="Fund raise date and amount")

    has_recent_exits: bool = Field(description="2+ exits in last 3 years")
    exits_count_3yr: int = Field(ge=0, description="Number of exits in last 3 years")
    exit_details: List[VC_ExitDetails] = Field(default_factory=list)

    has_portfolio_followons: bool = Field(description="Portfolio companies raising follow-on rounds")
    followon_details: Optional[str] = Field(default=None, description="Examples of follow-on activity")

    momentum_points: int = Field(ge=0, le=2, description="New fund <18mo=2pts OR 2+ exits in 3yrs=2pts OR Portfolio follow-ons=2pts (pick one)")
    momentum_reasoning: str = Field(description="Explanation of momentum scoring")

    category_total: int = Field(ge=0, le=5, description="Strategic Factors total (geography_points + momentum_points)")

class VC_DisqualificationAnalysis(BaseModel):
    """Disqualification analysis (ONLY for Fund AUM < $20M)."""
    is_disqualified: bool = Field(description="True only if Fund AUM < $20M")
    disqualification_reason: Optional[str] = Field(default=None, description="Reason for DQ (should be 'Fund AUM < $20M' if DQ'd)")

class VC_ActionableIntelligence(BaseModel):
    """Actionable intelligence for pitch preparation (9 sections from playbook)."""

    portfolio_pattern: str = Field(description="Stage, traction levels, founder profiles they invest in. Be specific.")

    partner_insights: str = Field(description="Recent content, beliefs, what excites them. Use LinkedIn posts! Include quotes and dates.")

    investment_pace_and_process: str = Field(description="Deals per quarter, timeline, current urgency, IC process. Be specific with numbers.")

    value_add_evidence: str = Field(description="Specific examples with numbers (e.g., 'Intro'd 15 VP Marketing candidates to portfolio in 2024')")

    deal_preferences: str = Field(description="Traction bar, team requirements, what they pass on, what excites them")

    recent_positioning: str = Field(description="Thesis updates, market views from recent posts/tweets. USE EXACT QUOTES and language for pitch prep.")

    fund_context: str = Field(description="Deployment stage, team changes, pressure/urgency signals")

    competitive_intel: str = Field(description="Portfolio overlaps, gaps (specifically for AI B2B content/marketing tools), frequent co-investors")

    pitch_prep: str = Field(description="3 specific elements:\n• Reference: Specific portfolio company or statement to mention\n• Angle: How you fit their thesis\n• Opening: Personalized hook for outreach")

class VC_CurrentEmploymentInfo(BaseModel):
    """Current employment verification details."""
    current_fund_name: str = Field(description="Partner's current fund/firm name")
    current_title: str = Field(description="Partner's current title/role")
    is_still_at_input_firm: bool = Field(description="Whether partner is still at the firm provided in input")
    firm_change_detected: bool = Field(description="Whether partner moved to a different firm")
    firm_change_details: Optional[str] = Field(default=None, description="Details of firm change if applicable (e.g., 'Moved from Fund A to Fund B in March 2024')")
    is_still_in_vc: bool = Field(description="Whether partner is still actively in venture capital")
    employment_notes: Optional[str] = Field(default=None, description="Additional employment verification notes")

class VC_InvestorLeadScoringOutput(BaseModel):
    """Complete VC investor lead scoring output (100-point framework)."""

    # Employment verification (DO THIS FIRST)
    current_employment: VC_CurrentEmploymentInfo

    # Scoring categories (100 points total)
    fund_vitals: VC_FundVitalsScoring  # 0-25 points
    lead_capability: VC_LeadCapabilityScoring  # 0-25 points
    thesis_alignment: VC_ThesisFitScoring  # 0-30 points
    partner_value: VC_PartnerValueScoring  # 0-15 points
    strategic_factors: VC_StrategicFactorsScoring  # 0-5 points

    # Total score and tier
    total_score: int = Field(ge=0, le=100, description="Sum of all category totals (max 100 points)")
    score_tier: Literal["A (85-100)", "B (70-84)", "C (50-69)", "D (<50)"] = Field(description="Tier based on total score")
    recommended_action: Literal["Top Priority", "High Priority", "Medium Priority", "Low Priority"] = Field(description="Action priority based on tier")

    # Disqualification (ONLY for Fund AUM < $20M)
    disqualification: VC_DisqualificationAnalysis

    # Actionable Intelligence (9 sections for pitch prep)
    actionable_intelligence: VC_ActionableIntelligence

    # Supporting data
    notable_portfolio_companies: List[VC_PortfolioCompany] = Field(default_factory=list, max_length=10, description="Top 8-10 notable portfolio companies")

    # Research quality indicators
    research_confidence: Literal["High", "Medium", "Low"] = Field(description="Confidence in research findings")
    missing_critical_info: List[str] = Field(default_factory=list, description="List of critical information not found")
    additional_notes: Optional[str] = Field(default=None, description="Any additional context or notes")

# Generate JSON Schema from Pydantic Model for VC Framework
VC_INVESTOR_LEAD_SCORING_OUTPUT_SCHEMA = VC_InvestorLeadScoringOutput.model_json_schema()


# ================================================================================
# ANGEL FRAMEWORK: Deep Research & Extraction Prompts and Schemas
# ================================================================================

# ========================================
# Angel Framework: Step 1 - Deep Research Configuration
# ========================================

ANGEL_STEP1_DEEP_RESEARCH_SYSTEM_PROMPT = """You are an expert angel investor researcher specializing in comprehensive fact-gathering on high-value individual angel investors.

Your task is to conduct thorough, factual research on angel investors. You are gathering data for downstream scoring and analysis - focus on facts, numbers, dates, and specific examples.

**Research Areas:**

**1. EMPLOYER BRAND & CREDIBILITY** (data for 0-25 points):
   - **Current/Former Employer**: Identify tier-1 brands (Google, Amazon, OpenAI, Anthropic, Adobe, HubSpot, Salesforce, Meta, Microsoft, Stripe, Snowflake), tier-2 unicorns (Notion, Figma, Databricks, Scale AI), tier-3 (Series C+ startups), tier-4 (earlier stage)
   - **Role Level at Brand**: C-level (CMO, CPO, CTO, VP→C-level), VP-level, Director/Senior IC
   - **Ex-Founder Status**: Founded successful exit ($50M+), founded acquired/failed startup, currently founding
   - Search: "[Angel] (Google OR Amazon OR OpenAI OR HubSpot) linkedin", "[Angel] founder OR founded"

**2. FUNCTIONAL EXPERTISE** (data for 0-25 points):
   - **Domain Expertise**: CMO/VP Marketing at B2B scale-up, VP Sales/Revenue/Growth, VP Product (AI/ML focus), CTO/VP Eng (AI/infra), Generalist operator
   - **Relevance**: Direct MarTech experience, AI/ML product leadership, B2B SaaS GTM expertise, Growth/PLG expertise, Adjacent expertise
   - Search: "[Angel] (CMO OR 'VP Marketing' OR 'VP Sales')", "[Angel] MarTech OR 'marketing technology' OR 'AI product'"

**3. VC NETWORK ACCESS** (data for 0-20 points):
   - **VC Ecosystem Integration**: Co-invests with tier-1 VCs (Sequoia, a16z, Benchmark), tier-2 VCs, limited co-investment
   - **Portfolio Success**: 5+ portfolio cos raised Series A/B, 2-4 portfolio cos raised follow-ons, 1 portfolio co raised follow-on, no follow-ons
   - Search: "[Angel] portfolio site:crunchbase.com 'series A' OR 'series B'", "[Angel] AND (Sequoia OR a16z) invested OR co-investor"

**4. CHECK ACTIVITY & SIZE** (data for 0-20 points):
   - **Check Frequency (last 24 months)**: 15+ checks, 8-15 checks, 3-7 checks, 1-2 checks
   - **Typical Check Size**: $100K+, $50K-$100K, $25K-$50K, $10K-$25K, <$10K
   - Search: "[Angel] angel investor 2024 OR 2025", "[Angel] announces investment OR backs"

**5. SHARED AFFINITY** (data for 0-22 points):
   - **Educational**: IIT alumni, U-Michigan alumni, other top school (Stanford, MIT, Berkeley)
   - **Ex-Amazon/Ex-Google**: Ex-Amazon = 7 pts, Ex-Google = 7 pts (can stack with other affinity)
   - **Geographic/Cultural**: Indian/South Asian background, lived/worked in India
   - **Technical Background**: Engineering/CS degree
   - Search: "[Angel] IIT OR 'Indian Institute of Technology'", "[Angel] Michigan OR 'University of Michigan'", "[Angel] India OR Indian", "[Angel] Amazon OR Google"

**6. ACTIONABLE INTELLIGENCE** (for pitch prep):
   - Recent public statements, tweets, blog posts
   - Investment patterns and preferences
   - Value-add evidence with specific examples
   - Co-investors they work with frequently

**CRITICAL INSTRUCTIONS:**
- NO disqualification criteria for angels - score everyone 0-105 (normalized to 0-100)
- Provide SPECIFIC examples with DATES and NUMBERS
- Use exact quotes when available
- Don't summarize - provide raw facts for scoring
- If data not found, explicitly state "Information not found"
- Be comprehensive and thorough

**⚠️ CRITICAL FIRST STEP - VERIFY CURRENT EMPLOYMENT:**

**0. CURRENT EMPLOYMENT VERIFICATION** (DO THIS FIRST):

**SEARCH STRATEGY** (follow this order for best results):

**Step 0a: Use LinkedIn Scraped Data (MOST RELIABLE if available)**
   - If LinkedIn scraped data is provided, use it as PRIMARY source:
     * Check the "position" array for current employment
     * Look for the position with no end date or most recent start date
     * Extract: current company name, current title, start date
     * This is the MOST ACCURATE source

**Step 0b: LinkedIn URL Search (SECOND MOST RELIABLE)**
   - If LinkedIn URL provided, use it as PRIMARY source:
     * Extract LinkedIn username from URL
     * Search: "site:linkedin.com/in/<username>" OR "<username> linkedin current"
     * LinkedIn profiles are most up-to-date for current employment

**Step 0c: Verify Current Company**
   - Search: "<name> <company>" OR "<linkedin_username> <company>"
   - Look for recent activity: press releases, announcements, company website

**Step 0d: Find Current Company if Changed**
   - Search: "<name> angel investor current" OR "<name> operator company"
   - Look for recent announcements, news

**WHAT TO EXTRACT:**
   - **Current company name**: Full official name
   - **Current title**: Exact title from most recent source
   - **Is still at input company?**: Boolean
   - **Company change detected?**: Has angel moved companies?
   - **Still operating/investing?**: Is angel still active?
   - **Employment notes**: Any relevant context

**IMPORTANT INSTRUCTIONS**:
   - Prioritize LinkedIn scraped data FIRST (if provided)
   - Second priority: LinkedIn URL searches
   - If angel moved companies: research NEW current company for employer brand scoring
   - If angel is no longer operating, note it but still research their last company

Provide comprehensive, factual research with specific details and evidence for downstream scoring.
"""

ANGEL_STEP1_DEEP_RESEARCH_USER_PROMPT = """Research the following angel investor for seed-stage fundraising evaluation:

**ANGEL INVESTOR DETAILS PROVIDED:**
Name: {first_name} {last_name}
Title (from input): {title}
Company (from input): {firm_company}
Investor Type: {investor_type}
Investor Role Detail: {investor_role_detail}
Relationship Status: {relationship_status}
LinkedIn URL: {linkedin_url}
Twitter URL: {twitter_url}
Crunchbase URL: {crunchbase_url}
Investment Criteria (from input): {investment_criteria}
Notes (from input): {notes}
Source: {source_sheets}

**LINKEDIN PROFILE DATA** (if available - most reliable source for current employment):
{linkedin_scraped_profile}
"""

# ========================================
# Angel Framework: Step 2 - Structured Extraction Configuration
# ========================================

ANGEL_STEP2_EXTRACTION_SYSTEM_PROMPT = """You are an expert angel investor analyst specializing in investor scoring for seed-stage B2B AI/MarTech fundraising.

Your task is to analyze research data and produce a structured score (0-112 raw, normalized to 0-100) with actionable intelligence for pitch preparation.

**SCORING FRAMEWORK (112 points max raw, normalized to 100):**

**A. EMPLOYER BRAND & CREDIBILITY (0-25 pts)**
```
Current/Former Employer Brand:
  Tier-1 (Google, Amazon, OpenAI, Anthropic, Adobe, HubSpot, Salesforce, Meta, Microsoft, Stripe, Snowflake) = 15 pts
  Tier-2 (Unicorns: Notion, Figma, Databricks, Scale AI) = 12 pts
  Tier-3 (Series C+ startups, strong brands) = 8 pts
  Tier-4 (Earlier stage or weaker brand) = 4 pts

Role Level at Brand:
  C-level (CMO, CPO, CTO, VP→C-level) = 7 pts
  VP-level = 5 pts
  Director/Senior IC = 3 pts

Ex-Founder Bonus (ADDITIVE):
  Founder of successful exit ($50M+) = +10 pts
  Founder of acquired/failed startup = +7 pts
  Currently founding = +5 pts
```

**B. FUNCTIONAL EXPERTISE (0-25 pts)**
```
Domain Expertise:
  CMO/VP Marketing at B2B scale-up = 15 pts
  VP Sales/Revenue/Growth = 12 pts
  VP Product (AI/ML focus) = 12 pts
  CTO/VP Eng (AI/infra) = 10 pts
  Generalist operator = 5 pts

Relevance to MarTech/AI:
  Direct MarTech experience = 10 pts
  AI/ML product leadership = 8 pts
  B2B SaaS GTM expertise = 7 pts
  Growth/PLG expertise = 6 pts
  Adjacent expertise = 3 pts
```

**C. VC NETWORK ACCESS (0-20 pts)**
```
VC Ecosystem Integration:
  Co-invests with tier-1 VCs (Sequoia, a16z, Benchmark) = 10 pts
  Co-invests with tier-2 VCs = 7 pts
  Limited VC co-investment = 3 pts

Portfolio Success Signals:
  5+ portfolio cos raised Series A/B = 10 pts
  2-4 portfolio cos raised follow-ons = 7 pts
  1 portfolio co raised follow-on = 4 pts
  No portfolio follow-ons = 0 pts
```

**D. CHECK ACTIVITY & SIZE (0-20 pts)**
```
Check Frequency (last 24 months):
  15+ checks = 10 pts
  8-15 checks = 8 pts
  3-7 checks = 6 pts
  1-2 checks = 2 pts

Typical Check Size:
  $100K+ = 10 pts
  $50K-$100K = 8 pts
  $25K-$50K = 6 pts
  $10K-$25K = 3 pts
  <$10K = 1 pt
```

**E. SHARED AFFINITY (0-22 pts)**
```
Educational Connection:
  IIT alumni = 7 pts
  U-Michigan alumni = 7 pts
  Other top school (Stanford, MIT, Berkeley) = 4 pts

Ex-Amazon/Ex-Google (ADDITIVE - can stack):
  Ex-Amazon = 7 pts
  Ex-Google = 7 pts

Geographic/Cultural:
  Indian/South Asian background = 5 pts
  Lived/worked in India = 3 pts

Technical Background:
  Engineering/CS degree = 3 pts
```

**TIER ASSIGNMENT (based on normalized score 0-100):**
- A: 75-100 points (Top Priority)
- B: 60-74 points (High Priority)
- C: 40-59 points (Medium Priority)
- D: <40 points (Skip)

**CRITICAL RULES:**
- NO disqualification criterion for angels - score everyone
- Raw score is 0-112, then normalize to 0-100 by dividing raw by 1.12
- Ex-Founder bonus is ADDITIVE to employer brand score (can exceed 25 in raw before normalization)
- Ex-Amazon/Ex-Google points are ADDITIVE to shared affinity (can stack with educational/cultural/technical)
- Use specifics: Not "helps with hiring" but "Intro'd 15 VP Marketing candidates in 2024"
- Special situations: Angel moved companies (research CURRENT company for brand scoring)

Apply scoring rigorously based on evidence. Be conservative but fair.

**TASK:**

1. **Employment Verification** (DO THIS FIRST):
   - Determine angel's CURRENT company (may have moved from input company)
   - Use LinkedIn profile data as primary source for current employment
   - If angel moved, document the change and use CURRENT company for employer brand scoring

2. **Score Calculation** (112-point raw framework, normalized to 100):
   - **Employer Brand & Credibility** (0-25 pts base, can go higher with founder bonus): Brand tier + role level + ex-founder bonus (additive)
   - **Functional Expertise** (0-25 pts): Domain expertise + relevance to MarTech/AI
   - **VC Network Access** (0-20 pts): VC ecosystem integration + portfolio success
   - **Check Activity & Size** (0-20 pts): Check frequency + typical check size
   - **Shared Affinity** (0-22 pts): Educational + ex-Amazon/ex-Google + geographic/cultural + technical (all additive)
   - **Raw Total**: Sum all categories (max 112)
   - **Normalized Score**: raw_total / 1.12 (scale to 0-100)

3. **Tier Assignment (based on normalized score)**:
   - A: 75-100 (Top Priority)
   - B: 60-74 (High Priority)
   - C: 40-59 (Medium)
   - D: <40 (Skip)

4. **Actionable Intelligence** (8 sections from playbook):
   - Brand Value & Expertise
   - Founder Story (if applicable)
   - VC Connectivity
   - Portfolio Pattern
   - Value-Add Specifics
   - Networking Power
   - Affinity Points
   - Pitch Prep (Hook, Connection, Value ask, Opening)

**IMPORTANT INSTRUCTIONS:**
- Use LinkedIn profile data as PRIMARY source for current company verification
- Use LinkedIn posts to understand angel's recent interests and positioning
- NO disqualification - all angels get scored
- Use SPECIFIC examples with DATES and NUMBERS
- Use exact QUOTES from posts for "Recent Positioning"
- If angel moved companies, document in structured output and score the CURRENT company
- Be evidence-based - only score what you can verify
- Remember: Raw score can exceed 100 (due to founder bonus and affinity stacking), max 112 raw which normalizes to 100
"""

ANGEL_STEP2_EXTRACTION_USER_PROMPT = """Based on the research report and LinkedIn data, extract structured information and calculate a 0-112 raw score (normalized to 0-100) using the angel scoring framework.

**ANGEL INVESTOR INPUT DATA:**
Angel: {first_name} {last_name}
Title (from input): {title}
Company (from input): {firm_company}
Investor Type: {investor_type}
Investment Criteria: {investment_criteria}
Notes: {notes}

**LINKEDIN PROFILE DATA:**
{linkedin_scraped_profile}

**DEEP RESEARCH REPORT:**
{deep_research_report}

**WEB SEARCH CITATIONS:**
{deep_research_citations}

**LINKEDIN POSTS DATA (20 recent posts):**
{linkedin_scraped_posts}
"""


# ========================================
# Angel Framework: Pydantic Output Schema Models
# ========================================

class ANGEL_InvestmentExample(BaseModel):
    """Angel investment example."""
    company_name: str = Field(description="Company name")
    investment_date: Optional[str] = Field(default=None, description="Investment date if available")
    round_stage: Optional[str] = Field(default=None, description="Round stage (Seed, Series A, etc.)")
    check_size: Optional[str] = Field(default=None, description="Check size if available")
    source: Optional[str] = Field(default=None, description="Information source")

class ANGEL_PortfolioCompany(BaseModel):
    """Portfolio company details."""
    company_name: str = Field(description="Company name")
    sector: Optional[str] = Field(default=None, description="Sector (e.g., 'AI B2B', 'MarTech', 'DevTools')")
    investment_date: Optional[str] = Field(default=None, description="Investment date if available")
    raised_followon: bool = Field(default=False, description="Whether company raised follow-on funding")
    followon_details: Optional[str] = Field(default=None, description="Follow-on round details")

class ANGEL_EmployerBrandScoring(BaseModel):
    """Employer brand & credibility scoring (0-25 points base, can exceed with founder bonus)."""
    current_employer: str = Field(description="Current employer name")
    employer_tier: Literal["Tier-1", "Tier-2", "Tier-3", "Tier-4", "Unknown"] = Field(description="Employer brand tier")
    employer_brand_points: int = Field(ge=0, le=15, description="Tier-1=15, Tier-2=12, Tier-3=8, Tier-4=4")
    employer_brand_reasoning: str = Field(description="Explanation of employer brand scoring")
    
    role_level: str = Field(description="Role level (C-level, VP-level, Director/Senior IC)")
    role_level_points: int = Field(ge=0, le=7, description="C-level=7, VP-level=5, Director/Senior IC=3")
    role_level_reasoning: str = Field(description="Explanation of role level scoring")
    
    is_ex_founder: bool = Field(description="Is or was a founder")
    founder_exit_type: Optional[Literal["Successful Exit ($50M+)", "Acquired/Failed", "Currently Founding", "Not a founder"]] = Field(default=None, description="Type of founder experience")
    founder_details: Optional[str] = Field(default=None, description="Founder story details")
    ex_founder_bonus_points: int = Field(ge=0, le=10, description="Successful exit=10, Acquired/Failed=7, Currently founding=5, Not founder=0")
    
    category_total_raw: int = Field(ge=0, description="Employer Brand total RAW (can exceed 25 with founder bonus)")
    category_total_normalized: float = Field(ge=0, le=25, description="Employer Brand total NORMALIZED (raw / 1.05, max 25)")

class ANGEL_FunctionalExpertiseScoring(BaseModel):
    """Functional expertise scoring (0-25 points)."""
    domain: str = Field(description="Domain expertise (CMO/Marketing, Sales/Revenue, Product, Eng, Generalist)")
    domain_expertise_points: int = Field(ge=0, le=15, description="CMO/VP Marketing B2B=15, VP Sales/Revenue=12, VP Product AI/ML=12, CTO/VP Eng=10, Generalist=5")
    domain_reasoning: str = Field(description="Explanation of domain expertise scoring")
    
    relevance: str = Field(description="Relevance to MarTech/AI (Direct MarTech, AI/ML product, B2B SaaS GTM, Growth/PLG, Adjacent)")
    relevance_points: int = Field(ge=0, le=10, description="Direct MarTech=10, AI/ML product=8, B2B SaaS GTM=7, Growth/PLG=6, Adjacent=3")
    relevance_reasoning: str = Field(description="Explanation of relevance scoring")
    
    category_total: int = Field(ge=0, le=25, description="Functional Expertise total (domain + relevance)")

class ANGEL_VCNetworkScoring(BaseModel):
    """VC network access scoring (0-20 points)."""
    vc_ecosystem_integration: str = Field(description="Level of VC ecosystem integration (Tier-1 VCs, Tier-2 VCs, Limited, None)")
    co_investment_examples: List[str] = Field(default_factory=list, description="Examples of co-investments with VCs")
    vc_integration_points: int = Field(ge=0, le=10, description="Tier-1 VCs=10, Tier-2 VCs=7, Limited=3, None=0")
    vc_integration_reasoning: str = Field(description="Explanation of VC integration scoring")
    
    portfolio_followon_count: int = Field(ge=0, description="Number of portfolio companies that raised follow-on rounds")
    portfolio_followon_companies: List[ANGEL_PortfolioCompany] = Field(default_factory=list, description="Portfolio companies with follow-on rounds")
    portfolio_success_points: int = Field(ge=0, le=10, description="5+ followons=10, 2-4 followons=7, 1 followon=4, 0=0")
    portfolio_success_reasoning: str = Field(description="Explanation of portfolio success scoring")
    
    category_total: int = Field(ge=0, le=20, description="VC Network total (integration + success)")

class ANGEL_CheckActivityScoring(BaseModel):
    """Check activity & size scoring (0-20 points)."""
    check_frequency_24mo: int = Field(ge=0, description="Number of angel checks in last 24 months")
    recent_investments: List[ANGEL_InvestmentExample] = Field(default_factory=list, description="Recent investment examples")
    check_frequency_points: int = Field(ge=0, le=10, description="15+ checks=10, 8-15=8, 3-7=6, 1-2=2")
    check_frequency_reasoning: str = Field(description="Explanation of check frequency scoring")
    
    typical_check_size: str = Field(description="Typical check size (e.g., '$100K+', '$50K-$100K', etc.)")
    check_size_points: int = Field(ge=0, le=10, description="$100K+=10, $50K-$100K=8, $25K-$50K=6, $10K-$25K=3, <$10K=1")
    check_size_reasoning: str = Field(description="Explanation of check size scoring")
    
    category_total: int = Field(ge=0, le=20, description="Check Activity total (frequency + size)")

class ANGEL_SharedAffinityScoring(BaseModel):
    """Shared affinity scoring (0-22 points)."""
    educational_connection: str = Field(description="Educational background (IIT, U-Michigan, Other top school, None)")
    educational_points: int = Field(ge=0, le=7, description="IIT=7, U-Michigan=7, Other top=4, None=0")
    educational_reasoning: str = Field(description="Explanation of educational connection scoring")
    
    is_ex_amazon: bool = Field(description="Is ex-Amazon employee")
    ex_amazon_points: int = Field(ge=0, le=7, description="Ex-Amazon=7, None=0")
    
    is_ex_google: bool = Field(description="Is ex-Google employee")
    ex_google_points: int = Field(ge=0, le=7, description="Ex-Google=7, None=0")
    
    ex_amazon_google_reasoning: str = Field(description="Explanation of ex-Amazon/Google scoring")
    
    geographic_cultural_connection: str = Field(description="Geographic/cultural background (Indian/South Asian, Lived/worked India, None)")
    geographic_cultural_points: int = Field(ge=0, le=5, description="Indian/South Asian=5, Lived/worked India=3, None=0")
    geographic_cultural_reasoning: str = Field(description="Explanation of geographic/cultural scoring")
    
    technical_background: bool = Field(description="Has engineering/CS degree")
    technical_background_points: int = Field(ge=0, le=3, description="Eng/CS degree=3, None=0")
    technical_background_reasoning: str = Field(description="Explanation of technical background scoring")
    
    category_total: int = Field(ge=0, le=22, description="Shared Affinity total (education + ex-Amazon/Google + geo/cultural + technical, all additive)")

class ANGEL_ActionableIntelligence(BaseModel):
    """Actionable intelligence for pitch preparation (8 sections from angel playbook)."""
    
    brand_value_and_expertise: str = Field(description="Company, role, what they scaled, specific skills")
    
    founder_story: str = Field(description="What they built, exit/outcome, lessons learned (if applicable)")
    
    vc_connectivity: str = Field(description="VCs they co-invest with, portfolio companies that raised, ecosystem presence")
    
    portfolio_pattern: str = Field(description="Companies invested, stage, check size, involvement, which raised Series A/B")
    
    value_add_specifics: str = Field(description="Customer intros at [Company], hiring via [Company] network, product feedback")
    
    networking_power: str = Field(description="Who they likely know: VCs (via co-investment), customers, talent")
    
    affinity_points: str = Field(description="IIT/Michigan/India connection, shared experiences")
    
    pitch_prep: str = Field(description="4 specific elements:\n• Hook: [Company + role + founder status]\n• Connection: [IIT/Michigan/India angle if applicable]\n• Value ask: [VC network + specific functional help]\n• Opening: [Personalized based on background]")

class ANGEL_CurrentEmploymentInfo(BaseModel):
    """Current employment verification details."""
    current_company_name: str = Field(description="Angel's current company name")
    current_title: str = Field(description="Angel's current title/role")
    is_still_at_input_company: bool = Field(description="Whether angel is still at the company provided in input")
    company_change_detected: bool = Field(description="Whether angel moved to a different company")
    company_change_details: Optional[str] = Field(default=None, description="Details of company change if applicable")
    is_still_operating: bool = Field(description="Whether angel is still actively operating/working")
    employment_notes: Optional[str] = Field(default=None, description="Additional employment verification notes")

class ANGEL_InvestorLeadScoringOutput(BaseModel):
    """Complete angel investor lead scoring output (112-point raw framework, normalized to 100)."""
    
    # Employment verification (DO THIS FIRST)
    current_employment: ANGEL_CurrentEmploymentInfo
    
    # Scoring categories (112 points raw total, normalized to 100)
    employer_brand: ANGEL_EmployerBrandScoring  # 0-25 points normalized (can exceed in raw with founder bonus)
    functional_expertise: ANGEL_FunctionalExpertiseScoring  # 0-25 points
    vc_network: ANGEL_VCNetworkScoring  # 0-20 points
    check_activity: ANGEL_CheckActivityScoring  # 0-20 points
    shared_affinity: ANGEL_SharedAffinityScoring  # 0-22 points
    
    # Total scores
    total_score_raw: int = Field(ge=0, description="Raw total score (can exceed 100, max 112)")
    total_score_normalized: int = Field(ge=0, le=100, description="Normalized score (raw / 1.12, scaled to 0-100)")
    score_tier: Literal["A (75-100)", "B (60-74)", "C (40-59)", "D (<40)"] = Field(description="Tier based on normalized score")
    recommended_action: Literal["Top Priority", "High Priority", "Medium Priority", "Skip"] = Field(description="Action priority based on tier")
    
    # Actionable Intelligence (8 sections for pitch prep)
    actionable_intelligence: ANGEL_ActionableIntelligence
    
    # Supporting data
    notable_portfolio_companies: List[ANGEL_PortfolioCompany] = Field(default_factory=list, max_length=10, description="Top 8-10 notable portfolio companies")
    
    # Research quality indicators
    research_confidence: Literal["High", "Medium", "Low"] = Field(description="Confidence in research findings")
    missing_critical_info: List[str] = Field(default_factory=list, description="List of critical information not found")
    additional_notes: Optional[str] = Field(default=None, description="Any additional context or notes")

# Generate JSON Schema from Pydantic Model for Angel Framework
ANGEL_INVESTOR_LEAD_SCORING_OUTPUT_SCHEMA = ANGEL_InvestorLeadScoringOutput.model_json_schema()


# ================================================================================
# EMAIL GENERATION: Personalization Line and Email Template (Works with both frameworks)
# ================================================================================

# ========================================
# Personalization Line Generation Configuration
# ========================================

PERSONALIZATION_LINE_SYSTEM_PROMPT = """You are an expert at crafting personalized outreach emails for fundraising.

Your task is to generate a highly personalized, relevant connection line for an investor email based on their background and portfolio.

**PERSONALIZATION PLAYBOOK:**

**🎯 For VCs - Portfolio Pattern (Strongest):**
- Look for: 2-3 similar B2B companies in their portfolio
- Insert: "Noticed the pattern in your portfolio - [Company1], [Company2] all have complex products that need thought leadership. We're systematizing that"
- Examples:
  * "Noticed the pattern in your portfolio - Linear, Airplane all have complex products that need thought leadership. We're systematizing that"
  * "Looking at Vercel and Planetscale in your portfolio - you clearly get the challenge of technical products building pipeline"

**👤 For Angels - Operator Experience:**
- Look for: Their scaling experience at specific companies
- Insert one of:
  * "You scaled [Company] from seed to Series C - you know firsthand how content becomes critical at exactly our target stage"
  * "Having built [function] at [Company], you've lived through the problem we're solving"
  * "Your experience taking [Company] through hypergrowth is exactly why we'd value your perspective on our platform trajectory"
- Examples:
  * "You scaled Plaid from seed to Series C - you know firsthand how content becomes critical at exactly our target stage"
  * "Having built marketing at Stripe, you've lived through the problem we're solving"

**CRITICAL INSTRUCTIONS:**
- Be specific - use actual company names and roles
- Be concise - one sentence, max 25 words
- Be authentic - don't oversell, just make the connection
- Use information from their portfolio, background, or thesis
- If insufficient data, create a generic but thoughtful line based on their investor type

The personalization line should fit in the email template below:
"We are building company-specific Marketing Brains at KiwiQ to help B2B companies navigate both winds at once. 
<personalization_line> and would love to have an exploratory chat."

"""

PERSONALIZATION_LINE_USER_PROMPT = """Generate a personalized line for this investor based on their scoring data:

**INVESTOR PROFILE:**
Name: {first_name} {last_name}

**LINKEDIN PROFILE DATA** (if available - most reliable source for current employment):
{linkedin_scraped_profile}

**KEY INSIGHTS FROM SCORING:**
{scoring_result}

Generate a personalized, specific connection line (one sentence, max 25 words) that references their background, portfolio, or expertise."""

class PersonalizationLineOutput(BaseModel):
    """Personalization line output."""
    reasoning: str = Field(description="Brief explanation of why this personalization was chosen based on the investor's profile")
    personalization_line: str = Field(description="The personalized connection line for the email (one sentence, max 25 words)")

# Generate JSON Schema
PERSONALIZATION_LINE_OUTPUT_SCHEMA = PersonalizationLineOutput.model_json_schema()


# ========================================
# Email Template Configuration
# ========================================

EMAIL_TEMPLATE = """Hey {first_name},

Two twin winds are completely reshaping B2B marketing today:

1. 90% of B2B buyers now use generative AI tools (Forrester, 2025\)  
2. When everyone uses ChatGPT to write content, everyone sounds exactly the same

So here's the problem \- companies are invisible where buyers search AND indistinguishable if they're found.

We are building company-specific Marketing Brains at KiwiQ to help B2B companies navigate both winds at once. {personalization_line} and would love to have an exploratory chat.

**Blurb:** Our first product ContentQ helps B2B teams get discovered by AI and humans, with authentic content that establishes authority and closes deals. Diagnostics, research, strategy, content \- our agents handle it e2e.

Under the hood, it's built on a production-grade multi-agent platform with self-healing workflows and persistent memory \- that can be custom-built in natural language in days and not months. 70% of our agents are built by non-coder marketing experts this way.

**Founders:** Founder A (Ex-BigTech ML Lead, Knowledge Graphs) and Founder B (Ex-BigTech Product Lead, Marketing Expert).

**Traction:** $4.5K MRR, 5 customers in 3 weeks (3 from YC), late-stage discussions with decacorn.

**Raising:** $2M

Chat? \[Cal link\]

Cheers,  
 Founder A

P.S \- If there are any portfolio companies (B2B pre-seed → Series B) who might be good candidates to accelerate their thought leadership content efforts, we'd love to chat with them and help out :)
"""


# ================================================================================
# FRAMEWORK SELECTOR: Automatically sets prompts and schemas based on ACTIVE_FRAMEWORK
# ================================================================================

def get_active_framework_config():
    """
    Returns the active framework's prompts and schemas based on ACTIVE_FRAMEWORK setting.
    
    Returns:
        dict: Configuration dictionary with prompts and schemas for the active framework
    """
    if ACTIVE_FRAMEWORK == "VC":
        return {
            "framework_name": "VC",
            "step1_system_prompt": VC_STEP1_DEEP_RESEARCH_SYSTEM_PROMPT,
            "step1_user_prompt": VC_STEP1_DEEP_RESEARCH_USER_PROMPT,
            "step2_system_prompt": VC_STEP2_EXTRACTION_SYSTEM_PROMPT,
            "step2_user_prompt": VC_STEP2_EXTRACTION_USER_PROMPT,
            "output_schema": VC_INVESTOR_LEAD_SCORING_OUTPUT_SCHEMA,
        }
    elif ACTIVE_FRAMEWORK == "ANGEL":
        return {
            "framework_name": "ANGEL",
            "step1_system_prompt": ANGEL_STEP1_DEEP_RESEARCH_SYSTEM_PROMPT,
            "step1_user_prompt": ANGEL_STEP1_DEEP_RESEARCH_USER_PROMPT,
            "step2_system_prompt": ANGEL_STEP2_EXTRACTION_SYSTEM_PROMPT,
            "step2_user_prompt": ANGEL_STEP2_EXTRACTION_USER_PROMPT,
            "output_schema": ANGEL_INVESTOR_LEAD_SCORING_OUTPUT_SCHEMA,
        }
    else:
        raise ValueError(f"Invalid ACTIVE_FRAMEWORK: {ACTIVE_FRAMEWORK}. Must be 'VC' or 'ANGEL'")


# Export the active configuration for easy access
ACTIVE_CONFIG = get_active_framework_config()

# Export individual components for backward compatibility and easy access
STEP1_DEEP_RESEARCH_SYSTEM_PROMPT = ACTIVE_CONFIG["step1_system_prompt"]
STEP1_DEEP_RESEARCH_USER_PROMPT = ACTIVE_CONFIG["step1_user_prompt"]
STEP2_EXTRACTION_SYSTEM_PROMPT = ACTIVE_CONFIG["step2_system_prompt"]
STEP2_EXTRACTION_USER_PROMPT = ACTIVE_CONFIG["step2_user_prompt"]
INVESTOR_LEAD_SCORING_OUTPUT_SCHEMA = ACTIVE_CONFIG["output_schema"]
