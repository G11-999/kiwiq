# Usage Guide: CodeRunnerNode

This guide explains how to configure and use the `CodeRunnerNode` to execute Python code in a secure Docker environment with full customer data integration capabilities.

## Purpose

The `CodeRunnerNode` allows your workflow to execute arbitrary Python code in a sandboxed environment. You can:

- Execute Python code with configurable resource limits (CPU, memory, timeout)
- Load customer data files and make them available to your code
- Access workflow input data through global variables in your code
- Create output files that are automatically saved as customer data documents
- Return structured results to the workflow for use by subsequent nodes
- Handle both simple data processing and complex file-based operations
- Configure custom save locations and sharing settings for output files

The code runs in a secure Docker container with read-only filesystem and network isolation, making it safe for processing untrusted or dynamic code.

## Configuration (`NodeConfig`)

You configure the `CodeRunnerNode` within the `node_config` field of its entry in the `GraphSchema`. The configuration follows the `CodeRunnerConfigSchema` schema.

### Full Config and all fields with brief explanations

```python
{
    "node_id": "my_code_runner",
    "node_name": "code_runner",  # ** Must be "code_runner" **
    "node_config": {  # This is the CodeRunnerConfigSchema
        # --- EXECUTION LIMITS ---
        "timeout_seconds": 30,           # Maximum execution time (default: 30)
        "memory_mb": 256,               # Memory limit in MB (default: 256)
        "cpus": 0.5,                    # CPU limit (default: 0.5)
        "enable_network": False,        # Allow network access (default: False)
        
        # --- CODE CONFIGURATION ---
        "default_code": '''
# Your Python code here
import json
import os

print(f"Hello! Input data: {INPUT}")

# Process data
result = {"processed": True, "input_count": len(INPUT) if INPUT else 0}

# Create output file
with open("out/results.json", "w") as f:
    json.dump(result, f, indent=2)

# Set return value
RESULT = result
''',
        
        # --- FILE HANDLING ---
        "load_data_config": {           # Optional: Load customer data files
            "load_paths": [
                {
                    "filename_config": {
                        "static_namespace": "data_files",
                        "static_docname": "input.csv"
                    },
                    "output_field_name": "csv_data"
                }
            ]
        },
        
        # --- OUTPUT FILE SAVING ---
        "persist_artifacts": True,                      # Save output files as customer data
        "default_save_namespace": "workflow_outputs_{run_id}",  # Default namespace pattern
        "default_save_is_shared": False,               # Default sharing setting
        
        # --- ERROR HANDLING ---
        "fail_node_on_code_error": False              # Whether to fail node on code errors
    }
}
```

### Configuration Sections:

1. **Execution Limits**: Control resource usage and security
   - `timeout_seconds`: Maximum time for code execution (default: 30 seconds)
   - `memory_mb`: Memory limit in megabytes (default: 256 MB)
   - `cpus`: CPU limit as a decimal (default: 0.5 cores)
   - `enable_network`: Whether code can access network (default: False for security)

2. **Code Configuration**:
   - `default_code`: Python code to execute if none provided in input. Can be overridden by input data.

3. **File Loading** (Optional):
   - `load_data_config`: Uses the same configuration as `LoadCustomerDataNode` to load files before code execution
   - Loaded files are made available in the code execution environment

4. **Output File Handling**:
   - `persist_artifacts`: Whether to save output files as customer data (default: True)
   - `default_save_namespace`: Default namespace pattern for saved files. `{run_id}` is replaced with workflow run ID
   - `default_save_is_shared`: Default sharing setting for saved files

5. **Error Handling**:
   - `fail_node_on_code_error`: If True, node fails when code execution fails. If False, returns error info in output.

## Input (`CodeRunnerInputSchema`)

The `CodeRunnerNode` accepts input data to control code execution and provide data to the code.

