"""
Utility functions for discovering and gathering workflow information.

This module provides functions to:
1. Discover all workflow JSON schema files
2. Extract workflow metadata (category, name, content)
3. Fetch associated workflow files (LLM inputs, testing files)
4. Get sandbox identifiers
5. Combine all workflow data into structured format

Author: AI Assistant
Date: 2025-09-26
"""

import os
import glob
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union
import logging

# For variable editing functionality
import libcst as cst
import libcst.matchers as m

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class _UpdateAssign(cst.CSTTransformer):
    """
    CST Transformer for updating variable assignments in Python files.
    Handles both regular assignments (x = value) and annotated assignments (x: type = value).
    """
    
    def __init__(self, var_name: str, new_value_node: cst.BaseExpression):
        """
        Initialize the transformer.
        
        Args:
            var_name: Name of the variable to update
            new_value_node: CST expression node representing the new value
        """
        self.var_name = var_name
        self.new_value_node = new_value_node
        self.updated = False

    def leave_Assign(self, original_node: cst.Assign, updated_node: cst.Assign) -> cst.BaseStatement:
        """Handle regular assignments: x = 1 or a = b = 1"""
        if any(m.matches(t.target, m.Name(self.var_name)) for t in original_node.targets):
            self.updated = True
            return updated_node.with_changes(value=self.new_value_node)
        return updated_node

    def leave_AnnAssign(self, original_node: cst.AnnAssign, updated_node: cst.AnnAssign) -> cst.BaseStatement:
        """Handle annotated assignments: x: int = 1"""
        if m.matches(original_node.target, m.Name(self.var_name)) and original_node.value is not None:
            self.updated = True
            return updated_node.with_changes(value=self.new_value_node)
        return updated_node


def detect_original_quote_style(code: str, var_name: str) -> str:
    """
    Detect the original quote style used for a variable in the source code.
    
    Args:
        code: Source code content
        var_name: Variable name to find
        
    Returns:
        Quote style: double quotes, single quotes, triple double quotes, or triple single quotes
    """
    import re
    
    # Look for variable assignment patterns
    patterns = [
        rf'{var_name}\s*=\s*""".*?"""',       # Triple double quotes
        rf"{var_name}\s*=\s*'''.*?'''",       # Triple single quotes  
        rf'{var_name}\s*=\s*"[^"]*"',         # Double quotes
        rf"{var_name}\s*=\s*'[^']*'",         # Single quotes
    ]
    
    for i, pattern in enumerate(patterns):
        if re.search(pattern, code, re.DOTALL):
            if i == 0:
                return '"""'
            elif i == 1:
                return "'''"
            elif i == 2:
                return '"'
            elif i == 3:
                return "'"
    
    # Default to double quotes if not found
    return '"'


def format_value_with_quotes(value: Any, quote_style: str) -> str:
    """
    Format a value using the specified quote style.
    
    Args:
        value: Value to format
        quote_style: Quote style to use
        
    Returns:
        Formatted string representation
    """
    if not isinstance(value, str):
        return repr(value)
    
    triple_double = '"""'
    triple_single = "'''"
    
    if quote_style in [triple_double, triple_single]:
        # Use triple quotes for multi-line or when preserving triple quote style
        return f'{quote_style}{value}{quote_style}'
    elif quote_style == '"':
        # Use double quotes, escape internal double quotes
        escaped_value = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped_value}"'
    elif quote_style == "'":
        # Use single quotes, escape internal single quotes  
        escaped_value = value.replace('\\', '\\\\').replace("'", "\\'")
        return f"'{escaped_value}'"
    else:
        # Fallback to repr
        return repr(value)


def update_global_var(file_path: Union[str, Path], name: str, value: Any) -> bool:
    """
    Update a global variable in a Python file while preserving formatting, comments, and quote style.
    
    Args:
        file_path: Path to the Python file to modify
        name: Variable name to update
        value: New value for the variable
        
    Returns:
        bool: True if successful, False otherwise
        
    Raises:
        ImportError: If libcst is not available
        FileNotFoundError: If the file doesn't exist
    """
 
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    try:
        # Read the current file content
        code = file_path.read_text(encoding="utf-8")
        
        # Detect original quote style for this variable
        original_quote_style = detect_original_quote_style(code, name)
        
        # Format the value preserving the original quote style
        if isinstance(value, str):
            formatted_value = format_value_with_quotes(value, original_quote_style)
            new_value_node = cst.parse_expression(formatted_value)
        else:
            # For non-string values, use repr
            new_value_node = cst.parse_expression(repr(value))
        
        # Parse the module and apply the transformer
        mod = cst.parse_module(code)
        transformer = _UpdateAssign(name, new_value_node)
        new_mod = mod.visit(transformer)
        
        # If variable wasn't found, append it at the end
        if not transformer.updated:
            # For new variables, use double quotes as default
            if isinstance(value, str):
                formatted_value = format_value_with_quotes(value, '"')
            else:
                formatted_value = repr(value)
            stmt = cst.parse_statement(f"{name} = {formatted_value}\n")
            new_mod = new_mod.with_changes(body=(*new_mod.body, stmt))
            logger.info(f"📝 APPENDING new variable '{name}' to {file_path}")
        else:
            logger.info(f"📝 UPDATING existing variable '{name}' to {file_path} (preserving {original_quote_style} quotes)")
        
        # Write the updated code back to file
        file_path.write_text(new_mod.code, encoding="utf-8")
        
        # Print the change clearly
        print(f"\n🔧 FILE EDIT: {file_path}")
        print(f"   Variable: {name}")
        print(f"   New Value: {formatted_value if isinstance(value, str) else repr(value)}")
        print(f"   Quote Style: {original_quote_style} (preserved)" if transformer.updated else "   Quote Style: \" (default for new variable)")
        print(f"   Action: {'APPEND' if not transformer.updated else 'UPDATE'}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error updating variable '{name}' in {file_path}: {e}")
        print(f"\n❌ FILE EDIT FAILED: {file_path}")
        print(f"   Variable: {name}")
        print(f"   Error: {e}")
        return False


def get_workflow_variable(workflow_info: Dict[str, Any], file_type: str, var_name: str) -> Any:
    """
    Get a specific variable value from a workflow's file.
    
    Args:
        workflow_info: Workflow information dictionary
        file_type: Type of file ('llm_inputs', 'testing_inputs', 'sandbox_setup', 'state_filter', 'wf_runner')
        var_name: Name of the variable to get
        
    Returns:
        Variable value or None if not found
    """
    try:
        if file_type == 'llm_inputs':
            module = workflow_info.get('llm_inputs')
        else:
            # Handle testing files
            testing_files = workflow_info.get('testing_files', {})
            if file_type == 'testing_inputs':
                module = testing_files.get('wf_inputs')
            elif file_type == 'sandbox_setup':
                module = testing_files.get('sandbox_setup_docs')
            elif file_type == 'state_filter':
                module = testing_files.get('wf_state_filter_mapping')
            elif file_type == 'wf_runner':
                module = testing_files.get('wf_runner')
            else:
                logger.error(f"Unknown file_type: {file_type}")
                return None
        
        if module and hasattr(module, var_name):
            return getattr(module, var_name)
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting variable '{var_name}' from {file_type}: {e}")
        return None


