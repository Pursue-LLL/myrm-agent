"""Virtual environment management service.

Manages shared virtual environment creation, initialization, and pip command rewriting.

[INPUT]
- toolkits.code_execution.config::ExecutionConfig (POS: Code execution configuration layer. Defines execution modes, network policies, and runtime settings for the Agent-in-Sandbox architecture.)
- core.security.redact::command_preview (POS: masked, cut command for a log line)
- infra.data_dir::resolve_data_dir (POS: Single entry point for the Myrm state root; harness and server code derive every state path from it)

[OUTPUT]
- VenvManager: Shared virtual environment manager (single-flight lazy create, background pip bootstrap, pip rewrite, crash-safe discard).
- mentions_pip: True when a command or snippet names pip, so it must wait for the venv's pip.

[POS]
Virtual environment management service.
"""

import asyncio
import logging
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

from myrm_agent_harness.core.security.redact import command_preview
from myrm_agent_harness.infra.data_dir import resolve_data_dir
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.common.subprocess_guard import (
    guarded_communicate,
)

logger = logging.getLogger(__name__)

_PIP_NAMED = re.compile(r"\bpip[0-9.]*\b|\bensurepip\b")
_CREATE_TIMEOUT_SECONDS = 120
_PIP_BOOTSTRAP_TIMEOUT_SECONDS = 120


def mentions_pip(text: str) -> bool:
    """True when a command or snippet names pip: ``pip``, ``pip3``, ``python -m pip``, ``uv pip``, ``.../bin/pip``, ``ensurepip``.

    Such text needs the shared venv's pip to exist; any other text runs as soon as the interpreter does.
    """
    return _PIP_NAMED.search(text) is not None


def _get_default_venv_path() -> Path:
    """Resolve the default shared virtual environment path.

    Lives at ``<state root>/venvs``; the state root is MYRM_DATA_DIR, default ``~/.myrm``.
    """
    return resolve_data_dir().resolve() / "venvs"


DEFAULT_SHARED_VENV_PATH = _get_default_venv_path()


