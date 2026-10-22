"""[INPUT]
- .service: CommandMatrixService
- .registry: SYSTEM_COMMAND_MATRIX

[OUTPUT]
- CommandMatrixService, SYSTEM_COMMAND_MATRIX facade

[POS]
Server-side business service facade for Item 38 P0.
"""

from .registry import SYSTEM_COMMAND_MATRIX
from .service import CommandMatrixService

__all__ = ["CommandMatrixService", "SYSTEM_COMMAND_MATRIX"]
