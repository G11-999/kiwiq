"""
Example Workflow: CodeRunner Node with File Processing

This workflow demonstrates how to use the code_runner node to:
1. Load customer data files (CSV in this example)
2. Process structured data with pandas-like operations
3. Perform data aggregations and analysis
4. Generate multiple output files with different formats
5. Create visualizations and reports

The workflow showcases:
- File loading through load_data_config
- CSV data processing and analysis
- Employee salary analysis example
- Multiple output file generation
- Structured data transformations

Expected CSV format:
name,age,department,salary,years_experience
Alice,28,Engineering,85000,4
Bob,35,Marketing,65000,8
Charlie,42,Engineering,95000,12
Diana,31,Sales,70000,6
Eve,29,Engineering,80000,5
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
                    # File loading configuration
                    "data_namespace": {
                        "type": "str",
                        "required": True,
                        "description": "Namespace where the CSV file is stored"
                    },
                    "data_filename": {
                        "type": "str",
                        "required": True,
                        "description": "Name of the CSV file to load"
                    },
                    # Analysis parameters
                    "analysis_type": {
                        "type": "str",
                        "required": False,
                        "default": "comprehensive",
                        "description": "Type of analysis to perform (comprehensive, salary, department)"
                    },
                    "min_salary_filter": {
                        "type": "int",
                        "required": False,
                        "default": 0,
                        "description": "Minimum salary filter for analysis"
                    },
                    "target_department": {
                        "type": "str",
                        "required": False,
                        "default": None,
                        "description": "Specific department to focus analysis on"
                    }
                }
            },
            "edges": [
                {
                    "dst_node_id": "file_processor",
                    "mappings": [
                        {"src_field": "analysis_type", "dst_field": "input_data.analysis_type"},
                        {"src_field": "min_salary_filter", "dst_field": "input_data.min_salary_filter"},
                        {"src_field": "target_department", "dst_field": "input_data.target_department"}
                    ]
                }
            ]
        },
        
        # --- 2. File Processing CodeRunner Node ---
        "file_processor": {
            "node_id": "file_processor",
            "node_name": "code_runner",
            "node_config": {
                # Code execution settings
                "timeout_seconds": 60,
                "memory_mb": 512,
                "cpus": 1.0,
                "enable_network": False,
                "persist_artifacts": True,
                "fail_node_on_code_error": True,  # Set to True to fail the node on code errors
                
                # File loading configuration
                "load_data_config": {
                    "load_paths": [
                        {
                            "filename_config": {
                                "static_namespace": "uploaded_files",
                                "static_docname": "test_data.csv"
                            },
                            "output_field_name": "csv_data"
                        }
                    ]
                },
                
                # Data processing code
                "default_code": '''
# CSV Data Processing and Analysis
import json
import csv
import io
from collections import defaultdict, Counter
from datetime import datetime
from statistics import mean, median, stdev
import os

print("📊 Starting CSV Data Analysis")
print("="*60)

# Access input parameters
analysis_type = INPUT.get("analysis_type", "comprehensive")
min_salary_filter = INPUT.get("min_salary_filter", 0)
target_department = INPUT.get("target_department")

print(f"🔍 Analysis Type: {analysis_type}")
print(f"💰 Min Salary Filter: ${min_salary_filter:,}")
if target_department:
    print(f"🏢 Target Department: {target_department}")

# Check what files are available
print("\\n📁 Available Input Files:")
input_files = []
if os.path.exists("inputs"):
    for filename in os.listdir("inputs"):
        file_path = os.path.join("inputs", filename)
        file_size = os.path.getsize(file_path)
        print(f"  📄 {filename} ({file_size} bytes)")
        input_files.append(filename)

if not input_files:
    print("❌ No input files found!")
    RESULT = {"error": "No input files available"}
    exit()

# Find CSV file
csv_file = None
for filename in input_files:
    if filename.endswith('.csv') or 'csv' in filename.lower():
        csv_file = filename
        break

if not csv_file:
    # Try the first file
    csv_file = input_files[0]

csv_path = os.path.join("inputs", csv_file)
print(f"\\n📋 Processing CSV file: {csv_file}")

# Read and parse CSV data
employees = []
try:
    with open(csv_path, 'r', encoding='utf-8') as f:
        # Try to detect if this is CSV data
        sample = f.read(200)
        f.seek(0)
        
        if ',' in sample and ('name' in sample.lower() or 'age' in sample.lower()):
            # Looks like CSV
            reader = csv.DictReader(f)
            for row in reader:
                # Clean and convert data
                employee = {}
                for key, value in row.items():
                    key = key.strip()
                    if key.lower() == 'age':
                        employee[key] = int(value.strip()) if value.strip().isdigit() else 0
                    elif key.lower() == 'salary':
                        # Remove commas and convert to int
                        salary_str = value.strip().replace(',', '').replace('$', '')
                        employee[key] = int(salary_str) if salary_str.isdigit() else 0
                    elif key.lower() == 'years_experience':
                        employee[key] = int(value.strip()) if value.strip().isdigit() else 0
                    else:
                        employee[key] = value.strip()
                employees.append(employee)
        else:
            # Try JSON format
            f.seek(0)
            data = json.load(f)
            if isinstance(data, list):
                employees = data
            elif isinstance(data, dict) and 'data' in data:
                employees = data['data']
            
    print(f"✅ Successfully loaded {len(employees)} employee records")
    
except Exception as e:
    print(f"❌ Error reading CSV file: {e}")
    # Try reading as plain text to see what we have
    with open(csv_path, 'r', encoding='utf-8') as f:
        content = f.read()
        print(f"File content preview: {content[:200]}...")
    RESULT = {"error": f"Failed to parse CSV: {str(e)}"}
    exit()

if not employees:
    print("❌ No employee data found")
    RESULT = {"error": "No employee data found"}
    exit()

# Display sample data
print(f"\\n👥 Sample Employee Data:")
for i, emp in enumerate(employees[:3]):
    print(f"  {i+1}. {emp}")
if len(employees) > 3:
    print(f"  ... and {len(employees)-3} more records")

# Apply filters
filtered_employees = employees
if min_salary_filter > 0:
    filtered_employees = [emp for emp in filtered_employees 
                         if emp.get('salary', 0) >= min_salary_filter]
    print(f"\\n🔍 Filtered to {len(filtered_employees)} employees with salary >= ${min_salary_filter:,}")

if target_department:
    filtered_employees = [emp for emp in filtered_employees 
                         if emp.get('department', '').lower() == target_department.lower()]
    print(f"🏢 Filtered to {len(filtered_employees)} employees in {target_department}")

if not filtered_employees:
    print("❌ No employees match the filters")
    RESULT = {"error": "No employees match the specified filters"}
    exit()

# Perform analysis based on type
results = {
    "analysis_type": analysis_type,
    "total_employees": len(employees),
    "filtered_employees": len(filtered_employees),
    "min_salary_filter": min_salary_filter,
    "target_department": target_department,
    "timestamp": datetime.now().isoformat()
}

print(f"\\n📈 Performing {analysis_type} analysis...")

if analysis_type == "comprehensive" or analysis_type == "salary":
    # Salary analysis
    salaries = [emp.get('salary', 0) for emp in filtered_employees if emp.get('salary')]
    if salaries:
        salary_stats = {
            "count": len(salaries),
            "total": sum(salaries),
            "average": mean(salaries),
            "median": median(salaries),
            "min": min(salaries),
            "max": max(salaries),
            "std_dev": stdev(salaries) if len(salaries) > 1 else 0,
            "range": max(salaries) - min(salaries)
        }
        results["salary_analysis"] = salary_stats
        
        print(f"💰 Salary Statistics:")
        print(f"   Count: {salary_stats['count']}")
        print(f"   Average: ${salary_stats['average']:,.2f}")
        print(f"   Median: ${salary_stats['median']:,.2f}")
        print(f"   Range: ${salary_stats['min']:,} - ${salary_stats['max']:,}")
        print(f"   Std Dev: ${salary_stats['std_dev']:,.2f}")

if analysis_type == "comprehensive" or analysis_type == "department":
    # Department analysis
    dept_counts = Counter(emp.get('department', 'Unknown') for emp in filtered_employees)
    dept_salaries = defaultdict(list)
    
    for emp in filtered_employees:
        dept = emp.get('department', 'Unknown')
        salary = emp.get('salary', 0)
        if salary > 0:
            dept_salaries[dept].append(salary)
    
    dept_analysis = {}
    for dept, count in dept_counts.items():
        salaries = dept_salaries[dept]
        dept_stats = {
            "employee_count": count,
            "avg_salary": mean(salaries) if salaries else 0,
            "total_salary": sum(salaries),
            "min_salary": min(salaries) if salaries else 0,
            "max_salary": max(salaries) if salaries else 0
        }
        dept_analysis[dept] = dept_stats
    
    results["department_analysis"] = dept_analysis
    
    print(f"\\n🏢 Department Analysis:")
    for dept, stats in dept_analysis.items():
        print(f"   {dept}:")
        print(f"     Employees: {stats['employee_count']}")
        print(f"     Avg Salary: ${stats['avg_salary']:,.2f}")
        print(f"     Total Budget: ${stats['total_salary']:,}")

if analysis_type == "comprehensive":
    # Experience analysis
    experience_data = [emp.get('years_experience', 0) for emp in filtered_employees 
                      if emp.get('years_experience') is not None]
    if experience_data:
        exp_stats = {
            "average": mean(experience_data),
            "median": median(experience_data),
            "min": min(experience_data),
            "max": max(experience_data)
        }
        results["experience_analysis"] = exp_stats
        
        print(f"\\n🎓 Experience Analysis:")
        print(f"   Average: {exp_stats['average']:.1f} years")
        print(f"   Range: {exp_stats['min']} - {exp_stats['max']} years")
    
    # Age analysis
    ages = [emp.get('age', 0) for emp in filtered_employees if emp.get('age')]
    if ages:
        age_stats = {
            "average": mean(ages),
            "median": median(ages),
            "min": min(ages),
            "max": max(ages)
        }
        results["age_analysis"] = age_stats
        
        print(f"\\n👤 Age Analysis:")
        print(f"   Average: {age_stats['average']:.1f} years old")
        print(f"   Range: {age_stats['min']} - {age_stats['max']} years old")

# Generate detailed output files
print(f"\\n💾 Generating output files...")

# 1. JSON results file
with open("out/analysis_results.json", "w") as f:
    json.dump(results, f, indent=2)
    print(f"  📄 analysis_results.json")

# 2. Employee summary CSV
with open("out/employee_summary.csv", "w", newline='') as f:
    if filtered_employees:
        fieldnames = filtered_employees[0].keys()
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(filtered_employees)
        print(f"  📊 employee_summary.csv ({len(filtered_employees)} records)")

# 3. Department report
if "department_analysis" in results:
    with open("out/department_report.txt", "w") as f:
        f.write("DEPARTMENT ANALYSIS REPORT\\n")
        f.write("="*50 + "\\n")
        f.write(f"Generated: {results['timestamp']}\\n")
        f.write(f"Total Employees Analyzed: {results['filtered_employees']}\\n\\n")
        
        for dept, stats in results["department_analysis"].items():
            f.write(f"DEPARTMENT: {dept}\\n")
            f.write(f"  Employee Count: {stats['employee_count']}\\n")
            f.write(f"  Average Salary: ${stats['avg_salary']:,.2f}\\n")
            f.write(f"  Total Budget: ${stats['total_salary']:,}\\n")
            f.write(f"  Salary Range: ${stats['min_salary']:,} - ${stats['max_salary']:,}\\n")
            f.write("\\n")
        
        print(f"  📋 department_report.txt")

# 4. Executive summary
with open("out/executive_summary.txt", "w") as f:
    f.write("EXECUTIVE SUMMARY\\n")
    f.write("="*40 + "\\n")
    f.write(f"Analysis Date: {results['timestamp']}\\n")
    f.write(f"Analysis Type: {analysis_type.title()}\\n")
    f.write(f"Total Employees: {results['total_employees']}\\n")
    f.write(f"Employees Analyzed: {results['filtered_employees']}\\n")
    
    if "salary_analysis" in results:
        sal = results["salary_analysis"]
        f.write(f"\\nSALARY OVERVIEW:\\n")
        f.write(f"  Average Salary: ${sal['average']:,.2f}\\n")
        f.write(f"  Median Salary: ${sal['median']:,.2f}\\n")
        f.write(f"  Salary Range: ${sal['min']:,} - ${sal['max']:,}\\n")
        f.write(f"  Total Payroll: ${sal['total']:,}\\n")
    
    if "department_analysis" in results:
        f.write(f"\\nDEPARTMENT OVERVIEW:\\n")
        dept_analysis = results["department_analysis"]
        total_budget = sum(stats['total_salary'] for stats in dept_analysis.values())
        f.write(f"  Total Departments: {len(dept_analysis)}\\n")
        f.write(f"  Total Department Budget: ${total_budget:,}\\n")
        
        # Top paying department
        top_dept = max(dept_analysis.items(), key=lambda x: x[1]['avg_salary'])
        f.write(f"  Highest Avg Salary Dept: {top_dept[0]} (${top_dept[1]['avg_salary']:,.2f})\\n")
    
    print(f"  📈 executive_summary.txt")

# Set file-specific save configurations
save_file_config = {
    "analysis_results.json": {
        "namespace": f"analysis_output_{datetime.now().strftime('%Y%m%d')}",
        "docname": f"analysis_results_{analysis_type}.json",
        "is_shared": False
    },
    "department_report.txt": {
        "namespace": f"reports_{datetime.now().strftime('%Y%m%d')}",
        "docname": f"dept_report_{analysis_type}.txt",
        "is_shared": True  # Share reports with team
    }
}

# Add save config to global scope for the CodeRunner to use
SAVE_FILE_CONFIG = save_file_config

print("="*60)
print("✅ Analysis completed successfully!")
print(f"📁 Generated {len([f for f in os.listdir('out') if os.path.isfile(os.path.join('out', f))])} output files")

# Set the RESULT that will be returned by the node
RESULT = results
''',
                
                # Save configuration
                "default_save_namespace": "csv_analysis_{run_id}",
                "default_save_is_shared": False
            },
            "edges": [
                {
                    "dst_node_id": "output_node",
                    "mappings": [
                        {"src_field": "success", "dst_field": "processing_success"},
                        {"src_field": "result", "dst_field": "analysis_results"},
                        {"src_field": "logs", "dst_field": "processing_logs"},
                        {"src_field": "error_message", "dst_field": "error_message"},
                        {"src_field": "saved_files", "dst_field": "output_files"},
                        {"src_field": "execution_time_seconds", "dst_field": "processing_time"},
                        {"src_field": "loaded_files_info", "dst_field": "input_files_info"}
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

async def validate_file_processing_output(
    outputs: Optional[Dict[str, Any]], 
    expected_inputs: Dict[str, Any]
) -> bool:
    """
    Custom validation function for the file processing CodeRunner outputs.
    
    Validates CSV processing, data analysis, and file generation.
    
    Args:
        outputs: The dictionary of final outputs from the workflow run
        expected_inputs: The original inputs for comparison
        
    Returns:
        True if outputs are valid, False otherwise
        
    Raises:
        AssertionError: If validation fails
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating file processing outputs...")
    
    # Check processing success
    assert 'processing_success' in outputs, "Validation Failed: 'processing_success' missing in outputs."
    assert outputs['processing_success'] == True, f"Validation Failed: File processing failed"
    
    # Check analysis results
    assert 'analysis_results' in outputs, "Validation Failed: 'analysis_results' missing in outputs."
    
    analysis_results = outputs['analysis_results']
    assert analysis_results is not None, "Validation Failed: Analysis results are None"
    
    # Validate basic result structure
    assert 'analysis_type' in analysis_results, "Validation Failed: 'analysis_type' missing in results"
    assert 'total_employees' in analysis_results, "Validation Failed: 'total_employees' missing in results"
    assert 'filtered_employees' in analysis_results, "Validation Failed: 'filtered_employees' missing in results"
    
    expected_analysis_type = expected_inputs.get('analysis_type', 'comprehensive')
    assert analysis_results['analysis_type'] == expected_analysis_type, f"Validation Failed: Expected analysis type '{expected_analysis_type}', got '{analysis_results['analysis_type']}'"
    
    # Check that we processed some employees
    assert analysis_results['total_employees'] > 0, "Validation Failed: No employees found in data"
    assert analysis_results['filtered_employees'] > 0, "Validation Failed: No employees passed filters"
    
    logger.info(f"✓ Processed {analysis_results['total_employees']} total employees")
    logger.info(f"✓ Analyzed {analysis_results['filtered_employees']} filtered employees")
    
    # Validate analysis type specific results
    if expected_analysis_type in ['comprehensive', 'salary']:
        assert 'salary_analysis' in analysis_results, "Validation Failed: 'salary_analysis' missing"
        sal_analysis = analysis_results['salary_analysis']
        
        required_salary_fields = ['count', 'average', 'median', 'min', 'max']
        for field in required_salary_fields:
            assert field in sal_analysis, f"Validation Failed: '{field}' missing in salary analysis"
        
        assert sal_analysis['average'] > 0, "Validation Failed: Average salary should be > 0"
        assert sal_analysis['min'] <= sal_analysis['max'], "Validation Failed: Min salary should be <= max salary"
        
        logger.info(f"✓ Salary analysis - Avg: ${sal_analysis['average']:,.2f}, Range: ${sal_analysis['min']:,} - ${sal_analysis['max']:,}")
    
    if expected_analysis_type in ['comprehensive', 'department']:
        assert 'department_analysis' in analysis_results, "Validation Failed: 'department_analysis' missing"
        dept_analysis = analysis_results['department_analysis']
        assert len(dept_analysis) > 0, "Validation Failed: No departments found"
        
        # Validate department structure
        for dept_name, dept_stats in dept_analysis.items():
            required_dept_fields = ['employee_count', 'avg_salary', 'total_salary']
            for field in required_dept_fields:
                assert field in dept_stats, f"Validation Failed: '{field}' missing in department '{dept_name}'"
        
        logger.info(f"✓ Department analysis - {len(dept_analysis)} departments analyzed")
    
    # Check input files were loaded
    assert 'input_files_info' in outputs, "Validation Failed: 'input_files_info' missing in outputs."
    input_files = outputs['input_files_info']
    if input_files:
        logger.info(f"✓ Input files loaded: {list(input_files.keys())}")
    
    # Check output files were generated
    assert 'output_files' in outputs, "Validation Failed: 'output_files' missing in outputs."
    output_files = outputs['output_files']
    assert len(output_files) >= 2, f"Validation Failed: Expected at least 2 output files, got {len(output_files)}"
    
    # Verify specific output files
    output_filenames = [f['filename'] for f in output_files]
    expected_files = ['analysis_results.json']
    for expected_file in expected_files:
        assert any(expected_file in filename for filename in output_filenames), f"Validation Failed: Expected output file '{expected_file}' not found"
    
    logger.info(f"✓ Generated {len(output_files)} output files: {output_filenames}")
    
    # Check processing time
    assert 'processing_time' in outputs, "Validation Failed: 'processing_time' missing in outputs."
    proc_time = outputs['processing_time']
    assert proc_time > 0, f"Validation Failed: Invalid processing time: {proc_time}"
    assert proc_time < 60, f"Validation Failed: Processing time too long: {proc_time}s"
    
    logger.info(f"✓ Processing completed in {proc_time:.2f} seconds")
    
    # Check processing logs for key indicators
    assert 'processing_logs' in outputs, "Validation Failed: 'processing_logs' missing in outputs."
    logs = outputs['processing_logs']
    assert "Starting CSV Data Analysis" in logs, "Validation Failed: Expected start message not found in logs"
    assert "Analysis completed successfully!" in logs, "Validation Failed: Success message not found in logs"
    
    logger.info("✓ File processing validation passed completely.")
    
    return True


