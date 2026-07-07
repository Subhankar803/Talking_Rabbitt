"""
schemas.py
Pydantic models for request validation and response serialization.
Kept separate from models.py (ORM) so API contracts can evolve
independently of the DB schema.
"""
from typing import Any, Optional
from datetime import datetime
from pydantic import BaseModel


# ---------- Dataset ----------

class DatasetPreviewResponse(BaseModel):
    dataset_id: int
    original_name: str
    row_count: int
    column_count: int
    column_schema: dict
    preprocessing_report: dict
    preview_rows: list[dict]

    class Config:
        from_attributes = True


class DatasetSummary(BaseModel):
    id: int
    original_name: str
    row_count: int
    column_count: int
    uploaded_at: datetime

    class Config:
        from_attributes = True


# ---------- Analytics ----------

class KPIResponse(BaseModel):
    kpis: dict[str, Any]
    trend_chart: dict
    top_performers: list[dict]
    worst_performers: list[dict]
    anomalies: list[dict]


# ---------- Chat ----------

class ChatRequest(BaseModel):
    dataset_id: int
    message: str
    user_email: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    chart_spec: Optional[dict] = None
    tools_used: list[str] = []


class ChatHistoryItem(BaseModel):
    question: str
    answer: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Forecast ----------

class ForecastRequest(BaseModel):
    dataset_id: int
    metric: str
    horizon_periods: int = 6


class ForecastResponse(BaseModel):
    metric: str
    predictions: list[dict]
    confidence: float
    model_used: str


# ---------- Recommendations ----------

class RecommendationItem(BaseModel):
    category: str
    title: str
    reasoning: str
    impact: str

    class Config:
        from_attributes = True


# ---------- Executive report ----------

class ExecutiveReportResponse(BaseModel):
    business_health: str
    key_insights: list[str]
    risks: list[str]
    strengths: list[str]
    weaknesses: list[str]
    opportunities: list[str]
    summary: str
