"""
[INPUT]
app.api.spreadsheet.routes::router

[OUTPUT]
router: FastAPI APIRouter for spreadsheet endpoints

[POS]
Package init for spreadsheet API subpackage.
"""

from app.api.spreadsheet.routes import router

__all__ = ["router"]
