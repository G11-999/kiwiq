"""
Investor Lead Scoring Workflow Runner

This module provides batch execution capabilities for the investor lead scoring workflow.
It handles:
- CSV input with flexible column mapping
- Batch processing with parallel or sequential execution
- Run ID polling mode (retrieve results from already-running workflows)
- Result aggregation and CSV output (supports both regular and run-ID batch files)
- Comprehensive timing statistics
- Failure handling and partial results

Usage Examples:
    # Process entire CSV in parallel (default: 2 concurrent batches)
    python wf_runner.py --input investors.csv --output results.csv
    
    # Process specific rows with custom batch size
    python wf_runner.py --input investors.csv --output results.csv --start-row 0 --end-row 50 --batch-size 10
    
    # Run batches sequentially instead of in parallel
    python wf_runner.py --input investors.csv --output results.csv --sequential
    
    # Increase parallel processing (8 concurrent batches)
    python wf_runner.py --input investors.csv --output results.csv --batch-parallelism-limit 8
    
    # Parallel execution with staggered starts (60 seconds between batch starts)
    python wf_runner.py --input investors.csv --output results.csv --batch-parallelism-limit 4 --intra-parallel-batch-delay 60
    
    # Poll existing workflow run IDs (no job submission)
    python wf_runner.py --output results.csv --run-ids abc123 def456 ghi789
    
    # Poll run IDs with limit (only first 5)
    python wf_runner.py --output results.csv --run-ids abc123 def456 ghi789 jkl012 mno345 pqr678 --poll-limit 5
    
    # Combine existing batch files without running workflows (handles both regular and run-ID batches)
    python wf_runner.py --output results.csv --combine-only
"""

import json
import asyncio
import csv
import argparse
import sys
import time
import pandas as pd
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging

# --- Test Execution Logic ---
from kiwi_client.test_run_workflow_client import (
    run_workflow_test,
    SetupDocInfo,
    CleanupDocInfo
)
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

from kiwi_client.workflows.active.investor.investor_lead_scoring_sandbox.wf_investor_lead_scoring_json import (
    workflow_graph_schema
)

logger = logging.getLogger(__name__)


