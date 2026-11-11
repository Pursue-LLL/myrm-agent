"""Unit tests for lockfile dependency extraction (uv.lock, bun.lock, package-lock.json)."""

from __future__ import annotations

import json
import time

import pytest

from myrm_agent_harness.backends.skills.scanning.dependency_extractor import (
    extract_dependencies_from_bun_lock,
    extract_dependencies_from_files,
    extract_dependencies_from_package_lock_json,
    extract_dependencies_from_uv_lock,
)


def test_extract_dependencies_from_uv_lock_basic() -> None:
    content = """
version = 1
revision = 1

[[package]]
name = "aiofiles"
version = "25.1.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "fastapi"
version = "0.115.0"
dependencies = [
    { name = "pydantic" },
]
"""
    deps = extract_dependencies_from_uv_lock(content, "uv.lock")
    assert len(deps) == 2
    assert deps[0].name == "aiofiles"
    assert deps[0].version_spec == "25.1.0"
    assert deps[0].ecosystem == "PyPI"
    assert deps[0].file_path == "uv.lock"

    assert deps[1].name == "fastapi"
    assert deps[1].version_spec == "0.115.0"
    assert deps[1].ecosystem == "PyPI"


# Shaped like a lockfile written by Bun: JSONC with a trailing comma after every last member, and
# `packages` entries of the form [ident, registry, metadata, integrity].
_BUN_LOCK_TEXT = """{
  "lockfileVersion": 1,
  "workspaces": {
    "": {
      "name": "app",
      "dependencies": {
        "next": "^16.4.5",
        "xlsx": "https://cdn.sheetjs.com/xlsx-0.20.3/xlsx-0.20.3.tgz",
      },
      "devDependencies": {
        "typescript": "^5.0.0",
      },
    },
  },
  "trustedDependencies": ["@swc/core"],
  "packages": {
    "@babel/runtime": ["@babel/runtime@7.29.2", "https://registry.npmjs.org/@babel/runtime/-/runtime-7.29.2.tgz", {}, "sha512-aaa"],
    "app": ["app@workspace:."],
    "dup/postcss": ["postcss@8.5.6", "", {}, "sha512-ddd"],
    "next": ["next@16.4.5", "https://registry.npmjs.org/next/-/next-16.4.5.tgz", { "dependencies": { "postcss": "8.4.31" } }, "sha512-bbb"],
    "next/postcss": ["postcss@8.4.31", "", { "dependencies": { "nanoid": "^3.3.6" } }, "sha512-ccc"],
    "postcss": ["postcss@8.5.6", "", {}, "sha512-ddd"],
    "tool": ["tool@github:owner/tool#abc1234", {}, "abc1234"],
    "typescript": ["typescript@5.9.3-rc.1", "", { "bin": { "tsc": "bin/tsc" } }, "sha512-eee"],
    "xlsx": ["xlsx@https://cdn.sheetjs.com/xlsx-0.20.3/xlsx-0.20.3.tgz", { "bin": { "xlsx": "./bin/xlsx.njs" } }, "sha512-fff"],
  }
}
"""


def test_extract_dependencies_from_bun_lock_reads_resolved_registry_packages() -> None:
    deps = extract_dependencies_from_bun_lock(_BUN_LOCK_TEXT, "bun.lock")

    # Scoped names keep their "@", nested copies of one package at different versions are both reported,
    # and the same name@version resolved under two keys is reported once.
    assert [(d.name, d.version_spec) for d in deps] == [
        ("@babel/runtime", "7.29.2"),
        ("postcss", "8.5.6"),
        ("next", "16.4.5"),
        ("postcss", "8.4.31"),
        ("typescript", "5.9.3-rc.1"),
    ]
    assert all(d.ecosystem == "npm" and d.file_path == "bun.lock" and not d.is_dev for d in deps)


@pytest.mark.parametrize(
    "content",
    [
        "",
        "not json",
        "[]",
        '{"workspaces": {}}',
        '{"packages": []}',
        '{"packages": {"a": "text", "b": [], "c": [1], "d": ["no-version-separator"], "e": ["@scope-only"]}}',
        '{"packages": ' + "1" * 5000 + "}",  # beyond Python's integer-literal digit limit
        "[" * 200_000 + "]" * 200_000,  # beyond the parser's recursion limit
    ],
)
def test_extract_dependencies_from_bun_lock_ignores_unusable_content(content: str) -> None:
    assert extract_dependencies_from_bun_lock(content, "bun.lock") == []


def test_extract_dependencies_from_bun_lock_runs_in_linear_time_on_hostile_input() -> None:
    # An unterminated string ending in a lone backslash made a naive trailing-comma stripper quadratic:
    # 40 KB took ~10 s, so a skill-supplied lockfile could stall the scanner for hours.
    hostile = '"' + '\\"' * 20_000 + "\\"

    started = time.perf_counter()
    assert extract_dependencies_from_bun_lock(hostile, "bun.lock") == []
    assert time.perf_counter() - started < 2.0


def test_extract_dependencies_from_package_lock_json_v3() -> None:
    data = {
        "name": "test-pkg",
        "lockfileVersion": 3,
        "packages": {
            "": {
                "name": "test-pkg",
            },
            "node_modules/express": {
                "version": "4.19.2",
                "dev": False,
            },
            "node_modules/@types/node": {
                "name": "@types/node",
                "version": "20.11.0",
                "dev": True,
            },
        },
    }
    content = json.dumps(data)
    deps = extract_dependencies_from_package_lock_json(content, "package-lock.json")
    assert len(deps) == 2

    dep_map = {d.name: (d.version_spec, d.is_dev) for d in deps}
    assert "express" in dep_map
    assert dep_map["express"] == ("4.19.2", False)
    assert "@types/node" in dep_map
    assert dep_map["@types/node"] == ("20.11.0", True)


def test_extract_dependencies_from_files_lockfiles() -> None:
    uv_content = b"""
[[package]]
name = "pydantic"
version = "2.9.2"
"""

    files = {
        "workspace/uv.lock": uv_content,
    }

    deps = extract_dependencies_from_files(files)
    assert len(deps) == 1
    assert deps[0].name == "pydantic"
    assert deps[0].version_spec == "2.9.2"
    assert deps[0].ecosystem == "PyPI"


def test_extract_dependencies_from_files_reads_bun_lock() -> None:
    deps = extract_dependencies_from_files({"web/bun.lock": _BUN_LOCK_TEXT.encode()})

    assert {(d.name, d.version_spec) for d in deps} >= {("next", "16.4.5"), ("@babel/runtime", "7.29.2")}
    assert {d.file_path for d in deps} == {"web/bun.lock"}
