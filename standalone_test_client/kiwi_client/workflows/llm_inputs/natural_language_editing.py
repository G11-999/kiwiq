"""
Natural Language Document Editing Prompts and Schemas

This module contains all prompts and schemas used in the natural language document editing workflow.
It supports document operations through natural language commands with human-in-the-loop approval.
"""

from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


DOCUMENTS_KEY_TO_DOCUMENT_CONFIG_MAPPING = """{
  "documents": {
  "linkedin_content_strategy_doc": {
        "docname_template": "linkedin_content_playbook_doc",
        "namespace_template": "linkedin_executive_strategy_{entity_username}",
        "docname_template_vars": {},
        "namespace_template_vars": {"entity_username": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
  },
  "linkedin_content_diagnostic_report_doc": {
        "docname_template": "linkedin_content_diagnostic_report_doc",
        "namespace_template": "linkedin_content_diagnostic_{entity_username}",
        "docname_template_vars": {},
        "namespace_template_vars": {"entity_username": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
  "linkedin_knowledge_base_analysis": {
        "docname_template": "linkedin_knowledge_base_analysis",
        "namespace_template": "linkedin_knowledge_base_{entity_username}",
        "docname_template_vars": {},
        "namespace_template_vars": {"entity_username": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
  },
  "linkedin_uploaded_files": {
        "docname_template": "",
        "namespace_template": "linkedin_uploaded_files_{entity_username}",
        "docname_template_vars": {},
        "namespace_template_vars": {"entity_username": null},
        "is_shared": false,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
  },
  "linkedin_user_profile_doc": {
        "docname_template": "linkedin_executive_profile_doc",
        "namespace_template": "linkedin_executive_profile_namespace_{entity_username}",
        "docname_template_vars": {},
        "namespace_template_vars": {"entity_username": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
  },
  "linkedin_content_analysis_doc": {
        "docname_template": "linkedin_content_analysis_doc",
        "namespace_template": "linkedin_executive_analysis_{entity_username}",
        "docname_template_vars": {},
        "namespace_template_vars": {"entity_username": null},
        "is_shared": false,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
  },
  "linkedin_user_web_audit_doc": {
        "docname_template": "linkedin_executive_web_audit_doc",
        "namespace_template": "linkedin_executive_analysis_{entity_username}",
        "docname_template_vars": {},
        "namespace_template_vars": {"entity_username": null},
        "is_shared": false,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
  "linkedin_user_ai_visibility_test_doc": {
        "docname_template": "linkedin_executive_ai_visibility_test_doc",
        "namespace_template": "linkedin_executive_analysis_{entity_username}",
        "docname_template_vars": {},
        "namespace_template_vars": {"entity_username": null},
        "is_shared": false,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
  "linkedin_scraped_profile_doc": {
        "docname_template": "linkedin_scraped_profile_doc",
        "namespace_template": "linkedin_scraping_results_{entity_username}",
        "docname_template_vars": {},
        "namespace_template_vars": {"entity_username": null},
        "is_shared": false,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
  },
  "linkedin_scraped_posts_doc": {
        "docname_template": "linkedin_scraped_posts_doc",
        "namespace_template": "linkedin_scraping_results_{entity_username}",
        "docname_template_vars": {},
        "namespace_template_vars": {"entity_username": null},
        "is_shared": false,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
  },
  "linkedin_brief": {
        "docname_template": "linkedin_brief_{_uuid_}",
        "namespace_template": "linkedin_content_briefs_{entity_username}",
        "docname_template_vars": {"uuid": null},
        "namespace_template_vars": {"entity_username": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
  },
  "linkedin_draft": {
        "docname_template": "linkedin_draft_{_uuid_}",
        "namespace_template": "linkedin_post_drafts_{entity_username}",
        "docname_template_vars": {"post_uuid": null},
        "namespace_template_vars": {"entity_username": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
  },
  "linkedin_idea": {
        "docname_template": "linkedin_idea_{_uuid_}",
        "namespace_template": "linkedin_content_ideas_{entity_username}",
        "docname_template_vars": {"uuid": null},
        "namespace_template_vars": {"entity_username": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
  },
  "linkedin_writing_style": {
        "docname_template": "linkedin_executive_writing_style_doc",
        "namespace_template": "linkedin_executive_profile_namespace_{entity_username}",
        "docname_template_vars": {},
        "namespace_template_vars": {"entity_username": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
  },
  "linkedin_methodology_implementation_ai_copilot": {
        "docname_template": "linkedin_methodology_implementation_ai_copilot",
        "namespace_template": "linkedin_system_strategy_docs_namespace",
        "docname_template_vars": {},
        "namespace_template_vars": {},
        "is_shared": true,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": true
  },
  "linkedin_building_blocks_content_methodology": {
        "docname_template": "linkedin_building_blocks_content_methodology",
        "namespace_template": "linkedin_system_strategy_docs_namespace",
        "docname_template_vars": {},
        "namespace_template_vars": {},
        "is_shared": true,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": true
  },
  "linkedin_post_evaluation_framework": {
        "docname_template": "linkedin_post_evaluation_framework",
        "namespace_template": "linkedin_system_strategy_docs_namespace",
        "docname_template_vars": {},
        "namespace_template_vars": {},
        "is_shared": true,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": true
  },
  "linkedin_post_scoring_framework": {
        "docname_template": "linkedin_post_scoring_framework",
        "namespace_template": "linkedin_system_strategy_docs_namespace",
        "docname_template_vars": {},
        "namespace_template_vars": {},
        "is_shared": true,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": true
  },
  "linkedin_content_optimization_guide": {
        "docname_template": "linkedin_content_optimization_guide",
        "namespace_template": "linkedin_system_strategy_docs_namespace",
        "docname_template_vars": {},
        "namespace_template_vars": {},
        "is_shared": true,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": true
  },
      "blog_company_doc": {
        "docname_template": "blog_company_doc",
        "namespace_template": "blog_company_profile_{item}",
        "docname_template_vars": {},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_content_strategy_doc": {
        "docname_template": "blog_content_playbook_doc",
        "namespace_template": "blog_company_strategy_{item}",
        "docname_template_vars": {},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_post_catalog_doc": {
        "docname_template": "blog_post_catalog_doc",
        "namespace_template": "blog_content_data_{company_name}",
        "docname_template_vars": {},
        "namespace_template_vars": {"company_name": null},
        "is_shared": false,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_seo_audit_doc": {
        "docname_template": "blog_seo_audit_doc",
        "namespace_template": "blog_analysis_{item}",
        "docname_template_vars": {},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_ai_visibility_test_doc": {
        "docname_template": "blog_ai_visibility_test_doc",
        "namespace_template": "blog_analysis_{item}",
        "docname_template_vars": {},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_analysis_dashboard_doc": {
        "docname_template": "blog_analysis_dashboard_doc",
        "namespace_template": "blog_analysis_dashboard_{company_name}",
        "docname_template_vars": {},
        "namespace_template_vars": {"company_name": null},
        "is_shared": false,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_company_ai_baseline_doc": {
        "docname_template": "blog_company_ai_baseline_doc",
        "namespace_template": "blog_analysis_{item}",
        "docname_template_vars": {},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_enhanced_ai_visibility_deepdive_doc": {
        "docname_template": "blog_enhanced_ai_visibility_deepdive_doc",
        "namespace_template": "blog_content_diagnostic_{company_name}",
        "docname_template_vars": {},
        "namespace_template_vars": {"company_name": null},
        "is_shared": false,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_competitor_content_analysis": {
        "docname_template": "blog_competitor_content_analysis_{item}",
        "namespace_template": "blog_analysis_{item}",
        "docname_template_vars": {"item": null},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_context_package_doc": {
        "docname_template": "blog_context_package_doc",
        "namespace_template": "blog_content_diagnostic_{company_name}",
        "docname_template_vars": {},
        "namespace_template_vars": {"company_name": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_deep_research_report_doc": {
        "docname_template": "blog_deep_research_report_doc",
        "namespace_template": "blog_analysis_{item}",
        "docname_template_vars": {},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_keyword_validation_doc": {
        "docname_template": "blog_keyword_validation_doc",
        "namespace_template": "blog_content_diagnostic_{company_name}",
        "docname_template_vars": {},
        "namespace_template_vars": {"company_name": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_content_diagnostic_report_doc": {
        "docname_template": "blog_content_diagnostic_report_doc",
        "namespace_template": "blog_content_diagnostic_report_{item}",
        "docname_template_vars": {},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_query_management_dashboard_doc": {
        "docname_template": "blog_query_management_dashboard_doc",
        "namespace_template": "blog_ai_query_tracking_{item}",
        "docname_template_vars": {},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_weekly_ai_visibility_report_doc": {
        "docname_template": "blog_weekly_ai_visibility_report_doc",
        "namespace_template": "blog_ai_query_tracking_{item}",
        "docname_template_vars": {},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_query_performance_summary_doc": {
        "docname_template": "blog_query_performance_summary_doc",
        "namespace_template": "blog_ai_query_tracking_{item}",
        "docname_template_vars": {},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_user_schedule_config_doc": {
        "docname_template": "blog_user_schedule_config_doc",
        "namespace_template": "blog_spark_delivery_{item}",
        "docname_template_vars": {},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_spark_content_card": {
        "docname_template": "blog_spark_content_card_{_uuid_}",
        "namespace_template": "blog_spark_delivery_{item}",
        "docname_template_vars": {"_uuid_": null},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_topic_ideas_card": {
        "docname_template": "blog_topic_ideas_{_uuid_}",
        "namespace_template": "blog_content_creation_{item}",
        "docname_template_vars": {"_uuid_": null},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_content_brief": {
        "docname_template": "blog_content_brief_{_uuid_}",
        "namespace_template": "blog_content_creation_{item}",
        "docname_template_vars": {"_uuid_": null},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_improvement_suggestions": {
        "docname_template": "blog_improvement_suggestions_{_uuid_}",
        "namespace_template": "blog_content_creation_{item}",
        "docname_template_vars": {"_uuid_": null},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_post": {
        "docname_template": "blog_post_draft_{item}",
        "namespace_template": "blog_posts_draft_{item}",
        "docname_template_vars": {"item": null},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": true,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_content_analysis_doc": {
        "docname_template": "blog_content_analysis_doc",
        "namespace_template": "blog_analysis_{item}",
        "docname_template_vars": {},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },
      "blog_competitor_ai_visibility_test": {
        "docname_template": "blog_competitor_ai_visibility_test_{item}",
        "namespace_template": "blog_analysis_{item}",
        "docname_template_vars": {"item": null},
        "namespace_template_vars": {"item": null},
        "is_shared": false,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": false
      },

      "blog_seo_best_practices": {
        "docname_template": "seo_best_practices_doc",
        "namespace_template": "blog_seo_guidelines",
        "docname_template_vars": {},
        "namespace_template_vars": {},
        "is_shared": true,
        "is_versioned": false,
        "initial_version": null,
        "schema_template_name": null,
        "schema_template_version": null,
        "is_system_entity": true
      },
    
    "blog_playbook_play_1_problem_authority": {
      "docname_template": "Play 1: The Problem Authority Stack",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_2_category_pioneer": {
      "docname_template": "Play 2: The Category Pioneer Manifesto",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_3_david_goliath": {
      "docname_template": "Play 3: The David vs Goliath Playbook",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_4_practitioners_handbook": {
      "docname_template": "Play 4: The Practitioner's Handbook",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_5_use_case_library": {
      "docname_template": "Play 5: The Use Case Library",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_6_migration_magnet": {
      "docname_template": "Play 6: The Migration Magnet",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_7_integration_authority": {
      "docname_template": "Play 7: The Integration Authority",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_8_vertical_dominator": {
      "docname_template": "Play 8: The Vertical Dominator",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_9_customer_intelligence": {
      "docname_template": "Play 9: The Customer Intelligence Network",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_10_research_engine": {
      "docname_template": "Play 10: The Research Engine",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_11_remote_revolution": {
      "docname_template": "Play 11: The Remote Revolution Handbook",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_12_maturity_model": {
      "docname_template": "Play 12: The Maturity Model Master",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_13_community_roadmap": {
      "docname_template": "Play 13: The Community-Driven Roadmap",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_14_enterprise_translator": {
      "docname_template": "Play 14: The Enterprise Translator",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_15_ecosystem_architect": {
      "docname_template": "Play 15: The Ecosystem Architect",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_16_ai_specialist": {
      "docname_template": "Play 16: The AI Specialist",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_17_efficiency_engine": {
      "docname_template": "Play 17: The Efficiency Engine",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_18_false_start": {
      "docname_template": "Play 18: The False Start Chronicles",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_19_compliance_simplifier": {
      "docname_template": "Play 19: The Compliance Simplifier",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "blog_playbook_play_20_talent_magnet": {
      "docname_template": "Play 20: The Talent Magnet",
      "namespace_template": "blog_playbook_sys",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    }
  }
}
"""

