/* ============================================================
   forecast.js — metric picker + scikit-learn forecast rendering.
   ============================================================ */

document.addEventListener("DOMContentLoaded", async () => {
  const dataset = requireDatasetOrRedirect();
  if (!dataset) return;

  const metricSelect = document.getElementById("metric-select");
  const horizonInput = document.getElementById("horizon-input");
  const runBtn = document.getElementById("run-forecast");
  const resultEl = document.getElementById("forecast-result");

  try {
    const dashboard = await apiFetch(`/analytics/${dataset.dataset_id}/dashboard`);
    const numericKeys = Object.keys(dashboard.kpis).filter((k) => k.startsWith("total_")).map((k) => k.replace("total_", ""));
    const fallback = numericKeys.length ? numericKeys : ["revenue"];
    metricSelect.innerHTML = fallback.map((m) => `<option value="${m}">${m}</option>`).join("");
  } catch { /* dashboard optional here */ }

  runBtn.addEventListener("click", async () => {
    const metric = metricSelect.value;
    const horizon = parseInt(horizonInput.value, 10) || 6;
    resultEl.innerHTML = `<div class="empty-state"><span class="spinner"></span></div>`;

    try {
      const result = await apiFetch("/forecast", {
        method: "POST",
        body: JSON.stringify({ dataset_id: dataset.dataset_id, metric, horizon_periods: horizon }),
      });

      if (result.error) {
        resultEl.innerHTML = `<div class="empty-state"><i class="ti ti-alert-circle"></i>${result.error}</div>`;
        return;
      }

      resultEl.innerHTML = `
        <div class="grid grid-3" style="margin-bottom:16px">
          <div class="card kpi-card"><div class="card-title">Model</div><div class="kpi-value" style="font-size:18px">${result.model_used.replace("_", " ")}</div></div>
          <div class="card kpi-card"><div class="card-title">Confidence (R²)</div><div class="kpi-value">${(result.confidence * 100).toFixed(1)}%</div></div>
          <div class="card kpi-card"><div class="card-title">Horizon</div><div class="kpi-value">${horizon} periods</div></div>
        </div>
        <div class="card" style="margin-bottom:16px">
          <div class="card-title"><i class="ti ti-chart-line"></i> ${metric} — actual vs forecast</div>
          <div style="height:280px"><canvas id="forecast-chart"></canvas></div>
        </div>
        <div class="card">
          <div class="card-title"><i class="ti ti-table"></i> Predicted values</div>
          <table>
            <thead><tr><th>Period</th><th>Predicted value</th></tr></thead>
            <tbody>${result.predictions.map((p) => `<tr><td class="primary">${p.period}</td><td>${p.value.toLocaleString("en-IN")}</td></tr>`).join("")}</tbody>
          </table>
        </div>`;

      renderChart("forecast-chart", result.chart);
    } catch (err) {
      resultEl.innerHTML = `<div class="empty-state"><i class="ti ti-alert-circle"></i>${err.message}</div>`;
    }
  });
});
