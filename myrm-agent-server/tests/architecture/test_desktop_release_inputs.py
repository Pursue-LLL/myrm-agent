"""Every input the desktop bundle declares has a producer that ships it.

`bundle.resources` sources are resolved while the Tauri crate compiles, so a single path that no job
produces fails the build on every platform. This pins each resource group to what makes it:

- the sidecar folder -> `sidecar/build.py`, run by every build job through one shared composite action
- the Next server and client assets -> the frontend artifact the build jobs download
- the tokenizer tables -> the sidecar's own copy: litellm carries them and the PyInstaller command
  collects them, so no separate resource exists
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

from tests.support.desktop_release import (
    FRONTEND,
    REPO_ROOT,
    TAURI_CONF,
    YamlMapping,
    expanded_release_steps,
    release_jobs,
    release_steps,
    sidecar_build_module,
)

# The architecture of the app each build job bundles its sidecar into; PyInstaller cannot cross-compile.
_SIDECAR_ARCH = {"build-macos-arm": "arm64", "build-windows": "x86_64", "build-linux": "x86_64"}
_BUILD_JOBS = frozenset(_SIDECAR_ARCH)
_SIDECAR_ACTION = "./.github/actions/build-sidecar"


def _runner_arch(label: str) -> str:
    """Architecture of a GitHub-hosted runner label: macOS images are arm64 unless they name the Intel host."""
    if label.startswith("macos-"):
        return "x86_64" if label.endswith(("-intel", "-large")) else "arm64"
    return "arm64" if label.endswith("-arm") else "x86_64"


def _resource_sources() -> list[str]:
    conf = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    return list(conf["bundle"]["resources"])


def _artifact_steps(action: str) -> list[tuple[str, YamlMapping]]:
    """`(job id, step)` for every step a runner executes in the release workflow that runs `actions/<action>`."""
    return [
        (job_id, step)
        for job_id in release_jobs()
        for step in expanded_release_steps(job_id)
        if str(step.get("uses", "")).startswith(f"actions/{action}@")
    ]


def _sidecar_call(job_id: str) -> YamlMapping:
    calls = [step for step in release_steps(job_id) if step.get("uses") == _SIDECAR_ACTION]
    assert len(calls) == 1, f"{job_id} must build its sidecar once, through {_SIDECAR_ACTION}"
    return cast("YamlMapping", calls[0]["with"])


def _frontend_upload() -> YamlMapping:
    uploads = [
        step for step in release_steps("prepare-frontend") if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    ]
    assert len(uploads) == 1, "prepare-frontend must publish exactly one artifact"
    return cast("YamlMapping", uploads[0]["with"])


def _uploaded_paths(upload: YamlMapping) -> list[Path]:
    return [Path(line.strip()) for line in str(upload["path"]).splitlines() if line.strip()]


def test_the_sidecar_folder_is_the_only_binaries_resource() -> None:
    # build.py writes nothing else under binaries/, so any other entry points at a path nobody produces.
    sidecar = f"binaries/{sidecar_build_module().SIDECAR_NAME}"

    assert [source for source in _resource_sources() if source.startswith("binaries/")] == [sidecar]


def test_every_build_job_builds_the_sidecar_for_the_architecture_it_bundles() -> None:
    assert {job_id for job_id in release_jobs() if job_id.startswith("build-")} == _BUILD_JOBS
    assert {job_id: _sidecar_call(job_id)["arch"] for job_id in _BUILD_JOBS} == _SIDECAR_ARCH


def test_every_build_job_runs_on_a_host_of_the_architecture_it_bundles() -> None:
    # PyInstaller freezes the host interpreter, so an x86_64 sidecar cannot come out of an arm64 runner.
    jobs = release_jobs()

    assert {job_id: _runner_arch(str(jobs[job_id]["runs-on"])) for job_id in _BUILD_JOBS} == _SIDECAR_ARCH


def test_the_sidecar_is_built_in_one_place() -> None:
    # A job that builds it by hand would drift from the composite action (arch export, venv sync, order).
    by_hand = [
        job_id
        for job_id in release_jobs()
        if any("python build.py" in str(step.get("run", "")) for step in release_steps(job_id))
    ]

    assert by_hand == []


def test_the_sidecar_action_exports_the_architecture_and_syncs_the_venv_before_it_builds() -> None:
    runs = [str(step.get("run", "")) for step in expanded_release_steps("build-linux")]
    arch, sync, build = (
        next(index for index, run in enumerate(runs) if marker in run)
        for marker in ("TARGET_ARCH=", "sync-server-venv.sh", "python build.py")
    )

    assert arch < build
    assert sync < build


def test_the_macos_job_installs_the_rust_target_it_builds() -> None:
    # The target is written twice (toolchain and bundle step) and drifts silently when only one is edited.
    tauri = next(
        step for step in release_steps("build-macos-arm") if str(step.get("uses", "")).startswith("tauri-apps/tauri-action@")
    )
    target = _sidecar_call("build-macos-arm")["rust-target"]

    assert f"--target {target}" in str(cast("YamlMapping", tauri["with"])["args"])


def test_frontend_artifact_carries_every_next_output_the_bundle_declares() -> None:
    next_dir = (FRONTEND / ".next").resolve()
    declared = [
        resolved.relative_to(REPO_ROOT)
        for resolved in ((TAURI_CONF.parent / source).resolve() for source in _resource_sources())
        if resolved.is_relative_to(next_dir)
    ]
    assert declared, "tauri.conf.json no longer bundles any .next output; update this contract"

    uploaded = _uploaded_paths(_frontend_upload())
    missing = [str(path) for path in declared if not any(path.is_relative_to(root) for root in uploaded)]
    assert not missing, f"bundled but not in the frontend artifact: {missing}"


def test_frontend_artifact_keeps_the_hidden_server_output_and_fails_when_empty() -> None:
    upload = _frontend_upload()

    # The standalone server keeps its compiled pages in a hidden `.next/` folder; upload-artifact
    # skips hidden files unless told otherwise, and a server without them starts but serves nothing.
    assert upload.get("include-hidden-files") is True
    assert upload.get("if-no-files-found") == "error"


def test_every_build_job_restores_the_artifact_to_where_the_bundle_reads_it() -> None:
    upload = _frontend_upload()
    # With several paths, upload-artifact roots the artifact at their common ancestor.
    root = os.path.commonpath([path.as_posix() for path in _uploaded_paths(upload)])
    downloads = [
        (job_id, step)
        for job_id, step in _artifact_steps("download-artifact")
        if cast("YamlMapping", step["with"])["name"] == upload["name"]
    ]

    assert {job_id for job_id, _ in downloads} == _BUILD_JOBS
    assert [job_id for job_id, step in downloads if cast("YamlMapping", step["with"])["path"] != root] == []


def test_pyinstaller_collects_the_tokenizer_tables_the_sidecar_relies_on() -> None:
    cmd = sidecar_build_module().pyinstaller_command(Path("python"), Path("work"))
    options = set(zip(cmd, cmd[1:], strict=False))

    assert ("--collect-data", "litellm") in options
    assert ("--collect-submodules", "tiktoken_ext") in options
    assert ("--hidden-import", "tiktoken_ext.openai_public") in options


_OFFLINE_TOKENIZER_PROBE = """
import litellm
import tiktoken
from myrm_agent_harness.utils.text_utils import PLANNING_ENCODING

