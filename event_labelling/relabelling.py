import os
import glob
import pandas as pd
import numpy as np
from ast import literal_eval # Used to safely convert the string representation of a list to an actual list

# --- Helper Functions (Revised) ---

def remove_event_label(event_list, label_to_remove):
    """Removes a specific label from a list if it exists."""
    if isinstance(event_list, list):
        try:
            event_list.remove(label_to_remove)
        except ValueError:
            pass  # Label was not in the list
    # Return the modified list or an empty list if it wasn't a list
    return event_list if isinstance(event_list, list) else []

def find_file(folder, pattern):
        potential_path = os.path.join(folder, pattern)
        if os.path.exists(potential_path):
            return potential_path
        return None

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))
DATA_FOLDER = os.path.join(PROJECT_ROOT, "data", "csv")

team_folders = glob.glob(os.path.join(DATA_FOLDER, "year-long-project-team-*"))
if not team_folders:
    raise FileNotFoundError(f"❌ No team folders found in {DATA_FOLDER}")

print(f"[INFO] Found {len(team_folders)} team folders:")
for t in team_folders:
    print(" -", os.path.basename(t))


for TEAM_FOLDER in team_folders:
    team_name = os.path.basename(TEAM_FOLDER)
    
    REVIEWS_PATH = find_file(TEAM_FOLDER, f"{team_name}_review-comments.csv")
    print(REVIEWS_PATH)
    LABELLED_PATH = find_file(DATA_FOLDER, f"pr_labels_{team_name}.csv")
    reviews_df = pd.read_csv(REVIEWS_PATH)
    relabelled_df = pd.read_csv(LABELLED_PATH)

    REVIEWS_PATH = find_file(TEAM_FOLDER, f"{team_name}_review-comments.csv")
    LABELLED_PATH = find_file(DATA_FOLDER, f"pr_labels_{team_name}.csv")

    reviews_df = pd.read_csv(REVIEWS_PATH)
    relabelled_df = pd.read_csv(LABELLED_PATH)

    # --- Core Logic ---

    ## 1. Convert 'event' column to actual Python lists
    # NOTE: The 'event' column must contain valid list strings (e.g., '["a", "b"]')
    try:
        # Use literal_eval to safely parse the string as a Python literal (a list)
        relabelled_df['event'] = relabelled_df['event'].apply(literal_eval)
    except ValueError as e:
        print(f"⚠️ Error parsing 'event' column for {team_name}. Ensure it's a valid string representation of a list. Error: {e}")
        # Handle the error, maybe by skipping or converting unparsable rows to an empty list
        # For now, let's assume it works or skip the team.
        continue # Skip to the next TEAM_FOLDER

    ## 2. Remove existing "empty_review_comment" labels
    print(f"➡️ Removing 'empty_review_comment' from {len(relabelled_df)} rows...")
    label_to_remove = "empty_review_comment"
    # Apply the removal function to every list in the 'event' column
    relabelled_df['event'] = relabelled_df['event'].apply(lambda x: remove_event_label(x, label_to_remove))
    print("✅ Removal complete.")

    ## 3. Identify new rows to append from reviews_df
    print("🔍 Identifying new 'empty_review_comment' events...")

    # Criteria: comment_body is effectively empty AND state is APPROVED
    # Use .str.strip().eq('') to check for empty/whitespace-only strings
    empty_comments_mask = reviews_df['comment_body'].fillna('').str.strip().eq('')
    approved_state_mask = reviews_df['state'].str.lower() == 'approved'

    # Filter the reviews DataFrame
    new_empty_reviews = reviews_df[empty_comments_mask & approved_state_mask]
    print(f"Found {len(new_empty_reviews)} new rows to label.")

    ## 4. Prepare new DataFrame and Append
    if not new_empty_reviews.empty:
        # Select and rename columns to match the target DataFrame structure
        new_rows = pd.DataFrame({
            'pr_id': new_empty_reviews['pr_id'],
            # Assuming 'author' is the correct column in reviews_df for pr_author
            'pr_author': new_empty_reviews['author'], 
            'event': [['empty_review_comment']] * len(new_empty_reviews), # List containing the single new label
            'created_at': new_empty_reviews['created_at']
            # You may need to fill other required columns of relabelled_df with default values (e.g., NaN)
        })

        # Concatenate the new rows to the existing relabelled_df
        # We use ignore_index=True because these are entirely new events/rows
        relabelled_df = pd.concat([relabelled_df, new_rows], ignore_index=True)
        print("✅ New rows appended.")

    # --- Save to New File ---
    RELABELLED_OUTPUT_PATH = os.path.join(DATA_FOLDER, f"pr_labels_{team_name}.csv")

    print(f"💾 Saving final DataFrame to {RELABELLED_OUTPUT_PATH}...")
    if not relabelled_df.empty:
        # When saving, convert the list back to a string representation if needed by downstream tools
        relabelled_df['event'] = relabelled_df['event'].astype(str)
        relabelled_df.to_csv(RELABELLED_OUTPUT_PATH, index=False)
        print("✅ File saved successfully.")

    # Note: The original print(relabelled_df) and final save logic needs to be moved
    # inside the loop to save the file for each team, or merged outside if you are
    # combining all teams' data. I've placed a modified save inside the loop.
