# LinkedIn Alternate Text Suggestion Workflow - Evaluation Guidelines

## Overview
The LinkedIn Alternate Text Suggestion Workflow aims to generate creative alternative text suggestions for selected portions of LinkedIn content through personalized content generation. The workflow loads user DNA (content playbook) for voice and style personalization, generates multiple creative alternatives that maintain context and narrative flow, includes human-in-the-loop approval with feedback capability, and supports iterative refinement based on user feedback (maximum 5 iterations) to deliver alternative text options that seamlessly integrate with the complete post while preserving user voice and intent.

## LLM Node Evaluation Guidelines

### 1. Content Generation Node
**Node ID**: `generate_content`  
**Task Type**: Creative text generation with voice preservation (Medium complexity, High variance)

#### What We Are Analyzing
This node generates creative alternative text suggestions for selected portions of LinkedIn content while maintaining consistency with overall content tone, incorporating user DNA for personalization, and ensuring seamless integration with surrounding content.

#### Ideal Output
- 3-4 distinct alternative phrasings that maintain original meaning and intent
- Perfect alignment with surrounding content flow and narrative consistency
- Clear reflection of user's writing style and tone preferences from user DNA
- Stylistic variations that offer different approaches while preserving context
- Smooth transitions that integrate naturally with complete post structure
- Clear, impactful alternatives that enhance rather than disrupt content quality

#### Evaluation Parameters
1. **Voice Preservation Quality**: How well alternatives maintain user's established writing style and tone
2. **Context Integration**: Seamless flow with surrounding content before and after selected text
3. **Meaning Preservation**: Accuracy in maintaining original intent while offering stylistic variation
4. **Creative Variation**: Diversity of approaches while staying within appropriate style boundaries
5. **User DNA Application**: Effective incorporation of personalization preferences from content playbook
6. **Transition Smoothness**: Natural integration that doesn't disrupt overall post readability

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 2. Feedback Analysis Node
**Node ID**: `analyze_feedback`  
**Task Type**: Feedback interpretation and improvement guidance (Medium complexity, Medium variance)

#### What We Are Analyzing
This node analyzes user feedback on alternative text suggestions to understand specific requirements and preferences, providing clear instructions for improvement while maintaining context and user style preferences.

#### Ideal Output
- Accurate summary of user's key feedback points and concerns
- Specific identification of improvement areas that address user requirements
- Clear, actionable rewriting instructions that maintain original intent
- Understanding of how feedback relates to overall context and style preferences
- Recognition of patterns across feedback iterations for cumulative improvement
- Balanced approach that preserves successful elements while addressing concerns

#### Evaluation Parameters
1. **Feedback Interpretation Accuracy**: Correct understanding of user's specific concerns and requests
2. **Improvement Area Identification**: Precise recognition of what aspects need refinement
3. **Instruction Clarity**: Specificity and actionability of rewriting guidance provided
4. **Context Awareness**: Understanding of how feedback affects overall flow and style consistency
5. **Iterative Learning**: Building on previous feedback rounds for cumulative improvement
6. **Balance Preservation**: Maintaining successful elements while addressing specific concerns

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
- **Creative Temperature**: High temperature (1.0) setting affects variability and requires careful evaluation for consistency
- **User DNA Dependency**: Quality heavily depends on user content playbook completeness and specificity
- **Context Preservation**: Selected text must integrate perfectly with surrounding content flow
- **Iteration Limits**: Maximum 5 feedback iterations affects refinement depth and user satisfaction
- **Voice Consistency**: Critical requirement to maintain user's established writing style and tone
- **HITL Feedback Quality**: Success depends on user's ability to provide specific, actionable feedback
- **Model Performance**: GPT-5 usage affects output quality and creative variation capabilities