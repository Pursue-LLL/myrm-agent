"""Virtual environment management service.

Manages shared virtual environment creation, initialization, and pip command rewriting.

[INPUT]
- toolkits.code_execution.config::ExecutionConfig (POS: Code execution configuration layer. Defines execution modes, network policies, and runtime settings for the Agent-in-Sandbox architecture.)
- core.security.redact::command_preview (POS: masked, cut command for a log line)
- infra.data_dir::resolve_data_dir (POS: Single entry point for the Myrm state root; harness and server code derive every state path from it)

[OUTPUT]
- VenvManager: Shared virtual environment manager (single-flight lazy create, pip installed in the background, pip rewrite, crash-safe discard).
- mentions_pip: True when a command or snippet names pip, so it must wait for the venv's pip.

[POS]
Virtual environment management service.
"""

import asyncio
import logging
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import BinaryIO

from myrm_agent_harness.core.security.redact import command_preview
from myrm_agent_harness.infra.data_dir import resolve_data_dir
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.common.subprocess_guard import (
    guarded_communicate,
)

logger = logging.getLogger(__name__)

_PIP_NAMED = re.compile(r"\bpip[0-9.]*\b|\bensurepip\b")
_BUILD_TIMEOUT_SECONDS = 120
_LINK_POLL_SECONDS = 0.01
_INTERPRETER_NAMES = ("python", "python3", f"python3.{sys.version_info.minor}")


def mentions_pip(text: str) -> bool:
    """True when a command or snippet names pip: ``pip``, ``pip3``, ``python -m pip``, ``uv pip``, ``.../bin/pip``, ``ensurepip``.

    Such text needs the shared venv's pip to exist; any other text runs as soon as the interpreter does.
    """
    return _PIP_NAMED.search(text) is not None


def _interpreter_linked(venv_path: Path) -> bool:
    """True once ``python -m venv`` has linked the interpreter under every name it uses, which it does before it installs pip.

    A copied interpreter is not a link and may be half written, so it counts only when the command has ended.
    """
    bin_dir = venv_path / "bin"
    return (bin_dir / "python").is_symlink() and all((bin_dir / name).exists() for name in _INTERPRETER_NAMES)


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

    ``python -m venv`` links the interpreter within milliseconds and then spends seconds installing pip. A Python run
    needs only the link, so it starts as soon as the link exists while the command finishes in the background; a command
    or snippet that names pip waits for the command to end.
    """

    def __init__(self, config: ExecutionConfig):
        self.config = config
        self._python_executable: str | None = None
        self._venv_initialized = False
        self._resolve_lock = asyncio.Lock()
        self._build: asyncio.Task[bool] | None = None

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
        interpreter path. A build still running for the removed venv is cancelled.

        Returns:
            True if a venv existed and was removed.
        """
        self._python_executable = None
        self._venv_initialized = False
        if self._build is not None:
            self._build.cancel()
            self._build = None

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
        warm-up and the first Python run never build it twice. Creation ends when the interpreter is
        linked; pip may still be installing (see ``ensure_pip_ready_for``).
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
        """Run ``python -m venv`` and return the venv's interpreter as soon as the command has linked it.

        The stock command links the interpreter and then installs pip, nearly all of its time. A Python run needs only the link, so
        the command finishes in the background (``_finish_build``) and ``ensure_pip_ready_for`` holds back whatever needs pip. The
        command does both steps itself, so whatever becomes of this process the venv ends as complete as a synchronous build leaves
        it; its output goes to a file because a pipe nobody reads any more kills it. Falls back to system Python if it fails.
        """
        logger.warning(f" [VenvManager] Creating shared venv: {venv_path}")
        started = time.monotonic()
        try:
            process, log = await self._start_venv_command(venv_path)
        except Exception as exc:
            logger.error(f" [VenvManager] Failed to create venv: {exc}")
            return self._fall_back_to_system_python()

        build = self._build = asyncio.create_task(self._finish_build(process, log, venv_path, started))
        while process.returncode is None and not _interpreter_linked(venv_path):
            await asyncio.sleep(_LINK_POLL_SECONDS)
        if process.returncode is None and _interpreter_linked(venv_path):
            return self._use_venv(venv_path)

        # Over already (copied interpreters count only then), failed, or out of time: nothing is left to run in the background.
        await asyncio.wait((build,))
        if build.result():
            return self._use_venv(venv_path)
        return self._fall_back_to_system_python()

    @staticmethod
    async def _start_venv_command(venv_path: Path) -> tuple[asyncio.subprocess.Process, BinaryIO]:
        """Start ``python -m venv`` writing to an unlinked file next to the venv, which the caller must close (``_finish_build`` does).

        The file sits in the state directory the venv is created in, which has to be writable anyway; the system temp
        directory may be read-only or tiny, and the build must not depend on it.
        """
        venv_path.parent.mkdir(parents=True, exist_ok=True)
        log = tempfile.TemporaryFile(dir=venv_path.parent)  # noqa: SIM115  outlives this call: the child writes to it until the build ends
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "venv", str(venv_path), stdout=log, stderr=log
            )
        except BaseException:
            log.close()
            raise
        return process, log

    async def _finish_build(
        self, process: asyncio.subprocess.Process, log: BinaryIO, venv_path: Path, started: float
    ) -> bool:
        """Wait for ``python -m venv`` to end; when it fails, fall back to system Python.

        The deadline counts from the start of the command, so a hang is bounded once however early the interpreter was linked.
        A failed build leaves the directory as it is: processes that start together run the same command on the same path and
        each can fail where another succeeds, so removing it would take away what another process is still building.
        """
        with log:
            try:
                await guarded_communicate(
                    process, max(_BUILD_TIMEOUT_SECONDS - (time.monotonic() - started), 0.0), label="venv create"
                )
                if process.returncode == 0:
                    logger.info(f" [VenvManager] Shared venv built in {time.monotonic() - started:.1f}s: {venv_path}")
                    return True
                log.seek(0)
                reason = log.read().decode("utf-8", errors="replace")
            except Exception as exc:
                reason = str(exc)

        if (venv_path / "bin" / "pip").exists():
            # Another process finished the same venv; its pip is as good as the one this command failed to install.
            return True
        logger.error(f" [VenvManager] Failed to create venv: {reason}")
        self._fall_back_to_system_python()
        return False

    def _use_venv(self, venv_path: Path) -> str:
        self._python_executable = str(venv_path / "bin" / "python")
        self._venv_initialized = True
        logger.warning(f" [VenvManager] Shared venv created: {venv_path}")
        return self._python_executable

    def _fall_back_to_system_python(self) -> str:
        self._python_executable = sys.executable
        self._venv_initialized = True
        return self._python_executable

    async def ensure_pip_ready_for(self, text: str) -> None:
        """Wait until the shared venv has pip when ``text`` names pip; any other text returns at once.

        PATH puts the shared venv's ``bin`` first, so a command that names pip must not start before the venv has one:
        it would reach a pip outside the venv. A venv that is not created yet is created first. The build keeps
        running when the caller is cancelled.
        """
        if not mentions_pip(text):
            return
        await self.get_python_executable()
        build = self._build
        if build is not None and not build.done():
            await asyncio.wait((build,))

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