async def main_test_file_processing(
    data_namespace: str = "uploaded_files",
    data_filename: str = "test_data.csv",
    analysis_type: str = "comprehensive",
    min_salary_filter: int = 0,
    target_department: Optional[str] = None,
    setup_test_data: bool = True
):
    """
    Test the CodeRunner Node with file processing capabilities.
    
    Args:
        data_namespace: Namespace where CSV file is stored
        data_filename: Name of the CSV file
        analysis_type: Type of analysis to perform
        min_salary_filter: Minimum salary for filtering
        target_department: Department to focus on (optional)
        setup_test_data: Whether to create test CSV data
    """
    test_name = f"CodeRunner File Processing - {analysis_type.capitalize()}"
    print(f"\n--- Starting {test_name} ---")
    print(f"Data Source: {data_namespace}/{data_filename}")
    print(f"Analysis Type: {analysis_type}")
    print(f"Min Salary Filter: ${min_salary_filter:,}")
    if target_department:
        print(f"Target Department: {target_department}")
    
    # Prepare workflow inputs
    WORKFLOW_INPUTS = {
        "data_namespace": data_namespace,
        "data_filename": data_filename,
        "analysis_type": analysis_type,
        "min_salary_filter": min_salary_filter,
        "target_department": target_department
    }
    
    # Setup test CSV data if requested
    setup_docs: List[SetupDocInfo] = []
    cleanup_docs: List[CleanupDocInfo] = []
    
    if setup_test_data:
        # Create sample employee CSV data
        csv_data = """name,age,department,salary,years_experience
Alice,28,Engineering,85000,4
Bob,35,Marketing,65000,8
Charlie,42,Engineering,95000,12
Diana,31,Sales,70000,6
Eve,29,Engineering,80000,5
Frank,38,Marketing,72000,10
Grace,26,Engineering,78000,3
Henry,45,Sales,85000,15
Iris,33,Marketing,68000,7
Jack,40,Engineering,92000,11
Karen,29,Sales,69000,5
Leo,34,Engineering,87000,8
Maya,31,Marketing,71000,6
Noah,27,Engineering,82000,4
Olivia,36,Sales,76000,9"""
        
        setup_docs = [
            {
                'namespace': data_namespace,
                'docname': data_filename,
                'initial_data': {
                    "raw_content": csv_data.encode('utf-8'),
                    "source_filename": data_filename,
                    "content_type": "text/csv",
                    "description": "Sample employee data for analysis"
                },
                'is_versioned': False,
                'is_shared': False,
                'initial_version': None,
                'is_system_entity': False
            }
        ]
        
        # Define cleanup
        cleanup_docs = [
            {
                'namespace': data_namespace, 
                'docname': data_filename, 
                'is_versioned': False, 
                'is_shared': False, 
                'is_system_entity': False
            }
        ]
        
        logger.info(f"Setup: Creating test CSV with {len(csv_data.split(chr(10)))-1} employee records")
    
    # Execute the test
    final_run_status_obj, final_run_outputs = await run_workflow_test(
        test_name=test_name,
        workflow_graph_schema=workflow_graph_schema,
        initial_inputs=WORKFLOW_INPUTS,
        expected_final_status=WorkflowRunStatus.COMPLETED,
        hitl_inputs=None,  # No HITL needed for this test
        # setup_docs=setup_docs,
        # cleanup_docs=cleanup_docs,
        # cleanup_docs_created_by_setup=True,
        validate_output_func=partial(
            validate_file_processing_output,
            expected_inputs=WORKFLOW_INPUTS
        ),
        stream_intermediate_results=True,
        poll_interval_sec=3,
        timeout_sec=180  # Allow time for file processing
    )
    
    # Display detailed results
    if final_run_outputs:
        print(f"\n--- Processing Summary ---")
        print(f"Success: {final_run_outputs.get('processing_success', False)}")
        print(f"Processing Time: {final_run_outputs.get('processing_time', 0):.2f} seconds")
        
        if final_run_outputs.get('analysis_results'):
            results = final_run_outputs['analysis_results']
            print(f"\n--- Analysis Results ---")
            print(f"Total Employees: {results.get('total_employees', 0)}")
            print(f"Filtered Employees: {results.get('filtered_employees', 0)}")
            
            # Salary analysis
            if 'salary_analysis' in results:
                sal = results['salary_analysis']
                print(f"\n💰 Salary Analysis:")
                print(f"   Average: ${sal['average']:,.2f}")
                print(f"   Median: ${sal['median']:,.2f}")
                print(f"   Range: ${sal['min']:,} - ${sal['max']:,}")
                print(f"   Total Payroll: ${sal['total']:,}")
            
            # Department analysis
            if 'department_analysis' in results:
                dept = results['department_analysis']
                print(f"\n🏢 Department Analysis:")
                for dept_name, stats in dept.items():
                    print(f"   {dept_name}:")
                    print(f"     Employees: {stats['employee_count']}")
                    print(f"     Avg Salary: ${stats['avg_salary']:,.2f}")
                    print(f"     Total Budget: ${stats['total_salary']:,}")
            
            # Other analyses
            if 'age_analysis' in results:
                age = results['age_analysis']
                print(f"\n👤 Age Analysis:")
                print(f"   Average Age: {age['average']:.1f} years")
                print(f"   Age Range: {age['min']} - {age['max']} years")
            
            if 'experience_analysis' in results:
                exp = results['experience_analysis']
                print(f"\n🎓 Experience Analysis:")
                print(f"   Average Experience: {exp['average']:.1f} years")
                print(f"   Experience Range: {exp['min']} - {exp['max']} years")
        
        if final_run_outputs.get('input_files_info'):
            input_files = final_run_outputs['input_files_info']
            print(f"\n--- Input Files Loaded ({len(input_files)}) ---")
            for field_name, file_info in input_files.items():
                print(f"  📄 {file_info['filename']} ({file_info['size_bytes']} bytes)")
                print(f"      Field: {field_name}, Type: {file_info['content_type']}")
        
        if final_run_outputs.get('output_files'):
            output_files = final_run_outputs['output_files']
            print(f"\n--- Generated Files ({len(output_files)}) ---")
            for file_info in output_files:
                print(f"  📄 {file_info['filename']} ({file_info['size_bytes']} bytes)")
                print(f"      Namespace: {file_info['namespace']}")
                print(f"      Document: {file_info['docname']}")
                if file_info.get('is_shared'):
                    print(f"      🌐 Shared with team")
        
        if final_run_outputs.get('error_message'):
            print(f"\n--- Errors ---")
            print(f"Error: {final_run_outputs['error_message']}")
        
        # Show execution logs (abbreviated)
        if final_run_outputs.get('processing_logs'):
            logs = final_run_outputs['processing_logs']
            print(f"\n--- Processing Logs (Last 800 chars) ---")
            print(logs[-800:] if len(logs) > 800 else logs)
    
    print(f"\n--- {test_name} Finished ---")
    
    return final_run_status_obj, final_run_outputs


