"""
report_engine.py

Assembles the executive summary by combining signals from analytics_engine
and recommendation_engine. Kept rule-based and deterministic so it always
works even without an LLM key configured, but reads like an analyst wrote it.

Each section (key insights / risks / strengths / weaknesses) is derived
independently from the same underlying trend/anomaly data — they must
never just be the same sentence list copy-pasted into multiple sections,
or the report reads as templated regardless of what was uploaded.
"""
from __future__ import annotations

from services import analytics_engine as ae
from services import recommendation_engine as re_engine


def build_executive_report(df, schema: dict) -> dict:
    numeric_cols = [c for c, t in schema.items() if t == "numeric"]

    risks = ae.detect_risks(df, schema)
    recs = re_engine.generate_recommendations(df, schema)

    # Compute the latest-period trend once per metric and reuse it —
    # this is the shared source of truth for insights/strengths/weaknesses,
    # but each section below turns it into a *different* statement.
    trend_by_metric = {}
    for col in numeric_cols[:6]:
        trend = ae.get_trend(df, schema, col)
        change = trend.get("latest_change_pct")
        if "error" not in trend and change is not None:
            trend_by_metric[col] = change

    declining = {c: v for c, v in trend_by_metric.items() if v < 0}
    growing = {c: v for c, v in trend_by_metric.items() if v >= 0}
    anomaly_risks = [r for r in risks if r["type"] == "anomaly"]

    # --- Key insights: the headline takeaways, not a dump of every risk ---
    key_insights = []
    if declining:
        worst_metric = min(declining, key=declining.get)
        key_insights.append(
            f"{worst_metric} shows the steepest decline of any tracked metric, "
            f"down {abs(declining[worst_metric]):.1f}% in the latest period."
        )
    if growing:
        best_metric = max(growing, key=growing.get)
        key_insights.append(
            f"{best_metric} is the strongest performer, up "
            f"{growing[best_metric]:.1f}% in the latest period."
        )
    if anomaly_risks:
        key_insights.append(
            f"{len(anomaly_risks)} metric(s) — "
            f"{', '.join(r['metric'] for r in anomaly_risks)} — contain statistically "
            f"unusual data points worth a manual check."
        )
    if not key_insights:
        key_insights.append(
            "No strong upward or downward signal was detected across the tracked metrics this period."
        )

    # --- Strengths: metrics that are actually growing, not a fallback-only list ---
    strengths = [
        f"{col} grew {change:.1f}% in the latest period."
        for col, change in sorted(growing.items(), key=lambda kv: -kv[1])
    ]
    if not strengths:
        strengths.append(
            "No metric shows positive momentum this period — the priority is stabilizing "
            "the metrics below before pursuing growth initiatives."
        )

    # --- Weaknesses: metrics that are actually declining, phrased distinctly from Risks ---
    weaknesses = [
        f"{col} is trending downward, down {abs(change):.1f}% in the latest period."
        for col, change in sorted(declining.items(), key=lambda kv: kv[1])
    ]
    if not weaknesses:
        weaknesses.append("No metric shows a significant decline this period.")

    opportunities = [r["title"] for r in recs]

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
        "key_insights": key_insights,
        "risks": [r["detail"] for r in risks] or ["No significant risks detected."],
        "strengths": strengths,
        "weaknesses": weaknesses,
        "opportunities": opportunities,
        "summary": summary,
    }