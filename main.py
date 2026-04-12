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
from src.utils.list_repos import get_org_repositories

ORG_NAME = os.getenv("GITHUB_ORG", "UBCO-COSC499-Winter-2018-Term-1-2")


def _load_org_repo_names(org_name: str) -> list[str]:
    repos = get_org_repositories(org_name)
    repo_names = sorted({repo.get("name") for repo in repos if repo.get("name")})
    if not repo_names:
        raise RuntimeError(f"No repositories found for organization: {org_name}")
    return repo_names


def run_full_pipeline(run_id: str | None = None) -> dict:
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
            repo_names = _load_org_repo_names(ORG_NAME)
            print(f"   • Target org: {ORG_NAME}")
            print(f"   • Repositories discovered: {len(repo_names)}")
            all_results, failed_repos = run_batch_extraction(
                repo_owner=ORG_NAME,
                repo_names=repo_names,
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
            print("   • Processing PR Labels...")
            process_all_teams_pr()
            print("   [OK] Finished PR Analysis\n")
        except Exception as e:
            print(f"   [ERROR] PR analysis error: {e}\n")

        try:
            print("   • Processing Communication Labels...")
            process_all_teams_comm()
            print("   [OK] Finished Communication Analysis\n")
        except Exception as e:
            print(f"   [ERROR] Communication analysis error: {e}\n")
        
        # Step 3: Process model analysis
        print("📊 Step 3: Process Model Analysis (All Datasets)")
        print("   Processing for branching, pr, and communication automatically...\n")
        
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
        print(f"  • PR analysis: data/outputs/pr/")
        print(f"  • Communication analysis: data/outputs/communication/")
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