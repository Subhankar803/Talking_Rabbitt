"""
analytics_engine.py

Business analytics on top of a cleaned dataframe: trends, anomalies,
top/worst performers, growth comparisons, and risk flags.

These functions double as the "tools" the LLM chat engine calls —
each one takes a dataframe + simple args and returns a small,
JSON-safe dict, never raw dataframes, so they're safe to hand
straight back to an LLM or a chart renderer.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from services import pandas_processor as pp
from utils.helpers import json_safe


def get_trend(df: pd.DataFrame, schema: dict, metric: str, freq: str = "ME") -> dict:
    date_col = _first_of_type(schema, "datetime")
    metric_col = _resolve_metric(df, metric)
    if not date_col or not metric_col:
        return {"error": "No date column or matching metric found for trend analysis."}

    ts = pp.resample_timeseries(df, date_col, metric_col, freq)
    ts["period"] = ts[date_col].dt.strftime("%Y-%m")
    values = ts[metric_col].tolist()

    change_pct = None
    if len(values) >= 2 and values[-2] != 0:
        change_pct = round((values[-1] - values[-2]) / abs(values[-2]) * 100, 2)

    return json_safe({
        "metric": metric_col,
        "periods": ts["period"].tolist(),
        "values": values,
        "latest_change_pct": change_pct,
        "direction": "up" if (change_pct or 0) >= 0 else "down",
    })


def detect_anomalies(df: pd.DataFrame, schema: dict, metric: str, z_thresh: float = 2.5) -> dict:
    metric_col = _resolve_metric(df, metric)
    if not metric_col:
        return {"error": f"No column matching '{metric}' found."}

    series = df[metric_col].dropna()
    mean, std = series.mean(), series.std()
    if std == 0 or np.isnan(std):
        return {"metric": metric_col, "anomalies": []}

    z_scores = (series - mean) / std
    anomaly_idx = z_scores[abs(z_scores) > z_thresh].index

    date_col = _first_of_type(schema, "datetime")
    records = []
    for idx in anomaly_idx:
        row = {"row_index": int(idx), "value": float(df.loc[idx, metric_col])}
        if date_col:
            row["date"] = str(df.loc[idx, date_col])
        records.append(row)

    return json_safe({
        "metric": metric_col,
        "mean": mean,
        "std_dev": std,
        "anomalies_found": len(records),
        "anomalies": records[:20],
        "series_values": series.tolist(),
        "series_labels": df.loc[series.index, date_col].dt.strftime("%Y-%m-%d").tolist() if date_col else [str(i) for i in series.index],
        "anomaly_indices": [series.index.get_loc(idx) for idx in anomaly_idx],
    })


def compare_dimension(df: pd.DataFrame, schema: dict, dimension: str, metric: str) -> dict:
    dim_col = _resolve_column(df, dimension)
    metric_col = _resolve_metric(df, metric)
    if not dim_col or not metric_col:
        return {"error": f"Could not resolve dimension '{dimension}' or metric '{metric}'."}

    grouped = pp.group_and_aggregate(df, dim_col, metric_col, "sum")
    total = grouped[metric_col].sum()
    grouped["share_pct"] = (grouped[metric_col] / total * 100).round(2) if total else 0

    return json_safe({
        "dimension": dim_col,
        "metric": metric_col,
        "ranking": grouped.to_dict(orient="records"),
        "best": grouped.iloc[0].to_dict() if not grouped.empty else None,
        "worst": grouped.iloc[-1].to_dict() if not grouped.empty else None,
    })


def top_bottom_performers(df: pd.DataFrame, schema: dict, dimension: str, metric: str, n: int = 5) -> dict:
    result = compare_dimension(df, schema, dimension, metric)
    if "error" in result:
        return result
    ranking = result["ranking"]
    return {
        "dimension": result["dimension"],
        "metric": result["metric"],
        "top": ranking[:n],
        "bottom": ranking[-n:][::-1],
    }


def detect_risks(df: pd.DataFrame, schema: dict) -> list[dict]:
    """Lightweight rule-based business risk flags derived from trend + anomaly signals."""
    risks = []
    numeric_cols = [c for c, t in schema.items() if t == "numeric"]
    date_col = _first_of_type(schema, "datetime")

    for metric_col in numeric_cols[:5]:
        if date_col:
            trend = get_trend(df, schema, metric_col)
            if trend.get("direction") == "down" and (trend.get("latest_change_pct") or 0) < -10:
                risks.append({
                    "type": "declining_trend",
                    "metric": metric_col,
                    "detail": f"{metric_col} dropped {trend['latest_change_pct']}% in the latest period.",
                })
        anomalies = detect_anomalies(df, schema, metric_col)
        if anomalies.get("anomalies_found", 0) > 0:
            risks.append({
                "type": "anomaly",
                "metric": metric_col,
                "detail": f"{anomalies['anomalies_found']} unusual values detected in {metric_col}.",
            })
    return risks


# ---------- Resolution helpers ----------

def _first_of_type(schema: dict, dtype: str) -> str | None:
    for col, t in schema.items():
        if t == dtype:
            return col
    return None


def _resolve_metric(df: pd.DataFrame, metric: str) -> str | None:
    return _resolve_column(df, metric)


def _resolve_column(df: pd.DataFrame, name: str) -> str | None:
    if name in df.columns:
        return name
    name_lower = name.lower().strip()
    for col in df.columns:
        if name_lower == col.lower() or name_lower in col.lower() or col.lower() in name_lower:
            return col
    return None
