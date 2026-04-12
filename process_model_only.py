"""Process model analysis pipeline (skips extraction, starts with labeling).
Can be called from collabAnalysis or other projects.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env if it exists
load_dotenv(verbose=False)

from event_labelling.CodeStructure_Branching.main import process_all_teams as process_all_teams_cs
from event_labelling.Communication.comm_label import process_all_teams as process_all_teams_comm
from event_labelling.PR.pr_label import process_all_teams as process_all_teams_pr
from process_model.transition_edges import main as run_transition_edges
from process_model.zscore_calculation import main as run_zscore
from process_model.clustering import main as run_clustering
from process_model.graphing import main as run_graphing
from analysis import main as run_analysis


def run_process_model_pipeline() -> dict:
    """
    Run process model analysis (labeling + process models + analysis).
    Skips extraction step - assumes data already extracted.
    
    This function can be imported and called from collabAnalysis or other projects.
    
    Returns:
        Dictionary with pipeline results and status
    """
    try:
        print(f"\n{'='*70}")
        print(f"🚀 STARTING PROCESS MODEL PIPELINE")
        print(f"{'='*70}\n")
        
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
    result = run_process_model_pipeline()
    sys.exit(0 if result['status'] == 'completed' else 1)
