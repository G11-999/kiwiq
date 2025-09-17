# Blog Content Playbook Generation - Evaluation Guidelines

## Overview
The Blog Content Playbook Generation workflow aims to create comprehensive, customized blog content strategies by analyzing company context and diagnostic reports to identify strategic needs and content gaps. The workflow selects appropriate content plays from a library of proven strategies, generates detailed implementation plans with specific topics and timelines, incorporates human approval for play selection and playbook refinement, and delivers actionable blog content playbooks that combine multiple strategic plays to achieve business goals through coordinated content creation.

## LLM Node Evaluation Guidelines

### 1. Play Selection Node
**Node ID**: `play_suggestion_llm`  
**Task Type**: Strategic content play selection and analysis (High complexity, High variance)

#### What We Are Analyzing
This node analyzes company documents and diagnostic reports to select 4-5 complementary content plays from a library of 13 strategic options, ensuring plays work together as a cohesive strategy addressing different business goals and content gaps.

#### Ideal Output
- Selection of 4-5 strategically diverse plays that complement each other
- Data-driven reasoning citing specific metrics and findings from source documents
- Clear source path attribution for each selection decision
- Overall strategy notes explaining how plays work together
- Correct play IDs matching available plays exactly

#### Evaluation Parameters
1. **Strategic Diversity**: Whether selected plays address different goals and avoid redundancy
2. **Evidence Quality**: Strength of data-driven reasoning with specific metrics and source citations
3. **Source Attribution Accuracy**: Correct document paths and sections referenced for each decision
4. **Play Complementarity**: How well selected plays work together as a cohesive strategy
5. **Business Alignment**: Alignment of play selection with identified business goals and gaps
6. **ID Validity**: Correct matching of play IDs to available plays

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 2. Playbook Generator Node
**Node ID**: `playbook_generator_llm`  
**Task Type**: Customized playbook creation with implementation details (High complexity, High variance)

#### What We Are Analyzing
This node generates a comprehensive blog content playbook by synthesizing selected plays with company-specific context, creating detailed implementation strategies, content formats, success metrics, timelines, and example topics for each play.

#### Ideal Output
- Customized implementation strategy for each selected play
- Specific blog post topics and angles aligned with company context
- Realistic publishing timeline with milestones for 3 months
- Clear success metrics for tracking performance
- Actionable next steps and overall recommendations
- Proper source path attribution for all strategic decisions

#### Evaluation Parameters
1. **Implementation Specificity**: Concreteness and actionability of implementation strategies
2. **Topic Relevance**: Quality and relevance of example blog topics to company needs
3. **Timeline Feasibility**: Realistic and achievable publishing schedules
4. **Source Attribution Quality**: Accuracy of document paths for implementation decisions
5. **Strategic Coherence**: How well the playbook integrates multiple plays into unified strategy

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 3. Feedback Management Node
**Node ID**: `feedback_management_llm`  
**Task Type**: Feedback interpretation and playbook revision (Medium complexity, Medium variance)

#### What We Are Analyzing
This node analyzes user feedback to determine appropriate actions (direct update, clarification needed, or additional information required) and generates specific instructions for playbook modification while maintaining strategic coherence.

#### Ideal Output
- Correct action decision based on feedback clarity and scope
- Clear, concise clarification questions when needed
- Specific step-by-step modification instructions
- Appropriate play IDs when new plays are requested
- Preservation of strategic coherence during revisions

#### Evaluation Parameters
1. **Feedback Interpretation Accuracy**: Correct understanding of user revision requests
2. **Action Decision Quality**: Appropriate routing based on feedback type
3. **Instruction Clarity**: Specificity and actionability of modification instructions
4. **Play ID Accuracy**: Correct identification of plays to add or replace when requested

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
- **Play Library Dependency**: Quality depends on the 13 predefined strategic plays available
- **Diagnostic Report Influence**: Presence/absence of diagnostic report affects strategy depth
- **HITL Integration**: Human approval at two stages impacts final quality
- **Iteration Limits**: Maximum 30 feedback iterations allows extensive refinement
- **Document Search Capability**: Tool calling enables additional context gathering