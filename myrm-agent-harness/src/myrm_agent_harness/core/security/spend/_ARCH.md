# core/security/spend/

## Overview
Spend governance for agent commerce: a pure, deterministic budget state machine that decides whether an agent purchase may proceed, with merchant allowlists, per-action and daily caps in integer USD cents, and atomic leases.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Public aggregation facade exposing `SpendGovernor`, `SpendGovernorConfig`, `SpendLease`, `SpendLeaseResult`, `SpendCommitResult`, `SpendMetrics` and the spend-voucher helpers. | — |
| `spend_contracts.py` | Core | Immutable data models and token primitives (`SpendGovernorConfig`, `SpendLease`, `SpendLeaseResult`, `SpendCommitResult`, `SpendMetrics`, `is_spend_voucher`) for zero-float commerce accounting. | ✅ |
| `spend_governor.py` | Core | Pure deterministic micro-spending state machine (`SpendGovernor`) enforcing merchant allowlists, per-action/daily caps in USD Cents, atomic leases, and voucher generation. | ✅ |

## Key Invariants

1. **Zero-Float Accounting**: All commerce spending operations enforce integer USD Cents calculations to eliminate floating point rounding errors.
2. **No Prompt Cache Impact**: Spend governance evaluates strictly in the interceptor layer outside LLM prompts.
3. **No Credential Handling**: Credentials are not tokenized or proxied here. They reach a command through the executor's command-scoped environment (`toolkits/code_execution/executors/local/_command_env.py`).
