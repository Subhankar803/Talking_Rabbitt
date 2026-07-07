/* ============================================================
   chat.js — conversational analytics: text + voice in, text + speech out.
   ============================================================ */

document.addEventListener("DOMContentLoaded", async () => {
  const dataset = requireDatasetOrRedirect();
  if (!dataset) return;

  const thread = document.getElementById("chat-thread");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const micBtn = document.getElementById("mic-btn");
  const speakToggle = document.getElementById("speak-toggle");
  const sessionsList = document.getElementById("chat-sessions-list");
  const newChatBtn = document.getElementById("new-chat-btn");
  const toggleHistoryBtn = document.getElementById("toggle-history-btn");
  const sidebar = document.querySelector(".chat-history-sidebar");

  let chartCounter = 0;
  let currentSessionId = null;

  const userRaw = localStorage.getItem("tr_user");
  const user = userRaw ? JSON.parse(userRaw) : null;
  const email = user ? user.email : null;

  // Restore sidebar state
  if (localStorage.getItem("tr_chat_sidebar_collapsed") === "true" && sidebar) {
    sidebar.classList.add("collapsed");
  }

  // Initialize page
  initChat();

  if (toggleHistoryBtn && sidebar) {
    toggleHistoryBtn.addEventListener("click", () => {
      sidebar.classList.toggle("collapsed");
      localStorage.setItem("tr_chat_sidebar_collapsed", sidebar.classList.contains("collapsed"));
    });
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const message = input.value.trim();
    if (!message) return;
    input.value = "";
    sendMessage(message);
  });

  if (newChatBtn) {
    newChatBtn.addEventListener("click", () => {
      startNewChat();
    });
  }

  if (micBtn) {
    if (!VoiceAssistant.isSupported()) micBtn.disabled = true;
    micBtn.addEventListener("click", () => {
      micBtn.classList.add("listening");
      VoiceAssistant.startListening({
        onResult: (transcript) => { input.value = transcript; sendMessage(transcript); },
        onEnd: () => micBtn.classList.remove("listening"),
        onError: (err) => { micBtn.classList.remove("listening"); appendSystemNote(`Voice error: ${err}`); },
      });
    });
  }

  async function initChat() {
    await loadSessions();
    const firstSession = sessionsList.querySelector(".chat-session-item");
    if (firstSession) {
      firstSession.click();
    } else {
      startNewChat();
    }
  }

  function startNewChat() {
    currentSessionId = null;
    thread.innerHTML = `
      <div class="empty-state">
        <i class="ti ti-message-chatbot" style="color:var(--signal)"></i>
        <div style="font-family:var(--font-display); font-size:18px; font-weight:600; margin-bottom:4px;">Ask Rabbitt</div>
        <div style="color:var(--text-muted); font-size:12.5px;">Ask questions, explore correlations, and forecast metrics with AI.</div>
      </div>
    `;
    document.querySelectorAll(".chat-session-item").forEach(item => item.classList.remove("active"));
  }

  async function loadSessions() {
    try {
      const url = email ? `/chat/${dataset.dataset_id}/sessions?user_email=${encodeURIComponent(email)}` : `/chat/${dataset.dataset_id}/sessions`;
      const sessions = await apiFetch(url);
      sessionsList.innerHTML = "";
      if (!sessions || sessions.length === 0) {
        sessionsList.innerHTML = `<div style="text-align:center; padding:20px 0; color:var(--text-muted); font-size:12px;">No past chats</div>`;
        return;
      }
      sessions.forEach((s) => {
        const item = document.createElement("button");
        item.className = `chat-session-item ${s.session_id === currentSessionId ? 'active' : ''}`;
        item.dataset.sessionId = s.session_id;
        item.innerHTML = `
          <i class="ti ti-message-circle"></i>
          <span class="chat-session-title" title="${escapeHtml(s.session_title)}">${escapeHtml(s.session_title)}</span>
        `;
        item.addEventListener("click", () => {
          loadSessionHistory(s.session_id);
        });
        sessionsList.appendChild(item);
      });
    } catch (err) {
      sessionsList.innerHTML = `<div style="color:var(--danger); text-align:center; font-size:12px; padding:10px 0;">Error loading sessions</div>`;
    }
  }

  async function loadSessionHistory(sessionId) {
    currentSessionId = sessionId;
    // Update active highlight
    document.querySelectorAll(".chat-session-item").forEach((item) => {
      item.classList.toggle("active", item.dataset.sessionId === sessionId);
    });

    thread.innerHTML = "";
    chartCounter = 0;

    try {
      const url = email ? `/chat/session/${sessionId}?user_email=${encodeURIComponent(email)}` : `/chat/session/${sessionId}`;
      const history = await apiFetch(url);
      history.forEach((item) => {
        appendMessage("user", item.question);
        appendMessage("assistant", item.answer, item.chart_spec, item.tools_used);
      });
      scrollToBottom();
    } catch (err) {
      appendSystemNote("Failed to load chat history.");
    }
  }

  async function sendMessage(message) {
    if (currentSessionId === null) {
      thread.innerHTML = "";
    }

    appendMessage("user", message);
    const thinkingId = appendThinking();
    scrollToBottom();

    try {
      const bodyPayload = {
        dataset_id: dataset.dataset_id,
        message,
        user_email: email
      };
      if (currentSessionId) {
        bodyPayload.session_id = currentSessionId;
      }

      const res = await apiFetch("/chat", {
        method: "POST",
        body: JSON.stringify(bodyPayload),
      });

      document.getElementById(thinkingId)?.remove();
      appendMessage("assistant", res.answer, res.chart_spec, res.tools_used);

      if (!currentSessionId) {
        currentSessionId = res.session_id;
        await loadSessions();
      }

      if (speakToggle?.checked) VoiceAssistant.speak(res.answer);
    } catch (err) {
      document.getElementById(thinkingId)?.remove();
      appendMessage("assistant", `I couldn't process that: ${err.message}`);
    }
    scrollToBottom();
  }

  function appendMessage(role, text, chartSpec, toolsUsed) {
    const bubble = document.createElement("div");
    bubble.className = `chat-msg ${role}`;
    const toolsTag = toolsUsed?.length ? `<div class="insight-tag" style="margin-bottom:8px"><i class="ti ti-tool"></i> ${toolsUsed.join(", ")}</div>` : "";

    let chartHtml = "";
    if (chartSpec && !chartSpec.error) {
      chartCounter += 1;
      const canvasId = `chat-chart-${chartCounter}`;
      chartHtml = `<div class="chat-chart-wrap"><canvas id="${canvasId}" height="140"></canvas></div>`;
      setTimeout(() => renderChart(canvasId, chartSpec), 0);
    }

    const contentHtml = role === "user" ? escapeHtml(text) : parseMarkdown(text);

    bubble.innerHTML = `
      <div class="chat-avatar">${role === "user" ? '<i class="ti ti-user"></i>' : '<i class="ti ti-sparkles"></i>'}</div>
      <div class="chat-bubble">
        ${toolsTag}
        <div>${contentHtml}</div>
        ${chartHtml}
      </div>`;
    thread.appendChild(bubble);
  }

  function appendThinking() {
    const id = `thinking-${Date.now()}`;
    const bubble = document.createElement("div");
    bubble.className = "chat-msg assistant";
    bubble.id = id;
    bubble.innerHTML = `
      <div class="chat-avatar"><i class="ti ti-sparkles"></i></div>
      <div class="chat-bubble"><span class="spinner"></span> Analyzing the data...</div>`;
    thread.appendChild(bubble);
    return id;
  }

  function appendSystemNote(text) {
    const note = document.createElement("div");
    note.className = "chat-system-note";
    note.textContent = text;
    thread.appendChild(note);
  }

  function scrollToBottom() {
    thread.scrollTop = thread.scrollHeight;
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

  // Suggested questions
  document.querySelectorAll("[data-suggest]").forEach((btn) => {
    btn.addEventListener("click", () => sendMessage(btn.dataset.suggest));
  });
});
