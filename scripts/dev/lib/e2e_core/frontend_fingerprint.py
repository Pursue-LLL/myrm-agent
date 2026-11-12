"""Source fingerprint of what the Next.js dev server reads, the key of `frontend-warmth.json`.

[INPUT]
- git work tree of the frontend dir and its sibling `shared/` (POS: committed, uncommitted and untracked state of what the dev server reads)

[OUTPUT]
- `frontend_source_fingerprint()`: covers only what the dev server reads (frontend sources and configs, sibling `shared/`), so a commit elsewhere in the repository leaves it unchanged

[POS]
Dev infrastructure. Decides when `frontend-warmth.json` is stale; consumed by `frontend_epoch.py` and, through `python -c`, by `frontend-warmup.sh`.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

# What the dev server reads from the frontend directory itself.
_FRONTEND_INPUT_PATHS = (
    "src",
    "locales",
    "public",
    "next.config.ts",
    "next.config.js",
    "next.config.mjs",
    "package.json",
    "bun.lock",
    "postcss.config.mjs",
    "tailwind.config.ts",
    "tsconfig.base.json",
    ".env.local",
)


# The sibling directory it imports as `@shared/*` (the alias lives in tsconfig.base.json). Git rejects the pathspec
# when the frontend directory is the repository root, so it is only listed when the frontend has a parent in the repo.
_SHARED_INPUT_PATH = "../shared"


def frontend_source_fingerprint(frontend_dir: Path) -> str:
    """Hash the frontend inputs: their tree ids at HEAD, the uncommitted diff and the untracked files under them."""
    try:
        probe = subprocess.run(
            [
                "git",
                "-C",
                str(frontend_dir),
                "rev-parse",
                "--is-inside-work-tree",
                "--show-prefix",
            ],
            check=False,
            capture_output=True,
            timeout=2,
        )
        inside, _, prefix = probe.stdout.decode().partition("\n")
        if probe.returncode != 0 or inside != "true":
            return ""
    except (OSError, subprocess.TimeoutExpired):
        return ""
    tracked_paths = (
        (*_FRONTEND_INPUT_PATHS, _SHARED_INPUT_PATH)
        if prefix.strip()
        else _FRONTEND_INPUT_PATHS
    )
    try:
        diff = subprocess.run(
            [
                "git",
                "-C",
                str(frontend_dir),
                "diff",
                "--no-ext-diff",
                "--binary",
                "HEAD",
                "--",
                *tracked_paths,
            ],
            check=False,
            capture_output=True,
            timeout=10,
        ).stdout
        untracked = subprocess.run(
            [
                "git",
                "-C",
                str(frontend_dir),
                "ls-files",
                "--others",
                "--exclude-standard",
                "--",
                *tracked_paths,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.splitlines()
        # Tree ids of the input paths only: a commit elsewhere in the repository must not look like a source change.
        committed = subprocess.run(
            ["git", "-C", str(frontend_dir), "ls-tree", "HEAD", "--", *tracked_paths],
            check=False,
            capture_output=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""

    digest = hashlib.sha256(committed + diff)
    for relative_path in sorted(item for item in untracked if item):
        path = frontend_dir / relative_path
        try:
            digest.update(relative_path.encode("utf-8"))
            digest.update(path.read_bytes())
        except OSError:
            return ""
    # tsconfig is hashed without its include/exclude globs: isolated Next builds rewrite them, and that
    # noise must not look like a source change (it would invalidate the client warmth for nothing).
    stable_tsconfig = _stable_tsconfig_fingerprint(frontend_dir)
    if stable_tsconfig:
        digest.update(b"tsconfig:")
        digest.update(stable_tsconfig.encode("utf-8"))
    return digest.hexdigest()[:16]


def _stable_tsconfig_fingerprint(frontend_dir: Path) -> str:
    """Hash the tsconfig without the include/exclude globs Next rewrites during isolated builds."""
    path = frontend_dir / "tsconfig.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    stable = {key: value for key, value in payload.items() if key not in {"include", "exclude"}}
    try:
        return hashlib.sha256(json.dumps(stable, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    except (TypeError, ValueError):
        return ""
