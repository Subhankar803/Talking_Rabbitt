/* ============================================================
   upload.js — drag/drop upload, cleaning report, live preview table.
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  const statusEl = document.getElementById("upload-status");
  const resultEl = document.getElementById("upload-result");

  if (!dropzone) return;

  ["dragenter", "dragover"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.add("drag-active"); })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.remove("drag-active"); })
  );
  dropzone.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  });
  dropzone.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => {
    if (e.target.files[0]) handleUpload(e.target.files[0]);
  });

  async function handleUpload(file) {
    const validExt = /\.(csv|xlsx|xls)$/i.test(file.name);
    if (!validExt) {
      statusEl.innerHTML = `<span style="color:var(--danger)">Unsupported file type. Use CSV or Excel.</span>`;
      return;
    }

    statusEl.innerHTML = `<span class="spinner"></span> Cleaning &amp; analyzing ${file.name}...`;
    resultEl.innerHTML = "";

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: formData });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Upload failed.");
      }
      const data = await res.json();

      AppState.setDataset({
        dataset_id: data.dataset_id,
        original_name: data.original_name,
        row_count: data.row_count,
      });

      statusEl.innerHTML = `<span style="color:var(--signal)"><i class="ti ti-check"></i> Dataset ready.</span>`;
      renderResult(data);
    } catch (err) {
      statusEl.innerHTML = `<span style="color:var(--danger)">${err.message}</span>`;
    }
  }

  function renderResult(data) {
    const report = data.preprocessing_report;
    const nullEntries = Object.entries(report.nulls_found || {});

    resultEl.innerHTML = `
      <div class="grid grid-4" style="margin-bottom:16px">
        ${statCard("Rows loaded", report.original_rows)}
        ${statCard("Duplicates removed", report.duplicates_removed)}
        ${statCard("Columns", report.final_columns)}
        ${statCard("Date columns found", (report.date_columns_detected || []).length)}
      </div>

      <div class="card" style="margin-bottom:16px">
        <div class="card-title"><i class="ti ti-list-details"></i> Column schema detected</div>
        <table>
          <thead><tr><th>Column</th><th>Type</th></tr></thead>
          <tbody>
            ${Object.entries(data.column_schema).map(([col, type]) => `
              <tr><td class="primary">${col}</td><td>${badgeForType(type)}</td></tr>
            `).join("")}
          </tbody>
        </table>
      </div>

      ${nullEntries.length ? `
      <div class="card" style="margin-bottom:16px">
        <div class="card-title"><i class="ti ti-alert-triangle"></i> Nulls found &amp; imputed</div>
        <table>
          <thead><tr><th>Column</th><th>Nulls filled</th></tr></thead>
          <tbody>${nullEntries.map(([col, n]) => `<tr><td class="primary">${col}</td><td>${n}</td></tr>`).join("")}</tbody>
        </table>
      </div>` : ""}

      <div class="card" style="margin-bottom:16px">
        <div class="card-title"><i class="ti ti-table"></i> Preview (first 10 rows)</div>
        <div style="overflow-x:auto">
          <table>
            <thead><tr>${Object.keys(data.preview_rows[0] || {}).map((c) => `<th>${c}</th>`).join("")}</tr></thead>
            <tbody>
              ${data.preview_rows.map((row) => `<tr>${Object.values(row).map((v) => `<td>${v ?? "—"}</td>`).join("")}</tr>`).join("")}
            </tbody>
          </table>
        </div>
      </div>

      <a href="/dashboard" class="btn btn-primary"><i class="ti ti-chart-bar"></i> Go to dashboard</a>
    `;
  }

  function statCard(label, value) {
    return `<div class="card kpi-card"><div class="card-title">${label}</div><div class="kpi-value">${value}</div></div>`;
  }

  function badgeForType(type) {
    const map = { numeric: "low", categorical: "medium", datetime: "high", text: "low" };
    return `<span class="badge ${map[type] || "low"}">${type}</span>`;
  }
});
