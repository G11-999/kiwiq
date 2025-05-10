import uuid
import re
import string
import json # Added for loading default configs
from copy import deepcopy # For deep copying inputs if not using Pydantic's model_copy
from typing import List, Dict, Any, Optional, Union, Set, cast, Type, TypeVar
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, status, Body, Query, Path
from pydantic import BaseModel, Field, model_validator, field_validator, ValidationError

# Assuming these dependencies exist based on app_state.py
from kiwi_app.auth.dependencies import get_current_active_verified_user, get_current_active_superuser # Make sure get_current_superuser exists
from kiwi_app.auth.models import User
from kiwi_app.utils import get_kiwi_logger # If a logger is needed

# logger = get_kiwi_logger(name="kiwi_app.app_artifacts")

# --- JSON String Constants (moved here before Pydantic models that might use them indirectly)
# These were previously at the top of the file, ensure they are here or loaded appropriately.
USER_DOCUMENTS_CONFIG_JSON_STR = """
{
  "documents": {
    "user_dna_doc": {
      "docname_template": "user_dna_doc",
      "namespace_template": "user_strategy_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "content_strategy_doc": {
      "docname_template": "content_strategy_doc",
      "namespace_template": "user_strategy_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "user_source_analysis": {
      "docname_template": "user_source_analysis",
      "namespace_template": "user_analysis_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "uploaded_files": {
      "docname_template": "",
      "namespace_template": "uploaded_files_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "core_beliefs_perspectives_doc": {
      "docname_template": "core_beliefs_perspectives_doc",
      "namespace_template": "user_inputs_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "content_pillars_doc": {
      "docname_template": "content_pillars_doc",
      "namespace_template": "user_inputs_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "user_preferences_doc": {
      "docname_template": "user_preferences_doc",
      "namespace_template": "user_inputs_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "content_analysis_doc": {
      "docname_template": "content_analysis_doc",
      "namespace_template": "user_analysis_{entity_username}",
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
      "namespace_template": "scraping_results_{entity_username}",
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
      "namespace_template": "scraping_results_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": false,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "brief": {
      "docname_template": "brief_{_uuid_}",
      "namespace_template": "content_briefs_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "concept": {
      "docname_template": "concept_{_uuid_}",
      "namespace_template": "content_concepts_{entity_username}",
      "docname_template_vars": {},
      "namespace_template_vars": {"entity_username": null},
      "is_shared": false,
      "is_versioned": true,
      "initial_version": null,
      "schema_template_name": null,
      "schema_template_version": null,
      "is_system_entity": false
    },
    "draft": {
      "docname_template": "draft_{post_uuid}",
      "namespace_template": "post_drafts_{entity_username}",
      "docname_template_vars": {"post_uuid": null},
      "namespace_template_vars": {"entity_username": null},
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
    "linkedin_scraping_workflow": {
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
    "linkedin_content_analysis_workflow": {
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
    "sources_extraction_workflow": {
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
    "content_strategy_workflow": {
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
    "user_dna_workflow": {
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
    "content_calendar_entry_workflow": {
      "name": "content_calendar_entry_workflow",
      "version": null,
      "inputs": {
        "entity_username": null,
        "weeks_to_generate": 1,
        "customer_context_doc_configs": [
            {
                "filename_config": {
                    "input_namespace_field_pattern": "user_strategy_{item}",
                    "input_namespace_field": "entity_username",
                    "static_docname": "user_dna_doc"
                },
                "output_field_name": "user_dna"
            },
            {
                "filename_config": {
                    "input_namespace_field_pattern": "user_inputs_{item}",
                    "input_namespace_field": "entity_username",
                    "static_docname": "user_preferences_doc"
                },
                "output_field_name": "user_preferences"
            },
            {
                "filename_config": {
                    "input_namespace_field_pattern": "user_strategy_{item}",
                    "input_namespace_field": "entity_username",
                    "static_docname": "content_strategy_doc"
                },
                "output_field_name": "strategy_doc"
            },
            {
                "filename_config": {
                    "input_namespace_field_pattern": "scraping_results_{item}",
                    "input_namespace_field": "entity_username",
                    "static_docname": "linkedin_scraped_posts_doc"
                },
                "output_field_name": "scraped_posts"
            }
        ],
        "past_context_posts_limit": 20
    },
      "user_documents_config_variables": {},
      "template_specific": false
    },
    "content_creation_workflow": {
      "name": "content_creation_workflow",
      "version": null,
      "inputs": {
            "post_uuid": "test_post_uuid",
            "brief_docname": "brief_docname",
            "customer_context_doc_configs": [
                {
                    "filename_config": {
                        "input_namespace_field_pattern": "user_strategy_{item}",
                        "input_namespace_field": "entity_username",
                        "static_docname": "user_dna_doc"
                    },
                    "output_field_name": "user_dna"
                },
                {
                    "filename_config": {
                        "input_namespace_field_pattern": "content_briefs_{item}",
                        "input_namespace_field": "entity_username",
                        "input_docname_field": "brief_docname"
                    },
                    "output_field_name": "content_brief"
                }
            ],
            "entity_username": "example-user"
        },
      "user_documents_config_variables": {},
      "template_specific": false
    },
    "initial_brief_to_concepts_workflow": {
      "name": "initial_brief_to_concepts_workflow",
      "version": null,
      "inputs": {
        "initial_brief_docname": "test_brief_1",
        "customer_context_doc_configs": [
            {
                "filename_config": {
                    "input_namespace_field_pattern": "user_strategy_{item}",
                    "input_namespace_field": "entity_username",
                    "static_docname": "user_dna_doc"
                },
                "output_field_name": "user_dna"
            },
            {
                "filename_config": {
                    "input_namespace_field_pattern": "content_briefs_{item}",
                    "input_namespace_field": "entity_username",
                    "input_docname_field": "initial_brief_docname"
                },
                "output_field_name": "initial_brief"
            },
            {
                "filename_config": {
                    "input_namespace_field_pattern": "scraping_results_{item}",
                    "input_namespace_field": "entity_username",
                    "static_docname": "linkedin_scraped_posts_doc"
                },
                "output_field_name": "scraped_posts"
            }
        ],
        "past_context_posts_limit": 20,
        "entity_username": null
      },
      "user_documents_config_variables": {},
      "template_specific": false
    }
  }
}
"""

