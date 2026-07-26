"""Shared verify-api base resolver for live integration tests.

[INPUT]
- e2e_api_verify::resolve_e2e_api_context (POS: epoch-matched verify-api routing SSOT)
- verify_backend_seed::ensure_verify_backend_seed (POS: on-demand backend-only isolated spawn)

[OUTPUT]
- resolve_verify_api_base(): loopback API base for live server-route pytest (parallel-safe)

[POS]
Server test support. Centralizes verify-api private backend resolution for live integration
suites; avoids duplicated sys.path bootstrap in each integration module.
"""

from __future__ import annotations

import sys
from pathlib import Path

_DEV_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_DEV_LIB) not in sys.path:
    sys.path.insert(0, str(_DEV_LIB))


def resolve_verify_api_base(*, ensure_backend: bool = True) -> str:
    """Return loopback API base for live server-route tests (parallel-safe, not shared :8080)."""
    import pytest
    from e2e_api_verify import monorepo_root, resolve_e2e_api_context  # noqa: PLC0415
    from verify_backend_seed import ensure_verify_backend_seed  # noqa: PLC0415

    ctx = resolve_e2e_api_context()
    if ctx.blocked and ensure_backend:
        seed = ensure_verify_backend_seed(monorepo=monorepo_root())
        if not seed.ok:
            pytest.skip(f"verify-api seed failed: {seed.detail}")
        ctx = resolve_e2e_api_context(retry_after_apply=False)
    if ctx.blocked:
        pytest.skip(f"verify-api blocked: {ctx.blocked_reason}")
    return ctx.verify_api_base.rstrip("/")
