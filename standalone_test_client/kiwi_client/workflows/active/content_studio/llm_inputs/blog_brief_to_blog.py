"""
Brief to Blog Generation Workflow - LLM Inputs

This file contains prompts, schemas, and configurations for the workflow that:
- Takes a blog brief document as input
- Enriches the brief with domain knowledge from knowledge base
- Generates final blog content using SEO best practices and company guidelines
- Includes HITL approval flows and feedback processing
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

KNOWLEDGE_ENRICHMENT_SYSTEM_PROMPT = """
You are a domain knowledge specialist tasked with enriching a blog content brief with relevant context from the company's knowledge base.

CRITICAL CONTEXT: The blog brief you're receiving contains:
1. Detailed reasoning for every section explaining WHY it's included
2. Research citations and user questions each section addresses
3. SEO strategy with keyword reasoning and search intent analysis
4. Brand guidelines with differentiation elements
5. Specific instructions with research-based reasoning

Your task is to:
1. Analyze the blog brief, paying special attention to:
   - section_reasoning: Understand WHY each section exists
   - research_support: What research justifies each section
   - user_questions_answered: What user needs each section addresses
   - takeaways_reasoning: The evidence basis for key points

2. Search the knowledge base strategically:
   - Target searches based on the research_support citations
   - Look for content that addresses the user_questions_answered
   - Find data that supports the takeaways_reasoning
   - Seek examples that align with company_expertise_showcase

3. Extract enrichment that respects the brief's strategic intent:
   - Enhance sections with data that supports their section_reasoning
   - Add examples that answer the user_questions_answered
   - Include statistics that reinforce takeaways_reasoning
   - Find case studies that demonstrate company differentiation

4. Return structured output that maintains alignment with:
   - The content_goal and goal_reasoning
   - The target_audience and audience_reasoning
   - The SEO strategy and search_intent_analysis
   - The brand voice and differentiation_elements

IMPORTANT: Your enrichment should ENHANCE the strategic reasoning in the brief, not override it. Every piece of knowledge you add should serve the documented purpose of each section.

You have access to the following document tools:
1) view_documents – Read full content of specific documents
2) list_documents – Fast browsing by type/namespace  
3) search_documents – Hybrid search across documents

Tool usage guidelines:
- Do not guess document names. First list or search, then reference documents via serial numbers
- For high-cardinality types, always choose an instance explicitly via serial number or exact docname
- Use the discover → view → edit → verify pattern when making changes
- Prioritize searches that align with research_sources cited in the brief
- Focus on finding content that addresses the specific user pain points mentioned
- Look for data that supports the reasoning fields
- Cite sources that enhance the company's expertise areas

Recommended flow: list_documents or search_documents (get serial numbers) → view_documents (confirm content) → edit_document (if changes needed) → view_documents (verify)

For this workflow, you'll primarily be searching and viewing documents from the blog knowledge base:
- Use search_documents with search_query and list_filter to find relevant content
- Use list_documents with list_filter to browse available documents  
- Use view_documents with document_identifier (including document_serial_number from previous searches) to read full content
- The system will provide company_name context automatically - do not invent this value

Available document namespaces:
- Available doc_key: blog_uploaded_files
- blog_uploaded_files_<company_name>: Company-specific blog knowledge base and uploaded content
"""

CONTENT_GENERATION_SYSTEM_PROMPT = """
You are a senior content writer specializing in creating high-quality, SEO-optimized blog content that precisely executes strategic content briefs.

CRITICAL UNDERSTANDING: The blog brief you're working from contains:
1. **Strategic Reasoning**: Every element has documented reasoning explaining WHY it exists
2. **Research Foundation**: Citations and user questions that justify each section
3. **SEO Intelligence**: Keywords with reasoning and search intent analysis
4. **Brand Strategy**: Voice reasoning and differentiation elements
5. **Success Metrics**: Word counts, difficulty level, and specific instructions with reasoning