for name in ("cl100k_base", PLANNING_ENCODING):
    tiktoken.get_encoding(name)
"""


def test_token_counting_works_offline_from_the_tables_litellm_bundles(tmp_path: Path) -> None:
    # litellm repoints TIKTOKEN_CACHE_DIR at its own tables on import. The empty cache, the empty temp
    # dir (tiktoken's fallback cache) and a dead proxy make any attempt to download a table fail
    # loudly, so a litellm release that stops bundling one fails here instead of in a packaged app.
    temp_dir = tmp_path / "tmp"
    temp_dir.mkdir()
    dead_proxy = "http://127.0.0.1:9"
    env = {key: value for key, value in os.environ.items() if key not in {"DATA_GYM_CACHE_DIR", "CUSTOM_TIKTOKEN_CACHE_DIR"}}
    env.update(
        TIKTOKEN_CACHE_DIR=str(tmp_path / "cache"),
        TMPDIR=str(temp_dir),
        TEMP=str(temp_dir),
        TMP=str(temp_dir),
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        NO_PROXY="",
        no_proxy="",
    )
    for proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env[proxy_var] = dead_proxy

    completed = subprocess.run(
        [sys.executable, "-c", _OFFLINE_TOKENIZER_PROBE],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert completed.returncode == 0, completed.stderr[-2000:]
