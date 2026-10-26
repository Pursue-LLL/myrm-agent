"""Resource attributes shared by the trace and metric providers.

[INPUT]
- opentelemetry.sdk.resources::OTELResourceDetector, Resource (POS: standard resource env handling)
- infra.git.git_resolver::resolve_git_metadata (POS: filesystem-only VCS metadata)

[OUTPUT]
- build_resource: Resource with Myrm defaults that the standard environment variables override
- VCS_REF_HEAD_NAME / VCS_REPOSITORY_CHANGE_ID / VCS_REPOSITORY_REF_TYPE: VCS resource attribute names

[POS]
One Resource builder for traces and metrics, so both signals describe the same service. Service
name, version and deployment environment are defaults; ``OTEL_SERVICE_NAME`` and
``OTEL_RESOURCE_ATTRIBUTES`` always win, which is how an operator (or the control plane) labels
an instance without a code change.
"""

from __future__ import annotations

from collections.abc import Mapping

from opentelemetry.sdk.resources import SERVICE_NAME, OTELResourceDetector, Resource

from myrm_agent_harness.infra.git.git_resolver import resolve_git_metadata

VCS_REF_HEAD_NAME = "vcs.ref.head.name"
VCS_REPOSITORY_CHANGE_ID = "vcs.repository.change.id"
VCS_REPOSITORY_REF_TYPE = "vcs.repository.ref.type"


def build_resource(service_name: str, attributes: Mapping[str, str] | None = None) -> Resource:
    """Build the Resource: caller defaults < VCS metadata < ``OTEL_*`` environment values."""
    merged: dict[str, str] = {SERVICE_NAME: service_name, **(attributes or {})}
    git = resolve_git_metadata()
    if git.branch:
        merged[VCS_REF_HEAD_NAME] = git.branch
        merged[VCS_REPOSITORY_REF_TYPE] = "branch"
    if git.commit:
        merged[VCS_REPOSITORY_CHANGE_ID] = git.commit
    # ``Resource.create`` lets explicit attributes override the environment; folding the
    # environment into the explicit set first keeps the standard variables authoritative.
    merged.update({key: str(value) for key, value in OTELResourceDetector().detect().attributes.items()})
    return Resource.create(merged)
