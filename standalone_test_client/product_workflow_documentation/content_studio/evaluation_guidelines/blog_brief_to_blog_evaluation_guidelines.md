# Blog Brief to Blog Generation - Evaluation Guidelines

## Overview
The Blog Brief to Blog Generation workflow aims to transform strategic content briefs into complete, SEO-optimized blog posts that align with company brand guidelines and target audience needs. The workflow enriches briefs with domain knowledge from the knowledge base, generates comprehensive content following SEO best practices, incorporates human-in-the-loop approval with iterative feedback processing, and delivers publication-ready blog content that effectively communicates key messages while maintaining brand voice and strategic alignment.

## LLM Node Evaluation Guidelines

### 1. Knowledge Enrichment Node
**Node ID**: `knowledge_enrichment_llm`  
**Task Type**: Strategic knowledge extraction and brief enrichment (High complexity, High variance)

#### What We Are Analyzing
This node searches the company knowledge base to extract relevant information for each section of the blog brief, including product features, company metrics, case studies, expertise insights, and supporting evidence to personalize and strengthen the content.

#### Ideal Output
- Relevant information extracted for each section that aligns with section reasoning
- Concrete data points, metrics, and statistics from company sources
- Specific case studies and customer success stories
- Company expertise and thought leadership insights
- Clear acknowledgment of information gaps when data is unavailable

#### Evaluation Parameters
1. **Search Strategy Effectiveness**: Quality and relevance of search queries based on brief requirements
2. **Information Relevance**: Whether extracted information aligns with section purposes and user questions
3. **Data Accuracy**: Truthfulness and accuracy of extracted metrics, quotes, and examples
4. **Coverage Completeness**: How well all sections of the brief are enriched with relevant information
5. **Source Integration**: Proper presentation of information without revealing document sources
6. **Gap Transparency**: Clear identification of areas where information is unavailable

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 2. Content Generation Node
**Node ID**: `content_generation_llm`  
**Task Type**: Strategic content creation with SEO optimization (High complexity, Medium variance)

#### What We Are Analyzing
This node generates complete blog content from the enriched brief, following SEO best practices, maintaining brand voice, integrating company-specific information naturally, and creating value-driven content that serves the strategic purpose of each section.

#### Ideal Output
- Complete blog post with proper markdown formatting
- Natural integration of company-specific information and data
- Appropriate keyword usage without stuffing
- Consistent tone and voice aligned with brand guidelines
- Strategic alignment with content goals and key takeaways
- No scripts, code, meta commentary, or placeholder text

#### Evaluation Parameters
1. **Strategic Alignment**: How well content serves the documented purpose from the brief
2. **Information Integration**: Natural incorporation of enriched knowledge without forced insertion
3. **SEO Optimization**: Appropriate keyword usage and content structure for search visibility
4. **Brand Consistency**: Adherence to specified tone, voice, and differentiation elements
5. **Content Quality**: Value delivery, readability, and engagement level

#### Suggested Improvements
[To be filled based on evaluation results]

---

### 3. Feedback Analysis Node
**Node ID**: `feedback_analysis_llm`  
**Task Type**: Feedback interpretation and content revision (Medium complexity, Medium variance)

#### What We Are Analyzing
This node analyzes user feedback during the revision process to identify required changes and generate specific update instructions for content regeneration.

#### Ideal Output
- Clear identification of feedback points and required changes
- Specific update instructions for content modification
- Preservation of approved content sections
- Strategic understanding of feedback intent
- Actionable revision guidelines

#### Evaluation Parameters
1. **Feedback Interpretation Accuracy**: Correct understanding of user revision requests
2. **Change Specification Clarity**: Clear and actionable update instructions
3. **Content Preservation**: Appropriate retention of already-approved sections
4. **Revision Scope**: Appropriate scope of changes based on feedback

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
- **Tool Calling Dependency**: Knowledge enrichment quality depends on search_documents tool effectiveness
- **Iteration Limits**: Maximum 10 feedback iterations affects revision depth
- **HITL Integration**: Human approval quality impacts final content quality
- **Version Control**: Document versioning enables tracking of content evolution