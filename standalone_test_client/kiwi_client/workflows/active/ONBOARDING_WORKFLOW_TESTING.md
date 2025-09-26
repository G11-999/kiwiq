# Blog Brief to Blog Sandbox Workflow - Onboarding Guide

## 🚀 TL;DR - Quick Setup Process

### Directory Structure
```
blog_brief_to_blog_sandbox/
├── wf_blog_brief_to_blog_json.py    # 📋 Main workflow definition & graph schema
├── wf_llm_inputs.py                 # 🤖 LLM prompts, schemas, and templates  
└── wf_testing/                      # 🧪 Testing environment
    ├── sandbox_identifiers.py       # 🏷️  Document IDs & asset names for sandbox
    ├── sandbox_setup_docs.py        # 🏗️  Creates synthetic test documents
    ├── wf_inputs.py                 # ⚡ Initial workflow inputs
    ├── wf_run_hitl_inputs.py        # 👤 HITL (Human-in-the-Loop) responses
    ├── wf_state_filter_mapping.py          # ✨ State filtering for focused debugging
    ├── wf_runner.py                 # 🏃 Main test execution script
    └── runs/                        # 📁 Test run artifacts & intermediate outputs
        └── <run_id>__<test_name>/   # 📂 Individual run folder
            ├── hitl_turn_1_state__<test_name>.json  # 🔍 Before 1st HITL
            ├── hitl_turn_2_state__<test_name>.json  # 🔍 Before 2nd HITL  
            └── final_state_<...>.md            # 📊 Final run artifacts: state
            └── final_logs_<...>.md            # 📊 Final run artifacts: logs
```

### ⚡ Quick Setup (7 steps):
1. **Edit `sandbox_identifiers.py`** → Set unique asset name & document IDs
2. **Edit `wf_inputs.py`** → Set initial workflow inputs (uses sandbox IDs)
3. **Edit `wf_run_hitl_inputs.py`** → Define HITL responses for each interaction
4. **✨ Edit `wf_state_filter_mapping.py`** → Configure state filtering for focused debugging (optional)
5. **🔥 Edit `wf_llm_inputs.py`** → Modify prompts/schemas for testing & optimization
6. **Run `python wf_runner.py`** → Execute workflow with dynamic HITL loading
7. **Check `runs/` folder** → View intermediate outputs & final results

### 🔗 File Interconnections:
- `sandbox_identifiers.py` IDs → used in `wf_inputs.py` + `sandbox_setup_docs.py`
- `wf_run_hitl_inputs.py` → loaded dynamically by `wf_runner.py` during HITL turns
- `wf_state_filter_mapping.py` → loaded by `wf_runner.py` to filter state dumps for debugging
- `wf_llm_inputs.py` prompts/schemas → imported by `wf_blog_brief_to_blog_json.py` workflow
- Workflow schema in `wf_blog_brief_to_blog_json.py` → defines expected inputs/outputs
- `wf_runner.py` → passes file paths to `run_workflow_test()` function for dynamic loading
- ⚠️ **Schema changes may require graph updates** if fields are used in graph mappings

---

## 📁 Detailed Folder Structure & Components

### Main Workflow Files

#### `wf_blog_brief_to_blog_json.py` - Core Workflow Definition
- **Purpose**: Contains the complete workflow graph schema (nodes, edges, configuration)
- **Key Components**:
  - Workflow nodes (LLM processing, document loading, HITL interactions)
  - Edge mappings for data flow between nodes
  - LLM model configurations and prompts
  - Document loading and storage configurations
- **Usage**: Referenced by test runner to execute the workflow

#### `wf_llm_inputs.py` - LLM Components & Testing Hub
- **Purpose**: Contains all LLM-related components used by the workflow
- **Key Components**:
  - System and user prompt templates
  - Output schemas for structured LLM responses
  - Template variables and construction options
- **Usage**: Imported by main workflow file for LLM node configurations
- **🔥 Testing & Optimization**:
  - **Easy prompt experimentation**: Modify prompts to test different approaches
  - **Schema iteration**: Update output schemas for better structured responses
  - **Performance testing**: Compare different prompt strategies
  - **A/B testing**: Switch between prompt versions for comparison
