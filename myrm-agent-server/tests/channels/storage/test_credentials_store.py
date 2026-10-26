"""CredentialsStore keeps channel logins in the application state directory, wherever the server was launched."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.channels.storage import CredentialsStore


@pytest.fixture
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state"
    monkeypatch.setattr("app.config.settings.settings.database.state_dir", str(state))
    return state


async def test_default_store_lives_in_the_state_dir_not_the_working_directory(
    state_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launched_from = tmp_path / "launched-from"
    launched_from.mkdir()
    monkeypatch.chdir(launched_from)

    await CredentialsStore().save("wechat", {"bot_token": "tok"})

    assert (state_dir / "credentials.json").is_file()
    assert not any(launched_from.iterdir())


async def test_logins_survive_relaunching_from_another_directory(
    state_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    await CredentialsStore().save("wechat", {"bot_token": "tok"})

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert await CredentialsStore().get("wechat") == {"bot_token": "tok"}


async def test_explicit_storage_dir_wins(state_dir: Path, tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"

    store = CredentialsStore(storage_dir=explicit)
    await store.save("slack", {"token": "x"})

    assert (explicit / "credentials.json").is_file()
    assert not (state_dir / "credentials.json").exists()
    assert await store.list_channels() == ["slack"]
