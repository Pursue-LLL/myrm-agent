"""Tests for competitor secret import with provider seeding."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.migration.source.source_secrets_importer import import_external_source_secrets


@pytest.mark.asyncio
async def test_import_secrets_seeds_providers_when_list_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / ".hermes"
    root.mkdir()
    (root / ".env").write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")

    monkeypatch.setattr(
        "app.services.migration.source.source_secrets_importer.is_local_mode",
        lambda: True,
    )

    stored: dict[str, object] = {}

    async def fake_get(key: str) -> MagicMock | None:
        assert key == "providers"
        return None

    async def fake_set(
        key: str,
        value: dict[str, object],
        *,
        device_id: str,
        expected_version: str | None,
    ) -> None:
        assert key == "providers"
        assert device_id == "competitor-migration"
        stored["value"] = value

    monkeypatch.setattr(
        "app.services.migration.source.source_secrets_importer.config_service.get",
        fake_get,
    )
    monkeypatch.setattr(
        "app.services.migration.source.source_secrets_importer.config_service.set",
        fake_set,
    )

    result = await import_external_source_secrets(root)
    assert result["imported_keys"] == ["OPENAI_API_KEY"]
    providers = stored["value"]["providers"]
    assert isinstance(providers, list)
    assert len(providers) == 1
    assert providers[0]["id"] == "openai"


@pytest.mark.asyncio
async def test_import_ai_gateway_api_key_seeds_vercel_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / ".hermes"
    root.mkdir()
    (root / ".env").write_text("AI_GATEWAY_API_KEY=vca_test_secret_123\n", encoding="utf-8")

    monkeypatch.setattr(
        "app.services.migration.source.source_secrets_importer.is_local_mode",
        lambda: True,
    )

    stored: dict[str, object] = {}

    async def fake_get(key: str) -> MagicMock | None:
        assert key == "providers"
        return None

    async def fake_set(
        key: str,
        value: dict[str, object],
        *,
        device_id: str,
        expected_version: str | None,
    ) -> None:
        assert key == "providers"
        assert device_id == "competitor-migration"
        stored["value"] = value

    monkeypatch.setattr(
        "app.services.migration.source.source_secrets_importer.config_service.get",
        fake_get,
    )
    monkeypatch.setattr(
        "app.services.migration.source.source_secrets_importer.config_service.set",
        fake_set,
    )

    result = await import_external_source_secrets(root)
    assert result["imported_keys"] == ["AI_GATEWAY_API_KEY"]
    providers = stored["value"]["providers"]
    assert isinstance(providers, list)
    assert len(providers) == 1
    assert providers[0]["id"] == "vercel_ai_gateway"
    assert providers[0]["name"] == "Vercel AI Gateway"
    assert providers[0]["routingProfile"] == "openai"
    assert providers[0]["apiUrl"] == "https://ai-gateway.vercel.sh/v1"
    assert providers[0]["apiKeys"][0]["key"] == "vca_test_secret_123"


@pytest.mark.asyncio
async def test_import_vercel_ai_gateway_key_seeds_vercel_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / ".hermes"
    root.mkdir()
    (root / ".env").write_text("VERCEL_AI_GATEWAY_KEY=vck_prod_secret_456\n", encoding="utf-8")

    monkeypatch.setattr(
        "app.services.migration.source.source_secrets_importer.is_local_mode",
        lambda: True,
    )

    stored: dict[str, object] = {}

    async def fake_get(key: str) -> MagicMock | None:
        assert key == "providers"
        return None

    async def fake_set(
        key: str,
        value: dict[str, object],
        *,
        device_id: str,
        expected_version: str | None,
    ) -> None:
        assert key == "providers"
        assert device_id == "competitor-migration"
        stored["value"] = value

    monkeypatch.setattr(
        "app.services.migration.source.source_secrets_importer.config_service.get",
        fake_get,
    )
    monkeypatch.setattr(
        "app.services.migration.source.source_secrets_importer.config_service.set",
        fake_set,
    )

    result = await import_external_source_secrets(root)
    assert result["imported_keys"] == ["VERCEL_AI_GATEWAY_KEY"]
    providers = stored["value"]["providers"]
    assert isinstance(providers, list)
    assert len(providers) == 1
    assert providers[0]["id"] == "vercel_ai_gateway"
    assert providers[0]["apiKeys"][0]["key"] == "vck_prod_secret_456"


async def _import_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_bytes: bytes,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Run the import of ``env_bytes`` as a ``.env`` into an empty providers config; return the result and the rows."""
    root = tmp_path / ".hermes"
    root.mkdir()
    (root / ".env").write_bytes(env_bytes)
    stored: dict[str, object] = {}

    async def fake_get(key: str) -> MagicMock | None:
        return None

    async def fake_set(key: str, value: dict[str, object], *, device_id: str, expected_version: str | None) -> None:
        stored["value"] = value

    prefix = "app.services.migration.source.source_secrets_importer"
    monkeypatch.setattr(f"{prefix}.is_local_mode", lambda: True)
    monkeypatch.setattr(f"{prefix}.config_service.get", fake_get)
    monkeypatch.setattr(f"{prefix}.config_service.set", fake_set)

    result = await import_external_source_secrets(root)
    value = stored.get("value")
    providers = value["providers"] if isinstance(value, dict) else []
    assert isinstance(providers, list)
    return result, providers