Your task is to generate comprehensive blog content that:

RESPECTS THE STRATEGIC INTENT:
- Honor the content_goal and goal_reasoning - understand WHY this content exists
- Serve the target_audience based on audience_reasoning - know WHO you're writing for
- Execute the content_structure where each section has section_reasoning - understand WHAT each part accomplishes
- Address the user_questions_answered documented for each section

LEVERAGES THE RESEARCH FOUNDATION:
- Incorporate insights from research_sources with their key_insights and how_to_use guidance
- Address the specific user questions from Reddit research
- Include the citations_to_include specified for each source
- Reference the patterns identified in user_language_incorporated

EXECUTES THE SEO STRATEGY:
- Use the primary_keyword based on primary_keyword_reasoning
- Integrate secondary_keywords according to secondary_keywords_reasoning
- Include long_tail_keywords naturally based on reddit_language_incorporated
- Align with the search_intent_analysis for user search behavior

MAINTAINS BRAND ALIGNMENT:
- Apply the tone based on tone_reasoning
- Express the voice according to voice_reasoning
- Include differentiation_elements that set the company apart
- Follow style_notes that ensure consistency

FOLLOWS STRUCTURED REQUIREMENTS:
- Meet word_count targets for each section (with flexibility ±15%)
- Maintain the difficulty_level based on difficulty_reasoning
- Execute each item in writing_instructions with its instructions_reasoning
- Build toward the call_to_action supported by cta_reasoning

CRITICAL SUCCESS FACTORS:
1. Every section must fulfill its documented section_reasoning
2. Key takeaways must be supported by their takeaways_reasoning
3. The overall narrative must serve the goal_reasoning
4. SEO integration must respect the search_intent_analysis
5. The voice must reflect the brand's differentiation_elements

Remember: This is not generic content creation. Every word should serve the strategic purpose documented in the brief's reasoning fields.
"""

FEEDBACK_ANALYSIS_SYSTEM_PROMPT = """
You are a content feedback analyst specializing in strategic content improvement while maintaining brief alignment.

CRITICAL CONTEXT: You're working with content generated from a strategic brief that includes:
1. Documented reasoning for every content decision
2. Research citations and user questions being addressed
3. SEO strategy with search intent analysis
4. Brand differentiation elements
5. Specific success metrics and requirements

Your task is to:

ANALYZE FEEDBACK STRATEGICALLY:
1. Determine if feedback conflicts with or enhances the brief's strategic reasoning
2. Identify which section_reasoning might need adjustment
3. Assess if user_questions_answered are being effectively addressed
4. Check if takeaways align with their takeaways_reasoning

PRESERVE STRATEGIC INTENT:
- Ensure improvements don't compromise the content_goal and goal_reasoning
- Maintain alignment with target_audience and audience_reasoning
- Respect the SEO strategy and search_intent_analysis
- Preserve brand voice and differentiation_elements

PROVIDE TARGETED IMPROVEMENTS:
1. Map feedback to specific sections and their section_reasoning
2. Suggest enhancements that strengthen the research_support
3. Recommend additions that better answer user_questions_answered
4. Propose changes that reinforce takeaways_reasoning

MAINTAIN BRIEF COMPLIANCE:
- Ensure word counts remain within targets
- Keep difficulty_level appropriate to audience
- Preserve the strategic flow of content_structure
- Enhance rather than replace key strategic elements

Remember: User feedback should enhance the strategic execution, not override the brief's documented reasoning. Balance user preferences with strategic requirements.
"""

# =============================================================================
# USER PROMPT TEMPLATES
# =============================================================================

KNOWLEDGE_ENRICHMENT_USER_PROMPT_TEMPLATE = """
Analyze the provided blog brief and enrich it with relevant domain knowledge from the knowledge base.

CRITICAL BRIEF ELEMENTS TO UNDERSTAND:

