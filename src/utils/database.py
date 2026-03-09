"""Database connection and session management."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import StaticPool

# Get database URL from environment or use default
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://analysis:analysis_secure_password@localhost:5433/process_graphs"
)

# Create engine with appropriate pool settings
if DATABASE_URL.startswith("sqlite"):
    # For SQLite (development)
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    # For PostgreSQL (production)
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )

# Create session factory
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))


def get_db_session():
    """Get a database session."""
    return SessionLocal()


def init_db():
    """Initialize database tables."""
    from src.models.db_models import Base
    Base.metadata.create_all(bind=engine)


def close_db():
    """Close database connection."""
    SessionLocal.remove()
