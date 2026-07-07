"""
report_engine.py

Assembles the executive summary by combining signals from analytics_engine
and recommendation_engine. Kept rule-based and deterministic so it always
works even without an LLM key configured, but reads like an analyst wrote it.
"""
from __future__ import annotations

from services import analytics_engine as ae
from services import recommendation_engine as re_engine


def build_executive_report(df, schema: dict) -> dict:
    numeric_cols = [c for c, t in schema.items() if t == "numeric"]
    metric_col = numeric_cols[0] if numeric_cols else None

    risks = ae.detect_risks(df, schema)
    recs = re_engine.generate_recommendations(df, schema)

    key_insights = []
    strengths = []
    weaknesses = []
    opportunities = [r["title"] for r in recs]

    if metric_col:
        trend = ae.get_trend(df, schema, metric_col)
        if "error" not in trend:
            change = trend.get("latest_change_pct")
            if change is not None:
                direction = "grew" if change >= 0 else "declined"
                key_insights.append(f"{metric_col} {direction} {abs(change)}% in the most recent period.")
                if change >= 0:
                    strengths.append(f"Positive momentum in {metric_col} ({change:+}% last period).")
                else:
                    weaknesses.append(f"{metric_col} is trending downward ({change:+}% last period).")

    for risk in risks:
        key_insights.append(risk["detail"])
        weaknesses.append(risk["detail"])

    if not risks:
        strengths.append("No major statistical anomalies or risk signals detected in the current dataset.")

    health = "Healthy"
    if len(risks) >= 3:
        health = "At risk"
    elif len(risks) >= 1:
        health = "Stable with caution areas"

    summary = (
        f"Business health is assessed as '{health}' based on {len(risks)} risk signal(s) detected "
        f"across the dataset. {len(recs)} actionable recommendation(s) have been generated, "
        f"with {'high' if any(r['impact']=='high' for r in recs) else 'moderate'} potential impact "
        f"identified in at least one area."
    )

    return {
        "business_health": health,
        "key_insights": key_insights or ["Dataset does not contain enough time-series or categorical signal for deep insights."],
        "risks": [r["detail"] for r in risks] or ["No significant risks detected."],
        "strengths": strengths,
        "weaknesses": weaknesses or ["No major weaknesses detected."],
        "opportunities": opportunities,
        "summary": summary,
    }