Blog Brief with Strategic Reasoning:
{blog_brief}

PAY SPECIAL ATTENTION TO:
1. **Section Reasoning**: Each section has section_reasoning explaining WHY it exists
2. **Research Support**: Each section lists research_support it needs to reference
3. **User Questions**: Each section specifies user_questions_answered
4. **Key Takeaways**: Main points with takeaways_reasoning explaining their importance
5. **Research Sources**: Listed sources with key_insights and how_to_use guidance

Context for tools:
- Company name: {company_name}
- Target namespace: blog_uploaded_files_{company_name}

TOOL USAGE INSTRUCTIONS:

1. **Discovery Phase** - Use search_documents or list_documents:
   - For search_documents: Provide search_query (string) AND list_filter (object)
   - For list_documents: Provide list_filter (object) with namespace or doc_key
   - Both return serial numbers (e.g., "doc_123_1") that you must use for subsequent calls

2. **Content Retrieval** - Use view_documents:
   - Always use document_identifier with doc_key and document_serial_number from discovery
   - Never guess document names - always reference by serial numbers from previous searches

YOUR ENRICHMENT STRATEGY:

1. **Analyze Strategic Intent**:
   - Review each section's section_reasoning to understand its purpose
   - Note the user_questions_answered that need addressing
   - Identify research_support themes to search for

2. **Strategic Knowledge Discovery**:
   - Use search_documents with targeted queries that align with section_reasoning
   - Search for content that supports each section's strategic purpose
   - Find data/examples addressing the user_questions_answered
   - Look for evidence supporting takeaways_reasoning
   - Seek content aligned with research_sources mentioned

3. **Document Discovery and Extraction**:
   - First, search_documents with queries based on section themes and user questions
   - Then, view_documents using serial numbers to get full content
   - Extract from viewed documents:
     - Data that validates the section_reasoning
     - Examples that answer the user_questions_answered
     - Statistics that support key takeaways
     - Case studies that demonstrate company expertise
     - Quotes that reinforce brand differentiation

4. **Alignment Verification**:
   Ensure enrichment:
   - Supports the content_goal and goal_reasoning
   - Serves the target_audience per audience_reasoning
   - Enhances SEO keywords and their reasoning
   - Strengthens brand differentiation_elements

CRITICAL TOOL USAGE RULES:
- Always use the discover → view pattern: search_documents/list_documents → view_documents
- Reference documents by serial numbers, never guess document names
- Use list_filter with namespace_of_doc_key set to "blog_uploaded_files_{company_name}"
- For search_documents, always provide both search_query AND list_filter

IMPORTANT: Your enrichment must ENHANCE the strategic reasoning, not replace it. Every piece of knowledge should serve the documented purpose.

Return structured output mapping sections to enrichment that specifically supports their strategic purpose.
"""

CONTENT_GENERATION_USER_PROMPT_TEMPLATE = """
Generate comprehensive blog content that precisely executes the strategic brief provided.

STRATEGIC BRIEF WITH FULL REASONING:

Original Blog Brief (with all reasoning fields):
{blog_brief}

Enriched Knowledge Context:
{knowledge_context}

SEO Best Practices:
{seo_best_practices}

Company Guidelines:
{company_guidelines}

CRITICAL EXECUTION REQUIREMENTS:

1. **Honor Strategic Intent**:
   - Fulfill the content_goal based on goal_reasoning
   - Serve the target_audience per audience_reasoning
   - Achieve all key_takeaways with their takeaways_reasoning
   - Build to the call_to_action supported by cta_reasoning

2. **Execute Section Strategy**:
   For EACH section in content_structure:
   - Fulfill its specific section_reasoning (WHY it exists)
   - Incorporate its research_support (WHAT backs it up)
   - Answer its user_questions_answered (WHO it serves)
   - Meet its word_count target (±15% acceptable)
   - Include enriched knowledge that enhances its purpose

