"""Wiki vault export for portable backup (Export-only #10).

[INPUT]
myrm_agent_harness.toolkits.wiki.core.structure::WikiStructure (POS: Wiki file system abstraction layer)

[OUTPUT]
build_wiki_export_zip: Build streaming ZIP bytes for concepts + OKF index/log + manifest.json

[POS]
Server-side wiki vault export packager for Settings portability download.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

EXPORT_MANIFEST_VERSION = 1


def _vault_relative(path: Path, vault_base: Path) -> str:
    return str(path.relative_to(vault_base)).replace("\\", "/")


def build_wiki_export_zip(structure: WikiStructure, agent_id: str | None = None) -> io.BytesIO:
    """Build a portable zip of concepts, OKF index/log, and manifest.json."""
    vault_base = structure.base_dir
    memory_file = io.BytesIO()
    included_paths: list[str] = []

    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        if structure.concepts_dir.is_dir():
            for md_file in sorted(structure.concepts_dir.rglob("*.md")):
                if not md_file.is_file() or WikiStructure._is_directory_sidecar(md_file):
                    continue
                arcname = _vault_relative(md_file, vault_base)
                zf.write(md_file, arcname)
                included_paths.append(arcname)

        for rel_name in ("wiki/index.md", "wiki/log.md"):
            file_path = vault_base / rel_name
            if file_path.is_file():
                zf.write(file_path, rel_name)
                included_paths.append(rel_name)

        manifest = {
            "version": EXPORT_MANIFEST_VERSION,
            "exported_at": datetime.now(UTC).isoformat(),
            "agent_id": agent_id,
            "files": included_paths,
            "concepts_count": len([path for path in included_paths if path.startswith("wiki/concepts/")]),
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

    memory_file.seek(0)
    return memory_file
