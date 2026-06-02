import io

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.files.storage import router as storage_router
from app.api.files.upload import router as upload_router
from app.database.connection import get_db
from app.database.models import Base
from app.middleware.max_body_size import MaxBodySizeMiddleware


@pytest_asyncio.fixture
async def _upload_db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:testdb_upload_e2e?mode=memory&cache=shared&uri=true"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def client(_upload_db_session: AsyncSession):
    test_app = FastAPI()
    test_app.include_router(upload_router, prefix="/api/v1/files")
    test_app.include_router(storage_router, prefix="/api/v1/files/storage")
    test_app.add_middleware(MaxBodySizeMiddleware, max_size=15 * 1024 * 1024)

    async def override_get_db():
        yield _upload_db_session

    test_app.dependency_overrides[get_db] = override_get_db
    with TestClient(test_app) as test_client:
        yield test_client

def create_test_image(width: int, height: int, format: str = "JPEG") -> bytes:
    img = Image.new("RGB", (width, height), color="blue")
    buffer = io.BytesIO()
    img.save(buffer, format=format)
    return buffer.getvalue()

def test_upload_large_image_downsampling(client):
    # Create a 4000x4000 image
    img_bytes = create_test_image(4000, 4000, "JPEG")

    # Upload the image
    response = client.post(
        "/api/v1/files/upload",
        files={"files": ("large_test.jpg", img_bytes, "image/jpeg")}
    )

    assert response.status_code == 200
    data = response.json()
    print("Response data:", data)
    assert data["success"] is True
    
    files_data = data["data"]
    assert files_data["uploaded_count"] == 1
    
    file_info = files_data["files"][0]
    file_url = file_info["file_url"]
    
    # Now download the file and check its dimensions
    # The URL is an absolute URL, we need to extract the path
    # e.g. http://testserver/api/v1/files/storage/files/{id}/content
    path = file_url.replace("http://testserver", "")
    
    download_response = client.get(path)
    assert download_response.status_code == 200
    
    # Verify dimensions
    downloaded_img = Image.open(io.BytesIO(download_response.content))
    assert downloaded_img.size == (2048, 2048)

def test_upload_small_image_no_downsampling(client):
    # Create a 800x800 image
    img_bytes = create_test_image(800, 800, "PNG")

    # Upload the image
    response = client.post(
        "/api/v1/files/upload",
        files={"files": ("small_test.png", img_bytes, "image/png")}
    )

    assert response.status_code == 200
    data = response.json()
    print("Response data:", data)
    assert data["success"] is True
    
    files_data = data["data"]
    assert files_data["uploaded_count"] == 1
    
    file_info = files_data["files"][0]
    file_url = file_info["file_url"]
    
    path = file_url.replace("http://testserver", "")
    
    download_response = client.get(path)
    assert download_response.status_code == 200
    
    # Verify dimensions
    downloaded_img = Image.open(io.BytesIO(download_response.content))
    assert downloaded_img.size == (800, 800)

def test_upload_exceeds_max_body_size(client):
    # Create a 16MB payload (exceeds the 15MB limit)
    # We use a simple text file to test the raw body size limit
    large_payload = b"a" * (16 * 1024 * 1024)
    
    response = client.post(
        "/api/v1/files/upload",
        files={"files": ("huge_test.txt", large_payload, "text/plain")}
    )
    
    assert response.status_code == 413
    data = response.json()
    assert "Payload Too Large" in data.get("detail", "")

