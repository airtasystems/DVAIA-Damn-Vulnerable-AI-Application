"""
OpenAI API via official openai SDK (chat completions + vision).

Uses client.chat.completions.create for text and multimodal messages.
"""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from core.config import get_openai_api_key
from core.providers import strip_provider_prefix

_client = None


def _require_key() -> str:
    key = get_openai_api_key()
    if not key:
        raise RuntimeError(
            "OpenAI selected but OPENAI_API_KEY is not set. "
            "Add your API key to .env or choose another backend in Settings."
        )
    return key


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(api_key=_require_key())
    return _client


def clear_openai_client_cache() -> None:
    """Reset lazy OpenAI SDK client (e.g. after API key change)."""
    global _client
    _client = None


def normalize_model_name(model_id: str) -> str:
    """Bare OpenAI model id, e.g. gpt-4o-mini."""
    return strip_provider_prefix(model_id) or "gpt-4o-mini"


def _completion_kwargs(options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not options:
        return {}
    out: Dict[str, Any] = {}
    if options.get("temperature") is not None:
        out["temperature"] = float(options["temperature"])
    if options.get("top_p") is not None:
        out["top_p"] = float(options["top_p"])
    num = options.get("max_output_tokens") or options.get("max_tokens") or options.get("num_predict")
    if num is not None:
        out["max_tokens"] = int(num)
    return out


def _response_text(response) -> str:
    try:
        choice = response.choices[0]
        content = getattr(getattr(choice, "message", None), "content", None)
        if content:
            return str(content).strip()
    except (AttributeError, IndexError, TypeError):
        pass
    return "No text returned by OpenAI."


def generate_text(
    model_id: str,
    prompt: str,
    *,
    options: Optional[Dict[str, Any]] = None,
    system_instruction: Optional[str] = None,
) -> str:
    """Single-turn text generation."""
    client = _get_client()
    model = normalize_model_name(model_id)
    messages: List[Dict[str, str]] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt or ""})
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        **_completion_kwargs(options),
    )
    return _response_text(response)


def generate_messages(
    model_id: str,
    messages: List[Dict[str, str]],
    *,
    options: Optional[Dict[str, Any]] = None,
) -> str:
    """Multi-turn chat from role/content dicts."""
    client = _get_client()
    model = normalize_model_name(model_id)
    api_messages: List[Dict[str, str]] = []
    for m in messages:
        role = (m.get("role") or "user").strip().lower()
        text = (m.get("content") or "").strip()
        if not text:
            continue
        if role == "assistant":
            api_messages.append({"role": "assistant", "content": text})
        elif role == "system":
            api_messages.append({"role": "system", "content": text})
        else:
            api_messages.append({"role": "user", "content": text})
    if not api_messages:
        return "No text returned."
    response = client.chat.completions.create(
        model=model,
        messages=api_messages,
        **_completion_kwargs(options),
    )
    return _response_text(response)


def generate_with_images(
    model_id: str,
    prompt: str,
    image_paths: List[Union[str, Path]],
    *,
    options: Optional[Dict[str, Any]] = None,
) -> str:
    """Vision / multimodal: text prompt plus local image files."""
    client = _get_client()
    model = normalize_model_name(model_id)
    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt or ""}]
    added = 0
    for raw in image_paths:
        path = Path(raw)
        if not path.is_file():
            continue
        mime = _image_mime_type(path)
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{encoded}"},
        })
        added += 1
    if added == 0:
        return "No valid image files provided."
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        **_completion_kwargs(options),
    )
    return _response_text(response)


def _image_mime_type(path: Path) -> str:
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
