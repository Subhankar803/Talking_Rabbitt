/* ============================================================
   report.js — executive summary + recommendation engine output.
   ============================================================ */

document.addEventListener("DOMContentLoaded", async () => {
  const dataset = requireDatasetOrRedirect();
  if (!dataset) return;

  const reportEl = document.getElementById("report-content");
  const recEl = document.getElementById("recommendations-content");

  try {
    const [report, recs] = await Promise.all([
      apiFetch(`/analytics/${dataset.dataset_id}/report`),
      apiFetch(`/analytics/${dataset.dataset_id}/recommendations`),
    ]);
    renderReport(report);
    renderRecommendations(recs);
  } catch (err) {
    reportEl.innerHTML = `<div class="empty-state"><i class="ti ti-alert-circle"></i>${err.message}</div>`;
  }

  function renderReport(r) {
    const healthColor = { Healthy: "low", "Stable with caution areas": "medium", "At risk": "high" }[r.business_health] || "low";
    reportEl.innerHTML = `
      <div class="card" style="margin-bottom:16px">
        <div style="display:flex; align-items:center; justify-content:space-between">
          <div>
            <div class="card-title">Business health</div>
            <div class="kpi-value" style="font-size:20px">${r.business_health}</div>
          </div>
          <span class="badge ${healthColor}">${r.business_health}</span>
        </div>
        <p style="color:var(--text-secondary); margin-top:14px; margin-bottom:0">${r.summary}</p>
      </div>
      <div class="grid grid-2" style="margin-bottom:16px">
        ${listCard("Key insights", "ti-bulb", r.key_insights)}
        ${listCard("Risks", "ti-alert-triangle", r.risks)}
      </div>
      <div class="grid grid-2">
        ${listCard("Strengths", "ti-shield-check", r.strengths)}
        ${listCard("Weaknesses", "ti-trending-down", r.weaknesses)}
      </div>`;
  }

  function listCard(title, icon, items) {
    return `
      <div class="card">
        <div class="card-title"><i class="ti ${icon}"></i> ${title}</div>
        <ul style="margin:10px 0 0; padding-left:18px; color:var(--text-secondary); font-size:13px">
          ${items.map((i) => `<li style="margin-bottom:6px">${i}</li>`).join("")}
        </ul>
      </div>`;
  }

  function renderRecommendations(recs) {
    recEl.innerHTML = recs.map((r) => `
      <div class="card" style="margin-bottom:12px">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px">
          <div>
            <div class="insight-tag" style="margin-bottom:8px"><i class="ti ti-sparkles"></i> ${r.category.replace(/_/g, " ")}</div>
            <div style="font-weight:600; font-family:var(--font-display)">${r.title}</div>
            <p style="color:var(--text-secondary); font-size:13px; margin:8px 0 0">${r.reasoning}</p>
          </div>
          <span class="badge ${r.impact}">${r.impact} impact</span>
        </div>
      </div>
    `).join("");
  }
});
