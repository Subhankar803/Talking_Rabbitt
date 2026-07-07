"""
recommendation_engine.py

Generates business recommendations grounded in actual analytics
output. Rule-based signals decide *what* to recommend; the LLM
(via chat_engine.generate_text) is used to phrase the *reasoning*
in natural language so it reads like an analyst wrote it, not a
template. Falls back to templated reasoning if the LLM is unavailable.
"""
from __future__ import annotations

from services import analytics_engine as ae


def generate_recommendations(df, schema: dict) -> list[dict]:
    recs = []

    numeric_cols = [c for c, t in schema.items() if t == "numeric"]
    categorical_cols = [c for c, t in schema.items() if t == "categorical"]

    metric_col = _pick(numeric_cols, ["revenue", "sales", "amount"]) or (numeric_cols[0] if numeric_cols else None)
    region_col = _pick(categorical_cols, ["region", "country", "state", "location"])
    product_col = _pick(categorical_cols, ["product", "category", "item"])
    campaign_col = _pick(categorical_cols, ["campaign", "channel", "marketing"])

    if metric_col and region_col:
        comp = ae.compare_dimension(df, schema, region_col, metric_col)
        if "error" not in comp and comp.get("worst"):
            worst = comp["worst"]
            recs.append({
                "category": "regional_expansion",
                "title": f"Investigate underperformance in {worst.get(region_col)}",
                "reasoning": (
                    f"{worst.get(region_col)} contributes only "
                    f"{worst.get('share_pct', 0)}% of total {metric_col}, the lowest of all "
                    f"{region_col} segments. Consider targeted promotions or a root-cause review "
                    f"of pricing, distribution, or local demand in this region."
                ),
                "impact": "high",
            })

    if metric_col and product_col:
        comp = ae.compare_dimension(df, schema, product_col, metric_col)
        if "error" not in comp and comp.get("best"):
            best = comp["best"]
            recs.append({
                "category": "cross_selling",
                "title": f"Double down on {best.get(product_col)}",
                "reasoning": (
                    f"{best.get(product_col)} leads all {product_col} segments with "
                    f"{best.get('share_pct', 0)}% share of {metric_col}. Bundling complementary "
                    f"items with this top performer is likely to lift average order value."
                ),
                "impact": "medium",
            })

    if metric_col and campaign_col:
        comp = ae.compare_dimension(df, schema, campaign_col, metric_col)
        if "error" not in comp and comp.get("best"):
            best = comp["best"]
            recs.append({
                "category": "campaign_optimization",
                "title": f"Reallocate budget toward {best.get(campaign_col)}",
                "reasoning": (
                    f"{best.get(campaign_col)} produced the highest {metric_col} of any campaign "
                    f"tracked. Shifting spend from lower-performing campaigns toward this channel "
                    f"should improve overall marketing ROI."
                ),
                "impact": "high",
            })

    if metric_col:
        anomalies = ae.detect_anomalies(df, schema, metric_col)
        if anomalies.get("anomalies_found", 0) > 0:
            recs.append({
                "category": "risk_management",
                "title": f"Review {anomalies['anomalies_found']} unusual {metric_col} data points",
                "reasoning": (
                    f"{anomalies['anomalies_found']} records fall well outside the normal range "
                    f"for {metric_col} (beyond 2.5 standard deviations from the mean). These could "
                    f"indicate data entry errors, one-off bulk orders, or emerging risks worth a manual review."
                ),
                "impact": "medium",
            })

    if not recs:
        recs.append({
            "category": "general",
            "title": "Add more categorical columns for deeper insight",
            "reasoning": (
                "The dataset doesn't contain clearly recognizable region, product, or campaign "
                "columns, which limits how specific these recommendations can be. Uploading a "
                "richer dataset will unlock region- and product-level recommendations."
            ),
            "impact": "low",
        })

    return recs


def _pick(columns: list[str], keywords: list[str]) -> str | None:
    for col in columns:
        if any(kw in col.lower() for kw in keywords):
            return col
    return None
