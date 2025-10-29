#!/usr/bin/env python3
"""
Investor Personalization Line Generation Runner

Runs the investor personalization workflow on a CSV to generate tailored outreach lines.

Usage:
    python personalization_runner.py --input investors.csv --output personalized.csv [options]

Examples:
    # Process entire CSV with all columns as context (default: 3 concurrent batches)
    python personalization_runner.py --input investors.csv --output personalized.csv

    # Only include specific columns in context
    python personalization_runner.py --input investors.csv --output personalized.csv --allow-cols "investor_name,firm_name,recent_investments,investment_thesis"

    # Exclude specific columns from context
    python personalization_runner.py --input investors.csv --output personalized.csv --deny-cols "email,phone,internal_notes"

    # Process specific rows
    python personalization_runner.py --input investors.csv --output personalized.csv --start-row 0 --end-row 50

    # Run batches sequentially
    python personalization_runner.py --input investors.csv --output personalized.csv --sequential

    # Increase parallel processing (5 concurrent batches)
    python personalization_runner.py --input investors.csv --output personalized.csv --batch-parallelism-limit 5

    # Combine existing batch files without running workflows
    python personalization_runner.py --output personalized.csv --combine-only

Note:
    - row_index column is always excluded from context (used for tracking)
    - deny_list takes precedence over allow_list
    - If allow_list is specified, only those columns are included (unless denied)
"""

import asyncio
import csv
import argparse
import sys
import time
import pandas as pd
from pathlib import Path
from typing import List, Optional, Dict, Any, Set
import logging
import io
import contextlib

# Import test execution logic
from kiwi_client.test_run_workflow_client import run_workflow_test
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

# Import workflow schema
from kiwi_client.workflows.active.investor.investor_lead_scoring_sandbox.wf_investor_personalization import workflow_graph_schema

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def build_context_from_row(
    row: pd.Series,
    allow_list: Optional[Set[str]] = None,
    deny_list: Optional[Set[str]] = None
) -> str:
    """
    Build markdown-formatted context from a pandas row.
    
    Args:
        row: Pandas Series representing a row from the CSV
        allow_list: If provided, only include these columns (unless in deny_list)
        deny_list: Exclude these columns (takes precedence over allow_list)
    
    Returns:
        Markdown-formatted context string
    
    Column filtering logic:
    1. Always exclude 'row_index'
    2. If column is in deny_list → exclude
    3. If allow_list is specified and column NOT in allow_list → exclude
    4. Otherwise → include
    """
    context_lines = []
    
    # Always exclude row_index from context
    excluded_keys = {'row_index'}
    
    for col_name, value in row.items():
        # Skip row_index
        if col_name in excluded_keys:
            continue
        
        # Apply deny_list (takes precedence)
        if deny_list and col_name in deny_list:
            continue
        
        # Apply allow_list (if specified, only include allowed columns)
        if allow_list and col_name not in allow_list:
            continue
        
        # Skip NaN values
        if pd.isna(value):
            continue
        
        # Convert value to string and strip whitespace
        value_str = str(value).strip()
        
        # Skip empty strings
        if not value_str:
            continue
        
        # Add to context in markdown format
        context_lines.append(f"# {col_name}:")
        context_lines.append(value_str)
        context_lines.append("")  # Blank line between fields
    
    return "\n".join(context_lines)


def load_investors_for_personalization(
    csv_file: str,
    start_row: int = 0,
    end_row: Optional[int] = None,
    allow_cols: Optional[str] = None,
    deny_cols: Optional[str] = None
) -> List[Dict]:
    """
    Load investor rows from CSV for personalization.
    
    Args:
        csv_file: Path to CSV file
        start_row: Starting row index (0-based, after header)
        end_row: Ending row index (exclusive)
        allow_cols: Comma-separated list of columns to include in context
        deny_cols: Comma-separated list of columns to exclude from context
    
    Returns:
        List of investor dictionaries with row_index and context
    """
    logger.info(f"Loading data from {csv_file}...")

    df = pd.read_csv(csv_file)

    # Ensure row_index column exists
    if 'row_index' not in df.columns:
        logger.info("row_index column not found - adding sequential index")
        df['row_index'] = range(len(df))

    # Apply row range filtering
    if end_row is not None:
        df = df.iloc[start_row:end_row]
    else:
        df = df.iloc[start_row:]

    logger.info(f"Loaded {len(df)} rows from CSV file: {csv_file}")
    logger.info(f"Row range: {start_row} to {end_row if end_row else 'end'}")

    # Parse allow/deny lists
    allow_list = set(allow_cols.split(',')) if allow_cols else None
    deny_list = set(deny_cols.split(',')) if deny_cols else None

    # Log column filtering configuration
    if allow_list:
        logger.info(f"Allow list: {sorted(allow_list)}")
    if deny_list:
        logger.info(f"Deny list: {sorted(deny_list)}")
    
    # Calculate which columns will actually be used
    available_cols = set(df.columns) - {'row_index'}
    if deny_list:
        available_cols = available_cols - deny_list
    if allow_list:
        available_cols = available_cols & allow_list
    logger.info(f"Context will include {len(available_cols)} columns: {sorted(available_cols)}")

    investors = []
    for _, row in df.iterrows():
        # Build context from row using allow/deny lists
        context = build_context_from_row(row, allow_list, deny_list)
        
        investor = {
            'row_index': str(row['row_index']),
            'context': context
        }
        investors.append(investor)

    logger.info(f"Prepared {len(investors)} investors for personalization")
    return investors