if __name__ == "__main__":
    print("="*60)
    print("CodeRunner File Processing Example")
    print("="*60)
    print("\nThis example demonstrates CSV file loading and processing with the CodeRunner node.")
    print("The workflow will:")
    print("1. Load a CSV file from customer data")
    print("2. Parse and analyze employee data")
    print("3. Perform salary, department, and demographic analysis")
    print("4. Generate multiple output files with results")
    print("5. Apply filtering and targeted analysis")
    
    # Configuration for different test scenarios
    test_scenarios = [
        {
            "name": "Comprehensive Analysis",
            "config": {
                "data_namespace": "uploaded_files",
                "data_filename": "test_data.csv",
                "analysis_type": "comprehensive",
                "min_salary_filter": 0,
                "target_department": None,
                "setup_test_data": False
            }
        },
        {
            "name": "High-Salary Engineering Focus",
            "config": {
                "data_namespace": "uploaded_files", 
                "data_filename": "test_data.csv",
                "analysis_type": "salary",
                "min_salary_filter": 80000,
                "target_department": "Engineering",
                "setup_test_data": False
            }
        },
        {
            "name": "Department Analysis Only",
            "config": {
                "data_namespace": "uploaded_files",
                "data_filename": "test_data.csv", 
                "analysis_type": "department",
                "min_salary_filter": 70000,
                "target_department": None,
                "setup_test_data": False
            }
        }
    ]
    
    # Choose which scenario to run
    selected_scenario = 0  # Change this to run different scenarios
    
    if selected_scenario < len(test_scenarios):
        scenario = test_scenarios[selected_scenario]
        print(f"\nRunning scenario: {scenario['name']}")
        print(f"Configuration: {json.dumps({k: v for k, v in scenario['config'].items() if k != 'setup_test_data'}, indent=2)}")
        
        # Handle async execution
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop and loop.is_running():
            print("\nAsync event loop already running. Adding task...")
            task = loop.create_task(main_test_file_processing(**scenario['config']))
        else:
            print("\nStarting new async event loop...")
            asyncio.run(main_test_file_processing(**scenario['config']))
    else:
        print(f"\nInvalid scenario selected: {selected_scenario}")
        print(f"Available scenarios (0-{len(test_scenarios)-1}):")
        for i, scenario in enumerate(test_scenarios):
            print(f"  {i}: {scenario['name']}")
    
    print("\n" + "-"*60)
    print("Run this script from the project root directory using:")
    print("PYTHONPATH=. python standalone_test_client/kiwi_client/workflows/examples/code_runner_egs/wf_code_runner_files_eg.py")
    print("-"*60)
