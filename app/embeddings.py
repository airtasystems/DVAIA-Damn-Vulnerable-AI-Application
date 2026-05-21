"""
Embedding service for RAG using Ollama, Gemini, or OpenAI.
Documents and chunks are embedded when added; search uses similarity over vectors.
"""
from typing import List, Optional

from core.config import (
    get_embedding_backend,
    get_embedding_model_id,
    get_gemini_embedding_model,
    get_google_api_key,
    get_openai_api_key,
    get_openai_embedding_model,
    get_ollama_host,
)

_embeddings_cache: dict = {}


def _backend_for_provider(llm_provider: Optional[str] = None) -> str:
    """Resolve embedding backend from explicit provider or env default."""
    if llm_provider:
        p = llm_provider.strip().lower()
        if p in ("gemini", "openai", "ollama"):
            return p
    backend = get_embedding_backend()
    return backend if backend in ("ollama", "gemini", "openai") else "ollama"


def _collection_suffix_key(backend: str) -> str:
    if backend in ("gemini", "openai"):
        return backend
    return "ollama"


def _get_embeddings(backend: Optional[str] = None):
    """Lazy init embeddings client for ollama, gemini, or openai."""
    resolved = _backend_for_provider(backend)
    cache_key = _collection_suffix_key(resolved)
    if cache_key in _embeddings_cache:
        return _embeddings_cache[cache_key]

    if resolved == "openai":
        api_key = get_openai_api_key()
        if not api_key:
            raise RuntimeError(
                "OpenAI embeddings require OPENAI_API_KEY. "
                "Set the key in .env or choose another backend in Settings."
            )
        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError:
            raise RuntimeError(
                "OpenAI embeddings require langchain-openai. pip install langchain-openai"
            )
        model = get_openai_embedding_model()
        _embeddings_cache[cache_key] = OpenAIEmbeddings(model=model, api_key=api_key)
        return _embeddings_cache[cache_key]

    if resolved == "gemini":
        api_key = get_google_api_key()
        if not api_key:
            raise RuntimeError(
                "Gemini embeddings require GOOGLE_API_KEY. "
                "Set the key in .env or choose Local (Ollama) in the UI."
            )
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
        except ImportError:
            raise RuntimeError(
                "Gemini embeddings require langchain-google-genai. pip install langchain-google-genai"
            )
        model = get_gemini_embedding_model()
        _embeddings_cache[cache_key] = GoogleGenerativeAIEmbeddings(
            model=model,
            google_api_key=api_key,
        )
        return _embeddings_cache[cache_key]

    try:
        from langchain_ollama import OllamaEmbeddings
    except ImportError:
        raise RuntimeError(
            "Ollama embeddings require langchain-ollama. pip install langchain-ollama"
        )
    model = get_embedding_model_id()
    base_url = get_ollama_host()
    _embeddings_cache[cache_key] = OllamaEmbeddings(model=model, base_url=base_url)
    return _embeddings_cache[cache_key]


def clear_embeddings_cache() -> None:
    """Drop cached embedding clients (e.g. after API key change)."""
    _embeddings_cache.clear()


def embed_text(text: str, llm_provider: Optional[str] = None) -> List[float]:
    """Embed a single string; returns list of floats."""
    if not (text or "").strip():
        return []
    backend = _backend_for_provider(llm_provider)
    emb = _get_embeddings(backend)
    return emb.embed_query(text.strip())


def embed_texts(texts: List[str], llm_provider: Optional[str] = None) -> List[List[float]]:
    """Embed multiple strings; returns list of vectors."""
    if not texts:
        return []
    stripped = [t.strip() for t in texts if (t or "").strip()]
    if not stripped:
        return []
    backend = _backend_for_provider(llm_provider)
    emb = _get_embeddings(backend)
    return emb.embed_documents(stripped)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors. Assumes non-zero."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
