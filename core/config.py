"""
Shared config: default model and .env loading. Used by core, api, and runner.
Site-specific config (RECORDED, Origin/Referer, submissions) is loaded from CONFIG_DIR
(e.g. config/genbounty or config/localhost3000).
"""
import importlib
import json
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore

DEFAULT_MODEL = "ollama:llama3.2"
# Agentic panel: thinking model (e.g. qwen3:0.6b) for CoT visibility; override with AGENTIC_MODEL
AGENTIC_MODEL = "qwen3:0.6b"
# Document Injection vision path: image files sent directly to a VLM; override with VISION_MODEL
VISION_MODEL = "ollama:qwen2.5vl:7b"
# Document Injection audio extract path: local Whisper via faster-whisper; override with WHISPER_MODEL
WHISPER_MODEL = "base"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"
WHISPER_NO_SPEECH_THRESHOLD = 0.35
WHISPER_GAIN_BOOST_DB = 15
WHISPER_MULTI_PASS = True
# Web Injection: use Playwright headless browser for JS-rendered pages (requires playwright + chromium)
WEB_FETCH_JS = False
OLLAMA_HOST = "http://localhost:11480"  # override with env OLLAMA_HOST
# Runner and Docker: base URL and port from .env (no hardcoded localhost in code)
REDTEAM_API_URL_DEFAULT = "http://127.0.0.1:5000"
PORT_DEFAULT = 5000
# Embedding backend: ollama
EMBEDDING_BACKEND = "ollama"
# Embedding model for RAG (Ollama model name, e.g. nomic-embed-text)
EMBEDDING_MODEL = "nomic-embed-text"
# Ollama embedding model
EMBEDDING_MODEL_GEMINI = "text-embedding-004"

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _ensure_env_loaded() -> None:
    if load_dotenv and _ENV_PATH.exists():
        load_dotenv(_ENV_PATH)


def _get_config_dir() -> str:
    """CONFIG_DIR from .env (e.g. config/genbounty or config/localhost3000). Loads .env first."""
    _ensure_env_loaded()
    return (os.getenv("CONFIG_DIR") or "config/genbounty").strip().rstrip("/") or "config/genbounty"


def get_config_dir() -> str:
    """Return CONFIG_DIR from .env (e.g. config/genbounty). Used for log paths under config/[sitename]/logs/."""
    return _get_config_dir()


def _get_site_config_module():
    """Load the site config module for CONFIG_DIR. If COMPONENT is set, load that module; else site_config (or genbounty_config)."""
    config_dir = _get_config_dir()
    component = (os.getenv("COMPONENT") or "").strip()
    if component:
        # Sanitize to a valid Python identifier (e.g. chat_widget)
        component = component.lower().replace("-", "_")
        component = "".join(c for c in component if c.isalnum() or c == "_") or "site_config"
        pkg = config_dir.replace("/", ".")
        # Prefer config/[site]/components/[component].py
        try:
            return importlib.import_module(pkg + ".components." + component)
        except ImportError:
            pass
        try:
            return importlib.import_module(pkg + "." + component)
        except ImportError:
            pass
    if config_dir == "config/genbounty":
        import config.genbounty.genbounty_config as m
        return m
    pkg = config_dir.replace("/", ".")
    return importlib.import_module(pkg + ".site_config")


def _recorded(key: str) -> Optional[str]:
    """Return value from the current site config RECORDED dict (CONFIG_DIR)."""
    if _site is None:
        return None
    try:
        val = _site.RECORDED.get(key)
        return (val or "").strip() or None
    except (AttributeError, KeyError):
        return None


def get_redteam_api_url() -> str:
    """Base URL of the API under test. REDTEAM_API_URL or RECORDED; default REDTEAM_API_URL_DEFAULT."""
    _ensure_env_loaded()
    val = _recorded("REDTEAM_API_URL") or os.getenv("REDTEAM_API_URL", REDTEAM_API_URL_DEFAULT)
    return (val or REDTEAM_API_URL_DEFAULT).strip().rstrip("/") or REDTEAM_API_URL_DEFAULT


