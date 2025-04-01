"""
Prompt Constructor Node.

This module provides a flexible prompt construction node that can fill templates
with variables from input data and configuration.
"""
from collections import defaultdict
import json
from typing import Any, ClassVar, Dict, List, Optional, Type, Union
import re
from pydantic import Field

from workflow_service.config.constants import PROMPT_CONSTRUCTOR_DELIMITER
from workflow_service.registry.nodes.core.base import BaseNode, BaseSchema
from workflow_service.registry.nodes.core.dynamic_nodes import DynamicSchema, BaseDynamicNode

class PromptTemplate(BaseSchema):
    """Prompt template with name and template string."""
    id: str = Field(description="Unique identifier of the prompt template")
    # NOTE: frontend consideration: In edge and out edge both have to refer to prompt template id if required (which can be handled specially in UI! just show the prompt template as block with name as title and linked to/from it)
    name: Optional[str] = Field(None, description="Name of the prompt template")
    version: Optional[str] = Field(None, description="Version of the prompt template")
    template: str = Field(description="Template string for the prompt")
    variables: Dict[str, Optional[str]] = Field(
        default_factory=dict,
        description="Dictionary of variables in the template, with optional default values or user overrides"
    )

class PromptTemplateConfig(BaseSchema):
    """Configuration for prompt templates and variable overwrites."""
    prompt_templates: Dict[str, PromptTemplate] = Field(
        description="Dictionary of prompt templates with name as key and template string as value"
    )

class PromptConstructorNode(BaseDynamicNode):
    """
    Prompt Constructor Node that fills templates with variables.
    
    This node takes input data and configuration to construct prompts based on templates.
    It supports global variable replacement across all templates or template-specific
    variable replacement using a delimiter in the variable name.
    
    The node can construct multiple prompts simultaneously and adds them to the output schema.
    """
    node_name: ClassVar[str] = "prompt_constructor"
    node_version: ClassVar[str] = "0.1.0"
    
    input_schema_cls: ClassVar[Type[DynamicSchema]] = DynamicSchema
    output_schema_cls: ClassVar[Type[DynamicSchema]] = DynamicSchema
    config_schema_cls: ClassVar[Type[PromptTemplateConfig]] = PromptTemplateConfig
    
    # Default delimiter for template-specific variable names
    DELIMITER: ClassVar[str] = PROMPT_CONSTRUCTOR_DELIMITER

    # instance params
    config: PromptTemplateConfig
    
    def process(self, input_data: DynamicSchema, config: Dict[str, Any], *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """
        Process input data and construct prompts based on templates.
        
        Args:
            input_data: Dynamic schema containing input variables
            config: Configuration containing prompt templates and variable overwrites
            
        Returns:
            Dict[str, Any]: Output data with constructed prompts
        """
        # Convert input data to dictionary
        input_dict = input_data.model_dump() if hasattr(input_data, "model_dump") else input_data
        print(json.dumps(input_dict, indent=4))
        
        # Extract prompt templates from config
        prompt_templates = {
            template.id: template.template 
            for template in self.config.prompt_templates.values()
        }
        
        # Extract variables from templates and merge with input variables
        template_variables: Dict[str, Dict[str, Optional[str]]] = {
            template.id: template.variables
            for template in self.config.prompt_templates.values()
        }

        var_to_template_id: Dict[str, List[str]] = defaultdict(list)
        for template_id, template_vars in template_variables.items():
            for var in template_vars:
                var_to_template_id[var].append(template_id)
        
        # Process any prompt templates that might be in the input data
        for prompt_var_name, prompt_var_value in input_dict.items():
            split_var = prompt_var_name.split(self.__class__.DELIMITER, 1)
            print(f"split_var: {split_var}")
            if len(split_var) > 1:
                template_id, field = split_var
                if template_id not in template_variables:
                    raise ValueError(f"Template {template_id} not found in {self.__class__.node_name} config!")
                if field not in template_variables[template_id]:
                    raise ValueError(f"Field {field} not found in template {template_id}!")
                template_variables[template_id][field] = prompt_var_value
            else:
                if prompt_var_name not in var_to_template_id:
                    raise ValueError(f"Variable {prompt_var_name} not found in any template!")
                for template_id in var_to_template_id[prompt_var_name]:
                    template_variables[template_id][prompt_var_name] = prompt_var_value
        
        # Construct prompts for each template
        constructed_prompts = {}
        for template_id, template_str in prompt_templates.items():
            # Get template-specific variables
            _template_variable_dict = {k: v for k, v in template_variables[template_id].items() if v is not None}
            print(f"_template_variable_dict: (template_id: {template_id}) {_template_variable_dict}")
            constructed_prompts[template_id] = self.build_prompt_template(template_str, _template_variable_dict)
        
        # Return the original input data with constructed prompts added
        constructed_prompts_for_output = {template_id: prompt for template_id, prompt in constructed_prompts.items() if template_id in self.__class__.output_schema_cls.model_fields}
        return self.__class__.output_schema_cls(**constructed_prompts_for_output)
    
    def build_prompt_template(self, template: str, variables: Dict[str, Any]) -> str:
        """
        Build a prompt by filling a template with variables.
        
        Args:
            template: The prompt template string with placeholders
            variables: Dictionary of variables to fill the template
            
        Returns:
            str: The constructed prompt with variables filled in
        """
        # Find all placeholders in the template
        placeholders = set(re.findall(r'\{([^{}]+)\}', template))
        placeholders_not_in_variables = placeholders - set(variables.keys())
        if placeholders_not_in_variables:
            raise ValueError(f"Variables {placeholders_not_in_variables} not found in either defaults, config overrides or provided prompt template variables!")
        
        # Replace each placeholder with its value
        return template.format(**variables)