# --- Helper Classes ---

class PartialFormatter(string.Formatter):
    """
    A custom string formatter that leaves missing keys as placeholders
    instead of raising a KeyError. Useful for partial template building.
    Example: "Hello {name}, age {age}".format_map(SafeDict(name="World"))
             -> "Hello World, age {age}"
    """
    def get_value(self, key: Union[int, str], args: List[Any], kwargs: Dict[str, Any]) -> Any:
        """
        Overrides the base method to return the key itself (as a placeholder)
        if it's not found in kwargs or if its value is None.
        """
        if isinstance(key, str) and key in kwargs:
            value = kwargs[key]
            if value is None: # MODIFIED: Treat None as a missing key for placeholder purposes
                return f"{{{key}}}"
            return value
        elif isinstance(key, int) and key < len(args): # Should not happen with named placeholders
            # Potentially treat args[key] is None similarly if this branch becomes relevant
            return args[key]
        # Return the placeholder itself if not found
        return f"{{{key}}}"

    def format_field(self, value: Any, format_spec: str) -> str:
        """
        Ensures that even if a placeholder is returned by get_value,
        it's treated as a string for further formatting (though typically not needed for simple placeholders).
        """
        if value == f"{{{self._current_key}}}": # If value is an unresolved placeholder
             return value # Return it as is
        return super().format_field(value, format_spec)

    def _vformat(self, format_string, args, kwargs, used_args, recursion_depth, auto_arg_index=0):
        # Store the current key being processed for format_field
        # This is a bit of a hack as Formatter doesn't directly expose this to format_field
        # We iterate through parse results to achieve this.
        result = []
        for literal_text, field_name, format_spec, conversion in self.parse(format_string):
            result.append(literal_text)
            if field_name is not None:
                self._current_key = field_name
                obj, arg_used = self.get_field(field_name, args, kwargs)
                
                # If obj is a placeholder (because it was missing or None), append it with its spec if any
                if obj == f"{{{field_name}}}":
                    if format_spec: # MODIFIED: Re-attach format_spec to unresolved placeholder
                        result.append(f"{{{field_name}:{format_spec}}}")
                    else:
                        result.append(obj)
                else:
                    obj = self.convert_field(obj, conversion)
                    result.append(self.format_field(obj, format_spec))
        return "".join(result), auto_arg_index


# --- Core Pydantic Models ---

