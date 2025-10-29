# **Investor Lead Scoring Research Brief**

## **Deep Research Protocol for Pre-Seed/Seed Investors**

---

## **🎯 CONTEXT & TASK**

**Mission**: Research and score VC investors (0-100) for a B2B AI/MarTech pre-seed startup raising $500K-$750K.

**Approach**: Complete full scoring across 5 categories + capture actionable intelligence for all investors.

---

## **📊 SCORING FRAMEWORK (100 points max)**

### **A. FUND VITALS (0-25)**

```
Fund Size:
  $200M-$500M = 15 pts
  $500M-$1B = 12 pts
  $100M-$200M = 10 pts
  $50M-$100M = 7 pts
  $20M-$50M = 5 pts
  $10M-$20M = 3 pts
  <$10M = 1 pt

Activity (2024-2025):
  3+ deals in 2025 = 10 pts
  1-2 deals in 2025 = 7 pts
  Active in 2024 only = 4 pts
  No recent activity = 0 pts
```

**Queries**: `"[Fund]" crunchbase fund size` | `"[Fund]" invests 2025`

---

### **B. LEAD CAPABILITY (0-25)**

```
Lead Behavior:
  Regularly leads = 15 pts
  Co-leads = 10 pts
  Mostly participates = 5 pts
  Unclear = 2 pts

Check Size (average cheques):
  $500K-$2M = 10 pts
  $250K-$500K = 6 pts
  $2M-$10M = 2 pts
  >$10M = 0 pts
```

**Queries**: `"[Fund]" led "pre-seed" OR "seed" 2024 OR 2025` | `"[Fund]" check size pre-seed` | `"[Fund]" check size seed`

---

### **C. THESIS ALIGNMENT (0-30)**

```
Portfolio:
  3+ AI B2B companies = 12 pts
  2+ MarTech companies = 10 pts
  Explicit AI/B2B thesis = 8 pts

Focus (additive):
  Dev tools/API = +5 pts
  PLG focus = +5 pts
```

**Queries**: `site:[fund-site.com] portfolio AI B2B MarTech` | `"[Fund]" thesis AI MarTech`

---

### **D. PARTNER VALUE (0-15)**

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

**Queries**: `"[Partner]" "[Fund]" linkedin` | `"[Partner]" CMO OR founder before:[fund]`

**Note**: If partner moved firms, research their CURRENT firm.

---

### **E. STRATEGIC FACTORS (0-5)**

```
Geography:
  US-based = 3 pts
  India-based = 2 pts

Momentum (pick one):
  New fund <18mo = 2 pts
  2+ exits in 3 yrs = 2 pts
  Portfolio follow-ons = 2 pts
```

**Queries**: `"[Fund]" location` | `"[Fund]" portfolio exit OR acquisition`

---

## **📋 OUTPUT FORMAT**

### **Part 1: Score Summary**

```
INVESTOR: [Fund] - [Partner]
SCORE: [XX/100] | TIER: [A/B/C/D]

SCORE BREAKDOWN:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fund Vitals: [XX/25]
  • Fund size: $[X]M = [X] pts
  • Activity: [finding] = [X] pts

Lead Capability: [XX/25]
  • Lead behavior: [finding] = [X] pts  
  • Check size: [finding] = [X] pts

Thesis Alignment: [XX/30]
  • AI B2B: [#] = [X] pts
  • MarTech: [#] = [X] pts
  • Thesis: [finding] = [X] pts
  • Focus: [finding] = [X] pts

Partner Value: [XX/15]
  • Title: [role] = [X] pts
  • Background: [finding] = [X] pts

Strategic: [XX/5]
  • Geography: [location] = [X] pts
  • Momentum: [finding] = [X] pts

TOTAL: [XX/100]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIER: [A: 85-100 | B: 70-84 | C: 50-69 | D: <50]
ACTION: [Top Priority/High Priority/Medium/Low]
```

---

### 

### **Part 2: Actionable Intelligence**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ACTIONABLE INTELLIGENCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. PORTFOLIO PATTERN
[Stage, traction, founder profiles they invest in]

2. PARTNER INSIGHTS
[Recent content, beliefs, what excites them]

3. INVESTMENT PACE & PROCESS
[Deals/quarter, timeline, current urgency, IC process]

4. VALUE-ADD EVIDENCE  
[Specific examples: customer intros, hiring, programs]

5. DEAL PREFERENCES
[Traction bar, team needs, passes on, excited by]

6. RECENT POSITIONING
[Thesis updates, market views - use this language]

7. FUND CONTEXT
[Deployment stage, pressure, team changes]

8. COMPETITIVE INTEL
[Portfolio overlaps, gaps you fill, co-investors]

