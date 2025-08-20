"""
Billing Analyzer Client for Workflow Runs

This client analyzes billing consumption for a workflow run and all its descendant runs,
providing detailed breakdowns by workflow name, event type, and model usage.
"""

import asyncio
import json
from typing import Dict, Any, List, Optional, Union, Tuple
from collections import defaultdict
from datetime import datetime, timedelta
import uuid
from pydantic import BaseModel
from pathlib import Path

from kiwi_client.auth_client import AuthenticatedClient
from kiwi_client.run_client import WorkflowRunTestClient
from kiwi_client.test_config import BILLING_DASHBOARD_USAGE_URL
import kiwi_client.schemas.workflow_api_schemas as wf_schemas

current_dir = Path(__file__).parent


class ModelUsageStats(BaseModel):
    """Statistics for model usage"""
    model_name: str
    total_credits: float
    event_count: int
    providers: List[str]


class EventTypeBreakdown(BaseModel):
    """Breakdown of credits by event type and subtype"""
    event_type: str
    subtype: Optional[str]
    total_credits: float
    event_count: int
    model_breakdown: Optional[Dict[str, ModelUsageStats]] = None


class WorkflowBillingBreakdown(BaseModel):
    """Billing breakdown for a specific workflow"""
    workflow_name: str
    run_count: int
    total_credits: float
    event_type_breakdown: List[EventTypeBreakdown]
    model_usage: Dict[str, ModelUsageStats]


class RunBillingAnalysis(BaseModel):
    """Complete billing analysis for a run and its descendants"""
    root_run_id: str
    root_workflow_name: Optional[str]
    analysis_timestamp: datetime
    total_runs_analyzed: int
    total_credits_consumed: float
    total_events: int
    
    # Breakdowns
    workflow_breakdown: Dict[str, WorkflowBillingBreakdown]
    event_type_breakdown: List[EventTypeBreakdown]
    overall_model_usage: Dict[str, ModelUsageStats]
    
    # Raw data
    run_hierarchy: Dict[str, Any]
    raw_events: Optional[List[Dict[str, Any]]] = None