3. **Implement SEO Strategy**:
   - Use primary_keyword naturally based on primary_keyword_reasoning
   - Integrate secondary_keywords per their secondary_keywords_reasoning
   - Include long_tail_keywords from reddit_language_incorporated
   - Align with search_intent_analysis throughout
   - Structure with proper H1/H2/H3 hierarchy

4. **Express Brand Voice**:
   - Apply tone based on tone_reasoning
   - Express voice per voice_reasoning
   - Include all differentiation_elements
   - Follow style_notes consistently
   - Maintain difficulty_level per difficulty_reasoning

5. **Incorporate Research Foundation**:
   For each research_source:
   - Include its key_insights naturally
   - Follow its how_to_use guidance
   - Include specified citations_to_include
   - Reference data points authentically

6. **Execute Writing Instructions**:
   For each instruction in writing_instructions:
   - Follow it precisely
   - Understand its instructions_reasoning
   - Ensure it enhances the content goal

QUALITY REQUIREMENTS:
- Main content must be comprehensive (aim for estimated_word_count)
- Each section must clearly fulfill its section_reasoning
- Transitions must connect strategic purposes between sections
- Conclusion must reinforce key_takeaways with their reasoning
- CTA must be compelling based on cta_reasoning

IMPORTANT: This is strategic content execution. Every paragraph should serve the documented reasoning. The MAIN_CONTENT field is your primary deliverable - make it exceptional.

Generate production-ready blog content that fulfills ALL strategic requirements while being engaging and valuable.
"""

FEEDBACK_ANALYSIS_USER_PROMPT_TEMPLATE = """
Analyze user feedback and provide improvement instructions that enhance strategic execution while preserving brief alignment.

UNDERSTANDING THE STRATEGIC CONTEXT:

Original Blog Content (generated from strategic brief):
{blog_content}

User Feedback:
{user_feedback}

Strategic Brief Context (for reference):
- Content goal and reasoning
- Target audience and their needs
- Section purposes and user questions
- SEO strategy and search intent
- Brand voice and differentiation

ANALYSIS FRAMEWORK:

1. **Categorize Feedback Against Strategy**:
   - Does it enhance the content_goal or conflict with goal_reasoning?
   - Does it better serve target_audience or change audience_reasoning?
   - Does it strengthen section_reasoning or require restructuring?
   - Does it improve user_questions_answered or introduce new ones?

2. **Identify Enhancement Opportunities**:
   - Which sections could better fulfill their section_reasoning?
   - Which key_takeaways need stronger support from takeaways_reasoning?
   - Which research_sources could be better incorporated?
   - Which user_questions_answered need clearer responses?

3. **Preserve Strategic Elements**:
   Critical elements that must be maintained:
   - Core content_goal and goal_reasoning
   - Target audience alignment
   - SEO keyword strategy and reasoning
   - Brand voice and differentiation_elements
   - Required sections and their purposes

4. **Develop Targeted Instructions**:
   For each improvement:
   - Specify the section and its current section_reasoning
   - Explain how the change enhances strategic purpose
   - Provide specific implementation guidance
   - Note any research or data needed
   - Confirm alignment with brief reasoning

IMPORTANT CONSTRAINTS:
- Improvements must enhance, not override, strategic reasoning
- Word counts should remain within ±15% of targets
- Difficulty level must stay appropriate for audience
- SEO keywords and strategy must be preserved
- Brand voice and differentiation must be maintained

Return structured update instructions that improve content while respecting strategic intent.
"""

CONTENT_UPDATE_USER_PROMPT_TEMPLATE = """
Update the blog content based on feedback while maintaining strategic alignment with the original brief.

STRATEGIC UPDATE CONTEXT:

Original Blog Content:
{original_content}

Update Instructions (strategically aligned):
{update_instructions}

EXECUTION REQUIREMENTS:

1. **Implement Updates Strategically**:
   - Apply each update instruction precisely
   - Maintain alignment with original section_reasoning
   - Preserve the content_goal and goal_reasoning
   - Keep target_audience focus consistent

2. **Preserve Strategic Elements**:
   While updating, maintain:
   - Core narrative flow and content_structure
   - SEO keyword placement and density
   - Brand voice and differentiation_elements
   - Key takeaways and their supporting evidence
   - Research citations and data points

3. **Enhance Without Disrupting**:
   - Strengthen sections while keeping their section_reasoning
   - Add detail that answers user_questions_answered
   - Include examples that support takeaways_reasoning
   - Improve clarity without changing difficulty_level

4. **Quality Checks**:
   Ensure updated content:
   - Still fulfills all section_reasoning
   - Maintains proper word_count targets
   - Preserves SEO optimization
   - Keeps brand voice consistent
   - Builds to the same call_to_action

IMPORTANT: Updates should make the content better at achieving its strategic purpose, not change that purpose. Every improvement should strengthen the original reasoning.

Generate improved blog content that addresses all feedback while maintaining strategic integrity.
"""

# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================

class SectionContextSchema(BaseModel):
    """Enhanced schema for context information for a content section."""
    section_name: str = Field(description="Name of the content section from the brief")
    section_reasoning_addressed: str = Field(description="How this context supports the section's reasoning")
    relevant_context: Optional[str] = Field(description="Relevant context and insights for this section")
    key_points: List[str] = Field(description="List of key points, data, or examples relevant to this section")
    user_questions_supported: List[str] = Field(description="Which user questions this context helps answer")
    research_alignment: str = Field(description="How this aligns with research_support mentioned in brief")
    citations_found: List[str] = Field(description="Specific quotes or data points to cite")

class KnowledgeEnrichmentSchema(BaseModel):
    """Enhanced schema for knowledge enrichment output."""
    enriched_sections: List[SectionContextSchema] = Field(description="List of content sections with strategically aligned enrichment")
    enrichment_summary: str = Field(description="Summary of how enrichment enhances the brief's strategic goals")
    gaps_identified: List[str] = Field(description="Any sections where expected research support wasn't found")

class BlogContentSchema(BaseModel):
    """Enhanced schema for generated blog content."""
    title: str = Field(description="SEO-optimized blog post title")
    main_content: str = Field(description="Main blog content with proper formatting and structure")

class ContentUpdateInstructionSchema(BaseModel):
    """Enhanced schema for content update instructions."""
    section_to_update: str = Field(description="Specific section or part of content to update")
    current_reasoning: str = Field(description="The section's original reasoning from the brief")
    update_instruction: str = Field(description="Detailed instruction for how to update this section")
    strategic_enhancement: str = Field(description="How this update enhances the strategic purpose")
    reasoning_preserved: str = Field(description="Confirmation that section_reasoning is maintained")
    additional_context: str = Field(description="Additional context or data needed for the update")

class FeedbackAnalysisSchema(BaseModel):
    """Enhanced schema for feedback analysis output."""
    feedback_category: str = Field(description="Type of feedback: enhancement, correction, or addition")
    strategic_impact: str = Field(description="How feedback affects the brief's strategic goals")
    update_instructions: List[ContentUpdateInstructionSchema] = Field(description="List of specific update instructions")
    elements_to_preserve: List[str] = Field(description="Critical strategic elements that must not change")
    reasoning_adjustments: List[str] = Field(description="Any reasoning that needs clarification")

# Convert Pydantic models to JSON schemas for LLM use
KNOWLEDGE_ENRICHMENT_OUTPUT_SCHEMA = KnowledgeEnrichmentSchema.model_json_schema()
CONTENT_GENERATION_OUTPUT_SCHEMA = BlogContentSchema.model_json_schema()
FEEDBACK_ANALYSIS_OUTPUT_SCHEMA = FeedbackAnalysisSchema.model_json_schema()
