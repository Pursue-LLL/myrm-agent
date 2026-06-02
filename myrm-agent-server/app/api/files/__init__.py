"""Files management API module

Provides endpoints for:
- File upload (via FilesService + StorageProvider)
- File storage management (list, download, delete)
- PDF content extraction
- Local file actions (reveal in file manager, open with default app)
"""

from app.api.files.local_actions import router as local_actions_router
from app.api.files.pdf_extract import router as pdf_extract_router
from app.api.files.storage import router as storage_router
from app.api.files.upload import router as upload_router

__all__ = ["upload_router", "storage_router", "pdf_extract_router", "local_actions_router"]
