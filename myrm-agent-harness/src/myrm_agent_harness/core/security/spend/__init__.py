"""Spend governance for agent commerce.

[INPUT]
- core.security.spend.spend_governor::SpendGovernor, SpendGovernorConfig, SpendLease, SpendLeaseResult,
  SpendCommitResult, SpendMetrics, SPEND_VOUCHER_PREFIX, SPEND_VOUCHER_SUFFIX, is_spend_voucher
  (POS: 确定性微额支出状态机与契约)

[OUTPUT]
- SpendGovernor, SpendGovernorConfig, SpendLease, SpendLeaseResult, SpendCommitResult, SpendMetrics
- SPEND_VOUCHER_PREFIX, SPEND_VOUCHER_SUFFIX, is_spend_voucher

[POS]
Public surface of the core spend package: the spend governor that gates agent purchases. Credentials
reach a child process only through the command-scoped environment of the executor, never through this package.
"""

from __future__ import annotations

from .spend_governor import (
    SPEND_VOUCHER_PREFIX,
    SPEND_VOUCHER_SUFFIX,
    SpendCommitResult,
    SpendGovernor,
    SpendGovernorConfig,
    SpendLease,
    SpendLeaseResult,
    SpendMetrics,
    is_spend_voucher,
)

__all__ = [
    "SPEND_VOUCHER_PREFIX",
    "SPEND_VOUCHER_SUFFIX",
    "SpendCommitResult",
    "SpendGovernor",
    "SpendGovernorConfig",
    "SpendLease",
    "SpendLeaseResult",
    "SpendMetrics",
    "is_spend_voucher",
]
