"""
routes/voice.py

Speech-to-text and text-to-speech run in the browser via the Web Speech
API (js/voice.js) — no audio ever needs to hit the server, which keeps
this fast and avoids extra ML dependencies for the hackathon demo. This
route exists so the transcribed text follows the exact same grounded
chat pipeline as typed questions, with a `via_voice` flag for logging.
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

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.post("/query", response_model=schemas.ChatResponse)
def voice_query(payload: schemas.ChatRequest, db: Session = Depends(get_db)):
    dataset = crud.get_dataset(db, payload.dataset_id)
    validate_dataset_exists(dataset)

    df = cache.load(payload.dataset_id, dataset.cache_path)
    schema = dataset.column_schema
    summary = pp.dataframe_summary_for_ai(df, schema)

    result = chat_engine.handle_chat(df, schema, payload.message, summary)

    crud.save_chat(
        db,
        dataset_id=payload.dataset_id,
        question=f"[voice] {payload.message}",
        answer=result["answer"],
        tools_used=result["tools_used"],
        chart_spec=result["chart_spec"],
    )

    return schemas.ChatResponse(**result)