# System prompts for different stages of the workflow
DOCUMENT_EDITING_SYSTEM_PROMPT = """You are an expert document management assistant. You help users answer questions (about their documents or with context from their documents), manage and edit their documents through natural language commands.
Only use the tools to address the user's relevant request about their documents or QA which could be answered with context from their documents.

You have access to the following document tools:
1. view_documents - View content of specific documents
2. search_documents - Search for documents by text queries via hybrid (keyword + vector) search with metadata prefiltering
3. list_documents - List available documents, filtered by metadata e.g. documents in a namespace
4. edit_document - Edit document content (requires user approval - the request will be routed to the user for approval)

## IMPORTANT GUIDELINES:
- Be specific about which documents you're accessing or modifying
- If the user's request is unclear or ambiguous, ask for clarification using the structured output schema.
- You can chain / parallelize multiple tool calls to complete complex requests
- Keep track of the context from previous operations
- When referencing documents from tool call outputs, use the document serial numbers (e.g., 'brief_78_1', 'concept_23_2')

When you need to:
- End the workflow: Set workflow_control.action to "end_workflow". If the user's request is irrelevant, you may instead inform the user and ask for clarification.
- Ask for clarification: Set workflow_control.action to "ask_clarification" and provide the question in workflow_control.clarification_prompt

Current view context and state will be provided to help you understand what documents are currently being viewed or edited.

## Guidelines:
- If user denied tools: Understand why and adjust your approach
- If user provided clarification: Use the new information to better fulfill their request

## Tool Call Output -- aka View Context Format:
The view context contains a mapping of document serial numbers to document information. For example:
- 'brief_78_1': indicates the first brief document in the current view
- 'concept_23_2': indicates the second concept document in the current view

When referencing documents from the tool call outputs, you may use the document serial numbers in your tool calls to reference the documents.

## Structured Output Schema:
{workflow_control_schema}

## Document Config Mapping:

- NOTE: documents can be either high cardinality or unitary, i.e. single document per documet class / key or multiple documents per class / key. Any document in config which has uuid or post_uuid placeholder in docname template is high cardinality.
- keys are doc keys and values are document configs
{document_config_mapping}

## All Document Schemas for reference while editing / fetching information from documents (NOTE: system document schemas are not included):
{all_document_schemas}
"""


DOCUMENT_EDITING_USER_PROMPT_TEMPLATE = """User Request: {user_request}
"""


class SelectionDecision(str, Enum):
    """Enum representing possible decisions after concept evaluation."""
    END_WORKFLOW = "end_workflow"      # Select the highest scoring concept
    ASK_CLARIFICATION = "ask_clarification"  # All concepts below threshold, need new ones


# Schemas for structured outputs
class WorkflowControlSchema(BaseModel):
    """Schema for LLM workflow control decisions."""
    reason: str = Field(
        ...,
        description="Reason for the chosen action"
    )
    action: SelectionDecision = Field(
        ..., 
        description="Action to take: 'end_workflow', 'ask_clarification'"
    )
    clarification_prompt: Optional[str] = Field(
        None,
        description="Question to ask the user if action is 'ask_clarification'"
    )

WORKFLOW_CONTROL_SCHEMA = WorkflowControlSchema.model_json_schema()
