"""
routes/chat.py
Conversational analytics endpoint — the "talking" part of the dashboard.
"""
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
import crud
import schemas
from utils.validators import validate_dataset_exists
from services import dataset_cache as cache
from services import pandas_processor as pp
from services import chat_engine

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=schemas.ChatResponse)
def chat(payload: schemas.ChatRequest, db: Session = Depends(get_db)):
    dataset = crud.get_dataset(db, payload.dataset_id)
    validate_dataset_exists(dataset)

    df = cache.load(payload.dataset_id, dataset.cache_path)
    schema = dataset.column_schema
    summary = pp.dataframe_summary_for_ai(df, schema)

    company_name = None
    if payload.user_email:
        from models import User
        user = db.query(User).filter(User.email == payload.user_email.lower().strip()).first()
        if user:
            company_name = user.company_name

    result = chat_engine.handle_chat(df, schema, payload.message, summary, company_name=company_name)

    session_id = payload.session_id or str(uuid.uuid4())
    session_title = payload.session_title
    if not session_title:
        session_title = payload.message[:40] + ("..." if len(payload.message) > 40 else "")

    crud.save_chat(
        db,
        dataset_id=payload.dataset_id,
        question=payload.message,
        answer=result["answer"],
        tools_used=result["tools_used"],
        chart_spec=result["chart_spec"],
        user_email=payload.user_email,
        session_id=session_id,
        session_title=session_title,
    )

    return schemas.ChatResponse(
        answer=result["answer"],
        chart_spec=result["chart_spec"],
        tools_used=result["tools_used"],
        session_id=session_id,
        session_title=session_title,
    )


@router.get("/{dataset_id}/history", response_model=list[schemas.ChatHistoryItem])
def history(dataset_id: int, user_email: str = None, db: Session = Depends(get_db)):
    return crud.get_chat_history(db, dataset_id, user_email=user_email)


@router.get("/{dataset_id}/sessions", response_model=list[schemas.ChatSessionItem])
def list_sessions(dataset_id: int, user_email: str = None, db: Session = Depends(get_db)):
    return crud.get_chat_sessions(db, dataset_id, user_email=user_email)


@router.get("/session/{session_id}", response_model=list[schemas.ChatHistoryItem])
def get_session(session_id: str, user_email: str = None, db: Session = Depends(get_db)):
    return crud.get_session_history(db, session_id, user_email=user_email)
