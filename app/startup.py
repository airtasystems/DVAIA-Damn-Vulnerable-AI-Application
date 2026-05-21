"""Startup hooks: optional wipe of document DB, uploads, and RAG when RESET_DATA_ON_START is enabled."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional


def clear_document_store() -> Dict[str, Any]:
    """Delete all uploaded documents (DB rows and files). Does not touch users/MFA or payloads."""
    from app import documents as app_documents
    from app.config import get_upload_dir

    docs = app_documents.list_documents(user_id=None)
    removed = 0
    for doc in docs:
        if app_documents.delete_document(doc["id"], user_id=None):
            removed += 1

    upload_path = Path(get_upload_dir())
    if upload_path.is_dir():
        shutil.rmtree(upload_path, ignore_errors=True)
    upload_path.mkdir(parents=True, exist_ok=True)

    return {"documents_removed": removed, "upload_dir": str(upload_path)}


def clear_payload_outputs() -> Dict[str, Any]:
    """Remove generated payload files under PAYLOADS_OUTPUT_DIR."""
    from payloads.config import get_output_dir

    out_dir = get_output_dir()
    count = sum(1 for p in out_dir.rglob("*") if p.is_file()) if out_dir.is_dir() else 0
    if out_dir.is_dir():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    return {"payload_files_removed": count, "payloads_output_dir": str(out_dir)}


def clear_rag_index() -> List[str]:
    """Delete all RAG Qdrant collections."""
    from app import vector_store as app_vector_store

    return app_vector_store.reset_all_rag_collections()


def clear_lab_data(*, include_payloads: bool = True) -> Dict[str, Any]:
    """Wipe uploads, optional generated payloads, and RAG vectors (keeps users table)."""
    doc_result = clear_document_store()
    payload_result: Optional[Dict[str, Any]] = None
    if include_payloads:
        payload_result = clear_payload_outputs()

    collections: List[str] = []
    try:
        collections = clear_rag_index()
    except Exception as exc:
        raise RuntimeError(f"RAG clear failed: {exc}") from exc

    out: Dict[str, Any] = {
        **doc_result,
        "collections": collections,
    }
    if payload_result:
        out.update(payload_result)
    return out


def apply_startup_reset() -> Dict[str, Any]:
    """
    When reset_data_on_start is enabled, delete SQLite DB, uploads dir, and RAG collections.
    Called once per worker process at import time (gunicorn / python -m api).
    """
    from core.config import reset_data_on_start_enabled

    if not reset_data_on_start_enabled():
        return {"applied": False, "reason": "reset_data_on_start disabled"}

    from app.config import get_database_uri, get_upload_dir

    db_path = Path(get_database_uri())
    if db_path.is_file():
        db_path.unlink()

    upload_path = Path(get_upload_dir())
    if upload_path.is_dir():
        shutil.rmtree(upload_path, ignore_errors=True)

    collections: List[str] = []
    try:
        collections = clear_rag_index()
    except Exception:
        pass

    return {
        "applied": True,
        "database_uri": str(db_path),
        "upload_dir": str(upload_path),
        "collections": collections,
    }


def warmup_llm_backends() -> Dict[str, Any]:
    """
    Eager-load LLM clients so the first user prompt is not paying import/connection setup cost.
    Does not send a generation request (no API tokens consumed).
    """
    from core.config import gemini_configured, is_gemini_only_mode, is_openai_only_mode, openai_configured

    warmed = []
    if gemini_configured() or is_gemini_only_mode():
        try:
            from core.gemini_client import _get_client

            _get_client()
            warmed.append("gemini")
        except Exception:
            pass
    if openai_configured() or is_openai_only_mode():
        try:
            from core.openai_client import _get_client

            _get_client()
            warmed.append("openai")
        except Exception:
            pass
    return {"warmed": warmed}
