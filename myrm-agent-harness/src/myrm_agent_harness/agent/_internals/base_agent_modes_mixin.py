"""BaseAgent consensus entrypoint.

[INPUT]
- toolkits.llms.consensus (POS: Mixture-of-Agents consensus engine)

[OUTPUT]
- run_consensus: Mixture-of-Agents consensus inference entrypoint

[POS]
Mixin: run_consensus on BaseAgent.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from langchain_core.language_models import BaseChatModel

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.llms.consensus.types import (
        ConsensusConfig,
        ConsensusResult,
    )
    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken


def _make_consensus_redactor() -> Callable[[str], str]:
    """Build the consensus privacy redactor from the agent security layer.

    Delayed imports keep this mixin free of the security stack until a
    privacy-filtered consensus run actually needs it.
    """
    from myrm_agent_harness.agent.security.detection.pii_redactor import redact_pii
    from myrm_agent_harness.agent.security.redact import redact_sensitive_text

    def redact(text: str) -> str:
        redacted = redact_sensitive_text(text)
        redacted, _ = redact_pii(redacted)
        return redacted

    return redact


class BaseAgentModesMixin:
    async def run_consensus(
        self,
        query: str,
        reference_llms: list[BaseChatModel] | None = None,
        aggregator_llm: BaseChatModel | None = None,
        config: ConsensusConfig | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> ConsensusResult:
        """Run Mixture-of-Agents consensus inference."""
        from myrm_agent_harness.toolkits.llms.consensus import (
            ConsensusConfig,
            ConsensusEngine,
        )

        cfg = config or ConsensusConfig()
        refs = reference_llms or [self.llm]
        agg = aggregator_llm or self.llm
        engine = ConsensusEngine(
            reference_llms=refs,
            aggregator_llm=agg,
            config=cfg,
            privacy_redactor=_make_consensus_redactor() if cfg.privacy_filter != "off" else None,
        )
        return await engine.run(query, system_prompt=self.system_prompt, cancel_token=cancel_token)
