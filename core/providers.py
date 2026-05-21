"""
LLM provider resolution: map UI provider choice (ollama | gemini | openai) to model_id strings.
"""
from typing import Any, Dict

from core.config import (
    get_agentic_model_id,
    get_default_model_id,
    get_gemini_agentic_model,
    get_gemini_chat_model,
    get_gemini_vision_model,
    get_openai_agentic_model,
    get_openai_chat_model,
    get_openai_vision_model,
    get_vision_model_id,
    gemini_configured,
    openai_configured,
)

GEMINI_PREFIX = "gemini:"
OPENAI_PREFIX = "openai:"
OLLAMA_PREFIX = "ollama:"


def _with_gemini_prefix(model_name: str) -> str:
    name = (model_name or "").strip()
    if not name:
        return f"{GEMINI_PREFIX}{get_gemini_chat_model()}"
    lower = name.lower()
    if lower.startswith(GEMINI_PREFIX) or lower.startswith("google:"):
        return name
    return f"{GEMINI_PREFIX}{name}"


def _with_openai_prefix(model_name: str) -> str:
    name = (model_name or "").strip()
    if not name:
        return f"{OPENAI_PREFIX}{get_openai_chat_model()}"
    lower = name.lower()
    if lower.startswith(OPENAI_PREFIX):
        return name
    return f"{OPENAI_PREFIX}{name}"


def _normalize_ollama_id(model_id: str) -> str:
    s = (model_id or "").strip()
    if not s:
        return f"{OLLAMA_PREFIX}llama3.2"
    lower = s.lower()
    if lower.startswith(GEMINI_PREFIX) or lower.startswith("google:") or lower.startswith(OPENAI_PREFIX):
        return get_default_model_id()
    if not lower.startswith(OLLAMA_PREFIX):
        return f"{OLLAMA_PREFIX}{s}"
    return s


def detect_provider(model_id: str) -> str:
    """Return 'openai', 'gemini', or 'ollama' based on model_id prefix."""
    s = (model_id or "").strip().lower()
    if s.startswith(OPENAI_PREFIX):
        return "openai"
    if s.startswith(GEMINI_PREFIX) or s.startswith("google:"):
        return "gemini"
    return "ollama"


def strip_provider_prefix(model_id: str) -> str:
    """Return bare model name without ollama:/gemini:/google:/openai: prefix."""
    s = (model_id or "").strip()
    lower = s.lower()
    for prefix in (OPENAI_PREFIX, GEMINI_PREFIX, "google:", OLLAMA_PREFIX):
        if lower.startswith(prefix):
            return s[len(prefix) :].strip()
    return s


def resolve_models_for_provider(provider: str) -> Dict[str, Any]:
    """
    Map provider name to model_ids for each role.
    Returns {chat, vision, agentic, embedding_backend, available}.
    """
    p = (provider or "ollama").strip().lower()
    if p == "openai":
        available = openai_configured()
        return {
            "available": available,
            "chat": _with_openai_prefix(get_openai_chat_model()),
            "vision": _with_openai_prefix(get_openai_vision_model()),
            "agentic": _with_openai_prefix(get_openai_agentic_model()),
            "embedding_backend": "openai",
        }
    if p == "gemini":
        available = gemini_configured()
        return {
            "available": available,
            "chat": _with_gemini_prefix(get_gemini_chat_model()),
            "vision": _with_gemini_prefix(get_gemini_vision_model()),
            "agentic": _with_gemini_prefix(get_gemini_agentic_model()),
            "embedding_backend": "gemini",
        }
    return {
        "available": True,
        "chat": _normalize_ollama_id(get_default_model_id()),
        "vision": _normalize_ollama_id(get_vision_model_id()),
        "agentic": _normalize_ollama_id(get_agentic_model_id()),
        "embedding_backend": "ollama",
    }


def providers_payload() -> Dict[str, Any]:
    """Full providers block for GET /api/models."""
    return {
        "ollama": resolve_models_for_provider("ollama"),
        "gemini": resolve_models_for_provider("gemini"),
        "openai": resolve_models_for_provider("openai"),
    }
