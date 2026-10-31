"""Layout QA helper for Office documents after writes.

[INPUT]
- Path to .docx on disk
- core.security.bounded_communicate::communicate_bounded (POS: communicate() with a cap on each pipe, stopping the process through the caller's on_abort)
- utils.os_compat::get_process_group_kwargs, kill_spawned_group (POS: cross-platform process-group control)

[OUTPUT]
- run_layout_qa_check: optional soffice conversion sanity check; a conversion that has not finished after 60 s is stopped with everything it started and reported

[POS]
Optional soffice headless PDF conversion check; invoked by OfficeBashAudit finalize step. soffice runs in a process
group of its own under a deadline, so a conversion that never ends (or a cancelled check) cannot leave soffice behind
or hold the bash tool's result.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

from myrm_agent_harness.core.security.bounded_communicate import communicate_bounded
from myrm_agent_harness.utils.os_compat import get_process_group_kwargs, kill_spawned_group

logger = logging.getLogger(__name__)

# The bound the soffice conversion in toolkits/file_parsers uses.
_CONVERT_TIMEOUT_SECONDS = 60.0


async def _stop_soffice(proc: asyncio.subprocess.Process) -> None:
    """Kill soffice and what it started (the soffice.bin behind the launcher): they share the group named after its pid."""
    kill_spawned_group(proc.pid)


async def run_layout_qa_check(file_path: Path) -> list[str]:
    """Run a lightweight layout QA gate when soffice is available."""
    warnings: list[str] = []
    if file_path.suffix.lower() not in {".docx", ".doc"}:
        return warnings
    if not file_path.is_file():
        return warnings

    soffice = shutil.which("soffice")
    if soffice is None:
        logger.debug("Layout QA skipped: soffice not available for %s", file_path)
        return warnings

    with tempfile.TemporaryDirectory(prefix="office-layout-qa-") as tmp_dir:
        tmp = Path(tmp_dir)
        cmd = [
            soffice,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(tmp),
            str(file_path.resolve()),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **get_process_group_kwargs(),
            )
            captured = await communicate_bounded(
                proc, timeout=_CONVERT_TIMEOUT_SECONDS, on_abort=lambda: _stop_soffice(proc)
            )
        # Before OSError: TimeoutError is a subclass of it.
        except TimeoutError:
            logger.warning("Layout QA soffice did not finish for %s within %.0fs", file_path, _CONVERT_TIMEOUT_SECONDS)
            warnings.append(
                f"Layout QA failed: soffice did not finish converting {file_path.name} "
                f"within {_CONVERT_TIMEOUT_SECONDS:.0f}s."
            )
            return warnings
        except OSError as exc:
            logger.warning("Layout QA soffice failed for %s: %s", file_path, exc)
            warnings.append(f"Layout QA failed to run soffice: {exc}")
            return warnings

        if proc.returncode != 0:
            detail = captured.stderr.decode("utf-8", errors="replace").strip()
            warnings.append(
                f"Layout QA failed: soffice could not convert {file_path.name} (exit {proc.returncode}). {detail[:200]}"
            )
            return warnings

        pdf_path = tmp / f"{file_path.stem}.pdf"
        if not pdf_path.is_file() or pdf_path.stat().st_size < 128:
            warnings.append(f"Layout QA failed: converted PDF for {file_path.name} is missing or empty.")

    return warnings