def get_sandbox_identifiers_variable(var_name: str) -> Any:
    """
    Get a specific variable value from the global sandbox_identifiers.py file.
    
    Args:
        var_name: Name of the variable to get
        
    Returns:
        Variable value or None if not found
    """
    try:
        sandbox_module = get_sandbox_identifiers()
        if sandbox_module and hasattr(sandbox_module, var_name):
            return getattr(sandbox_module, var_name)
        else:
            logger.debug(f"Variable '{var_name}' not found in sandbox_identifiers")
            return None
            
    except Exception as e:
        logger.error(f"Error getting sandbox_identifiers variable '{var_name}': {e}")
        return None


def update_workflow_variable(workflow_info: Dict[str, Any], file_type: str, var_name: str, value: Any) -> bool:
    """
    Update a variable in a workflow's file and reload affected modules and graph schema.
    
    Args:
        workflow_info: Workflow information dictionary
        file_type: Type of file ('llm_inputs', 'testing_inputs', 'sandbox_setup', 'state_filter', 'wf_runner')
        var_name: Name of the variable to update
        value: New value for the variable
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        workflows_root = get_workflows_root_path()
        category = workflow_info['metadata']['category']
        workflow_name = workflow_info['metadata']['workflow_name']
        
        # Determine the file path based on file_type
        if file_type == 'llm_inputs':
            file_path = workflows_root / category / workflow_name / 'wf_llm_inputs.py'
        elif file_type == 'testing_inputs':
            file_path = workflows_root / category / workflow_name / 'wf_testing' / 'wf_inputs.py'
        elif file_type == 'sandbox_setup':
            file_path = workflows_root / category / workflow_name / 'wf_testing' / 'sandbox_setup_docs.py'
        elif file_type == 'state_filter':
            file_path = workflows_root / category / workflow_name / 'wf_testing' / 'wf_state_filter_mapping.py'
        elif file_type == 'wf_runner':
            file_path = workflows_root / category / workflow_name / 'wf_testing' / 'wf_runner.py'
        else:
            logger.error(f"Unknown file_type: {file_type}")
            return False
        
        # Update the variable
        success = update_global_var(file_path, var_name, value)
        
        if success:
            print(f"🔄 RELOADING: Refreshing modules and graph schema for {category}/{workflow_name}")
            
            # Reload the affected module
            if file_type == 'llm_inputs':
                workflow_info['llm_inputs'] = load_python_module_content(file_path)
                print(f"   ✓ Reloaded LLM inputs module")
            elif file_type == 'testing_inputs':
                workflow_info['testing_files']['wf_inputs'] = load_python_module_content(file_path)
                print(f"   ✓ Reloaded testing inputs module")
            elif file_type == 'sandbox_setup':
                workflow_info['testing_files']['sandbox_setup_docs'] = load_python_module_content(file_path)
                print(f"   ✓ Reloaded sandbox setup module")
            elif file_type == 'state_filter':
                workflow_info['testing_files']['wf_state_filter_mapping'] = load_python_module_content(file_path)
                print(f"   ✓ Reloaded state filter mapping module")
            elif file_type == 'wf_runner':
                workflow_info['testing_files']['wf_runner'] = load_python_module_content(file_path)
                # Also update the testing workflow name since wf_runner contains it
                workflow_info['testing_workflow_name'] = get_workflow_testing_name(workflow_info)
                print(f"   ✓ Reloaded wf_runner module and testing workflow name")
            
            # Reload the graph schema since it may depend on the updated variables
            updated_schema = get_workflow_json_content(workflow_info)
            if updated_schema:
                workflow_info['json_schema'] = updated_schema
                print(f"   ✓ Reloaded graph schema")
            else:
                print(f"   ⚠️  Could not reload graph schema")
            
            print(f"🔄 RELOAD COMPLETE for {category}/{workflow_name}")
            
        return success
        
    except Exception as e:
        logger.error(f"Error updating workflow variable: {e}")
        print(f"❌ RELOAD FAILED: {e}")
        return False


def reload_all_workflow_inputs() -> bool:
    """
    Reload all workflow input modules (LLM inputs and testing files) across all workflows.
    This is used when global files like sandbox_identifiers.py are modified.
    
    Returns:
        bool: True if successful, False otherwise
    """
    print(f"🔄 GLOBAL RELOAD: Refreshing all workflow inputs due to global file change")
    
    try:
        # Get all workflow files that need reloading
        workflow_json_files = discover_workflow_json_files()
        reload_count = 0
        
        for workflow_info in workflow_json_files:
            category = workflow_info['category']  
            workflow_name = workflow_info['workflow_name']
            
            print(f"   Reloading inputs for {category}/{workflow_name}")
            
            # Get the workflow root path by going up one level from the JSON file
            workflow_root_path = workflow_info['file_path'].parent
            
            # Reload LLM inputs if exists
            llm_file = workflow_root_path / 'wf_llm_inputs.py'
            if llm_file.exists():
                try:
                    load_python_module_content(llm_file, extract_vars_only=True)
                    print(f"     ✓ Reloaded LLM inputs")
                except Exception as e:
                    print(f"     ⚠️  Failed to reload LLM inputs: {e}")
            
            # Reload testing files if they exist
            testing_dir = workflow_root_path / 'wf_testing'
            if testing_dir.exists():
                testing_files = ['wf_inputs.py', 'sandbox_setup_docs.py', 'wf_state_filter_mapping.py', 'wf_runner.py']
                for test_file in testing_files:
                    test_path = testing_dir / test_file
                    if test_path.exists():
                        try:
                            load_python_module_content(test_path, extract_vars_only=True)
                            print(f"     ✓ Reloaded {test_file}")
                        except Exception as e:
                            print(f"     ⚠️  Failed to reload {test_file}: {e}")
            
            reload_count += 1
        
        print(f"🔄 GLOBAL RELOAD COMPLETE: Refreshed inputs for {reload_count} workflows")
        return True
        
    except Exception as e:
        logger.error(f"Error during global workflow inputs reload: {e}")
        print(f"❌ GLOBAL RELOAD FAILED: {e}")
        return False


def update_sandbox_identifiers_variable(var_name: str, value: Any) -> bool:
    """
    Update a variable in the global sandbox_identifiers.py file and reload the module.
    
    Args:
        var_name: Name of the variable to update
        value: New value for the variable
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        workflows_root = get_workflows_root_path()
        sandbox_file = workflows_root / 'sandbox_identifiers.py'
        
        success = update_global_var(sandbox_file, var_name, value)
        
        if success:
            print(f"🔄 RELOADING: Refreshing sandbox_identifiers module")
            # Since sandbox_identifiers is global, reload all workflow inputs that might reference it
            reload_all_workflow_inputs()
            print(f"🔄 RELOAD COMPLETE for sandbox_identifiers")
        
        return success
        
    except Exception as e:
        logger.error(f"Error updating sandbox identifiers variable: {e}")
        print(f"❌ SANDBOX RELOAD FAILED: {e}")
        return False


