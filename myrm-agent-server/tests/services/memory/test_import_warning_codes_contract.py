"""Contract test: every emitted import warning code is declared in the SSOT.

Emitters live in the import adapters, their parsers and the migration source
loaders, so the scanner walks ``app/services/memory/imports`` and
``app/services/migration`` recursively and collects the codes those modules can
attach to a dry-run result — ``WARNING_*`` constants, ``warnings=[...]``
payloads, ``warnings.append/extend`` calls and ``warning``/``refusal`` helper
arguments. Archive-restore and rollback codes belong to their own review
surfaces and therefore stay out of this vocabulary.
A new code that is not declared in ``app.schemas.memory.import_warning_codes``
fails here, which is what keeps the six-language copy mapping complete.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app.schemas.memory.import_warning_codes import IMPORT_WARNING_CODES

_SERVER_ROOT = Path(__file__).resolve().parents[3]
_SCAN_ROOTS = (
    _SERVER_ROOT / "app" / "services" / "memory" / "imports",
    _SERVER_ROOT / "app" / "services" / "migration",
)
_HELPER_MARKERS = ("warning", "refusal")


def _module_files() -> list[Path]:
    files: list[Path] = []
    for root in _SCAN_ROOTS:
        files.extend(
            sorted(path for path in root.rglob("*.py") if path.name != "__init__.py" and "__pycache__" not in path.parts),
        )
    return files


def _warning_constants(tree: ast.Module) -> dict[str, str]:
    constants: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.startswith("WARNING_"):
                value = node.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    constants[target.id] = value.value
    return constants


# Every dry-run warning code is a multi-segment snake_case identifier.
_CODE_RE = re.compile(r"^[a-z][a-z0-9]*_[a-z0-9_]{3,}$")


def _strings_in(node: ast.AST, constants: dict[str, str]) -> set[str]:
    found: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            found.add(child.value)
        elif isinstance(child, ast.Name) and child.id in constants:
            found.add(constants[child.id])
    return {item for item in found if _CODE_RE.match(item)}


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _emitted_codes(tree: ast.Module, constants: dict[str, str]) -> set[str]:
    """Collect codes the module can attach to a dry-run result."""

    codes: set[str] = set(constants.values())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "warnings":
                    codes |= _strings_in(keyword.value, constants)
            name = _call_name(node.func)
            if name in {"append", "extend"} and isinstance(node.func, ast.Attribute):
                target = node.func.value
                if isinstance(target, ast.Name) and "warning" in target.id.lower():
                    for arg in node.args:
                        codes |= _strings_in(arg, constants)
            elif "warning" in name.lower() or "refusal" in name.lower():
                for arg in (*node.args, *(kw.value for kw in node.keywords)):
                    codes |= _strings_in(arg, constants)
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if value is None or not isinstance(value, ast.List | ast.Set | ast.Tuple):
                continue
            for target in targets:
                if isinstance(target, ast.Name) and "warning" in target.id.lower():
                    codes |= _strings_in(value, constants)
    return codes


def _collected_codes() -> dict[str, set[str]]:
    per_file: dict[str, set[str]] = {}
    for path in _module_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = _warning_constants(tree)
        codes = _emitted_codes(tree, constants)
        codes |= set(constants.values())
        if codes:
            per_file[path.name] = codes
    return per_file


def test_every_emitted_code_is_declared() -> None:
    declared = set(IMPORT_WARNING_CODES)
    per_file = _collected_codes()
    assert per_file, "warning scanner found no emitters — update the scan roots"

    undeclared: dict[str, list[str]] = {}
    for filename, codes in per_file.items():
        unknown = sorted(code for code in codes if code not in declared)
        if unknown:
            undeclared[filename] = unknown

    assert not undeclared, f"warning codes missing from the SSOT vocabulary: {undeclared}"


def test_vocabulary_has_no_stale_entries() -> None:
    per_file = _collected_codes()
    emitted = {code for codes in per_file.values() for code in codes}
    stale = sorted(set(IMPORT_WARNING_CODES) - emitted)

    assert not stale, f"declared warning codes nothing emits: {stale}"


def test_vocabulary_is_unique() -> None:
    assert len(IMPORT_WARNING_CODES) == len(set(IMPORT_WARNING_CODES))