class UserDocumentConfig(BaseModel):
    """
    Configuration for a user-specific document, defining how its
    docname and namespace are templated and built.
    """
    docname_template: str = Field(
        ...,
        description="Template string for the document name. E.g., 'profile_{entity_username}_{date}'.",
        examples=["user_dna_summary_{user_id}", "linkedin_posts_{profile_id}"]
    )
    namespace_template: str = Field(
        ...,
        description="Template string for the document namespace. E.g., 'user_data_{org_id}'.",
        examples=["user_documents_{org_id}", "shared_analysis_{project_id}"]
    )
    docname_template_vars: Dict[str, Optional[Any]] = Field(
        default_factory=dict,
        description="Default values for variables in docname_template. None means required from input."
    )
    namespace_template_vars: Dict[str, Optional[Any]] = Field(
        default_factory=dict,
        description="Default values for variables in namespace_template. None means required from input."
    )
    is_shared: bool = Field(False, description="Indicates if the document is shared within an organization.")
    is_versioned: bool = Field(True, description="Indicates if the document is versioned.")
    initial_version: Optional[str] = Field(None, description="Initial version for the document, if versioned.")
    schema_template_name: Optional[str] = Field(None, description="Name of the schema template for this document.")
    schema_template_version: Optional[str] = Field(None, description="Version of the schema template.")
    is_system_entity: bool = Field(False, description="Indicates if this document is a system-level entity.")

    description: Optional[str] = Field(None, description="A human-readable description of this document config.")

    def _get_template_placeholders(self, template_string: str) -> Set[str]:
        """
        Extracts unique placeholder variable names (e.g., 'entity_username')
        from a template string (e.g., "profile_{entity_username}").
        """
        return set(fname for _, fname, _, _ in string.Formatter().parse(template_string) if fname)

    def _build_template(
        self,
        template_string: str,
        default_vars: Dict[str, Optional[Any]],
        input_variables: Dict[str, Any],
        partial: bool
    ) -> str:
        """
        Builds a single template string (docname or namespace) using provided variables.

        Args:
            template_string: The template string (e.g., "profile_{user_id}").
            default_vars: Default variables for this template.
            input_variables: User-provided variables.
            partial: If True, allows partial formatting (missing keys remain as placeholders).

        Returns:
            The built string.

        Raises:
            ValueError: If not partial and a required variable is missing.
        """
        # Merge input variables with defaults, input_variables take precedence
        merged_vars = {**default_vars, **input_variables}

        # Identify all placeholders in the template
        placeholders = self._get_template_placeholders(template_string)
        
        # Check for missing required variables if not doing a partial build
        if not partial:
            missing_vars = [
                p for p in placeholders if p not in merged_vars or merged_vars[p] is None
            ]
            if missing_vars:
                missing_vars.sort() # MODIFIED: Sort for deterministic error messages
                raise ValueError(
                    f"Missing required variables for template '{template_string}': {', '.join(missing_vars)}. "
                    f"Provided: {list(input_variables.keys())}, Defaults: {list(default_vars.keys())}" # MODIFIED: Show keys as lists for clarity
                )
        
        # Filter out None values before formatting, unless it's a partial build
        # For partial build, we want to pass all merged_vars to PartialFormatter
        # For full build, if a var made it this far (not missing and not None), it should be used.
        # If a var is None and it's a full build, an error should have been raised already.
        vars_for_formatting = {k: v for k, v in merged_vars.items() if v is not None or partial}


        if partial:
            formatter = PartialFormatter()
            return formatter.format(template_string, **vars_for_formatting)
        else:
            # Ensure all needed placeholders are in vars_for_formatting for strict formatting
            # This check is mostly redundant due to the earlier missing_vars check but ensures safety
            final_vars_for_strict_format = {p: vars_for_formatting[p] for p in placeholders if p in vars_for_formatting}
            if not all(p in final_vars_for_strict_format for p in placeholders):
                 # This case should ideally be caught by `missing_vars`
                raise ValueError(f"Internal error: Not all placeholders satisfied for strict formatting of '{template_string}'")
            return template_string.format(**final_vars_for_strict_format)


    def build_document_templates(
        self,
        input_variables: Dict[str, Any],
        partial: bool = False
    ) -> Dict[str, Any]:
        """
        Builds the docname and namespace templates using provided variables.

        Args:
            input_variables: A dictionary of variables to fill in the templates.
            partial: If True, performs a partial build (missing variables remain as placeholders).
                     If False, raises ValueError if any required variable is missing.

        Returns:
            A dictionary containing the built 'docname', 'namespace', and all other
            static attributes of this config (is_shared, is_versioned, etc.).
        """
        built_docname = self._build_template(
            self.docname_template, self.docname_template_vars, input_variables, partial
        )
        built_namespace = self._build_template(
            self.namespace_template, self.namespace_template_vars, input_variables, partial
        )

        return {
            "docname": built_docname,
            "namespace": built_namespace,
            "is_shared": self.is_shared,
            "is_versioned": self.is_versioned,
            "initial_version": self.initial_version,
            "schema_template_name": self.schema_template_name,
            "schema_template_version": self.schema_template_version,
            "is_system_entity": self.is_system_entity,
            "description": self.description,
            "_source_doc_config": self.model_dump() # For introspection
        }

    def get_template_info(self) -> Dict[str, Any]:
        """
        Provides information about the templates, their placeholders, and default variables.
        """
        docname_placeholders = self._get_template_placeholders(self.docname_template)
        namespace_placeholders = self._get_template_placeholders(self.namespace_template)
        
        all_placeholders = docname_placeholders.union(namespace_placeholders)
        required_vars = set()
        for placeholder in docname_placeholders:
            if placeholder not in self.docname_template_vars or self.docname_template_vars.get(placeholder) is None:
                required_vars.add(placeholder)
        for placeholder in namespace_placeholders:
            if placeholder not in self.namespace_template_vars or self.namespace_template_vars.get(placeholder) is None:
                required_vars.add(placeholder)

        return {
            "docname_template": self.docname_template,
            "docname_placeholders": list(docname_placeholders),
            "docname_defaults": self.docname_template_vars,
            "namespace_template": self.namespace_template,
            "namespace_placeholders": list(namespace_placeholders),
            "namespace_defaults": self.namespace_template_vars,
            "all_placeholders": list(all_placeholders),
            "required_variables_without_defaults": list(required_vars),
            "static_config": {
                "is_shared": self.is_shared,
                "is_versioned": self.is_versioned,
                "initial_version": self.initial_version,
                "schema_template_name": self.schema_template_name,
                "schema_template_version": self.schema_template_version,
                "is_system_entity": self.is_system_entity,
                "description": self.description
            }
        }