def get_redteam_http_version() -> Optional[str]:
    """
    HTTP version for curl_cffi: "v1" (HTTP/1.1) or None (default HTTP/2).
    Use "v1" for local dev servers (Flask etc.) that don't support HTTP/2 to avoid
    "Empty reply from server" (curl error 52). Set REDTEAM_HTTP_VERSION=v1 to force,
    or it auto-defaults to v1 when REDTEAM_API_URL host is localhost/127.0.0.1.
    """
    _ensure_env_loaded()
    explicit = os.getenv("REDTEAM_HTTP_VERSION", "").strip().lower()
    if explicit in ("v1", "v2", "v2tls", "v2_prior_knowledge", "v3", "v3only"):
        return explicit
    base = get_redteam_api_url()
    try:
        host = (urlparse(base).hostname or "").lower()
        if host in ("localhost", "127.0.0.1", "::1"):
            return "v1"
    except Exception:
        pass
    return None


def get_port() -> int:
    """Port for the Flask API and Docker host mapping. PORT; default PORT_DEFAULT."""
    _ensure_env_loaded()
    try:
        return int(os.getenv("PORT", str(PORT_DEFAULT)))
    except ValueError:
        return PORT_DEFAULT


def get_default_model_id() -> str:
    """Default model from .env (DEFAULT_MODEL). Loads project .env when resolving."""
    _ensure_env_loaded()
    return os.getenv("DEFAULT_MODEL", DEFAULT_MODEL)


def get_agentic_model_id() -> str:
    """Model for Agentic panel (thinking/CoT). From .env AGENTIC_MODEL; default qwen3:0.6b."""
    _ensure_env_loaded()
    return os.getenv("AGENTIC_MODEL", AGENTIC_MODEL).strip() or AGENTIC_MODEL


def get_vision_model_id() -> str:
    """Model for Document Injection vision mode (image bytes to VLM). From .env VISION_MODEL."""
    _ensure_env_loaded()
    return os.getenv("VISION_MODEL", VISION_MODEL).strip() or VISION_MODEL


def get_whisper_model_name() -> str:
    """Whisper model size/name for audio transcription (faster-whisper). From .env WHISPER_MODEL."""
    _ensure_env_loaded()
    return os.getenv("WHISPER_MODEL", WHISPER_MODEL).strip() or WHISPER_MODEL


def get_whisper_device() -> str:
    """Device for faster-whisper: cpu or cuda. From .env WHISPER_DEVICE."""
    _ensure_env_loaded()
    return os.getenv("WHISPER_DEVICE", WHISPER_DEVICE).strip() or WHISPER_DEVICE


def get_whisper_compute_type() -> str:
    """Compute type for faster-whisper (e.g. int8, float16). From .env WHISPER_COMPUTE_TYPE."""
    _ensure_env_loaded()
    return os.getenv("WHISPER_COMPUTE_TYPE", WHISPER_COMPUTE_TYPE).strip() or WHISPER_COMPUTE_TYPE


def get_whisper_vad_filter() -> bool:
    """When True, Whisper VAD skips non-speech — can drop quiet overlay tracks. Default off for red-team audio."""
    _ensure_env_loaded()
    val = os.getenv("WHISPER_VAD_FILTER", "false").strip().lower()
    return val in ("1", "true", "yes")


def whisper_google_fallback_enabled() -> bool:
    """When True, fall back to Google Web Speech if Whisper fails. From .env WHISPER_FALLBACK_GOOGLE."""
    _ensure_env_loaded()
    val = os.getenv("WHISPER_FALLBACK_GOOGLE", "false").strip().lower()
    return val in ("1", "true", "yes")


def get_whisper_no_speech_threshold() -> float:
    """Lower values make Whisper more sensitive to quiet speech. From .env WHISPER_NO_SPEECH_THRESHOLD."""
    _ensure_env_loaded()
    try:
        return float(os.getenv("WHISPER_NO_SPEECH_THRESHOLD", str(WHISPER_NO_SPEECH_THRESHOLD)))
    except ValueError:
        return WHISPER_NO_SPEECH_THRESHOLD


def get_whisper_gain_boost_db() -> float:
    """Extra gain (dB) for a second Whisper pass to capture quiet overlay tracks."""
    _ensure_env_loaded()
    try:
        return float(os.getenv("WHISPER_GAIN_BOOST_DB", str(WHISPER_GAIN_BOOST_DB)))
    except ValueError:
        return WHISPER_GAIN_BOOST_DB


def get_whisper_multi_pass() -> bool:
    """When True, run Whisper on normalized and gain-boosted variants and merge results."""
    _ensure_env_loaded()
    val = os.getenv("WHISPER_MULTI_PASS", "true" if WHISPER_MULTI_PASS else "false").strip().lower()
    return val in ("1", "true", "yes")


