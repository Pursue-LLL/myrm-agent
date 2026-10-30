"""The release's manifest gates demand exactly the platforms the release builds.

`finalize-release.sh` fails when a required platform has no signed updater bundle and `verify-release.sh`
fails when `latest.json` lacks one, so a platform that no job builds, or that the gate does not wait for,
blocks the manifest of every platform. The list is written in three places (the first finalize, the
re-finalize after Linux, the manual repair workflow); this pins them against the build jobs and each other.
"""

from __future__ import annotations

from typing import cast

import pytest

from tests.support.desktop_release import YamlMapping, workflow_jobs

# The OTA manifest key each platform's updater bundle is published under, and the job that builds it.
_BUILDER = {"darwin-aarch64": "build-macos-arm", "windows-x86_64": "build-windows", "linux-x86_64": "build-linux"}

_RELEASE = "desktop-release.yml"
_REPAIR = "desktop-release-repair.yml"
_FINALIZE = "finalize-release.sh"
_VERIFY = "verify-release.sh"

# The jobs that run the manifest gate: `(workflow file, job id)`.
_GATES = ((_RELEASE, "finalize-release"), (_RELEASE, "refinalize-after-linux"), (_REPAIR, "refinalize"))


def _needs_closure(jobs: dict[str, YamlMapping], job_id: str) -> set[str]:
    """Every job that has to finish before `job_id` starts."""
    needs = jobs[job_id].get("needs", [])
    direct = [needs] if isinstance(needs, str) else cast("list[str]", needs)
    return {*direct, *(job for parent in direct for job in _needs_closure(jobs, parent))}


def _step_env(workflow: str, job_id: str, script: str) -> YamlMapping:
    steps = cast("list[YamlMapping]", workflow_jobs(workflow)[job_id]["steps"])
    running_script = [step for step in steps if script in str(step.get("run", ""))]
    assert len(running_script) == 1, f"{job_id} must run {script} exactly once"
    return cast("YamlMapping", running_script[0]["env"])


def _required_keys(workflow: str, job_id: str) -> list[str]:
    return str(_step_env(workflow, job_id, _FINALIZE)["REQUIRED_OTA_PLATFORM_KEYS"]).split()


def _requirements(workflow: str, job_id: str, script: str) -> dict[str, object]:
    return {key: value for key, value in _step_env(workflow, job_id, script).items() if key.startswith("REQUIRE")}


def test_every_build_job_has_a_platform_in_the_manifest() -> None:
    # A new build job fails here until the gates are told to require the platform it produces.
    built = {job_id for job_id in workflow_jobs(_RELEASE) if job_id.startswith("build-")}

    assert built == set(_BUILDER.values())


@pytest.mark.parametrize(("workflow", "job_id"), _GATES)
def test_a_gate_requires_one_consistent_set_of_platforms_a_job_builds(workflow: str, job_id: str) -> None:
    keys = _required_keys(workflow, job_id)
    verify = _step_env(workflow, job_id, _VERIFY)

    assert keys
    assert set(keys) <= set(_BUILDER)
    assert str(verify["REQUIRED_OTA_PLATFORM_KEYS"]).split() == keys
    assert int(str(verify["REQUIRE_MIN_OTA_PLATFORMS"])) == len(keys)


@pytest.mark.parametrize("job_id", ["finalize-release", "refinalize-after-linux"])
def test_a_gate_waits_for_every_platform_it_requires(job_id: str) -> None:
    jobs = workflow_jobs(_RELEASE)
    required_builders = {_BUILDER[key] for key in _required_keys(_RELEASE, job_id)}

    assert required_builders <= _needs_closure(jobs, job_id)


def test_the_last_gate_requires_every_platform_the_release_builds() -> None:
    assert set(_required_keys(_RELEASE, "refinalize-after-linux")) == set(_BUILDER)


@pytest.mark.parametrize("script", [_FINALIZE, _VERIFY])
def test_the_repair_workflow_demands_what_a_full_release_demands(script: str) -> None:
    assert _requirements(_REPAIR, "refinalize", script) == _requirements(_RELEASE, "refinalize-after-linux", script)