async def run_single_workflow(input_data: Dict[str, Any], test_name: str) -> tuple:
    """
    Run a single workflow instance with given input data.

    Args:
        input_data: Input data for the workflow
        test_name: Name for this workflow test

    Returns:
        Tuple of (final_run_status_obj, final_run_outputs)
    """
    logger.info(f"Starting {test_name}...")

    # Capture stdout to prevent verbose output
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
                stream_intermediate_results=False,
                dump_artifacts=False,
                poll_interval_sec=5,
                timeout_sec=600  # 10 minutes timeout per batch
            )
    except Exception as e:
        logger.error(f"Workflow execution failed: {str(e)}")
        raise

    status_str = str(final_run_status_obj.status) if final_run_status_obj else "None"
    logger.info(f"{test_name} completed with status: {status_str}")

    return final_run_status_obj, final_run_outputs


def save_batch_results_to_csv(final_run_outputs: Dict[str, Any], batch_output_file: str) -> int:
    """
    Save batch personalization results to CSV file.
    
    Handles NaN values by replacing them with appropriate defaults before saving.
    Outputs both Founder A and Founder B perspectives.
    """
    personalized_investors = final_run_outputs.get('personalized_investors', [])

    if not personalized_investors:
        logger.warning("No personalized investors found in workflow outputs")
        return 0

    # Helper to safely get value from dict, converting NaN to default
    def safe_get(data: Dict, key: str, default: Any) -> Any:
        """Get value from dict, handling NaN values."""
        val = data.get(key, default)
        # Check if value is NaN (works for float NaN)
        if isinstance(val, float) and pd.isna(val):
            return default
        return val

    # Prepare CSV rows - now with dual perspective
    # Note: LLM node outputs include both structured_output and passthrough_data
    csv_rows = []
    for investor in personalized_investors:
        # Extract structured output (nested inside the result)
        structured_output = safe_get(investor, 'personalization_result', {})  # personalization_result  structured_output
        
        row = {
            'row_index': safe_get(investor, 'row_index', ''),
            'personalization_line_founder_a': safe_get(structured_output, 'personalization_line_founder_a', ''),
            'personalization_reason_founder_a': safe_get(structured_output, 'personalization_reason_founder_a', ''),
            'personalization_line_founder_b': safe_get(structured_output, 'personalization_line_founder_b', ''),
            'personalization_reason_founder_b': safe_get(structured_output, 'personalization_reason_founder_b', ''),
        }
        csv_rows.append(row)

    # Write to CSV (fillna to handle any remaining NaN values)
    df = pd.DataFrame(csv_rows)
    df.fillna('', inplace=True)  # Replace any remaining NaN with empty string
    df.to_csv(batch_output_file, index=False)

    logger.info(f"Saved {len(csv_rows)} personalized results to: {batch_output_file}")
    return len(csv_rows)


