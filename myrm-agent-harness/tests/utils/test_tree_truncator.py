from myrm_agent_harness.toolkits.browser.snapshot.aria_types import AriaNode, EnhancedNode
from myrm_agent_harness.utils.tree_truncator import _get_aria_weight, truncate_aria_tree


def test_aria_truncation():
    # Construct a tree
    # root
    #  |- main (role=main)
    #  |   |- button (role=button)
    #  |- nav (role=navigation)
    #      |- link (role=link)

    main_node = EnhancedNode(
        node=AriaNode(role="main", name="Main Content"),
        children=(EnhancedNode(node=AriaNode(role="button", name="Click Me " * 10)),),
    )

    nav_node = EnhancedNode(
        node=AriaNode(role="navigation", name="Nav Menu"),
        children=(EnhancedNode(node=AriaNode(role="link", name="Link " * 100)),),
    )

    root = EnhancedNode(node=AriaNode(role="document", name="Doc"), children=(main_node, nav_node))

    # 1. No truncation
    nodes, was_truncated = truncate_aria_tree([root], max_tokens=10000)
    assert not was_truncated
    assert len(nodes) == 1

    # 2. Truncation
    # Link is huge, Nav weight is 0.2. Main weight is 2.0.
    nodes, was_truncated = truncate_aria_tree([root], max_tokens=20)  # 80 chars
    assert was_truncated
    assert len(nodes) == 1

    # Check that it reached TRUNCATED
    def has_truncated(n: EnhancedNode) -> bool:
        if "[TRUNCATED]" in n.node.name:
            return True
        return any(has_truncated(c) for c in n.children)

    assert has_truncated(nodes[0])


def test_weights():
    assert _get_aria_weight("main") == 2.0
    assert _get_aria_weight("navigation") == 0.2
    assert _get_aria_weight("group") == 1.0
