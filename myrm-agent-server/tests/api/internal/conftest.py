"""Fixtures shared by the agent audit pull tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from app.api.internal.agent_audit import router as agent_audit_router


@pytest.fixture
def audit_app() -> FastAPI:
    app = FastAPI()
    app.include_router(agent_audit_router)
    return app


@pytest.fixture
def event_log_dir(tmp_path: Path) -> Path:
    log_dir = tmp_path / "event_logs"
    log_dir.mkdir()
    return log_dir
