"""
Flask API for DVAIA. Thin HTTP layer; delegates to app.*.
Load .env via python -m api (api/__main__.py). PORT, DEFAULT_MODEL, OLLAMA_HOST.
"""
import os
import tempfile
import mimetypes
import time
from pathlib import Path

from flask import Flask, request, jsonify, render_template, session, send_from_directory

from core.config import (
    get_agentic_model_id,
    get_default_model_id,
    get_embedding_backend,
    get_default_llm_provider,
    get_vision_model_id,
    get_whisper_model_name,
    gemini_configured,
    is_gemini_only_mode,
    is_openai_only_mode,
    ollama_enabled,
    openai_configured,
    reset_data_on_start_enabled,
)
from core.providers import providers_payload, resolve_models_for_provider, detect_provider
from core.openai_client import clear_openai_client_cache

from app import agent as app_agent
from app import auth as app_auth
from app import chat as app_chat
from app import db as app_db
from app import documents as app_documents
from app import fetch as app_fetch
from app import mfa as app_mfa
from app import retrieval as app_retrieval
from app.cache_maintenance import clear_pycache
from app.startup import clear_document_store, clear_lab_data, clear_rag_index
from app import embeddings as app_embeddings
from app import vector_store as app_vector_store
from app.config import get_secret_key, get_database_uri, get_upload_dir
from app.settings_store import set_reset_data_on_start
from core.gemini_client import clear_gemini_client_cache
from payloads.config import get_output_dir as get_payloads_output_dir

ROOT = Path(__file__).resolve().parent.parent

app = Flask(__name__, template_folder="templates")
app.config["SECRET_KEY"] = get_secret_key()

_startup_lock = __import__("threading").Lock()
_startup_applied = False


def _apply_startup_reset_once() -> None:
    global _startup_applied
    with _startup_lock:
        if _startup_applied:
            return
        _startup_applied = True
        from app.startup import apply_startup_reset, warmup_llm_backends

        apply_startup_reset()
        warmup_llm_backends()


_apply_startup_reset_once()


@app.context_processor
def inject_static_version():
    """Cache-bust static assets when JS/CSS change (volume-mounted dev setups)."""
    static_root = Path(__file__).resolve().parent / "static"
    versions = {}
    for rel in ("js/main.js", "css/style.css"):
        try:
            versions[rel.replace("/", "_").replace(".", "_")] = int((static_root / rel).stat().st_mtime)
        except OSError:
            versions[rel.replace("/", "_").replace(".", "_")] = 0
    return {"static_version": max(versions.values()), "static_versions": versions}

# Initialize DB on first use (call once at startup)
_initialized = False


def _ensure_db():
    global _initialized
    if not _initialized:
        app_db.init_db()
        _initialized = True


def _default_model() -> str:
    return get_default_model_id()


def _user_id_from_session():
    return session.get("user_id")


@app.route("/")
def index():
    """Single-page front end: prompt input and output."""
    return render_template("index.html")


@app.route("/api/health", methods=["GET"])
def api_health():
    """Health check for probes and load balancers."""
    return jsonify({"status": "ok"})


def _llm_provider_from_request(data: dict | None = None) -> str | None:
    """Extract llm_provider from JSON body or query string."""
    p = None
    if data and data.get("llm_provider"):
        p = str(data.get("llm_provider")).strip().lower()
    elif request.args.get("llm_provider"):
        p = request.args.get("llm_provider", "").strip().lower()
    if p not in ("ollama", "gemini", "openai"):
        return None
    if p == "ollama" and not ollama_enabled():
        return get_default_llm_provider()
    return p


def _resolve_chat_model_id(data: dict) -> str:
    """Pick chat model_id from body + provider; avoid Ollama when cloud-only."""
    llm_provider = _llm_provider_from_request(data)
    explicit = (data.get("model_id") or "").strip()
    if llm_provider:
        provider_models = resolve_models_for_provider(llm_provider)
        if not explicit or detect_provider(explicit) != llm_provider:
            return provider_models["chat"]
    if not ollama_enabled():
        cloud = get_default_llm_provider()
        explicit_provider = detect_provider(explicit or _default_model())
        if explicit_provider == "ollama":
            return resolve_models_for_provider(cloud)["chat"]
    return explicit or _default_model()


