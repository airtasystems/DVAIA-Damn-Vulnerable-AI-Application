const API = "/api";
const LLM_PROVIDER_KEY = "dvaia_llm_provider";
let modelsConfigCache = null;
let settingsConfigCache = null;

async function loadModelsConfig() {
  if (modelsConfigCache) return modelsConfigCache;
  try {
    const r = await fetch(API + "/models", { credentials: "include" });
    modelsConfigCache = await r.json().catch(() => ({}));
  } catch (_) {
    modelsConfigCache = {};
  }
  updateProviderUI();
  return modelsConfigCache;
}

function getProvider() {
  const cfg = modelsConfigCache || {};
  if (cfg.openai_only) return "openai";
  if (cfg.gemini_only) return "gemini";
  if (cfg.ollama_enabled === false) return cfg.default_provider || "gemini";
  const stored = sessionStorage.getItem(LLM_PROVIDER_KEY);
  if (stored === "gemini" || stored === "openai" || stored === "ollama") return stored;
  return cfg.default_provider || "ollama";
}

function setProvider(provider) {
  sessionStorage.setItem(LLM_PROVIDER_KEY, provider);
  updateProviderUI();
}

function providerModels() {
  const cfg = modelsConfigCache || {};
  const p = getProvider();
  return (cfg.providers && cfg.providers[p]) || {};
}

async function getChatModelId() {
  await loadModelsConfig();
  const m = providerModels();
  return m.chat || modelsConfigCache.default || "ollama:llama3.2";
}

async function getVisionModelId() {
  await loadModelsConfig();
  const m = providerModels();
  return m.vision || modelsConfigCache.vision_model || "ollama:qwen2.5vl:7b";
}

function llmProviderPayload() {
  return { llm_provider: getProvider() };
}

function updateProviderUI() {
  const cfg = modelsConfigCache || {};
  const geminiOk = !!cfg.gemini_configured;
  const openaiOk = !!cfg.openai_configured;
  const ollamaOk = cfg.ollama_enabled !== false && !cfg.gemini_only && !cfg.openai_only;
  if (cfg.gemini_only && geminiOk) {
    sessionStorage.setItem(LLM_PROVIDER_KEY, "gemini");
  }
  if (cfg.openai_only && openaiOk) {
    sessionStorage.setItem(LLM_PROVIDER_KEY, "openai");
  }
  const provider = getProvider();
  document.querySelectorAll('input[name="llm_provider"]').forEach(el => {
    el.checked = el.value === provider;
    if (el.value === "gemini") el.disabled = !geminiOk;
    if (el.value === "openai") el.disabled = !openaiOk;
    if (el.value === "ollama") el.disabled = !ollamaOk;
  });
  const noteGeminiOnly = document.getElementById("llm_provider_note_gemini_only");
  const noteOpenaiOnly = document.getElementById("llm_provider_note_openai_only");
  const noteCloudGemini = document.getElementById("llm_provider_note_cloud");
  const noteCloudOpenai = document.getElementById("llm_provider_note_cloud_openai");
  const noteNoKeyGemini = document.getElementById("llm_provider_note_no_key");
  const noteNoKeyOpenai = document.getElementById("llm_provider_note_no_key_openai");
  [noteGeminiOnly, noteOpenaiOnly, noteCloudGemini, noteCloudOpenai, noteNoKeyGemini, noteNoKeyOpenai].forEach(el => {
    if (el) el.style.display = "none";
  });

  if (cfg.openai_only && provider === "openai") {
    if (noteOpenaiOnly) noteOpenaiOnly.style.display = "block";
  } else if (cfg.gemini_only && provider === "gemini") {
    if (noteGeminiOnly) noteGeminiOnly.style.display = "block";
  } else if (provider === "openai") {
    if (noteCloudOpenai) noteCloudOpenai.style.display = "block";
  } else if (provider === "gemini") {
    if (noteCloudGemini) noteCloudGemini.style.display = "block";
  } else if (!geminiOk && noteNoKeyGemini) {
    noteNoKeyGemini.style.display = "block";
  }
  if (!openaiOk && provider !== "openai" && noteNoKeyOpenai) {
    noteNoKeyOpenai.style.display = "block";
  }
  updateDirectSamplingUI();
}

function updateDirectSamplingUI() {
  const provider = getProvider();
  const isCloud = provider === "gemini" || provider === "openai";
  const cloudName = provider === "openai" ? "OpenAI" : "Gemini";
  const intro = document.getElementById("sampling_options_intro");
  if (intro) {
    intro.textContent = isCloud
      ? "Cloud (" + cloudName + "): temperature, top P, and max tokens are sent to the API. Top K applies to Gemini only. Repeat penalty is Ollama-only and is ignored."
      : "Local (Ollama): all options below are passed to the Ollama runtime.";
  }
  document.querySelectorAll("[data-sampling-for='ollama']").forEach(el => {
    el.style.display = isCloud ? "none" : "";
  });
  const rp = document.getElementById("opt_repeat_penalty");
  if (rp) rp.disabled = isCloud;
  const topKRow = document.getElementById("opt_top_k")?.closest(".sampling-option-row");
  if (topKRow) topKRow.style.display = provider === "openai" ? "none" : "";
}

function getDirectSamplingOptions() {
  const opts = {};
  const t = parseFloat(document.getElementById("opt_temperature")?.value);
  if (!Number.isNaN(t)) opts.temperature = t;
  const k = parseInt(document.getElementById("opt_top_k")?.value, 10);
  if (getProvider() !== "openai" && !Number.isNaN(k)) opts.top_k = k;
  const p = parseFloat(document.getElementById("opt_top_p")?.value);
  if (!Number.isNaN(p)) opts.top_p = p;
  const m = parseInt(document.getElementById("opt_max_tokens")?.value, 10);
  if (!Number.isNaN(m)) opts.max_tokens = m;
  if (getProvider() === "ollama") {
    const rp = parseFloat(document.getElementById("opt_repeat_penalty")?.value);
    if (!Number.isNaN(rp)) opts.repeat_penalty = rp;
  }
  return opts;
}

function showSettingsCacheStatus(message, isError) {
  const el = document.getElementById("settings_cache_status");
  if (!el) return;
  el.textContent = message;
  el.className = "settings-status message" + (isError ? " error" : " success");
  el.style.display = "block";
}

function showSettingsPersistStatus(message, isError) {
  const el = document.getElementById("settings_persist_status");
  if (!el) return;
  el.textContent = message;
  el.className = "settings-status message" + (isError ? " error" : " success");
  el.style.display = "block";
}

async function loadSettingsConfig() {
  try {
    const r = await fetch(API + "/settings", { credentials: "include" });
    settingsConfigCache = await r.json().catch(() => ({}));
  } catch (_) {
    settingsConfigCache = {};
  }
  updateSettingsUI();
  return settingsConfigCache;
}

function updateSettingsUI() {
  const cfg = settingsConfigCache || {};
  const resetBox = document.getElementById("settings_reset_data_on_start");
  if (resetBox) resetBox.checked = !!cfg.reset_data_on_start;
  const dbUri = document.getElementById("settings_database_uri");
  const uploadDir = document.getElementById("settings_upload_dir");
  if (dbUri && cfg.database_uri) dbUri.textContent = cfg.database_uri;
  if (uploadDir && cfg.upload_dir) uploadDir.textContent = cfg.upload_dir;
  const ephemeralWarn = document.getElementById("settings_ephemeral_warning");
  if (ephemeralWarn) {
    ephemeralWarn.style.display = cfg.using_ephemeral_storage ? "block" : "none";
  }
}

async function saveResetDataOnStart(enabled) {
  showSettingsPersistStatus("Saving…", false);
  try {
    const r = await fetch(API + "/settings", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reset_data_on_start: enabled }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      showSettingsPersistStatus(data.error || "Failed to save setting", true);
      return;
    }
    settingsConfigCache = data;
    updateSettingsUI();
    const msg = data.message || (
      enabled
        ? "Enabled: data will be cleared on next app start. Restart the container to apply."
        : "Disabled: document store and RAG will persist across restarts."
    );
    showSettingsPersistStatus(msg, false);
    appendTerminalLine("Settings: " + msg, "muted");
  } catch (err) {
    showSettingsPersistStatus(String(err.message || err), true);
  }
}

document.getElementById("settings_reset_data_on_start")?.addEventListener("change", function () {
  saveResetDataOnStart(this.checked);
});

async function clearSettingsCache(target, buttonEl) {
  if (buttonEl) buttonEl.disabled = true;
  showSettingsCacheStatus("Clearing " + target + "…", false);
  try {
    const r = await fetch(API + "/settings/clear-cache", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target }),
    });
    const contentType = r.headers.get("content-type") || "";
    let data = {};
    if (contentType.includes("application/json")) {
      data = await r.json();
    } else {
      await r.text();
    }
    if (!r.ok) {
      let err = data.error;
      if (!err) {
        if (r.status === 404) {
          err = "Cache API not found (HTTP 404). Restart the app: docker compose restart dvaia";
        } else {
          err = "Request failed (HTTP " + r.status + ")";
        }
      }
      showSettingsCacheStatus(err, true);
      return;
    }
    if (target === "gemini" || target === "openai") {
      modelsConfigCache = null;
      await loadModelsConfig();
    }
    if (target === "rag" || target === "documents" || target === "lab") {
      if (typeof loadDocuments === "function") await loadDocuments();
      const previewEl = document.getElementById("rag_retrieve_preview");
      if (previewEl) {
        previewEl.textContent = "";
        previewEl.style.display = "none";
      }
    }
    let msg = data.message || ("Cleared " + target);
    if (data.collections && data.collections.length) {
      msg += " Collections: " + data.collections.join(", ") + ".";
    }
    if (data.truncated) msg += " (path list truncated)";
    showSettingsCacheStatus(msg, false);
    appendTerminalLine("Cache: " + msg, "muted");
  } catch (err) {
    showSettingsCacheStatus(String(err.message || err), true);
  } finally {
    if (buttonEl) buttonEl.disabled = false;
  }
}

