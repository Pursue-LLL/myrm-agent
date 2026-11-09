"""Image request edges: what a caller leaves out leaves its field out of the request, and an Azure API version that a
call does not name comes from the environment."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.transport import images
from myrm_agent_harness.toolkits.llms.transport.service_routes import service_route

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def test_a_gemini_image_model_given_an_unreadable_size_sends_no_image_config() -> None:
    route = service_route("gemini/gemini-3-pro-image-preview", api_key="k", api_base=None)

    request = images._gemini_request(route, "a cat", "huge", 1, 30.0)

    assert request.body == {
        "contents": [{"parts": [{"text": "a cat"}]}],
        "generationConfig": {"response_modalities": ["IMAGE", "TEXT"], "candidateCount": 1},
    }


def test_a_stability_request_with_an_unreadable_size_and_no_key_names_neither_ratio_nor_credentials() -> None:
    route = service_route("stability/sd3", api_key=None, api_base=None)

    request = images._stability_request(route, "a cat", "huge", 30.0)

    assert request.form == {"prompt": "a cat", "output_format": "png"}
    assert request.headers == {"Accept": "application/json"}


def _azure_versions() -> tuple[dict[str, str], dict[str, str]]:
    """The ``api-version`` query of a generation and of an edit sent to an Azure deployment."""
    route = service_route("azure/gpt-image-1", api_key="k", api_base="https://r.openai.azure.com")
    generation = images._openai_generation(route, "a cat", "1024x1024", None, None, 1, 30.0)
    edit = images._openai_edit(route, _PNG, "a cat", None, "1024x1024", 1, 30.0)
    return dict(generation.query), dict(edit.query)


def test_an_azure_image_request_takes_its_api_version_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_API_VERSION", "2025-04-01-preview")

    generation, edit = _azure_versions()

    assert generation == edit == {"api-version": "2025-04-01-preview"}


def test_an_azure_image_request_gets_the_default_version_when_the_environment_names_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_API_VERSION", raising=False)

    generation, edit = _azure_versions()

    assert generation == edit == {"api-version": "2025-02-01-preview"}
