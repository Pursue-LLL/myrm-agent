"""Fuzzy tool name auto-repair.

Resolves model hallucinated typos, case discrepancies and invented name suffixes often emitted by
open-weights models or proxy gateways, so the call reaches the registered tool instead of failing.

[INPUT]
- __future__
- difflib

[OUTPUT]
- ToolNameFuzzyRepairer: Performs exact, canonical, alias, suffix-strip and fuzzy distance name repair.

[POS]
Fuzzy tool name auto-repair.
"""

from __future__ import annotations

import difflib

# Suffixes a model tends to append to a real tool name when it guesses the implementation naming
# instead of the registered one. Ordered longest-first so "_tool_call" wins over "_call"/"_tool".
_HALLUCINATED_NAME_SUFFIXES: tuple[str, ...] = (
    "_tool_call",
    "_call_tool",
    "_function",
    "_tool",
)


class ToolNameFuzzyRepairer:
    """Repairs common tool name hallucinations and typos within safe similarity thresholds."""

    def __init__(
        self,
        alias_map: dict[str, str] | None = None,
        similarity_threshold: float = 0.82,
    ) -> None:
        self.alias_map: dict[str, str] = dict(alias_map) if alias_map else {}
        self.similarity_threshold: float = max(0.5, min(1.0, similarity_threshold))

    @staticmethod
    def _normalize_identifier(name: str) -> str:
        """Strip punctuation and normalize casing to snake-case style for heuristic comparison."""
        return name.lower().replace("-", "_").replace(" ", "_").strip()

    def repair_name(self, raw_name: str, valid_names: set[str]) -> str | None:
        """Attempt to repair a raw tool name against the set of registered valid names.

        Returns:
            The canonical tool name if safely repairable; None if ambiguous or unknown.
        """
        # 1. Exact match
        if raw_name in valid_names:
            return raw_name

        # 2. Explicit alias dictionary
        if raw_name in self.alias_map:
            target = self.alias_map[raw_name]
            if target in valid_names:
                return target

        # 3. Normalized case-insensitive / separator matching
        raw_norm = self._normalize_identifier(raw_name)
        norm_to_valid = {self._normalize_identifier(v): v for v in valid_names}
        if raw_norm in norm_to_valid:
            return norm_to_valid[raw_norm]

        # 4. Suffix strip: the model invents an implementation-ish suffix for a real tool
        # ("todo_write_tool" for "todo_write"). The extra word dilutes the fuzzy ratio below the
        # threshold (0.76 vs 0.82 for that pair), so the exact suffix rule runs first: it can only
        # match a registered tool name, so it never repairs a call to the wrong tool.
        for suffix in _HALLUCINATED_NAME_SUFFIXES:
            if raw_name.endswith(suffix):
                candidate = raw_name[: -len(suffix)]
                if candidate in valid_names:
                    return candidate

        # 5. Fuzzy SequenceMatcher comparison
        best_candidate: str | None = None
        best_ratio: float = 0.0

        for valid in valid_names:
            valid_norm = self._normalize_identifier(valid)
            ratio = difflib.SequenceMatcher(None, raw_norm, valid_norm).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_candidate = valid

        if best_ratio >= self.similarity_threshold and best_candidate is not None:
            return best_candidate

        return None