class UserDocumentsConfig(BaseModel):
    """
    Container for multiple UserDocumentConfig instances, keyed by a unique document identifier.
    """
    documents: Dict[str, UserDocumentConfig] = Field(
        ...,
        description="A dictionary mapping unique keys to their UserDocumentConfig objects."
    )

    def get_document_config(self, doc_key: str) -> Optional[UserDocumentConfig]:
        """Retrieves a specific UserDocumentConfig by its key."""
        return self.documents.get(doc_key)

    def get_built_document_config(
        self,
        doc_key: str,
        variables: Dict[str, Any],
        partial: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves and builds a specific document configuration.

        Args:
            doc_key: The key of the document configuration to build.
            variables: Variables to use for building.
            partial: Whether to perform a partial build.

        Returns:
            The built document configuration dictionary, or None if doc_key is not found.
        """
        doc_config = self.get_document_config(doc_key)
        if doc_config:
            return doc_config.build_document_templates(variables, partial=partial)
        return None

    def get_built_document_configs(
        self,
        variables_map: Dict[str, Dict[str, Any]], # doc_key -> {var_name: value}
        doc_keys_to_build: Optional[List[str]] = None,
        partial_build: bool = False
    ) -> Dict[str, Dict[str, Any]]:
        """
        Builds multiple document configurations.

        Args:
            variables_map: A dictionary mapping each doc_key to its specific variables.
            doc_keys_to_build: Optional list of doc_keys to build. If None, builds all documents.
            partial_build: Whether to perform a partial build for all specified documents.

        Returns:
            A dictionary mapping each doc_key to its built configuration dictionary.
            Raises ValueError if a doc_key in doc_keys_to_build is not found or if variables are missing for a key.
        """
        results: Dict[str, Dict[str, Any]] = {}
        keys_to_process = doc_keys_to_build if doc_keys_to_build is not None else list(self.documents.keys())

        for key in keys_to_process:
            doc_config = self.get_document_config(key)
            if not doc_config:
                raise ValueError(f"Document configuration key '{key}' not found.")
            
            doc_specific_vars = variables_map.get(key)
            if doc_specific_vars is None:
                # If no specific vars for this key, but it's requested, it might be an issue
                # or rely purely on defaults. build_document_templates will handle missing mandatory vars.
                doc_specific_vars = {} # Use empty dict, relies on defaults or fails if mandatory missing

            results[key] = doc_config.build_document_templates(doc_specific_vars, partial=partial_build)
        return results

    def get_documents_info(self, doc_keys_to_inspect: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Retrieves template information for specified document configurations.

        Args:
            doc_keys_to_inspect: Optional list of doc_keys. If None, gets info for all.

        Returns:
            A dictionary mapping each doc_key to its template information.
        """
        info: Dict[str, Any] = {}
        keys_to_process = doc_keys_to_inspect if doc_keys_to_inspect is not None else list(self.documents.keys())

        for key in keys_to_process:
            doc_config = self.get_document_config(key)
            if doc_config:
                info[key] = doc_config.get_template_info()
            else:
                # Or raise error, or just skip. For info, skipping might be fine.
                # logger.warning(f"Document key '{key}' not found during info retrieval.")
                info[key] = {"error": f"Document key '{key}' not found."}
        return info


FILENAME_REF_PATTERN = re.compile(r"^\$filename:(?P<key>[^.]+)\.(?P<attr>[^.]+)(?:\.(?P<mod>built|partial|template))?$")

class AppWorkflow(BaseModel):
    """
    Defines a workflow, its inputs, and how those inputs might reference
    dynamically built document configurations.
    """
    name: str = Field(..., description="Name of the workflow.")
    version: Optional[str] = Field(..., description="Version of the workflow.")
    inputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input parameters for the workflow. Values can be static or reference document configs "
                    "using '$filename:<doc_key>.<attribute>[.modifier]' syntax."
    )
    user_documents_config_variables: Union[Dict[str, Any], Dict[str, Dict[str, Any]]] = Field(
        default_factory=dict,
        description="Variables used to populate UserDocumentConfig templates. "
                    "Structure depends on 'template_specific'."
    )
    template_specific: bool = Field(
        False,
        description="If True, 'user_documents_config_variables' is a Dict[doc_key, Dict[var_name, value]]. "
                    "If False, it's a flat Dict[var_name, value] applied globally or to specific doc_keys "
                    "if they match."
    )

    def _get_vars_for_doc_key(self, doc_key: str) -> Dict[str, Any]:
        """
        Helper to get the appropriate variables for a given document key based on
        'user_documents_config_variables' and 'template_specific'.
        """
        if self.template_specific:
            if isinstance(self.user_documents_config_variables, dict) and doc_key in self.user_documents_config_variables:
                # Ensure the value is a dict for type consistency downstream
                val = self.user_documents_config_variables[doc_key]
                return val if isinstance(val, dict) else {}
            return {} # No specific variables for this key
        else:
            # Global variables
            return self.user_documents_config_variables if isinstance(self.user_documents_config_variables, dict) else {}


    def _resolve_filename_reference(
        self,
        ref_string: str,
        docs_config: UserDocumentsConfig
    ) -> Any:
        """
        Parses a '$filename:...' reference string and resolves it to its actual value.
        """
        match = FILENAME_REF_PATTERN.match(ref_string)
        if not match:
            return ref_string # Not a filename reference, return as is

        groups = match.groupdict()
        doc_key = groups["key"]
        attribute_name = groups["attr"]
        modifier = groups.get("mod") # Can be None

        doc_config_instance = docs_config.get_document_config(doc_key)
        if not doc_config_instance:
            raise ValueError(f"Referenced document key '{doc_key}' not found in UserDocumentsConfig.")

        current_doc_vars = self._get_vars_for_doc_key(doc_key)

        # Handle modifiers for docname/namespace or retrieving the template itself
        if attribute_name in ["docname", "namespace"]:
            if modifier == "template":
                return getattr(doc_config_instance, f"{attribute_name}_template")
            
            # Default to 'built' if no modifier or 'built' is specified
            is_partial = modifier == "partial"
            built_config = doc_config_instance.build_document_templates(current_doc_vars, partial=is_partial)
            return built_config.get(attribute_name) # Get 'docname' or 'namespace' from built result

        # Handle direct attribute access (e.g., is_shared, schema_template_name)
        # These do not use modifiers like .built, .partial, .template
        if hasattr(doc_config_instance, attribute_name):
            if modifier:
                raise ValueError(f"Modifier '.{modifier}' is not applicable to attribute '{attribute_name}' of doc_key '{doc_key}'.")
            return getattr(doc_config_instance, attribute_name)
        
        # Handle case where attribute is a key in a fully built config (e.g., we want the whole built dict)
        # This can be triggered if attribute_name is 'built_config' (a convention) or similar
        # Or if we want the entire built config for a doc_key without specifying a sub-attribute
        # For this, the syntax would be $filename:my_doc_key.config.built or $filename:my_doc_key.config.partial
        if attribute_name == "config": # Convention for getting the whole built config
            is_partial = modifier == "partial" # .built is default or explicit
            return doc_config_instance.build_document_templates(current_doc_vars, partial=is_partial)

        raise ValueError(f"Invalid attribute '{attribute_name}' or modifier '{modifier}' for filename reference '{ref_string}'.")


    def _recursive_process_inputs(
        self,
        current_struct: Any,
        docs_config: UserDocumentsConfig
    ) -> Any:
        """
        Recursively traverses the input structure (dict or list) and resolves
        '$filename:...' references.
        """
        if isinstance(current_struct, dict):
            processed_dict = {}
            for key, value in current_struct.items():
                processed_dict[key] = self._recursive_process_inputs(value, docs_config)
            return processed_dict
        elif isinstance(current_struct, list):
            return [self._recursive_process_inputs(item, docs_config) for item in current_struct]
        elif isinstance(current_struct, str):
            return self._resolve_filename_reference(current_struct, docs_config)
        else:
            # Numbers, booleans, None, etc., are returned as is
            return current_struct

    def get_processed_inputs(self, docs_config: UserDocumentsConfig) -> Dict[str, Any]:
        """
        Processes the workflow's inputs, resolving all '$filename:...' references.

        Args:
            docs_config: The UserDocumentsConfig instance containing document definitions.

        Returns:
            A new dictionary with all references resolved.
        
        Raises:
            ValueError: If a reference is invalid or cannot be resolved.
        """
        if not isinstance(self.inputs, dict):
            # logger.warning("Workflow inputs are not a dictionary, cannot process.")
            return self.inputs # Or raise error, depending on strictness

        return self._recursive_process_inputs(self.inputs, docs_config)

    def _recursive_analyze_inputs(
        self,
        current_struct: Any,
        docs_config: UserDocumentsConfig,
        path: str = "inputs"
    ) -> List[Dict[str, Any]]:
        """
        Recursively analyzes inputs for $filename references and gathers info.
        """
        references_info = []
        if isinstance(current_struct, dict):
            for key, value in current_struct.items():
                references_info.extend(self._recursive_analyze_inputs(value, docs_config, f"{path}.{key}"))
        elif isinstance(current_struct, list):
            for i, item in enumerate(current_struct):
                references_info.extend(self._recursive_analyze_inputs(item, docs_config, f"{path}[{i}]"))
        elif isinstance(current_struct, str):
            match = FILENAME_REF_PATTERN.match(current_struct)
            if match:
                groups = match.groupdict()
                doc_key = groups["key"]
                doc_config_instance = docs_config.get_document_config(doc_key)
                info = {
                    "path_in_inputs": path,
                    "raw_reference": current_struct,
                    "doc_key": doc_key,
                    "attribute": groups["attr"],
                    "modifier": groups.get("mod"),
                    "doc_config_exists": doc_config_instance is not None,
                }
                if doc_config_instance:
                    info["doc_template_info"] = doc_config_instance.get_template_info()
                    current_doc_vars_needed = set(info["doc_template_info"].get("required_variables_without_defaults", []))
                    
                    # Determine what variables are provided for this doc_key by the workflow
                    provided_vars_for_key = self._get_vars_for_doc_key(doc_key)
                    
                    info["workflow_provided_variables_for_key"] = provided_vars_for_key
                    # info["still_missing_variables"] = list(current_doc_vars_needed - set(provided_vars_for_key.keys()))
                    still_missing = []
                    for req_var in current_doc_vars_needed:
                        if req_var not in provided_vars_for_key or provided_vars_for_key[req_var] is None:
                            still_missing.append(req_var)
                    info["still_missing_variables"] = sorted(list(set(still_missing))) # Ensure uniqueness and sort
                else:
                    info["error"] = f"Document key '{doc_key}' not found in UserDocumentsConfig."
                references_info.append(info)
        return references_info

    def get_unresolved_inputs_info(self, docs_config: UserDocumentsConfig) -> Dict[str, Any]:
        """
        Analyzes the workflow's inputs to find '$filename' references and report on
        their corresponding document configurations and variable requirements.
        """
        references = self._recursive_analyze_inputs(self.inputs, docs_config)
        return {
            "workflow_name": self.name,
            "workflow_version": self.version,
            "filename_references_found": references,
            "global_user_documents_config_variables": self.user_documents_config_variables if not self.template_specific else "N/A (template_specific is True)",
            "template_specific_variables_structure": self.user_documents_config_variables if self.template_specific else "N/A (template_specific is False)",
        }


