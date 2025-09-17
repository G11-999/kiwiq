# Deep Research Workflow - Evaluation Guidelines

## Overview
The Deep Research Workflow aims to perform comprehensive strategic intelligence analysis using OpenAI's o4-mini-deep-research model with web search capabilities. The workflow can execute blog content strategy research, LinkedIn executive research, or both simultaneously, providing deep insights into market dynamics, competitive positioning, industry trends, and strategic positioning opportunities. The ultimate goal is to deliver actionable strategic intelligence that reveals competitive advantages, execution barriers, and market positioning opportunities for content strategy and executive thought leadership.

## LLM Node Evaluation Guidelines

### 1. Content Strategy Research Node
**Node ID**: `deep_researcher_content_strategy`  
**Task Type**: Deep strategic analysis with web search integration (High complexity, Medium variance)

#### What We Are Analyzing
This node conducts comprehensive research on blog content strategy using web search to gather current market intelligence, analyze industry best practices, research competitive positioning, and develop strategic intelligence for content advantage.

#### Ideal Output
- Comprehensive industry-specific buyer journey stage analysis with detailed strategic rationales
- Strategic intelligence on content mix optimization with specific scoring and competitive advantages
- Deep competitive positioning insights with specific vulnerabilities and differentiation opportunities  
- Actionable decision intelligence including the 3 battles to win, 1 position to own, and 5 strategic moves
- Evidence-based recommendations grounded in real market research and competitor analysis

#### Evaluation Parameters
1. **Strategic Intelligence Depth**: Quality of strategic insights that explain WHY and HOW certain strategies work, not just WHAT to do
2. **Market Research Integration**: Effective use of web search capabilities to gather current, relevant market intelligence and competitive data
3. **Industry-Specific Adaptation**: Accuracy in identifying and mapping industry-specific buyer journey stages rather than generic SaaS funnels
4. **Competitive Analysis Quality**: Depth and actionability of competitor vulnerability analysis and differentiation opportunities
5. **Decision Intelligence Clarity**: Specificity and actionability of the 3 battles, 1 position, and 5 moves framework
6. **Evidence Grounding**: All recommendations supported by specific citations, data points, and source attribution

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 2. LinkedIn Research Node
**Node ID**: `deep_researcher_linkedin`  
**Task Type**: LinkedIn competitive intelligence with peer analysis (Medium complexity, Medium variance)

#### What We Are Analyzing
This node performs deep research on LinkedIn executive strategy by analyzing comparable peers, identifying high-leverage tactics, researching industry trends, and developing audience intelligence specific to the executive's industry and positioning.

#### Ideal Output
- Comprehensive peer benchmarking with 5-10 relevant executives (excluding the user) with accurate engagement metrics
- Industry-specific high-leverage tactics tailored to the user's role and capabilities
- Relevant macro and micro trends specific to the user's industry sector
- Credible narrative hooks aligned with the user's unique background and expertise
- Detailed audience personas with platform-specific content preferences

#### Evaluation Parameters
1. **Peer Selection Quality**: Relevance and comparability of selected peers in similar roles, industries, and company stages
2. **Tactic Specificity**: Industry-specific adaptation of high-leverage tactics rather than generic LinkedIn advice
3. **Trend Relevance**: Currency and relevance of identified trends to the user's specific industry context
4. **Narrative Hook Credibility**: Alignment of narrative hooks with user's actual background, expertise, and market positioning
5. **Audience Intelligence Depth**: Specificity and actionability of persona analysis including pain points and content preferences
6. **Source Integration**: Effective use of web search to gather current LinkedIn strategy intelligence and competitive insights

#### Suggested Improvements
[To be filled based on evaluation results]

---

## General Evaluation Considerations

### Quality Thresholds
- **Critical**: Outputs that fail on more than 2 evaluation parameters or lack strategic depth
- **Needs Improvement**: Outputs that fail on 1-2 evaluation parameters or provide generic rather than strategic intelligence
- **Acceptable**: Outputs that meet all evaluation parameters with minor gaps in depth or specificity
- **Excellent**: Outputs that exceed expectations with deep strategic insights and comprehensive competitive intelligence

### Evaluation Frequency
- Initial baseline evaluation should be conducted on a sample of 8-12 workflow runs covering both research types
- Regular spot checks should be performed bi-weekly given the external data dependency
- Full evaluation should be repeated after any prompt modifications or model updates
- Special evaluation after significant market changes that might affect research quality

### Documentation Requirements
- Record specific examples of strategic insights vs. generic recommendations
- Document effectiveness of web search integration and source quality
- Track consistency of industry-specific adaptations across different companies
- Maintain examples of excellent competitive intelligence vs. surface-level analysis
- Monitor and document model performance with complex strategic synthesis tasks

### External Dependency Considerations
- Web search availability and quality can impact research depth
- Market volatility may affect consistency of competitive intelligence
- Industry-specific research quality may vary based on available online sources
- Consider external factors when evaluating research completeness and accuracy