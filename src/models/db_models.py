"""SQLAlchemy database models for storing process model results."""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class PipelineRun(Base):
    """Track pipeline executions."""
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, unique=True, index=True)  # UUID for this run
    dataset_type = Column(String, index=True)  # "branching" or "pr"
    status = Column(String, default="pending")  # pending, running, completed, failed
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    metadata = Column(JSON, nullable=True)

    # Relationships
    team_results = relationship("TeamResult", back_populates="pipeline_run", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<PipelineRun {self.run_id} ({self.dataset_type})>"


class TeamResult(Base):
    """Store process model results per team per dataset."""
    __tablename__ = "team_results"

    id = Column(Integer, primary_key=True, index=True)
    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"), index=True)
    team_name = Column(String, index=True)
    dataset_type = Column(String, index=True)  # "branching" or "pr"
    
    # Process model metrics
    num_clusters = Column(Integer, nullable=True)
    num_events = Column(Integer, nullable=True)
    num_transitions = Column(Integer, nullable=True)
    
    # File locations
    transition_edges_file = Column(String, nullable=True)
    zscore_file = Column(String, nullable=True)
    clusters_file = Column(String, nullable=True)
    elbow_plot_file = Column(String, nullable=True)
    graph_output_dir = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    pipeline_run = relationship("PipelineRun", back_populates="team_results")

    def __repr__(self):
        return f"<TeamResult {self.team_name} ({self.dataset_type})>"


class AnalysisResult(Base):
    """Store team-level analysis statistics."""
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"), index=True, nullable=True)
    team_name = Column(String, index=True)
    metric_name = Column(String, index=True)
    metric_value = Column(Float, nullable=True)
    metric_text = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<AnalysisResult {self.team_name} - {self.metric_name}>"


class ExportedFile(Base):
    """Track exported CSV and graph files for easy retrieval."""
    __tablename__ = "exported_files"

    id = Column(Integer, primary_key=True, index=True)
    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"), index=True, nullable=True)
    file_type = Column(String, index=True)  # csv, png, pdf, etc.
    file_name = Column(String, index=True)
    file_path = Column(String, unique=True, index=True)
    dataset_type = Column(String, nullable=True)  # "branching", "pr", "analysis"
    team_name = Column(String, nullable=True, index=True)
    description = Column(Text, nullable=True)
    
    is_public = Column(Boolean, default=True)  # Whether accessible to collabAnalysis
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ExportedFile {self.file_name}>"
