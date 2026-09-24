# commerce/

## Overview
Commerce domain services and session state isolation for transactional AI agents.

## File Index

| File | Role | Description |
|------|------|-------------|
| `__init__.py` | Package | Public export of session isolation components and gated services. |
| `session_state.py` | State Isolation | `ShoppingSessionState`, `MerchantSessionState`, and `CommerceSessionManager`. |
| `gates_service.py` | Transactional Gates | `GatedStorefrontService` coordinating OPTIONS_GATE, CAP_GOVERNANCE, and ID-only receipt fencing. |
| `cart_governance.py` | Cart Risk Control | `CartGovernanceService` coordinating options convergence and cart capacity limits. |
| `spending_ledger.py` | Audit & Ledger | `SpendingLedgerEntry` and `SpendingLedgerStore` providing persistent, tamper-evident spending audit records. |
| `budget_service.py` | Budget Governance | `CommerceBudgetService` orchestrating SpendGovernor state machine, budget limits, emergency freezes, and ledger entries. |

## Invariants
- **Role Crossover Prohibited**: A session ID registered for a consumer shopping flow cannot simultaneously operate as a merchant session, and vice versa.
- **Auditability**: All state modifications track `last_activity_at` in UTC.
- **Framework Protocol Binding**: Consumes `myrm_agent_harness.core.security.egress` and `myrm_agent_harness.backends.commerce` protocols directly.
- **Zero-Float Financial Safety**: All monetary values are managed strictly in USD Cents integer units.