- **⚠️ Important**: Schema field changes may require updating graph mappings in `wf_blog_brief_to_blog_json.py` if those fields are referenced in edge mappings or node configurations

---

## 🧪 Testing Environment (`wf_testing/`)

### Configuration Files

#### `sandbox_identifiers.py` - Document & Asset Identifiers
```python
# Core identifiers used throughout testing setup
SANDBOX_ASSET_NAME = "conversation_intelligence_blog_sandbox"
BRIEF_DOCNAME = "conversation_intelligence_roi_calculator_brief"  
COMPANY_NAME = "kiwiq"
POST_UUID = "12345"
```

- **Purpose**: Centralized identifiers for sandbox documents and assets
- **Usage**: 
  - Used in `wf_inputs.py` for workflow initial inputs
  - Used in `sandbox_setup_docs.py` for creating test documents
  - Ensures consistency across all test components
- **Key Fields**:
  - `SANDBOX_ASSET_NAME`: Namespace for isolating test data
  - `BRIEF_DOCNAME`: Document name for blog brief input
  - `COMPANY_NAME`: Company identifier for document organization
  - `POST_UUID`: Unique identifier for blog post output

#### `wf_inputs.py` - Initial Workflow Inputs
```python
# Example structure
test_scenario = {
    "name": "Generate Blog Content from Brief",
    "initial_inputs": {
        "company_name": COMPANY_NAME,           # From sandbox_identifiers
        "brief_docname": BRIEF_DOCNAME,        # From sandbox_identifiers  
        "post_uuid": POST_UUID,                # From sandbox_identifiers
        "initial_status": "draft",
        "load_additional_user_files": []       # Optional additional documents
    }
}
```

- **Purpose**: Defines the starting inputs fed to the workflow
- **Structure**: Contains test scenario with named initial inputs
- **Relationship**: Uses identifiers from `sandbox_identifiers.py`

#### `wf_run_hitl_inputs.py` - HITL Response Definitions

**Required Variable Structure**:
```python
# Required variable name - must be exactly 'hitl_inputs'
hitl_inputs = [
    # Option 1: List of JSON objects (one per HITL turn)
    {
        "user_action": "provide_feedback",           # Action type
        "revision_feedback": "Please improve...",    # User feedback text
        "updated_content_draft": {                   # Updated content
            "title": "Updated Title",
            "main_content": "Updated content..."
        },
        "load_additional_user_files": []            # Optional additional docs
    },
    {
        "user_action": "complete",                  # Final approval
        "revision_feedback": None,
        "updated_content_draft": {
            "title": "Final Title", 
            "main_content": "Final content..."
        }
    }
    # Option 2: Single JSON object (used for all HITL turns)
    # hitl_inputs = { ... single object ... }
]
```

- **Purpose**: Pre-defines responses for Human-in-the-Loop interactions
- **Variable Name**: Must be exactly `hitl_inputs` (loaded dynamically)
- **Format Options**:
  - **List**: Each index corresponds to HITL turn number (0-based)
  - **Single Object**: Same response used for all HITL turns
- **Dynamic Loading**: File reloaded on each HITL turn if user presses Enter
- **Interaction Flow**:
  1. Workflow reaches HITL node
  2. System displays current turn index and file path
  3. User can edit file and press Enter to reload
  4. Or provide JSON directly in terminal

#### `wf_state_filter_mapping.py` - State Filtering Configuration ✨

**Purpose**: Filters workflow state dumps to reduce verbosity and focus on relevant data for debugging.

**Required Variable Structure**:
```python
# Required variable name - must be exactly 'state_filter_mapping'
state_filter_mapping = {
    # Filter specific nodes by their IDs
    "knowledge_enrichment_llm": {
        "structured_output": "knowledge_context",      # Rename for clarity
        "metadata.iteration_count": "iterations",      # Access nested paths
        "tool_calls": None                             # Include as-is
    },
    "content_generation_llm": {
        "structured_output": "generated_content",
        "metadata.token_usage": "tokens_used"
    },
    
    # Filter central workflow state
    "central_state": {
        "blog_brief": None,                            # Include as-is
        "blog_content": "current_blog_content",       # Rename for readability
        "user_action": "latest_user_action",          # Rename for clarity
        "generation_metadata": "llm_metadata"
    }
}
```

