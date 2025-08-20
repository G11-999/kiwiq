#!/usr/bin/env python3
"""
Test script for the Billing Analyzer Client.

This script demonstrates how to use the RunBillingAnalyzerClient to analyze
billing consumption for workflow runs.
"""

import asyncio
import sys
from datetime import datetime
from kiwi_client.auth_client import AuthenticatedClient
from kiwi_client.run_client import WorkflowRunTestClient
from kiwi_client.analysis.run_billing_analyzer_client import RunBillingAnalyzerClient


async def test_billing_analyzer():
    """Test the billing analyzer with various scenarios."""
    
    auth_client = AuthenticatedClient()
    
    try:
        # Login
        print("🔐 Logging in...")
        await auth_client.login()
        print("✅ Login successful")
        
        # Initialize clients
        run_client = WorkflowRunTestClient(auth_client)
        analyzer = RunBillingAnalyzerClient(auth_client)
        
        # Option 1: Analyze a specific run ID provided as command line argument
        if len(sys.argv) > 1:
            run_id = sys.argv[1]
            print(f"\n📊 Analyzing billing for run ID: {run_id}")
            
            # Perform analysis with reasonable depth limit
            analysis = await analyzer.analyze_run_billing(run_id, include_raw_events=False, max_hierarchy_depth=3)
            
            # Print results
            print("\n" + "="*80)
            print(analyzer.format_analysis_as_markdown(analysis))
            
            # Save to files
            analysis, md_path, json_path = await analyzer.analyze_and_save(
                run_id=run_id,
                # output_dir="billing_analysis_test",
                max_hierarchy_depth=3
            )
            
            print(f"\n📁 Results saved to:")
            print(f"   - {md_path}")
            print(f"   - {json_path}")
            
        # Option 2: List recent runs and let user choose
        else:
            print("\n📋 Fetching recent workflow runs...")
            runs = await run_client.list_runs(limit=10)
            
            if not runs:
                print("No runs found.")
                return
            
            print("\nRecent runs:")
            print("-" * 80)
            for i, run in enumerate(runs, 1):
                status_emoji = "✅" if run.status.value == "completed" else "⏳"
                created = run.created_at.strftime("%Y-%m-%d %H:%M") if run.created_at else "N/A"
                parent = f" (child of {str(run.parent_run_id)[:8]}...)" if run.parent_run_id else ""
                
                print(f"{i}. {status_emoji} {run.workflow_name or 'Unknown'}")
                print(f"   ID: {run.id}")
                print(f"   Status: {run.status.value if hasattr(run.status, 'value') else run.status}")
                print(f"   Created: {created}{parent}")
                print()
            
            # Get user selection
            try:
                selection = input("Enter the number of the run to analyze (or 'q' to quit): ").strip()
                
                if selection.lower() == 'q':
                    print("Exiting.")
                    return
                
                index = int(selection) - 1
                if 0 <= index < len(runs):
                    selected_run = runs[index]
                    
                    print(f"\n🔍 Analyzing run: {selected_run.id}")
                    print(f"   Workflow: {selected_run.workflow_name or 'Unknown'}")
                    
                    # Check if this run has children
                    print("\n🌳 Checking for child runs...")
                    children = await run_client.list_runs(
                        limit=100,
                        # Use the parent_run_id filter we just added!
                        workflow_name=None,  # We need to pass parent_run_id through the API
                    )
                    
                    # Filter children manually for now since we need to update the client
                    child_count = sum(1 for r in children if r.parent_run_id and str(r.parent_run_id) == str(selected_run.id))
                    
                    if child_count > 0:
                        print(f"   Found {child_count} child run(s)")
                    else:
                        print("   No child runs found")
                    
                    # Perform analysis
                    print("\n💰 Analyzing billing consumption...")
                    analysis = await analyzer.analyze_run_billing(selected_run.id, max_hierarchy_depth=3)
                    
                    # Print summary
                    print("\n" + "="*80)
                    print("BILLING ANALYSIS RESULTS")
                    print("="*80)
                    print(f"Total Credits: ${analysis.total_credits_consumed:.6f}")
                    print(f"Total Events: {analysis.total_events}")
                    print(f"Runs Analyzed: {analysis.total_runs_analyzed}")
                    
                    if analysis.overall_model_usage:
                        print("\n🤖 Model Usage:")
                        for model_name, stats in sorted(
                            analysis.overall_model_usage.items(),
                            key=lambda x: x[1].total_credits,
                            reverse=True
                        ):
                            print(f"   - {model_name}: ${stats.total_credits:.6f} ({stats.event_count} events)")
                    
                    # Save full analysis
                    _, md_path, json_path = await analyzer.analyze_and_save(
                        run_id=selected_run.id,
                        # output_dir="billing_analysis_test",
                        max_hierarchy_depth=3
                    )
                    
                    print(f"\n📁 Full analysis saved to:")
                    print(f"   - {md_path}")
                    print(f"   - {json_path}")
                    
                    # Ask if user wants to see full markdown
                    show_full = input("\nShow full markdown report? (y/n): ").strip().lower()
                    if show_full == 'y':
                        print("\n" + "="*80)
                        print(analyzer.format_analysis_as_markdown(analysis))
                    
                else:
                    print("Invalid selection.")
                    
            except ValueError:
                print("Invalid input. Please enter a number.")
            except Exception as e:
                print(f"Error during analysis: {e}")
                import traceback
                traceback.print_exc()
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await auth_client.close()
        print("\n👋 Goodbye!")


async def test_parent_run_filter():
    """Test the newly added parent_run_id filter."""
    
    auth_client = AuthenticatedClient()
    
    try:
        await auth_client.login()
        print("✅ Logged in")
        
        run_client = WorkflowRunTestClient(auth_client)
        
        # Get recent runs
        runs = await run_client.list_runs(limit=20)
        
        # Find a run with parent_run_id
        parent_runs = [r for r in runs if r.parent_run_id is None]
        
        if parent_runs:
            parent_run = parent_runs[0]
            print(f"\n🔍 Testing parent_run_id filter with parent: {parent_run.id}")
            
            # Now test the filter by making a direct API call with parent_run_id
            response = await auth_client.client.get(
                "/api/workflows/runs",
                params={
                    "parent_run_id": str(parent_run.id),
                    "limit": 100
                }
            )
            
            if response.status_code == 200:
                children = response.json()
                print(f"✅ Found {len(children)} child runs")
                for child in children[:5]:  # Show first 5
                    print(f"   - {child['id']}: {child.get('workflow_name', 'Unknown')}")
            else:
                print(f"❌ Error: {response.status_code} - {response.text}")
        else:
            print("No parent runs found to test with")
    
    finally:
        await auth_client.close()


if __name__ == "__main__":
    # Run the main test
    asyncio.run(test_billing_analyzer())
    
    # Optionally test the parent_run_id filter
    # asyncio.run(test_parent_run_filter())
