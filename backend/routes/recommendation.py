"""
routes/recommendation.py
Standalone recommendation endpoint (also reachable via analytics/{id}/recommendations).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
import crud
from utils.validators import validate_dataset_exists

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("/{dataset_id}")
def get_saved_recommendations(dataset_id: int, db: Session = Depends(get_db)):
    dataset = crud.get_dataset(db, dataset_id)
    validate_dataset_exists(dataset)
    return crud.get_recommendations(db, dataset_id)