class RunBillingAnalyzerClient:
    """
    Client for analyzing billing consumption for workflow runs.
    
    This client:
    1. Fetches a run and all its descendant runs
    2. Queries billing events for each run
    3. Aggregates and analyzes billing data
    4. Provides detailed breakdowns by workflow, event type, and model usage
    """
    
    def __init__(self, auth_client: AuthenticatedClient):
        """
        Initialize the billing analyzer client.
        
        Args:
            auth_client: Authenticated client for API access
        """
        self.auth_client = auth_client
        self.run_client = WorkflowRunTestClient(auth_client)
        
    async def get_run_hierarchy(self, run_id: Union[str, uuid.UUID], max_depth: int = 10) -> Dict[str, Any]:
        """
        Get the complete hierarchy of a run including all descendants.
        
        Args:
            run_id: The root run ID to analyze
            max_depth: Maximum depth to traverse (default 10) to prevent infinite loops
            
        Returns:
            Dictionary containing the run hierarchy with run details
        """
        run_id_str = str(run_id)
        hierarchy = {}
        processed_runs = set()  # Track processed runs to avoid cycles
        
        # Get the root run
        root_run = await self.run_client.get_run_status(run_id_str)
        if not root_run:
            raise ValueError(f"Run {run_id_str} not found")
        
        # Build hierarchy recursively with cycle detection
        await self._build_run_hierarchy(root_run, hierarchy, processed_runs, depth=0, max_depth=max_depth)
        
        return hierarchy
    
    async def _build_run_hierarchy(self, 
                                  run: wf_schemas.WorkflowRunRead, 
                                  hierarchy: Dict[str, Any],
                                  processed_runs: set,
                                  depth: int = 0,
                                  max_depth: int = 10) -> None:
        """
        Recursively build the run hierarchy with cycle detection.
        
        Args:
            run: The current run
            hierarchy: Dictionary to populate with run hierarchy
            processed_runs: Set of already processed run IDs to detect cycles
            depth: Current depth in the hierarchy
            max_depth: Maximum depth to traverse
        """
        run_id_str = str(run.id)
        
        # Check for cycles and depth limit
        if run_id_str in processed_runs:
            print(f"⚠️  Cycle detected: Run {run_id_str} already processed, skipping...")
            return
        
        if depth >= max_depth:
            print(f"⚠️  Maximum depth {max_depth} reached at run {run_id_str}, stopping traversal...")
            return
        
        # Mark this run as processed
        processed_runs.add(run_id_str)
        
        # Add current run to hierarchy
        hierarchy[run_id_str] = {
            "run_id": run_id_str,
            "workflow_name": run.workflow_name,
            "workflow_id": str(run.workflow_id) if run.workflow_id else None,
            "status": run.status.value if hasattr(run.status, 'value') else str(run.status),
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "parent_run_id": str(run.parent_run_id) if run.parent_run_id else None,
            "children": {},
            "depth": depth
        }
        
        # Get child runs using the parent_run_id filter with pagination
        try:
            all_children = []
            skip = 0
            limit = 100
            max_children = 1000  # Limit total children to prevent runaway queries
            
            while len(all_children) < max_children:
                children = await self.run_client.list_runs(
                    skip=skip,
                    limit=limit,
                    parent_run_id=run_id_str  # Use the new parent_run_id filter
                )
                
                if not children:
                    break
                    
                # Validate that returned runs are actually children of this run
                valid_children = []
                for child in children:
                    child_parent_id = str(child.parent_run_id) if child.parent_run_id else None
                    child_id = str(child.id)
                    
                    # Check if this is actually a child of the current run
                    if child_parent_id != run_id_str:
                        if depth == 0:  # Only warn at root level to avoid spam
                            if child_parent_id:
                                print(f"  {'  ' * depth}⚠️  WARNING: Run {child_id[:8]} has parent {child_parent_id[:8]}, not {run_id_str[:8]}. Skipping...")
                            else:
                                print(f"  {'  ' * depth}⚠️  WARNING: Run {child_id[:8]} has NULL parent_run_id, not {run_id_str[:8]}. Skipping...")
                        continue
                    
                    # Also skip if the child is the same as the parent (self-reference)
                    if child_id == run_id_str:
                        print(f"  {'  ' * depth}⚠️  WARNING: Run {child_id[:8]} references itself as parent! Skipping...")
                        continue
                        
                    valid_children.append(child)
                
                all_children.extend(valid_children)
                
                # If we got less than the limit, we've reached the end
                if len(children) < limit:
                    break
                    
                skip += limit
            
            # Process child runs
            if all_children:
                print(f"  {'  ' * depth}Found {len(all_children)} children for run {run_id_str[:8]}...")
                
                # If we have too many children, just process a subset and warn
                if len(all_children) >= max_children:
                    print(f"  {'  ' * depth}⚠️  Run has {max_children}+ children, processing first {max_children}...")
                
                for child in all_children:
                    # Only process if not already processed (cycle detection)
                    if str(child.id) not in processed_runs:
                        await self._build_run_hierarchy(
                            child, 
                            hierarchy[run_id_str]["children"], 
                            processed_runs,
                            depth=depth + 1,
                            max_depth=max_depth
                        )
                    else:
                        print(f"  {'  ' * depth}⚠️  Skipping already processed child: {str(child.id)[:8]}...")
        except Exception as e:
            print(f"  {'  ' * depth}❌ Error fetching children for {run_id_str[:8]}: {e}")
    
    async def get_billing_events_for_run(self, run_id: Union[str, uuid.UUID]) -> List[Dict[str, Any]]:
        """
        Get all billing events for a specific run.
        
        Args:
            run_id: The run ID to get billing events for
            
        Returns:
            List of billing events
        """
        run_id_str = str(run_id)
        all_events = []
        skip = 0
        limit = 2000
        
        while True:
            # Query billing events with run_id in metadata
            # Use the full URL to avoid base_url concatenation issues
            response = await self.auth_client.client.get(
                f"{BILLING_DASHBOARD_USAGE_URL}/events",
                params={
                    "metadata_search": run_id_str,
                    "skip": skip,
                    "limit": limit,
                    "sort_by": "created_at",
                    "sort_order": "desc"
                }
            )
            
            if response.status_code != 200:
                print(f"Error fetching billing events: {response.status_code} - {response.text}")
                break
            
            data = response.json()
            events = data.get("items", [])
            
            if not events:
                break
                
            all_events.extend(events)
            
            # Check if there are more events
            if len(events) < limit:
                break
                
            skip += limit
        
        return all_events
    
    async def analyze_run_billing(self, 
                                   run_id: Union[str, uuid.UUID],
                                   include_raw_events: bool = False,
                                   max_hierarchy_depth: int = 5) -> RunBillingAnalysis:
        """
        Analyze billing consumption for a run and all its descendants.
        
        Args:
            run_id: The root run ID to analyze
            include_raw_events: Whether to include raw events in the analysis
            max_hierarchy_depth: Maximum depth to traverse in run hierarchy (default 5)
            
        Returns:
            Complete billing analysis
        """
        run_id_str = str(run_id)
        
        # Get run hierarchy with limited depth to prevent infinite loops
        print(f"📊 Building run hierarchy (max depth: {max_hierarchy_depth})...")
        hierarchy = await self.get_run_hierarchy(run_id_str, max_depth=max_hierarchy_depth)
        
        # Collect all run IDs (including descendants)
        all_run_ids = self._extract_all_run_ids(hierarchy)
        
        # Get billing events for all runs
        print(f"📋 Fetching billing events for {len(all_run_ids)} run(s)...")
        all_events = []
        for i, rid in enumerate(all_run_ids, 1):
            print(f"  [{i}/{len(all_run_ids)}] Fetching events for run {rid[:8]}...")
            events = await self.get_billing_events_for_run(rid)
            if events:
                print(f"    Found {len(events)} events")
            all_events.extend(events)
        
        print(f"✅ Total billing events collected: {len(all_events)}")
        
        # Analyze the events
        analysis = self._analyze_billing_events(
            all_events, 
            hierarchy,
            run_id_str,
            include_raw_events
        )
        
        return analysis
    
    def _extract_all_run_ids(self, hierarchy: Dict[str, Any]) -> List[str]:
        """
        Extract all run IDs from the hierarchy.
        
        Args:
            hierarchy: Run hierarchy dictionary
            
        Returns:
            List of all run IDs
        """
        run_ids = []
        
        def extract_recursive(node: Dict[str, Any]):
            if isinstance(node, dict):
                if "run_id" in node:
                    run_ids.append(node["run_id"])
                if "children" in node:
                    for child in node["children"].values():
                        extract_recursive(child)
                else:
                    # Top level hierarchy
                    for run_data in node.values():
                        extract_recursive(run_data)
        
        extract_recursive(hierarchy)
        return run_ids
    
    def _analyze_billing_events(self, 
                                events: List[Dict[str, Any]], 
                                hierarchy: Dict[str, Any],
                                root_run_id: str,
                                include_raw_events: bool) -> RunBillingAnalysis:
        """
        Analyze billing events and create breakdown.
        
        Args:
            events: List of billing events
            hierarchy: Run hierarchy
            root_run_id: Root run ID
            include_raw_events: Whether to include raw events
            
        Returns:
            Billing analysis
        """
        # Initialize aggregation structures
        workflow_breakdown = defaultdict(lambda: {
            "total_credits": 0.0,
            "run_ids": set(),
            "events_by_type": defaultdict(lambda: {
                "total_credits": 0.0,
                "event_count": 0,
                "subtypes": defaultdict(lambda: {"total_credits": 0.0, "event_count": 0}),
                "models": defaultdict(lambda: {"total_credits": 0.0, "event_count": 0, "providers": set()})
            }),
            "model_usage": defaultdict(lambda: {"total_credits": 0.0, "event_count": 0, "providers": set()})
        })
        
        overall_event_breakdown = defaultdict(lambda: {
            "total_credits": 0.0,
            "event_count": 0,
            "subtypes": defaultdict(lambda: {"total_credits": 0.0, "event_count": 0}),
            "models": defaultdict(lambda: {"total_credits": 0.0, "event_count": 0, "providers": set()})
        })
        
        overall_model_usage = defaultdict(lambda: {"total_credits": 0.0, "event_count": 0, "providers": set()})
        
        total_credits = 0.0
        total_events = len(events)
        
        # Map run IDs to workflow names from hierarchy
        run_to_workflow = {}
        def map_runs_to_workflows(node: Dict[str, Any]):
            if isinstance(node, dict):
                if "run_id" in node and "workflow_name" in node:
                    run_to_workflow[node["run_id"]] = node["workflow_name"] or "unknown"
                if "children" in node:
                    for child in node["children"].values():
                        map_runs_to_workflows(child)
                else:
                    # Top level hierarchy
                    for run_data in node.values():
                        map_runs_to_workflows(run_data)
        
        map_runs_to_workflows(hierarchy)
        
        # Process each event
        for event in events:
            credits = event.get("credits_consumed", 0.0)
            event_type = event.get("event_type", "unknown")
            
            # Remove __dollar_credit_fallback_for suffix if present
            # This suffix is used internally for billing fallback mechanisms and should be 
            # ignored for user-facing billing analysis
            if "__dollar_credit_fallback_for" in event_type:
                event_type = event_type.split("__dollar_credit_fallback_for")[0]
            
            metadata = event.get("usage_metadata", {})
            
            # Extract run_id from metadata (might be in different fields)
            event_run_id = None
            if metadata:
                # Check various possible fields for run_id
                event_run_id = (metadata.get("run_id") or 
                               metadata.get("workflow_run_id") or
                               metadata.get("operation_id"))
            
            # Determine workflow name
            workflow_name = "unknown"
            if event_run_id and event_run_id in run_to_workflow:
                workflow_name = run_to_workflow[event_run_id]
            
            # Extract subtype if exists (split by __)
            subtype = None
            base_event_type = event_type
            if "__" in event_type:
                parts = event_type.split("__", 1)
                base_event_type = parts[0]
                subtype = parts[1]
            
            # Extract model information for specific event types
            model_name = None
            provider = None
            if (event_type.startswith("llm_token_usage") or event_type == "web_search"):
                model_name = metadata.get("model_name")
                provider = metadata.get("provider")
            
            # Update totals
            total_credits += credits
            
            # Update workflow breakdown
            wb = workflow_breakdown[workflow_name]
            wb["total_credits"] += credits
            if event_run_id:
                wb["run_ids"].add(event_run_id)
            
            # Update event type breakdown for workflow
            event_data = wb["events_by_type"][base_event_type]
            event_data["total_credits"] += credits
            event_data["event_count"] += 1
            
            if subtype:
                event_data["subtypes"][subtype]["total_credits"] += credits
                event_data["subtypes"][subtype]["event_count"] += 1
            
            if model_name:
                model_data = event_data["models"][model_name]
                model_data["total_credits"] += credits
                model_data["event_count"] += 1
                if provider:
                    model_data["providers"].add(provider)
                
                # Update workflow model usage
                wm = wb["model_usage"][model_name]
                wm["total_credits"] += credits
                wm["event_count"] += 1
                if provider:
                    wm["providers"].add(provider)
            
            # Update overall event breakdown
            overall_event = overall_event_breakdown[base_event_type]
            overall_event["total_credits"] += credits
            overall_event["event_count"] += 1
            
            if subtype:
                overall_event["subtypes"][subtype]["total_credits"] += credits
                overall_event["subtypes"][subtype]["event_count"] += 1
            
            if model_name:
                model_data = overall_event["models"][model_name]
                model_data["total_credits"] += credits
                model_data["event_count"] += 1
                if provider:
                    model_data["providers"].add(provider)
                
                # Update overall model usage
                om = overall_model_usage[model_name]
                om["total_credits"] += credits
                om["event_count"] += 1
                if provider:
                    om["providers"].add(provider)
        
        # Convert to final format
        workflow_breakdown_final = {}
        for workflow_name, wb in workflow_breakdown.items():
            event_type_breakdown = []
            for event_type, event_data in wb["events_by_type"].items():
                # Build model breakdown for this event type
                model_breakdown = None
                if event_data["models"]:
                    model_breakdown = {}
                    for model_name, model_data in event_data["models"].items():
                        model_breakdown[model_name] = ModelUsageStats(
                            model_name=model_name,
                            total_credits=model_data["total_credits"],
                            event_count=model_data["event_count"],
                            providers=list(model_data["providers"])
                        )
                
                # Add main event type
                event_type_breakdown.append(EventTypeBreakdown(
                    event_type=event_type,
                    subtype=None,
                    total_credits=event_data["total_credits"],
                    event_count=event_data["event_count"],
                    model_breakdown=model_breakdown
                ))
                
                # Add subtypes
                for subtype, subtype_data in event_data["subtypes"].items():
                    event_type_breakdown.append(EventTypeBreakdown(
                        event_type=f"{event_type}__{subtype}",
                        subtype=subtype,
                        total_credits=subtype_data["total_credits"],
                        event_count=subtype_data["event_count"],
                        model_breakdown=None  # Model breakdown only at main type level
                    ))
            
            # Build model usage for workflow
            model_usage = {}
            for model_name, model_data in wb["model_usage"].items():
                model_usage[model_name] = ModelUsageStats(
                    model_name=model_name,
                    total_credits=model_data["total_credits"],
                    event_count=model_data["event_count"],
                    providers=list(model_data["providers"])
                )
            
            workflow_breakdown_final[workflow_name] = WorkflowBillingBreakdown(
                workflow_name=workflow_name,
                run_count=len(wb["run_ids"]),
                total_credits=wb["total_credits"],
                event_type_breakdown=event_type_breakdown,
                model_usage=model_usage
            )
        
        # Convert overall event breakdown
        overall_event_breakdown_final = []
        for event_type, event_data in overall_event_breakdown.items():
            # Build model breakdown
            model_breakdown = None
            if event_data["models"]:
                model_breakdown = {}
                for model_name, model_data in event_data["models"].items():
                    model_breakdown[model_name] = ModelUsageStats(
                        model_name=model_name,
                        total_credits=model_data["total_credits"],
                        event_count=model_data["event_count"],
                        providers=list(model_data["providers"])
                    )
            
            # Add main event type
            overall_event_breakdown_final.append(EventTypeBreakdown(
                event_type=event_type,
                subtype=None,
                total_credits=event_data["total_credits"],
                event_count=event_data["event_count"],
                model_breakdown=model_breakdown
            ))
            
            # Add subtypes
            for subtype, subtype_data in event_data["subtypes"].items():
                overall_event_breakdown_final.append(EventTypeBreakdown(
                    event_type=f"{event_type}__{subtype}",
                    subtype=subtype,
                    total_credits=subtype_data["total_credits"],
                    event_count=subtype_data["event_count"],
                    model_breakdown=None
                ))
        
        # Convert overall model usage
        overall_model_usage_final = {}
        for model_name, model_data in overall_model_usage.items():
            overall_model_usage_final[model_name] = ModelUsageStats(
                model_name=model_name,
                total_credits=model_data["total_credits"],
                event_count=model_data["event_count"],
                providers=list(model_data["providers"])
            )
        
        # Get root workflow name
        root_workflow_name = None
        if root_run_id in hierarchy:
            root_workflow_name = hierarchy[root_run_id].get("workflow_name")
        
        return RunBillingAnalysis(
            root_run_id=root_run_id,
            root_workflow_name=root_workflow_name,
            analysis_timestamp=datetime.utcnow(),
            total_runs_analyzed=len(run_to_workflow),
            total_credits_consumed=total_credits,
            total_events=total_events,
            workflow_breakdown=workflow_breakdown_final,
            event_type_breakdown=overall_event_breakdown_final,
            overall_model_usage=overall_model_usage_final,
            run_hierarchy=hierarchy,
            raw_events=events if include_raw_events else None
        )
    
    def format_analysis_as_markdown(self, analysis: RunBillingAnalysis) -> str:
        """
        Format the billing analysis as markdown for easy reading.
        
        Args:
            analysis: The billing analysis to format
            
        Returns:
            Markdown formatted string
        """
        md_lines = []
        
        # Header
        md_lines.append("# Workflow Run Billing Analysis")
        md_lines.append("")
        md_lines.append(f"**Analysis Date:** {analysis.analysis_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        md_lines.append(f"**Root Run ID:** `{analysis.root_run_id}`")
        if analysis.root_workflow_name:
            md_lines.append(f"**Root Workflow:** {analysis.root_workflow_name}")
        md_lines.append("")
        
        # Summary Statistics
        md_lines.append("## Summary Statistics")
        md_lines.append("")
        md_lines.append(f"- **Total Runs Analyzed:** {analysis.total_runs_analyzed}")
        md_lines.append(f"- **Total Events:** {analysis.total_events}")
        md_lines.append(f"- **Total Credits Consumed:** ${analysis.total_credits_consumed:.6f}")
        md_lines.append("")
        
        # Overall Model Usage
        if analysis.overall_model_usage:
            md_lines.append("## Overall Model Usage")
            md_lines.append("")
            md_lines.append("| Model | Credits | Events | Providers |")
            md_lines.append("|-------|---------|--------|-----------|")
            
            for model_name, stats in sorted(analysis.overall_model_usage.items(), 
                                           key=lambda x: x[1].total_credits, 
                                           reverse=True):
                providers = ", ".join(stats.providers) if stats.providers else "N/A"
                md_lines.append(f"| {model_name} | ${stats.total_credits:.6f} | {stats.event_count} | {providers} |")
            md_lines.append("")
        
        # Workflow Breakdown
        if analysis.workflow_breakdown:
            md_lines.append("## Breakdown by Workflow")
            md_lines.append("")
            
            for workflow_name, breakdown in sorted(analysis.workflow_breakdown.items(), 
                                                  key=lambda x: x[1].total_credits, 
                                                  reverse=True):
                md_lines.append(f"### {workflow_name}")
                md_lines.append("")
                md_lines.append(f"- **Runs:** {breakdown.run_count}")
                md_lines.append(f"- **Total Credits:** ${breakdown.total_credits:.6f}")
                md_lines.append("")
                
                # Model usage for this workflow
                if breakdown.model_usage:
                    md_lines.append("**Model Usage:**")
                    md_lines.append("")
                    md_lines.append("| Model | Credits | Events |")
                    md_lines.append("|-------|---------|--------|")
                    
                    for model_name, stats in sorted(breakdown.model_usage.items(), 
                                                   key=lambda x: x[1].total_credits, 
                                                   reverse=True):
                        md_lines.append(f"| {model_name} | ${stats.total_credits:.6f} | {stats.event_count} |")
                    md_lines.append("")
                
                # Event type breakdown for this workflow
                if breakdown.event_type_breakdown:
                    md_lines.append("**Event Types:**")
                    md_lines.append("")
                    md_lines.append("| Event Type | Credits | Count |")
                    md_lines.append("|------------|---------|-------|")
                    
                    for event in sorted(breakdown.event_type_breakdown, 
                                      key=lambda x: x.total_credits, 
                                      reverse=True):
                        if event.subtype:
                            md_lines.append(f"| └─ {event.subtype} | ${event.total_credits:.6f} | {event.event_count} |")
                        else:
                            md_lines.append(f"| **{event.event_type}** | ${event.total_credits:.6f} | {event.event_count} |")
                    md_lines.append("")
        
        # Overall Event Type Breakdown
        md_lines.append("## Overall Event Type Breakdown")
        md_lines.append("")
        md_lines.append("| Event Type | Credits | Count |")
        md_lines.append("|------------|---------|-------|")
        
        for event in sorted(analysis.event_type_breakdown, 
                          key=lambda x: x.total_credits, 
                          reverse=True):
            if event.subtype:
                md_lines.append(f"| └─ {event.event_type} | ${event.total_credits:.6f} | {event.event_count} |")
            else:
                md_lines.append(f"| **{event.event_type}** | ${event.total_credits:.6f} | {event.event_count} |")
                
                # Show model breakdown for llm_token_usage and web_search
                if event.model_breakdown:
                    for model_name, stats in sorted(event.model_breakdown.items(), 
                                                   key=lambda x: x[1].total_credits, 
                                                   reverse=True):
                        md_lines.append(f"|   • {model_name} | ${stats.total_credits:.6f} | {stats.event_count} |")
        md_lines.append("")
        
        # Run Hierarchy
        md_lines.append("## Run Hierarchy")
        md_lines.append("")
        md_lines.append("```")
        
        def format_hierarchy(node: Dict[str, Any], indent: int = 0):
            if isinstance(node, dict):
                if "run_id" in node:
                    prefix = "  " * indent + ("└─ " if indent > 0 else "")
                    workflow = node.get("workflow_name", "unknown")
                    status = node.get("status", "unknown")
                    md_lines.append(f"{prefix}{workflow} ({node['run_id'][:8]}...) [{status}]")
                    
                    if "children" in node and node["children"]:
                        for child in node["children"].values():
                            format_hierarchy(child, indent + 1)
                else:
                    # Top level
                    for run_data in node.values():
                        format_hierarchy(run_data, indent)
        
        format_hierarchy(analysis.run_hierarchy)
        md_lines.append("```")
        md_lines.append("")
        
        return "\n".join(md_lines)
    
    def format_analysis_as_json(self, analysis: RunBillingAnalysis) -> str:
        """
        Format the billing analysis as pretty-printed JSON.
        
        Args:
            analysis: The billing analysis to format
            
        Returns:
            JSON formatted string
        """
        # Convert Pydantic models to dictionaries
        analysis_dict = analysis.model_dump(exclude={"raw_events"} if not analysis.raw_events else set())
        
        # Convert datetime to string
        if "analysis_timestamp" in analysis_dict:
            analysis_dict["analysis_timestamp"] = analysis_dict["analysis_timestamp"].isoformat()
        
        return json.dumps(analysis_dict, indent=2, default=str)
    
    async def analyze_and_save(self, 
                              run_id: Union[str, uuid.UUID],
                              output_dir: str = current_dir.as_posix(),
                              include_raw_events: bool = False,
                              max_hierarchy_depth: int = 5) -> Tuple[RunBillingAnalysis, str, str]:
        """
        Analyze run billing and save results to files.
        
        Args:
            run_id: The run ID to analyze
            output_dir: Directory to save analysis files
            include_raw_events: Whether to include raw events in JSON output
            max_hierarchy_depth: Maximum depth to traverse in run hierarchy (default 5)
            
        Returns:
            Tuple of (analysis, markdown_path, json_path)
        """
        import os
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Perform analysis
        analysis = await self.analyze_run_billing(run_id, include_raw_events, max_hierarchy_depth)
        
        # Generate filenames with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        run_id_short = str(run_id)[:8]
        
        markdown_filename = f"billing_analysis_{run_id_short}_{timestamp}.md"
        json_filename = f"billing_analysis_{run_id_short}_{timestamp}.json"
        
        markdown_path = os.path.join(output_dir, markdown_filename)
        json_path = os.path.join(output_dir, json_filename)
        
        # Save markdown
        markdown_content = self.format_analysis_as_markdown(analysis)
        with open(markdown_path, "w") as f:
            f.write(markdown_content)
        
        # Save JSON
        json_content = self.format_analysis_as_json(analysis)
        with open(json_path, "w") as f:
            f.write(json_content)
        
        print(f"\n✅ Billing analysis completed!")
        print(f"📄 Markdown report: {markdown_path}")
        print(f"📊 JSON data: {json_path}")
        print(f"\n💰 Total Credits Consumed: ${analysis.total_credits_consumed:.6f}")
        print(f"📈 Total Runs Analyzed: {analysis.total_runs_analyzed}")
        print(f"📋 Total Events: {analysis.total_events}")
        
        return analysis, markdown_path, json_path


async def main():
    """Example usage of the billing analyzer client."""
    
    # Initialize authenticated client
    auth_client = AuthenticatedClient()
    
    try:
        # Login
        await auth_client.login()
        print("✅ Logged in successfully")
        
        # Create billing analyzer
        analyzer = RunBillingAnalyzerClient(auth_client)
        
        # Example: Analyze a specific run
        # Replace with an actual run ID
        run_id = input("\nEnter the run ID to analyze: ").strip()
        
        if run_id:
            # Ask for max depth
            depth_input = input("Enter max hierarchy depth (default 3, max 10): ").strip()
            try:
                max_depth = int(depth_input) if depth_input else 3
                max_depth = min(max(max_depth, 1), 10)  # Clamp between 1 and 10
            except ValueError:
                max_depth = 3
                print(f"Invalid depth input, using default: {max_depth}")
            
            print(f"\n🔍 Analyzing billing for run: {run_id}")
            print(f"📊 Max hierarchy depth: {max_depth}")
            
            # Perform analysis and save results
            analysis, md_path, json_path = await analyzer.analyze_and_save(
                run_id=run_id,
                output_dir="billing_analysis",
                include_raw_events=False,  # Set to True to include raw events in JSON
                max_hierarchy_depth=max_depth
            )
            
            # Print summary to console
            print("\n" + "="*60)
            print("BILLING ANALYSIS SUMMARY")
            print("="*60)
            
            # Print markdown to console for immediate viewing
            print(analyzer.format_analysis_as_markdown(analysis))
            
        else:
            print("No run ID provided. Exiting.")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await auth_client.close()


if __name__ == "__main__":
    asyncio.run(main())