def refresh_workflow_data(workflow_info: Dict[str, Any]) -> bool:
    """
    Refresh all modules and schema for a workflow after external changes.
    
    Args:
        workflow_info: Workflow information dictionary to refresh
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        category = workflow_info['metadata']['category']
        workflow_name = workflow_info['metadata']['workflow_name']
        
        print(f"🔄 FULL REFRESH: Reloading all data for {category}/{workflow_name}")
        
        # Reload LLM inputs
        if workflow_info['has_llm_inputs']:
            workflow_info['llm_inputs'] = get_workflow_llm_inputs(workflow_info)
            print(f"   ✓ Refreshed LLM inputs")
        
        # Reload testing files
        if workflow_info['has_testing_files']:
            workflow_info['testing_files'] = get_workflow_testing_files(workflow_info)
            print(f"   ✓ Refreshed testing files")
        
        # Reload JSON schema
        if workflow_info['has_json_schema']:
            workflow_info['json_schema'] = get_workflow_json_content(workflow_info)
            print(f"   ✓ Refreshed JSON schema")
        
        print(f"🔄 FULL REFRESH COMPLETE for {category}/{workflow_name}")
        return True
        
    except Exception as e:
        logger.error(f"Error refreshing workflow data: {e}")
        print(f"❌ FULL REFRESH FAILED: {e}")
        return False


def get_workflows_root_path() -> Path:
    """
    Get the root path for workflows relative to current file location.
    
    Current file: standalone_test_client/kiwi_client/workflow_exec_ui/workflow_utils.py
    Target: standalone_test_client/kiwi_client/workflows/active/
    
    Returns:
        Path: The absolute path to the workflows/active directory
    """
    # Get current file directory
    current_dir = Path(__file__).parent
    # Navigate back to workflows/active
    workflows_root = current_dir.parent / "workflows" / "active"
    
    if not workflows_root.exists():
        raise FileNotFoundError(f"Workflows directory not found: {workflows_root}")
    
    return workflows_root.resolve()


def discover_workflow_json_files() -> List[Dict[str, Any]]:
    """
    Discover all workflow JSON schema files matching pattern: *_json.py
    
    Returns:
        List[Dict]: List of dictionaries containing:
            - file_path: Absolute path to the JSON file
            - category: Workflow category (directory name)
            - workflow_name: Workflow name (directory name)
            - relative_path: Path relative to workflows/active
    """
    workflows_root = get_workflows_root_path()
    
    # Find all *_json.py files
    json_files = []
    pattern = "**/*_json.py"
    
    for file_path in workflows_root.glob(pattern):
        # Extract category and workflow name from path structure
        # Expected structure: workflows/active/<category>/<workflow_name>/*_json.py
        relative_path = file_path.relative_to(workflows_root)
        path_parts = relative_path.parts
        
        if len(path_parts) >= 3:  # category/workflow_name/file.py
            category = path_parts[0]
            workflow_name = path_parts[1]
            
            json_files.append({
                'file_path': file_path,
                'category': category,
                'workflow_name': workflow_name,
                'relative_path': str(relative_path),
                'filename': file_path.name
            })
    
    logger.debug(f"Found {len(json_files)} workflow JSON files")
    return json_files


def load_python_module_content(file_path: Path, extract_vars_only: bool = False) -> Optional[Any]:
    """
    Load content from a Python file.
    
    Args:
        file_path: Path to the Python file
        extract_vars_only: If True, try to extract variables even if imports fail
        
    Returns:
        Module content or None if loading fails
    """
    try:
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return None
            
        spec = importlib.util.spec_from_file_location("module", file_path)
        if spec is None or spec.loader is None:
            logger.warning(f"Could not load spec for: {file_path}")
            return None
            
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
        
    except Exception as e:
        if extract_vars_only:
            # Try to extract simple variables by parsing the file directly
            try:
                logger.warning(f"Module loading failed for {file_path}, trying variable extraction: {e}")
                return extract_variables_from_file(file_path)
            except Exception as parse_e:
                logger.error(f"Both module loading and variable extraction failed for {file_path}: {e} | {parse_e}")
                return None
        else:
            logger.error(f"Error loading module {file_path}: {e}")
            return None


def extract_variables_from_file(file_path: Path) -> Optional[Any]:
    """
    Extract simple global variables from a Python file by parsing it.
    This is a fallback when the module can't be loaded due to import errors.
    
    Args:
        file_path: Path to the Python file
        
    Returns:
        Simple module-like object with extracted variables
    """
    import ast
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse the AST
        tree = ast.parse(content)
        
        # Create a simple object to hold variables
        class VariableContainer:
            pass
        
        container = VariableContainer()
        
        # Extract simple variable assignments
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                # Handle simple assignments like: VAR_NAME = "value"
                if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    var_name = node.targets[0].id
                    
                    # Try to extract the value for simple types
                    try:
                        if isinstance(node.value, ast.Constant):  # Python 3.8+
                            var_value = node.value.value
                            setattr(container, var_name, var_value)
                        elif isinstance(node.value, ast.Str):  # Older Python versions
                            var_value = node.value.s
                            setattr(container, var_name, var_value)
                        elif isinstance(node.value, ast.Num):  # Older Python versions
                            var_value = node.value.n
                            setattr(container, var_name, var_value)
                        elif isinstance(node.value, ast.Dict):  # Simple dictionaries
                            try:
                                # Use eval for simple dict structures (limited safety but works for our use case)
                                var_value = eval(compile(ast.Expression(node.value), '<string>', 'eval'))
                                setattr(container, var_name, var_value)
                            except:
                                pass
                        elif isinstance(node.value, ast.List):  # Simple lists
                            try:
                                # Use eval for simple list structures
                                var_value = eval(compile(ast.Expression(node.value), '<string>', 'eval'))
                                setattr(container, var_name, var_value)
                            except:
                                pass
                    except:
                        # Skip complex expressions
                        pass
        
        # Return the container if it has any attributes
        if hasattr(container, '__dict__') and container.__dict__:
            logger.info(f"Extracted {len(container.__dict__)} variables from {file_path}")
            return container
        else:
            return None
            
    except Exception as e:
        logger.error(f"Error parsing file {file_path}: {e}")
        return None


def get_workflow_json_content(workflow_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract the JSON schema content from a workflow JSON file.
    Schema is always stored as a global variable (typically 'workflow_graph_schema').
    
    Args:
        workflow_info: Dictionary containing workflow file information
        
    Returns:
        Dictionary containing the workflow schema or None if extraction fails
    """
    try:
        file_path = workflow_info['file_path']
        module = load_python_module_content(file_path)
        
        if module is None:
            return None
        
        # Look for common schema variable names (schema is always a global variable)
        schema_vars = ['workflow_graph_schema', 'WORKFLOW_SCHEMA', 'GRAPH_SCHEMA', 'schema', 'workflow_schema']
        
        for var_name in schema_vars:
            if hasattr(module, var_name):
                schema = getattr(module, var_name)
                if isinstance(schema, dict):
                    logger.debug(f"Found schema variable '{var_name}' in {file_path}")
                    return schema
        
        logger.warning(f"No schema variable found in {file_path}. Looked for: {schema_vars}")
        return None
        
    except Exception as e:
        # Safely extract workflow identifier for error logging
        try:
            if isinstance(workflow_info, dict):
                if 'metadata' in workflow_info:
                    meta = workflow_info['metadata']
                    workflow_id = f"{meta.get('category', 'unknown')}/{meta.get('workflow_name', 'unknown')}"
                elif 'category' in workflow_info and 'workflow_name' in workflow_info:
                    workflow_id = f"{workflow_info['category']}/{workflow_info['workflow_name']}"
                else:
                    workflow_id = f"workflow at {workflow_info.get('file_path', 'unknown path')}"
            else:
                workflow_id = "unknown workflow"
        except:
            workflow_id = "unknown workflow"
        
        logger.error(f"Error extracting JSON content from {workflow_id}: {e}")
        return None


