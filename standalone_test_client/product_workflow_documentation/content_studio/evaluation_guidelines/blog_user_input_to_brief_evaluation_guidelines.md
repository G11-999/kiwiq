# Blog User Input to Brief - Evaluation Guidelines

## Overview
The Blog User Input to Brief workflow aims to transform user content ideas into comprehensive, research-driven blog briefs through systematic research and strategic topic generation. The workflow conducts Google and Reddit research for real-time insights and authentic user perspectives, generates AI-powered topic suggestions with human selection and feedback incorporation, creates detailed content briefs with SEO optimization and structure guidelines, and includes human-in-the-loop approval with manual editing support and iterative revision capabilities to deliver publication-ready content briefs that address both search intent and user needs.

## LLM Node Evaluation Guidelines

### 1. Google Research Node
**Node ID**: `google_research_llm`  
**Task Type**: Web research and industry intelligence gathering (Medium complexity, Medium variance)

#### What We Are Analyzing
This node conducts comprehensive Google research to gather high-quality web insights, industry trends, and authoritative sources relevant to user content ideas, with clear reasoning and citation for each selected resource.

#### Ideal Output
- Precise research queries that capture relevant aspects of the user's content ideas
- Top 5 most relevant and practical web resources with clear authority and credibility
- Specific citations including quotes, statistics, and key insights from each source
- Clear reasoning explaining why each source was selected and its relevance to user needs
- Proper connection between sources and company positioning or expertise areas
- Identification of themes and "People Also Asked" questions from research

#### Evaluation Parameters
1. **Research Query Quality**: Precision and relevance of search queries to user input and company context
2. **Source Selection Appropriateness**: Quality and credibility of selected web resources
3. **Citation Specificity**: Quality and detail of extracted quotes, statistics, and insights
4. **Reasoning Clarity**: Clear explanation of why each source was chosen and its connection to user needs
5. **Company Alignment**: How well research connects to company positioning and target audience
6. **Practical Value**: Focus on actionable insights rather than theoretical or generic content

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 2. Reddit Research Node
**Node ID**: `reddit_research_llm`  
**Task Type**: Community insight mining and user voice analysis (Medium complexity, High variance)

#### What We Are Analyzing
This node analyzes Reddit discussions to understand authentic user questions, pain points, and language patterns, building on Google research to capture genuine user perspectives and discussion patterns.

#### Ideal Output
- Targeted Reddit search queries that build effectively on Google research insights
- Frequently asked questions extracted from real user discussions
- Grouped question clusters with identified user intent and pain points
- Variations in user language and terminology patterns
- Specific Reddit thread or comment citations as supporting evidence
- Clear connection between user questions and company's strategic goals

#### Evaluation Parameters
1. **Query Strategy Building**: How effectively Reddit searches build on and complement Google research
2. **Question Extraction Quality**: Accuracy in identifying and grouping frequently asked questions
3. **User Intent Recognition**: Understanding of underlying user pain points and motivations
4. **Evidence Documentation**: Quality of citations from specific Reddit threads and comments
5. **Language Pattern Capture**: Effectiveness in documenting authentic user terminology and expressions
6. **Strategic Connection**: Clear link between user questions and company goals or positioning

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 3. Topic Generation Node
**Node ID**: `topic_generation_llm`  
**Task Type**: Strategic topic ideation and content planning (High complexity, Medium variance)

#### What We Are Analyzing
This node synthesizes Google and Reddit research insights to create strategic blog topic ideas that address real search intent, align with company positioning, and offer fresh angles or frameworks.

#### Ideal Output
- 3-5 strategic blog topic suggestions that address both SEO goals and user needs
- Clear reasoning connecting each topic to specific research findings from both sources
- Fresh angles, frameworks, or case study formats that avoid generic approaches
- Alignment with company positioning and expertise areas
- Documentation of which user questions and search intents each topic addresses
- Evidence of how topics showcase company strengths and thought leadership potential

#### Evaluation Parameters
1. **Research Integration Quality**: How well topics synthesize insights from both Google and Reddit research
2. **Strategic Alignment**: Consistency with company positioning, expertise, and content goals
3. **User Need Addressing**: Effectiveness in targeting real user questions and search intent
4. **Differentiation Strategy**: Quality of fresh angles and unique approaches to avoid generic content
5. **Reasoning Traceability**: Clear connection between topics and specific research findings
6. **Thought Leadership Potential**: How well topics position the company as an industry authority

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 4. Topic Feedback Analysis Node
**Node ID**: `analyze_topic_feedback`  
**Task Type**: Feedback interpretation and topic refinement guidance (Medium complexity, Medium variance)

