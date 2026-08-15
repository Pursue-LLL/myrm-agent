"""Static contract guards for local-only E2E seed routes under app/api."""

from __future__ import annotations

from pathlib import Path

_FORBIDDEN_SNIPPETS = (
    "get_memory_manager(",
    "get_crud_memory_manager(",
    "Depends(get_memory_manager",
    "Depends(get_crud_memory_manager",
)


def _api_root() -> Path:
    return Path(__file__).resolve().parents[3] / "app" / "api"


def _fixture_paths() -> list[Path]:
    """All seed-fixture modules under app/api, either single-file or subpackage style."""
    api_root = _api_root()
    return sorted(
        path
        for path in api_root.rglob("*.py")
        if path.name.startswith("test_fixtures") or "test_fixtures" in path.parts
    )


def test_test_fixtures_do_not_call_fastapi_memory_depends_directly() -> None:
    """Seed fixtures must not invoke FastAPI Depends callables (returns coroutine/misbound)."""
    violations: list[str] = []
    for path in _fixture_paths():
        text = path.read_text(encoding="utf-8")
        for snippet in _FORBIDDEN_SNIPPETS:
            if snippet in text:
                violations.append(f"{path.relative_to(_api_root().parent.parent)}: {snippet}")
    assert not violations, "Forbidden FastAPI memory Depends usage in test fixtures:\n" + "\n".join(
        violations
    )
