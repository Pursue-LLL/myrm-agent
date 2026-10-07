"""Workspace environment probe extracting runtime profiles and architecture baselines.

[POS]
app/services/memory/world_model/probe.py
Safely probes local filesystem markers (pyproject.toml, package.json, _ARCH.md)
to produce a structured ProjectEnvironmentSnapshot with strict budget caps and error fallback.

[INPUT]
- pathlib.Path
- json
- re
- myrm_agent_harness.toolkits.memory: (ProjectEnvironmentSnapshot, RuntimeEnvironmentInfo)

[OUTPUT]
- ProjectEnvironmentProbe: Static utility inspecting workspace directories safely.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    ProjectEnvironmentSnapshot,
    RuntimeEnvironmentInfo,
)


class ProjectEnvironmentProbe:
    """Safe, non-blocking environment detector probing workspace configuration files."""

    @classmethod
    def probe_workspace(cls, workspace_path: str | Path) -> ProjectEnvironmentSnapshot:
        """Inspect workspace directory and synthesize a ProjectEnvironmentSnapshot."""
        root = Path(workspace_path).resolve()
        workspace_name = root.name or "workspace"

        runtimes: list[RuntimeEnvironmentInfo] = []
        markers: list[str] = []

        if not root.exists() or not root.is_dir():
            return ProjectEnvironmentSnapshot(
                workspace_name=workspace_name,
                runtimes=[],
                config_markers=[],
                detected_at=time.time(),
            )

        detected_name: str | None = None

        # 1. Probe Python environment
        pyproject_file = root / "pyproject.toml"
        if pyproject_file.exists():
            markers.append("pyproject.toml")
            py_info, py_name = cls._probe_python(pyproject_file)
            if py_info:
                runtimes.append(py_info)
            if py_name:
                detected_name = py_name

        # 2. Probe Node / JS environment
        pkg_file = root / "package.json"
        if pkg_file.exists():
            markers.append("package.json")
            node_info, node_name = cls._probe_node(pkg_file)
            if node_info:
                runtimes.append(node_info)
            if node_name and not detected_name:
                detected_name = node_name

        # 3. Check Architecture doc markers
        if (root / "_ARCH.md").exists():
            markers.append("_ARCH.md")
        elif (root / "ARCHITECTURE.md").exists():
            markers.append("ARCHITECTURE.md")

        workspace_name = detected_name or root.name or "workspace"

        return ProjectEnvironmentSnapshot(
            workspace_name=workspace_name,
            runtimes=runtimes,
            config_markers=markers,
            detected_at=time.time(),
        )

    @classmethod
    def _probe_python(cls, file_path: Path) -> tuple[RuntimeEnvironmentInfo | None, str | None]:
        """Extract Python version, top dependencies, and name from pyproject.toml."""
        try:
            content = file_path.read_text(encoding="utf-8")[:16384]
        except Exception:
            return None, None

        # Detect project name
        name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
        proj_name = name_match.group(1) if name_match else None

        # Detect python version requirement
        version_match = re.search(r'python\s*=\s*["\']([^"\']+)["\']', content)
        py_version = version_match.group(1) if version_match else ">=3.11"

        # Detect key dependencies
        key_deps: list[str] = []
        for dep in ["fastapi", "pydantic", "pytest", "uvicorn", "qdrant-client", "langchain"]:
            if dep in content:
                key_deps.append(dep)

        return RuntimeEnvironmentInfo(
            name="Python",
            version=py_version,
            package_manager="uv/poetry",
            key_dependencies=key_deps,
        ), proj_name

    @classmethod
    def _probe_node(cls, file_path: Path) -> tuple[RuntimeEnvironmentInfo | None, str | None]:
        """Extract Node tooling, top dependencies, and name from package.json."""
        try:
            content = file_path.read_text(encoding="utf-8")[:16384]
            data = json.loads(content)
        except Exception:
            return None, None

        proj_name: str | None = data.get("name") if isinstance(data, dict) else None

        deps_dict: dict[str, str] = {}
        if isinstance(data.get("dependencies"), dict):
            deps_dict.update(data["dependencies"])
        if isinstance(data.get("devDependencies"), dict):
            deps_dict.update(data["devDependencies"])

        key_deps: list[str] = []
        for dep in ["react", "vue", "next", "vite", "tailwindcss", "typescript"]:
            if dep in deps_dict:
                key_deps.append(dep)

        node_version = ">=20.0"
        if isinstance(data.get("engines"), dict) and "node" in data["engines"]:
            node_version = str(data["engines"]["node"])

        return RuntimeEnvironmentInfo(
            name="Node.js",
            version=node_version,
            package_manager="pnpm/npm",
            key_dependencies=key_deps,
        ), proj_name