document.getElementById("btn_clear_lab_data")?.addEventListener("click", function () {
  if (
    !confirm(
      "Delete all uploaded documents, generated payload files, and RAG vectors? This empties document dropdowns."
    )
  )
    return;
  clearSettingsCache("lab", this);
});
document.getElementById("btn_clear_rag_cache")?.addEventListener("click", function () {
  if (
    !confirm(
      "Delete all RAG chunks from Qdrant only? Uploads and payload files will stay in the document lists."
    )
  )
    return;
  clearSettingsCache("rag", this);
});
document.getElementById("btn_clear_documents_cache")?.addEventListener("click", function () {
  if (!confirm("Delete all uploaded documents from the store? Generated payloads and RAG index are unchanged."))
    return;
  clearSettingsCache("documents", this);
});
document.getElementById("btn_clear_gemini_cache")?.addEventListener("click", function () {
  clearSettingsCache("gemini", this);
});
document.getElementById("btn_clear_openai_cache")?.addEventListener("click", function () {
  clearSettingsCache("openai", this);
});
document.getElementById("btn_clear_pycache")?.addEventListener("click", function () {
  clearSettingsCache("pycache", this);
});

document.querySelectorAll('input[name="llm_provider"]').forEach(el => {
  el.addEventListener("change", () => {
    if (el.checked) setProvider(el.value);
  });
});

async function getSession() {
  const r = await fetch(API + "/session", { credentials: "include" });
  return r.json();
}

// Terminal output functions
function appendTerminalLine(text, className = "") {
  const terminal = document.getElementById("terminal_output");
  if (!terminal) return;
  const line = document.createElement("div");
  if (className) line.className = "terminal-line " + className;
  line.textContent = text;
  terminal.appendChild(line);
  terminal.scrollTop = terminal.scrollHeight;
}

function appendTerminalJson(data) {
  const terminal = document.getElementById("terminal_output");
  if (!terminal) return;
  const pre = document.createElement("pre");
  pre.className = "terminal-json";
  pre.textContent = JSON.stringify(data, null, 2);
  terminal.appendChild(pre);
  terminal.scrollTop = terminal.scrollHeight;
}

function hideTerminalLog() {
  const terminal = document.getElementById("terminal_output");
  if (terminal) terminal.style.display = "none";
}

function showTerminalLog() {
  const terminal = document.getElementById("terminal_output");
  if (terminal) terminal.style.display = "block";
}

function setOutput(outputElId, text, kind, thinkingText) {
  const outputEl = document.getElementById(outputElId);
  const thinkingEl = document.getElementById(outputElId + "_thinking");
  const tabsEl = document.getElementById("tabs_" + outputElId.replace("output_", ""));

  outputEl.textContent = text || "";
  outputEl.className = "output-box";
  if (kind === "error") outputEl.classList.add("error");
  else if (kind === "loading") outputEl.classList.add("loading");
  else if (!text) outputEl.classList.add("empty");

  if (thinkingEl) {
    thinkingEl.textContent = thinkingText || "";
    thinkingEl.className = "output-box thinking";
    if (kind === "error") thinkingEl.classList.add("error");
    else if (!thinkingText) thinkingEl.classList.add("empty");
    if (thinkingText) {
      thinkingEl.style.display = "block";
      if (tabsEl) {
        tabsEl.querySelector('[data-tab="thinking"]').style.display = "inline-block";
        tabsEl.querySelector('[data-tab="thinking"]').classList.add("has-content");
      }
    } else {
      thinkingEl.style.display = "none";
      if (tabsEl) {
        tabsEl.querySelector('[data-tab="thinking"]').style.display = "none";
        tabsEl.querySelector('[data-tab="thinking"]').classList.remove("has-content");
        tabsEl.querySelector('[data-tab="answer"]').classList.add("active");
        outputEl.style.display = "block";
      }
    }
  }
  if (tabsEl) showOutputTab(tabsEl, "answer"); // Default to answer tab
}

let documentElapsedTimer = null;

function stopDocumentElapsedTimer() {
  if (documentElapsedTimer) {
    clearInterval(documentElapsedTimer);
    documentElapsedTimer = null;
  }
}

function startDocumentElapsedTimer(outputElId, prefix) {
  stopDocumentElapsedTimer();
  const outputEl = document.getElementById(outputElId);
  const started = Date.now();
  documentElapsedTimer = setInterval(() => {
    if (!outputEl) return;
    const seconds = Math.floor((Date.now() - started) / 1000);
    outputEl.textContent = prefix + " (" + seconds + "s elapsed…)";
  }, 1000);
}

function formatDurationMs(ms) {
  if (ms == null || !Number.isFinite(ms)) return "";
  if (ms < 1000) return ms + " ms";
  return (ms / 1000).toFixed(1) + " s";
}

function setLoading(outputElId, btnId, loading, message) {
  const btn = document.getElementById(btnId);
  const outputEl = document.getElementById(outputElId);
  const thinkingEl = document.getElementById(outputElId + "_thinking");
  const tabsEl = document.getElementById("tabs_" + outputElId.replace("output_", ""));

  if (btn) btn.disabled = loading;
  if (loading) {
    if (outputEl) {
      outputEl.textContent = message || "Waiting for response…";
      outputEl.className = "output-box loading";
    }
    if (thinkingEl) {
      thinkingEl.textContent = ""; // Clear thinking box when loading new response
      thinkingEl.style.display = "none"; // Hide thinking tab when loading
    }
    if (tabsEl) {
      tabsEl.querySelector('[data-tab="thinking"]').style.display = "none";
      tabsEl.querySelector('[data-tab="thinking"]').classList.remove("has-content");
      showOutputTab(tabsEl, "answer"); // Always show answer tab when loading
    }
  }
}

function showOutputTab(tabsContainer, tabId) {
  const outputIdPrefix = tabsContainer.id.replace("tabs_", "output_");
  tabsContainer.querySelectorAll(".tab-btn").forEach(btn => {
    btn.classList.remove("active");
  });
  tabsContainer.querySelector(`[data-tab="${tabId}"]`).classList.add("active");

  document.getElementById(outputIdPrefix).style.display = "none";
  document.getElementById(outputIdPrefix + "_thinking").style.display = "none";

  document.getElementById(outputIdPrefix + (tabId === "thinking" ? "_thinking" : "")).style.display = "block";
}

// Event listeners for output tabs (in main panels, not terminal history)
document.querySelectorAll(".output-tabs:not(.terminal-output-tabs)").forEach(tabsContainer => {
  tabsContainer.addEventListener("click", (e) => {
    const btn = e.target.closest(".tab-btn");
    if (!btn) return;
    showOutputTab(tabsContainer, btn.dataset.tab);
  });
});

let terminalResponseCounter = 0;

function addTerminalResponseToHistory(responseText, thinkingText, modelId) {
  const historyEl = document.getElementById("terminal_response_history");
  if (!historyEl) return;
  
  historyEl.style.display = "block";
  hideTerminalLog();
  
  terminalResponseCounter++;
  const itemId = "terminal_resp_" + terminalResponseCounter;
  
  const item = document.createElement("div");
  item.className = "terminal-response-item";
  item.id = itemId;
  
  // Model label
  const label = document.createElement("div");
  label.className = "terminal-response-label";
  label.textContent = (modelId || "Model") + " • " + new Date().toLocaleTimeString();
  item.appendChild(label);
  
  // Tabs
  const tabs = document.createElement("div");
  tabs.className = "output-tabs terminal-output-tabs";
  tabs.id = "tabs_" + itemId;
  
  const answerBtn = document.createElement("button");
  answerBtn.type = "button";
  answerBtn.className = "tab-btn active";
  answerBtn.dataset.tab = "answer";
  answerBtn.textContent = "Answer";
  
  const thinkingBtn = document.createElement("button");
  thinkingBtn.type = "button";
  thinkingBtn.className = "tab-btn";
  thinkingBtn.dataset.tab = "thinking";
  thinkingBtn.textContent = "Thinking";
  
  tabs.appendChild(answerBtn);
  tabs.appendChild(thinkingBtn);
  
  if (!thinkingText) {
    thinkingBtn.style.display = "none";
  }
  
  // Content boxes
  const answerBox = document.createElement("div");
  answerBox.className = "terminal-response-box terminal-answer";
  answerBox.id = itemId + "_answer";
  answerBox.textContent = responseText || "";
  
  const thinkingBox = document.createElement("div");
  thinkingBox.className = "terminal-response-box terminal-thinking";
  thinkingBox.id = itemId + "_thinking";
  thinkingBox.style.display = "none";
  thinkingBox.textContent = thinkingText || "";
  
  item.appendChild(tabs);
  item.appendChild(answerBox);
  item.appendChild(thinkingBox);
  
  // Tab click handler
  tabs.addEventListener("click", (e) => {
    const btn = e.target.closest(".tab-btn");
    if (!btn) return;
    tabs.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    if (btn.dataset.tab === "answer") {
      answerBox.style.display = "block";
      thinkingBox.style.display = "none";
    } else {
      answerBox.style.display = "none";
      thinkingBox.style.display = "block";
    }
  });
  
  historyEl.appendChild(item);
  historyEl.scrollTop = historyEl.scrollHeight;
}

function clearTerminalResponseHistory() {
  const historyEl = document.getElementById("terminal_response_history");
  if (historyEl) {
    historyEl.innerHTML = "";
    historyEl.style.display = "none";
  }
  terminalResponseCounter = 0;
}

const DEFAULT_PANEL = "payloads";

function showPanel(panelId) {
  document.querySelectorAll("#main_body .panel").forEach(p => p.classList.remove("active"));
  document.querySelectorAll("#main_menu li").forEach(li => li.classList.remove("selected"));
  const panel = document.getElementById("panel_" + panelId);
  const menuItem = document.querySelector('#main_menu li[data-panel="' + panelId + '"]');
  if (panel) panel.classList.add("active");
  if (menuItem) menuItem.classList.add("selected");
  if (panelId === "settings") {
    loadModelsConfig();
    loadSettingsConfig();
  }
  if (panelId === "direct") {
    updateDirectSamplingUI();
  }
}

