# Orchestrator Workflow - Evaluation Guidelines

## Overview
The Orchestrator Workflow serves as the master workflow that coordinates the execution of multiple content analysis workflows in parallel, manages data flow between workflows, and generates comprehensive diagnostic reports. The workflow orchestrates up to 8 different sub-workflows based on input flags, synthesizes their outputs into strategic intelligence reports, and produces final diagnostic summaries for both blog and LinkedIn content strategies. This workflow represents the pinnacle of the content diagnostic system's capabilities.

## LLM Node Evaluation Guidelines

### 1. LinkedIn Report Generation Nodes
**Node IDs**: `generate_linkedin_competitive_intelligence`, `generate_linkedin_content_performance`, `generate_linkedin_strategy_gaps`, `generate_linkedin_strategic_recommendations`, `generate_linkedin_executive_summary`  
**Task Type**: Multi-document synthesis and strategic report generation (High complexity, Medium variance)

#### What We Are Analyzing
These nodes synthesize multiple LinkedIn analysis documents (user profile, content analysis, deep research) into specialized strategic reports including competitive intelligence, performance analysis, strategy gaps, recommendations, and executive summaries.

#### Ideal Output
- Comprehensive competitive intelligence with 5-8 industry peer profiles and actionable content tactics
- Detailed content performance analysis with specific metrics, theme-by-theme breakdowns, and goal alignment assessment
- Strategic gap analysis identifying content opportunities and positioning vulnerabilities
- Prioritized strategic recommendations with specific implementation guidance and impact scoring
- Executive summary that distills key insights into actionable strategic intelligence

#### Evaluation Parameters
1. **Data Synthesis Quality**: Effective integration of multiple data sources without redundancy or conflicting insights
2. **Strategic Intelligence Depth**: Generation of actionable insights that go beyond summarization to provide competitive advantage
3. **Citation Accuracy**: Proper attribution of insights to specific data sources with credible information_source fields
4. **Recommendation Actionability**: Specific, implementable recommendations with clear impact assessment and implementation guidance
5. **Executive Appropriateness**: All content and recommendations suitable for C-level executive positioning
6. **Goal Alignment**: Effective mapping of content strategies to stated business objectives and target personas

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 2. Blog Report Generation Nodes
**Node IDs**: `generate_blog_ai_visibility_report`, `generate_blog_competitive_intelligence`, `generate_blog_performance_report`, `generate_blog_gap_analysis`, `generate_blog_strategic_recommendations`, `generate_blog_executive_summary`  
**Task Type**: Multi-workflow output synthesis for blog strategy intelligence (High complexity, Medium variance)

#### What We Are Analyzing
These nodes synthesize outputs from blog content analysis, competitor analysis, company analysis, AI visibility, and deep research workflows into comprehensive strategic reports covering AI visibility, competitive positioning, performance metrics, gap analysis, recommendations, and executive summaries.

#### Ideal Output
- AI visibility report with platform-specific insights and improvement strategies
- Competitive intelligence highlighting competitor content strategies and differentiation opportunities
- Performance report with detailed metrics, funnel stage analysis, and content effectiveness assessment
- Gap analysis identifying content portfolio weaknesses and strategic positioning vulnerabilities
- Strategic recommendations prioritized by impact with specific implementation pathways
- Executive summary synthesizing key findings into strategic decision-making intelligence

#### Evaluation Parameters
1. **Multi-Workflow Integration**: Seamless synthesis of insights from 5+ different workflow outputs without information conflicts
2. **Strategic Coherence**: Logical flow of insights that builds a comprehensive strategic narrative
3. **Competitive Analysis Depth**: Actionable competitive intelligence that identifies specific advantages and vulnerabilities
4. **Performance Insight Quality**: Data-driven analysis that identifies concrete content optimization opportunities
5. **Recommendation Prioritization**: Clear impact-based prioritization with realistic implementation assessments
6. **Executive Decision Support**: Insights formatted for strategic decision-making at leadership level

#### Suggested Improvements
[To be filled based on evaluation results]

---

## Workflow Orchestration Evaluation Guidelines

### 3. Parallel Workflow Coordination
**Function**: Master orchestration of 8 sub-workflows with parallel execution and synchronization
**Task Type**: Complex workflow orchestration with dependency management (High complexity, Medium variance)

