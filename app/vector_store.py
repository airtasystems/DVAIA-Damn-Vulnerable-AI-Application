"""
Qdrant vector store for RAG. Single place for collection create, upsert, search, list.
Uses app.config for QDRANT_URL, QDRANT_COLLECTION, optional QDRANT_API_KEY.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import (
    get_qdrant_api_key,
    get_qdrant_collection,
    get_qdrant_collection_for_provider,
    get_qdrant_url,
)

_client = None


def _get_client():
    """Lazy init Qdrant client."""
    global _client
    if _client is None:
        from qdrant_client import QdrantClient

        url = get_qdrant_url()
        api_key = get_qdrant_api_key()
        _client = QdrantClient(url=url, api_key=api_key)
    return _client


def _collection_name(llm_provider: Optional[str] = None) -> str:
    if llm_provider:
        return get_qdrant_collection_for_provider(llm_provider)
    return get_qdrant_collection()


def reset_collection(llm_provider: Optional[str] = None) -> None:
    """Delete the RAG collection if it exists. Next add will recreate it. Used for RESET_DB_ON_START."""
    try:
        client = _get_client()
        name = _collection_name(llm_provider)
        if client.collection_exists(name):
            client.delete_collection(name)
    except Exception:
        pass


def invalidate_client_cache() -> None:
    """Drop cached Qdrant client (e.g. after collections were deleted elsewhere)."""
    global _client
    _client = None


def reset_all_rag_collections() -> List[str]:
    """Delete all RAG collections (explicit + default Ollama/Gemini names)."""
    import os

    names: List[str] = []
    explicit = os.getenv("QDRANT_COLLECTION", "").strip()
    if explicit:
        names.append(explicit)
    for default_name in ("rag_chunks", "rag_chunks_gemini", "rag_chunks_openai"):
        if default_name not in names:
            names.append(default_name)

    client = _get_client()
    cleared: List[str] = []
    errors: List[str] = []
    for name in names:
        try:
            if client.collection_exists(name):
                client.delete_collection(name)
                cleared.append(name)
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    if errors and not cleared:
        raise RuntimeError("Could not clear RAG collections: " + "; ".join(errors))
    invalidate_client_cache()
    return cleared


def _ensure_collection(dimension: int, llm_provider: Optional[str] = None) -> None:
    """Create collection if it does not exist. dimension must match embedding size."""
    from qdrant_client.models import Distance, VectorParams

    client = _get_client()
    name = _collection_name(llm_provider)
    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
        )


def add_point(
    source: str,
    content: str,
    vector: List[float],
    llm_provider: Optional[str] = None,
) -> str:
    """
    Upsert one point into the RAG collection. Creates collection on first use.
    Returns the point id (UUID string).
    """
    if not vector:
        raise ValueError("vector must be non-empty")
    _ensure_collection(len(vector), llm_provider)
    client = _get_client()
    point_id = str(uuid.uuid4())
    from qdrant_client.models import PointStruct

    created_at = datetime.now(timezone.utc).isoformat()
    client.upsert(
        collection_name=_collection_name(llm_provider),
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload={"source": source, "content": content, "created_at": created_at},
            )
        ],
    )
    return point_id


def search(
    query_vector: List[float],
    limit: int = 5,
    llm_provider: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Similarity search. Returns list of payload dicts with at least "content".
    Returns empty list if collection does not exist or query fails.
    """
    hits = search_with_scores(query_vector, limit=limit, llm_provider=llm_provider)
    return [{k: v for k, v in h.items() if k != "score"} for h in hits]


def search_with_scores(
    query_vector: List[float],
    limit: int = 5,
    llm_provider: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Similarity search returning payload dicts plus "score" (similarity).
    Used by search_diverse to take top N per source.
    """
    if not query_vector:
        return []
    try:
        client = _get_client()
        name = _collection_name(llm_provider)
        if not client.collection_exists(name):
            return []
        result = client.query_points(
            collection_name=name,
            query=query_vector,
            with_payload=True,
            with_vectors=False,
            limit=limit,
        )
        out = []
        for p in result.points:
            payload = p.payload or {}
            score = getattr(p, "score", None)
            out.append(
                {
                    "id": p.id,
                    "content": payload.get("content", ""),
                    "source": payload.get("source", ""),
                    "created_at": payload.get("created_at"),
                    "score": score,
                }
            )
        return out
    except Exception:
        return []


def list_all(llm_provider: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return all points as list of dicts: id, source, content, created_at."""
    try:
        client = _get_client()
        name = _collection_name(llm_provider)
        if not client.collection_exists(name):
            return []
        out = []
        offset = None
        while True:
            points, next_offset = client.scroll(
                collection_name=name,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for p in points:
                payload = p.payload or {}
                out.append(
                    {
                        "id": p.id,
                        "source": payload.get("source", ""),
                        "content": payload.get("content", ""),
                        "created_at": payload.get("created_at"),
                    }
                )
            if next_offset is None:
                break
            offset = next_offset
        return out
    except Exception:
        return []


def delete_by_source(source: str, llm_provider: Optional[str] = None) -> None:
    """Delete all points in the RAG collection whose payload source equals the given value."""
    if not (source or str(source).strip()):
        return
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector

        client = _get_client()
        name = _collection_name(llm_provider)
        if not client.collection_exists(name):
            return
        client.delete(
            collection_name=name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="source", match=MatchValue(value=source))],
                ),
            ),
        )
    except Exception:
        pass