def get_web_fetch_js() -> bool:
    """When True, fetch URLs with Playwright (headless Chromium) instead of HTTP-only."""
    _ensure_env_loaded()
    val = os.getenv("WEB_FETCH_JS", "true" if WEB_FETCH_JS else "false").strip().lower()
    return val in ("1", "true", "yes")


def get_ollama_host() -> str:
    """Ollama base URL from .env (OLLAMA_HOST). Loads project .env when resolving."""
    _ensure_env_loaded()
    return os.getenv("OLLAMA_HOST", OLLAMA_HOST)


def get_embedding_backend() -> str:
    """Embedding backend for RAG: ollama only. Used by app.embeddings."""
    _ensure_env_loaded()
    return os.getenv("EMBEDDING_BACKEND", EMBEDDING_BACKEND).strip().lower()


def get_embedding_model_id() -> str:
    """Embedding model for RAG (e.g. nomic-embed-text). Used by app.embeddings when backend is ollama."""
    _ensure_env_loaded()
    return os.getenv("EMBEDDING_MODEL", EMBEDDING_MODEL)


def get_ollama_embedding_model() -> str:
    """Ollama embedding model. Used for RAG embeddings."""
    _ensure_env_loaded()
    return os.getenv("EMBEDDING_MODEL_GEMINI", EMBEDDING_MODEL_GEMINI)


def _require_path(env_key: str) -> str:
    """Return env value for API path; raise if missing or empty (no default fallback)."""
    _ensure_env_loaded()
    val = os.getenv(env_key)
    if not val or not str(val).strip():
        raise RuntimeError(f"{env_key} must be set in environment (no default)")
    return str(val).strip()


def get_chat_path() -> str:
    """Chat endpoint path from CHAT_PATH or RECORDED. Required (no default) when not recorded."""
    val = _recorded("CHAT_PATH")
    if val:
        return val
    return _require_path("CHAT_PATH")


def get_chat_with_context_path() -> str:
    """Chat-with-context endpoint path from CHAT_WITH_CONTEXT_PATH or RECORDED. Required when not recorded."""
    val = _recorded("CHAT_WITH_CONTEXT_PATH")
    if val:
        return val
    return _require_path("CHAT_WITH_CONTEXT_PATH")


def get_login_path() -> str:
    """Login endpoint path from LOGIN_PATH or RECORDED. Required when not recorded."""
    val = _recorded("LOGIN_PATH")
    if val:
        return val
    return _require_path("LOGIN_PATH")


def get_document_upload_path() -> str:
    """Document upload endpoint path from DOCUMENT_PATH. Required (no default)."""
    return _require_path("DOCUMENT_PATH")


def get_rag_add_document_path() -> str:
    """
    RAG add-document path from RAG_ADD_DOCUMENT_PATH. Required (no default).
    Path without the document_id suffix, e.g. /api/rag/add-document. Code appends /{document_id}.
    """
    return _require_path("RAG_ADD_DOCUMENT_PATH")


def get_rag_delete_by_source_path() -> str:
    """
    RAG delete-by-source path from RAG_DELETE_BY_SOURCE_PATH.
    Default: /api/rag/delete-by-source. Used for experiment cleanup.
    """
    _ensure_env_loaded()
    val = os.getenv("RAG_DELETE_BY_SOURCE_PATH")
    if val and str(val).strip():
        return str(val).strip()
    return "/api/rag/delete-by-source"


def get_chat_with_template_path() -> str:
    """
    Chat-with-template endpoint path from CHAT_WITH_TEMPLATE_PATH.
    Default: /api/chat-with-template. Used for real-world template injection tests.
    """
    _ensure_env_loaded()
    val = os.getenv("CHAT_WITH_TEMPLATE_PATH")
    if val and str(val).strip():
        return str(val).strip()
    return "/api/chat-with-template"


def get_use_session() -> bool:
    """
    Whether to establish one session at run start for all tests (apps behind login).
    RECORDED or REDTEAM_USE_SESSION: truthy (1, true, yes) enables session-based auth.
    """
    _ensure_env_loaded()
    val = _recorded("REDTEAM_USE_SESSION") or os.getenv("REDTEAM_USE_SESSION", "").strip().lower()
    return val in ("1", "true", "yes")


def get_parallel_workers() -> int:
    """
    Number of tests to run in parallel. REDTEAM_PARALLEL; default 1 (sequential).
    When > 1, each worker uses a cloned session (no 401 retry across workers).
    """
    _ensure_env_loaded()
    try:
        return max(1, int(os.getenv("REDTEAM_PARALLEL", "1").strip()))
    except ValueError:
        return 1