**Key Features**:
- **Path Access**: Use dot notation (`"metadata.token_usage"`) for nested data
- **Field Renaming**: Map `"old_path": "new_name"` for clarity
- **Include As-Is**: Use `"path": None` to keep original field name
- **Node Filtering**: Only specified nodes/central_state paths are included
- **Empty Mapping**: `{}` results in full unfiltered dumps
- **Missing File**: Defaults to unfiltered dumps with warning

**State Dump Behavior**:
- **Intermediate Dumps**: Always filtered if mapping provided
- **Final Dumps**: 
  - **With Mapping**: Creates both `raw_unfiltered_final_state__*.json` and `filtered_final_state__*.json`
  - **Without Mapping**: Creates single `final_state__*.json`

### Execution Files

#### `sandbox_setup_docs.py` - Test Document Creation
- **Purpose**: Creates synthetic documents in the sandbox environment
- **Functionality**:
  - Sets up blog briefs, company guidelines, SEO best practices
  - Uses identifiers from `sandbox_identifiers.py`
  - Creates isolated test environment with known data
- **Usage**: Called automatically by test runner during setup phase

#### `wf_runner.py` - Main Test Execution
- **Purpose**: Orchestrates the complete workflow test execution
- **Key Features**:
  - Automatic path resolution for HITL inputs and runs folder
  - Dynamic HITL input loading with file reloading capability
  - Structured artifact dumping in run-specific folders
  - Comprehensive error handling and user guidance
- **Core Function Call**: Calls `run_workflow_test()` with required paths:
  ```python
  await run_workflow_test(
      # ... other parameters ...
      hitl_inputs_file_path=default_hitl_inputs_path,    # Path to wf_run_hitl_inputs.py
      runs_folder_path=default_runs_folder_path          # Path to runs/ folder
  )
  ```
- **Path Configuration**:
  - **`hitl_inputs_file_path`**: Points to `wf_testing/wf_run_hitl_inputs.py`
  - **`runs_folder_path`**: Points to `wf_testing/runs/` for artifact storage
  - **Automatic Resolution**: `get_workflow_paths()` determines these paths relative to script location
- **Execution Flow**:
  1. Resolves file paths automatically
  2. Loads configuration from various files
  3. Sets up sandbox documents
  4. Executes workflow with HITL handling
  5. Validates outputs and cleans up

---

## 📊 Runs Folder Structure & Artifacts

### Folder Organization
```
runs/
└── <run_id>__<test_name_first_5_words>/
    ├── hitl_turn_1_state__<test_name>.json              # 🔍 Intermediate state (filtered if mapping provided)
    ├── hitl_turn_1_request_data.json               # 👤 HITL request details & response schema
    ├── hitl_turn_2_state__<test_name>.json              # 🔍 Intermediate state (filtered if mapping provided)  
    ├── hitl_turn_2_request_data.json               # 👤 HITL request details & response schema
    ├── hitl_turn_N_state__<test_name>.json              # 🔍 Intermediate state (filtered if mapping provided)
    ├── hitl_turn_N_request_data.json               # 👤 HITL request details & response schema
    ├── logs__<test_name>_<timestamp>.json               # 📋 Final execution logs
    ├── state__<test_name>_<timestamp>.json              # 📊 Final workflow state (when no mapping)
    ├── raw_unfiltered_final_state__<test_name>.json     # 📊 Raw final state (when mapping provided)
    └── filtered_final_state__<test_name>.json           # ✨ Filtered final state (when mapping provided)
```

### Artifact Types

#### Intermediate State Files (`hitl_turn_N_state__*.json`)
- **Created**: Before each HITL interaction  
- **Purpose**: Capture workflow state for debugging HITL responses
- **Content**: Workflow state (filtered if `wf_state_filter_mapping.py` provided):
  - Node outputs and intermediate results (filtered by mapping)
  - Graph state variables (filtered by mapping)
  - Always includes metadata and run information