# --- Default Configuration Instances ---
_user_docs_data = json.loads(USER_DOCUMENTS_CONFIG_JSON_STR)
DEFAULT_USER_DOCUMENTS_CONFIG = UserDocumentsConfig.model_validate(_user_docs_data)
# print(DEFAULT_USER_DOCUMENTS_CONFIG)
_all_workflows_raw_data = json.loads(ALL_WORKFLOWS_CONFIG_JSON_STR)
DEFAULT_ALL_WORKFLOWS: Dict[str, AppWorkflow] = {
    key: AppWorkflow.model_validate(wf_data)
    for key, wf_data in _all_workflows_raw_data.get("all_workflows", {}).items()
}
# print(DEFAULT_ALL_WORKFLOWS)

# --- FastAPI Router and Endpoints ---
artifact_router = APIRouter(
    prefix="/app-artifacts",
    tags=["App Artifacts & Templating"],
    dependencies=[Depends(get_current_active_verified_user)]
)

# --- Request/Response Models for API Endpoints (Modified) ---

class GetWorkflowRequest(BaseModel):
    workflow_key: str = Field(..., description="The key of the workflow to process from default configurations.")
    override_variables: Optional[Union[Dict[str, Any], Dict[str, Dict[str, Any]]]] = Field(
        None,
        description="Optional override for user_documents_config_variables of the selected workflow."
    )
    override_template_specific: Optional[bool] = Field(
        None,
        description="Optional override for template_specific flag of the selected workflow."
    )

