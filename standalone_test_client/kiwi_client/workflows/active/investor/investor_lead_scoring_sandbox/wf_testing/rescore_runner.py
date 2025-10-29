#!/usr/bin/env python3
"""
Investor Check Size Rescoring Runner

Runs the investor check size rescoring workflow on results.csv to update scores based on new rules.

Usage:
    python rescore_runner.py --input results_with_index.csv --output rescored_results.csv [options]

Examples:
    # Process entire CSV in parallel (default: 3 concurrent batches)
    python rescore_runner.py --input results_with_index.csv --output results.csv

    # Process specific rows
    python rescore_runner.py --input results_with_index.csv --output results.csv --start-row 0 --end-row 50

    # Run batches sequentially
    python rescore_runner.py --input results_with_index.csv --output results.csv --sequential

    # Increase parallel processing (5 concurrent batches)
    python rescore_runner.py --input results_with_index.csv --output results.csv --batch-parallelism-limit 5

    # Combine existing batch files without running workflows
    python rescore_runner.py --output results.csv --combine-only
"""

import asyncio
import csv
import argparse
import sys
import time
import pandas as pd
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging
import io
import contextlib

# Import test execution logic
from kiwi_client.test_run_workflow_client import run_workflow_test
from kiwi_client.schemas.workflow_constants import WorkflowRunStatus