def get_workflow_llm_inputs(workflow_info: Dict[str, Any]) -> Optional[Any]:
    """
    Get LLM inputs file (wf_llm_inputs.py) for a workflow.
    
    Args:
        workflow_info: Dictionary containing workflow information
        
    Returns:
        Module content or None if file not found
    """
    try:
        workflows_root = get_workflows_root_path()
        llm_inputs_path = workflows_root / workflow_info['category'] / workflow_info['workflow_name'] / 'wf_llm_inputs.py'
        
        # Try normal loading first, then variable extraction fallback
        module = load_python_module_content(llm_inputs_path, extract_vars_only=False)
        if module is None:
            module = load_python_module_content(llm_inputs_path, extract_vars_only=True)
        return module
        
    except Exception as e:
        try:
            workflow_id = f"{workflow_info['metadata']['category']}/{workflow_info['metadata']['workflow_name']}" if 'metadata' in workflow_info else str(workflow_info.get('category', 'unknown'))
        except:
            workflow_id = "unknown workflow"
        logger.error(f"Error loading LLM inputs for {workflow_id}: {e}")
        return None


def get_workflow_testing_files(workflow_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get workflow testing files from wf_testing directory.
    
    Args:
        workflow_info: Dictionary containing workflow information
        
    Returns:
        Dictionary containing testing file contents:
        - wf_inputs: Content of wf_inputs.py
        - sandbox_setup_docs: Content of sandbox_setup_docs.py  
        - wf_state_filter_mapping: Content of wf_state_filter_mapping.py
        - wf_runner: Content of wf_runner.py (includes WORKFLOW_NAME_TO_INGEST_AS_FOR_TESTING)
    """
    testing_files = {
        'wf_inputs': None,
        'sandbox_setup_docs': None,
        'wf_state_filter_mapping': None,
        'wf_runner': None
    }
    
    try:
        workflows_root = get_workflows_root_path()
        testing_dir = workflows_root / workflow_info['category'] / workflow_info['workflow_name'] / 'wf_testing'
        
        if not testing_dir.exists():
            logger.warning(f"Testing directory not found: {testing_dir}")
            return testing_files
        
        # Load each testing file
        test_files = {
            'wf_inputs': 'wf_inputs.py',
            'sandbox_setup_docs': 'sandbox_setup_docs.py',
            'wf_state_filter_mapping': 'wf_state_filter_mapping.py',
            'wf_runner': 'wf_runner.py'
        }
        
        for key, filename in test_files.items():
            file_path = testing_dir / filename
            
            # For all testing files, try variable extraction fallback if normal loading fails
            # This handles cases where files import non-existent local modules
            module = load_python_module_content(file_path, extract_vars_only=False)
            if module is None:
                module = load_python_module_content(file_path, extract_vars_only=True)
            testing_files[key] = module
            
    except Exception as e:
        try:
            workflow_id = f"{workflow_info['metadata']['category']}/{workflow_info['metadata']['workflow_name']}" if 'metadata' in workflow_info else f"{workflow_info.get('category', 'unknown')}/{workflow_info.get('workflow_name', 'unknown')}"
        except:
            workflow_id = "unknown workflow"
        logger.error(f"Error loading testing files for {workflow_id}: {e}")
    
    return testing_files


def get_workflow_testing_name(workflow_info: Dict[str, Any]) -> Optional[str]:
    """
    Extract WORKFLOW_NAME_TO_INGEST_AS_FOR_TESTING from wf_runner.py file.
    
    Args:
        workflow_info: Dictionary containing workflow information
        
    Returns:
        String containing the testing workflow name or None if not found
    """
    try:
        # Check if wf_runner module is loaded
        testing_files = workflow_info.get('testing_files', {})
        wf_runner_module = testing_files.get('wf_runner')
        
        if wf_runner_module and hasattr(wf_runner_module, 'WORKFLOW_NAME_TO_INGEST_AS_FOR_TESTING'):
            testing_name = getattr(wf_runner_module, 'WORKFLOW_NAME_TO_INGEST_AS_FOR_TESTING')
            if isinstance(testing_name, str):
                return testing_name
        
        # If not available in current data, try loading directly
        workflows_root = get_workflows_root_path()
        wf_runner_path = workflows_root / workflow_info['metadata']['category'] / workflow_info['metadata']['workflow_name'] / 'wf_testing' / 'wf_runner.py'
        
        if wf_runner_path.exists():
            # Try loading module normally first, then with variable extraction fallback
            wf_runner_module = load_python_module_content(wf_runner_path, extract_vars_only=False)
            
            # If normal loading failed, try variable extraction
            if wf_runner_module is None:
                wf_runner_module = load_python_module_content(wf_runner_path, extract_vars_only=True)
            
            if wf_runner_module and hasattr(wf_runner_module, 'WORKFLOW_NAME_TO_INGEST_AS_FOR_TESTING'):
                testing_name = getattr(wf_runner_module, 'WORKFLOW_NAME_TO_INGEST_AS_FOR_TESTING')
                if isinstance(testing_name, str):
                    return testing_name
        
        logger.warning(f"WORKFLOW_NAME_TO_INGEST_AS_FOR_TESTING not found in wf_runner for {workflow_info['metadata']['category']}/{workflow_info['metadata']['workflow_name']}")
        return None
        
    except Exception as e:
        logger.error(f"Error extracting testing workflow name: {e}")
        return None


def get_sandbox_identifiers() -> Optional[Any]:
    """
    Get the sandbox_identifiers.py file content.
    
    Returns:
        Module content or None if file not found
    """
    try:
        workflows_root = get_workflows_root_path()
        sandbox_file = workflows_root / 'sandbox_identifiers.py'
        
        return load_python_module_content(sandbox_file)
        
    except Exception as e:
        logger.error(f"Error loading sandbox identifiers: {e}")
        return None


def get_all_workflows_data() -> Dict[str, Any]:
    """
    Get comprehensive data for all workflows.
    
    Returns:
        Dictionary containing:
        - workflows: List of workflow data dictionaries
        - sandbox_identifiers: Sandbox identifiers module
        - summary: Summary statistics
    """
    logger.debug("Starting comprehensive workflow data collection...")
    
    # Discover all workflows
    workflow_json_files = discover_workflow_json_files()
    
    # Get sandbox identifiers (shared across all workflows)
    sandbox_identifiers = get_sandbox_identifiers()
    
    # Process each workflow
    workflows_data = []
    
    for workflow_info in workflow_json_files:
        logger.debug(f"Processing workflow: {workflow_info['category']}/{workflow_info['workflow_name']}")
        
        # Get JSON schema content
        json_content = get_workflow_json_content(workflow_info)
        
        # Get LLM inputs
        llm_inputs = get_workflow_llm_inputs(workflow_info)
        
        # Get testing files
        testing_files = get_workflow_testing_files(workflow_info)
        
        # Get testing workflow name
        testing_workflow_name = get_workflow_testing_name({'metadata': workflow_info, 'testing_files': testing_files})
        
        # Combine all workflow data
        workflow_data = {
            'metadata': workflow_info,
            'json_schema': json_content,
            'llm_inputs': llm_inputs,
            'testing_files': testing_files,
            'testing_workflow_name': testing_workflow_name,
            'has_json_schema': json_content is not None,
            'has_llm_inputs': llm_inputs is not None,
            'has_testing_files': any(v is not None for v in testing_files.values()),
            'has_testing_workflow_name': testing_workflow_name is not None
        }
        
        workflows_data.append(workflow_data)
    
    # Create summary
    total_workflows = len(workflows_data)
    workflows_with_json = sum(1 for w in workflows_data if w['has_json_schema'])
    workflows_with_llm = sum(1 for w in workflows_data if w['has_llm_inputs'])
    workflows_with_testing = sum(1 for w in workflows_data if w['has_testing_files'])
    workflows_with_testing_name = sum(1 for w in workflows_data if w['has_testing_workflow_name'])
    
    summary = {
        'total_workflows': total_workflows,
        'workflows_with_json_schema': workflows_with_json,
        'workflows_with_llm_inputs': workflows_with_llm,
        'workflows_with_testing_files': workflows_with_testing,
        'workflows_with_testing_workflow_name': workflows_with_testing_name,
        'categories': list(set(w['metadata']['category'] for w in workflows_data))
    }
    
    result = {
        'workflows': workflows_data,
        'sandbox_identifiers': sandbox_identifiers,
        'summary': summary
    }
    
    logger.debug(f"Data collection complete. Summary: {summary}")
    return result


def get_workflow_by_name(category: str, workflow_name: str) -> Optional[Dict[str, Any]]:
    """
    Get specific workflow data by category and name.
    
    Args:
        category: Workflow category
        workflow_name: Workflow name
        
    Returns:
        Workflow data dictionary or None if not found
    """
    all_data = get_all_workflows_data()
    
    for workflow in all_data['workflows']:
        if (workflow['metadata']['category'] == category and 
            workflow['metadata']['workflow_name'] == workflow_name):
            return workflow
    
    return None


def list_available_workflows() -> List[Tuple[str, str]]:
    """
    Get a simple list of available workflows.
    
    Returns:
        List of tuples: (category, workflow_name)
    """
    workflow_json_files = discover_workflow_json_files()
    return [(w['category'], w['workflow_name']) for w in workflow_json_files]


# Convenience functions for testing and variable management
def list_workflow_variables(workflow_info: Dict[str, Any], file_type: str) -> Dict[str, Any]:
    """
    List all variables from a specific workflow file.
    
    Args:
        workflow_info: Workflow information dictionary
        file_type: Type of file ('llm_inputs', 'testing_inputs', 'sandbox_setup', 'state_filter', 'wf_runner')
        
    Returns:
        Dictionary of variable names and values
    """
    try:
        if file_type == 'llm_inputs':
            module = workflow_info.get('llm_inputs')
        else:
            testing_files = workflow_info.get('testing_files', {})
            if file_type == 'testing_inputs':
                module = testing_files.get('wf_inputs')
            elif file_type == 'sandbox_setup':
                module = testing_files.get('sandbox_setup_docs')
            elif file_type == 'state_filter':
                module = testing_files.get('wf_state_filter_mapping')
            elif file_type == 'wf_runner':
                module = testing_files.get('wf_runner')
            else:
                logger.error(f"Unknown file_type: {file_type}")
                return {}
        
        if module is None:
            return {}
        
        # Get all non-private attributes (those not starting with _)
        variables = {}
        for name in dir(module):
            if not name.startswith('_'):
                try:
                    value = getattr(module, name)
                    # Only include basic types and avoid functions/classes
                    if not callable(value):
                        variables[name] = value
                except:
                    pass
        
        return variables
        
    except Exception as e:
        logger.error(f"Error listing variables from {file_type}: {e}")
        return {}


def list_sandbox_variables() -> Dict[str, Any]:
    """
    List all variables from sandbox_identifiers.py.
    
    Returns:
        Dictionary of variable names and values
    """
    try:
        sandbox_module = get_sandbox_identifiers()
        if sandbox_module is None:
            return {}
        
        variables = {}
        for name in dir(sandbox_module):
            if not name.startswith('_'):
                try:
                    value = getattr(sandbox_module, name)
                    if not callable(value):
                        variables[name] = value
                except:
                    pass
        
        return variables
        
    except Exception as e:
        logger.error(f"Error listing sandbox variables: {e}")
        return {}


def demo_variable_editing():
    """
    Demonstrate variable editing functionality with examples.
    """
    print("\n🧪 VARIABLE EDITING DEMO")
    print("=" * 50)
    
    # Demo 1: Update sandbox identifiers
    print("\n1. Updating sandbox_identifiers.py:")
    current_vars = list_sandbox_variables()
    print(f"   Current variables: {list(current_vars.keys())}")
    
    if 'test_sandbox_company_name' in current_vars:
        old_value = current_vars['test_sandbox_company_name']
        new_value = f"{old_value}_updated"
        success = update_sandbox_identifiers_variable('test_sandbox_company_name', new_value)
        if success:
            print(f"   ✓ Updated test_sandbox_company_name: '{old_value}' → '{new_value}'")
        else:
            print(f"   ✗ Failed to update test_sandbox_company_name")
    
    # Demo 2: Update workflow variables
    print("\n2. Finding workflows with variables to update:")
    workflows_data = get_all_workflows_data()
    
    for workflow in workflows_data['workflows'][:2]:  # Demo with first 2 workflows
        category = workflow['metadata']['category']
        workflow_name = workflow['metadata']['workflow_name']
        print(f"\n   Workflow: {category}/{workflow_name}")
        
        # Check LLM inputs
        if workflow['has_llm_inputs']:
            llm_vars = list_workflow_variables(workflow, 'llm_inputs')
            print(f"     LLM Input variables: {list(llm_vars.keys())}")
            
            # Try to update a simple variable if it exists
            for var_name, var_value in llm_vars.items():
                if isinstance(var_value, str) and len(var_name) < 20:  # Simple string variable
                    print(f"     Attempting to demo edit of '{var_name}'...")
                    # Don't actually edit for demo, just show how it would work
                    print(f"     Would call: update_workflow_variable(workflow, 'llm_inputs', '{var_name}', 'new_value')")
                    break
        
        # Check testing inputs
        if workflow['has_testing_files']:
            testing_vars = list_workflow_variables(workflow, 'testing_inputs')
            if testing_vars:
                print(f"     Testing Input variables: {list(testing_vars.keys())}")


def print_workflow_summary():
    """Print a summary of all discovered workflows."""
    data = get_all_workflows_data()
    
    print("\n=== WORKFLOW DISCOVERY SUMMARY ===")
    print(f"Total workflows found: {data['summary']['total_workflows']}")
    print(f"Categories: {', '.join(data['summary']['categories'])}")
    print(f"Workflows with JSON schema: {data['summary']['workflows_with_json_schema']}")
    print(f"Workflows with LLM inputs: {data['summary']['workflows_with_llm_inputs']}")
    print(f"Workflows with testing files: {data['summary']['workflows_with_testing_files']}")
    print(f"Workflows with testing workflow name: {data['summary']['workflows_with_testing_workflow_name']}")
    
    print("\n=== INDIVIDUAL WORKFLOWS ===")
    for workflow in data['workflows']:
        meta = workflow['metadata']
        print(f"• {meta['category']}/{meta['workflow_name']}")
        print(f"  - JSON Schema: {'✓' if workflow['has_json_schema'] else '✗'}")
        print(f"  - LLM Inputs: {'✓' if workflow['has_llm_inputs'] else '✗'}")
        print(f"  - Testing Files: {'✓' if workflow['has_testing_files'] else '✗'}")
        if workflow['has_testing_workflow_name']:
            print(f"  - Testing Name: {workflow['testing_workflow_name']}")
        else:
            print(f"  - Testing Name: ✗")
    
    print(f"\n=== SANDBOX IDENTIFIERS ===")
    sandbox = data['sandbox_identifiers']
    if sandbox:
        print("✓ Found sandbox_identifiers.py")
        # Try to show some attributes if available
        if hasattr(sandbox, 'test_sandbox_company_name'):
            print(f"  - Company: {sandbox.test_sandbox_company_name}")
        if hasattr(sandbox, 'test_brief_uuid'):
            print(f"  - Brief UUID: {sandbox.test_brief_uuid}")
    else:
        print("✗ sandbox_identifiers.py not found")


def test_workflow_utilities():
    """
    Comprehensive test of all workflow utility functionality.
    """
    print("\n🧪 COMPREHENSIVE WORKFLOW UTILITIES TEST")
    print("=" * 70)
    
    try:
        # Test 1: Basic workflow discovery
        print("\n1️⃣  Testing workflow discovery...")
        workflows = list_available_workflows()
        print(f"   ✓ Found {len(workflows)} workflows")
        
        if not workflows:
            print("   ❌ No workflows found - cannot continue tests")
            return False
        
        # Test 2: Get comprehensive workflow data
        print(f"\n2️⃣  Testing comprehensive data collection...")
        all_data = get_all_workflows_data()
        print(f"   ✓ Loaded data for {all_data['summary']['total_workflows']} workflows")
        print(f"   ✓ Categories: {', '.join(all_data['summary']['categories'])}")
        print(f"   ✓ Workflows with JSON: {all_data['summary']['workflows_with_json_schema']}")
        print(f"   ✓ Workflows with LLM inputs: {all_data['summary']['workflows_with_llm_inputs']}")
        print(f"   ✓ Workflows with testing files: {all_data['summary']['workflows_with_testing_files']}")
        print(f"   ✓ Workflows with testing names: {all_data['summary']['workflows_with_testing_workflow_name']}")
        
        # Test 3: Get specific workflow
        print(f"\n3️⃣  Testing specific workflow retrieval...")
        test_category, test_name = workflows[0]
        workflow_data = get_workflow_by_name(test_category, test_name)
        
        if workflow_data:
            print(f"   ✓ Retrieved: {test_category}/{test_name}")
            print(f"     - Has JSON schema: {workflow_data['has_json_schema']}")
            print(f"     - Has LLM inputs: {workflow_data['has_llm_inputs']}")
            print(f"     - Has testing files: {workflow_data['has_testing_files']}")
            if workflow_data['has_testing_workflow_name']:
                print(f"     - Testing workflow name: {workflow_data['testing_workflow_name']}")
            else:
                print(f"     - Testing workflow name: None")
        else:
            print(f"   ❌ Failed to retrieve {test_category}/{test_name}")
            return False
        
        # Test 4: Variable listing
        print(f"\n4️⃣  Testing variable listing...")
        
        # Test sandbox variables
        sandbox_vars = list_sandbox_variables()
        print(f"   ✓ Sandbox variables ({len(sandbox_vars)}): {list(sandbox_vars.keys())}")
        
        # Test workflow variables
        if workflow_data['has_llm_inputs']:
            llm_vars = list_workflow_variables(workflow_data, 'llm_inputs')
            print(f"   ✓ LLM input variables ({len(llm_vars)}): {list(llm_vars.keys())[:5]}...")
        
        if workflow_data['has_testing_files']:
            testing_vars = list_workflow_variables(workflow_data, 'testing_inputs')
            if testing_vars:
                print(f"   ✓ Testing input variables ({len(testing_vars)}): {list(testing_vars.keys())[:5]}...")
        
        # Test 5: Variable retrieval  
        print(f"\n5️⃣  Testing variable retrieval...")
        if 'test_sandbox_company_name' in sandbox_vars:
            company_name = get_sandbox_identifiers_variable('test_sandbox_company_name')
            print(f"   ✓ Retrieved sandbox variable: test_sandbox_company_name = '{company_name}'")
        
        # Test 6: Dry run variable editing (don't actually edit, just test the logic)
        print(f"\n6️⃣  Testing variable editing logic...")
        
        # Test file path resolution for different file types
        test_workflows = [w for w in all_data['workflows'] if w['has_llm_inputs']][:1]
        
        for workflow in test_workflows:
            category = workflow['metadata']['category']
            workflow_name = workflow['metadata']['workflow_name']
            print(f"   Testing file path resolution for {category}/{workflow_name}")
            
            workflows_root = get_workflows_root_path()
            
            # Test LLM inputs path
            llm_path = workflows_root / category / workflow_name / 'wf_llm_inputs.py'
            print(f"     - LLM inputs path exists: {llm_path.exists()}")
            
            # Test testing paths
            testing_dir = workflows_root / category / workflow_name / 'wf_testing'
            if testing_dir.exists():
                wf_inputs_path = testing_dir / 'wf_inputs.py'
                sandbox_setup_path = testing_dir / 'sandbox_setup_docs.py'
                state_filter_path = testing_dir / 'wf_state_filter_mapping.py'
                
                print(f"     - Testing inputs path exists: {wf_inputs_path.exists()}")
                print(f"     - Sandbox setup path exists: {sandbox_setup_path.exists()}")
                print(f"     - State filter path exists: {state_filter_path.exists()}")
        
        # Test 7: Module loading isolation
        print(f"\n7️⃣  Testing module loading isolation...")
        workflows_to_test = all_data['workflows'][:2]  # Test first 2 workflows
        
        for i, workflow in enumerate(workflows_to_test):
            if workflow['has_llm_inputs']:
                llm_module = workflow['llm_inputs']
                print(f"   Workflow {i+1}: {workflow['metadata']['category']}/{workflow['metadata']['workflow_name']}")
                print(f"     - Module object ID: {id(llm_module)}")
                print(f"     - Module variables: {len([name for name in dir(llm_module) if not name.startswith('_')])}")
        
        # Test 8: Refresh functionality
        print(f"\n8️⃣  Testing workflow refresh functionality...")
        if workflow_data:
            original_schema = workflow_data.get('json_schema')
            original_id = id(original_schema) if original_schema else None
            
            success = refresh_workflow_data(workflow_data)
            
            if success:
                new_schema = workflow_data.get('json_schema')
                new_id = id(new_schema) if new_schema else None
                print(f"   ✓ Refresh successful")
                print(f"     - Schema reloaded: {original_id != new_id}")
            else:
                print(f"   ❌ Refresh failed")
        
        print(f"\n✅ ALL TESTS PASSED!")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_variable_editing():
    """
    Test the variable editing functionality by modifying DEFAULT_LLM_MODEL in blog_aeo_seo_scoring workflow.
    """
    print("\n🧪 TESTING VARIABLE EDITING FUNCTIONALITY")
    print("=" * 70)
    
    try:
        # Get the specific workflow
        workflow_data = get_workflow_by_name('content_studio', 'blog_aeo_seo_scoring')
        
        if not workflow_data:
            print("❌ Could not find blog_aeo_seo_scoring workflow")
            return False
            
        if not workflow_data['has_llm_inputs']:
            print("❌ Workflow has no LLM inputs")
            return False
        
        print(f"\n1️⃣  Found workflow: content_studio/blog_aeo_seo_scoring")
        
        # Get current value
        current_model = get_workflow_variable(workflow_data, 'llm_inputs', 'DEFAULT_LLM_MODEL')
        print(f"   Current DEFAULT_LLM_MODEL: {repr(current_model)}")
        
        # Update the variable
        new_model = "gpt-5-mini"
        print(f"\n2️⃣  Updating DEFAULT_LLM_MODEL to: {repr(new_model)}")
        
        success = update_workflow_variable(workflow_data, 'llm_inputs', 'DEFAULT_LLM_MODEL', new_model)
        
        if success:
            print(f"   ✅ Variable update successful!")
            
            # Verify the change
            updated_model = get_workflow_variable(workflow_data, 'llm_inputs', 'DEFAULT_LLM_MODEL')
            print(f"\n3️⃣  Verification:")
            print(f"   Updated DEFAULT_LLM_MODEL: {repr(updated_model)}")

            import ipdb; ipdb.set_trace()
            
            if updated_model == new_model:
                print(f"   ✅ Variable change verified in memory!")
                
                # Test that the file was actually updated
                print(f"\n4️⃣  Testing file persistence...")
                fresh_workflow = get_workflow_by_name('content_studio', 'blog_aeo_seo_scoring')
                fresh_model = get_workflow_variable(fresh_workflow, 'llm_inputs', 'DEFAULT_LLM_MODEL')
                print(f"   Fresh load DEFAULT_LLM_MODEL: {repr(fresh_model)}")
                
                if fresh_model == new_model:
                    print(f"   ✅ Variable change persisted to file!")
                    
                    # Restore original value
                    print(f"\n5️⃣  Restoring original value...")
                    restore_success = update_workflow_variable(workflow_data, 'llm_inputs', 'DEFAULT_LLM_MODEL', current_model)
                    
                    if restore_success:
                        restored_model = get_workflow_variable(workflow_data, 'llm_inputs', 'DEFAULT_LLM_MODEL')
                        print(f"   Restored DEFAULT_LLM_MODEL: {repr(restored_model)}")
                        print(f"   ✅ Original value restored!")
                    else:
                        print(f"   ⚠️  Failed to restore original value")
                        
                    print(f"\n✅ VARIABLE EDITING TEST PASSED!")
                    return True
                else:
                    print(f"   ❌ Variable change did not persist to file")
            else:
                print(f"   ❌ Variable not updated in memory")
        else:
            print(f"   ❌ Variable update failed")
            
        return False
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multiline_variable_editing():
    """
    Test editing a multi-line variable (B2B_BLOG_SCORING_SYSTEM_PROMPT) by replacing AEO with GEO.
    """
    print("\n🧪 TESTING MULTI-LINE VARIABLE EDITING")
    print("=" * 70)
    
    try:
        # Get the specific workflow
        workflow_data = get_workflow_by_name('content_studio', 'blog_aeo_seo_scoring')
        
        if not workflow_data:
            print("❌ Could not find blog_aeo_seo_scoring workflow")
            return False
            
        if not workflow_data['has_llm_inputs']:
            print("❌ Workflow has no LLM inputs")
            return False
        
        print(f"\n1️⃣  Found workflow: content_studio/blog_aeo_seo_scoring")
        
        # Get current value
        current_prompt = get_workflow_variable(workflow_data, 'llm_inputs', 'B2B_BLOG_SCORING_SYSTEM_PROMPT')
        if not current_prompt:
            print("❌ Could not retrieve B2B_BLOG_SCORING_SYSTEM_PROMPT")
            return False
            
        print(f"   Current prompt length: {len(current_prompt)} characters")
        aeo_count = current_prompt.count('AEO')
        print(f"   AEO occurrences: {aeo_count}")
        
        # Replace all AEO with GEO
        modified_prompt = current_prompt.replace('AEO', 'GEO')
        geo_count = modified_prompt.count('GEO')
        
        print(f"\n2️⃣  Replacing all 'AEO' with 'GEO'")
        print(f"   Expected GEO occurrences: {geo_count}")
        
        # Update the variable
        success = update_workflow_variable(workflow_data, 'llm_inputs', 'B2B_BLOG_SCORING_SYSTEM_PROMPT', modified_prompt)
        
        if success:
            # import ipdb; ipdb.set_trace()
            print(f"   ✅ Multi-line variable update successful!")
            
            # Verify the change
            updated_prompt = get_workflow_variable(workflow_data, 'llm_inputs', 'B2B_BLOG_SCORING_SYSTEM_PROMPT')
            print(f"\n3️⃣  Verification:")
            print(f"   Updated prompt length: {len(updated_prompt)} characters")
            
            updated_aeo_count = updated_prompt.count('AEO')
            updated_geo_count = updated_prompt.count('GEO')
            print(f"   AEO occurrences after update: {updated_aeo_count}")
            print(f"   GEO occurrences after update: {updated_geo_count}")
            
            if updated_aeo_count == 0 and updated_geo_count == aeo_count:
                print(f"   ✅ All AEO instances successfully replaced with GEO!")
                
                # Test that the file was actually updated
                print(f"\n4️⃣  Testing file persistence...")
                fresh_workflow = get_workflow_by_name('content_studio', 'blog_aeo_seo_scoring')
                fresh_prompt = get_workflow_variable(fresh_workflow, 'llm_inputs', 'B2B_BLOG_SCORING_SYSTEM_PROMPT')
                
                fresh_aeo_count = fresh_prompt.count('AEO')
                fresh_geo_count = fresh_prompt.count('GEO')
                print(f"   Fresh load AEO count: {fresh_aeo_count}")
                print(f"   Fresh load GEO count: {fresh_geo_count}")
                
                if fresh_aeo_count == 0 and fresh_geo_count == aeo_count:
                    print(f"   ✅ Multi-line changes persisted to file!")
                    
                    # Restore original value
                    print(f"\n5️⃣  Restoring original prompt...")
                    restore_success = update_workflow_variable(workflow_data, 'llm_inputs', 'B2B_BLOG_SCORING_SYSTEM_PROMPT', current_prompt)
                    
                    if restore_success:
                        restored_prompt = get_workflow_variable(workflow_data, 'llm_inputs', 'B2B_BLOG_SCORING_SYSTEM_PROMPT')
                        restored_aeo_count = restored_prompt.count('AEO')
                        restored_geo_count = restored_prompt.count('GEO')
                        print(f"   Restored AEO count: {restored_aeo_count}")
                        print(f"   Restored GEO count: {restored_geo_count}")
                        
                        if restored_aeo_count == aeo_count and restored_geo_count == 0:
                            print(f"   ✅ Original multi-line content restored!")
                        else:
                            print(f"   ⚠️  Restoration may not be complete")
                    else:
                        print(f"   ⚠️  Failed to restore original prompt")
                    
                    print(f"\n✅ MULTI-LINE VARIABLE EDITING TEST PASSED!")
                    return True
                else:
                    print(f"   ❌ Multi-line changes did not persist to file")
            else:
                print(f"   ❌ AEO replacement not completed correctly")
                print(f"     Expected: AEO=0, GEO={aeo_count}")
                print(f"     Actual: AEO={updated_aeo_count}, GEO={updated_geo_count}")
        else:
            print(f"   ❌ Multi-line variable update failed")
            
        return False
        
    except Exception as e:
        print(f"\n❌ MULTI-LINE TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def example_usage():
    """
    Example usage of the workflow utilities and variable editing functionality.
    """
    print("\n📚 WORKFLOW UTILITIES USAGE EXAMPLES")
    print("=" * 60)
    
    # Example 1: Basic workflow discovery
    print("\n1. Discover all workflows:")
    workflows = list_available_workflows()
    print(f"   Found {len(workflows)} workflows:")
    for category, name in workflows[:3]:  # Show first 3
        print(f"     - {category}/{name}")
    if len(workflows) > 3:
        print(f"     ... and {len(workflows) - 3} more")
    
    # Example 2: Get specific workflow data
    print("\n2. Get specific workflow data:")
    if workflows:
        category, name = workflows[0]
        workflow_data = get_workflow_by_name(category, name)
        if workflow_data:
            print(f"   Retrieved data for: {category}/{name}")
            print(f"   Has JSON schema: {workflow_data['has_json_schema']}")
            print(f"   Has LLM inputs: {workflow_data['has_llm_inputs']}")
            print(f"   Has testing files: {workflow_data['has_testing_files']}")
    
    # Example 3: List variables from a workflow
    print("\n3. List variables from workflow files:")
    if workflows:
        category, name = workflows[0]
        workflow_data = get_workflow_by_name(category, name)
        if workflow_data:
            # Show LLM input variables
            if workflow_data['has_llm_inputs']:
                llm_vars = list_workflow_variables(workflow_data, 'llm_inputs')
                print(f"   LLM input variables in {category}/{name}:")
                for var_name, var_value in list(llm_vars.items())[:3]:  # Show first 3
                    print(f"     - {var_name}: {type(var_value).__name__} = {str(var_value)[:50]}...")
            
            # Show testing variables
            if workflow_data['has_testing_files']:
                test_vars = list_workflow_variables(workflow_data, 'testing_inputs')
                if test_vars:
                    print(f"   Testing input variables in {category}/{name}:")
                    for var_name, var_value in list(test_vars.items())[:3]:  # Show first 3
                        print(f"     - {var_name}: {type(var_value).__name__} = {str(var_value)[:50]}...")
    
    # Example 4: Sandbox variables
    print("\n4. Sandbox identifier variables:")
    sandbox_vars = list_sandbox_variables()
    for var_name, var_value in sandbox_vars.items():
        print(f"   - {var_name}: {repr(var_value)}")
    
    # Example 5: Variable editing (conceptual)
    print("\n5. Variable editing examples:")
    print("   # Update a sandbox identifier:")
    print("   update_sandbox_identifiers_variable('test_sandbox_company_name', 'new_company')")
    print("   ")
    print("   # Update a workflow variable:")
    print("   workflow_data = get_workflow_by_name('content_studio', 'blog_aeo_seo_scoring')")
    print("   update_workflow_variable(workflow_data, 'llm_inputs', 'some_variable', 'new_value')")
    print("   ")
    print("   # Get a specific workflow variable:")
    print("   value = get_workflow_variable(workflow_data, 'llm_inputs', 'some_variable')")
    print("   ")
    print("   # Get a sandbox identifier variable:")
    print("   value = get_sandbox_identifiers_variable('test_sandbox_company_name')")
    
    print(f"\n💡 For interactive variable editing demo, call: demo_variable_editing()")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Run comprehensive tests
        test_workflow_utilities()
    elif len(sys.argv) > 1 and sys.argv[1] == "test_var_edit":
        # Run variable editing test
        test_variable_editing()
    elif len(sys.argv) > 1 and sys.argv[1] == "test_multiline_edit":
        # Run multi-line variable editing test
        test_multiline_variable_editing()
    elif len(sys.argv) > 1 and sys.argv[1] == "demo":
        # Run variable editing demo
        demo_variable_editing()
    elif len(sys.argv) > 1 and sys.argv[1] == "examples":
        # Show usage examples
        example_usage()
    else:
        # Default: show workflow summary
        print_workflow_summary()
