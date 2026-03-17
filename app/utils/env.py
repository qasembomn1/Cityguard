from __future__ import annotations

import os
import sys
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:8800"


def _strip_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _append_parent_env_files(candidates: list[Path], start: Path) -> None:
    current = start.resolve()
    while True:
        candidates.append(current / ".env")
        if current.parent == current:
            return
        current = current.parent


def _candidate_env_files() -> list[Path]:
    candidates: list[Path] = []

    override = (os.getenv("CITYGUARD_ENV_FILE") or "").strip()
    if override:
        candidates.append(Path(override).expanduser())

    executable = (sys.executable or "").strip()
    if executable:
        _append_parent_env_files(candidates, Path(executable).resolve().parent)

    argv0 = (sys.argv[0] or "").strip()
    if argv0:
        _append_parent_env_files(candidates, Path(argv0).resolve().parent)

    _append_parent_env_files(candidates, Path.cwd())

    project_root = Path(__file__).resolve().parents[2]
    _append_parent_env_files(candidates, project_root)

    unique_candidates: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = str(candidate)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_candidates.append(candidate)
    return unique_candidates


def load_runtime_env() -> Path | None:
    for env_file in _candidate_env_files():
        if not env_file.is_file():
            continue

        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            name = key.strip()
            if not name or name in os.environ:
                continue

            os.environ[name] = _strip_quotes(value)

        return env_file

    return None


def get_env_value(*names: str, default: str = "") -> str:
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value

    load_runtime_env()

    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value

    return default


def resolve_http_base_url(value: str | None = None, default: str = DEFAULT_BASE_URL) -> str:
    raw = str(value or "").strip()
    if not raw:
        raw = get_env_value("Base_URL", "BASE_URL", "base_url", default=default)

    normalized = raw.strip().rstrip("/")
    if normalized.startswith(("http://", "https://")):
        return normalized
    return f"http://{normalized}"
