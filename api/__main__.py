"""
Entry point for the red-team API. Loads .env then runs the Flask app.
  python -m api
"""
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    _env = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(_env)

if __name__ == "__main__":
    from app.startup import apply_startup_reset

    apply_startup_reset()
    from api.server import run_app

    run_app()