#### What We Are Analyzing
This node analyzes user feedback on topic suggestions to understand preferences and requirements, providing guidance for topic regeneration that maintains research foundation while addressing user concerns.

#### Ideal Output
- Accurate interpretation of user feedback intent and specific preferences
- Clear revision instructions for topic regeneration that maintain research grounding
- Identification of which research insights should be emphasized differently
- Guidance on incorporating feedback while preserving strategic value
- Understanding of what aspects of topics worked well and should be preserved
- Direction for improving topics without losing connection to authentic user needs

#### Evaluation Parameters
1. **Feedback Interpretation Accuracy**: Correct understanding of user preferences and concerns
2. **Research Foundation Preservation**: Maintaining connection to Google and Reddit insights during revisions
3. **Revision Instruction Clarity**: Specific and actionable guidance for topic improvement
4. **Strategic Balance**: Balancing user preferences with research findings and company goals
5. **Value Preservation**: Identifying successful elements to maintain during regeneration
6. **Iterative Learning**: Building on patterns from previous topic suggestions effectively

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 5. Brief Generation Node
**Node ID**: `brief_generation_llm`  
**Task Type**: Comprehensive content brief creation and strategic planning (High complexity, Medium variance)

#### What We Are Analyzing
This node synthesizes all research inputs and the selected topic to create detailed content briefs with comprehensive structure, SEO guidance, research support, and actionable writing instructions.

#### Ideal Output
- Comprehensive content brief with clear reasoning for every structural element
- Detailed content sections with complete research support including statistics, quotes, and sources
- SEO keyword strategy based on authentic user language from Reddit research
- Brand guidelines aligned with company positioning and target audience
- Specific writing instructions with word counts and difficulty level guidance
- Complete synthesis of all research findings into coherent content plan

#### Evaluation Parameters
1. **Research Synthesis Quality**: How effectively all research inputs are integrated into the brief structure
2. **Section Reasoning Depth**: Quality of explanations for why each content section is included
3. **Research Support Comprehensiveness**: Completeness of research material provided for each section
4. **SEO Strategy Integration**: Connection between keyword strategy and authentic user language patterns
5. **Writing Instruction Clarity**: Specificity and actionability of guidance for content creators
6. **Strategic Coherence**: Overall alignment between brief elements and company goals

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 6. Brief Feedback Analysis Node
**Node ID**: `analyze_brief_feedback`  
**Task Type**: Brief revision analysis and improvement guidance (Medium complexity, Medium variance)

#### What We Are Analyzing
This node analyzes user feedback on generated briefs to provide revision instructions that address concerns while maintaining research foundation and strategic alignment.

#### Ideal Output
- Accurate interpretation of feedback intent and specific revision requirements
- Clear revision instructions that maintain research foundation and reasoning quality
- Identification of which sections need adjustment and preservation of successful elements
- Guidance on enhancing research support while incorporating feedback
- Conversational change summary that acknowledges user concerns appropriately
- Structured approach to revision that maintains brief quality and coherence

#### Evaluation Parameters
1. **Feedback Intent Understanding**: Accurate interpretation of user concerns and requirements
2. **Research Foundation Maintenance**: Preservation of research-backed elements during revisions
3. **Revision Instruction Specificity**: Clear guidance on what to change and how to implement changes
4. **User Edit Respect**: Appropriate handling of manual user edits and preserving valuable modifications
5. **Change Summary Quality**: Effectiveness of conversational feedback acknowledgment
6. **Strategic Coherence Preservation**: Maintaining alignment with research and company goals through revisions

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
- **Research Chain Dependencies**: Quality builds sequentially from Google → Reddit → Topics → Brief
- **HITL Integration Points**: Two human selection/approval points affect workflow completion and satisfaction
- **Iteration Limits**: Maximum 10 iterations for both topic and brief feedback affects refinement depth
- **Research Tool Dependencies**: Quality depends on Perplexity's web access and platform availability
- **Manual Edit Handling**: System must preserve user modifications while incorporating feedback
- **Version Control Complexity**: Multiple save points and revision cycles require careful state management
- **Multi-Provider LLM Chain**: Different providers (Perplexity, OpenAI) in sequence affects consistency and handoff quality