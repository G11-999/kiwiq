# LinkedIn Content Calendar Entry - Evaluation Guidelines

## Overview
The LinkedIn Content Calendar Entry workflow aims to generate strategic LinkedIn content topic suggestions for specified time periods (default 2 weeks) through personalized content planning. The workflow loads comprehensive user context including strategy documents, user profiles, and historical content for personalization, generates themed topic clusters based on posting frequency preferences and content pillars, creates 4 interconnected topic variations per theme optimized for LinkedIn engagement, and manages scheduling across preferred posting days with timezone awareness to deliver a balanced content calendar aligned with strategic priorities and user voice.

## LLM Node Evaluation Guidelines

### 1. Topic Generation Node
**Node ID**: `generate_topics`  
**Task Type**: Strategic LinkedIn topic ideation and calendar planning (High complexity, High variance)

#### What We Are Analyzing
This node generates themed topic clusters for LinkedIn content calendar, creating 4 interconnected topic variations per theme that align with user's content strategy, expertise areas, and posting preferences while maintaining voice consistency and strategic alignment.

#### Ideal Output
- Exactly 4 unified topic ideas around one common theme from user's content pillars
- Clear alignment with specific strategic plays from content strategy
- Appropriate scheduling across preferred posting days within 2-week timeframe
- Topics that leverage user's demonstrated expertise and address audience needs
- Complementary topic angles that provide comprehensive theme coverage
- Strategic objective alignment with clear explanation of topic importance

#### Evaluation Parameters
1. **Theme Coherence**: How well the 4 topics unite around a common strategic theme
2. **Strategy Alignment**: Consistency with user's content pillars, expertise areas, and strategic plays
3. **Voice Preservation**: Maintenance of user's established tone and style from historical content
4. **Scheduling Accuracy**: Appropriate date/time selection respecting timezone and posting preferences
5. **Audience Value**: Relevance to target audience needs and pain points
6. **Topic Complementarity**: How effectively the 4 topics work together for comprehensive coverage

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
- **Multi-Context Loading**: Quality depends on comprehensive context loading from multiple document types
- **Historical Content Integration**: Effectiveness in using scraped posts and drafts for voice consistency
- **Timezone Complexity**: Accurate handling of timezone conversions and daylight saving time
- **Posting Schedule Compliance**: Adherence to user's preferred posting days and optimal timing windows
- **Creative Temperature**: High temperature (1.0) affects output variability and requires evaluation for strategic consistency
- **Theme Consistency**: Critical requirement for 4 topics to work cohesively around unified theme
- **Calendar Management**: Workflow handles deletion and recreation of calendar entries affecting version control