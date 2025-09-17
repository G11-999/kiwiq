# Executive AI Visibility Workflow - Evaluation Guidelines

## Overview
The Executive AI Visibility Workflow aims to analyze an executive's presence in AI-powered answer engines by generating targeted queries about their professional profile, executing these queries across multiple AI platforms, and generating a comprehensive visibility intelligence report. The workflow helps executives understand their digital presence in AI systems, identify visibility gaps, assess competitive positioning, and provides actionable recommendations for improving their AI visibility and digital reputation.

## LLM Node Evaluation Guidelines

### 1. Query Generation Node
**Node ID**: `generate_exec_queries`  
**Task Type**: Strategic query generation for AI visibility testing (Medium complexity, Medium variance)

#### What We Are Analyzing
This node analyzes executive profile data to generate authentic, targeted queries that various stakeholders would use when researching the executive on AI platforms, covering expertise, leadership, market position, innovation, and network influence.

#### Ideal Output
- Exactly 10 diverse, natural-language queries distributed across the 5 required categories
- Authentic search queries that mirror real professional research behavior
- Mix of direct name searches, role-based queries, and topical investigations
- Conversational language that people actually use with AI assistants
- Strategic coverage of professional credibility and thought leadership areas

#### Evaluation Parameters
1. **Query Authenticity**: How closely queries match real search behavior patterns used by buyers, partners, and stakeholders
2. **Category Distribution**: Proper distribution across expertise_credibility (2-3), leadership_impact (1-2), market_position (1-2), innovation_vision (1-2), network_influence (1-2)
3. **Language Naturalness**: Use of conversational phrases and natural search patterns rather than formal or robotic language
4. **Strategic Coverage**: Comprehensive coverage of professional areas that matter for executive visibility and credibility
5. **Profile Relevance**: Personalization based on the executive's actual background, expertise, and industry context
6. **Query Diversity**: Appropriate mix of query styles (questions, comparisons, opinion-seeking, fact-finding) without duplicates

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 2. Visibility Report Generation Node
**Node ID**: `generate_exec_report`  
**Task Type**: Multi-platform AI visibility analysis and strategic intelligence synthesis (High complexity, Medium variance)

#### What We Are Analyzing
This node synthesizes search results from multiple AI platforms into a comprehensive visibility intelligence report, analyzing platform performance, competitive positioning, information quality, and providing strategic recommendations for improving AI visibility.

#### Ideal Output
- Comprehensive platform-by-platform analysis with accurate metrics and evidence attribution
- Detailed competitive landscape intelligence with specific competitor mentions and positioning insights
- Evidence-based strategic recommendations with complete SourceEvidence objects for all claims
- Accurate platform rankings with clear justification and performance differentiators
- Actionable immediate actions and long-term strategic recommendations with impact scoring

#### Evaluation Parameters
1. **Evidence Attribution Quality**: Completeness and accuracy of SourceEvidence objects with proper platform attribution, query references, and confidence levels
2. **Platform Analysis Accuracy**: Correct calculation of metrics (coverage_score, depth_score, accuracy_score) and appropriate platform-specific insights
3. **Competitive Intelligence Depth**: Quality of competitor identification, positioning analysis, and differentiation factor assessment
4. **Recommendation Actionability**: Specificity and implementability of strategic recommendations with proper impact scoring and effort assessment
5. **Data Synthesis Quality**: Effective integration of multi-platform results into coherent strategic insights
6. **Information Quality Assessment**: Accurate evaluation of consistency, gaps, and potential misinformation risks

#### Suggested Improvements
[To be filled based on evaluation results]

---

## General Evaluation Considerations

### Quality Thresholds
- **Critical**: Outputs that fail on more than 2 evaluation parameters or lack proper evidence attribution
- **Needs Improvement**: Outputs that fail on 1-2 evaluation parameters or provide incomplete evidence objects
- **Acceptable**: Outputs that meet all evaluation parameters with minor issues in specificity or depth
- **Excellent**: Outputs that exceed expectations with comprehensive evidence attribution and strategic insights

### Evaluation Frequency
- Initial baseline evaluation should be conducted on a sample of 10-15 workflow runs covering different executive profiles
- Regular spot checks should be performed weekly given the dynamic nature of AI platform responses
- Full evaluation should be repeated after any prompt modifications or schema updates
- Special evaluation after significant changes to AI platforms or their response patterns

### Documentation Requirements
- Record examples of authentic vs. artificial query generation patterns
- Document quality of evidence attribution and source tracking across different platforms
- Track consistency of platform performance metrics and competitive analysis accuracy
- Maintain examples of excellent strategic recommendations vs. generic advice
- Monitor platform-specific variations in response quality and coverage

### External Dependency Considerations
- AI platform availability and response quality can vary significantly
- Different platforms may have varying coverage of specific executives or industries  
- Query result quality depends on the executive's existing digital footprint
- Cache settings can affect result freshness and accuracy
- Platform algorithm changes may impact consistency of results over time