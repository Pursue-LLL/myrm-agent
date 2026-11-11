"""
Tree Truncator (Smart Budget-Aware Truncation)
Provides generic utilities to intelligently truncate tree structures (ARIA accessibility trees)
based on token budgets and semantic weighting, keeping every retained node structurally intact.
"""

import copy
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.browser.snapshot.aria_types import EnhancedNode


def _get_aria_weight(role: str) -> float:
    role = role.lower()
    if role in {"main", "article", "dialog", "application", "region"}:
        return 2.0
    if role in {"button", "link", "textbox", "searchbox", "combobox", "listbox", "checkbox", "radio"}:
        return 1.5
    if role in {"navigation", "banner", "contentinfo", "complementary"}:
        return 0.2
    return 1.0


def _compute_aria_sizes(nodes: tuple["EnhancedNode", ...]) -> dict[int, int]:
    sizes: dict[int, int] = {}

    def _visit(node: "EnhancedNode") -> int:
        my_size = len(node.node.role) + len(node.node.name) + 10
        if node.ref_id:
            my_size += len(node.ref_id) + 5
        child_size = sum(_visit(c) for c in node.children)
        total = my_size + child_size
        sizes[id(node)] = total
        return total

    for n in nodes:
        _visit(n)
    return sizes


def truncate_aria_tree(nodes: list["EnhancedNode"], max_tokens: int) -> tuple[list["EnhancedNode"], bool]:
    """
    Intelligently truncate an ARIA tree to fit within max_tokens.
    Returns a new deeply-copied truncated tree tuple.
    """
    chars_per_token = 4
    max_chars = max_tokens * chars_per_token

    sizes = _compute_aria_sizes(tuple(nodes))
    total_size = sum(sizes[id(n)] for n in nodes)

    if total_size <= max_chars:
        return nodes, False

    def _truncate_node(node: "EnhancedNode", budget: int) -> "EnhancedNode | None":
        node_size = sizes[id(node)]
        if node_size <= budget:
            return node

        my_overhead = len(node.node.role) + len(node.node.name) + 10
        if node.ref_id:
            my_overhead += len(node.ref_id) + 5

        available = budget - my_overhead

        # Deep copy AriaNode to prevent mutation
        new_aria = copy.copy(node.node)
        new_aria.children = []  # We don't use this directly anyway, EnhancedNode does

        if available <= 0 or not node.children:
            marker = " [TRUNCATED]"
            keep = max(0, budget - len(marker))
            if new_aria.name and keep > 0 and len(new_aria.name) > keep:
                new_aria.name = new_aria.name[:keep] + marker
            else:
                new_aria.name = marker
            return replace(node, node=new_aria, children=())

        if len(node.children) == 1:
            child = _truncate_node(node.children[0], available)
            new_children = (child,) if child else ()
            return replace(node, node=new_aria, children=new_children)

        child_metrics = []
        total_mass = 0.0
        for c in node.children:
            c_size = sizes[id(c)]
            c_weight = _get_aria_weight(c.node.role)
            mass = c_size * c_weight
            total_mass += mass
            child_metrics.append((c, c_size, mass))

        new_children_list = []
        for c, c_size, mass in child_metrics:
            if total_mass > 0:
                c_budget = int(available * (mass / total_mass))
            else:
                c_budget = int(available / len(node.children))

            if c_budget < 20:
                pass  # Drop
            elif c_budget < c_size:
                truncated_c = _truncate_node(c, c_budget)
                if truncated_c:
                    new_children_list.append(truncated_c)
            else:
                new_children_list.append(c)

        return replace(node, node=new_aria, children=tuple(new_children_list))

    # Greedy-keep strategy: sort by weight (desc), keep nodes until budget exhausted.
    # This avoids the "spread too thin" problem where many same-weight nodes each
    # get budget < threshold and all get dropped.
    indexed_nodes = [(i, n, sizes[id(n)], _get_aria_weight(n.node.role)) for i, n in enumerate(nodes)]
    indexed_nodes.sort(key=lambda x: x[3], reverse=True)

    remaining_budget = max_chars
    kept: list[tuple[int, EnhancedNode]] = []

    for orig_idx, n, n_size, _weight in indexed_nodes:
        if remaining_budget <= 0:
            break

        if n_size <= remaining_budget:
            kept.append((orig_idx, n))
            remaining_budget -= n_size
        else:
            tn = _truncate_node(n, remaining_budget)
            if tn:
                kept.append((orig_idx, tn))
            remaining_budget = 0

    # Restore original order
    kept.sort(key=lambda x: x[0])
    new_nodes = [n for _, n in kept]

    return new_nodes, True