class GetWorkflowResponse(BaseModel):
    original_workflow_name: str
    original_workflow_version: Optional[str]
    processed_inputs: Dict[str, Any]
    messages: List[str] = Field(default_factory=list)

class GetBuiltDocConfigsRequest(BaseModel):
    doc_keys: List[str] = Field(..., description="List of document keys to build from default UserDocumentsConfig.")
    variables: Union[Dict[str, Any], Dict[str, Dict[str, Any]]] = Field(
        ..., 
        description="Variables for building templates. Structure depends on 'template_specific_variables' flag."
    )
    template_specific_variables: bool = Field(
        False, 
        description="If True, 'variables' is a Dict[doc_key, Dict[var_name, value]]. Else, flat Dict applied to all."
    )
    partial_build: bool = Field(False, description="If true, performs a partial build allowing missing variables.")
    # documents_config removed, will use DEFAULT_USER_DOCUMENTS_CONFIG

class BuiltDocConfigItem(BaseModel):
    doc_key: str
    built_config: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class BuiltDocConfigsResponse(BaseModel):
    results: List[BuiltDocConfigItem]
    messages: List[str] = Field(default_factory=list)

class DocConfigsInfoRequest(BaseModel):
    doc_keys: Optional[List[str]] = Field(None, description="List of document keys from default UserDocumentsConfig to get info for. If None, all.")
    # documents_config removed