#### What We Are Analyzing
The orchestrator's ability to successfully coordinate parallel execution of multiple analysis workflows, handle timeouts and errors gracefully, manage data dependencies, and ensure all required documents are available for report generation.

#### Ideal Output
- Successful parallel execution of all enabled sub-workflows within timeout limits
- Proper handling of workflow failures without blocking report generation
- Complete document availability for report synthesis phases
- Efficient resource utilization through parallel processing
- Graceful degradation when optional workflows fail

#### Evaluation Parameters
1. **Execution Success Rate**: Percentage of sub-workflows that complete successfully within timeout limits
2. **Error Handling Effectiveness**: Graceful handling of failed workflows without compromising overall execution
3. **Document Availability**: Consistent availability of required documents for report generation phases
4. **Performance Efficiency**: Optimal use of parallel processing to minimize total execution time
5. **Dependency Management**: Proper sequencing and synchronization of workflow dependencies
6. **Timeout Management**: Appropriate timeout settings that balance thoroughness with reliability

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 4. Document Loading and State Management
**Function**: Loading and coordinating documents from multiple workflows for report generation
**Task Type**: Document retrieval and state coordination (Medium complexity, Low variance)

#### What We Are Analyzing
The orchestrator's ability to load documents from completed workflows, handle missing documents gracefully, maintain state consistency across multiple execution paths, and prepare data for report generation.

#### Ideal Output
- Successful loading of all available documents from completed workflows
- Proper handling of missing documents without causing report generation failures
- Consistent state management across LinkedIn and blog execution paths
- Clean data preparation for report generation phases
- Appropriate error reporting for missing critical documents

#### Evaluation Parameters
1. **Document Retrieval Success**: Consistent loading of documents from completed workflows
2. **Missing Document Handling**: Graceful handling of missing documents without workflow failure
3. **State Consistency**: Proper maintenance of workflow state across parallel execution paths
4. **Data Preparation Quality**: Clean, properly formatted data preparation for report generation
5. **Error Communication**: Clear reporting of missing documents and their impact on report completeness
6. **Conditional Logic**: Proper execution of conditional report generation based on available data

#### Suggested Improvements
[To be filled based on evaluation results]

---

## General Evaluation Considerations

### Quality Thresholds
- **Critical**: More than 2 evaluation parameters fail or major workflow orchestration failures occur
- **Needs Improvement**: 1-2 evaluation parameters fail or report quality is significantly compromised
- **Acceptable**: All evaluation parameters met with minor issues in synthesis quality or orchestration efficiency
- **Excellent**: All parameters exceeded with comprehensive strategic intelligence and flawless orchestration

### Evaluation Frequency
- Initial baseline evaluation should be conducted on a sample of 8-12 complete orchestrator runs covering different workflow combinations
- Regular spot checks should be performed twice weekly given the workflow's complexity and dependencies
- Full evaluation should be repeated after any sub-workflow modifications or orchestrator logic changes
- Special evaluation when adding new sub-workflows or changing report generation logic

### Documentation Requirements
- Record examples of successful vs. failed workflow orchestration with root cause analysis
- Document report quality variations based on available input data
- Track synthesis quality across different combinations of available documents
- Maintain examples of excellent strategic intelligence vs. generic summarization
- Monitor timeout effectiveness and workflow completion patterns

### Orchestrator-Specific Considerations
- Total execution time can range from 60-90 minutes depending on enabled workflows
- Multiple model usage (OpenAI for strategic recommendations, Anthropic for other reports) may create consistency issues
- Complex state management across parallel paths increases error potential
- Document availability directly impacts report quality and completeness
- External dependencies from all sub-workflows compound reliability challenges

### Success Metrics
- **Orchestration Success Rate**: Percentage of complete successful orchestrator runs
- **Report Completeness Score**: Average completeness of generated reports based on available data
- **Strategic Intelligence Quality**: Assessment of actionable insights vs. generic recommendations
- **Synthesis Effectiveness**: Quality of multi-document integration and insight generation
- **Execution Efficiency**: Actual vs. optimal execution time for different workflow combinations

### Critical Success Factors
- Proper timeout configuration balancing thoroughness with reliability
- Robust error handling that enables partial success rather than complete failure
- High-quality document synthesis that creates strategic intelligence rather than simple summaries
- Effective parallel processing that maximizes throughput while maintaining data consistency
- Strategic report generation that provides executive-level decision support rather than operational details