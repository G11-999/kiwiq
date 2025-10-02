"""
LLM Inputs for Investor Lead Scoring Workflow

Scoring System (Based on Updated Playbook):
- Raw Total: 0-200 points
- Normalized Score: 0-100 (divide raw by 2)
- Tiers: 80+ (A-List), 60-79 (Hot), 40-59 (Warm), <40 (Pass)
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# LLM Model Configurations

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
LLM_MAX_TOKENS_DEEP_RESEARCH = 16000  # 16000
LLM_DEEP_RESEARCH_REASONING_EFFORT = "low"
LLM_DEEP_RESEARCH_SEARCH_CONTEXT_SIZE = "low"

# Structured Extraction (Claude Sonnet)
LLM_PROVIDER_EXTRACTION = "anthropic"
LLM_MODEL_EXTRACTION = "claude-sonnet-4-5-20250929"
LLM_TEMPERATURE_EXTRACTION = 0.1
LLM_MAX_TOKENS_EXTRACTION = 16000


# ========================================
# LinkedIn URL Finder Configuration
# ========================================

LINKEDIN_URL_FINDER_SYSTEM_PROMPT = """You are an expert at finding LinkedIn profiles for venture capital investors using web search.

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


# ========================================
# Step 1: Deep Research Configuration
# ========================================

STEP1_DEEP_RESEARCH_SYSTEM_PROMPT = """You are an expert venture capital researcher specializing in comprehensive fact-gathering on seed-stage investors.

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

STEP1_DEEP_RESEARCH_USER_PROMPT = """Research the following venture capital investor/partner for seed-stage fundraising evaluation:

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
# Step 2: Structured Extraction Configuration
# ========================================

STEP2_EXTRACTION_SYSTEM_PROMPT = """You are an expert venture capital analyst specializing in investor scoring for seed-stage B2B AI/MarTech fundraising.

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

STEP2_EXTRACTION_USER_PROMPT = """Based on the research report and LinkedIn data, extract structured information and calculate a 0-100 lead score using the new scoring framework.

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
# Pydantic Output Schema Models
# ========================================

class PortfolioCompany(BaseModel):
    """Portfolio company details."""
    company_name: str = Field(description="Company name")
    sector: str = Field(description="Sector (e.g., 'AI B2B', 'MarTech', 'DevTools')")
    investment_date: Optional[str] = Field(default=None, description="Investment date if available")
    stage_at_investment: Optional[str] = Field(default=None, description="Stage at investment")

class LedRoundExample(BaseModel):
    """Seed round led by the fund."""
    company_name: str = Field(description="Company name")
    date: str = Field(description="Round date")
    round_size: Optional[str] = Field(default=None, description="Total round size")
    fund_check_size: Optional[str] = Field(default=None, description="Fund's investment amount")
    source: Optional[str] = Field(default=None, description="Information source")

class ExitDetails(BaseModel):
    """Portfolio exit details."""
    company_name: str = Field(description="Exited company name")
    exit_type: str = Field(description="Exit type (Acquisition, IPO, Unicorn)")
    exit_date: Optional[str] = Field(default=None, description="Exit date")
    acquirer_or_details: Optional[str] = Field(default=None, description="Acquirer or details")

class FundVitalsScoring(BaseModel):
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

class LeadCapabilityScoring(BaseModel):
    """Lead capability scoring (0-25 points)."""
    lead_behavior: str = Field(description="Lead behavior pattern (Regularly leads, Co-leads, Mostly participates, Unclear)")
    led_rounds_count: int = Field(ge=0, description="Number of seed rounds led in 2024-2025")
    led_round_examples: List[LedRoundExample] = Field(default_factory=list, description="Specific examples of led rounds")
    lead_behavior_points: int = Field(ge=0, le=15, description="Regularly leads=15, Co-leads=10, Mostly participates=5, Unclear=2")
    lead_behavior_reasoning: str = Field(description="Explanation of lead behavior scoring")

    typical_check_size: str = Field(description="Typical check size at seed (e.g., '$2M', '$500K-$1M', 'Unknown')")
    check_size_points: int = Field(ge=0, le=10, description="$1M-$3M=10, $500K-$1M=7, $3M-$5M=8, Other=3")
    check_size_reasoning: str = Field(description="Explanation of check size scoring")

    category_total: int = Field(ge=0, le=25, description="Lead Capability total (lead_behavior_points + check_size_points)")

