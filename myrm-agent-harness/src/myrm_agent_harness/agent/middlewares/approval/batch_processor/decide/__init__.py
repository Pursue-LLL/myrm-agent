"""[INPUT]
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.loop::evaluate_calls (POS: The per-call decision loop of batch_processor.)

[OUTPUT]
- evaluate_calls: sort every tool call of a batch into approved, denied or pending

[POS]
Facade of the decision stages of `batch_processor`; `core.evaluate_tool_batch` is the only caller.
"""

from myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.loop import evaluate_calls

__all__ = ["evaluate_calls"]