def get_refresh_session_before_run() -> bool:
    """
    When True, run refresh_session.py (Selenium cookie refresh) before loading the session.
    Use when the app rotates tokens (e.g. genbounty). REDTEAM_REFRESH_SESSION_BEFORE_RUN: 1, true, yes.
    """
    _ensure_env_loaded()
    val = os.getenv("REDTEAM_REFRESH_SESSION_BEFORE_RUN", "").strip().lower()
    return val in ("1", "true", "yes")


def get_login_mode() -> str:
    """
    How to obtain the session when REDTEAM_USE_SESSION is set.
    REDTEAM_LOGIN_MODE: "api" (POST JSON to LOGIN_PATH) or "selenium" (browser login + cookies).
    Default: "api".
    """
    _ensure_env_loaded()
    val = os.getenv("REDTEAM_LOGIN_MODE", "api").strip().lower()
    return val if val in ("api", "selenium") else "api"


def get_redteam_username() -> str:
    """Username for runner login. REDTEAM_USERNAME; default "test"."""
    _ensure_env_loaded()
    return os.getenv("REDTEAM_USERNAME", "test").strip() or "test"


def get_redteam_password() -> str:
    """Password for runner login. REDTEAM_PASSWORD; default "test"."""
    _ensure_env_loaded()
    return os.getenv("REDTEAM_PASSWORD", "test")


def get_session_cookies_file() -> Optional[str]:
    """
    Optional path to a JSON file of cookies (e.g. from record_session.py).
    RECORDED or REDTEAM_SESSION_COOKIES_FILE; no default.
    """
    _ensure_env_loaded()
    val = _recorded("REDTEAM_SESSION_COOKIES_FILE") or os.getenv("REDTEAM_SESSION_COOKIES_FILE", "").strip()
    return val if val else None