class VenvManager:
    """Shared virtual environment manager.

    Isolates user-installed packages from the system Python. Lazily initializes
    the venv on first use and falls back to system Python on failure.

    The venv is created without pip (a fraction of a second) and pip installs in the background, so a Python run
    starts at once instead of waiting seconds for the bootstrap. A command or snippet that names pip waits for it.
    """

    def __init__(self, config: ExecutionConfig):
        self.config = config
        self._python_executable: str | None = None
        self._venv_initialized = False
        self._resolve_lock = asyncio.Lock()
        self._pip_bootstrap: asyncio.Task[None] | None = None

    def get_venv_path(self) -> Path:
        """Return the shared virtual environment path."""
        if self.config.local.shared_venv_path:
            return Path(self.config.local.shared_venv_path)
        return DEFAULT_SHARED_VENV_PATH

    def command_whitelist_paths(self, extra_readonly_paths: tuple[str, ...]) -> list[Path] | None:
        """Merge venv whitelist with per-command read-only grading mounts.

        ``extra_readonly_paths`` lets post-episode graders (e.g. eval ``test_suite``)
        reach grading assets mounted outside the agent workspace. Agent-runtime bash
        passes an empty tuple, so those assets stay blocked.
        """
        venv_path = self.get_venv_path()
        paths = [venv_path] if venv_path.exists() else []
        paths.extend(Path(p) for p in extra_readonly_paths)
        return paths or None

    def discard(self) -> bool:
        """Remove the shared venv so the next use rebuilds it from an empty interpreter.

        Only call this while no process is using the venv: a live process keeps its cached
        interpreter path. A pip bootstrap still running for the removed venv is cancelled.

        Returns:
            True if a venv existed and was removed.
        """
        self._python_executable = None
        self._venv_initialized = False
        if self._pip_bootstrap is not None:
            self._pip_bootstrap.cancel()
            self._pip_bootstrap = None

        venv_path = self.get_venv_path()
        if not self._delete(venv_path):
            return False

        logger.warning(" [VenvManager] Discarded shared venv: %s", venv_path)
        return True

    @staticmethod
    def _delete(venv_path: Path) -> bool:
        """Delete the venv directory; True if one existed.

        The directory is renamed before it is deleted. The rename is atomic, so a crash
        mid-delete cannot leave a half-deleted venv that still looks usable; the trash
        left by such a crash is cleared on the next call.
        """
        trash = venv_path.with_name(f"{venv_path.name}.discarding")
        shutil.rmtree(trash, ignore_errors=True)
        if not venv_path.exists():
            return False

        venv_path.rename(trash)
        shutil.rmtree(trash, ignore_errors=True)
        return True

    async def get_python_executable(self) -> str:
        """Return the Python executable path, creating the venv if needed.

        Callers that arrive while the venv is being created wait for that one creation, so a background
        warm-up and the first Python run never build it twice.
        """
        if self._python_executable and self._venv_initialized:
            return self._python_executable

        async with self._resolve_lock:
            if self._python_executable and self._venv_initialized:
                return self._python_executable
            return await self._resolve_python_executable()

    async def _resolve_python_executable(self) -> str:
        venv_path = self.get_venv_path()
        python_path = venv_path / "bin" / "python"

        if python_path.exists():
            self._python_executable = str(python_path)
            self._venv_initialized = True
            logger.info(f" [VenvManager] Using shared venv: {venv_path}")
            return self._python_executable

        if not self.config.local.auto_create_venv:
            self._python_executable = sys.executable
            self._venv_initialized = True
            logger.warning(" [VenvManager] Using system Python (no shared venv configured)")
            return self._python_executable

        return await self._create_venv(venv_path)

    async def _create_venv(self, venv_path: Path) -> str:
        """Create a shared virtual environment without pip and start installing pip in the background.

        Falls back to system Python if creation fails.
        """
        logger.warning(f" [VenvManager] Creating shared venv: {venv_path}")
        try:
            venv_path.parent.mkdir(parents=True, exist_ok=True)

            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "venv",
                "--without-pip",
                str(venv_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _stdout, stderr = await guarded_communicate(process, _CREATE_TIMEOUT_SECONDS, label="venv create")

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                logger.error(f" [VenvManager] Failed to create venv: {error_msg}")
                self._python_executable = sys.executable
                self._venv_initialized = True
                return self._python_executable

            python_path = venv_path / "bin" / "python"
            self._python_executable = str(python_path)
            self._venv_initialized = True
            self._pip_bootstrap = asyncio.create_task(self._bootstrap_pip(venv_path, python_path))
            logger.warning(f" [VenvManager] Shared venv created: {venv_path}")
            return self._python_executable
        except Exception as exc:
            logger.error(f" [VenvManager] Failed to create venv: {exc}")
            self._python_executable = sys.executable
            self._venv_initialized = True
            return self._python_executable

    async def _bootstrap_pip(self, venv_path: Path, python_path: Path) -> None:
        """Install pip into the new venv with ``ensurepip``, the step ``python -m venv`` runs when it is not told to skip pip.

        It runs the way ``venv`` runs it: from the venv's own interpreter, with ``VIRTUAL_ENV`` set and the parent's
        ``PYTHONHOME`` and ``PYTHONPATH`` removed so that neither can shadow the venv. Its output goes to a file, not to
        pipes: pip prints while it installs, and a pipe nobody reads any more kills it, which would leave the venv without
        pip whenever this process exits first. When it fails, the venv is dropped and Python falls back to the system
        interpreter, as it does when the creation itself fails.
        """
        started = time.monotonic()
        env = {**os.environ, "VIRTUAL_ENV": str(venv_path)}
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        with tempfile.TemporaryFile() as log:
            try:
                process = await asyncio.create_subprocess_exec(
                    str(python_path),
                    "-m",
                    "ensurepip",
                    "--upgrade",
                    "--default-pip",
                    stdout=log,
                    stderr=log,
                    env=env,
                    cwd=str(venv_path),
                )
                await guarded_communicate(process, _PIP_BOOTSTRAP_TIMEOUT_SECONDS, label="venv pip bootstrap")
            except Exception as exc:
                reason = str(exc)
            else:
                if process.returncode == 0:
                    logger.info(
                        f" [VenvManager] Shared venv pip installed in {time.monotonic() - started:.1f}s: {venv_path}"
                    )
                    return
                log.seek(0)
                reason = log.read().decode("utf-8", errors="replace")

        if (venv_path / "bin" / "pip").exists():
            # Another process finished the same venv; its pip is as good as the one this bootstrap failed to install.
            return
        logger.error(f" [VenvManager] Failed to install pip into {venv_path}: {reason}")
        self._python_executable = sys.executable
        self._venv_initialized = True
        await asyncio.to_thread(self._delete, venv_path)

    async def ensure_pip_ready_for(self, text: str) -> None:
        """Wait until the shared venv has pip when ``text`` names pip; any other text returns at once.

        PATH puts the shared venv's ``bin`` first, so a command that names pip must not start before the venv has one:
        it would reach a pip outside the venv. A venv that is not created yet is created first. The bootstrap keeps
        running when the caller is cancelled.
        """
        if not mentions_pip(text):
            return
        await self.get_python_executable()
        bootstrap = self._pip_bootstrap
        if bootstrap is not None and not bootstrap.done():
            await asyncio.wait((bootstrap,))

    async def rewrite_pip_command(self, command: str) -> str:
        """Rewrite pip install commands to use the shared venv's pip.

        A command that names pip anywhere waits for the venv's pip first, so it never reaches a pip outside the venv.

        Args:
            command: Original command string.

        Returns:
            Rewritten command string.
        """
        await self.ensure_pip_ready_for(command)

        stripped = command.strip()
        if not (stripped.startswith("pip install") or stripped.startswith("pip3 install")):
            return command

        venv_path = self.get_venv_path()
        pip_path = venv_path / "bin" / "pip"

        if not pip_path.exists():
            return command

        if stripped.startswith("pip3 install"):
            new_command = command.replace("pip3 install", f"{pip_path} install", 1)
        else:
            new_command = command.replace("pip install", f"{pip_path} install", 1)

        logger.warning(f" [VenvManager] Rewrote pip command: {command_preview(new_command, 100)}")
        return new_command
