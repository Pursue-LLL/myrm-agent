"""Execution claims: a finished answer that says what the run did must be backed by what the run did.

[INPUT]
- .verifier::check_execution_claim, has_completion_claim (POS: ground verification, outbound-action and code-change claims in this run's tool records)
- .lexicon (POS: the claim, exclusion, intent and evidence-shape patterns the verifier reads)

[OUTPUT]
- check_execution_claim, has_completion_claim

[POS]
Public surface of the execution-claim package, consulted by the completion guard and by the disclosure policy.
"""

from myrm_agent_harness.agent.middlewares.completion.execution_claim.verifier import (
    check_execution_claim,
    has_completion_claim,
)

__all__ = ["check_execution_claim", "has_completion_claim"]
