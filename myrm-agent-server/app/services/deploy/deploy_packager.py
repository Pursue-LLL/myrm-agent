"""Collect artifact files for Vercel deployment.

[INPUT]
- pathlib.Path (POS: artifact vault object paths)

[OUTPUT]
- DeployFile: dataclass for a single deployable file
- collect_deploy_files: read vault file/directory + HTML-relative static assets
- validate_deploy_payload: ensure deployable HTML entry exists

[POS]
Server business layer — packages vault/workspace artifacts for third-party hosting.
"""

from __future__ import annotations

import base64
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

TEXT_EXTENSIONS = frozenset(
    {
        ".html",
        ".htm",
        ".css",
        ".js",
        ".mjs",
        ".cjs",
        ".json",
        ".txt",
        ".md",
        ".svg",
        ".xml",
        ".wasm",
    }
)

ALLOWED_STATIC_EXTENSIONS = frozenset(
    {
        ".html",
        ".htm",
        ".css",
        ".js",
        ".mjs",
        ".cjs",
        ".json",
        ".txt",
        ".md",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".svg",
        ".ico",
        ".bmp",
        ".avif",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
        ".wasm",
        ".mp3",
        ".mp4",
        ".webm",
        ".ogg",
    }
)

EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".next",
        ".nuxt",
        ".svelte-kit",
        ".vite",
        ".cache",
        "coverage",
        ".myrm",
    }
)

SENSITIVE_DIRECTORY_NAMES = frozenset({".cowork-temp", ".openclaw", "memory"})

EXCLUDED_FILE_NAMES = frozenset(
    {
        ".DS_Store",
        "Thumbs.db",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
    }
)