async def run_single_batch(
    investors_batch: List[Dict],
    batch_num: int,
    total_batches: int,
    batch_output_file: str,
    founder_company_context: str = ""
) -> Dict[str, Any]:
    """Run a single batch of investors through the personalization workflow."""

    batch_start_time = time.time()

    print(f"\n{'='*60}")
    print(f"BATCH {batch_num}/{total_batches}")
    print(f"{'='*60}")
    print(f"Processing {len(investors_batch)} investors")
    print(f"Output: {batch_output_file}")

    try:
        # Run workflow
        test_name = f"personalization_batch_{batch_num}"
        workflow_input = {
            "investors_to_personalize": investors_batch,
            "founder_company_context": founder_company_context
        }

        final_status, final_outputs = await run_single_workflow(workflow_input, test_name)

        # Save results
        investors_processed = 0
        if final_outputs:
            investors_processed = save_batch_results_to_csv(final_outputs, batch_output_file)

        batch_duration = time.time() - batch_start_time
        success = final_status and final_status.status == WorkflowRunStatus.COMPLETED

        print(f"✅ Batch {batch_num} completed in {batch_duration:.1f}s - {investors_processed} investors personalized")

        return {
            'batch_num': batch_num,
            'success': success,
            'duration': batch_duration,
            'investors_processed': investors_processed,
            'avg_time_per_investor': batch_duration / investors_processed if investors_processed > 0 else 0
        }

    except Exception as e:
        batch_duration = time.time() - batch_start_time
        print(f"❌ Batch {batch_num} failed: {str(e)}")

        return {
            'batch_num': batch_num,
            'success': False,
            'duration': batch_duration,
            'investors_processed': 0,
            'avg_time_per_investor': 0
        }


async def run_batches_parallel(
    investors: List[Dict],
    batch_size: int,
    batch_parallelism_limit: int,
    batch_output_files: List[str],
    founder_company_context: str = ""
):
    """Run batches in parallel with concurrency limit."""

    total_batches = (len(investors) + batch_size - 1) // batch_size

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(batch_parallelism_limit)

    async def run_batch_with_semaphore(batch_start: int, batch_end: int, batch_num: int, batch_file: str):
        async with semaphore:
            batch = investors[batch_start:batch_end]
            return await run_single_batch(batch, batch_num, total_batches, batch_file, founder_company_context)

    # Create batch tasks
    batch_tasks = []
    for batch_num in range(1, total_batches + 1):
        batch_start = (batch_num - 1) * batch_size
        batch_end = min(batch_start + batch_size, len(investors))
        batch_file = batch_output_files[batch_num - 1]

        task = run_batch_with_semaphore(batch_start, batch_end, batch_num, batch_file)
        batch_tasks.append(task)

    print(f"🚀 Running {total_batches} batches in PARALLEL mode (max {batch_parallelism_limit} concurrent)")

    # Execute all batches
    batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

    # Process results
    successful_batches = sum(1 for r in batch_results if isinstance(r, dict) and r['success'])
    failed_batches = sum(1 for r in batch_results if isinstance(r, Exception) or (isinstance(r, dict) and not r['success']))
    total_investors_processed = sum(r['investors_processed'] for r in batch_results if isinstance(r, dict))

    return successful_batches, failed_batches, batch_results, total_investors_processed


async def run_batches_sequential(
    investors: List[Dict],
    batch_size: int,
    batch_output_files: List[str],
    delay: int = 60,
    founder_company_context: str = ""
):
    """Run batches sequentially with optional delay between batches."""

    total_batches = (len(investors) + batch_size - 1) // batch_size

    print(f"🐌 Running {total_batches} batches in SEQUENTIAL mode")

    batch_results = []
    for batch_num in range(1, total_batches + 1):
        batch_start = (batch_num - 1) * batch_size
        batch_end = min(batch_start + batch_size, len(investors))
        batch = investors[batch_start:batch_end]
        batch_file = batch_output_files[batch_num - 1]

        result = await run_single_batch(batch, batch_num, total_batches, batch_file, founder_company_context)
        batch_results.append(result)

        # Add delay between batches (except after last batch)
        if delay > 0 and batch_num < total_batches:
            print(f"⏳ Waiting {delay} seconds before next batch...")
            await asyncio.sleep(delay)

    successful_batches = sum(1 for r in batch_results if r['success'])
    failed_batches = sum(1 for r in batch_results if not r['success'])
    total_investors_processed = sum(r['investors_processed'] for r in batch_results)

    return successful_batches, failed_batches, batch_results, total_investors_processed


def combine_batch_results(batch_output_files: List[str], final_output_csv: str) -> None:
    """Combine results from multiple batch CSV files into a single output file."""

    logger.info(f"Combining {len(batch_output_files)} batch result files into: {final_output_csv}")

    combined_rows = []

    for i, batch_file in enumerate(batch_output_files):
        if not Path(batch_file).exists():
            logger.warning(f"Batch file does not exist: {batch_file}")
            continue

        try:
            batch_df = pd.read_csv(batch_file)
            logger.info(f"Loaded {len(batch_df)} results from batch file {i+1}: {batch_file}")
            batch_rows = batch_df.to_dict('records')
            combined_rows.extend(batch_rows)
        except Exception as e:
            logger.error(f"Error reading batch file {batch_file}: {str(e)}")
            continue

    if combined_rows:
        # Write combined results
        combined_df = pd.DataFrame(combined_rows)
        combined_df.to_csv(final_output_csv, index=False)

        logger.info(f"Successfully combined {len(combined_rows)} total results into: {final_output_csv}")
    else:
        logger.warning("No batch results to combine")


