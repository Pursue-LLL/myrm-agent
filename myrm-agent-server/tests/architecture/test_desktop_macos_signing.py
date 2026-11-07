"""A macOS release is sealed by the bundler and proven sealed before the shell is launched.

An `.app` whose only signature is the linker's ad-hoc one binds neither its Info.plist nor any resource, and
Gatekeeper reports such a bundle as damaged, with no way to open it. The bundler seals the bundle as soon as the
config names an identity (`-` is the ad-hoc one; Apple credentials replace it), `verify-signing.sh` fails a
bundle that lacks the seal, and the Tauri CLI that does the signing is pinned, so its behaviour changes only
when this repository does.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from tests.support.desktop_release import YamlMapping, bundle_config, expanded_release_steps, release_steps

_BUILD_JOBS = ("build-macos-arm", "build-windows", "build-linux")
_TAURI_ACTION = "tauri-apps/tauri-action@"
_VERIFIER = "myrm-agent-desktop/scripts/verify-signing.sh"
_CLI_INSTALL = re.compile(r"npm install --global @tauri-apps/cli@\d+\.\d+\.\d+")


def _cli_installs(job_id: str) -> list[str]:
    """The commands a job runs that install the Tauri CLI, composite actions expanded."""
    return [str(step["run"]).strip() for step in expanded_release_steps(job_id) if "@tauri-apps/cli" in str(step.get("run", ""))]


def _first_step(steps: list[YamlMapping], field: str, marker: str) -> int:
    return next(index for index, step in enumerate(steps) if marker in str(step.get(field, "")))


def test_every_macos_build_is_sealed_by_the_bundler_even_without_credentials() -> None:
    macos = cast("dict[str, object]", bundle_config("macos")["macOS"])

    # Credentials exported by export-apple-signing-env.sh replace the ad-hoc identity.
    assert macos["signingIdentity"] == "-"
    assert macos["hardenedRuntime"] is True


def test_the_macos_job_verifies_the_seal_between_bundling_and_launching() -> None:
    steps = release_steps("build-macos-arm")
    bundled = _first_step(steps, "uses", _TAURI_ACTION)
    verified = _first_step(steps, "run", _VERIFIER)
    launched = _first_step(steps, "run", "smoke_launch_shell.py")

    assert bundled < verified < launched


@pytest.mark.skipif(sys.platform == "win32", reason="bash step")
@pytest.mark.parametrize(
    ("apple_env", "level"),
    [({}, "sealed"), ({"APPLE_ID": "dev@example.com"}, "notarized")],
)
def test_the_verification_level_follows_the_notarization_credentials(
    tmp_path: Path, apple_env: dict[str, str], level: str
) -> None:
    # The workflow step itself runs, against a stand-in verifier that reports the arguments it was given.
    verifier = tmp_path / _VERIFIER
    verifier.parent.mkdir(parents=True)
    verifier.write_text('echo "$@"\n', encoding="utf-8")
    steps = release_steps("build-macos-arm")
    run = str(steps[_first_step(steps, "run", _VERIFIER)]["run"])
    inherited = {key: value for key, value in os.environ.items() if not key.startswith("APPLE_")}

    completed = subprocess.run(
        ["bash", "-e", "-c", run],
        cwd=tmp_path,
        env={**inherited, **apple_env},
        check=True,
        capture_output=True,
        text=True,
    )

    assert f"--level {level} " in completed.stdout


@pytest.mark.parametrize("job_id", _BUILD_JOBS)
def test_every_build_job_bundles_with_the_pinned_cli(job_id: str) -> None:
    steps = expanded_release_steps(job_id)
    installed = _first_step(steps, "run", "@tauri-apps/cli")
    bundled = _first_step(steps, "uses", _TAURI_ACTION)

    assert installed < bundled
    assert cast("YamlMapping", steps[bundled]["with"])["tauriScript"] == "tauri"


def test_the_cli_version_is_pinned_exactly_and_is_the_same_on_every_platform() -> None:
    installs = {job_id: _cli_installs(job_id) for job_id in _BUILD_JOBS}

    assert all(len(commands) == 1 for commands in installs.values())
    assert len({commands[0] for commands in installs.values()}) == 1
    assert _CLI_INSTALL.fullmatch(installs["build-macos-arm"][0])
