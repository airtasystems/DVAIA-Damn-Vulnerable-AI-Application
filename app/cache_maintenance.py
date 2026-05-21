"""Clear runtime and filesystem caches from Settings panel."""
import shutil
from pathlib import Path
from typing import List

_SKIP_DIR_NAMES = {".git", "venv", ".venv", "node_modules", ".cache"}


def clear_pycache(root: Path | None = None) -> List[str]:
    """Remove __pycache__ directories under the project root (excludes venv/.git)."""
    base = (root or Path(__file__).resolve().parent.parent).resolve()
    removed: List[str] = []
    for path in base.rglob("__pycache__"):
        if not path.is_dir():
            continue
        if _SKIP_DIR_NAMES.intersection(path.parts):
            continue
        try:
            shutil.rmtree(path)
            removed.append(str(path.relative_to(base)))
        except OSError:
            pass
    return removed
