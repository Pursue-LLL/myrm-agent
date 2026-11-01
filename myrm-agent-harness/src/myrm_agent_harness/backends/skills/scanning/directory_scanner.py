"""Multi-file skill directory scanner.

[INPUT]
- scanning.scanner::scan_skill_content, ScanResult, ScanFinding, ScanSeverity (POS: Single-content scanner and result types.)
- scanning.package_audit::audit_skill_directory (POS: package.json supply-chain audit.)

[OUTPUT]
- scan_skill_directory(): scan every text file of a skill directory plus its package.json files into one ScanResult

[POS]
Directory-level scan with safety limits (file count, per-file size, wall-clock budget). Each file goes through
scan_skill_content, so identical file contents are answered from its memo.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from myrm_agent_harness.backends.skills.scanning.scanner import (
    ScanFinding,
    ScanResult,
    ScanSeverity,
    scan_skill_content,
)

logger = logging.getLogger(__name__)

_MAX_SCAN_FILES = 500
_MAX_FILE_SIZE = 512 * 1024  # 512 KB
_SCAN_TIMEOUT_S = 5.0
_SKIP_DIRS = frozenset({"node_modules", ".git", "__pycache__", ".venv", "venv", ".svn", ".hg"})
_TEXT_EXTENSIONS = frozenset(
    {".py", ".sh", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".js", ".ts"}
)


def scan_skill_directory(
    skill_name: str,
    skill_dir: str | Path,
) -> ScanResult:
    """Scan all files in a skill directory for security threats.

    Performs multi-file scanning with safety limits:
    - MAX_SCAN_FILES: 500 files
    - MAX_FILE_SIZE: 512 KB per file
    - SCAN_TIMEOUT: 5 seconds

    Also audits any package.json files found.

    Args:
        skill_name: Skill identifier
        skill_dir: Path to the skill directory

    Returns:
        Combined ScanResult from all files
    """
    from myrm_agent_harness.backends.skills.scanning.package_audit import audit_skill_directory

    start_time = time.monotonic()
    root = Path(skill_dir)
    combined = ScanResult(skill_name=skill_name)

    if not root.is_dir():
        combined.scan_duration_ms = (time.monotonic() - start_time) * 1000
        return combined

    files_scanned = 0
    for file_path in _walk_text_files(root):
        if files_scanned >= _MAX_SCAN_FILES:
            break
        elapsed = time.monotonic() - start_time
        if elapsed > _SCAN_TIMEOUT_S:
            logger.warning("Scan timeout: scanned %d files in %.1fs", files_scanned, elapsed)
            break

        relative = str(file_path.relative_to(root))
        ext = file_path.suffix.lower()

        try:
            stat = file_path.stat()
            if stat.st_size > _MAX_FILE_SIZE or stat.st_size == 0:
                continue
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue

        files_scanned += 1
        file_result = scan_skill_content(f"{skill_name}/{relative}", content, file_extension=ext)
        combined.findings.extend(file_result.findings)
        combined.ast_findings.extend(file_result.ast_findings)

    # Package.json audit
    pkg_findings = audit_skill_directory(root)
    for pf in pkg_findings:
        combined.findings.append(
            ScanFinding(
                threat_type=pf.threat_type,
                severity=ScanSeverity.HIGH if pf.severity == "high" else ScanSeverity.MEDIUM,
                description=pf.description,
            )
        )

    combined.scan_duration_ms = (time.monotonic() - start_time) * 1000

    if not combined.is_clean:
        logger.warning("Directory scan: %s", combined.summary)

    return combined


def _walk_text_files(root: Path):
    """Walk text files in a directory, skipping ignored directories."""
    queue: list[Path] = [root]

    while queue:
        current = queue.pop(0)
        try:
            entries = sorted(current.iterdir())
        except PermissionError:
            continue

        for entry in entries:
            if entry.name.startswith(".") and entry.name not in {".env", ".gitignore"}:
                continue
            if entry.name in _SKIP_DIRS:
                continue
            if entry.is_symlink():
                continue
            if entry.is_file():
                ext = entry.suffix.lower()
                if ext in _TEXT_EXTENSIONS or entry.name == "SKILL.md":
                    yield entry
            elif entry.is_dir():
                queue.append(entry)
