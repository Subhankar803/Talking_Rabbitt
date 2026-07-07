"""
config.py
Central configuration for Talking Rabbitt.
All environment-dependent values are loaded here so no other module
reads os.environ directly.
"""
import os
from pathlib import Path
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    # --- Database ---
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "talking_rabbitt")

    # Full MySQL connection string (SQLAlchemy + PyMySQL driver)
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
    )

    # --- LLM ---
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

    # --- Storage ---
    UPLOAD_DIR = BASE_DIR / "storage" / "uploads"
    CACHE_DIR = BASE_DIR / "storage" / "cache"
    MAX_UPLOAD_MB = 25

    # --- App ---
    APP_NAME = "Talking Rabbitt"
    DEBUG = os.getenv("DEBUG", "true").lower() == "true"
    ALLOWED_ORIGINS = ["*"]  # tighten for production


settings = Settings()

settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
