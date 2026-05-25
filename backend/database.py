"""
SQLAlchemy database engine, session factory, and Base class.
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from backend.config import settings

engine = create_engine(
    settings.database_url,
    # SQLite-specific: allow use across threads
    connect_args={"check_same_thread": False}
    if "sqlite" in settings.database_url else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """FastAPI dependency — yields a DB session, always closes after request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
