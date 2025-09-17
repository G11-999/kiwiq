# Blog Content Calendar Entry - Evaluation Guidelines

## Overview
The Blog Content Calendar Entry workflow aims to generate strategic blog content topic suggestions for specified time periods (default 2 weeks) through a comprehensive theme-driven approach. The workflow analyzes company context and content strategy documents, generates strategic themes based on play weightages and content gaps, conducts targeted web research for each theme to uncover user perspectives and market opportunities, generates 4 topic variations per theme to provide diverse content options, and creates a balanced content calendar that aligns with strategic priorities while addressing authentic user needs.

## LLM Node Evaluation Guidelines

### 1. Theme Suggestion Node
**Node ID**: `theme_suggestion_llm`  
**Task Type**: Strategic theme selection and content planning (High complexity, Medium variance)

#### What We Are Analyzing
This node analyzes content playbook priorities, previous topic distribution, and strategic objectives to select the most impactful theme for the next blog content cycle, providing research guidance and differentiation angles.

#### Ideal Output
- Strategic reasoning that considers play weightages and content gap analysis
- Selected theme that aligns with high-priority plays and fills identified gaps
- Clear play alignment with understanding of strategic importance
- Specific research domains and platforms for targeted investigation
- Focused research areas that will yield actionable content insights
- Differentiation angle that distinguishes from competitor content and previous coverage

#### Evaluation Parameters
1. **Strategic Reasoning Quality**: Depth of analysis considering play weightages, content gaps, and timing
2. **Theme Selection Optimization**: Appropriateness of chosen theme based on strategic priorities and previous coverage
3. **Research Direction Specificity**: Clarity and actionability of research domains and focus areas
4. **Play Alignment Accuracy**: Correct understanding and application of playbook structure and priorities
5. **Differentiation Strategy**: Effectiveness of proposed angle to distinguish from competitors and previous content
6. **Research Guidance Actionability**: Quality of guidance for downstream research activities

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 2. Research Node
**Node ID**: `research_llm`  
**Task Type**: Targeted audience intelligence and market analysis (Medium complexity, High variance)

#### What We Are Analyzing
This node conducts focused web research on the selected theme to uncover authentic user perspectives, pain points, trending discussions, competitive gaps, and unique content opportunities that inform topic generation.

#### Ideal Output
- Executive summary capturing overall user sentiment and key findings
- Specific user questions with frequency and platform context
- Validated pain points with evidence and content opportunity connections
- Current trending discussions and emerging themes within the topic area
- Identified competitive gaps and underserved content areas
- Unique angles and differentiated perspectives for content approach
- Recommended content depth levels for different audience segments

#### Evaluation Parameters
1. **User Voice Authenticity**: Quality of captured real user discussions and perspectives
2. **Pain Point Validation**: Accuracy and evidence quality for identified user challenges
3. **Trend Identification Relevance**: Timeliness and significance of trending discussions discovered
4. **Competitive Gap Analysis**: Effectiveness in identifying underexplored content opportunities
5. **Insight Actionability**: How well research findings translate into specific content opportunities
6. **Evidence Quality**: Credibility and specificity of sources and supporting evidence

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 3. Topic Generation Node
**Node ID**: `generate_topics`  
**Task Type**: Research-driven topic ideation and content planning (High complexity, Medium variance)

#### What We Are Analyzing
This node transforms research insights and strategic context into 4 interconnected blog topics that comprehensively cover the selected theme, address specific user needs, and align with content strategy objectives.

#### Ideal Output
- Coherent topic set reasoning explaining how 4 topics work together
- Well-researched individual topics addressing specific user questions or pain points
- Strategic scheduling appropriate for content frequency and timing requirements
- Clear theme alignment with play objectives and strategic priorities
- Defined content journey stage and audience targeting
- SEO-optimized titles that balance optimization with reader appeal
- Comprehensive descriptions connecting research insights to content value

#### Evaluation Parameters
1. **Topic Set Coherence**: How well the 4 topics work together to provide comprehensive theme coverage
2. **Research Integration Effectiveness**: Quality of connection between research insights and proposed topics
3. **Strategic Alignment**: Consistency with playbook priorities, objectives, and content strategy
4. **Scheduling Logic**: Appropriateness of dates based on frequency requirements and current timeline
5. **Audience Targeting Specificity**: Clarity and accuracy of target audience segment identification
6. **Content Value Articulation**: Effectiveness in communicating topic value and reader outcomes

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

### Workflow-Specific Considerations
- **Theme Iteration Dependency**: Topic quality depends on effective theme selection and research quality
- **Research Tool Effectiveness**: Research quality varies based on Perplexity's web access and platform availability
- **Calendar Management**: Workflow manages deletion and recreation of calendar entries, affecting version control
- **Topic Quantity Requirements**: System generates 4 topics per theme with potential for additional iterations
- **Strategic Balance**: Need to balance play weightages with content diversity and timing considerations
- **Date Logic Complexity**: Scheduling logic must handle initial generation vs. additional iterations appropriately