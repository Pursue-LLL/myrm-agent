"""Hardware Cookbook endpoints of the integrations API.

[INPUT]
- app.api.integrations.hardware.cookbook::router (POS: hardware detection, model recommendations and local Ollama model management)

[OUTPUT]
- router: the hardware router the integrations router mounts under /hardware

[POS] app/api/integrations/hardware/__init__.py
"""

from app.api.integrations.hardware.cookbook import router

__all__ = ["router"]