- **Filtering**: Uses `state_filter_mapping` to focus on relevant nodes/fields only
- **Usage**: Review to understand workflow progression and debug HITL responses

#### HITL Request Data Files (`hitl_turn_N_request_data.json`) ✨
- **Created**: Before each HITL interaction (alongside state files)
- **Purpose**: Capture HITL node request details and expected response schema
- **Content**: Complete HITL interaction specification:
  - `hitl_job_id`: Unique identifier for the HITL job
  - `run_id`: Workflow run identifier
  - `hitl_turn`: HITL turn number
  - `timestamp`: When the HITL request was created
  - `request_details`: Data passed to the HITL node (what user sees)
  - `response_schema`: Expected structure of user response
  - `status`: Current HITL job status
  - `node_id`: The workflow node requesting HITL input
- **Usage**: 
  - Understand what data is presented to users during HITL
  - Debug HITL response format issues
  - Validate user responses match expected schema
  - Reference for creating proper `wf_run_hitl_inputs.py` responses

#### Final Artifacts 

**When No State Mapping Provided:**
- `logs__<test_name>_<timestamp>.json` - Complete execution logs
- `state__<test_name>_<timestamp>.json` - Final workflow state

**When State Mapping Provided:**
- `logs__<test_name>_<timestamp>.json` - Complete execution logs
- `raw_unfiltered_final_state__<test_name>.json` - Complete unfiltered final state
- `filtered_final_state__<test_name>.json` - Filtered final state using mapping

**Created**: At workflow completion
- **Purpose**: Complete execution record and final state
- **Content**: 
  - **Logs**: Execution timeline, node performance, error details
  - **State**: Final workflow state, outputs, and metadata

### Folder Naming Convention
- **Format**: `<run_id>__<test_name_first_5_words>`
- **Example**: `86681a9c-4e8f-467e-8d28-81139f2bd839__Brief_to_Blog_Generation_Workflow`
- **Benefits**: Easy identification and chronological organization

---

## 🤖 AI Assistant Integration

### Using Cursor/Claude for Workflow Development

#### Schema-Driven Development
```python
# AI assistants can reference the workflow schema to generate correct inputs
# Example: "Generate HITL inputs for a blog content approval workflow"
# Assistant will reference wf_blog_brief_to_blog_json.py schema
```

#### Recommended AI Workflows:

1. **HITL Response Generation**:
   - Prompt: "Based on the workflow schema, generate appropriate HITL responses for content approval"
   - AI references output schemas and node configurations
   - Generates properly structured JSON for `wf_run_hitl_inputs.py`

2. **Input Validation**:
   - Prompt: "Validate these workflow inputs against the schema"
   - AI checks input structure against dynamic_output_schema definitions
   - Suggests corrections for type mismatches or missing fields

3. **Debugging Assistance**:
   - Share intermediate state files from `runs/` folder
   - Prompt: "Analyze this workflow state and suggest why HITL interaction failed"
   - AI can identify data flow issues or schema mismatches

4. **Test Scenario Development**:
   - Prompt: "Create test scenarios for different blog brief types"
   - AI generates varied inputs in `wf_inputs.py` format
   - Creates corresponding HITL responses

5. **Prompt & Schema Optimization**:
   - Prompt: "Improve this system prompt for better blog content generation"
   - AI suggests enhanced prompts based on best practices
   - Generates updated output schemas with better structure
   - Identifies potential graph schema changes needed for new fields

### File Modification Best Practices with AI

#### Quick Edits with Context:
```bash
# Example prompts for AI assistants:
"Update wf_run_hitl_inputs.py to test the cancel workflow functionality"
"Modify sandbox_identifiers.py to use a different company name"  
"Add error handling HITL response to the inputs list"
"Improve the content generation prompt to produce more engaging blog titles"
"Add a 'meta_description' field to the CONTENT_GENERATION_OUTPUT_SCHEMA"
"Update the graph schema to handle the new 'seo_keywords' field from LLM output"
```

#### Schema-Aware Modifications:
- AI can read the workflow schema and suggest appropriate input/output structures
- Reference node configurations to understand expected data formats
- Generate test data that matches workflow expectations

