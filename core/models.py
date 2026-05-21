"""
Model router: generate(prompt, model_id) for Ollama, Gemini, and OpenAI backends.

Uses LangChain under the hood (core.llm.get_llm) so simple and agentic flows share one stack.
model_id format:
  - "ollama:llama3.2" or "llama3.2" → local Ollama (OLLAMA_HOST)
  - "gemini:gemini-2.0-flash" or "google:..." → Google Gemini API (GOOGLE_API_KEY)
  - "openai:gpt-4o-mini" → OpenAI API (OPENAI_API_KEY)
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
from core.content_utils import extract_text_content
from core.gemini_client import (
    generate_messages as gemini_generate_messages,
    generate_text as gemini_generate_text,
    generate_with_images as gemini_generate_with_images,
)
from core.openai_client import (
    generate_messages as openai_generate_messages,
    generate_text as openai_generate_text,
    generate_with_images as openai_generate_with_images,
)
from core.llm import get_llm
from core.providers import detect_provider


def _options_to_llm_kwargs(options: Optional[Dict[str, Any]], model_id: Optional[str] = None) -> Dict[str, Any]:
    """Map request options to get_llm kwargs for Ollama or Gemini."""
    if not options:
        return {}
    out: Dict[str, Any] = {}
    provider = detect_provider(model_id or "")
    num = options.get("num_predict") or options.get("max_tokens")
    if num is not None:
        try:
            n = int(num)
            if provider == "gemini":
                out["max_output_tokens"] = n
            elif provider == "openai":
                out["max_tokens"] = n
            else:
                out["num_predict"] = n
        except (TypeError, ValueError):
            pass
    if "temperature" in options and options["temperature"] is not None:
        try:
            out["temperature"] = float(options["temperature"])
        except (TypeError, ValueError):
            pass
    if "top_k" in options and options["top_k"] is not None and provider not in ("openai",):
        try:
            out["top_k"] = int(options["top_k"])
        except (TypeError, ValueError):
            pass
    if provider == "ollama" and "repeat_penalty" in options and options["repeat_penalty"] is not None:
        try:
            out["repeat_penalty"] = float(options["repeat_penalty"])
        except (TypeError, ValueError):
            pass
    if "top_p" in options and options["top_p"] is not None:
        try:
            out["top_p"] = float(options["top_p"])
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
    Send prompt plus one or more local image files to a vision-capable model (Ollama or Gemini).
    Returns {"text": str, "thinking": ""}.
    """
    model_id = model_id or DEFAULT_MODEL
    provider = detect_provider(model_id)
    llm_kwargs = _options_to_llm_kwargs(options, model_id)
    if provider == "openai":
        text = openai_generate_with_images(
            model_id,
            prompt or "",
            image_paths,
            options=llm_kwargs,
        )
        return {"text": text or "No text returned.", "thinking": ""}
    if provider == "gemini":
        text = gemini_generate_with_images(
            model_id,
            prompt or "",
            image_paths,
            options=llm_kwargs,
        )
        return {"text": text or "No text returned.", "thinking": ""}

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
    text = extract_text_content(getattr(msg, "content", None))
    text = text or "No text returned."
    return {"text": text, "thinking": ""}


def generate(
    prompt: Optional[str] = None,
    model_id: Optional[str] = DEFAULT_MODEL,
    options: Optional[Dict[str, Any]] = None,
    messages: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, str]:
    """
    Send prompt or messages to Ollama or Gemini.
    - prompt: single turn (optional if messages is set).
    - messages: multi-turn list of {role, content}; used instead of prompt when set.
    - options: generation options (num_predict, temperature, top_k, top_p, repeat_penalty).
    Returns {"text": str, "thinking": ""} (thinking not supported for Ollama).
    """
    model_id = model_id or DEFAULT_MODEL
    provider = detect_provider(model_id)
    llm_kwargs = _options_to_llm_kwargs(options, model_id)

    if provider == "openai":
        if messages:
            text = openai_generate_messages(model_id, messages, options=llm_kwargs)
        else:
            text = openai_generate_text(model_id, prompt or "", options=llm_kwargs)
        return {"text": text or "No text returned.", "thinking": ""}

    if provider == "gemini":
        if messages:
            text = gemini_generate_messages(model_id, messages, options=llm_kwargs)
        else:
            text = gemini_generate_text(model_id, prompt or "", options=llm_kwargs)
        return {"text": text or "No text returned.", "thinking": ""}

    llm = get_llm(model_id, **llm_kwargs)

    if messages:
        lc_messages = _messages_to_lc(messages)
        if not lc_messages:
            return {"text": "No text returned.", "thinking": ""}
        msg = llm.invoke(lc_messages)
    else:
        prompt = prompt or ""
        msg = llm.invoke([HumanMessage(content=prompt)])

    text = extract_text_content(getattr(msg, "content", None))
    text = text or "No text returned."

    return {"text": text, "thinking": ""}
