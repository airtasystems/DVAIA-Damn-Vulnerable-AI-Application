"""Startup hooks: optional wipe of document DB, uploads, and RAG when RESET_DATA_ON_START is enabled."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict


def apply_startup_reset() -> Dict[str, Any]:
    """
    When reset_data_on_start is enabled, delete SQLite DB, uploads dir, and RAG collections.
    Called once per worker process at import time (gunicorn / python -m api).
    """
    from core.config import reset_data_on_start_enabled

    if not reset_data_on_start_enabled():
        return {"applied": False, "reason": "reset_data_on_start disabled"}

    from app.config import get_database_uri, get_upload_dir
    from app import vector_store as app_vector_store

    db_path = Path(get_database_uri())
    if db_path.is_file():
        db_path.unlink()

    upload_path = Path(get_upload_dir())
    if upload_path.is_dir():
        shutil.rmtree(upload_path, ignore_errors=True)

    collections = []
    try:
        collections = app_vector_store.reset_all_rag_collections()
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
