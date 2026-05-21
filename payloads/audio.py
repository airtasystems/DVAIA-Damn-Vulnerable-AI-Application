"""
Audio payload generators. WAV via stdlib wave; synthetic (scipy/numpy); optional TTS (gTTS+pydub).
Returns absolute Path to created file.
"""
import shutil
import wave
from pathlib import Path
from typing import Optional

import numpy as np

from payloads.config import get_output_dir
from payloads._utils import resolve_output_path


def create_synthetic_wav(
    duration_sec: float = 1.0,
    frequency: float = 440.0,
    sample_rate: int = 44100,
    filename: Optional[str] = None,
    subdir: str = "audio",
    output_path: Optional[Path] = None,
) -> Path:
    """Create a synthetic WAV (sine tone). Returns absolute path."""
    if output_path is not None:
        path = Path(output_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        base = get_output_dir()
        path = resolve_output_path(filename, subdir, "wav", base)
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), dtype=np.float32)
    data = (np.sin(2 * np.pi * frequency * t) * 0.5).astype(np.float32)
    samples = (data * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(samples.tobytes())
    return path


def _synthesize_gtts(text: str, dest: Path, lang: str = "en") -> None:
    from gtts import gTTS

    dest.parent.mkdir(parents=True, exist_ok=True)
    tts = gTTS(text=text[:500], lang=lang)
    tts.save(str(dest))


def _segment_to_mono_float(seg) -> tuple[np.ndarray, int]:
    seg = seg.set_channels(1)
    sr = seg.frame_rate
    samples = np.array(seg.get_array_of_samples(), dtype=np.float32)
    peak = float(2 ** (8 * seg.sample_width - 1))
    if peak > 0:
        samples /= peak
    return samples, sr


def _resample_to_rate(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or len(samples) == 0:
        return samples
    from scipy.signal import resample

    new_len = max(1, int(round(len(samples) * dst_rate / src_rate)))
    return resample(samples, new_len).astype(np.float32)


def _float_to_segment(samples: np.ndarray, sample_rate: int):
    from pydub import AudioSegment

    samples = np.clip(samples, -1.0, 1.0)
    int_samples = (samples * 32767).astype(np.int16)
    return AudioSegment(
        int_samples.tobytes(),
        frame_rate=sample_rate,
        sample_width=2,
        channels=1,
    )


def _load_tts_samples(path: Path, sample_rate: int) -> np.ndarray:
    from pydub import AudioSegment

    suffix = path.suffix.lower()
    if suffix == ".mp3":
        seg = AudioSegment.from_mp3(str(path))
    elif suffix == ".wav":
        seg = AudioSegment.from_wav(str(path))
    else:
        seg = AudioSegment.from_file(str(path))
    samples, sr = _segment_to_mono_float(seg)
    return _resample_to_rate(samples, sr, sample_rate)


def _mix_overlay(main: np.ndarray, overlay: np.ndarray, level: float) -> np.ndarray:
    if level <= 0 or len(overlay) == 0:
        return main
    n = len(main)
    if len(overlay) < n:
        padded = np.zeros(n, dtype=np.float32)
        padded[: len(overlay)] = overlay
        overlay = padded
    else:
        overlay = overlay[:n]
    return main + overlay * level


def _apply_pitch(samples: np.ndarray, semitones: float) -> np.ndarray:
    if semitones == 0 or len(samples) == 0:
        return samples
    from scipy.signal import resample

    factor = 2 ** (semitones / 12)
    n = len(samples)
    intermediate = resample(samples, max(1, int(n / factor)))
    return resample(intermediate, n).astype(np.float32)


def _apply_speed(samples: np.ndarray, factor: float) -> np.ndarray:
    if factor == 1.0 or len(samples) == 0:
        return samples
    from scipy.signal import resample

    return resample(samples, max(1, int(len(samples) / factor))).astype(np.float32)


def _apply_background_tone(
    samples: np.ndarray, sample_rate: int, hz: float, level: float
) -> np.ndarray:
    if hz <= 0 or level <= 0 or len(samples) == 0:
        return samples
    peak = max(float(np.max(np.abs(samples))), 0.05)
    t = np.arange(len(samples), dtype=np.float32) / sample_rate
    tone = np.sin(2 * np.pi * hz * t, dtype=np.float32) * level * peak
    return samples + tone


def _apply_noise(samples: np.ndarray, level: float, rng: np.random.Generator) -> np.ndarray:
    if level <= 0 or len(samples) == 0:
        return samples
    peak = max(float(np.max(np.abs(samples))), 0.05)
    noise = rng.standard_normal(len(samples)).astype(np.float32)
    return samples + noise * level * peak


def _apply_echo(samples: np.ndarray, sample_rate: int, delay_ms: float, decay: float) -> np.ndarray:
    if delay_ms <= 0 or decay <= 0 or len(samples) == 0:
        return samples
    delay_samples = int(sample_rate * delay_ms / 1000)
    if delay_samples <= 0 or delay_samples >= len(samples):
        return samples
    out = samples.copy()
    out[delay_samples:] += samples[:-delay_samples] * decay
    return out


def _apply_filters(
    samples: np.ndarray, sample_rate: int, low_hz: float, high_hz: float
) -> np.ndarray:
    if len(samples) == 0:
        return samples
    from scipy.signal import butter, filtfilt

    nyq = sample_rate / 2
    out = samples
    if low_hz > 0 and low_hz < nyq:
        b, a = butter(4, low_hz / nyq, btype="low")
        out = filtfilt(b, a, out)
    if high_hz > 0 and high_hz < nyq:
        b, a = butter(4, high_hz / nyq, btype="high")
        out = filtfilt(b, a, out)
    return out.astype(np.float32)


def _apply_distortion(samples: np.ndarray, amount: float) -> np.ndarray:
    if amount <= 0 or len(samples) == 0:
        return samples
    drive = 1 + amount * 10
    return (np.tanh(samples * drive) / np.tanh(drive)).astype(np.float32)


def _apply_gain(samples: np.ndarray, gain_db: float) -> np.ndarray:
    if gain_db == 0 or len(samples) == 0:
        return samples
    return samples * (10 ** (gain_db / 20))


def describe_tts_effects(
    *,
    noise_level: float = 0.0,
    background_tone_hz: float = 0.0,
    background_tone_level: float = 0.0,
    pitch_semitones: float = 0.0,
    speed_factor: float = 1.0,
    echo_delay_ms: float = 0.0,
    echo_decay: float = 0.0,
    distortion: float = 0.0,
    gain_db: float = 0.0,
    low_pass_hz: float = 0.0,
    high_pass_hz: float = 0.0,
    overlay_text: Optional[str] = None,
    overlay_level: float = 0.0,
) -> list[str]:
    """Return human-readable labels for non-default TTS post-processing settings."""
    applied: list[str] = []
    if overlay_text and overlay_text.strip() and overlay_level > 0:
        applied.append("overlay")
    if noise_level > 0:
        applied.append("noise")
    if background_tone_hz > 0 and background_tone_level > 0:
        applied.append("background_tone")
    if pitch_semitones != 0:
        applied.append("pitch")
    if speed_factor != 1.0:
        applied.append("speed")
    if echo_delay_ms > 0 and echo_decay > 0:
        applied.append("echo")
    if distortion > 0:
        applied.append("distortion")
    if gain_db != 0:
        applied.append("gain")
    if low_pass_hz > 0:
        applied.append("low_pass")
    if high_pass_hz > 0:
        applied.append("high_pass")
    return applied


def _tts_effects_active(
    *,
    noise_level: float = 0.0,
    background_tone_hz: float = 0.0,
    background_tone_level: float = 0.0,
    pitch_semitones: float = 0.0,
    speed_factor: float = 1.0,
    echo_delay_ms: float = 0.0,
    echo_decay: float = 0.0,
    distortion: float = 0.0,
    gain_db: float = 0.0,
    low_pass_hz: float = 0.0,
    high_pass_hz: float = 0.0,
    overlay_text: Optional[str] = None,
    overlay_level: float = 0.0,
) -> bool:
    if overlay_text and overlay_text.strip() and overlay_level > 0:
        return True
    return any(
        [
            noise_level > 0,
            background_tone_hz > 0 and background_tone_level > 0,
            pitch_semitones != 0,
            speed_factor != 1.0,
            echo_delay_ms > 0 and echo_decay > 0,
            distortion > 0,
            gain_db != 0,
            low_pass_hz > 0,
            high_pass_hz > 0,
        ]
    )


def apply_tts_effects(
    samples: np.ndarray,
    sample_rate: int,
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
    overlay_samples: Optional[np.ndarray] = None,
    overlay_level: float = 0.15,
) -> np.ndarray:
    """
    Apply post-processing to TTS audio for ASR/transcription red-team testing.
    Order: overlay mix, pitch, speed, tone, noise, echo, filters, distortion, gain.
    """
    out = samples.astype(np.float32, copy=True)
    if overlay_samples is not None:
        out = _mix_overlay(out, overlay_samples, overlay_level)
    out = _apply_pitch(out, pitch_semitones)
    out = _apply_speed(out, speed_factor)
    out = _apply_background_tone(out, sample_rate, background_tone_hz, background_tone_level)
    out = _apply_noise(out, noise_level, np.random.default_rng())
    out = _apply_echo(out, sample_rate, echo_delay_ms, echo_decay)
    out = _apply_filters(out, sample_rate, low_pass_hz, high_pass_hz)
    out = _apply_distortion(out, distortion)
    out = _apply_gain(out, gain_db)
    peak = float(np.max(np.abs(out))) if len(out) else 0.0
    if peak > 1.0:
        out = out / peak
    return out


def create_tts_wav(
    text: str,
    filename: Optional[str] = None,
    subdir: str = "audio",
    sample_rate: int = 44100,
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
    Create speech audio from text (TTS). Uses gTTS + pydub/ffmpeg for WAV output.
    Optional effects support overlay whispers, noise, tone masking, pitch/speed shifts,
    echo, filtering, and distortion for transcription/jailbreak testing.
    """
    if not text.strip():
        raise ValueError("TTS text cannot be empty")
    try:
        from gtts import gTTS  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "gTTS is not installed. Install project requirements: pip install gTTS pydub"
        ) from exc

    effects = _tts_effects_active(
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
    if effects and not shutil.which("ffmpeg"):
        raise RuntimeError("Audio effects require ffmpeg on PATH")

    base = get_output_dir()
    wav_path = resolve_output_path(filename, subdir, "wav", base)
    mp3_path = wav_path.with_suffix(".mp3")
    overlay_mp3_path = wav_path.with_name(wav_path.stem + "_overlay.mp3")

    try:
        _synthesize_gtts(text, mp3_path, lang=lang)
    except Exception as exc:
        raise RuntimeError(f"TTS synthesis failed: {exc}") from exc
    if not mp3_path.is_file() or mp3_path.stat().st_size == 0:
        raise RuntimeError("TTS synthesis produced no audio output")

    if not shutil.which("ffmpeg"):
        return mp3_path

    try:
        from pydub import AudioSegment  # noqa: F401
    except ImportError as exc:
        if effects:
            raise RuntimeError("Audio effects require pydub") from exc
        return mp3_path

    main_samples = _load_tts_samples(mp3_path, sample_rate)
    overlay_samples = None
    if overlay_text and overlay_text.strip() and overlay_level > 0:
        try:
            _synthesize_gtts(overlay_text.strip(), overlay_mp3_path, lang=lang)
            overlay_samples = _load_tts_samples(overlay_mp3_path, sample_rate)
        finally:
            overlay_mp3_path.unlink(missing_ok=True)

    processed = apply_tts_effects(
        main_samples,
        sample_rate,
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
        overlay_samples=overlay_samples,
        overlay_level=overlay_level,
    )
    seg = _float_to_segment(processed, sample_rate)
    seg.export(str(wav_path), format="wav")
    mp3_path.unlink(missing_ok=True)
    return wav_path
