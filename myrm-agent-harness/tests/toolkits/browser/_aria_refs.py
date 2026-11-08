"""Ref id extraction from rendered ARIA tree text for the browser end-to-end tests."""

from __future__ import annotations

import re

_REF_ID_PATTERN = re.compile(r"\[ref=((f\d+_)?e\d+)\]")


def extract_ref_ids(aria_tree: str, name_filter: str = "", role_filter: str = "") -> list[str]:
    """Extract ref_ids from rendered aria_tree string.

    Args:
        aria_tree: Rendered ARIA tree string with ref IDs (e.g., '- button "Submit" [ref=e0]')
        name_filter: Optional filter for element name (substring match)
        role_filter: Optional filter for element role (substring match)

    Returns:
        List of ref_ids (e.g., ['e0', 'e1', 'f1_e0'])
    """
    lines = aria_tree.split("\n")
    ref_ids = []

    for line in lines:
        match = _REF_ID_PATTERN.search(line)
        if not match:
            continue

        if name_filter and name_filter not in line:
            continue
        if role_filter and role_filter not in line:
            continue

        ref_ids.append(match.group(1))

    return ref_ids
