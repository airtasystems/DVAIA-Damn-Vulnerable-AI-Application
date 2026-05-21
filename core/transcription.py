"""
Local speech-to-text for Document Injection using faster-whisper (OpenAI Whisper weights).
"""
from __future__ import annotations

import logging
import os
import tempfile
from typing import Iterable, List, Optional

from core.config import (
    get_whisper_compute_type,
    get_whisper_device,
    get_whisper_gain_boost_db,
    get_whisper_model_name,
    get_whisper_multi_pass,
    get_whisper_no_speech_threshold,
    get_whisper_vad_filter,
)

logger = logging.getLogger(__name__)

_model = None


def get_transcription_backend() -> str:
    return "whisper"


def _get_model():
    global _model
    if _model is not None:
        return _model
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "Whisper transcription unavailable. Install faster-whisper (see requirements.txt)."
        ) from exc
    _model = WhisperModel(
        get_whisper_model_name(),
        device=get_whisper_device(),
        compute_type=get_whisper_compute_type(),
    )
    return _model


def _dedupe_transcripts(texts: Iterable[str]) -> List[str]:
    """Keep distinct transcript strings (case-insensitive), preferring longer phrases."""
    ordered: List[str] = []
    for raw in texts:
        text = (raw or "").strip()
        if not text:
            continue
        lowered = text.lower()
        replaced = False
        for idx, existing in enumerate(ordered):
            existing_lower = existing.lower()
            if lowered == existing_lower:
                replaced = True
                break
            if lowered in existing_lower:
                replaced = True
                break
            if existing_lower in lowered:
                ordered[idx] = text
                replaced = True
                break
        if not replaced:
            ordered.append(text)
    return ordered


def _merge_transcripts(texts: Iterable[str]) -> str:
    parts = _dedupe_transcripts(texts)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return " | ".join(parts)


def _prepare_audio_variants(file_path: str) -> tuple[List[str], List[str]]:
    """
    Build mono 16kHz WAV variants for Whisper: original path, normalized, and gain-boosted.
    Returns (paths, temp_paths_to_cleanup).
    """
    paths: List[str] = [file_path]
    temp_paths: List[str] = []
    if not get_whisper_multi_pass():
        return paths, temp_paths
    try:
        from pydub import AudioSegment, effects
    except ImportError:
        return paths, temp_paths

    try:
        segment = AudioSegment.from_file(file_path).set_channels(1).set_frame_rate(16000)
    except Exception as exc:
        logger.warning("Audio preprocess failed for %s: %s", file_path, exc)
        return paths, temp_paths

    variants = [
        effects.normalize(segment),
        effects.normalize(segment + get_whisper_gain_boost_db()),
    ]
    for variant in variants:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        try:
            variant.export(tmp.name, format="wav")
            paths.append(tmp.name)
            temp_paths.append(tmp.name)
        except Exception:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
    return paths, temp_paths


def _transcribe_path(file_path: str) -> str:
    model = _get_model()
    segments, _info = model.transcribe(
        file_path,
        beam_size=5,
        vad_filter=get_whisper_vad_filter(),
        no_speech_threshold=get_whisper_no_speech_threshold(),
        without_timestamps=True,
    )
    parts = [(segment.text or "").strip() for segment in segments]
    parts = [part for part in parts if part]
    return " ".join(parts).strip()


def transcribe_audio(file_path: str) -> str:
    """
    Transcribe an audio file to text. Supports common formats via ffmpeg (wav, mp3, ogg, etc.).
    Runs optional multi-pass (normalize + gain boost) to capture quiet overlay speech.
    """
    variant_paths, temp_paths = _prepare_audio_variants(file_path)
    transcripts: List[str] = []
    try:
        for path in variant_paths:
            try:
                text = _transcribe_path(path)
            except Exception as exc:
                logger.warning("Whisper pass failed for %s: %s", path, exc)
                continue
            if text:
                transcripts.append(text)
    finally:
        for path in temp_paths:
            try:
                os.unlink(path)
            except OSError:
                pass
    return _merge_transcripts(transcripts)


def transcribe_audio_with_fallback(file_path: str) -> tuple[str, str]:
    """
    Transcribe audio with Whisper; optionally fall back to Google STT.
    Returns (text, backend) where backend is 'whisper' or 'google'.
    """
    from core.config import whisper_google_fallback_enabled

    try:
        text = transcribe_audio(file_path)
        if text:
            return text, "whisper"
    except Exception as exc:
        logger.warning("Whisper transcription failed for %s: %s", file_path, exc)
        if not whisper_google_fallback_enabled():
            raise

    if not whisper_google_fallback_enabled():
        return "", "whisper"

    text = _transcribe_google(file_path)
    return text, "google"


def _transcribe_google(file_path: str) -> str:
    """Legacy Google Web Speech API fallback (requires network)."""
    try:
        import speech_recognition as sr
        from pydub import AudioSegment
    except ImportError as exc:
        raise RuntimeError(
            "Google STT fallback unavailable. Install SpeechRecognition and pydub."
        ) from exc

    tmp_path: Optional[str] = None
    try:
        segment = AudioSegment.from_file(file_path)
        segment = segment.set_channels(1).set_frame_rate(16000)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        segment.export(tmp_path, format="wav")
        recognizer = sr.Recognizer()
        with sr.AudioFile(tmp_path) as source:
            audio = recognizer.record(source)
        return (recognizer.recognize_google(audio) or "").strip()
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
