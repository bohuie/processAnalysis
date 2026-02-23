import os
import sys
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

# Load .env if it exists
load_dotenv(verbose=False)

from scripts.app import run_batch_extraction
from event_labelling.CodeStructure_Branching.main import process_all_teams as process_all_teams_cs
from event_labelling.PR.pr_label import process_all_teams as process_all_teams_pr
from process_model.transition_edges import main as run_transition_edges
from process_model.zscore_calculation import main as run_zscore
from process_model.clustering import main as run_clustering
from process_model.graphing import main as run_graphing


def _count_teams_in_outputs(output_dir: str) -> int:
    sessions_fp = os.path.join(output_dir, "team_transition_sessions_count.csv")
    if not os.path.exists(sessions_fp):
        return 0
    try:
        df = pd.read_csv(sessions_fp, low_memory=False)
        if "team_number" in df.columns:
            return df["team_number"].nunique()
        if "team_name" in df.columns:
            return df["team_name"].nunique()
        return len(df)
    except Exception:
        return 0

# Your custom repo list
repos = [
    "year-long-project-team-1",
    "year-long-project-team-2",
    "year-long-project-team-3",
    "year-long-project-team-4",
    "year-long-project-team-5",
    "year-long-project-team-6",
    "year-long-project-team-7",
    "year-long-project-team-8",
    "year-long-project-team-9",
    "year-long-project-team-10",
    "year-long-project-team-11",
    "year-long-project-team-12",
    "year-long-project-team-13",
    "year-long-project-team-14",
    "year-long-project-team-15",
    "year-long-project-team-16",
    "year-long-project-team-17",
    "year-long-project-team-18",
    "year-long-project-team-19",
    "year-long-project-team-20",
    "year-long-project-team-21",
    "year-long-project-team-22",
]

# Run extraction
all_results, failed_repos = run_batch_extraction(
    repo_owner="COSC-499-W2023",
    repo_names=repos,
    output_base_dir="./data",
    save_csv=True,
    include_commits=True,
    include_files=True,
    include_comments=True,
)

# Optional: your custom summary
print("\nExtraction Summary:")
for result in all_results:
    print(f"  {result['repo_name']}: {result['pull_requests_extracted']} PRs")

# Continue with labeling steps
print("\n Step 2: Event Labelling & PR Analysis")
try:
    print("   • Processing Branching and Code Structure...")
    process_all_teams_cs()
    print("Finished Branching Analysis\n")
except Exception as e:
    print(f"Branching analysis error: {e}\n")

try:
    print("   • Processing PR Labels...")
    process_all_teams_pr()
    print("Finished PR Analysis\n")
except Exception as e:
    print(f"PR analysis error: {e}\n")

# Run process model analysis (BOTH datasets automatically)
print("\nStep 3: Process Model Analysis (Both Datasets)")
print("   Processing for branching AND pr_labels automatically...\n")

transition_ok = False
try:
    print("   • Computing transition edges...")
    run_transition_edges()
    print("   [OK] Finished transition edges\n")
    transition_ok = True
except Exception as e:
    print(f"   Transition edges error: {e}\n")

if transition_ok:
    branching_count = _count_teams_in_outputs(os.path.join("data", "outputs", "branching"))
    pr_count = _count_teams_in_outputs(os.path.join("data", "outputs", "pr"))
    if min(branching_count, pr_count) >= 3:
        try:
            print("   • Computing z-scores...")
            run_zscore()
            print("   [OK] Finished z-scores\n")
        except Exception as e:
            print(f"   Z-score error: {e}\n")

        try:
            print("   • Computing clusters...")
            run_clustering()
            print("   [OK] Finished clustering\n")
        except Exception as e:
            print(f"   Clustering error: {e}\n")
    else:
        print(
            "   [SKIP] Skipping z-scores and clustering (need >= 3 teams per dataset). "
            f"branching={branching_count}, pr={pr_count}\n"
        )

try:
    print("   • Generating graphs...")
    run_graphing()
    print("   [OK] Finished graph generation\n")
except Exception as e:
    print(f"   Graph generation error: {e}\n")

print("=" * 70)
print("[COMPLETE] Pipeline Complete!")
print("=" * 70)
print("\nOutput locations:")
print("  • Branching analysis: data/outputs/branching/")
print("  • PR analysis: data/outputs/pr/")
print("  • Both datasets processed automatically - no environment variables needed!")