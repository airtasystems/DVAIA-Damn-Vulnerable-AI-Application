"""
Model router: generate(prompt, model_id) for Ollama local models only.

Uses LangChain under the hood (core.llm.get_llm) so simple and agentic flows share one stack.
model_id format:
  - "ollama:llama3.2" or "llama3.2" → local Ollama (OLLAMA_HOST)
"""
from __future__ import annotations

import base64
import mimetypes
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Suppress LangChain/Pydantic v1 warning on Python 3.14+ (before first langchain import)
warnings.filterwarnings(
    "ignore",
    message=".*Pydantic V1.*Python 3.14.*",
)

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from core.config import DEFAULT_MODEL
from core.llm import get_llm


def _options_to_llm_kwargs(options: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Map request options to get_llm kwargs for Ollama."""
    if not options:
        return {}
    out: Dict[str, Any] = {}
    num = options.get("num_predict") or options.get("max_tokens")
    if num is not None:
        try:
            out["num_predict"] = int(num)
        except (TypeError, ValueError):
            pass
    if "temperature" in options and options["temperature"] is not None:
        try:
            out["temperature"] = float(options["temperature"])
        except (TypeError, ValueError):
            pass
    if "top_k" in options and options["top_k"] is not None:
        try:
            out["top_k"] = int(options["top_k"])
        except (TypeError, ValueError):
            pass
    if "top_p" in options and options["top_p"] is not None:
        try:
            out["top_p"] = float(options["top_p"])
        except (TypeError, ValueError):
            pass
    if "repeat_penalty" in options and options["repeat_penalty"] is not None:
        try:
            out["repeat_penalty"] = float(options["repeat_penalty"])
        except (TypeError, ValueError):
            pass
    return out


def _messages_to_lc(messages: List[Dict[str, str]]) -> List[BaseMessage]:
    """Convert [{"role": "user", "content": "..."}, ...] to LangChain message list."""
    lc: List[BaseMessage] = []
    for m in messages:
        role = (m.get("role") or "user").strip().lower()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "system":
            lc.append(SystemMessage(content=content))
        elif role == "assistant":
            lc.append(AIMessage(content=content))
        else:
            lc.append(HumanMessage(content=content))
    return lc


def _image_mime_type(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    if mime and mime.startswith("image/"):
        return mime
    suffix = path.suffix.lower()
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
    return mapping.get(suffix, "image/png")


def _encode_image_data_url(path: Path) -> str:
    data = path.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    mime = _image_mime_type(path)
    return f"data:{mime};base64,{encoded}"


def generate_with_images(
    prompt: str,
    image_paths: List[Union[str, Path]],
    model_id: Optional[str] = DEFAULT_MODEL,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    Send prompt plus one or more local image files to a vision-capable Ollama model.
    Returns {"text": str, "thinking": ""}.
    """
    model_id = model_id or DEFAULT_MODEL
    llm_kwargs = _options_to_llm_kwargs(options)
    llm = get_llm(model_id, **llm_kwargs)

    content: List[Dict[str, str]] = [{"type": "text", "text": prompt or ""}]
    for raw_path in image_paths:
        path = Path(raw_path)
        if not path.is_file():
            continue
        content.append({
            "type": "image_url",
            "image_url": _encode_image_data_url(path),
        })

    if len(content) == 1:
        return {"text": "No valid image files provided.", "thinking": ""}

    msg = llm.invoke([HumanMessage(content=content)])
    text = getattr(msg, "content", None) or ""
    text = (text if isinstance(text, str) else "").strip() or "No text returned."
    return {"text": text, "thinking": ""}


def generate(
    prompt: Optional[str] = None,
    model_id: Optional[str] = DEFAULT_MODEL,
    options: Optional[Dict[str, Any]] = None,
    messages: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, str]:
    """
    Send prompt or messages to Ollama local model.
    - prompt: single turn (optional if messages is set).
    - messages: multi-turn list of {role, content}; used instead of prompt when set.
    - options: generation options (num_predict, temperature, top_k, top_p, repeat_penalty).
    Returns {"text": str, "thinking": ""} (thinking not supported for Ollama).
    """
    model_id = model_id or DEFAULT_MODEL
    
    # Use LangChain ChatOllama
    llm_kwargs = _options_to_llm_kwargs(options)
    llm = get_llm(model_id, **llm_kwargs)

    if messages:
        lc_messages = _messages_to_lc(messages)
        if not lc_messages:
            return {"text": "No text returned.", "thinking": ""}
        msg = llm.invoke(lc_messages)
    else:
        prompt = prompt or ""
        msg = llm.invoke([HumanMessage(content=prompt)])

    text = getattr(msg, "content", None) or ""
    text = (text if isinstance(text, str) else "").strip() or "No text returned."
    
    return {"text": text, "thinking": ""}
