"""Process model analysis pipeline (skips extraction, starts with labeling).
Can be called from collabAnalysis or other projects.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

# Load .env if it exists
load_dotenv(verbose=False)

from event_labelling.CodeStructure_Branching.main import process_all_teams as process_all_teams_cs
from event_labelling.PR.pr_label import process_all_teams as process_all_teams_pr
from process_model.transition_edges import main as run_transition_edges
from process_model.zscore_calculation import main as run_zscore
from process_model.clustering import main as run_clustering
from process_model.graphing import main as run_graphing
from analysis import main as run_analysis
from src.utils.database import init_db, SessionLocal
from src.models.db_models import PipelineRun
from src.api.process_api import ProcessAnalysisAPI


def run_process_model_pipeline(run_id: str = None) -> dict:
    """
    Run process model analysis (labeling + process models + analysis).
    Skips extraction step - assumes data already extracted.
    
    This function can be imported and called from collabAnalysis or other projects.
    
    Args:
        run_id: Optional run identifier for tracking in database
        
    Returns:
        Dictionary with pipeline results and status
    """
    # Initialize database
    try:
        init_db()
    except Exception as e:
        print(f"[WARN] Database initialization failed: {e}")
    
    if not run_id:
        import uuid
        run_id = str(uuid.uuid4())[:8]
    
    db = SessionLocal()
    pipeline_run = None
    
    try:
        # Create pipeline run record
        pipeline_run = PipelineRun(
            run_id=run_id,
            dataset_type="both",
            status="running"
        )
        db.add(pipeline_run)
        db.commit()
        db.refresh(pipeline_run)
        
        print(f"\n{'='*70}")
        print(f"🚀 STARTING PROCESS MODEL PIPELINE (Run: {run_id})")
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
        
        # Step 3: Process model analysis
        print("📊 Step 3: Process Model Analysis (Both Datasets)")
        print("   Processing for branching AND pr automatically...\n")
        
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
        
        # Register output files
        _register_output_files(pipeline_run.id)
        
        # Mark as complete
        pipeline_run.status = "completed"
        pipeline_run.completed_at = datetime.utcnow()
        db.commit()
        
        print(f"{'='*70}")
        print(f"[COMPLETE] Pipeline Complete!")
        print(f"{'='*70}\n")
        
        print(f"Output locations:")
        print(f"  • Branching analysis: data/outputs/branching/")
        print(f"  • PR analysis: data/outputs/pr/")
        print(f"  • Team statistics: data/analysis/")
        print(f"  • Run ID: {run_id}")
        print(f"  • Both datasets processed automatically - no environment variables needed!\n")
        
        return {
            'status': 'completed',
            'run_id': run_id,
            'message': 'Pipeline completed successfully'
        }
        
    except Exception as e:
        print(f"\n[ERROR] Pipeline failed: {e}")
        if pipeline_run:
            pipeline_run.status = "failed"
            pipeline_run.error_message = str(e)
            pipeline_run.completed_at = datetime.utcnow()
            db.commit()
        return {
            'status': 'failed',
            'run_id': run_id,
            'error': str(e)
        }
    finally:
        db.close()


def _register_output_files(pipeline_run_id: int):
    """Register generated output files in database."""
    api = ProcessAnalysisAPI()
    output_dir = Path("data/outputs")
    analysis_dir = Path("data/analysis")
    
    # Register branching outputs
    if (output_dir / "branching").exists():
        for f in (output_dir / "branching").glob("*.csv"):
            api.register_exported_file(
                str(f), "csv", dataset_type="branching",
                description=f"Branching analysis: {f.stem}",
                pipeline_run_id=pipeline_run_id
            )
        for f in (output_dir / "branching").glob("*.png"):
            api.register_exported_file(
                str(f), "png", dataset_type="branching",
                description=f"Branching graph: {f.stem}",
                pipeline_run_id=pipeline_run_id
            )
    
    # Register PR outputs
    if (output_dir / "pr").exists():
        for f in (output_dir / "pr").glob("*.csv"):
            api.register_exported_file(
                str(f), "csv", dataset_type="pr",
                description=f"PR analysis: {f.stem}",
                pipeline_run_id=pipeline_run_id
            )
        for f in (output_dir / "pr").glob("*.png"):
            api.register_exported_file(
                str(f), "png", dataset_type="pr",
                description=f"PR graph: {f.stem}",
                pipeline_run_id=pipeline_run_id
            )
    
    # Register analysis outputs
    if analysis_dir.exists():
        for f in analysis_dir.glob("*.csv"):
            api.register_exported_file(
                str(f), "csv", dataset_type="analysis",
                description=f"Team analysis: {f.stem}",
                pipeline_run_id=pipeline_run_id
            )


if __name__ == "__main__":
    result = run_process_model_pipeline()
    sys.exit(0 if result['status'] == 'completed' else 1)