def load_default_founder_company_context() -> str:
    """
    Load the default founder/company context from Low-Fidelity Memo.md.
    
    Returns:
        Memo content as string, or empty string if file not found
    """
    try:
        current_file_dir = Path(__file__).parent
        memo_path = current_file_dir / "Low-Fidelity Memo.md"
        
        if memo_path.exists():
            with open(memo_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            logger.warning(f"Low-Fidelity Memo.md not found at: {memo_path}")
            return ""
    except Exception as e:
        logger.error(f"Error loading Low-Fidelity Memo: {str(e)}")
        return ""


async def main():
    # Configuration defaults
    current_file_dir = Path(__file__).parent
    default_input_csv = str(current_file_dir / "Outreach Box - Personalization_intake_ Angels.csv")
    default_output_csv = str(current_file_dir / "personalized_investors_Angels_100.csv")
    default_start_row = 0
    default_end_row = None
    default_batch_size = 100
    default_batch_folder = str(current_file_dir / "personalization_batches")
    default_delay = 60
    default_stop_on_failure = False
    default_combine_batch_files_only_mode = False
    default_run_batches_in_parallel = True
    default_batch_parallelism_limit = 1
    default_allow_cols = None
    default_deny_cols = None
    
    # Load default founder/company context from Low-Fidelity Memo
    default_founder_company_context = load_default_founder_company_context()

    parser = argparse.ArgumentParser(
        description='Run investor personalization line generation workflow',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process entire CSV with all columns as context
  python personalization_runner.py --input investors.csv --output personalized.csv
  
  # Only include specific columns in context
  python personalization_runner.py --input investors.csv --output personalized.csv --allow-cols "investor_name,firm_name,recent_investments"
  
  # Exclude specific columns from context
  python personalization_runner.py --input investors.csv --output personalized.csv --deny-cols "email,phone,internal_notes"
  
  # Process specific rows in parallel
  python personalization_runner.py --input investors.csv --output personalized.csv --start-row 0 --end-row 100 --batch-parallelism-limit 5
        """
    )
    
    parser.add_argument('--input', '--input-csv', type=str, default=default_input_csv,
                       help=f'Path to input CSV file (default: {default_input_csv})')
    parser.add_argument('--output', '--output-csv', type=str, default=default_output_csv,
                       help=f'Path to output CSV file (default: {default_output_csv})')
    parser.add_argument('--start-row', type=int, default=default_start_row,
                       help='Starting row index (0-based, excluding header). Default: 0')
    parser.add_argument('--end-row', type=int, default=default_end_row,
                       help='Ending row index (0-based, exclusive). Default: process all rows')
    parser.add_argument('--batch-size', type=int, default=default_batch_size,
                       help='Number of investors per batch. Default: 200')
    parser.add_argument('--batch-folder', type=str, default=default_batch_folder,
                       help=f'Folder for batch result files (default: {default_batch_folder})')
    parser.add_argument('--delay', type=int, default=default_delay,
                       help='Delay in seconds between batches (sequential mode). Default: 60')
    parser.add_argument('--stop-on-failure', action='store_true', default=default_stop_on_failure,
                       help='Stop if any batch fails. Default: False')
    parser.add_argument('--continue-on-failure', action='store_false', dest='stop_on_failure',
                       help='Continue even if batches fail')
    parser.add_argument('--combine-only', action='store_true', default=default_combine_batch_files_only_mode,
                       help='Only combine existing batch files. Default: False')
    parser.add_argument('--run-batches-in-parallel', action='store_true', default=default_run_batches_in_parallel,
                       help='Run batches in parallel. Default: True')
    parser.add_argument('--sequential', action='store_false', dest='run_batches_in_parallel',
                       help='Run batches sequentially')
    parser.add_argument('--batch-parallelism-limit', type=int, default=default_batch_parallelism_limit,
                       help='Max concurrent batches (parallel mode). Default: 1')
    parser.add_argument('--allow-cols', type=str, default=default_allow_cols,
                       help='Comma-separated list of columns to include in context (if specified, only these columns used)')
    parser.add_argument('--deny-cols', type=str, default=default_deny_cols,
                       help='Comma-separated list of columns to exclude from context (takes precedence over allow-cols)')
    parser.add_argument('--founder-company-context', type=str, default=default_founder_company_context,
                       help='Additional context about founders/company (e.g., recent traction, product updates). Default: content from Low-Fidelity Memo.md')

    args = parser.parse_args()

    # Resolve paths
    args.input = str(Path(args.input).resolve())
    args.output = str(Path(args.output).resolve())

    print("=" * 80)
    print("🚀 INVESTOR PERSONALIZATION LINE GENERATION WORKFLOW")
    print("=" * 80)

    # Create batch folder
    batch_folder_path = Path(args.batch_folder)
    batch_folder_path.mkdir(parents=True, exist_ok=True)

    overall_start_time = time.time()

    # Combine-only mode: skip workflow execution
    if args.combine_only:
        print("\n📂 COMBINE-ONLY MODE: Combining existing batch files...")
        batch_files = sorted(batch_folder_path.glob("batch_*.csv"))

        if not batch_files:
            print(f"❌ No batch files found in {batch_folder_path}")
            return

        combine_batch_results([str(f) for f in batch_files], args.output)
        print(f"✅ Combined results saved to: {args.output}")

        return

    # Load investors
    investors = load_investors_for_personalization(
        args.input,
        args.start_row,
        args.end_row,
        args.allow_cols,
        args.deny_cols
    )

    if not investors:
        print("❌ No investors to process")
        return

    # Calculate batches
    total_batches = (len(investors) + args.batch_size - 1) // args.batch_size
    batch_output_files = [
        str(batch_folder_path / f"batch_{i+1:03d}.csv")
        for i in range(total_batches)
    ]

    print(f"\n📊 Processing Configuration:")
    print(f"  Input file: {args.input}")
    print(f"  Output file: {args.output}")
    print(f"  Total investors: {len(investors)}")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Total batches: {total_batches}")
    print(f"  Parallel mode: {'Yes' if args.run_batches_in_parallel else 'No'}")
    if args.run_batches_in_parallel:
        print(f"  Max concurrent batches: {args.batch_parallelism_limit}")
    else:
        print(f"  Delay between batches: {args.delay}s")
    
    # Log column filtering
    if args.allow_cols:
        print(f"  Column allow list: {args.allow_cols}")
    if args.deny_cols:
        print(f"  Column deny list: {args.deny_cols}")
    
    # Log founder/company context
    if args.founder_company_context:
        context_preview = args.founder_company_context[:150].replace('\n', ' ')
        print(f"  Founder/company context: {context_preview}..." if len(args.founder_company_context) > 150 else f"  Founder/company context: {context_preview}")
        print(f"  Context length: {len(args.founder_company_context)} characters")
    else:
        print(f"  Founder/company context: None (Low-Fidelity Memo.md not found)")

    # Run batches
    batch_processing_start_time = time.time()

    if args.run_batches_in_parallel:
        successful, failed, results, total_processed = await run_batches_parallel(
            investors, args.batch_size, args.batch_parallelism_limit, batch_output_files, args.founder_company_context
        )
    else:
        successful, failed, results, total_processed = await run_batches_sequential(
            investors, args.batch_size, batch_output_files, args.delay, args.founder_company_context
        )

    batch_processing_end_time = time.time()
    total_batch_processing_time = batch_processing_end_time - batch_processing_start_time

    # Combine batch results
    print(f"\n{'='*60}")
    print(f"COMBINING BATCH RESULTS")
    print(f"{'='*60}")

    combine_batch_results(batch_output_files, args.output)
    print(f"✓ All batch results combined into: {args.output}")
    print(f"✓ Individual batch files preserved in: {batch_folder_path}")

    print(f"\n✅ PERSONALIZATION COMPLETE - Results saved to: {args.output}")

    # Final statistics
    overall_end_time = time.time()
    total_execution_time = overall_end_time - overall_start_time

    print(f"\n{'='*60}")
    print(f"BATCH PROCESSING COMPLETE")
    print(f"{'='*60}")
    print(f"Total batches: {total_batches}")
    print(f"Successful batches: {successful}")
    print(f"Failed batches: {failed}")
    print(f"Total investors processed: {total_processed}")
    print(f"Total execution time: {total_execution_time:.1f}s ({total_execution_time/60:.1f} minutes)")

    if total_processed > 0:
        print(f"Average time per investor: {total_batch_processing_time/total_processed:.1f}s")

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

