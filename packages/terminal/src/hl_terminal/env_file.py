from __future__ import annotations

import re
from pathlib import Path

_ENV_VAR_RE = re.compile(r"^(\s*#?\s*)([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def find_project_root(start: Path | None = None) -> Path:
    """Return the nearest directory containing pyproject.toml."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    return current


def resolve_project_path(path: Path, *, start: Path | None = None) -> Path:
    """Resolve a project-relative path from the repo root."""
    if path.is_absolute():
        return path
    return (find_project_root(start) / path).resolve()


def upsert_env_vars(path: Path, values: dict[str, str]) -> list[str]:
    """Create or update KEY=value lines in a dotenv file."""
    path = resolve_project_path(path)
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    else:
        example = path.with_name(".env.example")
        if example.exists():
            lines = example.read_text(encoding="utf-8").splitlines()
        else:
            lines = []

    updated: list[str] = []
    remaining = dict(values)

    for index, line in enumerate(lines):
        match = _ENV_VAR_RE.match(line)
        if match is None:
            continue
        key = match.group(2)
        if key not in remaining:
            continue
        lines[index] = f"{key}={remaining.pop(key)}"
        updated.append(key)

    for key, value in remaining.items():
        lines.append(f"{key}={value}")
        updated.append(key)

    trailing_newline = "\n" if lines else ""
    path.write_text("\n".join(lines) + trailing_newline, encoding="utf-8")
    return updated