function updateSessionUI(data) {
  const user = data && data.user;
  const userLabel = document.getElementById("user_label");
  const btnLogout = document.getElementById("btn_logout");
  if (user) {
    userLabel.textContent = "Logged in as " + user.username + (user.mfa_verified ? "" : " (MFA required)");
    btnLogout.style.display = "inline-block";
    document.getElementById("panel_login").classList.remove("active");
    if (!user.mfa_verified) {
      document.querySelectorAll("#main_body .panel").forEach(p => p.classList.remove("active"));
      document.getElementById("panel_mfa").classList.add("active");
    } else {
      document.getElementById("panel_mfa").classList.remove("active");
      if (!document.querySelector("#main_body .panel.active")) showPanel(DEFAULT_PANEL);
    }
  } else {
    userLabel.textContent = "";
    btnLogout.style.display = "none";
    document.getElementById("panel_login").classList.remove("active");
    document.getElementById("panel_mfa").classList.remove("active");
  }
}

document.getElementById("main_menu").addEventListener("click", (e) => {
  const li = e.target.closest("li[data-panel]");
  if (li) {
    e.preventDefault();
    showPanel(li.dataset.panel);
    if (li.dataset.panel === "rag") loadRagDocuments();
    if (li.dataset.panel === "payloads") loadPayloadsList();
    if (li.dataset.panel === "document" || li.dataset.panel === "rag") loadDocuments();
  }
});

// Login button removed from UI

document.getElementById("btn_logout").addEventListener("click", async () => {
  await fetch(API + "/logout", { method: "POST", credentials: "include" });
  const data = await getSession();
  updateSessionUI(data);
  showPanel(DEFAULT_PANEL);
});

document.getElementById("form_login").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = document.getElementById("login_error");
  errEl.style.display = "none";
  const username = document.getElementById("login_username").value.trim();
  const password = document.getElementById("login_password").value;
  const r = await fetch(API + "/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ username, password }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    errEl.textContent = data.error || "Login failed";
    errEl.style.display = "block";
    return;
  }
  const session = await getSession();
  updateSessionUI(session);
  if (session.user && !session.user.mfa_verified) showPanel("mfa");
  else showPanel(DEFAULT_PANEL);
});

document.getElementById("form_mfa").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = document.getElementById("mfa_error");
  errEl.style.display = "none";
  const code = document.getElementById("mfa_code").value.trim();
  const r = await fetch(API + "/mfa", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ code }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    errEl.textContent = data.error || "Invalid code";
    errEl.style.display = "block";
    return;
  }
  const session = await getSession();
  updateSessionUI(session);
  showPanel(DEFAULT_PANEL);
});

document.getElementById("send_direct").addEventListener("click", async () => {
  const prompt = document.getElementById("prompt_direct").value.trim();
  if (!prompt) return;
  setLoading("output_direct", "send_direct", true);
  const model_id = await getChatModelId();
  const options = getDirectSamplingOptions();
  const body = { prompt, model_id, ...llmProviderPayload() };
  if (Object.keys(options).length) body.options = options;
  appendTerminalLine("Direct chat request", "muted");
  appendTerminalLine("Provider: " + getProvider(), "muted");
  appendTerminalLine("Model: " + model_id, "muted");
  appendTerminalLine("Options: " + (Object.keys(options).length ? JSON.stringify(options) : "(none)"), "muted");
  try {
    const r = await fetch(API + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      setOutput("output_direct", data.error || r.statusText, "error");
      appendTerminalLine("Direct chat (error)", "fail");
      appendTerminalJson(data);
      return;
    }
    setOutput("output_direct", data.response ?? "", "", data.thinking ?? "");
    addTerminalResponseToHistory(data.response ?? "", data.thinking ?? "", model_id);
    if (data.duration_ms != null) {
      appendTerminalLine("Duration: " + data.duration_ms + " ms", "muted");
    }
  } catch (err) {
    setOutput("output_direct", err.message || "Network error", "error");
    appendTerminalLine("Direct chat: " + (err.message || "Network error"), "fail");
  } finally {
    setLoading("output_direct", "send_direct", false);
  }
});

function appendSelectSectionHeader(select, label) {
  const header = document.createElement("option");
  header.disabled = true;
  header.textContent = label;
  header.value = "";
  select.appendChild(header);
}

function populateDocumentSelect(selectId, data) {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  sel.innerHTML = '<option value="">-- Select a document --</option>';
  const uploaded = data.documents || [];
  const payloads = data.payload_files || [];
  if (uploaded.length) {
    appendSelectSectionHeader(sel, "Uploaded documents");
    uploaded.forEach(d => {
      const opt = document.createElement("option");
      opt.value = String(d.id);
      opt.textContent = d.filename + " (id " + d.id + ")";
      opt.dataset.ragSource = d.filename || ("document_" + d.id);
      sel.appendChild(opt);
    });
  }
  if (payloads.length) {
    appendSelectSectionHeader(sel, "Generated payloads");
    payloads.forEach(f => {
      const rel = f.relative_path || f.name;
      const opt = document.createElement("option");
      opt.value = "payload:" + rel;
      opt.textContent = rel + (f.size != null ? " (" + f.size + " B)" : "");
      opt.dataset.ragSource = rel;
      sel.appendChild(opt);
    });
  }
}

function parseDocumentSelection(value) {
  if (!value) return null;
  if (value.startsWith("payload:")) {
    return {
      context_from: "payload",
      payload_relative_path: value.slice("payload:".length),
    };
  }
  const documentId = parseInt(value, 10);
  if (!Number.isFinite(documentId)) return null;
  return { context_from: "upload", document_id: documentId };
}

async function loadDocuments() {
  const r = await fetch(API + "/documents", { credentials: "include" });
  const data = await r.json().catch(() => ({}));
  populateDocumentSelect("doc_select", data);
  populateDocumentSelect("rag_doc_select", data);
}

document.getElementById("btn_upload").addEventListener("click", async () => {
  const input = document.getElementById("doc_file");
  const status = document.getElementById("upload_status");
  if (!input.files || !input.files[0]) {
    status.textContent = "Select a file first.";
    return;
  }
  status.textContent = "Uploading…";
  const form = new FormData();
  form.append("file", input.files[0]);
  const r = await fetch(API + "/documents/upload", {
    method: "POST",
    credentials: "include",
    body: form,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    status.textContent = data.error || "Upload failed";
    return;
  }
  status.textContent = "Uploaded (id " + data.document_id + ")";
  input.value = "";
  loadDocuments();
});

async function previewDocumentExtraction() {
  const previewEl = document.getElementById("doc_extract_preview");
  const visionEl = document.getElementById("doc_use_vision");
  const visionHint = document.getElementById("doc_vision_hint");
  const selection = parseDocumentSelection(document.getElementById("doc_select").value);
  if (!previewEl) return;
  if (!selection) {
    previewEl.style.display = "none";
    previewEl.textContent = "";
    setDocumentAudioPreview(null, null);
    if (visionEl) {
      visionEl.checked = false;
      visionEl.disabled = true;
    }
    if (visionHint) {
      visionHint.textContent = "Images: optional vision mode. Audio: Whisper transcription. PDF/text use text extraction.";
    }
    return;
  }
  previewEl.style.display = "block";
  previewEl.textContent = "Running extraction preview…";
  try {
    const params = new URLSearchParams();
    if (selection.context_from === "payload") {
      params.set("payload_relative_path", selection.payload_relative_path);
    } else {
      params.set("document_id", String(selection.document_id));
    }
    const r = await fetch(API + "/documents/extract-preview?" + params.toString(), { credentials: "include" });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      previewEl.textContent = data.error || "Could not preview extracted text.";
      return;
    }
    const text = (data.text || "").trim();
    const preview = text ? text.slice(0, 400) + (text.length > 400 ? "…" : "") : "(no text extracted)";
    const warning = data.warning ? ("Warning: " + data.warning + "\n\n") : "";
    const backend = data.extraction_backend
      ? ("Backend: " + data.extraction_backend + (data.whisper_model ? " (" + data.whisper_model + ")" : "") + "\n")
      : (data.transcription_backend
        ? ("Transcription: " + data.transcription_backend + (data.whisper_model ? " (" + data.whisper_model + ")" : "") + "\n")
        : "");
    const timing = data.extraction_ms != null ? ("Completed in " + formatDurationMs(data.extraction_ms) + "\n\n") : "";
    const ocrHint = data.ocr_hint ? ("Note: " + data.ocr_hint + "\n\n") : "";
    previewEl.textContent = warning + backend + timing + ocrHint + "Extracted text preview (" + (data.chars || 0) + " chars):\n" + preview;

    if (visionEl) {
      const supportsVision = !!data.supports_vision;
      visionEl.disabled = !supportsVision;
      if (!supportsVision) visionEl.checked = false;
    }
    if (visionHint) {
      if (data.supports_vision) {
        visionHint.textContent = "Image selected — OCR preview above (~3–10s). Vision mode sends pixels to qwen2.5vl (~30–90s).";
      } else if (data.file_kind === "audio") {
        visionHint.textContent = "Audio selected — use the player below to listen; the LLM receives the Whisper transcript only.";
      } else {
        visionHint.textContent = "Vision mode is only available for image files (" + (data.file_kind || "other") + " selected). PDF, text, and audio use text extraction.";
      }
    }
    setDocumentAudioPreview(selection, data.file_kind);
  } catch (err) {
    previewEl.textContent = err.message || "Could not preview extracted text.";
    setDocumentAudioPreview(selection, null);
  }
}

document.getElementById("doc_select").addEventListener("change", previewDocumentExtraction);

