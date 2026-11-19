"""One .env, three readers: the migration preview, the payload's key names and the import agree on what a key is."""

from __future__ import annotations

from pathlib import Path

from app.services.migration._loader_utils import extract_env_key_names
from app.services.migration.env_secrets import IMPORTABLE_PROVIDERS, MULTI_ENDPOINT_PROVIDERS, read_env_keys
from app.services.migration.source.source_discovery import _detect_api_keys_in_env

# Written the way competitors write them: an ``export`` prefix, a quoted value with a trailing comment, an alias of
# the transport's own variable, a blank value, an unresolved reference, and a variable that is no provider key.
_COMPETITOR_ENV = (
    "export GLM_API_KEY=glm-key\n"
    'KIMI_API_KEY="kimi-key"  # my kimi\n'
    "OPENAI_API_KEY=\n"
    "ANTHROPIC_API_KEY=${SERVER_ONLY_SECRET}\n"
    "RANDOM_VAR=1\n"
)
# Keys the import leaves alone: a provider that needs more than a key, a tool's key, and one the transport names by a
# token variable; blank and unresolved values are no keys, and a bot token is no API key.
_UNSUPPORTED_ENV = (
    "OPENAI_API_KEY=sk-ok\n"
    "NVIDIA_API_KEY=nv-key\n"
    "export TAVILY_API_KEY=tvly-key\n"
    "AWS_BEARER_TOKEN_BEDROCK=bedrock-key\n"
    "COHERE_API_KEY=\n"
    "EXA_API_KEY=${SERVER_ONLY_SECRET}\n"
    "TELEGRAM_BOT_TOKEN=123:abc\n"
)


def _env_file(tmp_path: Path, content: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(content, encoding="utf-8")
    return path


def test_the_import_reads_the_keys_a_competitor_writes(tmp_path: Path) -> None:
    assert read_env_keys(_env_file(tmp_path, _COMPETITOR_ENV)).importable == {
        "GLM_API_KEY": "glm-key",
        "KIMI_API_KEY": "kimi-key",
    }


def test_the_names_of_keys_the_import_leaves_alone_are_listed_in_file_order(tmp_path: Path) -> None:
    keys = read_env_keys(_env_file(tmp_path, _UNSUPPORTED_ENV))

    assert keys.importable == {"OPENAI_API_KEY": "sk-ok"}
    assert keys.unsupported == ("NVIDIA_API_KEY", "TAVILY_API_KEY", "AWS_BEARER_TOKEN_BEDROCK")


def test_the_payload_names_exactly_the_keys_the_import_reads(tmp_path: Path) -> None:
    path = _env_file(tmp_path, _COMPETITOR_ENV)

    assert [item["name"] for item in extract_env_key_names(path)] == list(read_env_keys(path).importable)


def test_the_payload_marks_the_names_it_takes_from_the_dotenv(tmp_path: Path) -> None:
    items = extract_env_key_names(_env_file(tmp_path, _COMPETITOR_ENV))

    assert {item["source"] for item in items} == {"env"}


def test_the_preview_announces_keys_only_when_the_import_has_some(tmp_path: Path) -> None:
    assert _detect_api_keys_in_env(_env_file(tmp_path, "export GLM_API_KEY=glm-key\n")) is True
    assert _detect_api_keys_in_env(_env_file(tmp_path, "OPENAI_API_KEY=\nANTHROPIC_API_KEY=${X}\nRANDOM_VAR=1\n")) is False
    assert _detect_api_keys_in_env(_env_file(tmp_path, "NVIDIA_API_KEY=nv-key\n")) is False


def test_a_missing_file_holds_no_keys(tmp_path: Path) -> None:
    missing = tmp_path / "absent.env"

    keys = read_env_keys(missing)
    assert keys.importable == {}
    assert keys.unsupported == ()
    assert extract_env_key_names(missing) == []
    assert _detect_api_keys_in_env(missing) is False


def test_the_providers_that_need_an_endpoint_choice_are_providers_the_import_knows() -> None:
    assert MULTI_ENDPOINT_PROVIDERS <= set(IMPORTABLE_PROVIDERS)
