from uuid import UUID
from typing import Dict, Tuple
from scripts.initial_setup.file_config_schema import (
    UserDnaDocModel,
    ContentStrategyDocModel,
    UserSourceAnalysisModel,
    UploadedFilesModel,
    CoreBeliefsPerspectivesDocModel,
    ContentPillarsDocModel,
    UserPreferencesDocModel,
    ContentAnalysisDocModel,
    LinkedInScrapedProfileDocModel,
    LinkedInScrapedPostsDocModel,
    MethodologyImplementationAICopilotModel,
    BuildingBlocksContentMethodologyModel,
    LinkedInPostEvaluationFrameworkModel,
    LinkedInPostScoringFrameworkModel,
    LinkedInContentOptimizationGuideModel,
)



class DocumentConfigManager:
    _configs: Dict[str, Tuple[str, bool, type]] = {
        "user_dna_doc": ("user_strategy_{entity_username}", False, UserDnaDocModel),
        "content_strategy_doc": ("user_strategy_{entity_username}", False, ContentStrategyDocModel),
        "user_source_analysis": ("user_analysis_{entity_username}", False, UserSourceAnalysisModel),
        "uploaded_files": ("uploaded_files_{entity_username}", False, UploadedFilesModel),
        "core_beliefs_perspectives_doc": ("user_inputs_{entity_username}", False, CoreBeliefsPerspectivesDocModel),
        "content_pillars_doc": ("user_inputs_{entity_username}", False, ContentPillarsDocModel),
        "user_preferences_doc": ("user_inputs_{entity_username}", False, UserPreferencesDocModel),
        "content_analysis_doc": ("user_analysis_{entity_username}", False, ContentAnalysisDocModel),
        "linkedin_scraped_profile_doc": ("scraping_results_{entity_username}", False, LinkedInScrapedProfileDocModel),
        "linkedin_scraped_posts_doc": ("scraping_results_{entity_username}", False, LinkedInScrapedPostsDocModel),
        "methodology_implementation_ai_copilot": ("system_strategy_docs_namespace", True, MethodologyImplementationAICopilotModel),
        "building_blocks_content_methodology": ("system_strategy_docs_namespace", True, BuildingBlocksContentMethodologyModel),
        "linkedin_post_evaluation_framework": ("system_strategy_docs_namespace", True, LinkedInPostEvaluationFrameworkModel),
        "linkedin_post_scoring_framework": ("system_strategy_docs_namespace", True, LinkedInPostScoringFrameworkModel),
        "linkedin_content_optimization_guide": ("system_strategy_docs_namespace", True, LinkedInContentOptimizationGuideModel),
    }

    @classmethod
    def get_config(cls, docname: str, user_id: UUID, entity_username: str, data: str) -> Tuple[str, dict]:
        if docname not in cls._configs:
            raise ValueError(f"Unknown document type: {docname}")

        namespace_template, is_system_entity, config_model = cls._configs[docname]
        namespace = namespace_template.format(entity_username=entity_username)

        config_data = {
            "schema_template_name": None,
            "schema_template_version": None,
            "is_system_entity": is_system_entity,
            "data": data,
        }

        # Only add `on_behalf_of_user_id` if `is_system_entity` is False
        if not is_system_entity:
            config_data["on_behalf_of_user_id"] = str(user_id)

        config_instance = config_model(**config_data)

        return namespace, config_instance.model_dump(exclude_none=True)