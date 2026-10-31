"""Backend cold-start budget: CPU and module-count limits measured on the real app.

[INPUT]
  startup_budget.cli::main (POS: entry point; the gate and its stub-pricing companion)
  startup_budget.runner (POS: process boundary, cold child interpreters), startup_budget.probe
  (POS: child process, one cold measurement), startup_budget.budget (POS: pure policy)

[OUTPUT]
  python -m startup_budget check|measure

[POS]
  Package facade; callers import submodules explicitly.
"""
