"""Main pipeline runner - can be called from other projects like collabAnalysis."""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env if it exists
load_dotenv(verbose=False)

from scripts.app import run_batch_extraction
from event_labelling.CodeStructure_Branching.main import process_all_teams as process_all_teams_cs
from event_labelling.Communication.comm_label import process_all_teams as process_all_teams_comm
from event_labelling.PR.pr_label import process_all_teams as process_all_teams_pr
from process_model.transition_edges import main as run_transition_edges
from process_model.zscore_calculation import main as run_zscore
from process_model.clustering import main as run_clustering
from process_model.graphing import main as run_graphing
from analysis import main as run_analysis

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


def run_full_pipeline(run_id: str = None) -> dict:
    """
    Run the complete analysis pipeline: extraction → labeling → process models → analysis.
    
    This function can be imported and called from collabAnalysis or other projects.
    
    Args:
        run_id: Optional run identifier (for logging purposes)
        
    Returns:
        Dictionary with pipeline results and status
    """
    try:
        print(f"\n{'='*70}")
        print(f"🚀 STARTING FULL ANALYSIS PIPELINE")
        print(f"{'='*70}\n")
        
        # Step 1: Batch extraction
        print("📊 Step 1: Batch Extraction")
        try:
            all_results, failed_repos = run_batch_extraction(
                repo_owner="COSC-499-W2023",
                repo_names=repos,
                output_base_dir="./data",
                save_csv=True,
                include_commits=True,
                include_files=True,
                include_comments=True,
            )
            print("\nExtraction Summary:")
            for result in all_results:
                print(f"  {result['repo_name']}: {result['pull_requests_extracted']} PRs")
            print("   ✓ Batch extraction complete\n")
        except Exception as e:
            print(f"   ⚠️  Extraction error: {e}\n")
        
        # Step 2: Event labeling
        print("📊 Step 2: Event Labelling & PR Analysis")
        try:
            print("   • Processing Branching and Code Structure...")
            process_all_teams_cs()
            print("   [OK] Finished Branching Analysis\n")
        except Exception as e:
            print(f"   [ERROR] Branching analysis error: {e}\n")

        try:
            print("   • Processing Communication Labels...")
            process_all_teams_comm()
            print("   [OK] Finished Communication Analysis\n")
        except Exception as e:
            print(f"   [ERROR] Communication analysis error: {e}\n")

        try:
            print("   • Processing PR Labels...")
            process_all_teams_pr()
            print("   [OK] Finished PR Analysis\n")
        except Exception as e:
            print(f"   [ERROR] PR analysis error: {e}\n")

        # Step 3: Process model analysis
        print("📊 Step 3: Process Model Analysis (Both Datasets)")
        print("   Processing for branching, communication, AND pr automatically...\n")
        
        transition_ok = False
        try:
            print("   • Computing transition edges...")
            run_transition_edges()
            print("   ✓ Finished transition edges\n")
            transition_ok = True
        except Exception as e:
            print(f"   ⚠️  Transition edges error: {e}\n")
        
        if transition_ok:
            try:
                print("   • Computing z-scores...")
                run_zscore()
                print("   ✓ Finished z-scores\n")
            except Exception as e:
                print(f"   ⚠️  Z-score error: {e}\n")
            
            try:
                print("   • Computing clusters...")
                run_clustering()
                print("   ✓ Finished clustering\n")
            except Exception as e:
                print(f"   ⚠️  Clustering error: {e}\n")
        
        try:
            print("   • Generating graphs...")
            run_graphing()
            print("   ✓ Finished graph generation\n")
        except Exception as e:
            print(f"   ⚠️  Graph generation error: {e}\n")
        
        # Step 4: Team-level analysis
        print("📊 Step 4: Team-Level Analysis")
        try:
            print("   • Computing team statistics...")
            run_analysis()
            print("   ✓ Finished analysis\n")
        except Exception as e:
            print(f"   ⚠️  Analysis error: {e}\n")
        
        print(f"{'='*70}")
        print(f"[COMPLETE] Pipeline Complete!")
        print(f"{'='*70}\n")
        
        print(f"Output locations:")
        print(f"  • Branching analysis: data/outputs/branching/")
        print(f"  • Communication analysis: data/outputs/communication/")
        print(f"  • PR analysis: data/outputs/pr/")
        print(f"  • Team statistics: data/analysis/")
        print(f"  • All datasets processed automatically - no environment variables needed!\n")
        
        return {
            'status': 'completed',
            'message': 'Pipeline completed successfully',
            'data_dir': str(Path('data').resolve())
        }
        
    except Exception as e:
        print(f"\n[ERROR] Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            'status': 'failed',
            'error': str(e)
        }


if __name__ == "__main__":
    result = run_full_pipeline()
    sys.exit(0 if result['status'] == 'completed' else 1)