@pytest.mark.asyncio
async def test_import_reads_the_dotenv_grammar_competitors_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = (
        b"# a comment\n"
        b'export OPENAI_API_KEY="sk-quoted"  # trailing comment\n'
        b"ANTHROPIC_API_KEY='sk-ant-single'\n"
        b"GROQ_API_KEY =  gsk-spaced  \n"
        b"XAI_API_KEY=\n"
        b"this line is not an assignment\n"
        b"DEEPSEEK_API_KEY=sk-deep\n"
    )

    result, providers = await _import_env(tmp_path, monkeypatch, env)

    assert result["imported_keys"] == ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY"]
    keys = {row["id"]: row["apiKeys"][0]["key"] for row in providers}  # type: ignore[index]
    assert keys == {"openai": "sk-quoted", "anthropic": "sk-ant-single", "groq": "gsk-spaced", "deepseek": "sk-deep"}


@pytest.mark.asyncio
async def test_import_never_reads_this_process_environment_into_a_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVER_ONLY_SECRET", "must-not-be-imported")

    result, providers = await _import_env(
        tmp_path,
        monkeypatch,
        b"OPENAI_API_KEY=${SERVER_ONLY_SECRET}\nANTHROPIC_API_KEY=sk-ant\n",
    )

    assert result["imported_keys"] == ["ANTHROPIC_API_KEY"]
    assert [row["id"] for row in providers] == ["anthropic"]


@pytest.mark.asyncio
async def test_import_survives_bytes_that_are_not_utf8(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, providers = await _import_env(tmp_path, monkeypatch, b"# caf\xe9\nOPENAI_API_KEY=sk-ok\n")

    assert result["imported_keys"] == ["OPENAI_API_KEY"]
    assert providers[0]["apiKeys"][0]["key"] == "sk-ok"  # type: ignore[index]


@pytest.mark.asyncio
async def test_a_google_key_fills_the_gemini_provider_the_settings_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, providers = await _import_env(tmp_path, monkeypatch, b"GOOGLE_API_KEY=ai-studio-key\n")

    assert result["imported_keys"] == ["GOOGLE_API_KEY"]
    assert (providers[0]["id"], providers[0]["routingProfile"], providers[0]["name"]) == (
        "gemini",
        "gemini",
        "Google Gemini",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("variable", "provider_id"),
    [
        ("GLM_API_KEY", "zai"),
        ("KIMI_API_KEY", "moonshot"),
        ("XIAOMI_API_KEY", "xiaomi_mimo"),
        ("FIREWORKS_API_KEY", "fireworks_ai"),
    ],
)
async def test_variables_other_assistants_use_reach_the_provider_they_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variable: str, provider_id: str
) -> None:
    result, providers = await _import_env(tmp_path, monkeypatch, f"{variable}=key-1\n".encode())

    assert result["imported_keys"] == [variable]
    assert providers[0]["id"] == provider_id
    assert providers[0]["routingProfile"] == provider_id


@pytest.mark.asyncio
@pytest.mark.parametrize("variable", ["AZURE_API_KEY", "AWS_BEARER_TOKEN_BEDROCK", "NVIDIA_API_KEY", "OPENCODE_GO_API_KEY"])
async def test_a_key_that_needs_an_endpoint_the_dotenv_lacks_is_not_imported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    result, providers = await _import_env(tmp_path, monkeypatch, f"{variable}=key-1\n".encode())

    assert result["imported_keys"] == []
    assert providers == []