HTML_ATTR_REF_PATTERN = re.compile(
    r"""(?:href|src|data|poster)\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
CSS_IMPORT_PATTERN = re.compile(
    r"""@import\s+(?:url\(\s*)?["']?([^"')]+)["']?\s*\)?""",
    re.IGNORECASE,
)
CSS_URL_PATTERN = re.compile(r"""url\(\s*["']?([^"')]+)["']?\s*\)""", re.IGNORECASE)
JS_IMPORT_PATTERN = re.compile(
    r"""(?:import\s+(?:[^"']*?\s+from\s+)?|export\s+[^"']*?\s+from\s+|import\(\s*)["']([^"']+)["']""",
    re.IGNORECASE,
)

MAX_SINGLE_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_DEPENDENCY_FILES = 500

SCANNABLE_SUFFIXES = frozenset({".html", ".htm", ".css", ".js", ".mjs", ".cjs", ".svg"})


@dataclass(frozen=True)
class DeployFile:
    path: str
    content: str
    encoding: Literal["utf-8", "base64"] = "utf-8"


def _is_remote_reference(value: str) -> bool:
    trimmed = value.strip()
    return bool(
        re.match(r"^(?:[a-z][a-z0-9+.-]*:|//|#|data:|mailto:|tel:|javascript:)", trimmed, re.I)
    )


def _strip_reference_query(value: str) -> str:
    return value.split("?", 1)[0].split("#", 1)[0]


def _is_allowed_static_file(path: Path) -> bool:
    return path.suffix.lower() in ALLOWED_STATIC_EXTENSIONS


def _is_blocked_path(allowed_root: Path, file_path: Path) -> bool:
    try:
        relative = file_path.resolve().relative_to(allowed_root.resolve())
    except ValueError:
        return True
    parts = relative.parts
    if not parts:
        return False
    if any(part in EXCLUDED_DIRECTORY_NAMES or part in SENSITIVE_DIRECTORY_NAMES for part in parts):
        return True
    return file_path.name in EXCLUDED_FILE_NAMES or file_path.name.startswith(".env")


def _resolve_reference(allowed_root: Path, from_file: Path, reference: str) -> Path | None:
    trimmed = reference.strip()
    if not trimmed or _is_remote_reference(trimmed):
        return None

    clean = _strip_reference_query(trimmed)
    if not clean:
        return None

    base_dir = allowed_root if clean.startswith("/") else from_file.parent
    candidate = (base_dir / clean.lstrip("/")).resolve()
    try:
        candidate.relative_to(allowed_root.resolve())
    except ValueError:
        return None
    return candidate


def _scan_html_references(content: str) -> list[str]:
    refs = list(HTML_ATTR_REF_PATTERN.findall(content))
    for style_block in re.findall(r"<style[^>]*>(.*?)</style>", content, re.I | re.S):
        refs.extend(CSS_IMPORT_PATTERN.findall(style_block))
        refs.extend(CSS_URL_PATTERN.findall(style_block))
    for inline_style in re.findall(r"""style\s*=\s*["']([^"']+)["']""", content, re.I):
        refs.extend(CSS_IMPORT_PATTERN.findall(inline_style))
        refs.extend(CSS_URL_PATTERN.findall(inline_style))
    return refs


def _scan_file_references(file_path: Path, content: str) -> list[str]:
    suffix = file_path.suffix.lower()
    if suffix in {".html", ".htm", ".svg"}:
        return _scan_html_references(content)
    if suffix == ".css":
        refs = CSS_IMPORT_PATTERN.findall(content)
        refs.extend(CSS_URL_PATTERN.findall(content))
        return refs
    if suffix in {".js", ".mjs", ".cjs"}:
        return JS_IMPORT_PATTERN.findall(content)
    return []


def _discover_dependency_files(entry_path: Path, allowed_root: Path) -> set[Path]:
    """BFS static asset discovery from an HTML/CSS/JS entry within allowed_root."""
    if not entry_path.is_file():
        return set()

    discovered: set[Path] = set()
    pending: deque[Path] = deque([entry_path.resolve()])
    visited: set[Path] = set()

    while pending and len(discovered) < MAX_DEPENDENCY_FILES:
        current = pending.popleft()
        if current in visited:
            continue
        visited.add(current)

        if _is_blocked_path(allowed_root, current) or not _is_allowed_static_file(current):
            continue
        if not current.is_file():
            continue

        discovered.add(current)
        if current.suffix.lower() not in SCANNABLE_SUFFIXES:
            continue

        try:
            content = current.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        for ref in _scan_file_references(current, content):
            resolved = _resolve_reference(allowed_root, current, ref)
            if resolved and resolved not in visited:
                pending.append(resolved)

    return discovered


def _normalize_entry_name(path: Path, obj_path: Path) -> str:
    if path.is_file() and obj_path.is_file():
        if path.suffix.lower() in {".html", ".htm"}:
            return "index.html"
        return path.name
    return path.relative_to(obj_path).as_posix()


def _deploy_name_for_asset(path: Path, allowed_root: Path) -> str:
    relative = path.resolve().relative_to(allowed_root.resolve()).as_posix()
    if relative.lower().endswith((".html", ".htm")) and "/" not in relative:
        return "index.html"
    return relative


def _read_file_entry(file_path: Path, entry_name: str, total_bytes: int) -> tuple[DeployFile, int]:
    raw = file_path.read_bytes()
    next_total = total_bytes + len(raw)
    if len(raw) > MAX_SINGLE_FILE_BYTES:
        raise ValueError(f"File too large for deploy: {entry_name} ({len(raw)} bytes)")
    if next_total > MAX_TOTAL_BYTES:
        raise ValueError(f"Total deploy payload exceeds limit ({MAX_TOTAL_BYTES} bytes)")

    if file_path.suffix.lower() in TEXT_EXTENSIONS:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            encoded = base64.b64encode(raw).decode("ascii")
            return DeployFile(path=entry_name, content=encoded, encoding="base64"), next_total
        return DeployFile(path=entry_name, content=text, encoding="utf-8"), next_total

    encoded = base64.b64encode(raw).decode("ascii")
    return DeployFile(path=entry_name, content=encoded, encoding="base64"), next_total


def _merge_disk_assets(
    files: dict[str, DeployFile],
    total_bytes: int,
    *,
    allowed_root: Path,
    entry_hint: Path | None,
) -> tuple[dict[str, DeployFile], int]:
    if not allowed_root.is_dir() or entry_hint is None:
        return files, total_bytes

    entry = entry_hint if entry_hint.is_file() else None
    if entry is None:
        for candidate in (allowed_root / "index.html", allowed_root / "index.htm"):
            if candidate.is_file():
                entry = candidate
                break
    if entry is None and entry_hint.suffix.lower() in {".html", ".htm"}:
        entry = allowed_root / entry_hint.name
    if entry is None or not entry.is_file():
        return files, total_bytes

    for disk_path in sorted(_discover_dependency_files(entry, allowed_root.resolve())):
        deploy_name = _deploy_name_for_asset(disk_path, allowed_root.resolve())
        if deploy_name in files:
            continue
        deploy_file, total_bytes = _read_file_entry(disk_path, deploy_name, total_bytes)
        files[deploy_name] = deploy_file

    return files, total_bytes


def collect_deploy_files(
    obj_path: Path,
    *,
    asset_root: Path | None = None,
    entry_name_hint: str | None = None,
) -> dict[str, DeployFile]:
    """Read a vault file or directory into a deployable file map."""
    if not obj_path.exists():
        raise FileNotFoundError(f"Missing artifact path: {obj_path}")

    files: dict[str, DeployFile] = {}
    total_bytes = 0
    allowed_root = asset_root.resolve() if asset_root and asset_root.exists() else None
    entry_hint = (allowed_root / entry_name_hint) if allowed_root and entry_name_hint else None

    if obj_path.is_file():
        entry_name = _normalize_entry_name(obj_path, obj_path)
        deploy_file, total_bytes = _read_file_entry(obj_path, entry_name, total_bytes)
        files[entry_name] = deploy_file
        if allowed_root is not None:
            hint = entry_hint or obj_path
            files, total_bytes = _merge_disk_assets(
                files, total_bytes, allowed_root=allowed_root, entry_hint=hint
            )
        return files

    if obj_path.is_dir():
        root = obj_path.resolve()
        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue
            if not _is_allowed_static_file(file_path):
                continue
            relative = file_path.relative_to(root)
            if any(
                part in EXCLUDED_DIRECTORY_NAMES or part in SENSITIVE_DIRECTORY_NAMES
                for part in relative.parts[:-1]
            ):
                continue
            entry_name = _normalize_entry_name(file_path, obj_path)
            deploy_file, total_bytes = _read_file_entry(file_path, entry_name, total_bytes)
            files[entry_name] = deploy_file
        if not files:
            raise ValueError("Artifact directory contains no deployable files")
        return files

    raise ValueError("Invalid artifact physical format")


def validate_deploy_payload(files: dict[str, DeployFile]) -> None:
    """Ensure payload is deployable static content."""
    if not files:
        raise ValueError("No files to deploy")
    if "index.html" in files:
        return
    html_entries = [name for name in files if name.lower().endswith((".html", ".htm"))]
    if len(html_entries) == 1 and len(files) <= 2:
        return
    raise ValueError("Deploy payload must include index.html or a single HTML entry")
