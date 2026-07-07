"""
routes/chat.py
Conversational analytics endpoint — the "talking" part of the dashboard.
"""
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

    result = chat_engine.handle_chat(df, schema, payload.message, summary)

    crud.save_chat(
        db,
        dataset_id=payload.dataset_id,
        question=payload.message,
        answer=result["answer"],
        tools_used=result["tools_used"],
        chart_spec=result["chart_spec"],
        user_email=payload.user_email,
    )

    return schemas.ChatResponse(**result)


@router.get("/{dataset_id}/history", response_model=list[schemas.ChatHistoryItem])
def history(dataset_id: int, user_email: str = None, db: Session = Depends(get_db)):
    return crud.get_chat_history(db, dataset_id, user_email=user_email)