```python
{
    "code": "print('Custom code')",      # Optional: Python code to execute (overrides default_code)
    "input_data": {                      # Optional: Data available as INPUT global variable
        "numbers": [1, 2, 3, 4, 5],
        "user_name": "Alice",
        "settings": {"debug": True}
    },
    "load_data_inputs": {                # Optional: Input for loading customer data files
        "file_id": "report_123",         # Used if load_data_config uses dynamic paths
        "namespace": "user_reports"
    }
}
```

- **`code`** (Optional str): Python code to execute. If not provided, uses `default_code` from configuration.
- **`input_data`** (Optional Dict): Data made available to code execution as the global `INPUT` variable.
- **`load_data_inputs`** (Optional Dict): Input data passed to the LoadCustomerDataNode for dynamic file loading.

## Code Execution Environment

Your Python code runs in a secure environment with these global variables available:

### Global Variables Available in Code:

- **`INPUT`**: Dictionary containing the `input_data` from the node input
- **`FILES`**: Dictionary of loaded files (filename -> file path mapping) - available when files are loaded
- **`OUT_DIR`**: String path to output directory where you can create files (typically "out/")
- **`RESULT`**: Set this variable to return data from your code to the workflow

### Code Structure Example:

```python
# Access input data
user_name = INPUT.get("user_name", "Anonymous")
numbers = INPUT.get("numbers", [])

print(f"Processing data for {user_name}")

# Process data
total = sum(numbers)
average = total / len(numbers) if numbers else 0

# Create output files (will be saved as customer data)
import json
import os

results = {
    "user": user_name,
    "total": total,
    "average": average,
    "count": len(numbers)
}

# Save to output directory
with open(os.path.join(OUT_DIR, "results.json"), "w") as f:
    json.dump(results, f, indent=2)

# Create a report
with open(os.path.join(OUT_DIR, "report.txt"), "w") as f:
    f.write(f"Report for {user_name}\n")
    f.write(f"Total: {total}\n")
    f.write(f"Average: {average:.2f}\n")

# Return result to workflow
RESULT = results
```

### Custom Save Configuration from Code:

Your code can specify custom save configurations for output files:

```python
# Set custom save configurations
RESULT = {
    "data": {"processed": True},
    "save_file_config": {
        "default_save_config": {
            "namespace": "custom_outputs",
            "docname": "default_output",
            "is_shared": True
        },
        "save_configs": {
            "results.json": {
                "namespace": "analysis_results",
                "docname": "analysis_2024_01",
                "is_shared": False
            },
            "report.pdf": {
                "namespace": "reports",
                "docname": "monthly_report",
                "is_shared": True
            }
        }
    }
}
```

## Output (`CodeRunnerOutputSchema`)

The node produces comprehensive information about code execution and file handling.

```python
{
    "success": True,                    # Whether code execution succeeded
    "result": {                         # The value assigned to RESULT in your code
        "processed": True,
        "count": 42
    },
    "logs": "STDOUT:\nHello World!\n\nSTDERR:\n",  # Combined execution logs
    "error_message": None,              # Error message if execution failed
    "traceback": None,                  # Python traceback if execution failed
    
    # File handling results
    "loaded_files_info": {              # Info about files that were loaded
        "csv_data": {
            "filename": "data.csv",
            "content_type": "text/csv",
            "size_bytes": 1024,
            "file_path": "/path/to/data.csv"
        }
    },
    "saved_files": [                    # List of files saved as customer data
        {
            "filename": "results.json",
            "namespace": "workflow_outputs_run123",
            "docname": "results.json",
            "operation": "create",
            "size_bytes": 256,
            "document_path": "org123/workflow_outputs_run123/results.json",
            "is_shared": False
        }
    ],
    
    # Execution metadata
    "execution_time_seconds": 2.5,      # Total execution time
    "artifacts_count": 2                # Number of output files created
}
```

### Output Fields:

- **`success`**: Boolean indicating if code executed without errors
- **`result`**: The value assigned to `RESULT` global variable in your code
- **`logs`**: Combined stdout and stderr from code execution
- **`error_message`**: Error description if execution failed
- **`traceback`**: Python traceback if execution failed
- **`loaded_files_info`**: Information about customer data files that were loaded
- **`saved_files`**: Details about output files saved as customer data documents
- **`execution_time_seconds`**: Total execution time
- **`artifacts_count`**: Number of output artifacts created

