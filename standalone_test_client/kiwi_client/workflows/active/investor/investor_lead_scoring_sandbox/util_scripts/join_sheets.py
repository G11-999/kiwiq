"""
CSV Join Utility Script

This script joins two CSV files (left and right) based on specified key fields.
It provides configurable options for handling column conflicts and join types.

Key Features:
- Supports multiple join types (left, right, inner, outer)
- Configurable column conflict resolution (replace_left, replace_right, keep_both)
- Intelligent column ordering for investor workflows (enabled by default)
- Preserves data types during join operations
- Outputs to CSV with configurable filename

Column Ordering (Default):
1. All input_* columns (alphabetically sorted)
2. total_score
3. recommended_action
4. All personalization_* columns (founder_a & founder_b variants)
5. Remaining columns (alphabetically sorted)

Usage:
    python join_sheets.py --left input1.csv --right input2.csv --keys id,name
    
    # With advanced options
    python join_sheets.py \
        --left input1.csv \
        --right input2.csv \
        --keys email \
        --join-type inner \
        --conflict-strategy replace_right \
        --output joined_output.csv
    
    # Disable column ordering
    python join_sheets.py \
        --left input1.csv \
        --right input2.csv \
        --keys id \
        --no-column-ordering
"""

import argparse
import sys
from pathlib import Path
from typing import List, Literal, Optional

import pandas as pd


# Type aliases for better code clarity
JoinType = Literal["left", "right", "inner", "outer"]
ConflictStrategy = Literal["replace_left", "replace_right", "keep_both"]


