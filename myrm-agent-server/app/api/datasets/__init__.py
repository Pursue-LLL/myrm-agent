"""Dataset Export API — trajectory export to standard fine-tuning formats.

[INPUT]
- fastapi::APIRouter
- myrm_agent_harness.agent.event_log.dataset_export (POS: Dataset export pipeline)

[OUTPUT]
- router: dataset export HTTP endpoints

[POS]
Thin HTTP layer. All export logic delegated to harness dataset_export module.
"""

from .router import router

__all__ = ["router"]
