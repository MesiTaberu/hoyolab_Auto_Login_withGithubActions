import os
from pathlib import Path


def _find_env_file() -> str:
    # Prefer ".env" in current dir, then next to script, then repo/src/.env.
    here = Path(__file__).resolve().parent
    repo = here.parent
    candidates = [
        Path.cwd() / ".env",
        here / ".env",
        repo / "src" / ".env",
        repo / ".env",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return str(Path.cwd() / ".env")


def load_env() -> None:
    path = _find_env_file()
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if not k:
                continue
            os.environ.setdefault(k, v.strip())


def mask(v: str) -> str:
    if not v:
        return "(empty)"
    if len(v) <= 8:
        return "*" * len(v)
    return f"{v[:4]}...{v[-4:]}"


def pause_exit(msg: str = "Press Enter to exit...") -> None:
    # When double-clicking an .exe, the console closes immediately.
    try:
        input(msg)
    except (EOFError, KeyboardInterrupt):
        pass
