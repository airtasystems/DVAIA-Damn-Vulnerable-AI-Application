"""
Document upload and text extraction. Used for document-injection tests.
"""
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app import db as app_db
from app.config import get_upload_dir


def save_upload(file_storage: Any, user_id: Optional[int] = None) -> int:
    """
    Save uploaded file to UPLOAD_DIR, insert row in documents, return document_id.
    file_storage: Flask request.files["file"]-like object with .filename and .read().
    """
    upload_dir = get_upload_dir()
    Path(upload_dir).mkdir(parents=True, exist_ok=True)
    filename = file_storage.filename or "unnamed"
    safe_name = f"{uuid.uuid4().hex}_{filename}"
    file_path = os.path.join(upload_dir, safe_name)
    content = file_storage.read()
    with open(file_path, "wb") as f:
        f.write(content)
    extracted = extract_text(file_path)
    return app_db.insert_document(user_id, filename, file_path, extracted)


# Image extensions supported for OCR (Pillow + pytesseract).
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}
_AUDIO_SUFFIXES = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac"}


def resolve_payload_path(relative_path: str) -> Optional[Path]:
    """Resolve a generated payload file under PAYLOADS_OUTPUT_DIR. Returns None if invalid."""
    from payloads.config import get_output_dir

    relative_path = (relative_path or "").strip().replace("\\", "/")
    if not relative_path or ".." in relative_path or relative_path.startswith("/"):
        return None
    out_dir = Path(get_output_dir()).resolve()
    full = (out_dir / relative_path).resolve()
    try:
        full.relative_to(out_dir)
    except ValueError:
        return None
    if not full.is_file():
        return None
    return full


def list_payload_files() -> List[Dict[str, Any]]:
    """List generated payload files from the payloads output directory."""
    from payloads.config import get_output_dir

    out_dir = Path(get_output_dir()).resolve()
    if not out_dir.is_dir():
        return []
    files: List[Dict[str, Any]] = []
    for path in out_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            rel = str(path.relative_to(out_dir)).replace("\\", "/")
        except ValueError:
            continue
        if ".." in rel or rel.startswith("/"):
            continue
        stat = path.stat()
        files.append({
            "name": path.name,
            "relative_path": rel,
            "size": stat.st_size,
            "mtime": int(stat.st_mtime),
        })
    files.sort(key=lambda item: item["relative_path"])
    return files


def resolve_uploaded_document_path(document_id: int, user_id: Optional[int] = None) -> Optional[Path]:
    """Resolve on-disk path for an uploaded document row."""
    row = app_db.get_document(document_id, user_id)
    if not row:
        return None
    file_path = row.get("file_path")
    if not file_path:
        return None
    path = Path(file_path).resolve()
    if not path.is_file():
        return None
    return path


def is_image_path(path: Union[str, Path]) -> bool:
    return Path(path).suffix.lower() in _IMAGE_SUFFIXES


def file_kind(path: Union[str, Path]) -> str:
    """Return coarse file category for UI and routing hints."""
    suffix = Path(path).suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    if suffix in _AUDIO_SUFFIXES:
        return "audio"
    if suffix in {".txt", ".csv", ".pdf", ".docx", ".doc", ".md"} or not suffix:
        return "text"
    return "other"


