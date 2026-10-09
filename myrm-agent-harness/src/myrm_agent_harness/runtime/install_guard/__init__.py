"""Install guard — post-install verification CLI for the harness wheel.

[INPUT]
- install_guard.verify (POS: Post-install verification checks)

[OUTPUT]
- Console script ``verify-harness-distribution`` (via ``install_guard.verify:main``)

[POS]
Runtime domain for install readiness: confirms an installed harness is importable and its runtime dependencies work.
"""
