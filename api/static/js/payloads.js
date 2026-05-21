function showPayloadOptions(assetType) {
  document.querySelectorAll(".payload-type-options").forEach(el => { el.style.display = "none"; });
  const show = (id) => {
    const el = document.getElementById(id);
    if (el) el.style.display = "block";
  };
  if (assetType === "text" || assetType === "pdf_visible") show("payload_options_text");
  else if (assetType === "image") {
    show("payload_options_image");
    if (typeof schedulePayloadPreview === "function") schedulePayloadPreview();
  }
  else if (assetType === "pdf_invisible") show("payload_options_pdf_invisible");
  else if (assetType === "pdf_metadata") show("payload_options_pdf_metadata");
  else if (assetType === "qr") show("payload_options_qr");
  else if (assetType === "audio_synthetic") show("payload_options_audio_synthetic");
  else if (assetType === "audio_tts") show("payload_options_audio_tts");
}
document.getElementById("payload_asset_type").addEventListener("change", () => {
  showPayloadOptions(document.getElementById("payload_asset_type").value);
});
showPayloadOptions("text");

document.querySelectorAll(".payload-line-tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    const tabId = btn.dataset.tab;
    document.querySelectorAll(".payload-line-tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".payload-line-tab").forEach(p => p.classList.remove("active"));
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

function payloadFileUrl(relativePath, cacheKey) {
  const rel = (relativePath || "").replace(/^\/+/, "");
  let url = API + "/payloads/file/" + encodeURIComponent(rel);
  if (cacheKey != null && cacheKey !== "") {
    url += (url.indexOf("?") >= 0 ? "&" : "?") + "v=" + encodeURIComponent(String(cacheKey));
  }
  return url;
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
  if (assetType === "text" || assetType === "pdf_visible") {
    body.content = document.getElementById("payload_content").value;
    body.filename = document.getElementById("payload_filename").value.trim() || undefined;
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
  if (assetType === "pdf_invisible") {
    body.visible_content = document.getElementById("payload_visible_content").value;
    body.hidden_content = document.getElementById("payload_hidden_content").value;
    body.filename = document.getElementById("payload_filename_pdf_inv").value.trim() || undefined;
  }
  if (assetType === "pdf_metadata") {
    body.body_content = document.getElementById("payload_body_content").value;
    body.subject = document.getElementById("payload_subject").value.trim();
    body.author = document.getElementById("payload_author").value.trim();
    body.filename = document.getElementById("payload_filename_pdf_meta").value.trim() || undefined;
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
    const useMultipart = assetType === "image" && imageFileInput && imageFileInput.files && imageFileInput.files.length > 0;
    let fetchOpts = { method: "POST", credentials: "include" };
    if (useMultipart) {
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
    const downloadUrl = rel ? payloadFileUrl(rel, cacheKey) : "";
    document.getElementById("payload_download_link").href = downloadUrl;
    document.getElementById("payload_download_link").textContent = data.path || rel || "file";
    document.getElementById("payload_relative_path").textContent = rel;
    const audioPreview = document.getElementById("payload_audio_preview");
    const audioPlayer = document.getElementById("payload_audio_player");
    if (audioPreview && audioPlayer) {
      const isAudio = assetType === "audio_synthetic" || assetType === "audio_tts";
      if (isAudio && downloadUrl) {
        audioPlayer.src = downloadUrl;
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
  } catch (err) {
    statusEl.textContent = err.message || "Network error";
    statusEl.className = "message error";
    statusEl.style.display = "block";
  } finally {
    document.getElementById("btn_payload_generate").disabled = false;
  }
});
