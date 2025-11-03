import pandas as pd
import numpy as np
import os
import glob

# The script is now configured to iterate over a range of team files (e.g., team-2 to team-22).
# The file paths will be constructed dynamically in the main execution block.

def clean_and_impute_branch_names(input_path, output_path):
    """
    Reads a CSV, imputes missing branch_name values based on the same pr_id,
    and saves the cleaned data to a new CSV.
    
    FIX: Ensures 'pr_id' is converted to a consistent integer type for robust grouping.
    """
    # Ensure the output directory exists
    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        print(f"Creating output directory: {output_dir}")
        os.makedirs(output_dir)

    if not os.path.exists(input_path):
        print(f"Error: Input file not found at {input_path}. Skipping.")
        return

    print(f"Loading data from {input_path}...")
    
    try:
        # Load the CSV.
        df = pd.read_csv(input_path)
    except pd.errors.EmptyDataError:
        print(f"Warning: File {input_path} is empty. Skipping.")
        return
    except Exception as e:
        print(f"An error occurred reading {input_path}: {e}")
        return

    # Check for critical columns early
    if 'pr_id' not in df.columns:
        print("Error: 'pr_id' column not found. Cannot proceed with imputation.")
        return
    if 'branch_name' not in df.columns:
        print("Error: 'branch_name' column not found. Cannot proceed with imputation.")
        return

    # --- FIX IMPLEMENTATION: Convert pr_id to integer (Int64 handles NaNs) ---
    try:
        # Convert pr_id to nullable integer type (Int64) for robust grouping and storage
        # This safely converts '283.0' to 283 and handles any potential NaNs
        df['pr_id'] = pd.to_numeric(df['pr_id'], errors='coerce').astype(pd.Int64Dtype())
    except Exception as e:
        print(f"Warning: Could not convert 'pr_id' to integer. Proceeding with original type. Error: {e}")
        # If conversion fails, the column remains its original type (likely float)
        
    # 1. Standardize missing values
    # Replace any empty strings in 'branch_name' with actual NaN values
    df['branch_name'] = df['branch_name'].replace('', np.nan)
    initial_missing = df['branch_name'].isna().sum()

    print(f"Found {initial_missing} records with missing branch_name initially.")

    # 2. Create the Imputation Map
    # Find all rows that HAVE a valid branch name and a valid pr_id
    valid_branches = df.dropna(subset=['branch_name', 'pr_id'])

    # For each unique pr_id, select the FIRST associated non-empty branch_name.
    branch_map = valid_branches.drop_duplicates(subset=['pr_id'], keep='first').set_index('pr_id')['branch_name']

    # 3. Apply Imputation
    # Fill any missing 'branch_name' values using the lookup map
    df['branch_name'].fillna(df['pr_id'].map(branch_map), inplace=True)

    # Calculate how many values were filled
    filled_count = initial_missing - df['branch_name'].isna().sum()

    # 4. Save the Result
    try:
        df.to_csv(output_path, index=False)
        print("-" * 50)
        print(f"Cleaning complete for {input_path}.")
        print(f"-> Successfully imputed {filled_count} missing branch names based on matching pr_id.")
        print(f"-> The cleaned data is saved to: {output_path}")
    except Exception as e:
        print(f"An error occurred writing to {output_path}: {e}")


# --- Execution ---
if __name__ == "__main__":
    # Define the range of teams to process (2 to 22 inclusive)
    START_TEAM = 2
    END_TEAM = 22

    # --- MODIFIED TEMPLATES ---
    INPUT_DIR = "../data/csv/"
    OUTPUT_DIR = "../data/csv/clean/"
    INPUT_FILE_TEMPLATE = os.path.join(INPUT_DIR, "code_structure_branching_labels_year-long-project-team-{team_id}_anonymized.csv")
    
    # The output file name will be the input file name (before adding the directory)
    OUTPUT_FILE_TEMPLATE = os.path.join(OUTPUT_DIR, "code_structure_branching_labels_year-long-project-team-{team_id}_anonymized.csv")
    # --------------------------
    
    print(f"Starting batch processing for teams {START_TEAM} through {END_TEAM}...")

    for team_id in range(START_TEAM, END_TEAM + 1):
        # Construct the file paths for the current team
        input_filename = INPUT_FILE_TEMPLATE.format(team_id=team_id)
        output_filename = OUTPUT_FILE_TEMPLATE.format(team_id=team_id)

        print(f"\n==================================================")
        print(f"--- Processing Team {team_id} ({input_filename}) ---")
        clean_and_impute_branch_names(input_filename, output_filename)
        print(f"==================================================")