class DocConfigInfoItem(BaseModel):
    doc_key: str
    info: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class DocConfigsInfoResponse(BaseModel):
    results: List[DocConfigInfoItem]

class WorkflowInfoRequest(BaseModel):
    workflow_key: str = Field(..., description="The key of the workflow to get info for from default configurations.")
    # workflow_definition removed
    # documents_config removed

class WorkflowInfoResponse(BaseModel):
    workflow_name: str
    workflow_version: Optional[str]
    unresolved_inputs_analysis: Dict[str, Any]


# --- API Endpoints Implementation (Modified) ---

@artifact_router.post(
    "/get-workflow",
    response_model=GetWorkflowResponse,
    summary="Get a predefined workflow definition with its inputs resolved as per the provided variables.",
    description="Selects a workflow by key from default configurations, optionally overrides its variables, "
                "and resolves all $filename references in its inputs using default document configurations."
)
async def get_workflow(
    request_data: GetWorkflowRequest = Body(...)
) -> GetWorkflowResponse:
    workflow_template = DEFAULT_ALL_WORKFLOWS.get(request_data.workflow_key)
    if not workflow_template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow key '{request_data.workflow_key}' not found.")

    # Create a copy of the template to modify for this request
    workflow_to_process = workflow_template.model_copy(deep=True) # Assumes Pydantic V2+

    # Apply overrides
    if request_data.override_variables is not None:
        # Ensure deepcopy for override_variables if it's a complex mutable type being assigned
        workflow_to_process.user_documents_config_variables = deepcopy(request_data.override_variables) 
    if request_data.override_template_specific is not None:
        workflow_to_process.template_specific = request_data.override_template_specific
    
    messages = []
    try:
        processed_inputs = workflow_to_process.get_processed_inputs(DEFAULT_USER_DOCUMENTS_CONFIG)
        messages.append(f"Workflow '{request_data.workflow_key}' inputs processed successfully.")
        return GetWorkflowResponse(
            original_workflow_name=workflow_to_process.name,
            original_workflow_version=workflow_to_process.version,
            processed_inputs=processed_inputs,
            messages=messages
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error processing workflow '{request_data.workflow_key}': {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred while processing workflow '{request_data.workflow_key}': {str(e)}")

@artifact_router.options(
    "/get-workflow",
    response_model=WorkflowInfoResponse,
    summary="Get information about unresolved inputs and variables for a predefined workflow.",
    dependencies=[Depends(get_current_active_superuser)],
    description="Analyzes a predefined workflow (by key) to identify $filename references, "
                "the document configurations they point to (from defaults), and variables required. Needs `workflow_key` to be set in Body!"
)
async def get_workflow_processing_info(
    request_data: WorkflowInfoRequest = Body(...)
) -> WorkflowInfoResponse:
    workflow_definition = DEFAULT_ALL_WORKFLOWS.get(request_data.workflow_key)
    if not workflow_definition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow key '{request_data.workflow_key}' not found.")
    
    try:
        # Use the workflow_definition directly as get_unresolved_inputs_info does not modify it
        analysis = workflow_definition.get_unresolved_inputs_info(DEFAULT_USER_DOCUMENTS_CONFIG)
        return WorkflowInfoResponse(
            workflow_name=workflow_definition.name,
            workflow_version=workflow_definition.version,
            unresolved_inputs_analysis=analysis
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred during analysis of workflow '{request_data.workflow_key}': {str(e)}")


@artifact_router.post(
    "/doc-configs",
    response_model=BuiltDocConfigsResponse,
    summary="Get built document configurations for a list of document keys from default config.",
    description="Builds and returns document configurations (docname, namespace, etc.) "
                "for the specified keys using provided variables and the default UserDocumentsConfig."
)
async def get_built_document_configurations(
    request_data: GetBuiltDocConfigsRequest = Body(...)
) -> BuiltDocConfigsResponse:
    docs_config_source = DEFAULT_USER_DOCUMENTS_CONFIG # Use default
    results: List[BuiltDocConfigItem] = []
    messages: List[str] = []
    per_doc_key_variables: Dict[str, Dict[str, Any]] = {}

    if request_data.template_specific_variables:
        if not isinstance(request_data.variables, dict) or not all(isinstance(v, dict) for v in request_data.variables.values()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="If 'template_specific_variables' is True, 'variables' must be a Dict[str (doc_key), Dict[str, Any]]."
            )
        per_doc_key_variables = cast(Dict[str, Dict[str, Any]], request_data.variables)
    else:
        if not isinstance(request_data.variables, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="If 'template_specific_variables' is False, 'variables' must be a Dict[str, Any]."
            )
        global_vars = cast(Dict[str, Any], request_data.variables)
        for key in request_data.doc_keys:
            per_doc_key_variables[key] = global_vars.copy()

    for key in request_data.doc_keys:
        doc_config_instance = docs_config_source.get_document_config(key)
        item_result = BuiltDocConfigItem(doc_key=key)
        if not doc_config_instance:
            item_result.error = f"Document key '{key}' not found in default documents_config."
            results.append(item_result)
            messages.append(f"Error: Document key '{key}' not found.")
            continue

        current_vars = per_doc_key_variables.get(key, {})
        
        try:
            built_config = doc_config_instance.build_document_templates(
                input_variables=current_vars,
                partial=request_data.partial_build
            )
            item_result.built_config = built_config
            messages.append(f"Successfully built config for '{key}'.")
        except ValueError as e:
            item_result.error = f"Failed to build '{key}': {str(e)}"
            messages.append(f"Error building '{key}': {str(e)}")
        except Exception as e:
            item_result.error = f"Unexpected error building '{key}': {str(e)}"
            messages.append(f"Critical error building '{key}'.")
        results.append(item_result)
            
    return BuiltDocConfigsResponse(results=results, messages=messages)


@artifact_router.options(
    "/doc-configs",
    response_model=DocConfigsInfoResponse,
    summary="Get template information for specified document configurations from default config.",
    dependencies=[Depends(get_current_active_superuser)],
    description="Retrieves details about document templates, placeholders, and default variables "
                "for the specified document keys from the default UserDocumentsConfig. Superuser only. Optionally, provide `doc_keys` key with list of documents keys set in Body!"
)
async def get_document_configurations_info(
    request_data: Optional[DocConfigsInfoRequest] = Body(None)
) -> DocConfigsInfoResponse:
    docs_config_source = DEFAULT_USER_DOCUMENTS_CONFIG # Use default
    results: List[DocConfigInfoItem] = []
    
    keys_to_inspect = request_data.doc_keys if request_data and request_data.doc_keys is not None else list(docs_config_source.documents.keys())

    for key in keys_to_inspect:
        item_result = DocConfigInfoItem(doc_key=key)
        doc_config_instance = docs_config_source.get_document_config(key)
        if doc_config_instance:
            try:
                item_result.info = doc_config_instance.get_template_info()
            except Exception as e:
                item_result.error = f"Failed to get info for '{key}': {str(e)}"
        else:
            item_result.error = f"Document key '{key}' not found in default documents_config."
        results.append(item_result)
        
    return DocConfigsInfoResponse(results=results)

# To include this router in your main FastAPI app (e.g., in main.py or app.py):
# from services.kiwi_app.workflow_app.app_artifacts import artifact_router
# app.include_router(artifact_router)
