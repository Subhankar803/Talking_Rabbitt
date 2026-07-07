"""
main.py
Talking Rabbitt — FastAPI application entrypoint.
Wires together CORS, static frontend serving, DB init, and all routers.
"""
import sys
from pathlib import Path

# Add backend directory to sys.path to allow absolute imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

import hashlib
from fastapi import FastAPI, Depends, HTTPException, status
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from fastapi.staticfiles import StaticFiles
# pyrefly: ignore [missing-import]
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import init_db, get_db
from models import User
from utils.logger import get_logger

from routes import upload, analytics, chat, forecast, recommendation, voice

logger = get_logger(__name__)

app = FastAPI(title=settings.APP_NAME, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(analytics.router)
app.include_router(chat.router)
app.include_router(forecast.router)
app.include_router(recommendation.router)
app.include_router(voice.router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


@app.on_event("startup")
def on_startup():
    logger.info(f"Starting {settings.APP_NAME}...")
    try:
        init_db()
        logger.info("Database tables verified/created.")
    except Exception as exc:
        logger.error(f"Database init failed — check MySQL connection settings. {exc}")


@app.get("/health")
def health_check():
    return {"status": "ok", "app": settings.APP_NAME}


# ---------- Authentication Schemas & Endpoints ----------

class UserSignUpRequest(BaseModel):
    fullName: str
    companyName: str
    email: str
    password: str

class UserLoginRequest(BaseModel):
    email: str
    password: str

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

@app.post("/api/signup")
def signup(payload: UserSignUpRequest, db: Session = Depends(get_db)):
    email_clean = payload.email.lower().strip()
    existing_user = db.query(User).filter(User.email == email_clean).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email is already registered")
    
    new_user = User(
        full_name=payload.fullName,
        company_name=payload.companyName,
        email=email_clean,
        password=hash_password(payload.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"status": "success", "message": "User registered successfully"}

@app.post("/api/login")
def login(payload: UserLoginRequest, db: Session = Depends(get_db)):
    email_clean = payload.email.lower().strip()
    user = db.query(User).filter(User.email == email_clean).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid email or password")
    
    if user.password != hash_password(payload.password):
        raise HTTPException(status_code=400, detail="Invalid email or password")
    
    return {
        "status": "success",
        "user": {
            "id": user.id,
            "fullName": user.full_name,
            "companyName": user.company_name,
            "email": user.email
        }
    }

# ---------- Serve frontend pages ----------

for page in ["index", "dashboard", "chat", "upload", "forecast", "report", "login", "sign_up"]:
    def _make_handler(p=page):
        def handler():
            return FileResponse(FRONTEND_DIR / f"{p}.html")
        return handler
    
    if page == "login":
        app.get("/login")(_make_handler("login"))
        app.get("/")(_make_handler("login"))
    elif page == "index":
        app.get("/home")(_make_handler("index"))
    else:
        app.get(f"/{page}")(_make_handler())
