"""
forecast_engine.py

Time-series forecasting using scikit-learn. Keeps it simple and
explainable for a hackathon demo: linear regression on period index
with confidence derived from R^2, rather than a heavy ARIMA/Prophet
dependency that's harder to justify live to judges.
"""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

from services import analytics_engine as ae


def forecast_metric(df, schema: dict, metric: str, horizon_periods: int = 6, filter_col: str | None = None, filter_val: str | None = None) -> dict:
    trend = ae.get_trend(df, schema, metric, filter_col=filter_col, filter_val=filter_val)
    if "error" in trend:
        return trend

    values = np.array(trend["values"], dtype=float)
    periods = trend["periods"]

    if len(values) < 3:
        return {"error": "Not enough historical periods to forecast (need at least 3)."}

    X = np.arange(len(values)).reshape(-1, 1)
    y = values

    model = LinearRegression()
    model.fit(X, y)

    y_pred_hist = model.predict(X)
    confidence = float(max(0.0, r2_score(y, y_pred_hist)))

    future_X = np.arange(len(values), len(values) + horizon_periods).reshape(-1, 1)
    future_y = model.predict(future_X)
    future_y = np.maximum(future_y, 0)  # business metrics rarely go negative

    future_periods = _extend_period_labels(periods, horizon_periods)

    return {
        "metric": trend["metric"],
        "model_used": "linear_regression",
        "confidence": round(confidence, 3),
        "historical_periods": periods,
        "historical_values": [round(float(v), 2) for v in values],
        "forecast_periods": future_periods,
        "forecast_values": [round(float(v), 2) for v in future_y],
        "predictions": [
            {"period": p, "value": round(float(v), 2)}
            for p, v in zip(future_periods, future_y)
        ],
        "filter_col": filter_col,
        "filter_val": filter_val,
    }


def _extend_period_labels(periods: list[str], n: int) -> list[str]:
    """Extends a list of 'YYYY-MM' labels by n more months."""
    try:
        last_year, last_month = map(int, periods[-1].split("-"))
    except Exception:
        return [f"period_{i+1}" for i in range(n)]

    labels = []
    y, m = last_year, last_month
    for _ in range(n):
        m += 1
        if m > 12:
            m = 1
            y += 1
        labels.append(f"{y}-{m:02d}")
    return labels
