# Blog Content Analysis - Evaluation Guidelines

## Overview
The Blog Content Analysis workflow aims to provide comprehensive insights into a company's blog content portfolio by analyzing posts across multiple dimensions. The workflow crawls blog content, classifies posts into sales funnel stages (Awareness, Consideration, Purchase, Retention), evaluates content quality metrics, identifies topic authority and coverage gaps, and provides technical SEO analysis. The ultimate goal is to deliver actionable strategic recommendations for improving content effectiveness, filling coverage gaps, and optimizing the content portfolio for better search visibility and buyer journey alignment.

## LLM Node Evaluation Guidelines

### 1. Post Classification Node
**Node ID**: `classify_batch`  
**Task Type**: Multi-dimensional classification and scoring (High complexity, High variance)

#### What We Are Analyzing
This node analyzes individual blog posts to classify them into sales funnel stages and evaluate multiple quality dimensions including readability, content depth, E-E-A-T signals, and structural elements.

#### Ideal Output
- Accurate classification into the correct sales funnel stage based on content intent and buyer journey position
- Precise scoring (0-100) across multiple quality dimensions that align with actual content attributes
- Correct identification of structural elements (ToC, FAQ sections)
- Comprehensive topic extraction (primary and secondary topics)

#### Evaluation Parameters
1. **Classification Accuracy**: How accurately the post is assigned to the correct funnel stage (Awareness/Consideration/Purchase/Retention)
2. **Scoring Consistency**: Whether quality scores (readability, clarity, depth, originality) are consistent across similar content and align with objective content analysis
3. **E-E-A-T Assessment Precision**: Accuracy in identifying and scoring expertise, experience, authority, and trustworthiness signals
4. **Topic Extraction Quality**: Relevance and completeness of primary and secondary topics identified
5. **Structural Element Detection**: Accuracy in detecting presence of ToC, FAQ sections, and other structural elements
6. **Cross-batch Consistency**: Scoring consistency when the same post appears in different batches or different runs

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 2. Funnel Stage Analysis Node
**Node ID**: `analyze_funnel_stage_group`  
**Task Type**: Group-level strategic analysis (Medium complexity, Medium variance)

#### What We Are Analyzing
This node analyzes groups of posts within the same funnel stage to identify patterns, themes, content quality trends, and strategic insights specific to that stage.

#### Ideal Output
- Clear identification of dominant narratives and topic clusters within the funnel stage
- Accurate assessment of content quality patterns (information density, writing quality)
- Concrete E-E-A-T signals that are actually present in the content
- Actionable insights about content structure and readability patterns

#### Evaluation Parameters
1. **Theme Extraction Accuracy**: Quality and relevance of identified primary narratives and topic clusters
2. **Pattern Recognition**: Ability to identify meaningful patterns across the post group
3. **Strategic Insight Quality**: Depth and actionability of the inferred content strategy
4. **Evidence Grounding**: Whether identified elements (storytelling, evidence types) are actually present in the analyzed posts

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 3. Portfolio Batch Analysis Node
**Node ID**: `run_portfolio_batch_analysis`  
**Task Type**: Portfolio-level strategic analysis (High complexity, Medium variance)

#### What We Are Analyzing
This node analyzes batches of classified posts (50 posts per batch) to generate portfolio-level insights about content quality, topic authority, and funnel coverage.

#### Ideal Output
- Accurate calculation of average quality metrics across the batch
- Comprehensive topic authority analysis with correct funnel coverage mapping
- Strategic insights that connect individual post quality to portfolio patterns
- Identification of genuine content gaps based on data

#### Evaluation Parameters
1. **Metric Calculation Accuracy**: Correctness of averaged scores and percentages
2. **Topic Authority Assessment**: Quality of topic grouping and authority level assignments (Expert/Strong/Developing/Weak)
3. **Gap Identification Precision**: Accuracy in identifying actual content gaps and coverage issues
4. **Strategic Recommendation Quality**: Relevance and actionability of recommendations
5. **Data Grounding**: Whether insights are properly grounded in the actual post data

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 4. Portfolio Final Synthesis Node
**Node ID**: `run_final_synthesis`  
**Task Type**: Multi-batch synthesis and consolidation (Medium complexity, Low variance)

#### What We Are Analyzing
This node synthesizes multiple batch analysis reports into a single comprehensive portfolio analysis, consolidating insights and deduplicating findings.

#### Ideal Output
- Properly consolidated metrics with correct weighted averaging
- Deduplicated topic authority insights focusing on most significant topics
- Coherent executive summary capturing key strengths and gaps
- Unified strategic recommendations without redundancy

#### Evaluation Parameters
1. **Consolidation Accuracy**: Correctness of merged metrics and averaged scores
2. **Deduplication Quality**: Effectiveness in removing redundant insights while preserving unique findings
3. **Summary Coherence**: Quality and conciseness of the executive summary
4. **Prioritization Logic**: Appropriate prioritization of topics and recommendations

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 5. Technical SEO Analysis Node
**Node ID**: `run_technical_analysis`  
**Task Type**: Technical metrics analysis (Low complexity, Low variance)

#### What We Are Analyzing
This node analyzes technical SEO audit data and robots.txt configuration to identify technical issues, provide fixes, and optimize bot access.

#### Ideal Output
- Accurate technical health scores based on measurable SEO metrics
- Correct identification of critical technical issues with proper severity classification
- Specific, implementable technical fixes with clear metrics
- Appropriate robots.txt recommendations for bot access optimization

#### Evaluation Parameters
1. **Metric Interpretation Accuracy**: Correct analysis of technical SEO metrics and their implications
2. **Issue Prioritization**: Appropriate severity assignment based on SEO impact
3. **Recommendation Specificity**: Clarity and implementability of technical fixes
4. **Robots.txt Analysis Quality**: Accuracy in identifying bot access issues and recommendations

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