## Example `GraphSchema` Snippets

### Basic Code Execution Example

```json
{
  "nodes": {
    "input_data": {
      "node_id": "input_data",
      "node_name": "input_node",
      "dynamic_output_schema": {
        "fields": {
          "numbers": {"type": "list", "required": true},
          "user_name": {"type": "str", "required": true}
        }
      },
      "edges": [
        {
          "dst_node_id": "process_data",
          "mappings": [
            {"src_field": "numbers", "dst_field": "input_data.numbers"},
            {"src_field": "user_name", "dst_field": "input_data.user_name"}
          ]
        }
      ]
    },
    
    "process_data": {
      "node_id": "process_data",
      "node_name": "code_runner",
      "node_config": {
        "timeout_seconds": 30,
        "memory_mb": 256,
        "default_code": "import statistics\nprint(f'Hello {INPUT[\"user_name\"]}!')\nresult = {'sum': sum(INPUT['numbers']), 'avg': statistics.mean(INPUT['numbers'])}\nRESULT = result"
      },
      "edges": [
        {
          "dst_node_id": "output_node",
          "mappings": [
            {"src_field": "success", "dst_field": "execution_success"},
            {"src_field": "result", "dst_field": "processing_results"}
          ]
        }
      ]
    }
  }
}
```

### File Processing Example

```json
{
  "nodes": {
    "csv_analyzer": {
      "node_id": "csv_analyzer", 
      "node_name": "code_runner",
      "node_config": {
        "timeout_seconds": 60,
        "memory_mb": 512,
        "load_data_config": {
          "load_paths": [
            {
              "filename_config": {
                "static_namespace": "uploaded_files",
                "input_docname_field": "csv_filename"
              },
              "output_field_name": "csv_data"
            }
          ]
        },
        "default_code": "import pandas as pd\nimport json\ncsv_file = list(FILES.values())[0]\ndf = pd.read_csv(csv_file)\nanalysis = {'rows': len(df), 'columns': list(df.columns)}\nwith open('out/analysis.json', 'w') as f:\n    json.dump(analysis, f)\nRESULT = analysis",
        "default_save_namespace": "csv_analysis_{run_id}",
        "persist_artifacts": True
      }
    }
  }
}
```

### Dynamic Save Configuration Example

```json
{
  "nodes": {
    "report_generator": {
      "node_id": "report_generator",
      "node_name": "code_runner", 
      "node_config": {
        "default_code": "import json\nfrom datetime import datetime\n\n# Generate report\nreport = {'timestamp': datetime.now().isoformat(), 'status': 'complete'}\n\n# Save with custom configuration\nwith open('out/report.json', 'w') as f:\n    json.dump(report, f)\n\nwith open('out/summary.txt', 'w') as f:\n    f.write('Report Summary\\nStatus: Complete')\n\n# Custom save config\nRESULT = {\n    'report': report,\n    'save_file_config': {\n        'save_configs': {\n            'report.json': {\n                'namespace': 'daily_reports',\n                'docname': f'report_{datetime.now().strftime(\"%Y%m%d\")}',\n                'is_shared': True\n            }\n        }\n    }\n}"
      }
    }
  }
}
```

## Advanced Usage Patterns

### 1. Data Analysis Pipeline

```python
# Code for processing and analyzing data
import pandas as pd
import json
from datetime import datetime

# Load and process data
data = INPUT.get('dataset', [])
df = pd.DataFrame(data)

# Perform analysis
analysis_results = {
    'total_records': len(df),
    'summary_stats': df.describe().to_dict(),
    'analysis_date': datetime.now().isoformat()
}

# Save detailed results
df.to_csv('out/processed_data.csv', index=False)
with open('out/analysis_results.json', 'w') as f:
    json.dump(analysis_results, f, indent=2)

# Generate report
with open('out/analysis_report.txt', 'w') as f:
    f.write(f"Data Analysis Report\n")
    f.write(f"Generated: {analysis_results['analysis_date']}\n")
    f.write(f"Total Records: {analysis_results['total_records']}\n")

RESULT = analysis_results
```

