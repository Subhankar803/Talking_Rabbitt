/* ============================================================
   dashboard.js — fetches /api/analytics/{id}/dashboard and renders
   KPI cards, trend chart, performer tables, anomalies, and risks.
   ============================================================ */

document.addEventListener("DOMContentLoaded", async () => {
  const dataset = requireDatasetOrRedirect();
  if (!dataset) return;

  const kpiGrid = document.getElementById("kpi-grid");
  const perfSection = document.getElementById("performers-section");
  const riskSection = document.getElementById("risk-section");

  try {
    const data = await apiFetch(`/analytics/${dataset.dataset_id}/dashboard`);
    renderKPIs(data.kpi_cards);
    renderChart(
      dataset.dataset_id ? "trend-chart" : "trend-chart",
      data.trend_chart
    );
    renderPerformers(data.top_performers, data.worst_performers);
    renderRisks(data.risks);
    renderAnomalies(data.anomalies);
  } catch (err) {
    kpiGrid.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><i class="ti ti-alert-circle"></i>${err.message}</div>`;
  }

  function renderKPIs(cards) {
    if (!cards || !cards.length) {
      kpiGrid.innerHTML = `<div class="empty-state" style="grid-column:1/-1">No numeric KPIs detected in this dataset.</div>`;
      return;
    }
    kpiGrid.innerHTML = cards.map((c) => `
      <div class="card kpi-card">
        <div class="card-title">${c.title}</div>
        <div class="kpi-value">${formatValue(c.value, c.format)}</div>
      </div>
    `).join("");
  }

  function renderPerformers(top, bottom) {
    if (!perfSection) return;
    if (!top.length && !bottom.length) {
      perfSection.innerHTML = `<div class="empty-state"><i class="ti ti-list"></i>No categorical dimension found to rank.</div>`;
      return;
    }
    perfSection.innerHTML = `
      <div class="grid grid-2">
        <div class="card">
          <div class="card-title"><i class="ti ti-trophy"></i> Top performers</div>
          ${performerTable(top)}
        </div>
        <div class="card">
          <div class="card-title"><i class="ti ti-trending-down"></i> Underperforming</div>
          ${performerTable(bottom)}
        </div>
      </div>`;
  }

  function performerTable(rows) {
    if (!rows.length) return `<div class="empty-state">No data.</div>`;
    const dimKey = Object.keys(rows[0]).find((k) => !["share_pct"].includes(k) && typeof rows[0][k] !== "number") || Object.keys(rows[0])[0];
    const metricKey = Object.keys(rows[0]).find((k) => typeof rows[0][k] === "number" && k !== "share_pct");
    return `
      <table>
        <thead><tr><th>${dimKey}</th><th>${metricKey}</th><th>Share</th></tr></thead>
        <tbody>${rows.map((r) => `
          <tr><td class="primary">${r[dimKey]}</td><td>${formatValue(r[metricKey], "currency")}</td><td>${r.share_pct ?? "—"}%</td></tr>
        `).join("")}</tbody>
      </table>`;
  }

  function renderRisks(risks) {
    if (!riskSection) return;
    if (!risks.length) {
      riskSection.innerHTML = `<div class="empty-state"><i class="ti ti-shield-check"></i>No risk signals detected.</div>`;
      return;
    }
    riskSection.innerHTML = risks.map((r) => `
      <div class="card" style="border-color:var(--danger-dim); margin-bottom:10px; display:flex; gap:12px; align-items:flex-start">
        <i class="ti ti-alert-triangle" style="color:var(--danger); font-size:18px; margin-top:2px"></i>
        <div>
          <div style="font-weight:500">${r.type.replace(/_/g, " ")}</div>
          <div style="color:var(--text-secondary); font-size:12.5px; margin-top:2px">${r.detail}</div>
        </div>
      </div>
    `).join("");
  }

  function renderAnomalies(anomalies) {
    const el = document.getElementById("anomaly-count");
    if (el) el.textContent = anomalies?.length ? `${anomalies.length} unusual data points flagged` : "No anomalies detected";
  }

  function formatValue(value, format) {
    if (value == null) return "—";
    if (format === "currency") return "₹" + Number(value).toLocaleString("en-IN", { maximumFractionDigits: 0 });
    return Number(value).toLocaleString("en-IN");
  }

  // Chat History Modal logic
  const viewHistoryBtn = document.getElementById("view-chat-history-btn");
  const modal = document.getElementById("chat-history-modal");
  const modalBody = document.getElementById("chat-history-modal-body");
  const closeBtn = document.getElementById("close-chat-history-btn");

  if (viewHistoryBtn && modal && modalBody && closeBtn) {
    viewHistoryBtn.addEventListener("click", async () => {
      // Clear previous content and show spinner
      modalBody.innerHTML = `
        <div style="display:flex; justify-content:center; align-items:center; padding: 40px 0;">
          <span class="spinner" style="width:24px; height:24px;"></span>
        </div>`;
      modal.classList.add("active");

      try {
        const userRaw = localStorage.getItem("tr_user");
        const user = userRaw ? JSON.parse(userRaw) : null;
        const email = user ? user.email : null;

        if (!email) {
          modalBody.innerHTML = `<div class="modal-empty"><i class="ti ti-alert-circle"></i>User email not found. Please log in again.</div>`;
          return;
        }

        const history = await apiFetch(`/chat/${dataset.dataset_id}/history?user_email=${encodeURIComponent(email)}`);
        
        if (!history || history.length === 0) {
          modalBody.innerHTML = `<div class="modal-empty"><i class="ti ti-message-off"></i>No chat history found for this dataset.</div>`;
          return;
        }

        modalBody.innerHTML = history.map((item) => {
          const timeStr = item.created_at ? new Date(item.created_at).toLocaleString() : '';
          return `
            <div class="history-item">
              <div class="history-q"><i class="ti ti-user"></i> <span>${escapeHtml(item.question)}</span></div>
              <div class="history-a">${parseMarkdown(item.answer)}</div>
              ${timeStr ? `<div class="history-time">${timeStr}</div>` : ''}
            </div>`;
        }).join("");
      } catch (err) {
        modalBody.innerHTML = `<div class="modal-empty" style="color:var(--danger)"><i class="ti ti-alert-circle"></i>Failed to load history: ${err.message}</div>`;
      }
    });

    closeBtn.addEventListener("click", () => {
      modal.classList.remove("active");
    });

    modal.addEventListener("click", (e) => {
      if (e.target === modal) {
        modal.classList.remove("active");
      }
    });
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function parseMarkdown(text) {
    if (!text) return "";
    let escaped = escapeHtml(text);
    
    // Convert headings: ### and ## and #
    escaped = escaped.replace(/^### (.*?)$/gm, '<h4 style="margin: 10px 0 6px; font-weight: 600; font-size: 14px; color: var(--text-primary);">$1</h4>');
    escaped = escaped.replace(/^## (.*?)$/gm, '<h3 style="margin: 12px 0 8px; font-weight: 600; font-size: 15px; color: var(--text-primary);">$1</h3>');
    escaped = escaped.replace(/^# (.*?)$/gm, '<h2 style="margin: 14px 0 10px; font-weight: 700; font-size: 16px; color: var(--text-primary);">$1</h2>');
    
    // Convert bold: **text**
    escaped = escaped.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Convert bullet lists
    let lines = escaped.split('\n');
    let inList = false;
    for (let i = 0; i < lines.length; i++) {
      let line = lines[i].trim();
      if (line.startsWith('- ') || line.startsWith('* ')) {
        let content = line.substring(2);
        if (!inList) {
          lines[i] = '<ul style="margin: 6px 0; padding-left: 20px; list-style-type: disc;">\n<li>' + content + '</li>';
          inList = true;
        } else {
          lines[i] = '<li>' + content + '</li>';
        }
      } else {
        if (inList) {
          lines[i] = '</ul>\n' + lines[i];
          inList = false;
        }
      }
    }
    if (inList) {
      lines.push('</ul>');
    }
    escaped = lines.join('\n');
    
    // Convert double newlines to paragraph spacers, single to line breaks
    escaped = escaped.replace(/\n\n/g, '<p style="margin: 8px 0;"></p>');
    escaped = escaped.replace(/\n/g, '<br>');
    
    return escaped;
  }
});