---

## 🔧 Step-by-Step Workflow Setup

### 1. Environment Preparation
```bash
# Ensure you're in the correct directory
cd standalone_test_client/kiwi_client/workflows/active/content_studio/blog_brief_to_blog_sandbox/wf_testing

# Verify all configuration files exist
ls -la *.py
```

### 2. Configure Sandbox Identifiers
```python
# Edit sandbox_identifiers.py
SANDBOX_ASSET_NAME = "your_unique_sandbox_name"    # Change this!
BRIEF_DOCNAME = "your_blog_brief_document"         # Change this!
COMPANY_NAME = "your_company"                      # Change this!
POST_UUID = "unique_post_identifier"               # Change this!
```

### 3. Set Initial Workflow Inputs
```python
# Edit wf_inputs.py - uses identifiers from step 2
# Verify the initial_inputs match your sandbox setup
test_scenario = {
    "initial_inputs": {
        "company_name": COMPANY_NAME,        # Must match sandbox_identifiers
        "brief_docname": BRIEF_DOCNAME,     # Must match sandbox_identifiers
        "post_uuid": POST_UUID,             # Must match sandbox_identifiers
        # ... other inputs
    }
}
```

### 4. Define HITL Interactions
```python
# Edit wf_run_hitl_inputs.py
hitl_inputs = [
    {
        "user_action": "provide_feedback",     # or "complete", "cancel_workflow", "draft"
        "revision_feedback": "Your feedback text here",
        "updated_content_draft": {
            "title": "Your title",
            "main_content": "Your content..."
        }
    }
    # Add more HITL turns as needed
]
```

### 5. Configure State Filtering (Optional) ✨
```python
# Edit wf_state_filter_mapping.py for focused debugging
state_filter_mapping = {
    # Focus on key LLM nodes
    "content_generation_llm": {
        "structured_output": "generated_content",      # Rename for clarity
        "metadata.token_usage": "tokens_used"          # Track token usage
    },
    "knowledge_enrichment_llm": {
        "structured_output": "knowledge_context",
        "tool_calls": None                             # Include as-is
    },
    
    # Focus on relevant central state
    "central_state": {
        "blog_brief": None,                            # Include original brief
        "blog_content": "current_content",            # Current blog state
        "user_action": "latest_action",               # Latest user decision
        "generation_metadata": "llm_metadata"         # LLM performance data
    }
}

# For full unfiltered dumps, use: state_filter_mapping = {}
```

**Benefits**: 
- Reduces state dump size from ~10MB to ~1MB
- Focuses debugging on relevant workflow data
- Creates both raw and filtered versions for final dumps

### 6. Customize LLM Prompts & Schemas (Optional)
```python
# Edit wf_llm_inputs.py for testing different approaches
# Example: Modify system prompts for different writing styles
CONTENT_GENERATION_SYSTEM_PROMPT = """
You are an expert blog writer specializing in technical content...
# Modify this to test different prompt strategies
"""

# Example: Update output schemas for different structured responses
CONTENT_GENERATION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "main_content": {"type": "string"},
        # Add new fields here, but check graph mappings!
        "seo_keywords": {"type": "array", "items": {"type": "string"}}  # New field
    }
}
```

**⚠️ Schema Change Checklist:**
- If adding new schema fields, search `wf_blog_brief_to_blog_json.py` for existing field references
- Update edge mappings that use modified fields (look for `"src_field"` and `"dst_field"`)
- Test schema changes with a quick run to catch validation errors early

### 6. Execute Workflow
```bash
# Run the test
python wf_runner.py

# During HITL interactions:
# Option 1: Edit wf_run_hitl_inputs.py and press Enter
# Option 2: Provide JSON directly in terminal
```

### 7. Review Results
```bash
# Check the runs folder for artifacts
ls -la runs/

# View intermediate states (before each HITL)
cat runs/<run_folder>/hitl_turn_1_state__*.json

# View HITL request details (NEW - shows what user sees)
cat runs/<run_folder>/hitl_turn_1_request_data.json

# View final results  
cat runs/<run_folder>/state__*.json
```

