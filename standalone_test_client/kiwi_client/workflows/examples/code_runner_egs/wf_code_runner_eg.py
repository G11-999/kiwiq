"""
Example Workflow: Basic CodeRunner Node Demonstration

This workflow demonstrates how to use the code_runner node to:
1. Execute Python code that prints to stdout
2. Perform basic data processing operations
3. Access input data through the INPUT global variable
4. Output results using the RESULT global variable
5. Handle execution logs and results

The workflow is useful for:
- Testing basic code execution capabilities
- Learning CodeRunner node structure and configuration
- Demonstrating simple data processing workflows
- Understanding input/output data flow patterns
"""

import asyncio
import json
from typing import Dict, Any, Optional, List
from functools import partial
from datetime import datetime

# Import necessary components for workflow testing
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)
from kiwi_client.test_config import CLIENT_LOG_LEVEL
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

# Setup logger
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)


# --- Workflow Graph Definition ---
workflow_graph_schema = {
    "nodes": {
        # --- 1. Input Node ---
        "input_node": {
            "node_id": "input_node",
            "node_name": "input_node",
            "node_config": {},
            "dynamic_output_schema": {
                "fields": {
                    # Basic data for processing
                    "numbers": {
                        "type": "list",
                        "required": True,
                        "description": "List of numbers for processing"
                    },
                    "user_name": {
                        "type": "str",
                        "required": True,
                        "description": "User name for greeting"
                    },
                    "calculation_type": {
                        "type": "str",
                        "required": False,
                        "default": "statistics",
                        "description": "Type of calculation to perform"
                    }
                }
            },
            "edges": [
                {
                    "dst_node_id": "code_runner",
                    "mappings": [
                        {"src_field": "numbers", "dst_field": "input_data.numbers"},
                        {"src_field": "user_name", "dst_field": "input_data.user_name"},
                        {"src_field": "calculation_type", "dst_field": "input_data.calculation_type"}
                    ]
                }
            ]
        },
        
        # --- 2. Code Runner Node ---
        "code_runner": {
            "node_id": "code_runner",
            "node_name": "code_runner",
            "node_config": {
                # Code execution settings
                "timeout_seconds": 30,
                "memory_mb": 256,
                "cpus": 0.5,
                "enable_network": False,
                "persist_artifacts": True,
                "fail_node_on_code_error": False,  # Set to True to fail the node on code errors
                
                # Default code to execute
                "default_code": '''
# Hello World CodeRunner Example
import json
import statistics
from datetime import datetime

print("🚀 Hello World from CodeRunner!")
print("="*50)

# Access input data through global INPUT variable
user_name = INPUT.get("user_name", "Anonymous")
numbers = INPUT.get("numbers", [])
calc_type = INPUT.get("calculation_type", "statistics")

print(f"👋 Hello {user_name}!")
print(f"📊 Processing {len(numbers)} numbers: {numbers}")
print(f"🔢 Calculation type: {calc_type}")

# Basic data processing
results = {
    "greeting": f"Hello {user_name}!",
    "input_count": len(numbers),
    "timestamp": datetime.now().isoformat()
}

if numbers:
    if calc_type == "statistics":
        results.update({
            "sum": sum(numbers),
            "average": statistics.mean(numbers),
            "median": statistics.median(numbers),
            "min": min(numbers),
            "max": max(numbers),
            "range": max(numbers) - min(numbers)
        })
        
        print(f"📈 Statistics calculated:")
        print(f"   Sum: {results['sum']}")
        print(f"   Average: {results['average']:.2f}")
        print(f"   Median: {results['median']}")
        print(f"   Min: {results['min']}")
        print(f"   Max: {results['max']}")
        print(f"   Range: {results['range']}")
        
    elif calc_type == "squares":
        squares = [x**2 for x in numbers]
        results.update({
            "squares": squares,
            "sum_of_squares": sum(squares)
        })
        
        print(f"🔢 Squares calculated:")
        print(f"   Original: {numbers}")
        print(f"   Squares: {squares}")
        print(f"   Sum of squares: {sum(squares)}")
        
    elif calc_type == "fibonacci":
        # Generate fibonacci sequence up to max number
        max_num = max(numbers) if numbers else 10
        fib_sequence = []
        a, b = 0, 1
        while a <= max_num:
            fib_sequence.append(a)
            a, b = b, a + b
            
        results.update({
            "fibonacci_sequence": fib_sequence,
            "fibonacci_count": len(fib_sequence)
        })
        
        print(f"🌀 Fibonacci sequence up to {max_num}:")
        print(f"   {fib_sequence}")
        
else:
    print("⚠️  No numbers provided for processing")
    results["warning"] = "No numbers provided"

# Create output file with results
with open("out/results.json", "w") as f:
    json.dump(results, f, indent=2)
    print(f"💾 Results saved to out/results.json")

# Create a simple text report
with open("out/report.txt", "w") as f:
    f.write(f"Hello World CodeRunner Report\\n")
    f.write(f"Generated at: {results['timestamp']}\\n")
    f.write(f"User: {user_name}\\n")
    f.write(f"Numbers processed: {numbers}\\n")
    f.write(f"Calculation type: {calc_type}\\n")
    f.write("\\n--- Results ---\\n")
    for key, value in results.items():
        if key not in ["timestamp"]:
            f.write(f"{key}: {value}\\n")
    print(f"📄 Report saved to out/report.txt")

print("="*50)
print("✅ Code execution completed successfully!")

# Set the RESULT that will be returned by the node
RESULT = results
''',
                
                # Save configuration
                "default_save_namespace": "workflow_outputs_{run_id}",
                "default_save_is_shared": False
            },
            "edges": [
                {
                    "dst_node_id": "output_node",
                    "mappings": [
                        {"src_field": "success", "dst_field": "execution_success"},
                        {"src_field": "result", "dst_field": "processing_results"},
                        {"src_field": "logs", "dst_field": "execution_logs"},
                        {"src_field": "error_message", "dst_field": "error_message"},
                        {"src_field": "saved_files", "dst_field": "saved_artifacts"},
                        {"src_field": "execution_time_seconds", "dst_field": "execution_time"},
                        {"src_field": "loaded_files_info", "dst_field": "loaded_files_info"}
                    ]
                }
            ]
        },
        
        # --- 3. Output Node ---
        "output_node": {
            "node_id": "output_node",
            "node_name": "output_node",
            "node_config": {}
        }
    },
    
    # --- Define Start and End ---
    "input_node_id": "input_node",
    "output_node_id": "output_node"
}


