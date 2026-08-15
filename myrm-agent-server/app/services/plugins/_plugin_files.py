"""Plugin bundled-file persistence and removal (business layer).

When a plugin ships bundled stdio MCP servers — a ``./``-relative command or
``${PLUGIN_ROOT}`` / ``${PLUGIN_DATA}`` placeholders in env/cwd/args — the
imported server can only launch once the plugin's files are on disk. This
module owns that persistence:

- ``persist_plugin_files``: writes a security-filtered file tree (parser
  output) under ``{data_dir}/plugins/{plugin_name}/`` and returns the
  ``(plugin_root, data_root)`` pair to embed into the MCP server's
  ``extra_params``.
- ``remove_plugin_files``: deletes a plugin's root + data directories on
  uninstall.
- ``plugin_installed_dir`` / ``plugin_data_dir``: canonical path accessors.

Security: archive entries were already vetted by ``safe_extract_zip``
(traversal / symlink / executable-binary / forbidden paths). Persistence
re-checks path containment anyway (defense in depth) so a malformed key can
never escape the plugin root.

[INPUT]
- myrm_agent_harness.agent.plugins.models::PluginMcpServer (POS: framework
  parser output dataclasses.)
- myrm_agent_harness.backends.skills.scanning.zip_extract::safe_extract_zip
  (POS: framework secure ZIP extraction — the upstream file filter.)

[OUTPUT]
- persist_plugin_files / remove_plugin_files / plugin_installed_dir /
  plugin_data_dir: plugin file lifecycle for bundled stdio MCP servers.
- server_needs_bundled_files: decision helper (needs files when the server
  references the plugin package).

[POS]
Business-layer plugin file lifecycle. Parsing stays in the framework; the
business layer decides what to persist, where, and when to delete it.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from myrm_agent_harness.agent.plugins.mcp_config import has_placeholders
from myrm_agent_harness.agent.plugins.models import PluginMcpServer

logger = logging.getLogger(__name__)

# Matches the naming constraints enforced by manifest._NAME_RE (lowercase
# alnum/dot/dash, no leading/trailing dash, no "--"/".."). Only such names may
# appear in a filesystem path.
_SAFE_PLUGIN_NAME_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789.-"


def _plugins_root(data_dir: Path) -> Path:
    return data_dir / "plugins"


def plugin_installed_dir(data_dir: Path, plugin_name: str) -> Path:
    """Return the canonical read-only root for a plugin's bundled files."""
    return _plugins_root(data_dir) / plugin_name


def plugin_data_dir(data_dir: Path, plugin_name: str) -> Path:
    """Return the canonical writable data root for a plugin (``PLUGIN_DATA``)."""
    return _plugins_root(data_dir) / f"{plugin_name}_data"


def plugin_dir_exists(data_dir: Path, plugin_name: str) -> bool:
    """True when the plugin's bundled-file directory exists on disk."""
    return plugin_installed_dir(data_dir, plugin_name).is_dir()


def is_safe_plugin_name(name: str) -> bool:
    """Validate a plugin name for use as a filesystem directory segment."""
    if not name or len(name) > 64:
        return False
    if not all(c in _SAFE_PLUGIN_NAME_CHARS for c in name):
        return False
    if ".." in name or "--" in name:
        return False
    return name[0].isalnum() and name[-1].isalnum()


def server_needs_bundled_files(server: PluginMcpServer) -> bool:
    """True when a stdio server references the plugin package at launch.

    Triggers: a ``./``-relative command (in-package executable, §7.2.1) or a
    ``${PLUGIN_ROOT}`` / ``${PLUGIN_DATA}`` placeholder in cwd/args/env.
    Remote servers never need bundled files.
    """
    if server.server_type != "stdio":
        return False
    if server.command and server.command.startswith("./"):
        return True
    values: list[str | None] = [server.cwd]
    if server.args:
        values.extend(server.args)
    values.extend(server.raw_env.values())
    return has_placeholders(*values)


def persist_plugin_files(
    plugin_name: str,
    files: dict[str, bytes],
    data_dir: Path,
) -> tuple[str, str] | None:
    """Persist a plugin's bundled files to disk.

    Writes ``files`` (parser output, already security-filtered) into
    ``{data_dir}/plugins/{plugin_name}/`` and creates the ``{name}_data``
    directory for ``PLUGIN_DATA``. Returns ``(plugin_root, data_root)`` as
    absolute paths, or ``None`` when the plugin needs no files (nothing to
    write) or the name is unsafe (refused).

    Raises:
        ValueError: plugin_name fails the filesystem-safety constraints.
    """
    if not files:
        return None
    if not is_safe_plugin_name(plugin_name):
        raise ValueError(f"Unsafe plugin name for filesystem persistence: {plugin_name!r}")

    root_dir = plugin_installed_dir(data_dir, plugin_name)
    data_root_dir = plugin_data_dir(data_dir, plugin_name)
    root_dir.mkdir(parents=True, exist_ok=True)
    data_root_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for rel_path, content in files.items():
        target = _contained_path(root_dir, rel_path)
        if target is None:
            logger.warning(
                "Skipping unsafe plugin file path '%s' during persistence", rel_path
            )
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            written += 1
        except OSError as exc:
            logger.error("Failed to persist plugin file '%s': %s", rel_path, exc)
            raise RuntimeError("Failed to persist the plugin's bundled files.") from exc

    logger.info(
        "Persisted %d bundled file(s) for plugin '%s' -> %s",
        written,
        plugin_name,
        root_dir,
    )
    return str(root_dir), str(data_root_dir)


def _contained_path(root_dir: Path, rel_path: str) -> Path | None:
    """Resolve ``rel_path`` under ``root_dir``, rejecting any escape.

    Returns None for absolute paths, drive prefixes, and ``..`` traversal.
    """
    normalized = rel_path.replace("\\", "/")
    if normalized.startswith("/"):
        return None
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized or normalized.startswith("../") or "/../" in normalized or normalized == "..":
        return None
    candidate = (root_dir / normalized).resolve()
    root_resolved = root_dir.resolve()
    return candidate if candidate.is_relative_to(root_resolved) else None


def remove_plugin_files(plugin_name: str, data_dir: Path) -> bool:
    """Remove a plugin's root + data directories. Returns True if anything was removed."""
    removed = False
    for directory in (
        plugin_installed_dir(data_dir, plugin_name),
        plugin_data_dir(data_dir, plugin_name),
    ):
        if directory.exists():
            try:
                shutil.rmtree(directory)
                removed = True
            except OSError as exc:
                logger.warning("Failed to remove plugin directory %s: %s", directory, exc)
    if removed:
        logger.info("Removed plugin files for '%s'", plugin_name)
    return removed
