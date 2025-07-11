#!/usr/bin/env python3
"""
Script to ingest all workflows at once using the WorkflowIngestionClient.

This script will:
1. Authenticate with the workflow service
2. Ingest all workflows defined in the configuration
3. Print results for each workflow
4. Provide a summary of the ingestion process

Run with: PYTHONPATH=. python scripts/ingest_all_workflows.py
"""

import asyncio
import sys
import logging
from typing import List, Dict, Any, Tuple, Optional
import uuid

# Add the parent directory to the path to import kiwi_client
sys.path.insert(0, '.')

from kiwi_client.auth_client import AuthenticatedClient, AuthenticationError
from scripts.workflow_ingestion_client import WorkflowIngestionClient, WorkflowIngestionConfig

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('workflow_ingestion.log')
    ]
)
logger = logging.getLogger(__name__)

# Configuration for all workflows to ingest
WORKFLOW_CONFIGS: List[WorkflowIngestionConfig] = [
    {
        "workflow_key": "linkedin_scraping_workflow",
        "module_path": "kiwi_client.workflows.wf_linkedin_scraping"
    },
    {
        "workflow_key": "automatic_concept_selection_workflow",
        "module_path": "kiwi_client.workflows.wf_automatic_concept_selection_workflow"
    },
    {
        "workflow_key": "sources_extraction_workflow",
        "module_path": "kiwi_client.workflows.wf_sources_extraction_workflow"
    },
    {
        "workflow_key": "knowledge_base_analysis_workflow",
        "module_path": "kiwi_client.workflows.wf_knowledge_base_analysis_workflow"
    },
    {
        "workflow_key": "content_strategy_workflow",
        "module_path": "kiwi_client.workflows.wf_content_strategy_workflow"
    },
    {
        "workflow_key": "user_dna_workflow",
        "module_path": "kiwi_client.workflows.wf_user_dna_workflow"
    },
    {
        "workflow_key": "content_calendar_entry_workflow",
        "module_path": "kiwi_client.workflows.wf_content_calendar_entry"
    },
    {
        "workflow_key": "content_creation_workflow",
        "module_path": "kiwi_client.workflows.wf_content_creation_workflow"
    },
    {
        "workflow_key": "initial_brief_to_concepts_workflow",
        "module_path": "kiwi_client.workflows.wf_initial_brief_to_concepts_workflow"
    },
    {
        "workflow_key": "idea_generation_workflow",
        "module_path": "kiwi_client.workflows.wf_idea_generation_workflow"
    },
    {
        "workflow_key": "idea_brainstorm_workflow",
        "module_path": "kiwi_client.workflows.wf_idea_brainstorm_workflow"
    },
    {
        "workflow_key": "concept_brainstorm_workflow",
        "module_path": "kiwi_client.workflows.wf_concept_brainstorm_from_scratch"
    },
    {
        "workflow_key": "alternate_text_suggestion_workflow",
        "module_path": "kiwi_client.workflows.wf_alternate_text_suggestion_workflow"
    },
    {
        "workflow_key": "post_editing_workflow",
        "module_path": "kiwi_client.workflows.wf_post_editing_workflow"
    },
    {
        "workflow_key": "linkedin_profile_analysis_onboarding_workflow",
        "module_path": "kiwi_client.workflows.wf_linkedin_profile_analysis_onboarding_workflow"
    },
    {
        "workflow_key": "core_beliefs_perspectives_extraction_workflow",
        "module_path": "kiwi_client.workflows.wf_core_beliefs_perspectives_extraction_workflow"
    },
    {
        "workflow_key": "style_test_workflow",
        "module_path": "kiwi_client.workflows.wf_style_test_workflow"
    },
    {
        "workflow_key": "post_creation_from_scratch_workflow",
        "module_path": "kiwi_client.workflows.wf_post_brainstorm_from_scratch"
    },
    {
        "workflow_key": "linkedin_content_analysis_workflow",
        "module_path": "kiwi_client.workflows.wf_linkedin_content_analysis"
    }
]


def print_banner():
    """Print a banner for the script."""
    print("=" * 80)
    print("                    WORKFLOW INGESTION SCRIPT")
    print("=" * 80)
    print(f"Total workflows to ingest: {len(WORKFLOW_CONFIGS)}")
    print("=" * 80)


