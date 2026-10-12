#!/usr/bin/env python3
"""Cross-check memory API route prefixes against frontend /memory/* references.

Usage (from myrm-agent-server):
  uv run python scripts/memory_router_fe_inventory.py

Exit code 0 always; prints orphan mounts (no FE first-segment match) for human review.
Conservative: crud and sub-router modules may appear as false orphans — verify manually.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE_ROOT = ROOT.parent / "myrm-agent-frontend" / "src"
API_ROOT = ROOT / "app" / "api" / "memory"

FE_PATH_PAT = re.compile(r"(?:['\"`]|)\s*(?:/api/v1)?(/memory/[a-zA-Z0-9_/${}-]+)")
FE_API_PAT = re.compile(r"['\"`](/api/memory/[a-zA-Z0-9_/-]+)")
PREFIX_RE = re.compile(r'APIRouter\(\s*prefix\s*=\s*["\']([^"\']+)')
ROUTE_RE = re.compile(r'@router\.(?:get|post|put|patch|delete)\(\s*["\']([^"\']+)')
INCLUDE_RE = re.compile(r"include_router\(([\w.]+)")


def collect_fe_prefixes() -> set[str]:
    paths: set[str] = set()
    for p in FE_ROOT.rglob("*"):
        if p.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for m in FE_PATH_PAT.finditer(text):
            raw = m.group(1)
            if "${" in raw:
                raw = raw.split("${",0)[0]
            paths.add(raw.split("?")[0].rstrip("/"))
        for m in FE_API_PAT.finditer(text):
            paths.add(m.group(1).split("?")[0].rstrip("/"))
    prefixes: set[str] = set()
    for path in paths:
        norm = path.replace("/api/v1", "")
        if norm.startswith("/api/memory/"):
            norm = "/memory/" + norm[len("/api/memory/") :]
        if not norm.startswith("/memory/"):
            continue
        rest = norm[len("/memory/") :]
        if rest:
            prefixes.add(rest.split("/")[0])
    return prefixes


def module_route_segments(py_file: Path) -> set[str]:
    text = py_file.read_text(encoding="utf-8", errors="ignore")
    segs: set[str] = set()
    mp = PREFIX_RE.search(text)
    if mp:
        segs.add(mp.group(1).strip("/").split("/")[0])
    for m in ROUTE_RE.finditer(text):
        r = m.group(1)
        part = r.strip("/").split("/")[0] if r.startswith("/") else r.split("/")[0]
        if part and part not in {"{", ""}:
            segs.add(part)
    return segs


def find_module_file(base: str) -> Path | None:  # noqa: UP007 — py3.9 compat in dev shells
    for rel in (f"{base}.py", f"operations/{base}.py", "follow_ups/__init__.py"):
        p = API_ROOT / rel
        if p.is_file():
            return p
    if base.endswith("_router"):
        stem = base[: -len("_router")]
        for rel in (f"{stem}_router.py", f"{stem}.py"):
            p = API_ROOT / rel
            if p.is_file():
                return p
    hits = list(API_ROOT.rglob(f"{base}.py"))
    return hits[0] if hits else None


def main() -> None:
    fe_prefixes = collect_fe_prefixes()
    router_py = (API_ROOT / "router.py").read_text(encoding="utf-8")
    mounted: list[str] = []
    for line in router_py.splitlines():
        m = INCLUDE_RE.search(line)
        if m:
            mounted.append(m.group(1).split(".")[0])

    orphans: list[tuple[str, str, set[str]]] = []
    matched = 0
    for base in mounted:
        mod = find_module_file(base)
        if mod is None:
            orphans.append((base, "FILE_NOT_FOUND", set()))
            continue
        rel = mod.relative_to(API_ROOT).as_posix()
        segs = module_route_segments(mod)
        if not segs:
            orphans.append((base, rel, {"NO_ROUTES"}))
            continue
        if any(s in fe_prefixes for s in segs):
            matched += 1
        else:
            orphans.append((base, rel, segs))

    print(f"FE first-segment prefixes: {len(fe_prefixes)}")
    print(f"Mounted modules with FE match: {matched}")
    print(f"Candidate orphans (verify manually): {len(orphans)}")
    for base, rel, segs in sorted(orphans, key=lambda x: x[0]):
        print(f"  {base}\t{rel}\t{sorted(segs)}")


if __name__ == "__main__":
    main()
