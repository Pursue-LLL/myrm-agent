"""Tests for the opt-in key import: which providers it creates, which keys it reports as left alone, and how."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.schemas.config import ConfigRecord
from app.services.migration.source.source_secrets_importer import (
    SecretsImportResult,
    SkippedKey,
    import_external_source_secrets,
)

_PREFIX = "app.services.migration.source.source_secrets_importer"


def _providers_record(value: dict[str, object], *, unreadable: bool = False) -> ConfigRecord:
    """The stored ``providers`` row as the config service returns it."""
    return ConfigRecord(
        key="providers",
        value=value,
        version="v1",
        updatedAt="2026-01-01T00:00:00",
        deviceId="web",
        unreadable=unreadable,
    )


@dataclass
class _Run:
    """One import: its result, the provider rows it wrote (empty when it wrote nothing) and how it wrote them."""

    result: SecretsImportResult
    providers: list[dict[str, object]]
    writes: int
    expected_version: str | None


async def _import_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_bytes: bytes,
    existing: list[dict[str, object]] | None = None,
) -> _Run:
    """Import ``env_bytes`` as a ``.env`` into an empty providers config, or into ``existing`` provider rows."""
    root = tmp_path / ".hermes"
    root.mkdir()
    (root / ".env").write_bytes(env_bytes)
    written: list[dict[str, object]] = []
    versions: list[str | None] = []
    record = None if existing is None else _providers_record({"providers": existing})

    async def fake_get(key: str) -> ConfigRecord | None:
        assert key == "providers"
        return record

    async def fake_set(key: str, value: dict[str, object], *, device_id: str, expected_version: str | None) -> None:
        assert key == "providers"
        assert device_id == "competitor-migration"
        written.append(value)
        versions.append(expected_version)

    monkeypatch.setattr(f"{_PREFIX}.is_local_mode", lambda: True)
    monkeypatch.setattr(f"{_PREFIX}.config_service.get", fake_get)
    monkeypatch.setattr(f"{_PREFIX}.config_service.set", fake_set)

    result = await import_external_source_secrets(root)
    rows = written[-1]["providers"] if written else []
    assert isinstance(rows, list)
    return _Run(result, rows, len(written), versions[-1] if versions else None)


def _first_key(row: dict[str, object]) -> str:
    api_keys = row["apiKeys"]
    assert isinstance(api_keys, list)
    return str(api_keys[0]["key"])


@pytest.mark.asyncio
async def test_import_secrets_seeds_providers_when_list_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = await _import_env(tmp_path, monkeypatch, b"OPENAI_API_KEY=sk-test\n")

    assert run.result.imported_keys == ["OPENAI_API_KEY"]
    assert [row["id"] for row in run.providers] == ["openai"]
    assert run.expected_version is None


@pytest.mark.asyncio
async def test_import_ai_gateway_api_key_seeds_vercel_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = await _import_env(tmp_path, monkeypatch, b"AI_GATEWAY_API_KEY=vca_test_secret_123\n")

    assert run.result.imported_keys == ["AI_GATEWAY_API_KEY"]
    assert len(run.providers) == 1
    row = run.providers[0]
    assert row["id"] == "vercel_ai_gateway"
    assert row["name"] == "Vercel AI Gateway"
    assert row["routingProfile"] == "openai"
    assert row["apiUrl"] == "https://ai-gateway.vercel.sh/v1"
    assert _first_key(row) == "vca_test_secret_123"


@pytest.mark.asyncio
async def test_import_vercel_ai_gateway_key_seeds_vercel_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = await _import_env(tmp_path, monkeypatch, b"VERCEL_AI_GATEWAY_KEY=vck_prod_secret_456\n")

    assert run.result.imported_keys == ["VERCEL_AI_GATEWAY_KEY"]
    assert [row["id"] for row in run.providers] == ["vercel_ai_gateway"]
    assert _first_key(run.providers[0]) == "vck_prod_secret_456"


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

    run = await _import_env(tmp_path, monkeypatch, env)

    assert run.result.imported_keys == ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY"]
    assert {row["id"]: _first_key(row) for row in run.providers} == {
        "openai": "sk-quoted",
        "anthropic": "sk-ant-single",
        "groq": "gsk-spaced",
        "deepseek": "sk-deep",
    }


@pytest.mark.asyncio
async def test_import_never_reads_this_process_environment_into_a_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVER_ONLY_SECRET", "must-not-be-imported")

    run = await _import_env(
        tmp_path,
        monkeypatch,
        b"OPENAI_API_KEY=${SERVER_ONLY_SECRET}\nANTHROPIC_API_KEY=sk-ant\n",
    )

    assert run.result.imported_keys == ["ANTHROPIC_API_KEY"]
    assert [row["id"] for row in run.providers] == ["anthropic"]


@pytest.mark.asyncio
async def test_import_survives_bytes_that_are_not_utf8(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = await _import_env(tmp_path, monkeypatch, b"# caf\xe9\nOPENAI_API_KEY=sk-ok\n")

    assert run.result.imported_keys == ["OPENAI_API_KEY"]
    assert _first_key(run.providers[0]) == "sk-ok"


@pytest.mark.asyncio
async def test_a_google_key_fills_the_gemini_provider_the_settings_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = await _import_env(tmp_path, monkeypatch, b"GOOGLE_API_KEY=ai-studio-key\n")

    assert run.result.imported_keys == ["GOOGLE_API_KEY"]
    assert (run.providers[0]["id"], run.providers[0]["routingProfile"], run.providers[0]["name"]) == (
        "gemini",
        "gemini",
        "Google Gemini",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("variable", "provider_id"),
    [
        ("FIREWORKS_API_KEY", "fireworks_ai"),
        ("TOGETHER_API_KEY", "together_ai"),
    ],
)
async def test_variables_of_a_provider_a_key_alone_makes_usable_create_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variable: str, provider_id: str
) -> None:
    run = await _import_env(tmp_path, monkeypatch, f"{variable}=key-1\n".encode())

    assert run.result.imported_keys == [variable]
    assert run.providers[0]["id"] == provider_id
    assert run.providers[0]["routingProfile"] == provider_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "variable",
    [
        "GLM_API_KEY",
        "ZAI_API_KEY",
        "KIMI_API_KEY",
        "MOONSHOT_API_KEY",
        "DASHSCOPE_API_KEY",
        "MINIMAX_API_KEY",
        "XIAOMI_API_KEY",
        "XIAOMI_MIMO_API_KEY",
    ],
)
async def test_a_provider_with_regional_endpoints_is_not_created_from_a_key_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    # Which endpoint such a key belongs to is not in the .env, and a row at the wrong one fails on its first call.
    run = await _import_env(tmp_path, monkeypatch, f"{variable}=key-1\n".encode())

    assert run.result.imported_keys == []
    assert run.result.skipped_keys == [SkippedKey(variable, "needs_endpoint")]
    assert run.writes == 0


@pytest.mark.asyncio
async def test_a_regional_provider_the_user_already_set_up_receives_its_key_and_keeps_its_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    zai = {"id": "zai", "routingProfile": "zai", "apiUrl": "https://api.z.ai/api/paas/v4", "apiKeys": []}

    run = await _import_env(tmp_path, monkeypatch, b"GLM_API_KEY=glm-key\n", existing=[zai])

    assert run.result.imported_keys == ["GLM_API_KEY"]
    assert run.result.skipped_keys == []
    assert [row["id"] for row in run.providers] == ["zai"]
    assert run.providers[0]["apiUrl"] == "https://api.z.ai/api/paas/v4"
    assert _first_key(run.providers[0]) == "glm-key"
    assert run.expected_version == "v1"


@pytest.mark.asyncio
async def test_a_row_the_user_routes_through_a_provider_receives_its_key_and_no_second_row_appears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = {"id": "my-proxy", "routingProfile": "openai", "apiUrl": "https://gw.example/v1", "apiKeys": []}

    run = await _import_env(tmp_path, monkeypatch, b"OPENAI_API_KEY=sk-new\n", existing=[proxy])

    assert [row["id"] for row in run.providers] == ["my-proxy"]
    assert _first_key(run.providers[0]) == "sk-new"


@pytest.mark.asyncio
@pytest.mark.parametrize("variable", ["AZURE_API_KEY", "AWS_BEARER_TOKEN_BEDROCK", "NVIDIA_API_KEY", "OPENCODE_GO_API_KEY"])
async def test_a_key_the_import_has_no_provider_for_is_reported_and_nothing_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    run = await _import_env(tmp_path, monkeypatch, f"{variable}=key-1\n".encode())

    assert run.result.imported_keys == []
    assert run.result.skipped_keys == [SkippedKey(variable, "unsupported")]
    assert run.writes == 0


@pytest.mark.asyncio
async def test_every_key_left_alone_is_listed_by_name_and_never_by_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = (
        b"OPENAI_API_KEY=sk-imported\nGLM_API_KEY=glm-secret-111\nNVIDIA_API_KEY=nv-secret-222\nTAVILY_API_KEY=tvly-secret-333\n"
    )

    run = await _import_env(tmp_path, monkeypatch, env)

    assert run.result.imported_keys == ["OPENAI_API_KEY"]
    assert run.result.skipped_keys == [
        SkippedKey("GLM_API_KEY", "needs_endpoint"),
        SkippedKey("NVIDIA_API_KEY", "unsupported"),
        SkippedKey("TAVILY_API_KEY", "unsupported"),
    ]
    assert [row["id"] for row in run.providers] == ["openai"]
    assert not any(secret in repr(run.result) for secret in ("glm-secret-111", "nv-secret-222", "tvly-secret-333"))


@pytest.mark.asyncio
async def test_a_dotenv_without_importable_keys_still_reports_the_keys_it_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = await _import_env(tmp_path, monkeypatch, b"EXA_API_KEY=exa-key\nRANDOM_VAR=1\n")

    assert run.result == SecretsImportResult(imported_keys=[], skipped_keys=[SkippedKey("EXA_API_KEY", "unsupported")])
    assert run.writes == 0


@pytest.mark.asyncio
async def test_a_missing_dotenv_imports_and_reports_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / ".hermes"
    root.mkdir()
    monkeypatch.setattr(f"{_PREFIX}.is_local_mode", lambda: True)

    assert await import_external_source_secrets(root) == SecretsImportResult(imported_keys=[], skipped_keys=[])


@pytest.mark.asyncio
async def test_a_providers_config_that_is_not_an_object_fails_the_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / ".hermes"
    root.mkdir()
    (root / ".env").write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")

    async def fake_get(key: str) -> MagicMock:
        # A list is not a value the typed record can hold, so this one shape needs a stand-in.
        return MagicMock(version="v1", value=["not", "an", "object"], unreadable=False)

    monkeypatch.setattr(f"{_PREFIX}.is_local_mode", lambda: True)
    monkeypatch.setattr(f"{_PREFIX}.config_service.get", fake_get)

    with pytest.raises(ValueError, match="Providers config is not an object"):
        await import_external_source_secrets(root)


@pytest.mark.asyncio
async def test_providers_sealed_under_a_lost_key_fail_the_import_without_a_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / ".hermes"
    root.mkdir()
    (root / ".env").write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
    writes: list[dict[str, object]] = []

    async def fake_get(key: str) -> ConfigRecord:
        return _providers_record({}, unreadable=True)

    async def fake_set(key: str, value: dict[str, object], *, device_id: str, expected_version: str | None) -> None:
        writes.append(value)

    monkeypatch.setattr(f"{_PREFIX}.is_local_mode", lambda: True)
    monkeypatch.setattr(f"{_PREFIX}.config_service.get", fake_get)
    monkeypatch.setattr(f"{_PREFIX}.config_service.set", fake_set)

    with pytest.raises(ValueError, match="cannot be decrypted"):
        await import_external_source_secrets(root)

    assert writes == []


@pytest.mark.asyncio
async def test_the_import_is_refused_outside_local_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(f"{_PREFIX}.is_local_mode", lambda: False)

    with pytest.raises(ValueError, match="local or Tauri"):
        await import_external_source_secrets(tmp_path)
