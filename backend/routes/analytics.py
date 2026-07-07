"""
routes/analytics.py
Powers the dashboard: KPI cards, trend chart, top/worst performers, anomalies.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
import crud
from utils.validators import validate_dataset_exists
from services import dataset_cache as cache
from services import pandas_processor as pp
from services import analytics_engine as ae
from services import visualization_engine as ve

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _load(dataset_id: int, db: Session):
    dataset = crud.get_dataset(db, dataset_id)
    validate_dataset_exists(dataset)
    df = cache.load(dataset_id, dataset.cache_path)
    schema = dataset.column_schema
    return dataset, df, schema


@router.get("/{dataset_id}/dashboard")
def get_dashboard(dataset_id: int, db: Session = Depends(get_db)):
    dataset, df, schema = _load(dataset_id, db)

    kpis = pp.compute_kpis(df, schema)
    numeric_cols = [c for c, t in schema.items() if t == "numeric"]
    metric_col = numeric_cols[0] if numeric_cols else None

    trend_chart, ranking_top, ranking_bottom, anomalies = {}, [], [], []

    if metric_col:
        trend = ae.get_trend(df, schema, metric_col)
        trend_chart = ve.trend_to_chart(trend)

        anomaly_result = ae.detect_anomalies(df, schema, metric_col)
        anomalies = anomaly_result.get("anomalies", [])

        categorical_cols = [c for c, t in schema.items() if t == "categorical"]
        if categorical_cols:
            perf = ae.top_bottom_performers(df, schema, categorical_cols[0], metric_col, n=5)
            ranking_top = perf.get("top", [])
            ranking_bottom = perf.get("bottom", [])

    return {
        "kpis": pp.compute_kpis(df, schema),
        "kpi_cards": ve.kpi_cards(kpis),
        "trend_chart": trend_chart,
        "top_performers": ranking_top,
        "worst_performers": ranking_bottom,
        "anomalies": anomalies,
        "risks": ae.detect_risks(df, schema),
    }


@router.get("/{dataset_id}/compare")
def compare(dataset_id: int, dimension: str = Query(...), metric: str = Query(...), db: Session = Depends(get_db)):
    _, df, schema = _load(dataset_id, db)
    result = ae.compare_dimension(df, schema, dimension, metric)
    result["chart"] = ve.comparison_to_chart(result) if "ranking" in result else None
    return result


@router.get("/{dataset_id}/report")
def executive_report(dataset_id: int, db: Session = Depends(get_db)):
    from services import report_engine
    _, df, schema = _load(dataset_id, db)
    return report_engine.build_executive_report(df, schema)


@router.get("/{dataset_id}/recommendations")
def recommendations(dataset_id: int, db: Session = Depends(get_db)):
    from services import recommendation_engine
    dataset, df, schema = _load(dataset_id, db)
    recs = recommendation_engine.generate_recommendations(df, schema)
    crud.save_recommendations(db, dataset_id, recs)
    return recs
