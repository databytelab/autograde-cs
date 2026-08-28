"""
SQLAlchemy engine, session factory, and Base.
All models import Base from here.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import settings

# ── Engine ────────────────────────────────────────────────────
connect_args = {}
if "sqlite" in settings.database_url:
    # SQLite: allow the same connection across multiple threads
    # (needed because FastAPI runs in async context)
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=(settings.environment == "development"),  # log SQL in dev
)

# Enable WAL mode for SQLite — better concurrent read performance
if "sqlite" in settings.database_url:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# ── Session ───────────────────────────────────────────────────
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ── Base ──────────────────────────────────────────────────────
Base = declarative_base()

# ── FastAPI dependency ────────────────────────────────────────
def get_db():
    """
    Yields a database session for a single request,
    guarantees it is closed afterwards even if an error occurs.

    Usage in a route:
        def my_route(db: Session = Depends(get_db)):
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
