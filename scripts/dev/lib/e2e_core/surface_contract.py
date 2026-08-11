"""Shared E2E surface probe helpers (Dev Gate v2)."""

from __future__ import annotations

from dev_gate_contract import E2E_SURFACE_TESTIDS

__all__ = [
    "E2E_SURFACE_TESTIDS",
    "css_testid",
    "js_query_testid",
]


def css_testid(testid: str) -> str:
    if testid not in E2E_SURFACE_TESTIDS:
        raise ValueError(f"Unknown E2E surface testid: {testid}")
    return f'[data-testid="{testid}"]'


def js_query_testid(testid: str) -> str:
    selector = css_testid(testid)
    return f"document.querySelector({selector!r})"