document.getElementById("send_document").addEventListener("click", async () => {
  const selected = document.getElementById("doc_select").value;
  const prompt = document.getElementById("prompt_document").value.trim();
  if (!prompt) return;
  const selection = parseDocumentSelection(selected);
  if (!selection) {
    setOutput("output_document", "Select a document or generated payload first.", "error");
    return;
  }
  const useVision = document.getElementById("doc_use_vision") && document.getElementById("doc_use_vision").checked;
  const visionModelId = await getVisionModelId();
  if (useVision) {
    setLoading(
      "output_document",
      "send_document",
      true,
      "Vision model processing — typically 30–90 seconds…"
    );
    startDocumentElapsedTimer(
      "output_document",
      "Vision model processing — typically 30–90 seconds"
    );
  } else {
    setLoading("output_document", "send_document", true);
  }
  try {
    const body = {
      prompt,
      ...selection,
      context_mode: useVision ? "vision" : "extract",
      model_id: await getChatModelId(),
      ...llmProviderPayload(),
    };
    if (useVision) body.vision_model_id = visionModelId;
    const r = await fetch(API + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      setOutput("output_document", data.error || r.statusText, "error");
      appendTerminalLine("Document chat (error)", "fail");
      appendTerminalJson(data);
      return;
    }
    setOutput("output_document", data.response ?? "", "", data.thinking ?? "");
    if (data.duration_ms != null) {
      appendTerminalLine(
        "Request completed in " + formatDurationMs(data.duration_ms)
          + (data.context_mode === "vision" ? " (vision model)" : ""),
        "muted"
      );
    }
    if (data.context_mode) {
      appendTerminalLine("Document context mode: " + data.context_mode + (data.vision_model ? " (" + data.vision_model + ")" : ""), "muted");
    }
    if (data.transcription_backend) {
      appendTerminalLine(
        "Audio transcription: " + data.transcription_backend + (data.whisper_model ? " (" + data.whisper_model + ")" : ""),
        "muted"
      );
    }
    if (data.context_warning) {
      appendTerminalLine("Document extraction warning: " + data.context_warning, "fail");
    }
    if (data.context_extracted != null) {
      const preview = String(data.context_extracted).slice(0, 500);
      appendTerminalLine("Context sent to model (" + String(data.context_extracted).length + " chars): " + preview, "muted");
    }
    addTerminalResponseToHistory(data.response ?? "", data.thinking ?? "", "Document");
  } catch (err) {
    setOutput("output_document", err.message || "Network error", "error");
    appendTerminalLine("Document chat: " + (err.message || "Network error"), "fail");
  } finally {
    stopDocumentElapsedTimer();
    setLoading("output_document", "send_document", false);
  }
});

function resolveWebUrl(raw) {
  let url = (raw || "").trim();
  if (!url) return "";
  if (!url.startsWith("http") && !url.startsWith("/")) url = "/" + url;
  if (url.startsWith("/")) url = window.location.origin + url;
  return url;
}

async function previewWebFetch() {
  const previewEl = document.getElementById("web_fetch_preview");
  const urlInput = document.getElementById("web_url");
  if (!previewEl || !urlInput) return;
  const url = resolveWebUrl(urlInput.value);
  if (!url) {
    previewEl.style.display = "none";
    previewEl.textContent = "";
    return;
  }
  previewEl.style.display = "block";
  previewEl.textContent = "Fetching and extracting page text…";
  try {
    const params = new URLSearchParams({ url });
    const r = await fetch(API + "/web/fetch-preview?" + params.toString(), { credentials: "include" });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      previewEl.textContent = data.error || "Could not fetch URL.";
      return;
    }
    const warning = data.warning ? ("Warning: " + data.warning + "\n\n") : "";
    const timing = data.extraction_ms != null
      ? ("Fetch: " + (data.fetch_backend || "?") + " + " + (data.extractor || "extract") + " in " + formatDurationMs(data.extraction_ms) + "\n\n")
      : "";
    const title = data.title ? ("Title: " + data.title + "\n") : "";
    const meta = data.meta_description ? ("Meta: " + data.meta_description + "\n\n") : "";
    const visible = data.visible_text
      ? ("Visible text:\n" + data.visible_text.slice(0, 500) + (data.visible_text.length > 500 ? "…" : "") + "\n\n")
      : "";
    const hidden = data.hidden_text
      ? ("Hidden HTML text (sent to model):\n" + data.hidden_text.slice(0, 500) + (data.hidden_text.length > 500 ? "…" : "") + "\n\n")
      : "";
    previewEl.textContent = warning + timing + title + meta + visible + hidden
      + "Full context preview (" + (data.chars || 0) + " chars):\n"
      + ((data.preview || data.text || "").slice(0, 600) || "(empty)");
  } catch (err) {
    previewEl.textContent = err.message || "Could not fetch URL.";
  }
}

document.getElementById("web_url").addEventListener("change", previewWebFetch);
document.getElementById("web_url").addEventListener("blur", previewWebFetch);

document.getElementById("send_web").addEventListener("click", async () => {
  let url = resolveWebUrl(document.getElementById("web_url").value.trim());
  const prompt = document.getElementById("prompt_web").value.trim();
  if (!prompt) return;
  if (!url) {
    setOutput("output_web", "Enter a URL (e.g. /evil/ or https://...).", "error");
    return;
  }
  setLoading("output_web", "send_web", true, "Fetching URL and querying model…");
  try {
    const body = {
      prompt,
      context_from: "url",
      url,
      model_id: await getChatModelId(),
      ...llmProviderPayload(),
    };
    const r = await fetch(API + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      setOutput("output_web", data.error || r.statusText, "error");
      appendTerminalLine("Web chat (error)", "fail");
      appendTerminalJson(data);
      return;
    }
    if (data.context_warning && !data.context_extracted) {
      setOutput("output_web", data.context_warning, "error");
    } else {
      setOutput("output_web", data.response ?? "", "", data.thinking ?? "");
    }
    if (data.duration_ms != null) {
      appendTerminalLine("Web request completed in " + formatDurationMs(data.duration_ms), "muted");
    }
    if (data.context_warning) {
      appendTerminalLine("Web fetch warning: " + data.context_warning, "fail");
    }
    if (data.context_extracted != null) {
      const preview = String(data.context_extracted).slice(0, 500);
      appendTerminalLine("Page context sent to model (" + String(data.context_extracted).length + " chars): " + preview, "muted");
    }
    addTerminalResponseToHistory(data.response ?? "", data.thinking ?? "", "Web");
  } catch (err) {
    setOutput("output_web", err.message || "Network error", "error");
    appendTerminalLine("Web chat: " + (err.message || "Network error"), "fail");
  } finally {
    setLoading("output_web", "send_web", false);
  }
});

// Agentic: multi-round conversation state
let agenticMessages = [];
let agenticThinking = "";
let agenticLastToolCalls = [];

async function getAgenticModelId() {
  await loadModelsConfig();
  const m = providerModels();
  return m.agentic || modelsConfigCache.agentic_model || "qwen3:0.6b";
}

function parseThinkingIntoSteps(thinkingText) {
  if (!thinkingText || !thinkingText.trim()) return [];
  const steps = [];
  const blocks = thinkingText.split(/\s*---\s*Step\s+\d+\s*---\s*/i).filter(B => B.trim());
  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i].trim();
    const stepNum = i + 1;
    let reasoning = "";
    let thought = "";
    const actions = [];
    const lines = block.split("\n");
    let section = "";
    let currentAction = null;
    for (let j = 0; j < lines.length; j++) {
      const line = lines[j];
      if (line.startsWith("Reasoning (CoT):")) {
        section = "reasoning";
        continue;
      }
      if (line.startsWith("Thought:")) {
        section = "thought";
        thought = line.slice(7).trim();
        continue;
      }
      if (line.startsWith("Action:")) {
        if (currentAction) actions.push(currentAction);
        currentAction = { name: line.slice(7).trim(), input: "", observation: "" };
        section = "action";
        continue;
      }
      if (line.startsWith("Action Input:")) {
        if (currentAction) currentAction.input = line.slice(12).trim();
        continue;
      }
      if (line.startsWith("Observation:")) {
        section = "observation";
        if (currentAction) currentAction.observation = line.slice(12).trim();
        continue;
      }
      if (section === "reasoning") reasoning += (reasoning ? "\n" : "") + line;
      else if (section === "observation" && currentAction) currentAction.observation += (currentAction.observation ? "\n" : "") + line;
    }
    if (currentAction) actions.push(currentAction);
    steps.push({ stepNum, reasoning, thought, actions });
  }
  return steps;
}

function renderAgenticConversation() {
  const container = document.getElementById("agentic_conversation");
  if (!container) return;
  if (agenticMessages.length === 0) {
    container.innerHTML = "Conversation will appear here. Send a message to start.";
    container.classList.remove("has-rounds");
    return;
  }
  container.classList.add("has-rounds");
  let html = "";
  for (let i = 0; i < agenticMessages.length; i++) {
    const msg = agenticMessages[i];
    const isLast = i === agenticMessages.length - 1;
    const showThinking = isLast && msg.role === "assistant" && agenticThinking;
    if (msg.role === "user") {
      html += '<div class="agentic-round"><div class="agentic-msg-user"><div class="agentic-role">User</div>' + escapeHtml(msg.content) + "</div></div>";
    } else {
      html += '<div class="agentic-round"><div class="agentic-msg-assistant"><div class="agentic-role">Assistant</div>' + escapeHtml(msg.content || "");
      if (isLast && msg.role === "assistant" && agenticLastToolCalls && agenticLastToolCalls.length > 0) {
        html += '<div class="agentic-tools-used">Tools used: ' + escapeHtml(agenticLastToolCalls.join(", ")) + '</div>';
      }
      if (showThinking) {
        const steps = parseThinkingIntoSteps(agenticThinking);
        const stepId = "agentic_steps_" + Date.now();
        html += '<div class="agentic-thinking-toggle" data-toggle="' + stepId + '">▼ Show thinking (' + steps.length + " step(s))</div>";
        html += '<div id="' + stepId + '" class="agentic-thinking-steps" style="display:none;">';
        steps.forEach(function(s) {
          html += '<div class="agentic-step-block"><div class="agentic-step-title">Step ' + s.stepNum + '</div>';
          if (s.reasoning) html += '<div class="agentic-step-reasoning">Reasoning (CoT): ' + escapeHtml(s.reasoning) + '</div>';
          if (s.thought) html += '<div class="agentic-step-thought">Thought: ' + escapeHtml(s.thought) + '</div>';
          s.actions.forEach(function(a) {
            html += '<div class="agentic-step-action">Action: ' + escapeHtml(a.name) + '</div>';
            if (a.input) html += '<div class="agentic-step-action">Action Input: ' + escapeHtml(a.input) + '</div>';
            if (a.observation) html += '<div class="agentic-step-observation">Observation: ' + escapeHtml(a.observation) + '</div>';
          });
          html += '</div>';
        });
        html += '</div>';
      }
      html += "</div></div>";
    }
  }
  container.innerHTML = html;
  container.scrollTop = container.scrollHeight;
  container.querySelectorAll(".agentic-thinking-toggle").forEach(function(el) {
    el.addEventListener("click", function() {
      const target = document.getElementById(el.getAttribute("data-toggle"));
      if (!target) return;
      if (target.style.display === "none") {
        target.style.display = "block";
        el.textContent = el.textContent.replace("▼", "▲").replace("Show", "Hide");
      } else {
        target.style.display = "none";
        el.textContent = el.textContent.replace("▲", "▼").replace("Hide", "Show");
      }
    });
  });
}