# --- Test Execution Logic ---

async def validate_code_runner_output(
    outputs: Optional[Dict[str, Any]], 
    expected_inputs: Dict[str, Any]
) -> bool:
    """
    Custom validation function for the CodeRunner outputs.
    
    Validates that the code executed successfully and produced expected results.
    
    Args:
        outputs: The dictionary of final outputs from the workflow run
        expected_inputs: The original inputs for comparison
        
    Returns:
        True if outputs are valid, False otherwise
        
    Raises:
        AssertionError: If validation fails
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating CodeRunner outputs...")
    
    # Check execution success
    assert 'execution_success' in outputs, "Validation Failed: 'execution_success' missing in outputs."
    assert outputs['execution_success'] == True, f"Validation Failed: Code execution failed"
    
    # Check processing results
    assert 'processing_results' in outputs, "Validation Failed: 'processing_results' missing in outputs."
    
    processing_results = outputs['processing_results']
    assert processing_results is not None, "Validation Failed: Processing results are None"
    
    # Validate basic result structure
    expected_user_name = expected_inputs.get('user_name', 'Anonymous')
    assert 'greeting' in processing_results, "Validation Failed: 'greeting' missing in results"
    assert expected_user_name in processing_results['greeting'], f"Validation Failed: User name '{expected_user_name}' not in greeting"
    
    assert 'input_count' in processing_results, "Validation Failed: 'input_count' missing in results"
    expected_count = len(expected_inputs.get('numbers', []))
    assert processing_results['input_count'] == expected_count, f"Validation Failed: Expected count {expected_count}, got {processing_results['input_count']}"
    
    # Validate calculation results based on type
    calc_type = expected_inputs.get('calculation_type', 'statistics')
    numbers = expected_inputs.get('numbers', [])
    
    if numbers and calc_type == 'statistics':
        required_stats = ['sum', 'average', 'median', 'min', 'max', 'range']
        for stat in required_stats:
            assert stat in processing_results, f"Validation Failed: '{stat}' missing in statistics results"
        
        # Verify calculations
        assert processing_results['sum'] == sum(numbers), "Validation Failed: Incorrect sum calculation"
        assert processing_results['min'] == min(numbers), "Validation Failed: Incorrect min calculation"
        assert processing_results['max'] == max(numbers), "Validation Failed: Incorrect max calculation"
        
        logger.info(f"✓ Statistics validation passed - Sum: {processing_results['sum']}, Avg: {processing_results['average']:.2f}")
    
    elif numbers and calc_type == 'squares':
        assert 'squares' in processing_results, "Validation Failed: 'squares' missing in results"
        assert 'sum_of_squares' in processing_results, "Validation Failed: 'sum_of_squares' missing in results"
        
        expected_squares = [x**2 for x in numbers]
        assert processing_results['squares'] == expected_squares, "Validation Failed: Incorrect squares calculation"
        
        logger.info(f"✓ Squares validation passed - Squares: {processing_results['squares']}")
    
    # Check execution logs
    assert 'execution_logs' in outputs, "Validation Failed: 'execution_logs' missing in outputs."
    logs = outputs['execution_logs']
    assert "Hello World from CodeRunner!" in logs, "Validation Failed: Expected greeting not found in logs"
    assert "Code execution completed successfully!" in logs, "Validation Failed: Success message not found in logs"
    
    # Check saved files
    assert 'saved_artifacts' in outputs, "Validation Failed: 'saved_artifacts' missing in outputs."
    saved_files = outputs['saved_artifacts']
    assert len(saved_files) >= 1, f"Validation Failed: Expected at least 1 saved file, got {len(saved_files)}"
    
    # Verify file types
    filenames = [f['filename'] for f in saved_files]
    logger.info(f"✓ Saved files: {filenames}")
    
    # Check execution time
    assert 'execution_time' in outputs, "Validation Failed: 'execution_time' missing in outputs."
    exec_time = outputs['execution_time']
    assert exec_time > 0, f"Validation Failed: Invalid execution time: {exec_time}"
    assert exec_time < 30, f"Validation Failed: Execution time too long: {exec_time}s"
    
    logger.info(f"✓ Execution completed in {exec_time:.2f} seconds")
    logger.info("✓ CodeRunner validation passed completely.")
    
    return True


async def main_test_code_runner_basic(
    user_name: str = "TestUser",
    numbers: List[float] = None,
    calculation_type: str = "statistics"
):
    """
    Test the CodeRunner Node with basic data processing.
    
    Args:
        user_name: Name for greeting
        numbers: List of numbers to process
        calculation_type: Type of calculation ('statistics', 'squares', 'fibonacci')
    """
    if numbers is None:
        numbers = [10, 25, 30, 15, 40, 35, 20]
    
    test_name = f"CodeRunner Basic Test - {calculation_type.capitalize()}"
    print(f"\n--- Starting {test_name} ---")
    print(f"User: {user_name}")
    print(f"Numbers: {numbers}")
    print(f"Calculation Type: {calculation_type}")
    
    # Prepare workflow inputs
    WORKFLOW_INPUTS = {
        "user_name": user_name,
        "numbers": numbers,
        "calculation_type": calculation_type
    }
    
    # No setup/cleanup docs needed for this basic example
    setup_docs: List[SetupDocInfo] = []
    cleanup_docs: List[CleanupDocInfo] = []
    
    # Execute the test
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=WORKFLOW_INPUTS,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=None,  # No HITL needed for this test
        setup_docs=setup_docs,
        cleanup_docs=cleanup_docs,
        cleanup_docs_created_by_setup=False,
        validate_output_func=partial(
            validate_code_runner_output,
            expected_inputs=WORKFLOW_INPUTS
        ),
        stream_intermediate_results=True,
        poll_interval_sec=2,
        timeout_sec=120  # Allow time for code execution
    )
    
    # Display detailed results
    if final_run_outputs:
        print(f"\n--- Execution Summary ---")
        print(f"Success: {final_run_outputs.get('execution_success', False)}")
        print(f"Execution Time: {final_run_outputs.get('execution_time', 0):.2f} seconds")
        
        if final_run_outputs.get('processing_results'):
            results = final_run_outputs['processing_results']
            print(f"\n--- Processing Results ---")
            print(f"Greeting: {results.get('greeting', 'unknown')}")
            print(f"Input Count: {results.get('input_count', 0)}")
            
            if calculation_type == 'statistics' and 'sum' in results:
                print(f"Sum: {results['sum']}")
                print(f"Average: {results['average']:.2f}")
                print(f"Min/Max: {results['min']}/{results['max']}")
                print(f"Range: {results['range']}")
            elif calculation_type == 'squares' and 'squares' in results:
                print(f"Squares: {results['squares']}")
                print(f"Sum of Squares: {results['sum_of_squares']}")
            elif calculation_type == 'fibonacci' and 'fibonacci_sequence' in results:
                print(f"Fibonacci: {results['fibonacci_sequence']}")
                print(f"Count: {results['fibonacci_count']}")
        
        if final_run_outputs.get('saved_artifacts'):
            saved_files = final_run_outputs['saved_artifacts']
            print(f"\n--- Saved Files ({len(saved_files)}) ---")
            for file_info in saved_files:
                print(f"  📄 {file_info['filename']} ({file_info['size_bytes']} bytes)")
                print(f"      Namespace: {file_info['namespace']}")
                print(f"      Document: {file_info['docname']}")
        
        if final_run_outputs.get('error_message'):
            print(f"\n--- Errors ---")
            print(f"Error: {final_run_outputs['error_message']}")
        
        # Show execution logs (abbreviated)
        if final_run_outputs.get('execution_logs'):
            logs = final_run_outputs['execution_logs']
            print(f"\n--- Execution Logs (Last 500 chars) ---")
            print(logs[-500:] if len(logs) > 500 else logs)
    
    print(f"\n--- {test_name} Finished ---")
    
    return final_run_status_obj, final_run_outputs


if __name__ == "__main__":
    print("="*60)
    print("CodeRunner Basic Example")
    print("="*60)
    print("\nThis example demonstrates basic Python code execution with the CodeRunner node.")
    print("The code will:")
    print("1. Print a greeting message")
    print("2. Process a list of numbers with various calculations")
    print("3. Create output files with results")
    print("4. Return structured data to the workflow")
    
    # Configuration for different test scenarios
    test_scenarios = [
        {
            "name": "Statistics Processing",
            "config": {
                "user_name": "Alice",
                "numbers": [10, 25, 30, 15, 40, 35, 20, 45],
                "calculation_type": "statistics"
            }
        },
        {
            "name": "Squares Calculation", 
            "config": {
                "user_name": "Bob",
                "numbers": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                "calculation_type": "squares"
            }
        },
        {
            "name": "Fibonacci Generation",
            "config": {
                "user_name": "Charlie",
                "numbers": [50],  # Generate fibonacci up to 50
                "calculation_type": "fibonacci"
            }
        },
        {
            "name": "Debug Test (Fail on Error)", 
            "config": {
                "user_name": "Debug",
                "numbers": [1, 2, 3],
                "calculation_type": "statistics"
            },
            "fail_on_error": True  # Enable failing on code errors for debugging
        }
    ]
    
    # Choose which scenario to run (or run all)
    selected_scenario = 0  # Change this to run different scenarios
    
    if selected_scenario < len(test_scenarios):
        scenario = test_scenarios[selected_scenario]
        print(f"\nRunning scenario: {scenario['name']}")
        print(f"Configuration: {json.dumps(scenario['config'], indent=2)}")
        
        # Update workflow config if fail_on_error is specified
        if scenario.get('fail_on_error', False):
            print("🚨 Enabling fail_node_on_code_error for debugging")
            # Need to modify the workflow graph for this scenario
            workflow_graph_schema['nodes']['code_runner']['node_config']['fail_node_on_code_error'] = True
        
        # Handle async execution
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop and loop.is_running():
            print("\nAsync event loop already running. Adding task...")
            task = loop.create_task(main_test_code_runner_basic(**scenario['config']))
        else:
            print("\nStarting new async event loop...")
            asyncio.run(main_test_code_runner_basic(**scenario['config']))
    else:
        print(f"\nInvalid scenario selected: {selected_scenario}")
        print(f"Available scenarios (0-{len(test_scenarios)-1}):")
        for i, scenario in enumerate(test_scenarios):
            print(f"  {i}: {scenario['name']}")
    
    print("\n" + "-"*60)
    print("Run this script from the project root directory using:")
    print("PYTHONPATH=. python standalone_test_client/kiwi_client/workflows/examples/code_runner_egs/wf_code_runner_eg.py")
    print("-"*60)
