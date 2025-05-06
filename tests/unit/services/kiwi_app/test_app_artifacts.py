import unittest
import uuid
import json # For loading the provided JSON strings
import re # Import re for re.escape
from typing import Dict, Any, List, Optional, Set
from copy import deepcopy
from pydantic import ValidationError

# Modules to test
from services.kiwi_app.workflow_app.app_artifacts import (
    PartialFormatter,
    UserDocumentConfig,
    UserDocumentsConfig,
    AppWorkflow,
    FILENAME_REF_PATTERN 
)

# Complex JSON objects provided by the user
USER_DOCUMENTS_CONFIG_JSON_STR = """
{
  "documents": {
    "user_dna_doc": {
      "docname_template": "user_dna_doc_{entity_username}",
      "namespace_template": "user_strategy",
      "docname_template_vars": {"entity_username": null},
      "namespace_template_vars": {},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "content_strategy_doc": {
      "docname_template": "content_strategy_doc_{entity_username}",
      "namespace_template": "user_strategy",
      "docname_template_vars": {"entity_username": null},
      "namespace_template_vars": {},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "user_source_analysis": {
      "docname_template": "user_source_analysis_{entity_username}",
      "namespace_template": "user_analysis",
      "docname_template_vars": {"entity_username": null},
      "namespace_template_vars": {},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "uploaded_files": {
      "docname_template": "{uploaded_file_name}",
      "namespace_template": "uploaded_files",
      "docname_template_vars": {"uploaded_file_name": null},
      "namespace_template_vars": {},
      "is_shared": false,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "core_beliefs_perspectives_doc": {
      "docname_template": "core_beliefs_perspectives_doc_{entity_username}",
      "namespace_template": "user_insights",
      "docname_template_vars": {"entity_username": null},
      "namespace_template_vars": {},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "content_pillars_doc": {
      "docname_template": "content_pillars_doc_{entity_username}",
      "namespace_template": "user_insights",
      "docname_template_vars": {"entity_username": null},
      "namespace_template_vars": {},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "user_preferences_doc": {
      "docname_template": "user_preferences_doc_{entity_username}",
      "namespace_template": "user_insights",
      "docname_template_vars": {"entity_username": null},
      "namespace_template_vars": {},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "content_analysis_doc": {
      "docname_template": "content_analysis_doc_{entity_username}",
      "namespace_template": "user_analysis",
      "docname_template_vars": {"entity_username": null},
      "namespace_template_vars": {},
      "is_shared": false,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "linkedin_scraped_profile_doc": {
      "docname_template": "linkedin_scraped_profile_doc_{entity_username}",
      "namespace_template": "user_identity",
      "docname_template_vars": {"entity_username": null},
      "namespace_template_vars": {},
      "is_shared": false,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "linkedin_scraped_posts_doc": {
      "docname_template": "linkedin_scraped_posts_doc_{entity_username}",
      "namespace_template": "user_identity",
      "docname_template_vars": {"entity_username": null},
      "namespace_template_vars": {},
      "is_shared": false,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "brief": {
      "docname_template": "brief_{entity_username}_{uuid}",
      "namespace_template": "content_briefs",
      "docname_template_vars": {"entity_username": null, "uuid": null},
      "namespace_template_vars": {},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "concept": {
      "docname_template": "concept_{entity_username}_{uuid}",
      "namespace_template": "content_concepts",
      "docname_template_vars": {"entity_username": null, "uuid": null},
      "namespace_template_vars": {},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "draft": {
      "docname_template": "draft_{entity_username}_{uuid}",
      "namespace_template": "post_drafts",
      "docname_template_vars": {"entity_username": null, "uuid": null},
      "namespace_template_vars": {},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "methodology_implementation_ai_copilot": {
      "docname_template": "methodology_implementation_ai_copilot",
      "namespace_template": "system_strategy_docs_namespace",
      "docname_template_vars": {},
      "namespace_template_vars": {},
      "is_shared": true,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": true
    },
    "building_blocks_content_methodology": {
      "docname_template": "building_blocks_content_methodology",
      "namespace_template": "system_strategy_docs_namespace",
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
      "namespace_template": "system_strategy_docs_namespace",
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
      "namespace_template": "system_strategy_docs_namespace",
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
      "namespace_template": "system_strategy_docs_namespace",
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

ALL_WORKFLOWS_CONFIG_JSON_STR = """
{
  "all_workflows": {
    "linkedin_scraping": {
      "name": "linkedin_scraping_workflow",
      "version": null,
      "inputs": {
        "entity_username": null
      },
      "user_documents_config_variables": {
        "entity_username": null
      },
      "template_specific": false
    },
    "linkedin_content_analysis": {
      "name": "linkedin_content_analysis_workflow",
      "version": null,
      "inputs": {
        "scraped_posts_doc": {
          "filename_config": {
            "static_namespace": "user_identity",
            "input_docname_field": "entity_username",
            "input_docname_field_pattern": "linkedin_scraped_posts_doc_{item}"
          },
          "output_field_name": "scraped_posts",
          "is_shared": "$filename:linkedin_scraped_posts_doc.is_shared",
          "is_system_entity": "$filename:linkedin_scraped_posts_doc.is_system_entity"
        }
      },
      "user_documents_config_variables": {
        "entity_username": null
      },
      "template_specific": false
    },
    "sources_extraction": {
      "name": "sources_extraction_workflow",
      "version": null,
      "inputs": {
        "source_docs": {
          "load_configs_input_path": "uploaded_files_configs"
        }
      },
      "user_documents_config_variables": {
        "entity_username": null
      },
      "template_specific": false
    },
    "content_strategy": {
      "name": "content_strategy_workflow",
      "version": null,
      "inputs": {
        "customer_context_doc_configs": [
          {
            "namespace": "$filename:content_analysis_doc.namespace.built",
            "docname": "$filename:content_analysis_doc.docname.built"
          },
          {
            "namespace": "$filename:user_preferences_doc.namespace.built",
            "docname": "$filename:user_preferences_doc.docname.built"
          },
          {
            "namespace": "$filename:content_pillars_doc.namespace.built",
            "docname": "$filename:content_pillars_doc.docname.built"
          },
          {
            "namespace": "$filename:core_beliefs_perspectives_doc.namespace.built",
            "docname": "$filename:core_beliefs_perspectives_doc.docname.built"
          },
          {
            "namespace": "$filename:user_source_analysis.namespace.built",
            "docname": "$filename:user_source_analysis.docname.built"
          }
        ],
        "entity_username": null
      },
      "user_documents_config_variables": {
        "entity_username": null
      },
      "template_specific": false
    },
    "user_dna": {
      "name": "user_dna_workflow",
      "version": null,
      "inputs": {
        "analysis_doc": {
          "filename_config": {
            "static_namespace": "user_analysis",
            "input_docname_field": "entity_username",
            "input_docname_field_pattern": "content_analysis_doc_{item}"
          },
          "output_field_name": "analysis_results",
          "is_shared": "$filename:content_analysis_doc.is_shared",
          "is_system_entity": "$filename:content_analysis_doc.is_system_entity"
        },
        "preferences_doc": {
          "filename_config": {
            "static_namespace": "user_insights",
            "input_docname_field": "entity_username",
            "input_docname_field_pattern": "user_preferences_doc_{item}"
          },
          "output_field_name": "user_preferences",
          "is_shared": "$filename:user_preferences_doc.is_shared",
          "is_system_entity": "$filename:user_preferences_doc.is_system_entity"
        },
        "pillars_doc": {
          "filename_config": {
            "static_namespace": "user_insights",
            "input_docname_field": "entity_username",
            "input_docname_field_pattern": "content_pillars_doc_{item}"
          },
          "output_field_name": "content_pillars",
          "is_shared": "$filename:content_pillars_doc.is_shared",
          "is_system_entity": "$filename:content_pillars_doc.is_system_entity"
        },
        "beliefs_doc": {
          "filename_config": {
            "static_namespace": "user_insights",
            "input_docname_field": "entity_username",
            "input_docname_field_pattern": "core_beliefs_perspectives_doc_{item}"
          },
          "output_field_name": "core_beliefs",
          "is_shared": "$filename:core_beliefs_perspectives_doc.is_shared",
          "is_system_entity": "$filename:core_beliefs_perspectives_doc.is_system_entity"
        },
        "source_analysis_doc": {
          "filename_config": {
            "static_namespace": "user_analysis",
            "input_docname_field": "entity_username",
            "input_docname_field_pattern": "user_source_analysis_{item}"
          },
          "output_field_name": "source_analysis",
          "is_shared": "$filename:user_source_analysis.is_shared",
          "is_system_entity": "$filename:user_source_analysis.is_system_entity"
        },
        "profile_doc": {
          "filename_config": {
            "static_namespace": "user_identity",
            "input_docname_field": "entity_username",
            "input_docname_field_pattern": "linkedin_scraped_profile_doc_{item}"
          },
          "output_field_name": "linkedin_profile",
          "is_shared": "$filename:linkedin_scraped_profile_doc.is_shared",
          "is_system_entity": "$filename:linkedin_scraped_profile_doc.is_system_entity"
        }
      },
      "user_documents_config_variables": {
        "entity_username": null
      },
      "template_specific": false
    },
    "content_calendar": {
      "name": "content_calendar_entry_workflow",
      "version": null,
      "inputs": {
        "user_dna_doc": {
          "filename_config": {
            "static_namespace": "user_strategy",
            "input_docname_field": "entity_username",
            "input_docname_field_pattern": "user_dna_doc_{item}"
          },
          "output_field_name": "user_dna",
          "is_shared": "$filename:user_dna_doc.is_shared",
          "is_system_entity": "$filename:user_dna_doc.is_system_entity"
        },
        "content_strategy_doc": {
          "filename_config": {
            "static_namespace": "user_strategy",
            "input_docname_field": "entity_username",
            "input_docname_field_pattern": "content_strategy_doc_{item}"
          },
          "output_field_name": "content_strategy",
          "is_shared": "$filename:content_strategy_doc.is_shared",
          "is_system_entity": "$filename:content_strategy_doc.is_system_entity"
        },
        "scraped_posts_doc": {
          "filename_config": {
            "static_namespace": "user_identity",
            "input_docname_field": "entity_username",
            "input_docname_field_pattern": "linkedin_scraped_posts_doc_{item}"
          },
          "output_field_name": "scraped_posts",
          "is_shared": "$filename:linkedin_scraped_posts_doc.is_shared",
          "is_system_entity": "$filename:linkedin_scraped_posts_doc.is_system_entity"
        },
        "draft_doc": {
          "filename_config": {
            "static_namespace": "$filename:draft.namespace.built",
            "input_docname_field": "uuid",
            "input_docname_field_pattern": "$filename:draft.docname.partial"
          },
          "output_field_name": "draft_post",
          "is_shared": "$filename:draft.is_shared",
          "is_system_entity": "$filename:draft.is_system_entity"
        }
      },
      "user_documents_config_variables": {
        "entity_username": null,
        "uuid": null
      },
      "template_specific": false
    },
    "content_creation": {
      "name": "content_creation_workflow",
      "version": null,
      "inputs": {
        "brief_doc": {
          "filename_config": {
            "static_namespace": "content_briefs",
            "input_docname_field": "uuid",
            "input_docname_field_pattern": "$filename:brief.docname.partial"
          },
          "output_field_name": "brief",
          "is_shared": "$filename:brief.is_shared",
          "is_system_entity": "$filename:brief.is_system_entity"
        },
        "user_dna_doc": {
          "filename_config": {
            "static_namespace": "user_strategy",
            "input_docname_field": "entity_username",
            "input_docname_field_pattern": "user_dna_doc_{item}"
          },
          "output_field_name": "user_dna",
          "is_shared": "$filename:user_dna_doc.is_shared",
          "is_system_entity": "$filename:user_dna_doc.is_system_entity"
        }
      },
      "user_documents_config_variables": {
        "entity_username": null,
        "uuid": null
      },
      "template_specific": false
    },
    "brief_to_concepts": {
      "name": "initial_brief_to_concepts_workflow",
      "version": null,
      "inputs": {
        "user_dna_doc": {
          "filename_config": {
            "static_namespace": "user_strategy",
            "input_docname_field": "entity_username",
            "input_docname_field_pattern": "user_dna_doc_{item}"
          },
          "output_field_name": "user_dna",
          "is_shared": "$filename:user_dna_doc.is_shared",
          "is_system_entity": "$filename:user_dna_doc.is_system_entity"
        },
        "scraped_posts_doc": {
          "filename_config": {
            "static_namespace": "user_identity",
            "input_docname_field": "entity_username",
            "input_docname_field_pattern": "linkedin_scraped_posts_doc_{item}"
          },
          "output_field_name": "scraped_posts",
          "is_shared": "$filename:linkedin_scraped_posts_doc.is_shared",
          "is_system_entity": "$filename:linkedin_scraped_posts_doc.is_system_entity"
        },
        "draft_doc": {
          "filename_config": {
            "static_namespace": "$filename:draft.namespace.built",
            "input_docname_field": "uuid",
            "input_docname_field_pattern": "$filename:draft.docname.partial"
          },
          "output_field_name": "draft_post",
          "is_shared": "$filename:draft.is_shared",
          "is_system_entity": "$filename:draft.is_system_entity"
        }
      },
      "user_documents_config_variables": {
        "entity_username": null,
        "uuid": null
      },
      "template_specific": false
    }
  }
}
"""

# Load the JSON data
USER_DOC_CONFIG_DATA = json.loads(USER_DOCUMENTS_CONFIG_JSON_STR)
ALL_WORKFLOWS_DATA = json.loads(ALL_WORKFLOWS_CONFIG_JSON_STR)


class TestPartialFormatter(unittest.TestCase):
    def setUp(self):
        self.formatter = PartialFormatter()

    def test_missing_keys(self):
        self.assertEqual(self.formatter.format("Hello {name}, age {age}", name="World"), "Hello World, age {age}")

    def test_all_keys_present(self):
        self.assertEqual(self.formatter.format("Hello {name}, age {age}", name="World", age=30), "Hello World, age 30")

    def test_no_placeholders(self):
        self.assertEqual(self.formatter.format("Hello World"), "Hello World")

    def test_empty_string(self):
        self.assertEqual(self.formatter.format(""), "")
        
    def test_mixed_present_and_missing(self):
        self.assertEqual(self.formatter.format("{greeting} {name}, you are {status}", greeting="Hi", status="welcome"), "Hi {name}, you are welcome")

    def test_with_format_spec_on_unresolved(self):
        # The current PartialFormatter does not apply format_spec to unresolved placeholders
        self.assertEqual(self.formatter.format("Value: {val:03d}", other="test"), "Value: {val:03d}")
    
    def test_with_format_spec_on_resolved(self):
        self.assertEqual(self.formatter.format("Value: {val:03d}", val=5), "Value: 005")


class TestUserDocumentConfig(unittest.TestCase):
    def test_initialization_minimal(self):
        config = UserDocumentConfig(docname_template="doc_{id}", namespace_template="ns_{id}")
        self.assertEqual(config.docname_template, "doc_{id}")
        self.assertEqual(config.namespace_template, "ns_{id}")
        self.assertEqual(config.docname_template_vars, {})
        self.assertEqual(config.namespace_template_vars, {})
        self.assertFalse(config.is_shared)
        self.assertTrue(config.is_versioned) # Default is True

    def test_initialization_full(self):
        config = UserDocumentConfig(
            docname_template="doc_{id}",
            namespace_template="ns_{id}",
            docname_template_vars={"id": "default_id"},
            namespace_template_vars={"id": "ns_default"},
            is_shared=True,
            is_versioned=False,
            initial_version="1.0",
            schema_template_name="my_schema",
            schema_template_version="v1",
            is_system_entity=True,
            description="Test Description"
        )
        self.assertEqual(config.docname_template_vars, {"id": "default_id"})
        self.assertTrue(config.is_shared)
        self.assertFalse(config.is_versioned)
        self.assertEqual(config.description, "Test Description")

    def test_get_template_placeholders(self):
        config = UserDocumentConfig(docname_template="doc_{id}_{name}", namespace_template="ns_{id}_{loc}")
        self.assertEqual(config._get_template_placeholders("doc_{id}_{name}"), {"id", "name"})
        self.assertEqual(config._get_template_placeholders("ns_{id}_{id}"), {"id"}) # Duplicate removed by set
        self.assertEqual(config._get_template_placeholders("no_placeholders"), set())
        self.assertEqual(config._get_template_placeholders("doc_{id}_{name}_{id}"), {"id", "name"})

    def test_build_template_full_build_success(self):
        config = UserDocumentConfig(docname_template="doc_{id}_{name}", namespace_template="ns", 
                                    docname_template_vars={"name": "default_name"})
        # All from input
        self.assertEqual(config._build_template("doc_{id}_{name}", {}, {"id": "1", "name": "test"}, False), "doc_1_test")
        # Some from input, some from default
        self.assertEqual(config._build_template(config.docname_template, config.docname_template_vars, {"id": "1"}, False), "doc_1_default_name")
        # Extra vars ignored
        self.assertEqual(config._build_template(config.docname_template, config.docname_template_vars, {"id": "1", "extra": "ignored"}, False), "doc_1_default_name")
        # No placeholders in template
        config_no_place = UserDocumentConfig(docname_template="fixed_doc", namespace_template="fixed_ns")
        self.assertEqual(config_no_place._build_template("fixed_doc", {}, {}, False), "fixed_doc")

    def test_build_template_full_build_missing_var_error(self):
        config = UserDocumentConfig(docname_template="doc_{id}_{name}", namespace_template="ns",
                                    docname_template_vars={"name": "default_name"})
        with self.assertRaisesRegex(ValueError, "Missing required variables for template 'doc_{id}_{name}': id"):
            config._build_template(config.docname_template, config.docname_template_vars, {}, False) # Missing id
        
        config_no_defaults = UserDocumentConfig(docname_template="doc_{id}", namespace_template="ns")
        with self.assertRaisesRegex(ValueError, "Missing required variables for template 'doc_{id}': id"):
            config_no_defaults._build_template(config_no_defaults.docname_template, {}, {}, False)

    def test_build_template_full_build_var_is_none_error(self):
        config = UserDocumentConfig(docname_template="doc_{id}", namespace_template="ns",
                                    docname_template_vars={"id": None}) # Default is None, so it's required
        with self.assertRaisesRegex(ValueError, "Missing required variables for template 'doc_{id}': id"):
            config._build_template(config.docname_template, config.docname_template_vars, {}, False)
        with self.assertRaisesRegex(ValueError, "Missing required variables for template 'doc_{id}': id"):
            config._build_template(config.docname_template, {}, {"id": None}, False)


    def test_build_template_partial_build(self):
        config = UserDocumentConfig(docname_template="doc_{id}_{name}", namespace_template="ns",
                                    docname_template_vars={"name": "default_name"})
        self.assertEqual(config._build_template(config.docname_template, config.docname_template_vars, {"id": "1"}, True), "doc_1_default_name")
        self.assertEqual(config._build_template(config.docname_template, config.docname_template_vars, {}, True), "doc_{id}_default_name")
        self.assertEqual(config._build_template("doc_{uid}_{status}", {}, {"uid":"user1"}, True), "doc_user1_{status}")
        # Var provided as None in partial build becomes placeholder
        self.assertEqual(config._build_template("doc_{id}", {}, {"id": None}, True), "doc_{id}")
        # No placeholders in template, partial or full build makes no difference
        config_no_place = UserDocumentConfig(docname_template="fixed_doc", namespace_template="fixed_ns")
        self.assertEqual(config_no_place._build_template("fixed_doc", {}, {}, True), "fixed_doc")

    def test_build_document_templates_full_build_success(self):
        config = UserDocumentConfig(
            docname_template="user_file_{user_id}",
            namespace_template="project_{project_name}",
            docname_template_vars={"user_id": None}, # Required
            namespace_template_vars={"project_name": "default_project"},
            is_shared=True
        )
        variables = {"user_id": "user123"}
        built = config.build_document_templates(variables, partial=False)
        self.assertEqual(built["docname"], "user_file_user123")
        self.assertEqual(built["namespace"], "project_default_project")
        self.assertTrue(built["is_shared"])
        self.assertTrue(built["is_versioned"]) # Default
        self.assertIn("_source_doc_config", built)

    def test_build_document_templates_full_build_error(self):
        config = UserDocumentConfig(docname_template="file_{req_var}", namespace_template="ns")
        with self.assertRaises(ValueError):
            config.build_document_templates({}, partial=False)

    def test_build_document_templates_partial_build_success(self):
        config = UserDocumentConfig(
            docname_template="user_file_{user_id}_{role}",
            namespace_template="project_{project_name}",
            docname_template_vars={"role": "guest"},
            namespace_template_vars={}
        )
        variables = {"user_id": "user456"} # project_name missing
        built = config.build_document_templates(variables, partial=True)
        self.assertEqual(built["docname"], "user_file_user456_guest")
        self.assertEqual(built["namespace"], "project_{project_name}")

    def test_get_template_info(self):
        config = UserDocumentConfig(
            docname_template="doc_{id}_{name}",
            namespace_template="ns_{id}_{loc}",
            docname_template_vars={"name": "default_name", "id": None}, # id is required
            namespace_template_vars={"loc": "default_loc", "extra_ns_var": "val"}
        )
        info = config.get_template_info()
        self.assertEqual(info["docname_template"], "doc_{id}_{name}")
        self.assertCountEqual(info["docname_placeholders"], ["id", "name"])
        self.assertEqual(info["docname_defaults"], {"name": "default_name", "id": None})
        
        self.assertEqual(info["namespace_template"], "ns_{id}_{loc}")
        self.assertCountEqual(info["namespace_placeholders"], ["id", "loc"])
        self.assertEqual(info["namespace_defaults"], {"loc": "default_loc", "extra_ns_var": "val"})
        
        self.assertCountEqual(info["all_placeholders"], ["id", "name", "loc"])
        # 'id' is required because its default is None in docname_template_vars, and it's a placeholder in namespace too without a non-None default
        self.assertCountEqual(info["required_variables_without_defaults"], ["id"]) 
        self.assertFalse(info["static_config"]["is_shared"])

    def test_get_template_info_no_placeholders(self):
        config = UserDocumentConfig(docname_template="fixed_doc", namespace_template="fixed_ns")
        info = config.get_template_info()
        self.assertEqual(info["docname_placeholders"], [])
        self.assertEqual(info["namespace_placeholders"], [])
        self.assertEqual(info["all_placeholders"], [])
        self.assertEqual(info["required_variables_without_defaults"], [])


class TestUserDocumentsConfig(unittest.TestCase):
    def setUp(self):
        self.complex_docs_config = UserDocumentsConfig.model_validate(USER_DOC_CONFIG_DATA)
        self.simple_doc_config_data = {
            "documents": {
                "test_doc": {
                    "docname_template": "test_{var}", 
                    "namespace_template": "common",
                    "docname_template_vars": {"var": None} # Required
                }
            }
        }
        self.simple_docs_config = UserDocumentsConfig.model_validate(self.simple_doc_config_data)

    def test_initialization(self):
        self.assertIn("user_dna_doc", self.complex_docs_config.documents)
        self.assertEqual(len(self.complex_docs_config.documents), 18) # Count from JSON
        empty_conf = UserDocumentsConfig(documents={})
        self.assertEqual(empty_conf.documents, {})

    def test_get_document_config(self):
        self.assertIsNotNone(self.complex_docs_config.get_document_config("user_dna_doc"))
        self.assertIsNone(self.complex_docs_config.get_document_config("non_existent_key"))

    def test_get_built_document_config_success(self):
        built = self.simple_docs_config.get_built_document_config("test_doc", {"var": "value1"}, partial=False)
        self.assertEqual(built["docname"], "test_value1")
        self.assertEqual(built["namespace"], "common")

        built_partial = self.simple_docs_config.get_built_document_config("test_doc", {}, partial=True)
        self.assertEqual(built_partial["docname"], "test_{var}")

    def test_get_built_document_config_error_and_none(self):
        with self.assertRaises(ValueError): # Missing var for full build
            self.simple_docs_config.get_built_document_config("test_doc", {}, partial=False)
        self.assertIsNone(self.simple_docs_config.get_built_document_config("non_existent", {"var": "val"}))

    def test_get_built_document_configs(self):
        variables_map = {
            "user_dna_doc": {"entity_username": "test_user"},
            "brief": {"entity_username": "test_user", "uuid": "brief_uuid_123"}
        }
        built_configs = self.complex_docs_config.get_built_document_configs(
            variables_map=variables_map,
            doc_keys_to_build=["user_dna_doc", "brief"]
        )
        self.assertEqual(len(built_configs), 2)
        self.assertEqual(built_configs["user_dna_doc"]["docname"], "user_dna_doc_test_user")
        self.assertEqual(built_configs["brief"]["docname"], "brief_test_user_brief_uuid_123")

    def test_get_built_document_configs_all_keys(self):
         # Test building all, some will fail if they have required vars not in map
         # This requires careful setup of variables_map if used this way in production
        variables_map = {
            "methodology_implementation_ai_copilot": {} # No vars needed
        }
        built_configs = self.complex_docs_config.get_built_document_configs(
            variables_map=variables_map,
            doc_keys_to_build=["methodology_implementation_ai_copilot"] # Limit for test
        )
        self.assertIn("methodology_implementation_ai_copilot", built_configs)
        self.assertEqual(built_configs["methodology_implementation_ai_copilot"]["docname"], "methodology_implementation_ai_copilot")

    def test_get_built_document_configs_partial(self):
        variables_map = {
            "brief": {"entity_username": "test_user"} # uuid missing
        }
        built_configs = self.complex_docs_config.get_built_document_configs(
            variables_map=variables_map,
            doc_keys_to_build=["brief"],
            partial_build=True
        )
        self.assertEqual(built_configs["brief"]["docname"], "brief_test_user_{uuid}")

    def test_get_built_document_configs_errors(self):
        with self.assertRaisesRegex(ValueError, "Document configuration key 'non_existent' not found."):
            self.complex_docs_config.get_built_document_configs({}, doc_keys_to_build=["non_existent"])
        
        # Missing var for a key in full build
        with self.assertRaisesRegex(ValueError, "Missing required variables for template 'brief_{entity_username}_{uuid}': uuid"):
            self.complex_docs_config.get_built_document_configs(
                variables_map={"brief": {"entity_username": "user1"}}, # uuid missing
                doc_keys_to_build=["brief"],
                partial_build=False
            )
    
    def test_get_documents_info(self):
        info = self.complex_docs_config.get_documents_info(doc_keys_to_inspect=["user_dna_doc", "non_existent_key"])
        self.assertIn("user_dna_doc", info)
        self.assertEqual(info["user_dna_doc"]["docname_template"], "user_dna_doc_{entity_username}")
        self.assertIn("non_existent_key", info)
        self.assertIn("error", info["non_existent_key"])

        all_info = self.complex_docs_config.get_documents_info() # All keys
        self.assertEqual(len(all_info), len(self.complex_docs_config.documents))

    def test_get_built_document_configs_mixed_needs(self):
        # "brief" needs entity_username and uuid
        # "methodology_implementation_ai_copilot" needs nothing
        variables_map = {
            "brief": {"entity_username": "test_user", "uuid": "brief_123"},
            "methodology_implementation_ai_copilot": {}
        }
        keys_to_build = ["brief", "methodology_implementation_ai_copilot"]
        built_configs = self.complex_docs_config.get_built_document_configs(
            variables_map=variables_map,
            doc_keys_to_build=keys_to_build,
            partial_build=False
        )
        self.assertEqual(len(built_configs), 2)
        self.assertEqual(built_configs["brief"]["docname"], "brief_test_user_brief_123")
        self.assertEqual(built_configs["methodology_implementation_ai_copilot"]["docname"], "methodology_implementation_ai_copilot")

    def test_get_built_document_configs_partial_varying_missing(self):
        variables_map = {
            "brief": {"entity_username": "user_brief"}, # uuid missing
            "concept": {"uuid": "concept_uuid"},        # entity_username missing
            "draft": {}                                # both missing
        }
        keys_to_build = ["brief", "concept", "draft"]
        built_configs = self.complex_docs_config.get_built_document_configs(
            variables_map=variables_map,
            doc_keys_to_build=keys_to_build,
            partial_build=True
        )
        self.assertEqual(built_configs["brief"]["docname"], "brief_user_brief_{uuid}")
        self.assertEqual(built_configs["concept"]["docname"], "concept_{entity_username}_concept_uuid")
        self.assertEqual(built_configs["draft"]["docname"], "draft_{entity_username}_{uuid}")

    def test_get_documents_info_larger_subset(self):
        keys = ["user_dna_doc", "brief", "methodology_implementation_ai_copilot", "non_existent"]
        info = self.complex_docs_config.get_documents_info(doc_keys_to_inspect=keys)
        self.assertEqual(len(info), len(keys))
        self.assertIn("user_dna_doc", info)
        self.assertNotIn("error", info["user_dna_doc"])
        self.assertIn("methodology_implementation_ai_copilot", info)
        self.assertNotIn("error", info["methodology_implementation_ai_copilot"])
        self.assertIn("non_existent", info)
        self.assertIn("error", info["non_existent"])


class TestAppWorkflow(unittest.TestCase):
    def setUp(self):
        self.docs_config = UserDocumentsConfig.model_validate(USER_DOC_CONFIG_DATA)
        self.content_strategy_workflow_data = ALL_WORKFLOWS_DATA["all_workflows"]["content_strategy"]
        self.content_calendar_workflow_data = ALL_WORKFLOWS_DATA["all_workflows"]["content_calendar"]

    def test_initialization(self):
        workflow = AppWorkflow(**self.content_strategy_workflow_data)
        self.assertEqual(workflow.name, "content_strategy_workflow")
        self.assertEqual(workflow.user_documents_config_variables, {"entity_username": None})
        self.assertFalse(workflow.template_specific)

    def test_get_vars_for_doc_key(self):
        # template_specific = False
        workflow_global_vars = AppWorkflow(
            name="wf1", version="1", inputs={},
            user_documents_config_variables={"entity_username": "global_user", "project": "projA"},
            template_specific=False
        )
        self.assertEqual(workflow_global_vars._get_vars_for_doc_key("any_doc_key"), 
                         {"entity_username": "global_user", "project": "projA"})

        # template_specific = True
        workflow_specific_vars_data = {
            "name": "wf2", "version": "1", "inputs": {},
            "user_documents_config_variables": {
                "doc1": {"entity_username": "user_doc1"},
                "doc2": {"entity_username": "user_doc2", "uuid": "id_doc2"}
            },
            "template_specific": True
        }
        workflow_specific_vars = AppWorkflow(**workflow_specific_vars_data)
        self.assertEqual(workflow_specific_vars._get_vars_for_doc_key("doc1"), {"entity_username": "user_doc1"})
        self.assertEqual(workflow_specific_vars._get_vars_for_doc_key("doc2"), {"entity_username": "user_doc2", "uuid": "id_doc2"})
        self.assertEqual(workflow_specific_vars._get_vars_for_doc_key("doc3_not_present"), {}) # Key not present

    def test_resolve_filename_reference_docname_namespace(self):
        workflow = AppWorkflow(**self.content_strategy_workflow_data) 
        workflow.user_documents_config_variables = {"entity_username": "strat_user_99"}
        
        # .built (default)
        resolved_ns = workflow._resolve_filename_reference("$filename:content_analysis_doc.namespace.built", self.docs_config)
        self.assertEqual(resolved_ns, "user_analysis") # namespace_template is static
        resolved_dn = workflow._resolve_filename_reference("$filename:content_analysis_doc.docname", self.docs_config) # .built is default
        self.assertEqual(resolved_dn, "content_analysis_doc_strat_user_99")

        # .partial
        workflow_cal = AppWorkflow(**self.content_calendar_workflow_data) 
        workflow_cal.user_documents_config_variables = {"entity_username": "strat_user_99"}
        resolved_partial_dn = workflow_cal._resolve_filename_reference("$filename:draft.docname.partial", self.docs_config)
        self.assertEqual(resolved_partial_dn, "draft_strat_user_99_{uuid}")

        # .template
        resolved_template = workflow_cal._resolve_filename_reference("$filename:brief.namespace_template", self.docs_config)
        self.assertEqual(resolved_template, "content_briefs")
        resolved_dn_template = workflow_cal._resolve_filename_reference("$filename:brief.docname.template", self.docs_config)
        self.assertEqual(resolved_dn_template, "brief_{entity_username}_{uuid}")

    def test_resolve_filename_reference_direct_attribute(self):
        workflow = AppWorkflow(**self.content_calendar_workflow_data)
        is_shared_val = workflow._resolve_filename_reference("$filename:draft.is_shared", self.docs_config)
        self.assertFalse(is_shared_val) 
        
        is_sys_entity = workflow._resolve_filename_reference("$filename:methodology_implementation_ai_copilot.is_system_entity", self.docs_config)
        self.assertTrue(is_sys_entity)

    def test_resolve_filename_reference_config_modifier(self):
        workflow_cal = AppWorkflow(**self.content_calendar_workflow_data)
        workflow_cal.user_documents_config_variables = {"entity_username": "dna_cal_user"}
        
        built_config = workflow_cal._resolve_filename_reference("$filename:user_dna_doc.config.built", self.docs_config)
        self.assertIsInstance(built_config, dict)
        self.assertEqual(built_config["docname"], "user_dna_doc_dna_cal_user")
        self.assertEqual(built_config["namespace"], "user_strategy")
        self.assertFalse(built_config["is_shared"])

        # Partial build of config
        workflow_cal_for_partial = AppWorkflow(**self.content_calendar_workflow_data)
        workflow_cal_for_partial.user_documents_config_variables = {"entity_username": "cal_user_draft"}
        
        partial_config = workflow_cal_for_partial._resolve_filename_reference("$filename:draft.config.partial", self.docs_config)
        self.assertEqual(partial_config["docname"], "draft_cal_user_draft_{uuid}")
        self.assertEqual(partial_config["namespace"], "post_drafts")
    
    def test_resolve_filename_reference_doc_template_vars_attribute(self):
        workflow = AppWorkflow(**self.content_strategy_workflow_data)
        vars_dict = workflow._resolve_filename_reference("$filename:content_analysis_doc.docname_template_vars", self.docs_config)
        self.assertEqual(vars_dict, {"entity_username": None})


    def test_resolve_filename_reference_errors(self):
        workflow = AppWorkflow(**self.content_calendar_workflow_data)
        
        # Not a filename reference
        self.assertEqual(workflow._resolve_filename_reference("not_a_ref", self.docs_config), "not_a_ref")

        # Non-existent doc_key
        with self.assertRaisesRegex(ValueError, "Referenced document key 'no_such_doc' not found"):
            workflow._resolve_filename_reference("$filename:no_such_doc.name.built", self.docs_config)

        # Invalid attribute
        with self.assertRaisesRegex(ValueError, "Invalid attribute 'non_existent_attr' or modifier 'None'"):
            workflow._resolve_filename_reference("$filename:draft.non_existent_attr", self.docs_config)

        # Invalid modifier for attribute
        with self.assertRaisesRegex(ValueError, "Modifier '.built' is not applicable to attribute 'is_shared'"):
            workflow._resolve_filename_reference("$filename:draft.is_shared.built", self.docs_config)
        
        # Missing var for .built on docname/namespace (via config)
        workflow_missing_var_for_built = AppWorkflow(
            name="wf_err", version="1", inputs={},
            user_documents_config_variables={"brief":{}}, # No uuid, no entity_username for brief
            template_specific=True
        )
        # The error message will have sorted missing variables: entity_username, uuid
        # And also the "Provided: ... Defaults: ..." part.
        # Corrected regex to account for space after `uuid.`
        # Using re.escape for literal parts and a robust pattern for lists.
        "Missing required variables for template 'brief_{entity_username}_{uuid}': entity_username, uuid. Provided: [], Defaults: ['entity_username', 'uuid']"
        msg_part1 = "Missing required variables for template 'brief_{entity_username}_{uuid}': entity_username, uuid. "
        msg_part2_provided = "Provided: "
        msg_part3_list_content = r"\[[^]]*\]" # Matches list like [] or ['item1', 'item2']
        msg_part4_comma_defaults = ", Defaults: "
        
        expected_regex = (
            re.escape(msg_part1) + 
            re.escape(msg_part2_provided) + 
            
            msg_part3_list_content + 
            re.escape(msg_part4_comma_defaults) + 
            msg_part3_list_content
        )
        
        with self.assertRaisesRegex(ValueError, expected_regex):
            workflow_missing_var_for_built._resolve_filename_reference("$filename:brief.docname.built", self.docs_config)


    def test_get_processed_inputs_content_strategy(self):
        workflow = AppWorkflow(**self.content_strategy_workflow_data)
        workflow.user_documents_config_variables = {"entity_username": "strat_user_99"}
        processed = workflow.get_processed_inputs(self.docs_config)

        context_configs = processed["customer_context_doc_configs"]
        self.assertEqual(len(context_configs), 5)
        self.assertEqual(context_configs[0]["namespace"], "user_analysis") 
        self.assertEqual(context_configs[0]["docname"], "content_analysis_doc_strat_user_99")
        self.assertEqual(context_configs[1]["namespace"], "user_insights") 
        self.assertEqual(context_configs[1]["docname"], "user_preferences_doc_strat_user_99")
        self.assertEqual(context_configs[2]["docname"], "content_pillars_doc_strat_user_99")
        self.assertEqual(context_configs[3]["docname"], "core_beliefs_perspectives_doc_strat_user_99")
        self.assertEqual(context_configs[4]["docname"], "user_source_analysis_strat_user_99")
        
        self.assertIsNone(processed["entity_username"])


    def test_get_processed_inputs_content_calendar_mixed_results(self):
        workflow = AppWorkflow(**self.content_calendar_workflow_data)
        with self.assertRaisesRegex(ValueError, r"Missing required variables for template 'draft_\{entity_username\}_\{uuid\}': entity_username, uuid"):
            workflow.get_processed_inputs(self.docs_config)

        valid_calendar_inputs = {
            "user_dna_doc_config_built": "$filename:user_dna_doc.config.built",
            "brief_doc_namespace_template": "$filename:brief.namespace_template",
            "draft_doc_partial_name": "$filename:draft.docname.partial",
            "is_draft_shared": "$filename:draft.is_shared",
        }
        workflow_valid_cal = AppWorkflow(
            name=self.content_calendar_workflow_data["name"],
            version=self.content_calendar_workflow_data["version"],
            inputs=valid_calendar_inputs,
            user_documents_config_variables={
                "user_dna_doc": {"entity_username": "dna_cal_user"},
                "brief": {"entity_username": "cal_user", "uuid": "cal_uuid"},
                "draft": {"entity_username": "cal_user_draft"}
            },
            template_specific=True
        )
        processed = workflow_valid_cal.get_processed_inputs(self.docs_config)
        
        self.assertEqual(processed["user_dna_doc_config_built"]["docname"], "user_dna_doc_dna_cal_user")
        self.assertEqual(processed["brief_doc_namespace_template"], "content_briefs")
        self.assertEqual(processed["draft_doc_partial_name"], "draft_cal_user_draft_{uuid}")
        self.assertFalse(processed["is_draft_shared"])


    def test_get_unresolved_inputs_info(self):
        workflow = AppWorkflow(**self.content_calendar_workflow_data)
        analysis = workflow.get_unresolved_inputs_info(self.docs_config)

        self.assertEqual(analysis["workflow_name"], "content_calendar_entry_workflow")
        refs_found = analysis["filename_references_found"]
        self.assertEqual(len(refs_found), 10) 

        # Example: Check details for a resolvable reference like "$filename:user_dna_doc.config.built"
        # content_calendar_workflow_data has user_documents_config_variables = {"entity_username": null, "uuid": null}
        # and template_specific = False.
        dna_ref_info = next(r for r in refs_found if r["doc_key"] == "user_dna_doc" and r["path_in_inputs"] == "inputs.user_dna_doc.is_shared") 
        self.assertEqual(dna_ref_info["raw_reference"], "$filename:user_dna_doc.is_shared") 
        self.assertEqual(dna_ref_info["attribute"], "is_shared")
        self.assertIsNone(dna_ref_info["modifier"])
        self.assertTrue(dna_ref_info["doc_config_exists"])
        self.assertIn("doc_template_info", dna_ref_info)
        self.assertEqual(dna_ref_info["workflow_provided_variables_for_key"], {"entity_username": None, "uuid": None})
        self.assertEqual(dna_ref_info["still_missing_variables"], ['entity_username'])
        
        draft_ref_info = next(r for r in refs_found if r["doc_key"] == "draft" and r["attribute"] == "docname" and r["modifier"] == "partial")
        self.assertEqual(draft_ref_info["workflow_provided_variables_for_key"], {"entity_username": None, "uuid": None})
        self.assertCountEqual(draft_ref_info["still_missing_variables"], ['entity_username', 'uuid'])

    def test_get_vars_for_doc_key_empty_vars(self):
        workflow_global_empty = AppWorkflow(
            name="wf_empty_global", version="1", inputs={},
            user_documents_config_variables={}, template_specific=False
        )
        self.assertEqual(workflow_global_empty._get_vars_for_doc_key("any_key"), {})

        workflow_specific_empty = AppWorkflow(
            name="wf_empty_specific", version="1", inputs={},
            user_documents_config_variables={}, template_specific=True
        )
        self.assertEqual(workflow_specific_empty._get_vars_for_doc_key("any_key"), {})
        
        workflow_specific_key_missing = AppWorkflow(
            name="wf_key_missing", version="1", inputs={},
            user_documents_config_variables={"doc1": {"var": "val"}}, template_specific=True
        )
        self.assertEqual(workflow_specific_key_missing._get_vars_for_doc_key("doc_not_in_vars"), {})

    def test_resolve_filename_reference_attr_from_template_vars(self):
        doc_with_specific_var_default = UserDocumentConfig(
            docname_template="doc_{id}", namespace_template="ns",
            docname_template_vars={"id": "default123", "other_detail": "detail_val"}
        )
        temp_docs_config = UserDocumentsConfig(documents={
            "doc_specific": doc_with_specific_var_default
        })
        workflow = AppWorkflow(
            name="wf_test_var_access", version="1", inputs={},
            user_documents_config_variables={},
            template_specific=False
        )
        self.assertEqual(workflow._resolve_filename_reference("$filename:doc_specific.docname_template_vars", temp_docs_config),
                         {"id": "default123", "other_detail": "detail_val"})
        
        with self.assertRaisesRegex(ValueError, "Invalid attribute 'other_detail' or modifier 'None'"):
            workflow._resolve_filename_reference("$filename:doc_specific.other_detail", temp_docs_config)

    def test_get_processed_inputs_complex_structure_and_empty_vars(self):
        linkedin_scraping_workflow_data = ALL_WORKFLOWS_DATA["all_workflows"]["linkedin_scraping"]
        workflow = AppWorkflow(
            name=linkedin_scraping_workflow_data["name"],
            version=linkedin_scraping_workflow_data["version"],
            inputs={
                "level1": {
                    "target_profile_doc_name": "$filename:linkedin_scraped_profile_doc.docname.built",
                    "is_shared_status": "$filename:linkedin_scraped_profile_doc.is_shared",
                    "deep_list": [
                        {"ref": "$filename:linkedin_scraped_posts_doc.namespace.built"},
                        "static_string",
                        123
                    ]
                },
                "raw_entity_user_from_inputs": linkedin_scraping_workflow_data["inputs"]["entity_username"]
            },
            user_documents_config_variables=linkedin_scraping_workflow_data["user_documents_config_variables"], 
            template_specific=linkedin_scraping_workflow_data["template_specific"]
        )
        
        with self.assertRaisesRegex(ValueError, "Missing required variables for template 'linkedin_scraped_profile_doc_{entity_username}': entity_username"):
            workflow.get_processed_inputs(self.docs_config)

        workflow.user_documents_config_variables = {"entity_username": "valid_user"}
        processed = workflow.get_processed_inputs(self.docs_config)
        
        self.assertEqual(processed["level1"]["target_profile_doc_name"], "linkedin_scraped_profile_doc_valid_user")
        self.assertFalse(processed["level1"]["is_shared_status"])
        self.assertEqual(processed["level1"]["deep_list"][0]["ref"], "user_identity")
        self.assertEqual(processed["level1"]["deep_list"][1], "static_string")
        self.assertEqual(processed["raw_entity_user_from_inputs"], linkedin_scraping_workflow_data["inputs"]["entity_username"])

    def test_get_unresolved_inputs_info_more_workflows(self):
        workflow_data_lca = ALL_WORKFLOWS_DATA["all_workflows"]["linkedin_content_analysis"]
        workflow_lca = AppWorkflow(**workflow_data_lca)
        analysis_lca = workflow_lca.get_unresolved_inputs_info(self.docs_config)
        
        self.assertEqual(analysis_lca["workflow_name"], "linkedin_content_analysis_workflow")
        lca_refs = analysis_lca["filename_references_found"]
        self.assertEqual(len(lca_refs), 2)
        
        shared_ref = next(r for r in lca_refs if r["attribute"] == "is_shared")
        self.assertEqual(shared_ref["doc_key"], "linkedin_scraped_posts_doc")
        self.assertEqual(shared_ref["workflow_provided_variables_for_key"], {"entity_username": None})
        self.assertIn("entity_username", shared_ref["doc_template_info"]["required_variables_without_defaults"])
        self.assertEqual(shared_ref["still_missing_variables"], ["entity_username"])

        content_creation_data = deepcopy(ALL_WORKFLOWS_DATA["all_workflows"]["content_creation"])
        content_creation_data["user_documents_config_variables"] = {
            "brief": {"entity_username": "cc_user", "uuid": "cc_uuid"}
        }
        workflow_cc_data_custom = {
            "name": content_creation_data["name"],
            "version": content_creation_data["version"],
            "inputs": content_creation_data["inputs"],
            "user_documents_config_variables": {
                 "brief": {"entity_username": "cc_user", "uuid": "cc_uuid"}
            },
            "template_specific": True
        }
        workflow_cc = AppWorkflow(**workflow_cc_data_custom)
        analysis_cc = workflow_cc.get_unresolved_inputs_info(self.docs_config)
        cc_refs = analysis_cc["filename_references_found"]
        
        dna_ref_info_cc = next(r for r in cc_refs if r["doc_key"] == "user_dna_doc" and r["attribute"] == "is_shared")
        self.assertEqual(dna_ref_info_cc["workflow_provided_variables_for_key"], {})
        self.assertCountEqual(dna_ref_info_cc["still_missing_variables"], ["entity_username"])



if __name__ == "__main__":
    unittest.main()