function getAgenticToolNames() {
  const checked = document.querySelectorAll(".agentic-tool-cb:checked");
  const all = document.querySelectorAll(".agentic-tool-cb");
  if (checked.length === 0 || checked.length === all.length) return null;  // all or none = use default (all)
  return Array.from(checked).map(el => el.value);
}

document.querySelectorAll(".agentic-scenario-btn").forEach(function(btn) {
  btn.addEventListener("click", function() {
    const promptEl = document.getElementById("prompt_agentic");
    if (promptEl) promptEl.value = btn.getAttribute("data-prompt") || "";
  });
});

document.getElementById("send_agentic").addEventListener("click", async () => {
  const prompt = document.getElementById("prompt_agentic").value.trim();
  if (!prompt) return;
  setLoading("output_agentic", "send_agentic", true);
  appendTerminalLine("Agentic chat request", "muted");
  const modelId = await getAgenticModelId();
  const toolNames = getAgenticToolNames();
  const maxSteps = parseInt(document.getElementById("agentic_max_steps") && document.getElementById("agentic_max_steps").value, 10) || 15;
  const timeout = parseInt(document.getElementById("agentic_timeout") && document.getElementById("agentic_timeout").value, 10) || 120;
  const body = {
    prompt,
    model_id: modelId,
    messages: agenticMessages,
    max_steps: Math.max(1, Math.min(50, maxSteps)),
    timeout: Math.max(10, Math.min(300, timeout)),
    ...llmProviderPayload(),
  };
  if (toolNames) body.tool_names = toolNames;
  try {
    const r = await fetch(API + "/agent/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      setOutput("output_agentic", data.error || r.statusText, "error");
      appendTerminalLine("Agentic (error)", "fail");
      appendTerminalJson(data);
      return;
    }
    agenticMessages = data.messages || [];
    agenticThinking = data.thinking || "";
    agenticLastToolCalls = data.tool_calls || [];
    renderAgenticConversation();
    setOutput("output_agentic", data.response ?? "", "", data.thinking ?? "");
    addTerminalResponseToHistory(data.response ?? "", data.thinking ?? "", "Agentic (" + modelId + ")");
    document.getElementById("prompt_agentic").value = "";
  } catch (err) {
    setOutput("output_agentic", err.message || "Network error", "error");
    appendTerminalLine("Agentic: " + (err.message || "Network error"), "fail");
  } finally {
    setLoading("output_agentic", "send_agentic", false);
  }
});

document.getElementById("agentic_new_conversation").addEventListener("click", function() {
  agenticMessages = [];
  agenticThinking = "";
  agenticLastToolCalls = [];
  renderAgenticConversation();
  document.getElementById("prompt_agentic").value = "";
  setOutput("output_agentic", "", "empty", "");
});

document.getElementById("send_template").addEventListener("click", async () => {
  const template = document.getElementById("template_text").value.trim();
  const userInput = document.getElementById("template_user_input").value;
  if (!template) return;
  setLoading("output_template", "send_template", true);
  try {
    const r = await fetch(API + "/chat-with-template", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        template,
        user_input: userInput,
        model_id: await getChatModelId(),
        ...llmProviderPayload(),
      }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      setOutput("output_template", data.error || r.statusText, "error");
      appendTerminalLine("Template chat (error)", "fail");
      appendTerminalJson(data);
      return;
    }
    setOutput("output_template", data.response ?? "", "", data.thinking ?? "");
    addTerminalResponseToHistory(data.response ?? "", data.thinking ?? "", "Template");
  } catch (err) {
    setOutput("output_template", err.message || "Network error", "error");
    appendTerminalLine("Template: " + (err.message || "Network error"), "fail");
  } finally {
    setLoading("output_template", "send_template", false);
  }
});

async function loadRagDocuments() {
  await loadDocuments();
}

document.getElementById("rag_btn_add_chunk").addEventListener("click", async () => {
  const source = document.getElementById("rag_chunk_source").value.trim() || "manual";
  const content = document.getElementById("rag_chunk_content").value.trim();
  const statusEl = document.getElementById("rag_add_chunk_status");
  if (!content) {
    statusEl.textContent = "Enter content.";
    return;
  }
  statusEl.textContent = "Adding…";
  try {
    const r = await fetch(API + "/rag/chunks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ source, content, ...llmProviderPayload() }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      statusEl.textContent = data.error || r.statusText || "Failed";
      return;
    }
    statusEl.textContent = "Added (id " + (data.id || "") + ").";
    document.getElementById("rag_chunk_content").value = "";
  } catch (err) {
    statusEl.textContent = err.message || "Network error";
  }
});

document.getElementById("rag_btn_add_document").addEventListener("click", async () => {
  const selected = document.getElementById("rag_doc_select").value;
  const statusEl = document.getElementById("rag_add_doc_status");
  const selection = parseDocumentSelection(selected);
  if (!selection) {
    statusEl.textContent = "Select a document or generated payload first.";
    return;
  }
  statusEl.textContent = "Adding…";
  try {
    const ragProviderBody = llmProviderPayload();
    const r = selection.context_from === "payload"
      ? await fetch(API + "/rag/add-payload", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ payload_relative_path: selection.payload_relative_path, ...ragProviderBody }),
        })
      : await fetch(API + "/rag/add-document/" + selection.document_id, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify(ragProviderBody),
        });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      statusEl.textContent = data.error || r.statusText || "Failed";
      return;
    }
    const source = data.source || "document";
    const len = data.content_length != null ? data.content_length : 0;
    const n = data.chunks_added != null ? data.chunks_added : 0;
    statusEl.textContent = "Added \u201c" + source + "\u201d as " + n + " chunk(s) with embeddings. Query with natural language (e.g. Who created this document?).";
  } catch (err) {
    statusEl.textContent = err.message || "Network error";
  }
});

function getRagSourceFilter() {
  const limitEl = document.getElementById("rag_limit_source");
  if (limitEl && !limitEl.checked) return null;
  const sel = document.getElementById("rag_doc_select");
  if (!sel || !sel.value) return undefined;
  const opt = sel.options[sel.selectedIndex];
  return opt && opt.dataset.ragSource ? opt.dataset.ragSource : null;
}

async function previewRagRetrieval() {
  const previewEl = document.getElementById("rag_retrieve_preview");
  const promptEl = document.getElementById("rag_chat_prompt");
  if (!previewEl || !promptEl) return;
  const q = promptEl.value.trim();
  if (!q) {
    previewEl.style.display = "none";
    previewEl.textContent = "";
    return;
  }
  const sourceFilter = getRagSourceFilter();
  if (sourceFilter === undefined) {
    previewEl.style.display = "block";
    previewEl.textContent =
      "Limit to selected document is checked, but no document is selected. Pick one from the dropdown or uncheck the limit.";
    return;
  }
  previewEl.style.display = "block";
  previewEl.textContent = "Searching indexed chunks…";
  try {
    const params = new URLSearchParams({ q, llm_provider: getProvider() });
    if (sourceFilter) params.set("rag_source", sourceFilter);
    const r = await fetch(API + "/rag/retrieve-preview?" + params.toString(), { credentials: "include" });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      previewEl.textContent = data.error || "Could not preview retrieval.";
      return;
    }
    const scope = data.rag_source
      ? ("Source filter: " + data.rag_source + "\n\n")
      : "Source filter: (all indexed sources)\n\n";
    const warning = data.warning ? ("Warning: " + data.warning + "\n\n") : "";
    const count = (data.chunks || []).length;
    const header = scope + warning + "Retrieved " + count + " chunk(s):\n\n";
    const body = (data.formatted_preview || "").slice(0, 1200);
    previewEl.textContent = header + (body || "(no matching chunks)") + (body.length >= 1200 ? "…" : "");
  } catch (err) {
    previewEl.textContent = err.message || "Could not preview retrieval.";
  }
}

document.getElementById("rag_btn_preview").addEventListener("click", previewRagRetrieval);
document.getElementById("rag_chat_prompt").addEventListener("blur", previewRagRetrieval);
document.getElementById("rag_limit_source").addEventListener("change", previewRagRetrieval);
document.getElementById("rag_doc_select").addEventListener("change", previewRagRetrieval);

