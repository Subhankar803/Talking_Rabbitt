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

def save_chat(db: Session, *, dataset_id, question, answer, tools_used, chart_spec, user_email: str = None, session_id: str = None, session_title: str = None):
    chat = models.ChatHistory(
        dataset_id=dataset_id,
        user_email=user_email,
        question=question,
        answer=answer,
        tools_used=tools_used,
        chart_spec=chart_spec,
        session_id=session_id,
        session_title=session_title,
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


def get_chat_sessions(db: Session, dataset_id: int, user_email: str = None):
    from sqlalchemy import func
    query = db.query(
        models.ChatHistory.session_id,
        func.max(models.ChatHistory.session_title).label("session_title"),
        func.max(models.ChatHistory.created_at).label("last_updated")
    ).filter(
        models.ChatHistory.dataset_id == dataset_id,
        models.ChatHistory.session_id != None
    )
    if user_email:
        query = query.filter(models.ChatHistory.user_email == user_email)
    
    results = query.group_by(models.ChatHistory.session_id).order_by(func.max(models.ChatHistory.created_at).desc()).all()
    return [
        {"session_id": r[0], "session_title": r[1] or "Unnamed Chat", "last_updated": r[2]}
        for r in results
    ]


def get_session_history(db: Session, session_id: str, user_email: str = None):
    query = db.query(models.ChatHistory).filter(models.ChatHistory.session_id == session_id)
    if user_email:
        query = query.filter(models.ChatHistory.user_email == user_email)
    return query.order_by(models.ChatHistory.created_at.asc()).all()


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