def resolve_context_file_path(
    context_from: str,
    *,
    document_id: Optional[int] = None,
    payload_relative_path: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Optional[Path]:
    """Resolve a document-injection context file from upload id or payload relative path."""
    if context_from == "upload" and document_id is not None:
        return resolve_uploaded_document_path(document_id, user_id)
    if context_from == "payload" and payload_relative_path:
        return resolve_payload_path(payload_relative_path)
    return None


def extract_payload_text(relative_path: str) -> str:
    """Extract text from a generated payload file by relative path."""
    path = resolve_payload_path(relative_path)
    if path is None:
        return ""
    return extract_text(str(path))


def extract_file_preview(file_path: str) -> Dict[str, Any]:
    """Extract text and routing metadata for extract-preview API."""
    import time

    started = time.perf_counter()
    path = Path(file_path)
    kind = file_kind(path)
    if kind == "audio":
        details = transcribe_audio_details(str(path))
        text = details.get("text") or ""
        normalized, warning = extraction_status(text, kind)
        return {
            "text": normalized,
            "warning": warning,
            "chars": len(normalized),
            "file_kind": kind,
            "supports_vision": False,
            "transcription_backend": details.get("transcription_backend"),
            "extraction_backend": details.get("transcription_backend"),
            "extraction_ms": int((time.perf_counter() - started) * 1000),
            "ocr_hint": None,
        }
    if kind == "image":
        raw = extract_text(str(path))
        text, warning = extraction_status(raw, kind)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        ocr_hint = None
        if text and not warning:
            ocr_hint = (
                "OCR may miss colored overlay or stylized text. "
                "Enable vision mode for fuller image understanding (slower, ~30–90s)."
            )
        return {
            "text": text,
            "warning": warning,
            "chars": len(text),
            "file_kind": kind,
            "supports_vision": True,
            "transcription_backend": None,
            "extraction_backend": "ocr",
            "extraction_ms": elapsed_ms,
            "ocr_hint": ocr_hint,
        }
    raw = extract_text(str(path))
    text, warning = extraction_status(raw, kind)
    return {
        "text": text,
        "warning": warning,
        "chars": len(text),
        "file_kind": kind,
        "supports_vision": kind == "image",
        "transcription_backend": None,
        "extraction_backend": None,
        "extraction_ms": int((time.perf_counter() - started) * 1000),
        "ocr_hint": None,
    }


def extraction_status(text: str, file_kind: str = "other") -> tuple[str, Optional[str]]:
    """Return (normalized_text, warning). warning is set when extraction failed or is partial."""
    cleaned = (text or "").strip()
    if not cleaned:
        if file_kind == "audio":
            return "", "No intelligible speech detected. Whisper returned empty text — try louder TTS or lower overlay masking."
        if file_kind == "image":
            return "", "No text detected by OCR. Try vision mode (qwen2.5vl) for stylized or low-contrast images."
        return "", "No text could be extracted from this file."
    if cleaned.startswith("[") and (
        "unavailable" in cleaned.lower()
        or "failed" in cleaned.lower()
        or "transcription" in cleaned.lower()
    ):
        return cleaned, "Extraction failed or returned an error message instead of document content."
    return cleaned, None


def _decode_qr_image(img) -> str:
    """Decode QR codes embedded in an image."""
    try:
        from pyzbar.pyzbar import decode as qr_decode

        codes = qr_decode(img)
        if not codes:
            return ""
        parts = []
        for code in codes:
            payload = code.data.decode("utf-8", errors="replace").strip()
            if payload:
                parts.append(payload)
        if not parts:
            return ""
        return "QR code payload:\n" + "\n".join(parts)
    except Exception:
        return ""


def _prepare_image_for_ocr(img):
    """Flatten alpha onto white and return RGB base image."""
    from PIL import Image

    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        return background
    return img.convert("RGB")


def _ocr_variant_images(rgb):
    """Build OCR input variants: contrast, color masks, region crops, red-banner isolation."""
    from PIL import Image, ImageFilter, ImageOps

    import numpy as np

    variants = []
    gray = ImageOps.grayscale(rgb)
    contrast = ImageOps.autocontrast(gray)
    scaled = contrast.resize(
        (max(1, contrast.width * 3), max(1, contrast.height * 3)),
        Image.Resampling.LANCZOS,
    )
    sharp = contrast.filter(ImageFilter.SHARPEN)
    inverted = ImageOps.invert(contrast)

    arr = np.array(rgb)
    r = arr[..., 0].astype(np.int16)
    g = arr[..., 1].astype(np.int16)
    b = arr[..., 2].astype(np.int16)

    # Light pink / magenta overlay text (high R+B, lower G)
    pink_mask = (r + b > 360) & (r > g + 15) & (b > g + 5) & (r > 130) & (b > 90)
    pink_layer = np.full(arr.shape[:2], 255, dtype=np.uint8)
    pink_layer[pink_mask] = 0
    pink_img = Image.fromarray(pink_layer, mode="L")

    # Red banner regions → isolate high-luminance text on red
    red_mask = (r > 140) & (g < 120) & (b < 120)
    red_banner = np.full(arr.shape[:2], 255, dtype=np.uint8)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b)
    text_on_red = red_mask & (luminance > 170)
    red_banner[text_on_red] = 0
    red_banner_img = Image.fromarray(red_banner, mode="L")

    width, height = rgb.size
    top_band = rgb.crop((0, 0, width, max(1, int(height * 0.28))))
    top_gray = ImageOps.autocontrast(ImageOps.grayscale(top_band))
    top_scaled = top_gray.resize(
        (max(1, width * 3), max(1, int(height * 0.28 * 3))),
        Image.Resampling.LANCZOS,
    )
    top_contrast = ImageOps.autocontrast(top_scaled)

    center_band = rgb.crop((0, int(height * 0.2), width, int(height * 0.78)))
    center_gray = ImageOps.autocontrast(ImageOps.grayscale(center_band))
    center_scaled = center_gray.resize(
        (max(1, width * 3), max(1, int(height * 0.58 * 3))),
        Image.Resampling.LANCZOS,
    )

    for candidate in (
        rgb,
        contrast,
        scaled,
        sharp,
        inverted,
        pink_img,
        red_banner_img,
        top_scaled,
        top_contrast,
        center_scaled,
    ):
        variants.append(candidate)
    return variants


def _score_ocr_text(text: str) -> int:
    """Heuristic score — prefer longer alphanumeric lines, penalize OCR noise."""
    if not text or not text.strip():
        return 0
    score = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        alnum = sum(ch.isalnum() for ch in line)
        ratio = alnum / max(len(line), 1)
        if len(line) <= 2:
            score -= 8
            continue
        if ratio < 0.45:
            score -= 4
            continue
        score += len(line) + int(ratio * 20)
    return score