document.getElementById("rag_btn_chat").addEventListener("click", async () => {
  const prompt = document.getElementById("rag_chat_prompt").value.trim();
  if (!prompt) {
    setOutput("output_rag", "Enter your prompt.", "error");
    return;
  }
  const sourceFilter = getRagSourceFilter();
  if (sourceFilter === undefined) {
    setOutput(
      "output_rag",
      "Limit to selected document is checked, but no document is selected. Pick one or uncheck the limit.",
      "error",
    );
    return;
  }
  setLoading("output_rag", "rag_btn_chat", true);
  try {
    const body = {
      prompt,
      context_from: "rag",
      rag_query: prompt,
      model_id: await getChatModelId(),
      ...llmProviderPayload(),
    };
    if (sourceFilter) body.rag_source = sourceFilter;
    const r = await fetch(API + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      setOutput("output_rag", data.error || r.statusText, "error");
      appendTerminalLine("RAG chat (error)", "fail");
      appendTerminalJson(data);
      return;
    }
    if (data.context_warning && !data.context_extracted) {
      setOutput("output_rag", data.context_warning, "error");
    } else {
      setOutput("output_rag", data.response ?? "", "", data.thinking ?? "");
    }
    if (data.rag_source_filter) {
      appendTerminalLine("RAG source filter: " + data.rag_source_filter, "muted");
    } else {
      appendTerminalLine("RAG source filter: (all indexed sources)", "muted");
    }
    if (data.rag_chunk_count != null) {
      appendTerminalLine("RAG chunks retrieved: " + data.rag_chunk_count, "muted");
    }
    if (data.context_warning) {
      appendTerminalLine("RAG warning: " + data.context_warning, "fail");
    }
    if (data.context_extracted != null) {
      const preview = String(data.context_extracted).slice(0, 500);
      appendTerminalLine(
        "Retrieved context sent to model (" + String(data.context_extracted).length + " chars): " + preview,
        "muted",
      );
    }
    addTerminalResponseToHistory(data.response ?? "", data.thinking ?? "", "RAG");
  } catch (err) {
    setOutput("output_rag", err.message || "Network error", "error");
    appendTerminalLine("RAG chat: " + (err.message || "Network error"), "fail");
  } finally {
    setLoading("output_rag", "rag_btn_chat", false);
  }
});

function showPayloadOptions(assetType) {
  document.querySelectorAll(".payload-type-options").forEach(el => { el.style.display = "none"; });
  const show = (id) => {
    const el = document.getElementById(id);
    if (el) el.style.display = "block";
  };
  if (assetType === "text") show("payload_options_text");
  else if (assetType === "csv") {
    show("payload_options_csv");
    toggleCsvMode();
  }
  else if (assetType === "pdf") show("payload_options_pdf");
  else if (assetType === "image") {
    show("payload_options_image");
    if (typeof schedulePayloadPreview === "function") schedulePayloadPreview();
  }
  else if (assetType === "pdf_metadata") show("payload_options_pdf_metadata");
  else if (assetType === "qr") show("payload_options_qr");
  else if (assetType === "audio_synthetic") show("payload_options_audio_synthetic");
  else if (assetType === "audio_tts") show("payload_options_audio_tts");
}
document.getElementById("payload_asset_type").addEventListener("change", () => {
  showPayloadOptions(document.getElementById("payload_asset_type").value);
});
showPayloadOptions("text");

function toggleCsvMode() {
  const isCustom = document.getElementById("csv_mode_custom") && document.getElementById("csv_mode_custom").checked;
  const customSection = document.getElementById("csv_custom_section");
  const dummySection = document.getElementById("csv_dummy_section");
  const dummyRows = document.getElementById("csv_dummy_rows_section");
  const dummyFaker = document.getElementById("csv_dummy_faker_section");
  if (customSection) customSection.style.display = isCustom ? "block" : "none";
  if (dummySection) dummySection.style.display = isCustom ? "none" : "block";
  if (dummyRows) dummyRows.style.display = isCustom ? "none" : "block";
  if (dummyFaker) dummyFaker.style.display = isCustom ? "none" : "block";
}
document.querySelectorAll("input[name=csv_mode]").forEach(function(radio) {
  radio.addEventListener("change", toggleCsvMode);
});

document.querySelectorAll(".payload-line-tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    const tabId = btn.dataset.tab;
    const isPdfTab = btn.classList.contains("payload-pdf-tab");
    document.querySelectorAll(isPdfTab ? ".payload-pdf-tab" : ".payload-line-tab-btn:not(.payload-pdf-tab)").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(isPdfTab ? ".payload-pdf-panel" : ".payload-line-tab:not(.payload-pdf-panel)").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    const panel = document.getElementById("payload_tab_" + tabId);
    if (panel) panel.classList.add("active");
    if (tabId === "preview") schedulePayloadPreview();
  });
});

var payloadPreviewTimeout;
var PAYLOAD_COLOR_NAMES = { black: "#000000", white: "#ffffff", red: "#ff0000", green: "#008000", blue: "#0000ff", pink: "#ffc0cb", gray: "#808080", grey: "#808080", transparent: "#000000" };
function parsePayloadColor(str) {
  if (!str || typeof str !== "string") return { r: 0, g: 0, b: 0 };
  str = str.trim();
  if (str.startsWith("#")) {
    var hex = str.slice(1);
    if (hex.length === 3) hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
    if (hex.length === 6) {
      var n = parseInt(hex, 16);
      return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
    }
  }
  var lower = str.toLowerCase();
  if (PAYLOAD_COLOR_NAMES[lower]) return parsePayloadColor(PAYLOAD_COLOR_NAMES[lower]);
  return { r: 0, g: 0, b: 0 };
}
function payloadColorToHex(str) {
  if (!str || !str.trim()) return null;
  var c = parsePayloadColor(str.trim());
  return "#" + [c.r, c.g, c.b].map(function(x) { var n = Math.max(0, Math.min(255, x)); return ("0" + n.toString(16)).slice(-2); }).join("");
}
function positionToXY(position, width, height, blockWidth, blockHeight, padding) {
  padding = padding || 20;
  var pos = (position || "top_left").toLowerCase().replace(/ /g, "_");
  var posV = "top", posH = "left";
  if (pos.indexOf("_") >= 0) {
    var parts = pos.split("_");
    if (["top", "center", "bottom"].indexOf(parts[0]) >= 0) posV = parts[0];
    if (parts.length > 1 && ["left", "center", "right"].indexOf(parts[1]) >= 0) posH = parts[1];
  } else if (["top", "center", "bottom"].indexOf(pos) >= 0) posV = pos;
  var startY = padding;
  if (posV === "bottom") startY = Math.max(padding, height - padding - blockHeight);
  else if (posV === "center") startY = Math.max(0, (height - blockHeight) / 2);
  var startX = padding;
  if (posH === "right") startX = Math.max(padding, width - padding - blockWidth);
  else if (posH === "center") startX = Math.max(0, (width - blockWidth) / 2);
  return { x: Math.round(startX), y: Math.round(startY) };
}
function getImagePreviewState() {
  var w = parseInt(document.getElementById("payload_image_width").value, 10) || 400;
  var h = parseInt(document.getElementById("payload_image_height").value, 10) || 200;
  w = Math.max(100, Math.min(2000, w));
  h = Math.max(50, Math.min(2000, h));
  var bgColor = parsePayloadColor((document.getElementById("payload_bg_color") && document.getElementById("payload_bg_color").value) || "#ffffff");
  var bgAlpha = parseInt(document.getElementById("payload_bg_alpha").value, 10);
  if (isNaN(bgAlpha)) bgAlpha = 100;
  bgAlpha = Math.max(0, Math.min(100, bgAlpha)) / 100;
  var lines = [];
  for (var i = 1; i <= 3; i++) {
    var textEl = document.getElementById("line" + i + "_text");
    var text = (textEl && textEl.value) ? textEl.value.trim().substring(0, 80) : "";
    if (!text) continue;
    var fs = parseInt(document.getElementById("line" + i + "_font_size").value, 10) || 14;
    fs = Math.max(8, Math.min(120, fs));
    var colorEl = document.getElementById("line" + i + "_color");
    var color = parsePayloadColor((colorEl && colorEl.value) ? colorEl.value : "#000000");
    var alphaEl = document.getElementById("line" + i + "_alpha");
    var alpha = parseInt(alphaEl && alphaEl.value ? alphaEl.value : 100, 10);
    if (isNaN(alpha)) alpha = 100;
    alpha = Math.max(0, Math.min(100, alpha)) / 100;
    var posEl = document.getElementById("line" + i + "_position");
    var position = (posEl && posEl.value) ? posEl.value : "top_left";
    var lowContrastEl = document.getElementById("line" + i + "_low_contrast");
    var lowContrast = lowContrastEl ? lowContrastEl.checked : false;
    var rotEl = document.getElementById("line" + i + "_text_rotation");
    var textRotation = (rotEl && rotEl.value !== "") ? parseFloat(rotEl.value) : 0;
    if (isNaN(textRotation)) textRotation = 0;
    lines.push({ text: text, fontSize: fs, color: color, alpha: alpha, position: position, lowContrast: lowContrast, textRotation: textRotation });
  }
  var fileInput = document.getElementById("payload_image_file");
  var file = (fileInput && fileInput.files && fileInput.files[0]) ? fileInput.files[0] : null;
  return { width: w, height: h, bgColor: bgColor, bgAlpha: bgAlpha, lines: lines, file: file };
}
function drawPayloadPreview() {
  var canvas = document.getElementById("payload_preview_canvas");
  if (!canvas) return;
  var state = getImagePreviewState();
  var w = state.width, h = state.height;
  canvas.width = w;
  canvas.height = h;
  var ctx = canvas.getContext("2d");
  if (!ctx) return;
  function drawBackground() {
    ctx.fillStyle = "rgba(" + state.bgColor.r + "," + state.bgColor.g + "," + state.bgColor.b + "," + state.bgAlpha + ")";
    ctx.fillRect(0, 0, w, h);
  }
  function drawLines() {
    var padding = 20;
    state.lines.forEach(function(line) {
      var fontSize = Math.max(8, Math.min(120, line.fontSize));
      ctx.font = fontSize + "px sans-serif";
      var metrics = ctx.measureText(line.text);
      var blockWidth = Math.min(metrics.width, w - 2 * padding);
      var blockHeight = fontSize + 6;
      var pos = positionToXY(line.position, w, h, blockWidth, blockHeight, padding);
      var r = line.color.r, g = line.color.g, b = line.color.b;
      if (line.lowContrast) { r = 180; g = 180; b = 180; }
      ctx.fillStyle = "rgba(" + r + "," + g + "," + b + "," + line.alpha + ")";
      var rot = (line.textRotation != null && !isNaN(line.textRotation)) ? line.textRotation : 0;
      if (Math.abs(rot) >= 0.5) {
        ctx.save();
        var cx = pos.x + blockWidth / 2, cy = pos.y + fontSize / 2;
        ctx.translate(cx, cy);
        ctx.rotate(-rot * Math.PI / 180);
        ctx.translate(-cx, -cy);
        ctx.fillText(line.text, pos.x, pos.y + fontSize);
        ctx.restore();
      } else {
        ctx.fillText(line.text, pos.x, pos.y + fontSize);
      }
    });
  }
  if (state.file) {
    var url = URL.createObjectURL(state.file);
    var img = new Image();
    img.onload = function() {
      ctx.drawImage(img, 0, 0, w, h);
      URL.revokeObjectURL(url);
      drawLines();
    };
    img.onerror = function() {
      URL.revokeObjectURL(url);
      drawBackground();
      drawLines();
    };
    img.src = url;
  } else {
    drawBackground();
    drawLines();
  }
}
function schedulePayloadPreview() {
  clearTimeout(payloadPreviewTimeout);
  payloadPreviewTimeout = setTimeout(drawPayloadPreview, 120);
}
var payloadImagePreviewInputs = ["line1_text", "line1_font_size", "line1_color", "line1_alpha", "line1_position", "line1_low_contrast", "line1_text_rotation", "line2_text", "line2_font_size", "line2_color", "line2_alpha", "line2_position", "line2_low_contrast", "line2_text_rotation", "line3_text", "line3_font_size", "line3_color", "line3_alpha", "line3_position", "line3_low_contrast", "line3_text_rotation", "payload_image_width", "payload_image_height", "payload_bg_color", "payload_bg_alpha"];
payloadImagePreviewInputs.forEach(function(id) {
  var el = document.getElementById(id);
  if (el) {
    el.addEventListener("input", schedulePayloadPreview);
    el.addEventListener("change", schedulePayloadPreview);
  }
});
[1, 2, 3].forEach(function(i) {
  var picker = document.getElementById("line" + i + "_color_picker");
  var textEl = document.getElementById("line" + i + "_color");
  if (picker && textEl) {
    var hex = payloadColorToHex(textEl.value);
    if (hex) picker.value = hex;
    picker.addEventListener("input", function() {
      textEl.value = picker.value;
      schedulePayloadPreview();
    });
    picker.addEventListener("change", function() {
      textEl.value = picker.value;
      schedulePayloadPreview();
    });
    textEl.addEventListener("input", function() {
      var h = payloadColorToHex(textEl.value);
      if (h) picker.value = h;
    });
    textEl.addEventListener("change", function() {
      var h = payloadColorToHex(textEl.value);
      if (h) picker.value = h;
    });
  }
});
[1, 2, 3].forEach(function(i) {
  var picker = document.getElementById("pdf_line" + i + "_color_picker");
  var textEl = document.getElementById("pdf_line" + i + "_color");
  if (picker && textEl) {
    var hex = payloadColorToHex(textEl.value);
    if (hex) picker.value = hex;
    picker.addEventListener("input", function() {
      textEl.value = picker.value;
    });
    picker.addEventListener("change", function() {
      textEl.value = picker.value;
    });
    textEl.addEventListener("input", function() {
      var h = payloadColorToHex(textEl.value);
      if (h) picker.value = h;
    });
    textEl.addEventListener("change", function() {
      var h = payloadColorToHex(textEl.value);
      if (h) picker.value = h;
    });
  }
});
var payloadImageFileEl = document.getElementById("payload_image_file");
if (payloadImageFileEl) {
  payloadImageFileEl.addEventListener("change", function() {
    schedulePayloadPreview();
    if (document.getElementById("payload_tab_preview").classList.contains("active")) drawPayloadPreview();
  });
}
document.getElementById("main_menu").addEventListener("click", function(e) {
  var li = e.target.closest("li[data-panel]");
  if (li && li.dataset.panel === "payloads") setTimeout(schedulePayloadPreview, 50);
});

