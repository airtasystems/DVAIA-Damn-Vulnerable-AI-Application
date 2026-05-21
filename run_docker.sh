#!/bin/bash
# DVAIA - Damn Vulnerable AI Application
# Docker Compose wrapper: Ollama + Qdrant + Flask (or cloud-only without Ollama)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

GEMINI_ONLY_FLAG=false
OPENAI_ONLY_FLAG=false
LOCAL_FLAG=false
SKIP_PROMPT=false

for arg in "$@"; do
  case "$arg" in
    --gemini-only|--gemini)
      GEMINI_ONLY_FLAG=true
      ;;
    --openai-only|--openai)
      OPENAI_ONLY_FLAG=true
      ;;
    --local|--ollama)
      LOCAL_FLAG=true
      ;;
    --skip-prompt|--yes|-y)
      SKIP_PROMPT=true
      ;;
    -h|--help)
      echo "Usage: $0 [OPTIONS] [docker compose args...]"
      echo ""
      echo "Interactive setup runs when no mode is set in .env and stdin is a TTY."
      echo "Use ./run_docker.sh instead of 'docker compose up' directly."
      echo ""
      echo "Options:"
      echo "  (default)       Prompt for local vs cloud, or use .env (GEMINI_ONLY / OPENAI_ONLY)"
      echo "  --local         Local Ollama stack (skip prompt)"
      echo "  --gemini-only   Cloud Gemini — no Ollama, no model downloads"
      echo "  --openai-only   Cloud OpenAI — no Ollama, no model downloads"
      echo "  --skip-prompt   Use .env flags only; default to local if unset"
      echo "  -y, --yes       Same as --skip-prompt"
      echo ""
      echo "Cloud modes require API keys in .env. See .env.example."
      echo "Set DVAIA_SKIP_MODE_PROMPT=1 to always skip the interactive prompt."
      exit 0
      ;;
  esac
done

is_truthy() {
  case "$(echo "$1" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes) return 0 ;;
    *) return 1 ;;
  esac
}

ensure_env_file() {
  if [ -f .env ]; then
    return 0
  fi
  echo ""
  echo "No .env file found."
  if [ -f .env.example ]; then
    read -r -p "Copy .env.example to .env now? [Y/n]: " copy_env
    copy_env="${copy_env:-Y}"
    if [[ "$copy_env" =~ ^[Yy]$ ]]; then
      cp .env.example .env
      echo "Created .env — edit it to add API keys before using cloud mode."
      return 0
    fi
  fi
  echo "Warning: continuing without .env (docker-compose defaults only)."
  return 0
}

print_local_info() {
  cat <<'EOF'

  LOCAL (Ollama) — full stack with on-device LLMs

  What you need:
    • Copy .env.example to .env (optional; no API keys required)
    • Docker with Compose v2
    • Disk: ~9–10 GB for Ollama models on first start
    • RAM: 8–16 GB recommended for CPU inference

  Models pulled automatically on first start:
    • llama3.2          (~2 GB)   — chat / main panels
    • nomic-embed-text  (~275 MB) — RAG embeddings
    • qwen3:0.6b        (~400 MB) — Agentic / chain-of-thought
    • qwen2.5vl:7b      (~6 GB)   — Document Injection vision

  First startup can take several minutes while models download.
  After startup, use Settings → Backend → Local (Ollama) in the UI.
  Whisper (audio) and OCR still run locally in the app container.
EOF
}

print_gemini_info() {
  cat <<'EOF'

  CLOUD (Gemini) — no Ollama container, no local LLM downloads

  What you need in .env:
    • GOOGLE_API_KEY          — https://aistudio.google.com/apikey
    • GEMINI_ONLY=true
    • EMBEDDING_BACKEND=gemini
    • GEMINI_CHAT_MODEL, GEMINI_VISION_MODEL, GEMINI_AGENTIC_MODEL
    • EMBEDDING_MODEL_GEMINI=text-embedding-004  (RAG)

  Optional: DEFAULT_MODEL=gemini:… to match chat model.
  After startup, use Settings → Backend → Cloud (Gemini).
  Re-index RAG documents (collection rag_chunks_gemini vs rag_chunks).
  Whisper/OCR still run locally in the app container.
EOF
}

print_openai_info() {
  cat <<'EOF'

  CLOUD (OpenAI) — no Ollama container, no local LLM downloads

  What you need in .env:
    • OPENAI_API_KEY          — https://platform.openai.com/api-keys
    • OPENAI_ONLY=true
    • EMBEDDING_BACKEND=openai
    • OPENAI_CHAT_MODEL, OPENAI_VISION_MODEL, OPENAI_AGENTIC_MODEL
    • EMBEDDING_MODEL_OPENAI=text-embedding-3-small  (RAG)

  Optional: DEFAULT_MODEL=openai:gpt-4o-mini
  After startup, use Settings → Backend → Cloud (OpenAI).
  Re-index RAG documents (collection rag_chunks_openai vs rag_chunks).
  Whisper/OCR still run locally in the app container.
EOF
}