# Import workflow schema
from kiwi_client.workflows.active.investor.investor_lead_scoring_sandbox.wf_investor_rescoring import workflow_graph_schema

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def load_investors_for_rescoring(csv_file: str, start_row: int = 0, end_row: Optional[int] = None) -> List[Dict]:
    """Load investor rows from CSV for rescoring."""
    logger.info(f"Loading data from {csv_file}...")

    df = pd.read_csv(csv_file)

    # Apply row range filtering
    if end_row is not None:
        df = df.iloc[start_row:end_row]
    else:
        df = df.iloc[start_row:]

    logger.info(f"Loaded {len(df)} rows from CSV file: {csv_file}")
    logger.info(f"Row range: {start_row} to {end_row if end_row else 'end'}")

    investors = []
    for _, row in df.iterrows():
        # Helper function to safely get string values from pandas row (handles NaN)
        def safe_get_str(row_data, key: str, default: str = '') -> str:
            """Get string value from pandas row, handling NaN values."""
            val = row_data.get(key, default)
            return default if pd.isna(val) else str(val)
        
        # Helper function to safely get int values from pandas row (handles NaN)
        def safe_get_int(row_data, key: str, default: int = 0) -> int:
            """Get int value from pandas row, handling NaN values."""
            val = row_data.get(key, default)
            return default if pd.isna(val) else int(val)
        
        investor = {
            'row_index': str(row['row_index']),
            'investor_name': f"{safe_get_str(row, 'input_first_name')} {safe_get_str(row, 'input_last_name')}".strip(),
            'typical_check_size': safe_get_str(row, 'typical_check_size'),
            'old_check_size_points': safe_get_int(row, 'check_size_points'),
            'old_total_score': safe_get_int(row, 'total_score'),
            'is_disqualified': safe_get_str(row, 'is_disqualified', 'false').lower() == 'true',
        }
        investors.append(investor)

    logger.info(f"Prepared {len(investors)} investors for rescoring")
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
    Save batch rescoring results to CSV file.
    
    Handles NaN values by replacing them with appropriate defaults before saving.
    """
    rescored_investors = final_run_outputs.get('rescored_investors', [])

    if not rescored_investors:
        logger.warning("No rescored investors found in workflow outputs")
        return 0

    # Helper to safely get value from dict, converting NaN to default
    def safe_get(data: Dict, key: str, default: Any) -> Any:
        """Get value from dict, handling NaN values."""
        val = data.get(key, default)
        # Check if value is NaN (works for float NaN)
        if isinstance(val, float) and pd.isna(val):
            return default
        return val

    # Prepare CSV rows
    csv_rows = []
    for investor in rescored_investors:
        row = {
            'row_index': safe_get(investor, 'row_index', ''),
            'investor_name': safe_get(investor, 'investor_name', ''),
            'typical_check_size': safe_get(investor, 'typical_check_size', ''),
            'old_check_size_points': safe_get(investor, 'old_check_size_points', 0),
            'new_check_size_points': safe_get(investor, 'new_check_size_points', 0),
            'points_difference': safe_get(investor, 'points_difference', 0),
            'old_total_score': safe_get(investor, 'old_total_score', 0),
            'new_total_score': safe_get(investor, 'new_total_score', 0),
            'new_score_tier': safe_get(investor, 'new_score_tier', ''),
            'new_recommended_action': safe_get(investor, 'new_recommended_action', ''),
            # 'scoring_reasoning': safe_get(investor, 'scoring_reasoning', ''),
            'parsed_typical_amount': safe_get(investor, 'parsed_typical_amount', ''),
        }
        csv_rows.append(row)

    # Write to CSV (fillna to handle any remaining NaN values)
    df = pd.DataFrame(csv_rows)
    df.fillna('', inplace=True)  # Replace any remaining NaN with empty string
    df.to_csv(batch_output_file, index=False)

    logger.info(f"Saved {len(csv_rows)} rescored results to: {batch_output_file}")
    return len(csv_rows)


async def run_single_batch(
    investors_batch: List[Dict],
    batch_num: int,
    total_batches: int,
    batch_output_file: str
) -> Dict[str, Any]:
    """Run a single batch of investors through the rescoring workflow."""

    batch_start_time = time.time()

    print(f"\n{'='*60}")
    print(f"BATCH {batch_num}/{total_batches}")
    print(f"{'='*60}")
    print(f"Processing {len(investors_batch)} investors")
    print(f"Output: {batch_output_file}")

    try:
        # Run workflow
        test_name = f"rescore_batch_{batch_num}"
        workflow_input = {"investors_to_rescore": investors_batch}

        final_status, final_outputs = await run_single_workflow(workflow_input, test_name)

        # Save results
        investors_processed = 0
        if final_outputs:
            investors_processed = save_batch_results_to_csv(final_outputs, batch_output_file)

        batch_duration = time.time() - batch_start_time
        success = final_status and final_status.status == WorkflowRunStatus.COMPLETED

        print(f"✅ Batch {batch_num} completed in {batch_duration:.1f}s - {investors_processed} investors rescored")

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
    batch_output_files: List[str]
):
    """Run batches in parallel with concurrency limit."""

    total_batches = (len(investors) + batch_size - 1) // batch_size

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(batch_parallelism_limit)

    async def run_batch_with_semaphore(batch_start: int, batch_end: int, batch_num: int, batch_file: str):
        async with semaphore:
            batch = investors[batch_start:batch_end]
            return await run_single_batch(batch, batch_num, total_batches, batch_file)

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
    delay: int = 60
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

        result = await run_single_batch(batch, batch_num, total_batches, batch_file)
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

        # Log summary statistics
        score_increases = sum(1 for row in combined_rows if row.get('points_difference', 0) > 0)
        score_decreases = sum(1 for row in combined_rows if row.get('points_difference', 0) < 0)
        score_unchanged = sum(1 for row in combined_rows if row.get('points_difference', 0) == 0)

        logger.info(f"Score Summary: {score_increases} increases, {score_decreases} decreases, {score_unchanged} unchanged")
    else:
        logger.warning("No batch results to combine")


def merge_rescored_results(original_file: str, rescored_file: str, output_file: str):
    """
    Merge rescored results back into original CSV, overwriting updated columns.
    
    Handles NaN values by replacing them with appropriate defaults.
    """

    logger.info(f"Merging rescored results back into {original_file}...")

    # Load rescored results indexed by row_index
    rescored_df = pd.read_csv(rescored_file)
    # Fill NaN values in rescored data before processing
    rescored_df.fillna('', inplace=True)
    rescored_data = {str(row['row_index']): row for _, row in rescored_df.iterrows()}

    # Read original file and update columns
    original_df = pd.read_csv(original_file)

    for idx, row in original_df.iterrows():
        row_index = str(row['row_index'])

        if row_index in rescored_data:
            rescored = rescored_data[row_index]
            # Safely update fields, handling any NaN values
            original_df.at[idx, 'check_size_points'] = rescored.get('new_check_size_points', 0)
            original_df.at[idx, 'total_score'] = rescored.get('new_total_score', 0)
            original_df.at[idx, 'score_tier'] = rescored.get('new_score_tier', '')
            original_df.at[idx, 'recommended_action'] = rescored.get('new_recommended_action', '')

    # Write merged results
    original_df.to_csv(output_file, index=False)

    logger.info(f"Merged and saved to {output_file}")
    logger.info(f"Updated {len(rescored_data)} rows")


async def main():
    # Configuration defaults
    current_file_dir = Path(__file__).parent
    default_input_csv = str(current_file_dir / "results_with_index.csv")
    default_output_csv = str(current_file_dir / "results_rescored.csv")
    default_start_row = 0
    default_end_row = None
    default_batch_size = 200
    default_batch_folder = str(current_file_dir / "rescore_batches")
    default_delay = 60
    default_stop_on_failure = False
    default_combine_batch_files_only_mode = False
    default_merge_back = False
    default_run_batches_in_parallel = True
    default_batch_parallelism_limit = 1

    parser = argparse.ArgumentParser(description='Run investor check size rescoring workflow')
    parser.add_argument('--input', '--input-csv', type=str, default=default_input_csv,
                       help=f'Path to input CSV file (default: {default_input_csv})')
    parser.add_argument('--output', '--output-csv', type=str, default=default_output_csv,
                       help=f'Path to output CSV file (default: {default_output_csv})')
    parser.add_argument('--start-row', type=int, default=default_start_row,
                       help='Starting row index (0-based, excluding header). Default: 0')
    parser.add_argument('--end-row', type=int, default=default_end_row,
                       help='Ending row index (0-based, exclusive). Default: process all rows')
    parser.add_argument('--batch-size', type=int, default=default_batch_size,
                       help='Number of investors per batch. Default: 20')
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
                       help='Max concurrent batches (parallel mode). Default: 3')
    parser.add_argument('--merge-back', action='store_true', default=default_merge_back,
                       help='Merge results back into input file (overwrites check_size_points, total_score, score_tier, recommended_action)')

    args = parser.parse_args()

    # Resolve paths
    args.input = str(Path(args.input).resolve())
    args.output = str(Path(args.output).resolve())

    print("=" * 80)
    print("🚀 INVESTOR CHECK SIZE RESCORING WORKFLOW")
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
    
    if args.merge_back:
        final_output = args.input.replace('_with_index.csv', '.csv')
        merge_rescored_results(args.input, args.output, final_output)
        print(f"✅ Merged back into: {final_output}")
        return

    # Load investors
    investors = load_investors_for_rescoring(args.input, args.start_row, args.end_row)

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

    # Run batches
    batch_processing_start_time = time.time()

    if args.run_batches_in_parallel:
        successful, failed, results, total_processed = await run_batches_parallel(
            investors, args.batch_size, args.batch_parallelism_limit, batch_output_files
        )
    else:
        successful, failed, results, total_processed = await run_batches_sequential(
            investors, args.batch_size, batch_output_files, args.delay
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

    # Merge back if requested
    if args.merge_back:
        final_output = args.input.replace('_with_index.csv', '.csv')
        merge_rescored_results(args.input, args.output, final_output)
        print(f"\n✅ RESCORING COMPLETE - Merged back into: {final_output}")
    else:
        print(f"\n✅ RESCORING COMPLETE - Results saved to: {args.output}")
        print(f"\n💡 To merge back into original, run with --merge-back flag")

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
