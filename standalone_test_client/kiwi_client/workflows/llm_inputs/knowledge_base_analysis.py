from typing import Dict, Any, Optional, List, Union
import json

# Using Pydantic for easier schema generation
from pydantic import BaseModel, Field


class KnowledgeBaseAnalysisSchema(BaseModel):
    """Generic document analysis schema that adapts based on analysis focus and usage description"""
    
    # Core extracted information
    key_information: Optional[List[str]] = Field(description="Key information extracted relevant to the analysis focus")
    main_themes: Optional[List[str]] = Field(description="Main themes and topics identified in the documents")
    important_details: Optional[List[str]] = Field(description="Important details and specific information found")
    actionable_insights: Optional[List[str]] = Field(description="Actionable insights derived from the analysis")
    
    # Contextual information
    relevant_quotes: Optional[List[str]] = Field(description="Relevant quotes or specific text excerpts")
    data_points: Optional[List[str]] = Field(description="Specific data points, metrics, or factual information")
    recommendations: Optional[List[str]] = Field(description="Recommendations based on the document content")
    
    # Summary and implications
    summary: Optional[str] = Field(description="Overall summary of the document analysis")
    content_implications: Optional[str] = Field(description="How this information should influence content creation")
    focus_area_analysis: Optional[str] = Field(description="Specific analysis related to the requested focus areas")


# Generate JSON schema from the Pydantic model
KNOWLEDGE_BASE_ANALYSIS_JSON_SCHEMA = KnowledgeBaseAnalysisSchema.model_json_schema()


KNOWLEDGE_BASE_ANALYSIS_SYSTEM_PROMPT = """
You are a document analysis and knowledge extraction expert.

Your job is to extract structured data from uploaded documents based on the specific analysis focus and usage context provided.

Usage Context (optional): {usage_description}

Instructions:
• Extract information that is directly relevant to the specified analysis focus
• Adapt your analysis approach based on the usage context
• Never infer or fabricate information - only use what's explicitly present in the documents
• If a field isn't relevant to the focus areas or mentioned in the documents, leave it null
• Focus your extraction on information that will be most useful for the specified usage context
• Match the schema's structure, names, and data types exactly
• Return a single JSON object and nothing else
• MAKE IT A DETAILED DOCUMENT - extract comprehensive information, don't summarize too much, include specific details, examples, and context

Respond only with the requested JSON schema as follows: ```json\n{extraction_schema}\n```
"""


KNOWLEDGE_BASE_ANALYSIS_USER_PROMPT = """
I am uploading documents to help build a knowledge base for content generation. Your task is to extract all relevant information from these documents based on the specified focus areas and usage context.

Usage Context (optional): {usage_description}

Documents to analyze:

{document_content}

Extract the relevant information according to the focus areas and populate the provided schema. Organize the information in a way that will be most useful for the specified usage context.
""" 