def load_csv_data(csv_filename: str, start_row: int = 0, end_row: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Load CSV data and convert to the required format for workflow processing.
    
    Args:
        csv_filename: Path to the CSV file containing investor lead data
        start_row: Starting row index (0-based, excluding header)
        end_row: Ending row index (0-based, exclusive). If None, process all rows from start_row
        
    Returns:
        List of investor lead dictionaries with required fields
        
    Expected CSV columns (supports aliases):
        - first_name: First name of partner (aliases: 'First Name', 'first_name', 'First')
        - last_name: Last name of partner (aliases: 'Last Name', 'last_name', 'Last')
        - title: Partner's title (aliases: 'Title', 'title', 'Current Title', 'Role')
        - firm_company: Firm/company name (aliases: 'Firm/Company', 'firm_company', 'Current Company', 'Company', 'Fund', 'Firm')
        - firm_id: Firm ID (aliases: 'Firm ID', 'firm_id', 'FirmID')
        - investor_type: Investor type (aliases: 'Investor Type', 'investor_type', 'Type')
        - investor_role_detail: Investor role detail (aliases: 'Investor Role Detail', 'investor_role_detail', 'Role Detail')
        - relationship_status: Relationship status (aliases: 'Relationship Status', 'relationship_status', 'Status')
        - linkedin_url: LinkedIn profile URL (aliases: 'LinkedIn URL', 'linkedin_url', 'LinkedIn')
        - twitter_url: Twitter profile URL (optional, aliases: 'Twitter URL', 'twitter_url', 'Twitter')
        - crunchbase_url: Crunchbase URL (optional, aliases: 'Crunchbase URL', 'crunchbase_url', 'Crunchbase')
        - investment_criteria: Investment criteria (optional, aliases: 'Investment Criteria', 'investment_criteria', 'Criteria')
        - notes: Notes (optional, aliases: 'Notes', 'notes', 'Detailed Notes')
        - source_sheets: Source sheets (optional, aliases: 'Source Sheets', 'source_sheets', 'Source')
    """
    try:
        # Read CSV file using pandas for better handling
        df = pd.read_csv(csv_filename)
        
        # Apply row range filtering
        if end_row is not None:
            df = df.iloc[start_row:end_row]
        else:
            df = df.iloc[start_row:]
            
        logger.info(f"Loaded {len(df)} rows from CSV file: {csv_filename}")
        logger.info(f"Row range: {start_row} to {end_row if end_row else 'end'}")
        logger.info(f"Available columns: {list(df.columns)}")
        
        # Define column aliases mapping - maps standard field names to possible CSV column names
        column_aliases = {
            'first_name': ['First Name', 'first_name', 'First', 'firstName'],
            'last_name': ['Last Name', 'last_name', 'Last', 'lastName'],
            'title': ['Title', 'title', 'Current Title', 'current_title', 'Role', 'role'],
            'firm_company': ['Firm/Company', 'firm_company', 'Current Company', 'current_company', 'Company', 'company', 'Fund', 'fund', 'Firm', 'firm'],
            'firm_id': ['Firm ID', 'firm_id', 'FirmID', 'firm ID'],
            'investor_type': ['Investor Type', 'investor_type', 'Type', 'type'],
            'investor_role_detail': ['Investor Role Detail', 'investor_role_detail', 'Role Detail', 'role_detail'],
            'relationship_status': ['Relationship Status', 'relationship_status', 'Status', 'status', 'Classification', 'classification'],
            'linkedin_url': ['LinkedIn URL', 'linkedin_url', 'LinkedIn', 'linkedin', 'LinkedIn Profile'],
            'twitter_url': ['Twitter URL', 'twitter_url', 'Twitter', 'twitter', 'Twitter Profile'],
            'crunchbase_url': ['Crunchbase URL', 'crunchbase_url', 'Crunchbase', 'crunchbase'],
            'investment_criteria': ['Investment Criteria', 'investment_criteria', 'Criteria', 'criteria'],
            'notes': ['Notes', 'notes', 'Detailed Notes', 'detailed_notes'],
            'source_sheets': ['Source Sheets', 'source_sheets', 'Source', 'source']
        }
        
        # Create mapping from CSV columns to standard field names
        column_mapping = {}
        available_columns = list(df.columns)
        
        for standard_field, possible_names in column_aliases.items():
            found_column = None
            for possible_name in possible_names:
                if possible_name in available_columns:
                    found_column = possible_name
                    break
            
            if found_column:
                column_mapping[standard_field] = found_column
                logger.info(f"Mapped '{standard_field}' to CSV column '{found_column}'")
            else:
                logger.info(f"Column '{standard_field}' not found - will use empty string")
        
        # Check if required fields have been mapped (only first_name and last_name are truly required)
        required_fields = ['first_name', 'last_name']
        missing_required_fields = [field for field in required_fields if field not in column_mapping]
        
        if missing_required_fields:
            available_cols_str = ", ".join(available_columns)
            missing_aliases = {field: column_aliases[field] for field in missing_required_fields}
            raise ValueError(
                f"Could not map required fields to CSV columns: {missing_required_fields}\n"
                f"Available CSV columns: {available_cols_str}\n"
                f"Expected column names for missing fields: {missing_aliases}"
            )
        
        # Convert to list of dictionaries using the column mapping
        investors_data = []
        
        for _, row in df.iterrows():
            investor_data = {}
            
            # Map all fields, using empty string for missing optional fields
            for standard_field, csv_column in column_mapping.items():
                value = row[csv_column]
                if pd.isna(value):
                    investor_data[standard_field] = ""
                else:
                    # Strip whitespace from all fields
                    # This is especially important for linkedin_url to ensure empty check works in workflow
                    investor_data[standard_field] = str(value).strip()
            
            # Add empty strings for any optional fields not found in CSV
            for standard_field in column_aliases.keys():
                if standard_field not in investor_data:
                    investor_data[standard_field] = ""
            
            investors_data.append(investor_data)
        
        logger.info(f"Successfully processed {len(investors_data)} investor leads from CSV")
        logger.info(f"Column mappings used: {column_mapping}")
        return investors_data
        
    except FileNotFoundError:
        logger.error(f"CSV file not found: {csv_filename}")
        raise
    except Exception as e:
        logger.error(f"Error loading CSV file {csv_filename}: {str(e)}")
        raise


def save_results_to_csv(final_run_outputs: Dict[str, Any], output_csv_filename: str) -> None:
    """
    Save workflow results to CSV file with comprehensive investor scoring data.
    Handles nested Pydantic schema structure and avoids column name overlaps with input.
    
    Args:
        final_run_outputs: Final workflow outputs containing scored_investors
        output_csv_filename: Path to output CSV file
    """
    try:
        scored_investors = final_run_outputs.get('scored_investors', [])
        
        if not scored_investors:
            logger.warning("No scored investors found in workflow outputs")
            return
        
        # Helper function to flatten nested portfolio company lists
        def flatten_portfolio_companies(companies_list):
            """Convert list of PortfolioCompany objects to formatted string."""
            if not companies_list:
                return ""
            result = []
            for company in companies_list:
                if isinstance(company, dict):
                    parts = [company.get('company_name', '')]
                    if company.get('investment_date'):
                        parts.append(f"({company['investment_date']})")
                    if company.get('sector'):
                        parts.append(f"[{company['sector']}]")
                    result.append(' '.join(parts))
            return ' | '.join(result)
        
        # Helper function to flatten led round examples
        def flatten_led_rounds(rounds_list):
            """Convert list of LedRoundExample objects to formatted string."""
            if not rounds_list:
                return ""
            result = []
            for round_item in rounds_list:
                if isinstance(round_item, dict):
                    parts = [round_item.get('company_name', '')]
                    if round_item.get('date'):
                        parts.append(round_item['date'])
                    if round_item.get('round_size'):
                        parts.append(round_item['round_size'])
                    result.append(' - '.join(parts))
            return ' | '.join(result)
        
        # Helper function to flatten exit details
        def flatten_exits(exits_list):
            """Convert list of ExitDetails objects to formatted string."""
            if not exits_list:
                return ""
            result = []
            for exit in exits_list:
                if isinstance(exit, dict):
                    parts = [exit.get('company_name', '')]
                    if exit.get('exit_type'):
                        parts.append(f"({exit['exit_type']})")
                    if exit.get('exit_date'):
                        parts.append(exit['exit_date'])
                    result.append(' '.join(parts))
            return ' | '.join(result)
        
        # Prepare CSV rows with flattened data structure
        csv_rows = []
        
        for investor in scored_investors:
            row = {}
            
            # ===== INPUT DATA (from passthrough) =====
            # Using new column structure
            row['input_first_name'] = investor.get('first_name', '')
            row['input_last_name'] = investor.get('last_name', '')
            row['input_title'] = investor.get('title', '')
            row['input_firm_company'] = investor.get('firm_company', '')
            row['input_firm_id'] = investor.get('firm_id', '')
            row['input_investor_type'] = investor.get('investor_type', '')
            row['input_investor_role_detail'] = investor.get('investor_role_detail', '')
            row['input_relationship_status'] = investor.get('relationship_status', '')
            row['input_linkedin_url'] = investor.get('linkedin_url', '')
            row['input_twitter_url'] = investor.get('twitter_url', '')
            row['input_crunchbase_url'] = investor.get('crunchbase_url', '')
            row['input_investment_criteria'] = investor.get('investment_criteria', '')
            row['input_notes'] = investor.get('notes', '')
            row['input_source_sheets'] = investor.get('source_sheets', '')
            # URL found by Perplexity if originally missing
            row['linkedin_url_found_by_perplexity'] = investor.get('linkedin_url_found', '')
            
            # # ===== DEEP RESEARCH REPORT =====
            # deep_research_report = investor.get('deep_research_report', '')
            # row['research_report'] = deep_research_report  # [:2000] + '...' if len(deep_research_report) > 2000 else deep_research_report
            # deep_research_citations = investor.get('deep_research_citations', '')
            # deep_research_citations = json.dumps(deep_research_citations, indent=2) if isinstance(deep_research_citations, (list, dict)) else deep_research_citations
            # row['research_citations'] = deep_research_citations  # [:2000] + '...' if len(deep_research_citations) > 2000 else deep_research_citations
            
            # Parse scoring result (nested Pydantic schema)
            scoring_result_raw = investor.get('scoring_result', {})
            if isinstance(scoring_result_raw, str):
                try:
                    scoring_result = json.loads(scoring_result_raw)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"Failed to parse scoring_result as JSON")
                    scoring_result = {}
            elif isinstance(scoring_result_raw, dict):
                scoring_result = scoring_result_raw
            else:
                logger.warning(f"Unexpected scoring_result type: {type(scoring_result_raw)}")
                scoring_result = {}
            
            # ===== EXTRACT NESTED SCORING RESULTS =====
            if isinstance(scoring_result, dict):
                # === CURRENT EMPLOYMENT INFO (NEW - at top for visibility) ===
                employment = scoring_result.get('current_employment', {})
                if isinstance(employment, dict):
                    row['current_fund_verified'] = employment.get('current_fund_name', '')
                    row['current_title_verified'] = employment.get('current_title', '')
                    row['still_at_input_firm'] = employment.get('is_still_at_input_firm', True)
                    row['firm_change_detected'] = employment.get('firm_change_detected', False)
                    row['firm_change_details'] = employment.get('firm_change_details', '')
                    row['still_in_vc'] = employment.get('is_still_in_vc', True)
                    row['employment_notes'] = employment.get('employment_notes', '')
                
                # === OVERALL SCORES (100-point framework) ===
                row['total_score'] = scoring_result.get('total_score', 0)

                # === DISQUALIFICATION (right after score for easy review) ===
                dq = scoring_result.get('disqualification', {})
                if isinstance(dq, dict):
                    row['is_disqualified'] = dq.get('is_disqualified', False)
                    row['disqualification_reason'] = dq.get('disqualification_reason', '')

                # === TIER & ACTION (after DQ status) ===
                row['score_tier'] = scoring_result.get('score_tier', '')
                row['recommended_action'] = scoring_result.get('recommended_action', '')
                
                # === FUND VITALS (0-25 points) ===
                fund_vitals = scoring_result.get('fund_vitals', {})
                if isinstance(fund_vitals, dict):
                    row['fund_size_usd'] = fund_vitals.get('fund_size_usd', '')
                    row['fund_size_points'] = fund_vitals.get('fund_size_points', 0)
                    row['fund_size_reasoning'] = fund_vitals.get('fund_size_reasoning', '')
                    row['fund_number'] = fund_vitals.get('fund_number', '')
                    row['latest_fund_raise_date'] = fund_vitals.get('latest_fund_raise_date', '')
                    row['recent_activity_2024_2025'] = fund_vitals.get('recent_activity_2024_2025', '')
                    row['deals_in_2025_count'] = fund_vitals.get('deals_in_2025_count', 0)
                    row['deals_in_2024_count'] = fund_vitals.get('deals_in_2024_count', 0)
                    row['activity_points'] = fund_vitals.get('activity_points', 0)
                    row['activity_reasoning'] = fund_vitals.get('activity_reasoning', '')
                    row['fund_vitals_total'] = fund_vitals.get('category_total', 0)
                
                # === LEAD CAPABILITY (0-25 points) ===
                lead_cap = scoring_result.get('lead_capability', {})
                if isinstance(lead_cap, dict):
                    row['lead_behavior'] = lead_cap.get('lead_behavior', '')
                    row['led_rounds_count'] = lead_cap.get('led_rounds_count', 0)
                    row['led_round_examples'] = flatten_led_rounds(lead_cap.get('led_round_examples', []))
                    row['lead_behavior_points'] = lead_cap.get('lead_behavior_points', 0)
                    row['lead_behavior_reasoning'] = lead_cap.get('lead_behavior_reasoning', '')
                    row['typical_check_size'] = lead_cap.get('typical_check_size', '')
                    row['check_size_points'] = lead_cap.get('check_size_points', 0)
                    row['check_size_reasoning'] = lead_cap.get('check_size_reasoning', '')
                    row['lead_capability_total'] = lead_cap.get('category_total', 0)
                
                # === THESIS ALIGNMENT (0-30 points) ===
                thesis = scoring_result.get('thesis_alignment', {})
                if isinstance(thesis, dict):
                    row['ai_b2b_portfolio_count'] = thesis.get('ai_b2b_portfolio_count', 0)
                    row['ai_b2b_companies'] = flatten_portfolio_companies(thesis.get('ai_b2b_companies', []))
                    row['ai_b2b_points'] = thesis.get('ai_b2b_points', 0)
                    row['martech_portfolio_count'] = thesis.get('martech_portfolio_count', 0)
                    row['martech_companies'] = flatten_portfolio_companies(thesis.get('martech_companies', []))
                    row['martech_points'] = thesis.get('martech_points', 0)
                    row['has_explicit_ai_b2b_thesis'] = thesis.get('has_explicit_ai_b2b_thesis', False)
                    row['investment_thesis_summary'] = thesis.get('investment_thesis_summary', '')
                    row['thesis_points'] = thesis.get('thesis_points', 0)
                    row['devtools_api_portfolio_count'] = thesis.get('devtools_api_portfolio_count', 0)
                    row['devtools_api_companies'] = flatten_portfolio_companies(thesis.get('devtools_api_companies', []))
                    row['has_devtools_api_focus'] = thesis.get('has_devtools_api_focus', False)
                    row['devtools_api_points'] = thesis.get('devtools_api_points', 0)
                    row['plg_portfolio_count'] = thesis.get('plg_portfolio_count', 0)
                    row['plg_companies'] = flatten_portfolio_companies(thesis.get('plg_companies', []))
                    row['has_plg_focus'] = thesis.get('has_plg_focus', False)
                    row['plg_points'] = thesis.get('plg_points', 0)
                    row['thesis_alignment_total'] = thesis.get('category_total', 0)
                
                # === PARTNER VALUE (0-15 points) ===
                partner = scoring_result.get('partner_value', {})
                if isinstance(partner, dict):
                    row['partner_title'] = partner.get('partner_title', '')
                    row['decision_authority_level'] = partner.get('decision_authority_level', '')
                    row['title_points'] = partner.get('title_points', 0)
                    row['title_reasoning'] = partner.get('title_reasoning', '')
                    row['operational_background_summary'] = partner.get('operational_background_summary', '')
                    row['is_ex_founder_martech_b2b'] = partner.get('is_ex_founder_martech_b2b', False)
                    row['founder_details'] = partner.get('founder_details', '')
                    row['ex_founder_points'] = partner.get('ex_founder_points', 0)
                    row['is_ex_cmo_vp_marketing'] = partner.get('is_ex_cmo_vp_marketing', False)
                    row['cmo_marketing_details'] = partner.get('cmo_marketing_details', '')
                    row['ex_cmo_marketing_points'] = partner.get('ex_cmo_marketing_points', 0)
                    row['is_ex_vp_sales_growth'] = partner.get('is_ex_vp_sales_growth', False)
                    row['vp_sales_growth_details'] = partner.get('vp_sales_growth_details', '')
                    row['ex_vp_sales_points'] = partner.get('ex_vp_sales_points', 0)
                    row['is_active_creator'] = partner.get('is_active_creator', False)
                    row['active_creator_details'] = partner.get('active_creator_details', '')
                    row['active_creator_points'] = partner.get('active_creator_points', 0)
                    row['background_total_points'] = partner.get('background_total_points', 0)
                    row['partner_value_total'] = partner.get('category_total', 0)
                
                # === STRATEGIC FACTORS (0-5 points) ===
                strategic = scoring_result.get('strategic_factors', {})
                if isinstance(strategic, dict):
                    row['fund_hq_location'] = strategic.get('fund_hq_location', '')
                    row['geography_category'] = strategic.get('geography_category', '')
                    row['geography_points'] = strategic.get('geography_points', 0)
                    row['has_new_fund_under_18mo'] = strategic.get('has_new_fund_under_18mo', False)
                    row['new_fund_details'] = strategic.get('new_fund_details', '')
                    row['has_recent_exits'] = strategic.get('has_recent_exits', False)
                    row['exits_count_3yr'] = strategic.get('exits_count_3yr', 0)
                    row['exit_details'] = flatten_exits(strategic.get('exit_details', []))
                    row['has_portfolio_followons'] = strategic.get('has_portfolio_followons', False)
                    row['followon_details'] = strategic.get('followon_details', '')
                    row['momentum_points'] = strategic.get('momentum_points', 0)
                    row['momentum_reasoning'] = strategic.get('momentum_reasoning', '')
                    row['strategic_factors_total'] = strategic.get('category_total', 0)

                # === ACTIONABLE INTELLIGENCE (9 sections from playbook) ===
                intel = scoring_result.get('actionable_intelligence', {})
                if isinstance(intel, dict):
                    row['portfolio_pattern'] = intel.get('portfolio_pattern', '')
                    row['partner_insights'] = intel.get('partner_insights', '')
                    row['investment_pace_and_process'] = intel.get('investment_pace_and_process', '')
                    row['value_add_evidence'] = intel.get('value_add_evidence', '')
                    row['deal_preferences'] = intel.get('deal_preferences', '')
                    row['recent_positioning'] = intel.get('recent_positioning', '')
                    row['fund_context'] = intel.get('fund_context', '')
                    row['competitive_intel'] = intel.get('competitive_intel', '')
                    row['pitch_prep'] = intel.get('pitch_prep', '')

                # === ADDITIONAL CONTEXT ===
                row['notable_portfolio_companies'] = flatten_portfolio_companies(scoring_result.get('notable_portfolio_companies', []))
                row['research_confidence'] = scoring_result.get('research_confidence', '')
                row['missing_critical_info'] = ' | '.join(scoring_result.get('missing_critical_info', []))
            
            csv_rows.append(row)
        
        # Write to CSV file
        if csv_rows:
            fieldnames = list(csv_rows[0].keys())
            
            with open(output_csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(csv_rows)
            
            logger.info(f"Successfully saved {len(csv_rows)} scored investors to: {output_csv_filename}")
            
            # Log summary statistics
            total_disqualified = len([row for row in csv_rows if row.get('is_disqualified', False)])
            avg_score = sum(float(row.get('total_score', 0)) for row in csv_rows) / len(csv_rows) if csv_rows else 0
            a_tier = len([row for row in csv_rows if 'A' in row.get('score_tier', '')])
            b_tier = len([row for row in csv_rows if 'B' in row.get('score_tier', '')])

            logger.info(f"Summary: {a_tier} A-tier (85-100), {b_tier} B-tier (70-84), {total_disqualified} disqualified, Avg Score: {avg_score:.1f}/100")
        else:
            logger.warning("No data to write to CSV file")
            
    except Exception as e:
        logger.error(f"Error saving results to CSV file {output_csv_filename}: {str(e)}")
        raise


# Example Test Inputs (updated for new schema)
TEST_INPUTS = {
    "investors_to_process": [
        {
            "first_name": "Oliver",
            "last_name": "Hsu",
            "title": "Investment Partner",
            "firm_company": "Andreessen Horowitz",
            "firm_id": "FIRM_001",
            "investor_type": "VC/Institutional",
            "investor_role_detail": "VC (Partner/Principal)",
            "relationship_status": "WARM",
            "linkedin_url": "https://www.linkedin.com/in/ohsu",
            "twitter_url": "https://twitter.com/oyhsu",
            "crunchbase_url": "",
            "investment_criteria": "AI/B2B SaaS, Seed to Series A",
            "notes": "Location: New York, New York, United States | GOOD FIT: Partner at US-based VC",
            "source_sheets": "Test Data"
        }
    ]
}


async def validate_output(outputs: Optional[Dict[str, Any]]) -> bool:
    """
    Custom validation function for the workflow outputs.
    
    Validates that:
    1. Investors were processed through deep research
    2. All investors received structured scoring
    3. Final results contain all required fields
    4. Deep research reports are present
    """
    assert outputs is not None, "Validation Failed: Workflow returned no outputs."
    logger.info("Validating investor lead scoring workflow outputs...")
    
    # Check if we have the expected output fields
    assert 'scored_investors' in outputs, "Validation Failed: 'scored_investors' key missing."
    
    scored_results = outputs.get('scored_investors', [])
    
    logger.info(f"Scored results count: {len(scored_results)}")
    
    # Validate that we have some scored results
    assert len(scored_results) > 0, "Validation Failed: No investors were scored successfully."
    
    # Validate the structure of scored results
    for i, result in enumerate(scored_results):
        logger.info(f"Validating result {i+1}...")
        
        # Check for required lead information (from passthrough data)
        required_lead_fields = ['first_name', 'last_name', 'firm_company']
        for field in required_lead_fields:
            assert field in result, f"Validation Failed: Missing lead field '{field}' in result {i+1}"
        
        # Check for deep research report
        assert 'deep_research_report' in result, f"Validation Failed: Missing deep_research_report in result {i+1}"
        assert len(result['deep_research_report']) > 100, f"Validation Failed: Deep research report too short in result {i+1}"
        
        # Check for scoring result
        assert 'scoring_result' in result, f"Validation Failed: Missing scoring_result in result {i+1}"
        
        scoring_result = result['scoring_result']
        
        # Check for top-level scoring fields (100-point framework)
        required_top_level_fields = ['total_score', 'score_tier', 'recommended_action']
        for field in required_top_level_fields:
            assert field in scoring_result, f"Validation Failed: Missing top-level field '{field}' in result {i+1}"

        # Check for nested scoring sections (new 100-point Pydantic structure)
        required_sections = ['current_employment', 'fund_vitals', 'lead_capability', 'thesis_alignment', 'partner_value',
                            'strategic_factors', 'disqualification', 'actionable_intelligence']
        for section in required_sections:
            assert section in scoring_result, f"Validation Failed: Missing section '{section}' in result {i+1}"
        
        # Check employment verification
        employment = scoring_result.get('current_employment', {})
        assert 'current_fund_name' in employment, f"Validation Failed: Missing current_fund_name in result {i+1}"
        assert 'is_still_at_input_firm' in employment, f"Validation Failed: Missing is_still_at_input_firm in result {i+1}"
        
        # Check disqualification info
        dq = scoring_result.get('disqualification', {})
        assert 'is_disqualified' in dq, f"Validation Failed: Missing is_disqualified in result {i+1}"
        
        # Log validation results with firm change info
        input_firm = result.get('firm_company', 'Unknown')
        current_firm = employment.get('current_fund_name', 'Unknown')
        firm_changed = employment.get('firm_change_detected', False)

        logger.info(f"  ✓ Investor: {result['first_name']} {result['last_name']}")
        logger.info(f"  ✓ Input Firm: {input_firm} | Current Firm: {current_firm}{' (CHANGED)' if firm_changed else ''}")
        logger.info(f"  ✓ Total Score: {scoring_result['total_score']}/100 ({scoring_result['score_tier']})")
        logger.info(f"  ✓ Disqualified: {dq['is_disqualified']}")
        logger.info(f"  ✓ Research report length: {len(result['deep_research_report'])} characters")
    
    logger.info("✓ All validation checks passed successfully!")
    return True


async def run_batch_workflow(input_csv: str,
                             output_csv: str, 
                             batch_start: int,
                             batch_end: int,
                             batch_number: int,
                             total_batches: int) -> tuple:
    """
    Run a single batch of the workflow.
    
    Returns:
        Tuple of (status, outputs, duration, investors_processed)
    """
    batch_start_time = time.time()
    batch_size = batch_end - batch_start
    test_name = f"Batch {batch_number}/{total_batches}"
    
    print(f"  Loading {batch_size} investors from rows {batch_start}-{batch_end-1}...")
    
    try:
        # Load CSV data for this batch
        investors_data = load_csv_data(input_csv, batch_start, batch_end)
        initial_inputs = {"investors_to_process": investors_data}
        
        print(f"  Running workflow for {len(investors_data)} investors...")
        
        # Run workflow for this batch
        final_run_status_obj, final_run_outputs = await run_single_workflow(
            input_data=initial_inputs,
            test_name=test_name
        )
        
        # Save batch results to file
        investors_processed = 0
        if final_run_outputs and 'scored_investors' in final_run_outputs:
            save_results_to_csv(final_run_outputs, output_csv)
            investors_processed = len(final_run_outputs['scored_investors'])
            print(f"  Saved {investors_processed} results to: {Path(output_csv).name}")
        else:
            print(f"  ⚠️  No results to save")
        
        batch_duration = time.time() - batch_start_time
        
        return final_run_status_obj, final_run_outputs, batch_duration, investors_processed
        
    except Exception as e:
        batch_duration = time.time() - batch_start_time
        print(f"  ❌ Batch failed: {str(e)}")
        return None, None, batch_duration, 0


def combine_existing_batch_files(batch_folder: str, output_csv: str) -> None:
    """
    Combine all existing batch CSV files in the batch folder into a single output file.
    Handles both regular batch files (batch_001_rows_0-10.csv) and run ID files (batch_runid_abc123.csv).
    
    Args:
        batch_folder: Path to folder containing batch result files
        output_csv: Path to final combined output CSV file
    """
    batch_folder_path = Path(batch_folder)
    
    if not batch_folder_path.exists():
        print(f"❌ Batch folder does not exist: {batch_folder}")
        return
    
    # Find all batch CSV files (both regular and run ID patterns)
    all_batch_files = list(batch_folder_path.glob("batch_*.csv"))
    
    if not all_batch_files:
        print(f"❌ No batch files found in: {batch_folder}")
        return
    
    # Separate regular batch files and run ID batch files for reporting
    regular_batch_files = [f for f in all_batch_files if not f.name.startswith("batch_runid_")]
    runid_batch_files = [f for f in all_batch_files if f.name.startswith("batch_runid_")]
    
    # Sort files by name for consistent ordering
    all_batch_files.sort()
    batch_file_paths = [str(f) for f in all_batch_files]
    
    print(f"📁 Found {len(all_batch_files)} batch files in: {batch_folder}")
    if regular_batch_files:
        print(f"  - {len(regular_batch_files)} regular batch files (batch_###_rows_*)")
    if runid_batch_files:
        print(f"  - {len(runid_batch_files)} run ID batch files (batch_runid_*)")
    
    # Show first few files of each type
    if regular_batch_files:
        print(f"\n  Regular batch files:")
        for batch_file in sorted(regular_batch_files)[:3]:
            print(f"    - {batch_file.name}")
        if len(regular_batch_files) > 3:
            print(f"    ... and {len(regular_batch_files) - 3} more")
    
    if runid_batch_files:
        print(f"\n  Run ID batch files:")
        for batch_file in sorted(runid_batch_files)[:3]:
            print(f"    - {batch_file.name}")
        if len(runid_batch_files) > 3:
            print(f"    ... and {len(runid_batch_files) - 3} more")
    
    print()
    
    # Use existing combine function
    combine_batch_results(batch_file_paths, output_csv)
    
    print(f"✅ Combined {len(all_batch_files)} batch files into: {output_csv}")


def combine_batch_results(batch_output_files: List[str], final_output_csv: str) -> None:
    """
    Combine results from multiple batch CSV files into a single output file.
    
    Args:
        batch_output_files: List of batch CSV file paths
        final_output_csv: Path to final combined output CSV file
    """
    logger.info(f"Combining {len(batch_output_files)} batch result files into: {final_output_csv}")
    
    combined_rows = []
    
    for i, batch_file in enumerate(batch_output_files):
        if not Path(batch_file).exists():
            logger.warning(f"Batch file does not exist: {batch_file}")
            continue
            
        try:
            # Read batch CSV file
            batch_df = pd.read_csv(batch_file)
            logger.info(f"Loaded {len(batch_df)} results from batch file {i+1}: {batch_file}")
            
            # Convert to list of dictionaries and add to combined results
            batch_rows = batch_df.to_dict('records')
            combined_rows.extend(batch_rows)
            
        except Exception as e:
            logger.error(f"Error reading batch file {batch_file}: {str(e)}")
            continue
    
    if combined_rows:
        # Write combined results to final CSV
        combined_df = pd.DataFrame(combined_rows)
        combined_df.to_csv(final_output_csv, index=False)
        
        logger.info(f"Successfully combined {len(combined_rows)} total results into: {final_output_csv}")
        
        # Log summary statistics
        total_disqualified = len([row for row in combined_rows if row.get('is_disqualified', False)])
        avg_score = sum(float(row.get('total_score', 0)) for row in combined_rows if row.get('total_score')) / len(combined_rows) if combined_rows else 0
        a_tier = len([row for row in combined_rows if 'A' in str(row.get('score_tier', ''))])
        b_tier = len([row for row in combined_rows if 'B' in str(row.get('score_tier', ''))])

        logger.info(f"Final Summary: {a_tier} A-tier (85-100), {b_tier} B-tier (70-84), {total_disqualified} disqualified, Avg Score: {avg_score:.1f}/100")
    else:
        logger.warning("No batch results to combine")


async def run_single_workflow(input_data: Dict[str, Any], test_name: str) -> tuple:
    """
    Run a single workflow instance with given input data.
    
    Args:
        input_data: Input data for the workflow
        test_name: Name for this workflow test
        
    Returns:
        Tuple of (final_run_status_obj, final_run_outputs)
    """
    import io
    import contextlib
    
    logger.info(f"Starting {test_name}...")
    
    # Capture all stdout to prevent WorkflowRunRead objects from being printed
    captured_output = io.StringIO()
    
    try:
        with contextlib.redirect_stdout(captured_output):
            final_run_status_obj, final_run_outputs = await run_workflow_test(
                test_name=test_name,
                workflow_graph_schema=workflow_graph_schema,
                initial_inputs=input_data,
                expected_final_status=WorkflowRunStatus.COMPLETED,
                setup_docs=None,
                cleanup_docs=None,
                stream_intermediate_results=False,  # Suppress verbose workflow output
                dump_artifacts=False,  # Don't create artifact files
                poll_interval_sec=10,  # Poll every 10 seconds
                timeout_sec=1800  # 30 minutes for deep research workflows
            )
    except Exception as e:
        logger.error(f"Workflow execution failed: {str(e)}")
        raise
    
    # Log completion status without printing the full object
    status_str = str(final_run_status_obj.status) if final_run_status_obj else "None"
    logger.info(f"{test_name} completed with status: {status_str}")
    
    return final_run_status_obj, final_run_outputs


async def poll_existing_run_id(run_id: str, batch_folder_path: Path, output_csv_suffix: str) -> Dict[str, Any]:
    """
    Poll an existing workflow run ID and save results.
    
    Args:
        run_id: The workflow run ID to poll
        batch_folder_path: Folder to store batch result files
        output_csv_suffix: File extension for output files (e.g., '.csv')
        
    Returns:
        Dictionary containing polling results and timing information
    """
    from kiwi_client.test_run_workflow_client import poll_workflow_run_until_completion
    
    poll_start_time = time.time()
    
    print(f"📡 Polling run ID: {run_id}")
    
    try:
        # Poll the existing workflow run until completion
        final_run_status_obj, final_run_outputs = await poll_workflow_run_until_completion(
            run_id=run_id,
            poll_interval_sec=10,
            timeout_sec=3600  # 1 hour timeout for polling
        )
        
        poll_duration = time.time() - poll_start_time
        
        # Save results to file with run ID in filename
        investors_processed = 0
        batch_output_file = batch_folder_path / f"batch_runid_{run_id}{output_csv_suffix}"
        
        if final_run_outputs and 'scored_investors' in final_run_outputs:
            save_results_to_csv(final_run_outputs, str(batch_output_file))
            investors_processed = len(final_run_outputs['scored_investors'])
            print(f"  ✅ Saved {investors_processed} results to: {batch_output_file.name}")
        else:
            print(f"  ⚠️  No results found for run ID: {run_id}")
        
        success = final_run_status_obj and final_run_status_obj.status == WorkflowRunStatus.COMPLETED
        
        return {
            'run_id': run_id,
            'status': final_run_status_obj,
            'outputs': final_run_outputs,
            'duration': poll_duration,
            'investors_processed': investors_processed,
            'output_file': str(batch_output_file),
            'success': success
        }
        
    except Exception as e:
        poll_duration = time.time() - poll_start_time
        print(f"  ❌ Failed to poll run ID {run_id}: {str(e)}")
        
        return {
            'run_id': run_id,
            'status': None,
            'outputs': None,
            'duration': poll_duration,
            'investors_processed': 0,
            'output_file': None,
            'success': False,
            'error': str(e)
        }


async def poll_existing_run_ids(
    run_ids: List[str],
    batch_folder_path: Path,
    output_csv: str,
    poll_limit: Optional[int] = None
) -> tuple:
    """
    Poll multiple existing workflow run IDs and save their results.
    
    Args:
        run_ids: List of workflow run IDs to poll
        batch_folder_path: Folder to store batch result files
        output_csv: Path to output CSV file (used for file extension)
        poll_limit: Maximum number of run IDs to poll (None = poll all)
        
    Returns:
        Tuple of (successful_polls, failed_polls, poll_timings, total_investors_processed)
    """
    output_suffix = Path(output_csv).suffix
    
    # Apply poll limit if specified
    if poll_limit is not None and poll_limit > 0:
        run_ids = run_ids[:poll_limit]
        print(f"📊 Polling {len(run_ids)} run IDs (limited to {poll_limit})")
    else:
        print(f"📊 Polling {len(run_ids)} run IDs")
    
    print()
    
    # Poll each run ID sequentially
    poll_results = []
    for i, run_id in enumerate(run_ids, 1):
        print(f"{'='*60}")
        print(f"POLLING RUN ID {i}/{len(run_ids)}: {run_id}")
        print(f"{'='*60}")
        
        result = await poll_existing_run_id(
            run_id=run_id,
            batch_folder_path=batch_folder_path,
            output_csv_suffix=output_suffix
        )
        
        poll_results.append(result)
        print()
    
    # Process results
    successful_polls = sum(1 for r in poll_results if r['success'])
    failed_polls = len(poll_results) - successful_polls
    total_investors_processed = sum(r['investors_processed'] for r in poll_results)
    
    poll_timings = [
        {
            'run_id': r['run_id'],
            'duration': r['duration'],
            'investors_processed': r['investors_processed'],
            'success': r['success']
        }
        for r in poll_results
    ]
    
    print(f"📈 POLLING SUMMARY:")
    print(f"  Total run IDs polled: {len(run_ids)}")
    print(f"  Successful: {successful_polls}")
    print(f"  Failed: {failed_polls}")
    print(f"  Total investors retrieved: {total_investors_processed}")
    print()
    
    return successful_polls, failed_polls, poll_timings, total_investors_processed


def print_partial_statistics(overall_start_time: float, 
                            batch_timings: List[Dict],
                            total_investors_processed: int,
                            successful_batches: int,
                            failed_batches: int,
                            total_delay_time: float,
                            current_batch: int,
                            total_batches: int,
                            start_row: int,
                            batch_size: int) -> None:
    """
    Print partial statistics when job stops due to failure.
    """
    current_time = time.time()
    partial_execution_time = current_time - overall_start_time
    
    # Calculate pure workflow time from successful batches
    successful_batch_timings = [b for b in batch_timings if b['investors_processed'] > 0]
    pure_workflow_time = sum(b['duration'] for b in successful_batch_timings)
    
    print(f"\n{'='*60}")
    print(f"JOB STOPPED DUE TO BATCH FAILURE - PARTIAL STATISTICS")
    print(f"{'='*60}")
    
    print(f"📊 PROGRESS AT FAILURE:")
    print(f"  Batches completed: {successful_batches}/{total_batches}")
    print(f"  Batches failed: {failed_batches}")
    print(f"  Current batch: {current_batch}")
    print(f"  Investors processed: {total_investors_processed}")
    
    if successful_batch_timings:
        for batch_timing in successful_batch_timings:
            batch_num = batch_timing['batch_num']
            duration = batch_timing['duration']
            investors = batch_timing['investors_processed']
            avg_time = batch_timing['avg_time_per_investor']
            print(f"  Batch {batch_num:2d}: {duration:5.1f}s total, {investors:2d} investors, {avg_time:4.1f}s/investor")
    
    print(f"{'='*60}")


async def run_single_batch_with_semaphore(
    semaphore: asyncio.Semaphore,
    input_csv: str,
    batch_output_file: str,
    batch_start: int,
    batch_end: int,
    batch_num: int,
    total_batches: int,
    delay: int = 0,
    is_sequential: bool = False,
    intra_parallel_batch_delay: int = 0
) -> Dict[str, Any]:
    """
    Run a single batch workflow with semaphore control for both parallel and sequential execution.
    
    Args:
        semaphore: Asyncio semaphore to control concurrency
        delay: Delay in seconds after batch completion (only for sequential mode)
        is_sequential: If True, adds detailed progress reporting and delays
        intra_parallel_batch_delay: Delay in seconds before starting each batch in parallel mode.
                                   Each batch waits (batch_num - 1) * intra_parallel_batch_delay seconds
                                   before starting. Default: 0 (no staggering)
    
    Returns:
        Dictionary containing batch results and timing information
    """
    # Apply intra-parallel batch delay to stagger batch starts (only in parallel mode)
    stagger_delay_time = 0.0
    if not is_sequential and intra_parallel_batch_delay > 0 and batch_num > 1:
        stagger_delay_seconds = (batch_num - 1) * intra_parallel_batch_delay
        print(f"⏳ Batch {batch_num}: Waiting {stagger_delay_seconds}s before starting (intra-batch stagger)...")
        stagger_start = time.time()
        await asyncio.sleep(stagger_delay_seconds)
        stagger_delay_time = time.time() - stagger_start
    
    async with semaphore:
        if is_sequential:
            print(f"{'='*60}")
            print(f"BATCH {batch_num}/{total_batches}: Processing rows {batch_start}-{batch_end-1}")
            print(f"{'='*60}")
        else:
            print(f"🔄 Starting Batch {batch_num}/{total_batches}: rows {batch_start}-{batch_end-1}")
        
        batch_status, batch_outputs, batch_duration, investors_processed = await run_batch_workflow(
            input_csv=input_csv,
            output_csv=batch_output_file,
            batch_start=batch_start,
            batch_end=batch_end,
            batch_number=batch_num,
            total_batches=total_batches
        )
        
        # Return comprehensive batch result
        result = {
            'batch_num': batch_num,
            'batch_start': batch_start,
            'batch_end': batch_end,
            'status': batch_status,
            'outputs': batch_outputs,
            'duration': batch_duration,
            'investors_processed': investors_processed,
            'avg_time_per_investor': batch_duration / investors_processed if investors_processed > 0 else 0,
            'output_file': batch_output_file,
            'success': batch_status and batch_status.status == WorkflowRunStatus.COMPLETED if batch_status else False,
            'actual_delay_time': 0.0,  # Will be updated if post-completion delay is applied (sequential mode)
            'stagger_delay_time': stagger_delay_time  # Pre-start delay for parallel batch staggering
        }
        
        # Print completion status
        if result['success']:
            print(f"✅ Batch {batch_num} completed in {batch_duration:.1f}s ({investors_processed} investors)")
        else:
            print(f"❌ Batch {batch_num} failed after {batch_duration:.1f}s")
        
        if is_sequential and batch_num < total_batches and delay > 0:
            print(f"⏳ Waiting {delay} seconds before next batch...")
            delay_start_time = time.time()
            await asyncio.sleep(delay)
            delay_end_time = time.time()
            actual_delay_time = delay_end_time - delay_start_time
            result['actual_delay_time'] = actual_delay_time
            print()
        
        return result


async def run_batches_unified(
    input_csv: str,
    batch_folder_path: Path,
    output_csv: str,
    start_row: int,
    actual_end_row: int,
    batch_size: int,
    total_batches: int,
    batch_parallelism_limit: int,
    stop_on_failure: bool,
    batch_output_files: List[str],
    delay: int = 0,
    overall_start_time: float = None,
    intra_parallel_batch_delay: int = 0
) -> tuple:
    """
    Run batches with semaphore-controlled concurrency (unified for both parallel and sequential modes).
    
    Args:
        intra_parallel_batch_delay: Delay in seconds between batch starts in parallel mode.
                                   Each batch waits (batch_num - 1) * intra_parallel_batch_delay
                                   before starting. Default: 0 (no staggering)
    
    Returns:
        Tuple of (successful_batches, failed_batches, batch_timings, total_investors_processed[, total_delay_time][, total_stagger_time])
    """
    # Create semaphore to limit concurrent batches
    semaphore = asyncio.Semaphore(batch_parallelism_limit)
    is_sequential = batch_parallelism_limit == 1
    
    # Create batch tasks
    batch_tasks = []
    for batch_num in range(1, total_batches + 1):
        batch_start = start_row + (batch_num - 1) * batch_size
        batch_end = min(batch_start + batch_size, actual_end_row)
        
        # Create batch-specific output file
        output_suffix = Path(output_csv).suffix
        batch_output_file = batch_folder_path / f"batch_{batch_num:03d}_rows_{batch_start}-{batch_end-1}{output_suffix}"
        batch_output_files.append(str(batch_output_file))
        
        # Create task for this batch
        task = run_single_batch_with_semaphore(
            semaphore=semaphore,
            input_csv=input_csv,
            batch_output_file=str(batch_output_file),
            batch_start=batch_start,
            batch_end=batch_end,
            batch_num=batch_num,
            total_batches=total_batches,
            delay=delay,
            is_sequential=is_sequential,
            intra_parallel_batch_delay=intra_parallel_batch_delay
        )
        batch_tasks.append(task)
    
    print(f"📊 Created {len(batch_tasks)} batch tasks for {'sequential' if is_sequential else 'parallel'} execution")
    print(f"⚡ Running with concurrency limit: {batch_parallelism_limit}")
    print()
    
    # Execute all batches
    try:
        if stop_on_failure:
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=False)
        else:
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
    except Exception as e:
        print(f"❌ Batch execution stopped due to failure: {str(e)}")
        if stop_on_failure:
            raise RuntimeError(f"Batch processing stopped due to batch failure: {str(e)}")
        batch_results = []
    
    # Process results
    successful_batches = 0
    failed_batches = 0
    batch_timings = []
    total_investors_processed = 0
    total_delay_time = 0.0
    total_stagger_time = 0.0
    
    for i, result in enumerate(batch_results):
        if isinstance(result, Exception):
            failed_batches += 1
            batch_num = i + 1
            print(f"❌ Batch {batch_num} failed with exception: {str(result)}")
            batch_timings.append({
                'batch_num': batch_num,
                'duration': 0.0,
                'investors_processed': 0,
                'avg_time_per_investor': 0.0
            })
        elif isinstance(result, dict):
            if result['success']:
                successful_batches += 1
                total_investors_processed += result['investors_processed']
            else:
                failed_batches += 1
            
            total_delay_time += result.get('actual_delay_time', 0.0)
            total_stagger_time += result.get('stagger_delay_time', 0.0)
            
            batch_timings.append({
                'batch_num': result['batch_num'],
                'duration': result['duration'],
                'investors_processed': result['investors_processed'],
                'avg_time_per_investor': result['avg_time_per_investor']
            })
    
    batch_timings.sort(key=lambda x: x['batch_num'])
    
    execution_mode = "SEQUENTIAL" if is_sequential else "PARALLEL"
    print(f"\n📈 {execution_mode} EXECUTION SUMMARY:")
    print(f"  Total batches: {total_batches}")
    print(f"  Successful: {successful_batches}")
    print(f"  Failed: {failed_batches}")
    print(f"  Total investors processed: {total_investors_processed}")
    if is_sequential and total_delay_time > 0:
        print(f"  Total post-completion delay time: {total_delay_time:.1f}s")
    if not is_sequential and total_stagger_time > 0:
        print(f"  Total intra-batch stagger time: {total_stagger_time:.1f}s")
    print()
    
    if is_sequential:
        return successful_batches, failed_batches, batch_timings, total_investors_processed, total_delay_time
    else:
        return successful_batches, failed_batches, batch_timings, total_investors_processed, total_stagger_time


async def main_batch_investor_scoring(input_csv: Optional[str] = None,
                                      output_csv: Optional[str] = None,
                                      batch_folder: Optional[str] = None,
                                      start_row: int = 0,
                                      end_row: Optional[int] = None,
                                      batch_size: int = 10,
                                      delay: int = 60,
                                      stop_on_failure: bool = True,
                                      run_batches_in_parallel: bool = True,
                                      batch_parallelism_limit: int = 2,
                                      intra_parallel_batch_delay: int = 0,
                                      run_ids: Optional[List[str]] = None,
                                      poll_limit: Optional[int] = None):
    """
    Main function for batch processing investor lead scoring workflow.
    
    Args:
        input_csv: Path to input CSV file with investor lead data
        output_csv: Path to output CSV file for results  
        batch_folder: Folder to store individual batch result files
        start_row: Starting row index for processing (0-based, excluding header)
        end_row: Ending row index for processing (0-based, exclusive)
        batch_size: Number of investors to process in each batch
        delay: Delay in seconds between consecutive batch workflows (only for sequential processing)
        stop_on_failure: If True, stop processing and throw exception on batch failure
        run_batches_in_parallel: If True, run batches concurrently instead of sequentially
        batch_parallelism_limit: Maximum number of concurrent batches when parallel processing is enabled
        intra_parallel_batch_delay: Delay in seconds between batch starts in parallel mode.
                                   Each batch waits (batch_num - 1) * intra_parallel_batch_delay seconds
                                   before starting. Default: 0 (no staggering)
        run_ids: List of existing workflow run IDs to poll (if provided, skips job submission)
        poll_limit: Maximum number of run IDs to poll (only used with run_ids)
    """
    # Check if we're in run-IDs polling mode
    if run_ids:
        print(f"--- Starting Run IDs Polling Mode ---")
        print(f"Configuration:")
        print(f"  Output CSV: {output_csv if output_csv else 'No output file'}")
        print(f"  Batch folder: {batch_folder}")
        print(f"  Run IDs provided: {len(run_ids)}")
        if poll_limit:
            print(f"  Poll limit: {poll_limit}")
        print()
        
        overall_start_time = time.time()
        
        # Create batch results folder
        batch_folder_path = Path(batch_folder)
        batch_folder_path.mkdir(parents=True, exist_ok=True)
        print(f"Batch results will be stored in: {batch_folder_path.resolve()}")
        print()
        
        # Poll existing run IDs
        successful_polls, failed_polls, poll_timings, total_investors_processed = await poll_existing_run_ids(
            run_ids=run_ids,
            batch_folder_path=batch_folder_path,
            output_csv=output_csv,
            poll_limit=poll_limit
        )
        
        # Combine all batch results
        print(f"{'='*60}")
        print(f"COMBINING BATCH RESULTS")
        print(f"{'='*60}")
        
        try:
            combine_existing_batch_files(batch_folder, output_csv)
            print(f"✓ All batch results combined into: {output_csv}")
            print(f"✓ Individual batch files preserved in: {batch_folder_path}")
        except Exception as e:
            logger.error(f"Error combining batch results: {str(e)}")
            print(f"✗ Error combining batch results: {str(e)}")
        
        # Final statistics
        overall_end_time = time.time()
        total_execution_time = overall_end_time - overall_start_time
        
        print(f"\n{'='*60}")
        print(f"RUN IDs POLLING COMPLETE")
        print(f"{'='*60}")
        print(f"Total run IDs polled: {len(run_ids) if not poll_limit else min(len(run_ids), poll_limit)}")
        print(f"Successful polls: {successful_polls}")
        print(f"Failed polls: {failed_polls}")
        print(f"Total investors retrieved: {total_investors_processed}")
        print(f"Total execution time: {total_execution_time:.1f} seconds ({total_execution_time/60:.1f} minutes)")
        print(f"Final combined results saved to: {output_csv}")
        print(f"{'='*60}")
        
        return successful_polls, failed_polls
    
    # Normal batch processing mode
    print(f"--- Starting Batch Investor Lead Scoring Workflow ---")
    print(f"Configuration:")
    print(f"  Input CSV: {input_csv if input_csv else 'Using default test data'}")
    print(f"  Output CSV: {output_csv if output_csv else 'No output file'}")
    print(f"  Batch folder: {batch_folder}")
    print(f"  Row range: {start_row} to {end_row if end_row else 'end'}")
    print(f"  Batch size: {batch_size}")
    print(f"  Parallel processing: {run_batches_in_parallel}")
    if run_batches_in_parallel:
        print(f"  Max concurrent batches: {batch_parallelism_limit}")
        if intra_parallel_batch_delay > 0:
            print(f"  Intra-batch start delay: {intra_parallel_batch_delay} seconds")
    else:
        print(f"  Inter-batch delay: {delay} seconds")
    print(f"  Stop on failure: {stop_on_failure}")
    print()
    
    overall_start_time = time.time()
    
    # Handle case where no CSV is provided (use default test data)
    if not input_csv or not Path(input_csv).exists():
        if input_csv:
            print(f"CSV file not found: {input_csv}")
        print("Using default test inputs (single workflow run)")
        
        test_name = "Investor Lead Scoring"
        workflow_start_time = time.time()
        final_run_status_obj, final_run_outputs = await run_single_workflow(
            input_data=TEST_INPUTS,
            test_name=test_name
        )
        workflow_end_time = time.time()
        
        if output_csv and final_run_outputs:
            print(f"Saving results to: {output_csv}")
            save_results_to_csv(final_run_outputs, output_csv)
            print(f"Results saved successfully to: {output_csv}")
        
        overall_duration = time.time() - overall_start_time
        workflow_duration = workflow_end_time - workflow_start_time
        investors_processed = len(final_run_outputs.get('scored_investors', [])) if final_run_outputs else 0
        
        print(f"\n{'='*60}")
        print(f"TIMING STATISTICS - SINGLE RUN")
        print(f"{'='*60}")
        print(f"Total execution time: {overall_duration:.1f} seconds ({overall_duration/60:.1f} minutes)")
        print(f"Workflow execution time: {workflow_duration:.1f} seconds ({workflow_duration/60:.1f} minutes)")
        print(f"Investors processed: {investors_processed}")
        if investors_processed > 0:
            print(f"Average time per investor: {workflow_duration/investors_processed:.1f} seconds")
        print(f"{'='*60}")
        
        return final_run_status_obj, final_run_outputs
    
    # Calculate batch processing parameters
    df = pd.read_csv(input_csv)
    total_rows = len(df)
    actual_end_row = min(end_row if end_row is not None else total_rows, total_rows)
    total_investors_to_process = actual_end_row - start_row
    total_batches = (total_investors_to_process + batch_size - 1) // batch_size
    
    print(f"Batch Processing Plan:")
    print(f"  Total rows in CSV: {total_rows}")
    print(f"  Processing rows {start_row} to {actual_end_row-1} ({total_investors_to_process} investors)")
    print(f"  Batch size: {batch_size}")
    print(f"  Total batches: {total_batches}")
    print()
    
    # Create batch results folder
    batch_folder_path = Path(batch_folder)
    batch_folder_path.mkdir(parents=True, exist_ok=True)
    print(f"Batch results will be stored in: {batch_folder_path.resolve()}")
    
    batch_output_files = []
    batch_processing_start_time = time.time()
    
    # Run batches
    if run_batches_in_parallel:
        print(f"🚀 Running {total_batches} batches in PARALLEL mode (max {batch_parallelism_limit} concurrent)")
        if intra_parallel_batch_delay > 0:
            print(f"   Staggering batch starts with {intra_parallel_batch_delay}s delay between each")
        batch_result = await run_batches_unified(
            input_csv=input_csv,
            batch_folder_path=batch_folder_path,
            output_csv=output_csv,
            start_row=start_row,
            actual_end_row=actual_end_row,
            batch_size=batch_size,
            total_batches=total_batches,
            batch_parallelism_limit=batch_parallelism_limit,
            stop_on_failure=stop_on_failure,
            batch_output_files=batch_output_files,
            delay=0,
            overall_start_time=overall_start_time,
            intra_parallel_batch_delay=intra_parallel_batch_delay
        )
        successful_batches, failed_batches, batch_timings, total_investors_processed, total_stagger_time = batch_result
        total_delay_time = 0.0
    else:
        print(f"🐌 Running {total_batches} batches in SEQUENTIAL mode")
        batch_result = await run_batches_unified(
            input_csv=input_csv,
            batch_folder_path=batch_folder_path,
            output_csv=output_csv,
            start_row=start_row,
            actual_end_row=actual_end_row,
            batch_size=batch_size,
            total_batches=total_batches,
            batch_parallelism_limit=1,
            stop_on_failure=stop_on_failure,
            batch_output_files=batch_output_files,
            delay=delay,
            overall_start_time=overall_start_time,
            intra_parallel_batch_delay=0  # Not used in sequential mode
        )
        successful_batches, failed_batches, batch_timings, total_investors_processed, total_delay_time = batch_result
        total_stagger_time = 0.0
    
    batch_processing_end_time = time.time()
    total_batch_processing_time = batch_processing_end_time - batch_processing_start_time
    pure_workflow_time = total_batch_processing_time - total_delay_time - total_stagger_time
    
    # Combine all batch results
    print(f"{'='*60}")
    print(f"COMBINING BATCH RESULTS")
    print(f"{'='*60}")
    
    try:
        combine_batch_results(batch_output_files, output_csv)
        print(f"✓ All batch results combined into: {output_csv}")
        print(f"✓ Individual batch files preserved in: {batch_folder_path}")
    except Exception as e:
        logger.error(f"Error combining batch results: {str(e)}")
        print(f"✗ Error combining batch results: {str(e)}")
    
    # Final statistics
    overall_end_time = time.time()
    total_execution_time = overall_end_time - overall_start_time
    
    successful_batch_timings = [b for b in batch_timings if b['investors_processed'] > 0]
    
    print(f"\n{'='*60}")
    print(f"BATCH PROCESSING COMPLETE")
    print(f"{'='*60}")
    print(f"Total batches: {total_batches}")
    print(f"Successful batches: {successful_batches}")
    print(f"Failed batches: {failed_batches}")
    print(f"Final merged results saved to: {output_csv}")
    
    print(f"\n{'='*60}")
    print(f"COMPREHENSIVE TIMING STATISTICS")
    print(f"{'='*60}")
    
    print(f"📊 OVERALL PERFORMANCE:")
    print(f"  Total execution time: {total_execution_time:.1f} seconds ({total_execution_time/60:.1f} minutes)")
    print(f"  Pure workflow time: {pure_workflow_time:.1f} seconds ({pure_workflow_time/60:.1f} minutes)")
    print(f"  Total investors processed: {total_investors_processed}")
    
    if total_investors_processed > 0:
        print(f"  Pure workflow time per investor: {pure_workflow_time/total_investors_processed:.1f} seconds")
        print(f"  Workflow throughput: {total_investors_processed/(pure_workflow_time/3600):.1f} investors/hour")
    
    if successful_batch_timings:
        batch_durations = [b['duration'] for b in successful_batch_timings]
        print(f"\n⏱️  BATCH PERFORMANCE:")
        print(f"  Average batch duration: {sum(batch_durations)/len(batch_durations):.1f} seconds")
        print(f"  Fastest batch: {min(batch_durations):.1f} seconds")
        print(f"  Slowest batch: {max(batch_durations):.1f} seconds")
    
    print(f"{'='*60}")
    
    return successful_batches, failed_batches


def parse_arguments():
    """Parse command line arguments for CSV input/output functionality."""
    parser = argparse.ArgumentParser(
        description="Investor Lead Scoring Workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default hardcoded test data
  python wf_runner.py
  
  # Process entire CSV file in batches
  python wf_runner.py --input investors.csv --output results.csv
  
  # Process specific row range with custom batch size
  python wf_runner.py --input investors.csv --output results.csv --start-row 0 --end-row 50 --batch-size 10
  
  # Run batches in parallel with custom concurrency (8 concurrent batches)
  python wf_runner.py --input investors.csv --output results.csv --batch-parallelism-limit 8
  
  # Parallel execution with staggered starts (60 seconds between batch starts)
  python wf_runner.py --input investors.csv --output results.csv --batch-parallelism-limit 4 --intra-parallel-batch-delay 60
  
  # Run batches sequentially
  python wf_runner.py --input investors.csv --output results.csv --sequential
  
  # Poll existing workflow run IDs (no job submission, just retrieve results)
  python wf_runner.py --output results.csv --run-ids abc123 def456 ghi789
  
  # Poll run IDs with limit (only first 5)
  python wf_runner.py --output results.csv --run-ids abc123 def456 ghi789 jkl012 mno345 --poll-limit 5
  
  # Combine existing batch files (handles both regular and run-ID batches)
  python wf_runner.py --output results.csv --combine-only

Note: Deep research workflows are time-intensive. Expect 2-3 minutes per investor lead.
      Use --intra-parallel-batch-delay to stagger batch starts for API rate limiting.
      Use --run-ids to retrieve results from already-running workflows without submitting new jobs.
        """
    )

    current_file_dir = Path(__file__).parent
    default_input_csv = str(current_file_dir / "Outreach Box - needs scoring.csv")  # Outreach Box - Investor Pool (OVERALL).csv  sample_investors.csv
    default_output_csv = str(current_file_dir / "results.csv")
    default_batch_folder = str(current_file_dir / "batch_results")
    default_start_row = 0
    default_end_row = None
    default_batch_size = 75
    default_delay = 15
    default_stop_on_failure = True
    default_combine_batch_files_only_mode = False
    default_run_batches_in_parallel = True
    default_batch_parallelism_limit = 3
    default_intra_parallel_batch_delay = 120

    default_run_ids = None  # ["ad6e4374-4edc-421f-a9ee-4a4ee68aa895", ]
    default_poll_limit = None
    
    parser.add_argument('--input', '--input-csv', type=str, default=default_input_csv,
                       help=f'Path to input CSV file (default: {default_input_csv})')
    parser.add_argument('--output', '--output-csv', type=str, default=default_output_csv,
                       help=f'Path to output CSV file (default: {default_output_csv})')
    parser.add_argument('--start-row', type=int, default=default_start_row,
                       help='Starting row index (0-based, excluding header). Default: 0')
    parser.add_argument('--end-row', type=int, default=default_end_row,
                       help='Ending row index (0-based, exclusive). Default: process all rows')
    parser.add_argument('--batch-size', type=int, default=default_batch_size,
                       help='Number of investors per batch. Default: 10')
    parser.add_argument('--batch-folder', type=str, default=default_batch_folder,
                       help=f'Folder for batch result files (default: {default_batch_folder})')
    parser.add_argument('--delay', type=int, default=default_delay,
                       help='Delay in seconds between batches (sequential mode). Default: 60')
    parser.add_argument('--stop-on-failure', action='store_true', default=default_stop_on_failure,
                       help='Stop if any batch fails. Default: True')
    parser.add_argument('--continue-on-failure', action='store_false', dest='stop_on_failure',
                       help='Continue even if batches fail')
    parser.add_argument('--combine-only', action='store_true', default=default_combine_batch_files_only_mode,
                       help='Only combine existing batch files. Default: False')
    parser.add_argument('--run-batches-in-parallel', action='store_true', default=default_run_batches_in_parallel,
                       help='Run batches in parallel. Default: True')
    parser.add_argument('--sequential', action='store_false', dest='run_batches_in_parallel',
                       help='Run batches sequentially')
    parser.add_argument('--batch-parallelism-limit', type=int, default=default_batch_parallelism_limit,
                       help='Max concurrent batches (parallel mode). Default: 2')
    parser.add_argument('--intra-parallel-batch-delay', type=int, default=default_intra_parallel_batch_delay,
                       help='Delay in seconds between batch starts in parallel mode. Each batch waits (batch_num - 1) * delay before starting. Default: 0 (no staggering)')
    parser.add_argument('--run-ids', type=str, nargs='+', default=default_run_ids,
                       help='List of existing workflow run IDs to poll. When provided, skips job submission and only polls these run IDs. Example: --run-ids abc123 def456 ghi789')
    parser.add_argument('--poll-limit', type=int, default=default_poll_limit,
                       help='Maximum number of run IDs to poll (only used with --run-ids). Default: None (poll all provided run IDs)')
    
    args = parser.parse_args()
    
    # Validate arguments
    input_path = Path(args.input).resolve()
    args.input = str(input_path)
    args.output = str(Path(args.output).resolve())
    
    # Validation checks (skip some if in run-ids mode)
    if not args.run_ids:
        if args.start_row < 0:
            parser.error("Start row must be >= 0")
        if args.end_row is not None and args.end_row <= args.start_row:
            parser.error("End row must be greater than start row")
        if args.batch_size <= 0:
            parser.error("Batch size must be greater than 0")
        if args.batch_parallelism_limit <= 0:
            parser.error("Batch parallelism limit must be greater than 0")
        if args.intra_parallel_batch_delay < 0:
            parser.error("Intra-parallel batch delay must be >= 0")
    
    # Validate run-ids specific arguments
    if args.poll_limit is not None and args.poll_limit <= 0:
        parser.error("Poll limit must be greater than 0")
    if args.poll_limit is not None and not args.run_ids:
        parser.error("--poll-limit can only be used with --run-ids")
    
    return args


if __name__ == "__main__":
    print("="*80)
    print("Investor Lead Scoring Workflow")
    print("="*80)
    logging.basicConfig(level=logging.INFO)
    
    args = parse_arguments()
    
    # Handle combine-only mode
    if args.combine_only:
        print("🔄 COMBINE-ONLY MODE: Combining existing batch files...")
        combine_existing_batch_files(args.batch_folder, args.output)
        print("✅ Combine-only operation completed.")
        sys.exit(0)
    
    asyncio.run(main_batch_investor_scoring(
        input_csv=args.input,
        output_csv=args.output,
        batch_folder=args.batch_folder,
        start_row=args.start_row,
        end_row=args.end_row,
        batch_size=args.batch_size,
        delay=args.delay,
        stop_on_failure=args.stop_on_failure,
        run_batches_in_parallel=args.run_batches_in_parallel,
        batch_parallelism_limit=args.batch_parallelism_limit,
        intra_parallel_batch_delay=args.intra_parallel_batch_delay,
        run_ids=args.run_ids,
        poll_limit=args.poll_limit
    ))

