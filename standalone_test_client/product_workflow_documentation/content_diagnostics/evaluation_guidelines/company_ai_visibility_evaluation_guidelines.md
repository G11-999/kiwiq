# Company AI Visibility - Evaluation Guidelines

## Overview
The Company AI Visibility workflow aims to assess and optimize a company's presence and positioning in AI-powered answer engines (Perplexity, Google AI, OpenAI). The workflow performs competitive analysis, generates strategic queries to test visibility across different content categories, executes these queries on AI platforms, and produces comprehensive reports analyzing the company's AI visibility performance, competitive positioning, and strategic improvement opportunities.

## LLM Node Evaluation Guidelines

### 1. Competitive Analysis Node
**Node ID**: `competitive_analysis_llm`  
**Task Type**: Market intelligence and competitive positioning (High complexity, High variance)

#### What We Are Analyzing
This node performs comprehensive competitive analysis using company documentation to identify market position, core offerings, value propositions, and competitive dynamics for the target company and its top 3 competitors.

#### Ideal Output
- Evidence-based market positioning with specific source references
- Clear identification of core offerings and unique value propositions
- Accurate competitor analysis with demonstrable threats and vulnerabilities
- Strategic implications grounded in documented evidence
- Explicit information gaps acknowledged

#### Evaluation Parameters
1. **Evidence Quality**: Whether claims are properly supported with source references and verbatim quotes from documentation
2. **Competitive Accuracy**: Correctness of competitor identification and market positioning analysis
3. **Strategic Insight Depth**: Quality and actionability of strategic implications and recommendations
4. **Information Gap Recognition**: Appropriate identification of missing critical information
5. **Differentiation Clarity**: Clear articulation of unique value propositions vs competitors

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 2. Blog Coverage Query Generation Node
**Node ID**: `generate_blog_queries`  
**Task Type**: Strategic query generation for content visibility testing (Medium complexity, Medium variance)

#### What We Are Analyzing
This node generates 15 authentic search queries across 5 categories (industry insights, educational guides, problem solutions, thought leadership, comparative analysis) to test blog content visibility in AI responses.

#### Ideal Output
- Natural, user-authentic queries that real users would search
- Balanced distribution across all 5 required categories
- Mix of query formats (questions, statements, comparisons)
- Industry-specific terminology properly incorporated
- Appropriate specificity levels from broad to narrow

#### Evaluation Parameters
1. **Query Authenticity**: Whether queries reflect real user search behavior and intent
2. **Category Balance**: Appropriate distribution across the 5 specified categories
3. **Format Diversity**: Good mix of questions (40%), how-to (30%), comparisons (20%), trends (10%)
4. **Relevance to Company**: Queries align with company's industry, offerings, and competitive context

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 3. Company Comparison Query Generation Node
**Node ID**: `generate_company_comp_queries`  
**Task Type**: Buyer journey query generation (Medium complexity, Medium variance)

#### What We Are Analyzing
This node generates 15 buyer research queries across 5 categories (discovery research, capability assessment, competitive comparison, implementation technical, validation proof) to test company vs competitor visibility.

#### Ideal Output
- Queries reflecting actual buyer research patterns during vendor evaluation
- Coverage of different buyer journey stages (awareness to decision)
- Multiple stakeholder perspectives (technical, business, user)
- Mix of direct entity, comparison, and evaluation queries
- Risk and compliance considerations included

#### Evaluation Parameters
1. **Buyer Journey Alignment**: Queries accurately map to buyer research stages
2. **Stakeholder Coverage**: Appropriate representation of different decision-maker perspectives
3. **Comparison Quality**: Effective competitive comparison queries that reveal differentiation
4. **Technical Depth**: Appropriate technical and implementation queries for evaluation

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 4. Blog Coverage Report Generation Node
**Node ID**: `generate_blog_coverage_report`  
**Task Type**: Comprehensive visibility analysis and reporting (High complexity, High variance)

#### What We Are Analyzing
This node analyzes blog coverage query results from AI platforms to generate detailed visibility reports with metrics, competitive analysis, content gaps, and strategic recommendations.

#### Ideal Output
- Accurate visibility metrics with clear calculation methodology
- Every finding includes specific query citations and evidence
- Platform-specific analysis with unique insights
- Actionable recommendations with expected impact scores
- Competitive positioning clearly articulated with evidence

#### Evaluation Parameters
1. **Query Citation Completeness**: Every finding properly cites the queries that revealed it
2. **Metric Calculation Accuracy**: Visibility scores and metrics correctly calculated from data
3. **Evidence Grounding**: All claims supported by specific platform results and positions
4. **Recommendation Quality**: Strategic recommendations are specific, actionable, and evidence-based
5. **Competitive Analysis Depth**: Thorough analysis of competitor performance with query evidence
6. **Gap Identification Precision**: Content gaps accurately identified with affected queries listed

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 5. Company Comparison Report Generation Node
**Node ID**: `generate_company_comp_report`  
**Task Type**: Competitive positioning analysis and reporting (High complexity, High variance)

#### What We Are Analyzing
This node analyzes company comparison query results to generate comprehensive competitive positioning reports with head-to-head comparisons, market positioning analysis, and strategic recommendations.

#### Ideal Output
- Clear competitive positioning with win/loss analysis
- Feature and capability comparisons grounded in query results
- Market perception insights with evidence
- Strategic differentiation opportunities identified
- Implementation and integration insights documented

#### Evaluation Parameters
1. **Positioning Accuracy**: Correct assessment of company vs competitor positioning in AI responses
2. **Evidence Quality**: Strong query citations and platform-specific evidence for all findings
3. **Differentiation Analysis**: Clear identification of competitive advantages and weaknesses
4. **Strategic Insight Value**: Quality and actionability of competitive intelligence
5. **Market Perception Assessment**: Accurate analysis of how AI platforms perceive the company

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