@app.route("/api/models", methods=["GET"])
def api_models():
    """Return model_id format, provider configs, and role-specific models."""
    ollama = resolve_models_for_provider("ollama")
    gemini = resolve_models_for_provider("gemini")
    openai = resolve_models_for_provider("openai")
    return jsonify({
        "default": _default_model(),
        "agentic_model": get_agentic_model_id(),
        "vision_model": get_vision_model_id(),
        "whisper_model": get_whisper_model_name(),
        "transcription_backend": "whisper",
        "embedding_backend": get_embedding_backend(),
        "gemini_configured": gemini_configured(),
        "openai_configured": openai_configured(),
        "gemini_only": is_gemini_only_mode(),
        "openai_only": is_openai_only_mode(),
        "ollama_enabled": ollama_enabled(),
        "default_provider": get_default_llm_provider(),
        "providers": providers_payload(),
        "format": (
            "Use 'model_id' in POST body. Prefix: ollama: (local), gemini: (Google), or openai: (OpenAI). "
            "Optional 'llm_provider': ollama|gemini|openai selects provider defaults from Settings."
        ),
        "examples": [
            "ollama:llama3.2",
            "gemini:gemini-2.0-flash",
            "openai:gpt-4o-mini",
            ollama["chat"],
            gemini["chat"],
            openai["chat"],
        ],
    })


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Send prompt or messages to model. JSON body:
    - prompt: string (or use "message" if CHAT_REQUEST_BODY_KEY is message); required if messages not set.
    - messages: optional list of {role, content} for multi-turn; if set, used instead of prompt.
    - model_id: optional.
    - options: optional dict for generation (max_tokens, num_predict) to cap output length.
    - context_from, document_id, payload_relative_path, context_mode, url, rag_query, rag_source: for indirect-injection tests.
    - context_mode: "extract" (default, OCR/PDF/STT text) or "vision" (image bytes to VISION_MODEL).
    - vision_model_id: optional override for vision mode (defaults to VISION_MODEL env).
    - llm_provider: optional ollama|gemini|openai — used for RAG embeddings when indexing/retrieving.
    """
    _ensure_db()
    data = request.get_json() or {}
    prompt = data.get("prompt") or data.get("message", "")
    messages = data.get("messages")
    llm_provider = _llm_provider_from_request(data)
    model_id = _resolve_chat_model_id(data)
    vision_model_id = (data.get("vision_model_id") or "").strip() or None
    options = data.get("options")
    context_from = data.get("context_from")
    context_mode = (data.get("context_mode") or "extract").strip().lower()
    document_id = data.get("document_id")
    payload_relative_path = (data.get("payload_relative_path") or data.get("payload_path") or "").strip() or None
    url = data.get("url")
    rag_query = data.get("rag_query")
    rag_source = (data.get("rag_source") or "").strip() or None
    if not prompt and not messages:
        return jsonify({"error": "Missing 'prompt' (or 'message') / 'messages' in body"}), 400
    user_id = _user_id_from_session()
    try:
        started = time.perf_counter()
        res = app_chat.handle_chat(
            prompt=prompt,
            user_id=user_id,
            model_id=model_id,
            context_from=context_from,
            context_mode=context_mode,
            document_id=document_id,
            payload_relative_path=payload_relative_path,
            url=url,
            rag_query=rag_query,
            rag_source=rag_source,
            vision_model_id=vision_model_id,
            llm_provider=llm_provider,
            options=options,
            messages=messages,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        return jsonify({
            "response": res["text"],
            "thinking": res.get("thinking", ""),
            "context_extracted": res.get("context_extracted"),
            "context_warning": res.get("context_warning"),
            "context_mode": res.get("context_mode"),
            "vision_model": res.get("vision_model"),
            "transcription_backend": res.get("transcription_backend"),
            "whisper_model": res.get("whisper_model"),
            "rag_source_filter": res.get("rag_source_filter"),
            "rag_chunk_count": res.get("rag_chunk_count"),
            "llm_provider": res.get("llm_provider"),
            "duration_ms": duration_ms,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/agent/chat", methods=["POST"])
def api_agent_chat():
    """
    Agentic testing: ReAct agent with SQLite tools. JSON body: prompt, optional model_id,
    messages, tool_names (list), max_steps, timeout.
    Returns response, thinking, messages, tool_calls (names used this turn).
    """
    _ensure_db()
    data = request.get_json() or {}
    prompt = (data.get("prompt") or data.get("message") or "").strip()
    if not prompt:
        return jsonify({"error": "Missing 'prompt' (or 'message') in body"}), 400
    llm_provider = _llm_provider_from_request(data)
    model_id = data.get("model_id") or get_agentic_model_id()
    if llm_provider and not data.get("model_id"):
        model_id = resolve_models_for_provider(llm_provider)["agentic"]
    messages = data.get("messages")
    if messages is not None and not isinstance(messages, list):
        messages = None
    tool_names = data.get("tool_names")
    if tool_names is not None and not isinstance(tool_names, list):
        tool_names = None
    max_steps = data.get("max_steps")
    if max_steps is not None:
        try:
            max_steps = max(1, min(50, int(max_steps)))
        except (TypeError, ValueError):
            max_steps = 15
    else:
        max_steps = 15
    timeout = data.get("timeout")
    if timeout is not None:
        try:
            timeout = max(10, min(300, int(timeout)))
        except (TypeError, ValueError):
            timeout = 120
    else:
        timeout = 120
    try:
        res = app_agent.run_agent(
            prompt,
            model_id=model_id,
            messages=messages,
            tool_names=tool_names,
            max_steps=max_steps,
            timeout=timeout,
        )
        return jsonify({
            "response": res["text"],
            "thinking": res.get("thinking", ""),
            "messages": res.get("messages", []),
            "tool_calls": res.get("tool_calls", []),
            "llm_provider": llm_provider or None,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _build_prompt_from_template(template: str, user_input: str) -> str:
    """Substitute {{user_input}} in template with user_input. No escaping (vulnerable by design)."""
    if not template:
        return user_input
    return template.replace("{{user_input}}", user_input)


@app.route("/api/chat-with-template", methods=["POST"])
def api_chat_with_template():
    """
    Build prompt from template + user_input (substitute {{user_input}}), then send to model.
    JSON body: template, user_input, optional model_id. No escaping—vulnerable for red-team tests.
    """
    _ensure_db()
    data = request.get_json() or {}
    template = data.get("template", "")
    user_input = data.get("user_input", "")
    llm_provider = _llm_provider_from_request(data)
    model_id = data.get("model_id") or _default_model()
    if llm_provider and not data.get("model_id"):
        model_id = resolve_models_for_provider(llm_provider)["chat"]
    if not template.strip():
        return jsonify({"error": "Missing 'template' in body"}), 400
    user_id = _user_id_from_session()
    constructed = _build_prompt_from_template(template, user_input)
    try:
        res = app_chat.handle_chat(
            prompt=constructed,
            user_id=user_id,
            model_id=model_id,
            llm_provider=llm_provider,
        )
        return jsonify({
            "response": res["text"],
            "thinking": res.get("thinking", ""),
            "constructed_prompt": constructed
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/login", methods=["POST"])
def api_login():
    """JSON body: username, password. Sets session on success."""
    _ensure_db()
    data = request.get_json() or request.form
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "Missing username or password"}), 400
    user = app_auth.login(username, password)
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401
    session["user_id"] = user["id"]
    session["mfa_verified"] = False
    return jsonify({"ok": True, "user_id": user["id"], "username": user["username"], "role": user["role"]})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    """Clear session."""
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/session", methods=["GET"])
def api_session():
    """Return current user if logged in."""
    _ensure_db()
    user_id = _user_id_from_session()
    if not user_id:
        return jsonify({"user": None}), 200
    user = app_auth.get_user_by_id(user_id)
    if not user:
        session.clear()
        return jsonify({"user": None}), 200
    return jsonify({
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "mfa_verified": session.get("mfa_verified", False),
        }
    })


@app.route("/api/mfa", methods=["POST"])
def api_mfa():
    """JSON body: code. Verify MFA and set session.mfa_verified."""
    _ensure_db()
    user_id = _user_id_from_session()
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    data = request.get_json() or {}
    code = (data.get("code") or "").strip()
    if not code:
        return jsonify({"error": "Missing code"}), 400
    if not app_mfa.verify_code(user_id, code):
        return jsonify({"error": "Invalid code"}), 401
    session["mfa_verified"] = True
    return jsonify({"ok": True})


@app.route("/api/documents/upload", methods=["POST"])
def api_documents_upload():
    """Multipart: file. Returns document_id."""
    _ensure_db()
    user_id = _user_id_from_session()
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    file_storage = request.files["file"]
    if not file_storage or not file_storage.filename:
        return jsonify({"error": "No file selected"}), 400
    try:
        doc_id = app_documents.save_upload(file_storage, user_id)
        return jsonify({"document_id": doc_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/documents", methods=["GET"])
def api_documents_list():
    """List uploaded documents and generated payload files for document injection."""
    _ensure_db()
    user_id = _user_id_from_session()
    docs = app_documents.list_documents(user_id)
    payload_files = app_documents.list_payload_files()
    return jsonify({
        "documents": [
            {"id": d["id"], "filename": d["filename"], "created_at": d["created_at"]}
            for d in docs
        ],
        "payload_files": payload_files,
    })


@app.route("/api/documents/extract-preview", methods=["GET"])
def api_documents_extract_preview():
    """Preview extracted text for an uploaded document or generated payload file."""
    _ensure_db()
    user_id = _user_id_from_session()
    document_id = request.args.get("document_id", type=int)
    payload_relative_path = (request.args.get("payload_relative_path") or "").strip() or None
    if document_id is not None:
        doc = app_documents.get_document(document_id, user_id)
        if not doc:
            return jsonify({"error": "Document not found"}), 404
        file_path = doc.get("file_path")
        if not file_path:
            return jsonify({"error": "Document file missing on disk"}), 404
        preview = app_documents.extract_file_preview(file_path)
        return jsonify({
            "source": doc.get("filename") or f"document_{document_id}",
            **preview,
            "whisper_model": get_whisper_model_name() if preview.get("transcription_backend") else None,
        })
    if payload_relative_path:
        path = app_documents.resolve_payload_path(payload_relative_path)
        if path is None:
            return jsonify({"error": "Payload file not found"}), 404
        preview = app_documents.extract_file_preview(str(path))
        return jsonify({
            "source": payload_relative_path,
            **preview,
            "whisper_model": get_whisper_model_name() if preview.get("transcription_backend") else None,
        })
    return jsonify({"error": "Provide document_id or payload_relative_path"}), 400


@app.route("/api/web/fetch-preview", methods=["GET"])
def api_web_fetch_preview():
    """Preview fetched/extracted text for a URL (Web Injection)."""
    url = (request.args.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Provide url query parameter"}), 400
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "URL must be http or https (use absolute URL)"}), 400
    try:
        page = app_fetch.fetch_page_context(url, timeout=20)
        preview = (page.get("context_text") or "")[:2000]
        return jsonify({
            "url": url,
            "title": page.get("title") or "",
            "meta_description": page.get("meta_description") or "",
            "visible_text": page.get("visible_text") or "",
            "hidden_text": page.get("hidden_text") or "",
            "text": page.get("context_text") or "",
            "preview": preview,
            "chars": page.get("chars") or 0,
            "fetch_backend": page.get("fetch_backend"),
            "extractor": page.get("extractor"),
            "fetch_ms": page.get("fetch_ms"),
            "extraction_ms": page.get("extraction_ms"),
            "warning": page.get("warning"),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def _send_local_file(path: Path, *, inline: bool = False):
    """Serve a file from disk; inline=True sets MIME type for browser playback."""
    response = send_from_directory(
        str(path.parent),
        path.name,
        as_attachment=not inline,
        download_name=path.name,
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    if inline:
        guessed, _ = mimetypes.guess_type(path.name)
        if guessed:
            response.headers["Content-Type"] = guessed
    return response


@app.route("/api/documents/file/<int:document_id>", methods=["GET"])
def api_documents_file(document_id):
    """Serve an uploaded document file (inline playback for audio/images)."""
    _ensure_db()
    user_id = _user_id_from_session()
    doc = app_documents.get_document(document_id, user_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404
    file_path = doc.get("file_path")
    if not file_path:
        return jsonify({"error": "Document file missing on disk"}), 404
    path = Path(file_path).resolve()
    if not path.is_file():
        return jsonify({"error": "Document file missing on disk"}), 404
    inline = request.args.get("inline", "").strip().lower() in ("1", "true", "yes")
    return _send_local_file(path, inline=inline)


@app.route("/api/documents/<int:document_id>", methods=["GET"])
def api_documents_get(document_id):
    """Get document metadata and extracted text."""
    _ensure_db()
    user_id = _user_id_from_session()
    doc = app_documents.get_document(document_id, user_id)
    if not doc:
        return jsonify({"error": "Not found"}), 404
    return jsonify({
        "id": doc["id"],
        "filename": doc["filename"],
        "extracted_text": doc.get("extracted_text"),
        "created_at": doc["created_at"],
    })


@app.route("/api/documents/<int:document_id>", methods=["DELETE"])
def api_documents_delete(document_id):
    """Delete document (file and DB row). Requires authenticated session."""
    _ensure_db()
    user_id = _user_id_from_session()
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    if not app_documents.delete_document(document_id, user_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/rag/retrieve-preview", methods=["GET"])
def api_rag_retrieve_preview():
    """Preview semantic retrieval before RAG chat. Query params: q, optional rag_source."""
    _ensure_db()
    q = (request.args.get("q") or "").strip()
    rag_source = (request.args.get("rag_source") or "").strip() or None
    llm_provider = _llm_provider_from_request()
    if not q:
        return jsonify({
            "chunks": [],
            "formatted_preview": "",
            "rag_source": rag_source,
            "warning": "Enter a query to preview retrieval.",
            "sources": app_retrieval.list_sources(llm_provider=llm_provider),
        })
    hits = app_retrieval.search_diverse_hits(
        q, source_filter=rag_source, llm_provider=llm_provider
    )
    formatted = app_retrieval.format_chunks_for_prompt(hits)
    warning = None
    if rag_source and not hits:
        sources = app_retrieval.list_sources(llm_provider=llm_provider)
        warning = (
            f"No chunks matched for source '{rag_source}'. "
            f"Indexed sources: {', '.join(sources) if sources else '(none)'}"
        )
    return jsonify({
        "chunks": [
            {
                "source": h.get("source"),
                "content": h.get("content"),
                "score": h.get("score"),
            }
            for h in hits
        ],
        "formatted_preview": formatted,
        "rag_source": rag_source,
        "warning": warning,
        "sources": app_retrieval.list_sources(llm_provider=llm_provider) if not hits else None,
    })


@app.route("/api/rag/search", methods=["GET"])
def api_rag_search():
    """Search RAG chunks by keyword. Query params: q, top_k (default 5)."""
    _ensure_db()
    q = (request.args.get("q") or "").strip()
    top_k = min(20, max(1, int(request.args.get("top_k", 5))))
    if not q:
        return jsonify({"chunks": []})
    chunks = app_retrieval.search(q, top_k=top_k)
    return jsonify({"chunks": [{"content": c} for c in chunks]})


@app.route("/api/rag/chunks", methods=["GET"])
def api_rag_chunks_list():
    """List all RAG chunks (id, source, content, created_at)."""
    _ensure_db()
    chunks = app_retrieval.list_chunks()
    return jsonify({"chunks": chunks})


@app.route("/api/rag/chunks", methods=["POST"])
def api_rag_chunks_add():
    """Add a chunk to the RAG index. Body: source (optional), content, optional llm_provider."""
    _ensure_db()
    data = request.get_json() or {}
    source = (data.get("source") or "").strip() or "manual"
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "Missing or empty 'content'"}), 400
    llm_provider = _llm_provider_from_request(data)
    chunk_id = app_retrieval.add_chunk(source, content, llm_provider=llm_provider)
    return jsonify({"id": chunk_id})


@app.route("/api/rag/add-document/<int:document_id>", methods=["POST"])
def api_rag_add_document(document_id):
    """Add a document to RAG: split into chunks, embed each, store. Returns number of chunks added."""
    _ensure_db()
    user_id = _user_id_from_session()
    data = request.get_json(silent=True) or {}
    llm_provider = _llm_provider_from_request(data)
    doc = app_documents.get_document(document_id, user_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404
    text = (doc.get("extracted_text") or "").strip()
    if not text:
        return jsonify({
            "error": "Document has no extracted text. Use .txt, or install PyPDF2 for PDF, python-docx for DOCX, pytesseract + tesseract-ocr for images.",
        }), 400
    source = doc.get("filename") or f"document_{document_id}"
    chunks_added = app_retrieval.add_document(source, text, llm_provider=llm_provider)
    return jsonify({
        "chunks_added": chunks_added,
        "source": source,
        "content_length": len(text),
    })


@app.route("/api/rag/add-payload", methods=["POST"])
def api_rag_add_payload():
    """Add a generated payload file to RAG by relative path under PAYLOADS_OUTPUT_DIR."""
    _ensure_db()
    data = request.get_json() or {}
    relative_path = (data.get("payload_relative_path") or data.get("payload_path") or "").strip()
    if not relative_path:
        return jsonify({"error": "Missing payload_relative_path"}), 400
    text = app_documents.extract_payload_text(relative_path).strip()
    if not text:
        return jsonify({"error": "Payload file not found or has no extracted text."}), 400
    source = relative_path.replace("\\", "/")
    llm_provider = _llm_provider_from_request(data)
    chunks_added = app_retrieval.add_document(source, text, llm_provider=llm_provider)
    return jsonify({
        "chunks_added": chunks_added,
        "source": source,
        "content_length": len(text),
    })


@app.route("/api/rag/delete-by-source", methods=["POST"])
def api_rag_delete_by_source():
    """Delete all RAG chunks with the given source. Body: source (string). Requires authenticated session."""
    _ensure_db()
    user_id = _user_id_from_session()
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    data = request.get_json() or {}
    source = (data.get("source") or "").strip()
    if not source:
        return jsonify({"error": "Missing or empty 'source'"}), 400
    app_retrieval.delete_chunks_by_source(source)
    return jsonify({"ok": True})


@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    """Runtime settings for the Settings panel (persistence, paths)."""
    db_uri = get_database_uri()
    upload_dir = get_upload_dir()
    ephemeral = db_uri.startswith("/tmp") or upload_dir.startswith("/tmp")
    return jsonify({
        "reset_data_on_start": reset_data_on_start_enabled(),
        "database_uri": db_uri,
        "upload_dir": upload_dir,
        "using_ephemeral_storage": ephemeral,
        "gemini_only": is_gemini_only_mode(),
        "openai_only": is_openai_only_mode(),
        "note": (
            "When reset_data_on_start is false, document DB, uploads, and Qdrant data "
            "persist across restarts (use data/ paths and a Qdrant volume in Docker)."
        ),
    })


@app.route("/api/settings", methods=["POST"])
def api_settings_update():
    """Update settings from the UI. Body: { reset_data_on_start: bool }."""
    data = request.get_json(silent=True) or {}
    result = {}
    if "reset_data_on_start" in data:
        result = set_reset_data_on_start(bool(data["reset_data_on_start"]))
    payload = {
        "ok": True,
        "reset_data_on_start": reset_data_on_start_enabled(),
        "database_uri": get_database_uri(),
        "upload_dir": get_upload_dir(),
        "using_ephemeral_storage": get_database_uri().startswith("/tmp") or get_upload_dir().startswith("/tmp"),
        **result,
    }
    if result:
        payload["message"] = (
            "Restart the app for the reset-on-start behavior to take effect on next boot."
        )
    return jsonify(payload)


@app.route("/api/settings/clear-cache", methods=["POST"])
def api_settings_clear_cache():
    """
    Clear runtime or persisted caches. Body target:
      rag | documents | lab | gemini | openai | pycache
    """
    data = request.get_json(silent=True) or {}
    target = (data.get("target") or "").strip().lower()
    allowed = ("rag", "documents", "lab", "gemini", "openai", "pycache")
    if target not in allowed:
        return jsonify({"error": f"target must be one of: {', '.join(allowed)}"}), 400

    try:
        if target == "rag":
            collections = clear_rag_index()
            if collections:
                message = (
                    "RAG index cleared. Uploaded documents and generated payloads are unchanged — "
                    "use “Clear all lab data” to empty document dropdowns."
                )
            else:
                message = (
                    "RAG index already empty (no collections in Qdrant). "
                    "Document dropdowns list uploads/payloads, not the vector index."
                )
            return jsonify({
                "ok": True,
                "target": target,
                "message": message,
                "collections": collections,
            })

        if target == "documents":
            result = clear_document_store()
            n = result.get("documents_removed", 0)
            return jsonify({
                "ok": True,
                "target": target,
                "message": f"Document store cleared ({n} upload(s) removed). RAG vectors unchanged.",
                **result,
            })

        if target == "lab":
            result = clear_lab_data(include_payloads=True)
            n_docs = result.get("documents_removed", 0)
            n_payloads = result.get("payload_files_removed", 0)
            cols = result.get("collections") or []
            return jsonify({
                "ok": True,
                "target": target,
                "message": (
                    f"Lab data cleared: {n_docs} upload(s), {n_payloads} payload file(s), "
                    f"{len(cols)} RAG collection(s)."
                ),
                **result,
            })

        if target == "gemini":
            clear_gemini_client_cache()
            app_embeddings.clear_embeddings_cache()
            return jsonify({
                "ok": True,
                "target": target,
                "message": "Gemini client and embedding cache cleared.",
            })

        if target == "openai":
            clear_openai_client_cache()
            app_embeddings.clear_embeddings_cache()
            return jsonify({
                "ok": True,
                "target": target,
                "message": "OpenAI client and embedding cache cleared.",
            })

        removed = clear_pycache()
        if removed:
            message = f"Removed {len(removed)} __pycache__ director{'y' if len(removed) == 1 else 'ies'}."
        else:
            message = (
                "No __pycache__ directories found under the project "
                "(normal when PYTHONDONTWRITEBYTECODE=1 in Docker)."
            )
        return jsonify({
            "ok": True,
            "target": target,
            "message": message,
            "paths": removed[:50],
            "truncated": len(removed) > 50,
        })
    except Exception as exc:
        return jsonify({"error": str(exc), "target": target}), 500


@app.route("/evil/")
@app.route("/evil")
def evil_page():
    """Serve malicious page for web-injection tests."""
    evil_dir = Path(__file__).resolve().parent.parent / "app" / "static" / "evil"
    return send_from_directory(str(evil_dir), "index.html")


def _payloads_output_dir():
    """Payloads output directory (resolved)."""
    return Path(get_payloads_output_dir()).resolve()


def _payloads_relative_path(safe_path: Path) -> str:
    """Return path relative to payloads output dir (for list/download). Works when output is container-local."""
    out_dir = _payloads_output_dir()
    try:
        return str(Path(safe_path).resolve().relative_to(out_dir)).replace("\\", "/")
    except ValueError:
        return str(safe_path.name)


def _parse_bool(value):
    """Return True for truthy form/JSON values (true, 1, 'true', '1'), else False."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    return s in ("true", "1", "yes", "on")