prompt_for_mode() {
  echo ""
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║           DVAIA — choose LLM backend for Docker              ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
  echo ""
  echo "  1) Local (Ollama)     — download and run models in Docker"
  echo "  2) Cloud (Gemini)     — Google API; skip Ollama entirely"
  echo "  3) Cloud (OpenAI)     — OpenAI API; skip Ollama entirely"
  echo ""
  echo "  h) Show requirements for a option before choosing"
  echo "  q) Quit"
  echo ""

  while true; do
    read -r -p "Enter choice [1/2/3] (default: 1): " choice
    choice="${choice:-1}"
    case "$choice" in
      1)
        print_local_info
        read -r -p "Start with local Ollama? [Y/n]: " confirm
        confirm="${confirm:-Y}"
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
          LOCAL_FLAG=true
          return 0
        fi
        ;;
      2)
        print_gemini_info
        read -r -p "Start with Cloud (Gemini)? [Y/n]: " confirm
        confirm="${confirm:-Y}"
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
          GEMINI_ONLY_FLAG=true
          return 0
        fi
        ;;
      3)
        print_openai_info
        read -r -p "Start with Cloud (OpenAI)? [Y/n]: " confirm
        confirm="${confirm:-Y}"
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
          OPENAI_ONLY_FLAG=true
          return 0
        fi
        ;;
      h|H)
        echo ""
        echo "Which option do you want details for?"
        echo "  1 = Local   2 = Gemini   3 = OpenAI"
        read -r -p "Choice: " help_choice
        case "$help_choice" in
          1) print_local_info ;;
          2) print_gemini_info ;;
          3) print_openai_info ;;
          *) echo "Unknown option." ;;
        esac
        echo ""
        ;;
      q|Q)
        echo "Aborted."
        exit 0
        ;;
      *)
        echo "Invalid choice. Enter 1, 2, 3, h, or q."
        ;;
    esac
  done
}

# Load .env when present (may be created interactively below)
load_env() {
  if [ -f .env ]; then
    set -a
    # shellcheck source=/dev/null
    source .env 2>/dev/null || true
    set +a
  fi
}

MODE_EXPLICIT=false
if [ "$GEMINI_ONLY_FLAG" = true ] || [ "$OPENAI_ONLY_FLAG" = true ] || [ "$LOCAL_FLAG" = true ]; then
  MODE_EXPLICIT=true
fi

if [ "$SKIP_PROMPT" = false ] && [ "$MODE_EXPLICIT" = false ] && is_truthy "${DVAIA_SKIP_MODE_PROMPT:-false}"; then
  SKIP_PROMPT=true
fi

# Interactive mode selection (TTY only, no flags, no .env cloud-only flags yet)
if [ "$SKIP_PROMPT" = false ] && [ "$MODE_EXPLICIT" = false ]; then
  if [ -t 0 ]; then
    ensure_env_file
    load_env
    if ! is_truthy "${GEMINI_ONLY:-false}" && ! is_truthy "${OPENAI_ONLY:-false}"; then
      prompt_for_mode
      MODE_EXPLICIT=true
    fi
  fi
fi

load_env

GEMINI_ONLY_MODE=false
OPENAI_ONLY_MODE=false
if is_truthy "${GEMINI_ONLY:-false}" || [ "$GEMINI_ONLY_FLAG" = true ]; then
  GEMINI_ONLY_MODE=true
fi
if is_truthy "${OPENAI_ONLY:-false}" || [ "$OPENAI_ONLY_FLAG" = true ]; then
  OPENAI_ONLY_MODE=true
fi

if [ "$LOCAL_FLAG" = true ]; then
  GEMINI_ONLY_MODE=false
  OPENAI_ONLY_MODE=false
fi

if [ "$GEMINI_ONLY_MODE" = true ] && [ "$OPENAI_ONLY_MODE" = true ]; then
  echo "Error: cannot use both Gemini-only and OpenAI-only mode. Set only one of GEMINI_ONLY or OPENAI_ONLY."
  exit 1
fi

echo "Clearing Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

COMPOSE_ARGS=(up --build)

if [ "$OPENAI_ONLY_MODE" = true ]; then
  if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "Error: OPENAI_ONLY mode requires OPENAI_API_KEY in .env"
    print_openai_info
    exit 1
  fi
  export OPENAI_ONLY=true
  export GEMINI_ONLY=false
  export EMBEDDING_BACKEND="${EMBEDDING_BACKEND:-openai}"
  export OLLAMA_HOST=""
  echo ""
  echo "OpenAI-only mode: starting Qdrant + DVAIA (skipping Ollama — no local LLM downloads)"
  echo "  RAG embeddings: ${EMBEDDING_BACKEND}"
  echo "  Whisper/OCR still run locally in the app container for audio/image tests"
  echo ""
elif [ "$GEMINI_ONLY_MODE" = true ]; then
  if [ -z "${GOOGLE_API_KEY:-}" ] && [ -z "${GEMINI_API_KEY:-}" ]; then
    echo "Error: GEMINI_ONLY mode requires GOOGLE_API_KEY or GEMINI_API_KEY in .env"
    print_gemini_info
    exit 1
  fi
  export GEMINI_ONLY=true
  export OPENAI_ONLY=false
  export EMBEDDING_BACKEND="${EMBEDDING_BACKEND:-gemini}"
  export OLLAMA_HOST=""
  echo ""
  echo "Gemini-only mode: starting Qdrant + DVAIA (skipping Ollama — no local LLM downloads)"
  echo "  RAG embeddings: ${EMBEDDING_BACKEND}"
  echo "  Whisper/OCR still run locally in the app container for audio/image tests"
  echo ""
else
  export OLLAMA_HOST="${OLLAMA_HOST:-http://ollama:11434}"
  export GEMINI_ONLY=false
  export OPENAI_ONLY=false
  COMPOSE_ARGS=(--profile ollama "${COMPOSE_ARGS[@]}")
  echo ""
  echo "Local mode: building and running DVAIA with Ollama + Qdrant..."
  echo "First startup downloads llama3.2, nomic-embed-text, qwen3:0.6b, qwen2.5vl:7b (may take several minutes)"
  echo "Requirements: ~9–10 GB disk, 8–16 GB RAM recommended. See: ./run_docker.sh --help"
  echo ""
fi

docker compose "${COMPOSE_ARGS[@]}"
