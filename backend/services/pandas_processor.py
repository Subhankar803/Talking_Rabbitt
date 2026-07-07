"""
pandas_processor.py

Pure data-processing module. No FastAPI, no SQLAlchemy, no UI logic —
just pandas/numpy functions that take a dataframe in and hand one back.
This is deliberately isolated so it can be unit-tested or demoed on its
own, independent of the web layer.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from utils.logger import get_logger

logger = get_logger(__name__)


# ---------- Loading ----------

def load_dataset(filepath: str) -> pd.DataFrame:
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    elif filepath.endswith((".xlsx", ".xls")):
        df = pd.read_excel(filepath)
    else:
        raise ValueError("Unsupported file format")
    return df


# ---------- Cleaning ----------

def clean_dataset(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Runs the full cleaning pipeline and returns (clean_df, report)."""
    report = {}

    report["original_rows"] = int(len(df))
    report["original_columns"] = int(len(df.columns))

    # Strip whitespace from column names
    df.columns = [str(c).strip() for c in df.columns]

    # Duplicates
    dup_count = int(df.duplicated().sum())
    df = df.drop_duplicates()
    report["duplicates_removed"] = dup_count

    # Null handling: report per-column, then impute sensibly
    null_counts = df.isnull().sum()
    report["nulls_found"] = {k: int(v) for k, v in null_counts[null_counts > 0].items()}

    for col in df.columns:
        if df[col].isnull().any():
            if pd.api.types.is_numeric_dtype(df[col]):
                df[col] = df[col].fillna(df[col].median())
            else:
                mode = df[col].mode()
                df[col] = df[col].fillna(mode.iloc[0] if not mode.empty else "Unknown")

    # Date detection & conversion
    date_cols = detect_date_columns(df)
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed")
    report["date_columns_detected"] = date_cols

    report["final_rows"] = int(len(df))
    report["final_columns"] = int(len(df.columns))

    logger.info(f"Cleaned dataset: {report}")
    return df, report


def detect_date_columns(df: pd.DataFrame) -> list[str]:
    date_like = []
    for col in df.columns:
        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            name_hint = any(kw in col.lower() for kw in ["date", "time", "day", "month", "year"])
            sample = df[col].dropna().head(20)
            if len(sample) == 0:
                continue
            try:
                parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
                success_rate = parsed.notna().mean()
                if success_rate > 0.8 or (name_hint and success_rate > 0.5):
                    date_like.append(col)
            except Exception:
                continue
    return date_like


def detect_column_types(df: pd.DataFrame) -> dict:
    """Classify each column as numeric / categorical / datetime / text."""
    schema = {}
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            schema[col] = "datetime"
        elif pd.api.types.is_numeric_dtype(df[col]):
            schema[col] = "numeric"
        elif df[col].nunique() <= max(20, len(df) * 0.05):
            schema[col] = "categorical"
        else:
            schema[col] = "text"
    return schema


# ---------- Filtering / grouping / aggregation ----------

def group_and_aggregate(df: pd.DataFrame, group_col: str, value_col: str, agg: str = "sum") -> pd.DataFrame:
    return df.groupby(group_col)[value_col].agg(agg).reset_index().sort_values(value_col, ascending=False)


def filter_dataframe(df: pd.DataFrame, column: str, value) -> pd.DataFrame:
    return df[df[column] == value]


def resample_timeseries(df: pd.DataFrame, date_col: str, value_col: str, freq: str = "ME") -> pd.DataFrame:
    ts = df.set_index(date_col)[value_col].resample(freq).sum().reset_index()
    return ts


# ---------- KPIs ----------

def compute_kpis(df: pd.DataFrame, schema: dict) -> dict:
    numeric_cols = [c for c, t in schema.items() if t == "numeric"]
    kpis = {"row_count": int(len(df))}

    for hint, candidates in {
        "revenue": ["revenue", "sales", "amount", "total"],
        "profit": ["profit", "margin"],
        "orders": ["order", "quantity", "units"],
    }.items():
        col = _match_column(numeric_cols, candidates)
        if col:
            kpis[f"total_{hint}"] = float(df[col].sum())
            kpis[f"avg_{hint}"] = float(df[col].mean())

    customer_col = _match_column(list(df.columns), ["customer", "client", "user"])
    if customer_col:
        kpis["unique_customers"] = int(df[customer_col].nunique())

    return kpis


def _match_column(columns: list[str], keywords: list[str]) -> str | None:
    for col in columns:
        if any(kw in col.lower() for kw in keywords):
            return col
    return None


# ---------- Prep for AI / visualization ----------

def dataframe_summary_for_ai(df: pd.DataFrame, schema: dict, max_rows: int = 5) -> str:
    """A compact textual description an LLM can use as grounding context."""
    lines = [
        f"Dataset shape: {df.shape[0]} rows x {df.shape[1]} columns.",
        f"Columns: {', '.join(f'{c} ({t})' for c, t in schema.items())}",
        f"Sample rows:\n{df.head(max_rows).to_string(index=False)}",
    ]
    return "\n".join(lines)
