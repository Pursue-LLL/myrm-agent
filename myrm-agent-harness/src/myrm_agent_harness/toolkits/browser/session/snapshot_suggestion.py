"""Heuristic token / scope suggestions for large ARIA snapshots.

[INPUT]
- (none)

[OUTPUT]
- generate_snapshot_suggestion: Args:

[POS]
Heuristic token / scope suggestions for large ARIA snapshots.
"""


def generate_snapshot_suggestion(
    ref_count: int,
    estimated_tokens: int,
    current_scope: str,
    current_compact: bool,
    current_selector: str,
) -> str:
    """Generate a smart optimization suggestion.

    Args:
        ref_count: Current ref count.
        estimated_tokens: Estimated token count.
        current_scope: Current scope parameter.
        current_compact: Current compact parameter.
        current_selector: Current selector parameter.

    Returns:
        Suggestion string, or empty string when no suggestion applies.

    Note:
        Heuristic-based rules; finer-grained scoping can be combined with
        `browser_inspect` and `selector`.
    """
    if estimated_tokens > 2000 and not current_selector:
        return (
            f" Large page detected ({ref_count} refs, ~{estimated_tokens} tokens)\n"
            "→ Recommended: Use browser_inspect() to get a precise selector and snapshot only that region\n"
            "→ Quick fix: scope='interactive' or compact=True"
        )

    if ref_count > 200 and current_scope != "interactive":
        return (
            f" Many elements detected ({ref_count} refs, ~{estimated_tokens} tokens)\n"
            "→ Recommended: scope='interactive' (interactive elements only)\n"
            "→ Alternative: compact=True or use selector for specific region"
        )

    if ref_count > 200 and not current_compact:
        return " Optimization tip: compact=True renders a single-line format with fewer tokens"

    return ""
