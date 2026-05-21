"""
LangChain LLM factory: get_llm(model_id) returns a BaseChatModel for simple or agentic use.

Use for:
  - Simple: llm.invoke(messages) or use core.models.generate()
  - Agentic: llm.bind_tools(tools), create_react_agent(), RAG chains, etc.

Backends:
  - Ollama local (OLLAMA_HOST): ollama:llama3.2 or bare model name
  - Gemini cloud (GOOGLE_API_KEY): gemini:gemini-2.0-flash or google:...
  - OpenAI cloud (OPENAI_API_KEY): openai:gpt-4o-mini
"""
import warnings
from typing import Any, Optional

warnings.filterwarnings(
    "ignore",
    message=".*Pydantic V1.*Python 3.14.*",
)

from core.config import get_default_model_id, get_google_api_key, get_openai_api_key, get_ollama_host
from core.providers import detect_provider, strip_provider_prefix

OLLAMA_PREFIX = "ollama:"
GEMINI_PREFIX = "gemini:"


def _ollama_model_name(model_id: str) -> str:
    """Extract Ollama model name (strip ollama: prefix if present)."""
    name = strip_provider_prefix(model_id)
    return name or "llama3.2"


def _gemini_model_name(model_id: str) -> str:
    """Extract Gemini model name (strip gemini:/google: prefix)."""
    s = (model_id or "").strip()
    lower = s.lower()
    if lower.startswith("google:"):
        return s[len("google:") :].strip() or "gemini-2.0-flash"
    return strip_provider_prefix(s) or "gemini-2.0-flash"


def _require_gemini_key() -> str:
    key = get_google_api_key()
    if not key:
        raise RuntimeError(
            "Gemini selected but GOOGLE_API_KEY is not set. "
            "Add your Google AI Studio key to .env or choose Local (Ollama) in the UI."
        )
    return key


def _openai_model_name(model_id: str) -> str:
    return strip_provider_prefix(model_id) or "gpt-4o-mini"


def _require_openai_key() -> str:
    key = get_openai_api_key()
    if not key:
        raise RuntimeError(
            "OpenAI selected but OPENAI_API_KEY is not set. "
            "Add your API key to .env or choose another backend in Settings."
        )
    return key


def get_llm(
    model_id: Optional[str] = None,
    *,
    timeout: Optional[int] = 120,
    **kwargs: Any,
) -> Any:
    """
    Return a LangChain chat model for the given model_id.

    Uses DEFAULT_MODEL from env when model_id is not passed.
    Routes to ChatOllama or ChatGoogleGenerativeAI by prefix.
    """
    resolved = (model_id or get_default_model_id()).strip()
    if not resolved:
        resolved = get_default_model_id()

    provider = detect_provider(resolved)

    if provider == "openai":
        api_key = _require_openai_key()
        name = _openai_model_name(resolved)
        openai_kwargs = {k: v for k, v in kwargs.items() if k not in ("reasoning", "repeat_penalty", "top_k")}
        if "max_output_tokens" in openai_kwargs and "max_tokens" not in openai_kwargs:
            openai_kwargs["max_tokens"] = openai_kwargs.pop("max_output_tokens")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=name,
            api_key=api_key,
            timeout=timeout,
            **openai_kwargs,
        )

    if provider == "gemini":
        api_key = _require_gemini_key()
        name = _gemini_model_name(resolved)
        gemini_kwargs = {k: v for k, v in kwargs.items() if k != "reasoning"}
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=name,
            google_api_key=api_key,
            timeout=timeout,
            **gemini_kwargs,
        )

    name = _ollama_model_name(resolved)
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=name,
        base_url=get_ollama_host().rstrip("/"),
        timeout=timeout,
        **kwargs,
    )
