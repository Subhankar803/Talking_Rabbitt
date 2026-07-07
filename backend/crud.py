"""
crud.py
All direct database reads/writes live here. Routes and services never
touch the SQLAlchemy session directly except through these functions.
"""
from sqlalchemy.orm import Session
import models


# ---------- Dataset ----------

def create_dataset(db: Session, *, filename, original_name, cache_path,
                    row_count, column_count, column_schema, preprocessing_report):
    ds = models.Dataset(
        filename=filename,
        original_name=original_name,
        cache_path=cache_path,
        row_count=row_count,
        column_count=column_count,
        column_schema=column_schema,
        preprocessing_report=preprocessing_report,
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return ds


def get_dataset(db: Session, dataset_id: int):
    return db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()


def list_datasets(db: Session, limit: int = 20):
    return (
        db.query(models.Dataset)
        .order_by(models.Dataset.uploaded_at.desc())
        .limit(limit)
        .all()
    )


# ---------- Chat ----------

def save_chat(db: Session, *, dataset_id, question, answer, tools_used, chart_spec, user_email: str = None):
    chat = models.ChatHistory(
        dataset_id=dataset_id,
        user_email=user_email,
        question=question,
        answer=answer,
        tools_used=tools_used,
        chart_spec=chart_spec,
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


def get_chat_history(db: Session, dataset_id: int, user_email: str = None, limit: int = 50):
    query = db.query(models.ChatHistory).filter(models.ChatHistory.dataset_id == dataset_id)
    if user_email:
        query = query.filter(models.ChatHistory.user_email == user_email)
    return (
        query.order_by(models.ChatHistory.created_at.asc())
        .limit(limit)
        .all()
    )


# ---------- Recommendations ----------

def save_recommendations(db: Session, dataset_id: int, items: list[dict]):
    objs = [
        models.Recommendation(
            dataset_id=dataset_id,
            category=item["category"],
            title=item["title"],
            reasoning=item["reasoning"],
            impact=item.get("impact", "medium"),
        )
        for item in items
    ]
    db.add_all(objs)
    db.commit()
    return objs


def get_recommendations(db: Session, dataset_id: int):
    return (
        db.query(models.Recommendation)
        .filter(models.Recommendation.dataset_id == dataset_id)
        .order_by(models.Recommendation.created_at.desc())
        .all()
    )


# ---------- Forecasts ----------

def save_forecast(db: Session, *, dataset_id, metric, horizon_periods, model_used, predictions, confidence):
    fc = models.Forecast(
        dataset_id=dataset_id,
        metric=metric,
        horizon_periods=horizon_periods,
        model_used=model_used,
        predictions=predictions,
        confidence=confidence,
    )
    db.add(fc)
    db.commit()
    db.refresh(fc)
    return fc


# ---------- Reports ----------

def save_report(db: Session, dataset_id: int, report_type: str, content: dict):
    r = models.Report(dataset_id=dataset_id, report_type=report_type, content=content)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r
