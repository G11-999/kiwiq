# Competitor Content Analysis - Evaluation Guidelines

## Overview
The Competitor Content Analysis workflow aims to provide comprehensive competitive intelligence by analyzing competitor content strategies across multiple dimensions. The workflow loads competitor information, performs parallel analysis of each competitor's content approach, evaluates their SEO performance and AI visibility, identifies content gaps and opportunities, and delivers actionable insights about competitive positioning and differentiation strategies to inform content strategy decisions.

## LLM Node Evaluation Guidelines

### 1. Competitor Content Analysis Node
**Node ID**: `analyze_competitor_content`  
**Task Type**: Comprehensive competitive content analysis (High complexity, High variance)

#### What We Are Analyzing
This node performs deep analysis of a competitor's content strategy using Perplexity search, evaluating their content across four sales funnel stages (Awareness, Consideration, Purchase, Retention) and multiple quality dimensions including themes, E-E-A-T signals, content structure, and readability.

#### Ideal Output
- Accurate assessment of content metrics and publishing patterns
- Clear identification of content themes and narratives for each funnel stage
- Evidence-based E-E-A-T analysis with specific signals identified
- Quantitative scoring of content quality dimensions (0-100 scale)
- Strategic insights about competitor positioning and differentiation

#### Evaluation Parameters
1. **Data Accuracy**: Whether content metrics (post counts, publishing frequency) are accurately gathered from competitor sites
2. **Theme Extraction Quality**: Relevance and completeness of identified narratives, topic clusters, and unique angles
3. **E-E-A-T Assessment Precision**: Accuracy in identifying expertise, authority, and trust signals in competitor content
4. **Scoring Consistency**: Whether quality scores (information density, writing quality, readability) are consistent and justified
5. **Strategic Insight Depth**: Quality of inferred content strategy and competitive positioning analysis
6. **Funnel Stage Distribution**: Appropriate categorization of content across the four sales funnel stages

#### Suggested Improvements
[To be filled based on evaluation results]

---

## General Evaluation Considerations

### Quality Thresholds
- **Critical**: Outputs that fail on more than 2 evaluation parameters
- **Needs Improvement**: Outputs that fail on 1-2 evaluation parameters
- **Acceptable**: Outputs that meet all evaluation parameters with minor issues
- **Excellent**: Outputs that exceed expectations on all parameters

### Evaluation Frequency
- Initial baseline evaluation should be conducted on a sample of 10-20 workflow runs
- Regular spot checks should be performed weekly
- Full evaluation should be repeated after any prompt or schema modifications

### Documentation Requirements
- Record specific examples of failures for each parameter
- Document patterns in errors or quality issues
- Track improvement trends over time
- Maintain a log of suggested improvements and their implementation status

### Special Considerations for This Workflow
- **Parallel Processing**: Since competitors are analyzed in parallel, ensure consistency across different competitor analyses
- **Perplexity Search Dependency**: Quality depends on Perplexity's ability to find relevant competitor content
- **Dynamic Competitor Count**: The workflow adapts to varying numbers of competitors (typically 3-5)
- **Storage Pattern**: Each competitor gets a separate document, so evaluation should consider individual document quality