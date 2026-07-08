"""
routes/upload.py
Handles dataset upload: save file -> clean -> cache -> persist metadata.
"""
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session

from config import settings
from database import get_db
import crud
import schemas
from services import pandas_processor as pp
from services import dataset_cache as cache
from utils.validators import validate_file_extension, validate_file_size
from utils.helpers import generate_unique_filename, dataframe_preview
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("", response_model=schemas.DatasetPreviewResponse)
async def upload_dataset(file: UploadFile = File(...), db: Session = Depends(get_db)):
    validate_file_extension(file.filename)

    unique_name = generate_unique_filename(file.filename)
    saved_path = settings.UPLOAD_DIR / unique_name

    with open(saved_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    validate_file_size(saved_path.stat().st_size, settings.MAX_UPLOAD_MB)

    try:
        raw_df = pp.load_dataset(str(saved_path))
    except Exception as exc:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Could not parse file: {exc}")

    clean_df, report = pp.clean_dataset(raw_df)
    schema = pp.detect_column_types(clean_df)

    # Create DB row first to get an id, then persist the parquet cache keyed by that id.
    dataset = crud.create_dataset(
        db,
        filename=unique_name,
        original_name=file.filename,
        cache_path="",  # filled in below
        row_count=len(clean_df),
        column_count=len(clean_df.columns),
        column_schema=schema,
        preprocessing_report=report,
    )

    cache_path = cache.save(dataset.id, clean_df)
    dataset.cache_path = cache_path
    db.commit()

    return schemas.DatasetPreviewResponse(
        dataset_id=dataset.id,
        original_name=dataset.original_name,
        row_count=dataset.row_count,
        column_count=dataset.column_count,
        column_schema=schema,
        preprocessing_report=report,
        preview_rows=dataframe_preview(clean_df, 10),
    )


@router.get("/list", response_model=list[schemas.DatasetSummary])
def list_datasets(db: Session = Depends(get_db)):
    return crud.list_datasets(db)


@router.get("/{dataset_id}", response_model=schemas.DatasetPreviewResponse)
def get_dataset(dataset_id: int, db: Session = Depends(get_db)):
    dataset = crud.get_dataset(db, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    df = cache.load(dataset.id, dataset.cache_path)
    from utils.helpers import dataframe_preview
    
    return schemas.DatasetPreviewResponse(
        dataset_id=dataset.id,
        original_name=dataset.original_name,
        row_count=dataset.row_count,
        column_count=dataset.column_count,
        column_schema=dataset.column_schema,
        preprocessing_report=dataset.preprocessing_report,
        preview_rows=dataframe_preview(df, 10),
    )
