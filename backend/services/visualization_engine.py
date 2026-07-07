"""
visualization_engine.py

Takes analytics results (plain dicts) and shapes them into chart specs
the frontend can hand straight to Chart.js. Returns a uniform structure:
{ "type": "line"|"bar"|"pie"|"scatter", "labels": [...], "datasets": [...] }
so charts.js on the frontend has one rendering path regardless of source.
"""
from __future__ import annotations


def trend_to_chart(trend: dict, label: str = None) -> dict:
    if "error" in trend:
        return {"error": trend["error"]}
    return {
        "type": "line",
        "labels": trend["periods"],
        "datasets": [{
            "label": label or trend["metric"],
            "data": trend["values"],
        }],
    }


def comparison_to_chart(comparison: dict, chart_type: str = "bar") -> dict:
    if "error" in comparison:
        return {"error": comparison["error"]}
    ranking = comparison["ranking"]
    return {
        "type": chart_type,
        "labels": [r[comparison["dimension"]] for r in ranking],
        "datasets": [{
            "label": comparison["metric"],
            "data": [r[comparison["metric"]] for r in ranking],
        }],
    }


def anomalies_to_chart(series_values: list[float], series_labels: list[str], anomaly_indices: list[int]) -> dict:
    return {
        "type": "scatter",
        "labels": series_labels,
        "datasets": [
            {"label": "Values", "data": series_values},
            {"label": "Anomalies", "data": [
                series_values[i] if i in anomaly_indices else None for i in range(len(series_values))
            ]},
        ],
    }


def forecast_to_chart(historical_periods: list, historical_values: list, forecast_periods: list, forecast_values: list, metric: str) -> dict:
    return {
        "type": "line",
        "labels": historical_periods + forecast_periods,
        "datasets": [
            {"label": f"{metric} (actual)", "data": historical_values + [None] * len(forecast_periods)},
            {"label": f"{metric} (forecast)", "data": [None] * len(historical_values) + forecast_values},
        ],
    }


def kpi_cards(kpis: dict) -> list[dict]:
    """Formats raw KPI dict into display-ready cards for the dashboard."""
    label_map = {
        "total_revenue": ("Total revenue", "currency"),
        "avg_revenue": ("Avg revenue / row", "currency"),
        "total_profit": ("Total profit", "currency"),
        "avg_profit": ("Avg profit / row", "currency"),
        "total_orders": ("Total orders", "number"),
        "unique_customers": ("Unique customers", "number"),
        "row_count": ("Records analyzed", "number"),
    }
    cards = []
    for key, value in kpis.items():
        title, fmt = label_map.get(key, (key.replace("_", " ").title(), "number"))
        cards.append({"key": key, "title": title, "value": value, "format": fmt})
    return cards