**Using HITL Request Data for Debugging:**
- **`request_details`**: Shows data presented to user during HITL
- **`response_schema`**: Shows expected JSON structure for user response
- **Use these files** to create correct responses in `wf_run_hitl_inputs.py`
- **Example**: If `response_schema` requires `"user_action"` field, ensure your HITL input includes it

---

## 🚨 Common Issues & Troubleshooting

### HITL Input Errors
- **Issue**: Invalid JSON structure in HITL responses
- **Solution**: Reference workflow schema for correct field names and types
- **Debug Files**: Check `hitl_turn_N_request_data.json` for:
  - `response_schema`: Expected JSON structure
  - `request_details`: Context data provided to user
  - Use these to craft correct responses in `wf_run_hitl_inputs.py`
- **AI Help**: "Validate this HITL input against the workflow schema"

### Document Loading Failures  
- **Issue**: Sandbox documents not found
- **Solution**: Verify `sandbox_identifiers.py` matches `sandbox_setup_docs.py`
- **Check**: Ensure sandbox documents were created successfully

### Workflow Schema Mismatches
- **Issue**: Input types don't match expected schema
- **Solution**: Compare `wf_inputs.py` against workflow's `dynamic_output_schema`
- **AI Help**: "Generate correct inputs for this workflow schema"

### Run Folder Issues
- **Issue**: Cannot access intermediate state files
- **Solution**: Check file permissions and run folder creation
- **Location**: Files stored in `wf_testing/runs/<run_id>__<test_name>/`

### Path Configuration Issues
- **Issue**: HITL inputs file not found or runs folder not created
- **Root Cause**: `run_workflow_test()` requires specific paths to be passed
- **Solution**: Verify `wf_runner.py` correctly passes required paths:
  ```python
  # These paths are required for run_workflow_test()
  hitl_inputs_file_path=default_hitl_inputs_path    # Must point to wf_run_hitl_inputs.py
  runs_folder_path=default_runs_folder_path         # Must point to runs/ directory
  ```
- **Custom Paths**: To use different locations, modify `get_workflow_paths()` in `wf_runner.py`
- **Debug**: Check that `get_workflow_paths()` returns correct absolute paths

### State Filtering Issues ✨
- **Issue**: State dumps are too large or verbose for debugging
- **Solution**: Configure `wf_state_filter_mapping.py` to filter relevant data:
  ```python
  # Focus on specific nodes and central state fields
  state_filter_mapping = {
      "key_node_id": {"structured_output": "filtered_output"},
      "central_state": {"important_field": None}
  }
  ```
- **Empty Dumps**: Check that node IDs in mapping match actual workflow nodes
- **Missing Fields**: Verify field paths exist in node outputs (use raw dumps to inspect)
- **No Filtering**: Missing or empty `wf_state_filter_mapping.py` results in full unfiltered dumps

---

## 📚 Additional Resources

### Key Files Reference:
- **Workflow Logic**: `wf_blog_brief_to_blog_json.py`
- **LLM Components**: `wf_llm_inputs.py` 
- **Test Configuration**: `wf_testing/*.py` files
- **Execution**: `wf_testing/wf_runner.py`
- **Artifacts**: `wf_testing/runs/`

### External Dependencies:
- KIWIQ backend API for workflow execution
- Authentication tokens for API access
- Python environment with required packages

### Development Workflow:
1. Modify configuration files as needed
2. Use AI assistants for schema-compliant changes
3. Test with `wf_runner.py`
4. Review intermediate outputs for debugging
5. Iterate based on results

### Core Function Requirements:
The `run_workflow_test()` function requires two critical paths:
- **`hitl_inputs_file_path`**: Path to the HITL inputs Python file (default: `wf_testing/wf_run_hitl_inputs.py`)
- **`runs_folder_path`**: Path to artifacts storage directory (default: `wf_testing/runs/`)

These paths enable:
- Dynamic HITL input loading during workflow execution
- Structured artifact dumping for debugging and analysis
- Intermediate state capture before each HITL interaction

---

*Happy workflow testing! 🎉*
