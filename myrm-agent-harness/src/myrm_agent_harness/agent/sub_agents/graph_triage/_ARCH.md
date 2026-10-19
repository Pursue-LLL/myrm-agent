# graph_triage/

## Overview

Applicability triage for graph execution. Classifies a task before it enters a graph, caps
the spend a graph run may consume, and reduces concurrency elastically when the budget
starts running out.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports the gate, budget guard, reducer and models. | — |
| triage_gate.py | Core | `GraphApplicabilityTriageGate` — decides whether a task belongs in a graph at all. | — |
| budget_guard.py | Core | `PredictiveBudgetGuard` — projects spend and stops a run before it exceeds the cap. | — |
| elastic_reducer.py | Core | `ElasticConcurrencyReducer` — lowers parallelism as budget pressure rises. | — |
| types.py | Core | `TaskComplexityCategory`, `GraphTriageDecision`, `TriageFeatureVector`, `BudgetCapConfig`, `BudgetStatus`, `ExecutionSpendState`, `PartialNodeOutput`, `PartialReduceReport`, `TriageVerdict`. | — |

## Key Dependencies

- `pydantic` (models)

## Key Design Decisions

- **Triage precedes execution**: the gate runs before any node starts, so an unsuitable task
  never pays the graph's setup cost.
- **Budget is predicted, not only measured**: the guard projects remaining spend so it can stop
  a run while there is still budget left to report a useful partial result.
- **Partial output is a first-class type**: `PartialNodeOutput` / `PartialReduceReport` carry what
  a cut-short run produced instead of discarding it.
