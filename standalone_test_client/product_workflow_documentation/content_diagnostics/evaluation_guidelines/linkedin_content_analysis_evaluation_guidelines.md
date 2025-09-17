# LinkedIn Content Analysis Workflow - Evaluation Guidelines

## Overview
The LinkedIn Content Analysis Workflow aims to analyze LinkedIn posts by extracting key content themes, classifying posts into theme groups, and generating detailed performance reports for each theme. The workflow processes posts in batches, identifies exactly 5 distinct themes that represent the author's recurring focus areas, assigns posts to themes with confidence scoring, and produces comprehensive theme-based analysis with actionable insights for content optimization and strategic decision-making.

## LLM Node Evaluation Guidelines

### 1. Theme Extraction Node
**Node ID**: `extract_themes`  
**Task Type**: Content pattern recognition and theme categorization (Medium complexity, Medium variance)

#### What We Are Analyzing
This node analyzes an entire corpus of LinkedIn posts to identify exactly 5 distinct content themes that represent the author's primary focus areas, with each theme being mutually exclusive, substantive, and specific enough to enable strategic content analysis.

#### Ideal Output
- Exactly 5 distinct, high-value content themes with clear differentiation
- Specific theme names (2-3 words) that are immediately recognizable and actionable
- Comprehensive theme descriptions including core topics, strategic intent, content patterns, and distinguishing features
- Balanced theme coverage that can classify 80-90% of posts effectively
- Strategic themes that enable actionable content optimization decisions

#### Evaluation Parameters
1. **Theme Distinctiveness**: Themes have minimal overlap (<20%) and represent genuinely different content categories
2. **Coverage Effectiveness**: Themes collectively cover 80-90% of posts without forcing artificial categorization
3. **Specificity Quality**: Theme names are specific and contextual rather than generic (avoid "Business" or "Life")
4. **Description Completeness**: Each theme description includes core topics, strategic intent, content patterns, audience value, and distinguishing features
5. **Strategic Actionability**: Themes enable meaningful content strategy decisions and optimization opportunities
6. **Balance Assessment**: Reasonable distribution with no theme representing >40% or <10% of expected posts

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 2. Post Classification Node
**Node ID**: `classify_batch`  
**Task Type**: Content classification with confidence scoring (Medium complexity, High variance)

#### What We Are Analyzing
This node classifies batches of 10 LinkedIn posts into the predefined themes using multi-criteria decision making that considers content analysis, intent matching, pattern recognition, and contextual factors.

#### Ideal Output
- Accurate assignment of each post to the most appropriate theme with proper confidence assessment
- Consistent classification patterns across batches and similar content types
- Proper use of "Other" category only when confidence for all themes is below 40%
- Clear, concise reasoning for each classification decision
- Correct post ID mapping using the exact 'urn' values from source posts

#### Evaluation Parameters
1. **Classification Accuracy**: Correctness of theme assignments based on content alignment and strategic intent
2. **Confidence Calibration**: Appropriate confidence scoring that reflects actual fit quality (90-100 for perfect matches, <40 for "Other")
3. **Consistency Maintenance**: Similar posts receive identical classifications across different batches and runs
4. **Reasoning Quality**: Clear, specific explanations for classification decisions with identifiable logic
5. **Schema Compliance**: Proper use of exact post URNs and theme IDs without creating new categories
6. **Edge Case Handling**: Appropriate handling of ambiguous posts and proper "Other" category usage

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 3. Theme Analysis Node
**Node ID**: `analyze_theme_group`  
**Task Type**: Comprehensive performance analysis with data synthesis (High complexity, Medium variance)

#### What We Are Analyzing
This node generates detailed performance analysis for each theme group by examining content quality, structural patterns, engagement mechanics, discovery optimization, timing intelligence, and asset usage to produce actionable strategic recommendations.

#### Ideal Output
- Comprehensive analysis across all required dimensions (content quality, structure, hooks, storytelling, CTAs, keywords, hashtags, engagement, timing, assets)
- Accurate metrics calculated from actual post data with proper citation support
- Prioritized, actionable recommendations with clear impact assessment and implementation guidance
- Evidence-based insights supported by specific post citations and performance data
- Strategic intelligence that identifies both successes to replicate and failures to avoid

#### Evaluation Parameters
1. **Data Accuracy**: Correct calculation of metrics from actual post data with proper statistical analysis
2. **Citation Quality**: Complete, relevant citations with post IDs, dates, and meaningful excerpts that support claims
3. **Recommendation Actionability**: Specific, implementable recommendations with clear impact scores and effort assessments
4. **Analysis Comprehensiveness**: Complete coverage of all required analysis dimensions with strategic depth
5. **Insight Quality**: Evidence-based findings that reveal meaningful patterns and optimization opportunities
6. **Strategic Value**: Analysis enables concrete content strategy decisions and competitive advantage identification

#### Suggested Improvements
[To be filled based on evaluation results]

---

## General Evaluation Considerations

### Quality Thresholds
- **Critical**: Outputs that fail on more than 2 evaluation parameters or lack essential theme distinctiveness/accuracy
- **Needs Improvement**: Outputs that fail on 1-2 evaluation parameters or provide incomplete analysis depth
- **Acceptable**: Outputs that meet all evaluation parameters with minor issues in specificity or citation quality
- **Excellent**: Outputs that exceed expectations with strategic insights and comprehensive evidence-based analysis

### Evaluation Frequency
- Initial baseline evaluation should be conducted on a sample of 12-15 workflow runs covering diverse LinkedIn profiles
- Regular spot checks should be performed weekly to monitor classification consistency and theme quality
- Full evaluation should be repeated after any prompt modifications or schema updates
- Special evaluation when processing significantly different content types or industries

### Documentation Requirements
- Record examples of excellent vs. poor theme extraction with specificity and coverage analysis
- Document classification consistency patterns and edge case handling effectiveness
- Track quality of strategic recommendations and their implementation success rates
- Maintain examples of comprehensive theme analysis vs. surface-level reporting
- Monitor performance of the 5-theme limit and its effectiveness across different content types

### Workflow-Specific Considerations
- Theme extraction quality directly impacts all downstream analysis - prioritize theme evaluation
- Batch processing can introduce consistency issues - monitor cross-batch classification alignment
- Complex schema requirements increase risk of incomplete outputs - verify all required fields are populated
- Multi-model approach (gpt-5 for extraction/analysis, gpt-5-mini for classification) may create inconsistencies
- Private input/output mode for classification may affect debugging and quality assessment