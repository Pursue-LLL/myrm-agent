"""[INPUT]
- .common (POS: shared constants and error type)

[OUTPUT]
- _ensure_symlink, ensure_standalone_assets, patch_nextjs_rewrites

[POS]
Frontend launcher: standalone symlink/asset materialisation and Next.js rewrite patching.
"""

from __future__ import annotations

import os
from pathlib import Path

from .common import (
    _FRONTEND_DIR,
    _STANDALONE_DIR,
    FrontendEnvironmentError,
    _resolve_standalone_dir,
    logger,
)


def _ensure_symlink(link: Path, target: Path) -> None:
    """Create a relative symlink, replacing broken ones.

    Raises:
        FrontendEnvironmentError: If the symlink cannot be created.
    """
    try:
        if link.is_symlink():
            if link.resolve() == target.resolve():
                return
            link.unlink()
        elif link.exists():
            return

        rel_target = os.path.relpath(target, link.parent)
        link.symlink_to(rel_target)
    except OSError as exc:
        raise FrontendEnvironmentError(f"Cannot create symlink {link} -> {target}: {exc}") from exc


def ensure_standalone_assets() -> None:
    """Symlink static assets and public files into the standalone directory.

    Next.js standalone output only contains server.js; CSS/JS chunks and
    public files must be linked separately.
    """
    standalone_dir = _resolve_standalone_dir()
    static_src = _FRONTEND_DIR / ".next" / "static"
    static_dst = standalone_dir / ".next" / "static"
    if static_src.is_dir():
        static_dst.parent.mkdir(parents=True, exist_ok=True)
        _ensure_symlink(static_dst, static_src)
        logger.info("[Frontend] Static assets linked: %s", static_dst)

    public_src = _FRONTEND_DIR / "public"
    public_dst = standalone_dir / "public"
    if public_src.is_dir():
        _ensure_symlink(public_dst, public_src)
        logger.info("[Frontend] Public files linked: %s", public_dst)
    else:
        logger.info("[Frontend] No public/ directory found, skipping")


def patch_nextjs_rewrites(api_host: str, api_port: int) -> None:
    """Patch the hardcoded API port in Next.js build artifacts."""
    standalone_dir = _resolve_standalone_dir()
    target_files = [
        standalone_dir / ".next" / "routes-manifest.json",
        standalone_dir / ".next" / "required-server-files.json",
        standalone_dir / "server.js",
    ]
    if standalone_dir != _STANDALONE_DIR:
        for extra in [
            _STANDALONE_DIR / ".next" / "routes-manifest.json",
            _STANDALONE_DIR / ".next" / "required-server-files.json",
            _STANDALONE_DIR / "server.js",
        ]:
            if extra.exists() and extra not in target_files:
                target_files.append(extra)

    for file_path in target_files:
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
                import re

                # Match both 127.0.0.1 and localhost (Next rewrites may bake in either).
                new_content = re.sub(
                    r"http://(?:127\.0\.0\.1|localhost):\d+",
                    f"http://{api_host}:{api_port}",
                    content,
                )
                if new_content != content:
                    file_path.write_text(new_content, encoding="utf-8")
                    logger.info(
                        "[Frontend] Patched %s with API port %d",
                        file_path.name,
                        api_port,
                    )
            except Exception as e:
                logger.warning("[Frontend] Failed to patch %s: %s", file_path.name, e)
