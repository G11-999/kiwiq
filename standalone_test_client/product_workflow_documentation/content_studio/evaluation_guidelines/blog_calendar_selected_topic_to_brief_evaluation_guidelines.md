# Blog Calendar Selected Topic to Brief - Evaluation Guidelines

## Overview
The Blog Calendar Selected Topic to Brief workflow aims to transform pre-selected content calendar topics into comprehensive, research-driven blog content briefs. The workflow conducts extensive web research through Google/Perplexity and community insights via Reddit, synthesizes findings with company context and content strategy playbooks, generates detailed briefs with strategic reasoning for every element, and enables human-in-the-loop editing with iterative feedback processing to deliver publication-ready content briefs that align with strategic objectives and audience needs.

## LLM Node Evaluation Guidelines

### 1. Google Research Node
**Node ID**: `google_research_llm`  
**Task Type**: Web research and competitive intelligence gathering (Medium complexity, Medium variance)

#### What We Are Analyzing
This node conducts comprehensive Google/Perplexity research to gather current trends, statistics, expert opinions, competitor analysis, and content gaps related to the selected topic, providing foundational intelligence for strategic brief development.

#### Ideal Output
- Comprehensive search strategy with varied query approaches
- Trending subtopics and emerging angles in the space
- Detailed competitor content analysis and positioning gaps
- Current statistics, data points, and research findings with sources
- Expert opinions and thought leader perspectives with attribution
- Common user questions and search intent patterns
- Specific actionable insights with relevance scoring and application guidance

#### Evaluation Parameters
1. **Search Strategy Comprehensiveness**: Quality and variety of search queries used to gather diverse perspectives
2. **Competitive Intelligence Depth**: Thoroughness of competitor analysis and identification of positioning opportunities
3. **Data Quality and Attribution**: Accuracy and credibility of statistics, sources, and expert opinions collected
4. **Content Gap Identification**: Effectiveness in finding unaddressed questions and underserved content areas
5. **Insight Actionability**: How well insights translate into specific content development opportunities
6. **Source Diversity**: Balance of authoritative sources, industry reports, and current discussions

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 2. Reddit Research Node
**Node ID**: `reddit_research_llm`  
**Task Type**: Community insight mining and authentic user voice capture (Medium complexity, High variance)

#### What We Are Analyzing
This node analyzes Reddit discussions and community conversations to capture authentic user language, pain points, misconceptions, success stories, and emotional triggers that inform content strategy and ensure authentic audience connection.

#### Ideal Output
- Identification of relevant communities and discussion threads
- Authentic user language patterns and terminology preferences
- Common misconceptions and knowledge gaps to address
- Real-world examples and user-generated case studies
- Emotional triggers and sentiment patterns around the topic
- User objections, concerns, and success stories
- Community insights that reveal unmet needs and authentic perspectives

#### Evaluation Parameters
1. **Community Relevance**: Appropriateness and diversity of Reddit communities analyzed
2. **Language Authenticity Capture**: Effectiveness in documenting genuine user voice and terminology
3. **Pain Point Identification**: Depth of understanding user frustrations and unmet needs
4. **Misconception Recognition**: Accuracy in identifying and documenting user misunderstandings
5. **Emotional Intelligence**: Ability to capture sentiment patterns and emotional triggers
6. **Insight Uniqueness**: Quality of insights not available through formal research channels

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 3. Brief Generation Node
**Node ID**: `brief_generation_llm`  
**Task Type**: Strategic content brief synthesis and planning (High complexity, Medium variance)

#### What We Are Analyzing
This node synthesizes all research inputs, company context, and playbook guidelines to generate comprehensive content briefs with detailed reasoning, strategic alignment, research integration, and actionable guidance for content creators.

#### Ideal Output
- Complete content brief with strategic reasoning for every element
- Seamless integration of Google and Reddit research insights
- Clear content structure with purpose-driven sections and word count guidance
- SEO strategy based on user language patterns and search intent
- Brand guidelines aligned with company positioning and audience expectations
- Competitive differentiation strategy with unique angles and exclusive insights
- Actionable writing instructions with specific examples and data points

#### Evaluation Parameters
1. **Strategic Reasoning Quality**: Depth and logic of reasoning provided for all brief elements
2. **Research Integration Effectiveness**: How well Google and Reddit insights are synthesized into actionable guidance
3. **Content Structure Coherence**: Logical flow and purpose clarity of content sections and organization
4. **SEO Strategy Alignment**: Integration of authentic user language with strategic keyword placement
5. **Differentiation Clarity**: Explicit articulation of unique angles and competitive advantages
6. **Actionability for Writers**: Specificity and clarity of instructions for content creation execution

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 4. Feedback Analysis Node
**Node ID**: `analyze_brief_feedback`  
**Task Type**: Feedback interpretation and revision instruction generation (Medium complexity, Medium variance)

#### What We Are Analyzing
This node analyzes user feedback on generated briefs to understand revision intent, maintain strategic alignment, preserve successful elements, and provide clear implementation guidance for iterative improvements.

#### Ideal Output
- Accurate interpretation of feedback intent and underlying concerns
- Specific revision instructions that maintain research foundation
- Clear identification of elements to preserve, modify, or remove
- Strategic coherence maintenance across revisions
- Priority-ordered implementation guidance
- Consideration of downstream impact on content creation

#### Evaluation Parameters
1. **Feedback Interpretation Accuracy**: Correct understanding of explicit and implicit user requirements
2. **Strategic Preservation**: Ability to maintain research foundation and playbook alignment during revisions
3. **Change Specification Clarity**: Specificity and actionability of revision instructions
4. **Element Triage Effectiveness**: Appropriate decisions on what to preserve, modify, or remove
5. **Coherence Maintenance**: Ensuring revisions work harmoniously with unchanged elements
6. **Implementation Guidance Quality**: Clear priority ordering and practical revision steps

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
- **Research Tool Dependency**: Research quality depends on Perplexity's web access and Reddit content availability
- **Topic Variability**: Performance may vary significantly based on topic complexity and research availability
- **Iteration Limits**: Maximum 10 feedback iterations affects refinement depth
- **HITL Integration**: Human approval quality impacts final brief quality
- **Version Control**: Document versioning enables tracking of brief evolution through iterations