9. PITCH PREP
• Reference: [Specific portfolio/statement]
• Angle: [How you fit thesis]  
• Opening: [Personalized hook]
```

---

## **⚠️ SPECIAL SITUATIONS**

**Partner moved firms**: Research their CURRENT fund. Note: "Moved from \[Old\] to \[New\] in \[Date\]"

**New fund (\<6mo)**: Don't penalize for no 2025 deals. Score on GP track record \+ thesis.

**Can't find check size**: Estimate: (Fund size ÷ 25 companies) × 0.5 \= typical first check

**Multiple GPs**: Score fund once, note if different partner is better fit

---

## **🚫 CRITICAL RULES**

✅ **No disqualifications**: Score all investors 0-100  
✅ **If partner moved**: Research new firm  
✅ **Use specifics**: Not "helps with hiring" but "Intro'd 15 VP Marketing candidates to portfolio in 2024"  
✅ **Be honest**: Low scores are valuable data, not failures

---

**Output**: Score \+ tier \+ 9 intelligence sections with specific, actionable details for pitch preparation.

## **💡 COMPLETE EXAMPLE**

```
INVESTOR: Acme Ventures - Jane Doe
SCORE: 88/100 | TIER: A

SCORE BREAKDOWN:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fund Vitals: 23/25
  • Fund size: $300M = 15 pts
  • Activity: 4 deals in 2025 = 8 pts

Lead Capability: 22/25
  • Lead behavior: Led 2, co-led 1 in 24-25 = 13 pts
  • Check size: $2M typical = 9 pts

Thesis Alignment: 28/30
  • AI B2B: 5 companies = 12 pts
  • MarTech: 3 companies = 10 pts
  • Thesis: Explicit AI focus = 6 pts
  • Focus: PLG mentioned = 5 pts (minus 5 for no dev tools)

Partner Value: 13/15
  • Title: GP = 8 pts
  • Background: Ex-CMO + active Twitter = 6 pts (minus 1 for no board seats)

Strategic: 5/5
  • Geography: SF = 3 pts
  • Momentum: New fund + 2 exits = 2 pts

TOTAL: 88/100

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIER: A (Top Priority)
ACTION: Hunt warm intro immediately

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ACTIONABLE INTELLIGENCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. PORTFOLIO PATTERN
Jasper (pre-seed), Copy.ai (seed), Writer (Series A). Invests pre-$1M ARR. Prefers technical + marketing co-founder pairs. 75% of portfolio <50 employees.

2. PARTNER INSIGHTS
Feb 2025 tweet: "Future of content is distribution intelligence, not generation."
Writes about AI agents, PLG, GTM efficiency. Sits on Drift board.
Skeptical: AI wrappers, SEO-dependent models.
Excited: Fast time-to-value, bottoms-up → enterprise.

3. INVESTMENT PACE & PROCESS
3 deals in Jan 2025 - aggressive. Fund 6mo old, 25% deployed.
4-6 week process, 2 partner meetings. Weekly IC Thursdays.
Jane champions, needs Tom (co-GP) alignment.

4. VALUE-ADD EVIDENCE
Quarterly CMO dinners (50+ attendees). "GTM Studio": 50+ advisors, 200+ marketer Slack.
Helped Jasper: first 3 sales hires, HubSpot partnership intro.
Portfolio avg: 3-5 customer intros in 90 days.

5. DEAL PREFERENCES
Wants: $50K MRR OR 10K engaged users.
Prefers: Technical co-founder + moat answer ("Why won't ChatGPT build this?")
Passes: Features without distribution moat, SEO-dependent.

6. RECENT POSITIONING
Jan 2025: "AI infrastructure phase for marketing. Distribution is new moat."
Committed to "10 AI marketing investments this fund."
Tweet: "Build distribution engines not writing tools." ← USE THIS LANGUAGE

7. FUND CONTEXT
Fund III $300M (Oct 2024), up from $120M Fund II.
Added Sarah (GP, AI focus). Positioning as "AI-native B2B fund."
Deployment pressure: need velocity + quality signals to LPs.

8. COMPETITIVE INTEL
Portfolio: Copy.ai (SMB), Writer (enterprise).
Your differentiation: LinkedIn-native, mid-market, distribution-first.
No direct conflict. Co-invests with Lightspeed, Sequoia.

9. PITCH PREP
• Reference: "Backed Jasper pre-$1M when others said too early"
• Angle: "We're the distribution engine you tweeted about - LinkedIn-native AI that gets content published, not just generated"
• Opening: "Jane - saw your 'build distribution engines' tweet. We're LinkedIn-native AI for B2B content distribution. [Mutual connection] suggested we connect."
```

---

