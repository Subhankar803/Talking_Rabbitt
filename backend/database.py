"""
database.py
SQLAlchemy engine, session factory, and declarative base.
Every other module gets its DB session through get_db().
"""
# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker, declarative_base

from config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,   # avoids "MySQL server has gone away" on idle connections
    pool_recycle=3600,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Call once on startup."""
    import models  # noqa: F401  (ensures models are registered on Base)
    Base.metadata.create_all(bind=engine)