function apiPathFileUrl(pathPrefix, relativeOrId, cacheKey, inline) {
  const encodedPath = String(relativeOrId || "").replace(/^\/+/, "").split("/").map(encodeURIComponent).join("/");
  let url = API + pathPrefix + encodedPath;
  const params = [];
  if (cacheKey != null && cacheKey !== "") params.push("v=" + encodeURIComponent(String(cacheKey)));
  if (inline) params.push("inline=1");
  if (params.length) url += "?" + params.join("&");
  return url;
}

function payloadFileUrl(relativePath, cacheKey, inline) {
  return apiPathFileUrl("/payloads/file/", relativePath, cacheKey, inline);
}

function documentFileUrl(documentId, cacheKey, inline) {
  return apiPathFileUrl("/documents/file/", String(documentId), cacheKey, inline);
}

function setDocumentAudioPreview(selection, fileKind) {
  const wrap = document.getElementById("doc_audio_preview");
  const player = document.getElementById("doc_audio_player");
  if (!wrap || !player) return;
  if (!selection || fileKind !== "audio") {
    player.removeAttribute("src");
    player.load();
    wrap.style.display = "none";
    return;
  }
  const cacheKey = Date.now();
  let src = "";
  if (selection.context_from === "payload") {
    src = payloadFileUrl(selection.payload_relative_path, cacheKey, true);
  } else if (selection.context_from === "upload") {
    src = documentFileUrl(selection.document_id, cacheKey, true);
  }
  if (!src) {
    wrap.style.display = "none";
    return;
  }
  player.src = src;
  player.load();
  wrap.style.display = "block";
}

