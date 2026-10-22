"""[INPUT]
- .service: SwarmExecutionService

[OUTPUT]
- SwarmExecutionService

[POS]
Facade for SwarmExecutionService in app.services.swarm.
"""

from .service import SwarmExecutionService

__all__ = ["SwarmExecutionService"]