def _parse_float_param(data, key, default=0.0, minimum=None, maximum=None):
    """Parse a numeric request field with optional clamping."""
    raw = data.get(key, default)
    try:
        value = float(default if raw is None or raw == "" else raw)
    except (TypeError, ValueError):
        value = float(default)
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _payloads_generate_data():
    """Build request data from JSON or multipart form. Returns (data, uploaded_file, pdf_file, pdf_metadata_file)."""
    if request.is_json:
        return (request.get_json() or {}), None, None, None
    data = dict(request.form) if request.form else {}
    # Form values are lists for multi-value keys; take first element
    data = {k: (v[0] if isinstance(v, (list, tuple)) else v) for k, v in data.items()}
    files = request.files or {}
    uploaded_file = files.get("file")
    if uploaded_file and not (uploaded_file.filename and uploaded_file.filename.strip()):
        uploaded_file = None
    pdf_file = files.get("payload_pdf_file")
    pdf_metadata_file = files.get("payload_pdf_metadata_file")
    return data, uploaded_file, pdf_file, pdf_metadata_file


@app.route("/api/payloads/generate", methods=["POST"])
def api_payloads_generate():
    """
    Generate a payload asset. JSON body or multipart form: asset_type, plus type-specific options.
    For image, optional form field "file" = uploaded image to modify. Returns { path, relative_path } or 400/500.
    """
    data, uploaded_file, pdf_file, pdf_metadata_file = _payloads_generate_data()
    asset_type = (data.get("asset_type") or "").strip().lower()
    if not asset_type:
        return jsonify({"error": "Missing asset_type"}), 400
    try:
        import payloads
        out_dir = _payloads_output_dir()
        path = None
        if asset_type == "text":
            content = (data.get("content") or "").strip() or "Sample payload text."
            path = payloads.generate_text(content=content, filename=data.get("filename"), subdir=data.get("subdir", "docs"), extension=data.get("extension", "txt"))
        elif asset_type == "pdf":
            text_lines = []
            for i in range(1, 4):
                t = (data.get(f"pdf_line{i}_text") or data.get(f"line{i}_text") or "").strip()
                if t:
                    text_lines.append({
                        "text": t[:80],
                        "font_size": max(8, min(72, int(data.get(f"pdf_line{i}_font_size") or data.get(f"line{i}_font_size") or 12))),
                        "color": (data.get(f"pdf_line{i}_color") or data.get(f"line{i}_color") or "").strip() or None,
                        "alpha": min(255, max(0, int(data.get(f"pdf_line{i}_alpha") or data.get(f"line{i}_alpha") or 255))),
                        "position": (data.get(f"pdf_line{i}_position") or data.get(f"line{i}_position") or "top_left").strip() or "top_left",
                    })
            if not text_lines:
                text_lines = None
            hidden = (data.get("pdf_hidden_content") or data.get("hidden_content") or "").strip() or None
            source_pdf_path = None
            source_file = pdf_file or uploaded_file  # dedicated field or generic "file"
            if source_file:
                fname = (getattr(source_file, "filename", None) or "").strip()
                if not fname or fname.lower().endswith(".pdf"):
                    source_file.seek(0, 2)
                    size = source_file.tell()
                    source_file.seek(0)
                    if size > 10 * 1024 * 1024:
                        return jsonify({"error": "Uploaded PDF too large (max 10 MB)"}), 400
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                        source_file.save(tmp.name)
                        source_pdf_path = tmp.name
            try:
                path = payloads.generate_pdf(
                    text_lines=text_lines,
                    hidden_content=hidden,
                    filename=data.get("pdf_filename") or data.get("filename"),
                    subdir=data.get("subdir", "docs"),
                    source_pdf=source_pdf_path,
                )
            finally:
                if source_pdf_path and os.path.isfile(source_pdf_path):
                    try:
                        os.unlink(source_pdf_path)
                    except OSError:
                        pass
        elif asset_type == "pdf_metadata":
            body = (data.get("body_content") or "").strip() or "Document body."
            subject = (data.get("subject") or "").strip()
            author = (data.get("author") or "").strip()
            source_pdf_path = None
            meta_file = pdf_metadata_file or uploaded_file
            if meta_file and (getattr(meta_file, "filename", None) or "").strip().lower().endswith(".pdf"):
                meta_file.seek(0, 2)
                size = meta_file.tell()
                meta_file.seek(0)
                if size > 10 * 1024 * 1024:
                    return jsonify({"error": "Uploaded PDF too large (max 10 MB)"}), 400
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    meta_file.save(tmp.name)
                    source_pdf_path = tmp.name
            try:
                path = payloads.generate_pdf_metadata(
                    body_content=body,
                    subject=subject,
                    author=author,
                    filename=data.get("filename"),
                    subdir=data.get("subdir", "docs"),
                    source_pdf=source_pdf_path,
                )
            finally:
                if source_pdf_path and os.path.isfile(source_pdf_path):
                    try:
                        os.unlink(source_pdf_path)
                    except OSError:
                        pass
        elif asset_type == "csv":
            csv_content = (data.get("csv_content") or "").strip() or None
            csv_columns = (data.get("csv_columns") or "").strip() or None
            num_rows = max(0, min(10000, int(data.get("csv_num_rows") or 10)))
            use_faker = _parse_bool(data.get("csv_use_faker", "true"))
            path = payloads.generate_csv(
                content=csv_content,
                columns=csv_columns,
                num_rows=num_rows,
                filename=data.get("filename"),
                subdir=data.get("subdir", "docs"),
                use_faker=use_faker,
            )
        elif asset_type == "image":
            text_lines = []
            for i in range(1, 4):
                t = (data.get(f"line{i}_text") or data.get(f"text_line{i}") or "").strip()
                if t:
                    text_lines.append({
                        "text": t[:80],
                        "font_size": max(8, min(120, int(data.get(f"line{i}_font_size") or 14))),
                        "color": (data.get(f"line{i}_color") or "").strip() or None,
                        "alpha": min(255, max(0, int(data.get(f"line{i}_alpha") or 255))),
                        "position": (data.get(f"line{i}_position") or "top_left").strip() or "top_left",
                        "low_contrast": _parse_bool(data.get(f"line{i}_low_contrast")),
                        "text_rotation": float(data.get(f"line{i}_text_rotation") or 0),
                        "blur_radius": max(0.0, min(25.0, float(data.get(f"line{i}_blur_radius") or 0))),
                        "noise_level": max(0.0, min(1.0, float(data.get(f"line{i}_noise_level") or 0))),
                    })
            if not text_lines:
                text_lines = None
            position = (data.get("position") or "top_left").strip() or "top_left"
            font_size = max(8, min(120, int(data.get("font_size") or 14)))
            source_image = None
            if uploaded_file:
                # Limit size (e.g. 10 MB); save to temp and pass path
                uploaded_file.seek(0, 2)
                size = uploaded_file.tell()
                uploaded_file.seek(0)
                if size > 10 * 1024 * 1024:
                    return jsonify({"error": "Uploaded image too large (max 10 MB)"}), 400
                ext = Path(uploaded_file.filename).suffix or ".png"
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                    uploaded_file.save(tmp.name)
                    source_image = tmp.name
            try:
                path = payloads.generate_image(
                    content=None,
                    width=int(data.get("width") or 400),
                    height=int(data.get("height") or 200),
                    filename=data.get("filename"),
                    subdir=data.get("subdir", "images"),
                    low_contrast=False,
                    background_color=(data.get("background_color") or "").strip() or None,
                    text_color=(data.get("text_color") or "").strip() or None,
                    background_alpha=min(255, max(0, int(data.get("background_alpha", 255)))),
                    text_alpha=min(255, max(0, int(data.get("text_alpha", 255)))),
                    text_rotation=0.0,
                    blur_radius=0.0,
                    noise_level=0.0,
                    source_image=source_image,
                    text_lines=text_lines,
                    position=position,
                    font_size=font_size,
                )
            finally:
                if source_image and os.path.isfile(source_image):
                    try:
                        os.unlink(source_image)
                    except OSError:
                        pass
        elif asset_type == "qr":
            payload = (data.get("payload") or data.get("content") or "").strip() or "https://example.com"
            cw = data.get("composite_width")
            ch = data.get("composite_height")
            path = payloads.generate_qr(payload=payload, filename=data.get("filename"), subdir=data.get("subdir", "images"), composite_width=int(cw) if cw is not None else None, composite_height=int(ch) if ch is not None else None)
        elif asset_type == "audio_synthetic":
            frequency = float(data.get("frequency") or 440.0)
            duration_sec = float(data.get("duration_sec") or 1.0)
            filename = (data.get("filename") or "").strip() or None
            if not filename:
                filename = f"tone_{int(round(frequency))}hz.wav"
            path = payloads.generate_audio_synthetic(
                duration_sec=duration_sec,
                frequency=frequency,
                filename=filename,
                subdir=data.get("subdir", "audio"),
            )
        elif asset_type == "audio_tts":
            text = (data.get("text") or data.get("content") or "").strip() or "Hello world."
            overlay_text = (data.get("overlay_text") or "").strip() or None
            tts_kwargs = dict(
                text=text,
                filename=data.get("filename"),
                subdir=data.get("subdir", "audio"),
                lang=(data.get("lang") or "en").strip() or "en",
                noise_level=_parse_float_param(data, "noise_level", 0.0, 0.0, 1.0),
                background_tone_hz=_parse_float_param(data, "background_tone_hz", 0.0, 0.0, 20000.0),
                background_tone_level=_parse_float_param(data, "background_tone_level", 0.2, 0.0, 1.0),
                pitch_semitones=_parse_float_param(data, "pitch_semitones", 0.0, -12.0, 12.0),
                speed_factor=_parse_float_param(data, "speed_factor", 1.0, 0.5, 2.0),
                echo_delay_ms=_parse_float_param(data, "echo_delay_ms", 0.0, 0.0, 1000.0),
                echo_decay=_parse_float_param(data, "echo_decay", 0.4, 0.0, 1.0),
                distortion=_parse_float_param(data, "distortion", 0.0, 0.0, 1.0),
                gain_db=_parse_float_param(data, "gain_db", 0.0, -20.0, 20.0),
                low_pass_hz=_parse_float_param(data, "low_pass_hz", 0.0, 0.0, 20000.0),
                high_pass_hz=_parse_float_param(data, "high_pass_hz", 0.0, 0.0, 20000.0),
                overlay_text=overlay_text,
                overlay_level=_parse_float_param(data, "overlay_level", 0.15, 0.0, 1.0),
            )
            from payloads.audio import describe_tts_effects

            effects_applied = describe_tts_effects(
                noise_level=tts_kwargs["noise_level"],
                background_tone_hz=tts_kwargs["background_tone_hz"],
                background_tone_level=tts_kwargs["background_tone_level"],
                pitch_semitones=tts_kwargs["pitch_semitones"],
                speed_factor=tts_kwargs["speed_factor"],
                echo_delay_ms=tts_kwargs["echo_delay_ms"],
                echo_decay=tts_kwargs["echo_decay"],
                distortion=tts_kwargs["distortion"],
                gain_db=tts_kwargs["gain_db"],
                low_pass_hz=tts_kwargs["low_pass_hz"],
                high_pass_hz=tts_kwargs["high_pass_hz"],
                overlay_text=overlay_text,
                overlay_level=tts_kwargs["overlay_level"],
            )
            path = payloads.generate_audio_tts(**tts_kwargs)
        else:
            return jsonify({"error": f"Unknown asset_type: {asset_type}"}), 400
        if path is None:
            return jsonify({"error": "Generation failed"}), 500
        path = Path(path).resolve()
        if not path.is_file():
            return jsonify({"error": "Generated file not found"}), 500
        relative_path = _payloads_relative_path(path)
        response = {"path": str(path), "relative_path": relative_path}
        if asset_type == "audio_tts":
            response["effects_applied"] = effects_applied
        if path.suffix.lower() == ".mp3":
            response["warning"] = (
                "Saved as MP3 because ffmpeg is unavailable for WAV conversion. "
                "Install ffmpeg on PATH for WAV output."
            )
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/payloads/list", methods=["GET"])
def api_payloads_list():
    """List files under the payloads output directory (safe, no path traversal)."""
    out_dir = _payloads_output_dir()
    if not out_dir.is_dir():
        return jsonify({"files": []})
    files = []
    for p in out_dir.rglob("*"):
        if p.is_file():
            try:
                rel = p.relative_to(out_dir)
                rel_str = str(rel).replace("\\", "/")
                if ".." in rel_str or rel_str.startswith("/"):
                    continue
                stat = p.stat()
                files.append({
                    "name": p.name,
                    "relative_path": rel_str,
                    "size": stat.st_size,
                    "mtime": int(stat.st_mtime),
                })
            except ValueError:
                continue
    files.sort(key=lambda x: (x["relative_path"],))
    return jsonify({"files": files})


@app.route("/api/payloads/file/<path:relative_path>")
def api_payloads_file(relative_path):
    """Serve a file from the payloads output directory. Validates path stays under output (no traversal)."""
    relative_path = (relative_path or "").strip().replace("\\", "/")
    if ".." in relative_path or relative_path.startswith("/"):
        return jsonify({"error": "Invalid path"}), 400
    out_dir = _payloads_output_dir()
    full = (out_dir / relative_path).resolve()
    if not full.is_file():
        return jsonify({"error": "Not found"}), 404
    try:
        full.relative_to(out_dir)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400
    inline = request.args.get("inline", "").strip().lower() in ("1", "true", "yes")
    return _send_local_file(full, inline=inline)


def run_app():
    """Run the Flask app (host/port from env). Called from api/__main__.py."""
    from core.config import get_port
    _ensure_db()
    port = get_port()
    app.run(host="0.0.0.0", port=port)
