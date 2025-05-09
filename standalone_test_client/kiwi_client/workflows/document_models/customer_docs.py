# User DNA
USER_DNA_DOCNAME = "user_dna_doc"
USER_DNA_NAMESPACE_TEMPLATE = "user_strategy_{item}"
USER_DNA_IS_VERSIONED = True

# Content Strategy
CONTENT_STRATEGY_DOCNAME = "content_strategy_doc"
CONTENT_STRATEGY_NAMESPACE_TEMPLATE = "user_strategy_{item}"
CONTENT_STRATEGY_IS_VERSIONED = True

# LinkedIn scraping

LINKEDIN_SCRAPING_NAMESPACE_TEMPLATE = "scraping_results_{item}"
LINKEDIN_PROFILE_DOCNAME = "linkedin_scraped_profile_doc"  # item refers to entity name input to workflow
LINKEDIN_POST_DOCNAME = "linkedin_scraped_posts_doc"  # item refers to entity name input to workflow

# User Preferences

USER_PREFERENCES_DOCNAME = "user_preferences_doc"
USER_PREFERENCES_NAMESPACE_TEMPLATE = "user_inputs_{item}"
USER_PREFERENCES_IS_VERSIONED = True

# Content Drafts
CONTENT_DRAFT_DOCNAME = "draft_{item}"
CONTENT_DRAFT_NAMESPACE_TEMPLATE = "post_drafts_{item}"
CONTENT_DRAFT_IS_VERSIONED = True

# Content Brief
CONTENT_BRIEF_DOCNAME = "brief_{_uuid_}"
CONTENT_BRIEF_NAMESPACE_TEMPLATE = "content_briefs_{item}"
CONTENT_BRIEF_IS_VERSIONED = True
CONTENT_BRIEF_DEFAULT_VERSION = "draft"
CONTENT_BRIEF_FINAL_VERSION = "final"

# Namespace and docname for storing the final content analysis result
CONTENT_ANALYSIS_DOCNAME = "content_analysis_doc"
CONTENT_ANALYSIS_NAMESPACE_TEMPLATE = "user_analysis_{item}" # {item} will be entity_name

# User Source Analysis
USER_SOURCE_ANALYSIS_DOCNAME = "user_source_analysis"
USER_SOURCE_ANALYSIS_NAMESPACE_TEMPLATE = "user_analysis_{item}"
USER_SOURCE_ANALYSIS_IS_VERSIONED = True

# Uploaded Files
UPLOADED_FILES_NAMESPACE_TEMPLATE = "uploaded_files_{item}"

# Core Beliefs and Perspectives
CORE_BELIEFS_PERSPECTIVES_DOCNAME = "core_beliefs_perspectives_doc"
CORE_BELIEFS_PERSPECTIVES_NAMESPACE_TEMPLATE = "user_inputs_{item}"
CORE_BELIEFS_PERSPECTIVES_IS_VERSIONED = True

# Content Pillars
CONTENT_PILLARS_DOCNAME = "content_pillars_doc"
CONTENT_PILLARS_NAMESPACE_TEMPLATE = "user_inputs_{item}"
CONTENT_PILLARS_IS_VERSIONED = True

# Content Concept
CONCEPT_DOCNAME = "concept_{_uuid_}"
CONCEPT_NAMESPACE_TEMPLATE = "content_concepts_{item}"
CONCEPT_IS_VERSIONED = True

# System Strategy Documents
METHODOLOGY_IMPLEMENTATION_DOCNAME = "methodology_implementation_ai_copilot"
METHODOLOGY_IMPLEMENTATION_NAMESPACE_TEMPLATE = "system_strategy_docs_namespace"
METHODOLOGY_IMPLEMENTATION_IS_SHARED = True
METHODOLOGY_IMPLEMENTATION_IS_SYSTEM_ENTITY = True

BUILDING_BLOCKS_DOCNAME = "building_blocks_content_methodology"
BUILDING_BLOCKS_NAMESPACE_TEMPLATE = "system_strategy_docs_namespace"
BUILDING_BLOCKS_IS_SHARED = True
BUILDING_BLOCKS_IS_SYSTEM_ENTITY = True

LINKEDIN_POST_EVALUATION_DOCNAME = "linkedin_post_evaluation_framework"
LINKEDIN_POST_EVALUATION_NAMESPACE_TEMPLATE = "system_strategy_docs_namespace"
LINKEDIN_POST_EVALUATION_IS_SHARED = True
LINKEDIN_POST_EVALUATION_IS_SYSTEM_ENTITY = True

LINKEDIN_POST_SCORING_DOCNAME = "linkedin_post_scoring_framework"
LINKEDIN_POST_SCORING_NAMESPACE_TEMPLATE = "system_strategy_docs_namespace"
LINKEDIN_POST_SCORING_IS_SHARED = True
LINKEDIN_POST_SCORING_IS_SYSTEM_ENTITY = True

LINKEDIN_CONTENT_OPTIMIZATION_DOCNAME = "linkedin_content_optimization_guide"
LINKEDIN_CONTENT_OPTIMIZATION_NAMESPACE_TEMPLATE = "system_strategy_docs_namespace"
LINKEDIN_CONTENT_OPTIMIZATION_IS_SHARED = True
LINKEDIN_CONTENT_OPTIMIZATION_IS_SYSTEM_ENTITY = True