def get_redteam_bearer_token() -> Optional[str]:
    """
    Optional Bearer token for APIs that use Authorization: Bearer instead of (or in addition to) cookies.
    When set, the runner adds this header to every request.
    Source: REDTEAM_BEARER_TOKEN env, or auth_session.json bearer_token in CONFIG_DIR.
    """
    _ensure_env_loaded()
    val = os.getenv("REDTEAM_BEARER_TOKEN", "").strip()
    if val:
        return val
    try:
        config_dir = _get_config_dir()
        auth_path = Path(__file__).resolve().parent.parent / config_dir / "auth_session.json"
        if auth_path.exists():
            data = json.loads(auth_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                token = (data.get("bearer_token") or "").strip()
                if token:
                    return token
    except Exception:
        pass
    return None


# Default browser User-Agent for test requests (Cloudflare WAF / bot detection)
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def get_redteam_user_agent() -> str:
    """
    User-Agent for test requests. Set REDTEAM_USER_AGENT in .env or override in site config
    so requests look like a browser (helps with Cloudflare WAF).
    """
    _ensure_env_loaded()
    val = os.getenv("REDTEAM_USER_AGENT", "").strip()
    if val:
        return val
    return getattr(_site, "get_redteam_user_agent", lambda: _DEFAULT_USER_AGENT)()


def get_csrf_token_path() -> str:
    """
    Path for fetching CSRF token (GET with session). Used for apps that require a fresh token.
    REDTEAM_CSRF_TOKEN_PATH; default /api/v2/auth/csrf-token.
    """
    _ensure_env_loaded()
    val = os.getenv("REDTEAM_CSRF_TOKEN_PATH", "").strip()
    return val if val else "/api/v2/auth/csrf-token"


def get_auth_refresh_path() -> str:
    """
    Path for POST auth refresh (cookie-based; no CSRF). Session must send refresh_token cookie.
    REDTEAM_AUTH_REFRESH_PATH; default /api/v2/auth/refresh.
    """
    _ensure_env_loaded()
    val = os.getenv("REDTEAM_AUTH_REFRESH_PATH", "").strip()
    return val if val else "/api/v2/auth/refresh"


def get_redteam_csrf_token() -> Optional[str]:
    """
    Optional CSRF token (fallback when fetch fails). RECORDED or REDTEAM_CSRF_TOKEN; no default.
    """
    _ensure_env_loaded()
    val = _recorded("REDTEAM_CSRF_TOKEN") or os.getenv("REDTEAM_CSRF_TOKEN", "").strip()
    return val if val else None


def get_redteam_csrf_header() -> str:
    """Header name for CSRF token. REDTEAM_CSRF_HEADER; default X-CSRF-Token."""
    _ensure_env_loaded()
    val = os.getenv("REDTEAM_CSRF_HEADER", "X-CSRF-Token").strip()
    return val if val else "X-CSRF-Token"


# Site-specific config (request mode, Origin/Referer, program body, submissions) from CONFIG_DIR
# Components can omit genbounty/submissions-only getters; we use defaults then.
# For DVAIA standalone, site config is optional (used only for testing external APIs)
try:
    _site = _get_site_config_module()
except (ImportError, ModuleNotFoundError):
    _site = None


def _default_chat_request_body_key() -> str:
    return "prompt"


def _default_get_redteam_origin() -> Optional[str]:
    return None


def _default_get_redteam_referer() -> Optional[str]:
    return None


def _default_get_redteam_project_url() -> str:
    return get_redteam_api_url()


def _default_get_redteam_company_name() -> str:
    return "Genbounty"


def _default_get_redteam_project_type() -> str:
    return "pmm"


def _default_get_submissions_path() -> str:
    return "/api/v2/submissions"


def _default_get_redteam_submission_program_id() -> str:
    return ""


def _default_get_redteam_submission_email() -> str:
    return "parisbase@proton.me"


def _default_get_redteam_submission_level() -> str:
    return "low"


def _default_get_redteam_submission_status() -> str:
    return "submitted"


def _default_get_redteam_submission_title() -> Optional[str]:
    return None


def _default_get_delay_between_tests() -> float:
    return 0.3


def _default_get_429_backoff_initial() -> float:
    return 30.0


def _default_get_429_backoff_max_wait() -> float:
    return 60.0


def _default_get_429_backoff_max_retries() -> int:
    return 6


get_chat_request_body_key = getattr(_site, "get_chat_request_body_key", _default_chat_request_body_key)
get_chat_request_mode = getattr(_site, "get_chat_request_mode", lambda: "default")
# Optional: site/component can define build_chat_payload(prompt, model_id) -> dict for custom JSON body
build_chat_payload_override = getattr(_site, "build_chat_payload", None)
get_redteam_company_name = getattr(_site, "get_redteam_company_name", _default_get_redteam_company_name)
get_redteam_origin = getattr(_site, "get_redteam_origin", _default_get_redteam_origin)
get_redteam_project_type = getattr(_site, "get_redteam_project_type", _default_get_redteam_project_type)
get_redteam_project_url = getattr(_site, "get_redteam_project_url", _default_get_redteam_project_url)
get_redteam_referer = getattr(_site, "get_redteam_referer", _default_get_redteam_referer)
get_redteam_submission_email = getattr(_site, "get_redteam_submission_email", _default_get_redteam_submission_email)
get_redteam_submission_level = getattr(_site, "get_redteam_submission_level", _default_get_redteam_submission_level)
get_redteam_submission_program_id = getattr(_site, "get_redteam_submission_program_id", _default_get_redteam_submission_program_id)
get_redteam_submission_status = getattr(_site, "get_redteam_submission_status", _default_get_redteam_submission_status)
get_redteam_submission_title = getattr(_site, "get_redteam_submission_title", _default_get_redteam_submission_title)
get_submissions_path = getattr(_site, "get_submissions_path", _default_get_submissions_path)
get_delay_between_tests = getattr(_site, "get_delay_between_tests", _default_get_delay_between_tests)
get_429_backoff_initial_seconds = getattr(_site, "get_429_backoff_initial_seconds", _default_get_429_backoff_initial)
get_429_backoff_max_wait = getattr(_site, "get_429_backoff_max_wait", _default_get_429_backoff_max_wait)
get_429_backoff_max_retries = getattr(_site, "get_429_backoff_max_retries", _default_get_429_backoff_max_retries)


def _default_is_rate_limit_response(_status_code: int, _response_text: str) -> bool:
    """Default: only HTTP 429 is treated as rate limit."""
    return False


get_is_rate_limit_response = getattr(_site, "get_is_rate_limit_response", _default_is_rate_limit_response)


def get_refresh_session_module():
    """Return the refresh_session module for CONFIG_DIR (e.g. config.genbounty.refresh_session)."""
    config_dir = _get_config_dir()
    pkg = config_dir.replace("/", ".")
    return importlib.import_module(pkg + ".refresh_session")
