"""Auto-format observer — runs code formatters after AI file edits.

Integrated with CLI Tool Discovery to detect available formatters at startup.
Uses a timeout-guarded subprocess call with graceful failure handling.

A formatter that loads code the workspace declares (prettier runs ``prettier.config.js`` and local plugins, ``mix
format`` runs ``.formatter.exs``) runs only in a workspace the user trusts: the agent's sandbox can write those files
without an approval, so formatting after the write would run them on the host.

[INPUT]
- observers.base::FileOperationObserver (POS: Provides FileOperationObserver.)
- utils.vault_scope::is_vault_markdown_path (POS: Scope detection for vault write guards — no server imports.)
- toolkits.code_execution.executors.base::get_executor (POS: Code executor base classes.)
- core.security.path::container_relative (POS: Aggregation facade for the path security domain)
- agent.security.workspace_trust.provider::resolve_workspace_trust_level (POS: Harness-side indirection so agent runs resolve trust without importing server code.)
- agent.security.workspace_trust.gate::blocks_workspace_side_channels (POS: Pure predicate layer of the workspace_trust gate; no persistence and no server calls.)

[OUTPUT]
- FormatterRule: Maps file extensions to a formatter command and says whether the formatter loads code the workspace declares.
- FormatObserver: Runs the matching code formatter after every file create/modify; one that loads workspace code is skipped unless the workspace is trusted.

[POS]
Auto-format observer — runs code formatters after AI file edits, those that load workspace code only in trusted workspaces.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.core.security.path import container_relative

from .base import FileOperationObserver

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor

logger = logging.getLogger(__name__)

FORMAT_TIMEOUT_SECONDS: float = 10.0


@dataclass(frozen=True, slots=True)
class FormatterRule:
    """Maps file extensions to a formatter command.

    cmd_template uses {path} as placeholder for the target file. ``loads_workspace_code`` marks a formatter that
    runs code the workspace declares (config programs, plugins) and so needs a trusted workspace; a formatter that
    reads only declarative config stays unmarked.
    """

    extensions: frozenset[str]
    bin_name: str
    args_template: tuple[str, ...]
    loads_workspace_code: bool = False

    def build_cmd(self, file_path: str) -> list[str]:
        return [self.bin_name] + [a.replace("{path}", file_path) for a in self.args_template]


CONFIG_FILE_TO_FORMATTER: dict[str, str] = {
    "ruff.toml": "ruff",
    ".ruff.toml": "ruff",
    "pyproject.toml": "ruff",
    ".prettierrc": "prettier",
    ".prettierrc.json": "prettier",
    ".prettierrc.yml": "prettier",
    ".prettierrc.yaml": "prettier",
    "prettier.config.js": "prettier",
    "prettier.config.cjs": "prettier",
    ".editorconfig": "",
}

FORMATTER_RULES: tuple[FormatterRule, ...] = (
    FormatterRule(
        extensions=frozenset({".py", ".pyi"}), bin_name="ruff", args_template=("format", "--quiet", "{path}")
    ),
    FormatterRule(extensions=frozenset({".py", ".pyi"}), bin_name="black", args_template=("--quiet", "{path}")),
    FormatterRule(extensions=frozenset({".go"}), bin_name="gofmt", args_template=("-w", "{path}")),
    FormatterRule(extensions=frozenset({".rs"}), bin_name="rustfmt", args_template=("--edition", "2021", "{path}")),
    FormatterRule(
        extensions=frozenset(
            {
                ".js",
                ".jsx",
                ".ts",
                ".tsx",
                ".css",
                ".scss",
                ".json",
                ".md",
                ".mdx",
                ".html",
                ".vue",
                ".svelte",
                ".yaml",
                ".yml",
            }
        ),
        bin_name="prettier",
        args_template=("--write", "--log-level", "silent", "{path}"),
        loads_workspace_code=True,
    ),
    FormatterRule(extensions=frozenset({".dart"}), bin_name="dart", args_template=("format", "{path}")),
    FormatterRule(
        extensions=frozenset({".swift"}), bin_name="swift-format", args_template=("format", "--in-place", "{path}")
    ),
    FormatterRule(
        extensions=frozenset({".java", ".kt", ".kts"}),
        bin_name="google-java-format",
        args_template=("--replace", "{path}"),
    ),
    FormatterRule(extensions=frozenset({".sh", ".bash"}), bin_name="shfmt", args_template=("-w", "{path}")),
    FormatterRule(extensions=frozenset({".tf", ".tfvars"}), bin_name="terraform", args_template=("fmt", "{path}")),
    FormatterRule(
        extensions=frozenset({".c", ".cpp", ".cc", ".h", ".hpp"}),
        bin_name="clang-format",
        args_template=("-i", "{path}"),
    ),
    FormatterRule(extensions=frozenset({".zig"}), bin_name="zig", args_template=("fmt", "{path}")),
    FormatterRule(
        extensions=frozenset({".ex", ".exs"}),
        bin_name="mix",
        args_template=("format", "{path}"),
        loads_workspace_code=True,
    ),
)


@dataclass
class _FormatterCache:
    """Caches which formatters are available (extension -> command).

    Supports project-level config detection: if a project has ruff.toml,
    prefer ruff over black for Python files.
    """

    _ext_map: dict[str, FormatterRule] = field(default_factory=dict)
    _available: dict[str, FormatterRule] = field(default_factory=dict)
    _unavailable: set[str] = field(default_factory=set)
    _initialized: bool = False

    async def resolve(self, ext: str, file_path: str = "") -> FormatterRule | None:
        if not self._initialized:
            await self._init()

        if file_path:
            project_rule = self._detect_project_formatter(ext, file_path)
            if project_rule is not None:
                return project_rule

        return self._ext_map.get(ext)

    def _detect_project_formatter(self, ext: str, file_path: str) -> FormatterRule | None:
        """Walk up directories to find project-level formatter config."""
        directory = Path(file_path).parent
        for _ in range(10):
            for config_name, formatter_bin in CONFIG_FILE_TO_FORMATTER.items():
                if (directory / config_name).is_file() and formatter_bin:
                    rule = self._available.get(formatter_bin)
                    if rule is not None and ext in rule.extensions:
                        return rule
            parent = directory.parent
            if parent == directory:
                break
            directory = parent
        return None

    async def _init(self) -> None:
        self._initialized = True
        for rule in FORMATTER_RULES:
            if rule.bin_name in self._unavailable:
                continue
            path = await asyncio.to_thread(_which, rule.bin_name)
            if path is None:
                self._unavailable.add(rule.bin_name)
                continue
            self._available[rule.bin_name] = rule
            for ext in rule.extensions:
                if ext not in self._ext_map:
                    self._ext_map[ext] = rule


def _which(name: str) -> str | None:
    """Synchronous which lookup."""
    import shutil

    return shutil.which(name)


def _workspace_is_trusted(executor: CodeExecutor | None) -> bool:
    """Whether the user trusts the folder the executor works in; with no executor there is no folder to ask about.

    The level is looked up by the workspace root in the process-wide trust registry, not read from the run's
    ContextVar: LangGraph runs a tool body in a task that may not see the variable bound when the run started, and a
    trusted folder would then count as restricted and silently stop being formatted.
    """
    if executor is None:
        return False

    from myrm_agent_harness.agent.security.workspace_trust.gate import blocks_workspace_side_channels
    from myrm_agent_harness.agent.security.workspace_trust.provider import resolve_workspace_trust_level

    return not blocks_workspace_side_channels(resolve_workspace_trust_level(executor.workspace_path))


_cache = _FormatterCache()


class FormatObserver(FileOperationObserver):
    """Runs the matching code formatter after every file create/modify.

    Failures are silently logged — formatting is best-effort and must never
    block or break the file write pipeline.
    """

    async def on_file_created(self, path: str, content: str) -> None:
        await self._try_format(path)

    async def on_file_modified(self, path: str, old_content: str, new_content: str) -> None:
        await self._try_format(path)

    async def on_file_viewed(self, path: str) -> None:
        pass

    async def _try_format(self, path: str) -> None:
        ext = Path(path).suffix.lower()
        if not ext:
            return

        from ..utils.vault_scope import is_vault_markdown_path

        if is_vault_markdown_path(path):
            logger.debug("Skipping formatter for vault markdown note: %s", path)
            return

        rule = await _cache.resolve(ext, path)
        if rule is None:
            return

        from myrm_agent_harness.toolkits.code_execution.executors.base import get_executor

        executor = get_executor()

        if rule.loads_workspace_code and not _workspace_is_trusted(executor):
            logger.debug(
                "Skipping %s for %s: it loads code the workspace declares and the workspace is not trusted",
                rule.bin_name,
                path,
            )
            return

        # If we have an executor, resolve the path to the workspace
        actual_path = path
        cwd = os.path.dirname(path) or None
        if executor:
            from pathlib import Path as _Path

            wp = _Path(executor.workspace_path).resolve()
            clean = container_relative(path) or path
            if not _Path(clean).is_absolute():
                actual_path = str((wp / clean).resolve())
                cwd = str(wp)

        if is_vault_markdown_path(actual_path):
            logger.debug("Skipping formatter for vault markdown note: %s", actual_path)
            return

        cmd = rule.build_cmd(actual_path)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=FORMAT_TIMEOUT_SECONDS)
            if proc.returncode != 0:
                logger.info(
                    "Formatter %s exited %d for %s: %s",
                    rule.bin_name,
                    proc.returncode,
                    path,
                    (stderr or b"").decode(errors="replace")[:200],
                )
            else:
                logger.debug("Formatted %s with %s", path, rule.bin_name)
        except TimeoutError:
            logger.warning("Formatter %s timed out for %s", rule.bin_name, path)
        except OSError as e:
            logger.info("Formatter %s unavailable: %s", rule.bin_name, e)
