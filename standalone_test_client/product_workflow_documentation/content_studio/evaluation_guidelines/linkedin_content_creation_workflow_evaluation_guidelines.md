# LinkedIn Content Creation Workflow - Evaluation Guidelines

## Overview
The LinkedIn Content Creation Workflow aims to transform LinkedIn content briefs into complete, platform-optimized posts that maintain authentic user voice and strategic alignment. The workflow loads comprehensive context including user profiles, content playbooks, and source briefs, generates LinkedIn-specific content with engagement hooks and strategic structure, provides human-in-the-loop approval with iterative feedback processing, and delivers publication-ready posts that execute brief requirements while optimizing for LinkedIn's algorithm and user behavior patterns.

## LLM Node Evaluation Guidelines

### 1. Content Generation Node
**Node ID**: `generate_content`  
**Task Type**: LinkedIn post creation from brief (High complexity, Medium variance)

#### What We Are Analyzing
This node transforms content briefs into complete LinkedIn posts while maintaining authentic user voice, following platform best practices, and executing brief requirements with precise structure and messaging alignment.

#### Ideal Output
- Complete LinkedIn post that executes brief requirements precisely
- Authentic voice preservation matching user's established style and tone
- Platform optimization with proper formatting, hooks, and engagement tactics
- Accurate adherence to specified word count and structural requirements
- Strategic use of provided evidence and examples without fabrication
- Appropriate hashtag selection and call-to-action implementation

#### Evaluation Parameters
1. **Brief Compliance**: Exact adherence to structure, key messages, word count, and CTA specifications
2. **Voice Authenticity**: Maintenance of user's established tone, style, and relationship with audience
3. **Platform Optimization**: Effective use of LinkedIn-specific formatting and engagement tactics
4. **Content Accuracy**: Use only of provided information without fabrication or addition of new claims
5. **Strategic Structure**: Proper execution of hook, body sections, and CTA as specified in brief
6. **Professional Quality**: Maintaining credibility while optimizing for engagement

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 2. Feedback Analysis Node
**Node ID**: `analyze_user_feedback`  
**Task Type**: Post revision analysis and improvement guidance (Medium complexity, Medium variance)

#### What We Are Analyzing
This node analyzes user feedback on generated LinkedIn posts to provide revision instructions that address concerns while preserving brief compliance, user manual edits, and factual accuracy.

#### Ideal Output
- Accurate interpretation of user feedback intent and specific change requirements
- Clear revision instructions that address feedback while maintaining brief compliance
- Preservation of user manual edits and successful elements not criticized
- Structured guidance that maintains factual accuracy and voice authenticity
- Progressive improvement approach that builds on previous iterations
- Quality validation ensuring core message and strategic value remain intact

#### Evaluation Parameters
1. **Feedback Interpretation Accuracy**: Correct understanding of user's specific change requirements
2. **Brief Compliance Preservation**: Maintaining adherence to original brief requirements through revisions
3. **Manual Edit Respect**: Appropriate preservation of user's direct modifications
4. **Factual Accuracy Maintenance**: Ensuring no new information is fabricated during revisions
5. **Voice Consistency**: Maintaining authentic user voice through revision process
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
- **Brief Dependency**: Quality heavily depends on completeness and clarity of source brief
- **Voice Preservation**: Critical requirement to maintain authentic user voice throughout iterations
- **Platform Specificity**: LinkedIn-specific optimization requirements affect format and structure
- **Manual Edit Handling**: System must preserve user modifications while implementing feedback
- **Iteration Limits**: Maximum 10 feedback iterations affects refinement depth and user satisfaction
- **Multi-Document Context**: Integration of brief, profile, and playbook documents affects consistency
- **Content Boundaries**: Strict requirement to use only provided information without fabrication