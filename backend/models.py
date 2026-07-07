"""
models.py
SQLAlchemy ORM models. Mirrors database/schema.sql exactly.
Only metadata / history / generated-content tables live here —
raw uploaded dataset rows are never stored in MySQL, only cached
on disk as parquet and referenced by Dataset.cache_path.
"""
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, JSON, Float
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_name = Column(String(255), nullable=False)
    cache_path = Column(String(500), nullable=False)     # parquet file on disk
    row_count = Column(Integer, default=0)
    column_count = Column(Integer, default=0)
    column_schema = Column(JSON, default=dict)            # {col: dtype}
    preprocessing_report = Column(JSON, default=dict)      # nulls dropped, dupes removed, etc.
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    chat_history = relationship("ChatHistory", back_populates="dataset", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="dataset", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="dataset", cascade="all, delete-orphan")
    forecasts = relationship("Forecast", back_populates="dataset", cascade="all, delete-orphan")


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False, index=True)
    user_email = Column(String(255), ForeignKey("user_table.email"), nullable=True, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    tools_used = Column(JSON, default=list)     # which analytics functions the LLM called
    chart_spec = Column(JSON, nullable=True)      # chart data returned alongside the answer
    session_id = Column(String(255), nullable=True, index=True)
    session_title = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    dataset = relationship("Dataset", back_populates="chat_history")


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False, index=True)
    report_type = Column(String(50), default="executive_summary")
    content = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    dataset = relationship("Dataset", back_populates="reports")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False, index=True)
    category = Column(String(100))         # pricing, marketing, inventory, retention...
    title = Column(String(255))
    reasoning = Column(Text)
    impact = Column(String(20), default="medium")  # low / medium / high
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    dataset = relationship("Dataset", back_populates="recommendations")


class Forecast(Base):
    __tablename__ = "forecasts"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False, index=True)
    metric = Column(String(100))            # revenue, sales, profit...
    horizon_periods = Column(Integer, default=6)
    model_used = Column(String(50), default="linear_regression")
    predictions = Column(JSON, nullable=False)   # [{period, value}, ...]
    confidence = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    dataset = relationship("Dataset", back_populates="forecasts")


class User(Base):
    __tablename__ = "user_table"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
