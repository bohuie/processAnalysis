"""Public API for running process models and retrieving results.
This module is designed to be imported by collabAnalysis.
"""
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.utils.database import SessionLocal
from src.models.db_models import PipelineRun, TeamResult, AnalysisResult, ExportedFile


class ProcessAnalysisAPI:
    """Main API for collabAnalysis to interact with processAnalysis."""

    @staticmethod
    def run_process_model_pipeline(
        dataset_type: str = "both",
        teams: Optional[List[str]] = None,
        wait_for_completion: bool = False
    ) -> Dict:
        """
        Run the process model pipeline.
        
        Args:
            dataset_type: "branching", "pr", or "both"
            teams: List of team names to process (None = all)
            wait_for_completion: If True, block until pipeline completes
            
        Returns:
            Dictionary with pipeline run info:
            {
                'run_id': str,
                'status': str,
                'dataset_type': str,
                'started_at': datetime,
                'url': str  # Can be used to poll status
            }
        """
        db = SessionLocal()
        try:
            run_id = str(uuid.uuid4())[:8]
            pipeline_run = PipelineRun(
                run_id=run_id,
                dataset_type=dataset_type,
                status="pending",
                metadata={
                    "specified_teams": teams,
                    "wait_for_completion": wait_for_completion
                }
            )
            db.add(pipeline_run)
            db.commit()
            db.refresh(pipeline_run)
            
            return {
                'run_id': run_id,
                'status': 'pending',
                'dataset_type': dataset_type,
                'started_at': pipeline_run.started_at.isoformat(),
                'poll_url': f'/api/pipeline/status/{run_id}'
            }
        finally:
            db.close()

    @staticmethod
    def get_pipeline_status(run_id: str) -> Dict:
        """Get the status of a pipeline run."""
        db = SessionLocal()
        try:
            pipeline = db.query(PipelineRun).filter(PipelineRun.run_id == run_id).first()
            if not pipeline:
                return {'status': 'not_found', 'run_id': run_id}
            
            return {
                'run_id': run_id,
                'status': pipeline.status,
                'dataset_type': pipeline.dataset_type,
                'started_at': pipeline.started_at.isoformat(),
                'completed_at': pipeline.completed_at.isoformat() if pipeline.completed_at else None,
                'error_message': pipeline.error_message
            }
        finally:
            db.close()

    @staticmethod
    def get_team_results(
        team_name: str,
        dataset_type: Optional[str] = None,
        latest_only: bool = True
    ) -> List[Dict]:
        """
        Get process model results for a team.
        
        Args:
            team_name: Team identifier (e.g., 'year-long-project-team-1')
            dataset_type: Filter by dataset ("branching", "pr", or None for all)
            latest_only: Return only the most recent results
            
        Returns:
            List of result dictionaries
        """
        db = SessionLocal()
        try:
            query = db.query(TeamResult).filter(TeamResult.team_name == team_name)
            
            if dataset_type:
                query = query.filter(TeamResult.dataset_type == dataset_type)
            
            if latest_only:
                query = query.order_by(desc(TeamResult.updated_at)).limit(1)
            else:
                query = query.order_by(desc(TeamResult.updated_at))
            
            results = query.all()
            
            return [
                {
                    'team_name': r.team_name,
                    'dataset_type': r.dataset_type,
                    'num_clusters': r.num_clusters,
                    'num_events': r.num_events,
                    'num_transitions': r.num_transitions,
                    'files': {
                        'transition_edges': r.transition_edges_file,
                        'zscore': r.zscore_file,
                        'clusters': r.clusters_file,
                        'elbow_plot': r.elbow_plot_file,
                        'graph_output_dir': r.graph_output_dir
                    },
                    'created_at': r.created_at.isoformat(),
                    'updated_at': r.updated_at.isoformat()
                }
                for r in results
            ]
        finally:
            db.close()

    @staticmethod
    def get_analysis_results(team_name: Optional[str] = None) -> List[Dict]:
        """
        Get team-level analysis statistics.
        
        Args:
            team_name: Filter by team (None returns all)
            
        Returns:
            List of analysis result dictionaries
        """
        db = SessionLocal()
        try:
            query = db.query(AnalysisResult).order_by(desc(AnalysisResult.created_at))
            
            if team_name:
                query = query.filter(AnalysisResult.team_name == team_name)
            
            results = query.all()
            
            return [
                {
                    'team_name': r.team_name,
                    'metric_name': r.metric_name,
                    'metric_value': r.metric_value,
                    'metric_text': r.metric_text,
                    'created_at': r.created_at.isoformat()
                }
                for r in results
            ]
        finally:
            db.close()

    @staticmethod
    def get_exported_files(
        file_type: Optional[str] = None,
        dataset_type: Optional[str] = None,
        team_name: Optional[str] = None,
        public_only: bool = True
    ) -> List[Dict]:
        """
        Get exported files (CSVs, graphs, etc.).
        
        Args:
            file_type: Filter by type (csv, png, etc.)
            dataset_type: Filter by dataset ("branching", "pr", "analysis")
            team_name: Filter by team
            public_only: Only return public files
            
        Returns:
            List of file metadata dictionaries with paths
        """
        db = SessionLocal()
        try:
            query = db.query(ExportedFile)
            
            if public_only:
                query = query.filter(ExportedFile.is_public == True)
            if file_type:
                query = query.filter(ExportedFile.file_type == file_type)
            if dataset_type:
                query = query.filter(ExportedFile.dataset_type == dataset_type)
            if team_name:
                query = query.filter(ExportedFile.team_name == team_name)
            
            query = query.order_by(desc(ExportedFile.created_at))
            results = query.all()
            
            return [
                {
                    'file_name': r.file_name,
                    'file_path': r.file_path,
                    'file_type': r.file_type,
                    'dataset_type': r.dataset_type,
                    'team_name': r.team_name,
                    'description': r.description,
                    'created_at': r.created_at.isoformat(),
                    'exists': Path(r.file_path).exists()
                }
                for r in results
            ]
        finally:
            db.close()

    @staticmethod
    def get_graph_file(team_name: str, dataset_type: str, file_name: str) -> Optional[str]:
        """
        Get full path to a graph file.
        
        Args:
            team_name: Team identifier
            dataset_type: "branching" or "pr"
            file_name: Base filename (e.g., 'team_overall.png')
            
        Returns:
            Full file path if exists, None otherwise
        """
        db = SessionLocal()
        try:
            export = db.query(ExportedFile).filter(
                ExportedFile.team_name == team_name,
                ExportedFile.dataset_type == dataset_type,
                ExportedFile.file_name == file_name
            ).first()
            
            if export and Path(export.file_path).exists():
                return export.file_path
            return None
        finally:
            db.close()

    @staticmethod
    def get_csv_file(file_name: str) -> Optional[str]:
        """
        Get full path to a CSV file (for analysis results).
        
        Args:
            file_name: Base filename (e.g., 'table2_statistics.csv')
            
        Returns:
            Full file path if exists, None otherwise
        """
        db = SessionLocal()
        try:
            export = db.query(ExportedFile).filter(
                ExportedFile.file_type == 'csv',
                ExportedFile.file_name == file_name
            ).first()
            
            if export and Path(export.file_path).exists():
                return export.file_path
            return None
        finally:
            db.close()

    @staticmethod
    def register_exported_file(
        file_path: str,
        file_type: str,
        dataset_type: Optional[str] = None,
        team_name: Optional[str] = None,
        description: Optional[str] = None,
        pipeline_run_id: Optional[int] = None,
        public: bool = True
    ) -> bool:
        """
        Register an exported file in the database.
        
        Args:
            file_path: Full path to the file
            file_type: File type (csv, png, pdf, etc.)
            dataset_type: Dataset this belongs to ("branching", "pr", "analysis")
            team_name: Team this belongs to (if applicable)
            description: Human-readable description
            pipeline_run_id: Associated pipeline run ID
            public: Whether accessible to collabAnalysis
            
        Returns:
            True if successful, False otherwise
        """
        db = SessionLocal()
        try:
            if not Path(file_path).exists():
                return False
            
            export = ExportedFile(
                file_path=file_path,
                file_type=file_type,
                file_name=Path(file_path).name,
                dataset_type=dataset_type,
                team_name=team_name,
                description=description,
                pipeline_run_id=pipeline_run_id,
                is_public=public
            )
            db.add(export)
            db.commit()
            return True
        except Exception as e:
            print(f"Error registering file {file_path}: {e}")
            return False
        finally:
            db.close()


# Convenience aliases
api = ProcessAnalysisAPI()
