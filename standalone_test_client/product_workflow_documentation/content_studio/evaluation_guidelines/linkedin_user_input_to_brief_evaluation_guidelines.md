# LinkedIn User Input to Brief - Evaluation Guidelines

## Overview
The LinkedIn User Input to Brief workflow aims to create strategic LinkedIn content briefs based on executive profiles and content strategy through systematic topic generation and knowledge-based research. The workflow loads executive profiles and content playbooks for strategic context, generates diverse topic suggestions with content type recommendations and reasoning, performs targeted knowledge base research for selected topics, creates comprehensive LinkedIn-specific briefs with platform optimization, and includes human-in-the-loop approval with revision capabilities to deliver strategic blueprints for executive thought leadership content.

## LLM Node Evaluation Guidelines

### 1. Topic Generation Node
**Node ID**: `topic_generation_llm`  
**Task Type**: Strategic LinkedIn topic ideation (High complexity, Medium variance)

#### What We Are Analyzing
This node generates strategic topic suggestions with unique angles based on user input, executive profile characteristics, and content strategy alignment, providing clear reasoning for topic selection and angle differentiation.

#### Ideal Output
- 5 distinct topic suggestions with unique and differentiated angles
- Clear reasoning explaining relevance to user input and target audience
- Strategic angle reasoning that demonstrates differentiation and resonance potential
- Overall strategy reasoning connecting topics to business goals and market opportunities
- Alignment with executive expertise areas and content pillars
- Balance of thought leadership value with practical application

#### Evaluation Parameters
1. **Topic Relevance**: How well topics address user input while leveraging executive expertise
2. **Angle Differentiation**: Uniqueness and strategic value of proposed angles for each topic
3. **Reasoning Quality**: Depth and logic of explanations for topic and angle selection
4. **Strategic Alignment**: Consistency with executive profile and content strategy objectives
5. **Audience Value**: Potential for topics to solve real problems or address burning questions
6. **Platform Optimization**: Appropriateness for LinkedIn's professional context and engagement patterns

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 2. Knowledge Base Query Node
**Node ID**: `knowledge_base_query_llm`  
**Task Type**: Targeted research strategy and information gathering (Medium complexity, Medium variance)

#### What We Are Analyzing
This node develops targeted search strategies for knowledge base research, identifying information gaps and focusing on high-value research areas that support content development with clear reasoning for research approach.

#### Ideal Output
- Strategic search queries that target specific information needs
- Well-defined content focus areas critical for the selected topic
- Appropriate research depth specification based on content requirements
- Clear query strategy reasoning explaining information gap targeting
- Focus area reasoning demonstrating critical importance for content piece
- Balanced approach prioritizing relevance over volume

#### Evaluation Parameters
1. **Search Strategy Effectiveness**: Quality and specificity of search queries for information discovery
2. **Focus Area Relevance**: Appropriateness of research areas for supporting content development
3. **Research Depth Planning**: Correct assessment of detail level needed for content quality
4. **Query Strategy Reasoning**: Logic and clarity of explanations for research approach
5. **Information Gap Identification**: Accuracy in identifying what knowledge is needed
6. **Content Support Alignment**: How well research strategy supports selected topic and angle

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 3. Brief Generation Node
**Node ID**: `brief_generation_llm`  
**Task Type**: Comprehensive LinkedIn brief creation with strategic reasoning (High complexity, Medium variance)

#### What We Are Analyzing
This node synthesizes research findings, executive profile, and content strategy to create detailed LinkedIn content briefs with comprehensive reasoning, structural guidance, and platform optimization.

#### Ideal Output
- Complete content brief with strategic reasoning for all elements
- Well-defined target audience with clear selection reasoning and pain point identification
- Structured outline with reasoning for hooks, frameworks, and engagement tactics
- Message hierarchy with clear prioritization reasoning
- Platform-specific optimization including hashtags and CTAs
- Research summary demonstrating effective knowledge integration

#### Evaluation Parameters
1. **Research Integration Quality**: Effective synthesis of knowledge base findings into brief structure
2. **Strategic Reasoning Depth**: Quality of explanations for audience selection, message hierarchy, and content approach
3. **Platform Optimization**: LinkedIn-specific formatting and engagement strategy appropriateness
4. **Executive Voice Alignment**: Consistency with executive profile characteristics and expertise areas
5. **Content Structure Logic**: Coherence and strategic flow of outlined content structure
6. **Actionability for Writers**: Clarity and completeness of guidance for content creation

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 4. Brief Feedback Analysis Node
**Node ID**: `analyze_brief_feedback`  
**Task Type**: Feedback interpretation and brief revision guidance (Medium complexity, Medium variance)

#### What We Are Analyzing
This node analyzes user feedback on generated briefs to provide revision instructions that maintain strategic value while addressing user concerns and preserving manual edits.

#### Ideal Output
- Accurate interpretation of user feedback intent and specific requirements
- Clear revision instructions that maintain brief quality while addressing concerns
- Preservation of successful elements and user manual edits
- Strategic coherence throughout revision process
- Progressive improvement approach building on previous iterations
- Clear change summary acknowledging user feedback appropriately

#### Evaluation Parameters
1. **Feedback Interpretation Accuracy**: Correct understanding of user concerns and revision requirements
2. **Strategic Value Preservation**: Maintenance of brief quality and strategic reasoning through revisions
3. **Manual Edit Respect**: Appropriate handling of user modifications while incorporating feedback
4. **Revision Instruction Clarity**: Specificity and actionability of guidance for brief improvement
5. **Executive Voice Consistency**: Maintaining alignment with executive profile through revision process
6. **Progressive Enhancement**: Building upon successful elements while addressing specific concerns

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
- **Executive Profile Dependency**: Quality heavily depends on executive profile completeness and strategic clarity
- **Knowledge Base Integration**: Effectiveness relies on targeted research strategy and information synthesis
- **HITL Selection Points**: Two human interaction points (topic selection and brief approval) affect workflow completion
- **Multiple Content Types**: System must handle diverse LinkedIn content formats appropriately
- **Iteration Management**: Multiple iteration limits (3 for regeneration, 10 for feedback) affect refinement depth
- **Strategic Reasoning Requirements**: High-level reasoning expected throughout all outputs
- **LinkedIn Platform Specificity**: Content must be optimized for LinkedIn's professional context and algorithm