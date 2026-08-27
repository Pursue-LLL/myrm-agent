import io
import zipfile
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.system.router import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/system")
    return TestClient(app)


def test_export_support_debug_bundle_success(client):
    """Test successful export of redacted support debug zip bundle."""
    # Create a small valid test zip
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MANIFEST.json", '{"bundle_version": "1.0.0"}')
        zf.writestr("system_info.json", '{"platform": "Darwin"}')
        zf.writestr("doctor_health.json", '{"is_healthy": true}')

    fake_zip_bytes = zip_buf.getvalue()

    with patch(
        "app.services.system.support_bundle_service.SupportBundleService.build_bundle_zip",
        new_callable=AsyncMock,
    ) as mock_build:
        mock_build.return_value = fake_zip_bytes

        response = client.get("/api/v1/system/debug-bundle?include_traces=true&include_profiles=true")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "attachment; filename=" in response.headers.get("content-disposition", "")
        assert response.headers.get("x-bundle-version") == "1.0.0"

        # Verify zip structure
        downloaded_zip = zipfile.ZipFile(io.BytesIO(response.content))
        file_list = downloaded_zip.namelist()
        assert "MANIFEST.json" in file_list
        assert "system_info.json" in file_list
        assert "doctor_health.json" in file_list

        mock_build.assert_awaited_once_with(include_traces=True, include_profiles=True)


def test_export_support_debug_bundle_failure(client):
    """Test 500 error handling when bundle generation raises exception."""
    with patch(
        "app.services.system.support_bundle_service.SupportBundleService.build_bundle_zip",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Disk allocation failure"),
    ):
        response = client.get("/api/v1/system/debug-bundle")
        assert response.status_code == 500
        assert "Failed to generate support debug bundle" in response.json().get("detail", "")
