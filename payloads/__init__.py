"""
Payload generation suite for red-team testing (document injection, multimodal).
Generators return the path to the created file. Use from scripts or via API/UI.
"""
from pathlib import Path
from typing import BinaryIO, List, Optional, Union

from payloads.config import get_output_dir, get_project_root

__all__ = [
    "get_output_dir",
    "get_project_root",
    "generate_text",
    "generate_pdf",
    "generate_pdf_visible",
    "generate_pdf_invisible",
    "generate_pdf_metadata",
    "generate_csv",
    "generate_image",
    "generate_qr",
    "generate_audio_synthetic",
    "generate_audio_tts",
]


def generate_text(
    content: str,
    filename: Optional[str] = None,
    subdir: str = "docs",
    extension: str = "txt",
) -> Path:
    """Write a plain text file. Returns absolute path to the created file."""
    from payloads import documents

    return documents.write_text_file(
        content=content,
        filename=filename,
        subdir=subdir,
        extension=extension,
    )


def generate_pdf(
    text_lines: Optional[List[Union[str, dict]]] = None,
    hidden_content: Optional[str] = None,
    filename: Optional[str] = None,
    subdir: str = "docs",
    source_pdf: Optional[Union[str, Path, BinaryIO, bytes]] = None,
) -> Path:
    """Create a PDF with up to 3 lines (font_size, color, alpha, position). Optional hidden content; optional source PDF to overlay. Returns absolute path."""
    from payloads import documents

    return documents.create_pdf_with_lines(
        text_lines=text_lines,
        hidden_content=hidden_content,
        filename=filename,
        subdir=subdir,
        source_pdf=source_pdf,
    )


def generate_pdf_visible(
    content: str,
    filename: Optional[str] = None,
    subdir: str = "docs",
) -> Path:
    """Create a PDF with visible text. Returns absolute path."""
    from payloads import documents

    return documents.create_visible_text_pdf(
        content=content,
        filename=filename,
        subdir=subdir,
    )


def generate_pdf_invisible(
    visible_content: str,
    hidden_content: str,
    filename: Optional[str] = None,
    subdir: str = "docs",
) -> Path:
    """Create a PDF with visible text and hidden (white-on-white) text. Returns absolute path."""
    from payloads import documents

    return documents.create_pdf_with_invisible_text(
        visible_content=visible_content,
        hidden_content=hidden_content,
        filename=filename,
        subdir=subdir,
    )


def generate_pdf_metadata(
    body_content: str,
    subject: str = "",
    author: str = "",
    filename: Optional[str] = None,
    subdir: str = "docs",
    source_pdf: Optional[str] = None,
) -> Path:
    """Create a PDF with optional metadata payload (Subject/Author). Optional source_pdf to set metadata on existing PDF."""
    from payloads import documents

    return documents.create_pdf_with_metadata(
        body_content=body_content,
        subject=subject,
        author=author,
        filename=filename,
        subdir=subdir,
        source_pdf=source_pdf,
    )


def generate_csv(
    content: Optional[str] = None,
    columns: Optional[Union[str, List]] = None,
    num_rows: int = 10,
    filename: Optional[str] = None,
    subdir: str = "docs",
    use_faker: bool = True,
) -> Path:
    """Create a CSV file. Custom content (paste) or generated dummy data. Optional Faker for realistic data. Returns absolute path."""
    from payloads import csv as csv_module

    return csv_module.create_csv(
        content=content,
        columns=columns,
        num_rows=num_rows,
        filename=filename,
        subdir=subdir,
        use_faker=use_faker,
    )


def generate_image(
    content: Optional[str] = None,
    width: int = 400,
    height: int = 200,
    filename: Optional[str] = None,
    subdir: str = "images",
    low_contrast: bool = False,
    background_color: Optional[str] = None,
    text_color: Optional[str] = None,
    background_alpha: int = 255,
    text_alpha: int = 255,
    text_rotation: float = 0.0,
    blur_radius: float = 0.0,
    noise_level: float = 0.0,
    source_image: Optional[Union[str, Path, bytes, BinaryIO]] = None,
    text_lines: Optional[List[Union[str, dict]]] = None,
    position: str = "top_left",
    font_size: int = 14,
) -> Path:
    """Create an image with text overlay. Per-line: text, font_size, color, alpha, position. Optional source_image. Returns absolute path."""
    from payloads import images

    return images.create_text_image(
        content=content,
        width=width,
        height=height,
        filename=filename,
        subdir=subdir,
        low_contrast=low_contrast,
        background_color=background_color,
        text_color=text_color,
        background_alpha=background_alpha,
        text_alpha=text_alpha,
        text_rotation=text_rotation,
        blur_radius=blur_radius,
        noise_level=noise_level,
        source_image=source_image,
        text_lines=text_lines,
        position=position,
        font_size=font_size,
    )


def generate_qr(
    payload: str,
    filename: Optional[str] = None,
    subdir: str = "images",
    composite_width: Optional[int] = None,
    composite_height: Optional[int] = None,
) -> Path:
    """Create a QR code image (optionally composited onto a larger image). Returns absolute path."""
    from payloads import qr as qr_module

    return qr_module.create_qr_image(
        payload=payload,
        filename=filename,
        subdir=subdir,
        composite_width=composite_width,
        composite_height=composite_height,
    )


def generate_audio_synthetic(
    duration_sec: float = 1.0,
    frequency: float = 440.0,
    filename: Optional[str] = None,
    subdir: str = "audio",
) -> Path:
    """Create a synthetic WAV (sine tone). Returns absolute path."""
    from payloads import audio

    return audio.create_synthetic_wav(
        duration_sec=duration_sec,
        frequency=frequency,
        filename=filename,
        subdir=subdir,
    )


def generate_audio_tts(
    text: str,
    filename: Optional[str] = None,
    subdir: str = "audio",
    lang: str = "en",
    *,
    noise_level: float = 0.0,
    background_tone_hz: float = 0.0,
    background_tone_level: float = 0.2,
    pitch_semitones: float = 0.0,
    speed_factor: float = 1.0,
    echo_delay_ms: float = 0.0,
    echo_decay: float = 0.4,
    distortion: float = 0.0,
    gain_db: float = 0.0,
    low_pass_hz: float = 0.0,
    high_pass_hz: float = 0.0,
    overlay_text: Optional[str] = None,
    overlay_level: float = 0.15,
) -> Path:
    """
    Create a WAV from text (TTS). Uses gTTS + pydub if available; returns MP3 when ffmpeg is missing.
    Optional post-processing effects support ASR/transcription red-team testing.
    """
    from payloads import audio

    return audio.create_tts_wav(
        text=text,
        filename=filename,
        subdir=subdir,
        lang=lang,
        noise_level=noise_level,
        background_tone_hz=background_tone_hz,
        background_tone_level=background_tone_level,
        pitch_semitones=pitch_semitones,
        speed_factor=speed_factor,
        echo_delay_ms=echo_delay_ms,
        echo_decay=echo_decay,
        distortion=distortion,
        gain_db=gain_db,
        low_pass_hz=low_pass_hz,
        high_pass_hz=high_pass_hz,
        overlay_text=overlay_text,
        overlay_level=overlay_level,
    )
