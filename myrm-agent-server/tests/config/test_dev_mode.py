"""Test development mode features."""

import logging
import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config.env import is_debug_mode
from app.config.logging import configure_logging
from app.core.utils.errors import MyrmError, register_exception_handlers
from app.database.standard_responses import BusinessCode


def test_debug_mode_detection() -> None:
    """Test is_debug_mode() with various env values."""
    with patch.dict(os.environ, {"DEBUG": "true"}, clear=False):
        assert is_debug_mode() is True

    with patch.dict(os.environ, {"DEBUG": "1"}, clear=False):
        assert is_debug_mode() is True

    with patch.dict(os.environ, {"DEBUG": "yes"}, clear=False):
        assert is_debug_mode() is True

    with patch.dict(os.environ, {"DEBUG": "false"}, clear=False):
        assert is_debug_mode() is False

    with patch.dict(os.environ, {}, clear=True):
        assert is_debug_mode() is False


def test_logging_level_debug_mode() -> None:
    """Test logging level changes with DEBUG env var."""
    with patch.dict(os.environ, {"DEBUG": "true"}, clear=False):
        configure_logging()
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

    with patch.dict(os.environ, {"DEBUG": "false"}, clear=False):
        configure_logging()
        root_logger = logging.getLogger()
        assert root_logger.level == logging.WARNING


def test_error_traceback_in_debug_mode() -> None:
    """Test MyrmError returns traceback in debug mode."""
    with patch.dict(os.environ, {"DEBUG": "true"}, clear=False):
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/test-error")
        async def _trigger_error():
            raise MyrmError(
                code=BusinessCode.INTERNAL_ERROR,
                message="Test error",
            )

        client = TestClient(app)
        response = client.get("/test-error")
        assert response.status_code == 500
        body = response.json()
        assert "traceback" in body
        assert isinstance(body["traceback"], list)
        assert len(body["traceback"]) > 0

    with patch.dict(os.environ, {"DEBUG": "false"}, clear=False):
        app2 = FastAPI()
        register_exception_handlers(app2)

        @app2.get("/test-error")
        async def _trigger_error2():
            raise MyrmError(
                code=BusinessCode.INTERNAL_ERROR,
                message="Test error",
            )

        client2 = TestClient(app2)
        response = client2.get("/test-error")
        assert response.status_code == 500
        body = response.json()
        assert "traceback" not in body


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
