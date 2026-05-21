"""
Gemini API via google-genai SDK (same pattern as gemini_base.py).

Uses client.models.generate_content(model=..., contents=...) and response.text.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from core.config import get_google_api_key
from core.providers import strip_provider_prefix

_client = None


def _require_key() -> str:
    key = get_google_api_key()
    if not key:
        raise RuntimeError(
            "Gemini selected but GOOGLE_API_KEY (or GEMINI_API_KEY) is not set. "
            "Add your Google AI Studio key to .env or choose Local (Ollama) in the UI."
        )
    return key


def _get_client():
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client(api_key=_require_key())
    return _client


def clear_gemini_client_cache() -> None:
    """Reset lazy Gemini SDK client (e.g. after API key change)."""
    global _client
    _client = None


def normalize_model_name(model_id: str) -> str:
    """Bare Gemini model id, e.g. gemini-2.0-flash."""
    return strip_provider_prefix(model_id) or "gemini-2.0-flash"


def _build_config(options: Optional[Dict[str, Any]] = None):
    from google.genai import types

    if not options:
        return None
    cfg: Dict[str, Any] = {}
    if options.get("temperature") is not None:
        cfg["temperature"] = float(options["temperature"])
    if options.get("top_p") is not None:
        cfg["topP"] = float(options["top_p"])
    if options.get("top_k") is not None:
        cfg["topK"] = int(options["top_k"])
    num = options.get("max_output_tokens") or options.get("num_predict") or options.get("max_tokens")
    if num is not None:
        cfg["maxOutputTokens"] = int(num)
    if not cfg:
        return None
    return types.GenerateContentConfig(**cfg)


def _response_text(response) -> str:
    """Extract text from generate_content response (mirrors gemini_base.py)."""
    try:
        if getattr(response, "text", None):
            return str(response.text).strip()
    except Exception:
        pass
    candidates = getattr(response, "candidates", None) or []
    parts_text: List[str] = []
    for cand in candidates:
        content = getattr(cand, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", None) or []:
            text = getattr(part, "text", None)
            if text:
                parts_text.append(str(text))
    if parts_text:
        return "\n".join(parts_text).strip()
    feedback = getattr(response, "prompt_feedback", None)
    if feedback:
        return f"Gemini returned no text (prompt_feedback: {feedback})"
    return "No text returned by Gemini."


def generate_text(
    model_id: str,
    prompt: str,
    *,
    options: Optional[Dict[str, Any]] = None,
    system_instruction: Optional[str] = None,
) -> str:
    """Single-turn text generation."""
    from google.genai import types

    client = _get_client()
    model = normalize_model_name(model_id)
    config = _build_config(options)
    if system_instruction:
        if config is None:
            config = types.GenerateContentConfig(system_instruction=system_instruction)
        else:
            config.system_instruction = system_instruction
    kwargs: Dict[str, Any] = {"model": model, "contents": prompt or ""}
    if config is not None:
        kwargs["config"] = config
    response = client.models.generate_content(**kwargs)
    return _response_text(response)


def generate_messages(
    model_id: str,
    messages: List[Dict[str, str]],
    *,
    options: Optional[Dict[str, Any]] = None,
) -> str:
    """Multi-turn chat from role/content dicts."""
    from google.genai import types

    client = _get_client()
    model = normalize_model_name(model_id)
    system_parts: List[str] = []
    contents: List[types.Content] = []
    for m in messages:
        role = (m.get("role") or "user").strip().lower()
        text = (m.get("content") or "").strip()
        if not text:
            continue
        if role == "system":
            system_parts.append(text)
            continue
        gemini_role = "model" if role == "assistant" else "user"
        contents.append(
            types.Content(role=gemini_role, parts=[types.Part.from_text(text=text)])
        )
    if not contents:
        return "No text returned."
    config = _build_config(options)
    if system_parts:
        if config is None:
            config = types.GenerateContentConfig(system_instruction="\n\n".join(system_parts))
        else:
            config.system_instruction = "\n\n".join(system_parts)
    kwargs: Dict[str, Any] = {"model": model, "contents": contents}
    if config is not None:
        kwargs["config"] = config
    response = client.models.generate_content(**kwargs)
    return _response_text(response)


def generate_with_images(
    model_id: str,
    prompt: str,
    image_paths: List[Union[str, Path]],
    *,
    options: Optional[Dict[str, Any]] = None,
) -> str:
    """Vision / multimodal: text prompt plus local image files."""
    from google.genai import types

    client = _get_client()
    model = normalize_model_name(model_id)
    parts: List[types.Part] = [types.Part.from_text(text=prompt or "")]
    added = 0
    for raw in image_paths:
        path = Path(raw)
        if not path.is_file():
            continue
        mime = _image_mime_type(path)
        parts.append(types.Part.from_bytes(data=path.read_bytes(), mime_type=mime))
        added += 1
    if added == 0:
        return "No valid image files provided."
    config = _build_config(options)
    kwargs: Dict[str, Any] = {
        "model": model,
        "contents": [types.Content(role="user", parts=parts)],
    }
    if config is not None:
        kwargs["config"] = config
    response = client.models.generate_content(**kwargs)
    return _response_text(response)


def _image_mime_type(path: Path) -> str:
    import mimetypes

    mime, _ = mimetypes.guess_type(str(path))
    if mime and mime.startswith("image/"):
        return mime
    mapping = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }
    return mapping.get(path.suffix.lower(), "image/png")