### 2. File Processing with Custom Libraries

```python
# Code that uses specific libraries for file processing
import os
import json
from PIL import Image
import pandas as pd

print("Processing uploaded files...")

# Process different file types
results = {"processed_files": []}

if FILES:
    for filename, filepath in FILES.items():
        file_ext = os.path.splitext(filename)[1].lower()
        
        if file_ext == '.csv':
            df = pd.read_csv(filepath)
            summary = {"type": "csv", "rows": len(df), "columns": len(df.columns)}
            results["processed_files"].append({"filename": filename, "summary": summary})
        
        elif file_ext in ['.jpg', '.png', '.gif']:
            with Image.open(filepath) as img:
                summary = {"type": "image", "size": img.size, "mode": img.mode}
                results["processed_files"].append({"filename": filename, "summary": summary})

# Save processing results
with open('out/processing_results.json', 'w') as f:
    json.dump(results, f, indent=2)

RESULT = results
```

### 3. Multi-Stage Processing with Error Handling

```python
# Code with comprehensive error handling and multi-stage processing
import json
import traceback
from datetime import datetime

def safe_process_data(data):
    try:
        # Stage 1: Data validation
        if not isinstance(data, dict):
            raise ValueError("Input data must be a dictionary")
        
        # Stage 2: Processing
        processed = {
            "original_keys": list(data.keys()),
            "processed_at": datetime.now().isoformat(),
            "item_count": len(data)
        }
        
        # Stage 3: Analysis
        if "numbers" in data and isinstance(data["numbers"], list):
            numbers = [x for x in data["numbers"] if isinstance(x, (int, float))]
            processed["analysis"] = {
                "sum": sum(numbers),
                "average": sum(numbers) / len(numbers) if numbers else 0,
                "count": len(numbers)
            }
        
        return {"success": True, "data": processed, "error": None}
        
    except Exception as e:
        return {
            "success": False, 
            "data": None, 
            "error": str(e),
            "traceback": traceback.format_exc()
        }

# Execute processing
input_data = INPUT or {}
result = safe_process_data(input_data)

# Save results and logs
with open('out/processing_results.json', 'w') as f:
    json.dump(result, f, indent=2)

with open('out/processing_log.txt', 'w') as f:
    f.write(f"Processing Log - {datetime.now().isoformat()}\n")
    f.write(f"Success: {result['success']}\n")
    if result['error']:
        f.write(f"Error: {result['error']}\n")

RESULT = result
```

## Security Considerations

The CodeRunnerNode implements several security measures:

- **Sandboxed Environment**: Code runs in a Docker container with read-only filesystem
- **Resource Limits**: Configurable CPU, memory, and timeout limits prevent resource exhaustion
- **Network Isolation**: Network access is disabled by default
- **File System Isolation**: Code can only read provided input files and write to designated output directory
- **User Isolation**: Runs as non-root user (10001:10001) within container

## Error Handling

The node provides comprehensive error information:

- **Code Errors**: Python exceptions and tracebacks are captured and returned
- **Timeout Errors**: Execution timeouts are handled gracefully
- **Resource Limit Errors**: Memory or CPU limit violations are reported
- **File Access Errors**: Problems loading or saving files are logged and reported

## Notes for Non-Coders

- Use this node when you need to run custom Python code as part of your workflow
- The `default_code` field contains the Python code that will be executed
- Set `input_data` in your workflow to pass information to the code (available as `INPUT` variable)
- Your code can create files in the `OUT_DIR` directory - these will be automatically saved
- Use `load_data_config` to make existing files available to your code
- Set the `RESULT` variable in your code to return data to the next workflow step
- Adjust `timeout_seconds` and `memory_mb` based on your code's requirements
- Set `fail_node_on_code_error` to `True` if you want the workflow to stop when code fails
- Use `default_save_namespace` to control where output files are stored
- Output files are automatically saved as customer data documents for later use
