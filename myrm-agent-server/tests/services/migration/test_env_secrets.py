"""One .env, three readers: the migration preview, the payload's key names and the import agree on what a key is."""

from __future__ import annotations

from pathlib import Path

from app.services.migration._loader_utils import extract_env_key_names
from app.services.migration.env_secrets import read_env_secrets
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


def _env_file(tmp_path: Path, content: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(content, encoding="utf-8")
    return path


def test_the_import_reads_the_keys_a_competitor_writes(tmp_path: Path) -> None:
    assert read_env_secrets(_env_file(tmp_path, _COMPETITOR_ENV)) == {
        "GLM_API_KEY": "glm-key",
        "KIMI_API_KEY": "kimi-key",
    }


def test_the_payload_names_exactly_the_keys_the_import_reads(tmp_path: Path) -> None:
    path = _env_file(tmp_path, _COMPETITOR_ENV)

    assert [item["name"] for item in extract_env_key_names(path)] == list(read_env_secrets(path))


def test_the_preview_announces_keys_only_when_the_import_has_some(tmp_path: Path) -> None:
    assert _detect_api_keys_in_env(_env_file(tmp_path, "export GLM_API_KEY=glm-key\n")) is True
    assert _detect_api_keys_in_env(_env_file(tmp_path, "OPENAI_API_KEY=\nANTHROPIC_API_KEY=${X}\nRANDOM_VAR=1\n")) is False


def test_a_missing_file_holds_no_keys(tmp_path: Path) -> None:
    missing = tmp_path / "absent.env"

    assert read_env_secrets(missing) == {}
    assert extract_env_key_names(missing) == []
    assert _detect_api_keys_in_env(missing) is False