def _clean_ocr_lines(text: str) -> str:
    """Keep readable OCR lines and drop obvious noise fragments."""
    cleaned: List[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if len(line) < 3:
            continue
        alnum = sum(ch.isalnum() for ch in line)
        if alnum / max(len(line), 1) < 0.45:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(line)
    return "\n".join(cleaned)


def _best_ocr_for_variants(variants, configs: tuple[str, ...] = ("--psm 6", "--psm 11")) -> str:
    """Run OCR on variants and return the highest-scoring cleaned result."""
    import pytesseract

    best_text = ""
    best_score = 0
    for candidate in variants:
        for config in configs:
            raw = (pytesseract.image_to_string(candidate, config=config) or "").strip()
            cleaned = _clean_ocr_lines(raw)
            score = _score_ocr_text(cleaned)
            if score > best_score:
                best_score = score
                best_text = cleaned
    return best_text


def _ocr_image(file_path: str) -> str:
    """Extract text from an image via QR decode and targeted multi-pass OCR."""
    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        return ""
    try:
        img = Image.open(file_path)
        qr_text = _decode_qr_image(img)
        rgb = _prepare_image_for_ocr(img)
        variants = _ocr_variant_images(rgb)
        (
            _rgb,
            contrast,
            scaled,
            sharp,
            _inverted,
            pink_img,
            _red_banner,
            _top_scaled,
            top_contrast,
            center_scaled,
        ) = variants

        sections: List[str] = []

        overlay = _clean_ocr_lines(
            pytesseract.image_to_string(pink_img, config="--psm 6") or ""
        )
        if overlay:
            sections.append(f"Overlay text:\n{overlay}")

        main_body = _best_ocr_for_variants(
            (contrast, scaled, sharp, top_contrast, center_scaled),
            configs=("--psm 6", "--psm 11"),
        )
        if main_body:
            sections.append(f"OCR text:\n{main_body}")

        ocr_text = "\n\n".join(sections)
        if qr_text and ocr_text:
            return f"{qr_text}\n\n{ocr_text}"
        if qr_text:
            return qr_text
        return ocr_text
    except Exception:
        return ""


def _transcribe_audio(file_path: str) -> str:
    """Transcribe speech audio to text for document-injection context (Whisper via faster-whisper)."""
    try:
        from core.transcription import transcribe_audio_with_fallback

        text, _backend = transcribe_audio_with_fallback(file_path)
        return text
    except Exception as exc:
        return f"[Audio transcription failed: {exc}]"


def transcribe_audio_details(file_path: str) -> dict:
    """Transcribe audio and return text plus backend metadata for API previews."""
    try:
        from core.transcription import get_transcription_backend, transcribe_audio_with_fallback

        text, backend = transcribe_audio_with_fallback(file_path)
        return {
            "text": text,
            "transcription_backend": backend or get_transcription_backend(),
        }
    except Exception as exc:
        return {
            "text": f"[Audio transcription failed: {exc}]",
            "transcription_backend": "whisper",
        }


def extract_text(file_path: str) -> str:
    """Extract text from PDF, docx, plain text, images (OCR), or audio (transcription)."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            try:
                import PyPDF2
                with open(file_path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    parts = []
                    for page in reader.pages:
                        parts.append(page.extract_text() or "")
                    return "\n".join(parts)
            except ImportError:
                return ""
        if suffix in (".docx", ".doc"):
            try:
                import docx
                doc = docx.Document(file_path)
                return "\n".join(p.text for p in doc.paragraphs)
            except ImportError:
                return ""
        if suffix in _IMAGE_SUFFIXES:
            return _ocr_image(file_path)
        if suffix in _AUDIO_SUFFIXES:
            details = transcribe_audio_details(file_path)
            return details.get("text") or ""
        if suffix == ".txt" or not suffix:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        if suffix == ".csv":
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
    except Exception:
        return ""
    return ""


def get_document(document_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Return document metadata and extracted_text. If extracted_text is null or empty, extract and update."""
    row = app_db.get_document(document_id, user_id)
    if not row:
        return None
    current = row.get("extracted_text")
    has_no_text = current is None or (isinstance(current, str) and not current.strip())
    if has_no_text and row.get("file_path"):
        text = extract_text(row["file_path"])
        app_db.update_document_text(document_id, text)
        row["extracted_text"] = text
    return row


def list_documents(user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """List documents for user (or all if user_id is None)."""
    return app_db.list_documents_by_user(user_id)


def delete_document(document_id: int, user_id: Optional[int] = None) -> bool:
    """Get document, remove file from disk if present, delete row. Returns True if deleted."""
    row = app_db.get_document(document_id, user_id)
    if not row:
        return False
    file_path = row.get("file_path")
    if file_path and os.path.isfile(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
    return app_db.delete_document(document_id, user_id)
