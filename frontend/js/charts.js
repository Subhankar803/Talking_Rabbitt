/* ============================================================
   charts.js — renders the uniform { type, labels, datasets } spec
   produced by visualization_engine.py, using Chart.js.
   ============================================================ */

const CHART_PALETTE = ["#2BD9A8", "#F5A855", "#7F9CF5", "#F0616B", "#B39DDB"];

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function renderChart(canvasId, spec, opts = {}) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !spec || spec.error) {
    if (canvas) canvas.closest(".card")?.querySelector(".chart-empty")?.classList.remove("hidden");
    return null;
  }

  const existing = Chart.getChart(canvas);
  if (existing) existing.destroy();

  const textColor = cssVar("--text-secondary");
  const gridColor = cssVar("--border");

  const datasets = spec.datasets.map((ds, i) => {
    let color = CHART_PALETTE[i % CHART_PALETTE.length];
    if (ds.label === "Anomalies" || ds.label === "anomalies") {
      color = "#F0616B";
    }
    const isPieLike = (spec.type === "pie" || spec.type === "doughnut" || spec.type === "polarArea");
    const base = {
      label: ds.label,
      data: ds.data,
      borderColor: isPieLike
        ? ds.data.map((_, idx) => CHART_PALETTE[idx % CHART_PALETTE.length])
        : color,
      backgroundColor: isPieLike
        ? ds.data.map((_, idx) => CHART_PALETTE[idx % CHART_PALETTE.length])
        : (spec.type === "line" ? `${color}22` : color),
      borderWidth: spec.type === "scatter" ? 0 : (isPieLike ? 1 : 2),
      pointRadius: spec.type === "line" ? 2 : (spec.type === "scatter" ? 5 : 0),
      tension: 0.35,
      fill: spec.type === "line",
      borderRadius: spec.type === "bar" ? 6 : 0,
    };
    return base;
  });

  const isPieLike = (spec.type === "pie" || spec.type === "doughnut" || spec.type === "polarArea");

  return new Chart(canvas, {
    type: spec.type === "scatter" ? "line" : spec.type,
    data: { labels: spec.labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: datasets.length > 1 || isPieLike, labels: { color: textColor, font: { size: 11 } } },
        tooltip: { mode: "index", intersect: false },
      },
      scales: isPieLike ? {} : {
        x: { ticks: { color: textColor, font: { size: 11 } }, grid: { color: gridColor, display: false } },
        y: { ticks: { color: textColor, font: { size: 11 } }, grid: { color: gridColor } },
      },
      ...opts,
    },
  });
}
