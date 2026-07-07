"""
routes/forecast.py
Forecasting endpoint backed by scikit-learn.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
import crud
import schemas
from utils.validators import validate_dataset_exists
from services import dataset_cache as cache
from services import forecast_engine as fe
from services import visualization_engine as ve

router = APIRouter(prefix="/api/forecast", tags=["forecast"])


@router.post("")
def forecast(payload: schemas.ForecastRequest, db: Session = Depends(get_db)):
    dataset = crud.get_dataset(db, payload.dataset_id)
    validate_dataset_exists(dataset)

    df = cache.load(payload.dataset_id, dataset.cache_path)
    schema = dataset.column_schema

    result = fe.forecast_metric(df, schema, payload.metric, payload.horizon_periods)
    if "error" in result:
        return result

    crud.save_forecast(
        db,
        dataset_id=payload.dataset_id,
        metric=result["metric"],
        horizon_periods=payload.horizon_periods,
        model_used=result["model_used"],
        predictions=result["predictions"],
        confidence=result["confidence"],
    )

    chart = ve.forecast_to_chart(
        result["historical_periods"], result["historical_values"],
        result["forecast_periods"], result["forecast_values"], result["metric"],
    )

    return {**result, "chart": chart}
