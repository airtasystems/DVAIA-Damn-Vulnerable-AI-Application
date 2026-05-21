"""
RAG retrieval: embeddings for semantic search. Chunks and documents are embedded when added.
Search uses Qdrant vector similarity. Keyword fallback removed when using Qdrant.
Documents are split into smaller chunks so retrieval returns only relevant parts.
"""
from typing import Any, Dict, List, Optional

from app import embeddings as app_embeddings
from app import vector_store as app_vector_store


# Max chars to embed (avoid exceeding model context; full content still stored)
_EMBED_MAX_CHARS = 8000

# Document chunking: size and overlap for splitting long text before embedding
_CHUNK_SIZE = 500
_CHUNK_OVERLAP = 50


def _chunk_text(text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> List[str]:
    """Split text into overlapping chunks (paragraphs preferred, then by size)."""
    text = (text or "").strip()
    if not text:
        return []
    # Prefer paragraph boundaries (double newline)
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    for p in parts:
        if len(p) <= chunk_size:
            chunks.append(p)
        else:
            start = 0
            while start < len(p):
                end = start + chunk_size
                chunks.append(p[start:end])
                start = end - overlap
                if start >= len(p):
                    break
    return chunks if chunks else [text[:chunk_size]]


def add_document(source: str, text: str) -> int:
    """Split document text into chunks, embed each, and add to RAG. Returns number of chunks added."""
    chunks = _chunk_text(text)
    for chunk in chunks:
        add_chunk(source, chunk)
    return len(chunks)


def add_chunk(source: str, content: str) -> str:
    """Insert a chunk and compute its embedding; store in Qdrant. Returns point id (UUID string)."""
    to_embed = content if len(content) <= _EMBED_MAX_CHARS else content[:_EMBED_MAX_CHARS]
    vec = app_embeddings.embed_text(to_embed)
    if not vec:
        raise RuntimeError("Could not embed chunk; embedding service unavailable or returned empty.")
    return app_vector_store.add_point(source, content, vec)


# For diverse retrieval: fetch this many then take top_k_per_source per source
_SEARCH_DIVERSE_FETCH = 200
_TOP_K_PER_SOURCE = 10


def search(query: str, top_k: int = 5) -> List[str]:
    """Semantic search: embed query, return top_k chunks by similarity via Qdrant."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        query_vec = app_embeddings.embed_text(q)
        if not query_vec:
            return []
        hits = app_vector_store.search(query_vec, limit=top_k)
        return [h["content"] for h in hits if h.get("content")]
    except Exception:
        return []


def search_diverse(
    query: str,
    top_k_per_source: int = _TOP_K_PER_SOURCE,
    fetch_limit: int = _SEARCH_DIVERSE_FETCH,
    source_filter: Optional[str] = None,
) -> List[str]:
    """Semantic search; returns content strings only (backward compatible)."""
    hits = search_diverse_hits(
        query,
        top_k_per_source=top_k_per_source,
        fetch_limit=fetch_limit,
        source_filter=source_filter,
    )
    return [h["content"] for h in hits if h.get("content")]


def search_diverse_hits(
    query: str,
    top_k_per_source: int = _TOP_K_PER_SOURCE,
    fetch_limit: int = _SEARCH_DIVERSE_FETCH,
    source_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Semantic search returning chunk dicts: content, source, score.
    Optional source_filter limits results to one indexed source label.
    """
    q = (query or "").strip()
    if not q:
        return []
    try:
        query_vec = app_embeddings.embed_text(q)
        if not query_vec:
            return []
        hits = app_vector_store.search_with_scores(query_vec, limit=fetch_limit)
        if not hits:
            return []
        if source_filter:
            sf = source_filter.strip()
            hits = [h for h in hits if (h.get("source") or "").strip() == sf]
            if not hits:
                return []
        by_source: Dict[str, List[Dict[str, Any]]] = {}
        for h in hits:
            if not h.get("content"):
                continue
            src = (h.get("source") or "").strip() or "unknown"
            by_source.setdefault(src, []).append(h)
        chosen = []
        for list_h in by_source.values():
            for h in list_h[:top_k_per_source]:
                chosen.append(h)
        chosen.sort(key=lambda x: (x.get("score") is None, -(x.get("score") or 0)))
        return chosen
    except Exception:
        return []


def format_chunks_for_prompt(hits: List[Dict[str, Any]]) -> str:
    """Format retrieved chunks with explicit source labels for the LLM."""
    parts: List[str] = []
    for idx, hit in enumerate(hits, start=1):
        content = (hit.get("content") or "").strip()
        if not content:
            continue
        src = (hit.get("source") or "unknown").strip()
        score = hit.get("score")
        header = f"[retrieved chunk {idx} | source: {src}"
        if score is not None:
            header += f" | score: {score:.3f}"
        header += "]"
        parts.append(f"{header}\n{content}")
    return "\n\n".join(parts)


def list_sources() -> List[str]:
    """Distinct source labels currently indexed in RAG."""
    seen: set[str] = set()
    sources: List[str] = []
    for row in list_chunks():
        src = (row.get("source") or "").strip()
        if src and src not in seen:
            seen.add(src)
            sources.append(src)
    sources.sort()
    return sources


def resolve_rag_source_label(
    *,
    document_id: Optional[int] = None,
    payload_relative_path: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Optional[str]:
    """Map UI document selection to the RAG source label used at index time."""
    from app import documents as app_documents

    if payload_relative_path:
        return payload_relative_path.strip().replace("\\", "/")
    if document_id is not None:
        doc = app_documents.get_document(document_id, user_id)
        if not doc:
            return None
        return (doc.get("filename") or f"document_{document_id}").strip()
    return None


def list_chunks() -> List[Dict[str, Any]]:
    """Return all RAG chunks (id, source, content, created_at) from Qdrant."""
    return app_vector_store.list_all()


def delete_chunks_by_source(source: str) -> None:
    """Delete all RAG chunks with the given source (e.g. filename). Used for experiment cleanup."""
    app_vector_store.delete_by_source(source)
