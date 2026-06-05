"""Test sandbox configuration and path setup."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.config.settings import AppSettings, DatabaseSettings


def test_myrm_data_dir_env():
    """Test that MYRM_DATA_DIR environment variable is correctly used."""
    # Save original value
    original_value = os.environ.get("MYRM_DATA_DIR")

    try:
        # Set a custom value
        test_path = "/test/custom/workspace"
        os.environ["MYRM_DATA_DIR"] = test_path

        # Reload settings
        db_settings = DatabaseSettings()

        # Verify the data directory is set correctly
        assert db_settings.state_dir.startswith(test_path) or db_settings.state_dir == test_path
    finally:
        # Restore original value
        if original_value is not None:
            os.environ["MYRM_DATA_DIR"] = original_value
        else:
            os.environ.pop("MYRM_DATA_DIR", None)


def test_default_data_dir():
    """Test default data directory when MYRM_DATA_DIR is not set."""
    # Remove the environment variable
    original_value = os.environ.pop("MYRM_DATA_DIR", None)

    try:
        db_settings = DatabaseSettings()

        # Default should be ~/.myrm
        expected_path = Path.home() / ".myrm"
        assert Path(db_settings.state_dir).expanduser().resolve() == expected_path.expanduser().resolve()
    finally:
        # Restore original value
        if original_value is not None:
            os.environ["MYRM_DATA_DIR"] = original_value


def test_sqlite_path_within_data_dir():
    """Test that SQLite database path is within the data directory."""
    db_settings = DatabaseSettings()

    # SQLite path should be relative to workspace dir
    actual_path = db_settings.sqlite_path.replace("sqlite+aiosqlite:///", "/")
    assert Path(actual_path).parent == Path(db_settings.state_dir).expanduser().resolve()


def test_qdrant_path_within_data_dir():
    """Test that Qdrant storage path is within the data directory."""
    db_settings = DatabaseSettings()

    # Qdrant path should be relative to workspace dir
    expected_qdrant_path = str(Path(db_settings.state_dir).expanduser().resolve() / "qdrant")
    assert db_settings.qdrant_path == expected_qdrant_path


def test_no_user_id_in_settings():
    """Verify that AppSettings does not contain user_id related fields."""
    settings = AppSettings()

    # Ensure no user_id related attributes exist
    assert not hasattr(settings, "user_id")
    assert not hasattr(settings, "default_user_id")
    assert not hasattr(settings, "sandbox_user_id")


@pytest.mark.parametrize(
    "deploy_mode,expected_dir",
    [
        ("local", Path.home() / ".myrm"),
        ("tauri", Path.home() / ".myrm"),
        ("sandbox", Path("/workspace")),  # Docker override expected
    ],
)
def test_data_dir_by_deploy_mode(deploy_mode: str, expected_dir: Path):
    """Test data directory defaults for different deployment modes."""
    # Save original values
    original_mode = os.environ.get("DEPLOY_MODE")
    original_workspace = os.environ.get("MYRM_DATA_DIR")

    try:
        # Set deployment mode
        os.environ["DEPLOY_MODE"] = deploy_mode

        # For sandbox mode, we expect Docker to override with /workspace
        if deploy_mode == "sandbox":
            os.environ["MYRM_DATA_DIR"] = str(expected_dir)
        else:
            # Clear any override for local/tauri modes
            os.environ.pop("MYRM_DATA_DIR", None)

        db_settings = DatabaseSettings()

        # Verify the state directory matches expectations
        assert Path(db_settings.state_dir).expanduser().resolve() == expected_dir.expanduser().resolve()
    finally:
        # Restore original values
        if original_mode is not None:
            os.environ["DEPLOY_MODE"] = original_mode
        else:
            os.environ.pop("DEPLOY_MODE", None)

        if original_workspace is not None:
            os.environ["MYRM_DATA_DIR"] = original_workspace
        else:
            os.environ.pop("MYRM_DATA_DIR", None)
