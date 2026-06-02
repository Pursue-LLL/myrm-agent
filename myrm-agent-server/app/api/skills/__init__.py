"""Skills management API module

Provides CRUD operations for skills, including:
- Prebuilt skills (system-provided)
- Pool skills (user-uploaded, shared)
- Local skills (local mode only)
- Skill packaging and upload
"""

from app.api.skills.router import router

__all__ = ["router"]
