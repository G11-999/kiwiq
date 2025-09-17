# LinkedIn Content Playbook Generation - Evaluation Guidelines

## Overview
The LinkedIn Content Playbook Generation workflow aims to create personalized LinkedIn content strategies by analyzing user profiles and diagnostic reports to understand professional positioning and content opportunities. The workflow selects appropriate content plays from a library of 10 LinkedIn-specific strategies, generates detailed implementation plans with posting schedules and content themes, incorporates human approval for strategic alignment, and delivers actionable LinkedIn playbooks that combine multiple plays to build thought leadership and professional influence through consistent, strategic content creation.

## LLM Node Evaluation Guidelines

### 1. Play Selection Node
**Node ID**: `play_suggestion_llm`  
**Task Type**: Strategic LinkedIn play selection based on professional profile (High complexity, High variance)

#### What We Are Analyzing
This node analyzes LinkedIn profile documents and optional diagnostic reports to select 3-5 complementary content plays from 10 LinkedIn-specific strategies, ensuring plays align with the user's professional brand, industry position, and career objectives.

#### Ideal Output
- Selection of 3-5 strategically aligned plays that fit the user's professional persona
- Profile-driven reasoning citing specific aspects of user's background and goals
- Clear connection between selected plays and user's industry/role
- Overall strategy notes explaining personal brand development approach
- Correct play IDs matching available LinkedIn plays exactly

#### Evaluation Parameters
1. **Profile Alignment**: How well selected plays match user's professional background and role
2. **Personal Brand Coherence**: Whether plays work together to build consistent professional identity
3. **Industry Relevance**: Appropriateness of plays for user's industry and target audience
4. **Strategic Diversity**: Balance between different content types and engagement strategies
5. **Evidence Quality**: Strength of reasoning based on profile analysis
6. **ID Validity**: Correct matching of play IDs to available LinkedIn plays

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 2. Playbook Generator Node
**Node ID**: `playbook_generator_llm`  
**Task Type**: Personalized LinkedIn playbook creation with implementation details (High complexity, High variance)

#### What We Are Analyzing
This node generates a comprehensive LinkedIn content playbook by synthesizing selected plays with user's professional context, creating specific content themes, posting schedules, engagement strategies, and example post topics that align with LinkedIn best practices.

#### Ideal Output
- Personalized implementation strategy for each selected play
- Specific LinkedIn post topics and angles aligned with professional brand
- Realistic posting schedule optimized for LinkedIn algorithm
- Clear engagement metrics and growth targets
- Platform-specific best practices and formatting guidelines
- Actionable next steps for immediate implementation

#### Evaluation Parameters
1. **Personalization Quality**: How well strategies are customized to user's specific profile
2. **Content Theme Relevance**: Alignment of post topics with professional expertise
3. **LinkedIn Optimization**: Adherence to platform best practices and algorithm considerations
4. **Schedule Feasibility**: Realistic posting frequency for user's capacity
5. **Engagement Strategy Depth**: Quality of community building and interaction tactics

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 3. Feedback Management Node
**Node ID**: `feedback_management_llm`  
**Task Type**: Feedback interpretation and LinkedIn playbook revision (Medium complexity, Medium variance)

#### What We Are Analyzing
This node analyzes user feedback to determine appropriate actions and generates specific instructions for playbook modification while maintaining LinkedIn platform best practices and personal brand consistency.

#### Ideal Output
- Correct action decision based on feedback scope and clarity
- Targeted clarification questions when needed
- Specific modification instructions preserving LinkedIn optimization
- Appropriate play IDs when new strategies are requested
- Maintenance of personal brand coherence during revisions

#### Evaluation Parameters
1. **Feedback Interpretation Accuracy**: Correct understanding of LinkedIn-specific revision requests
2. **Platform Awareness**: Preservation of LinkedIn best practices during modifications
3. **Instruction Specificity**: Clear, actionable steps for playbook updates
4. **Brand Consistency**: Maintaining professional identity through revisions

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
- **LinkedIn Play Library**: Quality depends on the 10 predefined LinkedIn-specific plays
- **Profile Document Quality**: Depth of profile information affects strategy personalization
- **Platform Evolution**: LinkedIn algorithm and best practices change frequently
- **Professional Context**: B2B focus requires different evaluation than B2C content
- **Engagement Metrics**: LinkedIn-specific metrics differ from other platforms