class CSVJoiner:
    """
    Handles joining of two CSV files with configurable options.
    
    This class provides a flexible interface for joining CSV files with various
    strategies for handling column conflicts and different join types.
    """
    
    def __init__(
        self,
        left_path: str,
        right_path: str,
        join_keys: List[str],
        join_type: JoinType = "left",
        conflict_strategy: ConflictStrategy = "replace_left",
        output_path: Optional[str] = None,
        enable_column_ordering: bool = True
    ):
        """
        Initialize the CSV joiner.
        
        Args:
            left_path: Path to the left CSV file
            right_path: Path to the right CSV file
            join_keys: List of column names to use as join keys
            join_type: Type of join to perform (default: "left")
            conflict_strategy: How to handle conflicting column names (default: "replace_left")
            output_path: Path for output file (default: auto-generated)
            enable_column_ordering: Whether to reorder columns in standard order (default: True)
        
        Design Decision:
            - Using pandas for robust CSV handling and efficient join operations
            - Default to left join to preserve all left table records
            - Default to replace_left to maintain left table values (conservative approach)
            - Default to enable column ordering for investor workflow consistency
        """
        self.left_path = Path(left_path)
        self.right_path = Path(right_path)
        self.join_keys = join_keys
        self.join_type = join_type
        self.conflict_strategy = conflict_strategy
        self.output_path = output_path or self._generate_output_path()
        self.enable_column_ordering = enable_column_ordering
        
        # Validate inputs
        self._validate_inputs()
    
    def _validate_inputs(self) -> None:
        """
        Validate that input files exist and are accessible.
        
        Raises:
            FileNotFoundError: If either CSV file doesn't exist
        """
        if not self.left_path.exists():
            raise FileNotFoundError(f"Left CSV file not found: {self.left_path}")
        if not self.right_path.exists():
            raise FileNotFoundError(f"Right CSV file not found: {self.right_path}")
    
    def _generate_output_path(self) -> str:
        """
        Generate a default output filename based on input files.
        
        Returns:
            Default output path string
        
        Design Decision:
            - Include timestamp to avoid overwriting previous joins
            - Use descriptive naming to indicate join operation
            - Place in same directory as left CSV file for convenience
        """
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"joined_{self.left_path.stem}_{self.right_path.stem}_{timestamp}.csv"
        
        # Place output in the same directory as the left CSV file
        output_path = self.left_path.parent / output_filename
        return str(output_path)
    
    def _load_csv(self, path: Path) -> pd.DataFrame:
        """
        Load CSV file with proper error handling.
        
        Args:
            path: Path to CSV file
        
        Returns:
            Loaded DataFrame
        
        Caveat: Automatically detects encoding; may need adjustment for special characters
        """
        try:
            # Try UTF-8 first (most common)
            df = pd.read_csv(path, encoding='utf-8')
        except UnicodeDecodeError:
            # Fallback to ISO-8859-1 for older files
            print(f"Warning: UTF-8 decoding failed for {path}, trying ISO-8859-1")
            df = pd.read_csv(path, encoding='iso-8859-1')
        
        print(f"Loaded {path.name}: {len(df)} rows, {len(df.columns)} columns")
        return df
    
    def _validate_join_keys(
        self, 
        left_df: pd.DataFrame, 
        right_df: pd.DataFrame
    ) -> None:
        """
        Validate that join keys exist in both DataFrames.
        
        Args:
            left_df: Left DataFrame
            right_df: Right DataFrame
        
        Raises:
            ValueError: If join keys are missing from either DataFrame
        """
        left_cols = set(left_df.columns)
        right_cols = set(right_df.columns)
        
        for key in self.join_keys:
            if key not in left_cols:
                raise ValueError(f"Join key '{key}' not found in left CSV. Available: {list(left_cols)}")
            if key not in right_cols:
                raise ValueError(f"Join key '{key}' not found in right CSV. Available: {list(right_cols)}")
    
    def _identify_conflicting_columns(
        self, 
        left_df: pd.DataFrame, 
        right_df: pd.DataFrame
    ) -> List[str]:
        """
        Identify columns that exist in both DataFrames (excluding join keys).
        
        Args:
            left_df: Left DataFrame
            right_df: Right DataFrame
        
        Returns:
            List of conflicting column names
        
        Design Decision:
            - Exclude join keys from conflicts as they're used for joining
            - These columns need special handling based on conflict_strategy
        """
        left_cols = set(left_df.columns) - set(self.join_keys)
        right_cols = set(right_df.columns) - set(self.join_keys)
        conflicting = list(left_cols & right_cols)
        
        if conflicting:
            print(f"Found {len(conflicting)} conflicting columns: {conflicting}")
        
        return conflicting
    
    def _prepare_dataframes_for_join(
        self,
        left_df: pd.DataFrame,
        right_df: pd.DataFrame,
        conflicting_cols: List[str]
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Prepare DataFrames based on conflict resolution strategy.
        
        Args:
            left_df: Left DataFrame
            right_df: Right DataFrame
            conflicting_cols: List of columns that exist in both DataFrames
        
        Returns:
            Tuple of (prepared_left_df, prepared_right_df)
        
        Design Decision:
            - Add suffixes during join to track origin of columns
            - Strategy determines which columns to keep after join
        """
        # For pandas merge, we'll use suffixes to track which side columns come from
        # The actual resolution happens after the join
        return left_df, right_df
    
    def _apply_conflict_strategy(
        self,
        merged_df: pd.DataFrame,
        conflicting_cols: List[str]
    ) -> pd.DataFrame:
        """
        Apply conflict resolution strategy to merged DataFrame.
        
        Args:
            merged_df: DataFrame after join (with _x and _y suffixes for conflicts)
            conflicting_cols: List of original conflicting column names
        
        Returns:
            DataFrame with conflicts resolved
        
        Caveat: 
            - pandas adds _x (left) and _y (right) suffixes to conflicting columns
            - We remove these suffixes based on the chosen strategy
        """
        result_df = merged_df.copy()
        
        for col in conflicting_cols:
            left_col = f"{col}_x"
            right_col = f"{col}_y"
            
            # Check if suffixed columns exist (they will after merge)
            if left_col in result_df.columns and right_col in result_df.columns:
                
                if self.conflict_strategy == "replace_left":
                    # Keep left value (drop right)
                    result_df[col] = result_df[left_col]
                    result_df = result_df.drop(columns=[left_col, right_col])
                    
                elif self.conflict_strategy == "replace_right":
                    # Keep right value (drop left), but preserve left if right is NaN
                    result_df[col] = result_df[right_col].fillna(result_df[left_col])
                    result_df = result_df.drop(columns=[left_col, right_col])
                    
                elif self.conflict_strategy == "keep_both":
                    # Rename to indicate source
                    result_df = result_df.rename(columns={
                        left_col: f"{col}_from_left",
                        right_col: f"{col}_from_right"
                    })
        
        return result_df
    
    def _reorder_columns(
        self,
        df: pd.DataFrame,
        enable_ordering: bool = True
    ) -> pd.DataFrame:
        """
        Reorder columns in a standard, logical order for investor workflows.
        
        Args:
            df: DataFrame to reorder
            enable_ordering: Whether to apply column ordering (default: True)
        
        Returns:
            DataFrame with reordered columns
        
        Default Column Order:
            1. All input_* columns (alphabetically sorted)
            2. total_score
            3. recommended_action  
            4. All personalization_* columns (in specific order):
               - personalization_line_founder_a
               - personalization_reason_founder_a
               - personalization_line_founder_b
               - personalization_reason_founder_b
            5. Rest of columns (alphabetically sorted)
        
        Design Decision:
            - Prioritize input columns (original data) first
            - Show scoring/decision columns prominently after inputs
            - Group personalization columns together for easy review
            - Sort remaining columns alphabetically for consistency
            - Missing columns are gracefully skipped (no errors)
        """
        if not enable_ordering:
            return df
        
        all_columns = list(df.columns)
        
        # Categorize columns
        input_cols = sorted([col for col in all_columns if col.startswith('input_')])
        
        # Priority columns (in specific order)
        priority_cols = ['total_score', 'recommended_action']
        priority_cols_present = [col for col in priority_cols if col in all_columns]
        
        # Personalization columns (in specific order)
        personalization_cols = [
            'personalization_line_founder_a',
            'personalization_reason_founder_a', 
            'personalization_line_founder_b',
            'personalization_reason_founder_b'
        ]
        personalization_cols_present = [col for col in personalization_cols if col in all_columns]
        
        # Collect remaining columns (not in any of the above categories)
        used_cols = set(input_cols + priority_cols_present + personalization_cols_present)
        remaining_cols = sorted([col for col in all_columns if col not in used_cols])
        
        # Build final column order
        ordered_columns = (
            input_cols + 
            priority_cols_present + 
            personalization_cols_present + 
            remaining_cols
        )
        
        # Log reordering summary
        print("\nColumn Ordering:")
        print(f"  Input columns: {len(input_cols)}")
        print(f"  Priority columns: {len(priority_cols_present)}")
        print(f"  Personalization columns: {len(personalization_cols_present)}")
        print(f"  Remaining columns: {len(remaining_cols)}")
        print(f"  Total columns: {len(ordered_columns)}")
        
        # Reorder DataFrame
        return df[ordered_columns]
    
    def join(self) -> pd.DataFrame:
        """
        Perform the join operation with configured settings.
        
        Returns:
            Joined DataFrame
        
        Key Steps:
            1. Load both CSV files
            2. Validate join keys exist
            3. Identify conflicting columns
            4. Perform join operation
            5. Apply conflict resolution strategy
            6. Return final DataFrame
        """
        print(f"\n{'='*60}")
        print(f"Starting CSV Join Operation")
        print(f"{'='*60}")
        
        # Load CSV files
        print("\nStep 1: Loading CSV files...")
        left_df = self._load_csv(self.left_path)
        right_df = self._load_csv(self.right_path)
        
        # Validate join keys
        print("\nStep 2: Validating join keys...")
        self._validate_join_keys(left_df, right_df)
        print(f"Join keys validated: {self.join_keys}")
        
        # Identify conflicting columns
        print("\nStep 3: Identifying conflicting columns...")
        conflicting_cols = self._identify_conflicting_columns(left_df, right_df)
        
        # Perform join
        print(f"\nStep 4: Performing {self.join_type} join...")
        merged_df = pd.merge(
            left_df,
            right_df,
            on=self.join_keys,
            how=self.join_type,
            suffixes=('_x', '_y')
        )
        print(f"Join complete: {len(merged_df)} rows, {len(merged_df.columns)} columns")
        
        # Apply conflict resolution
        if conflicting_cols:
            print(f"\nStep 5: Applying conflict resolution strategy: {self.conflict_strategy}...")
            result_df = self._apply_conflict_strategy(merged_df, conflicting_cols)
        else:
            print("\nStep 5: No conflicting columns, skipping resolution...")
            result_df = merged_df
        
        # Apply column ordering
        if self.enable_column_ordering:
            print(f"\nStep 6: Applying column ordering...")
            result_df = self._reorder_columns(result_df, enable_ordering=True)
        else:
            print(f"\nStep 6: Column ordering disabled, preserving original order...")
        
        print(f"\nFinal result: {len(result_df)} rows, {len(result_df.columns)} columns")
        print(f"First 10 columns: {list(result_df.columns)[:10]}{'...' if len(result_df.columns) > 10 else ''}")
        
        return result_df
    
    def save(self, df: pd.DataFrame) -> None:
        """
        Save the joined DataFrame to CSV.
        
        Args:
            df: DataFrame to save
        
        Design Decision:
            - Use UTF-8 encoding for maximum compatibility
            - Include index=False to avoid extra index column
            - Show full output path for user reference
        """
        output_path = Path(self.output_path)
        df.to_csv(output_path, index=False, encoding='utf-8')
        print(f"\n{'='*60}")
        print(f"✓ Successfully saved to: {output_path.absolute()}")
        print(f"{'='*60}\n")
    
    def run(self) -> pd.DataFrame:
        """
        Execute the full join and save pipeline.
        
        Returns:
            The joined DataFrame
        """
        joined_df = self.join()
        self.save(joined_df)
        return joined_df


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.
    
    Returns:
        Parsed arguments namespace
    """
    # Define default values at the top for easy configuration
    current_file_dir = Path(__file__).parent
    default_base_dir = str(current_file_dir)
    default_left_csv = "Outreach Box - Personalization_intake_ Angels.csv"  # No default - user must specify
    default_right_csv = "personalized_investors_Angels_100.csv"  # No default - user must specify
    default_keys = "row_index"
    # "input_first_name,input_last_name,input_title,input_firm_company,input_firm_id,input_investor_type,input_investor_role_detail,input_relationship_status,input_linkedin_url,input_twitter_url,input_crunchbase_url,input_email,input_investment_criteria,input_notes,input_source_sheets"  # No default - user must specify  # comma separated str!
    default_join_type = 'right'
    default_conflict_strategy = 'replace_left'
    default_output = "Angels personalized batch 1.csv"  # Auto-generated if not specified
    default_enable_column_ordering = True
    
    parser = argparse.ArgumentParser(
        description="Join two CSV files based on specified key fields",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic join with single key (files in current directory)
  python join_sheets.py --left customers.csv --right orders.csv --keys customer_id

  # Join with multiple keys
  python join_sheets.py --left sales.csv --right targets.csv --keys year,quarter

  # Join files from a different directory
  python join_sheets.py --base-dir /path/to/data --left input1.csv --right input2.csv --keys id

  # Inner join with right values taking precedence
  python join_sheets.py --left a.csv --right b.csv --keys id \\
      --join-type inner --conflict-strategy replace_right

  # Keep both versions of conflicting columns
  python join_sheets.py --left a.csv --right b.csv --keys id \\
      --conflict-strategy keep_both --output merged.csv
  
  # Disable column ordering (preserve original join order)
  python join_sheets.py --left a.csv --right b.csv --keys id --no-column-ordering
  
  # Use absolute paths to ignore base directory
  python join_sheets.py --left /full/path/to/file1.csv --right /full/path/to/file2.csv --keys id

Note: 
  - Relative paths are resolved relative to --base-dir (default: current script directory)
  - Absolute paths are used as-is, ignoring --base-dir
  - Default base directory: {default_base_dir}
  - Column ordering is ENABLED by default (input_*, total_score, recommended_action, personalization_*, rest)
        """
    )
    
    parser.add_argument(
        '--base-dir',
        type=str,
        default=default_base_dir,
        help=f'Base directory for resolving relative paths (default: {default_base_dir})'
    )
    
    parser.add_argument(
        '--left',
        type=str,
        default=default_left_csv,
        required=default_left_csv is None,
        help='Path to the left CSV file (relative to base-dir or absolute)'
    )
    
    parser.add_argument(
        '--right',
        type=str,
        default=default_right_csv,
        required=default_right_csv is None,
        help='Path to the right CSV file (relative to base-dir or absolute)'
    )
    
    parser.add_argument(
        '--keys',
        type=str,
        default=default_keys,
        required=default_keys is None,
        help='Comma-separated list of column names to use as join keys (e.g., "id,year")'
    )
    
    parser.add_argument(
        '--join-type',
        choices=['left', 'right', 'inner', 'outer'],
        default=default_join_type,
        help=f'Type of join to perform (default: {default_join_type})'
    )
    
    parser.add_argument(
        '--conflict-strategy',
        choices=['replace_left', 'replace_right', 'keep_both'],
        default=default_conflict_strategy,
        help=f'How to handle conflicting column names (default: {default_conflict_strategy})'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default=default_output,
        help='Output CSV filename (relative to base-dir or absolute, default: auto-generated with timestamp)'
    )
    
    parser.add_argument(
        '--enable-column-ordering',
        action='store_true',
        default=default_enable_column_ordering,
        dest='enable_column_ordering',
        help='Enable standard column ordering (input_*, total_score, recommended_action, personalization_*, rest). Default: True'
    )
    
    parser.add_argument(
        '--no-column-ordering',
        action='store_false',
        dest='enable_column_ordering',
        help='Disable column ordering (preserve original column order from join)'
    )
    
    args = parser.parse_args()
    
    # Resolve paths relative to base directory
    base_dir = Path(args.base_dir).resolve()
    
    # Helper function to resolve path relative to base_dir
    def resolve_path(path_str: str) -> str:
        """
        Resolve a path string relative to base_dir.
        If path is absolute, use it as-is. Otherwise, resolve relative to base_dir.
        """
        if not path_str:
            return path_str
        
        path = Path(path_str)
        if path.is_absolute():
            # Use absolute path as-is
            return str(path)
        else:
            # Resolve relative to base_dir
            return str(base_dir / path)
    
    # Resolve all path arguments
    args.left = resolve_path(args.left)
    args.right = resolve_path(args.right)
    
    # For output, only resolve if it's provided (otherwise let CSVJoiner auto-generate in current dir)
    if args.output:
        args.output = resolve_path(args.output)
    
    # Validate arguments
    if not args.left:
        parser.error("--left is required")
    if not args.right:
        parser.error("--right is required")
    if not args.keys:
        parser.error("--keys is required")
    
    return args


def main() -> int:
    """
    Main entry point for the script.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        args = parse_arguments()
        
        # Display configuration summary
        print(f"{'='*60}")
        print(f"CSV JOIN OPERATION")
        print(f"{'='*60}")
        print(f"Configuration:")
        print(f"  Base directory: {Path(args.left).parent}")
        print(f"  Left CSV: {Path(args.left).name}")
        print(f"  Right CSV: {Path(args.right).name}")
        print(f"  Join keys: {args.keys}")
        print(f"  Join type: {args.join_type}")
        print(f"  Conflict strategy: {args.conflict_strategy}")
        print(f"  Column ordering: {'Enabled' if args.enable_column_ordering else 'Disabled'}")
        if args.output:
            print(f"  Output file: {Path(args.output).name}")
        else:
            print(f"  Output file: Auto-generated with timestamp")
        print()
        
        # Parse join keys
        join_keys = [key.strip() for key in args.keys.split(',')]
        
        # Create joiner and run
        joiner = CSVJoiner(
            left_path=args.left,
            right_path=args.right,
            join_keys=join_keys,
            join_type=args.join_type,
            conflict_strategy=args.conflict_strategy,
            output_path=args.output,
            enable_column_ordering=args.enable_column_ordering
        )
        
        joiner.run()
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
