"""Windows UI Automation pattern actions — toggle, expand/collapse and invoke on one element.

[INPUT]
- None (operates on the UIA control object handed in by windows_ax)

[OUTPUT]
- apply_uia_toggle: Idempotent check/uncheck via ToggleState; toggle always flips
- apply_uia_expand_collapse: ExpandCollapsePattern expand/collapse with Click fallback
- apply_uia_invoke: InvokePattern invoke with Click fallback

[POS]
Pattern-level element actions for Windows accessibility invocation. Each action prefers the
UIA pattern and falls back to a Click when the control does not expose it.
"""

from __future__ import annotations


def apply_uia_toggle(target: object, normalized: str, auto: object) -> None:
    """Apply toggle/check/uncheck via TogglePattern (Click fallback).

    ``check`` / ``uncheck`` are idempotent when ``ToggleState`` is readable:
    already-On + check and already-Off + uncheck are no-ops. Indeterminate
    may require a second Toggle to reach the requested side (MS cycle order).
    """
    get_pattern = getattr(target, "GetTogglePattern", None)
    pattern = None
    if callable(get_pattern):
        try:
            pattern = get_pattern()
        except Exception:
            pattern = None

    if pattern is None or not hasattr(pattern, "Toggle"):
        target.Click()  # type: ignore[attr-defined]
        return

    if normalized == "toggle":
        pattern.Toggle()
        return

    want_on = normalized == "check"
    on_val = 1
    off_val = 0
    state_enum = getattr(auto, "ToggleState", None)
    if state_enum is not None:
        if hasattr(state_enum, "On") and isinstance(state_enum.On, int):
            on_val = int(state_enum.On)
        if hasattr(state_enum, "Off") and isinstance(state_enum.Off, int):
            off_val = int(state_enum.Off)

    def _current_state() -> object | None:
        try:
            return getattr(pattern, "ToggleState", None)
        except Exception:
            return None

    current = _current_state()
    if want_on and current == on_val:
        return
    if not want_on and current == off_val:
        return

    pattern.Toggle()
    current = _current_state()
    if (want_on and current != on_val) or (not want_on and current != off_val):
        pattern.Toggle()


def apply_uia_expand_collapse(target: object, action: str) -> None:
    """Expand or collapse via ExpandCollapsePattern (Click fallback)."""
    get_pattern = getattr(target, "GetExpandCollapsePattern", None)
    pattern = None
    if callable(get_pattern):
        try:
            pattern = get_pattern()
        except Exception:
            pattern = None

    if pattern is not None:
        if action == "expand" and hasattr(pattern, "Expand"):
            pattern.Expand()
            return
        elif action == "collapse" and hasattr(pattern, "Collapse"):
            pattern.Collapse()
            return

    target.Click()  # type: ignore[attr-defined]


def apply_uia_invoke(target: object) -> None:
    """Invoke via InvokePattern (Click fallback)."""
    get_pattern = getattr(target, "GetInvokePattern", None)
    pattern = None
    if callable(get_pattern):
        try:
            pattern = get_pattern()
        except Exception:
            pattern = None

    if pattern is not None and hasattr(pattern, "Invoke"):
        pattern.Invoke()
        return

    target.Click()  # type: ignore[attr-defined]
