"""Package manifest security audit for skill directories.

Audits package.json files for supply chain attack vectors:
- Install-time lifecycle scripts (the ones a bare ``npm install`` runs)
- Suspicious commands inside any script
- Entry points and build artifacts that are missing, empty or escape the package
- A manifest the audit cannot take (bad JSON, a repeated key, too deep, a symbolic link) is a high ``invalid_manifest``
  finding: the installer reads it all the same, so it is never clean

[INPUT]
- (none)

[OUTPUT]
- PackageAuditFinding: single finding from package audit
- audit_package_json(): audit a package.json string for security issues
- audit_package_manifest_dict(): audit a parsed manifest for lifecycle scripts and suspicious commands
- check_lifecycle_scripts(): audit every package.json of an in-memory file map
- audit_skill_directory(): scan a skill directory for package.json issues
- audit_package_entry_artifacts(): audit entry files and build artifacts for existence and integrity

[POS]
Supply chain security audit for skill package manifests.
Catches install script attacks that can execute arbitrary code on npm install. Whatever a manifest holds, the audit
answers with findings instead of raising.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# The scripts a bare ``npm install`` runs for the package root; bun, pnpm and yarn each run a subset of them.
_LIFECYCLE_SCRIPTS = (
    "preinstall",
    "install",
    "postinstall",
    "prepublish",
    "preprepare",
    "prepare",
    "postprepare",
)
_MANIFEST_NAME = "package.json"
_SKIPPED_DIRS = frozenset({"node_modules", ".git", "__pycache__", ".venv", "venv"})
_MAX_DIR_DEPTH = 3
_MAX_FILES = 100


@dataclass(frozen=True, slots=True)
class PackageAuditFinding:
    """A single finding from package.json audit."""

    threat_type: str
    severity: str  # "high" or "medium"
    description: str
    file_path: str = ""
    detail: str = ""


class _DuplicateKeyError(ValueError):
    """A JSON object repeats a key."""


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """``object_pairs_hook`` refusing a repeated key: bun keeps the first value, npm, pnpm and yarn the last."""
    manifest: dict[str, object] = {}
    for key, value in pairs:
        if key in manifest:
            raise _DuplicateKeyError
        manifest[key] = value
    return manifest


def _parse_manifest(text: str) -> tuple[dict[str, object] | None, str | None]:
    """Parse package.json text the way the package managers read it.

    Returns ``(manifest, None)`` for a JSON object and ``(None, None)`` for any other JSON value (it declares no
    scripts). ``(None, reason)`` means the text cannot be audited although an installer may still read it, so the
    caller must report it instead of treating it as clean.
    """
    if text.startswith("\ufeff"):  # a BOM: npm, bun and pnpm run a manifest that opens with one (yarn 1 rejects it)
        text = text[1:]
    try:
        loaded = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except _DuplicateKeyError:
        return None, "it repeats a key"
    except json.JSONDecodeError as exc:
        return None, f"it is not valid JSON ({exc.msg})"
    except RecursionError:
        return None, "it is nested too deeply"
    except ValueError:  # an integer with more digits than int() converts
        return None, "it holds a number the parser cannot take"
    except MemoryError:
        return None, "it is too large to parse"
    return (loaded, None) if isinstance(loaded, dict) else (None, None)


def _unauditable_finding(reason: str, file_path: str) -> PackageAuditFinding:
    return PackageAuditFinding(
        threat_type="invalid_manifest",
        severity="high",
        description=f"package.json cannot be audited: {reason}",
        file_path=file_path,
    )


def _is_manifest_name(name: str) -> bool:
    """Case-insensitive: a case-insensitive file system resolves ``Package.json`` to the manifest."""
    return name.lower() == _MANIFEST_NAME


def _script_finding(severity: str, description: str, name: str, command: str, file_path: str) -> PackageAuditFinding:
    """A supply-chain finding about one script, quoting the first 200 characters of its command."""
    return PackageAuditFinding(
        threat_type="supply_chain",
        severity=severity,
        description=description,
        file_path=file_path,
        detail=f"{name}: {command[:200]}",
    )


def audit_package_manifest_dict(pkg: dict[str, object], file_path: str = "") -> list[PackageAuditFinding]:
    """Audit a parsed package.json dictionary for supply chain security issues."""
    scripts = pkg.get("scripts")
    if not isinstance(scripts, dict):
        return []

    findings: list[PackageAuditFinding] = []
    for name in _LIFECYCLE_SCRIPTS:
        command = scripts.get(name)
        if isinstance(command, str) and command.strip():
            findings.append(_script_finding("high", f"Dangerous install script: {name}", name, command, file_path))

    for name, command in scripts.items():
        if isinstance(command, str) and _contains_suspicious_command(command):
            description = f"Script contains suspicious command: {name}"
            findings.append(_script_finding("medium", description, name, command, file_path))
    return findings


def check_lifecycle_scripts(files: dict[str, bytes]) -> list[PackageAuditFinding]:
    """Audit every package.json of an in-memory file map (an archive before extraction)."""
    findings: list[PackageAuditFinding] = []
    for filename, content in files.items():
        if _is_manifest_name(Path(filename).name):
            findings.extend(audit_package_json(content.decode("utf-8", errors="replace"), filename))
    return findings


def audit_package_json(content: str, file_path: str = "") -> list[PackageAuditFinding]:
    """Audit a package.json string for security issues.

    Args:
        content: Raw JSON string of package.json
        file_path: Optional path label for the finding

    Returns:
        List of findings (empty if clean)
    """
    return _audit_manifest_text(content, file_path)


def audit_skill_directory(skill_dir: str | Path) -> list[PackageAuditFinding]:
    """Scan a skill directory for package.json files and audit them.

    Walks the directory tree (up to MAX_DIR_DEPTH levels) looking for
    package.json files. Skips node_modules, .git, etc.

    Args:
        skill_dir: Path to the skill directory

    Returns:
        Combined findings from all package.json files found
    """
    root = Path(skill_dir)
    if not root.is_dir():
        return []

    all_findings: list[PackageAuditFinding] = []
    files_checked = 0

    for file_path in _walk_files(root):
        if files_checked >= _MAX_FILES:
            break

        if not _is_manifest_name(file_path.name):
            continue

        files_checked += 1
        all_findings.extend(_audit_manifest_file(file_path, str(file_path.relative_to(root))))

    return all_findings


def _audit_manifest_text(text: str, file_path: str, artifact_dir: Path | None = None) -> list[PackageAuditFinding]:
    """Audit package.json text; with *artifact_dir*, the entry points it declares are verified there as well."""
    manifest, problem = _parse_manifest(text)
    if problem is not None:
        return [_unauditable_finding(problem, file_path)]
    if manifest is None:
        return []
    findings = audit_package_manifest_dict(manifest, file_path)
    if artifact_dir is not None:
        findings.extend(audit_package_entry_artifacts(manifest, artifact_dir, file_path))
    return findings


def _audit_manifest_file(manifest_path: Path, relative: str) -> list[PackageAuditFinding]:
    """Audit one package.json on disk: its scripts and the artifacts it declares."""
    if manifest_path.is_symlink():
        # An installer follows the link, so what it would read is not what this audit can vouch for.
        return [_unauditable_finding("it is a symbolic link", relative)]
    try:
        raw = manifest_path.read_bytes()
    except OSError:
        return [_unauditable_finding("it cannot be read", relative)]
    return _audit_manifest_text(raw.decode("utf-8", errors="replace"), relative, manifest_path.parent)


def audit_package_entry_artifacts(
    pkg: dict[str, object],
    base_dir: Path,
    manifest_rel_path: str = "package.json",
) -> list[PackageAuditFinding]:
    """Audit declared entry points and executable outputs for physical existence and integrity."""
    findings: list[PackageAuditFinding] = []

    # 1. Audit "main" entry
    main_val = pkg.get("main")
    if isinstance(main_val, str) and main_val.strip():
        findings.extend(_verify_entry_artifact(main_val.strip(), base_dir, manifest_rel_path, "main"))

    # 2. Audit "bin" entries
    bin_val = pkg.get("bin")
    if isinstance(bin_val, str) and bin_val.strip():
        findings.extend(_verify_entry_artifact(bin_val.strip(), base_dir, manifest_rel_path, "bin"))
    elif isinstance(bin_val, dict):
        for cmd_name, cmd_path in bin_val.items():
            if isinstance(cmd_path, str) and cmd_path.strip():
                findings.extend(
                    _verify_entry_artifact(cmd_path.strip(), base_dir, manifest_rel_path, f"bin[{cmd_name}]")
                )

    # 3. Audit "exports" entries (supporting conditional exports and nested maps)
    exports_val = pkg.get("exports")
    if exports_val is not None:
        for target in _collect_export_targets(exports_val):
            findings.extend(_verify_entry_artifact(target, base_dir, manifest_rel_path, "exports"))

    return findings


def _collect_export_targets(val: object) -> list[str]:
    """Collect the relative file paths of a (conditional, nested) ``exports`` value, in document order.

    Iterative: the manifest decides how deeply the value nests, and recursion stops at the interpreter's limit.
    """
    targets: list[str] = []
    pending: list[object] = [val]
    while pending:
        node = pending.pop()
        if isinstance(node, str):
            if node.strip():
                targets.append(node.strip())
        elif isinstance(node, dict):
            pending.extend(reversed(node.values()))
        elif isinstance(node, list):
            pending.extend(reversed(node))
    return targets


def _is_file(path: Path) -> bool:
    """``Path.is_file`` that also answers False for a name the file system rejects (too long)."""
    try:
        return path.is_file()
    except OSError:
        return False


def _resolve_artifact_file(base_dir: Path, clean_entry: str) -> Path | None:
    """Resolve physical file respecting Node.js extension and directory index conventions."""
    direct = base_dir / clean_entry
    if _is_file(direct):
        return direct

    extensions = (".js", ".cjs", ".mjs", ".json")
    for ext in extensions:
        candidate = base_dir / f"{clean_entry}{ext}"
        if _is_file(candidate):
            return candidate

    for ext in extensions:
        candidate = base_dir / clean_entry / f"index{ext}"
        if _is_file(candidate):
            return candidate

    return None


def _verify_entry_artifact(
    entry_rel: str,
    base_dir: Path,
    manifest_rel_path: str,
    field_label: str,
) -> list[PackageAuditFinding]:
    """Verify a single declared artifact path exists, is inside base_dir, and is non-empty."""
    findings: list[PackageAuditFinding] = []
    clean_entry = entry_rel.strip()
    if clean_entry.startswith("./") or clean_entry.startswith(".\\"):
        clean_entry = clean_entry[2:]

    parts = clean_entry.replace("\\", "/").split("/")
    if ".." in parts or clean_entry.startswith(("/", "\\")):
        findings.append(
            PackageAuditFinding(
                threat_type="integrity",
                severity="high",
                description=f"Declared {field_label} uses unsafe path traversal: {entry_rel}",
                file_path=manifest_rel_path,
                detail=f"Path traversal blocked: {entry_rel}",
            )
        )
        return findings

    resolved_file = _resolve_artifact_file(base_dir, clean_entry)
    if resolved_file is None:
        ts_hint = ""
        src_dir = base_dir / "src"
        if src_dir.is_dir() and any(src_dir.glob("*.ts")):
            ts_hint = " Detected TypeScript sources in 'src/' but missing compiled outputs. Run 'npm run build' before packaging."

        findings.append(
            PackageAuditFinding(
                threat_type="missing_artifact",
                severity="high",
                description=f"Declared {field_label} entry file not found: {entry_rel}",
                file_path=manifest_rel_path,
                detail=f"Missing file: {clean_entry}.{ts_hint}",
            )
        )
    elif resolved_file.stat().st_size == 0:
        findings.append(
            PackageAuditFinding(
                threat_type="empty_artifact",
                severity="high",
                description=f"Declared {field_label} entry file is empty (0 bytes): {entry_rel}",
                file_path=manifest_rel_path,
                detail=f"Empty file: {clean_entry}",
            )
        )

    return findings


def _walk_files(root: Path) -> Iterator[Path]:
    """Yield the files under *root* level by level (down to ``_MAX_DIR_DEPTH``), skipping ignored directories.

    A symbolic link is yielded only when it is named like a manifest: an installer follows it, so it must be reported.
    """
    queue: list[tuple[int, Path]] = [(0, root)]

    while queue:
        depth, current = queue.pop(0)
        try:
            entries = sorted(current.iterdir())
        except PermissionError:
            continue

        for entry in entries:
            if entry.name.startswith(".") and entry.name not in {".env", ".gitignore"}:
                continue
            if entry.name in _SKIPPED_DIRS:
                continue
            if entry.is_symlink():
                if _is_manifest_name(entry.name):
                    yield entry
                continue
            if entry.is_file():
                yield entry
            elif entry.is_dir() and depth < _MAX_DIR_DEPTH:
                queue.append((depth + 1, entry))


def _contains_suspicious_command(script: str) -> bool:
    """Check if a script value contains suspicious commands."""
    suspicious = [
        "curl ",
        "wget ",
        "chmod +x",
        "eval ",
        "node -e",
        "python -c",
        "/dev/tcp",
        "nc -",
        "netcat ",
    ]
    lowered = script.lower()
    return any(cmd in lowered for cmd in suspicious)
