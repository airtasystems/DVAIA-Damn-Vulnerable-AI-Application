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

document.getElementById("send_document").addEventListener("click", async () => {
  const selected = document.getElementById("doc_select").value;
  const prompt = document.getElementById("prompt_document").value.trim();
  if (!prompt) return;
  const selection = parseDocumentSelection(selected);
  if (!selection) {
    setOutput("output_document", "Select a document or generated payload first.", "error");
    return;
  }
  setLoading("output_document", "send_document", true);
  try {
    const body = { prompt, ...selection };
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
    setOutput("output_document", data.response ?? "", "");
    appendTerminalLine("Document chat response", "muted");
    appendTerminalJson(data);
  } catch (err) {
    setOutput("output_document", err.message || "Network error", "error");
    appendTerminalLine("Document chat: " + (err.message || "Network error"), "fail");
  } finally {
    setLoading("output_document", "send_document", false);
  }
});
