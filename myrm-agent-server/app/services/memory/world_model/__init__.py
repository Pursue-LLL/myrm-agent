"""Package entrypoint for L3 World Model macro memory service.

[POS]
app/services/memory/world_model/__init__.py
Exposes the singleton L3WorldModelService and factory provider.

[INPUT]
- .service: L3WorldModelService, get_world_model_service
- .probe: ProjectEnvironmentProbe

[OUTPUT]
- L3WorldModelService, get_world_model_service, ProjectEnvironmentProbe
"""

from __future__ import annotations

from app.services.memory.world_model.probe import ProjectEnvironmentProbe
from app.services.memory.world_model.service import (
    L3WorldModelService,
    get_world_model_service,
)

__all__ = [
    "L3WorldModelService",
    "ProjectEnvironmentProbe",
    "get_world_model_service",
]