def print_workflow_summary(workflow_configs: List[WorkflowIngestionConfig]):
    """Print a summary of workflows to be ingested."""
    print("\nWorkflows to be ingested:")
    print("-" * 60)
    for i, config in enumerate(workflow_configs, 1):
        print(f"{i:2d}. {config['workflow_key']}")
        print(f"     Module: {config['module_path']}")
    print("-" * 60)


def print_results_summary(results: Dict[str, Tuple[Optional[uuid.UUID], bool]]):
    """Print a summary of ingestion results."""
    print("\n" + "=" * 80)
    print("                    INGESTION RESULTS SUMMARY")
    print("=" * 80)
    
    successful_ingestions = []
    failed_ingestions = []
    
    for workflow_key, (workflow_id, test_success) in results.items():
        if workflow_id:
            successful_ingestions.append((workflow_key, workflow_id, test_success))
        else:
            failed_ingestions.append(workflow_key)
    
    print(f"Total workflows processed: {len(results)}")
    print(f"Successful ingestions: {len(successful_ingestions)}")
    print(f"Failed ingestions: {len(failed_ingestions)}")
    
    if successful_ingestions:
        print("\n✅ SUCCESSFUL INGESTIONS:")
        print("-" * 60)
        for workflow_key, workflow_id, test_success in successful_ingestions:
            test_status = "✅ Test Passed" if test_success else "⚠️  Test Not Run"
            print(f"  • {workflow_key}")
            print(f"    ID: {workflow_id}")
            print(f"    Status: {test_status}")
    
    if failed_ingestions:
        print("\n❌ FAILED INGESTIONS:")
        print("-" * 60)
        for workflow_key in failed_ingestions:
            print(f"  • {workflow_key}")
    
    print("=" * 80)


async def main():
    """Main function to run the workflow ingestion process."""
    print_banner()
    print_workflow_summary(WORKFLOW_CONFIGS)
    
    try:
        print("\n🔐 Initializing authentication client...")
        async with AuthenticatedClient() as auth_client:
            print("✅ Authentication successful!")
            
            print("\n🔧 Initializing workflow ingestion client...")
            ingestion_client = WorkflowIngestionClient(auth_client)
            print("✅ Workflow ingestion client initialized!")
            
            print("\n🚀 Starting workflow ingestion process...")
            print("This may take several minutes depending on the number of workflows...")
            
            # Ingest all workflows
            results = await ingestion_client.ingest_workflows(WORKFLOW_CONFIGS)
            
            # Print detailed results
            print("\n📊 DETAILED RESULTS:")
            print("-" * 60)
            for workflow_key, (workflow_id, test_success) in results.items():
                status = "✅ SUCCESS" if workflow_id else "❌ FAILED"
                test_result = "✅ Test Passed" if test_success else "⚠️  Test Failed/Not Run"
                print(f"{status} {workflow_key}")
                if workflow_id:
                    print(f"         ID: {workflow_id}")
                    print(f"         Test: {test_result}")
                print()
            
            # Print summary
            print_results_summary(results)
            
            # Save results to file
            import json
            results_for_json = {
                k: {
                    "workflow_id": str(v[0]) if v[0] else None,
                    "test_success": v[1],
                    "status": "success" if v[0] else "failed"
                }
                for k, v in results.items()
            }
            
            with open('workflow_ingestion_results.json', 'w') as f:
                json.dump(results_for_json, f, indent=2)
            
            print(f"\n💾 Results saved to 'workflow_ingestion_results.json'")
            print(f"📋 Logs saved to 'workflow_ingestion.log'")
            
    except AuthenticationError as e:
        logger.error(f"Authentication Error: {e}")
        print(f"\n❌ Authentication Error: {e}")
        print("Please check your credentials and try again.")
        sys.exit(1)
        
    except Exception as e:
        logger.exception(f"Unexpected error during workflow ingestion: {e}")
        print(f"\n❌ Unexpected error: {e}")
        print("Check the logs for more details.")
        sys.exit(1)
    
    print("\n🎉 Workflow ingestion process completed!")
    print("Check the summary above for results.")


if __name__ == "__main__":
    print("Starting workflow ingestion script...")
    print("Make sure to run with: PYTHONPATH=. python scripts/ingest_all_workflows.py")
    print()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Script interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        sys.exit(1)
