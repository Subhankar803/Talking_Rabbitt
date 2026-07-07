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

    # Auto-migration for chat_history sessions columns
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            res = conn.execute(text("SHOW COLUMNS FROM chat_history LIKE 'session_id'")).fetchone()
            if not res:
                # Add columns
                conn.execute(text("ALTER TABLE chat_history ADD COLUMN session_id VARCHAR(255) NULL"))
                conn.execute(text("ALTER TABLE chat_history ADD COLUMN session_title VARCHAR(255) NULL"))
                conn.execute(text("CREATE INDEX idx_chat_session ON chat_history (session_id)"))
                # Migrate existing chats to a default session
                conn.execute(text("UPDATE chat_history SET session_id = 'default', session_title = 'Previous Chat' WHERE session_id IS NULL"))
    except Exception as e:
        print(f"Database migration failed: {e}")