class ThesisFitScoring(BaseModel):
    """Thesis alignment scoring (0-30 points)."""
    # Portfolio analysis
    ai_b2b_portfolio_count: int = Field(ge=0, description="Number of AI B2B companies in portfolio")
    ai_b2b_companies: List[PortfolioCompany] = Field(default_factory=list)
    ai_b2b_points: int = Field(ge=0, le=12, description="3+ companies=12pts, use judgment for 1-2")

    martech_portfolio_count: int = Field(ge=0, description="Number of MarTech companies in portfolio")
    martech_companies: List[PortfolioCompany] = Field(default_factory=list)
    martech_points: int = Field(ge=0, le=10, description="2+ companies=10pts, use judgment for 1")

    # Thesis analysis
    has_explicit_ai_b2b_thesis: bool = Field(description="Has explicit AI/B2B investment thesis")
    investment_thesis_summary: str = Field(description="Summary of investment thesis with quotes")
    thesis_points: int = Field(ge=0, le=8, description="Explicit AI/B2B thesis=8pts")

    # Focus areas (additive)
    devtools_api_portfolio_count: int = Field(ge=0, description="Number of DevTools/API companies")
    devtools_api_companies: List[PortfolioCompany] = Field(default_factory=list)
    has_devtools_api_focus: bool = Field(description="Has DevTools/API focus")
    devtools_api_points: int = Field(ge=0, le=5, description="DevTools/API focus=5pts")

    plg_portfolio_count: int = Field(ge=0, description="Number of PLG companies")
    plg_companies: List[PortfolioCompany] = Field(default_factory=list)
    has_plg_focus: bool = Field(description="Has PLG (Product-Led Growth) focus")
    plg_points: int = Field(ge=0, le=5, description="PLG focus=5pts")

    thesis_alignment_reasoning: str = Field(description="Overall reasoning for thesis alignment scoring")
    category_total: int = Field(ge=0, le=30, description="Thesis Alignment total (sum of all thesis components, max 30)")

class PartnerValueScoring(BaseModel):
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

class StrategicFactorsScoring(BaseModel):
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
    exit_details: List[ExitDetails] = Field(default_factory=list)

    has_portfolio_followons: bool = Field(description="Portfolio companies raising follow-on rounds")
    followon_details: Optional[str] = Field(default=None, description="Examples of follow-on activity")

    momentum_points: int = Field(ge=0, le=2, description="New fund <18mo=2pts OR 2+ exits in 3yrs=2pts OR Portfolio follow-ons=2pts (pick one)")
    momentum_reasoning: str = Field(description="Explanation of momentum scoring")

    category_total: int = Field(ge=0, le=5, description="Strategic Factors total (geography_points + momentum_points)")

class DisqualificationAnalysis(BaseModel):
    """Disqualification analysis (ONLY for Fund AUM < $20M)."""
    is_disqualified: bool = Field(description="True only if Fund AUM < $20M")
    disqualification_reason: Optional[str] = Field(default=None, description="Reason for DQ (should be 'Fund AUM < $20M' if DQ'd)")

class ActionableIntelligence(BaseModel):
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

class CurrentEmploymentInfo(BaseModel):
    """Current employment verification details."""
    current_fund_name: str = Field(description="Partner's current fund/firm name")
    current_title: str = Field(description="Partner's current title/role")
    is_still_at_input_firm: bool = Field(description="Whether partner is still at the firm provided in input")
    firm_change_detected: bool = Field(description="Whether partner moved to a different firm")
    firm_change_details: Optional[str] = Field(default=None, description="Details of firm change if applicable (e.g., 'Moved from Fund A to Fund B in March 2024')")
    is_still_in_vc: bool = Field(description="Whether partner is still actively in venture capital")
    employment_notes: Optional[str] = Field(default=None, description="Additional employment verification notes")

class InvestorLeadScoringOutput(BaseModel):
    """Complete investor lead scoring output (100-point framework)."""

    # Employment verification (DO THIS FIRST)
    current_employment: CurrentEmploymentInfo

    # Scoring categories (100 points total)
    fund_vitals: FundVitalsScoring  # 0-25 points
    lead_capability: LeadCapabilityScoring  # 0-25 points
    thesis_alignment: ThesisFitScoring  # 0-30 points
    partner_value: PartnerValueScoring  # 0-15 points
    strategic_factors: StrategicFactorsScoring  # 0-5 points

    # Total score and tier
    total_score: int = Field(ge=0, le=100, description="Sum of all category totals (max 100 points)")
    score_tier: Literal["A (85-100)", "B (70-84)", "C (50-69)", "D (<50)"] = Field(description="Tier based on total score")
    recommended_action: Literal["Top Priority", "High Priority", "Medium Priority", "Low Priority"] = Field(description="Action priority based on tier")

    # Disqualification (ONLY for Fund AUM < $20M)
    disqualification: DisqualificationAnalysis

    # Actionable Intelligence (9 sections for pitch prep)
    actionable_intelligence: ActionableIntelligence

    # Supporting data
    notable_portfolio_companies: List[PortfolioCompany] = Field(default_factory=list, max_length=10, description="Top 8-10 notable portfolio companies")

    # Research quality indicators
    research_confidence: Literal["High", "Medium", "Low"] = Field(description="Confidence in research findings")
    missing_critical_info: List[str] = Field(default_factory=list, description="List of critical information not found")
    additional_notes: Optional[str] = Field(default=None, description="Any additional context or notes")

# Generate JSON Schema from Pydantic Model
INVESTOR_LEAD_SCORING_OUTPUT_SCHEMA = InvestorLeadScoringOutput.model_json_schema()
