# CSV Join Script - Usage Examples

## New Features

### 1. Base Directory Support
- By default, the script uses its own directory as the base for relative paths
- You can override this with `--base-dir` to work with files in a different directory
- Absolute paths always work as-is, ignoring the base directory

### 2. Default Configuration
- All arguments have sensible defaults (similar to `wf_runner.py`)
- Easy to modify defaults at the top of `parse_arguments()` function

---

## Basic Examples

### 1. Join files in the script's directory
```bash
python join_sheets.py --left results.csv --right batch_results/batch_001.csv --keys id
```

### 2. Join files from a different directory
```bash
python join_sheets.py \
  --base-dir ../wf_testing \
  --left results.csv \
  --right old_results.csv \
  --keys id,firm_id
```

### 3. Use absolute paths (ignores base-dir)
```bash
python join_sheets.py \
  --left /full/path/to/file1.csv \
  --right /full/path/to/file2.csv \
  --keys email
```

---

## Advanced Examples

### 4. Inner join with right values taking precedence
```bash
python join_sheets.py \
  --left batch_results/batch_001.csv \
  --right batch_results/batch_002.csv \
  --keys linkedin_url \
  --join-type inner \
  --conflict-strategy replace_right
```

### 5. Keep both versions of conflicting columns
```bash
python join_sheets.py \
  --left results_old.csv \
  --right results_new.csv \
  --keys input_first_name,input_last_name \
  --conflict-strategy keep_both \
  --output comparison_results.csv
```

### 6. Multiple join keys with custom output
```bash
python join_sheets.py \
  --left investors.csv \
  --right enriched_data.csv \
  --keys first_name,last_name,firm_company \
  --output merged_investors.csv
```

---

## Investor Lead Scoring Specific Examples

### 7. Join two batch results files
```bash
# Files are in the same directory as the script
python join_sheets.py \
  --left batch_001_rows_0-9.csv \
  --right batch_002_rows_10-19.csv \
  --keys input_linkedin_url \
  --conflict-strategy replace_right \
  --output combined_batches_001_002.csv
```

### 8. Join main results with additional enrichment data
```bash
python join_sheets.py \
  --left results.csv \
  --right ../enrichment/linkedin_posts.csv \
  --keys input_linkedin_url \
  --join-type left \
  --output results_with_posts.csv
```

### 9. Join using run ID batch files
```bash
python join_sheets.py \
  --base-dir batch_results \
  --left batch_runid_abc123.csv \
  --right batch_runid_def456.csv \
  --keys input_first_name,input_last_name \
  --output combined_runids.csv
```

---

## Join Type Explanations

### Left Join (default)
- Keep all rows from left CSV
- Add matching data from right CSV
- Non-matching rows from right are excluded

### Right Join
- Keep all rows from right CSV
- Add matching data from left CSV
- Non-matching rows from left are excluded

### Inner Join
- Keep only rows that match in BOTH CSVs
- Most restrictive option

### Outer Join
- Keep all rows from BOTH CSVs
- Fills with empty values where no match exists
- Most inclusive option

---

## Conflict Strategy Explanations

### replace_left (default)
- When columns exist in both CSVs, keep the LEFT value
- Conservative approach - preserves original left data

### replace_right
- When columns exist in both CSVs, keep the RIGHT value
- Falls back to left value if right is NaN/empty
- Good for updating/enriching left data with right data

### keep_both
- When columns exist in both CSVs, keep BOTH
- Renames to: `column_from_left` and `column_from_right`
- Useful for comparison and analysis

---

## Tips & Tricks

1. **View help**: `python join_sheets.py --help`

2. **Check defaults**: Look at the top of `parse_arguments()` in the script

3. **Output location**: 
   - If no `--output` specified, generates timestamped file in left CSV's directory
   - Format: `joined_<left>_<right>_<timestamp>.csv`

4. **Testing joins**: Use `head` command to preview results
   ```bash
   python join_sheets.py --left a.csv --right b.csv --keys id
   head -n 20 joined_a_b_20250116_143022.csv
   ```

5. **Multiple keys**: Separate with commas (no spaces)
   ```bash
   --keys "id,name,company"  # ✅ Good
   --keys "id, name, company"  # ❌ Keys will have spaces
   ```

