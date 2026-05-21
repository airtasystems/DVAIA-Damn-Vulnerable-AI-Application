# DVAIA - Damn Vulnerable AI Application
# Intentionally vulnerable LLM web application for security testing education (Ollama local models only)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000 \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

# Install Python dependencies (no system deps for Gemini-only; add later for local models)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Fonts for payload image generation; tesseract-ocr for Document Injection image uploads;
# ffmpeg for TTS audio conversion (gTTS MP3 -> WAV via pydub)
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core tesseract-ocr ffmpeg libzbar0 \
    && rm -rf /var/lib/apt/lists/*

# Pre-download Whisper model so first audio transcription is fast (~150MB for base)
RUN mkdir -p /app/.cache/huggingface \
    && python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"

# Copy application code
COPY . .

# Non-root user for better security
RUN useradd -m agentuser && chown -R agentuser:agentuser /app
USER agentuser

EXPOSE 5000

# Run with Gunicorn; --reload picks up volume-mounted code changes in Docker dev
ENTRYPOINT ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--reload", "--timeout", "120", "api.server:app"]