async function loadPayloadsList() {
  try {
    const r = await fetch(API + "/payloads/list", { credentials: "include" });
    const data = await r.json().catch(() => ({}));
    const files = data.files || [];
    const table = document.getElementById("payload_list_table");
    const tbody = table.querySelector("tbody");
    const emptyEl = document.getElementById("payload_list_empty");
    tbody.innerHTML = "";
    if (files.length === 0) {
      table.style.display = "none";
      emptyEl.style.display = "block";
      return;
    }
    emptyEl.style.display = "none";
    table.style.display = "table";
    files.forEach(f => {
      const tr = document.createElement("tr");
      const rel = f.relative_path || f.name;
      const cacheKey = f.mtime != null ? f.mtime : (f.size != null ? f.size : Date.now());
      const downloadUrl = payloadFileUrl(rel, cacheKey);
      tr.innerHTML = "<td>" + escapeHtml(f.name) + "</td><td><code>" + escapeHtml(rel) + "</code></td><td>" + (f.size != null ? f.size + " B" : "") + "</td><td><a href=\"" + escapeHtml(downloadUrl) + "\" target=\"_blank\" rel=\"noopener\">Download</a></td>";
      tbody.appendChild(tr);
    });
  } catch (err) {
    document.getElementById("payload_list_empty").textContent = "Could not load list: " + (err.message || "error");
    document.getElementById("payload_list_empty").style.display = "block";
    document.getElementById("payload_list_table").style.display = "none";
  }
}
function escapeHtml(s) {
  if (s == null) return "";
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function parsePayloadNumber(id, fallback) {
  const el = document.getElementById(id);
  if (!el) return fallback;
  const value = parseFloat(el.value);
  return Number.isFinite(value) ? value : fallback;
}

document.getElementById("btn_payload_generate").addEventListener("click", async () => {
  const statusEl = document.getElementById("payload_generate_status");
  const resultEl = document.getElementById("payload_generated_result");
  const assetType = document.getElementById("payload_asset_type").value;
  statusEl.style.display = "none";
  resultEl.style.display = "none";
  const body = { asset_type: assetType };
  if (assetType === "text") {
    body.content = document.getElementById("payload_content").value;
    body.filename = document.getElementById("payload_filename").value.trim() || undefined;
  }
  if (assetType === "pdf") {
    for (var i = 1; i <= 3; i++) {
      body["pdf_line" + i + "_text"] = document.getElementById("pdf_line" + i + "_text").value.trim();
      body["pdf_line" + i + "_font_size"] = parseInt(document.getElementById("pdf_line" + i + "_font_size").value, 10) || 12;
      body["pdf_line" + i + "_color"] = document.getElementById("pdf_line" + i + "_color").value.trim();
      var lineAlpha = parseInt(document.getElementById("pdf_line" + i + "_alpha").value, 10);
      body["pdf_line" + i + "_alpha"] = Math.min(255, Math.max(0, Math.round((lineAlpha != null && !isNaN(lineAlpha) ? lineAlpha : 100) * 2.55)));
      body["pdf_line" + i + "_position"] = document.getElementById("pdf_line" + i + "_position").value || "top_left";
    }
    body.pdf_hidden_content = document.getElementById("pdf_hidden_content").value.trim() || "";
    body.pdf_filename = document.getElementById("payload_pdf_filename").value.trim() || undefined;
  }
  if (assetType === "image") {
    for (var i = 1; i <= 3; i++) {
      body["line" + i + "_text"] = document.getElementById("line" + i + "_text").value.trim();
      body["line" + i + "_font_size"] = parseInt(document.getElementById("line" + i + "_font_size").value, 10) || 14;
      body["line" + i + "_color"] = document.getElementById("line" + i + "_color").value.trim();
      var lineAlpha = parseInt(document.getElementById("line" + i + "_alpha").value, 10);
      body["line" + i + "_alpha"] = Math.min(255, Math.max(0, Math.round((lineAlpha != null && !isNaN(lineAlpha) ? lineAlpha : 100) * 2.55)));
      body["line" + i + "_position"] = document.getElementById("line" + i + "_position").value || "top_left";
      body["line" + i + "_low_contrast"] = document.getElementById("line" + i + "_low_contrast").checked;
      body["line" + i + "_text_rotation"] = parseFloat(document.getElementById("line" + i + "_text_rotation").value) || 0;
      body["line" + i + "_blur_radius"] = parseFloat(document.getElementById("line" + i + "_blur_radius").value) || 0;
      body["line" + i + "_noise_level"] = parseFloat(document.getElementById("line" + i + "_noise_level").value) || 0;
    }
    body.position = "top_left";
    body.font_size = 14;
    body.filename = document.getElementById("payload_image_filename").value.trim() || undefined;
    body.width = parseInt(document.getElementById("payload_image_width").value, 10) || 400;
    body.height = parseInt(document.getElementById("payload_image_height").value, 10) || 200;
    body.background_color = document.getElementById("payload_bg_color").value.trim() || undefined;
    var bgAlpha = parseInt(document.getElementById("payload_bg_alpha").value, 10);
    body.background_alpha = Math.min(255, Math.max(0, Math.round((bgAlpha != null && !isNaN(bgAlpha) ? bgAlpha : 100) * 2.55)));
  }
  if (assetType === "pdf_metadata") {
    body.body_content = document.getElementById("payload_body_content").value;
    body.subject = document.getElementById("payload_subject").value.trim();
    body.author = document.getElementById("payload_author").value.trim();
    body.filename = document.getElementById("payload_filename_pdf_meta").value.trim() || undefined;
  }
  if (assetType === "csv") {
    var csvCustom = document.getElementById("csv_mode_custom") && document.getElementById("csv_mode_custom").checked;
    body.filename = document.getElementById("payload_csv_filename").value.trim() || undefined;
    if (csvCustom) {
      body.csv_content = document.getElementById("payload_csv_content").value;
    } else {
      body.csv_columns = document.getElementById("payload_csv_columns").value.trim();
      body.csv_num_rows = parseInt(document.getElementById("payload_csv_num_rows").value, 10) || 10;
      body.csv_use_faker = document.getElementById("payload_csv_use_faker").checked;
    }
  }
  if (assetType === "qr") {
    body.payload = document.getElementById("payload_qr_payload").value.trim();
    body.filename = document.getElementById("payload_filename_qr").value.trim() || undefined;
  }
  if (assetType === "audio_synthetic") {
    body.duration_sec = parseFloat(document.getElementById("payload_duration").value) || 1;
    body.frequency = parseFloat(document.getElementById("payload_frequency").value) || 440;
    body.filename = document.getElementById("payload_filename_audio").value.trim() || undefined;
  }
  if (assetType === "audio_tts") {
    body.text = document.getElementById("payload_tts_text").value;
    body.overlay_text = document.getElementById("payload_tts_overlay_text").value.trim();
    body.overlay_level = parsePayloadNumber("payload_tts_overlay_level", 0.15);
    body.noise_level = parsePayloadNumber("payload_tts_noise_level", 0);
    body.background_tone_hz = parsePayloadNumber("payload_tts_background_tone_hz", 0);
    body.background_tone_level = parsePayloadNumber("payload_tts_background_tone_level", 0.2);
    body.pitch_semitones = parsePayloadNumber("payload_tts_pitch_semitones", 0);
    body.speed_factor = parsePayloadNumber("payload_tts_speed_factor", 1);
    body.echo_delay_ms = parsePayloadNumber("payload_tts_echo_delay_ms", 0);
    body.echo_decay = parsePayloadNumber("payload_tts_echo_decay", 0.4);
    body.distortion = parsePayloadNumber("payload_tts_distortion", 0);
    body.gain_db = parsePayloadNumber("payload_tts_gain_db", 0);
    body.low_pass_hz = parsePayloadNumber("payload_tts_low_pass_hz", 0);
    body.high_pass_hz = parsePayloadNumber("payload_tts_high_pass_hz", 0);
    body.filename = document.getElementById("payload_filename_tts").value.trim() || undefined;
  }
  document.getElementById("btn_payload_generate").disabled = true;
  try {
    const imageFileInput = document.getElementById("payload_image_file");
    const pdfFileInput = document.getElementById("payload_pdf_file");
    const pdfMetadataFileInput = document.getElementById("payload_pdf_metadata_file");
    const useMultipartImage = assetType === "image" && imageFileInput && imageFileInput.files && imageFileInput.files.length > 0;
    const useMultipartPdf = assetType === "pdf" && pdfFileInput && pdfFileInput.files && pdfFileInput.files.length > 0;
    const useMultipartPdfMetadata = assetType === "pdf_metadata" && pdfMetadataFileInput && pdfMetadataFileInput.files && pdfMetadataFileInput.files.length > 0;
    let fetchOpts = { method: "POST", credentials: "include" };
    if (useMultipartImage) {
      const form = new FormData();
      form.append("asset_type", assetType);
      for (var i = 1; i <= 3; i++) {
        if (body["line" + i + "_text"]) {
          form.append("line" + i + "_text", body["line" + i + "_text"]);
          form.append("line" + i + "_font_size", String(body["line" + i + "_font_size"] != null ? body["line" + i + "_font_size"] : 14));
          if (body["line" + i + "_color"]) form.append("line" + i + "_color", body["line" + i + "_color"]);
          form.append("line" + i + "_alpha", String(body["line" + i + "_alpha"] != null ? body["line" + i + "_alpha"] : 255));
          form.append("line" + i + "_position", body["line" + i + "_position"] || "top_left");
          form.append("line" + i + "_low_contrast", body["line" + i + "_low_contrast"] ? "true" : "false");
          form.append("line" + i + "_text_rotation", String(body["line" + i + "_text_rotation"] != null ? body["line" + i + "_text_rotation"] : 0));
          form.append("line" + i + "_blur_radius", String(body["line" + i + "_blur_radius"] != null ? body["line" + i + "_blur_radius"] : 0));
          form.append("line" + i + "_noise_level", String(body["line" + i + "_noise_level"] != null ? body["line" + i + "_noise_level"] : 0));
        }
      }
      form.append("position", body.position || "top_left");
      form.append("font_size", String(body.font_size != null ? body.font_size : 14));
      if (body.filename) form.append("filename", body.filename);
      form.append("width", String(body.width || 400));
      form.append("height", String(body.height || 200));
      if (body.background_color) form.append("background_color", body.background_color);
      form.append("background_alpha", String(body.background_alpha != null ? body.background_alpha : 255));
      form.append("file", imageFileInput.files[0]);
      fetchOpts.body = form;
    } else if (useMultipartPdf) {
      const form = new FormData();
      form.append("asset_type", assetType);
      for (var i = 1; i <= 3; i++) {
        form.append("pdf_line" + i + "_text", body["pdf_line" + i + "_text"] || "");
        form.append("pdf_line" + i + "_font_size", String(body["pdf_line" + i + "_font_size"] != null ? body["pdf_line" + i + "_font_size"] : 12));
        if (body["pdf_line" + i + "_color"]) form.append("pdf_line" + i + "_color", body["pdf_line" + i + "_color"]);
        form.append("pdf_line" + i + "_alpha", String(body["pdf_line" + i + "_alpha"] != null ? body["pdf_line" + i + "_alpha"] : 255));
        form.append("pdf_line" + i + "_position", body["pdf_line" + i + "_position"] || "top_left");
      }
      form.append("pdf_hidden_content", body.pdf_hidden_content || "");
      if (body.pdf_filename) form.append("pdf_filename", body.pdf_filename);
      var pdfFile = pdfFileInput.files[0];
      form.append("payload_pdf_file", pdfFile, pdfFile.name || "document.pdf");
      fetchOpts.body = form;
    } else if (useMultipartPdfMetadata) {
      const form = new FormData();
      form.append("asset_type", assetType);
      form.append("body_content", body.body_content || "Document body.");
      form.append("subject", body.subject || "");
      form.append("author", body.author || "");
      if (body.filename) form.append("filename", body.filename);
      var metaFile = pdfMetadataFileInput.files[0];
      form.append("payload_pdf_metadata_file", metaFile, metaFile.name || "document.pdf");
      fetchOpts.body = form;
    } else {
      fetchOpts.headers = { "Content-Type": "application/json" };
      fetchOpts.body = JSON.stringify(body);
    }
    const r = await fetch(API + "/payloads/generate", fetchOpts);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      statusEl.textContent = data.error || r.statusText || "Generation failed";
      statusEl.style.display = "block";
      statusEl.className = "message error";
      return;
    }
    const rel = data.relative_path || data.path || "";
    const cacheKey = Date.now();
    const downloadUrl = rel ? payloadFileUrl(rel, cacheKey, false) : "";
    const playbackUrl = rel ? payloadFileUrl(rel, cacheKey, true) : "";
    document.getElementById("payload_download_link").href = downloadUrl;
    document.getElementById("payload_download_link").textContent = data.path || rel || "file";
    document.getElementById("payload_relative_path").textContent = rel;
    const audioPreview = document.getElementById("payload_audio_preview");
    const audioPlayer = document.getElementById("payload_audio_player");
    if (audioPreview && audioPlayer) {
      const isAudio = assetType === "audio_synthetic" || assetType === "audio_tts";
      if (isAudio && playbackUrl) {
        audioPlayer.src = playbackUrl;
        audioPlayer.load();
        audioPreview.style.display = "block";
      } else {
        audioPlayer.removeAttribute("src");
        audioPlayer.load();
        audioPreview.style.display = "none";
      }
    }
    resultEl.style.display = "block";
    statusEl.textContent = assetType === "audio_synthetic"
      ? ("Generated " + (body.frequency != null ? body.frequency : 440) + " Hz tone successfully.")
      : (assetType === "audio_tts" && Array.isArray(data.effects_applied) && data.effects_applied.length
        ? ("Generated with effects: " + data.effects_applied.join(", ") + ".")
        : (data.warning || "Generated successfully."));
    statusEl.className = "message";
    statusEl.style.display = "block";
    loadPayloadsList();
    loadDocuments();
  } catch (err) {
    statusEl.textContent = err.message || "Network error";
    statusEl.className = "message error";
    statusEl.style.display = "block";
  } finally {
    document.getElementById("btn_payload_generate").disabled = false;
  }
});

async function loadModelDefault() {
  await loadModelsConfig();
}

(async function init() {
  await loadModelsConfig();
  const session = await getSession();
  updateSessionUI(session);
  if (!document.querySelector("#main_body .panel.active")) showPanel(DEFAULT_PANEL);
  loadDocuments();
  loadPayloadsList();
})();
